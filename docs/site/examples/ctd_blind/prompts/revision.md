# Prompt · `revision` (round 0)

The **revision** agent reads what the selected model still misses and proposes new mechanisms. Below is the exact prompt it was sent in this run (272,575 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 2 times here; the record keeps the prompt and reply of the last call, which carries the earlier attempts in its `attempt_history`.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Space expansion: say what the fitted model space was missing, and propose it as new axes

A model space has been fitted and selected. This is the loop's second chance: the first space was a hypothesis about
what might be uncertain, the fit is evidence about what is wrong. A space that did not contain the truth is not a
failure; failing to correct it now is.

## What you receive
- The fit: `selected_model`, `selection_table`, `models_fitted_this_run`, `declared_axes`, `untested_axes`,
  `evaluation_report`, `misfit_evidence` (fitted sigma against the replicate floor), `residual_diagnostics` (curves
  for the selected model and the base, a cross-model table, `residual_forms`), `bound_pressure`,
  `declared_constant_drift`, `interpretation_hypotheses`, `assembly` (observable and condition ids),
  `condition_attributes`. No raw measurements: the misfit evidence speaks for the data.
- The problem and its biology: `intent`, `experiment_description` (the lab note), `domain_packs`,
  `supplied_literature` (`lit_k`, papers the owner staged) and, with research on, `retrieved_evidence` (`res_k`) with
  `evidence_instruction`: what the retrieval role found, just before this call, about mechanisms described for this
  system that the selected model lacks; with grounding on, `prior_reactions` with `grounding_instruction`: the
  reactions the literature describes for this system, each with its sources and its grade (a band, never a
  number), `support_floor` (the band an added conversion must reach this round, with its reason) and `known_facts`.
  An axis that adds a described reaction cites its evidence ids; the card shows each axis's reactions against the
  dossier; an axis that adds a conversion below the floor is flagged to the person (advisory mode, the default) or
  held back (strict mode). An axis never removes a required reaction.
- On a second ask: `diagnostics_requested`, `human_feedback` with your `previous_reply`, or `redraft_instruction`
  with `legal_reaction_ids`.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
Required: `diagnosis` (what is missing, in mechanistic terms), `axes`, `stop_instead`; optional `beyond_this_data`,
`untested_axes_addressed`, `requested_diagnostics`, `expand_from` (shape: Output contract). Each axis has an `origin`
(`residual` | `biology`), a `priority`, one patch (`on_antimony_patch` or `on_assembly_patch`), `adds_parameters` and
`discriminating_evidence`. `stop_instead: true` comes with `axes: []` and a diagnosis naming what would account for
the evidence instead (an artefact, a missing experiment, correlated noise).

## Rules that get your reply refused
- Patch the selected model by its own reaction ids, verbatim, and declare every symbol you add in `adds_parameters`
  (`time`, `exp` and standard functions excepted). An axis that does not apply is dropped; you get one repair with
  `legal_reaction_ids`, keeping the accepted axes unchanged.
- Every axis names the observable and condition that separate on from off. That is what makes it falsifiable: the
  criterion can only choose between states the data tell apart. A mechanism nothing in the data separates goes in
  `beyond_this_data`, not in `axes`.
- One mechanism per axis, one parameter per `split_parameter` axis, so the search can say which one the data wanted.
- Do not re-propose what this run already fitted: a variant that scored worse is a wasted round.

## How to judge
**Two origins, both admissible.** `origin: residual` when the misfit points at the axis, `origin: biology` when the
packs or literature do (cite the item, `res_1` or `lit_1`). Propose new biology, not only patches for residuals: a
regulator, a loop, a route the system is known to have and the model lacks is an axis whenever the data can
separate it. Origin changes nothing about fitting or selection. An item is a claim about a source, not evidence that
this data show the mechanism, and you see the claim, not the document: attribute nothing beyond `supports` and
`quote`, and say which item motivates or rules out which proposal.

**The lab note first.** A residual whose cause the lab note names (a drift, a handling artefact, a selected
subpopulation, a process excluded by decision) is not a missing mechanism, and its decisions (what is compared,
shared, excluded) bound what you propose. A comparison the lab note or intent requires is fitted, not argued away.

**Where the misfit is, and its shape.**
- A sigma above the replicate floor on one observable localises the problem to what it reports on; a declared
  constant the fit moves (`declared_constant_drift`) is a named place to look before inventing a law.
- Shape in time is structural evidence; size may not be. A residual that changes sign along the timecourse, or runs
  one way, says the dynamics are wrong (a missing regulatory term, a wrong timescale, a missing delay), not a rate
  constant; one merely large may be the error model. If every driver rises monotonically to a plateau, no parameter
  value makes a response that peaks and returns: that shape is unreachable, not badly fitted.
- `residual_forms.summary` is the shortest account of what is still wrong: each residual's form and timescale,
  grouped where series agree. A shared timescale points at one missing process, a dose-scaled amplitude at where it
  enters, a form changing by condition at what the condition changes. It describes, it does not test: confirm a
  form with `fit_residual_form` before building an axis on it.
- A structure confined to one region of the design is easy to miss: its conditions may be the ones you have fewest
  of.
- Reason from this system's parts to the shape in front of you. Regulation is as much a mechanism as chemistry: what
  could the parts do to each other that the current rate laws do not let them?
- Spaces most often miss the truth because every candidate varied the same step: name the parts never varied and
  treat them as prior suspects (after conversion chemistry, regulation, and the other way round).

**Bound pressure.** A parameter pressed hard against its bound is a fit the box is holding back, so read
`bound_pressure` before believing a fit converged. Either the bound is wrong (a unit, a scale, a range the lab note
does not support) or the parameter stands in for a missing mechanism acting where it acts. At its edge without
pressure it is not needed there, which argues for simplification. When several are pinned, ask which limiting form
the fit walks toward and whether that form is a mechanism. Say which pinned parameters your axes release.

**The interpreter's hypotheses.** Each entry of `interpretation_hypotheses` is a hypothesis to TEST: separable from
the selected model, it is a candidate axis (structural first if it is about mechanism), and a feature it calls never
isolated by the models fitted so far is a prime suspect. They are not evidence and do not bind you; say which you
took up and why you left the others.

**Structure or observation, one diagnosis.** Shape localised in time or in one condition is structure. |residual|
growing with signal across conditions, or a noise check rejecting the distribution while the shape is unstructured,
is the error model: propose an `on_assembly_patch` axis (kinds in the Output contract, the assembly's own ids) and
name the evidence line. A sigma above the floor on one readout with no time shape can be either; say what would
separate them. An observation axis is a hypothesis about the measurement, never a fit improver; one per observable.

**Groups that may differ.** `split_parameter {parameter_id, by}` gives one estimated parameter a copy per value of a
`condition_attributes` attribute: is this rate or pool the same in every group? Propose it when one group's residuals
share a pattern the shared value cannot produce, alike in every stimulus of that group, and the lab note does not
call the parameter shared; prefer it to a new mechanism when groups differ in size or speed, not shape. The engine
writes the copies (leave `adds_parameters` empty; values − 1 extra parameters); a parameter already set per condition
is not split again.

**Writing the patch.** `append` may add anything a model holds: states and species with initial values, reactions,
assignment rules (`Y_tot := Y + Y_a;`), a whole pathway. `replace_reaction` rewrites one line; one axis may list
both, applied all or none. For example, a reservoir that sequesters X:
`[{"append": ["species W in cell;", "W = 0;", "R8: X -> W; cell * k_s * X;", "R9: W -> X; cell * k_r * W;"]}]`
with `k_s` (`neutral_value: 0`) and `k_r` in `adds_parameters`. Every added parameter declares the `neutral_value`
that switches its term off, unless it has no off-state of its own (a half-saturation, a Hill exponent) and another
parameter of the axis turns the term off. A transient is a state with first-order decay, not a function of `time`,
unless it is a declared forcing. Size the addition to the mechanism you mean, not to the residual: parsimony is the
criterion's job, and it charges every parameter you add, so a mechanism that needs three states and two rates is
proposed with three states and two rates.

**Axes declared and never fitted.** Before proposing anything new, account for every id in `untested_axes` in
`untested_axes_addressed`: `fit` (and return it in `axes`, patched onto the selected model) or `ruled_out` with the
residual evidence that excludes it. An unfitted axis is the cheapest thing left, and a free one (no new parameter)
costs one calibration and cannot overfit, so cost never justifies leaving it. This is advisory: an axis left
unaccounted for is shown to the human as such, and the human decides whether that is acceptable. Nothing rejects
your reply over it and you are not asked again, so a gap should be a choice your diagnosis defends. A ruling is shown
with its `why`, and the human can buy the axis over it: argue so a person can check, not by likelihood.

**Priority, platform, effect.** Rank the axes (`priority`, 1 = most load-bearing, one line each): when
`search.max_models` bites the lowest go first, and the human sees which. Name `expand_from` only when a rival with a
worse criterion is the better platform to build on (cleanly localised residuals, say), in one line; the human
decides, and the criterion's ranking is arithmetic, not yours to overturn. For each axis, say what the misfit
evidence should do if you are right (which sigma falls toward the floor, which pattern disappears): an improved
objective alone is not evidence.

**Beyond this data.** A mechanism you think acts here but nothing in this data tells apart from the selected model
goes in `beyond_this_data`, with why it is not separable and the measurement or perturbation that would separate it;
the human sees it on the card and the run page lists it for the next experiment. Never list one you also propose as
an axis.

**Ask, and revise.** When the payload does not settle a diagnosis, return `axes: []` with `requested_diagnostics`
(`simulate_with`, `residuals_for`, `compare_conditions`, `fit_residual_form`; budget in `diagnostics_instruction`)
rather than guess: the engine runs them and asks again. When whether a mechanism is described for this system would
settle the proposal and the evidence you hold does not say, return `axes: []` with `requested_research` (1–3
one-sentence questions, each naming the mechanism or observation to look for; one search per round, see
`research_instruction`) rather than guess: the engine has the research role search for them and asks again, the items
in `retrieved_evidence` (with grounding on, the knowledge role runs that search, and what it finds is graded and,
at the floor, admitted to the dossier you see). With `human_feedback`, revise the proposal in `previous_reply`: do what they asked, keep
every axis, id and patch the request does not implicate exactly as it was, and say what changed and why (the card
shows new, withdrawn and kept). If what they ask cannot be a fittable axis, or the data cannot separate it, say so
plainly and propose the closest testable thing.

## Mistakes we have seen
- An axis declared early and never fitted, while later proposals invented new laws for the part of the model it
  would have repaired.
- Concluding that no new state can be added: it can, with an `append` block that declares it.
- Every candidate varying the same step while the residuals pointed elsewhere.


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
## selected_model
M5_neighbour_and_count
## selection_table
```json
[
  {
    "id": "M1_independent",
    "n_est": 6,
    "n_flat": 0,
    "n_data": 36,
    "nllh": -61.35757784224383,
    "aic": -110.71515568448766,
    "bic": -101.214042053751,
    "at_bounds": [],
    "near_bounds": [],
    "delta_aic": 55.688,
    "akaike_weight": 0.0,
    "criterion": "AIC",
    "value": -110.715156,
    "delta": 55.688,
    "weight": 0.0
  },
  {
    "id": "M2_count_coop",
    "n_est": 7,
    "n_flat": 0,
    "n_data": 36,
    "nllh": -81.64140731312479,
    "aic": -149.28281462624957,
    "bic": -138.1981820570568,
    "at_bounds": [],
    "near_bounds": [],
    "delta_aic": 17.121,
    "akaike_weight": 0.0002,
    "criterion": "AIC",
    "value": -149.282815,
    "delta": 17.121,
    "weight": 0.0002
  },
  {
    "id": "M3_neighbour",
    "n_est": 7,
    "n_flat": 0,
    "n_data": 36,
    "nllh": -84.25342084679188,
    "aic": -154.50684169358377,
    "bic": -143.422209124391,
    "at_bounds": [],
    "near_bounds": [],
    "delta_aic": 11.897,
    "akaike_weight": 0.0026,
    "criterion": "AIC",
    "value": -154.506842,
    "delta": 11.897,
    "weight": 0.0026
  },
  {
    "id": "M4_processive",
    "n_est": 7,
    "n_flat": 0,
    "n_data": 36,
    "nllh": -80.95238258088617,
    "aic": -147.90476516177233,
    "bic": -136.82013259257957,
    "at_bounds": [],
    "near_bounds": [],
    "delta_aic": 18.499,
    "akaike_weight": 0.0001,
    "criterion": "AIC",
    "value": -147.904765,
    "delta": 18.499,
    "weight": 0.0001
  },
  {
    "id": "M5_neighbour_and_count",
    "n_est": 8,
    "n_flat": 0,
    "n_data": 36,
    "nllh": -91.20174613400813,
    "aic": -166.40349226801627,
    "bic": -153.7353407603674,
    "at_bounds": [],
    "near_bounds": [],
    "delta_aic": 0.0,
    "akaike_weight": 0.9971,
    "criterion": "AIC",
    "value": -166.403492,
    "delta": 0.0,
    "weight": 0.9971
  }
]
```
## models_fitted_this_run
```json
[
  {
    "round": 0,
    "model": "M1_independent",
    "axes_on": [],
    "axes_in_space": [],
    "n_estimated": 6,
    "nllh": -61.35757784224383,
    "criterion": "AIC",
    "delta": 55.688,
    "weight": 0.0,
    "selected": false,
    "base_model": "round-0 base",
    "base_carried_undecided": []
  },
  {
    "round": 0,
    "model": "M2_count_coop",
    "axes_on": [],
    "axes_in_space": [],
    "n_estimated": 7,
    "nllh": -81.64140731312479,
    "criterion": "AIC",
    "delta": 17.121,
    "weight": 0.0002,
    "selected": false,
    "base_model": "round-0 base",
    "base_carried_undecided": []
  },
  {
    "round": 0,
    "model": "M3_neighbour",
    "axes_on": [],
    "axes_in_space": [],
    "n_estimated": 7,
    "nllh": -84.25342084679188,
    "criterion": "AIC",
    "delta": 11.897,
    "weight": 0.0026,
    "selected": false,
    "base_model": "round-0 base",
    "base_carried_undecided": []
  },
  {
    "round": 0,
    "model": "M4_processive",
    "axes_on": [],
    "axes_in_space": [],
    "n_estimated": 7,
    "nllh": -80.95238258088617,
    "criterion": "AIC",
    "delta": 18.499,
    "weight": 0.0001,
    "selected": false,
    "base_model": "round-0 base",
    "base_carried_undecided": []
  },
  {
    "round": 0,
    "model": "M5_neighbour_and_count",
    "axes_on": [],
    "axes_in_space": [],
    "n_estimated": 8,
    "nllh": -91.20174613400813,
    "criterion": "AIC",
    "delta": 0.0,
    "weight": 0.9971,
    "selected": true,
    "base_model": "round-0 base",
    "base_carried_undecided": []
  }
]
```
## declared_axes
```json
[]
```
## untested_axes
```json
[]
```
## untested_first
UNTESTED FIRST. `untested_axes` lists mechanisms already DECLARED in this run that no fitted model has ever carried. Before proposing a new law, account for every one of them in `untested_axes_addressed`: either action 'fit' (return it in `axes`, patched to the selected model) or action 'ruled_out' with `why` citing the residual evidence that excludes it. A FREE axis (adds no parameter) costs one calibration and cannot overfit, so 'too expensive' is never a reason to leave one untested. Re-proposing a mechanism already rejected is allowed only if you name what has changed in the background and quote its previous standing. This is advisory, not a contract: an axis you leave unaccounted for is shown to the human as unaccounted for, beside your proposal, and the human decides whether that is acceptable.
## declared_constant_drift
```json
{
  "declared": 2,
  "measured": 2,
  "unmeasured": 0,
  "violated": 0,
  "worst_drift": 1.41824330057716e-13,
  "rows": [
    {
      "expression": "CTD_0 + CTD_1 + CTD_2 + CTD_3 + CTD_4 + CTD_5 + CTD_6 + CTD_7 + CTD_8",
      "tolerance": 0.01,
      "locator": "'even though the total amount of substrate in the tube is conserved throughout'",
      "why": "total CTD substrate is conserved at 100 uM; modification only moves molecules between count classes",
      "condition": "cond_invitro_PTEFb_CTD8",
      "at_t0": 100.0,
      "worst": 99.99999999998582,
      "at_time": 96.0,
      "drift": 1.41824330057716e-13,
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
}
```
## misfit_evidence
```json
{
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
## evaluation_report
```json
{
  "parameters": {
    "M1_independent": {
      "kmod": 0.006385455193426391,
      "cp": 1.0,
      "q_proc": 0.0,
      "K_ATP": 49.99999999999999,
      "sc_ctd_ms_t0": 0.009944023052820867,
      "sc_ctd_ms_t60": 0.0371308445971237,
      "sc_ctd_ms_t120": 0.03491726666273612,
      "sc_ctd_ms_t960": 0.008640211962315082,
      "sigma_ctd_ms": 2.409048832995405
    },
    "M2_count_coop": {
      "kmod": 0.005099661486496304,
      "cp": 1.1360867690006224,
      "q_proc": 0.0,
      "K_ATP": 49.99999999999999,
      "sc_ctd_ms_t0": 0.009979933912982136,
      "sc_ctd_ms_t60": 0.038576876992173076,
      "sc_ctd_ms_t120": 0.03900083614079316,
      "sc_ctd_ms_t960": 0.008504880705952919,
      "sigma_ctd_ms": 1.3252979929600286
    },
    "M3_neighbour": {
      "kmod": 0.004888921585140934,
      "cp": 1.0,
      "q_proc": 0.0,
      "K_ATP": 49.99999999999999,
      "nb": 1.8116197474139275,
      "sc_ctd_ms_t0": 0.009982165002816854,
      "sc_ctd_ms_t60": 0.038951863027663444,
      "sc_ctd_ms_t120": 0.039194953974109936,
      "sc_ctd_ms_t960": 0.008514385686318286,
      "sigma_ctd_ms": 1.2277024337493585
    },
    "M4_processive": {
      "kmod": 0.005212587921621219,
      "cp": 1.0,
      "q_proc": 0.21236831526693548,
      "K_ATP": 49.99999999999999,
      "sc_ctd_ms_t0": 0.009980037397603874,
      "sc_ctd_ms_t60": 0.04045616953277489,
      "sc_ctd_ms_t120": 0.03934069010666261,
      "sc_ctd_ms_t960": 0.008789151778087286,
      "sigma_ctd_ms": 1.3211048815283524
    },
    "M5_neighbour_and_count": {
      "kmod": 0.004576866216237832,
      "cp": 1.5882933610312424,
      "q_proc": 0.0,
      "K_ATP": 49.99999999999999,
      "nb": 0.3139807103785649,
      "sc_ctd_ms_t0": 0.009986490804763796,
      "sc_ctd_ms_t60": 0.039708106720571464,
      "sc_ctd_ms_t120": 0.03843859274915539,
      "sc_ctd_ms_t960": 0.008519391989917075,
      "sigma_ctd_ms": 1.0119563866831265
    }
  }
}
```
## interpretation_hypotheses
```json
{
  "recommendation": "revise",
  "diagnosis": "Within the five fitted candidates, M5_neighbour_and_count is selected decisively. Its AIC is -166.40, its Akaike weight 0.9971, and the indistinguishable set is {M5_neighbour_and_count}. The others trail by \u0394AIC 11.90 (M3_neighbour), 17.12 (M2_count_coop), 18.50 (M4_processive) and 55.69 (M1_independent); petab_select agrees.\n\nOBSERVATION MODEL AS FITTED. Each of the 36 cells is y_n(t_j) = sc_ctd_ms_tj * [CTD with n phosphates](t_j) + e, with e ~ N(0, (sigma_ctd_ms * sc_ctd_ms_tj)^2), on a linear scale. Each spectrum has one free scale: t0 0.009986, t60 0.03971, t120 0.03844 and t960 0.008519 per \u00b5M. These map 100 \u00b5M to 1.00/3.97/3.84/0.85, against measured sums of 1.00/4.07/3.79/0.85. One sigma_ctd_ms = 1.012 \u00b5M-equivalent is shared by every cell. Check: the phos5 1-h residual of 0.1027 equals 2.555 x 1.012 x 0.03971. Substrate conservation holds to 1e-13.\n\nWHY M5 WINS (attribution).\n- Against M1, the 1-h spectrum pays: phos1 3.27, phos3 2.63, phos0 2.29 and phos2 1.71 in -log L. An independent, homogeneous model must give a binomial, but the measured 1-h distribution is much broader. Measured phos0 is 0.394 against 0.183 predicted, and the variance is about 1.5x binomial at the same mean.\n- Against M2 and M3, the gain is in phos2 at 1 h (2.77, 2.13), phos4 at 1 h (1.49, 1.38) and phos7 at 2 h (1.32, 1.76). M5 gives back phos0 at 1 h and phos2/phos6 at 2 h.\n- Against M4, the gain is phos7 at 16 h (3.21; M4's slower base rate leaves 3% stuck at seven), phos1 at 1 h (1.70) and phos8 at 2 h (1.62; M4 predicts 0.145 where 0 was measured). M4 is better on the 1-h upper tail (phos5 -2.66, phos6 -1.73).\n\nThe data demand a distribution that is broad at 1 h, has an empty phos8 peak at 2 h, and is complete at 16 h. M5 gets there by pairing count acceleration (cp 1.588) with nb 0.314. If nb is a per-neighbour multiplicative factor with neutral value 1, like cp, this brakes the filling of flanked gaps late in the reaction.\n\nTWO LIMITS ON THIS RESULT.\n(i) Roughly half of every margin is sigma bookkeeping, not mechanism. The 18 cells at 0 h and 16 h are fitted to within noise by every model (19 measured values are exact zeros). Each adds log(sigma_rival/sigma_M5) to the winner: 0.193 per cell against M3, about 3.5 of its 6.95 \u0394(-log L). On the 18 informative cells at 1 h and 2 h, the margin over M3 is about \u0394AIC 5. That is still above 2, but the weight is nearer 0.9 than 0.997. Exact zeros are also not what the stated additive Gaussian noise produces.\n(ii) The neighbour term is seen only through the count distribution, and its value moves across neutral between models (nb 1.812 in M3, 0.314 in M5). What it buys in M5 is a step-rate profile that rises through mid-counts and brakes at the end, which M2's single cp cannot express. No count-only candidate with an equally flexible step-rate profile was fitted. So this round does not show that the effect is specifically about immediate neighbours.\n\nREMAINING STRUCTURE. The per-series shape tools are degenerate here: each peak x time is its own observable with n = 1, so sign runs, autocorrelation and residual_forms carry no shape. Read across counts within each spectrum, M5's largest residuals form one pattern:\n- the 1-h upper tail is underpredicted (phos5 +2.6 sigma, 0.352 vs 0.250; phos6 +2.0 sigma);\n- the 2-h top is overpredicted (phos8 -2.3 sigma, 0 vs 0.088; phos7 -2.0 sigma);\n- the 2-h low tail is heavier than any candidate gives (phos1 at 2 h is 0.191, against at most 0.164).\nThere are no replicates, sigma is fitted from these same residuals, and the noise check has n = 1 per cell. Absolute adequacy therefore cannot be judged; chi2/dof is about 1 by construction.\n\nIDENTIFIABILITY. The FIM spans 2.86 decades with no flat direction; its smallest eigenvector is sigma_ctd_ms. Profiles were not computed, so no intervals exist. The nested reductions still exceed the 1.92 profile threshold even if halved: M2 drops nb (\u0394(-log L) 9.56) and M3 fixes cp = 1 (6.95). Both terms are therefore non-null within M5.\n\nANSWERS TO THE INTENT.\n- 'The rate depends on nothing at all' is rejected for a homogeneous substrate. Static substrate heterogeneity was not tried.\n- Count-only and neighbour-only each fall short of both together. Whether the second term is specifically an immediate-neighbour effect is not established.\n- Distributive vs processive: processivity alone (q_proc 0.2124) loses by \u0394AIC 18.5, which is consistent with the by-eye call. But processivity was never combined with the coupling terms, and M4 fits the 1-h upper tail best. 'Distributive' therefore holds only against processivity alone.\n- Global effects cannot produce the non-binomial shape. These are ATP (3 mM with at most 0.8 mM consumed, K_ATP fixed at 50), kinase loss and product inhibition. They multiply every step equally and only re-time the trajectory.\n\nREVISE, with one move: fit a count-only candidate with a three-parameter step-rate profile and compare its -log L with M5's -91.20.",
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
  "how_to_read_this": "The interpretation agent read the same fits and residuals and wrote these hypotheses and open questions. They are SUGGESTIONS TO TEST, not decisions: where the data can separate one from the selected model it is a candidate axis. Say in your diagnosis which you took up and why you left the others."
}
```
## assembly
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
  ],
  "noise": [
    {
      "observable_id": "obs_phos0",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos1",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos2",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos3",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos4",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos5",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos6",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos7",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos8",
      "distribution": "normal",
      "formula": "sc_ctd_ms * sigma_ctd_ms",
      "estimate_sigma": true,
      "per": "observable",
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    }
  ],
  "scaling": [
    {
      "observable_id": "obs_phos0",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos1",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos2",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos3",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos4",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos5",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos6",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos7",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    },
    {
      "observable_id": "obs_phos8",
      "mode": "factor",
      "scale_parameter": "sc_ctd_ms",
      "offset_parameter": null,
      "per": "timepoint",
      "shared_across_observables": "ctd_ms",
      "pin_first_to_one": false,
      "shared_across_conditions": true,
      "rationale": "(argued with the observable's rationale \u2014 one observation function)"
    }
  ],
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
```
## attempt_history
```json
{
  "attempts": [
    {
      "attempt": 1,
      "gate_failures": [
        "axis 'processive_adjacent_double_hit': every combination carrying 'processive_adjacent_double_hit' fails the pre-compile ladder: state goes negative over the horizon",
        "axis 'per_molecule_docking_route': every combination carrying 'per_molecule_docking_route' fails the pre-compile ladder: state goes negative over the horizon"
      ],
      "draft_summary": {
        "axes_proposed": [
          "processive_adjacent_double_hit",
          "per_molecule_docking_route"
        ],
        "diagnosis": "WHERE M5 STILL MISSES. Each peak x time cell is its own n=1 series, so residual_forms carries no time shape. The structure has to be read across counts within each spectrum. At 1 h the upper tail is short: obs_phos5 +2.6\u03c3, obs_phos6 +2.0\u03c3 and obs_phos4 +1.2\u03c3, while obs_phos0/2/3 sit between -1.1\u03c3 an"
      }
    }
  ],
  "instruction": "Every attempt so far, oldest first, with its gate failures and what each draft looked like. Do not re-propose what an earlier attempt already tried; fix the failures named and keep everything that passed. If `minimal_repair` is present, return a MINIMAL edit of the previous draft \u2014 the engine measures how much you changed beyond what the failures implicated."
}
```
## legal_reaction_ids
```json
[
  "J0",
  "J1",
  "J2",
  "J3",
  "J4",
  "J5",
  "J6",
  "J7",
  "Jp0_2",
  "Jp0_3",
  "Jp0_4",
  "Jp0_5",
  "Jp0_6",
  "Jp0_7",
  "Jp0_8",
  "Jp1_2",
  "Jp1_3",
  "Jp1_4",
  "Jp1_5",
  "Jp1_6",
  "Jp1_7",
  "Jp2_2",
  "Jp2_3",
  "Jp2_4",
  "Jp2_5",
  "Jp2_6",
  "Jp3_2",
  "Jp3_3",
  "Jp3_4",
  "Jp3_5",
  "Jp4_2",
  "Jp4_3",
  "Jp4_4",
  "Jp5_2",
  "Jp5_3",
  "Jp6_2",
  "Q_G00_111_G00_11",
  "Q_G00_11_G00_1",
  "Q_G00_1_G00",
  "Q_G00_211_G00_111",
  "Q_G00_211_G00_21",
  "Q_G00_21_G00_11",
  "Q_G00_21_G00_2",
  "Q_G00_22_G00_21",
  "Q_G00_2_G00_1",
  "Q_G00_31_G00_111",
  "Q_G00_31_G00_21",
  "Q_G00_31_G00_3",
  "Q_G00_32_G00_211",
  "Q_G00_32_G00_22",
  "Q_G00_32_G00_31",
  "Q_G00_3_G00_11",
  "Q_G00_3_G00_2",
  "Q_G00_41_G00_211",
  "Q_G00_41_G00_31",
  "Q_G00_41_G00_4",
  "Q_G00_4_G00_21",
  "Q_G00_4_G00_3",
  "Q_G00_5_G00_22",
  "Q_G00_5_G00_31",
  "Q_G00_5_G00_4",
  "Q_G00_6_G00_32",
  "Q_G00_6_G00_41",
  "Q_G00_6_G00_5",
  "Q_G01_111_G00_111",
  "Q_G01_111_G01_11",
  "Q_G01_11_G00_11",
  "Q_G01_11_G01_1",
  "Q_G01_1_G00_1",
  "Q_G01_1_G01",
  "Q_G01_21_G00_21",
  "Q_G01_21_G01_11",
  "Q_G01_21_G01_2",
  "Q_G01_22_G00_22",
  "Q_G01_22_G01_21",
  "Q_G01_2_G00_2",
  "Q_G01_2_G01_1",
  "Q_G01_31_G00_31",
  "Q_G01_31_G01_111",
  "Q_G01_31_G01_21",
  "Q_G01_31_G01_3",
  "Q_G01_3_G00_3",
  "Q_G01_3_G01_11",
  "Q_G01_3_G01_2",
  "Q_G01_4_G00_4",
  "Q_G01_4_G01_21",
  "Q_G01_4_G01_3",
  "Q_G01_5_G00_5",
  "Q_G01_5_G01_22",
  "Q_G01_5_G01_31",
  "Q_G01_5_G01_4",
  "Q_G01_G00",
  "Q_G02_11_G00_111",
  "Q_G02_11_G01_11",
  "Q_G02_11_G02_1",
  "Q_G02_1_G00_11",
  "Q_G02_1_G01_1",
  "Q_G02_1_G02",
  "Q_G02_21_G00_211",
  "Q_G02_21_G01_21",
  "Q_G02_21_G02_11",
  "Q_G02_21_G02_2",
  "Q_G02_2_G00_21",
  "Q_G02_2_G01_2",
  "Q_G02_2_G02_1",
  "Q_G02_3_G00_31",
  "Q_G02_3_G01_3",
  "Q_G02_3_G02_11",
  "Q_G02_3_G02_2",
  "Q_G02_4_G00_41",
  "Q_G02_4_G01_4",
  "Q_G02_4_G02_21",
  "Q_G02_4_G02_3",
  "Q_G02_G00_1",
  "Q_G02_G01",
  "Q_G03_11_G00_211",
  "Q_G03_11_G01_111",
  "Q_G03_11_G02_11",
  "Q_G03_11_G03_1",
  "Q_G03_1_G00_21",
  "Q_G03_1_G01_11",
  "Q_G03_1_G02_1",
  "Q_G03_1_G03",
  "Q_G03_2_G00_22",
  "Q_G03_2_G01_21",
  "Q_G03_2_G02_2",
  "Q_G03_2_G03_1",
  "Q_G03_3_G00_32",
  "Q_G03_3_G01_31",
  "Q_G03_3_G02_3",
  "Q_G03_3_G03_11",
  "Q_G03_3_G03_2",
  "Q_G03_G00_2",
  "Q_G03_G01_1",
  "Q_G03_G02",
  "Q_G04_1_G00_31",
  "Q_G04_1_G01_21",
  "Q_G04_1_G02_11",
  "Q_G04_1_G03_1",
  "Q_G04_1_G04",
  "Q_G04_2_G00_32",
  "Q_G04_2_G01_22",
  "Q_G04_2_G02_21",
  "Q_G04_2_G03_2",
  "Q_G04_2_G04_1",
  "Q_G04_G00_3",
  "Q_G04_G01_2",
  "Q_G04_G02_1",
  "Q_G04_G03",
  "Q_G05_1_G00_41",
  "Q_G05_1_G01_31",
  "Q_G05_1_G02_21",
  "Q_G05_1_G03_11",
  "Q_G05_1_G04_1",
  "Q_G05_1_G05",
  "Q_G05_G00_4",
  "Q_G05_G01_3",
  "Q_G05_G02_2",
  "Q_G05_G03_1",
  "Q_G05_G04",
  "Q_G06_G00_5",
  "Q_G06_G01_4",
  "Q_G06_G02_3",
  "Q_G06_G03_2",
  "Q_G06_G04_1",
  "Q_G06_G05",
  "Q_G07_G00_6",
  "Q_G07_G01_5",
  "Q_G07_G02_4",
  "Q_G07_G03_3",
  "Q_G07_G04_2",
  "Q_G07_G05_1",
  "Q_G07_G06",
  "Q_G11_11_G01_11",
  "Q_G11_11_G11_1",
  "Q_G11_1_G01_1",
  "Q_G11_1_G11",
  "Q_G11_21_G01_21",
  "Q_G11_21_G11_11",
  "Q_G11_21_G11_2",
  "Q_G11_2_G01_2",
  "Q_G11_2_G11_1",
  "Q_G11_3_G01_3",
  "Q_G11_3_G11_11",
  "Q_G11_3_G11_2",
  "Q_G11_4_G01_4",
  "Q_G11_4_G11_21",
  "Q_G11_4_G11_3",
  "Q_G11_G01",
  "Q_G12_11_G01_111",
  "Q_G12_11_G02_11",
  "Q_G12_11_G11_11",
  "Q_G12_11_G12_1",
  "Q_G12_1_G01_11",
  "Q_G12_1_G02_1",
  "Q_G12_1_G11_1",
  "Q_G12_1_G12",
  "Q_G12_2_G01_21",
  "Q_G12_2_G02_2",
  "Q_G12_2_G11_2",
  "Q_G12_2_G12_1",
  "Q_G12_3_G01_31",
  "Q_G12_3_G02_3",
  "Q_G12_3_G11_3",
  "Q_G12_3_G12_11",
  "Q_G12_3_G12_2",
  "Q_G12_G01_1",
  "Q_G12_G02",
  "Q_G12_G11",
  "Q_G13_1_G01_21",
  "Q_G13_1_G03_1",
  "Q_G13_1_G11_11",
  "Q_G13_1_G12_1",
  "Q_G13_1_G13",
  "Q_G13_2_G01_22",
  "Q_G13_2_G03_2",
  "Q_G13_2_G11_21",
  "Q_G13_2_G12_2",
  "Q_G13_2_G13_1",
  "Q_G13_G01_2",
  "Q_G13_G03",
  "Q_G13_G11_1",
  "Q_G13_G12",
  "Q_G14_1_G01_31",
  "Q_G14_1_G04_1",
  "Q_G14_1_G11_21",
  "Q_G14_1_G12_11",
  "Q_G14_1_G13_1",
  "Q_G14_1_G14",
  "Q_G14_G01_3",
  "Q_G14_G04",
  "Q_G14_G11_2",
  "Q_G14_G12_1",
  "Q_G14_G13",
  "Q_G15_G01_4",
  "Q_G15_G05",
  "Q_G15_G11_3",
  "Q_G15_G12_2",
  "Q_G15_G13_1",
  "Q_G15_G14",
  "Q_G16_G01_5",
  "Q_G16_G06",
  "Q_G16_G11_4",
  "Q_G16_G12_3",
  "Q_G16_G13_2",
  "Q_G16_G14_1",
  "Q_G16_G15",
  "Q_G22_1_G02_11",
  "Q_G22_1_G12_1",
  "Q_G22_1_G22",
  "Q_G22_2_G02_21",
  "Q_G22_2_G12_2",
  "Q_G22_2_G22_1",
  "Q_G22_G02_1",
  "Q_G22_G12",
  "Q_G23_1_G02_21",
  "Q_G23_1_G03_11",
  "Q_G23_1_G12_11",
  "Q_G23_1_G13_1",
  "Q_G23_1_G22_1",
  "Q_G23_1_G23",
  "Q_G23_G02_2",
  "Q_G23_G03_1",
  "Q_G23_G12_1",
  "Q_G23_G13",
  "Q_G23_G22",
  "Q_G24_G02_3",
  "Q_G24_G04_1",
  "Q_G24_G12_2",
  "Q_G24_G14",
  "Q_G24_G22_1",
  "Q_G24_G23",
  "Q_G25_G02_4",
  "Q_G25_G05_1",
  "Q_G25_G12_3",
  "Q_G25_G15",
  "Q_G25_G22_2",
  "Q_G25_G23_1",
  "Q_G25_G24",
  "Q_G33_G03_2",
  "Q_G33_G13_1",
  "Q_G33_G23",
  "Q_G34_G03_3",
  "Q_G34_G04_2",
  "Q_G34_G13_2",
  "Q_G34_G14_1",
  "Q_G34_G23_1",
  "Q_G34_G24",
  "Q_G34_G33",
  "Q_Gf8_G07",
  "Q_Gf8_G16",
  "Q_Gf8_G25",
  "Q_Gf8_G34"
]
```
## redraft_instruction
Some of the axes you proposed could not be applied or failed the pre-compile ladder on the selected model (see attempt_history). Re-emit your proposal with those fixed or removed; patch ONLY the reaction ids listed in legal_reaction_ids, declare every symbol you introduce, and keep the axes that were accepted unchanged. You will not be asked again.

# Output contract
{
  "diagnosis": "what the residual evidence says is missing, in mechanistic terms",
  "requested_diagnostics": [{"kind": "simulate_with|residuals_for|compare_conditions|fit_residual_form", "args": {"candidate_id": "..."}}],
  "requested_research": ["one sentence naming the mechanism or observation to look for in the literature on this system"],
  "axes": [{"id": "short_slug", "question": "the structural question this axis settles",
             "origin": "residual|biology",
             "default": "off",
             "priority": 1, "priority_reason": "one line: why this axis first (1 = most load-bearing)",
             "on_antimony_patch": {"replace_reaction": "R2", "with": "R2: Y -> Y_a; ...full replacement line..."},
             "adds_parameters": [{"id": "k_x", "nominal_value": 1.0, "unit": "...", "lb": 0.0, "ub": 0.0, "evidence_tier": "to_be_estimated", "source": "...", "estimate": true, "neutral_value": 0.0, "denotes": "strength of the term this axis adds (0 = off)"}],
             "rationale": "why this mechanism, and why HERE in the network",
             "discriminating_evidence": "which observable, in which condition, separates on from off"}],
  "beyond_this_data": [{"mechanism": "a mechanism you think acts in this system",
                        "why_not_separable": "why THIS data cannot tell it from the selected model",
                        "experiment": "the measurement or perturbation that would"}],
  "untested_axes_addressed": [{"id": "an id from untested_axes", "action": "fit|ruled_out", "why": "for ruled_out: the residual evidence that excludes it"}],
  "expand_from": {"candidate_id": "an id from selection_table", "why": "one line: why this is the better PLATFORM to enlarge"},
  "stop_instead": false
}
NOTE on the BIOLOGY you are given: `domain_packs` (the pitfalls and templates
construction was given), `supplied_literature` when the person staged papers,
and, when research is on, `retrieved_evidence` — what the research role found,
just before this call, about mechanisms described for this system that the
selected model lacks (`evidence_instruction` says how to use it). Propose new
biology, not only patches for the residuals: a regulator, a loop, a route the
system is known to have that the model leaves out is an axis when the data can
separate it from the selected model.
NOTE on "origin" (OPTIONAL, default "residual"): per axis, what proposed it —
"residual" when the misfit evidence pointed at it, "biology" when the packs or
the literature did (cite the item's id, res_1 or lit_1, in the rationale). The
card shows it beside each axis; it changes nothing about how the axis is fitted
or selected.
NOTE on "beyond_this_data" (OPTIONAL, may be empty): mechanisms you think act
in this system that THIS data cannot separate from the selected model — no
observable, condition or time point tells on from off — each with why, and the
experiment that would separate it. They are not axes and nothing is fitted for
them: the human sees them on the card, and the run page lists them as what the
next experiment could decide. Do not list a mechanism you also propose as an
axis.
NOTE on `expand_from` (OPTIONAL): the engine's default base for the enlarged
space is the criterion winner. A criterion measures fit-plus-parsimony NOW, not
expandability: a rival with a worse AIC whose residuals are cleanly localised
can be the better platform to build on. Name one only if you think so, and say
why in one line — it is shown to the human beside the default, and the HUMAN
decides. Do not use it to relitigate the verdict: the criterion's ranking of
the fitted models is arithmetic and is not yours to overturn.
NOTE: account for EVERY id in `untested_axes` in `untested_axes_addressed`. An
axis already declared in this run and never fitted is cheaper to settle than a
new law, and a free axis (no new parameter) cannot overfit — so it is fitted,
not priced out. This is ADVISORY and not part of the contract: an axis you
leave unaccounted for is shown to the human as unaccounted for, beside your
proposal, and the human decides whether that is acceptable. Nothing refuses
your reply over it and you are not asked again.

NOTE: you are expanding a model space that has already been fitted and selected.
The axes you return are added to the SELECTED model and the whole enlarged space
is refitted, so each axis must patch the selected model's own reaction ids
verbatim and declare every symbol it introduces (`time`, `exp` and the standard
functions need no declaration, but PREFER a transient written as an additional
state with an initial value and first-order decay — a removable mechanism the
fit can test — over an explicit function of time; use `time` only for a
genuinely external, declared forcing). Return `stop_instead: true`
with an empty `axes` list ONLY if you judge that no mechanism can explain the
residual evidence and say why in `diagnosis`.

NOTE on "requested_diagnostics": OPTIONAL. When the payload does not settle a
diagnosis, ask the ENGINE for one more computation instead of guessing: it runs
deterministically, is ledgered, and its results come back to you under
`diagnostics_requested`; then you are asked again. Return `axes: []` together
with requests when you are not ready to propose. Bounded (see the instruction
in your inputs); no request fits anything or reads outside the run.

NOTE on "requested_research": OPTIONAL. When whether a mechanism is described
for this system would settle your proposal and the evidence you were given does
not say, ask for a literature search instead of guessing: 1-3 questions, each
ONE sentence naming the mechanism or observation to look for. Return `axes: []`
and your diagnosis so far with them, as with `requested_diagnostics` (both may
go in one reply). You stay offline: the engine hands your questions to the
research role, fences what it returns like every retrieved item (the case's
blocklist and publication horizon), freezes it in the round, adds the items to
`retrieved_evidence` with new ids (each names the question it answers in
`answers_question`), and asks you again with your questions under
`research_answered`. One search per expansion round: a second request is
refused and you are asked once more without it, and a run that allows no
search refuses the first the same way (`research_refused` says why).
`research_instruction` in your inputs says which applies. When
`prior_reactions` is in your inputs, the search is the knowledge role's
targeted search instead: name each conversion to look for as an equation in the
selected model's species ids (`A + B -> C`) and why; what it finds is graded by
the engine, and what reaches `support_floor` joins `prior_reactions` (origin
`search`) before you are asked again.
NOTE on "support_floor" when present: the floor of the round your axes are
fitted in (`words` says it in a sentence). An axis whose patch adds a
conversion graded below it, or one no entry of `prior_reactions` describes, is
REFUSED from the offer by name before the person sees it; an axis that changes
only a rate law or a switch adds no conversion and is never refused for it. An
axis that removes a reaction implementing one of the intent's required
reactions is refused whatever the floor: only the person removes a required
reaction, by editing the intent.

NOTE on OBSERVATION axes: an axis may instead carry `on_assembly_patch` (never
both): {"change_observable_formula": {"observable_id", "new_formula"}},
{"change_noise_model": {"observable_id", "new_distribution": "normal|laplace"}},
{"change_noise_model": {"observable_id", "new_formula": "sigma_obs_x * <this observable's signal expression>"}}
(proportional noise), {"change_noise_model": {"observable_id", "new_per": "condition"}}
(one sigma per condition — for a replicate spread that differs between arms of
the design; every extra sigma counts in k), {"add_offset": {"observable_id"}}, {"remove_scaling":
{"observable_id"}}, {"change_scaling": {"observable_id" | "observable_ids": [...],
"per": "observable|timepoint|condition", "shared_across_observables": false | "<group>",
"pin_first_to_one": false}} (a scale factor per time or per condition, optionally
shared by a group), {"change_condition": {"condition_id", "overrides":
{"<model parameter>": value}}} (which parameter a perturbation enters — never a
measured factor's value), {"split_parameter": {"parameter_id", "by": "<attribute>"}}
(one copy of an ESTIMATED model parameter per value of a condition attribute listed
in `condition_attributes` — e.g. one per population — in every condition; the engine
writes the copies and their rows from the parameter's own, so leave adds_parameters
empty; it adds (values - 1) parameters to k; one parameter family per axis; never a
parameter the assembly already sets per condition). Use the assembly's own
observable_id / condition_id (you are given the assembly). The differential diagnosis is one act: structure
vs observation model. Propose an observation axis ONLY when the observation-
layer evidence points there — |residual| growing with signal, a rejected
noise-model check, a sigma above the floor on ONE readout with no time shape —
and cite that evidence in `discriminating_evidence`. Residual SHAPE that
localises in time or condition is structure, not observation. One observation
axis per observable.

NOTE on "neutral_value" (the same rule as at construction): for each entry of
`adds_parameters`, give the value at which that parameter makes the axis's term
VANISH from the selected model — an added route has `neutral_value: 0`; a
feedback written as `k*A/(1 + beta*A)` has `neutral_value: 0` for beta. Where
every axis declares one, the enlarged space is ONE compiled model whose
candidates differ by parameter table alone and are exactly nested. THE RULE:
EVERY parameter an axis adds should carry `neutral_value`. A parameter with no
honest off-state of its own — a half-saturation `K`, a Hill exponent — may omit
it ONLY when another parameter of the SAME axis switches the whole term off
(`k` with `neutral_value: 0` makes `K` irrelevant); the engine then fixes `K` at
its nominal value in the off-state candidates and checks by simulation that the
term is gone. An axis in which NO parameter declares a neutral value costs its
own compile. Every declaration is CHECKED against the selected model; a wrong
one is recorded, never trusted — declare it where it is true and nowhere else.

NOTE on "known_facts" when present: what the knowledge module found, before the intent was frozen, that a model of this system needs beyond its reactions — each with an `id` (`fact_1`), a `kind`, a `statement` (a `value` and `unit` where it is quantitative), what it `applies_to`, its evidence and the grade the engine gave it (`not_applicable` when it was gathered offline). Only the facts meant for your role reach you. Use a fact where it applies instead of inventing the assumption, and where you depart from one, say why. A parameter an axis adds whose value comes from a fact carries `source: "knowledge:<fact id>"` in `adds_parameters`, and an axis a fact motivates cites its id in its `rationale`.
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "diagnosis": "WHERE M5 STILL MISSES. Each peak at each time is its own n=1 series, so residual_forms carries no time shape. The structure has to be read across counts within each spectrum. All of M5's residuals above 1.5σ sit at 1 h and 2 h, and they form one timing distortion. At 60 min the data are further along than M5: obs_phos0 is −1.6σ (fewer unmodified molecules), obs_phos5 +2.6σ and obs_phos6 +2.0σ, and the spectrum's mean count is 2.48 measured against 2.33 simulated. At 120 min the data are behind: obs_phos7 is −2.0σ, obs_phos8 −2.3σ (0 measured, 0.088 simulated), obs_phos2 +1.5σ and obs_phos1 +0.7σ, and the mean count is 4.13 measured against 4.32. Each spectrum has its own free gain, so only shape is seen. Along M5's trajectory, shape is set by how far the reaction has run, and a constant-activity kinase fixes the 2-h/1-h ratio of that progress at 2; the data want less. Read through the mean count, the data look first-order between 1 h and 2 h: the 1-h rate (0.0062/min per site) predicts 4.20 at 2 h against 4.13 measured. M5 gets its 1-h breadth from count acceleration (cp 1.59), and that acceleration carries the 2-h spectrum past the data. The data therefore ask for broadening without mean acceleration. That is the signature of a brake that grows as the reaction proceeds, acting together with the coupling.\n\nWHAT WAS NEVER VARIED. Every candidate varied the per-step rate law. None varied the kinase: it was always constant and uninhibited, with mass-action kinetics. The interpretation set global effects aside because they cannot by themselves make a non-binomial shape. That is true. But on top of M5's coupling, a global brake changes the 1-h versus 2-h relation, which is exactly where M5 misses. The lab note states the kinase is not consumed and its amount is constant. So the brake is proposed as product occupancy: phosphate load, equal to ADP produced, sequesters free P-TEFb reversibly while total kinase stays conserved. Two variants are not proposed: kinase activity loss (the lab note rules it out) and substrate saturation of the kinase (it accelerates the late reaction, the opposite of what the residuals ask). This axis also bears on the intent. If cp moves toward 1 once the brake is on, part of the count-cooperativity evidence was compensating for timing.\n\nINTERPRETER'S HYPOTHESES.\n- #3 (processivity on top of coupling) is taken up as axis 2. The intent requires the distributive call to be tested, and so far it holds only against processivity alone (M4).\n- #1 is taken up through its timing part. The per-step version is left for construction: a count-only candidate with a flexible step-rate profile (rise, then brake for the last step), which was the interpreter's single move. It rewrites the J/Q rate laws, whose text is not in this payload. An axis would have to guess the current lines and would not nest. Until that candidate is fitted, an immediate-neighbour effect is not established.\n- #2 (static substrate heterogeneity) is also left for construction. It needs a second substrate chain plus observables that sum both chains, and one axis cannot carry an antimony patch and an assembly patch together. The complete 16-h spectrum (obs_phos7 at 960 min within 0.12σ under M5) also requires any slow subpopulation to finish within 16 h. That caps how much it can broaden the 1-h spectrum.\n- #4 (observation layer) is not testable here and is listed under beyond_this_data. The 19 exact zeros behave as non-detections and inflate the AIC margins, but no assembly patch expresses censoring.\n\nOTHER CHECKS.\n- No parameter is at or near a bound, and K_ATP is fixed at 50 µM. No axis releases a pinned parameter.\n- No replicate floor exists, so absolute adequacy cannot be judged.\n- Both axes of attempt 1 moved substrate between states outside the selected model's own transitions and drove states negative. They are dropped, not repaired. Neither new axis moves substrate mass: axis 1 moves only kinase between its free and product-occupied forms, and axis 2 frees the model's own Jp jump strength.",
 "axes": [
  {
   "id": "product_load_inhibition",
   "question": "Does the kinase slow as phosphate product accumulates? That would make the second hour slower relative to the first than a constant-activity kinase allows, on top of M5's count and neighbour coupling.",
   "origin": "residual",
   "default": "off",
   "priority": 1,
   "priority_reason": "One mechanism addresses all four largest M5 residuals together (phos5/phos6 at 1 h, phos7/phos8 at 2 h), and it tests whether cp is partly a timing artefact.",
   "on_antimony_patch": {
    "append": [
     "species PTEFb_I in vial;",
     "PTEFb_I = 0;",
     "R_PI_on: PTEFb -> PTEFb_I; vial * kon_I * PTEFb * (CTD_1 + 2*CTD_2 + 3*CTD_3 + 4*CTD_4 + 5*CTD_5 + 6*CTD_6 + 7*CTD_7 + 8*CTD_8);",
     "R_PI_off: PTEFb_I -> PTEFb; vial * koff_I * PTEFb_I;",
     "kon_I = 0.001;",
     "koff_I = 1;"
    ]
   },
   "adds_parameters": [
    {
     "id": "kon_I",
     "nominal_value": 0.001,
     "unit": "1/(uM*min)",
     "lb": 1e-07,
     "ub": 0.1,
     "evidence_tier": "to_be_estimated",
     "source": "residual: M5 too slow at 60 min and too fast at 120 min (mean count 2.33 vs 2.48, 4.32 vs 4.13)",
     "estimate": true,
     "neutral_value": 0.0,
     "denotes": "rate at which the phosphate load (Σ n·CTD_n, µM, equal to ADP produced) occupies free P-TEFb; with koff_I it sets K_I = koff_I/kon_I (0 = no product inhibition)"
    },
    {
     "id": "koff_I",
     "nominal_value": 1.0,
     "unit": "1/min",
     "lb": 0.01,
     "ub": 100.0,
     "evidence_tier": "to_be_estimated",
     "source": "fixed fast relative to the 60-min sampling so that only K_I = koff_I/kon_I is seen (general-dynamics #7)",
     "estimate": false,
     "denotes": "release rate of product-occupied kinase; no off-state of its own, since kon_I = 0 removes the term"
    }
   ],
   "rationale": "Residual origin. With one free gain per spectrum, the data see only the shape at 60 and 120 min. Along M5's trajectory that shape is set by how far the reaction has run. M5 is too slow in the first hour (60 min: obs_phos5 +2.6σ, obs_phos6 +2.0σ, obs_phos0 −1.6σ) and too fast in the second (120 min: obs_phos7 −2.0σ, obs_phos8 −2.3σ, obs_phos2 +1.5σ). Every candidate assumed a constant, uninhibited kinase, so this part of the model was never varied. The lab note fixes the kinase as not consumed and constant in amount. The brake is therefore written as reversible product occupancy, with total kinase PTEFb + PTEFb_I conserved. The existing rate laws see free PTEFb, so every modification step, count-lumped or positional, is slowed by the same factor 1/(1 + load/K_I), and no substrate mass moves. The load term reads Σ n·CTD_n, which equals ADP produced, so ADP and phosphorylated CTD are not told apart (beyond_this_data). In the on-state, the declared constant 'PTEFb' denotes free kinase and will drift; the conserved quantity is PTEFb + PTEFb_I. Substrate saturation of the kinase (the same occupancy idea with unmodified sites) would speed up the late reaction, the opposite of what the residuals ask, so it is not proposed.",
   "discriminating_evidence": "cond_invitro_PTEFb_CTD8, obs_phos5 and obs_phos6 at 60 min (scale sc_ctd_ms_t60) and obs_phos7 and obs_phos8 at 120 min (scale sc_ctd_ms_t120). If the axis is right, these four residuals (+2.6, +2.0, −2.0, −2.3σ) shrink together, obs_phos2 at 120 min (+1.5σ) and obs_phos0 at 60 min (−1.6σ) follow, and sigma_ctd_ms falls below 1.01. The 960-min spectrum must stay complete (obs_phos7 at 960 min within noise); a gain that grows that residual is evidence against. If cp moves toward 1 with the brake on, part of the count-cooperativity evidence was a timing effect; if cp and nb hold, the coupling is robust to it."
  },
  {
   "id": "processive_with_coupling",
   "question": "Once count and neighbour coupling are present, does a processive component (several repeats modified per kinase encounter) still improve the fit, or does the distributive call hold?",
   "origin": "residual",
   "default": "off",
   "priority": 2,
   "priority_reason": "The intent requires testing the by-eye distributive call, and processivity has only been tested without coupling.",
   "on_antimony_patch": {
    "append": [
     "q_proc = 0;"
    ]
   },
   "adds_parameters": [
    {
     "id": "q_proc",
     "nominal_value": 0.2,
     "unit": "dimensionless",
     "lb": 0.0,
     "ub": 0.9,
     "evidence_tier": "to_be_estimated",
     "source": "existing parameter of the selected model, held at 0 in M5; M4_processive estimated 0.212 without coupling",
     "estimate": true,
     "neutral_value": 0.0,
     "denotes": "strength of the selected model's processive jump reactions Jp* as already defined there (0 = purely distributive)"
    }
   ],
   "rationale": "Residual support, intent-driven. Processivity was fitted only without coupling (M4_processive, q_proc 0.212, ΔAIC 18.5), so 'distributive' currently holds only against processivity alone. M4 is the best candidate on the 1-h upper tail, where M5 misses most: rmse for obs_phos4/5/6 at 60 min is 0.021/0.042/0.021 against M5's 0.048/0.103/0.082. M4 fails mainly at the top (0.145 predicted for phos8 at 2 h, 3% left at seven at 16 h), and M5's coupling handles that. The axis estimates the selected model's own processive-jump strength q_proc (reactions Jp0_2 to Jp6_2) alongside cp and nb. The append only restates the neutral value; the parameter table carries the switch, and no new symbol is added. Caveat: the Jp reactions act on counts. If they are not consistent with the configuration states in the selected model's positional representation, the ladder will reject this axis, and a positional processive candidate must then be built at construction.",
   "discriminating_evidence": "cond_invitro_PTEFb_CTD8. With the axis on, obs_phos4, obs_phos5 and obs_phos6 at 60 min (+1.2, +2.6, +2.0σ under M5) must move toward the data without worsening obs_phos8 at 120 min (−2.3σ, measured 0) or obs_phos7 at 960 min (measured 0). If q_proc is estimated near 0 and the likelihood gains less than about 1 log unit, the distributive call is upheld against processivity combined with coupling. If q_proc is clearly above 0 and the 1-h upper tail is repaired, the by-eye distributive conclusion is not supported."
  }
 ],
 "beyond_this_data": [
  {
   "mechanism": "An immediate-neighbour effect as such (modifying repeat i changes the rate at i±1), as distinct from a count-dependent step rate whose profile rises through the mid-counts and brakes near the end",
   "why_not_separable": "MS resolves only the count, so the neighbour term reaches the data only through the count distribution. Its estimate crosses neutral between models (nb 1.81 in M3, 0.31 in M5), which suggests it is acting as a shape term for the step-rate profile. With four time points, no replicates and nine peaks per spectrum, a count-only profile with as many parameters can absorb the same imprint. A count-only flexible-profile candidate should still be fitted at construction, but even a tie would leave the question open.",
   "experiment": "Use a position-resolved readout at 1 h and 2 h: cleave between repeats (or use middle-down MS with ETD) to localise each phosphate. Alternatively, make one internal repeat unmodifiable (S2A/S5A at repeat 4). A neighbour effect changes the rates at repeats 3 and 5 specifically; a count effect changes every repeat equally per mark."
  },
  {
   "mechanism": "A phosphorylation-count-dependent MS ionisation and detection response",
   "why_not_separable": "Each spectrum has one free gain, and the 0-h and 16-h spectra each contain a single species. Per-count response factors are therefore confounded with cp, nb and the kinetics. A single factor on phos8 alone would simply absorb the one informative cell (phos8 at 2 h).",
   "experiment": "Calibrate with defined mixtures of synthetic or enzymatically completed phospho-isoforms (for example, known ratios of 0P and 8P CTD) in the same injection, or spike a known amount of 8P standard into the 2-h sample."
  },
  {
   "mechanism": "Loss of kinase activity during the incubation, rather than product inhibition, as the cause of the slower second hour",
   "why_not_separable": "It would be separated from M5 only by the same timing signal the product-inhibition axis uses. With one condition sampled at 0, 1, 2 and 16 h, a time-dependent loss and a load-dependent brake both just slow the second hour relative to the first. The lab note states the kinase is unchanged, so it is not proposed as a competing axis.",
   "experiment": "Add fresh P-TEFb at 2 h (activity loss predicts a burst; inhibition by product does not). Alternatively, pre-incubate the kinase with ATP and no substrate for 2 h before starting the reaction."
  },
  {
   "mechanism": "Inhibition by phosphorylated CTD, as opposed to ADP, as the product that occupies the kinase",
   "why_not_separable": "In this assay each phosphate added produces one ADP, so both inhibitors equal Σ n·CTD_n at every time point.",
   "experiment": "Spike ADP at t = 0, or run with an ATP-regenerating system (pyruvate kinase with PEP) that keeps ADP near zero. Separately, add pre-phosphorylated CTD at t = 0."
  },
  {
   "mechanism": "Genuine processivity (several repeats per binding event), as opposed to distributive release followed by rapid rebinding to the same molecule",
   "why_not_separable": "Both produce clustered modification events. A count-level jump term cannot tell them apart at a single kinase and substrate concentration with no chase.",
   "experiment": "Run a substrate-trap or dilution chase: add a 10-fold excess of unlabelled CTD, or vary the kinase concentration at fixed substrate, and compare count distributions at matched mean. Processive runs are insensitive to the trap; rebinding-driven clustering is not."
  }
 ],
 "untested_axes_addressed": [],
 "stop_instead": false
}
````
