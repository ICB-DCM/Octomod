# Prompt · `interpretation` (round 0)

The **interpretation** agent reads the fits and answers the question (S7, round 0). Below is the exact prompt it was sent in this run (340,245 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent.

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
        "id": "M1_independent",
        "n_est": 6,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -61.36,
        "aic": -110.7152,
        "bic": -101.214,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 55.69,
        "akaike_weight": 0.0,
        "criterion": "AIC",
        "value": -110.7152,
        "delta": 55.69,
        "weight": 0.0
      },
      {
        "id": "M2_count_coop",
        "n_est": 7,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -81.64,
        "aic": -149.2828,
        "bic": -138.1982,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 17.12,
        "akaike_weight": 0.0002,
        "criterion": "AIC",
        "value": -149.2828,
        "delta": 17.12,
        "weight": 0.0002
      },
      {
        "id": "M3_neighbour",
        "n_est": 7,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -84.25,
        "aic": -154.5068,
        "bic": -143.4222,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 11.9,
        "akaike_weight": 0.0026,
        "criterion": "AIC",
        "value": -154.5068,
        "delta": 11.9,
        "weight": 0.0026
      },
      {
        "id": "M4_processive",
        "n_est": 7,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -80.95,
        "aic": -147.9048,
        "bic": -136.8201,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 18.5,
        "akaike_weight": 0.0001,
        "criterion": "AIC",
        "value": -147.9048,
        "delta": 18.5,
        "weight": 0.0001
      },
      {
        "id": "M5_neighbour_and_count",
        "n_est": 8,
        "n_flat": 0,
        "n_data": 36,
        "nllh": -91.2,
        "aic": -166.4035,
        "bic": -153.7353,
        "at_bounds": [],
        "near_bounds": [],
        "delta_aic": 0.0,
        "akaike_weight": 0.9971,
        "criterion": "AIC",
        "value": -166.4035,
        "delta": 0.0,
        "weight": 0.9971
      }
    ],
    "winner": "M5_neighbour_and_count",
    "indistinguishable": [
      "M5_neighbour_and_count"
    ],
    "undecided_axes": [],
    "search_topology": {
      "n_axes_declared": 0,
      "union_lattice_models": 0,
      "visited": 0,
      "visited_fraction": null,
      "lattice_root": null,
      "visited_by_root": {},
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
      "note": "the union space over every axis declared in this run is not defined (no axes declared) models; the search visited 0 of them. Corners never visited are not evidence against \u2014 they were not tried. The same family as stepwise/FAMoS."
    },
    "cross_round_comparability": {
      "across_rounds": true,
      "regime": "single round",
      "why": "one round, so there is no cross-round comparison to caveat"
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
        "M1_independent": {
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
        "M2_count_coop": {
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
        "M3_neighbour": {
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
        "M4_processive": {
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
        "M5_neighbour_and_count": {
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
      "model_space_sha": "2251b8303fe4cd57",
      "crosscheck": "petab_select 0.4.0 agrees with the local arithmetic on AIC, weights and winner (5 models, tol 1e-06)"
    },
    "t2prime": {},
    "t2prime_passed": null
  },
  "parameters": {
    "M1_independent": {
      "kmod": 0.006385,
      "cp": 1.0,
      "q_proc": 0.0,
      "K_ATP": 50.0,
      "sc_ctd_ms_t0": 0.009944,
      "sc_ctd_ms_t60": 0.03713,
      "sc_ctd_ms_t120": 0.03492,
      "sc_ctd_ms_t960": 0.00864,
      "sigma_ctd_ms": 2.409
    },
    "M2_count_coop": {
      "kmod": 0.0051,
      "cp": 1.136,
      "q_proc": 0.0,
      "K_ATP": 50.0,
      "sc_ctd_ms_t0": 0.00998,
      "sc_ctd_ms_t60": 0.03858,
      "sc_ctd_ms_t120": 0.039,
      "sc_ctd_ms_t960": 0.008505,
      "sigma_ctd_ms": 1.325
    },
    "M3_neighbour": {
      "kmod": 0.004889,
      "cp": 1.0,
      "q_proc": 0.0,
      "K_ATP": 50.0,
      "nb": 1.812,
      "sc_ctd_ms_t0": 0.009982,
      "sc_ctd_ms_t60": 0.03895,
      "sc_ctd_ms_t120": 0.03919,
      "sc_ctd_ms_t960": 0.008514,
      "sigma_ctd_ms": 1.228
    },
    "M4_processive": {
      "kmod": 0.005213,
      "cp": 1.0,
      "q_proc": 0.2124,
      "K_ATP": 50.0,
      "sc_ctd_ms_t0": 0.00998,
      "sc_ctd_ms_t60": 0.04046,
      "sc_ctd_ms_t120": 0.03934,
      "sc_ctd_ms_t960": 0.008789,
      "sigma_ctd_ms": 1.321
    },
    "M5_neighbour_and_count": {
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
    "evaluated_for": "M5_neighbour_and_count"
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
    "n_free": 8,
    "x_names": [
      "kmod",
      "cp",
      "nb",
      "sc_ctd_ms_t0",
      "sc_ctd_ms_t60",
      "sc_ctd_ms_t120",
      "sc_ctd_ms_t960",
      "sigma_ctd_ms"
    ],
    "eigenvalues_log10": [
      5.148,
      4.715,
      4.713,
      4.135,
      3.968,
      3.789,
      2.541,
      2.289
    ],
    "spread_decades": 2.86,
    "flat_decades_threshold": 8.0,
    "flat_directions": [],
    "eigenvector_composition_smallest": {
      "kmod": -0.002,
      "cp": 0.002,
      "nb": -0.002,
      "sc_ctd_ms_t0": 0.001,
      "sc_ctd_ms_t60": 0.006,
      "sc_ctd_ms_t120": 0.007,
      "sc_ctd_ms_t960": 0.001,
      "sigma_ctd_ms": -1.0
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
    "n_free": 10,
    "projection": {
      "available": true,
      "n_parameters": 8,
      "points_low": 44,
      "points_high": 536,
      "basis": "FIM at the MLE",
      "n_fim": 8,
      "workers": 9,
      "per_point_low_s": 16.09,
      "per_point_high_s": 32.19,
      "per_point_source": "cost probe range",
      "per_point_detail": "1\u20132 \u00d7 the median start (16.09 s) from the cost probe",
      "low_s": 78.7,
      "high_s": 1916.9,
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
    "mechanism:M5_neighbour_and_count"
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
    "declared": 2,
    "measured": 2,
    "unmeasured": 0,
    "violated": 0,
    "worst_drift": 1.418e-13,
    "rows": [
      {
        "expression": "CTD_0 + CTD_1 + CTD_2 + CTD_3 + CTD_4 + CTD_5 + CTD_6 + CTD_7 + CTD_8",
        "tolerance": 0.01,
        "locator": "'even though the total amount of substrate in the tube is conserved throughout'",
        "why": "total CTD substrate is conserved at 100 uM; modification only moves molecules between count classes",
        "condition": "cond_invitro_PTEFb_CTD8",
        "at_t0": 100.0,
        "worst": 100.0,
        "at_time": 96.0,
        "drift": 1.418e-13,
        "within_tolerance": true
      },
      {
        "expression": "PTEFb",
        "tolerance": 0.01,
        "locator": "'It is not consumed and its concentration does not change over the experiment.'",
        "why": "the kinase is catalytic and constant",
        "condition": "cond_invitro_PTEFb_CTD8",
        "at_t0": 1.0,
        "worst": 1.0,
        "at_time": 0.0,
        "drift": 0.0,
        "within_tolerance": true
      }
    ]
  },
  "attribution": {
    "available": true,
    "winner": "M5_neighbour_and_count",
    "reconciliation": {
      "winner_recorded_nllh": -91.2,
      "winner_reevaluated_nllh": -91.2,
      "winner_drift": 2.786e-06,
      "split_tolerance": 1e-06,
      "table_checked": true,
      "table_mismatches": [],
      "table_tolerance": 0.05,
      "note": "the split is exact against AMICI's own per-condition likelihood; `drift` is the difference between re-evaluating the recorded optimum and the value the fit recorded there, which is solver noise between two evaluations and is not attributed to any measurement"
    },
    "full_record": "attribution",
    "rivals": [
      {
        "rival": "M1_independent",
        "available": true,
        "delta_aic": 55.69,
        "delta_nllh": 29.84,
        "delta_k": 2,
        "likelihood_units": 59.69,
        "parameter_units": -4.0,
        "contributions": [
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 3.273,
            "delta_aic_units": 6.547,
            "n": 1,
            "share": 0.0844
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.63,
            "delta_aic_units": 5.259,
            "n": 1,
            "share": 0.0678
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.285,
            "delta_aic_units": 4.571,
            "n": 1,
            "share": 0.0589
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.739,
            "delta_aic_units": -3.477,
            "n": 1,
            "share": 0.0448
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.709,
            "delta_aic_units": 3.417,
            "n": 1,
            "share": 0.0441
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.575,
            "delta_aic_units": 3.15,
            "n": 1,
            "share": 0.0406
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.465,
            "delta_aic_units": 2.929,
            "n": 1,
            "share": 0.0378
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.201,
            "delta_aic_units": 2.402,
            "n": 1,
            "share": 0.031
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.117,
            "delta_aic_units": -2.234,
            "n": 1,
            "share": 0.0288
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.096,
            "delta_aic_units": -2.192,
            "n": 1,
            "share": 0.0283
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.059,
            "delta_aic_units": 2.118,
            "n": 1,
            "share": 0.0273
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.9351,
            "delta_aic_units": 1.87,
            "n": 1,
            "share": 0.0241
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.9015,
            "delta_aic_units": 1.803,
            "n": 1,
            "share": 0.0232
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8822,
            "delta_aic_units": 1.764,
            "n": 1,
            "share": 0.0228
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8814,
            "delta_aic_units": 1.763,
            "n": 1,
            "share": 0.0227
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.8631,
            "delta_aic_units": 1.726,
            "n": 1,
            "share": 0.0223
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.799,
            "delta_aic_units": 1.598,
            "n": 1,
            "share": 0.0206
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.7245,
            "delta_aic_units": 1.449,
            "n": 1,
            "share": 0.0187
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.6932,
            "delta_aic_units": 1.386,
            "n": 1,
            "share": 0.0179
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.6201,
            "delta_aic_units": 1.24,
            "n": 1,
            "share": 0.016
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.5152,
            "delta_aic_units": -1.03,
            "n": 1,
            "share": 0.0133
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3103,
            "delta_aic_units": 0.6207,
            "n": 1,
            "share": 0.008
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1732,
            "delta_aic_units": 0.3463,
            "n": 1,
            "share": 0.0045
          }
        ],
        "top": [
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 3.273,
            "delta_aic_units": 6.547,
            "n": 1,
            "share": 0.0844
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.63,
            "delta_aic_units": 5.259,
            "n": 1,
            "share": 0.0678
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.285,
            "delta_aic_units": 4.571,
            "n": 1,
            "share": 0.0589
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.739,
            "delta_aic_units": -3.477,
            "n": 1,
            "share": 0.0448
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.709,
            "delta_aic_units": 3.417,
            "n": 1,
            "share": 0.0441
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.575,
            "delta_aic_units": 3.15,
            "n": 1,
            "share": 0.0406
          }
        ],
        "groups_only_in_winner": [],
        "groups_only_in_rival": [],
        "worst_group_detail": {
          "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
          "points": [
            {
              "time": 60.0,
              "measured": 0.8975,
              "winner_sim": 0.846,
              "rival_sim": 0.6679,
              "delta_nllh": 3.273
            }
          ]
        }
      },
      {
        "rival": "M4_processive",
        "available": true,
        "delta_aic": 18.5,
        "delta_nllh": 10.25,
        "delta_k": 1,
        "likelihood_units": 20.5,
        "parameter_units": -2.0,
        "contributions": [
          {
            "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 3.212,
            "delta_aic_units": 6.424,
            "n": 1,
            "share": 0.1394
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -2.664,
            "delta_aic_units": -5.328,
            "n": 1,
            "share": 0.1156
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.731,
            "delta_aic_units": -3.462,
            "n": 1,
            "share": 0.0751
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.699,
            "delta_aic_units": 3.399,
            "n": 1,
            "share": 0.0738
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.623,
            "delta_aic_units": 3.247,
            "n": 1,
            "share": 0.0705
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.065,
            "delta_aic_units": 2.129,
            "n": 1,
            "share": 0.0462
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.9001,
            "delta_aic_units": 1.8,
            "n": 1,
            "share": 0.0391
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.8618,
            "delta_aic_units": -1.724,
            "n": 1,
            "share": 0.0374
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.6438,
            "delta_aic_units": 1.288,
            "n": 1,
            "share": 0.0279
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.6144,
            "delta_aic_units": -1.229,
            "n": 1,
            "share": 0.0267
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.5731,
            "delta_aic_units": 1.146,
            "n": 1,
            "share": 0.0249
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.485,
            "delta_aic_units": 0.9701,
            "n": 1,
            "share": 0.0211
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.449,
            "delta_aic_units": 0.898,
            "n": 1,
            "share": 0.0195
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.4032,
            "delta_aic_units": 0.8064,
            "n": 1,
            "share": 0.0175
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3452,
            "delta_aic_units": 0.6904,
            "n": 1,
            "share": 0.015
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.3422,
            "delta_aic_units": -0.6845,
            "n": 1,
            "share": 0.0149
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3011,
            "delta_aic_units": 0.6023,
            "n": 1,
            "share": 0.0131
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3009,
            "delta_aic_units": 0.6019,
            "n": 1,
            "share": 0.0131
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2992,
            "delta_aic_units": 0.5985,
            "n": 1,
            "share": 0.013
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2978,
            "delta_aic_units": 0.5955,
            "n": 1,
            "share": 0.0129
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2978,
            "delta_aic_units": 0.5955,
            "n": 1,
            "share": 0.0129
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2978,
            "delta_aic_units": 0.5955,
            "n": 1,
            "share": 0.0129
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2978,
            "delta_aic_units": 0.5955,
            "n": 1,
            "share": 0.0129
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2978,
            "delta_aic_units": 0.5955,
            "n": 1,
            "share": 0.0129
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2978,
            "delta_aic_units": 0.5955,
            "n": 1,
            "share": 0.0129
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2688,
            "delta_aic_units": 0.5377,
            "n": 1,
            "share": 0.0117
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2659,
            "delta_aic_units": 0.5319,
            "n": 1,
            "share": 0.0115
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.182,
            "delta_aic_units": -0.3639,
            "n": 1,
            "share": 0.0079
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1617,
            "delta_aic_units": 0.3234,
            "n": 1,
            "share": 0.007
          }
        ],
        "top": [
          {
            "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 3.212,
            "delta_aic_units": 6.424,
            "n": 1,
            "share": 0.1394
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -2.664,
            "delta_aic_units": -5.328,
            "n": 1,
            "share": 0.1156
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.731,
            "delta_aic_units": -3.462,
            "n": 1,
            "share": 0.0751
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.699,
            "delta_aic_units": 3.399,
            "n": 1,
            "share": 0.0738
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.623,
            "delta_aic_units": 3.247,
            "n": 1,
            "share": 0.0705
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.065,
            "delta_aic_units": 2.129,
            "n": 1,
            "share": 0.0462
          }
        ],
        "groups_only_in_winner": [],
        "groups_only_in_rival": [],
        "worst_group_detail": {
          "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
          "points": [
            {
              "time": 960.0,
              "measured": 0.0,
              "winner_sim": 0.001018,
              "rival_sim": 0.02807,
              "delta_nllh": 3.212
            }
          ]
        }
      },
      {
        "rival": "M2_count_coop",
        "available": true,
        "delta_aic": 17.12,
        "delta_nllh": 9.56,
        "delta_k": 1,
        "likelihood_units": 19.12,
        "parameter_units": -2.0,
        "contributions": [
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.766,
            "delta_aic_units": 5.532,
            "n": 1,
            "share": 0.1681
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.489,
            "delta_aic_units": 2.977,
            "n": 1,
            "share": 0.0905
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.318,
            "delta_aic_units": 2.636,
            "n": 1,
            "share": 0.0801
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.8622,
            "delta_aic_units": -1.724,
            "n": 1,
            "share": 0.0524
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.6556,
            "delta_aic_units": -1.311,
            "n": 1,
            "share": 0.0398
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.6363,
            "delta_aic_units": -1.273,
            "n": 1,
            "share": 0.0387
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.5443,
            "delta_aic_units": -1.089,
            "n": 1,
            "share": 0.0331
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.4943,
            "delta_aic_units": 0.9885,
            "n": 1,
            "share": 0.03
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.4522,
            "delta_aic_units": 0.9044,
            "n": 1,
            "share": 0.0275
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.4119,
            "delta_aic_units": 0.8239,
            "n": 1,
            "share": 0.025
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.3791,
            "delta_aic_units": -0.7581,
            "n": 1,
            "share": 0.023
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.3589,
            "delta_aic_units": -0.7178,
            "n": 1,
            "share": 0.0218
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2864,
            "delta_aic_units": 0.5728,
            "n": 1,
            "share": 0.0174
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.272,
            "delta_aic_units": 0.5441,
            "n": 1,
            "share": 0.0165
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.271,
            "delta_aic_units": 0.542,
            "n": 1,
            "share": 0.0165
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2691,
            "delta_aic_units": 0.5382,
            "n": 1,
            "share": 0.0164
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.5361,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.5361,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.5361,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.5361,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.5361,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.5361,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.268,
            "delta_aic_units": 0.536,
            "n": 1,
            "share": 0.0163
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2657,
            "delta_aic_units": 0.5315,
            "n": 1,
            "share": 0.0161
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2612,
            "delta_aic_units": 0.5225,
            "n": 1,
            "share": 0.0159
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2424,
            "delta_aic_units": 0.4848,
            "n": 1,
            "share": 0.0147
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2402,
            "delta_aic_units": 0.4804,
            "n": 1,
            "share": 0.0146
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2087,
            "delta_aic_units": 0.4175,
            "n": 1,
            "share": 0.0127
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.01102,
            "delta_aic_units": -0.02204,
            "n": 1,
            "share": 0.0007
          }
        ],
        "top": [
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.766,
            "delta_aic_units": 5.532,
            "n": 1,
            "share": 0.1681
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.489,
            "delta_aic_units": 2.977,
            "n": 1,
            "share": 0.0905
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.318,
            "delta_aic_units": 2.636,
            "n": 1,
            "share": 0.0801
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.8622,
            "delta_aic_units": -1.724,
            "n": 1,
            "share": 0.0524
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.6556,
            "delta_aic_units": -1.311,
            "n": 1,
            "share": 0.0398
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.6363,
            "delta_aic_units": -1.273,
            "n": 1,
            "share": 0.0387
          }
        ],
        "groups_only_in_winner": [],
        "groups_only_in_rival": [],
        "worst_group_detail": {
          "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
          "points": [
            {
              "time": 60.0,
              "measured": 0.8977,
              "winner_sim": 0.9523,
              "rival_sim": 1.032,
              "delta_nllh": 2.766
            }
          ]
        }
      },
      {
        "rival": "M3_neighbour",
        "available": true,
        "delta_aic": 11.9,
        "delta_nllh": 6.948,
        "delta_k": 1,
        "likelihood_units": 13.9,
        "parameter_units": -2.0,
        "contributions": [
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.133,
            "delta_aic_units": 4.266,
            "n": 1,
            "share": 0.1501
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.764,
            "delta_aic_units": 3.528,
            "n": 1,
            "share": 0.1241
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.38,
            "delta_aic_units": 2.76,
            "n": 1,
            "share": 0.0971
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.115,
            "delta_aic_units": -2.229,
            "n": 1,
            "share": 0.0784
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.9095,
            "delta_aic_units": -1.819,
            "n": 1,
            "share": 0.064
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.7233,
            "delta_aic_units": -1.447,
            "n": 1,
            "share": 0.0509
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.4297,
            "delta_aic_units": -0.8593,
            "n": 1,
            "share": 0.0302
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.418,
            "delta_aic_units": 0.8361,
            "n": 1,
            "share": 0.0294
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.3873,
            "delta_aic_units": -0.7746,
            "n": 1,
            "share": 0.0273
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.3658,
            "delta_aic_units": 0.7315,
            "n": 1,
            "share": 0.0257
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.2858,
            "delta_aic_units": 0.5715,
            "n": 1,
            "share": 0.0201
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1948,
            "delta_aic_units": 0.3895,
            "n": 1,
            "share": 0.0137
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1946,
            "delta_aic_units": 0.3892,
            "n": 1,
            "share": 0.0137
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1928,
            "delta_aic_units": 0.3857,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1927,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1927,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1927,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1927,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1927,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1927,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1926,
            "delta_aic_units": 0.3853,
            "n": 1,
            "share": 0.0136
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1899,
            "delta_aic_units": 0.3797,
            "n": 1,
            "share": 0.0134
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1737,
            "delta_aic_units": 0.3474,
            "n": 1,
            "share": 0.0122
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1724,
            "delta_aic_units": 0.3448,
            "n": 1,
            "share": 0.0121
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1579,
            "delta_aic_units": 0.3158,
            "n": 1,
            "share": 0.0111
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1289,
            "delta_aic_units": 0.2578,
            "n": 1,
            "share": 0.0091
          },
          {
            "group": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 0.1284,
            "delta_aic_units": 0.2568,
            "n": 1,
            "share": 0.009
          },
          {
            "group": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.04027,
            "delta_aic_units": -0.08053,
            "n": 1,
            "share": 0.0028
          },
          {
            "group": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.02584,
            "delta_aic_units": -0.05169,
            "n": 1,
            "share": 0.0018
          }
        ],
        "top": [
          {
            "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 2.133,
            "delta_aic_units": 4.266,
            "n": 1,
            "share": 0.1501
          },
          {
            "group": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.764,
            "delta_aic_units": 3.528,
            "n": 1,
            "share": 0.1241
          },
          {
            "group": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": 1.38,
            "delta_aic_units": 2.76,
            "n": 1,
            "share": 0.0971
          },
          {
            "group": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -1.115,
            "delta_aic_units": -2.229,
            "n": 1,
            "share": 0.0784
          },
          {
            "group": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.9095,
            "delta_aic_units": -1.819,
            "n": 1,
            "share": 0.064
          },
          {
            "group": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
            "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
            "condition": "cond_invitro_PTEFb_CTD8",
            "delta_nllh": -0.7233,
            "delta_aic_units": -1.447,
            "n": 1,
            "share": 0.0509
          }
        ],
        "groups_only_in_winner": [],
        "groups_only_in_rival": [],
        "worst_group_detail": {
          "group": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
          "points": [
            {
              "time": 60.0,
              "measured": 0.8977,
              "winner_sim": 0.9523,
              "rival_sim": 1.012,
              "delta_nllh": 2.133
            }
          ]
        }
      }
    ],
    "neutralisation": {
      "note": "no mechanism parameter on the winner declares a usable neutral_value, so no term was switched off \u2014 declared, never guessed",
      "refused": {},
      "parameters": {}
    },
    "axes_on": []
  },
  "estimated_inner": {}
}
```
## residual_diagnostics
```json
{
  "observation_evidence": {
    "for_model": "M5_neighbour_and_count",
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
    "M1_independent": {
      "sigma_vs_replicate_floor": [],
      "per_series": {
        "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.005166,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0052,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05233,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0523,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.2109,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.2109,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.232e-21,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1144,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.1144,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.2296,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.2296,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 3.955e-18,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.09986,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0999,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1712,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.1712,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 5.567e-15,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04714,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0471,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1978,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.1978,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 4.481e-12,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.115,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.115,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03544,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0354,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 2.255e-09,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.009431,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0094,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1479,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.1479,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 7.264e-07,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1669,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.1669,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1116,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.1116,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0001463,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04222,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0422,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.006105,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0061,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.01683,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0168,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02137,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0214,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0003489,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0003,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.004579,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0046,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        }
      },
      "note": "point-by-point fit omitted for this candidate; shape descriptors kept. Full curves are given for the selected model (M5_neighbour_and_count) and the base (M3_neighbour), and cross_model_by_measurement compares all of them."
    },
    "M2_count_coop": {
      "sigma_vs_replicate_floor": [],
      "per_series": {
        "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001575,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0016,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02899,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.029,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04567,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0457,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.919e-17,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03527,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0353,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05454,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0545,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 8.257e-16,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.01011,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0101,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1343,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.1343,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 2.359e-14,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03401,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.034,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05681,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0568,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 6.609e-13,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.004271,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0043,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.101,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.101,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 2.408e-11,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04431,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0443,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1348,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.1348,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.577e-09,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03617,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0362,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.08779,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0878,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 2.783e-07,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1276,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.1276,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0155,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0155,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0002044,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0002,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.09569,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0957,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001781,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0018,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001343,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0013,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        }
      },
      "note": "point-by-point fit omitted for this candidate; shape descriptors kept. Full curves are given for the selected model (M5_neighbour_and_count) and the base (M3_neighbour), and cross_model_by_measurement compares all of them."
    },
    "M3_neighbour": {
      "sigma_vs_replicate_floor": [],
      "per_series": {
        "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 0.0,
              "measured": 0.9996,
              "simulated": 0.9982,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001352,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0014,
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
              "simulated": 0.039,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0218,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0218,
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
              "simulated": 0.3879,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.005574,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0056,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
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
          "rmse": 1.946e-16,
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
              "simulated": 0.1608,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02969,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0297,
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
              "simulated": 0.8442,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05329,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0533,
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
              "simulated": -0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.102e-14,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
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
              "simulated": 0.3848,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.01417,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0142,
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
              "simulated": 1.012,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1148,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.1148,
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
          "rmse": 1.199e-13,
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
              "simulated": 0.6507,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02646,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0265,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "fit_over_time": [
            {
              "t": 60.0,
              "measured": 0.7797,
              "simulated": 0.8307,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.05107,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0511,
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
          "rmse": 1.23e-11,
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
              "simulated": 0.8315,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.004395,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0044,
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
              "simulated": 0.5006,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.09351,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0935,
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
          "rmse": 1.182e-09,
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
              "simulated": 0.8175,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03792,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0379,
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
              "simulated": 0.2257,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1267,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.1267,
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
          "rmse": 1.145e-07,
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
              "simulated": 0.6092,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0326,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0326,
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
              "simulated": 0.0746,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.08373,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0837,
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
              "simulated": 0.0,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 1.106e-05,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0,
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
              "simulated": 0.323,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1285,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.1285,
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
              "simulated": 0.0168,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.01683,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0168,
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
          "rmse": 0.0009558,
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
              "simulated": 0.103,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.103,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.103,
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
              "simulated": 0.0021,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.002079,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0021,
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
              "simulated": 0.8505,
              "residual_in_noise_units": null
            }
          ],
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001155,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0012,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        }
      }
    },
    "M4_processive": {
      "sigma_vs_replicate_floor": [],
      "per_series": {
        "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001565,
          "largest_deviation": {
            "at_time": 0.0,
            "signed_residual": 0.0016,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03194,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0319,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04755,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0475,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 8.428e-18,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03615,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0361,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.113,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.113,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 7.06e-15,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.008699,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0087,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.07712,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0771,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 2.69e-12,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.07387,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0739,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.07185,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0719,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 6.118e-10,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.03073,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.0307,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02112,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0211,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 9.144e-08,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.06441,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0644,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04241,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0424,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 9.293e-06,
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.08574,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": 0.0857,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02108,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": 0.0211,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0006384,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0006,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1009,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.1009,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.04994,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0499,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.02807,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": -0.0281,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
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
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.1447,
          "largest_deviation": {
            "at_time": 120.0,
            "signed_residual": -0.1447,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.0187,
          "largest_deviation": {
            "at_time": 60.0,
            "signed_residual": -0.0187,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "-",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        },
        "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8": {
          "abs_residual_vs_signal_corr": null,
          "n_timepoints": 1,
          "thinned_from": null,
          "rmse": 0.001425,
          "largest_deviation": {
            "at_time": 960.0,
            "signed_residual": 0.0014,
            "in_noise_units": null
          },
          "residual_sign_pattern_over_time": "+",
          "n_sign_runs": 1,
          "lag1_autocorr": null
        }
      },
      "note": "point-by-point fit omitted for this candidate; shape descriptors kept. Full curves are given for the selected model (M5_neighbour_and_count) and the base (M3_neighbour), and cross_model_by_measurement compares all of them."
    },
    "M5_neighbour_and_count": {
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
    }
  },
  "cross_model_by_measurement": [
    {
      "observable": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0014,
      "best_rmse": 0.0009,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.32,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0218,
      "best_rmse": 0.0095,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.566,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0056,
      "best_rmse": 0.0056,
      "best_model": "M3_neighbour",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 1.0,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0297,
      "best_rmse": 0.0264,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.11,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0533,
      "best_rmse": 0.0515,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.034,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 1.0,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0142,
      "best_rmse": 0.0087,
      "best_model": "M4_processive",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.386,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.1148,
      "best_rmse": 0.0546,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.524,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.954,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0265,
      "best_rmse": 0.0265,
      "best_model": "M3_neighbour",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0511,
      "best_rmse": 0.0446,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.127,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M2_count_coop",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.946,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0044,
      "best_rmse": 0.0043,
      "best_model": "M2_count_coop",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.028,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0935,
      "best_rmse": 0.0211,
      "best_model": "M4_processive",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.774,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M2_count_coop",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.98,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0379,
      "best_rmse": 0.0094,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.751,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.1267,
      "best_rmse": 0.0424,
      "best_model": "M4_processive",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.665,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M2_count_coop",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.986,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0326,
      "best_rmse": 0.0326,
      "best_model": "M3_neighbour",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.0,
      "verdict": "unimproved; no replicate floor available, so whether anything remains to fix is unknown",
      "unimproved_by_every_candidate": true
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0837,
      "best_rmse": 0.0211,
      "best_model": "M4_processive",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.748,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M2_count_coop",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.975,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.1285,
      "best_rmse": 0.0422,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.671,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0168,
      "best_rmse": 0.0061,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.637,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.001,
      "best_rmse": 0.0002,
      "best_model": "M2_count_coop",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.786,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0,
      "best_rmse": 0.0,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.103,
      "best_rmse": 0.0214,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.792,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0021,
      "best_rmse": 0.0003,
      "best_model": "M1_independent",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.832,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    },
    {
      "observable": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8",
      "condition": "cond_invitro_PTEFb_CTD8",
      "base_rmse": 0.0012,
      "best_rmse": 0.0008,
      "best_model": "M5_neighbour_and_count",
      "best_rmse_over_noise_floor": null,
      "improvement_vs_base": 0.32,
      "verdict": "improved by at least one candidate",
      "unimproved_by_every_candidate": false
    }
  ],
  "identical_prediction_controls": [],
  "residual_forms": {
    "per_series": [
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.091,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.2435,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.61,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.162e-13,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.6793,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.281,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -6.421e-13,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.527,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
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
        "model": "M5_neighbour_and_count",
        "series": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.68e-12,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.6857,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.11,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.313e-08,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.137,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.188,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -8.507e-06,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.5612,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.555,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.0009928,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
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
        "model": "M5_neighbour_and_count",
        "series": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.047,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.008301,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.007,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.3951,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.1181,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.255,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.05038,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M5_neighbour_and_count",
        "series": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.09112,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.1103,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.4531,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.1166,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.862e-14,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.617,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.114,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.054e-12,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.2944,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.401,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.147e-11,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.55,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.068,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.177e-09,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.09133,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.955,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.131e-07,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.788,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 2.649,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -1.096e-05,
        "amplitude_units": "sigma",
        "r2": 0.0,
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.6774,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 1.751,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.001058,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.67,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.352,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.09143,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.0,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -2.14,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": -0.04347,
        "amplitude_units": "sigma",
        "n": 1
      },
      {
        "model": "M3_neighbour",
        "series": "obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8@cond_invitro_PTEFb_CTD8",
        "attributes": {},
        "sigma_source": "fitted sigma",
        "form": "constant",
        "amplitude": 0.1105,
        "amplitude_units": "sigma",
        "n": 1
      }
    ],
    "summary": [
      "M5_neighbour_and_count (selected): residual of obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.091 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.24 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.6 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00000000000012 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.68 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.3 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00000000000064 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.5 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.4 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000000000017 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.69 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.1 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000000013 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.1 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.2 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000085 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.56 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.6 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00099 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.5 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0083 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.4 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.12 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.3 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.05 \u03c3 (1 series).",
      "M5_neighbour_and_count (selected): residual of obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.091 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.11 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.45 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.12 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000000000000019 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.62 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.1 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000000000011 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.29 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.4 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000000000011 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.55 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.1 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0000000012 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.091 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.00000011 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.79 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.6 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.000011 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.68 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 1.8 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.0011 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.7 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.35 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.091 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 2.1 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.043 \u03c3 (1 series).",
      "M3_neighbour (base): residual of obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8: no time shape; offset 0.11 \u03c3 (1 series)."
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
 "diagnosis": "Within the five fitted candidates, M5_neighbour_and_count is selected decisively. Its AIC is -166.40, its Akaike weight 0.9971, and the indistinguishable set is {M5_neighbour_and_count}. The others trail by ΔAIC 11.90 (M3_neighbour), 17.12 (M2_count_coop), 18.50 (M4_processive) and 55.69 (M1_independent); petab_select agrees.\n\nOBSERVATION MODEL AS FITTED. Each of the 36 cells is y_n(t_j) = sc_ctd_ms_tj * [CTD with n phosphates](t_j) + e, with e ~ N(0, (sigma_ctd_ms * sc_ctd_ms_tj)^2), on a linear scale. Each spectrum has one free scale: t0 0.009986, t60 0.03971, t120 0.03844 and t960 0.008519 per µM. These map 100 µM to 1.00/3.97/3.84/0.85, against measured sums of 1.00/4.07/3.79/0.85. One sigma_ctd_ms = 1.012 µM-equivalent is shared by every cell. Check: the phos5 1-h residual of 0.1027 equals 2.555 x 1.012 x 0.03971. Substrate conservation holds to 1e-13.\n\nWHY M5 WINS (attribution).\n- Against M1, the 1-h spectrum pays: phos1 3.27, phos3 2.63, phos0 2.29 and phos2 1.71 in -log L. An independent, homogeneous model must give a binomial, but the measured 1-h distribution is much broader. Measured phos0 is 0.394 against 0.183 predicted, and the variance is about 1.5x binomial at the same mean.\n- Against M2 and M3, the gain is in phos2 at 1 h (2.77, 2.13), phos4 at 1 h (1.49, 1.38) and phos7 at 2 h (1.32, 1.76). M5 gives back phos0 at 1 h and phos2/phos6 at 2 h.\n- Against M4, the gain is phos7 at 16 h (3.21; M4's slower base rate leaves 3% stuck at seven), phos1 at 1 h (1.70) and phos8 at 2 h (1.62; M4 predicts 0.145 where 0 was measured). M4 is better on the 1-h upper tail (phos5 -2.66, phos6 -1.73).\n\nThe data demand a distribution that is broad at 1 h, has an empty phos8 peak at 2 h, and is complete at 16 h. M5 gets there by pairing count acceleration (cp 1.588) with nb 0.314. If nb is a per-neighbour multiplicative factor with neutral value 1, like cp, this brakes the filling of flanked gaps late in the reaction.\n\nTWO LIMITS ON THIS RESULT.\n(i) Roughly half of every margin is sigma bookkeeping, not mechanism. The 18 cells at 0 h and 16 h are fitted to within noise by every model (19 measured values are exact zeros). Each adds log(sigma_rival/sigma_M5) to the winner: 0.193 per cell against M3, about 3.5 of its 6.95 Δ(-log L). On the 18 informative cells at 1 h and 2 h, the margin over M3 is about ΔAIC 5. That is still above 2, but the weight is nearer 0.9 than 0.997. Exact zeros are also not what the stated additive Gaussian noise produces.\n(ii) The neighbour term is seen only through the count distribution, and its value moves across neutral between models (nb 1.812 in M3, 0.314 in M5). What it buys in M5 is a step-rate profile that rises through mid-counts and brakes at the end, which M2's single cp cannot express. No count-only candidate with an equally flexible step-rate profile was fitted. So this round does not show that the effect is specifically about immediate neighbours.\n\nREMAINING STRUCTURE. The per-series shape tools are degenerate here: each peak x time is its own observable with n = 1, so sign runs, autocorrelation and residual_forms carry no shape. Read across counts within each spectrum, M5's largest residuals form one pattern:\n- the 1-h upper tail is underpredicted (phos5 +2.6 sigma, 0.352 vs 0.250; phos6 +2.0 sigma);\n- the 2-h top is overpredicted (phos8 -2.3 sigma, 0 vs 0.088; phos7 -2.0 sigma);\n- the 2-h low tail is heavier than any candidate gives (phos1 at 2 h is 0.191, against at most 0.164).\nThere are no replicates, sigma is fitted from these same residuals, and the noise check has n = 1 per cell. Absolute adequacy therefore cannot be judged; chi2/dof is about 1 by construction.\n\nIDENTIFIABILITY. The FIM spans 2.86 decades with no flat direction; its smallest eigenvector is sigma_ctd_ms. Profiles were not computed, so no intervals exist. The nested reductions still exceed the 1.92 profile threshold even if halved: M2 drops nb (Δ(-log L) 9.56) and M3 fixes cp = 1 (6.95). Both terms are therefore non-null within M5.\n\nANSWERS TO THE INTENT.\n- 'The rate depends on nothing at all' is rejected for a homogeneous substrate. Static substrate heterogeneity was not tried.\n- Count-only and neighbour-only each fall short of both together. Whether the second term is specifically an immediate-neighbour effect is not established.\n- Distributive vs processive: processivity alone (q_proc 0.2124) loses by ΔAIC 18.5, which is consistent with the by-eye call. But processivity was never combined with the coupling terms, and M4 fits the 1-h upper tail best. 'Distributive' therefore holds only against processivity alone.\n- Global effects cannot produce the non-binomial shape. These are ATP (3 mM with at most 0.8 mM consumed, K_ATP fixed at 50), kinase loss and product inhibition. They multiply every step equally and only re-time the trajectory.\n\nREVISE, with one move: fit a count-only candidate with a three-parameter step-rate profile and compare its -log L with M5's -91.20.",
 "misfit_hypotheses": [
  "1 (highest). The per-step rate profile is still wrong at the top of the distribution. M5 is too slow into the upper counts at 1 h: phos5 +2.6 sigma (0.352 vs 0.250) and phos6 +2.0 sigma (0.158 vs 0.076). It is too fast into them at 2 h: phos8 -2.3 sigma (measured 0 vs 0.088) and phos7 -2.0 sigma (0.195 vs 0.273). Every coupled or processive candidate predicts 0.088-0.145 for phos8 at 2 h; only M1 (0.021) does not. Yet completion by 16 h needs a final step faster than M4's base rate of 0.0052/min. This points at a step rate that rises through mid-counts and drops for the last one or two repeats. That could be a non-monotone count dependence, or one intrinsically slow repeat such as a construct-terminal one. cp-type acceleration plus nb only approximates it. A count-only candidate with a separate final-step factor would test it.",
  "2. The distribution broadens from the slow side, not by accelerating leaders. The 2-h low tail is heavier than every candidate gives: phos1 at 2 h is 0.191 measured vs 0.076-0.164 predicted, phos0 0.061 vs at most 0.051, and phos2 is +1.5 sigma under M5. Meanwhile the top end is empty. A slower substrate sub-population with independent sites broadens the distribution without populating phos7-phos8. That would be an alternative to cooperativity and would reopen 'the rate depends on nothing at all'. It needs two parameters (fraction and rate ratio) and is not in the candidate set.",
  "3. A processive component on top of the coupling terms. M4 is the best candidate on phos4/phos5/phos6 at 1 h (rmse 0.021/0.042/0.021 vs M5's 0.048/0.103/0.082). It fails mainly at the end: 0.145 for phos8 at 2 h, and 3% left at phos7 at 16 h. M5 with q_proc free was never fitted.",
  "4 (lowest). Observation layer. Equal MS response for every phospho-state is assumed and cannot be tested here. A monotone trend in response with phosphate number cannot both raise phos5-6 at 1 h and lower phos7-8 at 2 h, so it does not explain the main pattern. The 19 exact zeros behave as non-detections rather than Gaussian measurements. The phos8 zero at 2 h is not a detection artefact, though: phos0 at 2 h (0.061) was reported, which is below phos8's predicted 0.088. The zeros' main effect is on the size of the AIC margins, not on which model is selected."
 ],
 "cannot_distinguish": [
  "which repeats carry the phosphates: MS resolves only the count (0-8), so positional configurations, and any neighbour effect, are seen only through their imprint on the count distribution",
  "an immediate-neighbour effect versus a count-dependent rate with a more flexible profile than M2_count_coop's single cp: the nb term in M5 may be supplying a rise-then-brake step-rate profile, and no count-only candidate with three mechanism parameters was fitted",
  "the direction of the neighbour effect: nb = 1.812 in M3_neighbour but 0.314 in M5_neighbour_and_count, i.e. enhancing without the count term and (if 1 is its neutral value) inhibiting with it; its sign is conditional on how count dependence is modelled",
  "cooperativity between repeats versus static heterogeneity of the substrate (a slower sub-population with independent sites): both broaden the count distribution; no heterogeneous candidate was fitted, and the 2-h low tail (phos0-phos2) is heavier than every candidate predicts",
  "a processive contribution on top of count/neighbour coupling: M4_processive (q_proc 0.2124) was fitted only without coupling and is the best candidate on the 1-h phos4-phos6 peaks; q_proc was held at 0 in M5, not estimated",
  "count-dependent kinetics versus a count-dependent MS response (ionisation efficiency changing with phosphate number): the observation model assumes equal response for every phospho-state, and with single-species spectra at 0 h and 16 h and one free scale per spectrum this cannot be tested here",
  "whether M5's remaining residuals (largest 2.6 sigma, phos5 at 1 h) exceed measurement noise: there are no replicates, sigma_ctd_ms is fitted from the same residuals, and the 19 exact-zero cells pull it down"
 ],
 "nonetheless_determined": [
  "mechanism:M5_neighbour_and_count",
  "a homogeneous substrate whose repeats are modified independently at one rate is excluded: M1_independent ΔAIC 55.69 (Akaike weight 0.0), driven by the 1-h spectrum being broader than binomial (phos0 at 1 h 0.394 measured vs 0.183 predicted; phos1 0.898 vs 0.668); the margin is still about 27 on the 1-h and 2-h cells alone",
  "neither count cooperativity alone (M2_count_coop, ΔAIC 17.12) nor neighbour coupling alone (M3_neighbour, ΔAIC 11.90) accounts for the distributions; removing either term from M5 costs 9.56 or 6.95 in -log L for one parameter, above the 1.92 profile threshold even if halved for the sigma bookkeeping",
  "processivity without coupling (M4_processive, q_proc 0.2124) is excluded relative to M5: ΔAIC 18.50, Akaike weight 0.0001",
  "the intensity mapping: sc_ctd_ms_t0 0.009986, sc_ctd_ms_t60 0.03971, sc_ctd_ms_t120 0.03844, sc_ctd_ms_t960 0.008519, within about 5% across M2-M5 and reproducing the measured spectrum sums (1.00/3.97/3.84/0.85 vs 1.00/4.07/3.79/0.85)",
  "the reaction runs to completion within 16 h (phos8 at 16 h is 0.852 of a 0.852 spectrum; phos0-phos7 at 16 h are 0), and the non-binomial shape cannot come from ATP depletion (at most 0.8 of 3 mM consumed), product inhibition or kinase loss, which multiply every step alike and only re-time the trajectory"
 ],
 "answers_intent": [
  {
   "criterion": "the selected mechanism is reported with its information criterion, its Akaike weight and the indistinguishable set, honestly, whatever they turn out to be",
   "verdict": "pass",
   "evidence": "M5_neighbour_and_count: AIC -166.40, Akaike weight 0.9971, indistinguishable set {M5_neighbour_and_count} at the ΔAIC threshold of 2. Next are M3 11.90, M2 17.12, M4 18.50 and M1 55.69; the petab_select 0.4.0 cross-check agrees. Honest reading: about 3.5 of the 6.95 Δ(-log L) over M3 comes from the 18 cells at 0 h and 16 h, which every model fits identically and which add 0.193 each through the shared sigma. On the 1-h and 2-h cells alone, ΔAIC to M3 is about 5. The set stays {M5}, but the weight is nearer 0.9. The set is relative to five hand-built candidates with no lattice; heterogeneity, M5 with processivity, and flexible count profiles were not tried."
  },
  {
   "criterion": "the observation model is stated explicitly, including how predicted amounts are mapped onto relative MS intensities at each time point",
   "verdict": "pass",
   "evidence": "The model is y_n(t_j) = sc_ctd_ms_tj * [CTD_n](t_j) + N(0, (sigma_ctd_ms * sc_ctd_ms_tj)^2), on a linear scale, matching the lab note's description of noise that scales with each spectrum. The scales are t0 0.009986, t60 0.03971, t120 0.03844 and t960 0.008519 per µM, with sigma_ctd_ms 1.012. Residuals confirm the mapping (0.1027 = 2.555 sigma at 1 h), and substrate conservation drift is 1.4e-13. Not tested: equal MS response for every phospho-state."
  },
  {
   "criterion": "any mechanistic question the data cannot resolve is named as unresolved rather than decided",
   "verdict": "partial",
   "evidence": "computed_cannot_distinguish is empty and the FIM has no flat direction, so the round itself names nothing as unresolved. The open questions are structural, not parametric: positional arrangement is unobserved; nb moves from 1.812 (M3) to 0.314 (M5); no count-only candidate has a comparably flexible step-rate profile; there is no heterogeneous-substrate candidate; processivity was never combined with coupling; and equal MS response is assumed. These are named in cannot_distinguish here. Accepted as is, however, the selection would present the neighbour term as established."
  },
  {
   "criterion": "intent test: neighbour effect vs count cooperativity vs no dependence, and which the data can separate",
   "verdict": "partial",
   "evidence": "'Nothing at all' is rejected for a homogeneous substrate (M1 ΔAIC 55.69, driven by the 1-h spectrum). Both terms are needed given each other (Δ(-log L) 9.56 and 6.95 for one parameter each). Neighbour-only edges count-only by ΔAIC 5.2, about half of which is sigma bookkeeping. The data do not establish that the second term is specifically an immediate-neighbour effect rather than a more flexible count dependence or substrate heterogeneity."
  },
  {
   "criterion": "intent test: the by-eye conclusion that P-TEFb is distributive rather than processive",
   "verdict": "partial",
   "evidence": "Processivity alone (M4, q_proc 0.2124) loses to the distributive winner by ΔAIC 18.50 (weight 0.0001), which is consistent with the by-eye conclusion. That loss is paid mainly at the end of the reaction: phos7 at 16 h (3.21) and phos8 at 2 h (1.62). M4 is the best candidate on the 1-h phos4-phos6 peaks. q_proc was held at 0 in M5 rather than estimated, so a processive component alongside coupling remains untested."
  }
 ],
 "recommendation": "revise"
}
````
