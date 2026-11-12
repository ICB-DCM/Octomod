"""Tiers, priorities and the axis ceiling of the model space, without the engine.

    uv run python tests/tier_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.model import model_space as ms  # noqa: E402

AXES = [
    {"id": "b", "priority": 2, "default": "off", "kind": "structure", "question": "q"},
    {"id": "a", "priority": 1, "default": "off", "kind": "structure", "question": "q"},
    {
        "id": "c",
        "priority": 3,
        "default": "off",
        "kind": "observation",
        "question": "q",
    },
    {"id": "d", "priority": 4, "default": "off", "kind": "structure", "question": "q"},
]


def main() -> int:
    assert [a["id"] for a in ms.by_priority(AXES)] == ["a", "b", "c", "d"]
    # note parsing: tiers, and axes: still wins
    assert ms.parse_axis_selection("tier: base", AXES) == set()
    assert ms.parse_axis_selection("y tier: top2 — start small", AXES) == {"a", "b"}
    assert ms.parse_axis_selection("tier: all", AXES) == {"a", "b", "c", "d"}
    assert ms.parse_axis_selection("tier: top9", AXES) == {"a", "b", "c", "d"}
    assert ms.parse_axis_selection("axes: c, d; tier: top1", AXES) == {
        "c",
        "d",
    }, "explicit axes win"
    assert (
        ms.parse_axis_selection("looks fine", AXES) is None
    ), "no instruction = unresolved, never silent"
    # the ceiling: 8 models -> 3 axes, by priority; undecided first when given
    assert ms.max_axes(8) == 3 and ms.max_axes(4) == 2 and ms.max_axes(1) == 0
    kept, dropped = ms.cap_axes(AXES, 8)
    assert [a["id"] for a in kept] == ["a", "b", "c"] and [
        a["id"] for a in dropped
    ] == ["d"]
    kept, dropped = ms.cap_axes(AXES, 4, undecided_ids={"d"})
    assert [a["id"] for a in kept] == [
        "d",
        "a",
    ], "undecided axes come first, then priority"
    # recommended tier: clamped, never 'all' as a label, default base
    rec = ms.parse_recommended_tier(
        {"recommended_tier": {"tier": "top2", "reasoning": "r"}}, 4
    )
    assert (
        rec["k"] == 2
        and rec["label"] == "top2"
        and rec["given"]
        and rec["source"] == "agent"
    )
    rec = ms.parse_recommended_tier({"recommended_tier": {"tier": "all"}}, 4)
    assert rec["k"] == 4 and rec["label"] == "top4"
    rec = ms.parse_recommended_tier({}, 4)
    assert rec["k"] == 0 and rec["label"] == "base" and not rec["given"]
    # a DEFAULT is never attributed to the agent
    assert rec["source"] == "engine", rec
    card = "\n".join(ms.tier_card_lines(AXES, 8, rec))
    assert "no recommendation from the agent" in card, card
    assert (
        "agent recommends" not in card
    ), "a default must not be dressed as the agent's"

    # an expansion round's axes were bought at the previous gate: the default is
    # ALL of them, and the card says the purchase already happened
    rec = ms.parse_recommended_tier(None, 2, already_bought=True)
    assert rec["k"] == 2 and rec["label"] == "top2" and rec["source"] == "engine"
    assert rec["already_bought"] and "bought at the expansion gate" in rec["reasoning"]
    card = "\n".join(ms.tier_card_lines(AXES[:2], 8, rec))
    assert "APPROVED at the expansion gate" in card, card
    assert (
        "no instruction = no search" not in card
    ), "silence on a bought round must not be advertised as spending nothing"
    # the card: every tier with its model count, the recommendation, the answer key
    lines = ms.tier_card_lines(
        AXES,
        8,
        ms.parse_recommended_tier(
            {
                "recommended_tier": {
                    "tier": "top1",
                    "reasoning": "one axis decides the question",
                }
            },
            4,
        ),
    )
    text = "\n".join(lines)
    assert "tier: base   -> 1 model" in text
    assert "tier: top1 -> 2 model(s) — axes: a" in text
    assert "tier: all (= top4)-> 16 model(s)" in text and "over the ceiling" in text
    assert "agent recommends: top1 (2 model(s))" in text

    # validate_axes carries priority and falls back to declaration order
    class Ctx:
        round_idx = 0

        class ledger:
            @staticmethod
            def append(*a, **k):
                pass

    axes, _ = ms.validate_axes(
        Ctx(),
        [
            {
                "id": "x",
                "on_antimony_patch": {"append": "k9 = 1;"},
                "adds_parameters": [{"id": "k9"}],
            },
            {
                "id": "y",
                "priority": 1,
                "priority_reason": "why",
                "on_antimony_patch": {"append": "k8 = 1;"},
                "adds_parameters": [{"id": "k8"}],
            },
        ],
        "model m\n end",
        set(),
        module="unit",
    )
    assert [(a["id"], a["priority"]) for a in axes] == [("x", 1), ("y", 1)]
    assert axes[1]["priority_reason"] == "why"
    print(
        "TIER UNIT OK — tiers parse, ceiling orders by undecided then priority, card shows counts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
