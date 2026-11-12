"""DOT labels: line breaks belong to `_dot_label` and are never double-escaped.

  1. a break is one escape, never two; backslashes in the content still escape;
  2. wrapping still happens within each line;
  3. the emitted DOT of the real figure over four candidates is not double-escaped;
  4. no label carries a rate law: the diagram says where models differ, the table how;
  5. the wrong ordering (quote the whole string, then join) fails the same assertion;
  6. with no `dot` binary the network figure is drawn by the circular matplotlib
     fallback, in the model report's M1 section too, and a model past that
     layout's species cap gets a note naming the cap.

    uv run python tests/dot_label_unit.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.reporting.sbml_view import (  # noqa: E402
    _dot_label,
    _dot_quote,
    _overlay_dot,
    compare_models,
)
from octomod.result import node as tree  # noqa: E402
from tests._record import rnd, run_root, temp_record  # noqa: E402

# The user's runs folder, deliberately not redirected by the battery: this
# reads an existing run, not one this suite makes.
USER_RUNS = config.USER_RUNS_DIR

# In a DOT file, `\n` inside a quoted label is a line break and `\\n` is a
# literal backslash followed by n. Written here as Python so the intent is
# unmistakable: BREAK is two characters, LITERAL is three.
BREAK = "\\" + "n"
LITERAL = "\\\\" + "n"


def _labels(dot: str) -> list[str]:
    return re.findall(r'label="((?:[^"\\]|\\.)*)"', dot)


def _live_models() -> list[tuple[str, str]]:
    """live_blind_3's candidate SBMLs off its record — (id, text) per
    candidate; empty when the live run is not on this machine."""
    root = run_root("live_blind_3", USER_RUNS)
    if not root.exists():
        return []
    r0 = rnd(root, 0)
    return [
        (cid, (tree.model_node(r0, cid) / "sbml").text())
        for cid in tree.candidate_ids(r0)
        if (tree.model_node(r0, cid) / "sbml").exists()
    ]


def test_a_break_is_one_escape_and_never_two() -> None:
    for text, want_lines in (
        ("J5\nlaw differs — see the table", 2),
        ("one line only", 1),
        (["first", "second", "third"], 3),
        ("a\nb\nc", 3),
    ):
        out = _dot_label(text, width=99)
        assert LITERAL not in out, f"double-escaped: {out!r}"
        assert out.count(BREAK) == want_lines - 1, (out, want_lines)

    # a caller that embeds the DOT escape itself still gets one break
    assert _dot_label("J5" + BREAK + "law differs", width=99) == _dot_label(
        "J5\nlaw differs", width=99
    ), "a literal escape in the text must normalise to a break, not double up"

    # a backslash in the CONTENT is still escaped; only the separator is not
    assert _dot_quote("a\\b") == "a\\\\b"
    assert _dot_label("a\\b", width=99) == "a\\\\b"
    # backslash-t, not backslash-n: doubled, and not read as a break
    assert _dot_label("C:\\temp", width=99) == "C:\\\\temp"

    # The cost of normalising a literal `\n` to a break: a label cannot carry a
    # real backslash followed by `n`. Labels here are ids and SBML rate laws,
    # which never contain a backslash.
    assert (
        _dot_label("a\\next", width=99).count(BREAK) == 1
    ), "documented consequence: backslash-n in content reads as a break"
    print(
        f"  helper        breaks emit one {BREAK!r}; other content backslashes "
        f"still escape"
    )


def test_wrapping_still_happens_within_each_line() -> None:
    """Long lines still wrap: an unwrapped rate law widens a node past the diagram."""
    long_law = "cell * k_prod_kina * KinA_p * PreC * some_other_factor * more"
    out = _dot_label(f"R5b (M3)\n{long_law}", width=30)
    assert out.count(BREAK) >= 2, f"the long line was not wrapped: {out!r}"
    assert LITERAL not in out
    for piece in out.split(BREAK):
        assert len(piece) <= 40, f"a line came out {len(piece)} chars: {piece!r}"
    print("  wrapping      long laws still wrap, and every wrap is a real break")


def test_the_real_figure_over_four_real_candidates() -> None:
    """`_overlay_dot` on four saved candidates that differ in topology and laws."""
    models = _live_models()
    if len(models) < 2:  # pragma: no cover - the live run is not in the repo
        print("  (live_blind_3 not on disk — skipping the real-figure assertions)")
        return
    diff = compare_models(models)
    dot = _overlay_dot(diff)

    assert LITERAL not in dot, (
        "the emitted DOT contains a literal backslash-n, which Graphviz draws "
        "as text — the defect this suite exists for:\n  "
        + next((line for line in dot.splitlines() if LITERAL in line), "?").strip()[
            :160
        ]
    )
    labels = _labels(dot)
    assert labels, "no labels in the figure at all"
    multi = [x for x in labels if BREAK in x]
    assert multi, (
        "no label in this figure has a line break, so this run does not "
        "exercise the line-break branches"
    )
    # the law_differs branch, by its own words
    assert any(
        "law differs" in x and BREAK in x for x in labels
    ), f"the law_differs branch is not drawn on two lines: {multi[:3]}"
    print(
        f"  real figure   {len(labels)} labels over {len(models)} candidates, "
        f"{len(multi)} on multiple lines, zero double-escaped"
    )


def test_no_label_carries_a_rate_law() -> None:
    """A label names a reaction and its status, never a rate law (the table's job)."""
    models = _live_models()
    if len(models) < 2:  # pragma: no cover
        print("  (live_blind_3 not on disk — skipping)")
        return
    diff = compare_models(models)
    labels = _labels(_overlay_dot(diff))
    assert labels

    # a rate law is arithmetic: an operator between identifiers. Reaction ids
    # and status words carry none.
    law_like = [x for x in labels if re.search(r"[A-Za-z_)\]]\s*[*/+]\s*[A-Za-z_(]", x)]
    assert not law_like, (
        "a label still carries a rate law, which belongs in the table:\n  "
        + "\n  ".join(law_like[:3])
    )
    # and no label is truncated
    assert not [x for x in labels if x.rstrip().endswith("…")], labels

    # every REACTION label states a status a reader can act on
    statuses = ("see the table", "shared by every candidate", "new this round")
    rx = [x for x in labels if x.split(BREAK)[0] in diff["reactions"]]
    assert rx, f"no reaction labels found among {labels}"
    for lab in rx:
        assert any(s in lab for s in statuses), f"no status on {lab!r}"
    print(
        f"  no laws       {len(rx)} reaction labels, each a status, none "
        f"carrying arithmetic"
    )


def test_it_refuses_the_wrong_ordering() -> None:
    """The wrong ordering (quote the whole string, then join) fails the same assertion."""
    import textwrap

    def wrong_dot_label(text: str, width: int = 30) -> str:
        lines = textwrap.wrap(
            str(text), width=width, break_long_words=False, break_on_hyphens=False
        ) or [str(text)]
        return BREAK.join(_dot_quote(line) for line in lines)

    # a caller passing the DOT escape already in the text
    old = wrong_dot_label("J5" + BREAK + "law differs — see the table", width=99)
    assert LITERAL in old, (
        "the reproduction of the wrong ordering did not double-escape, so "
        "this suite proves nothing about the right one"
    )
    new = _dot_label("J5\nlaw differs — see the table", width=99)
    assert LITERAL not in new and new.count(BREAK) == 1
    print(
        "  wrong order   quoting then joining double-escapes; the assertion catches it"
    )


def test_without_graphviz_the_network_falls_back_to_matplotlib() -> None:
    """With `dot` absent the network is still drawn, by the circular layout."""

    import antimony

    from octomod.reporting import sbml_view
    from octomod.reporting.model_report import _m1_glance

    toy = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab" / "model.xml"
    sbml = toy.read_text()
    chain = "; ".join(f"J{i}: A{i} -> A{i + 1}; k*A{i}" for i in range(12))
    antimony.loadAntimonyString(f"model big; {chain}; A0 = 1; k = 0.1; end")
    big = antimony.getSBMLString("big")

    consulted: list[int] = []
    real_dot_binary = sbml_view._dot_binary

    def no_dot():
        consulted.append(1)
        return None

    sbml_view._dot_binary = no_dot
    try:
        fig = sbml_view.network_figure(sbml)
        with temp_record("dot_m1") as root:
            model = rnd(root, 0) / "model"
            (model / "sbml").put_text(sbml)
            m1 = _m1_glance(model)
        capped = sbml_view.network_figure(big)
    finally:
        sbml_view._dot_binary = real_dot_binary

    assert consulted, "the Graphviz guard was never consulted"
    assert "graphviz layout" not in fig, "the Graphviz path drew with no dot binary"
    assert "circular layout" in fig and "<svg" in fig, (
        "with no dot binary the network figure is not the matplotlib fallback: "
        + fig[:200]
    )
    # the drawing is of this model: its species and a rate law are text in it
    for text in (">R</text>", ">Rp</text>", "k_phos"):
        assert text in fig, f"the fallback drawing lacks {text!r}"
    assert "circular layout" in m1, "the model report's M1 has no fallback figure"
    assert "<svg" not in capped and "12-species cap" in capped, (
        "a model past the fallback's species cap must get a note naming the "
        "cap, not a hairball: " + capped[:200]
    )
    print(
        f"  no graphviz   the guard was consulted {len(consulted)} time(s); the "
        f"circular fallback drew the network, and a 13-species model got a note"
    )


if __name__ == "__main__":
    test_a_break_is_one_escape_and_never_two()
    test_wrapping_still_happens_within_each_line()
    test_the_real_figure_over_four_real_candidates()
    test_no_label_carries_a_rate_law()
    test_it_refuses_the_wrong_ordering()
    test_without_graphviz_the_network_falls_back_to_matplotlib()
    print(
        "DOT LABEL UNIT OK — a line break is one escape, wrapping survives, "
        "the wrong ordering fails the same check, and the network is drawn "
        "without Graphviz"
    )
