"""pyPESTO/AMICI plumbing: problem construction with a compile cache, and scales.

The only module that touches AMICI compilation. Two keys: the compile key (SBML,
observables, conditions, measurements, toolchain) names the compiled module and
its lock; the problem key adds parameters.tsv and names the in-memory problem,
so candidates over one structure share a module but never a problem.
"""

from __future__ import annotations

import contextlib
import fcntl
import logging
import math
import os
import re
import time

import numpy as np

from octomod.config import AMICI_CACHE_DIR, SWIG_BIN
from octomod.orchestration.ledger import sha256_text
from octomod.workflow_modules.assembly.petab_io import PetabInput, table_text

# What the C++ build actually depends on. The parameter table is deliberately
# absent: estimate flags and fixed values reach the model through the runtime
# parameter mapping, never the generated code (verified, see the module
# docstring). The observable table stays — formulas and noise ARE compiled.
COMPILED_TABLES = ("observables", "conditions", "measurements")
RUNTIME_TABLES = ("parameters",)

# The noise distributions the estimation path can fit; the assembly grammar
# accepts exactly this tuple. AMICI has no FIM for a Laplace likelihood, so
# `build_problem` switches the FIM Hessian off there (Fides then uses BFGS).
FITTABLE_NOISE_DISTRIBUTIONS = ("normal", "laplace")


def lr_threshold(alpha: float = 0.05) -> float:
    """The one-parameter likelihood-ratio threshold in -log(L):
    chi2.ppf(1 - alpha, df=1) / 2 (1.92 at alpha = 0.05)."""
    from scipy.stats import chi2

    return float(chi2.ppf(1.0 - alpha, 1) / 2.0)


def non_gaussian_observables(observable_df) -> list[str]:
    """Sorted observableIds whose `noiseDistribution` is not `normal`.

    A missing or empty cell is PEtab's default, `normal`.
    """
    if observable_df is None or "noiseDistribution" not in observable_df.columns:
        return []
    ids = (
        observable_df.index
        if observable_df.index.name == "observableId"
        else observable_df["observableId"]
    )
    out = []
    for oid, dist in zip(ids, observable_df["noiseDistribution"], strict=False):
        text = "" if dist is None else str(dist).strip().lower()
        if text in ("", "nan", "none"):
            text = "normal"
        if text != "normal":
            out.append(str(oid))
    return sorted(out)


def _disable_fim_hessian(problem, observable_ids: list[str]) -> None:
    """Switch pyPESTO's FIM-as-Hessian off on a built problem, or raise RuntimeError.

    pyPESTO reads `fim_for_hess` live (with it off, second order is not
    advertised and Fides' default Hessian update is BFGS), so setting it on the built
    objective is the whole change.
    """
    objective = getattr(problem, "objective", None)
    targets = [objective, *(getattr(objective, "_objectives", None) or [])]
    hit = False
    for obj in targets:
        if hasattr(obj, "fim_for_hess"):
            obj.fim_for_hess = False
            hit = True
    if not hit:
        raise RuntimeError(
            f"observable(s) {observable_ids} declare a non-Gaussian noise "
            f"distribution and the built objective "
            f"({type(objective).__name__}) has no `fim_for_hess` flag to switch "
            f"off — pyPESTO would index AMICI's missing FIM on the first "
            f"Hessian request. Refusing to build a problem the optimiser "
            f"cannot evaluate."
        )


def uses_fim_hessian(problem) -> bool | None:
    """What a Hessian request does on this problem: True = AMICI's FIM,
    False = a BFGS update inside the optimiser, None = not an AMICI objective."""
    return getattr(getattr(problem, "objective", None), "fim_for_hess", None)


def _toolchain() -> str:
    """Toolchain id for the compile key, so a venv switch misses the cache.

    A module built by one venv's amici/swig must not be loaded by another's
    (SWIG type tables).
    """
    import sys

    import amici

    return (
        f"amici={amici.__version__};swig={SWIG_BIN};"
        f"py={sys.version_info.major}.{sys.version_info.minor}"
    )


def compile_content_hash(inp: PetabInput) -> str:
    """Names the compiled AMICI module: everything the C++ depends on, and the
    toolchain that built it. Two candidates over one structure share this."""
    parts = [inp.sbml]
    parts += [table_text(getattr(inp, name)) for name in COMPILED_TABLES]
    parts.append(_toolchain())
    return sha256_text("\n".join(parts))[:12]


def problem_content_hash(inp: PetabInput) -> str:
    """Names the pyPESTO problem: the compile key plus the parameter table.
    Never use this to name a compile output folder — that is what throws the
    compile-once saving away."""
    parts = [compile_content_hash(inp)]
    parts += [table_text(getattr(inp, name)) for name in RUNTIME_TABLES]
    return sha256_text("\n".join(parts))[:12]


@contextlib.contextmanager
def _cache_key_lock(key: str):
    """Exclusive cross-process lock on one AMICI cache key.

    The cache is shared, so two runs must not compile one model into the same
    directory at once; different keys still compile in parallel.
    """
    AMICI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = AMICI_CACHE_DIR / f".lock_{key}"
    with open(lock_path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def build_problem(
    inp: PetabInput,
    cache: dict,
    spec=None,
    overrides: dict | None = None,
) -> tuple:
    """Build or reuse the pyPESTO problem; return (problem, petab_problem, compile_s)
    for an assembled problem (`petab_io.from_work`, or `from_dir` for an input
    on disk).

    compile_s is ~0 when the AMICI module came from the cache, including for
    another candidate over the same structure. The solver gets AMICI's built
    state, then the declared `simulation.amici` settings, then `overrides` (this
    candidate's recorded choices), on a cache hit too.
    """
    problem_key = problem_content_hash(inp)
    if problem_key in cache:
        prob, petab_problem = cache[problem_key]
        # the cached solver may have been retuned by an earlier caller: restore
        # the built state, then apply the declared settings and this caller's
        _settle_settings(
            prob, spec, overrides, cache.get(f"_solver_built:{problem_key}")
        )
        return prob, petab_problem, 0.0
    compile_key = compile_content_hash(inp)

    from pypesto.petab import PetabImporter

    from octomod.workflow_modules.assembly import hierarchical as _hier
    from octomod.workflow_modules.assembly.petab_io import load_problem

    os.environ["SWIG"] = str(SWIG_BIN)  # house convention for AMICI compiles
    # built from the tables and SBML in memory; petab, pyPESTO and AMICI
    # receive the object and read nothing from disk (the compile cache aside)
    petab_problem = load_problem(inp)
    # the PROBLEM asks for hierarchical optimisation, via `parameterType` in
    # its own parameter table. Read here rather than passed in, so a flag can never disagree with
    # the file — and note where this falls in the cache split: parameterType is
    # in parameters.tsv, hence the problem key, so a hierarchical and a plain
    # fit of one structure are two problems over ONE compiled model.
    hierarchical = _hier.enabled_for(petab_problem.parameter_df.reset_index())
    # the output folder basename must differ from model_name: identical names
    # nest as <name>/<name>/<name>.py and break SWIG module resolution
    out_dir = AMICI_CACHE_DIR / f"amici_{compile_key}"
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    from octomod.orchestration.artifacts import timepoint_check_patched

    # the lock is on the COMPILE key, because the C++ build is the thing two
    # processes must not do at once; the patched check lets a problem in which
    # only some conditions pre-equilibrate import at all
    with _cache_key_lock(compile_key), timepoint_check_patched():
        importer = PetabImporter(
            petab_problem,
            output_folder=str(out_dir),
            model_name=f"m_{compile_key}",
            validate_petab=False,
            hierarchical=hierarchical,
        )
        from octomod.orchestration import timing as _timing

        t0 = time.perf_counter()
        # EVERY parameter is compiled as estimable, not just the ones this
        # problem estimates. AMICI's default is the opposite
        # (`non_estimated_parameters_as_constants=True`), which bakes the
        # estimable SET into the generated C++ — and that makes one compiled
        # module per STRUCTURE impossible, because a candidate that fixes an
        # axis at its neutral value and a candidate that estimates it are two
        # different problems over the same model. Compiled AMICI's way, the
        # second candidate of a supermodel group whose axes are neutralizable
        # dies on
        #   "The available AMICI model does not support estimating the
        #    following parameters ... {'k_alt'}"
        # once the first has compiled `k_alt` away as a constant.
        # The revision grammar's `free_parameter` move hits the same wall for
        # the same reason, so this is not only the supermodel's problem.
        # The model is compiled EXPLICITLY, before `create_problem`, so the
        # flag reaches `import_petab_problem`: pypesto's `create_objective`
        # calls `create_model` with only force_compile and verbose, so a
        # keyword handed to `create_problem` never arrives. `create_problem`
        # then finds the module already on disk and loads it.
        with _timing.span("compute", "compile", model=f"m_{compile_key}"):
            importer.create_objective_creator().create_model(
                verbose=False, non_estimated_parameters_as_constants=False
            )
            prob = importer.create_problem()
        # pypesto's own `create_objective` call inside `create_problem` uses
        # its default verbose=True, which amici reads as "set the whole amici
        # logger tree to DEBUG" — permanently, for the rest of the process.
        # On the CTD problem (36 flattened observables) that printed a ~25 KB
        # parameter-mapping dump per simulation and buried the run's own
        # output. The compile's stdout is what the user asked to see; amici's
        # DEBUG stream is not. Restore the level amici ships with.
        logging.getLogger("amici").setLevel(logging.WARNING)
        compile_s = time.perf_counter() - t0
    # a non-Gaussian observable has no FIM in AMICI (see FITTABLE_NOISE_DISTRIBUTIONS)
    non_gaussian = non_gaussian_observables(petab_problem.observable_df)
    if non_gaussian:
        _disable_fim_hessian(prob, non_gaussian)
    cache[problem_key] = (prob, petab_problem)
    cache[f"_solver_built:{problem_key}"] = _solver_state(prob)
    _settle_settings(prob, spec, overrides, None)
    return prob, petab_problem, compile_s


def _solver_state(problem) -> dict:
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    if solver is None:
        return {}
    return _ss.read_back(solver, getattr(objective, "amici_model", None))


def _settle_settings(problem, spec, overrides: dict | None, built: dict | None) -> None:
    """Built state (on a reused object), then declared, then overrides."""
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    model = getattr(objective, "amici_model", None)
    if built and solver is not None:
        _ss.restore(solver, model, built)
    _apply_declared_settings(problem, spec)
    if overrides and solver is not None:
        _ss.apply_amici(solver, model, dict(overrides))


def _apply_declared_settings(problem, spec) -> dict:
    """Push `simulation.amici` onto the built problem's solver; return what was set.

    `spec=None` leaves AMICI's own defaults; every caller inside a run passes it.
    """
    if spec is None:
        return {}
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    if solver is None:
        return {}
    return _ss.apply_amici(
        solver, getattr(objective, "amici_model", None), _ss.flatten_spec(spec)
    )


# ----------------------------------------------------------- scale handling


def parameter_scales(parameters) -> dict[str, str]:
    """parameterId → parameterScale, from the parameter table (a DataFrame,
    or a `PetabInput`)."""
    par = parameters.parameters if isinstance(parameters, PetabInput) else parameters
    return dict(zip(par["parameterId"], par["parameterScale"], strict=False))


def unscale(value: float, scale: str) -> float:
    if scale == "log10":
        return float(10**value)
    if scale == "log":
        return float(np.exp(value))
    return float(value)


def x_to_unscaled_dict(
    x_full: np.ndarray, x_names: list[str], scales: dict[str, str]
) -> dict[str, float]:
    return {
        name: unscale(val, scales.get(name, "lin"))
        for name, val in zip(x_names, x_full, strict=False)
    }


# ---------------------------------------------- persisting the optimize result
# The multistart is the most expensive deterministic artifact a run produces,
# so it is persisted rather than held in one process's heap. Held only in the
# heap, a resume re-runs the whole thing to profile (on the CTD problem an hour
# and a half, to answer one gate), and a process that dies after profiling
# loses all of it (two hours forty there). Persisting it is also what makes a
# run's optimum re-checkable by someone else, which is the reproducibility
# half of the same argument.
# The run is one HDF5 file, so pyPESTO's own HDF5 writer is not used —
# the multistart's arrays go into the record as the candidate's `multistart`
# (one dataset per field, native), and `result_from_record` rebuilds the
# `pypesto.Result` of `OptimizerResult`s that profiling and refits consume.

_START_FIELDS = (
    "id",
    "x",
    "fval",
    "grad",
    "hess",
    "res",
    "sres",
    "x0",
    "fval0",
    "exitflag",
    "n_fval",
    "n_grad",
    "n_hess",
    "n_res",
    "n_sres",
    "time",
    "message",
    "optimizer",
    "free_indices",
    "inner_parameters",
)
# Row-aligned arrays, padded with NaN to one width and flagged `_present`.
# The 2-D ones are flattened: `hess` is n×n and `sres` is n_res×n, both
# reshaped on read from the start's own `x`. (`spline_knots`, a ragged list
# of arrays per observable, is the one pyPESTO field not kept.)
_ARRAY_FIELDS = (
    "x",
    "x0",
    "grad",
    "hess",
    "res",
    "sres",
    "free_indices",
    "inner_parameters",
)
# Scalars, flagged `_present` so None and NaN read back as they were written
# — pyPESTO's own writer keeps a NaN fval as NaN, and its `sort` (which
# `result_from_record` calls) puts NaN last but raises on None.
_FLOAT_FIELDS = ("fval", "fval0", "time")
_INT_FIELDS = ("n_fval", "n_grad", "n_hess", "n_res", "n_sres", "exitflag")


def _flat(v) -> np.ndarray | None:
    """An array-like start field as a flat float row; anything else is absent."""
    if v is None or not isinstance(v, (np.ndarray, list, tuple)):
        return None
    return np.asarray(v, dtype=float).ravel()


def result_to_record(result) -> dict:
    """The optimize result as arrays, one per field, row-aligned by start."""
    starts = list(result.optimize_result.list)
    out: dict = {"n_starts": len(starts), "fields": list(_START_FIELDS)}
    for f in _START_FIELDS:
        vals = [getattr(s, f, None) for s in starts]
        if f in _ARRAY_FIELDS:
            vals = [_flat(v) for v in vals]
            width = max((len(v) for v in vals if v is not None), default=0)
            rows = []
            for v in vals:
                if v is None:
                    rows.append([float("nan")] * width)
                else:
                    row = [float(x) for x in v]
                    rows.append(row + [float("nan")] * (width - len(row)))
            out[f] = rows
            out[f + "_present"] = [v is not None for v in vals]
        elif f in _FLOAT_FIELDS:
            out[f] = [float(v) if v is not None else float("nan") for v in vals]
            out[f + "_present"] = [v is not None for v in vals]
        elif f in _INT_FIELDS:
            out[f] = [int(v) if v is not None else -1 for v in vals]
            out[f + "_present"] = [v is not None for v in vals]
        else:
            out[f] = ["" if v is None else str(v) for v in vals]
    return out


def result_from_record(data: dict):
    """A `pypesto.Result` whose `optimize_result` holds the recorded starts."""
    import pypesto
    from pypesto.result import OptimizerResult

    n = int(data.get("n_starts") or 0)
    result = pypesto.Result()

    def _row(field, i, present_key=None):
        vals = data.get(field)
        if vals is None or i >= len(vals):
            return None
        if present_key and not bool(data.get(present_key, [True] * n)[i]):
            return None
        return vals[i]

    def _arr(field, i):
        row = _row(field, i, field + "_present")
        return None if row is None else np.asarray(row, dtype=float)

    def _scalar(field, i):
        v = _row(field, i, field + "_present")
        return None if v is None else float(v)

    for i in range(n):
        x = _arr("x", i)
        width = None if x is None else len(x)
        hess, sres = _arr("hess", i), _arr("sres", i)
        if hess is not None and hess.size == int(math.isqrt(hess.size)) ** 2:
            hess = hess.reshape(int(math.isqrt(hess.size)), -1)
        if sres is not None and width and sres.size % width == 0:
            sres = sres.reshape(-1, width)
        free = _arr("free_indices", i)
        opt = OptimizerResult(
            id=str(_row("id", i) or i),
            x=x,
            fval=_scalar("fval", i),
            grad=_arr("grad", i),
            hess=hess,
            res=_arr("res", i),
            sres=sres,
            x0=_arr("x0", i),
            fval0=_scalar("fval0", i),
            exitflag=_row("exitflag", i, "exitflag_present"),
            n_fval=_row("n_fval", i, "n_fval_present"),
            n_grad=_row("n_grad", i, "n_grad_present"),
            n_hess=_row("n_hess", i, "n_hess_present"),
            n_res=_row("n_res", i, "n_res_present"),
            n_sres=_row("n_sres", i, "n_sres_present"),
            time=_scalar("time", i),
            message=_row("message", i) or None,
            optimizer=_row("optimizer", i) or None,
        )
        # not constructor arguments in pyPESTO; the padding is dropped so the
        # indices come back as the ints they were
        if free is not None:
            opt.free_indices = free[~np.isnan(free)].astype(int)
        inner = _arr("inner_parameters", i)
        if inner is not None:
            opt.inner_parameters = inner
        result.optimize_result.append(opt)
    result.optimize_result.sort()
    return result


def write_optimize_result(result, node) -> None:
    """Persist the multistart at `node` (`ctx.work / "multistart"`, or an
    attempt's `…/attempts/<n>/multistart`)."""
    node.put_raw(result_to_record(result))


def read_optimize_result(node):
    """The persisted Result, or None when the record has none / it is broken.

    Returning None rather than raising is deliberate: the caller's fallback is
    to recompute, which is slow but correct, and a run that cannot read its own
    record should not die at the evaluation module.
    """
    try:
        data = node.get(None)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return result_from_record(data)
    except Exception:
        return None


# What a human may change when the convergence gate offers a refit. The solver
# keys are whatever `solver_settings` can apply, so a key legal at the gate is
# also legal in `simulation:`, and the reverse.
from octomod.workflow_modules.estimation.solver_settings import (  # noqa: E402
    ALL_KEYS as _SOLVER_SETTING_KEYS,
)

SOLVER_KEYS = _SOLVER_SETTING_KEYS
OPTIMIZER_KEYS = ("maxiter", "fatol")
REFIT_KEYS = ("n_starts_factor", *SOLVER_KEYS, *OPTIMIZER_KEYS)


def resolve_refit(spec, request: str) -> tuple[dict, str]:
    """(overrides, description) for a refit preset name or explicit key=value pairs.

    Raises ValueError naming the legal presets and keys.
    """
    presets = dict(spec.get("estimation.refit_presets") or {})
    text = (request or "").strip()
    if not text:
        raise ValueError(f"name a preset {sorted(presets)} or keys {list(REFIT_KEYS)}")
    if text in presets:
        return dict(presets[text]), f"preset {text!r}"
    out, unknown = {}, []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        if "=" not in part:
            unknown.append(part)
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k not in REFIT_KEYS:
            unknown.append(k)
            continue
        try:
            out[k] = float(v) if ("." in v or "e" in v.lower()) else int(v)
        except ValueError:
            unknown.append(part)
    if unknown or not out:
        raise ValueError(
            f"cannot read {unknown or [text]} — name a preset "
            f"{sorted(presets)}, or give keys from {list(REFIT_KEYS)} "
            f"as key=value"
        )
    return out, "explicit " + ", ".join(f"{k}={v}" for k, v in sorted(out.items()))


def apply_refit(problem, overrides: dict) -> tuple[list[str], dict]:
    """Push solver overrides onto a built problem; hand back the optimizer ones.

    Returns (applied, optimizer_overrides): the solver is live on the objective,
    the optimizer is built fresh by `run_multistart`. `applied` lists only what
    was actually set.
    """
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    want = {k: v for k, v in overrides.items() if k in SOLVER_KEYS}
    applied: list[str] = []
    if want and solver is not None:
        model = getattr(objective, "amici_model", None)
        got = _ss.apply_amici(solver, model, want)
        applied = [f"{k}={v}" for k, v in sorted(got.items())]
    opt = {k: overrides[k] for k in OPTIMIZER_KEYS if k in overrides}
    return applied, opt


_SERIAL_WORDS = ("singlecore", "single", "serial")
_PARALLEL_WORDS = ("multiprocess", "multiprocessing", "parallel")


def engine_kind(spec) -> str:
    """`estimation.engine` as `auto`, `serial` or `parallel`; anything else is refused."""
    kind = str(spec.get("estimation.engine", "auto")).lower()
    if kind in _SERIAL_WORDS:
        return "serial"
    if kind in _PARALLEL_WORDS:
        return "parallel"
    if kind == "auto":
        return kind
    raise ValueError(f"unknown estimation.engine in workflow spec: {kind}")


def resolve_n_procs(spec) -> int:
    """`estimation.n_procs`: a positive integer, or null / `auto` for
    cpu_count - 1 (leaving the machine usable). Anything else is refused by name."""
    n = spec.get("estimation.n_procs")
    if n is None or str(n).strip().lower() in ("", "auto", "null", "none"):
        return max(1, (os.cpu_count() or 2) - 1)
    if not isinstance(n, bool):
        try:
            v = int(str(n).strip())
        except ValueError:
            v = 0
        if v >= 1:
            return v
    raise ValueError(
        f"estimation.n_procs must be a positive integer, or null for "
        f"cpu_count - 1; the workflow spec has {n!r}"
    )


def _parallel_floor(spec) -> float:
    return float(spec.get("estimation.parallel_min_start_s", 2.0))


def make_engine(spec, median_start_s: float | None = None):
    """The pyPESTO engine for starts and profiles, from `estimation.engine`.

    `auto` goes parallel only when the measured median start is slower than
    `estimation.parallel_min_start_s`, since each task pickles the objective into
    a freshly spawned interpreter; `singlecore` and `multiprocess` force either
    way. `estimation.n_procs` defaults to cpu_count - 1, and a pool of one
    process is no pool: that is serial too. Multistarts run through
    `start_engine` (this decision, with each start timed); the cost probe,
    which measures the median this reads, uses `make_probe_engine`.
    """
    import pypesto.engine

    kind = engine_kind(spec)
    if kind == "serial":
        return pypesto.engine.SingleCoreEngine()
    if kind == "auto" and (
        median_start_s is None or float(median_start_s) < _parallel_floor(spec)
    ):
        return pypesto.engine.SingleCoreEngine()
    n = resolve_n_procs(spec)
    if n == 1:  # one worker would only add the pickling
        return pypesto.engine.SingleCoreEngine()
    return pypesto.engine.MultiProcessEngine(n_procs=n)


def engine_reason(spec, median_start_s: float | None = None) -> str:
    """Why `make_engine` runs starts one at a time or in parallel, in words."""
    kind = engine_kind(spec)
    if kind == "serial":
        return "estimation.engine: singlecore"
    floor = _parallel_floor(spec)
    if kind == "auto":
        if median_start_s is None:
            return "no start measured yet"
        if float(median_start_s) < floor:
            return (
                f"a start ({float(median_start_s):.2f}s) is under "
                f"parallel_min_start_s ({floor:g}s): too fast to be worth dispatching"
            )
    if resolve_n_procs(spec) == 1:
        return "estimation.n_procs allows one process"
    if kind == "parallel":
        return "estimation.engine: multiprocess"
    return (
        f"a start ({float(median_start_s):.2f}s) is over parallel_min_start_s "
        f"({floor:g}s)"
    )


def start_engine(spec, seed: int, median_start_s: float | None = None, capture=None):
    """The `StartEngine` for a multistart: `make_engine`'s decision, with every
    start seeded by its index and timed (`start_engine.py`)."""
    from octomod.workflow_modules.estimation.start_engine import StartEngine

    engine = make_engine(spec, median_start_s)
    n = int(getattr(engine, "n_procs", 1) or 1)
    return StartEngine(
        "parallel" if n > 1 else "serial",
        n,
        seed=seed,
        capture=capture,
        decided=engine_reason(spec, median_start_s),
    )


def make_probe_engine(
    spec, seed: int, capture=None, known_start_s: float | None = None
):
    """The engine for the cost probe's starts, from the same `estimation.engine`.

    The probe measures the median `make_engine` decides from, so under `auto`
    it decides as it goes (`StartEngine` mode `adaptive`): starts run here
    until one has used `estimation.parallel_min_start_s` of CPU and is still
    running, and then the rest are dispatched. `known_start_s`, what an
    earlier probe of the same problem measured (the adjoint re-probe), settles
    it up front when it is over the floor. `multiprocess` dispatches every
    start; `singlecore` runs them all here. `capture` (a
    `solver_messages.Capture`) also receives AMICI's messages from the workers.
    """
    from octomod.workflow_modules.estimation.start_engine import StartEngine

    kind = engine_kind(spec)
    if kind == "serial":
        return StartEngine(
            "serial", seed=seed, capture=capture, decided=engine_reason(spec)
        )
    n = resolve_n_procs(spec)
    floor = _parallel_floor(spec)
    if kind == "parallel":
        return StartEngine(
            "parallel",
            n,
            seed=seed,
            capture=capture,
            decided="estimation.engine: multiprocess dispatches every start",
        )
    if known_start_s is not None and float(known_start_s) >= floor:
        return StartEngine(
            "parallel",
            n,
            seed=seed,
            capture=capture,
            decided=(
                f"the forward probe measured {float(known_start_s):.2f}s per "
                f"start, over parallel_min_start_s ({floor:g}s)"
            ),
        )
    return StartEngine("adaptive", n, seed=seed, min_start_cpu_s=floor, capture=capture)


# The record key a run writes its optimiser selection to, a sibling of the
# cost probe that measured it (`…/candidates/<id>/optimizer_selection`). In
# the record rather than an in-memory cache because the run pauses at gates
# and resumes in a new process: a selection that did not survive the pause
# would silently revert to the default and nothing would say so.
#
# SCOPE: the key lives in the fitted problem's group (`ctx.work`: the round's
# `_single`, or a candidate's) — so a selection is per ROUND and, during
# mechanism discrimination, per CANDIDATE. That is deliberate and not a
# per-run cache: a later round fits a DIFFERENT model, and a selection
# measured on the previous one is not evidence about it. The consequence to
# know is that each round re-decides from its own probe, and a round whose
# probe does not trigger a comparison runs on the default even if an earlier
# round selected something else.
SELECTION_KEY = "optimizer_selection"


def resolve_optimizer(spec, work=None) -> tuple[str, str]:
    """Which optimiser to run, and why. Returns (name, provenance).

    The order is the whole contract, and the first rule is the one that
    matters: an EXPLICIT request always wins. `estimation.optimizer` set to a
    concrete name in the spec, or a policy or refit that names one, is obeyed
    without measurement — a person who asked for a solver gets that solver.

    1. `estimation.optimizer` is a concrete name  -> that name, "explicit".
    2. it is `auto` and THIS ROUND (and candidate) has selected one -> that,
       "selected". Scope is `work`, the fitted problem's record group (a
       `Node`); see SELECTION_KEY above.
    3. it is `auto` and nothing has been selected -> the default,
       "default (no comparison on file)".

    Rule 3 is what makes `auto` safe to be the default setting: a run that
    never reaches the comparison, or whose comparison was inconclusive, behaves
    exactly as the workflow always has.
    """
    name = str(spec.get("estimation.optimizer", "auto"))
    if name != "auto":
        return name, "explicit (workflow spec)"
    if work is not None:
        try:
            sel = (work / SELECTION_KEY).get(None)
        except Exception:  # an unreadable selection is no selection
            sel = None
        if isinstance(sel, dict):
            chosen = str(sel.get("selected") or "")
            if chosen:
                return chosen, f"selected by comparison — {sel.get('reason', '')}"
    from octomod.workflow_modules.estimation.optimizer_compare import DEFAULT_OPTIMIZER

    return DEFAULT_OPTIMIZER, "default (no comparison on file)"


def build_optimizer(name: str, optimizer_overrides: dict | None = None):
    """The pyPESTO optimiser for an `estimation.optimizer` name.

    Knows `auto`, `fides`, `scipy` and every comparison backend; callers outside
    the comparison use this, not `optimizer_compare.build`. Raises ValueError for
    an unknown or unavailable name, or for optimizer overrides on a non-fides one.
    """
    import logging

    import pypesto.optimize

    if name == "auto":  # unresolved: the caller did not resolve, so default
        from octomod.workflow_modules.estimation.optimizer_compare import (
            DEFAULT_OPTIMIZER,
        )

        name = DEFAULT_OPTIMIZER
    if name == "fides":
        # refit overrides (`maxiter`, `fatol`) are fides' own option names
        return pypesto.optimize.FidesOptimizer(
            verbose=logging.WARNING, options=dict(optimizer_overrides or {}) or None
        )
    if name == "scipy":  # spec-level fallback, still not agent-chosen
        return pypesto.optimize.ScipyOptimizer(method="L-BFGS-B")
    from octomod.workflow_modules.estimation import optimizer_compare as _oc

    if name not in _oc.BACKENDS:
        raise ValueError(f"unknown optimizer in workflow spec: {name}")
    ok, why = _oc.available(name)
    if not ok:
        raise ValueError(f"optimiser {name!r} was selected but cannot run here: {why}")
    if optimizer_overrides:
        # `maxiter`/`fatol` mean nothing to other optimisers; dropping them would
        # spend a refit on a run identical to the last one, so refuse by name
        raise ValueError(
            f"the refit asks for optimizer options "
            f"{sorted(optimizer_overrides)}, which are fides' own option "
            f"names and do not exist for {name!r} (selected for this run). "
            f"Either refit with solver keys instead, or set "
            f"`estimation.optimizer: fides` explicitly to tune fides."
        )
    return _oc.build(name)


def run_multistart(
    problem,
    n_starts: int,
    seed: int,
    spec,
    median_start_s: float | None = None,
    optimizer_overrides: dict | None = None,
    optimizer_name: str | None = None,
    purpose: str = "multistart",
    engine=None,
) -> object:
    """Seeded multistart with the workflow's optimiser — the spec's choice or
    the one this run selected, never the agent's. `purpose` names the span
    of the time account this call is: the fit itself, the cost
    probe's starts, or S7's re-run of a fit it could not load. `engine`
    overrides `start_engine` (the cost probe passes `make_probe_engine`'s)."""

    from octomod.orchestration import timing as _timing

    np.random.seed(seed)  # the start points; each start is seeded by its index
    name = optimizer_name or str(spec.get("estimation.optimizer", "auto"))
    optimizer = build_optimizer(name, optimizer_overrides)
    if engine is None:
        engine = start_engine(spec, seed, median_start_s)
    if hasattr(engine, "seed"):
        engine.seed = int(seed)
    with _timing.span(
        "compute", purpose, n_starts=int(n_starts), optimizer=name
    ) as _span:
        try:
            result = _minimize(problem, optimizer, n_starts, engine)
        finally:
            # the processes that actually ran starts, also when it raised
            _span.update(_engine_detail(engine, n_starts))
        # the WORK, beside the time: objective and gradient evaluations are
        # what the machine actually did, and the cost per evaluation is what
        # compares across machines
        _span.update(work_units(result))
        return result


def _engine_detail(engine, n_starts: int) -> dict:
    summary = getattr(engine, "summary", None)
    if callable(summary):
        s = summary()
        return {"n_procs": s["n_workers"], "n_dispatched": s["n_dispatched"]}
    n = int(getattr(engine, "n_procs", 1) or 1)
    return {"n_procs": max(1, min(n, int(n_starts)))}


def work_units(result) -> dict:
    """Objective / gradient / Hessian evaluations summed over a pypesto
    Result's optimizer starts; zeros when unknown."""
    out = {"n_fval": 0, "n_grad": 0, "n_hess": 0}
    try:
        for r in result.optimize_result.list:
            for k in out:
                v = getattr(r, k, None)
                out[k] += int(v) if isinstance(v, (int, float)) and v == v else 0
    except Exception:  # noqa: BLE001 - a reading, never a reason to fail a fit
        pass
    return out


def _minimize(problem, optimizer, n_starts, engine):
    import pypesto.optimize

    return pypesto.optimize.minimize(
        problem=problem,
        optimizer=optimizer,
        n_starts=n_starts,
        engine=engine,
        progress_bar=False,
        filename=None,
    )


# a free parameter within this fraction of its box width from a bound is AT it
# (the same line `at_bounds` below draws)
ACTIVE_BOUND_FRACTION = 1e-3


def projected_gradient(opt, problem, x_names: list[str]) -> dict:
    """Raw and projected (KKT) gradient norms of an optimum over the free parameters.

    In the optimiser's scaled space. A component at an active bound that points
    out of the box (positive at a lower bound, negative at an upper one) cannot
    be descended along: the projected norm drops it and `parked` names the
    parameter. Non-finite components are named in `nonfinite`, not skipped.
    """
    out = {"raw_norm": None, "projected_norm": None, "parked": [], "nonfinite": []}
    if opt.grad is None or opt.x is None:
        return out
    g_all = np.asarray(opt.grad, dtype=float)
    x_all = np.asarray(opt.x, dtype=float)
    lb = np.asarray(problem.lb_full, dtype=float)
    ub = np.asarray(problem.ub_full, dtype=float)
    free = list(problem.x_free_indices)
    full = len(g_all) == len(x_names)
    raw, proj = [], []
    for j, i in enumerate(free):
        gi = float(g_all[i] if full else g_all[j])
        name = x_names[i]
        if not np.isfinite(gi):
            out["nonfinite"].append(name)
            continue
        raw.append(gi)
        width = ub[i] - lb[i]
        at_lb = width > 0 and (x_all[i] - lb[i]) / width < ACTIVE_BOUND_FRACTION
        at_ub = width > 0 and (ub[i] - x_all[i]) / width < ACTIVE_BOUND_FRACTION
        if (at_lb and gi > 0) or (at_ub and gi < 0):
            out["parked"].append(
                {
                    "id": name,
                    "edge": "lower" if at_lb else "upper",
                    "component": round(gi, 6),
                }
            )
            continue
        proj.append(gi)
    if raw:
        out["raw_norm"] = float(np.linalg.norm(raw))
        out["projected_norm"] = float(np.linalg.norm(proj)) if proj else 0.0
    return out


def summarize_result(
    result,
    problem,
    scales: dict[str, str],
    n_data: int,
    seed: int,
    spec,
    optimizer_name: str | None = None,
) -> dict:
    starts = []
    for opt in result.optimize_result.list:
        starts.append(
            {
                "id": opt.id,
                "fval": float(opt.fval) if opt.fval is not None else float("inf"),
                "time_s": float(opt.time) if opt.time is not None else None,
                "n_grad": getattr(opt, "n_grad", None),
            }
        )
    fvals = sorted(s["fval"] for s in starts)
    best = result.optimize_result.list[0]
    x_names = list(problem.x_names)
    if best.x is None or not np.isfinite(fvals[0] if fvals else np.inf):
        # every start died: an all-failed summary for the fit gates, not a crash
        return {
            "optimizer": optimizer_name or resolve_optimizer(spec)[0],
            "seed": seed,
            "n_starts": len(starts),
            "n_data": n_data,
            "fvals": fvals,
            "best_fval": float("inf"),
            "best_grad_norm": None,
            "best_projected_grad_norm": None,
            "grad_at_active_bounds": [],
            "grad_nonfinite": [],
            "best_x_unscaled": {},
            "at_bounds": [],
            "near_bounds": [],
            "ensemble": [],
            "ensemble_delta_nllh": float(spec.get("gates.ensemble_delta_nllh", 1.92)),
            "starts": starts,
            "x_names": x_names,
        }

    grad = projected_gradient(best, problem, x_names)
    grad_norm = grad["raw_norm"]

    # At-bounds check in scaled space, free parameters only. `near_bounds` is a
    # report, not a flag: a parameter near its bound may be compensating for a
    # missing mechanism, but it is allowed to sit there.
    at_bounds = []
    near_bounds = []
    near_frac = float(spec.get("gates.near_bound_fraction", 0.05))
    x_full = np.asarray(best.x, dtype=float)
    lb, ub = np.asarray(problem.lb_full, dtype=float), np.asarray(
        problem.ub_full, dtype=float
    )
    for i in problem.x_free_indices:
        width = ub[i] - lb[i]
        if width <= 0:
            continue
        from_lb = (x_full[i] - lb[i]) / width
        from_ub = (ub[i] - x_full[i]) / width
        if min(from_lb, from_ub) < 1e-3:
            at_bounds.append(x_names[i])
        elif min(from_lb, from_ub) <= near_frac:
            near_bounds.append(
                {
                    "id": x_names[i],
                    "edge": "lower" if from_lb < from_ub else "upper",
                    "position": round(float(from_lb), 4),
                    "from_edge": round(float(min(from_lb, from_ub)), 4),
                }
            )

    delta = float(spec.get("gates.ensemble_delta_nllh", 1.92))
    ensemble = [
        {
            "fval": float(opt.fval),
            "x_unscaled": x_to_unscaled_dict(
                np.asarray(opt.x, dtype=float), x_names, scales
            ),
        }
        for opt in result.optimize_result.list
        if opt.fval is not None
        and np.isfinite(opt.fval)
        and opt.fval <= fvals[0] + delta
    ]

    return {
        # the resolved name, never the spec word `auto`
        "optimizer": optimizer_name or resolve_optimizer(spec)[0],
        "seed": seed,
        "n_starts": len(starts),
        "n_data": n_data,
        "fvals": fvals,
        "best_fval": fvals[0] if fvals else float("inf"),
        "best_grad_norm": grad_norm,
        # the gradient the optimum can still descend along, and the parameters
        # pressing on their box
        "best_projected_grad_norm": grad["projected_norm"],
        "grad_at_active_bounds": grad["parked"],
        "grad_nonfinite": grad["nonfinite"],
        # inner (analytically solved) values are part of the fit: the held-out
        # prediction reads this dict and would otherwise simulate them at nominal
        "best_x_unscaled": {
            **x_to_unscaled_dict(x_full, x_names, scales),
            **{
                pid: unscale(val, scales.get(pid, "lin"))
                for pid, val in _inner_at_optimum(result, problem).items()
                if not pid.startswith("unnamed_inner_")
            },
        },
        "at_bounds": at_bounds,
        "near_bounds": near_bounds,
        "near_bound_fraction": near_frac,
        "ensemble": ensemble,
        "ensemble_delta_nllh": delta,
        "starts": starts,
        "x_names": x_names,
        # parameters the inner problem solved analytically: absent from the outer
        # waterfall, but estimated, and they count in k
        "estimated_inner": _inner_at_optimum(result, problem),
    }


def _inner_at_optimum(result, problem) -> dict:
    """{parameter_id: value on its estimation scale} for the inner parameters, or {}.

    pyPESTO carries them on the best optimizer result, not in `x`; the ids come
    from the problem's own parameter table.
    """
    try:
        best = result.optimize_result.list[0]
    except Exception:
        return {}
    values = best.get("inner_parameters") if hasattr(best, "get") else None
    if values is None:
        values = getattr(best, "inner_parameters", None)
    if values is None:
        return {}
    try:
        from octomod.workflow_modules.assembly import hierarchical as _hier

        ids = _hier.inner_ids(
            problem.objective.amici_object_builder.petab_problem.parameter_df.reset_index()
        )
    except Exception:
        ids = []
    vals = [float(v) for v in values]
    if len(ids) == len(vals):
        return dict(zip(ids, vals, strict=False))
    # a value that cannot be named is recorded under an `unnamed_inner_` key
    return {f"unnamed_inner_{i}": v for i, v in enumerate(vals)}
