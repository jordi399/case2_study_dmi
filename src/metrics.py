"""Metric calculations for the spend-per-card investigation.

Units used throughout
---------------------
* Cards: Table 1 reports thousands (k). Converted to absolute counts here.
* Spend: Table 1 reports ₹ crore (1 Cr = 1e7). Converted to ₹ here.
* Tables 2-4 are already in ₹ per card per month.
"""
import numpy as np
import pandas as pd

CRORE = 1e7
THOUSAND = 1e3


# --------------------------------------------------------------------------- #
# Table 1 - portfolio trend
# --------------------------------------------------------------------------- #
def portfolio_metrics(t1: pd.DataFrame) -> pd.DataFrame:
    """Add per-card metrics to the monthly portfolio table."""
    df = t1.copy()
    df["active_cards"] = df["active_cards_k"] * THOUSAND
    df["total_spend_inr"] = df["total_spend_cr"] * CRORE
    df["zero_spend_share"] = df["zero_spend_pct"] / 100
    df["spending_cards"] = df["active_cards"] * (1 - df["zero_spend_share"])
    df["zero_spend_cards"] = df["active_cards"] * df["zero_spend_share"]

    # The KPI leadership is looking at
    df["avg_spend_per_active_card"] = df["total_spend_inr"] / df["active_cards"]
    # The like-for-like view: only cards that actually transacted
    df["avg_spend_per_spending_card"] = df["total_spend_inr"] / df["spending_cards"]

    # Implied cards leaving the active base:
    # previous active + new cards added - current active
    df["implied_cards_exited"] = (
        df["active_cards"].shift(1) + df["new_cards_added_k"] * THOUSAND - df["active_cards"]
    )
    return df


def growth_summary(pm: pd.DataFrame) -> pd.Series:
    """Jan -> Jun % change for the headline metrics."""
    first, last = pm.iloc[0], pm.iloc[-1]
    cols = [
        "active_cards",
        "spending_cards",
        "zero_spend_cards",
        "total_spend_inr",
        "avg_spend_per_active_card",
        "avg_spend_per_spending_card",
    ]
    return pd.Series({c: last[c] / first[c] - 1 for c in cols}, name="jan_to_jun_change")


def decompose_avg_change(pm: pd.DataFrame, start: int = 0, end: int = -1) -> pd.Series:
    """Split the change in avg spend per active card into two effects.

    avg per active card = (1 - zero_share) x avg per spending card
                        =  activation rate  x spend per spending card

    A symmetric (Shapley / midpoint) split is used so the result does not
    depend on which factor is changed first:
        d(a*b) = da * mean(b) + db * mean(a)
    """
    s, e = pm.iloc[start], pm.iloc[end]
    a0, a1 = 1 - s["zero_spend_share"], 1 - e["zero_spend_share"]
    b0, b1 = s["avg_spend_per_spending_card"], e["avg_spend_per_spending_card"]

    activation_effect = (a1 - a0) * (b0 + b1) / 2
    spend_effect = (b1 - b0) * (a0 + a1) / 2
    total = e["avg_spend_per_active_card"] - s["avg_spend_per_active_card"]
    assert np.isclose(activation_effect + spend_effect, total)

    return pd.Series(
        {
            "start_avg": s["avg_spend_per_active_card"],
            "zero_spend_dilution": activation_effect,
            "lower_spend_per_spending_card": spend_effect,
            "end_avg": e["avg_spend_per_active_card"],
            "total_change": total,
            "share_from_zero_spend": activation_effect / total,
            "share_from_spend_per_spender": spend_effect / total,
        }
    )


def monthly_bridge(pm: pd.DataFrame) -> pd.DataFrame:
    """Month-on-month version of the decomposition."""
    rows = []
    for i in range(1, len(pm)):
        d = decompose_avg_change(pm, i - 1, i)
        rows.append(
            {
                "month": pm.iloc[i]["month"],
                "zero_spend_dilution": d["zero_spend_dilution"],
                "lower_spend_per_spending_card": d["lower_spend_per_spending_card"],
                "total_change": d["total_change"],
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Table 3 - vintage view
# --------------------------------------------------------------------------- #
def vintage_metrics(t3: pd.DataFrame) -> pd.DataFrame:
    """Share of cards vs share of spend by vintage (June)."""
    df = t3.copy()
    df["card_share"] = df["pct_cards"] / 100
    df["spend_contrib"] = df["card_share"] * df["avg_spend_inr"]
    df["spend_share"] = df["spend_contrib"] / df["spend_contrib"].sum()
    return df


def vintage_mix_scenarios(t3: pd.DataFrame, new_shares=(0.0, 0.15, 0.20, 0.28)) -> pd.DataFrame:
    """Portfolio average if the <3-month cohort were a different share of the base.

    Holds each cohort's own average spend fixed at June levels and keeps the
    seasoned cohorts in their June proportions. Isolates the pure mix effect.
    """
    new = t3[t3["vintage"] == "< 3 months"].iloc[0]
    old = t3[t3["vintage"] != "< 3 months"]
    seasoned_avg = np.average(old["avg_spend_inr"], weights=old["pct_cards"])
    actual = np.average(t3["avg_spend_inr"], weights=t3["pct_cards"])

    rows = []
    for s in new_shares:
        avg = s * new["avg_spend_inr"] + (1 - s) * seasoned_avg
        rows.append({"new_card_share": s, "portfolio_avg": avg, "vs_june_actual": avg / actual - 1})
    return pd.DataFrame(rows), seasoned_avg, actual


def new_card_zero_spend_floor(t3: pd.DataFrame, pm: pd.DataFrame) -> pd.Series:
    """Minimum number of zero-spend cards that must be new cards.

    Median spend of the <3-month cohort is ₹0, so at least half of that cohort
    spent nothing in June.
    """
    jun = pm.iloc[-1]
    new_share = t3.loc[t3["vintage"] == "< 3 months", "pct_cards"].iloc[0] / 100
    new_cards = new_share * jun["active_cards"]
    min_zero_new = 0.5 * new_cards
    return pd.Series(
        {
            "june_new_cards": new_cards,
            "june_zero_spend_cards": jun["zero_spend_cards"],
            "min_zero_spend_new_cards": min_zero_new,
            "min_share_of_zero_spend_from_new": min_zero_new / jun["zero_spend_cards"],
            "jan_to_jun_increase_in_zero_spend": jun["zero_spend_cards"] - pm.iloc[0]["zero_spend_cards"],
        }
    )


# --------------------------------------------------------------------------- #
# Table 4 - category mix
# --------------------------------------------------------------------------- #
def category_mix(t4: pd.DataFrame) -> pd.DataFrame:
    df = t4.copy()
    df["share_change_pp"] = df["jun_share_pct"] - df["jan_share_pct"]
    return df


def ticket_weighted_average(t4: pd.DataFrame) -> pd.Series:
    """Average ticket implied by the mix, IF shares are shares of transactions.

    Ticket sizes are held fixed, so any change is purely a mix effect.
    """
    jan = np.average(t4["avg_ticket_inr"], weights=t4["jan_share_pct"])
    jun = np.average(t4["avg_ticket_inr"], weights=t4["jun_share_pct"])
    return pd.Series({"jan_avg_ticket": jan, "jun_avg_ticket": jun, "change": jun / jan - 1})


# --------------------------------------------------------------------------- #
# Cross-table consistency
# --------------------------------------------------------------------------- #
def consistency_checks(pm: pd.DataFrame, t2: pd.DataFrame, t3: pd.DataFrame) -> pd.DataFrame:
    """Compare the June average spend per active card across the three tables."""
    jun = pm.iloc[-1]
    t1_avg = jun["avg_spend_per_active_card"]
    t3_avg = np.average(t3["avg_spend_inr"], weights=t3["pct_cards"])

    # Table 2 only gives buckets: the lowest possible average puts every card
    # at its bucket's lower edge.
    t2_min = (t2["lower_inr"].fillna(0) * t2["pct_active_cards"] / 100).sum()

    rows = [
        ("Table 1: total spend / active cards", t1_avg, "exact"),
        ("Table 2: lowest average the buckets allow", t2_min, "lower bound"),
        ("Table 3: card-weighted vintage average", t3_avg, "exact"),
    ]
    out = pd.DataFrame(rows, columns=["source", "june_avg_spend_inr", "type"])
    out["ratio_to_table3"] = out["june_avg_spend_inr"] / t3_avg
    return out


def cohort_count_check(pm: pd.DataFrame, t3: pd.DataFrame) -> pd.Series:
    """Cards added Apr-Jun vs the <3-month share reported in Table 3."""
    added_q2 = pm[pm["month"].isin(["Apr", "May", "Jun"])]["new_cards_added_k"].sum() * THOUSAND
    t3_new = t3.loc[t3["vintage"] == "< 3 months", "pct_cards"].iloc[0] / 100 * pm.iloc[-1]["active_cards"]
    return pd.Series({"cards_added_apr_jun": added_q2, "t3_new_cards_in_active_base": t3_new,
                      "gap": added_q2 - t3_new})
