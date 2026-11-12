"""Generate the toy_phos synthetic dataset. Deterministic: numpy seed 42.

GROUND TRUTH — this file is the only place it is written down. The agents see
`description.md` and `data/timecourse.csv`, never this.

    R <-> Rp, total receptor conserved at Rtot = 10 (a.u.)
    a  = kp * dose            (pseudo-first-order phosphorylation rate)
    Rp(t) = Rtot * a/(a+kd) * (1 - exp(-(a+kd) * t))
    kp = 0.05 /(min*dose),  kd = 0.1 /min
    measured  y = 3.7 * Rp + Normal(0, 1.2)

The scale factor 3.7 is the point of the case: the readout is arbitrary
densitometry, so a correct pipeline must introduce an observable scaling
parameter rather than compare Rp to y directly.

Negative values are NOT clipped. Additive noise around a near-zero t=0 signal
genuinely produces them, and clipping would hand the pipeline a censored
dataset while telling it the noise is Gaussian — the exact dishonesty the
noise-model gate is supposed to catch.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42

RTOT = 10.0  # total receptor, arbitrary normalised units
KP = 0.05  # 1/(min * dose)
KD = 0.1  # 1/min
SCALE = 3.7  # densitometry units per unit Rp
SIGMA = 1.2  # additive readout noise, densitometry units

DOSES = [0.3, 1.0, 3.0]
TIMES_MIN = [0.0, 5.0, 10.0, 20.0, 40.0, 60.0]
REPLICATES = [1, 2]


def rp_true(t: np.ndarray, dose: float) -> np.ndarray:
    """Analytic solution of the two-state module at constant ligand dose."""
    a = KP * dose
    return RTOT * a / (a + KD) * (1.0 - np.exp(-(a + KD) * t))


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = []
    for dose in DOSES:
        for t in TIMES_MIN:
            for rep in REPLICATES:
                rows.append(
                    {
                        "dose": dose,
                        "time_min": t,
                        "replicate": rep,
                        "pR_au": SCALE * float(rp_true(np.array(t), dose)),
                    }
                )
    df = pd.DataFrame(rows, columns=["dose", "time_min", "replicate", "pR_au"])
    df["pR_au"] = df["pR_au"] + rng.normal(0.0, SIGMA, size=len(df))

    out = Path(__file__).parent / "data" / "timecourse.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} rows)")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
