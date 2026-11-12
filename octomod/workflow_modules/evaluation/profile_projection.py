"""What profiling a model will cost, as a range, and what it did cost.

A profile walks one free parameter away from the optimum in both directions,
re-optimising the others at every point, until the likelihood ratio drops past
its threshold or the parameter reaches its bound. The number of points depends
on how far that walk goes, and the Fisher information at the optimum knows it
only locally: a sharp quadratic minimum ends the walk near the optimum, a flat
or non-quadratic direction can run to the bound. So the projection is a range.

  LOW   each direction walks the quadratic half-width sqrt(2 thr / FIM_pp),
        capped at the bound. FIM_pp is the curvature with the other parameters
        held fixed, which is at least the profile's own curvature (the others
        re-optimise), so this is the shortest walk the quadratic picture allows.
  HIGH  each direction walks to its bound.

A walk's points follow the profiler's step schedule (`walk_points`). A point is
a warm-started local optimisation, whose cost relative to a multistart start is
not a constant either: before this run has profiled anything it is a declared
range of start costs (`gates.profiles_auto.point_cost_range`), and once it has,
the measured per-point cost replaces the range (`point_cost`). Profiling runs
in batches so the remaining time can be re-projected from that measurement
while it runs (`Progress`), with the remaining point counts scaled by the ratio
of measured to projected points on the parameters already finished; the
measurement is persisted in the record (`TIMING_KEY`) for the projections of later
rounds. pyPESTO profiles a parameter as two tasks, one per direction, so a batch
of b parameters keeps up to 2b processes busy (`workers`).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

TIMING_KEY = "profiles_timing"  # under the fitted problem's group (`ctx.work`)

PROBE = "cost probe range"
MEASURED = "measured in this run"

# A module attribute rather than a direct call, so a fixture can drive the
# batch loop on a fake clock.
now = time.perf_counter


# --------------------------------------------------------------- the schedule


def profile_options(spec):
    """The `ProfileOptions` the profiler runs with, or None for pyPESTO's defaults.

    The profiler and the projection read `uncertainty.profile_step_sizes`
    through this one function, so the projection counts steps under the
    options the profiler takes. An undeclared size keeps pyPESTO's own default.
    """
    steps = spec.get("uncertainty.profile_step_sizes") or {}
    if not steps:
        return None
    import pypesto.profile

    base = pypesto.profile.ProfileOptions()
    return pypesto.profile.ProfileOptions(
        min_step_size=float(steps.get("min_step_size", base.min_step_size)),
        default_step_size=float(steps.get("default_step_size", base.default_step_size)),
        max_step_size=float(steps.get("max_step_size", base.max_step_size)),
        step_size_factor=float(steps.get("step_size_factor", base.step_size_factor)),
    )


@dataclass(frozen=True)
class Schedule:
    """The step sizes a profile walk takes, in the optimiser's scaled space."""

    default_step: float
    min_step: float
    max_step: float
    factor: float

    def as_dict(self) -> dict:
        return {
            "default_step_size": self.default_step,
            "min_step_size": self.min_step,
            "max_step_size": self.max_step,
            "step_size_factor": self.factor,
        }


def schedule(options=None) -> Schedule:
    """The schedule of `options` (a `ProfileOptions`), or of pyPESTO's defaults."""
    if options is None:
        import pypesto.profile

        options = pypesto.profile.ProfileOptions()
    return Schedule(
        default_step=float(options.default_step_size),
        min_step=float(options.min_step_size),
        max_step=float(options.max_step_size),
        factor=float(options.step_size_factor),
    )


def walk_points(distance: float, sched: Schedule) -> int:
    """Points one direction of a profile adds to cover `distance` (scaled units).

    The first step is `default_step`; each accepted point multiplies it by
    `factor` up to `max_step`, and the walk then goes on linearly. The point
    that crosses `distance` is counted: the profiler stops after it.
    """
    if not (distance > 0) or not math.isfinite(distance):
        return 0
    step = max(sched.default_step, sched.min_step)
    covered, n = 0.0, 0
    while covered < distance:
        if step >= sched.max_step:
            # linear from here: the remainder in whole max steps
            return n + int(math.ceil((distance - covered) / sched.max_step - 1e-12))
        covered += step
        n += 1
        step = min(step * sched.factor, sched.max_step)
    return n


def profile_points(down: float, up: float, sched: Schedule) -> int:
    """Points of one parameter's profile: the optimum plus both walks."""
    return 1 + walk_points(down, sched) + walk_points(up, sched)


# --------------------------------------------------------------- the geometry


@dataclass(frozen=True)
class Box:
    """One free parameter in scaled space: its optimum, bounds and FIM diagonal."""

    name: str
    x_hat: float
    lb: float
    ub: float
    fim_pp: float | None = None


def to_scale(value: float, scale: str) -> float:
    """A value on its parameter's estimation scale (PEtab `parameterScale`)."""
    value = float(value)
    if scale == "log10":
        return math.log10(value) if value > 0 else float("-inf")
    if scale == "log":
        return math.log(value) if value > 0 else float("-inf")
    return value


def walks(box: Box, threshold: float) -> dict:
    """The low and high walk of one parameter, per direction, and the low's basis."""
    to_lb = max(0.0, box.x_hat - box.lb) if math.isfinite(box.x_hat) else 0.0
    to_ub = max(0.0, box.ub - box.x_hat) if math.isfinite(box.x_hat) else 0.0
    high = [to_lb, to_ub]
    fim = box.fim_pp
    if fim is not None and math.isfinite(float(fim)) and float(fim) > 0:
        half = math.sqrt(2.0 * threshold / float(fim))
        return {"low": [min(half, to_lb), min(half, to_ub)], "high": high, "fim": True}
    return {"low": list(high), "high": high, "fim": False}


def plan(boxes: list[Box], sched: Schedule, threshold: float) -> list[dict]:
    """Per parameter: the low and high walks and the points each takes."""
    rows = []
    for box in boxes:
        w = walks(box, threshold)
        rows.append(
            {
                "name": box.name,
                "walk_low": [round(v, 6) for v in w["low"]],
                "walk_high": [round(v, 6) for v in w["high"]],
                "points_low": profile_points(*w["low"], sched),
                "points_high": profile_points(*w["high"], sched),
                "basis": "FIM at the MLE" if w["fim"] else "bounds only",
            }
        )
    return rows


# ------------------------------------------------------------- the point cost


def point_cost(
    spec,
    median_start_s: float | None,
    timing: dict | None = None,
    same_model: bool = False,
) -> dict | None:
    """Seconds one profile point costs, as {low_s, high_s, source, detail}, or None.

    A measurement from this run wins over the probe range. On the same model it
    is taken as it is; from another round's model it is carried as a number of
    starts per point, times this model's start, within
    `gates.profiles_auto.carried_point_band`. None when neither a measurement
    nor a probed start is on file.
    """
    if timing and timing.get("per_point_s"):
        seconds = float(timing["per_point_s"])
        where = timing.get("round")
        if same_model:
            return {
                "low_s": seconds,
                "high_s": seconds,
                "source": MEASURED,
                "detail": f"{seconds:.2f} s per point, measured on this model's own profiles",
            }
        band = float(spec.get("gates.profiles_auto.carried_point_band", 0.25))
        ratio = timing.get("per_point_starts")
        if ratio and median_start_s:
            seconds = float(ratio) * float(median_start_s)
            detail = (
                f"{float(ratio):.2g} starts per point, measured in round {where}, "
                f"times this model's {float(median_start_s):.2f} s start, "
                f"± {band:.0%}"
            )
        else:
            detail = (
                f"{seconds:.2f} s per point, measured in round {where}, ± {band:.0%}"
            )
        return {
            "low_s": seconds * (1.0 - band),
            "high_s": seconds * (1.0 + band),
            "source": MEASURED,
            "detail": detail,
        }
    if median_start_s:
        lo, hi = (
            float(v)
            for v in spec.get("gates.profiles_auto.point_cost_range", [1.0, 2.0])
        )
        m = float(median_start_s)
        return {
            "low_s": lo * m,
            "high_s": hi * m,
            "source": PROBE,
            "detail": f"{lo:g}–{hi:g} × the median start ({m:.2f} s) from the cost probe",
        }
    return None


def workers(n_procs: int, n_parameters: int) -> int:
    """Processes a profiling of `n_parameters` keeps busy: at most two per parameter.

    pyPESTO profiles one parameter as two tasks, one walk per direction, so a
    batch of b parameters dispatches 2b tasks. The wall projection divides by
    this and the measured per-point cost multiplies by it, so the two agree.
    """
    return max(1, min(int(n_procs or 1), 2 * int(n_parameters or 0) or 1))


def batch_size(n_procs: int, n_parameters: int) -> int:
    """Parameters per batch: as many as the engine has processes, or fewer.

    Their 2b direction tasks give every process two walks, so one short walk
    does not leave a process idle for the rest of the batch.
    """
    return max(1, min(int(n_procs or 1), int(n_parameters or 0) or 1))


def midpoint_points(row: dict) -> float:
    """The projection's central estimate of one parameter's points."""
    return 0.5 * (float(row["points_low"]) + float(row["points_high"]))


def calibrated(rows: list[dict], ratio: float | None) -> list[dict]:
    """`rows` with both point counts scaled by the measured-to-projected `ratio`.

    The profiler's adaptive step is a line search on the rise in −log L, not a
    distance schedule, so its walks can take more points than the step schedule
    counts; the ratio measured on finished parameters carries that to the rest.
    """
    if not ratio or not (ratio > 0) or ratio == 1.0:
        return list(rows)
    return [
        {
            **r,
            "points_low": max(1, int(round(r["points_low"] * ratio))),
            "points_high": max(1, int(round(r["points_high"] * ratio))),
        }
        for r in rows
    ]


def one_profile_high_s(rows: list[dict], cost: dict | None) -> float | None:
    """The high estimate of the dearest single profile, the unit an engine dispatches."""
    if not rows or not cost:
        return None
    return max(r["points_high"] for r in rows) * float(cost["high_s"])


# ------------------------------------------------------------- the projection


def project(rows: list[dict], cost: dict | None, n_workers: int, **extra) -> dict:
    """The projection record: points, seconds per point and wall time, low and high."""
    if not rows:
        return {"available": False, "why": "no free parameter to profile", **extra}
    n_fim = sum(1 for r in rows if r["basis"] == "FIM at the MLE")
    if n_fim == len(rows):
        basis = "FIM at the MLE"
    elif n_fim == 0:
        basis = "bounds only"
    else:
        basis = f"FIM at the MLE for {n_fim} of {len(rows)} parameters, bounds only for the rest"
    points_low = sum(r["points_low"] for r in rows)
    points_high = sum(r["points_high"] for r in rows)
    record = {
        "available": True,
        "n_parameters": len(rows),
        "points_low": points_low,
        "points_high": points_high,
        "basis": basis,
        "n_fim": n_fim,
        "workers": int(n_workers),
        "per_point_low_s": None,
        "per_point_high_s": None,
        "per_point_source": None,
        "per_point_detail": None,
        "low_s": None,
        "high_s": None,
        "parameters": {
            r["name"]: {k: v for k, v in r.items() if k != "name"} for r in rows
        },
        **extra,
    }
    if cost:
        record.update(
            per_point_low_s=round(float(cost["low_s"]), 4),
            per_point_high_s=round(float(cost["high_s"]), 4),
            per_point_source=cost["source"],
            per_point_detail=cost.get("detail"),
            low_s=round(points_low * float(cost["low_s"]) / max(1, n_workers), 1),
            high_s=round(points_high * float(cost["high_s"]) / max(1, n_workers), 1),
        )
    else:
        record["why"] = "no probed start and no profile measured in this run"
    return record


def summary(record: dict | None) -> dict:
    """The record without its per-parameter rows, for a ledger row."""
    return {k: v for k, v in (record or {}).items() if k != "parameters"}


def _num(v: float) -> str:
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}".removesuffix(".0")


def duration(seconds: float) -> str:
    """`40 s`, `4.1 min`, `2.3 h`: one duration, in the unit that reads."""
    s = float(seconds)
    if s < 90:
        return f"{_num(s)} s"
    if s < 5400:
        return f"{_num(s / 60)} min"
    return f"{_num(s / 3600)} h"


def span(low_s: float, high_s: float) -> str:
    """`~3–12 min`: a range in the unit of its high end."""
    lo, hi = float(low_s), float(high_s)
    unit, div = ("s", 1) if hi < 90 else (("min", 60) if hi < 5400 else ("h", 3600))
    a, b = _num(lo / div), _num(hi / div)
    return f"~{a} {unit}" if a == b else f"~{a}–{b} {unit}"


def _pair(lo, hi, fmt) -> str:
    a, b = fmt(lo), fmt(hi)
    return a if a == b else f"{a}–{b}"


def describe(record: dict | None, what: str = "profiles projected") -> str:
    """One sentence for every surface that shows a projection."""
    record = record or {}
    if not record.get("available"):
        return f"{what}: no projection ({record.get('why', 'nothing on file')})"
    points = (
        _pair(record["points_low"], record["points_high"], lambda v: f"{int(v):,}")
        + f" points over {record['n_parameters']} parameter"
        + ("" if record["n_parameters"] == 1 else "s")
    )
    if record.get("low_s") is None:
        return (
            f"{what} at {points}; no seconds ({record.get('why', 'no per-point cost')})"
        )
    per = _pair(
        record["per_point_low_s"], record["per_point_high_s"], lambda v: f"{v:.2g}"
    )
    source = (
        "from the cost probe" if record["per_point_source"] == PROBE else "measured"
    )
    # processes, not parameters: each parameter is two direction tasks
    workers_note = (
        f", on {record['workers']} processes"
        if int(record.get("workers") or 1) > 1
        else ""
    )
    return (
        f"{what} {span(record['low_s'], record['high_s'])} ({points}; {per} s per "
        f"point {source}{workers_note})"
    )


# --------------------------------------------------------------- the batches


def batches(indices: list[int], size: int) -> list[list[int]]:
    """`indices` in consecutive batches of `size`; one batch when size covers them."""
    size = max(1, int(size))
    return [list(indices[i : i + size]) for i in range(0, len(indices), size)]


def points_in(profile) -> int:
    """Points of one finished profile, counted as `profile_points` counts them.

    Both halves start from a copy of the optimum, so the combined path holds it
    twice; it is counted once.
    """
    if profile is None:
        return 0
    return max(0, len(profile.fval_path) - 1)


class Progress:
    """Profiling measured batch by batch, and the rest re-projected from it."""

    def __init__(
        self,
        rows: list[dict],
        cost: dict | None,
        n_procs: int,
        total: int,
        done_before: int = 0,
        prior: list[dict] | None = None,
        median_start_s: float | None = None,
    ):
        self.rows = {r["name"]: r for r in rows}
        self.cost = cost
        self.n_procs = int(n_procs or 1)
        self.total = int(total)
        self.done_before = int(done_before)
        self.prior = list(prior or [])
        self.new: list[dict] = []
        self.median_start_s = median_start_s
        self.started = now()

    def add(self, names: list[str], points: int, wall_s: float, n_workers: int):
        self.new.append(
            {
                "parameters": list(names),
                "points": int(points),
                "wall_s": round(float(wall_s), 3),
                "workers": int(n_workers),
            }
        )

    @property
    def done(self) -> list[str]:
        return [n for b in self.new for n in b["parameters"]]

    @property
    def elapsed_s(self) -> float:
        return float(now() - self.started)

    @property
    def points_ratio(self) -> float | None:
        """Measured points over projected points (the midpoint of low and high),
        over the parameters this profiling finished; None before one.

        A batch whose parameters were not planned here (one an earlier, stopped
        profiling finished) has no projection to compare, and is left out.
        """
        measured = projected = 0.0
        for b in self.new:
            names = list(b["parameters"])
            if not names or any(n not in self.rows for n in names):
                continue
            measured += float(b["points"])
            projected += sum(midpoint_points(self.rows[n]) for n in names)
        return measured / projected if projected > 0 else None

    @property
    def per_point_s(self) -> float | None:
        """Worker-seconds per point over every batch so far, or None before one."""
        batches_ = self.prior + self.new
        points = sum(b["points"] for b in batches_)
        if points <= 0:
            return None
        return sum(b["wall_s"] * b["workers"] for b in batches_) / points

    def current_cost(self) -> dict | None:
        measured = self.per_point_s
        if measured is None:
            return self.cost
        return {
            "low_s": measured,
            "high_s": measured,
            "source": MEASURED,
            "detail": f"{measured:.2f} s per point, measured on this model's own profiles",
        }

    def remaining(self, names: list[str]) -> dict:
        """The projection record for `names`, at the current per-point cost and
        with their point counts scaled by the ratio measured so far."""
        ratio = self.points_ratio
        rows = calibrated([self.rows[n] for n in names if n in self.rows], ratio)
        return project(
            rows,
            self.current_cost(),
            workers(self.n_procs, len(rows)),
            points_ratio=round(ratio, 4) if ratio is not None else None,
        )

    def would_pass(self, cap_s: float, names: list[str]) -> bool:
        """True when the time spent plus the LOW estimate for `names` passes `cap_s`."""
        low = self.remaining(names).get("low_s")
        return low is not None and self.elapsed_s + float(low) > float(cap_s)

    def line(self, names_left: list[str]) -> str:
        done = self.done_before + len(self.done)
        text = (
            f"profiles: {done}/{self.total} parameters done, "
            f"{duration(self.elapsed_s)} elapsed"
        )
        if self.per_point_s is not None:
            text += f"; {self.per_point_s:.2g} s per point measured"
        if names_left:
            rem = self.remaining(names_left)
            if rem.get("low_s") is not None:
                text += f"; remaining {span(rem['low_s'], rem['high_s'])}"
        ratio = self.points_ratio
        if ratio is not None:
            text += f" (points so far {ratio:.2g}× the projected midpoint" + (
                ", applied to the rest)" if names_left else ")"
            )
        return text

    def ledger_fields(self, names_left: list[str]) -> dict:
        rem = self.remaining(names_left) if names_left else {}
        last = self.new[-1] if self.new else {}
        return {
            "parameters_done": self.done_before + len(self.done),
            "parameters_total": self.total,
            "elapsed_s": round(self.elapsed_s, 1),
            "batch_parameters": last.get("parameters"),
            "batch_points": last.get("points"),
            "batch_wall_s": last.get("wall_s"),
            "per_point_s": (
                round(self.per_point_s, 3) if self.per_point_s is not None else None
            ),
            "remaining_low_s": rem.get("low_s"),
            "remaining_high_s": rem.get("high_s"),
            # measured over projected points on the finished parameters; the
            # remaining projection's point counts are scaled by it
            "points_ratio": (
                round(self.points_ratio, 4) if self.points_ratio is not None else None
            ),
        }

    def timing_record(self, **extra) -> dict:
        batches_ = self.prior + self.new
        per = self.per_point_s
        return {
            "per_point_s": round(per, 4) if per is not None else None,
            "per_point_starts": (
                round(per / float(self.median_start_s), 4)
                if per is not None and self.median_start_s
                else None
            ),
            "median_start_s": self.median_start_s,
            "points": sum(b["points"] for b in batches_),
            "wall_s": round(sum(b["wall_s"] for b in batches_), 2),
            "workers": max((b["workers"] for b in batches_), default=0),
            "parameters_done": sum(len(b["parameters"]) for b in batches_),
            "parameters_total": self.total,
            "points_ratio": (
                round(self.points_ratio, 4) if self.points_ratio is not None else None
            ),
            "batches": batches_,
            **extra,
        }


# ---------------------------------------------------------------- the record

TIME_CAP = "time cap"


def not_profiled(profiles) -> list[str]:
    """The parameters a profiling stopped before, by name; [] when it finished.

    Read from `_meta.not_profiled`, which the batch loop writes when the time
    cap stops an automatic profiling.
    """
    meta = profiles.get("_meta") if isinstance(profiles, dict) else None
    stop = meta.get("not_profiled") if isinstance(meta, dict) else None
    names = stop.get("names") if isinstance(stop, dict) else None
    return [str(n) for n in (names or [])]


def write_timing(work, record: dict):
    """Record the profiling's timing at `work / TIMING_KEY` (the fitted
    problem's group, `ctx.work`). Returns the node written."""
    node = work / TIMING_KEY
    node.put(record)
    return node


def latest_timing(root, round_idx: int) -> dict | None:
    """The latest profile timing in this run, up to and including `round_idx`.

    Read from every unit of work of those rounds (`…/candidates/<id>/
    profiles_timing`, `_single` included). A re-entered evaluation does NOT
    supersede these records (`profiles_timing` is not among the evaluation's
    module caches): one stays until a profiling of the same unit of work
    rewrites it, so a re-entry that reuses its profiles, or computes none,
    still reads the earlier measurement. The latest round wins; within a
    round, the record with the latest `at`.
    """
    if root is None:
        return None
    from octomod.result import node as _tree

    best: tuple[int, dict] | None = None
    try:
        rounds = [k for k in _tree.round_indices(root) if k <= int(round_idx)]
    except Exception:  # no rounds is no measurement
        return None
    for k in rounds:
        rnd = _tree.round_node(root, k)
        try:
            works = (rnd / "candidates").children()
        except Exception:
            continue
        for cid in works:
            node = (rnd / "candidates").child(cid) / TIMING_KEY
            try:
                rec = node.get(None)
            except Exception:  # an unreadable record is no measurement
                continue
            if not isinstance(rec, dict) or not rec.get("per_point_s"):
                continue
            # the latest round wins; within a round, the latest written
            if (
                best is None
                or k > best[0]
                or (
                    k == best[0]
                    and str(rec.get("at") or "") > str(best[1].get("at") or "")
                )
            ):
                best = (k, rec)
    if best is None:
        return None
    return {**best[1], "round": best[1].get("round", best[0])}
