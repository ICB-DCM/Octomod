"""How many rounds a run may take, and how that is said on a card or record.

A run whose round-buying gates a person answers has no cap; declining one ends
it. An unattended run (`--auto-approve`, or a policy answering a buying gate)
keeps `loop.max_rounds_unattended`, since there the cap is the stop.
`--max-rounds` and a policy's `max_rounds` only lower the budget. No cap is
`NO_CAP` (infinity), so `rounds_left > 0` comparisons read it correctly.
"""

from __future__ import annotations

import math
from pathlib import Path

NO_CAP = math.inf
# the judgment gates that BUY a round; a policy answering one is the unattended case
BUYING_GATES = ("revision", "revision_proposal_stop_vs_revise", "revision_proposal")


def run_cap(spec, cli_max_rounds, *, auto: bool, policy) -> int | None:
    """The round budget of a run: None = no cap (a person buys every round)."""
    cap = cli_max_rounds if cli_max_rounds is not None else spec.get("loop.max_rounds")
    cap = None if cap is None else int(cap)
    unattended = auto or (
        policy is not None
        and any(
            str((policy.answers.get(g) or {}).get("answer", "")).lower()
            in ("y", "yes", "true")
            for g in BUYING_GATES
        )
    )
    if unattended:
        bound = int(spec.require("loop.max_rounds_unattended"))
        cap = bound if cap is None else min(cap, bound)
    if policy is not None:
        cap = policy.clamp_rounds(cap)
    return cap


def rounds_left_after(round_idx: int, max_rounds: int | None) -> float:
    """Rounds still available after the one at `round_idx` (`NO_CAP` when
    `max_rounds` is None).

    The expansion guard and the verdict card both read this, so the card never
    promises a round the engine will not run.
    """
    if max_rounds is None:
        return NO_CAP
    return max_rounds - round_idx - 1


def remain(rounds_left) -> str:
    """The card's words: '2 round(s) remain', 'no cap on rounds', or 'no
    rounds remain'."""
    if rounds_left is None or rounds_left <= 0:
        return "no rounds remain"
    if rounds_left == NO_CAP:
        return "no cap on rounds (you end the run at a gate)"
    return f"{int(rounds_left)} round(s) remain"


def left(rounds_left) -> str:
    """The same, as a parenthetical: '2 round(s) left', 'no cap on rounds'."""
    if rounds_left is None or rounds_left <= 0:
        return "no rounds left"
    if rounds_left == NO_CAP:
        return "no cap on rounds"
    return f"{int(rounds_left)} round(s) left"


def as_record(rounds_left):
    """JSON-safe for a ledger row or an agent's context: an int, or 'no cap'."""
    if rounds_left == NO_CAP:
        return "no cap"
    return rounds_left


def round_index(rnd) -> int:
    """The round number of a `round_<k>` node (`rounds/round_<k>` in the
    record; a legacy run directory's folder reads the same way)."""
    name = rnd.name if hasattr(rnd, "name") else Path(rnd).name
    return int(str(name).split("_", 1)[1])


def round_nodes(root) -> list:
    """The run's round nodes in round order (round_10 after round_9)."""
    from octomod.result import node as tree

    return [tree.round_node(root, k) for k in tree.round_indices(root)]


def round_dirs(run) -> list:
    """The rounds of a run in round order: the record's round nodes for a
    record `Node` (`rounds/round_<k>`), the folders for a legacy run
    directory (`round_<k>/`)."""
    if hasattr(run, "store"):
        return round_nodes(run)
    return sorted(
        (
            p
            for p in Path(run).glob("round_*")
            if p.is_dir() and p.name.split("_", 1)[1].isdigit()
        ),
        key=round_index,
    )
