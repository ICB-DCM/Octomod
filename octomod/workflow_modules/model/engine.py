"""S1 — model construction. Highest agent freedom, hardest gate ladder.

The agent writes Antimony; the ladder is builds -> SBML valid -> references
resolve -> simulates -> simulates across the bounds box. A failed draft goes
back with the dossier of every attempt, within a budget the human can extend.
A supplied model (the round's `model/antimony`, or `model/network`) skips the
agent, never the gates. For mechanism discrimination every candidate runs the
full ladder; S7 discriminates by information criteria, S1 only guarantees every
candidate is a real model.

Everything this module reads and writes is in the run record, by key:
the round's model at `model/*`, a candidate's at `candidates/<id>/model/*`,
the space at `space/*`, the decisions at `decisions/*`, the agent calls at
`agent_calls/<role>/*`; a two-call discrimination round's tested base at
`base_model/*`. Only the rendered model report is a file.
"""

from __future__ import annotations

import re
from pathlib import Path

from octomod.gates import run_gate_set
from octomod.gates.build_gates import make_build_gates
from octomod.gates.sim_gates import make_sim_gates
from octomod.orchestration import timing
from octomod.orchestration.interaction import gate_note, humangate
from octomod.orchestration.interaction import human_redraft as _hr
from octomod.orchestration.run_context import (
    ModuleFailure,
    NoteRefused,
    RunContext,
    as_candidate,
    candidate_work,
)
from octomod.result import node as _tree
from octomod.result.node import Node
from octomod.result.slots import AxisRecord, CandidateDecl
from octomod.result.write import write_records
from octomod.workflow_modules.data import phenomenology
from octomod.workflow_modules.knowledge import reaction_evidence as _rxe
from octomod.workflow_modules.model import declared_constants as _dc
from octomod.workflow_modules.model import model_space

MD = "mechanism_discrimination"


@timing.phase("model")
def run(ctx: RunContext, directive: str | None = None) -> list[str] | None:
    """Run S1. Returns the round's candidate ids (mechanism discrimination or
    a bought model-space search), None for a single model."""
    if ctx.has_marker("s1"):
        print(
            "  (already passed — resumed from marker; model and scope stand as approved)"
        )
        cands = (ctx.round / "space/candidates").get(None)
        return [c["id"] for c in cands] if cands is not None else None

    goal = ctx.intent["inference_target"]
    model = ctx.round / "model"
    t_end = float(ctx.testcase.get("t_end", 100.0))

    # in a seeded round the model records are the seed: a re-entry that moved
    # them aside gets them back before S1 decides what it is doing
    from octomod.orchestration import round_seed as _seed

    if _seed.restore_model(ctx.root, ctx.round):
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note="the seeded model was restored from model/seed — a re-entry had "
            "moved it aside, and it is this round's input, not its product",
        )
        print(
            "  (seeded model restored from model/seed — a re-entry had moved it aside)"
        )

    supplied_ant = model / "antimony"
    redraft = None
    if supplied_ant.exists():
        # A model space beside the model makes it a BASE plus axes (what an
        # expansion round seeds); a single fixed model supplied to a
        # discrimination run is contradictory.
        has_space = (ctx.round / "space/axes").exists()
        if goal == MD and not has_space:
            raise ModuleFailure(
                "mechanism discrimination with a single supplied model is "
                "contradictory — supply nothing and let the agent propose "
                "candidates, or change the inference_target"
            )
        # Who wrote the model decides the marker's producer and whether a
        # `redraft:` has an author to go back to: in file-gate mode every scope
        # answer arrives on a resume, which finds the agent's model here.
        author = (
            "agent:construction"
            if (ctx.agent_calls.child("construction") / "reply").exists()
            else _supplied_producer(ctx)
        )
        try:
            return _run_single(ctx, model, t_end, author)
        except _hr.RedraftRequested as req:
            if author != "agent:construction":
                raise  # a model the user (or the seed) supplied has no author to redraft
            redraft = req

    context = _construction_context(ctx, directive, goal)
    if redraft is not None:
        _take_human_redraft(ctx, context, redraft)
    return _draft_loop(ctx, context, model, t_end, goal)


def _supplied_producer(ctx: RunContext) -> str:
    """Who put a model here before S1 ran: the user, or the previous round.

    The revision and expansion seeders write `model/seed` beside the model
    they copy (provenance is recorded by the writer, not inferred by a
    reader from neighbouring records)."""
    seed = ctx.round / "model/seed"
    return "seeded-from-previous-round" if seed.exists() else "user-supplied"


def _construction_context(ctx: RunContext, directive: str | None, goal: str) -> dict:
    """What the construction agent is told: the problem, a supplied network if
    there is one, the revision directive on a later round, the evidence it may
    cite, the essential set it builds the base from (with the knowledge
    module's output in the run), the candidate
    instruction for mechanism discrimination, and what the measured curves
    look like in words (shape and timescale, never a value): from the round's
    data table when it holds one, else from the raw files when they can be
    read without ambiguity."""
    context = {
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        "domain_packs": ctx.pack_texts(),
    }
    # the one data-derived input construction may read (routing.py): a
    # modeller reads shape and timescale off a plot before drawing a network.
    # In the first round of a fresh run, whose data module comes after, it is
    # the raw files' reading, and absent when their acceptance rules fail.
    view = phenomenology.for_construction(ctx)
    if view is not None:
        context["data_phenomenology"] = view
    network = ctx.round / "model/network"
    if network.exists():  # externally supplied network (GRN seam)
        context["supplied_network"] = network.get()
        context["instruction"] = (
            "A network specification was supplied. Translate it faithfully "
            "into a simulable model; do not invent mechanism beyond it."
        )
    if directive:
        context["revision_directive"] = directive
        prev_ant = _previous_round_antimony(ctx)
        if prev_ant:
            context["previous_model_antimony"] = prev_ant
    # Research items (`origin: research`) and the literature the human staged
    # (`origin: human`) share one channel; only the origin label differs.
    research_items = _maybe_research(ctx)
    supplied_items = _supplied_literature(ctx)
    if research_items is not None or supplied_items is not None:
        evidence = list(supplied_items or []) + list(research_items or [])
        context["retrieved_evidence"] = evidence
        context["evidence_instruction"] = (
            "Ground your decisions in the retrieved evidence where it applies: "
            "cite its source ids in the build report's evidence entries. "
            "Evidence you did not receive here must not be cited as direct. "
            "Each item carries an `origin`: `human` means the person who staged "
            "this problem already knows this source and hands you what it says "
            "(use it — it is the literature they expect the model to build on); "
            "`research` means the online retrieval role found it. Cite an item "
            "by its `id` or its `source` string verbatim; the evidence tier still "
            "follows what the SOURCE establishes, not who supplied it."
        )
    _ground_reactions(ctx, context, directive, network.exists())
    if goal == MD:
        max_c = int(ctx.spec.get("estimation.md_max_candidates", 5))
        # the base first, tested on its own; the candidates are written
        # afterwards as differences from it
        context["instruction_mechanism_discrimination"] = (
            "The inference target is mechanism discrimination, built in two "
            "steps. THIS call writes the BASE only: the one structure every "
            "candidate shares. Build each "
            "feature the comparison tests into the base as a switch the next "
            "step can set — a parameter whose base value turns the feature "
            "off (for example a competition switch at 0) — wherever that is "
            "possible, and say in the build report which parameter switches "
            "which feature. The engine tests your base on its own; a second "
            f"call then writes the 2-{max_c} candidates as differences from "
            "it, and the engine builds each one. Do not privilege one "
            "mechanism; the data decides."
        )

    return context


def _ground_reactions(
    ctx: RunContext, context: dict, directive: str | None, supplied_network: bool
) -> None:
    """With the knowledge module's output in the run, construction builds the
    BASE from the essential set (`_put_essential_context`). A revision round
    builds on the dossier of the round it revises (`dossier_of` reads the most
    recent round's); a supplied network is translated as given, so no set is
    handed over and no essential gate runs."""
    if not _rxe.active(ctx):
        return
    if supplied_network:
        ctx.ledger.append(
            "note",
            module=_rxe.MODULE,
            round_idx=ctx.round_idx,
            note="grounding skipped: a supplied network is translated as given, "
            "so construction is handed no essential set and no essential gate runs",
        )
        return
    _put_essential_context(ctx, context)


def _put_essential_context(ctx: RunContext, context: dict) -> dict:
    """What construction is shown of the knowledge module, from the round's
    dossier and floor as they stand: `essential_reactions` (the base set, each
    entry with its origin, grade and counting evidence), `support_floor`
    (`{band, step, source, words}`), `knowledge_summary` (the module's
    `system` block), `known_facts` (the facts meant for construction) and
    `grounding_instruction` (`BASE_INSTRUCTION` in strict mode,
    `ADVISORY_INSTRUCTION` in advisory, which adds `prior_reactions`, the
    whole dossier). Called again after a search admitted reactions or the
    floor moved. Returns the base set."""
    from octomod.workflow_modules.knowledge import engine as _kn

    view = _rxe.dossier_of(ctx)
    floor = _rxe.base_floor(ctx)
    base = _rxe.base_set(view, floor)
    context["essential_reactions"] = _rxe.essential_rows(base)
    context["support_floor"] = _rxe.floor_context(floor)
    if view.get("system"):
        context["knowledge_summary"] = view["system"]
    facts = _kn.facts_for(view, "construction")
    if facts:
        context["known_facts"] = facts
    if _rxe.strict(ctx):
        context["grounding_instruction"] = _rxe.BASE_INSTRUCTION
        context.pop("prior_reactions", None)
    else:
        # the whole dossier is prior knowledge: the entries outside the base
        # set are candidates construction may take where the question needs them
        context["grounding_instruction"] = _rxe.ADVISORY_INSTRUCTION
        context["prior_reactions"] = _rxe.prior_reactions(view)
    return base


def _reaction_support(ctx: RunContext, sbml: str, parameters) -> dict | None:
    """A model annotated against the round's dossier (`dossier_of`: the
    staged reactions and those a targeted search admitted) — where each of its
    reactions comes from and who proposed it, with `dossier_round` naming the
    round the dossier is in. None when the run does not build on the
    knowledge module: then nothing is annotated and no gate is recorded."""
    if not _rxe.active(ctx):
        return None
    view = _rxe.dossier_of(ctx)
    if not view.get("reactions"):
        return None
    return {
        **_rxe.annotate(view, sbml, parameters),
        "dossier_round": int(view.get("dossier_round") or 0),
    }


def set_per_condition_ids(construction: dict | None) -> list[str]:
    """The ids a construction reply marks `set_per_condition: true`: on a
    `parameters` entry, a `network.species` entry or a glossary entry."""
    reply = construction or {}
    entries = list(reply.get("parameters") or [])
    entries += list((reply.get("network") or {}).get("species") or [])
    glossary = reply.get("entity_glossary") or {}
    for kind in ("species", "parameters"):
        entries += list(glossary.get(kind) or [])
    out: list[str] = []
    for e in entries:
        if isinstance(e, dict) and e.get("set_per_condition") is True and e.get("id"):
            if str(e["id"]) not in out:
                out.append(str(e["id"]))
    return out


def connectivity_anchors(ctx: RunContext, construction: dict, sbml: str) -> list[str]:
    """The species `model_connected` requires the graph to reach: those matched to
    the intent's `required_entities`, by id or name or through the glossary,
    as `model_required_entities` reads them."""
    from octomod.gates.sim_gates import required_entity_matches

    match = required_entity_matches(
        sbml,
        (ctx.intent or {}).get("required_entities") or [],
        (construction or {}).get("entity_glossary") or {},
    )
    species = set(match["species_ids"])
    found = set(match["species"].values())
    found |= {eid for eid in match["via"].values() if eid in species}
    return sorted(found)


def _essential_gates(
    ctx: RunContext, context: dict, construction: dict, sbml: str
) -> tuple[dict | None, list[str]]:
    """`model_essential_reactions`, `model_connected` and `model_fact_citations` on a
    base that passed its ladder and its glossary check, each recorded like
    every other check.
    Returns (the model's annotation, the failures in the words the redraft
    dossier hands back to construction). Nothing runs when construction was
    handed no essential set (the run does not build on the knowledge module,
    or a network was supplied): the annotation alone, which gates nothing."""
    if "essential_reactions" not in context:
        return _reaction_support(ctx, sbml, construction["parameters"]), []
    from octomod.workflow_modules.model import connectivity

    view = _rxe.dossier_of(ctx)
    base = _rxe.base_set(view, _rxe.base_floor(ctx))
    support = {
        **_rxe.annotate(view, sbml, construction["parameters"]),
        "dossier_round": int(view.get("dossier_round") or 0),
    }
    mode = _rxe.grounding_mode(ctx)
    check = _rxe.essential_check(support, base)
    res_ess = _rxe.essential_result(check, support, mode)
    res_conn = connectivity.model_result(
        sbml,
        set(connectivity_anchors(ctx, construction, sbml)),
        set(set_per_condition_ids(construction)),
    )
    res_cite = _rxe.fact_citation_result(construction["parameters"], view)
    run_gate_set(
        [lambda r=res_ess: r, lambda r=res_conn: r, lambda r=res_cite: r],
        ctx.gates,
        ctx.ledger,
        "model",
        round_idx=ctx.round_idx,
        stop_on_fail=False,
    )
    failures = [] if res_ess.passed else _rxe.essential_failures(check, mode)
    if not res_conn.passed and res_conn.blocking:
        failures.append(
            f"the species graph is not complete (model_connected): {res_conn.detail}"
        )
    if failures:
        # what the failure path hands a targeted search: the draft as it stood
        ctx.cache["_s1_knowledge_failed"] = {"sbml": sbml}
    # a citation of a fact the dossier lacks is a redraft, never a search
    if not res_cite.passed:
        failures.append(
            f"a parameter cites a fact the dossier does not have "
            f"(model_fact_citations): {res_cite.detail}"
        )
    return support, failures


def _put_support(model: Node, support: dict | None) -> None:
    """The annotation at the model's node (`<model>/reaction_support`). With
    none, an annotation an earlier draft left there is removed: it describes
    a model that is no longer this one."""
    node = model / _rxe.SUPPORT_KEY
    if support is None:
        node.delete()
    else:
        node.put(support)


def _reaction_card_lines(model: Node, where: str | None = None) -> list[str]:
    """What a card says about a model's reactions, from its annotation in the
    record — a resumed card says what the first one said."""
    return _rxe.card_lines(
        (model / _rxe.SUPPORT_KEY).get(None), where or _rxe.REPORT_POINTER
    )


def _reaction_document(model: Node, report_path) -> list[tuple]:
    """The card's document entry for the reactions: the model report's M1
    block, when the model is annotated and the report was written."""
    if report_path is None or not (model / _rxe.SUPPORT_KEY).exists():
        return []
    return [("where each reaction comes from — model report M1", report_path)]


# ------------------------------------------------------------ drafting


def research_enabled(testcase: dict, spec) -> bool:
    return bool(
        (testcase.get("research") or {}).get(
            "enabled", spec.get("research.enabled", False)
        )
    )


def research_fence(testcase: dict, spec, case_name: str, blocklist_path) -> dict | None:
    """The research fence of a case: its publication horizon and forbidden
    sources, for the orchestrator to ledger at run start.

    A case with research on must declare its own
    `research.max_publication_year` in testcase.yaml; the workflow default is
    never silently the horizon. An empty or absent `blocklist.txt` is legitimate
    and is recorded as such. Returns None when research is off. Raises
    ValueError (the cli prints `refused:` and exits 2)."""
    if not research_enabled(testcase, spec):
        return None
    year = (testcase.get("research") or {}).get("max_publication_year")
    if year is None:
        raise ValueError(
            f"testcase {case_name!r} has research.enabled but no "
            "`research.max_publication_year` in its testcase.yaml — the horizon "
            "belongs to the case, not to the workflow default. Declare it, or turn "
            "research off for this case."
        )
    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    path = Path(blocklist_path) if blocklist_path else None
    entries: list[str] = _lit.read_blocklist(path)
    return {
        "horizon": int(year),
        "forbidden_sources": entries,
        "blocklist_file": path.name if path is not None and path.exists() else None,
        "note": (
            "research on, no forbidden sources"
            if not entries
            else f"research on, {len(entries)} forbidden source(s)"
        ),
    }


def research_at_expansion(testcase: dict, spec) -> bool:
    """Is the research role asked again before each expansion proposal? Only
    when research is on for the run; `research.at_expansion` in testcase.yaml
    overrides the workflow's."""
    if not research_enabled(testcase, spec):
        return False
    return bool(
        (testcase.get("research") or {}).get(
            "at_expansion", spec.get("research.at_expansion", True)
        )
    )


def _maybe_research(ctx: RunContext) -> list | None:
    """Retrieval as its own ONLINE hole (web tools only, file tools denied):
    the construction agent stays offline and consumes evidence as data."""
    if not research_enabled(ctx.testcase, ctx.spec):
        return None
    return retrieve_evidence(ctx, ctx.round / "evidence", module="model_research")


def retrieve_evidence(
    ctx: RunContext,
    ev: Node,
    *,
    module: str,
    extra: dict | None = None,
    calls: Node | None = None,
    name: str | None = None,
    first_id: int = 1,
) -> list:
    """One call of the research role, fenced and frozen; the accepted items.

    Engine-enforced: the per-testcase blocklist and publication-year cutoff
    filter the returned items BEFORE any decider sees them; the accepted
    snapshot is frozen at the record node `ev` (replayable, and a resume reads
    it back instead of calling), the documents behind it are cached in the
    round's `evidence_sources`, and dropped items are ledgered. `extra` is what
    this call is told beyond the problem itself (the expansion's model and
    misfit); `name` keeps its prompt and reply apart from another research
    call's in the same round, as a flat `agent_calls/<name>` entry
    (`ctx.call(..., name=)`); `calls` as in `ctx.call`; `first_id` numbers the
    items after those an agent already holds (`res_<first_id>` onwards), so
    one id names one item in its payload."""
    if ev.exists():
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"{'expansion ' if extra else ''}evidence snapshot reused "
            f"(resume): {ev.key}",
        )
        return ev.get()["items"]

    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    blocklist = _lit.read_blocklist(ctx.testcase_dir / "blocklist.txt")
    # the cutoff is per-testcase, falling back to the workflow's conservative
    # default
    cutoff_year = int(
        ctx.testcase.get("research", {}).get(
            "max_publication_year",
            ctx.spec.get("research.max_publication_year", 2025),
        )
    )
    payload = {
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        **(extra or {}),
        "restrictions": (
            f"HARD RULES: use only literature published up to {cutoff_year} "
            f"inclusive. NEVER consult, cite, or search for these excluded "
            f"sources: {blocklist or '(none listed)'}. Never fabricate a "
            f"source; returning fewer or zero items is acceptable."
        ),
    }
    # only what was given: a context's `call` need not take the options
    opts = {k: v for k, v in (("calls", calls), ("name", name)) if v is not None}
    out = ctx.call("research", payload, **opts)
    items, dropped = [], []
    max_items = int(ctx.spec.get("research.max_items", 12))
    for it in out.get("evidence_items", []):
        blob = " ".join(
            str(it.get(k, "")) for k in ("source", "title", "url")
        ).casefold()
        year = it.get("year")
        if any(b.casefold() in blob for b in blocklist):
            dropped.append({"item": it, "reason": "blocklist"})
        elif isinstance(year, (int, float)) and year > cutoff_year:
            dropped.append({"item": it, "reason": f"published after {cutoff_year}"})
        else:
            # the origin label that tells a research item from one the human
            # supplied, on every item that reaches an agent
            it = {**it, "origin": _lit.ORIGIN_RESEARCH}
            items.append(it)
    items = items[:max_items]
    # the id the contract promises every evidence item (`res_k` beside the
    # human's `lit_k`), so a build-report citation can name one either way
    for k, it in enumerate(items, start=max(1, int(first_id))):
        it["id"] = f"res_{k}"
    # engine-side source caching: freeze the documents behind the accepted
    # claims for later audit; failures are honest per-item records
    sources = ctx.round / "evidence_sources"
    n_cached = 0
    for it in items:
        it.update(_cache_source(ctx, str(it.get("url", "")), sources))
        n_cached += it.get("fetch_status") == "cached"
    if items:
        print(f"  source cache: {n_cached}/{len(items)} documents frozen for audit")
    if dropped:
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"evidence filter dropped {len(dropped)} item(s): "
            f"{[d['reason'] for d in dropped]}",
        )
    ev.put(
        {
            "items": items,
            "dropped": dropped,
            "queries_run": out.get("queries_run", []),
            "notes": out.get("notes", ""),
        }
    )
    print(
        f"  research: {len(items)} evidence item(s) accepted, "
        f"{len(dropped)} filtered out"
    )
    return items


# ------------------------------------------------ research before an expansion

# the snapshot of the research call made before an expansion proposal: the
# round's `expansion_evidence` record, beside construction's `evidence`
EXPANSION_EVIDENCE = "expansion_evidence"

EXPANSION_RESEARCH_INSTRUCTION = (
    "This search runs AFTER a fit, before another agent proposes what the model "
    "space was missing. `model_summary` is the selected model: every species and "
    "reaction it already has. `misfit_summary` says where it fails to fit. Find "
    "mechanisms DESCRIBED FOR THIS SYSTEM in the literature that the model does "
    "not contain — a regulator, a feedback or feed-forward loop, a second route, "
    "a transport, synthesis or turnover step, an effect specific to one condition "
    "or cell type — above all those that act where the misfit is. A mechanism the "
    "model already contains is wanted only where a source contradicts the form "
    "the model gives it. Report what each source says, faithfully; do not propose "
    "a model change."
)

EXPANSION_EVIDENCE_INSTRUCTION = (
    "Literature the research role retrieved just before this call (origin: "
    "research), searched for mechanisms described for this system that the "
    "selected model lacks, and fenced by the case's blocklist and publication "
    "horizon. An axis an item (or a domain pack) motivates carries `origin: "
    "biology` and cites the item by its `id` (res_1) in its rationale. An item "
    "is a claim about a source, never evidence that the mechanism is in THIS "
    "data: the data decide that, by the criterion, and a mechanism this data "
    "cannot separate belongs in `beyond_this_data`, not in `axes`. You see the "
    "claim, never the document; do not attribute to an item more than its "
    "supports/quote."
)


def expansion_model_summary(model: Node, model_id: str) -> dict:
    """The selected model as the research role reads it: every species with
    what it denotes (its glossary entry), every reaction as the model states
    it, one line each. `model` is the model group (`…/model`) of the selected
    candidate."""
    return _model_summary(
        (model / "antimony").text("") or "",
        (model / "glossary").get({}) or {},
        (model / "sbml").text(None),
        model_id,
    )


def draft_model_summary(construction: dict, sbml: str | None) -> dict:
    """A construction draft as a targeted search reads it, in the shape of
    `expansion_model_summary`: from the reply's Antimony and glossary and the
    SBML its ladder built."""
    return _model_summary(
        (construction or {}).get("antimony") or "",
        (construction or {}).get("entity_glossary") or {},
        sbml,
        "the draft under construction",
    )


def _model_summary(ant: str, glossary: dict, sbml: str | None, model_id: str) -> dict:
    from octomod.workflow_modules.model import antimony_text as _at

    denotes = {
        str(s.get("id")): " ".join(str(s.get("denotes") or "").split())[:200]
        for s in glossary.get("species") or []
        if isinstance(s, dict) and s.get("id")
    }
    species = _species_ids(sbml) if sbml else list(denotes)
    return {
        "model": model_id,
        "species": [{"id": s, "denotes": denotes.get(s, "")} for s in species],
        "reactions": [
            {"id": rid, "line": line[:240]} for rid, line in _at.reaction_lines(ant)
        ],
    }


def expansion_misfit_summary(misfit_evidence: dict | None) -> list[str]:
    """Where the selected model fails, in the sentences the gate cards print:
    the open indicators' reasons, then every indicator's closeness on one
    line. No measurement, residual or fitted parameter value — only each
    indicator's own statistic (a sigma ratio, a chi2/dof)."""
    from octomod.workflow_modules.evaluation import misfit_margins as _mm

    ev = misfit_evidence or {}
    out = [" ".join(str(r).split()) for r in ev.get("reasons") or [] if str(r).strip()]
    compact = _mm.card_line_compact(ev)
    if compact:
        out.append(compact)
    return out or ["no structural-misfit indicator was measured for the selected model"]


def expansion_biology(
    ctx: RunContext,
    model: Node,
    misfit_evidence: dict | None,
    model_id: str,
    floor: dict | None = None,
) -> tuple[dict, list[str]]:
    """What the expansion agent is shown from the biology side, and what its
    card says about it: `(context keys, card lines)`.

    The intent's domain packs, always. With the knowledge module's output in
    the run, the round's dossier (the most recent round's, with what a search
    admitted), as `prior_reactions`, and `floor` — the floor of the round the
    expansion seeds — as `support_floor` (`reaction_evidence.expansion_context`;
    nothing is searched for it). With
    research on for the run and `research.at_expansion`, the research role is
    asked first about mechanisms described for the system that the selected
    model lacks; its items are fenced like construction's, frozen in the
    round's `expansion_evidence`, and reach the expansion agent as
    `retrieved_evidence` with the same `res_k` ids. A resume reads the
    snapshot back and calls nothing. One research call per expansion round."""
    context: dict = {"domain_packs": ctx.pack_texts()}
    context.update(_rxe.expansion_context(ctx, floor))
    if not research_at_expansion(ctx.testcase, ctx.spec):
        return context, []
    ev = ctx.round / EXPANSION_EVIDENCE
    rel = ev.key
    if not ev.exists() and (ctx.round / "expansion_diagnostics").exists():
        # the agent was already asked in this round without this call: items
        # it never read would be paid for and shown beside a proposal made
        # without them
        ctx.ledger.append(
            "note",
            module="revision",
            round_idx=ctx.round_idx,
            note="research before the expansion not run: the expansion agent was "
            "already asked in this round without it (expansion_diagnostics)",
        )
        return context, [
            "research before this proposal: not run — the expansion agent had "
            "already been asked in this round without it"
        ]
    from octomod.agents import AgentCallError, AgentKilled

    fresh = not ev.exists()
    try:
        retrieve_evidence(
            ctx,
            ev,
            module="revision",
            extra={
                "model_summary": expansion_model_summary(model, model_id),
                "misfit_summary": expansion_misfit_summary(misfit_evidence),
                "instruction": EXPANSION_RESEARCH_INSTRUCTION,
            },
            name="research_expansion",
        )
    except AgentKilled:
        raise  # a person stopped it: not a reply to work around
    except AgentCallError as e:
        # frozen as failed, so a resume does not pay again for items the
        # proposal, made without them, would never read
        ev.put({"items": [], "dropped": [], "failed": str(e)[:400]})
    snap = ev.get({}) or {}
    items = snap.get("items") or []
    dropped = snap.get("dropped") or []
    if fresh:
        ctx.ledger.append(
            "expansion_evidence",
            module="revision",
            round_idx=ctx.round_idx,
            n_items=len(items),
            n_dropped=len(dropped),
            failed=snap.get("failed"),
            sources=[str(it.get("source") or "")[:120] for it in items],
            note=(
                f"research before the expansion FAILED ({snap['failed'][:200]}); "
                f"the proposal is made without retrieved evidence"
                if snap.get("failed")
                else f"research before the expansion: {len(items)} item(s) "
                f"accepted, {len(dropped)} filtered out, frozen in {rel}; they "
                f"reach the expansion agent as retrieved_evidence"
            ),
        )
    if snap.get("failed"):
        return context, [
            f"research before this proposal FAILED ({str(snap['failed'])[:160]}) — "
            f"the proposal was made without retrieved evidence ({rel})"
        ]
    context["retrieved_evidence"] = items
    context["evidence_instruction"] = EXPANSION_EVIDENCE_INSTRUCTION
    lines = [
        f"research before this proposal: {len(items)} literature item(s) "
        f"retrieved, {len(dropped)} filtered out ({rel})"
    ]
    lines += [
        f"  {it.get('id')}: {str(it.get('title') or it.get('source') or '')[:110]}"
        + (f" ({it['year']})" if it.get("year") else "")
        for it in items
    ]
    return context, lines


# ------------------------------------ the search the expansion agent asks for

# the snapshot of the n-th literature search the expansion agent asked for in a
# round: the round's `research_requests/<n>`, beside the pre-search's
# `expansion_evidence`
REQUESTED_RESEARCH = "research_requests/{n}"
# questions one request may carry; the rest are recorded and not searched
MAX_RESEARCH_QUESTIONS = 3
# the two refusals by name: the card, the ledger and the agent read these words
RESEARCH_ALREADY_REQUESTED = "research already requested this round"
RESEARCH_NOT_ALLOWED = "a search the run does not allow"

REQUESTED_RESEARCH_INSTRUCTION = (
    "The agent proposing what the fitted model space was missing has read the "
    "residuals and asks these `questions`; each names a mechanism or an "
    "observation to look for. Answer THEM, not the problem in general: for each "
    "question find what the literature on this system describes, or "
    "contradicts, and tag every item with `question`, the number of the question "
    "it answers (1 for the first). `model_summary` is the selected model: every "
    "species and reaction it already has. Report what each source says, "
    "faithfully; do not propose a model change. A question nothing answers is an "
    "honest result: say so in `notes`."
)


def requested_research_rounds(testcase: dict, spec, grounded: bool = False) -> int:
    """How many literature searches the expansion agent may ask for in one
    expansion round. With the knowledge module's output in the run
    (`grounded`) the search is a targeted search of the knowledge role, one per
    expansion round (`grounding.search.per_round`); otherwise none with
    research off for the run, else `research.max_requested_rounds`
    (testcase.yaml overrides the workflow's)."""
    if grounded:
        return _rxe.search_caps(spec)["per_round"]
    if not research_enabled(testcase, spec):
        return 0
    n = (testcase.get("research") or {}).get(
        "max_requested_rounds", spec.get("research.max_requested_rounds", 1)
    )
    return max(0, int(n or 0))


def research_questions(reply: dict) -> tuple[list[str], list[str]]:
    """The questions of an expansion reply's `requested_research`, one line
    each and without repeats: `(searched, beyond the cap)`. A reply without
    one, or with nothing readable in it, asks nothing."""
    raw = (reply or {}).get("requested_research")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return [], []
    out: list[str] = []
    for q in raw:
        if isinstance(q, dict):
            q = q.get("question")
        text = " ".join(str(q or "").split())[:400]
        if text and text not in out:
            out.append(text)
    return out[:MAX_RESEARCH_QUESTIONS], out[MAX_RESEARCH_QUESTIONS:]


def next_research_id(items) -> int:
    """The number after the highest `res_k` id among `items` (1 when none)."""
    ks = []
    for it in items or []:
        m = re.fullmatch(r"res_(\d+)", str((it or {}).get("id") or ""))
        if m:
            ks.append(int(m.group(1)))
    return max(ks, default=0) + 1


def _question_number(tag, n_questions: int) -> int | None:
    """The 1-based question an item's `question` tag names, or None."""
    if isinstance(tag, bool):
        return None
    if isinstance(tag, float) and tag.is_integer():
        tag = int(tag)
    try:
        k = int(str(tag).strip())
    except (TypeError, ValueError):
        return None
    return k if 1 <= k <= n_questions else None


def requested_research(
    ctx: RunContext,
    model: Node,
    model_id: str,
    questions: list[str],
    n: int,
    first_id: int,
) -> dict:
    """The n-th literature search the expansion agent asked for in this round.

    One research call with its questions and the selected model, fenced like
    every retrieval (`retrieve_evidence`: blocklist, horizon, source cache),
    its items numbered from `res_<first_id>` and frozen in the round's
    `research_requests/<n>` with the questions and how many accepted items
    answer each. A resume reads the snapshot back and calls
    nothing; a failed call is frozen as failed, so a resume does not pay for
    it again. Returns what the round's state records about the search."""
    from octomod.agents import AgentCallError, AgentKilled

    ev = ctx.round / REQUESTED_RESEARCH.format(n=n)
    try:
        retrieve_evidence(
            ctx,
            ev,
            module="revision",
            extra={
                "questions": list(questions),
                "model_summary": expansion_model_summary(model, model_id),
                "instruction": REQUESTED_RESEARCH_INSTRUCTION,
            },
            name=f"research_request_{n}",
            first_id=first_id,
        )
    except AgentKilled:
        raise  # a person stopped it: not a reply to work around
    except AgentCallError as e:
        ev.put({"items": [], "dropped": [], "failed": str(e)[:400]})
    snap = ev.get({}) or {}
    items = snap.get("items") or []
    per_question = [0] * len(questions)
    listed = []
    for it in items:
        k = _question_number(it.get("question"), len(questions))
        if k is not None:
            per_question[k - 1] += 1
            # the question in its own words: an item read beside another
            # search's still says what it answers
            it["answers_question"] = questions[k - 1]
        listed.append(
            {
                "id": it.get("id"),
                "title": str(it.get("title") or it.get("source") or "")[:110],
                "year": it.get("year"),
                "question": k,
            }
        )
    if snap.get("questions") != list(questions):
        ev.put(
            {
                **snap,
                "items": items,
                "questions": list(questions),
                "per_question": per_question,
            },
        )
    return {
        "snapshot": REQUESTED_RESEARCH.format(n=n),
        "n_items": len(items),
        "n_dropped": len(snap.get("dropped") or []),
        "per_question": per_question,
        "items": listed,
        "failed": snap.get("failed"),
    }


def requested_knowledge_search(
    ctx: RunContext,
    model: Node,
    model_id: str,
    questions: list[str],
    n: int,
    floor: dict | None,
    requested_by: str = _rxe.REQUESTED_BY_REVISION,
) -> dict:
    """The literature search asked for at an expansion, with the knowledge
    module's output in the run: the round's n-th targeted search of the
    knowledge role (`knowledge.targeted_search`, frozen at
    `knowledge_search/<n>`, a resume reads it back), with the questions and
    the selected model; what it finds is graded and admitted at the floor of
    the round the expansion seeds (`floor`) into the round's
    `knowledge_admitted`, where the expansion's axes are annotated against it.
    Returns what the round's state records about the search."""
    from octomod.workflow_modules.knowledge import engine as _kn

    node = ctx.round / _rxe.SEARCH_KEY / str(n)
    fresh = not node.exists()
    view = _rxe.dossier_of(ctx)
    # the dossier entries the selected model already implements, by its
    # annotation: a search does not return those again
    support = (model / _rxe.SUPPORT_KEY).get(None) or {}
    unused = set(map(str, support.get("unused_entries") or []))
    carried = [
        {"id": e["id"], "equation": e.get("equation")}
        for e in view.get("reactions") or []
        if support
        and isinstance(e, dict)
        and e.get("id")
        and str(e["id"]) not in unused
    ]
    # a failed call is frozen as failed by the search itself, and a person's
    # stop is raised through it
    _kn.targeted_search(
        ctx,
        list(questions),
        n,
        model_summary=expansion_model_summary(model, model_id),
        essential_ids=carried,
        requested_by=requested_by,
        known=view.get("reactions"),
    )
    band = _rxe.floor_band(floor) if floor else _rxe.NONE
    res = _rxe.admit(ctx, n, {"band": band})
    if fresh:
        ledger_search(ctx, n, requested_by, res, band, module="revision")
    rec = node.get({}) or {}
    adm = rec.get("admission") or {}
    found = [r for r in rec.get("reactions") or [] if isinstance(r, dict)]
    per_question = [
        sum(1 for r in found if q_id in (r.get("answers") or []))
        for q_id in (str(q.get("id")) for q in rec.get("questions") or [])
    ]
    return {
        "kind": "knowledge",
        "snapshot": node.key.split(f"{ctx.round.key}/", 1)[-1],
        "search_n": int(n),
        "requested_by": requested_by,
        "n_items": len(found),
        "n_dropped": len(rec.get("dropped") or []),
        "per_question": per_question,
        "items": [
            {
                "id": r.get("id"),
                "title": str(r.get("equation") or ""),
                "grade": r.get("grade"),
                "question": next(
                    (
                        k
                        for k, q in enumerate(rec.get("questions") or [], start=1)
                        if str(q.get("id")) in (r.get("answers") or [])
                    ),
                    None,
                ),
            }
            for r in found
        ],
        "admitted": list(adm.get("admitted") or []),
        "not_admitted": list(adm.get("not_admitted") or []),
        "floor": adm.get("floor", band),
        "failed": rec.get("failed"),
    }


def requested_research_instruction(
    testcase: dict, spec, requests: list, grounded: bool = False
) -> str:
    """What the expansion agent is told about the literature search it may
    ask for: whether it may, and, once one has run, where its answers are."""
    if grounded:
        return _requested_search_instruction(spec, requests)
    if not research_enabled(testcase, spec):
        return (
            "This run allows no literature search (research is off for this "
            "case): do not return `requested_research`; propose from what you "
            "were given."
        )
    allowed = requested_research_rounds(testcase, spec)
    answered = [r for r in requests or [] if r.get("status") == "answered"]
    ran = ""
    if answered:
        ran = (
            "The literature search you asked for has run: `research_answered` "
            "lists your questions, and the items it found are in "
            "`retrieved_evidence`, each naming the question it answers "
            "(`answers_question`); a question no item names found nothing inside "
            "the case's fence. "
        )
        if any(r.get("failed") for r in answered):
            ran += "A search FAILED and returned nothing. "
    if len(answered) < allowed:
        left = allowed - len(answered)
        return ran + (
            f"You may ask for {'one literature search' if left == 1 else f'{left} literature searches'} "
            "this round via `requested_research`: 1-3 questions, each ONE "
            "sentence naming the mechanism or observation to look for, returned "
            "with `axes: []` and your diagnosis so far. The research role searches "
            "for them under this case's blocklist and publication horizon; its "
            "items join `retrieved_evidence` with new ids and you are asked "
            "again. A source says what is described for this system; the data "
            "still decide, by the criterion."
        )
    if allowed == 0:
        return (
            "This run allows no requested literature search "
            "(research.max_requested_rounds = 0): do not return "
            "`requested_research`; propose from what you were given."
        )
    return ran + (
        f"No further search this round (research.max_requested_rounds = "
        f"{allowed}): propose from what you have."
    )


def _requested_search_instruction(spec, requests: list) -> str:
    """The same, when the run builds on the knowledge module: the search is a
    targeted search of the knowledge role, graded by the engine and admitted
    at the floor of the round the expansion seeds."""
    allowed = _rxe.search_caps(spec)["per_round"]
    answered = [r for r in requests or [] if r.get("status") == "answered"]
    ran = ""
    for r in answered:
        who = (
            "you asked for"
            if r.get("requested_by", _rxe.REQUESTED_BY_REVISION)
            == _rxe.REQUESTED_BY_REVISION
            else "the person asked for"
        )
        if r.get("failed"):
            ran += f"The targeted search {who} FAILED and found nothing. "
            continue
        ran += (
            f"The targeted search {who} has run ({r.get('snapshot')}): "
            f"{r.get('n_items', 0)} reaction(s) found; "
            + (
                f"admitted at the floor {_rxe.band_text(r.get('floor'))}, and now in "
                f"`prior_reactions` with origin `search`: "
                + ", ".join(r.get("admitted") or [])
                if r.get("admitted")
                else f"nothing reached the floor {_rxe.band_text(r.get('floor'))}"
            )
            + (
                "; not admitted: "
                + "; ".join(
                    f"{b.get('id')} {b.get('equation')} ({b.get('why')})"
                    for b in r.get("not_admitted") or []
                )
                if r.get("not_admitted")
                else ""
            )
            + ". "
        )
    if len(answered) < allowed:
        return ran + (
            "You may ask for one targeted literature search this round via "
            "`requested_research`: 1-3 questions, each ONE sentence naming the "
            "conversion to look for (write it as an equation in the selected "
            "model's species ids, `A + B -> C`, and why), returned with `axes: []` "
            "and your diagnosis so far. The knowledge role searches under this "
            "case's blocklist and horizon; the engine grades what it finds, admits "
            "what reaches the floor of the next round (`support_floor`) into "
            "`prior_reactions`, and asks you again. Ask when an axis you would "
            "propose adds a conversion `prior_reactions` does not describe at that "
            "floor: such an axis is refused otherwise."
        )
    if allowed == 0:
        return ran + (
            "This run allows no targeted search at an expansion "
            "(grounding.search.per_round = 0): do not return `requested_research`; "
            "propose from what you were given."
        )
    return ran + (
        f"No further search this round (grounding.search.per_round = {allowed}): "
        f"propose from what you have."
    )


def requested_research_lines(requests: list) -> list[str]:
    """What the expansion card says about the searches the agent asked for:
    each request's questions with how many accepted items answer each, the
    items by id, and a refusal by name."""
    out: list[str] = []
    for r in requests or []:
        status = r.get("status")
        qs = [str(q) for q in r.get("questions") or []]
        if status == "answered" and r.get("kind") == "knowledge":
            out += _knowledge_request_lines(r, qs)
            continue
        if status == "answered":
            out.append(
                (
                    f"the agent asked for a literature search before proposing; it "
                    f"FAILED ({str(r['failed'])[:160]}) and the agent was asked "
                    f"again without its items ({r.get('snapshot')}):"
                )
                if r.get("failed")
                else (
                    f"the agent asked for a literature search before proposing: "
                    f"{r.get('n_items', 0)} item(s) accepted, "
                    f"{r.get('n_dropped', 0)} filtered out ({r.get('snapshot')}):"
                )
            )
            per = list(r.get("per_question") or [])
            per += [0] * (len(qs) - len(per))
            out += [
                f"  Q{k} ({per[k - 1]} item(s)): {q[:200]}" for k, q in enumerate(qs, 1)
            ]
            out += [
                f"  {it.get('id')}: {it.get('title')}"
                + (f" ({it['year']})" if it.get("year") else "")
                + (
                    f" — Q{it['question']}"
                    if it.get("question")
                    else " — names no question"
                )
                for it in r.get("items") or []
            ]
        elif status in ("refused", "ignored"):
            if status == "ignored":
                head = (
                    f"the agent asked for a literature search again after the "
                    f"refusal ({r.get('reason')}): not searched, and its reply was "
                    f"taken as it stood:"
                )
            elif r.get("refusal") == "not_allowed":
                head = (
                    f"the agent asked for {r.get('reason')}: not searched; it was "
                    f"asked once more with that fact:"
                )
            else:
                head = (
                    f"the agent asked for another literature search: refused, "
                    f"{r.get('reason')}; it was asked once more without it:"
                )
            out.append(head)
            out += [f"  Q{k}: {q[:200]}" for k, q in enumerate(qs, 1)]
        else:
            continue  # pending: finished before any card is built
        out += [
            f"  not searched (at most {MAX_RESEARCH_QUESTIONS} questions per "
            f"request): {str(q)[:200]}"
            for q in r.get("not_searched") or []
        ]
    return out


def _knowledge_request_lines(r: dict, qs: list[str]) -> list[str]:
    """The card's lines for one targeted search asked for at an expansion:
    who asked, its questions, what it found and what reached the floor."""
    who = (
        "the agent"
        if r.get("requested_by", _rxe.REQUESTED_BY_REVISION)
        == _rxe.REQUESTED_BY_REVISION
        else "you"
    )
    floor = _rxe.band_text(r.get("floor"))
    if r.get("failed"):
        head = (
            f"{who} asked for a targeted search; it FAILED "
            f"({str(r['failed'])[:160]}) and admitted nothing ({r.get('snapshot')}):"
        )
    else:
        head = (
            f"{who} asked for a targeted search ({r.get('snapshot')}): "
            f"{r.get('n_items', 0)} reaction(s) found, "
            + (
                f"admitted at floor {floor}: {', '.join(r['admitted'])}"
                if r.get("admitted")
                else f"nothing admitted at floor {floor}"
            )
        )
    out = [head[0].upper() + head[1:]]
    per = list(r.get("per_question") or [])
    per += [0] * (len(qs) - len(per))
    out += [f"  Q{k} ({per[k - 1]} found): {q[:200]}" for k, q in enumerate(qs, 1)]
    out += [
        f"  not admitted {b.get('id')} {b.get('equation')} — {b.get('why')}"
        for b in r.get("not_admitted") or []
    ]
    out += [
        f"  not searched (at most {MAX_RESEARCH_QUESTIONS} questions per request): "
        f"{str(q)[:200]}"
        for q in r.get("not_searched") or []
    ]
    return out


def _supplied_literature(ctx: RunContext) -> list | None:
    """The literature the human staged in `intent.supplied_literature`, as
    construction receives it: every item tagged `origin: human`, its document
    cached into the run for audit, the snapshot frozen in the round's
    `supplied_evidence` so a resume reuses it, and one ledger row naming
    what was handed over. None when the intent has none. The fence (blocklist,
    horizon, benchmark declaration) was already applied at the intent gate."""
    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    # the run-level snapshot S0 froze, never `ctx.intent`, which is written
    # without the items so that the other roles granted `intent` do not see them
    raw = _lit.load_frozen(ctx.root)
    if not raw:
        return None
    snapshot = ctx.round / "supplied_evidence"
    if snapshot.exists():
        ctx.ledger.append(
            "note",
            module="model_literature",
            round_idx=ctx.round_idx,
            note="supplied literature snapshot reused (resume)",
        )
        return snapshot.get()["items"]
    import time as _time

    items = _lit.normalized(raw)
    sources = ctx.round / "evidence_sources"
    n_cached = 0
    t0 = _time.perf_counter()
    with timing.span("io", "literature_cache", n_items=len(items)):
        for it in items:
            it.update(_cache_source(ctx, str(it.get("url") or ""), sources))
            n_cached += it.get("fetch_status") == "cached"
    # recorded, not capped: a human's list is never truncated silently, and the
    # per-item limits (20 MB, 20 s) already bound each fetch
    bytes_cached = sum(int(it.get("bytes") or 0) for it in items)
    cache_seconds = round(_time.perf_counter() - t0, 2)
    snapshot.put({"items": items, "n_cached": n_cached, "origin": "human"})
    ctx.ledger.append(
        "supplied_literature",
        module="model_literature",
        round_idx=ctx.round_idx,
        n_items=len(items),
        n_cached=n_cached,
        bytes_cached=bytes_cached,
        cache_seconds=cache_seconds,
        sources=[str(it.get("source") or "")[:120] for it in items],
        note=(
            f"{len(items)} literature item(s) supplied by the human in "
            f"intent.supplied_literature reach construction as retrieved_evidence "
            f"(origin: human); {n_cached} document(s) cached for audit"
        ),
    )
    print(
        f"  supplied literature: {len(items)} item(s) from the intent handed to "
        f"construction (origin: human); source cache {n_cached}/{len(items)}"
    )
    return items


def _cache_source(ctx: RunContext, url: str, sources: Node) -> dict:
    """`octomod.connectors.web_cache.cache_source`, into the record: the connector
    fetches into a scratch directory (it writes files), and the document it
    froze is stored as a blob at `evidence_sources/<cached_file>`. Returns
    the connector's status record unchanged."""
    import tempfile

    from octomod.connectors.web_cache import cache_source

    with tempfile.TemporaryDirectory(prefix="octomod_src_") as tmp:
        rec = cache_source(url, Path(tmp), base_dir=ctx.testcase_dir)
        name = rec.get("cached_file")
        if rec.get("fetch_status") == "cached" and name:
            sources.child(name).put_blob((Path(tmp) / name).read_bytes())
    return rec


def _ledger_evidence_origins(ctx: RunContext, construction: dict) -> None:
    """Which of the build report's decisions leaned on the human's
    literature, which on the research agent's, which on neither — one ledger
    row, read by `decisions_md`. Never fatal: a record must not end a round."""
    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    try:
        sup = (ctx.round / "supplied_evidence").get(None)
        res = (ctx.round / "evidence").get(None)
        supplied = sup["items"] if sup is not None else []
        research = res["items"] if res is not None else []
        if not supplied and not research:
            return
        decisions = (construction.get("build_report") or {}).get("decisions") or []
        att = _lit.attribution(decisions, supplied, research)
        ctx.ledger.append(
            "evidence_attribution",
            module="model",
            round_idx=ctx.round_idx,
            **att,
            note=(
                f"{len(att['leaned_on_human'])} of {att['n_decisions']} decision(s) "
                f"cite the human's supplied literature, "
                f"{len(att['leaned_on_research'])} cite research items, "
                f"{att['cited_neither']} cite neither"
            ),
        )
    except Exception as e:  # noqa: BLE001
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"evidence attribution record failed: {e}",
        )


def _draft_loop(
    ctx: RunContext, context: dict, model: Node, t_end: float, goal: str
) -> list[str] | None:
    """Draft, ladder, gate — and go round again when a GATE fails, when a
    HUMAN asks for something different, or when the ENGINE answered what a
    base named missing (`_answer_missing`). They are deliberately not the
    same: a gate failure spends the redraft budget, while a person's request
    and the engine's answer are granted extra budget instead, because that
    budget bounds failure and neither is one."""
    while True:
        try:
            return _draft_once(ctx, context, model, t_end, goal)
        except _hr.RedraftRequested as req:
            _take_human_redraft(ctx, context, req)


# the grant an engine redraft after a targeted search is recorded under: the
# draft loop counts them to know how far the search ladder has gone
SEARCH_GRANT = "knowledge_search"
# what the engine ran on the base before it asked again
SEARCH_STEP = "its check of your base against the essential set and the species graph"
_ENGINE_KEYS = ("engine_feedback", "engine_feedback_instruction")


def _take_human_redraft(ctx: RunContext, context: dict, req) -> None:
    """A redraft reaches the agent with the reply it is about, and the budget
    is extended: the person's words verbatim (their request never competes
    with a real failure), or the engine's finding under its own keys."""
    from octomod.orchestration.interaction import retry as _retry

    engine = req.source == _hr.ENGINE
    context.update(
        _hr.context_for(
            req.text,
            req.role,
            _hr.previous_reply(ctx, req.role),
            source=req.source,
            step=SEARCH_STEP if engine else None,
        )
    )
    history = _retry.AttemptHistory(_retry.dossier_of(ctx, "construction"))
    if engine:
        history.add_grant(1, why=SEARCH_GRANT)
    else:
        history.add_grant(1)
    if not engine:
        # a person's request supersedes the engine's last finding; the
        # engine's never silences a person's
        for key in _ENGINE_KEYS:
            context.pop(key, None)
    if engine:
        _hr.record(ctx, "model", req.role, req.text, source=_hr.ENGINE)
        print("  → construction is asked again with what the engine found")
    else:
        print(f"  → redrafting at your request: {req.text[:90]}")


def _reuse_cached_reply(cached: Node, history, context: dict, first_pass: bool) -> bool:
    """May this pass of the draft loop take the saved construction reply
    instead of calling the agent?

    Yes when this is the first pass of a (re)started module, a reply is in the
    record, nobody has asked for a change, and that reply is not a FAILED
    draft: either no attempt ever failed, or the dossier records that the draft
    after the failures passed its ladder.
    """
    if not first_pass or not cached.exists():
        return False
    if "human_feedback" in context:
        return False
    return not history.attempts or history.passed_attempt is not None


def _backfill_passed(history, evidence: list[Node]) -> bool:
    """A dossier without a pass record says only which drafts failed. If an
    artifact that ONLY a passed draft writes (`space/candidates` for
    discrimination, `model/antimony` for a single model) is in the record,
    the draft after those failures passed: record it, so the resume reuses
    that draft instead of re-drafting it. Returns True when it wrote the
    record.

    The record keeps no modification times, so the test is the artifact's
    presence rather than "newer than the dossier's last failure": only a
    dossier imported from a legacy run directory can lack the pass-record
    field, and every dossier this engine writes carries it."""
    if not history.attempts or history.has_pass_record:
        return False
    for node in evidence:
        if node.exists():
            history.mark_passed()
            return True
    return False


def _draft_once(
    ctx: RunContext, context: dict, model: Node, t_end: float, goal: str
) -> list[str] | None:
    from octomod.orchestration.interaction import retry as _retry

    base_budget = int(ctx.spec.get("retry.module_draft", 2)) + 1
    # S1's marker is written only after the scope gate, so a run paused there
    # (in file-gate mode, every run) comes back here on resume: the saved reply
    # is reused for the first attempt unless it failed, and a genuine retry
    # still calls fresh, with the dossier of every earlier attempt.
    cached = ctx.agent_calls.child("construction") / "reply"
    dossier = _retry.dossier_of(ctx, "construction")
    history = _retry.AttemptHistory(dossier)
    # A RESUMED retry continues where the dossier left off: attempts already
    # spent are recorded, and so is the previous draft (the last saved reply),
    # which is what minimal-repair mode needs to offer.
    if _backfill_passed(history, [ctx.round / "space/candidates", model / "antimony"]):
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note="construction dossier predates the passed-draft record; "
            "backfilled from the artifacts only a passed draft writes "
            f"(attempt {history.passed_attempt} passed)",
        )
    attempt = len(history)
    first_pass = True
    prev_ant: str | None = None
    if history.attempts and cached.exists():
        try:
            prev_ant = cached.get().get("antimony")
        except Exception:
            prev_ant = None
    while True:
        # The budget is checked before the call: checked after it, a resume
        # would make one unbudgeted call and the answer meant for the
        # exhaustion gate would be consumed by the next gate.
        budget = base_budget + history.grants_total
        if attempt >= budget or _search_ladder_spent(history):
            # the budget is spent, or a base failed its essential set after
            # the search and the lowered floor: either way, the person decides
            granted = _retry.exhaustion_gate(
                ctx,
                "model",
                "construction",
                history,
                budget,
                extra_lines=_rxe.search_card_lines(ctx) if _rxe.active(ctx) else [],
                set_floor=(
                    _floor_setter(ctx, context)
                    if "essential_reactions" in context
                    else None
                ),
            )
            if granted == 0:
                raise ModuleFailure(
                    "model construction exhausted its redraft budget on the gate "
                    "ladder and the human did not extend it — failing checks "
                    f"recorded in {ctx.gates.key}, every attempt in "
                    f"{dossier.key}"
                )
            continue  # re-read the budget from the persisted grant
        # The dossier's `passed_attempt` (in _reuse_cached_reply) decides reuse;
        # a pause at the scope gate is a second proof that the cached reply passed.
        paused_at_scope = False
        try:
            pending = humangate.pending_path(ctx.root).get(None)
            # a staged round also pauses at its BASE gate, on a reply that
            # passed: the same proof that the cached reply is good
            paused_at_scope = isinstance(pending, dict) and pending.get("module") in (
                "model_scope",
                "model_base_scope",
            )
        except Exception:
            paused_at_scope = False
        if _reuse_cached_reply(cached, history, context, first_pass) or (
            first_pass
            and paused_at_scope
            and cached.exists()
            and "human_feedback" not in context
        ):
            construction = cached.get()
            ctx.cache["_construction_reply"] = construction
            why = (
                "paused at the scope gate on this reply"
                if paused_at_scope and history.attempts
                else "before the gate pause"
            )
            print(
                f"  (reusing the construction reply from {cached.key} — {why}; "
                "no new agent call)"
            )
            ctx.ledger.append(
                "note",
                module="model",
                round_idx=ctx.round_idx,
                note=f"construction reply reused from {cached.key} ({why}); "
                "no new agent call",
            )
        else:
            if history.attempts:
                context["attempt_history"] = history.as_context()
                last = history.attempts[-1]
                # minimal-repair mode is for a draft that FAILED. It is wrong
                # when the last draft passed and a human asked for a change
                # (their request is not a failure to localise), and wrong
                # when the recorded failure was repaired by a later draft.
                repairable = (
                    history.last_draft_failed and "human_feedback" not in context
                )
                if repairable and _retry.localized(last["gate_failures"]) and prev_ant:
                    ctx.ledger.append(
                        "note",
                        module="model",
                        round_idx=ctx.round_idx,
                        note=f"minimal-repair mode: attempt {attempt + 1} is asked "
                        f"for a MINIMAL edit of the previous draft — the "
                        f"failures named "
                        f"{sorted(_retry.implicated_names(last['gate_failures']))}",
                    )
                    # minimal-repair mode: the failures name reactions /
                    # symbols / species, so the unit of retry shrinks to an EDIT
                    context["minimal_repair"] = {
                        "previous_draft_antimony": prev_ant,
                        "instruction": (
                            "The failures above are LOCALIZED to the named "
                            "reactions/symbols. Return a MINIMAL edit of this "
                            "previous draft: change only what the failures "
                            "implicate, keep every line that passed. The engine "
                            "measures how much you changed beyond that."
                        ),
                    }
                else:
                    context.pop("minimal_repair", None)
                # a repair sees the WHOLE failed reply, not only the base
                # Antimony minimal-repair offers: a candidate set's failures
                # live in the candidates
                if history.last_draft_failed and "human_feedback" not in context:
                    _prev = _hr.previous_reply(ctx, "construction")
                    if _prev is not None:
                        context["previous_reply"] = _prev
            history.clear_passed()
            construction = ctx.call("construction", context)
            # the engine's finding answers this draft; a later draft is asked
            # with its own
            for key in _ENGINE_KEYS:
                context.pop(key, None)
            # the gate ladder reads the declared constants from here, so the
            # measurement runs on whichever draft is about to be laddered
            ctx.cache["_construction_reply"] = construction
        first_pass = False
        failures: list[str] = []
        if construction.get("candidates"):
            # the candidates are the expansion agent's: a reply that writes
            # them is a failed draft, handed back like any other
            ok, results = False, []
            failures = [CANDIDATES_REFUSED]
        elif goal == MD:
            # a BASE: tested exactly as a single model is, then the candidates
            # are built on it as declared differences
            ok, results = _run_ladder(
                ctx, construction["antimony"], construction["parameters"], t_end
            )
            support = None
            if ok:
                gl_problems = glossary_problems(construction, ctx.cache["_s1_sbml"])
                if not _glossary_gate(ctx, gl_problems):
                    failures = [
                        f"entity_glossary incomplete: {pr}" for pr in gl_problems
                    ]
                    ctx.cache.pop("_s1_sbml", None)
                else:
                    support, failures = _essential_gates(
                        ctx, context, construction, ctx.cache["_s1_sbml"]
                    )
                    if failures:
                        ctx.cache.pop("_s1_sbml", None)
            else:
                failures = [r.detail for r in results if not r.passed and r.blocking]
            if ok and not failures:
                history.mark_passed()
                _persist_base(
                    ctx,
                    construction,
                    ctx.cache.pop("_s1_sbml"),
                    redrafted="human_feedback" in context,
                )
                _put_support(_base_model(ctx), support)
                _base_gate(ctx, construction, results)
                evidence = {
                    k: context[k]
                    for k in ("retrieved_evidence", "evidence_instruction")
                    if k in context
                }
                return _expansion_module(ctx, construction, t_end, evidence)
        else:
            ok, results = _run_ladder(
                ctx, construction["antimony"], construction["parameters"], t_end
            )
            support = None
            if ok:
                gl_problems = glossary_problems(construction, ctx.cache["_s1_sbml"])
                if not _glossary_gate(ctx, gl_problems):
                    failures = [
                        f"entity_glossary incomplete: {pr}" for pr in gl_problems
                    ]
                    ctx.cache.pop("_s1_sbml", None)
                else:
                    support, failures = _essential_gates(
                        ctx, context, construction, ctx.cache["_s1_sbml"]
                    )
                    if failures:
                        ctx.cache.pop("_s1_sbml", None)
            else:
                failures = [r.detail for r in results if not r.passed and r.blocking]
            if ok and not failures:
                history.mark_passed()
                _persist_single(ctx, model, construction)
                _put_support(model, support)
                checker_lines = []
                decisions = construction["build_report"]["decisions"]
                if ctx.spec.get("verification.citation_check", True):
                    checker_lines += _citation_resolution(ctx, decisions)
                    rep = (model / "build_report").get()
                    rep["decisions"] = decisions
                    (model / "build_report").put(rep)
                if ctx.spec.get("verification.s1", True):
                    checker_lines += _t3_construction_audit(ctx, construction)
                checker_lines += _redraft_lines(history, dossier)
                cand_ids = _scope_gate(ctx, results, construction, checker_lines)
                if cand_ids:
                    # the human bought a model-space search: this round becomes
                    # a candidate set, fitted and selected by criterion
                    ctx.set_marker(
                        "s1",
                        producer="agent:construction",
                        candidates=cand_ids,
                        search=True,
                    )
                    return cand_ids
                ctx.set_marker("s1", producer="agent:construction")
                return None
        # ---- the attempt failed: into the dossier, then decide whether to go on
        ant = construction.get("antimony", "")
        implicated = _retry.implicated_names(failures)
        # a base that failed its essential set or its graph and names what it
        # lacks climbs the search ladder in strict mode: a search, then a
        # lowered floor, then the person; in advisory mode nothing it adds is
        # refused for its support, so there is nothing to search for
        knowledge = ctx.cache.pop("_s1_knowledge_failed", None)
        questions = (
            _kn_questions(construction.get("missing"))
            if knowledge is not None and _rxe.strict(ctx)
            else []
        )
        step = _search_step(history) if questions else None
        entry = history.add(
            failures,
            _retry.antimony_summary(ant, failures),
            previous_text=prev_ant,
            current_text=ant if prev_ant else None,
            implicated=implicated,
            extra=({"missing": questions, "search_step": step} if step else None),
        )
        ctx.ledger.append(
            "redraft",
            module="model",
            round_idx=ctx.round_idx,
            role="construction",
            attempt=entry["attempt"],
            n_failures=len(failures),
            localized=_retry.localized(failures),
            **(
                {
                    "collateral_change_ratio": entry["what_changed_vs_previous"][
                        "collateral_change_ratio"
                    ]
                }
                if entry.get("what_changed_vs_previous")
                else {}
            ),
        )
        print(
            f"  redraft: attempt {entry['attempt']} failed {len(failures)} check(s); "
            f"dossier now carries {len(history)} attempt(s)"
        )
        if step in (STEP_SEARCH, STEP_FLOOR):
            finding = _answer_missing(
                ctx, context, construction, questions, step, failures, knowledge
            )
            raise _hr.RedraftRequested(finding, "construction", source=_hr.ENGINE)
        prev_ant = ant
        context.pop("previous_attempt_errors", None)
        attempt += 1


# the rungs of the search ladder a base climbs when it fails its essential set
# or its graph and names what it lacks: a targeted search, then a floor one band
# lower, then the person (the exhaustion gate)
STEP_SEARCH = "search"
STEP_FLOOR = "floor_lowered"
STEP_PERSON = "person"


def _kn_questions(missing) -> list[dict]:
    from octomod.workflow_modules.knowledge import engine as _kn

    return _kn.targeted_questions(missing)


def _floor_setter(ctx: RunContext, context: dict):
    """`floor: <band|none>` at the redraft-budget card: the round's floor
    written as the person's (source `human`, a `floor_set` row), construction's
    own searches of the round admitted again at it, and construction's context
    rebuilt from the base set as it now stands. The callable returns None when
    it acted, else the reason it did not."""

    def set_floor(raw: str) -> str | None:
        word = _rxe.parse_band(raw)
        if word is None or word == _rxe.NOT_APPLICABLE:
            return "not a floor — accepted: high, medium, low, weak, none"
        cur = _rxe.floor_of(ctx) or {}
        if _rxe.floor_band(cur) == _rxe.NOT_APPLICABLE:
            return "the knowledge module ran offline: no floor applies"
        _rxe.write_floor(
            ctx,
            word,
            _rxe.step_of(cur, ctx.spec),
            "human",
            note=f"support floor {_rxe.band_text(word)} set by the person at the "
            f"redraft-budget card",
            module="model",
        )
        floor = _rxe.base_floor(ctx)
        in_base = _rxe.base_set(_rxe.dossier_of(ctx), floor)["ids"]
        for n, rec in _rxe.searches(ctx):
            if _rxe.requested_by(rec) == _rxe.REQUESTED_BY_CONSTRUCTION:
                _rxe.admit(ctx, n, floor, in_base=in_base)
        _put_essential_context(ctx, context)
        return None

    return set_floor


def _search_step(history) -> str:
    """The rung the next failure with `missing` stands on: counted from the
    engine redrafts already granted in this round (`SEARCH_GRANT`)."""
    k = sum(1 for g in history.grants if g.get("why") == SEARCH_GRANT)
    return (STEP_SEARCH, STEP_FLOOR)[k] if k < 2 else STEP_PERSON


def _search_ladder_spent(history) -> bool:
    """The last draft failed its essential set after the search and the
    lowered floor, and nobody has granted another attempt since: the person
    is asked before anything else is spent — on a resume too."""
    if not history.attempts:
        return False
    if history.attempts[-1].get("search_step") != STEP_PERSON:
        return False
    n = len(history.attempts)
    return not any(int(g.get("after_attempts") or 0) >= n for g in history.grants)


def _question_key(q: dict) -> str:
    eq = str((q or {}).get("equation") or "")
    try:
        return _rxe.canonical(_rxe.parse_equation(eq))
    except _rxe.EquationError:
        return " ".join(eq.split())


def _answer_missing(
    ctx: RunContext,
    context: dict,
    construction: dict,
    questions: list[dict],
    step: str,
    failures: list[str],
    knowledge: dict,
) -> str:
    """The engine's answer to a base that failed its essential set or its
    graph and named what it lacks (`missing`), on the rung `step`:

    - `search`: one targeted search (`knowledge.targeted_search`) with the
      questions, while the round's cap allows it (`grounding.search.
      per_redraft` searches per redraft, counted in `knowledge_search`); when
      it does not, the floor is lowered instead;
    - `floor_lowered`: the floor goes one band down
      (`reaction_evidence.lower_floor`), and a new search runs only for a
      question no search of the round asked.

    Then every search of the round is admitted at the floor as it now stands
    (`reaction_evidence.admit`), construction's context gets the new base set,
    and the text returned — the failures and what the engine did — is the
    finding construction is asked again with."""
    from octomod.workflow_modules.knowledge import engine as _kn

    # construction's own searches: the expansions' and an expansion's are
    # counted against their own caps
    every = _rxe.searches(ctx)
    done = [
        (n, rec)
        for n, rec in every
        if _rxe.requested_by(rec) == _rxe.REQUESTED_BY_CONSTRUCTION
    ]
    cap = _rxe.search_caps(ctx.spec)["per_redraft"]
    rung = 1 if step == STEP_SEARCH else 2
    asked = {
        _question_key(q)
        for _, rec in done
        for q in rec.get("questions") or []
        if isinstance(q, dict)
    }
    fresh = [q for q in questions if _question_key(q) not in asked]
    ask = questions if step == STEP_SEARCH else fresh
    search_now = bool(ask) and len(done) < cap * rung
    named = ", ".join(q["equation"] for q in questions)
    lowered = None
    if step == STEP_FLOOR or not search_now:
        why = (
            "the base failed its essential set a second time"
            if step == STEP_FLOOR
            else "the round's targeted searches are spent (grounding.search.per_redraft)"
        )
        lowered = _rxe.lower_floor(ctx, f"{why}; construction names {named} missing")
    n_new = None
    if search_now:
        n_new = len(every) + 1
        view = _rxe.dossier_of(ctx)
        base = _rxe.base_set(view, _rxe.base_floor(ctx))
        print(f"  → targeted search {n_new} for what the base lacks: {named}")
        _kn.targeted_search(
            ctx,
            ask,
            n_new,
            model_summary=draft_model_summary(
                construction, (knowledge or {}).get("sbml")
            ),
            essential_ids=[
                {"id": e.get("id"), "equation": e.get("equation")}
                for e in base["reactions"]
            ],
            requested_by="construction",
            known=view.get("reactions"),
        )
    # every search of the round, at the floor as it now stands
    floor = _rxe.base_floor(ctx)
    in_base = _rxe.base_set(_rxe.dossier_of(ctx), floor)["ids"]
    results = {
        n: _rxe.admit(ctx, n, floor, in_base=in_base)
        for n, rec in _rxe.searches(ctx)
        if _rxe.requested_by(rec) == _rxe.REQUESTED_BY_CONSTRUCTION
    }
    band = _rxe.band_text(floor.get("band"))
    if n_new is not None:
        ledger_search(
            ctx,
            n_new,
            _rxe.REQUESTED_BY_CONSTRUCTION,
            results.get(n_new) or {},
            floor.get("band"),
        )
    readmitted = [
        rid
        for n, res in results.items()
        if n != n_new
        for rid in res.get("admitted") or []
    ]
    if lowered is not None:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=(
                f"the round's searches read again at floor {band}: "
                + (
                    f"{', '.join(readmitted)} admitted"
                    if readmitted
                    else "nothing further admitted"
                )
            ),
        )
    _put_essential_context(ctx, context)
    # the finding, in the words construction is asked again with
    admitted_rows = {
        str(e.get("id")): e for e in (ctx.round / _rxe.ADMITTED_KEY).get(None) or []
    }
    new_ids = [rid for res in results.values() for rid in res.get("admitted") or []]
    lines = ["Your base failed its checks:"] + [f"- {f}" for f in failures]
    if n_new is not None:
        lines.append(
            f"The engine ran a targeted literature search (search {n_new}) for what "
            f"you named missing: " + "; ".join(q["question"] for q in ask) + "."
        )
    elif step == STEP_SEARCH:
        lines.append("No search was run: the round's targeted searches are spent.")
    elif not fresh:
        lines.append(
            "No new search was run: you named nothing a search of this round had "
            "not already asked."
        )
    if lowered is not None:
        lines.append(
            f"The support floor was lowered one band, from "
            f"{_rxe.band_text(lowered[0])} to {_rxe.band_text(lowered[1])}, and every "
            f"search of this round was read again at it."
        )
    if new_ids:
        lines.append(
            "Admitted into the essential set (origin search): "
            + "; ".join(
                f"{rid} {(admitted_rows.get(rid) or {}).get('equation')} — "
                + _rxe.because_text(
                    (admitted_rows.get(rid) or {}).get("grade"),
                    (admitted_rows.get(rid) or {}).get("because"),
                )
                for rid in new_ids
            )
            + "."
        )
    else:
        below = [b for res in results.values() for b in res.get("not_admitted") or []]
        lines.append(
            f"Nothing was admitted at the support floor {band}"
            + (
                ": "
                + "; ".join(
                    f"{b.get('id')} {b.get('equation')} ({b.get('why')})" for b in below
                )
                if below
                else "."
            )
        )
    lines.append(
        "`essential_reactions` holds the set as it now stands: implement every entry, "
        "add nothing it lacks, and name in `missing` only what it still lacks."
    )
    return "\n".join(lines)


def ledger_search(
    ctx: RunContext,
    n: int,
    requested_by: str,
    admission: dict,
    floor_band,
    *,
    module: str = "model",
) -> None:
    """The `knowledge_search` row of the round's search `n`: who asked, its
    questions, what it found, what it admitted at which floor and what not,
    its cost — ledgered once, when the search ran."""
    node = ctx.round / _rxe.SEARCH_KEY / str(n)
    rec = node.get({}) or {}
    found = [r for r in rec.get("reactions") or [] if isinstance(r, dict)]
    band = _rxe.band_text(floor_band)
    admitted = list(admission.get("admitted") or [])
    ctx.ledger.append(
        "knowledge_search",
        module=module,
        round_idx=ctx.round_idx,
        artifact=node.key,
        n=n,
        requested_by=requested_by,
        questions=[q.get("question") for q in rec.get("questions") or []],
        n_found=len(found),
        n_facts=len(rec.get("facts") or []),
        n_admitted=len(admitted),
        admitted=admitted,
        not_admitted=list(admission.get("not_admitted") or []),
        floor=floor_band,
        failed=rec.get("failed"),
        battery_failures=len(rec.get("battery_failures") or []),
        cost_usd=(rec.get("cost") or {}).get("usd"),
        note=(
            f"targeted search {n} for {requested_by}: {len(found)} reaction(s) "
            f"found, "
            + (
                f"{len(admitted)} admitted at floor {band}: {', '.join(admitted)}"
                if admitted
                else f"nothing admitted at floor {band}"
            )
            + (
                f" — the call failed: {rec['failed'][:160]}"
                if rec.get("failed")
                else ""
            )
        ),
    )


def round_search_by(ctx: RunContext, *who: str) -> int | None:
    """The number of this round's targeted search asked for by one of `who`
    (the first), or None: a round's expansions, and its expansion, spend one."""
    for n, rec in _rxe.searches(ctx):
        if str(rec.get("requested_by") or "") in who:
            return n
    return None


def _knowledge_card_lines(
    ctx: RunContext, construction: dict | None, support: dict | None = None
) -> list[str]:
    """What the scope card says about the base's essential set, from the
    record so a resumed card says what the first one said: the set and the
    floor it was built at, what the floor left out, the round's searches and
    the floor's history, and an advisory line when no quantity is marked
    `set_per_condition` while the intent lists perturbations. In advisory
    mode the set is prior knowledge, and the model's annotation (`support`)
    adds each essential entry the model does not implement and each reaction
    below the floor. Nothing when the run does not build on the knowledge
    module."""
    if not _rxe.active(ctx):
        return []
    view = _rxe.dossier_of(ctx)
    floor = _rxe.base_floor(ctx)
    base = _rxe.base_set(view, floor)
    by_origin: dict[str, int] = {}
    for e in base["reactions"]:
        o = _rxe.origin_of(e)
        by_origin[o] = by_origin.get(o, 0) + 1
    strict = _rxe.strict(ctx)
    head = (
        f"the base is built from {len(base['ids'])} reaction(s)"
        if strict
        else f"prior knowledge (advisory): {len(base['ids'])} reaction(s)"
    )
    lines = [
        f"ESSENTIAL SET — {head} at the support floor "
        f"{_rxe.band_text(floor.get('band'))} ({floor.get('source')}): "
        + ", ".join(f"{n} {o}" for o, n in by_origin.items())
    ]
    lines += [
        f"  left out: {x['id']} {x.get('equation')} — {x['why']}"
        for x in base.get("left_out") or []
    ]
    if not strict and support:
        unused = {str(x) for x in support.get("unused_entries") or []}
        lines += [
            f"  not implemented: {e['id']} {e.get('equation')} — "
            f"{_rxe.band_text(e.get('grade'))}"
            for e in base["reactions"]
            if str(e.get("id")) in unused and not e.get("required")
        ]
        lines += [
            f"  {_rxe.below_floor_line(r, floor.get('band'))}"
            for r in _rxe.model_below_floor(support, view, floor)
        ]
    lines += [f"  {x}" for x in _rxe.search_card_lines(ctx)]
    reply = construction
    if reply is None:
        reply = (ctx.agent_calls.child("construction") / "reply").get(None)
    if isinstance(reply, dict):
        if not set_per_condition_ids(reply) and (ctx.intent or {}).get("perturbations"):
            lines.append(
                "  ⚑ no quantity is marked `set_per_condition: true` while the intent "
                "lists perturbations — model_connected checked the graph with no inputs"
            )
        named = _kn_questions(reply.get("missing"))
        if named:
            lines.append(
                f"  construction names {len(named)} conversion(s) missing, and the "
                f"base passed its checks without them — not searched: "
                + "; ".join(q["equation"] for q in named)
            )
    return lines


def _run_single(ctx: RunContext, model: Node, t_end: float, author: str):
    """A `model/antimony` already in the record — the user's, the seed's, or
    the agent's from the pass that paused at the scope gate. `author` is
    recorded as the marker's producer; the construction agent is not called
    either way, the gates run."""
    antimony_src = (model / "antimony").text()
    parameters = _load_supplied_parameters(model)
    ctx.ledger.append(
        "note",
        module="model",
        round_idx=ctx.round_idx,
        note=f"model/antimony in the record ({author}); construction agent not "
        f"called, gates run",
    )
    ok, results = _run_ladder(ctx, antimony_src, parameters, t_end)
    if not ok:
        raise ModuleFailure(
            "supplied model failed the S1 gate ladder — see "
            f"{ctx.gates.key} for the failing check"
        )
    sbml = ctx.cache.pop("_s1_sbml")
    (model / "sbml").put_text(sbml)
    # the drafting pass annotated its model before this pause; a model that
    # reaches here without one is annotated now, when the round has a dossier
    if not (model / _rxe.SUPPORT_KEY).exists():
        _put_support(model, _reaction_support(ctx, sbml, parameters))
    # the drafting pass's citation, audit and redraft lines, from its record:
    # a resumed card must say what the first one said
    cand_ids = _scope_gate(ctx, results, None, _recorded_checker_lines(ctx, model))
    if cand_ids:
        # a supplied model can carry a model space, and a resumed run always
        # arrives here (the first pass wrote model/antimony before the scope gate)
        ctx.set_marker("s1", producer=author, candidates=cand_ids, search=True)
        return cand_ids
    ctx.set_marker("s1", producer=author)
    return None


# ------------------------------------------------------------ MD candidates


def _record_encoding(ctx, encoding: dict) -> None:
    """Persist the lattice's encoding and record its verification as a GATE.

    `model_supermodel_neutrality` is T1 and non-blocking: a false neutral
    declaration only sends its axis back to being its own structure, so the
    lattice the human bought is unchanged. It is recorded because the winner is
    later simulated at these same neutral values.
    """
    from octomod.gates import GateResult, gate, run_gate_set

    (ctx.round / "model/encoding").put(encoding)
    ver = encoding.get("verification") or {}
    per_axis = ver.get("per_axis") or {}
    liars = sorted(k for k, v in per_axis.items() if not v.get("neutralizes"))
    joint = ver.get("joint_failures") or []
    absorbed = encoding.get("absorbed_axes") or []
    if not per_axis:
        detail = (
            "no axis declared a usable neutral value, so every candidate is "
            "its own structure (no shared compiled model to switch terms off in)"
        )
    elif liars or joint:
        detail = (
            f"{len(liars)} declared neutral value(s) do not neutralize "
            f"{liars or ''}"
            + (f"; combined: {joint[0]}" if joint else "")
            + f" — those axes are separated back out; {len(absorbed)} axis/axes "
            f"still share one structure"
        )
    else:
        detail = (
            f"every declared neutral value reproduces the base model to "
            f"{ver.get('checked_to', {}).get('rtol')}: {len(absorbed)} axis/axes "
            f"absorbed into one structure, {encoding.get('compiles_saved', 0)} "
            f"AMICI compile(s) saved over {encoding.get('n_models', 0)} candidates"
        )

    @gate("model_supermodel_neutrality", "T1")
    def g():
        return GateResult(
            gate_id="model_supermodel_neutrality",
            tier="T1",
            passed=not (liars or joint),
            blocking=False,
            value=f"{len(absorbed)}/{len(absorbed) + len(liars)} verified",
            threshold=f"rtol {ver.get('checked_to', {}).get('rtol')}",
            detail=detail,
        )

    run_gate_set(
        [g],
        _tree.gates_node(ctx.round, None),
        ctx.ledger,
        module="model",
        round_idx=ctx.round_idx,
    )
    for n in encoding.get("noop_axes") or []:
        print(f"  axis {n['id']} is a no-op on this base: {n['why'][:110]}")
    print(
        f"  lattice encoding: {encoding.get('kind')} — "
        f"{encoding.get('n_models')} candidate(s) over "
        f"{encoding.get('n_structures')} structure(s)"
        + (
            f", {encoding['compiles_saved']} compile(s) saved"
            if encoding.get("compiles_saved")
            else ""
        )
    )
    for aid, reason in (encoding.get("why_separate") or {}).items():
        print(f"    · {aid} stays its own structure: {reason}")


def _ladder_candidates(
    ctx: RunContext, construction: dict, t_end: float, max_candidates: int | None = None
):
    """Run the S1 gate ladder over a candidate set.

    `max_candidates` distinguishes the two ways a set can arrive. Mechanism
    discrimination bounds what an AGENT may propose (2-5 rival mechanisms, a
    contract limit). A model-space search bounds what the ENGINE enumerates
    (capped by search.max_models), so the agent-facing limit must not apply.
    """
    cands = construction.get("candidates") or []
    max_c = int(
        max_candidates
        if max_candidates is not None
        else ctx.spec.get("estimation.md_max_candidates", 5)
    )
    if not (2 <= len(cands) <= max_c):
        return (
            [],
            [
                {
                    "id": "(contract)",
                    "reason": f"'candidates' must hold 2-{max_c} entries, got {len(cands)}",
                }
            ],
            [],
        )
    survivors, dropped, gate_lines = [], [], []
    seen = set()
    for cand in cands:
        cid = str(cand.get("id", "")).strip()
        if not cid or cid in seen:
            dropped.append({"id": cid or "(empty)", "reason": "missing/duplicate id"})
            continue
        seen.add(cid)
        with as_candidate(ctx, cid):
            ok, results = _run_ladder(
                ctx, cand["antimony"], cand.get("parameters", []), t_end
            )
        gate_lines += [f"[{cid}] {r.summary().strip()}" for r in results]
        if ok:
            survivors.append((cand, ctx.cache.pop("_s1_sbml")))
        else:
            dropped.append(
                {
                    "id": cid,
                    "reason": "; ".join(
                        r.detail for r in results if not r.passed and r.blocking
                    ),
                }
            )
    return survivors, dropped, gate_lines


# ------------------------------------------------------------ staged discrimination
#
# A discrimination round in two calls: construction writes the BASE, the engine
# tests it as one model, and `expansion` writes each candidate as a declared
# difference from it, which `octomod/workflow_modules/model/expansion.py` builds. Every repair —
# a person's redraft or a failed check — hands the agent its own previous reply
# and asks for a revision of it, never a new draft.


# a construction reply that writes candidates, in the words handed back
CANDIDATES_REFUSED = (
    "construction writes the base only; the expansion agent writes the candidates"
)


def _base_gate_enabled(ctx: RunContext) -> bool:
    """The optional human gate on the base, before any variation is written:
    per run in testcase.yaml (`s1: {base_gate: true}`), else the workflow's."""
    own = ctx.testcase.get("s1") if isinstance(ctx.testcase, dict) else None
    if isinstance(own, dict) and "base_gate" in own:
        return bool(own["base_gate"])
    return bool(ctx.spec.get("s1.base_gate", False))


def _base_key(base: dict) -> str:
    """Which base a expansions reply was written against, so a redrafted base
    is never paired with candidates built for the previous one."""
    import hashlib
    import json as _json

    blob = _json.dumps(
        {"antimony": base.get("antimony"), "parameters": base.get("parameters")},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _base_model(ctx: RunContext) -> Node:
    """The round's tested BASE of a two-call discrimination round: a sibling
    model group, `base_model/*` — NOT `model/*`, which a resume reads as a
    user-supplied single model and a discrimination round refuses outright."""
    return ctx.round / "base_model"


def _base_model_previous(ctx: RunContext) -> Node:
    """The base a person sent back, kept when the redraft replaces it so the
    card can say what moved (`base_model_previous/{antimony,parameters}`)."""
    return ctx.round / "base_model_previous"


def _persist_base(
    ctx: RunContext, construction: dict, sbml: str, *, redrafted: bool = False
) -> None:
    """The tested base, under `base_model/` — NOT `model/antimony`, which a
    resume reads as a user-supplied single model and a discrimination round
    refuses outright.

    When a person sent the base back (`redrafted`), the base they read is kept
    in `base_model_previous/` before the new one replaces it, so the card can
    say what moved."""
    base = _base_model(ctx)
    if redrafted and (base / "antimony").exists() and (base / "parameters").exists():
        prev = _base_model_previous(ctx)
        for name in ("antimony", "parameters"):
            (base / name).copy_to(prev / name)
    ant = construction["antimony"]
    (base / "antimony").put_text(ant if ant.endswith("\n") else ant + "\n")
    (base / "sbml").put_text(sbml)
    (base / "parameters").put(construction["parameters"])
    if construction.get("entity_glossary"):
        (base / "glossary").put(construction["entity_glossary"])
    params = construction["parameters"]
    n_est = sum(1 for p in params if p.get("estimate", True))
    ctx.ledger.append(
        "note",
        module="model",
        round_idx=ctx.round_idx,
        note=f"the base passed its checks ({len(params)} parameters, "
        f"{n_est} estimated) and is in {base.key}; the candidates are built on it",
    )


def _base_diff_lines(ctx: RunContext, construction: dict) -> list[str]:
    """What the redrafted base changed against the base the person sent
    back (`base_model_previous/`) — reactions, parameters, other lines; empty
    when no base was sent back this round."""
    prev = _base_model_previous(ctx)
    if not (prev / "antimony").exists():
        return []
    try:
        old_ant = (prev / "antimony").text()
        old_par = (prev / "parameters").get([]) or []
    except Exception:
        return []
    return base_diff(
        old_ant,
        old_par,
        construction["antimony"],
        construction["parameters"],
        where=prev.key,
    )


def base_diff(
    old_ant: str,
    old_par: list,
    new_ant: str,
    new_par: list,
    where: str = "base_model_previous",
) -> list[str]:
    """The card lines of a model-vs-model difference: reactions added, removed
    or with a changed rate law (by reaction id), parameters added, removed or
    changed (value, bounds, estimate flag), other lines added/removed. `where`
    names the record the old base is kept at, on the header line."""
    from octomod.workflow_modules.model import antimony_text as _at

    def reactions(text: str) -> dict[str, str]:
        out = {}
        for line in _at.strip_comments(text).splitlines():
            m = re.match(r"\s*([A-Za-z_]\w*)\s*:(?!=)(.*->.*)$", line)
            if m:
                out[m.group(1)] = re.sub(r"\s+", "", m.group(2)).rstrip(";")
        return out

    p0 = {str(p.get("id")): p for p in old_par or []}
    p1 = {str(p.get("id")): p for p in new_par or []}

    def others(text: str) -> set[str]:
        """Statements that are neither a reaction nor a parameter's value
        (those are reported above, by id)."""
        keep = set()
        for line in _at.strip_comments(text).splitlines():
            # a reaction line's `;` separates its equation from its rate law —
            # the whole line is a reaction, reported above by id
            if re.match(r"\s*[A-Za-z_]\w*\s*:(?!=).*->", line):
                continue
            for stmt in line.split(";"):
                t = re.sub(r"\s+", " ", stmt).strip()
                v = re.match(r"(?:const\s+|var\s+)?([A-Za-z_]\w*)\s*=", t)
                if (
                    not t
                    or (v and v.group(1) in set(p0) | set(p1))
                    or t == "end"
                    or t.startswith("model ")
                ):
                    continue
                keep.add(t)
        return keep

    r0, r1 = reactions(old_ant), reactions(new_ant)
    fields = ("nominal_value", "lb", "ub", "estimate")
    changed_p = []
    for pid in sorted(set(p0) & set(p1)):
        moved = [
            f"{f} {p0[pid].get(f)!r} → {p1[pid].get(f)!r}"
            for f in fields
            if p0[pid].get(f) != p1[pid].get(f)
        ]
        if moved:
            changed_p.append(f"{pid} ({'; '.join(moved)})")
    o0, o1 = others(old_ant), others(new_ant)

    def ids(xs, n=8):
        xs = sorted(xs)
        return ", ".join(xs[:n]) + (f" … (+{len(xs) - n})" if len(xs) > n else "")

    add_r, rem_r = set(r1) - set(r0), set(r0) - set(r1)
    law_r = [rid for rid in sorted(set(r0) & set(r1)) if r0[rid] != r1[rid]]
    add_p, rem_p = set(p1) - set(p0), set(p0) - set(p1)
    if not (add_r or rem_r or law_r or add_p or rem_p or changed_p or (o0 ^ o1)):
        return [
            "",
            "CHANGED SINCE THE BASE YOU SENT BACK: nothing — the redraft returned the same model",
        ]
    out = ["", f"CHANGED SINCE THE BASE YOU SENT BACK ({where}):"]
    if add_r or rem_r or law_r:
        out.append(
            "  reactions: "
            + "; ".join(
                x
                for x in (
                    f"+{len(add_r)} ({ids(add_r)})" if add_r else "",
                    f"−{len(rem_r)} ({ids(rem_r)})" if rem_r else "",
                    f"rate law changed: {ids(law_r)}" if law_r else "",
                )
                if x
            )
        )
    if add_p or rem_p:
        out.append(
            "  parameters: "
            + "; ".join(
                x
                for x in (
                    f"+{len(add_p)} ({ids(add_p)})" if add_p else "",
                    f"−{len(rem_p)} ({ids(rem_p)})" if rem_p else "",
                )
                if x
            )
        )
    for c in changed_p[:8]:
        out.append(f"  changed: {c[:150]}")
    if len(changed_p) > 8:
        out.append(f"  … {len(changed_p) - 8} more parameter(s) changed")
    if o0 ^ o1:
        out.append(f"  other lines: +{len(o1 - o0)} / −{len(o0 - o1)}")
        for t in sorted(o1 - o0)[:4]:
            out.append(f"    + {t[:120]}")
        for t in sorted(o0 - o1)[:4]:
            out.append(f"    − {t[:120]}")
    return out


def _base_card_lines(construction: dict, results) -> list[str]:
    params = construction["parameters"]
    est = [p for p in params if p.get("estimate", True)]
    per_group = [p for p in est if p.get("varies_by")]
    n_rx = sum(
        1
        for line in construction["antimony"].splitlines()
        if re.match(r"\s*[A-Za-z_]\w*\s*:", line) and "->" in line
    )
    lines = [
        f"base model: {n_rx} reactions, {len(params)} parameters — {len(est)} "
        f"estimated ({len(per_group)} of them per group), {len(params) - len(est)} fixed",
        f"checks: {sum(1 for r in results if r.passed)} of {len(results)} passed",
    ]
    lines += [f"  advisory: {r.summary().strip()}" for r in results if not r.passed]
    decisions = construction["build_report"]["decisions"]
    lines.append(
        f"construction's decisions ({len(decisions)}, all in the build report):"
    )
    lines += [f"  · {str(d.get('decision', ''))[:150]}" for d in decisions]
    return lines


def _base_gate(ctx: RunContext, construction: dict, results) -> None:
    """Optional: a person looks at the mechanism before five candidates
    multiply it. A redraft here goes back to construction with its reply."""
    if not _base_gate_enabled(ctx):
        return

    decisions = construction["build_report"]["decisions"]
    flagged = [d for d in decisions if d.get("user_decision_required")]
    base = _base_model(ctx)
    lines = (
        _base_card_lines(construction, results)
        + _base_diff_lines(ctx, construction)
        + _dc.card_lines(ctx.cache.get("_declared_constant_rows") or [])
        + _declared_space_lines(construction)
        # no model report is written for the base: its annotation is the record
        + _reaction_card_lines(base, (base / _rxe.SUPPORT_KEY).key)
    )
    # the grounding lines print whatever the card's evidence cap
    grounding = _reaction_card_lines(base, (base / _rxe.SUPPORT_KEY).key)
    if flagged:
        lines.append("")
        lines.append(
            "THE AGENT ASKS (genuinely ambiguous choices it will act on either way):"
        )
        for k, d in enumerate(flagged, 1):
            lines.append(f"  {k}. {d.get('question') or d['decision']}")
        lines.append(
            "  → answer in the note, e.g.:  y 1: face value; 2: leave unmodelled"
        )
    decision = ctx.round / "decisions/model_base"
    approved, note = humangate.ask_once(
        ctx,
        decision,
        "Build the candidate expansions on this base?",
        lines,
        module="model_base_scope",
        record_decline=False,
        uncapped=grounding,
        intent=ctx.intent,
        consequences=(
            "the expansion agent writes each candidate as a difference from this "
            "base; the engine builds and checks every one",
            "run stops; rerun to redraft the base",
        ),
        note_forms=(
            "1: <answer>  2: <answer>    answer the agent's numbered questions",
            _hr.NOTE_FORM,
            "(nothing)                   approve the base as it is",
        ),
        documents=[("the base model (Antimony)", base / "antimony")]
        + (
            [("where each reaction comes from", base / _rxe.SUPPORT_KEY)]
            if (base / _rxe.SUPPORT_KEY).exists()
            else []
        ),
    )
    if not approved:
        raise ModuleFailure("user rejected the base model at the S1 base gate")
    text = _hr.parse(note)
    if text:
        _hr.send_back(ctx, "model_base_scope", "construction", text, remove=[decision])
    if flagged:
        record_open_questions(ctx, flagged, note, prefix="s1base")


def _expansion_context(ctx: RunContext, base: dict, evidence: dict) -> dict:
    max_c = int(ctx.spec.get("estimation.md_max_candidates", 5))
    decisions = (base.get("build_report") or {}).get("decisions") or []
    return {
        **_expansion_brief(ctx, base, evidence, max_c, decisions),
        **_expansion_grounding(ctx),
    }


def _expansion_grounding(ctx: RunContext) -> dict:
    """With the knowledge module's output in the run, what the expansions are
    shown of it: `essential_reactions` (the base's set, which `base_model`
    implements), `prior_reactions` (the round's whole dossier, with what a
    search admitted), `variants_floor` (`{band, base, offset, words}`: what a
    variation may add), `knowledge_summary`, the facts meant for construction
    (`known_facts`) and `grounding_instruction`. Nothing otherwise, so the
    prompt is what it was."""
    if not _rxe.active(ctx):
        return {}
    from octomod.workflow_modules.knowledge import engine as _kn

    view = _rxe.dossier_of(ctx)
    if not view.get("reactions"):
        return {}
    vf = _rxe.variants_floor(ctx)
    out = {
        "essential_reactions": _rxe.essential_rows(
            _rxe.base_set(view, _rxe.base_floor(ctx))
        ),
        "prior_reactions": _rxe.prior_reactions(view),
        "variants_floor": {k: vf[k] for k in ("band", "base", "offset", "words")},
        "grounding_instruction": (
            _rxe.VARIATIONS_INSTRUCTION
            if _rxe.strict(ctx)
            else _rxe.VARIATIONS_ADVISORY_INSTRUCTION
        ),
    }
    if view.get("system"):
        out["knowledge_summary"] = view["system"]
    facts = _kn.facts_for(view, "construction")
    if facts:
        out["known_facts"] = facts
    return out


def _expansion_brief(
    ctx: RunContext, base: dict, evidence: dict, max_c: int, decisions: list
) -> dict:
    """The problem, the tested base and the instruction the expansions are
    written from."""
    return {
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        "domain_packs": ctx.pack_texts(),
        **evidence,
        "base_model": {
            "antimony": base.get("antimony"),
            "parameters": base.get("parameters"),
            "entity_glossary": base.get("entity_glossary"),
            "decisions": [
                {k: d.get(k) for k in ("decision", "rationale", "confidence")}
                for d in decisions
            ],
            "declared_axes_for_a_later_round": [
                {"id": a.get("id"), "question": a.get("question")}
                for a in base.get("model_space") or []
            ],
        },
        "instruction": (
            f"Write the 2-{max_c} candidates of this discrimination round as "
            "DIFFERENCES from `base_model`, which the engine has already tested. "
            "Prefer the switches construction built in (its decisions say which "
            "parameter switches which feature); patch a reaction only where a "
            "tested feature cannot be a switch. Each candidate differs from the "
            "base only in its tested feature, and the base itself is a candidate "
            "when the comparison needs the model with no tested feature on. "
            "`declared_axes_for_a_later_round` are tested by the engine after "
            "this round — do not build them into candidates."
        ),
    }


def _merged_construction(base: dict, reply: dict, cands: list[dict]) -> dict:
    """The base reply with the built candidates in place of `candidates`, and
    both calls' decisions in one build report — the shape `_persist_md` and
    everything downstream already read."""
    vdec = list((reply.get("build_report") or {}).get("decisions") or [])
    merged = dict(base)
    merged["candidates"] = cands
    merged["build_report"] = {
        **(base.get("build_report") or {}),
        "decisions": list((base.get("build_report") or {}).get("decisions") or [])
        + vdec,
    }
    merged["_staged"] = True
    return merged


def _raise_if_staged_redraft(ctx: RunContext, note) -> None:
    """At a staged scope card, `redraft base:` goes to construction and plain
    `redraft:` to the expansion. A base redraft also clears the base gate's
    decision: a changed base is approved again, not waved through."""
    scope = ctx.round / "decisions/model_scope"
    base_text = _hr.parse_base(note)
    if base_text:
        _hr.send_back(
            ctx,
            "model_scope",
            "construction",
            base_text,
            remove=[scope, ctx.round / "decisions/model_base"],
        )
    text = _hr.parse(note)
    if text:
        _hr.send_back(ctx, "model_scope", "expansion", text, remove=[scope])


def _variants_under_floor(
    ctx: RunContext, base: dict, reply: dict, survivors
) -> tuple[list, list[dict], list[str]]:
    """The expansions gate under the floor, with the knowledge module's output
    in the run. A variation that ADDS a conversion (`new_reactions` against the
    tested base: an id the base lacks, or a kept id whose reactants or products
    moved) graded below the variants' floor, or one no dossier entry describes,
    is refused by name and dropped from the set — after the round's one
    targeted search (`grounding.search.per_round`, requested by the expansions)
    has looked for what the reply names in `missing` and admitted what reaches
    the variants' floor. Returns (the survivors kept, the dropped `{id,
    reason}`, the card's lines); everything is kept when the run does not
    build on the knowledge module. In advisory mode everything is kept, no
    search runs, and the card flags each such addition and each base
    reaction below the base's floor."""
    if not _rxe.active(ctx) or not survivors:
        return survivors, [], []
    view = _rxe.dossier_of(ctx)
    if not view.get("reactions"):
        return survivors, [], []
    vf = _rxe.variants_floor(ctx)
    strict = _rxe.strict(ctx)
    lines = [
        f"VARIANTS' FLOOR: {_rxe.band_text(vf['band'])} (the base's floor "
        f"{_rxe.band_text(vf['base'])} lowered by {vf['offset']}) — "
        + (
            "a conversion a variation adds must be described at it or better"
            if strict
            else "a conversion a variation adds below it is flagged, not refused"
        )
    ]
    base_rx, err = _rxe.base_reactions(base.get("antimony") or "")
    if base_rx is None:
        lines.append(
            f"  ⚑ the base does not convert to SBML ({err[:160]}); no variation was "
            f"held to the floor"
        )
        return survivors, [], lines
    base_ids = set(_rxe.base_set(view, _rxe.base_floor(ctx))["ids"])

    def refusals(dossier: dict) -> dict[str, list[dict]]:
        allowed = _rxe.admitted_at(
            dossier, vf["band"], exempt=base_ids | _rxe.exempt_ids(dossier, vf)
        )
        out: dict[str, list[dict]] = {}
        for cand, sbml in survivors:
            support = _rxe.annotate(dossier, sbml, cand.get("parameters") or [])
            refs = _rxe.floor_refusals(
                _rxe.new_reactions(support, base_rx), allowed, vf["band"]
            )
            if refs:
                out[str(cand["id"])] = refs
        return out

    refused = refusals(view)
    if not strict:
        bf = _rxe.base_floor(ctx)
        lines += [
            f"  {_rxe.below_floor_line(r, bf.get('band'), 'the base')}"
            for r in _rxe.model_below_floor(
                (_base_model(ctx) / _rxe.SUPPORT_KEY).get(None), view, bf
            )
        ]
        lines += [
            f"  {_rxe.below_floor_line(r, vf['band'], f'variation {cid}')}"
            for cid, refs in refused.items()
            for r in refs
        ]
        return survivors, [], lines
    questions = _kn_questions((reply or {}).get("missing"))
    n = round_search_by(ctx, _rxe.REQUESTED_BY_EXPANSION)
    fresh = False
    if n is None and refused and questions:
        if _rxe.search_caps(ctx.spec)["per_round"] > 0:
            from octomod.workflow_modules.knowledge import engine as _kn

            n = len(_rxe.searches(ctx)) + 1
            fresh = True
            print(
                f"  → targeted search {n} for what the expansions name missing: "
                + ", ".join(q["equation"] for q in questions)
            )
            _kn.targeted_search(
                ctx,
                questions,
                n,
                model_summary=draft_model_summary(
                    base, (_base_model(ctx) / "sbml").text(None)
                ),
                essential_ids=[
                    {"id": e.get("id"), "equation": e.get("equation")}
                    for e in _rxe.base_set(view, _rxe.base_floor(ctx))["reactions"]
                ],
                requested_by=_rxe.REQUESTED_BY_EXPANSION,
                known=view.get("reactions"),
            )
        else:
            lines.append(
                "  the expansions name conversions missing, and the run allows no "
                "search for them (grounding.search.per_round = 0)"
            )
    if n is not None:
        res = _rxe.admit(ctx, n, {"band": vf["band"]}, in_base=sorted(base_ids))
        if fresh:
            ledger_search(ctx, n, _rxe.REQUESTED_BY_EXPANSION, res, vf["band"])
        rec = (ctx.round / _rxe.SEARCH_KEY / str(n)).get({}) or {}
        adm = rec.get("admission") or {}
        lines.append(
            f"  search {n} (asked by the expansions): "
            + "; ".join(_question_text_of(q) for q in rec.get("questions") or [])
            + " — "
            + (
                f"admitted at floor {_rxe.band_text(adm.get('floor'))}: "
                + ", ".join(adm["admitted"])
                if adm.get("admitted")
                else f"nothing admitted at floor {_rxe.band_text(adm.get('floor'))}"
            )
        )
        lines += [
            f"    not admitted {b.get('id')} {b.get('equation')} — {b.get('why')}"
            for b in adm.get("not_admitted") or []
        ]
        refused = refusals(_rxe.dossier_of(ctx))
    elif refused:
        lines.append(
            "  the expansions name nothing missing: no search was run for the "
            "conversions below the floor"
        )
    kept = [(c, s) for c, s in survivors if str(c["id"]) not in refused]
    dropped = []
    # a resumed module refuses the same expansions again: one row each
    seen = {
        (e.get("candidate"), e.get("note"))
        for e in ctx.ledger.entries()
        if e.get("event") == "variation_refused_floor"
        and e.get("round") == ctx.round_idx
    }
    for cid, refs in refused.items():
        reason = _rxe.variant_refusal_reason(refs, vf["band"])
        dropped.append({"id": cid, "reason": reason})
        note = f"variation {cid} dropped: {reason}"
        if (cid, note) not in seen:
            ctx.ledger.append(
                "variation_refused_floor",
                module="model",
                round_idx=ctx.round_idx,
                candidate=cid,
                reactions=[r.get("reaction_id") for r in refs],
                bands=[r.get("band") for r in refs],
                floor=vf["band"],
                note=note,
            )
        print(f"  ✗ variation {cid} dropped: {reason[:200]}")
    return kept, dropped, lines


def _question_text_of(q) -> str:
    if isinstance(q, dict):
        return str(q.get("question") or q.get("equation") or q.get("id") or "")[:200]
    return str(q)[:200]


def _expansion_module(
    ctx: RunContext, base: dict, t_end: float, evidence: dict
) -> list[str]:
    """Write, build, check and — on failure — REPAIR the candidate set, then
    hand it to the scope gate. A candidate that fails is repaired with the
    reply that produced it, not dropped: the set is a design, and losing a
    member (such as the reference) would change what it compares."""
    from octomod.orchestration.interaction import retry as _retry
    from octomod.workflow_modules.model import expansion as _var

    call = ctx.agent_calls.child("expansion")
    cached = call / "reply"
    # which base the saved reply was written against (`_base_key`), a sibling
    # of the call's prompt and reply so `call_agent` never replaces it
    key_node = call / "base_key"
    dossier = _retry.dossier_of(ctx, "expansion")
    history = _retry.AttemptHistory(dossier)
    key = _base_key(base)
    context = _expansion_context(ctx, base, evidence)
    base_budget = int(ctx.spec.get("retry.module_draft", 2)) + 1
    attempt = len(history)
    first_pass = True
    while True:
        saved_key = key_node.text(None)
        same_base = saved_key is not None and saved_key.strip() == key
        if (
            first_pass
            and cached.exists()
            and same_base
            and "human_feedback" not in context
            and not history.last_draft_failed
        ):
            reply = cached.get()
            print(
                f"  (reusing the expansions reply from {cached.key} — no new agent call)"
            )
            ctx.ledger.append(
                "note",
                module="model",
                round_idx=ctx.round_idx,
                note=f"expansion reply reused from {cached.key} (same base); "
                f"no new agent call",
            )
        else:
            budget = base_budget + history.grants_total
            if attempt >= budget:
                granted = _retry.exhaustion_gate(
                    ctx, "model_expansion", "expansion", history, budget
                )
                if granted == 0:
                    raise ModuleFailure(
                        "the candidate expansions exhausted their repair budget and "
                        "the human did not extend it — every attempt and its "
                        f"failures in {dossier.key}"
                    )
                continue
            prev = _hr.previous_reply(ctx, "expansion")
            if prev is not None:
                context["previous_reply"] = prev
            if prev is not None and not same_base:
                context["base_changed_instruction"] = (
                    "The base was redrafted after your previous reply; `base_model` "
                    "is the new one. Rebuild the same candidates on it: keep their "
                    "ids and what each one tests, and change only what the new base "
                    "forces — say where in the build report."
                )
            else:
                context.pop("base_changed_instruction", None)
            if history.last_draft_failed:
                context["previous_attempt_errors"] = history.attempts[-1][
                    "gate_failures"
                ]
                context["attempt_history"] = history.as_context()
            history.clear_passed()
            reply = ctx.call("expansion", context)
            key_node.put_text(key + "\n")
            attempt += 1
        first_pass = False
        cands, failures = _var.materialize_all(base, reply.get("candidates") or [])
        survivors, gate_lines = [], []
        if not failures:
            survivors, dropped, gate_lines = _ladder_candidates(
                ctx, {"candidates": cands}, t_end
            )
            failures += [f"{d['id']}: {d['reason']}" for d in dropped]
        merged = _merged_construction(base, reply, cands)
        if not failures:
            gl = glossary_set_problems(merged, survivors)
            if gl:
                _glossary_gate(ctx, gl)
                failures += [f"entity_glossary incomplete: {p}" for p in gl]
        floor_dropped: list[dict] = []
        floor_lines: list[str] = []
        if not failures:
            # what a variation adds is held to the variants' floor: a refused
            # one leaves the set, named on the card; a set of fewer than two
            # goes back for repair with the refusals
            survivors, floor_dropped, floor_lines = _variants_under_floor(
                ctx, base, reply, survivors
            )
            if len(survivors) < 2:
                failures += [f"{d['id']}: {d['reason']}" for d in floor_dropped]
                failures.append(
                    "fewer than two candidates are left once the variants' floor "
                    "refused the expansions above — keep the base's reactions and "
                    "add only conversions the dossier describes at the floor"
                )
        if not failures:
            history.mark_passed()
            vdec = (reply.get("build_report") or {}).get("decisions") or []
            try:
                return _persist_md(
                    ctx,
                    merged,
                    survivors,
                    floor_dropped,
                    gate_lines,
                    questions_from=vdec if _base_gate_enabled(ctx) else None,
                    extra_lines=floor_lines,
                )
            except _hr.RedraftRequested as req:
                if req.role != "expansion":
                    raise
                context.update(
                    _hr.context_for(
                        req.text, "expansion", _hr.previous_reply(ctx, "expansion")
                    )
                )
                history.add_grant(1)
                print(f"  → redrafting the expansions at your request: {req.text[:90]}")
                continue
        entry = history.add(
            failures, {"n_candidates": len(reply.get("candidates") or [])}
        )
        ctx.ledger.append(
            "redraft",
            module="model",
            round_idx=ctx.round_idx,
            role="expansion",
            attempt=entry["attempt"],
            n_failures=len(failures),
            localized=True,
        )
        print(
            f"  expansions: attempt {entry['attempt']} failed {len(failures)} check(s); "
            f"sent back for repair with its own reply — {'; '.join(failures)[:200]}"
        )


def _move_aside_stale_candidates(ctx: RunContext, keep_ids: set) -> list[str]:
    """Move every candidate group not in the set being written aside — never
    delete it — into `superseded/model_candidates_<stamp>/candidates/<id>`, the
    convention `--from-module` uses, so no reader or re-entry scanning the
    round's candidates meets a model nobody approved. Returns the moved
    candidate ids."""
    import datetime

    if not (ctx.round / "candidates").exists():
        return []
    stale = sorted(c for c in _tree.candidate_ids(ctx.round) if c not in keep_ids)
    if not stale:
        return []
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = ctx.round / "superseded" / f"model_candidates_{stamp}"
    moved = []
    for cid in stale:
        src = _tree.work_node(ctx.round, cid)
        src.copy_to((dest / "candidates").child(cid))
        src.delete()
        moved.append(cid)
    ctx.ledger.append(
        "note",
        module="model",
        round_idx=ctx.round_idx,
        note=f"{len(moved)} candidate group(s) of an earlier draft moved aside to "
        f"{dest.key} (kept, not deleted): {moved}",
        superseded_candidates=moved,
    )
    print(
        f"  (moved {len(moved)} candidate group(s) of an earlier draft aside: {moved})"
    )
    return moved


def _persist_md(
    ctx: RunContext,
    construction: dict,
    survivors,
    dropped,
    gate_lines,
    ask_human: bool = True,
    questions_from: list | None = None,
    extra_lines: list[str] | None = None,
) -> list[str]:
    # a staged round's construction is the base plus the built candidates
    staged = bool(construction and construction.get("_staged"))
    _move_aside_stale_candidates(ctx, {str(c["id"]) for c, _ in survivors})
    ids = []
    supports: dict[str, dict | None] = {}
    # the floor what each candidate adds was held to: the variants' floor in a
    # discrimination round, the round's own floor in a model-space search
    held_to = _candidate_floor(ctx, search=not ask_human)
    for cand, sbml in survivors:
        cid = cand["id"]
        mdl = candidate_work(ctx, cid) / "model"
        ant = cand["antimony"]
        (mdl / "antimony").put_text(ant if ant.endswith("\n") else ant + "\n")
        (mdl / "sbml").put_text(sbml)
        (mdl / "parameters").put(cand.get("parameters", []))
        # every candidate the round fits is annotated against the dossier,
        # whoever wrote it: construction, the expansions, or the engine's own
        # enumeration of a model space
        supports[cid] = _reaction_support(ctx, sbml, cand.get("parameters", []))
        if supports[cid] is not None and held_to is not None:
            supports[cid]["floor"] = held_to
        _put_support(mdl, supports[cid])
        gl = cand.get("entity_glossary_merged")
        if gl is None:
            gl = (
                merged_glossary(construction, cand)
                if construction is not None
                else _inherited_glossary(ctx)
            )
        if gl and (gl.get("species") or gl.get("parameters")):
            (mdl / "glossary").put(gl)
        if cand.get("assembly_overlay"):
            # observation axes: applied to this candidate's copy of the shared
            # assembly at S3; recorded here so the candidate is complete
            (mdl / "assembly_overlay").put(cand["assembly_overlay"])
        ids.append(cid)
    write_records(
        ctx.round / "space/candidates",
        CandidateDecl,
        [
            {
                "id": c["id"],
                "label": c.get("label", ""),
                "rationale": c.get("rationale", ""),
                "assembly_overlay": c.get("assembly_overlay") or [],
            }
            for c, _ in survivors
        ],
    )
    # On a resumed search the construction reply is gone but its build report
    # is already in the record from the first pass — keep it rather than
    # losing the decisions and their evidence.
    br = ctx.round / "model/build_report"
    checker_lines: list[str] = []
    if construction is not None:
        decisions = _enforce_tier_evidence(
            ctx, construction["build_report"]["decisions"]
        )
        sources = construction["consulted_sources"]
        _ledger_evidence_origins(ctx, construction)
        # citations are resolved before the report is written, so the report
        # records the resolutions and any demotion
        if ctx.spec.get("verification.citation_check", True):
            checker_lines += _citation_resolution(ctx, decisions)
    else:
        prior = br.get({}) or {}
        decisions = prior.get("decisions", [])
        sources = prior.get("consulted_sources", [])
    br.put(
        {
            "decisions": decisions,
            "consulted_sources": sources,
            "dropped_candidates": dropped,
            "declared_constants": _dc.parse(construction)
            or (prior.get("declared_constants") if construction is None else []),
            "basal_state": (
                basal_state(construction)
                if construction is not None
                else prior.get("basal_state")
            ),
        }
    )
    try:  # the MD candidate gate gets its model report too (renderer, never fatal)
        from octomod.reporting import write_model_report_html

        report_path = write_model_report_html(ctx.round)
        # as a document, so the card prints a link and the payload carries the
        # absolute path
        model_report_line = []
        model_report_docs = [("model report — the model as built, M1-M5", report_path)]
    except Exception as e:
        model_report_docs = []
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"model report failed: {e}",
        )
        model_report_line = []
    # the candidate set is what this gate buys, so it travels as the menu and
    # the card's evidence budget can never cap it away
    menu = []
    for c, _ in survivors:
        menu.append(
            f"candidate {c['id']}: {c.get('label', '')} — {c.get('rationale', '')[:90]}"
        )
        if c.get("difference") is not None:
            # built from the base plus this declared difference, so the line
            # below is EVERYTHING that differs — nothing else can
            from octomod.workflow_modules.model.expansion import difference_lines

            menu.append(
                f"    differs from the base in: {'; '.join(difference_lines(c))}"
            )
    # the candidate set is audited by the independent checker
    if construction is not None and ctx.spec.get("verification.s1", True):
        checker_lines += _t3_construction_audit(
            ctx, construction, candidates=[c for c, _ in survivors]
        )
    lines = (
        model_report_line
        + [f"DROPPED {d['id']}: {d['reason'][:300]}" for d in dropped]
        + list(extra_lines or [])
        + checker_lines
        # with the base gate off, this card is where a redrafted base's diff shows
        + (
            _base_diff_lines(ctx, construction)
            if construction is not None and construction.get("antimony")
            else []
        )
        + _dc.card_lines(ctx.cache.get("_declared_constant_rows") or [])
        + _declared_space_lines(construction)
        # where each candidate's reactions come from, the inferred ones put
        # to the person beside the agent's questions
        + _rxe.set_card_lines(supports)
    )
    # the grounding lines (the floor, the searches, where each reaction comes
    # from) print whatever the card's evidence cap
    grounding = list(extra_lines or []) + _rxe.set_card_lines(supports)
    _record_declared_axes(ctx, construction)
    # the agent's `user_decision_required` questions, rendered and recorded as
    # on the single-model card; when the base gate already asked the base's
    # questions, this card asks only the expansions'
    flagged = [
        d
        for d in ((questions_from if questions_from is not None else decisions) or [])
        if d.get("user_decision_required")
    ]
    _order = {"low": 0, "medium": 1, "high": 2}
    flagged.sort(key=lambda d: _order.get(d.get("confidence", "low"), 0))
    n_esc_max = int(ctx.spec.get("s1.max_escalations", 5))
    if flagged:
        lines.append("")
        lines.append(
            "THE AGENT ASKS (genuinely ambiguous choices it will act on either way):"
        )
        for k, d in enumerate(flagged[:n_esc_max], 1):
            lines.append(f"  {k}. {d.get('question') or d['decision']}")
        if len(flagged) > n_esc_max:
            lines.append(f"  (+{len(flagged) - n_esc_max} more in {br.key})")
        lines.append(
            "  → answer in the note, e.g.:  y 1: face value; 2: leave unmodelled"
        )
    if ask_human:
        # record_decline=False: the stop message says to rerun and redraft
        approved, _scope_note = humangate.ask_once(
            ctx,
            ctx.round / "decisions/model_scope",
            f"Discriminate between these {len(ids)} candidate mechanisms? "
            f"(each will be compiled and fitted)",
            lines,
            module="model_scope",
            record_decline=False,
            always_show=menu,
            uncapped=grounding,
            intent=ctx.intent,
            consequences=(
                "every candidate is assembled, compiled and fitted (cost gate follows)",
                "run stops; rerun to redraft the candidate set",
            ),
            # the discrimination card's OWN forms — no `tier:`/`axes:`,
            # because this path never runs `_resolve_search` and a card must
            # not promise a search it does not run
            note_forms=MD_SCOPE_NOTE_FORMS_STAGED if staged else MD_SCOPE_NOTE_FORMS,
            documents=model_report_docs
            + (
                [
                    (
                        "where each reaction comes from — model report M1",
                        model_report_docs[0][1],
                    )
                ]
                if model_report_docs and any(supports.values())
                else []
            ),
        )
        if not approved:
            raise ModuleFailure("user rejected the candidate set at the S1 gate")
        if staged:
            _raise_if_staged_redraft(ctx, _scope_note)
        else:
            _raise_if_redraft_asked(ctx, _scope_note, "model_scope")
        if flagged:
            record_open_questions(
                ctx,
                flagged,
                _scope_note,
                prefix="s1var" if questions_from is not None else "s1",
            )
        _warn_search_forms_ignored_on_md(ctx, _scope_note)
        ctx.set_marker("s1", producer="agent:construction", candidates=ids)
    return ids


def _candidate_floor(ctx: RunContext, *, search: bool) -> dict | None:
    """The floor a candidate set's additions were held to, as its annotation
    records it (`reaction_support.floor`): in the model-space search of a round
    an expansion seeded, the round's floor, which the expansion's axes were
    offered at (`held_to: axes`); in a discrimination round the variants'
    floor, with the base's beside it (`held_to: variants`). None when the run
    does not build on the knowledge module, and for the axes construction
    declares, which no floor holds."""
    if not _rxe.active(ctx):
        return None
    if search:
        seeded = ctx.round_idx > 0 and (ctx.round / "model/seed").exists()
        if not seeded:
            return None
        cur = _rxe.recorded_floor(ctx)
        if cur is None:
            return None
        return {
            "band": _rxe.floor_band(cur),
            "source": cur.get("source"),
            "held_to": "axes",
        }
    vf = _rxe.variants_floor(ctx)
    return {
        "band": vf["band"],
        "base": vf["base"],
        "offset": vf["offset"],
        "held_to": "variants",
    }


def _raise_if_redraft_asked(ctx, note, module: str) -> None:
    """A `redraft:` in the gate note sends the work back to the agent.

    The gate's decision record is cleared first: the next pass must ASK again,
    otherwise the resume would read the old answer and the human would be
    asking into a decision that is already recorded.
    """
    text = _hr.parse(note)
    if text:
        _hr.send_back(
            ctx,
            module,
            "construction",
            text,
            remove=[ctx.round / "decisions/model_scope"],
        )


# What the SCOPE gate accepts in its note. Declared as data so the card, the
# file-gate payload and the parsers in `model_space.parse_axis_selection` and
# `_resolve_search` cannot drift apart.
def _scope_note_forms() -> tuple[str, ...]:
    return (
        "tier: base | top<k> | all   how many of the open axes to search "
        "(base = one model, top2 = the 2 highest-priority axes -> 3 models: "
        "the base and each axis on its own)",
        "axes: <id>, <id>            search exactly these axes, by name",
        "lattice                     search every on/off combination of them "
        "instead (2^k models; off unless asked)",
        "1: <answer>  2: <answer>    answer the engine's numbered questions",
        _hr.NOTE_FORM,
        "axes: none                  no search: the round stays single-model",
        "(nothing)                   refused when the card lists axes, and the "
        "card is asked again (axes bought at the expansion gate stay bought)",
    )


SCOPE_NOTE_FORMS = _scope_note_forms()


# What the DISCRIMINATION scope card accepts. That card buys a candidate SET,
# not axes: `tier:` and `axes:` are read by `_resolve_search`, which the
# discrimination path never calls, so the card does not offer them; the axes
# rejoin at the expansion gate.
def _md_scope_note_forms() -> tuple[str, ...]:
    return (
        "1: <answer>  2: <answer>    answer the engine's numbered questions",
        _hr.NOTE_FORM,
        "(nothing)                   approve the candidate set as listed "
        "(`tier:` / `axes:` are NOT read here — the declared axes rejoin at "
        "the expansion gate)",
    )


MD_SCOPE_NOTE_FORMS = _md_scope_note_forms()


def _md_scope_note_forms_staged() -> tuple[str, ...]:
    """A staged card says which of the two calls a redraft goes to."""
    return (
        "1: <answer>  2: <answer>    answer the engine's numbered questions",
        _hr.NOTE_FORM.replace("send it back to the agent", "send the VARIATIONS back"),
        _hr.NOTE_FORM_BASE,
        "(nothing)                   approve the candidate set as listed "
        "(`tier:` / `axes:` are NOT read here — the declared axes rejoin at "
        "the expansion gate)",
    )


MD_SCOPE_NOTE_FORMS_STAGED = _md_scope_note_forms_staged()

_SEARCH_FORM = re.compile(r"\b(tier|axes)\s*[:=]", re.I)


def _warn_search_forms_ignored_on_md(ctx: RunContext, note: str | None) -> None:
    """Say so, loudly and in the ledger, when a discrimination-round answer
    carries `tier:` or `axes:` — the human meant a search this round does not
    run."""
    if not note or not _SEARCH_FORM.search(str(note)):
        return
    msg = (
        "`tier:` / `axes:` in the answer are NOT applied on a discrimination "
        "round: this gate bought the candidate set only, no lattice is "
        "searched this round, and the declared axes come back as a question at "
        "the expansion gate after selection"
    )
    print(f"  ⚑ {msg}")
    ctx.ledger.append(
        "note",
        module="model_scope",
        round_idx=ctx.round_idx,
        note=msg,
        search_forms_ignored=True,
        answer=str(note)[:300],
    )


def _declared_constant_gates(ctx: RunContext, sbml: str, t_end: float) -> list:
    """Measure what the note says is constant, at nominal parameters.

    Advisory: a sink stays allowed and the note may be wrong, but the
    contradiction is made visible before any fitting.
    """
    from octomod.gates import GateResult, gate

    constants = _dc.parse(ctx.cache.get("_construction_reply"))
    if not constants:
        return []

    @gate("model_declared_constants", "T1")
    def g_declared():
        rows = _dc.drift(sbml, constants, t_end)
        ctx.cache["_declared_constant_rows"] = rows
        bad = _dc.offenders(rows)
        return GateResult(
            "model_declared_constants",
            "T1",
            not bad,
            blocking=False,
            detail=(
                f"{len(constants)} declared constant(s) hold at nominal"
                if not bad
                else "; ".join(
                    f"{r['expression']} drifts {r['drift']:.0%} by "
                    f"t={r['at_time']:.3g} (tolerance {r['tolerance']:.0%})"
                    for r in bad
                )
            ),
        )

    return [g_declared]


def _record_declared_axes(ctx: RunContext, construction: dict | None) -> None:
    """Write the axes the agent declared to the round's own record.

    Its own record (`space/declared`), NOT `space/axes`: that is the set the
    engine enumerates, and a discrimination round buys candidates rather than
    axes. Later rounds read it to offer the declared axes that were never
    tested.
    """
    axes = [
        a
        for a in ((construction or {}).get("model_space") or [])
        if isinstance(a, dict) and a.get("id")
    ]
    if not axes:
        return
    try:
        (ctx.round / "space/declared").put(axes)
    except Exception as e:  # a record must never end a round
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"declared-axis record failed: {e}",
        )


def _declared_space_lines(construction: dict | None) -> list[str]:
    """The axes and tier recommendation the agent declared, shown on the
    discrimination card as information: that card buys candidates, not axes,
    and nothing here changes what is fitted.
    """
    proposed = [
        a
        for a in ((construction or {}).get("model_space") or [])
        if isinstance(a, dict)
    ]
    if not proposed:
        return []
    rec = model_space.parse_recommended_tier(construction, len(proposed))
    out = [
        f"THE AGENT ALSO DECLARED {len(proposed)} STRUCTURAL AXES — shown for "
        f"information; this gate buys candidates, not axes:"
    ]
    for axis in model_space.by_priority(proposed):
        question = str(axis.get("question") or axis.get("label") or "").strip()
        out.append(f"  · {axis.get('id')}: {question[:88]}")
    who = (
        "the agent recommends"
        if rec.get("source") == "agent"
        else "the engine defaults to"
    )
    out.append(
        f"  {who} tier {rec.get('label')} ({rec.get('k')} of {len(proposed)} axes) "
        f"— for the EXPANSION gate after this round; a `tier:` note here is not acted on"
    )
    if rec.get("reasoning"):
        out.append(f"    why: {str(rec['reasoning'])[:150]}")
    out.append(
        "  (recorded in this round's build report; none is fitted this round — "
        "`tier:` / `axes:` are not read on this card; the axes rejoin at the "
        "expansion gate after selection)"
    )
    return out


# ------------------------------------------------------------ shared helpers


def _run_ladder(ctx: RunContext, antimony_src: str, parameters: list, t_end: float):
    holder: dict = {}
    gates = make_build_gates(antimony_src, holder)
    ok, results = run_gate_set(
        gates, ctx.gates, ctx.ledger, "model", round_idx=ctx.round_idx
    )
    if ok:
        est_bounds = {
            p["id"]: (float(p["lb"]), float(p["ub"]))
            for p in parameters
            if p.get("estimate") and p.get("lb") is not None
            # an observation axis's parameter is not in the model, and the box
            # gate sets every id it is given on the simulator
            and p.get("layer") != "assembly"
        }
        from octomod.gates.build_gates import make_parameter_use_gates

        # cheapest first: a parameter nobody reads is found without simulating
        sim_gates = make_parameter_use_gates(holder["sbml"], parameters)
        # the glossary lets the required-entity check match a renamed entity:
        # the unit of work's own (a candidate's), else the round's
        _glossary = None
        for g in (ctx.model / "glossary", ctx.round / "model/glossary"):
            try:
                _glossary = g.get(None)
            except Exception:
                _glossary = None
            if _glossary is not None:
                break
        sim_gates += make_sim_gates(
            holder["sbml"],
            t_end,
            est_bounds,
            ctx.spec,
            required_entities=ctx.intent.get("required_entities"),
            glossary=_glossary if isinstance(_glossary, dict) else None,
        )
        sim_gates += _declared_constant_gates(ctx, holder["sbml"], t_end)
        ok2, results2 = run_gate_set(
            sim_gates, ctx.gates, ctx.ledger, "model", round_idx=ctx.round_idx
        )
        results = results + results2
        ok = ok and ok2
    if ok:
        ctx.cache["_s1_sbml"] = holder["sbml"]
    return ok, results


def _enforce_tier_evidence(ctx: RunContext, decisions: list) -> list:
    """A decision claiming 'direct' or 'transferred' evidence without a source
    that points somewhere IS a 'default' claim, whatever the agent says: demote
    and mark it."""
    demoted = 0
    for d in decisions:
        tier = d.get("evidence_tier")
        if tier in ("direct", "transferred"):
            ev = d.get("evidence") or []
            has_source = any(
                evidence_points_somewhere(e) for e in ev if isinstance(e, dict)
            )
            if not has_source:
                d["evidence_tier"] = "default"
                d["tier_demoted_from"] = tier
                demoted += 1
    if demoted:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"{demoted} decision(s) demoted to evidence_tier="
            f"default: tier claimed without a source",
        )
    return decisions


# ------------------------------------------------ the entity glossary


def _species_ids(sbml: str) -> list[str]:
    import libsbml

    m = libsbml.readSBMLFromString(sbml).getModel()
    return [m.getSpecies(i).getId() for i in range(m.getNumSpecies())]


def merged_glossary(
    construction: dict | None,
    candidate: dict | None = None,
    axes_on: list[dict] | None = None,
) -> dict:
    """The glossary the assembly agents will read: the top-level one, with a
    candidate's own entries overriding by id, plus a `denotes` line for every
    parameter an ON axis adds."""
    out = {"species": [], "parameters": []}
    by_id: dict[str, dict] = {}
    for src in (
        (construction or {}).get("entity_glossary"),
        (candidate or {}).get("entity_glossary"),
    ):
        if not isinstance(src, dict):
            continue
        for kind in ("species", "parameters"):
            for e in src.get(kind) or []:
                if isinstance(e, dict) and e.get("id"):
                    by_id[(kind, str(e["id"]))] = dict(e)
    for a in axes_on or []:
        for p in a.get("adds_parameters") or []:
            if p.get("id") and p.get("denotes"):
                by_id.setdefault(
                    ("parameters", str(p["id"])),
                    {
                        "id": str(p["id"]),
                        "role": str(p["denotes"]),
                        "convention": str(p.get("unit", "")) or "see the axis",
                        "from_axis": a.get("id"),
                    },
                )
    for (kind, _), e in by_id.items():
        out[kind].append(e)
    return out


def glossary_problems(
    construction: dict,
    sbml: str,
    candidate: dict | None = None,
    check_stray: bool = True,
) -> list[str]:
    """T0 COVERAGE rule: every species of this model must resolve in the
    glossary it will be read with — the top-level one, overridden by the
    candidate's own entries. Candidates do not need a glossary of their own;
    a shared glossary that covers them is enough.

    `check_stray` covers the other direction: an entry naming an id this model
    does not have. For a single model that is a typo. For a candidate SET the
    question belongs to the set rather than to one member — an entry for a
    species only one candidate carries is legal — so the set path passes
    `check_stray=False` here and `glossary_set_problems` runs the check once
    against the union of the set's species.
    """
    gl = merged_glossary(construction, candidate)
    species = _species_ids(sbml)
    have = {str(e.get("id")): e for e in gl["species"]}
    where = f"candidate {candidate.get('id')}: " if candidate else ""
    problems = []
    missing = [sp for sp in species if sp not in have]
    if missing:
        problems.append(
            f"{where}species without a glossary entry: {missing} "
            f"(every species must resolve in the top-level glossary or "
            f"in this candidate's own)"
        )
    for sid in species:
        e = have.get(sid)
        if e is not None and not str(e.get("denotes", "")).strip():
            problems.append(f"{where}glossary entry {sid!r} has no 'denotes' text")
    if check_stray:
        stray = [sid for sid in have if sid not in species]
        if stray:
            problems.append(f"{where}glossary names species the model lacks: {stray}")
    if not isinstance(construction.get("entity_glossary"), dict) and not (
        candidate and isinstance(candidate.get("entity_glossary"), dict)
    ):
        problems.append(f"{where}entity_glossary missing or not an object")
    return problems


def glossary_set_problems(construction: dict, survivors: list) -> list[str]:
    """The coverage rule over a candidate SET: coverage per candidate, plus ONE
    stray-entry check against the union of species over every candidate and the
    base model. An entry for a species only one candidate carries is legal; an
    entry matching no model in the set is a typo and is named.

    `survivors` is the [(candidate_dict, sbml)] list the ladder produced.
    """
    from octomod.gates.build_gates import antimony_to_sbml

    union: set[str] = set()
    for _cand, sbml in survivors:
        union |= set(_species_ids(sbml))
    base_ant = str(construction.get("antimony") or "")
    if base_ant.strip():
        base_sbml, _err = antimony_to_sbml(base_ant)
        if base_sbml:
            union |= set(_species_ids(base_sbml))

    problems: list[str] = []
    for cand, sbml in survivors:
        problems += glossary_problems(
            construction, sbml, candidate=cand, check_stray=False
        )
    entry_ids: set[str] = set()
    for src in [construction.get("entity_glossary")] + [
        cand.get("entity_glossary") for cand, _ in survivors
    ]:
        if isinstance(src, dict):
            entry_ids |= {
                str(e.get("id"))
                for e in (src.get("species") or [])
                if isinstance(e, dict) and e.get("id")
            }
    stray = sorted(sid for sid in entry_ids if sid not in union)
    if stray:
        problems.append(
            f"glossary names species no model in this candidate set has: {stray} "
            f"(the set covers {sorted(union)}) — a typo, or an entry left behind "
            f"from a model that changed"
        )
    return problems


def _glossary_gate(ctx: RunContext, problems: list[str]) -> bool:
    from octomod.gates import GateResult, run_gate_set

    res = GateResult(
        "model_glossary_complete",
        "T0",
        not problems,
        value=len(problems),
        detail=(
            " | ".join(problems)[:600]
            if problems
            else "every species carries a glossary entry that says " "what it denotes"
        ),
    )
    ok, _ = run_gate_set(
        [lambda r=res: r],
        ctx.gates,
        ctx.ledger,
        "model",
        round_idx=ctx.round_idx,
    )
    return ok


def basal_state(construction: dict | None) -> dict | None:
    """The construction reply's optional `basal_state`, as S3 hands it on.

    A dict keeps its three fields, a bare string is its note; anything else,
    or nothing, is None, so a reply without the field routes nothing."""
    raw = (construction or {}).get("basal_state")
    if isinstance(raw, str) and raw.strip():
        return {"note": raw.strip()[:600]}
    if not isinstance(raw, dict) or not raw:
        return None
    out = {
        k: raw[k]
        for k in ("initial_values_are_steady_state", "suggest_preequilibration")
        if isinstance(raw.get(k), bool)
    }
    if str(raw.get("note") or "").strip():
        out["note"] = str(raw["note"]).strip()[:600]
    return out or None


def _persist_single(ctx: RunContext, model: Node, construction: dict) -> None:
    ant = construction["antimony"]
    (model / "antimony").put_text(ant if ant.endswith("\n") else ant + "\n")
    (model / "sbml").put_text(ctx.cache.pop("_s1_sbml"))
    (model / "parameters").put(construction["parameters"])
    (model / "network").put(construction["network"])
    (model / "glossary").put(merged_glossary(construction))
    (model / "build_report").put(
        {
            "decisions": _enforce_tier_evidence(
                ctx, construction["build_report"]["decisions"]
            ),
            "consulted_sources": construction["consulted_sources"],
            # persisted so the fit can be measured against the same
            # declaration, without going back to the agent's reply
            "declared_constants": _dc.parse(construction),
            # read by S3 for the condition-encoding agent
            "basal_state": basal_state(construction),
        }
    )
    _ledger_evidence_origins(ctx, construction)


def _citation_resolution(ctx: RunContext, decisions: list) -> list[str]:
    """Deterministic hallucination trap: every evidence source
    that CAN be resolved is looked up. Unresolvable sources demote their
    decision's tier; network trouble is recorded as unchecked, never punished
    as fabrication."""
    from octomod.connectors.web_cache import resolve_source

    n_demoted = 0
    for d in decisions:
        evs = [e for e in (d.get("evidence") or []) if isinstance(e, dict)]
        any_resolved = False
        any_unresolvable = False
        for e in evs:
            status = resolve_source(str(e.get("source", "")))
            e["resolution"] = status
            any_resolved |= status == "resolved"
            any_unresolvable |= status == "unresolvable"
        if (
            any_unresolvable
            and not any_resolved
            and d.get("evidence_tier") in ("direct", "transferred")
        ):
            d["tier_demoted_from"] = d.get("evidence_tier")
            d["evidence_tier"] = "default"
            n_demoted += 1
    findings = _citation_findings(decisions)
    if findings:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"citation resolution: {len(findings)} finding(s), "
            f"{n_demoted} demotion(s)",
        )
    return findings


def _citation_findings(decisions: list) -> list[str]:
    """The scope card's citation lines, read from decisions that citation
    resolution has already annotated (`resolution` on each evidence entry,
    `tier_demoted_from` on a demoted decision) — the drafting pass and a
    resume that reads `model/build_report` back print the same lines, and the
    resume resolves nothing. A decision is demoted by resolution only where
    no source resolved and one could not be: a sourceless demotion never has
    an unresolvable source, since such a source already points somewhere."""
    findings = []
    for d in decisions or []:
        if not isinstance(d, dict):
            continue
        status = [
            e.get("resolution")
            for e in (d.get("evidence") or [])
            if isinstance(e, dict)
        ]
        if "unresolvable" not in status:
            continue
        if "resolved" not in status and d.get("tier_demoted_from") in (
            "direct",
            "transferred",
        ):
            findings.append(
                f"UNRESOLVABLE source(s) on: {str(d.get('decision'))[:70]} "
                f"(tier demoted)"
            )
        else:
            findings.append(
                f"unresolvable source among evidence for: "
                f"{str(d.get('decision'))[:70]}"
            )
    return findings


def _audit_lines(concerns: list) -> list[str]:
    """The scope card's lines for the construction audit's concerns (none is
    a line too: the audit ran and found nothing)."""
    return [
        f"checker[{v.get('aspect')}]: CONCERN — {str(v.get('note'))[:110]}"
        for v in concerns or []
        if isinstance(v, dict)
    ] or ["independent construction audit: no concerns"]


def _redraft_lines(history, dossier: Node) -> list[str]:
    """The scope card's line for the drafts that failed their gates before
    the one it shows, from the construction dossier (`dossier` is its record
    node, named on the line)."""
    if not history.attempts:
        return []
    last = history.attempts[-1].get("what_changed_vs_previous")
    return [
        f"redrafts: {len(history.attempts)} earlier attempt(s) failed "
        f"their gates (dossier: {dossier.key})"
        + (
            f"; last collateral-change ratio {last['collateral_change_ratio']}"
            if last
            else ""
        )
    ]


def _recorded_checker_lines(ctx: RunContext, model: Node) -> list[str]:
    """The citation, audit and redraft lines the drafting pass put on the scope
    card, for a resume that finds the agent's model in the record and no
    reply in hand. Read from what that pass recorded — the resolutions written
    into `model/build_report`, the audit's `gates/model_verification`, the
    construction dossier — so nothing is resolved or audited again. Empty for
    a model the construction agent did not write in this round (a supplied or
    seeded one had no audit)."""
    from octomod.orchestration.interaction import retry as _retry

    if not (ctx.agent_calls.child("construction") / "reply").exists():
        return []
    lines: list[str] = []
    if ctx.spec.get("verification.citation_check", True):
        report = (model / "build_report").get({}) or {}
        lines += _citation_findings(report.get("decisions") or [])
    audit = ctx.gates.child("model_verification")
    if ctx.spec.get("verification.s1", True) and audit.exists():
        record = audit.get({}) or {}
        lines += _audit_lines(record.get("advisory_findings") or [])
    dossier = _retry.dossier_of(ctx, "construction")
    lines += _redraft_lines(_retry.AttemptHistory(dossier), dossier)
    return lines


def _audit_fact_context(ctx: RunContext, construction: dict) -> dict:
    """What the construction audit is shown of the knowledge module when the
    run builds on it: `known_facts` (the facts routed to construction) and
    `cited_parameters` (each parameter whose `source` cites one, so the audit
    can judge how the fact was applied); {} otherwise."""
    if not _rxe.active(ctx):
        return {}
    from octomod.workflow_modules.knowledge import engine as _kn

    facts = _kn.facts_for(_rxe.dossier_of(ctx), "construction")
    if not facts:
        return {}
    cited = [
        {
            k: p.get(k)
            for k in ("id", "nominal_value", "unit", "source")
            if p.get(k) is not None
        }
        for p in construction.get("parameters") or []
        if isinstance(p, dict) and _rxe.FACT_CITATION.search(str(p.get("source") or ""))
    ]
    return {"known_facts": facts, **({"cited_parameters": cited} if cited else {})}


def _t3_construction_audit(
    ctx: RunContext, construction: dict, candidates: list | None = None
) -> list[str]:
    """Independent checker over the construction record (fresh context,
    artifacts only). Advisory: its concerns go IN FRONT OF the human at the
    scope gate; it never blocks alone.

    `candidates`: a discrimination round's set is audited too. That audit runs
    on every resume that reaches the scope card, so it goes through
    `call_cached`: the same candidate set is audited once."""
    from octomod.agents import AgentCallError
    from octomod.gates import GateResult, run_gate_set

    context = {
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        "build_report": construction["build_report"],
        "network": construction["network"],
        "antimony": construction["antimony"],
        **_audit_fact_context(ctx, construction),
    }
    if candidates is not None:
        context["candidates"] = [
            (
                {k: c.get(k) for k in ("id", "label", "rationale", "difference")}
                if c.get("difference") is not None
                else {
                    k: c.get(k)
                    for k in ("id", "label", "rationale", "antimony", "parameters")
                }
            )
            for c in candidates
        ]
    try:
        verdict = (
            ctx.call_cached("construction_verification", context)
            if candidates is not None
            else ctx.call("construction_verification", context)
        )
    except AgentCallError as e:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"s1 verification skipped: {e}",
        )
        # an earlier draft's audit is not this draft's: a resumed card reads
        # the record back, and must not show a verdict on another model
        ctx.gates.child("model_verification").delete()
        return []
    concerns = [v for v in verdict["verdicts"] if not v.get("ok")]
    res = GateResult(
        "model_verification",
        "T3",
        True,
        blocking=False,
        value=verdict["overall"],
        detail="; ".join(f"{v['aspect']}: {v['note']}" for v in concerns)
        or "construction audit raised no concerns",
        advisory_findings=concerns,
    )
    run_gate_set(
        [lambda r=res: r],
        ctx.gates,
        ctx.ledger,
        "model",
        round_idx=ctx.round_idx,
    )
    return _audit_lines(concerns)


def _scope_gate(
    ctx: RunContext,
    results,
    construction: dict | None,
    checker_lines: list[str] | None = None,
) -> None:
    from octomod.reporting.render import model_mermaid, model_terminal_lines

    model = ctx.round / "model"
    sbml = (model / "sbml").text()
    (model / "mermaid").put_text(model_mermaid(sbml) + "\n")

    # the document the user reads to answer THIS gate: what was built, where
    # the build needed a judgement call, what the ladder already proved
    from octomod.reporting import write_model_report_html

    report_path = None
    try:
        report_path = write_model_report_html(ctx.round)
    except Exception as e:  # rendering a report must never kill a run
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"model report failed: {e}",
        )

    parameters = (construction or {}).get("parameters") or _load_supplied_parameters(
        model
    )
    lines = model_terminal_lines(sbml, parameters)
    menu: list[str] = []  # the axis choices; exempt from the card's cap
    # what the note says is constant, and what this model does with it
    lines += _dc.card_lines(ctx.cache.get("_declared_constant_rows") or [])
    lines.append(
        f"  (source: {(model / 'antimony').key} · "
        f"reasoning: {(model / 'build_report').key})"
    )

    n_esc_max = int(ctx.spec.get("s1.max_escalations", 5))
    axes = []
    if ctx.spec.get("search.enabled", True):
        axes, construction = model_space.axes_for_gate(ctx, construction)
        if axes:
            # the whole pre-compile ladder on every combination of the declared
            # space BEFORE the human prices it: an axis whose every combination
            # dies is dropped here, named, not bought and then lost
            base_par = (construction or {}).get("parameters") or parameters
            base_ant_text = (construction or {}).get("antimony") or (
                model / "antimony"
            ).text()
            n_models_cap = int(ctx.spec.get("search.max_models", 8))
            mode = model_space.search_mode(ctx)
            capped, _ = model_space.cap_axes(
                model_space.by_priority(axes), n_models_cap, mode=mode
            )
            viable, dropped_b, _n_viable, _failing = model_space.pregate_ladder(
                ctx,
                base_ant_text,
                base_par,
                capped,
                n_models_cap,
                float(ctx.testcase.get("t_end", 100.0)),
                module="model",
                mode=mode,
            )
            if dropped_b:
                keep_ids = {a["id"] for a in viable} | {
                    a["id"] for a in axes if a not in capped
                }
                axes = [a for a in axes if a["id"] in keep_ids]
                write_records(model_space.space_path(ctx), AxisRecord, axes)
                for d in dropped_b:
                    lines.append(
                        f"  · axis {d['id']} DROPPED before the gate: {d['reason'][:150]}"
                    )
            # the agent prices its own confidence: tiers with their model
            # counts, the recommendation never presented as "all"
            bought = axes_already_bought(ctx)
            recommended = model_space.parse_recommended_tier(
                construction, len(axes), already_bought=bought
            )
            rec_node = ctx.round / "space/recommended_tier"
            if construction is None:  # resumed: the recommendation is recorded
                recommended = rec_node.get(recommended)
            else:
                rec_node.put(recommended)
            # The axis menu is what the human CHOOSES from, so it is passed as
            # always_show and never counts against the card's evidence cap.
            menu.append(
                "OPEN STRUCTURAL AXES"
            )  # the marker tests and the front end key on
            menu += model_space.tier_card_lines(
                axes,
                int(ctx.spec.get("search.max_models", 8)),
                recommended,
                mode=model_space.search_mode(ctx),
            )
            # On an expansion-seeded round the axis question was answered one
            # gate ago, so the closing sentence below follows what was bought.
            from octomod.workflow_modules.model import tried_models as _tried

            # what earlier runs on this case already found out about these
            # axes. Evidence on the card, never a filter — a "tried" verdict is
            # context-dependent (which space, which base, which data).
            lines += _tried.resemblance_lines(axes, _tried.snapshot_if_enabled(ctx))
            crit = ctx.spec.get("search.criterion", "AIC")
            menu.append(
                f"  (selection by {crit}; these axes were already bought at "
                f"the expansion gate — naming a tier or axes here CHANGES that "
                f"set, and naming none would un-buy the round)"
                if bought
                else f"  (selection by {crit}; name a tier or axes to search "
                f"them; the round stays single-model on `axes: none`, and an "
                f"answer that names neither is refused)"
            )
    # an axis construction declared that the engine could not apply is on the
    # card that approves the space, by author and reason — after the axes are
    # recorded, so the card shows THIS draft's drops
    dropped_lines = model_space_dropped_lines(ctx)
    lines += dropped_lines
    # the grounding lines print whatever the card's evidence cap: what each
    # declared axis adds at the variants' floor and the axes it refused; where
    # each reaction comes from, the inferred ones put to the person here beside
    # construction's own questions; the essential set the base was built from,
    # the searches and the floor
    refused = [x for x in dropped_lines if x.lstrip().startswith("⚑ REFUSED")]
    grounding = (
        _rxe.axis_card_lines((ctx.round / _rxe.S1_AXIS_SUPPORT_KEY).get(None))
        + _reaction_card_lines(model)
        + _knowledge_card_lines(ctx, construction, (model / _rxe.SUPPORT_KEY).get(None))
    )
    lines += grounding

    flagged = _scope_questions(ctx, construction)
    if flagged:
        lines.append("")
        lines.append(
            "THE AGENT ASKS (genuinely ambiguous choices it will act on either way):"
        )
        for k, d in enumerate(flagged[:n_esc_max], 1):
            lines.append(f"  {k}. {d.get('question') or d['decision']}")
        if len(flagged) > n_esc_max:
            lines.append(
                f"  (+{len(flagged) - n_esc_max} more in "
                f"{(model / 'build_report').key})"
            )
        lines.append(
            "  → answer in the note, e.g.:  y 1: assume linear; 2: keep lumped"
        )

    for line in checker_lines or []:
        lines.append(line)
    n_ok = sum(1 for r in results if r.passed)
    flags = [r for r in results if r.passed and not r.blocking and r.advisory_findings]
    lines.append("")
    lines.append(
        f"deterministic checks: {n_ok}/{len(results)} passed "
        f"(details above; evidence in {ctx.gates.key})"
    )
    for r in flags:
        lines.append(f"  ⚑ {r.detail}")

    # record_decline=False: rejecting scope stops the run before anything is
    # spent, and re-answering retries cleanly; an approval whose note is then
    # refused is cleared by the refusal for the same reason
    approved, scope_note = humangate.ask_once(
        ctx,
        ctx.round / "decisions/model_scope",
        "Is this the right model scope to spend compute on?",
        lines,
        module="model_scope",
        record_decline=False,
        always_show=menu,
        uncapped=refused + grounding,
        intent=ctx.intent,
        where="S1 scope — the network is cheap to redo now, expensive to "
        "regret after calibration",
        consequences=(
            "proceed to data semantics + problem assembly (cheap, redoable)",
            "run stops; rerun to redraft construction — put guidance in the note",
        ),
        note_forms=SCOPE_NOTE_FORMS,
        # the documents this card is about, as openable links: the rendered
        # report is a real file; the diagram and the decision record are
        # record content, carried as `<record>::<key>` references
        documents=[
            (label, doc)
            for label, doc in (
                ("model report — the model as built, M1-M5", report_path),
                ("the model diagram", model / "mermaid"),
                ("who decided what, and why", ctx.round / "decisions_md"),
            )
            if doc is not None and doc.exists()
        ]
        + _reaction_document(model, report_path),
    )
    if not approved:
        raise ModuleFailure("user rejected the model scope at the S1 gate")
    # `redraft:` is honoured before anything is recorded from the note, which
    # `_resolve_search` would otherwise read as "no axes named"
    _raise_if_redraft_asked(ctx, scope_note, "model_scope")
    _report_scope_reading(ctx, scope_note, axes)
    # the search is read in the mode this note asks for, and a refused note
    # takes its `lattice` with it: the next answer is read in the mode the
    # round had before, never as a lattice nobody asked for on that answer
    mode_node = model_space.search_mode_node(ctx.round)
    mode_before = mode_node.get(None)
    if axes and model_space.lattice_requested(scope_note):
        model_space.record_search_mode(
            ctx.round,
            model_space.LATTICE,
            "the human's `lattice` at the scope gate",
        )
    try:
        cand_ids = _resolve_search(ctx, axes, scope_note, construction, model)
    except NoteRefused:
        if mode_before is None:
            mode_node.delete()
        else:
            mode_node.put(mode_before)
        raise
    # recorded only from a note the gate took: the first answer recorded for a
    # question is the one kept, so a refused note's answers would outlive it
    if flagged is not None:
        record_open_questions(ctx, flagged, scope_note)
    return cand_ids


def _scope_questions(ctx: RunContext, construction: dict | None) -> list | None:
    """The construction agent's `user_decision_required` decisions, least
    confident first, as the scope card numbers them; None when the round's
    model has no construction reply (a supplied or seeded model asks nothing).

    In file-gate mode every scope answer arrives on a resume, which finds the
    agent's model in the record (`_run_single`) and no reply in hand. The
    questions are then read from `model/build_report`, which the drafting pass
    wrote with that model from the same reply, so the resumed card numbers
    them as the first one did and the note's `1: …` answers the same question.
    """
    if construction is not None:
        decisions = (construction.get("build_report") or {}).get("decisions") or []
    elif (ctx.agent_calls.child("construction") / "reply").exists():
        report = (ctx.round / "model/build_report").get({})
        decisions = (report or {}).get("decisions") or []
    else:
        return None
    flagged = [
        d for d in decisions if isinstance(d, dict) and d.get("user_decision_required")
    ]
    order = {"low": 0, "medium": 1, "high": 2}
    flagged.sort(key=lambda d: order.get(d.get("confidence", "low"), 0))
    return flagged


def _report_scope_reading(ctx: RunContext, note: str | None, axes: list) -> None:
    """What the scope gate takes from its note, said at once (`gate_note`)."""
    r = gate_note.Reading()
    text = _hr.parse(note)
    if text:
        r.read["redraft"] = text
    if axes:
        keep = model_space.parse_axis_selection(note or "", axes)
        if keep is not None:
            r.read["axes"] = (
                ", ".join(sorted(keep)) or "none (the round stays single-model)"
            )
        ids = [str(a.get("id")) for a in axes]
        r.unread.update(_unknown_axis_tokens(ctx, note, ids))
        r.unread.update(gate_note.unread_in_prose(note, ids, keep or set()))
    if axes and model_space.lattice_requested(note):
        r.read["lattice"] = True
    numbered = re.findall(r"(?<![\w.])(\d+)\s*:", note or "")
    if numbered:
        r.read["answers to questions"] = ", ".join(numbered)
    gate_note.report(
        r, note, ledger=ctx.ledger, module="model_scope", round_idx=ctx.round_idx
    )


# the words `model_space.parse_axis_selection` reads as "every axis" / "none"
_COLLECTIVE_AXIS_WORDS = frozenset(
    {"all", "*", "everything", "none", "-", "no", "nothing"}
)


def _unknown_axis_tokens(ctx: RunContext, note: str | None, ids: list[str]) -> dict:
    """{"axes: <token>": why} for each `axes:` value that names no axis, so a
    mistyped id is said back rather than dropped in silence.

    A token naming an axis declared earlier in the run is not unknown: the
    scope gate buys it back (`model_space.human_added_axes`). A collective
    word first decides the whole selection, and the words after it are prose.
    """
    tokens = gate_note.key_list(note, "axes", "axis")
    if not tokens or tokens[0].lower() in _COLLECTIVE_AXIS_WORDS:
        return {}
    from octomod.workflow_modules.model import tried_models as _tried

    known = {i.lower() for i in ids}
    unknown = [
        t
        for t in dict.fromkeys(tokens)
        if t.lower() not in known and t.lower() not in _COLLECTIVE_AXIS_WORDS
    ]
    if unknown:
        earlier = {k.lower() for k in _tried.declared_axis_dicts(ctx.root)}
        unknown = [t for t in unknown if t.lower() not in earlier]
    why = f"not an axis of this round (the axes are: {', '.join(ids)})"
    return {f"axes: {t}": why for t in unknown}


# `source` values that name a CATEGORY rather than a place to look. On their
# own they are not evidence; paired with a locator they are.
_GENERIC_SOURCE = frozenset(
    {"", "none", "n/a", "general knowledge", "general_knowledge", "assumed"}
)

# These categories are only a claim until the locator says where.
_LOCATOR_REQUIRED = frozenset({"lab_note", "literature", "lab note"})

# A locator that says nothing. The agent fills these in when it has no pointer,
# so treating them as one would make the rule unable to demote anything.
_EMPTY_LOCATOR = frozenset({"", "n/a", "na", "none", "-", "—", "unknown", "tbd"})


def _has_locator(entry: dict) -> bool:
    return str(entry.get("locator", "")).strip().lower() not in _EMPTY_LOCATOR


def evidence_points_somewhere(entry: dict) -> bool:
    """Does one evidence entry point at something a human could go and check?

    Judged on the (source, locator) PAIR: an entry whose `source` is only a
    category still points somewhere when its `locator` does.
    """
    source = str(entry.get("source", "")).strip().lower()
    if source in _LOCATOR_REQUIRED:
        return _has_locator(entry)
    if source and source not in _GENERIC_SOURCE:
        return True
    # a category plus a real locator is still a pointer: the locator is what
    # the human follows, and it sits next to the claim on the model report
    return _has_locator(entry)


def axes_already_bought(ctx: RunContext) -> bool:
    """True when this round's axes were purchased at the previous round's
    `revision` gate. The scope gate must not then treat silence as a
    refusal: the axis question was answered one gate ago, and answering it
    again with 'none' would un-buy a round the human approved and leave the
    expansion with no candidate set."""
    if ctx.round_idx == 0:
        return False
    prev = _tree.round_node(ctx.root, ctx.round_idx - 1) / "expansion"
    try:
        decided = prev.get(None)
    except Exception:
        return False
    if decided is None:
        return False
    return (
        bool(decided.get("expanded"))
        and int(decided.get("next_round", -1)) == ctx.round_idx
    )


def _resolve_search(
    ctx: RunContext,
    axes: list,
    scope_note: str,
    construction,
    model: Node | None = None,
) -> list[str] | None:
    """Turn the human's axis selection into a candidate set, or None.

    Returning candidates makes this round a SEARCH: the engine fits every
    on/off combination and a criterion selects. Returning None keeps the round
    single-model. The human's answer at the scope gate is
    the only thing that decides which — the agent proposes the axes, it does
    not get to choose how much compute to spend on itself. A note that decides
    neither is refused (NoteRefused), in every delivery mode.
    """
    if not axes:
        return None

    # The base model may come from the construction reply (first pass) or from
    # the record (resumed after a gate pause). Either way the search needs the
    # same two things, so read them from whichever source exists.
    if construction is not None:
        base_ant = construction["antimony"]
        base_par = construction["parameters"]
    elif model is not None and (model / "antimony").exists():
        base_ant = (model / "antimony").text()
        base_par = (model / "parameters").get([])
    else:
        return None

    # a human may buy back an axis declared earlier in the run (dropped at a
    # ceiling, or never bought) by naming it in `axes:` — validated here like
    # any carried axis, then part of this round's list
    from octomod.workflow_modules.model import tried_models as _tried

    extra = model_space.human_added_axes(
        scope_note, axes, _tried.declared_axis_dicts(ctx.root)
    )
    if extra:
        accepted = []
        for a in extra:
            if a.get("on_antimony_patch"):
                missing = model_space.undeclared_symbols(base_ant, a)
                missing = [m for m in missing if m not in {p["id"] for p in base_par}]
                _, applies = model_space.apply_patch(base_ant, a["on_antimony_patch"])
                if missing or not applies:
                    ctx.ledger.append(
                        "note",
                        module="model",
                        round_idx=ctx.round_idx,
                        note=f"human named declared axis {a['id']!r}, not added: "
                        + (
                            f"its patch uses undeclared symbol(s) {missing}"
                            if missing
                            else "its patch does not apply to this base model"
                        ),
                    )
                    continue
            accepted.append(a)
        if accepted:
            axes = list(axes) + accepted
            write_records(model_space.space_path(ctx), AxisRecord, axes)
            ctx.ledger.append(
                "note",
                module="model",
                round_idx=ctx.round_idx,
                note=f"human added declared axis/axes {[a['id'] for a in accepted]} "
                f"to this round's search at the scope gate",
                human_added_axes=[a["id"] for a in accepted],
            )
            print(
                f"  human added declared axis/axes {[a['id'] for a in accepted]} to the search"
            )
    keep = model_space.parse_axis_selection(scope_note, axes)
    if keep is None and axes_already_bought(ctx):
        # the purchase happened at the expansion gate; silence here honours it
        keep = {a["id"] for a in axes}
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"scope note named no axes, but these were bought at "
            f"the previous round's expansion gate — searching all "
            f"{len(keep)} of them",
        )
    if keep is None:
        # No axis instruction is NOT the same as "the human said none": a bare
        # answer on a card that lists axes is an oversight, so it is refused
        # however the answer arrived (terminal, front end, --auto-approve, a
        # policy), and `axes: none` is how a round is kept single-model. The
        # answer is already recorded: a refusal clears it, or every resume
        # would replay it into this same refusal.
        (ctx.round / "decisions/model_scope").delete()
        raise NoteRefused(
            "a model space is declared for this round but the scope note "
            "selected no axes. That answer is cleared, so the scope gate asks "
            "again on resume: answer with 'axes: all', 'axes: none', or the "
            "axis ids.",
            gate="model_scope",
        )
    max_models = int(ctx.spec.get("search.max_models", 8))
    live_all = [a for a in axes if a["id"] in keep]
    # an axis the base already carries is not searched: its lattice half would
    # duplicate the other half exactly
    from octomod.workflow_modules.model import supermodel as _sm

    noop = _sm.noop_axes(base_ant, live_all)
    if noop:
        noop_ids = {n["id"] for n in noop}
        live_all = [a for a in live_all if a["id"] not in noop_ids]
        for n in noop:
            ctx.ledger.append(
                "note",
                module="model",
                round_idx=ctx.round_idx,
                note=f"axis {n['id']!r} not searched on this base: {n['why']}",
                noop_axis=n["id"],
            )
        print(
            f"  not searched on this base (already carried by it): "
            f"{sorted(noop_ids)} — the search is "
            f"{model_space.n_models(len(live_all), model_space.search_mode(ctx))} "
            f"model(s), not "
            f"{model_space.n_models(len(live_all) + len(noop_ids), model_space.search_mode(ctx))}"
        )
    # the hard ceiling, enforced deterministically BEFORE enumeration so the
    # lattice is complete for the axes that are searched, kept by the agent's
    # priority
    mode = model_space.search_mode(ctx)
    live, over_cap = model_space.cap_axes(live_all, max_models, mode=mode)
    if over_cap:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"ceiling search.max_models={max_models} admits "
            f"{len(live)} axes; dropped by priority order: "
            f"{[a['id'] for a in over_cap]}",
        )
        print(
            f"  ceiling: {len(live_all)} axes selected, {max_models} models allowed "
            f"-> searching the top {len(live)} by priority; "
            f"{[a['id'] for a in over_cap]} not searched this round"
        )
    keep = {a["id"] for a in live}
    if not live and axes_already_bought(ctx):
        # `_scope_gate` recorded this answer before it was read: a refusal
        # clears it, or every resume would replay it into this same error. It
        # comes before the selection is recorded, so the ledger never says
        # the axes were frozen by an answer the run then refused.
        (ctx.round / "decisions/model_scope").delete()
        raise NoteRefused(
            "the scope note selected NO axes on a round whose axes were "
            "already bought at the expansion gate — that contradicts the "
            "purchase and leaves the round with nothing to fit. That answer "
            "is cleared, so the scope gate asks again on resume: answer "
            "'tier: all' (or name the axes you do want), or 'n' to stop "
            "the run.",
            gate="model_scope",
        )
    model_space.freeze_axes(ctx, keep)
    ctx.ledger.append(
        "tier_decision",
        module="model",
        round_idx=ctx.round_idx,
        tier=gate_note.tier(scope_note) or ("axes" if keep else "base"),
        axes_selected=sorted(keep),
        n_models=model_space.n_models(len(live), mode),
        search_mode=mode,
        recommended=(ctx.round / "space/recommended_tier").get(None),
        dropped_by_ceiling=[a["id"] for a in over_cap],
    )
    if not live:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note="tier: base — the round stays single-model by the "
            "human's choice; the axes remain on record",
        )
        return None
    t_end = float(ctx.testcase.get("t_end", 100.0))
    # in a round seeded from a fitted candidate the all-off member is that
    # candidate's model as it is, so its fit is found rather than redone
    from octomod.orchestration import round_seed as _seed

    seeded_from = (_seed.seeded(ctx.round) or {}).get("seeded_from") or {}
    enumerated = model_space.enumerate_with_encoding(
        base_ant,
        base_par,
        live,
        max_models,
        t_end=t_end,
        keep_base=bool(seeded_from.get("candidate")),
        one_at_a_time=(mode == model_space.CANDIDATES),
    )
    print(f"  model-space search: {model_space.search_mode_line(len(live), mode)}")
    models, encoding = enumerated["models"], enumerated["encoding"]
    _record_encoding(ctx, encoding)
    if len(models) < 2:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"model-space search abandoned: {len(live)} axis/axes "
            f"selected but only {len(models)} model(s) could be "
            f"built — every patch failed to apply",
        )
        return None
    by_axis = {a["id"]: a for a in live}
    base_gl = (
        merged_glossary(construction)
        if construction is not None
        else _inherited_glossary(ctx)
    )
    # the round's BASE may carry observation-layer patches inherited from the
    # previous winner: `round_seed` builds them into this round's shared
    # assembly, so every lattice model starts from them without a second
    # overlay here
    cands = [
        {
            "id": m["model_id"],
            "label": "+".join(m["axes_on"]) or "base",
            "antimony": m["antimony"],
            "parameters": m["parameters"],
            "assembly_overlay": m.get("assembly_overlay") or [],
            "structure_id": m.get("structure_id"),
            "encoding": m.get("encoding"),
            "fixed_at_neutral": m.get("fixed_at_neutral") or [],
            "entity_glossary_merged": merged_glossary(
                {"entity_glossary": base_gl},
                None,
                axes_on=[by_axis[a] for a in m["axes_on"] if a in by_axis],
            ),
            "rationale": f"model space: axes on = {m['axes_on'] or '(none)'}",
        }
        for m in models
    ]
    survivors, dropped, gate_lines = _ladder_candidates(
        ctx, {"candidates": cands}, t_end, max_candidates=max_models
    )
    if len(survivors) < 2:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"model-space search abandoned: fewer than two "
            f"candidates survived the gate ladder "
            f"({dropped}) — falling back to the base model",
        )
        return None
    print(
        f"  model-space search: {len(survivors)} of {len(cands)} candidates "
        f"passed the gate ladder"
    )
    # persist without a second human gate: the axis selection at the scope
    # gate WAS the approval, and it was made with the model count in view
    return _persist_md(
        ctx, construction, survivors, dropped, gate_lines, ask_human=False
    )


# --------------------------------------------------- the open-questions ledger


def open_questions_path(ctx: RunContext):
    """RUN-level, not round-level: a deferred structural question outlives the
    round that raised it. The run's `questions` record, shared with the
    engine-raised questions (`octomod.orchestration.interaction.questions`)."""
    from octomod.orchestration.interaction import questions as _q

    return _q.open_node(ctx.root)


def record_open_questions(
    ctx: RunContext,
    flagged: list,
    human_note: str,
    prefix: str = "s1",
    raised_by: str = "construction (S1)",
) -> None:
    """Persist the construction agent's escalations, together with what the
    human answered, as a standing ledger the later modules can consult, so a
    question deferred at one gate is still visible when later rounds revisit
    the model."""
    node = open_questions_path(ctx)
    existing = list(node.get([]) or [])
    known = {q["id"] for q in existing}
    for i, d in enumerate(flagged):
        # the prefix keeps two gates' questions apart: a staged round asks the
        # base's at the base gate and the expansions' at the scope gate, and
        # one index space would make the second set look already recorded
        qid = f"r{ctx.round_idx}_{prefix}_{i}"
        if qid in known:
            continue
        existing.append(
            {
                "id": qid,
                "raised_by": raised_by,
                "raised_round": ctx.round_idx,
                "topic": d.get("decision", "")[:200],
                "question": d.get("question", ""),
                "confidence": d.get("confidence"),
                "human_answer": human_note or "(approved without a note)",
                "status": "deferred_by_human" if human_note else "open",
            }
        )
    if existing:
        node.put(existing)
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"the `{node.key}` record now carries "
            f"{len(existing)} structural question(s) raised "
            f"at construction and answered by the human",
        )


def _inherited_glossary(ctx: RunContext) -> dict:
    """The round's `model/glossary` when one exists (a supplied model may ship
    one; an expansion round inherits the winner's). Absent, the assembly maps
    from structure alone — and the ledger says so."""
    gl = (ctx.round / "model/glossary").get(None)
    if gl is not None:
        return gl
    ctx.ledger.append(
        "note",
        module="model",
        round_idx=ctx.round_idx,
        note="no entity glossary for this model — the assembly "
        "agents map from structure alone",
    )
    return {"species": [], "parameters": []}


def _load_supplied_parameters(model: Node) -> list:
    """A supplied model must bring its parameter declaration (estimate flags,
    bounds) — if absent, everything is fixed at nominal and S3 will fail DOF
    loudly, which is the honest outcome."""
    return (model / "parameters").get([])


def _previous_round_antimony(ctx: RunContext) -> str | None:
    if ctx.round_idx == 0:
        return None
    prev = _tree.round_node(ctx.root, ctx.round_idx - 1) / "model/antimony"
    return prev.text(None)


def model_space_dropped_lines(ctx) -> list[str]:
    return model_space.dropped_axes_card_lines(ctx, module="model")
