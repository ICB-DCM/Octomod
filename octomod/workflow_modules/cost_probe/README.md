# M5 · Compilation and probing

M5 compiles each model candidate with AMICI and checks how the compiled model integrates. It then
runs a probe of 5 optimisation starts to project what the full estimation will cost. You approve the
number of starts and the solver settings, and M6 fits the model candidate with them. No check in M5
stops the run: each one measures, and you see the result with a proposal where there is one.

## What happens

1. M5 runs for each model candidate after you approve the compile at the end of M4, just before that
   candidate's fit in M6. A candidate already fitted, such as the base model in a later round, is
   not probed.
2. The module engine compares the trajectory at the declared tolerances with one at 100-fold tighter
   tolerances. A relative difference above 0.001 makes the card offer the tighter setting.
3. It times the residuals with their sensitivities against the residuals alone; a ratio above 8 makes
   the card offer adjoint sensitivities. It also reports whether every steady state a condition
   starts from is reached.
4. It looks for structural flat directions: parameter combinations no output depends on, near the
   nominal values. They are an indicator only, since AIC and BIC still count every estimated
   parameter, and are measured again in M7.
5. The probe runs 5 full optimisation starts and records the time per start, the objective values
   and the failed starts with AMICI's messages.
6. You approve the budget once per round. A later candidate reuses that approval only if its probe
   objectives are finite and its median start time is within 5-fold of the approved one's.

With several model candidates, a compile or fit failure naming the observation model returns to the
`observation` agent, once per round, and M4 runs again. Any other failure drops that model candidate;
the run stops when none is left.

## Agents

No agent: this module is deterministic.

## Where it asks you

- **Run the full estimation with this many starts?** Asked on the first model candidate of the round
  that costs anything. The card shows the measured times, projections for 100 and 500 starts, the
  probe results, the solver findings and the agent cost so far. You can accept the proposed number,
  100 by default, choose another between 10 and 1000, or stop before anything is estimated. You can
  take a solver setting the probe proposed. You can also accept in advance, with a reason, a fit that
  misses the plateau or gradient check in M6.
- **Fit this later model candidate too?** Asked when its probe does not match the approved one. You
  can fit it with the round's number of starts, or drop it and let the round go on.

## What it writes

For each model candidate, the measured times, the projection, the solver findings and the probe
itself go into the run record. The probe is stored as measured, so answering the card does not run
it again. Section 6 of the round report, `runs/<id>_reports/round_k/report/report.html`, shows the
cost profile.

## Reference

<details>
<summary>Exact checks and answer forms</summary>

### Checks, in full

M5 runs after the compile interaction point at the end of M4, once per model candidate and just
before that candidate's M6. None of these checks stops the run: each one measures, and its result is
shown on the budget card, with a proposal where there is one.

- Tolerance agreement: the trajectory at the declared tolerances is compared with one at tolerances
  100 times tighter; a relative difference above 1e-3 makes the card offer `tighten`.
- Sensitivity cost: the residuals with their sensitivities are timed against the residuals alone; a
  ratio above 8 makes the card offer `adjoint`.
- Steady states: whether every pre-equilibration settles. Reported only.
- Structural flat directions: parameter combinations no output depends on, at 2 points near the
  nominal values. An indicator only (AIC and BIC still charge every estimated parameter), measured
  again at the fit in M7.
- The probe: 5 full optimisation starts, for the time per start, the objective values, and which
  starts failed, with AMICI's messages.
- Probe match: a later model candidate reuses the round's approval only if every probe objective is
  finite and its median start time is within a factor of 5 of the approved model candidate's;
  otherwise the budget is asked again for it.
- Compile failures: in a round with several model candidates, a compile or fit failure that names
  the observation model goes back to the observation agent once per round, and M4 and its compile
  card run again; any other failure drops that model candidate by name. The run stops when no model
  candidate is left.

A model candidate whose fit is already in the run record, such as the base model in a later round,
is not probed; the card names it and leaves it out of the projection.

### Interaction points, with the answer forms

- Budget (`cost_boundary_estimation`), on the first model candidate of the round that costs
  anything: "Run the full estimation with N starts (x K candidates)?" The card shows the compile
  time, the time of one objective evaluation and per condition, the probe's time per start, the
  optimiser and why, the parallel workers, the projections for 100 and 500 starts, the probe
  objective values and failed starts, the solver findings, the structural flat directions, and the
  agent cost so far.
  - `y`: fit with the proposed number of starts (100 by default). `n`: the run stops before
    anything is estimated.
  - `n=<starts>`: another number of starts, within 10 to 1000.
  - `tighten`, `adjoint`: use the proposed solver settings for the round. Each is offered only when
    the probe proposed it; with `adjoint` the probe is run again before the fit.
  - `convergence: accept <why>`: answers the convergence interaction point of M6 in advance for
    this round, for plateau and gradient failures. Failed integrations still ask.
- Budget again, for a later model candidate whose probe does not match: `y` fits it with the round's
  number of starts, `n` drops that model candidate and the round goes on.

### What it writes, with the record keys

Per model candidate, under `rounds/round_k/candidates/<id>/` (`_single` for one model): `cost` (the
measured times, the projection and the solver findings), `probe_record` (the probe as measured, so
that answering the card does not run it again), `structural_nulls`, `budget_declined` after an `n`
at a re-asked card, and the module's marker with the approved number of starts. Solver choices made
at the card go to `estimation_settings`, of the round or of the model candidate. The cost profile is
in section 6 of the round report, `runs/<id>_reports/round_k/report/report.html`.

### Where the code is

The module engine is `engine.py` in this folder, with the solver checks in `solver_probe.py`; the
compile itself is done by the problem builder in `octomod/workflow_modules/estimation/problem.py`,
which keeps compiled models by content hash.

</details>

## Files

| file | what it is |
|---|---|
| `compile_feedback.py` | A compile or fit failure that names the observation model goes back to its author, once per round. |
| `compile_gate.py` | The compile boundary: the one card before the first real compute. |
| `engine.py` | Cost profiling — measure before committing. |
| `solver_messages.py` | What AMICI said while the cost probe's starts ran, counted by kind. |
| `solver_probe.py` | What the compiled model costs and whether the integrator has converged. |
