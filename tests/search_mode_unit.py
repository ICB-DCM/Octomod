"""Rounds and candidates: no round cap for a person, one axis at a time by default.

  1. a person-gated run has no round cap; an unattended one keeps the unattended cap;
  2. the CLI and a policy cap only lower the budget, and the card says "no cap";
  3. bought axes are searched one at a time (k+1 models) unless `lattice` asks for 2^k;
  4. the model counts, ceiling, enumeration and recorded mode follow the search mode.

    uv run python tests/search_mode_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.orchestration import rounds  # noqa: E402
from octomod.orchestration.interaction.policy import Policy  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.model import model_space as ms  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")


def test_the_round_cap() -> None:
    check(
        "a person-gated run has no cap (the person stops it at a gate)",
        rounds.run_cap(SPEC, None, auto=False, policy=None) is None,
    )
    bound = int(SPEC.require("loop.max_rounds_unattended"))
    check(
        "`--auto-approve` keeps the unattended cap",
        rounds.run_cap(SPEC, None, auto=True, policy=None) == bound,
    )
    bench = Policy.load("benchmark")
    check(
        "a policy that answers the expansion gate keeps it too",
        rounds.run_cap(SPEC, None, auto=False, policy=bench) == bound,
    )
    copilot = Policy.load("copilot")
    check(
        "copilot pauses at the expansion gate, so a person buys the rounds: no cap",
        rounds.run_cap(SPEC, None, auto=False, policy=copilot) is None,
    )
    check(
        "`--max-rounds 2` still caps",
        rounds.run_cap(SPEC, 2, auto=False, policy=None) == 2,
    )
    capped = Policy.load("copilot")
    capped.caps["max_rounds"] = 1
    check(
        "a policy's max_rounds cap lowers an uncapped run",
        rounds.run_cap(SPEC, None, auto=False, policy=capped) == 1,
    )
    check(
        "no cap is infinitely many rounds left",
        rounds.rounds_left_after(5, None) == rounds.NO_CAP,
    )
    check("…and 2 of 3 rounds after round 0", rounds.rounds_left_after(0, 3) == 2)
    check(
        "the card says 'no cap', never 'inf'",
        "no cap" in rounds.remain(rounds.NO_CAP)
        and "inf" not in rounds.remain(rounds.NO_CAP),
    )
    check(
        "a record holds 'no cap', JSON-safe",
        rounds.as_record(rounds.NO_CAP) == "no cap" and rounds.as_record(2) == 2,
    )
    check(
        "0 left is no rounds",
        rounds.remain(0) == "no rounds remain" and rounds.left(0) == "no rounds left",
    )


def test_the_counts_and_the_ceiling() -> None:
    check("k axes one at a time: k+1 models", ms.n_models(3, ms.CANDIDATES) == 4)
    check("k axes as a lattice: 2^k", ms.n_models(3, ms.LATTICE) == 8)
    check(
        "the ceiling admits max_models-1 axes one at a time",
        ms.max_axes(8, ms.CANDIDATES) == 7,
    )
    check("…and log2(max_models) as a lattice", ms.max_axes(8, ms.LATTICE) == 3)
    axes = [{"id": f"x{i}", "priority": i} for i in range(1, 6)]
    kept, dropped = ms.cap_axes(axes, 4, mode=ms.CANDIDATES)
    check(
        "cap one at a time: 3 axes under a ceiling of 4",
        [a["id"] for a in kept] == ["x1", "x2", "x3"],
        str([a["id"] for a in kept]),
    )
    kept, _ = ms.cap_axes(axes, 4, mode=ms.LATTICE)
    check(
        "cap as a lattice: 2 axes under a ceiling of 4",
        [a["id"] for a in kept] == ["x1", "x2"],
    )


BASE = """model cell
  R1: A -> B; k1*A;
  A = 1; B = 0; k1 = 0.5;
end
"""
BASE_PAR = [
    {"id": "k1", "lb": 1e-3, "ub": 10.0, "nominal_value": 0.5, "estimate": True}
]


def _axis(aid: str, reaction: str, pid: str, neutral=None) -> dict:
    par = {"id": pid, "lb": 1e-4, "ub": 1.0, "nominal_value": 0.1, "estimate": True}
    if neutral is not None:
        par["neutral_value"] = neutral
    return {
        "id": aid,
        "on_antimony_patch": {"append": reaction},
        "adds_parameters": [par],
    }


def test_the_enumeration() -> None:
    axes = [
        _axis("alt", "R2: A -> C; k2*A", "k2"),
        _axis("leak", "R3: B -> ; k3*B", "k3"),
        _axis("decay", "R4: A -> ; k4*A", "k4"),
    ]
    one = ms.enumerate_with_encoding(
        BASE, BASE_PAR, axes, 8, t_end=10.0, one_at_a_time=True
    )
    ids = sorted(m["model_id"] for m in one["models"])
    check(
        "one at a time: the base and each axis on its own",
        ids == ["alt", "base", "decay", "leak"],
        str(ids),
    )
    full = ms.enumerate_with_encoding(BASE, BASE_PAR, axes, 8, t_end=10.0)
    check(
        "the lattice is every combination",
        len(full["models"]) == 8,
        str(len(full["models"])),
    )
    neutral = [
        _axis("alt", "R2: A -> C; k2*A", "k2", neutral=0.0),
        _axis("leak", "R3: B -> ; k3*B", "k3", neutral=0.0),
        _axis("decay", "R4: A -> ; k4*A", "k4", neutral=0.0),
    ]
    one_n = ms.enumerate_with_encoding(
        BASE, BASE_PAR, neutral, 8, t_end=10.0, one_at_a_time=True
    )
    check(
        "one at a time works in the one-compile encoding too",
        sorted(m["model_id"] for m in one_n["models"])
        == ["alt", "base", "decay", "leak"]
        and one_n["encoding"]["kind"] == "supermodel",
        f"{sorted(m['model_id'] for m in one_n['models'])}, {one_n['encoding']['kind']}",
    )


def test_the_opt_in_and_its_record() -> None:
    for note, want in {
        "lattice": True,
        "tier: all; lattice": True,
        "axes: a, b\nlattice": True,
        "search: lattice": True,
        "the lattice would be too big": False,
        "tier: all": False,
        "": False,
    }.items():
        check(f"lattice asked in {note!r}: {want}", ms.lattice_requested(note) is want)
    with temp_record() as root:
        ctx = SimpleNamespace(round=rnd(root, 1), spec=SPEC)
        check("the default is one at a time", ms.search_mode(ctx) == ms.CANDIDATES)
        ms.record_search_mode(ctx.round, ms.LATTICE, "the human's `lattice`")
        check(
            "a recorded `lattice` is this round's mode",
            ms.search_mode(ctx) == ms.LATTICE,
        )
    rec = {"k": 2, "label": "top2", "reasoning": "r", "source": "agent"}
    axes = [
        {"id": "a", "priority": 1, "default": "off"},
        {"id": "b", "priority": 2, "default": "off"},
    ]
    lines = "\n".join(ms.tier_card_lines(axes, 8, rec, mode=ms.CANDIDATES))
    check(
        "the tier card counts in the round's mode and names the alternative",
        "tier: top1 -> 2 model(s)" in lines
        and "all (= top2)-> 3 model(s)" in lines
        and "`lattice` in the note buys every combination: 4" in lines,
        lines[-400:],
    )


def _round(
    run,
    idx: int,
    cands: list[tuple[str, float]],
    winner: str,
    space: list[str],
    expanded_from: str | None = None,
    carried: list | None = None,
    report: bool = True,
) -> None:
    """One round planted in the record `run`: its declared axes
    (`space/axes`), its evaluation, and the previous round's `expansion`."""
    d = rnd(run, idx)
    (d / "space/axes").put([{"id": a} for a in space])
    if report:
        (d / "evaluation").put(
            {
                "discrimination": {
                    "candidates": [{"id": c, "nllh": v, "n_est": 1} for c, v in cands],
                    "winner": winner,
                    "criterion": "AIC",
                }
            }
        )
    if expanded_from:
        (rnd(run, idx - 1) / "expansion").put(
            {
                "expanded": True,
                "next_round": idx,
                "from_winner": expanded_from,
                "expanded_from": expanded_from,
                "carried_undecided": carried or [],
            }
        )


def test_the_search_topology() -> None:
    """Every model fitted over three rounds is placed in the search topology."""
    from octomod.workflow_modules.model import tried_models

    with temp_record() as run:
        _round(
            run,
            0,
            [("M1", 1100.0), ("M2", 1050.0), ("M3", 1200.0), ("M4", 1300.0)],
            "M2",
            [],
        )
        ax1 = ["typeI", "pstat1_off", "shared_off"]
        lattice = [
            "base",
            "typeI",
            "pstat1_off",
            "shared_off",
            "typeI+pstat1_off",
            "typeI+shared_off",
            "pstat1_off+shared_off",
            "typeI+pstat1_off+shared_off",
        ]
        _round(
            run,
            1,
            [(m, 1010.0) for m in lattice],
            "typeI+pstat1_off+shared_off",
            ax1,
            expanded_from="M2",
        )
        declared = [{"id": a} for a in ax1 + ["typeII"]]
        # round 2 is being evaluated: no evaluation yet
        _round(
            run,
            2,
            [],
            "",
            ["typeII"],
            expanded_from="typeI+pstat1_off+shared_off",
            report=False,
        )
        fitted = tried_models.models_fitted_this_run(
            run,
            current={
                "round": 2,
                "candidates": [
                    {"id": "base", "nllh": 1002.15, "n_est": 83},
                    {"id": "typeII", "nllh": 925.77, "n_est": 84},
                ],
                "winner": "typeII",
            },
        )
        check(
            "the round being evaluated is in the fitted list",
            any(r["round"] == 2 for r in fitted),
        )
        topo = ms.search_topology(declared, fitted, mode=ms.CANDIDATES)
        check(
            "every model sits at its actual corner: 8 + 1 new = 9 of 16 on M2",
            topo["visited"] == 9
            and topo["union_lattice_models"] == 16
            and topo["lattice_root"] == "M2 (round 0)",
            f"visited {topo['visited']}, root {topo['lattice_root']}",
        )
        check(
            "the models outside the lattice carry their round and outcome",
            topo["models_outside_the_lattice"] == ["M1", "M2", "M3", "M4"]
            and any(
                st.startswith("M2 (round 0, fitted, -log L 1050.00, selected")
                for st in topo["outside_status"]
            ),
            str(topo["outside_status"]),
        )
        check(
            "the topology says how rounds searched",
            topo["topology"].startswith("one axis at a time"),
        )


def main() -> int:
    print("rounds and candidates — no cap for a person, one axis at a time by default")
    test_the_search_topology()
    test_the_round_cap()
    test_the_counts_and_the_ceiling()
    test_the_enumeration()
    test_the_opt_in_and_its_record()
    return finish("\nSEARCH MODE", "SEARCH MODE OK")


if __name__ == "__main__":
    sys.exit(main())
