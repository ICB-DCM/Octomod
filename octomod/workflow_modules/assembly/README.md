# M4 · PEtab assembly

M4 links each model to the data. Once per round, the `observation` and `condition` agents write how
the data relate to the first model; every model of the round shares this assembly. The module engine
merges it with each model into that model's own PEtab problem, the standard files a fit needs, and
checks it. A round built on an earlier one reuses its assembly, unless its model was sent back and
rewritten. A PEtab problem you supply skips the agents but not the checks.

## What happens

1. The `observation` agent writes, for each measured quantity, a formula on the model species, a
   transformation, a noise model and any scaling or offset. It sees a summary of the model and the
   noise in the data, never a measured value.
2. The `condition` agent writes what each data condition fixes in the model, and whether the system
   first reaches a steady state without the stimulus.
3. The module engine merges both with each model into a PEtab problem; held-out measurements (kept
   from fitting, for evaluation) get a table of their own. A data label that nothing maps stops the
   module, and a model candidate that cannot carry the shared assembly is dropped.
4. It checks each problem: formulas compile, names resolve, parameters are bounded, and a readout
   sees every part of the model. If none does, a candidate is dropped and a single model stops.
5. Advisory checks, which never stop the run, report more estimated parameters than data points and
   parameters the data do not move. They flag medians of simulation and data 100-fold apart without
   a scale factor.
6. The `assembly_verification` agent audits the tables as advice; then you are asked to compile.

A failed check goes back to the agent that wrote the value, up to 3 attempts; a failure no agent
wrote comes to you.

## Agents

| agent | what it does here |
|---|---|
| `observation` | writes each measured quantity's formula, transformation, noise model and scaling; sees no measured value |
| `condition` | writes what each data condition fixes in the model, and any steady state reached first |
| `assembly_verification` | audits the tables against the experiment, such as noise against the readout technique; sees no data; advisory |

What each agent is shown is listed in [`docs/ROUTING.md`](../../../docs/ROUTING.md). What it must
return is in its file under [`skills/`](../../../skills/).

## Where it asks you

- **Grant more attempts?** Asked when an agent has used its attempts, or no agent wrote the failing
  value. You can grant more, redo the assembly with your own words, or stop. You can also switch the
  failing part to a declared default, such as additive noise; it is recorded as your decision.
- **Compile the models with AMICI and probe their cost?** Asked once per round, after every model is
  assembled. The card shows each model's estimated parameters and fitting points, the agents'
  reasoning, the data flags and the audit. You can approve, and M5 compiles and probes every model.
  You can send the work back to the two agents with your words, or stop before any expensive step.

## What it writes

Each model's assembly and PEtab problem go into the run record, beside the round's shared assembly,
your compile answer and who decided what, and why. The PEtab problem can be used without the
workflow; section 5 of each round report, `runs/<id>_reports/round_k/report/report.html`, shows it.

## Reference

<details>
<summary>Exact inputs and outputs of the agents, the checks with their ids, and the answer forms</summary>

### Agents: what each receives and returns

| agent | receives | returns |
|---|---|---|
| `observation` | the intent, the project description, the domain packs, the entity glossary, a model summary (species and parameter ids, assignment rules, each reaction's kinetics, the magnitude each species reaches at the nominal parameters), the data labels (observable labels with units and error type, condition labels), the data signals (noise per observable from the replicates, zeros, negatives, range, whether a log is legal, the processing applied, declared detection floors), your papers as claims; no measurement value; on a redraft its previous reply with the failing check, your words, or a compile failure that names it | `observables`, per measured quantity: `observable_id`, `maps_to_label`, `formula` on model species, `transformation` (lin, log, log10), `noise` (normal or laplace, one of four shapes, per observable or condition), `scaling` (none, factor, factor with offset, offset; per observable, time point or condition; shared across a group or not), `rationale`; optional `model_space` for an alternative it cannot settle, recorded for a later round |
| `condition` | the intent, the project description, the condition labels, the same model summary and glossary, the experimental design summary, the observation draft, the basal state construction declared; no measurement value; on a redraft its previous reply with the failing check or your words | `conditions`, per data condition: `condition_id`, `maps_to_label`, `overrides` (a number the condition fixes, or a new parameter id for a per-group copy), `preequilibration` (false, or the condition with the stimulus removed), `rationale`; optional `model_space` |
| `assembly_verification` | the intent, the project description, the domain packs, the entity glossary, the observables, conditions and parameters tables as text, the data extraction agent's flags; no data, no model; for an observation axis only the changed entries | `verdicts` (aspect, ok, note) on at least the noise model against the readout technique, the conditions against the project description, scaling and offset against the units, the observable mapping against what the assay measures; `overall`; advisory |

### Checks, with their ids

A blocking failure goes back to the agent that wrote the value, with the check verbatim, its own
block and the merged rows, 3 attempts in all. A failure no agent wrote goes to you. A piece of the
model no readout sees is the model's: a candidate is dropped, a single model stops and names M1 to
re-enter. A candidate whose model cannot carry the shared assembly is dropped.

- **On the observation reply** (`assembly_observation_seam`, blocking): ids present and unique,
  `maps_to_label` a data label, a formula, a legal transformation and distribution, a noise
  formula that renders on the model's entities, a sigma that reaches the model only through its
  own observable, legal scaling.
- **At the merge** (blocking): `assembly_merge_observables` (each observable its own data label),
  `assembly_merge_noise` (a noise model per observable; a fixed sigma is a number or the data's
  error column), `assembly_merge_conditions` (each override a number or a new id, no estimated
  parameter also set by a condition, a well-formed pre-equilibration). A data label that no
  observable or condition maps stops the module.
- **On every model's problem** (blocking, in this order): `assembly_formulas_compile_safe`,
  `assembly_observables_resolve`, `assembly_sigma_through_observable`,
  `assembly_conditions_resolve`, `assembly_noise_declared`, `assembly_parameters_sane` (bounded,
  scaled, no orphan), `assembly_measurements_resolve`, `assembly_connected` (every piece of the
  model is seen by a readout, every varied quantity reaches one), `assembly_petablint`,
  `assembly_preequilibration` (each pre-equilibration reaches a steady state).
- **Advisory**: `assembly_dof` (at most 1 estimated parameter per data point),
  `assembly_magnitude_reconciliation` (simulated and measured medians within 2 decades unless a
  scale factor is present), `assembly_sensitivity_coverage` (parameters the data do not move, and
  the Fisher information spectrum), `assembly_verification` (the audit).

### Interaction points, with the answer forms

- **Failure point** (`assembly_redraft_budget`), when an agent has spent its attempts or no agent
  wrote the failing value: `n=<attempts>` grants more, `redraft: <words>` redoes the assembly with
  your words, `fallback: additive-noise|scaling|no-scaling` rewrites the block to a declared
  default on your signed answer, `n` stops.
- **Compile** (`assembly_cost_boundary`), asked by the central engine once per round after every
  model is assembled: "Approve AMICI compile + cost probe?" It shows each model's estimated
  parameters and training points, the pointer to every agent's reasoning, the data flags, the
  curves in words, the audit's findings and any re-ask, fallback or dropped model. `y` compiles
  and probes every model (M5), `redraft: <words>` returns to the observation and condition agents
  and asks again, `n` stops before any expensive step.

### What it writes, with the record keys

Per model, `candidates/<id>/assembly` and `candidates/<id>/petab` (observables, conditions,
parameters, measurements, holdout_measurements, problem_yaml; `<id>` is `_single` for one model).
Per round, `shared_assembly`, `decisions_md` (who decided what, and why), the compile answer in
`decisions`, `agent_calls`, `gates`. `./run.sh show --run-id <id> rounds/round_0/candidates/<id>/petab/<table>`
prints each table; the PEtab problem can be used without the workflow.

</details>

## Files

| file | what it is |
|---|---|
| `assembly_edit.py` | Assembly edits: the observation layer as a patchable artifact. |
| `engine.py` | Estimation problem assembly. |
| `hierarchical.py` | Which observation parameters pyPESTO's hierarchical estimation may solve analytically (scaling, offset), and which it must not. |
| `petab_io.py` | PEtab problems in memory — the libraries never read the run's record. |
