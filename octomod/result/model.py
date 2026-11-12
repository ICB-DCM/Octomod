"""The root of the result object: RunResult → RoundRecord → CandidateRecord.

Two shapes of round exist and the object
keeps both under one type: a single-model round has one candidate, keyed
`_single`, whose `model` is None because it IS the round's model; a
candidate-set round has one CandidateRecord per `candidates/<id>` and the
round's `model` is the base the candidates were enumerated from.

Dicts are keyed by id rather than lists of records wherever HDF5 is the
target: hdfdict stores a dict as a group and a list of dicts as one YAML
string, and a group is what a partial reader can open on its own.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from octomod.result.records import (
    SCHEMA_VERSION,
    AgentCallRecord,
    DecisionRecord,
    GateRecord,
    LedgerEvent,
    QuestionRecord,
    Record,
    Table,
    tier,
)
from octomod.result.slots import (
    AssemblyRecord,
    CostRecord,
    DataRecord,
    EstimationRecord,
    EvaluationRecord,
    ExpansionRecord,
    IntentRecord,
    ModelRecord,
    ModelSpaceRecord,
    PetabRecord,
    RevisionRecord,
    RoundStatusRecord,
    SelectionRecord,
)


class RunMeta(Record):
    """`run`: what ran, on what (written at run start)."""

    run_id: str | None = Field(
        default=None, description="Filled from the file name when absent."
    )
    engine_version: str | None = None
    provenance: dict[str, Any] | None = Field(
        default=None, description="git state, package versions, lockfile sha."
    )
    workflow: str | None = None
    workflow_sha: str | None = None
    testcase: str | None = None
    testcase_sha: str | None = None
    backend: str | None = None
    auto: bool | None = None
    max_rounds: int | None = None
    from_module: str | None = None
    spec_overlay: str | None = None
    policy: str | None = None
    policy_profile: str | None = None
    policy_sha: str | None = None
    started_at: str | None = Field(
        default=None, description="ts of the first run_start."
    )
    n_invocations: int | None = Field(
        default=None, description="Number of run_start rows — one per resume."
    )
    research_fence: dict[str, Any] | None = None


class RunOutcome(Record):
    """The `run_end` ledger row, or its absence."""

    outcome: str | None = Field(
        default=None,
        description="completed | completed_t2prime_unmet | stopped | interrupted; "
        "None while the run is still open.",
    )
    reason: str | None = None
    winner: str | None = None
    decisive: bool | None = None
    at: str | None = None
    final_round: int | None = None


class CandidateRecord(Record):
    """One fitted model of a round — `rounds/<k>/candidates/<id>`, or `_single`."""

    id: str | None = Field(default=None, description="Filled from the key.")
    axes_on: list[str] = Field(default_factory=list)
    label: str | None = None
    rationale: str | None = None
    model: ModelRecord | None = Field(
        default=None,
        description="None for `_single`: the round's model is this candidate's.",
    )
    assembly: AssemblyRecord | None = None
    petab: PetabRecord | None = None
    cost: CostRecord | None = None
    estimation: EstimationRecord | None = None
    starts: Table | None = tier(
        "bulk", default=None, description="Per-start table of the multistart."
    )
    multistart: dict[str, Any] | None = tier(
        "bulk",
        default=None,
        description="The multistart as arrays, one per OptimizerResult field "
        "(`estimation.result_from_record` rebuilds the pypesto.Result).",
    )
    attempts: dict[str, Any] = tier(
        "bulk",
        default_factory=dict,
        description="Earlier fits a refit superseded, by attempt number: "
        "estimation, starts, multistart.",
    )
    refit: dict[str, Any] | None = Field(
        default=None,
        description="Read so that records keeping the refit here still load; "
        "the engine writes it to `estimation_settings.refit`.",
    )
    optimizer_comparison: dict[str, Any] | None = tier("bulk", default=None)
    optimizer_selection: dict[str, Any] | None = None
    optimizer_compare_runs: dict[str, Any] | None = tier("bulk", default=None)
    estimation_settings: dict[str, Any] | None = Field(
        default=None,
        description="The settings the fit ran with: declared, budget-gate choices, refit overrides.",
    )
    fit_key: dict[str, Any] | None = Field(
        default=None, description="What identifies this fit for re-use (reuse.py)."
    )
    probe_record: dict[str, Any] | None = Field(
        default=None,
        description="The cost probe as measured, so a budget answer does not re-run it.",
    )
    profiles: dict[str, Any] | None = tier(
        "bulk",
        default=None,
        description="Persisted profile likelihoods, for re-use.",
    )
    profiles_timing: dict[str, Any] | None = Field(
        default=None, description="What each profile cost, for projections."
    )
    structural_nulls: dict[str, Any] | None = Field(
        default=None,
        description="Parameter combinations no output depends on, at any value.",
    )
    structural_nulls_at_mle: dict[str, Any] | None = Field(
        default=None, description="The same, evaluated at the fitted optimum."
    )
    assembly_overlay_applied: list[Any] | dict[str, Any] | None = Field(
        default=None, description="The overlay patches S3 applied: {patch, as}."
    )
    budget_declined: dict[str, Any] | None = Field(
        default=None,
        description="The human's `n` at this candidate's re-asked budget gate "
        "(candidate, note, reasons, at): read back on a resume, so the "
        "candidate is dropped once and never asked again this round.",
    )
    decisions: dict[str, DecisionRecord] = Field(
        default_factory=dict,
        description="The candidate's own gate decisions, by module.",
    )
    gates: dict[str, GateRecord] = Field(
        default_factory=dict, description="By gate id — the candidate's own gates."
    )
    dropped: LedgerEvent | None = Field(
        default=None, description="The candidate_dropped row, when it was dropped."
    )
    markers: dict[str, Any] = Field(
        default_factory=dict, description="Marker name → payload, per candidate."
    )


class RoundRecord(Record):
    """One round: everything under `rounds/round_<k>`."""

    index: int | None = Field(default=None, description="Filled from the key.")
    shape: Literal["single", "candidate_set"] = "single"
    directive: str | None = Field(
        default=None, description="The human's directive for the round."
    )
    model: ModelRecord | None = None
    space: ModelSpaceRecord | None = None
    data: DataRecord | None = None
    shared_assembly: AssemblyRecord | None = None
    candidates: dict[str, CandidateRecord] = Field(default_factory=dict)
    evaluation_core: dict[str, Any] | None = Field(
        default=None,
        description="S7's computed core, written before the interpretation.",
    )
    evaluation: EvaluationRecord | None = None
    attribution: dict[str, Any] | None = tier("bulk", default=None)
    interpretation_diagnostics: dict[str, Any] | None = tier("bulk", default=None)
    base_model: ModelRecord | None = Field(
        default=None,
        description="The tested BASE of a two-call discrimination round; candidates are declared differences from it.",
    )
    base_model_previous: dict[str, Any] | None = tier(
        "audit",
        default=None,
        description="The base before its last redraft, so the card can say what moved.",
    )
    residual_forms: dict[str, Any] | None = Field(
        default=None, description="The residual shape per observable."
    )
    expansion_evidence: dict[str, Any] | None = Field(
        default=None,
        description="The research role's evidence snapshot taken before the expansion "
        "proposal (what that proposal could cite).",
    )
    estimation_settings: dict[str, Any] | None = Field(
        default=None,
        description="Round-level estimation settings shared by its candidates.",
    )
    superseded: dict[str, Any] = tier(
        "audit",
        default_factory=dict,
        description="Groups a re-entered module set aside, by `<what>_<stamp>`.",
    )
    report_md: str | None = tier("audit", default=None)
    selection: SelectionRecord | None = None
    selection_files: dict[str, str] = tier(
        "bulk",
        default_factory=dict,
        description="petab_select's interchange files, by name, as text.",
    )
    decisions: dict[str, DecisionRecord] = Field(
        default_factory=dict, description="By gate module: `…/decisions/<module>`."
    )
    revision: RevisionRecord | None = None
    expansion: ExpansionRecord | None = None
    expansion_offer: dict[str, Any] | None = Field(
        default=None, description="The expansion offer the human answered."
    )
    expansion_diagnostics: dict[str, Any] | None = tier(
        "bulk", default=None, description="Diagnostics the agent asked for."
    )
    expansion_support: dict[str, Any] | None = Field(
        default=None,
        description="With grounding on, each axis of the expansion offer annotated "
        "against the reaction dossier: {dossier_round, base, axes: {axis id: "
        "{reactions, label}}} — the reactions its patch adds to the base, each "
        "labelled as a model reaction is, and the weakest label, 'no new "
        "reaction', or 'not annotated' with the error.",
    )
    compile_feedback: dict[str, Any] | None = Field(
        default=None,
        description="The engine's one redraft of the observation model this round: "
        "the compile or fit failure it sent back, the candidate that failed, "
        "the observable ids the failure named and the finding as worded.",
    )
    research_requests: dict[str, Any] = Field(
        default_factory=dict,
        description="By request number: the frozen snapshot of each literature "
        "search the expansion agent asked for (items, dropped, questions, "
        "per_question, failed).",
    )
    agent_calls: dict[str, AgentCallRecord] = Field(
        default_factory=dict, description="By role."
    )
    gates: dict[str, GateRecord] = Field(
        default_factory=dict, description="Round-level gates (s1 base, s2, s7)."
    )
    status: RoundStatusRecord | None = None
    evidence: dict[str, Any] | None = Field(
        default=None,
        description="The research role's filtered items.",
    )
    supplied_evidence: dict[str, Any] | None = Field(
        default=None,
        description="The human's staged literature.",
    )
    reaction_evidence: dict[str, Any] | None = Field(
        default=None,
        description="The knowledge module's dossier as the run was started with "
        "it (copied into round 0 from the record's input): each reaction with "
        "its sources, its grade, whether it is required or essential, and its "
        "origin; the facts, the system summary, the mode.",
    )
    knowledge_search: dict[str, Any] = Field(
        default_factory=dict,
        description="By search number: each targeted search of the knowledge role "
        "the engine ran in the round — for a base that named what it lacks, for "
        "the expansions' `missing`, for an expansion, or on the person's "
        "`search:` at the expansion card (`requested_by`) — its questions, the "
        "graded reactions and facts it returned, its calls and cost, and what it "
        "admitted at which floor (`admission`).",
    )
    knowledge_admitted: list[Any] | None = Field(
        default=None,
        description="The reactions a targeted search admitted in the round, in "
        "order: each with origin `search`, who asked (`requested_by`), the "
        "question it answers, the search that found it and the floor it was "
        "admitted at; those construction asked for join the base's essential "
        "set, the others are reactions the expansions or an expansion may add.",
    )
    axis_refused: list[Any] | None = Field(
        default=None,
        description="The axes this round's expansion offer refused for the floor "
        "of the round it seeds, as the answer left them: each with the axis id, "
        "the round it was offered for, the floor, the added reactions below it "
        "(each with the entry it matches and that entry's band, or none) and the "
        "card's line.",
    )
    evidence_sources: dict[str, bytes] | None = tier(
        "bulk",
        default=None,
        description="The documents S1 cached for audit, by cached file name: "
        "opaque bytes (a PDF, a page), never text.",
    )
    decisions_md: str | None = tier(
        "audit", default=None, description="The decision record, as rendered."
    )


class TimingSession(Record):
    """One process of the run.

    From its `run_start` row to its `run_end` or `gate_pending` row, extended
    over the checkpoint and account written after that row."""

    index: int
    started: float = Field(
        description="Epoch seconds: the process's start (its first row minus startup_s)."
    )
    startup_s: float | None = Field(
        default=None, description="Imports and set-up before the run_start row."
    )
    ended: float | None = None
    ended_by: str | None = Field(
        default=None,
        description="run_end:<outcome> | gate_pending | open | killed (no end row).",
    )
    wall_s: float | None = None
    timed_s: float | None = Field(
        default=None, description="The leaf spans inside this session, summed."
    )
    engine_s: float | None = Field(
        default=None, description="wall_s − timed_s: the engine between timed blocks."
    )
    cpu_s: float | None = Field(
        default=None,
        description="The process's CPU (self + children, user + sys) at its end row.",
    )
    timed_cpu_s: float | None = None
    engine_cpu_s: float | None = None
    parallelism: float | None = Field(default=None, description="cpu_s / wall_s.")
    cpu_overshoot_s: float | None = Field(
        default=None,
        description="When the spans' CPU exceeds the process's: a child reaped inside "
        "a span that started before it.",
    )
    started_iso: str | None = None


class TimingRecord(Record):
    """Where the run's wall and CPU time went (`timing`).

    Written at every pause and at run end by `octomod/orchestration/timing.py`; rebuilt
    by `derive` from the ledger's `span` rows when absent or stale. The
    account closes by construction: `run_wall_s = Σ sessions.wall_s +
    waiting_for_human_s + unaccounted_s`, and every session is the self time
    of its spans (agent, compute, render, human, io, record) plus `engine_s`.
    Wall time is one machine's; `cpu_s`, the per-unit costs under `compute`
    and `machine` are what compare across machines."""

    run_wall_s: float | None = None
    run_cpu_s: float | None = Field(
        default=None,
        description="CPU over every session (process + children): what the work "
        "cost, comparable across core counts and load.",
    )
    parallelism: float | None = Field(
        default=None, description="run_cpu_s / run_wall_s."
    )
    machine: dict[str, Any] | None = Field(
        default=None,
        description="What it ran on: os, arch, python, cpu_model, cpu_count, "
        "memory_gb, load_avg_1m (no hostname: the record is shared).",
    )
    accounted_s: float | None = None
    residual_s: float | None = Field(
        default=None,
        description="run_wall_s − accounted_s: the gap after a killed session "
        "(= unaccounted_s), else zero.",
    )
    unaccounted_s: float | None = Field(
        default=None,
        description="Wall after a session that lost its end row, before the next "
        "process: nobody was asked anything, the process died.",
    )
    n_sessions: int | None = None
    waiting_for_human_s: float | None = Field(
        default=None,
        description="Between sessions: a human (or the front end) at a file gate.",
    )
    sessions: list[TimingSession] = Field(default_factory=list)
    by_category: dict[str, Any] = Field(
        default_factory=dict,
        description="agent (with api_s, tools_s), compute, render, human, io, "
        "record, engine, waiting_for_human, unaccounted → {wall_s, cpu_s, n, "
        "parallelism; compute also the work units and per-unit costs}.",
    )
    by_module: dict[str, Any] = Field(default_factory=dict)
    by_round: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, Any] = Field(
        default_factory=dict, description="Per role: n, wall_s, api_s (model), tools_s."
    )
    compute: dict[str, Any] = Field(
        default_factory=dict,
        description="Per block: wall_s, cpu_s, parallelism, the work units (n_starts, "
        "n_fval, n_grad, n_hess, n_points, n_profiles, n_procs) and cpu_s/wall_s "
        "per start, fval, point.",
    )
    spans: list[Any] = tier(
        "bulk",
        default_factory=list,
        description="Every span: category, name, module, round, candidate, t0, t1, "
        "wall_s, cpu_s, depth, n_children, children_wall_s/cpu_s, self_wall_s/cpu_s, "
        "leaf, ok, late, and the block's detail (api_s, tools_s, n_starts, …).",
    )
    note: str | None = None
    written_at: str | None = None


class RunResult(Record):
    """The whole run."""

    schema_version: int = SCHEMA_VERSION
    run: RunMeta = Field(
        default_factory=RunMeta,
        description="run_meta; empty when a record was built without one.",
    )
    intent: IntentRecord | None = None
    rounds: dict[str, RoundRecord] = Field(
        default_factory=dict, description='"round_0", "round_1", …'
    )
    questions: list[QuestionRecord] = Field(
        default_factory=list, description="The questions raised for the human."
    )
    history: list[Any] = Field(
        default_factory=list, description="The single-model loop's round history."
    )
    ledger: list[LedgerEvent] = tier(
        "audit", default_factory=list, description="Every ledger row, verbatim."
    )
    outcome: RunOutcome | None = None
    timing: TimingRecord | None = Field(
        default=None,
        description="Where the wall time went; derived from the ledger when absent.",
    )
    input: dict[str, Any] | None = tier(
        "core",
        default=None,
        description="What the run was started with: the case files the run reads, by "
        "relative path (text, or bytes), snapshotted before S0 — the lab note, the "
        "intent, the case file, the blocklist, data/, supplied/, stubs/ and the "
        "documents the supplied literature names; nothing else.",
    )
    input_source: dict[str, Any] | None = Field(
        default=None,
        description="Where `input` came from: the testcase, a previous run (started_from).",
    )
    input_pending: dict[str, Any] | None = Field(
        default=None,
        description="Set while an `input` snapshot or copy is being written; left "
        "behind only by a kill, which makes the next start take the snapshot again.",
    )
    fit_index: dict[str, Any] | None = Field(
        default=None,
        description="Fits in this record by fit key, for re-use (reuse.py).",
    )
    analysis: dict[str, Any] | None = tier(
        "bulk", default=None, description="The analysis report's summary, when written."
    )
    models_used: dict[str, Any] | None = Field(
        default=None,
        description="Which models the agent calls ran on, summed from the ledger "
        "at every pause and at run end (`provenance.models_used`): `by_model` "
        "(roles, calls, input/output tokens, cost) and `by_role` (models as "
        "resolved and as asked, effort). What they were SET UP with is "
        "`run.provenance.agents`.",
    )
    completeness: dict[str, Any] | None = tier(
        "audit",
        default=None,
        description="What the record held at each checkpoint (`completeness.py`): "
        "per marker, decision, pause, run end and final write, what was looked for "
        "and what was missing, under `run/<checkpoint>`, `round_k/<module>/<unit>` "
        "and `round_k/decision_<module>/<unit>`; written before each checkpoint copy.",
    )
    phenomenology_raw: dict[str, Any] | None = Field(
        default=None,
        description="What the curves look like, read from the raw data files "
        "before any round ran, present when its acceptance rules all held; "
        "round 0's construction reads it, and the data module's own reading is "
        "checked against it.",
    )

    @field_validator("ledger", mode="before")
    @classmethod
    def _ledger_from_stream(cls, v: Any) -> Any:
        """The ledger as stored: JSON lines in a byte stream. A reader
        that loads the file generically (mkstd) hands over the bytes, the
        array of them, or the text; each becomes the list of rows."""
        import json

        import numpy as np

        if isinstance(v, np.ndarray) and v.dtype == np.uint8:
            v = v.tobytes()
        elif isinstance(v, list) and v and all(isinstance(x, int) for x in v):
            v = bytes(v)
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        if isinstance(v, str):
            rows = []
            for line in v.split("\n"):
                line = line[2:] if line.startswith("- ") else line
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            return rows
        return v

    @model_validator(mode="after")
    def _identity_from_keys(self) -> RunResult:
        """The tree's keys name the rounds and candidates; a record written
        one group at a time carries no copy of the name inside the
        group, so the copy is filled in here for readers that use it."""
        for name, rnd in self.rounds.items():
            if rnd.index is None and name.startswith("round_"):
                try:
                    rnd.index = int(name.split("_", 1)[1])
                except ValueError:
                    pass
            for cid, cand in rnd.candidates.items():
                if cand.id is None:
                    cand.id = cid
            for role, call in rnd.agent_calls.items():
                if call.role is None:
                    call.role = role
            if (
                rnd.candidates
                and rnd.shape == "single"
                and set(rnd.candidates) != {"_single"}
            ):
                rnd.shape = "candidate_set"
        return self

    # ------------------------------------------------------------ helpers
    def round(self, k: int) -> RoundRecord:
        return self.rounds[f"round_{k}"]

    @property
    def round_indices(self) -> list[int]:
        return sorted(r.index for r in self.rounds.values() if r.index is not None)

    def failures(self) -> list[dict[str, Any]]:
        """Where things went wrong, in order: failed blocking gates, dropped
        candidates, redrafts, refused proposals, a stopped outcome."""
        out: list[dict[str, Any]] = []
        for k in self.round_indices:
            r = self.round(k)
            gates = list(r.gates.values()) + [
                g for c in r.candidates.values() for g in c.gates.values()
            ]
            for g in gates:
                if g.blocking and not g.passed:
                    out.append(
                        {
                            "round": k,
                            "kind": "gate_failed",
                            "id": g.gate_id,
                            "candidate": g.candidate,
                            "detail": g.detail,
                        }
                    )
            for c in r.candidates.values():
                if c.dropped is not None:
                    out.append(
                        {
                            "round": k,
                            "kind": "candidate_dropped",
                            "id": c.id,
                            "detail": getattr(c.dropped, "reason", None)
                            or (c.dropped.model_extra or {}).get("reason"),
                        }
                    )
            for a in r.agent_calls.values():
                for rd in a.redrafts:
                    out.append(
                        {
                            "round": k,
                            "kind": "redraft",
                            "id": a.role,
                            "detail": (rd.model_extra or {}).get("n_failures"),
                        }
                    )
        if self.outcome and self.outcome.outcome not in (None, "completed"):
            out.append(
                {
                    "round": self.outcome.final_round,
                    "kind": "run_end",
                    "id": self.outcome.outcome,
                    "detail": self.outcome.reason,
                }
            )
        return out
