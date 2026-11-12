# M6 · Parameter estimation

M6 estimates the parameters of each model candidate by multistart optimisation with pyPESTO and
AMICI: many fits, each from a random starting point. It uses the starts and solver settings you
approved in M5, a fixed seed, and the Fides optimiser unless a comparison selected another. It
records every start and checks that the optimisation converged; a failed check comes to you instead
of ending the run. The fits go to M7, which compares the model candidates of the round.

## What happens

1. The module engine first looks for exactly this fit in the run record: the same problem, settings,
   optimiser, seed and code, with enough starts. If it is there, as for the base model in a later
   round, it is reused and nothing is recomputed.
2. Otherwise it runs the starts, in parallel when the probe's median start took 2 s or more, else one
   at a time.
3. It checks that at least 3 starts lie within 0.5 of the best objective value and the gradient at
   the optimum is at most 10. At most 30 % of the starts may fail to integrate.
4. Estimates that sit on a parameter bound are noted and carried into the report; they do not stop
   the run.
5. If a convergence check failed, you decide what happens to that model candidate's fit.

A failed check does not stop the run: it comes to you, for that model candidate. A seed missing from
the record is an engine fault and stops the run.

## Agents

No agent: this module is deterministic.

## Where it asks you

- **Accept this fit, refit, or stop?** Asked for each model candidate, only when a convergence check
  failed. The card shows the failed checks with their numbers and a suggested order of refits. You
  can accept the fit with a reason, which the report carries as a caveat. You can refit with more
  starts, a stricter solver or more optimiser iterations, at most 2 times; the earlier fit is kept.
  You can have the optimisers compared on the same starts, once per model candidate and round. If one
  is conclusively better, the fit is redone with it at once. Or you can stop; a resume asks again.
- At the budget card of M5 you can accept plateau and gradient failures in advance for the round. A
  failed integration check still asks.

## What it writes

Each model candidate's best objective value, every start, the starts near the best, the optimiser
and the seed go into the run record. A run-level index lists every fit, so a later round can reuse
it. Section 6 of the round report, `runs/<id>_reports/round_k/report/report.html`, shows the
waterfall of sorted objective values and the parameters against their bounds.

## Reference

<details>
<summary>Exact checks with their ids, and the answer forms</summary>

### Checks, with their ids

Before fitting, the module engine looks for exactly this fit in the run record (the same problem,
solver settings, optimiser, seed and engine code, with at least the approved number of starts). If
it is there, as for the base model in a later round, it is reused and nothing is recomputed. The
starts run in parallel when the probe's median start took 2 s or more, otherwise one at a time.

After the fit, in `octomod/gates/fit_gates.py`:

- `estimation_waterfall_plateau`: at least 3 starts within 0.5 of the best objective value.
  Blocking.
- `estimation_gradient_norm`: the projected gradient norm at the optimum is at most 10. Blocking.
- `estimation_integration_failures`: at most 30 % of the starts failed to integrate. Blocking.
- `estimation_parameters_at_bounds`: which estimates sit on a bound. Advisory, carried into the
  report.

A failed blocking check is not a redraft: it opens the convergence interaction point for that model
candidate. The engine also checks that the seed is in the record; a missing seed is an engine fault
and stops the run.

### Interaction points, with the answer forms

- Convergence (`estimation_convergence`), only when a blocking check failed, for each model
  candidate: "The fit for <model> crossed a convergence check. Accept it, refit, or stop?" The card
  shows the failed checks with their numbers, a suggested order of refits, and the refits used.
  - `accept <why>`: the fit stands. A reason is required; it is recorded with the failed numbers,
    and the report carries it as a caveat.
  - `refit <preset>` or `refit key=value`: fit again with `more_starts` (3 times the starts),
    `robust_solver` (relative tolerance 1e-10, more integration steps) or `optimizer` (more
    iterations). At most 2 refits per model candidate and round; the earlier fit is kept. The card
    puts `robust_solver` first when integrations failed.
  - `compare`: the optimisers named in the settings (`cmaes`, `fides`, `nlopt_lbfgs`,
    `scipy_lbfgsb`) run on the same starts, sized from 35 % of the estimation's cost, with at least
    3 starts each. If one is conclusively better, the fit is redone with it at once, using one of the
    2 refits; otherwise the card comes back with the table. The card suggests it first when the
    plateau or the integration check failed; it can be bought once per model candidate and round.
  - `n`: the run stops. The answer is not kept, so a resume asks again.
- `convergence: accept <why>` at the budget card of M5 answers this card in advance for the round,
  for plateau and gradient failures; a failed integration check still asks.

### What it writes, with the record keys

Per model candidate, under `rounds/round_k/candidates/<id>/` (`_single` for one model):
`estimation` (the best objective value, every start, the ensemble of starts within 1.92 of the
best, the parameters at or within 5 % of a bound, the gradient, the optimiser and the seed),
`starts` (one row per start), `multistart` (the full result, which M7 profiles from), `gates`,
`decisions/estimation_convergence`, `attempts/<n>` (fits a refit replaced), `estimation_settings`
(refits), `optimizer_comparison` and `optimizer_selection` after `compare`, and the module's marker.
The run-level `fit_index` lists every fit by its key, so a later round can reuse it. The waterfall
and the parameters against their bounds are in section 6 of the round report, `report.html`.

</details>

## Files

| file | what it is |
|---|---|
| `convergence_record.py` | What the human decided about convergence, read back from the ledger. |
| `engine.py` | Parameter estimation. |
| `estimation_settings.py` | The settings a candidate's problem is built with, recorded in the run record. |
| `optimizer_compare.py` | Optimiser comparison on the same start points, measured by the engine. |
| `problem.py` | PyPESTO/AMICI plumbing: problem construction with a compile cache, and scales. |
| `solver_settings.py` | Turn declared solver settings into calls on live AMICI solver/model objects. |
| `start_engine.py` | Where a multistart's starts run, and what each one cost. |
