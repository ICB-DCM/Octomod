"""Generate the ctd_positional benchmark: a DIRECTIONAL CTD phosphorylation truth,
observed two ways.

The scientific point of this case (and the reason it exists) is a provable
statement about experimental design:

  * with COUNT data — mass spectrometry that resolves only HOW MANY of the eight
    heptarepeats are phosphorylated — the likelihood is EXACTLY invariant under
    reversing the chain, which swaps alpha_up and alpha_down. Direction is
    structurally non-identifiable, not merely hard to estimate.
  * with POSITIONAL data — a readout that resolves WHICH repeats are phosphorylated,
    reported as a per-site occupancy — that symmetry is broken and direction becomes
    identifiable.

The published analysis of the real Czudnochowski data could not settle directionality
for exactly this reason (Callenbach et al. 2026, doi 10.1371/journal.pcbi.1014531:
"the limited positional resolution of the data precludes a definitive conclusion").
This case asks whether the pipeline, given the new modality, recovers what the old
one could not.

Run: uv run python testcase/ctd_positional/make_data.py
"""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
N_SITES = 8
SEED = 20260911

# ---------------------------------------------------------------- the truth
TRUE = dict(
    k_p=1.2e-6,  # base rate, 1/(uM*min); calibrated so the mean count
    #                    moves 0.4 -> 1.8 -> 3.5 -> 5.8 -> 8.0 across the window
    #                    rather than saturating before the second sample
    alpha_up=3.5,  # neighbour on the LOW-index side already modified
    alpha_down=1.2,  # neighbour on the HIGH-index side already modified
    alpha_dual=4.0,  # both neighbours modified
)
CTD_TOT = 100.0  # uM substrate, as in the real assay
ATP0 = 3000.0  # uM
E_CONC = 1.0  # kinase, catalytic and constant; absorbed into k_p's units
TIMES = [0.0, 15.0, 30.0, 60.0, 120.0, 240.0, 480.0, 960.0]
N_REPLICATES = 3
# observation: MS-style relative intensity with a per-time-point scaling factor
S_T0 = 0.01
XI = {
    0.0: 1.0,
    15.0: 1.4,
    30.0: 2.1,
    60.0: 3.4,
    120.0: 3.9,
    240.0: 3.1,
    480.0: 1.6,
    960.0: 0.9,
}
SIGMA_COUNT = 0.012  # on the scaled count readout, proportional to xi
SIGMA_SITE = 0.010  # on the per-site occupancy readout (a fraction in [0,1])

STATES = list(itertools.product((0, 1), repeat=N_SITES))
IDX = {s: i for i, s in enumerate(STATES)}


def rate(state, pos, p):
    """Rate of phosphorylating `pos` (0-based) in `state`. Boundaries unoccupied."""
    left = state[pos - 1] if pos > 0 else 0
    right = state[pos + 1] if pos < N_SITES - 1 else 0
    if left and right:
        return p["k_p"] * p["alpha_dual"]
    if left:
        return p["k_p"] * p["alpha_up"]
    if right:
        return p["k_p"] * p["alpha_down"]
    return p["k_p"]


def build_transitions(p):
    """(from_index, to_index, rate_constant) for every single-phosphorylation step."""
    out = []
    for s in STATES:
        for pos in range(N_SITES):
            if s[pos] == 0:
                t = list(s)
                t[pos] = 1
                out.append((IDX[s], IDX[tuple(t)], rate(s, pos, p)))
    return out


def simulate(p, times):
    trans = build_transitions(p)
    fr = np.array([t[0] for t in trans])
    to = np.array([t[1] for t in trans])
    kk = np.array([t[2] for t in trans])

    def rhs(_t, y):
        c, atp = y[:-1], y[-1]
        flux = kk * c[fr] * atp * E_CONC
        dc = np.zeros_like(c)
        np.add.at(dc, fr, -flux)
        np.add.at(dc, to, flux)
        return np.concatenate([dc, [-flux.sum()]])

    y0 = np.zeros(len(STATES) + 1)
    y0[IDX[tuple([0] * N_SITES)]] = CTD_TOT
    y0[-1] = ATP0
    sol = solve_ivp(
        rhs, (0.0, max(times)), y0, t_eval=times, method="LSODA", rtol=1e-9, atol=1e-12
    )
    assert sol.success, sol.message
    return sol.y[:-1, :], sol.y[-1, :]


def counts(conc):
    """conc: (256, T) -> (9, T) summed by number of phosphorylated repeats."""
    out = np.zeros((N_SITES + 1, conc.shape[1]))
    for s, i in IDX.items():
        out[sum(s), :] += conc[i, :]
    return out


def occupancy(conc):
    """conc: (256, T) -> (8, T) fraction of molecules phosphorylated at each site."""
    tot = conc.sum(axis=0)
    out = np.zeros((N_SITES, conc.shape[1]))
    for s, i in IDX.items():
        for pos in range(N_SITES):
            if s[pos]:
                out[pos, :] += conc[i, :]
    return out / tot


def main() -> int:
    rng = np.random.default_rng(SEED)
    conc, atp = simulate(TRUE, TIMES)
    cnt, occ = counts(conc), occupancy(conc)

    (HERE / "data").mkdir(exist_ok=True)
    # ---- the NEW positional readout: per-site occupancy + the count distribution
    with open(HERE / "data" / "ctd_positional.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["time_min", "replicate"]
            + [f"site{i+1}_occ" for i in range(N_SITES)]
            + [f"phos{i}_rel" for i in range(N_SITES + 1)]
        )
        for k, t in enumerate(TIMES):
            for r in range(1, N_REPLICATES + 1):
                srow = [occ[i, k] + rng.normal(0, SIGMA_SITE) for i in range(N_SITES)]
                crow = [
                    S_T0 * XI[t] * cnt[i, k] + rng.normal(0, SIGMA_COUNT * XI[t])
                    for i in range(N_SITES + 1)
                ]
                w.writerow([f"{t:g}", r] + [f"{v:.9g}" for v in srow + crow])

    # ---- the NEGATIVE CONTROL: the same truth seen only as counts
    ctrl = HERE.parent / "ctd_countonly" / "data"
    ctrl.mkdir(parents=True, exist_ok=True)
    with open(ctrl / "ctd_countonly.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["time_min", "replicate"] + [f"phos{i}_rel" for i in range(N_SITES + 1)]
        )
        rng2 = np.random.default_rng(SEED + 1)
        for k, t in enumerate(TIMES):
            for r in range(1, N_REPLICATES + 1):
                crow = [
                    S_T0 * XI[t] * cnt[i, k] + rng2.normal(0, SIGMA_COUNT * XI[t])
                    for i in range(N_SITES + 1)
                ]
                w.writerow([f"{t:g}", r] + [f"{v:.9g}" for v in crow])

    mean_p = (cnt * np.arange(N_SITES + 1)[:, None]).sum(axis=0) / CTD_TOT
    print(
        "mean phosphorylations per CTD:",
        {f"{t:g}": round(float(m), 2) for t, m in zip(TIMES, mean_p, strict=False)},
    )
    print(
        "ATP remaining (uM):",
        {f"{t:g}": round(float(a), 1) for t, a in zip(TIMES, atp, strict=False)},
    )
    print(
        "site occupancy at 120 min:",
        [round(float(occ[i, TIMES.index(120.0)]), 3) for i in range(N_SITES)],
    )
    json.dump(
        {
            "true_parameters": TRUE,
            "seed": SEED,
            "times_min": TIMES,
            "n_replicates": N_REPLICATES,
            "ctd_uM": CTD_TOT,
            "atp_uM": ATP0,
            "s_t0": S_T0,
            "xi": XI,
            "sigma_count": SIGMA_COUNT,
            "sigma_site": SIGMA_SITE,
        },
        open(HERE / "truth" / "generator_settings.json", "w"),
        indent=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
