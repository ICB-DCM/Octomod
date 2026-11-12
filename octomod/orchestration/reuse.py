"""Reuse instead of recompute: fingerprints for the expensive products of a run.

A fit is keyed by the problem content, the solver settings the solver holds,
the optimiser and its options, the seed, the estimation source and the library
versions; a fit with at least the requested starts answers the request (same
seed, same problem). Profiles are keyed by the problem, the optimum, every
declared profile setting and their source. This module never decides what to
compute; it only answers "has exactly this been computed already?".

Everything here lives in the run record. A fit's fingerprint is the
`fit_key` of the work group that holds it (`…/candidates/<id>/fit_key`), the
run-level index is `fit_index` at the record root (fingerprint → the work
groups holding that fit), and the profiles a fit carries are `…/profiles`.
A "fit" is the three records `multistart`, `estimation` and `starts` of one
work group; adopting one copies those groups from another work group.
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import importlib
import inspect
import json
import textwrap

from octomod.result.node import Node
from octomod.workflow_modules.assembly.petab_io import PetabInput

FIT_KEY = "fit_key"
FIT_INDEX_KEY = "fit_index"  # run-level (record root): fingerprint -> fits
FIT_KEYS = ("multistart", "estimation", "starts")
PROFILES_KEY = "profiles"
# Decided or computed on the fit, so an identical fit carries them; profiles
# are still checked against their own key when read.
CARRIED_WITH_FIT = ("decisions/estimation_convergence", PROFILES_KEY)
_LIBRARIES = ("pypesto", "fides", "amici", "petab")


def _sha(parts: dict) -> str:
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def _read(node: Node) -> dict | None:
    try:
        d = node.get(None)
    except Exception:  # an unreadable record is no record
        return None
    return d if isinstance(d, dict) else None


_TIMING_NAMES = ("timing", "_timing")


def _is_timing_attr(node) -> bool:
    """`timing.<x>` / `_timing.<x>` (the time account)."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in _TIMING_NAMES
    )


def _is_timing_call(node) -> bool:
    return isinstance(node, ast.Call) and _is_timing_attr(node.func)


class _StripTiming(ast.NodeTransformer):
    """Remove the time account's instrumentation from a syntax tree: a
    `with timing.span(...) [as s]:` becomes its body, `timing.*` decorators
    go, and so do `s.update(...)` / `s[...] = ...` on a span's `as` name and
    the imports of the timing module. What is timed, and with what detail,
    is not what a fit or a profile computes."""

    def __init__(self):
        self.span_names: set[str] = set()

    def _body(self, stmts):
        out = []
        for stmt in stmts:
            r = self.visit(stmt)
            if r is None:
                continue
            out.extend(r if isinstance(r, list) else [r])
        return out

    def generic_visit(self, node):
        super().generic_visit(node)
        # a block whose only statements were instrumentation keeps a `pass`
        if getattr(node, "body", None) == [] and isinstance(node, ast.stmt):
            node.body = [ast.Pass()]
        return node

    def _strip_decorators(self, node):
        node.decorator_list = [
            d
            for d in node.decorator_list
            if not (_is_timing_attr(d) or _is_timing_call(d))
        ]
        return self.generic_visit(node)

    visit_FunctionDef = _strip_decorators
    visit_AsyncFunctionDef = _strip_decorators
    visit_ClassDef = _strip_decorators

    def _strip_with(self, node):
        kept = []
        for item in node.items:
            if _is_timing_call(item.context_expr):
                if isinstance(item.optional_vars, ast.Name):
                    self.span_names.add(item.optional_vars.id)
            else:
                kept.append(item)
        body = self._body(node.body)
        if not kept:
            return body
        node.items = kept
        node.body = body or [ast.Pass()]
        return node

    visit_With = _strip_with
    visit_AsyncWith = _strip_with

    def visit_Expr(self, node):
        v = node.value
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Attribute)
            and v.func.attr == "update"
            and isinstance(v.func.value, ast.Name)
            and v.func.value.id in self.span_names
        ):
            return None
        return self.generic_visit(node)

    def visit_Assign(self, node):
        if all(
            isinstance(t, ast.Subscript)
            and isinstance(t.value, ast.Name)
            and t.value.id in self.span_names
            for t in node.targets
        ):
            return None
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module == "octomod.orchestration" and all(
            a.name == "timing" for a in node.names
        ):
            return None
        return node

    def visit_Import(self, node):
        if all(a.name == "octomod.orchestration.timing" for a in node.names):
            return None
        return node


def _code_text(source: str) -> str:
    """The code of `source` as fingerprinted: its syntax tree without
    docstrings and without the timing instrumentation, unparsed. A change to
    a comment, a docstring or a `timing.span(...)` leaves it unchanged."""
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    tree = ast.fix_missing_locations(_StripTiming().visit(tree))
    return ast.unparse(tree)


def _code(*objects) -> str:
    """Hash of the code behind a product (`_code_text` of each object's source).

    A code edit makes the next re-entry recompute instead of reuse; an edit to
    a comment, a docstring or the timing instrumentation does not.
    """
    h = hashlib.sha256()
    for obj in objects:
        try:
            text = _code_text(inspect.getsource(obj))
        except (OSError, TypeError, SyntaxError):
            h.update(repr(obj).encode())
            continue
        h.update(text.encode())
    return h.hexdigest()[:12]


def _versions() -> dict:
    out = {}
    for name in _LIBRARIES:
        try:
            out[name] = str(getattr(importlib.import_module(name), "__version__", "?"))
        except Exception:
            out[name] = None
    return out


def fit_fingerprint(
    inp: PetabInput,
    work: Node | None,
    problem,
    spec,
    seed: int,
    optimizer_overrides: dict | None = None,
) -> tuple[str, dict]:
    """The fingerprint of the multistart `estimation` is about to run.

    `inp` is the assembled problem (`petab_io.from_work`), `work` the fitted
    problem's record group (`ctx.work`), whose optimiser selection counts.
    """
    from octomod.workflow_modules.estimation import problem as estimation
    from octomod.workflow_modules.estimation import solver_settings as _ss

    objective = getattr(problem, "objective", None)
    solver = getattr(objective, "amici_solver", None)
    solver_state = (
        _ss.read_back(solver, getattr(objective, "amici_model", None))
        if solver is not None
        else {}
    )
    parts = {
        "problem": estimation.problem_content_hash(inp),
        "solver": solver_state,
        # the optimiser that will run (explicit, else this work group's
        # selection, else the default), not the spec word `auto`
        "optimizer": estimation.resolve_optimizer(spec, work)[0],
        "optimizer_overrides": dict(optimizer_overrides or {}),
        "seed": int(seed),
        "code": _code(estimation),
        "versions": _versions(),
    }
    return _sha(parts), parts


def fit_in_record(ctx, problem, n_starts: int) -> tuple[Node | None, str, dict]:
    """Look up the fit this candidate needs, with at least `n_starts` starts.

    Returns (the work group holding it or None, fingerprint, its parts). The
    one lookup used by S6, the cost module and the orchestrator's round pricing.
    """
    from octomod.workflow_modules.assembly import petab_io

    key, parts = fit_fingerprint(
        petab_io.from_work(ctx.work, ctx.model),
        ctx.work,
        problem,
        ctx.spec,
        int(ctx.spec.require("estimation.seed")),
        _optimizer_overrides(ctx),
    )
    return find_fit(ctx.root, ctx.work, key, n_starts), key, parts


def _optimizer_overrides(ctx) -> dict | None:
    from octomod.workflow_modules.estimation import estimation_settings

    return estimation_settings.optimizer_overrides(ctx) or None


def stored_fit(work: Node) -> dict:
    """The fingerprint record written beside a fit ({} when there is none)."""
    return _read(work / FIT_KEY) or {}


def _fit_complete(work: Node, key: str, n_starts: int) -> bool:
    if not all((work / k).exists() for k in FIT_KEYS):
        return False
    stored = stored_fit(work)
    return stored.get("key") == key and int(stored.get("n_starts") or 0) >= int(
        n_starts
    )


def _index(root: Node) -> dict[str, list[dict]]:
    raw = _read(root / FIT_INDEX_KEY) or {}
    return {
        k: [e for e in v if isinstance(e, dict)]
        for k, v in raw.items()
        if isinstance(v, list)
    }


def find_fit(root: Node, work: Node, key: str, n_starts: int) -> Node | None:
    """The work group holding exactly this fit with at least `n_starts`
    starts, or None.

    Checks the candidate's own group first, then anywhere the run has indexed
    the fit (most starts first).
    """
    if _fit_complete(work, key, n_starts):
        return work
    entries = sorted(
        _index(root).get(key, []),
        key=lambda e: -int(e.get("n_starts") or 0),
    )
    for e in entries:
        # the indexed key is already escaped: address it whole, not by segment
        src = Node(root.store, str(e.get("work") or ""))
        if src.key and src.key != work.key and _fit_complete(src, key, n_starts):
            return src
    return None


def fits_of_problem(root: Node, problem_hash: str) -> list[dict]:
    """Every fit the run has indexed for this problem hash, whatever its settings."""
    out = []
    for key, entries in _index(root).items():
        for e in entries:
            if e.get("problem") == problem_hash:
                out.append({**e, "key": key})
    return out


def adopt_fit(src: Node, work: Node) -> list[str]:
    """Copy a fit found elsewhere in the run into `work`, keeping it self-contained.

    Returns the record keys (relative to the work group) copied.
    """
    copied = []
    for name in FIT_KEYS + (FIT_KEY,) + CARRIED_WITH_FIT:
        if (src / name).copy_to(work / name):
            copied.append(name)
    return copied


def record_fit(
    root: Node,
    work: Node,
    key: str,
    parts: dict,
    n_starts: int,
    best_fval: float | None = None,
) -> None:
    """Write the fit's fingerprint beside it and index it in the run's fit index."""
    at = datetime.datetime.now().isoformat(timespec="seconds")
    (work / FIT_KEY).put(
        {
            "key": key,
            "parts": parts,
            "n_starts": int(n_starts),
            "best_fval": best_fval,
            "at": at,
        }
    )
    if work.store.path != root.store.path:  # a fit outside the run: not indexed
        return
    index = _index(root)
    entries = [e for e in index.get(key, []) if e.get("work") != work.key]
    entries.append(
        {
            "work": work.key,
            "n_starts": int(n_starts),
            "problem": parts.get("problem"),
            "best_fval": best_fval,
            "at": at,
        }
    )
    index[key] = entries
    (root / FIT_INDEX_KEY).put(index)


def profile_fingerprint(
    inp: PetabInput, summary: dict, spec, solver: dict | None = None
) -> tuple[str, dict]:
    """The fingerprint of the profiles `evaluation._profiles` would compute.

    `inp` is the assembled problem; `solver` holds the candidate's solver
    overrides (`estimation_settings`).
    """
    from octomod.workflow_modules.estimation import problem as estimation
    from octomod.workflow_modules.evaluation import engine as evaluation_module
    from octomod.workflow_modules.evaluation import profile_projection

    best = summary.get("best_x_unscaled") or {}
    if isinstance(best, list):
        best = dict(zip(summary.get("x_names") or [], best, strict=False))
    section = spec.get("uncertainty") or {}
    parts = {
        "problem": estimation.problem_content_hash(inp),
        "best_x": {str(k): float(v) for k, v in sorted(dict(best).items())},
        "best_fval": float(summary.get("best_fval") or 0.0),
        "solver_overrides": dict(solver or {}),
        "next_guess": str(spec.get("uncertainty.profile_next_guess")),
        "step_sizes": dict(spec.get("uncertainty.profile_step_sizes") or {}),
        # every declared `profile_*` setting, so one added later cannot be
        # forgotten here; the band settings beside them do not move a profile
        "declared": {
            k: v
            for k, v in (section.items() if isinstance(section, dict) else [])
            if str(k).startswith("profile_")
        },
        "code": _code(
            evaluation_module._profiles,
            profile_projection.profile_options,
            estimation.build_problem,
            estimation._apply_declared_settings,
        ),
        "versions": _versions(),
    }
    return _sha(parts), parts


def load_profiles(work: Node, key: str) -> dict | None:
    """The profile summaries already computed for exactly this key, or None."""
    d = _read(work / PROFILES_KEY)
    if not d or d.get("key") != key or not isinstance(d.get("profiles"), dict):
        return None
    return d["profiles"]


def store_profiles(work: Node, key: str, parts: dict, profiles: dict) -> None:
    (work / PROFILES_KEY).put(
        {
            "key": key,
            "parts": parts,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "profiles": profiles,
        }
    )
