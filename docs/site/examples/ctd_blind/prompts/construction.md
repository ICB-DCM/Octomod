# Prompt · `construction` (round 0)

The **construction** agent builds the base model (S1). Below is the exact prompt it was sent in this run (55,857 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Construction: build the mechanistic model the rest of the run fits

You build the species network, a simulable Antimony source, the parameter table and a build report with one entry
per modelling decision. A supplied network is translated faithfully, not reinvented.

## What you receive
`intent`, `experiment_description` (the lab note), `domain_packs` (the reference layer for domain detail) and, with
literature, `retrieved_evidence`: claims tagged `origin: human` (`lit_k`, staged by the problem's owner) or `origin:
research` (`res_k`). When the round already holds data, `data_phenomenology`: the curves in words (shape; when they
peak, return or plateau, to one significant figure; level against control; monotonicity in dose), held-out
conditions left out. In the first round they may come from the raw data files, before extraction (`source: raw
files`, named by the files' own columns), with the same rule that values are withheld. Shape and timescale are shown
because a modeller reads them off a plot before drawing a network; values are withheld because a network drawn to
numbers is a fit, not a hypothesis. Sometimes `supplied_network`, `revision_directive`, `minimal_repair` (change only
what the failure names), `instruction_mechanism_discrimination`, or `essential_reactions` with `support_floor`,
`knowledge_summary` and `known_facts` (below).

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
Required: `network`, `antimony`, `parameters`, `build_report`, `consulted_sources`, `entity_glossary`. Optional:
`model_space`, `recommended_tier`, `basal_state`, `declared_constants` (quantities the lab note calls constant, with
the quoted sentence; the engine measures their drift as a flag, not a constraint) and `missing` (below). In a
discrimination round you write the base only: the expansion agent writes the candidates. Shape: Output contract. Bounds are linear-scale; the engine owns log scaling. Each
decision carries `alternatives_considered`, an honest `evidence_tier`, a defensible `confidence`, and
`user_decision_required` with its `question` written out. A failed check comes back with its words, within a retry
budget, then goes to the human.

## Rules that get your reply refused
- It builds: every species has a compartment and an initial value, every parameter a nominal value, every reaction a
  kinetic law, every symbol declared, every participant a species. Explicit compartment, named reactions
  (`J1: A -> B; k1*A`), species and initial values before parameters.
- It integrates from t0 to t_end at the nominals and at sampled corners of the bounds box, no state going negative:
  a rate law that survives only the vector you tried fails.
- Every estimated parameter is read by the model; one that nothing reads only adds a flat direction.
- Every species has a glossary entry, because the assembly agents map readouts onto a model they did not build.
- Never remove or rename away an entity the user named without asking: removal is a `user_decision_required`
  question, and a renamed id keeps the user's term as its `name`.
- An axis patch applies to your own model (`replace_reaction` with your exact reaction id and the whole new line, or
  `append`) and declares every new symbol in `adds_parameters` with a nominal and bounds; one that does not match is
  dropped with its axis.
- Never seek, open or rely on the target model's own publication: rebuilding it from its paper measures retrieval,
  not construction. List every source you consulted.

## How to judge
**Scope.** The smallest network that carries every perturbation to every required readout; that path is mandatory,
a full pathway diagram is not. Every entity is motivated by the intent, the lab note or the data. Report a supplied
network's gaps in the build report; never repair them silently.

**Kinetics.** Mass action for elementary steps. Michaelis–Menten is the standard choice for an enzyme-catalysed step
when a quasi-steady state holds at the declared timescale: decide it and say why (literature Km, kcat where given).
Name any other form (Hill, quasi-steady-state elimination, lumping) with the timescale ratio that justifies it, not
the word "fast". Ask the user only when the choice is load-bearing and undecidable from the description. A
transient is a state with first-order decay; `time` only for a declared external forcing.

**Values and bounds.** Nominals from literature (`direct`, or `transferred` naming the species, cell-type or
temperature mismatch), else order-of-magnitude plausibility (`default`), else `to_be_estimated`. Bounds are a prior,
typically 2–4 decades: too narrow parks parameters on bounds and strangles multistart, ten decades wastes starts in
stiff corners. Wide where the nominal is a guess, narrow where it is measured.

**Evidence.** A rationale is the argument (system, data, timescale), never a restatement. Ground it in a resolvable
source (DOI, PMID, ISBN) with a locator and what the source actually says; general knowledge is called that and stays
`default`; never fabricate. `direct` means this organism, this context, a nameable source; an unsourced `direct` or
`transferred` is demoted to `default` anyway. `origin` (user-provided, database-supported, literature-supported,
inferred, assumed) says where a claim came from, the tier how strongly it carries. An `origin: human` item is the
literature the owner expects the model to build on: cite it (`lit_1`, or its `source` verbatim) where it settles a
decision, and say so where you depart from it; `origin: research` carries no such expectation. You see claims, not
documents: attribute nothing beyond `supports` and `quote`. The tier follows what a source shows for this system, so
a paper on another cell type is `transferred`, whoever supplied it.

**The data's shape** is what a mechanism must be able to produce, not a curve to copy: argue the network from biology
and let the fit decide.

**Groups measured as conditions of one model** (populations, tissues, strains): the lab note says what differs
(abundances, basal levels, feedback capacity) and what is shared chemistry (catalytic constants, the measurement
scale). Write it into `varies_by` (`["population"]` per level, `[]` shared); the encoding agent copies exactly those
and reads no prose. All empty means all shared; say why if you leave a difference the lab note names undeclared.

**The basal state.** Say whether the initial values are the unstimulated steady state and whether measured
conditions should be simulated to it first: suggest it for a balance you cannot write down (synthesis against decay,
a cycle whose resting split depends on estimated rates, an inhibitor with a basal level), not when the initial values
are that state by construction (every stimulus-driven form starts at zero and nothing moves without the stimulus).
The encoding agent decides per condition, beside the protocol; yours is a suggestion with a reason.

**The glossary** says what ids and rate laws cannot, one or two lines each: which states a "total" readout sums, that
`Y_a` is every active form because two inactivation routes were lumped, that `u` is set per condition, which totals
are normalised to 1.

**The observation model is not yours.** The Antimony carries the dynamical system and nothing else. A response
factor per state, a gain per acquisition, an offset, a background, a detection floor, a normalisation, and any
quantity that exists only because of the assay belong to the observation model, which the observation-model agent
writes as the PEtab observable formula on your species. An assignment rule is for a quantity the dynamics need, a
derived rate or a total that enters a rate law. A rule that re-expresses a readout with a response factor declares
the observation model twice and parks a measurement hypothesis where no observation axis can reach it. Say in the
glossary which states a readout sums and let the observation model write the sum; a response or detection
hypothesis worth testing is an observation-layer axis (below), not a model parameter.

**What goes to the human.** `user_decision_required` is for a decision the user owns (is this regulator in scope, is
this lumping acceptable) with low confidence and a bearing on a required prediction, not for every doubt. A question
worth asking is usually worth testing, so it normally becomes an axis too.

**The model space.** An axis is one mechanism, on or off, switchable alone on the base; the engine fits it beside the
base and a criterion chooses. `default` is what your base encodes, usually `off`: the base is the conservative model.
An axis is not a hedge: commit to the base and name the specific alternative to test. `discriminating_evidence` names
the observable and condition where on and off differ; if none does, leave the axis out and say so, since a mechanism
the data cannot see costs identifiability and buys nothing. One hypothesis may take a list of patches (all or none);
a new state is an `append` block declaring the species, its initial value and reactions. Put a strength in front of
each added term and declare the `neutral_value` that turns it off (`k*A/(1 + beta*A)`, `beta` at 0, not
`k*A/(1 + A/Km)`). Rank axes by `priority` (1 = the answer that changes most for the question; one line why) and
set `recommended_tier`: `base` (one model: get it working, read its residuals, let expansion propose from evidence),
`top<k>` or `all`. We do not run models because we can: recommend the smallest tier you can argue is informative,
in one line, and keep axes to the few that matter. The human sees each tier's model count and pays for each fit;
when `search.max_models` bites, the lowest-priority axes go, so rank honestly.

**Observation-layer axes.** The observation model is a hypothesis too. Unsure how a readout relates to the model (a
background on one assay, error growing with signal, a readout summing states you split, an inhibitor entering
through another parameter)? Declare an `on_assembly_patch` axis — `add_offset`, `remove_scaling`, `change_scaling`,
`change_noise_model`, `change_observable_formula`, or `change_condition` (which parameter a perturbation
enters, never a measured factor's value) — naming observables and conditions by data label, since no estimation
problem exists yet. Transformation axes are refused until the criterion can compare scales. Cite observation-layer
evidence (which readout, at which signal level or condition), never "the fit might improve": shape in time or
condition points at structure, error growing with signal at observation. One observation axis per observable.

## The knowledge module's reactions (`essential_reactions`)
When the knowledge module ran before the intent was frozen, `essential_reactions` is what the literature and
databases describe for this system, each entry with its `origin` (`human`: the intent requires it; `knowledge`: the
module's survey; `search`: a search the engine ran for a conversion you named missing), its `grade` (a band from a
declared rule table, with the source that earned it; never a probability) and the evidence that counts for it.
`support_floor` says in words what a grade had to reach to be in the set; `knowledge_summary` is what is known about
the system, its scope and what is unknown; `known_facts` are the abundances, rates, timescales and responses the
module found for construction. `grounding_instruction` says which of two modes the run is in.

**Advisory (the default).** The set is prior knowledge, not a fence, and so is `prior_reactions`, the whole dossier:
its entries outside the set are candidates you may use where the question needs them. Build the model the question and the data need
from the biology, using the entries where they apply and their species ids verbatim where a reaction is taken from
one; implement every `required: true` entry. Add any reaction the model needs — a mechanical or observation process
(a drift, a background), one copy of a reaction per population or compartment, a mechanism nothing here describes:
each one the dossier does not back is shown to the person with your rationale, so the build report says why it is
there. `missing` is not needed.

**Strict.** The base is EXACTLY the set: implement every entry, in a direction its rate law carries, with its species
ids verbatim, and add no conversion the set lacks. When the model cannot be complete without one, build the best
model the set allows and name each missing conversion in `missing`, `{equation, why}`: the engine searches the
literature for it, admits what reaches the support floor into the set, and asks you again with it
(`engine_feedback`); a conversion you write without naming it fails `model_essential_reactions`.

In both modes:
- Kinetics, modifiers, parameters, initial values and the glossary are yours.
- A participant you hold as a parameter (a dose, a clamped input) keeps the entry's id as the parameter's id: the
  engine then compares the entry without it.
- Mark every quantity the conditions set (a dose, an inhibitor level, a genotype switch) `set_per_condition: true`
  on its `parameters`, `network.species` or glossary entry: `model_connected` checks that each reaches a required
  entity, and that every piece of the species graph holds one, so no part of the model is unobserved.
- A parameter value taken from a fact carries `source: "knowledge:<fact id>"`; a decision that rests on an entry
  cites its evidence ids (`req_1.e1`, `rx_2.e1`) in its `evidence`.
- Every reaction you write is annotated afterwards — user-provided, database-supported, literature-supported or
  inferred, with the origin of the entry it implements — and the card shows it to the person.

## Mistakes we have seen
- A rate law naming an undeclared symbol, or a participant that is not a species.
- Two ids for one entity (`ERK`, `MAPK1`) as two species: pick one, record the synonym.
- An accidental moiety conservation that pins a state so it cannot respond.
- A denominator that reaches zero inside the bounds box.
- A correlational finding recorded as mechanism at `direct`.
- Decorative entries ("chosen based on literature", no locator, no alternative): the verifier reads the report, not
  your intentions.
- A regulator invented so a shape comes out right; mechanism the data demand is a later revision, argued from
  residuals.
- A group split left in glossary prose: the catalytic constants were copied per group too, unidentifiable next to
  the per-group abundances, answering "same chemistry?" by construction.


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
## instruction_mechanism_discrimination
The inference target is mechanism discrimination, built in two steps. THIS call writes the BASE only: the one structure every candidate shares. Build each feature the comparison tests into the base as a switch the next step can set — a parameter whose base value turns the feature off (for example a competition switch at 0) — wherever that is possible, and say in the build report which parameter switches which feature. The engine tests your base on its own; a second call then writes the 2-5 candidates as differences from it, and the engine builds each one. Do not privilege one mechanism; the data decides.

# Output contract
{
  "network": {"species": [{"id": "...", "name": "...", "compartment": "...", "set_per_condition": false}],
              "interactions": [{"id": "...", "type": "phosphorylation|binding|conversion|synthesis|degradation|regulation",
                                 "participants": [{"species": "...", "role": "substrate|product|modifier", "stoichiometry": 1}],
                                 "evidence_tier": "direct|transferred|default|to_be_estimated", "note": "..."}]},
  "antimony": "model <name>\n  ...full antimony source...\nend",
  "parameters": [{"id": "...", "nominal_value": 0.0, "unit": "...", "evidence_tier": "direct|transferred|default|to_be_estimated",
                   "source": "...", "estimate": true, "lb": 0.0, "ub": 0.0, "varies_by": [], "set_per_condition": false}],
  "missing": [],
  "build_report": {"decisions": [{"decision": "...",
                                    "rationale": "the argument for THIS choice, not a restatement of it",
                                    "alternatives_considered": "...",
                                    "evidence": [{"source": "lab_note|literature|database|general_knowledge", "locator": "REQUIRED for lab_note and literature — where exactly: quote the phrase from the note, or give DOI/PMID + figure/table/section", "supports": "what it actually says", "origin": "user-provided|database-supported|literature-supported|inferred|assumed"}],
                                    "evidence_tier": "direct|transferred|default|to_be_estimated",
                                    "confidence": "high|medium|low", "user_decision_required": false, "question": ""}]},
  "declared_constants": [{"expression": "X + Y", "tolerance": 0.1, "locator": "quote the sentence that says so", "why": "what it is asserting"}],
  "basal_state": {"initial_values_are_steady_state": true, "suggest_preequilibration": false,
                  "note": "one or two sentences: what the unstimulated state is and how the initial values relate to it"},
  "consulted_sources": ["..."],
  "entity_glossary": {"species": [{"id": "Y_a", "denotes": "ALL active forms of Y; the two inactivation routes are lumped into one",
                                    "unit_convention": "fraction of total Y, total normalised to 1", "lump_membership": "Y_a covers the singly- and doubly-modified forms"}],
                      "parameters": [{"id": "u", "role": "stimulus level, set per condition", "convention": "relative units against the standard stock", "set_per_condition": true}]},
  "recommended_tier": {"tier": "base|top1|top2|...|all", "reasoning": "one line: how many models you consider GENUINELY necessary, and why"},
  "model_space": [{"id": "short_slug", "question": "the structural question this axis settles",
                    "default": "off|on",
                    "priority": 1, "priority_reason": "one line: why this axis is the most load-bearing (1 = most)",
                    "on_antimony_patch": {"replace_reaction": "R3", "with": "R3: X -> Z; cell * (k1*Y_a + k2*X) * X;"},
                    "adds_parameters": [{"id": "k2", "nominal_value": 0.0, "unit": "...", "lb": 0.0, "ub": 0.0, "evidence_tier": "to_be_estimated", "source": "...", "estimate": true, "denotes": "rate of the second route this axis adds"}],
                    "rationale": "why this mechanism is plausible at all",
                    "discriminating_evidence": "which observable, in which condition, separates on from off"},
                   {"id": "second_slug", "question": "an OBSERVATION-layer question: does the Z readout carry a nonzero background?",
                    "default": "off", "priority": 2, "priority_reason": "one line",
                    "on_assembly_patch": {"add_offset": {"observable_label": "Z"}},
                    "adds_parameters": [],
                    "rationale": "why this alternative observation model is a hypothesis about the MEASUREMENT, not a fit device",
                    "discriminating_evidence": "the observation-layer evidence: which readout, at which signal level, shows the defect"}]
}
NOTE on "basal_state": OPTIONAL. Your view of the model's starting point, for
the condition-encoding agent, which decides pre-equilibration per measured
condition: are the initial values you wrote the unstimulated steady state
(the cells before the stimulus), and should the measured conditions be
simulated to that steady state first? Suggest it when the basal state is a
balance you cannot write down as initial values (synthesis against decay, a
cycle whose resting split depends on estimated rates). A suggestion, not a
decision.

NOTE on mechanism discrimination: you write the BASE only; the expansion
agent writes the candidates, each as a declared difference from your base. A
reply that carries candidates is refused.

NOTE on "retrieved_evidence" when present: a list of evidence items, each
with `id`, `source`, `title`, `year`, `locator`, `supports`, `quote`, `url` and an
`origin`. `origin: human` = the person who staged this problem already has this
source and wrote down what it says — it is the literature they expect the model
to build on, so use it and cite it. `origin: research` = the online retrieval
role found it. Cite either kind in a decision's `evidence` entries by its `id`
(`lit_1`) or its `source` string verbatim, with `origin: literature-supported`.
The evidence TIER still follows what the source establishes for THIS system, not
who handed it to you. You never see the document itself; `supports` and `quote`
are what reach you, and a claim the item does not make must not be attributed to it.

NOTE on "essential_reactions" when present: the reactions the knowledge module
(run before the intent was frozen) and the engine's searches describe for this
system — each entry with its `origin` (`human` = the intent requires it,
`knowledge` = the module's survey, `search` = a targeted search that answered a
conversion you named missing), its `grade` (a band from a declared rule table,
with the source that earned it in `because`; never a probability) and the
evidence that counts for it. `support_floor` says in words what a grade had to
reach to be in the set; `knowledge_summary` is what is known about the system,
its scope and what is unknown; `grounding_instruction` says which of two modes
the run is in. ADVISORY (the default): the set is prior knowledge, not a fence —
build the model the question and the data need, use the entries where they
apply with their species ids verbatim, implement every `required: true` entry,
and add any reaction the model needs (a drift, a background, one copy per
population, a mechanism nothing describes); every reaction is annotated and each
one the dossier does not back is shown to the person with your rationale.
In advisory mode `prior_reactions` is the whole dossier, graded, essential or
not: the entries outside the set are candidates to use where the question needs
them. STRICT: the base is EXACTLY the set — implement every entry in a direction
its rate law carries, with its species ids verbatim, and add no conversion it
lacks.
In both, kinetics, modifiers, parameters, initial values and the glossary are
yours; a participant held as a parameter (a dose) keeps the entry's id as the
parameter's id; where a decision rests on an entry, cite its evidence ids
(`req_1.e1`) in that decision's `evidence`.
NOTE on "missing": OPTIONAL, and read only in strict mode. When the model cannot
be complete without a conversion the set lacks, build the best model the set
allows and name each such conversion here, `{equation, why}`, species ids
verbatim: the engine searches the literature for it, admits what reaches the
support floor into the set, and asks you again with it (`engine_feedback`). A
conversion you write without naming it here fails `model_essential_reactions`.
NOTE on "set_per_condition": OPTIONAL flag on a `parameters` entry, a
`network.species` entry or a glossary entry: true on every quantity the
experimental conditions set (a dose, an inhibitor level, a genotype switch). The
engine checks that each one reaches a required entity through the reaction
graph (`model_connected`).

NOTE on "entity_glossary" (REQUIRED): what your model MEANS, for the agents that
map readouts onto it without having built it. EVERY species gets an entry: what
it denotes physically, its unit/scale convention, and which real states it lumps
("Y_a represents ALL active forms of Y; the two inactivation routes are
lumped into one"). Every
parameter the assembly must understand (dose parameters set per condition,
inhibitor switches, totals) gets a role and convention. A total readout is a sum
over exactly the states YOU chose to represent — the glossary is where you say
which. Missing species entries fail a deterministic check and come back to you.

NOTE on "priority" and "recommended_tier": you price your own confidence. Rank
the axes (1 = the one whose answer changes the most; one line each) and say in
recommended_tier how many models you consider genuinely necessary — "base"
(one model: get it working, read its fits and residuals first, let the
expansion loop propose from evidence), "top<k>" (the k highest-priority axes,
each fitted on its own against the base: k+1 models; every on/off combination,
2^k models, only when the human asks for it) or "all". We do not run models
because we can: recommend the
smallest tier you can argue is informative. The human sees every tier with its
model count and decides.

NOTE on "model_space" patch kinds: an axis carries EITHER on_antimony_patch
(a structural alternative: replace one reaction line, or append lines; one
hypothesis that needs several edits, e.g. removing several reactions together,
is a LIST of such patches, applied in order, all or nothing) OR
on_assembly_patch (an observation-layer alternative), never both. A NEW STATE
is added with an `append` block that declares the species, its initial value
and its reactions — `replace_reaction` alone cannot introduce a species, and a
patch whose rate law names an undeclared symbol is dropped. A dropped patch
does not mean a state cannot be added: declare it in the same `append` block
and the axis stands. Observation
kinds: {"change_observable_formula": {"observable_label", "new_formula"}},
{"change_noise_model": {"observable_label", "new_distribution": "normal|laplace"}},
{"change_noise_model": {"observable_label", "new_per": "condition"}} (one sigma
per treatment arm for that observable — the arm-specific noise alternative;
the observable_label is REQUIRED, an axis without it is dropped)
or {"change_noise_model": {"observable_label", "new_formula": "sigma_obs_x * <this observable's signal expression>"}}
(proportional noise), {"add_offset": {"observable_label"}}, {"remove_scaling":
{"observable_label"}}, {"change_scaling": {"observable_label" | "observable_ids": [...],
"per": "observable|timepoint|condition", "shared_across_observables": false | "<group>",
"pin_first_to_one": false}} (one scale factor per measurement time or per condition,
optionally one parameter set shared by a group of readouts),
{"change_condition": {"condition_label",
"overrides": {"<model parameter>": value}}} — the last only for WHICH parameter a
perturbation enters (hypothesis class); changing a measured factor's value or
pre-equilibration reinterprets the data and is refused. Name observables and
conditions by their DATA labels (the measured quantity / condition as the lab note
names them) — no estimation problem exists yet when you write this. One
observation axis per observable. Transformation axes (lin/log) are refused until
criterion comparability exists. Observation axes are few and evidence-motivated:
cite the observation-layer evidence, not general dissatisfaction with the fit.

NOTE on "model_space": the set of structural choices you are NOT sure about,
expressed as independently toggleable axes on top of the base model. Every
`user_decision_required` decision you raise SHOULD normally appear here too —
a question worth asking the human is a question worth testing against the data.
Each axis must be switchable on its own: give the exact Antimony patch its
"on" state applies and the parameters that come with it. `default` says which
state the base `antimony` above encodes. An axis whose two states cannot be
told apart by any measurement in the data is not an axis — say so in
`discriminating_evidence` and leave it out.
Explicit time (`time`, `exp` and the standard functions) is accepted in a patch,
but PREFER to write a transient as an additional state with an initial value and
first-order decay: a state is a removable mechanism the fit can test (its rate,
its neutral value); an explicit function of time is a curve. Use `time` only
for a genuinely external, declared forcing such as a dosing schedule.

NOTE on "neutral_value" (STRONGLY PREFERRED where it is honest): for each entry
of `adds_parameters`, give the value at which that parameter makes the axis's
term VANISH, recovering the base model exactly. An added route has
`neutral_value: 0`. A saturation or feedback should be WRITTEN so that a finite
value turns it off — `k*A/(1 + beta*A)` with `neutral_value: 0` for beta, not
`k*A/(1 + A/Km)`, whose off-state is Km at infinity and cannot be declared.
The scale and the bounds do NOT constrain this: a parameter estimated on log10
with `lb: 1e-5` can still be switched off at exactly 0, because the box
constrains estimation and a switched-off parameter is fixed, not estimated. The
one mechanical condition is that two axes replacing the SAME reaction can never
both be neutral, and neither can two axes that reuse one parameter id with
different off-states. Where you can declare it,
every candidate the axes make shares one compiled model and the candidates
are exactly nested; where you cannot, say nothing and each candidate is built on
its own, as before. Every declaration is CHECKED by simulation against the base
model, so a wrong one costs nothing but is recorded — do not guess one.
THE RULE, stated once: EVERY parameter an axis adds should carry `neutral_value`.
A parameter with no honest off-state of its own — a half-saturation `K` in
`k*A/(K + A)`, a Hill exponent — may omit it ONLY when another parameter of the
SAME axis switches the whole term off (`k` with `neutral_value: 0` makes `K`
irrelevant): the engine then fixes `K` at its nominal value in the off-state
candidates, estimates it in the on-state ones, and checks by simulation that the
term really is gone. An axis in which NO parameter declares a neutral value is
built as its own structure — one extra compile, and its candidates are not
exactly nested. Write the strength in front of the term and declare its zero.

NOTE on "known_facts" when present: what the knowledge module found, before the intent was frozen, that a model of this system needs beyond its reactions — each with an `id` (`fact_1`), a `kind`, a `statement` (a `value` and `unit` where it is quantitative), what it `applies_to`, its evidence and the grade the engine gave it (`not_applicable` when it was gathered offline). Only the facts meant for your role reach you. Use a fact where it applies instead of inventing the assumption, and where you depart from one, say why. A parameter whose value you take from a fact carries `source: "knowledge:<fact id>"` in `parameters`, and a decision that rests on one cites its id (`fact_2`) in its `evidence` entries.
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "network": {
  "species": [
   {
    "id": "CTD_0",
    "name": "CTD, 0 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_1",
    "name": "CTD, 1 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_2",
    "name": "CTD, 2 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_3",
    "name": "CTD, 3 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_4",
    "name": "CTD, 4 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_5",
    "name": "CTD, 5 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_6",
    "name": "CTD, 6 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_7",
    "name": "CTD, 7 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "CTD_8",
    "name": "CTD, 8 of 8 repeats phosphorylated",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "ATP",
    "name": "ATP",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "ADP",
    "name": "ADP",
    "compartment": "vial",
    "set_per_condition": false
   },
   {
    "id": "PTEFb",
    "name": "P-TEFb",
    "compartment": "vial",
    "set_per_condition": false
   }
  ],
  "interactions": [
   {
    "id": "J0",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_1",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter; reaction from the lab note, rate law default"
   },
   {
    "id": "J1",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_2",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter"
   },
   {
    "id": "J2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_2",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_3",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter"
   },
   {
    "id": "J3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_3",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_4",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter"
   },
   {
    "id": "J4",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_4",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_5",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter"
   },
   {
    "id": "J5",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_5",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_6",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter"
   },
   {
    "id": "J6",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_6",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter"
   },
   {
    "id": "J7",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_7",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "direct",
    "note": "single-repeat encounter; last repeat, no continuation possible"
   },
   {
    "id": "Jp0_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_2",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive encounter, off in base (q_proc = 0)"
   },
   {
    "id": "Jp0_3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 3
     },
     {
      "species": "CTD_3",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 3
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp0_4",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 4
     },
     {
      "species": "CTD_4",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 4
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp0_5",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 5
     },
     {
      "species": "CTD_5",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 5
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp0_6",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 6
     },
     {
      "species": "CTD_6",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 6
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp0_7",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 7
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 7
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp0_8",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_0",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 8
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 8
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   },
   {
    "id": "Jp1_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_3",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp1_3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 3
     },
     {
      "species": "CTD_4",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 3
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp1_4",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 4
     },
     {
      "species": "CTD_5",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 4
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp1_5",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 5
     },
     {
      "species": "CTD_6",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 5
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp1_6",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 6
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 6
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp1_7",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_1",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 7
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 7
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   },
   {
    "id": "Jp2_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_2",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_4",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp2_3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_2",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 3
     },
     {
      "species": "CTD_5",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 3
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp2_4",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_2",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 4
     },
     {
      "species": "CTD_6",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 4
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp2_5",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_2",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 5
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 5
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp2_6",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_2",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 6
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 6
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   },
   {
    "id": "Jp3_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_3",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_5",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp3_3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_3",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 3
     },
     {
      "species": "CTD_6",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 3
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp3_4",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_3",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 4
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 4
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp3_5",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_3",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 5
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 5
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   },
   {
    "id": "Jp4_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_4",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_6",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp4_3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_4",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 3
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 3
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp4_4",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_4",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 4
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 4
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   },
   {
    "id": "Jp5_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_5",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_7",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive, off in base"
   },
   {
    "id": "Jp5_3",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_5",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 3
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 3
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   },
   {
    "id": "Jp6_2",
    "type": "phosphorylation",
    "participants": [
     {
      "species": "CTD_6",
      "role": "substrate",
      "stoichiometry": 1
     },
     {
      "species": "ATP",
      "role": "substrate",
      "stoichiometry": 2
     },
     {
      "species": "CTD_8",
      "role": "product",
      "stoichiometry": 1
     },
     {
      "species": "ADP",
      "role": "product",
      "stoichiometry": 2
     },
     {
      "species": "PTEFb",
      "role": "modifier",
      "stoichiometry": 1
     }
    ],
    "evidence_tier": "to_be_estimated",
    "note": "processive run to completion, off in base"
   }
  ]
 },
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
 "build_report": {
  "decisions": [
   {
    "decision": "The base tracks how many of the 8 repeats each molecule carries (CTD_0..CTD_8), not which. It is the exact count lumping of the 256-configuration positional model whenever the per-repeat rate does not depend on the state of the immediate neighbours. The positional (neighbour) model is not written in this reply.",
    "rationale": "For every rate rule this base can switch on (independent repeats, count cooperativity cp^n, processive continuation that picks among the remaining unmodified repeats), all unmodified repeats of a molecule with n marks share one rate, so the 256 configurations are strongly lumpable by n and these 9 states reproduce the positional model's count distribution exactly. The 'nothing at all', 'cooperativity' and 'distributive vs processive' hypotheses therefore lose nothing by being counted. A nearest-neighbour effect is the one hypothesis that breaks the lumping, so it cannot be a switch on this base. Two previous replies to this brief failed the contract outright; a 1024-reaction hand enumeration, together with its 256-entry glossary and network, is not something this reply can carry reliably or check without execution. The next decision gives the exact rule so the positional model can be generated mechanically. A generator check comes free: at nb = 1 it must reproduce this base trajectory for trajectory.",
    "alternatives_considered": "Full 256-configuration model written out by hand as the base (the user's stated preference; not deliverable reliably here). Mirror-symmetry reduction to 136 orbits (exact, but still ~500 reactions with multiplicities and harder to audit). Pair or domain-count approximations (n, number of marked runs) were rejected because they are not exact, and the lab note asks that the question not be settled from counts alone.",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'Any model that simulates is acceptable, whether it tracks only how many repeats are modified or which repeats are modified (with eight repeats, 256 configurations).'",
      "supports": "a count-resolved model is an admissible description",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "'If a possibility can only be represented by tracking which repeats are modified, we would rather see that model fitted than the question settled by argument from the counts alone.'",
      "supports": "the neighbour hypothesis must be fitted as a positional model, not argued away",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "",
      "supports": "strong lumpability of a Markov chain: states may be aggregated exactly when every state in a block has the same total rate into each other block",
      "origin": "assumed"
     }
    ],
    "evidence_tier": "default",
    "confidence": "medium",
    "user_decision_required": true,
    "question": "The neighbour hypothesis needs the 256-configuration model. Option A: it is generated mechanically from the rule in this report, fitted as the neighbour candidate, and checked against this 9-state base, which is its exact nb = 1 lumping. Option B: you require the full hand-enumerated model as the base itself. Which do you want?"
   },
   {
    "decision": "Exact construction rule for the positional (neighbour) candidate, to be generated and not hand-written. Species C_b1b2b3b4b5b6b7b8 (b_i = 1 if repeat i, numbered from the N-terminus, is phosphorylated), C_00000000 = 100 uM, all others 0. For every configuration and every unmodified repeat i, one reaction to the configuration with b_i = 1, consuming one ATP and producing one ADP. Rate: vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m*C, where n = marks on the molecule and m = marked immediate neighbours of i (0 to 2; repeats 1 and 8 have one neighbour). New parameter nb, a fold change per marked neighbour: nominal and neutral value 1, bounds 0.01 to 100.",
    "rationale": "This is the minimal positional extension that separates 'a mark changes its neighbours' rate' (nb) from 'the rate depends on how many marks the molecule carries' (cp) and from neither (nb = cp = 1). It is 8*2^7 = 1024 reactions. Summing C over the C(8,n) configurations with n marks gives CTD_n, so readouts map onto it exactly as onto this base. nb < 1 (neighbour inhibition) jams molecules near 3 to 4 non-adjacent marks before slow filling, and that stall at intermediate counts between 2 h and 16 h is something cp alone cannot shape. nb > 1 gives nucleation-and-growth (bimodal 0-versus-high counts at 1 to 2 h), which cp > 1 and processivity also give. That is the likely indistinguishable set.",
    "alternatives_considered": "A directional neighbour effect (separate factors for N- and C-side neighbours) was not chosen: counts carry no positional information to separate the two directions, so it would add a flat direction. Pairwise or longer-range interactions were not chosen either: they are not the hypothesis named.",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'that the modification of one repeat changes the rate at which its immediate neighbours in the array are modified, as opposed to the rate depending only on how many repeats of the molecule are already modified (cooperativity between repeats ...), or on nothing at all'",
      "supports": "the three hypotheses to compare, with neighbours meaning immediate neighbours",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "'It does not resolve which repeats those are.'",
      "supports": "only counts are observed, so the positional model is observed through sums over configurations",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "'The simulator reserves the single letters x, k, p, y, w, h and t'",
      "supports": "naming: C_..., nb, cp avoid the reserved letters",
      "origin": "user-provided"
     }
    ],
    "evidence_tier": "to_be_estimated",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "Distributive single-repeat steps J0..J7. Each unmodified repeat is modified at kmod*PTEFb*ATP/(K_ATP + ATP), mass action in the substrate at constant enzyme, so a molecule with n marks advances at (8 - n) times that rate. The template is phosphorylation X -> X_p with the kinase as modifier. Irreversible: no reverse step and no phosphatase.",
    "rationale": "The assay is purified kinase, CTD and ATP with no phosphatase, so removal of phosphate is not modelled. The kinase is catalytic and constant, so its level enters as a fixed multiplier. Mass action in CTD assumes the kinase is far from saturated by substrate. Neither the enzyme concentration nor a CTD Km is given, so saturation cannot be decided from the note. If all unmodified repeats bind alike, saturation would only reparameterise time by a factor common to every reaction (the same sequence of distributions, a different clock). With three post-zero time points that clock change is largely absorbed by kmod and cp, so it is named unresolved rather than built in. With cp = 1 and q_proc = 0 the count distribution is binomial(8, 1 - exp(-r*t)): the independent-repeat ('nothing at all') hypothesis.",
    "alternatives_considered": "Michaelis-Menten in CTD with competition among all substrate forms (left out: time warp only, not identifiable here). Reversible steps (no phosphatase present).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'There is no transcription, no DNA, no polymerase — only a purified CTD substrate, purified kinase, and ATP in buffer.'",
      "supports": "no phosphatase, no other reactions",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "'Kinase: P-TEFb, catalytic. It is not consumed and its concentration does not change over the experiment.'",
      "supports": "enzyme enters as a constant modifier",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "",
      "supports": "mass action at constant enzyme is the low-saturation limit of Michaelis-Menten kinetics",
      "origin": "assumed"
     }
    ],
    "evidence_tier": "default",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "Count-cooperativity switch cp: the per-repeat rate of a molecule carrying n marks is multiplied by cp^n. cp = 1 (base) turns it off; cp > 1 is positive and cp < 1 negative cooperativity between repeats.",
    "rationale": "One parameter expresses 'the rate depends only on how many repeats are already modified' as a constant fold change per existing mark, the additive free-energy form. It is the most parsimonious count-dependent law the data can constrain with 9 peaks at 3 informative time points. A free factor per n (7 parameters) would not be identifiable. Bounds 0.2 to 5 are 1.4 decades on cp but compound to ~10 decades on the n = 7 step. Wider bounds put the solver in stiff corners without adding plausible behaviour.",
    "alternatives_considered": "A free rate per count n (unidentifiable). A saturating dependence on n (an extra shape parameter the data cannot see).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'the rate depending only on how many repeats of the molecule are already modified (cooperativity between repeats, which was also raised as a possibility to look at)'",
      "supports": "count-dependent rate is one of the hypotheses to test",
      "origin": "user-provided"
     }
    ],
    "evidence_tier": "to_be_estimated",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "Processivity switch q_proc on reactions Jp<n>_<j>. A binding event on a molecule with n marks starts at the same encounter rate as a distributive step. After each modification the kinase continues to another unmodified repeat with probability q_proc, else releases. The run is truncated only by running out of unmodified repeats (weights q^(j-1)(1-q), and q^(j-1) for the run that completes the molecule). q_proc = 0 (base) is strictly distributive.",
    "rationale": "Distributive versus processive is about how many modifications one binding event makes. The encounter-level jump n -> n+j with geometric run length is the standard count-level representation, and its weights sum to 1, so q_proc changes what an encounter does, not how often encounters happen. Strong processivity predicts early bimodality (CTD_0 plus high counts, depleted intermediates at 1 h). Its difference from cp > 1 is memory: under processivity a released molecule returns to the slow distributive pace, so long-lived intermediates persist to the 16 h point. Sliding processivity (running along to the next repeat, stopped by an already-modified repeat) depends on positions and only exists in the positional model. It is not exactly lumpable and is likely aliased with nb > 1.",
    "alternatives_considered": "An explicit enzyme-substrate complex per state (adds unknown enzyme concentration and koff, which the data cannot see; the encounter is far shorter than the 60 min sampling). Sliding processivity (positional only, see previous decisions).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'concluded that P-TEFb works distributively rather than processively: that it modifies a repeat, lets go, and rebinds — rather than holding on and running along the substrate'",
      "supports": "definition of the two modes and the claim to test",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "",
      "supports": "in multisite modification, processivity is commonly represented as several modifications per binding event with a continuation probability",
      "origin": "assumed"
     }
    ],
    "evidence_tier": "to_be_estimated",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "ATP is an explicit consumed species (one per repeat modified, ADP produced) and enters every rate as ATP/(K_ATP + ATP), with K_ATP fixed at 50 uM.",
    "rationale": "ATP is a required entity, and the note states one ATP per phosphorylation. At most 800 uM of the 3000 uM is consumed, so with any K_ATP in the tens of uM the factor stays near 0.98 throughout. ATP is saturating, and its depletion cannot shape the data. K_ATP is therefore fixed, not estimated: no part of the data window constrains it. Mass action in ATP was rejected because it would impose a ~27% rate decline by 16 h as an artefact of the rate-law form.",
    "alternatives_considered": "Mass action in ATP (artefactual slowdown). ATP held constant as a parameter (loses the required entity and the mass balance). Estimating K_ATP (flat direction).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'ATP: 3 mM at the start. Each phosphorylation consumes one ATP.'",
      "supports": "initial ATP and stoichiometry",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "'Present at 100 µM.'",
      "supports": "at most 8 x 100 uM = 800 uM ATP consumed",
      "origin": "user-provided"
     },
     {
      "source": "general_knowledge",
      "locator": "",
      "supports": "protein-kinase ATP Km values typically in the 10-100 uM range",
      "origin": "assumed"
     }
    ],
    "evidence_tier": "default",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "P-TEFb is a constant species at 1 (relative units). Its absolute level is absorbed into kmod; CTD is in uM with CTD_0(0) = 100 uM.",
    "rationale": "The enzyme concentration is not given, and only the product kmod*PTEFb is visible. Fixing PTEFb = 1 removes that flat direction. Total substrate is known, so the model's amounts are absolute in uM. The arbitrary MS scale belongs to the observation model's per-time-point factors and does not trade off against any model state. Each repeat is one bit, so 9 count states are complete.",
    "alternatives_considered": "Estimating PTEFb and kmod separately (structurally non-identifiable). Tracking Ser2 and Ser5 separately (excluded by the note).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'within a single heptarepeat, phosphorylation happens on either Ser2 or Ser5, but not both at once'",
      "supports": "one bit per repeat, so 9 count states",
      "origin": "user-provided"
     },
     {
      "source": "lab_note",
      "locator": "'Present at 100 µM.'",
      "supports": "initial substrate amount",
      "origin": "user-provided"
     }
    ],
    "evidence_tier": "direct",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "Not in the base, and named for the evaluation as what these data are expected not to separate: enzyme activity loss over 16 h, substrate saturation of the kinase, sliding versus random-site processivity, and nb > 1 versus cp > 1 versus processivity.",
    "rationale": "Loss of kinase activity over 16 h would slow late modification exactly as negative cooperativity (cp < 1) does at high n, and only the 960 min point sees either. Substrate saturation is a time reparameterisation (see the distributive-steps decision). Positive neighbour effects, positive count cooperativity and processivity all produce nucleation-then-fast-completion from counts at 3 time points without replicates. These are recorded so that a criterion difference among them is reported as an indistinguishable set, not as a mechanism. None is added to the base: no observable in the single condition is argued to separate them.",
    "alternatives_considered": "Adding a first-order enzyme inactivation state (deferred: a revision to argue from residuals at 960 min, not a priori).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'with eight repeats, four time points and no positional information, we expect there to be things the data simply cannot decide'",
      "supports": "user expects and wants named the unresolvable questions",
      "origin": "user-provided"
     }
    ],
    "evidence_tier": "default",
    "confidence": "medium",
    "user_decision_required": false,
    "question": ""
   },
   {
    "decision": "No observation quantities in the Antimony. Readout phos<n>_rel maps onto species CTD_n (n = 0..8) with one scale factor per time point, shared by the nine peaks of that spectrum. Per the note, noise is additive normal with one sigma scaled by the same factor. That is the observation-model agent's to write.",
    "rationale": "The intensities are relative and drift between injections, so a per-time-point scale is a property of the measurement, not of the chemistry. The constant total substrate (100 uM) gives the dynamics the absolute reference, so the scales are identifiable from the shape of each spectrum.",
    "alternatives_considered": "Normalising states to fractions inside the model (rejected: it duplicates the observation layer).",
    "evidence": [
     {
      "source": "lab_note",
      "locator": "'Any model of this data needs a way to map predicted amounts onto measured intensities, and that mapping is not the same at every time point.'",
      "supports": "per-time-point scaling belongs to the observation model",
      "origin": "user-provided"
     }
    ],
    "evidence_tier": "direct",
    "confidence": "high",
    "user_decision_required": false,
    "question": ""
   }
  ]
 },
 "declared_constants": [
  {
   "expression": "CTD_0 + CTD_1 + CTD_2 + CTD_3 + CTD_4 + CTD_5 + CTD_6 + CTD_7 + CTD_8",
   "tolerance": 0.01,
   "locator": "'even though the total amount of substrate in the tube is conserved throughout'",
   "why": "total CTD substrate is conserved at 100 uM; modification only moves molecules between count classes"
  },
  {
   "expression": "PTEFb",
   "tolerance": 0.01,
   "locator": "'It is not consumed and its concentration does not change over the experiment.'",
   "why": "the kinase is catalytic and constant"
  }
 ],
 "basal_state": {
  "initial_values_are_steady_state": false,
  "suggest_preequilibration": false,
  "note": "t = 0 is the start of the kinase reaction: all CTD unmodified at 100 uM, ATP 3 mM. This is the pre-reaction state by construction but not a steady state of the model, whose only steady state is full modification (CTD_8). Pre-equilibrating would run the reaction to completion before the first sample, so simulate from these initial values."
 },
 "consulted_sources": [
  "experiment_description (bench note: CTD phosphorylation by P-TEFb, in vitro time course)",
  "intent",
  "domain pack general-dynamics (pitfalls 1-8, reaction templates)",
  "domain pack measurement-tech (pitfalls 4, 7)",
  "general knowledge (Markov-chain lumpability; count-level representation of processive multisite modification; typical kinase ATP Km range)"
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
 }
}
````
