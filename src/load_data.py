"""Load the four case-study tables and run basic integrity checks."""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]


def load_tables(raw_dir: Path = RAW_DIR) -> dict:
    """Return the four tables as DataFrames, keyed t1..t4."""
    t1 = pd.read_csv(raw_dir / "t1_portfolio_trend.csv")
    t1["month"] = pd.Categorical(t1["month"], categories=MONTH_ORDER, ordered=True)
    t1 = t1.sort_values("month").reset_index(drop=True)

    t2 = pd.read_csv(raw_dir / "t2_spend_distribution_jun.csv")
    t3 = pd.read_csv(raw_dir / "t3_vintage_spend_jun.csv")
    t4 = pd.read_csv(raw_dir / "t4_category_mix.csv")

    tables = {"t1": t1, "t2": t2, "t3": t3, "t4": t4}
    validate_tables(tables)
    return tables


def validate_tables(tables: dict) -> None:
    """Shares must add up to 100%; fail loudly if a table was mistyped."""
    checks = {
        "t2 % active cards": tables["t2"]["pct_active_cards"].sum(),
        "t3 % cards": tables["t3"]["pct_cards"].sum(),
        "t4 Jan share": tables["t4"]["jan_share_pct"].sum(),
        "t4 Jun share": tables["t4"]["jun_share_pct"].sum(),
    }
    bad = {k: v for k, v in checks.items() if abs(v - 100) > 0.5}
    if bad:
        raise ValueError(f"Shares do not sum to 100%: {bad}")
