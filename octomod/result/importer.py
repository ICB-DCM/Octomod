"""LEGACY: transcribe a run DIRECTORY into a run record.

A legacy run is a directory of files (`runs/<id>/round_0/petab/
measurements.tsv`, `…/gates/s6.pass`, `ledger.jsonl`). The engine's only
store is the record — the run is `runs/<id>.h5`, addressed by record key —
and nothing in the engine knows the directory's file names. This module is
the one place that does, as the bridge for runs kept as directories:

    ./run.sh import-legacy --run-dir runs/<old>/ [--run-id <id>]

It is a TRANSCRIPTION, not a reconstruction: every file the directory holds
is written, through its codec, to the record key the engine writes that
artifact to today (`LEGACY_NAMES`), so an imported run and a run the engine
made are the same shape and every reader reads both. pyPESTO's
`optimize_result.h5` becomes the candidate's `multistart` arrays; rendered
HTML is copied to `runs/<id>_reports/`. What the engine derives while it runs
— the outcome from the `run_end` row, each round's slot state — is derived
here the same way. Files the table does not know are listed, not guessed at.
Of the directory's `input/` folder, which holds the whole staged case, the
record keeps what a run reads (`run_folder.inputs_read`), as a snapshot does;
the rest is listed as skipped.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from octomod.result.node import Node
from octomod.result.runstore import RunStore

_RK = "rounds/{round}"
_WK = "rounds/{round}/candidates/{cid}"  # {cid} = the candidate id or `_single`

# (legacy file name, record key, codec). Tokens: {round} (`round_<k>`), {cid}
# (a candidate id), {name}, {role}, {n}. Codecs: json · text · yaml · tsv ·
# csv (tables) · bytes (opaque) · ledger · pypesto (pyPESTO's HDF5 →
# arrays) · render (HTML, copied to the reports directory) · skip.
_RUN_AND_ROUND: list[tuple[str, str, str]] = [
    # ---------------------------------------------------------------- run
    ("run_meta.json", "run", "json"),
    ("intent.json", "intent", "json"),
    ("ledger.jsonl", "ledger", "ledger"),
    ("PENDING_GATE.json", "pending_gate", "json"),
    ("history.json", "history", "json"),
    ("open_questions.json", "questions", "json"),
    ("pending_questions.json", "pending_questions", "json"),
    ("supplied_literature.json", "supplied_literature", "json"),
    ("tried_models_snapshot.json", "tried_log_snapshot", "json"),
    ("analysis_report.json", "analysis", "json"),
    ("ANALYSIS.md", "ANALYSIS.md", "render"),
    ("ANALYSIS.html", "ANALYSIS.html", "render"),
    ("result.h5", "", "skip"),  # a copy rebuilt from the files: they are the source
    # the run folder's input snapshot and fit index
    ("input/source.json", "input_source", "json"),
    # the input snapshot, nested folders included, stored as the snapshot
    # stores it: text where it decodes, bytes otherwise. Only what a run
    # reads (`run_folder.inputs_read`) reaches this row; `import_run` skips
    # the rest of the folder
    ("input/{path}", "input/{path}", "input"),
    ("fit_index.json", "fit_index", "json"),
    # the slot state is computed from the markers, never copied
    ("{round}/round_status.json", "", "skip"),
    # -------------------------------------------------------------- round
    ("{round}/DIRECTIVE.txt", f"{_RK}/directive", "text"),
    ("{round}/candidates.json", f"{_RK}/space/candidates", "json"),
    ("{round}/assembly_shared.json", f"{_RK}/shared_assembly", "json"),
    ("{round}/cost_boundary.json", f"{_RK}/decisions/assembly_cost_boundary", "json"),
    ("{round}/expansion.json", f"{_RK}/expansion", "json"),
    ("{round}/expansion_offer.json", f"{_RK}/expansion_offer", "json"),
    ("{round}/expansion_diagnostics.json", f"{_RK}/expansion_diagnostics", "json"),
    ("{round}/revision.json", f"{_RK}/revision", "json"),
    (
        "{round}/interpretation_diagnostics.json",
        f"{_RK}/interpretation_diagnostics",
        "json",
    ),
    ("{round}/decisions.md", f"{_RK}/decisions_md", "text"),
    ("{round}/model/model_space.json", f"{_RK}/space/axes", "json"),
    ("{round}/model/declared_axes.json", f"{_RK}/space/declared", "json"),
    ("{round}/model/dropped_axes.json", f"{_RK}/space/dropped", "json"),
    ("{round}/model/recommended_tier.json", f"{_RK}/space/recommended_tier", "json"),
    ("{round}/model/scope_gate.json", f"{_RK}/decisions/model_scope", "json"),
    ("{round}/model/petab_select/selection.json", f"{_RK}/selection", "json"),
    ("{round}/model/petab_select/{name}", f"{_RK}/selection_files/{{name}}", "text"),
    ("{round}/data/measurements_long.tsv", f"{_RK}/data/measurements", "tsv"),
    ("{round}/data/measurements_raw.tsv", f"{_RK}/data/raw", "tsv"),
    ("{round}/data/data_report.json", f"{_RK}/data/report", "json"),
    ("{round}/data/data_signals.json", f"{_RK}/data/signals", "json"),
    ("{round}/data/design_summary.json", f"{_RK}/data/design_summary", "json"),
    ("{round}/evidence/evidence.json", f"{_RK}/evidence", "json"),
    ("{round}/evidence/supplied.json", f"{_RK}/supplied_evidence", "json"),
    ("{round}/evidence/reactions.json", f"{_RK}/reaction_evidence", "json"),
    # a reaction set construction could not leave: a design this engine no
    # longer has, so its three artifacts have no key to go to
    ("{round}/model/reaction_set.json", "", "skip"),  # the set itself
    ("{round}/evidence/reaction_decisions.json", "", "skip"),  # answers at its gate
    ("{round}/agent_io/construction_reactions.sha", "", "skip"),  # its staleness key
    ("{round}/evidence/sources/{name}", f"{_RK}/evidence_sources/{{name}}", "bytes"),
    (
        "{round}/agent_io/{role}_prompt.txt",
        f"{_RK}/agent_calls/{{role}}/prompt",
        "text",
    ),
    (
        "{round}/agent_io/{role}_prompt_bytes.json",
        f"{_RK}/agent_calls/{{role}}/prompt_budget",
        "json",
    ),
    (
        "{round}/agent_io/{role}_attempts.json",
        f"{_RK}/agent_calls/{{role}}/dossier",
        "json",
    ),
    (
        "{round}/agent_io/{role}_fallback_applied.json",
        f"{_RK}/agent_calls/{{role}}/fallback_applied",
        "json",
    ),
    (
        "{round}/agent_io/{role}_attempt{n}_partial.txt",
        f"{_RK}/agent_calls/{{role}}/replies/{{n}}/partial",
        "text",
    ),
    (
        "{round}/agent_io/{role}_attempt{n}_stderr.txt",
        f"{_RK}/agent_calls/{{role}}/replies/{{n}}/stderr",
        "text",
    ),
    (
        "{round}/agent_io/{role}_attempt{n}_timeout.json",
        f"{_RK}/agent_calls/{{role}}/replies/{{n}}/timeout",
        "json",
    ),
    (
        "{round}/agent_io/{role}_attempt{n}.txt",
        f"{_RK}/agent_calls/{{role}}/replies/{{n}}/text",
        "text",
    ),
    (
        "{round}/agent_io/{role}_base.sha",
        f"{_RK}/agent_calls/{{role}}/base_key",
        "text",
    ),
    (
        "{round}/agent_io/assembly_verification_overlay/{name}.json",
        f"{_RK}/agent_calls/assembly_verification/overlay_audits/{{name}}",
        "json",
    ),
    ("{round}/agent_io/{role}.json", f"{_RK}/agent_calls/{{role}}/reply", "json"),
    ("{round}/report/report_core.json", f"{_RK}/evaluation_core", "json"),
    ("{round}/report/report.json", f"{_RK}/evaluation", "json"),
    ("{round}/report/attribution.json", f"{_RK}/attribution", "json"),
    ("{round}/report/report.md", f"{_RK}/report_md", "text"),
    ("{round}/report/verdict.json", f"{_RK}/decisions/evaluation_verdict", "json"),
    (
        "{round}/report/profiling_gate.json",
        f"{_RK}/decisions/evaluation_profile",
        "json",
    ),
    (
        "{round}/report/profiles_decision.json",
        f"{_RK}/decisions/evaluation_profile_request",
        "profile_request",
    ),
    (
        "{round}/report/profiles_timing.json",
        f"{_RK}/candidates/_single/profiles_timing",
        "json",
    ),
    ("{round}/estimation_settings.json", f"{_RK}/estimation_settings", "json"),
    ("{round}/report/residual_forms.json", f"{_RK}/residual_forms", "json"),
    ("{round}/model/base_gate.json", f"{_RK}/decisions/model_base", "json"),
    ("{round}/model/base/model.ant", f"{_RK}/base_model/antimony", "text"),
    ("{round}/model/base/model.xml", f"{_RK}/base_model/sbml", "text"),
    ("{round}/model/base/parameters.json", f"{_RK}/base_model/parameters", "json"),
    ("{round}/model/base/entity_glossary.json", f"{_RK}/base_model/glossary", "json"),
    ("{round}/model/search_mode.json", f"{_RK}/space/search_mode", "json"),
    ("{round}/seed.json", f"{_RK}/model/seed", "json"),
    ("{round}/data/data_phenomenology.json", f"{_RK}/data/phenomenology", "json"),
    (
        "{round}/data/data_phenomenology_raw.json",
        "phenomenology_raw",
        "json",
    ),
    ("{round}/evidence/expansion_evidence.json", f"{_RK}/expansion_evidence", "json"),
    (
        "{round}/evidence/expansion_research_{n}.json",
        f"{_RK}/research_requests/{{n}}",
        "json",
    ),
    ("{round}/compile_feedback.json", f"{_RK}/compile_feedback", "json"),
    (
        "{round}/evidence/knowledge_search_{n}.json",
        f"{_RK}/knowledge_search/{{n}}",
        "json",
    ),
    ("{round}/evidence/knowledge_admitted.json", f"{_RK}/knowledge_admitted", "json"),
    ("{round}/model/support_floor.json", f"{_RK}/space/floor", "json"),
    ("{round}/model/axis_refused.json", f"{_RK}/axis_refused", "json"),
    (
        "{round}/agent_io/interpretation.pinned.json",
        f"{_RK}/agent_calls/interpretation/pinned",
        "json",
    ),
    (
        "{round}/_superseded/{path}",
        "",
        "skip",
    ),  # set aside by a re-entry, at any depth; not the run's state
    ("{round}/report/{name}.html", "{round}/report/{name}.html", "render"),
    ("{round}/report/{name}.png", "{round}/report/{name}.png", "render"),
    # round-level model (the base of a candidate set, or the single model)
    ("{round}/model/model.ant", f"{_RK}/model/antimony", "text"),
    ("{round}/model/model.xml", f"{_RK}/model/sbml", "text"),
    ("{round}/model/model.mmd", f"{_RK}/model/mermaid", "text"),
    ("{round}/model/parameters.json", f"{_RK}/model/parameters", "json"),
    ("{round}/model/network.json", f"{_RK}/model/network", "json"),
    ("{round}/model/entity_glossary.json", f"{_RK}/model/glossary", "json"),
    ("{round}/model/build_report.json", f"{_RK}/model/build_report", "json"),
    ("{round}/model/encoding.json", f"{_RK}/model/encoding", "json"),
    ("{round}/model/SEED.json", f"{_RK}/model/seed", "json"),
    ("{round}/gates/{name}.pass", f"{_RK}/status/markers/{{name}}", "json"),
    ("{round}/gates/{name}.json", f"{_RK}/gates/{{name}}", "json"),
]

# a candidate's workdir (`cand_<id>/`); the single-model round holds the same
# files directly under `round_k/` (the rows are generated from these)
_WORKDIR: list[tuple[str, str, str]] = [
    ("model/model.ant", "model/antimony", "text"),
    ("model/model.xml", "model/sbml", "text"),
    ("model/model.mmd", "model/mermaid", "text"),
    ("model/parameters.json", "model/parameters", "json"),
    ("model/network.json", "model/network", "json"),
    ("model/entity_glossary.json", "model/glossary", "json"),
    ("model/build_report.json", "model/build_report", "json"),
    ("model/encoding.json", "model/encoding", "json"),
    ("model/assembly_overlay.json", "model/assembly_overlay", "json"),
    ("gates/{name}.pass", "markers/{name}", "json"),
    ("gates/{name}.json", "gates/{name}", "json"),
    ("petab/problem.yaml", "petab/problem_yaml", "yaml"),
    ("petab/model.xml", "petab/sbml", "text"),
    ("petab/{name}.sbml", "petab/sbml", "text"),
    ("petab/assembly.json", "assembly", "json"),
    ("petab/assembly_overlay_applied.json", "assembly_overlay_applied", "json"),
    ("petab/cost_boundary.json", "decisions/cost_boundary", "json"),
    ("petab/{name}.tsv", "petab/{name}", "tsv"),
    ("estimation/result_summary.json", "estimation", "json"),
    ("estimation/starts.csv", "starts", "csv"),
    ("estimation/cost_profile.json", "cost", "json"),
    ("estimation/optimize_result.h5", "multistart", "pypesto"),
    ("estimation/convergence_gate.json", "decisions/estimation_convergence", "json"),
    ("estimation/optimizer_comparison.json", "optimizer_comparison", "json"),
    ("estimation/optimizer_selection.json", "optimizer_selection", "json"),
    ("estimation/optimizer_compare_runs.json", "optimizer_compare_runs", "json"),
    ("estimation/attempt_{n}/result_summary.json", "attempts/{n}/estimation", "json"),
    ("estimation/attempt_{n}/starts.csv", "attempts/{n}/starts", "csv"),
    ("estimation/attempt_{n}/optimize_result.h5", "attempts/{n}/multistart", "pypesto"),
    ("refit.json", "refit", "json"),
    ("estimation/estimation_settings.json", "estimation_settings", "json"),
    ("estimation/probe_record.json", "probe_record", "json"),
    ("estimation/fit_key.json", "fit_key", "json"),
    ("estimation/profiles.json", "profiles", "json"),
    ("estimation/profiles_timing.json", "profiles_timing", "json"),
    ("estimation/structural_nulls.json", "structural_nulls", "json"),
    ("estimation/structural_nulls_at_mle.json", "structural_nulls_at_mle", "json"),
    ("estimation/budget_declined.json", "budget_declined", "json"),
]


def _legacy_names() -> list[tuple[str, str, str]]:
    """The whole table. Round-level rows first: in a single-model round
    `round_k/model/model.xml` is the ROUND's model and `round_k/gates/` the
    round's gates, exactly where the engine keeps them today."""
    rows = list(_RUN_AND_ROUND)
    for name, key, codec in _WORKDIR:
        rows.append((f"{{round}}/cand_{{cid}}/{name}", f"{_WK}/{key}", codec))
    for name, key, codec in _WORKDIR:
        rows.append(
            (f"{{round}}/{name}", f"{_WK.replace('{cid}', '_single')}/{key}", codec)
        )
    return rows


LEGACY_NAMES = _legacy_names()

_TOKEN = {
    "round": r"(?P<round>round_\d+)",
    "cid": r"(?P<cid>[^/]+?)",
    "name": r"(?P<name>[^/]+)",
    "role": r"(?P<role>[a-z][a-z0-9_]*?)",
    "n": r"(?P<n>\d+)",
    "path": r"(?P<path>.+)",
}


def _compile(pattern: str) -> re.Pattern:
    out = re.escape(pattern)
    for tok, rx in _TOKEN.items():
        out = out.replace(re.escape("{" + tok + "}"), rx)
    return re.compile("^" + out + "$")


_COMPILED = [(_compile(p), k, c) for p, k, c in LEGACY_NAMES]


def resolve(rel: str) -> tuple[str, str] | None:
    """(record key, codec) for a legacy run-relative file name, or None."""
    for rx, key_t, codec in _COMPILED:
        m = rx.match(rel)
        if m:
            k = key_t
            for tok, val in m.groupdict().items():
                k = k.replace("{" + tok + "}", val)
            return k, codec
    return None


# ------------------------------------------------------------- transcribe


@dataclass
class ImportReport:
    path: Path
    written: int = 0
    rendered: int = 0
    skipped: list[str] = field(default_factory=list)  # known, deliberately not
    unknown: list[str] = field(default_factory=list)  # not in the table
    failed: list[str] = field(default_factory=list)  # in the table, unreadable


# Never transcribed outside `input/`: build detritus, a cross-run archive
# (`tried_models.json`, which lives beside a case, never in a run), and a
# provenance file other than `input/source.json`, the one the table maps.
_DETRITUS = frozenset({".DS_Store", "tried_models.json", "source.json"})


def import_run(run_dir: Path, store: RunStore) -> ImportReport:
    """Transcribe `run_dir` into the (new, absent) record file of `store`."""
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"{run_dir} is not a directory")
    if store.exists_on_disk():
        raise FileExistsError(store.path)
    store.create()
    root = Node(store)
    rep = ImportReport(path=store.path)
    from octomod.orchestration import run_folder

    source_rel = f"{run_folder.INPUT_DIRNAME}/{run_folder.SOURCE_FILE}"
    # a legacy folder's `input/` holds the whole staged case; the record keeps
    # what a run reads of it, as a snapshot does
    inputs = run_dir / run_folder.INPUT_DIRNAME
    read = {
        f"{run_folder.INPUT_DIRNAME}/{r.as_posix()}"
        for r in (run_folder.inputs_read(inputs) if inputs.is_dir() else [])
    }
    for p in sorted(q for q in run_dir.rglob("*") if q.is_file()):
        rel = p.relative_to(run_dir).as_posix()
        parts = p.relative_to(run_dir).parts
        if parts[0] == run_folder.INPUT_DIRNAME and rel != source_rel:
            if rel not in read:
                rep.skipped.append(rel)
                continue
        elif p.name in _DETRITUS and rel != source_rel:
            rep.skipped.append(rel)
            continue
        hit = resolve(rel)
        if hit is None:
            rep.unknown.append(rel)
            continue
        key, codec = hit
        if codec == "skip":
            rep.skipped.append(rel)
            continue
        try:
            if codec == "render":
                dst = store.reports_dir / key
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dst)
                rep.rendered += 1
                continue
            _write(root / key, codec, p, store)
            rep.written += 1
        except Exception as e:  # noqa: BLE001 - one bad file is a finding
            rep.failed.append(f"{rel}: {type(e).__name__}: {str(e)[:120]}")
    _derive(root)
    return rep


def _write(n: Node, codec: str, p: Path, store: RunStore) -> None:
    import pandas as pd
    import yaml

    if codec == "json":
        n.put(json.loads(p.read_text() or "{}"))
    elif codec == "text":
        n.put_text(p.read_text())
    elif codec == "yaml":
        n.put(yaml.safe_load(p.read_text()) or {})
    elif codec == "profile_request":
        # the human's profile request was written without the decision
        # record's `module`; every decision in the record carries one
        d = json.loads(p.read_text() or "{}")
        d.setdefault("module", "evaluation_profiling_gate")
        n.put(d)
    elif codec in ("tsv", "csv"):
        n.put_table(pd.read_csv(p, sep="\t" if codec == "tsv" else ","))
    elif codec == "bytes":
        n.put_blob(p.read_bytes())
    elif codec == "input":
        from octomod.orchestration import run_folder

        data = p.read_bytes()
        if p.suffix.lower() in run_folder.TEXT_SUFFIXES and b"\x00" not in data:
            try:
                n.put_text(data.decode("utf-8"))
                return
            except UnicodeDecodeError:
                pass
        n.put_blob(data)
    elif codec == "ledger":
        rows = []
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"ts": "", "event": "unparseable", "raw": line})
        store.replace_ledger(rows)
    elif codec == "pypesto":
        import pypesto.store

        from octomod.workflow_modules.estimation.problem import write_optimize_result

        res = pypesto.store.read_result(
            str(p), problem=False, optimize=True, with_history=False
        )
        write_optimize_result(res, n)
    else:  # pragma: no cover - the table names only the codecs above
        raise ValueError(f"unknown codec {codec!r}")


def _derive(root: Node) -> None:
    """What the engine writes as it runs and a directory never held: the
    outcome (from the last `run_end` row) and each round's slot state."""
    from octomod.orchestration import round_status
    from octomod.result import node as tree
    from octomod.result.model import RunOutcome

    store = root.store
    rows = store.ledger_rows()
    end = next((r for r in reversed(rows) if r.get("event") == "run_end"), None)
    if end:
        (root / "outcome").put(
            RunOutcome(
                outcome=end.get("outcome"),
                reason=end.get("reason"),
                winner=end.get("winner"),
                decisive=end.get("decisive"),
                at=end.get("ts"),
                final_round=end.get("round"),
            ).model_dump(exclude_none=True)
        )
    for k in tree.round_indices(root):
        rnd = tree.round_node(root, k)
        try:
            state = round_status.slot_state(rnd)
        except Exception as e:  # noqa: BLE001 - a reading aid, never a failure
            print(f"  (slot state of {rnd.name} not derived: {e})", file=sys.stderr)
            continue
        (rnd / "status/slots").put(state["slots"])
        (rnd / "status/candidates").put(state["candidates"])
