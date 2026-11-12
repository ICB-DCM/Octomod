# Revision

Revision proposes the next round's model candidates from what the last round could not explain. It
runs when the verdict asks for another round, by default when misfit is open (several candidates) or
the `interpretation` agent advises revising (one model). With several candidates the `revision` agent
proposes and the central engine runs the step; with one model the `revision_proposal` agent proposes
one move. The module engine checks every proposal before anything is fitted, and you decide.

## What happens

1. The `revision` agent reads the fits, residuals and misfit evidence, never a measured value. It
   says what the candidates missed and proposes revisions, each a patch to the model or assembly.
2. It may ask for 1 literature search per round and twice for diagnostics. With the knowledge module,
   the search goes to the `knowledge` agent.
3. The module engine checks each revision on the selected model, with the build and simulation checks
   of M1. No revision may remove a required reaction or exceed 1 estimated parameter per data point.
4. With the knowledge module, additions are graded against the next round's evidence floor, the
   lowest grade they need. Strict mode holds back a revision below it; advisory mode flags it.
5. At most 8 models are offered per round, by priority. Revisions the last round left unsettled are
   carried in, and so are earlier ones never fitted, unless the agent ruled them out.
6. With one model, the `revision_proposal` agent picks one move from a fixed list. The module engine
   checks its names and refuses a configuration already tried; 3 failed attempts stop the run.

A failing revision is dropped by name, and the agent gets 1 repair. A revision that would change what
a condition means is put to you as a question instead.

## Agents

| agent | what it does here |
|---|---|
| `revision` | reads the fits and residuals, says what the model candidates missed, and proposes revisions; sees no measured value |
| `revision_proposal` | with one model: proposes one move from a fixed list, such as changing the noise model or adding a reaction |
| `research` | off by default; searches the literature on the misfit and on the `revision` agent's questions |

What each agent is shown is listed in [`docs/ROUTING.md`](../../../docs/ROUTING.md). What it must
return is in its file under [`skills/`](../../../skills/).

## Where it asks you

- **Run another round with these revisions?** The card shows the diagnosis and each revision with
  its grade. If you accept, they are fitted one at a time on the selected model, or in every
  combination if you ask. You can also build on another fitted model candidate, add a revision the
  card leaves out, or set the next round's floor. You can spend the round's search on your question,
  or send the proposal back with your words. If you decline, the run ends with the misfit
  unexplained; if the agent proposes nothing, there is no card.
- **Spend another round on a structural revision?** One model only, when the agent proposes to stop
  while misfit is open. You can go on or end the run.
- **Approve this revision?** One model only. You can apply the move or end the run.

## What it writes

With several candidates, the round keeps the diagnostics, proposals, searches, your answer and what
was bought, from which the next round starts. With one model it keeps the move, or why there is none.
`runs/<id>_reports/ANALYSIS.html` lists what the agent says lies beyond this data.

## Reference

<details>
<summary>Exact inputs and outputs of the agents, the checks with their ids, and the answer forms</summary>

### Agents: what each receives and returns

| agent | receives | returns |
|---|---|---|
| `revision` | the intent, the project description, the domain packs and the user's literature; the selected model, the selection table, every model fitted in the run, the expansions and revisions declared and never fitted, the misfit evidence, the residual diagnostics, the fit summary, the pressure of the fit on the parameter bounds, the drift of quantities the project description calls constant, the interpretation agent's hypotheses, the selected model's assembly and the condition attributes; with research on, what the `research` agent found; with the knowledge module, the knowledge file's reactions with their grades and the next round's floor. No measurement values | `diagnosis`; `axes`, the revisions, each with an `origin` (residual or biology), a `priority`, one patch (to the Antimony, or to the assembly, a `split_parameter` included), `adds_parameters` with nominal values, bounds and the value that switches the term off, and `discriminating_evidence`; `stop_instead`; optionally `beyond_this_data`, `untested_axes_addressed`, `expand_from`, `requested_diagnostics`, `requested_research` |
| `revision_proposal` | the intent, the project description, the evaluation report with the interpretation, the closed list of moves, the configurations already tried with the reasons and predictions given for them, and the rounds left; when present, the open misfit indicators, the structural questions you deferred at construction, and your request for a structural move instead of a stop. No measurement values | `move` (one of `change_noise_model`, `add_offset`, `remove_scaling`, `change_observable_formula`, `fix_parameter`, `free_parameter`, `change_bounds`, `change_kinetic_law`, `add_reaction`, `remove_reaction`, `stop`, with its arguments), `motivated_by`, `expected_effect` |
| `research` | the intent, the project description, the search horizon and the excluded sources; before the `revision` agent, the selected model's species and reactions and where it misfits, in sentences; at that agent's request, its 1 to 3 questions. Web access; no data | `evidence_items` (source, title, year, locator, what it says, a short quote, url), `queries_run`, `notes` |

The `research` agent runs only with research on for the case (off by default); with the knowledge
module, a search the `revision` agent asks for goes to the `knowledge` agent, graded and admitted at
the next round's floor. 1 requested search per round; diagnostics may be asked for twice.

### Checks, in full

- **Before the card, on the `revision` agent's proposal** (a failing revision is dropped by name).
  Each revision applies to the selected model: one patch, the reactions it replaces exist, every
  new symbol is declared, no id repeats, an assembly patch uses the assembly's own ids, at most 1
  observation revision per observable. None removes a reaction that implements a required reaction
  or takes the model past 1 estimated parameter per data point. The build and simulation checks of
  M1 (`octomod/gates/build_gates.py`, `sim_gates.py`) run on every model the revisions would build.
  After a drop the agent gets 1 repair, with the reasons and the selected model's reaction ids. A
  revision that would change what a condition means is refused and put to you as a question.
- **On the offer.** With the knowledge module, what a revision adds is graded against the next
  round's floor (this round's, lowered by the step); below it, a revision is flagged in advisory
  mode and held back in strict mode. At most 8 models per round, by priority. Carried in: revisions
  the indistinguishable set disagreed on, and those declared earlier and never fitted unless the
  agent ruled them out; one it did not account for is shown on the card, never refused.
- **On the `revision_proposal` agent's move** (3 attempts, then the run stops): it is in the list
  with its arguments, the ids it names exist, and it repeats no configuration already evaluated
  (a hash of model, assembly and parameters; a repeated reaction move stops the next round).

### Interaction points, with the answer forms

- Revision approval (`revision`): "Buy this expansion and run another selection round?" The card
  shows the diagnosis, the misfit evidence, the searches, each revision with what it adds and its
  grade, the dropped, held-back and carried-in revisions, the floor, a different base if the agent
  recommends one, and the number of models. If the agent proposes nothing, no card: the run ends.
  - `y`: the revisions are fitted one at a time on the selected model (k + 1 models), or every
    combination with `lattice` (2^k). `n`: the run ends, the misfit recorded as unexplained.
  - `base: <candidate_id>`: build on that fitted model candidate instead; `axes: +<id>`: also fit a
    declared revision the card does not carry, such as one the agent ruled out.
  - `redraft: <words>` (with `y`): back to the agent with your words; the card is asked again on
    the new proposal, says what moved, and nothing is bought.
  - `floor:`, `step:` (knowledge module): the next round's floor as yours; `search: <question>`
    spends the round's search on your question.
- One model: `revision_proposal_stop_vs_revise` if the agent proposes to stop with indicators open
  ("Spend another round on a structural revision?"), then `revision_proposal` ("Approve this
  revision?"); `y` goes on to a structural move or applies the move, `n` ends the run.

### What it writes, with the record keys

Several model candidates, under `rounds/round_k/`: `expansion_diagnostics` (requests, results,
searches, every proposal), `expansion_evidence`, `research_requests`, `knowledge_search`,
`expansion_offer` (your answer) and `expansion` (what was bought, the base, the seed, what the
ceiling or the floor left out, `beyond_this_data`, which `ANALYSIS.html` lists); the next round
starts from its `model/seed`, `space/axes` and `space/floor`. One model: `rounds/round_k/revision`
(the move, its motivation and expected effect, or why there is none), `decisions/`, and `history`.

### Where the code is

With several model candidates the `revision` agent proposes and
`octomod/orchestration/orchestrator.py` runs the step; with one model the `revision_proposal` agent
proposes a move, run by `engine.py`.

</details>

## Files

| file | what it is |
|---|---|
| `engine.py` | Revision proposal. |
