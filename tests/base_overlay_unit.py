"""A decided observation-layer patch (arm-specific sigma) is inherited by the next round's base.

One mechanism decides what a round starts from: `round_seed` builds the winner's decided
patches into the next round's shared assembly and leaves the patch of every axis carried
live again to the lattice (`model_space.base_overlay_after_carry`).

    uv run python tests/base_overlay_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from round_seed_unit import ANT, PETAB, SHARED  # noqa: E402

from octomod.orchestration import round_seed  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit, petab_io  # noqa: E402
from octomod.workflow_modules.model import model_space  # noqa: E402
from tests._record import rnd, temp_record, work  # noqa: E402

CX = {"change_noise_model": {"observable_id": "obs_CXCL9", "new_per": "condition"}}
SO = {"change_noise_model": {"observable_id": "obs_SOCS1", "new_per": "condition"}}
# on the fixture's one observable: a decided offset, and a noise axis carried live
OFFSET = {"add_offset": {"observable_id": "obs_A"}}
LAPLACE = {
    "change_noise_model": {"observable_id": "obs_A", "new_distribution": "laplace"}
}


def _ctx(root, r: int) -> RunContext:
    """The record twin of round_seed_unit's context: round `r` of `root`."""
    return RunContext(
        root=root,
        testcase_dir=REPO / "testcase" / "toy_phos_petab",
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(root),
        backend="stub",
        auto=True,
        round_idx=r,
    )


def _candidate(root, cid: str, *, overlay: list, audited: bool) -> None:
    """A fitted candidate of round 0 as S1-S6 leave it (record twin of
    round_seed_unit's `_candidate`): model, merged assembly, PEtab, fit, audit."""
    w = work(root, 0, cid)
    (w / "model/antimony").put_text(ANT)
    (w / "model/sbml").put_text((PETAB / "model.xml").read_text())
    (w / "model/parameters").put([{"id": "k", "estimate": True}])
    (w / "model/glossary").put({"A": "a species"})
    if overlay:
        (w / "model/assembly_overlay").put(overlay)
    inp = petab_io.from_dir(PETAB)
    if overlay:
        import pandas as pd

        extra = pd.DataFrame(
            [
                {
                    "parameterId": "off_obs_A",
                    "parameterScale": "lin",
                    "lowerBound": -5,
                    "upperBound": 5,
                    "nominalValue": 0,
                    "estimate": 1,
                }
            ]
        )
        inp.parameters = pd.concat([inp.parameters, extra], ignore_index=True)
    petab_io.to_record(inp, w / "petab")
    merged = assembly_edit.apply_overlay(SHARED, overlay, assembly_for_refs=SHARED)
    (w / "assembly").put({**merged, "_shared_version": 2})
    (w / "multistart").put_blob(b"x")
    if audited:
        (w / "gates/assembly_verification").put({})


def finished_report(root) -> None:
    """What S7 leaves in a finished round: the report the next round is seeded from."""
    (rnd(root, 0) / "evaluation").put(
        {"goal": "prediction", "interpretation": {"recommendation": "revise"}}
    )


def _round0(root) -> None:
    import pandas as pd

    r0 = rnd(root, 0)
    (r0 / "data/measurements").put_table(pd.DataFrame({"x": []}))
    (r0 / "shared_assembly").put(SHARED)
    _candidate(root, "w", overlay=[OFFSET, LAPLACE], audited=True)
    finished_report(root)


def main() -> int:
    winner_overlay = [CX, SO]
    carried = [
        {"id": "arm_sigma_SOCS1", "on_assembly_patch": SO},
        {"id": "loop", "on_antimony_patch": {"append": "x"}},
    ]
    assert model_space.base_overlay_after_carry(winner_overlay, carried) == [CX]
    assert model_space.base_overlay_after_carry(winner_overlay, []) == [CX, SO]
    assert model_space.base_overlay_after_carry([], carried) == []

    # nothing carried: the base IS the winner, both patches built in, its fit kept
    with temp_record() as root:
        _round0(root)
        rec = round_seed.seed_round(_ctx(root, 0), rnd(root, 1), candidate="w", why="w")
        shared = (rnd(root, 1) / "shared_assembly").get()
        noise = shared["noise"][0]
        scale = shared["scaling"][0]
        assert noise.get("distribution") == "laplace" and scale.get("mode") in (
            "offset",
            "factor_offset",
        ), shared
        assert rec["fit"] and not rec.get("left_out_live_patches"), rec

    # the noise axis carried live: the decided offset stays in the base, the
    # carried patch is left to the lattice, and the base is not the fit
    with temp_record() as root:
        _round0(root)
        rec = round_seed.seed_round(
            _ctx(root, 0),
            rnd(root, 1),
            candidate="w",
            why="w",
            carried=[{"id": "noise_A", "on_assembly_patch": LAPLACE}],
        )
        shared = (rnd(root, 1) / "shared_assembly").get()
        noise = shared["noise"][0]
        scale = shared["scaling"][0]
        assert (
            noise.get("distribution") == "normal"
        ), "the carried axis's patch was built into the base"
        assert scale.get("mode") in (
            "offset",
            "factor_offset",
        ), "the decided patch was lost"
        assert (
            rec["left_out_live_patches"] == [LAPLACE]
            and rec["fit"] is None
            and rec["problem"] is None
        ), rec

    # wiring: the expansion hands the carried axes to the seed, and S1 applies no second overlay
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    i = src.index("seed_record = _seed.seed_round(")
    assert (
        "carried=carried" in src[i : i + 900]
    ), "the expansion must hand the carried axes to the seed"
    s1 = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert "base_ov_path" not in s1, "a second base-overlay mechanism is back in S1"
    print(
        "BASE OVERLAY UNIT OK — a decided noise split stays in the next round's base; a carried axis's patch is left to the lattice"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
