"""Leaf records and the conventions every record follows.

Three conventions, declared once here so no record re-invents them:

* **Tiers.** Every field carries a tier — `core` (what a reader needs to
  understand the answer), `bulk` (arrays, traces, tables) or `audit` (prompts,
  raw replies, the ledger). A field with no tier is `core`. `store.prune`
  drops whole tiers to make a smaller copy for sharing, and every record that
  lost a field says so in `elided`, so a shared copy is honest about what it
  left out.

* **Extras are kept.** Most artifacts carry agent-authored content whose exact
  keys vary by role and by round; a record that rejected an unknown key would
  throw information away on import. So records allow extra keys (they survive
  the HDF5 round trip like any field) and type the keys the engine itself
  reads. Tightening a field from `dict` to a class is a later, per-record step.

* **No datetimes, no paths.** Timestamps are ISO strings exactly as the ledger
  writes them; file locations are `FileRef` records with a sha, never `Path`
  objects. Both choices keep the HDF5 form byte-stable across machines.

Polymorphic gate values are the one place `object` was tempting and is not
allowed: its schema would be empty. `GateValue` is the union of every shape a
gate writes today; a gate that needs more declares a subtype.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2  # 2: every independently written artifact is its own group

Tier = Literal["core", "bulk", "audit"]
TIERS: tuple[str, ...] = ("core", "bulk", "audit")

Producer = Literal[
    "engine",
    "agent:construction",
    "agent:data_extraction",
    "agent:assembly",
    "agent:observation",
    "agent:condition",
    "agent:research",
    "agent:construction_verification",
    "agent:assembly_verification",
    "agent:interpretation",
    "agent:revision_proposal",
    "agent:revision",
    "human",
    "policy",
    "user-supplied",
    "seeded-from-previous-round",
    "unknown",
]

GateValue = float | int | bool | str | list[float] | list[str] | dict[str, Any] | None


def tier(level: Tier, **kwargs: Any) -> Any:
    """A pydantic Field carrying its tier in the JSON Schema extras.

    Written as a helper so the tier is spelled once per field and read back by
    both the schema generator (docs/RESULT-SCHEMA.md) and `store.prune`.
    """
    extra = dict(kwargs.pop("json_schema_extra", None) or {})
    extra["tier"] = level
    return Field(json_schema_extra=extra, **kwargs)


class Record(BaseModel):
    """Base of every record: extras allowed, an `elided` list for pruning."""

    model_config = ConfigDict(extra="allow", validate_assignment=False)

    elided: list[str] = tier(
        "core",
        default_factory=list,
        description="Fields removed from this record by a tiered copy "
        "(store.prune). Empty on a full record.",
    )


class FileRef(Record):
    """A file the record refers to but does not embed, with its content hash
    (legacy: the record itself holds no file paths; these come from
    transcribed legacy run directories)."""

    path: str = Field(
        description="The legacy file path (relative to the legacy run "
        "directory) that a transcribed entry referred to."
    )
    sha16: str | None = Field(
        default=None, description="First 16 hex digits of the sha256 of the text."
    )


class Table(Record):
    """A columnar table: one dataset per column in HDF5, native for numbers.

    Chosen over a list of row dicts because hdfdict stores a list of dicts as
    one YAML string, which is neither native nor addressable. Column order is
    kept in `columns`; `data` holds the values by column name.
    """

    columns: list[str] = Field(description="Column names, in order.")
    data: dict[str, list] = tier(
        "core",
        default_factory=dict,
        description="Values by column, one list per column, row-aligned.",
    )

    @property
    def n_rows(self) -> int:
        return len(next(iter(self.data.values()))) if self.data else 0

    @classmethod
    def from_rows(cls, rows: list[dict], columns: list[str] | None = None) -> Table:
        cols = list(columns) if columns else sorted({k for r in rows for k in r})
        return cls(columns=cols, data={c: [r.get(c) for r in rows] for c in cols})

    @classmethod
    def from_dataframe(cls, df) -> Table:
        """A missing value is None. An EMPTY STRING is a missing value too: a
        TSV on disk never distinguished the two (an empty cell reads back as
        NaN), and the engine writes `""` for "no value" in string columns such
        as `parameterType` — which its readers then test with `isna`."""
        cols = [str(c) for c in df.columns]
        data = {}
        for c in cols:
            col = df[c]
            data[c] = [
                (
                    None
                    if v is None or v == "" or (isinstance(v, float) and v != v)
                    else (v.item() if hasattr(v, "item") else v)
                )
                for v in col.tolist()
            ]
        return cls(columns=cols, data=data)

    def to_rows(self) -> list[dict]:
        n = self.n_rows
        return [{c: self.data[c][i] for c in self.columns} for i in range(n)]

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame({c: self.data.get(c, []) for c in self.columns})


class SolverSettings(Record):
    """The integrator settings a gate verdict was reached under."""

    solver: str | None = None
    atol: float | None = None
    rtol: float | None = None
    maxsteps: int | None = None


class GateRecord(Record):
    """One deterministic gate verdict — `gates.GateResult` plus where it ran."""

    gate_id: str = Field(
        description="The gate's id, e.g. estimation_waterfall_plateau."
    )
    tier_level: str = Field(
        alias="tier", description="T0 | T1 | T2 | T2prime | T3, as the gate declares."
    )
    passed: bool
    blocking: bool = True
    value: GateValue = Field(default=None, description="The computed quantity.")
    threshold: GateValue = Field(
        default=None, description="The declared threshold it was compared against."
    )
    detail: str = ""
    advisory_findings: list[Any] = Field(default_factory=list)
    solver_settings: SolverSettings | None = None
    module: str | None = Field(default=None, description="Module that ran the gate.")
    round: int | None = None
    candidate: str | None = Field(
        default=None, description="Candidate id when the gate ran per candidate."
    )
    at: str | None = Field(default=None, description="ISO timestamp, from the ledger.")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class LedgerEvent(Record):
    """One ledger row, verbatim. Extra keys are the row's payload."""

    ts: str
    round: int = 0
    module: str = ""
    event: str


class DecisionRecord(Record):
    """A human (or policy, or auto) answer at a gate, with what the engine read
    from the note. Written by `ask_once` at `…/decisions/<module>`; the
    `human_gate` ledger rows carry the same answer."""

    module: str
    question: str | None = None
    approved: bool | None = None
    note: str = ""
    mode: str | None = Field(
        default=None, description="interactive | file | auto | policy | recorded."
    )
    signed: str | None = Field(
        default=None,
        description="How the signature reads: a human, policy(<sha>), auto.",
    )
    at: str | None = None
    round: int | None = None
    consequences: list[str] | None = None
    source_file: str | None = Field(
        default=None, description="The decision file this was read from, if any."
    )


class AttemptRecord(Record):
    """One raw reply of an agent, accepted or not."""

    attempt: int
    text: str | None = tier("audit", default=None, description="The raw reply text.")
    gate_failures: list[str] = Field(default_factory=list)


class AgentCallRecord(Record):
    """Everything archived about one agent role in one round.

    `calls` holds the ledger's `agent_call` rows (one per invocation, with
    model, cost, duration and prompt sha); the prompt and replies in the record
    are those of the LAST invocation, because the engine overwrites them per role.
    """

    role: str | None = Field(default=None, description="Filled from the key.")
    reply: dict[str, Any] | None = Field(
        default=None, description="The accepted, validated JSON object."
    )
    prompt: str | None = tier(
        "audit", default=None, description="The exact prompt of the last call."
    )
    prompt_gate: GateRecord | None = Field(
        default=None, description="The agent_prompt_bytes gate for that prompt."
    )
    attempts: list[AttemptRecord] = tier("audit", default_factory=list)
    calls: list[LedgerEvent] = Field(
        default_factory=list,
        description="The ledger's agent_call rows for this role in this round.",
    )
    redrafts: list[LedgerEvent] = Field(
        default_factory=list, description="The ledger's redraft rows for this role."
    )
    cost_usd: float | None = Field(
        default=None, description="Sum of cost_usd over `calls`, when reported."
    )
    # each a group the engine writes beside the reply
    pinned: dict[str, Any] | None = Field(
        default=None, description="A reply pinned for re-use (the interpretation)."
    )
    dossier: Any = tier(
        "audit",
        default=None,
        description="The retry dossier: earlier attempts and why each failed.",
    )
    prompt_misses: dict[str, Any] = tier(
        "audit",
        default_factory=dict,
        description="Why a cached reply was NOT reused: both prompts and the first difference.",
    )
    replies: dict[str, Any] = tier(
        "audit",
        default_factory=dict,
        description="Per attempt: the raw reply, and `timeout`/`killed` with partial output.",
    )
    base_key: Any = Field(
        default=None,
        description="expansion: the base model the candidates were written against.",
    )
    overlay_audits: dict[str, Any] = tier(
        "bulk",
        default_factory=dict,
        description="assembly_verification: overlay audits by content sha.",
    )
    fallback_applied: Any = Field(
        default=None,
        description="A deterministic fallback the engine applied to this role's reply.",
    )


class QuestionRecord(Record):
    """A structural question an agent raised for the human (`questions`)."""

    id: str
    raised_by: str | None = None
    raised_round: int | None = None
    topic: str | None = None
    question: str | None = None
    confidence: str | None = None
    human_answer: str | None = None
    status: str | None = None
