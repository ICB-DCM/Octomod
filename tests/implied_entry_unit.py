"""A resume is not a re-entry: an implied entry at estimation keeps finished work.

  1. an asked-for entry (`--from-module estimation`) still invalidates later markers;
  2. an implied entry (`supplied/petab`, on every invocation) keeps them;
  3. the ledger's `entry_implied` says which it was; the orchestrator sets the flag.

    uv run python tests/implied_entry_unit.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration import round_status  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


class _Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event, **k):
        self.rows.append((event, k))


def _ctx(root: Node):
    """The surface `enter` touches: a single-model round's markers, in the
    record (`rounds/round_0/status/markers/<name>`)."""
    markers = tree.markers_node(rnd(root, 0), None)
    ctx = types.SimpleNamespace(
        root=root,
        round=rnd(root, 0),
        round_idx=0,
        ledger=_Ledger(),
        testcase={},
        spec={},
        markers=markers,
        round_markers=markers,
    )
    ctx.marker = lambda name: markers.child(name)
    ctx.has_marker = lambda name: markers.child(name).exists()

    def set_marker(name, **payload):
        markers.child(name).put(dict(payload))

    ctx.set_marker = set_marker
    return ctx


def _enter(root: Node, *, invalidate: bool, monkeypatched_slots=()):
    ctx = _ctx(root)
    for m in ("cost", "s6", "s7"):
        ctx.marker(m).put({})
    # every upstream slot validates: this test is about invalidation, not
    # validation, and validation has its own suite (petab_entry_smoke).
    real_required, real_validate = round_status.required_before, round_status.validate
    round_status.required_before = lambda module: list(monkeypatched_slots)
    round_status.validate = lambda c, s: (True, [f"slot {s!r}: ok"])
    try:
        round_status.enter(ctx, "estimation", invalidate=invalidate)
    finally:
        round_status.required_before = real_required
        round_status.validate = real_validate
    return ctx


def test_an_asked_for_entry_still_invalidates():
    with temp_record("asked") as root:
        ctx = _enter(root, invalidate=True)
        for m in ("cost", "s6"):
            assert not ctx.marker(m).exists(), f"{m} survived an explicit --from-module"
    row = next(k for e, k in ctx.ledger.rows if e == "entry")
    assert row["entry_implied"] is False, row
    assert "s6" in row["invalidated_markers"], row
    print("  asked for     --from-module estimation still clears cost and s6")


def test_an_implied_entry_keeps_finished_work():
    with temp_record("implied") as root:
        ctx = _enter(root, invalidate=False)
        for m in ("cost", "s6", "s7"):
            assert ctx.marker(m).exists(), f"{m} was cleared on an implied entry"
    row = next(k for e, k in ctx.ledger.rows if e == "entry")
    assert row["entry_implied"] is True, row
    assert row["invalidated_markers"] == [], row
    print("  implied       supplied/petab resume keeps cost, s6 and s7")


def test_the_ledger_says_which_it_was():
    """The ledger tells an asked-for entry from an implied one at the same module."""
    with temp_record("l1") as r1, temp_record("l2") as r2:
        a = _enter(r1, invalidate=True)
        b = _enter(r2, invalidate=False)
    ra = next(k for e, k in a.ledger.rows if e == "entry")
    rb = next(k for e, k in b.ledger.rows if e == "entry")
    assert ra["entry_implied"] != rb["entry_implied"]
    assert ra["from_module"] == rb["from_module"] == "estimation"
    print("  ledger        entry_implied distinguishes the two at the same module")


def test_the_orchestrator_wires_the_flag():
    """The flag is only worth anything if the two call paths actually set it."""
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    assert "self.entry_implied = False" in src, "default not set in __init__"
    assert "self.entry_implied = True" in src, "supplied/petab does not imply entry"
    assert (
        "invalidate=not self.entry_implied" in src
    ), "enter() is called without the flag"
    print("  wiring        orchestrator defaults False, supplied/petab sets True")


if __name__ == "__main__":
    test_an_asked_for_entry_still_invalidates()
    test_an_implied_entry_keeps_finished_work()
    test_the_ledger_says_which_it_was()
    test_the_orchestrator_wires_the_flag()
    print(
        "IMPLIED ENTRY UNIT OK — an asked-for entry redoes the module, an implied "
        "one keeps finished work, and the ledger says which happened"
    )
