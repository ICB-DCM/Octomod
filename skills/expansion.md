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
