# Prompt · `construction_verification` (round 0)

The **construction_verification** agent independent check of the model and its candidates (S1). Below is the exact prompt it was sent in this run (154,182 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 2 times here; the record keeps the prompt and reply of the last call.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Construction audit: check the model-construction record independently

Fresh context, artifacts only: you never see the builder's reasoning, and you audit, never rebuild. Your concerns
reach the human at the scope gate and never block on their own, so what they are worth is how specific they are.

## What you receive
`intent`, `experiment_description` (the lab note), `build_report`, `network`, `antimony`, and on a discrimination
round `candidates` (each a declared `difference` from the base, or a full source with its parameters); with the
knowledge module's output, `known_facts` and `cited_parameters` (each parameter whose `source` cites
`knowledge:<fact id>`). No data and no supplied literature: an auditor who read the same claims would not be
independent of them.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`verdicts` (`{aspect, ok, note}`, one per aspect below) and `overall` (`pass` | `concerns`), both required.

## Rules that get your reply refused
- Every verdict has a note naming the decision(s) concerned, and `overall` is `concerns` exactly when a verdict has
  `ok: false`.

## How to judge
Audit exactly these aspects:
- **citation honesty**: do evidence entries look real and consistent (plausible venue and year, a `supports` a real
  source could contain)? An entry the engine marked `resolution: unresolvable` is a presumptive fabrication; say so.
- **support**: does each `supports` justify the decision it is attached to, or is correlational or adjacent
  material recorded as mechanism?
- **rationale quality**: an argument from the system, the data or the timescale, or a restatement of the decision?
- **tier honesty**: are `direct` and `transferred` warranted by the evidence, and is anything labelled `default`
  that actually has support?
- **structure sanity**: does the Antimony implement the network it claims; is anything in it without a decision?
- **fact application** (only with `cited_parameters`): for every parameter citing `knowledge:<fact id>`, is the fact
  applied faithfully — the right species, population or compartment, the unit, and a value from a related system
  only where that is defensible? Name each misapplication in a note.
- **candidate set** (only with `candidates`): does each candidate differ from the others only in the feature its
  rationale names? A `difference` is everything separating it from the base: does it implement that feature and
  nothing else? With full sources, a parameter one estimates and another fixes, a rate law differing outside the
  tested reaction, or a parameter the Antimony uses but the list lacks is a concern. Say whether the set contains
  the reference model (nothing switched on) when the intent's comparison needs one.

You can be wrong in both directions: prefer a specific, checkable note to vague suspicion.

## Mistakes we have seen
- Inventing a problem to look diligent. A clean report is a valid finding.


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

## build_report
```json
{
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
          "locator": "'There is no transcription, no DNA, no polymerase \u2014 only a purified CTD substrate, purified kinase, and ATP in buffer.'",
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
          "locator": "'concluded that P-TEFb works distributively rather than processively: that it modifies a repeat, lets go, and rebinds \u2014 rather than holding on and running along the substrate'",
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
          "locator": "'Present at 100 \u00b5M.'",
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
          "locator": "'Present at 100 \u00b5M.'",
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
    },
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
```
## network
```json
{
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
}
```
## antimony
model ctd_ptefb_counts
  // CTD_n: CTD molecules with n of 8 repeats phosphorylated (one bit per repeat)
  compartment vial = 1;
  species CTD_0 in vial, CTD_1 in vial, CTD_2 in vial, CTD_3 in vial, CTD_4 in vial;
  species CTD_5 in vial, CTD_6 in vial, CTD_7 in vial, CTD_8 in vial;
  species ATP in vial, ADP in vial, PTEFb in vial;
  CTD_0 = 100; CTD_1 = 0; CTD_2 = 0; CTD_3 = 0; CTD_4 = 0;
  CTD_5 = 0; CTD_6 = 0; CTD_7 = 0; CTD_8 = 0;
  ATP = 3000; ADP = 0; PTEFb = 1;
  kmod = 0.01; cp = 1; q_proc = 0; K_ATP = 50;
  // single-repeat encounters: one modification per binding event (distributive)
  J0: CTD_0 + ATP -> CTD_1 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*(1 - q_proc)*CTD_0;
  J1: CTD_1 + ATP -> CTD_2 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*(1 - q_proc)*CTD_1;
  J2: CTD_2 + ATP -> CTD_3 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*(1 - q_proc)*CTD_2;
  J3: CTD_3 + ATP -> CTD_4 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*(1 - q_proc)*CTD_3;
  J4: CTD_4 + ATP -> CTD_5 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*(1 - q_proc)*CTD_4;
  J5: CTD_5 + ATP -> CTD_6 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*3*cp^5*(1 - q_proc)*CTD_5;
  J6: CTD_6 + ATP -> CTD_7 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*cp^6*(1 - q_proc)*CTD_6;
  J7: CTD_7 + ATP -> CTD_8 + ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*cp^7*CTD_7;
  // processive encounters: j repeats per binding event, continuation probability q_proc (0 in base)
  Jp0_2: CTD_0 + 2 ATP -> CTD_2 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc*(1 - q_proc)*CTD_0;
  Jp0_3: CTD_0 + 3 ATP -> CTD_3 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^2*(1 - q_proc)*CTD_0;
  Jp0_4: CTD_0 + 4 ATP -> CTD_4 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^3*(1 - q_proc)*CTD_0;
  Jp0_5: CTD_0 + 5 ATP -> CTD_5 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^4*(1 - q_proc)*CTD_0;
  Jp0_6: CTD_0 + 6 ATP -> CTD_6 + 6 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^5*(1 - q_proc)*CTD_0;
  Jp0_7: CTD_0 + 7 ATP -> CTD_7 + 7 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^6*(1 - q_proc)*CTD_0;
  Jp0_8: CTD_0 + 8 ATP -> CTD_8 + 8 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*8*q_proc^7*CTD_0;
  Jp1_2: CTD_1 + 2 ATP -> CTD_3 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc*(1 - q_proc)*CTD_1;
  Jp1_3: CTD_1 + 3 ATP -> CTD_4 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^2*(1 - q_proc)*CTD_1;
  Jp1_4: CTD_1 + 4 ATP -> CTD_5 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^3*(1 - q_proc)*CTD_1;
  Jp1_5: CTD_1 + 5 ATP -> CTD_6 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^4*(1 - q_proc)*CTD_1;
  Jp1_6: CTD_1 + 6 ATP -> CTD_7 + 6 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^5*(1 - q_proc)*CTD_1;
  Jp1_7: CTD_1 + 7 ATP -> CTD_8 + 7 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*7*cp*q_proc^6*CTD_1;
  Jp2_2: CTD_2 + 2 ATP -> CTD_4 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc*(1 - q_proc)*CTD_2;
  Jp2_3: CTD_2 + 3 ATP -> CTD_5 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^2*(1 - q_proc)*CTD_2;
  Jp2_4: CTD_2 + 4 ATP -> CTD_6 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^3*(1 - q_proc)*CTD_2;
  Jp2_5: CTD_2 + 5 ATP -> CTD_7 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^4*(1 - q_proc)*CTD_2;
  Jp2_6: CTD_2 + 6 ATP -> CTD_8 + 6 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*6*cp^2*q_proc^5*CTD_2;
  Jp3_2: CTD_3 + 2 ATP -> CTD_5 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc*(1 - q_proc)*CTD_3;
  Jp3_3: CTD_3 + 3 ATP -> CTD_6 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc^2*(1 - q_proc)*CTD_3;
  Jp3_4: CTD_3 + 4 ATP -> CTD_7 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc^3*(1 - q_proc)*CTD_3;
  Jp3_5: CTD_3 + 5 ATP -> CTD_8 + 5 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*5*cp^3*q_proc^4*CTD_3;
  Jp4_2: CTD_4 + 2 ATP -> CTD_6 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*q_proc*(1 - q_proc)*CTD_4;
  Jp4_3: CTD_4 + 3 ATP -> CTD_7 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*q_proc^2*(1 - q_proc)*CTD_4;
  Jp4_4: CTD_4 + 4 ATP -> CTD_8 + 4 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*4*cp^4*q_proc^3*CTD_4;
  Jp5_2: CTD_5 + 2 ATP -> CTD_7 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*3*cp^5*q_proc*(1 - q_proc)*CTD_5;
  Jp5_3: CTD_5 + 3 ATP -> CTD_8 + 3 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*3*cp^5*q_proc^2*CTD_5;
  Jp6_2: CTD_6 + 2 ATP -> CTD_8 + 2 ADP; vial*kmod*PTEFb*ATP/(K_ATP + ATP)*2*cp^6*q_proc*CTD_6;
end
## candidates
```json
[
  {
    "id": "M1_independent",
    "label": "Independent repeats, strictly distributive (base)",
    "rationale": "This is the 'nothing at all' hypothesis and the distributive null. Every unmodified repeat is modified at the same constant rate, whatever the state of the molecule or its neighbours. Each kinase encounter modifies one repeat (cp = 1, q_proc = 0, no positional term), so the count distribution is binomial(8, 1 - exp(-r*t)) at every time point. M2 to M5 each depart from it in one declared feature, so every 'required' verdict (count cooperativity, neighbour effect, processivity) is measured against this reference. No differences from the base.",
    "difference": {
      "set_parameters": [],
      "on_antimony_patch": [],
      "adds_parameters": []
    }
  },
  {
    "id": "M2_count_coop",
    "label": "Count cooperativity between repeats (cp estimated)",
    "rationale": "Tests 'the rate depends only on how many repeats are already modified'. It switches on the base's count-cooperativity term: a molecule with n marks has its per-repeat rate multiplied by cp^n, with cp estimated between 0.2 and 5 on a log scale; cp = 1 is M1. Everything else is as in the base: distributive, no positional term. cp < 1 slows the late steps and lets intermediates pile up by 16 h. cp > 1 gives nucleation then fast completion, with early bimodality between 0 and high counts.",
    "difference": {
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
      "adds_parameters": []
    }
  },
  {
    "id": "M3_neighbour",
    "label": "Nearest-neighbour effect (positional model, nb estimated)",
    "rationale": "Tests 'modifying a repeat changes the rate at which its immediate neighbours are modified'. The base counts marks and cannot express this, because a neighbour effect breaks the count lumping (construction decision 1). It is therefore added as a patch that implements construction's positional rule exactly. Each unmodified repeat is modified at kmod*PTEFb*ATP/(K_ATP + ATP)*cp^n*nb^m, where m is the number of its marked immediate neighbours. cp is held at 1, so nb is the only tested feature; it is estimated between 0.01 and 100 on a log scale, and nb = 1 reproduces M1 exactly. The positional model is written out state by state and reaction by reaction on the 74 gap-structure classes onto which the 256 configurations lump exactly (build report). Gf8 is the unmodified molecule. In G<a><b>_<g...>, a <= b are the unmarked stretches at the two chain ends and the digits after the underscore are the unmarked stretches between marks. Each class reaction also moves one molecule from CTD_n to CTD_n+1 and consumes one ATP, so CTD_n stays the count readout and equals its class sum identically. J0 to J7 stay in the model at zero rate, and the class reactions take over their role. nb < 1 (neighbour inhibition) jams molecules at up to 4 non-adjacent marks before a slow filling phase, a stall between 2 h and 16 h that cp alone cannot shape. nb > 1 (neighbour facilitation) gives nucleation-and-growth, which cp > 1 and processivity also produce.",
    "difference": {
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
      ]
    }
  },
  {
    "id": "M4_processive",
    "label": "Processive continuation (q_proc estimated)",
    "rationale": "Tests the earlier by-eye conclusion that P-TEFb is distributive. It switches on the base's processivity term: after each modification the kinase continues to another unmodified repeat with probability q_proc. q_proc is estimated between 1e-4 and 0.99 on a log scale, with nominal 0.1 inside the box; the lower bound is the strictly distributive M1 to within 1e-4. Repeats are otherwise independent (cp = 1) and there is no positional term. Strong processivity predicts early bimodality, with intermediates that persist to 16 h because released molecules return to the distributive pace. The q_proc profile is the direct test. If it reaches the lower bound with the likelihood flat below about 0.1, distributive action is supported. If a q_proc clearly above 0 is required, the by-eye conclusion fails.",
    "difference": {
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
      "adds_parameters": []
    }
  },
  {
    "id": "M5_neighbour_and_count",
    "label": "Nearest-neighbour effect plus count cooperativity (nb and cp estimated)",
    "rationale": "This candidate combines two features deliberately: the neighbour term nb (as in M3, with the identical positional patch) and count cooperativity cp (as in M2), both estimated. It is the model that contains M2 and M3 as nested cases. M5 against M2 asks whether a neighbour effect is needed once count cooperativity is allowed, and M5 against M3 asks the converse. The joint nb-cp profile shows whether these data can separate the two at all, which is the separability statement the question asks for. Distributive (q_proc = 0). At nb = 1 it reproduces M2 exactly; at cp = 1 it reproduces M3.",
    "difference": {
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
      ]
    }
  }
]
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
   "aspect": "citation honesty",
   "ok": false,
   "note": "No external literature is cited and no entry is marked resolution: unresolvable. The general-knowledge statements are accurate: strong lumpability (Kemeny-Snell), mass action as the low-saturation limit of Michaelis-Menten, and protein-kinase ATP Km of 10-100 uM. Several entries are mis-sourced, though. (1) Decision 10 (five candidates) evidence 2, decision 11 (positional patch) evidence 3 and decision 14 (indistinguishable set) evidence 2 give source 'lab_note', but their locators ('base_model decisions (count cooperativity, processivity switches)', 'base_model decision: exact construction rule...', 'base_model decision: not in the base...') are the build report's own decisions 2, 4, 5 and 8; the lab note contains no such text. (2) Decisions 12, 13 and 15 file engine error logs ('previous_attempt_errors', 'attempt_history'), domain-pack entries and human feedback (petablint rejection) under source 'general_knowledge'. The origins ('inferred', 'user-provided') show nothing is invented, but the source fields should name the build report, the engine log, the pack and the human feedback so a reader can check them."
  },
  {
   "aspect": "support",
   "ok": true,
   "note": "Each lab-note quote matches its decision. Purified components only supports no phosphatase and irreversibility (decision 3). Catalytic and constant kinase supports PTEFb as a fixed modifier (decision 7). 3 mM ATP with 100 uM x 8 repeats supports the at-most-800 uM consumption argument and K_ATP being immaterial (decision 6). One bit per repeat supports the 9 count states. The relative, drifting intensities support per-time-point scales in the observation layer (decision 9). The three-hypothesis passage supports cp, nb and the five-candidate design. The general-knowledge entries back only modelling-form choices (lumpability, the mass-action limit, the continuation-probability representation of processivity) and are recorded as assumed or inferred. No correlational or adjacent material is recorded as mechanism."
  },
  {
   "aspect": "rationale quality",
   "ok": false,
   "note": "Most rationales argue from the system: ATP stays saturating (factor about 0.98); 0.2-5 on cp compounds to about 10 decades at n = 7; neighbour inhibition jams at 3-4 non-adjacent marks; processivity's memory distinguishes it from cp > 1. Three specific problems. (a) Decision 13 says that with cp^7 'the fastest corner reaches rates about 1e4-fold above the per-repeat kmod'. In M5 at cp = 5, nb = 100, Q_G00_1_G00 carries cp^7*nb^2 = 78125*1e4, about 7.8e8. The slow corner (cp = 0.2, nb = 0.01) is about 1.3e-9, so the box spans about 18 decades on that step, not 8. The 1e4 holds only for M3 (cp = 1). The corner-integrability check the decision asks for should use the correct span. (b) Decisions 1 and 2 are stale relative to decision 11. Decision 1 says 'The positional (neighbour) model is not written in this reply' and still carries user_decision_required: true with options A (generate 1024 reactions mechanically) and B (hand-enumerate 256 states). What was delivered is neither: a hand-written exact 74-class lumping. The human at the scope gate is asked a question that no longer describes the record. Part of decision 1's rationale is also about the builder's capacity ('Two previous replies ... failed the contract') rather than the system. (c) Decision 11 says the full enumeration 'would only split each class into configurations with identical trajectories'. That is false for nb != 1. For example, 10110000 and 11010000 are both in G04_1 but receive different inflows: 10110000 gets nb from 10100000, nb from 10010000 and 1 from 00110000; 11010000 gets 1 from 11000000, nb from 10010000 and nb from 01010000. Only the class sums are exact. The conclusion (same likelihood and verdicts) still holds."
  },
  {
   "aspect": "tier honesty",
   "ok": true,
   "note": "The default labels are appropriate: decision 3 (mass action in CTD, irreversibility), decision 6 (K_ATP fixed at 50 uM from a generic range, argued immaterial because ATP >> K_ATP throughout), decision 1 (count-level base) and decision 13 (bounds). cp, nb and q_proc are correctly to_be_estimated. 'direct' on decision 7 (CTD_0(0) = 100 uM, constant kinase), decision 9 (per-time-point scaling) and the J0-J7 stoichiometry rests on lab-note statements. 'direct'/high on decisions 11, 12 and 15 is generous: they rest on a lumping derivation and engine workarounds, not system evidence. The lumping was verified under structure sanity, so no mechanistic support is overstated. Nothing labelled default has unclaimed support."
  },
  {
   "aspect": "structure sanity",
   "ok": true,
   "note": "The base Antimony matches the network: 12 species, and J0-J7 plus 28 Jp reactions (36 in total) with j ATP consumed per j-repeat run. The per-repeat encounter rate is (8-n)*cp^n. Run weights are q^(j-1)(1-q), with q^(r-1) for the run that completes the molecule, so J7 correctly lacks (1-q_proc) and Jp6_2 = q_proc; each encounter's weights sum to 1. The M3/M5 patch was checked class by class against decision 2's rule. The 74 gap classes are exactly the gap structures with n = 0..8 marks (1, 4, 16, 20, 16, 9, 5, 2, 1), and the 257 reactions have the correct target classes. nb exponents equal the number of marked immediate neighbours, including terminal repeats, and cp powers equal n. Each class's coefficients sum to 8-n at nb = 1 (for example G04_1: nb^2+nb+3; G01_22: 5nb; G00_111: 3nb^2). Each Q reaction also moves CTD_n to CTD_n+1 and consumes one ATP, so CTD_n equals its class sum identically. J0-J7 at zero rate and the Jp reactions at q_proc = 0 contribute nothing in M3/M5. Minor gap: kmod's nominal value (0.01 per min) and its estimation scale and bounds are not recorded in any decision."
  },
  {
   "aspect": "candidate set",
   "ok": false,
   "note": "The reference model M1 (cp = 1, q_proc = 0, no positional term) is present, as both the three-way test and the distributive test need. M2 (cp), M3 (nb, cp held at 1) and M4 (q_proc) each switch on one feature. M5 declares its nb+cp combination and carries the identical positional patch, which reduces to M2 at nb = 1 and to M3 at cp = 1. The J0-J7 zeroing and Q-reaction bookkeeping change no trajectory at neutral values, and kmod and K_ATP are handled identically across all five, so no candidate differs outside its named feature. The concern is M4. It implements random-site continuation: the kinase picks any remaining unmodified repeat. The lab note defines processive as 'holding on and running along the substrate', and asks that possibilities representable only positionally be fitted rather than settled from counts. Sliding processivity was set aside in decisions 5, 10 and 14 as 'likely aliased with nb > 1' to stay within five candidates, which is an argument from counts. M4's decision rule ('If it reaches the lower bound ... distributive action is supported') therefore overstates. A q_proc at its lower bound would exclude only random-site processivity. Either the M4 verdict should be reported as testing random-site processivity only, with sliding listed as untested, or the human should decide whether a positional sliding candidate replaces M5 or goes beyond the cap."
  }
 ],
 "overall": "concerns"
}
````
