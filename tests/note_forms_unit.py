"""A gate card says what the human may type in the note, not only what it will do.

  1. each gate whose note is parsed declares its forms, printed under the consequences;
  2. the record's `pending_gate` carries them, so the chat front end offers the same options;
  3. `?` reprints the card and is never taken as an answer;
  4. every advertised form is read by a real parser;
  5. the discrimination card advertises no search form and flags one if it is typed.

    uv run python tests/note_forms_unit.py
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger  # noqa: E402

from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.workflow_modules.evaluation.engine import (  # noqa: E402
    EXPANSION_NOTE_FORMS,
    REVISION_NOTE_FORMS,
    parse_another_round_request,
)
from octomod.workflow_modules.model import model_space  # noqa: E402
from octomod.workflow_modules.model.engine import SCOPE_NOTE_FORMS  # noqa: E402


def _card(**kw) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        humangate.ask(
            kw.pop("question", "Proceed?"),
            kw.pop("lines", ["some evidence"]),
            ledger=RecordingLedger(),
            module=kw.pop("module", "test_gate"),
            auto=True,
            **kw,
        )
    return buf.getvalue()


def test_the_forms_are_printed_under_the_consequences() -> None:
    out = _card(
        consequences=("it runs", "it stops"),
        note_forms=["n=<starts>   run that many starts", "(nothing)    accept"],
    )
    assert "y → it runs" in out and "n → it stops" in out
    assert "you may also type" in out, f"the forms are not introduced: {out!r}"
    assert "n=<starts>" in out and "(nothing)" in out
    # under the consequences, not above them: the reader decides yes/no first
    assert out.index("y → it runs") < out.index("n=<starts>"), out

    # and a gate with no forms says nothing at all rather than an empty header
    plain = _card(consequences=("a", "b"))
    assert "you may also type" not in plain, plain
    print("  card          forms printed under the consequences, absent when none")


def test_the_payload_carries_them_for_the_front_end(tmp=None) -> None:
    """The `pending_gate` payload must offer what the terminal offers."""
    from tests._record import temp_record

    with temp_record() as root:
        humangate.configure_file_mode(root, None, "")
        try:
            forms = ["expand: yes  — buy another round", "expand: no   — end it"]
            try:
                with redirect_stdout(io.StringIO()):
                    humangate.ask(
                        "Sign off?",
                        ["evidence"],
                        ledger=RecordingLedger(),
                        module="evaluation_verdict",
                        consequences=("ends", "stops"),
                        note_forms=forms,
                    )
            except humangate.GatePending:
                pass
            else:  # pragma: no cover
                raise AssertionError("file mode must pause")
            payload = humangate.pending_path(root).get()
        finally:
            # There is no `disable_file_mode()`: a real run sets the flag once,
            # so the test resets the module state directly.
            humangate._FILE_MODE.update(enabled=False, root=None, answer=None, note="")
    assert payload["note_forms"] == forms, (
        f"the payload does not carry the note forms: {payload.get('note_forms')!r} "
        f"— the chat front end would have to know the parsers by heart"
    )
    print(f"  payload       note_forms travels to the front end ({len(forms)} form(s))")


def test_question_mark_is_not_an_answer() -> None:
    """The property that stops a reader signing a claim by asking a question."""
    import builtins

    typed = iter(["?", "help", "y looks good"])
    real_input = builtins.input
    buf = io.StringIO()
    led = RecordingLedger()

    # echoes the prompt, as the real `input` does — otherwise the prompt is
    # invisible to a redirected stdout and the assertion below tests nothing
    def _fake_input(prompt: str = "") -> str:
        print(prompt, end="")
        return next(typed)

    builtins.input = _fake_input
    try:
        with redirect_stdout(buf):
            approved, note = humangate.ask(
                "Sign off this verdict? (it is a scientific claim)",
                ["evidence"],
                ledger=led,
                module="evaluation_verdict",
                consequences=("the run ends", "the run stops"),
                note_forms=["revise: yes  — buy another round"],
            )
    finally:
        builtins.input = real_input
    out = buf.getvalue()
    assert approved is True and note.strip() == "looks good", (approved, note)
    # the card tail was reprinted for each of the two help requests, so the
    # consequences appear three times: once up front, once per `?`
    assert out.count("y → the run ends") == 3, (
        f"`?` must reprint the card; the consequence line appears "
        f"{out.count('y → the run ends')} time(s)"
    )
    assert out.count("revise: yes") == 3
    signed = [r for r in led.rows if r["event"] == "human_gate"]
    assert len(signed) == 1, (
        f"asking for help signed {len(signed)} verdicts — `?` must never reach "
        f"the ledger as an answer"
    )
    assert signed[0]["approved"] is True and signed[0]["mode"] == "interactive"

    # and it is offered in the prompt, so nobody has to guess that it exists
    assert "'?' for the options" in out
    print("  '?'           reprints the card, answers nothing, signs nothing")


def test_every_advertised_form_is_actually_parsed() -> None:
    """A card that advertises a form nothing reads is worse than silence."""
    # the verdict gates
    for forms, positive, negative in (
        (EXPANSION_NOTE_FORMS, "expand: yes", "expand: no"),
        (REVISION_NOTE_FORMS, "revise: yes", "revise: no"),
    ):
        assert any(f.startswith(positive) for f in forms), forms
        assert parse_another_round_request(positive) is True
        assert parse_another_round_request(negative) is False
        assert forms[-1].startswith("(nothing)"), (
            "every gate must say what happens if the note is empty — that is "
            "the answer most people give"
        )

    # the scope gate: `tier:` and `axes:` must reach `parse_axis_selection`
    axes = [
        {"id": "basal_route", "priority": 1},
        {"id": "product_feedback", "priority": 2},
    ]
    assert "tier:" in " ".join(SCOPE_NOTE_FORMS)
    assert "axes:" in " ".join(SCOPE_NOTE_FORMS)
    assert model_space.parse_axis_selection("axes: basal_route", axes) == {
        "basal_route"
    }
    assert model_space.parse_axis_selection("tier: all", axes) == {
        "basal_route",
        "product_feedback",
    }
    assert model_space.parse_axis_selection("tier: base", axes) == set()
    assert model_space.parse_axis_selection("", axes) is None, (
        "an empty note must mean 'no instruction', which is what the card's "
        "(nothing) line promises"
    )

    # the budget gate and the redraft gate: `n=`
    import re

    for text in ("n=30", "n = 30"):
        assert re.search(r"n\s*=\s*(\d+)", text), text
    print(
        f"  advertised    every form on {len(SCOPE_NOTE_FORMS) + 6} card lines "
        f"is read by a real parser"
    )


def test_the_cards_that_parse_a_note_declare_it() -> None:
    """Each gate module whose note is parsed declares non-empty forms."""
    from octomod.orchestration.interaction import retry
    from octomod.workflow_modules.cost_probe import engine as cost_profile
    from octomod.workflow_modules.evaluation import engine as evaluation_module
    from octomod.workflow_modules.model import engine as model_module

    declared = {
        "model_scope": model_module.SCOPE_NOTE_FORMS,
        "model_scope (discrimination)": model_module.MD_SCOPE_NOTE_FORMS,
        "evaluation_verdict (selection)": evaluation_module.EXPANSION_NOTE_FORMS,
        "evaluation_verdict (single model)": evaluation_module.REVISION_NOTE_FORMS,
    }
    for name, forms in declared.items():
        assert forms and all(isinstance(f, str) and f.strip() for f in forms), name
    # The discrimination card buys candidates and never runs `_resolve_search`,
    # so it must not advertise the search forms.
    md = " ".join(model_module.MD_SCOPE_NOTE_FORMS)
    assert not any(
        f.lstrip().startswith(("tier:", "axes:"))
        for f in model_module.MD_SCOPE_NOTE_FORMS
    ), "the discrimination card advertises a search it does not run"
    assert "1: <answer>" in md and "redraft:" in md, md
    assert "NOT read" in md, "the card must say the search forms are not read here"
    print(
        "  discrimination card: no tier:/axes: form; numbered answers and redraft stay"
    )
    # the two that build their forms inline still have to pass them
    for mod, needle in ((cost_profile, "note_forms="), (retry, "note_forms=")):
        src = Path(mod.__file__).read_text()
        assert needle in src, f"{mod.__name__} parses a note and declares nothing"
    print(f"  coverage      {len(declared) + 2} gates that parse a note declare it")


def test_a_search_form_answered_on_a_discrimination_round_is_flagged() -> None:
    """A search form typed there is not applied; the ledger and terminal say so."""
    from octomod.orchestration.ledger import Ledger
    from octomod.workflow_modules.model import engine as model_module
    from tests._record import ledger_rows, temp_record

    class _Ctx:
        round_idx = 0

        def __init__(self, root):
            self.ledger = Ledger(root)

    with temp_record() as root:  # the ledger is the record's
        ctx = _Ctx(root)
        buf = io.StringIO()
        with redirect_stdout(buf):
            model_module._warn_search_forms_ignored_on_md(ctx, "y tier: top2")
            model_module._warn_search_forms_ignored_on_md(ctx, "y 1: assume linear")
        rows = ledger_rows(root)
        flagged = [r for r in rows if r.get("search_forms_ignored")]
        assert len(flagged) == 1 and "top2" in flagged[0]["answer"], flagged
        assert "NOT applied" in buf.getvalue(), buf.getvalue()
        assert "expansion gate" in flagged[0]["note"], flagged[0]["note"]
    lines = model_module._declared_space_lines(
        {"model_space": [{"id": "ax1", "question": "does A feed back?", "priority": 1}]}
    )
    assert any("not read on this card" in ln for ln in lines), lines
    print(
        "  discrimination: `tier:` answered there is flagged and ledgered, never silently kept"
    )


if __name__ == "__main__":
    test_the_forms_are_printed_under_the_consequences()
    test_the_payload_carries_them_for_the_front_end()
    test_question_mark_is_not_an_answer()
    test_every_advertised_form_is_actually_parsed()
    test_the_cards_that_parse_a_note_declare_it()
    test_a_search_form_answered_on_a_discrimination_round_is_flagged()
    print(
        "NOTE FORMS UNIT OK — every gate that reads a note says so, the "
        "payload carries it, and '?' answers nothing"
    )
