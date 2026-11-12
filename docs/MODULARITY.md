# Module contracts, entry, and re-entry

**Status: the entry/re-entry half is BUILT; the rest remains a design note,**
written when none of it existed. What now runs is
described in "Where we actually are" below and proved by the `entry` suite; the
sections after it are kept because they are the design that was implemented (and,
for profiling, a design still partly waiting). Read the table first — it is the
only part guaranteed to describe today.

**Payload routing lives next door.** This page is about which MODULES can be
entered and with what artifacts. Which *agent role* inside a module is shown
which payload — and which it must never see — is [ROUTING.md](ROUTING.md),
generated from `octomod/agents/routing.py` and enforced at `RunContext.call`.

## The goal

The framing: the orchestrator should be able to **call any part of the
workflow as a tool and start at that point with the inputs it needs**. A user
arrives with a PEtab problem and wants it estimated and profiled. Or with a
model and data. Or with estimation results they want re-fitted under a different
optimiser. Or having decided one reaction is wrong, wanting to change it and
continue from there rather than from the beginning.

That is one mechanism, used in two directions:

- **forward entry** — start at module *k* with artifacts supplied from outside;
- **re-entry** — go back to module *k* in a run that already went past it.

## Where we actually are

Honest, and tested rather than assumed — which cuts both ways: this section
said `supplied/petab` was broken and re-entry absent, and both have since been
built. Corrected against the suite that proves it.

| entry point | status |
|---|---|
| `supplied/model.ant` (+ parameters) | works |
| `supplied/network.json` | works |
| `supplied/measurements_long.tsv` | works |
| `supplied/petab/` | works — `entry` suite (`tests/petab_entry_smoke.py`) |
| `--from-module <module>` (forward entry and re-entry) | works — same suite |

The PEtab route is the one people would most want, and it now works: an adapter
derives the model slot (SBML, a best-effort Antimony reconstruction, the dynamic
parameter declaration) and the data slot (the long measurement table with
semantic condition keys, plus its report) from the supplied problem, applies the
staged holdout split, and the run enters at estimation. Construction and the
assembly agents are never called; every slot is still validated by the battery
that owns it, under the module name `entry_<slot>`, leaving the usual gate
verdict nodes under `ctx.gates` and ledger rows. The adapter is the work this document predicted: SBML path
normalisation, parameter-table conventions, measurement rows to the engine's
own vocabulary.

**Re-entry exists**: `run --from-module model|data|assembly|estimation|
evaluation` (aliases for the module names too) validates every upstream slot,
refuses with the NAMED missing or invalid slot before anything is run, marks the
upstream modules as passed with their producer recorded, and invalidates the
entry module and everything downstream so it runs afresh. It works on a fresh run
(forward entry from `supplied/`) and on an existing run id. Hand-deleting marker
files is no longer the only way back, and remains a sharp edge nobody needs.

The mechanism was `round_status.json` per round: a schema'd INDEX of the round's
artifacts — path, sha per file, producer, when and by which battery it was last
validated — written on every marker, with the content staying in the artifacts
themselves. **Retired 2026-09-22:** the marker now carries the
slot's shas itself, the slot state is computed from the hashed record keys +
markers (`round_status.slot_state`, `slot_parts`) into the run's record, and `require_marker` still
refuses a marker whose slot's required artifacts have gone. Since
2026-09-23 the artifacts, the markers and the slot state all live in the one
file `runs/<id>.h5` — `--from-module` and the supplied-PEtab adapter work on
record locations.

## What already exists and can be reused

Most of the machinery is here. What is missing is that it is expressed as
control flow rather than as data.

- **The DAG is real but implicit**: `s1 → s2 → s3 → cost → s6 → s7`, six edges,
  each written as a `ctx.require_marker(...)` call inside the module that needs it.
- **The validators exist**: 28 checks across four batteries — `build_gates`,
  `sim_gates`, `petab_gates`, `fit_gates` — each of which validates the output of
  one module. **These are exactly the entry checks.** `petab_gates` is a complete
  validator for a PEtab problem, which is precisely what a PEtab entry needs run
  against it.
- **The principle is already the design**: *agents are skipped, gates are not.*
  It is simply only wired for two of the four routes.

## The design: module contracts as data

Each module declares three things. All of this information exists today; none of
it is written down anywhere a program can read.

```
requires     markers that must be set, and artifact paths that must be present
produces     artifact paths written, and the gate battery that validates them
invalidates  which downstream markers die when this module is re-entered
```

Once that is data instead of code, both directions fall out of one mechanism.

### Forward entry at module k — built

Supply the artifacts module *k−1* `produces`. The engine runs **k−1's output
battery against them**. On pass it writes markers `0…k−1` stamped
`producer: user-supplied`. On fail the gate failures are the answer — they are
written to be actionable ("parameter L is condition-controlled AND marked for
estimation — pick one"), and the refusal happens before anything is run.

This is what makes `supplied/petab/` work: the problem enters as a validated
petab slot, the S3 battery checks it, and construction never fires.

### Re-entry at module k — built

The same mechanism, reversed: the entry module's markers and every marker
downstream of it are cleared, and the run continues from there. Changing the
optimiser is `--from-module estimation` plus a spec edit; re-reading a finished
run's evaluation is `--from-module evaluation`. Both are ordinary commands rather
than hand-deleted files.

## Where the work actually is: adapters

Not the tool interface — the **normalisation of supplied artifacts**. Every one
of these is a mismatch class we have already been bitten by:

- SBML paths in `problem.yaml`, relative vs absolute vs alongside;
- condition labels vs the engine's semantic `column=value` keys (this one cost a
  whole run);
- observable ids vs whatever the measurement table calls them (cost another);
- parameter-table columns, scales and bounds conventions;
- replicate encoding, units, error-type declarations.

An adapter per entry point, each with its own failure modes. This is the bulk of
the effort and it does not shrink because the plumbing is elegant. The PEtab
adapter (`round_status.adapt_supplied_petab`) handles the first four of those
mismatch classes; replicate encoding is derived by counting repeated
(observable, condition, time) rows.

## Prerequisite, not polish

Eight distinct early bugs were one of two shapes: *a resume replayed
state no marker guarded*, or *a transient failure wrote permanent state*. Making
re-entry a first-class feature multiplies exactly those paths. The invalidation
semantics and the "nothing terminal is written on a transient failure" rule are
therefore prerequisites for this design, not follow-ups to it.

## Who may call it

Exposing modules as tools is right. The recommendation on record is to keep the
**default sequence deterministic** and make re-entry a request that passes
through a human gate, because it costs money and changes the scientific record.
An agent proposing "redo assembly with a different noise model" is good; an agent
silently doing it loses the property that made those eight bugs findable in
minutes — that the run is replayable and the ledger says what the workflow did,
not what an agent chose to do.

## Hierarchical estimation · what pyPESTO's inner optimisation actually supports

Read from pyPESTO's own documentation and then verified against the pinned
0.6.0 source, because the engine's feature gate has to be right and an empirical probe
alone was giving misleading answers.

Sources: [Hierarchical optimization](https://pypesto.readthedocs.io/en/v0.4.0/example/hierarchical.html)
· [pypesto.hierarchical.relative API](https://pypesto.readthedocs.io/en/latest/api/pypesto.hierarchical.relative.html).

**The encoding.** Inner parameters are selected by a non-standard
`parameterType` column in the PEtab parameter table — `scaling`, `offset` or
`sigma` — and they must reach the model through the placeholder convention:
`observableParameter1_<obsId>` (scaling) and `observableParameter2_<obsId>`
(offset) in `observableFormula`, `noiseParameter1_<obsId>` in `noiseFormula`,
each resolved per measurement by the `observableParameters` /
`noiseParameters` columns. The importer is
`PetabImporter(petab_problem, hierarchical=True)`.

This is **not** the encoding the merge emits today: it composes the scaling
factor into the observable formula directly (`sc_obs_x * (...)`). The engine has to
change the merge, not just add a flag.

**Three hard constraints, each confirmed in the installed source.**

| constraint | documented | verified in 0.6.0 |
|---|---|---|
| inner bounds are fixed, not ours | offset/scaling `[-inf, inf]`, sigma `[0, inf]` | `pypesto.C.INNER_PARAMETER_BOUNDS` has exactly those; other bounds raise `ValueError: Invalid bounds for inner parameters` |
| inner parameters are linearly scaled | "linearly-scaled inner parameters" only | sigma on `log10` raises `NotImplementedError`; scaling/offset on a log scale merely warn that the scale is "used only for their visualization" — i.e. silently ignored |
| Gaussian noise only | "Gaussian (normal) noise distributions" only | `hierarchical/relative/util.compute_nllh` hardcodes `0.5 * Σ log(2π σ²) + …`; the word "laplace" appears nowhere in the hierarchical package |

**The dangerous one is the third, and it is worse than unsupported.** A PEtab
problem may declare `noiseDistribution: laplace` and enable hierarchical
optimisation, and the analytical inner solver will compute a **Gaussian**
likelihood anyway. It does not check the declared distribution and it does not
raise. That is a wrong number wearing the shape of a result — exactly the cell
the engine must never enable.

**So the feature gate is:**

- hierarchical is available only when every observable in the problem declares
  `normal` noise. One `laplace` observable disables it for the whole problem,
  with a ledger note naming the observable — never silently.
- the merge writes inner bounds from `INNER_PARAMETER_BOUNDS`, overriding
  `assembly_defaults.{scaling,offset,sigma}_bounds` for parameters it marks
  inner, and keeps them on `lin` scale whatever the rest of the table uses.
- scaling and offset for one observable are marked inner together or not at
  all. Marking one while its partner stays an ordinary estimated
  `observableParameter` is not a configuration the library supports, and the
  objective it then computes does not agree with the plain fit at the same
  parameter values (measured: 108.59 against 4.66 on a one-species problem).
- inner parameters still COUNT in k for AIC/BIC and in the DOF gate, and the
  report labels their values `estimated_inner` — the accounting rules are
  unchanged by any of this.

`tools/probe_hierarchical_matrix.py` verifies this contract rather than
exploring blindly: it checks that the documented combinations reach the same
optimum as a plain fit, and that each undocumented one fails LOUDLY instead of
returning a plausible number.

<!-- HIERARCHICAL-PROBE-BEGIN -->
**Measured on pypesto 0.6.0 (this venv), `tools/probe_hierarchical_matrix.py`.** The `expected` column is the DOCUMENTED contract, fixed before anything ran; the verdict is what the installed library did. Each cell fits a one-species synthetic problem plainly, then checks an exact identity — at the plain optimum the hierarchical objective must read the same number, since it re-solves inner parameters that are already optimal there — and only then compares the two optima (8 seeded starts, tolerance 0.01). `raises (safe)` is the RIGHT outcome for an unsupported cell. **`SILENTLY WRONG` is the only outcome the engine cannot defend against**: no error, and a number that is not the likelihood the problem declared.

| inner set | noise | scale | expected | verdict | plain −logL | hier @ plain opt | detail |
|---|---|---|---|---|---|---|---|
| sigma | normal | lin | supported | **works** | 4.6554 | 4.6554 | same function, same optimum |
| sigma | normal | log10 | unsupported | **raises (safe)** | 4.6554 | — | refuses loudly, as an unsupported cell should: NotImplementedError: LOG and LOG10 parameter scale of inner parameters is not supported for sigma parameters. Inner parameter table: parameterType parameterScale parameterId sigma_obs sigma log10 |
| sigma | laplace | lin | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| sigma | laplace | log10 | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| scaling+offset | normal | lin | supported | **works** | 4.6554 | 4.6554 | same function, same optimum |
| scaling+offset | normal | log10 | unsupported | **works anyway** | 4.6554 | 4.6554 | accepted without raising and agrees with the declared likelihood at the plain optimum; undocumented but not observably wrong here |
| scaling+offset | laplace | lin | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| scaling+offset | laplace | log10 | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| scaling+offset+sigma | normal | lin | supported | **works** | 4.6554 | 4.6554 | same function, same optimum |
| scaling+offset+sigma | normal | log10 | unsupported | **raises (safe)** | 4.6554 | — | refuses loudly, as an unsupported cell should: NotImplementedError: LOG and LOG10 parameter scale of inner parameters is not supported for sigma parameters. Inner parameter table: parameterType parameterScale parameterId sc_obs scaling log10 off_o |
| scaling+offset+sigma | laplace | lin | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| scaling+offset+sigma | laplace | log10 | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| scaling | normal | lin | unsupported | **SILENTLY WRONG** | 4.6554 | 108.5945 | accepted an unsupported cell without raising, and at the plain optimum its objective reads 108.5945 where the declared likelihood reads 4.6554 — it is computing a different likelihood and saying nothing |
| scaling | normal | log10 | unsupported | **SILENTLY WRONG** | 4.6554 | 108.5899 | accepted an unsupported cell without raising, and at the plain optimum its objective reads 108.5899 where the declared likelihood reads 4.6554 — it is computing a different likelihood and saying nothing |
| scaling | laplace | lin | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| scaling | laplace | log10 | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| offset | normal | lin | unsupported | **works anyway** | 4.6554 | 4.6554 | accepted without raising and agrees with the declared likelihood at the plain optimum; undocumented but not observably wrong here |
| offset | normal | log10 | unsupported | **works anyway** | 4.6554 | 4.6554 | accepted without raising and agrees with the declared likelihood at the plain optimum; undocumented but not observably wrong here |
| offset | laplace | lin | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |
| offset | laplace | log10 | unsupported | **reference failed** | — | — | the PLAIN fit failed, so this cell says nothing about hierarchical: RuntimeError: no start converged to a finite objective |

**3 of 3 documented-supported cells verified.** 2 unsupported cell(s) refused loudly, which is the correct behaviour. **2 cell(s) came back SILENTLY WRONG** — accepted without raising while computing a different likelihood: [('scaling', 'normal', 'lin'), ('scaling', 'normal', 'log10')]. The ENGINE must refuse these, since the library will not.
<!-- HIERARCHICAL-PROBE-END -->

## Related: profiling

Same modularity question, smaller. Today `_profiles()` is called only on the
single-model path, so the discrimination and model-space-search runs — every run
worth showing — carry **no identifiability assessment at all**.

The rule: profiles should run **on the best model only, behind
a gate, and then be assessed**. As a module that is a post-selection step
operating on the winner, uniform across goals, which is simpler than the three
different behaviours currently in the code.

Settings are a separate decision and should be made deliberately rather than
inherited. We pass no `ProfileOptions` at all, so we run pyPESTO defaults, and
those defaults are what the open PRs target:

- **ICB-DCM/pyPESTO#1713** (open) — "Profile method 1 stabilisation and default":
  extrapolating parameters that do not move with the profiled one makes the walk
  "bounce around or fail". Proposes `next_guess_method` `adaptive_step_order_1` →
  `adaptive_step_order_0`, `reg_order` 4 → 1, and a `correlation_threshold` (0.7).
  **We run `adaptive_step_order_1` with `reg_order=4` — the configuration it
  calls unstable.**
- **ICB-DCM/pyPESTO#1711** (merged upstream) — absolute step sizes are too small
  for wide bounds; adds relative step sizes as a fraction of `ub−lb`. Not present
  in our installed 0.6.0 (`ProfileOptions` still exposes only the absolute
  family). Our bounds routinely span 4–7 decades, which is the case it fixes.
- **ICB-DCM/pyPESTO#1712** (open) — multistart at each profile point, plus
  warnings when profiling finds a *lower* objective than the supplied optimum and
  when non-profiled parameters hit bounds. Both are disconnected-profile
  symptoms, currently silent for us.
- **ICB-DCM/pyPESTO#1736** — v0.7.0 release, in flight.

Suggested order when this is picked up: pin a pypesto version deliberately, pass
explicit `ProfileOptions`, and validate on `toy_decay_params`, where the truth is
known and a disconnected profile is visible.

### ProfileOptions stability probe

<!-- PROFILE-OPTIONS-PROBE-BEGIN -->
**Measured on pypesto 0.6.0 (this venv), `tools/probe_profile_options.py`.** The question per cell is the dangerous direction only: can a profile that SHOULD be open read as closed? A `closed` interval is a claim of identifiability, and an overclaim there is one the epistemics gate cannot catch, because that gate compares the agent's words against the profile rather than against the truth. The sloppy case builds an exact flat direction (a free scale on absolutely calibrated data, collinear with `A0`), and the parameter that must read OPEN is the one whose own box binds first: `A0`, whose box is 2 decades against `sc_sloppy`'s 6. Its partner reading closed at ~2 decades is the compensation for that box, not a claim; `k1` and `sigma_obs_A` are identified here and should read closed.

| case | options | parameter | reads | width (scaled) | of bound span |
|---|---|---|---|---|---|
| toy_decay_params | defaults (what we run today) | `k1` | **closed** | 0.0527 | 0.0132 |
| toy_decay_params | defaults (what we run today) | `A0` | **closed** | 0.0219 | 0.0109 |
| toy_decay_params | defaults (what we run today) | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| toy_decay_params | PR1713 (order_0 + reg_order 1) | `k1` | **closed** | 0.0481 | 0.012 |
| toy_decay_params | PR1713 (order_0 + reg_order 1) | `A0` | **closed** | 0.023 | 0.0115 |
| toy_decay_params | PR1713 (order_0 + reg_order 1) | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| toy_decay_params | order_0 only | `k1` | **closed** | 0.0481 | 0.012 |
| toy_decay_params | order_0 only | `A0` | **closed** | 0.023 | 0.0115 |
| toy_decay_params | order_0 only | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| toy_decay_params | reg_order 1 only | `k1` | **closed** | 0.0527 | 0.0132 |
| toy_decay_params | reg_order 1 only | `A0` | **closed** | 0.0219 | 0.0109 |
| toy_decay_params | reg_order 1 only | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| toy_phos | defaults (what we run today) | `k_phos` | **closed** | 0.9453 | 0.2363 |
| toy_phos | defaults (what we run today) | `k_dephos` | **closed** | 0.3147 | 0.0787 |
| toy_phos | defaults (what we run today) | `sc_obs_pR` | **closed** | 0.8943 | 0.149 |
| toy_phos | defaults (what we run today) | `sigma_obs_pR` | **closed** | 0.2386 | 0.0341 |
| toy_phos | PR1713 (order_0 + reg_order 1) | `k_phos` | **closed** | 1.0277 | 0.2569 |
| toy_phos | PR1713 (order_0 + reg_order 1) | `k_dephos` | **closed** | 0.3641 | 0.091 |
| toy_phos | PR1713 (order_0 + reg_order 1) | `sc_obs_pR` | **closed** | 1.0094 | 0.1682 |
| toy_phos | PR1713 (order_0 + reg_order 1) | `sigma_obs_pR` | **closed** | 0.2386 | 0.0341 |
| toy_phos | order_0 only | `k_phos` | **closed** | 1.0277 | 0.2569 |
| toy_phos | order_0 only | `k_dephos` | **closed** | 0.3641 | 0.091 |
| toy_phos | order_0 only | `sc_obs_pR` | **closed** | 1.0094 | 0.1682 |
| toy_phos | order_0 only | `sigma_obs_pR` | **closed** | 0.2386 | 0.0341 |
| toy_phos | reg_order 1 only | `k_phos` | **closed** | 0.9453 | 0.2363 |
| toy_phos | reg_order 1 only | `k_dephos` | **closed** | 0.3147 | 0.0787 |
| toy_phos | reg_order 1 only | `sc_obs_pR` | **closed** | 0.8943 | 0.149 |
| toy_phos | reg_order 1 only | `sigma_obs_pR` | **closed** | 0.2386 | 0.0341 |
| sloppy (free scale on calibrated data) | defaults (what we run today) | `k1` | **closed** | 0.0527 | 0.0132 |
| sloppy (free scale on calibrated data) | defaults (what we run today) | `A0` | **OPEN** | 2.0 | 1.0 |
| sloppy (free scale on calibrated data) | defaults (what we run today) | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| sloppy (free scale on calibrated data) | defaults (what we run today) | `sc_sloppy` | **closed** | 2.0226 | 0.3371 |
| sloppy (free scale on calibrated data) | PR1713 (order_0 + reg_order 1) | `k1` | **closed** | 0.0481 | 0.012 |
| sloppy (free scale on calibrated data) | PR1713 (order_0 + reg_order 1) | `A0` | **OPEN** | 2.0 | 1.0 |
| sloppy (free scale on calibrated data) | PR1713 (order_0 + reg_order 1) | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| sloppy (free scale on calibrated data) | PR1713 (order_0 + reg_order 1) | `sc_sloppy` | **closed** | 2.023 | 0.3372 |
| sloppy (free scale on calibrated data) | order_0 only | `k1` | **closed** | 0.0481 | 0.012 |
| sloppy (free scale on calibrated data) | order_0 only | `A0` | **OPEN** | 2.0 | 1.0 |
| sloppy (free scale on calibrated data) | order_0 only | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| sloppy (free scale on calibrated data) | order_0 only | `sc_sloppy` | **closed** | 2.023 | 0.3372 |
| sloppy (free scale on calibrated data) | reg_order 1 only | `k1` | **closed** | 0.0527 | 0.0132 |
| sloppy (free scale on calibrated data) | reg_order 1 only | `A0` | **OPEN** | 2.0 | 1.0 |
| sloppy (free scale on calibrated data) | reg_order 1 only | `sigma_obs_A` | **closed** | 0.2932 | 0.0419 |
| sloppy (free scale on calibrated data) | reg_order 1 only | `sc_sloppy` | **closed** | 2.0226 | 0.3371 |

**No options set read a genuinely unbounded parameter as closed.** `A0` reads OPEN in every cell, which is the one-directional question this probe exists to answer.

`sc_sloppy` reads closed in every cell, and that is CORRECT rather than an overclaim: it is the other half of the flat direction, and the direction terminates when `A0` hits its own (narrower) bound. The widths agree with that reading — PR1713 (order_0 + reg_order 1): sc_sloppy spans 2.023 decades against A0's 2.0-decade box; defaults (what we run today): sc_sloppy spans 2.0226 decades against A0's 2.0-decade box; order_0 only: sc_sloppy spans 2.023 decades against A0's 2.0-decade box; reg_order 1 only: sc_sloppy spans 2.0226 decades against A0's 2.0-decade box.

`k1` and `sigma_obs_A` are identified in this problem and read closed in every cell, as they should.

Every cell keeps `x_full_scaled` and `nllh` in the stored path, which uncertainty.py reads as the confidence-region skeleton.
<!-- PROFILE-OPTIONS-PROBE-END -->
