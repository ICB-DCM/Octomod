"""Modular entry works on a discrimination round, whose parts sit under `candidates/<id>`.

  1. a per-candidate slot is validated in every candidate, not at round level;
  2. one broken candidate fails the slot: a round fits all of them;
  3. the reasons name the candidate;
  4. a single-model round is untouched by any of this.

    uv run python tests/candidate_entry_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration import round_status as rs  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


class _Ledger:
    def append(self, *a, **k):
        pass


class _Ctx:
    """The RunContext surface `check_intact`/`validate` read, over a record."""

    def __init__(self, rnd_node):
        self.root = tree.Node(rnd_node.store, "")
        self.store = rnd_node.store
        self.round = rnd_node
        self.round_idx = 0
        self.candidate = None
        self.ledger = _Ledger()
        self.spec = {}
        self.testcase = {}
        self.intent = {}

    @property
    def work(self):
        return tree.work_node(self.round, self.candidate)

    @property
    def model(self):
        return tree.model_node(self.round, self.candidate)

    @property
    def gates(self):
        return tree.gates_node(self.round, self.candidate)


def _round_with_candidates(root, ids, missing_in=()):
    r0 = rnd(root, 0)
    (r0 / "space/candidates").put([{"id": i} for i in ids])
    for i in ids:
        if i not in missing_in:
            (tree.model_node(r0, i) / "sbml").put_text("<sbml/>")
    return r0


def test_every_candidate_is_validated():
    """The required part is sought per candidate (the presence step, not the battery)."""
    ids = ["A", "B", "C"]
    with temp_record("ok") as root:
        ctx = _Ctx(_round_with_candidates(root, ids))
        missing, _ = rs.check_intact(ctx, "s1")
    assert missing == [], f"present parts reported missing: {missing}"
    print(f"  per candidate  the model is sought in all {len(ids)} candidates")


def test_one_broken_candidate_fails_the_slot():
    ids = ["A", "B", "C"]
    with temp_record("bad") as root:
        ctx = _Ctx(_round_with_candidates(root, ids, missing_in={"B"}))
        missing, _ = rs.check_intact(ctx, "s1")
    assert missing, "a candidate with no model was accepted"
    assert any(m.startswith("B:") for m in missing), missing
    assert not any(m.startswith("A:") for m in missing), missing
    print(f"  one broken     names the candidate: {missing[0]}")


def test_the_reasons_name_the_candidate():
    ids = ["A", "B"]
    with temp_record("names") as root:
        ctx = _Ctx(_round_with_candidates(root, ids, missing_in={"A", "B"}))
        ok, why = rs.validate(ctx, "model")
    assert ok is False
    joined = " ".join(why)
    assert "2 candidate(s)" in joined, why
    assert "candidates/A/model" in joined and "candidates/B/model" in joined, why
    print("  reasons        each failing candidate is named in the output")


def test_a_single_model_round_is_untouched():
    """No `space/candidates`: the model is validated at round level."""
    with temp_record("single") as root:
        r0 = rnd(root, 0)
        (r0 / "model/antimony").put_text("model m\nend")  # a model, no sbml
        ctx = _Ctx(r0)
        missing, _ = rs.check_intact(ctx, "s1")
    assert missing == ["sbml"], missing
    assert not any("candidates" in m for m in missing), missing
    print("  single model   still validated at round level, no candidate keys")


if __name__ == "__main__":
    test_every_candidate_is_validated()
    test_one_broken_candidate_fails_the_slot()
    test_the_reasons_name_the_candidate()
    test_a_single_model_round_is_untouched()
    print(
        "CANDIDATE ENTRY UNIT OK — a discrimination round can be re-entered, "
        "every candidate is checked, and a failure says which one"
    )
