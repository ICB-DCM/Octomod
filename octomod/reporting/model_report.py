"""model_report.html — M1 to M5, the model as built.

Written at the end of S1, BEFORE the scope gate, because it is the document the
human reads in order to answer that gate: what was built, where the build
needed a judgement call, how confident each call was, and what the
deterministic ladder already proved. Same rules as the round report — fixed
sections, no LLM, degrade rather than raise.
"""

from __future__ import annotations

import json
from pathlib import Path

from octomod.reporting.budget import (
    DECISION_ALTERNATIVES_CHARS,
    DECISION_QUESTION_CHARS,
    DECISION_RATIONALE_CHARS,
    DECISIONS_SHOWN,
    EVIDENCE_LINES_SHOWN,
    clip_chars,
    fold,
)
from octomod.reporting.html import (
    esc,
    kv,
    load_json,
    load_text,
    note,
    num,
    page,
    table,
    trunc,
)
from octomod.reporting.round_report import (
    Round,
)
from octomod.reporting.sbml_view import (
    comparison_figure,
    model_counts,
    model_tables_or_note,
    network_figure,
)
from octomod.result import node as tree
from octomod.result.node import Node

_CONF_WORDS = {
    "low": 0.25,
    "medium": 0.55,
    "moderate": 0.55,
    "high": 0.85,
    "very high": 0.95,
    "very low": 0.1,
}


def _confidence(value) -> tuple[float, str]:
    """Confidence arrives as a word or a float depending on which agent wrote
    it. Normalise to a sort key; keep the original text for display."""
    if value is None:
        return 0.0, "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), f"{float(value):.2f}"
    word = str(value).strip().lower()
    if word in _CONF_WORDS:
        return _CONF_WORDS[word], str(value)
    try:
        v = float(word)
        return v, f"{v:.2f}"
    except ValueError:
        return 0.0, str(value)


_TIER_CLASS = {
    "default": "tier-default",
    "assumed": "tier-default",
    "transferred": "tier-transferred",
    "analogous": "tier-transferred",
    "direct": "tier-direct",
    "measured": "tier-direct",
    "reported": "tier-direct",
}


# What the evidence tier says, in the reader's words: `default` means no
# resolvable source (not "the default choice"), `transferred` a measurement of
# another system. Mapped only at this render boundary; the machine vocabulary
# (`evidence_tier` values, the demotion rule in s1) stays in the record.
TIER_WORDS = {
    "direct": "measured here",
    "transferred": "carried from elsewhere",
    "default": "no source given",
    "to_be_estimated": "fitted",
}

# What the column is for, in one sentence above the table.
TIER_COLUMN_NOTE = (
    "This column says WHERE EACH NUMBER CAME FROM: measured in this "
    "experiment, carried over from another system or context, taken from an "
    "engine default because no source resolved, or being estimated from the "
    "data. Carried from elsewhere is the one to look at hardest — it is a "
    "real measurement of a different system."
)


def tier_words(tier) -> str:
    """The reader's phrase for a machine tier, or the raw value if unknown.

    An unrecognised tier is shown verbatim rather than blanked: a new value
    this map has not learned must be visible, not silently rendered as
    nothing.
    """
    key = str(tier or "").strip().lower()
    return TIER_WORDS.get(key, str(tier or "\u2014"))


def _tier_cell(tier) -> str:
    t = str(tier or "\u2014")
    cls = _TIER_CLASS.get(t.strip().lower(), "tier-none")
    # the machine value rides along in the tooltip, for a reader who is also
    # looking at the model's build_report
    return (
        '<span class="tier '
        + cls
        + '" title="evidence_tier: '
        + esc(t)
        + '">'
        + esc(tier_words(t))
        + "</span>"
    )


def _m1_glance(model: Node, title: str = "") -> str:
    """M1 — the model record `model` at a glance."""
    sbml = load_text(model / "sbml")
    parts = []
    if sbml is None:
        parts.append(note(f"{model.key}/sbml is missing — no diagram, no counts"))
    else:
        parts.append(network_figure(sbml, title))
        try:
            counts = model_counts(sbml)
        except Exception as exc:
            counts = []
            parts.append(note(f"counts unavailable: {trunc(exc, 120)}"))
        pj = load_json(model / "parameters")
        if isinstance(pj, list):
            counts.append(
                (
                    "declared for estimation",
                    str(
                        sum(1 for p in pj if isinstance(p, dict) and p.get("estimate"))
                    ),
                )
            )
        if counts:
            parts.append(kv([(k, esc(v)) for k, v in counts]))
        parts.append(model_tables_or_note(model, sbml))
    gl = load_json(model / "glossary")
    if isinstance(gl, dict) and (gl.get("species") or gl.get("parameters")):
        # the same glossary the assembly agents read, so the human answers
        # the scope gate seeing what the builder says the model MEANS
        parts.append("<h3>What the model means (entity glossary)</h3>")
        rows = [
            [
                f"<code>{esc(e.get('id', '—'))}</code>",
                "species",
                esc(e.get("denotes", "")),
                esc(e.get("unit_convention", "")),
                esc(e.get("lump_membership", "")),
            ]
            for e in gl.get("species") or []
            if isinstance(e, dict)
        ]
        rows += [
            [
                f"<code>{esc(e.get('id', '—'))}</code>",
                "parameter",
                esc(e.get("role", e.get("denotes", ""))),
                esc(e.get("convention", "")),
                esc(e.get("from_axis", "")),
            ]
            for e in gl.get("parameters") or []
            if isinstance(e, dict)
        ]
        parts.append(
            table(
                [
                    "id",
                    "kind",
                    "denotes / role",
                    "unit or convention",
                    "lumps / from axis",
                ],
                rows,
            )
        )
    elif gl is None:
        parts.append(
            note(
                "no entity glossary — the assembly agents map this "
                "model from its structure alone"
            )
        )
    ant = load_text(model / "antimony")
    if ant:
        parts.append(
            "<details><summary>Antimony source (model/antimony)</summary>"
            f"<pre>{esc(ant)}</pre></details>"
        )
    else:
        parts.append(note("model/antimony is missing"))
    return "".join(parts)


# the chip each reaction label wears: supported green, inferred flagged
_SUPPORT_CHIP = {
    "user-provided": "pass",
    "database-supported": "pass",
    "literature-supported": "mute",
    "inferred": "flag",
}


def _support_chip(label) -> str:
    cls = _SUPPORT_CHIP.get(str(label), "mute")
    return f'<span class="chip {cls}">{esc(str(label or "—"))}</span>'


def _counted_sources(entry: dict | None) -> str:
    """The sources that count for a dossier entry, each with the search's
    classification."""
    from octomod.workflow_modules.knowledge.reaction_evidence import counted_items

    items = counted_items(entry or {})
    if not items:
        n = len((entry or {}).get("evidence") or [])
        return note(
            "no source that counts"
            + (f" ({n} cited, none passing the preconditions)" if n else "")
        )
    return _evidence_lines(
        [
            {
                "source": it.get("source"),
                "locator": it.get("locator"),
                "supports": (
                    f"{it.get('evidence_kind') or '?'}, "
                    f"{it.get('context_match') or '?'}"
                    + (
                        " · contradicts"
                        if str(it.get("stance") or "") == "contradicts"
                        else ""
                    )
                    + (" · supplied by you" if it.get("origin") == "human" else "")
                ),
            }
            for it in items
        ]
    )


def _because(block: dict) -> str:
    from octomod.workflow_modules.knowledge.reaction_evidence import because_text

    return because_text(block.get("grade"), block.get("because"))


def _entry_cell(block: dict | None, way: str) -> str:
    if block is None:
        return ""
    if not block.get("entry_id"):
        return f"<div>{esc(way)}: nothing in the dossier</div>"
    also = block.get("also_matches") or []
    origins = {
        str(x.get("id")): str(x.get("origin") or "")
        for x in block.get("entries") or []
        if x.get("id")
    }
    return (
        f"<div>{esc(way)}: <code>{esc(block['entry_id'])}</code> "
        f"<code>{esc(str(block.get('equation', '')))}</code> · "
        f"{esc(_because(block))}"
        + (f" · origin {esc(str(block['origin']))}" if block.get("origin") else "")
        + (
            " · also "
            + esc(
                ", ".join(
                    f"{a} (origin {origins[a]})" if origins.get(a) else str(a)
                    for a in also
                )
            )
            if also
            else ""
        )
        + "</div>"
    )


def _floor_held_to(floor: dict | None) -> str:
    """The sentence on the floor what a candidate adds was held to, from its
    annotation's `floor`; "" when it records none."""
    from octomod.workflow_modules.knowledge.reaction_evidence import band_text

    if not isinstance(floor, dict) or not floor.get("band"):
        return ""
    band = band_text(floor.get("band"))
    if floor.get("held_to") == "variants":
        return (
            f"What this candidate adds to the base was held to the variants' floor "
            f"{band} (the base's floor {band_text(floor.get('base'))} lowered by "
            f"{floor.get('offset')}): a conversion graded below it, or one no "
            f"dossier entry describes, was refused before any fit; the base's own "
            f"reactions were held to {band_text(floor.get('base'))}."
        )
    if floor.get("held_to") == "axes":
        return (
            f"What this candidate's axes add to the round's base was held to the "
            f"round's support floor {band} (set by {floor.get('source')}): an axis "
            f"adding a conversion graded below it was refused from the offer."
        )
    return f"Held to the support floor {band}."


def _reactions_block(model: Node, rnd: Node, anchor: bool = True) -> str:
    """Where each reaction of `model` comes from: its annotation against the
    round's dossier (`<model>/reaction_support`), one row per model reaction
    with the entry it matches in each direction its rate law carries and the
    sources that count for it, then the dossier entries the model does not
    use. Nothing when the model is not annotated. `anchor` gives the heading
    the id a gate card's link names; a page carries it once."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    support = load_json(model / "reaction_support")
    if not isinstance(support, dict):
        return ""
    # the dossier the annotation was made against, which a round an
    # expansion seeded holds in an earlier round
    k = _rxe.dossier_round_of(support, tree.round_index(rnd))
    held = tree.round_node(rnd.parent.parent, k)
    dossier = load_json(held / _rxe.DOSSIER_KEY) or {}
    # the staged entries, then those a targeted search admitted
    admitted = list(load_json(rnd / _rxe.ADMITTED_KEY) or [])
    if held.key != rnd.key:
        admitted += list(load_json(held / _rxe.ADMITTED_KEY) or [])
    entries = {
        str(e.get("id")): e
        for e in list(dossier.get("reactions") or []) + admitted
        if isinstance(e, dict) and e.get("id")
    }
    c = support.get("counts") or {}
    parts = [
        "<h3"
        + (' id="reaction-support"' if anchor else "")
        + ">Where each reaction comes from</h3>",
        note(
            f"Every reaction is matched to the reaction dossier (the literature "
            f"search before construction) by its reactants and products, in each "
            f"direction its rate law can carry — the law decides, not the arrow. "
            f"{c.get('user_provided', 0)} user-provided (the intent requires it), "
            f"{c.get('database_supported', 0)} database-supported, "
            f"{c.get('literature_supported', 0)} literature-supported, "
            f"{c.get('inferred', 0)} inferred (nothing in the dossier backs it in "
            f"some direction it runs). Each entry's grade is a band the engine "
            f"decided from the declared rule table, with the source that earned "
            f"it — never a number."
        ),
    ]
    held = _floor_held_to(support.get("floor"))
    if held:
        parts.append(note(held))
    missing = support.get("required_missing") or []
    if missing:
        parts.append(
            '<div class="flagbox"><b>Required by the intent and in no model '
            "reaction:</b><ul>"
            + "".join(
                f"<li><code>{esc(m.get('id'))}</code> "
                f"<code>{esc(m.get('equation'))}</code></li>"
                for m in missing
            )
            + "</ul></div>"
        )
    rows = []
    for r in support.get("reactions") or []:
        dirs = r.get("directions") or {}
        fwd = (
            " + ".join(r.get("reactants") or [])
            + " -> "
            + " + ".join(r.get("products") or [])
        )
        bwd = (
            " + ".join(r.get("products") or [])
            + " -> "
            + " + ".join(r.get("reactants") or [])
        )
        matched = [
            entries.get(str(b.get("entry_id")))
            for b in dirs.values()
            if isinstance(b, dict) and b.get("entry_id")
        ]
        held = r.get("as_parameter") or []
        rows.append(
            [
                f"<code>{esc(r.get('reaction_id'))}</code>",
                f"<code>{esc(fwd.strip())}</code>"
                + (
                    " <span class='muted'>(the law runs both ways)</span>"
                    if dirs.get("backward")
                    else ""
                )
                + f"<div class='muted'>law {esc(r.get('law'))}</div>",
                _support_chip(r.get("label")),
                _entry_cell(dirs.get("forward"), fwd.strip())
                + _entry_cell(dirs.get("backward"), bwd.strip())
                + (
                    f"<div class='muted'>held as a parameter: "
                    f"{esc(', '.join(held))}</div>"
                    if held
                    else ""
                ),
                "".join(_counted_sources(e) for e in matched if e is not None)
                or note("nothing in the dossier"),
            ]
        )
    parts.append(
        table(
            ["reaction", "equation", "label", "matched entry", "counted sources"],
            rows,
        )
    )
    unused = [entries[i] for i in support.get("unused_entries") or [] if i in entries]
    if unused:
        parts.append(
            fold(
                f"{len(unused)} dossier entr{'y' if len(unused) == 1 else 'ies'} "
                f"the model does not use",
                table(
                    ["entry", "equation", "support", "sources"],
                    [
                        [
                            f"<code>{esc(e.get('id'))}</code>"
                            + (
                                " <span class='muted'>(required)</span>"
                                if e.get("required")
                                else ""
                            ),
                            f"<code>{esc(e.get('equation'))}</code>",
                            esc(
                                _rxe.because_text(e.get("grade"), e.get("because"))
                                + f" · origin {_rxe.origin_of(e)}"
                            ),
                            _counted_sources(e),
                        ]
                        for e in unused
                    ],
                ),
            )
        )
    return "".join(parts)


def _reactions_summary(r: Round, cids: list[str]) -> str:
    """For a candidate set: each candidate's reaction counts and its inferred
    reactions in one table; each candidate's own view below carries the full
    block. Nothing when no candidate is annotated."""
    rows = []
    for cid in cids:
        support = load_json(tree.model_node(r.rnd, cid) / "reaction_support")
        if not isinstance(support, dict):
            continue
        c = support.get("counts") or {}
        rows.append(
            [
                f"<code>{esc(cid)}</code>",
                esc(str(len(support.get("reactions") or []))),
                esc(
                    f"{c.get('user_provided', 0)} / {c.get('database_supported', 0)} / "
                    f"{c.get('literature_supported', 0)} / {c.get('inferred', 0)}"
                ),
                ", ".join(
                    f"<code>{esc(x)}</code>" for x in support.get("inferred") or []
                )
                or "—",
            ]
        )
    if not rows:
        return ""
    return (
        '<h3 id="reaction-support">Where each reaction comes from</h3>'
        + note(
            "Each candidate's reactions matched to the reaction dossier; its own "
            "view below lists every reaction with its matched entry and sources."
        )
        + table(
            [
                "candidate",
                "reactions",
                "user-provided / database / literature / inferred",
                "inferred",
            ],
            rows,
        )
    )


def _m2_input_needed(build: dict | None) -> str:
    """M2 — the places the build needed a judgement the description did not
    settle. These are the questions the scope gate exists to answer."""
    if build is None:
        return note(
            "no model/build_report — this model was supplied rather "
            "than constructed by an agent, so it declares no open "
            "questions"
        )
    flagged = [
        d
        for d in (build.get("decisions") or [])
        if isinstance(d, dict) and d.get("user_decision_required")
    ]
    if not flagged:
        return (
            '<div class="okbox">The construction agent flagged '
            "<b>no</b> choice as needing your decision. Every assumption it "
            "made is listed in section M3 with its confidence — a low "
            "confidence there is still worth your eye.</div>"
        )
    flagged.sort(key=lambda d: _confidence(d.get("confidence"))[0])
    items = []
    for _k, d in enumerate(flagged, 1):
        q = str(d.get("question") or d.get("decision") or "")
        alts = d.get("alternatives_considered")
        alts = ", ".join(alts) if isinstance(alts, list) else (alts or "")
        conf = _confidence(d.get("confidence"))[1]
        items.append(
            f'<li><p class="ask">{esc(q)}</p>'
            + fold(
                "what the agent did meanwhile, and on what evidence",
                f'<p class="askmeta">decision taken meanwhile: '
                f'{esc(str(d.get("decision", "—")))}<br>'
                + (f"alternatives considered: {esc(alts)}<br>" if alts else "")
                + "where the number came from: "
                + _tier_cell(d.get("evidence_tier"))
                + " · "
                f"confidence: {esc(conf)}</p>",
            )
            + "</li>"
        )
    return (
        '<div class="askbox"><b>The construction agent acted either way and '
        "wants your call on these.</b> It is cheap to change the network "
        "now and expensive to regret it after calibration."
        f"<ol class=\"asks\">{''.join(items)}</ol></div>"
    )


_GENERIC_SOURCE = (
    "general knowledge",
    "general_knowledge",
    "common knowledge",
    "background knowledge",
    "domain knowledge",
    "prior knowledge",
    "no source",
    "none",
    "model builder",
    "assumed",
)


def _is_generic_source(source: str) -> bool:
    """A 'general knowledge' citation is not a citation. It still gets shown —
    flag-never-hide — but muted, so a real locator stands out against it."""
    s = str(source or "").strip().lower()
    return (not s) or any(g in s for g in _GENERIC_SOURCE)


def _evidence_lines(evidence) -> str:
    """Each entry as a compact 'source [locator] — supports' line."""
    if not isinstance(evidence, list) or not evidence:
        return ""
    out = []
    for e in evidence:
        if not isinstance(e, dict):
            out.append(f'<span class="ev gen">{esc(trunc(e, 200))}</span>')
            continue
        source = str(e.get("source", "")).strip()
        locator = str(e.get("locator", "")).strip()
        supports = str(e.get("supports", "")).strip()
        text = esc(source or "—")
        if locator:
            text += f' <span class="loc">[{esc(locator)}]</span>'
        if supports:
            text += f" — {esc(supports)}"
        cls = "ev gen" if _is_generic_source(source) else "ev"
        out.append(f'<span class="{cls}">{text}</span>')
    # The first citations carry the claim; a long list is context that folds.
    if len(out) > EVIDENCE_LINES_SHOWN:
        head = "".join(out[:EVIDENCE_LINES_SHOWN])
        return f'<div class="evlist">{head}</div>' + fold(
            f"all {len(out)} citations",
            f'<div class="evlist">{"".join(out)}</div>',
        )
    return f'<div class="evlist">{"".join(out)}</div>'


def _carried_model(r: Round) -> str | None:
    """The previous round's SELECTED model, when there is one.

    The comparison figure colours what THIS round added on top of what was
    already chosen, so it needs the structure the round started from.
    """
    if getattr(r, "round_idx", 0) <= 0:
        return None
    prev = tree.round_node(r.root, r.round_idx - 1)
    report = load_json(prev / "evaluation") or {}
    winner = str((report.get("discrimination") or {}).get("winner") or "")
    models = [tree.model_node(prev, winner)] if winner else []
    for model in models + [prev / "model"]:
        sbml = load_text(model / "sbml")
        if sbml is not None:
            return sbml
    return None


def _per_candidate(cids: list[str], labels: dict, render) -> str:
    """One candidate open, the rest a click away.

    Rendering every candidate in full multiplies the default view by the
    candidate count. The first candidate stands for the shape; each other one
    is named in its fold's summary, so nothing is hidden, only deferred.
    """
    if not cids:
        return note("no candidates found in the record")
    out = []
    for i, cid in enumerate(cids):
        label = labels.get(cid, "")
        head = f'<h3>{esc(cid)}{esc(" — " + label) if label else ""}</h3>'
        content = render(cid)
        if i == 0:
            out.append(head + content)
        else:
            out.append(
                fold(f"{esc(cid)}{esc(' — ' + label) if label else ''}", content)
            )
    return "".join(out)


def _m3_shared(r: Round, cids: list[str]) -> str:
    """M3 for a candidate set, rendered ONCE per distinct build report.

    The candidates of a discrimination round usually share one construction
    reply and write no build report of their own, so reports are grouped by
    content: an identical one is stated once and named, and a candidate that
    recorded its own assumptions gets its own block.
    """
    shared = load_json(r.rnd / "model" / "build_report")
    groups: list[tuple[str, dict | None, list[str]]] = []
    for cid in cids:
        build = load_json(tree.model_node(r.rnd, cid) / "build_report") or shared
        key = json.dumps(build, sort_keys=True, default=str)
        for k, _b, ids in groups:
            if k == key:
                ids.append(cid)
                break
        else:
            groups.append((key, build, [cid]))
    if not groups:
        return (
            _m3_assumptions(shared)
            if shared
            else note("no candidates found in the record")
        )
    out = []
    for _key, build, ids in groups:
        if len(groups) == 1 and len(ids) > 1:
            out.append(
                note(
                    f"one construction reply built all {len(ids)} candidates, so "
                    f"these assumptions are shared by every one of them: "
                    + ", ".join(ids)
                )
            )
        elif len(groups) > 1:
            out.append(f"<h3>{esc(', '.join(ids))}</h3>")
        out.append(_m3_assumptions(build))
    return "".join(out)


def _m3_assumptions(build: dict | None) -> str:
    """M3 — every construction decision, least-confident first.

    The rationale is the point of this section: it is the argument the model
    rests on, so it sits directly under the decision at full reading size,
    above the evidence it cites. A tier demoted for want of a source is an
    engine enforcement, not an agent opinion, and is badged as such."""
    if build is None:
        return note(
            "no model/build_report — a supplied model carries no recorded assumptions"
        )
    decisions = [d for d in (build.get("decisions") or []) if isinstance(d, dict)]
    if not decisions:
        return note("the build report records no decisions")
    ranked = sorted(decisions, key=lambda d: _confidence(d.get("confidence"))[0])
    rows = []
    for d in ranked:
        conf_key, conf_txt = _confidence(d.get("confidence"))
        mark = (
            ' <span class="chip flag">asked</span>'
            if d.get("user_decision_required")
            else ""
        )
        cell = f'<span class="dtext">{esc(str(d.get("decision", "—")))}</span>{mark}'

        rationale = d.get("rationale")
        evidence = d.get("evidence")
        if rationale:
            lead, cut = clip_chars(rationale, DECISION_RATIONALE_CHARS)
            cell += f'<div class="rationale">{esc(lead)}</div>'
            if cut:
                cell += fold(
                    "full rationale",
                    f'<div class="rationale">{esc(str(rationale))}</div>',
                )
        cell += _evidence_lines(evidence)
        # pre-contract runs carry neither field; say so once, quietly
        missing = [
            n for n, v in (("rationale", rationale), ("evidence", evidence)) if not v
        ]
        if missing:
            cell += (
                f'<div class="prec">{" and ".join(missing)} not recorded '
                f"(pre-contract run)</div>"
            )

        alts = d.get("alternatives_considered")
        alts = ", ".join(alts) if isinstance(alts, list) else (alts or "")
        if alts:
            # Budgeted like the rationale: an argument whose first line is the
            # claim and the rest context.
            lead, cut = clip_chars(alts, DECISION_ALTERNATIVES_CHARS)
            cell += f'<div class="alts">alternatives: {esc(lead)}</div>'
            if cut:
                cell += fold(
                    "all alternatives considered",
                    f'<div class="alts">{esc(str(alts))}</div>',
                )
        # a decision may carry a caveat the agent did not escalate; showing it
        # here is the difference between a recorded doubt and a hidden one
        q = d.get("question")
        if q:
            lead, cut = clip_chars(q, DECISION_QUESTION_CHARS)
            cell += f'<span class="qnote">{esc(lead)}</span>'
            if cut:
                cell += fold(
                    "the whole question",
                    f'<div class="qnote">{esc(str(q))}</div>',
                )

        tier = _tier_cell(d.get("evidence_tier"))
        demoted = d.get("tier_demoted_from")
        if demoted:
            tier += (
                f'<span class="demoted">demoted from {esc(str(demoted))}: '
                f"no source attached</span>"
            )
        rows.append(
            [
                cell,
                tier,
                (
                    f'<span class="conf {"lo" if conf_key <= 0.5 else "hi"}">'
                    f"{esc(conf_txt)}</span>"
                ),
            ]
        )
    cols = [
        "assumption, rationale and evidence",
        "where the number came from",
        "confidence",
    ]
    lead = note(
        "sorted least-confident first: the top of this table is where "
        "the model is most likely to be wrong"
    ) + note(TIER_COLUMN_NOTE)
    if len(rows) > DECISIONS_SHOWN:
        return (
            lead
            + note(
                f"the {DECISIONS_SHOWN} least-confident of {len(rows)} recorded "
                f"decisions are shown; the rest, which the agent was more sure "
                f"of, are in the fold"
            )
            + table(cols, rows[:DECISIONS_SHOWN], cls="assumptions")
            + fold(
                f"all {len(rows)} decisions, least-confident first",
                table(cols, rows, cls="assumptions"),
            )
        )
    return lead + table(cols, rows, cls="assumptions")


def _s1_ladder(r: Round, cid: str | None) -> list[dict]:
    """The S1 gate ladder for one model (candidate `cid`, or the single
    model for None). Prefer the per-model gate verdicts (`gates/model_*`) — in a
    discrimination round every candidate runs its own ladder and the ledger
    rows cannot be attributed to a candidate. Fall back to the ledger."""
    out = []
    gates = tree.gates_node(r.rnd, cid)
    for gid in gates.children():
        if not gid.startswith("model_"):
            continue
        g = load_json(gates.child(gid))
        if isinstance(g, dict):
            g.setdefault("module", "model")
            out.append(g)
    if out:
        return out
    return [e for e in r.rows("gate") if str(e.get("module", "")).startswith("model")]


def _m4_checks(gates: list[dict]) -> str:
    """M4 — what the deterministic ladder already proved, and what it merely
    flagged. Advisory findings are candidate problems, not verdicts."""
    if not gates:
        return note("no S1 gate results recorded for this model")
    advisory = []
    for g in gates:
        findings = g.get("advisory_findings") or []
        if findings:
            advisory.append(
                f"{g.get('gate_id')}: " + ", ".join(str(f) for f in findings)
            )
        elif not g.get("blocking", True):
            advisory.append(f"{g.get('gate_id')}: {g.get('detail', '')}")
        elif not g.get("passed"):
            advisory.append(f"{g.get('gate_id')} FAILED: {g.get('detail', '')}")
    head = ""
    if advisory:
        head = (
            '<div class="flagbox"><b>Candidate problems to keep in view</b> '
            "— advisory findings, flagged and not excluded:<ul>"
            + "".join(f"<li>{esc(trunc(a, 220))}</li>" for a in advisory)
            + "</ul></div>"
        )
    rows = []
    for g in gates:
        passed = bool(g.get("passed"))
        verdict = (
            '<span class="chip pass">PASS</span>'
            if passed
            else '<span class="chip fail">FAIL</span>'
        )
        if not g.get("blocking", True):
            verdict += ' <span class="chip mute">advisory</span>'
        val, thr = g.get("value"), g.get("threshold")
        vt = (
            "—"
            if val is None and thr is None
            else f"{num(val)}{'' if thr is None else ' vs ' + num(thr)}"
        )
        rows.append(
            [
                f"<code>{esc(g.get('gate_id', '—'))}</code>",
                esc(g.get("tier", "—")),
                verdict,
                vt,
                esc(trunc(g.get("detail", ""), 120)),
            ]
        )
    n_ok = sum(1 for g in gates if g.get("passed"))
    return (
        head
        + kv([("ladder", f"{n_ok}/{len(gates)} checks passed")])
        + table(
            ["check", "tier", "verdict", "value vs threshold", "detail"],
            rows,
            cls="gates",
        )
    )


def _m5_sources(build: dict | None, rnd: Node | None = None) -> str:
    """Sources consulted — the agent's own list, and the literature the human
    handed over at staging, shown separately because its origin is a fact of
    the record: the person who staged the problem chose these."""
    out = ""
    sup = load_json(rnd / "supplied_evidence") if rnd is not None else None
    if sup and sup.get("items"):
        rows = "".join(
            f"<li><code>{esc(str(it.get('id', '?')))}</code> "
            f"{esc(str(it.get('source', '?')))} ({esc(str(it.get('year', '?')))})"
            f" [{esc(str(it.get('locator') or ''))}] — "
            f"{esc(str(it.get('supports') or ''))}"
            + (
                f" <span class='muted'>(document cached: {esc(str(it['cached_file']))})</span>"
                if it.get("cached_file")
                else ""
            )
            + "</li>"
            for it in sup["items"]
        )
        out += (
            "<p><b>Supplied by the human</b> (<code>intent.supplied_literature</code>, "
            "origin: human — the fence applied at the intent gate):</p>"
            f"<ul>{rows}</ul>"
        )
    if build is None:
        return out + note("no model/build_report — no sources declared")
    src = build.get("consulted_sources") or []
    if not src:
        return out + note("the construction agent declared no consulted sources")
    head = "<p><b>Declared by the construction agent:</b></p>" if out else ""
    return out + head + "<ul>" + "".join(f"<li>{esc(s)}</li>" for s in src) + "</ul>"


def _model_header(r: Round) -> str:
    testcase = (
        str(r.run_meta.get("project") or "")
        or Path(str(r.run_meta.get("testcase", ""))).name
        or r.store.run_id
    )
    when = r.run_start.get("ts") or "—"
    if r.is_md:
        badge = f"{len(r.cids)} candidate mechanisms built"
    else:
        badge = "model built — read before the scope gate"
    return (
        '<header class="hdr">'
        f'<h1>{esc(testcase)} — {esc(r.rnd.name.replace("_", " "))} — '
        "the model as built</h1>"
        f'<p class="sub">{esc(str(r.intent.get("question", "")))}</p>'
        f'<div class="badge flag">{esc(badge)}</div>'
        + kv(
            [
                ("run id", f"<code>{esc(r.store.run_id)}</code>"),
                ("date", esc(when)),
                (
                    "inference target",
                    f"<code>{esc(str(r.intent.get('inference_target', '—')))}</code>",
                ),
                ("backend", esc(str(r.run_meta.get("backend", "—")))),
                (
                    "this document",
                    "what was built, where the build needed a judgement call, and "
                    "what the deterministic checks already proved — the evidence for "
                    "the scope gate",
                ),
            ]
        )
        + "</header>"
    )


def render_model_report_html(rnd: Node) -> str:
    """The S1 'model built' report for the round node `rounds/round_k`.
    Never raises."""
    with rnd.store.reading():
        return _render(rnd)


def _render(rnd: Node) -> str:
    try:
        r = Round(rnd)
    except Exception as exc:
        return page(
            f"model report — {rnd.name}",
            f'<header class="hdr"><h1>{esc(rnd.name)}</h1>'
            f'<div class="badge fail">round could not be loaded</div>'
            f"</header>{note(str(exc))}",
        )

    try:
        body = _model_header(r)
    except Exception as exc:
        body = note(f"header unavailable: {trunc(exc, 160)}")

    def add(idx: str, title: str, fn) -> str:
        try:
            content = fn()
        except Exception as exc:
            content = note(
                f"section unavailable: {type(exc).__name__}: " f"{trunc(exc, 200)}"
            )
        return (
            f'<section class="sec" id="{idx.lower()}">'
            f'<h2><span class="n">{esc(idx)}</span>{esc(title)}</h2>'
            f"{content}</section>"
        )

    body += add("M0", "What you asked for", lambda: _m0_your_requests(r))

    if r.is_md:
        cids = r.cids
        labels = {
            c.get("id"): c.get("label", "") for c in r.candidates if isinstance(c, dict)
        }
        body += add(
            "M1",
            "The candidate mechanisms, compared",
            lambda: comparison_figure(
                [
                    (cid, sbml)
                    for cid in cids
                    if (sbml := load_text(tree.model_node(r.rnd, cid) / "sbml"))
                    is not None
                ],
                carried=_carried_model(r),
            )
            + _reactions_summary(r, cids)
            + fold(
                "each candidate on its own — full diagram, tables and parameters",
                _per_candidate(
                    cids,
                    labels,
                    lambda cid: _m1_glance(tree.model_node(r.rnd, cid), cid)
                    + _reactions_block(
                        tree.model_node(r.rnd, cid), r.rnd, anchor=False
                    ),
                ),
            ),
        )
        body += add(
            "M2",
            "Places needing your input",
            lambda: _m2_input_needed(load_json(r.rnd / "model" / "build_report")),
        )
        body += add(
            "M3",
            "Assumptions ranked by uncertainty",
            lambda: _m3_shared(r, cids),
        )
        body += add(
            "M4",
            "Deterministic check results",
            lambda: _per_candidate(
                cids, labels, lambda cid: _m4_checks(_s1_ladder(r, cid))
            ),
        )
    else:
        build = load_json(r.rnd / "model" / "build_report")
        supplied = build is None
        if supplied:
            body += note(
                "model/build_report is absent — this model was "
                "supplied rather than constructed, so it declares no "
                "decisions, no confidences and no sources. Sections "
                "M2, M3 and M5 say so; M1 and M4 are unaffected: the "
                "gates ran either way."
            )
        body += add(
            "M1",
            "The model at a glance",
            lambda: _m1_glance(r.rnd / "model")
            + _reactions_block(r.rnd / "model", r.rnd),
        )
        body += add("M2", "Places needing your input", lambda: _m2_input_needed(build))
        body += add(
            "M3", "Assumptions ranked by uncertainty", lambda: _m3_assumptions(build)
        )
        body += add(
            "M4",
            "Deterministic check results",
            lambda: _m4_checks(_s1_ladder(r, None)),
        )
        body += add("M5", "Sources consulted", lambda: _m5_sources(build, r.rnd))

    if r.is_md:
        body += add(
            "M5",
            "Sources consulted",
            lambda: _m5_sources(load_json(r.rnd / "model" / "build_report"), r.rnd),
        )

    body += (
        '<p class="colophon">Rendered by octomod.reporting at the end '
        "of S1, before the scope gate. No language model took part in "
        "producing this page; the agent's own words appear only as the "
        "quoted decision text in M2/M3.</p>"
    )
    testcase = (
        str(r.run_meta.get("project") or "")
        or Path(str(r.run_meta.get("testcase", ""))).name
        or r.store.run_id
    )
    return page(f"{testcase} — {rnd.name} — model built", body)


def _m0_your_requests(r) -> str:
    """What the HUMAN asked for, and what it changed.

    A redraft request is the one thing on this page that came from neither an
    agent nor a gate — it is the reader's own words — so it goes FIRST and is
    never folded away.
    """
    rows = []
    for row in getattr(r, "ledger", None) or []:
        if isinstance(row, dict) and row.get("human_redraft"):
            text = str(row.get("note", ""))
            text = text.split("redraft:", 1)[-1].strip() if "redraft:" in text else text
            rows.append(
                [
                    str(row.get("ts", ""))[11:19],
                    esc(str(row.get("module", ""))),
                    esc(str(row.get("role", ""))),
                    esc(text),
                ]
            )
    if not rows:
        return note(
            "no redraft was requested — every artifact on this page is the "
            "agents' own work, gated but unedited by a human"
        )
    return note(
        f"{len(rows)} change(s) below were asked for by YOU, not by a gate. The "
        f"agent was re-asked with your words and its own previous draft, and told "
        f"it may disagree in its build report rather than comply silently — so "
        f"check that what you asked for is what you got."
    ) + table(["time", "at gate", "agent", "what you asked for"], rows)


def model_report_path(rnd: Node) -> Path:
    """Where the round's rendered model report lives: a REAL file beside
    the record, `runs/<id>_reports/round_k/report/model_report.html`."""
    return rnd.store.reports_dir / rnd.name / "report" / "model_report.html"


def write_model_report_html(rnd: Node) -> Path:
    """Render the round `rnd` and write it to `model_report_path(rnd)`;
    returns that path."""
    path = model_report_path(rnd)
    html_text = render_model_report_html(rnd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text)
    return path
