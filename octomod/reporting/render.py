"""Text and mermaid views derived from the typed record.

A view is always derived from the record it depicts, so it cannot disagree
with it. Terminal views are shown at gates; mermaid views go into reports
(the round's `report_md` in the record; GitHub renders them once exported)
and the chat front end.
"""

from __future__ import annotations

from octomod.result.node import Node


def _model(sbml: str):
    import libsbml

    return libsbml.readSBMLFromString(sbml).getModel()


def _formula(kl) -> str:
    import libsbml

    return libsbml.formulaToString(kl.getMath()) if kl and kl.getMath() else "?"


def species_initial(m, sid: str) -> str:
    """A species' initial as a human should read it: a number, or the
    ASSIGNMENT that defines it — never NaN (an assignment-based initial has
    no constant value; printing NaN misreads a well-built model as broken)."""
    import libsbml

    sp = m.getSpecies(sid)
    ia = m.getInitialAssignmentBySymbol(sid)
    if ia is not None and ia.getMath() is not None:
        return f"{libsbml.formulaToString(ia.getMath())} (assigned)"
    if sp.isSetInitialConcentration():
        return f"{sp.getInitialConcentration():g}"
    if sp.isSetInitialAmount():
        return f"{sp.getInitialAmount():g}"
    return "(undefined)"


def parameter_display(m, pid: str) -> tuple[str, str]:
    """(value_text, kind) where kind is 'derived' for assignment-rule
    parameters (diagnostics like total checks), else 'constant'."""
    import libsbml

    rule = m.getRuleByVariable(pid)
    if rule is not None and rule.getMath() is not None:
        return f":= {libsbml.formulaToString(rule.getMath())}", "derived"
    ia = m.getInitialAssignmentBySymbol(pid)
    if ia is not None and ia.getMath() is not None:
        return f"= {libsbml.formulaToString(ia.getMath())} (assigned)", "constant"
    return f"= {m.getParameter(pid).getValue():g}", "constant"


def model_terminal_lines(sbml: str, parameters: list[dict] | None = None) -> list[str]:
    """The model as a human reads it: species with initials, reactions as
    arrows with their rate laws, parameters with estimation status.
    Assignment-aware — see species_initial / parameter_display."""
    m = _model(sbml)
    lines = ["THE MODEL, as built:"]
    for i in range(m.getNumSpecies()):
        sid = m.getSpecies(i).getId()
        lines.append(f"  species    {sid:12s} initial = {species_initial(m, sid)}")
    for i in range(m.getNumReactions()):
        rxn = m.getReaction(i)
        lhs = (
            " + ".join(
                rxn.getReactant(j).getSpecies() for j in range(rxn.getNumReactants())
            )
            or "(source)"
        )
        rhs = (
            " + ".join(
                rxn.getProduct(j).getSpecies() for j in range(rxn.getNumProducts())
            )
            or "(sink)"
        )
        lines.append(
            f"  reaction   {lhs} -> {rhs}    rate: {_formula(rxn.getKineticLaw())}"
        )
    est = {p["id"]: p for p in (parameters or [])}
    for i in range(m.getNumParameters()):
        pid = m.getParameter(i).getId()
        val, kind = parameter_display(m, pid)
        if pid in est and est[pid].get("estimate"):
            e = est[pid]
            lines.append(
                f"  parameter  {pid:12s} {val}   "
                f"ESTIMATED in [{e.get('lb')}, {e.get('ub')}]"
            )
        elif kind == "derived":
            lines.append(f"  derived    {pid:12s} {val}   (diagnostic, no dynamics)")
        else:
            lines.append(f"  parameter  {pid:12s} {val}   fixed")
    return lines


def model_mermaid(sbml: str) -> str:
    """Reaction network in SBGN-style process-node form: species are boxes,
    each reaction is a small hexagon node carrying its RATE LAW, so the law
    sits on the reaction rather than dangling on an edge. Modifiers arrive
    dashed. Renders on GitHub and in the chat front end."""
    m = _model(sbml)
    lines = ["flowchart LR"]
    for i in range(m.getNumSpecies()):
        sid = m.getSpecies(i).getId()
        lines.append(f'    {sid}["{sid}"]')
    for i in range(m.getNumReactions()):
        rxn = m.getReaction(i)
        rid = rxn.getId() or f"rxn{i}"
        rate = _formula(rxn.getKineticLaw()).replace('"', "'")
        rev = " ⇌" if rxn.getReversible() else ""
        lines.append(f'    {rid}{{{{"{rid}: {rate}{rev}"}}}}')
        reactants = [
            rxn.getReactant(j).getSpecies() for j in range(rxn.getNumReactants())
        ]
        products = [rxn.getProduct(j).getSpecies() for j in range(rxn.getNumProducts())]
        for r in reactants:
            lines.append(f"    {r} --> {rid}")
        for p in products:
            lines.append(f"    {rid} --> {p}")
        if not reactants:
            lines.append(f"    src_{rid}(( )) --> {rid}")
        if not products:
            lines.append(f"    {rid} --> sink_{rid}(( ))")
        for j in range(rxn.getNumModifiers()):
            lines.append(f"    {rxn.getModifier(j).getSpecies()} -.-> {rid}")
    return "\n".join(lines)


def decisions_md(rnd_node: Node) -> str:
    """One readable document per round (`rounds/round_k`): who decided what,
    and why — assembled from the agents' structured records, never written by
    them. The caller stores it at the round's `decisions_md`."""
    from octomod.result.access import (
        as_artifact,
        candidate_assembly,
        ledger_rows,
        record_for,
        round_of,
    )

    rr = record_for(rnd_node)
    rnd = round_of(rr, rnd_node)

    def _reply(role: str):
        call = rnd.agent_calls.get(role) if rnd is not None else None
        return call.reply if call is not None else None

    # every input below is read off the run's typed record, named
    # by its record key under the round
    def load(key):
        if rnd is None:
            return None
        return {
            "model/build_report": rnd.model.build_report if rnd.model else None,
            "data/report": rnd.data.report if rnd.data else None,
            # the single-model round's `assembly`, else the shared base
            "assembly": candidate_assembly(rnd),
            "shared_assembly": as_artifact(rnd.shared_assembly),
            "supplied_evidence": rnd.supplied_evidence,
            "evidence": rnd.evidence,
            "agent_calls/construction_verification/reply": _reply(
                "construction_verification"
            ),
            "agent_calls/assembly_verification/reply": _reply("assembly_verification"),
            "space/dropped": list(rnd.space.dropped) if rnd.space else None,
        }.get(key)

    lines = [f"# Decision record — {rnd_node.name}", ""]

    build = load("model/build_report")
    if build:
        lines += ["## Model construction (agent)", ""]
        for d in build.get("decisions", []):
            mark = " **[asked the user]**" if d.get("user_decision_required") else ""
            lines.append(f"- **{d.get('decision','')}**{mark}")
            if d.get("rationale"):
                lines.append(f"  - why: {d['rationale']}")
            alts = d.get("alternatives_considered")
            if alts:
                alts = ", ".join(alts) if isinstance(alts, list) else alts
                lines.append(f"  - alternatives: {alts}")
            for e in d.get("evidence") or []:
                if isinstance(e, dict):
                    org = f" ({e['origin']})" if e.get("origin") else ""
                    lines.append(
                        f"  - source: {e.get('source','?')}"
                        f" [{e.get('locator','')}]{org} — {e.get('supports','')}"
                    )
            demote = (
                f" (demoted from {d['tier_demoted_from']}: no source)"
                if d.get("tier_demoted_from")
                else ""
            )
            lines.append(
                f"  - evidence tier: {d.get('evidence_tier','?')}{demote} · "
                f"confidence: {d.get('confidence','?')}"
            )
        src = build.get("consulted_sources", [])
        lines += [
            "",
            f"consulted sources: {'; '.join(src) if src else 'none declared'}",
            "",
        ]

    data = load("data/report")
    if data:
        lines += ["## Data semantics (agent)", ""]
        for m in data.get("mappings", []):
            lines.append(
                f"- `{m.get('file')}`: {m.get('observable_label')} from "
                f"`{m.get('value_column')}`, units {m.get('units')}, "
                f"error {m.get('error_type')}"
            )
        flags = data.get("flags", [])
        if flags:
            lines += ["", f"flags raised ({len(flags)}) — flag-never-exclude:", ""]
            lines += [f"- {f}" for f in flags]
        proc = data.get("processing") or []
        if proc:
            lines += [
                "",
                "processing declared by data extraction, executed by the engine:",
                "",
            ]
            for e in proc:
                ref = e.get("reference") or {}
                what = (
                    f"reference {ref}"
                    if ref
                    else (
                        f"factor {e.get('factor')}" if "factor" in e else "per-cell sum"
                    )
                )
                lines.append(
                    f"- **{e.get('kind')}** on {', '.join(e.get('labels', []))} ({what}, "
                    f"{e.get('n_rows')} rows) — why: {e.get('rationale') or '(no rationale given)'}"
                )
        lines.append("")

    asm = load("assembly") or load("shared_assembly")
    if asm:
        lines += [
            "## Estimation-problem assembly (observation model + condition encoding)",
            "",
        ]
        for o in asm.get("observables", []):
            lines.append(
                f"- **observable** `{o['observable_id']}` = "
                f"`{o.get('formula')}` ({o.get('transformation','lin')}): "
                f"{o.get('rationale','')}"
            )
        for n in asm.get("noise", []):
            lines.append(
                f"- **noise** `{n['observable_id']}`: {n.get('distribution')}"
                f", sigma `{n.get('formula')}`: {n.get('rationale','')}"
            )
        for s in asm.get("scaling", []):
            lines.append(
                f"- **scaling** `{s['observable_id']}`: mode {s.get('mode')}"
                f": {s.get('rationale','')}"
            )
        for c in asm.get("conditions", []):
            lines.append(
                f"- **condition** `{c['condition_id']}` <- "
                f"'{c.get('maps_to_label')}', overrides {c.get('overrides')}"
                f": {c.get('rationale','')}"
            )
        lines.append("")

    # shown by origin: who handed a source over is part of the decision record
    sup = load("supplied_evidence")
    ev = load("evidence")
    if sup or ev:
        lines += ["## Evidence handed to construction (`retrieved_evidence`)", ""]
        if sup:
            items = sup.get("items", [])
            lines.append(
                f"supplied by the human in `intent.supplied_literature` "
                f"(origin: human) — {len(items)} item(s), "
                f"{sup.get('n_cached', 0)} document(s) cached for audit:"
            )
            for it in items:
                lines.append(
                    f"- `{it.get('id', '?')}` {it.get('source', '?')} "
                    f"({it.get('year', '?')}) [{it.get('locator', '')}] — "
                    f"{it.get('supports', '')}"
                )
            lines.append("")
        if ev:
            lines.append(
                "retrieved online by the research role, filtered by the engine "
                "(origin: research):"
            )
            for it in ev.get("items", []):
                lines.append(
                    f"- {it.get('source','?')} ({it.get('year','?')}) "
                    f"[{it.get('locator','')}] — {it.get('supports','')}"
                )
            if ev.get("dropped"):
                lines.append(
                    f"- ({len(ev['dropped'])} item(s) dropped by the "
                    f"blocklist/year filter — see the round's `evidence` record)"
                )
            lines.append("")

    lines += reaction_support_lines(rnd, rr)

    aud = load("agent_calls/construction_verification/reply")
    if aud:
        lines += [
            "## Independent construction audit (fresh context, artifacts only)",
            "",
        ]
        for v in aud.get("verdicts", []):
            lines.append(
                f"- {'OK' if v.get('ok') else 'CONCERN'} — "
                f"{v.get('aspect')}: {v.get('note','')}"
            )
        lines.append("")

    # this round's ledger rows; a missing or unreadable ledger reads as none
    try:
        tail = rnd_node.name.rsplit("_", 1)[-1]
        ridx = int(tail) if tail.isdigit() else 0
        rows = ledger_rows(rr)
    except Exception:
        rows = []
    # which decisions cited the human's literature and which the research
    # role's (S1's `evidence_attribution` row)
    att = [
        e
        for e in rows
        if e.get("round") == ridx and e.get("event") == "evidence_attribution"
    ]
    if att:
        e = att[-1]
        lines += ["## Which literature the build leaned on (engine)", ""]
        lines.append(
            f"- {len(e.get('leaned_on_human') or [])} of {e.get('n_decisions')} "
            f"decision(s) cite the human's supplied literature "
            f"({e.get('n_supplied_items')} item(s)); "
            f"{len(e.get('leaned_on_research') or [])} cite research items "
            f"({e.get('n_research_items')} item(s)); {e.get('cited_neither')} "
            f"cite neither"
        )
        for who, key in (
            ("supplied", "leaned_on_human"),
            ("research", "leaned_on_research"),
        ):
            for label in e.get(key) or []:
                lines.append(f"  - {who}: {label}")
        lines.append("")
    fb = [
        e
        for e in rows
        if e.get("round") == ridx
        and (
            e.get("event")
            in ("redraft_attributed", "assembly_fallback", "candidate_dropped")
            or (e.get("event") == "note" and e.get("human_redraft"))
            # a compile failure the engine sent back to its author
            or (e.get("event") == "note" and e.get("engine_feedback"))
            # a base the engine asked again after a targeted search
            or (e.get("event") == "note" and e.get("engine_redraft"))
        )
    ]
    dropped = load("space/dropped") or []
    if fb or dropped:
        lines += ["## Battery feedback (engine)", ""]
        for e in fb:
            if e.get("event") == "redraft_attributed":
                lines.append(
                    f"- re-asked **{e.get('role')}** after `{e.get('gate_id')}` "
                    f"(attempt {e.get('attempt')}, module {e.get('module')})"
                )
            elif e.get("event") == "assembly_fallback":
                lines.append(
                    f"- **fallback `{e.get('fallback')}`** applied to {e.get('role')}'s "
                    f"block, signed by {e.get('signed')}; the agent's reply is kept in the record"
                )
            elif e.get("event") == "candidate_dropped":
                lines.append(
                    f"- candidate `{e.get('candidate')}` dropped: {e.get('reason')}"
                )
            else:
                lines.append(f"- {e.get('note')}")
        for d in dropped:
            lines.append(
                f"- axis `{d.get('id')}` declared by {d.get('declared_by')} was dropped: "
                f"{d.get('reason')}"
            )
        lines.append("")
    # what the payload budget did not show an agent (rows `call_agent` wrote):
    # a trim is a decision the engine made on the human's behalf
    trims = [
        e
        for e in rows
        if e.get("round") == ridx and e.get("event") == "payload_trimmed"
    ]
    if trims:
        lines += ["## What the agents were not shown (payload budget)", ""]
        for e in trims:
            lines.append(
                f"- **{e.get('role')}** — {e.get('step')}: {e.get('what')} "
                f"({int(e.get('bytes_before') or 0):,} -> "
                f"{int(e.get('bytes_after') or 0):,} bytes). The payload says so "
                f"in its own text and names the request that fetches it back."
            )
        lines.append("")

    ver = load("agent_calls/assembly_verification/reply")
    if ver:
        lines += ["## Independent checker (fresh context, artifacts only)", ""]
        for v in ver.get("verdicts", []):
            lines.append(
                f"- {'OK' if v.get('ok') else 'CONCERN'} — "
                f"{v.get('aspect')}: {v.get('note','')}"
            )
        lines.append("")

    mmd = rnd.model.mermaid if rnd is not None and rnd.model else None
    if mmd:
        lines += [
            "## Model diagram",
            "",
            "```mermaid",
            mmd.strip(),
            "```",
            "",
        ]
    return "\n".join(lines)


def _support_models(rnd) -> list[tuple[str, dict]]:
    """(title, annotation) for every annotated model of a round record: the
    round's model, a discrimination round's base, then each candidate."""
    out = []
    cands = [c for c in (rnd.candidates or {}) if c != "_single"]
    if rnd.model is not None and rnd.model.reaction_support:
        out.append(("the base" if cands else "the model", rnd.model.reaction_support))
    if rnd.base_model is not None and rnd.base_model.reaction_support:
        out.append(("the base", rnd.base_model.reaction_support))
    for cid in cands:
        m = rnd.candidates[cid].model
        if m is not None and m.reaction_support:
            out.append((f"candidate `{cid}`", m.reaction_support))
    return out


def reaction_support_lines(rnd, run=None) -> list[str]:
    """The decision record's section "Reactions and their support": for each
    annotated model, its counts, every reaction with its label, the entry it
    matches and the sources that count for it, then the inferred reactions
    set apart, then the dossier entries the model does not use. The entries
    are read from the round the annotation names (`dossier_round`, in `run`),
    which for a round an expansion seeded is an earlier one. Nothing when no
    model of the round is annotated."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    if rnd is None:
        return []
    models = _support_models(rnd)
    if not models:
        return []
    dossier = rnd.reaction_evidence
    k = _rxe.dossier_round_of(models[0][1], rnd.index or 0)
    held = run.rounds.get(f"round_{k}") if run is not None else None
    if held is not None and held.reaction_evidence:
        dossier = held.reaction_evidence
    # the staged entries, then those a targeted search admitted in this round
    # or the round the dossier is in
    admitted = list(getattr(rnd, "knowledge_admitted", None) or [])
    if held is not None and held is not rnd:
        admitted += list(getattr(held, "knowledge_admitted", None) or [])
    entries = {
        str(e.get("id")): e
        for e in list((dossier or {}).get("reactions") or []) + admitted
        if isinstance(e, dict) and e.get("id")
    }
    lines = [
        "## Reactions and their support (engine)",
        "",
        "Every model reaction matched to the round's reaction dossier "
        "(`reaction_evidence`) by its reactants and products, in each direction "
        "its rate law can carry. Each entry's grade is a band the engine decided "
        "from the declared rule table, with the source that earned it — never a "
        "number.",
        "",
    ]
    for title, support in models:
        lines += [f"### {title}", "", _rxe.summary_line(support), ""]
        for r in support.get("reactions") or []:
            lines.append(
                f"- `{r.get('reaction_id')}` {_rxe.reaction_sides(r)} (law `{r.get('law')}`) "
                f"— **{r.get('label')}**"
                + (
                    f"; held as a parameter: {', '.join(r['as_parameter'])}"
                    if r.get("as_parameter")
                    else ""
                )
            )
            for way, b in (r.get("directions") or {}).items():
                if b is None:
                    continue
                sides = _rxe.reaction_sides(r, backward=way == "backward")
                if not b.get("entry_id"):
                    lines.append(f"  - {sides}: nothing in the dossier")
                    continue
                others = [
                    x
                    for x in b.get("entries") or []
                    if str(x.get("id")) != str(b["entry_id"])
                ]
                lines.append(
                    f"  - {sides}: `{b['entry_id']}` {b.get('equation')} "
                    f"({_rxe.because_text(b.get('grade'), b.get('because'))}; origin "
                    f"{b.get('origin') or '?'}) — {b.get('label')}"
                    + (
                        "; also "
                        + ", ".join(
                            f"`{x.get('id')}` (origin {x.get('origin')}, "
                            f"{_rxe.band_text(x.get('grade'))})"
                            for x in others
                        )
                        if others
                        else ""
                    )
                )
                for it in _rxe.counted_items(entries.get(str(b["entry_id"])) or {}):
                    lines.append(
                        f"    - source: {it.get('source', '?')} "
                        f"[{it.get('locator') or ''}] — {it.get('evidence_kind')}, "
                        f"{it.get('context_match')}"
                        + (" (origin: human)" if it.get("origin") == "human" else "")
                    )
        inferred = [
            r for r in support.get("reactions") or [] if r.get("label") == _rxe.INFERRED
        ]
        if inferred:
            lines += ["", "inferred — put to the person at the scope card:", ""]
            lines += [f"- {_rxe.inferred_line(r)}" for r in inferred]
        missing = support.get("required_missing") or []
        if missing:
            lines += ["", "required by the intent, and in no model reaction:", ""]
            lines += [f"- `{m['id']}` {m['equation']}" for m in missing]
        unused = support.get("unused_entries") or []
        if unused:
            lines += ["", "dossier entries the model does not use:", ""]
            for eid in unused:
                e = entries.get(str(eid)) or {}
                lines.append(
                    f"- `{eid}` {e.get('equation', '?')} (grade "
                    f"{_rxe.band_text(e.get('grade'))}"
                    + (", required" if e.get("required") else "")
                    + f"; {len(_rxe.counted_items(e))} counted source(s))"
                )
        lines.append("")
    return lines
