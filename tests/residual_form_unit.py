"""Residual form fits name a planted trend and not autocorrelated noise (no engine).

The request fits through the curve_forms library (constant, linear,
exponential, rise-and-fall), so its forms carry that library's names.

  1. AR(1) noise is called a trend in at most 20 % of realisations;
  2. a planted relaxation is named an exponential, beating both nulls;
  3. a planted peak (overshoot, then return) is named a rise-and-fall,
     beating both nulls;
  4. a series at the noise floor is refused.

    uv run python tests/residual_form_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.evaluation.diagnostics import (  # noqa: E402
    fit_residual_form,
)

T = np.array([0, 5, 15, 30, 50, 75, 100, 120], dtype=float)


def ar1(rng, n, phi=0.7, scale=1.0):
    r = np.zeros(n)
    e = rng.normal(0, scale, n)
    r[0] = e[0]
    for i in range(1, n):
        r[i] = phi * r[i - 1] + e[i]
    return r


def main() -> int:
    rng = np.random.default_rng(20260907)
    # 1. AR(1) noise: a trend must not be declared in most realisations
    called_trend = 0
    n_trials = 30
    for _ in range(n_trials):
        out = fit_residual_form(T, ar1(rng, len(T)), n_boot=60)
        called_trend += "beats both nulls" in out["verdict"]
    rate = called_trend / n_trials
    print(
        f"AR(1) realisations called a trend: {called_trend}/{n_trials} ({rate:.0%}) "
        f"at alpha 0.05"
    )
    assert rate <= 0.2, "autocorrelated noise is being read as a nameable trend"

    # 2./3. planted relaxation and planted peak (overshoot then return — product
    # feedback's signature), clearly above the floor: the right form must be
    # named and both nulls beaten in the large majority of realisations
    hits = {"relaxation": 0, "peak": 0}
    n_planted = 20
    for _ in range(n_planted):
        r = 4.0 * np.exp(-T / 25.0) + rng.normal(0, 0.3, len(T))
        out = fit_residual_form(T, r, n_boot=60)
        hits["relaxation"] += (
            out["best_form"] == "exponential" and "beats both nulls" in out["verdict"]
        )
        r = 4.0 * (T / 20.0) * np.exp(1 - T / 20.0) + rng.normal(0, 0.3, len(T))
        out = fit_residual_form(T, r, n_boot=60)
        hits["peak"] += (
            out["best_form"] == "rise_and_fall" and "beats both nulls" in out["verdict"]
        )
    print(
        f"planted forms recovered (right form, both nulls beaten): {hits} of {n_planted}"
    )
    assert hits["relaxation"] >= 0.8 * n_planted, "planted relaxation not recovered"
    assert hits["peak"] >= 0.8 * n_planted, "planted peak not recovered"

    # 4. at the noise floor: refused
    out = fit_residual_form(T, rng.normal(0, 1, len(T)), at_floor=True)
    assert "refused" in out and "noise floor" in out["refused"]
    print("at-floor series refused:", out["refused"][:60])
    print("RESIDUAL FORM UNIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
