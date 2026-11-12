"""Typed holes: the only place where the workflow hands control to a model.

A module never asks an agent an open question. It declares a role, a context
dict and a JSON contract; the agent fills that hole and nothing else. Two
backends satisfy one signature — "llm" (headless `claude -p`) and "stub"
(canned JSON from the testcase folder, for token-free pipeline runs) — so a
module cannot tell, and cannot come to depend on, which one answered.

Nothing a model returns is trusted until it parses and carries the contract's
required top-level keys. A reply that never gets there raises: a half-filled
hole is not a partial result to patch downstream, it is a failed call.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from octomod.config import SKILLS_DIR
from octomod.orchestration.ledger import sha256_text


class AgentCallError(Exception):
    """An agent did not deliver a contract-shaped reply. Fatal to the module —
    the workflow does not improvise around a hole it could not fill."""


class AgentKilled(AgentCallError):
    """The `claude -p` child was KILLED (a signal, or the shell's 128+signal
    exit): a person or the machine stopped it. Not a bad reply, so never
    retried; a retry would start a call only killing the parent could stop."""


# Imported below AgentCallError on purpose: both backends raise it and import
# it from this module, so it must exist before their module bodies run.
from octomod.agents.llm_backend import extract_json, run_llm  # noqa: E402
from octomod.agents.stub_backend import load_stub, stub_path  # noqa: E402


@dataclass(frozen=True)
class RoleSpec:
    """One typed hole: which skill briefs it, what its reply must contain.

    `tools` is the grant ONE call runs under (`call_agent` sets it from
    `granted_tools`); None on the registry's own entry, which means the
    role's default grant."""

    name: str
    skill_file: str
    required_keys: list[str]
    contract: str
    tools: tuple[str, ...] | None = None


ROLES: dict[str, RoleSpec] = {}


# what each role that receives `known_facts` is asked to do with one, beside
# the note every such role shares
_FACT_USE = {
    "construction": (
        "A parameter whose value you take from a fact carries `source: "
        '"knowledge:<fact id>"` in `parameters`, and a decision that rests on '
        "one cites its id (`fact_2`) in its `evidence` entries."
    ),
    "observation": (
        "A noise floor, a detection limit or a fixed sigma taken from a fact "
        "names its id (`fact_2`) in that observable's `rationale`."
    ),
    "condition": (
        "An override or a pre-equilibration taken from a fact names its id "
        "(`fact_2`) in that condition's `rationale`."
    ),
    "revision": (
        "A parameter an axis adds whose value comes from a fact carries "
        '`source: "knowledge:<fact id>"` in `adds_parameters`, and an axis a '
        "fact motivates cites its id in its `rationale`."
    ),
    "expansion": (
        "A parameter a candidate adds whose value comes from a fact carries "
        '`source: "knowledge:<fact id>"` in `adds_parameters`, and a decision '
        "that rests on one cites its id in its `evidence` entries."
    ),
}


def _known_facts_note(role: str) -> str:
    """The contract note on `known_facts`, for a role the routing table
    grants it: the facts the knowledge module found for that role."""
    return (
        '\nNOTE on "known_facts" when present: what the knowledge module found, '
        "before the intent was frozen, that a model of this system needs beyond "
        "its reactions — each with an `id` (`fact_1`), a `kind`, a `statement` "
        "(a `value` and `unit` where it is quantitative), what it `applies_to`, "
        "its evidence and the grade the engine gave it (`not_applicable` when it "
        "was gathered offline). Only the facts meant for your role reach you. Use "
        "a fact where it applies instead of inventing the assumption, and where "
        f"you depart from one, say why. {_FACT_USE[role]}\n"
    )


def _role(name: str, required_keys: list[str], contract: str) -> None:
    ROLES[name] = RoleSpec(name, f"{name}.md", required_keys, contract.strip())


_role(
    "construction",
    [
        "network",
        "antimony",
        "parameters",
        "build_report",
        "consulted_sources",
        "entity_glossary",
    ],
    """
{
  "network": {"species": [{"id": "...", "name": "...", "compartment": "...", "set_per_condition": false}],
              "interactions": [{"id": "...", "type": "phosphorylation|binding|conversion|synthesis|degradation|regulation",
                                 "participants": [{"species": "...", "role": "substrate|product|modifier", "stoichiometry": 1}],
                                 "evidence_tier": "direct|transferred|default|to_be_estimated", "note": "..."}]},
  "antimony": "model <name>\\n  ...full antimony source...\\nend",
  "parameters": [{"id": "...", "nominal_value": 0.0, "unit": "...", "evidence_tier": "direct|transferred|default|to_be_estimated",
                   "source": "...", "estimate": true, "lb": 0.0, "ub": 0.0, "varies_by": [], "set_per_condition": false}],
  "missing": [],
  "build_report": {"decisions": [{"decision": "...",
                                    "rationale": "the argument for THIS choice, not a restatement of it",
                                    "alternatives_considered": "...",
                                    "evidence": [{"source": "lab_note|literature|database|general_knowledge", "locator": "REQUIRED for lab_note and literature — where exactly: quote the phrase from the note, or give DOI/PMID + figure/table/section", "supports": "what it actually says", "origin": "user-provided|database-supported|literature-supported|inferred|assumed"}],
                                    "evidence_tier": "direct|transferred|default|to_be_estimated",
                                    "confidence": "high|medium|low", "user_decision_required": false, "question": ""}]},
  "declared_constants": [{"expression": "X + Y", "tolerance": 0.1, "locator": "quote the sentence that says so", "why": "what it is asserting"}],
  "basal_state": {"initial_values_are_steady_state": true, "suggest_preequilibration": false,
                  "note": "one or two sentences: what the unstimulated state is and how the initial values relate to it"},
  "consulted_sources": ["..."],
  "entity_glossary": {"species": [{"id": "Y_a", "denotes": "ALL active forms of Y; the two inactivation routes are lumped into one",
                                    "unit_convention": "fraction of total Y, total normalised to 1", "lump_membership": "Y_a covers the singly- and doubly-modified forms"}],
                      "parameters": [{"id": "u", "role": "stimulus level, set per condition", "convention": "relative units against the standard stock", "set_per_condition": true}]},
  "recommended_tier": {"tier": "base|top1|top2|...|all", "reasoning": "one line: how many models you consider GENUINELY necessary, and why"},
  "model_space": [{"id": "short_slug", "question": "the structural question this axis settles",
                    "default": "off|on",
                    "priority": 1, "priority_reason": "one line: why this axis is the most load-bearing (1 = most)",
                    "on_antimony_patch": {"replace_reaction": "R3", "with": "R3: X -> Z; cell * (k1*Y_a + k2*X) * X;"},
                    "adds_parameters": [{"id": "k2", "nominal_value": 0.0, "unit": "...", "lb": 0.0, "ub": 0.0, "evidence_tier": "to_be_estimated", "source": "...", "estimate": true, "denotes": "rate of the second route this axis adds"}],
                    "rationale": "why this mechanism is plausible at all",
                    "discriminating_evidence": "which observable, in which condition, separates on from off"},
                   {"id": "second_slug", "question": "an OBSERVATION-layer question: does the Z readout carry a nonzero background?",
                    "default": "off", "priority": 2, "priority_reason": "one line",
                    "on_assembly_patch": {"add_offset": {"observable_label": "Z"}},
                    "adds_parameters": [],
                    "rationale": "why this alternative observation model is a hypothesis about the MEASUREMENT, not a fit device",
                    "discriminating_evidence": "the observation-layer evidence: which readout, at which signal level, shows the defect"}]
}
NOTE on "basal_state": OPTIONAL. Your view of the model's starting point, for
the condition-encoding agent, which decides pre-equilibration per measured
condition: are the initial values you wrote the unstimulated steady state
(the cells before the stimulus), and should the measured conditions be
simulated to that steady state first? Suggest it when the basal state is a
balance you cannot write down as initial values (synthesis against decay, a
cycle whose resting split depends on estimated rates). A suggestion, not a
decision.

NOTE on mechanism discrimination: you write the BASE only; the expansion
agent writes the candidates, each as a declared difference from your base. A
reply that carries candidates is refused.

NOTE on "retrieved_evidence" when present: a list of evidence items, each
with `id`, `source`, `title`, `year`, `locator`, `supports`, `quote`, `url` and an
`origin`. `origin: human` = the person who staged this problem already has this
source and wrote down what it says — it is the literature they expect the model
to build on, so use it and cite it. `origin: research` = the online retrieval
role found it. Cite either kind in a decision's `evidence` entries by its `id`
(`lit_1`) or its `source` string verbatim, with `origin: literature-supported`.
The evidence TIER still follows what the source establishes for THIS system, not
who handed it to you. You never see the document itself; `supports` and `quote`
are what reach you, and a claim the item does not make must not be attributed to it.

NOTE on "essential_reactions" when present: the reactions the knowledge module
(run before the intent was frozen) and the engine's searches describe for this
system — each entry with its `origin` (`human` = the intent requires it,
`knowledge` = the module's survey, `search` = a targeted search that answered a
conversion you named missing), its `grade` (a band from a declared rule table,
with the source that earned it in `because`; never a probability) and the
evidence that counts for it. `support_floor` says in words what a grade had to
reach to be in the set; `knowledge_summary` is what is known about the system,
its scope and what is unknown; `grounding_instruction` says which of two modes
the run is in. ADVISORY (the default): the set is prior knowledge, not a fence —
build the model the question and the data need, use the entries where they
apply with their species ids verbatim, implement every `required: true` entry,
and add any reaction the model needs (a drift, a background, one copy per
population, a mechanism nothing describes); every reaction is annotated and each
one the dossier does not back is shown to the person with your rationale.
In advisory mode `prior_reactions` is the whole dossier, graded, essential or
not: the entries outside the set are candidates to use where the question needs
them. STRICT: the base is EXACTLY the set — implement every entry in a direction
its rate law carries, with its species ids verbatim, and add no conversion it
lacks.
In both, kinetics, modifiers, parameters, initial values and the glossary are
yours; a participant held as a parameter (a dose) keeps the entry's id as the
parameter's id; where a decision rests on an entry, cite its evidence ids
(`req_1.e1`) in that decision's `evidence`.
NOTE on "missing": OPTIONAL, and read only in strict mode. When the model cannot
be complete without a conversion the set lacks, build the best model the set
allows and name each such conversion here, `{equation, why}`, species ids
verbatim: the engine searches the literature for it, admits what reaches the
support floor into the set, and asks you again with it (`engine_feedback`). A
conversion you write without naming it here fails `model_essential_reactions`.
NOTE on "set_per_condition": OPTIONAL flag on a `parameters` entry, a
`network.species` entry or a glossary entry: true on every quantity the
experimental conditions set (a dose, an inhibitor level, a genotype switch). The
engine checks that each one reaches a required entity through the reaction
graph (`model_connected`).

NOTE on "entity_glossary" (REQUIRED): what your model MEANS, for the agents that
map readouts onto it without having built it. EVERY species gets an entry: what
it denotes physically, its unit/scale convention, and which real states it lumps
("Y_a represents ALL active forms of Y; the two inactivation routes are
lumped into one"). Every
parameter the assembly must understand (dose parameters set per condition,
inhibitor switches, totals) gets a role and convention. A total readout is a sum
over exactly the states YOU chose to represent — the glossary is where you say
which. Missing species entries fail a deterministic check and come back to you.

NOTE on "priority" and "recommended_tier": you price your own confidence. Rank
the axes (1 = the one whose answer changes the most; one line each) and say in
recommended_tier how many models you consider genuinely necessary — "base"
(one model: get it working, read its fits and residuals first, let the
expansion loop propose from evidence), "top<k>" (the k highest-priority axes,
each fitted on its own against the base: k+1 models; every on/off combination,
2^k models, only when the human asks for it) or "all". We do not run models
because we can: recommend the
smallest tier you can argue is informative. The human sees every tier with its
model count and decides.

NOTE on "model_space" patch kinds: an axis carries EITHER on_antimony_patch
(a structural alternative: replace one reaction line, or append lines; one
hypothesis that needs several edits, e.g. removing several reactions together,
is a LIST of such patches, applied in order, all or nothing) OR
on_assembly_patch (an observation-layer alternative), never both. A NEW STATE
is added with an `append` block that declares the species, its initial value
and its reactions — `replace_reaction` alone cannot introduce a species, and a
patch whose rate law names an undeclared symbol is dropped. A dropped patch
does not mean a state cannot be added: declare it in the same `append` block
and the axis stands. Observation
kinds: {"change_observable_formula": {"observable_label", "new_formula"}},
{"change_noise_model": {"observable_label", "new_distribution": "normal|laplace"}},
{"change_noise_model": {"observable_label", "new_per": "condition"}} (one sigma
per treatment arm for that observable — the arm-specific noise alternative;
the observable_label is REQUIRED, an axis without it is dropped)
or {"change_noise_model": {"observable_label", "new_formula": "sigma_obs_x * <this observable's signal expression>"}}
(proportional noise), {"add_offset": {"observable_label"}}, {"remove_scaling":
{"observable_label"}}, {"change_scaling": {"observable_label" | "observable_ids": [...],
"per": "observable|timepoint|condition", "shared_across_observables": false | "<group>",
"pin_first_to_one": false}} (one scale factor per measurement time or per condition,
optionally one parameter set shared by a group of readouts),
{"change_condition": {"condition_label",
"overrides": {"<model parameter>": value}}} — the last only for WHICH parameter a
perturbation enters (hypothesis class); changing a measured factor's value or
pre-equilibration reinterprets the data and is refused. Name observables and
conditions by their DATA labels (the measured quantity / condition as the lab note
names them) — no estimation problem exists yet when you write this. One
observation axis per observable. Transformation axes (lin/log) are refused until
criterion comparability exists. Observation axes are few and evidence-motivated:
cite the observation-layer evidence, not general dissatisfaction with the fit.

NOTE on "model_space": the set of structural choices you are NOT sure about,
expressed as independently toggleable axes on top of the base model. Every
`user_decision_required` decision you raise SHOULD normally appear here too —
a question worth asking the human is a question worth testing against the data.
Each axis must be switchable on its own: give the exact Antimony patch its
"on" state applies and the parameters that come with it. `default` says which
state the base `antimony` above encodes. An axis whose two states cannot be
told apart by any measurement in the data is not an axis — say so in
`discriminating_evidence` and leave it out.
Explicit time (`time`, `exp` and the standard functions) is accepted in a patch,
but PREFER to write a transient as an additional state with an initial value and
first-order decay: a state is a removable mechanism the fit can test (its rate,
its neutral value); an explicit function of time is a curve. Use `time` only
for a genuinely external, declared forcing such as a dosing schedule.

NOTE on "neutral_value" (STRONGLY PREFERRED where it is honest): for each entry
of `adds_parameters`, give the value at which that parameter makes the axis's
term VANISH, recovering the base model exactly. An added route has
`neutral_value: 0`. A saturation or feedback should be WRITTEN so that a finite
value turns it off — `k*A/(1 + beta*A)` with `neutral_value: 0` for beta, not
`k*A/(1 + A/Km)`, whose off-state is Km at infinity and cannot be declared.
The scale and the bounds do NOT constrain this: a parameter estimated on log10
with `lb: 1e-5` can still be switched off at exactly 0, because the box
constrains estimation and a switched-off parameter is fixed, not estimated. The
one mechanical condition is that two axes replacing the SAME reaction can never
both be neutral, and neither can two axes that reuse one parameter id with
different off-states. Where you can declare it,
every candidate the axes make shares one compiled model and the candidates
are exactly nested; where you cannot, say nothing and each candidate is built on
its own, as before. Every declaration is CHECKED by simulation against the base
model, so a wrong one costs nothing but is recorded — do not guess one.
THE RULE, stated once: EVERY parameter an axis adds should carry `neutral_value`.
A parameter with no honest off-state of its own — a half-saturation `K` in
`k*A/(K + A)`, a Hill exponent — may omit it ONLY when another parameter of the
SAME axis switches the whole term off (`k` with `neutral_value: 0` makes `K`
irrelevant): the engine then fixes `K` at its nominal value in the off-state
candidates, estimates it in the on-state ones, and checks by simulation that the
term really is gone. An axis in which NO parameter declares a neutral value is
built as its own structure — one extra compile, and its candidates are not
exactly nested. Write the strength in front of the term and declare its zero.
"""
    + _known_facts_note("construction"),
)

_role(
    # a discrimination round's candidates, as declared differences from the
    # base construction wrote; the engine builds each one (expansion.py)
    "expansion",
    ["candidates", "build_report"],
    """
{
  "candidates": [{"id": "M1_short_slug", "label": "...", "rationale": "why this mechanism, and which tested feature it switches",
                   "set_parameters": [{"id": "an EXISTING base parameter", "nominal_value": 1.0, "estimate": false, "lb": 0.0, "ub": 0.0}],
                   "on_antimony_patch": [{"replace_reaction": "R3", "with": "R3: X -> Z; cell * (k1*Y_a + k2*X) * X;"},
                                         {"append": ["R9: -> W; cell * k9 * X;"]}],
                   "adds_parameters": [{"id": "k2", "nominal_value": 0.0, "unit": "...", "lb": 0.0, "ub": 0.0,
                                         "evidence_tier": "to_be_estimated", "source": "...", "estimate": true}],
                   "entity_glossary": {"species": [], "parameters": []}}],
  "missing": [{"equation": "A + B -> C", "why": "the conversion a candidate adds that no entry at the variants' floor describes"}],
  "build_report": {"decisions": [{"decision": "...", "rationale": "...", "alternatives_considered": "...",
                                    "evidence": [{"source": "lab_note|literature|database|general_knowledge", "locator": "...", "supports": "...", "origin": "user-provided|database-supported|literature-supported|inferred|assumed"}],
                                    "evidence_tier": "direct|transferred|default|to_be_estimated",
                                    "confidence": "high|medium|low", "user_decision_required": false, "question": ""}]}
}
NOTE on "essential_reactions", "prior_reactions" and "variants_floor" when
present: the knowledge module ran before the intent was frozen.
`essential_reactions` is the base's essential set, which `base_model`
implements; `prior_reactions` is every reaction the module and the round's
searches describe for this system, each with its `origin` (`human`, `knowledge`,
`search`) and its `grade` (a band from a declared rule table, with the source
that earned it in `because`; never a probability). A candidate keeps every
reaction of the base and may ADD a conversion described at `variants_floor` or
better (`words` says it in a sentence); take it from `prior_reactions` with its
species ids verbatim. The engine annotates what each candidate adds. In
advisory mode (the default; `grounding_instruction` says which) a candidate may
add any conversion, and one below the floor or one no entry describes is kept
and flagged to the person on the card. In strict mode the engine REFUSES a
candidate that adds a conversion below the floor, or one no entry describes: it
leaves the set, named on the card. A candidate that changes only rate laws or
switches adds no conversion and is never refused for the floor.
NOTE on "missing": OPTIONAL, and read only in strict mode. A conversion a
candidate needs that no entry at the variants' floor describes, `{equation,
why}`, species ids verbatim: the engine runs ONE targeted literature search for
this round's `missing` before it refuses anything, and admits what reaches the
variants' floor. Name it here and keep the candidate; the search decides
whether it stays.
"""
    + _known_facts_note("expansion"),
)

_role(
    "data_extraction",
    ["mappings", "observable_labels", "flags", "notes"],
    """
{
  "mappings": [{"file": "...", "observable_label": "...", "observable_column": null, "time_column": "...",
                 "value_column": "...", "condition_columns": ["..."], "condition_label_template": "dose={dose}",
                 "replicate_column": null, "error_column": null, "units": "arbitrary",
                 "error_type": "sd|sem|replicates|none|column"}],
  "observable_labels": [{"label": "...", "description": "...", "units": "...", "error_type": "...", "n": null}],
  "flags": ["anything suspicious — flag, never silently exclude"],
  "notes": "...",
  "processing": [{"kind": "subtract_reference", "labels": ["..."], "reference": {"condition_label": "..."},
                  "rationale": "quote the note or name the file feature (a blank row, a reference column)"}],
  "below_detection": [{"observable_label": "...", "threshold": 6.3, "rule": "imputed|dropped|left_as_is",
                       "note": "what the source says it did with values below its detection floor"}]
}
NOTE on LONG-FORMAT files: when one column NAMES the measured
quantity (e.g. `readout` = pStat1 / pStat3 / pStat5) and one column holds the
values, set `observable_column` to that naming column and leave `observable_label`
null; every row is assigned to the label written in that column, and every such
label must appear in `observable_labels`. The observable is NOT a condition:
never put the naming column into `condition_columns`.
NOTE on "error_column": when the file carries a per-row measurement error
on the value's own scale (a sigma, an SE of the summary statistic), name that
column here and set `error_type: "column"` for the labels it covers. The engine
carries it into the estimation problem as a FIXED per-row sigma; the observation
agent's noise formula is then not used for those observables.
NOTE on "below_detection" (OPTIONAL): DECLARE, never fix. When the source
states a detection floor (array background, assay LOD, sites undetectable at
t = 0) say per observable what the SOURCE did with values below it — `imputed`
(a floor or a fill value written into the table), `dropped` (rows absent), or
`left_as_is` (raw values kept). `threshold` is the floor on the measurement's own
scale, or null when the source gives no number. The engine records it, counts
the rows it touches, tells the observation-model agent, and the report states
that the comparison is conditional on the source's handling — no censored
likelihood is fitted. Declaring it is what keeps the limitation visible; a run
that swallows an imputed floor silently makes every candidate look cleaner than
the data justifies.
NOTE on "processing" (OPTIONAL): the ENGINE executes these, in order, on
the extracted table before any check and before any model exists; you compute
nothing. A CLOSED vocabulary of three operations, each a pure function of the
rows in the same cell (condition, time, replicate) or of ONE declared reference:
  normalize_by_group_sum {labels}
        divide each value in `labels` by their sum in the same cell (row
        normalisation); the divisor is kept per cell and shown in the report.
  subtract_reference {labels, reference: {observable_label | condition_label | time}}
        blank / background subtraction against a named reference row set: the
        same cell's other observable, a reference CONDITION (a blank lane, an
        unstimulated well), or a reference TIME (values relative to t = 0).
  scale_units {labels, factor, from_units, to_units}
        multiply by a declared constant; the label's units become `to_units`.
The holdout rule is engine-checked: a reference condition that is HELD OUT is
refused by name and comes back to you. NOT operations here, by rule: dropping
or clipping rows (a human decides exclusions), log or any transformation (the
observation model owns that), anything read from a fit. Declare processing only
when the note states the data WERE processed that way or a blank / reference
exists in the files — where the same assumption can be written model-side (a
per-timepoint or per-condition scale factor), the observation model will do
that instead.
""",
)

_role(
    "observation",
    ["observables"],
    """
{"observables": [{"observable_id": "obs_x", "maps_to_label": "...",
                   "formula": "<the model quantity AS THE DATA TABULATE IT: species/parameter expression, with the instrument link written in when the data scale is not affine in the model quantity (NOTE below) — no gain, no background>",
                   "transformation": "lin|log|log10",
                   "noise": {"distribution": "normal|laplace",
                             "formula": "<one of the four shapes below>",
                             "estimate_sigma": true,
                             "per": "observable|condition"},
                   "scaling": {"mode": "none|factor|factor_offset|offset",
                               "scale_parameter": "sc_obs_x or null", "offset_parameter": "off_obs_x or null",
                               "per": "observable|timepoint|condition",
                               "shared_across_observables": "false, or a group name",
                               "pin_first_to_one": false},
                   "rationale": "ONE argument, from the measurement process, for the COHERENT triple (mapping, transformation+noise, scaling) — not three restatements"}]}
NOTE on NOISE FROM THE DATA: when the data extraction declared
an `error_column` for a label (error_type "column"), that observable's sigma is
FIXED per measurement row from the data and your `noise` block is not rendered —
write {"distribution": "normal", "formula": "from_data", "estimate_sigma": false}
and say so in the rationale. Otherwise a fixed sigma must be a NUMBER; a bare
parameter id with estimate_sigma=false is refused (nothing declares it).
NOTE on INSTRUMENT LINKS: `transformation` is PEtab's
residual-scale switch and nothing more — lin|log|log10 applied to BOTH the
measurement and the simulation before the residual is formed. It cannot
express a data scale that is not affine in the model quantity. When the
tabulated values are arcsinh(x/c) (mass cytometry, flow cytometry), a
saturating binding or Hill readout, or any other nonlinear instrument
response, the link goes INTO `formula` and `transformation` stays `lin`, so a
fixed or estimated sigma sits on the scale the values are reported on:
  data = arcsinh(count/5), model pX in counts  ->  "log(pX/5 + sqrt(1 + pX*pX/25))"
  (`log` is the natural logarithm in PEtab and sympy; `ln` is accepted too)
The model quantity is then in the instrument's linear units and mass action,
conservation and fold-changes hold where they physically hold. Writing
`formula: pX` against arcsinh-scale data makes the model STATE the compressed
value — every fold-change and every conserved total is then imposed on a
logarithm. If you choose that deliberately, write it in the rationale as a
decision, never as a constraint of this contract. "No gain, no background" in
the formula means the SCALING block owns those two; it does not exclude the
link.

NOTE on SCALING SHAPES — what a scale factor is indexed BY:

  per: "observable"  one factor for the observable, every row (the default).
  per: "timepoint"   one factor per distinct measurement time — an instrument
                     gain that drifts between acquisitions. The engine
                     writes `sc_<stem>_t<time>` for each time and fills the
                     PEtab observableParameters column row by row.
  per: "condition"   one factor per condition — separate gels, plates, days.
  shared_across_observables: a GROUP NAME makes every observable declaring it
                     share ONE parameter set (`sc_<group>_t60` is the same
                     parameter in all k readouts of one acquisition). `false`
                     keeps the set per observable. Members of a group must
                     declare the same per, mode and pin.
  pin_first_to_one:  fix the first factor (earliest time / first condition) at
                     1, estimate: 0. IDENTIFIABILITY: with every factor free the
                     absolute scale must be pinned by EITHER a fixed model
                     total (an unestimated initial amount) OR this; the
                     rationale must name which, and the FIM screen shows the
                     flat direction if neither holds.

NOTE on SPELLING (AMICI compiles the formula): write log2(x) as log(x)/log(2)
and log10(x) as log(x)/log(10). Antimony, roadrunner and petablint accept
`log2`, AMICI does not, and the failure surfaces only at compile, after every
earlier check has passed, for every candidate at once. The engine rewrites these
two for you and refuses any other unknown function by name, but write it right.

NOTE on the NOISE FORMULA — four shapes, all supported:

  constant              "sigma_obs_x"
        one scale, independent of signal. The right default when replicate
        spread does not follow magnitude.
  proportional          "sigma_obs_x * <this observable's signal expression>"
        spread scales with signal. Degenerates to sigma=0 wherever the signal
        is zero, so it is wrong for any readout that reaches zero.
  additive+proportional "sigma_abs + sigma_rel * <this observable's signal expression>"
        a floor plus a signal-dependent term. THE shape for a readout that
        CONTAINS ZEROS — which `data_signals.support` tells you directly, as
        "a log transform is NOT legal: N zero(s)". Pure proportional puts
        sigma=0 at those points; pure constant misses the scale at high
        signal. Name both parameters; both are estimated.
  gain-scaled           "sc_obs_x * sigma_obs_x"
        the error scales with the observable's SCALE FACTOR (the
        scale_parameter you declared), not with the signal: a per-acquisition
        gain multiplies signal and noise alike, so a per-timepoint or
        per-condition scaling usually carries its factor into sigma. The
        engine renders `sc_obs_x` as the observable placeholder, so each
        row's sigma uses that row's own gain.

In the two signal-dependent shapes, the signal expression is this observable's
own formula, with or without its gain `sc_obs_x`; a sigma on any other state of
the model is refused and re-asked. Assignment-rule symbols are fine; the engine
expands them.

Each non-model symbol becomes its own PEtab noiseParameter placeholder, in the
order it appears in your formula. Up to three are rendered. This is offered,
not merely tolerated: when the error has a floor and a signal-dependent part,
write both rather than forcing one symbol to carry the two.

NOTE on "noise.per" — what the sigma is indexed BY:
  per: "observable"  one sigma set for the readout, every condition (default).
  per: "condition"   one sigma set PER CONDITION. The engine renders
                     `sigma_<obs>_<cond>` for every condition the observable is
                     measured in, fills the PEtab noiseParameters column row by
                     row, and counts every extra sigma in k. A held-out
                     condition's sigma is never fitted (fixed, out of k).
Use `condition` when the replicate spread differs between ARMS of the design
in a way no signal-dependent shape explains — a control arm at 0.1–0.3 log2
against a stimulated arm at 0.5–1.3 log2 — and cite the data_signals evidence
that shows it. It is NOT a scale factor: a per-condition sigma reweights the
residuals of that arm; it never moves the prediction. Do not reach for a
gain-scaled shape with a per-condition factor to get this effect: on log-scale
data that factor is an additive offset degenerate with the basal rates.

NOTE on "data_signals.processing_applied" when present: the table you
map onto was PROCESSED by the engine as data extraction declared (row
normalisation, a subtracted blank, a unit factor) — the facts are listed. Do
not add a second scale or offset on top of a step that already did it.

NOTE on "supplied_literature" when present: typed claims about papers the
person who staged this problem already has — `id` (lit_1 …), `source`, `title`,
`year`, `locator`, `supports`, `quote`, `origin: human`. Construction received the
same items. What they say about the MEASUREMENT is yours: the assay and what it
detects, units and whether they are absolute, a detection floor, replicate
structure, the scale on which the error is additive. Cite the id in the rationale
where an item decided something; never attribute to an item a claim its
`supports`/`quote` does not make.

NOTE on "data_signals" when present: the replicates' own read on the
error model, measured with no model involved — the slope of log(replicate
spread) on log(signal), which is 0 for constant error and 1 for proportional.
Use it as EVIDENCE for the noise block you are authoring, and weigh it against
the measurement process: an `inconclusive` verdict means these replicates
cannot separate the two, so argue from the assay rather than treating the
number as an answer, and say which you did in the rationale. It says nothing
about the MODEL — it is about the observation function.

NOTE: you author the whole observation function y = sc * g(x) + off + eps for
every measured quantity. The three parts are one decision: a log transformation
IS a claim that the error is multiplicative; a free scale factor on absolutely
calibrated data creates an exact flat direction with the model's own totals. The
rationale must argue that coherence; the engine splits your reply into the
estimation problem mechanically and checks the seams it can check.

NOTE on "model_space" (OPTIONAL): when there is more than one DEFENSIBLE
observation function for this data — not a better and a worse, two a careful
person could argue for — declare the alternative as an AXIS instead of choosing
silently. Shape:

  "model_space": [{"id": "per_timepoint_scaling", "priority": 1,
                   "question": "<the question the axis answers, in one line>",
                   "on_assembly_patch": {"change_scaling": {"observable_ids": ["obs_x", "obs_y"],
                                                            "per": "timepoint",
                                                            "shared_across_observables": "acq"}}}]

`on_assembly_patch` is a dict with EXACTLY ONE kind as its key — the kinds are
listed under "model_space patch kinds" in the construction contract:
change_observable_formula, change_noise_model, add_offset, remove_scaling,
change_scaling {observable_id | observable_ids, per, shared_across_observables?,
pin_first_to_one?}, change_condition, and change_transformation
{observable_id, new} — declared but REFUSED until a criterion can compare fits
on different residual scales, so do not propose it. split_parameter {parameter_id, by} is the
expansion agent's: the engine resolves it against the data at the expansion
gate, so do not propose it here either. A patch in any other shape is dropped by name and
comes back to you.

The engine fits both and lets the criterion and the human decide. Declare an
axis only when you would otherwise be making the choice on taste: a scaling
convention the data cannot settle, a noise model the replicates leave open, an
offset that may or may not exist. Choose, and say why in the rationale, when
the measurement process actually decides it — an axis per preference would
multiply the fitting for nothing.
"""
    + _known_facts_note("observation"),
)

_role(
    "condition",
    ["conditions"],
    """
{"conditions": [{"condition_id": "cond_x", "maps_to_label": "...", "overrides": {"<model_param_or_species>": 0.0},
                  "preequilibration": false | {"<model_param_or_species>": 0.0}, "rationale": "..."}]}

NOTE on "preequilibration": your decision, per measured condition, from the
protocol in the experiment description, from `basal_state` (the construction
agent's view of whether the model's initial values are the unstimulated steady
state), and from your own judgment. `false` = the condition is simulated from
the model's initial values. To pre-equilibrate, give the pre-equilibration
condition IN FULL as a dict of overrides, applied on top of a copy of this
condition's own overrides: the measured condition with the stimulus removed,
e.g. {"S": 0} or {"S1": 0, "S2": 0} (a control whose stimulus is
already off repeats that override at its value). The engine simulates that
condition to steady state and starts this one from it; a per-group parameter
id in `overrides` stays the same id, so the steady state is that group's. Keys
are model parameter or species ids, checked like overrides. A bare `true` names
no condition and is refused. A species this condition sets in `overrides` is
re-set at t=0 after pre-equilibration; every other species starts from the
steady state. Say in the rationale which protocol step the pre-equilibration
stands for.

NOTE on PARAMETER-VALUED overrides: an override value may be a
NUMBER (the condition fixes that quantity) or a PARAMETER ID (the condition gets
its OWN estimated copy of that model parameter). Use ids for a biological factor
whose levels are different cells or samples measured under identical staining —
e.g. `population` — for exactly the parameters the intent, the lab note or the
construction build report declare as varying with that factor (abundances,
basal fractions, feedback capacity), and NEVER for parameters declared shared
(catalytic rate constants, observation scale). Name the copy `<param>_<level>`
(`X_tot_groupA`); the engine creates the parameter rows, inheriting bounds
and scale from `<param>`, and removes `<param>` itself from the parameter table.
A factor that is an intervention (dose, ligand present) is a number.
WHICH parameters to split: exactly those whose construction entry carries
`"varies_by": ["<factor>"]`. If construction declared none, fall back to what
the intent and the lab note say varies between the groups — and split nothing
they declare shared (catalytic rate constants, measurement scale). Splitting a
shared catalytic constant next to a per-group abundance makes the two
unidentifiable and answers the "same chemistry?" question by construction.

NOTE on "model_space" (OPTIONAL): an encoding choice the data cannot settle
— whether a condition is a fixed override or an estimated quantity, whether two
labels are really one condition — may be declared as an axis rather than
decided silently, in the same shape the observation agent uses. Only when both
readings are defensible; otherwise choose and give the reason.
"""
    + _known_facts_note("condition"),
)

_role(
    "research",
    ["evidence_items", "queries_run", "notes"],
    """
{"evidence_items": [{"source": "DOI/PMID/URL", "title": "...", "year": 2020,
                      "locator": "figure/table/section", "supports": "what it actually says, faithfully",
                      "quote": "short verbatim quote if available", "url": "..."}],
 "queries_run": ["the searches you actually ran"],
 "notes": "coverage gaps, conflicts between sources, what you could NOT find"}
""",
)

_role(
    # what is known about the system before the intent is frozen (mode
    # `survey`), and inside a run what a model under construction lacks (mode
    # `targeted`). Online or offline by the CALL's grant (`granted_tools`), so
    # one role serves both; it CLASSIFIES each source and the engine grades
    # every reaction and fact (octomod/workflow_modules/knowledge/engine.py) — the agent grades nothing.
    "knowledge",
    ["reactions", "facts", "queries_run", "notes"],
    """
{"system": {"summary": "what is known about this system for this question, in a few sentences",
            "scope": "the organisms, cell types, compartments and conditions that knowledge comes from",
            "unknowns": ["what is known to be unknown or disputed"]},
 "species": [{"id": "Xp", "name": "the modified form of X", "represents": "the required entity this id stands for, copied verbatim, or empty",
              "identifiers": {"uniprot": "uniprot:P12345", "chebi": "chebi:15422", "pubchem": "pubchem:5957",
                              "hgnc": "hgnc:1234", "go_compartment": "go:0005829"}}],
 "reactions": [{"equation": "X -> Xp", "required": "req_1 or null", "essential": true, "modifiers": ["Z"],
                "type": "phosphorylation|dephosphorylation|binding|dissociation|conversion|synthesis|degradation|transport|other",
                "description": "what this reaction is, in one line",
                "identifiers": {"reactome": "reactome:R-HSA-123456", "kegg": "kegg:R00001", "rhea": "rhea:12345"},
                "answers": "targeted mode only: the id of the question this entry answers",
                "evidence": [{"source": "DOI/PMID/URL, a database id (reactome:R-HSA-123456), or the id of a supplied_literature item (lit_1)",
                              "title": "...", "year": 2020, "locator": "figure/table/section",
                              "supports": "what the source says about THIS reaction or fact, faithfully", "quote": "short verbatim quote",
                              "url": "...", "evidence_kind": "direct_experimental|mechanistic_model|curated_database|review|indirect",
                              "context_match": "same_system|related_system|different_system",
                              "context_note": "the organism, cell type and condition of the source, against the intent's system",
                              "stance": "supports|contradicts"}]}],
 "facts": [{"kind": "abundance|expression|rate|affinity|timescale|stoichiometry|response|assay|unknown",
            "statement": "the fact, in one sentence", "value": 0.0, "unit": "...",
            "applies_to": ["the species, reaction, population, compartment or assay it is about"],
            "for": ["construction", "observation", "condition", "expansion"],
            "answers": "targeted mode only: the id of the question this entry answers",
            "evidence": ["evidence items, the same shape as a reaction's"]}],
 "queries_run": ["the searches you actually ran"],
 "notes": "coverage gaps, conflicts between sources, what you could NOT find"}
NOTE on "mode" (in your inputs): `survey` = no model exists yet; say what is
known about this system for this question — `system`, `species`, `reactions`,
`facts`. `targeted` = a model is being built and lacks something: answer the
`questions` in your inputs (each with an `id`) and nothing else, with
`reactions` and `facts` only (`system` and `species` are not asked), each entry
naming the question it answers in `answers`. `model_summary` is the model as
it stands and `essential_ids` the reactions it already carries; do not return
those again.
NOTE on "equation": species are IDENTIFIERS (letters, digits and _, not starting
with a digit), because the model will use them verbatim — use the intent's own
entity names where they are identifiers. `A + B -> C`; `2 A -> A2`; `-> A`
(synthesis); `A ->` (degradation). Here `->` is ONE direction, the conversion the
source supports; a step the source shows running both ways is `A <-> B` (or two
entries, when the sources for each direction differ). A catalyst or regulator
that is not consumed goes in `modifiers`, not in the equation.
NOTE on "required" and "essential": every entry of `required_reactions` gets an
entry of its own, carrying its `id` in `required` and its equation as given,
with the literature you found for it — or `evidence: []` when you found none,
said in `notes`. The person requires it; the engine keeps it whatever you find.
`essential: true` marks a reaction a base model of this system cannot answer
the question without; `false` one that is described for the system but that
the base does not need. When the intent's `inference_target` is
`mechanism_discrimination`, the mechanisms the question asks to discriminate
are never `essential`: return each as `essential: false`, its `description`
naming the hypothesis it serves — the base is what every hypothesis shares.
Return EVERYTHING you find, essential or not: the variants and later rounds
draw on the rest.
NOTE on "supplied_literature" when present: papers the person who staged this
problem already has, each with an `id` (`lit_1`) and what it says. Where one
describes a reaction or a fact, cite it with its `id` as the item's `source`, your
own reading of what it says about THIS entry, and your own classification: it
is classified like any other source.
NOTE on classifying a source: you CLASSIFY, the ENGINE grades. Never write a
grade, a band, a score or a confidence: the engine decides each entry's grade
from your classifications, from its own check that the cited identifier exists,
from the document's own metadata (a paper PubMed or Crossref types "Review" is
a `review`, whatever you call it) and from whether the quote is in the
document. Classify what the source IS, not how convincing you find it:
`evidence_kind`: `direct_experimental` = an experiment that demonstrates this
conversion or measures this quantity; `mechanistic_model` = a published
mechanistic model that contains it; `curated_database` = a curated database
entry; `review` = a review or textbook statement; `indirect` = correlational,
or inferred from something else. `context_match`: `same_system` = the intent's
organism and cell type or context; `related_system` = the same pathway in a
related cell type or organism; `different_system` = anything further away.
`stance`: `supports` or `contradicts` the entry — a source that contradicts it
is returned, with that stance, never left out. An inflated classification is
an audit finding: the document is cached for audit.
NOTE on "identifiers": give an identifier where you know it and leave the key
out where you do not — a wrong identifier is worse than none. Each is a
`namespace:id` string of the declared shape (uniprot:P12345, chebi:15422,
pubchem:5957, hgnc:1234, go:0005829; reactome:R-HSA-123456, kegg:R00001,
rhea:12345); a malformed one is dropped and noted.
NOTE on "facts": the assumptions a model of this system needs and would
otherwise invent. `abundance` = copy numbers or concentrations per cell type or
compartment; `expression` = which population or compartment expresses which
receptor, enzyme or transporter; `rate` = a rate constant or half-life;
`affinity` = a dissociation or Michaelis constant; `timescale` = how fast a
response rises or decays; `stoichiometry` = a stoichiometry or fixed ratio;
`response` = a known response of the system to a perturbation the intent names,
crosstalk included; `assay` = what the measurement measures, its detection
floor and its error structure; `unknown` = what is known to be unknown or
disputed. `value` and `unit` where it is quantitative. `for` names the roles
that use it: `construction` (species, reactions, parameters, initial values),
`observation` (what a readout measures, its floor and its noise),
`condition` (how a perturbation enters the model), `expansion`
(mechanisms to test after a first fit); the engine routes each fact only to
those. A fact with no source is `evidence: []`, with the reason in `notes`. A
fact that contradicts the lab note is still returned: the person decides.
NOTE on "species": one entry per species id your equations use; for each entry of
the intent's `required_entities`, the species that stands for it names the entity
verbatim in `represents`.
NOTE when your tools are none: the same reply is expected, from your own
knowledge. Say so in `notes`, cite a source only when you are sure of its
identifier, and leave `evidence: []` otherwise; the engine records the support
as not applicable.
""",
)

_role(
    # a second reading of the knowledge module's sources, advisory: each item
    # re-classified from the cached document's own text around its quote
    "knowledge_verification",
    ["classifications"],
    """
{"classifications": [{"id": "rx_1.e1",
                      "evidence_kind": "direct_experimental|mechanistic_model|curated_database|review|indirect",
                      "context_match": "same_system|related_system|different_system",
                      "stance": "supports|contradicts",
                      "note": "one line: what in the excerpt decides it, or why the excerpt cannot"}]}
NOTE: one entry per item in `items`, by its `id`. Classify from the document's
text in `excerpts` (keyed by item id), not from the item's own claims: the
vocabulary is the knowledge role's (`direct_experimental` = the excerpt shows an
experiment demonstrating this conversion or measuring this quantity, and so on).
An item with no excerpt is classified from what it states, and its note says
there was no excerpt. Where the excerpt does not bear the claim out, say so in
the note; the engine keeps the lower of the two readings.
""",
)

_role(
    "construction_verification",
    ["verdicts", "overall"],
    """
{"verdicts": [{"aspect": "...", "ok": true, "note": "..."}], "overall": "pass|concerns"}
""",
)

_role(
    "assembly_verification",
    ["verdicts", "overall"],
    """
{"verdicts": [{"aspect": "...", "ok": true, "note": "..."}], "overall": "pass|concerns"}
""",
)

_role(
    "interpretation",
    [
        "diagnosis",
        "misfit_hypotheses",
        "cannot_distinguish",
        "nonetheless_determined",
        "answers_intent",
        "recommendation",
    ],
    """
{"diagnosis": "...", "misfit_hypotheses": ["..."],
 "requested_diagnostics": [{"kind": "residual_curve", "args": {"candidate_id": "...", "observable_id": "...", "condition_id": "..."}}],
 "cannot_distinguish": ["<every entry of report_core.computed_cannot_distinguish, COPIED>", "<then your own>"],
 "nonetheless_determined": ["<every entry of report_core.computed_nonetheless_determined, COPIED>", "<then your own>"],
 "finite_but_poorly_determined": ["<OPTIONAL: your own entries beyond report_core.computed_finite_but_poorly_determined>"],
 "answers_intent": [{"criterion": "...", "verdict": "pass|partial|fail", "evidence": "..."}],
 "recommendation": "accept|revise|stop"}

NOTE on "requested_diagnostics": OPTIONAL. The residual payload carries the
point-by-point curve for the few series with the worst fit-versus-noise-floor
ratio and, for the rest, the ratio alone — enough to see a series exists and
how bad it is. Ask for what you need and nothing more: each request is one
further call. `diagnostics_instruction` in your context lists the kinds and
the budget. Omit the key when the summaries are enough, which is the usual
case.

RULE on the two epistemic lists (a deterministic gate checks this, and it
blocks): each must CONTAIN every entry of the matching `computed_*` list in
report_core, copied character for character. They are not only parameter ids —
an entry may be a parameter id, `mechanism:<candidate_id>`, an
`observable@condition` label, or a whole flat-combination formula
("flat combination (FIM): 1.00*log(k_a) -1.00*log(k_b)"). Copy the string; do
not reformat it, translate it, shorten it or merge two entries into one. Then
add your own interpretation as FURTHER entries — the computed lists are a
floor, never a ceiling.

NOTE on "finite_but_poorly_determined": OPTIONAL, and no gate checks it. The
engine puts every entry of `computed_finite_but_poorly_determined` into it
itself: parameters whose profile closes on both sides but spans more of its box
than counts as determined. Add an entry only for a further quantity you can
point at the same way; omit the key otherwise.
""",
)

_role(
    "revision_proposal",
    ["move", "motivated_by", "expected_effect"],
    """
{"move": {"type": "change_noise_model|add_offset|remove_scaling|change_observable_formula|fix_parameter|free_parameter|change_bounds|change_kinetic_law|add_reaction|remove_reaction|stop",
           "args": {}},
 "motivated_by": "...", "expected_effect": "..."}
""",
)


_role(
    "revision",
    ["axes", "diagnosis", "stop_instead"],
    """
{
  "diagnosis": "what the residual evidence says is missing, in mechanistic terms",
  "requested_diagnostics": [{"kind": "simulate_with|residuals_for|compare_conditions|fit_residual_form", "args": {"candidate_id": "..."}}],
  "requested_research": ["one sentence naming the mechanism or observation to look for in the literature on this system"],
  "axes": [{"id": "short_slug", "question": "the structural question this axis settles",
             "origin": "residual|biology",
             "default": "off",
             "priority": 1, "priority_reason": "one line: why this axis first (1 = most load-bearing)",
             "on_antimony_patch": {"replace_reaction": "R2", "with": "R2: Y -> Y_a; ...full replacement line..."},
             "adds_parameters": [{"id": "k_x", "nominal_value": 1.0, "unit": "...", "lb": 0.0, "ub": 0.0, "evidence_tier": "to_be_estimated", "source": "...", "estimate": true, "neutral_value": 0.0, "denotes": "strength of the term this axis adds (0 = off)"}],
             "rationale": "why this mechanism, and why HERE in the network",
             "discriminating_evidence": "which observable, in which condition, separates on from off"}],
  "beyond_this_data": [{"mechanism": "a mechanism you think acts in this system",
                        "why_not_separable": "why THIS data cannot tell it from the selected model",
                        "experiment": "the measurement or perturbation that would"}],
  "untested_axes_addressed": [{"id": "an id from untested_axes", "action": "fit|ruled_out", "why": "for ruled_out: the residual evidence that excludes it"}],
  "expand_from": {"candidate_id": "an id from selection_table", "why": "one line: why this is the better PLATFORM to enlarge"},
  "stop_instead": false
}
NOTE on the BIOLOGY you are given: `domain_packs` (the pitfalls and templates
construction was given), `supplied_literature` when the person staged papers,
and, when research is on, `retrieved_evidence` — what the research role found,
just before this call, about mechanisms described for this system that the
selected model lacks (`evidence_instruction` says how to use it). Propose new
biology, not only patches for the residuals: a regulator, a loop, a route the
system is known to have that the model leaves out is an axis when the data can
separate it from the selected model.
NOTE on "origin" (OPTIONAL, default "residual"): per axis, what proposed it —
"residual" when the misfit evidence pointed at it, "biology" when the packs or
the literature did (cite the item's id, res_1 or lit_1, in the rationale). The
card shows it beside each axis; it changes nothing about how the axis is fitted
or selected.
NOTE on "beyond_this_data" (OPTIONAL, may be empty): mechanisms you think act
in this system that THIS data cannot separate from the selected model — no
observable, condition or time point tells on from off — each with why, and the
experiment that would separate it. They are not axes and nothing is fitted for
them: the human sees them on the card, and the run page lists them as what the
next experiment could decide. Do not list a mechanism you also propose as an
axis.
NOTE on `expand_from` (OPTIONAL): the engine's default base for the enlarged
space is the criterion winner. A criterion measures fit-plus-parsimony NOW, not
expandability: a rival with a worse AIC whose residuals are cleanly localised
can be the better platform to build on. Name one only if you think so, and say
why in one line — it is shown to the human beside the default, and the HUMAN
decides. Do not use it to relitigate the verdict: the criterion's ranking of
the fitted models is arithmetic and is not yours to overturn.
NOTE: account for EVERY id in `untested_axes` in `untested_axes_addressed`. An
axis already declared in this run and never fitted is cheaper to settle than a
new law, and a free axis (no new parameter) cannot overfit — so it is fitted,
not priced out. This is ADVISORY and not part of the contract: an axis you
leave unaccounted for is shown to the human as unaccounted for, beside your
proposal, and the human decides whether that is acceptable. Nothing refuses
your reply over it and you are not asked again.

NOTE: you are expanding a model space that has already been fitted and selected.
The axes you return are added to the SELECTED model and the whole enlarged space
is refitted, so each axis must patch the selected model's own reaction ids
verbatim and declare every symbol it introduces (`time`, `exp` and the standard
functions need no declaration, but PREFER a transient written as an additional
state with an initial value and first-order decay — a removable mechanism the
fit can test — over an explicit function of time; use `time` only for a
genuinely external, declared forcing). Return `stop_instead: true`
with an empty `axes` list ONLY if you judge that no mechanism can explain the
residual evidence and say why in `diagnosis`.

NOTE on "requested_diagnostics": OPTIONAL. When the payload does not settle a
diagnosis, ask the ENGINE for one more computation instead of guessing: it runs
deterministically, is ledgered, and its results come back to you under
`diagnostics_requested`; then you are asked again. Return `axes: []` together
with requests when you are not ready to propose. Bounded (see the instruction
in your inputs); no request fits anything or reads outside the run.

NOTE on "requested_research": OPTIONAL. When whether a mechanism is described
for this system would settle your proposal and the evidence you were given does
not say, ask for a literature search instead of guessing: 1-3 questions, each
ONE sentence naming the mechanism or observation to look for. Return `axes: []`
and your diagnosis so far with them, as with `requested_diagnostics` (both may
go in one reply). You stay offline: the engine hands your questions to the
research role, fences what it returns like every retrieved item (the case's
blocklist and publication horizon), freezes it in the round, adds the items to
`retrieved_evidence` with new ids (each names the question it answers in
`answers_question`), and asks you again with your questions under
`research_answered`. One search per expansion round: a second request is
refused and you are asked once more without it, and a run that allows no
search refuses the first the same way (`research_refused` says why).
`research_instruction` in your inputs says which applies. When
`prior_reactions` is in your inputs, the search is the knowledge role's
targeted search instead: name each conversion to look for as an equation in the
selected model's species ids (`A + B -> C`) and why; what it finds is graded by
the engine, and what reaches `support_floor` joins `prior_reactions` (origin
`search`) before you are asked again.
NOTE on "support_floor" when present: the floor of the round your axes are
fitted in (`words` says it in a sentence). An axis whose patch adds a
conversion graded below it, or one no entry of `prior_reactions` describes, is
REFUSED from the offer by name before the person sees it; an axis that changes
only a rate law or a switch adds no conversion and is never refused for it. An
axis that removes a reaction implementing one of the intent's required
reactions is refused whatever the floor: only the person removes a required
reaction, by editing the intent.

NOTE on OBSERVATION axes: an axis may instead carry `on_assembly_patch` (never
both): {"change_observable_formula": {"observable_id", "new_formula"}},
{"change_noise_model": {"observable_id", "new_distribution": "normal|laplace"}},
{"change_noise_model": {"observable_id", "new_formula": "sigma_obs_x * <this observable's signal expression>"}}
(proportional noise), {"change_noise_model": {"observable_id", "new_per": "condition"}}
(one sigma per condition — for a replicate spread that differs between arms of
the design; every extra sigma counts in k), {"add_offset": {"observable_id"}}, {"remove_scaling":
{"observable_id"}}, {"change_scaling": {"observable_id" | "observable_ids": [...],
"per": "observable|timepoint|condition", "shared_across_observables": false | "<group>",
"pin_first_to_one": false}} (a scale factor per time or per condition, optionally
shared by a group), {"change_condition": {"condition_id", "overrides":
{"<model parameter>": value}}} (which parameter a perturbation enters — never a
measured factor's value), {"split_parameter": {"parameter_id", "by": "<attribute>"}}
(one copy of an ESTIMATED model parameter per value of a condition attribute listed
in `condition_attributes` — e.g. one per population — in every condition; the engine
writes the copies and their rows from the parameter's own, so leave adds_parameters
empty; it adds (values - 1) parameters to k; one parameter family per axis; never a
parameter the assembly already sets per condition). Use the assembly's own
observable_id / condition_id (you are given the assembly). The differential diagnosis is one act: structure
vs observation model. Propose an observation axis ONLY when the observation-
layer evidence points there — |residual| growing with signal, a rejected
noise-model check, a sigma above the floor on ONE readout with no time shape —
and cite that evidence in `discriminating_evidence`. Residual SHAPE that
localises in time or condition is structure, not observation. One observation
axis per observable.

NOTE on "neutral_value" (the same rule as at construction): for each entry of
`adds_parameters`, give the value at which that parameter makes the axis's term
VANISH from the selected model — an added route has `neutral_value: 0`; a
feedback written as `k*A/(1 + beta*A)` has `neutral_value: 0` for beta. Where
every axis declares one, the enlarged space is ONE compiled model whose
candidates differ by parameter table alone and are exactly nested. THE RULE:
EVERY parameter an axis adds should carry `neutral_value`. A parameter with no
honest off-state of its own — a half-saturation `K`, a Hill exponent — may omit
it ONLY when another parameter of the SAME axis switches the whole term off
(`k` with `neutral_value: 0` makes `K` irrelevant); the engine then fixes `K` at
its nominal value in the off-state candidates and checks by simulation that the
term is gone. An axis in which NO parameter declares a neutral value costs its
own compile. Every declaration is CHECKED against the selected model; a wrong
one is recorded, never trusted — declare it where it is true and nowhere else.
"""
    + _known_facts_note("revision"),
)


# --------------------------------------------------------------- prompt build


def _skill_text(rs: RoleSpec) -> str:
    """Skills are scaffolding, not contract: a missing or unreadable skill file
    degrades the prompt, it does not stop the run."""
    try:
        return (SKILLS_DIR / rs.skill_file).read_text()
    except OSError:
        return f"You are the {rs.name} agent."


def tools_statement(role: str, online: bool | None = None) -> str:
    """What this call can and cannot do, stated in the prompt itself.

    The call runs with an allowlist (`--tools ""` for every offline call,
    `WebSearch,WebFetch` for an online one), so nothing a reply tries to
    execute can execute; a model not told this writes shell commands into its
    reply. The statement is the same for every call of a role under one grant
    (`granted_tools`), so `prompt_sha` still identifies the ask."""
    return _statement(granted_tools(role, online))


def _statement(tools: tuple[str, ...]) -> str:
    if tools:
        return (
            f"TOOLS: {', '.join(tools)} — nothing else. No shell, no file system, "
            "no code execution. Everything else you may use is in this prompt."
        )
    return (
        "TOOLS: none. No shell, no file system, no web, no code execution, and "
        "no way to inspect data beyond what this prompt contains — the inputs "
        "below are everything this role is given, by design. A command, a tool "
        "call, or 'let me look at …' written into the reply cannot run and "
        "fails the contract. Reply with the JSON object only."
    )


def build_prompt(role: str, context: dict, spec, online: bool | None = None) -> str:
    """Skill text, then the inputs in insertion order, then the contract.

    Deterministic by construction: the same role, context and grant give the
    same prompt, which is what makes the ledger's prompt_sha identify the ask.
    `spec` is part of the fixed signature (modules pass it everywhere) and is
    not read here — no prompt content may depend on run-tunable knobs.
    `online` is the call's grant (`granted_tools`), stated in the prompt.
    """
    rs = ROLES[role]
    parts = [
        _skill_text(rs),
        "\n\n# Your tools\n" + tools_statement(role, online),
    ]
    example = SKILLS_DIR / "examples" / rs.skill_file
    if example.exists():  # human-curated only, by house rule (examples/README)
        parts.append("\n\n# Worked example (curated)\n" + example.read_text())
    parts.append("\n\n# Inputs\n")
    for key, value in context.items():
        parts.append(f"\n## {key}\n")
        if isinstance(value, str):
            parts.append(value)
        else:
            parts.append(
                "```json\n" + json.dumps(value, indent=2, default=str) + "\n```"
            )
    parts.append("\n\n# Output contract\n" + rs.contract)
    parts.append(
        "\nRespond with ONLY a single JSON object matching the contract. "
        "No prose, no markdown fences."
    )
    return "".join(parts)


def build_prompt_within_budget(
    role: str, context: dict, spec, online: bool | None = None
) -> tuple[str, dict, list]:
    """`build_prompt`, degraded in the declared order until it fits the cap.

    Returns `(prompt, context, trims)`. The context comes back unchanged, and
    `trims` empty, whenever the prompt already fits — so a payload under the
    cap is byte-identical to one built by `build_prompt` alone.

    `call_agent` and `RunContext.call_cached` both build through here: they
    must render the same bytes for the same context, or a resumed run pays a
    second time for a reply it already has.
    """
    from octomod.agents.payload import fit_to_budget

    return fit_to_budget(
        context, spec, lambda c: build_prompt(role, c, spec, online=online)
    )


# ----------------------------------------------------------------- the call


def _missing_keys(parsed: dict, rs: RoleSpec) -> list[str]:
    """Every way the reply fails its contract: the required top-level keys,
    and the reply class in `result.agent_replies`, which also checks the TYPE
    of each key. Both backends quote the list back to the agent as the retry
    instruction."""
    from octomod.result.agent_replies import contract_failures

    missing = [k for k in rs.required_keys if k not in parsed]
    typed = [
        f
        for f in contract_failures(rs.name, parsed)
        if not f.startswith("missing required top-level key")
    ]
    return missing + typed


def _fill_from_stub(
    rs: RoleSpec,
    stubs_dir: Path | None,
    call,
    call_index: int = 0,
    family: str | None = None,
) -> tuple[dict, int, str, dict]:
    """Canned reply for a token-free run, held to exactly the contract a live
    reply is held to — a stub that drifts from the contract must fail loudly,
    or the free pipeline stops testing the real one. `call_index` selects the
    reply from a numbered sequence when the testcase ships one (see
    stub_backend); `family` names the replies a named call reads in place of
    its role's (`stub_backend.stub_family`)."""
    if stubs_dir is None:
        raise AgentCallError(f"backend 'stub' needs stubs_dir (role {rs.name})")
    served = family or rs.name
    path = stub_path(stubs_dir, served, call_index)
    parsed = load_stub(stubs_dir, served, call_index)
    (call / "replies/1/text").put_text(path.read_text())
    missing = _missing_keys(parsed, rs)
    if missing:
        raise AgentCallError(f"stub {path} does not fit its contract: {missing}")
    return parsed, 1, "stub", {}


ONLINE_ROLES = {
    "research": ("WebSearch", "WebFetch"),
    # the knowledge module's grant in online mode, exactly research's
    "knowledge": ("WebSearch", "WebFetch"),
}
# Roles whose grant each CALL chooses: online only when the call asks for it
# (`online=True`), so a caller that says nothing places an offline call.
PER_CALL_GRANT = frozenset({"knowledge"})


def granted_tools(role: str, online: bool | None = None) -> tuple[str, ...]:
    """The tools one call of `role` runs with.

    `online=None` is the role's default: its `ONLINE_ROLES` grant, or none
    for a role in `PER_CALL_GRANT`. `online=False` narrows any role to no
    tools; `online=True` asks for the role's grant and is refused for a role
    that has none — a call can narrow a grant, never widen one."""
    tools = tuple(ONLINE_ROLES.get(role, ()))
    if online is None:
        return () if role in PER_CALL_GRANT else tools
    if online and not tools:
        raise AgentCallError(
            f"role {role!r} has no online grant; an online call of it is refused "
            f"(online roles: {sorted(ONLINE_ROLES)})"
        )
    return tools if online else ()


def resolved_model(meta: dict) -> tuple[str | None, dict]:
    """(the model id that did the work, per-model breakdown) from a call's meta.

    The CLI's `modelUsage` is keyed by model id and one headless call can list
    more than one (small auxiliary requests run on a cheaper model), so the
    first key is not the answer: the model that produced the reply is the one
    with the output tokens. The breakdown is returned so the ledger row carries
    the evidence rather than a label.
    """
    usage = meta.get("modelUsage") or {}
    breakdown: dict = {}
    for mid, u in usage.items() if isinstance(usage, dict) else []:
        if not isinstance(u, dict):
            continue

        def _num(*keys, _u=u):
            for k in keys:
                v = _u.get(k)
                if isinstance(v, (int, float)):
                    return v
            return 0

        breakdown[str(mid)] = {
            "output_tokens": _num("outputTokens", "output_tokens"),
            "input_tokens": _num("inputTokens", "input_tokens")
            + _num("cacheCreationInputTokens", "cache_creation_input_tokens")
            + _num("cacheReadInputTokens", "cache_read_input_tokens"),
            "cost_usd": _num("costUSD", "cost_usd"),
        }
    if breakdown:
        best = max(
            breakdown,
            key=lambda m: (breakdown[m]["output_tokens"], breakdown[m]["cost_usd"]),
        )
        return best, breakdown
    m = meta.get("model")
    return (str(m) if m else None), breakdown


def _fill_from_llm(
    rs: RoleSpec, prompt: str, spec, call
) -> tuple[dict, int, str, dict]:
    """Headless `claude -p`, re-asked only on contract failure.

    A reply that is prose, truncated or short of a required key is a failure of
    this call. We quote the error back a declared number of times and then give
    up; we never repair the JSON ourselves, because a repaired hole hides which
    part of the contract the model could not satisfy.
    """
    model = spec.model_for_role(rs.name)
    effort = spec.effort_for_role(rs.name)
    tools = rs.tools if rs.tools is not None else granted_tools(rs.name)
    # null/0 = no limit. `int(None)` would raise, and a crash while READING a
    # setting is a worse failure than the one the setting exists to prevent.
    _t = spec.get("agents.timeout_s")
    timeout_s = int(_t) if _t else 0
    max_attempts = int(spec.get("retry.agent_json", 2)) + 1
    text = prompt
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        if last_error:
            text += (
                f"\n\nYour previous reply failed: {last_error}. "
                f"{_statement(tools)} "
                "Reply with ONLY one JSON object matching the contract."
            )
        t_started = time.perf_counter()
        try:
            reply, meta = run_llm(
                text,
                model,
                timeout_s,
                allowed_tools=tools,
                effort=effort,
            )
        except AgentKilled as e:
            # a killed child is not a bad reply and is never retried; what
            # it had written is kept beside the attempt, like a timeout's
            elapsed = time.perf_counter() - t_started
            reply_node = call / f"replies/{attempt}"
            partial = getattr(e, "partial_stdout", "") or ""
            partial_err = getattr(e, "partial_stderr", "") or ""
            if partial:
                (reply_node / "partial").put_text(partial)
            if partial_err:
                (reply_node / "stderr").put_text(partial_err)
            (reply_node / "killed").put(
                {
                    "attempt": attempt,
                    "elapsed_s": round(elapsed, 1),
                    "model": model,
                    "prompt_bytes": len(text.encode()),
                    "reason": str(e),
                    "partial_stdout_bytes": len(partial.encode()),
                    "note": "the child was killed; the call is NOT retried",
                }
            )
            e.attempt, e.elapsed_s = attempt, round(elapsed, 1)
            raise
        except AgentCallError as e:
            # A malformed reply is worth retrying (the model can fix it when
            # told); a timeout on the same prompt most likely recurs at full
            # cost, so timeout retries are separate and default to none.
            elapsed = time.perf_counter() - t_started
            timed_out = "timed out" in str(e)
            if timed_out:
                # whatever the child had written before it was killed — this is
                # the only evidence of what a slow agent was DOING
                partial = getattr(e, "partial_stdout", "") or ""
                partial_err = getattr(e, "partial_stderr", "") or ""
                reply_node = call / f"replies/{attempt}"
                if partial:
                    (reply_node / "partial").put_text(partial)
                if partial_err:
                    (reply_node / "stderr").put_text(partial_err)
                (reply_node / "timeout").put(
                    {
                        "attempt": attempt,
                        "timeout_s": timeout_s or "none",
                        "elapsed_s": round(elapsed, 1),
                        "model": model,
                        "prompt_bytes": len(text.encode()),
                        "partial_stdout_bytes": len(partial.encode()),
                        "partial_stderr_bytes": len(partial_err.encode()),
                        "note": (
                            "partial output saved beside this entry when the "
                            "child had written any; empty means the CLI "
                            "produced nothing before being killed, which is "
                            "itself the finding. Raise agents.timeout_s, or "
                            "set it null for no limit."
                        ),
                    }
                )
                if attempt > int(spec.get("retry.agent_timeout", 0)):
                    raise AgentCallError(
                        f"agent {rs.name} (model {model}) timed out after "
                        f"{timeout_s}s on attempt {attempt}. Retrying a timeout "
                        f"repeats the same wait for the same prompt, so the run "
                        f"stops here rather than spending it. Raise "
                        f"agents.timeout_s, or retry.agent_timeout to allow "
                        f"retries. Prompt saved in the record at {call.key}"
                    ) from e
            last_error = f"call failed ({e})"
            if attempt < max_attempts:
                time.sleep(10)
            continue
        (call / f"replies/{attempt}/text").put_text(reply)
        try:
            parsed = extract_json(reply)
        except AgentCallError as e:
            last_error = str(e)
            continue
        missing = _missing_keys(parsed, rs)
        if not missing:
            return parsed, attempt, model, meta
        last_error = f"missing required top-level keys: {missing}"
    raise AgentCallError(
        f"agent {rs.name} (model {model}) gave no contract-shaped JSON in "
        f"{max_attempts} attempts; last error: {last_error}. "
        f"Replies saved in the record at {call.key}"
    )


def check_prompt_budget(
    role: str,
    prompt: str,
    spec,
    context: dict,
    call,
    ledger,
    module: str,
    round_idx: int,
) -> None:
    """Run the T0 byte cap on this prompt; raise GateFailure if it breaches
    and the gate is blocking.

    Placed on `call_agent` rather than on `build_prompt`, because the cap is
    about what gets SENT: `call_cached` serves a byte-identical ask from
    the record without reaching any context window or costing anything, and
    gating that path would only re-ledger a row the first ask already wrote.
    """
    from octomod.agents.payload import prompt_budget
    from octomod.gates import GateFailure

    res = prompt_budget(role, prompt, spec, context)
    (call / "prompt_budget").put(asdict(res))
    ledger.append(
        "gate",
        module=module,
        round_idx=round_idx,
        gate_id=res.gate_id,
        tier=res.tier,
        passed=res.passed,
        blocking=res.blocking,
        value=res.value,
        threshold=res.threshold,
        detail=res.detail,
        role=role,
    )
    print(res.summary())
    if not res.passed and res.blocking:
        raise GateFailure(res)


def _api_split(meta: dict) -> tuple[float | None, float | None]:
    """(api_s, tools_s) from the CLI's envelope: `duration_api_ms` is the time
    inside the model API; the rest of `duration_ms` is the CLI's own — its
    tools, mostly. None on the stub backend, which has neither."""
    total = meta.get("duration_ms")
    api = meta.get("duration_api_ms")
    if not isinstance(total, (int, float)):
        return None, None
    api_s = float(api) / 1000.0 if isinstance(api, (int, float)) else None
    tools_s = max(0.0, float(total) / 1000.0 - api_s) if api_s is not None else None
    return (
        round(api_s, 3) if api_s is not None else None,
        round(tools_s, 3) if tools_s is not None else None,
    )


def call_agent(
    role: str,
    context: dict,
    *,
    spec,
    backend: str,
    calls,
    ledger,
    module: str,
    round_idx: int = 0,
    stubs_dir: Path | None = None,
    name: str | None = None,
    online: bool | None = None,
) -> dict:
    """Fill one typed hole; return the validated JSON object.

    Whichever backend answered, the call leaves the same trace in the record
    at `calls/<role>` (`ctx.agent_calls`): the prompt, one reply per attempt,
    the accepted JSON, and one ledger row carrying the model and prompt hash —
    so a run can be audited without rerunning it.

    `name` is the record name of the call when a role is asked twice in one
    round for different purposes (`research_expansion`): the trace goes to
    `calls/<name>` and the ledger row's `io` names it; the contract and the
    row's `role` stay the role's, and so do the stubs unless the name is of
    a family that ships its own (`stub_backend.stub_family`). Default: the
    role.

    `online` is the call's grant (`granted_tools`): the knowledge role runs
    online only when its caller says so, and the prompt states the grant.
    """
    if role not in ROLES:
        raise AgentCallError(f"unknown agent role {role!r}; known: {sorted(ROLES)}")
    from dataclasses import replace as _replace

    tools = granted_tools(role, online)
    rs = _replace(ROLES[role], tools=tools)
    call = calls.child(name or role)
    prompt, context, trims = build_prompt_within_budget(
        role, context, spec, online=online
    )
    (call / "prompt").put_text(prompt)
    # One row per degrade step, read back by `render.decisions_md`: what the
    # agent was not shown is a decision the engine made for the human.
    for trim in trims:
        ledger.append(
            "payload_trimmed",
            module=module,
            round_idx=round_idx,
            role=role,
            step=trim["step"],
            what=trim["what"],
            bytes_before=trim["bytes_before"],
            bytes_after=trim["bytes_after"],
        )
        print(
            f"  payload trimmed [{trim['step']}] {trim['bytes_before']:,} -> "
            f"{trim['bytes_after']:,} bytes: {trim['what']}"
        )
    # The prompt is in the record BEFORE it is judged: a payload that breaches the
    # cap is the evidence, and a gate that discards what it refused leaves the
    # operator nothing to trim.
    check_prompt_budget(role, prompt, spec, context, call, ledger, module, round_idx)

    started = time.time()
    # the call is one `agent` span of the time account, with the CLI's
    # own split — `api_s` inside the model API (thinking), `tools_s` the rest
    # of the CLI's clock (its tools), and what remains of the wall is the
    # subprocess itself. A stub call is a span too, of milliseconds.
    from octomod.orchestration import timing as _timing

    # the span's module is the PIPELINE module that is open (model, …), not
    # the role: `module` here is the ledger row's, which names the role
    with _timing.span("agent", role, backend=backend) as _span:
        if backend == "stub":
            # the k-th call of this role in the RUN gets the k-th canned reply
            # of a sequence; counted from the ledger so a resumed run keeps
            # counting
            from octomod.agents import stub_backend as _sb

            family = _sb.stub_family(name, role)
            if family is not None and not (
                _sb.has_replies(stubs_dir, family) or role in _sb.NAMED_STUBS_ONLY
            ):
                family = None
            prior = sum(
                1
                for e in ledger.entries()
                if e.get("event") == "agent_call"
                and e.get("role") == role
                and (
                    family is None
                    or _sb.stub_family(_sb.call_name(e.get("io")), role) == family
                )
            )
            parsed, attempts, model, meta = _fill_from_stub(
                rs, stubs_dir, call, call_index=prior, family=family
            )
        elif backend == "llm":
            try:
                parsed, attempts, model, meta = _fill_from_llm(rs, prompt, spec, call)
            except AgentCallError as e:
                # an aborted call is a call: its prompt was sent and its tokens
                # were spent. The CLI reports no cost for a killed or timed-out
                # call, so the row says the cost is UNKNOWN rather than zero.
                ledger.append(
                    "agent_call_aborted",
                    module=module,
                    round_idx=round_idx,
                    role=role,
                    backend=backend,
                    model=spec.model_for_role(rs.name),
                    duration_s=round(time.time() - started, 2),
                    prompt_sha=sha256_text(prompt),
                    prompt_bytes=len(prompt.encode()),
                    attempts=getattr(e, "attempt", None),
                    killed=isinstance(e, AgentKilled),
                    reason=str(e)[:400],
                    cost_usd=None,
                    cost_unknown=True,
                )
                raise
        else:
            raise AgentCallError(
                f"unknown agent backend {backend!r} (expected 'llm' or 'stub')"
            )
        api_s, tools_s = _api_split(meta)
        _span.update(model=model, attempts=attempts, api_s=api_s, tools_s=tools_s)

    out = call / "reply"
    out.put(parsed)
    # `model` is the alias the call was made with ("opus"); `model_resolved`
    # is the id that produced the reply — the model with the output tokens in
    # the CLI's per-model breakdown, which is kept on the row.
    _resolved_id, _models_used = resolved_model(meta)
    ledger.append(
        "agent_call",
        module=module,
        round_idx=round_idx,
        role=role,
        backend=backend,
        model=model,
        model_resolved=_resolved_id,
        models_used=_models_used or None,
        duration_s=round(time.time() - started, 2),
        api_s=api_s,
        tools_s=tools_s,
        prompt_sha=sha256_text(prompt),
        prompt_bytes=len(prompt.encode()),
        attempts=attempts,
        io=out.key,
        cost_usd=meta.get("total_cost_usd"),
        usage=meta.get("usage"),
        # how the subprocess was isolated: could the call have carried the
        # repo's CLAUDE.md or a user-wide MCP server? None on the stub backend,
        # which launches no subprocess.
        call_cwd_policy=meta.get("call_cwd_policy"),
        mcp_policy=meta.get("mcp_policy"),
        # the declared effort the call ran at (None on the stub backend)
        effort=meta.get("effort"),
        # the grant of a role whose calls choose it, so the row says whether
        # this one could reach the web
        **({"online": bool(tools)} if role in PER_CALL_GRANT else {}),
    )
    return parsed
