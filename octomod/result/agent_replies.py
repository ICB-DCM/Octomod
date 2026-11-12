"""One record per agent role: the reply an agent must return, as a class.

`RoleSpec.required_keys` says which top-level keys a reply must carry; these
classes say that AND what type each key has, and `agents.call_agent`
validates every reply against them before the engine acts on it — a list
where a dict was promised is the agent's failure at the seam, not a
`KeyError` two modules later.

The prompt's output contract is NOT rendered from these classes, on purpose.
The hand-written contract text in `agents.ROLES` carries instructions a schema
cannot ("one sentence per decision", "never a measurement value"), and the
prompt bytes are what `prompt_sha` and `call_cached` identify a call by.
`tests/agent_replies_unit.py` asserts that the required fields here and
`required_keys` there are the same set, so the two cannot drift apart.

Every class allows extra keys: the roles add optional blocks
(`model_space`, `recommended_tier`, `expand_from`, `processing`, a
`_fixture_note` on stubs) that are read when present and must not be refused.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Reply(BaseModel):
    """Base of every agent reply: extras kept, nothing coerced silently."""

    model_config = ConfigDict(extra="allow")


class ConstructionReply(Reply):
    """`construction`: the model it draws and the space it is unsure about."""

    network: dict[str, Any]
    antimony: str
    parameters: list[Any]
    build_report: dict[str, Any]
    consulted_sources: list[Any]
    entity_glossary: dict[str, Any]
    model_space: list[Any] = Field(default_factory=list)
    recommended_tier: dict[str, Any] | None = None
    declared_constants: list[Any] = Field(default_factory=list)
    # the conversions a base cannot be complete without, `{equation, why}`:
    # the engine searches for each and asks again with what it admitted
    missing: list[Any] = Field(default_factory=list)


class DataExtractionReply(Reply):
    """`data_extraction`: columns → the long table's labels."""

    mappings: list[Any]
    observable_labels: list[Any]
    flags: list[Any]
    notes: str
    processing: list[Any] = Field(default_factory=list)


class ObservationModelReply(Reply):
    """`observation`: the observation function per measured label."""

    observables: list[Any]
    model_space: list[Any] = Field(default_factory=list)


class ConditionEncodingReply(Reply):
    """`condition`: experimental conditions as parameter settings."""

    conditions: list[Any]


class ResearchReply(Reply):
    """`research`: literature evidence for construction."""

    evidence_items: list[Any]
    queries_run: list[Any]
    notes: str


class KnowledgeReply(Reply):
    """`knowledge`: what is known about the system — its reactions, the facts
    a model of it needs, and their sources, every source classified and none
    graded. `system` and `species` are the survey's; a targeted reply answers
    its questions with reactions and facts alone. The survey's own rules (a
    `system` summary, species covering the equations) are the knowledge
    module's reply battery (`knowledge.battery`)."""

    reactions: list[Any]
    facts: list[Any]
    queries_run: list[Any]
    notes: str
    system: dict[str, Any] | None = None
    species: list[Any] = Field(default_factory=list)


class VerificationKnowledgeReply(Reply):
    """`knowledge_verification`: a second classification of each counting
    evidence item, read from the cached document's text around its quote."""

    classifications: list[Any]


class VerificationReply(Reply):
    """`construction_verification` / `assembly_verification`: an independent audit."""

    verdicts: list[Any]
    overall: str


class EvaluationInterpretationReply(Reply):
    """`interpretation`: diagnosis and epistemic claims."""

    diagnosis: str
    misfit_hypotheses: list[Any]
    cannot_distinguish: list[Any]
    nonetheless_determined: list[Any]
    answers_intent: list[Any]
    recommendation: str


class RevisionProposalReply(Reply):
    """`revision_proposal`: one move from the closed grammar, motivated."""

    move: dict[str, Any]
    motivated_by: str
    expected_effect: str


class SpaceExpansionReply(Reply):
    """`revision`: what the model space was missing."""

    axes: list[Any]
    diagnosis: str
    stop_instead: bool
    expand_from: dict[str, Any] | None = None
    requested_diagnostics: list[Any] = Field(default_factory=list)


class VariationsReply(Reply):
    """The candidates of a two-call discrimination round, each a declared
    difference from the tested base."""

    candidates: list[dict[str, Any]]
    build_report: dict[str, Any]


REPLY_CLASSES: dict[str, type[Reply]] = {
    "construction": ConstructionReply,
    "data_extraction": DataExtractionReply,
    "observation": ObservationModelReply,
    "condition": ConditionEncodingReply,
    "research": ResearchReply,
    "knowledge": KnowledgeReply,
    "knowledge_verification": VerificationKnowledgeReply,
    "construction_verification": VerificationReply,
    "assembly_verification": VerificationReply,
    "interpretation": EvaluationInterpretationReply,
    "revision_proposal": RevisionProposalReply,
    "revision": SpaceExpansionReply,
    "expansion": VariationsReply,
}


def required_fields(role: str) -> list[str]:
    """The fields a reply of `role` must carry, read off its class."""
    cls = REPLY_CLASSES[role]
    return [name for name, info in cls.model_fields.items() if info.is_required()]


def contract_failures(role: str, parsed: Any) -> list[str]:
    """Every way `parsed` fails `role`'s reply class, as sentences an agent can
    act on. Empty when the reply fits. A role without a class fails nothing
    here (its `required_keys` check still applies)."""
    cls = REPLY_CLASSES.get(role)
    if cls is None:
        return []
    if not isinstance(parsed, dict):
        return [f"reply must be a JSON object, got {type(parsed).__name__}"]
    try:
        cls.model_validate(parsed)
    except ValidationError as e:
        out = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"]) or "<root>"
            if err["type"] == "missing":
                out.append(f"missing required top-level key: {loc}")
            else:
                out.append(f"{loc}: {err['msg']}")
        return out
    return []
