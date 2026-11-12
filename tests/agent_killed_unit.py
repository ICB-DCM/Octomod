"""A killed agent call is not retried as a bad reply, and every aborted call
leaves a ledger row.

  1. a signal kill (negative return code or 128+signal) raises AgentKilled, naming it;
  2. the fill loop does not retry a kill and writes a `replies/<n>/killed` record;
  3. every aborted LLM call is ledgered as `agent_call_aborted`, cost unknown, not zero;
  4. a malformed reply is still retried.

    uv run python tests/agent_killed_unit.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import agents as A  # noqa: E402
from octomod.agents import llm_backend as B  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


class _Spec(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)

    def model_for_role(self, name):
        return "test-model"

    def effort_for_role(self, name):
        return "xhigh"


def test_a_signal_kill_is_named():
    real = B.subprocess.run
    for code, name in ((-15, "SIGTERM"), (143, "SIGTERM"), (-9, "SIGKILL")):
        B.subprocess.run = lambda *a, c=code, **k: subprocess.CompletedProcess(
            a, c, "", ""
        )
        try:
            B.run_llm("p", "m", 0)
        except A.AgentKilled as e:
            assert name in str(e), str(e)
        else:
            raise AssertionError(f"return code {code} was not read as a kill")
        finally:
            B.subprocess.run = real
    print("  killed        -15, 143 and -9 are kills, named SIGTERM / SIGKILL")


def test_a_kill_is_not_retried():
    calls = []

    def fake(text, model, timeout_s, workdir=None, allowed_tools=(), effort=None):
        calls.append(1)
        raise A.AgentKilled("`claude -p` was killed by SIGTERM (model m)")

    with temp_record() as root:
        call = rnd(root, 0) / "agent_calls" / "construction"
        real, A.run_llm = A.run_llm, fake
        try:
            A._fill_from_llm(
                A.ROLES["construction"], "prompt", _Spec({"retry.agent_json": 2}), call
            )
        except A.AgentKilled as e:
            assert e.attempt == 1
        else:
            raise AssertionError("a killed call returned")
        finally:
            A.run_llm = real
        assert calls == [1], f"a killed call was retried: {len(calls)} calls"
        assert (call / "replies/1/killed").exists()
    print(
        "  no retry      one call, a replies/1/killed record, the attempt on the error"
    )


def test_every_aborted_call_is_ledgered():
    for exc, killed in (
        (A.AgentKilled("killed by SIGTERM"), True),
        (A.AgentCallError("timed out"), False),
    ):
        with temp_record() as root:
            led = Ledger(root.store)

            def fake_fill(rs, prompt, spec, call, _e=exc):
                raise _e

            real, A._fill_from_llm = A._fill_from_llm, fake_fill
            try:
                A.call_agent(
                    "construction",
                    {"intent": "q"},
                    spec=_Spec(),
                    backend="llm",
                    calls=rnd(root, 0) / "agent_calls",
                    ledger=led,
                    module="model",
                )
            except A.AgentCallError:
                pass
            else:
                raise AssertionError("an aborted call returned")
            finally:
                A._fill_from_llm = real
            rows = [r for r in led.entries() if r.get("event") == "agent_call_aborted"]
            assert (
                len(rows) == 1
                and rows[0]["killed"] is killed
                and rows[0]["cost_unknown"]
            ), rows
            assert rows[0]["cost_usd"] is None and rows[0]["prompt_bytes"] > 0, rows
            assert not [
                r for r in led.entries() if r.get("event") == "agent_call"
            ], "an aborted call counted as a call"
    print(
        "  ledgered      killed and timed-out calls leave an aborted row, cost unknown"
    )


def test_a_malformed_reply_is_still_retried():
    calls = []

    def fake(text, model, timeout_s, workdir=None, allowed_tools=(), effort=None):
        calls.append(1)
        return (
            "not json"
            if len(calls) == 1
            # a contract-shaped reply: the engine types the top-level keys
            # (`result.agent_replies.contract_failures`), so `[]` everywhere
            # would itself be a malformed reply
            else json.dumps(
                {
                    "network": {},
                    "antimony": "",
                    "parameters": [],
                    "build_report": {},
                    "consulted_sources": [],
                    "entity_glossary": {},
                }
            )
        ), {}

    with temp_record() as root:
        call = rnd(root, 0) / "agent_calls" / "construction"
        real, A.run_llm = A.run_llm, fake
        try:
            A._fill_from_llm(
                A.ROLES["construction"], "prompt", _Spec({"retry.agent_json": 2}), call
            )
        finally:
            A.run_llm = real
    assert len(calls) == 2, calls
    print("  malformed     a bad reply is still re-asked (2 calls)")


if __name__ == "__main__":
    test_a_signal_kill_is_named()
    test_a_kill_is_not_retried()
    test_every_aborted_call_is_ledgered()
    test_a_malformed_reply_is_still_retried()
    print(
        "\nAGENT KILLED UNIT OK — a kill stops the call, and every aborted call is on the ledger"
    )
