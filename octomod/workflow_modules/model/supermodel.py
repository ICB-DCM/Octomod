"""Supermodel encoding: candidates that differ only in the parameter table.

A parameter-neutralizable axis (e.g. an added route off at rate 0) is patched in
once, and a candidate switches it off by fixing its parameters at their declared
neutral values: one AMICI compile per structure, and exact nesting. An axis that
replaces the same reaction as another, clashes on an off-state, or fails the
simulated neutrality check is not dropped; it stays its own structure.
"""

from __future__ import annotations

import itertools
import math
import re

from octomod.orchestration.ledger import sha256_text
from octomod.workflow_modules.model.antimony_text import used_symbols
from octomod.workflow_modules.model.model_space import (
    apply_patch,
    declare_parameter,
    patch_steps,
)

NEUTRAL_FIELD = "neutral_value"

# The all-neutral supermodel must reproduce the base within a relative tolerance
# (magnitudes differ by decades) plus an absolute floor for all-zero species.
# Both integrators are tightened first, since two different SBML models step
# differently: that puts the numerical floor near 5e-10, far below 1e-6.
NEUTRALITY_RTOL = 1e-6
NEUTRALITY_ATOL = 1e-9
NEUTRALITY_SOLVER_TOL = 1e-12


# ------------------------------------------------------- neutralizability


def neutral_problem(p: dict) -> str:
    """Why this parameter cannot be neutralized, or "" when it can.

    Checks the declaration only (present, numeric, finite). Scale and bounds are
    not consulted: a log10 parameter fixed at 0 is -inf on its scale, which
    pyPESTO unscales back to 0 before AMICI sees it, and the box constrains
    estimation, not a fixed value. Whether the value neutralizes is settled by
    simulation (`neutrality_failures`).
    """
    pid = str(p.get("id", "?"))
    if NEUTRAL_FIELD not in p or p[NEUTRAL_FIELD] is None:
        return f"{pid} declares no {NEUTRAL_FIELD}"
    try:
        value = float(p[NEUTRAL_FIELD])
    except (TypeError, ValueError):
        return f"{pid} has a non-numeric {NEUTRAL_FIELD} {p[NEUTRAL_FIELD]!r}"
    if not math.isfinite(value):
        return f"{pid} has a non-finite {NEUTRAL_FIELD} {value!r}"
    return ""


def neutral_split(axis: dict) -> tuple[list[dict], list[dict]]:
    """An axis's added parameters, split into SWITCHES and INERT ones.

    A switch declares `neutral_value`, at which the axis's term vanishes. An
    inert parameter declares none because a switch makes it irrelevant (the `K`
    in `k*A/(K + A)` at `k = 0`); `neutrality_failures` checks that it is.
    Raises TypeError when `adds_parameters` holds ids rather than records.
    """
    adds = axis.get("adds_parameters") or []
    bad = [p for p in adds if not isinstance(p, dict)]
    if bad:
        raise TypeError(
            f"axis {axis.get('id')!r}: adds_parameters holds {bad[:3]} — parameter "
            f"RECORDS are needed (id, bounds, neutral_value), not ids; this is an "
            f"axis SUMMARY (tried_models.declared_axes_this_run), use "
            f"declared_axis_dicts for the axis itself"
        )
    switches = [p for p in adds if p.get(NEUTRAL_FIELD) is not None]
    inert = [p for p in adds if p.get(NEUTRAL_FIELD) is None]
    return switches, inert


def axis_neutralizable(axis: dict) -> tuple[bool, str]:
    """Can this axis be switched off by the parameter table alone?"""
    if axis.get("on_assembly_patch"):
        # an observation axis never touches the model, so it costs no compile
        # and has nothing to neutralize — it rides along either encoding
        return False, "observation axis: the model is untouched, nothing to neutralize"
    adds = axis.get("adds_parameters") or []
    if not adds:
        return False, "adds no parameter, so no parameter can turn it off"
    switches, inert = neutral_split(axis)
    if not switches:
        ids = [str(p.get("id", "?")) for p in adds]
        if len(ids) == 1:
            return False, f"{ids[0]} declares no {NEUTRAL_FIELD}"
        return False, (
            f"no {NEUTRAL_FIELD} on any of {ids}, so no parameter value "
            f"switches the axis off"
        )
    for p in switches:
        why = neutral_problem(p)
        if why:
            return False, why
    return True, ""


def fix_orphaned(
    base_antimony: str, antimony_src: str, params: list[dict]
) -> list[dict]:
    """Fix (not estimate) the parameters the base model uses and this structure
    does not.

    An axis that removes a reaction by zeroing its rate leaves the constant
    declared; estimated, it cannot affect the fit but is still charged by the
    criterion and profiles flat. Only constants the patch orphaned are touched.
    """
    lost = used_symbols(base_antimony) - used_symbols(antimony_src)
    out = []
    for p in params:
        if str(p.get("id")) in lost and p.get("estimate", True):
            p = dict(p, estimate=False, orphaned_by_structure=True)
        out.append(p)
    return out


def replaced_reactions(axis: dict) -> list[str]:
    """The reaction ids an axis's patch replaces (a patch may be a list of
    steps). Two axes that replace the same reaction cannot both be applied and
    then told apart by a parameter value."""
    rids = [
        p.get("replace_reaction") for p in patch_steps(axis.get("on_antimony_patch"))
    ]
    return [str(r).strip() for r in rids if r]


def partition(axes: list[dict]) -> dict:
    """Split the axes into the ones a supermodel can absorb and the ones that
    stay their own structures, with a reason recorded for every exclusion."""
    neutral: list[dict] = []
    separate: list[dict] = []
    why: dict[str, str] = {}
    for a in axes:
        ok, reason = axis_neutralizable(a)
        if ok:
            neutral.append(a)
        else:
            separate.append(a)
            why[str(a.get("id"))] = reason

    # Non-interference: two axes do not compose when they replace the same
    # reaction or give one parameter id different off-states.
    def exclude(group: list[dict], reason_for) -> None:
        for a in group:
            aid = str(a.get("id"))
            if a in neutral:
                neutral.remove(a)
                separate.append(a)
            why[aid] = reason_for(aid)

    by_reaction: dict[str, list[dict]] = {}
    for a in neutral:
        for rid in dict.fromkeys(replaced_reactions(a)):
            by_reaction.setdefault(rid, []).append(a)
    for rid, group in list(by_reaction.items()):
        if len(group) < 2:
            continue
        ids = [str(a.get("id")) for a in group]
        exclude(
            list(group),
            lambda aid, rid=rid, ids=ids: (
                f"replaces reaction {rid!r}, and so do {[i for i in ids if i != aid]}: "
                f"applying both leaves only the last rate law, so no parameter "
                f"value could tell them apart"
            ),
        )

    by_param: dict[str, dict[str, list[dict]]] = {}
    for a in neutral:
        # switches only: an inert parameter has no off-state to clash over
        for prm in neutral_split(a)[0]:
            by_param.setdefault(str(prm["id"]), {}).setdefault(
                repr(float(prm[NEUTRAL_FIELD])), []
            ).append(a)
    for pid, by_value in list(by_param.items()):
        if len(by_value) < 2:
            continue  # one id, one agreed off-state: fine, they compose
        clashing = [a for group in by_value.values() for a in group]
        ids = [str(a.get("id")) for a in clashing]
        values = sorted(by_value)
        exclude(
            clashing,
            lambda aid, pid=pid, vals=values, ids=ids: (
                f"declares parameter {pid!r} neutral at {vals[0]} while "
                f"{[i for i in ids if i != aid]} declare it neutral at "
                f"{vals[1:]}: one parameter cannot hold two off-states at once, "
                f"so switching one axis off would switch the other on"
            ),
        )
    order = {id(a): i for i, a in enumerate(axes)}
    neutral.sort(key=lambda a: order[id(a)])
    separate.sort(key=lambda a: order[id(a)])
    return {"neutral": neutral, "separate": separate, "why_separate": why}


# ------------------------------------------------------------- encoding


def neutralized(parameters: list[dict], off_axes: list[dict]) -> list[dict]:
    """The parameter list with every OFF axis's parameters pinned: fixed at the
    declared neutral value, not estimated. The row is rewritten rather than
    removed, because the supermodel's Antimony declares the symbol and PEtab
    must carry a value for it."""
    pinned: dict[str, tuple[str, float | None]] = {}
    for a in off_axes:
        switches, inert = neutral_split(a)
        for p in switches:
            pinned[str(p["id"])] = ("neutral", float(p[NEUTRAL_FIELD]))
        for p in inert:
            # no off-state of its own: fixed at its nominal, because estimated it
            # would be an unidentifiable dimension the criterion still charges
            nominal = p.get("nominal_value")
            pinned[str(p["id"])] = (
                "inert",
                float(nominal) if nominal is not None else None,
            )
    out = []
    for p in parameters:
        pid = str(p.get("id"))
        if pid in pinned:
            how, value = pinned[pid]
            q = dict(p)
            if value is not None:
                q["nominal_value"] = value
            q["estimate"] = False
            q["fixed_at_neutral"] = True
            if how == "inert":
                q["inert_at_neutral"] = True
            out.append(q)
        else:
            out.append(p)
    return out


def structure_key(antimony: str) -> str:
    """Names the compiled structure. Short on purpose: it appears in candidate
    records and in the report."""
    return sha256_text(antimony)[:12]


def build_structure(
    base_antimony: str,
    base_parameters: list[dict],
    axes: list[dict],
    nominal_hints: dict[str, float] | None = None,
) -> tuple[str, list[dict], bool]:
    """The base model with every axis in `axes` ON: patches applied in order,
    each added parameter declared once, and the constants the patches orphaned
    fixed (`fix_orphaned`). An observation axis touches no model text; its
    parameters still join the table. The base's own parameters are copied, so
    with no axes the result is the base exactly.

    Returns (antimony, parameters, all_applied); a patch that does not apply
    returns the base unchanged and False. `nominal_hints` (id -> value) are
    start values that override the table's nominals. Both the lattice and the
    next round's expansion base are built with this, so the two cannot drift.
    """
    hints = nominal_hints or {}
    ant = base_antimony
    params: list[dict] = []
    seen: set[str] = set()

    def take(p: dict) -> dict | None:
        pid = str(p.get("id"))
        if pid in seen:
            return None
        seen.add(pid)
        merged = dict(p)
        if hints.get(pid) is not None:
            merged["nominal_value"] = hints[pid]
        params.append(merged)
        return merged

    for p in base_parameters:
        take(p)
    for a in axes:
        if not a.get("on_assembly_patch"):
            ant, applied = apply_patch(ant, a["on_antimony_patch"])
            if not applied:
                return base_antimony, list(base_parameters), False
        for p in a.get("adds_parameters") or []:
            # an observation axis's parameter (a per-condition override, an
            # offset) is read by the PEtab tables, not the model: tagged so S1's
            # parameter-use check does not refuse it as unused
            row = dict(p, layer="assembly") if a.get("on_assembly_patch") else p
            added = take(row)
            # nor is it declared in the Antimony, where a per-condition copy
            # would collide in S3 with the model parameter of the same name
            if not a.get("on_assembly_patch"):
                ant = declare_parameter(ant, added or p)
    return ant, fix_orphaned(base_antimony, ant, params), True


def apply_all(base_antimony: str, axes: list[dict]) -> tuple[str, list[dict], bool]:
    """Apply every axis's Antimony patch and declare every parameter it adds,
    in axis order. Returns (antimony, parameters_added, all_applied)."""
    ant = base_antimony
    added: list[dict] = []
    for a in axes:
        ant, applied = apply_patch(ant, a["on_antimony_patch"])
        if not applied:
            return ant, added, False
        for p in a.get("adds_parameters") or []:
            added.append(dict(p))
            ant = declare_parameter(ant, p)
    return ant, added, True


# ------------------------------------------------------------ verification


def neutrality_failures(
    base_antimony: str,
    super_antimony: str,
    neutral_axes: list[dict],
    t_end: float,
    *,
    rtol: float = NEUTRALITY_RTOL,
    atol: float = NEUTRALITY_ATOL,
) -> list[str]:
    """The T1 check behind the encoding: with every neutralizable axis at its
    neutral values, does the supermodel reproduce the base model?

    Returns the failures, one line each, empty when the encoding holds. A
    failure means a declared neutral value does not actually neutralize — the
    axis is not off, it is merely quiet — and the lattice would then be
    comparing something other than what it says it compares.
    """
    import numpy as np

    from octomod.gates.build_gates import antimony_to_sbml
    from octomod.workflow_modules.model.simwrap import RRModel, SimError

    # switches at their neutral values; inert parameters keep their declared
    # nominal, which checks the claim that they do not matter there
    overrides = {
        str(p["id"]): float(p[NEUTRAL_FIELD])
        for a in neutral_axes
        for p in neutral_split(a)[0]
    }
    loaded = {}
    for label, src in (("base model", base_antimony), ("supermodel", super_antimony)):
        sbml, err = antimony_to_sbml(src)
        if sbml is None:
            return [f"the {label} does not build, so nothing can be checked: {err}"]
        try:
            model = RRModel(sbml)
            # compare two DIFFERENT structures, so remove the solver's own
            # step-choice difference before calling anything a mismatch
            for knob in ("relative_tolerance", "absolute_tolerance"):
                model.rr.integrator.setValue(knob, NEUTRALITY_SOLVER_TOL)
            loaded[label] = model
        except Exception as e:  # a model that will not load IS a failure
            return [f"the {label} does not load: {e}"]
    base, sup = loaded["base model"], loaded["supermodel"]
    try:
        traj_base = base.simulate(t_end)
        traj_sup = sup.simulate(t_end, overrides=overrides)
    except SimError as e:
        return [f"neutrality check could not simulate: {e}"]

    failures: list[str] = []
    shared = [s for s in base.species_ids if s in traj_sup]
    missing = [s for s in base.species_ids if s not in traj_sup]
    if missing:
        failures.append(
            f"the supermodel lost species the base model has: {missing} — "
            f"an axis patch removed rather than added"
        )
    for sid in shared:
        a, b = np.asarray(traj_base[sid]), np.asarray(traj_sup[sid])
        if a.shape != b.shape:
            failures.append(f"{sid}: {a.shape} vs {b.shape} time points")
            continue
        scale = np.maximum(np.abs(a), np.abs(b))
        err = np.abs(a - b)
        bad = err > (atol + rtol * scale)
        if bad.any():
            i = int(np.argmax(err / np.maximum(scale, atol)))
            failures.append(
                f"{sid}: worst relative difference "
                f"{float(err[i] / max(scale[i], atol)):.3e} at t="
                f"{float(traj_base['time'][i]):.4g} "
                f"(base {float(a[i]):.6g} vs neutral supermodel {float(b[i]):.6g}), "
                f"over tolerance {rtol:g}"
            )
    return failures


def _canonical_lines(antimony_src: str) -> set[str]:
    """The model as a set of statements: comments and whitespace stripped,
    duplicates collapsed. Two sources with the same set declare the same
    species, reactions, rules and values."""
    out: set[str] = set()
    for raw in antimony_src.splitlines():
        for stmt in raw.split("//", 1)[0].split(";"):
            stmt = re.sub(r"\s+", "", stmt)
            if stmt:
                out.add(stmt)
    return out


def noop_axes(base_antimony: str, axes: list[dict]) -> list[dict]:
    """Axes whose patch REPRODUCES the base: applies, changes no statement, and
    adds no parameter the base does not already declare.

    The base already carries such a mechanism, and enumerating the axis would
    duplicate every model. Returns [{"id", "why"}], in declaration order.
    """
    base_lines = _canonical_lines(base_antimony)
    base_symbols = set(re.findall(r"\b([A-Za-z_]\w*)\b", base_antimony))
    out: list[dict] = []
    for a in axes:
        if not a.get("on_antimony_patch"):
            continue
        patched, _added, applied = apply_all(base_antimony, [a])
        if not applied:
            continue
        new_params = [
            str(p.get("id"))
            for p in (a.get("adds_parameters") or [])
            if str(p.get("id")) not in base_symbols
        ]
        if new_params:
            continue
        if _canonical_lines(patched) == base_lines:
            out.append(
                {
                    "id": str(a.get("id")),
                    "why": "its patch reproduces the base model and adds no new "
                    "parameter — the base already carries this mechanism, so "
                    "the axis would only duplicate every model",
                }
            )
    return out


def verified_partition(base_antimony: str, axes: list[dict], t_end: float) -> dict:
    """`partition`, with every declared neutral value actually CHECKED.

    Per axis first, then jointly. Per axis, because a false declaration should
    cost that axis its place in the supermodel and nothing else: two honest
    axes still get one compile. Jointly, because composition can break what
    each part gets right on its own — two patches that both touch a species can
    each neutralize alone and not together.

    A failure never drops an axis: it moves back to being its own structure.
    The per-axis verdict is recorded, since the winner is later simulated at
    these same neutral values. No-op axes (`noop_axes`) are set aside first.
    """
    noop = noop_axes(base_antimony, axes)
    noop_ids = {n["id"] for n in noop}
    part = partition([a for a in axes if str(a.get("id")) not in noop_ids])
    neutral, separate, why = part["neutral"], part["separate"], part["why_separate"]
    verdicts: dict[str, dict] = {
        n["id"]: {"neutralizes": None, "noop": True, "why": n["why"]} for n in noop
    }

    still: list[dict] = []
    for a in neutral:
        aid = str(a.get("id"))
        one, _added, applied = apply_all(base_antimony, [a])
        if not applied:
            verdicts[aid] = {"neutralizes": False, "why": "its patch does not apply"}
            why[aid] = "its patch does not apply to the base model"
            separate.append(a)
            continue
        fails = neutrality_failures(base_antimony, one, [a], t_end)
        verdicts[aid] = {"neutralizes": not fails, "why": "; ".join(fails)}
        if fails:
            why[aid] = f"its declared neutral value does not neutralize it: {fails[0]}"
            separate.append(a)
        else:
            still.append(a)
    neutral = still

    joint: list[str] = []
    if len(neutral) > 1:
        sup, _added, applied = apply_all(base_antimony, neutral)
        joint = (
            neutrality_failures(base_antimony, sup, neutral, t_end)
            if applied
            else ["the combined patches do not apply to the base model"]
        )
        if joint:
            for a in neutral:
                why[str(a.get("id"))] = (
                    f"each axis neutralizes alone, but not together: {joint[0]}"
                )
            separate = separate + neutral
            neutral = []

    order = {str(a.get("id")): i for i, a in enumerate(axes)}
    neutral.sort(key=lambda a: order[str(a.get("id"))])
    separate.sort(key=lambda a: order[str(a.get("id"))])
    return {
        "neutral": neutral,
        "separate": separate,
        "noop": noop,
        "why_separate": why,
        "verification": {
            "per_axis": verdicts,
            "joint_failures": joint,
            "checked_to": {
                "rtol": NEUTRALITY_RTOL,
                "atol": NEUTRALITY_ATOL,
                "solver_tol": NEUTRALITY_SOLVER_TOL,
                "t_end": t_end,
            },
        },
    }


# ------------------------------------------------------------- enumeration


def enumerate_grouped(
    base_antimony: str,
    base_parameters: list[dict],
    axes: list[dict],
    max_models: int,
    *,
    t_end: float,
    keep_base: bool = False,
    one_at_a_time: bool = False,
) -> dict:
    """The lattice, grouped by structure.

    One structure per on/off combination of the SEPARATED axes; within each,
    every on/off combination of the neutralizable axes, differing in the
    parameter table alone. With no neutralizable axes this reduces exactly to
    the per-candidate encoding.

    `one_at_a_time`: only the base and each axis on its own, k+1 models rather
    than 2^k. `keep_base`: the member with every axis off is the base model
    itself, not the supermodel with the axes switched off, so an expansion
    round's base is the problem already compiled and fitted, which `reuse` finds.

    Returns {"models": [...], "encoding": {...}}: which axes were absorbed,
    which were separated and why, and the compiles the grouping saves.
    """
    part = verified_partition(base_antimony, axes, t_end)
    neutral, separate = part["neutral"], part["separate"]

    models: list[dict] = []
    structures: dict[str, dict] = {}
    for sep_bits in itertools.product([False, True], repeat=len(separate)):
        sep_on = [a for a, b in zip(separate, sep_bits, strict=False) if b]
        if one_at_a_time and len(sep_on) > 1:
            continue
        # the structure: the separated axes that are ON, plus every
        # neutralizable axis (present, and switched off by its parameters)
        overlay = [a["on_assembly_patch"] for a in sep_on if a.get("on_assembly_patch")]
        ant, params, ok = build_structure(
            base_antimony, base_parameters, sep_on + neutral
        )
        if not ok:
            continue
        skey = structure_key(ant)
        structures.setdefault(
            skey,
            {
                "structure_id": skey,
                "separated_axes_on": [str(a.get("id")) for a in sep_on],
                "antimony": ant,
                "absorbed_axes": [str(a.get("id")) for a in neutral],
            },
        )
        for neu_bits in itertools.product([False, True], repeat=len(neutral)):
            # by INDEX, not by value: two axes are distinguished by their id,
            # and `x not in list` would compare dicts field by field
            neu_on = [neutral[i] for i, b in enumerate(neu_bits) if b]
            neu_off = [neutral[i] for i, b in enumerate(neu_bits) if not b]
            if one_at_a_time and len(sep_on) + len(neu_on) > 1:
                continue
            cand_params = neutralized(params, neu_off)
            # DECLARATION order, not grouping order: the id appears in reports
            # and in the cross-run tried log, so it must not depend on how the
            # encoder happened to partition the axes
            on_ids = {str(a.get("id")) for a in sep_on} | {
                str(a.get("id")) for a in neu_on
            }
            ids = [str(a.get("id")) for a in axes if str(a.get("id")) in on_ids]
            models.append(
                {
                    "model_id": "base" if not ids else "+".join(ids),
                    "axes_on": ids,
                    "antimony": ant,
                    "parameters": cand_params,
                    "assembly_overlay": overlay,
                    "n_estimated": sum(
                        1 for p in cand_params if p.get("estimate", True)
                    ),
                    "structure_id": skey,
                    "encoding": "supermodel" if neutral else "separate",
                    "fixed_at_neutral": [
                        str(p["id"])
                        for a in neu_off
                        for p in (a.get("adds_parameters") or [])
                    ],
                }
            )
            if len(models) >= max_models:
                break
        if len(models) >= max_models:
            break

    if keep_base and neutral and models and not models[0]["axes_on"]:
        skey = structure_key(base_antimony)
        models[0] = {
            **models[0],
            "antimony": base_antimony,
            "parameters": list(base_parameters),
            "n_estimated": sum(1 for p in base_parameters if p.get("estimate", True)),
            "structure_id": skey,
            "encoding": "base_as_is",
            "fixed_at_neutral": [],
        }
        structures.setdefault(
            skey,
            {
                "structure_id": skey,
                "separated_axes_on": [],
                "antimony": base_antimony,
                "absorbed_axes": [],
                "why": "the base model as fitted in the previous round (keep_base)",
            },
        )
    n_structures = len({m["structure_id"] for m in models})
    return {
        "models": models,
        "encoding": {
            "kind": "supermodel" if neutral else "separate",
            "absorbed_axes": [str(a.get("id")) for a in neutral],
            "separated_axes": [str(a.get("id")) for a in separate],
            "noop_axes": part.get("noop", []),
            "why_separate": part["why_separate"],
            "verification": part["verification"],
            "structures": [structures[k] for k in sorted(structures)],
            "n_models": len(models),
            "n_structures": n_structures,
            "compiles_saved": len(models) - n_structures,
        },
    }
