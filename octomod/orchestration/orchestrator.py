"""The orchestrator — code, not an agent.

Walks the declared module sequence, evaluates gates, enforces the DAG through
markers in the run record and loops through revisions under a budget; nothing
here is for an LLM to decide. A run reads its inputs only from its own
snapshot: the record's `input` group (taken from `--testcase` before S0, or
authored into the record before the run; see `run_folder`), materialised to a
directory for the process. Artifacts in `input/supplied/` are seeded into
round 0 of the record: their module's agents are skipped, their gates are not.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from octomod import PROCESS_T0 as _PROCESS_T0
from octomod import (
    __version__,
    config,
)
from octomod.agents import AgentCallError
from octomod.agents import payload as _agent_payload
from octomod.gates import GateFailure
from octomod.orchestration import provenance as pv
from octomod.orchestration import run_folder, run_guard, timing
from octomod.orchestration.artifacts import read_json, read_tsv
from octomod.orchestration.interaction import humangate as humangate_module
from octomod.orchestration.interaction.policy import Policy, PolicyUncovered
from octomod.orchestration.ledger import Ledger
from octomod.orchestration.rounds import rounds_left_after
from octomod.orchestration.run_context import (
    ModuleFailure,
    NoteRefused,
    RunContext,
    as_candidate,
    candidate_work,
)
from octomod.result import node as tree
from octomod.result.autocommit import commit_run
from octomod.result.node import Node
from octomod.result.runstore import RunStore
from octomod.result.slots import ExpansionRecord
from octomod.result.write import write_record
from octomod.spec import WorkflowSpec
from octomod.workflow_modules.assembly import assembly_edit
from octomod.workflow_modules.assembly import engine as assembly_module
from octomod.workflow_modules.cost_probe import compile_feedback, compile_gate
from octomod.workflow_modules.cost_probe import engine as cost_profile
from octomod.workflow_modules.data import engine as data_module
from octomod.workflow_modules.estimation import engine as estimation_module
from octomod.workflow_modules.evaluation import engine as evaluation_module
from octomod.workflow_modules.intent import engine as intent_module
from octomod.workflow_modules.model import engine as model_module
from octomod.workflow_modules.revision import engine as revision_proposal_module

SUPPLIED_MAP = {
    # input/supplied/<src> -> (record key under rounds/round_0, codec).
    # `supplied/petab/` is not copied: round_status.adapt_supplied_petab reads
    # it from the staged inputs themselves.
    "model.ant": ("model/antimony", "text"),
    "parameters.json": ("model/parameters", "json"),
    "entity_glossary.json": ("model/glossary", "json"),
    "network.json": ("model/network", "json"),
    "measurements_long.tsv": ("data/measurements", "table"),
}

# the record's snapshot of the staged inputs, and where it came from
INPUT_KEY = run_folder.INPUT_KEY

# what the expansion card also reads when the run builds on the knowledge
# module: the floor of the round it seeds, the step, and the round's one search
EXPANSION_FLOOR_FORMS = (
    "floor: <band|none>     the support floor of the round this expansion "
    "seeds (the card names it); an axis adding a conversion graded below it is "
    "refused — recorded as yours",
    "step: <n>              the bands every later expansion lowers the floor "
    "by, from that round on — recorded as yours",
    "search: <question>     spend this round's one targeted search on your "
    "question when the agent did not; the axes are annotated again and the card "
    "is asked again, and nothing is bought by this answer",
)


def _floor_record(floor: dict | None) -> dict | None:
    """A floor as the record keeps it, `{band, step, source}`."""
    if not floor:
        return None
    return {k: floor.get(k) for k in ("band", "step", "source")}


def should_expand(
    misfit_open: bool,
    rounds_left: int,
    requested: bool | None,
    expand_on_misfit: bool = True,
) -> tuple[bool, str]:
    """Whether to offer another expansion round, and why, as a pure decision.

    `requested` is the human's answer at the verdict gate: True, False, or
    None when the note said nothing. The human decides; the indicators only
    set the default. `expand_on_misfit` gates the automatic trigger only: an
    explicit request outranks it, silence does not.
    """
    if rounds_left <= 0:
        return False, "no rounds left"
    if requested is False:
        return False, "another round was offered and declined at the verdict gate"
    if requested is True:
        return True, (
            "bought at the verdict gate"
            + ("" if misfit_open else " with no indicator open")
        )
    if not misfit_open:
        return False, "no indicator is open, and no round was asked for"
    if not expand_on_misfit:
        return False, "search.expand_on_misfit is off and no round was asked for"
    return True, "the misfit evidence is open (the default)"


def expansion_took_over(expanded) -> bool:
    """Did the expanded round run to its own end and write the record?

    `_maybe_expand_space` returns None when it did not expand, otherwise the
    exit code of the round it ran; 0 is success, so truthiness is the wrong test.
    """
    return expanded is not None


# Exceptions that steer the run rather than report a defect: a gate pausing in
# file mode, a policy hole, a human's redraft, a module's own refusal. The
# per-candidate compile loop must let every one of them through untouched.
_CONTROL_FLOW_NAMES = frozenset(
    {
        "ModuleFailure",
        "GateFailure",
        "GatePending",
        "AgentCallError",
        "PolicyUncovered",
        "RedraftRequested",
        "CandidateDefect",
        "KeyboardInterrupt",
    }
)


def _is_control_flow(exc: BaseException) -> bool:
    return any(k.__name__ in _CONTROL_FLOW_NAMES for k in type(exc).__mro__)


class Orchestrator:
    def __init__(
        self,
        testcase_dir: Path | None,
        workflow_path: Path,
        backend: str,
        run_id: str,
        auto: bool,
        max_rounds: int | None = None,
        n_starts: int | None = None,
        model_override: str | None = None,
        gate_mode: str = "interactive",
        gate_answer: str | None = None,
        gate_note: str = "",
        from_module: str | None = None,
        overwrite: bool = False,
        policy: str | None = None,
        skip_profiles: str | None = None,
        request_profiles: str | None = None,
        from_run: str | None = None,
    ):
        config.assert_venv()
        self.from_module = from_module
        # `--from-module` is a human asking to redo a module; a testcase with
        # supplied/petab enters at estimation on EVERY invocation and must
        # not throw finished work away when it does.
        self.entry_implied = False
        self.spec = WorkflowSpec.load(workflow_path)
        self.spec.validate()
        # declared gate answers, loaded before any cap is read, hashed into the run
        self.policy = Policy.load(policy) if policy else None
        if model_override:
            self.spec.raw.setdefault("models", {})["override_all"] = model_override
        # the run IS one file, runs/<id>.h5; every location below is a
        # record key of it (a Node), and nothing else is written under runs/
        # except the rendered documents beside it.
        self.store = RunStore.for_run(config.RUNS_DIR, run_id)
        self.root = Node(self.store)
        # where the inputs come from, decided before anything is written, so
        # a run with neither --testcase nor an `input` group is refused at no
        # cost (run_folder: snapshot | in_record | copy | legacy)
        plan = run_folder.plan(
            self.root, testcase_dir, overwrite=overwrite, from_run=from_run
        )
        # run-id safety (an existing run is never silently reused), checked
        # before the record exists and before `run` is rewritten, because the
        # check compares against what `run` records. `--overwrite`
        # keeps an `input` group the user authored in place: it is the only
        # copy.
        run_guard.check(
            self.root,
            plan.inputs_dir,
            self.spec.sha,
            overwrite=overwrite,
            from_module=from_module,
            # a `--from-run` copy replaces the group, so nothing is kept
            keep_input=plan.source is None and plan.mode != "copy",
        )
        # the record is created here when it does not exist yet; a snapshot
        # is taken into its `input` group, which is then materialised to the
        # temporary directory the engine reads (`ctx.testcase_dir`)
        self.inputs = run_folder.materialise(plan, self.root, run_id=run_id)
        self.ledger = Ledger(self.store)
        self.project = self.inputs.project
        legacy = self.inputs.legacy
        staged = self.inputs.dir
        self.input_mode = self.inputs.mode
        self.started_from = self.inputs.started_from
        # The source case, for the record and the report — NOT what the run
        # reads. Everything downstream reads `staged` (`ctx.testcase_dir`).
        self.testcase_dir = self.inputs.source
        source = self.inputs.source
        self.source_label = self.inputs.source_label
        # hashed once: the `run` record and the run_start row must agree, and
        # the walk is over every input the run carries (the record's `input`
        # group; a legacy run's testcase folder)
        input_files = run_guard.manifest(staged if legacy else self.root)
        input_sha = run_guard.sha_of(input_files)
        copied = self.inputs.copied
        if copied:
            self.ledger.append(
                "artifact",
                module="input",
                artifact=INPUT_KEY,
                producer="snapshot",
                source=str(source) if source else "authored in place",
                sha=input_sha,
                n_files=len(copied),
                files=copied[:50],
            )
            print(
                f"  snapshotted {len(copied)} input file(s) from "
                f"{source if source else 'the authored inputs'} into the "
                f"record's {INPUT_KEY} group"
            )
        self.ctx = RunContext(
            root=self.root,
            testcase_dir=staged,
            spec=self.spec,
            ledger=self.ledger,
            backend=backend,
            auto=auto,
            source_dir=source,
            project=self.project,
            skip_profiles=(skip_profiles.strip() or None) if skip_profiles else None,
            request_profiles=(
                (request_profiles.strip() or None) if request_profiles else None
            ),
        )
        # research on => the case declares its own horizon or is refused here,
        # before anything runs; the blocklist is optional, and what it holds
        # (even nothing) is ledgered at run start below
        from octomod.workflow_modules.model.engine import research_fence

        research = research_fence(
            self.ctx.testcase,
            self.spec,
            self.project,
            staged / "blocklist.txt",
        )
        # a case that builds on the knowledge module needs the grade's rule
        # table declared and well-formed, refused here by name before anything
        # runs (a `reactions:` block too); the module's own refusals follow
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        grounding = _rxe.fence(
            self.ctx.testcase,
            self.spec,
            self.project,
            staged / "blocklist.txt",
        )
        # the knowledge module runs before the intent is frozen: a case that
        # declares no skip starts only with the module's output, the person's
        # support floor and the required reactions the module saw — refused
        # here by name, before anything is spent
        from octomod.workflow_modules.knowledge import engine as _kn

        knowledge_refusals = _kn.run_start_problems(
            staged,
            self.ctx.testcase or {},
            _kn.staged_intent(staged),
            self.spec,
            source=source if source is not None else "<the staging folder>",
        )
        if knowledge_refusals:
            raise ValueError(
                f"testcase {self.project!r} cannot start: "
                + " | ".join(knowledge_refusals)
            )
        if n_starts:
            self.ctx.cache["n_starts_override"] = n_starts
        # None = no cap: a person buys every further round at a gate. A run
        # nobody answers keeps `loop.max_rounds_unattended`.
        from octomod.orchestration import rounds as _rounds

        self.max_rounds = _rounds.run_cap(
            self.spec, max_rounds, auto=auto, policy=self.policy
        )
        # what code produced the numbers: `engine_version` is a static string,
        # so the commit, the dirty flag and the numerics versions identify it
        provenance = pv.collect()
        # the agents as set up: what the calls RAN on is `models_used`
        provenance["agents"] = pv.agent_setup(self.spec, backend)
        # read, update, put: keys other writers keep in `run` (the tried-log's
        # `tried_log_consumed`) survive this invocation's rewrite
        run_meta = (self.root / "run").get({}) or {}
        if not isinstance(run_meta, dict):
            run_meta = {}
        run_meta.update(
            {
                "run_id": run_id,
                "engine_version": __version__,
                "provenance": provenance,
                "workflow": str(workflow_path),
                "workflow_sha": self.spec.sha,
                # what this run was started with: `testcase` is the source
                # path (empty for a run staged in place); `project` groups the
                # runs of one problem
                "project": self.project,
                "testcase": str(self.testcase_dir) if self.testcase_dir else "",
                # the record key of the snapshot (empty for a legacy run, which
                # reads the testcase in place)
                "input_dir": INPUT_KEY if not legacy else "",
                "input_source": self.source_label,
                "started_from": self.started_from,
                # a legacy run (no snapshot) keeps recording, and being checked
                # against, the key it started with
                ("testcase_sha" if legacy else "input_sha"): input_sha,
                "input_files": input_files,
                "backend": backend,
                "auto": auto,
                "max_rounds": self.max_rounds,
                "from_module": from_module,
                "spec_overlay": self.spec.overlay,
                "policy": (str(self.policy.source) if self.policy else None),
                "policy_profile": (self.policy.profile if self.policy else None),
                "policy_sha": (self.policy.sha if self.policy else None),
            },
        )
        (self.root / "run").put(run_meta)
        timing.attach(self.ctx)  # the time account follows this process
        humangate_module.configure_questions(self.root)
        humangate_module.configure_policy(self.policy)
        if gate_mode == "file":
            humangate_module.configure_file_mode(
                self.root,
                None if gate_answer is None else gate_answer.lower().startswith("y"),
                gate_note,
            )
        elif auto and gate_note:
            # token-free tests that need a real instruction at the gates
            humangate_module.configure_auto_note(gate_note)
        if auto:
            # auto mode's grant cap at exhaustion gates, declared in the spec
            humangate_module.configure_auto_grants(
                int(self.spec.require("retry.auto_grants"))
            )
        self.ledger.append(
            "run_start",
            # how long this process took to get here — imports, the
            # spec, the guard, the record's `run` group — so the session
            # begins where the process did, not where its first row is
            startup_s=round(time.time() - _PROCESS_T0, 3),
            workflow_sha=self.spec.sha,
            backend=backend,
            project=self.project,
            testcase=str(self.testcase_dir) if self.testcase_dir else "",
            input_source=self.source_label,
            started_from=self.started_from,
            input_sha=input_sha,
            spec_overlay=self.spec.overlay,
            policy_profile=(self.policy.profile if self.policy else None),
            policy_sha=(self.policy.sha if self.policy else None),
            code=pv.one_line(provenance),
            git_commit=(provenance.get("git") or {}).get("commit"),
            git_dirty=(provenance.get("git") or {}).get("dirty"),
            versions=(provenance.get("versions") or {}),
            uv_lock_sha256=provenance.get("uv_lock_sha256"),
        )
        # the record checks of how the previous process ended (its pause, its
        # run end) are not this one's: it checks its own at its own stops
        from octomod.result import completeness

        completeness.forget_run(self.root)
        if research is not None:
            # "research on" gets its own row: horizon and forbidden sources, an
            # empty list included (read by round_report.research_line)
            self.ledger.append(
                "research_fence",
                module="run_start",
                horizon=research["horizon"],
                forbidden_sources=research["forbidden_sources"],
                blocklist_file=research["blocklist_file"],
                note=research["note"],
            )
            print(f"  research: on — horizon {research['horizon']}; {research['note']}")
        # its own row beside research's: the knowledge module's mode, the
        # support floor and who set it, the step, the horizon and the
        # forbidden sources (an empty list included) — or the declared skip
        fence_row = _kn.grounding_fence_row(
            staged,
            self.ctx.testcase or {},
            self.spec,
            blocklist=(grounding or {}).get("forbidden_sources"),
        )
        self.ledger.append("grounding_fence", module="run_start", **fence_row)
        print(f"  grounding: {fence_row['note']}")
        if not fence_row.get("skip"):
            # round 0's floor, from the person's decision in testcase.yaml
            _kn.write_round0_floor(self.ctx, self.spec)
        # On the console too, because a reader who is about to spend money on
        # a live run should see whether the result will be attributable.
        print(pv.one_line(provenance))
        if self.policy is not None:
            print(f"gate policy in force: {self.policy.describe()}")
        if self.spec.overlay:
            print(
                f"reduced-effort spec overlay in force: {self.spec.overlay} "
                f"(workflow_sha {self.spec.sha} covers it)"
            )
        model = self.spec.get("models.override_all") or self.spec.get("models.default")
        print(
            f"Octomod · project {self.project} · backend {backend}"
            f"{f' (agents: {model})' if backend == 'llm' else ' (canned outputs, token-free)'}"
        )
        if legacy:
            print(f"inputs: {staged} ({self.source_label})")
        elif self.inputs.matched is not None:
            # the record's own snapshot was used; --testcase was only compared
            print(
                f"inputs: {humangate_module.show_command(self.root / INPUT_KEY)} "
                f"(the record's inputs were used; --testcase "
                f"{self.inputs.matched} matched them)"
            )
        else:
            print(
                f"inputs: {humangate_module.show_command(self.root / INPUT_KEY)} "
                f"({self.source_label})"
            )
        if self.started_from:
            print(f"  started from run {self.started_from}")
        print(f"results & audit trail: {self.store.path}")
        print(
            "\nPIPELINE  intent ▸[you]▸ model ▸gates▸ [you: scope] ▸ data ▸gates▸ "
            "assembly ▸battery+checker▸ [you: compile] ▸ probe ▸ [you: budget] ▸ "
            "estimate ▸gates▸ evaluate ▸ [you: verdict] ▸ revise? ▸ [you: next round]"
        )

    @staticmethod
    def _banner(text: str) -> None:
        print(f"\n▶ {text}")

    # ------------------------------------------------------------ seeding
    @timing.phase("seed")
    def _seed_round0(self) -> None:
        supplied = self.ctx.testcase_dir / "supplied"
        if not supplied.exists():
            return
        round0 = tree.round_node(self.root, 0)
        for src_name, (dst_rel, codec) in SUPPLIED_MAP.items():
            src = supplied / src_name
            if not src.exists():
                continue
            dst = round0 / dst_rel
            if codec == "text":
                dst.put_text(src.read_text())
            elif codec == "table":
                dst.put_table(read_tsv(src))
            else:
                dst.put(read_json(src))
            self.ledger.append(
                "artifact", module="seed", artifact=dst.key, producer="user-supplied"
            )
            print(f"  seeded user-supplied artifact: {dst.key}")
        if (supplied / "petab").exists():
            # A supplied PEtab problem is the estimation problem: derive the
            # model and data slots from it and enter at estimation, so the
            # construction and assembly agents are never called.
            from octomod.orchestration import round_status

            round_status.adapt_supplied_petab(self.ctx)
            if self.from_module is None:
                self.from_module = "estimation"
                # implied, not asked for: this decides whether a resume keeps
                # its finished estimation (see round_status.enter)
                self.entry_implied = True
                self.ledger.append(
                    "note",
                    module="seed",
                    note="supplied/petab implies entry at "
                    "estimation (agents skipped, gates not)",
                )

    # ------------------------------------------------------------ main loop
    def run(self) -> int:
        try:
            return self._run()
        finally:
            # the time account is written whatever ended the process — a
            # finished run, a pause at a gate, a stop, an interrupt. Written
            # LAST and not checkpointed: a checkpoint after it would be time
            # the account cannot see, and the checkpoint taken before it (at
            # run_end, at the pause) restores to a record whose account
            # `derive` rebuilds from the ledger.
            timing.write(self.ctx)
            timing.detach()
            # the materialised inputs (a temporary directory) are done with;
            # atexit stays as the fallback for a process that dies earlier
            run_folder.release(getattr(self, "inputs", None))

    def _run(self) -> int:
        try:
            intent_module.run(self.ctx)
            self._seed_round0()
            if self.from_module:
                from octomod.orchestration import round_status

                self._enter_at(round_status)
            if self.ctx.intent["inference_target"] == "mechanism_discrimination":
                return self._run_discrimination()
            return self._run_single_model_loop()
        except (ModuleFailure, GateFailure, AgentCallError) as e:
            # A GateFailure also arrives from the per-call prompt byte cap, the
            # one blocking gate outside a module's gate set. Every stop ends with
            # a run_end row, so a stopped run never reads as one in progress.
            # Two stops are resumable, and the row says so, so run_guard lets a
            # plain resume through: one at that byte cap (every artifact is in
            # the record, no answer outstanding), and a refused gate note (every
            # artifact is in the record, and the gate whose answer was cleared
            # is the next thing the resume asks).
            gate_id = getattr(getattr(e, "result", None), "gate_id", None)
            if isinstance(e, NoteRefused):
                resumable = {"resumable": True, "gate": e.gate}
            elif gate_id == "agent_prompt_bytes":
                resumable = {"resumable": True, "gate_id": gate_id}
            else:
                resumable = {}
            self.ledger.append("run_end", outcome="stopped", reason=str(e), **resumable)
            commit_run(self.store, None, why="run_end")
            print(f"\nRUN STOPPED: {e}", file=sys.stderr)
            if isinstance(e, NoteRefused):
                print(
                    f"  the run is not over: the answer at {e.gate} was refused "
                    f"and cleared, and the resume asks {e.gate} again.\n"
                    f"  answer with: the same run command plus --gate-answer y "
                    f'--gate-note "<a note the card accepts>" (the refusal '
                    f"above says which), or --gate-answer n to stop; without "
                    f"--gate-answer the card is shown again",
                    file=sys.stderr,
                )
            # a link the terminal opens, not a path to retype
            print(
                "  "
                + humangate_module.doc_link(self.root, "artifacts and gate evidence")
            )
            return 1
        except PolicyUncovered as e:
            # benchmark: the policy file is the specification, and it has a
            # hole. Naming the gate is the whole value — never invent an answer.
            self.ledger.append(
                "run_end",
                outcome="stopped",
                reason=str(e),
                module=e.module,
                policy_profile=(self.policy.profile if self.policy else None),
                policy_sha=(self.policy.sha if self.policy else None),
            )
            commit_run(self.store, None, why="run_end")
            print(f"\nRUN STOPPED: {e}", file=sys.stderr)
            print(
                f"  the {self.policy.profile if self.policy else '?'} policy "
                f"answers no gate it does not cover: declare an answer for "
                f"{e.module!r} in {self.policy.source if self.policy else '?'}, "
                f"or run a profile that pauses for a human.",
                file=sys.stderr,
            )
            print(
                "  "
                + humangate_module.doc_link(self.root, "artifacts and gate evidence")
            )
            return 1
        except humangate_module.GatePending as g:
            # a pause is a place the process ends; the record must
            # be current there too, gate answered or not. Silent (no ledger
            # row), like the run_end commits: `gate_pending` and `run_end` are
            # the rows readers expect to find LAST (suplit, the front end).
            commit_run(self.store, None, why="gate_pending")
            print(
                f"\nPAUSED at human gate '{g.payload['module']}' — question "
                f"written to the record's "
                f"{humangate_module.pending_path(self.root).key} "
                f"(./run.sh pending --run-id {self.store.run_id})"
            )
            print(
                "answer with: the same run command plus "
                '--gate-answer y|n [--gate-note "..."]'
            )
            return 3
        except KeyboardInterrupt:
            self.ledger.append("run_end", outcome="interrupted")
            commit_run(self.store, None, why="run_end")
            raise
        except Exception as e:  # noqa: BLE001
            # Record the crash, then let the traceback out: without a run_end a
            # crash reads as a run in progress. `crashed` is not an ending for
            # the run guard; like a kill, the run resumes from its markers.
            self.ledger.append(
                "run_end", outcome="crashed", reason=f"{type(e).__name__}: {e}"
            )
            commit_run(self.store, None, why="run_end")
            print(f"\nRUN CRASHED: {type(e).__name__}: {e}", file=sys.stderr)
            raise

    def _enter_at(self, round_status) -> None:
        """Modular entry: validate upstream slots of the latest round, mark
        them passed, invalidate the entry module and everything after it.
        On a fresh run the latest round is round 0 with the seeded artifacts;
        on an existing run it is wherever the run got to."""
        rounds = tree.round_indices(self.root)
        self.ctx.round_idx = rounds[-1] if rounds else 0
        round_status.enter(
            self.ctx, self.from_module, invalidate=not self.entry_implied
        )
        self.ctx.round_idx = 0  # the loops replay from the top over markers

    def _run_discrimination(self) -> int:
        """One round: propose candidates -> gate each -> fit each -> AIC
        discrimination + selection uncertainty. The revision loop does not
        run for this goal; further rounds come from space expansion."""

        self.ctx.round_idx = 0
        print("\n===== mechanism discrimination =====")
        cand_ids = model_module.run(self.ctx)
        if not cand_ids:
            raise ModuleFailure("mechanism discrimination needs a candidate set")
        return self._fit_and_select(cand_ids)

    def _fit_and_select(self, cand_ids: list[str]) -> int:
        """Assemble, compile, fit and select, restarting the whole step when a
        human asks for a different assembly at the cost gate, or when the
        engine sends a compile failure back to the observation agent.

        The loop sits out here because the cost boundary is asked once for the
        whole candidate set, several frames after the last assembly, and a
        compile failure comes later still. Re-entry is cheap: `data` is
        marker-skipped, and the request itself deleted the assembly caches.
        """
        from octomod.orchestration.interaction import human_redraft as _hr

        while True:
            try:
                return self._fit_and_select_once(cand_ids)
            except _hr.RedraftRequested as req:
                self.ctx.cache["_human_feedback"] = _hr.context_for(
                    req.text, req.role, source=req.source
                )
                if req.source == _hr.ENGINE:
                    print(
                        f"  → re-assembling all candidates: the engine sent a "
                        f"compile failure back to {req.role}"
                    )
                else:
                    print(f"  → re-assembling all candidates: {req.text[:80]}")

    def _assemble_and_approve(self) -> None:
        """S3 and the compile card for the single model, restarting S3 when a
        human asks the assembly agents for a different assembly at the card.

        The same card as the candidate path's (`compile_gate`), asked after the
        module rather than inside it, so a re-entry that skips S3 still asks it.
        """
        from octomod.orchestration.interaction import human_redraft as _hr

        while True:
            assembly_module.run(self.ctx)
            try:
                return compile_gate.ask(self.ctx, [None])
            except _hr.RedraftRequested as req:
                self.ctx.cache["_human_feedback"] = _hr.context_for(req.text, req.role)
                print(f"  → re-assembling at your request: {req.text[:90]}")

    def _remerge_stale_candidates(self, cand_ids: list[str]) -> None:
        """After a battery re-ask rewrote the round's `shared_assembly`, every
        candidate whose `assembly` carries an older `_shared_version` is
        merged again and re-batteried, so the set compared shares one assembly."""
        shared = (self.ctx.round / "shared_assembly").get(None)
        if shared is None:
            return
        current = int((shared or {}).get("_version", 0))
        if current == 0:
            return
        for cid in cand_ids:
            with as_candidate(self.ctx, cid):
                asm = self.ctx.work / "assembly"
                have = int((asm.get(None) or {}).get("_shared_version", 0))
                if have >= current:
                    continue
                self.ledger.append(
                    "note",
                    module="assembly",
                    round_idx=self.ctx.round_idx,
                    note=f"candidate {cid}: re-merged against the re-asked shared assembly (v{have} -> v{current})",
                )
                self.ctx.marker("s3").delete()
                asm.delete()
                print(
                    f"\n--- re-assembling candidate {cid} against the repaired shared assembly ---"
                )
                assembly_module.run(self.ctx)

    def _fit_and_select_once(self, cand_ids: list[str]) -> int:
        """Assemble, compile, fit and criterion-select a candidate set.

        Shared by mechanism discrimination (the agent proposes whole rival
        mechanisms) and by a model-space search (the engine builds the models
        over the axes the agent declared and the human bought), so the
        selection reporting — AIC weights, the indistinguishable set,
        model-averaged held-out prediction — is identical either way.
        """
        data_module.run(self.ctx)
        # the whole set, for a rebuild after an engine redraft: a candidate
        # dropped at S3 below still holds a merge of the old assembly
        asked = list(cand_ids)
        # a resume whose agent never answered the engine's finding gets it back
        compile_feedback.restore(self.ctx)
        # a resolve failure on a candidate whose shared assembly passed on
        # another is that candidate's own defect: dropped with a note, the
        # rest continue
        kept: list[str] = []
        for cid in cand_ids:
            with as_candidate(self.ctx, cid):
                print(f"\n--- assembling candidate {cid} ---")
                try:
                    assembly_module.run(self.ctx)
                    kept.append(cid)
                except assembly_module.CandidateDefect as e:
                    self.ledger.append(
                        "candidate_dropped",
                        module="assembly",
                        round_idx=self.ctx.round_idx,
                        candidate=cid,
                        reason=e.reason,
                    )
                    print(f"  ✗ candidate {cid} dropped: {e.reason[:160]}")
        if not kept:
            raise ModuleFailure(
                "every candidate was dropped at the S3 battery — nothing left to fit"
            )
        cand_ids = kept
        # a re-ask rewrote the shared assembly: candidates merged against the
        # older one are re-merged so the set being compared shares one assembly
        self._remerge_stale_candidates(cand_ids)
        compile_feedback.consumed(self.ctx)
        # the round's decision record is written inside each candidate's S3
        # pass, before a drop is ledgered here, so it is refreshed once those
        # rows exist
        from octomod.reporting.render import decisions_md

        (self.ctx.round / "decisions_md").put_text(decisions_md(self.ctx.round))

        compile_gate.ask(self.ctx, cand_ids)

        # A candidate whose fit is already in the record (an expansion round's
        # base) costs nothing: it goes last, so the budget gate is asked on one
        # that does cost, and it is named on that card instead of being probed.
        order, carried_lines, n_approved = self._order_by_fit_on_disk(cand_ids)
        failed: list[str] = []
        for cid in order:
            with as_candidate(self.ctx, cid):
                print(f"\n--- fitting candidate {cid} ---")
                try:
                    n_this = cost_profile.run(
                        self.ctx,
                        ask_human=(n_approved is None),
                        n_candidates=max(1, len(cand_ids) - len(carried_lines)),
                        preapproved_n=n_approved,
                        carried_lines=carried_lines,
                    )
                    # the round's approval is the first one; a candidate whose
                    # budget was re-asked (its probe did not match) fits with its
                    # own answer, which never becomes the others'
                    if n_approved is None:
                        n_approved = n_this
                    estimation_module.run(self.ctx, n_this)
                except cost_profile.BudgetDeclinedForCandidate as e:
                    # `n` to a budget gate re-asked for this candidate drops it by
                    # name and the round continues (`n` at the round's first
                    # budget gate stops the run). A resume replays this loop from
                    # the first candidate: an answer read back from the record was
                    # ledgered as the drop when it was given, and one decline is
                    # one drop
                    if e.remembered:
                        self.ledger.append(
                            "note",
                            module="cost_boundary_estimation",
                            round_idx=self.ctx.round_idx,
                            candidate=cid,
                            note=(
                                f"candidate {cid}: its estimation budget was "
                                f"declined earlier this round "
                                f"({cost_profile.DECLINED_KEY}) — not asked again"
                            ),
                            budget_decline_remembered=True,
                        )
                        print(
                            f"  ✗ candidate {cid} dropped: the human declined its "
                            f"estimation budget earlier this round "
                            f"({cost_profile.DECLINED_KEY}) — not asked again"
                        )
                    else:
                        self.ledger.append(
                            "candidate_dropped",
                            module="cost_boundary_estimation",
                            round_idx=self.ctx.round_idx,
                            candidate=cid,
                            reason=f"human declined the re-asked estimation budget — {e}",
                            human_declined_budget=True,
                        )
                        print(
                            f"  ✗ candidate {cid} dropped: the human declined its "
                            f"estimation budget — {str(e)[:160]}"
                        )
                    failed.append(cid)
                except Exception as e:
                    if _is_control_flow(e):
                        raise
                    # a failure that names the observation model goes back to
                    # its author first, once per round (raises RedraftRequested);
                    # otherwise a model AMICI cannot build (a C++ error in the
                    # generated code) is this candidate's defect, not the
                    # round's: it is dropped with the reason and the others fitted
                    spent_before = compile_feedback.spent(self.ctx.round)
                    compile_feedback.send_back_if_owed(self.ctx, cid, e, asked)
                    head = f"{type(e).__name__}: {str(e)[:300]}"
                    reason = compile_feedback.drop_reason(head, spent_before)
                    self.ledger.append(
                        "candidate_dropped",
                        module="candidate_compile",
                        round_idx=self.ctx.round_idx,
                        candidate=cid,
                        reason=reason,
                    )
                    print(f"  ✗ candidate {cid} dropped: {reason[:220]}")
                    failed.append(cid)
        fitted = [c for c in cand_ids if c not in failed]
        if not fitted:
            raise ModuleFailure(
                "every candidate failed to compile or fit — the reasons are the "
                "candidate_dropped rows in the ledger"
            )

        report = evaluation_module.run(
            self.ctx,
            cand_ids=fitted,
            rounds_left=rounds_left_after(self.ctx.round_idx, self.max_rounds),
        )
        expanded = self._maybe_expand_space(report, fitted)
        if expansion_took_over(expanded):
            # the expanded round ran to its own end and wrote the record; this
            # round must not write a second one over it
            return expanded
        # T2' is computed per candidate; every candidate failing the held-out
        # cell ends the run as unmet, as on the single-model path
        t2_ok = bool(report.get("t2prime_passed", True))
        self.ledger.append(
            "run_end",
            outcome="completed" if t2_ok else "completed_t2prime_unmet",
            winner=report["discrimination"]["winner"],
            decisive=report["discrimination"]["decisive"],
        )
        commit_run(self.store, None, why="run_end")
        print(
            "\n===== run complete ====="
            if t2_ok
            else "\n===== run ended: T2prime UNMET on every candidate ====="
        )
        print("  " + humangate_module.doc_link(self.root, "run record"))
        print(
            "  "
            + humangate_module.doc_link(
                self.ctx.reports_dir / "report.html", "final report"
            )
        )
        self._write_analysis()
        return 0 if t2_ok else 1

    def _order_by_fit_on_disk(
        self, cand_ids: list[str]
    ) -> tuple[list[str], list[str], int | None]:
        """(fitting order, card lines for the candidates already fitted, the
        start count to fit with if no gate needs asking).

        Asked at the start count the budget gate will propose: a candidate
        whose fit is in the record for at least that many starts, with the
        round's solver settings, is reused — unless the answer asks for more
        starts or other settings (`tighten`/`adjoint` are recorded for the
        whole round), which the line says. With every candidate's fit in the
        record nothing is spent and no budget is asked; the proposal is used
        as the approval."""
        n_default = cost_profile.proposed_n_starts(self.ctx)
        on_disk: dict[str, dict] = {}
        for cid in cand_ids:
            with as_candidate(self.ctx, cid):
                if self.ctx.marker("cost").exists():
                    continue  # already through the cost module: nothing to decide
                found = cost_profile.fit_already_on_disk(self.ctx, n_default)
                if found is not None:
                    on_disk[cid] = found
        order = [c for c in cand_ids if c not in on_disk] + [
            c for c in cand_ids if c in on_disk
        ]
        lines = []
        for cid, f in on_disk.items():
            best = f.get("best_fval")
            lines.append(
                f"{cid}: already fitted — {f['from']} ({f['n_starts']} starts"
                + (f", best -log L {float(best):.2f}" if best is not None else "")
                + f"): reused, not probed, not in the projection below (an n= "
                f"above {f['n_starts']}, `tighten` or `adjoint` here refits it)"
            )
        n_approved = None
        if on_disk and len(on_disk) == len(cand_ids):
            n_approved = n_default
            self.ledger.append(
                "note",
                module="cost_boundary_estimation",
                round_idx=self.ctx.round_idx,
                note=(
                    f"budget gate not asked: every candidate's fit is already in "
                    f"the record for {n_default} starts ({sorted(on_disk)}) — "
                    f"nothing to spend"
                ),
                fits_on_disk=sorted(on_disk),
            )
            print(
                "  every candidate's fit is already in the record — no budget to "
                "approve, nothing is refitted"
            )
        elif on_disk:
            self.ledger.append(
                "note",
                module="cost_boundary_estimation",
                round_idx=self.ctx.round_idx,
                note=(
                    f"fits already in the record for {sorted(on_disk)} — fitted "
                    f"last and "
                    f"left out of the projection: "
                    + "; ".join(f"{c} from {f['from']}" for c, f in on_disk.items())
                ),
                fits_on_disk=sorted(on_disk),
            )
        return order, lines, n_approved

    def _another_round_asked(self, round_idx: int) -> bool | None:
        """The human's answer to "another round?" at that round's verdict gate.

        True / False / None, read from the round's `decisions/evaluation_verdict` —
        where `ask_once` put it durably, so a resumed run honours the same
        answer instead of re-deriving it. A missing verdict is normal (a
        policy-answered or `--auto-approve` run), so absence means "said
        nothing" and the default applies.
        """
        from octomod.workflow_modules.evaluation.engine import (
            parse_another_round_request,
        )

        vnode = tree.round_node(self.root, round_idx) / "decisions/evaluation_verdict"
        try:
            verdict = vnode.get({})
        except Exception as e:
            self.ledger.append(
                "note",
                module="loop",
                round_idx=round_idx,
                note=f"{vnode.key} unreadable, another-round note not read: {e}",
                swallowed=True,
            )
            return None
        if not isinstance(verdict, dict):
            return None
        return parse_another_round_request(verdict.get("note"))

    def _maybe_expand_space(
        self, report: dict, cand_ids: list[str], _redrafted: bool = False
    ):
        """Offer to enlarge the model space after a selection round.

        The expansion agent reads the misfit evidence and says what the space
        was missing; the human decides whether to buy it, and the enlarged
        space is seeded as the next round and fitted. Returns None when no
        expansion ran, else the exit code of the round it ran. The decision is
        recorded in the round's `expansion`, so a resume neither re-calls nor
        re-asks.
        """
        decision = self.ctx.round / "expansion"
        decided = decision.get(None)
        if decided is not None:
            if not decided.get("expanded"):
                print(
                    "  (expansion already declined for this round — resumed "
                    f"from {decision.key})"
                )
                return None
            print(
                "  (expansion already decided for this round — resumed from "
                f"{decision.key})"
            )
            self.ctx.round_idx = decided["next_round"]
            cand_prev = model_module.run(self.ctx)
            if not cand_prev:
                raise ModuleFailure("the enlarged space produced no candidate set")
            return self._fit_and_select(cand_prev)

        ev = report.get("misfit_evidence") or {}
        rounds_left = rounds_left_after(self.ctx.round_idx, self.max_rounds)
        if rounds_left <= 0:
            return None

        # The human's answer at the verdict gate decides; the indicators only
        # set the default. `_another_round_asked` is the one reader of it for
        # both loops, from `decisions/evaluation_verdict`, so a resumed run honours it
        # too.
        requested = self._another_round_asked(self.ctx.round_idx)
        go, why = should_expand(
            bool(ev.get("open")),
            rounds_left,
            requested,
            bool(self.spec.get("search.expand_on_misfit", True)),
        )
        if not go:
            if requested is False:
                print(f"  ({why})")
            return None
        # the offer and the round it seeds are built from this round's report:
        # refused by name before anything reads it, or is paid for on it
        from octomod.orchestration import round_seed as _seed

        _seed.require_evaluation(self.ctx)
        # the second pass after a redraft is the same offer, not a new request:
        # its note and banner are already on the ledger and the screen
        if requested is True and not ev.get("open") and not _redrafted:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    f"expansion {why} — the indicators set the default, not "
                    f"the decision"
                ),
                human_expansion_request=True,
                misfit_open=False,
            )

        winner = report["discrimination"]["winner"]
        self._banner(
            (
                "MODEL SPACE EXPANSION, REDRAFTED AT YOUR REQUEST — "
                if _redrafted
                else "MODEL SPACE EXPANSION — "
            )
            + (
                "the selected model still carries structural-misfit evidence"
                if ev.get("open")
                else "bought at the verdict gate with no indicator open"
            )
            + "; the agent proposes what the space was missing and you decide "
            "whether to buy it"
        )
        # What the space was missing is a question about residual structure, so
        # the agent gets structure, not scalar summaries: every candidate's
        # time-resolved residuals, the cross-model table of measurements no
        # candidate could fix, and the identical-prediction noise controls.
        from octomod.workflow_modules.evaluation.residuals import expansion_payload

        try:
            # `report` is `{**core, ...}`, so it answers every key the payload
            # reads and no record re-read is needed
            diagnostics = expansion_payload(self.ctx, cand_ids, winner, report)
        except Exception as e:  # never let a diagnostic kill the round
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=f"residual diagnostics failed: {e}",
            )
            diagnostics = {"error": str(e)}
        from octomod.workflow_modules.model import tried_models as _tried

        declared_axes = _tried.declared_axes_this_run(self.root)
        # with the knowledge module's output in the run, the floor of the round
        # this expansion seeds is written before the agent is asked: this
        # round's floor lowered by its step, or what a person set at this card
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        grounded = _rxe.active(self.ctx)
        next_floor = self._schedule_next_floor() if grounded else None
        # the biology construction had: the domain packs, and (research on)
        # what the research role finds about mechanisms described for the
        # system that the selected model lacks — one research call per
        # expansion round, frozen and reused on a resume
        biology, biology_lines = model_module.expansion_biology(
            self.ctx,
            candidate_work(self.ctx, winner) / "model",
            ev,
            winner,
            floor=next_floor,
        )
        context = {
            "intent": self.ctx.intent,
            # the lab note, so a residual it already explains (drift, handling
            # artefacts) is not proposed a mechanism
            "experiment_description": self.ctx.description,
            **biology,
            "selected_model": winner,
            "selection_table": report["discrimination"]["candidates"],
            # the whole run, not just this round's ids, so a mechanism rejected
            # in an earlier round is not re-proposed and re-paid for
            "models_fitted_this_run": _tried.models_fitted_this_run(self.root),
            "declared_axes": declared_axes,
            "untested_axes": _tried.untested(declared_axes),
            "untested_first": _tried.UNTESTED_FIRST_NOTE,
            # a quantity the experiment calls constant, which the fitted model
            # moves, is a named place to look before inventing a law
            "declared_constant_drift": report.get("declared_constants")
            or ((self.ctx.round / "evaluation").get(None) or {}).get(
                "declared_constants"
            )
            or {},
            "misfit_evidence": ev,
            # column arrays at reporting precision, agent view only
            "residual_diagnostics": _agent_payload.for_agents(diagnostics),
            "evaluation_report": {
                k: report[k]
                for k in ("fit", "chi2_per_dof", "parameters")
                if k in report
            },
        }
        # which fitted parameters the bounds are holding back, and how hard: the
        # values alone read a bound-limited fit as a converged one
        from octomod.workflow_modules.evaluation.residuals import (
            BOUND_PRESSURE_NOTE,
            bound_pressure,
        )

        try:
            _pressure = bound_pressure(self.ctx, cand_ids)
        except Exception as e:  # a diagnostic never kills the round
            _pressure = {}
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=f"bound pressure could not be read: {e}",
            )
        if any(_pressure.values()):
            context["bound_pressure"] = {
                "per_candidate": _pressure,
                "how_to_read_this": BOUND_PRESSURE_NOTE,
            }
        # the interpretation agent's hypotheses and open questions about the
        # same fits, handed on as suggestions to test
        _interp = report.get("interpretation") or {}
        _hyp = {
            k: _interp[k]
            for k in (
                "recommendation",
                "diagnosis",
                "misfit_hypotheses",
                "cannot_distinguish",
            )
            if _interp.get(k)
        }
        if _hyp:
            context["interpretation_hypotheses"] = {
                **_hyp,
                "how_to_read_this": (
                    "The interpretation agent read the same fits and residuals "
                    "and wrote these hypotheses and open questions. They are "
                    "SUGGESTIONS TO TEST, not decisions: where the data can "
                    "separate one from the selected model it is a candidate axis. "
                    "Say in your diagnosis which you took up and why you left the "
                    "others."
                ),
            }
        # the literature construction was given, from the snapshot S0 froze,
        # with the same lit_k ids construction cites
        from octomod.workflow_modules.knowledge import supplied_literature as _lit

        _sup = _lit.normalized(_lit.load_frozen(self.root))
        if _sup:
            context["supplied_literature"] = {
                "items": _sup,
                "how_to_read_this": (
                    "Literature the person who staged this problem already has, as "
                    "typed claims (origin: human) — the same items construction was "
                    "given. Use what they say about MECHANISM: which species acts "
                    "on which, through which step, on what timescale, and what the "
                    "lab note excludes on their strength. Cite an item by its id "
                    "(lit_1) in an axis's rationale where it motivates or rules out "
                    "a proposal. You see the claim, never the document; do not "
                    "attribute to an item anything beyond its supports/quote."
                ),
            }
        # the data's condition attributes and their values: what a
        # `split_parameter` axis may split by (from the engine's condition keys)
        _long = self._long_table()
        if _long is not None:
            try:
                _keys = _long["condition_key"].dropna().astype(str)
                _attrs: dict[str, set] = {}
                for _k in set(_keys):
                    for _part in _k.split("|"):
                        if "=" in _part:
                            _a, _v = _part.split("=", 1)
                            _attrs.setdefault(_a, set()).add(_v)
                if _attrs:
                    context["condition_attributes"] = {
                        a: sorted(v) for a, v in sorted(_attrs.items())
                    }
            except Exception:
                pass
        shared_asm = self.ctx.round / "shared_assembly"
        # observation axes name its ids: the selected model's assembly (the
        # shared one with its overlay), which the next round starts from
        winner_asm = self._assembly_of(winner)
        if winner_asm is not None:
            context["assembly"] = winner_asm
        proposal = self._expansion_proposal(context, cand_ids)
        # Tier A: every free check runs before the human pays
        from octomod.workflow_modules.model import model_space as _ms

        base_antimony, base_params = self._model_of(winner)
        # axes the indistinguishable set disagreed on were not decided: the next
        # round's base drops them and re-declares them live (with none
        # undecided, the base is the winner)
        carried, base_antimony, base_params, undecided_seed = self._carry_undecided(
            report, winner, base_antimony, base_params
        )
        win_row = next(
            (c for c in report["discrimination"]["candidates"] if c["id"] == winner), {}
        )
        dof = (
            int(win_row.get("n_est") or 0),
            int(win_row.get("n_data") or 0),
            float(self.spec.get("gates.dof.max_par_per_datapoint", 1.0)),
        )
        t_end = float(self.ctx.testcase.get("t_end", 100.0))
        max_models = int(self.spec.get("search.max_models", 8))
        # the assembly the new axes are validated against is the one the next
        # round starts from
        if undecided_seed is None:
            base_asm = winner_asm
        elif undecided_seed.get("candidate"):
            base_asm = self._assembly_of(undecided_seed["candidate"])
        else:
            shared0 = shared_asm.get(None)
            base_asm = (
                assembly_edit.apply_overlay(
                    shared0, undecided_seed["overlay"], assembly_for_refs=shared0
                )
                if shared0 is not None
                else None
            )

        # what a `split_parameter` axis is resolved against: the data's own
        # condition attributes and the base's parameter rows
        split_ctx = self._split_context(base_asm, base_params, winner)
        carried_ids = {str(a.get("id")) for a in carried}
        undecided_ids = set(carried_ids)
        # the space is priced in the declared search mode (one axis at a time
        # on the base unless `search.lattice`); `lattice` in the answer buys
        # every combination for the next round, re-capped for it below
        price_mode = (
            _ms.LATTICE if self.spec.get("search.lattice", False) else _ms.CANDIDATES
        )

        def _tiers(prop: dict) -> tuple[list[dict], list[dict], int]:
            ax, dropped = _ms.validate_axes(
                self.ctx,
                prop.get("axes") or [],
                base_antimony,
                {str(p.get("id")) for p in base_params},
                module="revision",
                base_assembly=base_asm,
                dof=dof,
                split_context=split_ctx,
            )
            # the carried axes are already validated (they ran this round) and
            # are not the agent's to re-propose; they join the lattice here so
            # the ladder and the ceiling see the whole live space at once.
            # Order: undecided (the data failed to settle them), then
            # declared-but-never-fitted, then the agent's new proposals.
            proposed_ids = {str(a.get("id")) for a in ax} | carried_ids
            untested_carried = self._carry_untested(
                declared_axes,
                prop,
                base_antimony,
                {str(p.get("id")) for p in base_params},
                proposed_ids,
                base_assembly=base_asm,
                obs_taken=self._obs_targets(carried + ax),
            )
            ax = carried + untested_carried + _ms.by_priority(ax)
            carried_ids.update(str(a.get("id")) for a in untested_carried)
            n_viable = _ms.n_models(len(ax), price_mode)
            if ax:  # Tier B: the whole ladder on every model, before the gate
                capped, _over = _ms.cap_axes(
                    ax, max_models, carried_ids, mode=price_mode
                )
                ax, dropped_b, n_viable, _failing = _ms.pregate_ladder(
                    self.ctx,
                    base_antimony,
                    base_params,
                    capped,
                    max_models,
                    t_end,
                    module="revision",
                    mode=price_mode,
                )
                dropped = dropped + dropped_b
            return ax, dropped, n_viable

        axes, dropped_axes, n_viable = _tiers(proposal)
        # one bounded re-call: the agent gets the complete named-failure
        # dossier from both tiers plus the legal reaction ids; persisted so a
        # resume never re-pays
        redraft_budget = int(self.spec.get("search.expansion_redraft", 1))
        if dropped_axes and redraft_budget > 0 and not proposal.get("stop_instead"):
            proposal, axes, dropped_axes, n_viable = self._expansion_redraft(
                context, cand_ids, proposal, dropped_axes, _tiers, base_antimony
            )
        # what the agent says acts in the system but this data cannot separate:
        # on the card, in the round's `expansion`, on the run page
        beyond = _ms.beyond_this_data(proposal)
        # the literature searches the agent asked for, read from the round's
        # state so a resumed card says the same
        research_lines = model_module.requested_research_lines(
            ((self.ctx.round / "expansion_diagnostics").get({}) or {}).get(
                "research_requests"
            )
        )
        if proposal.get("stop_instead") or not axes:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=f"no expansion proposed: "
                f"{str(proposal.get('diagnosis'))[:300]}"
                + (
                    f"; {len(beyond)} mechanism(s) named beyond this data "
                    f"(expansion_diagnostics, and the run page)"
                    if beyond
                    else ""
                ),
            )
            print(
                f"  agent proposes no expansion: "
                f"{str(proposal.get('diagnosis'))[:300]}"
            )
            for line in research_lines + _ms.beyond_card_lines(beyond):
                print(f"  {line}")
            self._discard_unseeded_floor()
            return None
        # the deterministic order: undecided axes, then the carried untested
        # ones, then the agent's by priority
        ordered = (
            [a for a in axes if a["id"] in undecided_ids]
            + [
                a
                for a in axes
                if a["id"] in carried_ids and a["id"] not in undecided_ids
            ]
            + _ms.by_priority([a for a in axes if a["id"] not in carried_ids])
        )
        # with the knowledge module's output in the run, what each axis adds to
        # the base, annotated against the round's dossier — which holds what the
        # expansion's own search admitted — and recorded before the card reads
        # it back; an axis adding a conversion graded below the floor of the
        # round it would be fitted in is refused from the offer (`held`), and a
        # lower floor answered at the card can admit it again
        axis_support = _rxe.annotate_axes(
            self.ctx, ordered, base_antimony, base_params, winner
        )
        held: list[dict] = []
        held_refusals: dict[str, list[dict]] = {}
        if axis_support is not None and next_floor is not None:
            ordered, held, held_refusals = self._split_by_floor(
                ordered, axis_support, next_floor
            )
        # the hard ceiling, applied once over the whole live space
        axes, over_cap = _ms.cap_axes(
            ordered,
            max_models,
            carried_ids,
            mode=price_mode,
        )
        if over_cap:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=f"ceiling search.max_models={max_models}: expansion "
                f"axes {[a['id'] for a in over_cap]} not bought this "
                f"round (priority order)",
            )

        lines = [f"the selected model {winner} still shows:"]
        lines += [f"  · {r}" for r in ev.get("reasons", [])]
        diag_state = self.ctx.round / "expansion_diagnostics"
        if diag_state.exists():
            steps = diag_state.get().get("steps") or []
            n_req = sum(len(st.get("results") or []) for st in steps)
            if n_req:
                lines.append(
                    f"the agent requested {n_req} engine-run diagnostic(s) "
                    f"before proposing (expansion_diagnostics): "
                    + ", ".join(
                        r.get("kind", "?")
                        for st in steps
                        for r in st.get("results") or []
                    )
                )
        # what the research role retrieved for this proposal, when it ran, and
        # the searches the agent asked for: its questions, the items each found
        lines += biology_lines
        lines += research_lines
        lines += self._expansion_redraft_lines(proposal)
        lines += [
            "",
            f"diagnosis: {str(proposal.get('diagnosis'))[:400]}",
            "",
            "proposed new axes:",
        ]
        lines += _ms.expansion_axis_lines(axes)
        for a in over_cap:
            lines.append(
                f"  · NOT BOUGHT (ceiling {max_models} models): {a['id']} — "
                f"lowest priority; remains on record"
            )
        for d in dropped_axes:
            lines.append(f"  · DROPPED {d['id']}: {d['reason'][:300]}")
        if axis_support is not None:
            lines += _rxe.axis_card_lines(
                (self.ctx.round / _rxe.AXIS_SUPPORT_KEY).get(None)
            )
        if next_floor is not None:
            lines += self._floor_card_lines(next_floor, held, held_refusals)
        # the base is search policy: the agent may propose one, the human
        # decides; the criterion's ranking of the fitted models is untouched
        rec_base = proposal.get("expand_from") or {}
        rec_id = str(rec_base.get("candidate_id") or "").strip()
        valid_bases = {c["id"] for c in report["discrimination"]["candidates"]}
        base_menu: list[str] = []
        if rec_id and rec_id in valid_bases and rec_id != winner:
            base_menu = [
                f"BASE FOR THE ENLARGED SPACE — default is the winner "
                f"{winner}; the agent recommends {rec_id} instead:",
                f"  why: {str(rec_base.get('why', ''))[:200]}",
                f"  a criterion measures fit-plus-parsimony now, not "
                f"expandability. Answer 'y base: {rec_id}' to build on it, or "
                f"plain 'y' for the winner.",
            ]
        elif rec_id and rec_id not in valid_bases:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    f"agent proposed expand_from={rec_id!r}, which is not a "
                    f"fitted candidate of this round {sorted(valid_bases)} — "
                    f"ignored; the base stays the winner"
                ),
            )
        lines.append(
            f"  → refits {min(n_viable, _ms.n_models(len(axes), price_mode))} "
            f"model(s) on top of {winner} — "
            f"{_ms.search_mode_line(len(axes), price_mode)}; every one already "
            f"passed the pre-compile ladder"
        )
        lines += _ms.beyond_card_lines(beyond)
        # what was declared earlier and never fitted, and what the proposal
        # said about it: a free axis nobody tried is the cheapest thing left
        lines += _tried.resemblance_lines(axes, _tried.snapshot_if_enabled(self.ctx))
        untested_lines = _tried.untested_card_lines(declared_axes)
        if untested_lines:
            # "untested first" is advisory: a gap is a line here, never a
            # refused proposal; tried_models owns what "accounted for" means
            lines += untested_lines
            lines += _tried.untested_verdict_lines(
                proposal,
                declared_axes,
                carried={str(a["id"]) for a in axes if a.get("carried_untested")},
                buy_form=True,
            )
        # record_decline=True is implicit and deliberate here: the offer cost an
        # agent call to produce, so a resume must not re-ask and re-pay for it
        approved, note = humangate_module.ask_once(
            self.ctx,
            self.ctx.round / "expansion_offer",
            "Buy this expansion and run another selection round?",
            lines,
            always_show=base_menu or None,
            module="revision",
            intent=self.ctx.intent,
            note_forms=(
                "base: <candidate_id>   build the enlarged space on that "
                "candidate instead of the winner",
                "lattice                fit every on/off combination of the "
                "new axes instead of one at a time on the base (off unless "
                "asked, since 2^k fits grow fast; re-capped at search.max_models)",
                "axes: +<id>, +<id>     also fit a declared axis this card does "
                "not carry — one the agent ruled out, or one fitted and beaten on "
                "an earlier base; checked against the base like any axis",
                "redraft: <what to change>   (with y) send this proposal back "
                "to the expansion agent with your words; the card is asked "
                "again on its new proposal and nothing is bought by this answer",
            )
            + (EXPANSION_FLOOR_FORMS if next_floor is not None else ())
            + ("(nothing)              one axis at a time on the winner",),
            consequences=(
                "the enlarged space is enumerated, fitted and "
                "selected again (another calibration per model)",
                "the run ends with the current selection and the "
                "misfit recorded as unexplained",
            ),
        )
        from octomod.orchestration.interaction import human_redraft as _hr

        if not approved:
            from octomod.orchestration.interaction import gate_note

            # a decline is recorded (the offer cost a call), so a redraft or a
            # floor written with `n` is NOT acted on — said, not dropped silently
            no_reading = gate_note.Reading()
            if _hr.parse(note):
                no_reading.unread["redraft"] = (
                    "the answer was no, so the run ends here; a redraft is asked "
                    "with y"
                )
            if next_floor is not None:
                for form in self._floor_forms_written(note):
                    no_reading.unread[form] = (
                        "the answer was no: no round is seeded, so no floor is set"
                    )
            if no_reading.unread:
                gate_note.report(
                    no_reading,
                    note,
                    ledger=self.ledger,
                    module="revision",
                    round_idx=self.ctx.round_idx,
                )
            if next_floor is not None:
                self._record_floor_refusals(held, held_refusals, next_floor)
            write_record(
                decision,
                ExpansionRecord,
                {
                    "expanded": False,
                    "why": "human declined the expansion",
                    "beyond_this_data": beyond,
                    **(
                        {
                            "floor": _floor_record(next_floor),
                            "refused_for_floor": [a["id"] for a in held],
                        }
                        if next_floor is not None
                        else {}
                    ),
                },
            )
            self._discard_unseeded_floor()
            commit_run(self.store, self.ledger, why="decision:revision")
            return None
        # `redraft:` sends the request and the proposal it is about back to the
        # expansion agent, and the card is asked again on the new proposal;
        # this answer buys nothing
        _redraft = _hr.parse(note)
        if _redraft:
            self._take_expansion_redraft(_redraft, note)
            return self._maybe_expand_space(report, cand_ids, _redrafted=True)
        # `search: <question>` spends the round's one targeted search on the
        # person's question when the agent did not, and asks the card again on
        # the axes annotated against what it admitted; this answer buys nothing
        searched, search_why = (
            self._take_person_search(note, winner)
            if next_floor is not None
            else (False, "")
        )
        if searched:
            return self._maybe_expand_space(report, cand_ids, _redrafted=True)

        from octomod.orchestration.interaction import gate_note

        base_reading = gate_note.Reading()
        if search_why:
            base_reading.unread["search:"] = search_why
        # `floor:` and `step:` set the floor of the round this expansion seeds,
        # as the person's; a held axis the new floor admits rejoins the offer
        final_floor = next_floor
        if next_floor is not None:
            final_floor = self._floor_answer(note, next_floor, base_reading)
            if _floor_record(final_floor) != _floor_record(next_floor):
                pool = axes + held
                axis_support = _rxe.annotate_axes(
                    self.ctx, pool, base_antimony, base_params, winner
                )
                axes, held, held_refusals = self._split_by_floor(
                    pool, axis_support, final_floor
                )
                axes, over_floor = _ms.cap_axes(
                    axes, max_models, carried_ids, mode=price_mode
                )
                over_cap = list(over_cap) + list(over_floor)
        # `axes: +<id>`: declared axes the human buys over the agent's
        # proposal; the ceiling keeps them ahead of the agent's own axes
        added = self._axes_bought_at_expansion(
            note,
            axes,
            declared_axes,
            proposal,
            base_antimony,
            base_params,
            base_asm,
            t_end,
            max_models,
            price_mode,
            base_reading,
        )
        added_ids = {a["id"] for a in added}
        if added:
            axes = axes + added
            keep = carried_ids | added_ids
            if not _ms.lattice_requested(note):
                axes, over_added = _ms.cap_axes(axes, max_models, keep, mode=price_mode)
                if over_added:
                    self.ledger.append(
                        "note",
                        module="revision",
                        round_idx=self.ctx.round_idx,
                        note=(
                            f"axes added with +<id>: search.max_models={max_models} "
                            f"admits {len(axes)} axes; not bought this round: "
                            f"{[a['id'] for a in over_added]}"
                        ),
                    )
                    print(
                        f"  the added axes fill the ceiling; not bought: "
                        f"{[a['id'] for a in over_added]}"
                    )
                    over_cap = list(over_cap) + list(over_added)
        # the next round's search mode: the declared one, or every combination
        # when the human wrote `lattice`, capped for that count
        next_mode = _ms.LATTICE if _ms.lattice_requested(note) else price_mode
        if next_mode != price_mode:
            base_reading.read["lattice"] = True
            axes, over_lattice = _ms.cap_axes(
                axes, max_models, carried_ids | added_ids, mode=next_mode
            )
            if over_lattice:
                self.ledger.append(
                    "note",
                    module="revision",
                    round_idx=self.ctx.round_idx,
                    note=(
                        f"`lattice` asked: search.max_models={max_models} admits "
                        f"{len(axes)} axes as a lattice; not bought this round: "
                        f"{[a['id'] for a in over_lattice]}"
                    ),
                )
                print(
                    f"  lattice: {len(axes)} axes fit the ceiling; not bought: "
                    f"{[a['id'] for a in over_lattice]}"
                )
                over_cap = list(over_cap) + list(over_lattice)
        # the human's answer picks the base; without an instruction it is the
        # winner
        base_id = winner
        # case-insensitive, like every other note parser: a human who writes
        # "BASE: M2" means it, and an unparsed note must never silently do
        # something else
        chosen = re.search(
            r"\b(?:base|expand_from)\s*[:=]\s*([A-Za-z0-9_+.-]+)",
            note or "",
            re.I,
        )
        if chosen:
            if chosen.group(1) in valid_bases:
                base_reading.read["base"] = chosen.group(1)
            else:
                base_reading.unread[f"base: {chosen.group(1)}"] = (
                    "not a fitted candidate of this round — the winner stays"
                )
        gate_note.report(
            base_reading,
            note,
            ledger=self.ledger,
            module="revision",
            round_idx=self.ctx.round_idx,
        )
        if chosen:
            want = chosen.group(1)
            if want in valid_bases:
                base_id = want
            else:
                self.ledger.append(
                    "note",
                    module="revision",
                    round_idx=self.ctx.round_idx,
                    note=(
                        f"the note asked to expand from {want!r}, which is not a "
                        f"fitted candidate of this round {sorted(valid_bases)} — "
                        f"the base stays the winner {winner}"
                    ),
                )
                print(
                    f"  the requested base {want!r} is not a fitted candidate of "
                    f"this round; building on the winner {winner} instead"
                )
        if base_id != winner:
            # a different base is a different lattice: re-validate and re-ladder
            # rather than fitting something other than what was priced
            base_antimony, base_params = self._model_of(base_id)
            kept, dropped_alt = [], []
            for a in axes:
                patch = a.get("on_antimony_patch")
                if not patch:
                    kept.append(a)  # observation axes do not touch the model
                    continue
                missing = _ms.undeclared_symbols(base_antimony, a)
                _, applies = _ms.apply_patch(base_antimony, patch)
                if missing or not applies:
                    dropped_alt.append(a["id"])
                else:
                    kept.append(a)
            if not kept:
                self.ledger.append(
                    "note",
                    module="revision",
                    round_idx=self.ctx.round_idx,
                    note=(
                        f"expanding from {base_id} would drop EVERY axis "
                        f"{dropped_alt} (their patches do not apply to it) — "
                        f"the base stays the winner {winner}"
                    ),
                )
                print(
                    f"  no axis applies to {base_id}; building on the winner "
                    f"{winner} instead"
                )
                base_id = winner
                base_antimony, base_params = self._model_of(winner)
            else:
                axes = kept
                carried = [a for a in carried if a["id"] in {k["id"] for k in kept}]
                self.ledger.append(
                    "note",
                    module="revision",
                    round_idx=self.ctx.round_idx,
                    note=(
                        f"human chose to expand from {base_id} rather than the "
                        f"criterion winner {winner}"
                        + (
                            f"; axes {dropped_alt} do not apply to it and were "
                            f"dropped"
                            if dropped_alt
                            else ""
                        )
                    ),
                )
                print(
                    f"  expanding from {base_id} (the human's choice, not the "
                    f"criterion winner {winner})"
                    + (f" — dropped {dropped_alt}" if dropped_alt else "")
                )

        # each bought axis carries what it adds, as annotated against the base
        # the next round builds on: the card's annotation, or a fresh one when
        # the answer moved the base or added axes after the card — and is held
        # to the floor again on that annotation
        if axis_support is not None and (base_id != winner or added):
            axis_support = _rxe.annotate_axes(
                self.ctx, axes, base_antimony, base_params, base_id
            )
            if final_floor is not None:
                axes, late, late_refusals = self._split_by_floor(
                    axes, axis_support, final_floor
                )
                held = held + late
                held_refusals.update(late_refusals)
        if final_floor is not None:
            self._record_floor_refusals(held, held_refusals, final_floor)
            if not axes:
                # the floor refused every axis: nothing is left to buy
                write_record(
                    decision,
                    ExpansionRecord,
                    {
                        "expanded": False,
                        "why": "every proposed axis adds a conversion below the "
                        "floor of the round it would be fitted in",
                        "beyond_this_data": beyond,
                        "floor": _floor_record(final_floor),
                        "refused_for_floor": [a["id"] for a in held],
                    },
                )
                self._discard_unseeded_floor()
                commit_run(self.store, self.ledger, why="decision:revision")
                print(
                    "  every proposed axis is refused at the floor "
                    f"{_rxe.band_text(_rxe.floor_band(final_floor))}: nothing to buy"
                )
                return None

        # Seed the next round with the new axes declared: from one fitted
        # candidate's group exactly (its model, its merged assembly with the
        # observation-axis choices it carried, and so its fit), or from the
        # rebuilt base plus the decided observation axes. `round_seed` is the
        # one place that decides what a round starts from (it writes the next
        # round's data, model, shared assembly and `model/seed`); undecided
        # axes stay live either way.
        from octomod.orchestration import round_seed as _seed

        nxt_idx = self.ctx.round_idx + 1
        nxt = tree.round_node(self.root, nxt_idx)
        if carried and base_id == winner:
            seed_cand = (undecided_seed or {}).get("candidate")
            why = "this round's base plus the decided axes" + (
                f" (= candidate {seed_cand}, fitted)" if seed_cand else " (rebuilt)"
            )
        else:
            seed_cand = base_id
            why = (
                f"the criterion winner {winner}"
                if base_id == winner
                else f"the human's base choice {base_id} (the winner was {winner})"
            )
        seed_record = _seed.seed_round(
            self.ctx,
            nxt,
            candidate=seed_cand,
            why=why,
            antimony=base_antimony,
            parameters=base_params,
            overlay=(undecided_seed or {}).get("overlay"),
            glossary_from=winner,
            # the base inherits the winner's decided observation patches; an
            # axis carried live again keeps its patch out of the base, so the
            # lattice can still switch it off
            carried=carried,
        )
        (nxt / "space" / "axes").put(
            [_rxe.with_support({**a, "frozen": False}, axis_support) for a in axes]
        )
        _ms.record_search_mode(
            nxt,
            next_mode,
            (
                "the human's `lattice` at the expansion gate"
                if next_mode != price_mode
                else "the declared search mode (search.lattice)"
            ),
        )
        write_record(
            decision,
            ExpansionRecord,
            {
                "expanded": True,
                "next_round": nxt_idx,
                "from_winner": winner,
                "expanded_from": base_id,
                "base_was_the_agents_recommendation": bool(
                    rec_id and base_id == rec_id and base_id != winner
                ),
                "axes": [a.get("id") for a in axes],
                "carried_undecided": [a.get("id") for a in carried],
                # bought by the human's `axes: +<id>`, not proposed
                "bought_by_human": [
                    a.get("id") for a in axes if a.get("id") in added_ids
                ],
                "base": why,
                # what the next round was written from, and what came with it
                "seed": seed_record,
                "not_bought_by_ceiling": [a.get("id") for a in over_cap],
                # mechanisms the agent names that this data cannot separate
                "beyond_this_data": beyond,
                # the floor the next round's axes were offered at, and the
                # axes it refused
                **(
                    {
                        "floor": _floor_record(final_floor),
                        "refused_for_floor": [a["id"] for a in held],
                    }
                    if final_floor is not None
                    else {}
                ),
            },
        )
        self.ledger.append(
            "tier_decision",
            module="revision",
            round_idx=nxt_idx,
            tier="expansion",
            axes_selected=[a.get("id") for a in axes],
            n_models=_ms.n_models(len(axes), next_mode),
            search_mode=next_mode,
            dropped_by_ceiling=[a.get("id") for a in over_cap],
        )
        commit_run(self.store, self.ledger, why="decision:revision")
        self.ctx.round_idx = nxt_idx
        origin = (
            f"candidate {seed_cand} of round {nxt_idx - 1}"
            if seed_cand
            else f"a rebuild of round {nxt_idx - 1}'s base plus the decided axes"
        )
        self.ledger.append(
            "note",
            module="revision",
            round_idx=nxt_idx,
            note=(
                f"round {nxt_idx} seeded from {origin} ({why}) with new axes "
                f"{[a.get('id') for a in axes]}; its model files"
                + (
                    ", its assembly with its observation overlay "
                    f"{seed_record.get('observation_overlay') or '(none)'}"
                    if seed_record.get("assembly_carried")
                    else ""
                )
                + (
                    " and its assembly audit"
                    if seed_record.get("audit_carried")
                    else ""
                )
                + " carried as they are"
            ),
            seeded_from=seed_record,
        )
        print(f"\n===== round {nxt_idx} — enlarged space on top of {base_id} =====")
        cand_ids2 = model_module.run(self.ctx)
        if not cand_ids2:
            raise ModuleFailure("the enlarged space produced no candidate set")
        return self._fit_and_select(cand_ids2)

    def _long_table(self):
        """This round's long measurement table (`RK/data/measurements`) as a
        DataFrame, or None when the round has none."""
        try:
            return (self.ctx.round / "data" / "measurements").table(None)
        except Exception:
            return None

    def _model_of(self, cid: str) -> tuple[str, list[dict]]:
        """(antimony, parameters) of candidate `cid` of this round."""
        model = candidate_work(self.ctx, cid) / "model"
        return (model / "antimony").text(), list((model / "parameters").get([]) or [])

    def _assembly_of(self, cand_id: str) -> dict | None:
        """A fitted candidate's merged assembly (the round's shared assembly
        with its observation-axis overlay), or the shared one when the
        candidate has no merged copy; None for a supplied PEtab problem."""
        merged = (candidate_work(self.ctx, cand_id) / "assembly").get(None)
        if merged is not None:
            return merged
        return (self.ctx.round / "shared_assembly").get(None)

    def _carry_undecided(
        self,
        report: dict,
        winner: str,
        base_antimony: str,
        base_params: list[dict],
    ) -> tuple[list[dict], str, list[dict], dict | None]:
        """Rebuild the expansion base so undecided axes stay live.

        An axis the indistinguishable set disagreed on was not decided by the
        data, so the next round's base is this round's base plus only the
        decided axes, and the undecided ones are re-declared live. Returns
        (carried axes, base antimony, base parameters, seed): `seed` is None
        when nothing is undecided (the winner seeds the round), else
        {"candidate", "overlay"} — the candidate of this round that is
        base-plus-decided when one was fitted (its group and fit carry over),
        or None with the decided observation axes' patches for the rebuilt
        base's assembly.

        The winner's fitted values are the nominal start hints for every
        surviving parameter. Axes are looked up in the round's `space/axes`,
        which holds their full definitions; the run summary (`tried_models`)
        carries only ids and names.
        """
        from octomod.workflow_modules.model import model_space as _ms
        from octomod.workflow_modules.model import supermodel as _sm
        from octomod.workflow_modules.model import tried_models as _tried

        disc = report.get("discrimination") or {}
        undecided = set(disc.get("undecided_axes") or [])
        if not undecided:
            return [], base_antimony, base_params, None
        # the axes themselves, never their status summaries: this round's own
        # definitions first (patched to this round's base), then the run's
        # earliest declaration for any id this round does not define
        by_id = {str(a.get("id")): a for a in _ms.declared_axes(self.ctx)}
        for aid, axis in _tried.declared_axis_dicts(self.root).items():
            by_id.setdefault(aid, axis)
        undecided = {a for a in undecided if a in by_id}
        if not undecided:
            return [], base_antimony, base_params, None

        winner_order = [a for a in str(winner).split("+") if a in by_id]
        winner_on = set(winner_order)  # the ids the winner carries
        decided_on = [
            by_id[a] for a in winner_on - undecided if by_id[a].get("on_antimony_patch")
        ]
        decided_overlay = [
            by_id[a]["on_assembly_patch"]
            for a in winner_order
            if a not in undecided and by_id[a].get("on_assembly_patch")
        ]
        round_base = tree.model_node(self.ctx.round, None)
        round_base_ant = (round_base / "antimony").text(None)
        if round_base_ant is None:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    f"undecided axes {sorted(undecided)} could not be carried: "
                    f"this round has no base model antimony to rebuild from, so the "
                    f"expansion seeds from the winner, as it does when nothing is "
                    f"undecided"
                ),
            )
            return [], base_antimony, base_params, None

        round_base_par = list((round_base / "parameters").get([]) or [])
        rebuilt, params, applied = _sm.build_structure(
            round_base_ant,
            round_base_par,
            decided_on,
            nominal_hints={
                str(p.get("id")): p.get("nominal_value") for p in base_params
            },
        )
        if not applied:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    f"undecided axes {sorted(undecided)} could not be carried: a "
                    f"decided axis patch does not apply to the round's base "
                    f"model, so the expansion seeds from the winner, as it does "
                    f"when nothing is undecided"
                ),
            )
            return [], base_antimony, base_params, None

        carried = [
            {**by_id[a], "frozen": False, "carried_undecided": True}
            for a in sorted(undecided)
        ]
        self.ledger.append(
            "note",
            module="revision",
            round_idx=self.ctx.round_idx,
            note=(
                f"axes {sorted(undecided)} stay LIVE — the indistinguishable "
                f"set {disc.get('indistinguishable')} disagreed on them, so the "
                f"data did not decide them. The expansion base is this round's "
                f"base plus the DECIDED axes "
                f"{sorted(a['id'] for a in decided_on)}, not the winner"
            ),
        )
        print(
            f"  undecided: {len(carried)} axis/axes stay live "
            f"({sorted(undecided)}); the expansion base drops them rather than "
            f"freezing them at the winner's setting"
        )
        # When this round fitted exactly base-plus-decided, the next round
        # starts from that candidate's group (model, assembly and fit) rather
        # than from an unfitted rebuild. Not when an undecided axis was
        # absorbed into the one-compile structure: that candidate carries the
        # axis's terms (switched off), and the next round could not search it.
        decided_ids = winner_on - undecided
        member = "+".join(a for a in winner_order if a in decided_ids) or "base"
        fitted_ids = {str(c.get("id")) for c in disc.get("candidates") or []}
        absorbed = set(
            ((round_base / "encoding").get(None) or {}).get("absorbed_axes") or []
        )
        member_model = candidate_work(self.ctx, member) / "model"
        if (
            member in fitted_ids
            and (member_model / "antimony").exists()
            and not (undecided & absorbed)
        ):
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    f"expansion base = candidate {member} of this round (base plus the "
                    f"decided axes, already fitted): the next round starts from "
                    f"its folder, and its fit is reused"
                ),
            )
            return (
                carried,
                (member_model / "antimony").text(),
                list((member_model / "parameters").get([]) or []),
                {"candidate": member, "overlay": []},
            )
        return carried, rebuilt, params, {"candidate": None, "overlay": decided_overlay}

    def _carry_untested(
        self,
        declared_axes: list[dict],
        proposal: dict,
        base_antimony: str,
        base_parameter_ids: set[str],
        already: set[str],
        base_assembly: dict | None = None,
        obs_taken: dict[str, str] | None = None,
    ) -> list[dict]:
        """Declared-but-never-fitted axes that rejoin the expansion lattice,
        with the priority they were declared with.

        An axis the agent explicitly ruled out is not carried (the card shows
        the reason; the human can buy it with `axes: +<id>`). Observation axes
        rejoin too, checked against the base's assembly, one per observable.
        An axis that cannot be put on this base is dropped with the reason
        ledgered, as a freshly proposed one would be.
        """
        from octomod.workflow_modules.model import tried_models as _tried

        ruled_out = {
            str(e.get("id"))
            for e in (proposal.get("untested_axes_addressed") or [])
            if isinstance(e, dict) and str(e.get("action")) == "ruled_out"
        }
        by_id = _tried.declared_axis_dicts(self.root)
        taken = dict(obs_taken or {})
        carried: list[dict] = []
        for entry in _tried.untested(declared_axes):
            aid = str(entry.get("id"))
            axis = by_id.get(aid) or {}
            if aid in already or aid in ruled_out:
                continue
            if not (axis.get("on_antimony_patch") or axis.get("on_assembly_patch")):
                continue
            problem = self._declared_axis_problem(
                axis, base_antimony, base_parameter_ids, base_assembly, taken
            )
            if problem:
                self.ledger.append(
                    "note",
                    module="revision",
                    round_idx=self.ctx.round_idx,
                    note=(
                        f"untested axis {aid!r} not carried into the expansion "
                        f"lattice: {problem} — it stays on the card as untested"
                    ),
                )
                continue
            taken.update(self._obs_targets([axis]))
            carried.append({**axis, "frozen": False, "carried_untested": True})
        if carried:
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    f"declared-but-never-fitted axes "
                    f"{[a['id'] for a in carried]} join the enlarged space "
                    f"with their declared priorities — the agent did not have "
                    f"to re-propose them"
                ),
            )
            print(
                f"  untested-first: {[a['id'] for a in carried]} rejoin the "
                f"enlarged space with their declared priority (never fitted, not "
                f"ruled out)"
            )
        return carried

    def _split_context(
        self, base_asm: dict | None, base_par: list[dict], winner: str
    ) -> dict | None:
        """What a `split_parameter` axis is resolved against: each condition's
        attributes from the data's own condition key (never a display label),
        the base's parameter rows, and which conditions are trained on (a value
        seen only in held-out conditions cannot be split). None when the round
        has no long table or no assembly."""
        if base_asm is None:
            return None
        long_df = self._long_table()
        if long_df is None:
            return None
        if not {"condition_label", "condition_key"} <= set(long_df.columns):
            return None
        key_by_label = dict(
            zip(
                long_df["condition_label"].astype(str),
                long_df["condition_key"].fillna("").astype(str),
                strict=True,
            )
        )
        trained = None
        meas = candidate_work(self.ctx, winner) / "petab" / "measurements"
        if meas.exists():
            try:
                trained = set(meas.table()["simulationConditionId"].astype(str))
            except Exception:
                trained = None
        return {
            "condition_values": assembly_edit.condition_attributes(
                base_asm, key_by_label
            ),
            "base_parameters": base_par,
            "trained_ids": trained,
        }

    @staticmethod
    def _obs_targets(axes: list[dict]) -> dict[str, str]:
        """{observable or condition -> the observation axis that claims it}."""
        out: dict[str, str] = {}
        for a in axes:
            if not a.get("on_assembly_patch"):
                continue
            try:
                targets = assembly_edit.patch_targets(a["on_assembly_patch"])
            except ValueError:
                continue
            for t in targets:
                out.setdefault(str(t), str(a.get("id")))
        return out

    def _declared_axis_problem(
        self,
        axis: dict,
        base_antimony: str,
        base_parameter_ids: set[str],
        base_assembly: dict | None,
        obs_taken: dict[str, str],
    ) -> str | None:
        """Why an axis declared earlier in the run cannot be put on this base,
        or None. One check for both ways such an axis comes back: carried
        because nobody fitted it, and bought by the human over the agent's
        ruling. The same rules a proposed axis meets in `validate_axes`."""
        from octomod.workflow_modules.model import antimony_text as _at
        from octomod.workflow_modules.model import model_space as _ms

        if axis.get("on_antimony_patch"):
            missing = [
                m
                for m in _ms.undeclared_symbols(base_antimony, axis)
                if m not in base_parameter_ids
            ]
            if missing:
                return f"its patch uses undeclared symbol(s) {missing}"
            _, applies = _ms.apply_patch(base_antimony, axis["on_antimony_patch"])
            return None if applies else "its patch does not apply to this base model"
        patch = axis.get("on_assembly_patch")
        if not patch:
            return "it carries no patch"
        if base_assembly is None:
            return "this base has no assembly to check its observation patch against"
        adds = {str(p.get("id")) for p in (axis.get("adds_parameters") or [])}
        problems = assembly_edit.validate_patch(
            patch,
            model_entities=_at.identifiers(base_antimony or ""),
            parameter_ids=set(base_parameter_ids) | adds,
            adds=adds,
            assembly=base_assembly,
        )
        if problems:
            return "; ".join(problems)
        clash = next(
            (t for t in assembly_edit.patch_targets(patch) if str(t) in obs_taken), None
        )
        if clash is not None:
            return (
                f"{clash!r} already carries the observation axis "
                f"{obs_taken[str(clash)]!r} (one observation axis per observable "
                f"per round)"
            )
        return None

    def _axes_bought_at_expansion(
        self,
        note: str,
        axes: list[dict],
        declared_axes: list[dict],
        proposal: dict,
        base_antimony: str,
        base_parameters: list[dict],
        base_assembly: dict | None,
        t_end: float,
        max_models: int,
        mode: str,
        reading,
    ) -> list[dict]:
        """`axes: +<id>` at the expansion card: buy declared axes the card does
        not carry (ruled out by the agent, or fitted and beaten on an earlier
        base).

        Each is checked against the base like a carried axis, and a structural
        one goes through the pre-compile ladder, since it is bought after the
        card's own ladder ran. What cannot be put on the base is read back as
        not acted on, with the reason."""
        from octomod.orchestration.interaction import gate_note
        from octomod.workflow_modules.model import model_space as _ms
        from octomod.workflow_modules.model import tried_models as _tried

        tokens = gate_note.key_list(note, "axes", "axis")
        if tokens is None:
            return []
        plus = [t[1:] for t in tokens if t.startswith("+") and len(t) > 1]
        other = [t for t in tokens if not (t.startswith("+") and len(t) > 1)]
        if other:
            reading.unread["axes: " + ", ".join(other)] = (
                "at the expansion card `axes:` only adds, written +<id>; to search "
                "fewer, answer the next round's scope gate with axes: …"
            )
        by_id = _tried.declared_axis_dicts(self.root)
        status = {str(a.get("id")): a for a in declared_axes}
        on_card = {str(a.get("id")) for a in axes}
        ruled = {
            str(e.get("id")): str(e.get("why") or "")
            for e in (proposal.get("untested_axes_addressed") or [])
            if isinstance(e, dict) and str(e.get("action")) == "ruled_out"
        }
        taken = self._obs_targets(axes)
        base_pids = {str(p.get("id")) for p in base_parameters}
        added: list[dict] = []
        why_each: list[str] = []
        for aid in dict.fromkeys(plus):
            if aid in on_card:
                reading.unread[f"+{aid}"] = "already on this card — a y buys it"
                continue
            axis = by_id.get(aid)
            if axis is None:
                reading.unread[f"+{aid}"] = (
                    "not declared in any round of this run — a new axis comes from "
                    "the agent (redraft:), not by id"
                )
                continue
            st = status.get(aid) or {}
            if st.get("status") == "selected":
                reading.unread[f"+{aid}"] = (
                    "selected on a winning model already — it is part of the base "
                    "it was selected on"
                )
                continue
            problem = self._declared_axis_problem(
                axis, base_antimony, base_pids, base_assembly, taken
            )
            if problem is None and axis.get("on_antimony_patch"):
                viable, dropped, _n, _f = _ms.pregate_ladder(
                    self.ctx,
                    base_antimony,
                    base_parameters,
                    [axis],
                    max_models,
                    t_end,
                    module="revision",
                    mode=mode,
                )
                if not viable:
                    problem = (
                        dropped[0]["reason"]
                        if dropped
                        else "it fails the pre-compile ladder"
                    )
            if problem:
                reading.unread[f"+{aid}"] = f"cannot be put on this base: {problem}"
                continue
            taken.update(self._obs_targets([axis]))
            added.append({**axis, "frozen": False, "bought_by_human": True})
            if aid in ruled:
                why_each.append(f"{aid} (ruled out by the agent: {ruled[aid][:120]})")
            elif st.get("status") == "rejected":
                why_each.append(
                    f"{aid} (fitted before on {st.get('fitted_on')} and beaten)"
                )
            else:
                why_each.append(
                    f"{aid} (declared in round {st.get('declared_in_round')}, never fitted)"
                )
        if added:
            reading.read["axes"] = ", ".join(f"+{a['id']}" for a in added)
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=(
                    "the human bought declared axes at the expansion gate, over "
                    "the agent's proposal: " + "; ".join(why_each)
                ),
                bought_by_human=[a["id"] for a in added],
            )
            print(f"  bought at your request: {', '.join(why_each)}")
        return added

    def _take_expansion_redraft(self, text: str, note: str) -> None:
        """A `redraft:` at the expansion card. The person's words, and the
        proposal they read, go back to the expansion agent; the card is then
        asked again on its new proposal.

        Written in the order a crash can resume from: the request and the reply
        it is about go into the round's `expansion_diagnostics` BEFORE the
        offer's recorded answer is removed, so a crash between the two re-reads
        the same answer on the resume and finds the request already taken. The
        engine's diagnostic results stay: they were measured on this round's
        fits and answer the new proposal as well as the old one."""
        import datetime as _dt

        from octomod.orchestration.interaction import gate_note
        from octomod.orchestration.interaction import human_redraft as _hr
        from octomod.workflow_modules.model import model_space as _ms

        reading = gate_note.Reading(read={"redraft": text})
        later = "not acted on — the expansion is proposed again first; answer it on the next card"
        if re.search(r"\b(?:base|expand_from)\s*[:=]", note or "", re.I):
            reading.unread["base:"] = later
        if _ms.lattice_requested(note):
            reading.unread["lattice"] = later
        for form in self._floor_forms_written(note):
            reading.unread[form] = later
        gate_note.report(
            reading,
            note,
            ledger=self.ledger,
            module="revision",
            round_idx=self.ctx.round_idx,
        )
        state_node = self.ctx.round / "expansion_diagnostics"
        state = state_node.get({"steps": []})
        asks = state.setdefault("human_redrafts", [])
        taken = (
            bool(asks)
            and asks[-1].get("text") == text
            and not state.get("final_proposal")
        )
        if not taken:
            _hr.record(self.ctx, "revision", "revision", text)
            asks.append(
                {
                    "text": text,
                    "previous_reply": state.get("final_proposal"),
                    "at": _dt.datetime.now().isoformat(timespec="seconds"),
                }
            )
            # the proposal the person sent back is kept as `previous_reply`;
            # its repair belongs to it, and the new proposal gets its own
            state.pop("final_proposal", None)
            state.pop("redraft_proposal", None)
            state_node.put(state)
        (self.ctx.round / "expansion_offer").delete()
        print(f"  → re-proposing the expansion at your request: {text[:90]}")

    # ------------------------------------------------- the floor an expansion seeds

    def _schedule_next_floor(self) -> dict | None:
        """The floor of the round this expansion seeds, written at
        `rounds/round_{k+1}/space/floor` before the expansion agent is asked
        (source `schedule`: this round's floor lowered by its step), unless it
        is already there — a resumed offer, or the person's answer at this card.
        Returns the record, with the band the schedule lowered (`from`) when
        the schedule set it; None when the run records no floor."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        sched = _rxe.scheduled_floor(self.ctx)
        rec = _rxe.next_floor(self.ctx)
        if rec is None:
            if sched is None:
                return None
            k = self.ctx.round_idx
            rec = _rxe.write_next_floor(
                self.ctx,
                sched["band"],
                sched["step"],
                "schedule",
                note=(
                    f"support floor {_rxe.band_text(sched['band'])} for round {k + 1}: "
                    f"the schedule lowers round {k}'s {_rxe.band_text(sched['from'])} "
                    f"by {sched['step']} band(s), before the expansion agent is asked"
                ),
            )
        out = dict(rec)
        if rec.get("source") == "schedule" and sched is not None:
            out["from"] = sched["from"]
        return out

    def _split_by_floor(
        self, axes: list[dict], record: dict | None, floor: dict
    ) -> tuple[list[dict], list[dict], dict[str, list[dict]]]:
        """(offered, held, refusals by axis id): an axis whose patch adds a
        conversion graded below `floor`, or one no dossier entry describes, is
        held back from the offer (`reaction_evidence.floor_refusals` on its
        annotation); an axis the annotation could not read, or one that adds
        no conversion, is offered. In advisory mode every axis is offered and
        `refusals` holds what the card flags."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        view = _rxe.dossier_of(self.ctx)
        band = _rxe.floor_band(floor)
        allowed = _rxe.admitted_at(
            view,
            band,
            exempt=_rxe.exempt_ids(view, _rxe.base_floor(self.ctx)),
        )
        by_axis = (record or {}).get("axes") or {}
        strict = _rxe.strict(self.ctx)
        offered, held, refusals = [], [], {}
        for a in axes:
            support = by_axis.get(str(a.get("id"))) or {}
            refs = _rxe.floor_refusals(support.get("reactions") or [], allowed, band)
            if refs:
                refusals[str(a["id"])] = refs
            if refs and strict:
                held.append(a)
            else:
                offered.append(a)
        return offered, held, refusals

    def _floor_card_lines(
        self, floor: dict, held: list[dict], refusals: dict[str, list[dict]]
    ) -> list[str]:
        """The expansion card's floor block: the floor of the round it seeds
        and who set it, each axis refused for it (strict) or each addition
        below it flagged (advisory), whether the round's one search is spent,
        and the step."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        band = _rxe.floor_band(floor)
        words = _rxe.expansion_floor_words(band, mode=_rxe.grounding_mode(self.ctx))
        lines = [
            "",
            f"SUPPORT FLOOR for round {self.ctx.round_idx + 1}: "
            f"{_rxe.floor_from_text(floor)} — {words}",
        ]
        lines += [
            f"  ⚑ REFUSED {_rxe.axis_refusal_line(a['id'], refusals[str(a['id'])], band)}"
            for a in held
        ]
        held_ids = {str(a["id"]) for a in held}
        lines += [
            f"  {_rxe.below_floor_line(ref, band, f'axis {aid}')}"
            for aid, refs in refusals.items()
            if aid not in held_ids
            for ref in refs
        ]
        state = (self.ctx.round / "expansion_diagnostics").get({}) or {}
        spent = [
            r
            for r in state.get("research_requests") or []
            if r.get("status") == "answered"
        ]
        cap = _rxe.search_caps(self.spec)["per_round"]
        if spent:
            lines.append(
                f"  the round's targeted search is spent ({len(spent)} of {cap}; "
                f"what it found is above)"
            )
        elif cap:
            lines.append(
                "  the round's one targeted search is not spent: `search: "
                "<question>` spends it on yours, and the card is asked again"
            )
        lines.append(
            f"  step {_rxe.step_of(floor, self.spec)}: each later expansion lowers "
            f"the floor by it — `floor:` and `step:` in your answer are recorded as "
            f"yours"
        )
        return lines

    @staticmethod
    def _floor_forms_written(note: str | None) -> list[str]:
        """The floor forms a note carries (`floor:`, `step:`, `search:`), as
        written, for a read-back of what was not acted on."""
        from octomod.orchestration.interaction import gate_note

        out = []
        for key in ("floor", "step", "search"):
            value = gate_note.key_value(note, key)
            if value:
                out.append(f"{key}: {value[:60]}")
        return out

    def _floor_answer(self, note: str | None, floor: dict, reading) -> dict:
        """`floor: <band|none>` and `step: <n>` at the expansion card: the floor
        of the round it seeds, written as the person's (source `human`, a
        `floor_set` row) — a `step:` alone lowers this round's floor by the new
        step — and read back. The round's expansion searches are admitted again
        at the new floor. Returns the floor that applies."""
        from octomod.orchestration.interaction import gate_note
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        band_words = gate_note.key_list(note, "floor")
        step_words = gate_note.key_list(note, "step")
        if not band_words and not step_words:
            return floor
        cur = _rxe.floor_band(floor)
        if cur == _rxe.NOT_APPLICABLE:
            for form in self._floor_forms_written(note):
                if not form.startswith("search"):
                    reading.unread[form] = (
                        "the knowledge module ran offline: no floor applies"
                    )
            return floor
        band, step = cur, _rxe.step_of(floor, self.spec)
        wrote_band = wrote_step = False
        if step_words:
            raw = step_words[0]
            if raw.isdigit():
                step, wrote_step = int(raw), True
            else:
                reading.unread[f"step: {raw}"] = "a step is a whole number of bands"
        if band_words:
            raw = band_words[0]
            word = _rxe.parse_band(raw)
            if word is None or word == _rxe.NOT_APPLICABLE:
                reading.unread[f"floor: {raw}"] = (
                    "not a floor — accepted: high, medium, low, weak, none"
                )
            else:
                band, wrote_band = word, True
        if not (wrote_band or wrote_step):
            return floor
        if wrote_step and not wrote_band:
            # the schedule with the person's step: this round's floor lowered by it
            this = _rxe.recorded_floor(self.ctx)
            band = _rxe.lower_band(_rxe.floor_band(this), step) if this else band
        k1 = self.ctx.round_idx + 1
        rec = _rxe.write_next_floor(
            self.ctx,
            band,
            step,
            "human",
            note=(
                f"support floor {_rxe.band_text(band)}, step {step}, for round {k1}: "
                f"set by the person at the expansion card"
            ),
        )
        reading.read["floor"] = _rxe.band_text(band)
        if wrote_step:
            reading.read["step"] = step
        # the searches of this expansion, read again at the floor as it stands
        for n, srec in _rxe.searches(self.ctx):
            if _rxe.requested_by(srec) in (
                _rxe.REQUESTED_BY_REVISION,
                _rxe.REQUESTED_BY_HUMAN,
            ):
                _rxe.admit(self.ctx, n, {"band": band})
        return dict(rec)

    def _take_person_search(self, note: str | None, winner: str) -> tuple[bool, str]:
        """`search: <question>` at the expansion card: the round's one targeted
        search spent on the person's question (`requested_by: human`) when the
        agent did not spend it, what it finds admitted at the floor of the
        round the expansion seeds, and the card's answer cleared so it is asked
        again on the axes annotated against it. Returns (ran, why it did not)."""
        from octomod.orchestration.interaction import gate_note
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        question = " ".join((gate_note.key_value(note, "search") or "").split())[:400]
        if not question:
            return False, ""
        state_node = self.ctx.round / "expansion_diagnostics"
        state = state_node.get({"steps": []})
        reqs = state.setdefault("research_requests", [])
        allowed = model_module.requested_research_rounds(
            self.ctx.testcase, self.spec, grounded=True
        )
        pending = next(
            (
                r
                for r in reqs
                if r.get("status") == "pending"
                and r.get("requested_by") == _rxe.REQUESTED_BY_HUMAN
                and r.get("questions") == [question]
            ),
            None,
        )
        n_done = sum(1 for r in reqs if r.get("status") == "answered")
        if pending is None and n_done >= allowed:
            return False, (
                f"the round's targeted search is spent "
                f"(grounding.search.per_round = {allowed})"
            )
        if pending is None:
            pending = {
                "questions": [question],
                "not_searched": [],
                "n": n_done + 1,
                "status": "pending",
                "kind": "knowledge",
                "requested_by": _rxe.REQUESTED_BY_HUMAN,
                "search_n": len(_rxe.searches(self.ctx)) + 1,
            }
            reqs.append(pending)
            state_node.put(state)  # recorded before it is paid for
        print(f"  → targeted search for your question: {question[:120]}")
        self._run_research_request(state, pending, {"selected_model": winner})
        later = (
            "not acted on — the card is asked again after the search; answer it "
            "there"
        )
        reading = gate_note.Reading(read={"search": question})
        for form in self._floor_forms_written(note):
            if not form.startswith("search"):
                reading.unread[form] = later
        if re.search(r"\b(?:base|expand_from)\s*[:=]", note or "", re.I):
            reading.unread["base:"] = later
        gate_note.report(
            reading,
            note,
            ledger=self.ledger,
            module="revision",
            round_idx=self.ctx.round_idx,
        )
        (self.ctx.round / "expansion_offer").delete()
        return True, ""

    def _record_floor_refusals(
        self, held: list[dict], refusals: dict[str, list[dict]], floor: dict
    ) -> None:
        """The axes the offer refused for the floor, as the answer left them: the
        round's `axis_refused` record (one entry per axis: its reactions, the
        floor, the round it was offered for, the card's line) and one
        `axis_refused_floor` row per axis — once, so a resume adds none."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        band = _rxe.floor_band(floor)
        k1 = self.ctx.round_idx + 1
        rows = [
            {
                "axis": str(a["id"]),
                "for_round": k1,
                "floor": band,
                "reactions": refusals.get(str(a["id"])) or [],
                "line": _rxe.axis_refusal_line(
                    a["id"], refusals.get(str(a["id"])) or [], band
                ),
            }
            for a in held
        ]
        node = self.ctx.round / _rxe.AXIS_REFUSED_KEY
        if rows or node.exists():
            node.put(rows)
        seen = {
            (e.get("axis"), e.get("floor"))
            for e in self.ledger.entries()
            if e.get("event") == "axis_refused_floor"
            and e.get("round") == self.ctx.round_idx
        }
        for row in rows:
            if (row["axis"], band) in seen:
                continue
            refs = row["reactions"]
            self.ledger.append(
                "axis_refused_floor",
                module="revision",
                round_idx=self.ctx.round_idx,
                axis=row["axis"],
                reaction=refs[0].get("reaction_id") if refs else None,
                band=refs[0].get("band") if refs else None,
                reactions=[r.get("reaction_id") for r in refs],
                bands=[r.get("band") for r in refs],
                floor=band,
                for_round=k1,
                note=f"refused from the offer: {row['line']}",
            )

    def _discard_unseeded_floor(self) -> None:
        """An offer that seeds no round leaves no round behind: the floor
        written for round k + 1 before the agent was asked is removed when it
        is all that round holds (its `floor_set` rows stay in the ledger)."""
        nxt = tree.round_node(self.root, self.ctx.round_idx + 1)
        if not nxt.exists() or set(nxt.children()) != {"space"}:
            return
        if set((nxt / "space").children()) != {"floor"}:
            return
        nxt.delete()
        self.ledger.append(
            "note",
            module="revision",
            round_idx=self.ctx.round_idx,
            note=(
                f"the support floor written for round {self.ctx.round_idx + 1} is "
                f"removed with the round: the offer seeded no round"
            ),
        )

    def _expansion_feedback(self, with_previous: bool = True) -> dict:
        """The latest `redraft:` a person wrote at this round's expansion card,
        as the context block every redraft carries, or {} when nobody asked
        (a plain call's prompt must not change)."""
        from octomod.orchestration.interaction import human_redraft as _hr

        state = (self.ctx.round / "expansion_diagnostics").get({}) or {}
        asks = state.get("human_redrafts") or []
        if not asks:
            return {}
        last = asks[-1]
        return _hr.context_for(
            last["text"],
            "revision",
            last.get("previous_reply") if with_previous else None,
        )

    def _expansion_redraft_lines(self, proposal: dict) -> list[str]:
        """What moved since the proposal the person sent back, for the card, so
        a redraft that changed nothing, or more than was asked, is seen."""
        state = (self.ctx.round / "expansion_diagnostics").get({}) or {}
        asks = state.get("human_redrafts") or []
        if not asks:
            return []
        last = asks[-1]
        prev = last.get("previous_reply") or {}
        before = {str(a.get("id")): a for a in prev.get("axes") or []}
        after = {str(a.get("id")): a for a in proposal.get("axes") or []}
        kept = [i for i in after if i in before]
        changed = [
            i
            for i in kept
            if before[i].get("on_antimony_patch") != after[i].get("on_antimony_patch")
            or before[i].get("on_assembly_patch") != after[i].get("on_assembly_patch")
        ]
        out = [
            "",
            f"REDRAFTED at your request ({len(asks)} so far): {last['text'][:200]}",
            f"  new axes: {', '.join(i for i in after if i not in before) or 'none'}",
            f"  withdrawn: {', '.join(i for i in before if i not in after) or 'none'}",
            f"  kept: {', '.join(i for i in kept if i not in changed) or 'none'}"
            + (f"; kept with a changed patch: {', '.join(changed)}" if changed else ""),
        ]
        if (
            str(prev.get("diagnosis") or "") == str(proposal.get("diagnosis") or "")
            and not (set(after) ^ set(before))
            and not changed
        ):
            out.append("  ! the new proposal is the same as the one you sent back")
        return out

    def _expansion_redraft(
        self,
        context: dict,
        cand_ids: list[str],
        proposal: dict,
        dropped: list[dict],
        tiers,
        base_antimony: str,
    ):
        """Re-ask the expansion agent once with every drop named (both tiers),
        the selected model's legal reaction ids, and the dossier of the
        attempt. Persisted in the round's `expansion_diagnostics` so a resume
        never re-pays; survivors of the re-validated reply go to the human."""
        from octomod.orchestration.interaction import retry as _retry
        from octomod.workflow_modules.model import antimony_text as _at

        state_node = self.ctx.round / "expansion_diagnostics"
        state = state_node.get({"steps": []})
        if state.get("redraft_proposal"):
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note="expansion redraft reused from the record (resume); no agent call",
            )
            prop = state["redraft_proposal"]
            axes, dropped2, n_viable = tiers(prop)
            return prop, axes, dropped2, n_viable
        history = _retry.AttemptHistory(_retry.dossier_of(self.ctx, "revision"))
        entry = history.add(
            [f"axis {d['id']!r}: {d['reason']}" for d in dropped],
            {
                "axes_proposed": [a.get("id") for a in proposal.get("axes") or []],
                "diagnosis": str(proposal.get("diagnosis"))[:300],
            },
        )
        self.ledger.append(
            "redraft",
            module="revision",
            round_idx=self.ctx.round_idx,
            role="revision",
            attempt=entry["attempt"],
            n_failures=len(dropped),
            localized=True,
        )
        ctx2 = dict(context)
        # the items of a search the agent asked for stay in its evidence, so the
        # repaired proposal's citations still resolve
        ctx2.update(self._research_request_context(context, state, for_redraft=True))
        # a proposal a person asked for keeps their request through its repair
        ctx2.update(self._expansion_feedback(with_previous=False))
        ctx2["attempt_history"] = history.as_context()
        ctx2["legal_reaction_ids"] = sorted(_at.reaction_ids(base_antimony))
        ctx2["redraft_instruction"] = (
            "Some of the axes you proposed could not be applied or failed the "
            "pre-compile ladder on the selected model (see attempt_history). Re-emit "
            "your proposal with those fixed or removed; patch ONLY the reaction ids "
            "listed in legal_reaction_ids, declare every symbol you introduce, and keep "
            "the axes that were accepted unchanged. You will not be asked again."
        )
        print(
            f"  expansion axes dropped {[d['id'] for d in dropped]} — re-asking the "
            f"agent once with the dossier"
        )
        prop = self.ctx.call("revision", ctx2)
        state["redraft_proposal"] = prop
        state["final_proposal"] = prop
        state_node.put(state)
        axes, dropped2, n_viable = tiers(prop)
        return prop, axes, dropped2, n_viable

    @timing.phase("revision")
    def _expansion_proposal(self, context: dict, cand_ids: list[str]) -> dict:
        """The expansion agent's proposal, through the bounded request loop:
        engine-run diagnostics (`requested_diagnostics`) and literature
        searches (`requested_research`) the agent asks for before proposing.
        Every step (requests, results, searches, proposal) is persisted in
        `rounds/round_k/expansion_diagnostics`, so a resume replays from the
        record and never re-pays an agent call or a search."""
        from octomod.workflow_modules.evaluation import diagnostics

        state_node = self.ctx.round / "expansion_diagnostics"
        state = state_node.get({"steps": []})
        if state.get("final_proposal"):
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note="expansion proposal reused from "
                "expansion_diagnostics (resume); no agent call",
            )
            print(
                "  (expansion proposal already in the record — resumed, no agent call)"
            )
            return state["final_proposal"]
        max_rounds = int(self.spec.require("diagnostics.rounds"))
        _raw = self.spec.get("diagnostics.max_requests")  # null = no limit
        max_req = None if _raw is None else int(_raw)
        instruction = (
            "You may request engine-run diagnostics before proposing, via "
            "`requested_diagnostics: [{kind, args}]` with kind in "
            f"{list(diagnostics.KINDS)} — simulate_with(candidate_id, "
            "parameter_overrides), residuals_for(candidate_id, group_by=<data "
            "column>), compare_conditions(candidate_id, observable_id, "
            "conditions=[a, b]), fit_residual_form(candidate_id, observable_id, "
            f"condition_id). At most {max_req} per request, {max_rounds} request "
            "round(s); results come back under `diagnostics_requested` and you are "
            "asked again. Diagnostics are suggestive, never selective: an axis is "
            "still fitted in the real likelihood and selected by the criterion."
        )
        # what the research requests extend: the evidence the agent was given
        base = context
        context = dict(context)
        context["diagnostics_instruction"] = instruction
        # a person's `redraft:` at the card, with the proposal they read
        feedback = self._expansion_feedback()
        context.update(feedback)
        # a search asked for before a crash is finished first, from its frozen
        # snapshot when there is one; then the agent reads every answered one
        for rec in state.get("research_requests") or []:
            if rec.get("status") == "pending":
                self._run_research_request(state, rec, base)
        context.update(self._research_request_context(base, state))
        if state["steps"]:
            context["diagnostics_requested"] = [
                r for st in state["steps"] for r in st.get("results") or []
            ]
        if (state["steps"] or state.get("research_requests")) and not feedback:
            print(
                f"  (resuming the request loop from {len(state['steps'])} "
                f"diagnostic step(s) and "
                f"{len(state.get('research_requests') or [])} literature "
                f"request(s) in the record; asking the agent once more)"
            )
        proposal = self.ctx.call("revision", context)
        # one more ask after a refused search, per pass: a request after that
        # one is recorded and the reply taken as it stands
        reasked = False
        while True:
            acted = False
            reqs = proposal.get("requested_diagnostics") or []
            if reqs and len(state["steps"]) < max_rounds:
                print(
                    f"  expansion agent requested {len(reqs)} diagnostic(s): "
                    + ", ".join(str(r.get("kind")) for r in reqs)
                )
                results = diagnostics.run_requests(self.ctx, cand_ids, reqs, max_req)
                state["steps"].append(
                    {
                        "requests": reqs,
                        "results": results,
                        "diagnosis_so_far": proposal.get("diagnosis"),
                    }
                )
                state_node.put(state)
                context["diagnostics_requested"] = [
                    r for st in state["steps"] for r in st.get("results") or []
                ]
                acted = True
            searched = self._take_research_request(proposal, state, base, reasked)
            if searched in ("answered", "refused"):
                acted = True
                reasked = reasked or searched == "refused"
            if not acted:
                break
            context.update(self._research_request_context(base, state))
            proposal = self.ctx.call("revision", context)
        if proposal.get("requested_diagnostics"):
            self.ledger.append(
                "note",
                module="revision",
                round_idx=self.ctx.round_idx,
                note=f"diagnostic request budget ({max_rounds} round(s)) "
                f"exhausted; further requests ignored, proposal "
                f"taken as final",
            )
        state["final_proposal"] = proposal
        state_node.put(state)
        return proposal

    def _take_research_request(
        self, proposal: dict, state: dict, base: dict, reasked: bool
    ) -> str | None:
        """The literature search an expansion reply asks for, if any: run
        within the round's budget ("answered"), refused by name and asked once
        more ("refused"), or, a request after that ask, recorded and not acted
        on ("ignored"). Recorded in the round's state before anything is paid
        for, and ledgered as `expansion_research_requested`."""
        qs, beyond_cap = model_module.research_questions(proposal)
        if not qs:
            if proposal.get("requested_research"):
                self.ledger.append(
                    "note",
                    module="revision",
                    round_idx=self.ctx.round_idx,
                    note="requested_research carried no readable question — "
                    "nothing searched",
                )
            return None
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        state_node = self.ctx.round / "expansion_diagnostics"
        reqs = state.setdefault("research_requests", [])
        # with the knowledge module's output in the run the search is a
        # targeted search of the knowledge role, one per expansion round
        grounded = _rxe.active(self.ctx)
        allowed = model_module.requested_research_rounds(
            self.ctx.testcase, self.spec, grounded=grounded
        )
        n_done = sum(1 for r in reqs if r.get("status") == "answered")
        rec: dict = {
            "questions": qs,
            "not_searched": beyond_cap,
            "diagnosis_so_far": str(proposal.get("diagnosis") or "")[:400],
        }
        if n_done < allowed:
            n = n_done + 1
            rec.update(
                n=n,
                status="pending",
                snapshot=model_module.REQUESTED_RESEARCH.format(n=n),
            )
            if grounded:
                k = len(_rxe.searches(self.ctx)) + 1
                rec.update(
                    kind="knowledge",
                    requested_by=_rxe.REQUESTED_BY_REVISION,
                    search_n=k,
                    snapshot=f"{_rxe.SEARCH_KEY}/{k}",
                )
            reqs.append(rec)
            state_node.put(state)  # recorded before it is paid for
            print(
                f"  expansion agent asked for a literature search "
                f"({len(qs)} question(s)"
                + (
                    f"; {len(beyond_cap)} beyond the cap not searched"
                    if beyond_cap
                    else ""
                )
                + ")"
            )
            self._run_research_request(state, rec, base)
            return "answered"
        if grounded and allowed == 0:
            refusal = "not_allowed"
            reason = (
                f"{model_module.RESEARCH_NOT_ALLOWED} (grounding.search.per_round = 0)"
            )
        elif grounded:
            refusal = "already"
            reason = (
                f"{model_module.RESEARCH_ALREADY_REQUESTED} "
                f"(grounding.search.per_round = {allowed})"
            )
        elif not model_module.research_enabled(self.ctx.testcase, self.spec):
            refusal = "not_allowed"
            reason = (
                f"{model_module.RESEARCH_NOT_ALLOWED} (research is off for this case)"
            )
        elif allowed == 0:
            refusal = "not_allowed"
            reason = f"{model_module.RESEARCH_NOT_ALLOWED} (research.max_requested_rounds = 0)"
        else:
            refusal = "already"
            reason = (
                f"{model_module.RESEARCH_ALREADY_REQUESTED} "
                f"(research.max_requested_rounds = {allowed})"
            )
        rec.update(
            status="ignored" if reasked else "refused", refusal=refusal, reason=reason
        )
        reqs.append(rec)
        state_node.put(state)
        acted = (
            "not acted on: it came after the refusal, so the reply was taken as "
            "it stood"
            if reasked
            else "not searched; the agent is asked once more with that fact"
        )
        self.ledger.append(
            "expansion_research_requested",
            module="revision",
            round_idx=self.ctx.round_idx,
            status=rec["status"],
            questions=qs,
            not_searched=beyond_cap,
            reason=reason,
            note=f"the expansion agent asked for a literature search — {reason}; "
            f"{acted}",
        )
        print(f"  expansion agent asked for a literature search — {reason}; {acted}")
        return rec["status"]

    def _run_research_request(self, state: dict, rec: dict, base: dict) -> None:
        """Run (or, on a resume, read back from its frozen snapshot) the search
        `rec` records, number its items after every item the agent already
        holds, and record and ledger what it returned."""
        winner = str(base.get("selected_model") or "")
        if rec.get("kind") == "knowledge":
            self._run_knowledge_request(state, rec, winner)
            return
        held = list(base.get("retrieved_evidence") or [])
        for r in state.get("research_requests") or []:
            if r is rec:
                break
            if r.get("status") == "answered":
                held += list(r.get("items") or [])
        out = model_module.requested_research(
            self.ctx,
            tree.model_node(self.ctx.round, winner),
            winner,
            rec["questions"],
            int(rec["n"]),
            model_module.next_research_id(held),
        )
        rec.update(status="answered", **out)
        (self.ctx.round / "expansion_diagnostics").put(state)
        per = ", ".join(
            f"Q{k}: {c}" for k, c in enumerate(out["per_question"], start=1)
        )
        self.ledger.append(
            "expansion_research_requested",
            module="revision",
            round_idx=self.ctx.round_idx,
            status="answered",
            n=rec["n"],
            questions=rec["questions"],
            not_searched=rec.get("not_searched") or [],
            snapshot=out["snapshot"],
            n_items=out["n_items"],
            n_dropped=out["n_dropped"],
            per_question=out["per_question"],
            failed=out["failed"],
            note=(
                f"the literature search the expansion agent asked for FAILED "
                f"({str(out['failed'])[:200]}); it is asked again without items"
                if out["failed"]
                else f"the literature search the expansion agent asked for: "
                f"{out['n_items']} item(s) accepted ({per}), {out['n_dropped']} "
                f"filtered out, frozen in {out['snapshot']}; they reach it as "
                f"retrieved_evidence"
            ),
        )

    def _run_knowledge_request(self, state: dict, rec: dict, winner: str) -> None:
        """The targeted search `rec` records (or, on a resume, its frozen
        record), admitted at the floor of the round this expansion seeds;
        recorded in the round's state and ledgered."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        out = model_module.requested_knowledge_search(
            self.ctx,
            tree.model_node(self.ctx.round, winner),
            winner,
            rec["questions"],
            int(rec["search_n"]),
            _rxe.next_floor(self.ctx),
            requested_by=rec.get("requested_by") or _rxe.REQUESTED_BY_REVISION,
        )
        rec.update(status="answered", **out)
        (self.ctx.round / "expansion_diagnostics").put(state)
        floor = _rxe.band_text(out.get("floor"))
        self.ledger.append(
            "expansion_research_requested",
            module="revision",
            round_idx=self.ctx.round_idx,
            status="answered",
            n=rec["n"],
            kind="knowledge",
            requested_by=out["requested_by"],
            questions=rec["questions"],
            not_searched=rec.get("not_searched") or [],
            snapshot=out["snapshot"],
            n_items=out["n_items"],
            admitted=out["admitted"],
            floor=out.get("floor"),
            failed=out["failed"],
            note=(
                f"the targeted search asked for at the expansion FAILED "
                f"({str(out['failed'])[:200]}); nothing was admitted"
                if out["failed"]
                else f"the targeted search asked for at the expansion "
                f"({out['requested_by']}): {out['n_items']} reaction(s) found, "
                + (
                    f"admitted at floor {floor}: {', '.join(out['admitted'])}"
                    if out["admitted"]
                    else f"nothing admitted at floor {floor}"
                )
                + f", frozen in {out['snapshot']}"
            ),
        )

    def _research_request_context(
        self, base: dict, state: dict, for_redraft: bool = False
    ) -> dict:
        """What the expansion agent is told about the searches it asked for:
        whether it may ask (`research_instruction`), the answered searches'
        items appended to the evidence it was given, with their questions under
        `research_answered`, and the latest refusal (`research_refused`). A
        redraft keeps the items, so its citations still resolve, and is told
        nothing else. With the knowledge module's output in the run, what a
        search admitted is in the dossier the agent is shown again
        (`prior_reactions`, `support_floor`)."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        reqs = state.get("research_requests") or []
        if _rxe.active(self.ctx):
            return self._knowledge_request_context(reqs, for_redraft)
        add: dict = {}
        if not for_redraft:
            add["research_instruction"] = model_module.requested_research_instruction(
                self.ctx.testcase, self.spec, reqs
            )
        answered = [r for r in reqs if r.get("status") == "answered"]
        if answered:
            items = list(base.get("retrieved_evidence") or [])
            for r in answered:
                snap = (self.ctx.round / r["snapshot"]).get({}) or {}
                items += snap.get("items") or []
            add["retrieved_evidence"] = items
            if "evidence_instruction" not in base:
                add["evidence_instruction"] = (
                    model_module.EXPANSION_EVIDENCE_INSTRUCTION
                )
            add["research_answered"] = [
                q for r in answered for q in r.get("questions") or []
            ]
        last = reqs[-1] if reqs else {}
        if not for_redraft and last.get("status") in ("refused", "ignored"):
            add["research_refused"] = {
                "questions": last.get("questions"),
                "why": last.get("reason"),
            }
        return add

    def _knowledge_request_context(self, reqs: list, for_redraft: bool) -> dict:
        """`_research_request_context` when the run builds on the knowledge
        module."""
        from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

        add: dict = {}
        if not for_redraft:
            add["research_instruction"] = model_module.requested_research_instruction(
                self.ctx.testcase, self.spec, reqs, grounded=True
            )
        answered = [r for r in reqs if r.get("status") == "answered"]
        if answered:
            add.update(_rxe.expansion_context(self.ctx, _rxe.next_floor(self.ctx)))
            add["research_answered"] = [
                q for r in answered for q in r.get("questions") or []
            ]
        last = reqs[-1] if reqs else {}
        if not for_redraft and last.get("status") in ("refused", "ignored"):
            add["research_refused"] = {
                "questions": last.get("questions"),
                "why": last.get("reason"),
            }
        return add

    def _append_tried_log(self) -> None:
        """Append this run's fitted models to the cross-run archive.

        A run with a testcase appends beside the testcase; a run started from
        its own `input` group appends to `<runs>/_projects/<project>/`. Written
        by the engine for every run under the user's `runs/` folder; whether a
        later run reads it is opt-in (`search.use_tried_log`), because a run
        that consumes it is not blind.

        A run that lives anywhere else (a battery, a sweep, a stub demo under a
        redirected runs folder) appends nothing: its fits would otherwise reach
        the next real run from the same case as if someone had tried them.
        """
        from octomod.workflow_modules.model import tried_models as _tried

        runs_home = Path(config.USER_RUNS_DIR).resolve()
        if not Path(self.store.path).resolve().is_relative_to(runs_home):
            self.ledger.append(
                "note",
                module="tried_models",
                round_idx=self.ctx.round_idx,
                note=f"tried-log not appended: the run lives outside {runs_home}",
            )
            return
        try:
            n = _tried.append_run(
                self.root,
                _tried.archive_for(self.testcase_dir, self.project),
                (self.root / "run").get({}) or {},
            )
            if n:
                self.ledger.append(
                    "note",
                    module="tried_models",
                    round_idx=self.ctx.round_idx,
                    note=f"appended {n} model(s) to the {self.project} tried-log",
                )
        except Exception as e:  # a record must never fail a finished run
            self.ledger.append(
                "note",
                module="tried_models",
                round_idx=self.ctx.round_idx,
                note=f"tried-log append failed: {e}",
            )

    @timing.phase("analysis")
    def _write_analysis(self) -> None:
        """Write the run-level document (ANALYSIS): what was asked, every model
        assessed across every round, what won, what is still open."""
        try:
            from octomod.reporting.analysis_report import write

            with timing.span("render", "analysis_report"):
                out = write(self.root)
            # the document the front end is told to lead with, as a link
            print(
                "  "
                + humangate_module.doc_link(
                    out, "ANALYSIS — start here: the answer and what is open"
                )
            )
            self._append_tried_log()
        except Exception as e:  # a summary must never fail a finished run
            self.ledger.append(
                "note",
                module="analysis_report",
                round_idx=self.ctx.round_idx,
                note=f"analysis report failed: {e}",
            )

        # the last commit of the run, after every document is
        # written, with no ledger row of its own — so the record and its
        # checkpoint describe exactly the same run (tests/result_writes_unit.py).
        commit_run(self.store, None, why="final")

    # ------------------------------------------------- single-model loop
    def _run_single_model_loop(self) -> int:
        history: list[dict] = []
        history_node = self.root / "history"
        directive = None
        import itertools

        rounds_iter = (
            itertools.count() if self.max_rounds is None else range(self.max_rounds)
        )
        for round_idx in rounds_iter:
            self.ctx.round_idx = round_idx
            print(f"\n===== round {round_idx} =====")
            if directive is None:
                saved = (self.ctx.round / "directive").text(None)
                if saved is not None:
                    directive = saved.strip()

            self._banner(
                "S1 · model construction — the agent drafts a mechanism; "
                "the gate ladder checks it (cheap → expensive); you gate scope"
            )
            cand_ids = model_module.run(self.ctx, directive=directive)
            directive = None
            if cand_ids:
                # The human bought a model-space search at the scope gate: the
                # models over the chosen axes are fitted and a criterion
                # selects. The revision loop does not continue after a search.
                print(
                    f"\n  this round is a MODEL-SPACE SEARCH over "
                    f"{len(cand_ids)} models — the axes you chose at the "
                    f"scope gate, fitted and compared"
                )
                return self._fit_and_select(cand_ids)
            self._banner(
                "S2 · data semantics — the agent maps columns to meaning; "
                "the engine moves the numbers; deterministic checks follow"
            )
            data_module.run(self.ctx)
            self._banner(
                "S3 · estimation problem assembly — two agents decide "
                "(the observation function, then the condition encoding), "
                "the engine merges to PEtab, the battery + independent "
                "checker vet it; then the cost boundary is yours"
            )
            self._assemble_and_approve()

            # cycle detection for model-move rounds happens here, once the
            # configuration actually exists
            h = revision_proposal_module.config_hash(self.ctx.round)
            if any(h == past["config_hash"] for past in history):
                raise ModuleFailure(
                    f"round {round_idx} reproduced an already-evaluated "
                    f"configuration (hash {h}) — loop stopped"
                )

            self._banner(
                "COST PROBE — compile once, measure a few real starts, "
                "then you approve a measured budget (never a guess)"
            )
            n_starts = cost_profile.run(self.ctx)
            self._banner(
                f"S6 · estimation — fides multistart, {n_starts} starts, "
                "seeded; post-fit gates decide if the optimum is trustworthy"
            )
            estimation_module.run(self.ctx, n_starts)
            self._banner(
                "S7 · evaluation — fit metrics, uncertainty, held-out "
                "prediction (T2′); the agent interprets; the consistency "
                "gate blocks over- AND under-claiming; the verdict is yours"
            )
            report = evaluation_module.run(
                self.ctx, rounds_left=rounds_left_after(round_idx, self.max_rounds)
            )
            # whether and how the next round is seeded is read from this
            # report: refused by name when the slot does not validate
            from octomod.orchestration import round_seed as _seed

            _seed.require_evaluation(self.ctx)

            best_fval = (self.ctx.work / "estimation").get()["best_fval"]
            history.append(
                {
                    "round": round_idx,
                    "config_hash": h,
                    "best_fval": best_fval,
                    "move": None,
                }
            )
            history_node.put(history)

            rec = report["interpretation"]["recommendation"]
            t2_ok = bool(report.get("t2prime_passed", True))
            if (
                rec in ("accept", "stop")
                and not t2_ok
                and self.ctx.intent["inference_target"] == "prediction"
            ):
                # T2' outranks: an acceptance over a failed held-out gate is
                # not an acceptance
                self.ledger.append(
                    "note", module="loop", note="recommendation overridden: T2' unmet"
                )
                print(
                    "\nrecommendation was accept, but T2' failed — "
                    "acceptance overridden"
                )
                rec = "revise"
            rounds_left = rounds_left_after(round_idx, self.max_rounds)

            # The human's answer at the verdict gate (durable in the round's
            # `decisions/evaluation_verdict`) outranks the agent's recommendation in
            # both directions.
            asked = self._another_round_asked(round_idx)
            if rec in ("accept", "stop") and asked is not True:
                print(f"\nagent recommendation: {rec} — loop ends")
                break
            if asked is False:
                print("\nanother round was offered and declined at the verdict gate")
                self.ledger.append(
                    "note",
                    module="loop",
                    round_idx=round_idx,
                    note="human declined another round at the verdict gate",
                    human_another_round_request=False,
                )
                break
            if rounds_left <= 0:
                print("\nloop budget exhausted — stopping with the current model")
                self.ledger.append("note", module="loop", note="round budget exhausted")
                break
            if asked is True and rec in ("accept", "stop"):
                self.ledger.append(
                    "note",
                    module="loop",
                    round_idx=round_idx,
                    note=(
                        f"another round bought at the verdict gate although the "
                        f"agent recommended {rec!r} — a recommendation informs, "
                        f"the human decides"
                    ),
                    human_another_round_request=True,
                    agent_recommendation=rec,
                )
            move = revision_proposal_module.run(self.ctx, report, history, rounds_left)
            if move is None:
                break
            history[-1]["move"] = move["move"]
            history_node.put(history)

        final_rnd = tree.round_node(self.root, self.ctx.round_idx)
        final_evaluation = (final_rnd / "evaluation").get(None)
        t2_final = True
        if final_evaluation is not None:
            t2_final = bool(final_evaluation.get("t2prime_passed", True))
        outcome = "completed" if t2_final else "completed_t2prime_unmet"
        self.ledger.append("run_end", outcome=outcome)
        commit_run(self.store, None, why="run_end")
        final_report = final_rnd / "report_md"
        print(f"\n===== run {'complete' if t2_final else 'ended: T2prime UNMET'} =====")
        print(f"run record:   {self.store.path}")
        if final_report.exists():
            print(f"final report: {humangate_module.show_command(final_report)}")
        self._write_analysis()
        return 0 if t2_final else 1
