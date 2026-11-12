# Prompt · `observation` (round 0)

The **observation** agent maps model states onto what the instrument measures (S3). Below is the exact prompt it was sent in this run (70,915 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 2 times here; the record keeps the prompt and reply of the last call.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Observation model: write the whole observation function for every measured quantity

For each readout you write `y = sc · g(x) + off + ε` as one decision: the model expression, the scale on which the
error is additive, the noise distribution and sigma, and whether a scale factor, an offset, both or neither is
needed. You map, weight and compose; you do not calibrate. It is one decision because its seams (transformation
against noise, scaling against transformation) are judgments no gate can check, so the rationale argues the whole
triple from the measurement process.

## What you receive
`model_summary`, `entity_glossary` (what each species denotes, its unit convention, what it lumps), `data_labels`
(label, units, `error_type`), `experiment_description` (the lab note, naming the assay), `intent`, `domain_packs`,
`data_signals` (the replicates' own read on the error model: noise slope, `support`, `data_signals.below_detection`,
`processing_applied`) and, when papers were staged, `supplied_literature`. Never raw values: the signals are the same
evidence without the temptation to read a curve as a mechanism.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`observables`, required, one per measured quantity; optional `model_space`. Shapes, fixed and per-row sigmas,
instrument links and spelling are in the Output contract. A reply the engine cannot render is re-asked by name, and
a failed check comes back as `battery_feedback`.

## Rules that get your reply refused
- **A log transformation is a multiplicative-noise claim.** Decide transformation and distribution together, keep
  `lin` unless the measurement process argues otherwise, and never log data that can be zero or negative.
- **A free scale factor on absolutely calibrated data is an exact flat direction**: the fit trades the initial amount
  against the scale and the profile is unbounded. Calibrated real units get `mode: none`; relative, normalised or
  arbitrary units always get a scale factor. The glossary's unit convention says which case you are in.
- `formula` names only model species and parameters, as the data tabulate the quantity, with no gain, offset, `/max`
  or normalisation: the scaling block owns those. Two states the assay cannot resolve are summed, and the rationale
  says so. `maps_to_label` is exactly one data label; one observable per measured quantity. Write the formula in
  the species yourself: a rule the model defines only to re-express a readout, with a response factor or a gain,
  is the model's copy of your job, and its parameter is not yours to estimate. Naming a rule is legal, since the
  engine expands every rule a formula carries into species before the compile, but the observation model is
  declared here, once.
- Every observable declares a distribution and a sigma, and its rationale names the readout technique: "normal
  because it usually is" is not a reason.
- `error_type: sem` is not sigma: the likelihood needs an SD (`sd = sem·√n`), hence `n`; without it, say so and
  estimate sigma.

## How to judge
**Noise shape.** Four shapes; each non-model symbol becomes its own noise parameter, up to three. **Constant**
`sigma_obs_x` when spread does not follow magnitude. **Proportional** `sigma_obs_x * <this observable's signal
expression>` falls to zero with the signal, so it is wrong for any readout that reaches zero. **Additive +
proportional** `sigma_abs + sigma_rel * <this observable's signal expression>`, both estimated, is the standard
answer for data containing zeros (mass-spec intensities, background-subtracted fluorescence), which
`data_signals.support` reports as "a log transform is NOT legal". The signal expression is this observable's own
formula, with or without `sc_obs_x`: the noise reaches the model only through this observable's prediction, and a
sigma on any other state is refused and re-asked. Assignment-rule symbols are fine; the engine expands them. **Gain-scaled** `sc_obs_x * sigma_obs_x` gives each row its own gain's sigma: pair
it with a per-acquisition gain, which multiplies signal and noise alike, unless the error floor is fixed. `noise.per:
condition` gives each condition its own sigma (all counted in k; a held-out condition's is fixed) when replicate
spread differs between arms in a way no signal-dependent shape explains (control at 0.1–0.3 log2, stimulated at
0.5–1.3), cited from `data_signals`. It reweights residuals and never moves the prediction; a gain-scaled
per-condition factor is no substitute, since on log-scale data it is an offset degenerate with the basal rates.

**At the floor, and beyond normal.** With `data_signals.below_detection` there is no censored likelihood: choose a
shape honest at the floor (a constant or additive part, never pure proportional or a log where imputed values sit)
and say the fit is conditional on the source's handling. Count data are not normal and no count model exists: flag
it so someone decides knowingly. When unsure, take normal with an estimated sigma and say what you were unsure of.
Add no scale or offset on top of a step `processing_applied` says the table already had.

**Scaling and offset.** Ask: if every model concentration doubled, would this number double? If so and it has no
absolute meaning, it needs a scale factor. Share it across conditions by default, since sharing is what lets the data
constrain relative amplitudes between doses, and scale per condition only for something the experimentalist did
(separate gels, plates, days). An offset needs a physically argued background (unsubtracted background,
autofluorescence, a nonzero blank, an instrument floor), never a better fit. Name them `sc_obs_x` and `off_obs_x`.
Scaling `per` is `observable`, `timepoint` (a gain drifting between acquisitions) or `condition`;
`shared_across_observables: "<group>"` gives one acquisition's readouts one parameter set (members agree on `per`,
`mode`, `pin_first_to_one`), and the engine writes the ids. With every factor free the absolute scale needs a fixed
model total (an unestimated initial amount the glossary names) or `pin_first_to_one: true` (the usual choice when a
reference acquisition defines the scale): name which, or the identifiability screen will show the flat direction. In
log space a scale factor is an offset: choosing both, say why both are identifiable. Offsets, scalings and the
model's totals trade off, so on short, noisy series prefer scaling alone.

**Mapping.** Ask what ends up on the membrane or in the well. A total readout sums exactly the states the glossary
says the protein occupies, a site-specific one a subset, a reporter is a proxy that often lags, and a ratio readout
maps to the ratio of model expressions. A glossary convention of "absolute concentration" or "normalised to 1 against
a calibrated total" argues against a free scale; a parameter "set per condition" is not yours to scale. Cite the
entries you used, or say the mapping is from structure alone. Model in amounts, assay in concentration: the volume
goes in the formula, not in a scale factor. Check magnitude: nM against µM passes every referential check and fails
reconciliation downstream.

**Assays.** Immunoblot densitometry after loading-control normalisation is usually additive normal on the linear
scale, unless the error grows with signal. Fluorescence, luminescence and MS intensities are usually multiplicative:
log with normal noise, if strictly positive. A calibrated readout with a stated precision may take a fixed sigma
from it; say where it came from. One sigma per observable, shared across conditions unless the assay or protocol
changed, never across assays. Laplace suits a technique with known sporadic outliers (name it), not an outlier you
want to stop mattering.

**Evidence.** `direct`: a source states what the probe targets or names the assay; `transferred`: the same technique
in a related system; `default`: inferred from the label, and a label called `pERK` is evidence of nothing.
`supplied_literature` carries the measurement facts of a methods section (assay, target, units and whether absolute,
detection floor, replicate design, where the error is additive): let them decide where the lab note is silent, cite
the `id`, attribute nothing beyond `supports` and `quote`, and call another assay or cell type `transferred`.

**Axes.** Two defensible observation functions (not a better and a worse) make an axis, not a choice on taste; when
the measurement process decides, choose. `on_assembly_patch` has exactly one kind as its key, and any other shape
comes back with the legal kinds: `change_observable_formula`, `change_noise_model` (including `new_per: condition`),
`add_offset`, `remove_scaling`, `change_scaling`, `change_condition`, and `change_transformation`, which is
refused until the criterion can compare across scales. Name the observable by `observable_id` or `observable_label`
(`observable_ids` for a group under `change_scaling`). `split_parameter` is the expansion agent's.

## Mistakes we have seen
- A species named as in the paper instead of by model id; a phospho readout mapped to the total pool; a "total"
  missing a state the glossary lists.
- A scale, offset or normalisation folded into `formula`.
- A log chosen because the data span decades while the noise is called additive.
- An error column used as sigma without checking `error_type`: SEM taken for SD mis-weights every point by √n.
- A log or pure proportional noise on data with zeros, negatives or background subtraction.
- The distribution that improved the fit rather than the one the technique implies.
- A scale factor on calibrated data; `mode: none` on arbitrary units because the magnitudes looked close; reflexive
  per-condition scaling.
- An offset on immunoblots whose loading control is already divided out, one free to go negative, or one absorbing
  an early-time misfit, which is a diagnosis for evaluation, not a parameter.
- A scale parameter duplicating a model parameter's role (a total already estimated).
- A rationale that paraphrases the triple instead of naming the assay, what it detects, where its error is additive
  and whether its units are absolute.


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

## model_summary
```json
{
  "species": [
    "CTD_0",
    "CTD_1",
    "CTD_2",
    "CTD_3",
    "CTD_4",
    "CTD_5",
    "CTD_6",
    "CTD_7",
    "CTD_8",
    "ATP",
    "ADP",
    "PTEFb"
  ],
  "parameters": [
    "kmod",
    "cp",
    "q_proc",
    "K_ATP"
  ],
  "assignment_rules": [],
  "assignment_rule_formulas": {},
  "reactions": [
    {
      "id": "J0",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * (1 - q_proc) * CTD_0"
    },
    {
      "id": "J1",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * (1 - q_proc) * CTD_1"
    },
    {
      "id": "J2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 6 * pow(cp, 2) * (1 - q_proc) * CTD_2"
    },
    {
      "id": "J3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 5 * pow(cp, 3) * (1 - q_proc) * CTD_3"
    },
    {
      "id": "J4",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 4 * pow(cp, 4) * (1 - q_proc) * CTD_4"
    },
    {
      "id": "J5",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 3 * pow(cp, 5) * (1 - q_proc) * CTD_5"
    },
    {
      "id": "J6",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 2 * pow(cp, 6) * (1 - q_proc) * CTD_6"
    },
    {
      "id": "J7",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * pow(cp, 7) * CTD_7"
    },
    {
      "id": "Jp0_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * q_proc * (1 - q_proc) * CTD_0"
    },
    {
      "id": "Jp0_3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * pow(q_proc, 2) * (1 - q_proc) * CTD_0"
    },
    {
      "id": "Jp0_4",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * pow(q_proc, 3) * (1 - q_proc) * CTD_0"
    },
    {
      "id": "Jp0_5",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * pow(q_proc, 4) * (1 - q_proc) * CTD_0"
    },
    {
      "id": "Jp0_6",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * pow(q_proc, 5) * (1 - q_proc) * CTD_0"
    },
    {
      "id": "Jp0_7",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * pow(q_proc, 6) * (1 - q_proc) * CTD_0"
    },
    {
      "id": "Jp0_8",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 8 * pow(q_proc, 7) * CTD_0"
    },
    {
      "id": "Jp1_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * q_proc * (1 - q_proc) * CTD_1"
    },
    {
      "id": "Jp1_3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * pow(q_proc, 2) * (1 - q_proc) * CTD_1"
    },
    {
      "id": "Jp1_4",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * pow(q_proc, 3) * (1 - q_proc) * CTD_1"
    },
    {
      "id": "Jp1_5",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * pow(q_proc, 4) * (1 - q_proc) * CTD_1"
    },
    {
      "id": "Jp1_6",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * pow(q_proc, 5) * (1 - q_proc) * CTD_1"
    },
    {
      "id": "Jp1_7",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 7 * cp * pow(q_proc, 6) * CTD_1"
    },
    {
      "id": "Jp2_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 6 * pow(cp, 2) * q_proc * (1 - q_proc) * CTD_2"
    },
    {
      "id": "Jp2_3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 6 * pow(cp, 2) * pow(q_proc, 2) * (1 - q_proc) * CTD_2"
    },
    {
      "id": "Jp2_4",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 6 * pow(cp, 2) * pow(q_proc, 3) * (1 - q_proc) * CTD_2"
    },
    {
      "id": "Jp2_5",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 6 * pow(cp, 2) * pow(q_proc, 4) * (1 - q_proc) * CTD_2"
    },
    {
      "id": "Jp2_6",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 6 * pow(cp, 2) * pow(q_proc, 5) * CTD_2"
    },
    {
      "id": "Jp3_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 5 * pow(cp, 3) * q_proc * (1 - q_proc) * CTD_3"
    },
    {
      "id": "Jp3_3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 5 * pow(cp, 3) * pow(q_proc, 2) * (1 - q_proc) * CTD_3"
    },
    {
      "id": "Jp3_4",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 5 * pow(cp, 3) * pow(q_proc, 3) * (1 - q_proc) * CTD_3"
    },
    {
      "id": "Jp3_5",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 5 * pow(cp, 3) * pow(q_proc, 4) * CTD_3"
    },
    {
      "id": "Jp4_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 4 * pow(cp, 4) * q_proc * (1 - q_proc) * CTD_4"
    },
    {
      "id": "Jp4_3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 4 * pow(cp, 4) * pow(q_proc, 2) * (1 - q_proc) * CTD_4"
    },
    {
      "id": "Jp4_4",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 4 * pow(cp, 4) * pow(q_proc, 3) * CTD_4"
    },
    {
      "id": "Jp5_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 3 * pow(cp, 5) * q_proc * (1 - q_proc) * CTD_5"
    },
    {
      "id": "Jp5_3",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 3 * pow(cp, 5) * pow(q_proc, 2) * CTD_5"
    },
    {
      "id": "Jp6_2",
      "formula": "vial * kmod * PTEFb * ATP / (K_ATP + ATP) * 2 * pow(cp, 6) * q_proc * CTD_6"
    }
  ],
  "nominal_magnitudes": {
    "per_species": {
      "CTD_0": {
        "min": 2.3219911443827552e-31,
        "median": 4.677538779383904e-15,
        "max": 100.0
      },
      "CTD_1": {
        "min": 0.0,
        "median": 2.1152235866379413e-12,
        "max": 37.2179294368137
      },
      "CTD_2": {
        "min": 0.0,
        "median": 8.868032470931939e-10,
        "max": 31.138348881972455
      },
      "CTD_3": {
        "min": 0.0,
        "median": 2.1245323364413671e-07,
        "max": 28.162667562968284
      },
      "CTD_4": {
        "min": 0.0,
        "median": 3.18112610874371e-05,
        "max": 27.22072796933103
      },
      "CTD_5": {
        "min": 0.0,
        "median": 0.0030484492909529266,
        "max": 28.061819510226787
      },
      "CTD_6": {
        "min": 0.0,
        "median": 0.1265042726896213,
        "max": 31.11705285534843
      },
      "CTD_7": {
        "min": 0.0,
        "median": 3.3313658952697507,
        "max": 39.26797142680335
      },
      "CTD_8": {
        "min": 0.0,
        "median": 92.95227926746011,
        "max": 99.93341247184647
      },
      "ATP": {
        "min": 2200.066606934554,
        "median": 2207.275113595904,
        "max": 3000.0
      },
      "ADP": {
        "min": 0.0,
        "median": 792.7248864040969,
        "max": 799.9333930654469
      },
      "PTEFb": {
        "min": 1.0,
        "median": 1.0,
        "max": 1.0
      }
    },
    "caveat": "simulated at NOMINAL parameters, which are placeholders \u2014 a mismatch of orders of magnitude against the data's support is weak evidence for a scaling parameter, a unit mismatch, or nothing at all. It informs your scaling block; the engine does not block on it, because a magnitude alone cannot tell those three apart."
  }
}
```
## entity_glossary
```json
{
  "species": [
    {
      "id": "CTD_0",
      "denotes": "CTD constructs (8 heptarepeats) with no repeat phosphorylated; maps to readout phos0_rel",
      "unit_convention": "uM; total over CTD_0..CTD_8 is 100 uM",
      "lump_membership": "the single configuration with no marks"
    },
    {
      "id": "CTD_1",
      "denotes": "CTD with exactly 1 of 8 repeats phosphorylated (Ser2 or Ser5, one bit per repeat); maps to phos1_rel",
      "unit_convention": "uM",
      "lump_membership": "all 8 configurations with one mark"
    },
    {
      "id": "CTD_2",
      "denotes": "CTD with exactly 2 repeats phosphorylated; maps to phos2_rel",
      "unit_convention": "uM",
      "lump_membership": "all 28 configurations with two marks"
    },
    {
      "id": "CTD_3",
      "denotes": "CTD with exactly 3 repeats phosphorylated; maps to phos3_rel",
      "unit_convention": "uM",
      "lump_membership": "all 56 configurations with three marks"
    },
    {
      "id": "CTD_4",
      "denotes": "CTD with exactly 4 repeats phosphorylated; maps to phos4_rel",
      "unit_convention": "uM",
      "lump_membership": "all 70 configurations with four marks"
    },
    {
      "id": "CTD_5",
      "denotes": "CTD with exactly 5 repeats phosphorylated; maps to phos5_rel",
      "unit_convention": "uM",
      "lump_membership": "all 56 configurations with five marks"
    },
    {
      "id": "CTD_6",
      "denotes": "CTD with exactly 6 repeats phosphorylated; maps to phos6_rel",
      "unit_convention": "uM",
      "lump_membership": "all 28 configurations with six marks"
    },
    {
      "id": "CTD_7",
      "denotes": "CTD with exactly 7 repeats phosphorylated; maps to phos7_rel",
      "unit_convention": "uM",
      "lump_membership": "all 8 configurations with seven marks"
    },
    {
      "id": "CTD_8",
      "denotes": "CTD with all 8 repeats phosphorylated; maps to phos8_rel",
      "unit_convention": "uM",
      "lump_membership": "the single fully marked configuration"
    },
    {
      "id": "ATP",
      "denotes": "ATP in the reaction buffer; one consumed per repeat modified",
      "unit_convention": "uM, 3000 at t = 0",
      "lump_membership": ""
    },
    {
      "id": "ADP",
      "denotes": "ADP produced by phosphoryl transfer; not observed, kept for mass balance",
      "unit_convention": "uM, 0 at t = 0",
      "lump_membership": ""
    },
    {
      "id": "PTEFb",
      "denotes": "P-TEFb (CDK9/cyclin T1) kinase; catalytic modifier, never consumed",
      "unit_convention": "relative units fixed at 1; absolute concentration absorbed into kmod",
      "lump_membership": "free and substrate-bound kinase together (encounters are fast relative to sampling)"
    }
  ],
  "parameters": [
    {
      "id": "kmod",
      "role": "per-repeat modification rate per unit kinase at saturating ATP",
      "convention": "1/min; a molecule with n marks advances at (8 - n)*cp^n*kmod*PTEFb*ATP/(K_ATP + ATP)",
      "set_per_condition": false
    },
    {
      "id": "cp",
      "role": "count-cooperativity switch: fold change of the per-repeat rate per mark already on the molecule",
      "convention": "neutral value 1 (off in base); log-scale bounds 0.2 to 5",
      "set_per_condition": false
    },
    {
      "id": "q_proc",
      "role": "processivity switch: probability the kinase modifies another repeat before releasing",
      "convention": "neutral value 0 (strictly distributive in base); bounds 1e-4 to 0.99 when switched on",
      "set_per_condition": false
    },
    {
      "id": "K_ATP",
      "role": "ATP half-saturation constant of the kinase",
      "convention": "uM, fixed at 50; ATP stays saturating",
      "set_per_condition": false
    },
    {
      "id": "vial",
      "role": "reaction volume compartment",
      "convention": "1; species are concentrations in uM",
      "set_per_condition": false
    }
  ]
}
```
## data_labels
```json
{
  "observable_labels": [
    {
      "label": "CTD_phos0_rel",
      "description": "Relative MS signal of the intact 8-heptarepeat CTD construct carrying 0 phosphates (no repeat modified). Relative intensity on a per-injection arbitrary scale; not comparable across time points without a per-time-point scale factor.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos1_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 1 phosphate (1 of 8 repeats modified, any position; position not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos2_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 2 phosphates (2 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos3_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 3 phosphates (3 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos4_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 4 phosphates (4 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos5_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 5 phosphates (5 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos6_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 6 phosphates (6 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos7_rel",
      "description": "Relative MS signal of CTD molecules carrying exactly 7 phosphates (7 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    },
    {
      "label": "CTD_phos8_rel",
      "description": "Relative MS signal of fully phosphorylated CTD molecules (all 8 repeats modified; Ser2/Ser5 mutually exclusive per repeat, so 8 is the maximum). Per-injection arbitrary scale.",
      "units": "arbitrary",
      "error_type": "none",
      "n": 1
    }
  ],
  "condition_labels": [
    "invitro_PTEFb_CTD8"
  ],
  "maps_to_label_must_be_one_of": [
    "CTD_phos0_rel",
    "CTD_phos1_rel",
    "CTD_phos2_rel",
    "CTD_phos3_rel",
    "CTD_phos4_rel",
    "CTD_phos5_rel",
    "CTD_phos6_rel",
    "CTD_phos7_rel",
    "CTD_phos8_rel"
  ]
}
```
## domain_packs
```json
{
  "general-dynamics": "# general-dynamics \u2014 pitfalls\n\n`draft-unreviewed`. Eight entries. Each is a claim an expert should confirm, edit or delete individually;\na pack returned with no edits has not been reviewed.\n\n---\n\n### 1 \u00b7 Bounds spanning too few decades strangle multistart\n\n**Pitfall** \u2014 Bounds set as a tight cordon around a nominal value (half an order of magnitude either side)\nlook careful and are not. Multistart then samples a box that may not contain the optimum at all.\n\n**Why it matters** \u2014 The optimiser converges tidily, the waterfall shows a clean plateau, and one or more\nparameters sit against a bound. The result reads as a converged fit and is an artefact of the box. The\nopposite error \u2014 ten decades on every parameter \u2014 wastes starts in regions where the model is stiff or\nnon-integrable and makes the integration-failure fraction the binding constraint.\n\n**How to apply** \u2014 construction: 2\u20134 decades around a defensible nominal is the working default; widen where\nthe nominal is `default`-tier, narrow where it is measured. interpretation: a parameter at a\nbound is a statement about the bound. revision_proposal: `change_bounds` is the right move only when the\nbound was a guess, not when it encodes a physical limit.\n\n_Reviewed: \u2014_\n\n---\n\n### 2 \u00b7 Rate constants belong on a log scale\n\n**Pitfall** \u2014 Estimating rate constants on a linear scale when their plausible range spans decades.\n\n**Why it matters** \u2014 Linear-scale sampling puts almost every start in the top decade of the range; the\nlower decades are effectively unexplored. Gradients are equally distorted, and step sizes that suit one\nparameter are useless for another three decades away.\n\n**How to apply** \u2014 Rate constants, concentrations, and scaling factors are `log10`-scaled by default;\nadditive offsets and quantities that can legitimately be zero or negative stay `lin`. Bounds are still\nwritten as linear-scale values \u2014 the scale field, not the bound field, carries this.\n\n_Reviewed: \u2014_\n\n---\n\n### 3 \u00b7 The data window must bracket the dynamics you claim to estimate\n\n**Pitfall** \u2014 Estimating a rate whose characteristic time falls outside the interval the data actually\ncovers: a degradation rate from data ending long before anything degrades, or a fast association from data\nwhose first point is at 5 min.\n\n**Why it matters** \u2014 The parameter is not slightly uncertain, it is unconstrained, and the fit will not say\nso. Whatever value the optimiser lands on is arbitrary within a wide range and will be reported with\nconfidence unless a profile is computed.\n\n**How to apply** \u2014 construction: before marking a parameter for estimation, ask which part of the data\nconstrains it. If none, expect it in `cannot_distinguish` and consider fixing it. interpretation:\na flat profile on a rate whose timescale sits outside the data window is expected, not a surprise to explain\naway.\n\n_Reviewed: \u2014_\n\n---\n\n### 4 \u00b7 Conserved totals silently pin states\n\n**Pitfall** \u2014 A moiety conservation the modeller did not intend \u2014 usually from writing only interconversion\nreactions with no synthesis or degradation \u2014 fixes a total and therefore pins the accessible state space.\n\n**Why it matters** \u2014 The model then cannot respond to the perturbation in the way the question asks about,\nand this shows up as a stubborn misfit that invites structural moves. Meanwhile the initial values of the\nconserved set become a single parameter's worth of information, so estimating them all is a structural\nnon-identifiability.\n\n**How to apply** \u2014 construction: read the conservation-law advisory and confirm each class is intended. If a\ntotal is conserved by design, estimate the total and the fractions, not every state's initial value.\nevaluation_interpretation: check conservation before diagnosing a missing reaction.\n\n_Reviewed: \u2014_\n\n---\n\n### 5 \u00b7 Relative data needs one scale fixed somewhere\n\n**Pitfall** \u2014 With arbitrary-unit data, the model's absolute concentrations and the observable's scaling\nfactor are only determined as a product. Estimating both freely leaves a perfectly flat direction.\n\n**Why it matters** \u2014 The likelihood is invariant along that direction, so the optimiser wanders, profiles\nrun flat in both parameters, and the diagnosis reads as \"the data is uninformative\" when in fact the\ninformation is there and the parameterisation is redundant.\n\n**How to apply** \u2014 Fix one scale: a known total protein amount, an initial condition set to 1, or a scaling\nfactor fixed to 1 for one observable. Then say in the report that concentrations are relative to that\nchoice. observation (scaling) and construction must not both leave the scale free.\n\n_Reviewed: \u2014_\n\n---\n\n### 6 \u00b7 Parameters at bounds after fitting are a finding, not a formality\n\n**Pitfall** \u2014 Recording \"converged\" while one or more estimates rest on their bounds.\n\n**Why it matters** \u2014 A parameter at a bound means the data wants a value the box forbids. Every uncertainty\nstatement about it is then wrong \u2014 the profile is truncated, the CI is an artefact of the box, and any\nprediction depending on it inherits that. It is also the most common way a genuine model error disguises\nitself as a converged fit.\n\n**How to apply** \u2014 interpretation: name every at-bound parameter and say whether widening is\nhonest (the bound was a guess) or whether the model is fighting a physical limit. revision_proposal: only\nthe first case justifies `change_bounds`.\n\n_Reviewed: \u2014_\n\n---\n\n### 7 \u00b7 Estimate the combination the data sees, not the pair\n\n**Pitfall** \u2014 Estimating `k_on` and `k_off` separately when the data only ever sees equilibrium binding, or\na synthesis and a degradation rate when the data only sees the steady-state ratio.\n\n**Why it matters** \u2014 The pair is unidentifiable but their combination (`Kd`, the steady-state level) may be\ntightly determined. Reporting two flat parameters hides a sharp result; reporting them as independently\nestimated values overclaims two numbers where the data supports one.\n\n**How to apply** \u2014 construction: where binding is fast relative to the data's resolution, parameterise by\n`Kd` directly. interpretation: put the pair in `cannot_distinguish` and the determined\ncombination in `nonetheless_determined` \u2014 both directions, in the same report.\n\n_Reviewed: \u2014_\n\n---\n\n### 8 \u00b7 Stiffness shows up where the optimiser goes, not where you tested\n\n**Pitfall** \u2014 A model that integrates cleanly at nominal parameters and fails across large parts of its own\nbounds box.\n\n**Why it matters** \u2014 Failed starts are dropped rather than counted, so the surviving starts form a plateau\nthat reads as convergence. It is survivorship: the \"converged\" region is simply the region where the solver\ndid not die, and it may exclude the optimum entirely.\n\n**How to apply** \u2014 construction: check integrability at sampled corners of the bounds box, not just at\nnominals; a denominator that can approach zero or an exponential of an unbounded expression is the usual\nculprit. interpretation: read the integration-failure fraction before reading the waterfall.\n\n_Reviewed: \u2014_\n\n\n# Reaction templates\n<!-- provenance: Jan Hasenauer, Octomod v0 agent specification (2026).\n     Human-curated lineage \u2014 inherit verbatim, extend only with curated content. -->\n\nStandard forms; prefer these over invented constructs, and name the template\nused in the decision rationale.\n\n- Synthesis: `\u2205 -> X` (zero-order or regulated rate)\n- Degradation: `X -> \u2205` (first-order unless evidence says otherwise)\n- Reversible binding: `A + B <-> A_B`\n- Enzymatic conversion: `S -> P` with enzyme `E` as MODIFIER\n  (Michaelis-Menten when QSS holds at the declared timescale)\n- Phosphorylation: `X -> X_p` with kinase as modifier\n- Dephosphorylation: `X_p -> X` with phosphatase as modifier\n- Transport: `X_c1 -> X_c2` (compartments explicit)\n- Transcriptional activation: regulator modifies mRNA synthesis rate\n- Translation: `mRNA -> mRNA + protein` (or simplified synthesis term)\n- Inhibition: inhibitor enters as a MODIFIER in the rate law \u2014 never as a\n  consumed reactant unless it is mechanistically consumed\n- Distinct species for: compartments, PTM states, activity states,\n  bound/unbound forms, complexes \u2014 whenever the distinction affects dynamics\n- Preserve mass balance for metabolites and binding; when a signalling-state\n  model simplifies it deliberately, SAY SO in the build report\n",
  "measurement-tech": "# measurement-tech \u2014 pitfalls\n\n`draft-unreviewed`. Eight entries. Each is a claim an expert should confirm, edit or delete individually;\na pack returned with no edits has not been reviewed.\n\n---\n\n### 1 \u00b7 The loading control has usually already been divided out\n\n**Pitfall** \u2014 Adding an offset to immunoblot data on the assumption that the background is still in there.\nIn most published quantifications the signal has already been normalised to a loading control\n(actin, tubulin, total protein), and often to a reference lane as well.\n\n**Why it matters** \u2014 An unnecessary offset is a free parameter that absorbs real dynamics, most visibly at\nearly timepoints where the model's baseline carries information. It fits better and identifies less, and\nnothing downstream announces it.\n\n**How to apply** \u2014 observation (scaling): for normalised blot data the default is a scaling factor with no offset.\nAdd an offset only where the description states that background was not subtracted, or where blank lanes are\nreported as nonzero. assembly_verification: an offset on normalised blot data with no stated background story is a\nconcern.\n\n_Reviewed: \u2014_\n\n---\n\n### 2 \u00b7 Densitometry saturates \u2014 the top of the range is censored\n\n**Pitfall** \u2014 Treating the highest signals on a blot as ordinary measurements. Film and, at high exposure,\ndigital detection compress the top of the range: the true signal keeps rising and the recorded one does not.\n\n**Why it matters** \u2014 Saturated points pull the fitted maximum down and flatten exactly the part of the\nresponse that identifies saturation parameters and maximal rates. The residuals look like a model that\novershoots, which invites a structural move \u2014 a rate law change to fix a detector artefact.\n\n**How to apply** \u2014 data_extraction: flag series where the top values plateau at a suspiciously common value\nor where several conditions share an identical maximum. interpretation: consider censoring before\nconcluding the model overshoots at high dose.\n\n_Reviewed: \u2014_\n\n---\n\n### 3 \u00b7 SD-vs-SEM mislabelling is endemic, and `n` decides it\n\n**Pitfall** \u2014 Taking the caption at its word. In several subfields error bars are SEM by convention even\nwhen labelled SD, and the reverse also happens; many captions state neither.\n\n**Why it matters** \u2014 Using SEM as sigma underweights every point by a factor of \u221an \u2014 a silent, uniform\ndistortion of every likelihood weight that no downstream diagnostic reveals. The fit looks confident and the\nuncertainty is wrong by a constant factor.\n\n**How to apply** \u2014 data_extraction: record `error_type` as stated **and** flag any conflict with convention;\nrecord `n` wherever available, since without it the SEM\u2192SD conversion is impossible. observation (noise): with\n`error_type: sem` and no `n`, estimate sigma rather than using the column. assembly_verification: an SEM column\nused directly as sigma is a failed verdict.\n\n_Reviewed: \u2014_\n\n---\n\n### 4 \u00b7 Arbitrary units mean a scaling factor, full stop\n\n**Pitfall** \u2014 Treating a.u., \"relative intensity\", \"fold change\" or \"% of control\" as if the numbers had\nabsolute meaning, because their magnitude happens to sit near the model's.\n\n**Why it matters** \u2014 The measurement is proportional to the model quantity by an unknown constant. Without a\nscaling parameter, that constant is silently forced to 1, and the estimation compensates by distorting\nwhichever model parameters set the amplitude \u2014 usually total amounts and synthesis rates.\n\n**How to apply** \u2014 data_extraction: declare `units: arbitrary` rather than guessing. observation (scaling): a\nscaling factor, shared across conditions unless the experiment argues otherwise. This is also the case the\nmagnitude-reconciliation gate is built to catch, so a failure there usually means this entry was ignored.\n\n_Reviewed: \u2014_\n\n---\n\n### 5 \u00b7 Replicate lanes are usually independent, not paired\n\n**Pitfall** \u2014 Assuming replicates on a blot or plate are matched across conditions, and encoding them as\npaired measurements.\n\n**Why it matters** \u2014 Biological replicates from separate cultures on separate days share no per-replicate\neffect worth pairing; treating them as paired invents structure. The reverse case \u2014 technical replicates\nfrom one lysate treated as independent biological replicates \u2014 inflates the effective `n` and shrinks every\nuncertainty statement.\n\n**How to apply** \u2014 data_extraction: record replicate identity as it appears; flag when the description does\nnot distinguish technical from biological replicates, since the two carry different information and only the\ndescription can tell them apart.\n\n_Reviewed: \u2014_\n\n---\n\n### 6 \u00b7 Background subtraction produces genuine small negatives\n\n**Pitfall** \u2014 Treating negative values after background subtraction as data-entry errors, and clipping them\nto zero or dropping the rows.\n\n**Why it matters** \u2014 Near-zero signal minus an estimated background is negative about half the time; that is\nthe noise doing its job. Clipping biases every low measurement upward, which systematically distorts\nbaselines and early timepoints \u2014 exactly where initial conditions and basal rates are identified.\n\n**How to apply** \u2014 data_extraction: keep the rows, flag if you must, never drop. observation (noise): additive\nnormal accommodates negatives; a log transformation or a proportional noise model does not, which rules\nboth out for background-subtracted data.\n\n_Reviewed: \u2014_\n\n---\n\n### 7 \u00b7 Normalisation moves the error structure with it\n\n**Pitfall** \u2014 Applying a noise model chosen for a raw readout to data that has been divided by a control, a\nloading standard or its own t=0 value.\n\n**Why it matters** \u2014 The normaliser carries its own error, which propagates into every normalised point, and\nthe ratio's error is no longer the numerator's. Normalising to t=0 additionally makes the first point exact\nby construction \u2014 a zero-variance measurement the likelihood will happily treat as infinitely informative if\nsigma is small there.\n\n**How to apply** \u2014 data_extraction: flag the normalisation explicitly, naming what it was normalised to.\nobservation_model (noise): state which readout the sigma refers to \u2014 raw or normalised. Consider whether the reference\npoint should carry data at all.\n\n_Reviewed: \u2014_\n\n---\n\n### 8 \u00b7 A digitised figure inherits the axis, not the data\n\n**Pitfall** \u2014 Treating points read off a published figure as equivalent to tabulated values.\n\n**Why it matters** \u2014 Digitisation drift is systematic, not random: a misplaced axis calibration shifts or\nscales an entire series, and log axes make small pixel errors into large value errors. The numbers stay\nplausible, so nothing flags them, and the resulting bias is attributed to the model.\n\n**How to apply** \u2014 data_extraction: record that a source is digitised, check the extracted range against the\nfigure's stated axis limits, and flag any series whose endpoints fall outside them. Cross-source\ndisagreement on a shared condition is a recorded finding, never resolved silently in favour of the more\nconvenient series.\n\n_Reviewed: \u2014_\n"
}
```
## data_signals
```json
{
  "per_observable": {
    "CTD_phos0_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 1,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.999569,
        "dynamic_range": 16.438,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 1 zero(s)"
      }
    },
    "CTD_phos1_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 2,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.897469,
        "dynamic_range": 4.712,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 2 zero(s)"
      }
    },
    "CTD_phos2_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 2,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.897677,
        "dynamic_range": 2.25,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 2 zero(s)"
      }
    },
    "CTD_phos3_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 2,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.779681,
        "dynamic_range": 1.249,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 2 zero(s)"
      }
    },
    "CTD_phos4_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 2,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.827112,
        "dynamic_range": 1.392,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 2 zero(s)"
      }
    },
    "CTD_phos5_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 2,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.855459,
        "dynamic_range": 2.428,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 2 zero(s)"
      }
    },
    "CTD_phos6_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 2,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.641782,
        "dynamic_range": 4.053,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 2 zero(s)"
      }
    },
    "CTD_phos7_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 3,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.194517,
        "dynamic_range": 1.0,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 3 zero(s)"
      }
    },
    "CTD_phos8_rel": {
      "noise": {
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
      "support": {
        "n_values": 4,
        "n_non_finite": 0,
        "n_zero": 3,
        "n_negative": 0,
        "integer_valued": false,
        "min": 0.0,
        "max": 0.851626,
        "dynamic_range": 1.0,
        "log_transform_legal": false,
        "reading": "a log transform is NOT legal: 3 zero(s)"
      }
    }
  },
  "processing_applied": null,
  "below_detection": null,
  "how_to_read_this": "Measured from the replicates, no model involved: the slope of log(replicate spread) on log(signal) is 0 for constant error and 1 for proportional. `error_model` is stated only when the interval excludes one of those \u2014 an `inconclusive` verdict means these replicates cannot separate them, and you should argue from the measurement process instead of treating the number as an answer. Nothing here constrains the MODEL; it is evidence about the observation function you are authoring."
}
```

# Output contract
{"observables": [{"observable_id": "obs_x", "maps_to_label": "...",
                   "formula": "<the model quantity AS THE DATA TABULATE IT: species/parameter expression, with the instrument link written in when the data scale is not affine in the model quantity (NOTE below) — no gain, no background>",
                   "transformation": "lin|log|log10",
                   "noise": {"distribution": "normal|laplace",
                             "formula": "<one of the four shapes below>",
                             "estimate_sigma": true,
                             "per": "observable|condition"},
                   "scaling": {"mode": "none|factor|factor_offset|offset",
                               "scale_parameter": "sc_obs_x or null", "offset_parameter": "off_obs_x or null",
                               "per": "observable|timepoint|condition",
                               "shared_across_observables": "false, or a group name",
                               "pin_first_to_one": false},
                   "rationale": "ONE argument, from the measurement process, for the COHERENT triple (mapping, transformation+noise, scaling) — not three restatements"}]}
NOTE on NOISE FROM THE DATA: when the data extraction declared
an `error_column` for a label (error_type "column"), that observable's sigma is
FIXED per measurement row from the data and your `noise` block is not rendered —
write {"distribution": "normal", "formula": "from_data", "estimate_sigma": false}
and say so in the rationale. Otherwise a fixed sigma must be a NUMBER; a bare
parameter id with estimate_sigma=false is refused (nothing declares it).
NOTE on INSTRUMENT LINKS: `transformation` is PEtab's
residual-scale switch and nothing more — lin|log|log10 applied to BOTH the
measurement and the simulation before the residual is formed. It cannot
express a data scale that is not affine in the model quantity. When the
tabulated values are arcsinh(x/c) (mass cytometry, flow cytometry), a
saturating binding or Hill readout, or any other nonlinear instrument
response, the link goes INTO `formula` and `transformation` stays `lin`, so a
fixed or estimated sigma sits on the scale the values are reported on:
  data = arcsinh(count/5), model pX in counts  ->  "log(pX/5 + sqrt(1 + pX*pX/25))"
  (`log` is the natural logarithm in PEtab and sympy; `ln` is accepted too)
The model quantity is then in the instrument's linear units and mass action,
conservation and fold-changes hold where they physically hold. Writing
`formula: pX` against arcsinh-scale data makes the model STATE the compressed
value — every fold-change and every conserved total is then imposed on a
logarithm. If you choose that deliberately, write it in the rationale as a
decision, never as a constraint of this contract. "No gain, no background" in
the formula means the SCALING block owns those two; it does not exclude the
link.

NOTE on SCALING SHAPES — what a scale factor is indexed BY:

  per: "observable"  one factor for the observable, every row (the default).
  per: "timepoint"   one factor per distinct measurement time — an instrument
                     gain that drifts between acquisitions. The engine
                     writes `sc_<stem>_t<time>` for each time and fills the
                     PEtab observableParameters column row by row.
  per: "condition"   one factor per condition — separate gels, plates, days.
  shared_across_observables: a GROUP NAME makes every observable declaring it
                     share ONE parameter set (`sc_<group>_t60` is the same
                     parameter in all k readouts of one acquisition). `false`
                     keeps the set per observable. Members of a group must
                     declare the same per, mode and pin.
  pin_first_to_one:  fix the first factor (earliest time / first condition) at
                     1, estimate: 0. IDENTIFIABILITY: with every factor free the
                     absolute scale must be pinned by EITHER a fixed model
                     total (an unestimated initial amount) OR this; the
                     rationale must name which, and the FIM screen shows the
                     flat direction if neither holds.

NOTE on SPELLING (AMICI compiles the formula): write log2(x) as log(x)/log(2)
and log10(x) as log(x)/log(10). Antimony, roadrunner and petablint accept
`log2`, AMICI does not, and the failure surfaces only at compile, after every
earlier check has passed, for every candidate at once. The engine rewrites these
two for you and refuses any other unknown function by name, but write it right.

NOTE on the NOISE FORMULA — four shapes, all supported:

  constant              "sigma_obs_x"
        one scale, independent of signal. The right default when replicate
        spread does not follow magnitude.
  proportional          "sigma_obs_x * <this observable's signal expression>"
        spread scales with signal. Degenerates to sigma=0 wherever the signal
        is zero, so it is wrong for any readout that reaches zero.
  additive+proportional "sigma_abs + sigma_rel * <this observable's signal expression>"
        a floor plus a signal-dependent term. THE shape for a readout that
        CONTAINS ZEROS — which `data_signals.support` tells you directly, as
        "a log transform is NOT legal: N zero(s)". Pure proportional puts
        sigma=0 at those points; pure constant misses the scale at high
        signal. Name both parameters; both are estimated.
  gain-scaled           "sc_obs_x * sigma_obs_x"
        the error scales with the observable's SCALE FACTOR (the
        scale_parameter you declared), not with the signal: a per-acquisition
        gain multiplies signal and noise alike, so a per-timepoint or
        per-condition scaling usually carries its factor into sigma. The
        engine renders `sc_obs_x` as the observable placeholder, so each
        row's sigma uses that row's own gain.

In the two signal-dependent shapes, the signal expression is this observable's
own formula, with or without its gain `sc_obs_x`; a sigma on any other state of
the model is refused and re-asked. Assignment-rule symbols are fine; the engine
expands them.

Each non-model symbol becomes its own PEtab noiseParameter placeholder, in the
order it appears in your formula. Up to three are rendered. This is offered,
not merely tolerated: when the error has a floor and a signal-dependent part,
write both rather than forcing one symbol to carry the two.

NOTE on "noise.per" — what the sigma is indexed BY:
  per: "observable"  one sigma set for the readout, every condition (default).
  per: "condition"   one sigma set PER CONDITION. The engine renders
                     `sigma_<obs>_<cond>` for every condition the observable is
                     measured in, fills the PEtab noiseParameters column row by
                     row, and counts every extra sigma in k. A held-out
                     condition's sigma is never fitted (fixed, out of k).
Use `condition` when the replicate spread differs between ARMS of the design
in a way no signal-dependent shape explains — a control arm at 0.1–0.3 log2
against a stimulated arm at 0.5–1.3 log2 — and cite the data_signals evidence
that shows it. It is NOT a scale factor: a per-condition sigma reweights the
residuals of that arm; it never moves the prediction. Do not reach for a
gain-scaled shape with a per-condition factor to get this effect: on log-scale
data that factor is an additive offset degenerate with the basal rates.

NOTE on "data_signals.processing_applied" when present: the table you
map onto was PROCESSED by the engine as data extraction declared (row
normalisation, a subtracted blank, a unit factor) — the facts are listed. Do
not add a second scale or offset on top of a step that already did it.

NOTE on "supplied_literature" when present: typed claims about papers the
person who staged this problem already has — `id` (lit_1 …), `source`, `title`,
`year`, `locator`, `supports`, `quote`, `origin: human`. Construction received the
same items. What they say about the MEASUREMENT is yours: the assay and what it
detects, units and whether they are absolute, a detection floor, replicate
structure, the scale on which the error is additive. Cite the id in the rationale
where an item decided something; never attribute to an item a claim its
`supports`/`quote` does not make.

NOTE on "data_signals" when present: the replicates' own read on the
error model, measured with no model involved — the slope of log(replicate
spread) on log(signal), which is 0 for constant error and 1 for proportional.
Use it as EVIDENCE for the noise block you are authoring, and weigh it against
the measurement process: an `inconclusive` verdict means these replicates
cannot separate the two, so argue from the assay rather than treating the
number as an answer, and say which you did in the rationale. It says nothing
about the MODEL — it is about the observation function.

NOTE: you author the whole observation function y = sc * g(x) + off + eps for
every measured quantity. The three parts are one decision: a log transformation
IS a claim that the error is multiplicative; a free scale factor on absolutely
calibrated data creates an exact flat direction with the model's own totals. The
rationale must argue that coherence; the engine splits your reply into the
estimation problem mechanically and checks the seams it can check.

NOTE on "model_space" (OPTIONAL): when there is more than one DEFENSIBLE
observation function for this data — not a better and a worse, two a careful
person could argue for — declare the alternative as an AXIS instead of choosing
silently. Shape:

  "model_space": [{"id": "per_timepoint_scaling", "priority": 1,
                   "question": "<the question the axis answers, in one line>",
                   "on_assembly_patch": {"change_scaling": {"observable_ids": ["obs_x", "obs_y"],
                                                            "per": "timepoint",
                                                            "shared_across_observables": "acq"}}}]

`on_assembly_patch` is a dict with EXACTLY ONE kind as its key — the kinds are
listed under "model_space patch kinds" in the construction contract:
change_observable_formula, change_noise_model, add_offset, remove_scaling,
change_scaling {observable_id | observable_ids, per, shared_across_observables?,
pin_first_to_one?}, change_condition, and change_transformation
{observable_id, new} — declared but REFUSED until a criterion can compare fits
on different residual scales, so do not propose it. split_parameter {parameter_id, by} is the
expansion agent's: the engine resolves it against the data at the expansion
gate, so do not propose it here either. A patch in any other shape is dropped by name and
comes back to you.

The engine fits both and lets the criterion and the human decide. Declare an
axis only when you would otherwise be making the choice on taste: a scaling
convention the data cannot settle, a noise model the replicates leave open, an
offset that may or may not exist. Choose, and say why in the rationale, when
the measurement process actually decides it — an axis per preference would
multiply the fitting for nothing.

NOTE on "known_facts" when present: what the knowledge module found, before the intent was frozen, that a model of this system needs beyond its reactions — each with an `id` (`fact_1`), a `kind`, a `statement` (a `value` and `unit` where it is quantitative), what it `applies_to`, its evidence and the grade the engine gave it (`not_applicable` when it was gathered offline). Only the facts meant for your role reach you. Use a fact where it applies instead of inventing the assumption, and where you depart from one, say why. A noise floor, a detection limit or a fixed sigma taken from a fact names its id (`fact_2`) in that observable's `rationale`.
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "observables": [
  {
   "observable_id": "obs_phos0",
   "maps_to_label": "CTD_phos0_rel",
   "formula": "CTD_0",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "The readout is intact-mass MS of the 8-heptarepeat CTD construct (the lab note names it). The phos0 peak is the unmodified mass, which is exactly the model's lumped species CTD_0 (glossary: the single configuration with no marks). Species are in uM with vial = 1, so no volume factor is needed. If a position-resolved candidate is fitted, this label maps to its single zero-mark configuration. Units are relative intensities on a per-injection scale (data_labels: arbitrary). The lab note shows spectra summing to 1.00, 4.07, 3.79 and 0.85 at 0, 60, 120 and 960 min while substrate is conserved. A scale factor is therefore required, indexed per time point and shared by all nine peaks under group ctd_ms, because one injection gives one spectrum and one gain. No offset: no background, blank or instrument floor is described, and the exact zeros in the table argue against an unsubtracted baseline. The absolute scale is pinned by the fixed model total: CTD_0 starts at 100 uM, the total over CTD_0..CTD_8 is conserved, and that amount must stay unestimated. Pinning the first factor to 1 would instead clash with the t=0 spectrum summing to 1 against 100 uM. The factors are thus intensity per uM, roughly 0.010, 0.041, 0.038 and 0.0085, consistent with the nominal-magnitude gap. Noise: the lab note states additive normal error, one SD for the whole experiment, equal for every peak, scaling between time points with the same factor that maps amounts onto intensities. That is the gain-scaled shape sc_ctd_ms * sigma_ctd_ms, with one sigma_ctd_ms shared by name across all nine observables. Per-peak sigmas would rest on 4 points each and collapse toward zero on peaks the model fits exactly. data_signals is inconclusive (n = 1, no replicates), so this choice follows the lab note rather than a replicate test. The scale stays lin because this peak is zero once (log illegal) and the error is stated to be additive. An assumption that cannot be tested here: every phosphorylation count has the same ionisation and detection response. A count-dependent response factor would be confounded with the cooperativity parameter cp, so it is named rather than estimated. Evidence: direct (the lab note names the assay, the units and the error model)."
  },
  {
   "observable_id": "obs_phos1",
   "maps_to_label": "CTD_phos1_rel",
   "formula": "CTD_1",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for the construct carrying one phosphate (lab note). Positional isomers and Ser2/Ser5 isomers have the same mass and land in one peak, so the assay sums all 8 one-mark configurations. The glossary's CTD_1 lump is exactly that sum, in uM with vial = 1. A position-resolved candidate must map this label to the sum of its 8 single-mark configurations. Intensities are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). This calls for one gain per time point, shared across all nine peaks of that spectrum (group ctd_ms). The absolute scale is pinned by the fixed, unestimated 100 uM CTD total, not by pin_first_to_one. No offset, since no background or blank is described. Noise follows the lab note: additive normal error with one experiment-wide SD equal for every peak, scaled per time point by that spectrum's gain. This gives sc_ctd_ms * sigma_ctd_ms with a single shared sigma_ctd_ms. data_signals is inconclusive with no replicates, so the lab note decides. The scale is lin because this peak has 2 zeros (log illegal) and the error is additive. Equal MS response across phosphorylation counts is assumed and stated; it is not estimated, because it would trade off against cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos2",
   "maps_to_label": "CTD_phos2_rel",
   "formula": "CTD_2",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for two phosphates (lab note). The assay cannot resolve which repeats carry them, so the peak sums all 28 two-mark configurations, which is the glossary's CTD_2 lump (uM, vial = 1). A position-resolved candidate sums its 28 configurations here. Intensities are arbitrary and drift per injection: spectrum sums are 1.00, 4.07, 3.79 and 0.85 while the total is conserved. Hence one scale factor per time point, shared across the nine peaks of one spectrum (group ctd_ms), with no offset because no background is described. The absolute scale is fixed by the unestimated 100 uM CTD total, so no factor is pinned. Noise is additive normal with one experiment-wide SD, equal for all peaks and scaled by each spectrum's gain, as the lab note states: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. data_signals is inconclusive (no replicates), so the lab note decides. The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal ionisation across counts is assumed rather than estimated, since it is confounded with cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos3",
   "maps_to_label": "CTD_phos3_rel",
   "formula": "CTD_3",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for three phosphates (lab note). Isobaric positional isomers sum into one peak, which is all 56 three-mark configurations, the glossary's CTD_3 lump (uM, vial = 1). A position-resolved candidate maps this label to the sum of those 56. The intensities are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). They therefore take one gain per time point, shared by all nine peaks of the spectrum (group ctd_ms). No offset, as no background or blank is reported. The absolute scale is pinned by the fixed, unestimated 100 uM total, not by pinning a factor. Noise follows the lab note's statement of additive normal error, one SD for every peak and the whole experiment, scaled by each spectrum's gain: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. data_signals is inconclusive (n = 1). The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal response across phosphorylation counts is an assumption, stated rather than estimated, because it would be degenerate with cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos4",
   "maps_to_label": "CTD_phos4_rel",
   "formula": "CTD_4",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for four phosphates (lab note). It sums all 70 four-mark configurations, which the assay cannot tell apart; this is the glossary's CTD_4 lump (uM, vial = 1). A position-resolved candidate sums its 70 configurations here. Signals are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). So there is one scale factor per time point, shared across the nine peaks of each spectrum (group ctd_ms), and no offset because no background is described. The absolute scale is pinned by the fixed, unestimated 100 uM CTD total. Noise is additive normal with one experiment-wide SD equal for every peak, scaled by that spectrum's gain, per the lab note: sc_ctd_ms * sigma_ctd_ms with a single shared sigma_ctd_ms. With no replicates, data_signals is inconclusive and the lab note decides. The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal MS response across counts is assumed rather than estimated, because a count-dependent response would be confounded with cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos5",
   "maps_to_label": "CTD_phos5_rel",
   "formula": "CTD_5",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for five phosphates (lab note). It sums the 56 isobaric five-mark configurations, which is the glossary's CTD_5 lump (uM, vial = 1). A position-resolved candidate sums those 56 here. Intensities are arbitrary and drift between injections (spectrum sums of 1.00, 4.07, 3.79 and 0.85 while substrate is conserved). That calls for one gain per time point shared by all nine peaks of the spectrum (group ctd_ms), with no offset because no background or blank is stated. The absolute scale is pinned by the fixed, unestimated 100 uM total. Noise is additive normal, with one SD for all peaks and the whole experiment, scaled by each spectrum's gain, as the lab note states: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. data_signals is inconclusive (no replicates). The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal ionisation across counts is assumed and stated; it is not estimated because it would trade off against cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos6",
   "maps_to_label": "CTD_phos6_rel",
   "formula": "CTD_6",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for six phosphates (lab note). It sums the 28 isobaric six-mark configurations, which is the glossary's CTD_6 lump (uM, vial = 1). A position-resolved candidate sums those 28 here. Signals are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). So there is one scale factor per time point, shared across the spectrum's nine peaks (group ctd_ms), and no offset because no background is described. The absolute scale is fixed by the unestimated 100 uM total rather than by pinning a factor. Noise follows the lab note: additive normal error, one experiment-wide SD equal for every peak, scaled per time point by the same gain, giving sc_ctd_ms * sigma_ctd_ms with a shared sigma_ctd_ms. data_signals is inconclusive (n = 1). The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal response across counts is assumed rather than estimated, since it is confounded with cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos7",
   "maps_to_label": "CTD_phos7_rel",
   "formula": "CTD_7",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for seven phosphates (lab note). It sums the 8 isobaric seven-mark configurations, which is the glossary's CTD_7 lump (uM, vial = 1). A position-resolved candidate sums those 8 here. Intensities are arbitrary per injection (spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate), so there is one gain per time point shared by all nine peaks (group ctd_ms). No offset, as no background is reported. The absolute scale is pinned by the fixed, unestimated 100 uM total. This peak is zero at 3 of 4 times, which rules out a log scale and any pure proportional noise. The lab note's additive normal error, one SD for every peak scaled by each spectrum's gain, fits that: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. A sigma for this peak alone would collapse to zero on its three exact zeros, which is why the sigma must be shared. data_signals is inconclusive (no replicates), so the lab note decides. Equal MS response across counts is assumed rather than estimated, because it would trade off against cp. Evidence: direct (lab note)."
  },
  {
   "observable_id": "obs_phos8",
   "maps_to_label": "CTD_phos8_rel",
   "formula": "CTD_8",
   "transformation": "lin",
   "noise": {
    "distribution": "normal",
    "formula": "sc_ctd_ms * sigma_ctd_ms",
    "estimate_sigma": true,
    "per": "observable"
   },
   "scaling": {
    "mode": "factor",
    "scale_parameter": "sc_ctd_ms",
    "offset_parameter": null,
    "per": "timepoint",
    "shared_across_observables": "ctd_ms",
    "pin_first_to_one": false
   },
   "rationale": "This is the intact-mass MS peak for the fully modified construct (lab note). Because Ser2 and Ser5 are mutually exclusive, 8 phosphates means every repeat is marked: the single configuration that is the glossary's CTD_8 (uM, vial = 1). A position-resolved candidate maps this label to its all-marked configuration. Signals are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). So there is one scale factor per time point, shared by the nine peaks of the spectrum (group ctd_ms), and no offset because no background or blank is described. The absolute scale is pinned by the fixed, unestimated 100 uM CTD total, not by pin_first_to_one. The peak is zero at 3 of 4 times, so log and pure proportional noise are illegal. The lab note states additive normal error with one experiment-wide SD for every peak, scaled by each spectrum's gain: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. A sigma for this peak alone would be unidentifiable from one nonzero point. data_signals is inconclusive (n = 1). Equal ionisation across counts is assumed rather than estimated, since it is degenerate with cp. Evidence: direct (lab note)."
  }
 ]
}
````
