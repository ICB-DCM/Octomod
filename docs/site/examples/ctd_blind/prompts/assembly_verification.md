# Prompt · `assembly_verification` (round 0)

The **assembly_verification** agent independent check of the assembled estimation problem (S3). Below is the exact prompt it was sent in this run (49,984 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 2 times here; the record keeps the prompt and reply of the last call.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Assembly audit: check the assembled estimation problem independently

You see the artifacts only, never the reasoning of the agents that produced them, and you audit, never rebuild: a
checker that rewrites the artifact is not independent of it. One agent wrote the whole observation function
(mapping, transformation and noise, scaling) and another the condition encoding, so the coherence of the triple is
yours to check: a log transformation is a multiplicative-noise claim, and a scale factor on absolutely calibrated
data is a flat direction. Your verdicts are advisory; a digest of each note reaches the human on the compile card.

## What you receive
- **A full audit:** `intent`, `experiment_description` (the lab note), `entity_glossary` (what each species
  denotes and lumps), `domain_packs`, `observables_tsv`, `conditions_tsv`, `parameters_tsv` and `data_flags`.
- **An overlay audit:** `audit_scope`, `overlay` and `changed_entries` — an observation axis changed an assembly
  already audited, and only those entries are in question.

No measurement values: a table that matches the data by construction is not audited by reading both.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`verdicts` (`{aspect, ok, note}` each) and `overall` (`pass` | `concerns`), both required.

## Rules that get your reply refused
- A full audit covers at least four aspects, and never drops one: **noise model vs readout technique**, **condition
  encoding vs experiment description**, **scaling and offset vs declared units**, **observable mapping vs what the
  assay measures**. Add aspects when something else looks wrong. An overlay audit judges only the changed entries:
  is the alternative a hypothesis about the measurement process, or a fit device?
- Every verdict carries a note, `ok` ones too, saying what you checked against what — not merely that you checked.
- `overall` is `concerns` whenever a verdict has `ok: false`, never `pass` over a failed aspect; a `concerns`
  with no failed aspect needs its reason stated.
- Name the problem precisely and stop: no replacement formula, encoding or distribution.

## How to judge
- The failure you exist to catch is a plausible, internally consistent artifact that contradicts the experiment.
  Read the lab note first and the tables second, and treat every rationale as a claim to test, never as evidence.
- Noise: does the distribution fit the named assay? Is an SEM column standing in for sigma, a log scale applied to
  data that reach zero, one sigma shared across assays?
- Conditions: can you reconstruct each treatment from its overrides alone? Does the count of conditions match the
  distinct treatments described? Is the pre-treatment in the pre-equilibration condition and the stimulus in the
  simulated one?
- Scaling: arbitrary units without a scale factor and calibrated units with one are both errors. An offset with no
  background story is a fit device. Per-condition scaling without a stated reason destroys the cross-condition
  information the experiment was designed to carry.
- Observables: total, site-specific or ratio? Audit the mapping against the glossary: a "total" that omits a state
  the glossary lumps in, or a state the glossary says the assay does not detect, is a concern.
- Say `ok` when it is ok. A checker that finds a concern everywhere is as useless as one that rubber-stamps:
  calibrate to what would mislead the estimation, not to what you would have done differently. When you doubt
  rather than know, keep `ok: true` and put the doubt in the note; flagging and failing are different acts.
- The deterministic gates have already run: audit the judgment they cannot see. Do not restate them, and do not
  fail an artifact for what they cover (an unresolved symbol, an unbounded parameter, a duplicate measurement key).

## Mistakes we have seen
- Rebuilding: "the formula should be `sc_pERK * ERKp`".
- Rubber-stamping: a note that paraphrases the artifact ("noise is normal, sigma estimated") without testing it
  against the named assay.
- Nitpicking ids, naming style, ordering or missing comments.
- Calling an unusual but justified choice an error because it is unusual.


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
## observables_tsv
observableId	observableFormula	observableTransformation	noiseFormula	noiseDistribution	observableName
obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_0)	lin	observableParameter1_obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos0__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos0
obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_0)	lin	observableParameter1_obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos0__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos0
obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_0)	lin	observableParameter1_obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos0__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos0
obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_0)	lin	observableParameter1_obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos0__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos0
obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_1)	lin	observableParameter1_obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos1__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos1
obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_1)	lin	observableParameter1_obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos1__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos1
obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_1)	lin	observableParameter1_obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos1__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos1
obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_1)	lin	observableParameter1_obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos1__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos1
obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_2)	lin	observableParameter1_obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos2__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos2
obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_2)	lin	observableParameter1_obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos2__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos2
obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_2)	lin	observableParameter1_obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos2__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos2
obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_2)	lin	observableParameter1_obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos2__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos2
obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_3)	lin	observableParameter1_obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos3__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos3
obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_3)	lin	observableParameter1_obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos3__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos3
obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_3)	lin	observableParameter1_obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos3__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos3
obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_3)	lin	observableParameter1_obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos3__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos3
obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_4)	lin	observableParameter1_obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos4__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos4
obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_4)	lin	observableParameter1_obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos4__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos4
obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_4)	lin	observableParameter1_obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos4__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos4
obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_4)	lin	observableParameter1_obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos4__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos4
obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_5)	lin	observableParameter1_obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos5__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos5
obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_5)	lin	observableParameter1_obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos5__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos5
obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_5)	lin	observableParameter1_obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos5__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos5
obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_5)	lin	observableParameter1_obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos5__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos5
obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_6)	lin	observableParameter1_obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos6__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos6
obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_6)	lin	observableParameter1_obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos6__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos6
obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_6)	lin	observableParameter1_obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos6__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos6
obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_6)	lin	observableParameter1_obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos6__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos6
obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_7)	lin	observableParameter1_obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos7__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos7
obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_7)	lin	observableParameter1_obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos7__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos7
obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_7)	lin	observableParameter1_obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos7__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos7
obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_7)	lin	observableParameter1_obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos7__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos7
obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_8)	lin	observableParameter1_obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos8__sc_ctd_ms_t0__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos8
obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_8)	lin	observableParameter1_obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos8__sc_ctd_ms_t120__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos8
obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_8)	lin	observableParameter1_obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos8__sc_ctd_ms_t60__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos8
obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	observableParameter1_obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * (CTD_8)	lin	observableParameter1_obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8 * noiseParameter1_obs_phos8__sc_ctd_ms_t960__sigma_ctd_ms__cond_invitro_PTEFb_CTD8	normal	obs_phos8

## conditions_tsv
conditionId	CTD_0	CTD_1	CTD_2	CTD_3	CTD_4	CTD_5	CTD_6	CTD_7	CTD_8	ATP	ADP	PTEFb
cond_invitro_PTEFb_CTD8	100.0	0.0	0.0	0.0	0.0	0.0	0.0	0.0	0.0	3000.0	0.0	1.0

## parameters_tsv
parameterId	parameterScale	lowerBound	upperBound	nominalValue	estimate
kmod	log10	1e-05	1.0	0.01	1
cp	log10	0.2	5.0	1.0	0
q_proc	log10	0.0001	0.99	0.0	0
K_ATP	log10	5.0	500.0	50.0	0
sc_ctd_ms_t0	log10	0.001	1000.0	1.0	1
sc_ctd_ms_t60	log10	0.001	1000.0	1.0	1
sc_ctd_ms_t120	log10	0.001	1000.0	1.0	1
sc_ctd_ms_t960	log10	0.001	1000.0	1.0	1
sigma_ctd_ms	log10	0.0001	1000.0	1.0	1

## data_flags
```json
[
  "design_summary role guess is WRONG and is corrected here: phos1_rel..phos8_rel are measurement columns (relative MS intensities for 1..8 phosphates), not design factors; their 'levels' are measured values, and the 2916-cell 'factorial' is meaningless. The file has NO condition columns: one in vitro condition (8-repeat CTD 100 uM, P-TEFb catalytic, ATP 3 mM) sampled at 4 times. All 9 phosN_rel columns are mapped as separate observables of that single condition; condition_columns is empty and the label template is a fixed string.",
  "ctd_ms_timecourse.csv, all columns phos0_rel..phos8_rel, all 4 rows: intensities are on a per-injection arbitrary scale that differs between time points (row sums 1.00 at 0 min, 4.07 at 60 min, 3.79 at 120 min, 0.85 at 960 min, matching the lab note) while total substrate is conserved. Values are NOT commensurable across time points as they stand. No processing was declared: the note does not say the data were normalised, and the note's own observation model (a per-time-point factor mapping amounts onto intensities, which also scales the noise SD) belongs model-side. Do not pool or compare raw values across rows.",
  "ctd_ms_timecourse.csv: 19 of 36 measured values are exactly 0.0 (row time_min=0: phos1_rel..phos8_rel; row 60: phos7_rel, phos8_rel; row 120: phos8_rel; row 960: phos0_rel..phos7_rel). The note states additive Gaussian noise of a single SD at every peak, under which a measured empty peak would scatter around zero (including small negatives), not sit at exactly 0.0. These exact zeros look like not-detected or absent peaks written as zero, or idealised values, but the source states no detection floor and no handling rule, so no below_detection entry is declared. Left as is and NOT excluded; the observation model should know that roughly half the likelihood terms are exact zeros of uncertain provenance.",
  "No replicates (n = 1 per species per time point, stated in the note) and no error column. error_type recorded as 'none' because the file carries no error estimate. The note describes the noise model (additive, normal, one SD for the whole experiment shared by all peaks, scaled per time point by the same factor that maps amounts onto intensities); that SD is not given and must be estimated by the observation model. This is not an SD/SEM call: no error bars exist.",
  "Information content is thin for mechanism discrimination. Of 4 time points, t = 0 carries only the initial condition (all substrate unmodified; phos0_rel = 0.99957). t = 960 min carries only completion (only phos8_rel nonzero). Effectively only the 60 and 120 min distributions carry shape information about rates, each losing one degree of freedom to its own scale factor. The readout is phosphate COUNT only (9 mass peaks); which repeats are modified is not observed, so position-dependent (neighbour) effects can only enter through their imprint on count distributions.",
  "time_min = 960 is a sampled time (16 h), not a declared steady-state measurement, and is mapped as 960, not inf. It appears to be at or near completion (all signal in phos8_rel), but treating it as steady state would be a modelling decision, not an extraction edit.",
  "Time units are minutes, consistent with the intent's horizon (960 min). No conversion was made."
]
```
## domain_packs
```json
{
  "general-dynamics": "# general-dynamics \u2014 pitfalls\n\n`draft-unreviewed`. Eight entries. Each is a claim an expert should confirm, edit or delete individually;\na pack returned with no edits has not been reviewed.\n\n---\n\n### 1 \u00b7 Bounds spanning too few decades strangle multistart\n\n**Pitfall** \u2014 Bounds set as a tight cordon around a nominal value (half an order of magnitude either side)\nlook careful and are not. Multistart then samples a box that may not contain the optimum at all.\n\n**Why it matters** \u2014 The optimiser converges tidily, the waterfall shows a clean plateau, and one or more\nparameters sit against a bound. The result reads as a converged fit and is an artefact of the box. The\nopposite error \u2014 ten decades on every parameter \u2014 wastes starts in regions where the model is stiff or\nnon-integrable and makes the integration-failure fraction the binding constraint.\n\n**How to apply** \u2014 construction: 2\u20134 decades around a defensible nominal is the working default; widen where\nthe nominal is `default`-tier, narrow where it is measured. interpretation: a parameter at a\nbound is a statement about the bound. revision_proposal: `change_bounds` is the right move only when the\nbound was a guess, not when it encodes a physical limit.\n\n_Reviewed: \u2014_\n\n---\n\n### 2 \u00b7 Rate constants belong on a log scale\n\n**Pitfall** \u2014 Estimating rate constants on a linear scale when their plausible range spans decades.\n\n**Why it matters** \u2014 Linear-scale sampling puts almost every start in the top decade of the range; the\nlower decades are effectively unexplored. Gradients are equally distorted, and step sizes that suit one\nparameter are useless for another three decades away.\n\n**How to apply** \u2014 Rate constants, concentrations, and scaling factors are `log10`-scaled by default;\nadditive offsets and quantities that can legitimately be zero or negative stay `lin`. Bounds are still\nwritten as linear-scale values \u2014 the scale field, not the bound field, carries this.\n\n_Reviewed: \u2014_\n\n---\n\n### 3 \u00b7 The data window must bracket the dynamics you claim to estimate\n\n**Pitfall** \u2014 Estimating a rate whose characteristic time falls outside the interval the data actually\ncovers: a degradation rate from data ending long before anything degrades, or a fast association from data\nwhose first point is at 5 min.\n\n**Why it matters** \u2014 The parameter is not slightly uncertain, it is unconstrained, and the fit will not say\nso. Whatever value the optimiser lands on is arbitrary within a wide range and will be reported with\nconfidence unless a profile is computed.\n\n**How to apply** \u2014 construction: before marking a parameter for estimation, ask which part of the data\nconstrains it. If none, expect it in `cannot_distinguish` and consider fixing it. interpretation:\na flat profile on a rate whose timescale sits outside the data window is expected, not a surprise to explain\naway.\n\n_Reviewed: \u2014_\n\n---\n\n### 4 \u00b7 Conserved totals silently pin states\n\n**Pitfall** \u2014 A moiety conservation the modeller did not intend \u2014 usually from writing only interconversion\nreactions with no synthesis or degradation \u2014 fixes a total and therefore pins the accessible state space.\n\n**Why it matters** \u2014 The model then cannot respond to the perturbation in the way the question asks about,\nand this shows up as a stubborn misfit that invites structural moves. Meanwhile the initial values of the\nconserved set become a single parameter's worth of information, so estimating them all is a structural\nnon-identifiability.\n\n**How to apply** \u2014 construction: read the conservation-law advisory and confirm each class is intended. If a\ntotal is conserved by design, estimate the total and the fractions, not every state's initial value.\nevaluation_interpretation: check conservation before diagnosing a missing reaction.\n\n_Reviewed: \u2014_\n\n---\n\n### 5 \u00b7 Relative data needs one scale fixed somewhere\n\n**Pitfall** \u2014 With arbitrary-unit data, the model's absolute concentrations and the observable's scaling\nfactor are only determined as a product. Estimating both freely leaves a perfectly flat direction.\n\n**Why it matters** \u2014 The likelihood is invariant along that direction, so the optimiser wanders, profiles\nrun flat in both parameters, and the diagnosis reads as \"the data is uninformative\" when in fact the\ninformation is there and the parameterisation is redundant.\n\n**How to apply** \u2014 Fix one scale: a known total protein amount, an initial condition set to 1, or a scaling\nfactor fixed to 1 for one observable. Then say in the report that concentrations are relative to that\nchoice. observation (scaling) and construction must not both leave the scale free.\n\n_Reviewed: \u2014_\n\n---\n\n### 6 \u00b7 Parameters at bounds after fitting are a finding, not a formality\n\n**Pitfall** \u2014 Recording \"converged\" while one or more estimates rest on their bounds.\n\n**Why it matters** \u2014 A parameter at a bound means the data wants a value the box forbids. Every uncertainty\nstatement about it is then wrong \u2014 the profile is truncated, the CI is an artefact of the box, and any\nprediction depending on it inherits that. It is also the most common way a genuine model error disguises\nitself as a converged fit.\n\n**How to apply** \u2014 interpretation: name every at-bound parameter and say whether widening is\nhonest (the bound was a guess) or whether the model is fighting a physical limit. revision_proposal: only\nthe first case justifies `change_bounds`.\n\n_Reviewed: \u2014_\n\n---\n\n### 7 \u00b7 Estimate the combination the data sees, not the pair\n\n**Pitfall** \u2014 Estimating `k_on` and `k_off` separately when the data only ever sees equilibrium binding, or\na synthesis and a degradation rate when the data only sees the steady-state ratio.\n\n**Why it matters** \u2014 The pair is unidentifiable but their combination (`Kd`, the steady-state level) may be\ntightly determined. Reporting two flat parameters hides a sharp result; reporting them as independently\nestimated values overclaims two numbers where the data supports one.\n\n**How to apply** \u2014 construction: where binding is fast relative to the data's resolution, parameterise by\n`Kd` directly. interpretation: put the pair in `cannot_distinguish` and the determined\ncombination in `nonetheless_determined` \u2014 both directions, in the same report.\n\n_Reviewed: \u2014_\n\n---\n\n### 8 \u00b7 Stiffness shows up where the optimiser goes, not where you tested\n\n**Pitfall** \u2014 A model that integrates cleanly at nominal parameters and fails across large parts of its own\nbounds box.\n\n**Why it matters** \u2014 Failed starts are dropped rather than counted, so the surviving starts form a plateau\nthat reads as convergence. It is survivorship: the \"converged\" region is simply the region where the solver\ndid not die, and it may exclude the optimum entirely.\n\n**How to apply** \u2014 construction: check integrability at sampled corners of the bounds box, not just at\nnominals; a denominator that can approach zero or an exponential of an unbounded expression is the usual\nculprit. interpretation: read the integration-failure fraction before reading the waterfall.\n\n_Reviewed: \u2014_\n\n\n# Reaction templates\n<!-- provenance: Jan Hasenauer, Octomod v0 agent specification (2026).\n     Human-curated lineage \u2014 inherit verbatim, extend only with curated content. -->\n\nStandard forms; prefer these over invented constructs, and name the template\nused in the decision rationale.\n\n- Synthesis: `\u2205 -> X` (zero-order or regulated rate)\n- Degradation: `X -> \u2205` (first-order unless evidence says otherwise)\n- Reversible binding: `A + B <-> A_B`\n- Enzymatic conversion: `S -> P` with enzyme `E` as MODIFIER\n  (Michaelis-Menten when QSS holds at the declared timescale)\n- Phosphorylation: `X -> X_p` with kinase as modifier\n- Dephosphorylation: `X_p -> X` with phosphatase as modifier\n- Transport: `X_c1 -> X_c2` (compartments explicit)\n- Transcriptional activation: regulator modifies mRNA synthesis rate\n- Translation: `mRNA -> mRNA + protein` (or simplified synthesis term)\n- Inhibition: inhibitor enters as a MODIFIER in the rate law \u2014 never as a\n  consumed reactant unless it is mechanistically consumed\n- Distinct species for: compartments, PTM states, activity states,\n  bound/unbound forms, complexes \u2014 whenever the distinction affects dynamics\n- Preserve mass balance for metabolites and binding; when a signalling-state\n  model simplifies it deliberately, SAY SO in the build report\n",
  "measurement-tech": "# measurement-tech \u2014 pitfalls\n\n`draft-unreviewed`. Eight entries. Each is a claim an expert should confirm, edit or delete individually;\na pack returned with no edits has not been reviewed.\n\n---\n\n### 1 \u00b7 The loading control has usually already been divided out\n\n**Pitfall** \u2014 Adding an offset to immunoblot data on the assumption that the background is still in there.\nIn most published quantifications the signal has already been normalised to a loading control\n(actin, tubulin, total protein), and often to a reference lane as well.\n\n**Why it matters** \u2014 An unnecessary offset is a free parameter that absorbs real dynamics, most visibly at\nearly timepoints where the model's baseline carries information. It fits better and identifies less, and\nnothing downstream announces it.\n\n**How to apply** \u2014 observation (scaling): for normalised blot data the default is a scaling factor with no offset.\nAdd an offset only where the description states that background was not subtracted, or where blank lanes are\nreported as nonzero. assembly_verification: an offset on normalised blot data with no stated background story is a\nconcern.\n\n_Reviewed: \u2014_\n\n---\n\n### 2 \u00b7 Densitometry saturates \u2014 the top of the range is censored\n\n**Pitfall** \u2014 Treating the highest signals on a blot as ordinary measurements. Film and, at high exposure,\ndigital detection compress the top of the range: the true signal keeps rising and the recorded one does not.\n\n**Why it matters** \u2014 Saturated points pull the fitted maximum down and flatten exactly the part of the\nresponse that identifies saturation parameters and maximal rates. The residuals look like a model that\novershoots, which invites a structural move \u2014 a rate law change to fix a detector artefact.\n\n**How to apply** \u2014 data_extraction: flag series where the top values plateau at a suspiciously common value\nor where several conditions share an identical maximum. interpretation: consider censoring before\nconcluding the model overshoots at high dose.\n\n_Reviewed: \u2014_\n\n---\n\n### 3 \u00b7 SD-vs-SEM mislabelling is endemic, and `n` decides it\n\n**Pitfall** \u2014 Taking the caption at its word. In several subfields error bars are SEM by convention even\nwhen labelled SD, and the reverse also happens; many captions state neither.\n\n**Why it matters** \u2014 Using SEM as sigma underweights every point by a factor of \u221an \u2014 a silent, uniform\ndistortion of every likelihood weight that no downstream diagnostic reveals. The fit looks confident and the\nuncertainty is wrong by a constant factor.\n\n**How to apply** \u2014 data_extraction: record `error_type` as stated **and** flag any conflict with convention;\nrecord `n` wherever available, since without it the SEM\u2192SD conversion is impossible. observation (noise): with\n`error_type: sem` and no `n`, estimate sigma rather than using the column. assembly_verification: an SEM column\nused directly as sigma is a failed verdict.\n\n_Reviewed: \u2014_\n\n---\n\n### 4 \u00b7 Arbitrary units mean a scaling factor, full stop\n\n**Pitfall** \u2014 Treating a.u., \"relative intensity\", \"fold change\" or \"% of control\" as if the numbers had\nabsolute meaning, because their magnitude happens to sit near the model's.\n\n**Why it matters** \u2014 The measurement is proportional to the model quantity by an unknown constant. Without a\nscaling parameter, that constant is silently forced to 1, and the estimation compensates by distorting\nwhichever model parameters set the amplitude \u2014 usually total amounts and synthesis rates.\n\n**How to apply** \u2014 data_extraction: declare `units: arbitrary` rather than guessing. observation (scaling): a\nscaling factor, shared across conditions unless the experiment argues otherwise. This is also the case the\nmagnitude-reconciliation gate is built to catch, so a failure there usually means this entry was ignored.\n\n_Reviewed: \u2014_\n\n---\n\n### 5 \u00b7 Replicate lanes are usually independent, not paired\n\n**Pitfall** \u2014 Assuming replicates on a blot or plate are matched across conditions, and encoding them as\npaired measurements.\n\n**Why it matters** \u2014 Biological replicates from separate cultures on separate days share no per-replicate\neffect worth pairing; treating them as paired invents structure. The reverse case \u2014 technical replicates\nfrom one lysate treated as independent biological replicates \u2014 inflates the effective `n` and shrinks every\nuncertainty statement.\n\n**How to apply** \u2014 data_extraction: record replicate identity as it appears; flag when the description does\nnot distinguish technical from biological replicates, since the two carry different information and only the\ndescription can tell them apart.\n\n_Reviewed: \u2014_\n\n---\n\n### 6 \u00b7 Background subtraction produces genuine small negatives\n\n**Pitfall** \u2014 Treating negative values after background subtraction as data-entry errors, and clipping them\nto zero or dropping the rows.\n\n**Why it matters** \u2014 Near-zero signal minus an estimated background is negative about half the time; that is\nthe noise doing its job. Clipping biases every low measurement upward, which systematically distorts\nbaselines and early timepoints \u2014 exactly where initial conditions and basal rates are identified.\n\n**How to apply** \u2014 data_extraction: keep the rows, flag if you must, never drop. observation (noise): additive\nnormal accommodates negatives; a log transformation or a proportional noise model does not, which rules\nboth out for background-subtracted data.\n\n_Reviewed: \u2014_\n\n---\n\n### 7 \u00b7 Normalisation moves the error structure with it\n\n**Pitfall** \u2014 Applying a noise model chosen for a raw readout to data that has been divided by a control, a\nloading standard or its own t=0 value.\n\n**Why it matters** \u2014 The normaliser carries its own error, which propagates into every normalised point, and\nthe ratio's error is no longer the numerator's. Normalising to t=0 additionally makes the first point exact\nby construction \u2014 a zero-variance measurement the likelihood will happily treat as infinitely informative if\nsigma is small there.\n\n**How to apply** \u2014 data_extraction: flag the normalisation explicitly, naming what it was normalised to.\nobservation_model (noise): state which readout the sigma refers to \u2014 raw or normalised. Consider whether the reference\npoint should carry data at all.\n\n_Reviewed: \u2014_\n\n---\n\n### 8 \u00b7 A digitised figure inherits the axis, not the data\n\n**Pitfall** \u2014 Treating points read off a published figure as equivalent to tabulated values.\n\n**Why it matters** \u2014 Digitisation drift is systematic, not random: a misplaced axis calibration shifts or\nscales an entire series, and log axes make small pixel errors into large value errors. The numbers stay\nplausible, so nothing flags them, and the resulting bias is attributed to the model.\n\n**How to apply** \u2014 data_extraction: record that a source is digitised, check the extracted range against the\nfigure's stated axis limits, and flag any series whose endpoints fall outside them. Cross-source\ndisagreement on a shared condition is a recorded finding, never resolved silently in favour of the more\nconvenient series.\n\n_Reviewed: \u2014_\n"
}
```

# Output contract
{"verdicts": [{"aspect": "...", "ok": true, "note": "..."}], "overall": "pass|concerns"}
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "verdicts": [
  {
   "aspect": "noise model vs readout technique",
   "ok": true,
   "note": "Checked against the lab note's stated error model for the intact-mass MS readout. Every observable uses a normal distribution on a lin scale. Its noise SD is observableParameter1 × noiseParameter1, which is the per-spectrum factor times the single sigma_ctd_ms. This matches the note's claims: additive Gaussian error, one SD for all peaks, scaled by the same factor that maps amounts to intensities at that time point. Reusing observableParameter1 in noiseFormula guarantees the noise and signal factors are the same parameter. The lin scale tolerates the 19 exact zeros, where a log transform would fail. No error column exists, so there is no SD/SEM question, and estimating sigma is the only option. Doubt only: MS peak noise often grows with intensity. The assembly follows the note's additive claim, which is defensible, but residuals at 60 and 120 min should be checked for intensity dependence."
  },
  {
   "aspect": "structurally exact likelihood terms under the shared estimated sigma",
   "ok": false,
   "note": "Checked the t=0 and t=960 rows against the initial-condition encoding and the per-time-point scales. At t=0 every candidate mechanism reproduces all nine terms with zero residual by construction. CTD_1..CTD_8 start at exactly 0, matching the exact-zero data. The free sc_ctd_ms_t0 (best value about 0.01, inside its box) absorbs the single nonzero peak. At t=960 the free sc_ctd_ms_t960 likewise absorbs phos8. These terms carry no information about mechanism, but they still count in the likelihood and pull the shared sigma_ctd_ms estimate toward zero. With sigma estimated, likelihood differences between candidates scale with the total number of terms. That inflates the evidence separating mechanisms, which affects the Akaike weights the intent requires to be reported honestly, as well as profile-based intervals. The data flags asked the observation model to account for the exact zeros. Nothing in observables or parameters shows that this was considered. Point estimates of kmod, cp and q_proc are not affected; sigma and the model-selection evidence are."
  },
  {
   "aspect": "condition encoding vs experiment description",
   "ok": true,
   "note": "Reconstructed the single treatment from its overrides alone: 100 µM CTD, all in CTD_0; ATP 3000 µM (3 mM); ADP 0; PTEFb 1. This matches the note's 8-repeat substrate at 100 µM, 3 mM ATP, a catalytic kinase that is never consumed, and t=0 data with all signal in phos0. One condition matches the note's one in vitro treatment sampled over time. No pre-equilibration is used, which is correct: there is no pre-treatment, and the reaction starts at mixing. Fixing PTEFb at 1 is consistent with the glossary's statement that kinase concentration is absorbed into kmod. Fixed K_ATP of 50 µM is harmless, since at most 800 µM ATP is consumed out of 3000."
  },
  {
   "aspect": "scaling and offset vs declared units",
   "ok": true,
   "note": "Checked against the note's statement that intensities are arbitrary, drift between injections and are not comparable across time points. There are four per-time-point scale factors (t0, t60, t120, t960). This is per-spectrum scaling with an explicit stated reason, not unexplained per-condition scaling. No information is lost that the data ever held, because cross-time amounts are declared incomparable, and each time point keeps its within-spectrum shape. The factors are identifiable rather than flat: the model total is fixed and conserved at 100 µM, so each factor is pinned near row-sum/100 (about 0.0085 to 0.041), well inside the 1e-3 to 1e3 log10 box. There is no offset, which is appropriate: the note gives no background story, and the exact-zero empty peaks argue against one. Consequence to carry into the report: each informative spectrum (60, 120 min) gives up one degree of freedom to its factor."
  },
  {
   "aspect": "observable mapping vs what the assay measures",
   "ok": true,
   "note": "Checked each mapping against the glossary lumps and the intact-mass readout. Each phosN observable maps to CTD_n, which lumps all C(8,n) configurations with n marks. That is exactly what one mass peak sees, since position is not resolved and the one-bit-per-repeat convention makes count equal phosphate number. No lumped state is omitted. ATP, ADP and PTEFb are correctly left unobserved, and no kinase-bound substrate species exists that would need adding to a total. I cannot verify from these artifacts that each measurement row uses the observable id matching its own time point; the ids hard-wire the time point. Doubt: the mapping assumes every phospho-form ionises with the same response factor within a spectrum, as the note's model also does. A count-dependent response would tilt peak heights systematically with n, in a way the count-cooperativity factor cp could absorb. This is a confound for the cooperativity conclusion that should be named in the report, not a fault in the table."
  },
  {
   "aspect": "hypothesis space vs the mechanistic question asked",
   "ok": false,
   "note": "Checked the glossary species and the parameters table against the intent and the lab note. The note asks that neighbour-dependent modification be fitted rather than settled by argument, explicitly inviting the 256-configuration model. The assembly holds only count-indexed species CTD_0..CTD_8, plus switches for count cooperativity (cp) and processivity (q_proc). A rate that depends on whether a repeat's immediate neighbours are modified is not a function of CTD_n alone, so it cannot be expressed in this state space. No parameter for it exists. As assembled, the comparison covers only two of the three hypotheses the intent names, and Akaike weights would be computed over a set that omits the hypothesis the note most wants tested. Minor, related: q_proc's distributive null value of 0 lies outside its own log10 box (1e-4 to 0.99) and has no finite log10 value. The base model's fixed 0 on a log10 scale may need checking in the tooling, and the switched-on test compares against q_proc ≥ 1e-4 rather than exactly distributive."
  }
 ],
 "overall": "concerns"
}
````
