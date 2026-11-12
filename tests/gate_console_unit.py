"""The gate lines printed at the console are written for a person.

  1. the tier leaves the printed line but stays in the record and in a `GateFailure`;
  2. `[40812 vs 250000]` reads `[40,812 of 250,000]`: a budget, not a comparison;
  3. a passing ladder collapses to one line; failures and flags always print in full;
  4. `OCTOMOD_VERBOSE_GATES=1` restores every line.

    uv run python tests/gate_console_unit.py
"""

from __future__ import annotations

import io
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger  # noqa: E402

from octomod.gates import (  # noqa: E402
    HUMAN_LABELS,
    GateFailure,
    GateResult,
    run_gate_set,
)
from tests._record import rnd, temp_record  # noqa: E402

TIER_RE = re.compile(r"\[T\d'?\]")


def _passing(i: int, blocking: bool = True):
    def f():
        return GateResult(
            f"model_check_{i}", "T0", True, blocking=blocking, detail=f"check {i} ok"
        )

    return f


def _run(gates, ledger=None):
    led = ledger or RecordingLedger()
    buf = io.StringIO()
    with temp_record() as root:
        with redirect_stdout(buf):
            run_gate_set(gates, rnd(root, 0) / "gates", led, "s1")
    return buf.getvalue(), led


def test_the_tier_leaves_the_line_but_not_the_record() -> None:
    r = GateResult(
        "agent_prompt_bytes",
        "T0",
        True,
        value=40812,
        threshold=250000,
        detail="construction prompt is 40,812 bytes (16% of the cap)",
    )
    line = r.summary()
    assert not TIER_RE.search(line), f"the tier still leads the line: {line}"
    assert "40,812 of 250,000" in line, (
        f"the raw pair is still engine-facing: {line} — separators and 'of' "
        f"are what make it a budget rather than a comparison operator"
    )
    assert "vs" not in line
    assert HUMAN_LABELS["agent_prompt_bytes"] in line, "the plain label is missing"

    # the auditor's form, and the record
    assert TIER_RE.search(r.summary(tier=True)), r.summary(tier=True)
    assert r.tier == "T0", "the tier must stay on the dataclass"
    try:
        raise GateFailure(
            GateResult("model_nonnegative_states", "T1", False, detail="neg")
        )
    except GateFailure as e:
        assert TIER_RE.search(str(e)), (
            f"a GateFailure is read after the fact by an auditor — the tier "
            f"belongs there: {e}"
        )

    # and every gate id in the tree has a plain-words label
    ids: set[str] = set()
    for f in (REPO / "octomod").rglob("*.py"):
        s = f.read_text()
        ids |= set(re.findall(r"@gate\(\s*[\"']([a-z0-9_]+)[\"']", s))
        ids |= set(re.findall(r"GateResult\(\s*[\"']([a-z0-9_]+)[\"']", s))
    unlabelled = sorted(i for i in ids if i not in HUMAN_LABELS)
    assert not unlabelled, (
        f"these gates print their raw id at a reader: {unlabelled} — one line "
        f"per check in plain words means every check"
    )
    print(
        f"  tier          off the line, kept in the record; "
        f"{len(ids)} gate ids all labelled"
    )


def test_numbers_read_like_numbers() -> None:
    def val(v, th=None):
        return GateResult(
            "model_check_0", "T0", True, value=v, threshold=th, detail="d"
        )

    assert "[40,812 of 250,000]" in val(40812, 250000).summary()
    assert "[1,099]" in val(1099).summary()
    # 4 significant figures, so 0.056116 -> 0.05612 (not 0.0561)
    assert "[0.05612 of 0.01]" in val(0.056116, 0.01).summary()
    assert "[yes]" in val(True).summary(), "a boolean must not print as 'True'"
    assert "[no]" in val(False).summary()
    assert "[obs_regb_p]" in val("obs_regb_p").summary()
    # a float over 1000 keeps its separator too
    assert "1,099" in val(1099.4).summary()
    print("  numbers       separators, 'of' not 'vs', booleans as yes/no")


def test_a_passing_ladder_is_one_line() -> None:
    out, led = _run([_passing(i) for i in range(13)])
    lines = [x for x in out.splitlines() if x.strip()]
    assert len(lines) == 1, f"13 passing gates printed {len(lines)} lines:\n{out}"
    assert "13 check(s) passed" in lines[0], lines[0]
    assert "in the ledger and in the record's gates" in lines[0], (
        "a collapsed line must say where the detail went, or it reads as a "
        "check that was skipped"
    )
    # NOTHING is lost: the ledger still has every row, with its tier
    gate_rows = [r for r in led.rows if r["event"] == "gate"]
    assert len(gate_rows) == 13, len(gate_rows)
    assert all(r["tier"] == "T0" for r in gate_rows)
    print(f"  collapse      13 lines -> 1, {len(gate_rows)} ledger rows intact")


def test_a_failure_always_prints_in_full() -> None:
    def failing():
        return GateResult(
            "model_nonnegative_states", "T1", False, detail="P goes negative at t=0"
        )

    out, _ = _run([_passing(0), _passing(1), failing, _passing(3)])
    assert "FAILED" in out and "P goes negative at t=0" in out, out
    assert "states stay non-negative" in out, "the plain label must be on it"
    # the passing ones still collapse around it
    assert "2 check(s) passed" in out, out

    # an advisory FLAG is not a pass and must not be collapsed away
    def flag():
        return GateResult(
            "model_declared_constants",
            "T2",
            False,
            blocking=False,
            detail="PreC + ProD drifts 26%",
        )

    out2, _ = _run([_passing(0), flag, _passing(2)])
    assert "⚑ flag" in out2 and "drifts 26%" in out2, out2
    assert HUMAN_LABELS["model_declared_constants"] in out2

    # and a non-blocking PASS is not swept up either: `•` means advisory, and
    # collapsing it would hide that an advisory screen ran and found nothing
    out3, _ = _run([_passing(0, blocking=False), _passing(1)])
    assert "•" in out3, out3
    print("  failures      printed in full; flags and advisories never collapsed")


def test_verbose_restores_every_line() -> None:
    os.environ["OCTOMOD_VERBOSE_GATES"] = "1"
    try:
        out, _ = _run([_passing(i) for i in range(5)])
    finally:
        del os.environ["OCTOMOD_VERBOSE_GATES"]
    lines = [x for x in out.splitlines() if x.strip()]
    assert len(lines) == 5, f"verbose printed {len(lines)} of 5:\n{out}"
    assert "check(s) passed" not in out, "verbose must not also print the summary"
    assert not any(
        TIER_RE.search(x) for x in lines
    ), "verbose restores the LINES, not the tier — that is a separate reader"

    # "0" and "" are off, so an exported-but-empty variable behaves as unset
    for value in ("", "0"):
        os.environ["OCTOMOD_VERBOSE_GATES"] = value
        try:
            out2, _ = _run([_passing(i) for i in range(4)])
        finally:
            del os.environ["OCTOMOD_VERBOSE_GATES"]
        assert "4 check(s) passed" in out2, (value, out2)
    print("  verbose       every line back with =1; '' and '0' are off")


def test_engine_vocabulary_does_not_reach_a_reader() -> None:
    """The engine's word "escalate" is in no gate detail and no agent skill."""
    from octomod.gates import fit_gates

    src = Path(fit_gates.__file__).read_text()
    body = src[src.index("def ") :]
    printed = re.findall(r'(?:detail|f)"([^"]*escalat[^"]*)"', body, re.I)
    assert not printed, f"a gate detail still says it our way: {printed}"

    # the skills: the word the agent is told to use is the word a reader gets
    for name in ("construction", "revision_proposal"):
        text = (REPO / "skills" / f"{name}.md").read_text()
        hits = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"\bescalat", line, re.I)
        ]
        assert not hits, (
            f"skills/{name}.md instructs the agent in the engine's word, so "
            f"the agent writes it into the report: {hits}"
        )

    # and the two surfaces that already said it well must keep saying it
    from octomod.reporting import model_report

    assert "Places needing your input" in Path(model_report.__file__).read_text()
    s1 = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert "THE AGENT ASKS" in s1

    # the spec key keeps its name: `workflow_sha` is compared on resume, so a
    # rename would refuse every paused run, and the key is never printed
    from octomod.spec import WorkflowSpec

    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    assert spec.get("s1.max_escalations") == 5, (
        "the spec key was renamed — that changes workflow_sha and refuses "
        "every paused run, for a word no card prints"
    )
    print("  vocabulary    no gate detail and no skill says 'escalate'; key intact")


def test_one_pass_one_set_of_verdicts() -> None:
    """A gate a stopped pass never reached keeps no verdict from an earlier pass."""
    from octomod.gates import gate

    def _g(gid: str, passed: bool):
        @gate(gid, "T0")
        def f():
            return GateResult(gid, "T0", passed, detail=gid)

        return f

    with temp_record("one_pass") as root:
        d = rnd(root, 0) / "gates"
        with redirect_stdout(io.StringIO()):
            run_gate_set(
                [
                    _g("assembly_a", True),
                    _g("assembly_b", True),
                    _g("assembly_c", True),
                ],
                d,
                RecordingLedger(),
                "s3",
            )
            assert d.child("assembly_c").exists()
            run_gate_set(
                [
                    _g("assembly_a", True),
                    _g("assembly_b", False),
                    _g("assembly_c", True),
                ],
                d,
                RecordingLedger(),
                "s3",
            )
        assert d.child(
            "assembly_b"
        ).exists(), "the failing verdict of this pass is kept"
        assert not d.child(
            "assembly_c"
        ).exists(), (
            "a gate this pass never reached still has the superseded pass's verdict"
        )
    print("  one pass     a gate not reached this pass leaves no stale verdict behind")


if __name__ == "__main__":
    test_one_pass_one_set_of_verdicts()
    test_the_tier_leaves_the_line_but_not_the_record()
    test_numbers_read_like_numbers()
    test_a_passing_ladder_is_one_line()
    test_a_failure_always_prints_in_full()
    test_verbose_restores_every_line()
    test_engine_vocabulary_does_not_reach_a_reader()
    print(
        "GATE CONSOLE UNIT OK — plain labels, readable numbers, a ladder in "
        "one line, and every tier still in the record"
    )
