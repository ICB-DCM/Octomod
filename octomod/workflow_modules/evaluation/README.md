# M7 · Evaluation

M7 compares the fitted model candidates of a round and tests them on the held-out data, which the
fit never saw. It measures what the best model still misses against the noise of the replicates. The
`interpretation` agent reads this evaluation and writes the diagnosis and the answer to each success
criterion. You then give the verdict, which ends the run or sends it on to revision and another
round.

## What happens

1. With several model candidates, the module engine computes AIC and BIC on one measurement scale,
   checked against PEtab Select. Candidates within 2 points of the best cannot be told apart.
2. To be the best model, a candidate must pass the held-out test, a misfit within the replicates'
   noise; if all fail, the round is unmet. With one model, failing it matters only for a prediction
   question, where it turns an accept into a revision.
3. For the best model it tests the misfit against the replicates' noise; with several candidates, an
   open misfit makes another round the default. It also checks the assumed noise distribution and
   screens how well the parameters are determined.
4. It fits each residual series of the best and the base model with 4 simple forms. It lists what
   the data could not distinguish, what they determined, and what is finite but poorly determined.
5. The `interpretation` agent reads all of this and writes the diagnosis and the answers. Its lists
   must repeat every computed entry exactly, and every name it uses must exist.
6. You give the verdict. Profile likelihoods are computed only when you ask, or unasked when the
   question is about parameter values.

A disagreement with PEtab Select stops the run. An agent reply that breaks its rules goes back once
with the entries quoted; a second failure stops the run.

## Agents

| agent | what it does here |
|---|---|
| `interpretation` | reads the evaluation, writes the diagnosis and answers each success criterion; may ask twice for diagnostics; decides nothing |

What each agent is shown is listed in [`docs/ROUTING.md`](../../../docs/ROUTING.md). What it must
return is in its file under [`skills/`](../../../skills/).

## Where it asks you

- **Sign off this verdict?** Asked every round, since a verdict is a scientific claim. The card shows
  each candidate's score, weight and held-out result, the best model and why it wins, and the agent's
  recommendation. With several candidates the default is another round while misfit is open and
  rounds remain, else the end; with one model, the agent's recommendation. You can also choose
  another round or the end yourself, ask for profile likelihoods first, or stop without a verdict.
- **Compute the profiles now?** Asked when profiles are due without a request, as for a question
  about parameter values, and may take over 600 s. If you decline, a parameter-values run stops;
  otherwise the run goes on without them.

## What it writes

The round's evaluation, the interpretation, the residual forms and, with several candidates, the
selection go into the run record. Open the round report,
`runs/<id>_reports/round_k/report/report.html`, and at the end of the run
`runs/<id>_reports/ANALYSIS.html`.

## Reference

<details>
<summary>Exact inputs and outputs of the agents, the checks with their ids, and the answer forms</summary>

### Agents: what each receives and returns

| agent | receives | returns |
|---|---|---|
| `interpretation` | the intent; the project description; the module engine's evaluation (fit metrics, held-out results, misfit evidence, noise-model check, identifiability screen, profile summaries when computed, the three computed lists, and with several model candidates the criterion values, the weights and which measurements account for the best model's lead); the residual diagnostics with the residual forms; the noise statistics of the replicates; on a later call, the diagnostics it asked for. Never the user's literature, never a benchmark's truth | `diagnosis`, `misfit_hypotheses`, `cannot_distinguish`, `nonetheless_determined`, `answers_intent` (per success criterion: pass, partial or fail, with the evidence), `recommendation` (accept, revise or stop); optionally `finite_but_poorly_determined` and `requested_diagnostics` |

The agent may ask twice for diagnostics the module engine runs (a series point by point, a profile
path, the model at given values, residuals by a data column, two conditions, a residual form tested
against noise). It decides nothing: its recommendation is one line on the verdict card.

### Checks, with their ids

Before the agent is called, the module engine computes the comparison (with several model
candidates: AIC and BIC on one measurement scale, differences, Akaike weights, the indistinguishable
set within 2, decisive at a weight of 0.7) and, for the best model, the misfit evidence, the
noise-model check, the latent states, the declared constants, the Fisher information screen, the
three lists (what the data could not distinguish, what they determined, what is finite but poorly
determined) and, on request, profiles. Each residual series of the best and the base model is fitted
with 4 forms (constant, linear, exponential, rise and fall), chosen by AICc with a margin of 2.

- **Stop the run.** `evaluation_selection_crosscheck`: the criterion arithmetic agrees with PEtab
  Select. On the agent's reply: `evaluation_no_overclaim` and `evaluation_no_underclaim` (both
  lists contain every computed entry, character for character) and `evaluation_names_exist` (every
  identifier exists in the problem), after one retry with the entries quoted back; and
  `evaluation_answers_intent_complete` (the success criteria are answered).
- **Decide the best model.** `evaluation_t2prime_holdout`: the held-out misfit is within the
  replicates' noise (p ≥ 0.01), or a normalised RMSE of at most 0.3 without replicates. A model
  candidate that fails cannot be the best model; when all fail, the round is recorded as unmet.
  With one model it blocks only for the prediction target, where it turns an accept into a revision.
- **Reported, never stop.** The misfit flag opens on a χ² test against the replicate noise
  (p < 0.01) or a fitted σ above 1.3 times it, and makes another round the default; residual
  autocorrelation only corroborates. The noise-model check tests the residuals against the assumed
  distribution (p ≥ 0.01). With one model both are recorded (`evaluation_structural_misfit_open`,
  `evaluation_noise_model_check`), with `evaluation_structure_at_optimum` (it simulates, with no
  negative state, at the optimum). `evaluation_selection_comparable`: a shared measurement scale.

### Interaction points, with the answer forms

- Verdict (`evaluation_verdict`), every round: "Sign off this verdict? (it is a scientific claim)".
  The card shows each model candidate's criterion value, difference, weight and held-out result,
  the best model and why it wins, the indistinguishable set, parameters near a bound, how far each
  misfit indicator is from its threshold, and the agent's recommendation, flagged if it disagrees.
  - `y`: sign and take the default. With several model candidates, another round when the misfit
    flag is open and rounds remain, else the end; with one model, the agent's recommendation
    (accept or stop ends the run, revise goes to revision).
  - `expand: yes|no` (`revise: yes|no` with one model): another round or the end, either way.
  - `profiles`: profile likelihoods for the model being judged, read again by the agent, and the
    card asked again. `--profiles "<why>"` asks for them at launch.
  - `n`: the run stops without an accepted verdict; a resume asks again.
- Profiling (`evaluation_profiling_gate`), when profiles are due unasked (parameter-values target)
  and may cost more than 600 s: `n` stops the run for that target, else goes on without them.

### What it writes, with the record keys

Under `rounds/round_k/`: `evaluation_core` (written before the agent is called), `evaluation` (the
report with the interpretation), `residual_forms`, `interpretation_diagnostics`, `agent_calls/`,
`decisions/`, and with several model candidates `selection`, `selection_files` and `attribution`;
per model candidate, its held-out check in `gates` and the profiles. Open the round's
`runs/<id>_reports/round_k/report/report.html`, and at the end of the run `ANALYSIS.html`.

</details>

## Files

| file | what it is |
|---|---|
| `attribution.py` | Mechanism attribution: which measurements pay for the winner's ΔAIC. |
| `diagnostics.py` | Engine-run diagnostics a tool-less agent may request, executed and ledgered here. |
| `engine.py` | Evaluation and the honest report. |
| `fitted.py` | A fitted candidate read back from the run record. |
| `identifiability.py` | Identifiability screen: the Fisher information at the MLE, reported as a SPECTRUM, never a rank verdict (full rank proves nothing). |
| `latent_states.py` | Are the unmeasured states plausible at the fit? |
| `misfit_margins.py` | How close each structural-misfit indicator came to firing. |
| `profile_projection.py` | What profiling a model will cost, as a range, and what it did cost. |
| `residuals.py` | Residual diagnostics rich enough to reason from. |
| `selection.py` | Model selection through PEtab Select. |
| `structural_nulls.py` | Structurally flat directions: parameter combinations no output depends on. |
| `uncertainty.py` | Prediction uncertainty from the profile-based confidence region. |
