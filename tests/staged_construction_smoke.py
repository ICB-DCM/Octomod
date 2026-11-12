"""A discrimination round built in two calls, base then expansions, with repair.

  1. the base is checked alone and persisted; its gate comes before any variation;
  2. the variation patching a missing reaction (J9) is repaired with its own reply;
  3. each candidate's parameters are the base's full list plus its additions;
  4. the scope card shows each candidate's declared difference from the base;
  5. `redraft:` goes to the expansions, `redraft base:` to construction, with replies;
  6. the candidate set is audited once across the resumes; its concern reaches the card.

    uv run python tests/staged_construction_smoke.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

from _record import ledger_rows, rnd, run_root, work  # noqa: E402
from file_gate_loop import drive  # noqa: E402

from octomod import config  # noqa: E402

RUNS = config.RUNS_DIR


def _call(r0, role: str):
    """A role's agent call in the round (`agent_calls/<role>`: prompt, reply, dossier)."""
    return (r0 / "agent_calls").child(role)


def main() -> int:
    run_id = f"staged_{time.strftime('%H%M%S')}"
    root = run_root(run_id, RUNS)  # the run is one record file
    r0 = rnd(root, 0)
    seen: dict[str, list] = {"scope": [], "base": []}

    def at_pause(payload, _root):
        module = payload["module"]
        if module == "model_base_scope":
            seen["base"].append(payload)
            # (1) the base gate comes before any variation exists
            assert (r0 / "base_model" / "antimony").exists(), "base not persisted"
            if len(seen["base"]) == 1:
                assert not (
                    _call(r0, "expansion") / "reply"
                ).exists(), "a variation was written before the base was approved"
            if len(seen["base"]) == 2:
                # after `redraft base:` the base card says what moved; the stub
                # returns the same base, so: nothing
                card = json.dumps(payload)
                assert "CHANGED SINCE THE BASE YOU SENT BACK: nothing" in card, card[
                    :600
                ]
                assert (r0 / "base_model_previous" / "antimony").exists()
        if module == "model_scope":
            seen["scope"].append(payload)
            prompt = (_call(r0, "expansion") / "prompt").text()
            if len(seen["scope"]) == 1:
                # (2) the repair call saw its own reply and the named problem
                assert (
                    "## previous_reply" in prompt
                ), "repair call without its previous reply"
                assert (
                    "## previous_attempt_errors" in prompt and "J9" in prompt
                ), "repair call without the problem that names the reaction"
                assert "M3_ff_feedback" in prompt
                # (3) full parameter lists, patches applied
                n = {
                    c: len((work(root, 0, c) / "model" / "parameters").get())
                    for c in ("M1_chain", "M2_feedforward", "M3_ff_feedback")
                }
                assert n == {"M1_chain": 6, "M2_feedforward": 7, "M3_ff_feedback": 8}, n
                m3 = (work(root, 0, "M3_ff_feedback") / "model" / "antimony").text()
                assert "/ (1 + D/K_fb)" in m3 and "J7: -> D; k_cat2" in m3, m3
                # (4) the card shows each declared difference
                card = json.dumps(payload)
                assert "differs from the base in: (the base itself)" in card, card[:400]
                assert (
                    "differs from the base in: 1 line(s) appended; + k_cat2" in card
                ), card[:400]
                assert (
                    "redraft base:" in card
                ), "the staged card does not offer redraft base:"
                # (6) the candidate set was audited and its concern is on the card
                assert "checker[structure sanity]: CONCERN" in card, card[:600]
            if len(seen["scope"]) == 2:
                # (5a) a expansions redraft carried the person's words AND the reply
                assert (
                    "## human_feedback" in prompt and "one line per candidate" in prompt
                )
                assert "## previous_reply" in prompt

    rc, gates = drive(
        "abcd_staged",
        run_id,
        answers={
            "model_scope": [
                ("y", "redraft: one line per candidate in the rationale"),
                ("y", "redraft base: name the inducer parameter u_dose"),
                ("n", ""),
            ]
        },
        at_pause=at_pause,
    )
    print(f"exit {rc}; gates: {gates}")
    assert rc == 1, f"the run should stop at the declined scope card, ended {rc}"
    assert gates == [
        "intent",
        "model_base_scope",
        "model_scope",
        "model_scope",
        "model_base_scope",
        "model_scope",
    ], gates
    ledger = ledger_rows(root)
    calls = [e["role"] for e in ledger if e["event"] == "agent_call"]
    assert calls.count("construction") == 2, calls
    assert calls.count("expansion") == 3, calls
    # the audit ran on the candidate set, once: three resumes reached the scope
    # card with the same set, and call_cached answered the other two
    assert calls.count("construction_verification") == 1, calls
    # (5b) the base redraft reached construction with its own previous reply
    cprompt = (_call(r0, "construction") / "prompt").text()
    assert (
        "## previous_reply" in cprompt and "u_dose" in cprompt
    ), "base redraft lost its reply"
    dossier = (_call(r0, "expansion") / "dossier").get()
    assert len(dossier["attempts"]) == 1 and "J9" in json.dumps(
        dossier["attempts"][0]
    ), dossier
    print(
        f"  staged        base gate before expansions; 1 repaired variation; "
        f"full lists 6/7/8; {calls.count('expansions')} expansions calls, "
        f"{calls.count('construction')} construction calls"
    )
    print("\nSTAGED CONSTRUCTION SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
