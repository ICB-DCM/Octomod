"""Which observation parameters may be solved analytically, and which are refused.

pyPESTO silently accepts two wrong configurations, so the engine refuses them itself.

  1. a laplace observable disables it (the package hardcodes the Gaussian likelihood);
  2. a scaling is never solved inside while its offset stays outside;
  3. the measured-exact cells are marked, and an inner parameter still counts in k.

    uv run python tests/hierarchical_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import pandas as pd  # noqa: E402
from _harness import check, finish  # noqa: E402

from octomod import config  # noqa: E402
from octomod.workflow_modules.assembly import hierarchical  # noqa: E402

# the user's runs folder, deliberately not redirected by the battery: this
# reads a previous run of theirs, not a run this suite makes
USER_RUNS = config.USER_RUNS_DIR


class Spec:
    def __init__(self, on: bool):
        self.on = on

    def get(self, key, default=None):
        return self.on if key == "estimation.hierarchical" else default


def assembly(mode: str, distribution: str = "normal", estimate_sigma: bool = True):
    return {
        "observables": [{"observable_id": "obs_x", "formula": "X"}],
        "noise": [
            {
                "observable_id": "obs_x",
                "distribution": distribution,
                "estimate_sigma": estimate_sigma,
                "formula": "sigma_obs_x",
            }
        ],
        "scaling": [
            {
                "observable_id": "obs_x",
                "mode": mode,
                "scale_parameter": "sc_obs_x" if "factor" in mode else None,
                "offset_parameter": "off_obs_x" if "offset" in mode else None,
            }
        ],
    }


def test_hierarchical_refuses_every_noise_shape_it_cannot_solve():
    from octomod.workflow_modules.assembly import hierarchical as H

    class _Spec:
        def __init__(self, on=True):
            self.on = on

        def get(self, k, d=None):
            return self.on if k == "estimation.hierarchical" else d

    def asm(formula, dist="normal"):
        return {
            "noise": [
                {
                    "observable_id": "o",
                    "distribution": dist,
                    "formula": formula,
                    "estimate_sigma": True,
                }
            ],
            "scaling": [
                {"observable_id": "o", "mode": "factor", "scale_parameter": "sc_o"}
            ],
        }

    marks, reasons = H.marks(asm("sigma_o"), _Spec())
    assert marks.get("sc_o"), "the SAFE shape must still be marked"

    for formula, why in (
        ("sigma_o * B", "proportional"),
        ("sigma_abs + sigma_rel * B", "two-component"),
        ("0.5", "a fixed number"),
    ):
        marks, reasons = H.marks(asm(formula), _Spec())
        assert marks == {}, f"{why} was marked hierarchical: {marks}"
        assert reasons and "DISABLED" in reasons[0], reasons
        assert (
            "additive" in reasons[0].lower()
        ), f"the refusal for {why} does not state WHY: {reasons[0]}"
        assert "pyPESTO" in reasons[0], "the refusal does not say whose limit it is"
    print("  hierarchical  only a bare sigma is marked; the rest refused with a reason")


def test_the_refusal_reaches_the_thing_that_consumes_it():
    """Empty marks -> no parameterType column -> `enabled_for` False -> a plain fit."""
    import pandas as pd

    from octomod.workflow_modules.assembly.hierarchical import enabled_for

    s3 = (REPO / "octomod" / "workflow_modules" / "assembly" / "engine.py").read_text()
    i = s3.index("hier_marks, hier_reasons = _hier.marks(")
    assert (
        "if hier_marks:" in s3[i : i + 200]
    ), "the parameterType column is written even when marks are empty"
    assert (
        "hier_reasons" in s3[i : i + 2000] and "hierarchical estimation: " in s3
    ), "the refusal reason is never ledgered"
    # and a table with no parameterType does not ask for hierarchical
    plain = pd.DataFrame([{"parameterId": "k", "estimate": 1}])
    assert enabled_for(plain) is False
    print("  consumed      empty marks -> no parameterType -> enabled_for False")


def main() -> int:
    # 1 ---- the knob is off by default, and off means nothing marked --------
    marks, reasons = hierarchical.marks(assembly("factor_offset"), Spec(False))
    check(
        "the knob off marks nothing at all", marks == {} and reasons == [], f"{marks}"
    )
    from octomod.spec import WorkflowSpec

    real = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    check(
        "and the shipped spec has it OFF",
        real.get("estimation.hierarchical") is False,
        f"{real.get('estimation.hierarchical')}",
    )

    # 2 ---- the cells that are measured-exact ------------------------------
    marks, _ = hierarchical.marks(assembly("factor_offset"), Spec(True))
    check(
        "a coupled scaling+offset is marked as BOTH inner",
        marks == {"sc_obs_x": "scaling", "off_obs_x": "offset"},
        f"{marks}",
    )
    marks, _ = hierarchical.marks(assembly("factor"), Spec(True))
    check(
        "a lone scaling with no offset present is marked (measured exact)",
        marks == {"sc_obs_x": "scaling"},
        f"{marks}",
    )

    # 3 ---- the refusal that would be SILENT in the library ----------------
    marks, reasons = hierarchical.marks(
        assembly("factor_offset", distribution="laplace"), Spec(True)
    )
    check(
        "one laplace observable disables the whole thing",
        marks == {},
        f"{marks}",
    )
    check(
        "and the reason names laplace AND the Gaussian substitution",
        any("laplace" in r and "Gaussian" in r for r in reasons),
        (reasons[0][:150] if reasons else "(no reason given)"),
    )

    # 4 ---- the unmeasured cell is left alone, and says so -----------------
    marks, reasons = hierarchical.marks(assembly("offset"), Spec(True))
    check(
        "an offset with no scaling is NOT marked (nobody measured that cell)",
        "off_obs_x" not in marks,
        f"{marks}",
    )
    check(
        "and the reason cites the neighbouring silently-wrong cell",
        any("silently" in r.lower() for r in reasons),
        (reasons[0][:150] if reasons else "(no reason given)"),
    )

    # 5 ---- sigma is never inner, and the reason is recorded ---------------
    marks, reasons = hierarchical.marks(assembly("factor_offset"), Spec(True))
    check(
        "sigma is never marked inner",
        "sigma_obs_x" not in marks,
        f"{sorted(marks)}",
    )
    check(
        "and the reason names pyPESTO's NotImplementedError for log sigma",
        any("NotImplementedError" in r for r in reasons),
        (next((r[:130] for r in reasons if "NotImplemented" in r), "") or f"{reasons}"),
    )

    # 6 ---- the question is read off the TABLE, not passed alongside it ----
    plain = pd.DataFrame({"parameterId": ["k", "sc_obs_x"], "estimate": [1, 1]})
    check(
        "a table with no parameterType asks for nothing",
        not hierarchical.enabled_for(plain),
    )
    marked = plain.assign(parameterType=["", "scaling"])
    check("a table with a mark asks for it", hierarchical.enabled_for(marked))
    check(
        "an all-blank parameterType column still asks for nothing",
        not hierarchical.enabled_for(plain.assign(parameterType=["", ""])),
    )
    check(
        "the inner ids come back in table order",
        hierarchical.inner_ids(marked) == ["sc_obs_x"],
        f"{hierarchical.inner_ids(marked)}",
    )

    # 7 ---- the accounting rule that keeps selection honest ----------------
    #        an inner parameter keeps estimate=1, so k is unchanged; otherwise a
    #        candidate could win by moving parameters into the inner problem
    table = pd.DataFrame(
        {
            "parameterId": ["k1", "sc_obs_x", "off_obs_x", "sigma_obs_x"],
            "estimate": [1, 1, 1, 1],
        }
    )
    k_before = int((table["estimate"] == 1).sum())
    marks, _ = hierarchical.marks(assembly("factor_offset"), Spec(True))
    after = table.copy()
    after["parameterType"] = [marks.get(str(p), "") for p in after["parameterId"]]
    k_after = int((after["estimate"] == 1).sum())
    check(
        "marking leaves every `estimate` flag alone, so k is unchanged",
        k_before == k_after == 4,
        f"k {k_before} -> {k_after}",
    )
    check(
        "the two inner parameters are still counted among the estimated ones",
        all(
            int(after.loc[after.parameterId == pid, "estimate"].iloc[0]) == 1
            for pid in ("sc_obs_x", "off_obs_x")
        ),
        "an inner parameter that stopped counting would let a search hide "
        "parameters to win",
    )
    check(
        "and the marks land only on the two the rules chose",
        list(after["parameterType"]) == ["", "scaling", "offset", ""],
        f"{list(after['parameterType'])}",
    )

    # 8 ---- NaN is blank, which a CSV round-trip makes the REAL case -------
    import numpy as np

    allnan = pd.DataFrame(
        {"parameterId": ["a", "b"], "parameterType": [np.nan, np.nan]}
    )
    check(
        "an all-NaN parameterType column asks for nothing",
        not hierarchical.enabled_for(allnan) and hierarchical.inner_ids(allnan) == [],
        f"enabled={hierarchical.enabled_for(allnan)} "
        f"ids={hierarchical.inner_ids(allnan)}",
    )
    mixed = pd.DataFrame(
        {
            "parameterId": ["k", "sc", "off"],
            "parameterType": [np.nan, "scaling", "offset"],
        }
    )
    check(
        "and a mixed column names only the marked rows",
        hierarchical.enabled_for(mixed)
        and hierarchical.inner_ids(mixed) == ["sc", "off"],
        f"{hierarchical.inner_ids(mixed)}",
    )

    # 9 ---- the end-to-end acceptance, from the runs on disk ---------------
    #        same optimum, fewer outer dimensions, k unchanged; read from two runs
    #        on disk (the pair takes minutes) and asserted only when both exist

    pair = {}
    from tests._record import run_root, work

    for label in ("c6_off", "c6_on"):
        # the run is a record, <user runs>/<label>.h5
        root = run_root(label, USER_RUNS)
        est = work(root, 0) / "estimation"
        if root.exists() and est.exists():
            pair[label] = est.get()
    if len(pair) == 2:
        off, on = pair["c6_off"], pair["c6_on"]
        check(
            "the hierarchical optimum matches the plain one",
            abs(off["best_fval"] - on["best_fval"]) < 1e-4,
            f"{off['best_fval']:.6f} vs {on['best_fval']:.6f}",
        )
        check(
            "with fewer OUTER dimensions",
            len(on["x_names"]) == len(off["x_names"]) - 1,
            f"{len(off['x_names'])} -> {len(on['x_names'])}",
        )
        check(
            "the inner value is NAMED, not numbered",
            list(on["estimated_inner"]) == ["sc_obs_pR"],
            f"{on['estimated_inner']}",
        )
        check(
            "and it is in the fitted vector, so every consumer sees the whole fit",
            set(on["best_x_unscaled"]) == set(off["best_x_unscaled"]),
            f"on={sorted(on['best_x_unscaled'])}",
        )
    else:
        print(
            "\n  ! SKIPPED the end-to-end pair: runs/c6_off.h5 and runs/c6_on.h5 are "
            "not both on disk.\n    Reproduce with the hierarchical overlay. "
            "(Skipped, not passed.)"
        )

    print()
    test_hierarchical_refuses_every_noise_shape_it_cannot_solve()
    test_the_refusal_reaches_the_thing_that_consumes_it()
    return finish(
        "HIERARCHICAL",
        "HIERARCHICAL OK — the measured cells are used, the wrong ones refused by name",
    )


if __name__ == "__main__":
    raise SystemExit(main())
