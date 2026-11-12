"""Measurement processing: a closed vocabulary (`KINDS`) the engine executes.

Closed, because an agent free to transform the data could normalise away what
its model cannot fit. Each op declared by data extraction is a replayable pure
function of one cell (condition, time, replicate) or of one declared reference
cell, so held-out rows are processed independently; a reference inside the
holdout is refused by name. The agent contract, `skills/data_extraction.md` and
`tests/data_processing_unit.py` quote `KINDS`; the drift test holds them equal.
"""

from __future__ import annotations

import pandas as pd

# kind -> required arguments
KINDS: dict[str, list[str]] = {
    "normalize_by_group_sum": ["labels"],
    "subtract_reference": ["labels", "reference"],
    "scale_units": ["labels", "factor", "from_units", "to_units"],
}
REFERENCE_KEYS = ("observable_label", "condition_label", "time")
CELL = ["condition_key", "time", "replicate"]


class ProcessingRefused(ValueError):
    """A declared op the engine will not execute (unknown kind, missing
    argument, unknown label, or a reference inside the holdout)."""


def holdout_conditions(long_df: pd.DataFrame, holdout_labels) -> set[str]:
    """Condition LABELS that are held out, matched the way the S3 split
    matches them: by declared label or by semantic key."""
    from octomod.workflow_modules.data.engine import parse_declared_label

    keys = (
        long_df["condition_key"].fillna("").astype(str)
        if "condition_key" in long_df
        else None
    )
    out: set[str] = set()
    for h in holdout_labels or []:
        h = str(h)
        out |= set(
            long_df.loc[
                long_df["condition_label"].astype(str) == h, "condition_label"
            ].astype(str)
        )
        k = parse_declared_label(h)
        if k and keys is not None:
            out |= set(long_df.loc[keys == k, "condition_label"].astype(str))
    return out


def validate(ops, long_df: pd.DataFrame, holdout_labels) -> None:
    """Raise ProcessingRefused for the first illegal op, before any is run."""
    if ops is None:
        return
    if not isinstance(ops, list):
        raise ProcessingRefused("`processing` must be a list of operations")
    labels_present = set(long_df["observable_label"].astype(str))
    conditions_present = set(long_df["condition_label"].astype(str))
    held = holdout_conditions(long_df, holdout_labels)
    for i, op in enumerate(ops):
        where = f"processing[{i}]"
        if not isinstance(op, dict) or "kind" not in op:
            raise ProcessingRefused(
                f"{where}: an operation is a dict with a `kind`; legal kinds: {sorted(KINDS)}"
            )
        kind = str(op["kind"])
        if kind not in KINDS:
            raise ProcessingRefused(
                f"{where}: kind {kind!r} is not in the vocabulary; legal kinds: {sorted(KINDS)}. "
                f"Dropping or clipping rows, log or other transformations, and anything that "
                f"reads a fitted quantity are not operations here by rule."
            )
        missing = [a for a in KINDS[kind] if a not in op]
        if missing:
            raise ProcessingRefused(f"{where} ({kind}): missing argument(s) {missing}")
        labels = op.get("labels")
        if not isinstance(labels, list) or not labels:
            raise ProcessingRefused(
                f"{where} ({kind}): `labels` must be a non-empty list of observable labels"
            )
        unknown = [str(x) for x in labels if str(x) not in labels_present]
        if unknown:
            raise ProcessingRefused(
                f"{where} ({kind}): labels {unknown} are not in the extracted table; present: {sorted(labels_present)}"
            )
        if kind == "subtract_reference":
            ref = op.get("reference")
            if not isinstance(ref, dict) or not any(k in ref for k in REFERENCE_KEYS):
                raise ProcessingRefused(
                    f"{where} (subtract_reference): `reference` names ONE of {REFERENCE_KEYS}"
                )
            if "condition_label" in ref:
                cl = str(ref["condition_label"])
                if cl not in conditions_present:
                    raise ProcessingRefused(
                        f"{where} (subtract_reference): reference condition {cl!r} is not in the table; "
                        f"present: {sorted(conditions_present)}"
                    )
                if cl in held:
                    raise ProcessingRefused(
                        f"{where} (subtract_reference): your reference {cl!r} is a HELD-OUT condition — "
                        f"a processing step may not read the rows the model is later scored on. "
                        f"Held out: {sorted(held)}; usable references: {sorted(conditions_present - held)}"
                    )
            if (
                "observable_label" in ref
                and str(ref["observable_label"]) not in labels_present
            ):
                raise ProcessingRefused(
                    f"{where} (subtract_reference): reference observable {ref['observable_label']!r} is not in the table"
                )
        if kind == "scale_units":
            try:
                float(op["factor"])
            except (TypeError, ValueError):
                raise ProcessingRefused(
                    f"{where} (scale_units): `factor` must be a number"
                ) from None


def apply(
    ops, long_df: pd.DataFrame, holdout_labels
) -> tuple[pd.DataFrame, list[dict]]:
    """Execute the declared ops in order on a copy; return (processed table,
    record). The record carries each op with its resolved numbers (per-cell
    divisors, reference values, factor), so the report shows what was done."""
    validate(ops, long_df, holdout_labels)
    df = long_df.copy()
    record: list[dict] = []
    for op in ops or []:
        kind = str(op["kind"])
        labels = [str(x) for x in op["labels"]]
        mask = df["observable_label"].astype(str).isin(labels)
        entry = {
            "kind": kind,
            "labels": labels,
            "rationale": str(op.get("rationale", "")),
            "n_rows": int(mask.sum()),
        }
        if kind == "normalize_by_group_sum":
            cell = [c for c in CELL if c in df.columns]
            sums = df[mask].groupby(cell)["value"].transform("sum")
            div = sums.where(sums != 0.0)  # a zero sum stays unnormalised, and says so
            df.loc[mask, "processing_divisor"] = div
            df.loc[mask, "value"] = df.loc[mask, "value"] / div
            per_cell = (
                df[mask]
                .drop_duplicates(cell)[cell + ["processing_divisor"]]
                .sort_values(cell)
            )
            entry["divisors"] = [
                {**{k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}}
                for row in per_cell.to_dict(orient="records")
            ]
            entry["zero_sum_cells"] = int(sums.eq(0.0).sum())
        elif kind == "subtract_reference":
            ref = op["reference"]
            if "observable_label" in ref:
                ro = str(ref["observable_label"])
                cell = [c for c in CELL if c in df.columns]
                ref_rows = df[df["observable_label"].astype(str) == ro].set_index(cell)[
                    "value"
                ]
                keyed = df.loc[mask, cell].apply(tuple, axis=1)
                sub = keyed.map(lambda k, _r=ref_rows: float(_r.get(k, float("nan"))))
                entry["reference"] = {"observable_label": ro, "matched_on": cell}
            elif "condition_label" in ref:
                # subtract the reference condition's mean over replicates at the
                # same time and observable; not replicate-matched, which would
                # leave the reference rows at exactly zero and deflate every
                # replicate-based noise floor downstream
                rc = str(ref["condition_label"])
                by = [c for c in ("observable_label", "time") if c in df.columns]
                ref_df = df[df["condition_label"].astype(str) == rc]
                ref_mean = ref_df.groupby(by)["value"].mean()
                keyed = df.loc[mask, by].apply(tuple, axis=1)
                sub = keyed.map(lambda k, _r=ref_mean: float(_r.get(k, float("nan"))))
                entry["reference"] = {
                    "condition_label": rc,
                    "matched_on": by,
                    "values": {str(k): float(v) for k, v in ref_mean.items()},
                }
            else:
                rt = float(ref["time"])
                by = [
                    c
                    for c in ("observable_label", "condition_key", "replicate")
                    if c in df.columns
                ]
                ref_df = df[df["time"].astype(float) == rt]
                ref_val = ref_df.groupby(by)["value"].mean()
                keyed = df.loc[mask, by].apply(tuple, axis=1)
                sub = keyed.map(lambda k, _r=ref_val: float(_r.get(k, float("nan"))))
                entry["reference"] = {"time": rt, "matched_on": by}
            n_missing = int(sub.isna().sum())
            df.loc[mask, "processing_reference"] = sub.values
            df.loc[mask, "value"] = df.loc[mask, "value"] - sub.fillna(0.0).values
            entry["rows_without_reference_left_unchanged"] = n_missing
        elif kind == "scale_units":
            f = float(op["factor"])
            df.loc[mask, "value"] = df.loc[mask, "value"] * f
            entry.update(
                {
                    "factor": f,
                    "from_units": str(op["from_units"]),
                    "to_units": str(op["to_units"]),
                }
            )
        record.append(entry)
    return df, record


def card_lines(record: list[dict]) -> list[str]:
    """One line per op, with the numbers, for the S2 console and the S3 card."""
    out = []
    for e in record or []:
        labels = ", ".join(e.get("labels", []))
        if e["kind"] == "normalize_by_group_sum":
            divs = e.get("divisors") or []
            shown = " / ".join(
                f"{d.get('processing_divisor'):.3g}"
                for d in divs[:6]
                if d.get("processing_divisor") is not None
            )
            more = f" … ({len(divs)} cells)" if len(divs) > 6 else ""
            out.append(
                f"processing: {labels} row-normalised by their per-cell sum — divisors {shown}{more}"
            )
        elif e["kind"] == "subtract_reference":
            ref = e.get("reference") or {}
            what = next((f"{k} {ref[k]!r}" for k in REFERENCE_KEYS if k in ref), "?")
            out.append(
                f"processing: {labels} minus the reference {what} ({e.get('n_rows')} rows)"
            )
        elif e["kind"] == "scale_units":
            out.append(
                f"processing: {labels} x {e.get('factor')} ({e.get('from_units')} -> {e.get('to_units')})"
            )
    return out


def summary_for_agent(record: list[dict]) -> dict | None:
    """What the observation agent is told about the processed table: the
    facts, and the instruction not to scale twice."""
    if not record:
        return None
    return {
        "ops": [
            {
                k: v
                for k, v in e.items()
                if k
                in ("kind", "labels", "factor", "to_units", "reference", "rationale")
            }
            for e in record
        ],
        "how_to_read_this": (
            "The measurement table you are mapping onto was PROCESSED by the "
            "engine as declared by data extraction, before any model existed. "
            "Row-normalised values sum to one per cell and their residuals are "
            "correlated in a way the likelihood ignores; subtracted values can be "
            "negative; scaled values carry `to_units`. Do not add a second scale "
            "or offset on top of a processing step that already did it — and "
            "where the same assumption can be written model-side (a per-timepoint "
            "or per-condition scale factor), prefer that."
        ),
    }
