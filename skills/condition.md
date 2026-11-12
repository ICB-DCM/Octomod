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
