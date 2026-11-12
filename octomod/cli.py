"""CLI entry point.

  <venv-python> -m octomod run --testcase testcase/<case> --backend stub --auto-approve
  <venv-python> -m octomod run --run-id <project>_<stamp>        (inputs already in the record's `input` group)
  <venv-python> -m octomod status --run-id <id>
  <venv-python> -m octomod knowledge --testcase staging/<project> --mode online|offline [--show]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from octomod import config
from octomod.orchestration import run_folder, run_guard


def _resolve_backend(run_id: str, requested: str | None, overwrite: bool) -> str | None:
    """The backend a run runs with. A run's backend is part of what it is: a run
    started with live agents must not continue on canned replies because a
    resume left the flag out, and the other way round. A new run (or one
    overwritten) takes the flag, default stub; an existing record's run takes
    its recorded backend when no flag is given and refuses a flag that
    differs. None means refused, and the reason is printed."""
    from octomod.result.node import Node
    from octomod.result.runstore import RunStore

    store = RunStore.for_run(config.RUNS_DIR, run_id)
    recorded = None
    if store.exists_on_disk() and not overwrite:
        try:
            run = (Node(store) / "run").get(None)
        except Exception:  # an unreadable record is the guard's to refuse
            run = None
        recorded = (run or {}).get("backend") if isinstance(run, dict) else None
    if recorded in ("stub", "llm"):
        if requested is not None and requested != recorded:
            print(
                f"refused: run {run_id!r} was started with --backend {recorded}; "
                f"a resume keeps the backend it started with (leave the flag out, "
                f"or pass --backend {recorded}). To run the case with --backend "
                f"{requested}, start a new run.",
                file=sys.stderr,
            )
            return None
        return recorded
    return requested or "stub"


def _knowledge(args) -> int:
    """`knowledge`: run the module on a staging folder and print the floor
    card, or print it again (`--show`). Never writes the decision: the front
    end writes the person's answer into testcase.yaml."""
    from octomod.agents import AgentCallError
    from octomod.spec import WorkflowSpec
    from octomod.workflow_modules.knowledge import engine as knowledge

    case = args.testcase
    if case.resolve().is_relative_to(config.RUNS_DIR.resolve()):
        print(
            f"refused: {case} is under {config.RUNS_DIR}; a problem is staged "
            f"outside it (staging/<project>/)",
            file=sys.stderr,
        )
        return 2
    if not (case / "intent.yaml").is_file():
        print(f"refused: {case} holds no intent.yaml", file=sys.stderr)
        return 2
    try:
        spec = WorkflowSpec.load(args.workflow)
        spec.validate()
    except (FileNotFoundError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    if args.show:
        for line in knowledge.card_lines(case, spec):
            print(line)
        return 0
    if args.mode is None:
        print(
            "refused: say --mode online (the role may search the literature) or "
            "--mode offline (no tools)",
            file=sys.stderr,
        )
        return 2
    if args.backend == "llm":
        from octomod.agents import llm_backend

        problem = llm_backend.login_problem()
        if problem:
            print(f"refused: {problem}", file=sys.stderr)
            return 2
    print(
        f"knowledge module · {case} · {args.mode} · backend {args.backend}"
        + (" (canned replies, token-free)" if args.backend == "stub" else "")
    )
    try:
        result = knowledge.run_survey(
            case, mode=args.mode, backend=args.backend, spec=spec
        )
    except AgentCallError as e:
        print(f"\nstopped: the knowledge call failed: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\nrefused: {e}", file=sys.stderr)
        return 2
    if not result["ok"]:
        print(
            "\nstopped: the knowledge module wrote no knowledge.json:",
            file=sys.stderr,
        )
        for line in result["problems"]:
            print(f"  {line}", file=sys.stderr)
        return 1 if result.get("calls") else 2
    print()
    for line in knowledge.card_lines(case, spec):
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="octomod")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run the pipeline on a problem")
    p_run.add_argument(
        "--testcase",
        type=Path,
        default=None,
        help="a staged case under testcase/. Snapshotted into the "
        "`input` group of the run's record (runs/<id>.h5) before S0, and from "
        "then on the run reads its inputs only from that snapshot. Omit it to "
        "run on inputs that are already in the `input` group of "
        "runs/<run-id>.h5 (what the chat front end authors with the user).",
    )
    p_run.add_argument(
        "--from-run",
        default=None,
        metavar="RUN_ID",
        help="a follow-up run: copy the `input` group (and its "
        "`input_source`) of the record runs/<RUN_ID>.h5 into this run's "
        "record before S0, so `started_from` is recorded; needs a new "
        "--run-id (or --overwrite). --testcase is not read with it.",
    )
    p_run.add_argument(
        "--workflow", type=Path, default=config.WORKFLOWS_DIR / "default.yaml"
    )
    p_run.add_argument(
        "--backend",
        choices=["stub", "llm"],
        default=None,
        help="the agents: canned replies (stub) or live calls (llm). A new run "
        "defaults to stub; a resume or re-entry defaults to the backend the "
        "run was started with, and refuses a different one.",
    )
    p_run.add_argument(
        "--run-id",
        default=None,
        help="the run's record, runs/<id>.h5. Default: <project>_<YYYYMMDD_HHMMSS>, "
        "which needs --testcase to know the project; required without one. "
        "It may not start with '_': that prefix is reserved for the engine's "
        "own folders under runs/ (_projects/, _amici_cache/).",
    )
    p_run.add_argument(
        "--auto-approve",
        action="store_true",
        help="answer every human gate with yes; recorded as such " "(test mode only)",
    )
    p_run.add_argument("--max-rounds", type=int, default=None)
    p_run.add_argument(
        "--overwrite",
        action="store_true",
        help="delete an existing run with this id before starting. Without "
        "it, a run-id whose run already ENDED is refused; a run paused at a "
        "gate still resumes, which is what the file-gate protocol needs. "
        "With no --testcase, the record's `input` group is KEPT: those "
        "inputs are the only copy "
        "of something the engine never created.",
    )
    p_run.add_argument(
        "--n-starts",
        type=int,
        default=None,
        help="override the proposed start count (still clamped "
        "by the workflow spec)",
    )
    p_run.add_argument(
        "--model-override",
        default=None,
        help="run every agent role on this model (e.g. haiku "
        "for a cheap plumbing test)",
    )
    p_run.add_argument(
        "--gate-mode",
        choices=["interactive", "file"],
        default="interactive",
        help="file: pause at each human gate, record it in the run "
        "(`pending_gate`; read it with `pending`), exit 3; answer by "
        "rerunning with --gate-answer",
    )
    p_run.add_argument(
        "--gate-answer",
        choices=["y", "n"],
        default=None,
        help="(file mode) answer for the pending gate",
    )
    p_run.add_argument(
        "--gate-note",
        default="",
        help="(file mode) note attached to the answer, e.g. 'n=50'",
    )
    p_run.add_argument(
        "--skip-profiles",
        default=None,
        metavar="WHY",
        help="skip the profile likelihoods of the round this invocation "
        "evaluates, giving the reason in the human's words; ledgered as a "
        "human decision and shown in the report. Refused for a "
        "parameter_values case, where the profiles are the deliverable. "
        "Profiles are computed only on request for every other goal, so "
        "this records a decline that is already the default.",
    )
    p_run.add_argument(
        "--profiles",
        default=None,
        metavar="WHY",
        help="compute the profile likelihoods of the model the round this "
        "invocation evaluates selects (off unless asked, except for a "
        "parameter_values case), giving the reason in the human's words; "
        "ledgered as a human decision. The verdict card offers the same as "
        "the form `profiles`.",
    )
    p_run.add_argument(
        "--policy",
        default=None,
        help="gate policy: a profile name (strict | copilot | benchmark) or a "
        "path to a policy yaml. Declared answers are hashed into the run and "
        "every policy-answered gate is ledgered mode=policy with that sha. "
        "strict pauses at every gate; copilot answers the cost-shaped gates "
        "under its caps and pauses at the judgment ones; benchmark must cover "
        "every gate it reaches and stops honestly (exit 1) at one it does "
        "not. Unset = strict, which is the workflow as drawn: every gate that "
        "a person should approve, or give input to, reaches them.",
    )
    p_run.add_argument(
        "--from-module",
        default=None,
        help="enter the pipeline at this module (model | data | "
        "assembly | estimation | evaluation): every upstream "
        "slot is validated by its gate battery and the run "
        "refuses with the named missing/invalid slot; the "
        "entry module and everything after it run afresh. "
        "A testcase with supplied/petab enters at estimation "
        "automatically, and refuses model | data | assembly "
        "by name (nothing upstream produced its problem).",
    )

    p_knowledge = sub.add_parser(
        "knowledge",
        help="the knowledge module, before a run: what is known about the "
        "system (the essential reactions, the facts a model needs, their "
        "sources), graded by the engine, written to <folder>/knowledge/, and "
        "the floor card for the person's support-floor decision",
    )
    p_knowledge.add_argument(
        "--testcase",
        type=Path,
        required=True,
        help="the staging folder (staging/<project>/ or testcase/<case>/)",
    )
    p_knowledge.add_argument(
        "--mode",
        choices=["online", "offline"],
        default=None,
        help="online: the knowledge role may search the literature (WebSearch, "
        "WebFetch, fenced by the case's horizon and blocklist); offline: no "
        "tools, the reply is the role's own knowledge and nothing is graded. "
        "Required unless --show.",
    )
    p_knowledge.add_argument(
        "--backend",
        choices=["stub", "llm"],
        default="stub",
        help="the agent: canned replies from <folder>/stubs/ (stub) or a live "
        "call (llm)",
    )
    p_knowledge.add_argument(
        "--workflow", type=Path, default=config.WORKFLOWS_DIR / "default.yaml"
    )
    p_knowledge.add_argument(
        "--show",
        action="store_true",
        help="print the floor card again from <folder>/knowledge/, with the "
        "decision testcase.yaml records; nothing is called or written",
    )

    p_status = sub.add_parser(
        "status",
        help="the run as its record says it stands: rounds, candidates, "
        "markers, decisions, outcome (runs/<id>.h5), then the ledger tail",
    )
    p_status.add_argument("--run-id", required=True)

    p_inspect = sub.add_parser(
        "inspect",
        help="where things went wrong, in order: every failed blocking gate, "
        "dropped candidate, agent redraft and stopped outcome, read from the "
        "result record",
    )
    p_inspect.add_argument("--run-id", required=True)

    p_report = sub.add_parser(
        "report",
        help="render the HTML report(s) for a round from the record, into "
        "runs/<id>_reports/",
    )
    p_report.add_argument("--run-id", required=True)
    p_report.add_argument(
        "--round",
        type=int,
        default=None,
        help="round index (default: the latest round present)",
    )
    p_report.add_argument(
        "--analysis",
        action="store_true",
        help="regenerate the RUN-level analysis report "
        "(runs/<id>_reports/ANALYSIS.html and ANALYSIS.md, kept in the "
        "record at `analysis`): every model assessed across every "
        "round, what won, the answer to the question that "
        "was asked, and what is still open",
    )
    p_report.add_argument(
        "--model",
        action="store_true",
        help="also render the S1 model report "
        "(runs/<id>_reports/round_k/report/model_report.html)",
    )

    p_export = sub.add_parser(
        "export",
        help="a copy of the run's record (runs/<id>.h5) with fewer tiers or "
        "rounds, for sharing — still valid against docs/RESULT-SCHEMA.md",
    )
    p_export.add_argument("--run-id", required=True)
    p_export.add_argument(
        "--tiers",
        default="core,bulk,audit",
        help="comma-separated tiers to keep: core (always), bulk (arrays, "
        "tables, traces), audit (prompts, raw replies, the ledger). A copy "
        "with fewer tiers lists what it dropped in each record's `elided`.",
    )
    p_export.add_argument(
        "--rounds",
        default=None,
        help="comma-separated round indices to keep in full; every other round "
        "is reduced to its index, selection and decisions",
    )
    p_export.add_argument(
        "--out",
        type=Path,
        default=None,
        help="where the copy goes (required for a pruned copy; the run's own "
        "record is never pruned in place)",
    )

    p_pending = sub.add_parser(
        "pending",
        help="the gate a paused run is waiting at, as JSON (what the front "
        "end reads after exit 3; empty when nothing is pending)",
    )
    p_pending.add_argument("--run-id", required=True)

    p_show = sub.add_parser(
        "show",
        help="print one part of the record: `show --run-id <id> [<key>]` — a "
        "record key (rounds/round_0/evaluation, rounds/round_0/decisions_md); "
        "no key lists the top level",
    )
    p_show.add_argument("--run-id", default=None)
    p_show.add_argument(
        "--file", type=Path, default=None, help="a record file anywhere"
    )
    p_show.add_argument("key", nargs="?", default=None)
    p_show.add_argument(
        "--full", action="store_true", help="do not fold long strings or arrays"
    )

    p_explore = sub.add_parser(
        "explore",
        help="explore the record interactively: ls, cd, cat, find, gates, "
        "decisions, failures, ledger, status, report, export",
    )
    p_explore.add_argument("--run-id", default=None)
    p_explore.add_argument(
        "--file",
        type=Path,
        default=None,
        help="a record file anywhere (a copy, an export)",
    )

    p_legacy = sub.add_parser(
        "import-legacy",
        help="transcribe a legacy run DIRECTORY (runs/<id>/ with ledger.jsonl "
        "and the artifact files) into a record file runs/<id>.h5",
    )
    p_legacy.add_argument("--run-dir", required=True, type=Path)
    p_legacy.add_argument(
        "--run-id", default=None, help="the record's id (default: the dir name)"
    )

    args = parser.parse_args(argv)

    if args.cmd == "knowledge":
        return _knowledge(args)

    if args.cmd == "run":
        from octomod.orchestration.orchestrator import Orchestrator

        if args.policy is not None and args.auto_approve:
            # two answer sources for one gate: refused rather than picked, so
            # the ledger can always say on whose authority a gate was answered
            print(
                "--auto-approve and --policy both answer gates; pass one. "
                "(--auto-approve is the test-suite primitive, recorded "
                'mode="auto"; a policy is declared configuration, recorded '
                'mode="policy" with its sha.)',
                file=sys.stderr,
            )
            return 2

        if args.profiles and args.skip_profiles:
            print(
                "--profiles and --skip-profiles ask for opposite things; pass one.",
                file=sys.stderr,
            )
            return 2

        if args.run_id is None and args.testcase is None and args.from_run is None:
            print(
                "nothing to run: pass --testcase <staged case> to start from "
                "the testcase library, or --run-id <id> to run on inputs "
                f"already staged in the `input` group of {config.RUNS_DIR}/<id>.h5.",
                file=sys.stderr,
            )
            return 2
        run_id = args.run_id or run_folder.default_run_id(
            args.testcase.name
            if args.testcase is not None
            else run_folder.project_of(args.from_run, None)
        )
        if run_id.startswith(config.RESERVED_RUN_PREFIX):
            # run ids name records (`<id>.h5`) beside the engine's own
            # folders (`_projects/`, `_amici_cache/`)
            print(
                f"refused: run-id {run_id!r} starts with "
                f"{config.RESERVED_RUN_PREFIX!r}, which is reserved for the "
                f"engine's own folders under {config.RUNS_DIR}.",
                file=sys.stderr,
            )
            return 2
        backend = _resolve_backend(run_id, args.backend, args.overwrite)
        if backend is None:
            return 2
        if backend == "llm":
            from octomod.agents import llm_backend

            problem = llm_backend.login_problem()
            if problem:
                print(f"refused: {problem}", file=sys.stderr)
                return 2
        try:
            orch = Orchestrator(
                testcase_dir=args.testcase,
                workflow_path=args.workflow,
                backend=backend,
                run_id=run_id,
                auto=args.auto_approve,
                max_rounds=args.max_rounds,
                n_starts=args.n_starts,
                model_override=args.model_override,
                gate_mode=args.gate_mode,
                gate_answer=args.gate_answer,
                gate_note=args.gate_note,
                from_module=args.from_module,
                overwrite=args.overwrite,
                skip_profiles=args.skip_profiles,
                request_profiles=args.profiles,
                # the default is `strict` (every gate reaches a person), named
                # so the run records which policy was in force
                policy=args.policy or "strict",
                from_run=args.from_run,
            )
        except run_folder.InputsMissing as e:
            # No inputs at all: an operator decision, before the run record
            # exists and before a token is spent.
            print(f"\nrefused: {e}", file=sys.stderr)
            return 2
        except run_guard.RunIdRefused as e:
            # An operator decision, not a crash: say what to do and stop.
            print(f"\n{e}", file=sys.stderr)
            return 1
        except (FileNotFoundError, ValueError) as e:
            # a bad --policy, or a workflow value the engine cannot honour
            # (e.g. an unimplemented `search.method`): refused by name
            print(f"\nrefused: {e}", file=sys.stderr)
            return 2
        return orch.run()

    if args.cmd in (
        "status",
        "inspect",
        "pending",
        "show",
        "explore",
        "report",
        "export",
    ):
        from octomod.result.node import Node
        from octomod.result.runstore import SUFFIX, RunStore

        if getattr(args, "file", None) is not None:
            store = RunStore(args.file)
        elif args.run_id:
            store = RunStore.for_run(config.RUNS_DIR, args.run_id)
        else:
            print(
                "name the run: --run-id <id> (or --file <record.h5>)", file=sys.stderr
            )
            return 2
        root = Node(store)
        if not store.exists_on_disk():
            print(f"no such run: {store.path}", file=sys.stderr)
            return 1

    if args.cmd == "pending":
        from octomod.orchestration.interaction.humangate import pending_path

        pend = pending_path(root)
        if not pend.exists():
            print("{}")
            return 0
        print(json.dumps(pend.get(), indent=2, default=str))
        return 0

    if args.cmd == "show":
        from octomod.result.explorer import show

        return show(store, args.key, full=args.full)

    if args.cmd == "explore":
        from octomod.result.explorer import Explorer

        Explorer(store).cmdloop()
        return 0

    if args.cmd in ("status", "inspect"):
        from octomod.result.access import record_for
        from octomod.result.explorer import failures_lines, status_lines

        if args.cmd == "inspect":
            record = record_for(store)
            print(
                f"{store.run_id}: {len(record.failures())} thing(s) went wrong "
                f"(outcome: {record.outcome.outcome if record.outcome else 'open'})"
            )
            for line in failures_lines(store):
                print("  " + line)
            return 0
        for line in status_lines(store):
            print(line)
        return 0

    if args.cmd == "report":
        from octomod.reporting import write_model_report_html, write_report_html

        if args.analysis:
            from octomod.reporting.analysis_report import write as write_analysis

            print(write_analysis(root))
            return 0
        from octomod.result import node as tree

        rounds = tree.round_indices(root)
        k = args.round if args.round is not None else (rounds[-1] if rounds else None)
        rnd = tree.round_node(root, k) if k is not None else None
        if rnd is None or not rnd.exists():
            print(f"no such round in {store.path}", file=sys.stderr)
            return 1
        print(write_report_html(rnd))
        if args.model:
            print(write_model_report_html(rnd))
        return 0

    if args.cmd == "export":
        from octomod.result import prune
        from octomod.result.store import commit, select_rounds

        try:
            result = store.load()
        except Exception as e:  # noqa: BLE001 - say what is wrong with the record
            print(f"refused: the record does not validate: {e}", file=sys.stderr)
            return 1
        tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
        pruned = set(tiers) != {"core", "bulk", "audit"} or bool(args.rounds)
        if args.out is None:
            if pruned:
                # the run's own record is never pruned in place
                print(
                    "refused: a copy with fewer tiers or rounds needs --out — "
                    "runs/<id>.h5 is the run's record and is never pruned in place",
                    file=sys.stderr,
                )
                return 2
            size_mb = store.path.stat().st_size / 1e6
            print(
                f"{store.path}  ({size_mb:.1f} MB; the run's own record — "
                f"rounds {result.round_indices}; outcome "
                f"{result.outcome.outcome if result.outcome else 'open'})"
            )
            return 0
        # `--out runs/<id>.h5` (or `runs/<id>`, since commit appends `.h5`)
        # would write the copy over the run's own record
        out_h5 = args.out
        if not out_h5.name.endswith(SUFFIX):
            out_h5 = out_h5.with_name(out_h5.name + SUFFIX)
        own = {store.path.resolve(), store.backup_path.resolve()}
        if {args.out.resolve(), out_h5.resolve()} & own:
            print(
                f"refused: --out names the run's own record ({store.path}) — "
                "a copy is a separate file; give it another path",
                file=sys.stderr,
            )
            return 2
        try:
            result = prune(result, tiers)
        except ValueError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        if args.rounds:
            keep = [int(k) for k in args.rounds.split(",") if k.strip()]
            result = select_rounds(result, keep)
        try:
            out = commit(result, args.out)  # `.h5` appended when missing
        except FileExistsError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        size_mb = out.stat().st_size / 1e6
        print(
            f"{out}  ({size_mb:.1f} MB; tiers {','.join(sorted(set(tiers) | {'core'}))}; "
            f"rounds {result.round_indices}; outcome "
            f"{result.outcome.outcome if result.outcome else 'open'})"
        )
        return 0

    if args.cmd == "import-legacy":
        from octomod.result.importer import import_run
        from octomod.result.runstore import RunStore as _RunStore

        run_dir = args.run_dir
        if not run_dir.is_dir():
            print(f"no such run directory: {run_dir}", file=sys.stderr)
            return 1
        target = _RunStore.for_run(config.RUNS_DIR, args.run_id or run_dir.name)
        if target.exists_on_disk():
            print(f"refused: {target.path} exists already", file=sys.stderr)
            return 2
        try:
            rep = import_run(run_dir, target)
        except FileNotFoundError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 1
        result = target.load()
        target.checkpoint()
        print(
            f"{rep.path}  ({rep.path.stat().st_size / 1e6:.1f} MB; "
            f"{rep.written} artifact(s), {rep.rendered} rendered document(s); "
            f"rounds {result.round_indices}; outcome "
            f"{result.outcome.outcome if result.outcome else 'open'})"
        )
        for label, items in (
            ("not transcribed (unknown name)", rep.unknown),
            ("unreadable", rep.failed),
        ):
            if items:
                print(f"  {label}: {len(items)}", file=sys.stderr)
                for x in items[:20]:
                    print(f"    {x}", file=sys.stderr)
        return 0

    return 2
