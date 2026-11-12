"""SBML rendered two ways: as species, reaction and parameter tables, and as a
network diagram.

Shared by the round report (section 3) and the model report (M1), which is why
this is its own module rather than part of either. The diagram prefers graphviz
for an SBGN-lite layout and falls back to a matplotlib circular layout when the
binary is absent, so the same document renders on a machine without dot.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from octomod.reporting import render
from octomod.reporting.figures import (
    figure,
    responsive_svg,
)
from octomod.reporting.html import (
    esc,
    load_json,
    note,
    num,
    table,
    trunc,
)

if TYPE_CHECKING:
    from octomod.result.node import Node

_MAX_NETWORK_SPECIES = 20  # graphviz SBGN-lite layout


_MAX_CIRCULAR_SPECIES = 12  # matplotlib fallback layout


def _sbml_model(sbml: str):
    import libsbml

    doc = libsbml.readSBMLFromString(sbml)
    return doc.getModel()


def _rate_law(kl) -> str:
    import libsbml

    return libsbml.formulaToString(kl.getMath()) if kl and kl.getMath() else "?"


def _model_tables(sbml: str, parameters: list | None = None) -> str:
    """The model as three compact tables: species, reactions, parameters.

    Species initials and parameter values come from render.species_initial /
    render.parameter_display, the assignment-aware helpers: the raw SBML
    fields read NaN for assignment-based species."""
    m = _sbml_model(sbml)
    if m is None:
        raise ValueError("SBML did not parse")

    rows = [
        [
            f"<code>{esc(m.getSpecies(i).getId())}</code>",
            esc(render.species_initial(m, m.getSpecies(i).getId())),
        ]
        for i in range(m.getNumSpecies())
    ]
    out = ["<h4>Species</h4>", table(["id", "initial"], rows, cls="model")]

    rows = []
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
        mods = [rxn.getModifier(j).getSpecies() for j in range(rxn.getNumModifiers())]
        arrow = f"{esc(lhs)} &rarr; {esc(rhs)}"
        if mods:
            arrow += (
                '<span class="mods">modifiers: '
                + ", ".join(f"<code>{esc(x)}</code>" for x in mods)
                + "</span>"
            )
        rows.append(
            [
                f"<code>{esc(rxn.getId() or f'r{i}')}</code>",
                arrow,
                f"<code>{esc(_rate_law(rxn.getKineticLaw()))}</code>",
            ]
        )
    out += [
        "<h4>Reactions</h4>",
        table(["id", "reaction", "rate law"], rows, cls="model"),
    ]

    est = {
        p["id"]: p for p in (parameters or []) if isinstance(p, dict) and p.get("id")
    }
    rows = []
    for i in range(m.getNumParameters()):
        pid = m.getParameter(i).getId()
        value, kind = render.parameter_display(m, pid)
        if pid in est and est[pid].get("estimate"):
            e = est[pid]
            status = f"<b>ESTIMATED in [{num(e.get('lb'))}, " f"{num(e.get('ub'))}]</b>"
        elif kind == "derived":
            status = '<span class="derived">derived (diagnostic, no dynamics)</span>'
        else:
            status = '<span class="mute">fixed</span>'
        rows.append([f"<code>{esc(pid)}</code>", f"<code>{esc(value)}</code>", status])
    out += [
        "<h4>Parameters</h4>",
        table(["id", "value / assignment", "status"], rows, cls="model"),
    ]
    return "".join(out)


def model_tables_or_note(model: Node, sbml: str | None) -> str:
    """The listing for the model record `model` (its `parameters` carry the
    agent's rationales) of the SBML `sbml`."""
    if sbml is None:
        return note("model/sbml is missing — no species, reaction or parameter listing")
    params = load_json(model / "parameters")
    try:
        return _model_tables(sbml, params if isinstance(params, list) else [])
    except Exception as exc:
        return note(
            f"model listing unavailable: {type(exc).__name__}: " f"{trunc(exc, 160)}"
        )


def reaction_count(sbml: str) -> int | None:
    try:
        m = _sbml_model(sbml)
        return int(m.getNumReactions()) if m is not None else None
    except Exception:
        return None


def _dot_binary() -> str | None:
    import shutil

    for cand in (shutil.which("dot"), "/opt/homebrew/bin/dot", "/usr/local/bin/dot"):
        if cand and Path(cand).exists():
            return cand
    return None


def _dot_quote(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _dot_label(text, width: int = 30) -> str:
    """Escape for DOT and wrap onto centred lines (a rate law is a node's own
    label, and an unwrapped one widens the node past the diagram).

    Line breaks belong to this function: callers pass a real newline or a list
    of lines. The text is split first, each line quoted, and the lines joined
    with DOT's `\\n` escape last, so `_dot_quote` never doubles the separator.
    A literal `\\n` in the text is also read as a break, so a label cannot
    carry a backslash followed by `n` (no species, reaction or candidate id or
    rate law does). Other backslashes are escaped normally.
    """
    import textwrap

    parts = (
        [str(x) for x in text]
        if isinstance(text, (list, tuple))
        else str(text).replace("\\n", "\n").split("\n")
    )
    lines: list[str] = []
    for part in parts:
        lines += textwrap.wrap(
            part, width=width, break_long_words=False, break_on_hyphens=False
        ) or [part]
    # the separator is added AFTER quoting, so `_dot_quote` never sees it
    return "\\n".join(_dot_quote(line) for line in lines)


def _network_dot(sbml: str) -> str:
    """SBGN-lite as a DOT digraph: species are rounded boxes, every reaction is
    a small square process node carrying its rate law, arrows run
    reactant → process → product and modifiers arrive at the process node on a
    dashed arc. This is the reading a modeller expects; the mermaid view in
    `report_md` edge-labels the same information but cannot show a process node."""
    m = _sbml_model(sbml)
    if m is None:
        raise ValueError("SBML did not parse")
    sids = [m.getSpecies(i).getId() for i in range(m.getNumSpecies())]
    lines = [
        "digraph model {",
        '  rankdir=LR; bgcolor="transparent"; splines=true; overlap=false;',
        "  nodesep=0.6; ranksep=0.9;",
        '  node [fontname="Helvetica,Arial,sans-serif", fontsize=10];',
        '  edge [fontname="Helvetica,Arial,sans-serif", fontsize=9, '
        'color="#5b6570", arrowsize=0.7, penwidth=0.9];',
    ]
    for sid in sids:
        lines.append(
            f'  "{_dot_quote(sid)}" [shape=box, style="rounded,filled", '
            f'fillcolor="#eef3f8", color="#42607d", fontcolor="#16324a", '
            f'penwidth=1.2, margin="0.14,0.08"];'
        )
    for i in range(m.getNumReactions()):
        rxn = m.getReaction(i)
        rid = rxn.getId() or f"r{i}"
        pid = f"__p_{rid}"
        rate = trunc(_rate_law(rxn.getKineticLaw()), 90)
        # the law is the process node's own label, not an edge label or an
        # xlabel: only a real label takes part in layout, so only a real
        # label is guaranteed not to collide with a node
        lines.append(
            f'  "{_dot_quote(pid)}" [shape=box, style=filled, '
            f'fillcolor="#f1f3f5", color="#9aa1a7", fontcolor="#3d4750", '
            f'fontsize=9, penwidth=0.8, margin="0.10,0.05", '
            f'label="{_dot_label(rate)}"];'
        )
        reactants = [
            rxn.getReactant(j).getSpecies() for j in range(rxn.getNumReactants())
        ]
        products = [rxn.getProduct(j).getSpecies() for j in range(rxn.getNumProducts())]
        modifiers = [
            rxn.getModifier(j).getSpecies() for j in range(rxn.getNumModifiers())
        ]
        if not reactants:  # (source) — degradation's mirror image
            src = f"__src_{rid}"
            lines.append(
                f'  "{_dot_quote(src)}" [shape=circle, width=0.10, '
                f'label="", color="#a8b0b8", penwidth=0.9];'
            )
            reactants = [src]
        if not products:  # (sink)
            snk = f"__snk_{rid}"
            lines.append(
                f'  "{_dot_quote(snk)}" [shape=circle, width=0.10, '
                f'label="", color="#a8b0b8", penwidth=0.9];'
            )
            products = [snk]
        for rsp in reactants:
            lines.append(
                f'  "{_dot_quote(rsp)}" -> "{_dot_quote(pid)}" ' f"[arrowhead=none];"
            )
        for psp in products:
            lines.append(f'  "{_dot_quote(pid)}" -> "{_dot_quote(psp)}";')
        for mod in modifiers:
            lines.append(
                f'  "{_dot_quote(mod)}" -> "{_dot_quote(pid)}" '
                f'[style=dashed, arrowhead=odot, color="#8a7a4e", '
                f"constraint=false];"
            )
    lines.append("}")
    return "\n".join(lines)


# Comparing candidate structures: one diagram over the whole candidate set,
# where colour says what varies and nothing else.
CMP_SHARED_FILL, CMP_SHARED_LINE = "#f1f3f5", "#9aa1a7"
CMP_LAW_FILL, CMP_LAW_LINE, CMP_LAW_INK = "#FEF3C7", "#B45309", "#92400E"
CMP_SOME_FILL, CMP_SOME_LINE, CMP_SOME_INK = "#F3EEFB", "#6D28D9", "#4C1D95"
CMP_NEW_FILL, CMP_NEW_LINE, CMP_NEW_INK = "#E7F5EF", "#047857", "#065F46"


def _structure(sbml: str) -> tuple[list[str], dict]:
    """Species ids, and every reaction as (reactants, products, modifiers, law).

    The law is part of the identity on purpose: an axis often modifies a rate
    law rather than adding a reaction, and a comparison that ignores the law
    calls two different mechanisms the same model.
    """
    import libsbml

    m = _sbml_model(sbml)
    if m is None:
        raise ValueError("SBML did not parse")
    species = [m.getSpecies(i).getId() for i in range(m.getNumSpecies())]
    reactions = {}
    for i in range(m.getNumReactions()):
        rxn = m.getReaction(i)
        kl = rxn.getKineticLaw()
        reactions[rxn.getId() or f"r{i}"] = {
            "reactants": [
                rxn.getReactant(j).getSpecies() for j in range(rxn.getNumReactants())
            ],
            "products": [
                rxn.getProduct(j).getSpecies() for j in range(rxn.getNumProducts())
            ],
            "modifiers": [
                rxn.getModifier(j).getSpecies() for j in range(rxn.getNumModifiers())
            ],
            "law": (
                libsbml.formulaToString(kl.getMath()) if kl and kl.getMath() else "?"
            ),
        }
    return species, reactions


def compare_models(models: list[tuple[str, str]], carried: str | None = None) -> dict:
    """What actually differs across a candidate set.

    `models` is [(candidate id, SBML)]. `carried` is the previous round's
    selected model, when there is one: anything absent from it is NEW this
    round, which is the other thing colour is asked to show.
    """
    ids, parsed = [], {}
    for cid, sbml in models:
        try:
            parsed[cid] = _structure(sbml)
            ids.append(cid)
        except Exception:  # a candidate that will not parse is left out, not fatal
            continue
    prev_sp, prev_rx = ([], {})
    if carried:
        try:
            prev_sp, prev_rx = _structure(carried)
        except Exception:
            prev_sp, prev_rx = [], {}

    species: dict[str, dict] = {}
    for sid in sorted({s for sp, _ in parsed.values() for s in sp}):
        holders = [c for c in ids if sid in parsed[c][0]]
        species[sid] = {
            "in": holders,
            "all": len(holders) == len(ids),
            "new": bool(carried) and sid not in prev_sp,
        }
    reactions: dict[str, dict] = {}
    for rid in sorted({r for _, rx in parsed.values() for r in rx}):
        holders = [c for c in ids if rid in parsed[c][1]]
        laws = {c: parsed[c][1][rid]["law"] for c in holders}
        shape = next(iter(holders), None)
        reactions[rid] = {
            "in": holders,
            "all": len(holders) == len(ids),
            "laws": laws,
            "law_differs": len(set(laws.values())) > 1,
            "new": bool(carried)
            and (rid not in prev_rx or prev_rx[rid]["law"] not in set(laws.values())),
            "shape": parsed[shape][1][rid] if shape else None,
        }
    varies = [r for r, d in reactions.items() if d["law_differs"] or not d["all"]]
    topology = [r for r, d in reactions.items() if not d["all"]] + [
        s for s, d in species.items() if not d["all"]
    ]
    return {
        "ids": ids,
        "species": species,
        "reactions": reactions,
        "varies": varies,
        "differ_by": (
            "nothing — every candidate has the same species, topology and laws"
            if not varies
            else (
                "topology and laws"
                if topology
                else "rate laws only — same species, same topology"
            )
        ),
        "carried": bool(carried),
    }


def _cmp_colours(cid: str, ids: list[str]) -> tuple[str, str, str]:
    """One hue per candidate, for elements only that candidate carries."""
    palette = [
        ("#F3EEFB", "#6D28D9", "#4C1D95"),
        ("#E6F1FA", "#1D6FA5", "#0F4C75"),
        ("#FDEEF3", "#BE123C", "#8C0E2C"),
        ("#EFF6E8", "#4D7C0F", "#3F6212"),
        ("#FDF2E3", "#B45309", "#92400E"),
    ]
    return palette[(ids.index(cid) if cid in ids else 0) % len(palette)]


def _overlay_dot(diff: dict) -> str:
    """One digraph over the union of the candidates, coloured by what varies.

    The diagram says where they differ; `comparison_table` says how. Every
    reaction label names the reaction and its status, never the rate law.
    """
    ids = diff["ids"]
    lines = [
        "digraph compare {",
        '  rankdir=LR; bgcolor="transparent"; splines=true; overlap=false;',
        "  nodesep=0.6; ranksep=0.9;",
        '  node [fontname="Helvetica,Arial,sans-serif", fontsize=10];',
        '  edge [fontname="Helvetica,Arial,sans-serif", fontsize=9, '
        'color="#5b6570", arrowsize=0.7, penwidth=0.9];',
    ]
    for sid, d in diff["species"].items():
        if not d["all"] and len(d["in"]) == 1:
            fill, line, ink = _cmp_colours(d["in"][0], ids)
        elif not d["all"]:
            fill, line, ink = CMP_SOME_FILL, CMP_SOME_LINE, CMP_SOME_INK
        elif d["new"]:
            fill, line, ink = CMP_NEW_FILL, CMP_NEW_LINE, CMP_NEW_INK
        else:
            fill, line, ink = "#eef3f8", "#42607d", "#16324a"
        tag = "" if d["all"] else "\n(" + ", ".join(d["in"]) + ")"
        lines.append(
            f'  "{_dot_quote(sid)}" [shape=box, style="rounded,filled", '
            f'fillcolor="{fill}", color="{line}", fontcolor="{ink}", '
            f'penwidth={2.0 if not d["all"] or d["new"] else 1.2}, '
            f'margin="0.14,0.08", label="{_dot_label(sid + tag)}"];'
        )
    for rid, d in diff["reactions"].items():
        shape = d["shape"] or {}
        pid = f"__p_{rid}"
        if d["law_differs"]:
            fill, line, ink = CMP_LAW_FILL, CMP_LAW_LINE, CMP_LAW_INK
            label = f"{rid}\nlaw differs — see the table"
            pen = 2.2
        elif not d["all"]:
            fill, line, ink = (
                _cmp_colours(d["in"][0], ids)
                if len(d["in"]) == 1
                else (CMP_SOME_FILL, CMP_SOME_LINE, CMP_SOME_INK)
            )
            label = f"{rid}\nonly in {', '.join(d['in'])} — see the table"
            pen = 2.2
        elif d["new"]:
            fill, line, ink = CMP_NEW_FILL, CMP_NEW_LINE, CMP_NEW_INK
            label = f"{rid}\nnew this round — see the table"
            pen = 2.0
        else:
            fill, line, ink = CMP_SHARED_FILL, CMP_SHARED_LINE, "#3d4750"
            label = f"{rid}\nshared by every candidate"
            pen = 0.8
        lines.append(
            f'  "{_dot_quote(pid)}" [shape=box, style=filled, '
            f'fillcolor="{fill}", color="{line}", fontcolor="{ink}", '
            f'fontsize=9, penwidth={pen}, margin="0.10,0.05", '
            f'label="{_dot_label(label)}"];'
        )
        reactants = list(shape.get("reactants") or [])
        products = list(shape.get("products") or [])
        if not reactants:
            src = f"__src_{rid}"
            lines.append(
                f'  "{_dot_quote(src)}" [shape=circle, width=0.10, label="", '
                f'color="#a8b0b8", penwidth=0.9];'
            )
            reactants = [src]
        if not products:
            snk = f"__snk_{rid}"
            lines.append(
                f'  "{_dot_quote(snk)}" [shape=circle, width=0.10, label="", '
                f'color="#a8b0b8", penwidth=0.9];'
            )
            products = [snk]
        for rsp in reactants:
            lines.append(
                f'  "{_dot_quote(rsp)}" -> "{_dot_quote(pid)}" [arrowhead=none];'
            )
        for psp in products:
            lines.append(f'  "{_dot_quote(pid)}" -> "{_dot_quote(psp)}";')
        for mod in shape.get("modifiers") or []:
            lines.append(
                f'  "{_dot_quote(mod)}" -> "{_dot_quote(pid)}" '
                f'[style=dashed, arrowhead=odot, color="#8a7a4e", '
                f"constraint=false];"
            )
    lines.append("}")
    return "\n".join(lines)


def _graphviz_network_svg(sbml: str) -> str | None:
    """Render the DOT graph with the system graphviz. Returns inline SVG, or
    None on any failure — the caller then falls back to the matplotlib layout,
    so a missing/broken graphviz costs a nicer picture, never the report."""
    import subprocess

    dot = _dot_binary()
    if dot is None:
        return None
    try:
        src = _network_dot(sbml)
        proc = subprocess.run(
            [dot, "-Tsvg"], input=src, capture_output=True, text=True, timeout=25
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        out = proc.stdout
        start = out.find("<svg")
        return responsive_svg(out[start:]) if start >= 0 else None
    except Exception:
        return None


def _render_dot(src: str) -> str | None:
    """DOT to inline SVG, or None on any failure."""
    import subprocess

    dot = _dot_binary()
    if dot is None:
        return None
    try:
        proc = subprocess.run(
            [dot, "-Tsvg"], input=src, capture_output=True, text=True, timeout=25
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        start = proc.stdout.find("<svg")
        return responsive_svg(proc.stdout[start:]) if start >= 0 else None
    except Exception:
        return None


def comparison_figure(models: list[tuple[str, str]], carried: str | None = None) -> str:
    """ONE diagram of a candidate set, with colour saying what varies.

    Grey is shared by every candidate. Amber marks a reaction whose RATE LAW
    differs — the laws themselves go in the table below, because a diagram can
    say where they differ and a table can say how. A colour of its own marks an
    element only one candidate carries, and green marks what this round added
    on top of the previous round's selection.
    """
    diff = compare_models(models, carried)
    if not diff["ids"]:
        return note("no candidate models could be read")
    svg = _render_dot(_overlay_dot(diff))
    caption = (
        f"{len(diff['ids'])} candidates, drawn once. They differ by "
        f"{diff['differ_by']}."
    )
    body = svg or note(
        "graphviz is not available, so the shared diagram could not be drawn; "
        "the comparison below is complete without it"
    )
    return (
        f'<figure class="fig net">{body}'
        f"<figcaption>{esc(caption)}</figcaption></figure>"
        + _comparison_legend(diff)
        + comparison_table(models, carried)
    )


def _comparison_legend(diff: dict) -> str:
    items = [
        (CMP_SHARED_FILL, CMP_SHARED_LINE, "shared by every candidate"),
    ]
    if any(d["law_differs"] for d in diff["reactions"].values()):
        items.append((CMP_LAW_FILL, CMP_LAW_LINE, "same reaction, different rate law"))
    if any(not d["all"] for d in diff["reactions"].values()) or any(
        not d["all"] for d in diff["species"].values()
    ):
        items.append((CMP_SOME_FILL, CMP_SOME_LINE, "present in some candidates only"))
    if diff["carried"]:
        items.append((CMP_NEW_FILL, CMP_NEW_LINE, "added this round"))
        items.append(("#eef3f8", "#42607d", "carried from the previous round"))
    swatches = "".join(
        f'<span class="swatch"><i style="background:{f};border-color:{ln}"></i>'
        f"{esc(t)}</span>"
        for f, ln, t in items
    )
    return f'<div class="legend">{swatches}</div>'


def comparison_table(models: list[tuple[str, str]], carried: str | None = None) -> str:
    """The rate laws side by side, one row per reaction that varies.

    Candidates that differ only in rate laws draw identical diagrams, so this
    table is where they become comparable.
    """
    diff = compare_models(models, carried)
    ids = diff["ids"]
    if not ids:
        return ""
    if not diff["varies"]:
        return note(
            "every candidate has the same species, the same topology and the "
            "same rate laws — the set does not discriminate anything"
        )
    rows = []
    for rid in diff["varies"]:
        d = diff["reactions"][rid]
        cells = [f"<code>{esc(rid)}</code>"]
        for cid in ids:
            law = d["laws"].get(cid)
            cells.append(
                f"<code>{esc(law)}</code>"
                if law
                else '<span class="none">absent</span>'
            )
        rows.append(cells)
    # table() escapes headers, so they are plain ids, not markup
    return table(["reaction", *ids], rows)


def network_figure(sbml: str, title: str = "") -> str:
    """The reaction network. Graphviz draws it when available (SBGN-lite:
    species boxes, reaction process nodes, dashed modifier arcs); the manual
    circular matplotlib layout is the fallback."""
    try:
        m = _sbml_model(sbml)
        n_species = int(m.getNumSpecies()) if m is not None else 0
    except Exception:
        n_species = 0
    if n_species > _MAX_NETWORK_SPECIES:
        return note(
            f"network figure skipped: {n_species} species exceeds the "
            f"{_MAX_NETWORK_SPECIES}-species cap for a legible diagram "
            f"(the reaction listing above is complete)"
        )
    svg = _graphviz_network_svg(sbml)
    if svg:
        head = f"<h4>{esc(title)}</h4>" if title else ""
        return (
            f'<figure class="fig net">{head}{svg}'
            "<figcaption>Reaction network from the model's SBML (graphviz "
            "layout): rounded blue boxes are species, grey boxes are "
            "reactions carrying their rate law, dashed arcs are "
            "modifiers.</figcaption></figure>"
        )
    return _network_figure_mpl(sbml, title)


def _network_figure_mpl(sbml: str, title: str = "") -> str:
    """Fallback: manual circular layout. Small models only — a hairball is a
    worse view than an honest note."""

    def build(plt):
        m = _sbml_model(sbml)
        if m is None:
            raise ValueError("SBML did not parse")
        sids = [m.getSpecies(i).getId() for i in range(m.getNumSpecies())]
        if not sids:
            raise ValueError("model declares no species")
        if len(sids) > _MAX_CIRCULAR_SPECIES:
            raise ValueError(
                f"graphviz unavailable and {len(sids)} species exceeds the "
                f"{_MAX_CIRCULAR_SPECIES}-species cap of the circular fallback "
                f"layout"
            )

        n = len(sids)
        if n == 1:
            pos = {sids[0]: np.array([0.0, 0.0])}
        else:
            ang = np.linspace(np.pi / 2, np.pi / 2 + 2 * np.pi, n, endpoint=False)
            pos = {
                s: np.array([np.cos(a), np.sin(a)])
                for s, a in zip(sids, ang, strict=False)
            }

        fig, ax = plt.subplots(figsize=(6.6, 5.6))
        ax.set_aspect("equal")
        ax.axis("off")
        ax.grid(False)

        def _outer(node: str, k: float = 1.55) -> np.ndarray:
            p = pos[node]
            r = float(np.linalg.norm(p))
            u = p / r if r > 1e-9 else np.array([1.0, 0.0])
            return p + 0.55 * u if r > 1e-9 else np.array([0.0, -1.0]) * k

        def arrow(a, b, label, dashed=False, color="#333", rad=0.16):
            from matplotlib.patches import FancyArrowPatch

            ax.add_patch(
                FancyArrowPatch(
                    tuple(a),
                    tuple(b),
                    connectionstyle=f"arc3,rad={rad}",
                    arrowstyle="-|>",
                    mutation_scale=9,
                    linewidth=1.0,
                    linestyle="--" if dashed else "-",
                    color=color,
                    shrinkA=13,
                    shrinkB=13,
                    zorder=1,
                )
            )
            if label:
                mid = (np.asarray(a) + np.asarray(b)) / 2.0
                d = np.asarray(b) - np.asarray(a)
                perp = np.array([-d[1], d[0]])
                nrm = float(np.linalg.norm(perp)) or 1.0
                mid = mid + perp / nrm * (0.30 + rad)
                ax.text(
                    mid[0],
                    mid[1],
                    trunc(label, 30),
                    fontsize=6.4,
                    ha="center",
                    va="center",
                    color=color,
                    zorder=3,
                    bbox=dict(
                        boxstyle="round,pad=0.18", fc="white", ec="#dddddd", lw=0.4
                    ),
                )

        for i in range(m.getNumReactions()):
            rxn = m.getReaction(i)
            rate = _rate_law(rxn.getKineticLaw())
            reactants = [
                rxn.getReactant(j).getSpecies() for j in range(rxn.getNumReactants())
            ]
            products = [
                rxn.getProduct(j).getSpecies() for j in range(rxn.getNumProducts())
            ]
            modifiers = [
                rxn.getModifier(j).getSpecies() for j in range(rxn.getNumModifiers())
            ]
            reactants = [r for r in reactants if r in pos]
            products = [p for p in products if p in pos]
            if reactants and products:
                pairs = [(pos[r], pos[p], True) for r in reactants for p in products]
            elif products:  # (source) -> P
                pairs = [(_outer(p), pos[p], False) for p in products]
            elif reactants:  # R -> (sink)
                pairs = [(pos[r], _outer(r), False) for r in reactants]
            else:
                pairs = []
            for a, b, real in pairs:
                if not real:
                    ax.plot(
                        [a[0]],
                        [a[1]],
                        marker="o",
                        ms=4,
                        mfc="white",
                        mec="#999999",
                        zorder=2,
                    )
                arrow(a, b, rate, rad=0.16 + 0.06 * (i % 3))
            for mod in modifiers:
                if mod in pos:
                    for p in products:
                        arrow(
                            pos[mod],
                            pos[p],
                            "modifies",
                            dashed=True,
                            color="#8a8a8a",
                            rad=-0.28,
                        )

        for s, p in pos.items():
            ax.plot(
                [p[0]],
                [p[1]],
                marker="o",
                ms=26,
                mfc="#f2f5f8",
                mec="#42607d",
                mew=1.1,
                zorder=4,
            )
            ax.text(
                p[0],
                p[1],
                s,
                fontsize=7.5,
                ha="center",
                va="center",
                color="#16324a",
                zorder=5,
            )

        lim = 1.95
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        if title:
            ax.set_title(title)
        return fig

    return figure(
        build,
        caption="Reaction network drawn from the model's SBML (circular layout; "
        "modifiers dashed).",
        fallback="network figure skipped",
    )


def model_counts(sbml: str) -> list[tuple[str, str]]:
    m = _sbml_model(sbml)
    if m is None:
        raise ValueError("SBML did not parse")
    return [
        ("species", str(m.getNumSpecies())),
        ("reactions", str(m.getNumReactions())),
        ("parameters", str(m.getNumParameters())),
        ("compartments", str(m.getNumCompartments())),
    ]
