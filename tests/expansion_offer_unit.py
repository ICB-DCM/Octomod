"""The human's lever on another round: indicators set the default, a person decides.

  1. `should_expand`: nine branches; an explicit request outranks quiet indicators;
  2. `parse_expansion_request`: the note forms, including a plain-sentence request;
  3. `md_verdict_consequences`: the question stays while a round remains;
  4. `verdict_disagreement`: the agent's `revise` leaves a trace;
  5. the single-model path offers a round too, in the same vocabulary;
  6. `misfit_margins`: measured on a saved run's own recorded evidence;
  7. a fired indicator prints its statistic; an unmeasured one never reads as quiet;
  8. an expansion axis names its origin, and what lies beyond this data reaches
     the card and the run page;
  9. a literature search the expansion agent asks for (`requested_research`):
     run once with its questions, frozen, its items handed back with fresh ids;
     a second request refused by name and asked once more, a third not; a
     resume reads the snapshot back; with research off, recorded and re-asked,
     nothing called.

    uv run python tests/expansion_offer_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration.orchestrator import should_expand  # noqa: E402
from octomod.workflow_modules.evaluation import misfit_margins as mm  # noqa: E402
from octomod.workflow_modules.evaluation.engine import (  # noqa: E402
    EXPANSION_NOTE_FORMS,
    REVISION_NOTE_FORMS,
    _verdict_consequences,
    another_round_note_forms,
    md_verdict_consequences,
    parse_another_round_request,
    parse_expansion_request,
    verdict_disagreement,
)
from tests._record import rnd, run_root  # noqa: E402

# The user's runs folder, deliberately not redirected by the battery: this
# reads an existing run, not one this suite makes.
USER_RUNS = config.USER_RUNS_DIR

LB4 = rnd(run_root("live_blind_4", USER_RUNS), 0) / "evaluation"


def test_the_human_decides_and_the_indicators_only_default() -> None:
    """Nine branches of `should_expand`; the human outranks the indicators."""
    cases = [
        # (misfit_open, rounds_left, requested, expand_on_misfit, expect, why)
        (True, 2, None, True, True, "the default that always worked"),
        (False, 2, None, True, False, "the default: quiet indicators end it"),
        (False, 2, True, True, True, "**THE FIX**: quiet, and asked for"),
        (True, 2, False, True, False, "human ends it despite open indicators"),
        (False, 0, True, True, False, "no rounds: there is nothing to buy"),
        (True, 0, None, True, False, "no rounds, indicators open"),
        (True, 2, None, False, False, "spec off, nobody asked"),
        (False, 2, True, False, True, "spec off, human asked — human wins"),
        (True, 2, True, False, True, "spec off, open, asked"),
    ]
    for open_, rl, req, spec_on, expect, label in cases:
        got, why = should_expand(open_, rl, req, spec_on)
        assert got is expect, (
            f"{label}: should_expand(open={open_}, rounds={rl}, "
            f"asked={req}, spec={spec_on}) = {got}, expected {expect} — {why}"
        )
        assert why, "every decision must state its reason"
    # the two invariants behind the table, stated as invariants
    for open_ in (True, False):
        assert should_expand(open_, 2, True, True)[0] is True, (
            "an explicit request must buy a round whatever the indicators say "
            "— that is what the request is for"
        )
        assert (
            should_expand(open_, 2, False, True)[0] is False
        ), "an explicit refusal must end the run whatever the indicators say"
        assert (
            should_expand(open_, 0, True, True)[0] is False
        ), "a request cannot conjure a round that the budget does not have"
    print(f"  decision      {len(cases)} branches; the human outranks the indicators")


def test_the_note_forms_parse_including_the_words_he_used() -> None:
    yes = [
        "expand: yes",
        "expand:y",
        "expand = TRUE",
        "expansion: yes",
        "I wanted to go into another loop",  # a plain-sentence request
        "another round please",
        "one more round",
        "a further iteration",
        "axes: basal_route; expand: yes",
    ]
    no = [
        "expand: no",
        "expand=n",
        "Expansion: false",
        "don't expand",
        "do not expand",
        "skip another round",
        "without expansion",
        "no expansion, the sigma is fine",
        "expand: no, the sigma is fine",
    ]
    silent = [
        "",
        "   ",
        "looks good, signing off",
        "1: assume linear; 2: keep lumped",
        "n=50",
        "tier: all",
        "axes: basal_route, product_feedback",
    ]
    for n in yes:
        assert parse_expansion_request(n) is True, f"should ask for a round: {n!r}"
    for n in no:
        assert parse_expansion_request(n) is False, f"should decline a round: {n!r}"
    for n in silent:
        assert parse_expansion_request(n) is None, (
            f"{n!r} says nothing about another round, so the default must "
            f"apply — a note the parser over-reads is worse than no parser"
        )
    # the negation must beat the bare word, or `expand: no` reads as a request
    assert parse_expansion_request("expand: no") is False
    assert "expand: yes" in " ".join(EXPANSION_NOTE_FORMS)
    assert "expand: no" in " ".join(EXPANSION_NOTE_FORMS)
    print(
        f"  note forms    {len(yes)} ask · {len(no)} decline · {len(silent)} "
        f"silent, all as intended; both forms are on the card"
    )


def test_the_question_never_disappears_while_a_round_remains() -> None:
    """The card asks about another round whenever one remains, quiet or not."""
    near = {"reads_as": "sigma 1.232 against 1.3 — 0.068 below"}

    quiet_with_rounds = md_verdict_consequences(False, 2, near)[0]
    assert "expand: yes" in quiet_with_rounds, (
        "no indicator open and 2 rounds left, and the card does not say how to "
        f"buy one: {quiet_with_rounds!r}"
    )
    assert "0.068 below" in quiet_with_rounds, (
        "the closest indicator's distance must be stated when the run is about "
        "to end on it"
    )
    assert "DEFAULT" in quiet_with_rounds, "the default must be named as a default"

    open_with_rounds = md_verdict_consequences(True, 2, near)[0]
    assert "expand: no" in open_with_rounds, (
        "the question is symmetric: with indicators open the human must be "
        "able to STOP, not only to continue"
    )

    # no rounds left: the card must not offer what the engine cannot deliver
    for open_ in (True, False):
        last = md_verdict_consequences(open_, 0, near)[0]
        assert "THE RUN ENDS" in last, last
        assert (
            "expand: yes" not in last
        ), f"no rounds left, and the card offers one anyway: {last!r}"
    assert md_verdict_consequences(False, None, near)[0], "None rounds_left must work"
    print("  card          asks either way with a round left, never without one")


def test_the_agents_recommendation_leaves_a_trace() -> None:
    d = verdict_disagreement("revise", misfit_open=False, rounds_left=2)
    assert d, "revise + engine ending = a disagreement to record"
    assert d["agent_recommendation"] == "revise"
    assert d["engine_default"] == "end"
    assert d["human_can_override"] is True
    assert "no indicator is open" in d["because"]

    last = verdict_disagreement("revise", misfit_open=True, rounds_left=0)
    assert last and last["human_can_override"] is False, (
        "with no rounds left the disagreement is still recorded — it just "
        "cannot be acted on, and the card must not pretend otherwise"
    )
    assert verdict_disagreement("revise", True, 2) is None, (
        "open indicators plus a round left means the engine is ALREADY doing "
        "what the agent asked; that is agreement, not disagreement"
    )
    for rec in ("accept", "stop", "", None):
        assert verdict_disagreement(rec, False, 2) is None, rec
    assert verdict_disagreement("reject", False, 2), "reject is the stronger form"
    print("  disagreement  recorded when it exists, absent when it does not")


class _Interp(dict):
    """The two fields `_verdict_consequences` reads off an interpretation."""

    def __init__(self, recommendation: str) -> None:
        super().__init__(recommendation=recommendation)


class _T2:
    def __init__(self, passed: bool) -> None:
        self.passed = passed


def test_the_single_model_path_offers_a_round_too() -> None:
    """On the single-model path the agent's `accept` is a default, not a decision."""
    near = {"reads_as": "sigma 1.232 against 1.3 — 0.068 below"}

    accept_with_rounds = _verdict_consequences(
        _Interp("accept"), _T2(True), "prediction", 2, near
    )[0]
    assert "revise: yes" in accept_with_rounds, (
        f"the agent said accept with 2 rounds left, and the card does not say "
        f"how to ask for another: {accept_with_rounds!r}"
    )
    assert "0.068 below" in accept_with_rounds, "the margin must be stated here too"
    assert "DEFAULT" in accept_with_rounds

    revise_with_rounds = _verdict_consequences(
        _Interp("revise"), _T2(True), "prediction", 2, near
    )[0]
    assert "revise: no" in revise_with_rounds, (
        "symmetric: with the agent asking for a revision the human must be "
        "able to stop"
    )

    # no rounds left: no offer, and no promise of a revision that cannot run
    # (the loop breaks on `rounds_left <= 0` before `revision_proposal` is called)
    last = _verdict_consequences(_Interp("revise"), _T2(True), "prediction", 0, near)[0]
    assert "THE RUN ENDS" in last, last
    assert "revise: yes" not in last, last
    assert (
        "a revision proposal follows" not in last
    ), f"the card promises a revision the loop will not run: {last!r}"

    # T2' unmet still outranks everything and keeps its own wording
    t2 = _verdict_consequences(_Interp("accept"), _T2(False), "prediction", 2, near)[0]
    assert "OVERRIDDEN" in t2, t2
    print("  single model  asks either way, and never promises a skipped revision")


def test_one_vocabulary_across_both_paths() -> None:
    """A human should not have to know which loop the engine is in."""
    assert (
        parse_expansion_request is parse_another_round_request
    ), "one parser, or the two cards will disagree about what a human said"
    for form in ("expand: yes", "revise: yes", "round: yes"):
        assert parse_another_round_request(form) is True, form
    for form in ("expand: no", "revise: no", "round: no"):
        assert parse_another_round_request(form) is False, form
    # each path prints the wording that is TRUE for it
    assert another_round_note_forms(True) == EXPANSION_NOTE_FORMS
    assert another_round_note_forms(False) == REVISION_NOTE_FORMS
    assert "space was missing" in EXPANSION_NOTE_FORMS[0]
    assert "one change to the model" in REVISION_NOTE_FORMS[0]
    for forms in (EXPANSION_NOTE_FORMS, REVISION_NOTE_FORMS):
        assert len(forms) == 3 and "(nothing)" in forms[2]
    print("  vocabulary    expand/revise/round all parse; each card says its own")


def test_margins_measured_on_live_blind_4s_own_evidence() -> None:
    """A saved run's evaluation record: sigma near-missed, chi2 (alpha 0.01) was clear."""
    if not LB4.exists():  # pragma: no cover - the live run is not in the repo
        print("  (live_blind_4 not on disk — skipping the measured assertions)")
        return
    ev = LB4.get()["misfit_evidence"]
    assert ev.get("open") is False, "the premise of this check is that nothing fired"

    rows = mm.margins(ev)
    assert rows, "the evidence recorded signals and the margins are empty"
    assert all(not e["fired"] for e in rows), "nothing fired on this round"
    # ranked nearest-first, so the head IS the answer to "what almost fired"
    close = [e["closeness"] for e in rows if e["closeness"] is not None]
    assert close == sorted(close, reverse=True), close

    near = mm.nearest(ev)
    assert near and "obs_regb_p" in near["indicator"], near
    assert abs(near["value"] - 1.232) < 1e-9, near["value"]
    assert abs(near["threshold"] - 1.3) < 1e-9, near["threshold"]
    assert abs(near["closeness"] - 0.948) < 5e-4, near["closeness"]
    assert "0.068" in near["reads_as"], near["reads_as"]

    chi2 = next(e for e in rows if e["indicator"].startswith("chi2"))
    assert abs(chi2["threshold"] - 0.01) < 1e-12, (
        f"the chi2 alpha is {chi2['threshold']}; the spec says 0.01, and the "
        f"failure write-up says 0.05 — the write-up is the one that is wrong"
    )
    assert chi2["closeness"] < 0.2, (
        f"the chi2 indicator was {chi2['closeness']:.0%} of the way to firing, "
        f"which is not the near-miss the failure describes; only the sigma indicator "
        f"was close"
    )

    one_line = mm.card_line_compact(ev)
    for e in rows:
        assert f"{e['closeness']:.0%}" in one_line, (
            f"the card's one-line summary drops {e['indicator']} — 'every "
            f"indicator prints its margin' has to mean every one"
        )
    print(
        f"  margins       nearest {near['indicator']} at "
        f"{near['closeness']:.1%}; chi2 at {chi2['closeness']:.1%} against "
        f"alpha {chi2['threshold']} — one near miss, not two"
    )


def test_a_fired_indicator_shows_its_statistic_not_a_percentage() -> None:
    """Past its threshold a percentage means nothing: a fired indicator prints p."""
    rows = [
        {
            "indicator": "residual shape (corroborating only)",
            "kind": "p",
            "value": 1.5e-7,
            "threshold": 0.01,
            "fired": True,
            "closeness": 0.01 / 1.5e-7,
            "threshold_recorded": True,
        },
        {
            "indicator": "sigma over replicate floor · obs_x",
            "kind": "ceiling",
            "value": 1.232,
            "threshold": 1.3,
            "fired": False,
            "closeness": 0.948,
            "threshold_recorded": True,
        },
    ]
    real = mm.margins
    mm.margins = lambda *a, **k: rows
    try:
        line = mm.card_line_compact({"signals": {}})
    finally:
        mm.margins = real
    assert "p=1.5e-07 < 0.01*" in line and "34005224" not in line, line
    assert "sigma·obs_x 95%" in line, line
    print("  fired         a fired indicator prints p against alpha, not 34005224%")


def test_an_indicator_that_could_not_be_measured_is_not_a_pass() -> None:
    """ "Not measured" and "measured and quiet" must not read alike."""
    ev = {
        "signals": {
            "sigma_not_constant": [
                {"observable": "obs_x", "note": "state-dependent noise"}
            ]
        },
        "thresholds": {"alpha": 0.01, "max_sigma_over_floor": 1.3},
    }
    rows = mm.margins(ev)
    unmeasured = [e for e in rows if e["closeness"] is None]
    assert unmeasured, "a screen that could not run must still appear"
    assert any("NOT COMPARABLE" in e["what"] for e in unmeasured)
    assert all(e["closeness"] is None for e in unmeasured)
    # and it must sort last, so it never looks like the closest call
    assert rows[-1]["closeness"] is None, [e["indicator"] for e in rows]
    assert mm.nearest(ev) is None or mm.nearest(ev)["closeness"] is not None
    # a run with no thresholds recorded says so rather than implying today's
    old = mm.margins({"gof_at_noise_floor": {"p": 0.2, "chi2_per_dof": 1.1, "dof": 9}})
    assert any("today's default" in e["reads_as"] for e in old), old
    print("  unmeasured    listed, sorted last, never counted as quiet")


BEYOND = {
    "mechanism": "a second, slow phosphatase acting on RegB_p",
    "why_not_separable": "every arm is sampled after it would have acted",
    "experiment": "a 2-minute-resolution washout after u=4",
}


def test_the_biology_and_what_lies_beyond_the_data_reach_card_and_run_page() -> None:
    """An expansion axis says whether it came from the residuals or from the
    biology, and the mechanisms the agent names beyond what this data can
    separate are shown on the card and collected on the run page — the latest
    round's list, and an earlier round's that ended without an expansion."""
    from octomod.orchestration.ledger import Ledger
    from octomod.reporting import analysis_report as ar
    from octomod.workflow_modules.model import model_space as ms
    from tests._record import reports_dir, temp_record

    class _Ctx:
        def __init__(self, root):
            self.root, self.round_idx = root, 0  # the run is one record
            self.ledger = Ledger(root)

        @property
        def round(self):
            return rnd(self.root, self.round_idx)

    base = "model m\n  R1: A -> B; k1*A\n  A = 1; B = 0; k1 = 0.1\nend\n"
    proposed = [
        {
            "id": "direct_route",
            "question": "does A reach B by a second route?",
            "origin": "biology",
            "on_antimony_patch": {"append": ["R9: A -> B; k9*A;"]},
            "adds_parameters": [{"id": "k9", "nominal_value": 0.1}],
        },
        {
            "id": "sat_step",
            "question": "does the R1 step saturate?",
            "on_antimony_patch": {
                "replace_reaction": "R1",
                "with": "R1: A -> B; k1*A/(1 + b1*A)",
            },
            "adds_parameters": [{"id": "b1", "nominal_value": 0.0}],
        },
    ]
    with temp_record("beyond_axes") as root:
        ctx = _Ctx(root)
        got, dropped = ms.validate_axes(ctx, proposed, base, {"k1"}, module="revision")
        assert not dropped, dropped
        assert [a.get("origin") for a in got] == ["biology", "residual"], got
        built, _ = ms.validate_axes(ctx, proposed, base, {"k1"}, module="model")
        assert all("origin" not in a for a in built), (
            "a construction axis was given an expansion origin: "
            f"{[a.get('origin') for a in built]}"
        )
    lines = ms.expansion_axis_lines(got)
    assert any("direct_route" in ln and "(from the biology)" in ln for ln in lines)
    assert any("sat_step" in ln and "(from the residuals)" in ln for ln in lines)

    proposal = {"beyond_this_data": [BEYOND, "not an entry", {"mechanism": ""}]}
    items = ms.beyond_this_data(proposal)
    assert items == [BEYOND], items
    assert ms.beyond_this_data({"axes": []}) == []
    card = ms.beyond_card_lines(items)
    assert card and "BEYOND THIS DATA" in card[0], card
    shown = "\n".join(card)
    for part in BEYOND.values():
        assert part in shown, (part, shown)
    assert ms.beyond_card_lines([]) == []

    later = {**BEYOND, "mechanism": "receptor internalisation"}
    with temp_record("beyond_run") as run:
        (run / "intent").put({"question": "q", "system": "s", "inference_target": "p"})
        for r in (0, 1):
            (rnd(run, r) / "evaluation").put(
                {"holdout": {"available": False}, "best_fval": 1.0}
            )
        # round 0 ended without an expansion: the list is in the proposal only
        (rnd(run, 0) / "expansion_diagnostics").put(
            {"steps": [], "final_proposal": {"beyond_this_data": [BEYOND]}}
        )
        (rnd(run, 1) / "expansion").put(
            {"expanded": False, "why": "declined", "beyond_this_data": [later]}
        )
        summary = ar.build(run)
        assert [b["round"] for b in summary["beyond_this_data"]] == [1, 0], summary[
            "beyond_this_data"
        ]
        ar.write(run)
        md = (reports_dir(run) / "ANALYSIS.md").read_text()
        html = (reports_dir(run) / "ANALYSIS.html").read_text()
        assert "## Beyond this data" in md, md[-800:]
        assert md.index("receptor internalisation") < md.index(BEYOND["mechanism"])
        assert BEYOND["experiment"] in md and BEYOND["why_not_separable"] in md
        assert (
            "<h2>Beyond this data</h2>" in html and "receptor internalisation" in html
        )
    print(
        "  beyond        each axis names its origin; the mechanisms beyond this "
        "data reach the card and the run page, latest round first"
    )


# the two refusals, by the names the card, the ledger and the agent read
ALREADY_REQUESTED = "research already requested this round"
NOT_ALLOWED = "a search the run does not allow"
# the questions of the first request: one more than a request may carry
ASKED = [
    "Is a conversion of A to B that bypasses the R1 step described for this system?",
    "Is B reported to inhibit its own formation from A?",
    "Is a loss of A other than conversion to B described?",
    "Is A synthesised during the experiment?",
]
# the research role's answer: one item for question 1, one for question 2 that
# the case's horizon drops before any agent reads it
REQUESTED_REPLY = {
    "evidence_items": [
        {
            "source": "A second A-to-B route (fixture)",
            "title": "A bypass of the R1 step",
            "year": 2020,
            "locator": "figure 1",
            "supports": "A reaches B without R1",
            "quote": "without R1",
            "url": "",
            "question": 1,
        },
        {
            "source": "Late preprint (fixture)",
            "title": "A preprint past the horizon",
            "year": 2031,
            "locator": "abstract",
            "supports": "B inhibits its own formation",
            "quote": "",
            "url": "",
            "question": 2,
        },
    ],
    "queries_run": ["A to B bypass (fixture)"],
    "notes": "FIXTURE: the search the expansion agent asked for",
}
# what the pre-search before the proposal found: the requested items follow it
PRE_SEARCH_ITEM = {
    "id": "res_1",
    "origin": "research",
    "source": "Pre-search (fixture)",
    "title": "Found before the proposal",
    "year": 2019,
    "supports": "B is lost",
}


def _expansion_reply(questions: list[str] | None = None, tag: str = "") -> dict:
    reply = {"diagnosis": f"FIXTURE {tag}", "axes": [], "stop_instead": False}
    if questions:
        reply["requested_research"] = questions
    return reply


def _proposal_rig(tmp: Path, root, research: bool, replies: list[dict]):
    """A round-0 context on the record `root` and the stub backend, the
    expansion agent's replies in sequence (one call more than the sequence
    fails), a spy on every agent call, and an orchestrator holding only what
    `_expansion_proposal` reads."""
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.orchestrator import Orchestrator
    from octomod.orchestration.run_context import RunContext
    from octomod.result import node as tree
    from octomod.spec import WorkflowSpec

    case = tmp / "case"
    (case / "stubs").mkdir(parents=True)
    (case / "testcase.yaml").write_text(
        "name: unit\n"
        + (
            "research:\n  enabled: true\n  max_publication_year: 2025\n"
            if research
            else ""
        )
    )
    (case / "description.md").write_text("A converts to B; B is lost.\n")
    for k, reply in enumerate(replies, start=1):
        (case / "stubs" / f"revision.{k}.json").write_text(json.dumps(reply))
    # a sequence of one: a second research call fails loudly
    (case / "stubs" / "research.1.json").write_text(json.dumps(REQUESTED_REPLY))
    (root / "intent").put(
        {"question": "unit", "system": "toy", "inference_target": "p"}
    )
    ctx = RunContext(
        root=root,
        testcase_dir=case,
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(root),
        backend="stub",
        auto=True,
    )
    # the selected candidate's model, which the research role is told about
    (tree.model_node(ctx.round, "M1") / "antimony").put_text(
        "model m\n  R1: A -> B; k1*A\n  R2: B -> ; k2*B\n"
        "  A = 1; B = 0; k1 = 0.1; k2 = 0.05\nend\n"
    )
    seen: list[tuple[str, dict]] = []

    def spy(role, context, calls=None, name=None):
        seen.append((role, json.loads(json.dumps(context, default=str))))
        return RunContext.call(ctx, role, context, calls=calls, name=name)

    ctx.call = spy
    orch = Orchestrator.__new__(Orchestrator)
    orch.ctx, orch.spec, orch.ledger = ctx, ctx.spec, ctx.ledger
    return ctx, orch, seen


def _agent_calls(ctx, role: str) -> int:
    return sum(
        1
        for e in ctx.ledger.entries()
        if e.get("event") == "agent_call" and e.get("role") == role
    )


def _payloads(calls, role: str) -> list[dict]:
    return [c for r, c in calls if r == role]


def test_the_expansion_agent_may_direct_one_literature_search() -> None:
    """`requested_research` in an expansion reply: the research role is called
    once with the questions, the snapshot is frozen, the items come back with
    fresh ids beside the pre-search's and the questions under
    `research_answered`; a second request is refused by name and the agent is
    asked once more, a third is recorded and not re-asked; a resume reads the
    snapshot back and calls nothing."""
    import tempfile

    from octomod.workflow_modules.model import engine as model_module
    from tests._record import temp_record

    base = {
        "intent": {"question": "unit"},
        "selected_model": "M1",
        "retrieved_evidence": [PRE_SEARCH_ITEM],
        "evidence_instruction": model_module.EXPANSION_EVIDENCE_INSTRUCTION,
    }
    replies = [
        _expansion_reply(ASKED, "asks for a search"),
        _expansion_reply(["Is a second search possible?"], "asks again"),
        _expansion_reply(["And a third?"], "asks a third time"),
        _expansion_reply(tag="after a crash"),
        _expansion_reply(tag="after a crash mid-search"),
    ]
    with tempfile.TemporaryDirectory() as d, temp_record("research_ask") as root:
        ctx, orch, calls = _proposal_rig(Path(d), root, True, replies)
        state_node = ctx.round / "expansion_diagnostics"
        # construction's research call of this round, which the search the
        # expansion agent asks for must leave where it is
        first_research = ctx.agent_calls / "research/reply"
        first_research.put({"evidence_items": [], "notes": "construction's"})
        orch._expansion_proposal(dict(base), ["M1"])
        assert _agent_calls(ctx, "research") == 1, _agent_calls(ctx, "research")
        assert _agent_calls(ctx, "revision") == 3, (
            "a request after the refusal must not buy another ask",
            _agent_calls(ctx, "revision"),
        )
        asked = _payloads(calls, "research")[0]
        assert asked.get("questions") == ASKED[:3], asked.get("questions")
        assert "model_summary" in asked and "restrictions" in asked, sorted(asked)
        # the call is archived apart from any other research call of the round
        assert (ctx.agent_calls / "research_request_1/prompt").exists()
        assert first_research.get() == {
            "evidence_items": [],
            "notes": "construction's",
        }, first_research.get()
        assert not (ctx.agent_calls / "research/prompt").exists()
        snap = (ctx.round / "research_requests/1").get()
        assert [
            (i.get("id"), i.get("origin"), i.get("answers_question"))
            for i in snap["items"]
        ] == [("res_2", "research", ASKED[0])], snap["items"]
        assert [x["reason"] for x in snap["dropped"]] == ["published after 2025"]
        second, third = _payloads(calls, "revision")[1:3]
        assert [i.get("id") for i in second.get("retrieved_evidence") or []] == [
            "res_1",
            "res_2",
        ], second.get("retrieved_evidence")
        assert second.get("research_answered") == ASKED[:3], second.get(
            "research_answered"
        )
        assert "research_refused" not in second, sorted(second)
        refused = third.get("research_refused") or {}
        assert ALREADY_REQUESTED in str(refused.get("why")), refused
        assert third.get("research_answered") == ASKED[:3]
        state = state_node.get()
        reqs = state.get("research_requests") or []
        assert [r.get("status") for r in reqs] == [
            "answered",
            "refused",
            "ignored",
        ], reqs
        assert reqs[0].get("not_searched") == ASKED[3:], reqs[0]
        rows = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "expansion_research_requested"
        ]
        assert [(r.get("status"), r.get("questions")) for r in rows] == [
            ("answered", ASKED[:3]),
            ("refused", ["Is a second search possible?"]),
            ("ignored", ["And a third?"]),
        ], rows
        lines = model_module.requested_research_lines(reqs)
        shown = "\n".join(lines)
        for k, n in ((1, 1), (2, 0), (3, 0)):
            assert any(ln.strip().startswith(f"Q{k} ({n} item(s))") for ln in lines), (
                k,
                shown,
            )
        assert ASKED[0] in shown and ASKED[3] in shown, shown
        assert ALREADY_REQUESTED in shown, shown
        assert "res_2" in shown, shown

        # a crash after the search, before the reply was final: the resume
        # reads the snapshot and asks the agent once more with its items
        state.pop("final_proposal")
        state_node.put(state)
        orch._expansion_proposal(dict(base), ["M1"])
        assert _agent_calls(ctx, "research") == 1, "a resume paid for the search twice"
        fourth = _payloads(calls, "revision")[3]
        assert fourth.get("research_answered") == ASKED[:3], sorted(fourth)
        assert [i.get("id") for i in fourth.get("retrieved_evidence") or []] == [
            "res_1",
            "res_2",
        ]

        # a crash between the frozen snapshot and the recorded answer: the
        # resume finishes the request from the snapshot, no second call
        state = state_node.get()
        state.pop("final_proposal")
        state["research_requests"][0] = {
            k: state["research_requests"][0][k]
            for k in ("questions", "not_searched", "n", "snapshot")
        } | {"status": "pending"}
        state_node.put(state)
        orch._expansion_proposal(dict(base), ["M1"])
        assert _agent_calls(ctx, "research") == 1, "a pending search was bought again"
        state = state_node.get()
        assert state["research_requests"][0].get("status") == "answered", state
        assert any(
            e.get("event") == "note"
            and "rounds/round_0/research_requests/1" in str(e.get("note"))
            and "reused" in str(e.get("note"))
            for e in ctx.ledger.entries()
        ), "the snapshot's reuse is not ledgered"
        fifth = _payloads(calls, "revision")[4]
        assert fifth.get("research_answered") == ASKED[:3], sorted(fifth)
    print(
        "  research ask  one search with the agent's questions, frozen, handed "
        "back as res_2; a second refused by name, a third not re-asked; a "
        "resume reads the snapshot"
    )


def test_a_search_the_run_does_not_allow_is_recorded_and_asked_again() -> None:
    """Research off for the case: a `requested_research` calls nothing, is
    recorded and ledgered, the card says so, and the agent is asked once more
    with the fact."""
    import tempfile

    from octomod.workflow_modules.model import engine as model_module
    from tests._record import temp_record

    replies = [
        _expansion_reply(ASKED[:2], "asks for a search"),
        _expansion_reply(tag="proposes without one"),
    ]
    with tempfile.TemporaryDirectory() as d, temp_record("research_off") as root:
        ctx, orch, calls = _proposal_rig(Path(d), root, False, replies)
        base = {"intent": {"question": "unit"}, "selected_model": "M1"}
        orch._expansion_proposal(base, ["M1"])
        assert _agent_calls(ctx, "research") == 0, "research is off and was called"
        assert _agent_calls(ctx, "revision") == 2
        first, second = _payloads(calls, "revision")
        assert "no literature search" in str(first.get("research_instruction")), first
        refused = second.get("research_refused") or {}
        assert refused.get("questions") == ASKED[:2], refused
        assert NOT_ALLOWED in str(refused.get("why")), refused
        assert "retrieved_evidence" not in second and "research_answered" not in second
        state = (ctx.round / "expansion_diagnostics").get()
        reqs = state.get("research_requests") or []
        assert [r.get("status") for r in reqs] == ["refused"], reqs
        assert not (ctx.round / "research_requests").exists(), "a snapshot was written"
        assert not (ctx.agent_calls / "research_request_1").exists()
        rows = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "expansion_research_requested"
        ]
        assert len(rows) == 1 and rows[0].get("questions") == ASKED[:2], rows
        shown = "\n".join(model_module.requested_research_lines(reqs))
        assert "asked for a search the run does not allow" in shown, shown
        assert ASKED[0] in shown, shown
    print(
        "  research off  the request is recorded, the card says the run does not "
        "allow it, the agent is asked again with that fact; nothing is called"
    )


if __name__ == "__main__":
    test_the_human_decides_and_the_indicators_only_default()
    test_the_note_forms_parse_including_the_words_he_used()
    test_the_question_never_disappears_while_a_round_remains()
    test_the_agents_recommendation_leaves_a_trace()
    test_the_single_model_path_offers_a_round_too()
    test_one_vocabulary_across_both_paths()
    test_margins_measured_on_live_blind_4s_own_evidence()
    test_a_fired_indicator_shows_its_statistic_not_a_percentage()
    test_an_indicator_that_could_not_be_measured_is_not_a_pass()
    test_the_biology_and_what_lies_beyond_the_data_reach_card_and_run_page()
    test_the_expansion_agent_may_direct_one_literature_search()
    test_a_search_the_run_does_not_allow_is_recorded_and_asked_again()
    print(
        "EXPANSION OFFER UNIT OK — the indicators set the default and the "
        "human sets the decision; every margin is printed and the agent's "
        "recommendation is never discarded in silence"
    )
