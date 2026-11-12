"""What an agent is allowed to see, and how many bytes of it.

`core_for_agents` keeps every summary of `evaluation_core` (the report core)
and drops the sampled curves, naming the record key that holds them.
`fit_to_budget` degrades a prompt over the cap in the declared `PAYLOAD_BUDGET`
order, each step leaving a notice and a trim record (a `payload_trimmed`
ledger row, read back by the round's decision record); `prompt_budget` is the
blocking gate on the prompt actually sent, and nothing is ever truncated. The
cap (`agents.max_prompt_bytes`, null = no cap) is read only through
`prompt_cap`. Both budget and gate run on the prompt that is actually SENT: a
reply served from the record (`agent_calls/<role>`) costs nothing and reaches
no context window, so `call_cached` pays for neither — it renders through the
same budget only so that the ask it compares is the ask that was answered.
"""

from __future__ import annotations

import copy
from statistics import median

from octomod.gates import GateResult

# Where the dropped arrays still live, named so a reader can go and get them.
FULL_RECORD = "evaluation_core"  # the round's key in the run record

# GateResult.summary() clips a detail at 300 chars and points at gates/<id>, but
# this gate writes beside the prompt (`agent_calls/<role>/prompt_budget`), so it
# keeps under the clip.
SUMMARY_CLIP = 300


def prompt_cap(spec) -> int | None:
    """The declared per-call prompt cap in bytes, or None for no cap.

    With `agents.max_prompt_bytes: null`, `fit_to_budget` degrades nothing and
    `prompt_budget` passes and records the size; the model's context window,
    which the CLI enforces, is then the only limit.
    """
    raw = spec.get("agents.max_prompt_bytes")
    return None if raw is None else int(raw)


def sig(value, digits: int = 6):
    """Round to `digits` significant digits; non-numbers pass through.

    `round(x, 6)` would flatten a 1e-9 band width to 0.0.
    """
    try:
        x = float(value)
    except (TypeError, ValueError):
        return value
    return float(f"{x:.{digits}g}")


def band_summary(band: dict) -> dict:
    """One prediction band as the few numbers a reader would take from it.

    `width95_max_over_best_range` divides by the range of this band's best
    trajectory, unlike `holdout.groups[].band_rel_width`, which divides by the
    range of the measurements (the one `gates.tight_prediction_rel_width` judges).
    """
    t = list(band.get("time") or [])
    lo = list(band.get("lo95") or [])
    hi = list(band.get("hi95") or [])
    best = list(band.get("best") or [])
    if not t or len(lo) != len(t) or len(hi) != len(t):
        return {
            "n_points": len(t),
            "summary_unavailable": "band arrays absent or of unequal length",
        }
    width = [float(h) - float(low) for h, low in zip(hi, lo, strict=True)]
    worst = max(range(len(width)), key=width.__getitem__)
    best_range = (max(best) - min(best)) if best else 0.0
    out = {
        "n_points": len(t),
        "t_range": [sig(t[0]), sig(t[-1])],
        "best_range": sig(best_range),
        "width95_median": sig(median(width)),
        "width95_max": sig(width[worst]),
        "width95_max_at_t": sig(t[worst]),
    }
    if best_range > 0:
        out["width95_max_over_best_range"] = sig(width[worst] / best_range)
    return out


BANDS_NOTE = (
    "the per-timepoint band arrays (time/best/lo95/lo90/hi95/hi90) are in "
    f"{FULL_RECORD}; summarised here. width95 is hi95 - lo95 in the "
    "observable's own units; width95_max_over_best_range divides it by the "
    "range of THIS band's best trajectory, which is a different denominator "
    "from holdout.groups[].band_rel_width (that one divides by the range of "
    "the measurements)."
)

PROFILES_NOTE = (
    f"per-parameter profile `path` arrays dropped from this view; they are in "
    f"{FULL_RECORD}. What remains is the whole reading of a profile: the "
    f"interval, whether it closed, its width in decades, and the fraction of "
    f"the bounds box it takes."
)


def core_for_agents(core: dict) -> dict:
    """`report_core` with the sampled curves replaced by their summaries.

    Intervals, widths, box fractions, band shapes and the (already compact) ΔAIC
    attribution survive; `for_agents` then rounds numbers and columnises blocks.
    """
    if not isinstance(core, dict):
        return core
    out = dict(core)

    profiles = core.get("profiles")
    if isinstance(profiles, dict):
        trimmed = {}
        dropped = 0
        for pid, rec in profiles.items():
            if isinstance(rec, dict) and "path" in rec:
                trimmed[pid] = {k: v for k, v in rec.items() if k != "path"}
                dropped += 1
            else:
                trimmed[pid] = rec
        if dropped:
            meta = dict(trimmed.get("_meta") or {})
            meta["paths_dropped"] = PROFILES_NOTE
            trimmed["_meta"] = meta
        out["profiles"] = trimmed

    pu = core.get("prediction_uncertainty")
    if isinstance(pu, dict) and isinstance(pu.get("bands"), dict):
        summarised = {k: v for k, v in pu.items() if k != "bands"}
        summarised["bands_summary"] = {
            label: band_summary(b) if isinstance(b, dict) else b
            for label, b in pu["bands"].items()
        }
        summarised["bands_note"] = BANDS_NOTE
        out["prediction_uncertainty"] = summarised

    # The FIM diagonal and a profile projection's per-parameter rows exist to
    # price the profiles; the spectrum and the projection's totals are what an
    # agent reads.
    ident = core.get("identifiability")
    if isinstance(ident, dict) and "diagonal_scaled" in ident:
        out["identifiability"] = {
            k: v for k, v in ident.items() if k != "diagonal_scaled"
        }
    proj = core.get("profiles_projection")
    if isinstance(proj, dict) and "parameters" in proj:
        out["profiles_projection"] = {
            k: v for k, v in proj.items() if k != "parameters"
        }
    req = core.get("profiles_on_request")
    if isinstance(req, dict) and "parameters" in (req.get("projection") or {}):
        out["profiles_on_request"] = {
            **req,
            "projection": {
                k: v for k, v in req["projection"].items() if k != "parameters"
            },
        }

    # applied here rather than at each producer, so `evaluation_core` in the
    # record keeps full precision
    return for_agents(out)


# Rounding applies to agent views only; every artifact in the record keeps full
# precision. The functions below build new containers and never mutate input.
DEFAULT_SIGFIGS = 4
# Above this magnitude, fixed decimals instead of significant figures.
LARGE_MAGNITUDE = 100.0
LARGE_DECIMALS = 4

# Named exceptions, by what the field IS rather than by which block it sits in,
# so a new block inherits the right rule without being listed anywhere.
TIME_DECIMALS = 3  # a timepoint is a coordinate, not a measurement
NOISE_UNIT_DECIMALS = 2  # a residual in units of sigma; the third digit is noise
TIME_FIELDS = frozenset({"t", "time", "at_time", "t_range", "times"})
NOISE_UNIT_FIELDS = frozenset(
    {
        "residual_in_noise_units",
        "in_noise_units",
        "resid_sigma",
        "worst_shift_in_sigma",
        "rmse_over_replicate_noise_floor",
        "best_rmse_over_noise_floor",
    }
)

# Per-point blocks that become column arrays. `columnise` refuses anything but
# a list of flat all-numeric records, so a block that grows a string field
# keeps its record form.
COLUMN_BLOCKS = frozenset({"fit_over_time", "points", "series", "path"})

COLUMNS_NOTE = (
    "COLUMNS: where a per-point block appears as arrays (t, measured, "
    "simulated, …) instead of a list of records, those arrays are POSITIONALLY "
    "ALIGNED — index i of each is the same measurement. Same content, each "
    "field named once per series instead of once per point."
)


def round_for_agents(value, field: str = ""):
    """One number, at the precision the data actually has.

    Non-numbers pass through untouched, including bools — `True` is an answer,
    not a quantity, and `round(True)` is 1. Ints keep their exact value: a
    count of 16 measurements is not a measurement.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    if isinstance(value, int):
        return value
    x = float(value)
    if x != x or x in (float("inf"), float("-inf")):  # NaN/inf survive as-is
        return x
    name = str(field)
    if name in TIME_FIELDS:
        return round(x, TIME_DECIMALS)
    if name in NOISE_UNIT_FIELDS:
        return round(x, NOISE_UNIT_DECIMALS)
    # Large numbers whose content is a difference get fixed decimals: -451.4639623
    # at 4 s.f. is -451.5, coarser than the ΔAIC ≤ 2 band they are compared
    # against. A magnitude rule, so nllh/aic/bic need not be enumerated.
    if abs(x) >= LARGE_MAGNITUDE:
        return round(x, LARGE_DECIMALS)
    return float(f"{x:.{DEFAULT_SIGFIGS}g}")


def columnise(rows: list) -> object:
    """A list of flat, all-numeric records as one record of column arrays.

    Returns `rows` unchanged unless every element is a dict with the same keys
    in the same order and every value is a number or None. No per-block note:
    `for_agents` states the convention once per payload.
    """
    if not isinstance(rows, list) or len(rows) < 2:
        return rows
    if not all(isinstance(r, dict) and r for r in rows):
        return rows
    keys = list(rows[0])
    if any(list(r) != keys for r in rows[1:]):
        return rows
    for r in rows:
        for v in r.values():
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, (int, float))
            ):
                return rows
    return {key: [round_for_agents(r[key], key) for r in rows] for key in keys}


def compact_numeric(obj, field: str = "", columnised: list | None = None):
    """A payload with its numbers rounded and its per-point blocks as column arrays.

    Rounding applies everywhere, with named exceptions; columnising only to the
    `COLUMN_BLOCKS` that pass `columnise`'s shape test. `columnised` collects
    the name of each reshaped block.
    """
    if isinstance(obj, dict):
        return {k: compact_numeric(v, k, columnised) for k, v in obj.items()}
    if isinstance(obj, list):
        if field in COLUMN_BLOCKS:
            packed = columnise(obj)
            if isinstance(packed, dict):
                if columnised is not None:
                    columnised.append(field)
                return packed
        return [compact_numeric(v, field, columnised) for v in obj]
    return round_for_agents(obj, field)


def for_agents(payload: dict) -> dict:
    """`compact_numeric`, plus one statement of the column convention.

    The statement is appended to `how_to_read_this` when the payload has one,
    else set as `_columns`, and only when a block was actually reshaped.
    """
    reshaped: list[str] = []
    out = compact_numeric(payload, "", reshaped)
    if not reshaped or not isinstance(out, dict):
        return out
    guide = out.get("how_to_read_this")
    if isinstance(guide, str):
        out["how_to_read_this"] = guide.rstrip() + " " + COLUMNS_NOTE
    else:
        out["_columns"] = COLUMNS_NOTE
    return out


# The degrade order, and the floor each step may halve down to. Every step
# leaves a notice in the payload naming what is missing and how to ask for it
# back. Floor 0 marks a one-shot step (collapse to totals once); a halving step
# starts at half of what the payload carries and halves until the prompt fits
# or the floor is reached. Floors: 4 observables of residuals (one with nothing
# kept cannot be reasoned about), 3 terms per rival (one term does not read as
# a pattern), 6 candidates (the winner, its indistinguishable set and the next
# best by AIC are what an interpretation argues from).
#
# TODO: declare this under `agents.payload_budget` so the order and the floors
# are hashed into `workflow_sha`. A new yaml key moves `workflow_sha`, and a
# paused run whose spec sha moved is refused on resume.
PAYLOAD_BUDGET = (
    # first: the per-series residual-form rows, which the summary sentences
    # beside them already state
    ("residual_form_rows", 0),
    # then packaging (the same prose once per condition), and drift reads as
    # one verdict per declaration
    ("declared_constants", 0),
    ("prediction_bands", 0),
    ("residual_series", 4),
    ("attribution_rivals", 3),
    ("discrimination_tables", 0),
    # after the steps above, so a payload they bring under the cap is unaffected
    ("rival_residuals", 0),
    # whole per-candidate detail below the top-K by AIC (the winner and its
    # indistinguishable set are kept)
    ("candidate_detail", 6),
    # last: the residual-form sentences, the shortest statement of what is
    # still wrong; halved from the end (the base's), the selected model's
    # strongest residuals kept
    ("residual_form_summary", 4),
)

# Every notice a degrade step leaves carries this mark, so an agent reading the
# prompt can find every gap in it by searching one string.
TRIM_MARK = "TRIMMED TO FIT THE PROMPT BUDGET"

# The diagnostic request that fetches one series back (`diagnostics.KINDS`),
# named in the notices.
CURVE_REQUEST = "residual_curve(candidate_id, observable_id, condition_id)"
# The request that fits one residual series' form, calibrated against noise.
FORM_REQUEST = "fit_residual_form(candidate_id, observable_id, condition_id)"

# Where the attribution table lives when the block does not name it itself.
ATTRIBUTION_RECORD = "attribution"


def _blocks_with(node: object, key: str) -> list[dict]:
    """Every dict inside `node` that carries `key`, outermost first.

    The degrade steps find blocks by field name rather than by path, so they
    keep working however the context nests them.
    """
    out: list[dict] = []
    queue: list[object] = [node]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            if key in cur:
                out.append(cur)
            queue.extend(cur.values())
        elif isinstance(cur, list):
            queue.extend(cur)
    return out


def _numbers(values) -> list[float]:
    return [
        float(v)
        for v in values
        if not isinstance(v, bool) and isinstance(v, (int, float))
    ]


def _observable_of(label: object) -> str:
    """The observable half of an `observable@condition` series label."""
    text = str(label)
    head = text.rpartition("@")[0]
    return head or text


def _trim_declared_constants(payload: dict, floor: int, fits) -> str:
    """Collapse per-(declaration, condition) drift rows to one row per declaration.

    Each row keeps the condition count, how many were within tolerance, and the
    worst drift and where; the `why`/`locator` prose stays in the full record,
    except the locator of a declaration that drifted. One-shot (floor 0). Only
    a table with the summary key `declared` beside `rows` is touched.
    """
    blocks = [
        b
        for b in _blocks_with(payload, "rows")
        if "declared" in b
        and isinstance(b.get("rows"), list)
        and b["rows"]
        and all(
            isinstance(r, dict) and "expression" in r and "drift" in r
            for r in b["rows"]
        )
    ]
    if not blocks:
        return ""
    n_rows = 0
    n_decl = 0
    for block in blocks:
        rows = block.pop("rows")
        by_expr: dict[str, list] = {}
        for r in rows:
            by_expr.setdefault(str(r.get("expression")), []).append(r)
        out = []
        for expr in sorted(by_expr):
            rs = by_expr[expr]
            drifted = [r for r in rs if isinstance(r.get("drift"), (int, float))]
            worst = (
                max(drifted, key=lambda r: abs(float(r["drift"]))) if drifted else rs[0]
            )
            n_ok = sum(1 for r in rs if r.get("within_tolerance") is True)
            rec: dict = {
                "expression": expr,
                "tolerance": rs[0].get("tolerance"),
                "n_conditions": len(rs),
                "n_within_tolerance": n_ok,
                "worst_drift": (
                    round_for_agents(float(worst["drift"]))
                    if isinstance(worst.get("drift"), (int, float))
                    else worst.get("drift")
                ),
                "worst_in": worst.get("condition"),
            }
            if n_ok < len(rs) and worst.get("locator"):
                rec["locator"] = worst.get("locator")
            out.append(rec)
        block["rows_by_declaration"] = out
        block["constants_trimmed"] = (
            f"{TRIM_MARK}: {len(rows)} per-(declaration, condition) drift rows "
            f"collapsed to one row per declaration ({len(out)}); the per-condition "
            f"rows with their `why` and `locator` are in {FULL_RECORD} under "
            f"declared_constants.rows."
        )
        n_rows += len(rows)
        n_decl += len(out)
    return (
        f"declared constants: {n_rows} per-condition drift rows collapsed to "
        f"{n_decl} per-declaration rows"
    )


def _trim_prediction_bands(payload: dict, floor: int, fits) -> str:
    """Collapse the per-band summaries to per-observable width totals (one-shot)."""
    blocks = [
        b
        for b in _blocks_with(payload, "bands_summary")
        if isinstance(b.get("bands_summary"), dict) and b["bands_summary"]
    ]
    if not blocks:
        return ""
    n_bands = 0
    observables: set[str] = set()
    for block in blocks:
        bands = block.pop("bands_summary")
        by_obs: dict[str, list] = {}
        for label, summary in bands.items():
            by_obs.setdefault(_observable_of(label), []).append((str(label), summary))
        totals = {}
        for obs in sorted(by_obs):
            rows = [(lab, s) for lab, s in by_obs[obs] if isinstance(s, dict)]
            medians = _numbers(s.get("width95_median") for _, s in rows)
            maxima = [
                (v, lab) for (lab, s) in rows for v in _numbers([s.get("width95_max")])
            ]
            rec: dict = {"n_bands": len(by_obs[obs])}
            if medians:
                rec["width95_median"] = round_for_agents(median(medians))
            if maxima:
                worst_v, worst_lab = max(maxima)
                rec["width95_max"] = round_for_agents(worst_v)
                # name the widest band only when the observable has several
                if len(rows) > 1:
                    rec["width95_max_in"] = worst_lab
                ratio = dict(rows)[worst_lab].get("width95_max_over_best_range")
                for v in _numbers([ratio]):
                    rec["width95_max_over_best_range"] = round_for_agents(v)
            totals[obs] = rec
        block["bands_summary_by_observable"] = totals
        block["bands_trimmed"] = (
            f"{TRIM_MARK}: the per-band summaries for {len(bands)} (observable, "
            f"condition) pairs are collapsed to the per-observable width totals "
            f"above. The per-band summaries and the full band arrays are in "
            f"{FULL_RECORD}; ask for one pair's fit by name with {CURVE_REQUEST}."
        )
        n_bands += len(bands)
        observables |= set(by_obs)
    return (
        f"prediction bands: {n_bands} per-band summaries over "
        f"{len(observables)} observable(s) collapsed to per-observable width totals"
    )


def _residual_details(payload: dict) -> tuple[list[dict], list[dict]]:
    """(the blocks that hold candidates, each candidate's own record)."""
    blocks = [
        b
        for b in _blocks_with(payload, "per_candidate_residuals")
        if isinstance(b.get("per_candidate_residuals"), dict)
    ]
    dets = [
        det
        for b in blocks
        for det in b["per_candidate_residuals"].values()
        if isinstance(det, dict) and isinstance(det.get("per_series"), dict)
    ]
    return blocks, dets


def _keep_observables(dets: list[dict], keep: set[str], key_used: str) -> None:
    """Series outside `keep` become their rank statistic, beside the ones an
    earlier thinning already reduced the same way."""
    from octomod.workflow_modules.evaluation.residuals import rank_of

    for det in dets:
        series = det["per_series"]
        other = det.setdefault("other_series_" + key_used, {})
        for label in list(series):
            if _observable_of(label) in keep:
                continue
            other[label] = round_for_agents(rank_of(series[label])[0])
            series.pop(label)
        n_curves = sum(
            1 for s in series.values() if isinstance(s, dict) and "fit_over_time" in s
        )
        if n_curves:
            det["curves_note"] = (
                f"point-by-point curves for {n_curves} series, the worst by "
                f"{key_used} within each observable. Request {CURVE_REQUEST} "
                f"for any other."
            )
        else:
            det.pop("curves_note", None)
        det["note"] = (
            f"{len(series)} series carry a full summary; {len(other)} carry "
            f"their {key_used} only — enough to see they exist and how bad "
            f"they are. Request {CURVE_REQUEST} for any of them."
        )


def _trim_residual_series(payload: dict, floor: int, fits) -> str:
    """Keep full residual summaries for the top-N misfit observables, halving N.

    The rest carry their rank statistic. The ranking is computed once across
    every candidate, so the same observables survive in each.
    """
    from octomod.workflow_modules.evaluation.residuals import rank_of

    blocks, dets = _residual_details(payload)
    if not dets:
        return ""
    worst: dict[str, float] = {}
    key_used = "none"
    for det in dets:
        for label, summary in det["per_series"].items():
            value, key = rank_of(summary)
            if key != "none":
                key_used = key
            obs = _observable_of(label)
            worst[obs] = max(worst.get(obs, 0.0), value)
    if not worst or key_used == "none":
        # no rank statistic anywhere: dropping series in an order nobody can
        # state would be truncation, so the step does nothing
        return ""
    order = sorted(worst, key=lambda o: (-worst[o], o))
    n_before = len(order)
    kept = n_before
    while kept > max(floor, 1):
        kept = max(floor, 1, kept // 2)
        _keep_observables(dets, set(order[:kept]), key_used)
        if fits():
            break
    if kept == n_before:  # already at or below the floor: nothing was removed
        return ""
    notice = (
        f"{TRIM_MARK}: full residual summaries for {kept} of {n_before} "
        f"observables, the worst by {key_used}; every other series carries its "
        f"{key_used} under other_series_{key_used}. Ask for any of them by name "
        f"with {CURVE_REQUEST}."
    )
    for block in blocks:
        block["residuals_trimmed"] = notice
    return (
        f"residual series: full summaries kept for the worst {kept} of "
        f"{n_before} observables by {key_used}, across {len(dets)} candidate(s)"
    )


def _top_terms(rows: list, field: str, k: int) -> list:
    """The k largest rows by |field|, ties broken by their own text so the
    same payload always degrades to the same table."""

    def size(row) -> tuple:
        value = row.get(field) if isinstance(row, dict) else None
        magnitude = abs(value) if isinstance(value, (int, float)) else 0.0
        return (-magnitude, str(row.get("group", "") if isinstance(row, dict) else row))

    return sorted(rows, key=size)[:k]


def _trim_attribution_rivals(payload: dict, floor: int, fits) -> str:
    """Each rival's per-(observable, condition) ΔAIC table keeps its top-K
    terms by |Δnllh|. K halves until the prompt fits."""
    blocks = [
        b
        for b in _blocks_with(payload, "rivals")
        if isinstance(b.get("rivals"), list) and b["rivals"]
    ]
    tables = [
        (block, rival)
        for block in blocks
        for rival in block["rivals"]
        if isinstance(rival, dict) and isinstance(rival.get("contributions"), list)
    ]
    if not tables:
        return ""
    n_before = max(len(rival["contributions"]) for _, rival in tables)
    kept = n_before
    while kept > max(floor, 1):
        kept = max(floor, 1, kept // 2)
        for block, rival in tables:
            record = str(block.get("full_record") or ATTRIBUTION_RECORD)
            total = int(rival.get("contributions_total") or len(rival["contributions"]))
            rival["contributions_total"] = total
            rival["contributions"] = _top_terms(
                rival["contributions"], "delta_nllh", kept
            )
            rival["contributions_trimmed"] = (
                f"{len(rival['contributions'])} of {total} terms, the largest "
                f"by |delta_nllh|; the whole table is in {record}."
            )
        if fits():
            break
    if kept == n_before:  # already at or below the floor: nothing was removed
        return ""
    for block in blocks:
        record = str(block.get("full_record") or ATTRIBUTION_RECORD)
        block["rivals_trimmed"] = (
            f"{TRIM_MARK}: every rival's attribution table keeps its {kept} "
            f"largest (observable, condition) terms by |delta_nllh| of "
            f"{n_before}; the whole table is in {record}, and the fit behind "
            f"any term is {CURVE_REQUEST}."
        )
    return (
        f"attribution rivals: top {kept} of {n_before} terms per rival by "
        f"|delta_nllh|, across {len(tables)} rival(s)"
    )


# A per-candidate table shorter than this is already the reading, not the
# packaging: collapsing it would cost a notice and save nothing.
TABLE_COLLAPSE_MIN = 4


def _per_observable_totals(name: str, rows: dict) -> dict:
    """One per-observable table as its totals: how many observables it covers,
    each numeric column summed, each categorical column counted."""
    counts: dict[str, dict[str, int]] = {}
    sums: dict[str, float] = {}
    for value in rows.values():
        columns = value.items() if isinstance(value, dict) else [(name, value)]
        for column, cell in columns:
            if not isinstance(cell, bool) and isinstance(cell, (int, float)):
                sums[column] = sums.get(column, 0.0) + float(cell)
            else:
                counts.setdefault(column, {})
                counts[column][str(cell)] = counts[column].get(str(cell), 0) + 1
    out: dict = {"n_observables": len(rows)}
    for column in sorted(counts):
        out[f"{column}_counts"] = dict(sorted(counts[column].items()))
    for column in sorted(sums):
        total = sums[column]
        # a count stays a count: `round_for_agents` is a precision rule for
        # quantities
        out[f"{column}_total"] = (
            int(total) if float(total).is_integer() else round_for_agents(total)
        )
    return out


def _trim_discrimination_tables(payload: dict, floor: int, fits) -> str:
    """The per-candidate tables under `discrimination` become per-observable
    totals. The selection table itself is never touched: it is the answer the
    round exists to produce."""
    discriminations = [
        b["discrimination"]
        for b in _blocks_with(payload, "discrimination")
        if isinstance(b.get("discrimination"), dict)
    ]
    tables = [
        t
        for disc in discriminations
        for t in _blocks_with(disc, "per_candidate")
        if isinstance(t.get("per_candidate"), dict)
    ]
    if not tables:
        return ""
    collapsed = 0
    candidates = 0
    for table in tables:
        here = 0
        for record in table["per_candidate"].values():
            if not isinstance(record, dict):
                continue
            candidates += 1
            for name in list(record):
                rows = record[name]
                if isinstance(rows, dict) and len(rows) >= TABLE_COLLAPSE_MIN:
                    record[name] = _per_observable_totals(name, rows)
                    here += 1
        collapsed += here
        if here:
            table["tables_trimmed"] = (
                f"{TRIM_MARK}: each candidate's per-observable table above is "
                f"collapsed to its totals. The selection table "
                f"(discrimination.candidates) is untouched, and the full "
                f"per-observable tables are in {FULL_RECORD}."
            )
    if not collapsed:
        return ""
    return (
        f"discrimination tables: {collapsed} per-observable table(s) over "
        f"{candidates} candidate(s) collapsed to per-observable totals; the "
        f"selection table is untouched"
    )


def _residual_focus(payload: dict, block: dict) -> str | None:
    """The selected model a residual block is about: the block's own
    `observation_evidence.for_model`, else the payload's declared winner."""
    focus = (block.get("observation_evidence") or {}).get("for_model")
    if isinstance(focus, str) and focus:
        return focus
    for b in _blocks_with(payload, "winner"):
        if isinstance(b.get("winner"), str) and b["winner"]:
            return b["winner"]
    return None


def _trim_rival_residuals(payload: dict, floor: int, fits) -> str:
    """Reduce each rival (not the selected model or base) to one number per series.

    That number is the series' rank statistic. The selected model shows what is
    still wrong, the base what the space started from, and
    `cross_model_by_measurement` still compares every candidate; the rivals'
    shape descriptors grow with the lattice, not the problem. One-shot (floor
    0); does nothing when the payload does not say which model is selected.
    """
    from octomod.workflow_modules.evaluation.residuals import base_id_of, rank_of

    n_cands = 0
    n_series = 0
    keys: set[str] = set()
    for block in _blocks_with(payload, "per_candidate_residuals"):
        dets = block.get("per_candidate_residuals")
        if not isinstance(dets, dict):
            continue
        focus = _residual_focus(payload, block)
        with_series = [
            c
            for c, d in dets.items()
            if isinstance(d, dict) and isinstance(d.get("per_series"), dict)
        ]
        if focus not in with_series:
            continue
        base = base_id_of(with_series)
        here = 0
        for cid in with_series:
            if cid in (focus, base):
                continue
            det = dets[cid]
            ranked = {label: rank_of(s) for label, s in det["per_series"].items()}
            if any(key == "none" for _v, key in ranked.values()):
                continue  # a series with no rank statistic cannot become one
            series = det.pop("per_series")
            for label, (value, key) in ranked.items():
                det.setdefault("other_series_" + key, {})[label] = round_for_agents(
                    value
                )
                keys.add(key)
            det.pop("curves_note", None)
            det["note"] = (
                f"shape descriptors omitted for this candidate: its {len(series)} "
                f"summarised series carry their rank statistic only, beside the "
                f"ones already reduced. Request {CURVE_REQUEST} for any of them."
            )
            here += 1
            n_series += len(series)
        if here:
            block["rival_residuals_trimmed"] = (
                f"{TRIM_MARK}: the residual summaries of {here} candidate(s) other "
                f"than the selected model ({focus}) and the base ({base}) are "
                f"collapsed to one number per series, under other_series_<key>; "
                f"cross_model_by_measurement still compares every candidate series "
                f"by series. Ask for any series by name with {CURVE_REQUEST}."
            )
            n_cands += here
    if not n_cands:
        return ""
    return (
        f"rival residuals: {n_cands} candidate(s) other than the selected model "
        f"and the base collapsed to their {'/'.join(sorted(keys))} per series "
        f"({n_series} series)"
    )


def _candidate_ranking(payload: dict) -> tuple[list[str], set[str]]:
    """(candidate ids best-first by AIC, ids that always keep their detail).

    The kept ids are the winner and its indistinguishable set. Both are empty
    when the payload has no selection table.
    """

    def _is_table(v) -> bool:
        return (
            isinstance(v, list)
            and len(v) >= 2
            and all(
                isinstance(c, dict) and "id" in c and ("aic" in c or "value" in c)
                for c in v
            )
        )

    def _crit(c):
        v = c.get("aic", c.get("value"))
        return float(v) if isinstance(v, (int, float)) else float("inf")

    # the interpreter's context: a selection block with candidates + winner +
    # indistinguishable set
    for block in _blocks_with(payload, "candidates"):
        cands = block.get("candidates")
        if not _is_table(cands):
            continue
        ranked = [str(c["id"]) for c in sorted(cands, key=_crit)]
        keep = {str(block.get("winner") or "")} - {""}
        keep |= {str(x) for x in (block.get("indistinguishable") or []) if x}
        return ranked, keep
    # the expansion agent's context: a bare `selection_table` list and a
    # `selected_model` string; the indistinguishable set is every row within
    # 2 AIC units of the best (the criterion's own threshold)
    for v in payload.values() if isinstance(payload, dict) else []:
        if _is_table(v):
            ranked = [str(c["id"]) for c in sorted(v, key=_crit)]
            best = _crit(sorted(v, key=_crit)[0])
            keep = {str(c["id"]) for c in v if _crit(c) - best <= 2.0}
            for wkey in ("selected_model", "winner"):
                w = payload.get(wkey)
                if isinstance(w, str) and w:
                    keep.add(w)
            return ranked, keep
    return [], set()


def _trim_candidate_detail(payload: dict, floor: int, fits) -> str:
    """Keep per-candidate detail only for the winner, its set and the top-K by AIC.

    Parameter tables, residual records and rival decompositions of the rest are
    dropped and the dropped ids named; K halves until the prompt fits. The
    selection table is never touched: every candidate keeps its row there.
    """
    ranked, always = _candidate_ranking(payload)
    if len(ranked) < 2:
        return ""
    ids = set(ranked)
    res_blocks = [
        b
        for b in _blocks_with(payload, "per_candidate_residuals")
        if isinstance(b.get("per_candidate_residuals"), dict)
    ]
    par_blocks = [
        b
        for b in _blocks_with(payload, "parameters")
        if isinstance(b.get("parameters"), dict)
        and len(ids & set(map(str, b["parameters"]))) >= 2
    ]
    riv_blocks = [
        b
        for b in _blocks_with(payload, "rivals")
        if isinstance(b.get("rivals"), list)
        and any(isinstance(r, dict) and "rival" in r for r in b["rivals"])
    ]
    if not (res_blocks or par_blocks or riv_blocks):
        return ""
    n_before = len(ranked)
    kept = n_before
    dropped: list[str] = []
    while kept > max(floor, 1):
        kept = max(floor, 1, kept // 2)
        keep_ids = always | set(ranked[:kept])
        dropped = [c for c in ranked if c not in keep_ids]
        note = (
            f"{TRIM_MARK}: per-candidate detail kept for {len(keep_ids)} of {n_before} "
            f"candidates (the winner, its indistinguishable set and the best {kept} by AIC); "
            f"dropped {dropped}; every candidate keeps its row in discrimination.candidates"
        )
        for b in res_blocks:
            b["per_candidate_residuals"] = {
                k: v
                for k, v in b["per_candidate_residuals"].items()
                if str(k) in keep_ids
            }
            b["per_candidate_residuals_trimmed"] = (
                note + f"; the full records are in {FULL_RECORD} and by "
                f"{CURVE_REQUEST}."
            )
        for b in par_blocks:
            b["parameters"] = {
                k: v for k, v in b["parameters"].items() if str(k) in keep_ids
            }
            b["parameters_trimmed"] = note + f"; the full tables are in {FULL_RECORD}."
        for b in riv_blocks:
            record = str(b.get("full_record") or ATTRIBUTION_RECORD)
            b["rivals"] = [
                r
                for r in b["rivals"]
                if not (isinstance(r, dict) and "rival" in r)
                or str(r["rival"]) in keep_ids
            ]
            b["rivals_by_candidate_trimmed"] = (
                note + f"; every rival's decomposition is in {record}."
            )
        if fits():
            break
    if kept == n_before:
        return ""
    return (
        f"candidate detail: parameter tables, residual records and rival decompositions "
        f"kept for the winner, its indistinguishable set and the best {kept} of {n_before} "
        f"candidates by AIC; {len(dropped)} candidate(s) named and dropped from the detail blocks"
    )


def _form_blocks(payload: dict, field: str) -> list[dict]:
    """Every `residual_forms` block whose `field` holds a non-empty list."""
    return [
        b["residual_forms"]
        for b in _blocks_with(payload, "residual_forms")
        if isinstance(b.get("residual_forms"), dict)
        and isinstance(b["residual_forms"].get(field), list)
        and b["residual_forms"][field]
    ]


def _trim_residual_form_rows(payload: dict, floor: int, fits) -> str:
    """Drop the per-series residual-form rows; the summary sentences stay.

    One shot: the sentences are built from these rows, so what is removed is
    the per-series detail, and the request that fits any one series is named.
    """
    blocks = _form_blocks(payload, "per_series")
    if not blocks:
        return ""
    n = 0
    for block in blocks:
        rows = block.pop("per_series")
        n += len(rows)
        block["per_series_trimmed"] = (
            f"{TRIM_MARK}: {len(rows)} per-series form rows removed; `summary` "
            f"states them grouped. Request {FORM_REQUEST} for any one series, "
            f"calibrated against autocorrelated noise."
        )
    return f"residual forms: {n} per-series row(s) removed, the summary sentences kept"


def _trim_residual_form_summary(payload: dict, floor: int, fits) -> str:
    """Halve the residual-form sentences down to `floor`, keeping the head:
    the selected model's strongest residuals come first."""
    blocks = [b for b in _form_blocks(payload, "summary") if len(b["summary"]) > floor]
    if not blocks:
        return ""
    before = {id(b): len(b["summary"]) for b in blocks}
    while any(len(b["summary"]) > max(floor, 1) for b in blocks):
        for b in blocks:
            b["summary"] = b["summary"][: max(floor, 1, len(b["summary"]) // 2)]
        if fits():
            break
    kept = sum(len(b["summary"]) for b in blocks)
    total = sum(before.values())
    for b in blocks:
        b["summary_trimmed"] = (
            f"{TRIM_MARK}: {len(b['summary'])} of {before[id(b)]} residual-form "
            f"sentences kept, the selected model's strongest first. Request "
            f"{FORM_REQUEST} for any series."
        )
    return f"residual forms: {kept} of {total} summary sentence(s) kept"


_STEPS = {
    "residual_form_rows": _trim_residual_form_rows,
    "residual_form_summary": _trim_residual_form_summary,
    "declared_constants": _trim_declared_constants,
    "prediction_bands": _trim_prediction_bands,
    "residual_series": _trim_residual_series,
    "attribution_rivals": _trim_attribution_rivals,
    "discrimination_tables": _trim_discrimination_tables,
    "rival_residuals": _trim_rival_residuals,
    "candidate_detail": _trim_candidate_detail,
}


def fit_to_budget(context: dict, spec, render) -> tuple[str, dict, list]:
    """Render `context`, degrading it in `PAYLOAD_BUDGET` order until within the cap.

    Returns `(prompt, context, trims)`. A payload already under the cap comes
    back with the caller's own context object and no trims, so its prompt is
    byte-identical to one built without this function. Each trim is `{step,
    what, bytes_before, bytes_after}`, for the caller to ledger as
    `payload_trimmed` (read back on the round's `decisions_md`). The cap is
    measured on the rendered prompt (skill text and contract included); the
    caller's context is never mutated.
    """
    cap = prompt_cap(spec)
    prompt = render(context)
    state = {"prompt": prompt, "bytes": len(prompt.encode())}
    if cap is None or state["bytes"] <= cap:
        return prompt, context, []

    working = copy.deepcopy(context)

    def fits() -> bool:
        state["prompt"] = render(working)
        state["bytes"] = len(state["prompt"].encode())
        return state["bytes"] <= cap

    trims: list[dict] = []
    for name, floor in PAYLOAD_BUDGET:
        if state["bytes"] <= cap:
            break
        before = state["bytes"]
        what = _STEPS[name](working, floor, fits)
        fits()
        if not what:
            # the block is absent or already at its floor: nothing removed
            continue
        trims.append(
            {
                "step": name,
                "what": what,
                "bytes_before": before,
                "bytes_after": state["bytes"],
            }
        )
    return state["prompt"], working, trims


def prompt_budget(role: str, prompt: str, spec, context: dict | None = None):
    """T0: the prompt about to be sent is within the declared byte cap.

    Blocking; runs after `fit_to_budget`, so a failure is a payload the whole
    degrade order could not bring under the cap. Nothing is truncated: the
    operator trims the payload or raises the cap and resumes. With no cap it
    passes and records the size.
    """
    cap = prompt_cap(spec)
    n = len(prompt.encode())
    if cap is None:
        # no cap declared: the gate still runs so the size is ledgered per call
        return GateResult(
            "agent_prompt_bytes",
            "T0",
            passed=True,
            blocking=True,
            value=n,
            threshold=None,
            detail=f"{role} prompt is {n:,} bytes (no cap declared)",
        )
    if n <= cap:
        detail = f"{role} prompt is {n:,} bytes ({n / cap:.0%} of the cap)"
    else:
        detail = (
            f"{role} prompt is {n:,} bytes vs cap {cap:,} ({n / cap:.1f}x) "
            f"after the declared degrade order; raise agents.max_prompt_bytes "
            f"or trim it; the prompt and this verdict are in agent_calls/{role}. "
            f"Biggest: {largest_inputs(context)}"
        )
        # the actionable half comes first, so clipping under SUMMARY_CLIP can
        # only cut the breakdown (kept in full in the JSON beside the prompt)
        if len(detail) >= SUMMARY_CLIP:
            detail = detail[: SUMMARY_CLIP - 4] + " ..."
    # gate_id and tier stay positional: tools/module_map.py reads gate ids off
    # the first positional argument of every GateResult call
    return GateResult(
        "agent_prompt_bytes",
        "T0",
        passed=n <= cap,
        blocking=True,
        value=n,
        threshold=cap,
        detail=detail,
    )


def largest_inputs(context: dict | None, limit: int = 3) -> str:
    """The `limit` largest context keys by serialised size, as one line.

    Called only when the cap is breached, so the common path never serialises
    twice.
    """
    import json

    if not isinstance(context, dict) or not context:
        return "context unavailable"
    sizes = []
    for key, value in context.items():
        try:
            n = len(
                value.encode()
                if isinstance(value, str)
                else json.dumps(value, indent=2, default=str).encode()
            )
        except (TypeError, ValueError):  # not serialisable: it is not the bytes
            n = 0
        sizes.append((n, key))
    sizes.sort(reverse=True)
    return ", ".join(f"{k[:40]} {n:,}B" for n, k in sizes[:limit])


def cost_gate_line(ledger, spec) -> str:
    """One cost-gate card line: the agent prompt bytes measured so far, and the cap.

    Measured, never projected: the interpreter's call comes after this gate.
    """
    cap = prompt_cap(spec)
    cap_text = "no cap" if cap is None else f"cap {cap:,}/call"
    rows = [
        e
        for e in ledger.entries()
        if e.get("event") == "agent_call" and e.get("prompt_bytes") is not None
    ]
    if not rows:
        return f"agent prompt bytes so far: no agent call yet ({cap_text})"
    total = sum(int(e["prompt_bytes"]) for e in rows)
    worst = max(rows, key=lambda e: int(e["prompt_bytes"]))
    return (
        f"agent prompt bytes so far: {len(rows)} call(s), {total:,} total, "
        f"largest {int(worst['prompt_bytes']):,} ({worst.get('role', '?')}) "
        f"— {cap_text}"
    )
