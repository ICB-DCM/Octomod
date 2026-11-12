"""The supermodel encoding, end to end on a real fit.

`testcase/toy_super` declares two axes that are exactly neutralizable and one that is not.

  1. the encoding: two axes absorbed, the third separated with its reason, the saving stated;
  2. the neutral values are verified by simulation, not taken on trust;
  3. the true structure wins, by a margin that is not a coin flip;
  4. the false axis is priced honestly rather than dropped;
  5. the held-out dose is predicted.

    uv run python tests/supermodel_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


sys.path.insert(0, str(REPO / "tests"))

from _record import ledger_rows, rnd, run_root, work  # noqa: E402
from file_gate_loop import drive  # noqa: E402

from octomod import config  # noqa: E402

# `test_runs/` under the battery (tests/run_all.py sets OCTOMOD_RUNS_DIR),
# `runs/` otherwise; a suite never spells `runs/` itself.
RUNS = config.RUNS_DIR

RUN_ID = "supermodel_smoke"
CASE = "toy_super"

# Bounds, not equalities: the fit is seeded and deterministic, but a tolerance
# change upstream may move a number without the case having changed.
TRUE_AXES = ("product_feedback",)
MIN_MARGIN_AIC = 50.0  # measured 104.9 to the nearest structure without it
MAX_WEIGHT_DROP = 0.60  # measured 0.7365; below 0.6 the case has changed


def main() -> int:
    root = run_root(RUN_ID, RUNS)  # the run is one file
    if root.exists():
        root.store.remove()
    t0 = time.time()
    rc, gates = drive(
        CASE,
        RUN_ID,
        answers={
            # the lattice on purpose: this suite measures the one-compile
            # encoding over every combination (one at a time is the default)
            "model_scope": [("y", "tier: all; lattice")],
            # the budget gate's documented answer form: 30 starts still leave ~8
            # within 0.5 of the best for the waterfall gate, and answering the gate
            # leaves the spec default, and so every other case, unchanged
            "cost_boundary_estimation": [("y", "n=30")],
        },
    )
    print(f"exit {rc}; gates: {gates} ({time.time() - t0:.0f}s)")
    assert rc == 0, f"the run ended {rc}"

    core = (rnd(root, 0) / "evaluation").get()
    enc = (rnd(root, 0) / "model/encoding").get()

    # ---- 1. the encoding ------------------------------------------------
    assert enc["kind"] == "supermodel", enc["kind"]
    assert sorted(enc["absorbed_axes"]) == [
        "alt_route",
        "product_feedback",
    ], f"expected both neutralizable axes absorbed, got {enc['absorbed_axes']}"
    assert enc["separated_axes"] == ["cooperative_production"], (
        f"the parameter-free axis must stay its own structure, got "
        f"{enc['separated_axes']}"
    )
    why = enc["why_separate"]["cooperative_production"]
    assert (
        "adds no parameter" in why
    ), f"the separation reason is not recorded in words: {why!r}"
    n_structures = len(enc["structures"])
    n_models = len(core["discrimination"]["candidates"])
    assert (n_models, n_structures) == (8, 2), (
        f"expected 8 candidates over 2 structures, got {n_models} over "
        f"{n_structures} — the grouping has changed"
    )
    print(
        f"  encoding      {n_models} candidates over {n_structures} structures; "
        f"absorbed {enc['absorbed_axes']}, separated {enc['separated_axes']}"
    )

    # ---- 2. verified, not trusted ---------------------------------------
    ver = enc["verification"]
    assert not ver["joint_failures"], ver["joint_failures"]
    for axis, rec in ver["per_axis"].items():
        assert rec["neutralizes"], f"{axis}: {rec['why']}"
    assert ver["checked_to"]["rtol"] <= 1e-6, ver["checked_to"]
    ledger = ledger_rows(root)
    neutrality = [
        e for e in ledger if e.get("gate_id") == "model_supermodel_neutrality"
    ]
    assert neutrality and neutrality[-1]["passed"], neutrality[-1:]
    assert "compile(s) saved" in neutrality[-1]["detail"], neutrality[-1]["detail"]
    print(
        f"  verified      {len(ver['per_axis'])} declared neutral value(s) "
        f"reproduce the base model to rtol {ver['checked_to']['rtol']}"
    )

    # ---- 3. the true structure wins -------------------------------------
    disc = core["discrimination"]
    winner_axes = tuple(a for a in disc["winner"].split("+") if a)
    assert winner_axes == TRUE_AXES, (
        f"the winner is {disc['winner']!r} and the truth is "
        f"{'+'.join(TRUE_AXES)!r} — the fixture is not measuring what it "
        f"claims"
    )
    by_id = {r["id"]: r for r in disc["candidates"]}
    without = [
        r for cid, r in by_id.items() if "product_feedback" not in cid.split("+")
    ]
    margin = min(r["delta_aic"] for r in without)
    assert margin >= MIN_MARGIN_AIC, (
        f"the nearest structure without the feedback axis is only {margin:.1f} "
        f"AIC units behind (104.9 on the reference run) — the separation is not "
        f"qualitative"
    )
    weight = by_id[disc["winner"]]["akaike_weight"]
    assert weight >= MAX_WEIGHT_DROP, f"winner weight {weight}"
    print(
        f"  discrimination winner {disc['winner']} (weight {weight:.4f}); the "
        f"nearest structure without the axis is {margin:.1f} AIC units behind"
    )

    # ---- 4. the false axis, priced honestly -----------------------------
    # `alt_route` is exactly neutralizable AND false. It must appear in the
    # table with its own AIC rather than be dropped, and its parameter must
    # come back at the bound rather than at something that looks fitted.
    runner = "product_feedback+alt_route"
    assert runner in by_id, sorted(by_id)
    assert 1.5 <= by_id[runner]["delta_aic"] <= 3.0, (
        f"the useless-parameter neighbour is at dAIC "
        f"{by_id[runner]['delta_aic']:.3f}; a free parameter that buys nothing "
        f"should sit near 2 x dk = 2"
    )
    summary = (work(root, 0, runner) / "estimation").get()
    assert "k_alt" in (summary.get("at_bounds") or []), (
        f"the false axis's parameter is not at a bound: at_bounds="
        f"{summary.get('at_bounds')}, fitted "
        f"{summary['best_x_unscaled'].get('k_alt')}"
    )
    print(
        f"  false axis    {runner} at dAIC "
        f"{by_id[runner]['delta_aic']:.3f}, k_alt pinned at its bound "
        f"({summary['best_x_unscaled']['k_alt']:.1e})"
    )

    # ---- 5. the held-out dose -------------------------------------------
    hold = core.get("holdout") or {}
    assert hold.get("available"), hold
    groups = hold.get("groups") or hold.get("model_averaged") or []
    assert groups, hold
    worst = max(g["nrmse"] for g in groups)
    assert worst < 0.3, f"held-out nRMSE {worst:.3f}: {groups}"
    print(
        f"  held out      u=2 predicted, worst nRMSE {worst:.3f} over "
        f"{len(groups)} series"
    )

    print(
        "\nSUPERMODEL SMOKE OK — two axes absorbed into one structure and "
        "verified, one separated with its reason, the true structure wins, "
        "and the false axis is priced rather than hidden"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
