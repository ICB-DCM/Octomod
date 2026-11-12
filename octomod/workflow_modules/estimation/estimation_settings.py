"""The settings a candidate's problem is built with, recorded in the run record.

    declared            `simulation.amici` in the spec
  + the ROUND's choice  the budget gate's `tighten` / `adjoint`   rounds/round_<k>/estimation_settings
  + the CANDIDATE's     a re-asked budget gate for it, and every  …/candidates/<id>/estimation_settings
                        refit bought at its convergence gate

`estimation.build_problem` applies them in that order on every build, a cache
hit included, starting from the solver as AMICI built it, so a fit runs with
what was asked, never with what an earlier module left on a live solver object.

Both records are keys of the run record, so they survive a gate pause. The
round's is `RK/estimation_settings`, the candidate's `WK/estimation_settings`
(`ctx.work`: the round's `_single`, or the candidate's group).
"""

from __future__ import annotations

import datetime

from octomod.result.node import Node

ROUND_KEY = "estimation_settings"
CANDIDATE_KEY = "estimation_settings"  # under the candidate's work group


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _round_node(ctx) -> Node:
    return ctx.round / ROUND_KEY


def _candidate_node(ctx) -> Node:
    return ctx.work / CANDIDATE_KEY


def _read(node: Node) -> dict:
    try:
        d = node.get({})
    except Exception:  # an unreadable record is an empty one
        return {}
    return d if isinstance(d, dict) else {}


def round_choice(ctx) -> dict:
    """The budget gate's recorded choice for the whole round ({} if none)."""
    return _read(_round_node(ctx))


def candidate_record(ctx) -> dict:
    return _read(_candidate_node(ctx))


def record_gate_choice(ctx, solver: dict, *, for_round: bool, note: str) -> None:
    """Record a budget-gate solver choice — for the round (the round's own
    gate) or for this candidate only (a gate re-asked for it)."""
    entry = {"solver": dict(solver), "note": str(note or "")[:300], "at": _now()}
    if for_round:
        _round_node(ctx).put({**entry, "source": "the round's budget gate"})
        return
    rec = candidate_record(ctx)
    rec["gate"] = {**entry, "source": "the budget gate re-asked for this candidate"}
    _candidate_node(ctx).put(rec)


def record_refit(ctx, overrides: dict, described: str, n_starts: int) -> dict:
    """Add a refit bought at this candidate's convergence gate: its solver and
    optimiser overrides accumulate (a second refit keeps the first's), the
    attempt count and the start count it asked for are kept. Returns the
    refit record."""
    from octomod.workflow_modules.estimation.problem import OPTIMIZER_KEYS, SOLVER_KEYS

    rec = candidate_record(ctx)
    refit = dict(rec.get("refit") or {})
    refit["attempts"] = int(refit.get("attempts") or 0) + 1
    refit["solver"] = {
        **(refit.get("solver") or {}),
        **{k: v for k, v in overrides.items() if k in SOLVER_KEYS},
    }
    refit["optimizer"] = {
        **(refit.get("optimizer") or {}),
        **{k: v for k, v in overrides.items() if k in OPTIMIZER_KEYS},
    }
    refit["n_starts"] = int(n_starts)
    refit.setdefault("history", []).append(
        {
            "attempt": refit["attempts"],
            "request": described,
            "n_starts": int(n_starts),
            "at": _now(),
        }
    )
    rec["refit"] = refit
    _candidate_node(ctx).put(rec)
    return refit


def solver_overrides(ctx) -> dict:
    """What this candidate's solver gets on top of the declared settings."""
    out = dict(round_choice(ctx).get("solver") or {})
    rec = candidate_record(ctx)
    out.update((rec.get("gate") or {}).get("solver") or {})
    out.update((rec.get("refit") or {}).get("solver") or {})
    return out


def optimizer_overrides(ctx) -> dict:
    return dict(((candidate_record(ctx).get("refit") or {}).get("optimizer")) or {})


def refit_attempts(ctx) -> int:
    return int((candidate_record(ctx).get("refit") or {}).get("attempts") or 0)


def refit_n_starts(ctx) -> int | None:
    n = (candidate_record(ctx).get("refit") or {}).get("n_starts")
    return int(n) if n else None


def build(ctx) -> tuple:
    """`build_problem` for the current candidate, with its settings — the
    problem read from the record (`petab_io.from_work`)."""
    from octomod.workflow_modules.assembly import petab_io
    from octomod.workflow_modules.estimation.problem import build_problem

    return build_problem(
        petab_io.from_work(ctx.work, ctx.model),
        ctx.cache,
        ctx.spec,
        overrides=solver_overrides(ctx),
    )
