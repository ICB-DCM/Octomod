"""A `redraft:` at the expansion card sends the proposal back to the expansion
agent with the person's words, and the card is asked again.

`testcase/abcd_expansion` is copied with one more stub reply, `revision.4.json`
(the redrafted proposal); the first card is answered `y` + `redraft: …`:

  1. that answer buys nothing: no `expansion` record, round 1 not started;
  2. the agent is called once more; its prompt carries the words and the previous reply;
  3. the card is asked again, and says it was redrafted and what moved;
  4. answering the second card re-calls nobody and buys the space from the new proposal;
  5. the ledger attributes the request to the human.

    uv run python tests/expansion_redraft_smoke.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish, run_cli_captured  # noqa: E402
from _record import ledger_rows, pending_gate, rnd, run_root  # noqa: E402

# where runs are written: `test_runs/` under the battery (run_root reads
# config.RUNS_DIR, which the battery redirects)
RUN_ID = "expansion_redraft_smoke"
WORDS = "say why the BX-11 arm needs a KinA route rather than a leak"


def _fixture() -> Path:
    case = Path(tempfile.mkdtemp()) / "abcd_expansion_redraft"
    shutil.copytree(
        REPO / "testcase" / "abcd_expansion",
        case,
        ignore=shutil.ignore_patterns("truth"),
    )
    stubs = case / "stubs"
    redrafted = json.loads((stubs / "revision.3.json").read_text())
    redrafted["diagnosis"] = (
        "STUB call 4, revised at the person's request: a leak of PreC to ProD "
        "would run at the same rate in every arm and could not make ProD rise "
        "faster at u=4 under BX-11 than at u=1; a route catalysed by active "
        "KinA scales with the input, which is what the BX-11 arms show."
    )
    (stubs / "revision.4.json").write_text(json.dumps(redrafted, indent=2))
    return case


def _ledger(root) -> list[dict]:
    return ledger_rows(root)


def main() -> int:
    root = run_root(RUN_ID)  # the run is one record file
    if root.exists():
        root.store.remove()
    case = _fixture()
    base = [
        "run",
        "--testcase",
        str(case),
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--gate-mode",
        "file",
    ]
    rd0 = rnd(root, 0)

    def module() -> str:
        return pending_gate(root)["module"]

    rc, out = run_cli_captured(base)
    scope_answers = [("y", "axes: product_feedback")]
    for _ in range(30):
        if rc != 3 or module() == "revision":
            break
        ans, note = (
            scope_answers.pop(0)
            if module() == "model_scope" and scope_answers
            else ("y", "")
        )
        rc, out = run_cli_captured(
            base + ["--gate-answer", ans] + (["--gate-note", note] if note else [])
        )
    check(
        "the run pauses at the expansion card",
        rc == 3 and module() == "revision",
        f"rc={rc}",
    )
    calls_before = [
        e
        for e in _ledger(root)
        if e.get("event") == "agent_call" and e.get("role") == "revision"
    ]

    # --- the redraft ------------------------------------------------------
    rc, out = run_cli_captured(
        base + ["--gate-answer", "y", "--gate-note", f"redraft: {WORDS}"]
    )
    check(
        "the redraft answer pauses at the expansion card again",
        rc == 3 and module() == "revision",
        f"rc={rc}\n{out[-600:]}",
    )
    check(
        "… and bought nothing",
        not (rd0 / "expansion").exists() and not rnd(root, 1).exists(),
    )
    check(
        "the engine read the redraft back",
        "read from your note: redraft" in out,
        out[-800:],
    )
    rows = _ledger(root)
    calls = [
        e
        for e in rows
        if e.get("event") == "agent_call" and e.get("role") == "revision"
    ]
    check(
        "the expansion agent was called exactly once more",
        len(calls) == len(calls_before) + 1,
        f"{len(calls_before)} -> {len(calls)}",
    )
    prompt = rd0 / "agent_calls/revision/prompt"
    text = prompt.text("") if prompt.exists() else ""
    check(
        "its prompt carries the person's words and the proposal they read",
        WORDS in text
        and "previous_reply" in text
        and "ghost axis is withdrawn" in text,
        f"prompt {'found' if text else 'missing'} at {prompt.key}",
    )
    card = pending_gate(root) or {}
    shown = "\n".join(str(x) for x in card.get("lines") or [])
    check(
        "the card says it was redrafted and what moved",
        "REDRAFTED at your request" in shown
        and "kept: basal_route" in shown
        and "revised at the person's request" in shown,
        shown[:900],
    )
    check(
        "the redraft form is on the card",
        any("redraft:" in str(f) for f in card.get("note_forms") or []),
        str(card.get("note_forms")),
    )
    asked = [
        e
        for e in rows
        if e.get("event") == "note"
        and e.get("human_redraft")
        and e.get("role") == "revision"
    ]
    check(
        "the request is on the ledger, attributed to the human",
        len(asked) == 1,
        str(asked)[:300],
    )

    # --- the answer to the redrafted card ----------------------------------
    rc, out = run_cli_captured(base + ["--gate-answer", "y"])
    rows = _ledger(root)
    calls_after = [
        e
        for e in rows
        if e.get("event") == "agent_call"
        and e.get("role") == "revision"
        and e.get("round") == 0
    ]
    check(
        "answering the redrafted card re-called nobody",
        len(calls_after) == len(calls),
        f"{len(calls)} -> {len(calls_after)}",
    )
    exp = (rd0 / "expansion").get(None) or {}
    check(
        "the enlarged space was bought from the new proposal",
        exp.get("expanded") and exp.get("axes") == ["basal_route"],
        str(exp)[:300],
    )
    shutil.rmtree(case.parent, ignore_errors=True)
    return finish(
        "\nEXPANSION REDRAFT",
        "\nEXPANSION REDRAFT OK — a person can send the expansion proposal back with their words",
    )


if __name__ == "__main__":
    sys.exit(main())
