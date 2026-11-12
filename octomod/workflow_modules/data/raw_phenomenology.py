"""The curves in words, read from the RAW data files before construction.

`phenomenology` describes the curated long table S2 writes, but S1 runs before
S2, so in the first round of a fresh run construction would read the lab note
alone. This module reads the input's own data files first, with the design
summary's column roles (`design_summary.summarize_frame`), and builds the same
descriptors and sentences the S2 path builds (`data_signals.curve_descriptors`
through `phenomenology.build`), tagged `source: "raw files"`. It does so only
when the files say unambiguously what the time axis, the readouts and the
conditions are; otherwise it produces nothing, says which rule failed, and
construction reads the lab note alone.

ACCEPTANCE RULES, every one required, checked in this order (the first that
fails is the one named):

  data_files          the input's data/ holds at least one .csv/.tsv the
                      connector reads, and no workbook beside them;
  one_time_column     each file has exactly one column whose role the design
                      summary infers as time;
  time_values         that column is numeric, has no blank or -inf cell (inf is
                      a steady-state measurement, kept off the curves), and has
                      at least 4 distinct finite values;
  time_unambiguous    no column is ambiguous between time and measurement: the
                      time column's name reads as time on its own, not only
                      through the pattern's `min…`/`sec…` prefix (`min_signal`,
                      `secreted_il6`); when the other columns form more than
                      one group (series, replicates) its values recur, as
                      sampling times do, rather than one per row, as readings
                      do; and no other column's name carries a time word
                      (`timepoint`, `Time (h)`), which would be a second time
                      axis the pattern missed;
  error_columns       no column is named as a spread (sd, sem, std, err, ci,
                      cv, sigma …): which readout it belongs to is S2's call;
  measurement_column  each file has at least one numeric measurement column;
  design_levels       every other column is a design factor with at most 16
                      levels or the replicate column (no identifier-like
                      column, whose place in the design cannot be told);
  holdout_resolves    every declared holdout label resolves against the raw
                      columns (the HOLDOUT RULE below);
  series_time_points  every series described (one measurement column under one
                      combination of the design columns, held-out rows removed)
                      has at least 4 distinct finite time points with a finite
                      value; a series measured at steady state only (time inf)
                      has no curve and is not described;
  files_disjoint      no series is held by two files (the files would differ in
                      something no column names).

HOLDOUT RULE. Each declared label is parsed into `column=value` pairs with the
parser the S3 split uses (`data.parse_declared_label`, values rendered with
%g as S2 renders them). A label resolves when it yields at least one pair,
every column it names is a design column of every file, and at least one raw
row carries all its values. The held-out conditions are every raw condition
that carries all the pairs of a label, whatever its other columns say, so a
raw design richer than the declaration holds out at least what the S3 split
holds out, never less. When any declared label does not resolve, NOTHING is
described — not "nothing excluded": construction is never told the exam, and
when the raw columns cannot say which rows are the exam, the only description
that cannot leak it is none.

Accepted: the record's run-level `phenomenology_raw`, ledgered as
`data_phenomenology` with `source: "raw files"`. Rejected: nothing in the
record, a ledger row naming the rule, and one line on the intent card. After
S2 the raw reading is compared with the curated one (`self_check`), ledgered,
and put on the compile card; everything downstream of construction reads the
S2 version.

The raw files themselves are the run's INPUT: `ctx.testcase_dir / "data"` (and
`…/supplied`) are real directories, the input snapshot materialised for the
process, and are read from disk with the local-files connector.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from octomod.result.node import Node
from octomod.workflow_modules.data import design_summary as _ds
from octomod.workflow_modules.data import phenomenology as _ph

# the raw reading is taken from the inputs before any round exists and is the
# same for every round, so it lives at the run level (`RunResult.phenomenology_raw`)
KEY = "phenomenology_raw"
SOURCE = "raw files"
MIN_TIME_POINTS = 4
MAX_LEVELS = _ds.MAX_LEVELS

RULES = (
    "data_files",
    "one_time_column",
    "time_values",
    "time_unambiguous",
    "error_columns",
    "measurement_column",
    "design_levels",
    "holdout_resolves",
    "series_time_points",
    "files_disjoint",
)

HOW_TO_READ = _ph.HOW_TO_READ + (
    " These were read from the raw data files, before the curated table "
    "exists: an observable is named by its column in the file and a "
    "condition by the file's own design columns, which the curated table may "
    "name differently."
)

# The design summary's time pattern accepts any name starting `min` or `sec`;
# on its own a name reads as time only as a time word, or a unit spelled out.
_TIME_NAME_RE = re.compile(
    r"^(t|time|time_\w+|\w*_time|hours?|hrs?|mins?|minutes?|secs?|seconds?|days?)$",
    re.I,
)
_TIME_WORDS = frozenset(
    "time times timepoint timepoints hour hours hr hrs minute minutes min mins "
    "second seconds sec secs day days".split()
)
_ERROR_WORDS = frozenset(
    "sd sem se std stdev stderr err error errors ci cv sigma var variance".split()
)


class _Reject(Exception):
    def __init__(self, rule: str, why: str):
        super().__init__(why)
        self.rule, self.why = rule, why


def node(root: Node) -> Node:
    """Where the raw reading lives: the run-level `phenomenology_raw`, taken
    before round 0's construction, which runs before any table exists (`root`
    = `ctx.root`)."""
    return root / KEY


def _tokens(name) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", str(name).lower()) if t}


# ------------------------------------------------------------------ reading


def _read_files(data_dir: Path) -> dict[str, pd.DataFrame]:
    from octomod.connectors.local_files import (
        LocalFilesConnector,
        unreadable_spreadsheets,
    )

    if not data_dir.is_dir():
        raise _Reject("data_files", "the input has no data/ folder")
    skipped = unreadable_spreadsheets(data_dir)
    if skipped:
        raise _Reject(
            "data_files",
            f"a workbook ({', '.join(skipped)}) sits beside the tables, and "
            f"which of its sheets are data is a staging decision",
        )
    connector = LocalFilesConnector(data_dir)
    frames = {}
    for ref in connector.list_sources():
        name = ref.locator.split("/")[-1]
        try:
            frames[name] = connector.fetch(ref).df
        except Exception as e:  # a malformed file is a reason, not a crash
            raise _Reject(
                "data_files", f"{name} could not be read ({type(e).__name__})"
            ) from e
    if not frames:
        raise _Reject("data_files", "data/ holds no .csv or .tsv file")
    return frames


def _design_of(name: str, df: pd.DataFrame) -> dict:
    """One file's roles, or the first rule it breaks."""
    s = _ds.summarize_frame(df)
    roles = {c: r["role"] for c, r in s["columns"].items()}
    times = s["time_columns"]
    if len(times) != 1:
        raise _Reject(
            "one_time_column",
            f"{name} has {len(times)} time-like columns"
            + (f" ({', '.join(times)})" if times else "")
            + "; exactly one is needed",
        )
    tcol = times[0]
    t = df[tcol]
    if not pd.api.types.is_numeric_dtype(t):
        raise _Reject("time_values", f"{name}: the time column {tcol} is not numeric")
    tv = t.to_numpy(dtype=float)
    # `inf` is a steady-state measurement (PEtab's convention), not a blank:
    # the curves leave it out, as they describe the time course
    if np.isnan(tv).any() or np.isneginf(tv).any():
        raise _Reject(
            "time_values",
            f"{name}: the time column {tcol} has blank or non-finite cells",
        )
    n_times = int(pd.Series(tv[np.isfinite(tv)]).nunique())
    if n_times < MIN_TIME_POINTS:
        raise _Reject(
            "time_values",
            f"{name}: the time column {tcol} has {n_times} distinct values; "
            f"a curve needs at least {MIN_TIME_POINTS}",
        )
    if not _TIME_NAME_RE.match(str(tcol)):
        raise _Reject(
            "time_unambiguous",
            f"{name}: {tcol} reads as time only through the pattern's "
            f"min…/sec… prefix, and may be a readout",
        )
    design = [c for c, r in roles.items() if r == "design"]
    reps = [c for c, r in roles.items() if r == "replicate"]
    groups = df.groupby(design + reps, dropna=False).ngroups if design + reps else 1
    if groups > 1 and n_times == len(df):
        raise _Reject(
            "time_unambiguous",
            f"{name}: every row carries its own {tcol} value although the "
            f"other columns form {groups} groups — either {tcol} holds readings "
            f"rather than sampling times, or a readout was taken for a design "
            f"factor",
        )
    others = [c for c in df.columns if c != tcol and _tokens(c) & _TIME_WORDS]
    if others:
        raise _Reject(
            "time_unambiguous",
            f"{name}: besides {tcol}, {', '.join(map(str, others))} "
            f"{'names' if len(others) == 1 else 'name'} a time too",
        )
    errors = [c for c in df.columns if c != tcol and _tokens(c) & _ERROR_WORDS]
    if errors:
        raise _Reject(
            "error_columns",
            f"{name}: {', '.join(map(str, errors))} "
            f"{'reads' if len(errors) == 1 else 'read'} as a spread, and which "
            f"readout it belongs to is the extraction's call",
        )
    meas = [
        c
        for c, r in roles.items()
        if r == "measurement" and pd.api.types.is_numeric_dtype(df[c])
    ]
    if not meas:
        raise _Reject("measurement_column", f"{name} has no numeric measurement column")
    idents = [c for c, r in roles.items() if r == "identifier"]
    if idents:
        raise _Reject(
            "design_levels",
            f"{name}: {', '.join(idents)} has more than {MAX_LEVELS} levels and "
            f"is not a measurement, so its place in the design cannot be told",
        )
    return {
        "file": name,
        "df": df,
        "time": tcol,
        "measurements": meas,
        "design": design,
        "replicate": reps[0] if reps else None,
    }


def _keys(df: pd.DataFrame, design: list[str]) -> pd.Series:
    """Each row's condition key, built as S2 builds it (`data.condition_key`:
    the design columns sorted, values rendered with %g)."""
    from octomod.workflow_modules.data.engine import format_value

    if not design:
        return pd.Series("", index=df.index)
    parts = [(c + "=") + df[c].map(format_value).astype(str) for c in sorted(design)]
    out = parts[0]
    for p in parts[1:]:
        out = out + "|" + p
    return out


# ------------------------------------------------------------------ holdout


def _resolve_holdout(tables: list[dict], labels) -> tuple[set[str], dict]:
    """(the raw condition keys held out, the record of how) — or the reject
    that says a label did not resolve (the HOLDOUT RULE)."""
    from octomod.workflow_modules.data.data_signals import attributes_of
    from octomod.workflow_modules.data.engine import format_value, parse_declared_label

    held: set[str] = set()
    resolved: dict[str, list[str]] = {}
    for label in labels or []:
        pairs = attributes_of(parse_declared_label(str(label)))
        if not pairs:
            raise _Reject(
                "holdout_resolves",
                f"the holdout {label!r} names no column=value pair, so which "
                f"raw rows it holds out cannot be told",
            )
        keys: set[str] = set()
        for t in tables:
            missing = [c for c in pairs if c not in t["design"]]
            if missing:
                raise _Reject(
                    "holdout_resolves",
                    f"the holdout {label!r} names {', '.join(missing)}, which "
                    f"is not a design column of {t['file']}, so that file's "
                    f"held-out rows cannot be told",
                )
            df = t["df"]
            hit = np.ones(len(df), dtype=bool)
            for c, v in pairs.items():
                hit &= df[c].map(format_value).astype(str).to_numpy() == str(v)
            keys |= set(_keys(df, t["design"])[hit])
        if not keys:
            raise _Reject(
                "holdout_resolves",
                f"the holdout {label!r} matches no raw row",
            )
        resolved[str(label)] = sorted(keys)
        held |= keys
    return held, {
        "declared": [str(x) for x in labels or []],
        "resolved": resolved,
        "rule": "a label holds out every raw condition carrying all its "
        "column=value pairs; a label that does not resolve means nothing "
        "is described",
    }


# ------------------------------------------------------------------ the table


def _long_table(tables: list[dict]) -> pd.DataFrame:
    """The raw files in the long form `curve_descriptors` reads, values as the
    files hold them (nothing edited, nothing dropped but blank readings)."""
    parts = []
    for t in tables:
        df = t["df"]
        keys = _keys(df, t["design"])
        for m in t["measurements"]:
            part = pd.DataFrame(
                {
                    "file": t["file"],
                    "observable_label": str(m),
                    "condition_label": keys,
                    "condition_key": keys,
                    "time": df[t["time"]].to_numpy(dtype=float),
                    "value": df[m].to_numpy(dtype=float),
                    "replicate": df[t["replicate"]] if t["replicate"] else 1,
                }
            )
            parts.append(part[np.isfinite(part["value"].to_numpy())])
    return pd.concat(parts, ignore_index=True)


def _check_series(long_df: pd.DataFrame, excluded: set[str]) -> None:
    kept = long_df[~long_df["condition_key"].isin(excluded)]
    if kept.empty:
        raise _Reject(
            "series_time_points", "no series is left once the holdout is removed"
        )
    for (fname, obs, key), g in kept.groupby(
        ["file", "observable_label", "condition_key"]
    ):
        t = g["time"].to_numpy(dtype=float)
        if not np.isfinite(t).any():
            continue  # steady state only (time inf): named, not described
        n = int(pd.Series(t[np.isfinite(t)]).nunique())
        if n < MIN_TIME_POINTS:
            raise _Reject(
                "series_time_points",
                f"{fname}: {obs} under {key or '(the one condition)'} has {n} "
                f"distinct time point(s); a curve needs at least {MIN_TIME_POINTS}",
            )
    owners = kept.groupby(["observable_label", "condition_key"])["file"].nunique()
    shared = owners[owners > 1]
    if len(shared):
        obs, key = shared.index[0]
        raise _Reject(
            "files_disjoint",
            f"{obs} under {key or '(the one condition)'} is in "
            f"{int(shared.iloc[0])} files, which differ in something no "
            f"column names",
        )


# ------------------------------------------------------------------ derive


def derive(data_dir: Path, holdout_labels) -> dict:
    """The raw reading of `data_dir`: the artifact when every rule holds,
    else `{available: False, rule, why}`. Deterministic; writes nothing."""
    from octomod.workflow_modules.data import data_signals as _sig

    try:
        frames = _read_files(Path(data_dir))
        tables = [_design_of(name, df) for name, df in sorted(frames.items())]
        excluded, holdout = _resolve_holdout(tables, holdout_labels)
        long_df = _long_table(tables)
        _check_series(long_df, excluded)
        try:
            cd = _sig.curve_descriptors(long_df.drop(columns=["file"]), excluded)
        except Exception as e:  # a description never stops construction
            raise _Reject(
                "series_time_points",
                f"the curves could not be described ({type(e).__name__}: {e})",
            ) from e
        ph = _ph.build({"curve_descriptors": cd})
        if not ph.get("available"):
            raise _Reject("series_time_points", str(ph.get("why")))
    except _Reject as r:
        return {"available": False, "source": SOURCE, "rule": r.rule, "why": r.why}
    except Exception as e:  # never a crash at the intent card: a reason
        return {
            "available": False,
            "source": SOURCE,
            "rule": "data_files",
            "why": f"the files could not be read into roles ({type(e).__name__}: {e})",
        }
    ph["source"] = SOURCE
    ph["how_to_read_this"] = HOW_TO_READ
    ph["files"] = {
        t["file"]: {
            "time_column": t["time"],
            "measurement_columns": [str(m) for m in t["measurements"]],
            "design_columns": [str(c) for c in t["design"]],
            "replicate_column": t["replicate"],
        }
        for t in tables
    }
    ph["holdout"] = holdout
    ph["rules_held"] = list(RULES)
    return ph


def applies(ctx) -> bool:
    """Whether a raw reading is what construction would read: not when the
    signals are off, and not when the input supplies what makes it moot — a
    model or a PEtab problem (construction is never called) or a curated long
    table (described instead)."""
    if str(ctx.spec.get("data_signals", "noise_only")).lower() == "off":
        return False
    sup = Path(ctx.testcase_dir) / "supplied"
    return not any(
        (sup / n).exists() for n in ("model.ant", "petab", "measurements_long.tsv")
    )


def ensure(ctx, module: str) -> dict | None:
    """The run's raw reading: read back when already written, else derived,
    written when accepted, and ledgered once either way. None when it does not
    apply (`applies`). The reading is in the record; the files it is derived
    from are the input's own."""
    if not applies(ctx):
        return None
    where = node(ctx.root)
    rec = where.get(None)
    if isinstance(rec, dict) and rec.get("available"):
        return rec
    holdout = (ctx.testcase.get("holdout") or {}).get("condition_labels") or []
    rec = derive(Path(ctx.testcase_dir) / "data", holdout)
    sha = None
    if rec.get("available"):
        sha = where.put(rec)
        # what the record holds (a JSON round trip), so the first reader and
        # a resumed one are handed the same reading
        rec = where.get()
    _ledger_once(ctx, rec, module, sha)
    return rec


def _ledger_once(ctx, rec: dict, module: str, sha: str | None) -> None:
    """One row per outcome: a resume that derives the same reading again (the
    intent card asked twice, construction after it) adds nothing."""
    for e in ctx.ledger.entries():
        if e.get("event") != "data_phenomenology" or e.get("source") != SOURCE:
            continue
        if rec.get("available") and e.get("sha") == sha:
            return
        if not rec.get("available") and (e.get("rule"), e.get("why")) == (
            rec.get("rule"),
            rec.get("why"),
        ):
            return
    if rec.get("available"):
        ctx.ledger.append(
            "data_phenomenology",
            module=module,
            round_idx=0,
            source=SOURCE,
            n_sentences=len(rec.get("sentences") or []),
            n_series=len(rec.get("descriptors") or []),
            excluded_conditions=rec.get("excluded_conditions") or [],
            sha=sha,
            note=(
                f"data phenomenology from the raw files · "
                f"{len(rec.get('sentences') or [])} sentence(s) over "
                f"{len(rec.get('descriptors') or [])} series, held-out "
                f"conditions excluded: {rec.get('excluded_conditions') or 'none'}"
            ),
        )
        return
    ctx.ledger.append(
        "data_phenomenology",
        module=module,
        round_idx=0,
        source=SOURCE,
        available=False,
        rule=rec.get("rule"),
        why=rec.get("why"),
        note=(
            f"curve descriptors not derived from the raw files — rule "
            f"{rec.get('rule')}: {rec.get('why')}; construction reads the lab "
            f"note only"
        ),
    )


def intent_card_lines(ctx) -> list[str]:
    """The intent card's one line on what construction will read of the data,
    with the command that prints the reading from the record."""
    from octomod.orchestration.interaction import humangate

    rec = ensure(ctx, "intent")
    if rec is None:
        return []
    if not rec.get("available"):
        return [
            f"curve descriptors: not derived from the raw files — {rec['why']} "
            f"(rule {rec['rule']}); construction reads the lab note only"
        ]
    held = rec.get("excluded_conditions") or []
    return [
        f"curve descriptors: {len(rec.get('sentences') or [])} sentence(s) over "
        f"{len(rec.get('descriptors') or [])} series, read from the raw files "
        f"for construction (values withheld; held out, not described: "
        f"{', '.join(held) if held else 'none'}) — "
        f"{humangate.show_command(node(ctx.root))}"
    ]


def view(ctx) -> dict | None:
    """Construction's view of the raw reading, or None when there is none."""
    rec = ensure(ctx, "model")
    if not isinstance(rec, dict) or not rec.get("sentences"):
        return None
    return {
        "sentences": list(rec["sentences"]),
        "how_to_read_this": HOW_TO_READ,
        "source": SOURCE,
    }


# ------------------------------------------------------------------ self-check

_TIMES = ("half_change_by", "peak_near", "half_return_by")
TIMESCALE_FACTOR = 2.0


def _s2_names(report: dict | None, obs: str, key: str) -> set[tuple[str, str]]:
    """The (label, condition key) the curated table gives a raw series, read
    from S2's own mappings: the value column names the label, the mapping's
    condition columns project the raw key. Without mappings (a supplied
    table), the raw names themselves."""
    from octomod.workflow_modules.data.data_signals import attributes_of
    from octomod.workflow_modules.data.engine import condition_key

    out = set()
    attrs = attributes_of(key)
    for m in (report or {}).get("mappings") or []:
        if m.get("observable_column") or str(m.get("value_column")) != obs:
            continue
        cols = list(m.get("condition_columns") or [])
        if all(c in attrs for c in cols):
            out.add(
                (
                    str(m.get("observable_label")),
                    condition_key({c: attrs[c] for c in cols}),
                )
            )
    return out or {(obs, key)}


def _shape_text(row: dict) -> str:
    form, d = row.get("form"), row.get("direction")
    words = {
        "constant": "flat",
        "linear": f"a steady {'rise' if d == 'increasing' else 'fall'}",
        "exponential": f"an exponential {d}",
        "rise_and_fall": "a rise and fall" if d == "peak" else "a dip and recovery",
    }.get(form, str(form))
    times = [
        f"{label} ~{row[k]}"
        for k, label in zip(
            _TIMES, ("half-change by", "peak near", "half-return by"), strict=True
        )
        if row.get(k) is not None
    ]
    return words + (f" ({', '.join(times)})" if times else "")


def _differs(a: dict, b: dict) -> str | None:
    """'shape' or 'timescale' when two descriptor rows disagree, else None."""
    if (a.get("form"), a.get("direction")) != (b.get("form"), b.get("direction")):
        return "shape"
    for k in _TIMES:
        try:
            x, y = float(a.get(k)), float(b.get(k))
        except (TypeError, ValueError):
            continue
        if x > 0 and y > 0 and max(x, y) > TIMESCALE_FACTOR * min(x, y):
            return "timescale"
    return None


def compare(raw: dict, s2: dict, report: dict | None) -> dict:
    """The raw reading against the curated one, per (observable, condition)
    whose names can be matched."""
    data_rows = {
        (r["observable"], r["condition"]): r for r in s2.get("descriptors") or []
    }
    targets: dict[tuple, list] = {}
    unmatched = []
    for r in raw.get("descriptors") or []:
        hits = [
            n
            for n in _s2_names(report, r["observable"], r["condition"])
            if n in data_rows
        ]
        if len(hits) == 1:
            targets.setdefault(hits[0], []).append(r)
        else:
            unmatched.append(f"{r['observable']} under {r['condition'] or '-'}")
    agree, disagree = 0, []
    for name, raws in sorted(targets.items()):
        if len(raws) > 1:  # the curated table pools series the raw files split
            unmatched += [
                f"{r['observable']} under {r['condition'] or '-'}" for r in raws
            ]
            continue
        r, c = raws[0], data_rows[name]
        on = _differs(r, c)
        if on is None:
            agree += 1
            continue
        disagree.append(
            {
                "on": on,
                "raw": [r["observable"], r["condition"]],
                "curated": list(name),
                "raw_reads": _shape_text(r),
                "curated_reads": _shape_text(c),
            }
        )
    return {
        "n_matched": agree + len(disagree),
        "n_agree": agree,
        "disagreements": disagree,
        "unmatched_raw": unmatched,
    }


def _check(ctx) -> dict | None:
    """The comparison for this round, when construction could have read the
    raw reading (round 0) and both readings exist."""
    if ctx.round_idx != 0:
        return None
    raw = node(ctx.root).get(None)
    s2 = _ph.node(ctx.round).get(None)
    if not (isinstance(raw, dict) and raw.get("available")):
        return None
    if not (isinstance(s2, dict) and s2.get("available")):
        return None
    report = (ctx.round / "data/report").get(None)
    return compare(raw, s2, report if isinstance(report, dict) else None)


def check_line(chk: dict | None) -> str | None:
    """The compile card's one line on the comparison."""
    if chk is None:
        return None
    if chk["disagreements"]:
        d = chk["disagreements"][0]
        more = len(chk["disagreements"]) - 1
        return (
            f"curve descriptors · the raw-file reading of {d['raw'][0]} under "
            f"{d['raw'][1] or '(the one condition)'} said {d['raw_reads']}, the "
            f"curated table says {d['curated_reads']}"
            + (f" (and {more} more disagreement(s), in the ledger)" if more else "")
        )
    if not chk["n_matched"]:
        return (
            "curve descriptors · the raw-file reading could not be matched to "
            "the curated table by name; everything after construction reads "
            "the curated one"
        )
    unmatched = len(chk["unmatched_raw"])
    return (
        f"curve descriptors · the raw-file reading construction was given "
        f"agrees with the curated table on all {chk['n_matched']} matched "
        f"series (shape class, and timescales within a factor of "
        f"{TIMESCALE_FACTOR:g})"
        + (f"; {unmatched} raw series not matched by name" if unmatched else "")
    )


def self_check(ctx) -> dict | None:
    """After S2: compare, ledger, and return the comparison (None when there
    is nothing to compare)."""
    try:
        chk = _check(ctx)
    except Exception as e:  # a check never stops the data module
        ctx.ledger.append(
            "note",
            module="data",
            round_idx=ctx.round_idx,
            note=f"curve descriptors · the raw-vs-curated check could not run "
            f"({type(e).__name__}: {e})",
        )
        return None
    if chk is None:
        return None
    ctx.ledger.append(
        "data_phenomenology_check",
        module="data",
        round_idx=ctx.round_idx,
        n_matched=chk["n_matched"],
        n_agree=chk["n_agree"],
        n_disagree=len(chk["disagreements"]),
        disagreements=chk["disagreements"][:8],
        unmatched_raw=chk["unmatched_raw"][:8],
        note=check_line(chk),
    )
    return chk


def check_card_lines(ctx) -> list[str]:
    """The compile card's line (none without both readings in round 0)."""
    try:
        line = check_line(_check(ctx))
    except Exception:  # the card never fails on a check; S2 ledgered why
        return []
    return [line] if line else []
