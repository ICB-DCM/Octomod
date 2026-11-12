"""S7 — evaluation and the honest report.

Deterministic report core first (fit metrics, ensemble uncertainty, held-out
prediction, profiles when the goal demands them); the agent interprets it;
a two-sided consistency gate stops both overclaiming (flat parameter not
listed as undetermined) and underclaiming (tight prediction not credited —
over-refusal is a documented pathology, not politeness).

Goal-conditioning (from the frozen intent):
  prediction        -> held-out T2' is the blocking gate; ensemble bands
  parameter_values  -> profiles behind their own human gate; CI finiteness
"""

from __future__ import annotations

import datetime
import json
import math
import re

import numpy as np
import pandas as pd

from octomod.gates import GateResult, gate, run_gate_set
from octomod.gates.petab_gates import PetabTables, noise_band
from octomod.orchestration import reuse as _reuse
from octomod.orchestration import rounds as _rounds
from octomod.orchestration import (
    timing,  # noqa: E402
)
from octomod.orchestration.interaction import gate_note, humangate
from octomod.orchestration.run_context import (
    ModuleFailure,
    RunContext,
    as_candidate,
    candidate_work,
)
from octomod.result import node as _tree
from octomod.workflow_modules.assembly import petab_io
from octomod.workflow_modules.cost_probe.engine import measured_start_s
from octomod.workflow_modules.estimation import estimation_settings
from octomod.workflow_modules.estimation.problem import resolve_optimizer
from octomod.workflow_modules.evaluation import attribution, fitted, profile_projection
from octomod.workflow_modules.model import model_space

# The record keys this module writes beside the mapped ones. Per unit of
# work (`ctx.work`): the profiles a fingerprint lets a later pass reuse
# (`reuse.PROFILES_KEY`), the profiling's timing (`profile_projection.TIMING_KEY`),
# the re-check of the probe's structural nulls at the MLE (`structural_nulls.node_at_mle`). Per round: the
# residual forms the report reads, and the two decisions.
VERDICT_DECISION = "decisions/evaluation_verdict"  # the verdict gate (`RK/decisions/evaluation_verdict`)
# The profiling gate's `ask_once` answer. A re-entered evaluation supersedes
# it (`round_status._MODULE_CACHE_PATTERNS`), so the gate is asked again.
PROFILE_DECISION = "decisions/evaluation_profile"
# A human's profile request for the round (`--skip-profiles`, `--profiles`,
# `profiles` at the verdict card) — a separate record, which a re-entered
# evaluation KEEPS: the human's request outlives the gate's answer.
PROFILE_REQUEST = "decisions/evaluation_profile_request"


def _write_report(rnd, report: dict) -> None:
    """The full report (`rnd / "evaluation"`, written whole)
    validated against EvaluationRecord on write."""
    from octomod.result.slots import EvaluationRecord
    from octomod.result.write import write_record

    write_record(rnd / "evaluation", EvaluationRecord, report)


def _work_tables(ctx: RunContext) -> PetabTables:
    """The fitted problem of `ctx.work` as tables (held-out table included, for
    which conditions pre-equilibrate), simulated with the SBML of `ctx.model` —
    the model S7 has always read beside the tables."""
    return PetabTables.from_work(ctx.work, ctx.model)


def _parameter_scales(ctx: RunContext) -> dict[str, str]:
    """parameterId → parameterScale of the fitted problem in `ctx.work`."""
    from octomod.workflow_modules.estimation.problem import parameter_scales

    return parameter_scales((ctx.work / "petab/parameters").table())


def _verdict_documents(ctx: RunContext) -> list:
    """The documents that carry the evidence behind a verdict — the
    rendered round report (a real file) and the round's decision record."""
    return [
        (label, doc)
        for label, doc in (
            (
                "the round report — fits, gates, uncertainty",
                ctx.reports_dir / "report.html",
            ),
            ("who decided what, and why", ctx.round / "decisions_md"),
        )
        if doc.exists()
    ]


def _write_profile_decision(ctx: RunContext, payload: dict) -> None:
    """A human's profile request for the round, at
    `decisions/evaluation_profile_request`: `--skip-profiles` (`skipped`),
    `--profiles` (`requested`) or `profiles` at the verdict card
    (`requested`, `form`). A decision record of its own, beside the profiling
    gate's answer (`decisions/evaluation_profile`), so a re-entered evaluation can
    supersede the gate's answer and keep the request."""
    from octomod.result.records import DecisionRecord
    from octomod.result.write import write_record

    write_record(
        ctx.round / PROFILE_REQUEST,
        DecisionRecord,
        {
            "module": "evaluation_profiling_gate",
            "note": str(payload.get("requested") or payload.get("skipped") or ""),
            "mode": "human",
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            **payload,
        },
    )


@timing.phase("evaluation")
def run(
    ctx: RunContext, cand_ids: list[str] | None = None, rounds_left: int | None = None
) -> dict:
    if ctx.has_marker("s7"):
        print("  (already done — resumed from marker; report stands)")
        return (ctx.round / "evaluation").get()
    if cand_ids:
        return _run_md(ctx, cand_ids, rounds_left)
    ctx.require_marker("s6", needed_by="evaluation")

    summary = (ctx.work / "estimation").get()
    tables = _work_tables(ctx)
    goal = ctx.intent["inference_target"]
    best = summary["best_x_unscaled"]
    ensemble = [m["x_unscaled"] for m in summary["ensemble"]]

    core: dict = {
        "goal": goal,
        "best_fval": summary["best_fval"],
        "n_ensemble": len(ensemble),
        "fit": _fit_metrics(tables, best),
        "chi2_per_dof": _chi2_per_dof(tables, best, summary),
        "chi2_per_dof_note": (
            "sigma is ESTIMATED, so this is ~1 by construction and cannot "
            "reject a model; see misfit_evidence.gof_at_noise_floor for the "
            "test against the assay's own replicate repeatability"
        ),
        "parameters": {
            "best": best,
            "at_bounds": summary["at_bounds"],
            "near_bounds": summary.get("near_bounds") or [],
            "ensemble_log10_spread": _ensemble_spread(ensemble),
        },
        # parameters the inner problem solved analytically, top level on both
        # paths: identifiability here is over the OUTER vector, so the
        # epistemics must say these were not assessed
        "estimated_inner": summary.get("estimated_inner") or {},
    }
    # deterministic structural-misfit evidence (model-free; gates the stop move)
    _long = (ctx.round / "data/measurements").table(None)
    _asm_node = ctx.work / "assembly"
    _obs_labels, _cond_labels = (
        fitted.label_maps(_asm_node.get(), fitted.trained_conditions(tables))
        if _asm_node.exists()
        else ({}, {})
    )
    core["misfit_evidence"] = structural_misfit_evidence(
        tables, best, _long, core["fit"], ctx.spec, _obs_labels, _cond_labels
    )
    core["declared_constants"] = _declared_constants_at_fit(ctx, tables, best)
    _join_declared_constants(core)
    core["latent_states"] = _latent_screen(ctx, tables, best)
    core["identifiability"] = _fim_screen(ctx, summary)

    spreads = core["parameters"]["ensemble_log10_spread"]
    if len(ensemble) > 1 and spreads and max(spreads.values()) < 1e-6:
        # All starts collapsed to one point: a MISSING diagnostic, not evidence
        # of identifiability. Provisional: profiles below may still supply the
        # instrument, and that is settled after they run.
        core["parameters"]["uncertainty_assessed"] = False
        core["parameters"]["note"] = (
            "multistart ensemble collapsed to a single point; ensemble spread "
            "of 0.0 carries no identifiability information in either direction"
        )
    else:
        core["parameters"]["uncertainty_assessed"] = bool(ensemble)

    # held-out prediction (T2')
    hold_df = (ctx.work / "petab" / petab_io.HOLDOUT).table(None)
    if hold_df is None:
        hold_df = pd.DataFrame()
    if len(hold_df):
        core["holdout"] = _holdout_eval(tables, hold_df, best, ensemble, ctx.spec)
    else:
        core["holdout"] = {
            "available": False,
            "note": "no held-out condition declared (single-condition "
            "problem) — T2' unavailable, stated honestly",
        }

    # profiles by the one rule in `_profiles_for`: on request by default, and
    # always (gated) for the parameter goal
    _profiles_for(
        ctx,
        core,
        summary,
        goal,
        int((tables.parameters["estimate"] == 1).sum()),
    )

    # Profiles, if they ran, ARE the parameter-uncertainty instrument — settle
    # the provisional verdict above rather than leaving a stale claim standing.
    _real_profiles = [k for k in core.get("profiles", {}) if not k.startswith("_")]
    if _real_profiles:
        core["parameters"]["uncertainty_assessed"] = True
        if core["parameters"].get("note"):
            core["parameters"]["note"] += (
                f" — but profile likelihoods DID run for {len(_real_profiles)} "
                f"parameters and are the uncertainty instrument for this run; "
                f"read identifiability from the profile CIs, not from the "
                f"ensemble"
            )
    elif core["parameters"].get("uncertainty_assessed") is False:
        core["parameters"]["note"] = (
            core["parameters"].get("note", "")
            + " — and no profiles ran, so this run carries NO parameter-"
            "uncertainty instrument at all"
        )

    # Prediction uncertainty from the profile confidence region (profile
    # skeleton plus ellipsoid rejection samples, envelope); supersedes the
    # sigma-only band.
    if "profiles" in core:
        core["prediction_uncertainty"] = _cr_band(ctx, core, tables, summary)
        if core["holdout"].get("available") and core["prediction_uncertainty"].get(
            "bands"
        ):
            _holdout_from_cr(core, hold_df, tables, summary, ctx.spec)

    # post-fit checks: noise-model residuals and structure at the optimum
    core["noise_check"] = _noise_model_check(tables, best, ctx.spec)
    post_gates = _post_fit_gates(core, tables, best, ctx)
    run_gate_set(
        post_gates, ctx.gates, ctx.ledger, "evaluation", round_idx=ctx.round_idx
    )

    # the consistency gate's reference sets, flat FIM combinations included
    core["computed_cannot_distinguish"] = _computed_cannot_distinguish(
        core, ctx.spec
    ) + _flat_combination_entries(core)
    core["computed_nonetheless_determined"] = _computed_determined(core, ctx.spec)
    core["computed_finite_but_poorly_determined"] = _computed_poorly_determined(
        core, ctx.spec
    )
    (ctx.round / "evaluation_core").put(core)

    # agent interpretation, the two-sided consistency gate, and the check that
    # every identifier the interpretation credits is one this problem has
    names = _problem_names(ctx.round)
    interp = _with_poorly_determined(
        core, _interpret_with_consistency(ctx, core, names=names)
    )
    gate_results = _consistency_results(core, interp, names)
    run_gate_set(
        [lambda r=r: r for r in gate_results],
        ctx.gates,
        ctx.ledger,
        "evaluation",
        round_idx=ctx.round_idx,
    )
    if any(not r.passed and r.blocking for r in gate_results):
        raise ModuleFailure(
            "report consistency gate failed after retry — the "
            "interpretation contradicts the computed evidence"
        )

    # T2' blocking decision (prediction goal)
    t2p = _t2prime_gate(core, goal, ctx.spec)
    run_gate_set(
        [lambda: t2p], ctx.gates, ctx.ledger, "evaluation", round_idx=ctx.round_idx
    )

    report = {**core, "interpretation": interp, "t2prime_passed": t2p.passed}
    _write_report(ctx.round, report)
    (ctx.round / "report_md").put_text(_render_md(ctx, report))
    _write_html(ctx, when="before the verdict ask")

    # the misfit margins and the offer of another round go in `always_show`, so
    # the card's evidence cap cannot hide them
    from octomod.workflow_modules.evaluation import misfit_margins as _mm

    _ev = core.get("misfit_evidence") or {}
    _near = _mm.nearest(_ev)
    _decision_lines: list[str] = []
    _compact = _mm.card_line_compact(_ev)
    if _compact:
        _decision_lines.append(_compact)
    if rounds_left and rounds_left > 0:
        _decision_lines.append(
            f"ANOTHER ROUND? {_rounds.remain(rounds_left)}, and this card is "
            f"the only place to ask for one."
        )
    # profiles on request: the card says so and offers the form
    _prof_lines, _prof_forms = _profiles_card_lines(core)
    _decision_lines += _prof_lines

    approved, _note = humangate.ask_once(
        ctx,
        ctx.round / VERDICT_DECISION,
        "Sign off this verdict? (it is a scientific claim)",
        [
            f"goal: {goal}; best -log(L): {summary['best_fval']:.3f}",
            f"T2' held-out: {'PASS' if t2p.passed else 'FAIL'} — {t2p.detail}",
            *(
                [
                    "⚑ STRUCTURAL MISFIT INDICATORS (measured against the assay's own "
                    "replicate repeatability — informative, not decisive):"
                ]
                + [f"    · {r}" for r in core["misfit_evidence"]["reasons"]]
                if core.get("misfit_evidence", {}).get("open")
                else []
            ),
            *(
                [
                    "also seen, NOT counted as an indicator (a loose screen "
                    "corroborates, it does not decide): "
                    + "; ".join(
                        str(x)[:100] for x in core["misfit_evidence"]["also_seen"]
                    )
                ]
                if core.get("misfit_evidence", {}).get("also_seen")
                else []
            ),
            *_latent_card_lines(core),
            *_structural_card_lines(core),
            *(
                [
                    "⚑ NEAR A BOUND (not at it, so the bounds gate is silent): "
                    + ", ".join(
                        f"{nb['id']} at {float(nb['position']):.0%} of its box"
                        for nb in core["parameters"]["near_bounds"]
                    )
                    + " — a constant pinned against its box is often the one "
                    "absorbing a missing mechanism"
                ]
                if core["parameters"].get("near_bounds")
                else []
            ),
            *(
                [f"⚑ {core['parameters']['note']}"]
                if core["parameters"].get("uncertainty_assessed") is False
                else []
            ),
            *_epistemic_card_lines(interp, ctx.spec),
            "(full claims with evidence: report.html, and the record's "
            f"{(ctx.round / 'report_md').key})",
            # The agent's recommendation is scoped to the intent's required
            # predictions; T2' spans ALL held-out observables and has the
            # authority. Say both, so a bare "accept" never sits beside a fail.
            (
                f"agent recommendation: {interp['recommendation']} — scoped to the "
                f"intent's required prediction; MOOT: T2' spans ALL held-out "
                f"observables, failed, and overrides"
                if interp["recommendation"] in ("accept", "stop")
                and goal == "prediction"
                and not t2p.passed
                else f"agent recommendation: {interp['recommendation']}"
            ),
        ],
        # record_decline=False: a rejected verdict stops the run and costs
        # nothing to re-ask; the human may want to answer differently
        module="evaluation_verdict",
        record_decline=False,
        intent=ctx.intent,
        consequences=_verdict_consequences(interp, t2p, goal, rounds_left, _near),
        note_forms=(
            list(another_round_note_forms(False))
            if rounds_left and rounds_left > 0
            else []
        )
        + _prof_forms,
        # the documents that carry the evidence behind this claim
        documents=_verdict_documents(ctx),
        # what the human chooses from is never capped by the evidence budget
        always_show=_decision_lines,
    )
    if not approved:
        raise ModuleFailure("user rejected the verdict")
    if _take_profiles_request(ctx, core, _note):
        return run(ctx, None, rounds_left)
    _requested = parse_another_round_request(_note)
    gate_note.report(
        another_round_reading(_note),
        _note,
        ledger=ctx.ledger,
        module="evaluation_verdict",
        round_idx=ctx.round_idx,
    )
    if _requested is not None:
        ctx.ledger.append(
            "note",
            module="evaluation_verdict",
            round_idx=ctx.round_idx,
            note=(
                "human asked for another round"
                if _requested
                else "human declined another round"
            )
            + f" (agent recommended {interp['recommendation']!r}, "
            f"rounds_left={_rounds.as_record(rounds_left)})",
            human_another_round_request=_requested,
            agent_recommendation=str(interp["recommendation"]),
        )
    ctx.set_marker("s7", recommendation=interp["recommendation"], t2prime=t2p.passed)
    _write_html(ctx, when="after signing")
    return report


def _profile_engine(ctx, one_profile_s: float | None):
    """The engine for profiles, chosen from what ONE PROFILE costs, not one start.

    `make_engine(auto)` goes parallel when a single dispatched task is slow
    enough to dwarf the ~1 s spawn. A profiling task is a parameter's profile,
    so the caller passes the high estimate of the dearest one
    (`profile_projection.one_profile_high_s`): its points walking to the bounds,
    at the high end of the per-point cost."""
    from octomod.workflow_modules.estimation.problem import make_engine

    return make_engine(ctx.spec, one_profile_s)


@timing.timed("compute", "prediction_uncertainty")
def _cr_band(ctx: RunContext, core: dict, tables: PetabTables, summary: dict) -> dict:
    from octomod.workflow_modules.evaluation.uncertainty import confidence_region_band

    try:
        # the settings the fit ran with, not the declared ones alone
        problem, _, _ = estimation_settings.build(ctx)
        t_end = float(ctx.testcase.get("t_end", 100.0))
        dense = np.linspace(0.0, t_end, 61)
        # a condition measured at steady state (time inf) is banded there too,
        # so a held-out steady-state row is scored against the steady state
        steady = _steady_state_conditions(tables)
        conditions_times = {}
        # a condition only ever pre-equilibrated from has no measurement to band
        pre_only = tables.preequilibration_only_ids
        for obs_id in tables.observables["observableId"].astype(str):
            for cond_id in tables.conditions["conditionId"].astype(str):
                if cond_id not in pre_only:
                    conditions_times[(obs_id, cond_id)] = (
                        np.append(dense, np.inf) if cond_id in steady else dense
                    )
        out = confidence_region_band(
            problem,
            tables,
            core["profiles"],
            _parameter_scales(ctx),
            summary["best_x_unscaled"],
            float(summary["best_fval"]),
            conditions_times,
            ctx.spec,
            rng_seed=int(ctx.spec.require("estimation.seed")),
            inner=summary.get("estimated_inner") or {},
        )
        # Every caveat is ledgered: a low acceptance rate, a region built from
        # the profile skeleton alone, and a band that covers only the outer
        # parameters. None may be silent.
        for key in ("note", "skeleton_only_note", "outer_only_note"):
            if key in out:
                ctx.ledger.append(
                    "note",
                    module="evaluation",
                    round_idx=ctx.round_idx,
                    note=f"CR band: {out[key]}",
                )
                print(f"  ⚑ confidence-region band: {out[key]}")
        if out.get("skeleton_only"):
            print(
                f"  confidence-region band: built from "
                f"{out['n_kept_skeleton']} profile skeleton point(s), no "
                f"rejection samples (df={out['df']})"
            )
        elif "note" not in out:
            # split: n_kept includes the profile skeleton, so one count would
            # exceed the number of box samples
            print(
                f"  confidence-region band: kept "
                f"{out['n_kept_box_samples']} of {out['n_box_samples']} box "
                f"samples, plus {out['n_kept_skeleton']} profile skeleton "
                f"point(s) (df={out['df']})"
            )
        return out
    except Exception as e:
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"CR band failed (falling back to sigma band): {e}",
        )
        return {"note": f"unavailable: {e}"}


def _steady_state_conditions(tables: PetabTables) -> set[str]:
    """The simulation conditions with a steady-state measurement (PEtab's time
    `inf`), training and held out alike."""
    out: set[str] = set()
    for df in (tables.measurements, tables.holdout_measurements):
        if df is None or not len(df):
            continue
        t = pd.to_numeric(df["time"], errors="coerce").to_numpy(dtype=float)
        out |= set(df.loc[np.isposinf(t), "simulationConditionId"].astype(str))
    return out


def _holdout_from_cr(
    core: dict, hold_df: pd.DataFrame, tables: PetabTables, summary: dict, spec
) -> None:
    """Re-score holdout coverage/width against the confidence-region envelope
    (95%) plus observation noise — parameter AND measurement uncertainty."""

    z = float(spec.get("gates.predictive_z", 1.96))
    best = summary["best_x_unscaled"]
    bands = core["prediction_uncertainty"]["bands"]
    # a skeleton-only envelope is narrower than the region: the held-out score
    # names that, so a miss is read against the band it was scored on
    source = (
        "confidence-region envelope (95%, profile skeleton only: undersampled) "
        "+ observation noise"
        if core["prediction_uncertainty"].get("skeleton_only")
        else "confidence-region envelope (95%) + observation noise"
    )
    for g in core["holdout"]["groups"]:
        band = bands.get(g["label"])
        if not band:
            continue
        obs_id, cond_id = g["label"].split("@", 1)
        grp = hold_df.query(
            "observableId == @obs_id and " "simulationConditionId == @cond_id"
        )
        times = grp["time"].to_numpy(dtype=float)
        meas = grp["measurement"].to_numpy(dtype=float)
        sig = noise_band(tables, obs_id, cond_id, times, best, z)
        lo = np.interp(times, band["time"], band["lo95"]) - sig
        hi = np.interp(times, band["time"], band["hi95"]) + sig
        rng = float(np.ptp(meas)) or 1.0
        g["band_coverage"] = float(np.mean((meas >= lo) & (meas <= hi)))
        g["band_rel_width"] = float(
            np.mean(
                np.interp(times, band["time"], band["hi95"])
                - np.interp(times, band["time"], band["lo95"])
            )
            / rng
        )
        g["band_source"] = source


@timing.timed("compute", "noise_check")
def _noise_model_check(tables: PetabTables, best: dict, spec) -> dict:
    """Do the standardized residuals actually follow the ASSUMED noise
    distribution? Shapiro for normal, KS against unit-variance Laplace; QQ data
    stored for the report's plot. Advisory: a failed test is a diagnosis, not a
    crash."""
    from scipy import stats

    out = {}
    for obs_id, grp in tables.measurements.groupby("observableId"):
        obs_id = str(obs_id)
        res = []
        for cond_id, cgrp in grp.groupby("simulationConditionId"):
            times = cgrp["time"].to_numpy(dtype=float)
            sim = sim_group(tables, obs_id, str(cond_id), times, best)
            # per-point sigma: constant for a plain sigma parameter, state-
            # dependent for a proportional noise formula
            sig = np.maximum(
                tables.sigma_series(obs_id, str(cond_id), times, best), 1e-12
            )
            res.extend(
                ((cgrp["measurement"].to_numpy(dtype=float) - sim) / sig).tolist()
            )
        r = np.sort(np.asarray(res, dtype=float))
        n = len(r)
        dist = str(
            tables.observables.set_index("observableId").loc[
                obs_id, "noiseDistribution"
            ]
        ).lower()
        if n < 8:
            out[obs_id] = {
                "assumed": dist,
                "n": n,
                "note": "too few residuals for a distribution test",
            }
            continue
        if dist == "laplace":
            stat, pval = stats.kstest(r, "laplace", args=(0, 1 / np.sqrt(2)))
            theo = stats.laplace.ppf((np.arange(1, n + 1) - 0.5) / n, 0, 1 / np.sqrt(2))
            test = "KS vs Laplace(0, 1/sqrt(2))"
        else:
            stat, pval = stats.shapiro(r)
            theo = stats.norm.ppf((np.arange(1, n + 1) - 0.5) / n)
            test = "Shapiro-Wilk vs N(0,1)"
        out[obs_id] = {
            "assumed": dist,
            "test": test,
            "n": n,
            "statistic": round(float(stat), 4),
            "p_value": round(float(pval), 5),
            "qq": {
                "theoretical": [round(float(v), 4) for v in theo],
                "sample": [round(float(v), 4) for v in r],
            },
        }
    return out


@timing.timed("compute", "post_fit_gates")
def _post_fit_gates(
    core: dict, tables: PetabTables, best: dict, ctx: RunContext
) -> list:
    from octomod.workflow_modules.model.simwrap import SimError

    @gate("evaluation_noise_model_check", "T2")
    def g_noise():
        alpha = float(ctx.spec.get("gates.noise_check_alpha", 0.01))
        bad = [
            f"{o} (p={c['p_value']})"
            for o, c in core["noise_check"].items()
            if c.get("p_value") is not None and c["p_value"] < alpha
        ]
        # advisory, so a rejection never stops the run — but it is a rejection,
        # and the card and the report read `passed`
        return GateResult(
            "evaluation_noise_model_check",
            "T2",
            not bad,
            blocking=False,
            value=bad,
            threshold=f"p >= {alpha}",
            detail=(
                "standardized residuals consistent with the assumed noise "
                "model for every observable"
                if not bad
                else f"residuals REJECT the assumed noise model for: {bad} — "
                f"a change_noise_model revision candidate"
            ),
            advisory_findings=bad,
        )

    @gate("evaluation_structure_at_optimum", "T1")
    def g_structure():
        """Structural tests repeated post-fit: the model must simulate
        finitely and non-negatively AT ITS OWN OPTIMUM."""
        t_end = float(ctx.testcase.get("t_end", 100.0))
        worst = 0.0
        for cond_id in tables.conditions["conditionId"].astype(str):
            try:
                overrides = tables.condition_overrides(cond_id, values=best)
                dyn = {k: v for k, v in best.items() if k in tables.model_entities}
                traj = tables.model.simulate(
                    t_end * 1.0001, n_points=121, overrides={**overrides, **dyn}
                )
            except SimError as e:
                return GateResult(
                    "evaluation_structure_at_optimum",
                    "T1",
                    False,
                    detail=f"model fails to simulate at its own "
                    f"optimum under {cond_id}: {e}",
                )
            for s in tables.model.species_ids:
                worst = min(worst, float(np.min(traj[s])))
        tol = float(ctx.spec.get("gates.sim_box.nonneg_tol", -1e-6))
        passed = worst >= tol
        return GateResult(
            "evaluation_structure_at_optimum",
            "T1",
            passed,
            value=round(worst, 8),
            threshold=tol,
            detail="simulates finitely and non-negatively at the "
            "fitted optimum under every condition",
        )

    @gate("evaluation_structural_misfit_open", "T2")
    def g_misfit():
        """Model-free evidence that the STRUCTURE is wrong: sigma above the
        replicate noise floor, autocorrelated residuals, or a fit worse than
        the assay's own repeatability. Advisory as a verdict — but it GATES
        THE STOP MOVE at S11: while this is open, 'we are satisfied' is not
        an available conclusion."""
        ev = core.get("misfit_evidence", {})
        if not ev.get("available"):
            return GateResult(
                "evaluation_structural_misfit_open",
                "T2",
                True,
                blocking=False,
                value=None,
                detail="no replicate structure in the data — the model-free "
                "noise floor could not be computed (this check is "
                "UNTESTED here, not passed)",
            )
        reasons = ev.get("reasons", [])
        return GateResult(
            "evaluation_structural_misfit_open",
            "T2",
            not reasons,
            blocking=False,
            value=len(reasons),
            threshold=f"alpha {ctx.spec.get('gates.misfit.alpha', 0.01)}",
            detail=(
                "; ".join(reasons)
                if reasons
                else "no structural-misfit signal: sigma at the replicate "
                "floor, residuals unstructured, fit consistent with assay "
                "repeatability"
            ),
            advisory_findings=reasons,
        )

    return [g_noise, g_structure, g_misfit]


def _declared_constants_at_fit(ctx: RunContext, tables, best: dict) -> dict:
    """Declared constants measured at the fit, in every condition the run used.

    S1 measures at nominal parameters, the cheap early warning; this asks
    whether, with the parameters the data chose, the quantity the note calls
    constant stays constant.
    """
    from octomod.workflow_modules.model import declared_constants as dc

    # a supplied-PEtab run never called construction, so there is no build
    # report and nothing was declared — that is a legitimate absence
    build = (ctx.round / "model/build_report").get(None) or {}
    constants = dc.parse({"declared_constants": build.get("declared_constants")})
    if not constants:
        return {"declared": 0, "violated": 0, "worst_drift": None, "rows": []}
    # the DECLARATION is shared by the round (one construction reply), but the
    # MODEL being measured is the candidate's: on a discrimination round
    # `ctx.model` is the winner's
    sbml = (ctx.model / "sbml").text(None)
    if sbml is None:
        sbml = (ctx.round / "model/sbml").text(None)
    if sbml is None:
        return {
            "declared": len(constants),
            "violated": 0,
            "worst_drift": None,
            "rows": [
                {**c, "condition": "-", "error": "no model in the record"}
                for c in constants
            ],
        }
    t_end = float(ctx.testcase.get("t_end", 100.0))
    # only names the MODEL knows: `best` also carries observable parameters,
    # and passing one as an override raises
    dyn = _model_only(tables, best)
    rows = []
    try:
        conds = list(tables.conditions["conditionId"].astype(str))
    except Exception:
        conds = []
    for cond_id in conds or ["nominal"]:
        overrides = dict(dyn)
        if conds:
            try:
                overrides.update(tables.condition_overrides(cond_id, values=dyn))
            except Exception:
                pass
        rows += dc.drift(sbml, constants, t_end, overrides, label=cond_id)
    return dc.summary(rows)


def _join_declared_constants(core: dict) -> None:
    """A violated declaration is structural-misfit evidence — CORROBORATING,
    never decisive on its own.

    A note can be wrong and the data outrank it, so the drift is treated like
    the autocorrelation screen: it joins `reasons` when a HARD signal (fitted
    sigma or chi2 against the replicate floor) is already open, and is
    otherwise reported in `also_seen`. The report states a selected model's
    violation on its first screen (`declared_constant_verdict_lines`).

    Runs AFTER `structural_misfit_evidence`, so `ev["open"]` already means "a
    hard signal fired".
    """
    from octomod.workflow_modules.model import declared_constants as dc

    summary = core.get("declared_constants") or {}
    bad = dc.offenders(summary.get("rows") or [])
    if not bad:
        return
    ev = core.setdefault(
        "misfit_evidence", {"open": False, "reasons": [], "signals": {}}
    )
    worst = bad[0]
    reason = (
        f"the experiment declares {worst['expression']} constant, and the "
        f"fitted model moves it by {worst['drift']:.0%} in {worst['condition']} "
        f"({worst['at_t0']:.4g} to {worst['worst']:.4g} by t="
        f"{worst['at_time']:.3g})"
    )
    if ev.get("open"):
        ev.setdefault("reasons", []).append(reason)
    else:
        ev.setdefault("also_seen", []).append(reason)
    ev.setdefault("signals", {})["declared_constant_drift"] = True


@timing.timed("compute", "identifiability")
def _fim_screen(ctx: RunContext, summary: dict) -> dict:
    """The Fisher information at the MLE, as a SPECTRUM (`identifiability`).

    Runs on `ctx.work`, so a discrimination round screens the winner. Never
    raises: a failure comes back as `available: False` with the reason.
    """
    from octomod.workflow_modules.evaluation import identifiability

    try:
        # the settings the fit ran with, not the declared ones alone
        problem, _, _ = estimation_settings.build(ctx)
        # rebuilt from the unscaled best and the parameter scales, in the
        # problem's own name order, so the screen also works after a resume
        scales = _parameter_scales(ctx)
        best = summary.get("best_x_unscaled") or {}
        if not best:
            return {
                "available": False,
                "note": "no MLE in the record to evaluate the information matrix at",
            }
        x_scaled = []
        for name in problem.x_names:
            value = best.get(name)
            if value is None:
                x_scaled.append(0.0)
            elif scales.get(name) == "log10":
                x_scaled.append(math.log10(max(float(value), 1e-300)))
            else:
                x_scaled.append(float(value))
        kept: dict = {}
        ident = identifiability.fim_at_mle(
            problem,
            x_scaled,
            list(summary.get("x_names") or problem.x_names),
            scales,
            flat_decades=float(ctx.spec.get("gates.fim.flat_decades", 8.0)),
            jacobian_out=kept,
        )
        free = list(problem.x_free_indices)
        x_free = np.asarray(x_scaled, dtype=float)
        if len(x_free) == len(problem.x_names):
            x_free = x_free[free]
        ident["structural_recheck"] = _structural_recheck(
            ctx, problem, x_free, kept.get("J")
        )
        return ident
    except Exception as exc:  # a screen must never end a run
        return {"available": False, "note": f"{type(exc).__name__}: {exc}"}


def _structural_recheck(ctx: RunContext, problem, x_free, jacobian) -> dict:
    """The pre-fit structural flat directions, measured again at the MLE.

    Reads the probe's record (`structural_nulls` under `ctx.work`) without
    measuring it: a fit reused from an earlier round was never probed, and the
    check then says so. The result is written beside the record
    (`structural_nulls_at_mle`) and ledgered
    once per distinct outcome, since S7 re-runs on every resume until its
    verdict is answered. The outcome is the counts and the line, not the whole
    record: the screen reads with sigma residuals on, as the probe does, so its
    Jacobian does not depend on what ran earlier in the process, but a pass
    that had none to reuse (adjoint sensitivities, an integration failure)
    measures the same finding the other way, and a resume must not ledger it
    twice for that. Never raises.
    """
    from octomod.workflow_modules.evaluation import structural_nulls as _sn

    counts = ("available", "n_pre_fit", "n_confirmed", "n_not_confirmed")

    def outcome(r) -> tuple | None:
        if not isinstance(r, dict):
            return None
        return (_sn.recheck_line(r), *(r.get(k) for k in (*counts, "n_flat_at_mle")))

    try:
        pre = _sn.node(ctx.work).get(None)
        rec = _sn.recheck_with_spec(problem, x_free, pre, ctx.spec, jacobian)
    except Exception as exc:  # a screen must never end a run
        rec = {"available": False, "why": f"{type(exc).__name__}: {exc}"}
    try:
        out = _sn.node_at_mle(ctx.work)
        before = out.get(None)
        out.put(rec)
        if outcome(before) != outcome(json.loads(json.dumps(rec, default=str))):
            ctx.ledger.append(
                "note",
                module="evaluation",
                round_idx=ctx.round_idx,
                candidate=getattr(ctx, "candidate", None),
                note=_sn.recheck_line(rec),
                structural_recheck={
                    k: rec.get(k) for k in (*counts, "n_flat_at_mle", "jacobian_reused")
                },
            )
    except Exception as exc:
        _swallowed(ctx, "the structural re-check record", exc)
    return rec


def _model_only(tables, best: dict) -> dict:
    """The best-fit values the MODEL can accept as overrides.

    `best` spans the whole PEtab parameter table, including observable and
    noise parameters that live in the observable formulas rather than in the
    SBML; passing one to the simulator raises.
    """
    try:
        known = set(tables.model_entities)
    except Exception:
        known = set()
    if not known:
        return {k: v for k, v in best.items() if not str(k).startswith("sigma")}
    return {k: v for k, v in best.items() if k in known}


def _interpreter_residuals(
    ctx: RunContext, core: dict, cand_ids: list[str] | None
) -> dict:
    """The same time-resolved residual payload the expansion proposer gets:
    an interpreter that interprets fits must see the fits, not only scalars.

    Its `residual_forms` block is also written to the round's `residual_forms`
    record, which the report reads: a resume that reuses the pinned
    interpretation does not rebuild this payload, and the report must not lose
    the line."""
    from octomod.workflow_modules.evaluation.residuals import (
        RESIDUAL_FORMS_KEY,
        expansion_payload,
    )

    winner = (core.get("discrimination") or {}).get("winner") or ""
    ids = [c for c in (cand_ids or []) if c] or [None]
    try:
        # `core` is already in hand, so the payload must not re-read the
        # round's evaluation_core from the record mid-module
        diag = expansion_payload(ctx, ids, winner, core)
        if (diag.get("residual_forms") or {}).get("summary") is not None:
            (ctx.round / RESIDUAL_FORMS_KEY).put(diag["residual_forms"])
        return diag
    except Exception as exc:  # the interpreter still runs without it
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"interpreter residual payload unavailable: {exc}",
        )
        return {"unavailable": f"{type(exc).__name__}: {exc}"}


def _flat_combination_entries(core: dict) -> list[str]:
    """Flat FIM directions as machine-computed `cannot_distinguish` entries.

    This is the other half of the sentence "these combinations are flat AND
    these predictions are nonetheless tight": a comprehensively
    non-identifiable model can still predict well, so the flat directions are
    a statistic the agent must echo, never a reason to reject a model.
    """
    from octomod.workflow_modules.evaluation import identifiability

    return identifiability.computed_flat_combinations(core.get("identifiability") or {})


def _latent_card_lines(core: dict) -> list[str]:
    from octomod.workflow_modules.evaluation import latent_states

    return latent_states.card_lines(core.get("latent_states") or {})


def _epistemic_card_lines(interp: dict, spec) -> list[str]:
    """The verdict card's epistemics: the two gated lists, then the third.

    The third (closed profiles wider than the determined fraction of their box)
    is shown only when it has entries; an empty one adds nothing to a card.
    """

    def short(c) -> str:
        return f"  · {str(c).split('(')[0].split(' — ')[0][:90].strip()}"

    cd = list(interp.get("cannot_distinguish") or [])
    nd = list(interp.get("nonetheless_determined") or [])
    pd_ = list(interp.get("finite_but_poorly_determined") or [])
    out = [f"cannot distinguish ({len(cd)}):", *(short(c) for c in cd[:4])]
    out += [f"nonetheless determined ({len(nd)}):", *(short(c) for c in nd[:4])]
    if pd_:
        frac = float(spec.get("gates.determined_box_fraction", 0.1))
        out += [
            f"finite but poorly determined ({len(pd_)}) — the profile closes, "
            f"over more than {frac:.0%} of its box:",
            *(short(c) for c in pd_[:4]),
        ]
    return out


def _structural_card_lines(core: dict) -> list[str]:
    """The pre-fit structural flat directions as they stand at the fit."""
    from octomod.workflow_modules.evaluation import structural_nulls as _sn

    line = _sn.recheck_line(
        (core.get("identifiability") or {}).get("structural_recheck")
    )
    return [line] if line else []


@timing.timed("compute", "latent_screen")
def _latent_screen(ctx: RunContext, tables, best: dict) -> dict:
    """Are the states nobody measured plausible at the MLE?

    Runs on whatever `ctx.work` points at, so a discrimination round screens
    the WINNER. Advisory unless the intent declared the range itself.
    """
    from octomod.workflow_modules.evaluation import latent_states

    sbml = (ctx.model / "sbml").text(None)
    if sbml is None:
        return {"conditions_checked": 0, "findings": [], "hard_failures": []}
    conditions = {}
    try:
        for cond_id in tables.conditions["conditionId"].astype(str):
            conditions[cond_id] = tables.condition_overrides(cond_id, values=best)
    except Exception:
        conditions = {}
    best = _model_only(tables, best)
    ranges = ctx.intent.get("state_ranges") or {}
    try:
        return latent_states.screen(
            sbml,
            float(ctx.testcase.get("t_end", 100.0)),
            conditions,
            best,
            ranges=ranges if isinstance(ranges, dict) else {},
            nonneg_tol=float(ctx.spec.get("gates.sim_box.nonneg_tol", -1e-6)),
        )
    except Exception as exc:
        return {
            "conditions_checked": 0,
            "findings": [],
            "hard_failures": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


@timing.timed("render", "report_html")
def _write_html(ctx, *, when: str) -> None:
    """Render report.html (a real file under `ctx.reports_dir`). Called TWICE
    per round on purpose.

    Once BEFORE the verdict ask, because the card tells the human the full
    claims are in that file; once after signing, so the recorded decision is in
    the document too. Never raises: a failure is ledgered.
    """
    from octomod.reporting import write_report_html

    try:
        write_report_html(ctx.round)
    except Exception as e:
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"html report failed ({when}): {e}",
        )


def _comparability_gate(comparability: dict):
    """T1, BLOCKING for a selection round.

    Passes when every candidate shares one transformation per observable, or
    when the change-of-variables correction was applied. Without it a search
    could "discover" that log-transforming everything improves AIC, which is
    an artefact of comparing likelihoods over different data.
    """

    @gate("evaluation_selection_comparable", "T1")
    def g():
        ok = (
            comparability["shared_transformation"]
            or comparability["correction_applied"]
        )
        terms = {
            cid: v["correction"]
            for cid, v in comparability["per_candidate"].items()
            if v["correction"]
        }
        return GateResult(
            "evaluation_selection_comparable",
            "T1",
            ok,
            detail=(
                comparability["detail"]
                if comparability["shared_transformation"]
                else f"{comparability['detail']} — correction applied: {terms}"
            ),
        )

    return g


# The note forms a verdict gate accepts, declared as data so the card, the
# file-gate payload and the parser cannot drift apart. The selection path buys
# an EXPANSION and the single-model path a REVISION; the parser accepts both
# spellings on both paths, and `another_round_note_forms` picks the wording.
EXPANSION_NOTE_FORMS = (
    "expand: yes  — buy another round: the agent says what the space was "
    "missing, and you get its own gate before anything is refitted",
    "expand: no   — end the run with this selection",
    "(nothing)    — take the default named above",
)

REVISION_NOTE_FORMS = (
    "revise: yes  — buy another round: the agent proposes one change to the "
    "model, and you get its own gate before anything is refitted",
    "revise: no   — end the run with this model",
    "(nothing)    — take the default named above",
)

# `expan\w*` rather than `expand\w*`, so the noun "expansion" matches too;
# `revis\w*` covers revise/revision the same way.
_EXPAND_EXPLICIT = re.compile(
    r"\b(?:expan\w*|revis\w*|round)\s*[:=]\s*(yes|y|true|no|n|false)\b", re.I
)
_EXPAND_NEGATIVE = re.compile(
    r"\b(?:no|don'?t|do\s+not|skip|without)\s+(?:another\s+)?"
    r"(?:expan\w*|revis\w*|round|loop|iteration)\b",
    re.I,
)
_EXPAND_POSITIVE = re.compile(
    r"\b(?:expan\w*|revis\w*|(?:another|one\s+more|a\s+further)\s+"
    r"(?:round|loop|iteration))\b",
    re.I,
)


def another_round_note_forms(is_selection_round: bool) -> tuple[str, ...]:
    """The note forms to print, worded for the loop this round is in."""
    return EXPANSION_NOTE_FORMS if is_selection_round else REVISION_NOTE_FORMS


_EXPAND_POSITIVE = re.compile(
    r"\b(?:expan\w*|(?:another|one\s+more|a\s+further)\s+"
    r"(?:round|loop|iteration))\b",
    re.I,
)


def parse_another_round_request(note: str | None) -> bool | None:
    """Did the human ASK for another round? True / False / None.

    None means the note said nothing about it, and the default applies. Accepts
    both paths' vocabulary (`expand:`, `revise:`) and plain forms such as
    "another loop". The explicit form is tried first, so `expand: no` is never
    read as a request by the positive pattern; then negations; then requests.
    """
    text = (note or "").strip()
    if not text:
        return None
    m = _EXPAND_EXPLICIT.search(text)
    if m:
        return m.group(1).lower() in ("yes", "y", "true")
    if _EXPAND_NEGATIVE.search(text):
        return False
    # Clause by clause (`gate_note.clauses`): a negation anywhere BEFORE the
    # word in its own clause wins, so "I don't think we need expansion yet" is
    # not a request.
    from octomod.orchestration.interaction import gate_note

    for clause in gate_note.clauses(text):
        hit = _EXPAND_POSITIVE.search(clause)
        if hit is None:
            continue
        return not bool(_NEGATION.search(clause[: hit.start()]))
    return None


_NEGATION = re.compile(
    r"\b(?:no|not|never|don'?t|doesn'?t|do\s+not|skip|without)\b", re.I
)


def another_round_reading(note: str | None):
    """The verdict gate's reading of its note, for `gate_note.report`."""
    from octomod.orchestration.interaction import gate_note

    asked = parse_another_round_request(note)
    r = gate_note.Reading()
    if asked is not None:
        r.read["another round"] = "yes" if asked else "no"
    elif re.search(r"\b(?:expan\w*|revis\w*|round|loop|iteration)\b", note or "", re.I):
        r.unread["another round"] = (
            "mentioned but not asked for — `expand: yes` or `expand: no`"
        )
    return r


# the selection path's name for it, read by `orchestrator` and the suites
parse_expansion_request = parse_another_round_request


# The recommendations that mean "do not stop here". `reject` is included
# because it is a stronger form of the same statement, not a different one.
AGENT_WANTS_MORE = ("revise", "reject")


def verdict_disagreement(
    recommendation: str | None, misfit_open: bool, rounds_left
) -> dict | None:
    """The agent said keep going and the engine is about to stop. Or None.

    Two judgements pointing opposite ways is information, so it goes on the
    card and in the ledger. Returns the record both are built from, so they
    cannot describe the disagreement differently.
    """
    rec = str(recommendation or "").lower()
    if rec not in AGENT_WANTS_MORE:
        return None
    have_round = bool(rounds_left and rounds_left > 0)
    # The engine's default is to end unless the misfit is open AND a round
    # remains — the same condition `should_expand` applies, stated here so the
    # card describes what will actually happen.
    if misfit_open and have_round:
        return None
    return {
        "agent_recommendation": rec,
        "engine_default": "end",
        "because": ("no indicator is open" if not misfit_open else "no rounds left"),
        "rounds_left": _rounds.as_record(rounds_left),
        "human_can_override": have_round,
    }


def md_verdict_consequences(
    misfit_open: bool, rounds_left, nearest: dict | None = None
) -> tuple[str, str]:
    """What signing a DISCRIMINATION verdict does, in the card's own words.

    Uses the rounds-remaining count the orchestrator uses, so the card never
    promises a step that is then skipped. While a round remains, BOTH answers
    to "another round?" are offered and the closest indicator's distance is
    stated either way: the default flips with the indicators, and the decision
    stays the user's.
    """
    have_round = bool(rounds_left and rounds_left > 0)
    near = f" The closest indicator: {nearest['reads_as']}" if nearest else ""

    if not have_round:
        if misfit_open:
            yes = (
                "verdict recorded and THE RUN ENDS with this selection — the "
                "misfit evidence stays OPEN and is recorded as unexplained, "
                "because no rounds are left to enlarge the space"
            )
        else:
            yes = (
                "verdict recorded and THE RUN ENDS with this selection; no "
                "rounds are left, so another round cannot be bought here" + near
            )
        return (yes, "run stops here without an accepted verdict")

    if misfit_open:
        yes = (
            "verdict recorded. DEFAULT, because the misfit evidence is open: "
            "the expansion agent is asked what the space was missing, and you "
            f"get its own gate before anything is refitted "
            f"({_rounds.left(rounds_left)}). Add `expand: no` to the note to end the run "
            "here instead."
        )
    else:
        yes = (
            "verdict recorded. DEFAULT, because no indicator is open: THE RUN "
            f"ENDS with this selection. Add `expand: yes` to the note to buy "
            f"another expansion round instead — {_rounds.remain(rounds_left)} "
            "and this is the only place to ask for one." + near
        )
    return (yes, "run stops here without an accepted verdict")


def _verdict_consequences(
    interp, t2p, goal, rounds_left, nearest: dict | None = None
) -> tuple[str, str]:
    """What signing a SINGLE-MODEL verdict does, in the card's own words.

    On this path the loop ends on the agent's `accept`/`stop` recommendation,
    so while a round remains the card offers another one: the agent
    recommends, the human decides.
    """
    rec = interp["recommendation"]
    have_round = bool(rounds_left and rounds_left > 0)
    near = f" The closest indicator: {nearest['reads_as']}" if nearest else ""

    if rec in ("accept", "stop"):
        if goal == "prediction" and not t2p.passed:
            yes = (
                "verdict recorded — but T2' is unmet, so the acceptance will be "
                "OVERRIDDEN into a revision"
                + (
                    f" ({_rounds.left(rounds_left)})"
                    if rounds_left
                    else " — and no rounds are left, so the run ends UNMET"
                )
            )
        elif have_round:
            yes = (
                f"verdict recorded. DEFAULT, because the agent recommends "
                f"'{rec}': THE RUN ENDS and this model is the result. Add "
                f"`revise: yes` to the note to buy another round instead — "
                f"{_rounds.remain(rounds_left)} and this is the only place to "
                f"ask for one." + near
            )
        else:
            yes = (
                "verdict recorded and THE RUN ENDS — this model is the result; "
                "no rounds are left, so another round cannot be bought here" + near
            )
    elif have_round:
        yes = (
            f"verdict recorded. DEFAULT, because the agent recommends "
            f"'{rec}': a revision proposal follows, with its own approval gate "
            f"({_rounds.left(rounds_left)}). Add `revise: no` to the note to "
            f"end the run here instead."
        )
    else:
        # the loop breaks on `rounds_left <= 0` before `revision_proposal` is called,
        # so no revision may be promised here
        yes = (
            f"verdict recorded and THE RUN ENDS — the agent recommends "
            f"'{rec}', but no rounds are left, so no revision is proposed and "
            f"the recommendation is recorded unacted-on"
        )
    return (yes, "run stops here without an accepted verdict")


def _run_md(
    ctx: RunContext, cand_ids: list[str], rounds_left: int | None = None
) -> dict:
    """Discriminate fitted candidates by information criteria, report
    selection uncertainty honestly (AIC weights, indistinguishable set), and
    model-average held-out predictions when a holdout exists — the field's
    formal answer to 'what can the data not distinguish'."""
    from octomod.workflow_modules.evaluation import selection as _selection

    rows, sims = [], {}
    # a criterion compares likelihoods over the SAME data, so the
    # transformation each candidate declares is collected before anything is
    # compared
    transforms: dict[str, dict[str, str]] = {}
    corrections: dict[str, float] = {}
    correction_detail: dict[str, dict] = {}
    for cid in cand_ids:
        with as_candidate(ctx, cid):
            wd = ctx.work
            summary = (wd / "estimation").get()
            par = (wd / "petab/parameters").table()
            n_est = int((par["estimate"] == 1).sum())
            # directions no output depends on at any parameter value, as an
            # INDICATOR only: the criterion charges every estimated parameter
            from octomod.workflow_modules.evaluation import structural_nulls as _sn

            n_flat = _sn.n_flat(_sn.for_candidate(ctx))
            nllh = float(summary["best_fval"])
            obs_df = (wd / "petab/observables").table()
            meas_df = (wd / "petab/measurements").table()
            transforms[cid] = _selection.transformations(obs_df)
            corrections[cid], correction_detail[cid] = _selection.jacobian_correction(
                obs_df, meas_df
            )
            rows.append(
                {
                    "id": cid,
                    "n_est": n_est,
                    "n_flat": n_flat,
                    "n_data": summary["n_data"],
                    "nllh": nllh,
                    **_selection.information_criteria(nllh, n_est, summary["n_data"]),
                    "at_bounds": summary["at_bounds"],
                    "near_bounds": summary.get("near_bounds") or [],
                    "best": summary["best_x_unscaled"],
                }
            )
            hold_df = (wd / "petab" / petab_io.HOLDOUT).table(None)
            if hold_df is None:
                hold_df = pd.DataFrame()
            if len(hold_df):
                tables = PetabTables(
                    observables=obs_df,
                    conditions=(wd / "petab/conditions").table(),
                    measurements=meas_df,
                    parameters=par,
                    sbml=(ctx.model / "sbml").text(),
                    holdout_measurements=hold_df,
                )
                sims[cid] = (tables, hold_df, summary)

    # This MUST come first: every candidate's likelihood goes into measurement
    # space BEFORE the ΔAIC/weight arithmetic and the petab_select crosscheck.
    shared, comparability = _selection.apply_correction(rows, transforms, corrections)
    for cid, rec in comparability["per_candidate"].items():
        rec["by_observable"] = correction_detail.get(cid, {})

    # AIC-based columns are always reported (renderers, scorer and tests read
    # them); the SELECTION uses the spec's criterion, computed once locally
    # (model_space.select) and once by petab_select, and the two must agree.
    aics = np.array([r["aic"] for r in rows])
    delta = aics - aics.min()
    weights = np.exp(-0.5 * delta)
    weights = weights / weights.sum()
    for r, d, w in zip(rows, delta, weights, strict=False):
        r["delta_aic"], r["akaike_weight"] = round(float(d), 3), round(float(w), 4)
    thresh = float(
        ctx.spec.get("gates.discrimination.delta_aic_indistinguishable", 2.0)
    )
    decisive_w = float(ctx.spec.get("gates.discrimination.decisive_weight", 0.7))
    crit_name = str(ctx.spec.get("search.criterion", "AIC")).upper()
    from octomod.workflow_modules.model import tried_models as _tried_models

    declared = {a["id"] for a in model_space.declared_axes(ctx)}

    def _axes_on(cid: str) -> list[str]:
        return [a for a in cid.split("+") if a in declared] if declared else []

    fits = [
        {
            "model_id": r["id"],
            "axes_on": _axes_on(r["id"]),
            "n_estimated": r["n_est"],
            "nllh": r["nllh"],
            "n_data": r["n_data"],
        }
        for r in rows
    ]
    local = model_space.select(fits, crit_name, thresh, decisive_w)
    if any(r.get("n_flat") for r in rows):
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note="structurally flat directions (an indicator — AIC and BIC charge "
            "every estimated parameter): "
            + "; ".join(
                f"{r['id']} {r['n_est']} estimated, {r['n_flat']} structurally flat"
                for r in rows
                if r.get("n_flat")
            ),
        )
    by_id = {m["model_id"]: m for m in local["models"]}
    for r in rows:
        m = by_id[r["id"]]
        r["criterion"] = crit_name
        r["value"] = round(float(m["value"]), 6)
        r["delta"] = round(float(m["delta"]), 3)
        r["weight"] = round(float(m["weight"]), 4)
    run_gate_set(
        [_comparability_gate(comparability)],
        ctx.gates,
        ctx.ledger,
        "evaluation",
        round_idx=ctx.round_idx,
    )

    winner, indist, decisive = (
        local["winner"],
        local["indistinguishable"],
        local["decisive"],
    )

    # PEtab Select: the interchange files and the independent arithmetic
    ps_rows = [
        {
            "id": r["id"],
            "nllh": r["nllh"],
            "n_data": r["n_data"],
            "work": _tree.work_node(ctx.round, r["id"]),
            "best": r["best"],
        }
        for r in rows
    ]
    ps_summary = _selection.run_selection(
        ctx.round, ps_rows, crit_name, ledger=ctx.ledger, round_idx=ctx.round_idx
    )
    ok_x, detail_x = _selection.crosscheck(local, ps_summary, crit_name)
    xgate = GateResult(
        "evaluation_selection_crosscheck",
        "T1",
        ok_x,
        value=crit_name,
        threshold=f"|Δ| <= {_selection.TOL}",
        detail=detail_x,
    )
    run_gate_set(
        [lambda g=xgate: g],
        ctx.gates,
        ctx.ledger,
        "evaluation",
        round_idx=ctx.round_idx,
    )
    if not ok_x:
        raise ModuleFailure(
            "selection cross-check failed: petab_select and the "
            "local criterion arithmetic disagree, or petab_select "
            f"could not run — {detail_x}"
        )

    def _rel(key: str) -> str:
        """A record key relative to the round (`selection_files/<name>`)."""
        prefix = ctx.round.key + "/"
        key = str(key)
        return key[len(prefix) :] if key.startswith(prefix) else key

    core: dict = {
        "goal": "mechanism_discrimination",
        "discrimination": {
            "candidates": [{k: v for k, v in r.items() if k != "best"} for r in rows],
            "winner": winner,
            "indistinguishable": indist,
            # axes the indistinguishable set disagreed on: frozen means decided
            # or declined, never merely unlucky, so these carry into an
            # expansion round instead of being baked into its base
            "undecided_axes": local.get("undecided_axes") or [],
            # the search topology, declared rather than assumed, including this
            # round's fits (its evaluation record is not written yet); then
            # whether criterion values compare across rounds at all
            "search_topology": model_space.search_topology(
                _tried_models.declared_axes_this_run(ctx.root),
                _tried_models.models_fitted_this_run(
                    ctx.root,
                    current={
                        "round": ctx.round_idx,
                        "candidates": [
                            {k: v for k, v in r.items() if k != "best"} for r in rows
                        ],
                        "winner": winner,
                        "criterion": crit_name,
                    },
                ),
                mode=model_space.search_mode(ctx),
            ),
            "cross_round_comparability": model_space.comparability_regime(ctx.root),
            "decisive": decisive,
            "criterion": crit_name,
            "delta_aic_threshold": thresh,
            "decisive_weight_threshold": decisive_w,
            "comparability": comparability,
            "petab_select": {
                "version": ps_summary.get("version"),
                "files": {
                    k: _rel(v) for k, v in (ps_summary.get("files") or {}).items()
                },
                "model_space_sha": ps_summary.get("model_space_sha"),
                "crosscheck": detail_x,
            },
        },
        "parameters": {r["id"]: r["best"] for r in rows},
        "holdout": {
            "available": False,
            "note": "no held-out condition declared — discrimination "
            "rests on information criteria alone, stated honestly",
        },
        "misfit_evidence": _md_winner_misfit(ctx, winner),
        "noise_check": _md_winner_noise_check(ctx, winner),
    }
    # T2' per candidate, with the single-model criterion; `_rule3`: a candidate
    # that fails the held-out prediction cannot be the winner
    t2_by_cand, per_res = _md_per_candidate_t2prime(ctx, sims, rows)
    core["discrimination"]["t2prime"] = t2_by_cand
    t2prime_passed = True
    override = None
    if sims:
        failing = {c for c, rec in t2_by_cand.items() if rec.get("passed") is False}
        verdict = _rule3(winner, fits, failing, crit_name, thresh, decisive_w)
        t2prime_passed = verdict["t2prime_passed"]
        override = verdict["override"]
        if override:
            winner, indist, decisive = (
                verdict["winner"],
                verdict["indistinguishable"],
                verdict["decisive"],
            )
            core["discrimination"].update(
                winner=winner,
                indistinguishable=indist,
                decisive=decisive,
                undecided_axes=verdict["undecided_axes"],
            )
            core["misfit_evidence"] = _md_winner_misfit(ctx, winner)
            core["noise_check"] = _md_winner_noise_check(ctx, winner)
            ctx.ledger.append(
                "note",
                module="evaluation",
                round_idx=ctx.round_idx,
                note=f"T2' outranks the criterion (Rule 3): {override['why']} — criterion winner "
                f"{override['criterion_winner']}, chosen {winner}",
                t2prime_override=override,
            )
        core["discrimination"]["t2prime_override"] = override
        core["discrimination"]["t2prime_passed"] = t2prime_passed
        core["holdout"] = _md_averaged_holdout(
            sims,
            dict(zip([r["id"] for r in rows], weights, strict=False)),
            ctx.spec,
            per_res=per_res,
        )
    else:
        core["discrimination"]["t2prime_passed"] = None  # no held-out condition

    _profile_the_winner(ctx, core, winner)
    # the three reference lists, once, from the decided winner (Rule 3 included)
    core.update(_md_computed_references(core))
    core["latent_states"] = _md_winner_latent(ctx, winner)
    core["declared_constants"] = _md_winner_declared_constants(ctx, winner)
    _join_declared_constants(core)
    core["attribution"] = _md_attribution(ctx, rows, winner)
    core["estimated_inner"] = _md_winner_inner(ctx, winner)

    (ctx.round / "evaluation_core").put(core)
    names = _problem_names(ctx.round, cand_ids)
    interp = _with_poorly_determined(
        core, _interpret_with_consistency(ctx, core, cand_ids, names=names)
    )
    gate_results = _consistency_results(core, interp, names)
    run_gate_set(
        [lambda r=r: r for r in gate_results],
        ctx.gates,
        ctx.ledger,
        "evaluation",
        round_idx=ctx.round_idx,
    )
    if any(not r.passed and r.blocking for r in gate_results):
        raise ModuleFailure("report consistency gate failed after retry")

    report = {**core, "interpretation": interp, "t2prime_passed": t2prime_passed}
    _write_report(ctx.round, report)
    (ctx.round / "report_md").put_text(_render_md_discrimination(ctx, report))
    _write_html(ctx, when="before the verdict ask")

    lines = _md_candidate_card_lines(rows, t2_by_cand)
    lines.append(
        f"winner: {winner} ({'decisive' if decisive else 'NOT decisive'}); "
        f"indistinguishable set: {indist}"
    )
    lines += _md_t2prime_card_lines(t2_by_cand, override, t2prime_passed, bool(sims))
    # the WINNER's near-bound constants, on the card that signs it off: the
    # at-bounds gate only fires AT the edge
    winner_near = next(
        (r.get("near_bounds") or [] for r in rows if r["id"] == winner), []
    )
    lines += _latent_card_lines(core)
    lines += _structural_card_lines(core)
    if winner_near:
        lines.append(
            "⚑ NEAR A BOUND on the winner (not at it, so the bounds gate is "
            "silent): "
            + ", ".join(
                f"{nb['id']} at {float(nb['position']):.0%} of its box"
                for nb in winner_near
            )
            + " — a constant pinned against its box is often the one absorbing "
            "a missing mechanism"
        )
    # the card says WHY the winner wins, not only THAT
    attr = core.get("attribution") or {}
    lines += attribution.card_lines(attr, attr.get("neutralisation") or {})
    from octomod.workflow_modules.evaluation import misfit_margins as _mm

    ev = core.get("misfit_evidence") or {}
    misfit_open = bool(ev.get("open"))
    have_round = bool(rounds_left and rounds_left > 0)
    nearest = _mm.nearest(ev)

    # Every indicator states its distance from threshold, fired or not. Compact
    # and in `always_show`, so the card's evidence cap never hides the margins
    # or the question under them.
    decision_lines: list[str] = []
    compact = _mm.card_line_compact(ev)
    if compact:
        decision_lines.append(compact)

    evidence_lines: list[str] = []
    if misfit_open:
        evidence_lines.append(
            "⚑ STRUCTURAL MISFIT INDICATORS on the selected model: "
            + "; ".join(str(r)[:110] for r in ev.get("reasons", []))
        )
    for also in ev.get("also_seen") or []:
        evidence_lines.append(f"(corroborating only, does not open the flag) {also}")

    # an agent's `revise` while the engine is about to end the run goes on the
    # card: two judgements pointing opposite ways is information
    dis = verdict_disagreement(interp["recommendation"], misfit_open, rounds_left)
    if dis:
        decision_lines.append(
            f"⚑ THE INTERPRETATION AGENT RECOMMENDS '{dis['agent_recommendation']}' "
            f"AND THE ENGINE WOULD END THE RUN — {dis['because']}, so ending is "
            f"the default. The agent read the fits and disagrees."
            + (
                " Answer with `expand: yes` to take the agent's side and buy "
                "another round."
                if dis["human_can_override"]
                else " No rounds are left, so this cannot be acted on here."
            )
        )

    # While a round remains the question is asked either way; the answer forms
    # travel in `note_forms` (printed under the consequences and written to
    # the pending gate, `pending_gate`).
    if have_round:
        decision_lines.append(
            f"ANOTHER ROUND? {_rounds.remain(rounds_left)}, and this card is "
            f"the only place to ask for one."
        )
    # profiles on request: the card says so and offers the form
    _prof_lines, _prof_forms = _profiles_card_lines(core)
    decision_lines += _prof_lines

    approved, note = humangate.ask_once(
        ctx,
        ctx.round / VERDICT_DECISION,
        "Sign off this discrimination verdict? (it is a scientific claim)",
        lines + [f"recommendation: {interp['recommendation']}"] + evidence_lines,
        module="evaluation_verdict",
        record_decline=False,
        intent=ctx.intent,
        always_show=decision_lines,
        # every gate states the consequences of both answers; the file-gate
        # payload carries them to the front end
        consequences=md_verdict_consequences(misfit_open, rounds_left, nearest),
        note_forms=(list(another_round_note_forms(True)) if have_round else [])
        + _prof_forms,
        # the documents that carry the evidence behind this claim
        documents=_verdict_documents(ctx),
    )
    if not approved:
        raise ModuleFailure("user rejected the discrimination verdict")
    if _take_profiles_request(ctx, core, note):
        return _run_md(ctx, cand_ids, rounds_left)

    requested = parse_expansion_request(note)
    gate_note.report(
        another_round_reading(note),
        note,
        ledger=ctx.ledger,
        module="evaluation_verdict",
        round_idx=ctx.round_idx,
    )
    if dis:
        # Recorded whether or not the human overrode it, because the row is
        # about the two judgements, not about who won.
        ctx.ledger.append(
            "note",
            module="evaluation_verdict",
            round_idx=ctx.round_idx,
            note=(
                f"DISAGREEMENT: interpretation agent recommended "
                f"'{dis['agent_recommendation']}' while the engine's default "
                f"was to end the run ({dis['because']}); human answered "
                f"expansion={requested}"
            ),
            misfit_open=misfit_open,
            human_expansion_request=requested,
            nearest_indicator=(nearest or {}).get("reads_as"),
            **dis,
        )
    if requested is not None:
        ctx.ledger.append(
            "note",
            module="evaluation_verdict",
            round_idx=ctx.round_idx,
            note=(
                "human asked for another expansion round"
                if requested
                else "human declined another expansion round"
            )
            + f" (misfit_open={misfit_open}, rounds_left={_rounds.as_record(rounds_left)})",
            human_expansion_request=requested,
        )
    ctx.set_marker(
        "s7", recommendation=interp["recommendation"], winner=winner, decisive=decisive
    )
    _write_html(ctx, when="after signing")
    return report


def _swallowed(ctx: RunContext, what: str, exc: BaseException) -> None:
    """Record an exception a diagnostic deliberately absorbed.

    A diagnostic must never kill a round, but a silent absorb leaves a reader
    unable to tell a diagnostic that found nothing from one that could not run.
    Appends one ledger row naming the attempt and the exception verbatim.
    """
    ctx.ledger.append(
        "note",
        module="evaluation",
        round_idx=ctx.round_idx,
        note=f"swallowed by a diagnostic — {what}: {type(exc).__name__}: {exc}",
        swallowed=True,
    )


@timing.timed("compute", "attribution")
def _md_attribution(ctx: RunContext, rows: list[dict], winner: str) -> dict:
    """WHY the winner wins: the ΔAIC split over (observable, condition), plus
    what each mechanism term buys when switched off.

    One objective evaluation per candidate on the modules the fits already
    compiled, so the split comes from AMICI's own numbers. Writes the round's
    `attribution` record and appends a summary ledger row.
    """
    evals, n_est = {}, {}
    for r in rows:
        cid = r["id"]
        with as_candidate(ctx, cid):
            wd = ctx.work
            try:
                summary = (wd / "estimation").get()
                # the parameter term prices every estimated parameter, as the
                # criterion does, or the card's "why" line disagrees with the table
                n_est[cid] = int(r["n_est"])
                evals[cid] = attribution.evaluate_at_mle(
                    petab_io.from_work(wd, ctx.model),
                    summary,
                    ctx.cache,
                    spec=ctx.spec,
                    solver=estimation_settings.solver_overrides(ctx),
                )
            except Exception as e:  # attribution never blocks a verdict
                evals[cid] = {"available": False, "why": f"{type(e).__name__}: {e}"}
                _swallowed(ctx, f"attribution: candidate {cid} not evaluated", e)

    # the split must agree with the table the reader sees; hand it over so a
    # disagreement is recorded instead of shown as two different numbers
    dec = attribution.decompose(
        winner,
        evals,
        n_est,
        table_delta_aic={
            str(r["id"]): float(r["delta_aic"])
            for r in rows
            if r.get("delta_aic") is not None
        },
    )

    # term neutralisation, on the winner only
    axes = model_space.declared_axes(ctx)
    declared_ids = {str(a.get("id")) for a in axes}
    axes_on = [a for a in str(winner).split("+") if a in declared_ids]
    encoding = {}
    enc_node = ctx.round / "model/encoding"
    if enc_node.exists():
        try:
            encoding = enc_node.get() or {}
        except Exception as e:  # a missing record is no verdict
            encoding = {}
            _swallowed(ctx, f"attribution: {enc_node.key} unreadable", e)
    mech = attribution.mechanism_parameters(axes, axes_on, encoding)
    neut: dict = {"parameters": {}, "refused": mech.get("refused") or {}}
    base_eval = evals.get(winner) or {}
    if mech.get("usable") and base_eval.get("available"):
        with as_candidate(ctx, winner):
            wd = ctx.work
            try:
                neut = attribution.neutralise(
                    petab_io.from_work(wd, ctx.model),
                    (wd / "estimation").get(),
                    ctx.cache,
                    mech,
                    base_eval,
                    spec=ctx.spec,
                    solver=estimation_settings.solver_overrides(ctx),
                )
            except Exception as e:
                neut = {
                    "parameters": {},
                    "refused": {**(mech.get("refused") or {}), "_error": str(e)},
                }
                _swallowed(ctx, f"attribution: neutralisation of {winner} failed", e)
    elif not mech.get("usable"):
        neut["note"] = (
            "no mechanism parameter on the winner declares a usable "
            "neutral_value, so no term was switched off — declared, never guessed"
        )

    ctx.ledger.append(
        "note",
        module="evaluation",
        round_idx=ctx.round_idx,
        note=(
            "mechanism attribution: "
            + (
                f"{len(dec.get('rivals') or [])} rival(s) decomposed"
                if dec.get("available")
                else f"unavailable ({dec.get('why', '?')[:120]})"
            )
            + f"; {len(neut.get('parameters') or {})} term(s) neutralised"
        ),
    )
    # the per-point arrays go to their own record (`attribution`, a sibling
    # of the evaluation); evaluation_core carries the summary every reader
    # actually uses, within its size budget
    (ctx.round / "attribution").put(
        {
            "decomposition": dec,
            "neutralisation": neut,
            "axes_on": axes_on,
            "per_candidate": evals,
        }
    )
    out = attribution.compact(dec, neut, evals, winner)
    out["axes_on"] = axes_on
    return out


def _md_winner_misfit(ctx: RunContext, winner: str) -> dict:
    """Model-free misfit evidence for the SELECTED candidate.

    A selection round answers "which of these is best", never "is the best one
    good enough"; the two come apart exactly when the space is missing a
    mechanism, and this is the evidence an expansion round fires on.
    """
    try:
        f = fitted.load(ctx, winner)
        ev = f.misfit_evidence(ctx.spec, _fit_metrics(f.tables, f.best))
        ev["evaluated_for"] = winner
        return ev
    except Exception as e:  # a diagnostic must never kill a selection round
        return {
            "available": False,
            "open": False,
            "reasons": [],
            "error": f"{type(e).__name__}: {e}",
        }


def _md_averaged_holdout(
    sims: dict, weights: dict, spec, per_res: dict | None = None
) -> dict:
    """Per-candidate holdout metrics plus the model-AVERAGED prediction —
    multi-model inference's answer, not just the winner's. `per_res` is the
    per-candidate `_holdout_eval` result already computed for T2', so the
    held-out rows are simulated once per candidate."""
    per_candidate = {}
    averaged = {}
    for cid, (tables, hold_df, summary) in sims.items():
        res = (per_res or {}).get(cid) or _holdout_eval(
            tables,
            hold_df,
            summary["best_x_unscaled"],
            [m["x_unscaled"] for m in summary["ensemble"]],
            spec,
        )
        per_candidate[cid] = res["groups"]
        for (obs_id, cond_id), grp in hold_df.groupby(
            ["observableId", "simulationConditionId"]
        ):
            times = grp["time"].to_numpy(dtype=float)
            key = f"{obs_id}@{cond_id}"
            sim = sim_group(
                tables, str(obs_id), str(cond_id), times, summary["best_x_unscaled"]
            )
            averaged.setdefault(
                key,
                {
                    "meas": grp["measurement"].to_numpy(dtype=float),
                    "sum": np.zeros_like(times),
                },
            )
            averaged[key]["sum"] = averaged[key]["sum"] + weights[cid] * sim
    avg_groups = []
    for key, d in averaged.items():
        rng = float(np.ptp(d["meas"])) or 1.0
        rmse = float(np.sqrt(np.mean((d["meas"] - d["sum"]) ** 2)))
        avg_groups.append({"label": key, "rmse": rmse, "nrmse": rmse / rng})
    return {
        "available": True,
        "per_candidate": per_candidate,
        "model_averaged": avg_groups,
    }


def _md_per_candidate_t2prime(
    ctx: RunContext, sims: dict, rows: list
) -> tuple[dict, dict]:
    """T2' for every candidate that has a held-out table, judged exactly as the
    single-model gate judges it (`_t2prime_gate`: the assay's replicate floor
    when the data carry one, the spec threshold otherwise), persisted under the
    CANDIDATE's gates/ as `evaluation_t2prime_holdout`. Returns ({cid: record}, {cid:
    holdout evaluation}) — the second feeds the model-averaged prediction so
    the held-out rows are simulated once per candidate."""
    out: dict[str, dict] = {}
    per_res: dict[str, dict] = {}
    for cid, (tables, hold_df, summary) in sims.items():
        with as_candidate(ctx, cid):
            res = _holdout_eval(
                tables,
                hold_df,
                summary["best_x_unscaled"],
                [m["x_unscaled"] for m in summary["ensemble"]],
                ctx.spec,
            )
            per_res[cid] = res
            cand_core = {"holdout": res, "misfit_evidence": _md_winner_misfit(ctx, cid)}
            g = _t2prime_gate(cand_core, "mechanism_discrimination", ctx.spec)
            run_gate_set(
                [lambda g=g: g],
                ctx.gates,
                ctx.ledger,
                "evaluation",
                round_idx=ctx.round_idx,
            )
            worst = max(
                (grp.get("nrmse", 0.0) for grp in res.get("groups") or []), default=None
            )
            out[cid] = {
                "passed": bool(g.passed),
                "value": g.value,
                "threshold": g.threshold,
                "worst_nrmse": worst,
                "detail": g.detail,
            }
    return out, per_res


def _rule3(
    winner: str,
    fits: list[dict],
    failing: set[str],
    crit_name: str,
    thresh: float,
    decisive_w: float,
) -> dict:
    """Rule 3: T2' outranks the criterion. A candidate that fails the
    held-out prediction cannot be the winner, whatever its rank; the SAME
    criterion is then re-read over the candidates the held-out cell admits,
    and the full-set ranking stays on record as the criterion's own. Every
    candidate failing is the run's honest ending (`t2prime_passed` False), not
    a different winner. Pure — the smoke exercises every branch without a run."""
    out = {
        "winner": winner,
        "indistinguishable": None,
        "decisive": None,
        "undecided_axes": None,
        "override": None,
        "t2prime_passed": True,
    }
    eligible = [f for f in fits if f["model_id"] not in failing]
    if not eligible:
        out["t2prime_passed"] = False  # every candidate fails the held-out cell
        return out
    if winner not in failing:
        return out
    local = model_space.select(eligible, crit_name, thresh, decisive_w)
    out.update(
        winner=local["winner"],
        indistinguishable=local["indistinguishable"],
        decisive=local["decisive"],
        undecided_axes=local.get("undecided_axes") or [],
        override={
            "criterion_winner": winner,
            "chosen": local["winner"],
            "excluded_by_t2prime": sorted(failing),
            "why": (
                f"{winner} fails T2' on the held-out condition; T2' outranks the "
                f"criterion (Rule 3), so {crit_name} is re-read over the "
                f"candidates that predict the held-out cell"
            ),
        },
    )
    return out


def _md_candidate_card_lines(rows: list, t2_by_cand: dict) -> list[str]:
    """One line per candidate: the criterion numbers, and T2' beside the weight."""
    lines = []
    for r in sorted(rows, key=lambda r: r["aic"]):
        t2 = t2_by_cand.get(r["id"])
        tail = ""
        if t2 is not None:
            tail = f"  T2' {'pass' if t2['passed'] else 'FAIL'}" + (
                f" (worst nRMSE {t2['worst_nrmse']:.3f})"
                if t2.get("worst_nrmse") is not None
                else ""
            )
        lines.append(
            f"{r['id']:24s} nllh {r['nllh']:9.3f}  AIC {r['aic']:9.2f}  "
            f"dAIC {r['delta_aic']:7.2f}  weight {r['akaike_weight']:.3f}{tail}"
        )
    return lines


def _md_t2prime_card_lines(
    t2_by_cand: dict, override, t2prime_passed: bool, have_holdout: bool
) -> list[str]:
    if not have_holdout:
        return []
    lines = []
    if override:
        lines.append(
            f"⚑ T2' OUTRANKS THE CRITERION (Rule 3): {override['criterion_winner']} "
            f"ranks first but FAILS the held-out prediction — winner is "
            f"{override['chosen']}, the best-ranked candidate that predicts the "
            f"held-out cell"
        )
    if not t2prime_passed:
        lines.append(
            "⚑ EVERY candidate FAILS T2' on the held-out condition: the criterion "
            "ranking stands as a ranking, and none of these structures predicts "
            "the held-out cell — t2prime_passed is False"
        )
    for cid, t2 in t2_by_cand.items():
        if not t2.get("passed"):
            lines.append(f"  T2' detail {cid}: {str(t2.get('detail'))[:170]}")
    return lines


def _render_md_discrimination(ctx: RunContext, report: dict) -> str:
    d = report["discrimination"]
    lines = [
        f"# Mechanism discrimination report — round {ctx.round_idx}",
        "",
        f"**Question:** {ctx.intent['question']}",
        "",
        "| candidate | k | −log L | AIC | ΔAIC | Akaike weight | T2' (held-out) |",
        "|---|---|---|---|---|---|---|",
    ]
    t2 = d.get("t2prime") or {}
    for r in sorted(d["candidates"], key=lambda r: r["aic"]):
        rec = t2.get(r["id"])
        cell = (
            "—"
            if rec is None
            else ("pass" if rec.get("passed") else "FAIL")
            + (
                f" (nRMSE {rec['worst_nrmse']:.3f})"
                if rec.get("worst_nrmse") is not None
                else ""
            )
        )
        lines.append(
            f"| {r['id']} | {r['n_est']} | {r['nllh']:.3f} | "
            f"{r['aic']:.2f} | {r['delta_aic']:.2f} | {r['akaike_weight']:.3f} | {cell} |"
        )
    if d.get("t2prime_override"):
        o = d["t2prime_override"]
        lines += [
            "",
            f"**T2' outranks the criterion (Rule 3):** {o['why']} — criterion winner `{o['criterion_winner']}`, winner `{o['chosen']}`.",
        ]
    lines += [
        "",
        f"**Winner:** {d['winner']}"
        + (" — decisive" if d["decisive"] else " — **not decisive**"),
        f"**Statistically indistinguishable set** (ΔAIC < {d['delta_aic_threshold']}): "
        f"{', '.join(d['indistinguishable'])}",
        "",
        "## Interpretation",
        report["interpretation"]["diagnosis"],
        "",
        "## What the data cannot distinguish",
        ", ".join(report["interpretation"]["cannot_distinguish"]) or "nothing flagged",
        "",
        "## Nonetheless determined",
        ", ".join(report["interpretation"]["nonetheless_determined"])
        or "nothing credited",
        "",
        "## Finite but poorly determined",
        ", ".join(report["interpretation"].get("finite_but_poorly_determined") or [])
        or "nothing listed",
        "",
        f"**Recommendation:** {report['interpretation']['recommendation']}",
        "",
    ]
    return "\n".join(lines)


def sim_group(
    tables: PetabTables, obs_id: str, cond_id: str, times: np.ndarray, params: dict
) -> np.ndarray:
    sims = tables.simulate_observables(cond_id, times, param_override=params)
    return sims[obs_id]


def _fit_metrics(tables: PetabTables, best: dict) -> list[dict]:
    out = []
    for (obs_id, cond_id), grp in tables.measurements.groupby(
        ["observableId", "simulationConditionId"]
    ):
        times = grp["time"].to_numpy(dtype=float)
        meas = grp["measurement"].to_numpy(dtype=float)
        sim = sim_group(tables, str(obs_id), str(cond_id), times, best)
        res = meas - sim
        rng = np.ptp(
            tables.measurements.query("observableId == @obs_id")["measurement"]
        )
        # residual structure: lag-1 autocorrelation of time-averaged residuals
        # along the time course; a steady-state row (time inf) is not the
        # sample after the last one
        on_course = np.isfinite(times)
        tmean = (
            pd.DataFrame({"t": times[on_course], "r": res[on_course]})
            .groupby("t")["r"]
            .mean()
        )
        auto1 = (
            float(np.corrcoef(tmean[:-1], tmean[1:])[0, 1]) if len(tmean) > 2 else None
        )
        out.append(
            {
                "observable": str(obs_id),
                "condition": str(cond_id),
                "n": len(meas),
                "rmse": float(np.sqrt(np.mean(res**2))),
                "nrmse": float(np.sqrt(np.mean(res**2)) / rng) if rng > 0 else None,
                "residual_lag1_autocorr": auto1,
            }
        )
    return out


def replicate_noise_floors(long_df, cond_labels: dict | None = None) -> dict:
    """The assay's own noise, per observable LABEL, pooled over every replicate
    of every (condition, time) cell — no model involved.

    Pooled within-cell variance: sum over cells of the squared deviations from
    the cell mean, divided by the summed (n_cell − 1). Every replicate value
    counts, a cell with one value contributes nothing, and `dof` is what the
    floor's own chi-square interval is taken on. Keys: `sigma_replicate`,
    `dof`, `n_cells` (cells with ≥ 2 values), `n_values`, and `n_pairs`
    (= n_cells, kept for readers of older records).

    Training conditions only when `cond_labels` names them: the holdout stays
    sealed behind T2'.
    """
    floors: dict = {}
    if long_df is None or "replicate" not in getattr(long_df, "columns", []):
        return floors
    train_conds = set((cond_labels or {}).values()) or None
    if train_conds:
        long_df = long_df[long_df["condition_label"].isin(train_conds)]
    for label, grp in long_df.groupby("observable_label"):
        cells = grp.groupby(["condition_label", "time"])["value"]
        n = cells.count()
        multi = n[n >= 2]
        if len(multi) == 0:
            continue
        dev = cells.apply(lambda v: float(((v - v.mean()) ** 2).sum()))
        ss = float(dev.loc[multi.index].sum())
        dof = int((multi - 1).sum())
        if dof < 3:
            continue
        floors[str(label)] = {
            "sigma_replicate": float(np.sqrt(ss / dof)),
            "dof": dof,
            "n_cells": int(len(multi)),
            "n_values": int(multi.sum()),
            "n_pairs": int(len(multi)),
        }
    return floors


@timing.timed("compute", "misfit_evidence")
def structural_misfit_evidence(
    tables: PetabTables,
    best: dict,
    long_df,
    fit_metrics: list[dict],
    spec,
    obs_labels: dict | None = None,
    cond_labels: dict | None = None,
) -> dict:
    """Deterministic, model-free evidence that the STRUCTURE is wrong.

    Three signals, none of which needs ground truth, and none of which is an
    agent's opinion:

    1. sigma vs the replicate noise floor. Replicates measure the assay's own
       noise without any model. A fitted sigma above that floor means the
       likelihood bought fit by inflating noise — structural misfit absorbed
       into the error model.
    2. residual autocorrelation in time (Ljung-Box style, aggregated over
       series). Dynamics of the wrong SHAPE leave runs of same-sign residuals.
    3. chi2/dof with sigma FIXED at the replicate floor. The reported chi2/dof
       uses the ESTIMATED sigma and is therefore ~1 by construction — it can
       never reject anything. Against the model-free floor it is a real test.
    """
    from scipy import stats

    out: dict = {"available": False, "signals": {}}
    labels = obs_labels or {}
    # Read ABOVE the try: a missing threshold is a spec defect and must raise
    # here, not be swallowed into "evidence unavailable" by the guard below.
    from octomod.workflow_modules.evaluation import misfit_margins as _mm

    thr = _mm.thresholds_from_spec(spec)
    try:
        alpha = thr["alpha"]
        max_ratio = thr["max_sigma_over_floor"]
        sigmas = _resolved_sigmas(tables, best)
        per_cond_sigmas = _per_condition_sigmas(tables, best)

        # 1. replicate noise floor, per observable label; TRAINING conditions
        # only, so the holdout stays sealed behind T2'
        floors = replicate_noise_floors(long_df, cond_labels)

        inflated = []
        for obs_id, sigma in sigmas.items():
            label = labels.get(str(obs_id), str(obs_id))
            f = floors.get(label)
            # The state-dependence check comes BEFORE the finiteness guard:
            # `resolve_sigmas` returns nan for additive+proportional noise (no
            # single number is the sigma), which the guard would skip silently.
            try:
                constant = tables.sigma_is_constant(str(obs_id))
            except Exception:
                constant = True
            if not constant:
                from octomod.gates.petab_gates import sigma_components

                try:
                    comps = sigma_components(tables, str(obs_id))
                except Exception:
                    comps = []
                out["signals"].setdefault("sigma_not_constant", []).append(
                    {
                        "observable": obs_id,
                        "components": comps,
                        "note": (
                            "noise formula depends on the model state "
                            + (
                                f"({' + '.join(comps)}: a floor plus a "
                                f"signal-dependent term) "
                                if len(comps) > 1
                                else ""
                            )
                            + "; sigma-vs-floor not comparable — the per-point "
                            "sigma is in the residual diagnostics"
                        ),
                    }
                )
                continue
            if obs_id in per_cond_sigmas:
                # one sigma per condition: one record per condition, each
                # against the observable's pooled replicate floor, so a
                # control arm and a stimulated arm are judged separately
                for cid, s_c in sorted(per_cond_sigmas[obs_id].items()):
                    if not f or not np.isfinite(s_c) or s_c <= 0:
                        continue
                    n_p = int(f.get("dof") or f["n_pairs"])
                    hi = f["sigma_replicate"] * np.sqrt(
                        n_p / stats.chi2.ppf(alpha / 2, n_p)
                    )
                    ratio = s_c / f["sigma_replicate"]
                    rec = {
                        "observable": obs_id,
                        "condition": cid,
                        "sigma_fitted": round(float(s_c), 5),
                        "sigma_replicate": round(f["sigma_replicate"], 5),
                        "ratio": round(float(ratio), 3),
                        "upper_ci": round(float(hi), 5),
                        "floor_dof": n_p,
                        "floor_cells": int(f.get("n_cells") or f["n_pairs"]),
                    }
                    if ratio > max_ratio and s_c > hi:
                        inflated.append(rec)
                    out["signals"].setdefault("sigma_vs_floor", []).append(rec)
                continue
            if not f or not np.isfinite(sigma) or sigma <= 0:
                continue
            # the floor's own uncertainty, on its pooled degrees of freedom
            n_p = int(f.get("dof") or f["n_pairs"])
            hi = f["sigma_replicate"] * np.sqrt(n_p / stats.chi2.ppf(alpha / 2, n_p))
            ratio = sigma / f["sigma_replicate"]
            rec = {
                "observable": obs_id,
                "sigma_fitted": round(float(sigma), 5),
                "sigma_replicate": round(f["sigma_replicate"], 5),
                "ratio": round(float(ratio), 3),
                "upper_ci": round(float(hi), 5),
                "floor_dof": n_p,
                "floor_cells": int(f.get("n_cells") or f["n_pairs"]),
            }
            if ratio > max_ratio and sigma > hi:
                inflated.append(rec)
            out["signals"].setdefault("sigma_vs_floor", []).append(rec)

        # 2. residual autocorrelation, ONE-SIDED. A missing process leaves runs
        # of same-sign residuals, i.e. POSITIVE lag-1 autocorrelation; negative
        # autocorrelation (a model tracking noise) is no evidence to add
        # mechanism. Stouffer over series: directional, no multiplicity.
        rs = [
            (f["residual_lag1_autocorr"], f["n"])
            for f in fit_metrics
            if f.get("residual_lag1_autocorr") is not None and f.get("n")
        ]
        autocorr = None
        if rs:
            zs = [r * np.sqrt(n) for r, n in rs]
            Z = float(sum(zs) / np.sqrt(len(zs)))
            p = float(1 - stats.norm.cdf(Z))  # one-sided: positive only
            autocorr = {
                "stouffer_z": round(Z, 3),
                "n_series": len(rs),
                "p": p,
                "most_positive": round(max(r for r, _ in rs), 3),
                "n_series_positive": sum(1 for r, _ in rs if r > 0),
            }

        # 3. chi2/dof against the floor
        gof = None
        if floors:
            chi2 = 0.0
            n_pts = 0
            for f in fit_metrics:
                fl = floors.get(labels.get(str(f["observable"]), str(f["observable"])))
                if not fl or not f.get("n"):
                    continue
                chi2 += f["n"] * (f["rmse"] / fl["sigma_replicate"]) ** 2
                n_pts += f["n"]
            n_est = int((tables.parameters["estimate"] == 1).sum())
            dof = max(n_pts - n_est, 1)
            if n_pts:
                gof = {
                    "chi2": round(chi2, 1),
                    "dof": dof,
                    "chi2_per_dof": round(chi2 / dof, 3),
                    "p": float(1 - stats.chi2.cdf(chi2, dof)),
                }

        out.update(
            {
                "available": bool(floors or autocorr),
                "sigma_inflated": inflated,
                "autocorrelation": autocorr,
                "gof_at_noise_floor": gof,
                # the thresholds this round applied, beside the values they
                # judged: a number that judged a run belongs in the run
                "thresholds": dict(thr),
            }
        )
        # Two of these three can open the misfit flag on their own. The shape
        # screen cannot: its alpha is deliberately loose, so it is reported
        # always and decisive never.
        hard: list[str] = []
        soft: list[str] = []
        reasons = hard
        if inflated:
            reasons.append(
                "fitted sigma exceeds the replicate noise floor for "
                + ", ".join(f"{r['observable']} ({r['ratio']}x)" for r in inflated)
                + " — the error model is absorbing structure"
            )
        # Screening alpha, looser than the two hard tests: a missing process
        # usually shows in SOME conditions, which dilutes a combined statistic.
        ac_alpha = thr["autocorr_alpha"]
        if autocorr and autocorr["p"] < ac_alpha:
            soft.append(
                f"residuals run positive in time (Stouffer Z="
                f"{autocorr['stouffer_z']} over {autocorr['n_series']} series, "
                f"p={autocorr['p']:.2e}; most positive "
                f"{autocorr['most_positive']}) — systematic over/undershoot, "
                f"the signature of a missing process"
            )
        if gof and gof["p"] < alpha:
            hard.append(
                f"chi2/dof against the model-free noise floor is "
                f"{gof['chi2_per_dof']} (p={gof['p']:.2e}) — the fit "
                f"is worse than the assay's own repeatability"
            )
        out["open"] = bool(hard)
        # when something hard fired, the shape screen corroborates it and joins
        # the reasons; when nothing else fired it is REPORTED and nothing more,
        # because a loose screen alone is not a finding
        out["reasons"] = hard + (soft if hard else [])
        out["also_seen"] = [] if hard else soft
        # ADDITIVE: `signals` already accumulates the per-observable records
        # that section 8 and the verdict card read, so it must not be replaced
        out["signals"]["residual_shape_only"] = bool(soft and not hard)
    except Exception as e:  # a diagnostic must never kill a run
        out["error"] = f"{type(e).__name__}: {e}"
        out["open"] = False
        out["reasons"] = []
    return out


def _per_condition_sigmas(tables: PetabTables, best: dict) -> dict:
    """{observable: {condition: sigma}} where the sigma is indexed by
    condition; {} otherwise or when the tables cannot say."""
    from octomod.gates.petab_gates import per_condition_sigmas

    try:
        return per_condition_sigmas(tables, values=best)
    except Exception:
        return {}


def _resolved_sigmas(tables: PetabTables, best: dict) -> dict:
    from octomod.gates.petab_gates import resolve_sigmas

    try:
        return {k: float(v) for k, v in resolve_sigmas(tables, values=best).items()}
    except Exception:
        return {}


def _chi2_per_dof(tables: PetabTables, best: dict, summary: dict) -> float | None:

    try:
        chi2 = 0.0
        n = 0
        for (obs_id, cond_id), grp in tables.measurements.groupby(
            ["observableId", "simulationConditionId"]
        ):
            times = grp["time"].to_numpy(dtype=float)
            meas = grp["measurement"].to_numpy(dtype=float)
            sim = sim_group(tables, str(obs_id), str(cond_id), times, best)
            sig = np.maximum(
                tables.sigma_series(str(obs_id), str(cond_id), times, best), 1e-12
            )
            chi2 += float(np.sum(((meas - sim) / sig) ** 2))
            n += len(meas)
        n_est = int((tables.parameters["estimate"] == 1).sum())
        return round(chi2 / max(n - n_est, 1), 3)
    except Exception:
        return None


def _ensemble_spread(ensemble: list[dict]) -> dict[str, float]:
    if not ensemble:
        return {}
    out = {}
    for pid in ensemble[0]:
        vals = np.array([abs(m[pid]) for m in ensemble], dtype=float)
        vals = np.clip(vals, 1e-300, None)
        out[pid] = round(float(np.log10(vals.max()) - np.log10(vals.min())), 3)
    return out


@timing.timed("compute", "holdout")
def _holdout_eval(
    tables: PetabTables, hold_df: pd.DataFrame, best: dict, ensemble: list[dict], spec
) -> dict:
    """Predictive band = ensemble spread PLUS observation noise. On a
    well-identified problem the multistart ensemble collapses to a point, so
    parameter-agreement alone is NOT a predictive interval; sigma is."""

    z = float(spec.get("gates.predictive_z", 1.96))
    groups = []
    for (obs_id, cond_id), grp in hold_df.groupby(
        ["observableId", "simulationConditionId"]
    ):
        times = grp["time"].to_numpy(dtype=float)
        meas = grp["measurement"].to_numpy(dtype=float)
        sim_best = sim_group(tables, str(obs_id), str(cond_id), times, best)
        band = (
            np.array(
                [
                    sim_group(tables, str(obs_id), str(cond_id), times, m)
                    for m in ensemble
                ]
            )
            if ensemble
            else sim_best[None, :]
        )
        sig = noise_band(tables, str(obs_id), str(cond_id), times, best, z)
        lo, hi = band.min(axis=0) - sig, band.max(axis=0) + sig
        rng = float(np.ptp(meas)) or float(np.ptp(sim_best)) or 1.0
        rmse = float(np.sqrt(np.mean((meas - sim_best) ** 2)))
        groups.append(
            {
                "label": f"{obs_id}@{cond_id}",
                "n": len(meas),
                "rmse": rmse,
                "nrmse": rmse / rng,
                "band_coverage": float(
                    np.mean((meas >= lo - 1e-12) & (meas <= hi + 1e-12))
                ),
                "band_rel_width": float(np.mean(hi - lo) / rng),
            }
        )
    return {"available": True, "groups": groups}


def _profile_the_winner(ctx: RunContext, core: dict, winner: str) -> None:
    """The selected mechanism gets its identifiability assessment.

    The winner's problem lives in its own candidate group, so
    `ctx.candidate` is pointed at it and every module helper works unchanged —
    the same trick the fitting loop uses.
    """
    with as_candidate(ctx, winner):
        summary_node = ctx.work / "estimation"
        if not summary_node.exists():
            core["profiles_skipped"] = (
                f"no estimation summary for the winner {winner} — nothing to "
                f"profile"
            )
            return
        summary = summary_node.get() or {}
        n_free = len(
            [x for x in (summary.get("x_names") or []) if not str(x).startswith("_")]
        )
        # the selected mechanism's information spectrum, before the profiles:
        # its diagonal is the low end of their projection
        core["identifiability"] = _fim_screen(ctx, summary)
        _profiles_for(ctx, core, summary, "mechanism_discrimination", n_free)
        # the winner's prediction band, from the profiles that just ran
        if core.get("profiles"):
            try:
                core["prediction_uncertainty"] = _cr_band(
                    ctx,
                    core,
                    _work_tables(ctx),
                    summary,
                )
            except Exception as exc:
                ctx.ledger.append(
                    "note",
                    module="evaluation",
                    round_idx=ctx.round_idx,
                    note=f"winner prediction band failed (advisory): {exc}",
                )


def _md_winner_inner(ctx: RunContext, winner: str) -> dict:
    """The WINNER's analytically-solved parameters, or {}."""
    node = candidate_work(ctx, winner) / "estimation"
    try:
        return (node.get(None) or {}).get("estimated_inner") or {}
    except Exception:  # a missing record is no record
        return {}


def _md_winner_latent(ctx: RunContext, winner: str) -> dict:
    """The latent-state screen on the selected mechanism."""
    try:
        with as_candidate(ctx, winner):
            summary_node = ctx.work / "estimation"
            if not (ctx.work / "petab").exists() or not summary_node.exists():
                return {"conditions_checked": 0, "findings": [], "hard_failures": []}
            best = (summary_node.get() or {}).get("best_x_unscaled") or {}
            return _latent_screen(ctx, _work_tables(ctx), best)
    except Exception as exc:
        return {
            "conditions_checked": 0,
            "findings": [],
            "hard_failures": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


def _md_winner_noise_check(ctx: RunContext, winner: str) -> dict:
    """The noise-model check on the SELECTED mechanism, in its own group.

    It feeds report section 8's noise-model check and the observation-evidence
    block, which asks whether a misfit is a wrong error model rather than a
    missing process.
    """
    try:
        with as_candidate(ctx, winner):
            summary_node = ctx.work / "estimation"
            if not (ctx.work / "petab").exists() or not summary_node.exists():
                return {}
            best = (summary_node.get() or {}).get("best_x_unscaled") or {}
            if not best:
                return {}
            return _noise_model_check(_work_tables(ctx), best, ctx.spec)
    except Exception as exc:  # a diagnostic must never kill a round
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"noise-model check on the winner unavailable: "
            f"{type(exc).__name__}: {exc}",
        )
        return {}


def _md_winner_declared_constants(ctx: RunContext, winner: str) -> dict:
    """Declared constants measured on the selected mechanism, in its own
    group."""
    try:
        with as_candidate(ctx, winner):
            if not (ctx.work / "petab").exists():
                return {"declared": 0, "violated": 0, "worst_drift": None, "rows": []}
            tables = _work_tables(ctx)
            summary_node = ctx.work / "estimation"
            # the estimation record keys the optimum `best_x_unscaled` (no "best")
            best = (summary_node.get(None) or {}).get("best_x_unscaled") or {}
            # An empty `best` is NOT short-circuited to a clean record: a row that
            # could not be simulated counts as `unmeasured`, not as a constant that
            # holds.
            return _declared_constants_at_fit(ctx, tables, best)
    except Exception as exc:
        return {
            "declared": 0,
            "violated": 0,
            "worst_drift": None,
            "rows": [],
            "error": f"{type(exc).__name__}: {exc}",
        }


PROFILES_NOT_REQUESTED = (
    "not requested — profiles are computed only when asked for: `profiles` at the "
    "verdict card computes them for this model, or start the round with --profiles"
)


def _fim_diagonal(ident) -> dict:
    """{parameter: FIM_pp in scaled space} from the identifiability screen, or {}."""
    if not isinstance(ident, dict) or not ident.get("available"):
        return {}
    return dict(ident.get("diagonal_scaled") or {})


def _boxes_from_petab(
    ctx: RunContext, summary: dict, ident, names: list[str] | None = None
) -> list:
    """The free parameters' optimum, bounds and FIM diagonal, in scaled space.

    Read from the PEtab table and the estimation summary, so projecting costs no
    model build; the outer parameters only (`summary.x_names`), because the
    inner ones are solved analytically and never profiled.
    """
    par = (ctx.work / "petab/parameters").table()
    x_names = [str(x) for x in summary.get("x_names") or []]
    best = summary.get("best_x_unscaled") or {}
    diag = _fim_diagonal(ident)
    estimate = pd.to_numeric(par.get("estimate"), errors="coerce").fillna(0)
    boxes = []
    for (_, row), est in zip(par.iterrows(), estimate, strict=False):
        pid = str(row["parameterId"])
        if int(est) != 1 or pid not in best:
            continue
        if (x_names and pid not in x_names) or (names is not None and pid not in names):
            continue
        scale = row.get("parameterScale")
        scale = str(scale) if isinstance(scale, str) and scale else "lin"
        boxes.append(
            profile_projection.Box(
                pid,
                profile_projection.to_scale(best[pid], scale),
                profile_projection.to_scale(row["lowerBound"], scale),
                profile_projection.to_scale(row["upperBound"], scale),
                diag.get(pid),
            )
        )
    return boxes


def _per_point_cost(
    ctx: RunContext, profile_key: str | None = None
) -> tuple[dict | None, float | None]:
    """(what one profile point costs, the median start it is scaled from).

    The latest profiling measured in this run wins over the probe's range; it
    counts as this model's own when it was taken under the same profile
    fingerprint.
    """
    median = measured_start_s(ctx)
    if median is None:
        try:
            marker = ctx.marker("cost")
            if marker.exists():
                median = (marker.get(None) or {}).get("median_start_s")
        except Exception:  # no marker is no probe
            median = None
    latest = profile_projection.latest_timing(
        getattr(ctx, "root", None), int(getattr(ctx, "round_idx", 0) or 0)
    )
    same = bool(latest) and (
        latest.get("profile_key") == profile_key
        if profile_key or latest.get("profile_key")
        else (
            latest.get("round") == getattr(ctx, "round_idx", None)
            and latest.get("candidate") == getattr(ctx, "candidate", None)
        )
    )
    cost = profile_projection.point_cost(
        ctx.spec, float(median) if median else None, latest, same_model=same
    )
    return cost, (float(median) if median else None)


def _profile_projection(
    ctx: RunContext,
    summary: dict,
    ident=None,
    names: list[str] | None = None,
    profile_key: str | None = None,
) -> dict:
    """The projection record for profiling this model (`profile_projection.project`).

    `names` restricts it to the parameters still to profile. Profiles are
    independent per parameter and run on the engine the dearest one's high
    estimate chooses, so the wall time divides by the parameters that engine
    profiles at once. Never raises: a failure comes back as `available: False`.
    """
    from octomod.workflow_modules.estimation.problem import lr_threshold

    try:
        boxes = _boxes_from_petab(ctx, summary, ident, names)
        sched = profile_projection.schedule(
            profile_projection.profile_options(ctx.spec)
        )
        threshold = lr_threshold(0.05)
        rows = profile_projection.plan(boxes, sched, threshold)
        cost, _median = _per_point_cost(ctx, profile_key)
        engine = _profile_engine(ctx, profile_projection.one_profile_high_s(rows, cost))
        n_procs = int(getattr(engine, "n_procs", 1) or 1)
        return profile_projection.project(
            rows,
            cost,
            profile_projection.workers(n_procs, len(rows)),
            schedule=sched.as_dict(),
            threshold_nllh=round(threshold, 4),
        )
    except Exception as exc:  # a projection must never end a run
        return {"available": False, "why": f"{type(exc).__name__}: {exc}"}


def _take_profiles_request(ctx: RunContext, core: dict, note: str) -> bool:
    """`profiles` at the verdict card. True when the request was taken —
    the caller re-runs the module, which computes the profiles, re-reads the
    interpretation with them and asks the card again. The verdict answer that
    carried the request signs nothing: its record is removed FIRST, so a crash
    part-way leaves a card to answer, never a verdict signed without the
    profiles its signer asked for. Profiles a time cap stopped are continued:
    the request covers the parameters it left."""
    from octomod.orchestration.interaction import gate_note

    if not gate_note.standalone(note, ["profiles"]):
        return False
    left = profile_projection.not_profiled(core.get("profiles"))
    if (
        any(not str(k).startswith("_") for k in (core.get("profiles") or {}))
        and not left
    ):
        gate_note.report(
            gate_note.Reading(
                unread={
                    "profiles": "already computed for this model — they are in the report"
                }
            ),
            note,
            ledger=ctx.ledger,
            module="evaluation_verdict",
            round_idx=ctx.round_idx,
        )
        return False
    (ctx.round / VERDICT_DECISION).delete()
    _write_profile_decision(
        ctx,
        {
            "requested": "at the verdict card",
            "round": ctx.round_idx,
            "by": "human",
            "form": "profiles",
            **({"continues": left} if left else {}),
        },
    )
    _interpretation_pin(ctx).delete()
    reading = gate_note.Reading(read={"profiles": True})
    if str(note or "").strip().lower() != "profiles":
        reading.unread["the rest of the note"] = (
            "not acted on — the card is asked again with the profiles; answer it there"
        )
    gate_note.report(
        reading,
        note,
        ledger=ctx.ledger,
        module="evaluation_verdict",
        round_idx=ctx.round_idx,
    )
    ctx.ledger.append(
        "note",
        module="evaluation_verdict",
        round_idx=ctx.round_idx,
        note=(
            (
                f"profiles requested at the verdict card: continued for the "
                f"{len(left)} parameter(s) the time cap stopped before "
                f"({', '.join(left)}), "
                if left
                else "profiles requested at the verdict card: computed for the model "
                "being judged, "
            )
            + "the interpretation re-read with them, and the card asked again "
            "— the answer that carried the request signed nothing"
        ),
        human_decision=True,
        profiles_requested=True,
    )
    print(
        "  → profiles requested: "
        + (
            f"continuing with the {len(left)} not yet profiled"
            if left
            else "computing them for this model"
        )
        + "; the card is asked again after"
    )
    return True


def _names(names: list[str], limit: int = 12) -> str:
    shown = ", ".join(names[:limit])
    return shown + (f" and {len(names) - limit} more" if len(names) > limit else "")


def _partial_note(left: list[str]) -> str:
    """What a reuse line adds when the profiles it reuses stopped at the time cap."""
    if not left:
        return ""
    return (
        f" — not profiled: time cap — {_names(left)}; `profiles` at the verdict "
        "card continues with them"
    )


def _profiles_card_lines(core: dict) -> tuple[list[str], list[str]]:
    """(the card's line, the note form) when the profiles were not requested,
    or when a time cap stopped them before every parameter."""
    left = profile_projection.not_profiled(core.get("profiles"))
    if left:
        stop = core["profiles"]["_meta"]["not_profiled"]
        n_done = len([k for k in core["profiles"] if not str(k).startswith("_")])
        rest = profile_projection.describe(stop.get("remaining"), "projected")
        return (
            [
                f"PROFILES: stopped at the {float(stop.get('cap_s') or 0):.0f}s time "
                f"cap after {n_done} of {n_done + len(left)} parameters "
                f"({profile_projection.duration(stop.get('elapsed_s') or 0)} spent); "
                f"not profiled: time cap — {_names(left)}. `profiles` on its own "
                f"line continues with the remaining {len(left)}; {rest}. It re-reads "
                "the interpretation with them (one agent call) and asks this card again."
            ],
            [
                "profiles               continue the profiles the time cap stopped, on "
                "this model, then this card is asked again"
            ],
        )
    if core.get("profiles_skipped") != PROFILES_NOT_REQUESTED:
        return [], []
    proj = (core.get("profiles_on_request") or {}).get("projection") or {}
    cost = (
        f"; {profile_projection.describe(proj, 'projected')}"
        if proj.get("available")
        else ""
    )
    return (
        [
            "PROFILES: not computed — only on request; the FIM screen names the flat "
            f"directions. `profiles` on its own line computes them for this model{cost}. "
            "It re-reads the interpretation with them (one agent call) and asks this "
            "card again."
        ],
        [
            "profiles               compute profile likelihoods on this model, then this "
            "card is asked again (off unless asked)"
        ],
    )


def _profiles_for(
    ctx: RunContext,
    core: dict,
    summary: dict,
    goal: str,
    n_free: int,
) -> None:
    """Profiles on the model in `ctx.work`, one rule for every goal.

    Skipped on `--skip-profiles`, reused when already computed, and otherwise
    computed on request (`gates.profiles.on_request`; always for
    `parameter_values`) or, with that off, automatically when even the HIGH
    projection is under the spec's cost cap, and behind a gate otherwise. An
    automatic profiling stops before a batch once the time spent plus the LOW
    estimate for the rest would pass the cap; it keeps what it finished, and
    `profiles` at the verdict card continues it. A decline is LEDGERED as the
    reason profiles are absent; for `parameter_values`, whose estimates ARE the
    deliverable, it stops the run.
    """

    if not ctx.spec.get("gates.profiles_auto.enabled", True):
        core["profiles_skipped"] = "profiles disabled in the workflow spec"
        return
    # `--skip-profiles` is a ROUND decision, persisted like every other human
    # decision: S7 re-runs from the top on every resume until its verdict gate
    # is answered.
    decision = ctx.round / PROFILE_DECISION
    request = ctx.round / PROFILE_REQUEST
    why = getattr(ctx, "skip_profiles", None)
    remembered = False
    if not why and request.exists():
        try:
            why = (request.get(None) or {}).get("skipped") or None
            remembered = bool(why)
        except Exception:
            why = None
    if why:
        # the same decline the profiling gate offers, taken up front by the
        # human who typed --skip-profiles, with the same consequence per goal
        if goal == "parameter_values":
            raise ModuleFailure(
                "--skip-profiles refused: a parameter-values run cannot "
                "conclude without profiles (the estimates ARE the deliverable)"
            )
        why = str(why)
        core["profiles_skipped"] = f"skipped at the human's request: {why}"
        print(f"  profiles skipped at the human's request: {why[:120]}")
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=(
                "profiles skipped at the human's request "
                + (
                    "(decision remembered from this round): "
                    if remembered
                    else "(--skip-profiles): "
                )
                + why[:300]
            ),
            human_decision=True,
        )
        if not remembered:
            _write_profile_decision(
                ctx,
                {
                    "skipped": why,
                    "round": ctx.round_idx,
                    "by": "human",
                    "flag": "--skip-profiles",
                },
            )
        return
    # The human's request, `--profiles "<why>"` or this round's record of one
    # (the verdict card's `profiles` writes it), read before the reuse below:
    # it is what continues profiles a time cap stopped.
    requested = getattr(ctx, "request_profiles", None)
    if not requested and request.exists():
        try:
            requested = (request.get(None) or {}).get("requested") or None
        except Exception:
            requested = None
    # Profiles already computed for exactly this problem, optimum and profile
    # settings are read back (`reuse.py`), with no projection and no gate,
    # because nothing is spent. Profiles a time cap stopped are read back the
    # same way, and continued only when a human asked.
    done = None
    work = ctx.work
    profile_key, profile_parts = None, None
    try:
        profile_key, profile_parts = _reuse.profile_fingerprint(
            petab_io.from_work(work, ctx.model),
            summary,
            ctx.spec,
            solver=estimation_settings.solver_overrides(ctx),
        )
    except Exception:  # no fingerprint, no reuse: compute them
        profile_key, profile_parts = None, None
    if profile_key:
        cached = _reuse.load_profiles(work, profile_key)
        left = profile_projection.not_profiled(cached)
        if cached is not None and left and requested:
            done = cached
        elif cached is not None:
            core["profiles"] = cached
            partial = _partial_note(left)
            print(
                f"  profiles: already computed for this problem, optimum and "
                f"settings (fingerprint {profile_key}) — reused, not recomputed"
                + partial
            )
            ctx.ledger.append(
                "note",
                module="evaluation",
                round_idx=ctx.round_idx,
                note=(
                    f"profile likelihoods reused from the record's "
                    f"{(work / _reuse.PROFILES_KEY).key} "
                    f"(fingerprint {profile_key}); no projection, no gate, nothing recomputed"
                    + partial
                ),
                profiles_reused=True,
                profile_key=profile_key,
            )
            return
    # Fallback for profiles stored without a fingerprint: this round's
    # persisted report core, when it holds profiles for the same winner and
    # parameter set (a resume, or a `--from-module evaluation` re-entry).
    saved_node = ctx.round / "evaluation_core"
    if done is None and saved_node.exists():
        try:
            saved = saved_node.get(None)
        except Exception:
            saved = {}
        prof = saved.get("profiles") if isinstance(saved, dict) else None
        saved_winner = (
            (saved.get("discrimination") or {}) if isinstance(saved, dict) else {}
        ).get("winner")
        same_model = saved_winner is None or getattr(ctx, "candidate", None) in (
            None,
            saved_winner,
        )
        same_names = isinstance(prof, dict) and list(
            (prof.get("_meta") or {}).get("x_names") or []
        ) == list(summary.get("x_names") or [])
        left = profile_projection.not_profiled(prof)
        if prof and same_model and same_names and left and requested:
            done = prof
        elif prof and same_model and same_names:
            core["profiles"] = prof
            partial = _partial_note(left)
            print(
                f"  profiles reused from {saved_node.key} (computed earlier in this round)"
                + partial
            )
            ctx.ledger.append(
                "note",
                module="evaluation",
                round_idx=ctx.round_idx,
                note=f"profiles reused from {saved_node.key}: computed earlier in "
                "this round for the same model and parameter set; not recomputed"
                + partial,
            )
            return
    # Profiles run only on request (`--profiles "<why>"`, or `profiles` at the
    # verdict card); the FIM screen runs on every fit. parameter_values always
    # profiles, since the estimates are the deliverable. The request is a ROUND
    # decision, persisted beside the skip, so a resume reuses what was computed.
    flag = getattr(ctx, "request_profiles", None)
    if flag:
        _write_profile_decision(
            ctx,
            {
                "requested": str(flag),
                "round": ctx.round_idx,
                "by": "human",
                "flag": "--profiles",
            },
        )
    ident = core.get("identifiability")
    if (
        bool(ctx.spec.get("gates.profiles.on_request", True))
        and goal != "parameter_values"
        and not requested
    ):
        proj = _profile_projection(ctx, summary, ident, profile_key=profile_key)
        text = profile_projection.describe(proj)
        core["profiles_skipped"] = PROFILES_NOT_REQUESTED
        core["profiles_on_request"] = {"n_free": n_free, "projection": proj}
        print(
            "  profiles: not computed — only on request; the FIM screen names the "
            f"flat directions ({text})"
        )
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=(
                "profiles not computed: on request (gates.profiles.on_request); " + text
            ),
            profiles_on_request=True,
            projection=profile_projection.summary(proj),
        )
        return
    cap = float(ctx.spec.require("gates.profiles_auto.max_projected_s"))
    left = profile_projection.not_profiled(done)
    proj = _profile_projection(
        ctx, summary, ident, names=left or None, profile_key=profile_key
    )
    core["profiles_projection"] = proj
    text = profile_projection.describe(proj)
    low, high = proj.get("low_s"), proj.get("high_s")
    # the cap bounds only a profiling nobody asked for
    auto_cap = None

    if requested:
        # the human asked, knowing the card's projection — no second question
        what = (
            f"profiles continue at the human's request with the {len(left)} "
            f"parameter(s) the time cap stopped before ({text})"
            if left
            else f"profiles run at the human's request ({text})"
        )
        print(f"  {what}: {str(requested)[:100]}")
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"{what}: {str(requested)[:200]}",
            human_decision=True,
            projection=profile_projection.summary(proj),
        )
    elif high is not None and high <= cap:
        print(
            f"  profiles auto-run on the selected model ({text}; even the high "
            f"end is under the {cap:.0f}s auto cap)"
        )
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"auto-profiles: {text}; high end {high:.1f}s <= cap {cap}s",
            projection=profile_projection.summary(proj),
        )
        auto_cap = cap
    else:
        approved, _ = humangate.ask_once(
            ctx,
            decision,
            "Run profile likelihoods on the selected model now? "
            "(the expensive uncertainty step)",
            [
                text,
                (
                    f"the high end is over the {cap:.0f}s auto cap and the low end "
                    "under it"
                    if low is not None and low <= cap
                    else (
                        f"both ends are over the {cap:.0f}s auto cap"
                        if low is not None
                        else f"no projection in seconds, so the {cap:.0f}s auto "
                        "cap cannot be checked"
                    )
                ),
                "low end: each parameter walks the quadratic half-width the FIM "
                "at the MLE gives, capped at its bounds; high end: each walks to "
                "both bounds — the FIM does not see a flat or non-quadratic "
                "direction",
                f"parameters: {list(summary.get('x_names') or [])}",
                "without them the run has no parameter-uncertainty instrument, "
                "and the report will say so",
            ],
            module="evaluation_profiling_gate",
            # A decline the run goes ON past is recorded, because the resume
            # that answers the verdict re-runs this module; a decline that STOPS
            # the run (parameter_values) is not, so re-answering retries cleanly.
            record_decline=goal != "parameter_values",
            intent=ctx.intent,
            consequences=(
                "profile likelihoods run now on the selected model",
                (
                    "run stops — a parameter-values verdict without profiles "
                    "would be a claim without an instrument"
                    if goal == "parameter_values"
                    else "the run continues WITHOUT an uncertainty instrument, "
                    "and the report records that you declined"
                ),
            ),
        )
        if not approved:
            if goal == "parameter_values":
                raise ModuleFailure(
                    "user declined profiling; a parameter-values run cannot "
                    "conclude without it"
                )
            core["profiles_skipped"] = (
                f"declined at the profiling gate ({text}; the {cap:.0f}s auto "
                "cap was not met by the high end)"
            )
            ctx.ledger.append(
                "note",
                module="evaluation",
                round_idx=ctx.round_idx,
                note="profiles declined at the gate; recorded as the reason "
                "no uncertainty instrument is present",
            )
            return
    try:
        core["profiles"] = _profiles(
            ctx,
            summary,
            fim=ident,
            auto_cap_s=auto_cap,
            done=done,
            profile_key=profile_key,
        )
        # the projection travels with the profiles, so a report built on reused
        # ones still shows what was projected beside what was measured; a
        # continuation keeps the projection of the whole profiling
        core["profiles"].setdefault("_meta", {})["projection"] = (
            ((done or {}).get("_meta") or {}).get("projection")
        ) or profile_projection.summary(proj)
        if profile_key:
            _reuse.store_profiles(work, profile_key, profile_parts, core["profiles"])
    except Exception as e:  # an instrument that fails is reported, not fatal
        if done:
            # what the stopped profiling finished is still an instrument
            core["profiles"] = done
        core["profiles_skipped"] = f"profiling failed: {type(e).__name__}: {e}"
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"profiles failed (advisory): {e}",
        )


def _profiles(
    ctx: RunContext,
    summary: dict,
    *,
    fim: dict | None = None,
    auto_cap_s: float | None = None,
    done: dict | None = None,
    profile_key: str | None = None,
) -> dict:
    """Profile likelihoods via pyPESTO, in batches with a progress line each.

    Needs the optimize result: from memory, else the persisted multistart
    record, else a re-run of the seeded multistart; a resume says which in
    the ledger. Each batch is a `profiles` span of the time account,
    with the work the profiler did beside the time it took; the timing record
    goes to `ctx.work / profile_projection.TIMING_KEY`.

    The free parameters are profiled as many at a time as the engine has
    processes, each as two direction tasks; after each batch the measured
    per-point cost, and the ratio of measured to projected points on the
    finished parameters, re-project the rest (a `profiles_progress` ledger
    row). `done` holds profiles a time cap
    stopped earlier, kept and not recomputed. With `auto_cap_s` (profiles
    nobody asked for), a batch is not started once the time spent plus the LOW
    estimate for the rest would pass it; the parameters left are named in
    `_meta.not_profiled`. A profiling a human asked for is never stopped.
    """
    import pypesto.profile

    from octomod.workflow_modules.estimation.problem import (
        lr_threshold,
        run_multistart,
        unscale,
    )

    # `ctx.work`, not the round: identical for a single-model goal, and the
    # WINNER's own group on a discrimination round
    # the settings the fit ran with: a profile computed on other solver
    # settings than its optimum was found with starts from a point that is not
    # that solver's optimum
    problem, _, _ = estimation_settings.build(ctx)
    # keyed by candidate, like `ctx.work`: the cache holds every candidate's
    # result, and the winner must be profiled from its own optimum
    result = ctx.cache.get(ctx.candidate_key("pypesto_result"))
    if result is None:
        # a resume is a new process, so the in-memory handoff from S6 is gone:
        # read the persisted Result rather than recompute it
        from octomod.workflow_modules.estimation.problem import read_optimize_result

        result = read_optimize_result(ctx.work / "multistart")
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=(
                "optimize result not in memory (resume); "
                + (
                    "loaded from the record's multistart"
                    if result is not None
                    else "no persisted result — re-running seeded multistart"
                )
            ),
        )
    if result is None:
        # the same optimiser S6 used: recomputing an optimum with a different
        # solver than the one that found it would compare two different things
        _name, _ = resolve_optimizer(ctx.spec, ctx.work)
        result = run_multistart(
            problem,
            int(summary["n_starts"]),
            int(summary["seed"]),
            ctx.spec,
            measured_start_s(ctx),
            estimation_settings.optimizer_overrides(ctx) or None,
            optimizer_name=_name,
            purpose="multistart_rerun",
        )
    import pypesto.optimize

    from octomod.workflow_modules.estimation.optimizer_compare import (
        DEFAULT_OPTIMIZER as _DEFAULT,
    )

    # The profile re-optimises at each point, so it uses the optimiser the run
    # resolved, not fides by default; built through `estimation.build_optimizer`,
    # which accepts every optimiser name the spec does.
    from octomod.workflow_modules.estimation.problem import build_optimizer as _build

    _prof_name, _prof_why = resolve_optimizer(ctx.spec, ctx.work)
    if _prof_name != _DEFAULT:
        print(f"  profiles use {_prof_name} — {_prof_why}")
    optimizer = _build(_prof_name)
    # `o0 n6 medium` (adaptive_step_order_0, 6 restarts per point, medium
    # steps) is the robust setting of the pyPESTO profiling benchmarks,
    # github.com/Doresic/pypesto-profiling-benchmark and
    # github.com/Doresic/pypesto-profile-benchmarks; pypesto 0.6.0 has no
    # per-point restarts, so the spec declares that part unavailable.
    # Required, no code fallback: it decides identifiability.
    guess = str(ctx.spec.require("uncertainty.profile_next_guess"))
    # The step sizes go WITH the guess method: order 0 does not extrapolate, so
    # it needs larger steps than pyPESTO's defaults to cover the same range
    # (the benchmark's `medium` preset). One reader, so the projection counts
    # steps under the options the profiler runs with.
    options = profile_projection.profile_options(ctx.spec)
    threshold = lr_threshold(0.05)

    x_names_all = list(problem.x_names)
    free = [int(i) for i in problem.x_free_indices]
    kept = {k: v for k, v in (done or {}).items() if not str(k).startswith("_") and v}
    todo = [i for i in free if x_names_all[i] not in kept]
    x_hat = np.asarray(result.optimize_result.list[0].x, dtype=float)
    diag = _fim_diagonal(fim)
    rows = profile_projection.plan(
        [
            profile_projection.Box(
                x_names_all[i],
                float(x_hat[i]),
                float(problem.lb_full[i]),
                float(problem.ub_full[i]),
                diag.get(x_names_all[i]),
            )
            for i in todo
        ],
        profile_projection.schedule(options),
        threshold,
    )
    cost, median_s = _per_point_cost(ctx, profile_key)
    # one profile per free parameter, and they do not depend on each other —
    # the engine is workflow-owned exactly as it is for the multistart
    engine = _profile_engine(ctx, profile_projection.one_profile_high_s(rows, cost))
    n_procs = int(getattr(engine, "n_procs", 1) or 1)
    progress = profile_projection.Progress(
        rows,
        cost,
        n_procs,
        total=len(free),
        done_before=len(free) - len(todo),
        prior=_prior_batches(ctx.work, profile_key) if kept else [],
        median_start_s=median_s,
    )
    # Batches accumulate into ONE profile list: the first call appends a new
    # list, the later ones name it (`profile_list`), and pyPESTO fills only
    # the indices of each call. A single batch is the single call it replaces.
    list_idx = None
    stopped: list[str] = []
    for batch in profile_projection.batches(
        todo, profile_projection.batch_size(n_procs, len(todo))
    ):
        left = [x_names_all[i] for i in todo if x_names_all[i] not in progress.done]
        if auto_cap_s is not None and progress.would_pass(auto_cap_s, left):
            stopped = left
            break
        t0 = profile_projection.now()
        with timing.span(
            "compute",
            "profiles",
            n_profiles=len(batch),
            # the processes this batch keeps busy, not the engine's cap
            n_procs=profile_projection.workers(n_procs, len(batch)),
        ) as _span:
            result = pypesto.profile.parameter_profile(
                problem=problem,
                result=result,
                optimizer=optimizer,
                engine=engine,
                profile_index=batch,
                profile_list=list_idx,
                next_guess_method=guess,
                profile_options=options,
                progress_bar=False,
            )
            wall = profile_projection.now() - t0
            if list_idx is None:
                list_idx = len(result.profile_result.list) - 1
            current = result.profile_result.list[list_idx]
            _span.update(_profile_work(current, batch))
        progress.add(
            [x_names_all[i] for i in batch],
            sum(profile_projection.points_in(current[i]) for i in batch),
            wall,
            profile_projection.workers(n_procs, len(batch)),
        )
        left = [n for n in left if n not in progress.done]
        line = progress.line(left)
        print(f"  {line}")
        ctx.ledger.append(
            "profiles_progress",
            module="evaluation",
            round_idx=ctx.round_idx,
            candidate=getattr(ctx, "candidate", None),
            note=line,
            **progress.ledger_fields(left),
        )

    timing_rec = progress.timing_record(
        round=ctx.round_idx,
        candidate=getattr(ctx, "candidate", None),
        profile_key=profile_key,
        stopped=profile_projection.TIME_CAP if stopped else None,
    )
    if progress.new:
        profile_projection.write_timing(ctx.work, timing_rec)

    scales = _parameter_scales(ctx)
    records: dict = dict(kept)
    prof_list = result.profile_result.list[list_idx] if list_idx is not None else []
    for i in todo:
        prof = prof_list[i] if i < len(prof_list) else None
        if prof is None:
            continue
        name = problem.x_names[i] if i < len(problem.x_names) else f"x_{i}"
        fvals = np.asarray(prof.fval_path, dtype=float)
        xs = np.asarray(prof.x_path[i], dtype=float)
        x_full = np.asarray(prof.x_path, dtype=float)  # (n_par, n_points)
        ok = fvals <= fvals.min() + threshold
        lo_s, hi_s = float(xs[ok].min()), float(xs[ok].max())
        lb, hi_bound = float(problem.lb_full[i]), float(problem.ub_full[i])
        touches = (lo_s - lb < 1e-6 * (hi_bound - lb)) or (
            hi_bound - hi_s < 1e-6 * (hi_bound - lb)
        )
        # persist the CURVE, not just the interval — profile plots are a
        # modeller's primary non-identifiability read
        step = max(1, len(xs) // 60)
        records[name] = {
            "ci95": [
                unscale(lo_s, scales.get(name, "lin")),
                unscale(hi_s, scales.get(name, "lin")),
            ],
            "ci_finite": not touches,
            # a width is a DECADE count only on a log scale, where hi - lo is a
            # ratio; a lin-scaled CI (an offset, say) can straddle zero
            "ci_width_decades": (
                round(abs(hi_s - lo_s), 3)
                if scales.get(name) in ("log10", "log")
                else None
            ),
            "ci_width_scaled": round(abs(hi_s - lo_s), 6),
            "ci_scale": scales.get(name, "lin"),
            # Scale-free and always defined: the fraction of the prior box the
            # data left. A 1-decade CI in a 6-decade box and in a 1.2-decade box
            # are opposite situations an absolute threshold cannot tell apart.
            "ci_box_fraction": (
                round(abs(hi_s - lo_s) / (hi_bound - lb), 4) if hi_bound > lb else None
            ),
            "box_scaled": [round(lb, 6), round(hi_bound, 6)],
            "path": {
                "x_unscaled": [
                    unscale(float(v), scales.get(name, "lin")) for v in xs[::step]
                ],
                "nllh": [float(v) for v in fvals[::step]],
                "nllh_threshold": float(fvals.min() + threshold),
                # display convention: plot the LIKELIHOOD RATIO, never -logL —
                # renderers use these two fields
                "likelihood_ratio": [
                    float(np.exp(-(v - fvals.min()))) for v in fvals[::step]
                ],
                "ratio_threshold": float(np.exp(-threshold)),
                # full re-optimized vectors (scaled space, x_names order):
                # free confidence-region skeleton points for the envelope
                "x_full_scaled": [
                    [float(v) for v in x_full[:, k]]
                    for k in range(0, x_full.shape[1], step)
                ],
            },
        }
    # in the problem's own order, whichever batch or earlier call finished them
    out: dict = {n: records[n] for n in x_names_all if n in records}
    out["_meta"] = {
        "x_names": x_names_all,
        "timing": {
            k: timing_rec[k]
            for k in (
                "per_point_s",
                "points",
                "wall_s",
                "workers",
                "parameters_done",
                "parameters_total",
                "points_ratio",
            )
        },
    }
    if stopped:
        remaining = progress.remaining(stopped)
        out["_meta"]["not_profiled"] = {
            "names": stopped,
            "reason": profile_projection.TIME_CAP,
            "cap_s": float(auto_cap_s),
            "elapsed_s": round(progress.elapsed_s, 1),
            "remaining": profile_projection.summary(remaining),
        }
        n_done = len(free) - len(stopped)
        line = (
            f"profiles stopped at the {float(auto_cap_s):.0f}s time cap after "
            f"{n_done} of {len(free)} parameters "
            f"({profile_projection.duration(progress.elapsed_s)} spent): the low "
            f"estimate for the remaining {len(stopped)} would pass it "
            f"({profile_projection.describe(remaining, 'projected')}). Not "
            f"profiled: time cap — {_names(stopped)}. The finished profiles are "
            "kept and reported; `profiles` at the verdict card continues with the rest"
        )
        print(f"  ⚑ {line}")
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            candidate=getattr(ctx, "candidate", None),
            note=line,
            profiles_time_cap=True,
            not_profiled=stopped,
            cap_s=float(auto_cap_s),
            elapsed_s=round(progress.elapsed_s, 1),
            remaining=profile_projection.summary(remaining),
        )
    return out


def _profile_work(profiles, batch: list[int]) -> dict:
    """Profile points and evaluations over one batch's entries of a profile
    list: the work the profiler did, beside the time it took."""
    out = {"n_points": 0, "n_fval": 0, "n_grad": 0}
    try:
        for i in batch:
            pr = profiles[i] if i < len(profiles) else None
            if pr is None:
                continue
            path = getattr(pr, "fval_path", None)
            out["n_points"] += int(len(path)) if path is not None else 0
            for k in ("n_fval", "n_grad"):
                v = getattr(pr, k, None)
                out[k] += int(v) if isinstance(v, (int, float)) and v == v else 0
    except Exception:  # noqa: BLE001 - a reading
        pass
    return out


def _prior_batches(work, profile_key: str | None) -> list[dict]:
    """The batches an earlier, stopped profiling of this model measured.

    A continuation adds its batches to them, so the round's timing record
    (`work / profile_projection.TIMING_KEY`) and its per-point cost cover the
    whole profiling, not the last part of it.
    """
    if work is None:
        return []
    try:
        rec = (work / profile_projection.TIMING_KEY).get(None) or {}
    except Exception:  # an unreadable record is no measurement
        return []
    if not isinstance(rec, dict) or rec.get("profile_key") != profile_key:
        return []
    return [b for b in rec.get("batches") or [] if isinstance(b, dict)]


def _computed_cannot_distinguish(core: dict, spec) -> list[str]:
    """What the BLOCKING gate may insist on: only the unambiguous case.

    A profile that does NOT close ran into its box without the likelihood
    rising past the threshold, so the data did not bound that parameter. A CI
    width is a continuum, not a verdict: it is reported as a number (the width,
    and the fraction of the prior box the data left) and the interpreter
    states it rather than picking a side.
    """
    flat = set()
    if "profiles" in core:
        for pid, p in core["profiles"].items():
            if pid.startswith("_"):
                continue
            if not p["ci_finite"]:
                flat.add(pid)
    else:
        # No profiles on this round: the ensemble spread is the declared cheap
        # proxy, and it keeps its threshold because it is a different quantity
        # with no interval to close.
        thresh = float(spec.get("gates.cannot_distinguish_log10_spread", 1.0))
        for pid, spread in core["parameters"]["ensemble_log10_spread"].items():
            if spread > thresh:
                flat.add(pid)
    return sorted(flat)


def _computed_determined(core: dict, spec) -> list[str]:
    tight_w = float(spec.get("gates.tight_prediction_rel_width", 0.5))
    max_nrmse = float(spec.get("gates.holdout.max_nrmse", 0.3))
    out = []
    if core.get("holdout", {}).get("available"):
        for g in core["holdout"]["groups"]:
            if g["nrmse"] <= max_nrmse and g["band_rel_width"] <= tight_w:
                out.append(g["label"])
    if "profiles" in core:
        # The mirror of the rule above: crediting is INSISTED on only where the
        # data clearly narrowed the prior — a closed interval taking a small
        # fraction of the box. Scale-free, so it means the same thing for a
        # log-scaled rate and a linear offset. A closed profile that spans most
        # of its box is in NEITHER set: the report gives its width and the
        # interpreter says so, and no gate adjudicates it.
        frac = float(spec.get("gates.determined_box_fraction", 0.1))
        for pid, p in core["profiles"].items():
            if pid.startswith("_"):
                continue
            bf = p.get("ci_box_fraction")
            if p["ci_finite"] and bf is not None and bf <= frac:
                out.append(pid)
    return sorted(out)


def _computed_poorly_determined(core: dict, spec) -> list[str]:
    """Profiles closed on both sides whose interval spans more of the box than
    `gates.determined_box_fraction`: bounded by the data, not well determined.

    The third list beside the two the consistency gate compares, and outside
    that gate: a closed-but-wide interval is a width, not a verdict, so it is
    listed for the reader and the interpreter, and no gate insists on it.
    """
    if "profiles" not in core:
        return []
    frac = float(spec.get("gates.determined_box_fraction", 0.1))
    out = []
    for pid, p in core["profiles"].items():
        if pid.startswith("_") or not isinstance(p, dict):
            continue
        bf = p.get("ci_box_fraction")
        if p.get("ci_finite") and bf is not None and bf > frac:
            out.append(pid)
    return sorted(out)


def _md_computed_references(core: dict) -> dict[str, list[str]]:
    """A discrimination round's three reference lists, by one rule.

    They are about the MECHANISM: the indistinguishable set, or the decisive
    winner, and the winner's flat FIM combinations. None carries a
    profile-derived parameter entry, although the winner may have been
    profiled: the two gated lists never did on this path, and a third list
    built from the profiles alone would show a closed-but-wide interval while
    an open one, the stronger finding, was shown nowhere. The winner's
    profiles are reported in their own section.
    """
    disc = core.get("discrimination") or {}
    decisive = bool(disc.get("decisive"))
    indist = disc.get("indistinguishable") or []
    winner = disc.get("winner")
    return {
        "computed_cannot_distinguish": (
            [] if decisive else sorted(f"mechanism:{c}" for c in indist)
        )
        + _flat_combination_entries(core),
        "computed_nonetheless_determined": (
            [f"mechanism:{winner}"] if decisive else []
        ),
        "computed_finite_but_poorly_determined": [],
    }


def _with_poorly_determined(core: dict, interp: dict) -> dict:
    """The interpretation's third list: every computed entry, then the agent's own.

    The engine fills it rather than a gate insisting on an echo, so an agent
    that does not write the list still shows every closed-but-wide profile.
    """
    computed = list(core.get("computed_finite_but_poorly_determined") or [])
    own = [
        e
        for e in (interp.get("finite_but_poorly_determined") or [])
        if _epistemic_key(e) not in {_epistemic_key(c) for c in computed}
    ]
    interp["finite_but_poorly_determined"] = computed + own
    return interp


def _data_signals_for_interpreter(ctx: RunContext) -> dict:
    """The data-side noise findings, or {} — the interpreter reads misfit, and
    a misspecified error model is a leading explanation for misfit."""
    node = ctx.round / "data/signals"
    if not node.exists():
        return {}
    try:
        signals = node.get() or {}
    except Exception:  # a missing record is no record
        return {}
    return {
        label: rec.get("noise")
        for label, rec in (signals.get("per_observable") or {}).items()
    }


def interpreter_diagnostics_note(kinds) -> str:
    """What the interpreter is told about asking for more diagnostics.

    A function rather than a format string: the note contains literal
    `{kind, args}` braces, which `str.format` would read as a field name.
    """
    return (
        "You may request engine-run diagnostics before answering, via "
        "`requested_diagnostics: [{kind, args}]`. The two that read what this "
        "payload bounded away are residual_curve(candidate_id, observable_id, "
        "condition_id) — one series' point-by-point fit, for a series "
        "summarised here rather than drawn — and profile_path(parameter_id) — "
        "one parameter's profile-likelihood path. The whole whitelist is "
        + str(list(kinds))
        + ". Results come back under `diagnostics_requested` and you are asked "
        "again. HONEST COST: a request is one more agent call, so ask only for "
        "a curve or a path you will actually reason about in your diagnosis; "
        "the summaries here are what rank the series, and they are usually "
        "enough."
    )


def _interpret_with_requests(ctx: RunContext, context: dict, cand_ids) -> dict:
    """The interpretation call, with a diagnostics request loop around it.

    Same budget as the expansion proposer (`diagnostics.rounds`,
    `diagnostics.max_requests`). Every request round is written to the round's
    `interpretation_diagnostics`, so a resume rebuilds the context from the
    record and `call_cached` serves the answered prompt instead of paying twice.
    """
    from octomod.workflow_modules.evaluation import diagnostics as _diag

    max_rounds = int(ctx.spec.require("diagnostics.rounds"))
    _raw = ctx.spec.get("diagnostics.max_requests")  # null = no limit
    max_req = None if _raw is None else int(_raw)
    ids = [c for c in (cand_ids or []) if c] or [""]

    state_node = ctx.round / "interpretation_diagnostics"
    state = state_node.get(None) or {"steps": []}
    if not isinstance(state, dict) or not isinstance(state.get("steps"), list):
        state = {"steps": []}
    context = dict(context)
    context["diagnostics_instruction"] = interpreter_diagnostics_note(_diag.KINDS)
    if state["steps"]:
        context["diagnostics_requested"] = [
            r for st in state["steps"] for r in st.get("results") or []
        ]
    interp = ctx.call_cached("interpretation", context)
    for _ in range(len(state["steps"]), max(max_rounds, 0)):
        reqs = interp.get("requested_diagnostics") or []
        if not reqs:
            break
        print(
            f"  interpreter requested {len(reqs)} diagnostic(s): "
            + ", ".join(str(r.get("kind")) for r in reqs)
        )
        results = _diag.run_requests(ctx, ids, reqs, max_req, module="evaluation")
        state["steps"].append({"requests": reqs, "results": results})
        state_node.put(state)
        context["diagnostics_requested"] = [
            r for st in state["steps"] for r in st.get("results") or []
        ]
        interp = ctx.call_cached("interpretation", context)
    if interp.get("requested_diagnostics"):
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note=f"interpreter diagnostic request budget ({max_rounds} "
            f"round(s)) exhausted; further requests ignored",
        )
    return interp


# The interpretation accepted before the verdict gate, pinned in the record
# (under the call: `agent_calls/interpretation/pinned`) so the
# resume that answers the gate reuses it without rebuilding the prompt
# (`call_cached` compares prompts byte for byte): a verdict is signed on the
# interpretation the human was shown. A `--from-module evaluation` re-entry
# forgets the pin (round_status.MODULE_DECISIONS).
INTERPRETATION_PIN = "interpretation/pinned"  # under `ctx.agent_calls`


def _interpretation_pin(ctx: RunContext):
    """The pinned interpretation's node: `RK/agent_calls/interpretation/pinned`."""
    return ctx.agent_calls / INTERPRETATION_PIN


def _interpret_with_consistency(
    ctx: RunContext,
    core: dict,
    cand_ids: list[str] | None = None,
    names: dict | None = None,
) -> dict:
    """The interpretation, retried once (llm backend) with the exact entries
    it failed on quoted back: a computed entry it did not echo, or, given the
    problem's `names` (`_problem_names`), an identifier the problem lacks."""
    from octomod.agents import payload as _payload

    pin = _interpretation_pin(ctx)
    if pin.exists():
        try:
            pinned = pin.get(None)
        except Exception:
            pinned = None
        if isinstance(pinned, dict) and pinned.get("recommendation"):
            print(
                "  → interpretation: pinned before the verdict gate "
                "on an earlier pass — reused, no prompt rebuilt, no agent call"
            )
            ctx.ledger.append(
                "note",
                module="interpretation",
                round_idx=ctx.round_idx,
                note=(
                    "interpretation reused from the pin written before the "
                    f"verdict gate ({pin.key}); the "
                    "prompt was not rebuilt and nothing was paid"
                ),
                interpretation_pinned=True,
            )
            return pinned

    context = {
        "intent": ctx.intent,
        # the lab note: without it the interpreter reads residuals it cannot
        # attribute to a known cause
        "experiment_description": ctx.description,
        # the agent-facing view: every summary survives, the sampled profile
        # paths and prediction bands do not (agents.payload.core_for_agents)
        "report_core": _payload.core_for_agents(core),
        # compacted for the agent; this payload is never written to the
        # record, so nothing an artifact reader could want is lost
        "residual_diagnostics": _payload.for_agents(
            _interpreter_residuals(ctx, core, cand_ids)
        ),
        # what the replicates say about the error model, beside the residuals:
        # noise misspecification is a leading explanation for misfit
        "data_signals": _data_signals_for_interpreter(ctx),
        "instruction": (
            "cannot_distinguish MUST include every entry of "
            "computed_cannot_distinguish verbatim; nonetheless_determined MUST "
            "include every entry of computed_nonetheless_determined verbatim. "
            "Add interpretation beyond them where the evidence warrants. An "
            "entry written as an identifier — a parameter id, an "
            "observable@condition label, mechanism:<id> — must name one this "
            "round's problem has; write anything else in words. "
            "residual_diagnostics is the fit itself, time-resolved, with the "
            "observation-layer evidence beside it: read the SHAPE and the "
            "differential diagnosis in how_to_read_this before naming a "
            "missing mechanism; residual_diagnostics.residual_forms.summary "
            "names each residual's functional form and timescale across the "
            "conditions, the shortest account of what is still wrong. "
            "report_core.attribution splits the ΔAIC over "
            "(observable, condition) exactly and says what each mechanism term "
            "buys when switched off — narrate WHY the winner wins from THOSE "
            "numbers, naming the measurements that paid for it, rather than "
            "restating the weight. experiment_description is the lab note: "
            "how the data were produced, the artefacts and caveats it names, "
            "and the study team's decisions. Treat those decisions as given, "
            "and before attributing a residual to a missing mechanism, check "
            "whether the lab note already names its cause."
        ),
    }
    # this call sits before the verdict gate, so the resume that answers the
    # verdict would otherwise re-ask it with a byte-identical prompt
    interp = _interpret_with_requests(ctx, context, cand_ids)
    if interp.pop("_copy_computed", False):
        # test-mode stub convenience, recorded honestly
        interp["cannot_distinguish"] = core["computed_cannot_distinguish"]
        interp["nonetheless_determined"] = core["computed_nonetheless_determined"]
        ctx.ledger.append(
            "note",
            module="evaluation",
            round_idx=ctx.round_idx,
            note="stub interpretation copied computed epistemic sets",
        )
    else:
        missing_cd = _missing_epistemic(
            core["computed_cannot_distinguish"], interp["cannot_distinguish"]
        )
        missing_nd = _missing_epistemic(
            core["computed_nonetheless_determined"], interp["nonetheless_determined"]
        )
        unknown = _unknown_names(interp, names) if names is not None else []
        if (missing_cd or missing_nd or unknown) and ctx.backend == "llm":
            # Quote the exact strings back. The retry is the one chance to fix
            # an echo, so it must show what to copy rather than describe it.
            errors = []
            if missing_cd or missing_nd:
                errors.append(
                    f"Consistency failure: cannot_distinguish is missing these "
                    f"entries {missing_cd}; nonetheless_determined is missing "
                    f"these entries {missing_nd}. Copy each one into the right "
                    f"list character for character, exactly as written here, "
                    f"and then add your own interpretation as further entries."
                )
            if unknown:
                errors.append(
                    f"These entries name nothing this problem has: {unknown} — "
                    f"no parameter, observable@condition label or candidate by "
                    f"that id. Remove them, or say what you mean in words."
                )
            context["previous_attempt_errors"] = " ".join(errors)
            interp = ctx.call("interpretation", context)
    # pin the accepted interpretation for the resume that answers the verdict
    # gate; written before the gate can pause the run
    try:
        pin.put(interp)
    except Exception as e:  # a pin that cannot be written costs a call, not a run
        ctx.ledger.append(
            "note",
            module="interpretation",
            round_idx=ctx.round_idx,
            note=f"interpretation pin not written ({e}); a resume may pay again",
        )
    return interp


def _epistemic_key(entry: object) -> str:
    """The identity of ONE `cannot_distinguish` / `nonetheless_determined`
    entry, for comparing what the engine computed against what the agent
    echoed. The gate is BLOCKING, so an echo that differs only in spelling must
    not fail it. Two kinds of entry, so two rules:

    - a flat FIM combination is identified by the parameters it names
      (`identifiability.combination_key`), because a weight's spelling and a
      term's position carry no claim;
    - everything else is an IDENTIFIER — a parameter id, `mechanism:<id>`, an
      `observable@condition` label — so whitespace is removed entirely (none
      of them contains meaningful whitespace) and nothing else is touched.

    Case is deliberately NOT folded: parameter ids are case-sensitive in
    SBML/PEtab, and a gate that fails loudly on a mis-cased echo beats one
    that silently accepts an overclaim.
    """
    from octomod.workflow_modules.evaluation import identifiability

    key = identifiability.combination_key(entry)
    if key is not None:
        return key
    return "".join(str(entry).split())


def _missing_epistemic(computed: list, echoed: list) -> list[str]:
    """Computed entries the agent did not echo, AS COMPUTED — the operator and
    the retry need the string the agent should have written, not its key."""
    have = {_epistemic_key(e) for e in (echoed or [])}
    return [e for e in (computed or []) if _epistemic_key(e) not in have]


_SBML_ID = re.compile(r"""\bid=["']([A-Za-z_]\w*)["']""")
_PETAB_ID_COLUMNS = (
    "parameterId",
    "observableId",
    "conditionId",
    "simulationConditionId",
    "preequilibrationConditionId",
)
_BARE_ID = re.compile(r"[A-Za-z_]\w*")
_LABEL = re.compile(r"([A-Za-z_]\w*)\s*@\s*([A-Za-z_]\w*)")
_MECHANISM = re.compile(r"mechanism\s*:\s*(\S+)", re.I)


def _petab_ids(df: pd.DataFrame | None) -> set[str]:
    """The ids a PEtab table defines or refers to, from its id columns (as a
    column, or as the index petab indexes it by)."""
    if df is None or not len(df):
        return set()
    out: set[str] = set()
    for col in _PETAB_ID_COLUMNS:
        if col in df.columns:
            values = df[col]
        elif df.index.name == col:
            values = df.index
        else:
            continue
        out |= {str(v).strip() for v in values if not pd.isna(v) and str(v).strip()}
    return out


def _problem_names(rnd, candidates: list[str] | None = None) -> dict:
    """What an identifier in the epistemic lists may name, read from the
    round's record (`rnd`, `rounds/round_k`): every SBML id of every model in
    the round — the round's own, a discrimination round's base, each
    candidate's — and the PEtab parameter, observable and condition ids of
    every fitted problem, held-out table included (a held-out label names its
    condition). `mechanisms` are the ids `mechanism:<id>` may name: the given
    candidates and every candidate the round holds."""
    cids = list(
        dict.fromkeys([*(str(c) for c in candidates or []), *_tree.candidate_ids(rnd)])
    )
    ids: set[str] = set()
    for model in (
        _tree.model_node(rnd, None),
        rnd / "base_model",
        *(_tree.model_node(rnd, c) for c in cids),
    ):
        ids |= set(_SBML_ID.findall((model / "sbml").text("")))
    for cid in (None, *cids):
        work = _tree.work_node(rnd, cid)
        if not (work / "petab/parameters").exists():
            continue  # a candidate built but never assembled has no problem yet
        try:
            inp = petab_io.from_work(work, _tree.model_node(rnd, cid))
        except _tree.RecordMissing:
            continue  # an assembly that stopped part-way: its tables name nothing
        ids |= set(_SBML_ID.findall(inp.sbml))
        for df in (*inp.tables().values(), inp.holdout):
            ids |= _petab_ids(df)
    return {"ids": ids, "mechanisms": set(cids)}


def _unknown_names(interp: dict, names: dict) -> list[str]:
    """Epistemic entries that name something this problem does not have.

    The echo checks compare the lists with what the engine computed; an entry
    the agent ADDS is compared with nothing, so without this a parameter of a
    process the model does not contain could be credited as determined and
    signed off.

    Only what is written as an identifier is checked: a bare id, an
    `observable@condition` label, `mechanism:<id>`. Anything with words in it
    is interpretation, and interpretation is the agent's. A flat FIM
    combination (`identifiability.combination_key`) is the engine's own entry
    and passes."""
    from octomod.workflow_modules.evaluation import identifiability

    bad: list[str] = []
    for entry in list(interp.get("cannot_distinguish") or []) + list(
        interp.get("nonetheless_determined") or []
    ):
        if identifiability.combination_key(entry) is not None:
            continue
        text = str(entry).strip()
        m = _MECHANISM.fullmatch(text)
        if m:
            if m.group(1) not in names["mechanisms"]:
                bad.append(text)
            continue
        m = _LABEL.fullmatch(text)
        if m:
            if not {m.group(1), m.group(2)} <= names["ids"]:
                bad.append(text)
            continue
        if _BARE_ID.fullmatch(text) and text not in names["ids"]:
            bad.append(text)
    return list(dict.fromkeys(bad))


def _consistency_results(
    core: dict, interp: dict, names: dict | None = None
) -> list[GateResult]:
    """The two-sided echo check and the intent check — and, given the
    problem's `names` (`_problem_names`), whether every identifier the lists
    credit exists (`evaluation_names_exist`)."""
    missing_cd = _missing_epistemic(
        core["computed_cannot_distinguish"], interp["cannot_distinguish"]
    )
    missing_nd = _missing_epistemic(
        core["computed_nonetheless_determined"], interp["nonetheless_determined"]
    )
    r1 = GateResult(
        "evaluation_no_overclaim",
        "T1",
        not missing_cd,
        detail=(
            "every computed-flat parameter is declared undetermined"
            if not missing_cd
            else f"OVERCLAIM: flat but not declared: {sorted(missing_cd)}"
        ),
    )
    r2 = GateResult(
        "evaluation_no_underclaim",
        "T1",
        not missing_nd,
        detail=(
            "every computed-tight quantity is credited"
            if not missing_nd
            else f"UNDERCLAIM (over-refusal): tight but not credited: {sorted(missing_nd)}"
        ),
    )
    r3 = GateResult(
        "evaluation_answers_intent_complete",
        "T1",
        bool(interp.get("answers_intent")),
        detail=f"answers_intent has {len(interp.get('answers_intent', []))} verdicts",
    )
    if names is None:
        return [r1, r2, r3]
    unknown = _unknown_names(interp, names)
    r4 = GateResult(
        "evaluation_names_exist",
        "T1",
        not unknown,
        detail=(
            "every identifier the interpretation names exists in this problem"
            if not unknown
            else f"names what this problem does not have: {unknown} — no "
            f"parameter, observable, condition or candidate by that id"
        ),
    )
    return [r1, r2, r3, r4]


def _t2prime_gate(core: dict, goal: str, spec) -> GateResult:
    """Held-out prediction, judged against the ASSAY's own repeatability when
    the data can supply it.

    An nRMSE threshold is a number someone picked; "the prediction disagrees
    with the held-out data by more than the assay's own replicate noise" is a
    measurement. When replicate structure exists we test the second and report
    the first; without replicates we fall back to the threshold and SAY SO.
    """
    max_nrmse = float(spec.get("gates.holdout.max_nrmse", 0.3))
    alpha = float(spec.get("gates.misfit.alpha", 0.01))
    hold = core.get("holdout", {})
    if not hold.get("available"):
        return GateResult(
            "evaluation_t2prime_holdout",
            "T2prime",
            True,
            blocking=False,
            detail="held-out prediction unavailable "
            "(no held-out condition) — stated, not hidden",
        )
    worst = max(g["nrmse"] for g in hold["groups"])
    blocking = goal == "prediction"  # primary gate for the prediction goal
    labels = [g["label"] for g in hold["groups"]]

    floors = {
        f["observable"]: f
        for f in (
            core.get("misfit_evidence", {}).get("signals", {}).get("sigma_vs_floor")
            or []
        )
    }
    scored = [g for g in hold["groups"] if str(g["label"]).split("@")[0] in floors]
    if scored:
        from scipy import stats

        worst_p, worst_lbl, worst_ratio = 1.0, "", 0.0
        for g in scored:
            s_rep = floors[str(g["label"]).split("@")[0]]["sigma_replicate"]
            chi2 = g["n"] * (g["rmse"] / s_rep) ** 2
            p = float(1 - stats.chi2.cdf(chi2, g["n"]))
            g["rmse_over_noise_floor"] = round(float(g["rmse"] / s_rep), 3)
            g["p_vs_noise_floor"] = p
            if p < worst_p:
                worst_p, worst_lbl = p, g["label"]
                worst_ratio = g["rmse_over_noise_floor"]
        passed = worst_p >= alpha
        return GateResult(
            "evaluation_t2prime_holdout",
            "T2prime",
            passed,
            blocking=blocking,
            value=round(worst_p, 6),
            threshold=f"p >= {alpha}",
            detail=(
                f"held-out prediction vs the assay's replicate noise: "
                f"worst is {worst_lbl} at {worst_ratio}x the noise floor "
                f"(p={worst_p:.2e}); worst nRMSE {worst:.4f} "
                f"(reference threshold {max_nrmse}) across {labels}"
            ),
        )
    return GateResult(
        "evaluation_t2prime_holdout",
        "T2prime",
        worst <= max_nrmse,
        blocking=blocking,
        value=round(worst, 4),
        threshold=max_nrmse,
        detail=f"worst held-out nRMSE across {labels} — judged against the "
        f"spec threshold because the data carry no replicates to "
        f"measure the assay's own noise",
    )


def _render_md(ctx: RunContext, report: dict) -> str:
    intent = ctx.intent
    lines = [
        f"# Evaluation report — round {ctx.round_idx}",
        "",
        f"**Question:** {intent['question']}",
        f"**Goal:** {report['goal']}  ·  **best −log L:** {report['best_fval']:.4f}"
        f"  ·  **χ²/dof:** {report['chi2_per_dof']}",
        "",
        "## Fit per observable × condition",
        "",
        "| observable | condition | n | RMSE | nRMSE | lag-1 autocorr |",
        "|---|---|---|---|---|---|",
    ]
    for f in report["fit"]:
        nrmse = f"{f['nrmse']:.3f}" if f["nrmse"] is not None else "n/a"
        auto = (
            f"{f['residual_lag1_autocorr']:.2f}"
            if f["residual_lag1_autocorr"] is not None
            else "n/a"
        )
        lines.append(
            f"| {f['observable']} | {f['condition']} | {f['n']} | "
            f"{f['rmse']:.3f} | {nrmse} | {auto} |"
        )
    lines += ["", "## Held-out prediction (T2′)"]
    hold = report["holdout"]
    if hold.get("available"):
        lines += [
            "",
            "| held-out | n | RMSE | nRMSE | band coverage | band width |",
            "|---|---|---|---|---|---|",
        ]
        for g in hold["groups"]:
            lines.append(
                f"| {g['label']} | {g['n']} | {g['rmse']:.3f} | "
                f"{g['nrmse']:.3f} | {g['band_coverage']:.0%} | "
                f"{g['band_rel_width']:.3f} |"
            )
    else:
        lines.append(hold.get("note", ""))
    lines += [
        "",
        "## Parameters",
        "",
        "| parameter | best | ensemble spread (decades) |",
        "|---|---|---|",
    ]
    spread = report["parameters"]["ensemble_log10_spread"]
    for pid, val in report["parameters"]["best"].items():
        lines.append(f"| {pid} | {val:.4g} | {spread.get(pid, '—')} |")
    if report["parameters"]["at_bounds"]:
        lines.append(f"\n**At bounds:** {report['parameters']['at_bounds']}")
    if "profiles" in report:
        lines += [
            "",
            "## Profile likelihood CIs (95%)",
            "",
            "| parameter | CI | closed | width | of its box |",
            "|---|---|---|---|---|",
        ]
        for pid, p in report["profiles"].items():
            if pid.startswith("_"):
                continue
            w = p.get("ci_width_decades")
            width = (
                f"{w} decades"
                if w is not None
                else f"{p.get('ci_width_scaled')} ({p.get('ci_scale', 'lin')})"
            )
            bf = p.get("ci_box_fraction")
            lines.append(
                f"| {pid} | [{p['ci95'][0]:.4g}, {p['ci95'][1]:.4g}] | "
                f"{p['ci_finite']} | {width} | "
                f"{'—' if bf is None else f'{bf:.0%}'} |"
            )
        _left = profile_projection.not_profiled(report["profiles"])
        if _left:
            lines.append(
                f"\n**Not profiled: time cap** — {', '.join(_left)}. The automatic "
                "profiling stopped before them; `profiles` at the verdict card "
                "continues with them."
            )
    interp = report["interpretation"]
    lines += [
        "",
        "## What the data cannot distinguish",
        ", ".join(interp["cannot_distinguish"]) or "nothing flagged",
        "",
        "## Nonetheless determined",
        ", ".join(interp["nonetheless_determined"]) or "nothing credited",
        "",
        "## Finite but poorly determined",
        ", ".join(interp.get("finite_but_poorly_determined") or []) or "nothing listed",
        "",
        "## Diagnosis",
        interp["diagnosis"],
        "",
        "## Verdicts against the intent",
        "",
    ]
    for a in interp["answers_intent"]:
        lines.append(
            f"- **{a['verdict'].upper()}** — {a['criterion']}: {a['evidence']}"
        )
    lines += ["", f"**Recommendation:** {interp['recommendation']}", ""]
    return "\n".join(lines)
