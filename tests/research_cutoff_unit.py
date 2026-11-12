"""The research horizon is read from the testcase first, the workflow spec second.

  1. the testcase value wins and reaches the restrictions string the agent is handed;
  2. the workflow default still applies when the testcase is silent;
  3. the engine-side filter drops items past that horizon, whatever the agent returns;
  4. the four staged CTD cases carry the horizons their write-ups claim.

    uv run python tests/research_cutoff_unit.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import yaml  # noqa: E402
from _harness import CallLedger  # noqa: E402

from octomod.workflow_modules.model.engine import _maybe_research  # noqa: E402
from tests._record import record_at, rnd  # noqa: E402


def _ctx(tmp: Path, testcase: dict, spec: dict, returned_items: list):
    """The smallest object `_maybe_research` actually touches."""
    seen = {}

    def call(hole, payload):
        seen["hole"] = hole
        seen["payload"] = payload
        return {"evidence_items": returned_items}

    ctx = types.SimpleNamespace(
        testcase=testcase,
        spec=spec,
        round=rnd(record_at(tmp / "run"), 0),  # a round of a record
        testcase_dir=tmp,
        ledger=CallLedger(),
        intent={"question": "q"},
        description="d",
        round_idx=0,
        call=call,
    )
    return ctx, seen


def _run(tmp: Path, testcase: dict, spec: dict, items: list):
    tmp.mkdir(parents=True, exist_ok=True)  # the (real) testcase directory
    ctx, seen = _ctx(tmp, testcase, spec, items)
    kept = _maybe_research(ctx)
    return kept, seen, ctx


def test_the_testcase_value_wins_and_reaches_the_agent(tmp: Path):
    _, seen, _ = _run(
        tmp / "a",
        {"research": {"enabled": True, "max_publication_year": 2026}},
        {"research.max_publication_year": 2025},
        [],
    )
    text = seen["payload"]["restrictions"]
    assert "up to 2026 inclusive" in text, text
    assert "2025" not in text, text
    print("  precedence    testcase 2026 beats spec 2025, and the agent is told 2026")


def test_the_workflow_default_still_applies(tmp: Path):
    _, seen, _ = _run(
        tmp / "b",
        {"research": {"enabled": True}},
        {"research.max_publication_year": 2025},
        [],
    )
    assert "up to 2025 inclusive" in seen["payload"]["restrictions"]
    print("  fallback      testcase silent -> the workflow spec's 2025 is used")


def test_the_filter_uses_the_same_number(tmp: Path):
    """The restriction text is a request. The filter is the rule."""
    items = [
        {"title": "old", "year": 2024, "source": "s", "url": "u"},
        {"title": "boundary", "year": 2026, "source": "s", "url": "u"},
        {"title": "future", "year": 2027, "source": "s", "url": "u"},
    ]
    kept, _, ctx = _run(
        tmp / "c",
        {"research": {"enabled": True, "max_publication_year": 2026}},
        {"research.max_publication_year": 2025},
        list(items),
    )
    titles = [i["title"] for i in kept]
    assert titles == ["old", "boundary"], titles

    kept2, _, _ = _run(
        tmp / "d",
        {"research": {"enabled": True}},
        {"research.max_publication_year": 2025},
        list(items),
    )
    assert [i["title"] for i in kept2] == ["old"], kept2
    print("  filter        2027 dropped at 2026; 2026 dropped at 2025 — same number")


def test_the_staged_ctd_cases_carry_the_horizons_they_claim():
    want = {
        "ctd_blind": None,  # must never see the 2026 paper
        "ctd_petab": None,  # same reproduction contract
        "ctd_positional": 2026,  # its premise is building on that paper
        "ctd_countonly": 2026,  # its control — identical access, or it is not one
    }
    for case, year in want.items():
        d = yaml.safe_load((REPO / "testcase" / case / "testcase.yaml").read_text())
        got = (d.get("research") or {}).get("max_publication_year")
        assert got == year, f"{case}: horizon {got!r}, expected {year!r}"
    # and the two that may read it must not also blocklist it
    for case in ("ctd_positional", "ctd_countonly"):
        lines = [
            ln.strip()
            for ln in (REPO / "testcase" / case / "blocklist.txt")
            .read_text()
            .splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        assert lines == [], f"{case} blocks {lines} while its horizon admits the paper"
    for case in ("ctd_blind", "ctd_petab"):
        text = (REPO / "testcase" / case / "blocklist.txt").read_text()
        active = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
        assert any("1014531" in ln for ln in active), f"{case} does not block the paper"
    print("  staged cases  blind/petab blocked at 2025, positional pair open to 2026")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        test_the_testcase_value_wins_and_reaches_the_agent(tmp)
        test_the_workflow_default_still_applies(tmp)
        test_the_filter_uses_the_same_number(tmp)
    test_the_staged_ctd_cases_carry_the_horizons_they_claim()
    print(
        "RESEARCH CUTOFF UNIT OK — the horizon is the case's, the filter enforces "
        "it, and the four CTD cases carry the horizons their write-ups claim"
    )
