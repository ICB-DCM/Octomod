"""The token-free battery: every suite once, in parallel.

    uv run python tests/run_all.py                    # every suite
    uv run python tests/run_all.py --group literature # one group (what a CI job runs)
    uv run python tests/run_all.py golden search      # a named subset
    uv run python tests/run_all.py --serial           # one at a time (for debugging)
    uv run python tests/run_all.py --jobs 4           # concurrency (default: cores/2)

Every suite is a stub-backend run of the real engine in its own subprocess with
its own run ids, so suites run concurrently; wall time is the slowest suite.

Each suite runs at the effort its assertions need. The PLUMBING suites (gate
sequences, resume idempotency, entry validation, the record) run under the
reduced-effort overlay workflows/overlays/quick.yaml (fewer starts and
samples): they assert protocol, which does not become truer with more starts.
The suites in `FULL_EFFORT` run at workflows/default.yaml: the SCIENTIFIC
assertions (parameter recovery and CI coverage, held-out rejection, mechanism
discrimination and selection, expansion recovery), and the few that skip a
step under the overlay. The overlay touches effort only and is hashed into each
run's workflow_sha, so no pass criterion is relaxed.

In parallel, suites start longest first, by each suite's time in the last
battery (`.battery_durations.json`, gitignored); a suite with no recorded time
starts first when it runs at full effort, last otherwise.

Every suite belongs to one group (`GROUPS`: the step or part of the engine it
tests). CI runs each group as its own job, from `--list-groups`, so the groups
run side by side.

After a suite exits, the records it left are read for what the engine's own
completeness checks found missing (`octomod/result/completeness.py`); a gap
fails the suite, unless `RECORD_GAPS_ALLOWED` names it with a reason.

Each suite writes to its own `test_runs/<suite>` (OCTOMOD_RUNS_DIR), removed on
OK and kept on FAIL (`--keep-runs` keeps all); the user's `runs/` is checked around
the whole battery, and any change to its directory set fails it.

`tests/amici_cache_lock_unit.py` is deliberately not a suite: it deletes a cold
AMICI cache key, so run it on its own when the compile path changes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# the reduced-effort overlay every suite outside FULL_EFFORT runs under
REDUCED_OVERLAY = REPO / "workflows" / "overlays" / "quick.yaml"
# the battery's own runs directory: gitignored, and never `runs/`
TEST_RUNS = REPO / "test_runs"
USER_RUNS = REPO / "runs"
# each suite's wall time in the last battery that ran it (gitignored): the
# parallel battery starts the longest suites first, so the slowest one is not
# the last to start. Outside test_runs/, which holds only kept runs.
DURATIONS = REPO / ".battery_durations.json"
# A suite whose FIXTURE is absent exits with this and prints one `SKIP: <reason>`
# line: an absent fixture is "cannot run here", not "is broken".
SKIP_EXIT = 77

# name -> argv (relative to the repo root). Order is the serial/fallback order:
# cheap and broad first, so a plumbing break shows up before a 200 s suite.
SUITES: dict[str, list[str]] = {
    "units": ["tests/assembly_axes_unit.py"],
    "datadir": ["tests/data_dir_guard_unit.py"],
    "forms": ["tests/residual_form_unit.py"],
    "curveforms": ["tests/curve_forms_unit.py"],
    "tiers": ["tests/tier_unit.py"],
    "redraft_unit": ["tests/redraft_unit.py"],
    "constreuse": ["tests/construction_reuse_unit.py"],
    "skipprof": ["tests/skip_profiles_unit.py"],
    "appendspecies": ["tests/append_species_unit.py"],
    "noopaxis": ["tests/noop_axis_unit.py"],
    "humanaxes": ["tests/human_axes_unit.py"],
    "canddetail": ["tests/candidate_detail_unit.py"],
    "acceptedentry": ["tests/accepted_entry_unit.py"],
    "resumablestop": ["tests/resumable_stop_unit.py"],
    "carryundecided": ["tests/carry_undecided_unit.py"],
    "baseoverlay": ["tests/base_overlay_unit.py"],
    "lineagecarry": ["tests/lineage_carry_unit.py"],
    "glossary": ["tests/glossary_unit.py"],
    "structure": ["tests/structure_unit.py"],
    "budget": ["tests/report_budget_unit.py"],
    "runid": ["tests/run_id_unit.py"],
    "runfolder": ["tests/run_folder_unit.py"],
    "inputsread": ["tests/inputs_read_unit.py"],
    "lb3": ["tests/live_blind_3_unit.py"],
    "longformat": ["tests/long_format_population_unit.py"],
    "reuse": ["tests/reuse_unit.py"],
    "roundseed": ["tests/round_seed_unit.py"],
    "gatenote": ["tests/gate_note_unit.py"],
    "estsettings": ["tests/estimation_settings_unit.py"],
    "searchmode": ["tests/search_mode_unit.py"],
    "tried": ["tests/tried_models_unit.py"],
    "constants": ["tests/declared_constants_unit.py"],
    "ident": ["tests/identifiability_unit.py"],
    "obsev": ["tests/observation_evidence_unit.py"],
    "compar": ["tests/comparability_unit.py"],
    "policy_unit": ["tests/policy_unit.py"],
    "compile_cache": ["tests/compile_cache_unit.py"],
    "optcompare": ["tests/optimizer_compare_unit.py"],
    "supermodel": ["tests/supermodel_unit.py"],
    "axispatch": ["tests/axis_patch_unit.py"],
    "gatebind": ["tests/gate_binding_unit.py"],
    "attribution": ["tests/attribution_unit.py"],
    "formulasafe": ["tests/formula_safe_unit.py"],
    "undecided": ["tests/undecided_unit.py"],
    "hierarchical": ["tests/hierarchical_unit.py"],
    "laplace": ["tests/laplace_noise_unit.py"],
    "probereuse": ["tests/cost_probe_reuse_unit.py"],
    "budgetdecline": ["tests/budget_decline_remembered_unit.py"],
    "fitband": ["tests/fit_band_unit.py"],
    "noisefloor": ["tests/noise_floor_unit.py"],
    "percondsigma": ["tests/per_condition_sigma_unit.py"],
    "reentry": ["tests/reentry_invalidation_unit.py"],
    "adjoint": ["tests/adjoint_reprobe_unit.py"],
    "promptcache": ["tests/prompt_cache_unit.py"],
    "timeforcing": ["tests/time_forcing_unit.py"],
    "cbredraft": ["tests/cost_boundary_redraft_smoke.py"],
    "signals": ["tests/data_signals_unit.py"],
    "prompts": ["tests/prompt_budget_unit.py"],
    "expandoffer": ["tests/expansion_offer_unit.py"],
    "dotlabel": ["tests/dot_label_unit.py"],
    "provenance": ["tests/provenance_unit.py"],
    "agenttiming": ["tests/agent_timing_unit.py"],
    "noteforms": ["tests/note_forms_unit.py"],
    "doclink": ["tests/doc_link_unit.py"],
    "gateconsole": ["tests/gate_console_unit.py"],
    "epistemic": ["tests/epistemic_echo_smoke.py"],
    "latent": ["tests/latent_states_unit.py"],
    "curves": ["tests/curves_on_request_smoke.py"],
    "noleak": ["tests/no_benchmark_in_templates.py"],
    "tcleak": ["tests/testcase_truth_leak_unit.py"],
    "rcutoff": ["tests/research_cutoff_unit.py"],
    "impentry": ["tests/implied_entry_unit.py"],
    "assignobs": ["tests/assignment_rule_obs_unit.py"],
    "resultstore": ["tests/result_persistence_unit.py"],
    "resultroundtrip": ["tests/result_roundtrip_unit.py"],
    "resultimport": ["tests/result_import_unit.py"],
    "resultschema": ["tests/result_schema_unit.py"],
    "resultwrites": ["tests/result_writes_unit.py"],
    "resultcrash": ["tests/result_store_crash_unit.py"],
    "recordnode": ["tests/record_node_unit.py"],
    "recordcheck": ["tests/record_completeness_unit.py"],
    "optresult": ["tests/optimize_result_unit.py"],
    "timing": ["tests/timing_unit.py"],
    "agentreplies": ["tests/agent_replies_unit.py"],
    "agenttimeout": ["tests/agent_timeout_unit.py"],
    "boundary": ["tests/boundary_species_unit.py"],
    "candentry": ["tests/candidate_entry_unit.py"],
    "expansion_agent": ["tests/expansion_agent_unit.py"],
    "staged": ["tests/staged_construction_smoke.py"],
    "paramuse": ["tests/parameter_use_unit.py"],
    "structnull": ["tests/structural_nulls_unit.py"],
    "patchids": ["tests/patch_ids_unit.py"],
    "condaxis": ["tests/condition_axis_unit.py"],
    "proberecord": ["tests/probe_record_smoke.py"],
    "mergerefusal": ["tests/merge_refusal_smoke.py"],
    "agentkilled": ["tests/agent_killed_unit.py"],
    "stalecands": ["tests/stale_candidates_unit.py"],
    "interp2exp": ["tests/interp_to_expansion_unit.py"],
    "expredraft": ["tests/expansion_redraft_smoke.py"],
    "untestedobs": ["tests/untested_obs_axis_unit.py"],
    "boundpressure": ["tests/bound_pressure_unit.py"],
    "splitparam": ["tests/split_parameter_unit.py"],
    "splitparam_e2e": ["tests/split_parameter_smoke.py"],
    "profilesreq": ["tests/profiles_on_request_smoke.py"],
    "advisorychecks": ["tests/advisory_checks_unit.py"],
    "basediff": ["tests/base_diff_unit.py"],
    "redraft_h": ["tests/human_redraft_unit.py"],
    "entrymatrix": ["tests/entry_matrix_unit.py"],
    "obsdeclare": ["tests/observation_axes_unit.py"],
    "callcwd": ["tests/call_cwd_unit.py"],
    "convgate": ["tests/convergence_gate_unit.py"],
    "preeq": ["tests/preequilibration_gate_unit.py"],
    "steadystate": ["tests/steady_state_time_unit.py"],
    "engineq": ["tests/engine_questions_unit.py"],
    "profpath": ["tests/diagnostics_profile_path_unit.py"],
    "profproj": ["tests/profile_projection_unit.py"],
    "solvermsgs": ["tests/solver_messages_unit.py"],
    "probeengine": ["tests/probe_engine_unit.py"],
    "offsetrow": ["tests/offset_row_unit.py"],
    "s3answers": ["tests/assembly_failure_answers_unit.py"],
    "revmoves": ["tests/revision_moves_unit.py"],
    "carriedaudit": ["tests/carried_audit_unit.py"],
    "probesel": ["tests/probe_selection_unit.py"],
    "neutralise": ["tests/neutralise_unit.py"],
    "routing": ["tests/routing_unit.py"],
    "designsum": ["tests/design_summary_unit.py"],
    "solversettings": ["tests/solver_settings_unit.py"],
    "tolprobe": ["tests/tolerance_probe.py"],
    "twocomp": ["tests/two_component_noise_unit.py"],
    "sigmarule": ["tests/sigma_through_rule_unit.py"],
    "overlayrefusal": ["tests/overlay_refusal_unit.py"],
    "compilefeedback": ["tests/compile_feedback_unit.py"],
    "convreport": ["tests/convergence_report_unit.py"],
    "speckeys": ["tests/spec_keys_unit.py"],
    "mcpprobe": ["tests/mcp_probe_unit.py"],
    "scaleshapes": ["tests/scaling_shapes_unit.py"],
    "batteryfeedback": ["tests/battery_feedback_unit.py"],
    # the completeness check: no piece of the model that no anchor sees, every
    # varied quantity reaching an anchor, and `assembly_connected` routed by its finding
    "connected": ["tests/connectivity_unit.py"],
    "batteryreask": ["tests/battery_redraft_smoke.py", "--only", "reask"],
    "batterygate": ["tests/battery_redraft_smoke.py", "--only", "gate"],
    "autogrants": ["tests/auto_grants_smoke.py"],
    "dataproc": ["tests/data_processing_unit.py"],
    "procsmoke": ["tests/processing_smoke.py"],
    "researchseam": ["tests/research_seam_smoke.py"],
    "researchfence": ["tests/research_fence_unit.py"],
    "suplit": ["tests/supplied_literature_unit.py"],
    # the knowledge module's reactions inside a run: the pure functions, the
    # base set and the floor, the round's dossier and admission on a record,
    # the wiring, the annotation of the built model and the essential gates in
    # S1 on a record
    "reactions": ["tests/reaction_evidence_unit.py"],
    # the support floor and the grade's helpers: the suggestion rule on crafted
    # essential reactions, the floor card, the case's decision block, the floor
    # on a record, the publication types through a fake fetch
    "gradefloor": ["tests/grade_floor_unit.py"],
    # the knowledge module before a run: the role's wiring, the survey's
    # processing and reply battery, the staged folder, the S0 lines and the
    # run-start refusals, `inputs_read` over `knowledge/`
    "knowledge": ["tests/knowledge_unit.py"],
    # the same end to end: `./run.sh knowledge` offline and online on a stub
    # fixture, the card, and the run start it gates (refused, decided, skipped)
    "knowledgecli": ["tests/knowledge_cli_smoke.py"],
    # the same end to end on its fixture, through file gates: the base from
    # the essential set, the targeted search and its admission, the floor
    # lowered, the exhaustion gate, the graph check, the record and the reports
    "grounding": ["tests/grounding_smoke.py"],
    # the support floor after the base: what a discrimination round's
    # expansions add at the variants' floor, with their search and a refused
    # variation dropped by name
    "floorvariants": ["tests/floor_variants_smoke.py"],
    # the floor across expansion rounds: the schedule, the person's floor and
    # step at the card, axes refused below it and for a required reaction, the
    # expansion's search, and ANALYSIS's "Where the model came from"
    "floorrounds": ["tests/floor_rounds_smoke.py"],
    "censor": ["tests/censoring_declared_unit.py"],
    "replabels": ["tests/replicate_labels_unit.py"],
    # split by cost: the benchmark section is one process; the
    # copilot and strict sections each drive a full pause-and-resume sequence
    "policy_bench": ["tests/policy_modes.py", "--only", "benchmark"],
    # BOTH toys unattended: a case-specific gate the profile does not cover
    # would only show up on the other one
    "policy_bench_decay": [
        "tests/policy_modes.py",
        "toy_decay_params",
        "--only",
        "benchmark",
    ],
    "policy": [
        "tests/policy_modes.py",
        "--only",
        "copilot,strict,hole,refusal",
    ],
    "golden": ["tests/golden_path.py", "toy_phos", "toy_decay_params"],
    "filegate": ["tests/file_gate_loop.py"],
    "filegate_decay": ["tests/file_gate_loop.py", "toy_decay_params"],
    "entry": ["tests/petab_entry_smoke.py"],
    "redraft": ["tests/redraft_smoke.py"],
    "search": ["tests/search_smoke.py"],
    "obsaxis": ["tests/obsaxis_smoke.py"],
    "supermodel_e2e": ["tests/supermodel_smoke.py"],
    "expandoffer_e2e": ["tests/expansion_offer_smoke.py"],
    "expansion": ["tests/expansion_smoke.py"],
    "optcompare_e2e": ["tests/optimizer_compare_smoke.py"],
}

# Every suite belongs to one GROUP: the step or part of the engine it tests.
# CI runs each group as its own job (tests/run_all.py --list-groups builds the
# matrix), so the groups run side by side; `--group <name>` runs one here.
GROUPS: dict[str, tuple[str, list[str]]] = {
    "static": (
        "docs, registries and code invariants, no pipeline run",
        [
            "structure",
            "speckeys",
            "routing",
            "noleak",
            "tcleak",
            "glossary",
            "budget",
            "prompts",
            "agentreplies",
            "dotlabel",
            "doclink",
            "lb3",
            "curves",
            "mcpprobe",
            "callcwd",
            "provenance",
        ],
    ),
    "record": (
        "the run record: inputs, writes, schema, import, crash safety, timing",
        [
            "runfolder",
            "inputsread",
            "runid",
            "resultstore",
            "resultroundtrip",
            "resultimport",
            "resultschema",
            "resultwrites",
            "resultcrash",
            "recordnode",
            "recordcheck",
            "optresult",
            "timing",
        ],
    ),
    "gates": (
        "gates and the front end: notes, file-gate driving, policy, resume and re-entry, agent calls",
        [
            "gatenote",
            "gatebind",
            "noteforms",
            "gateconsole",
            "policy_unit",
            "policy_bench",
            "policy_bench_decay",
            "policy",
            "filegate",
            "filegate_decay",
            "golden",
            "autogrants",
            "resumablestop",
            "reentry",
            "impentry",
            "agenttiming",
            "agenttimeout",
            "agentkilled",
            "promptcache",
        ],
    ),
    "construction": (
        "model construction: drafts, redrafts, axes and candidates (S1)",
        [
            "tiers",
            "redraft_unit",
            "constreuse",
            "appendspecies",
            "noopaxis",
            "canddetail",
            "carryundecided",
            "lineagecarry",
            "searchmode",
            "tried",
            "expansion_agent",
            "staged",
            "paramuse",
            "patchids",
            "advisorychecks",
            "basediff",
            "redraft_h",
            "redraft",
            "engineq",
            "axispatch",
            "timeforcing",
            "undecided",
            "untestedobs",
            "stalecands",
            "candentry",
            "connected",
            "boundary",
        ],
    ),
    "search": (
        "the model-space search: axes bought and searched end to end",
        [
            "humanaxes",
            "search",
            "obsaxis",
        ],
    ),
    "selection": (
        "model selection end to end on the abcd cases",
        [],
    ),
    "supermodel": (
        "the supermodel encoding: what it absorbs and refuses, and a real fit",
        [
            "supermodel",
            "supermodel_e2e",
        ],
    ),
    "data": (
        "data: extraction, processing, censoring, steady state, entry (S2)",
        [
            "datadir",
            "longformat",
            "dataproc",
            "procsmoke",
            "censor",
            "replabels",
            "signals",
            "noisefloor",
            "designsum",
            "steadystate",
            "preeq",
            "entry",
            "entrymatrix",
        ],
    ),
    "observation": (
        "the observation model: noise, scaling, sigma, observation axes",
        [
            "units",
            "assignobs",
            "formulasafe",
            "hierarchical",
            "laplace",
            "percondsigma",
            "twocomp",
            "sigmarule",
            "scaleshapes",
            "baseoverlay",
            "obsdeclare",
            "overlayrefusal",
            "offsetrow",
            "condaxis",
            "splitparam",
            "splitparam_e2e",
        ],
    ),
    "assembly": (
        "assembly: the S3 check battery, its feedback and redrafts",
        [
            "batteryfeedback",
            "batteryreask",
            "batterygate",
            "s3answers",
            "carriedaudit",
            "compilefeedback",
            "mergerefusal",
        ],
    ),
    "estimation": (
        "estimation: compile, cost probe, multistart, solvers, profiles, optimiser comparison",
        [
            "estsettings",
            "compile_cache",
            "probereuse",
            "budgetdecline",
            "adjoint",
            "probeengine",
            "proberecord",
            "probesel",
            "solvermsgs",
            "solversettings",
            "tolprobe",
            "skipprof",
            "profilesreq",
            "profpath",
            "profproj",
            "optcompare",
            "optcompare_e2e",
            "convgate",
            "convreport",
            "acceptedentry",
            "reuse",
            "cbredraft",
        ],
    ),
    "evaluation": (
        "evaluation: residual forms, identifiability, misfit evidence, attribution (S7)",
        [
            "curveforms",
            "forms",
            "ident",
            "obsev",
            "compar",
            "constants",
            "latent",
            "structnull",
            "attribution",
            "neutralise",
            "fitband",
            "epistemic",
            "revmoves",
            "roundseed",
        ],
    ),
    "expansion": (
        "expansion: the offer, the agent, redrafts and the next round",
        [
            "expandoffer",
            "interp2exp",
            "boundpressure",
            "expredraft",
            "expansion",
            "expandoffer_e2e",
        ],
    ),
    "literature": (
        "literature research: the research seam, its fence, supplied papers",
        [
            "researchseam",
            "researchfence",
            "suplit",
            "rcutoff",
        ],
    ),
    "knowledge": (
        "the knowledge module: reactions, grades, the CLI, grounding in a run",
        [
            "reactions",
            "gradefloor",
            "knowledge",
            "knowledgecli",
            "grounding",
        ],
    ),
    "floor": (
        "the support floor across expansions and rounds",
        [
            "floorvariants",
            "floorrounds",
        ],
    ),
}

_grouped = [n for _title, names in GROUPS.values() for n in names]
assert sorted(_grouped) == sorted(SUITES), (
    "every suite in exactly one group: "
    f"ungrouped {sorted(set(SUITES) - set(_grouped))}, "
    f"twice {sorted({n for n in _grouped if _grouped.count(n) > 1})}, "
    f"unknown {sorted(set(_grouped) - set(SUITES))}"
)

# The suites that run at full effort (workflows/default.yaml): those whose
# assertions are scientific (parameter recovery, held-out rejection, the
# model-space search, selection, expansion recovery), the multi-run plumbing
# that was always run at full effort (`resultcrash`, `policy`, `golden`,
# `tolprobe`), and the two that skip a step under the reduced-effort overlay
# (`_harness.quick_tier`): `sigmarule` and `steadystate`. Every other suite
# runs under REDUCED_OVERLAY.
FULL_EFFORT = {
    "cbredraft",
    "resultcrash",
    "splitparam_e2e",
    "tolprobe",
    "batterygate",
    "policy_bench_decay",
    "policy",
    "golden",
    "search",
    "obsaxis",
    "supermodel_e2e",
    "expandoffer_e2e",
    "expansion",
    "optcompare_e2e",
    "sigmarule",
    "steadystate",
}

assert FULL_EFFORT <= SUITES.keys(), FULL_EFFORT - SUITES.keys()


# Suites whose records are incomplete ON PURPOSE, each with the reason: they
# are not failed for what the record checks find in them.
RECORD_GAPS_ALLOWED: dict[str, str] = {}
assert RECORD_GAPS_ALLOWED.keys() <= SUITES.keys(), (
    RECORD_GAPS_ALLOWED.keys() - SUITES.keys()
)


def dirset(path: Path) -> set[str]:
    return {p.name for p in path.iterdir()} if path.is_dir() else set()


def child_env(name: str, runs_dir: Path) -> dict:
    env = dict(os.environ)
    # this suite's own runs directory; `runs/` belongs to the user
    env["OCTOMOD_RUNS_DIR"] = str(runs_dir)
    # one BLAS/OpenMP thread per child: N suites x N threads oversubscribes
    # every core and makes the parallel battery slower than the serial one
    env.update(
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        NUMEXPR_NUM_THREADS="1",
        VECLIB_MAXIMUM_THREADS="1",
    )
    if name not in FULL_EFFORT:
        env["OCTOMOD_SPEC_OVERLAY"] = str(REDUCED_OVERLAY)
    else:
        env.pop("OCTOMOD_SPEC_OVERLAY", None)
    return env


def record_gaps(runs_dir: Path) -> list[str]:
    """What the completeness checks found missing in the records a suite left
    (`octomod/result/completeness.py`): a finished step whose record lacks
    what a reader needs fails the suite, whatever its own checks said. Suites
    that remove their runs, or write them elsewhere, check them themselves
    (`_harness.remove_checked`, `_harness.check_records_complete`)."""
    files = sorted(runs_dir.glob("*.h5")) if runs_dir.is_dir() else []
    if not files:
        return []
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from octomod.result import completeness

    return [g for f in files for g in completeness.gaps(f)]


def run_suite(
    name: str, argv: list[str], keep_runs: bool = False
) -> tuple[str, int, float, str]:
    runs_dir = TEST_RUNS / name
    runs_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, *argv],
        cwd=REPO,
        env=child_env(name, runs_dir),
        capture_output=True,
        text=True,
    )
    dt = time.perf_counter() - t0
    rc, output = proc.returncode, proc.stdout + proc.stderr
    if rc in (0, SKIP_EXIT) and name not in RECORD_GAPS_ALLOWED:
        gaps = record_gaps(runs_dir)
        if gaps:
            rc = 1
            output += (
                f"\nRECORD INCOMPLETE — {len(gaps)} gap(s) in what the finished "
                "steps should have left in the record (or a record unreadable):\n"
                + "\n".join(f"  · {g}" for g in gaps[:40])
                + "\n"
            )
    # a PASSING suite's runs are leavings; a FAILING suite's runs are the evidence
    if rc in (0, SKIP_EXIT) and not keep_runs:
        shutil.rmtree(runs_dir, ignore_errors=True)
    return name, rc, dt, output


def load_durations() -> dict[str, float]:
    """Each suite's time in the last battery that ran it."""
    try:
        known = json.loads(DURATIONS.read_text())
        return {str(k): float(v) for k, v in known.items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}  # none yet (or an older layout): the fallback order


def save_durations(results: list[tuple[str, int, float, str]]) -> None:
    known = {**load_durations(), **{n: round(dt, 1) for n, _, dt, _ in results}}
    try:
        DURATIONS.write_text(json.dumps(known, indent=1, sort_keys=True) + "\n")
    except OSError:
        pass  # only an ordering hint


def skip_reason(output: str) -> str:
    for line in output.splitlines():
        if line.strip().startswith("SKIP:"):
            return line.strip()[len("SKIP:") :].strip()
    return "(no reason given)"


def verdict_of(rc: int) -> str:
    return "OK" if rc == 0 else ("SKIP" if rc == SKIP_EXIT else f"FAIL (exit {rc})")


def _tail(output: str, n: int = 40) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    tail = lines[-n:]
    # the output is stdout + stderr, so a suite that logs to stderr can push
    # its own verdict (`_harness.finish`'s FAILED block) out of the tail: the
    # block is what a reader needs, so it leads whenever the tail lost it
    start = next((i for i, line in enumerate(lines) if " FAILED — " in line), None)
    if start is not None and start < len(lines) - n:
        end = start + 1
        while end < len(lines) and lines[end].startswith("  · "):
            end += 1
        return "\n".join(lines[start:end] + ["[…]"] + tail)
    return "\n".join(tail)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="run_all")
    ap.add_argument(
        "suites", nargs="*", help=f"subset by name; known: {sorted(SUITES)}"
    )
    ap.add_argument("--serial", action="store_true", help="one suite at a time")
    ap.add_argument(
        "--keep-runs",
        action="store_true",
        help="keep every suite's run directory under test_runs/ instead of "
        "removing the ones a PASSING suite created. For a debugging "
        "session; a failing suite's runs are kept either way.",
    )
    ap.add_argument(
        "--jobs", type=int, default=None, help="concurrent suites (default: cores/2)"
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="SUITE",
        help=(
            "drop a suite from this run (repeatable). For suites that CANNOT "
            "pass in the environment running them — not for ones that merely "
            "fail; an unknown name here is an error, so a rename cannot make "
            "an exclusion silently stop applying."
        ),
    )
    ap.add_argument(
        "--group",
        action="append",
        default=[],
        choices=sorted(GROUPS),
        help="run only the suites of this group (repeatable)",
    )
    ap.add_argument(
        "--list-groups",
        action="store_true",
        help="print, as JSON, the groups that have a suite to run after "
        "--exclude (what CI builds its job matrix from), and run nothing",
    )
    args = ap.parse_args(argv)

    unknown = [n for n in args.suites if n not in SUITES]
    if unknown:
        print(f"unknown suite(s) {unknown}; known: {sorted(SUITES)}")
        return 2
    unknown_excludes = [n for n in args.exclude if n not in SUITES]
    if unknown_excludes:
        print(
            f"unknown --exclude suite(s) {unknown_excludes}; known: {sorted(SUITES)}\n"
            "(an exclusion naming a suite that does not exist is silently "
            "excluding nothing, so this is an error rather than a warning)"
        )
        return 2
    chosen = args.suites or list(SUITES)
    if args.group:
        wanted = {n for g in args.group for n in GROUPS[g][1]}
        chosen = [n for n in chosen if n in wanted]
    if args.list_groups:
        left = set(chosen) - set(args.exclude)
        print(json.dumps([g for g, (_t, names) in GROUPS.items() if left & set(names)]))
        return 0
    if args.exclude:
        dropped = [n for n in chosen if n in set(args.exclude)]
        chosen = [n for n in chosen if n not in set(args.exclude)]
        if dropped:
            print(f"excluded {len(dropped)} suite(s): {', '.join(dropped)}")
    if not chosen:
        print("no suites left to run after --group / --exclude")
        return 2
    if not REDUCED_OVERLAY.exists():
        print(f"missing overlay {REDUCED_OVERLAY}")
        return 2
    jobs = 1 if args.serial else (args.jobs or max(1, (os.cpu_count() or 2) // 2))
    jobs = min(jobs, len(chosen))

    n_full = sum(1 for n in chosen if n in FULL_EFFORT)
    tier = ", ".join(args.group) if args.group else "all groups"
    print(
        f"{'=' * 78}\nBATTERY — {tier}\n  {len(chosen)} suite(s): {', '.join(chosen)}\n"
        f"  {jobs} concurrent · {n_full} at full effort, the rest under "
        f"{REDUCED_OVERLAY.relative_to(REPO)}\n{'=' * 78}",
        flush=True,
    )

    # `runs/` is the user's: the battery must leave it exactly as it found it
    user_runs_before = dirset(USER_RUNS)

    results: list[tuple[str, int, float, str]] = []
    t_wall = time.perf_counter()
    if jobs == 1:
        for name in chosen:
            print(f"\n>>> {name}: {' '.join(SUITES[name])}", flush=True)
            res = run_suite(name, SUITES[name], args.keep_runs)
            print(res[3], end="", flush=True)
            results.append(res)
    else:
        # output is captured and printed per suite as it finishes: interleaved
        # live streams are unreadable, and a failure's tail is what a reader needs
        # longest first, so wall time is bounded by the slowest suite rather
        # than by whichever long one was submitted last: by the last
        # battery's times, and with none recorded (a CI runner) the
        # full-effort suites, the long ones, ahead of the rest
        last = load_durations()

        def expected_s(n: str) -> float:
            return last.get(n, float("inf") if n in FULL_EFFORT else 0.0)

        submit = sorted(chosen, key=lambda n: -expected_s(n))
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {
                pool.submit(run_suite, n, SUITES[n], args.keep_runs): n for n in submit
            }
            done = 0
            for fut in concurrent.futures.as_completed(futures):
                res = fut.result()
                results.append(res)
                done += 1
                name, rc, dt, out = res
                mark = (
                    "OK  "
                    if rc == 0
                    else ("SKIP" if rc == SKIP_EXIT else f"FAIL({rc})")
                )
                print(
                    f"[{done}/{len(chosen)}] {mark} {name:15s} {dt:7.1f}s"
                    + (f"  — {skip_reason(out)}" if rc == SKIP_EXIT else ""),
                    flush=True,
                )
                if rc not in (0, SKIP_EXIT):
                    print(
                        f"--- {name} output (tail) ---\n{_tail(out)}\n--- end {name} ---",
                        flush=True,
                    )
    wall = time.perf_counter() - t_wall
    save_durations(results)

    order = {n: i for i, n in enumerate(SUITES)}
    results.sort(key=lambda r: order.get(r[0], 99))
    print(f"\n{'=' * 78}\nBATTERY SUMMARY — {tier}\n{'=' * 78}")
    width = max(len(n) for n, _, _, _ in results)
    for name, rc, dt, _ in results:
        print(f"  {name:{width}s}  {verdict_of(rc):16s} {dt:7.1f}s")
    total = sum(dt for _, _, dt, _ in results)
    n_fail = sum(1 for _, rc, _, _ in results if rc not in (0, SKIP_EXIT))
    skipped = [(n, out) for n, rc, _, out in results if rc == SKIP_EXIT]
    print(
        f"\n  {len(results)} suite(s), {n_fail} failed, {len(skipped)} skipped, "
        f"{wall:.0f}s wall ({total:.0f}s of suite time at {jobs} concurrent)"
    )
    if n_fail:
        print(f"  failed: {[n for n, rc, _, _ in results if rc not in (0, SKIP_EXIT)]}")
    # a skip is NAMED on every run, with its reason
    for name, out in skipped:
        print(f"  skipped: {name} — {skip_reason(out)}")
    if not args.keep_runs:
        kept = sorted(dirset(TEST_RUNS))
        if kept:
            print(
                f"  runs kept for inspection under "
                f"{TEST_RUNS.relative_to(REPO)}/: {', '.join(kept)}"
            )
    # the battery must not have touched the user's folder at all
    moved = dirset(USER_RUNS) ^ user_runs_before
    if moved:
        print(
            f"\n  !! the battery changed {USER_RUNS.relative_to(REPO)}/: "
            f"{', '.join(sorted(moved))}\n"
            f"     `runs/` is the USER's record and the battery writes to "
            f"{TEST_RUNS.relative_to(REPO)}/. A suite that reached it is "
            f"spelling `runs/` instead of `config.RUNS_DIR`."
        )
        return 1
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
