"""A full run driven through file-mode gates, as the front end drives it, token-free.

  run --gate-mode file  -> exit 3 + `pending_gate` in the record -> answer with
  --gate-answer y       -> ... repeat ... -> exit 0 (or honest non-zero).

  What main() asserts:
  1. the run ends 0, pausing at exactly the expected gates in order (known cases);
  2. the estimation budget card shows the measured agent prompt bytes;
  3. the compile card shows the problem, the reasoning pointer and the checker;
  4. the round assembled across the resumed processes is identifiability-screened;
  5. a `--from-module estimation` re-entry pauses at the compile card again.

    uv run python tests/file_gate_loop.py [testcase]
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable

sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from tests import identifiability_unit  # noqa: E402
from tests._record import pending_gate, rnd, run_root, run_store  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

# The gates a run of this case pauses at, in order, one pause each. The exact
# sequence is asserted, not a count: a re-asked gate or an answer taken by the
# wrong gate shows up as a different sequence. A new gate is added deliberately.
EXPECTED: dict[str, list[str]] = {
    "toy_phos": [
        "intent",
        "model_scope",
        "assembly_cost_boundary",
        "cost_boundary_estimation",
        "evaluation_verdict",
    ],
    # Profiling is automatic when the measured projection is under the spec cap
    # and gated only above it; on these toys it is well under, so no
    # `evaluation_profiling_gate`.
    "toy_decay_params": [
        "intent",
        "model_scope",
        "assembly_cost_boundary",
        "cost_boundary_estimation",
        "evaluation_verdict",
    ],
}


def run_cli(args: list[str]) -> int:
    return subprocess.run([PY, "-m", "octomod", *args], cwd=REPO).returncode


def _captured_cli(args: list[str]) -> tuple[int, str]:
    """The CLI in its own process, its console kept for a failure's detail."""
    proc = subprocess.run(
        [PY, "-m", "octomod", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
    )
    return proc.returncode, proc.stdout[-800:] + proc.stderr[-800:]


def _base(case: str | Path, run_id: str, extra: list[str] | None) -> list[str]:
    """`case` is a library case's name (`testcase/<case>`) or a folder."""
    where = str(case) if isinstance(case, Path) else f"testcase/{case}"
    return [
        "run",
        "--testcase",
        where,
        "--backend",
        "stub",
        "--run-id",
        run_id,
        "--gate-mode",
        "file",
        *(extra or []),
    ]


def _gate_loop(
    base: list[str],
    root,
    cli,
    answers: dict | None,
    max_gates: int,
    collect: list[dict] | None = None,
    at_pause=None,
    resume: bool = False,
    stop_at: str | None = None,
    strict: bool = True,
) -> tuple[int, list[str], str]:
    """Answer the run's gates until it ends, pauses at `stop_at` or has
    paused `max_gates` times. `cli(args) -> (exit code, console)`. Returns
    (exit code, modules that paused, the last console).

    `answers` maps a module to `(answer, note)`, or to a list of them for the
    gate's repeated pauses in order; a module not named, or a list used up, is
    answered `y`. `strict` asserts every pause carries a payload with a
    question and consequences."""
    queues = {
        k: list(v) if isinstance(v, list) else v for k, v in (answers or {}).items()
    }
    gates: list[str] = []
    if resume:
        assert pending_gate(root) is not None, "resume=True needs a paused run"
        rc, out = 3, ""
    else:
        rc, out = cli(base)
    for _ in range(max_gates):
        if rc != 3:
            break
        payload = pending_gate(root)
        if strict:
            assert payload is not None, "exit 3 without a pending gate in the record"
            assert (
                payload["question"] and payload["consequences"]
            ), "gate payload must carry question + consequences"
        payload = payload or {}
        gates.append(str(payload.get("module")))
        if collect is not None:
            collect.append(payload)
        # Called while the run is PAUSED, so a caller can assert what is on
        # the record at decision time. `collect` cannot do this: by the time the list
        # is read the run has finished and every artifact exists.
        if at_pause is not None:
            at_pause(payload, root)
        if payload.get("module") == stop_at:
            break
        spec = queues.get(payload.get("module"), ("y", ""))
        if isinstance(spec, list):
            spec = spec.pop(0) if spec else ("y", "")
        ans, note = spec
        rc, out = cli(
            base + ["--gate-answer", ans] + (["--gate-note", note] if note else [])
        )
    return rc, gates, out


def drive(
    case: str,
    run_id: str,
    extra: list[str] | None = None,
    answers: dict[str, tuple[str, str]] | None = None,
    max_gates: int = 30,
    collect: list[dict] | None = None,
    at_pause=None,
    resume: bool = False,
) -> tuple[int, list[str]]:
    """Run `case` through file gates; return (exit code, modules that paused).

    `resume=True` continues a run already paused at a gate (one put back by
    `restore_run`): its pending gate is answered on the first call, because a
    resume without an answer re-enters the paused module before pausing again."""
    root = run_root(run_id)  # the run is one file; the gate is a group of it
    rc, gates, _ = _gate_loop(
        _base(case, run_id, extra),
        root,
        lambda args: (run_cli(args), ""),
        answers,
        max_gates,
        collect=collect,
        at_pause=at_pause,
        resume=resume,
    )
    assert pending_gate(root) is None or rc == 3, "the pending gate must be consumed"
    return rc, gates


def drive_cards(
    case: str | Path,
    run_id: str,
    answers: dict | None = None,
    stop_at: str | None = None,
    max_gates: int = 20,
) -> tuple[int, list[str], list[dict], str]:
    """A fresh run of `case` through file gates, each process's console kept
    (so several can run at once): returns (exit code, the modules that paused,
    every card's payload, the last console). Stops without answering at
    `stop_at`."""
    run_store(run_id).remove()
    cards: list[dict] = []
    rc, gates, out = _gate_loop(
        _base(case, run_id, None),
        run_root(run_id),
        _captured_cli,
        answers,
        max_gates,
        collect=cards,
        stop_at=stop_at,
        strict=False,
    )
    return rc, gates, cards, out


def check_cost_card_shows_prompt_bytes(cards: list[dict]) -> None:
    """Assert the estimation budget card shows the measured agent prompt bytes."""
    card = next((c for c in cards if c["module"] == "cost_boundary_estimation"), None)
    assert (
        card
    ), f"no estimation budget card was raised; saw {[c['module'] for c in cards]}"
    line = next((ln for ln in card["lines"] if "agent prompt bytes" in ln), None)
    assert line, (
        "the estimation budget card does not show agent prompt bytes — the CPU "
        f"projection is there but the token bill is not:\n  {card['lines']}"
    )
    # Measured bytes beside the declared cap, or "no cap" when none is declared.
    assert "call(s)" in line and ("cap " in line or line.endswith("no cap")), line
    assert any(
        ch.isdigit() for ch in line.split("cap")[0]
    ), f"the line shows a cap but no measured bytes: {line}"
    print(f"  cost card carries the token bill: {line}")


def check_compile_card_lines(cards: list[dict]) -> None:
    """Assert the single model's compile card carries the problem, the pointer to
    the agents' reasoning and the independent checker's summary."""
    card = next((c for c in cards if c["module"] == "assembly_cost_boundary"), None)
    assert card, f"no compile card was raised; saw {[c['module'] for c in cards]}"
    lines = card["lines"]
    assert any(
        ln.startswith("estimation problem: ")
        and "estimated parameters" in ln
        and "training points" in ln
        and "held-out points" in ln
        for ln in lines
    ), f"the compile card lost its problem line:\n  {lines}"
    # the pointer is the command that prints the round's decision record
    assert any(
        ln.startswith("full reasoning of every agent: ./run.sh show ")
        and ln.endswith("/decisions_md")
        for ln in lines
    ), lines
    assert any(
        ln.startswith("independent checker: ") or ln.startswith("checker[")
        for ln in lines
    ), f"the compile card lost the independent checker's summary:\n  {lines}"
    assert any("redraft:" in str(f) for f in card.get("note_forms") or []), card.get(
        "note_forms"
    )
    print(f"  compile card: {lines[0]}")


def check_estimation_reentry_reasks_the_compile_card(case: str, run_id: str) -> None:
    """A `--from-module estimation` re-entry forgets the compile approval, so the
    single-model round pauses at the compile card before anything compiles."""
    root = run_root(run_id)  # the pending gate is a group of the record
    rc = run_cli(
        [
            "run",
            "--testcase",
            f"testcase/{case}",
            "--backend",
            "stub",
            "--run-id",
            run_id,
            "--gate-mode",
            "file",
            "--from-module",
            "estimation",
        ]
    )
    card = pending_gate(root)
    module = card["module"] if card else None
    assert rc == 3 and module == "assembly_cost_boundary", (
        f"a re-entry at estimation must ask the compile card again before the "
        f"compile; it exited {rc} paused at {module}"
    )
    check_compile_card_lines([card])
    print("  re-entry at estimation: paused at the compile card again")


def main(case: str = "toy_phos") -> int:
    run_id = f"filegate_{case}_{time.strftime('%H%M%S')}"
    cards: list[dict] = []
    rc, gates = drive(case, run_id, collect=cards)
    assert rc == 0, f"run ended {rc}, gates answered: {gates}"
    assert len(gates) >= 4, f"expected >=4 gates, saw {gates}"
    if case in EXPECTED:
        assert gates == EXPECTED[case], (
            f"gate sequence differs from the expected one:\n"
            f"  expected {EXPECTED[case]}\n  saw      {gates}"
        )
    check_cost_card_shows_prompt_bytes(cards)
    check_compile_card_lines(cards)
    # This run was assembled across separate processes, one per gate answer, so
    # a screen that relied on the fitting process's memory would be missing.
    identifiability_unit.check_run_screened(
        rnd(run_root(run_id), 0), "resumed run (file-gate)"
    )
    check_estimation_reentry_reasks_the_compile_card(case, run_id)
    print(
        f"FILE-GATE LOOP OK — {len(gates)} gates relayed and "
        f"answered, in the expected order: {gates}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:] or [])))
