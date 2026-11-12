"""What the raw curves look like, in the words a modeller says off a plot.

Built from `data_signals.curve_descriptors`: per observable, and per stimulus
when the design has one, which conditions rise, peak, return toward baseline or
plateau, how fast, whether the level ends above its control, and whether the
response is monotone in dose. No measurement value appears — shape words,
timescales rounded to one significant figure, and the design's own condition
labels — and held-out conditions are not described.

This is the one data-derived input construction is shown (`routing.py`): a
modeller reads shape and timescale off a plot before drawing a network, while
values would turn the hypothesis into a fit. Written at S2 to the round's
`data/phenomenology` in the record. S1 runs before S2, so construction receives
it where the round already holds a data table when S1 runs: a revision round
(which carries `data/` forward), a seeded round, or a supplied long table. In
the first round of a fresh run it receives the same sentences read from the raw
data files instead (`raw_phenomenology`, kept at the run-level
`phenomenology_raw`), when those files are unambiguous enough to read
without the extraction agent, and nothing when they are not.
"""

from __future__ import annotations

from octomod.workflow_modules.data import curve_forms as _cf

# the round's `data/phenomenology` record (`rounds/round_k/data/phenomenology`)
KEY = "data/phenomenology"
CARD_LIMIT = 8

HOW_TO_READ = (
    "What the measured curves look like, described without values: the shape "
    "each condition's curve follows (the best of constant, linear, exponential "
    "and rise-and-fall by small-sample AICc), when it is half-way through its "
    "change, when it peaks, returns or plateaus — times in the data's own time "
    "unit, rounded to one significant figure — whether it ends above, at or "
    "below its control condition, and whether the response is monotone in "
    "dose. Held-out conditions are not described. These are observations a "
    "mechanism has to be able to produce, not a curve to copy: argue the "
    "network from biology, and let the fit decide."
)


def node(rnd):
    """Where the round's phenomenology lives: `rnd / "data/phenomenology"`
    (`rnd` = `ctx.round`)."""
    return rnd / KEY


def t1(x) -> str:
    """A time at one significant figure: 7.66 -> '8', 34 -> '30'."""
    return _cf.plain(x, 1)


def _span1(values) -> str:
    return _cf.span_text(values, 1)


def _by(label: str, values) -> str:
    """' (half-maximum by ~5)', or '' when no member has that time."""
    vals = [v for v in values if v is not None]
    return f" ({label} by ~{_span1(vals)})" if vals else ""


def shape_key(row: dict) -> tuple:
    """What two series must share to be described in one phrase: the form, its
    direction, whether it settles, whether a timescale sits on a bound, and for
    a transient whether its extreme lies before, inside or after the window."""
    fit, sh = row["fit"], row["shape"]
    where_peak = None
    if fit["form"] == "rise_and_fall" and fit.get("window") and fit.get("peak_time"):
        lo, hi = fit["window"]
        tp = fit["peak_time"]
        where_peak = "before" if tp < lo else ("after" if tp > hi else "inside")
    return (
        fit["form"],
        fit.get("direction"),
        bool(sh.get("settled_by_end")),
        fit.get("timescale_at_bound"),
        where_peak,
    )


GERUND = {"rises": "rising", "falls": "falling"}


def _shape_words(group: list[dict]) -> str:
    """One group's shape in words, its times spanned over the group."""
    form, direction, settled, bound, where_peak = shape_key(group[0])
    sh = [r["shape"] for r in group]
    if form == "constant":
        return "flat (no time course beyond noise)"
    if form == "linear":
        return (
            "rises steadily through the last sample"
            if direction == "increasing"
            else "falls steadily through the last sample"
        )
    if form == "exponential":
        verb, noun = (
            ("rises", "half-maximum") if direction == "rise" else ("falls", "half-way")
        )
        if bound == "lower":
            return f"{verb} within the first sampling interval, then holds"
        if bound == "upper":
            return f"{verb} slowly, still {GERUND[verb]} at the last sample"
        text = verb + _by(noun, [s["change_half_time"] for s in sh])
        taus = [(r["fit"].get("timescales") or [None])[0] for r in group]
        anchors = [r["fit"].get("anchor") or 0.0 for r in group]
        if settled:
            level = "plateaus" if direction == "rise" else "levels off"
            by = [a + 3.0 * t for a, t in zip(anchors, taus, strict=False) if t]
            return f"{text}, {level} by ~{_span1(by)}"
        return f"{text}, still {GERUND[verb]} at the last sample"
    # rise_and_fall
    peak = direction == "peak"
    if where_peak == "after":
        verb = "rises" if peak else "falls"
        return f"{verb}, still {GERUND[verb]} at the last sample"
    if where_peak == "before":
        return (
            "falls from the first sample (its peak comes earlier)"
            if peak
            else "recovers from the first sample (its dip comes earlier)"
        )
    if peak:
        text = (
            "rises"
            + _by("half-maximum", [s["rise_half_time"] for s in sh])
            + f", peaks near ~{_span1([s['peak_time'] for s in sh])}"
        )
        back = ", returns toward baseline by ~"
        still = ", declining at the last sample"
    else:
        text = f"dips (lowest near ~{_span1([s['peak_time'] for s in sh])})"
        back = ", recovers toward baseline by ~"
        still = ", recovering at the last sample"
    back_at = [s["return_half_time"] for s in sh if s["return_half_time"] is not None]
    if settled and back_at:
        return text + back + _span1(back_at)
    return text + still


def _control_words(group: list[dict]) -> str:
    """', ending above the control level' when every member agrees."""
    buckets = {(r.get("vs_control") or {}).get("bucket") for r in group}
    if len(buckets) != 1 or None in buckets:
        return ""
    return f", ending {buckets.pop()} the control level"


def _dose_words(orders: list[dict], obs: str, attr: str | None, val) -> list[str]:
    """Monotonicity across each numeric attribute, over the groups of this
    stratum that vary only in it."""
    mine = [
        o
        for o in orders
        if o["observable"] == obs
        and (attr is None or str(o["held_fixed"].get(attr)) == str(val))
    ]
    out = []
    for a in sorted({o["attribute"] for o in mine}):
        rows = [o for o in mine if o["attribute"] == a]
        kinds = {o["order"] for o in rows}
        n_levels = max(len(o["levels"]) for o in rows)
        if kinds == {"increasing"}:
            out.append(
                f"monotone in {a} (larger at each higher level)"
                if n_levels >= 3
                else f"larger at the higher {a}"
            )
        elif kinds == {"decreasing"}:
            out.append(
                f"monotone in {a} (smaller at each higher level)"
                if n_levels >= 3
                else f"smaller at the higher {a}"
            )
        elif kinds == {"flat"}:
            out.append(f"about the same at every {a}")
        else:
            out.append(f"not monotone in {a}")
    return out


def _qualitative(row: dict) -> dict:
    """A descriptor row without values: shape words and one-figure times."""
    fit, sh = row["fit"], row["shape"]
    return {
        "observable": row["observable"],
        "condition": row["condition"],
        "form": fit["form"],
        "direction": fit.get("direction"),
        "half_change_by": (
            None if sh.get("change_half_time") is None else t1(sh["change_half_time"])
        ),
        "peak_near": None if sh.get("peak_time") is None else t1(sh["peak_time"]),
        "half_return_by": (
            None if sh.get("return_half_time") is None else t1(sh["return_half_time"])
        ),
        "settles_in_window": sh.get("settled_by_end"),
        "returns_toward_baseline": sh.get("returns_toward_baseline"),
        "timescale_at_bound": fit.get("timescale_at_bound"),
        "control": row.get("control"),
        "vs_control": (row.get("vs_control") or {}).get("bucket"),
    }


def build(signals: dict) -> dict:
    """The phenomenology artifact from a signals artifact: sentences, and the
    qualitative descriptors they were read from."""
    cd = (signals or {}).get("curve_descriptors") or {}
    rows = cd.get("per_series") or []
    if not rows:
        return {
            "available": False,
            "why": cd.get("why") or "no raw series to describe",
            "sentences": [],
            "steady_state_only": cd.get("steady_state_only") or [],
        }
    orders = cd.get("dose_response") or []
    sentences = []
    for obs, attr, val, srows in _cf.strata(rows, key=shape_key):
        phrases = []
        for group in _cf.clusters(srows, key=shape_key):
            where = _cf.where_text(group, srows, attr)
            phrases.append(
                _shape_words(group)
                + (f" {where}" if where else "")
                + _control_words(group)
            )
        phrases += _dose_words(orders, obs, attr, val)
        under = _cf.under_text(srows, attr, val)
        sentences.append(f"{obs}{under}: " + "; ".join(phrases) + ".")
    return {
        "available": True,
        "sentences": sentences,
        "descriptors": [_qualitative(r) for r in rows],
        "dose_response": [
            {
                k: o[k]
                for k in ("observable", "attribute", "held_fixed", "levels", "order")
            }
            for o in orders
        ],
        "excluded_conditions": cd.get("excluded_conditions") or [],
        # measured at steady state only (time inf): no time course to describe
        "steady_state_only": cd.get("steady_state_only") or [],
        "how_to_read_this": HOW_TO_READ,
    }


def card_lines(ph: dict | None, limit: int = CARD_LIMIT) -> list[str]:
    """The sentences for a card, capped, with where the rest are."""
    if not isinstance(ph, dict) or not ph.get("sentences"):
        return []
    sentences = ph["sentences"]
    out = [
        "WHAT THE CURVES LOOK LIKE (data alone, no model; shape and timescale "
        "only — the view of the data construction is given):"
    ]
    out += [f"  · {s}" for s in sentences[:limit]]
    if len(sentences) > limit:
        out.append(f"  … {len(sentences) - limit} more in the record ({KEY})")
    if ph.get("excluded_conditions"):
        out.append(
            "  (held out, not described: " + ", ".join(ph["excluded_conditions"]) + ")"
        )
    if ph.get("steady_state_only"):
        out.append(
            "  (measured at steady state only, not described: "
            + ", ".join(
                f"{s['observable']}@{s['condition']}" for s in ph["steady_state_only"]
            )
            + ")"
        )
    return out


def for_construction(ctx) -> dict | None:
    """The construction agent's view of the data: the sentences and how to read
    them, or None when there is nothing robust to describe.

    The curated reading first: the round's `data/phenomenology` record (S2
    wrote it: a later round), else a table staged before S1 (supplied, or
    seeded) described on the spot, with the same held-out conditions excluded.
    Without a table, the raw files' own reading (`raw_phenomenology`), which is
    absent whenever its acceptance rules do not all hold.
    """
    if str(ctx.spec.get("data_signals", "noise_only")).lower() == "off":
        return None
    p = node(ctx.round)
    ph = None
    if p.exists():
        ph = p.get(None)
    else:
        long_df = (ctx.round / "data/measurements").table(None)
        if long_df is None:
            from octomod.workflow_modules.data import raw_phenomenology as _raw

            return _raw.view(ctx)
        try:
            ph = build(_signals_from_table(ctx, long_df))
        except Exception:  # a description never stops construction
            ph = None
    if not isinstance(ph, dict) or not ph.get("sentences"):
        return None
    return {"sentences": list(ph["sentences"]), "how_to_read_this": HOW_TO_READ}


def _signals_from_table(ctx, long_df) -> dict:
    """`long_df`: the round's `data/measurements` table (a DataFrame)."""
    from octomod.workflow_modules.data import data_signals as _sig

    if "condition_key" not in long_df.columns:
        return {}
    holdout = (ctx.testcase.get("holdout") or {}).get("condition_labels") or []
    return {
        "curve_descriptors": _sig.curve_descriptors(
            long_df, _sig.held_out_keys(long_df, holdout)
        )
    }


def write(ctx, signals: dict) -> dict:
    """Build the artifact beside the signals, ledger it and return it."""
    ph = build(signals)
    sha = node(ctx.round).put(ph)
    ctx.ledger.append(
        "data_phenomenology",
        module="data",
        round_idx=ctx.round_idx,
        n_sentences=len(ph.get("sentences") or []),
        n_series=len(ph.get("descriptors") or []),
        excluded_conditions=ph.get("excluded_conditions") or [],
        steady_state_only=ph.get("steady_state_only") or [],
        sha=sha,
        note=(
            f"data phenomenology · {len(ph.get('sentences') or [])} sentence(s) "
            f"over {len(ph.get('descriptors') or [])} series, held-out "
            f"conditions excluded: {ph.get('excluded_conditions') or 'none'}"
            if ph.get("available")
            else f"data phenomenology not available: {ph.get('why')}"
        ),
    )
    # the raw-file reading construction may have been given, against this one
    from octomod.workflow_modules.data import raw_phenomenology as _raw

    _raw.self_check(ctx)
    return ph
