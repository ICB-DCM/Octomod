"""The report honours an accepted convergence, and the budget gate can pre-declare it.

  1. the rendered round report and ANALYSIS show the failed checks, values and reason;
  2. the budget gate offers, parses and ledgers a pre-declared accept.

    uv run python tests/convergence_report_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.estimation import convergence_record as cr  # noqa: E402
from tests._record import record_at, rnd  # noqa: E402

ACCEPT_ROW = {
    "event": "note",
    "module": "estimation_convergence",
    "round_idx": 0,
    "note": "convergence accepted by human for this model: plateau expected here",
    "convergence": "accepted-by-human",
    "failed_checks": ["estimation_waterfall_plateau", "estimation_gradient_norm"],
    "failed_measured": [
        {
            "gate_id": "estimation_waterfall_plateau",
            "tier": "T2",
            "value": 1,
            "threshold": 3,
            "detail": "1 start within 0.5 nllh of the best",
        },
        {
            "gate_id": "estimation_gradient_norm",
            "tier": "T2",
            "value": 47.2,
            "threshold": 10,
            "detail": "gradient norm at the best start",
        },
    ],
    "accept_reason": "plateau expected at this model size",
    "candidate": None,
}


def _round_with(ledger_rows: list[dict], core: dict | None = None):
    # the fixture is a record file, not a directory
    tmp = record_at(Path(tempfile.mkdtemp(prefix="convrep_")) / "run")
    tmp.store.create()
    tmp.store.replace_ledger([{"ts": "2026-01-01T00:00:00", **r} for r in ledger_rows])
    r0 = rnd(tmp, 0)
    body = core or {}
    (r0 / "evaluation_core").put(body)
    (r0 / "evaluation").put(body)
    return tmp


# ---------------------------------------------------------------- the report


def test_the_estimation_section_shows_the_checks_the_values_and_the_reason():
    from octomod.reporting.round_report import render_report_html

    tmp = _round_with([ACCEPT_ROW])
    html = render_report_html(rnd(tmp, 0))
    assert (
        "NOT DEMONSTRATED" in html
    ), "the report does not say convergence was accepted"
    for gid in ("estimation_waterfall_plateau", "estimation_gradient_norm"):
        assert gid in html, f"{gid} is not named in the report"
    # the MEASURED values against their THRESHOLDS, not just the names
    assert "47.2" in html and "10" in html, "the gradient-norm measurement is missing"
    assert (
        "measured 1 against threshold 3" in html
    ), "the plateau check's measured value against its threshold is missing"
    assert (
        "plateau expected at this model size" in html
    ), "the human's reason does not appear"
    print("  estimation    failed checks, measured vs threshold, and the reason")


def test_the_epistemics_section_caveats_nonetheless_determined():
    from octomod.reporting.round_report import render_report_html

    core = {
        "computed_nonetheless_determined": ["k_on is determined to 0.3 decades"],
        "computed_cannot_distinguish": [],
    }
    tmp = _round_with([ACCEPT_ROW], core)
    html = render_report_html(rnd(tmp, 0))
    i_caveat = html.find("rest on a fit whose convergence was")
    i_claim = html.find("Nonetheless determined")
    assert i_caveat > 0, "the epistemics section carries no convergence caveat"
    assert i_caveat < i_claim, (
        "the caveat renders BELOW the claims it qualifies — a reader meets the "
        "claim first"
    )
    assert "pinned down" in html and "given" in html, html[i_caveat : i_caveat + 400]
    print("  epistemics    the caveat renders ABOVE the claims it qualifies")


def test_a_clean_run_carries_no_caveat_anywhere():
    """The caveat is absent when convergence was demonstrated."""
    from octomod.reporting.round_report import render_report_html

    html = render_report_html(rnd(_round_with([]), 0))
    for phrase in ("NOT DEMONSTRATED", "rest on a fit whose convergence was"):
        assert phrase not in html, f"a clean run shows {phrase!r}"
    print("  clean run     no caveat when convergence was demonstrated")


def test_the_run_level_analysis_lists_it_as_still_open():
    from octomod.reporting.analysis_report import build as build_analysis
    from octomod.reporting.analysis_report import render_html

    tmp = _round_with([ACCEPT_ROW])
    summary = build_analysis(tmp)
    hits = [s for s in summary["still_open"] if "ACCEPTED" in s]
    assert hits, f"not in still_open: {summary['still_open']}"
    assert (
        "estimation_waterfall_plateau" in hits[0] and "plateau expected" in hits[0]
    ), hits[0]
    html = render_html(summary)
    assert (
        "ACCEPTED, not" in html and "estimation_gradient_norm" in html
    ), "the run-level HTML does not carry it"
    print("  run level     listed in still_open and rendered in ANALYSIS")


def test_a_pre_declared_accept_reads_differently_from_a_post_hoc_one():
    from octomod.reporting.round_report import render_report_html

    pre = {**ACCEPT_ROW, "convergence": "pre-declared-by-human"}
    html = render_report_html(rnd(_round_with([pre]), 0))
    assert "PRE-DECLARED" in html, "a pre-declaration is not distinguishable"
    assert "before the fit ran" in html, html[html.find("PRE-DECLARED") :][:300]
    post = render_report_html(rnd(_round_with([ACCEPT_ROW]), 0))
    assert "PRE-DECLARED" not in post and "after seeing the numbers" in post
    print("  provenance    pre-declared and post-hoc accepts read differently")


def test_each_candidate_carries_only_its_own_accept():
    """Round scope would put one candidate's caveat on every other one."""
    rows = [
        {**ACCEPT_ROW, "candidate": "M1_fast"},
        {**ACCEPT_ROW, "candidate": "M2_slow", "accept_reason": "different reason"},
    ]
    accepts = cr.accepts_by_candidate(rows)
    assert set(accepts) == {"M1_fast", "M2_slow"}, accepts
    assert accepts["M2_slow"].reason == "different reason"
    assert accepts["M1_fast"].reason == "plateau expected at this model size"
    # and a clean candidate has none at all
    assert "M3_clean" not in accepts
    print("  scope         per candidate; a clean candidate carries nothing")


# ---------------------------------------------------------------- the budget gate


def test_the_budget_gate_pre_declaration_is_offered_parsed_and_ledgered():
    from octomod.workflow_modules.cost_probe.engine import (
        _record_convergence_predeclaration,
    )

    class _L:
        def __init__(self):
            self.rows = []

        def append(self, *a, **k):
            self.rows.append(k)

    class _Ctx:
        def __init__(self):
            self.cache, self.ledger, self.round_idx = {}, _L(), 0

    ctx = _Ctx()
    got = _record_convergence_predeclaration(
        ctx, "y convergence: accept the plateau is expected at this model size"
    )
    assert got and ctx.cache["_convergence_predeclared"] == got, ctx.cache
    row = ctx.ledger.rows[-1]
    assert row.get("convergence_predeclared") is True and row.get("scope") == "round"
    # a reason is required, exactly as at the gate itself
    ctx2 = _Ctx()
    assert _record_convergence_predeclaration(ctx2, "y convergence: accept") is None
    assert "_convergence_predeclared" not in ctx2.cache
    assert "REFUSED" in ctx2.ledger.rows[-1]["note"]
    # and a plain approval declares nothing
    ctx3 = _Ctx()
    assert _record_convergence_predeclaration(ctx3, "y n=50") is None
    print("  pre-declare   parsed, reason required, ledgered round-scoped")


def test_the_gate_offers_it_in_its_note_forms():
    """Offered, not merely accepted — an option nobody is told about is not one."""
    src = (
        REPO / "octomod" / "workflow_modules" / "cost_probe" / "engine.py"
    ).read_text()
    i = src.index("note_forms=[")
    block = src[i : i + 900]
    assert "convergence: accept" in block, "the budget gate does not offer it"
    assert (
        "Integration failures are NOT covered" in block
    ), "the offer does not state its limit"
    print("  offered       the budget gate's note_forms name it and its limit")


def test_integration_failures_are_never_pre_declarable():
    src = (
        REPO / "octomod" / "workflow_modules" / "estimation" / "engine.py"
    ).read_text()
    assert (
        "_cr.NOT_PREDECLARABLE" in src
    ), "the gate does not check the not-coverable set"
    assert "estimation_integration_failures" in cr.NOT_PREDECLARABLE
    assert "estimation_integration_failures" not in cr.PREDECLARABLE
    # and the evidence still prints when the pause IS skipped
    i = src.index("_convergence_predeclared")
    seg = src[i : i + 1400]
    assert (
        "print(summary_text)" in seg
    ), "a pre-declared accept suppresses the card's CONTENT, not only the pause"
    print("  not covered   integration failures still ask; evidence still prints")


if __name__ == "__main__":
    test_the_estimation_section_shows_the_checks_the_values_and_the_reason()
    test_the_epistemics_section_caveats_nonetheless_determined()
    test_a_clean_run_carries_no_caveat_anywhere()
    test_the_run_level_analysis_lists_it_as_still_open()
    test_a_pre_declared_accept_reads_differently_from_a_post_hoc_one()
    test_each_candidate_carries_only_its_own_accept()
    test_the_budget_gate_pre_declaration_is_offered_parsed_and_ledgered()
    test_the_gate_offers_it_in_its_note_forms()
    test_integration_failures_are_never_pre_declarable()
    print(
        "CONVERGENCE REPORT OK — the accept reaches the rendered artifact, the "
        "budget gate can pre-declare it, and hierarchical refuses what it "
        "cannot solve"
    )
