"""Reuse instead of recompute (`octomod/orchestration/reuse.py`).

  1. a fit's fingerprint moves with its inputs (engine code too), not the start count;
  2. the candidate's own fit is found first, then one elsewhere; never a partial one;
  3. real estimation: a repeat or an identical problem loads the fit, more starts refit;
  4. the next round's base is neither probed nor budgeted, and S6 adopts its fit;
  5. profiles are reused only for the same problem, optimum and settings;
  6. a budget-gate `convergence: accept` survives a restart; a later answer drops it.

    uv run python tests/reuse_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration import reuse  # noqa: E402
from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from tests._record import temp_record, work  # noqa: E402

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"


class _Spec(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def _tables() -> petab_io.PetabInput:
    """The supplied PEtab problem, in memory."""
    return petab_io.from_dir(PETAB)


def _more_data(inp: petab_io.PetabInput, n: int = 1) -> petab_io.PetabInput:
    """The same problem with its last measurement repeated `n` more times — a
    change to the DATA: the record hashes the table's content, not a file's
    bytes, so the change is a row."""
    import pandas as pd

    m = inp.measurements
    return inp.with_tables(
        measurements=pd.concat([m] + [m.tail(1)] * n, ignore_index=True)
    )


def test_the_fit_fingerprint_moves_only_with_its_inputs() -> None:
    spec = _Spec({"estimation.optimizer": "fides"})
    petab = _tables()
    k1, parts = reuse.fit_fingerprint(petab, None, None, spec, 7)
    k2, _ = reuse.fit_fingerprint(petab, None, None, spec, 7)
    check("the same inputs give the same fingerprint", k1 == k2)
    check(
        "the seed is in it",
        reuse.fit_fingerprint(petab, None, None, spec, 8)[0] != k1,
    )
    check(
        "optimiser options are in it",
        reuse.fit_fingerprint(petab, None, None, spec, 7, {"maxiter": 9})[0] != k1,
    )
    real = reuse._code
    reuse._code = lambda *objs: "an engine fix"
    try:
        check(
            "the engine's estimation code is in it (a fix recomputes)",
            reuse.fit_fingerprint(petab, None, None, spec, 7)[0] != k1,
        )
    finally:
        reuse._code = real
    petab = _more_data(petab)
    check(
        "the data are in it",
        reuse.fit_fingerprint(petab, None, None, spec, 7)[0] != k1,
    )
    check(
        "the parts are recorded, not only hashed",
        set(parts) >= {"problem", "solver", "seed", "code", "versions"}
        and "n_starts" not in parts,
        str(sorted(parts)),
    )


def _fake_fit(est: Node, key: str, n: int = 50) -> None:
    """A work group holding a fit's three records and its fingerprint."""
    for name in reuse.FIT_KEYS:
        (est / name).put_text("x")
    (est / reuse.FIT_KEY).put({"key": key, "n_starts": n})


def test_the_code_hash_ignores_comments_and_docstrings() -> None:
    """A comment or docstring edit keeps the code hash; a code edit moves it."""
    import types

    def build(src: str):
        mod = types.ModuleType("probe_mod")
        exec(compile(src, "<probe>", "exec"), mod.__dict__)
        return mod

    import inspect as _inspect

    base = 'def f(x):\n    """Sum."""\n    return x + 1  # add one\n'
    variants = {
        "comment": 'def f(x):\n    """Sum."""\n    return x + 1  # a different note\n',
        "docstring": 'def f(x):\n    """Add one to x."""\n    return x + 1\n',
        "code": 'def f(x):\n    """Sum."""\n    return x + 2\n',
    }
    real = _inspect.getsource
    try:
        hashes = {}
        for name, src in {"base": base, **variants}.items():
            fn = build(src).f
            _inspect.getsource = lambda obj, _s=src: _s
            hashes[name] = reuse._code(fn)
    finally:
        _inspect.getsource = real
    check(
        "a comment or docstring edit keeps the code hash, a code edit moves it",
        hashes["comment"] == hashes["base"] == hashes["docstring"]
        and hashes["code"] != hashes["base"],
        str(hashes),
    )


def test_the_code_hash_ignores_the_timing_instrumentation() -> None:
    """A change to a `timing.span(...)` (added, removed, its detail changed)
    keeps the fingerprinted code; a change to what the block computes moves it
    (stored fits and profiles survive an edit of the time account)."""
    plain = (
        "def fit(problem, n):\n"
        "    result = minimize(problem, n)\n"
        "    return result\n"
    )
    spanned = (
        "@timing.timed('compute', 'fit')\n"
        "def fit(problem, n):\n"
        "    from octomod.orchestration import timing as _timing\n"
        "    with _timing.span('compute', 'fit', n_starts=int(n)) as _span:\n"
        "        result = minimize(problem, n)\n"
        "        _span.update(work_units(result))\n"
        "        _span['extra'] = 1\n"
        "    return result\n"
    )
    respanned = spanned.replace("n_starts=int(n)", "n_starts=n, engine='x'")
    with_lock = (
        "def fit(problem, n):\n"
        "    with lock(n), timing.span('compute', 'fit'):\n"
        "        result = minimize(problem, n)\n"
        "    return result\n"
    )
    locked = (
        "def fit(problem, n):\n"
        "    with lock(n):\n"
        "        result = minimize(problem, n)\n"
        "    return result\n"
    )
    real_change = spanned.replace("minimize(problem, n)", "minimize(problem, 2 * n)")
    other_update = plain.replace(
        "    return result", "    result.update(x)\n    return result"
    )
    t = reuse._code_text
    check(
        "sources differing only by a timing span fingerprint equal",
        t(plain) == t(spanned) == t(respanned) and t(with_lock) == t(locked),
        t(spanned),
    )
    check(
        "a real code change (or an `.update` on a non-span) still moves it",
        t(real_change) != t(spanned)
        and t(other_update) != t(plain)
        and t(locked) != t(plain),
    )


def test_find_prefers_the_own_fit_then_the_run_index() -> None:
    with temp_record() as run:
        own = work(run, 1, "b")
        other = work(run, 0, "a")
        _fake_fit(other, "K", 100)
        (run / reuse.FIT_INDEX_KEY).put({"K": [{"work": other.key, "n_starts": 100}]})
        check(
            "an indexed fit elsewhere in the run is found",
            reuse.find_fit(run, own, "K", 100) == other,
        )
        check(
            "a fit with MORE starts answers a smaller request",
            reuse.find_fit(run, own, "K", 50) == other,
        )
        check(
            "a fit with fewer starts does not",
            reuse.find_fit(run, own, "K", 101) is None,
        )
        _fake_fit(own, "K", 100)
        check(
            "the candidate's own fit is preferred",
            reuse.find_fit(run, own, "K", 100) == own,
        )
        check(
            "a different fingerprint finds nothing",
            reuse.find_fit(run, own, "OTHER", 1) is None,
        )
        (other / "multistart").delete()
        (own / "multistart").delete()
        check(
            "an incomplete group is never reused",
            reuse.find_fit(run, own, "K", 1) is None,
        )
        dest = work(run, 2, "c")
        _fake_fit(other, "K")
        (other / "decisions/estimation_convergence").put({})
        (other / reuse.PROFILES_KEY).put({})
        copied = reuse.adopt_fit(other, dest)
        check(
            "adopting copies the fit, the convergence decision and the profiles made on it",
            {
                "multistart",
                "decisions/estimation_convergence",
                reuse.PROFILES_KEY,
                reuse.FIT_KEY,
            }
            <= set(copied),
            str(copied),
        )
        reuse.record_fit(run, dest, "K", {"problem": "P1"}, 30, 12.5)
        reuse.record_fit(run, dest, "K", {"problem": "P1"}, 40, 12.0)
        entries = (run / reuse.FIT_INDEX_KEY).get()["K"]
        check(
            "re-recording a work group replaces its index entry",
            [e["n_starts"] for e in entries if e["work"] == dest.key] == [40],
            str(entries),
        )
        check(
            "fits are findable by problem, whatever their settings",
            [e["work"] for e in reuse.fits_of_problem(run, "P1")] == [dest.key],
        )


def _context(
    tmp: Node, candidate: str, round_idx: int = 0, *, costed: bool = True
) -> RunContext:
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    ctx = RunContext(
        root=tmp,
        testcase_dir=REPO / "testcase" / "toy_phos_petab",
        spec=spec,
        ledger=Ledger(tmp.store),
        backend="stub",
        auto=False,
    )
    ctx.round_idx = round_idx
    (tmp / "intent").put(
        {
            "question": "unit test",
            "system": "toy",
            "inference_target": "parameter_values",
        }
    )
    ctx.candidate = candidate
    # the candidate's assembled problem (`WK/petab`) and its model (`WK/model/sbml`)
    inp = _tables()
    petab_io.to_record(inp, ctx.work / "petab")
    (ctx.model / "sbml").put_text(inp.sbml)
    if costed:
        (ctx.work / "cost").put({"median_start_s": 0.1, "compile_s": 0.0})
        ctx.set_marker("cost", approved_n_starts=4, median_start_s=0.1)
    return ctx


def _set_measurements(ctx, inp: petab_io.PetabInput) -> None:
    """Replace the candidate's measurement table."""
    (ctx.work / "petab" / "measurements").put_table(inp.measurements)


def _estimate(ctx, n: int) -> str:
    from octomod.workflow_modules.estimation import engine as estimation_module

    humangate.configure_file_mode(ctx.root, None, "")
    try:
        estimation_module.run(ctx, n)
        return "done"
    except humangate.GatePending:
        return "paused at the convergence gate"


def test_a_real_fit_is_reused_not_recomputed() -> None:
    import logging

    from octomod.workflow_modules.estimation import engine as estimation_module

    logging.disable(logging.WARNING)
    real = estimation_module.run_multistart
    calls: list[int] = []

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    estimation_module.run_multistart = counting
    try:
        with temp_record() as tmp:
            ctx = _context(tmp, "cand_a")
            first = _estimate(ctx, 4)
            check(
                "the first pass fits (one multistart)",
                len(calls) == 1,
                f"{first}; calls {len(calls)}",
            )
            est = ctx.work
            check(
                "the fingerprint is written beside the fit",
                (est / reuse.FIT_KEY).exists(),
            )
            # a resume: the s6 marker is set only after the gate, so it may be absent
            ctx.marker("s6").delete()
            ctx.cache.clear()
            second = _estimate(ctx, 4)
            rows = [e for e in ctx.ledger.entries() if e.get("fit_reused")]
            check(
                "a second pass over the same candidate loads the fit — no multistart",
                len(calls) == 1
                and rows
                and rows[-1].get("reused_from") == "this candidate's own group",
                f"{second}; calls {len(calls)}; rows {len(rows)}",
            )
            ctx2 = _context(tmp, "cand_b")
            _estimate(ctx2, 4)
            rows = [e for e in ctx2.ledger.entries() if e.get("fit_reused")]
            check(
                "a second candidate with the identical problem adopts the first one's fit",
                len(calls) == 1
                and rows
                and "candidates/cand_a" in str(rows[-1].get("reused_from")),
                f"calls {len(calls)}; from {rows[-1].get('reused_from') if rows else None}",
            )
            ctx2.marker("s6").delete()
            ctx2.cache.clear()
            _estimate(ctx2, 5)
            check(
                "MORE starts than in the record recompute",
                len(calls) == 2,
                f"calls {len(calls)}",
            )
            ctx3 = _context(tmp, "cand_c")
            _estimate(ctx3, 3)
            rows = [e for e in ctx3.ledger.entries() if e.get("fit_reused")]
            check(
                "FEWER starts reuse the larger fit (the same search, more of it)",
                len(calls) == 2 and rows and rows[-1].get("n_starts_reused") == 5,
                f"calls {len(calls)}; reused {rows[-1].get('n_starts_reused') if rows else None}",
            )
    finally:
        estimation_module.run_multistart = real
        logging.disable(logging.NOTSET)


def test_the_next_rounds_base_is_neither_probed_nor_refitted() -> None:
    """Round 1's base is round 0's fitted problem: no probe, no budget, no refit."""
    import logging

    from octomod.workflow_modules.cost_probe import engine as cost_profile
    from octomod.workflow_modules.estimation import engine as estimation_module

    logging.disable(logging.WARNING)
    real6, realc = estimation_module.run_multistart, cost_profile.run_multistart
    calls: list[str] = []

    def counting6(*a, **k):
        calls.append("fit")
        return real6(*a, **k)

    def countingc(*a, **k):
        calls.append("probe")
        return realc(*a, **k)

    estimation_module.run_multistart, cost_profile.run_multistart = counting6, countingc
    try:
        with temp_record() as tmp:
            ctx0 = _context(tmp, "winner", 0)
            _estimate(ctx0, 4)
            check("round 0 fits its winner once", calls == ["fit"], str(calls))
            ctx1 = _context(tmp, "base", 1, costed=False)
            ctx1.set_marker("s3", n_estimated=0)
            found = cost_profile.fit_already_on_disk(ctx1, 4)
            check(
                "before pricing: the base's fit is found in the record, in round 0",
                bool(found) and found["from"] == work(tmp, 0, "winner").key,
                str(found and found.get("from")),
            )
            check(
                "… and not for more starts than it has",
                cost_profile.fit_already_on_disk(ctx1, 5) is None,
            )
            n = cost_profile.run(ctx1, ask_human=False, n_candidates=2, preapproved_n=4)
            marker = ctx1.marker("cost").get()
            prof = (ctx1.work / "cost").get()
            check(
                "the cost module neither probes nor budgets it",
                n == 4
                and calls == ["fit"]
                and marker.get("reused_fit")
                and prof.get("reused_fit"),
                f"calls {calls}; marker {marker.get('reused_fit')}",
            )
            check(
                "its cost record still satisfies the compiled slot",
                "median_start_s" in prof and "compile_s" in prof,
            )
            _estimate(ctx1, 4)
            rows = [
                e
                for e in ctx1.ledger.entries()
                if e.get("fit_reused") and e.get("round") == 1
            ]
            check(
                "S6 adopts the round-0 fit — no multistart in round 1",
                calls == ["fit"]
                and rows
                and "round_0" in str(rows[-1].get("reused_from")),
                f"calls {calls}",
            )
            other = _context(tmp, "other", 1, costed=False)
            _set_measurements(other, _more_data(_tables(), 1))
            check(
                "a different problem is not found",
                cost_profile.fit_already_on_disk(other, 4) is None,
            )
            _the_round_is_priced_on_what_it_will_spend(tmp)
    finally:
        estimation_module.run_multistart, cost_profile.run_multistart = real6, realc
        logging.disable(logging.NOTSET)


def _the_round_is_priced_on_what_it_will_spend(tmp: Node) -> None:
    """Costly candidates go first, fits in the record last; all there means no budget."""
    from types import SimpleNamespace

    from octomod.orchestration.orchestrator import Orchestrator

    _context(tmp, "same", 1, costed=False)  # round 0's winner, not yet costed
    ctx = _context(tmp, "fresh", 1, costed=False)
    _set_measurements(ctx, _more_data(_tables(), 2))
    ctx.candidate = None
    # the proposal the 4-start round-0 fit answers (the spec's floor is 10,
    # which a 4-start fit rightly does NOT answer)
    ctx.spec.raw["estimation"]["n_starts_bounds"] = [1, 1000]
    ctx.cache["n_starts_override"] = 4
    fake = SimpleNamespace(ctx=ctx, ledger=ctx.ledger)
    order, lines, n = Orchestrator._order_by_fit_on_disk(fake, ["same", "fresh"])
    check(
        "the candidate that costs is fitted first and the one on disk last",
        order == ["fresh", "same"] and n is None,
        f"{order}, n={n}",
    )
    check(
        "the budget card names the one on disk, where from, and what refits it",
        len(lines) == 1
        and lines[0].startswith(f"same: already fitted — {work(tmp, 0, 'winner').key}")
        and "n= above 4, `tighten` or `adjoint` here refits it" in lines[0],
        " | ".join(lines),
    )
    order, lines, n = Orchestrator._order_by_fit_on_disk(fake, ["same"])
    rows = [
        e for e in ctx.ledger.entries() if "budget gate not asked" in str(e.get("note"))
    ]
    check(
        "with every candidate on disk no budget is asked: the proposal is the approval",
        n == 4 and rows,
        f"n={n}; rows {len(rows)}",
    )


def test_profiles_are_reused_only_for_the_same_problem_optimum_and_settings() -> None:
    spec = _Spec(
        {
            "uncertainty.profile_next_guess": "adaptive_step_order_0",
            "uncertainty.profile_step_sizes": {"default_step_size": 0.01},
        }
    )
    summary = {"best_x_unscaled": {"k1": 0.5, "k2": 2.0}, "best_fval": 10.0}
    with temp_record() as t:
        petab = _tables()
        est = work(t, 0)
        key, parts = reuse.profile_fingerprint(petab, summary, spec)
        check("nothing stored, nothing loaded", reuse.load_profiles(est, key) is None)
        reuse.store_profiles(est, key, parts, {"k1": {"ci95": [0.1, 1.0]}})
        check(
            "stored profiles are loaded for the same key",
            reuse.load_profiles(est, key) == {"k1": {"ci95": [0.1, 1.0]}},
        )
        moved = dict(summary, best_x_unscaled={"k1": 0.51, "k2": 2.0})
        check(
            "a different optimum is a different key",
            reuse.profile_fingerprint(petab, moved, spec)[0] != key,
        )
        other = _Spec(
            dict(spec, **{"uncertainty.profile_next_guess": "adaptive_step_order_1"})
        )
        check(
            "a different profile setting is a different key",
            reuse.profile_fingerprint(petab, summary, other)[0] != key,
        )
        check(
            "the profile code is in it",
            "code" in parts and "versions" in parts,
            str(sorted(parts)),
        )


def test_a_predeclared_accept_survives_a_restart() -> None:
    from octomod.workflow_modules.estimation.engine import predeclared_from_ledger

    class Ctx:
        def __init__(self, root, r):
            self.ledger = Ledger(root.store)
            self.round_idx = r

    with temp_record() as t:
        ctx = Ctx(t, 1)
        ctx.ledger.append(
            "human_gate", module="cost_boundary_estimation", round_idx=1, approved=True
        )
        ctx.ledger.append(
            "note",
            module="cost_boundary_estimation",
            round_idx=1,
            note="…",
            convergence_predeclared=True,
            predeclared_reason="bounds, projected gradient 0.1",
        )
        check(
            "the reason is read back from the ledger",
            predeclared_from_ledger(ctx) == "bounds, projected gradient 0.1",
        )
        check(
            "another round's declaration does not count",
            predeclared_from_ledger(Ctx(t, 2)) is None,
        )
        ctx.ledger.append(
            "human_gate", module="cost_boundary_estimation", round_idx=1, approved=True
        )
        check(
            "a later budget answer without one withdraws it",
            predeclared_from_ledger(ctx) is None,
        )


def main() -> int:
    print("reuse instead of recompute — fits, profiles, pre-declared decisions")
    test_the_fit_fingerprint_moves_only_with_its_inputs()
    test_the_code_hash_ignores_comments_and_docstrings()
    test_the_code_hash_ignores_the_timing_instrumentation()
    test_find_prefers_the_own_fit_then_the_run_index()
    test_a_real_fit_is_reused_not_recomputed()
    test_the_next_rounds_base_is_neither_probed_nor_refitted()
    test_profiles_are_reused_only_for_the_same_problem_optimum_and_settings()
    test_a_predeclared_accept_survives_a_restart()
    return finish("\nREUSE", "REUSE OK")


if __name__ == "__main__":
    sys.exit(main())
