"""S2 — data extraction and curation.

The agent decides SEMANTICS (column mappings, units, error type); the engine
moves the numbers deterministically. That split is what makes transcription
checkable: the numbers cannot be silently altered because no agent touches
them. The agent may flag, never exclude — exclusions are a human decision.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from octomod.gates import GateResult, gate, run_gate_set
from octomod.orchestration import timing  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure, RunContext


@timing.phase("data")
def run(ctx: RunContext) -> None:
    if ctx.has_marker("s2"):
        print("  (already passed — resumed from marker; extracted measurements stand)")
        return
    ctx.require_marker("s1", needed_by="data")
    data = ctx.round / "data"
    long_node = data / "measurements"
    # in a seeded round the table is part of the seed: a re-entry that moved it
    # aside gets it back instead of a fresh extraction with new labels
    from octomod.orchestration import round_seed as _seed

    if _seed.restore_data(ctx.root, ctx.round):
        ctx.ledger.append(
            "note",
            module="data",
            round_idx=ctx.round_idx,
            note="the seeded measurement table was restored from the seed's "
            "source round — a re-entry had moved it aside",
        )
        print("  (seeded measurement table restored — a re-entry had moved it aside)")

    if long_node.exists():
        # user-supplied measurement table: agents skipped, gates not
        long_df = long_node.table()
        if "condition_key" not in long_df.columns:
            long_df["condition_key"] = long_df["condition_label"].map(
                parse_declared_label
            )
        long_df["condition_key"] = long_df["condition_key"].fillna("")
        # A revision round carries `data` forward, report included: its
        # observable-label declarations are what S3's observable agent maps.
        prior = (data / "report").get(None)
        if prior and prior.get("observable_labels"):
            report = prior
            ctx.ledger.append(
                "note",
                module="data",
                round_idx=ctx.round_idx,
                note=f"measurements + data_report carried forward "
                f"({len(prior['observable_labels'])} observable labels)",
            )
        else:
            report = {
                "mappings": [],
                "observable_labels": [],
                "flags": [],
                "notes": "measurements supplied by user",
                "provenance": [],
            }
            ctx.ledger.append(
                "note",
                module="data",
                round_idx=ctx.round_idx,
                note="data/measurements user-supplied",
            )
    else:
        from octomod.connectors.local_files import (
            LocalFilesConnector,
            unreadable_spreadsheets,
        )

        raw_dir = ctx.testcase_dir / "data"
        connector = LocalFilesConnector(raw_dir)
        sources = connector.list_sources()
        # Checked BEFORE the empty case: a workbook beside a csv is the worse
        # bug of the two, because the run completes on whatever the csv held.
        skipped = unreadable_spreadsheets(raw_dir)
        if skipped:
            raise ModuleFailure(
                f"{raw_dir} holds spreadsheet files this engine does not read: "
                f"{', '.join(skipped)}. Export every sheet you want modelled to "
                f".csv or .tsv (one sheet per file, header row first) and stage "
                f"those instead; then delete or move the workbook. The "
                f"conversion is deliberately yours: which sheet and which row "
                f"is the header are modelling decisions, and a run that guessed "
                f"them would not be able to say so."
                + (
                    f" Currently readable: {', '.join(r.meta['filename'] for r in sources)}"
                    f" — a run on those alone would silently omit the rest."
                    if sources
                    else ""
                )
            )
        if not sources:
            raise ModuleFailure(f"no .csv/.tsv data files in {raw_dir}")
        previews = {}
        frames = {}
        for ref in sources:
            table = connector.fetch(ref)
            name = ref.locator.split("/")[-1]
            frames[name] = table.df
            previews[name] = (
                f"(file has {len(table.df)} rows total; preview of first 25)\n"
                + table.df.head(25).to_csv(index=False)
            )

        # The preview is 25 rows; the design summary (which factor levels exist,
        # which combinations are absent) covers the whole file, with no values.
        from octomod.workflow_modules.data import design_summary as _ds

        design = _ds.compute(frames)
        (data / "design_summary").put(design)

        context = {
            "intent": ctx.intent,
            "experiment_description": ctx.description,
            "data_file_previews": previews,
            "design_summary": design,
        }
        from octomod.orchestration.interaction import retry as _retry

        base_budget = int(ctx.spec.get("retry.module_draft", 2)) + 1
        history = _retry.AttemptHistory(_retry.dossier_of(ctx, "data_extraction"))
        long_df, report = None, None
        attempt = len(history)
        while long_df is None:
            # checked before the call, so a resume never makes an unbudgeted one
            budget = base_budget + history.grants_total
            if attempt >= budget:
                granted = _retry.exhaustion_gate(
                    ctx, "data", "data_extraction", history, budget
                )
                if granted == 0:
                    raise ModuleFailure(
                        "data extraction exhausted its redraft budget "
                        "and the human did not extend it"
                    )
                continue  # re-read the budget from the persisted grant
            if history.attempts:  # the whole dossier, not only the last error
                context["attempt_history"] = history.as_context()
            extraction = ctx.call("data_extraction", context)
            try:
                long_df, provenance = _execute_mappings(extraction, connector, sources)
            except ModuleFailure as e:
                entry = history.add(
                    [str(e)],
                    {
                        "n_mappings": len(extraction.get("mappings") or []),
                        "labels": [
                            m.get("observable_label")
                            for m in extraction.get("mappings") or []
                        ],
                        "files": sorted(
                            {
                                str(m.get("file"))
                                for m in extraction.get("mappings") or []
                            }
                        ),
                    },
                )
                ctx.ledger.append(
                    "redraft",
                    module="data",
                    round_idx=ctx.round_idx,
                    role="data_extraction",
                    attempt=entry["attempt"],
                    n_failures=1,
                    localized=False,
                )
                attempt += 1
                continue
            report = _report_from_extraction(extraction, provenance)

    long_df, report = _battery_with_feedback(ctx, long_df, report, locals())

    long_node.put_table(long_df)
    (data / "report").put(report)

    # Computed here, where the long table becomes final. The mode controls only
    # where the signals route; the artifact is written unless the mode is `off`.
    mode = str(ctx.spec.get("data_signals", "noise_only")).lower()
    if mode != "off":
        from octomod.workflow_modules.data import data_signals as _sig

        # the held-out conditions stay out of the curve descriptors, which
        # construction reads in words: the exam is not described to it
        holdout = (ctx.testcase.get("holdout") or {}).get("condition_labels") or []
        signals = _sig.compute(long_df, _sig.held_out_keys(long_df, holdout))
        signals["mode"] = mode
        # the processed-table facts travel with the noise signals, under the key
        # the routing table already grants the observation agent
        from octomod.workflow_modules.data import data_processing as _dp

        signals["processing_applied"] = _dp.summary_for_agent(
            report.get("processing") or []
        )
        # the declared detection floors travel to the observation agent under
        # the key it already sees, with the row counts they touch
        from octomod.workflow_modules.data import censoring as _cen

        cen = _cen.for_agent(report.get("below_detection_summary") or [])
        if cen is not None:
            signals["below_detection"] = cen
            for line in _cen.findings(cen["declared"]):
                ctx.ledger.append(
                    "note",
                    module="data",
                    round_idx=ctx.round_idx,
                    note=f"below-detection declared · {line}",
                )
                print(f"  below detection: {line}")
        if mode == "full":
            # `full` would feed construction structural hints, which needs S2 to
            # run before S1; the pipeline is not reordered, so `full` is
            # recorded and routes as noise_only
            signals["full_mode_note"] = (
                "`full` was requested but routes as `noise_only`: the "
                "structural hints it adds would have to reach construction, "
                "which runs BEFORE data extraction. The S2/S1 reorder is "
                "declined for now, so no structural hint is routed and none "
                "is computed."
            )
            ctx.ledger.append(
                "note",
                module="data",
                round_idx=ctx.round_idx,
                note=f"data signals: {signals['full_mode_note']}",
            )
        (data / "signals").put(signals)
        for line in _sig.card_lines(signals):
            print(f"  {line}")
        # the curves in words, beside the signals: the one data-derived input
        # construction is shown
        from octomod.workflow_modules.data import phenomenology as _ph

        for line in _ph.card_lines(_ph.write(ctx, signals)):
            print(f"  {line}")
        for label, rec in (signals.get("per_observable") or {}).items():
            ctx.ledger.append(
                "note",
                module="data",
                round_idx=ctx.round_idx,
                note=(
                    f"data signal · {label}: error model "
                    f"{rec['noise']['error_model']} — {rec['noise']['why']}"
                ),
            )
    ctx.set_marker(
        "s2",
        n_rows=len(long_df),
        n_flags=len(report.get("flags", [])),
        producer=(
            "agent:data_extraction" if report.get("mappings") else "user-supplied"
        ),
    )


def _report_from_extraction(extraction: dict, provenance: list) -> dict:
    """The data report from one extraction reply: the only place the reply's
    keys are picked out, so the first extraction and every re-ask keep the same
    keys."""
    return {
        "mappings": extraction["mappings"],
        "observable_labels": extraction["observable_labels"],
        "flags": extraction["flags"],
        "notes": extraction.get("notes", ""),
        "provenance": provenance,
        # what the source did below its detection floor: declared, counted and
        # reported; never modelled
        "below_detection": extraction.get("below_detection") or [],
    }


# ------------------------------------------------- battery feedback, no dead ends

MAX_FEEDBACK_CYCLES = 12


def _battery_with_feedback(ctx: RunContext, long_df, report: dict, scope: dict):
    """Run the S2 battery; a blocking failure goes back to `data_extraction`
    with the check verbatim, its own mappings for the implicated labels and
    the rows the engine built from them; when the budget is spent, or the
    table was user-supplied, a person decides at the failure point.
    `scope` is the caller's locals: the connector, sources, context and
    dossier exist only on the agent path and are reused from there."""
    from octomod.gates import failure_summary
    from octomod.orchestration.interaction import battery_feedback as _bf
    from octomod.orchestration.interaction import retry as _retry
    from octomod.workflow_modules.data import censoring as _cen
    from octomod.workflow_modules.data import data_processing as _dp

    agent_path = bool(report.get("mappings")) and "connector" in scope
    budget = int(ctx.spec.get("retry.module_draft", 2))
    history = _retry.AttemptHistory(_retry.dossier_of(ctx, "data_extraction"))
    holdout_labels = list(ctx.testcase.get("holdout", {}).get("condition_labels", []))
    raw_df = long_df.copy()  # what extraction produced; processing never edits it
    for _cycle in range(MAX_FEEDBACK_CYCLES):
        extraction = (
            ((ctx.agent_calls.child("data_extraction") / "reply").get(None) or {})
            if agent_path
            else {}
        )
        ops = extraction.get("processing") if agent_path else None
        report["processing_declared"] = ops or []
        # The declared ops run here, before the battery and the signals: what is
        # checked and fitted is the processed table. A refusal is a battery
        # failure attributed to data_extraction, never a dead end.
        try:
            long_df, record = _dp.apply(ops, raw_df, holdout_labels)
            report["processing"] = record
            # the declared floors are counted once, here, on the raw extracted
            # values (the scale a declared threshold refers to); the screen, the
            # signals and the round report read this record
            report["below_detection_summary"] = _cen.summary(
                _cen.declared(report),
                raw_df,
                counted_on="the raw extracted values, on the source's scale"
                + (", before the declared processing" if record else ""),
            )
            for e in record:  # scale_units: the label's declared units follow
                if e["kind"] == "scale_units":
                    for lab in report.get("observable_labels") or []:
                        if str(lab.get("label")) in e["labels"]:
                            lab["units"] = e["to_units"]
            ok, results = run_gate_set(
                make_data_gates(long_df, report, ctx),
                ctx.gates,
                ctx.ledger,
                "data",
                round_idx=ctx.round_idx,
            )
        except _dp.ProcessingRefused as e:
            refusal = GateResult("data_processing_legal", "T0", False, detail=str(e))
            print(refusal.summary())
            ctx.ledger.append(
                "gate",
                module="data",
                round_idx=ctx.round_idx,
                gate_id=refusal.gate_id,
                tier=refusal.tier,
                passed=False,
                blocking=True,
                detail=refusal.detail,
            )
            ok, results, long_df = False, [refusal], raw_df
        if ok:
            if report.get("processing"):
                (ctx.round / "data/raw").put_table(raw_df)
                for line in _dp.card_lines(report["processing"]):
                    print(f"  {line}")
                    ctx.ledger.append(
                        "note",
                        module="data",
                        round_idx=ctx.round_idx,
                        note=f"processing · {line}",
                    )
            return long_df, report
        role, failing = _bf.attribute(results)
        gate = failing[0]
        if not agent_path:
            role = None
        labels = sorted(set(long_df["observable_label"].astype(str)))
        ids = _bf.implicated_ids(gate.detail, labels)
        block = (
            extraction.get("processing")
            if gate.gate_id == "data_processing_legal"
            else _bf.extraction_block(extraction, ids)
        )
        if role is not None and len(history) < budget + history.grants_total:
            entry = history.add(
                [f"{gate.gate_id}: {gate.detail}"], {"gate": gate.gate_id}
            )
            ctx.ledger.append(
                "redraft_attributed",
                module="data",
                round_idx=ctx.round_idx,
                role=role,
                gate_id=gate.gate_id,
                attempt=entry["attempt"],
            )
            print(
                f"  → {gate.gate_id} failed; re-asking data_extraction with the "
                f"check and its own mappings (attempt {entry['attempt']})"
            )
            rows = (
                long_df[long_df["observable_label"].astype(str).isin(ids)]
                if ids
                else long_df
            )
            context = dict(scope["context"])
            context["attempt_history"] = history.as_context()
            context["battery_feedback"] = _bf.feedback(
                _bf.gate_record(gate),
                role,
                block,
                rows.head(12).to_dict(orient="records"),
                {
                    "data_labels_declared": labels,
                    "holdout_condition_labels": holdout_labels,
                    "condition_labels_present": sorted(
                        set(long_df["condition_label"].astype(str))
                    ),
                    "processing_kinds": _dp.KINDS,
                    "error_type": ["sd", "sem", "none", "column"],
                },
            )
            new = ctx.call("data_extraction", context)
            try:
                long_df, provenance = _execute_mappings(
                    new, scope["connector"], scope["sources"]
                )
            except ModuleFailure as e:
                history.add([str(e)], {"n_mappings": len(new.get("mappings") or [])})
                continue
            report = _report_from_extraction(new, provenance)
            raw_df = long_df.copy()
            continue
        decision, arg = _bf.failure_point_gate(
            ctx, "data", role, failing, block, history, budget, offer_fallbacks=False
        )
        if decision == "more":
            continue
        if decision == "redraft":
            if not agent_path:
                raise ModuleFailure(
                    "nothing to redraft: the measurement table was user-supplied; "
                    + failure_summary(results, "S2 data", ctx.gates)
                )
            from octomod.orchestration.interaction import human_redraft as _hr

            _hr.record(ctx, "data", "data_extraction", str(arg))
            context = dict(scope["context"])
            context.update(
                _hr.context_for(
                    str(arg),
                    "data_extraction",
                    _hr.previous_reply(ctx, "data_extraction"),
                )
            )
            new = ctx.call("data_extraction", context)  # a person's words: uncharged
            try:
                long_df, provenance = _execute_mappings(
                    new, scope["connector"], scope["sources"]
                )
            except ModuleFailure as e:
                history.add([str(e)], {"n_mappings": len(new.get("mappings") or [])})
                continue
            report = _report_from_extraction(new, provenance)
            raw_df = long_df.copy()
            continue
        raise ModuleFailure(failure_summary(results, "S2 data", ctx.gates))
    raise ModuleFailure("S2 battery: feedback cycles exhausted (engine ceiling)")


# ---------------------------------------------------------------- executor


def format_value(value) -> str:
    """Numeric condition-label rendering rule: %g (0.30 -> '0.3', 3.0 -> '3').
    One rule, stated once, so staged holdout declarations can match the data."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


# A condition's display label is the agent's free choice, so nothing staged is
# ever matched against it. The KEY is engine-derived from the data's own column
# names and %g values, sorted; holdout declarations are parsed to the same form.

_DECL_TOKEN = re.compile(
    r"([A-Za-z][A-Za-z0-9_]*)\s*=\s*"
    r"([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?|[A-Za-z0-9.+-]+)"
)


def condition_key(cond_vals: dict) -> str:
    """Canonical condition identity: 'col=val|col=val', columns sorted,
    values %g-rendered. Empty dict (a constant-label case) -> ''."""
    return "|".join(f"{k}={format_value(v)}" for k, v in sorted(cond_vals.items()))


def parse_declared_label(label: str) -> str:
    """Parse a staged 'column=value' declaration ('u=4,bx11=1'; separators
    and order free) into the same canonical key. No tokens -> ''."""
    return condition_key(
        {m.group(1): m.group(2) for m in _DECL_TOKEN.finditer(str(label))}
    )


def _execute_mappings(
    extraction: dict, connector, sources
) -> tuple[pd.DataFrame, list]:
    by_name = {ref.locator.split("/")[-1]: ref for ref in sources}
    rows, provenance = [], []
    for m in extraction["mappings"]:
        fname = m["file"].split("/")[-1]
        if fname not in by_name:
            raise ModuleFailure(
                f"mapping references file {m['file']!r}; available: {sorted(by_name)}"
            )
        table = connector.fetch(by_name[fname])
        df = table.df
        needed = [m["time_column"], m["value_column"]] + list(m["condition_columns"])
        if m.get("replicate_column"):
            needed.append(m["replicate_column"])
        # a long-format file names each row's observable in a column, with one
        # value column for several readouts
        obs_col = m.get("observable_column")
        if obs_col:
            needed.append(obs_col)
        elif not m.get("observable_label"):
            raise ModuleFailure(
                f"file {fname}: a mapping needs either `observable_label` (one "
                f"observable per mapping) or `observable_column` (the column that "
                f"names the observable in each row)"
            )
        # a per-row measurement error on the value's own scale, taken as a
        # FIXED sigma by the assembly (`error_type: column`)
        err_col = m.get("error_column")
        if err_col:
            needed.append(err_col)
        missing = [c for c in needed if c not in df.columns]
        if missing:
            raise ModuleFailure(
                f"file {fname}: mapped columns {missing} not found "
                f"(columns are {list(df.columns)})"
            )
        provenance.append(table.provenance)
        # replicate labels need not be integers (a donor code, a culture id); the
        # label -> id table is kept in the provenance so the report can name them
        rep_ids = _replicate_ids(df, m.get("replicate_column"))
        # A blank replicate cell is neither an id nor "no replicate" (the map
        # above drops blanks): refused by name, with the rows, rather than
        # grouped by a guess.
        rep_col = m.get("replicate_column")
        if rep_col:
            blank_rows = [i + 2 for i, v in enumerate(df[rep_col].isna()) if v]
            if blank_rows:
                raise ModuleFailure(
                    f"file {fname}: replicate column {rep_col!r} is blank in "
                    f"{len(blank_rows)} of {len(df)} rows (file rows "
                    f"{blank_rows[:8]}{', …' if len(blank_rows) > 8 else ''}, "
                    f"counting the header as row 1). A blank cell is not a "
                    f"replicate id: either {rep_col!r} is not the replicate "
                    f"column, or those rows belong to a replicate the file does "
                    f"not name. Map a different column, set replicate_column to "
                    f"null, or flag the rows — the engine never guesses a group"
                )
        if rep_ids is not None:
            provenance[-1]["replicate_labels"] = {str(k): v for k, v in rep_ids.items()}
        times = _numeric_cells(df, m["time_column"], fname, "time")
        values = _numeric_cells(df, m["value_column"], fname, "value")
        sigmas = _numeric_cells(df, err_col, fname, "error") if err_col else None
        for pos, (_, row) in enumerate(df.iterrows()):
            cond_vals = {c: format_value(row[c]) for c in m["condition_columns"]}
            try:
                label = m["condition_label_template"].format(**cond_vals)
            except KeyError as e:
                raise ModuleFailure(
                    f"condition_label_template {m['condition_label_template']!r} "
                    f"references unknown column {e}"
                ) from e
            entry = {
                "observable_label": (
                    format_value(row[obs_col]) if obs_col else m["observable_label"]
                ),
                "condition_label": label,
                "condition_key": condition_key(cond_vals),
                "time": times[pos],
                "value": values[pos],
                "replicate": (
                    rep_ids[row[m["replicate_column"]]] if rep_ids is not None else 1
                ),
            }
            if sigmas is not None:
                sig = sigmas[pos]
                if not np.isfinite(sig) or sig <= 0:
                    raise ModuleFailure(
                        f"file {fname}: error column {err_col!r} holds "
                        f"{row[err_col]!r} in a row of {entry['observable_label']} "
                        f"at t={entry['time']:g} — a fixed sigma must be a finite "
                        f"positive number; fix the file, map another column, or "
                        f"drop `error_column`"
                    )
                entry["sigma"] = sig
            rows.append(entry)
    if not rows:
        raise ModuleFailure("mappings produced zero measurement rows")
    return pd.DataFrame(rows), provenance


def _numeric_cells(df: pd.DataFrame, column: str, fname: str, role: str) -> list:
    """`column` as floats, a blank cell as NaN (the rows check reports it).

    A cell that holds text (`<LOD`, `n.d.`, `0h`) is refused by name, with its
    rows: the engine never reads text as a number, so the file or the mapping
    has to change, and a bare conversion error would recur on every resume.
    """
    out: list = []
    bad: list[tuple[int, object]] = []
    for i, cell in enumerate(df[column]):
        if pd.isna(cell):
            out.append(float("nan"))
            continue
        try:
            out.append(float(cell))
        except (TypeError, ValueError):
            bad.append((i + 2, cell))
            out.append(float("nan"))
    if bad:
        rows = [r for r, _ in bad]
        cells = list(dict.fromkeys(repr(c) for _, c in bad))
        raise ModuleFailure(
            f"file {fname}: {role} column {column!r} holds text where a number "
            f"belongs in {len(bad)} of {len(df)} rows (file rows "
            f"{rows[:8]}{', …' if len(rows) > 8 else ''}, counting the header as "
            f"row 1): {', '.join(cells[:4])}. The engine never reads text as a "
            f"number. If the text marks a value below a detection floor, declare "
            f"the floor in `below_detection` and give the file a number or a "
            f"blank there; otherwise map another column, or clean the file"
            + (
                ". A measurement taken at steady state rather than at a sampled "
                "time has the time `inf` (PEtab's convention): the file says so "
                "with `inf` in that cell"
                if role == "time"
                else ""
            )
        )
    return out


def _replicate_ids(df: pd.DataFrame, column: str | None) -> dict | None:
    """label -> integer replicate id for one mapping, or None without a
    replicate column. Integer-like labels (1, 2.0, "3") keep their own number;
    any other label set is numbered 1..n in sorted string order."""
    if not column:
        return None
    labels = list(pd.unique(df[column].dropna()))
    out: dict = {}
    try:
        for lab in labels:
            as_float = float(lab)
            if as_float != int(as_float):
                raise ValueError(lab)
            out[lab] = int(as_float)
        return out
    except (TypeError, ValueError):
        pass
    for i, lab in enumerate(sorted(labels, key=str), start=1):
        out[lab] = i
    return out


# ---------------------------------------------------------------- gates


def make_data_gates(long_df: pd.DataFrame, report: dict, ctx: RunContext) -> list:

    @gate("data_rows_well_formed", "T0")
    def g_rows():
        problems = []
        # `inf` is PEtab's steady-state measurement (the model's steady state
        # under that condition, which AMICI post-equilibrates to); `-inf` and
        # anything non-numeric are not measurement times
        times = pd.to_numeric(long_df["time"], errors="coerce").to_numpy(dtype=float)
        n_steady = int(np.isposinf(times).sum())
        if np.isnan(times).any():
            problems.append("non-numeric or non-finite times")
        if np.isneginf(times).any():
            problems.append(
                f"time -inf in {int(np.isneginf(times).sum())} row(s): a "
                f"steady-state measurement is time inf, and nothing is measured "
                f"at -inf"
            )
        if (np.isfinite(times) & (times < 0)).any():
            problems.append("negative time points")
        if long_df["value"].isna().any():
            problems.append("missing measurement values")
        dup = long_df.duplicated(
            subset=["observable_label", "condition_label", "time", "replicate"]
        )
        if dup.any():
            problems.append(
                f"{int(dup.sum())} duplicate "
                f"(observable, condition, time, replicate) keys"
            )
        # label <-> key must be 1:1: a label covering several keys means the
        # template dropped a condition column (distinct experiments silently
        # merged); one key under several labels would split one experimental
        # condition into several PEtab conditions.
        per_label = long_df.groupby("condition_label")["condition_key"].nunique()
        if (per_label > 1).any():
            problems.append(
                f"label(s) {sorted(per_label[per_label > 1].index)} each cover "
                f"several distinct condition keys — the label template drops a "
                f"condition column"
            )
        per_key = long_df.groupby("condition_key")["condition_label"].nunique()
        if (per_key > 1).any():
            problems.append(
                f"condition key(s) {sorted(per_key[per_key > 1].index)} appear "
                f"under several labels — one condition would become several "
                f"PEtab conditions"
            )
        if problems:
            return GateResult(
                "data_rows_well_formed", "T0", False, detail=" | ".join(problems)
            )
        return GateResult(
            "data_rows_well_formed",
            "T0",
            True,
            detail=f"{len(long_df)} rows, keys unique, times finite"
            + (f" or inf ({n_steady} steady-state row(s))" if n_steady else ""),
        )

    @gate("data_units_and_error_declared", "T0")
    def g_units():
        """SEM-recorded-as-SD is a silent 1/sqrt(n) error in every likelihood
        weight; undeclared units are the ancestor of every scaling bug. Both
        must be declared, even as 'arbitrary'/'replicates'."""
        problems = []
        labels_present = set(long_df["observable_label"])
        declared = {o["label"]: o for o in report.get("observable_labels", [])}
        for label in sorted(labels_present):
            if label not in declared:
                if report.get("mappings"):
                    problems.append(f"observable label {label!r} has no declaration")
                continue
            o = declared[label]
            if not o.get("units"):
                problems.append(f"{label}: units undeclared (say 'arbitrary' if so)")
            if o.get("error_type") not in ("sd", "sem", "replicates", "none", "column"):
                problems.append(f"{label}: error_type undeclared or invalid")
            # `column` means "a per-row sigma came with the data": then the rows
            # must actually carry it, and rows that carry one must say so
            has_sigma = "sigma" in long_df.columns and bool(
                long_df.loc[long_df["observable_label"].astype(str) == label, "sigma"]
                .notna()
                .all()
            )
            if o.get("error_type") == "column" and not has_sigma:
                problems.append(
                    f"{label}: error_type 'column' but no mapping declares an "
                    f"`error_column` covering its rows"
                )
            if has_sigma and o.get("error_type") != "column":
                problems.append(
                    f"{label}: rows carry a per-row sigma (error_column) but "
                    f"error_type is {o.get('error_type')!r} — declare 'column'"
                )
        # a below-detection declaration must name a declared label and a legal
        # rule, or it goes back to the agent
        from octomod.workflow_modules.data import censoring as _cen

        problems += _cen.problems(
            (report or {}).get("below_detection") or [], declared.keys()
        )
        if problems:
            return GateResult(
                "data_units_and_error_declared",
                "T0",
                False,
                detail=" | ".join(problems),
            )
        n_cen = len(_cen.declared(report))
        return GateResult(
            "data_units_and_error_declared",
            "T0",
            True,
            detail="units and error type declared for every observable"
            + (
                f"; {n_cen} below-detection declaration(s) well-formed" if n_cen else ""
            ),
        )

    @gate("data_holdout_labels_resolve", "T0")
    def g_holdout():
        """The held-out conditions are part of the evaluation contract, fixed
        at staging time in the data's own column vocabulary. Matching is
        semantic (parsed column=value keys) — never against display labels,
        which are the agent's to style. Drift is still a hard stop."""
        holdout = ctx.testcase.get("holdout", {}).get("condition_labels", [])
        labels = set(long_df["condition_label"])
        keys = set(long_df["condition_key"])
        unresolved, resolved = [], []
        for h in holdout:
            k = parse_declared_label(h)
            if h in labels or (k and k in keys):
                resolved.append(f"{h!r} -> {k or h!r}")
            else:
                unresolved.append(f"{h!r} (parsed {k!r})")
        if unresolved:
            return GateResult(
                "data_holdout_labels_resolve",
                "T0",
                False,
                detail=f"holdout {unresolved} matches no extracted condition; "
                f"condition keys present: {sorted(keys)} — declare "
                f"holdout as column=value pairs in the data's own "
                f"column names",
            )
        return GateResult(
            "data_holdout_labels_resolve",
            "T0",
            True,
            detail=f"holdout resolves: {resolved or '(none declared)'}",
        )

    @gate("data_processing_legal", "T0")
    def g_processing():
        """Every declared processing op is in the closed vocabulary, names
        labels the table has, and reads no held-out cell. Executed before the
        battery; re-validated here so the verdict is among the gates like any other."""
        from octomod.workflow_modules.data import data_processing as _dp

        ops = report.get("processing_declared") or []
        try:
            _dp.validate(
                ops,
                long_df,
                ctx.testcase.get("holdout", {}).get("condition_labels", []),
            )
        except _dp.ProcessingRefused as e:
            return GateResult("data_processing_legal", "T0", False, detail=str(e))
        return GateResult(
            "data_processing_legal",
            "T0",
            True,
            value=len(ops),
            detail=(
                f"{len(ops)} declared processing op(s), all in the vocabulary and "
                f"reading no held-out cell"
                if ops
                else "no processing declared"
            ),
        )

    @gate("data_plausibility_screen", "T2")
    def g_screen():
        """Advisory: negatives, constant series, extreme outliers — recorded
        as findings, never silently fixed."""
        findings = []
        for (obs, cond), grp in long_df.groupby(
            ["observable_label", "condition_label"]
        ):
            vals = grp["value"].to_numpy()
            if (vals < 0).any():
                findings.append(f"{obs}@{cond}: {(vals < 0).sum()} negative values")
            if len(vals) > 2 and np.ptp(vals) == 0:
                findings.append(f"{obs}@{cond}: series constant to machine precision")
        # what the source did below its detection floor, with the rows it
        # touches: a finding the reader sees, never a value the engine changes
        from octomod.workflow_modules.data import censoring as _cen

        recorded = (report or {}).get("below_detection_summary")
        findings += _cen.findings(
            recorded
            if recorded
            else _cen.summary(
                _cen.declared(report), long_df, counted_on="the table this gate checks"
            )
        )
        return GateResult(
            "data_plausibility_screen",
            "T2",
            True,
            blocking=False,
            value=len(findings),
            detail="; ".join(findings) or "no findings",
            advisory_findings=findings,
        )

    return [g_rows, g_units, g_holdout, g_processing, g_screen]
