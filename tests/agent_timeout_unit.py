"""A timeout is not a malformed reply, and a crash must still be recorded.

  1. a timeout is not retried by default; `retry.agent_timeout` is its own budget;
  2. a timeout writes its elapsed time and prompt size to the call's record,
     `agent_calls/<role>/replies/<n>/timeout`;
  3. `AgentCallError` reaches the orchestrator, so the run ends with a `run_end` row.

    uv run python tests/agent_timeout_unit.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import octomod.agents as A  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


class _Spec(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)

    def model_for_role(self, name):
        return "test-model"

    def effort_for_role(self, name):
        return "xhigh"  # what the real spec declares (agents.effort.default)


def _role():
    return A.ROLES["construction"]


def _call(root: Node, k: int) -> Node:
    """The construction call's record in round `k` — one round per test, so
    no test reads another's attempts."""
    return (rnd(root, k) / "agent_calls").child("construction")


def _run(call: Node, spec, fail_with: str, calls: list, partial: str = ""):
    """Drive the retry loop with run_llm replaced by a chosen failure.

    The 10 s pause between attempts is recorded instead of slept: what is
    asserted is how many attempts are made, and the wait is asserted to be
    asked for between them rather than spent."""

    def fake(text, model, timeout_s, workdir=None, allowed_tools=(), effort=None):
        calls.append(timeout_s)
        err = A.AgentCallError(fail_with)
        err.partial_stdout = partial
        err.partial_stderr = "some stderr" if partial else ""
        raise err

    waits: list[float] = []
    clock = types.SimpleNamespace(
        perf_counter=A.time.perf_counter, time=A.time.time, sleep=waits.append
    )
    real, A.run_llm = A.run_llm, fake
    real_time, A.time = A.time, clock
    try:
        return A._fill_from_llm(_role(), "prompt", spec, call)
    finally:
        A.run_llm = real
        A.time = real_time
        # one pause between consecutive attempts, none after the last
        assert len(waits) == max(
            0, len(calls) - 1
        ), f"{len(calls)} attempt(s) with {len(waits)} pause(s) between them"


def test_a_timeout_is_not_retried_by_default(root: Node):
    call = _call(root, 1)
    calls: list = []
    spec = _Spec({"agents.timeout_s": 600, "retry.agent_json": 2})
    try:
        _run(call, spec, "`claude -p` timed out after 600s (model x)", calls)
    except A.AgentCallError as e:
        assert "timed out" in str(e), e
        assert len(calls) == 1, f"retried a timeout {len(calls)} times"
        print("  timeout       one attempt, not three — the run stops and says why")
        return
    raise AssertionError("a timeout did not stop the run")


def test_a_timeout_leaves_evidence(root: Node):
    call = _call(root, 2)
    spec = _Spec({"agents.timeout_s": 600, "retry.agent_json": 2})
    try:
        _run(call, spec, "`claude -p` timed out after 600s (model x)", [])
    except A.AgentCallError:
        pass
    written = [
        call / "replies" / n / "timeout"
        for n in (call / "replies").children()
        if (call / "replies" / n / "timeout").exists()
    ]
    assert written, f"no evidence written under {call.key}"
    rec = written[0].get()
    for key in ("attempt", "timeout_s", "elapsed_s", "prompt_bytes", "model"):
        assert key in rec, f"{key} missing from {rec}"
    assert rec["timeout_s"] == 600 and rec["attempt"] == 1, rec
    print(f"  evidence      {written[0].key} records elapsed and prompt size")


def test_a_transient_failure_is_still_retried(root: Node):
    """A transient CLI failure is still retried; only timeouts lose the retries."""
    call = _call(root, 3)
    calls: list = []
    spec = _Spec({"agents.timeout_s": 600, "retry.agent_json": 2})
    try:
        _run(call, spec, "connection reset by peer", calls)
    except A.AgentCallError:
        pass
    assert len(calls) == 3, f"transient failure tried {len(calls)} time(s), want 3"
    print("  transient     a CLI blip still gets its three attempts")


def test_a_timeout_may_be_retried_when_asked(root: Node):
    call = _call(root, 4)
    calls: list = []
    spec = _Spec(
        {"agents.timeout_s": 600, "retry.agent_json": 2, "retry.agent_timeout": 1}
    )
    try:
        _run(call, spec, "`claude -p` timed out after 600s (model x)", calls)
    except A.AgentCallError:
        pass
    assert len(calls) == 2, f"budget 1 gave {len(calls)} attempt(s), want 2"
    print("  configurable  retry.agent_timeout: 1 allows exactly one retry")


def test_the_orchestrator_records_an_agent_failure():
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    assert (
        "except (ModuleFailure, GateFailure, AgentCallError)" in src
    ), "AgentCallError still escapes as a traceback with no run_end"
    head = src[: src.index("except (ModuleFailure, GateFailure, AgentCallError)")]
    assert "from octomod.agents import AgentCallError" in head, "not imported"
    print("  recorded      an exhausted agent call ends the run with a run_end row")


def test_the_partial_reply_is_kept(root: Node):
    """A timed-out call's partial output is kept in the record as the only evidence."""
    call = _call(root, 5)
    spec = _Spec({"agents.timeout_s": 600, "retry.agent_json": 2})
    body = '{"model_antimony": "model m() ... half a model here'
    try:
        _run(call, spec, "timed out after 600s", [], partial=body)
    except A.AgentCallError:
        pass
    first = call / "replies/1"
    kept = first / "partial"
    assert kept.exists(), f"partial output discarded; {first.children()}"
    assert kept.text() == body
    rec = (first / "timeout").get()
    assert rec["partial_stdout_bytes"] == len(body.encode()), rec
    assert (first / "stderr").exists()
    print(f"  partial       {len(body)} bytes of the killed reply kept in the record")


def test_no_timeout_is_expressible(root: Node):
    """`timeout_s: null` means no limit, not a crash in `int(None)` while reading it."""
    call = _call(root, 6)
    calls: list = []
    spec = _Spec({"agents.timeout_s": None, "retry.agent_json": 2})
    try:
        _run(call, spec, "connection reset by peer", calls)
    except A.AgentCallError:
        pass
    assert calls, "no call was made at all"
    assert all(c == 0 for c in calls), f"passed {calls} as the timeout, want 0"
    print("  no limit      timeout_s: null reaches the backend as 'no limit'")


def test_the_shipped_spec_does_not_cut_agents_off():
    """The shipped spec sets no agent timeout while agent durations are measured."""
    import yaml

    spec = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    assert not spec["agents"]["timeout_s"], (
        "workflows/default.yaml sets a finite agent timeout; the measured "
        "history is median 347 s and max 581 s against the old 600 s limit, "
        "which is why this is null while the project is still measuring"
    )
    print("  shipped spec  agents.timeout_s is null — no agent is cut off")


if __name__ == "__main__":
    with temp_record() as root:
        test_a_timeout_is_not_retried_by_default(root)
        test_a_timeout_leaves_evidence(root)
        test_a_transient_failure_is_still_retried(root)
        test_a_timeout_may_be_retried_when_asked(root)
        test_the_partial_reply_is_kept(root)
        test_no_timeout_is_expressible(root)
    test_the_orchestrator_records_an_agent_failure()
    test_the_shipped_spec_does_not_cut_agents_off()
    print(
        "AGENT TIMEOUT UNIT OK — a timeout stops once and leaves evidence, a "
        "blip keeps its patience, and neither ends a run without a record"
    )
