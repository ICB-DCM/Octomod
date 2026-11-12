"""S1 gate ladder, part 2: simulates -> simulates sensibly across plausible
parameter ranges. Plus the conservation-law advisory.

roadrunner-based: no compilation, so these run BEFORE the human cost gate.
"""

from __future__ import annotations

import re

import numpy as np

from octomod.gates import GateResult, gate
from octomod.workflow_modules.model.simwrap import RRModel, SimError

# words that carry no identity in a required-entity entry
_STOP = {
    "the",
    "and",
    "for",
    "with",
    "each",
    "per",
    "all",
    "any",
    "its",
    "into",
    "from",
    "that",
    "this",
    "are",
    "via",
    "every",
    "which",
    "who",
    "what",
}


def _tokens(text) -> set[str]:
    """Content tokens of a name or a glossary line, case-folded."""
    return {
        t
        for t in re.findall(r"[a-z0-9]+", str(text or "").casefold())
        if len(t) >= 3 and t not in _STOP
    }


def required_entity_matches(sbml: str, required, glossary=None) -> dict:
    """How the intent's required entities are found in a model: `exact`, the
    ones a species id or name matches (case-folded), with `species` naming
    the species each matched; `via`, the ones matched through the glossary
    ({entity: the id whose id, name and `denotes` share at least 0.6 of its
    words}, species or parameter); `missing`, the rest. A generic word or a
    sentence-length entry never matches an id, which is why the glossary is
    read too; `model_required_entities` puts the glossary matches to the person
    to confirm."""
    import libsbml

    req = [str(r) for r in (required or [])]
    m = libsbml.readSBMLFromString(sbml).getModel()
    by_word: dict[str, str] = {}  # id or name, case-folded -> species id
    texts: dict[str, str] = {}  # entity -> id, name and glossary line
    species: set[str] = set()
    for i in range(m.getNumSpecies()):
        sp = m.getSpecies(i)
        species.add(sp.getId())
        by_word.setdefault(sp.getId().casefold(), sp.getId())
        texts[sp.getId()] = f"{sp.getId()} {sp.getName() or ''}"
        if sp.getName():
            by_word.setdefault(sp.getName().casefold(), sp.getId())
    for kind in ("species", "parameters"):
        for e in (glossary or {}).get(kind) or []:
            if isinstance(e, dict) and e.get("id"):
                eid = str(e["id"])
                texts[eid] = f"{texts.get(eid, eid)} {e.get('denotes', '')}"
    exact = [r for r in req if r.casefold() in by_word]
    via: dict[str, str] = {}
    for r in req:
        if r in exact:
            continue
        toks = _tokens(r)
        if not toks:
            continue
        best, frac = None, 0.0
        for eid, text in texts.items():
            f = len(toks & _tokens(text)) / len(toks)
            if f > frac:
                best, frac = eid, f
        if best is not None and frac >= 0.6:
            via[r] = best
    return {
        "exact": exact,
        "via": via,
        "missing": [r for r in req if r not in exact and r not in via],
        "species": {r: by_word[r.casefold()] for r in exact},
        "species_ids": sorted(species),
    }


def _relative_motion(traj: dict, species_ids) -> float:
    rel = 0.0
    for s in species_ids:
        x = np.asarray(traj[s], dtype=float)
        scale = max(float(np.max(np.abs(x))), 1e-12)
        rel = max(rel, float(np.ptp(x)) / scale)
    return rel


def make_sim_gates(
    sbml: str,
    t_end: float,
    estimated_bounds: dict[str, tuple[float, float]],
    spec,
    required_entities: list[str] | None = None,
    glossary: dict | None = None,
) -> list:
    """The S1 simulation gates, as closures sharing the model the first one loads.

    estimated_bounds: {parameter_id: (lb, ub)} for dynamic model parameters
    that will be estimated — the plausible box the optimiser will roam.
    `glossary` (the construction agent's entity glossary) lets the required-
    entity check match a name the agent spelled differently."""

    holder: dict = {}

    # Tolerances come from the spec, not roadrunner's defaults, so the T1 hard
    # stops record what they integrated at.
    rr_tol = spec.get("simulation.roadrunner") or {}

    def _settings() -> dict:
        model = holder.get("model")
        if model is None:
            return {"unavailable": "the model never loaded"}
        return {"solver": "roadrunner/cvode", **model.tolerances}

    @gate("model_simulates_nominal", "T1", integrates=True)
    def g_nominal():
        model = RRModel(sbml, rr_tol)
        holder["model"] = model
        try:
            traj = model.simulate(t_end, n_points=101)
        except SimError as e:
            return GateResult("model_simulates_nominal", "T1", False, detail=str(e))
        holder["traj"] = traj
        # Each species' min / median / max at nominal parameters, which the
        # observation agent weighs against the data's support before it
        # authors. Recorded on this gate's verdict
        # (gates/model_simulates_nominal.json) so S3 reuses this integration.
        mags = {}
        for sid in model.species_ids:
            col = np.asarray(traj[sid], dtype=float)
            col = col[np.isfinite(col)]
            if col.size:
                mags[sid] = {
                    "min": float(np.min(col)),
                    "median": float(np.median(col)),
                    "max": float(np.max(col)),
                }
        return GateResult(
            "model_simulates_nominal",
            "T1",
            True,
            value={"nominal_magnitudes": mags},
            detail=f"integrated 0..{t_end} at nominal parameters",
        )

    @gate("model_nonnegative_states", "T1", integrates=True)
    def g_nonneg():
        tol = float(spec.get("gates.sim_box.nonneg_tol", -1e-6))
        traj = holder["traj"]
        worst = min(float(np.min(traj[s])) for s in holder["model"].species_ids)
        if worst < tol:
            return GateResult(
                "model_nonnegative_states",
                "T1",
                False,
                value=worst,
                threshold=tol,
                detail="state goes negative over the horizon",
            )
        return GateResult(
            "model_nonnegative_states",
            "T1",
            True,
            value=worst,
            threshold=tol,
            detail="all states non-negative",
        )

    @gate("model_simulates_across_box", "T1", integrates=True)
    def g_box():
        """Catches the model that integrates only at the one vector the agent
        happened to try and dies as soon as the optimiser moves."""
        n_samples = int(spec.get("gates.sim_box.n_samples", 16))
        min_frac = float(spec.get("gates.sim_box.min_frac_integrable", 0.8))
        model = holder["model"]
        if not estimated_bounds:
            return GateResult(
                "model_simulates_across_box",
                "T1",
                True,
                detail="no estimated dynamic parameters; skipped",
            )
        rng = np.random.default_rng(int(spec.require("estimation.seed")))
        ids = list(estimated_bounds)
        lo = np.log10([max(estimated_bounds[p][0], 1e-12) for p in ids])
        hi = np.log10([max(estimated_bounds[p][1], 1e-12) for p in ids])
        n_ok = 0
        failures = []
        for _k in range(n_samples):
            x = 10 ** (lo + rng.random(len(ids)) * (hi - lo))
            try:
                model.simulate(
                    t_end, n_points=51, overrides=dict(zip(ids, x, strict=False))
                )
                n_ok += 1
            except SimError as e:
                if len(failures) < 2:
                    failures.append(str(e)[:100])
        frac = n_ok / n_samples
        passed = frac >= min_frac
        return GateResult(
            "model_simulates_across_box",
            "T1",
            passed,
            value=round(frac, 3),
            threshold=min_frac,
            detail=f"{n_ok}/{n_samples} log-uniform samples in bounds box integrate"
            + (f"; e.g. {failures[0]}" if failures and not passed else ""),
        )

    @gate("model_conservation_laws", "T1")
    def g_conservation():
        """Advisory: report moiety conservation classes so an unintended
        conserved total is visible before anyone wonders why a state is pinned."""
        model = holder["model"]
        try:
            S = np.asarray(model.rr.getFullStoichiometryMatrix())
            if S.size == 0:
                return GateResult(
                    "model_conservation_laws",
                    "T1",
                    True,
                    blocking=False,
                    value=0,
                    detail="no reactions -> no analysis",
                )
            u, s, vt = np.linalg.svd(S.T)
            null_dim = int(np.sum(s < 1e-10)) + max(0, S.shape[0] - len(s))
            return GateResult(
                "model_conservation_laws",
                "T1",
                True,
                blocking=False,
                value=null_dim,
                detail=f"{null_dim} conserved moiety class(es) detected "
                f"(advisory — check they are intended)",
            )
        except Exception as e:
            return GateResult(
                "model_conservation_laws",
                "T1",
                True,
                blocking=False,
                detail=f"analysis unavailable: {e}",
            )

    @gate("model_no_dynamics_screen", "T1", integrates=True)
    def g_dynamics():
        """A flat model simulates perfectly and passes every other gate while
        being scientifically dead. Advisory: a pre-perturbation baseline can be
        legitimately quiet."""
        model = holder["model"]
        rel = _relative_motion(holder["traj"], model.species_ids)
        if rel >= 1e-6:
            return GateResult(
                "model_no_dynamics_screen",
                "T1",
                True,
                blocking=False,
                value=round(rel, 8),
                detail="model responds over the horizon",
            )
        # Quiet at nominal is the standard encoding of an unstimulated base
        # (every ligand input at 0). Switch each zero-valued parameter on, one
        # at a time: if one makes the model move, the conditions will.
        zeros = [
            p
            for p, v in model.parameter_values().items()
            if v == 0.0 and p in set(model.parameter_ids)
        ][:25]
        responders: list[str] = []
        for pid in zeros:
            try:
                tr = model.simulate(t_end, n_points=51, overrides={pid: 1.0})
            except SimError:
                continue
            if _relative_motion(tr, model.species_ids) >= 1e-6:
                responders.append(pid)
                if len(responders) >= 3:
                    break
        if responders:
            detail = (
                f"quiet at nominal because its inputs are off: {len(zeros)} parameter(s) "
                f"are 0 at nominal ({', '.join(zeros[:6])}{' …' if len(zeros) > 6 else ''}); "
                f"switching {', '.join(responders)} to 1 makes it respond — the "
                f"conditions set the inputs"
            )
        else:
            detail = (
                "NO DYNAMICS at nominal parameters over the horizon"
                + (
                    ", and switching each zero-valued parameter to 1 starts none"
                    if zeros
                    else ""
                )
                + " — check that conditions actually perturb something"
            )
        return GateResult(
            "model_no_dynamics_screen",
            "T1",
            True,
            blocking=False,
            value={
                "relative_motion": round(rel, 8),
                "inputs_off": zeros,
                "responds_to": responders,
            },
            detail=detail,
        )

    @gate("model_required_entities", "T0")
    def g_required():
        """The user's named entities must be findable in the model — the
        'never silently remove user-specified biology' rule, checked. Advisory
        because the agent may legitimately rename (KinA_p -> Aa); unmatched
        names surface at the scope gate for the human to accept the mapping."""
        req = [str(r) for r in (required_entities or [])]
        if not req:
            return GateResult(
                "model_required_entities",
                "T0",
                True,
                blocking=False,
                detail="no required entities declared",
            )
        match = required_entity_matches(sbml, req, glossary)
        via, missing = match["via"], match["missing"]
        sentences = [r for r in missing if len(_tokens(r)) > 4]
        parts = []
        if via:
            parts.append(
                "matched through the glossary — confirm: "
                + "; ".join(f"{r!r} → {eid}" for r, eid in via.items())
            )
        if missing:
            parts.append(
                f"no match for {missing} — confirm the agent's naming maps to them "
                f"(or reject scope)"
            )
        if sentences:
            parts.append(
                "a required entity is best a short id or name; "
                + ", ".join(repr(r[:40]) for r in sentences)
                + " reads as a sentence"
            )
        return GateResult(
            "model_required_entities",
            "T0",
            True,
            blocking=False,
            value={"missing": missing, "via_glossary": via},
            detail=(
                "all required entities matched by id/name"
                if not parts
                else "; ".join(parts)
            ),
            advisory_findings=missing,
        )

    # Every gate that declares integrates=True must be able to say what it
    # integrated at; attached over the same list the runner walks, so a gate
    # added and marked integrating cannot miss the wiring.
    out = [g_nominal, g_nonneg, g_box, g_conservation, g_dynamics, g_required]
    for fn in out:
        if getattr(fn, "integrates", False):
            fn.solver_settings = _settings
    return out
