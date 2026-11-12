"""What the replicates say about the error model, before any model exists.

  1. the verdict (log spread on log signal: slope 0 additive, 1 multiplicative);
  2. too little data, or an interval that excludes neither, says inconclusive;
  3. the distribution family is not claimed (2 replicates cannot reach the tails);
  4. every dropped cell is counted, so the cell counts reconcile;
  5. the artifact is byte-deterministic and independent of row order;
  6. a malformed table is refused, naming its missing columns;
  7. noise findings reach the observation model and interpreter, never construction;
  8. raw series get bin-free shape descriptors;
  9. support: zeros, negatives, counts and log legality are reported;
  10. level drift: a whole-group offset shows in the F ratio;
  11. closure carries the drift where there are no replicates (the CTD case).

    uv run python tests/data_signals_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from _harness import check, finish  # noqa: E402

from octomod.workflow_modules.data import data_signals  # noqa: E402


def synth(kind: str, seed: int = 7, n_times: int = 9, n_cond: int = 2) -> pd.DataFrame:
    """A long table with a known error model, over a decade of signal."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_cond):
        for i in range(n_times):
            t = float(i * 10)
            mu = 0.5 * (10 ** (i / (n_times - 1))) * (1 + c)  # ~1 decade of range
            for rep in (1, 2):
                if kind == "additive":
                    v = mu + 0.3 * rng.standard_normal()
                elif kind == "multiplicative":
                    v = mu * (1.0 + 0.15 * rng.standard_normal())
                else:  # a middle case, on purpose
                    v = mu + 0.15 * mu**0.5 * rng.standard_normal()
                rows.append(
                    {
                        "observable_label": "y",
                        "condition_label": f"c{c}",
                        "condition_key": f"c{c}",
                        "time": t,
                        "value": v,
                        "replicate": rep,
                    }
                )
    return pd.DataFrame(rows)


def noise_of(df: pd.DataFrame) -> dict:
    return data_signals.compute(df)["per_observable"]["y"]["noise"]


def main() -> int:
    # 1 ---- the verdict, on data whose error model is known ---------------
    add = noise_of(synth("additive"))
    check(
        "constant error reads as ADDITIVE",
        add["error_model"] == "additive",
        f"slope {add['spread_vs_magnitude_slope']} CI {add['slope_ci95']}",
    )
    mult = noise_of(synth("multiplicative"))
    check(
        "proportional error reads as MULTIPLICATIVE",
        mult["error_model"] == "multiplicative",
        f"slope {mult['spread_vs_magnitude_slope']} CI {mult['slope_ci95']}",
    )
    check(
        "and the two slopes are on opposite sides of 0.5",
        add["spread_vs_magnitude_slope"] < 0.5 < mult["spread_vs_magnitude_slope"],
        f"{add['spread_vs_magnitude_slope']} vs {mult['spread_vs_magnitude_slope']}",
    )
    check(
        "each verdict names the interval it rests on",
        "excludes" in add["why"] and "excludes" in mult["why"],
        add["why"][:90],
    )

    # 2 ---- restraint: too little data says so, it does not guess ---------
    tiny = noise_of(synth("additive", n_times=2, n_cond=1))
    check(
        "two replicate cells give NO verdict",
        tiny["error_model"] == "inconclusive" and "at least" in tiny["why"],
        f"{tiny['error_model']}: {tiny['why'][:80]}",
    )
    # a square-root error model sits between the two hypotheses
    middle = noise_of(synth("sqrt", n_times=5, n_cond=1))
    check(
        "a case the interval cannot separate says inconclusive, not the nearer one",
        middle["error_model"] in ("inconclusive", "neither"),
        f"{middle['error_model']} at slope {middle['spread_vs_magnitude_slope']} "
        f"CI {middle['slope_ci95']}",
    )

    # 3 ---- the family is NOT claimed ------------------------------------
    check(
        "the distribution family is explicitly not tested",
        "NOT TESTED" in add["distribution_family"],
        add["distribution_family"][:80],
    )
    check(
        "and the kurtosis it reports instead is labelled descriptive",
        "descriptive" in add["distribution_family"],
    )

    # 4 ---- every cell is accounted for ----------------------------------
    df = synth("additive")
    # plant a cell whose mean is zero (log undefined) and one with identical
    # replicates (zero spread) — both must be counted, not vanish
    df.loc[(df.condition_key == "c0") & (df.time == 0.0), "value"] = [-1.0, 1.0]
    df.loc[(df.condition_key == "c1") & (df.time == 10.0), "value"] = [4.0, 4.0]
    n = noise_of(df)
    total = n["n_cells_with_replicates"]
    parts = (
        n["n_usable_cells"]
        + n["n_cells_dropped_nonpositive_mean"]
        + n["n_cells_dropped_zero_spread"]
    )
    check(
        "the cell counts reconcile exactly",
        total == parts,
        f"{total} = {n['n_usable_cells']} usable + "
        f"{n['n_cells_dropped_nonpositive_mean']} non-positive + "
        f"{n['n_cells_dropped_zero_spread']} zero-spread",
    )
    check(
        "the planted non-positive-mean cell was counted, not skipped",
        n["n_cells_dropped_nonpositive_mean"] >= 1,
        f"{n['n_cells_dropped_nonpositive_mean']}",
    )
    check(
        "the planted zero-spread cell was counted, not skipped",
        n["n_cells_dropped_zero_spread"] >= 1,
        f"{n['n_cells_dropped_zero_spread']}",
    )

    # 5 ---- byte-deterministic ------------------------------------------
    a = json.dumps(data_signals.compute(synth("additive")), sort_keys=True)
    b = json.dumps(data_signals.compute(synth("additive")), sort_keys=True)
    check(
        "two computations over one table are byte-identical", a == b, f"{len(a)} chars"
    )
    shuffled = synth("additive").sample(frac=1.0, random_state=3).reset_index(drop=True)
    c = json.dumps(data_signals.compute(shuffled), sort_keys=True)
    check(
        "and row ORDER does not change the artifact",
        a == c,
        "a shuffled long table gives the same signals",
    )

    # 6 ---- a malformed table refuses instead of half-answering ----------
    bad = data_signals.compute(pd.DataFrame({"value": [1.0, 2.0]}))
    check(
        "a table missing its columns is refused, naming them",
        not bad.get("available") and "observable_label" in bad.get("why", ""),
        bad.get("why", ""),
    )

    # 7 ---- routing: never to construction, which never sees measured values,
    #        so that a blind run stays blind
    s3 = (REPO / "octomod" / "workflow_modules" / "assembly" / "engine.py").read_text()
    s1 = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    check(
        "the observation-model agent receives them",
        'obs_ctx["data_signals"]' in s3,
    )
    check(
        "the interpreter receives them",
        '"data_signals": _data_signals_for_interpreter(ctx)' in s7,
    )
    check(
        "and CONSTRUCTION never mentions them at all",
        "data_signals" not in s1,
        "a data-derived noise statistic in the construction context would end "
        "the blind-run guarantee",
    )

    # 8 ---- what the shape descriptors do without a model ----------------
    shapes = data_signals.compute(synth("additive"))["per_observable"]["y"][
        "shape_per_condition"
    ]
    one = next(iter(shapes.values()))
    check(
        "raw series get bin-free shape descriptors",
        {"monotone_trend_rho", "time_of_max", "peaks_then_declines"} <= set(one),
        f"{sorted(one)}",
    )
    check(
        "and a rising series is reported as rising",
        one["monotone_trend_rho"] > 0.8,
        f"rho {one['monotone_trend_rho']}",
    )

    # 9 ---- support -----------------------------------------------------
    print("\nSUPPORT — which noise models are even legal")
    sup = data_signals.compute(synth("additive"))["per_observable"]["y"]["support"]
    check(
        "support reports zeros, negatives, range and log legality",
        {
            "n_zero",
            "n_negative",
            "integer_valued",
            "dynamic_range",
            "log_transform_legal",
        }
        <= set(sup),
        f"{sorted(sup)}",
    )
    z = synth("additive")
    z.loc[z.index[:4], "value"] = 0.0
    sup_z = data_signals.compute(z)["per_observable"]["y"]["support"]
    check(
        "data containing zeros is declared illegal for a log transform",
        sup_z["log_transform_legal"] is False and sup_z["n_zero"] >= 4,
        f"legal={sup_z['log_transform_legal']} zeros={sup_z['n_zero']}",
    )
    counts = synth("additive")
    counts["value"] = np.round(np.abs(counts["value"]) * 100)
    sup_c = data_signals.compute(counts)["per_observable"]["y"]["support"]
    check(
        "whole-number data is flagged COUNT-LIKE",
        sup_c["integer_valued"] and "COUNT-LIKE" in sup_c["reading"],
        sup_c["reading"][:60],
    )

    # 10 ---- level drift ------------------------------------------------
    print("\nLEVEL DRIFT — a whole-group offset the model has no parameter for")

    def drifted(frac: float) -> pd.DataFrame:
        rng = np.random.default_rng(4)
        rows = []
        for cond in ("c1", "c2", "c3"):
            for t in (0, 5, 15, 30, 50, 75):
                base = 10 * np.exp(-t / 40) + 1
                for rep in (1, 2, 3):
                    rows.append(
                        dict(
                            observable_label="y",
                            condition_key=cond,
                            time=t,
                            replicate=rep,
                            value=base * (1 + frac * (rep - 2)) + rng.normal(0, 0.05),
                        )
                    )
        return pd.DataFrame(rows)

    quiet = data_signals.compute(drifted(0.0))["per_observable"]["y"]["level_drift"]
    loud = data_signals.compute(drifted(0.05))["per_observable"]["y"]["level_drift"]
    check(
        "no drift stays under the notable threshold",
        quiet["replicate"]["f_ratio"] < data_signals.DRIFT_F_NOTABLE,
        f"F={quiet['replicate']['f_ratio']}",
    )
    check(
        "a 5% per-injection shift is far above it",
        loud["replicate"]["f_ratio"] > 10 * data_signals.DRIFT_F_NOTABLE,
        f"F={loud['replicate']['f_ratio']}",
    )
    # A ratio over the RAW within-cell variance saturates near 1.3, because with
    # `by`=replicate the drift IS the within-cell spread; the F ratio must not.
    check(
        "the F ratio clears the ceiling the previous statistic could not",
        loud["replicate"]["f_ratio"] > 20.0,
        f"F={loud['replicate']['f_ratio']} (old statistic maxed out near 1.3)",
    )
    check(
        "`time` is deliberately NOT a drift column",
        "time" not in data_signals.DRIFT_COLUMNS,
        f"{data_signals.DRIFT_COLUMNS}",
    )

    # 11 ---- closure ----------------------------------------------------
    print("\nCLOSURE — the CTD case, which has no replicates at all")
    ctd = REPO / "testcase" / "ctd_petab" / "supplied" / "petab" / "measurementData.tsv"
    m = pd.read_csv(ctd, sep="\t")
    long = pd.DataFrame(
        {
            "observable_label": m["observableId"],
            "condition_key": m["simulationConditionId"],
            "time": m["time"],
            "value": m["measurement"],
        }
    )
    cells = m.groupby(["observableId", "simulationConditionId", "time"]).size()
    check(
        "the literature deposit really has no replicates (an earlier test plan assumed it did)",
        set(cells.unique()) == {1},
        f"rows per cell {sorted(cells.unique())}",
    )
    clo = data_signals.compute(long)["closure"]
    check(
        "so closure, not replicates, is what carries the drift there",
        clo["available"] and clo["max_over_min"] > 4.0,
        f"max/min {clo.get('max_over_min')}",
    )
    check(
        "and the reading asks the conserved-pool question rather than deciding",
        "conserved quantity" in clo["reading"] and "Which is it?" in clo["reading"],
        clo["reading"][:70],
    )
    flat = pd.DataFrame(
        [
            dict(observable_label=f"f{i}", condition_key=c, time=t, value=v)
            for c in ("c1", "c2")
            for t in (0, 10, 20)
            for i, v in enumerate((0.5, 0.3, 0.2))
        ]
    )
    check(
        "a genuinely closed set is reported as stable",
        "stable" in data_signals.compute(flat)["closure"]["reading"],
        data_signals.compute(flat)["closure"]["reading"][:60],
    )
    # sums that genuinely vary AND cross zero — the abcd shape, where a
    # background subtraction puts readings on both sides of zero
    neg = pd.DataFrame(
        [
            dict(observable_label=f"f{i}", condition_key="c1", time=t, value=v)
            for t, trio in ((0, (-1.0, 0.4, 0.3)), (10, (2.0, 1.5, 0.9)))
            for i, v in enumerate(trio)
        ]
    )
    check(
        "sums that are not strictly positive say the ratio is undefined, "
        "never 'stable'",
        "undefined" in data_signals.compute(neg)["closure"]["reading"]
        and "stable" not in data_signals.compute(neg)["closure"]["reading"],
        data_signals.compute(neg)["closure"]["reading"][:70],
    )

    # ---------------------------------------------------------------- routing
    check(
        "none of the new signals reach construction",
        "data_signals"
        not in __import__("octomod.agents.routing", fromlist=["x"]).allowed(
            "construction"
        ),
        "data_signals is granted to construction",
    )

    print()
    return finish(
        "DATA SIGNALS",
        "DATA SIGNALS OK — the verdict is measured, and the rest is refused by name",
    )


if __name__ == "__main__":
    raise SystemExit(main())
