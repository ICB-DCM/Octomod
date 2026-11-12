# M1, M2 · Model building and model expansion

M1 writes the base model: the species and reactions that every model candidate shares. M2 then
proposes mechanisms to add to it, and each proposal becomes one model candidate. Neither module sees
a measured value. The models are built from your intent, your project description and the knowledge
file.

## What happens

1. The `construction` agent writes the base model in Antimony, with its parameters and a note on
   every decision it took.
2. The module engine converts the model to SBML and checks it: it must build, every symbol must
   resolve, and it must simulate.
3. If your question is which mechanism explains the data (`mechanism_discrimination`), the
   `expansion` agent proposes 2 to 5 candidates, each written as a difference from the base. The
   module engine builds and checks every one. Other questions keep one model.
4. The `construction_verification` agent reads the result and comments on it. Its comments are
   advice and never stop a run.
5. You see the model, or the candidates with what each one changes, and decide whether to fit them.

A reply that fails a check goes back to its agent with the reason, up to 3 attempts. After that you
are asked.

## Agents

| agent | what it does here |
|---|---|
| `construction` | writes the base model from the intent, the project description and the knowledge file |
| `expansion` | proposes the model candidates as differences from the tested base model |
| `construction_verification` | audits the models: whether the cited sources exist and support the reactions; advisory |
| `knowledge` (targeted) | in strict mode, searches the literature for a reaction that a draft says it lacks |
| `research` | off by default; an open literature search before construction |

What each agent is shown is listed in [`docs/ROUTING.md`](../../../docs/ROUTING.md). What it must
return is in its file under [`skills/`](../../../skills/).

## Where it asks you

- **Build on this base model?** Only if you switched this question on. You can accept, ask for a
  redraft in your own words, or stop.
- **Fit these models?** You can accept, choose which further mechanisms to fit, ask for a redraft in
  your own words, or stop.
- **After 3 failed attempts.** You can grant more attempts, lower the evidence floor, or stop.

## What it writes

The base model and every candidate go into the run record under their round: Antimony, SBML,
parameters, glossary and the agents' notes. The file
`runs/<id>_reports/round_k/report/model_report.html` shows the models and where each reaction came
from.

## Reference

<details>
<summary>Exact inputs and outputs of the agents, the checks with their ids, and the answer forms</summary>

### Agents: what each receives and returns

| agent | receives | returns |
|---|---|---|
| `construction` | the intent, the project description, the domain packs, your papers as claims, the curves in words (shape and timescale, no values, no held-out condition); with the knowledge file, the essential reactions at the evidence floor with grade and origin, the floor, the knowledge summary and the facts for construction, and in advisory mode every other reaction as prior knowledge; in a later round of a one-model run, the revision directive and the previous model; on a redraft its previous reply with the failing checks, the engine's search findings or your words | `network`, `antimony`, `parameters` (nominal value, unit, bounds, source, estimated or fixed), `build_report` (one entry per decision, with your numbered questions), `consulted_sources`, `entity_glossary`; optional `model_space` (axes), `recommended_tier`, `basal_state`, `declared_constants`, and in strict mode `missing` |
| `knowledge` (targeted) | strict mode only, when a draft names what it lacks: the intent, each missing conversion and why, a summary of the draft, the reactions it already carries, your papers, the restrictions; web access when M0 ran online | reactions and facts that each answer one question, with classified sources; the module engine grades them and admits what reaches the floor |
| `research` | off unless `research.enabled` is set in `testcase.yaml`: the intent, the project description, the restrictions; web access | `evidence_items` (source, year, locator, what it supports, quote), `queries_run`, `notes`, handed to construction and expansion as claims |
| `expansion` | mechanism discrimination only: what construction was given of the problem and the evidence, the tested base (Antimony, parameters, glossary, construction's decisions), construction's axes as information for a later round; with the knowledge file, the base's essential reactions, every other reaction with its grade, the expansion floor (the base's floor lowered by 1 band), the knowledge summary and the facts for construction; on a repair its previous reply with the errors or your words | `candidates`, each `{id, label, rationale, set_parameters, on_antimony_patch, adds_parameters, entity_glossary}`; `build_report`; in strict mode `missing` |
| `construction_verification` | the intent, the project description, the network, the Antimony, the build report, in a candidate set each candidate's declared difference, and with the knowledge file the facts for construction and the parameters that cite one; not the data, not your papers | `verdicts` (aspect, ok, note) on citation honesty, support, rationale quality, tier honesty, structure sanity, fact application and the candidate set; `overall`; advisory |

### Checks, with their ids

A failed blocking check returns the draft to its agent with the check in words, 3 attempts in all;
a malformed reply returns with the error quoted. A supplied model gets the build and simulate checks.

- **Build and simulate, every model** (blocking): `model_antimony_builds`, `model_sbml_valid`,
  `model_refs_resolve` (Antimony gives valid SBML, every symbol resolves);
  `model_estimated_parameters_used`; `model_simulates_nominal`, `model_nonnegative_states` (no
  state below -1e-6), `model_simulates_across_box` (80 % of 16 samples in the bounds integrate).
- **Base or single model** (blocking): `model_glossary_complete`; with the knowledge file,
  `model_essential_reactions` (strict: exactly the essential set; advisory: every required
  reaction), `model_connected` (every piece of the species graph holds a required entity, every
  quantity set per condition reaches one), `model_fact_citations`; no candidates from construction.
- **Candidate set** (blocking): building each candidate from the base, it refuses by name a change
  to a parameter the base lacks, a redeclared parameter, an undeclared symbol, a patch that does
  not apply, identical candidates, and fewer than 2 or more than 5; then the build and simulate
  checks and the glossary over the set. A failing candidate sends the whole set back.
- **The floor on additions**: a conversion a candidate or axis adds below the expansion floor, or
  one the knowledge file lacks, is flagged in advisory mode; in strict mode the axis is refused,
  the candidate dropped after a search for what `missing` names, and a set left under 2 goes back.
- **Advisory, on the card**: `model_conservation_laws`, `model_no_dynamics_screen`,
  `model_required_entities`, `model_declared_constants` (constants quoted from the project
  description hold at nominal), `model_verification` (the audit), `model_supermodel_neutrality`,
  and citation resolution (a `direct` or `transferred` claim with no resolvable source is demoted).

### Interaction points, with the answer forms

- **Base model** (`model_base_scope`), before the expansions, if `testcase.yaml` sets
  `s1: {base_gate: true}`: "Build the candidate expansions on this base?" `y` calls the expansion
  agent, `redraft: <words>` returns the base to construction, `n` stops. On every card, an agent's
  numbered questions are answered by number in the note.
- **Scope, one model** (`model_scope`): "Is this the right model scope to spend compute on?"
  `tier: top<k>|all` or `axes: <id>, <id>` fits each chosen axis alone on the base (k+1 models),
  `lattice` every combination (2^k), at most 8; `axes: none` keeps one model, and a bare `y` is
  refused unless the axes were bought. `redraft: <words>` returns to construction; `n` stops.
- **Scope, candidates** (`model_scope`): "Discriminate between these N candidate mechanisms?" Each
  candidate reads "differs from the base in: ...". `y` fits the whole set, `redraft: <words>` goes
  to the expansion agent, `redraft base: <words>` to construction, `n` stops.
- **Failure point**, after 3 failed attempts: `n=<attempts>` grants more, `n` stops, and with the
  knowledge file `floor: <band|none>` sets the round's floor. In strict mode a base naming what it
  lacks first gets a targeted search, then a floor 1 band lower.

</details>

## Files

| file | what it is |
|---|---|
| `antimony_text.py` | Antimony source as text: the symbol-level reading needed before compiling. |
| `connectivity.py` | Whether the data sees every piece of a model, and whether what the conditions vary reaches it. |
| `declared_constants.py` | Quantities the lab note declares constant, measured in the model. |
| `engine.py` | Model construction. |
| `expansion.py` | Candidates as declared differences from one tested base. |
| `model_space.py` | Model space: the structural questions, written down and searched. |
| `simwrap.py` | Cheap SBML simulation via roadrunner (no compilation), plus observable formula evaluation. |
| `supermodel.py` | Supermodel encoding: candidates that differ only in the parameter table. |
| `tried_models.py` | What was already tried, within a run and across runs. |
