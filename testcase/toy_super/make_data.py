"""Generate the toy_super synthetic dataset. Deterministic: numpy seed
20260910, scipy LSODA at rtol 1e-8.

GROUND TRUTH — this file and `truth/` are the only places it is written down.
The pipeline stages `description.md` and `data/sensor_ts.csv` into agent context
and nothing else; `truth/` must never be staged.

WHY THIS FIXTURE EXISTS. The supermodel encoding
had no end-to-end exercise: no shipped axis declared a `neutral_value`, so
`partition` / `verified_partition` / `enumerate_grouped` and the T1 neutrality
gate only ever ran on synthetic dictionaries. This case is written so that two
of its three axes are EXACTLY neutralizable and one deliberately is not, which
is the mixed grouping the module describes — and the saving it claims (one
compile per structure instead of one per candidate) becomes measurable.

    States   A = the active sensor (normalised, Atot = 1)
             P = the product (uM)

    dA/dt = k_in * u * (Atot - A) / (1 + fb*P)  -  k_out * A
    dP/dt = k_cat * A  +  k_alt * u  -  k_deg * P

Three structural questions the description leaves open, and how each is written:

  fb     product feedback on sensor activation, written as a STRENGTH that is
         off at fb = 0 rather than as a half-saturating constant that is off at
         infinity. Exactly neutralizable: at fb = 0 the rate law is character
         for character the base model's. This is the true mechanism.
  k_alt  an input route to the product that bypasses the sensor entirely, off
         at k_alt = 0. Exactly neutralizable, and FALSE in the truth — so the
         fixture has a wrong-but-cheap axis, which is what makes the criterion
         comparison informative rather than a parameter-count contest.
  v_max  zeroth-order product loss, replacing first-order. NOT neutralizable
         and declares no neutral value, because no constant equals k_deg*P.
         It must fall out of the supermodel and stay its own structure.

The discriminating signature is A's SHAPE at high dose: with feedback, A rises,
peaks and relaxes as P accumulates; without it, A rises monotonically to a
plateau at any parameter setting. That is a qualitative impossibility for the
no-feedback candidates, not a tight fit, so the AIC gap should be large. The
SIGNATURE CHECKS below refuse to write the dataset if it is not visible above
the noise — a benchmark whose discriminating feature is invisible scores noise.

Negative values are NOT clipped: additive noise around a near-zero t=0 signal
genuinely produces them, and clipping would hand the pipeline a censored
dataset while telling it the noise is Gaussian.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

SEED = 20260910
HERE = Path(__file__).parent

ATOT = 1.0
# Chosen by searching a grid against SIGNATURE CHECKS, not by hand: the first
# hand-set values put the feedback's effect at the BOTTOM dose rather than the
# top (the sensor was saturated at high input, so dividing a large activation
# term still left A near 1), which inverts the contrast the dose series exists
# to provide. The checks caught it; these values clear all five.
TRUE = {
    "k_in": 0.085,  # 1/(min*dose) — sensor activation per unit input
    "k_out": 0.28,  # 1/min        — sensor deactivation
    "fb": 0.62,  # 1/uM         — product feedback strength (TRUE, axis on)
    "k_cat": 0.72,  # uM/min       — product formation per unit active sensor
    "k_alt": 0.0,  # uM/(min*dose)— bypass route (FALSE, axis off)
    "k_deg": 0.032,  # 1/min        — first-order product loss
}
DOSES = (0.5, 2.0, 8.0)
TIMES = (0.0, 5.0, 15.0, 30.0, 50.0, 80.0, 120.0)
REPLICATES = 2
SIGMA = {"A_frac": 0.035, "P_uM": 0.12}


def rhs(_t, y, u, p):
    a, prod = y
    activation = p["k_in"] * u * (ATOT - a) / (1.0 + p["fb"] * prod)
    return [
        activation - p["k_out"] * a,
        p["k_cat"] * a + p["k_alt"] * u - p["k_deg"] * prod,
    ]


def solve(u: float, p: dict, times=TIMES) -> np.ndarray:
    out = solve_ivp(
        rhs,
        (0.0, max(times)),
        [0.0, 0.0],
        t_eval=np.asarray(times, dtype=float),
        args=(u, p),
        method="LSODA",
        rtol=1e-8,
        atol=1e-10,
    )
    assert out.success, out.message
    return out.y


def signature_checks(p: dict) -> list[str]:
    """Refuse to ship a dataset whose discriminating feature is invisible.

    Two claims, both about what a NO-FEEDBACK model cannot do:

      1. A is non-monotone at the top dose, by more than the measurement noise.
         A model without feedback rises monotonically at every parameter value,
         so this is a qualitative separation rather than a tight fit.
      2. The bypass route is genuinely off. If `k_alt` were nonzero in the
         truth the fixture would be testing two mechanisms at once, and a
         reader could not tell which one the criterion found.
    """
    problems = []
    fine = np.linspace(0.0, max(TIMES), 400)
    a_top = solve(max(DOSES), p, fine)[0]
    peak = float(a_top.max())
    tail = float(a_top[-1])
    drop = peak - tail
    if drop < 3.0 * SIGMA["A_frac"]:
        problems.append(
            f"the sensor's overshoot at u={max(DOSES)} is {drop:.4f}, under 3 "
            f"sigma ({3 * SIGMA['A_frac']:.4f}) — a no-feedback model would fit "
            f"it and the fixture would score noise"
        )
    if float(np.argmax(a_top)) >= len(fine) - 2:
        problems.append("the sensor never peaks: A is monotone even with feedback on")
    if p["k_alt"] != 0.0:
        problems.append(f"k_alt is {p['k_alt']}, so the bypass axis is not OFF")
    # and the feedback must matter at the top dose but not at the bottom one
    off = dict(p, fb=0.0)
    lo_gap = float(
        np.max(np.abs(solve(min(DOSES), p, fine)[0] - solve(min(DOSES), off, fine)[0]))
    )
    hi_gap = float(np.max(np.abs(a_top - solve(max(DOSES), off, fine)[0])))
    if hi_gap < 4.0 * SIGMA["A_frac"]:
        problems.append(
            f"feedback changes A by only {hi_gap:.4f} at the top dose — under "
            f"4 sigma, so no dose separates the mechanisms"
        )
    if lo_gap > 2.0 * SIGMA["A_frac"]:
        problems.append(
            f"feedback already changes A by {lo_gap:.4f} at the BOTTOM dose — "
            f"the dose series then carries no contrast to learn from"
        )
    return problems


def main() -> int:
    problems = signature_checks(TRUE)
    if problems:
        print("SIGNATURE CHECKS FAILED — refusing to write the dataset:")
        for p in problems:
            print(f"  · {p}")
        return 1

    rng = np.random.default_rng(SEED)
    rows = []
    clean: dict[str, list] = {"A_frac": [], "P_uM": []}
    for u in DOSES:
        a, prod = solve(u, TRUE)
        for rep in range(1, REPLICATES + 1):
            for i, t in enumerate(TIMES):
                rows.append(
                    {
                        "u": u,
                        "time_min": t,
                        "replicate": rep,
                        "A_frac": a[i],
                        "P_uM": prod[i],
                    }
                )
        clean["A_frac"] += list(a)
        clean["P_uM"] += list(prod)
    df = pd.DataFrame(rows)
    # noise drawn per column over every row in column order, so the dataset is
    # reproducible from the seed alone
    for col in ("A_frac", "P_uM"):
        df[col] = df[col] + rng.normal(0.0, SIGMA[col], len(df))
    out = HERE / "data" / "sensor_ts.csv"
    df.to_csv(out, index=False)

    fine = np.linspace(0.0, max(TIMES), 400)
    a_top = solve(max(DOSES), TRUE, fine)[0]
    truth = {
        "system": "toy_super (fictional two-state sensor module, synthetic)",
        "why_this_case_exists": (
            "C5.6's supermodel encoding had no end-to-end exercise: no shipped "
            "axis declared a neutral_value. Two of the three axes here are "
            "exactly neutralizable and one deliberately is not."
        ),
        "generator": {
            "script": "make_data.py",
            "seed": SEED,
            "integrator": "scipy.integrate.solve_ivp, method=LSODA, rtol=1e-8, atol=1e-10",
            "noise": (
                "additive Gaussian, drawn per column over all rows in column "
                "order A_frac, P_uM; negatives not clipped"
            ),
        },
        "states": {
            "A": "A_frac, active sensor (fraction of a total normalised to 1)",
            "P": "P_uM, product (uM)",
        },
        "initial_conditions": {"A": 0.0, "P": 0.0},
        "totals": {"Atot": ATOT},
        "true_parameters": {k: v for k, v in TRUE.items()},
        "parameter_units": {
            "k_in": "1/(min*dose)",
            "k_out": "1/min",
            "fb": "1/uM",
            "k_cat": "uM/min",
            "k_alt": "uM/(min*dose)",
            "k_deg": "1/min",
        },
        "noise_sigma": dict(SIGMA),
        "design": {
            "doses": list(DOSES),
            "times": list(TIMES),
            "replicates": REPLICATES,
        },
        "true_axes": {
            "product_feedback": {
                "on": True,
                "parameter": "fb",
                "true_value": TRUE["fb"],
                "neutral_value": 0.0,
                "neutralizable": True,
                "why": (
                    "written as a strength that is off at 0, not as a "
                    "half-saturating constant that is off at infinity"
                ),
            },
            "alt_route": {
                "on": False,
                "parameter": "k_alt",
                "true_value": 0.0,
                "neutral_value": 0.0,
                "neutralizable": True,
                "why": "a cheap, exactly neutralizable axis that is FALSE here",
            },
            "zeroth_order_loss": {
                "on": False,
                "parameter": "v_max",
                "neutral_value": None,
                "neutralizable": False,
                "why": (
                    "no constant equals k_deg*P, so no parameter value turns "
                    "this rate law into the base one — it must fall out of the "
                    "supermodel and stay its own structure"
                ),
            },
        },
        "true_winner_axes": ["product_feedback"],
        "discriminating_signature": {
            "claim": (
                "the sensor is non-monotone at the top dose; a model without "
                "feedback is monotone at every parameter value"
            ),
            "peak_A_at_top_dose": round(float(a_top.max()), 5),
            "plateau_A_at_top_dose": round(float(a_top[-1]), 5),
            "overshoot": round(float(a_top.max() - a_top[-1]), 5),
            "overshoot_in_sigma": round(
                float((a_top.max() - a_top[-1]) / SIGMA["A_frac"]), 2
            ),
            "peak_time_min": round(float(fine[int(np.argmax(a_top))]), 2),
        },
        "must_never_be_staged": (
            "truth/ is the answer key. The pipeline stages description.md and "
            "data/ only; a run whose agent_io contains anything from here is void."
        ),
    }
    (HERE / "truth" / "true_parameters.json").write_text(
        json.dumps(truth, indent=2) + "\n"
    )
    print(f"wrote {out.relative_to(HERE.parent.parent)} ({len(df)} rows)")
    print("wrote truth/true_parameters.json")
    sig = truth["discriminating_signature"]
    print(
        f"signature: A peaks at {sig['peak_A_at_top_dose']} (t={sig['peak_time_min']} "
        f"min) and relaxes to {sig['plateau_A_at_top_dose']} — an overshoot of "
        f"{sig['overshoot']} = {sig['overshoot_in_sigma']} sigma"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
