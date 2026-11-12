# Reporting contract

`octomod/reporting/round_report.py` and `octomod/reporting/model_report.py`
render two self-contained HTML documents per round.
They are **renderers over typed artifacts**, not a module: no LLM is called, nothing
is inferred, every number is read from the run's record or simulated from the model it
depicts — so a figure cannot disagree with its data. Sections whose artifacts
are missing render a visible note; rendering never raises and never stops a run.

**The rule:** fixed sections are machine-filled from artifacts; the agent's
narrative appears ONLY in the labelled pocket (section 10), and as quoted
decision text in the model report's M2/M3. Everything else is computed.

The section order below is stable across runs and goals. A front end may rely on
it, on the `id` attributes (`s2`…`s13`, `m1`…`m5`) and on the shapes described.

## `report/report.html` — written at the end of S7

| # | Section | Filled from |
|---|---|---|
| 1 | Header — testcase + round, run id, date, backend, agent models, workflow sha, status badge | `run`, the ledger (`run_start`, `agent_call`), `evaluation` — record keys: the round's (`rounds/round_k/…`), the fitted problem's (`…/candidates/<id>/…`, `_single` for a single-model round) or the run's |
| 2 | Intent (frozen) — question, system, inference target, success criteria | `intent` |
| 3 | The model — species / reactions / parameters tables, Antimony in `<details>`, network figure | `model/sbml`, `model/antimony`, `model/parameters` |
| 4 | The data — one figure per observable, one series per condition, held-out open | `petab/measurements` + `petab/holdout_measurements`, else `data/measurements`; `data/report` |
| 5 | The estimation problem — parameter / observable / condition tables, DOF line | `petab/*`, `assembly` |
| 6 | Estimation — **the convergence caveat first, when there is one**, then **the optimiser comparison when one was run**, **waterfall**, **parameters vs bounds**, optimizer/seed/starts, cost profile | `estimation`, `optimizer_comparison` (absent on almost every run), `cost`, `petab/parameters`, the ledger (`convergence: accepted-by-human` / `pre-declared-by-human`) |
| 7 | Fit — **the central grid**: observable × condition, data + best fit + band | simulated via `PetabTables.simulate_observables` at `best_x_unscaled`; band from `evaluation.prediction_uncertainty` |
| 8 | Evaluation — in THREE GROUPS, see below | `evaluation` (`fit`, `noise_check`, `holdout`, `profiles`, `discrimination`, `identifiability`, `attribution`, `latent_states`, `declared_constants`) |
| 9 | Epistemics — `cannot_distinguish` / `nonetheless_determined`, with the `computed_*` lists as machine reference, and, when profiles ran, `finite_but_poorly_determined` (closed profiles wider than `gates.determined_box_fraction` of their box; engine-filled, no gate; not on a discrimination round, whose three lists are about the mechanism and carry no profile-derived entry); **the convergence caveat above them when the fit's convergence was accepted rather than demonstrated**; **the convergence caveat above them when the fit's convergence was accepted rather than demonstrated** | `evaluation`, the ledger |
| 10 | **Agent narrative** (pocket) — diagnosis, misfit hypotheses, verdicts, recommendation | `evaluation.interpretation` |
| 11 | Decision record — the decision record inlined, escaped, in `<details>` | `decisions_md` |
| 12 | Gate record — every gate event for this round, pass/fail coloured | the ledger (`event == "gate"`, matching round) |
| 13 | Provenance — agent calls, models used, summed cost, the record keys the page read | the ledger (`agent_call`, `human_gate`) |

**The convergence caveat.** When a human answered `accept` at the
`estimation_convergence` gate — or pre-declared it at the budget gate — the fit was
kept with post-fit checks failing. Three surfaces must say so, and a test
asserts each on the RENDERED artifact rather than on a function call:

- **section 6** leads with which checks failed, each measured value against its
  threshold, and the reason the person gave. It renders even when
  the `estimation` summary is missing, which is when it matters most;
- **section 9** carries it ABOVE `nonetheless_determined`, because that list
  asserts a quantity IS pinned down and it is pinned down only *given* an
  optimum nobody demonstrated was reached;
- **ANALYSIS** (run level) lists it under `still_open`.

Per CANDIDATE, never per round: candidates are compared, and one candidate's
accepted-not-demonstrated convergence must not be carried by the others.
A pre-declared accept reads differently from a post-hoc one ("before the fit
ran" vs "after seeing the numbers") — the provenance is part of the claim.

**Visual priority** (user requirement): the fit grid, the waterfall, the
parameters-vs-bounds plot and the profile plots are the dominant figures
(`figure.fig.lead`). Tables support them; they do not lead.

**Steady-state measurements.** A row at time `inf` (PEtab's steady-state
measurement) has no place on a time axis. The data figures (§4), the fit grid
(§7) and the held-out figure (§8) draw it in a column of its own right of the
last finite time, marked ∞ and set off by a dotted rule, with the model's
steady state and its band in the same column; the caption says so whenever
such a column is drawn.

### Section 8's three groups

§8 became the place every S7 feature added a subsection: nine by the time this
was noticed, ten with "Checks that ran", flat, with nothing
saying which order to read them in. It is NOT split — §8 is one of thirteen
numbered sections that every cross-reference depends on — so it is a
hierarchy. Three groups, each stating the question it answers, in the order a
modeller asks in, with every subsection at `h4` under one of them:

| group | answers | subsections, in order |
|---|---|---|
| **What won, and why** | the choice, the evidence that bought it, and how well the chosen model actually fits — including the data it never saw | Model comparison · Why the winner wins · What each mechanism term buys *(MD paths only)* · Fit metrics · Held-out prediction (T2′) |
| **How far to trust it** | what the data pinned down and what they did not | Profile likelihood · Information spectrum at the MLE |
| **What is still wrong** | the checks that could contradict the choice above — and, where one found nothing, that it ran | Noise-model check · Structural misfit indicators · Checks that ran |

Enforced, not just documented: `tests/report_budget_unit.py`
→ `test_s8_has_three_groups_and_nothing_outside_them` renders §8 on a round
that supplies EVERY subsection's input and asserts the three groups are
present in this order, that nothing renders above the first group, and that
every rendered subsection sits under one. **A new §8 subsection therefore
fails the battery until it is given a group** — which is the drift
described above.

Two consequences worth stating so they are not read as omissions. A subsection
whose input is absent renders nothing and is not asserted — the test supplies
all ten deliberately, because a shape test on a report with holes in it is a
shape test on the holes. And the group prose must say what the group is for: a
bare label would be the flat list again with three extra lines in it, so each
group's question is asserted non-trivial.

## `report/model_report.html` — written at the end of S1, before the scope gate

This is the document the user reads in order to answer the scope gate.

| # | Section | Filled from |
|---|---|---|
| M1 | The model at a glance — network figure, counts, the same three model tables, Antimony in `<details>`; **on a run built on the knowledge module, "Where each reaction comes from"** (below): every model reaction with its label, and per direction the entry it matches with that entry's origin and band | `model/sbml`, `model/antimony`, `model/parameters`; `model/reaction_support`, `reaction_evidence`, `knowledge_admitted` |
| M2 | **Places needing your input** — decisions with `user_decision_required`, numbered, question text prominent | `model/build_report` |
| M3 | Assumptions ranked by uncertainty — every decision, least-confident first; rationale, evidence, evidence tier | `model/build_report` |
| M4 | Deterministic check results — the S1 gate ladder; advisory findings called out above the table | `gates/model_*`, else the ledger (module `model`) |
| M5 | Sources consulted — verbatim | `model/build_report.consulted_sources` |

`model/build_report` absent (user-supplied model) means M1 and M4 render normally
while M2/M3/M5 say so. Mechanism-discrimination rounds render one M1/M3/M4 block
per candidate (`space/candidates` + `candidates/<id>/model`).

### M3 decision fields

Each entry of `model/build_report.decisions` renders as one row, sorted
least-confident first (`confidence` may be a word or a float):

- `decision` — the row's heading.
- `rationale` — the argument the model rests on. Rendered directly under the
  decision at full reading size with a left rule: it is the section's primary
  content, above the evidence it cites.
- `evidence` — list of `{source, locator, supports}`, each a compact line
  `source [locator] — supports`. A "general knowledge"-style `source` is shown
  **muted**: it is still recorded, but a real locator must stand out against it.
- `evidence_tier` — coloured badge (`default` amber, `transferred` pale,
  `direct`/`reported`/`measured` green).
- `tier_demoted_from` — when present, an amber badge in the tier cell reading
  `demoted from <tier>: no source attached`. This marks a **deterministic engine
  enforcement** — a direct or transferred claim with no source attached is
  recorded as `default` — so it is always visible, never folded away.
- `alternatives_considered`, `question`, `user_decision_required` — as before.

`rationale` and `evidence` are a newer contract. Decisions lacking them render a
muted `"<field(s)> not recorded (pre-contract run)"` line instead; absence of
`tier_demoted_from` renders nothing.

## Where each reaction comes from (the knowledge module)

Present on every run built on the knowledge module; a case that declares
`grounding: {skip: true, why: …}` renders nothing on any surface below except
the skip on the run page header. A grade is a BAND — high, medium, low, weak,
none, or not applicable (offline) — and every surface shows it with the
source that earned it (`medium — <source> (direct_experimental,
related_system)`), never as a number. The data are record keys, all the
engine's:

- `rounds/round_0/reaction_evidence` — the module's dossier as the run was
  started with it (copied once from `input/knowledge/knowledge.json`): every
  reaction with its evidence items (each item's classification, the citation
  check, whether it counts and the class it was graded as), its band, the
  source(s) that earned it (`because`), its flags (contested, disputed class,
  class corrected, unquoted), whether it is required or essential and its
  origin; the facts, the system summary, the mode, the suggested floor and the
  rule table it was graded by. A later round reads the most recent round's;
- `rounds/round_k/knowledge_search/<n>` — each targeted search: the questions,
  the reactions and facts it returned with their bands, its calls and cost,
  and `admission` (what it admitted at which floor, and why the rest was not);
- `rounds/round_k/knowledge_admitted` — the reactions searches admitted into
  the essential set, each with origin `search`, `requested_by`, the question it
  answers and the floor it was admitted at;
- `rounds/round_k/space/floor` — the round's support floor, `{band, step,
  source}`, `source` one of `human`, `rule` (the suggestion taken
  unchanged), `schedule` (an expansion round's step), `lowered` (the engine,
  after a base failed its essential set twice); its history is the round's
  `floor_set` ledger rows;
- each model's annotation `…/model/reaction_support` (a single model's at
  `model/`, a candidate's at `candidates/<id>/model/`, a staged base's at
  `base_model/`): every model reaction, in each direction its rate law can
  carry, with its label — user-provided, database-supported,
  literature-supported or inferred — and per direction the entry it matches
  with that entry's origin (human, knowledge, search) and band, every other
  entry it implements, the participants held as parameters (`as_parameter`),
  the required reactions the model lacks and the entries it does not use.

The surfaces:

- **model report M1** — "Where each reaction comes from" (anchor
  `reaction-support`, the link the scope card names): the counts, one row per
  model reaction with its equation and law, its label, the entry it matches in
  each direction (band and source, origin) and the sources that count for it,
  a flag box for a required reaction in no model reaction, then the dossier
  entries the model does not use, folded. A candidate set adds one table of
  each candidate's counts and inferred reactions above the per-candidate
  blocks;
- **the intent card (S0)** — the module's mode and counts; the support floor
  and whose it is (the person's or the rule's), with its step; the required and
  the essential reactions, one line each with band, source and origin; the
  facts per role; and the intent being frozen against the one the module saw
  (`knowledge/intent_before.yaml`), one line per added, removed or changed key;
- **the scope card** — in this order after the axes: the REACTIONS line with
  the counts, one line per inferred reaction (the reaction as written, its law,
  the direction the dossier does not hold, what the dossier holds nearby), one
  per required reaction the model lacks; then the ESSENTIAL SET line (how many
  reactions the base was built from, at which floor and whose, by origin), one
  line per essential the floor left out and why, the SUPPORT FLOOR line (the
  round's floors in order, each with its source) and every search with its
  questions, what it admitted and what it did not; an advisory line when no
  quantity is marked `set_per_condition` while the intent lists
  perturbations, and one when construction named conversions `missing` that
  the base passed its checks without (not searched). M1 is among its
  documents. A candidate set's card has the counts per candidate and each
  inferred reaction once, with the candidates that carry it; a staged base's
  card has the base's. The inferred reactions are what the person is asked
  about, beside the agent's own questions — there is no separate gate;
- **the redraft-budget card** of construction (the exhaustion gate) — the
  floor's history and every search of the round, above the measured cost;
- **the scope card of a discrimination round** — the VARIANTS' FLOOR (the
  base's floor lowered by `variants_offset`) with its reason, the expansions'
  search with what it admitted, and one DROPPED line per variation still below
  the floor, naming the conversion, its band and its entry;
- **the expansion card** — the SUPPORT FLOOR of the round it seeds with its
  source (the schedule, or the person), one line per axis (the reactions its
  patch adds to the base, each with the entry it matches, that entry's origin
  and band, or that nothing in the dossier describes it), one REFUSED line per
  axis that adds a conversion below the floor, a DROPPED line for an axis that
  removes a required reaction, the round's search (spent or not, and what it
  admitted), and the forms `floor: <band|none>`, `step: <n>` and `search:
  <question>` (a floor or step answer is recorded as the person's, a
  `floor_set` row; a search answer spends the round's one search and asks the
  card again);
- **`decisions_md`** — "Reactions and their support (engine)": for each
  annotated model its counts, every reaction with its label, the entry it
  matches with its band, source and origin, the sources that count, the
  inferred reactions set apart, and the dossier entries the model does not
  use;
- **the run page header** (research row) — from the `grounding_fence` ledger
  row: the module's mode, the support floor, whose it is, and the step — or
  the case's declared skip and its why;
- **ANALYSIS**, "Where the model came from" (below).

What must never happen on any of them: a grade shown as a number or a
probability, or without the source that earned it; a floor shown without
whose it is.

### The floor card (`./run.sh knowledge`, before the run)

Printed by the knowledge module when it finishes, and again by
`./run.sh knowledge --show --testcase <folder>` (which calls and writes
nothing). It is the one card the front end presents before a run exists, and
its order is fixed:

1. **ESSENTIAL REACTIONS** — how many, how many required; one line each: id,
   equation, `[required, origin human]` or `[origin knowledge]`, the band and
   the source that earned it; its flags beneath it;
2. **NO SOURCE COUNTS** — the essentials no source counts for, each a keep or
   drop decision (keep, tagged inferred, is the default on a plain yes);
   absent when there are none;
3. **SUGGESTED FLOOR** — the band and the rule's reason (the lowest-graded
   supported essential that is not required, with its source); offline, `not
   applicable`;
4. **TRADE-OFF** — the one sentence, then for each band above the suggestion
   the essentials that would leave the base at it (absent offline);
5. **FORMS** — `floor: <band|none>`, `step: <n>`, `keep: <id>, <id>`, `drop:
   <id>, <id>`, each with what it means;
6. **DECISION** — only when testcase.yaml records one: the floor, the step,
   who decided, what was dropped and kept, the note;
7. **FACTS** — how many per role, then one line each: id, kind, statement,
   band, the roles it is for;
8. the module's mode, its calls and their cost, and the folder it wrote.

## The optimiser comparison panel

Written only when a comparison actually ran — the cost probe selected an
optimiser, or a human answered `compare` at the convergence gate — so it is
absent from almost every report. It sits ABOVE the waterfall, because a reader
about to look at this fit's numbers needs to know another optimiser was tried
before they read them.

What it must carry, and why each part is not optional:

- **one row per method** with best objective, optimality gap, successful starts
  as hits over ATTEMPTED starts, and overall efficiency. Attempts, not
  survivors: a method that crashed six of eight starts must not read as 100%.
- **both metrics defined in words.** "Overall efficiency 0.12" is not
  self-explanatory, and a number a reader cannot interpret is one they skip.
- **the selection, when the run made one** — which optimiser this fit used and
  the reason, starred in the table. The star means the optimiser the workflow
  USED, so it follows the selection and not the default.
- **what the numbers point at**: more starts, a different optimiser, or
  neither, in those words. The comparison exists to separate an under-started
  fit from a wrong solver, and that distinction is the panel's whole point.
- **methods that did not compare, and WHY** — not installed is a different
  fact from stopped by the budget, and neither is a defeat. A method that was
  absent must never be ranked last.
- **the caveat**: the comparison ran on a fraction of the estimation budget, so
  a method can win here and lose at full start count.

The same decision appears on the cost card the human approves (the optimiser,
its reason, and its measured per-start cost when the run switched to a dearer
method) and in the ledger (`optimiser selected`, `optimiser comparison:
winner=…`, and `optimiser comparison not run: <why>` — the skip is recorded too, so
a reader can tell "not run" from "never considered").

## Prose budgets — the contract numbers

**Completeness is for the record; legibility is for the reader.** The ledger,
The decision record (`decisions_md`) and the agent calls (`agent_calls/<role>`) stay exhaustive and unchanged. The rendered
report is a reading surface, and these are its limits. They are enforced by the
RENDERER, never by asking an agent to write less: an agent that must argue its
case cannot also be told to be brief, and a budget that depends on its
cooperation is not a budget.

Three layers on every surface: **(1)** the visual plus a one-line claim,
**(2)** a structured summary — verdict, numbers, badges, **(3)** the full prose,
folded in `<details>` or linked to the artifact that holds it. The default view
is layers 1–2. **Nothing is deleted; layer 3 always exists.**

| surface | default-visible budget | overflow goes to |
|---|---|---|
| §8 misfit evidence, per reason | 1 line, ≤ 160 chars; ≤ 3 reasons shown | `<details>`, then `evaluation` |
| §9 epistemics, per entry | 1 line, ≤ 120 chars; ≤ 6 entries shown per column | `<details>` with the full list |
| §10 agent diagnosis | ≤ 3 sentences | `<details>` "full diagnosis" |
| §10 misfit hypotheses | ≤ 3 items, 1 line each | `<details>` |
| §10 `answers_intent`, per verdict | pass/partial/fail chip + ≤ 1 line of evidence | `<details>` with criterion text |
| §11 checker concern, per aspect | ≤ 280 chars (the existing digest precedent) | `gates/assembly_verification` |
| M2 agent question, per item | the question only | model report M3 |
| M3 per-decision rationale | ≤ 1 line, ≤ 200 chars | `<details>`, then `decisions_md` |
| M3 decisions shown | the 8 least-confident | `<details>` with all of them, same order |
| M3 evidence citations, per decision | ≤ 2 shown | `<details>` with every citation |
| M3 alternatives considered, per decision | ≤ 1 line, ≤ 200 chars | `<details>`, then `model/build_report` |
| M3 per-decision question, per decision | ≤ 1 line, ≤ 200 chars | `<details>`, then `questions` |

**M3 is budgeted per DECISION, not per section.** Every
other section's default view targets one screen; M3's does not, and that is a
choice rather than an oversight. The rationale is the argument the model rests
on, and the table is sorted least-confident first, so the rows a reader most
needs a reason for are the ones at the top — folding it would put a click
between them and the reason. On one live run's first round that is 8 rows and 9,435
visible chars, about three screens. The per-decision limits above are what is
enforced, and `tests/report_budget_unit.py::test_m3_holds_every_per_decision_budget`
asserts each one on maximally overlong input.

Two parts of an M3 cell are deliberately NOT budgeted. The decision text is the
row's identity — clipped, a reader cannot tell what the row is about without
opening a fold. And an evidence `locator` is the verbatim quote a reader checks
the citation against; clipping it damages the check the citation exists for. If
they ever need limits, the `supports` gloss is the part to clip, never the
quote.
| gate card evidence lines (live sessions) | ≤ 12 lines | the linked document named on the card |
| §4 data-extraction flags | ≤ 6 shown, 1 line each ≤ 160 chars | `<details>` with every flag |
| §8 misfit indicators | a three-signal traffic-light row + ≤ 3 reasons, 1 line each ≤ 160 chars, **plus one table row per indicator giving its measured value, the threshold that judged it, whether it fired, and how close it came** | `<details>`, then `evaluation` |
| §12 gate record | the count, plus every FAILING row | `<details>` with the complete table |
| §12 gate detail, per row | ≤ 200 chars | the fold's full table, then the ledger |

The last four rows were added while implementing these budgets: the acceptance clause
asks for one screen per section, and on a live run these four surfaces exceeded
it while the table above did not name them. §12 is the one that is a record
rather than prose — its budget therefore hides no finding, because a failing
gate is always shown and only the passing rows fold away.

Truncation rules, so a cut is never mistaken for the whole: cut at a **sentence
boundary** where the text has one, else at a word boundary; append `…`; and
always render the fold or the link that reaches the full text. A truncated
string with no route to its original is a defect, not a budget.

What is **never** truncated: any number that decides something (a criterion
value, a p-value, a threshold, a coverage fraction), any gate verdict, any id,
and `evaluation_core` — the budgets are render-side only, so the core JSON of
a run is byte-identical with and without them.

## M3's "where the number came from" column

The machine field is `evidence_tier` and its values stay `direct` ·
`transferred` · `default` · `to_be_estimated` in `model/build_report`, because
s1's demotion rule and several suites read them. What a READER sees is mapped
at the render boundary:

| machine | reader |
|---|---|
| `direct` | measured here |
| `transferred` | carried from elsewhere |
| `default` | no source given |
| `to_be_estimated` | fitted |

`default` was the value that most needed this: it means "the agent gave no
resolvable source, so this is an engine default" and read as "the default
choice" — the opposite of a warning. `transferred` is the value a reader
should look at hardest, being a real measurement of a different system, and
the word said none of that.

The column carries one sentence above the table saying what it is FOR, because
four labels with no question attached are still four labels. An unrecognised
tier renders verbatim rather than blank: a value the map has not learned must
be visible.

**This is one column, not a vocabulary layer.** The general machine-term →
reader-term mapping is held: it is not settled, and it
may not be a word list at all. `octomod/reporting/model_report.TIER_WORDS`
is scoped to this surface deliberately.

## Structural-misfit indicators: the margin, not the verdict

Every indicator states its DISTANCE from the threshold that judged it, whether
it fired or not, in §8's table and as one ranked line on the verdict card.

The reason is a run, not a preference. A live run ended two of its three
rounds unused, 21.7 nllh short of the true structure, because the sigma
indicator on `obs_regb_p` measured 1.232x the replicate floor against a 1.3
threshold. §8 said `quiet`. It did not say `0.068 below the line`, and the
channel in question was the one the missing mechanism lived in.

**One number, so the indicators can be ranked against each other.** Two are
ceilings and one is a p-value, so a raw distance is not comparable and "which
came closest" cannot be read off. Closeness normalises them:

| test | closeness |
|---|---|
| ceiling (fitted sigma over the replicate floor) | `value / threshold` |
| p-value (chi2 at the noise floor, residual shape) | `alpha / p` |

`closeness >= 1` means the indicator fired. Below 1 it is how far it got.

Three rules the surfaces must keep:
- **The thresholds come from the run**, recorded in
  `evaluation.misfit_evidence.thresholds` by the round that applied them. A
  run older than 2026-09-10 recorded none; the table then uses today's default
  and SAYS so on the row. A threshold that judged a run belongs in the run.
- **"Not measured" is not "measured and quiet."** An indicator that could not
  run (a state-dependent sigma has no single number to hold against a floor)
  appears with no value and sorts last, so it never reads as the closest call.
- **A quiet indicator is not a claim that the structure is complete.** §8 says
  so under the table, next to the verdict gate's standing offer of another
  round.

## Figure conventions

- **Waterfall**: sorted `(fval − best) + 1` on a log y-axis — the pyPESTO
  convention, never a bare linear fval plot.
- **Parameters vs bounds**: one row per estimated parameter, each with its own
  axis (log when `parameterScale == log10`); bracket = `[lowerBound,
  upperBound]`, dot = best, faint ticks = ensemble members, red = listed in
  `at_bounds`.
- **Profiles**: plotted as the **likelihood ratio** `exp(−(−logL − best))`,
  y ∈ [0, 1.05], dashed 95% threshold ≈ 0.147, `ci95` shaded, best marked,
  log-x when the values span more than a decade. Read from
  `profiles[p].path.likelihood_ratio` / `.ratio_threshold`, derived from
  `.nllh` for older runs. No `path` at all means the CI table only.
- **Noise-model check** (section 8): from `evaluation.noise_check`,
  `{<observableId>: {assumed, test, n, statistic, p_value, qq:{theoretical[],
  sample[]}}}`. Small multiples, **2 cards per row**, one card per observable
  holding **two panels** and one shared caption:
  - left, **QQ**: sample standardized residuals against the theoretical
    quantiles of the assumed distribution, identity line dashed;
  - right, **histogram**: the same residuals, density-normalized,
    `bins = clamp(round(sqrt(n)), 5, 15)`, with the assumed pdf drawn over it
    as a dashed line on a grid 15% beyond the sample range — `N(0,1)` for
    `assumed == "normal"`, `Laplace(0, 1/sqrt(2))` for `"laplace"` (both
    unit-variance, matching standardized residuals). An unrecognised family
    draws no curve and says so, rather than drawing the wrong one.

  Caption `<test>, n=<n>, p=<p_value>`. A card with `p_value < 0.01` is
  bordered amber, its marks turn red, and it carries "residuals reject the
  assumed noise model — change_noise_model is a revision candidate"; the
  rejected observables are summarised beneath the grid. An entry carrying only
  `{assumed, n, note}` renders the note in muted text with no plots. Field
  absent entirely (older runs) ⇒ the sub-block heading with a muted note, so
  the shape holds.
- **Profiles block**: iterate parameter entries only — the block also carries
  engine metadata under underscore keys (`_meta.x_names`). Rendering those as
  parameters produces a junk CI row badged **OPEN**, i.e. a false
  non-identifiability claim. `_real_profiles()` is the filter; use it anywhere
  `profiles` is enumerated, the header badge included.
- **Prediction bands**: from `evaluation.prediction_uncertainty.bands`
  (`{"<obs>@<cond>": {time, best, lo95, hi95, lo90, hi90}}`) — nested envelopes,
  widest lightest, `best` as the line. The held-out figure adds an outermost
  band of the 95% envelope ± 1.96·σ, because that is what coverage is scored
  against (`holdout.groups[*].band_source`). Absent means the fallback:
  ensemble min/max ± 1.96·σ. The method is captioned once, where bands first
  appear; an acceptance/undersampling `note` is shown in amber.
- **Network**: SBGN-lite via graphviz `dot` — species as rounded blue boxes,
  each reaction a grey process node whose **label is its rate law** (a real
  label participates in layout, so it cannot collide with a node the way an
  `xlabel` can; long laws wrap). `ranksep=0.9`, `nodesep=0.6`. The SVG root has
  its fixed `width`/`height` stripped and keeps only the `viewBox`, styled
  `max-width:100%; height:auto; display:block; margin:auto` — the diagram scales
  to its frame and is never clipped. Falls back to a manual circular matplotlib
  layout, then to a note. Cap 20 species (12 for the fallback layout).

## The model tables (section 3 and M1)

Three compact tables, never a text dump: **Species** (`id | initial`),
**Reactions** (`id | lhs → rhs | rate law`, rate law monospace, modifiers on a
sub-line) and **Parameters** (`id | value / assignment | status`, status being
bold `ESTIMATED in [lb, ub]`, `fixed`, or `derived (diagnostic, no dynamics)`).

Initials and parameter values come from `render.species_initial` and
`render.parameter_display` — the assignment-aware helpers. An assignment-based
initial reads `R_tot (assigned)` and an assignment rule reads `:= R + Rp`;
neither is ever `NaN`. Estimate flags and bounds come from
`model/parameters`. The renderer must not read these SBML fields itself:
doing so is what produced the NaN initials.

## Mechanics

- Single file, no CDN, no external JS/CSS. Inline `<style>`; every figure is
  inline SVG (matplotlib Agg, or graphviz `-Tsvg`), XML header stripped.
- `round_report.render_report_html(rnd: Node) -> str`,
  `round_report.write_report_html(rnd: Node) -> Path` (`rnd` is the round's
  record node, `rounds/round_k`; the HTML lands in `runs/<id>_reports/round_k/report/`);
  `model_report.render_model_report_html` / `write_model_report_html` likewise.
- CLI: `python -m octomod report --run-id <id> [--round N] [--model]`
  (default round: the latest present).
- Hooks: S1 `_scope_gate` writes the model report; S7 writes the round report on
  both the single-model and the discrimination path. Both are wrapped in a
  `try/except` that appends a ledger `note` — a report failure never kills a run.

## Selection rounds (mechanism discrimination and model-space search)

A round that fits a candidate SET reports through the same block whichever way
the candidates arrived — agent-proposed rival mechanisms, or the engine's
enumeration of the structural axes the human bought at the scope gate.

- **the selection table**, one row per candidate: n_estimated, −logL, the
  criterion value, ΔAIC and the Akaike weight, sorted best-first;
- **winner + decisiveness**, with the indistinguishable set spelled out. A set of
  more than one is not a defect and must not be presented as one: it is the
  honest statement that the data do not separate those structures. The blind run
  reported four indistinguishable models with the truth ranked first, and that
  was the correct answer;
- **misfit evidence for the SELECTED model** — a selection answers "which of
  these is best", never "is the best one good enough", and those come apart
  exactly when the space is missing a mechanism;
- **the expansion record**, when a round proposed one: the diagnosis, the axes,
  and the human's decision. `expansion` holds the decision so a resume never
  re-asks.
- **why the winner wins**: the ΔAIC split over (observable, condition),
  with the two halves kept apart — `2·Δnllh`, which splits over measurements,
  and `2·Δk`, which is the price of the extra parameters and splits over
  nothing. Then the per-timepoint detail for the largest contributor. The split
  is read out of AMICI's own return data and checked against its own
  per-condition likelihood; when that check fails the decomposition is NOT
  shown and the mismatch is named, because numbers that do not add up to the
  ΔAIC they claim to explain are worse than no numbers. Beside it, what each
  mechanism term BUYS: the winner simulated with one term at its declared
  neutral value, and which series move, in units of each point's own sigma.
  The full per-point record is the round's `attribution`; `evaluation_core`
  carries the summary.
- **what the search covered**: "visited k of the 2^N union lattice", over
  every axis declared anywhere in the run, with the topology named —
  exhaustive within a round, greedy across rounds. A corner never visited is
  not evidence against it, and a reader who assumes otherwise reads the table
  wrongly. Beside it, whether criterion values are comparable ACROSS rounds in
  this run: they are in a pure expansion run, where the data and the assembly
  are copied forward untouched, and they are not in the general loop, where an
  S11 move can change what the likelihood is over. The blanket caveat is gone;
  each run states its own regime.
- **how the lattice was encoded**: one structure per candidate, or one
  supermodel whose candidates differ only in the parameter table. It belongs
  beside the AIC table because it changes how that table reads — under the
  supermodel encoding the candidates share generated code, so a ΔAIC between
  two of them is a statement about the parameter table and nothing else.

## Residual diagnostics (what the expansion agent is given)

Documented here because it is a reporting contract as much as an agent input,
and because its first version was wrong in an instructive way.

Per observable and condition: **the fit point by point** — time, measurement,
simulation, and residual in units of the assay's own replicate noise floor —
plus shape descriptors that do NOT depend on bin edges: when the largest
deviation occurs, a Spearman trend test, the sign pattern and its run count.
Across candidates: a table marking every measurement that NO candidate improved,
separating "still above the noise floor" (a prime suspect) from "already at the
floor" (unimprovable — inventing mechanism for those is how a model gets fitted
to noise). Plus the identical-prediction control: condition pairs the model
cannot tell apart, whose residual difference is therefore pure noise.

**Residual forms** (`residual_forms`, also given to the interpreter): every
residual series of the selected model and of the base fitted with a four-form
library (`octomod/workflow_modules/data/curve_forms.py`: constant, linear, exponential,
rise-and-fall, chosen by small-sample AICc against the constant, amplitude in
units of the replicate floor), and one sentence per observable and stimulus
grouping the series whose forms agree with timescales within a factor of two,
naming what disagrees — "exponential decay in population B, NK, τ 35–48;
amplitude 2–3 σ, larger at higher dose". Written to `report/residual_forms.json`;
the report's "What is still wrong" group carries its strongest sentence as one
line. A description, not a test: the `fit_residual_form` request calibrates one
series against an AR(1) null. In the payload budget its per-series rows are the
first thing trimmed and its sentences the last.

The rejected first version binned each series into early/mid/late thirds. Three
numbers cannot represent the shapes that matter — a peak at one time and a slow
drift collapse to the same summary, and the peak LOCATION is the signature of
product feedback. Long series are thinned to evenly spaced samples rather than
bucketed, so shape survives at lower resolution.

## The result record (run level, one file)

`runs/<id>.h5` is not a rendering: it IS the run (fields in docs/RESULT-SCHEMA.md) — every artifact a module writes goes into
it as it is written, and every reader, these renderers included, reads from it.
The surfaces that read it:

| surface | reads | shows |
|---|---|---|
| `./run.sh status --run-id <id>` | the record | rounds, shape, markers, candidates and their best fval, selection, decisions with mode and note, revision/expansion, the ledger tail |
| `./run.sh inspect --run-id <id>` | `RunResult.failures()` | every failed blocking gate, dropped candidate, agent redraft, stopped outcome — round, candidate, id, detail, in order |
| `./run.sh pending --run-id <id>` | `pending_gate` | the gate a paused run waits at, as JSON |
| `./run.sh show --run-id <id> [<key>] [--full]` | one group or dataset | by record key, as YAML / text / TSV |
| `./run.sh explore --run-id <id>` | the record, interactively | `ls`/`cd`/`cat`/`find`, `gates`, `decisions`, `failures`, `ledger`, `status`, `report`, `export` |
| `./run.sh export --run-id <id> --tiers … --rounds … --out <file>.h5` | the record | a smaller copy for sharing, valid against the same schema, `elided` naming what it dropped |

The per-round HTML renderers in this file build the PEtab tables and the SBML
from the record to simulate; the pages they write are the only files beside
the record, under `runs/<id>_reports/`, and are regenerable. The front end's
use of the commands is `.claude/skills/results/SKILL.md`.

## The whole-analysis report (run level, not round level)

`runs/<id>_reports/ANALYSIS.html` (+ `ANALYSIS.md` as a terminal-readable
companion, and `analysis` in the record), written automatically at every
run end and regenerable with `./run.sh report --run-id <id> --analysis`.

Rounds each had a report and nothing summarised the analysis as a whole, so a
finished run left the reader to reconstruct the answer by opening several
documents and diffing them mentally.

**The order is the contract.** This is the document the reader is handed,
and the argument used to live in the round reports: measured on two real runs,
the rounds and the model report carried 3.5x more text than this page, and the
verdict sat below four sections of provenance. So the page leads with the
argument and keeps the record below it — nothing is cut, it is ordered.

1. **The question**, verbatim from the frozen intent, with the goal and outcome.
   Not budgeted: it is the user's own words from `intent.yaml`, and the engine
   must not clip the question the reader came with.
   Immediately after it, if it applies: **the selected model contradicts the
   experiment's own note** — above the page's own conclusion, because a run can
   finish ACCEPTED with a model that breaks a declared conservation.
2. **What won** — in words before ids. Each declared axis answered Yes or No
   using the axis's OWN `question` text, then the margin, the Akaike weight
   with its conditionality stated, whether the set is distinguishable, and the
   held-out error. Three shapes, and the renderer must use the right one: a
   lattice winner names its structure; a winner carrying no declared axis says
   "the base model plus nothing"; a run where nothing was compared says so in
   a sentence and must NOT print `build()`'s placeholder `"round k model"` as
   though it were an identifier.
3. **Why it won** — the ΔAIC decomposition against each rival, split into the
   likelihood part and the parameter-count part, and which measurement groups
   pay it.
4. **Still open** — open misfit evidence, a non-decisive selection, and the
   declared-undetermined list, with the standing note that these are stated
   because they are true, not because the run failed.
5. **The candidates** — the one picture: an axis grid, because search-path
   candidates differ BY axes, so the axes are the difference.
6. **How the analysis got there** — what changed between rounds, read from the
   decision the human actually approved (`expansion` / `revision`),
   never inferred; then the `answers_intent` verdicts against the criteria
   frozen at S0.
7. **Beyond this data** — only when the expansion agent named any: the
   mechanisms it thinks act in the system that the data cannot separate from
   the selected model, each with why and the experiment that would, latest
   round first (`beyond_this_data` in `expansion.json`, or in the round's final
   proposal when no expansion decision was written). Never fitted and not part
   of the answer: what the next experiment could decide.
8. **The evidence behind this page** — the per-round reports, linked only where
   the document exists. They stay generated and stop being the entry point:
   they are the audit trail, not the place the argument lives.
9. **Gate policy** — the profile, its sha, and every answer it gave.
10. **What it cost** — agent calls, dollars, human decisions, and the pointer to
   the ledger.

On a run built on the knowledge module the page also carries **Where the
model came from**, read from the record keys above: per round, the model's
reactions counted by origin (human, knowledge, search, and the agents that
proposed the rest) and by band; the support floor's history, each floor with
its source; and every targeted search with its question and what it admitted.
It is provenance, so it sits below the argument, never above the verdict.

Enforced by `tests/report_budget_unit.py`
→ `test_the_run_page_leads_with_the_verdict`: the first `<h2>` is
`analysis_report.VERDICT_HEADING`, the visible text above it fits one screen
(measured at 249 chars against a 2,000 budget), and every provenance section
is below it. `tests/live_blind_3_unit.py` asserts item 2's three shapes on
whichever run was written last, mirroring the renderer's own condition.

It reads only artifacts already on disk, so it never asks an agent for a claim
the engine already recorded, and it can be regenerated for a half-finished run.

