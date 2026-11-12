"""Generate the SynMod-4 ("ABCD") synthetic dataset. Deterministic: numpy seed
20260901, scipy LSODA at rtol 1e-8.

GROUND TRUTH — this file and `truth/` are the only places it is written down.
The pipeline stages `description.md` and `data/synmod4_ms.csv` into agent
context and nothing else; `truth/` must never be staged.

    States   Aa = KinA_p, Ba = RegB_p, D = ProD.  PreC is not a state:
             the precursor pool is Ctot - D by conservation.
    Totals   Atot = Btot = 1 (normalised), Ctot = 5 uM.

    dAa/dt = k_act*u*(Atot - Aa) - k_deact*Aa
    dBa/dt = k_actB_eff*Aa*(Btot - Ba)/(1 + D/K_fb) - k_deactB*Ba
    dD/dt  = (k_cat1*Ba + k_cat2*Aa)*(Ctot - D) - k_deg*D

    k_actB_eff = k_actB * (1 - 0.95*bx11)      BX-11 blocks RegB activation 95%

Two features are deliberately NOT obvious from the description and are what a
blind modelling run has to discover:

  1. k_cat2 — KinA converts PreC directly, in parallel with RegB. Visible
     because ProD keeps rising under BX-11, where the RegB route is shut.
  2. K_fb — the product feeds back onto RegB activation. Visible as a RegB_p
     overshoot at high dose: RegB_p peaks early, then relaxes as ProD builds.

This script refuses to write the dataset if either signature has been tuned
away (see SIGNATURE CHECKS below): a benchmark whose discriminating features
are invisible in the data is a benchmark that scores noise.

Negative values are NOT clipped. Additive noise around a near-zero t=0 signal
genuinely produces them; clipping would hand the pipeline a censored dataset
while telling it the noise is Gaussian.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

SEED = 20260901

# ------------------------------------------------------------------ truth
ATOT = 1.0  # total KinA, normalised (description states totals calibrated to 1)
BTOT = 1.0  # total RegB, normalised
CTOT = 5.0  # total PreC + ProD pool, uM (description states ~5 uM calibrated)

K_ACT = 0.08  # 1/(min * dose)   inducer-driven KinA activation
K_DEACT = 0.15  # 1/min            KinA deactivation
K_ACTB = 0.9  # 1/(min * uM)     KinA-catalysed RegB activation
K_DEACTB = 0.12  # 1/min           RegB deactivation
K_FB = 1.5  # uM               product feedback constant on RegB activation
K_CAT1 = 0.05  # 1/(min * uM)     RegB-catalysed PreC -> ProD
K_CAT2 = 0.018  # 1/(min * uM)     KinA-catalysed PreC -> ProD (the hidden leg)
K_DEG = 0.02  # 1/min            ProD degradation + dilution

BX11_BLOCK = 0.95  # BX-11 removes 95% of RegB activation (">90%" in the note)

Y0 = (0.0, 0.0, 0.0)  # Aa, Ba, D at t = 0 (uninduced)

SIGMA_KINA = 0.05  # uM, additive
SIGMA_REGB = 0.05  # uM, additive
SIGMA_PROD = 0.15  # uM, additive

# ------------------------------------------------------------------ design
CONDITIONS = [  # (u, bx11)
    (0.25, 0),
    (1.0, 0),
    (4.0, 0),
    (1.0, 1),
    (4.0, 1),
]
TIMES_MIN = [0.0, 5.0, 15.0, 30.0, 50.0, 75.0, 100.0, 120.0]
REPLICATES = [1, 2]

COLUMNS = ["u", "bx11", "time_min", "replicate", "KinA_p_uM", "RegB_p_uM", "ProD_uM"]

# Signature thresholds. Failing either means the case is not discriminating and
# must not ship; the docstring of `_signatures` says what may be adjusted.
MIN_PROD_UNDER_BX11 = 0.5  # uM, D(120) at u=1, bx11=1
MIN_OVERSHOOT_RATIO = 1.15  # max_t Ba / Ba(120) at u=4, bx11=0

ADJUSTMENTS: list[str] = []  # filled if a signature had to be restored


def rhs(t: float, y: np.ndarray, u: float, bx11: int) -> list[float]:
    aa, ba, d = y
    k_actb_eff = K_ACTB * (1.0 - BX11_BLOCK * bx11)
    d_aa = K_ACT * u * (ATOT - aa) - K_DEACT * aa
    d_ba = k_actb_eff * aa * (BTOT - ba) / (1.0 + d / K_FB) - K_DEACTB * ba
    d_d = (K_CAT1 * ba + K_CAT2 * aa) * (CTOT - d) - K_DEG * d
    return [d_aa, d_ba, d_d]


def simulate(u: float, bx11: int, t_eval: np.ndarray) -> np.ndarray:
    """Noiseless truth at the requested times. Returns (n_times, 3): Aa, Ba, D."""
    sol = solve_ivp(
        rhs,
        (0.0, float(np.max(t_eval))),
        Y0,
        args=(u, bx11),
        method="LSODA",
        rtol=1e-8,
        atol=1e-10,
        t_eval=t_eval,
    )
    if not sol.success:
        raise RuntimeError(f"integration failed at u={u}, bx11={bx11}: {sol.message}")
    return sol.y.T


def _signatures() -> tuple[bool, list[str], dict]:
    """Check the two discriminating features in the NOISELESS truth.

    If one fails the only sanctioned repairs are: raise K_CAT2 (cap 0.02) to
    strengthen the direct KinA route, or lower K_FB (floor 0.8) to deepen the
    feedback. Anything else changes the case rather than restoring it.
    """
    dense = np.linspace(0.0, 120.0, 1201)
    lines, ok = [], True

    y_bx = simulate(1.0, 1, dense)
    d120_bx = float(y_bx[-1, 2])
    passed = d120_bx >= MIN_PROD_UNDER_BX11
    ok &= passed
    lines.append(
        f"  signature 1  direct KinA->ProD leg: D(120 | u=1, bx11=1) = "
        f"{d120_bx:.3f} uM  (need >= {MIN_PROD_UNDER_BX11})  "
        f"{'OK' if passed else 'FAIL'}"
    )

    y_hi = simulate(4.0, 0, dense)
    ba_max = float(np.max(y_hi[:, 1]))
    ba_end = float(y_hi[-1, 1])
    ratio = ba_max / ba_end if ba_end > 0 else np.inf
    passed = ratio > MIN_OVERSHOOT_RATIO
    ok &= passed
    lines.append(
        f"  signature 2  product feedback on RegB: at u=4, bx11=0 "
        f"max_t RegB_p = {ba_max:.3f} uM at t = "
        f"{dense[int(np.argmax(y_hi[:, 1]))]:.0f} min, RegB_p(120) = "
        f"{ba_end:.3f} uM, ratio = {ratio:.2f}  "
        f"(need > {MIN_OVERSHOOT_RATIO})  {'OK' if passed else 'FAIL'}"
    )

    detail = {
        "prod_120_u1_bx11": d120_bx,
        "regb_max_u4": ba_max,
        "regb_120_u4": ba_end,
        "regb_overshoot_ratio": ratio,
    }
    return ok, lines, detail


def _truth_json(detail: dict) -> dict:
    return {
        "system": "SynMod-4 (fictional engineered module, S. cerevisiae)",
        "generator": {
            "script": "make_data.py",
            "seed": SEED,
            "integrator": "scipy.integrate.solve_ivp, method=LSODA, "
            "rtol=1e-8, atol=1e-10",
            "noise": "additive Gaussian, drawn per column over all 80 rows in "
            "column order KinA_p, RegB_p, ProD; negatives not clipped",
        },
        "states": {
            "Aa": "KinA_p, active kinase (uM, normalised total)",
            "Ba": "RegB_p, active regulator (uM, normalised total)",
            "D": "ProD, product (uM); PreC = Ctot - D is not a state",
        },
        "initial_conditions": {"Aa": Y0[0], "Ba": Y0[1], "D": Y0[2]},
        "totals": {"Atot": ATOT, "Btot": BTOT, "Ctot": CTOT},
        "true_parameters": {
            "k_act": K_ACT,
            "k_deact": K_DEACT,
            "k_actB": K_ACTB,
            "k_deactB": K_DEACTB,
            "K_fb": K_FB,
            "k_cat1": K_CAT1,
            "k_cat2": K_CAT2,
            "k_deg": K_DEG,
        },
        "parameter_units": {
            "k_act": "1/(min*dose)",
            "k_deact": "1/min",
            "k_actB": "1/(min*uM)",
            "k_deactB": "1/min",
            "K_fb": "uM",
            "k_cat1": "1/(min*uM)",
            "k_cat2": "1/(min*uM)",
            "k_deg": "1/min",
        },
        "inhibitor": {
            "parameter": "bx11",
            "effect": f"k_actB multiplied by (1 - {BX11_BLOCK}) when bx11 = 1",
        },
        "noise_sd": {
            "KinA_p_uM": SIGMA_KINA,
            "RegB_p_uM": SIGMA_REGB,
            "ProD_uM": SIGMA_PROD,
        },
        "conditions": [
            {"u": u, "bx11": b, "condition_label": f"u={u:g},bx={b:g}"}
            for u, b in CONDITIONS
        ],
        "times_min": TIMES_MIN,
        "replicates": REPLICATES,
        "discriminating_signatures": detail,
        "adjustments_from_specified_truth": ADJUSTMENTS,
    }


def main() -> int:
    ok, lines, detail = _signatures()
    print("SynMod-4 discriminating-signature check (noiseless truth):")
    for line in lines:
        print(line)
    if not ok:
        print(
            "\nSTOP: a discriminating signature is absent. The dataset was "
            "NOT written. Raise k_cat2 (cap 0.02) or lower K_fb (floor 0.8) "
            "and re-run.",
            file=sys.stderr,
        )
        return 1

    t_eval = np.asarray(TIMES_MIN, dtype=float)
    rows, sanity = [], []
    for u, bx11 in CONDITIONS:
        y = simulate(u, bx11, t_eval)
        sanity.append((u, bx11, float(y[-1, 0]), float(y[-1, 1]), float(y[-1, 2])))
        for i, t in enumerate(TIMES_MIN):
            for rep in REPLICATES:
                rows.append(
                    {
                        "u": u,
                        "bx11": bx11,
                        "time_min": t,
                        "replicate": rep,
                        "KinA_p_uM": y[i, 0],
                        "RegB_p_uM": y[i, 1],
                        "ProD_uM": y[i, 2],
                    }
                )

    df = pd.DataFrame(rows, columns=COLUMNS)
    rng = np.random.default_rng(SEED)
    n = len(df)
    df["KinA_p_uM"] = df["KinA_p_uM"] + rng.normal(0.0, SIGMA_KINA, size=n)
    df["RegB_p_uM"] = df["RegB_p_uM"] + rng.normal(0.0, SIGMA_REGB, size=n)
    df["ProD_uM"] = df["ProD_uM"] + rng.normal(0.0, SIGMA_PROD, size=n)

    here = Path(__file__).parent
    out = here / "data" / "synmod4_ms.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    truth = here / "truth" / "true_parameters.json"
    truth.parent.mkdir(parents=True, exist_ok=True)
    truth.write_text(json.dumps(_truth_json(detail), indent=2) + "\n")

    print(f"\nwrote {out} ({len(df)} rows, {len(df.columns)} columns)")
    print(f"wrote {truth}")
    print("\nnoiseless truth at t = 120 min:")
    print(f"  {'u':>5} {'bx11':>5} {'KinA_p':>9} {'RegB_p':>9} {'ProD':>9}")
    for u, bx11, aa, ba, d in sanity:
        print(f"  {u:>5g} {bx11:>5g} {aa:>9.3f} {ba:>9.3f} {d:>9.3f}")
    print("\nfirst rows as written:")
    print(df.head().to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
