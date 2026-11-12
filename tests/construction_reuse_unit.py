"""A construction reply that passed is reused on resume, whatever failed before it,
and a human redraft never runs in minimal-repair mode against those stale failures.

    uv run python tests/construction_reuse_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration.interaction import retry  # noqa: E402
from octomod.workflow_modules.model.engine import (  # noqa: E402
    _backfill_passed,
    _reuse_cached_reply,
)
from tests._record import rnd, temp_record  # noqa: E402


def main() -> int:
    with temp_record() as root:
        return _run(root)


def _run(root) -> int:
    calls = rnd(root, 0) / "agent_calls" / "construction"
    dossier = calls / "dossier"
    cached = calls / "reply"
    cached.put({})

    # no attempts, reply in the record, first pass: reuse
    h = retry.AttemptHistory(dossier)
    assert _reuse_cached_reply(cached, h, {}, True)
    assert not _reuse_cached_reply(cached, h, {}, False), "only the first pass"
    assert not _reuse_cached_reply(cached, h, {"human_feedback": "x"}, True)
    assert not _reuse_cached_reply(calls / "missing", h, {}, True)

    # one failed attempt, nothing passed yet: the reply in the record IS the
    # failed draft — call again, and minimal repair applies
    h.add(["entity_glossary incomplete: glossary names species ['P9']"], {})
    assert h.last_draft_failed
    assert not _reuse_cached_reply(cached, h, {}, True)

    # the next draft passed: the reply in the record is good, and a resume reuses it
    h.mark_passed()
    assert h.passed_attempt == 2, h.passed_attempt
    assert not h.last_draft_failed
    assert _reuse_cached_reply(cached, h, {}, True)
    # ...persisted, so the resumed PROCESS sees it
    h2 = retry.AttemptHistory(dossier)
    assert h2.passed_attempt == 2 and len(h2) == 1
    assert _reuse_cached_reply(cached, h2, {}, True)
    # a human redraft still calls fresh, and is not a repairable failure
    assert not _reuse_cached_reply(cached, h2, {"human_feedback": "add S0b"}, True)
    assert not h2.last_draft_failed

    # a fresh call clears the record; a new failure keeps it cleared
    h2.clear_passed()
    assert retry.AttemptHistory(dossier).passed_attempt is None
    h2.mark_passed()
    h2.add(["fewer than two candidates survived"], {})
    assert h2.passed_attempt is None and h2.last_draft_failed
    assert not _reuse_cached_reply(cached, h2, {}, True)
    # a legacy dossier without a pass record: failures only, and
    # `space/candidates` written after its last line. The record keeps no
    # modification times, so "written after" is the artifact's presence
    # (`_backfill_passed`): absent, nothing to backfill; present, backfilled.
    legacy_round = rnd(root, 1)
    legacy = legacy_round / "agent_calls" / "construction" / "dossier"
    legacy.put({"attempts": [{"attempt": 1, "gate_failures": ["x"]}], "grants": []})
    cands = legacy_round / "space" / "candidates"
    h3 = retry.AttemptHistory(legacy)
    assert not h3.has_pass_record and h3.last_draft_failed
    assert not _backfill_passed(
        h3, [cands]
    ), "no passed-only artifact: nothing to backfill"
    cands.put([])
    assert _backfill_passed(h3, [cands]) and h3.passed_attempt == 2
    assert _reuse_cached_reply(cached, h3, {}, True)
    h4 = retry.AttemptHistory(legacy)
    assert h4.has_pass_record and h4.passed_attempt == 2, "backfill persisted"
    assert not _backfill_passed(h4, [cands]), "backfilled once, never again"
    # once the record exists a stale space/candidates proves nothing
    h4.clear_passed()
    assert retry.AttemptHistory(legacy).has_pass_record
    assert not _backfill_passed(retry.AttemptHistory(legacy), [cands])
    print("construction_reuse_unit: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
