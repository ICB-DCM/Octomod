# Checks

A check is deterministic code that tests what an agent proposed or what the engine built from it.
It returns a pass or a fail with the measured value, the declared threshold, and the reason
(`GateResult`), changes nothing, and calls no LLM; the two advisory audits `model_verification` and
`assembly_verification` record a verification agent's verdict in the same form. A failing blocking
check stops what follows; an advisory check is reported and stops nothing. Most results go into
the run record, in the `gates` group of the round or the model candidate, and into the ledger. In
the code a check is a gate.

This folder holds the framework, in `__init__.py` (which the Files table below leaves out), and
three groups of checks; their docstrings name the steps S1, S3 and S6, explained in the
[names table](../workflow_modules/README.md#names-of-the-steps):

- `build_gates.py`, `sim_gates.py`: the model builds, is valid SBML, every symbol resolves, and it
  simulates; for the base model and every model candidate (M1, M2).
- `petab_gates.py`: each candidate's PEtab problem, before you approve the compile (M4).
- `fit_gates.py`: whether the multi-start fit converged (M6).

The other checks are in the code that builds what they test (paths from `octomod/`):

- M1, M2: `model_glossary_complete`, `model_declared_constants`, `model_supermodel_neutrality`, and
  the audit `model_verification` in `workflow_modules/model/engine.py`; `model_connected` in
  `workflow_modules/model/connectivity.py`; `model_essential_reactions` and `model_fact_citations`
  in `workflow_modules/knowledge/reaction_evidence.py`.
- M3: every data check, in `workflow_modules/data/engine.py`.
- M4: the checks on the agents' replies before the tables are merged (`assembly_merge_*`,
  `assembly_observation_seam`) and the audit `assembly_verification`, in
  `workflow_modules/assembly/engine.py`.
- M7: every evaluation check, in `workflow_modules/evaluation/engine.py`.
- Outside the modules: the `entry_*` checks of a run entered at a later module, in
  `orchestration/round_status.py`, and the prompt size check, in `agents/payload.py`.

Each module's README lists its checks with their ids.

## Order and consequences

Each file here returns its checks as a list (`make_build_gates`, `make_sim_gates`,
`make_petab_gates`, `make_fit_gates`). `run_gate_set` runs the list in that order, cheap checks
before those that simulate, and by default stops at the first blocking failure;
`model_essential_reactions`, `model_connected` and `model_fact_citations` run as one group that
does not stop. What happens then depends on the module:

- M1, M2: the draft goes back to the agent that wrote it (`construction`, or `expansion` for the
  candidates) with the checks it failed and its earlier attempts, until the redraft budget
  (`retry.module_draft`) is spent; then you are asked at the failure point (`model_redraft_budget`,
  `model_expansion_redraft_budget`).
- M3, M4: `role_for` in
  [`../orchestration/interaction/battery_feedback.py`](../orchestration/interaction/battery_feedback.py)
  names the agent that wrote the failing value, from its table `ATTRIBUTION`, and the failure goes
  back to that agent until the redraft budget is spent. You are asked at the failure point
  (`data_redraft_budget`, `assembly_redraft_budget`) then, or at once when no agent of this round
  wrote the value (`None` in the table) or the problem was supplied. A failure that one model
  candidate causes (its own observation overlay, a shared assembly naming what it lacks, or a piece
  of the model no readout sees) drops that candidate; with one model, the last stops the run and
  names `--from-module model`. In `make_petab_gates` the checks that read one agent's reply run
  before `assembly_petablint`, whose failure is the engine's own.
- M6: a failing fit check asks you at `estimation_convergence`: accept with a reason, refit, compare
  optimisers, or stop. No agent is asked.
- M7: see [the evaluation module](../workflow_modules/evaluation/README.md).

## Reference

<details>
<summary>Tiers, and how to add a check</summary>

Every check has a tier: T0 schema; T1 mathematical; T2 statistical, against a threshold declared in
`workflows/default.yaml`; T2' (`T2prime` in the code) the prediction of held-out data; T3 the audit
of a verification agent, always advisory. T4 is an interaction point
(`../orchestration/interaction/humangate.py`), not a check.

To add a check:

1. Write a function that returns a `GateResult`, decorate it with
   `@gate("<module>_<what>", "<tier>")`, and put it in the list its file's `make_*_gates` returns,
   where its cost and the order above call for. A check that solves the model's equations takes
   `integrates=True` and goes into `INTEGRATION_GATES`; `tests/solver_settings_unit.py` fails when
   the two disagree.
2. Give it a plain label in `HUMAN_LABELS` in `__init__.py`; `tests/gate_console_unit.py` fails for
   a check id without one.
3. For an M3 or M4 check, add its id to `ATTRIBUTION` (the agent to ask, or `None` for a person) or
   to `ADVISORY` in `battery_feedback.py`; `tests/battery_feedback_unit.py` fails otherwise. A check
   that reads one PEtab table also goes into `TABLE_FOR_GATE` there, so that the agent is shown the
   rows the engine built from its reply.
4. List it with its id in the module's README.

</details>

## Files

| file | what it is |
|---|---|
| `build_gates.py` | S1 gate ladder, part 1: builds -> valid -> references resolve. |
| `fit_gates.py` | S6 post-fit gates: is the optimisation itself trustworthy? |
| `petab_gates.py` | S3 gate battery: the estimation problem is checked before it may cost money. |
| `sim_gates.py` | S1 gate ladder, part 2: simulates -> simulates sensibly across plausible parameter ranges. |
