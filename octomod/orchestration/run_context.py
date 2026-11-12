"""Module runners.

Each module: consumes declared input artifacts, calls an agent to fill a typed
hole (or accepts a user-supplied artifact), runs its gate set, writes output
artifacts plus a marker. The marker is the DAG dependency instrument —
downstream modules refuse to start without it, so the protocol enforces itself
through missing-artifact errors rather than obedience.

The run is one HDF5 record, `runs/<id>.h5`, and a module addresses it
by record key through `Node`s (`octomod/result/node.py`): `ctx.root` is
the record, `ctx.round` the round (`rounds/round_k`), `ctx.work` the fitted
problem's group (`…/candidates/<id>`, or `_single`), `ctx.model`, `ctx.gates`
and `ctx.markers` the model, gate verdicts and markers of the unit of work
(the candidate's own, or the round's for a single-model round), and
`ctx.agent_calls` the round's agent calls. Rendered HTML is the one thing on
disk: `ctx.reports_dir`.

Beside the context the module provides `NoteRefused`, the resumable stop a
gate raises when a human's note cannot be acted on; `as_candidate`, a context
manager that points `ctx.work` at one candidate for a block;
`candidate_work`, a candidate's group without switching the context; the
run-folder fields `source_dir` and `project`, and the human's profile
decisions `skip_profiles` / `request_profiles`; `call(..., calls=)`, a
sibling `agent_calls` group for a role asked twice in one round; and the
prompt-cache miss diagnosis of `call_cached` (`_record_prompt_miss`), kept in
the record under `agent_calls/<role>/prompt_misses/<k>`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from octomod.orchestration.ledger import Ledger
from octomod.result import node as _tree
from octomod.result.node import Node


class ModuleFailure(Exception):
    """A module that cannot produce its artifact. The run stops here; partial
    results and the failure reason are part of the deliverable, not noise."""


class NoteRefused(ModuleFailure):
    """A human's gate note the gate cannot act on, raised after the gate's
    recorded answer has been cleared.

    The run stops, but nothing has gone wrong that a new answer cannot fix:
    every artifact is in the record and the cleared gate is the next thing a
    resume asks. The stop is therefore recorded as resumable, and `gate` names
    the gate whose answer was cleared.
    """

    def __init__(self, message: str, *, gate: str):
        super().__init__(message)
        self.gate = gate


def candidate_work(ctx, cid: str | None) -> Node:
    """Candidate `cid`'s group in the current round (`…/candidates/<cid>`, or
    `…/candidates/_single` for None), without switching the context to it.

    There is no candidate folder, only the record group `tree.work_node`
    names, so a caller reads `candidate_work(...) / "model"` (a `Node`).
    """
    return _tree.work_node(ctx.round, cid)


@contextmanager
def as_candidate(ctx, cid: str | None) -> Iterator:
    """Point `ctx.work` (and `model`, `gates`, `markers`) at candidate `cid`
    for the block and restore the previous candidate afterwards, also when the
    block raises."""
    previous = getattr(ctx, "candidate", None)
    ctx.candidate = cid
    try:
        yield ctx
    finally:
        ctx.candidate = previous


@dataclass
class RunContext:
    root: Node  # the run record
    # The staged case every module reads its inputs from, and nowhere else: the
    # `--testcase` directory that is snapshotted into the record's `input`
    # group before S0, or — for a run resumed by `--run-id` alone — a
    # temporary directory the orchestrator materialises from that group. A
    # `Path` in both cases, because the readers (testcase.yaml, description.md,
    # stubs/, the data files) stay file-based; never a directory under `runs/`.
    testcase_dir: Path
    spec: object
    ledger: Ledger
    backend: str  # "stub" | "llm"
    auto: bool
    # The testcase this run was copied from, if any. Not an input source: only
    # for what the snapshot does not carry, `truth/` (for the declaration
    # check) and the per-testcase tried-models archive.
    source_dir: Path | None = None
    # The problem these inputs describe: the testcase name, or the run id with
    # its timestamp removed. Groups runs of one problem across the archive.
    project: str = ""
    round_idx: int = 0
    candidate: str | None = None  # mechanism-discrimination: current candidate id
    cache: dict = field(default_factory=dict)  # in-process memoization only
    # `--skip-profiles "<why>"`: a human's decision to run this invocation's
    # evaluation without profile likelihoods (ledgered, and stated in the
    # report). Never set by the engine or a policy.
    skip_profiles: str | None = None
    # `--profiles "<why>"`: a human's request for profiles, which every goal
    # but parameter_values computes only on request (the verdict card's
    # `profiles` form is the other way to ask). Persisted for the round.
    request_profiles: str | None = None

    # ------------------------------------------------------------ layout
    @property
    def store(self):
        """The run's record file (`RunStore`)."""
        return self.root.store

    @property
    def round(self) -> Node:
        return _tree.round_node(self.root, self.round_idx)

    @property
    def work(self) -> Node:
        """The fitted problem's group: `…/candidates/<id>` during mechanism
        discrimination, `…/candidates/_single` otherwise — so every module
        runs unchanged per candidate."""
        return _tree.work_node(self.round, self.candidate)

    @property
    def model(self) -> Node:
        """The model being worked on: the candidate's, else the round's."""
        return _tree.model_node(self.round, self.candidate)

    @property
    def gates(self) -> Node:
        """Where this unit of work's gate verdicts go."""
        return _tree.gates_node(self.round, self.candidate)

    @property
    def markers(self) -> Node:
        return _tree.markers_node(self.round, self.candidate)

    @property
    def round_markers(self) -> Node:
        return _tree.markers_node(self.round, None)

    @property
    def agent_calls(self) -> Node:
        """The round's agent calls: `…/agent_calls/<role>/{prompt,reply,…}`."""
        return self.round / "agent_calls"

    @property
    def reports_dir(self) -> Path:
        """The rendered documents of this round (real files, for a browser)."""
        return self.store.reports_dir / f"round_{self.round_idx}" / "report"

    def candidate_key(self, name: str) -> str:
        """A `cache` key scoped to the CURRENT candidate.

        `work` already splits every record artifact per candidate, but
        `cache` is one dict for the whole run, so a bare key written inside the
        per-candidate fitting loop is silently overwritten by the next
        candidate — and then read back by code that believes it belongs to a
        different one. That is not a tidiness issue: a shared key lets a refit
        bought for one candidate change how the others are fitted, and hands
        the winner's profiler the last-fitted candidate's optimum. Any cache
        key written per candidate goes through here.
        """
        return f"{name}:{self.candidate or '_single'}"

    @property
    def stubs_dir(self) -> Path:
        return self.testcase_dir / "stubs"

    # ------------------------------------------------------------ testcase
    @property
    def testcase(self) -> dict:
        if "testcase_yaml" not in self.cache:
            self.cache["testcase_yaml"] = yaml.safe_load(
                (self.testcase_dir / "testcase.yaml").read_text()
            )
        return self.cache["testcase_yaml"]

    @property
    def description(self) -> str:
        path = self.testcase_dir / "description.md"
        return (
            path.read_text()
            if path.exists()
            else "(no experiment description supplied)"
        )

    @property
    def intent(self) -> dict:
        return (self.root / "intent").get()

    def pack_texts(self, pack_ids: list[str] | None = None) -> dict[str, str]:
        """Domain packs as data injected into prompts — engine code never
        interprets their content."""
        from octomod.config import KNOWLEDGE_DIR

        ids = pack_ids if pack_ids is not None else self.intent.get("domain_packs", [])
        out = {}
        for pid in ids:
            parts = []
            for name in ("pitfalls.md", "templates.md", "examples.md"):
                f = KNOWLEDGE_DIR / pid / name
                if f.exists():
                    parts.append(f.read_text())
            out[pid] = "\n\n".join(parts) or f"(pack {pid} has no content files)"
        return out

    # ------------------------------------------------------------ markers
    def marker(self, name: str) -> Node:
        return self.markers.child(name)

    def has_marker(self, name: str) -> bool:
        # candidate work sees round-level markers (s1/s2 are shared upstream)
        return self.marker(name).exists() or self.round_markers.child(name).exists()

    def set_marker(self, name: str, **payload) -> None:
        import datetime

        from octomod.orchestration import round_status

        now = datetime.datetime.now().isoformat(timespec="seconds")
        # the marker carries the shas of the slot it certifies,
        # taken now, so `check_intact` compares against what the battery saw.
        # One memo for the marker and the slot state below: each slot
        # artifact is hashed once per marker, not twice.
        shas: dict = {}
        try:
            files = round_status.marker_files(self, name, shas=shas)
        except Exception:  # a hashing failure must never fail a passing module
            files = {}
        self.marker(name).put({**payload, "files": files, "at": now})
        # the slot state (which artifacts are present, who produced them,
        # which battery validated them) goes into the record at every marker,
        # so `status` reads it; hashed through the same memo
        try:
            state = round_status.slot_state(self.round, shas=shas)
            status = self.round / "status"
            self.store.put_many(
                {
                    (status / "slots").key: state["slots"],
                    (status / "candidates").key: state["candidates"],
                    (status / "updated_at").key: now,
                }
            )
        except Exception as e:  # the slot state is a reading aid, never a failure
            self.ledger.append(
                "note",
                module=name,
                round_idx=self.round_idx,
                note=f"round_status update failed: {e}",
            )
        self.ledger.append("marker", module=name, round_idx=self.round_idx, **payload)
        # a marker is a resume point, so the record is
        # checkpointed here — a run killed mid-module restarts from this one
        from octomod.result.autocommit import commit_ctx

        commit_ctx(self, why=f"marker:{name}")

    def require_marker(self, name: str, needed_by: str) -> None:
        if not self.has_marker(name):
            raise ModuleFailure(
                f"{needed_by}: missing input marker {name!r} — the upstream "
                f"module has not passed its gates. (The error message is the "
                f"instruction: run/fix module {name} first.)"
            )
        # A marker whose artifacts are gone is a lie, not a pass: the slot it
        # owns must still be intact. Missing required parts stop the module;
        # a changed sha is recorded (same-content rewrites are legitimate).
        try:
            from octomod.orchestration import round_status

            missing, drifted = round_status.check_intact(self, name)
        except Exception:  # the check is a guard, never a new failure mode
            return
        if missing:
            raise ModuleFailure(
                f"{needed_by}: marker {name!r} is set but its slot is missing "
                f"{missing} — the artifact was removed or never written; re-run "
                f"module {name} (or enter with --from-module) rather than trusting "
                f"the marker"
            )
        if drifted:
            self.ledger.append(
                "note",
                module=name,
                round_idx=self.round_idx,
                note=f"slot parts changed since {name} passed: "
                f"{drifted} (sha drift; not re-validated)",
            )

    # ------------------------------------------------------------ agents
    def call_cached(
        self,
        role: str,
        context: dict,
        calls: Node | None = None,
        name: str | None = None,
        online: bool | None = None,
    ) -> dict:
        """`call`, except that an identical ask already answered in this round
        is read from the record instead of paid for again.

        Every agent call placed BEFORE a human gate is made twice by the
        file-gate protocol: once on the resume that reaches the gate, and again
        on the resume that answers it, because the module has no marker until the
        gate is signed. Identity is the PROMPT: `agent_calls/<role>/prompt` is
        byte-compared with the prompt this context would produce, so a changed
        context — a retry carrying an error, a different candidate — is never
        served a stale reply. A miss against a saved prompt is a paid call that
        may not have been needed, so it is diagnosed (`_record_prompt_miss`)
        before the call is placed. `calls` and `online` as in `call`.
        """
        from octomod.agents import build_prompt_within_budget

        # through the SAME budget `call_agent` applies, or a resumed run
        # compares a full payload against the degraded one in the record and
        # pays again for a reply it already has
        prompt, _context, _trims = build_prompt_within_budget(
            role, context, self.spec, online=online
        )
        call = (calls if calls is not None else self.agent_calls).child(name or role)
        saved_prompt, saved_reply = call / "prompt", call / "reply"
        if saved_reply.exists():
            saved = saved_prompt.text(None)
            if saved == prompt:
                print(
                    f"  → {role}: identical ask already answered this round — "
                    f"reusing the saved reply, no agent call"
                )
                self.ledger.append(
                    "note",
                    module=role,
                    round_idx=self.round_idx,
                    note=f"{role} reply reused from the record: the prompt "
                    f"is byte-identical to the one already answered "
                    f"in this round",
                )
                return saved_reply.get()
            if saved is not None:
                # a miss against a saved prompt is a paid call that may not
                # have been needed: keep both versions and record where they
                # part
                self._record_prompt_miss(role, saved, prompt, call)
        # the grant travels only when the caller chose one, so every other
        # call reaches `call` — or whatever stands in for it — with the
        # seam's plain signature
        grant = {} if online is None else {"online": online}
        return self.call(role, context, calls=calls, name=name, **grant)

    def _record_prompt_miss(self, role: str, saved: str, new: str, call: Node) -> None:
        """Both prompt versions in the record under their sha, and one report
        naming the first difference — so a cache miss is a diagnosable event,
        not a mystery bill.

        Written whole to `<call>/prompt_misses/<k>` (k counts the misses of
        this role in the round): `saved_prompt`, `new_prompt`, their shas, the
        byte/line of the first difference, and `report`, the text a person
        reads. A sibling of `prompt`/`reply`, so the call's own writer never
        replaces it.
        """
        from octomod.orchestration.ledger import sha256_text

        old_sha, new_sha = sha256_text(saved)[:12], sha256_text(new)[:12]
        offset = next(
            (i for i, (a, b) in enumerate(zip(saved, new, strict=False)) if a != b),
            min(len(saved), len(new)),
        )
        old_line = saved[: offset + 1].count("\n") + 1
        old_excerpt = saved.splitlines()[old_line - 1] if saved.splitlines() else ""
        new_lines = new.splitlines()
        new_excerpt = new_lines[old_line - 1] if len(new_lines) >= old_line else ""
        misses = call / "prompt_misses"
        k = 1 + len(misses.children()) if misses.exists() else 1
        miss = misses / str(k)
        report = (
            f"prompt cache MISS for {role} (round {self.round_idx})\n"
            f"saved: {len(saved):,} bytes  sha {old_sha}  -> {miss.key}/saved_prompt\n"
            f"new:   {len(new):,} bytes  sha {new_sha}  -> {miss.key}/new_prompt\n"
            f"first difference at byte {offset:,}, line {old_line}\n"
            f"saved line: {old_excerpt[:400]}\n"
            f"new line:   {new_excerpt[:400]}\n"
        )
        miss.put(
            {
                "role": role,
                "saved_prompt_sha": old_sha,
                "new_prompt_sha": new_sha,
                "bytes_saved": len(saved),
                "bytes_new": len(new),
                "first_difference_byte": int(offset),
                "first_difference_line": int(old_line),
                "saved_prompt": saved,
                "new_prompt": new,
                "report": report,
            }
        )
        self.ledger.append(
            "prompt_cache_miss",
            module=role,
            round_idx=self.round_idx,
            role=role,
            bytes_saved=len(saved),
            bytes_new=len(new),
            first_difference_byte=int(offset),
            first_difference_line=int(old_line),
            saved_line=old_excerpt[:200],
            new_line=new_excerpt[:200],
            saved_prompt_sha=old_sha,
            new_prompt_sha=new_sha,
            note=(
                f"{role}: the saved prompt differs from the rebuilt one at byte "
                f"{offset:,} (line {old_line}); both versions kept, see "
                f"{miss.key} — this call is paid again"
            ),
        )
        print(
            f"  ⚑ {role}: prompt cache miss — saved {len(saved):,} B vs rebuilt "
            f"{len(new):,} B, first difference at line {old_line}; both kept in "
            f"the record, diagnosis in {miss.key}/report"
        )

    def call(
        self,
        role: str,
        context: dict,
        calls: Node | None = None,
        name: str | None = None,
        online: bool | None = None,
    ) -> dict:
        """Fill one typed hole. `name` archives the prompt and reply under a
        record name of their own (`agent_calls/<name>/…`, a flat entry like
        every role's) when a role is asked twice in one round for different
        purposes (the research call before an expansion: `research_expansion`),
        so the second never overwrites the first; default the role. `calls`:
        the `agent_calls` group, default `ctx.agent_calls` (the round's).
        `online`: the call's grant (`agents.granted_tools`) — the knowledge
        role searches the web only when its caller asks."""
        import time as _time

        from octomod.agents import agent_timing, call_agent

        calls = calls if calls is not None else self.agent_calls

        model = self.spec.model_for_role(role) if self.backend == "llm" else "stub"
        live = self.backend == "llm"
        # what the agent is doing and how long that usually takes, from this
        # engine's own measured history
        doing = agent_timing.doing(role)
        typical = agent_timing.typical(role, self.backend)
        print(
            f"  → {role} agent ({model}) — {doing}"
            + (f"  [{typical}]" if typical else "")
        )
        # the routing table decides what this role may be shown, before the
        # prompt is built: a leak visible only in the archived prompt has
        # already happened
        from octomod.agents import routing

        routing.enforce(role, context.keys())
        # the context keys are the plumbing, not the work; kept for an auditor
        # rather than printed at a person
        self.ledger.append(
            "note",
            module=role,
            round_idx=self.round_idx,
            note=f"{role} sees: {', '.join(context.keys())}",
            context_keys=sorted(context.keys()),
        )
        t0 = _time.perf_counter()
        with agent_timing.Heartbeat(
            f"{role} agent", f"{doing}{' · ' + typical if typical else ''}", live=live
        ):
            out = call_agent(
                role,
                context,
                spec=self.spec,
                backend=self.backend,
                calls=calls,
                ledger=self.ledger,
                module=role,
                round_idx=self.round_idx,
                stubs_dir=self.stubs_dir,
                name=name,
                online=online,
            )
        print(
            f"  ← {role} returned in {_time.perf_counter() - t0:.0f}s "
            f"(prompt+reply saved: {calls.child(name or role).key})"
        )
        return out
