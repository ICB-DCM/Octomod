"""The experimental design of a data file, without any measurement value.

Unique levels per design column, rows and replicates per cell, and the absent
cells of the full factorial, so an agent shown only a preview still knows which
cells are missing. A measurement column is reported by name, dtype and
cardinality only. Granted to `data_extraction` and `condition`
(docs/ROUTING.md), not to construction.
"""

from __future__ import annotations

import itertools
import re

import pandas as pd

# At most this many distinct values makes a candidate design column; above it a
# numeric column is a measurement and its values are never shown. A factor with
# more levels is rare enough that mislabelling it is the lesser risk.
MAX_LEVELS = 16
# Without a time column, a numeric column whose values repeat this rarely is
# read as measurement. Only a fallback — the time test in _role_of is the real one.
UNIQUE_FRACTION = 0.5
# The factorial is reported only when it is small enough to read. Above this the
# counts still appear; the enumeration of absent cells does not.
MAX_CELLS = 200
MAX_MISSING_LISTED = 24

_TIME_RE = re.compile(
    r"^(t|time|time_\w+|\w*_time|hours?|hrs?|min\w*|sec\w*|days?)$", re.I
)
_REP_RE = re.compile(r"^(rep|reps|replicate|replicates|repeat|run|trial)$", re.I)


def _role_of(name: str, col: pd.Series, df: pd.DataFrame, time_col: str | None) -> str:
    """Guess a column's role: design / time / replicate / measurement / identifier.

    Cardinality alone does not separate design from measurement (a small table's
    readings fall under any level cap); repetition does: a design level recurs
    across time points, a reading belongs to one row. Without a time column the
    value-to-row ratio is the fallback.
    """
    if _TIME_RE.match(str(name)):
        return "time"
    if _REP_RE.match(str(name)):
        return "replicate"
    n_unique = int(col.nunique(dropna=True))
    n_rows = int(len(col))
    if n_unique <= 1:
        return "design"  # a constant column IS the design, held fixed
    numeric = pd.api.types.is_numeric_dtype(col)
    if numeric and n_unique > MAX_LEVELS:
        return "measurement"
    if not numeric:
        return "design" if n_unique <= MAX_LEVELS else "identifier"
    if time_col is not None and time_col in df.columns:
        # a design level recurs across time points; a reading does not
        spans = df.groupby(col, dropna=True)[time_col].nunique(dropna=True)
        if float(spans.mean()) <= 1.0:
            return "measurement"
        return "design"
    # no time column to ask with: values that almost never repeat are readings
    return "measurement" if n_unique / max(n_rows, 1) > UNIQUE_FRACTION else "design"


def summarize_frame(df: pd.DataFrame) -> dict:
    """Summarize one file's design; deterministic (sorted levels, sorted cells)."""
    # found first: the other roles are judged by repetition across time
    time_col = next((c for c in df.columns if _TIME_RE.match(str(c))), None)
    cols: dict[str, dict] = {}
    for name in df.columns:
        col = df[name]
        role = _role_of(name, col, df, time_col)
        rec = {
            "role": role,
            "dtype": str(col.dtype),
            "n_unique": int(col.nunique(dropna=True)),
            "n_missing": int(col.isna().sum()),
        }
        if role in ("design", "time", "replicate"):
            try:
                rec["levels"] = sorted(col.dropna().unique().tolist())
            except TypeError:  # mixed types do not sort
                rec["levels"] = sorted(map(str, col.dropna().unique().tolist()))
        # role == "measurement": name, dtype and cardinality only. No values.
        cols[str(name)] = rec

    design_cols = [c for c, r in cols.items() if r["role"] == "design"]
    time_cols = [c for c, r in cols.items() if r["role"] == "time"]
    rep_cols = [c for c, r in cols.items() if r["role"] == "replicate"]

    out: dict = {
        "n_rows": int(len(df)),
        "columns": cols,
        "design_columns": design_cols,
        "time_columns": time_cols,
        "replicate_columns": rep_cols,
        "measurement_columns": [
            c for c, r in cols.items() if r["role"] == "measurement"
        ],
    }
    if not design_cols:
        out["factorial"] = {
            "available": False,
            "why": "no column looked like a design factor (all were time, "
            "replicate, identifier, or measurement)",
        }
        return out

    levels = [cols[c]["levels"] for c in design_cols]
    n_full = 1
    for lv in levels:
        n_full *= len(lv)
    present_rows = df[design_cols].drop_duplicates()
    present = {tuple(r) for r in present_rows.to_numpy().tolist()}

    per_cell = []
    grouped = df.groupby(design_cols, dropna=False)
    for key, cell in grouped:
        key = key if isinstance(key, tuple) else (key,)
        rec = {
            "cell": dict(zip(design_cols, list(key), strict=False)),
            "n_rows": int(len(cell)),
        }
        if time_cols:
            rec["n_time_points"] = int(cell[time_cols[0]].nunique(dropna=True))
        if rep_cols:
            rec["n_replicates"] = int(cell[rep_cols[0]].nunique(dropna=True))
        per_cell.append(rec)
    per_cell.sort(key=lambda r: str(sorted(r["cell"].items())))

    fact: dict = {
        "available": True,
        "factors": design_cols,
        "n_full_factorial": n_full,
        "n_present": len(present),
        "n_absent": n_full - len(present),
        "balanced": n_full == len(present),
        "per_cell": per_cell,
    }
    if n_full <= MAX_CELLS:
        absent = [c for c in itertools.product(*levels) if c not in present]
        fact["absent_cells"] = [
            dict(zip(design_cols, list(c), strict=False))
            for c in absent[:MAX_MISSING_LISTED]
        ]
        if len(absent) > MAX_MISSING_LISTED:
            fact["absent_cells_truncated"] = len(absent) - MAX_MISSING_LISTED
    else:
        fact["absent_cells"] = None
        fact["why_not_enumerated"] = (
            f"the full factorial is {n_full} cells, over the {MAX_CELLS} this "
            f"payload enumerates; the counts above still hold"
        )
    out["factorial"] = fact
    return out


def compute(frames: dict[str, pd.DataFrame]) -> dict:
    """Build the design-summary artifact: one record per file, plus how to read it."""
    return {
        "available": True,
        "per_file": {str(k): summarize_frame(v) for k, v in sorted(frames.items())},
        "how_to_read_this": (
            "Computed from the raw files by the engine — no model, no agent, no "
            "measurement values. `role` is a GUESS from column name and "
            "cardinality; correct it if it is wrong, and say so in your reply. "
            "`factorial.absent_cells` names the design combinations that are "
            "NOT in the file: the preview you are also shown is the first 25 "
            "rows only, and a missing cell is usually not visible there."
        ),
    }


def card_lines(summary: dict, limit: int = 4) -> list[str]:
    """A compact table for the prompt, beside the 25-row preview."""
    if not summary.get("available"):
        return []
    out: list[str] = []
    for name, rec in list(summary.get("per_file", {}).items())[:limit]:
        out.append(f"  {name}: {rec['n_rows']} rows")
        for col, c in rec["columns"].items():
            if c["role"] == "measurement":
                out.append(
                    f"    {col:<16} measurement ({c['dtype']}, "
                    f"{c['n_unique']} distinct — values not shown)"
                )
            else:
                lv = c.get("levels", [])
                shown = ", ".join(map(str, lv[:8])) + (" …" if len(lv) > 8 else "")
                out.append(f"    {col:<16} {c['role']:<11} [{shown}]")
        f = rec.get("factorial", {})
        if f.get("available"):
            out.append(
                f"    factorial: {f['n_present']}/{f['n_full_factorial']} cells "
                f"present ({'balanced' if f['balanced'] else 'INCOMPLETE'})"
            )
            for cell in f.get("absent_cells") or []:
                out.append(
                    "      ABSENT: " + ", ".join(f"{k}={v}" for k, v in cell.items())
                )
    return out
