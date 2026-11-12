"""Observation-layer axes: the eager validator and the executor, without the engine.

  1. each validation rule drops its axis with a ledger note naming axis and reason;
  2. enumeration carries the overlays and leaves the antimony untouched;
  3. the executor applies an overlay to a copy, S11 moves included.

    uv run python tests/assembly_axes_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.assembly import assembly_edit  # noqa: E402
from octomod.workflow_modules.model import model_space  # noqa: E402
from tests._record import ledger_rows, rnd, temp_record  # noqa: E402

ANT = """model m
  compartment cell = 1;
  species Aa in cell = 0;
  species D in cell = 0;
  u = 1; bx11 = 0; k1 = 0.1; k2 = 0.2; Ctot = 5;
  J1: -> Aa; k1 * u * (1 - Aa);
  J2: -> D; k2 * Aa * (Ctot - D);
end
"""
ASM = {
    "observables": [
        {
            "observable_id": "obs_A",
            "maps_to_label": "KinA_p",
            "formula": "Aa",
            "transformation": "lin",
            "rationale": "-",
        },
        {
            "observable_id": "obs_D",
            "maps_to_label": "ProD",
            "formula": "D",
            "transformation": "lin",
            "rationale": "-",
        },
    ],
    "noise": [
        {
            "observable_id": "obs_A",
            "distribution": "normal",
            "formula": "sigma_obs_A",
            "estimate_sigma": True,
            "rationale": "-",
        },
        {
            "observable_id": "obs_D",
            "distribution": "normal",
            "formula": "sigma_obs_D",
            "estimate_sigma": True,
            "rationale": "-",
        },
    ],
    "scaling": [
        {
            "observable_id": "obs_A",
            "mode": "none",
            "scale_parameter": None,
            "offset_parameter": None,
            "shared_across_conditions": True,
            "rationale": "-",
        },
        {
            "observable_id": "obs_D",
            "mode": "factor",
            "scale_parameter": "sc_obs_D",
            "offset_parameter": None,
            "shared_across_conditions": True,
            "rationale": "-",
        },
    ],
    "conditions": [
        {
            "condition_id": "c1",
            "maps_to_label": "u=1,bx=0",
            "overrides": {"u": 1, "bx11": 0},
            "preequilibration": False,
            "rationale": "-",
        }
    ],
}


class FakeCtx:
    def __init__(self, root):
        self.root = root  # the record's root node: the run is one file
        self.round_idx = 0
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, self.round_idx)


def axis(aid, patch, **kw):
    return {
        "id": aid,
        "question": "?",
        "default": "off",
        "on_assembly_patch": patch,
        "adds_parameters": kw.get("adds", []),
        "rationale": "-",
        "discriminating_evidence": "-",
    }


def main() -> int:
    with temp_record("axes") as root:
        return _check(root)


def _check(root) -> int:
    ctx = FakeCtx(root)
    proposed = [
        axis("offset_D", {"add_offset": {"observable_label": "ProD"}}),
        axis(
            "prop_noise_A",
            {
                "change_noise_model": {
                    "observable_label": "KinA_p",
                    "new_formula": "sigma_obs_A * (Aa)",
                }
            },
        ),
        axis(
            "laplace_D",
            {
                "change_noise_model": {
                    "observable_label": "ProD",
                    "new_distribution": "laplace",
                }
            },
        ),  # 2nd axis on ProD
        axis(
            "log_A",
            {"change_transformation": {"observable_label": "KinA_p", "new": "log10"}},
        ),
        axis(
            "bad_symbol",
            {
                "change_observable_formula": {
                    "observable_label": "KinA_p",
                    "new_formula": "Aa * f_ghost",
                }
            },
        ),
        axis("unknown_obs", {"add_offset": {"observable_label": "Nope"}}),
        axis(
            "reinterpret",
            {
                "change_condition": {
                    "condition_label": "u=1,bx=0",
                    "overrides": {"u": 2.0},
                }
            },
        ),
        axis(
            "hyp_route",
            {
                "change_condition": {
                    "condition_label": "u=1,bx=0",
                    "overrides": {"k2": 0.0},
                }
            },
        ),
        axis("both", {"add_offset": {"observable_label": "ProD"}}),
        axis("struct_ok", None),
    ]
    proposed[-1]["on_antimony_patch"] = {
        "replace_reaction": "J2",
        "with": "J2: -> D; (k2 * Aa + k_alt) * (Ctot - D);",
    }
    proposed[-1]["adds_parameters"] = [
        {"id": "k_alt", "nominal_value": 0.01, "lb": 1e-4, "ub": 1, "estimate": True}
    ]
    proposed[-2]["on_antimony_patch"] = {"append": "k9 = 1;"}

    axes, dropped = model_space.validate_axes(
        ctx,
        proposed,
        ANT,
        {"k1", "k2", "u", "bx11", "Ctot"},
        module="unit",
        base_assembly=ASM,
    )
    kept = {a["id"]: a for a in axes}
    drop = {d["id"]: d["reason"] for d in dropped}
    print("kept:   ", sorted(kept))
    print("dropped:", json.dumps(drop, indent=1))

    assert set(kept) == {"offset_D", "prop_noise_A", "hyp_route", "struct_ok"}, sorted(
        kept
    )
    assert (
        kept["offset_D"]["kind"] == "observation"
        and kept["struct_ok"]["kind"] == "structure"
    )
    assert (
        "residual scales" in drop["log_A"]
    ), "a transformation axis must be refused, saying what the engine lacks"
    assert "f_ghost" in drop["bad_symbol"]
    assert "Nope" in drop["unknown_obs"]
    assert "reinterprets" in drop["reinterpret"]
    assert "one observation axis per observable" in drop["laplace_D"]
    assert "never both" in drop["both"]
    notes = ledger_rows(root)
    named = {n["note"].split("'")[1] for n in notes if "dropped" in n.get("note", "")}
    assert named == set(drop), f"every drop must be ledgered by axis id: {named}"

    # enumeration: 4 axes -> 16 models, overlays carried, antimony untouched by observation axes
    models = model_space.enumerate_models(
        ANT,
        [{"id": "k1", "nominal_value": 0.1, "estimate": True, "lb": 0.01, "ub": 1}],
        axes,
        max_models=16,
        t_end=10.0,  # neutral declarations are verified by simulation
    )
    assert len(models) == 16, len(models)
    by_id = {m["model_id"]: m for m in models}
    assert (
        by_id["offset_D"]["antimony"] == ANT
        and len(by_id["offset_D"]["assembly_overlay"]) == 1
    )
    assert (
        "k_alt" in by_id["struct_ok"]["antimony"]
        and not by_id["struct_ok"]["assembly_overlay"]
    )
    both = by_id["offset_D+prop_noise_A+hyp_route+struct_ok"]
    assert len(both["assembly_overlay"]) == 3

    # executor: overlay applied to a copy, references resolved by label
    out = assembly_edit.apply_overlay(ASM, both["assembly_overlay"])
    sc = {s["observable_id"]: s for s in out["scaling"]}
    assert (
        sc["obs_D"]["mode"] == "factor_offset"
        and sc["obs_D"]["offset_parameter"] == "off_obs_D"
    )
    nz = {n["observable_id"]: n for n in out["noise"]}
    assert nz["obs_A"]["formula"] == "sigma_obs_A * (Aa)"
    assert out["conditions"][0]["overrides"] == {"u": 1.0, "bx11": 0.0, "k2": 0.0}
    assert (
        ASM["scaling"][1]["mode"] == "factor"
    ), "the base assembly must not be mutated"
    # S11 moves go through the same executor
    moved = assembly_edit.apply_move(
        ASM, {"type": "remove_scaling", "args": {"observable_id": "obs_D"}}
    )
    assert {s["observable_id"]: s for s in moved["scaling"]}["obs_D"]["mode"] == "none"
    print(
        "ASSEMBLY AXES UNIT OK — validator drops each rule with a named note; "
        "enumeration carries overlays; executor shared with S11"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
