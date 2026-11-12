"""A prompt-cache miss is diagnosable; a verdict resume never re-asks the interpreter.

  1. an identical ask is served from the record; a changed one misses, keeping both prompts;
  2. the miss writes a diagnosis naming the first differing line, and is ledgered;
  3. the accepted interpretation is pinned before the verdict; a later pass reuses it;
  4. an explicit evaluation re-entry forgets the pin.

    uv run python tests/prompt_cache_unit.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check, finish  # noqa: E402

from octomod.orchestration import round_status  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.evaluation import engine as s7  # noqa: E402
from tests._record import temp_record  # noqa: E402

ROLE = "interpretation"


def _ctx(root) -> RunContext:
    ctx = RunContext(
        root=root,
        testcase_dir=REPO / "testcase" / "toy_phos",  # its stubs answer the interpreter
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(root.store),
        backend="stub",
        auto=True,
    )
    (root / "intent").put(
        {"question": "unit", "system": "toy", "inference_target": "prediction"}
    )
    return ctx


def _calls(ctx) -> int:
    return sum(
        1
        for e in ctx.ledger.entries()
        if e.get("event") == "agent_call" and e.get("role") == ROLE
    )


def test_call_cached_hits_and_diagnoses_misses() -> None:
    with temp_record() as root:
        ctx = _ctx(root)
        base = {
            "intent": ctx.intent,
            "instruction": "read the fits",
            "report_core": {"n": 9},
        }
        r1 = ctx.call_cached(ROLE, dict(base))
        r2 = ctx.call_cached(ROLE, dict(base))
        check(
            "an identical ask is served from the record: one agent call for two asks",
            _calls(ctx) == 1 and r1 == r2,
        )
        changed = {**base, "report_core": {"n": 10}}  # the one-byte class of change
        r3 = ctx.call_cached(ROLE, changed)
        check(
            "a changed ask is a miss and is paid", _calls(ctx) == 2 and r3 is not None
        )
        # the record keeps one group per miss, `<call>/prompt_misses/<k>`, holding
        # both prompts under their shas and the diagnosis text (`report`)
        misses_node = ctx.agent_calls.child(ROLE) / "prompt_misses"
        miss = [
            m.get() for m in (misses_node.child_nodes() if misses_node.exists() else [])
        ]
        versions = sorted(
            {m.get(f"{w}_prompt_sha") for m in miss for w in ("saved", "new")}
            if all(m.get("saved_prompt") and m.get("new_prompt") for m in miss)
            else set()
        )
        check(
            "BOTH prompt versions are kept under their sha",
            len(versions) == 2,
            str(versions),
        )
        text = str(miss[0].get("report") or "") if miss else ""
        check(
            "the diagnosis names the byte, the line and shows both lines",
            len(miss) == 1
            and "first difference at byte" in text
            and '"n": 9' in text
            and '"n": 10' in text,
            text[:300],
        )
        row = next(
            (e for e in ctx.ledger.entries() if e.get("event") == "prompt_cache_miss"),
            None,
        )
        check(
            "the ledger carries a prompt_cache_miss row with both sizes and the first differing line",
            row is not None
            and row["bytes_new"] - row["bytes_saved"] == 1
            and '"n": 9' in row["saved_line"],
            str(row)[:200] if row else "no row",
        )
        # the new prompt is now the saved one: asking the changed ask again is a hit
        ctx.call_cached(ROLE, changed)
        check(
            "after a miss the NEW prompt is what the next identical ask hits",
            _calls(ctx) == 2,
        )


def test_the_interpretation_is_pinned_before_the_verdict() -> None:
    with temp_record() as root:
        ctx = _ctx(root)
        core = {
            "computed_cannot_distinguish": [],
            "computed_nonetheless_determined": [],
            "discrimination": {},
            "parameters": {},
        }
        interp = s7._interpret_with_consistency(ctx, core)
        pin = ctx.agent_calls / s7.INTERPRETATION_PIN
        check(
            "the first pass calls the agent and pins the reply",
            _calls(ctx) == 1 and pin.exists() and interp.get("recommendation"),
        )
        # a later pass whose payload differs (a resume): NO rebuild, NO call
        core2 = {**core, "computed_nonetheless_determined": ["k_phos is determined"]}
        again = s7._interpret_with_consistency(ctx, core2)
        check(
            "a later pass with a changed payload returns the pin: no agent call, no cache miss",
            _calls(ctx) == 1
            and again == interp
            and not any(
                e.get("event") == "prompt_cache_miss" for e in ctx.ledger.entries()
            )
            and any(e.get("interpretation_pinned") for e in ctx.ledger.entries()),
        )
        # an explicit evaluation re-entry forgets the pin, so the next pass rebuilds
        _, forgotten, _ = round_status.invalidate_from(ctx, "evaluation")
        check(
            "`--from-module evaluation` forgets the pin",
            f"agent_calls/{s7.INTERPRETATION_PIN}" in forgotten and not pin.exists(),
            str(forgotten),
        )
        s7._interpret_with_consistency(ctx, core2)
        check(
            "…and the re-entered evaluation asks the agent again and re-pins",
            _calls(ctx) == 2 and pin.exists(),
        )


def main() -> int:
    test_call_cached_hits_and_diagnoses_misses()
    test_the_interpretation_is_pinned_before_the_verdict()
    return finish(
        "\nPROMPT CACHE",
        "\nprompt cache: misses are diagnosable, and the verdict resume pays nothing",
    )


if __name__ == "__main__":
    sys.exit(main())
