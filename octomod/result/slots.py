"""One record per artifact slot, in the vocabulary of `round_status.SLOTS`.

Each record names, in its docstring, where it lives in the run record (the
artifact, addressed by its record key). The typed fields are the keys the
ENGINE reads; agent-authored blocks whose shape varies stay `dict` and are
kept whole through the `extra="allow"` of `Record`. The records are loose on
purpose, so that nothing a module writes fails to load; tightening any of them
is a per-record step.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from octomod.result.records import Producer, Record, Table, tier


class IntentRecord(Record):
    """S0's frozen intent — `intent`."""

    question: str | None = None
    system: str | None = None
    inference_target: str | None = Field(
        default=None,
        description="prediction | parameter_values | mechanism_discrimination.",
    )
    required_entities: list[Any] = Field(default_factory=list)
    required_predictions: list[Any] = Field(default_factory=list)
    perturbations: list[Any] = Field(default_factory=list)
    timescale: str | int | float | None = None
    scope_exclusions: list[Any] = Field(default_factory=list)
    success_criteria: list[Any] = Field(default_factory=list)
    domain_packs: list[Any] = Field(default_factory=list)
    supplied_literature: list[Any] = Field(default_factory=list)


class ParameterDecl(Record):
    """One row of `model/parameters` — the construction agent's table."""

    id: str
    nominal_value: float | None = None
    lb: float | None = None
    ub: float | None = None
    unit: str | None = None
    estimate: bool | None = None
    evidence_tier: str | None = None
    source: str | None = None


class ModelRecord(Record):
    """The model slot — `…/model` of a round or a candidate.

    Antimony and SBML are embedded as text: they are small, and a copy that
    cannot rebuild the model is not a result.
    """

    antimony: str | None = Field(default=None, description="Antimony source.")
    sbml: str | None = tier("core", default=None, description="SBML.")
    mermaid: str | None = Field(default=None, description="Mermaid diagram.")
    parameters: list[ParameterDecl] = Field(default_factory=list)
    network: dict[str, Any] | None = Field(
        default=None, description="Species, interactions."
    )
    glossary: dict[str, Any] | None = Field(
        default=None, description="Entity glossary."
    )
    build_report: dict[str, Any] | None = Field(
        default=None,
        description="Build decisions, sources, constants.",
    )
    encoding: dict[str, Any] | None = Field(
        default=None, description="The supermodel encoding."
    )
    seed: dict[str, Any] | None = Field(
        default=None,
        description="Where this round's model came from: a revision move, or the "
        "round seed that carried the chosen model forward.",
    )
    assembly_overlay: list[Any] | dict[str, Any] | None = Field(
        default=None, description="Observation-axis patches applied at assembly."
    )
    reaction_support: dict[str, Any] | None = Field(
        default=None,
        description="Every reaction of the model annotated against the most "
        "recent round's reaction dossier (`dossier_round` names it): "
        "user-provided, database-supported, literature-supported or inferred, "
        "with the matched entry, its origin, its band and its counted sources; "
        "for a candidate, the floor what it adds was held to (`floor`: the "
        "variants' floor in a discrimination round, the round's in a model-space "
        "search).",
    )
    producer: Producer = "unknown"
    files: list = Field(
        default_factory=list, description="FileRefs of source files, with sha (legacy)."
    )


class AxisRecord(Record):
    """One structural or observation axis of `space/axes`."""

    id: str
    kind: str | None = None
    # agent-authored text: the contract asks for prose, agents sometimes send
    # a list of points, and `validate_axes` passes these through uncoerced —
    # a record that refused the list would fail S1 AFTER its gates
    question: str | list[Any] | None = None
    default: str | None = None
    priority: int | None = None
    priority_reason: str | list[Any] | None = None
    on_antimony_patch: Any = None
    on_assembly_patch: Any = None
    adds_parameters: list[Any] = Field(default_factory=list)
    rationale: str | list[Any] | None = None
    discriminating_evidence: str | list[Any] | None = None
    declared_by: str | None = None
    frozen: bool | None = Field(
        default=None, description="The last selection, not a deletion."
    )
    support: dict[str, Any] | None = Field(
        default=None,
        description="An expansion axis with grounding on: the reactions its patch "
        "adds to the base, annotated against the reaction dossier, and their "
        "weakest label ({reactions, label}).",
    )


class CandidateDecl(Record):
    """One row of `space/candidates`: a model the round will fit."""

    id: str
    label: str | None = None
    rationale: str | None = None
    assembly_overlay: list[Any] = Field(default_factory=list)


class ModelSpaceRecord(Record):
    """The declared model space and what became of it.

    `rounds/<k>/space/{axes,declared,dropped,recommended_tier,candidates,floor}`.
    """

    axes: list[AxisRecord] = Field(
        default_factory=list,
        description="The axes in the agent's priority order.",
    )
    declared: list[Any] = Field(
        default_factory=list, description="Axes declared later, verbatim."
    )
    dropped: list[Any] = Field(
        default_factory=list, description="Dropped axes: id, reason, module."
    )
    recommended_tier: dict[str, Any] | None = None
    search_mode: dict[str, Any] | None = Field(
        default=None, description="How the round searches its space: {mode, source}."
    )
    floor: dict[str, Any] | None = Field(
        default=None,
        description="The round's support floor: {band, step, source} — the band an "
        "essential reaction's grade must reach to enter the base, and who set it "
        "(human, rule, schedule, lowered).",
    )
    axis_support: dict[str, Any] | None = Field(
        default=None,
        description="With grounding on, each axis construction declared annotated "
        "against the reaction dossier and held to the variants' floor: "
        "{dossier_round, base, floor, axes: {axis id: {reactions, label}}}; an "
        "axis refused for that floor is in `dropped` (`refused_floor`) and in "
        "`declared`, from where an expansion round offers it again. In advisory "
        "mode nothing is refused: `mode` and `flagged` ({axis id: what it adds "
        "below the floor}) record what the card flags.",
    )
    candidates: list[Any] = Field(
        default_factory=list,
        description="Candidates: id, label, rationale, assembly_overlay.",
    )


class DataRecord(Record):
    """The data slot — `rounds/<k>/data`. Identical in every round of a run."""

    measurements: Table | None = tier(
        "bulk",
        default=None,
        description="The engine's long measurement table.",
    )
    raw: Table | None = tier(
        "bulk", default=None, description="The raw measurements, when present."
    )
    report: dict[str, Any] | None = Field(
        default=None, description="Mappings, labels, flags."
    )
    signals: dict[str, Any] | None = tier(
        "bulk", default=None, description="Data signals."
    )
    design_summary: dict[str, Any] | None = Field(
        default=None, description="Design summary."
    )
    phenomenology: dict[str, Any] | None = Field(
        default=None,
        description="What the curves look like, in words (data_phenomenology).",
    )
    producer: Producer = "unknown"
    n_rows: int | None = None


class AssemblyRecord(Record):
    """`…/candidates/<id>/assembly` (or the round's `shared_assembly`): the merge's source
    of truth — observables, noise, scaling, conditions, each an agent block."""

    observables: list[Any] = Field(default_factory=list)
    noise: list[Any] = Field(default_factory=list)
    scaling: list[Any] = Field(default_factory=list)
    conditions: list[Any] = Field(default_factory=list)


class PetabRecord(Record):
    """The PEtab problem as fitted — `petab/*`, tables embedded."""

    problem_yaml: dict[str, Any] | None = None
    observables: Table | None = tier("bulk", default=None)
    conditions: Table | None = tier("bulk", default=None)
    measurements: Table | None = tier("bulk", default=None)
    holdout_measurements: Table | None = tier("bulk", default=None)
    parameters: Table | None = tier("bulk", default=None)
    n_estimated: int | None = None
    n_train: int | None = None
    n_holdout: int | None = None
    producer: Producer = "unknown"


class CostRecord(Record):
    """The compile-and-probe slot (`…/candidates/<id>/cost`). The optimiser
    comparison, when it ran, is its own sibling (`optimizer_comparison`)."""

    compile_s: float | None = None
    objective_eval_s: float | None = None
    median_start_s: float | None = None
    n_probe_starts: int | None = None
    probe_fvals: list[float] = Field(default_factory=list)
    proposed_n_starts: int | None = None
    approved_n_starts: int | None = Field(
        default=None, description="From the cost marker: what the human approved."
    )
    projected_wall_s: float | None = None
    engine: str | None = None
    probe_engine: dict[str, Any] | None = Field(
        default=None,
        description="How the probe's starts ran (here, or dispatched to "
        "`n_workers` processes, and why), each start's wall and CPU, and the "
        "probe's wall against its one-at-a-time work (`speedup`). "
        "`median_start_s` is serial-equivalent: a start's wall when it ran "
        "alone, its CPU when others ran beside it.",
    )
    solver_settings: dict[str, Any] | None = None
    tolerance_agreement: dict[str, Any] | None = tier("bulk", default=None)
    sensitivity_probe: dict[str, Any] | None = tier("bulk", default=None)
    steady_state: dict[str, Any] | None = None


class EstimationRecord(Record):
    """The estimation slot's summary (`…/candidates/<id>/estimation`), as S6
    writes it. The multistart's arrays, the per-start table, earlier
    attempts and a refit are the candidate's own siblings (`multistart`,
    `starts`, `attempts`, `refit`), each written by its own step."""

    optimizer: str | None = None
    seed: int | None = None
    n_starts: int | None = None
    n_data: int | None = None
    x_names: list[str] = Field(default_factory=list)
    best_fval: float | None = None
    best_grad_norm: float | None = None
    best_x_unscaled: dict[str, float] = Field(default_factory=dict)
    fvals: list[float] = tier(
        "bulk", default_factory=list, description="Sorted final objective values."
    )
    ensemble: list[Any] = tier("bulk", default_factory=list)
    ensemble_delta_nllh: float | None = None
    at_bounds: list[Any] = Field(default_factory=list)
    near_bounds: list[Any] = Field(default_factory=list)
    near_bound_fraction: float | None = None
    estimated_inner: dict[str, Any] = Field(default_factory=dict)
    starts: list[Any] | None = tier(
        "bulk", default=None, description="The per-start rows, as S6 lists them."
    )
    producer: Producer = "engine"


class EvaluationRecord(Record):
    """The evaluation slot (`rounds/<k>/evaluation`): S7's report — the
    computed core plus the interpretation and the T2' verdict. Written once,
    whole, when S7 finishes; a round without it has no report. The computed
    core alone (`evaluation_core`) and the attribution (`attribution`) are
    the round's siblings."""

    goal: str | None = None
    best_fval: float | None = None
    n_ensemble: int | None = None
    fit: list[Any] = Field(
        default_factory=list, description="Per observable × condition fit rows."
    )
    chi2_per_dof: float | None = None
    parameters: dict[str, Any] | None = None
    estimated_inner: dict[str, Any] | None = None
    misfit_evidence: dict[str, Any] | None = None
    declared_constants: dict[str, Any] | None = None
    latent_states: dict[str, Any] | None = tier("bulk", default=None)
    identifiability: dict[str, Any] | None = None
    holdout: dict[str, Any] | None = None
    profiles: dict[str, Any] | None = tier("bulk", default=None)
    prediction_uncertainty: dict[str, Any] | None = tier("bulk", default=None)
    noise_check: dict[str, Any] | None = None
    computed_cannot_distinguish: list[Any] = Field(default_factory=list)
    computed_nonetheless_determined: list[Any] = Field(default_factory=list)
    interpretation: dict[str, Any] | None = Field(
        default=None, description="The interpretation agent's block."
    )
    t2prime_passed: bool | None = None
    discrimination: dict[str, Any] | None = Field(
        default=None, description="Search rounds: the selection table and winner."
    )
    attribution: dict[str, Any] | None = tier("bulk", default=None)


class SelectionRecord(Record):
    """The selection slot (`rounds/<k>/selection`): the criterion values and
    the winner. petab_select's interchange files are the round's sibling
    `selection_files`."""

    criterion: str | None = None
    winner: str | None = None
    decisive: bool | None = None
    values: dict[str, Any] = Field(
        default_factory=dict, description="Per model: the criterion values."
    )
    weights: dict[str, Any] = Field(default_factory=dict)
    tool: str | None = None
    version: str | None = None
    model_space_sha: str | None = None
    models: list[Any] = tier(
        "bulk", default_factory=list, description="petab_select models.yaml."
    )
    problem_yaml: dict[str, Any] | None = None
    indistinguishable: list[Any] = Field(default_factory=list)
    undecided_axes: list[Any] = Field(default_factory=list)


class RevisionRecord(Record):
    """`rounds/<k>/revision` — the move the loop took out of this round, with the
    agent's reasoning, and the cycle hash the round was judged by."""

    move: dict[str, Any] | None = Field(
        default=None, description="{type, args}; None means stop."
    )
    motivated_by: str | None = None
    expected_effect: str | None = None
    why: str | None = Field(default=None, description="When no move: the reason.")
    config_hash: str | None = None
    best_fval: float | None = None


class ExpansionRecord(Record):
    """The round's expansion decision (`rounds/<k>/expansion`). The offer the
    human answered and the diagnostics the agent asked for are the round's
    siblings `expansion_offer` and `expansion_diagnostics`."""

    expanded: bool | None = None
    next_round: int | None = None
    from_winner: str | None = None
    expanded_from: str | None = None
    base_was_the_agents_recommendation: bool | None = None
    axes: list[str] = Field(default_factory=list)
    carried_undecided: list[str] = Field(default_factory=list)
    base: str | None = None
    not_bought_by_ceiling: list[str] = Field(default_factory=list)
    why: str | None = None
    floor: dict[str, Any] | None = Field(
        default=None,
        description="With grounding on, the support floor of the round the offer "
        "seeds, as the answer left it: {band, step, source} (schedule, or human "
        "when the person set it at the card).",
    )
    refused_for_floor: list[str] = Field(
        default_factory=list,
        description="The axes the offer refused for that floor (the round's "
        "`axis_refused` says why).",
    )


class RoundStatusRecord(Record):
    """Which slots the round has, validated by what — computed from the
    record and its markers (which carry the validated slot shas)."""

    validations: dict[str, Any] = Field(
        default_factory=dict,
        description="Per candidate (or `_round`) and slot: the battery that validated "
        "a supplied or seeded slot on entry.",
    )
    markers: dict[str, Any] = Field(
        default_factory=dict,
        description="Marker name → its JSON payload (producer, validated_by, "
        "and the `files` shas stamped when the marker was set).",
    )
    slots: dict[str, Any] = Field(
        default_factory=dict,
        description="Per slot: key, files (part + sha16), present, producer, "
        "validated_by/at, drifted — computed from the record and the markers, "
        "so there is no separate index file.",
    )
    candidates: dict[str, Any] = Field(
        default_factory=dict, description="The same, per candidate."
    )
    updated_at: str | None = None
