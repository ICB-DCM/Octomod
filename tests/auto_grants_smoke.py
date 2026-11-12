"""`--auto-approve` grants at most `retry.auto_grants` extra attempts at an exhaustion gate.

It grants once, as one grant, then answers `n` with "auto mode: grant cap (N) reached",
and the run stops with the failing check shown. Fixture: `abcd_mechanism` with a
`candidates` list in construction's reply, so every construction reply is refused.

    uv run python tests/auto_grants_smoke.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# `test_runs/` under the battery (tests/run_all.py sets OCTOMOD_RUNS_DIR),
# `runs/` otherwise; a suite never spells `runs/` itself.
RUNS = config.RUNS_DIR

SPEC_PATH = REPO / "workflows" / "test_redraft.yaml"


def _write_candidates(construction_json: Path) -> None:
    """Give construction's reply a `candidates` list, which the engine refuses
    on every draft (construction writes the base only), so every reply fails."""
    data = json.loads(construction_json.read_text())
    data["candidates"] = [
        {"id": "M1_extra", "label": "a candidate construction may not write"}
    ]
    construction_json.write_text(json.dumps(data, indent=2))


def main() -> int:
    spec = WorkflowSpec.load(SPEC_PATH)
    budgeted = int(spec.require("retry.module_draft")) + 1  # model._draft_once
    cap = int(spec.require("retry.auto_grants"))
    rid = f"autogrants_{time.strftime('%H%M%S')}"
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "abcd_refused_static"
        shutil.copytree(
            REPO / "testcase" / "abcd_mechanism",
            case,
            ignore=shutil.ignore_patterns("tried_models.json"),
        )
        _write_candidates(case / "stubs" / "construction.json")
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "octomod",
                "run",
                "--testcase",
                str(case),
                "--backend",
                "stub",
                "--auto-approve",
                "--run-id",
                rid,
                "--workflow",
                str(SPEC_PATH.relative_to(REPO)),
            ],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=REPO,
        )
    root = run_root(rid, RUNS)
    rows = ledger_rows(root)
    calls = [
        e for e in rows if e["event"] == "agent_call" and e["role"] == "construction"
    ]
    print(
        f"  construction calls: {len(calls)} = {budgeted} budgeted "
        f"(1 + retry.module_draft {budgeted - 1}) + {cap} auto-granted (retry.auto_grants)"
    )
    assert (
        len(calls) == budgeted + cap
    ), f"expected {budgeted + cap} calls, saw {len(calls)}"

    grants = [e for e in rows if e["event"] == "redraft_grant"]
    assert len(grants) == 1 and grants[0]["granted"] == cap, grants
    gates = [
        e
        for e in rows
        if e["event"] == "human_gate" and e["module"] == "model_redraft_budget"
    ]
    assert (
        len(gates) == 2
    ), f"expected two exhaustion-gate answers, saw {len(gates)}: {gates}"
    first, second = gates
    assert first["approved"] is True and first["mode"] == "auto", first
    assert f"n={cap}" in first["note"], first["note"]
    assert second["approved"] is False and second["mode"] == "auto", second
    assert f"auto mode: grant cap ({cap}) reached" in second["note"], second["note"]
    print(f"  first answer:  {first['note']}")
    print(f"  second answer: {second['note'][:96]}")

    # the run ends honestly, and the failing check is shown — on the card the
    # auto answer followed, in the dossier the ModuleFailure names, in the record
    end = [e for e in rows if e["event"] == "run_end"][-1]
    assert end["outcome"] == "stopped", end
    assert proc.returncode == 1, f"expected exit 1, got {proc.returncode}"
    assert (
        f"auto mode: grant cap ({cap}) reached" in proc.stdout
    ), "the stop is not on the console"
    calls_node = rnd(root, 0) / "agent_calls"
    dossier = (calls_node.child("construction") / "dossier").get()
    last = dossier["attempts"][-1]
    assert last["gate_failures"], last
    print(f"  attempts in the dossier: {len(dossier['attempts'])}")
    print(f"  failing check shown: {str(last['gate_failures'][0])[:120]}")
    assert (
        str(last["gate_failures"][0])[:60] in proc.stdout or "base only" in proc.stdout
    ), "the failing check is not on the console"
    print(
        f"AUTO GRANTS OK — {budgeted}+{cap} construction calls, then `n` with the cap "
        f"note; exit 1, outcome {end['outcome']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
