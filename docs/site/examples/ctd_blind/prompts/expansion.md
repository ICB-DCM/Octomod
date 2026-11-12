# Prompt · `expansion` (round 0)

The **expansion** agent turns the open questions into candidate models (S1). Below is the exact prompt it was sent in this run (184,209 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 4 times here; the record keeps the prompt and reply of the last call, which carries the earlier attempts in its `attempt_history`.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Expansions: write a discrimination round's candidates as declared differences from the base

Construction wrote the base, the structure every candidate shares, and the engine has tested it (it builds,
simulates, stays non-negative, keeps its declared constants). You write each candidate as a difference from it; the
engine builds and tests each one. You never write a candidate out in full, and that is what keeps the comparison
honest: a candidate can differ from the base only in what you declare.

## What you receive
`intent`, `experiment_description` (the lab note), `domain_packs`, `base_model` with the decisions construction
recorded for it, `instruction`, and, when there is literature, `retrieved_evidence` with `evidence_instruction`
(cite items as construction does). With grounding on: `essential_reactions` (the base's set, each with its grade
and origin), `prior_reactions` (every reaction the dossier describes, graded), `variants_floor` (the band a reaction you
add must reach, with its reason), `knowledge_summary`, `known_facts` and `grounding_instruction`. On a repair: your `previous_reply`, with `human_feedback` (a person asked for a
change) or `previous_attempt_errors` (the engine named the candidate and symbol at fault), and possibly
`base_changed_instruction`. No data reaches you, and none may be assumed: you are choosing hypotheses, not fitting.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`candidates` and `build_report`, both required (shape: Output contract). A candidate is `{id, label, rationale,
set_parameters, on_antimony_patch, adds_parameters, entity_glossary}`; everything but `id` is optional, and a
candidate with no difference is the base. Between two and the declared maximum candidates, ids unique.

## Rules that get your reply refused
- `set_parameters` changes existing base parameters only — a switch value (`comp` 0 → 1), an estimate flag, bounds —
  with `lb`/`ub` whenever you set `estimate: true` on a parameter the base keeps fixed without bounds. A new symbol
  never goes here.
- `on_antimony_patch` uses the axis grammar: `{"replace_reaction": "<a base reaction id, exactly>", "with": "<the
  whole new line>"}` or `{"append": ["<lines>"]}`, one patch or a list. Every symbol it introduces is declared in
  `adds_parameters` with nominal value, unit, bounds, estimate flag and source.
- A candidate differs from the base only in its tested feature; if one combines two, its rationale says so.
- No two candidates identical once built.
- With grounding on, a conversion you add (a new reaction, or a base reaction rewired onto other species) is
  annotated against `prior_reactions`. In advisory mode (the default) one below `variants_floor`, or one no entry
  describes, is kept and flagged on the scope card. In strict mode it is graded at or above `variants_floor`, or it is
  named in `missing` (`{equation, why}`): the engine spends the round's one targeted search on those, admits what
  reaches the floor, and drops a candidate whose addition is still below it, with the reason on the scope card. A
  candidate never removes a required reaction.

## How to judge
- Read construction's decisions first: they say which features were built in as switches and how. Prefer a switch to
  a new patch, and patch only where the feature cannot be a switch the base carries.
- A switch that matters only when another is on (a site parameter that acts only under competition) is inert alone.
  A candidate that differs from another only in an inert switch behaves identically, and the engine will find it so.
- Include the base itself when the comparison needs the model with no tested feature switched on: it is the
  reference every "required" verdict is measured against.
- If the intent's comparison needs a feature the base cannot express, add it as a patch and say so in the build
  report, rather than leaving the feature out.
- On a repair, revise that reply: change only what the request or the error implicates and keep every id, value and
  patch it does not. When `base_changed_instruction` is present the base was redrafted after your reply: rebuild the
  same candidates on the new base and say in the build report where it forced a change.

## Mistakes we have seen
- Candidates that differ only in a switch that is inert on its own.


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

## domain_packs
```json
{
  "general-dynamics": "# general-dynamics \u2014 pitfalls\n\n`draft-unreviewed`. Eight entries. Each is a claim an expert should confirm, edit or delete individually;\na pack returned with no edits has not been reviewed.\n\n---\n\n### 1 \u00b7 Bounds spanning too few decades strangle multistart\n\n**Pitfall** \u2014 Bounds set as a tight cordon around a nominal value (half an order of magnitude either side)\nlook careful and are not. Multistart then samples a box that may not contain the optimum at all.\n\n**Why it matters** \u2014 The optimiser converges tidily, the waterfall shows a clean plateau, and one or more\nparameters sit against a bound. The result reads as a converged fit and is an artefact of the box. The\nopposite error \u2014 ten decades on every parameter \u2014 wastes starts in regions where the model is stiff or\nnon-integrable and makes the integration-failure fraction the binding constraint.\n\n**How to apply** \u2014 construction: 2\u20134 decades around a defensible nominal is the working default; widen where\nthe nominal is `default`-tier, narrow where it is measured. interpretation: a parameter at a\nbound is a statement about the bound. revision_proposal: `change_bounds` is the right move only when the\nbound was a guess, not when it encodes a physical limit.\n\n_Reviewed: \u2014_\n\n---\n\n### 2 \u00b7 Rate constants belong on a log scale\n\n**Pitfall** \u2014 Estimating rate constants on a linear scale when their plausible range spans decades.\n\n**Why it matters** \u2014 Linear-scale sampling puts almost every start in the top decade of the range; the\nlower decades are effectively unexplored. Gradients are equally distorted, and step sizes that suit one\nparameter are useless for another three decades away.\n\n**How to apply** \u2014 Rate constants, concentrations, and scaling factors are `log10`-scaled by default;\nadditive offsets and quantities that can legitimately be zero or negative stay `lin`. Bounds are still\nwritten as linear-scale values \u2014 the scale field, not the bound field, carries this.\n\n_Reviewed: \u2014_\n\n---\n\n### 3 \u00b7 The data window must bracket the dynamics you claim to estimate\n\n**Pitfall** \u2014 Estimating a rate whose characteristic time falls outside the interval the data actually\ncovers: a degradation rate from data ending long before anything degrades, or a fast association from data\nwhose first point is at 5 min.\n\n**Why it matters** \u2014 The parameter is not slightly uncertain, it is unconstrained, and the fit will not say\nso. Whatever value the optimiser lands on is arbitrary within a wide range and will be reported with\nconfidence unless a profile is computed.\n\n**How to apply** \u2014 construction: before marking a parameter for estimation, ask which part of the data\nconstrains it. If none, expect it in `cannot_distinguish` and consider fixing it. interpretation:\na flat profile on a rate whose timescale sits outside the data window is expected, not a surprise to explain\naway.\n\n_Reviewed: \u2014_\n\n---\n\n### 4 \u00b7 Conserved totals silently pin states\n\n**Pitfall** \u2014 A moiety conservation the modeller did not intend \u2014 usually from writing only interconversion\nreactions with no synthesis or degradation \u2014 fixes a total and therefore pins the accessible state space.\n\n**Why it matters** \u2014 The model then cannot respond to the perturbation in the way the question asks about,\nand this shows up as a stubborn misfit that invites structural moves. Meanwhile the initial values of the\nconserved set become a single parameter's worth of information, so estimating them all is a structural\nnon-identifiability.\n\n**How to apply** \u2014 construction: read the conservation-law advisory and confirm each class is intended. If a\ntotal is conserved by design, estimate the total and the fractions, not every state's initial value.\nevaluation_interpretation: check conservation before diagnosing a missing reaction.\n\n_Reviewed: \u2014_\n\n---\n\n### 5 \u00b7 Relative data needs one scale fixed somewhere\n\n**Pitfall** \u2014 With arbitrary-unit data, the model's absolute concentrations and the observable's scaling\nfactor are only determined as a product. Estimating both freely leaves a perfectly flat direction.\n\n**Why it matters** \u2014 The likelihood is invariant along that direction, so the optimiser wanders, profiles\nrun flat in both parameters, and the diagnosis reads as \"the data is uninformative\" when in fact the\ninformation is there and the parameterisation is redundant.\n\n**How to apply** \u2014 Fix one scale: a known total protein amount, an initial condition set to 1, or a scaling\nfactor fixed to 1 for one observable. Then say in the report that concentrations are relative to that\nchoice. observation (scaling) and construction must not both leave the scale free.\n\n_Reviewed: \u2014_\n\n---\n\n### 6 \u00b7 Parameters at bounds after fitting are a finding, not a formality\n\n**Pitfall** \u2014 Recording \"converged\" while one or more estimates rest on their bounds.\n\n**Why it matters** \u2014 A parameter at a bound means the data wants a value the box forbids. Every uncertainty\nstatement about it is then wrong \u2014 the profile is truncated, the CI is an artefact of the box, and any\nprediction depending on it inherits that. It is also the most common way a genuine model error disguises\nitself as a converged fit.\n\n**How to apply** \u2014 interpretation: name every at-bound parameter and say whether widening is\nhonest (the bound was a guess) or whether the model is fighting a physical limit. revision_proposal: only\nthe first case justifies `change_bounds`.\n\n_Reviewed: \u2014_\n\n---\n\n### 7 \u00b7 Estimate the combination the data sees, not the pair\n\n**Pitfall** \u2014 Estimating `k_on` and `k_off` separately when the data only ever sees equilibrium binding, or\na synthesis and a degradation rate when the data only sees the steady-state ratio.\n\n**Why it matters** \u2014 The pair is unidentifiable but their combination (`Kd`, the steady-state level) may be\ntightly determined. Reporting two flat parameters hides a sharp result; reporting them as independently\nestimated values overclaims two numbers where the data supports one.\n\n**How to apply** \u2014 construction: where binding is fast relative to the data's resolution, parameterise by\n`Kd` directly. interpretation: put the pair in `cannot_distinguish` and the determined\ncombination in `nonetheless_determined` \u2014 both directions, in the same report.\n\n_Reviewed: \u2014_\n\n---\n\n### 8 \u00b7 Stiffness shows up where the optimiser goes, not where you tested\n\n**Pitfall** \u2014 A model that integrates cleanly at nominal parameters and fails across large parts of its own\nbounds box.\n\n**Why it matters** \u2014 Failed starts are dropped rather than counted, so the surviving starts form a plateau\nthat reads as convergence. It is survivorship: the \"converged\" region is simply the region where the solver\ndid not die, and it may exclude the optimum entirely.\n\n**How to apply** \u2014 construction: check integrability at sampled corners of the bounds box, not just at\nnominals; a denominator that can approach zero or an exponential of an unbounded expression is the usual\nculprit. interpretation: read the integration-failure fraction before reading the waterfall.\n\n_Reviewed: \u2014_\n\n\n# Reaction templates\n<!-- provenance: Jan Hasenauer, Octomod v0 agent specification (2026).\n     Human-curated lineage \u2014 inherit verbatim, extend only with curated content. -->\n\nStandard forms; prefer these over invented constructs, and name the template\nused in the decision rationale.\n\n- Synthesis: `\u2205 -> X` (zero-order or regulated rate)\n- Degradation: `X -> \u2205` (first-order unless evidence says otherwise)\n- Reversible binding: `A + B <-> A_B`\n- Enzymatic conversion: `S -> P` with enzyme `E` as MODIFIER\n  (Michaelis-Menten when QSS holds at the declared timescale)\n- Phosphorylation: `X -> X_p` with kinase as modifier\n- Dephosphorylation: `X_p -> X` with phosphatase as modifier\n- Transport: `X_c1 -> X_c2` (compartments explicit)\n- Transcriptional activation: regulator modifies mRNA synthesis rate\n- Translation: `mRNA -> mRNA + protein` (or simplified synthesis term)\n- Inhibition: inhibitor enters as a MODIFIER in the rate law \u2014 never as a\n  consumed reactant unless it is mechanistically consumed\n- Distinct species for: compartments, PTM states, activity states,\n  bound/unbound forms, complexes \u2014 whenever the distinction affects dynamics\n- Preserve mass balance for metabolites and binding; when a signalling-state\n  model simplifies it deliberately, SAY SO in the build report\n",
  "measurement-tech": "# measurement-tech \u2014 pitfalls\n\n`draft-unreviewed`. Eight entries. Each is a claim an expert should confirm, edit or delete individually;\na pack returned with no edits has not been reviewed.\n\n---\n\n### 1 \u00b7 The loading control has usually already been divided out\n\n**Pitfall** \u2014 Adding an offset to immunoblot data on the assumption that the background is still in there.\nIn most published quantifications the signal has already been normalised to a loading control\n(actin, tubulin, total protein), and often to a reference lane as well.\n\n**Why it matters** \u2014 An unnecessary offset is a free parameter that absorbs real dynamics, most visibly at\nearly timepoints where the model's baseline carries information. It fits better and identifies less, and\nnothing downstream announces it.\n\n**How to apply** \u2014 observation (scaling): for normalised blot data the default is a scaling factor with no offset.\nAdd an offset only where the description states that background was not subtracted, or where blank lanes are\nreported as nonzero. assembly_verification: an offset on normalised blot data with no stated background story is a\nconcern.\n\n_Reviewed: \u2014_\n\n---\n\n### 2 \u00b7 Densitometry saturates \u2014 the top of the range is censored\n\n**Pitfall** \u2014 Treating the highest signals on a blot as ordinary measurements. Film and, at high exposure,\ndigital detection compress the top of the range: the true signal keeps rising and the recorded one does not.\n\n**Why it matters** \u2014 Saturated points pull the fitted maximum down and flatten exactly the part of the\nresponse that identifies saturation parameters and maximal rates. The residuals look like a model that\novershoots, which invites a structural move \u2014 a rate law change to fix a detector artefact.\n\n**How to apply** \u2014 data_extraction: flag series where the top values plateau at a suspiciously common value\nor where several conditions share an identical maximum. interpretation: consider censoring before\nconcluding the model overshoots at high dose.\n\n_Reviewed: \u2014_\n\n---\n\n### 3 \u00b7 SD-vs-SEM mislabelling is endemic, and `n` decides it\n\n**Pitfall** \u2014 Taking the caption at its word. In several subfields error bars are SEM by convention even\nwhen labelled SD, and the reverse also happens; many captions state neither.\n\n**Why it matters** \u2014 Using SEM as sigma underweights every point by a factor of \u221an \u2014 a silent, uniform\ndistortion of every likelihood weight that no downstream diagnostic reveals. The fit looks confident and the\nuncertainty is wrong by a constant factor.\n\n**How to apply** \u2014 data_extraction: record `error_type` as stated **and** flag any conflict with convention;\nrecord `n` wherever available, since without it the SEM\u2192SD conversion is impossible. observation (noise): with\n`error_type: sem` and no `n`, estimate sigma rather than using the column. assembly_verification: an SEM column\nused directly as sigma is a failed verdict.\n\n_Reviewed: \u2014_\n\n---\n\n### 4 \u00b7 Arbitrary units mean a scaling factor, full stop\n\n**Pitfall** \u2014 Treating a.u., \"relative intensity\", \"fold change\" or \"% of control\" as if the numbers had\nabsolute meaning, because their magnitude happens to sit near the model's.\n\n**Why it matters** \u2014 The measurement is proportional to the model quantity by an unknown constant. Without a\nscaling parameter, that constant is silently forced to 1, and the estimation compensates by distorting\nwhichever model parameters set the amplitude \u2014 usually total amounts and synthesis rates.\n\n**How to apply** \u2014 data_extraction: declare `units: arbitrary` rather than guessing. observation (scaling): a\nscaling factor, shared across conditions unless the experiment argues otherwise. This is also the case the\nmagnitude-reconciliation gate is built to catch, so a failure there usually means this entry was ignored.\n\n_Reviewed: \u2014_\n\n---\n\n### 5 \u00b7 Replicate lanes are usually independent, not paired\n\n**Pitfall** \u2014 Assuming replicates on a blot or plate are matched across conditions, and encoding them as\npaired measurements.\n\n**Why it matters** \u2014 Biological replicates from separate cultures on separate days share no per-replicate\neffect worth pairing; treating them as paired invents structure. The reverse case \u2014 technical replicates\nfrom one lysate treated as independent biological replicates \u2014 inflates the effective `n` and shrinks every\nuncertainty statement.\n\n**How to apply** \u2014 data_extraction: record replicate identity as it appears; flag when the description does\nnot distinguish technical from biological replicates, since the two carry different information and only the\ndescription can tell them apart.\n\n_Reviewed: \u2014_\n\n---\n\n### 6 \u00b7 Background subtraction produces genuine small negatives\n\n**Pitfall** \u2014 Treating negative values after background subtraction as data-entry errors, and clipping them\nto zero or dropping the rows.\n\n**Why it matters** \u2014 Near-zero signal minus an estimated background is negative about half the time; that is\nthe noise doing its job. Clipping biases every low measurement upward, which systematically distorts\nbaselines and early timepoints \u2014 exactly where initial conditions and basal rates are identified.\n\n**How to apply** \u2014 data_extraction: keep the rows, flag if you must, never drop. observation (noise): additive\nnormal accommodates negatives; a log transformation or a proportional noise model does not, which rules\nboth out for background-subtracted data.\n\n_Reviewed: \u2014_\n\n---\n\n### 7 \u00b7 Normalisation moves the error structure with it\n\n**Pitfall** \u2014 Applying a noise model chosen for a raw readout to data that has been divided by a control, a\nloading standard or its own t=0 value.\n\n**Why it matters** \u2014 The normaliser carries its own error, which propagates into every normalised point, and\nthe ratio's error is no longer the numerator's. Normalising to t=0 additionally makes the first point exact\nby construction \u2014 a zero-variance measurement the likelihood will happily treat as infinitely informative if\nsigma is small there.\n\n**How to apply** \u2014 data_extraction: flag the normalisation explicitly, naming what it was normalised to.\nobservation_model (noise): state which readout the sigma refers to \u2014 raw or normalised. Consider whether the reference\npoint should carry data at all.\n\n_Reviewed: \u2014_\n\n---\n\n### 8 \u00b7 A digitised figure inherits the axis, not the data\n\n**Pitfall** \u2014 Treating points read off a published figure as equivalent to tabulated values.\n\n**Why it matters** \u2014 Digitisation drift is systematic, not random: a misplaced axis calibration shifts or\nscales an entire series, and log axes make small pixel errors into large value errors. The numbers stay\nplausible, so nothing flags them, and the resulting bias is attributed to the model.\n\n**How to apply** \u2014 data_extraction: record that a source is digitised, check the extracted range against the\nfigure's stated axis limits, and flag any series whose endpoints fall outside them. Cross-source\ndisagreement on a shared condition is a recorded finding, never resolved silently in favour of the more\nconvenient series.\n\n_Reviewed: \u2014_\n"
}
```
## base_model
```json
{
  "antimony": "model ctd_ptefb_counts\n  // CTD_n: CTD molecules with n of 8 repeats phosphorylated (one bit per repeat)\n  compartment vial = 1;\n  species CTD_0 in vial, CTD_1 in vial, CTD_2 in vial, CTD_3 in vial, CTD_4 in vial;\n  species CTD_5 in vial, CTD_6 in vial, CTD_7 in vial, CTD_8 in vial;\n  species ATP in vial, ADP in vial, PTEFb in vial;\n  CTD_0 = 100; CTD_1 = 0; CTD_2 = 0; CTD_3 = 0; CTD_4 = 0;\n  CTD_5 = 0; CTD_6 = 0; CTD_7 = 0; CTD_8 = 0;\n  ATP = 3000; ADP = 0; PTEFb = 1;\n  kmod = 0.01; cp = 1; q_proc = 0; K_ATP = 50;\n  // single-repeat encounters: one modification per binding event (distributive)\n  J0: CTD_0 + ATP -> CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*(1 - q_proc)*CTD_0;\n  J1: CTD_1 + ATP -> CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*(1 - q_proc)*CTD_1;\n  J2: CTD_2 + ATP -> CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*(1 - q_proc)*CTD_2;\n  J3: CTD_3 + ATP -> CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*(1 - q_proc)*CTD_3;\n  J4: CTD_4 + ATP -> CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*(1 - q_proc)*CTD_4;\n  J5: CTD_5 + ATP -> CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*3*cp^5*(1 - q_proc)*CTD_5;\n  J6: CTD_6 + ATP -> CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*cp^6*(1 - q_proc)*CTD_6;\n  J7: CTD_7 + ATP -> CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*CTD_7;\n  // processive encounters: j repeats per binding event, continuation probability q_proc (0 in base)\n  Jp0_2: CTD_0 + 2 ATP -> CTD_2 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc*(1 - q_proc)*CTD_0;\n  Jp0_3: CTD_0 + 3 ATP -> CTD_3 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^2*(1 - q_proc)*CTD_0;\n  Jp0_4: CTD_0 + 4 ATP -> CTD_4 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^3*(1 - q_proc)*CTD_0;\n  Jp0_5: CTD_0 + 5 ATP -> CTD_5 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^4*(1 - q_proc)*CTD_0;\n  Jp0_6: CTD_0 + 6 ATP -> CTD_6 + 6 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^5*(1 - q_proc)*CTD_0;\n  Jp0_7: CTD_0 + 7 ATP -> CTD_7 + 7 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^6*(1 - q_proc)*CTD_0;\n  Jp0_8: CTD_0 + 8 ATP -> CTD_8 + 8 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^7*CTD_0;\n  Jp1_2: CTD_1 + 2 ATP -> CTD_3 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc*(1 - q_proc)*CTD_1;\n  Jp1_3: CTD_1 + 3 ATP -> CTD_4 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^2*(1 - q_proc)*CTD_1;\n  Jp1_4: CTD_1 + 4 ATP -> CTD_5 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^3*(1 - q_proc)*CTD_1;\n  Jp1_5: CTD_1 + 5 ATP -> CTD_6 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^4*(1 - q_proc)*CTD_1;\n  Jp1_6: CTD_1 + 6 ATP -> CTD_7 + 6 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^5*(1 - q_proc)*CTD_1;\n  Jp1_7: CTD_1 + 7 ATP -> CTD_8 + 7 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^6*CTD_1;\n  Jp2_2: CTD_2 + 2 ATP -> CTD_4 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc*(1 - q_proc)*CTD_2;\n  Jp2_3: CTD_2 + 3 ATP -> CTD_5 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^2*(1 - q_proc)*CTD_2;\n  Jp2_4: CTD_2 + 4 ATP -> CTD_6 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^3*(1 - q_proc)*CTD_2;\n  Jp2_5: CTD_2 + 5 ATP -> CTD_7 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^4*(1 - q_proc)*CTD_2;\n  Jp2_6: CTD_2 + 6 ATP -> CTD_8 + 6 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^5*CTD_2;\n  Jp3_2: CTD_3 + 2 ATP -> CTD_5 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc*(1 - q_proc)*CTD_3;\n  Jp3_3: CTD_3 + 3 ATP -> CTD_6 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc^2*(1 - q_proc)*CTD_3;\n  Jp3_4: CTD_3 + 4 ATP -> CTD_7 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc^3*(1 - q_proc)*CTD_3;\n  Jp3_5: CTD_3 + 5 ATP -> CTD_8 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc^4*CTD_3;\n  Jp4_2: CTD_4 + 2 ATP -> CTD_6 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*q_proc*(1 - q_proc)*CTD_4;\n  Jp4_3: CTD_4 + 3 ATP -> CTD_7 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*q_proc^2*(1 - q_proc)*CTD_4;\n  Jp4_4: CTD_4 + 4 ATP -> CTD_8 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*q_proc^3*CTD_4;\n  Jp5_2: CTD_5 + 2 ATP -> CTD_7 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*3*cp^5*q_proc*(1 - q_proc)*CTD_5;\n  Jp5_3: CTD_5 + 3 ATP -> CTD_8 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*3*cp^5*q_proc^2*CTD_5;\n  Jp6_2: CTD_6 + 2 ATP -> CTD_8 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*cp^6*q_proc*CTD_6;\nend",
  "parameters": [
    {
      "id": "kmod",
      "nominal_value": 0.01,
      "unit": "1/min per repeat per relative P-TEFb unit",
      "evidence_tier": "to_be_estimated",
      "source": "order-of-magnitude default: a per-repeat rate of 0.01/min half-modifies repeats by ~70 min, inside the 60-960 min sampling window",
      "estimate": true,
      "lb": 1e-05,
      "ub": 1.0,
      "varies_by": [],
      "set_per_condition": false
    },
    {
      "id": "cp",
      "nominal_value": 1.0,
      "unit": "dimensionless (fold change of per-repeat rate per mark already on the molecule)",
      "evidence_tier": "to_be_estimated",
      "source": "switch for count cooperativity; 1 = off (neutral value)",
      "estimate": false,
      "lb": 0.2,
      "ub": 5.0,
      "varies_by": [],
      "set_per_condition": false
    },
    {
      "id": "q_proc",
      "nominal_value": 0.0,
      "unit": "dimensionless probability of continuing to another repeat before release",
      "evidence_tier": "to_be_estimated",
      "source": "switch for processivity; 0 = off (strictly distributive, neutral value)",
      "estimate": false,
      "lb": 0.0001,
      "ub": 0.99,
      "varies_by": [],
      "set_per_condition": false
    },
    {
      "id": "K_ATP",
      "nominal_value": 50.0,
      "unit": "uM",
      "evidence_tier": "default",
      "source": "general knowledge: protein-kinase ATP Michaelis constants typically lie in the 10-100 uM range; not measured for this assay",
      "estimate": false,
      "lb": 5.0,
      "ub": 500.0,
      "varies_by": [],
      "set_per_condition": false
    }
  ],
  "entity_glossary": {
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
  },
  "decisions": [
    {
      "decision": "The base tracks how many of the 8 repeats each molecule carries (CTD_0..CTD_8), not which. It is the exact count lumping of the 256-configuration positional model whenever the per-repeat rate does not depend on the state of the immediate neighbours. The positional (neighbour) model is not written in this reply.",
      "rationale": "For every rate rule this base can switch on (independent repeats, count cooperativity cp^n, processive continuation that picks among the remaining unmodified repeats), all unmodified repeats of a molecule with n marks share one rate, so the 256 configurations are strongly lumpable by n and these 9 states reproduce the positional model's count distribution exactly. The 'nothing at all', 'cooperativity' and 'distributive vs processive' hypotheses therefore lose nothing by being counted. A nearest-neighbour effect is the one hypothesis that breaks the lumping, so it cannot be a switch on this base. Two previous replies to this brief failed the contract outright; a 1024-reaction hand enumeration, together with its 256-entry glossary and network, is not something this reply can carry reliably or check without execution. The next decision gives the exact rule so the positional model can be generated mechanically. A generator check comes free: at nb = 1 it must reproduce this base trajectory for trajectory.",
      "confidence": "medium"
    },
    {
      "decision": "Exact construction rule for the positional (neighbour) candidate, to be generated and not hand-written. Species C_b1b2b3b4b5b6b7b8 (b_i = 1 if repeat i, numbered from the N-terminus, is phosphorylated), C_00000000 = 100 uM, all others 0. For every configuration and every unmodified repeat i, one reaction to the configuration with b_i = 1, consuming one ATP and producing one ADP. Rate: vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m*C, where n = marks on the molecule and m = marked immediate neighbours of i (0 to 2; repeats 1 and 8 have one neighbour). New parameter nb, a fold change per marked neighbour: nominal and neutral value 1, bounds 0.01 to 100.",
      "rationale": "This is the minimal positional extension that separates 'a mark changes its neighbours' rate' (nb) from 'the rate depends on how many marks the molecule carries' (cp) and from neither (nb = cp = 1). It is 8*2^7 = 1024 reactions. Summing C over the C(8,n) configurations with n marks gives CTD_n, so readouts map onto it exactly as onto this base. nb < 1 (neighbour inhibition) jams molecules near 3 to 4 non-adjacent marks before slow filling, and that stall at intermediate counts between 2 h and 16 h is something cp alone cannot shape. nb > 1 gives nucleation-and-growth (bimodal 0-versus-high counts at 1 to 2 h), which cp > 1 and processivity also give. That is the likely indistinguishable set.",
      "confidence": "medium"
    },
    {
      "decision": "Distributive single-repeat steps J0..J7. Each unmodified repeat is modified at kmod*PTEFb*ATP/(K_ATP + ATP), mass action in the substrate at constant enzyme, so a molecule with n marks advances at (8 - n) times that rate. The template is phosphorylation X -> X_p with the kinase as modifier. Irreversible: no reverse step and no phosphatase.",
      "rationale": "The assay is purified kinase, CTD and ATP with no phosphatase, so removal of phosphate is not modelled. The kinase is catalytic and constant, so its level enters as a fixed multiplier. Mass action in CTD assumes the kinase is far from saturated by substrate. Neither the enzyme concentration nor a CTD Km is given, so saturation cannot be decided from the note. If all unmodified repeats bind alike, saturation would only reparameterise time by a factor common to every reaction (the same sequence of distributions, a different clock). With three post-zero time points that clock change is largely absorbed by kmod and cp, so it is named unresolved rather than built in. With cp = 1 and q_proc = 0 the count distribution is binomial(8, 1 - exp(-r*t)): the independent-repeat ('nothing at all') hypothesis.",
      "confidence": "medium"
    },
    {
      "decision": "Count-cooperativity switch cp: the per-repeat rate of a molecule carrying n marks is multiplied by cp^n. cp = 1 (base) turns it off; cp > 1 is positive and cp < 1 negative cooperativity between repeats.",
      "rationale": "One parameter expresses 'the rate depends only on how many repeats are already modified' as a constant fold change per existing mark, the additive free-energy form. It is the most parsimonious count-dependent law the data can constrain with 9 peaks at 3 informative time points. A free factor per n (7 parameters) would not be identifiable. Bounds 0.2 to 5 are 1.4 decades on cp but compound to ~10 decades on the n = 7 step. Wider bounds put the solver in stiff corners without adding plausible behaviour.",
      "confidence": "medium"
    },
    {
      "decision": "Processivity switch q_proc on reactions Jp<n>_<j>. A binding event on a molecule with n marks starts at the same encounter rate as a distributive step. After each modification the kinase continues to another unmodified repeat with probability q_proc, else releases. The run is truncated only by running out of unmodified repeats (weights q^(j-1)(1-q), and q^(j-1) for the run that completes the molecule). q_proc = 0 (base) is strictly distributive.",
      "rationale": "Distributive versus processive is about how many modifications one binding event makes. The encounter-level jump n -> n+j with geometric run length is the standard count-level representation, and its weights sum to 1, so q_proc changes what an encounter does, not how often encounters happen. Strong processivity predicts early bimodality (CTD_0 plus high counts, depleted intermediates at 1 h). Its difference from cp > 1 is memory: under processivity a released molecule returns to the slow distributive pace, so long-lived intermediates persist to the 16 h point. Sliding processivity (running along to the next repeat, stopped by an already-modified repeat) depends on positions and only exists in the positional model. It is not exactly lumpable and is likely aliased with nb > 1.",
      "confidence": "medium"
    },
    {
      "decision": "ATP is an explicit consumed species (one per repeat modified, ADP produced) and enters every rate as ATP/(K_ATP + ATP), with K_ATP fixed at 50 uM.",
      "rationale": "ATP is a required entity, and the note states one ATP per phosphorylation. At most 800 uM of the 3000 uM is consumed, so with any K_ATP in the tens of uM the factor stays near 0.98 throughout. ATP is saturating, and its depletion cannot shape the data. K_ATP is therefore fixed, not estimated: no part of the data window constrains it. Mass action in ATP was rejected because it would impose a ~27% rate decline by 16 h as an artefact of the rate-law form.",
      "confidence": "high"
    },
    {
      "decision": "P-TEFb is a constant species at 1 (relative units). Its absolute level is absorbed into kmod; CTD is in uM with CTD_0(0) = 100 uM.",
      "rationale": "The enzyme concentration is not given, and only the product kmod*PTEFb is visible. Fixing PTEFb = 1 removes that flat direction. Total substrate is known, so the model's amounts are absolute in uM. The arbitrary MS scale belongs to the observation model's per-time-point factors and does not trade off against any model state. Each repeat is one bit, so 9 count states are complete.",
      "confidence": "high"
    },
    {
      "decision": "Not in the base, and named for the evaluation as what these data are expected not to separate: enzyme activity loss over 16 h, substrate saturation of the kinase, sliding versus random-site processivity, and nb > 1 versus cp > 1 versus processivity.",
      "rationale": "Loss of kinase activity over 16 h would slow late modification exactly as negative cooperativity (cp < 1) does at high n, and only the 960 min point sees either. Substrate saturation is a time reparameterisation (see the distributive-steps decision). Positive neighbour effects, positive count cooperativity and processivity all produce nucleation-then-fast-completion from counts at 3 time points without replicates. These are recorded so that a criterion difference among them is reported as an indistinguishable set, not as a mechanism. None is added to the base: no observable in the single condition is argued to separate them.",
      "confidence": "medium"
    },
    {
      "decision": "No observation quantities in the Antimony. Readout phos<n>_rel maps onto species CTD_n (n = 0..8) with one scale factor per time point, shared by the nine peaks of that spectrum. Per the note, noise is additive normal with one sigma scaled by the same factor. That is the observation-model agent's to write.",
      "rationale": "The intensities are relative and drift between injections, so a per-time-point scale is a property of the measurement, not of the chemistry. The constant total substrate (100 uM) gives the dynamics the absolute reference, so the scales are identifiable from the shape of each spectrum.",
      "confidence": "high"
    }
  ],
  "declared_axes_for_a_later_round": []
}
```
## instruction
Write the 2-5 candidates of this discrimination round as DIFFERENCES from `base_model`, which the engine has already tested. Prefer the switches construction built in (its decisions say which parameter switches which feature); patch a reaction only where a tested feature cannot be a switch. Each candidate differs from the base only in its tested feature, and the base itself is a candidate when the comparison needs the model with no tested feature on. `declared_axes_for_a_later_round` are tested by the engine after this round — do not build them into candidates.
## human_feedback
In M3_neighbour and M5_neighbour_and_count, the 74 gap-class states (Gf8, G07 ... G00) are already declared as species in the append block; remove them from adds_parameters and keep only nb there. petablint rejected them as extraneous parameters in the parameter table. Change nothing else.
## human_feedback_instruction
A HUMAN read your previous reply and asked for this change. It is not a gate failure and nothing you produced was invalid — they want the expansions done differently. Your previous reply is `previous_reply`, exactly as you returned it. Return the SAME contract: revise THAT reply to do what they asked, changing only what their request implicates, and keep every id, name, value, bound and rate law it does not implicate exactly as it is there — the engine compares the two replies and shows the person every difference. If what they ask for is not possible, or would break something they may not have considered, say so plainly in your build report and do the closest thing that is defensible — do not silently ignore it, and do not comply in a way you believe is wrong without saying why.
## previous_reply
```json
{
  "candidates": [
    {
      "id": "M1_independent",
      "label": "Independent repeats, strictly distributive (base)",
      "rationale": "This is the 'nothing at all' hypothesis and the distributive null. Every unmodified repeat is modified at the same constant rate, whatever the state of the molecule or its neighbours. Each kinase encounter modifies one repeat (cp = 1, q_proc = 0, no positional term), so the count distribution is binomial(8, 1 - exp(-r*t)) at every time point. M2 to M5 each depart from it in one declared feature, so every 'required' verdict (count cooperativity, neighbour effect, processivity) is measured against this reference. No differences from the base.",
      "set_parameters": [],
      "on_antimony_patch": [],
      "adds_parameters": [],
      "entity_glossary": {
        "species": [],
        "parameters": []
      }
    },
    {
      "id": "M2_count_coop",
      "label": "Count cooperativity between repeats (cp estimated)",
      "rationale": "Tests 'the rate depends only on how many repeats are already modified'. It switches on the base's count-cooperativity term: a molecule with n marks has its per-repeat rate multiplied by cp^n, with cp estimated between 0.2 and 5 on a log scale; cp = 1 is M1. Everything else is as in the base: distributive, no positional term. cp < 1 slows the late steps and lets intermediates pile up by 16 h. cp > 1 gives nucleation then fast completion, with early bimodality between 0 and high counts.",
      "set_parameters": [
        {
          "id": "cp",
          "nominal_value": 1.0,
          "estimate": true,
          "lb": 0.2,
          "ub": 5.0
        }
      ],
      "on_antimony_patch": [],
      "adds_parameters": [],
      "entity_glossary": {
        "species": [],
        "parameters": []
      }
    },
    {
      "id": "M3_neighbour",
      "label": "Nearest-neighbour effect (positional model, nb estimated)",
      "rationale": "Tests 'modifying a repeat changes the rate at which its immediate neighbours are modified'. The base counts marks and cannot express this, because a neighbour effect breaks the count lumping (construction decision 1). It is therefore added as a patch that implements construction's positional rule exactly. Each unmodified repeat is modified at kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, where m is the number of its marked immediate neighbours. cp is held at 1, so nb is the only tested feature; it is estimated between 0.01 and 100 on a log scale, and nb = 1 reproduces M1 exactly. The positional model is written out state by state and reaction by reaction on the 74 gap-structure classes onto which the 256 configurations lump exactly (build report). Gf8 is the unmodified molecule. In G<a><b>_<g...>, a <= b are the unmarked stretches at the two chain ends and the digits after the underscore are the unmarked stretches between marks. J0 to J7 keep their stoichiometry and ATP use; their rate becomes the summed flux of the classes with n marks, so CTD_n stays the count readout and equals its class sum identically. nb < 1 (neighbour inhibition) jams molecules at up to 4 non-adjacent marks before a slow filling phase, a stall between 2 h and 16 h that cp alone cannot shape. nb > 1 (neighbour facilitation) gives nucleation-and-growth, which cp > 1 and processivity also produce.",
      "set_parameters": [],
      "on_antimony_patch": [
        {
          "replace_reaction": "J0",
          "with": "J0: CTD_0 + ATP -> CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*Gf8;"
        },
        {
          "replace_reaction": "J1",
          "with": "J1: CTD_1 + ATP -> CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*((6 + nb)*G07 + (5 + 2*nb)*(G16 + G25 + G34));"
        },
        {
          "replace_reaction": "J2",
          "with": "J2: CTD_2 + ATP -> CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*((5 + nb)*G06 + (4 + 2*nb)*(G15 + G24 + G33 + G00_6) + (4 + nb + nb^2)*G05_1 + (3 + 2*nb + nb^2)*(G14_1 + G23_1) + (3 + 3*nb)*(G04_2 + G03_3 + G02_4 + G01_5) + (2 + 4*nb)*(G13_2 + G22_2 + G12_3 + G11_4));"
        },
        {
          "replace_reaction": "J3",
          "with": "J3: CTD_3 + ATP -> CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*((4 + nb)*G05 + (3 + 2*nb)*(G14 + G23 + G00_5) + (3 + nb + nb^2)*G04_1 + (2 + 2*nb + nb^2)*(G13_1 + G22_1 + G00_41) + (2 + 3*nb)*(G03_2 + G02_3 + G01_4) + (1 + 4*nb)*(G12_2 + G11_3 + G00_32) + (2 + nb + 2*nb^2)*G03_11 + (1 + 2*nb + 2*nb^2)*G12_11 + (1 + 3*nb + nb^2)*(G02_21 + G01_31) + (4*nb + nb^2)*G11_21 + 5*nb*G01_22);"
        },
        {
          "replace_reaction": "J4",
          "with": "J4: CTD_4 + ATP -> CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*((3 + nb)*G04 + (2 + 2*nb)*(G13 + G22 + G00_4) + (2 + nb + nb^2)*G03_1 + (1 + 2*nb + nb^2)*(G12_1 + G00_31) + (1 + 3*nb)*(G02_2 + G01_3) + 4*nb*(G11_2 + G00_22) + (1 + nb + 2*nb^2)*G02_11 + (2*nb + 2*nb^2)*(G11_11 + G00_211) + (3*nb + nb^2)*G01_21 + (nb + 3*nb^2)*G01_111);"
        },
        {
          "replace_reaction": "J5",
          "with": "J5: CTD_5 + ATP -> CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*((2 + nb)*G03 + (1 + 2*nb)*(G12 + G00_3) + (1 + nb + nb^2)*G02_1 + (2*nb + nb^2)*(G11_1 + G00_21) + 3*nb*G01_2 + (nb + 2*nb^2)*G01_11 + 3*nb^2*G00_111);"
        },
        {
          "replace_reaction": "J6",
          "with": "J6: CTD_6 + ATP -> CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*((1 + nb)*G02 + 2*nb*(G11 + G00_2) + (nb + nb^2)*G01_1 + 2*nb^2*G00_11);"
        },
        {
          "replace_reaction": "J7",
          "with": "J7: CTD_7 + ATP -> CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*(nb*G01 + nb^2*G00_1);"
        },
        {
          "append": [
            "// Positional refinement by gap class: Gf8 = unmodified; G<a><b>_<g...> = unmarked end stretches a <= b and unmarked interior stretches g... between marks; n = 8 - a - b - sum(g)",
            "// The G classes with n marks sum to CTD_n identically; G reactions carry no ATP (ATP is consumed once, by J0-J7)",
            "species Gf8 in vial, G07 in vial, G16 in vial, G25 in vial, G34 in vial;",
            "species G06 in vial, G15 in vial, G24 in vial, G33 in vial, G05_1 in vial, G14_1 in vial, G23_1 in vial, G04_2 in vial;",
            "species G13_2 in vial, G22_2 in vial, G03_3 in vial, G12_3 in vial, G02_4 in vial, G11_4 in vial, G01_5 in vial, G00_6 in vial;",
            "species G05 in vial, G14 in vial, G23 in vial, G04_1 in vial, G13_1 in vial, G22_1 in vial, G03_2 in vial, G12_2 in vial, G02_3 in vial, G11_3 in vial;",
            "species G01_4 in vial, G00_5 in vial, G03_11 in vial, G12_11 in vial, G02_21 in vial, G11_21 in vial, G01_31 in vial, G01_22 in vial, G00_41 in vial, G00_32 in vial;",
            "species G04 in vial, G13 in vial, G22 in vial, G03_1 in vial, G12_1 in vial, G02_2 in vial, G11_2 in vial, G01_3 in vial;",
            "species G00_4 in vial, G02_11 in vial, G11_11 in vial, G01_21 in vial, G00_31 in vial, G00_22 in vial, G01_111 in vial, G00_211 in vial;",
            "species G03 in vial, G12 in vial, G02_1 in vial, G11_1 in vial, G01_2 in vial, G00_3 in vial, G01_11 in vial, G00_21 in vial, G00_111 in vial;",
            "species G02 in vial, G11 in vial, G01_1 in vial, G00_2 in vial, G00_11 in vial, G01 in vial, G00_1 in vial, G00 in vial;",
            "Gf8 = 100; G07 = 0; G16 = 0; G25 = 0; G34 = 0;",
            "G06 = 0; G15 = 0; G24 = 0; G33 = 0; G05_1 = 0; G14_1 = 0; G23_1 = 0; G04_2 = 0;",
            "G13_2 = 0; G22_2 = 0; G03_3 = 0; G12_3 = 0; G02_4 = 0; G11_4 = 0; G01_5 = 0; G00_6 = 0;",
            "G05 = 0; G14 = 0; G23 = 0; G04_1 = 0; G13_1 = 0; G22_1 = 0; G03_2 = 0; G12_2 = 0; G02_3 = 0; G11_3 = 0;",
            "G01_4 = 0; G00_5 = 0; G03_11 = 0; G12_11 = 0; G02_21 = 0; G11_21 = 0; G01_31 = 0; G01_22 = 0; G00_41 = 0; G00_32 = 0;",
            "G04 = 0; G13 = 0; G22 = 0; G03_1 = 0; G12_1 = 0; G02_2 = 0; G11_2 = 0; G01_3 = 0;",
            "G00_4 = 0; G02_11 = 0; G11_11 = 0; G01_21 = 0; G00_31 = 0; G00_22 = 0; G01_111 = 0; G00_211 = 0;",
            "G03 = 0; G12 = 0; G02_1 = 0; G11_1 = 0; G01_2 = 0; G00_3 = 0; G01_11 = 0; G00_21 = 0; G00_111 = 0;",
            "G02 = 0; G11 = 0; G01_1 = 0; G00_2 = 0; G00_11 = 0; G01 = 0; G00_1 = 0; G00 = 0;",
            "nb = 1;",
            "// rate per unmodified repeat: kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, m = marked immediate neighbours; coefficients count the repeats leading to each class",
            "Q_Gf8_G07: Gf8 -> G07; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_Gf8_G16: Gf8 -> G16; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_Gf8_G25: Gf8 -> G25; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_Gf8_G34: Gf8 -> G34; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_G07_G06: G07 -> G06; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G07;",
            "Q_G07_G05_1: G07 -> G05_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G04_2: G07 -> G04_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G03_3: G07 -> G03_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G02_4: G07 -> G02_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G01_5: G07 -> G01_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G00_6: G07 -> G00_6; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G16_G06: G16 -> G06; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
            "Q_G16_G15: G16 -> G15; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
            "Q_G16_G14_1: G16 -> G14_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G13_2: G16 -> G13_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G12_3: G16 -> G12_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G11_4: G16 -> G11_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G01_5: G16 -> G01_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G25_G15: G25 -> G15; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
            "Q_G25_G24: G25 -> G24; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
            "Q_G25_G05_1: G25 -> G05_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G23_1: G25 -> G23_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G22_2: G25 -> G22_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G12_3: G25 -> G12_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G02_4: G25 -> G02_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G34_G24: G34 -> G24; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
            "Q_G34_G33: G34 -> G33; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
            "Q_G34_G23_1: G34 -> G23_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G14_1: G34 -> G14_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G13_2: G34 -> G13_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G04_2: G34 -> G04_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G03_3: G34 -> G03_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G06_G05: G06 -> G05; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G06;",
            "Q_G06_G04_1: G06 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G03_2: G06 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G02_3: G06 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G01_4: G06 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G00_5: G06 -> G00_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G15_G05: G15 -> G05; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
            "Q_G15_G14: G15 -> G14; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
            "Q_G15_G13_1: G15 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G15_G12_2: G15 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G15_G11_3: G15 -> G11_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G15_G01_4: G15 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G24_G14: G24 -> G14; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
            "Q_G24_G23: G24 -> G23; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
            "Q_G24_G04_1: G24 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G24_G22_1: G24 -> G22_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G24_G12_2: G24 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G24_G02_3: G24 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G33_G23: G33 -> G23; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G33;",
            "Q_G33_G13_1: G33 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
            "Q_G33_G03_2: G33 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
            "Q_G05_1_G05: G05_1 -> G05; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G05_1;",
            "Q_G05_1_G04_1: G05_1 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G05_1;",
            "Q_G05_1_G03_11: G05_1 -> G03_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G05_1_G02_21: G05_1 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G05_1_G01_31: G05_1 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G05_1_G00_41: G05_1 -> G00_41; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G14_1_G14: G14_1 -> G14; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G14_1;",
            "Q_G14_1_G04_1: G14_1 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
            "Q_G14_1_G13_1: G14_1 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
            "Q_G14_1_G12_11: G14_1 -> G12_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
            "Q_G14_1_G11_21: G14_1 -> G11_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
            "Q_G14_1_G01_31: G14_1 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
            "Q_G23_1_G23: G23_1 -> G23; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G23_1;",
            "Q_G23_1_G13_1: G23_1 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
            "Q_G23_1_G22_1: G23_1 -> G22_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
            "Q_G23_1_G12_11: G23_1 -> G12_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
            "Q_G23_1_G03_11: G23_1 -> G03_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
            "Q_G23_1_G02_21: G23_1 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
            "Q_G04_2_G04_1: G04_2 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G04_2;",
            "Q_G04_2_G03_2: G04_2 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G04_2;",
            "Q_G04_2_G02_21: G04_2 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
            "Q_G04_2_G01_22: G04_2 -> G01_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
            "Q_G04_2_G00_32: G04_2 -> G00_32; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
            "Q_G13_2_G13_1: G13_2 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G13_2;",
            "Q_G13_2_G03_2: G13_2 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
            "Q_G13_2_G12_2: G13_2 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
            "Q_G13_2_G11_21: G13_2 -> G11_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
            "Q_G13_2_G01_22: G13_2 -> G01_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
            "Q_G22_2_G22_1: G22_2 -> G22_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
            "Q_G22_2_G12_2: G22_2 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
            "Q_G22_2_G02_21: G22_2 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G22_2;",
            "Q_G03_3_G03_2: G03_3 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G03_3;",
            "Q_G03_3_G02_3: G03_3 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G03_3;",
            "Q_G03_3_G03_11: G03_3 -> G03_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
            "Q_G03_3_G01_31: G03_3 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
            "Q_G03_3_G00_32: G03_3 -> G00_32; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
            "Q_G12_3_G12_2: G12_3 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G12_3;",
            "Q_G12_3_G02_3: G12_3 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
            "Q_G12_3_G11_3: G12_3 -> G11_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
            "Q_G12_3_G12_11: G12_3 -> G12_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
            "Q_G12_3_G01_31: G12_3 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
            "Q_G02_4_G02_3: G02_4 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G02_4;",
            "Q_G02_4_G01_4: G02_4 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G02_4;",
            "Q_G02_4_G02_21: G02_4 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G02_4;",
            "Q_G02_4_G00_41: G02_4 -> G00_41; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G02_4;",
            "Q_G11_4_G11_3: G11_4 -> G11_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
            "Q_G11_4_G01_4: G11_4 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
            "Q_G11_4_G11_21: G11_4 -> G11_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G11_4;",
            "Q_G01_5_G01_4: G01_5 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G01_5;",
            "Q_G01_5_G00_5: G01_5 -> G00_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G01_5;",
            "Q_G01_5_G01_31: G01_5 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G01_5;",
            "Q_G01_5_G01_22: G01_5 -> G01_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G01_5;",
            "Q_G00_6_G00_5: G00_6 -> G00_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G00_6;",
            "Q_G00_6_G00_41: G00_6 -> G00_41; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
            "Q_G00_6_G00_32: G00_6 -> G00_32; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
            "Q_G05_G04: G05 -> G04; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G05;",
            "Q_G05_G03_1: G05 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G05_G02_2: G05 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G05_G01_3: G05 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G05_G00_4: G05 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G14_G04: G14 -> G04; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
            "Q_G14_G13: G14 -> G13; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
            "Q_G14_G12_1: G14 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
            "Q_G14_G11_2: G14 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
            "Q_G14_G01_3: G14 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
            "Q_G23_G13: G23 -> G13; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
            "Q_G23_G22: G23 -> G22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
            "Q_G23_G12_1: G23 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
            "Q_G23_G03_1: G23 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
            "Q_G23_G02_2: G23 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
            "Q_G04_1_G04: G04_1 -> G04; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G04_1;",
            "Q_G04_1_G03_1: G04_1 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G04_1;",
            "Q_G04_1_G02_11: G04_1 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
            "Q_G04_1_G01_21: G04_1 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
            "Q_G04_1_G00_31: G04_1 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
            "Q_G13_1_G13: G13_1 -> G13; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G13_1;",
            "Q_G13_1_G03_1: G13_1 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
            "Q_G13_1_G12_1: G13_1 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
            "Q_G13_1_G11_11: G13_1 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
            "Q_G13_1_G01_21: G13_1 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
            "Q_G22_1_G22: G22_1 -> G22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G22_1;",
            "Q_G22_1_G12_1: G22_1 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G22_1;",
            "Q_G22_1_G02_11: G22_1 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G22_1;",
            "Q_G03_2_G03_1: G03_2 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G03_2;",
            "Q_G03_2_G02_2: G03_2 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_2;",
            "Q_G03_2_G01_21: G03_2 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
            "Q_G03_2_G00_22: G03_2 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
            "Q_G12_2_G12_1: G12_2 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G12_2;",
            "Q_G12_2_G02_2: G12_2 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
            "Q_G12_2_G11_2: G12_2 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
            "Q_G12_2_G01_21: G12_2 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_2;",
            "Q_G02_3_G02_2: G02_3 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_3;",
            "Q_G02_3_G01_3: G02_3 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_3;",
            "Q_G02_3_G02_11: G02_3 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
            "Q_G02_3_G00_31: G02_3 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
            "Q_G11_3_G11_2: G11_3 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
            "Q_G11_3_G01_3: G11_3 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
            "Q_G11_3_G11_11: G11_3 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G11_3;",
            "Q_G01_4_G01_3: G01_4 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_4;",
            "Q_G01_4_G00_4: G01_4 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_4;",
            "Q_G01_4_G01_21: G01_4 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G01_4;",
            "Q_G00_5_G00_4: G00_5 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_5;",
            "Q_G00_5_G00_31: G00_5 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_5;",
            "Q_G00_5_G00_22: G00_5 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_5;",
            "Q_G03_11_G03_1: G03_11 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G03_11;",
            "Q_G03_11_G02_11: G03_11 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_11;",
            "Q_G03_11_G01_111: G03_11 -> G01_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
            "Q_G03_11_G00_211: G03_11 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
            "Q_G12_11_G12_1: G12_11 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G12_11;",
            "Q_G12_11_G02_11: G12_11 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
            "Q_G12_11_G11_11: G12_11 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
            "Q_G12_11_G01_111: G12_11 -> G01_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_11;",
            "Q_G02_21_G02_2: G02_21 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G02_21;",
            "Q_G02_21_G02_11: G02_21 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_21;",
            "Q_G02_21_G01_21: G02_21 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_21;",
            "Q_G02_21_G00_211: G02_21 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_21;",
            "Q_G11_21_G11_2: G11_21 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G11_21;",
            "Q_G11_21_G11_11: G11_21 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
            "Q_G11_21_G01_21: G11_21 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
            "Q_G01_31_G01_3: G01_31 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G01_31;",
            "Q_G01_31_G01_21: G01_31 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_31;",
            "Q_G01_31_G00_31: G01_31 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_31;",
            "Q_G01_31_G01_111: G01_31 -> G01_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G01_31;",
            "Q_G01_22_G01_21: G01_22 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*4*nb*G01_22;",
            "Q_G01_22_G00_22: G01_22 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_22;",
            "Q_G00_41_G00_4: G00_41 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G00_41;",
            "Q_G00_41_G00_31: G00_41 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_41;",
            "Q_G00_41_G00_211: G00_41 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_41;",
            "Q_G00_32_G00_31: G00_32 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
            "Q_G00_32_G00_22: G00_32 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
            "Q_G00_32_G00_211: G00_32 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_32;",
            "Q_G04_G03: G04 -> G03; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G04;",
            "Q_G04_G02_1: G04 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
            "Q_G04_G01_2: G04 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
            "Q_G04_G00_3: G04 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
            "Q_G13_G03: G13 -> G03; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
            "Q_G13_G12: G13 -> G12; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
            "Q_G13_G11_1: G13 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
            "Q_G13_G01_2: G13 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
            "Q_G22_G12: G22 -> G12; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G22;",
            "Q_G22_G02_1: G22 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G22;",
            "Q_G03_1_G03: G03_1 -> G03; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G03_1;",
            "Q_G03_1_G02_1: G03_1 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G03_1;",
            "Q_G03_1_G01_11: G03_1 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
            "Q_G03_1_G00_21: G03_1 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
            "Q_G12_1_G12: G12_1 -> G12; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G12_1;",
            "Q_G12_1_G02_1: G12_1 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
            "Q_G12_1_G11_1: G12_1 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
            "Q_G12_1_G01_11: G12_1 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G12_1;",
            "Q_G02_2_G02_1: G02_2 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G02_2;",
            "Q_G02_2_G01_2: G02_2 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_2;",
            "Q_G02_2_G00_21: G02_2 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_2;",
            "Q_G11_2_G11_1: G11_2 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
            "Q_G11_2_G01_2: G11_2 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
            "Q_G01_3_G01_2: G01_3 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_3;",
            "Q_G01_3_G00_3: G01_3 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_3;",
            "Q_G01_3_G01_11: G01_3 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G01_3;",
            "Q_G00_4_G00_3: G00_4 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_4;",
            "Q_G00_4_G00_21: G00_4 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G00_4;",
            "Q_G02_11_G02_1: G02_11 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G02_11;",
            "Q_G02_11_G01_11: G02_11 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_11;",
            "Q_G02_11_G00_111: G02_11 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_11;",
            "Q_G11_11_G11_1: G11_11 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G11_11;",
            "Q_G11_11_G01_11: G11_11 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_11;",
            "Q_G01_21_G01_2: G01_21 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G01_21;",
            "Q_G01_21_G01_11: G01_21 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_21;",
            "Q_G01_21_G00_21: G01_21 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_21;",
            "Q_G00_31_G00_3: G00_31 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G00_31;",
            "Q_G00_31_G00_21: G00_31 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_31;",
            "Q_G00_31_G00_111: G00_31 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G00_31;",
            "Q_G00_22_G00_21: G00_22 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*4*nb*G00_22;",
            "Q_G01_111_G01_11: G01_111 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*3*nb^2*G01_111;",
            "Q_G01_111_G00_111: G01_111 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_111;",
            "Q_G00_211_G00_21: G00_211 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G00_211;",
            "Q_G00_211_G00_111: G00_211 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_211;",
            "Q_G03_G02: G03 -> G02; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G03;",
            "Q_G03_G01_1: G03 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
            "Q_G03_G00_2: G03 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
            "Q_G12_G02: G12 -> G02; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
            "Q_G12_G11: G12 -> G11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
            "Q_G12_G01_1: G12 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G12;",
            "Q_G02_1_G02: G02_1 -> G02; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G02_1;",
            "Q_G02_1_G01_1: G02_1 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G02_1;",
            "Q_G02_1_G00_11: G02_1 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G02_1;",
            "Q_G11_1_G11: G11_1 -> G11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G11_1;",
            "Q_G11_1_G01_1: G11_1 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G11_1;",
            "Q_G01_2_G01_1: G01_2 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G01_2;",
            "Q_G01_2_G00_2: G01_2 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_2;",
            "Q_G00_3_G00_2: G00_3 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_3;",
            "Q_G00_3_G00_11: G00_3 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G00_3;",
            "Q_G01_11_G01_1: G01_11 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb^2*G01_11;",
            "Q_G01_11_G00_11: G01_11 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_11;",
            "Q_G00_21_G00_2: G00_21 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G00_21;",
            "Q_G00_21_G00_11: G00_21 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_21;",
            "Q_G00_111_G00_11: G00_111 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*3*nb^2*G00_111;",
            "Q_G02_G01: G02 -> G01; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G02;",
            "Q_G02_G00_1: G02 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*G02;",
            "Q_G11_G01: G11 -> G01; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G11;",
            "Q_G01_1_G01: G01_1 -> G01; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb^2*G01_1;",
            "Q_G01_1_G00_1: G01_1 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G01_1;",
            "Q_G00_2_G00_1: G00_2 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G00_2;",
            "Q_G00_11_G00_1: G00_11 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb^2*G00_11;",
            "Q_G01_G00: G01 -> G00; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb*G01;",
            "Q_G00_1_G00: G00_1 -> G00; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb^2*G00_1;"
          ]
        }
      ],
      "adds_parameters": [
        {
          "id": "nb",
          "nominal_value": 1.0,
          "unit": "dimensionless (fold change of an unmodified repeat's rate per phosphorylated immediate neighbour)",
          "lb": 0.01,
          "ub": 100.0,
          "evidence_tier": "to_be_estimated",
          "source": "base_model construction decision (positional candidate rule): neutral value 1, bounds 0.01 to 100; log10 scale",
          "estimate": true
        }
      ],
      "entity_glossary": {
        "species": [
          {
            "id": "Gf8",
            "denotes": "CTD with 0 marks: one stretch of 8 unmarked repeats (equals CTD_0)",
            "unit_convention": "uM; 100 at t = 0; positional refinement of CTD, not extra substrate",
            "lump_membership": "the single unmarked configuration"
          },
          {
            "id": "G07",
            "denotes": "1 mark, on repeat 1 or 8 (end gaps 0,7); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {0,7}, no interior gap"
          },
          {
            "id": "G16",
            "denotes": "1 mark, on repeat 2 or 7 (end gaps 1,6); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {1,6}, no interior gap"
          },
          {
            "id": "G25",
            "denotes": "1 mark, on repeat 3 or 6 (end gaps 2,5); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {2,5}, no interior gap"
          },
          {
            "id": "G34",
            "denotes": "1 mark, on repeat 4 or 5 (end gaps 3,4); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {3,4}, no interior gap"
          },
          {
            "id": "G06",
            "denotes": "2 marks; end gaps 0,6; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,6}; interior {}"
          },
          {
            "id": "G15",
            "denotes": "2 marks; end gaps 1,5; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,5}; interior {}"
          },
          {
            "id": "G24",
            "denotes": "2 marks; end gaps 2,4; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {2,4}; interior {}"
          },
          {
            "id": "G33",
            "denotes": "2 marks; end gaps 3,3; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {3,3}; interior {}"
          },
          {
            "id": "G05_1",
            "denotes": "2 marks; end gaps 0,5; interior gap 1; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,5}; interior {1}"
          },
          {
            "id": "G14_1",
            "denotes": "2 marks; end gaps 1,4; interior gap 1; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,4}; interior {1}"
          },
          {
            "id": "G23_1",
            "denotes": "2 marks; end gaps 2,3; interior gap 1; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {2,3}; interior {1}"
          },
          {
            "id": "G04_2",
            "denotes": "2 marks; end gaps 0,4; interior gap 2; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,4}; interior {2}"
          },
          {
            "id": "G13_2",
            "denotes": "2 marks; end gaps 1,3; interior gap 2; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,3}; interior {2}"
          },
          {
            "id": "G22_2",
            "denotes": "2 marks; end gaps 2,2; interior gap 2; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {2,2}; interior {2}"
          },
          {
            "id": "G03_3",
            "denotes": "2 marks; end gaps 0,3; interior gap 3; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,3}; interior {3}"
          },
          {
            "id": "G12_3",
            "denotes": "2 marks; end gaps 1,2; interior gap 3; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,2}; interior {3}"
          },
          {
            "id": "G02_4",
            "denotes": "2 marks; end gaps 0,2; interior gap 4; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,2}; interior {4}"
          },
          {
            "id": "G11_4",
            "denotes": "2 marks; end gaps 1,1; interior gap 4; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,1}; interior {4}"
          },
          {
            "id": "G01_5",
            "denotes": "2 marks; end gaps 0,1; interior gap 5; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,1}; interior {5}"
          },
          {
            "id": "G00_6",
            "denotes": "2 marks, on repeats 1 and 8; interior gap 6; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,0}; interior {6}"
          },
          {
            "id": "G05",
            "denotes": "3 marks; end gaps 0,5; no interior gap; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,5}; interior {}"
          },
          {
            "id": "G14",
            "denotes": "3 marks; end gaps 1,4; no interior gap; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,4}; interior {}"
          },
          {
            "id": "G23",
            "denotes": "3 marks; end gaps 2,3; no interior gap; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {2,3}; interior {}"
          },
          {
            "id": "G04_1",
            "denotes": "3 marks; end gaps 0,4; interior gap 1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,4}; interior {1}"
          },
          {
            "id": "G13_1",
            "denotes": "3 marks; end gaps 1,3; interior gap 1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,3}; interior {1}"
          },
          {
            "id": "G22_1",
            "denotes": "3 marks; end gaps 2,2; interior gap 1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {2,2}; interior {1}"
          },
          {
            "id": "G03_2",
            "denotes": "3 marks; end gaps 0,3; interior gap 2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,3}; interior {2}"
          },
          {
            "id": "G12_2",
            "denotes": "3 marks; end gaps 1,2; interior gap 2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,2}; interior {2}"
          },
          {
            "id": "G02_3",
            "denotes": "3 marks; end gaps 0,2; interior gap 3; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,2}; interior {3}"
          },
          {
            "id": "G11_3",
            "denotes": "3 marks; end gaps 1,1; interior gap 3; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,1}; interior {3}"
          },
          {
            "id": "G01_4",
            "denotes": "3 marks; end gaps 0,1; interior gap 4; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,1}; interior {4}"
          },
          {
            "id": "G00_5",
            "denotes": "3 marks; end gaps 0,0; interior gap 5; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,0}; interior {5}"
          },
          {
            "id": "G03_11",
            "denotes": "3 marks; end gaps 0,3; interior gaps 1,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,3}; interior {1,1}"
          },
          {
            "id": "G12_11",
            "denotes": "3 marks; end gaps 1,2; interior gaps 1,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,2}; interior {1,1}"
          },
          {
            "id": "G02_21",
            "denotes": "3 marks; end gaps 0,2; interior gaps 2,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,2}; interior {2,1}"
          },
          {
            "id": "G11_21",
            "denotes": "3 marks; end gaps 1,1; interior gaps 2,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,1}; interior {2,1}"
          },
          {
            "id": "G01_31",
            "denotes": "3 marks; end gaps 0,1; interior gaps 3,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,1}; interior {3,1}"
          },
          {
            "id": "G01_22",
            "denotes": "3 marks; end gaps 0,1; interior gaps 2,2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,1}; interior {2,2}"
          },
          {
            "id": "G00_41",
            "denotes": "3 marks; end gaps 0,0; interior gaps 4,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,0}; interior {4,1}"
          },
          {
            "id": "G00_32",
            "denotes": "3 marks; end gaps 0,0; interior gaps 3,2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,0}; interior {3,2}"
          },
          {
            "id": "G04",
            "denotes": "4 marks; end gaps 0,4; no interior gap; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,4}; interior {}"
          },
          {
            "id": "G13",
            "denotes": "4 marks; end gaps 1,3; no interior gap; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,3}; interior {}"
          },
          {
            "id": "G22",
            "denotes": "4 marks; end gaps 2,2; no interior gap; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {2,2}; interior {}"
          },
          {
            "id": "G03_1",
            "denotes": "4 marks; end gaps 0,3; interior gap 1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,3}; interior {1}"
          },
          {
            "id": "G12_1",
            "denotes": "4 marks; end gaps 1,2; interior gap 1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,2}; interior {1}"
          },
          {
            "id": "G02_2",
            "denotes": "4 marks; end gaps 0,2; interior gap 2; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,2}; interior {2}"
          },
          {
            "id": "G11_2",
            "denotes": "4 marks; end gaps 1,1; interior gap 2; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,1}; interior {2}"
          },
          {
            "id": "G01_3",
            "denotes": "4 marks; end gaps 0,1; interior gap 3; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,1}; interior {3}"
          },
          {
            "id": "G00_4",
            "denotes": "4 marks; end gaps 0,0; interior gap 4; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {4}"
          },
          {
            "id": "G02_11",
            "denotes": "4 marks; end gaps 0,2; interior gaps 1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,2}; interior {1,1}"
          },
          {
            "id": "G11_11",
            "denotes": "4 marks, alternating on repeats 2,4,6... with end gaps 1,1 and interior gaps 1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,1}; interior {1,1}"
          },
          {
            "id": "G01_21",
            "denotes": "4 marks; end gaps 0,1; interior gaps 2,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,1}; interior {2,1}"
          },
          {
            "id": "G00_31",
            "denotes": "4 marks; end gaps 0,0; interior gaps 3,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {3,1}"
          },
          {
            "id": "G00_22",
            "denotes": "4 marks; end gaps 0,0; interior gaps 2,2; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {2,2}"
          },
          {
            "id": "G01_111",
            "denotes": "4 marks on alternate repeats (1,3,5,7 or 2,4,6,8): end gaps 0,1, interior gaps 1,1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,1}; interior {1,1,1}"
          },
          {
            "id": "G00_211",
            "denotes": "4 marks; end gaps 0,0; interior gaps 2,1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {2,1,1}"
          },
          {
            "id": "G03",
            "denotes": "5 marks; end gaps 0,3; no interior gap; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,3}; interior {}"
          },
          {
            "id": "G12",
            "denotes": "5 marks; end gaps 1,2; no interior gap; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {1,2}; interior {}"
          },
          {
            "id": "G02_1",
            "denotes": "5 marks; end gaps 0,2; interior gap 1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,2}; interior {1}"
          },
          {
            "id": "G11_1",
            "denotes": "5 marks; end gaps 1,1; interior gap 1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {1,1}; interior {1}"
          },
          {
            "id": "G01_2",
            "denotes": "5 marks; end gaps 0,1; interior gap 2; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,1}; interior {2}"
          },
          {
            "id": "G00_3",
            "denotes": "5 marks; end gaps 0,0; interior gap 3; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,0}; interior {3}"
          },
          {
            "id": "G01_11",
            "denotes": "5 marks; end gaps 0,1; interior gaps 1,1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,1}; interior {1,1}"
          },
          {
            "id": "G00_21",
            "denotes": "5 marks; end gaps 0,0; interior gaps 2,1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,0}; interior {2,1}"
          },
          {
            "id": "G00_111",
            "denotes": "5 marks; end gaps 0,0; interior gaps 1,1,1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,0}; interior {1,1,1}"
          },
          {
            "id": "G02",
            "denotes": "6 marks; end gaps 0,2; no interior gap; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,2}; interior {}"
          },
          {
            "id": "G11",
            "denotes": "6 marks, on repeats 2 to 7 (end gaps 1,1); refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {1,1}; interior {}"
          },
          {
            "id": "G01_1",
            "denotes": "6 marks; end gaps 0,1; interior gap 1; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,1}; interior {1}"
          },
          {
            "id": "G00_2",
            "denotes": "6 marks; end gaps 0,0; interior gap 2; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,0}; interior {2}"
          },
          {
            "id": "G00_11",
            "denotes": "6 marks; end gaps 0,0; interior gaps 1,1; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,0}; interior {1,1}"
          },
          {
            "id": "G01",
            "denotes": "7 marks, the unmarked repeat at an end (repeat 1 or 8); refines CTD_7",
            "unit_convention": "uM; sums with G00_1 to CTD_7",
            "lump_membership": "end gaps {0,1}; interior {}"
          },
          {
            "id": "G00_1",
            "denotes": "7 marks, the unmarked repeat interior (repeats 2 to 7); refines CTD_7",
            "unit_convention": "uM; sums with G01 to CTD_7",
            "lump_membership": "end gaps {0,0}; interior {1}"
          },
          {
            "id": "G00",
            "denotes": "all 8 repeats marked (equals CTD_8)",
            "unit_convention": "uM",
            "lump_membership": "the single fully marked configuration"
          }
        ],
        "parameters": [
          {
            "id": "nb",
            "role": "nearest-neighbour switch: fold change of an unmodified repeat's rate per phosphorylated immediate neighbour (m = 0, 1 or 2; repeats 1 and 8 have one neighbour)",
            "convention": "neutral value 1 (no neighbour effect); < 1 inhibition, > 1 facilitation; log10 scale, bounds 0.01 to 100",
            "set_per_condition": false
          }
        ]
      }
    },
    {
      "id": "M4_processive",
      "label": "Processive continuation (q_proc estimated)",
      "rationale": "Tests the earlier by-eye conclusion that P-TEFb is distributive. It switches on the base's processivity term: after each modification the kinase continues to another unmodified repeat with probability q_proc. q_proc is estimated between 1e-4 and 0.99 on a log scale, with nominal 0.1 inside the box; the lower bound is the strictly distributive M1 to within 1e-4. Repeats are otherwise independent (cp = 1) and there is no positional term. Strong processivity predicts early bimodality, with intermediates that persist to 16 h because released molecules return to the distributive pace. The q_proc profile is the direct test. If it reaches the lower bound with the likelihood flat below about 0.1, distributive action is supported. If a q_proc clearly above 0 is required, the by-eye conclusion fails.",
      "set_parameters": [
        {
          "id": "q_proc",
          "nominal_value": 0.1,
          "estimate": true,
          "lb": 0.0001,
          "ub": 0.99
        }
      ],
      "on_antimony_patch": [],
      "adds_parameters": [],
      "entity_glossary": {
        "species": [],
        "parameters": []
      }
    },
    {
      "id": "M5_neighbour_and_count",
      "label": "Nearest-neighbour effect plus count cooperativity (nb and cp estimated)",
      "rationale": "This candidate combines two features deliberately: the neighbour term nb (as in M3, with the identical positional patch) and count cooperativity cp (as in M2), both estimated. It is the model that contains M2 and M3 as nested cases. M5 against M2 asks whether a neighbour effect is needed once count cooperativity is allowed, and M5 against M3 asks the converse. The joint nb-cp profile shows whether these data can separate the two at all, which is the separability statement the question asks for. Distributive (q_proc = 0). At nb = 1 it reproduces M2 exactly; at cp = 1 it reproduces M3.",
      "set_parameters": [
        {
          "id": "cp",
          "nominal_value": 1.0,
          "estimate": true,
          "lb": 0.2,
          "ub": 5.0
        }
      ],
      "on_antimony_patch": [
        {
          "replace_reaction": "J0",
          "with": "J0: CTD_0 + ATP -> CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*Gf8;"
        },
        {
          "replace_reaction": "J1",
          "with": "J1: CTD_1 + ATP -> CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*((6 + nb)*G07 + (5 + 2*nb)*(G16 + G25 + G34));"
        },
        {
          "replace_reaction": "J2",
          "with": "J2: CTD_2 + ATP -> CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*((5 + nb)*G06 + (4 + 2*nb)*(G15 + G24 + G33 + G00_6) + (4 + nb + nb^2)*G05_1 + (3 + 2*nb + nb^2)*(G14_1 + G23_1) + (3 + 3*nb)*(G04_2 + G03_3 + G02_4 + G01_5) + (2 + 4*nb)*(G13_2 + G22_2 + G12_3 + G11_4));"
        },
        {
          "replace_reaction": "J3",
          "with": "J3: CTD_3 + ATP -> CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*((4 + nb)*G05 + (3 + 2*nb)*(G14 + G23 + G00_5) + (3 + nb + nb^2)*G04_1 + (2 + 2*nb + nb^2)*(G13_1 + G22_1 + G00_41) + (2 + 3*nb)*(G03_2 + G02_3 + G01_4) + (1 + 4*nb)*(G12_2 + G11_3 + G00_32) + (2 + nb + 2*nb^2)*G03_11 + (1 + 2*nb + 2*nb^2)*G12_11 + (1 + 3*nb + nb^2)*(G02_21 + G01_31) + (4*nb + nb^2)*G11_21 + 5*nb*G01_22);"
        },
        {
          "replace_reaction": "J4",
          "with": "J4: CTD_4 + ATP -> CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*((3 + nb)*G04 + (2 + 2*nb)*(G13 + G22 + G00_4) + (2 + nb + nb^2)*G03_1 + (1 + 2*nb + nb^2)*(G12_1 + G00_31) + (1 + 3*nb)*(G02_2 + G01_3) + 4*nb*(G11_2 + G00_22) + (1 + nb + 2*nb^2)*G02_11 + (2*nb + 2*nb^2)*(G11_11 + G00_211) + (3*nb + nb^2)*G01_21 + (nb + 3*nb^2)*G01_111);"
        },
        {
          "replace_reaction": "J5",
          "with": "J5: CTD_5 + ATP -> CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*((2 + nb)*G03 + (1 + 2*nb)*(G12 + G00_3) + (1 + nb + nb^2)*G02_1 + (2*nb + nb^2)*(G11_1 + G00_21) + 3*nb*G01_2 + (nb + 2*nb^2)*G01_11 + 3*nb^2*G00_111);"
        },
        {
          "replace_reaction": "J6",
          "with": "J6: CTD_6 + ATP -> CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*((1 + nb)*G02 + 2*nb*(G11 + G00_2) + (nb + nb^2)*G01_1 + 2*nb^2*G00_11);"
        },
        {
          "replace_reaction": "J7",
          "with": "J7: CTD_7 + ATP -> CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*(nb*G01 + nb^2*G00_1);"
        },
        {
          "append": [
            "// Positional refinement by gap class: Gf8 = unmodified; G<a><b>_<g...> = unmarked end stretches a <= b and unmarked interior stretches g... between marks; n = 8 - a - b - sum(g)",
            "// The G classes with n marks sum to CTD_n identically; G reactions carry no ATP (ATP is consumed once, by J0-J7)",
            "species Gf8 in vial, G07 in vial, G16 in vial, G25 in vial, G34 in vial;",
            "species G06 in vial, G15 in vial, G24 in vial, G33 in vial, G05_1 in vial, G14_1 in vial, G23_1 in vial, G04_2 in vial;",
            "species G13_2 in vial, G22_2 in vial, G03_3 in vial, G12_3 in vial, G02_4 in vial, G11_4 in vial, G01_5 in vial, G00_6 in vial;",
            "species G05 in vial, G14 in vial, G23 in vial, G04_1 in vial, G13_1 in vial, G22_1 in vial, G03_2 in vial, G12_2 in vial, G02_3 in vial, G11_3 in vial;",
            "species G01_4 in vial, G00_5 in vial, G03_11 in vial, G12_11 in vial, G02_21 in vial, G11_21 in vial, G01_31 in vial, G01_22 in vial, G00_41 in vial, G00_32 in vial;",
            "species G04 in vial, G13 in vial, G22 in vial, G03_1 in vial, G12_1 in vial, G02_2 in vial, G11_2 in vial, G01_3 in vial;",
            "species G00_4 in vial, G02_11 in vial, G11_11 in vial, G01_21 in vial, G00_31 in vial, G00_22 in vial, G01_111 in vial, G00_211 in vial;",
            "species G03 in vial, G12 in vial, G02_1 in vial, G11_1 in vial, G01_2 in vial, G00_3 in vial, G01_11 in vial, G00_21 in vial, G00_111 in vial;",
            "species G02 in vial, G11 in vial, G01_1 in vial, G00_2 in vial, G00_11 in vial, G01 in vial, G00_1 in vial, G00 in vial;",
            "Gf8 = 100; G07 = 0; G16 = 0; G25 = 0; G34 = 0;",
            "G06 = 0; G15 = 0; G24 = 0; G33 = 0; G05_1 = 0; G14_1 = 0; G23_1 = 0; G04_2 = 0;",
            "G13_2 = 0; G22_2 = 0; G03_3 = 0; G12_3 = 0; G02_4 = 0; G11_4 = 0; G01_5 = 0; G00_6 = 0;",
            "G05 = 0; G14 = 0; G23 = 0; G04_1 = 0; G13_1 = 0; G22_1 = 0; G03_2 = 0; G12_2 = 0; G02_3 = 0; G11_3 = 0;",
            "G01_4 = 0; G00_5 = 0; G03_11 = 0; G12_11 = 0; G02_21 = 0; G11_21 = 0; G01_31 = 0; G01_22 = 0; G00_41 = 0; G00_32 = 0;",
            "G04 = 0; G13 = 0; G22 = 0; G03_1 = 0; G12_1 = 0; G02_2 = 0; G11_2 = 0; G01_3 = 0;",
            "G00_4 = 0; G02_11 = 0; G11_11 = 0; G01_21 = 0; G00_31 = 0; G00_22 = 0; G01_111 = 0; G00_211 = 0;",
            "G03 = 0; G12 = 0; G02_1 = 0; G11_1 = 0; G01_2 = 0; G00_3 = 0; G01_11 = 0; G00_21 = 0; G00_111 = 0;",
            "G02 = 0; G11 = 0; G01_1 = 0; G00_2 = 0; G00_11 = 0; G01 = 0; G00_1 = 0; G00 = 0;",
            "nb = 1;",
            "// rate per unmodified repeat: kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, m = marked immediate neighbours; coefficients count the repeats leading to each class",
            "Q_Gf8_G07: Gf8 -> G07; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_Gf8_G16: Gf8 -> G16; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_Gf8_G25: Gf8 -> G25; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_Gf8_G34: Gf8 -> G34; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
            "Q_G07_G06: G07 -> G06; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G07;",
            "Q_G07_G05_1: G07 -> G05_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G04_2: G07 -> G04_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G03_3: G07 -> G03_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G02_4: G07 -> G02_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G01_5: G07 -> G01_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G07_G00_6: G07 -> G00_6; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
            "Q_G16_G06: G16 -> G06; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
            "Q_G16_G15: G16 -> G15; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
            "Q_G16_G14_1: G16 -> G14_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G13_2: G16 -> G13_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G12_3: G16 -> G12_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G11_4: G16 -> G11_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G16_G01_5: G16 -> G01_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
            "Q_G25_G15: G25 -> G15; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
            "Q_G25_G24: G25 -> G24; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
            "Q_G25_G05_1: G25 -> G05_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G23_1: G25 -> G23_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G22_2: G25 -> G22_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G12_3: G25 -> G12_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G25_G02_4: G25 -> G02_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
            "Q_G34_G24: G34 -> G24; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
            "Q_G34_G33: G34 -> G33; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
            "Q_G34_G23_1: G34 -> G23_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G14_1: G34 -> G14_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G13_2: G34 -> G13_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G04_2: G34 -> G04_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G34_G03_3: G34 -> G03_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
            "Q_G06_G05: G06 -> G05; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G06;",
            "Q_G06_G04_1: G06 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G03_2: G06 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G02_3: G06 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G01_4: G06 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G06_G00_5: G06 -> G00_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
            "Q_G15_G05: G15 -> G05; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
            "Q_G15_G14: G15 -> G14; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
            "Q_G15_G13_1: G15 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G15_G12_2: G15 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G15_G11_3: G15 -> G11_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G15_G01_4: G15 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
            "Q_G24_G14: G24 -> G14; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
            "Q_G24_G23: G24 -> G23; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
            "Q_G24_G04_1: G24 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G24_G22_1: G24 -> G22_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G24_G12_2: G24 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G24_G02_3: G24 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
            "Q_G33_G23: G33 -> G23; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G33;",
            "Q_G33_G13_1: G33 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
            "Q_G33_G03_2: G33 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
            "Q_G05_1_G05: G05_1 -> G05; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G05_1;",
            "Q_G05_1_G04_1: G05_1 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G05_1;",
            "Q_G05_1_G03_11: G05_1 -> G03_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G05_1_G02_21: G05_1 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G05_1_G01_31: G05_1 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G05_1_G00_41: G05_1 -> G00_41; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
            "Q_G14_1_G14: G14_1 -> G14; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G14_1;",
            "Q_G14_1_G04_1: G14_1 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
            "Q_G14_1_G13_1: G14_1 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
            "Q_G14_1_G12_11: G14_1 -> G12_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
            "Q_G14_1_G11_21: G14_1 -> G11_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
            "Q_G14_1_G01_31: G14_1 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
            "Q_G23_1_G23: G23_1 -> G23; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G23_1;",
            "Q_G23_1_G13_1: G23_1 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
            "Q_G23_1_G22_1: G23_1 -> G22_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
            "Q_G23_1_G12_11: G23_1 -> G12_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
            "Q_G23_1_G03_11: G23_1 -> G03_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
            "Q_G23_1_G02_21: G23_1 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
            "Q_G04_2_G04_1: G04_2 -> G04_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G04_2;",
            "Q_G04_2_G03_2: G04_2 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G04_2;",
            "Q_G04_2_G02_21: G04_2 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
            "Q_G04_2_G01_22: G04_2 -> G01_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
            "Q_G04_2_G00_32: G04_2 -> G00_32; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
            "Q_G13_2_G13_1: G13_2 -> G13_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G13_2;",
            "Q_G13_2_G03_2: G13_2 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
            "Q_G13_2_G12_2: G13_2 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
            "Q_G13_2_G11_21: G13_2 -> G11_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
            "Q_G13_2_G01_22: G13_2 -> G01_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
            "Q_G22_2_G22_1: G22_2 -> G22_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
            "Q_G22_2_G12_2: G22_2 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
            "Q_G22_2_G02_21: G22_2 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G22_2;",
            "Q_G03_3_G03_2: G03_3 -> G03_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G03_3;",
            "Q_G03_3_G02_3: G03_3 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G03_3;",
            "Q_G03_3_G03_11: G03_3 -> G03_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
            "Q_G03_3_G01_31: G03_3 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
            "Q_G03_3_G00_32: G03_3 -> G00_32; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
            "Q_G12_3_G12_2: G12_3 -> G12_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G12_3;",
            "Q_G12_3_G02_3: G12_3 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
            "Q_G12_3_G11_3: G12_3 -> G11_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
            "Q_G12_3_G12_11: G12_3 -> G12_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
            "Q_G12_3_G01_31: G12_3 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
            "Q_G02_4_G02_3: G02_4 -> G02_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G02_4;",
            "Q_G02_4_G01_4: G02_4 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G02_4;",
            "Q_G02_4_G02_21: G02_4 -> G02_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G02_4;",
            "Q_G02_4_G00_41: G02_4 -> G00_41; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G02_4;",
            "Q_G11_4_G11_3: G11_4 -> G11_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
            "Q_G11_4_G01_4: G11_4 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
            "Q_G11_4_G11_21: G11_4 -> G11_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G11_4;",
            "Q_G01_5_G01_4: G01_5 -> G01_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G01_5;",
            "Q_G01_5_G00_5: G01_5 -> G00_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G01_5;",
            "Q_G01_5_G01_31: G01_5 -> G01_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G01_5;",
            "Q_G01_5_G01_22: G01_5 -> G01_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G01_5;",
            "Q_G00_6_G00_5: G00_6 -> G00_5; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G00_6;",
            "Q_G00_6_G00_41: G00_6 -> G00_41; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
            "Q_G00_6_G00_32: G00_6 -> G00_32; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
            "Q_G05_G04: G05 -> G04; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G05;",
            "Q_G05_G03_1: G05 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G05_G02_2: G05 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G05_G01_3: G05 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G05_G00_4: G05 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
            "Q_G14_G04: G14 -> G04; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
            "Q_G14_G13: G14 -> G13; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
            "Q_G14_G12_1: G14 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
            "Q_G14_G11_2: G14 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
            "Q_G14_G01_3: G14 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
            "Q_G23_G13: G23 -> G13; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
            "Q_G23_G22: G23 -> G22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
            "Q_G23_G12_1: G23 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
            "Q_G23_G03_1: G23 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
            "Q_G23_G02_2: G23 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
            "Q_G04_1_G04: G04_1 -> G04; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G04_1;",
            "Q_G04_1_G03_1: G04_1 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G04_1;",
            "Q_G04_1_G02_11: G04_1 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
            "Q_G04_1_G01_21: G04_1 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
            "Q_G04_1_G00_31: G04_1 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
            "Q_G13_1_G13: G13_1 -> G13; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G13_1;",
            "Q_G13_1_G03_1: G13_1 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
            "Q_G13_1_G12_1: G13_1 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
            "Q_G13_1_G11_11: G13_1 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
            "Q_G13_1_G01_21: G13_1 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
            "Q_G22_1_G22: G22_1 -> G22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G22_1;",
            "Q_G22_1_G12_1: G22_1 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G22_1;",
            "Q_G22_1_G02_11: G22_1 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G22_1;",
            "Q_G03_2_G03_1: G03_2 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G03_2;",
            "Q_G03_2_G02_2: G03_2 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_2;",
            "Q_G03_2_G01_21: G03_2 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
            "Q_G03_2_G00_22: G03_2 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
            "Q_G12_2_G12_1: G12_2 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G12_2;",
            "Q_G12_2_G02_2: G12_2 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
            "Q_G12_2_G11_2: G12_2 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
            "Q_G12_2_G01_21: G12_2 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_2;",
            "Q_G02_3_G02_2: G02_3 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_3;",
            "Q_G02_3_G01_3: G02_3 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_3;",
            "Q_G02_3_G02_11: G02_3 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
            "Q_G02_3_G00_31: G02_3 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
            "Q_G11_3_G11_2: G11_3 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
            "Q_G11_3_G01_3: G11_3 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
            "Q_G11_3_G11_11: G11_3 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G11_3;",
            "Q_G01_4_G01_3: G01_4 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_4;",
            "Q_G01_4_G00_4: G01_4 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_4;",
            "Q_G01_4_G01_21: G01_4 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G01_4;",
            "Q_G00_5_G00_4: G00_5 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_5;",
            "Q_G00_5_G00_31: G00_5 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_5;",
            "Q_G00_5_G00_22: G00_5 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_5;",
            "Q_G03_11_G03_1: G03_11 -> G03_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G03_11;",
            "Q_G03_11_G02_11: G03_11 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_11;",
            "Q_G03_11_G01_111: G03_11 -> G01_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
            "Q_G03_11_G00_211: G03_11 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
            "Q_G12_11_G12_1: G12_11 -> G12_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G12_11;",
            "Q_G12_11_G02_11: G12_11 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
            "Q_G12_11_G11_11: G12_11 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
            "Q_G12_11_G01_111: G12_11 -> G01_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_11;",
            "Q_G02_21_G02_2: G02_21 -> G02_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G02_21;",
            "Q_G02_21_G02_11: G02_21 -> G02_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_21;",
            "Q_G02_21_G01_21: G02_21 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_21;",
            "Q_G02_21_G00_211: G02_21 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_21;",
            "Q_G11_21_G11_2: G11_21 -> G11_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G11_21;",
            "Q_G11_21_G11_11: G11_21 -> G11_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
            "Q_G11_21_G01_21: G11_21 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
            "Q_G01_31_G01_3: G01_31 -> G01_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G01_31;",
            "Q_G01_31_G01_21: G01_31 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_31;",
            "Q_G01_31_G00_31: G01_31 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_31;",
            "Q_G01_31_G01_111: G01_31 -> G01_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G01_31;",
            "Q_G01_22_G01_21: G01_22 -> G01_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*4*nb*G01_22;",
            "Q_G01_22_G00_22: G01_22 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_22;",
            "Q_G00_41_G00_4: G00_41 -> G00_4; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G00_41;",
            "Q_G00_41_G00_31: G00_41 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_41;",
            "Q_G00_41_G00_211: G00_41 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_41;",
            "Q_G00_32_G00_31: G00_32 -> G00_31; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
            "Q_G00_32_G00_22: G00_32 -> G00_22; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
            "Q_G00_32_G00_211: G00_32 -> G00_211; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_32;",
            "Q_G04_G03: G04 -> G03; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G04;",
            "Q_G04_G02_1: G04 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
            "Q_G04_G01_2: G04 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
            "Q_G04_G00_3: G04 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
            "Q_G13_G03: G13 -> G03; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
            "Q_G13_G12: G13 -> G12; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
            "Q_G13_G11_1: G13 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
            "Q_G13_G01_2: G13 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
            "Q_G22_G12: G22 -> G12; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G22;",
            "Q_G22_G02_1: G22 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G22;",
            "Q_G03_1_G03: G03_1 -> G03; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G03_1;",
            "Q_G03_1_G02_1: G03_1 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G03_1;",
            "Q_G03_1_G01_11: G03_1 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
            "Q_G03_1_G00_21: G03_1 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
            "Q_G12_1_G12: G12_1 -> G12; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G12_1;",
            "Q_G12_1_G02_1: G12_1 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
            "Q_G12_1_G11_1: G12_1 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
            "Q_G12_1_G01_11: G12_1 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G12_1;",
            "Q_G02_2_G02_1: G02_2 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G02_2;",
            "Q_G02_2_G01_2: G02_2 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_2;",
            "Q_G02_2_G00_21: G02_2 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_2;",
            "Q_G11_2_G11_1: G11_2 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
            "Q_G11_2_G01_2: G11_2 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
            "Q_G01_3_G01_2: G01_3 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_3;",
            "Q_G01_3_G00_3: G01_3 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_3;",
            "Q_G01_3_G01_11: G01_3 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G01_3;",
            "Q_G00_4_G00_3: G00_4 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_4;",
            "Q_G00_4_G00_21: G00_4 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G00_4;",
            "Q_G02_11_G02_1: G02_11 -> G02_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G02_11;",
            "Q_G02_11_G01_11: G02_11 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_11;",
            "Q_G02_11_G00_111: G02_11 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_11;",
            "Q_G11_11_G11_1: G11_11 -> G11_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G11_11;",
            "Q_G11_11_G01_11: G11_11 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_11;",
            "Q_G01_21_G01_2: G01_21 -> G01_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G01_21;",
            "Q_G01_21_G01_11: G01_21 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_21;",
            "Q_G01_21_G00_21: G01_21 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_21;",
            "Q_G00_31_G00_3: G00_31 -> G00_3; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G00_31;",
            "Q_G00_31_G00_21: G00_31 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_31;",
            "Q_G00_31_G00_111: G00_31 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G00_31;",
            "Q_G00_22_G00_21: G00_22 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*4*nb*G00_22;",
            "Q_G01_111_G01_11: G01_111 -> G01_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*3*nb^2*G01_111;",
            "Q_G01_111_G00_111: G01_111 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_111;",
            "Q_G00_211_G00_21: G00_211 -> G00_21; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G00_211;",
            "Q_G00_211_G00_111: G00_211 -> G00_111; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_211;",
            "Q_G03_G02: G03 -> G02; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G03;",
            "Q_G03_G01_1: G03 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
            "Q_G03_G00_2: G03 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
            "Q_G12_G02: G12 -> G02; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
            "Q_G12_G11: G12 -> G11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
            "Q_G12_G01_1: G12 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G12;",
            "Q_G02_1_G02: G02_1 -> G02; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G02_1;",
            "Q_G02_1_G01_1: G02_1 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G02_1;",
            "Q_G02_1_G00_11: G02_1 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G02_1;",
            "Q_G11_1_G11: G11_1 -> G11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G11_1;",
            "Q_G11_1_G01_1: G11_1 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G11_1;",
            "Q_G01_2_G01_1: G01_2 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G01_2;",
            "Q_G01_2_G00_2: G01_2 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_2;",
            "Q_G00_3_G00_2: G00_3 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_3;",
            "Q_G00_3_G00_11: G00_3 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G00_3;",
            "Q_G01_11_G01_1: G01_11 -> G01_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb^2*G01_11;",
            "Q_G01_11_G00_11: G01_11 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_11;",
            "Q_G00_21_G00_2: G00_21 -> G00_2; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G00_21;",
            "Q_G00_21_G00_11: G00_21 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_21;",
            "Q_G00_111_G00_11: G00_111 -> G00_11; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*3*nb^2*G00_111;",
            "Q_G02_G01: G02 -> G01; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G02;",
            "Q_G02_G00_1: G02 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*G02;",
            "Q_G11_G01: G11 -> G01; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G11;",
            "Q_G01_1_G01: G01_1 -> G01; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb^2*G01_1;",
            "Q_G01_1_G00_1: G01_1 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G01_1;",
            "Q_G00_2_G00_1: G00_2 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G00_2;",
            "Q_G00_11_G00_1: G00_11 -> G00_1; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb^2*G00_11;",
            "Q_G01_G00: G01 -> G00; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb*G01;",
            "Q_G00_1_G00: G00_1 -> G00; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb^2*G00_1;"
          ]
        }
      ],
      "adds_parameters": [
        {
          "id": "nb",
          "nominal_value": 1.0,
          "unit": "dimensionless (fold change of an unmodified repeat's rate per phosphorylated immediate neighbour)",
          "lb": 0.01,
          "ub": 100.0,
          "evidence_tier": "to_be_estimated",
          "source": "base_model construction decision (positional candidate rule): neutral value 1, bounds 0.01 to 100; log10 scale",
          "estimate": true
        }
      ],
      "entity_glossary": {
        "species": [
          {
            "id": "Gf8",
            "denotes": "CTD with 0 marks: one stretch of 8 unmarked repeats (equals CTD_0)",
            "unit_convention": "uM; 100 at t = 0; positional refinement of CTD, not extra substrate",
            "lump_membership": "the single unmarked configuration"
          },
          {
            "id": "G07",
            "denotes": "1 mark, on repeat 1 or 8 (end gaps 0,7); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {0,7}, no interior gap"
          },
          {
            "id": "G16",
            "denotes": "1 mark, on repeat 2 or 7 (end gaps 1,6); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {1,6}, no interior gap"
          },
          {
            "id": "G25",
            "denotes": "1 mark, on repeat 3 or 6 (end gaps 2,5); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {2,5}, no interior gap"
          },
          {
            "id": "G34",
            "denotes": "1 mark, on repeat 4 or 5 (end gaps 3,4); refines CTD_1",
            "unit_convention": "uM; sums with its class-mates to CTD_1",
            "lump_membership": "end gaps {3,4}, no interior gap"
          },
          {
            "id": "G06",
            "denotes": "2 marks; end gaps 0,6; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,6}; interior {}"
          },
          {
            "id": "G15",
            "denotes": "2 marks; end gaps 1,5; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,5}; interior {}"
          },
          {
            "id": "G24",
            "denotes": "2 marks; end gaps 2,4; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {2,4}; interior {}"
          },
          {
            "id": "G33",
            "denotes": "2 marks; end gaps 3,3; no interior gap; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {3,3}; interior {}"
          },
          {
            "id": "G05_1",
            "denotes": "2 marks; end gaps 0,5; interior gap 1; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,5}; interior {1}"
          },
          {
            "id": "G14_1",
            "denotes": "2 marks; end gaps 1,4; interior gap 1; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,4}; interior {1}"
          },
          {
            "id": "G23_1",
            "denotes": "2 marks; end gaps 2,3; interior gap 1; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {2,3}; interior {1}"
          },
          {
            "id": "G04_2",
            "denotes": "2 marks; end gaps 0,4; interior gap 2; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,4}; interior {2}"
          },
          {
            "id": "G13_2",
            "denotes": "2 marks; end gaps 1,3; interior gap 2; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,3}; interior {2}"
          },
          {
            "id": "G22_2",
            "denotes": "2 marks; end gaps 2,2; interior gap 2; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {2,2}; interior {2}"
          },
          {
            "id": "G03_3",
            "denotes": "2 marks; end gaps 0,3; interior gap 3; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,3}; interior {3}"
          },
          {
            "id": "G12_3",
            "denotes": "2 marks; end gaps 1,2; interior gap 3; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,2}; interior {3}"
          },
          {
            "id": "G02_4",
            "denotes": "2 marks; end gaps 0,2; interior gap 4; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,2}; interior {4}"
          },
          {
            "id": "G11_4",
            "denotes": "2 marks; end gaps 1,1; interior gap 4; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {1,1}; interior {4}"
          },
          {
            "id": "G01_5",
            "denotes": "2 marks; end gaps 0,1; interior gap 5; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,1}; interior {5}"
          },
          {
            "id": "G00_6",
            "denotes": "2 marks, on repeats 1 and 8; interior gap 6; refines CTD_2",
            "unit_convention": "uM; sums with its class-mates to CTD_2",
            "lump_membership": "end gaps {0,0}; interior {6}"
          },
          {
            "id": "G05",
            "denotes": "3 marks; end gaps 0,5; no interior gap; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,5}; interior {}"
          },
          {
            "id": "G14",
            "denotes": "3 marks; end gaps 1,4; no interior gap; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,4}; interior {}"
          },
          {
            "id": "G23",
            "denotes": "3 marks; end gaps 2,3; no interior gap; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {2,3}; interior {}"
          },
          {
            "id": "G04_1",
            "denotes": "3 marks; end gaps 0,4; interior gap 1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,4}; interior {1}"
          },
          {
            "id": "G13_1",
            "denotes": "3 marks; end gaps 1,3; interior gap 1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,3}; interior {1}"
          },
          {
            "id": "G22_1",
            "denotes": "3 marks; end gaps 2,2; interior gap 1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {2,2}; interior {1}"
          },
          {
            "id": "G03_2",
            "denotes": "3 marks; end gaps 0,3; interior gap 2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,3}; interior {2}"
          },
          {
            "id": "G12_2",
            "denotes": "3 marks; end gaps 1,2; interior gap 2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,2}; interior {2}"
          },
          {
            "id": "G02_3",
            "denotes": "3 marks; end gaps 0,2; interior gap 3; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,2}; interior {3}"
          },
          {
            "id": "G11_3",
            "denotes": "3 marks; end gaps 1,1; interior gap 3; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,1}; interior {3}"
          },
          {
            "id": "G01_4",
            "denotes": "3 marks; end gaps 0,1; interior gap 4; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,1}; interior {4}"
          },
          {
            "id": "G00_5",
            "denotes": "3 marks; end gaps 0,0; interior gap 5; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,0}; interior {5}"
          },
          {
            "id": "G03_11",
            "denotes": "3 marks; end gaps 0,3; interior gaps 1,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,3}; interior {1,1}"
          },
          {
            "id": "G12_11",
            "denotes": "3 marks; end gaps 1,2; interior gaps 1,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,2}; interior {1,1}"
          },
          {
            "id": "G02_21",
            "denotes": "3 marks; end gaps 0,2; interior gaps 2,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,2}; interior {2,1}"
          },
          {
            "id": "G11_21",
            "denotes": "3 marks; end gaps 1,1; interior gaps 2,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {1,1}; interior {2,1}"
          },
          {
            "id": "G01_31",
            "denotes": "3 marks; end gaps 0,1; interior gaps 3,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,1}; interior {3,1}"
          },
          {
            "id": "G01_22",
            "denotes": "3 marks; end gaps 0,1; interior gaps 2,2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,1}; interior {2,2}"
          },
          {
            "id": "G00_41",
            "denotes": "3 marks; end gaps 0,0; interior gaps 4,1; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,0}; interior {4,1}"
          },
          {
            "id": "G00_32",
            "denotes": "3 marks; end gaps 0,0; interior gaps 3,2; refines CTD_3",
            "unit_convention": "uM; sums with its class-mates to CTD_3",
            "lump_membership": "end gaps {0,0}; interior {3,2}"
          },
          {
            "id": "G04",
            "denotes": "4 marks; end gaps 0,4; no interior gap; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,4}; interior {}"
          },
          {
            "id": "G13",
            "denotes": "4 marks; end gaps 1,3; no interior gap; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,3}; interior {}"
          },
          {
            "id": "G22",
            "denotes": "4 marks; end gaps 2,2; no interior gap; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {2,2}; interior {}"
          },
          {
            "id": "G03_1",
            "denotes": "4 marks; end gaps 0,3; interior gap 1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,3}; interior {1}"
          },
          {
            "id": "G12_1",
            "denotes": "4 marks; end gaps 1,2; interior gap 1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,2}; interior {1}"
          },
          {
            "id": "G02_2",
            "denotes": "4 marks; end gaps 0,2; interior gap 2; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,2}; interior {2}"
          },
          {
            "id": "G11_2",
            "denotes": "4 marks; end gaps 1,1; interior gap 2; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,1}; interior {2}"
          },
          {
            "id": "G01_3",
            "denotes": "4 marks; end gaps 0,1; interior gap 3; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,1}; interior {3}"
          },
          {
            "id": "G00_4",
            "denotes": "4 marks; end gaps 0,0; interior gap 4; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {4}"
          },
          {
            "id": "G02_11",
            "denotes": "4 marks; end gaps 0,2; interior gaps 1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,2}; interior {1,1}"
          },
          {
            "id": "G11_11",
            "denotes": "4 marks; end gaps 1,1; interior gaps 1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {1,1}; interior {1,1}"
          },
          {
            "id": "G01_21",
            "denotes": "4 marks; end gaps 0,1; interior gaps 2,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,1}; interior {2,1}"
          },
          {
            "id": "G00_31",
            "denotes": "4 marks; end gaps 0,0; interior gaps 3,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {3,1}"
          },
          {
            "id": "G00_22",
            "denotes": "4 marks; end gaps 0,0; interior gaps 2,2; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {2,2}"
          },
          {
            "id": "G01_111",
            "denotes": "4 marks on alternate repeats (1,3,5,7 or 2,4,6,8): end gaps 0,1, interior gaps 1,1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,1}; interior {1,1,1}"
          },
          {
            "id": "G00_211",
            "denotes": "4 marks; end gaps 0,0; interior gaps 2,1,1; refines CTD_4",
            "unit_convention": "uM; sums with its class-mates to CTD_4",
            "lump_membership": "end gaps {0,0}; interior {2,1,1}"
          },
          {
            "id": "G03",
            "denotes": "5 marks; end gaps 0,3; no interior gap; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,3}; interior {}"
          },
          {
            "id": "G12",
            "denotes": "5 marks; end gaps 1,2; no interior gap; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {1,2}; interior {}"
          },
          {
            "id": "G02_1",
            "denotes": "5 marks; end gaps 0,2; interior gap 1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,2}; interior {1}"
          },
          {
            "id": "G11_1",
            "denotes": "5 marks; end gaps 1,1; interior gap 1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {1,1}; interior {1}"
          },
          {
            "id": "G01_2",
            "denotes": "5 marks; end gaps 0,1; interior gap 2; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,1}; interior {2}"
          },
          {
            "id": "G00_3",
            "denotes": "5 marks; end gaps 0,0; interior gap 3; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,0}; interior {3}"
          },
          {
            "id": "G01_11",
            "denotes": "5 marks; end gaps 0,1; interior gaps 1,1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,1}; interior {1,1}"
          },
          {
            "id": "G00_21",
            "denotes": "5 marks; end gaps 0,0; interior gaps 2,1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,0}; interior {2,1}"
          },
          {
            "id": "G00_111",
            "denotes": "5 marks; end gaps 0,0; interior gaps 1,1,1; refines CTD_5",
            "unit_convention": "uM; sums with its class-mates to CTD_5",
            "lump_membership": "end gaps {0,0}; interior {1,1,1}"
          },
          {
            "id": "G02",
            "denotes": "6 marks; end gaps 0,2; no interior gap; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,2}; interior {}"
          },
          {
            "id": "G11",
            "denotes": "6 marks, on repeats 2 to 7 (end gaps 1,1); refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {1,1}; interior {}"
          },
          {
            "id": "G01_1",
            "denotes": "6 marks; end gaps 0,1; interior gap 1; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,1}; interior {1}"
          },
          {
            "id": "G00_2",
            "denotes": "6 marks; end gaps 0,0; interior gap 2; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,0}; interior {2}"
          },
          {
            "id": "G00_11",
            "denotes": "6 marks; end gaps 0,0; interior gaps 1,1; refines CTD_6",
            "unit_convention": "uM; sums with its class-mates to CTD_6",
            "lump_membership": "end gaps {0,0}; interior {1,1}"
          },
          {
            "id": "G01",
            "denotes": "7 marks, the unmarked repeat at an end (repeat 1 or 8); refines CTD_7",
            "unit_convention": "uM; sums with G00_1 to CTD_7",
            "lump_membership": "end gaps {0,1}; interior {}"
          },
          {
            "id": "G00_1",
            "denotes": "7 marks, the unmarked repeat interior (repeats 2 to 7); refines CTD_7",
            "unit_convention": "uM; sums with G01 to CTD_7",
            "lump_membership": "end gaps {0,0}; interior {1}"
          },
          {
            "id": "G00",
            "denotes": "all 8 repeats marked (equals CTD_8)",
            "unit_convention": "uM",
            "lump_membership": "the single fully marked configuration"
          }
        ],
        "parameters": [
          {
            "id": "nb",
            "role": "nearest-neighbour switch: fold change of an unmodified repeat's rate per phosphorylated immediate neighbour (m = 0, 1 or 2; repeats 1 and 8 have one neighbour)",
            "convention": "neutral value 1 (no neighbour effect); < 1 inhibition, > 1 facilitation; log10 scale, bounds 0.01 to 100",
            "set_per_condition": false
          }
        ]
      }
    }
  ],
  "missing": [],
  "build_report": {
    "decisions": [
      {
        "decision": "Five candidates. M1 is the base: independent repeats, strictly distributive. M2 switches on count cooperativity (cp estimated). M3 adds the nearest-neighbour effect (positional patch, nb estimated). M4 switches on processivity (q_proc estimated). M5 combines the neighbour effect with count cooperativity (nb and cp estimated) and says so.",
        "rationale": "The intent asks for a three-way test (neighbour effect, count cooperativity, nothing at all) and a check of the distributive-versus-processive conclusion. M1 is the 'nothing at all' and distributive reference that every 'required' verdict is measured against. M2, M3 and M4 each switch on exactly one feature. M5 is the model that contains M2 and M3 as nested cases, so the comparisons 'neighbour effect beyond count cooperativity' and the converse are direct, and the joint nb-cp profile is where the separability question is answered. Every switch acts on its own: cp, nb and q_proc each change the dynamics with the others at their neutral values. No candidate differs from another only in an inert switch.",
        "alternatives_considered": "A processive-plus-cooperative combination (q_proc with cp), processivity on the positional model, and a free rate per count level (7 parameters, not identifiable from 9 peaks at 3 informative time points). The first two were left out to stay within five candidates, keeping the combination the question names directly (neighbour against count).",
        "evidence": [
          {
            "source": "lab_note",
            "locator": "What is already believed, and what is not settled",
            "supports": "the three named rate hypotheses and the distributive conclusion to be tested",
            "origin": "user-provided"
          },
          {
            "source": "lab_note",
            "locator": "base_model decisions (count cooperativity, processivity switches)",
            "supports": "cp and q_proc are the base's switches with neutral values 1 and 0",
            "origin": "inferred"
          }
        ],
        "evidence_tier": "direct",
        "confidence": "high",
        "user_decision_required": false,
        "question": ""
      },
      {
        "decision": "The neighbour effect, which the base cannot express, is added as a patch in M3 and M5. The patch implements construction's positional rule exactly: rate per unmodified repeat = kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, with m the number of marked immediate neighbours. It is written out state by state and reaction by reaction on 74 gap-structure classes and 257 reactions. These are the exact lumping of the 256-configuration, 1024-reaction model.",
        "rationale": "An unmodified repeat's rate depends only on n and on whether its two neighbours are marked. That is fixed by its position inside the maximal stretch of unmarked repeats (gap) that contains it, and by the gap's type: interior (marks on both sides), end (chain terminus on one side), or the whole unmodified chain. Modifying a repeat changes only its own gap: it splits the gap into at most two gaps of determined types, or shrinks it by one. The multiset of gap lengths with their types is therefore a sufficient state. The lengths of marked runs, the order of interior gaps and the orientation of the chain do not enter any rate; the rule treats both termini alike. Configurations sharing a gap structure have identical exit rates to every target class, so the 256 configurations are strongly lumpable onto the 74 classes. The classes with n marks sum to the count distribution exactly, at every nb and cp. Built-in check: at nb = 1 every class with n marks has total exit coefficient 8 - n (for example G01_22: 5*nb), so M3 reproduces M1 and M5 reproduces M2 trajectory for trajectory. Writing the reduced network by hand carries far less risk of an enumeration error than 1024 hand-written lines.",
        "alternatives_considered": "The literal 256-species, 1024-reaction enumeration. The note prefers the positional model written out rather than avoided, and it is written out here. The enumeration would only split each class into configurations with identical trajectories, so it gives the same likelihood and the same verdicts; it is not a different model. A positional readout (which repeats are marked) would need it, and none exists.",
        "evidence": [
          {
            "source": "lab_note",
            "locator": "What can be computed here",
            "supports": "positional model to be fitted rather than argued away; size is not a constraint",
            "origin": "user-provided"
          },
          {
            "source": "general_knowledge",
            "locator": "strong lumpability of Markov chains (Kemeny-Snell); exact lumping of linear ODE networks by symmetry of the rate rule",
            "supports": "class-level reactions reproduce the configuration-level count distribution exactly",
            "origin": "inferred"
          },
          {
            "source": "lab_note",
            "locator": "base_model decision: exact construction rule for the positional (neighbour) candidate",
            "supports": "rate cp^n*nb^m, nb neutral 1, bounds 0.01 to 100",
            "origin": "inferred"
          }
        ],
        "evidence_tier": "direct",
        "confidence": "high",
        "user_decision_required": false,
        "question": ""
      },
      {
        "decision": "In M3 and M5, J0 to J7 keep their stoichiometry (CTD_n + ATP -> CTD_n+1 + ADP). Each rate is replaced by the summed exit flux of the gap classes with n marks. The G reactions convert classes without consuming ATP. The observation model is unchanged: phos<n>_rel maps onto CTD_n.",
        "rationale": "This keeps CTD_n as the readout species shared by all five candidates. It also keeps ATP consumed exactly once per modification, and it avoids rewiring the 28 processive reactions. Since d(CTD_n)/dt and d(sum of G_n)/dt are identical linear expressions with equal initial values, CTD_n equals the class sum identically. A linear multistep integrator preserves that linear invariant to solver precision. The G species are the same 100 uM of CTD seen at positional resolution, not extra substrate. The deliberate simplification is a second conservation class (sum over G = 100 uM) alongside sum over CTD_n = 100 uM. Both are intended and neither carries a free parameter. The (1 - q_proc) factor is dropped from J0 to J6 because processivity is not composed with the positional model. q_proc stays at 0 in M3 and M5, where Jp* are present at exactly zero rate.",
        "alternatives_considered": "Assignment rules CTD_n := sum of G_n. These would require removing CTD_n from all 36 base reactions, which the patch grammar and the rule against removing reactions forbid. Making the G reactions consume ATP and dropping J0 to J7 was rejected for the same reason.",
        "evidence": [
          {
            "source": "lab_note",
            "locator": "The experiment (one ATP per phosphorylation; substrate conserved)",
            "supports": "ATP stoichiometry and the conserved total",
            "origin": "user-provided"
          },
          {
            "source": "general_knowledge",
            "locator": "measurement-tech pack entry 4; general-dynamics pack entry 4",
            "supports": "readout mapping and conserved totals kept intentional and declared",
            "origin": "inferred"
          }
        ],
        "evidence_tier": "direct",
        "confidence": "high",
        "user_decision_required": false,
        "question": ""
      },
      {
        "decision": "nb is estimated on log10 between 0.01 and 100, nominal 1 (neutral), as construction specified. cp in M2 and M5 keeps the base bounds 0.2 to 5. q_proc in M4 is estimated between 1e-4 and 0.99 with nominal 0.1, because 0 lies outside the estimation box and is invalid on a log scale.",
        "rationale": "nb enters as nb^2 on a repeat whose two neighbours are both marked, so its bounds span 8 decades on those steps. Together with cp^7, the fastest corner reaches rates about 1e4-fold above the per-repeat kmod. The engine should check integrability at the corners of the box, not only at the nominals (general-dynamics pack entry 8). The q_proc lower bound is strictly distributive to within 1e-4. If q_proc rests on that bound after fitting, that is a finding in favour of distributive action, not a bounds artefact (pack entry 6). Because M1 sits on the boundary of M4, a likelihood-ratio reading of M4 against M1 needs the boundary correction. The q_proc profile is the direct test.",
        "alternatives_considered": "nb bounds of 0.1 to 10. These would exclude the strong-inhibition regime (jamming at alternate repeats) that gives nb its most distinctive signature at 16 h.",
        "evidence": [
          {
            "source": "general_knowledge",
            "locator": "general-dynamics pack entries 1, 2, 6 and 8",
            "supports": "log scale, decade span, at-bound interpretation, corner integrability",
            "origin": "inferred"
          }
        ],
        "evidence_tier": "default",
        "confidence": "medium",
        "user_decision_required": false,
        "question": ""
      },
      {
        "decision": "Expected indistinguishable set and unresolved questions, named for the evaluation. nb > 1, cp > 1 and q_proc > 0 all predict nucleation then fast completion, and are expected to be hard to separate from counts at 3 informative time points without replicates. nb < 1 has a distinctive signature: a stall at 3 to 4 non-adjacent marks between 2 h and 16 h. Positional order, sliding versus random-site processivity, kinase inactivation and substrate saturation are not built into any candidate.",
        "rationale": "These data resolve count distributions, not positions. Neighbour inhibition caps fast modification at 4 marks on 8 repeats (alternate repeats) before a slow filling phase, a shape cp alone cannot produce. Neighbour facilitation, by contrast, aliases with count cooperativity and with processivity. M5's joint profile will show whether nb and cp are separately determined or only their combined effect. If the nb-cp profile is flat along a ridge, 'neighbour effect versus count cooperativity' must be reported as unresolved, with the combined effect reported as determined. Sliding processivity is positional and is likely aliased with nb > 1. Kinase inactivation over 16 h aliases with cp < 1, since only the 960 min point sees either. Substrate saturation reparameterises time. All of these follow construction's decisions and none is added this round.",
        "alternatives_considered": "Adding kinase inactivation as a sixth hypothesis. It exceeds the five-candidate cap, and no observable in the single condition is argued to separate it from cp < 1.",
        "evidence": [
          {
            "source": "lab_note",
            "locator": "The question (things the data cannot decide should be named)",
            "supports": "report unresolved mechanisms rather than decide them",
            "origin": "user-provided"
          },
          {
            "source": "lab_note",
            "locator": "base_model decision: not in the base, named as expected not to separate",
            "supports": "the aliasing pairs listed",
            "origin": "inferred"
          }
        ],
        "evidence_tier": "to_be_estimated",
        "confidence": "medium",
        "user_decision_required": false,
        "question": ""
      },
      {
        "decision": "Revision on human feedback: in M3_neighbour and M5_neighbour_and_count, the 74 positional-class species (Gf8, G07 ... G00) have been removed from adds_parameters, and nb is now the only entry there. They stay declared as species, with their initial amounts (Gf8 = 100 uM, every other class 0 uM), in each candidate's appended block, and they keep their entity_glossary entries as species. Nothing else changed. Every candidate id, set_parameters entry, patch line, rate expression, glossary entry, and every value and bound of nb, cp and q_proc is exactly as in the previous reply.",
        "rationale": "The G classes are model state variables, not parameters. Listing them in adds_parameters put them into the PEtab parameter table, where petablint correctly rejected them as extraneous: they are not parameters of the SBML model. Their initial amounts come from the append block's species declarations and assignments, so removing the parameter-table entries changes no trajectory and no likelihood. One risk needs stating plainly. The previous repair added these entries because attempt 1 was refused: the gate reported the G symbols in the J0-J7 replacement lines as undeclared, because it resolved patch symbols against the base and adds_parameters only. If the gate still resolves symbols that way, M3 and M5 will be refused again for the same reason, and that refusal would be a gate artefact, not a model error. The defensible fix is on the engine side: symbols that a candidate declares as species in its own append block should count as declared. I have not reordered the patches (append before the J replacements) to work around this, because the request was to change nothing else, and it is not known that the gate's check depends on order.",
        "alternatives_considered": "Keeping the species in adds_parameters. This was rejected because petablint refuses the PEtab problem with them there. Moving the J0-J7 rate changes into the append block, or dropping them, was also rejected. Dropping them would make CTD_n follow the base dynamics instead of the positional model, and the patch grammar only replaces a base reaction through replace_reaction.",
        "evidence": [
          {
            "source": "general_knowledge",
            "locator": "human_feedback: petablint rejected the G species as extraneous parameters in the parameter table",
            "supports": "the change made",
            "origin": "user-provided"
          },
          {
            "source": "general_knowledge",
            "locator": "previous_attempt_errors of attempt 1 (G symbols in the M3 and M5 J0-J7 replacement lines reported undeclared)",
            "supports": "the risk that the symbol gate refuses M3 and M5 again",
            "origin": "inferred"
          }
        ],
        "evidence_tier": "direct",
        "confidence": "medium",
        "user_decision_required": true,
        "question": "If the variants gate again reports the G species referenced in the M3/M5 J0-J7 replacement lines as undeclared, can the engine's symbol check be changed so that species declared in a candidate's own append block count as declared? The alternative is for me to restructure the patch, for example by putting the append first, without knowing whether the gate is sensitive to order."
      }
    ]
  }
}
```
## previous_attempt_errors
```json
[
  "M3_neighbour: a patch uses symbol(s) ['Gf8'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G07', 'G16', 'G25', 'G34'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G00_6', 'G01_5', 'G02_4', 'G03_3', 'G04_2', 'G05_1', 'G06', 'G11_4', 'G12_3', 'G13_2', 'G14_1', 'G15', 'G22_2', 'G23_1', 'G24', 'G33'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G00_32', 'G00_41', 'G00_5', 'G01_22', 'G01_31', 'G01_4', 'G02_21', 'G02_3', 'G03_11', 'G03_2', 'G04_1', 'G05', 'G11_21', 'G11_3', 'G12_11', 'G12_2', 'G13_1', 'G14', 'G22_1', 'G23'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G00_211', 'G00_22', 'G00_31', 'G00_4', 'G01_111', 'G01_21', 'G01_3', 'G02_11', 'G02_2', 'G03_1', 'G04', 'G11_11', 'G11_2', 'G12_1', 'G13', 'G22'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G00_111', 'G00_21', 'G00_3', 'G01_11', 'G01_2', 'G02_1', 'G03', 'G11_1', 'G12'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G00_11', 'G00_2', 'G01_1', 'G02', 'G11'] that neither the base nor adds_parameters declares",
  "M3_neighbour: a patch uses symbol(s) ['G00_1', 'G01'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['Gf8'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G07', 'G16', 'G25', 'G34'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G00_6', 'G01_5', 'G02_4', 'G03_3', 'G04_2', 'G05_1', 'G06', 'G11_4', 'G12_3', 'G13_2', 'G14_1', 'G15', 'G22_2', 'G23_1', 'G24', 'G33'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G00_32', 'G00_41', 'G00_5', 'G01_22', 'G01_31', 'G01_4', 'G02_21', 'G02_3', 'G03_11', 'G03_2', 'G04_1', 'G05', 'G11_21', 'G11_3', 'G12_11', 'G12_2', 'G13_1', 'G14', 'G22_1', 'G23'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G00_211', 'G00_22', 'G00_31', 'G00_4', 'G01_111', 'G01_21', 'G01_3', 'G02_11', 'G02_2', 'G03_1', 'G04', 'G11_11', 'G11_2', 'G12_1', 'G13', 'G22'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G00_111', 'G00_21', 'G00_3', 'G01_11', 'G01_2', 'G02_1', 'G03', 'G11_1', 'G12'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G00_11', 'G00_2', 'G01_1', 'G02', 'G11'] that neither the base nor adds_parameters declares",
  "M5_neighbour_and_count: a patch uses symbol(s) ['G00_1', 'G01'] that neither the base nor adds_parameters declares"
]
```
## attempt_history
```json
{
  "attempts": [
    {
      "attempt": 1,
      "gate_failures": [
        "M3_neighbour: a patch uses symbol(s) ['Gf8'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G07', 'G16', 'G25', 'G34'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_6', 'G01_5', 'G02_4', 'G03_3', 'G04_2', 'G05_1', 'G06', 'G11_4', 'G12_3', 'G13_2', 'G14_1', 'G15', 'G22_2', 'G23_1', 'G24', 'G33'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_32', 'G00_41', 'G00_5', 'G01_22', 'G01_31', 'G01_4', 'G02_21', 'G02_3', 'G03_11', 'G03_2', 'G04_1', 'G05', 'G11_21', 'G11_3', 'G12_11', 'G12_2', 'G13_1', 'G14', 'G22_1', 'G23'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_211', 'G00_22', 'G00_31', 'G00_4', 'G01_111', 'G01_21', 'G01_3', 'G02_11', 'G02_2', 'G03_1', 'G04', 'G11_11', 'G11_2', 'G12_1', 'G13', 'G22'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_111', 'G00_21', 'G00_3', 'G01_11', 'G01_2', 'G02_1', 'G03', 'G11_1', 'G12'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_11', 'G00_2', 'G01_1', 'G02', 'G11'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_1', 'G01'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['Gf8'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G07', 'G16', 'G25', 'G34'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_6', 'G01_5', 'G02_4', 'G03_3', 'G04_2', 'G05_1', 'G06', 'G11_4', 'G12_3', 'G13_2', 'G14_1', 'G15', 'G22_2', 'G23_1', 'G24', 'G33'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_32', 'G00_41', 'G00_5', 'G01_22', 'G01_31', 'G01_4', 'G02_21', 'G02_3', 'G03_11', 'G03_2', 'G04_1', 'G05', 'G11_21', 'G11_3', 'G12_11', 'G12_2', 'G13_1', 'G14', 'G22_1', 'G23'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_211', 'G00_22', 'G00_31', 'G00_4', 'G01_111', 'G01_21', 'G01_3', 'G02_11', 'G02_2', 'G03_1', 'G04', 'G11_11', 'G11_2', 'G12_1', 'G13', 'G22'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_111', 'G00_21', 'G00_3', 'G01_11', 'G01_2', 'G02_1', 'G03', 'G11_1', 'G12'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_11', 'G00_2', 'G01_1', 'G02', 'G11'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_1', 'G01'] that neither the base nor adds_parameters declares"
      ],
      "draft_summary": {
        "n_candidates": 5
      }
    },
    {
      "attempt": 2,
      "gate_failures": [
        "M3_neighbour: a patch uses symbol(s) ['Gf8'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G07', 'G16', 'G25', 'G34'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_6', 'G01_5', 'G02_4', 'G03_3', 'G04_2', 'G05_1', 'G06', 'G11_4', 'G12_3', 'G13_2', 'G14_1', 'G15', 'G22_2', 'G23_1', 'G24', 'G33'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_32', 'G00_41', 'G00_5', 'G01_22', 'G01_31', 'G01_4', 'G02_21', 'G02_3', 'G03_11', 'G03_2', 'G04_1', 'G05', 'G11_21', 'G11_3', 'G12_11', 'G12_2', 'G13_1', 'G14', 'G22_1', 'G23'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_211', 'G00_22', 'G00_31', 'G00_4', 'G01_111', 'G01_21', 'G01_3', 'G02_11', 'G02_2', 'G03_1', 'G04', 'G11_11', 'G11_2', 'G12_1', 'G13', 'G22'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_111', 'G00_21', 'G00_3', 'G01_11', 'G01_2', 'G02_1', 'G03', 'G11_1', 'G12'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_11', 'G00_2', 'G01_1', 'G02', 'G11'] that neither the base nor adds_parameters declares",
        "M3_neighbour: a patch uses symbol(s) ['G00_1', 'G01'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['Gf8'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G07', 'G16', 'G25', 'G34'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_6', 'G01_5', 'G02_4', 'G03_3', 'G04_2', 'G05_1', 'G06', 'G11_4', 'G12_3', 'G13_2', 'G14_1', 'G15', 'G22_2', 'G23_1', 'G24', 'G33'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_32', 'G00_41', 'G00_5', 'G01_22', 'G01_31', 'G01_4', 'G02_21', 'G02_3', 'G03_11', 'G03_2', 'G04_1', 'G05', 'G11_21', 'G11_3', 'G12_11', 'G12_2', 'G13_1', 'G14', 'G22_1', 'G23'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_211', 'G00_22', 'G00_31', 'G00_4', 'G01_111', 'G01_21', 'G01_3', 'G02_11', 'G02_2', 'G03_1', 'G04', 'G11_11', 'G11_2', 'G12_1', 'G13', 'G22'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_111', 'G00_21', 'G00_3', 'G01_11', 'G01_2', 'G02_1', 'G03', 'G11_1', 'G12'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_11', 'G00_2', 'G01_1', 'G02', 'G11'] that neither the base nor adds_parameters declares",
        "M5_neighbour_and_count: a patch uses symbol(s) ['G00_1', 'G01'] that neither the base nor adds_parameters declares"
      ],
      "draft_summary": {
        "n_candidates": 5
      }
    }
  ],
  "instruction": "Every attempt so far, oldest first, with its gate failures and what each draft looked like. Do not re-propose what an earlier attempt already tried; fix the failures named and keep everything that passed. If `minimal_repair` is present, return a MINIMAL edit of the previous draft \u2014 the engine measures how much you changed beyond what the failures implicated."
}
```

# Output contract
{
  "candidates": [{"id": "M1_short_slug", "label": "...", "rationale": "why this mechanism, and which tested feature it switches",
                   "set_parameters": [{"id": "an EXISTING base parameter", "nominal_value": 1.0, "estimate": false, "lb": 0.0, "ub": 0.0}],
                   "on_antimony_patch": [{"replace_reaction": "R3", "with": "R3: X -> Z; cell * (k1*Y_a + k2*X) * X;"},
                                         {"append": ["R9: -> W; cell * k9 * X;"]}],
                   "adds_parameters": [{"id": "k2", "nominal_value": 0.0, "unit": "...", "lb": 0.0, "ub": 0.0,
                                         "evidence_tier": "to_be_estimated", "source": "...", "estimate": true}],
                   "entity_glossary": {"species": [], "parameters": []}}],
  "missing": [{"equation": "A + B -> C", "why": "the conversion a candidate adds that no entry at the variants' floor describes"}],
  "build_report": {"decisions": [{"decision": "...", "rationale": "...", "alternatives_considered": "...",
                                    "evidence": [{"source": "lab_note|literature|database|general_knowledge", "locator": "...", "supports": "...", "origin": "user-provided|database-supported|literature-supported|inferred|assumed"}],
                                    "evidence_tier": "direct|transferred|default|to_be_estimated",
                                    "confidence": "high|medium|low", "user_decision_required": false, "question": ""}]}
}
NOTE on "essential_reactions", "prior_reactions" and "variants_floor" when
present: the knowledge module ran before the intent was frozen.
`essential_reactions` is the base's essential set, which `base_model`
implements; `prior_reactions` is every reaction the module and the round's
searches describe for this system, each with its `origin` (`human`, `knowledge`,
`search`) and its `grade` (a band from a declared rule table, with the source
that earned it in `because`; never a probability). A candidate keeps every
reaction of the base and may ADD a conversion described at `variants_floor` or
better (`words` says it in a sentence); take it from `prior_reactions` with its
species ids verbatim. The engine annotates what each candidate adds. In
advisory mode (the default; `grounding_instruction` says which) a candidate may
add any conversion, and one below the floor or one no entry describes is kept
and flagged to the person on the card. In strict mode the engine REFUSES a
candidate that adds a conversion below the floor, or one no entry describes: it
leaves the set, named on the card. A candidate that changes only rate laws or
switches adds no conversion and is never refused for the floor.
NOTE on "missing": OPTIONAL, and read only in strict mode. A conversion a
candidate needs that no entry at the variants' floor describes, `{equation,
why}`, species ids verbatim: the engine runs ONE targeted literature search for
this round's `missing` before it refuses anything, and admits what reaches the
variants' floor. Name it here and keep the candidate; the search decides
whether it stays.

NOTE on "known_facts" when present: what the knowledge module found, before the intent was frozen, that a model of this system needs beyond its reactions — each with an `id` (`fact_1`), a `kind`, a `statement` (a `value` and `unit` where it is quantitative), what it `applies_to`, its evidence and the grade the engine gave it (`not_applicable` when it was gathered offline). Only the facts meant for your role reach you. Use a fact where it applies instead of inventing the assumption, and where you depart from one, say why. A parameter a candidate adds whose value comes from a fact carries `source: "knowledge:<fact id>"` in `adds_parameters`, and a decision that rests on one cites its id in its `evidence` entries.
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "candidates": [
  {
   "id": "M1_independent",
   "label": "Independent repeats, strictly distributive (base)",
   "rationale": "This is the 'nothing at all' hypothesis and the distributive null. Every unmodified repeat is modified at the same constant rate, whatever the state of the molecule or its neighbours. Each kinase encounter modifies one repeat (cp = 1, q_proc = 0, no positional term), so the count distribution is binomial(8, 1 - exp(-r*t)) at every time point. M2 to M5 each depart from it in one declared feature, so every 'required' verdict (count cooperativity, neighbour effect, processivity) is measured against this reference. No differences from the base.",
   "set_parameters": [],
   "on_antimony_patch": [],
   "adds_parameters": [],
   "entity_glossary": {
    "species": [],
    "parameters": []
   }
  },
  {
   "id": "M2_count_coop",
   "label": "Count cooperativity between repeats (cp estimated)",
   "rationale": "Tests 'the rate depends only on how many repeats are already modified'. It switches on the base's count-cooperativity term: a molecule with n marks has its per-repeat rate multiplied by cp^n, with cp estimated between 0.2 and 5 on a log scale; cp = 1 is M1. Everything else is as in the base: distributive, no positional term. cp < 1 slows the late steps and lets intermediates pile up by 16 h. cp > 1 gives nucleation then fast completion, with early bimodality between 0 and high counts.",
   "set_parameters": [
    {
     "id": "cp",
     "nominal_value": 1.0,
     "estimate": true,
     "lb": 0.2,
     "ub": 5.0
    }
   ],
   "on_antimony_patch": [],
   "adds_parameters": [],
   "entity_glossary": {
    "species": [],
    "parameters": []
   }
  },
  {
   "id": "M3_neighbour",
   "label": "Nearest-neighbour effect (positional model, nb estimated)",
   "rationale": "Tests 'modifying a repeat changes the rate at which its immediate neighbours are modified'. The base counts marks and cannot express this, because a neighbour effect breaks the count lumping (construction decision 1). It is therefore added as a patch that implements construction's positional rule exactly. Each unmodified repeat is modified at kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, where m is the number of its marked immediate neighbours. cp is held at 1, so nb is the only tested feature; it is estimated between 0.01 and 100 on a log scale, and nb = 1 reproduces M1 exactly. The positional model is written out state by state and reaction by reaction on the 74 gap-structure classes onto which the 256 configurations lump exactly (build report). Gf8 is the unmodified molecule. In G<a><b>_<g...>, a <= b are the unmarked stretches at the two chain ends and the digits after the underscore are the unmarked stretches between marks. Each class reaction also moves one molecule from CTD_n to CTD_n+1 and consumes one ATP, so CTD_n stays the count readout and equals its class sum identically. J0 to J7 stay in the model at zero rate, and the class reactions take over their role. nb < 1 (neighbour inhibition) jams molecules at up to 4 non-adjacent marks before a slow filling phase, a stall between 2 h and 16 h that cp alone cannot shape. nb > 1 (neighbour facilitation) gives nucleation-and-growth, which cp > 1 and processivity also produce.",
   "set_parameters": [],
   "on_antimony_patch": [
    {
     "replace_reaction": "J0",
     "with": "J0: CTD_0 + ATP -> CTD_1 + ADP; 0;"
    },
    {
     "replace_reaction": "J1",
     "with": "J1: CTD_1 + ATP -> CTD_2 + ADP; 0;"
    },
    {
     "replace_reaction": "J2",
     "with": "J2: CTD_2 + ATP -> CTD_3 + ADP; 0;"
    },
    {
     "replace_reaction": "J3",
     "with": "J3: CTD_3 + ATP -> CTD_4 + ADP; 0;"
    },
    {
     "replace_reaction": "J4",
     "with": "J4: CTD_4 + ATP -> CTD_5 + ADP; 0;"
    },
    {
     "replace_reaction": "J5",
     "with": "J5: CTD_5 + ATP -> CTD_6 + ADP; 0;"
    },
    {
     "replace_reaction": "J6",
     "with": "J6: CTD_6 + ATP -> CTD_7 + ADP; 0;"
    },
    {
     "replace_reaction": "J7",
     "with": "J7: CTD_7 + ATP -> CTD_8 + ADP; 0;"
    },
    {
     "append": [
      "// Positional refinement by gap class: Gf8 = unmodified; G<a><b>_<g...> = unmarked end stretches a <= b and unmarked interior stretches g... between marks; n = 8 - a - b - sum(g)",
      "// Each G reaction from a class with n marks also carries CTD_n + ATP -> CTD_n+1 + ADP, so the G classes with n marks sum to CTD_n identically and ATP is consumed once per modification; J0-J7 are kept at zero rate",
      "species Gf8 in vial, G07 in vial, G16 in vial, G25 in vial, G34 in vial;",
      "species G06 in vial, G15 in vial, G24 in vial, G33 in vial, G05_1 in vial, G14_1 in vial, G23_1 in vial, G04_2 in vial;",
      "species G13_2 in vial, G22_2 in vial, G03_3 in vial, G12_3 in vial, G02_4 in vial, G11_4 in vial, G01_5 in vial, G00_6 in vial;",
      "species G05 in vial, G14 in vial, G23 in vial, G04_1 in vial, G13_1 in vial, G22_1 in vial, G03_2 in vial, G12_2 in vial, G02_3 in vial, G11_3 in vial;",
      "species G01_4 in vial, G00_5 in vial, G03_11 in vial, G12_11 in vial, G02_21 in vial, G11_21 in vial, G01_31 in vial, G01_22 in vial, G00_41 in vial, G00_32 in vial;",
      "species G04 in vial, G13 in vial, G22 in vial, G03_1 in vial, G12_1 in vial, G02_2 in vial, G11_2 in vial, G01_3 in vial;",
      "species G00_4 in vial, G02_11 in vial, G11_11 in vial, G01_21 in vial, G00_31 in vial, G00_22 in vial, G01_111 in vial, G00_211 in vial;",
      "species G03 in vial, G12 in vial, G02_1 in vial, G11_1 in vial, G01_2 in vial, G00_3 in vial, G01_11 in vial, G00_21 in vial, G00_111 in vial;",
      "species G02 in vial, G11 in vial, G01_1 in vial, G00_2 in vial, G00_11 in vial, G01 in vial, G00_1 in vial, G00 in vial;",
      "Gf8 = 100; G07 = 0; G16 = 0; G25 = 0; G34 = 0;",
      "G06 = 0; G15 = 0; G24 = 0; G33 = 0; G05_1 = 0; G14_1 = 0; G23_1 = 0; G04_2 = 0;",
      "G13_2 = 0; G22_2 = 0; G03_3 = 0; G12_3 = 0; G02_4 = 0; G11_4 = 0; G01_5 = 0; G00_6 = 0;",
      "G05 = 0; G14 = 0; G23 = 0; G04_1 = 0; G13_1 = 0; G22_1 = 0; G03_2 = 0; G12_2 = 0; G02_3 = 0; G11_3 = 0;",
      "G01_4 = 0; G00_5 = 0; G03_11 = 0; G12_11 = 0; G02_21 = 0; G11_21 = 0; G01_31 = 0; G01_22 = 0; G00_41 = 0; G00_32 = 0;",
      "G04 = 0; G13 = 0; G22 = 0; G03_1 = 0; G12_1 = 0; G02_2 = 0; G11_2 = 0; G01_3 = 0;",
      "G00_4 = 0; G02_11 = 0; G11_11 = 0; G01_21 = 0; G00_31 = 0; G00_22 = 0; G01_111 = 0; G00_211 = 0;",
      "G03 = 0; G12 = 0; G02_1 = 0; G11_1 = 0; G01_2 = 0; G00_3 = 0; G01_11 = 0; G00_21 = 0; G00_111 = 0;",
      "G02 = 0; G11 = 0; G01_1 = 0; G00_2 = 0; G00_11 = 0; G01 = 0; G00_1 = 0; G00 = 0;",
      "nb = 1;",
      "// rate per unmodified repeat: kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, m = marked immediate neighbours; coefficients count the repeats leading to each class",
      "Q_Gf8_G07: Gf8 + CTD_0 + ATP -> G07 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_Gf8_G16: Gf8 + CTD_0 + ATP -> G16 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_Gf8_G25: Gf8 + CTD_0 + ATP -> G25 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_Gf8_G34: Gf8 + CTD_0 + ATP -> G34 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_G07_G06: G07 + CTD_1 + ATP -> G06 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G07;",
      "Q_G07_G05_1: G07 + CTD_1 + ATP -> G05_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G04_2: G07 + CTD_1 + ATP -> G04_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G03_3: G07 + CTD_1 + ATP -> G03_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G02_4: G07 + CTD_1 + ATP -> G02_4 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G01_5: G07 + CTD_1 + ATP -> G01_5 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G00_6: G07 + CTD_1 + ATP -> G00_6 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G16_G06: G16 + CTD_1 + ATP -> G06 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
      "Q_G16_G15: G16 + CTD_1 + ATP -> G15 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
      "Q_G16_G14_1: G16 + CTD_1 + ATP -> G14_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G13_2: G16 + CTD_1 + ATP -> G13_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G12_3: G16 + CTD_1 + ATP -> G12_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G11_4: G16 + CTD_1 + ATP -> G11_4 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G01_5: G16 + CTD_1 + ATP -> G01_5 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G25_G15: G25 + CTD_1 + ATP -> G15 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
      "Q_G25_G24: G25 + CTD_1 + ATP -> G24 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
      "Q_G25_G05_1: G25 + CTD_1 + ATP -> G05_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G23_1: G25 + CTD_1 + ATP -> G23_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G22_2: G25 + CTD_1 + ATP -> G22_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G12_3: G25 + CTD_1 + ATP -> G12_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G02_4: G25 + CTD_1 + ATP -> G02_4 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G34_G24: G34 + CTD_1 + ATP -> G24 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
      "Q_G34_G33: G34 + CTD_1 + ATP -> G33 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
      "Q_G34_G23_1: G34 + CTD_1 + ATP -> G23_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G14_1: G34 + CTD_1 + ATP -> G14_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G13_2: G34 + CTD_1 + ATP -> G13_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G04_2: G34 + CTD_1 + ATP -> G04_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G03_3: G34 + CTD_1 + ATP -> G03_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G06_G05: G06 + CTD_2 + ATP -> G05 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G06;",
      "Q_G06_G04_1: G06 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G03_2: G06 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G02_3: G06 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G01_4: G06 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G00_5: G06 + CTD_2 + ATP -> G00_5 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G15_G05: G15 + CTD_2 + ATP -> G05 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
      "Q_G15_G14: G15 + CTD_2 + ATP -> G14 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
      "Q_G15_G13_1: G15 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G15_G12_2: G15 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G15_G11_3: G15 + CTD_2 + ATP -> G11_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G15_G01_4: G15 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G24_G14: G24 + CTD_2 + ATP -> G14 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
      "Q_G24_G23: G24 + CTD_2 + ATP -> G23 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
      "Q_G24_G04_1: G24 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G24_G22_1: G24 + CTD_2 + ATP -> G22_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G24_G12_2: G24 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G24_G02_3: G24 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G33_G23: G33 + CTD_2 + ATP -> G23 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G33;",
      "Q_G33_G13_1: G33 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
      "Q_G33_G03_2: G33 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
      "Q_G05_1_G05: G05_1 + CTD_2 + ATP -> G05 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G05_1;",
      "Q_G05_1_G04_1: G05_1 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G05_1;",
      "Q_G05_1_G03_11: G05_1 + CTD_2 + ATP -> G03_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G05_1_G02_21: G05_1 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G05_1_G01_31: G05_1 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G05_1_G00_41: G05_1 + CTD_2 + ATP -> G00_41 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G14_1_G14: G14_1 + CTD_2 + ATP -> G14 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G14_1;",
      "Q_G14_1_G04_1: G14_1 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
      "Q_G14_1_G13_1: G14_1 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
      "Q_G14_1_G12_11: G14_1 + CTD_2 + ATP -> G12_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
      "Q_G14_1_G11_21: G14_1 + CTD_2 + ATP -> G11_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
      "Q_G14_1_G01_31: G14_1 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
      "Q_G23_1_G23: G23_1 + CTD_2 + ATP -> G23 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G23_1;",
      "Q_G23_1_G13_1: G23_1 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
      "Q_G23_1_G22_1: G23_1 + CTD_2 + ATP -> G22_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
      "Q_G23_1_G12_11: G23_1 + CTD_2 + ATP -> G12_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
      "Q_G23_1_G03_11: G23_1 + CTD_2 + ATP -> G03_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
      "Q_G23_1_G02_21: G23_1 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
      "Q_G04_2_G04_1: G04_2 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G04_2;",
      "Q_G04_2_G03_2: G04_2 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G04_2;",
      "Q_G04_2_G02_21: G04_2 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
      "Q_G04_2_G01_22: G04_2 + CTD_2 + ATP -> G01_22 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
      "Q_G04_2_G00_32: G04_2 + CTD_2 + ATP -> G00_32 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
      "Q_G13_2_G13_1: G13_2 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G13_2;",
      "Q_G13_2_G03_2: G13_2 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
      "Q_G13_2_G12_2: G13_2 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
      "Q_G13_2_G11_21: G13_2 + CTD_2 + ATP -> G11_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
      "Q_G13_2_G01_22: G13_2 + CTD_2 + ATP -> G01_22 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
      "Q_G22_2_G22_1: G22_2 + CTD_2 + ATP -> G22_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
      "Q_G22_2_G12_2: G22_2 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
      "Q_G22_2_G02_21: G22_2 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G22_2;",
      "Q_G03_3_G03_2: G03_3 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G03_3;",
      "Q_G03_3_G02_3: G03_3 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G03_3;",
      "Q_G03_3_G03_11: G03_3 + CTD_2 + ATP -> G03_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
      "Q_G03_3_G01_31: G03_3 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
      "Q_G03_3_G00_32: G03_3 + CTD_2 + ATP -> G00_32 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
      "Q_G12_3_G12_2: G12_3 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G12_3;",
      "Q_G12_3_G02_3: G12_3 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
      "Q_G12_3_G11_3: G12_3 + CTD_2 + ATP -> G11_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
      "Q_G12_3_G12_11: G12_3 + CTD_2 + ATP -> G12_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
      "Q_G12_3_G01_31: G12_3 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
      "Q_G02_4_G02_3: G02_4 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G02_4;",
      "Q_G02_4_G01_4: G02_4 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G02_4;",
      "Q_G02_4_G02_21: G02_4 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G02_4;",
      "Q_G02_4_G00_41: G02_4 + CTD_2 + ATP -> G00_41 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G02_4;",
      "Q_G11_4_G11_3: G11_4 + CTD_2 + ATP -> G11_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
      "Q_G11_4_G01_4: G11_4 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
      "Q_G11_4_G11_21: G11_4 + CTD_2 + ATP -> G11_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G11_4;",
      "Q_G01_5_G01_4: G01_5 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G01_5;",
      "Q_G01_5_G00_5: G01_5 + CTD_2 + ATP -> G00_5 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G01_5;",
      "Q_G01_5_G01_31: G01_5 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G01_5;",
      "Q_G01_5_G01_22: G01_5 + CTD_2 + ATP -> G01_22 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G01_5;",
      "Q_G00_6_G00_5: G00_6 + CTD_2 + ATP -> G00_5 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G00_6;",
      "Q_G00_6_G00_41: G00_6 + CTD_2 + ATP -> G00_41 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
      "Q_G00_6_G00_32: G00_6 + CTD_2 + ATP -> G00_32 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
      "Q_G05_G04: G05 + CTD_3 + ATP -> G04 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G05;",
      "Q_G05_G03_1: G05 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G05_G02_2: G05 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G05_G01_3: G05 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G05_G00_4: G05 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G14_G04: G14 + CTD_3 + ATP -> G04 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
      "Q_G14_G13: G14 + CTD_3 + ATP -> G13 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
      "Q_G14_G12_1: G14 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
      "Q_G14_G11_2: G14 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
      "Q_G14_G01_3: G14 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
      "Q_G23_G13: G23 + CTD_3 + ATP -> G13 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
      "Q_G23_G22: G23 + CTD_3 + ATP -> G22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
      "Q_G23_G12_1: G23 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
      "Q_G23_G03_1: G23 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
      "Q_G23_G02_2: G23 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
      "Q_G04_1_G04: G04_1 + CTD_3 + ATP -> G04 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G04_1;",
      "Q_G04_1_G03_1: G04_1 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G04_1;",
      "Q_G04_1_G02_11: G04_1 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
      "Q_G04_1_G01_21: G04_1 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
      "Q_G04_1_G00_31: G04_1 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
      "Q_G13_1_G13: G13_1 + CTD_3 + ATP -> G13 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G13_1;",
      "Q_G13_1_G03_1: G13_1 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
      "Q_G13_1_G12_1: G13_1 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
      "Q_G13_1_G11_11: G13_1 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
      "Q_G13_1_G01_21: G13_1 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
      "Q_G22_1_G22: G22_1 + CTD_3 + ATP -> G22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G22_1;",
      "Q_G22_1_G12_1: G22_1 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G22_1;",
      "Q_G22_1_G02_11: G22_1 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G22_1;",
      "Q_G03_2_G03_1: G03_2 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G03_2;",
      "Q_G03_2_G02_2: G03_2 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_2;",
      "Q_G03_2_G01_21: G03_2 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
      "Q_G03_2_G00_22: G03_2 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
      "Q_G12_2_G12_1: G12_2 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G12_2;",
      "Q_G12_2_G02_2: G12_2 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
      "Q_G12_2_G11_2: G12_2 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
      "Q_G12_2_G01_21: G12_2 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_2;",
      "Q_G02_3_G02_2: G02_3 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_3;",
      "Q_G02_3_G01_3: G02_3 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_3;",
      "Q_G02_3_G02_11: G02_3 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
      "Q_G02_3_G00_31: G02_3 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
      "Q_G11_3_G11_2: G11_3 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
      "Q_G11_3_G01_3: G11_3 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
      "Q_G11_3_G11_11: G11_3 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G11_3;",
      "Q_G01_4_G01_3: G01_4 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_4;",
      "Q_G01_4_G00_4: G01_4 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_4;",
      "Q_G01_4_G01_21: G01_4 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G01_4;",
      "Q_G00_5_G00_4: G00_5 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_5;",
      "Q_G00_5_G00_31: G00_5 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_5;",
      "Q_G00_5_G00_22: G00_5 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_5;",
      "Q_G03_11_G03_1: G03_11 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G03_11;",
      "Q_G03_11_G02_11: G03_11 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_11;",
      "Q_G03_11_G01_111: G03_11 + CTD_3 + ATP -> G01_111 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
      "Q_G03_11_G00_211: G03_11 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
      "Q_G12_11_G12_1: G12_11 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G12_11;",
      "Q_G12_11_G02_11: G12_11 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
      "Q_G12_11_G11_11: G12_11 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
      "Q_G12_11_G01_111: G12_11 + CTD_3 + ATP -> G01_111 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_11;",
      "Q_G02_21_G02_2: G02_21 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G02_21;",
      "Q_G02_21_G02_11: G02_21 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_21;",
      "Q_G02_21_G01_21: G02_21 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_21;",
      "Q_G02_21_G00_211: G02_21 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_21;",
      "Q_G11_21_G11_2: G11_21 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G11_21;",
      "Q_G11_21_G11_11: G11_21 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
      "Q_G11_21_G01_21: G11_21 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
      "Q_G01_31_G01_3: G01_31 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G01_31;",
      "Q_G01_31_G01_21: G01_31 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_31;",
      "Q_G01_31_G00_31: G01_31 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_31;",
      "Q_G01_31_G01_111: G01_31 + CTD_3 + ATP -> G01_111 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G01_31;",
      "Q_G01_22_G01_21: G01_22 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*4*nb*G01_22;",
      "Q_G01_22_G00_22: G01_22 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_22;",
      "Q_G00_41_G00_4: G00_41 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G00_41;",
      "Q_G00_41_G00_31: G00_41 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_41;",
      "Q_G00_41_G00_211: G00_41 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_41;",
      "Q_G00_32_G00_31: G00_32 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
      "Q_G00_32_G00_22: G00_32 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
      "Q_G00_32_G00_211: G00_32 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_32;",
      "Q_G04_G03: G04 + CTD_4 + ATP -> G03 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G04;",
      "Q_G04_G02_1: G04 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
      "Q_G04_G01_2: G04 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
      "Q_G04_G00_3: G04 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
      "Q_G13_G03: G13 + CTD_4 + ATP -> G03 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
      "Q_G13_G12: G13 + CTD_4 + ATP -> G12 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
      "Q_G13_G11_1: G13 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
      "Q_G13_G01_2: G13 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
      "Q_G22_G12: G22 + CTD_4 + ATP -> G12 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G22;",
      "Q_G22_G02_1: G22 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G22;",
      "Q_G03_1_G03: G03_1 + CTD_4 + ATP -> G03 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G03_1;",
      "Q_G03_1_G02_1: G03_1 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G03_1;",
      "Q_G03_1_G01_11: G03_1 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
      "Q_G03_1_G00_21: G03_1 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
      "Q_G12_1_G12: G12_1 + CTD_4 + ATP -> G12 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G12_1;",
      "Q_G12_1_G02_1: G12_1 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
      "Q_G12_1_G11_1: G12_1 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
      "Q_G12_1_G01_11: G12_1 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G12_1;",
      "Q_G02_2_G02_1: G02_2 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G02_2;",
      "Q_G02_2_G01_2: G02_2 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_2;",
      "Q_G02_2_G00_21: G02_2 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_2;",
      "Q_G11_2_G11_1: G11_2 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
      "Q_G11_2_G01_2: G11_2 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
      "Q_G01_3_G01_2: G01_3 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_3;",
      "Q_G01_3_G00_3: G01_3 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_3;",
      "Q_G01_3_G01_11: G01_3 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G01_3;",
      "Q_G00_4_G00_3: G00_4 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_4;",
      "Q_G00_4_G00_21: G00_4 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G00_4;",
      "Q_G02_11_G02_1: G02_11 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G02_11;",
      "Q_G02_11_G01_11: G02_11 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_11;",
      "Q_G02_11_G00_111: G02_11 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_11;",
      "Q_G11_11_G11_1: G11_11 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G11_11;",
      "Q_G11_11_G01_11: G11_11 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_11;",
      "Q_G01_21_G01_2: G01_21 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G01_21;",
      "Q_G01_21_G01_11: G01_21 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_21;",
      "Q_G01_21_G00_21: G01_21 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_21;",
      "Q_G00_31_G00_3: G00_31 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G00_31;",
      "Q_G00_31_G00_21: G00_31 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_31;",
      "Q_G00_31_G00_111: G00_31 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G00_31;",
      "Q_G00_22_G00_21: G00_22 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*4*nb*G00_22;",
      "Q_G01_111_G01_11: G01_111 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*3*nb^2*G01_111;",
      "Q_G01_111_G00_111: G01_111 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_111;",
      "Q_G00_211_G00_21: G00_211 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G00_211;",
      "Q_G00_211_G00_111: G00_211 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_211;",
      "Q_G03_G02: G03 + CTD_5 + ATP -> G02 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G03;",
      "Q_G03_G01_1: G03 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
      "Q_G03_G00_2: G03 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
      "Q_G12_G02: G12 + CTD_5 + ATP -> G02 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
      "Q_G12_G11: G12 + CTD_5 + ATP -> G11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
      "Q_G12_G01_1: G12 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G12;",
      "Q_G02_1_G02: G02_1 + CTD_5 + ATP -> G02 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G02_1;",
      "Q_G02_1_G01_1: G02_1 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G02_1;",
      "Q_G02_1_G00_11: G02_1 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G02_1;",
      "Q_G11_1_G11: G11_1 + CTD_5 + ATP -> G11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G11_1;",
      "Q_G11_1_G01_1: G11_1 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G11_1;",
      "Q_G01_2_G01_1: G01_2 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G01_2;",
      "Q_G01_2_G00_2: G01_2 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_2;",
      "Q_G00_3_G00_2: G00_3 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_3;",
      "Q_G00_3_G00_11: G00_3 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G00_3;",
      "Q_G01_11_G01_1: G01_11 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb^2*G01_11;",
      "Q_G01_11_G00_11: G01_11 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_11;",
      "Q_G00_21_G00_2: G00_21 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G00_21;",
      "Q_G00_21_G00_11: G00_21 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_21;",
      "Q_G00_111_G00_11: G00_111 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*3*nb^2*G00_111;",
      "Q_G02_G01: G02 + CTD_6 + ATP -> G01 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G02;",
      "Q_G02_G00_1: G02 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*G02;",
      "Q_G11_G01: G11 + CTD_6 + ATP -> G01 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G11;",
      "Q_G01_1_G01: G01_1 + CTD_6 + ATP -> G01 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb^2*G01_1;",
      "Q_G01_1_G00_1: G01_1 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G01_1;",
      "Q_G00_2_G00_1: G00_2 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G00_2;",
      "Q_G00_11_G00_1: G00_11 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb^2*G00_11;",
      "Q_G01_G00: G01 + CTD_7 + ATP -> G00 + CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb*G01;",
      "Q_G00_1_G00: G00_1 + CTD_7 + ATP -> G00 + CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb^2*G00_1;"
     ]
    }
   ],
   "adds_parameters": [
    {
     "id": "nb",
     "nominal_value": 1.0,
     "unit": "dimensionless (fold change of an unmodified repeat's rate per phosphorylated immediate neighbour)",
     "lb": 0.01,
     "ub": 100.0,
     "evidence_tier": "to_be_estimated",
     "source": "base_model construction decision (positional candidate rule): neutral value 1, bounds 0.01 to 100; log10 scale",
     "estimate": true
    }
   ],
   "entity_glossary": {
    "species": [
     {
      "id": "Gf8",
      "denotes": "CTD with 0 marks: one stretch of 8 unmarked repeats (equals CTD_0)",
      "unit_convention": "uM; 100 at t = 0; positional refinement of CTD, not extra substrate",
      "lump_membership": "the single unmarked configuration"
     },
     {
      "id": "G07",
      "denotes": "1 mark, on repeat 1 or 8 (end gaps 0,7); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {0,7}, no interior gap"
     },
     {
      "id": "G16",
      "denotes": "1 mark, on repeat 2 or 7 (end gaps 1,6); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {1,6}, no interior gap"
     },
     {
      "id": "G25",
      "denotes": "1 mark, on repeat 3 or 6 (end gaps 2,5); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {2,5}, no interior gap"
     },
     {
      "id": "G34",
      "denotes": "1 mark, on repeat 4 or 5 (end gaps 3,4); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {3,4}, no interior gap"
     },
     {
      "id": "G06",
      "denotes": "2 marks; end gaps 0,6; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,6}; interior {}"
     },
     {
      "id": "G15",
      "denotes": "2 marks; end gaps 1,5; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,5}; interior {}"
     },
     {
      "id": "G24",
      "denotes": "2 marks; end gaps 2,4; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {2,4}; interior {}"
     },
     {
      "id": "G33",
      "denotes": "2 marks; end gaps 3,3; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {3,3}; interior {}"
     },
     {
      "id": "G05_1",
      "denotes": "2 marks; end gaps 0,5; interior gap 1; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,5}; interior {1}"
     },
     {
      "id": "G14_1",
      "denotes": "2 marks; end gaps 1,4; interior gap 1; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,4}; interior {1}"
     },
     {
      "id": "G23_1",
      "denotes": "2 marks; end gaps 2,3; interior gap 1; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {2,3}; interior {1}"
     },
     {
      "id": "G04_2",
      "denotes": "2 marks; end gaps 0,4; interior gap 2; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,4}; interior {2}"
     },
     {
      "id": "G13_2",
      "denotes": "2 marks; end gaps 1,3; interior gap 2; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,3}; interior {2}"
     },
     {
      "id": "G22_2",
      "denotes": "2 marks; end gaps 2,2; interior gap 2; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {2,2}; interior {2}"
     },
     {
      "id": "G03_3",
      "denotes": "2 marks; end gaps 0,3; interior gap 3; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,3}; interior {3}"
     },
     {
      "id": "G12_3",
      "denotes": "2 marks; end gaps 1,2; interior gap 3; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,2}; interior {3}"
     },
     {
      "id": "G02_4",
      "denotes": "2 marks; end gaps 0,2; interior gap 4; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,2}; interior {4}"
     },
     {
      "id": "G11_4",
      "denotes": "2 marks; end gaps 1,1; interior gap 4; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,1}; interior {4}"
     },
     {
      "id": "G01_5",
      "denotes": "2 marks; end gaps 0,1; interior gap 5; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,1}; interior {5}"
     },
     {
      "id": "G00_6",
      "denotes": "2 marks, on repeats 1 and 8; interior gap 6; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,0}; interior {6}"
     },
     {
      "id": "G05",
      "denotes": "3 marks; end gaps 0,5; no interior gap; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,5}; interior {}"
     },
     {
      "id": "G14",
      "denotes": "3 marks; end gaps 1,4; no interior gap; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,4}; interior {}"
     },
     {
      "id": "G23",
      "denotes": "3 marks; end gaps 2,3; no interior gap; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {2,3}; interior {}"
     },
     {
      "id": "G04_1",
      "denotes": "3 marks; end gaps 0,4; interior gap 1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,4}; interior {1}"
     },
     {
      "id": "G13_1",
      "denotes": "3 marks; end gaps 1,3; interior gap 1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,3}; interior {1}"
     },
     {
      "id": "G22_1",
      "denotes": "3 marks; end gaps 2,2; interior gap 1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {2,2}; interior {1}"
     },
     {
      "id": "G03_2",
      "denotes": "3 marks; end gaps 0,3; interior gap 2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,3}; interior {2}"
     },
     {
      "id": "G12_2",
      "denotes": "3 marks; end gaps 1,2; interior gap 2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,2}; interior {2}"
     },
     {
      "id": "G02_3",
      "denotes": "3 marks; end gaps 0,2; interior gap 3; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,2}; interior {3}"
     },
     {
      "id": "G11_3",
      "denotes": "3 marks; end gaps 1,1; interior gap 3; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,1}; interior {3}"
     },
     {
      "id": "G01_4",
      "denotes": "3 marks; end gaps 0,1; interior gap 4; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,1}; interior {4}"
     },
     {
      "id": "G00_5",
      "denotes": "3 marks; end gaps 0,0; interior gap 5; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,0}; interior {5}"
     },
     {
      "id": "G03_11",
      "denotes": "3 marks; end gaps 0,3; interior gaps 1,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,3}; interior {1,1}"
     },
     {
      "id": "G12_11",
      "denotes": "3 marks; end gaps 1,2; interior gaps 1,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,2}; interior {1,1}"
     },
     {
      "id": "G02_21",
      "denotes": "3 marks; end gaps 0,2; interior gaps 2,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,2}; interior {2,1}"
     },
     {
      "id": "G11_21",
      "denotes": "3 marks; end gaps 1,1; interior gaps 2,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,1}; interior {2,1}"
     },
     {
      "id": "G01_31",
      "denotes": "3 marks; end gaps 0,1; interior gaps 3,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,1}; interior {3,1}"
     },
     {
      "id": "G01_22",
      "denotes": "3 marks; end gaps 0,1; interior gaps 2,2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,1}; interior {2,2}"
     },
     {
      "id": "G00_41",
      "denotes": "3 marks; end gaps 0,0; interior gaps 4,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,0}; interior {4,1}"
     },
     {
      "id": "G00_32",
      "denotes": "3 marks; end gaps 0,0; interior gaps 3,2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,0}; interior {3,2}"
     },
     {
      "id": "G04",
      "denotes": "4 marks; end gaps 0,4; no interior gap; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,4}; interior {}"
     },
     {
      "id": "G13",
      "denotes": "4 marks; end gaps 1,3; no interior gap; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,3}; interior {}"
     },
     {
      "id": "G22",
      "denotes": "4 marks; end gaps 2,2; no interior gap; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {2,2}; interior {}"
     },
     {
      "id": "G03_1",
      "denotes": "4 marks; end gaps 0,3; interior gap 1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,3}; interior {1}"
     },
     {
      "id": "G12_1",
      "denotes": "4 marks; end gaps 1,2; interior gap 1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,2}; interior {1}"
     },
     {
      "id": "G02_2",
      "denotes": "4 marks; end gaps 0,2; interior gap 2; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,2}; interior {2}"
     },
     {
      "id": "G11_2",
      "denotes": "4 marks; end gaps 1,1; interior gap 2; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,1}; interior {2}"
     },
     {
      "id": "G01_3",
      "denotes": "4 marks; end gaps 0,1; interior gap 3; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,1}; interior {3}"
     },
     {
      "id": "G00_4",
      "denotes": "4 marks; end gaps 0,0; interior gap 4; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {4}"
     },
     {
      "id": "G02_11",
      "denotes": "4 marks; end gaps 0,2; interior gaps 1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,2}; interior {1,1}"
     },
     {
      "id": "G11_11",
      "denotes": "4 marks; end gaps 1,1; interior gaps 1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,1}; interior {1,1}"
     },
     {
      "id": "G01_21",
      "denotes": "4 marks; end gaps 0,1; interior gaps 2,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,1}; interior {2,1}"
     },
     {
      "id": "G00_31",
      "denotes": "4 marks; end gaps 0,0; interior gaps 3,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {3,1}"
     },
     {
      "id": "G00_22",
      "denotes": "4 marks; end gaps 0,0; interior gaps 2,2; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {2,2}"
     },
     {
      "id": "G01_111",
      "denotes": "4 marks on alternate repeats (1,3,5,7 or 2,4,6,8): end gaps 0,1, interior gaps 1,1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,1}; interior {1,1,1}"
     },
     {
      "id": "G00_211",
      "denotes": "4 marks; end gaps 0,0; interior gaps 2,1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {2,1,1}"
     },
     {
      "id": "G03",
      "denotes": "5 marks; end gaps 0,3; no interior gap; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,3}; interior {}"
     },
     {
      "id": "G12",
      "denotes": "5 marks; end gaps 1,2; no interior gap; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {1,2}; interior {}"
     },
     {
      "id": "G02_1",
      "denotes": "5 marks; end gaps 0,2; interior gap 1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,2}; interior {1}"
     },
     {
      "id": "G11_1",
      "denotes": "5 marks; end gaps 1,1; interior gap 1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {1,1}; interior {1}"
     },
     {
      "id": "G01_2",
      "denotes": "5 marks; end gaps 0,1; interior gap 2; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,1}; interior {2}"
     },
     {
      "id": "G00_3",
      "denotes": "5 marks; end gaps 0,0; interior gap 3; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,0}; interior {3}"
     },
     {
      "id": "G01_11",
      "denotes": "5 marks; end gaps 0,1; interior gaps 1,1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,1}; interior {1,1}"
     },
     {
      "id": "G00_21",
      "denotes": "5 marks; end gaps 0,0; interior gaps 2,1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,0}; interior {2,1}"
     },
     {
      "id": "G00_111",
      "denotes": "5 marks; end gaps 0,0; interior gaps 1,1,1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,0}; interior {1,1,1}"
     },
     {
      "id": "G02",
      "denotes": "6 marks; end gaps 0,2; no interior gap; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,2}; interior {}"
     },
     {
      "id": "G11",
      "denotes": "6 marks, on repeats 2 to 7 (end gaps 1,1); refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {1,1}; interior {}"
     },
     {
      "id": "G01_1",
      "denotes": "6 marks; end gaps 0,1; interior gap 1; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,1}; interior {1}"
     },
     {
      "id": "G00_2",
      "denotes": "6 marks; end gaps 0,0; interior gap 2; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,0}; interior {2}"
     },
     {
      "id": "G00_11",
      "denotes": "6 marks; end gaps 0,0; interior gaps 1,1; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,0}; interior {1,1}"
     },
     {
      "id": "G01",
      "denotes": "7 marks, the unmarked repeat at an end (repeat 1 or 8); refines CTD_7",
      "unit_convention": "uM; sums with G00_1 to CTD_7",
      "lump_membership": "end gaps {0,1}; interior {}"
     },
     {
      "id": "G00_1",
      "denotes": "7 marks, the unmarked repeat interior (repeats 2 to 7); refines CTD_7",
      "unit_convention": "uM; sums with G01 to CTD_7",
      "lump_membership": "end gaps {0,0}; interior {1}"
     },
     {
      "id": "G00",
      "denotes": "all 8 repeats marked (equals CTD_8)",
      "unit_convention": "uM",
      "lump_membership": "the single fully marked configuration"
     }
    ],
    "parameters": [
     {
      "id": "nb",
      "role": "nearest-neighbour switch: fold change of an unmodified repeat's rate per phosphorylated immediate neighbour (m = 0, 1 or 2; repeats 1 and 8 have one neighbour)",
      "convention": "neutral value 1 (no neighbour effect); < 1 inhibition, > 1 facilitation; log10 scale, bounds 0.01 to 100",
      "set_per_condition": false
     }
    ]
   }
  },
  {
   "id": "M4_processive",
   "label": "Processive continuation (q_proc estimated)",
   "rationale": "Tests the earlier by-eye conclusion that P-TEFb is distributive. It switches on the base's processivity term: after each modification the kinase continues to another unmodified repeat with probability q_proc. q_proc is estimated between 1e-4 and 0.99 on a log scale, with nominal 0.1 inside the box; the lower bound is the strictly distributive M1 to within 1e-4. Repeats are otherwise independent (cp = 1) and there is no positional term. Strong processivity predicts early bimodality, with intermediates that persist to 16 h because released molecules return to the distributive pace. The q_proc profile is the direct test. If it reaches the lower bound with the likelihood flat below about 0.1, distributive action is supported. If a q_proc clearly above 0 is required, the by-eye conclusion fails.",
   "set_parameters": [
    {
     "id": "q_proc",
     "nominal_value": 0.1,
     "estimate": true,
     "lb": 0.0001,
     "ub": 0.99
    }
   ],
   "on_antimony_patch": [],
   "adds_parameters": [],
   "entity_glossary": {
    "species": [],
    "parameters": []
   }
  },
  {
   "id": "M5_neighbour_and_count",
   "label": "Nearest-neighbour effect plus count cooperativity (nb and cp estimated)",
   "rationale": "This candidate combines two features deliberately: the neighbour term nb (as in M3, with the identical positional patch) and count cooperativity cp (as in M2), both estimated. It is the model that contains M2 and M3 as nested cases. M5 against M2 asks whether a neighbour effect is needed once count cooperativity is allowed, and M5 against M3 asks the converse. The joint nb-cp profile shows whether these data can separate the two at all, which is the separability statement the question asks for. Distributive (q_proc = 0). At nb = 1 it reproduces M2 exactly; at cp = 1 it reproduces M3.",
   "set_parameters": [
    {
     "id": "cp",
     "nominal_value": 1.0,
     "estimate": true,
     "lb": 0.2,
     "ub": 5.0
    }
   ],
   "on_antimony_patch": [
    {
     "replace_reaction": "J0",
     "with": "J0: CTD_0 + ATP -> CTD_1 + ADP; 0;"
    },
    {
     "replace_reaction": "J1",
     "with": "J1: CTD_1 + ATP -> CTD_2 + ADP; 0;"
    },
    {
     "replace_reaction": "J2",
     "with": "J2: CTD_2 + ATP -> CTD_3 + ADP; 0;"
    },
    {
     "replace_reaction": "J3",
     "with": "J3: CTD_3 + ATP -> CTD_4 + ADP; 0;"
    },
    {
     "replace_reaction": "J4",
     "with": "J4: CTD_4 + ATP -> CTD_5 + ADP; 0;"
    },
    {
     "replace_reaction": "J5",
     "with": "J5: CTD_5 + ATP -> CTD_6 + ADP; 0;"
    },
    {
     "replace_reaction": "J6",
     "with": "J6: CTD_6 + ATP -> CTD_7 + ADP; 0;"
    },
    {
     "replace_reaction": "J7",
     "with": "J7: CTD_7 + ATP -> CTD_8 + ADP; 0;"
    },
    {
     "append": [
      "// Positional refinement by gap class: Gf8 = unmodified; G<a><b>_<g...> = unmarked end stretches a <= b and unmarked interior stretches g... between marks; n = 8 - a - b - sum(g)",
      "// Each G reaction from a class with n marks also carries CTD_n + ATP -> CTD_n+1 + ADP, so the G classes with n marks sum to CTD_n identically and ATP is consumed once per modification; J0-J7 are kept at zero rate",
      "species Gf8 in vial, G07 in vial, G16 in vial, G25 in vial, G34 in vial;",
      "species G06 in vial, G15 in vial, G24 in vial, G33 in vial, G05_1 in vial, G14_1 in vial, G23_1 in vial, G04_2 in vial;",
      "species G13_2 in vial, G22_2 in vial, G03_3 in vial, G12_3 in vial, G02_4 in vial, G11_4 in vial, G01_5 in vial, G00_6 in vial;",
      "species G05 in vial, G14 in vial, G23 in vial, G04_1 in vial, G13_1 in vial, G22_1 in vial, G03_2 in vial, G12_2 in vial, G02_3 in vial, G11_3 in vial;",
      "species G01_4 in vial, G00_5 in vial, G03_11 in vial, G12_11 in vial, G02_21 in vial, G11_21 in vial, G01_31 in vial, G01_22 in vial, G00_41 in vial, G00_32 in vial;",
      "species G04 in vial, G13 in vial, G22 in vial, G03_1 in vial, G12_1 in vial, G02_2 in vial, G11_2 in vial, G01_3 in vial;",
      "species G00_4 in vial, G02_11 in vial, G11_11 in vial, G01_21 in vial, G00_31 in vial, G00_22 in vial, G01_111 in vial, G00_211 in vial;",
      "species G03 in vial, G12 in vial, G02_1 in vial, G11_1 in vial, G01_2 in vial, G00_3 in vial, G01_11 in vial, G00_21 in vial, G00_111 in vial;",
      "species G02 in vial, G11 in vial, G01_1 in vial, G00_2 in vial, G00_11 in vial, G01 in vial, G00_1 in vial, G00 in vial;",
      "Gf8 = 100; G07 = 0; G16 = 0; G25 = 0; G34 = 0;",
      "G06 = 0; G15 = 0; G24 = 0; G33 = 0; G05_1 = 0; G14_1 = 0; G23_1 = 0; G04_2 = 0;",
      "G13_2 = 0; G22_2 = 0; G03_3 = 0; G12_3 = 0; G02_4 = 0; G11_4 = 0; G01_5 = 0; G00_6 = 0;",
      "G05 = 0; G14 = 0; G23 = 0; G04_1 = 0; G13_1 = 0; G22_1 = 0; G03_2 = 0; G12_2 = 0; G02_3 = 0; G11_3 = 0;",
      "G01_4 = 0; G00_5 = 0; G03_11 = 0; G12_11 = 0; G02_21 = 0; G11_21 = 0; G01_31 = 0; G01_22 = 0; G00_41 = 0; G00_32 = 0;",
      "G04 = 0; G13 = 0; G22 = 0; G03_1 = 0; G12_1 = 0; G02_2 = 0; G11_2 = 0; G01_3 = 0;",
      "G00_4 = 0; G02_11 = 0; G11_11 = 0; G01_21 = 0; G00_31 = 0; G00_22 = 0; G01_111 = 0; G00_211 = 0;",
      "G03 = 0; G12 = 0; G02_1 = 0; G11_1 = 0; G01_2 = 0; G00_3 = 0; G01_11 = 0; G00_21 = 0; G00_111 = 0;",
      "G02 = 0; G11 = 0; G01_1 = 0; G00_2 = 0; G00_11 = 0; G01 = 0; G00_1 = 0; G00 = 0;",
      "nb = 1;",
      "// rate per unmodified repeat: kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, m = marked immediate neighbours; coefficients count the repeats leading to each class",
      "Q_Gf8_G07: Gf8 + CTD_0 + ATP -> G07 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_Gf8_G16: Gf8 + CTD_0 + ATP -> G16 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_Gf8_G25: Gf8 + CTD_0 + ATP -> G25 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_Gf8_G34: Gf8 + CTD_0 + ATP -> G34 + CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*Gf8;",
      "Q_G07_G06: G07 + CTD_1 + ATP -> G06 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G07;",
      "Q_G07_G05_1: G07 + CTD_1 + ATP -> G05_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G04_2: G07 + CTD_1 + ATP -> G04_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G03_3: G07 + CTD_1 + ATP -> G03_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G02_4: G07 + CTD_1 + ATP -> G02_4 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G01_5: G07 + CTD_1 + ATP -> G01_5 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G07_G00_6: G07 + CTD_1 + ATP -> G00_6 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G07;",
      "Q_G16_G06: G16 + CTD_1 + ATP -> G06 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
      "Q_G16_G15: G16 + CTD_1 + ATP -> G15 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G16;",
      "Q_G16_G14_1: G16 + CTD_1 + ATP -> G14_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G13_2: G16 + CTD_1 + ATP -> G13_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G12_3: G16 + CTD_1 + ATP -> G12_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G11_4: G16 + CTD_1 + ATP -> G11_4 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G16_G01_5: G16 + CTD_1 + ATP -> G01_5 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G16;",
      "Q_G25_G15: G25 + CTD_1 + ATP -> G15 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
      "Q_G25_G24: G25 + CTD_1 + ATP -> G24 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G25;",
      "Q_G25_G05_1: G25 + CTD_1 + ATP -> G05_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G23_1: G25 + CTD_1 + ATP -> G23_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G22_2: G25 + CTD_1 + ATP -> G22_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G12_3: G25 + CTD_1 + ATP -> G12_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G25_G02_4: G25 + CTD_1 + ATP -> G02_4 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G25;",
      "Q_G34_G24: G34 + CTD_1 + ATP -> G24 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
      "Q_G34_G33: G34 + CTD_1 + ATP -> G33 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*nb*G34;",
      "Q_G34_G23_1: G34 + CTD_1 + ATP -> G23_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G14_1: G34 + CTD_1 + ATP -> G14_1 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G13_2: G34 + CTD_1 + ATP -> G13_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G04_2: G34 + CTD_1 + ATP -> G04_2 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G34_G03_3: G34 + CTD_1 + ATP -> G03_3 + CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp*G34;",
      "Q_G06_G05: G06 + CTD_2 + ATP -> G05 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G06;",
      "Q_G06_G04_1: G06 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G03_2: G06 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G02_3: G06 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G01_4: G06 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G06_G00_5: G06 + CTD_2 + ATP -> G00_5 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G06;",
      "Q_G15_G05: G15 + CTD_2 + ATP -> G05 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
      "Q_G15_G14: G15 + CTD_2 + ATP -> G14 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G15;",
      "Q_G15_G13_1: G15 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G15_G12_2: G15 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G15_G11_3: G15 + CTD_2 + ATP -> G11_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G15_G01_4: G15 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G15;",
      "Q_G24_G14: G24 + CTD_2 + ATP -> G14 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
      "Q_G24_G23: G24 + CTD_2 + ATP -> G23 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G24;",
      "Q_G24_G04_1: G24 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G24_G22_1: G24 + CTD_2 + ATP -> G22_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G24_G12_2: G24 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G24_G02_3: G24 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G24;",
      "Q_G33_G23: G33 + CTD_2 + ATP -> G23 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G33;",
      "Q_G33_G13_1: G33 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
      "Q_G33_G03_2: G33 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G33;",
      "Q_G05_1_G05: G05_1 + CTD_2 + ATP -> G05 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G05_1;",
      "Q_G05_1_G04_1: G05_1 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G05_1;",
      "Q_G05_1_G03_11: G05_1 + CTD_2 + ATP -> G03_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G05_1_G02_21: G05_1 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G05_1_G01_31: G05_1 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G05_1_G00_41: G05_1 + CTD_2 + ATP -> G00_41 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G05_1;",
      "Q_G14_1_G14: G14_1 + CTD_2 + ATP -> G14 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G14_1;",
      "Q_G14_1_G04_1: G14_1 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
      "Q_G14_1_G13_1: G14_1 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G14_1;",
      "Q_G14_1_G12_11: G14_1 + CTD_2 + ATP -> G12_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
      "Q_G14_1_G11_21: G14_1 + CTD_2 + ATP -> G11_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
      "Q_G14_1_G01_31: G14_1 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G14_1;",
      "Q_G23_1_G23: G23_1 + CTD_2 + ATP -> G23 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb^2*G23_1;",
      "Q_G23_1_G13_1: G23_1 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
      "Q_G23_1_G22_1: G23_1 + CTD_2 + ATP -> G22_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G23_1;",
      "Q_G23_1_G12_11: G23_1 + CTD_2 + ATP -> G12_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
      "Q_G23_1_G03_11: G23_1 + CTD_2 + ATP -> G03_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
      "Q_G23_1_G02_21: G23_1 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G23_1;",
      "Q_G04_2_G04_1: G04_2 + CTD_2 + ATP -> G04_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G04_2;",
      "Q_G04_2_G03_2: G04_2 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G04_2;",
      "Q_G04_2_G02_21: G04_2 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
      "Q_G04_2_G01_22: G04_2 + CTD_2 + ATP -> G01_22 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
      "Q_G04_2_G00_32: G04_2 + CTD_2 + ATP -> G00_32 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G04_2;",
      "Q_G13_2_G13_1: G13_2 + CTD_2 + ATP -> G13_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G13_2;",
      "Q_G13_2_G03_2: G13_2 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
      "Q_G13_2_G12_2: G13_2 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G13_2;",
      "Q_G13_2_G11_21: G13_2 + CTD_2 + ATP -> G11_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
      "Q_G13_2_G01_22: G13_2 + CTD_2 + ATP -> G01_22 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G13_2;",
      "Q_G22_2_G22_1: G22_2 + CTD_2 + ATP -> G22_1 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
      "Q_G22_2_G12_2: G22_2 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G22_2;",
      "Q_G22_2_G02_21: G22_2 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G22_2;",
      "Q_G03_3_G03_2: G03_3 + CTD_2 + ATP -> G03_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G03_3;",
      "Q_G03_3_G02_3: G03_3 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G03_3;",
      "Q_G03_3_G03_11: G03_3 + CTD_2 + ATP -> G03_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
      "Q_G03_3_G01_31: G03_3 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
      "Q_G03_3_G00_32: G03_3 + CTD_2 + ATP -> G00_32 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G03_3;",
      "Q_G12_3_G12_2: G12_3 + CTD_2 + ATP -> G12_2 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G12_3;",
      "Q_G12_3_G02_3: G12_3 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
      "Q_G12_3_G11_3: G12_3 + CTD_2 + ATP -> G11_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G12_3;",
      "Q_G12_3_G12_11: G12_3 + CTD_2 + ATP -> G12_11 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
      "Q_G12_3_G01_31: G12_3 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G12_3;",
      "Q_G02_4_G02_3: G02_4 + CTD_2 + ATP -> G02_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G02_4;",
      "Q_G02_4_G01_4: G02_4 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G02_4;",
      "Q_G02_4_G02_21: G02_4 + CTD_2 + ATP -> G02_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G02_4;",
      "Q_G02_4_G00_41: G02_4 + CTD_2 + ATP -> G00_41 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G02_4;",
      "Q_G11_4_G11_3: G11_4 + CTD_2 + ATP -> G11_3 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
      "Q_G11_4_G01_4: G11_4 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G11_4;",
      "Q_G11_4_G11_21: G11_4 + CTD_2 + ATP -> G11_21 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G11_4;",
      "Q_G01_5_G01_4: G01_5 + CTD_2 + ATP -> G01_4 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G01_5;",
      "Q_G01_5_G00_5: G01_5 + CTD_2 + ATP -> G00_5 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*nb*G01_5;",
      "Q_G01_5_G01_31: G01_5 + CTD_2 + ATP -> G01_31 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G01_5;",
      "Q_G01_5_G01_22: G01_5 + CTD_2 + ATP -> G01_22 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*G01_5;",
      "Q_G00_6_G00_5: G00_6 + CTD_2 + ATP -> G00_5 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*nb*G00_6;",
      "Q_G00_6_G00_41: G00_6 + CTD_2 + ATP -> G00_41 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
      "Q_G00_6_G00_32: G00_6 + CTD_2 + ATP -> G00_32 + CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^2*2*G00_6;",
      "Q_G05_G04: G05 + CTD_3 + ATP -> G04 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G05;",
      "Q_G05_G03_1: G05 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G05_G02_2: G05 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G05_G01_3: G05 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G05_G00_4: G05 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G05;",
      "Q_G14_G04: G14 + CTD_3 + ATP -> G04 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
      "Q_G14_G13: G14 + CTD_3 + ATP -> G13 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G14;",
      "Q_G14_G12_1: G14 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
      "Q_G14_G11_2: G14 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
      "Q_G14_G01_3: G14 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G14;",
      "Q_G23_G13: G23 + CTD_3 + ATP -> G13 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
      "Q_G23_G22: G23 + CTD_3 + ATP -> G22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G23;",
      "Q_G23_G12_1: G23 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
      "Q_G23_G03_1: G23 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
      "Q_G23_G02_2: G23 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G23;",
      "Q_G04_1_G04: G04_1 + CTD_3 + ATP -> G04 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G04_1;",
      "Q_G04_1_G03_1: G04_1 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G04_1;",
      "Q_G04_1_G02_11: G04_1 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
      "Q_G04_1_G01_21: G04_1 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
      "Q_G04_1_G00_31: G04_1 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G04_1;",
      "Q_G13_1_G13: G13_1 + CTD_3 + ATP -> G13 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G13_1;",
      "Q_G13_1_G03_1: G13_1 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
      "Q_G13_1_G12_1: G13_1 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G13_1;",
      "Q_G13_1_G11_11: G13_1 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
      "Q_G13_1_G01_21: G13_1 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G13_1;",
      "Q_G22_1_G22: G22_1 + CTD_3 + ATP -> G22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G22_1;",
      "Q_G22_1_G12_1: G22_1 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G22_1;",
      "Q_G22_1_G02_11: G22_1 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G22_1;",
      "Q_G03_2_G03_1: G03_2 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G03_2;",
      "Q_G03_2_G02_2: G03_2 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_2;",
      "Q_G03_2_G01_21: G03_2 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
      "Q_G03_2_G00_22: G03_2 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_2;",
      "Q_G12_2_G12_1: G12_2 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G12_2;",
      "Q_G12_2_G02_2: G12_2 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
      "Q_G12_2_G11_2: G12_2 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_2;",
      "Q_G12_2_G01_21: G12_2 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_2;",
      "Q_G02_3_G02_2: G02_3 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_3;",
      "Q_G02_3_G01_3: G02_3 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_3;",
      "Q_G02_3_G02_11: G02_3 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
      "Q_G02_3_G00_31: G02_3 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_3;",
      "Q_G11_3_G11_2: G11_3 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
      "Q_G11_3_G01_3: G11_3 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_3;",
      "Q_G11_3_G11_11: G11_3 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G11_3;",
      "Q_G01_4_G01_3: G01_4 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_4;",
      "Q_G01_4_G00_4: G01_4 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_4;",
      "Q_G01_4_G01_21: G01_4 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G01_4;",
      "Q_G00_5_G00_4: G00_5 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_5;",
      "Q_G00_5_G00_31: G00_5 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_5;",
      "Q_G00_5_G00_22: G00_5 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_5;",
      "Q_G03_11_G03_1: G03_11 + CTD_3 + ATP -> G03_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G03_11;",
      "Q_G03_11_G02_11: G03_11 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G03_11;",
      "Q_G03_11_G01_111: G03_11 + CTD_3 + ATP -> G01_111 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
      "Q_G03_11_G00_211: G03_11 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G03_11;",
      "Q_G12_11_G12_1: G12_11 + CTD_3 + ATP -> G12_1 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb^2*G12_11;",
      "Q_G12_11_G02_11: G12_11 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
      "Q_G12_11_G11_11: G12_11 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G12_11;",
      "Q_G12_11_G01_111: G12_11 + CTD_3 + ATP -> G01_111 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G12_11;",
      "Q_G02_21_G02_2: G02_21 + CTD_3 + ATP -> G02_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G02_21;",
      "Q_G02_21_G02_11: G02_21 + CTD_3 + ATP -> G02_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G02_21;",
      "Q_G02_21_G01_21: G02_21 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G02_21;",
      "Q_G02_21_G00_211: G02_21 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G02_21;",
      "Q_G11_21_G11_2: G11_21 + CTD_3 + ATP -> G11_2 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G11_21;",
      "Q_G11_21_G11_11: G11_21 + CTD_3 + ATP -> G11_11 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
      "Q_G11_21_G01_21: G11_21 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G11_21;",
      "Q_G01_31_G01_3: G01_31 + CTD_3 + ATP -> G01_3 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G01_31;",
      "Q_G01_31_G01_21: G01_31 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G01_31;",
      "Q_G01_31_G00_31: G01_31 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_31;",
      "Q_G01_31_G01_111: G01_31 + CTD_3 + ATP -> G01_111 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G01_31;",
      "Q_G01_22_G01_21: G01_22 + CTD_3 + ATP -> G01_21 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*4*nb*G01_22;",
      "Q_G01_22_G00_22: G01_22 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb*G01_22;",
      "Q_G00_41_G00_4: G00_41 + CTD_3 + ATP -> G00_4 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*nb^2*G00_41;",
      "Q_G00_41_G00_31: G00_41 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_41;",
      "Q_G00_41_G00_211: G00_41 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*G00_41;",
      "Q_G00_32_G00_31: G00_32 + CTD_3 + ATP -> G00_31 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
      "Q_G00_32_G00_22: G00_32 + CTD_3 + ATP -> G00_22 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*2*nb*G00_32;",
      "Q_G00_32_G00_211: G00_32 + CTD_3 + ATP -> G00_211 + CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^3*G00_32;",
      "Q_G04_G03: G04 + CTD_4 + ATP -> G03 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G04;",
      "Q_G04_G02_1: G04 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
      "Q_G04_G01_2: G04 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
      "Q_G04_G00_3: G04 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G04;",
      "Q_G13_G03: G13 + CTD_4 + ATP -> G03 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
      "Q_G13_G12: G13 + CTD_4 + ATP -> G12 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G13;",
      "Q_G13_G11_1: G13 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
      "Q_G13_G01_2: G13 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G13;",
      "Q_G22_G12: G22 + CTD_4 + ATP -> G12 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G22;",
      "Q_G22_G02_1: G22 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G22;",
      "Q_G03_1_G03: G03_1 + CTD_4 + ATP -> G03 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G03_1;",
      "Q_G03_1_G02_1: G03_1 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G03_1;",
      "Q_G03_1_G01_11: G03_1 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
      "Q_G03_1_G00_21: G03_1 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G03_1;",
      "Q_G12_1_G12: G12_1 + CTD_4 + ATP -> G12 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G12_1;",
      "Q_G12_1_G02_1: G12_1 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
      "Q_G12_1_G11_1: G12_1 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G12_1;",
      "Q_G12_1_G01_11: G12_1 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G12_1;",
      "Q_G02_2_G02_1: G02_2 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G02_2;",
      "Q_G02_2_G01_2: G02_2 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_2;",
      "Q_G02_2_G00_21: G02_2 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_2;",
      "Q_G11_2_G11_1: G11_2 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
      "Q_G11_2_G01_2: G11_2 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_2;",
      "Q_G01_3_G01_2: G01_3 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_3;",
      "Q_G01_3_G00_3: G01_3 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_3;",
      "Q_G01_3_G01_11: G01_3 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G01_3;",
      "Q_G00_4_G00_3: G00_4 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_4;",
      "Q_G00_4_G00_21: G00_4 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*G00_4;",
      "Q_G02_11_G02_1: G02_11 + CTD_4 + ATP -> G02_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G02_11;",
      "Q_G02_11_G01_11: G02_11 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G02_11;",
      "Q_G02_11_G00_111: G02_11 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G02_11;",
      "Q_G11_11_G11_1: G11_11 + CTD_4 + ATP -> G11_1 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G11_11;",
      "Q_G11_11_G01_11: G11_11 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G11_11;",
      "Q_G01_21_G01_2: G01_21 + CTD_4 + ATP -> G01_2 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G01_21;",
      "Q_G01_21_G01_11: G01_21 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G01_21;",
      "Q_G01_21_G00_21: G01_21 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_21;",
      "Q_G00_31_G00_3: G00_31 + CTD_4 + ATP -> G00_3 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb^2*G00_31;",
      "Q_G00_31_G00_21: G00_31 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_31;",
      "Q_G00_31_G00_111: G00_31 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*G00_31;",
      "Q_G00_22_G00_21: G00_22 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*4*nb*G00_22;",
      "Q_G01_111_G01_11: G01_111 + CTD_4 + ATP -> G01_11 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*3*nb^2*G01_111;",
      "Q_G01_111_G00_111: G01_111 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*nb*G01_111;",
      "Q_G00_211_G00_21: G00_211 + CTD_4 + ATP -> G00_21 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb^2*G00_211;",
      "Q_G00_211_G00_111: G00_211 + CTD_4 + ATP -> G00_111 + CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^4*2*nb*G00_211;",
      "Q_G03_G02: G03 + CTD_5 + ATP -> G02 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G03;",
      "Q_G03_G01_1: G03 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
      "Q_G03_G00_2: G03 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G03;",
      "Q_G12_G02: G12 + CTD_5 + ATP -> G02 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
      "Q_G12_G11: G12 + CTD_5 + ATP -> G11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G12;",
      "Q_G12_G01_1: G12 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G12;",
      "Q_G02_1_G02: G02_1 + CTD_5 + ATP -> G02 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G02_1;",
      "Q_G02_1_G01_1: G02_1 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G02_1;",
      "Q_G02_1_G00_11: G02_1 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G02_1;",
      "Q_G11_1_G11: G11_1 + CTD_5 + ATP -> G11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G11_1;",
      "Q_G11_1_G01_1: G11_1 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G11_1;",
      "Q_G01_2_G01_1: G01_2 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G01_2;",
      "Q_G01_2_G00_2: G01_2 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_2;",
      "Q_G00_3_G00_2: G00_3 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_3;",
      "Q_G00_3_G00_11: G00_3 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*G00_3;",
      "Q_G01_11_G01_1: G01_11 + CTD_5 + ATP -> G01_1 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb^2*G01_11;",
      "Q_G01_11_G00_11: G01_11 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb*G01_11;",
      "Q_G00_21_G00_2: G00_21 + CTD_5 + ATP -> G00_2 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*nb^2*G00_21;",
      "Q_G00_21_G00_11: G00_21 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*2*nb*G00_21;",
      "Q_G00_111_G00_11: G00_111 + CTD_5 + ATP -> G00_11 + CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^5*3*nb^2*G00_111;",
      "Q_G02_G01: G02 + CTD_6 + ATP -> G01 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G02;",
      "Q_G02_G00_1: G02 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*G02;",
      "Q_G11_G01: G11 + CTD_6 + ATP -> G01 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G11;",
      "Q_G01_1_G01: G01_1 + CTD_6 + ATP -> G01 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb^2*G01_1;",
      "Q_G01_1_G00_1: G01_1 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*nb*G01_1;",
      "Q_G00_2_G00_1: G00_2 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb*G00_2;",
      "Q_G00_11_G00_1: G00_11 + CTD_6 + ATP -> G00_1 + CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^6*2*nb^2*G00_11;",
      "Q_G01_G00: G01 + CTD_7 + ATP -> G00 + CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb*G01;",
      "Q_G00_1_G00: G00_1 + CTD_7 + ATP -> G00 + CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*nb^2*G00_1;"
     ]
    }
   ],
   "adds_parameters": [
    {
     "id": "nb",
     "nominal_value": 1.0,
     "unit": "dimensionless (fold change of an unmodified repeat's rate per phosphorylated immediate neighbour)",
     "lb": 0.01,
     "ub": 100.0,
     "evidence_tier": "to_be_estimated",
     "source": "base_model construction decision (positional candidate rule): neutral value 1, bounds 0.01 to 100; log10 scale",
     "estimate": true
    }
   ],
   "entity_glossary": {
    "species": [
     {
      "id": "Gf8",
      "denotes": "CTD with 0 marks: one stretch of 8 unmarked repeats (equals CTD_0)",
      "unit_convention": "uM; 100 at t = 0; positional refinement of CTD, not extra substrate",
      "lump_membership": "the single unmarked configuration"
     },
     {
      "id": "G07",
      "denotes": "1 mark, on repeat 1 or 8 (end gaps 0,7); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {0,7}, no interior gap"
     },
     {
      "id": "G16",
      "denotes": "1 mark, on repeat 2 or 7 (end gaps 1,6); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {1,6}, no interior gap"
     },
     {
      "id": "G25",
      "denotes": "1 mark, on repeat 3 or 6 (end gaps 2,5); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {2,5}, no interior gap"
     },
     {
      "id": "G34",
      "denotes": "1 mark, on repeat 4 or 5 (end gaps 3,4); refines CTD_1",
      "unit_convention": "uM; sums with its class-mates to CTD_1",
      "lump_membership": "end gaps {3,4}, no interior gap"
     },
     {
      "id": "G06",
      "denotes": "2 marks; end gaps 0,6; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,6}; interior {}"
     },
     {
      "id": "G15",
      "denotes": "2 marks; end gaps 1,5; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,5}; interior {}"
     },
     {
      "id": "G24",
      "denotes": "2 marks; end gaps 2,4; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {2,4}; interior {}"
     },
     {
      "id": "G33",
      "denotes": "2 marks; end gaps 3,3; no interior gap; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {3,3}; interior {}"
     },
     {
      "id": "G05_1",
      "denotes": "2 marks; end gaps 0,5; interior gap 1; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,5}; interior {1}"
     },
     {
      "id": "G14_1",
      "denotes": "2 marks; end gaps 1,4; interior gap 1; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,4}; interior {1}"
     },
     {
      "id": "G23_1",
      "denotes": "2 marks; end gaps 2,3; interior gap 1; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {2,3}; interior {1}"
     },
     {
      "id": "G04_2",
      "denotes": "2 marks; end gaps 0,4; interior gap 2; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,4}; interior {2}"
     },
     {
      "id": "G13_2",
      "denotes": "2 marks; end gaps 1,3; interior gap 2; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,3}; interior {2}"
     },
     {
      "id": "G22_2",
      "denotes": "2 marks; end gaps 2,2; interior gap 2; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {2,2}; interior {2}"
     },
     {
      "id": "G03_3",
      "denotes": "2 marks; end gaps 0,3; interior gap 3; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,3}; interior {3}"
     },
     {
      "id": "G12_3",
      "denotes": "2 marks; end gaps 1,2; interior gap 3; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,2}; interior {3}"
     },
     {
      "id": "G02_4",
      "denotes": "2 marks; end gaps 0,2; interior gap 4; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,2}; interior {4}"
     },
     {
      "id": "G11_4",
      "denotes": "2 marks; end gaps 1,1; interior gap 4; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {1,1}; interior {4}"
     },
     {
      "id": "G01_5",
      "denotes": "2 marks; end gaps 0,1; interior gap 5; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,1}; interior {5}"
     },
     {
      "id": "G00_6",
      "denotes": "2 marks, on repeats 1 and 8; interior gap 6; refines CTD_2",
      "unit_convention": "uM; sums with its class-mates to CTD_2",
      "lump_membership": "end gaps {0,0}; interior {6}"
     },
     {
      "id": "G05",
      "denotes": "3 marks; end gaps 0,5; no interior gap; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,5}; interior {}"
     },
     {
      "id": "G14",
      "denotes": "3 marks; end gaps 1,4; no interior gap; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,4}; interior {}"
     },
     {
      "id": "G23",
      "denotes": "3 marks; end gaps 2,3; no interior gap; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {2,3}; interior {}"
     },
     {
      "id": "G04_1",
      "denotes": "3 marks; end gaps 0,4; interior gap 1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,4}; interior {1}"
     },
     {
      "id": "G13_1",
      "denotes": "3 marks; end gaps 1,3; interior gap 1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,3}; interior {1}"
     },
     {
      "id": "G22_1",
      "denotes": "3 marks; end gaps 2,2; interior gap 1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {2,2}; interior {1}"
     },
     {
      "id": "G03_2",
      "denotes": "3 marks; end gaps 0,3; interior gap 2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,3}; interior {2}"
     },
     {
      "id": "G12_2",
      "denotes": "3 marks; end gaps 1,2; interior gap 2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,2}; interior {2}"
     },
     {
      "id": "G02_3",
      "denotes": "3 marks; end gaps 0,2; interior gap 3; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,2}; interior {3}"
     },
     {
      "id": "G11_3",
      "denotes": "3 marks; end gaps 1,1; interior gap 3; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,1}; interior {3}"
     },
     {
      "id": "G01_4",
      "denotes": "3 marks; end gaps 0,1; interior gap 4; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,1}; interior {4}"
     },
     {
      "id": "G00_5",
      "denotes": "3 marks; end gaps 0,0; interior gap 5; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,0}; interior {5}"
     },
     {
      "id": "G03_11",
      "denotes": "3 marks; end gaps 0,3; interior gaps 1,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,3}; interior {1,1}"
     },
     {
      "id": "G12_11",
      "denotes": "3 marks; end gaps 1,2; interior gaps 1,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,2}; interior {1,1}"
     },
     {
      "id": "G02_21",
      "denotes": "3 marks; end gaps 0,2; interior gaps 2,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,2}; interior {2,1}"
     },
     {
      "id": "G11_21",
      "denotes": "3 marks; end gaps 1,1; interior gaps 2,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {1,1}; interior {2,1}"
     },
     {
      "id": "G01_31",
      "denotes": "3 marks; end gaps 0,1; interior gaps 3,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,1}; interior {3,1}"
     },
     {
      "id": "G01_22",
      "denotes": "3 marks; end gaps 0,1; interior gaps 2,2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,1}; interior {2,2}"
     },
     {
      "id": "G00_41",
      "denotes": "3 marks; end gaps 0,0; interior gaps 4,1; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,0}; interior {4,1}"
     },
     {
      "id": "G00_32",
      "denotes": "3 marks; end gaps 0,0; interior gaps 3,2; refines CTD_3",
      "unit_convention": "uM; sums with its class-mates to CTD_3",
      "lump_membership": "end gaps {0,0}; interior {3,2}"
     },
     {
      "id": "G04",
      "denotes": "4 marks; end gaps 0,4; no interior gap; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,4}; interior {}"
     },
     {
      "id": "G13",
      "denotes": "4 marks; end gaps 1,3; no interior gap; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,3}; interior {}"
     },
     {
      "id": "G22",
      "denotes": "4 marks; end gaps 2,2; no interior gap; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {2,2}; interior {}"
     },
     {
      "id": "G03_1",
      "denotes": "4 marks; end gaps 0,3; interior gap 1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,3}; interior {1}"
     },
     {
      "id": "G12_1",
      "denotes": "4 marks; end gaps 1,2; interior gap 1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,2}; interior {1}"
     },
     {
      "id": "G02_2",
      "denotes": "4 marks; end gaps 0,2; interior gap 2; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,2}; interior {2}"
     },
     {
      "id": "G11_2",
      "denotes": "4 marks; end gaps 1,1; interior gap 2; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,1}; interior {2}"
     },
     {
      "id": "G01_3",
      "denotes": "4 marks; end gaps 0,1; interior gap 3; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,1}; interior {3}"
     },
     {
      "id": "G00_4",
      "denotes": "4 marks; end gaps 0,0; interior gap 4; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {4}"
     },
     {
      "id": "G02_11",
      "denotes": "4 marks; end gaps 0,2; interior gaps 1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,2}; interior {1,1}"
     },
     {
      "id": "G11_11",
      "denotes": "4 marks; end gaps 1,1; interior gaps 1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {1,1}; interior {1,1}"
     },
     {
      "id": "G01_21",
      "denotes": "4 marks; end gaps 0,1; interior gaps 2,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,1}; interior {2,1}"
     },
     {
      "id": "G00_31",
      "denotes": "4 marks; end gaps 0,0; interior gaps 3,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {3,1}"
     },
     {
      "id": "G00_22",
      "denotes": "4 marks; end gaps 0,0; interior gaps 2,2; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {2,2}"
     },
     {
      "id": "G01_111",
      "denotes": "4 marks on alternate repeats (1,3,5,7 or 2,4,6,8): end gaps 0,1, interior gaps 1,1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,1}; interior {1,1,1}"
     },
     {
      "id": "G00_211",
      "denotes": "4 marks; end gaps 0,0; interior gaps 2,1,1; refines CTD_4",
      "unit_convention": "uM; sums with its class-mates to CTD_4",
      "lump_membership": "end gaps {0,0}; interior {2,1,1}"
     },
     {
      "id": "G03",
      "denotes": "5 marks; end gaps 0,3; no interior gap; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,3}; interior {}"
     },
     {
      "id": "G12",
      "denotes": "5 marks; end gaps 1,2; no interior gap; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {1,2}; interior {}"
     },
     {
      "id": "G02_1",
      "denotes": "5 marks; end gaps 0,2; interior gap 1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,2}; interior {1}"
     },
     {
      "id": "G11_1",
      "denotes": "5 marks; end gaps 1,1; interior gap 1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {1,1}; interior {1}"
     },
     {
      "id": "G01_2",
      "denotes": "5 marks; end gaps 0,1; interior gap 2; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,1}; interior {2}"
     },
     {
      "id": "G00_3",
      "denotes": "5 marks; end gaps 0,0; interior gap 3; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,0}; interior {3}"
     },
     {
      "id": "G01_11",
      "denotes": "5 marks; end gaps 0,1; interior gaps 1,1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,1}; interior {1,1}"
     },
     {
      "id": "G00_21",
      "denotes": "5 marks; end gaps 0,0; interior gaps 2,1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,0}; interior {2,1}"
     },
     {
      "id": "G00_111",
      "denotes": "5 marks; end gaps 0,0; interior gaps 1,1,1; refines CTD_5",
      "unit_convention": "uM; sums with its class-mates to CTD_5",
      "lump_membership": "end gaps {0,0}; interior {1,1,1}"
     },
     {
      "id": "G02",
      "denotes": "6 marks; end gaps 0,2; no interior gap; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,2}; interior {}"
     },
     {
      "id": "G11",
      "denotes": "6 marks, on repeats 2 to 7 (end gaps 1,1); refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {1,1}; interior {}"
     },
     {
      "id": "G01_1",
      "denotes": "6 marks; end gaps 0,1; interior gap 1; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,1}; interior {1}"
     },
     {
      "id": "G00_2",
      "denotes": "6 marks; end gaps 0,0; interior gap 2; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,0}; interior {2}"
     },
     {
      "id": "G00_11",
      "denotes": "6 marks; end gaps 0,0; interior gaps 1,1; refines CTD_6",
      "unit_convention": "uM; sums with its class-mates to CTD_6",
      "lump_membership": "end gaps {0,0}; interior {1,1}"
     },
     {
      "id": "G01",
      "denotes": "7 marks, the unmarked repeat at an end (repeat 1 or 8); refines CTD_7",
      "unit_convention": "uM; sums with G00_1 to CTD_7",
      "lump_membership": "end gaps {0,1}; interior {}"
     },
     {
      "id": "G00_1",
      "denotes": "7 marks, the unmarked repeat interior (repeats 2 to 7); refines CTD_7",
      "unit_convention": "uM; sums with G01 to CTD_7",
      "lump_membership": "end gaps {0,0}; interior {1}"
     },
     {
      "id": "G00",
      "denotes": "all 8 repeats marked (equals CTD_8)",
      "unit_convention": "uM",
      "lump_membership": "the single fully marked configuration"
     }
    ],
    "parameters": [
     {
      "id": "nb",
      "role": "nearest-neighbour switch: fold change of an unmodified repeat's rate per phosphorylated immediate neighbour (m = 0, 1 or 2; repeats 1 and 8 have one neighbour)",
      "convention": "neutral value 1 (no neighbour effect); < 1 inhibition, > 1 facilitation; log10 scale, bounds 0.01 to 100",
      "set_per_condition": false
     }
    ]
   }
  }
 ],
 "missing": [],
 "build_report": {
  "decisions": [
   {
    "decision": "Five candidates. M1 is the base: independent repeats, strictly distributive. M2 switches on count cooperativity (cp estimated). M3 adds the nearest-neighbour effect (positional patch, nb estimated). M4 switches on processivity (q_proc estimated). M5 combines the neighbour effect with count cooperativity (nb and cp estimated) and says so.",
    "rationale": "The intent asks for a three-way test (neighbour effect, count cooperativity, nothing at all) and a check of the distributive-versus-processive conclusion. M1 is the 'nothing at all' and distributive reference that every 'required' verdict is measured against. M2, M3 and M4 each switch on exactly one feature. M5 is the model that contains M2 and M3 as nested cases, so the comparisons 'neighbour effect beyond count cooperativity' and the converse are direct, and the joint nb-cp profile is where the separability question is answered. Every switch acts on its own: cp, nb and q_proc each change the dynamics with the others at their neutral values. No candidate differs from another only in an inert switch.",
    "alternatives_considered": "A processive-plus-cooperative combination (q_proc with cp), processivity on the positional model, and a free rate per count level (7 parameters, not identifiable from 9 peaks at 3 informative time points). The first two were left out to stay within five candidates, keeping the combination the question names directly (neighbour against count).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "What is already believed, and what is not settled",
      "supports": "the three named rate hypotheses and the distributive conclusion to be tested",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "base_model decisions (count cooperativity, processivity switches)",
      "supports": "cp and q_proc are the base's switches with neutral values 1 and 0",
      "origin": "inferred"
     }
    ],
    "evidence_tier": "direct",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "The neighbour effect, which the base cannot express, is added as a patch in M3 and M5. The patch implements construction's positional rule exactly: rate per unmodified repeat = kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, with m the number of marked immediate neighbours. It is written out state by state and reaction by reaction on 74 gap-structure classes and 257 reactions. These are the exact lumping of the 256-configuration, 1024-reaction model.",
    "rationale": "An unmodified repeat's rate depends only on n and on whether its two neighbours are marked. That is fixed by its position inside the maximal stretch of unmarked repeats (gap) that contains it, and by the gap's type: interior (marks on both sides), end (chain terminus on one side), or the whole unmodified chain. Modifying a repeat changes only its own gap: it splits the gap into at most two gaps of determined types, or shrinks it by one. The multiset of gap lengths with their types is therefore a sufficient state. The lengths of marked runs, the order of interior gaps and the orientation of the chain do not enter any rate; the rule treats both termini alike. Configurations sharing a gap structure have identical exit rates to every target class, so the 256 configurations are strongly lumpable onto the 74 classes. The classes with n marks sum to the count distribution exactly, at every nb and cp. Built-in check: at nb = 1 every class with n marks has total exit coefficient 8 - n (for example G01_22: 5*nb), so M3 reproduces M1 and M5 reproduces M2 trajectory for trajectory. Writing the reduced network by hand carries far less risk of an enumeration error than 1024 hand-written lines.",
    "alternatives_considered": "The literal 256-species, 1024-reaction enumeration. The note prefers the positional model written out rather than avoided, and it is written out here. The enumeration would only split each class into configurations with identical trajectories, so it gives the same likelihood and the same verdicts; it is not a different model. A positional readout (which repeats are marked) would need it, and none exists.",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "What can be computed here",
      "supports": "positional model to be fitted rather than argued away; size is not a constraint",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "strong lumpability of Markov chains (Kemeny-Snell); exact lumping of linear ODE networks by symmetry of the rate rule",
      "supports": "class-level reactions reproduce the configuration-level count distribution exactly",
      "origin": "inferred"
     },
     {
      "source": "lab_note",
      "locator": "base_model decision: exact construction rule for the positional (neighbour) candidate",
      "supports": "rate cp^n*nb^m, nb neutral 1, bounds 0.01 to 100",
      "origin": "inferred"
     }
    ],
    "evidence_tier": "direct",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "In M3 and M5 the class reactions carry the count bookkeeping. Each G reaction from a class with n marks also converts CTD_n + ATP -> CTD_n+1 + ADP, at the same rate. J0 to J7 are kept, with their stoichiometry, at zero rate. The observation model is unchanged: phos<n>_rel maps onto CTD_n.",
    "rationale": "This keeps CTD_n as the readout species shared by all five candidates, and it keeps ATP consumed exactly once per modification. Every flux into or out of a class with n marks moves CTD_n by the same amount, and CTD_n(0) equals its class sum, so CTD_n equals the sum of its classes identically. That identity now holds by stoichiometry, not by matching summed coefficients, so an error in any one coefficient cannot break it. A linear multistep integrator preserves the linear invariant to solver precision. The class reactions are the base's distributive single-repeat steps resolved by position, so J0 to J7 at zero rate are superseded, not contradicted. The base's processive Jp* reactions likewise sit at exactly zero rate in M3 and M5, where q_proc stays 0 and processivity is not composed with the positional model. The class rate laws read only the class amount, so listing CTD_n as a reactant changes no rate. The deliberate simplification is a second conservation class (sum over G = 100 uM) alongside sum over CTD_n = 100 uM. Both are intended and neither carries a free parameter.",
    "alternatives_considered": "The previous structure, in which the J0 to J7 rates were rewritten as the summed class fluxes. It is mathematically equivalent, but the engine's symbol check refused it twice: a replacement line may not use species declared in another patch (attempts 1 and 2). Assignment rules CTD_n := sum of G_n were also rejected. They would require removing CTD_n from all 36 base reactions, which the patch grammar does not allow.",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "The experiment (one ATP per phosphorylation; substrate conserved)",
      "supports": "ATP stoichiometry and the conserved total",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "previous_attempt_errors: J0-J7 replacement lines in M3 and M5 use G symbols that neither the base nor adds_parameters declares",
      "supports": "the bookkeeping cannot sit in the J replacement lines",
      "origin": "inferred"
     },
     {
      "source": "general_knowledge",
      "locator": "measurement-tech pack entry 4; general-dynamics pack entry 4",
      "supports": "readout mapping and conserved totals kept intentional and declared",
      "origin": "inferred"
     }
    ],
    "evidence_tier": "direct",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "nb is estimated on log10 between 0.01 and 100, nominal 1 (neutral), as construction specified. cp in M2 and M5 keeps the base bounds 0.2 to 5. q_proc in M4 is estimated between 1e-4 and 0.99 with nominal 0.1, because 0 lies outside the estimation box and is invalid on a log scale.",
    "rationale": "nb enters as nb^2 on a repeat whose two neighbours are both marked, so its bounds span 8 decades on those steps. Together with cp^7, the fastest corner reaches rates about 1e4-fold above the per-repeat kmod. The engine should check integrability at the corners of the box, not only at the nominals (general-dynamics pack entry 8). The q_proc lower bound is strictly distributive to within 1e-4. If q_proc rests on that bound after fitting, that is a finding in favour of distributive action, not a bounds artefact (pack entry 6). Because M1 sits on the boundary of M4, a likelihood-ratio reading of M4 against M1 needs the boundary correction. The q_proc profile is the direct test.",
    "alternatives_considered": "nb bounds of 0.1 to 10. These would exclude the strong-inhibition regime (jamming at alternate repeats) that gives nb its most distinctive signature at 16 h.",
    "evidence": [
     {
      "source": "general_knowledge",
      "locator": "general-dynamics pack entries 1, 2, 6 and 8",
      "supports": "log scale, decade span, at-bound interpretation, corner integrability",
      "origin": "inferred"
     }
    ],
    "evidence_tier": "default",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "Expected indistinguishable set and unresolved questions, named for the evaluation. nb > 1, cp > 1 and q_proc > 0 all predict nucleation then fast completion, and are expected to be hard to separate from counts at 3 informative time points without replicates. nb < 1 has a distinctive signature: a stall at 3 to 4 non-adjacent marks between 2 h and 16 h. Positional order, sliding versus random-site processivity, kinase inactivation and substrate saturation are not built into any candidate.",
    "rationale": "These data resolve count distributions, not positions. Neighbour inhibition caps fast modification at 4 marks on 8 repeats (alternate repeats) before a slow filling phase, a shape cp alone cannot produce. Neighbour facilitation, by contrast, aliases with count cooperativity and with processivity. M5's joint profile will show whether nb and cp are separately determined or only their combined effect. If the nb-cp profile is flat along a ridge, 'neighbour effect versus count cooperativity' must be reported as unresolved, with the combined effect reported as determined. Sliding processivity is positional and is likely aliased with nb > 1. Kinase inactivation over 16 h aliases with cp < 1, since only the 960 min point sees either. Substrate saturation reparameterises time. All of these follow construction's decisions and none is added this round.",
    "alternatives_considered": "Adding kinase inactivation as a sixth hypothesis. It exceeds the five-candidate cap, and no observable in the single condition is argued to separate it from cp < 1.",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "The question (things the data cannot decide should be named)",
      "supports": "report unresolved mechanisms rather than decide them",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "base_model decision: not in the base, named as expected not to separate",
      "supports": "the aliasing pairs listed",
      "origin": "inferred"
     }
    ],
    "evidence_tier": "to_be_estimated",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "Revision on human feedback and the gate errors. In M3_neighbour and M5_neighbour_and_count, adds_parameters holds only nb, as asked. The 74 gap classes (Gf8, G07 ... G00) are declared as species, with their initial amounts, in each candidate's append block; they are not parameters. The engine refused that same layout because the J0 to J7 replacement lines used G species that neither the base nor adds_parameters declares. Those replacement lines therefore no longer reference any G species: J0 to J7 are set to zero rate, and each class reaction in the append carries the CTD_n + ATP -> CTD_n+1 + ADP conversion. Everything else is unchanged: candidate ids, set_parameters, the values and bounds of nb, cp and q_proc, every class reaction's rate expression, every class species and its initial amount, and every glossary entry.",
    "rationale": "I could not satisfy 'change nothing else' and pass the gate at the same time. The previous reply already did exactly what was asked, and the gate refused M3 and M5 for the reason it gave in attempt 1. A replace_reaction line may use only symbols from the base or adds_parameters, and putting the classes in adds_parameters is what petablint rejected. The closest defensible change touches only the lines the gate names (the eight J replacements) and moves their job, moving CTD_n and consuming ATP, into the class reactions. The model is the same: every species trajectory, and therefore the likelihood, matches the previous structure, because CTD_n equals the class sum in both. The gate never flagged the append block, even though it uses every G symbol. That suggests each patch is checked against its own declarations plus the base and adds_parameters, and not against other patches. The replacement lines now use base symbols only, so they pass under either reading.",
    "alternatives_considered": "Reordering the patches so the append comes first. Not chosen: the append's acceptance suggests the check is per patch, not cumulative, so the order would probably not matter. Putting the classes back in adds_parameters: rejected, because petablint refuses them. Changing the engine's symbol check to accept species declared in another patch of the same candidate: that would let the previous structure stand and is the engine maintainers' call, but this reply does not depend on it.",
    "evidence": [
     {
      "source": "general_knowledge",
      "locator": "human_feedback: petablint rejected the G species as extraneous parameters in the parameter table; keep only nb in adds_parameters",
      "supports": "the classes stay out of adds_parameters",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "previous_attempt_errors and attempt_history (attempts 1 and 2): only the eight J replacement patches flagged, never the append",
      "supports": "the gate checks replacement lines against the base and adds_parameters only; the append's own declarations are accepted",
      "origin": "inferred"
     }
    ],
    "evidence_tier": "direct",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   }
  ]
 }
}
````
