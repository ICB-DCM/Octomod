"""Print the divisors `normalize_by_group_sum` finds on the ctd_blind data (read-only):
the per-time-point column sums, expected 1.00 / 4.07 / 3.79 / 0.85.

    uv run python tools/probe_processing_ctd.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CSV = REPO / "testcase" / "ctd_blind" / "data" / "ctd_ms_timecourse.csv"


def long_table() -> pd.DataFrame:
    wide = pd.read_csv(CSV)
    labels = [c for c in wide.columns if c != "time_min"]
    rows = [
        {
            "observable_label": lab,
            "condition_label": "single",
            "condition_key": "single",
            "time": float(r["time_min"]),
            "value": float(r[lab]),
            "replicate": 1,
        }
        for _, r in wide.iterrows()
        for lab in labels
    ]
    return pd.DataFrame(rows)


def divisors() -> list[tuple[float, float]]:
    from octomod.workflow_modules.data import data_processing as dp

    df = long_table()
    labels = sorted(set(df["observable_label"]))
    _out, record = dp.apply(
        [{"kind": "normalize_by_group_sum", "labels": labels}], df, []
    )
    return [
        (float(d["time"]), float(d["processing_divisor"]))
        for d in record[0]["divisors"]
    ]


if __name__ == "__main__":
    for t, d in divisors():
        print(f"t = {t:6g} min   divisor (column sum) = {d:.3f}")
