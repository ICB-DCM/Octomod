"""Generate the ctd_two_kinase case: two kinases writing one CTD lattice, observed
per repeat and as an intact-mass phosphate count.

The substrate is eight consensus heptarepeats, each one bit: a repeat is unmodified
or carries one phosphate. Two kinases write that bit by different rules:

  * P-TEFb (CDK9/cyclin T1) modifies one repeat per encounter, with a directional
    neighbour effect: a modified neighbour on the low-index side multiplies the
    rate by alpha_up_ptefb, one on the high-index side by alpha_down_ptefb, both
    by alpha_dual_ptefb. The rule and its values are ctd_positional's.
  * CDK7 (the TFIIH kinase module CDK7/cyclin H/MAT1) modifies every unmodified
    repeat at one rate k_cdk7, with no neighbour effect and no positional
    preference.

Where both are present, each still-unmodified repeat is modified at the sum of the
two rates. The kinases do not interfere, and P-TEFb's rule reads the bit, not which
kinase wrote it. Three conditions start from the unmodified substrate: each kinase
alone, and the two together at the same concentrations.

Two properties of this truth carry the case, and both are checked numerically on
every run of this script:

  * the combined condition follows from the two single-kinase conditions only for
    a model in which the rates add on a shared lattice;
  * reversing the chain swaps alpha_up_ptefb and alpha_down_ptefb and leaves every
    count trajectory unchanged in every condition (the CDK7 rule is its own mirror
    image), so P-TEFb's direction lives in the per-repeat readout alone.

Run: uv run python testcase/ctd_two_kinase/make_data.py
"""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
N_SITES = 8
# ctd_positional's seed: P-TEFb's rule is unchanged and the ptefb condition is drawn
# first, so that block of the file repeats ctd_positional's data draw for draw
SEED = 20260911

# ---------------------------------------------------------------- the truth
# Each rate constant is an effective second-order constant, per uM ATP per min, at
# its kinase's assay concentration. Both kinases are catalytic and constant, and in
# every condition each is either at that concentration or absent, so the enzyme is
# absorbed into the constant as in ctd_positional.
TRUE = dict(
    k_p_ptefb=1.2e-6,  # 1/(uM*min); P-TEFb alone moves the mean count
    #                    0.4 -> 1.8 -> 3.5 -> 5.8 -> 8.0 across the window
    alpha_up_ptefb=3.5,  # neighbour on the LOW-index side already modified
    alpha_down_ptefb=1.2,  # neighbour on the HIGH-index side already modified
    alpha_dual_ptefb=4.0,  # both neighbours modified
    k_cdk7=2.6e-7,  # 1/(uM*min); CDK7 alone reaches a mean of 4.0 of 8 at 960 min
)
CTD_TOT = 100.0  # uM substrate
ATP0 = 3000.0  # uM
TEMPERATURE_C = 30.0  # constant, so absorbed into the rate constants
# equal molar enzyme, so k_p_ptefb and k_cdk7 compare per kinase molecule
KINASE_UM = {"ptefb": 0.1, "cdk7": 0.1}
KINASE_FORM = {
    "ptefb": "P-TEFb, CDK9/cyclin T1",
    "cdk7": "CDK7/cyclin H/MAT1, the TFIIH kinase module",
}
PARAMETER_UNITS = {
    "k_p_ptefb": f"1/(uM*min), per uM ATP, at {KINASE_UM['ptefb']:g} uM P-TEFb",
    "alpha_up_ptefb": "dimensionless",
    "alpha_down_ptefb": "dimensionless",
    "alpha_dual_ptefb": "dimensionless",
    "k_cdk7": f"1/(uM*min), per uM ATP, at {KINASE_UM['cdk7']:g} uM CDK7",
}
# kinase uM per condition; the combined condition uses the single-kinase amounts
CONDITIONS = {
    "ptefb": {"ptefb": KINASE_UM["ptefb"], "cdk7": 0.0},
    "cdk7": {"ptefb": 0.0, "cdk7": KINASE_UM["cdk7"]},
    "both": {"ptefb": KINASE_UM["ptefb"], "cdk7": KINASE_UM["cdk7"]},
}
TIMES = [0.0, 15.0, 30.0, 60.0, 120.0, 240.0, 480.0, 960.0]
N_REPLICATES = 3
# observation: MS-style relative intensity with a per-time-point scaling factor,
# the same factor at a time point in every condition
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
# activity kept by one kinase in the combined condition, for the additivity check
INTERFERENCE_LEVELS = (0.8, 0.5)

STATES = list(itertools.product((0, 1), repeat=N_SITES))
IDX = {s: i for i, s in enumerate(STATES)}


def ptefb_rate(state, pos, p):
    """P-TEFb's rate of modifying `pos` (0-based) in `state`. Boundaries unoccupied."""
    left = state[pos - 1] if pos > 0 else 0
    right = state[pos + 1] if pos < N_SITES - 1 else 0
    if left and right:
        return p["k_p_ptefb"] * p["alpha_dual_ptefb"]
    if left:
        return p["k_p_ptefb"] * p["alpha_up_ptefb"]
    if right:
        return p["k_p_ptefb"] * p["alpha_down_ptefb"]
    return p["k_p_ptefb"]


def build_transitions(p):
    """Arrays (from, to, P-TEFb rate, CDK7 rate) over every single-phosphorylation step."""
    fr, to, kp, kc = [], [], [], []
    for s in STATES:
        for pos in range(N_SITES):
            if s[pos] == 0:
                t = list(s)
                t[pos] = 1
                fr.append(IDX[s])
                to.append(IDX[tuple(t)])
                kp.append(ptefb_rate(s, pos, p))
                kc.append(p["k_cdk7"])
    return np.array(fr), np.array(to), np.array(kp), np.array(kc)


def levels(condition):
    """Each kinase's amount relative to its assay concentration (1.0 or 0.0 here)."""
    return {k: CONDITIONS[condition][k] / KINASE_UM[k] for k in KINASE_UM}


def simulate(p, level, times):
    """Configuration amounts (256, T) and ATP (T), from the unmodified substrate."""
    fr, to, kp, kc = build_transitions(p)
    # the rates add and neither kinase changes the other's
    kk = level["ptefb"] * kp + level["cdk7"] * kc

    def rhs(_t, y):
        c, atp = y[:-1], y[-1]
        flux = kk * c[fr] * atp
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


def mean_count(cnt):
    """(9, T) -> (T,) mean phosphates per molecule."""
    return (cnt * np.arange(N_SITES + 1)[:, None]).sum(axis=0) / CTD_TOT


def mirror(p):
    """The same mechanism on the reversed chain: the two directional factors swap."""
    q = dict(p)
    q["alpha_up_ptefb"], q["alpha_down_ptefb"] = (
        p["alpha_down_ptefb"],
        p["alpha_up_ptefb"],
    )
    return q


def by_time(values, digits=4):
    """A trajectory keyed by sample time, rounded for the truth files."""
    return {
        f"{t:g}": round(float(v), digits) for t, v in zip(TIMES, values, strict=True)
    }


def sig(x, digits=4):
    """`x` to `digits` significant figures, so tiny differences stay readable."""
    return float(f"{float(x):.{digits}g}")


def observable_shift(cnt_a, occ_a, cnt_b, occ_b):
    """How far two predictions differ, in each readout's noise units.

    The count readout is S_T0 * xi * amount with noise SIGMA_COUNT * xi, so xi
    cancels and the shift in noise units is S_T0 * |amount difference| / SIGMA_COUNT.
    `delta_chi2` sums the squared shifts over every time point, both readouts and
    the replicates: the expected rise in the residual sum of squares, in noise
    units, when data made by one prediction are compared with the other.
    """
    z_cnt = S_T0 * (cnt_a - cnt_b) / SIGMA_COUNT
    z_occ = (occ_a - occ_b) / SIGMA_SITE
    return {
        "count_max_sigma": sig(np.abs(z_cnt).max()),
        "occupancy_max_abs": sig(np.abs(occ_a - occ_b).max()),
        "occupancy_max_sigma": sig(np.abs(z_occ).max()),
        "delta_chi2_count": sig(N_REPLICATES * (z_cnt**2).sum()),
        "delta_chi2_occupancy": sig(N_REPLICATES * (z_occ**2).sum()),
    }


def reversal_check(sims):
    """Re-simulate each condition with the directional factors swapped."""
    out = {}
    for c in CONDITIONS:
        cnt, occ = sims[c]["counts"], sims[c]["occupancy"]
        conc_m, _ = simulate(mirror(TRUE), levels(c), TIMES)
        cnt_m, occ_m = counts(conc_m), occupancy(conc_m)
        per_site = np.abs(occ - occ_m).max(axis=1)
        per_time = np.abs(occ - occ_m).max(axis=0)
        peak_t = TIMES[int(per_time.argmax())] if per_time.max() > 0 else None
        out[c] = {
            # relative to the substrate total, the scale of the count distribution
            "count_max_relative_difference": sig(np.abs(cnt - cnt_m).max() / CTD_TOT),
            **observable_shift(cnt, occ, cnt_m, occ_m),
            "occupancy_max_abs_per_site": {
                f"site{i + 1}": round(float(v), 4) for i, v in enumerate(per_site)
            },
            "occupancy_difference_peaks_at_min": peak_t,
            # the mirrored mechanism's profile is the true profile read backwards
            "mirror_minus_reversed_truth_max_abs": sig(np.abs(occ_m - occ[::-1]).max()),
        }
    return out


def simulate_labelled(p, level, times, ptefb_reads_cdk7_marks):
    """The lattice with every mark labelled by its writer (0 none, 1 P-TEFb, 2 CDK7).

    With `ptefb_reads_cdk7_marks` True this is the truth written out by writer, and
    summed over labels it must equal the one-bit lattice. With False, P-TEFb's
    neighbour rule counts only its own marks: the alternative the combined
    condition has to tell apart from the truth. Returns counts (9, T), occupancy
    (8, T) and phosphates per molecule written by each kinase (2, T).
    """
    states = list(itertools.product((0, 1, 2), repeat=N_SITES))
    index = {s: i for i, s in enumerate(states)}
    seen = (1, 2) if ptefb_reads_cdk7_marks else (1,)
    rows, cols, vals = [], [], []
    for s in states:
        for pos in range(N_SITES):
            if s[pos]:
                continue
            bits = tuple(int(x in seen) for x in s)
            for mark, k in (
                (1, level["ptefb"] * ptefb_rate(bits, pos, p)),
                (2, level["cdk7"] * p["k_cdk7"]),
            ):
                t = list(s)
                t[pos] = mark
                rows.append(index[tuple(t)])
                cols.append(index[s])
                vals.append(k)
    gain = sparse.csr_matrix((vals, (rows, cols)), shape=(len(states), len(states)))
    loss = np.asarray(gain.sum(axis=0)).ravel()

    def rhs(_t, y):
        c, atp = y[:-1], y[-1]
        return np.concatenate([atp * (gain @ c - loss * c), [-atp * (loss @ c)]])

    y0 = np.zeros(len(states) + 1)
    y0[index[tuple([0] * N_SITES)]] = CTD_TOT
    y0[-1] = ATP0
    sol = solve_ivp(
        rhs, (0.0, max(times)), y0, t_eval=times, method="LSODA", rtol=1e-9, atol=1e-12
    )
    assert sol.success, sol.message
    conc = sol.y[:-1, :]
    cnt = np.zeros((N_SITES + 1, conc.shape[1]))
    occ = np.zeros((N_SITES, conc.shape[1]))
    writer = np.zeros((2, conc.shape[1]))
    for s, i in index.items():
        cnt[sum(x > 0 for x in s), :] += conc[i, :]
        for pos in range(N_SITES):
            if s[pos]:
                occ[pos, :] += conc[i, :]
                writer[s[pos] - 1, :] += conc[i, :]
    return cnt, occ / conc.sum(axis=0), writer / CTD_TOT


def additivity_check(sims):
    """What the combined condition shows beyond the two single-kinase conditions."""
    m_p = mean_count(sims["ptefb"]["counts"])
    m_c = mean_count(sims["cdk7"]["counts"])
    m_b = mean_count(sims["both"]["counts"])
    cnt_b, occ_b = sims["both"]["counts"], sims["both"]["occupancy"]
    cnt_t, occ_t, writer = simulate_labelled(TRUE, levels("both"), TIMES, True)
    # the writer-labelled truth is the one-bit truth read at finer grain
    labelled_gap = max(
        np.abs(cnt_t - cnt_b).max() / CTD_TOT, np.abs(occ_t - occ_b).max()
    )
    assert labelled_gap < 1e-9, labelled_gap
    cnt_o, occ_o, _ = simulate_labelled(TRUE, levels("both"), TIMES, False)
    out = {
        "mean_count_both": by_time(m_b, 3),
        "mean_count_ptefb_plus_cdk7": by_time(m_p + m_c, 3),
        "both_minus_sum": by_time(m_b - (m_p + m_c), 3),
        "phosphates_written_in_both": {
            "ptefb": by_time(writer[0], 3),
            "cdk7": by_time(writer[1], 3),
        },
        "writer_labelled_minus_one_bit_max_abs": sig(labelled_gap),
        "ptefb_reads_only_its_own_marks": {
            "mean_count_both": by_time(mean_count(cnt_o), 3),
            **observable_shift(cnt_b, occ_b, cnt_o, occ_o),
        },
        "interference": {},
    }
    for kinase in KINASE_UM:
        for kept in INTERFERENCE_LEVELS:
            level = dict(levels("both"))
            level[kinase] = kept
            conc_i, _ = simulate(TRUE, level, TIMES)
            out["interference"][f"{kinase}_at_{kept:g}"] = observable_shift(
                cnt_b, occ_b, counts(conc_i), occupancy(conc_i)
            )
    return out


def main() -> int:
    rng = np.random.default_rng(SEED)
    sims = {}
    for c in CONDITIONS:
        conc, atp = simulate(TRUE, levels(c), TIMES)
        sims[c] = {"counts": counts(conc), "occupancy": occupancy(conc), "atp": atp}

    # CDK7 alone is calibrated to half the lattice at the last sample
    cdk7_final = float(mean_count(sims["cdk7"]["counts"])[-1])
    assert abs(cdk7_final - N_SITES / 2) < 0.05, cdk7_final

    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "truth").mkdir(exist_ok=True)
    noisy_occ = {c: [] for c in CONDITIONS}
    with open(HERE / "data" / "ctd_two_kinase.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["condition", "time_min", "replicate"]
            + [f"site{i + 1}_occ" for i in range(N_SITES)]
            + [f"phos{i}_rel" for i in range(N_SITES + 1)]
        )
        for c in CONDITIONS:
            cnt, occ = sims[c]["counts"], sims[c]["occupancy"]
            for k, t in enumerate(TIMES):
                for r in range(1, N_REPLICATES + 1):
                    srow = [
                        occ[i, k] + rng.normal(0, SIGMA_SITE) for i in range(N_SITES)
                    ]
                    crow = [
                        S_T0 * XI[t] * cnt[i, k] + rng.normal(0, SIGMA_COUNT * XI[t])
                        for i in range(N_SITES + 1)
                    ]
                    noisy_occ[c].extend(srow)
                    w.writerow([c, f"{t:g}", r] + [f"{v:.9g}" for v in srow + crow])

    reversal = reversal_check(sims)
    additivity = additivity_check(sims)
    means = {c: by_time(mean_count(sims[c]["counts"]), 3) for c in CONDITIONS}
    atp_left = {c: by_time(sims[c]["atp"], 1) for c in CONDITIONS}
    fully = {c: by_time(sims[c]["counts"][N_SITES] / CTD_TOT, 3) for c in CONDITIONS}
    occ_120 = {
        c: [round(float(v), 3) for v in sims[c]["occupancy"][:, TIMES.index(120.0)]]
        for c in CONDITIONS
    }
    outside = {
        c: {
            "n": len(v),
            "below_0": int(sum(x < 0 for x in v)),
            "above_1": int(sum(x > 1 for x in v)),
        }
        for c, v in noisy_occ.items()
    }

    settings = {
        "true_parameters": TRUE,
        "seed": SEED,
        "times_min": TIMES,
        "n_replicates": N_REPLICATES,
        "ctd_uM": CTD_TOT,
        "atp_uM": ATP0,
        "temperature_C": TEMPERATURE_C,
        "kinase_uM": KINASE_UM,
        "kinase_form": KINASE_FORM,
        "conditions_kinase_uM": CONDITIONS,
        "condition_order_in_file": list(CONDITIONS),
        "s_t0": S_T0,
        "xi": XI,
        "xi_note": "the same xi at a time point in every condition",
        "sigma_count": SIGMA_COUNT,
        "sigma_site": SIGMA_SITE,
        "integrator": "scipy.integrate.solve_ivp LSODA rtol 1e-9 atol 1e-12",
    }
    with open(HERE / "truth" / "generator_settings.json", "w") as fh:
        json.dump(settings, fh, indent=1)

    truth = {
        "system": (
            "RNA polymerase II CTD (8 consensus heptarepeats) phosphorylated in vitro "
            "by P-TEFb and by CDK7, each alone and the two together, positionally "
            "resolved"
        ),
        "truth_kind": "synthetic generating model",
        "generator": {
            "script": "make_data.py",
            "seed": SEED,
            "integrator": settings["integrator"],
            "n_states": len(STATES),
            "n_sites": N_SITES,
        },
        "true_mechanism_id": "ptefb_directional_neighbour_plus_cdk7_uniform_additive",
        "true_mechanism_note": (
            "One bit per repeat, one phosphate per catalytic event, one ATP per "
            "event; both kinases catalytic and constant. P-TEFb modifies an "
            "unmodified repeat at k_p_ptefb, multiplied by alpha_up_ptefb = "
            f"{TRUE['alpha_up_ptefb']:g} when the low-index neighbour is modified, "
            f"alpha_down_ptefb = {TRUE['alpha_down_ptefb']:g} when the high-index "
            f"neighbour is, alpha_dual_ptefb = {TRUE['alpha_dual_ptefb']:g} when "
            "both are; boundary repeats treat the missing neighbour as unmodified. CDK7 "
            "modifies every unmodified repeat at k_cdk7 whatever its neighbours or "
            "position. With both present the two rates add on the same lattice, "
            "with no interference; P-TEFb's rule reads the bit, not which kinase "
            "wrote it, so a CDK7-written repeat raises P-TEFb's rate at its "
            "neighbours and is itself closed to P-TEFb."
        ),
        "rate_law": (
            "flux(s -> s + e_l) = [e_ptefb * k_p_ptefb * f(s, l) + e_cdk7 * k_cdk7] "
            "* [s] * [ATP], f = 1, alpha_up_ptefb, alpha_down_ptefb or "
            "alpha_dual_ptefb by the modified neighbours of repeat l; "
            "e_kinase = 1 when present at its assay concentration, 0 when absent"
        ),
        "true_parameters": TRUE,
        "parameter_units": PARAMETER_UNITS,
        "assay": {
            "substrate": "8 consensus heptarepeats, one bit per repeat",
            "substrate_uM": CTD_TOT,
            "atp_uM": ATP0,
            "temperature_C": TEMPERATURE_C,
            "kinase_uM": KINASE_UM,
            "kinase_form": KINASE_FORM,
        },
        "conditions_kinase_uM": CONDITIONS,
        "observation": {
            "siteN_occ": "fraction of molecules with repeat N modified; additive noise, no scaling",
            "phosK_rel": (
                "s_t0 * xi_t * (summed amount with K phosphates); s_t0 = 0.01; noise "
                "proportional to xi_t; xi_t the same in every condition"
            ),
            "xi": {f"{t:g}": v for t, v in XI.items()},
        },
        "noise_sd": {
            "site_occupancy": SIGMA_SITE,
            "count_relative": SIGMA_COUNT,
            "note": "count noise is 0.012 * xi_t; three replicates per condition and time point",
        },
        "initial_conditions": {
            "all_conditions": "unmodified substrate",
            "CTD_unphosphorylated_uM": CTD_TOT,
            "ATP_uM": ATP0,
        },
        "times_min": TIMES,
        "replicates": list(range(1, N_REPLICATES + 1)),
        "mean_phosphates_per_molecule": means,
        "atp_remaining_uM": atp_left,
        "fully_modified_fraction": fully,
        "site_occupancy_at_120_min": occ_120,
        "reversal_check": {
            "meaning": (
                "swapping alpha_up_ptefb and alpha_down_ptefb (reversing the chain) "
                "leaves every count trajectory unchanged, in every condition, while "
                "the per-site occupancies move; the cdk7 condition has no directional "
                "factor, so its swap changes nothing"
            ),
            "sigma_site": SIGMA_SITE,
            "sigma_count": SIGMA_COUNT,
            "by_condition": reversal,
        },
        "additivity_check": {
            "meaning": (
                "the rates add per configuration, the observables do not: the "
                "combined mean count falls below the sum of the single-kinase ones "
                "because the kinases share the unmodified repeats, while every "
                "CDK7-written repeat raises P-TEFb's rate at its neighbours. A model "
                "built from the single-kinase conditions predicts the combined one "
                "only if the two rates add on one lattice whose marks P-TEFb reads "
                "whoever wrote them. 'ptefb_reads_only_its_own_marks' is the "
                "combined condition under the alternative in which P-TEFb's "
                "neighbour rule ignores CDK7-written repeats; 'interference' is the "
                "combined condition when one kinase keeps only that fraction of its "
                "rate there; both are compared with the truth in noise units"
            ),
            **additivity,
        },
        "noisy_occupancy_outside_0_1": outside,
    }
    with open(HERE / "truth" / "true_parameters.json", "w") as fh:
        json.dump(truth, fh, indent=2)

    print("mean phosphorylations per CTD:")
    for c in CONDITIONS:
        print(f"  {c:6s}", by_time(mean_count(sims[c]["counts"]), 2))
    print("ATP remaining (uM):")
    for c in CONDITIONS:
        print(f"  {c:6s}", atp_left[c])
    print("fully modified fraction:")
    for c in CONDITIONS:
        print(f"  {c:6s}", fully[c])
    print("site occupancy at 120 min:")
    for c in CONDITIONS:
        print(f"  {c:6s}", occ_120[c])
    n_all = sum(o["n"] for o in outside.values())
    n_out = sum(o["below_0"] + o["above_1"] for o in outside.values())
    print(f"noisy occupancy outside [0, 1]: {n_out} of {n_all} ({n_out / n_all:.1%})")
    for c, o in outside.items():
        print(f"  {c:6s} below 0: {o['below_0']}, above 1: {o['above_1']}, of {o['n']}")
    print("reversal check (alpha_up_ptefb <-> alpha_down_ptefb):")
    for c, r in reversal.items():
        print(
            f"  {c:6s} counts: {r['count_max_relative_difference']:.3g} relative "
            f"({r['count_max_sigma']:.3g} sigma); occupancies: "
            f"{r['occupancy_max_abs']:.4g} abs ({r['occupancy_max_sigma']:.3g} sigma), "
            f"peak at {r['occupancy_difference_peaks_at_min'] or '-'} min; delta_chi2 "
            f"counts {r['delta_chi2_count']:.3g}, occupancy "
            f"{r['delta_chi2_occupancy']:.4g}; mirror vs reversed truth "
            f"{r['mirror_minus_reversed_truth_max_abs']:.2g}"
        )
        print(f"         per site: {r['occupancy_max_abs_per_site']}")
    print("additivity check:")
    print("  both          ", additivity["mean_count_both"])
    print("  ptefb + cdk7  ", additivity["mean_count_ptefb_plus_cdk7"])
    print("  both - sum    ", additivity["both_minus_sum"])
    for k, v in additivity["phosphates_written_in_both"].items():
        print(f"  written by {k:6s}", v)
    print(
        "  writer-labelled lattice minus one-bit lattice:",
        additivity["writer_labelled_minus_one_bit_max_abs"],
    )
    print(
        "  P-TEFb reads only its own marks:",
        additivity["ptefb_reads_only_its_own_marks"],
    )
    for k, v in additivity["interference"].items():
        print(f"  {k:12s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
