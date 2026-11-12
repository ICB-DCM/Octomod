"""A file-gate answer is bound to the gate that paused the run.

  1. only the gate the record's `pending_gate` names takes the answer; another gate pauses;
  2. the gate it names applies it;
  3. the same module in another round does not take it;
  4. with nothing pending, the first gate takes the answer;
  5. a profiling decline the run continues past is recorded.

    uv run python tests/gate_binding_unit.py
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
from _record import temp_record  # noqa: E402

from octomod.orchestration.interaction import humangate  # noqa: E402


def _ask(module: str, ledger, round_idx: int = 0):
    with redirect_stdout(io.StringIO()):
        return humangate.ask(
            "question?",
            ["evidence"],
            ledger=ledger,
            module=module,
            round_idx=round_idx,
            consequences=("yes", "no"),
        )


def _reset() -> None:
    humangate._FILE_MODE.update(enabled=False, root=None, answer=None, note="")


def test_answer_goes_only_to_its_gate() -> None:
    with temp_record("gate_binding") as root:
        humangate.pending_path(root).put({"module": "evaluation_verdict", "round": 0})
        try:
            humangate.configure_file_mode(root, True, "expand: yes")
            led = RecordingLedger()
            try:
                _ask("evaluation_profiling_gate", led)
            except humangate.GatePending:
                payload = humangate.pending_path(root).get()
            else:
                raise AssertionError("a different gate consumed the bound answer")
            assert not any(
                r["event"] == "human_gate" for r in led.rows
            ), "the profiling gate must not record an answer it was not given"
            assert payload.get("module") == "evaluation_profiling_gate", payload
            assert any("not applied" in str(r.get("note")) for r in led.rows), led.rows
        finally:
            _reset()
    print("  bound       a verdict answer is not taken by the profiling gate met first")


def test_answer_reaches_its_gate() -> None:
    with temp_record("gate_binding") as root:
        humangate.pending_path(root).put({"module": "evaluation_verdict", "round": 0})
        try:
            humangate.configure_file_mode(root, True, "expand: yes")
            led = RecordingLedger()
            ok, note = _ask("evaluation_verdict", led)
            assert ok and note == "expand: yes", (ok, note)
        finally:
            _reset()
    print("  matched     the same answer is applied at the gate it names")


def test_same_module_other_round_is_not_it() -> None:
    with temp_record("gate_binding") as root:
        humangate.pending_path(root).put({"module": "model_scope", "round": 0})
        try:
            humangate.configure_file_mode(root, True, "axes: a")
            try:
                _ask("model_scope", RecordingLedger(), round_idx=1)
            except humangate.GatePending:
                pass
            else:
                raise AssertionError("round 1's scope gate took round 0's answer")
        finally:
            _reset()
    print("  round       a scope answer for round 0 is not taken by round 1")


def test_unbound_answer_keeps_old_behaviour() -> None:
    with temp_record("gate_binding") as root:
        # no pending_gate in the record: a re-entry, nothing to bind
        try:
            humangate.configure_file_mode(root, True, "")
            ok, _ = _ask("model_scope", RecordingLedger())
            assert ok
        finally:
            _reset()
    print("  unbound     with nothing pending, the first gate takes it (as before)")


def test_continuing_profile_decline_is_recorded() -> None:
    src = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    i = src.index('module="evaluation_profiling_gate",')
    assert (
        'record_decline=goal != "parameter_values"' in src[i : i + 700]
    ), "a profiling decline the run continues past must be recorded"
    print("  decline     a profiling 'no' the run continues past is recorded")


def main() -> int:
    test_answer_goes_only_to_its_gate()
    test_answer_reaches_its_gate()
    test_same_module_other_round_is_not_it()
    test_unbound_answer_keeps_old_behaviour()
    test_continuing_profile_decline_is_recorded()
    print("GATE BINDING UNIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
