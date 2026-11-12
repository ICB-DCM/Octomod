"""Below-detection measurements: declared, not modelled.

No censored likelihood is used. Data extraction declares what the source did
with values below detection — `{observable_label, threshold, rule, note}`, `rule`
one of `RULES`, `threshold` on the measurement's own scale or null — and the
declaration is counted, shown to the observation-model agent and stated on the
report, because an imputed floor biases every candidate the same way.
"""

from __future__ import annotations

import numpy as np

RULES = ("imputed", "dropped", "left_as_is")
KEYS = ("observable_label", "threshold", "rule", "note")


def declared(report: dict) -> list[dict]:
    raw = (report or {}).get("below_detection") or []
    return [e for e in raw if isinstance(e, dict)]


def problems(entries, labels_present) -> list[str]:
    """T0 check: every entry names a declared label, a legal rule and a numeric
    or null threshold. Problems are named by index, for the agent's re-ask."""
    out: list[str] = []
    labels = set(labels_present or [])
    if not isinstance(entries, list):
        return [f"below_detection must be a list of {list(KEYS)}"]
    for k, e in enumerate(entries):
        where = f"below_detection[{k}]"
        if not isinstance(e, dict):
            out.append(f"{where} is not an object ({list(KEYS)})")
            continue
        lab = e.get("observable_label")
        if lab not in labels:
            out.append(
                f"{where}.observable_label {lab!r} is not a declared observable "
                f"label (declared: {sorted(labels)})"
            )
        rule = e.get("rule")
        if rule not in RULES:
            out.append(f"{where}.rule {rule!r} is not one of {list(RULES)}")
        thr = e.get("threshold")
        if thr is not None and not isinstance(thr, (int, float)):
            out.append(f"{where}.threshold must be a number or null, got {thr!r}")
        unknown = sorted(set(e) - set(KEYS))
        if unknown:
            out.append(f"{where} carries unknown key(s) {unknown}")
    return out


def summary(entries: list[dict], long_df, counted_on: str | None = None) -> list[dict]:
    """Each declaration with the number of rows its threshold touches.

    Counted once, by S2, on the raw extracted values (the scale a declared
    threshold refers to) and recorded in the data report as
    `below_detection_summary`; every later reader uses that record. With no
    table (`long_df is None`) the counts are None, not zero."""
    out = []
    have_table = long_df is not None and "observable_label" in getattr(
        long_df, "columns", []
    )
    for e in entries:
        lab = e.get("observable_label")
        thr = e.get("threshold")
        n_total: int | None = None
        n_at: int | None = None
        if have_table:
            vals = long_df.loc[long_df["observable_label"] == lab, "value"].to_numpy(
                dtype=float
            )
            n_total = int(vals.size)
            n_at = (
                int(np.sum(vals <= float(thr)))
                if isinstance(thr, (int, float)) and vals.size
                else 0
            )
        out.append(
            {
                "observable_label": lab,
                "threshold": thr,
                "rule": e.get("rule"),
                "note": e.get("note") or "",
                "n_rows": n_total,
                "n_at_or_below_threshold": n_at,
                "counted_on": counted_on if have_table else None,
            }
        )
    return out


def _one_line(s: dict) -> str:
    thr = s.get("threshold")
    if s.get("n_rows") is None:
        at = "counts not recorded for this run"
    elif isinstance(thr, (int, float)):
        at = f"{s['n_at_or_below_threshold']} of {s['n_rows']} rows at or below {thr:g}"
    else:
        at = f"{s['n_rows']} rows, no numeric threshold stated"
    return f"{s['observable_label']}: below-detection values {s['rule']} by the source ({at})"


def findings(summaries: list[dict]) -> list[str]:
    """The plausibility screen's lines, one per declaration."""
    return [_one_line(s) for s in summaries]


CONDITIONAL_SENTENCE = (
    "Below-detection measurements are DECLARED, not modelled: no censored "
    "likelihood is used, so every candidate is fitted to the source's own "
    "handling of those values and the model comparison is conditional on it. "
    "The declaration IS shown to the observation-model agent as measurement "
    "evidence, so the noise shape it chose may depend on it; the engine's "
    "likelihood code does not. An imputed floor biases every candidate the same "
    "way and makes the comparison look cleaner than the data justifies."
)


def for_agent(summaries: list[dict]) -> dict | None:
    """What the observation-model agent is told, beside the data signals."""
    if not summaries:
        return None
    return {
        "declared": summaries,
        "how_to_read_this": (
            "The source reports these observables with a detection floor and "
            "the extraction declares how the source handled values below it. "
            "No censored likelihood exists in this engine: choose a noise shape "
            "that is honest at the floor (a constant or additive component, "
            "never pure proportional or a log transform where imputed floor "
            "values sit), and say in the rationale that the fit is conditional "
            "on the source's handling."
        ),
    }
