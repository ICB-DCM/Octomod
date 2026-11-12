# The result record — every field, its type and its tier

<!-- GENERATED from octomod/result/ by tools/make_result_schema.py.
     Do not edit by hand: tests/result_schema_unit.py fails on drift. -->

One record per run — the run IS the file `runs/<id>.h5`, written group by
group as the engine runs (`runstore.py`, hdfdict; mkstd's `Hdf5Standard` produces
this schema); the JSON Schema a reader validates against without this
repository is [`result_schema.json`](result_schema.json).

**Tiers.** `core` is what a reader needs to understand the answer and is
always kept; `bulk` holds arrays, traces and tables; `audit` holds prompts,
raw replies and the ledger. A copy made with fewer tiers lists what it
dropped in each record's `elided`.

Schema version **2**. Every record allows extra
keys, so agent-authored content whose shape varies is kept whole.

## `RunResult`

The whole run.

| field | type | tier | description |
|---|---|---|---|
| `schema_version` | `int` | core |  |
| `run` | `RunMeta` | core | run_meta; empty when a record was built without one. |
| `intent` | `IntentRecord | None` | core |  |
| `rounds` | `dict[str, RoundRecord]` | core | "round_0", "round_1", … |
| `questions` | `list[QuestionRecord]` | core | The questions raised for the human. |
| `history` | `list[Any]` | core | The single-model loop's round history. |
| `ledger` | `list[LedgerEvent]` | audit | Every ledger row, verbatim. |
| `outcome` | `RunOutcome | None` | core |  |
| `timing` | `TimingRecord | None` | core | Where the wall time went; derived from the ledger when absent. |
| `input` | `dict[str, Any] | None` | core | What the run was started with: the case files the run reads, by relative path (text, or bytes), snapshotted before S0 — the lab note, the intent, the case file, the blocklist, data/, supplied/, stubs/ and the documents the supplied literature names; nothing else. |
| `input_source` | `dict[str, Any] | None` | core | Where `input` came from: the testcase, a previous run (started_from). |
| `input_pending` | `dict[str, Any] | None` | core | Set while an `input` snapshot or copy is being written; left behind only by a kill, which makes the next start take the snapshot again. |
| `fit_index` | `dict[str, Any] | None` | core | Fits in this record by fit key, for re-use (reuse.py). |
| `analysis` | `dict[str, Any] | None` | bulk | The analysis report's summary, when written. |
| `models_used` | `dict[str, Any] | None` | core | Which models the agent calls ran on, summed from the ledger at every pause and at run end (`provenance.models_used`): `by_model` (roles, calls, input/output tokens, cost) and `by_role` (models as resolved and as asked, effort). What they were SET UP with is `run.provenance.agents`. |
| `completeness` | `dict[str, Any] | None` | audit | What the record held at each checkpoint (`completeness.py`): per marker, decision, pause, run end and final write, what was looked for and what was missing, under `run/<checkpoint>`, `round_k/<module>/<unit>` and `round_k/decision_<module>/<unit>`; written before each checkpoint copy. |
| `phenomenology_raw` | `dict[str, Any] | None` | core | What the curves look like, read from the raw data files before any round ran, present when its acceptance rules all held; round 0's construction reads it, and the data module's own reading is checked against it. |

## `RunMeta`

`run`: what ran, on what (written at run start).

| field | type | tier | description |
|---|---|---|---|
| `run_id` | `str | None` | core | Filled from the file name when absent. |
| `engine_version` | `str | None` | core |  |
| `provenance` | `dict[str, Any] | None` | core | git state, package versions, lockfile sha. |
| `workflow` | `str | None` | core |  |
| `workflow_sha` | `str | None` | core |  |
| `testcase` | `str | None` | core |  |
| `testcase_sha` | `str | None` | core |  |
| `backend` | `str | None` | core |  |
| `auto` | `bool | None` | core |  |
| `max_rounds` | `int | None` | core |  |
| `from_module` | `str | None` | core |  |
| `spec_overlay` | `str | None` | core |  |
| `policy` | `str | None` | core |  |
| `policy_profile` | `str | None` | core |  |
| `policy_sha` | `str | None` | core |  |
| `started_at` | `str | None` | core | ts of the first run_start. |
| `n_invocations` | `int | None` | core | Number of run_start rows — one per resume. |
| `research_fence` | `dict[str, Any] | None` | core |  |

## `IntentRecord`

S0's frozen intent — `intent`.

| field | type | tier | description |
|---|---|---|---|
| `question` | `str | None` | core |  |
| `system` | `str | None` | core |  |
| `inference_target` | `str | None` | core | prediction \| parameter_values \| mechanism_discrimination. |
| `required_entities` | `list[Any]` | core |  |
| `required_predictions` | `list[Any]` | core |  |
| `perturbations` | `list[Any]` | core |  |
| `timescale` | `str | int | float | None` | core |  |
| `scope_exclusions` | `list[Any]` | core |  |
| `success_criteria` | `list[Any]` | core |  |
| `domain_packs` | `list[Any]` | core |  |
| `supplied_literature` | `list[Any]` | core |  |

## `RoundRecord`

One round: everything under `rounds/round_<k>`.

| field | type | tier | description |
|---|---|---|---|
| `index` | `int | None` | core | Filled from the key. |
| `shape` | `'single' | 'candidate_set'` | core |  |
| `directive` | `str | None` | core | The human's directive for the round. |
| `model` | `ModelRecord | None` | core |  |
| `space` | `ModelSpaceRecord | None` | core |  |
| `data` | `DataRecord | None` | core |  |
| `shared_assembly` | `AssemblyRecord | None` | core |  |
| `candidates` | `dict[str, CandidateRecord]` | core |  |
| `evaluation_core` | `dict[str, Any] | None` | core | S7's computed core, written before the interpretation. |
| `evaluation` | `EvaluationRecord | None` | core |  |
| `attribution` | `dict[str, Any] | None` | bulk |  |
| `interpretation_diagnostics` | `dict[str, Any] | None` | bulk |  |
| `base_model` | `ModelRecord | None` | core | The tested BASE of a two-call discrimination round; candidates are declared differences from it. |
| `base_model_previous` | `dict[str, Any] | None` | audit | The base before its last redraft, so the card can say what moved. |
| `residual_forms` | `dict[str, Any] | None` | core | The residual shape per observable. |
| `expansion_evidence` | `dict[str, Any] | None` | core | The research role's evidence snapshot taken before the expansion proposal (what that proposal could cite). |
| `estimation_settings` | `dict[str, Any] | None` | core | Round-level estimation settings shared by its candidates. |
| `superseded` | `dict[str, Any]` | audit | Groups a re-entered module set aside, by `<what>_<stamp>`. |
| `report_md` | `str | None` | audit |  |
| `selection` | `SelectionRecord | None` | core |  |
| `selection_files` | `dict[str, str]` | bulk | petab_select's interchange files, by name, as text. |
| `decisions` | `dict[str, DecisionRecord]` | core | By gate module: `…/decisions/<module>`. |
| `revision` | `RevisionRecord | None` | core |  |
| `expansion` | `ExpansionRecord | None` | core |  |
| `expansion_offer` | `dict[str, Any] | None` | core | The expansion offer the human answered. |
| `expansion_diagnostics` | `dict[str, Any] | None` | bulk | Diagnostics the agent asked for. |
| `expansion_support` | `dict[str, Any] | None` | core | With grounding on, each axis of the expansion offer annotated against the reaction dossier: {dossier_round, base, axes: {axis id: {reactions, label}}} — the reactions its patch adds to the base, each labelled as a model reaction is, and the weakest label, 'no new reaction', or 'not annotated' with the error. |
| `compile_feedback` | `dict[str, Any] | None` | core | The engine's one redraft of the observation model this round: the compile or fit failure it sent back, the candidate that failed, the observable ids the failure named and the finding as worded. |
| `research_requests` | `dict[str, Any]` | core | By request number: the frozen snapshot of each literature search the expansion agent asked for (items, dropped, questions, per_question, failed). |
| `agent_calls` | `dict[str, AgentCallRecord]` | core | By role. |
| `gates` | `dict[str, GateRecord]` | core | Round-level gates (s1 base, s2, s7). |
| `status` | `RoundStatusRecord | None` | core |  |
| `evidence` | `dict[str, Any] | None` | core | The research role's filtered items. |
| `supplied_evidence` | `dict[str, Any] | None` | core | The human's staged literature. |
| `reaction_evidence` | `dict[str, Any] | None` | core | The knowledge module's dossier as the run was started with it (copied into round 0 from the record's input): each reaction with its sources, its grade, whether it is required or essential, and its origin; the facts, the system summary, the mode. |
| `knowledge_search` | `dict[str, Any]` | core | By search number: each targeted search of the knowledge role the engine ran in the round — for a base that named what it lacks, for the expansions' `missing`, for an expansion, or on the person's `search:` at the expansion card (`requested_by`) — its questions, the graded reactions and facts it returned, its calls and cost, and what it admitted at which floor (`admission`). |
| `knowledge_admitted` | `list[Any] | None` | core | The reactions a targeted search admitted in the round, in order: each with origin `search`, who asked (`requested_by`), the question it answers, the search that found it and the floor it was admitted at; those construction asked for join the base's essential set, the others are reactions the expansions or an expansion may add. |
| `axis_refused` | `list[Any] | None` | core | The axes this round's expansion offer refused for the floor of the round it seeds, as the answer left them: each with the axis id, the round it was offered for, the floor, the added reactions below it (each with the entry it matches and that entry's band, or none) and the card's line. |
| `evidence_sources` | `dict[str, bytes] | None` | bulk | The documents S1 cached for audit, by cached file name: opaque bytes (a PDF, a page), never text. |
| `decisions_md` | `str | None` | audit | The decision record, as rendered. |

## `ModelRecord`

The model slot — `…/model` of a round or a candidate.

| field | type | tier | description |
|---|---|---|---|
| `antimony` | `str | None` | core | Antimony source. |
| `sbml` | `str | None` | core | SBML. |
| `mermaid` | `str | None` | core | Mermaid diagram. |
| `parameters` | `list[ParameterDecl]` | core |  |
| `network` | `dict[str, Any] | None` | core | Species, interactions. |
| `glossary` | `dict[str, Any] | None` | core | Entity glossary. |
| `build_report` | `dict[str, Any] | None` | core | Build decisions, sources, constants. |
| `encoding` | `dict[str, Any] | None` | core | The supermodel encoding. |
| `seed` | `dict[str, Any] | None` | core | Where this round's model came from: a revision move, or the round seed that carried the chosen model forward. |
| `assembly_overlay` | `list[Any] | dict[str, Any] | None` | core | Observation-axis patches applied at assembly. |
| `reaction_support` | `dict[str, Any] | None` | core | Every reaction of the model annotated against the most recent round's reaction dossier (`dossier_round` names it): user-provided, database-supported, literature-supported or inferred, with the matched entry, its origin, its band and its counted sources; for a candidate, the floor what it adds was held to (`floor`: the variants' floor in a discrimination round, the round's in a model-space search). |
| `producer` | `'engine' | 'agent:construction' | 'agent:data_extraction' | 'agent:assembly' | 'agent:observation' | 'agent:condition' | 'agent:research' | 'agent:construction_verification' | 'agent:assembly_verification' | 'agent:interpretation' | 'agent:revision_proposal' | 'agent:revision' | 'human' | 'policy' | 'user-supplied' | 'seeded-from-previous-round' | 'unknown'` | core |  |
| `files` | `list` | core | FileRefs of source files, with sha (legacy). |

## `ParameterDecl`

One row of `model/parameters` — the construction agent's table.

| field | type | tier | description |
|---|---|---|---|
| `id` | `str` | core |  |
| `nominal_value` | `float | None` | core |  |
| `lb` | `float | None` | core |  |
| `ub` | `float | None` | core |  |
| `unit` | `str | None` | core |  |
| `estimate` | `bool | None` | core |  |
| `evidence_tier` | `str | None` | core |  |
| `source` | `str | None` | core |  |

## `ModelSpaceRecord`

The declared model space and what became of it.

| field | type | tier | description |
|---|---|---|---|
| `axes` | `list[AxisRecord]` | core | The axes in the agent's priority order. |
| `declared` | `list[Any]` | core | Axes declared later, verbatim. |
| `dropped` | `list[Any]` | core | Dropped axes: id, reason, module. |
| `recommended_tier` | `dict[str, Any] | None` | core |  |
| `search_mode` | `dict[str, Any] | None` | core | How the round searches its space: {mode, source}. |
| `floor` | `dict[str, Any] | None` | core | The round's support floor: {band, step, source} — the band an essential reaction's grade must reach to enter the base, and who set it (human, rule, schedule, lowered). |
| `axis_support` | `dict[str, Any] | None` | core | With grounding on, each axis construction declared annotated against the reaction dossier and held to the variants' floor: {dossier_round, base, floor, axes: {axis id: {reactions, label}}}; an axis refused for that floor is in `dropped` (`refused_floor`) and in `declared`, from where an expansion round offers it again. In advisory mode nothing is refused: `mode` and `flagged` ({axis id: what it adds below the floor}) record what the card flags. |
| `candidates` | `list[Any]` | core | Candidates: id, label, rationale, assembly_overlay. |

## `AxisRecord`

One structural or observation axis of `space/axes`.

| field | type | tier | description |
|---|---|---|---|
| `id` | `str` | core |  |
| `kind` | `str | None` | core |  |
| `question` | `str | list[Any] | None` | core |  |
| `default` | `str | None` | core |  |
| `priority` | `int | None` | core |  |
| `priority_reason` | `str | list[Any] | None` | core |  |
| `on_antimony_patch` | `Any` | core |  |
| `on_assembly_patch` | `Any` | core |  |
| `adds_parameters` | `list[Any]` | core |  |
| `rationale` | `str | list[Any] | None` | core |  |
| `discriminating_evidence` | `str | list[Any] | None` | core |  |
| `declared_by` | `str | None` | core |  |
| `frozen` | `bool | None` | core | The last selection, not a deletion. |
| `support` | `dict[str, Any] | None` | core | An expansion axis with grounding on: the reactions its patch adds to the base, annotated against the reaction dossier, and their weakest label ({reactions, label}). |

## `DataRecord`

The data slot — `rounds/<k>/data`. Identical in every round of a run.

| field | type | tier | description |
|---|---|---|---|
| `measurements` | `Table | None` | bulk | The engine's long measurement table. |
| `raw` | `Table | None` | bulk | The raw measurements, when present. |
| `report` | `dict[str, Any] | None` | core | Mappings, labels, flags. |
| `signals` | `dict[str, Any] | None` | bulk | Data signals. |
| `design_summary` | `dict[str, Any] | None` | core | Design summary. |
| `phenomenology` | `dict[str, Any] | None` | core | What the curves look like, in words (data_phenomenology). |
| `producer` | `'engine' | 'agent:construction' | 'agent:data_extraction' | 'agent:assembly' | 'agent:observation' | 'agent:condition' | 'agent:research' | 'agent:construction_verification' | 'agent:assembly_verification' | 'agent:interpretation' | 'agent:revision_proposal' | 'agent:revision' | 'human' | 'policy' | 'user-supplied' | 'seeded-from-previous-round' | 'unknown'` | core |  |
| `n_rows` | `int | None` | core |  |

## `Table`

A columnar table: one dataset per column in HDF5, native for numbers.

| field | type | tier | description |
|---|---|---|---|
| `columns` | `list[str]` | core | Column names, in order. |
| `data` | `dict[str, list]` | core | Values by column, one list per column, row-aligned. |

## `AssemblyRecord`

`…/candidates/<id>/assembly` (or the round's `shared_assembly`): the merge's source

| field | type | tier | description |
|---|---|---|---|
| `observables` | `list[Any]` | core |  |
| `noise` | `list[Any]` | core |  |
| `scaling` | `list[Any]` | core |  |
| `conditions` | `list[Any]` | core |  |

## `CandidateRecord`

One fitted model of a round — `rounds/<k>/candidates/<id>`, or `_single`.

| field | type | tier | description |
|---|---|---|---|
| `id` | `str | None` | core | Filled from the key. |
| `axes_on` | `list[str]` | core |  |
| `label` | `str | None` | core |  |
| `rationale` | `str | None` | core |  |
| `model` | `ModelRecord | None` | core | None for `_single`: the round's model is this candidate's. |
| `assembly` | `AssemblyRecord | None` | core |  |
| `petab` | `PetabRecord | None` | core |  |
| `cost` | `CostRecord | None` | core |  |
| `estimation` | `EstimationRecord | None` | core |  |
| `starts` | `Table | None` | bulk | Per-start table of the multistart. |
| `multistart` | `dict[str, Any] | None` | bulk | The multistart as arrays, one per OptimizerResult field (`estimation.result_from_record` rebuilds the pypesto.Result). |
| `attempts` | `dict[str, Any]` | bulk | Earlier fits a refit superseded, by attempt number: estimation, starts, multistart. |
| `refit` | `dict[str, Any] | None` | core | Read so that records keeping the refit here still load; the engine writes it to `estimation_settings.refit`. |
| `optimizer_comparison` | `dict[str, Any] | None` | bulk |  |
| `optimizer_selection` | `dict[str, Any] | None` | core |  |
| `optimizer_compare_runs` | `dict[str, Any] | None` | bulk |  |
| `estimation_settings` | `dict[str, Any] | None` | core | The settings the fit ran with: declared, budget-gate choices, refit overrides. |
| `fit_key` | `dict[str, Any] | None` | core | What identifies this fit for re-use (reuse.py). |
| `probe_record` | `dict[str, Any] | None` | core | The cost probe as measured, so a budget answer does not re-run it. |
| `profiles` | `dict[str, Any] | None` | bulk | Persisted profile likelihoods, for re-use. |
| `profiles_timing` | `dict[str, Any] | None` | core | What each profile cost, for projections. |
| `structural_nulls` | `dict[str, Any] | None` | core | Parameter combinations no output depends on, at any value. |
| `structural_nulls_at_mle` | `dict[str, Any] | None` | core | The same, evaluated at the fitted optimum. |
| `assembly_overlay_applied` | `list[Any] | dict[str, Any] | None` | core | The overlay patches S3 applied: {patch, as}. |
| `budget_declined` | `dict[str, Any] | None` | core | The human's `n` at this candidate's re-asked budget gate (candidate, note, reasons, at): read back on a resume, so the candidate is dropped once and never asked again this round. |
| `decisions` | `dict[str, DecisionRecord]` | core | The candidate's own gate decisions, by module. |
| `gates` | `dict[str, GateRecord]` | core | By gate id — the candidate's own gates. |
| `dropped` | `LedgerEvent | None` | core | The candidate_dropped row, when it was dropped. |
| `markers` | `dict[str, Any]` | core | Marker name → payload, per candidate. |

## `PetabRecord`

The PEtab problem as fitted — `petab/*`, tables embedded.

| field | type | tier | description |
|---|---|---|---|
| `problem_yaml` | `dict[str, Any] | None` | core |  |
| `observables` | `Table | None` | bulk |  |
| `conditions` | `Table | None` | bulk |  |
| `measurements` | `Table | None` | bulk |  |
| `holdout_measurements` | `Table | None` | bulk |  |
| `parameters` | `Table | None` | bulk |  |
| `n_estimated` | `int | None` | core |  |
| `n_train` | `int | None` | core |  |
| `n_holdout` | `int | None` | core |  |
| `producer` | `'engine' | 'agent:construction' | 'agent:data_extraction' | 'agent:assembly' | 'agent:observation' | 'agent:condition' | 'agent:research' | 'agent:construction_verification' | 'agent:assembly_verification' | 'agent:interpretation' | 'agent:revision_proposal' | 'agent:revision' | 'human' | 'policy' | 'user-supplied' | 'seeded-from-previous-round' | 'unknown'` | core |  |

## `CostRecord`

The compile-and-probe slot (`…/candidates/<id>/cost`). The optimiser

| field | type | tier | description |
|---|---|---|---|
| `compile_s` | `float | None` | core |  |
| `objective_eval_s` | `float | None` | core |  |
| `median_start_s` | `float | None` | core |  |
| `n_probe_starts` | `int | None` | core |  |
| `probe_fvals` | `list[float]` | core |  |
| `proposed_n_starts` | `int | None` | core |  |
| `approved_n_starts` | `int | None` | core | From the cost marker: what the human approved. |
| `projected_wall_s` | `float | None` | core |  |
| `engine` | `str | None` | core |  |
| `probe_engine` | `dict[str, Any] | None` | core | How the probe's starts ran (here, or dispatched to `n_workers` processes, and why), each start's wall and CPU, and the probe's wall against its one-at-a-time work (`speedup`). `median_start_s` is serial-equivalent: a start's wall when it ran alone, its CPU when others ran beside it. |
| `solver_settings` | `dict[str, Any] | None` | core |  |
| `tolerance_agreement` | `dict[str, Any] | None` | bulk |  |
| `sensitivity_probe` | `dict[str, Any] | None` | bulk |  |
| `steady_state` | `dict[str, Any] | None` | core |  |

## `EstimationRecord`

The estimation slot's summary (`…/candidates/<id>/estimation`), as S6

| field | type | tier | description |
|---|---|---|---|
| `optimizer` | `str | None` | core |  |
| `seed` | `int | None` | core |  |
| `n_starts` | `int | None` | core |  |
| `n_data` | `int | None` | core |  |
| `x_names` | `list[str]` | core |  |
| `best_fval` | `float | None` | core |  |
| `best_grad_norm` | `float | None` | core |  |
| `best_x_unscaled` | `dict[str, float]` | core |  |
| `fvals` | `list[float]` | bulk | Sorted final objective values. |
| `ensemble` | `list[Any]` | bulk |  |
| `ensemble_delta_nllh` | `float | None` | core |  |
| `at_bounds` | `list[Any]` | core |  |
| `near_bounds` | `list[Any]` | core |  |
| `near_bound_fraction` | `float | None` | core |  |
| `estimated_inner` | `dict[str, Any]` | core |  |
| `starts` | `list[Any] | None` | bulk | The per-start rows, as S6 lists them. |
| `producer` | `'engine' | 'agent:construction' | 'agent:data_extraction' | 'agent:assembly' | 'agent:observation' | 'agent:condition' | 'agent:research' | 'agent:construction_verification' | 'agent:assembly_verification' | 'agent:interpretation' | 'agent:revision_proposal' | 'agent:revision' | 'human' | 'policy' | 'user-supplied' | 'seeded-from-previous-round' | 'unknown'` | core |  |

## `DecisionRecord`

A human (or policy, or auto) answer at a gate, with what the engine read

| field | type | tier | description |
|---|---|---|---|
| `module` | `str` | core |  |
| `question` | `str | None` | core |  |
| `approved` | `bool | None` | core |  |
| `note` | `str` | core |  |
| `mode` | `str | None` | core | interactive \| file \| auto \| policy \| recorded. |
| `signed` | `str | None` | core | How the signature reads: a human, policy(<sha>), auto. |
| `at` | `str | None` | core |  |
| `round` | `int | None` | core |  |
| `consequences` | `list[str] | None` | core |  |
| `source_file` | `str | None` | core | The decision file this was read from, if any. |

## `GateRecord`

One deterministic gate verdict — `gates.GateResult` plus where it ran.

| field | type | tier | description |
|---|---|---|---|
| `gate_id` | `str` | core | The gate's id, e.g. estimation_waterfall_plateau. |
| `tier_level` | `str` | core | T0 \| T1 \| T2 \| T2prime \| T3, as the gate declares. |
| `passed` | `bool` | core |  |
| `blocking` | `bool` | core |  |
| `value` | `float | int | bool | str | list[float] | list[str] | dict[str, Any] | None` | core | The computed quantity. |
| `threshold` | `float | int | bool | str | list[float] | list[str] | dict[str, Any] | None` | core | The declared threshold it was compared against. |
| `detail` | `str` | core |  |
| `advisory_findings` | `list[Any]` | core |  |
| `solver_settings` | `SolverSettings | None` | core |  |
| `module` | `str | None` | core | Module that ran the gate. |
| `round` | `int | None` | core |  |
| `candidate` | `str | None` | core | Candidate id when the gate ran per candidate. |
| `at` | `str | None` | core | ISO timestamp, from the ledger. |

## `SolverSettings`

The integrator settings a gate verdict was reached under.

| field | type | tier | description |
|---|---|---|---|
| `solver` | `str | None` | core |  |
| `atol` | `float | None` | core |  |
| `rtol` | `float | None` | core |  |
| `maxsteps` | `int | None` | core |  |

## `LedgerEvent`

One ledger row, verbatim. Extra keys are the row's payload.

| field | type | tier | description |
|---|---|---|---|
| `ts` | `str` | core |  |
| `round` | `int` | core |  |
| `module` | `str` | core |  |
| `event` | `str` | core |  |

## `EvaluationRecord`

The evaluation slot (`rounds/<k>/evaluation`): S7's report — the

| field | type | tier | description |
|---|---|---|---|
| `goal` | `str | None` | core |  |
| `best_fval` | `float | None` | core |  |
| `n_ensemble` | `int | None` | core |  |
| `fit` | `list[Any]` | core | Per observable × condition fit rows. |
| `chi2_per_dof` | `float | None` | core |  |
| `parameters` | `dict[str, Any] | None` | core |  |
| `estimated_inner` | `dict[str, Any] | None` | core |  |
| `misfit_evidence` | `dict[str, Any] | None` | core |  |
| `declared_constants` | `dict[str, Any] | None` | core |  |
| `latent_states` | `dict[str, Any] | None` | bulk |  |
| `identifiability` | `dict[str, Any] | None` | core |  |
| `holdout` | `dict[str, Any] | None` | core |  |
| `profiles` | `dict[str, Any] | None` | bulk |  |
| `prediction_uncertainty` | `dict[str, Any] | None` | bulk |  |
| `noise_check` | `dict[str, Any] | None` | core |  |
| `computed_cannot_distinguish` | `list[Any]` | core |  |
| `computed_nonetheless_determined` | `list[Any]` | core |  |
| `interpretation` | `dict[str, Any] | None` | core | The interpretation agent's block. |
| `t2prime_passed` | `bool | None` | core |  |
| `discrimination` | `dict[str, Any] | None` | core | Search rounds: the selection table and winner. |
| `attribution` | `dict[str, Any] | None` | bulk |  |

## `SelectionRecord`

The selection slot (`rounds/<k>/selection`): the criterion values and

| field | type | tier | description |
|---|---|---|---|
| `criterion` | `str | None` | core |  |
| `winner` | `str | None` | core |  |
| `decisive` | `bool | None` | core |  |
| `values` | `dict[str, Any]` | core | Per model: the criterion values. |
| `weights` | `dict[str, Any]` | core |  |
| `tool` | `str | None` | core |  |
| `version` | `str | None` | core |  |
| `model_space_sha` | `str | None` | core |  |
| `models` | `list[Any]` | bulk | petab_select models.yaml. |
| `problem_yaml` | `dict[str, Any] | None` | core |  |
| `indistinguishable` | `list[Any]` | core |  |
| `undecided_axes` | `list[Any]` | core |  |

## `RevisionRecord`

`rounds/<k>/revision` — the move the loop took out of this round, with the

| field | type | tier | description |
|---|---|---|---|
| `move` | `dict[str, Any] | None` | core | {type, args}; None means stop. |
| `motivated_by` | `str | None` | core |  |
| `expected_effect` | `str | None` | core |  |
| `why` | `str | None` | core | When no move: the reason. |
| `config_hash` | `str | None` | core |  |
| `best_fval` | `float | None` | core |  |

## `ExpansionRecord`

The round's expansion decision (`rounds/<k>/expansion`). The offer the

| field | type | tier | description |
|---|---|---|---|
| `expanded` | `bool | None` | core |  |
| `next_round` | `int | None` | core |  |
| `from_winner` | `str | None` | core |  |
| `expanded_from` | `str | None` | core |  |
| `base_was_the_agents_recommendation` | `bool | None` | core |  |
| `axes` | `list[str]` | core |  |
| `carried_undecided` | `list[str]` | core |  |
| `base` | `str | None` | core |  |
| `not_bought_by_ceiling` | `list[str]` | core |  |
| `why` | `str | None` | core |  |
| `floor` | `dict[str, Any] | None` | core | With grounding on, the support floor of the round the offer seeds, as the answer left it: {band, step, source} (schedule, or human when the person set it at the card). |
| `refused_for_floor` | `list[str]` | core | The axes the offer refused for that floor (the round's `axis_refused` says why). |

## `AgentCallRecord`

Everything archived about one agent role in one round.

| field | type | tier | description |
|---|---|---|---|
| `role` | `str | None` | core | Filled from the key. |
| `reply` | `dict[str, Any] | None` | core | The accepted, validated JSON object. |
| `prompt` | `str | None` | audit | The exact prompt of the last call. |
| `prompt_gate` | `GateRecord | None` | core | The agent_prompt_bytes gate for that prompt. |
| `attempts` | `list[AttemptRecord]` | audit |  |
| `calls` | `list[LedgerEvent]` | core | The ledger's agent_call rows for this role in this round. |
| `redrafts` | `list[LedgerEvent]` | core | The ledger's redraft rows for this role. |
| `cost_usd` | `float | None` | core | Sum of cost_usd over `calls`, when reported. |
| `pinned` | `dict[str, Any] | None` | core | A reply pinned for re-use (the interpretation). |
| `dossier` | `Any` | audit | The retry dossier: earlier attempts and why each failed. |
| `prompt_misses` | `dict[str, Any]` | audit | Why a cached reply was NOT reused: both prompts and the first difference. |
| `replies` | `dict[str, Any]` | audit | Per attempt: the raw reply, and `timeout`/`killed` with partial output. |
| `base_key` | `Any` | core | expansion: the base model the candidates were written against. |
| `overlay_audits` | `dict[str, Any]` | bulk | assembly_verification: overlay audits by content sha. |
| `fallback_applied` | `Any` | core | A deterministic fallback the engine applied to this role's reply. |

## `AttemptRecord`

One raw reply of an agent, accepted or not.

| field | type | tier | description |
|---|---|---|---|
| `attempt` | `int` | core |  |
| `text` | `str | None` | audit | The raw reply text. |
| `gate_failures` | `list[str]` | core |  |

## `RoundStatusRecord`

Which slots the round has, validated by what — computed from the

| field | type | tier | description |
|---|---|---|---|
| `validations` | `dict[str, Any]` | core | Per candidate (or `_round`) and slot: the battery that validated a supplied or seeded slot on entry. |
| `markers` | `dict[str, Any]` | core | Marker name → its JSON payload (producer, validated_by, and the `files` shas stamped when the marker was set). |
| `slots` | `dict[str, Any]` | core | Per slot: key, files (part + sha16), present, producer, validated_by/at, drifted — computed from the record and the markers, so there is no separate index file. |
| `candidates` | `dict[str, Any]` | core | The same, per candidate. |
| `updated_at` | `str | None` | core |  |

## `QuestionRecord`

A structural question an agent raised for the human (`questions`).

| field | type | tier | description |
|---|---|---|---|
| `id` | `str` | core |  |
| `raised_by` | `str | None` | core |  |
| `raised_round` | `int | None` | core |  |
| `topic` | `str | None` | core |  |
| `question` | `str | None` | core |  |
| `confidence` | `str | None` | core |  |
| `human_answer` | `str | None` | core |  |
| `status` | `str | None` | core |  |

## `RunOutcome`

The `run_end` ledger row, or its absence.

| field | type | tier | description |
|---|---|---|---|
| `outcome` | `str | None` | core | completed \| completed_t2prime_unmet \| stopped \| interrupted; None while the run is still open. |
| `reason` | `str | None` | core |  |
| `winner` | `str | None` | core |  |
| `decisive` | `bool | None` | core |  |
| `at` | `str | None` | core |  |
| `final_round` | `int | None` | core |  |

## `TimingRecord`

Where the run's wall and CPU time went (`timing`).

| field | type | tier | description |
|---|---|---|---|
| `run_wall_s` | `float | None` | core |  |
| `run_cpu_s` | `float | None` | core | CPU over every session (process + children): what the work cost, comparable across core counts and load. |
| `parallelism` | `float | None` | core | run_cpu_s / run_wall_s. |
| `machine` | `dict[str, Any] | None` | core | What it ran on: os, arch, python, cpu_model, cpu_count, memory_gb, load_avg_1m (no hostname: the record is shared). |
| `accounted_s` | `float | None` | core |  |
| `residual_s` | `float | None` | core | run_wall_s − accounted_s: the gap after a killed session (= unaccounted_s), else zero. |
| `unaccounted_s` | `float | None` | core | Wall after a session that lost its end row, before the next process: nobody was asked anything, the process died. |
| `n_sessions` | `int | None` | core |  |
| `waiting_for_human_s` | `float | None` | core | Between sessions: a human (or the front end) at a file gate. |
| `sessions` | `list[TimingSession]` | core |  |
| `by_category` | `dict[str, Any]` | core | agent (with api_s, tools_s), compute, render, human, io, record, engine, waiting_for_human, unaccounted → {wall_s, cpu_s, n, parallelism; compute also the work units and per-unit costs}. |
| `by_module` | `dict[str, Any]` | core |  |
| `by_round` | `dict[str, Any]` | core |  |
| `agents` | `dict[str, Any]` | core | Per role: n, wall_s, api_s (model), tools_s. |
| `compute` | `dict[str, Any]` | core | Per block: wall_s, cpu_s, parallelism, the work units (n_starts, n_fval, n_grad, n_hess, n_points, n_profiles, n_procs) and cpu_s/wall_s per start, fval, point. |
| `spans` | `list[Any]` | bulk | Every span: category, name, module, round, candidate, t0, t1, wall_s, cpu_s, depth, n_children, children_wall_s/cpu_s, self_wall_s/cpu_s, leaf, ok, late, and the block's detail (api_s, tools_s, n_starts, …). |
| `note` | `str | None` | core |  |
| `written_at` | `str | None` | core |  |

## `TimingSession`

One process of the run.

| field | type | tier | description |
|---|---|---|---|
| `index` | `int` | core |  |
| `started` | `float` | core | Epoch seconds: the process's start (its first row minus startup_s). |
| `startup_s` | `float | None` | core | Imports and set-up before the run_start row. |
| `ended` | `float | None` | core |  |
| `ended_by` | `str | None` | core | run_end:<outcome> \| gate_pending \| open \| killed (no end row). |
| `wall_s` | `float | None` | core |  |
| `timed_s` | `float | None` | core | The leaf spans inside this session, summed. |
| `engine_s` | `float | None` | core | wall_s − timed_s: the engine between timed blocks. |
| `cpu_s` | `float | None` | core | The process's CPU (self + children, user + sys) at its end row. |
| `timed_cpu_s` | `float | None` | core |  |
| `engine_cpu_s` | `float | None` | core |  |
| `parallelism` | `float | None` | core | cpu_s / wall_s. |
| `cpu_overshoot_s` | `float | None` | core | When the spans' CPU exceeds the process's: a child reaped inside a span that started before it. |
| `started_iso` | `str | None` | core |  |

## `FileRef`

A file the record refers to but does not embed, with its content hash

| field | type | tier | description |
|---|---|---|---|
| `path` | `str` | core | The legacy file path (relative to the legacy run directory) that a transcribed entry referred to. |
| `sha16` | `str | None` | core | First 16 hex digits of the sha256 of the text. |

## `Record`

Base of every record: extras allowed, an `elided` list for pruning.

| field | type | tier | description |
|---|---|---|---|

## `CandidateDecl`

One row of `space/candidates`: a model the round will fit.

| field | type | tier | description |
|---|---|---|---|
| `id` | `str` | core |  |
| `label` | `str | None` | core |  |
| `rationale` | `str | None` | core |  |
| `assembly_overlay` | `list[Any]` | core |  |
