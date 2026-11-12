"""Generate the toy_decay_params synthetic dataset. Deterministic: numpy seed 43.

GROUND TRUTH — this file is the only place it is written down. The agents see
`description.md` and `data/decay.csv`, never this.

    dA/dt = -k1 * A,  A(0) = A0
    A0 = 10,  k1 = 0.35 /h
    measured  y = A + Normal(0, 0.3)

No scale factor: the readout is a calibrated fluorescence signal in units that
are approximately absolute concentration. That is the point of this case — the
pipeline should NOT introduce an observable scaling parameter here, and doing
so would make k1 and the scale trade off in the profile.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 43

A0 = 10.0  # initial reporter level, calibrated a.u.
K1 = 0.35  # 1/h
SIGMA = 0.3  # additive readout noise, calibrated a.u.

TIMES_H = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
REPLICATES = [1, 2]


def a_true(t: np.ndarray) -> np.ndarray:
    """Analytic solution of first-order decay after synthesis shutoff."""
    return A0 * np.exp(-K1 * t)


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows = []
    for t in TIMES_H:
        for rep in REPLICATES:
            rows.append(
                {
                    "time_h": t,
                    "replicate": rep,
                    "A_conc": float(a_true(np.array(t))),
                }
            )
    df = pd.DataFrame(rows, columns=["time_h", "replicate", "A_conc"])
    df["A_conc"] = df["A_conc"] + rng.normal(0.0, SIGMA, size=len(df))

    out = Path(__file__).parent / "data" / "decay.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} rows)")
    print(df.head().to_string(index=False))


if __name__ == "__main__":
    main()
