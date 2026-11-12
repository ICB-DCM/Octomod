"""Generate the multimodal-likelihood fixture (a supplied PEtab problem).

    uv run python testcase/toy_oscillator_multimodal/make_data.py

WHY THIS SHAPE. Every other toy in this tree is easy to fit on purpose — they
exist to exercise the pipeline, and a fit that lands in one step is what you
want when the thing under test is a gate sequence. This one exists to exercise
the OPTIMISER, so it has to be hard in a specific, well-understood way rather
than merely large.

A damped harmonic oscillator, observed over several periods, with the angular
frequency `omega` estimated:

    pos' = vel
    vel' = -omega^2 * pos - 2 * zeta * omega * vel

The likelihood in `omega` is MULTIMODAL, and the design that makes it so was
MEASURED, on the third attempt, against the quantity that actually decides it:
the PROFILE likelihood, with the nuisance parameters optimised at each omega
rather than held at truth.

The design is 50 points over 80 min with light damping (zeta = 0.02). A profile
scan over omega in [0.5, 6.0] finds 5 local minima, and the deepest is the
truth. Both halves of that sentence are load-bearing. Multimodality is what
gives a local optimiser something to fall into; the truth being GLOBAL is what
makes the fixture gradeable at all, because a case whose best fit is not the
true parameter grades an optimiser against an answer the data does not support.

Two earlier designs are recorded because each failed in a way worth not
repeating:

* **60 points over 30 min, zeta = 0.06** — built on the theory that a frequency
  off by one period over the window realigns its peaks. It does not: with dense
  sampling the whole trajectory has to match, not just the peaks. Nyquist is
  the quick way to see it — that design puts the Nyquist frequency at
  6.2 rad/min, above the entire parameter range, so nothing is ambiguous. The
  scan found exactly ONE minimum, and fides, L-BFGS-B, Powell and differential
  evolution each solved it from 20 of 20 starts.
* **20 points over 80 min, zeta = 0.015** — sparse enough to be multimodal (9
  minima) but too sparse to be identifiable: the profile optimum sits at
  omega = 2.58, not at the true 1.9. Every optimiser agreed on a wrong
  frequency with a BETTER objective value than the truth, which is a broken
  fixture rather than a hard one. It was caught by running the bake-off and
  noticing that all four methods converged to the same wrong answer.

  The reason the first design search missed it: that search scanned the
  objective with zeta, pos0 and sigma FIXED at truth. With sigma free a wrong
  frequency can buy itself a larger sigma, so the fixed-nuisance scan and the
  profile disagree — and the profile is the one the optimiser sees.

A gradient-based local method started in one of the wrong basins converges into
it and reports success — a small gradient norm, no integration failures, a
clean-looking fit that is simply the wrong frequency. That is the failure this
fixture is for: not a crash, and not a plateau the waterfall gate would catch,
but a confident wrong answer that only shows up when something searches
globally.

The problem is supplied as a whole PEtab problem (`supplied/petab/`) rather
than as a lab note plus data. An optimiser fixture must not have the
construction and assembly agents in the loop: their choices would move the
objective between runs, and then a comparison of optimisers would be measuring
the agents. Entering at estimation makes S6 the only thing that varies.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PETAB = HERE / "supplied" / "petab"

# --- truth -----------------------------------------------------------------
# omega is the parameter the multimodality acts on: 1.9 rad/min is a period of
# about 3.3 min, sampled every 1.6 min over 80 min.
TRUE = {
    "omega": 1.9,
    "zeta": 0.02,
    "amp": 1.0,
    "sigma_obs_A": 0.05,
}
T_END = 80.0
N_TIMES = 50
SEED = 20260919


def simulate(w: float, zeta: float, amp: float, t: np.ndarray) -> np.ndarray:
    """Analytic under-damped solution — the generator does not need a solver,
    and keeping it closed-form means the data cannot inherit a tolerance."""
    wd = w * np.sqrt(1.0 - zeta**2)
    return (
        amp
        * np.exp(-zeta * w * t)
        * (np.cos(wd * t) + (zeta / np.sqrt(1.0 - zeta**2)) * np.sin(wd * t))
    )


# NAMES ARE NOT FREE HERE. AMICI's generated C++ reserves `x` (states), `w`
# (expressions), `p` (parameters), `k` (constants), `h` (events) and `x0`
# (initial states) as file and variable names, and a model symbol that collides
# with one of them fails at COMPILE time with an error about the generated code
# rather than about the model — the first draft of this fixture used `w` for
# the frequency and `x0` for the initial position and died on
# "conflicting declaration 'const amici::realtype* p'" in x0.cpp. Hence
# `omega`, `pos`, `vel`, `pos0`.
# STATES MUST STAY NON-NEGATIVE. The engine's s1 ladder runs
# `states stay non-negative` on every model, because its states are
# concentrations. A displacement/velocity pair fails it honestly — the first
# version of this fixture did, at -0.856 — so the oscillator is written as two
# SPECIES oscillating about POSITIVE baselines instead:
#
#     u = A - A_base,  v = B - B_base
#     u' = -omega * v
#     v' =  omega * u - 2 * zeta * omega * v      =>  u'' + 2*zeta*omega*u' + omega^2*u = 0
#
# so A carries exactly the damped oscillation the landscape was measured on.
# The baselines are FIXED, not estimated: a constant present in both the model
# and the data cancels in the residual, so the profile likelihood — and every
# number in testcase.yaml's baseline table — is unchanged by the shift.
A_BASE = 3.0
B_BASE = 2.0

ANTIMONY = """
model toy_oscillator
  # Two species in a linear negative-feedback loop, oscillating about positive
  # baselines. Rate rules rather than reactions: the loop is a control
  # relationship, and forcing it into reaction syntax would invent fluxes that
  # do not exist.
  species A, B;

  A = A_base + amp;
  B = B_base;

  A' = -omega * (B - B_base);
  B' =  omega * (A - A_base) - 2 * zeta * omega * (B - B_base);

  omega = 1.0;
  zeta = 0.1;
  amp = 1.0;
  A_base = 3.0;
  B_base = 2.0;
end
"""


def build_sbml() -> str:
    import antimony

    antimony.clearPreviousLoads()
    code = antimony.loadAntimonyString(ANTIMONY)
    if code < 0:
        raise SystemExit(f"antimony refused the model: {antimony.getLastError()}")
    return antimony.getSBMLString(antimony.getModuleNames()[-1])


def main() -> int:
    PETAB.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    t = np.linspace(0.0, T_END, N_TIMES)

    # One condition. The difficulty is the frequency, not the design: adding
    # conditions would only make the objective more expensive without making
    # it more multimodal.
    x = simulate(TRUE["omega"], TRUE["zeta"], TRUE["amp"], t)
    noisy = A_BASE + x + rng.normal(0.0, TRUE["sigma_obs_A"], size=x.shape)

    meas = pd.DataFrame(
        {
            "observableId": "obs_A",
            "simulationConditionId": "c0",
            "measurement": noisy,
            "time": t,
            "noiseParameters": "sigma_obs_A",
        }
    )
    meas.to_csv(PETAB / "measurements.tsv", sep="\t", index=False)

    pd.DataFrame({"conditionId": ["c0"]}).to_csv(
        PETAB / "conditions.tsv", sep="\t", index=False
    )

    pd.DataFrame(
        {
            "observableId": ["obs_A"],
            "observableFormula": ["A"],
            "observableTransformation": ["lin"],
            "noiseFormula": ["noiseParameter1_obs_A"],
            "noiseDistribution": ["normal"],
        }
    ).to_csv(PETAB / "observables.tsv", sep="\t", index=False)

    # Bounds on omega span [0.5, 6.0], the range the profile scan covered and
    # over which it found 5 local minima. A start drawn uniformly
    # therefore lands in the truth's basin rarely, which is the point: the
    # interesting regime is the one a real problem is always in, where starts
    # are expensive and you cannot afford enough of them to brute-force it.
    pd.DataFrame(
        {
            "parameterId": ["omega", "zeta", "amp", "sigma_obs_A"],
            "parameterScale": ["lin", "log10", "lin", "log10"],
            "lowerBound": [0.5, 0.005, 0.5, 0.001],
            "upperBound": [6.0, 0.5, 1.5, 1.0],
            "nominalValue": [
                TRUE["omega"],
                TRUE["zeta"],
                TRUE["amp"],
                TRUE["sigma_obs_A"],
            ],
            "estimate": [1, 1, 1, 1],
        }
    ).to_csv(PETAB / "parameters.tsv", sep="\t", index=False)

    (PETAB / "model.xml").write_text(build_sbml())

    (PETAB / "problem.yaml").write_text(
        "format_version: 1\n"
        "parameter_file: parameters.tsv\n"
        "problems:\n"
        "- condition_files:\n"
        "  - conditions.tsv\n"
        "  measurement_files:\n"
        "  - measurements.tsv\n"
        "  observable_files:\n"
        "  - observables.tsv\n"
        "  sbml_files:\n"
        "  - model.xml\n"
    )

    truth = HERE / "truth"
    truth.mkdir(exist_ok=True)
    (truth / "true_parameters.json").write_text(
        json.dumps({"true_parameters": TRUE, "seed": SEED, "t_end": T_END}, indent=2)
        + "\n"
    )
    print(f"wrote {len(meas)} rows to {PETAB}")
    print(f"truth: {TRUE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
