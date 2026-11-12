"""Which context keys each agent role is shown.

`ROUTING` is the source: `enforce()` runs at the one seam every agent call passes
through (`RunContext.call`), and `docs/ROUTING.md` is generated from the table.
`construction` sees no measurement values, data preview, noise statistic or
design summary: a structural proposal that has seen the data is not a prior.
What it may see of the data is `data_phenomenology` — shape words and
timescales rounded to one significant figure, no values. `sees` is the
allow-list; `never` only records why a key is absent.
"""

from __future__ import annotations

# Granted to every role: the retry dossier, the human's own words, and the role's
# own previous reply, which was made only from what this table lets it see.
COMMON = (
    "attempt_history",
    "human_feedback",
    "human_feedback_instruction",
    "previous_attempt_errors",
    "previous_reply",
)

ROUTING: dict[str, dict] = {
    "research": {
        "sees": (
            "intent",
            "experiment_description",
            # the call before an expansion only (`research.at_expansion`): the
            # selected model's species and reactions, one line each, the misfit
            # indicator sentences, and what to look for
            "model_summary",
            "misfit_summary",
            "instruction",
            # the search the expansion agent asks for: its 1-3 questions, each
            # naming a mechanism or observation to look for
            "questions",
            "restrictions",
        ),
        "never": (
            "the data, in any form — no measurement, residual or fitted "
            "parameter value; before construction it sees nothing of a fit, and "
            "before an expansion only the misfit indicator sentences the gate "
            "cards print (each names an observable and its indicator's own "
            "statistic, a sigma ratio or a chi2/dof), which say WHERE the "
            "selected model fails, so the search can look for what it lacks "
            "there",
            "the target paper (enforced separately by the cutoff and exclusions "
            "in `restrictions`)",
        ),
        "may_request": (
            "WebSearch / WebFetch, one of the two online roles (with "
            "`knowledge`, whose calls are online only when asked)",
        ),
        "why": "literature evidence for construction, gathered before any fit, "
        "and for the expansion agent, about mechanisms the selected model lacks "
        "and about the questions that agent asks",
    },
    "knowledge": {
        "sees": (
            "intent",
            "experiment_description",
            # the intent's required reactions with their engine ids (`req_k`),
            # so every one gets an entry of its own
            "required_reactions",
            # the human's staged papers, which it may cite for a reaction or a
            # fact with its own classification
            "supplied_literature",
            "restrictions",
            # `survey` before the run, `targeted` inside it
            "mode",
            # targeted mode: the conversions asked about (by construction for
            # its base, by the expansions, by an expansion or the person at its
            # card), the model as it stands (species and reactions, one line
            # each) and the entries it already carries
            "questions",
            "model_summary",
            "essential_ids",
        ),
        "never": (
            "the data, in any form — no measurement, residual or fitted value: "
            "it says what is known about the system, before the intent is frozen "
            "and, inside a run, about what a model lacks",
            "a grade of its own making — it classifies each source "
            "(`evidence_kind`, `context_match`, `stance`) and the engine grades "
            "every reaction and fact from the declared rule table "
            "(`grounding.grading`)",
            "the target paper (enforced separately by the cutoff and exclusions "
            "in `restrictions`)",
        ),
        "may_request": (
            "WebSearch / WebFetch in online mode only — the call's grant; an "
            "offline call is granted nothing — fenced exactly like research",
        ),
        "why": "what is known about the system before the intent is frozen — the "
        "essential reactions, the facts a model needs, their sources — and, "
        "inside a run, the conversions a base under construction lacks, a "
        "round's expansions add or an expansion's axes would add",
    },
    "knowledge_verification": {
        "sees": (
            # each counting evidence item: what it claims and how the knowledge
            # role classified it
            "items",
            # the cached document's own text around each item's quote, bounded
            "excerpts",
        ),
        "never": (
            "the intent, the lab note, the question and the data — it re-reads "
            "each source's own text, not the problem the source is cited for",
            "a grade — the engine grades after both classifications, and keeps "
            "the lower where they disagree",
        ),
        "may_request": (),
        "why": "a second, advisory reading of each source the knowledge module "
        "cites, from the document's text rather than the agent's claim",
    },
    "construction": {
        "sees": (
            "intent",
            "experiment_description",
            "domain_packs",
            "retrieved_evidence",
            "evidence_instruction",
            # with the knowledge module: the base it builds (the essential
            # reactions with their origin, grade and counting evidence), the
            # support floor in words, what is known about the system, and the
            # instruction for the run's grounding mode
            "essential_reactions",
            "support_floor",
            "knowledge_summary",
            "grounding_instruction",
            # advisory mode only: the whole dossier as prior knowledge, the
            # entries outside the base set candidates construction may use
            "prior_reactions",
            # the engine's finding when it asks again after a base failed its
            # essential set and a targeted search answered what it named missing
            "engine_feedback",
            "engine_feedback_instruction",
            "supplied_network",
            "instruction",
            "instruction_mechanism_discrimination",
            "revision_directive",
            "previous_model_antimony",
            "minimal_repair",
            # the knowledge module's facts meant for construction (abundances,
            # rates, stoichiometries, known responses), each with its id
            "known_facts",
            # the curves in words: shape, timescale to one significant figure,
            # level against control, monotonicity in dose; held-out conditions
            # are not described
            "data_phenomenology",
        ),
        "never": (
            "measurement values — `data_file_previews`, the long table, any "
            "column of numbers. `data_phenomenology` is allowed because it "
            "carries none: a modeller reads shape and timescale off a plot "
            "before drawing a network, while values would turn the hypothesis "
            "into a fit",
            "`data_signals` — a noise statistic is observation-model evidence "
            "and says nothing about mechanism",
            "`design_summary` — measurement metadata, excluded so that what "
            "construction sees of the data stays one thing: the curves in words",
            "residuals, selection tables, anything downstream of a fit (that is "
            "`revision_proposal`'s and `revision`'s job)",
        ),
        "may_request": (),
        "why": (
            "proposes mechanism from prior knowledge, blind to the data's values "
            "and shown only what its curves look like"
        ),
    },
    "expansion": {
        "sees": (
            "intent",
            "experiment_description",
            "domain_packs",
            "retrieved_evidence",
            "evidence_instruction",
            "base_model",
            "base_changed_instruction",
            "instruction",
            # with the knowledge module: the base's essential set, every
            # reaction the dossier and the round's searches describe with its
            # origin and grade, the floor a variation adds a reaction at, what
            # is known about the system, and the instruction that says a
            # conversion below the floor is refused unless a search raises it
            "essential_reactions",
            "prior_reactions",
            "variants_floor",
            "knowledge_summary",
            "grounding_instruction",
            # the knowledge module's facts meant for construction, which the
            # expansions build on
            "known_facts",
        ),
        "never": (
            "measurement values, the data preview, `data_signals` or the "
            "design summary — the same exclusion as construction, for the same "
            "reason",
            "residuals or anything downstream of a fit",
        ),
        "may_request": (),
        "why": "writes each candidate as a declared difference from the tested base",
    },
    "construction_verification": {
        "sees": (
            "intent",
            "experiment_description",
            "network",
            "antimony",
            "build_report",
            # a discrimination round's candidates: declared differences or full
            # models, no data
            "candidates",
            # with the knowledge module's output in the run: the facts routed to
            # construction and the parameters that cite one
            "known_facts",
            "cited_parameters",
        ),
        "never": (
            "the data — it audits the draft against what was ASKED for, not "
            "against what was measured; a fit is the engine's job",
        ),
        "may_request": (),
        "why": "audits the construction reply against its own brief",
    },
    "data_extraction": {
        "sees": (
            "intent",
            "experiment_description",
            "data_file_previews",
            "design_summary",
            "battery_feedback",
        ),
        "never": (
            "the model — an extraction that knows the mechanism can label a "
            "column to suit it",
        ),
        "may_request": (),
        "why": "reads the raw files into the long table's labels",
    },
    "observation": {
        "sees": (
            "intent",
            "experiment_description",
            "domain_packs",
            "entity_glossary",
            "model_summary",
            "data_labels",
            "data_signals",
            "supplied_literature",
            # the knowledge module's facts meant for the observation model:
            # what an assay measures, its detection floor, its error structure
            "known_facts",
            "battery_feedback",
            # a compile failure that names this role's block, as the engine's
            # finding: the error and the observable rows the compiler read
            "engine_feedback",
            "engine_feedback_instruction",
        ),
        "never": (
            "raw measurement values — it is shown the SIGNALS computed from "
            "them, which is the same evidence without the temptation to "
            "read a curve and propose a mechanism",
        ),
        "may_request": (),
        "why": "maps model entities to measured quantities, and picks the noise model",
    },
    "condition": {
        "sees": (
            # the conditions it encodes are the intent's perturbations
            "intent",
            "experiment_description",
            "entity_glossary",
            "model_summary",
            "condition_labels",
            "observation_draft",
            "design_summary",
            # construction's view of the model's starting point, which the
            # pre-equilibration decision is made against
            "basal_state",
            # the knowledge module's facts meant for the encoding: how a
            # perturbation enters, which population expresses what
            "known_facts",
            "battery_feedback",
            # the same finding when it is addressed to the observation model:
            # the encoding is re-asked against the revised draft and told to
            # keep its own reply
            "engine_feedback",
            "engine_feedback_instruction",
        ),
        "never": (
            "measurement values — the encoding follows the DESIGN, and the "
            "design summary is exactly the part of the data that is design",
        ),
        "may_request": (),
        "why": "turns the experimental design into PEtab conditions",
    },
    "assembly_verification": {
        "sees": (
            "intent",
            "experiment_description",
            "domain_packs",
            "entity_glossary",
            "observables_tsv",
            "conditions_tsv",
            "parameters_tsv",
            "data_flags",
            "audit_scope",
            "changed_entries",
            "overlay",
        ),
        "never": (
            "measurement values — it audits the TABLES, and a table that "
            "matches the data by construction is not audited by seeing both",
        ),
        "may_request": (),
        "why": "audits the assembled PEtab tables",
    },
    "interpretation": {
        "sees": (
            "intent",
            # the lab note: without it a known artefact can be read as a mechanism
            "experiment_description",
            "instruction",
            "report_core",
            "residual_diagnostics",
            "diagnostics_instruction",
            "diagnostics_requested",
            "data_signals",
        ),
        "never": (
            "the ground truth, under any name — `testcase/*/truth/` is not "
            "reachable from any payload and a run that saw it is void",
            "the supplied literature — it judges the fit from the data, and "
            "claims about what papers expect would steer how it reads the "
            "residuals",
        ),
        "may_request": ("more residual diagnostics, up to two rounds",),
        "why": "reads the fitted result and says what it means",
    },
    "revision_proposal": {
        "sees": (
            "intent",
            "experiment_description",  # the lab note
            "history",
            "evaluation_report",
            "move_grammar",
            "open_structural_questions",
            "structural_misfit_indicators",
            "rounds_left",
            "human_override",
        ),
        "never": (
            "raw measurements — it revises from the MISFIT, which is where the "
            "data's disagreement with the model already lives",
        ),
        "may_request": (),
        "why": "proposes the next round's structural move",
    },
    "revision": {
        "sees": (
            "intent",
            # the lab note: which residuals it already explains (drift, artefacts)
            "experiment_description",
            # after the first round this role proposes every new mechanism
            "supplied_literature",
            # the biology construction was given: the intent's domain packs,
            # and (research on) what the research role found, just before this
            # call, about mechanisms described for the system that the selected
            # model lacks
            "domain_packs",
            "retrieved_evidence",
            "evidence_instruction",
            # with grounding on: the reaction dossier construction was given,
            # the support floor of the round its axes are fitted in, and the
            # instruction that says what an axis does with them
            "prior_reactions",
            "support_floor",
            "grounding_instruction",
            # the knowledge module's facts meant for the mechanisms tested
            # after a first fit
            "known_facts",
            "assembly",
            "declared_axes",
            "untested_axes",
            "untested_first",
            "declared_constant_drift",
            "evaluation_report",
            # the interpreter's hypotheses and open questions: suggestions only
            "interpretation_hypotheses",
            # fitted parameters at a bound, and how hard the fit presses on it
            "bound_pressure",
            # the data's condition attributes: what a split_parameter axis may
            # split by
            "condition_attributes",
            "selection_table",
            "selected_model",
            "models_fitted_this_run",
            "misfit_evidence",
            "residual_diagnostics",
            "diagnostics_instruction",
            "diagnostics_requested",
            # the literature search it may ask for: whether it may, the
            # questions a search answered (its items join retrieved_evidence),
            # and why a request was refused
            "research_instruction",
            "research_answered",
            "research_refused",
            "legal_reaction_ids",
            "redraft_instruction",
        ),
        "never": (
            "the ground truth, under any name",
            "raw measurements — `misfit_evidence` and the residual diagnostics "
            "are the data's voice here",
        ),
        "may_request": (
            "more residual diagnostics, up to two rounds",
            "one literature search per expansion round, with research on "
            "(`research.max_requested_rounds`), run by the research role under "
            "the case's fence — or, with the knowledge module's output in the "
            "run, one targeted search of the knowledge role "
            "(`grounding.search.per_round`), graded by the engine and admitted "
            "at the floor",
        ),
        "why": "proposes new model-space axes from what the fit could not explain "
        "and from the biology described for the system",
    },
}


class RoutingViolation(Exception):
    """A payload reached a role the table does not grant it."""


def allowed(role: str) -> frozenset[str]:
    if role not in ROUTING:
        raise KeyError(f"no routing row for role {role!r} — add one to ROUTING")
    return frozenset(ROUTING[role]["sees"]) | frozenset(COMMON)


def violations(role: str, keys) -> list[str]:
    return sorted(set(keys) - allowed(role))


def enforce(role: str, keys) -> None:
    """Raise RoutingViolation when `role` is handed a key the table does not grant.

    Called at the single agent seam, `RunContext.call`.
    """
    bad = violations(role, keys)
    if not bad:
        return
    raise RoutingViolation(
        f"role {role!r} was handed {bad}, which docs/ROUTING.md does not grant "
        f"it. Either the payload is wrong, or the table needs a row change and "
        f"a reason — do not add the key silently.\n"
        f"  granted: {sorted(allowed(role))}"
    )


def render_markdown() -> str:
    """Render `docs/ROUTING.md` from the table (written by tools/make_routing.py)."""
    out = [
        "# ROUTING — what each agent role is shown",
        "",
        "<!-- GENERATED from octomod/agents/routing.py by tools/make_routing.py.",
        "     Do not edit by hand: tests/routing_unit.py fails on drift. -->",
        "",
        "Every agent call in this engine passes through one seam",
        "(`RunContext.call`), and that seam calls `routing.enforce()`. A payload",
        "key that does not appear below cannot reach the role at all — the run",
        "stops with the key named.",
        "",
        f"Granted to every role: `{'`, `'.join(COMMON)}` — the retry dossier and",
        "the human's own words, neither of which carries data.",
        "",
        "`intent` is the frozen `intent` record, which is written WITHOUT",
        "`supplied_literature`: the human's literature is frozen in its own",
        "run-level record and reaches exactly four roles — `construction`, as",
        "`retrieved_evidence` with `origin: human`, `knowledge`, as",
        "`supplied_literature` (it may cite a paper for a reaction or a fact",
        "with its own classification), `observation`, as",
        "`supplied_literature` (measurement and noise details in a paper matter",
        "to it), and `revision`, as `supplied_literature` (after the first",
        "round it proposes the new mechanisms; the interpreter does not get it,",
        "so it judges the fit from the data). `construction_verification` does not see it",
        "— an auditor that reads the same claims is not independent of them.",
        "",
        "`battery_feedback` is the one key a battery failure adds: the",
        "failing check verbatim, the role's OWN block for the implicated ids, the",
        "merged table rows for them, and the legal vocabulary — never a",
        "measurement value for a role that does not already see them.",
        "",
        "`engine_feedback` is what a compile failure that names the observation",
        "model adds, once per round: the failure verbatim and the observable",
        "rows the compiler read, marked as the engine's finding and the role it",
        "is addressed to — never under the human's keys.",
        "",
        "Reaching NO role, by construction: the repository — no `CLAUDE.md`,",
        "`.claude/` or `.git` in the ancestor chain of the call's cwd, by cwd",
        "— and any MCP server — none, by flag: `--strict-mcp-config` with",
        "no `--mcp-config` on every call. Both are asserted token-free in",
        "`tests/call_cwd_unit.py`; the live probes that spend usage are",
        "`tests/isolation_probe.py` and `tools/probe_mcp_isolation.py`.",
        "",
    ]
    for role, row in ROUTING.items():
        out += [f"## `{role}`", "", f"*{row['why']}*", "", "**Sees:**", ""]
        out += [f"- `{k}`" for k in row["sees"]]
        out += ["", "**Never:**", ""]
        out += [f"- {n}" for n in row["never"]]
        if row["may_request"]:
            out += ["", "**May request:**", ""]
            out += [f"- {m}" for m in row["may_request"]]
        out.append("")
    return "\n".join(out).rstrip() + "\n"
