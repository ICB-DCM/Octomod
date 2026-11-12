"""One reading of the human's words at a gate (`octomod/orchestration/interaction/gate_note.py`).

  1. a `key: value` / `key=value` form is read anywhere; keys are whole words;
  2. a bare word is read only when it stands alone, never inside a sentence;
  3. the reading is printed and ledgered with the form words it did NOT act on;
  4. the verdict gate reads its phrases, and a negation earlier in the clause wins;
  5. the scope gate buys no axis search for an axis id mentioned in a sentence;
  6. an `axes:` value that is no axis of the round is named back, not dropped.

    uv run python tests/gate_note_unit.py
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.orchestration.interaction import gate_note  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result.slots import AxisRecord  # noqa: E402
from octomod.result.write import write_records  # noqa: E402
from octomod.workflow_modules.evaluation.engine import (  # noqa: E402
    parse_another_round_request,
)
from octomod.workflow_modules.model import model_space  # noqa: E402


def test_key_forms() -> None:
    check("n=50 is read", gate_note.key_int("n=50", "n") == 50)
    check("n = 50 is read", gate_note.key_int("y, n = 50 please", "n") == 50)
    check("run=3 is NOT n=3", gate_note.key_int("run=3", "n") is None)
    check("n=5.5 is not an integer form", gate_note.key_int("n=5.5", "n") is None)
    check(
        "a key: value runs to the end of its clause",
        gate_note.key_value("tier: top2; axes: a", "tier") == "top2",
        repr(gate_note.key_value("tier: top2; axes: a", "tier")),
    )
    check("keys are whole words", gate_note.key_value("taxes: high", "axes") is None)


def test_bare_words_only_on_their_own() -> None:
    words = ("adjoint", "tighten")
    cases = {
        "adjoint": {"adjoint"},
        "Adjoint.": {"adjoint"},
        "y adjoint": {"adjoint"},
        "n=200 adjoint": {"adjoint"},
        "tighten adjoint": {"adjoint", "tighten"},
        "n=200, tighten": {"tighten"},
        "convergence: accept the plateau is expected\nadjoint": {"adjoint"},
        "forward sensitivities as in rounds 0 and 1 (adjoint not taken)": set(),
        "please use adjoint": set(),
        "convergence: accept tighten later if needed": set(),
        "": set(),
    }
    for note, want in cases.items():
        got = gate_note.standalone(note, words)
        check(f"{note!r} → {sorted(want)}", got == want, f"got {sorted(got)}")
    unread = gate_note.unread_in_prose(
        "adjoint not taken", words, gate_note.standalone("adjoint not taken", words)
    )
    check(
        "a word mentioned in prose is reported as NOT read, with the reason",
        unread == {"adjoint": gate_note.IN_PROSE},
        str(unread),
    )


def test_the_reading_is_said_at_once() -> None:
    with temp_record("gate_note") as root:
        ledger = Ledger(root)
        r = gate_note.Reading(
            read={"n": 200, "adjoint": True}, unread={"tighten": "not offered"}
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            gate_note.report(
                r,
                "n=200 adjoint tighten",
                ledger=ledger,
                module="cost_boundary_estimation",
                round_idx=0,
            )
        out = buf.getvalue()
        check(
            "printed: what was read and what was not",
            "read from your note: n=200 · adjoint | NOT read: tighten (not offered)"
            in out,
            out.strip(),
        )
        rows = [e for e in ledger.entries() if e.get("note_read") is not None]
        check(
            "ledgered with the structured reading",
            rows and rows[-1]["note_read"] == {"n": 200, "adjoint": True},
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            gate_note.report(
                gate_note.Reading(), "   ", ledger=ledger, module="x", round_idx=0
            )
        check("an empty note says nothing", buf.getvalue() == "")
        check(
            "a note with no form says so",
            gate_note.Reading().line().startswith("no form"),
        )


def test_the_verdict_phrases_with_clause_negation() -> None:
    cases = {
        "I wanted to go into another loop": True,  # a plain-sentence request
        "another round please": True,
        "no, I want another round": True,
        "expand: no, the sigma is fine": False,
        "no expansion, the sigma is fine": False,
        "I don't think we need expansion yet": False,  # negation earlier in clause
        "skip another round": False,
        "looks good, signing off": None,
    }
    for note, want in cases.items():
        got = parse_another_round_request(note)
        check(f"verdict {note!r} → {want}", got is want, f"got {got}")


def test_an_axis_named_in_a_sentence_is_not_bought() -> None:
    axes = [
        {"id": "basal_route", "priority": 1},
        {"id": "product_feedback", "priority": 2},
    ]
    check(
        "an axis id mentioned in a sentence buys nothing",
        model_space.parse_axis_selection("not sure about basal_route yet", axes)
        is None,
    )
    check(
        "an axis id on its own is still a selection",
        model_space.parse_axis_selection("basal_route", axes) == {"basal_route"},
    )
    check(
        "and so is `axes:`",
        model_space.parse_axis_selection("axes: product_feedback", axes)
        == {"product_feedback"},
    )


def test_list_and_tier_forms() -> None:
    """`axes:` and `tier:` have one reader each, shared by every gate."""
    check(
        "key_list splits a form's values and stops at a sentence",
        gate_note.key_list("y\naxes: a, b. then more", "axes") == ["a", "b"]
        and gate_note.key_list("axis: x", "axes", "axis") == ["x"]
        and gate_note.key_list("no form here", "axes") is None,
    )
    check(
        "tier reads base, all and top<k>, and nothing else",
        gate_note.tier("tier: top 3") == "top3"
        and gate_note.tier("tier: base") == "base"
        and gate_note.tier("tier: maximal") is None,
    )
    axes = [{"id": "alt_route", "priority": 1}, {"id": "feedback", "priority": 2}]
    check(
        "an axes: list naming nothing known leaves the space as declared",
        model_space.parse_axis_selection(
            "axes: unknown\nthe alt_route idea is odd", axes
        )
        is None,
    )


def _scope_reading(root, note: str, axes: list) -> str:
    """The line the scope gate prints for `note`, through `_report_scope_reading`."""
    from types import SimpleNamespace

    from octomod.workflow_modules.model.engine import _report_scope_reading

    ctx = SimpleNamespace(ledger=Ledger(root), round_idx=0, root=root)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _report_scope_reading(ctx, note, axes)
    return buf.getvalue().strip()


def test_an_unknown_axis_id_is_named_back() -> None:
    """An `axes:` value that is no axis of the round is read back as not acted on."""
    axes = [{"id": "alt_route", "priority": 1}, {"id": "feedback", "priority": 2}]
    why = "not an axis of this round (the axes are: alt_route, feedback)"
    with temp_record("scope_reading") as root:
        out = _scope_reading(root, "axes: unknwn", axes)
        check(
            "axes: <unknown> names the id back instead of saying no form",
            out == f"read from your note: nothing acted on | NOT read: axes: unknwn "
            f"({why})"
            and "no form" not in out,
            out,
        )
        out = _scope_reading(root, "axes: feedback, unknwn", axes)
        check(
            "axes: <known>, <unknown> reads the known id and names the other",
            out == f"read from your note: axes: feedback | NOT read: axes: unknwn "
            f"({why})",
            out,
        )
        out = _scope_reading(root, "axes: all - the enlarged space", axes)
        check(
            "the words after a collective axes: word are prose, not unknown ids",
            out == "read from your note: axes: alt_route, feedback",
            out,
        )
        write_records(rnd(root, 0) / "space/axes", AxisRecord, [{"id": "old_route"}])
        out = _scope_reading(root, "axes: feedback, old_route", axes)
        check(
            "an axis declared earlier in the run is not unknown (it is bought back)",
            "NOT read" not in out,
            out,
        )


def main() -> int:
    print("one reading of the human's words at every gate")
    test_key_forms()
    test_bare_words_only_on_their_own()
    test_the_reading_is_said_at_once()
    test_the_verdict_phrases_with_clause_negation()
    test_an_axis_named_in_a_sentence_is_not_bought()
    test_list_and_tier_forms()
    test_an_unknown_axis_id_is_named_back()
    return finish("\nGATE NOTE", "GATE NOTE OK")


if __name__ == "__main__":
    sys.exit(main())
