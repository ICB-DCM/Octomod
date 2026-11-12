"""Structurally flat directions are counted, only those, as an indicator beside AIC.

A direction counts when it is flat at every random point near the nominal at
once, and is checked again around the fit. Token-free and AMICI-free: the
problems here are analytic, so the linear algebra is exact.

  1. a product model (y = w_r·R_p·e^{-kt}) has ONE flat direction, even with 1e-8 noise;
  2. the competitive variant (the same, divided by 1 + Σ w_r·S_r) has none;
  3. a SLOPPY direction, flat along different vectors at the two points, is not counted;
  4. a problem without residual sensitivities is reported as not measured;
  5. a tiny-but-nonzero single parameter is listed as weak, an exact zero counted;
  6. a record written under an earlier rule is measured again;
  7. the criterion is standard AIC, charging every estimated parameter;
  8. every probe point lies within `spread` of its centre and inside the bounds,
     and the spec's probe centres on the PEtab nominal values, by name;
  9. at the fit: a direction flat everywhere is confirmed, reusing the
     information screen's Jacobian; one flat only near the nominal is not, and
     one flat only at the fit is reported as missed by the pre-fit probe;
 10. S7 writes the re-check, ledgers it once, and the card and report say it;
 11. the information screen at the fit reads the same Jacobian, sigma rows
     included, whether or not the probe ran earlier in the process.

    uv run python tests/structural_nulls_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.workflow_modules.evaluation import structural_nulls as SN  # noqa: E402
from tests._record import temp_record, work  # noqa: E402

LN10 = np.log(10.0)
T = np.array([1.0, 5.0, 15.0, 30.0, 60.0])
S_FREE = (3.0, 1.5)  # fixed free-STAT amounts for the competitive variant


class ToyProblem:
    """Parameters (log10 scale): w1, w2, R1, R2, R3, k. Outputs y[p, r, t]."""

    x_names = ["w1", "w2", "R1", "R2", "R3", "k"]
    x_free_indices = list(range(6))
    lb = np.full(6, -2.0)
    ub = np.full(6, 1.0)

    def __init__(self, competitive=False, noise=0.0):
        self.competitive, self.noise = competitive, noise
        self._rng = np.random.default_rng(3)
        self.objective = self._objective

    def _objective(self, x, sensi_orders=(0,), mode=None, return_dict=False):
        th = 10.0 ** np.asarray(x, dtype=float)
        w, R, k = th[0:2], th[2:5], th[5]
        rows, jac = [], []
        Q = 1.0 + (w[0] * S_FREE[0] + w[1] * S_FREE[1] if self.competitive else 0.0)
        dlogQ_dlogw = (
            [w[0] * S_FREE[0] / Q, w[1] * S_FREE[1] / Q]
            if self.competitive
            else [0.0, 0.0]
        )
        for p in range(3):
            for r in range(2):
                for t in T:
                    y = w[r] * R[p] * np.exp(-k * t) / Q
                    g = np.zeros(6)  # d y / d log10(theta)
                    g[r] += LN10 * y
                    g[0] -= LN10 * y * dlogQ_dlogw[0]
                    g[1] -= LN10 * y * dlogQ_dlogw[1]
                    g[2 + p] += LN10 * y
                    g[5] += LN10 * y * (-k * t)
                    rows.append(y)
                    jac.append(g)
        sres = np.array(jac)
        if self.noise:
            sres = sres * (1 + self.noise * self._rng.standard_normal(sres.shape))
        return {"res": np.array(rows), "sres": sres}


class SequenceProblem:
    """Hands back fixed Jacobians in order, whatever x is asked about."""

    x_names = ["a", "b", "c"]
    x_free_indices = [0, 1, 2]
    lb = np.zeros(3)
    ub = np.ones(3)

    def __init__(self, jacobians):
        self._js = list(jacobians)
        self.objective = self._objective

    def _objective(self, x, sensi_orders=(0,), mode=None, return_dict=False):
        J = self._js.pop(0)
        return {"res": np.zeros(J.shape[0]), "sres": J}


def test_the_product_model_has_one_flat_direction():
    for noise in (0.0, 1e-8):
        rec = SN.measure(ToyProblem(noise=noise), seed=1)
        assert rec["available"], rec
        assert rec["n_flat"] == 1 and rec["k_effective"] == 5, rec
        comp = rec["directions"][0]["composition"]
        signs = {k: np.sign(v) for k, v in comp.items()}
        assert set(comp) == {"w1", "w2", "R1", "R2", "R3"}, comp
        assert (
            signs["w1"] == signs["w2"] and signs["R1"] == signs["R2"] == signs["R3"]
        ), comp
        assert signs["w1"] != signs["R1"], comp
    print(
        f"  product       1 flat direction ({rec['directions'][0]['reads_as'][:60]}…), k_eff 5 of 6"
    )


def test_the_competitive_variant_has_none():
    rec = SN.measure(ToyProblem(competitive=True, noise=1e-8), seed=1)
    assert rec["available"] and rec["n_flat"] == 0 and rec["k_effective"] == 6, rec
    print(
        f"  competitive   none; smallest singular value "
        f"{rec['smallest_not_counted_relative']:.1e} of the largest"
    )


def test_a_sloppy_direction_is_not_structure():
    rng = np.random.default_rng(0)
    base = rng.standard_normal((40, 3))

    def with_small(direction):
        # shrink the Jacobian along one direction to 1e-9 of the rest
        u, s, vt = np.linalg.svd(base, full_matrices=False)
        d = np.asarray(direction, float) / np.linalg.norm(direction)
        P = np.eye(3) - np.outer(d, d)
        return base @ (P + 1e-9 * np.outer(d, d))

    # flat along a at the first point, along b at the second: no common direction
    rec = SN.measure(SequenceProblem([with_small([1, 0, 0]), with_small([0, 1, 0])]))
    assert rec["available"] and rec["n_flat"] == 0, rec
    # the same direction at both points IS counted
    rec2 = SN.measure(SequenceProblem([with_small([1, 1, 0]), with_small([1, 1, 0])]))
    assert rec2["n_flat"] == 1, rec2
    print("  sloppy        flat at one point along a different vector: not counted")


def test_no_sensitivities_is_not_measured_and_charges_nothing():
    class NoSres(ToyProblem):
        def _objective(self, x, sensi_orders=(0,), mode=None, return_dict=False):
            return {"res": np.zeros(3)}

    rec = SN.measure(NoSres())
    assert not rec["available"] and SN.n_flat(rec) == 0, rec
    assert "not measured" in SN.card_lines(rec)[0], SN.card_lines(rec)
    print(f"  unavailable   {SN.card_lines(rec)[0][:80]}…")


def test_a_weak_single_parameter_is_not_a_symmetry():
    rng = np.random.default_rng(1)
    J1, J2 = rng.standard_normal((40, 3)), rng.standard_normal((40, 3))
    J1[:, 2] *= 1e-7
    J2[:, 2] *= 1e-7
    rec = SN.measure(SequenceProblem([J1.copy(), J2.copy()]))
    assert rec["rule"] == SN.RULE_VERSION and rec["n_flat"] == 0, rec
    assert len(rec["weak_single_parameters"]) == 1, rec
    assert "weak single parameter" in " ".join(SN.card_lines(rec)), SN.card_lines(rec)
    J1[:, 2] = 0.0
    J2[:, 2] = 0.0
    rec0 = SN.measure(SequenceProblem([J1, J2]))
    assert rec0["n_flat"] == 1 and not rec0["weak_single_parameters"], rec0
    print(
        "  weak          a tiny-but-nonzero single parameter is listed, not counted; an exact zero is counted"
    )


def test_a_rule_1_record_is_measured_again():
    from octomod.workflow_modules.estimation import estimation_settings

    with temp_record() as root:
        wk = work(root, 0)

        class Ctx:
            work = wk
            spec = None

        SN.node(wk).put({"available": True, "n_flat": 1, "n_estimated": 5})
        real = estimation_settings.build
        estimation_settings.build = lambda ctx: (_ for _ in ()).throw(
            RuntimeError("no problem here")
        )
        try:
            rec = SN.for_candidate(Ctx())
        finally:
            estimation_settings.build = real
    assert (
        not rec["available"] and SN.n_flat(rec) == 0
    ), "a rule-1 record was trusted instead of measured again"
    print("  versioned     a record from an earlier rule is re-measured, never reused")


def test_the_criterion_is_standard_aic():
    """AIC charges every estimated parameter; flat directions are only an indicator."""
    s7 = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    sel = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "selection.py"
    ).read_text()
    import math

    from octomod.workflow_modules.evaluation.selection import information_criteria

    ic = information_criteria(10.0, 3, 100)
    assert ic == {"aic": 26.0, "bic": 3 * math.log(100) + 20.0}, ic
    assert (
        "_selection.information_criteria(nllh, n_est," in s7
    ), "AIC must charge every estimated parameter"
    assert (
        "n_est - n_flat" not in s7 and "aic_nominal" not in s7
    ), "a corrected count is back in the criterion"
    assert (
        '"n_estimated": r["n_est"]' in s7
    ), "the selection must be handed the estimated count"
    assert (
        "local_nominal" not in s7
    ), "the cross-check checks the one selection there is"
    i = s7.index("dec = attribution.decompose(")
    assert (
        'n_est[cid] = int(r["n_est"])' in s7[max(0, i - 3000) : i]
    ), "the card's parameter term must match AIC"
    assert (
        'information_criteria(row["nllh"], row["n_est"], row["n_data"])' in sel
        and "aic_nominal" not in sel
    )
    lines = SN.card_lines(
        {
            "available": True,
            "n_flat": 1,
            "n_estimated": 86,
            "directions": [{"reads_as": "log(a) + log(b)"}],
        }
    )
    assert "AIC still charges all 86" in lines[0] and "indicator" in lines[0], lines
    print(
        "  criterion     standard AIC: every estimated parameter charged; flat directions an indicator"
    )


class XDependentProblem:
    """Flat along D where x[0] < 0.5 and along E elsewhere: flatness that moves.

    Every row is scaled by an x-dependent factor, so no two points hand back
    the same matrix while the null space stays exactly where it is put.
    """

    x_names = ["a", "b", "c"]
    x_free_indices = [0, 1, 2]
    lb = np.zeros(3)
    ub = np.ones(3)
    D = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
    E = np.array([0.0, 1.0, 1.0]) / np.sqrt(2.0)

    def __init__(self):
        self.B = np.random.default_rng(5).standard_normal((40, 3))
        self.objective = self._objective

    def jacobian(self, x):
        v = self.D if x[0] < 0.5 else self.E
        rows = 1.0 + x[1] * np.linspace(0.0, 1.0, 40)
        return rows[:, None] * (self.B @ (np.eye(3) - np.outer(v, v)))

    def _objective(self, x, sensi_orders=(0,), mode=None, return_dict=False):
        return {"res": np.zeros(40), "sres": self.jacobian(np.asarray(x, float))}


class _SigmaModel:
    """The AMICI model setting `identifiability.SigmaResiduals` reads and restores."""

    def __init__(self):
        self.on = False

    def get_add_sigma_residuals(self):
        return self.on

    def set_add_sigma_residuals(self, value):
        self.on = bool(value)


class _SigmaGuardedObjective:
    """pyPESTO's residual rule on an estimated sigma (`AmiciCalculator`):
    residual mode with sensitivities refuses while sigma residuals are off,
    until one such call has passed on this objective; with them on, the
    Jacobian carries one sigma row per datum. y = A·e^{-kt}, log10 scale."""

    T = np.linspace(1.0, 20.0, 8)

    def __init__(self):
        self.amici_model = _SigmaModel()
        self._known_least_squares_safe = False
        self.data = 2.0 * np.exp(-0.1 * self.T) * (1 + 0.05 * np.sin(self.T))

    def __call__(self, x, sensi_orders=(0,), mode=None, return_dict=False):
        import pypesto.C as C

        A, k, s = 10.0 ** np.asarray(x, dtype=float)
        y = A * np.exp(-k * self.T)
        r = (y - self.data) / s
        J = np.column_stack([LN10 * y / s, LN10 * y * (-k * self.T) / s, -LN10 * r])
        if mode == C.MODE_RES:
            if 1 in sensi_orders and not self._known_least_squares_safe:
                if not self.amici_model.on:
                    raise RuntimeError(
                        "Cannot use least squares solver with parameter dependent "
                        "sigma! Support can be enabled via "
                        "amici_model.setAddSigmaResiduals()."
                    )
                self._known_least_squares_safe = True
            if self.amici_model.on:
                rs = np.full(len(self.T), np.sqrt(2.0 * np.log(s) + 10.0))
                sigma_rows = np.zeros((len(self.T), 3))
                sigma_rows[:, 2] = LN10 / rs
                r, J = np.concatenate([r, rs]), np.vstack([J, sigma_rows])
            return {"res": r, "sres": J if 1 in sensi_orders else None}
        if 1 in sensi_orders:
            return J.T @ r + np.array([0.0, 0.0, len(self.T) * LN10])
        return float(0.5 * r @ r + len(self.T) * np.log(s))


class SigmaGuardedProblem:
    x_names = ["A", "k", "sigma"]
    x_free_indices = [0, 1, 2]
    lb = np.full(3, -2.0)
    ub = np.full(3, 2.0)

    def __init__(self):
        self.objective = _SigmaGuardedObjective()


def test_the_screen_reads_one_jacobian_whether_the_probe_ran_first_or_not():
    """The information screen at the fit computes the same Jacobian in a first
    pass, where the pre-fit probe ran earlier in the process, and on a resume,
    where it did not: pyPESTO stops refusing residual mode on an estimated
    sigma once one call with sigma residuals has passed, so the screen must
    not depend on whether one has."""
    from octomod.workflow_modules.evaluation import identifiability

    x = np.array([0.3, -1.0, -0.5])
    names = list(SigmaGuardedProblem.x_names)
    resumed = SigmaGuardedProblem()  # a fresh process: the probe never ran
    kept_resumed: dict = {}
    on_resume = identifiability.fim_at_mle(resumed, x, names, jacobian_out=kept_resumed)
    probed = SigmaGuardedProblem()  # the first pass: the probe ran before the fit
    SN.measure(probed, center=x, spread=0.2, seed=1)
    kept_first: dict = {}
    first = identifiability.fim_at_mle(probed, x, names, jacobian_out=kept_first)
    SN.measure(resumed, center=x, spread=0.2, seed=1)
    again = identifiability.fim_at_mle(resumed, x, names)
    for label, out in (("resume", on_resume), ("first pass", first), ("again", again)):
        assert out.get("available"), (label, out)
    assert on_resume["method"] == first["method"] == again["method"], (
        "the screen took a different path with and without the probe earlier in "
        f"the process: resume {on_resume['method']!r}, first pass "
        f"{first['method']!r}, after a probe {again['method']!r}"
    )
    assert "residual sensitivities" in first["method"], first["method"]
    assert (
        on_resume["eigenvalues_log10"]
        == first["eigenvalues_log10"]
        == again["eigenvalues_log10"]
    ), (on_resume["eigenvalues_log10"], first["eigenvalues_log10"])
    J0, J1 = kept_resumed.get("J"), kept_first.get("J")
    assert J0 is not None and J1 is not None and np.array_equal(J0, J1), (J0, J1)
    # the sigma rows the probe reads are in the screen's Jacobian as well
    assert J1.shape == (2 * len(_SigmaGuardedObjective.T), 3), J1.shape
    assert not probed.objective.amici_model.on and not resumed.objective.amici_model.on
    print(
        "  one Jacobian  the screen at the fit takes the same path, sigma rows "
        "included, whether or not the probe ran earlier in the process"
    )


class _Recorded:
    """`identifiability.residuals`, recording every point it is asked about."""

    def __init__(self):
        from octomod.workflow_modules.evaluation import identifiability

        self.module, self.real, self.xs = identifiability, None, []

    def __enter__(self):
        self.real = self.module.residuals

        def spy(problem, x, sensi):
            self.xs.append(np.asarray(x, dtype=float).copy())
            return self.real(problem, x, sensi)

        self.module.residuals = spy
        return self

    def __exit__(self, *exc):
        self.module.residuals = self.real
        return False


class _SpecStub:
    def __init__(self, **kv):
        self.kv = {"estimation.seed": 3, **kv}

    def get(self, key, default=None):
        return self.kv.get(key, default)

    def require(self, key):
        return self.kv[key]


def test_points_lie_near_the_centre_and_inside_the_bounds():
    prob = ToyProblem()
    center = np.array([0.9, -1.9, 0.0, -0.5, 0.5, -1.0])  # two near a bound
    spread = 0.5
    with _Recorded() as rec:
        out = SN.measure(prob, center=center, spread=spread, n_points=8, seed=4)
    xs = np.array(rec.xs)
    assert len(xs) >= 8, len(xs)
    assert np.all(np.abs(xs - center) <= spread + 1e-12), np.abs(xs - center).max()
    assert np.all(xs >= prob.lb) and np.all(xs <= prob.ub), (xs.min(), xs.max())
    clipped = int(np.sum(xs[:, 0] == prob.ub[0]) + np.sum(xs[:, 1] == prob.lb[1]))
    assert clipped > 0, "no draw ran past a bound, so clipping went untested"
    assert out["available"] and out["spread"] == spread, out
    assert "within ±0.5" in out["method"] and "clipped to the bounds" in out["method"]
    # and the old whole-box sampling would have strayed far from the centre
    assert np.abs(xs - center).max() <= spread
    print(
        f"  near          {len(xs)} points, every coordinate within ±{spread} of "
        f"the centre and inside the bounds ({clipped} clipped)"
    )


def test_the_spec_probe_centres_on_the_nominal():
    class Petab:
        # the PEtab order differs from the optimiser's, an inner parameter is
        # absent from it, and one nominal is missing
        x_ids = ["R3", "k", "inner_scale", "w2", "w1", "R1", "R2"]
        x_nominal_scaled = [0.3, -1.0, 2.0, 0.1, -0.2, float("nan"), -0.7]

    prob = ToyProblem()
    spec = _SpecStub(**{"gates.structural_nulls.spread": 0.25})
    with _Recorded() as rec:
        out = SN.measure_with_spec(prob, spec, Petab())
    want = {"w1": -0.2, "w2": 0.1, "R1": -0.5, "R2": -0.7, "R3": 0.3, "k": -1.0}
    assert out["center"] == want, out["center"]
    assert "box midpoint for 1" in out["center_basis"], out["center_basis"]
    c = np.array([want[n] for n in prob.x_names])
    assert np.all(np.abs(np.array(rec.xs) - c) <= 0.25 + 1e-12)
    assert "near the nominal parameter values" in SN.card_lines(out)[0], SN.card_lines(
        out
    )
    print(
        "  nominal       the spec's probe centres on the PEtab nominal values by "
        "name (the midpoint where one is missing), ±spread from the spec"
    )


def test_a_structural_direction_is_confirmed_at_the_mle():
    from octomod.workflow_modules.evaluation import identifiability

    prob = ToyProblem()
    pre = SN.measure(prob, center=np.full(6, -0.5), spread=0.5, seed=1)
    assert pre["n_flat"] == 1 and len(pre["directions"][0]["vector"]) == 6, pre
    x_mle = np.array([0.4, -1.5, 0.8, -1.2, 0.1, -1.8])
    _res, J = identifiability.residuals(prob, x_mle, True)
    with _Recorded() as rec:
        out = SN.recheck_at_mle(prob, x_mle, pre, jacobian=J, spread=0.3, seed=2)
    assert out["available"] and out["jacobian_reused"], out
    assert len(rec.xs) == 2, "the MLE's Jacobian was computed again, not reused"
    assert np.all(np.abs(np.array(rec.xs) - x_mle) <= 0.3 + 1e-12)
    d = out["directions"][0]
    assert d["confirmed_at_mle"] is True and out["n_confirmed"] == 1, out
    assert not out["flat_at_mle_only"], out["flat_at_mle_only"]
    line = SN.recheck_line(out)
    assert "1 of 1 flat at the fit too" in line, line
    # a probe that could not measure: every direction flat at the fit is named
    blind = SN.recheck_at_mle(
        prob, x_mle, {"available": False, "why": "stiff"}, jacobian=J, spread=0.3
    )
    said = SN.recheck_line(blind)
    assert not blind["pre_fit_available"] and len(blind["flat_at_mle_only"]) == 1
    assert said.startswith(
        "structural flat directions: not measured before the fit; 1 flat at it: "
    ), said
    print(f"  at the fit    a direction flat everywhere: {line}")


def test_a_direction_flat_only_near_the_nominal_is_not_confirmed():
    prob = XDependentProblem()
    pre = SN.measure(prob, center=np.array([0.2, 0.5, 0.5]), spread=0.2, seed=1)
    assert pre["n_flat"] == 1, pre
    assert abs(abs(np.dot(pre["directions"][0]["vector"], prob.D)) - 1) < 1e-9, pre
    x_mle = np.array([0.9, 0.5, 0.5])
    out = SN.recheck_at_mle(
        prob, x_mle, pre, jacobian=prob.jacobian(x_mle), spread=0.05, seed=2
    )
    d = out["directions"][0]
    assert d["confirmed_at_mle"] is False and out["n_not_confirmed"] == 1, out
    assert d["relative_singular_value_at_mle"] > 1e-3, d
    missed = out["flat_at_mle_only"]
    assert len(missed) == 1 and set(missed[0]["composition"]) == {"b", "c"}, missed
    line = SN.recheck_line(out)
    assert "not flat at the fit: " in line and "did not find" in line, line
    print(f"  moved         {line[:110]}…")


def test_s7_records_ledgers_and_shows_the_recheck():
    with temp_record() as root:
        _s7_records_ledgers_and_shows_the_recheck(root)


def _s7_records_ledgers_and_shows_the_recheck(root):
    import pandas as pd

    from octomod.reporting import round_report
    from octomod.workflow_modules.estimation import estimation_settings
    from octomod.workflow_modules.evaluation import engine as s7

    wd = work(root, 0)
    (wd / "petab" / "parameters").put_table(
        pd.DataFrame(
            {
                "parameterId": list(ToyProblem.x_names),
                "parameterScale": ["log10"] * len(ToyProblem.x_names),
            }
        )
    )
    prob = ToyProblem()
    pre = SN.measure(prob, center=np.full(6, -0.5), spread=0.5, seed=1)
    SN.node(wd).put(pre)
    x_mle = np.array([0.4, -1.5, 0.8, -1.2, 0.1, -1.8])

    class Ledger:
        rows: list = []

        def append(self, event, **kw):
            self.rows.append({"event": event, **kw})

    class Ctx:
        work = wd
        spec = _SpecStub()
        ledger = Ledger()
        round_idx = 0
        candidate = None

    summary = {
        "x_names": list(ToyProblem.x_names),
        "best_x_unscaled": {
            n: float(10**v) for n, v in zip(ToyProblem.x_names, x_mle, strict=True)
        },
    }
    real = estimation_settings.build
    estimation_settings.build = lambda ctx: (prob, None, 0.0)
    try:
        with _Recorded() as rec:
            ident = s7._fim_screen(Ctx(), summary)
        again = s7._fim_screen(Ctx(), summary)
    finally:
        estimation_settings.build = real
    check = ident.get("structural_recheck") or {}
    assert check.get("jacobian_reused") and check.get("n_confirmed") == 1, check
    # the screen reads its Jacobian itself; the re-check adds only the spec's two
    # points around the MLE, never a second Jacobian at it
    assert len(rec.xs) == 2, len(rec.xs)
    assert not any(np.allclose(x, x_mle) for x in rec.xs), rec.xs
    assert SN.node_at_mle(wd).exists()
    assert again["structural_recheck"] == check
    # a resumed process may find no screen Jacobian to reuse: the same outcome,
    # computed the other way, is not ledgered again
    resumed = s7._structural_recheck(Ctx(), prob, x_mle, None)
    assert not resumed["jacobian_reused"] and resumed["n_confirmed"] == 1, resumed
    notes = [r for r in Ctx.ledger.rows if "structural_recheck" in r]
    assert len(notes) == 1 and "flat at the fit too" in notes[0]["note"], notes
    lines = s7._structural_card_lines({"identifiability": ident})
    assert lines and "flat at the fit too" in lines[0], lines
    r = object.__new__(round_report.Round)
    r.core, r.report = {"identifiability": ident}, {}
    html = round_report._structural_flat(r)
    assert "before the fit and at it" in html and "flat at the fit too" in html, html
    moved = XDependentProblem()
    pre2 = SN.measure(moved, center=np.array([0.2, 0.5, 0.5]), spread=0.2, seed=1)
    x2 = np.array([0.9, 0.5, 0.5])
    r.core = {
        "identifiability": {
            "structural_recheck": SN.recheck_at_mle(
                moved, x2, pre2, jacobian=moved.jacobian(x2), spread=0.05
            )
        }
    }
    html2 = round_report._structural_flat(r)
    assert "not flat at the fit: relative singular value" in html2, html2
    assert "not found" in html2 and "flat at the fit (" in html2, html2
    print(
        "  S7            re-check written, ledgered once over two passes, on the "
        "card and in the report's table"
    )


if __name__ == "__main__":
    test_points_lie_near_the_centre_and_inside_the_bounds()
    test_the_spec_probe_centres_on_the_nominal()
    test_a_structural_direction_is_confirmed_at_the_mle()
    test_a_direction_flat_only_near_the_nominal_is_not_confirmed()
    test_s7_records_ledgers_and_shows_the_recheck()
    test_the_screen_reads_one_jacobian_whether_the_probe_ran_first_or_not()
    test_the_criterion_is_standard_aic()
    test_the_product_model_has_one_flat_direction()
    test_the_competitive_variant_has_none()
    test_a_sloppy_direction_is_not_structure()
    test_no_sensitivities_is_not_measured_and_charges_nothing()
    test_a_weak_single_parameter_is_not_a_symmetry()
    test_a_rule_1_record_is_measured_again()
    print("\nSTRUCTURAL NULLS UNIT OK")
