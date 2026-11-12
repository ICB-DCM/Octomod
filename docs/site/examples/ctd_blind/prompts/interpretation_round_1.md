# Prompt · `interpretation` (round 1)

The **interpretation** agent reads the fits and answers the question (S7, round 1). Below is the exact prompt it was sent in this run (203,192 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Evaluation interpretation: say what the fitted result means

You write the diagnosis: why the model misfits, what the data cannot distinguish, what is nonetheless determined,
whether each success criterion is met, and whether to accept, revise or stop. This is the least automated step in
the protocol and the reason a model is here at all.

## What you receive
`intent`, `experiment_description` (the lab note: how the data were made, the artefacts it names, the study team's
decisions, which are given), `report_core` (fit metrics, criteria, uncertainty, held-out performance, the
`computed_*` lists, `attribution`), `residual_diagnostics` (the fit over time with its observation-layer evidence,
and `residual_forms`), `data_signals` (the replicates' own read on the error model), `instruction`, and
`diagnostics_instruction`. You do not see supplied literature: you judge the fit from the data, not from what papers
expect.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
Required: `diagnosis`, `misfit_hypotheses`, `cannot_distinguish`, `nonetheless_determined`, `answers_intent`
(`{criterion, verdict: pass|partial|fail, evidence}` each), `recommendation`. Optional:
`finite_but_poorly_determined`, `requested_diagnostics`. Shape: Output contract.

## Rules that get your reply refused
- **Copy the computed entries, then add yours.** Every entry of `report_core.computed_cannot_distinguish` appears in
  `cannot_distinguish`, and every entry of `computed_nonetheless_determined` in `nonetheless_determined`, character
  for character. An entry may be a parameter id, `mechanism:<candidate_id>`, an `observable@condition` label or a
  formula (`flat combination (FIM): 1.00*log(k_a) -1.00*log(k_b)`): paste it, never retype a weight, flip a sign,
  reorder terms or merge two entries. A deterministic gate checks both lists; a miss is quoted back to you once and
  then blocks. The computed lists are the floor of what must be said, never the ceiling.
- Every parameter the report marks unconstrained or non-identifiable is in `cannot_distinguish`, since omitting one
  is overclaiming, and every prediction it marks tight is in `nonetheless_determined`: hedging a tight prediction
  because its parameters are flat is as wrong, and flat parameters with tight predictions is a normal, publishable
  result.
- Score each success criterion separately, with the number that decides it; never average them into an impression.
- `recommendation` is exactly one of `accept`, `revise`, `stop`, and follows from the verdicts you wrote.
- Thresholds come from the workflow spec: interpret them, do not re-derive them.

## How to judge
- Every claim points at a diagnostic: this observable, this condition, this parameter, this held-out series.
  Diagnose from the numbers you were given, not from a fit plot in your head.
- A residual whose cause the lab note already names is reported as that cause, not as a missing mechanism.
- Held-out performance is the primary evidence about generalisation: a good training fit that fails held out is a
  misfit, not a success.
- Structure in the residuals is the signal, not their size. Sign runs early-then-late in every condition point at a
  missing delay or a wrong initial state; misfit growing with dose at a missing saturation or a mis-encoded dose;
  misfit in one condition only at that condition's encoding; misfit in one observable everywhere at its mapping,
  scaling or noise model. `residual_forms` names each residual's functional form and timescale and groups the series
  that agree: evidence about shape and timescale, not a mechanism by itself.
- χ²/dof well below 1 means sigma is too large or the model over-parameterised, not an excellent fit. PIT
  non-uniformity with otherwise unstructured residuals indicts the noise distribution, not the mechanism.
- A parameter at a bound is a statement about the bound, not about the biology; say which. Keep "the data cannot
  determine it" (identifiability) apart from "its value is implausible" (modelling): they lead to different moves.
- An unidentifiable pair (`k_on`/`k_off` seen only as a ratio) goes into `cannot_distinguish` as the pair, with the
  determined combination in `nonetheless_determined`.
- `computed_finite_but_poorly_determined` holds parameters whose profile closes on both sides but spans more than a
  tenth of its box (`gates.determined_box_fraction`): bounded by the data, not well determined. The engine copies it
  into your third list; state the width rather than calling such a parameter determined or undetermined, and add an
  entry only for a further quantity you can point at the same way. A discrimination round has no such list.
- When several diagnoses fit, rank them and say which the report distinguishes. The next agent gets one move;
  ranking is your job. A mechanism the residual pattern cannot tell from three others is "one of several" — or say
  what would separate them.
- **Curves you were not sent.** Every series carries its summary (rmse, rmse over the replicate floor, largest
  deviation and when, sign pattern, lag-1 autocorrelation, monotone trend, |residual|-vs-signal correlation); only
  the worst few carry the point-by-point fit, because all of them would overflow the prompt, and the rest appear as
  one number each under `other_series_rmse_over_replicate_noise_floor`. The summaries usually suffice. When they do
  not, `residual_curve {candidate_id, observable_id, condition_id}` or `profile_path {parameter_id}` returns one
  series or one profile, read from files already written; nothing is refitted. Each request costs another call of
  you from a small budget: ask only for what your diagnosis will use. Omitting the key is the normal answer.

## Mistakes we have seen
- Blanket hedging ("preliminary, more data needed") beside tight intervals.
- Declaring success because the objective improved while a criterion went unmet.
- Attributing all structure in the residuals to noise.
- `accept` with a failed criterion, or `revise` without a diagnosis a single move could target.
- Dropping an unconstrained parameter because the prediction it feeds came out fine.


# Your tools
TOOLS: none. No shell, no file system, no web, no code execution, and no way to inspect data beyond what this prompt contains — the inputs below are everything this role is given, by design. A command, a tool call, or 'let me look at …' written into the reply cannot run and fails the contract. Reply with the JSON object only.

# Inputs

## intent
```json
{
  "question": "Build a model of this CTD phosphorylation time course that explains the measured distributions, and say what it implies about how P-TEFb modifies the substrate. Report explicitly what these data can and cannot establish about the mechanism. In particular, test whether the modification of a repeat changes the rate at which its immediate neighbours in the array are modified, against the alternatives that the rate depends only on how many repeats are already modified (cooperativity between repeats) or on nothing at all, and say which of these the data can and cannot separate. Also test the earlier conclusion, drawn by eye, that the kinase acts distributively rather than processively.",
  "system": "RNA polymerase II CTD (8 heptarepeats, in vitro), phosphorylated by P-TEFb (CDK9/cyclin T1); mass-spectrometry time course",
  "required_entities": [
    "CTD",
    "P-TEFb",
    "ATP"
  ],
  "required_predictions": [
    "the mechanism of phosphorylation that best explains the measured distributions, identified and defended",
    "a statement of which mechanistic questions these data cannot answer"
  ],
  "perturbations": [
    "none \u2014 a single in vitro condition, sampled over time"
  ],
  "timescale": "minutes, horizon 960 min (16 h)",
  "scope_exclusions": [
    "transcription, DNA and the polymerase itself \u2014 this is a purified in vitro assay",
    "the distinction between Ser2 and Ser5 within a repeat (established as mutually exclusive under these conditions; each repeat is one bit)"
  ],
  "success_criteria": [
    "the selected mechanism is reported with its information criterion, its Akaike weight and the indistinguishable set, honestly, whatever they turn out to be",
    "the observation model is stated explicitly, including how predicted amounts are mapped onto relative MS intensities at each time point",
    "any mechanistic question the data cannot resolve is named as unresolved rather than decided"
  ],
  "inference_target": "mechanism_discrimination",
  "domain_packs": [
    "general-dynamics",
    "measurement-tech"
  ]
}
```
## experiment_description
# CTD phosphorylation by P-TEFb — in vitro time course (bench note)

## The system

RNA polymerase II carries a long, flexible tail on its largest subunit called the
C-terminal domain, or CTD. The CTD is not a folded domain: it is a tandem array of
short repeats, each seven amino acids long, with the sequence Tyr–Ser–Pro–Thr–Ser–Pro–Ser.
In human Pol II there are 52 of these heptarepeats. During transcription the CTD is
progressively decorated with phosphate groups, and the resulting pattern of marks is
what recruits and releases the RNA-processing and elongation factors that act on the
polymerase. Which marks are present, and where, is therefore functionally important.

The kinase we are studying here is **P-TEFb** (the CDK9–cyclin T1 complex), which acts
during transcriptional elongation.

## The experiment

This is an **in vitro kinase assay**, not a cellular experiment. There is no
transcription, no DNA, no polymerase — only a purified CTD substrate, purified kinase,
and ATP in buffer.

- **Substrate**: a recombinant CTD construct containing **8 heptarepeats**, not the full
  52. Present at **100 µM**.
- **Kinase**: P-TEFb, catalytic. It is not consumed and its concentration does not change
  over the experiment.
- **ATP**: **3 mM** at the start. Each phosphorylation consumes one ATP.
- **Sampling**: four time points — **0, 1 h, 2 h and 16 h** (0, 60, 120 and 960 minutes).
- **Replication**: one measurement per species per time point. There are **no replicate
  measurements** in this dataset.

## What the readout is, and what it cannot see

The readout is **mass spectrometry** on the intact CTD construct. MS separates the
substrate molecules by mass, and since each phosphate adds a fixed mass, it resolves
**how many of the eight repeats carry a phosphate** — a number between 0 and 8.

**It does not resolve which repeats those are.** A molecule phosphorylated on repeats 1
and 2 and a molecule phosphorylated on repeats 1 and 7 are the same mass and appear in
the same peak. Everything downstream has to live with that: the data are nine numbers per
time point, one for each phosphorylation count, and the positional arrangement behind
those numbers is not observed.

A second point about the chemistry, established previously for this kinase and these
conditions: within a single heptarepeat, phosphorylation happens on **either Ser2 or
Ser5, but not both at once**. So for the purposes of counting, each repeat is either
modified or unmodified — one bit per repeat — and the distinction between the two serine
positions does not need to be tracked.

## The data file, and a caveat you must handle

`data/ctd_ms_timecourse.csv` has one row per time point and nine columns, `phos0_rel`
through `phos8_rel`: the relative MS signal for CTD molecules carrying 0, 1, … 8
phosphates.

**These are relative signal intensities, not concentrations, and they are not comparable
between time points as they stand.** Mass spectrometry reports intensities on an
arbitrary scale that drifts between injections. You can see this directly in the file:
the nine numbers sum to 1.00 at t = 0, to 4.07 at 1 h, to 3.79 at 2 h and to 0.85 at
16 h, even though the total amount of substrate in the tube is conserved throughout.
Any model of this data needs a way to map predicted amounts onto measured intensities,
and that mapping is not the same at every time point.

The measurement error is believed to be additive and normally distributed, with a single
standard deviation for the whole experiment — the same for every peak — that scales from one
time point to the next with that spectrum's overall intensity, the same factor that maps
amounts onto intensities at that time point.

## What is already believed, and what is not settled

Earlier work on this kinase, using this kind of hyperphosphorylation assay in human and
in *Drosophila*, concluded that P-TEFb works **distributively rather than processively**:
that it modifies a repeat, lets go, and rebinds — rather than holding on and running
along the substrate. That conclusion came from looking at the shape of MS distributions
by eye, and was never checked against a quantitative model.

Beyond that, the mechanism is genuinely open. We do not know from these data what governs
the rate at which any individual repeat gets modified, and that is what we would like a
model to tell us. One specific possibility was put to us and we want it tested rather than
assumed either way: that the modification of one repeat changes the rate at which its
immediate neighbours in the array are modified, as opposed to the rate depending only on
how many repeats of the molecule are already modified (cooperativity between repeats,
which was also raised as a possibility to look at), or on nothing at all.

## What can be computed here

Any model that simulates is acceptable, whether it tracks only how many repeats are
modified or which repeats are modified (with eight repeats, 256 configurations). Models
of a few hundred states and a thousand reactions simulate in seconds on the machine this
runs on, so size alone is not a reason to prefer one description over another; choose
the description the question needs. If a possibility can only be represented by tracking
which repeats are modified, we would rather see that model fitted than the question
settled by argument from the counts alone. Such a model can be written out in full, every
state and every reaction listed one by one, and we would rather it were written out than
avoided. The simulator reserves the single letters x, k, p, y, w, h and t, so no species
or parameter may be named with one of them.

## The question

Build a model of this time course that explains the measured distributions, and tell us
what it implies about how P-TEFb modifies the CTD. Be explicit about what these data can
and cannot establish — with eight repeats, four time points and no positional
information, we expect there to be things the data simply cannot decide, and we would
rather know which those are than have them glossed over. We would also like the earlier
conclusion, drawn by eye, that the kinase acts distributively rather than processively,
to be tested against a model and not assumed.

## report_core
```json
{
  "goal": "mechanism_discrimination",
  "discrimination": {
    "candidates": [
      {
        "id": "base",
        "n_est": 8,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -91.2,
        "aic": -166.4035,
        "bic": -153.7353,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 6.399,
        "akaike_weight": 0.0392,
        "criterion": "AIC",
        "value": -166.4035,
        "delta": 6.399,
        "weight": 0.0392
      },
      {
        "id": "product_load_inhibition",
        "n_est": 9,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -95.4,
        "aic": -172.8021,
        "bic": -158.5504,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 0.0,
        "akaike_weight": 0.9608,
        "criterion": "AIC",
        "value": -172.8021,
        "delta": 0.0,
        "weight": 0.9608
      }
    ],
    "winner": "product_load_inhibition",
    "indistinguishable": [
      "product_load_inhibition"
    ],
    "undecided_axes": [],
    "search_topology": {
      "n_axes_declared": 2,
      "union_lattice_models": 4,
      "visited": 2,
      "visited_fraction": 0.5,
      "lattice_root": "M5_neighbour_and_count (round 0)",
      "visited_by_root": {
        "M5_neighbour_and_count (round 0)": 2
      },
      "models_outside_the_lattice": [
        "M1_independent",
        "M2_count_coop",
        "M3_neighbour",
        "M4_processive",
        "M5_neighbour_and_count"
      ],
      "outside_status": [
        "M1_independent (round 0, fitted, -log L -61.36)",
        "M2_count_coop (round 0, fitted, -log L -81.64)",
        "M3_neighbour (round 0, fitted, -log L -84.25)",
        "M4_processive (round 0, fitted, -log L -80.95)",
        "M5_neighbour_and_count (round 0, fitted, -log L -91.20, selected)"
      ],
      "search_mode": "candidates",
      "topology": "one axis at a time on each round's base, greedy across rounds",
      "note": "the union space over every axis declared in this run is 4 models; the search visited 2 of them, on M5_neighbour_and_count (round 0). Corners never visited are not evidence against \u2014 they were not tried. The same family as stepwise/FAMoS."
    },
    "cross_round_comparability": {
      "across_rounds": true,
      "regime": "pure expansion",
      "why": "every round after the first came from an expansion, which copies the data and the shared assembly forward unchanged and only enlarges the model space: the criterion is over the same data in all 2 rounds, so the values ARE comparable across them"
    },
    "decisive": true,
    "criterion": "AIC",
    "delta_aic_threshold": 2.0,
    "decisive_weight_threshold": 0.7,
    "comparability": {
      "shared_transformation": true,
      "correction_applied": false,
      "detail": "every candidate uses the same transformation per observable (lin) \u2014 criteria are already over the same data",
      "per_candidate": {
        "base": {
          "transformations": {
            "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin"
          },
          "correction": 0.0,
          "by_observable": {
            "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            }
          }
        },
        "product_load_inhibition": {
          "transformations": {
            "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin",
            "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": "lin"
          },
          "correction": 0.0,
          "by_observable": {
            "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            },
            "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
              "transformation": "lin",
              "n": 1,
              "term": 0.0
            }
          }
        }
      },
      "reads_as": "criteria are over the same data; no change-of-variables term is needed"
    },
    "petab_select": {
      "version": "0.4.0",
      "files": {
        "problem_yaml": "selection_files/petab_select_problem.yaml",
        "model_space": "selection_files/model_space.tsv",
        "models": "selection_files/models.yaml"
      },
      "model_space_sha": "5211f6c6ae4586a1",
      "crosscheck": "petab_select 0.4.0 agrees with the local arithmetic on AIC, weights and winner (2 models, tol 1e-06)"
    },
    "t2prime": {},
    "t2prime_passed": null
  },
  "parameters": {
    "base": {
      "kmod": 0.004577,
      "cp": 1.588,
      "q_proc": 0.0,
      "K_ATP": 50.0,
      "nb": 0.314,
      "sc_ctd_ms_t0": 0.009986,
      "sc_ctd_ms_t60": 0.03971,
      "sc_ctd_ms_t120": 0.03844,
      "sc_ctd_ms_t960": 0.008519,
      "sigma_ctd_ms": 1.012
    },
    "product_load_inhibition": {
      "kmod": 0.005141,
      "cp": 1.627,
      "q_proc": 0.0,
      "K_ATP": 50.0,
      "nb": 0.3111,
      "kon_I": 0.0009088,
      "koff_I": 1.0,
      "sc_ctd_ms_t0": 0.009989,
      "sc_ctd_ms_t60": 0.0404,
      "sc_ctd_ms_t120": 0.03925,
      "sc_ctd_ms_t960": 0.008596,
      "sigma_ctd_ms": 0.8899
    }
  },
  "holdout": {
    "available": false,
    "note": "no held-out condition declared \u2014 discrimination rests on information criteria alone, stated honestly"
  },
  "misfit_evidence": {
    "available": false,
    "signals": {
      "residual_shape_only": false
    },
    "sigma_inflated": [],
    "autocorrelation": null,
    "gof_at_noise_floor": null,
    "thresholds": {
      "alpha": 0.01,
      "max_sigma_over_floor": 1.3,
      "autocorr_alpha": 0.05
    },
    "open": false,
    "reasons": [],
    "also_seen": [],
    "evaluated_for": "product_load_inhibition"
  },
  "noise_check": {
    "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    },
    "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
      "assumed": "normal",
      "n": 1,
      "note": "too few residuals for a distribution test"
    }
  },
  "identifiability": {
    "available": true,
    "method": "residual sensitivities (AMICI, sigma residuals included) at the MLE, FIM = J^T J",
    "space": "scaled parameter space (as optimised)",
    "n_free": 9,
    "x_names": [
      "kmod",
      "cp",
      "nb",
      "kon_I",
      "sc_ctd_ms_t0",
      "sc_ctd_ms_t60",
      "sc_ctd_ms_t120",
      "sc_ctd_ms_t960",
      "sigma_ctd_ms"
    ],
    "eigenvalues_log10": [
      5.243,
      4.826,
      4.778,
      4.217,
      4.061,
      3.88,
      2.66,
      2.29,
      1.524
    ],
    "spread_decades": 3.72,
    "flat_decades_threshold": 8.0,
    "flat_directions": [],
    "eigenvector_composition_smallest": {
      "kmod": 0.111,
      "cp": 0.014,
      "nb": 0.011,
      "kon_I": 0.993,
      "sc_ctd_ms_t0": 0.0,
      "sc_ctd_ms_t60": 0.013,
      "sc_ctd_ms_t120": 0.017,
      "sc_ctd_ms_t960": 0.012,
      "sigma_ctd_ms": -0.013
    },
    "note": "local, necessary-condition screen at one point: a direction this many decades below the largest eigenvalue is a parameter COMBINATION the data barely constrain (sloppy-model register); full rank proves nothing. Report the spectrum, never a rank verdict.",
    "structural_recheck": {
      "available": true,
      "method": "the residual Jacobian at the MLE (the information screen's own) and at 2 random points within \u00b10.5 (scaled units) of it, each normalised, stacked; each pre-fit direction is tested along its own vector",
      "rule": 3,
      "pre_fit_available": true,
      "pre_fit_why": null,
      "n_pre_fit": 0,
      "directions": [],
      "n_confirmed": 0,
      "n_not_confirmed": 0,
      "flat_at_mle_only": [],
      "n_flat_at_mle": 0,
      "jacobian_reused": true,
      "spread": 0.5,
      "seed": 20260943
    }
  },
  "profiles_skipped": "not requested \u2014 profiles are computed only when asked for: `profiles` at the verdict card computes them for this model, or start the round with --profiles",
  "profiles_on_request": {
    "n_free": 12,
    "projection": {
      "available": true,
      "n_parameters": 9,
      "points_low": 55,
      "points_high": 612,
      "basis": "FIM at the MLE",
      "n_fim": 9,
      "workers": 9,
      "per_point_low_s": 18.45,
      "per_point_high_s": 36.89,
      "per_point_source": "cost probe range",
      "per_point_detail": "1\u20132 \u00d7 the median start (18.45 s) from the cost probe",
      "low_s": 112.7,
      "high_s": 2508.8,
      "schedule": {
        "default_step_size": 0.01,
        "min_step_size": 0.001,
        "max_step_size": 0.1,
        "step_size_factor": 1.25
      },
      "threshold_nllh": 1.921
    }
  },
  "computed_cannot_distinguish": [],
  "computed_nonetheless_determined": [
    "mechanism:product_load_inhibition"
  ],
  "computed_finite_but_poorly_determined": [],
  "latent_states": {
    "conditions_checked": 1,
    "conserved_totals": [],
    "declared_ranges": {},
    "findings": [],
    "hard_failures": []
  },
  "declared_constants": {
    "declared": 0,
    "violated": 0,
    "worst_drift": null,
    "rows": []
  },
  "attribution": {
    "available": true,
    "winner": "product_load_inhibition",
    "reconciliation": {
      "winner_recorded_nllh": -95.4,
      "winner_reevaluated_nllh": -95.4,
      "winner_drift": 3.579e-06,
      "split_tolerance": 1e-06,
      "table_checked": true,
      "table_mismatches": [],
      "table_tolerance": 0.05,
      "note": "the split is exact against AMICI's own per-condition likelihood; `drift` is the difference between re-evaluating the recorded optimum and the value the fit recorded there, which is solver noise between two evaluations and is not attributed to any measurement"
    },
    "full_record": "attribution",
    "rivals": [
      {
        "rival": "base",
        "available": true,
        "delta_aic": 6.399,
        "delta_nllh": 4.199,
        "delta_k": 1,
        "likelihood_units": 8.399,
        "parameter_units": -2.0,
        "contributions": [
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.02,
            "delta_aic_units": 4.04,
            "n": 1,
            "share": 0.1454
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.432,
            "delta_aic_units": -2.865,
            "n": 1,
            "share": 0.1031
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.206,
            "delta_aic_units": -2.412,
            "n": 1,
            "share": 0.0868
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.088,
            "delta_aic_units": 2.176,
            "n": 1,
            "share": 0.0783
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8689,
            "delta_aic_units": 1.738,
            "n": 1,
            "share": 0.0625
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.8342,
            "delta_aic_units": -1.668,
            "n": 1,
            "share": 0.06
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8038,
            "delta_aic_units": 1.608,
            "n": 1,
            "share": 0.0578
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.6443,
            "delta_aic_units": 1.289,
            "n": 1,
            "share": 0.0464
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.6375,
            "delta_aic_units": -1.275,
            "n": 1,
            "share": 0.0459
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.3658,
            "delta_aic_units": -0.7316,
            "n": 1,
            "share": 0.0263
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.3434,
            "delta_aic_units": -0.6868,
            "n": 1,
            "share": 0.0247
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3349,
            "delta_aic_units": 0.6698,
            "n": 1,
            "share": 0.0241
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3122,
            "delta_aic_units": 0.6243,
            "n": 1,
            "share": 0.0225
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2633,
            "delta_aic_units": 0.5266,
            "n": 1,
            "share": 0.0189
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2111,
            "delta_aic_units": 0.4221,
            "n": 1,
            "share": 0.0152
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1756,
            "delta_aic_units": 0.3513,
            "n": 1,
            "share": 0.0126
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1292,
            "delta_aic_units": 0.2585,
            "n": 1,
            "share": 0.0093
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1283,
            "delta_aic_units": 0.2566,
            "n": 1,
            "share": 0.0092
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1205,
            "delta_aic_units": 0.2409,
            "n": 1,
            "share": 0.0087
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1196,
            "delta_aic_units": 0.2391,
            "n": 1,
            "share": 0.0086
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1196,
            "delta_aic_units": 0.2391,
            "n": 1,
            "share": 0.0086
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1196,
            "delta_aic_units": 0.2391,
            "n": 1,
            "share": 0.0086
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1196,
            "delta_aic_units": 0.2391,
            "n": 1,
            "share": 0.0086
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1196,
            "delta_aic_units": 0.2391,
            "n": 1,
            "share": 0.0086
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1193,
            "delta_aic_units": 0.2387,
            "n": 1,
            "share": 0.0086
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1145,
            "delta_aic_units": 0.229,
            "n": 1,
            "share": 0.0082
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1113,
            "delta_aic_units": 0.2225,
            "n": 1,
            "share": 0.008
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1073,
            "delta_aic_units": 0.2147,
            "n": 1,
            "share": 0.0077
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.03016,
            "delta_aic_units": -0.06032,
            "n": 1,
            "share": 0.0022
          }
        ],
        "top": [
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.02,
            "delta_aic_units": 4.04,
            "n": 1,
            "share": 0.1454
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.432,
            "delta_aic_units": -2.865,
            "n": 1,
            "share": 0.1031
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.206,
            "delta_aic_units": -2.412,
            "n": 1,
            "share": 0.0868
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.088,
            "delta_aic_units": 2.176,
            "n": 1,
            "share": 0.0783
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8689,
            "delta_aic_units": 1.738,
            "n": 1,
            "share": 0.0625
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.8342,
            "delta_aic_units": -1.668,
            "n": 1,
            "share": 0.06
          }
        ],
        "groups_only_in_winner": [],
        "groups_only_in_rival": [],
        "worst_group_detail": {
          "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
          "points": [
            {
              "time": 60.0,
              "measured": 0.3523,
              "winner_sim": 0.2931,
              "rival_sim": 0.2497,
              "delta_nllh": 2.02
            }
          ]
        }
      }
    ],
    "neutralisation": {
      "note": null,
      "refused": {},
      "parameters": {
        "kon_I": {
          "available": true,
          "axis": "product_load_inhibition",
          "neutral_value": 0.0,
          "denotes": "rate at which the phosphate load (\u03a3 n\u00b7CTD_n, \u00b5M, equal to ADP produced) occupies free P-TEFb; with koff_I it sets K_I = koff_I/kon_I (0 = no product inhibition)",
          "verified_by_simulation": true,
          "nllh_off": -1.013,
          "nllh_on": -95.4,
          "cost_of_switching_off_aic_units": 188.7766,
          "series_that_move": [
            "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8"
          ],
          "series": [
            {
              "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
              "worst_shift_in_sigma": 5.65,
              "mean_shift_in_sigma": 5.647,
              "delta_nllh": 4.352
            },
            {
              "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
              "worst_shift_in_sigma": 5.39,
              "mean_shift_in_sigma": 5.388,
              "delta_nllh": 27.17
            },
            {
              "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
              "worst_shift_in_sigma": 5.24,
              "mean_shift_in_sigma": 5.236,
              "delta_nllh": 14.37
            },
            {
              "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
              "worst_shift_in_sigma": 4.47,
              "mean_shift_in_sigma": 4.47,
              "delta_nllh": 12.71
            },
            {
              "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
              "worst_shift_in_sigma": 3.38,
              "mean_shift_in_sigma": 3.38,
              "delta_nllh": 15.1
            },
            {
              "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
              "worst_shift_in_sigma": 3.16,
              "mean_shift_in_sigma": 3.161,
              "delta_nllh": 11.87
            }
          ]
        }
      }
    },
    "axes_on": [
      "product_load_inhibition"
    ]
  },
  "estimated_inner": {}
}
```
## residual_diagnostics
```json
{
  "observation_evidence": {
    "for_model": "product_load_inhibition",
    "per_observable": {
      "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      },
      "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8": {
        "noise_check": {
          "assumed": "normal",
          "n": 1
        },
        "qq_tail_deviation": null,
        "fitted_sigma_vs_replicate_floor": {},
        "abs_residual_vs_signal_corr_by_condition": {
          "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": null
        },
        "abs_residual_vs_signal_corr_median": null
      }
    },
    "reads_as": "the error-model half of the diagnosis: a positive abs_residual_vs_signal_corr with a rejecting noise check points at proportional noise, not at a missing mechanism"
  },
  "per_candidate_residuals": {
    "base": {
      "sigma_vs_replicate_floor": [],
      "per_series": {
        "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.9996,
              "simulated": 0.9986,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0009197,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0009,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.0608,
              "simulated": 0.0513,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.009471,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0095,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.3935,
              "simulated": 0.4582,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.06468,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0647,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.002e-15,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.1905,
              "simulated": 0.164,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02642,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0264,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.8975,
              "simulated": 0.846,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05148,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0515,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 5.536e-15,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.3989,
              "simulated": 0.3395,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05939,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0594,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.8977,
              "simulated": 0.9523,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0546,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0546,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.448e-14,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.6243,
              "simulated": 0.5976,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02667,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0267,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.7797,
              "simulated": 0.8243,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04459,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0446,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.132e-10,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.8271,
              "simulated": 0.8713,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04423,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0442,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.5941,
              "simulated": 0.5464,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04773,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0477,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 7.334e-08,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.8555,
              "simulated": 0.8773,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02183,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0218,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.3523,
              "simulated": 0.2497,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1027,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.1027,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 8.559e-06,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.6418,
              "simulated": 0.5824,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05939,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0594,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.1584,
              "simulated": 0.0761,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.08223,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0822,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0001,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 7.157e-05,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0001,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.1945,
              "simulated": 0.2726,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.07807,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0781,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.0,
              "simulated": 0.0159,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.01588,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0159,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.001,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001018,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.001,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.0,
              "simulated": 0.0877,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.08771,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0877,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.0,
              "simulated": 0.002,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.002025,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.002,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.8516,
              "simulated": 0.8508,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0007856,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0008,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        }
      }
    },
    "product_load_inhibition": {
      "sigma_vs_replicate_floor": [],
      "per_series": {
        "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.9996,
              "simulated": 0.9989,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0007113,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0007,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.0608,
              "simulated": 0.0683,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.007458,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0075,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.3935,
              "simulated": 0.4499,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05641,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0564,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 2.136e-11,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.1905,
              "simulated": 0.1985,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.007999,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.008,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.8975,
              "simulated": 0.8193,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.07818,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0782,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.271e-10,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.3989,
              "simulated": 0.3777,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02126,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0213,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.8977,
              "simulated": 0.9294,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03175,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0318,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 7.518e-10,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.6243,
              "simulated": 0.6199,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.004373,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0044,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.7797,
              "simulated": 0.8328,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05315,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0532,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 5.088e-08,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.8271,
              "simulated": 0.8635,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03641,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0364,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.5941,
              "simulated": 0.5883,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0058,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0058,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 4.524e-06,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.8555,
              "simulated": 0.8534,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.002101,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0021,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.3523,
              "simulated": 0.2931,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05919,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0592,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0002,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0001646,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0002,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.6418,
              "simulated": 0.5701,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.07171,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0717,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.1584,
              "simulated": 0.0996,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05878,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0588,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.001,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0009885,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.001,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.1945,
              "simulated": 0.2766,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.08205,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0821,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.0,
              "simulated": 0.0238,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02382,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0238,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.0,
              "simulated": 0.0074,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.007416,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0074,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.0,
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "0",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 120.0,
              "measured": 0.0,
              "simulated": 0.097,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.09699,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.097,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.0,
              "simulated": 0.0036,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.00365,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0036,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 960.0,
              "measured": 0.8516,
              "simulated": 0.851,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0006184,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0006,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        }
      }
    }
  },
  "cross_model_by_measurement": [
    {
      "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0009,
      "best_rmse": 0.0007,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.227,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0095,
      "best_rmse": 0.0075,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.213,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0647,
      "best_rmse": 0.0564,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.128,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0264,
      "best_rmse": 0.008,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.697,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0515,
      "best_rmse": 0.0515,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0594,
      "best_rmse": 0.0213,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.642,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0546,
      "best_rmse": 0.0318,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.418,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0267,
      "best_rmse": 0.0044,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.836,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0446,
      "best_rmse": 0.0446,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0442,
      "best_rmse": 0.0364,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.177,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0477,
      "best_rmse": 0.0058,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.878,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0218,
      "best_rmse": 0.0021,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.904,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.1027,
      "best_rmse": 0.0592,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.424,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0594,
      "best_rmse": 0.0594,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0822,
      "best_rmse": 0.0588,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.285,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0001,
      "best_rmse": 0.0001,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0781,
      "best_rmse": 0.0781,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0159,
      "best_rmse": 0.0159,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.001,
      "best_rmse": 0.001,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "base",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0877,
      "best_rmse": 0.0877,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.002,
      "best_rmse": 0.002,
      "best_model": "base",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0008,
      "best_rmse": 0.0006,
      "best_model": "product_load_inhibition",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.213,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    }
  ],
  "identical_prediction_controls": [],
  "residual_forms": {
    "per_series": [
      {
        "model": "product_load_inhibition",
        "series": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.08002,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.2135,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.569,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.792e-09,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.229,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.175,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.662e-08,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.6086,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.8831,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -9.827e-08,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.1252,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.478,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -6.651e-06,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.042,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.1613,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.0005914,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.06015,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.646,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.02151,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.053,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.635,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.1292,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.349,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.6625,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.9695,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.777,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.1015,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "product_load_inhibition",
        "series": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.08084,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.091,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.2435,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.61,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.162e-13,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.6793,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.281,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -6.421e-13,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.527,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.359,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.68e-12,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.6857,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.11,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.313e-08,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.137,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.188,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -8.507e-06,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.5612,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.555,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.0009928,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.527,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.047,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.008301,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.007,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.3951,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.1181,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.255,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.05038,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "base",
        "series": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.09112,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      }
    ],
    "summary": [
      "product_load_inhibition (selected): residual of obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.08 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.21 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.6 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000000028 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.23 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.2 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000000017 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.61 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.88 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000000098 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.13 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.5 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000067 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.16 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00059 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.06 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.6 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.022 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.1 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.6 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.13 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.3 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.66 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.97 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.8 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.1 \u03c3 (1 series).",
      "product_load_inhibition (selected): residual of obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.081 \u03c3 (1 series).",
      "base (base): residual of obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.091 \u03c3 (1 series).",
      "base (base): residual of obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.24 \u03c3 (1 series).",
      "base (base): residual of obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.6 \u03c3 (1 series).",
      "base (base): residual of obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00000000000012 \u03c3 (1 series).",
      "base (base): residual of obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.68 \u03c3 (1 series).",
      "base (base): residual of obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.3 \u03c3 (1 series).",
      "base (base): residual of obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00000000000064 \u03c3 (1 series).",
      "base (base): residual of obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.5 \u03c3 (1 series).",
      "base (base): residual of obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.4 \u03c3 (1 series).",
      "base (base): residual of obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000000000017 \u03c3 (1 series).",
      "base (base): residual of obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.69 \u03c3 (1 series).",
      "base (base): residual of obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.1 \u03c3 (1 series).",
      "base (base): residual of obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000000013 \u03c3 (1 series).",
      "base (base): residual of obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.1 \u03c3 (1 series).",
      "base (base): residual of obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.2 \u03c3 (1 series).",
      "base (base): residual of obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000085 \u03c3 (1 series).",
      "base (base): residual of obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.56 \u03c3 (1 series).",
      "base (base): residual of obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.6 \u03c3 (1 series).",
      "base (base): residual of obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00099 \u03c3 (1 series).",
      "base (base): residual of obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.5 \u03c3 (1 series).",
      "base (base): residual of obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2 \u03c3 (1 series).",
      "base (base): residual of obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0083 \u03c3 (1 series).",
      "base (base): residual of obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2 \u03c3 (1 series).",
      "base (base): residual of obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.4 \u03c3 (1 series).",
      "base (base): residual of obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.12 \u03c3 (1 series).",
      "base (base): residual of obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "base (base): residual of obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.3 \u03c3 (1 series).",
      "base (base): residual of obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.05 \u03c3 (1 series).",
      "base (base): residual of obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.091 \u03c3 (1 series)."
    ],
    "how_to_read_this": "Each residual series (measured minus simulated, every replicate) of the selected model and the base, fitted with constant, linear, exponential and rise-and-fall forms and chosen by small-sample AICc against the constant, against the replicate noise floor (else the fitted sigma): `amplitude` is in units of that sigma, `timescales` in the data's own time unit; a field a form does not have (a constant's timescale, a peak time off a transient) is left out of its row. `summary` groups the series whose forms agree, with every timescale within a factor of two, per observable and stimulus, and names what disagrees. One timescale shared across conditions points at one missing process; an amplitude that scales with dose points at where it enters; a form that changes by condition points at what the condition changes. A description, not a test: AICc treats the points as independent, so confirm a form with the fit_residual_form request before building an axis on it."
  },
  "how_to_read_this": "fit_over_time is the fit itself: measured, simulated, and the residual in units of the assay's own replicate noise, per timepoint. Read the SHAPE. A residual that grows and then returns is an overshoot and points at a regulatory term the model lacks; largest_deviation.at_time tells you WHEN, which usually tells you where in the network. A residual that drifts one way throughout is a wrong rate or a missing sink, and monotone_trend_with_time will be significant while an overshoot's will not. Few n_sign_runs over many timepoints means systematic, not noise. A steady_state entry is a time-inf measurement read against the model's steady state, kept out of the time course and every statistic over it. Residuals within about 1 noise unit are the assay talking, not the model. A row in cross_model_by_measurement marked PRIME SUSPECT is a measurement no structure in the space could fix while it is still above the noise floor \u2014 start there. Rows marked already-at-the-noise-floor are unimprovable by construction; inventing mechanism for those is how a model gets fitted to noise. identical_prediction_controls are condition pairs this model cannot tell apart, so their residual difference is pure noise and calibrates everything else. THEN the differential diagnosis, which is one act with two answers: observation_evidence says whether the defect is the ERROR MODEL rather than the mechanism. When |residual| grows with the signal (abs_residual_vs_signal_corr well above 0) AND the noise check rejects the assumed distribution, propose an OBSERVATION axis \u2014 proportional noise, a scaling or an offset \u2014 not a mechanism; the curve's shape is then a consequence of the wrong error model. When the residual SHAPE localises in time or in a condition while the noise check does not reject and |residual| is flat in the signal, propose STRUCTURE. A fitted sigma above the replicate floor says the likelihood has already absorbed something into the noise, so read it alongside both. residual_forms names each residual's functional form and timescale and groups the series that agree: its summary is the shortest statement of what is still wrong, and its how_to_read_this says what a shared timescale or a dose-scaled amplitude points at."
}
```
## data_signals
```json
{
  "CTD_phos0_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos1_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos2_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos3_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos4_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos5_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos6_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos7_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  },
  "CTD_phos8_rel": {
    "error_model": "inconclusive",
    "why": "only 0 usable replicate cell(s); a slope needs at least 3",
    "spread_vs_magnitude_slope": null,
    "slope_ci95": null,
    "slope_se": null,
    "n_cells_with_replicates": 0,
    "n_usable_cells": 0,
    "n_cells_dropped_nonpositive_mean": 0,
    "n_cells_dropped_zero_spread": 0,
    "replicates_per_cell": [],
    "pooled_excess_kurtosis": null,
    "distribution_family": "NOT TESTED \u2014 with these replicate(s) per point the tail shape is out of reach; the kurtosis above is descriptive only"
  }
}
```
## instruction
cannot_distinguish MUST include every entry of computed_cannot_distinguish verbatim; nonetheless_determined MUST include every entry of computed_nonetheless_determined verbatim. Add interpretation beyond them where the evidence warrants. An entry written as an identifier — a parameter id, an observable@condition label, mechanism:<id> — must name one this round's problem has; write anything else in words. residual_diagnostics is the fit itself, time-resolved, with the observation-layer evidence beside it: read the SHAPE and the differential diagnosis in how_to_read_this before naming a missing mechanism; residual_diagnostics.residual_forms.summary names each residual's functional form and timescale across the conditions, the shortest account of what is still wrong. report_core.attribution splits the ΔAIC over (observable, condition) exactly and says what each mechanism term buys when switched off — narrate WHY the winner wins from THOSE numbers, naming the measurements that paid for it, rather than restating the weight. experiment_description is the lab note: how the data were produced, the artefacts and caveats it names, and the study team's decisions. Treat those decisions as given, and before attributing a residual to a missing mechanism, check whether the lab note already names its cause.
## diagnostics_instruction
You may request engine-run diagnostics before answering, via `requested_diagnostics: [{kind, args}]`. The two that read what this payload bounded away are residual_curve(candidate_id, observable_id, condition_id) — one series' point-by-point fit, for a series summarised here rather than drawn — and profile_path(parameter_id) — one parameter's profile-likelihood path. The whole whitelist is ['simulate_with', 'residuals_for', 'compare_conditions', 'fit_residual_form', 'residual_curve', 'profile_path']. Results come back under `diagnostics_requested` and you are asked again. HONEST COST: a request is one more agent call, so ask only for a curve or a path you will actually reason about in your diagnosis; the summaries here are what rank the series, and they are usually enough.

# Output contract
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
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "diagnosis": "SELECTED MECHANISM. product_load_inhibition is the round-0 winner M5_neighbour_and_count plus one global term, and it has the following parts. (a) It is distributive by construction: q_proc is fixed at 0.0. (b) The per-repeat rate is modulated by a neighbour factor nb = 0.311 and a count factor cp = 1.627. (c) ATP is saturating: K_ATP is fixed at 50 µM, while ATP never falls below about 2.2 mM (3 mM minus at most 0.8 mM consumed). (d) Free P-TEFb is inhibited by the accumulated phosphate load Σn·CTD_n, which equals the ADP produced. K_I = koff_I/kon_I = 1.0/0.000909 ≈ 1.1 mM, with koff_I fixed. If the rate tracks free P-TEFb, that is about 27% slowing at the ≈410 µM load reached by 2 h and about 42% at the 800 µM end point. Scores: AIC −172.80 and Akaike weight 0.961. The base is at ΔAIC 6.40 with weight 0.039. The indistinguishable set is {product_load_inhibition}. Only 2 of the 4 models in the declared lattice were visited, and the unvisited corners are untried, not rejected. There is no held-out series, so the selection rests on AIC alone.\n\nWHY IT WINS (attribution). ΔnLLH is 4.20, worth 8.40 likelihood units against 2 parameter units. Of that, 2.44 is earned in the 60- and 120-min spectra, as a net of gains and losses spread over nine peaks. Gains: phos5@60 +2.02 (winner 0.293, base 0.250, measured 0.352), phos2@120 +1.09, phos6@60 +0.87, phos4@60 +0.80, phos2@60 +0.64. Losses: phos1@60 −1.43, phos8@120 −1.21, phos6@120 −0.83, phos7@120 −0.64. The other 1.76 units come from the t0 and t960 points. Both models fit those to within 0.1σ, except phos7@960, which costs the winner 0.34. They pay only because the shared sigma fell from 1.012 to 0.890 µM. Switching kon_I off without refitting costs 188.8 AIC units. Refitted (that is, the base), it costs 6.4, because kmod drops from 0.00514 to 0.00458 to compensate. So the term mainly reshapes the progress curve rather than adding a large independent effect. The mean number of marks per molecule is 2.48 at 1 h and 4.13 at 2 h. First-order depletion of repeats at a constant ≈0.0062 min⁻¹ already predicts 4.19 at 2 h, so the overall deceleration does not by itself demand a global brake.\n\nOBSERVATION MODEL. Each peak's intensity is sc_t × the amount in µM, with a linear transformation. The scales are sc_ctd_ms_t0 = 0.00999, sc_ctd_ms_t60 = 0.0404, sc_ctd_ms_t120 = 0.0393 and sc_ctd_ms_t960 = 0.0086 per µM. For 100 µM of conserved substrate these give totals of 1.00, 4.04, 3.93 and 0.86, against measured 1.00, 4.07, 3.79 and 0.85. Noise is additive normal with one sigma_ctd_ms = 0.890 µM for all peaks, scaled by the same sc_t. In intensity units that is σ = 0.0089, 0.036, 0.035 and 0.0077 at the four time points.\n\nFIT QUALITY. Sigma is fitted and there are no replicates, so χ² = 36 = n_data by construction and no absolute goodness-of-fit test exists. About 35 of the 36 χ² units sit in the 18 points at 60 and 120 min, because each t0 and t960 spectrum is fitted trivially by its own scale factor. The fitted σ is therefore about √2 smaller than the scatter of the informative points. That inflates every σ-unit below and sharpens the likelihood behind ΔAIC. On the 60/120-min points alone the margin would be roughly 2×2.44−2 ≈ 2.9 AIC units, weight about 0.8: still above the 2.0 threshold, so the selection stands, but less sharply than 0.961 suggests.\n\nWHAT IS STILL WRONG. All residuals are single unreplicated points, so the case rests on sign agreement across the two informative spectra.\n- High counts: at both 60 and 120 min the winner puts mass at 7 and 8 marks that the data lack. Residuals: phos7@60 −0.66σ, phos8@60 −0.10σ, phos7@120 −2.35σ, phos8@120 −2.78σ (the last two are the largest in the fit).\n- Middle counts: it puts too little at 5–6 marks: phos5@60 +1.65σ, phos6@60 +1.64σ, phos6@120 +2.05σ.\n- Late time: it leaves about 0.9% of molecules at 7 marks at 16 h (phos7@960 −0.97σ), and the data have none.\n- The zero at phos8@120 is not a detection floor. Measured 8-mark CTD is 0 at 2 h while 7-mark CTD is 0.19, and a 0-mark peak of 0.061 was detected in the same spectrum.\n- So the data want the last one or two modifications specifically slowed early, yet complete by 16 h. The global product-load term brakes every step instead: it raised phos8@120 from 0.088 to 0.097.\n- A weaker, isolated residual at 60 min: phos1 +2.18σ, with phos0 −1.57σ and phos3 −1.48σ.\n\nMECHANISM ANSWERS. Round-0 log-likelihoods are given. AICs below assume each variant adds one parameter to a 6-parameter independent model, consistent with the 8-parameter M5. ΔAIC to the winner: M5 6.4, neighbour-only M3 18.3, count-only M2 23.5, processive-only M4 24.9, independent M1 62.1.\n1. 'Rate depends on nothing' is rejected (−log L −61.36 vs −95.40). The measured distributions are broader than binomial: the variance of marks per molecule is 2.57 against 1.71 at 1 h, and 2.63 against 2.00 at 2 h.\n2. Neighbour-only beats count-only by about 5.2 AIC, and both together beat neighbour-only by about 11.9. Dropping cp costs 6.95 nllh units and dropping nb 9.56. nb and cp move by less than 3% between the two round-1 candidates.\n3. But intact-mass MS sees only the configuration-averaged rate at each count. A neighbour effect projects onto an effective count-dependent rate profile, and M5's need for two shape parameters is what a two-parameter or free per-count count-only profile could also supply. That model was not fitted, so 'neighbour over count' holds only against the one-parameter count form.\n4. Distributive vs processive was not tested on the selected structure, because q_proc is fixed at 0.0 in both round-1 candidates. The only processive model fitted, M4 (processive with otherwise independent rates), loses to M5 by about 18.5 AIC, but it changes two things at once. Against count-only M2 it differs by only about 1.4 AIC, below the 2.0 threshold. Processivity and positive count cooperativity both broaden count distributions, and the data do not separate them as single additions. The distributions are unimodal at 60 and 120 min, with no unmodified-plus-heavily-modified bimodality. That is consistent with the by-eye distributive reading but does not exclude a partial processive component.\n5. The cause of the global slowdown is not identifiable. ADP and phospho-CTD both equal Σn·CTD_n by stoichiometry, and in a single condition progress is monotone in time, so time-dependent kinase inactivation is confounded with both.\n\nIDENTIFIABILITY. The local FIM is full rank with a 3.72-decade eigenvalue spread (threshold 8) and no flat directions. The smallest eigenvector is dominated by kon_I (0.993, with kmod at 0.111). Profiles were not computed, so no parameter interval is known. kon_I is the least-determined parameter: its K_I lies above the maximal load of 0.8 mM, so only the initial slope of inhibition is seen.\n\nRECOMMENDATION. Revise, with one move: free q_proc on product_load_inhibition. This is the test of the distributive conclusion that the intent asks for and that the winner currently assumes. The next move after that is a count-only model with a high-occupancy slowdown term, fitted against nb. It targets the 7–8-mark misfit and tests whether the neighbour term is separable from count dependence at all.",
 "misfit_hypotheses": [
  "1 (best supported, unaddressed by any visited model). A slowdown specific to the last one or two modifications is missing: the per-repeat rate falls once a molecule carries about 6 or more marks, or terminal/sequence-divergent repeats are poor substrates. Evidence: n=7,8 are over-predicted at both informative times (phos7@120 −2.35σ, phos8@120 −2.78σ, phos7@60 −0.66σ) and n=5–6 under-predicted (phos5@60 +1.65σ, phos6@60 +1.64σ, phos6@120 +2.05σ). Measured 8-mark CTD is 0 at 2 h while a 0.061 peak was detected in the same spectrum, and conversion is complete by 16 h. The global product-load term does not supply this: it worsened phos8@120 (0.088 → 0.097) and created phos7@960 −0.97σ. Count-dependent and position-dependent versions cannot be separated from intact-mass counts; middle-down or positional MS, or single-repeat mutants, would separate them.",
  "2. The product-load term partly stands in for distribution shape rather than reporting an independent inhibitory process. Evidence: the mean marks per molecule (2.48 at 1 h, 4.13 at 2 h) matches constant-rate first-order site depletion (≈0.0062 min⁻¹ predicts 4.19 at 2 h). Switching kon_I off unrefitted costs 188.8 AIC units, but refitted it costs only 6.4, with kmod compensating from 0.00514 to 0.00458. Of the 4.20 nllh gain, only 2.44 is earned at 60/120 min, spread as wins and losses over nine peaks. ADP inhibition, phospho-CTD inhibition and time-dependent kinase inactivation would all appear this way in one condition. An ADP spike-in, a second ATP/ADP ratio, or late enzyme addition would separate them.",
  "3. A partial processive component, or molecule-to-molecule rate heterogeneity (not in the model space), contributes to the broader-than-binomial distributions now carried by cp alone. Evidence: variance of marks 2.57 vs 1.71 binomial at 1 h and 2.63 vs 2.00 at 2 h. Processive-only and count-only additions to the independent model differ by only ≈1.4 AIC (−log L −80.95 vs −81.64). Untested on the selected structure because q_proc is fixed at 0.0; freeing it there is the separating move.",
  "4 (lowest as a cause of mechanism misfit). Observation layer: absent peaks are recorded as exact zeros (phos7@60, phos8@60, phos8@120 and every absent peak at t0/t960), which additive Gaussian noise cannot produce. The 18 trivially fitted t0/t960 points also shrink the shared sigma by about √2 relative to the informative scatter, inflating every σ-unit (phos8@120 would be ≈−2.0σ) and the likelihood margin. The noise model is the study team's stated decision and is not changed here. The phos8@120 zero is not a detection-floor artefact, because a smaller peak (phos0@120 = 0.061) was detected in the same spectrum."
 ],
 "cannot_distinguish": [
  "Neighbour-dependent rates (nb) versus a count-dependent rate profile with more than one shape parameter. Counts-only MS sees the configuration-averaged rate per count. The round-0 preference for neighbour-only over count-only (≈5.2 AIC) and for neighbour+count over either compares one-parameter encodings only; a flexible count-only profile was never fitted.",
  "Processive versus distributive modification on the selected structure. q_proc is fixed at 0.0 in both round-1 candidates. The only processive model fitted (M4_processive in round 0, −log L −80.95) lacks the neighbour and count terms, so its ≈18.5 AIC deficit to M5 conflates processivity with rate modulation.",
  "Positive count cooperativity versus processivity (and versus molecule-to-molecule rate heterogeneity, not in the model space) as the source of the broader-than-binomial count distributions. Count-only and processive-only additions to the independent model differ by ≈1.4 AIC units (−log L −81.64 vs −80.95), below the 2.0 threshold.",
  "The identity of the global slowdown. Inhibition of P-TEFb by ADP and by phosphorylated CTD both equal Σn·CTD_n by stoichiometry, and in a single condition both are confounded with time-dependent loss of kinase activity.",
  "kon_I and koff_I separately. koff_I is fixed at 1.0, so only K_I = koff_I/kon_I ≈ 1.1 mM is estimated. With samples 60 min or more apart the binding kinetics are not seen, and K_I above the maximal 0.8 mM load exposes only the initial slope of inhibition.",
  "K_ATP and any ATP-depletion effect. K_ATP is fixed at 50 µM, and ATP stays at or above about 2.2 mM throughout, so the data carry no information on ATP affinity.",
  "Which repeats carry the marks, including whether the deficit of 7- and 8-mark molecules at 60–120 min is position-dependent (terminal or divergent repeats being slower substrates) or count-dependent. Intact-mass MS does not resolve positions."
 ],
 "nonetheless_determined": [
  "mechanism:product_load_inhibition",
  "Rates that depend on nothing are rejected. The independent distributive model (round 0, −log L −61.36) is 34 log-likelihood units, about 62 AIC units at 6 parameters, below the selected model. The measured count distributions are broader than binomial: variance of marks 2.57 vs 1.71 at 1 h and 2.63 vs 2.00 at 2 h.",
  "Within the neighbour+count parametrisation, both terms are away from neutral. Removing cp costs 6.95 and removing nb 9.56 log-likelihood units (round 0). Their MLEs move by less than 3% when product inhibition is added (nb 0.314 → 0.311, cp 1.588 → 1.627).",
  "The per-time-point intensity scales are pinned by the spectrum totals for 100 µM of conserved substrate: sc_ctd_ms_t0 = 0.00999, sc_ctd_ms_t60 = 0.0404, sc_ctd_ms_t120 = 0.0393, sc_ctd_ms_t960 = 0.0086 per µM. They reproduce the measured totals 1.00, 4.07, 3.79 and 0.85 to within 4%.",
  "Fully modified CTD is absent at 2 h while 7-mark CTD is about 5% of molecules and a 0.061 peak is detected in the same spectrum; conversion is complete by 16 h, with 8-mark CTD the only species at 960 min."
 ],
 "answers_intent": [
  {
   "criterion": "the selected mechanism is reported with its information criterion, its Akaike weight and the indistinguishable set, honestly, whatever they turn out to be",
   "verdict": "pass",
   "evidence": "product_load_inhibition: AIC −172.80, Akaike weight 0.961. Base (M5_neighbour_and_count) at ΔAIC 6.40, weight 0.039. Indistinguishable set {product_load_inhibition}, decisive against the 2.0 / 0.7 thresholds. Stated with its caveats: only 2 of 4 lattice models were visited; there is no held-out data; 1.76 of the 4.20 nllh units are collected at t0/t960 only through the shared sigma, and the 60/120-min spectra alone would give roughly 2.9 AIC units."
  },
  {
   "criterion": "the observation model is stated explicitly, including how predicted amounts are mapped onto relative MS intensities at each time point",
   "verdict": "pass",
   "evidence": "Intensity = sc_t × amount (µM), linear, with one free scale per time point: 0.00999, 0.0404, 0.0393 and 0.0086 at 0, 60, 120 and 960 min. Model totals are 1.00, 4.04, 3.93 and 0.86 against measured 1.00, 4.07, 3.79 and 0.85. Noise is additive normal with one sigma_ctd_ms = 0.890 µM for every peak, scaled by the same sc_t, giving σ = 0.0089, 0.036, 0.035 and 0.0077 intensity units."
  },
  {
   "criterion": "any mechanistic question the data cannot resolve is named as unresolved rather than decided",
   "verdict": "partial",
   "evidence": "Named here as unresolved: neighbour versus flexible count dependence; processive versus distributive on the winning structure; count cooperativity versus processivity versus heterogeneity (M2 vs M4 ≈1.4 AIC); ADP versus phospho-CTD versus kinase inactivation; kon_I versus koff_I; K_ATP; positional pattern. But the run itself decided two of these by construction (q_proc fixed at 0.0, koff_I fixed at 1.0). computed_cannot_distinguish is empty, and no profiles were computed. Processivity is therefore untested, not shown to be undecidable."
  },
  {
   "criterion": "test whether modification of a repeat changes its neighbours' rate, against count cooperativity or nothing at all",
   "verdict": "partial",
   "evidence": "'Nothing at all' is rejected by about 62 AIC units. Neighbour-only beats count-only by about 5.2 AIC, and neighbour+count beats neighbour-only by about 11.9 (one parameter per term assumed). This separates neighbour from count only against the one-parameter count form; a count-only model with two or more shape parameters, the alternative counts-only data cannot a priori exclude, was not fitted."
  },
  {
   "criterion": "test the earlier by-eye conclusion that P-TEFb acts distributively rather than processively",
   "verdict": "partial",
   "evidence": "The distributions are unimodal at 60 and 120 min, consistent with distributive action. However, q_proc is fixed at 0.0 in the selected model. The only processive model (M4, −log L −80.95) loses to M5 by about 18.5 AIC while also lacking the neighbour and count terms, and it ties count-only M2 within about 1.4 AIC. Processivity on top of the selected structure has not been fitted."
  }
 ],
 "recommendation": "revise"
}
````
