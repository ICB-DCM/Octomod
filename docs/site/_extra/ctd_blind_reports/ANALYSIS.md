# Analysis report — ctd_blind_local_v3_opus55_20261004_022720

**Question.** Build a model of this CTD phosphorylation time course that explains the measured distributions, and say what it implies about how P-TEFb modifies the substrate. Report explicitly what these data can and cannot establish about the mechanism. In particular, test whether the modification of a repeat changes the rate at which its immediate neighbours in the array are modified, against the alternatives that the rate depends only on how many repeats are already modified (cooperativity between repeats) or on nothing at all, and say which of these the data can and cannot separate. Also test the earlier conclusion, drawn by eye, that the kinase acts distributively rather than processively.

*RNA polymerase II CTD (8 heptarepeats, in vitro), phosphorylated by P-TEFb (CDK9/cyclin T1); mass-spectrometry time course · goal: mechanism_discrimination · 2 round(s) · outcome: `completed`*

## The answer

**M5_neighbour_and_count + product_load_inhibition**, on the basis of information criterion over the fitted candidate set.

<sub>Named `product_load_inhibition` inside its own round, which is how to find it in the record.</sub>

- decisive: **True**
- indistinguishable set: `['product_load_inhibition']`

### Against the questions asked at the start

- **the selected mechanism is reported with its information criterion, its Akaike weight and the indistinguishable set, honestly, whatever they turn out to be** — pass
  - evidence: product_load_inhibition: AIC −172.80, Akaike weight 0.961. Base (M5_neighbour_and_count) at ΔAIC 6.40, weight 0.039. Indistinguishable set {product_load_inhibition}, decisive against the 2.0 / 0.7 thresholds. Stated with its caveats: only 2 of 4 lattice models were visited; there is no held-out data; 1.76 of the 4.20 nllh units are collected at t0/t960 only through the shared sigma, and the 60/120-min spectra alone would give roughly 2.9 AIC units.
- **the observation model is stated explicitly, including how predicted amounts are mapped onto relative MS intensities at each time point** — pass
  - evidence: Intensity = sc_t × amount (µM), linear, with one free scale per time point: 0.00999, 0.0404, 0.0393 and 0.0086 at 0, 60, 120 and 960 min. Model totals are 1.00, 4.04, 3.93 and 0.86 against measured 1.00, 4.07, 3.79 and 0.85. Noise is additive normal with one sigma_ctd_ms = 0.890 µM for every peak, scaled by the same sc_t, giving σ = 0.0089, 0.036, 0.035 and 0.0077 intensity units.
- **any mechanistic question the data cannot resolve is named as unresolved rather than decided** — partial
  - evidence: Named here as unresolved: neighbour versus flexible count dependence; processive versus distributive on the winning structure; count cooperativity versus processivity versus heterogeneity (M2 vs M4 ≈1.4 AIC); ADP versus phospho-CTD versus kinase inactivation; kon_I versus koff_I; K_ATP; positional pattern. But the run itself decided two of these by construction (q_proc fixed at 0.0, koff_I fixed at 1.0). computed_cannot_distinguish is empty, and no profiles were computed. Processivity is therefore untested, not shown to be undecidable.
- **test whether modification of a repeat changes its neighbours' rate, against count cooperativity or nothing at all** — partial
  - evidence: 'Nothing at all' is rejected by about 62 AIC units. Neighbour-only beats count-only by about 5.2 AIC, and neighbour+count beats neighbour-only by about 11.9 (one parameter per term assumed). This separates neighbour from count only against the one-parameter count form; a count-only model with two or more shape parameters, the alternative counts-only data cannot a priori exclude, was not fitted.
- **test the earlier by-eye conclusion that P-TEFb acts distributively rather than processively** — partial
  - evidence: The distributions are unimodal at 60 and 120 min, consistent with distributive action. However, q_proc is fixed at 0.0 in the selected model. The only processive model (M4, −log L −80.95) loses to M5 by about 18.5 AIC while also lacking the neighbour and count terms, and it ties count-only M2 within about 1.4 AIC. Processivity on top of the selected structure has not been fitted.

## Beyond this data

Mechanisms the expansion agent names as acting in this system that the data cannot separate from the selected model, each with the experiment that would. They were not fitted and are not part of the answer; they are what the next experiment could decide.

**Named after round 0**

- **An immediate-neighbour effect as such (modifying repeat i changes the rate at i±1), as distinct from a count-dependent step rate whose profile rises through the mid-counts and brakes near the end**
  - not separable here: MS resolves only the count, so the neighbour term reaches the data only through the count distribution. Its estimate crosses neutral between models (nb 1.81 in M3, 0.31 in M5), which suggests it is acting as a shape term for the step-rate profile. With four time points, no replicates and nine peaks per spectrum, a count-only profile with as many parameters can absorb the same imprint. A count-only flexible-profile candidate should still be fitted at construction, but even a tie would leave the question open.
  - the experiment that would: Use a position-resolved readout at 1 h and 2 h: cleave between repeats (or use middle-down MS with ETD) to localise each phosphate. Alternatively, make one internal repeat unmodifiable (S2A/S5A at repeat 4). A neighbour effect changes the rates at repeats 3 and 5 specifically; a count effect changes every repeat equally per mark.
- **A phosphorylation-count-dependent MS ionisation and detection response**
  - not separable here: Each spectrum has one free gain, and the 0-h and 16-h spectra each contain a single species. Per-count response factors are therefore confounded with cp, nb and the kinetics. A single factor on phos8 alone would simply absorb the one informative cell (phos8 at 2 h).
  - the experiment that would: Calibrate with defined mixtures of synthetic or enzymatically completed phospho-isoforms (for example, known ratios of 0P and 8P CTD) in the same injection, or spike a known amount of 8P standard into the 2-h sample.
- **Loss of kinase activity during the incubation, rather than product inhibition, as the cause of the slower second hour**
  - not separable here: It would be separated from M5 only by the same timing signal the product-inhibition axis uses. With one condition sampled at 0, 1, 2 and 16 h, a time-dependent loss and a load-dependent brake both just slow the second hour relative to the first. The lab note states the kinase is unchanged, so it is not proposed as a competing axis.
  - the experiment that would: Add fresh P-TEFb at 2 h (activity loss predicts a burst; inhibition by product does not). Alternatively, pre-incubate the kinase with ATP and no substrate for 2 h before starting the reaction.
- **Inhibition by phosphorylated CTD, as opposed to ADP, as the product that occupies the kinase**
  - not separable here: In this assay each phosphate added produces one ADP, so both inhibitors equal Σ n·CTD_n at every time point.
  - the experiment that would: Spike ADP at t = 0, or run with an ATP-regenerating system (pyruvate kinase with PEP) that keeps ADP near zero. Separately, add pre-phosphorylated CTD at t = 0.
- **Genuine processivity (several repeats per binding event), as opposed to distributive release followed by rapid rebinding to the same molecule**
  - not separable here: Both produce clustered modification events. A count-level jump term cannot tell them apart at a single kinase and substrate concentration with no chase.
  - the experiment that would: Run a substrate-trap or dilution chase: add a 10-fold excess of unlabelled CTD, or vary the kinase concentration at fixed substrate, and compare count distributions at matched mean. Processive runs are insensitive to the trap; rebinding-driven clustering is not.

## Rounds

| round | what changed | selected |
|---|---|---|
| 0 | initial model space | M5_neighbour_and_count |
| 1 | space expanded on top of M5_neighbour_and_count, adding product_load_inhibition, processive_with_coupling | M5_neighbour_and_count + product_load_inhibition |

## Every model assessed

Criterion values compare models WITHIN a round, not across rounds.

| round | model | n par | −logL | ΔAIC | weight | |
|---|---|---|---|---|---|---|
| 0 | M1_independent | 6 | -61.36 | 55.69 | 0.0000 |  |
| 0 | M2_count_coop | 7 | -81.64 | 17.12 | 0.0002 |  |
| 0 | M3_neighbour | 7 | -84.25 | 11.90 | 0.0026 |  |
| 0 | M4_processive | 7 | -80.95 | 18.50 | 0.0001 |  |
| 0 | M5_neighbour_and_count | 8 | -91.20 | 0.00 | 0.9971 | **selected** |
| 1 | M5_neighbour_and_count | 8 | -91.20 | 6.40 | 0.0392 |  |
| 1 | M5_neighbour_and_count + product_load_inhibition | 9 | -95.40 | 0.00 | 0.9608 | **selected** |

## Still open

- declared undetermined: Neighbour-dependent rates (nb) versus a count-dependent rate profile with more than one shape parameter. Counts-only MS 
- declared undetermined: Processive versus distributive modification on the selected structure. q_proc is fixed at 0.0 in both round-1 candidates
- declared undetermined: Positive count cooperativity versus processivity (and versus molecule-to-molecule rate heterogeneity, not in the model s
- declared undetermined: The identity of the global slowdown. Inhibition of P-TEFb by ADP and by phosphorylated CTD both equal Σn·CTD_n by stoich
- declared undetermined: kon_I and koff_I separately. koff_I is fixed at 1.0, so only K_I = koff_I/kon_I ≈ 1.1 mM is estimated. With samples 60 m
- declared undetermined: K_ATP and any ATP-depletion effect. K_ATP is fixed at 50 µM, and ATP stays at or above about 2.2 mM throughout, so the d

These are stated because they are true, not because the run failed. A limit declared is worth more than a limit hidden.

## What the search covered

local within a round, greedy across rounds. Over the 2 axis/axes declared in this run the union space is 4 models; the search visited **2** (50%). A corner never visited is not evidence against it — it was not tried.

Fitted outside that lattice (whole alternative models rather than axis combinations): `M1_independent (round 0, fitted, -log L -61.36)`, `M2_count_coop (round 0, fitted, -log L -81.64)`, `M3_neighbour (round 0, fitted, -log L -84.25)`, `M4_processive (round 0, fitted, -log L -80.95)`, `M5_neighbour_and_count (round 0, fitted, -log L -91.20, selected)`

## Gate policy

Profile **strict** (`e5c2195af0378fc1`, from `strict.yaml`). 0 gate(s) answered by policy, 15 by a human.

The verdict was signed by **human (via the front end)**. A policy signature is not a human's: it names the file and its hash, so the claim can be traced to the configuration that made it.

## What it cost

19 agent calls · $25.4 · 15 human decisions · 3 module redraft(s), 2 contract retry(ies), 0 extra attempt(s) granted (attempts per call 1.105).

*every gate verdict, agent call and human decision is in the run's ledger. every round after the first came from an expansion, which copies the data and the shared assembly forward unchanged and only enlarges the model space: the criterion is over the same data in all 2 rounds, so the values ARE comparable across them*

## What this run was started with

source: <repo>/testcase/ctd_blind_local_v3
project: ctd_blind_local_v3
input sha: 988971b38fbdf050
  - input/blocklist.txt
  - input/data/ctd_ms_timecourse.csv
  - input/description.md
  - input/intent.yaml
  - input/testcase.yaml

## What code produced this

code: commit 0f8649d plus UNCOMMITTED CHANGES in 4 file(s), diff 9d342c77ea94ba14 — this run is NOT reproducible from the commit alone

versions: python 3.13.12 · pypesto 0.6.0 · amici 1.0.1 · petab 0.8.2 · petab_select 0.4.0 · numpy 2.5.2 · scipy 1.18.1
uv.lock 80579277076996be
