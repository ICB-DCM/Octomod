# Prompt · `condition` (round 0)

The **condition** agent encodes the experimental condition (S3). Below is the exact prompt it was sent in this run (47,569 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 2 times here; the record keeps the prompt and reply of the last call.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Condition encoding: turn each experimental condition into model overrides

Encode what the experimentalist did, nothing more and nothing less: every distinct condition in the data becomes
parameter and species overrides, with a pre-equilibration where the protocol implies one.

## What you receive
`condition_labels`, `intent` (its perturbations are the conditions), `experiment_description` (the lab note),
`design_summary` (the design's levels and absent combinations, no values), `model_summary`, `entity_glossary`,
`observation_draft` (the observation function just written) and, when construction gave one, `basal_state`: its
view of whether the initial values are the unstimulated steady state.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`conditions`, required: one `{condition_id, maps_to_label, overrides, preequilibration, rationale}` per condition
(shape: Output contract). An override value is a number (the condition fixes it) or a parameter id (the condition
gets its own estimated copy). Optional `model_space`, only for an encoding choice with two defensible readings.

## Rules that get your reply refused
- Every override and pre-equilibration key is an existing model parameter or species id (else a T0 gate fails).
- Every condition label in the data is encoded, none is invented, and one distinct treatment is one condition: two
  ids for one experiment double its weight in the likelihood.
- `preequilibration` is `false` or a dict, never a bare `true`, which names no condition. The dict is the measured
  condition with the stimulus removed — `{"S": 0}`, or `{"S1": 0, "S2": 0}` for two stimuli; a control whose
  stimulus is already off repeats that override. The engine applies it on top of a copy of the measured condition's
  overrides, writes it as that condition's `preeq_` row, simulates it to steady state, and starts the measured
  condition there. One that does not reach steady state fails a gate.
- Encode the intervention as performed (dose, pre-treatment, inhibitor, genotype or knockdown, starvation,
  temperature), never what would make the fit work. The rationale names the physical intervention behind each
  override and where its value came from, and the protocol step a pre-equilibration stands for.

## How to judge
- **Pre-equilibration is yours to decide, per measured condition**, from the protocol in the lab note (overnight
  starvation, steady growth, resting cells before the stimulus), from `basal_state`, and from your own judgment.
  Declare it only where the protocol implies a settled baseline. A pre-treatment stays out of the dict: the
  pre-equilibration condition carries it, the simulated condition carries the stimulus, and that order is invisible
  in the tables once wrong.
- A species the measured condition overrides is re-set at t = 0 after pre-equilibration; every other species starts
  from the steady state. That is how a stimulus written as an initial amount enters, and why overriding any other
  species throws its steady state away.
- Dose is usually an override on the input species' initial value or on a stimulus parameter; say which and why.
  An inhibitor is a reduced rate constant: full abolition (→ 0) is a strong claim, and partial inhibition may need
  estimating. Genotype and knockdown are reduced amounts or synthesis rates, never deleted reactions, so the model
  stays one model. Untreated and vehicle controls are conditions too; encode them explicitly so the audit sees what
  "control" meant.
- **Groups measured under identical treatment** (a `population` factor): give each level its own copy
  (`<param>_<level>`) of exactly the parameters construction marked `varies_by` that factor (without any, what the
  intent and lab note say varies), never of one declared shared. A copied catalytic constant next to per-group
  abundances is unidentifiable and answers "same chemistry?" by construction. An intervention factor is a number.
  A per-group id stays the same inside a pre-equilibration, so the steady state is that group's.
- Encode through the parameters the glossary marks "set per condition", and flag a condition that has none. Say
  so in the rationale when a dose enters through a parameter the observation function also uses, or an override
  moves a quantity a scale factor absorbs; the battery checks only what it can.
- Tiers: `direct` when the lab note states dose and duration, `transferred` for this reagent's standard protocol in
  this system, `default` when inferred; a dose read off a figure legend is not `direct`. When the note is too vague
  (no dose, "pre-treated" with no duration), say so rather than pick a number that will later look like data.

## Mistakes we have seen
- Overriding a parameter no kinetic law uses: the dose does nothing and the mechanism gets the blame.
- Overriding an initial value that an initial assignment sets: silently ignored.
- Pre-equilibration on a model with no steady state, or with a stimulus left in the dict, or one stimulus zeroed
  and another forgotten.
- A knockout encoded by editing the model instead of overriding a parameter.
- Unit slips: nM in the table, µM in the model.
- A condition-specific parameter invented to absorb a misfit; that is a revision, not an encoding.


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

## condition_labels
```json
[
  "invitro_PTEFb_CTD8"
]
```
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
## observation_draft
```json
{
  "observables": [
    {
      "observable_id": "obs_phos0",
      "maps_to_label": "CTD_phos0_rel",
      "formula": "CTD_0",
      "transformation": "lin",
      "rationale": "The readout is intact-mass MS of the 8-heptarepeat CTD construct (the lab note names it). The phos0 peak is the unmodified mass, which is exactly the model's lumped species CTD_0 (glossary: the single configuration with no marks). Species are in uM with vial = 1, so no volume factor is needed. If a position-resolved candidate is fitted, this label maps to its single zero-mark configuration. Units are relative intensities on a per-injection scale (data_labels: arbitrary). The lab note shows spectra summing to 1.00, 4.07, 3.79 and 0.85 at 0, 60, 120 and 960 min while substrate is conserved. A scale factor is therefore required, indexed per time point and shared by all nine peaks under group ctd_ms, because one injection gives one spectrum and one gain. No offset: no background, blank or instrument floor is described, and the exact zeros in the table argue against an unsubtracted baseline. The absolute scale is pinned by the fixed model total: CTD_0 starts at 100 uM, the total over CTD_0..CTD_8 is conserved, and that amount must stay unestimated. Pinning the first factor to 1 would instead clash with the t=0 spectrum summing to 1 against 100 uM. The factors are thus intensity per uM, roughly 0.010, 0.041, 0.038 and 0.0085, consistent with the nominal-magnitude gap. Noise: the lab note states additive normal error, one SD for the whole experiment, equal for every peak, scaling between time points with the same factor that maps amounts onto intensities. That is the gain-scaled shape sc_ctd_ms * sigma_ctd_ms, with one sigma_ctd_ms shared by name across all nine observables. Per-peak sigmas would rest on 4 points each and collapse toward zero on peaks the model fits exactly. data_signals is inconclusive (n = 1, no replicates), so this choice follows the lab note rather than a replicate test. The scale stays lin because this peak is zero once (log illegal) and the error is stated to be additive. An assumption that cannot be tested here: every phosphorylation count has the same ionisation and detection response. A count-dependent response factor would be confounded with the cooperativity parameter cp, so it is named rather than estimated. Evidence: direct (the lab note names the assay, the units and the error model)."
    },
    {
      "observable_id": "obs_phos1",
      "maps_to_label": "CTD_phos1_rel",
      "formula": "CTD_1",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for the construct carrying one phosphate (lab note). Positional isomers and Ser2/Ser5 isomers have the same mass and land in one peak, so the assay sums all 8 one-mark configurations. The glossary's CTD_1 lump is exactly that sum, in uM with vial = 1. A position-resolved candidate must map this label to the sum of its 8 single-mark configurations. Intensities are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). This calls for one gain per time point, shared across all nine peaks of that spectrum (group ctd_ms). The absolute scale is pinned by the fixed, unestimated 100 uM CTD total, not by pin_first_to_one. No offset, since no background or blank is described. Noise follows the lab note: additive normal error with one experiment-wide SD equal for every peak, scaled per time point by that spectrum's gain. This gives sc_ctd_ms * sigma_ctd_ms with a single shared sigma_ctd_ms. data_signals is inconclusive with no replicates, so the lab note decides. The scale is lin because this peak has 2 zeros (log illegal) and the error is additive. Equal MS response across phosphorylation counts is assumed and stated; it is not estimated, because it would trade off against cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos2",
      "maps_to_label": "CTD_phos2_rel",
      "formula": "CTD_2",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for two phosphates (lab note). The assay cannot resolve which repeats carry them, so the peak sums all 28 two-mark configurations, which is the glossary's CTD_2 lump (uM, vial = 1). A position-resolved candidate sums its 28 configurations here. Intensities are arbitrary and drift per injection: spectrum sums are 1.00, 4.07, 3.79 and 0.85 while the total is conserved. Hence one scale factor per time point, shared across the nine peaks of one spectrum (group ctd_ms), with no offset because no background is described. The absolute scale is fixed by the unestimated 100 uM CTD total, so no factor is pinned. Noise is additive normal with one experiment-wide SD, equal for all peaks and scaled by each spectrum's gain, as the lab note states: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. data_signals is inconclusive (no replicates), so the lab note decides. The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal ionisation across counts is assumed rather than estimated, since it is confounded with cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos3",
      "maps_to_label": "CTD_phos3_rel",
      "formula": "CTD_3",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for three phosphates (lab note). Isobaric positional isomers sum into one peak, which is all 56 three-mark configurations, the glossary's CTD_3 lump (uM, vial = 1). A position-resolved candidate maps this label to the sum of those 56. The intensities are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). They therefore take one gain per time point, shared by all nine peaks of the spectrum (group ctd_ms). No offset, as no background or blank is reported. The absolute scale is pinned by the fixed, unestimated 100 uM total, not by pinning a factor. Noise follows the lab note's statement of additive normal error, one SD for every peak and the whole experiment, scaled by each spectrum's gain: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. data_signals is inconclusive (n = 1). The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal response across phosphorylation counts is an assumption, stated rather than estimated, because it would be degenerate with cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos4",
      "maps_to_label": "CTD_phos4_rel",
      "formula": "CTD_4",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for four phosphates (lab note). It sums all 70 four-mark configurations, which the assay cannot tell apart; this is the glossary's CTD_4 lump (uM, vial = 1). A position-resolved candidate sums its 70 configurations here. Signals are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). So there is one scale factor per time point, shared across the nine peaks of each spectrum (group ctd_ms), and no offset because no background is described. The absolute scale is pinned by the fixed, unestimated 100 uM CTD total. Noise is additive normal with one experiment-wide SD equal for every peak, scaled by that spectrum's gain, per the lab note: sc_ctd_ms * sigma_ctd_ms with a single shared sigma_ctd_ms. With no replicates, data_signals is inconclusive and the lab note decides. The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal MS response across counts is assumed rather than estimated, because a count-dependent response would be confounded with cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos5",
      "maps_to_label": "CTD_phos5_rel",
      "formula": "CTD_5",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for five phosphates (lab note). It sums the 56 isobaric five-mark configurations, which is the glossary's CTD_5 lump (uM, vial = 1). A position-resolved candidate sums those 56 here. Intensities are arbitrary and drift between injections (spectrum sums of 1.00, 4.07, 3.79 and 0.85 while substrate is conserved). That calls for one gain per time point shared by all nine peaks of the spectrum (group ctd_ms), with no offset because no background or blank is stated. The absolute scale is pinned by the fixed, unestimated 100 uM total. Noise is additive normal, with one SD for all peaks and the whole experiment, scaled by each spectrum's gain, as the lab note states: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. data_signals is inconclusive (no replicates). The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal ionisation across counts is assumed and stated; it is not estimated because it would trade off against cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos6",
      "maps_to_label": "CTD_phos6_rel",
      "formula": "CTD_6",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for six phosphates (lab note). It sums the 28 isobaric six-mark configurations, which is the glossary's CTD_6 lump (uM, vial = 1). A position-resolved candidate sums those 28 here. Signals are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). So there is one scale factor per time point, shared across the spectrum's nine peaks (group ctd_ms), and no offset because no background is described. The absolute scale is fixed by the unestimated 100 uM total rather than by pinning a factor. Noise follows the lab note: additive normal error, one experiment-wide SD equal for every peak, scaled per time point by the same gain, giving sc_ctd_ms * sigma_ctd_ms with a shared sigma_ctd_ms. data_signals is inconclusive (n = 1). The scale is lin because there are 2 zeros (log illegal) and the error is additive. Equal response across counts is assumed rather than estimated, since it is confounded with cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos7",
      "maps_to_label": "CTD_phos7_rel",
      "formula": "CTD_7",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for seven phosphates (lab note). It sums the 8 isobaric seven-mark configurations, which is the glossary's CTD_7 lump (uM, vial = 1). A position-resolved candidate sums those 8 here. Intensities are arbitrary per injection (spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate), so there is one gain per time point shared by all nine peaks (group ctd_ms). No offset, as no background is reported. The absolute scale is pinned by the fixed, unestimated 100 uM total. This peak is zero at 3 of 4 times, which rules out a log scale and any pure proportional noise. The lab note's additive normal error, one SD for every peak scaled by each spectrum's gain, fits that: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. A sigma for this peak alone would collapse to zero on its three exact zeros, which is why the sigma must be shared. data_signals is inconclusive (no replicates), so the lab note decides. Equal MS response across counts is assumed rather than estimated, because it would trade off against cp. Evidence: direct (lab note)."
    },
    {
      "observable_id": "obs_phos8",
      "maps_to_label": "CTD_phos8_rel",
      "formula": "CTD_8",
      "transformation": "lin",
      "rationale": "This is the intact-mass MS peak for the fully modified construct (lab note). Because Ser2 and Ser5 are mutually exclusive, 8 phosphates means every repeat is marked: the single configuration that is the glossary's CTD_8 (uM, vial = 1). A position-resolved candidate maps this label to its all-marked configuration. Signals are relative per injection (units arbitrary; spectrum sums of 1.00, 4.07, 3.79 and 0.85 over conserved substrate). So there is one scale factor per time point, shared by the nine peaks of the spectrum (group ctd_ms), and no offset because no background or blank is described. The absolute scale is pinned by the fixed, unestimated 100 uM CTD total, not by pin_first_to_one. The peak is zero at 3 of 4 times, so log and pure proportional noise are illegal. The lab note states additive normal error with one experiment-wide SD for every peak, scaled by each spectrum's gain: sc_ctd_ms * sigma_ctd_ms with one shared sigma_ctd_ms. A sigma for this peak alone would be unidentifiable from one nonzero point. data_signals is inconclusive (n = 1). Equal ionisation across counts is assumed rather than estimated, since it is degenerate with cp. Evidence: direct (lab note)."
    }
  ]
}
```
## design_summary
```json
{
  "available": true,
  "per_file": {
    "ctd_ms_timecourse.csv": {
      "n_rows": 4,
      "columns": {
        "time_min": {
          "role": "time",
          "dtype": "int64",
          "n_unique": 4,
          "n_missing": 0,
          "levels": [
            0,
            60,
            120,
            960
          ]
        },
        "phos0_rel": {
          "role": "measurement",
          "dtype": "float64",
          "n_unique": 4,
          "n_missing": 0
        },
        "phos1_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.190472606,
            0.897469038
          ]
        },
        "phos2_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.398928055,
            0.897676748
          ]
        },
        "phos3_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.624281335,
            0.779681099
          ]
        },
        "phos4_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.594147075,
            0.82711232
          ]
        },
        "phos5_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.352327675,
            0.855458644
          ]
        },
        "phos6_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.158350845,
            0.641781932
          ]
        },
        "phos7_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 2,
          "n_missing": 0,
          "levels": [
            0.0,
            0.194516845
          ]
        },
        "phos8_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 2,
          "n_missing": 0,
          "levels": [
            0.0,
            0.851626189
          ]
        }
      },
      "design_columns": [
        "phos1_rel",
        "phos2_rel",
        "phos3_rel",
        "phos4_rel",
        "phos5_rel",
        "phos6_rel",
        "phos7_rel",
        "phos8_rel"
      ],
      "time_columns": [
        "time_min"
      ],
      "replicate_columns": [],
      "measurement_columns": [
        "phos0_rel"
      ],
      "factorial": {
        "available": true,
        "factors": [
          "phos1_rel",
          "phos2_rel",
          "phos3_rel",
          "phos4_rel",
          "phos5_rel",
          "phos6_rel",
          "phos7_rel",
          "phos8_rel"
        ],
        "n_full_factorial": 2916,
        "n_present": 4,
        "n_absent": 2912,
        "balanced": false,
        "per_cell": [
          {
            "cell": {
              "phos1_rel": 0.0,
              "phos2_rel": 0.0,
              "phos3_rel": 0.0,
              "phos4_rel": 0.0,
              "phos5_rel": 0.0,
              "phos6_rel": 0.0,
              "phos7_rel": 0.0,
              "phos8_rel": 0.0
            },
            "n_rows": 1,
            "n_time_points": 1
          },
          {
            "cell": {
              "phos1_rel": 0.0,
              "phos2_rel": 0.0,
              "phos3_rel": 0.0,
              "phos4_rel": 0.0,
              "phos5_rel": 0.0,
              "phos6_rel": 0.0,
              "phos7_rel": 0.0,
              "phos8_rel": 0.851626189
            },
            "n_rows": 1,
            "n_time_points": 1
          },
          {
            "cell": {
              "phos1_rel": 0.190472606,
              "phos2_rel": 0.398928055,
              "phos3_rel": 0.624281335,
              "phos4_rel": 0.82711232,
              "phos5_rel": 0.855458644,
              "phos6_rel": 0.641781932,
              "phos7_rel": 0.194516845,
              "phos8_rel": 0.0
            },
            "n_rows": 1,
            "n_time_points": 1
          },
          {
            "cell": {
              "phos1_rel": 0.897469038,
              "phos2_rel": 0.897676748,
              "phos3_rel": 0.779681099,
              "phos4_rel": 0.594147075,
              "phos5_rel": 0.352327675,
              "phos6_rel": 0.158350845,
              "phos7_rel": 0.0,
              "phos8_rel": 0.0
            },
            "n_rows": 1,
            "n_time_points": 1
          }
        ],
        "absent_cells": null,
        "why_not_enumerated": "the full factorial is 2916 cells, over the 200 this payload enumerates; the counts above still hold"
      }
    }
  },
  "how_to_read_this": "Computed from the raw files by the engine \u2014 no model, no agent, no measurement values. `role` is a GUESS from column name and cardinality; correct it if it is wrong, and say so in your reply. `factorial.absent_cells` names the design combinations that are NOT in the file: the preview you are also shown is the first 25 rows only, and a missing cell is usually not visible there."
}
```
## basal_state
```json
{
  "initial_values_are_steady_state": false,
  "suggest_preequilibration": false,
  "note": "t = 0 is the start of the kinase reaction: all CTD unmodified at 100 uM, ATP 3 mM. This is the pre-reaction state by construction but not a steady state of the model, whose only steady state is full modification (CTD_8). Pre-equilibrating would run the reaction to completion before the first sample, so simulate from these initial values."
}
```

# Output contract
{"conditions": [{"condition_id": "cond_x", "maps_to_label": "...", "overrides": {"<model_param_or_species>": 0.0},
                  "preequilibration": false | {"<model_param_or_species>": 0.0}, "rationale": "..."}]}

NOTE on "preequilibration": your decision, per measured condition, from the
protocol in the experiment description, from `basal_state` (the construction
agent's view of whether the model's initial values are the unstimulated steady
state), and from your own judgment. `false` = the condition is simulated from
the model's initial values. To pre-equilibrate, give the pre-equilibration
condition IN FULL as a dict of overrides, applied on top of a copy of this
condition's own overrides: the measured condition with the stimulus removed,
e.g. {"S": 0} or {"S1": 0, "S2": 0} (a control whose stimulus is
already off repeats that override at its value). The engine simulates that
condition to steady state and starts this one from it; a per-group parameter
id in `overrides` stays the same id, so the steady state is that group's. Keys
are model parameter or species ids, checked like overrides. A bare `true` names
no condition and is refused. A species this condition sets in `overrides` is
re-set at t=0 after pre-equilibration; every other species starts from the
steady state. Say in the rationale which protocol step the pre-equilibration
stands for.

NOTE on PARAMETER-VALUED overrides: an override value may be a
NUMBER (the condition fixes that quantity) or a PARAMETER ID (the condition gets
its OWN estimated copy of that model parameter). Use ids for a biological factor
whose levels are different cells or samples measured under identical staining —
e.g. `population` — for exactly the parameters the intent, the lab note or the
construction build report declare as varying with that factor (abundances,
basal fractions, feedback capacity), and NEVER for parameters declared shared
(catalytic rate constants, observation scale). Name the copy `<param>_<level>`
(`X_tot_groupA`); the engine creates the parameter rows, inheriting bounds
and scale from `<param>`, and removes `<param>` itself from the parameter table.
A factor that is an intervention (dose, ligand present) is a number.
WHICH parameters to split: exactly those whose construction entry carries
`"varies_by": ["<factor>"]`. If construction declared none, fall back to what
the intent and the lab note say varies between the groups — and split nothing
they declare shared (catalytic rate constants, measurement scale). Splitting a
shared catalytic constant next to a per-group abundance makes the two
unidentifiable and answers the "same chemistry?" question by construction.

NOTE on "model_space" (OPTIONAL): an encoding choice the data cannot settle
— whether a condition is a fixed override or an estimated quantity, whether two
labels are really one condition — may be declared as an axis rather than
decided silently, in the same shape the observation agent uses. Only when both
readings are defensible; otherwise choose and give the reason.

NOTE on "known_facts" when present: what the knowledge module found, before the intent was frozen, that a model of this system needs beyond its reactions — each with an `id` (`fact_1`), a `kind`, a `statement` (a `value` and `unit` where it is quantitative), what it `applies_to`, its evidence and the grade the engine gave it (`not_applicable` when it was gathered offline). Only the facts meant for your role reach you. Use a fact where it applies instead of inventing the assumption, and where you depart from one, say why. An override or a pre-equilibration taken from a fact names its id (`fact_2`) in that condition's `rationale`.
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "conditions": [
  {
   "condition_id": "cond_invitro_PTEFb_CTD8",
   "maps_to_label": "invitro_PTEFb_CTD8",
   "overrides": {
    "CTD_0": 100.0,
    "CTD_1": 0.0,
    "CTD_2": 0.0,
    "CTD_3": 0.0,
    "CTD_4": 0.0,
    "CTD_5": 0.0,
    "CTD_6": 0.0,
    "CTD_7": 0.0,
    "CTD_8": 0.0,
    "ATP": 3000.0,
    "ADP": 0.0,
    "PTEFb": 1.0
   },
   "preequilibration": false,
   "rationale": "The intent lists no perturbation. The data hold a single label: one purified in vitro P-TEFb kinase reaction, sampled at 0, 60, 120 and 960 min with no replicates. That makes exactly one condition, and none is invented. The overrides only restate the reaction mix as the lab note gives it (tier direct: the note states amounts and sampling times), so the audit can see what this condition was. These values match the model's initial values, so they change nothing in the simulation. CTD_0 = 100 uM, the recombinant 8-heptarepeat substrate, all unmodified at the start of the reaction. CTD_1..CTD_8 = 0 uM, since no modified substrate exists at t = 0. ATP = 3000 uM (3 mM at start, model unit uM, so there is no unit slip). ADP = 0 uM, as no phosphoryl transfer has occurred yet. PTEFb = 1 relative unit: the glossary says it is catalytic and constant, with its absolute concentration absorbed into kmod; the note gives no kinase concentration, so 1 is a convention, not a measured dose. No assignment rules or initial assignments exist, so these initial-value overrides are not silently ignored. The CTD_0 = 100 uM total is what pins the absolute scale in the observation draft. Its per-time-point gains (intensity per uM) are identified only because this total is fixed and unestimated. Estimating it would make it degenerate with the scale factors. Likewise, kmod absorbs kinase amount, so PTEFb must stay fixed. No parameter is overridden. kmod, cp and q_proc are mechanism parameters to be estimated or switched by model selection, not properties of this condition. The glossary marks none of them 'set per condition', which is expected for a single-condition design. K_ATP stays at its construction-fixed 50 uM. No population factor exists, so nothing is split per group. Pre-equilibration is false. t = 0 is the moment kinase, substrate and ATP are combined, not a settled baseline. basal_state confirms that the model's only steady state is full modification (CTD_8), so pre-equilibrating would run the reaction to completion before the first sample. Correction to design_summary: phos1_rel..phos8_rel were guessed as 'design' factors, but they are measurements (relative MS intensities for 1..8 phosphates), like phos0_rel. Their few unique values reflect only four rows with exact zeros, not factor levels. The 2916-cell 'factorial' is therefore spurious."
  }
 ]
}
````
