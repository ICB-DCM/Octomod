# ROUTING — what each agent role is shown

<!-- GENERATED from octomod/agents/routing.py by tools/make_routing.py.
     Do not edit by hand: tests/routing_unit.py fails on drift. -->

Every agent call in this engine passes through one seam
(`RunContext.call`), and that seam calls `routing.enforce()`. A payload
key that does not appear below cannot reach the role at all — the run
stops with the key named.

Granted to every role: `attempt_history`, `human_feedback`, `human_feedback_instruction`, `previous_attempt_errors`, `previous_reply` — the retry dossier and
the human's own words, neither of which carries data.

`intent` is the frozen `intent` record, which is written WITHOUT
`supplied_literature`: the human's literature is frozen in its own
run-level record and reaches exactly four roles — `construction`, as
`retrieved_evidence` with `origin: human`, `knowledge`, as
`supplied_literature` (it may cite a paper for a reaction or a fact
with its own classification), `observation`, as
`supplied_literature` (measurement and noise details in a paper matter
to it), and `revision`, as `supplied_literature` (after the first
round it proposes the new mechanisms; the interpreter does not get it,
so it judges the fit from the data). `construction_verification` does not see it
— an auditor that reads the same claims is not independent of them.

`battery_feedback` is the one key a battery failure adds: the
failing check verbatim, the role's OWN block for the implicated ids, the
merged table rows for them, and the legal vocabulary — never a
measurement value for a role that does not already see them.

`engine_feedback` is what a compile failure that names the observation
model adds, once per round: the failure verbatim and the observable
rows the compiler read, marked as the engine's finding and the role it
is addressed to — never under the human's keys.

Reaching NO role, by construction: the repository — no `CLAUDE.md`,
`.claude/` or `.git` in the ancestor chain of the call's cwd, by cwd
— and any MCP server — none, by flag: `--strict-mcp-config` with
no `--mcp-config` on every call. Both are asserted token-free in
`tests/call_cwd_unit.py`; the live probes that spend usage are
`tests/isolation_probe.py` and `tools/probe_mcp_isolation.py`.

## `research`

*literature evidence for construction, gathered before any fit, and for the expansion agent, about mechanisms the selected model lacks and about the questions that agent asks*

**Sees:**

- `intent`
- `experiment_description`
- `model_summary`
- `misfit_summary`
- `instruction`
- `questions`
- `restrictions`

**Never:**

- the data, in any form — no measurement, residual or fitted parameter value; before construction it sees nothing of a fit, and before an expansion only the misfit indicator sentences the gate cards print (each names an observable and its indicator's own statistic, a sigma ratio or a chi2/dof), which say WHERE the selected model fails, so the search can look for what it lacks there
- the target paper (enforced separately by the cutoff and exclusions in `restrictions`)

**May request:**

- WebSearch / WebFetch, one of the two online roles (with `knowledge`, whose calls are online only when asked)

## `knowledge`

*what is known about the system before the intent is frozen — the essential reactions, the facts a model needs, their sources — and, inside a run, the conversions a base under construction lacks, a round's expansions add or an expansion's axes would add*

**Sees:**

- `intent`
- `experiment_description`
- `required_reactions`
- `supplied_literature`
- `restrictions`
- `mode`
- `questions`
- `model_summary`
- `essential_ids`

**Never:**

- the data, in any form — no measurement, residual or fitted value: it says what is known about the system, before the intent is frozen and, inside a run, about what a model lacks
- a grade of its own making — it classifies each source (`evidence_kind`, `context_match`, `stance`) and the engine grades every reaction and fact from the declared rule table (`grounding.grading`)
- the target paper (enforced separately by the cutoff and exclusions in `restrictions`)

**May request:**

- WebSearch / WebFetch in online mode only — the call's grant; an offline call is granted nothing — fenced exactly like research

## `knowledge_verification`

*a second, advisory reading of each source the knowledge module cites, from the document's text rather than the agent's claim*

**Sees:**

- `items`
- `excerpts`

**Never:**

- the intent, the lab note, the question and the data — it re-reads each source's own text, not the problem the source is cited for
- a grade — the engine grades after both classifications, and keeps the lower where they disagree

## `construction`

*proposes mechanism from prior knowledge, blind to the data's values and shown only what its curves look like*

**Sees:**

- `intent`
- `experiment_description`
- `domain_packs`
- `retrieved_evidence`
- `evidence_instruction`
- `essential_reactions`
- `support_floor`
- `knowledge_summary`
- `grounding_instruction`
- `prior_reactions`
- `engine_feedback`
- `engine_feedback_instruction`
- `supplied_network`
- `instruction`
- `instruction_mechanism_discrimination`
- `revision_directive`
- `previous_model_antimony`
- `minimal_repair`
- `known_facts`
- `data_phenomenology`

**Never:**

- measurement values — `data_file_previews`, the long table, any column of numbers. `data_phenomenology` is allowed because it carries none: a modeller reads shape and timescale off a plot before drawing a network, while values would turn the hypothesis into a fit
- `data_signals` — a noise statistic is observation-model evidence and says nothing about mechanism
- `design_summary` — measurement metadata, excluded so that what construction sees of the data stays one thing: the curves in words
- residuals, selection tables, anything downstream of a fit (that is `revision_proposal`'s and `revision`'s job)

## `expansion`

*writes each candidate as a declared difference from the tested base*

**Sees:**

- `intent`
- `experiment_description`
- `domain_packs`
- `retrieved_evidence`
- `evidence_instruction`
- `base_model`
- `base_changed_instruction`
- `instruction`
- `essential_reactions`
- `prior_reactions`
- `variants_floor`
- `knowledge_summary`
- `grounding_instruction`
- `known_facts`

**Never:**

- measurement values, the data preview, `data_signals` or the design summary — the same exclusion as construction, for the same reason
- residuals or anything downstream of a fit

## `construction_verification`

*audits the construction reply against its own brief*

**Sees:**

- `intent`
- `experiment_description`
- `network`
- `antimony`
- `build_report`
- `candidates`
- `known_facts`
- `cited_parameters`

**Never:**

- the data — it audits the draft against what was ASKED for, not against what was measured; a fit is the engine's job

## `data_extraction`

*reads the raw files into the long table's labels*

**Sees:**

- `intent`
- `experiment_description`
- `data_file_previews`
- `design_summary`
- `battery_feedback`

**Never:**

- the model — an extraction that knows the mechanism can label a column to suit it

## `observation`

*maps model entities to measured quantities, and picks the noise model*

**Sees:**

- `intent`
- `experiment_description`
- `domain_packs`
- `entity_glossary`
- `model_summary`
- `data_labels`
- `data_signals`
- `supplied_literature`
- `known_facts`
- `battery_feedback`
- `engine_feedback`
- `engine_feedback_instruction`

**Never:**

- raw measurement values — it is shown the SIGNALS computed from them, which is the same evidence without the temptation to read a curve and propose a mechanism

## `condition`

*turns the experimental design into PEtab conditions*

**Sees:**

- `intent`
- `experiment_description`
- `entity_glossary`
- `model_summary`
- `condition_labels`
- `observation_draft`
- `design_summary`
- `basal_state`
- `known_facts`
- `battery_feedback`
- `engine_feedback`
- `engine_feedback_instruction`

**Never:**

- measurement values — the encoding follows the DESIGN, and the design summary is exactly the part of the data that is design

## `assembly_verification`

*audits the assembled PEtab tables*

**Sees:**

- `intent`
- `experiment_description`
- `domain_packs`
- `entity_glossary`
- `observables_tsv`
- `conditions_tsv`
- `parameters_tsv`
- `data_flags`
- `audit_scope`
- `changed_entries`
- `overlay`

**Never:**

- measurement values — it audits the TABLES, and a table that matches the data by construction is not audited by seeing both

## `interpretation`

*reads the fitted result and says what it means*

**Sees:**

- `intent`
- `experiment_description`
- `instruction`
- `report_core`
- `residual_diagnostics`
- `diagnostics_instruction`
- `diagnostics_requested`
- `data_signals`

**Never:**

- the ground truth, under any name — `testcase/*/truth/` is not reachable from any payload and a run that saw it is void
- the supplied literature — it judges the fit from the data, and claims about what papers expect would steer how it reads the residuals

**May request:**

- more residual diagnostics, up to two rounds

## `revision_proposal`

*proposes the next round's structural move*

**Sees:**

- `intent`
- `experiment_description`
- `history`
- `evaluation_report`
- `move_grammar`
- `open_structural_questions`
- `structural_misfit_indicators`
- `rounds_left`
- `human_override`

**Never:**

- raw measurements — it revises from the MISFIT, which is where the data's disagreement with the model already lives

## `revision`

*proposes new model-space axes from what the fit could not explain and from the biology described for the system*

**Sees:**

- `intent`
- `experiment_description`
- `supplied_literature`
- `domain_packs`
- `retrieved_evidence`
- `evidence_instruction`
- `prior_reactions`
- `support_floor`
- `grounding_instruction`
- `known_facts`
- `assembly`
- `declared_axes`
- `untested_axes`
- `untested_first`
- `declared_constant_drift`
- `evaluation_report`
- `interpretation_hypotheses`
- `bound_pressure`
- `condition_attributes`
- `selection_table`
- `selected_model`
- `models_fitted_this_run`
- `misfit_evidence`
- `residual_diagnostics`
- `diagnostics_instruction`
- `diagnostics_requested`
- `research_instruction`
- `research_answered`
- `research_refused`
- `legal_reaction_ids`
- `redraft_instruction`

**Never:**

- the ground truth, under any name
- raw measurements — `misfit_evidence` and the residual diagnostics are the data's voice here

**May request:**

- more residual diagnostics, up to two rounds
- one literature search per expansion round, with research on (`research.max_requested_rounds`), run by the research role under the case's fence — or, with the knowledge module's output in the run, one targeted search of the knowledge role (`grounding.search.per_round`), graded by the engine and admitted at the floor
