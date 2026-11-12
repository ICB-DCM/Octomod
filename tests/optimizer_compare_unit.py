"""The optimiser comparison's metrics and decisions, checked on hand-built numbers.

  1. the success threshold is chi2.ppf(1 - alpha, 1) / 2;
  2. optimality gap, successes and overall efficiency match hand-computed numbers;
  3. an uninstalled optimiser is scored on no metric; a budget-stopped one is NOT RUN;
  4. the incumbent runs first; "materially better" means beyond the threshold;
  5. availability is by import; every shipped candidate is known, fides among them;
  6. the comparison's start count is derived from the budget and never exceeds it;
  7. every shipped candidate carries its benchmark score;
  8. the remedy tells "more starts" apart from "a different optimiser";
  9. only a conclusive edge displaces the default; explicit > selected > default;
 10. the probe trigger reads a hit rate, not one bad start;
 11. a failed start counts against its method; the verdict needs a resolved incumbent;
 12. the budget card projects the cost of the optimiser the run will use;
 13. one alpha decides the successes and the switch; every spec optimiser name builds;
 14. a gate comparison keeps the run's selection and refits with a conclusive winner;
 15. the payload defines both metrics in words.

    uv run python tests/optimizer_compare_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))  # `_record`: the run's record in tests

from _harness import check, finish  # noqa: E402

from octomod.workflow_modules.estimation import optimizer_compare as oc  # noqa: E402


def row_n(name, fvals, wall, n_attempted):
    """A row that distinguishes ATTEMPTED starts from surviving results."""
    return oc.MethodResult(
        name, name, True, fvals=list(fvals), n_attempted=n_attempted, wall_s=wall
    )


def row(name, fvals, wall, available=True, reason=""):
    return oc.MethodResult(
        name, name, available, reason=reason, fvals=list(fvals), wall_s=wall
    )


def test_threshold() -> None:
    thr = oc.success_threshold(0.05)
    check(
        "the success threshold is chi2.ppf(1-alpha,1)/2",
        abs(thr - 1.9207) < 1e-3,
        f"{thr:.4f} at alpha=0.05",
    )
    check(
        "a tighter alpha demands a smaller gap",
        oc.success_threshold(0.01) > thr,
        f"alpha=0.01 -> {oc.success_threshold(0.01):.4f}",
    )


def test_metrics_against_hand_numbers() -> None:
    # DE: best -101, all 4 starts within 1.92 of it, 20 s  -> t/succ 5.0, OE 1
    # fides: best -100 (gap 1.0), only that one start inside, 40 s -> t/succ 40
    # powell: best -80 (gap 21), no start inside, 10 s -> t/succ inf, OE 0
    rows = oc.score(
        [
            row("fides", [-100.0, -99.0, -50.0, -50.0], 40.0),
            row("scipy_de", [-101.0, -101.0, -100.5, -100.0], 20.0),
            row("scipy_powell", [-80.0, -79.0], 10.0),
        ]
    )
    by = {r.name: r for r in rows}
    check(
        "optimality gap is best-of-method minus best-of-field",
        abs(by["scipy_de"].optimality_gap) < 1e-12
        and abs(by["fides"].optimality_gap - 1.0) < 1e-12
        and abs(by["scipy_powell"].optimality_gap - 21.0) < 1e-12,
        f"de={by['scipy_de'].optimality_gap} fides={by['fides'].optimality_gap} "
        f"powell={by['scipy_powell'].optimality_gap}",
    )
    check(
        "a start counts as successful only within the threshold of the best",
        by["scipy_de"].n_success == 4 and by["fides"].n_success == 1,
        f"de {by['scipy_de'].n_success}/4, fides {by['fides'].n_success}/4 "
        f"(fides' -99.0 is 2.0 from the best, outside 1.92)",
    )
    check(
        "overall efficiency is min(t/succ) / (t/succ), best = 1",
        abs(by["scipy_de"].overall_efficiency - 1.0) < 1e-12
        and abs(by["fides"].overall_efficiency - 0.125) < 1e-12,
        f"de={by['scipy_de'].overall_efficiency:.3f} (20/4=5s per success), "
        f"fides={by['fides'].overall_efficiency:.3f} (40/1=40s, 5/40)",
    )
    check(
        "1/OE reads as 'this many times longer per successful start'",
        abs(1 / by["fides"].overall_efficiency - 8.0) < 1e-9,
        "fides needs 8x the time of DE to buy one successful start",
    )
    check(
        "no successful starts gives OE 0, not a crash and not a win",
        by["scipy_powell"].overall_efficiency == 0.0,
        f"powell OE={by['scipy_powell'].overall_efficiency}",
    )


def test_unavailable_is_not_a_loss() -> None:
    """pyPESTO returns fval=inf for a missing package: absence, not a loss."""
    rows = oc.score(
        [
            row("fides", [-100.0, -100.0], 10.0),
            row(
                "cmaes", [], 0.0, available=False, reason="not installed (needs `cma`)"
            ),
        ]
    )
    cm = next(r for r in rows if r.name == "cmaes")
    import math

    check(
        "an unavailable optimiser is scored on NEITHER metric",
        math.isnan(cm.optimality_gap) and math.isnan(cm.overall_efficiency),
        f"gap={cm.optimality_gap} oe={cm.overall_efficiency}",
    )
    v = oc.verdict(rows)
    check(
        "and it is named as unavailable in the verdict",
        v["unavailable"] == ["cmaes"] and v["winner"] == "fides",
        f"{v['unavailable']}, winner={v['winner']}",
    )
    check(
        "the table says UNAVAILABLE rather than ranking it last",
        any("UNAVAILABLE" in ln and "cma" in ln for ln in oc.table_lines(rows)),
        [ln for ln in oc.table_lines(rows) if "UNAVAILABLE" in ln][:1],
    )
    # A method the budget stopped before it started is installed; UNAVAILABLE
    # would tell the reader to install a package they already have.
    skipped = oc.score(
        [
            row("fides", [-100.0], 1.0),
            oc.MethodResult(
                "nlopt_lbfgs",
                oc.BACKENDS["nlopt_lbfgs"][1],
                False,
                reason="the comparison's 2s budget was spent before it started",
                not_run=True,
            ),
        ]
    )
    line = [ln for ln in oc.table_lines(skipped) if "nlopt" in ln.lower()]
    check(
        "a method the budget stopped reads NOT RUN, not UNAVAILABLE",
        line and "NOT RUN" in line[0] and "UNAVAILABLE" not in line[0],
        line[0].strip() if line else "no row",
    )


def test_the_incumbent_runs_first() -> None:
    """The incumbent runs first, so an exhausted budget still leaves its row."""
    import pypesto.optimize as po

    seen: list[str] = []
    real = po.minimize

    def recorder(**kw):
        seen.append(kw["optimizer"].__class__.__name__)
        raise RuntimeError("not a real fit — this test is about ORDER")

    po.minimize = recorder
    try:
        rows = oc.compare(
            None,
            methods=["cmaes", "fides", "scipy_lbfgsb"],
            n_starts=1,
            seed=0,
            incumbent="fides",
        )
    finally:
        po.minimize = real
    check(
        "the incumbent is the first method actually run",
        bool(seen) and "Fides" in seen[0],
        f"order: {seen}",
    )
    check(
        "and every candidate still appears in the result",
        sorted(r.name for r in rows) == ["cmaes", "fides", "scipy_lbfgsb"],
        f"{[r.name for r in rows]}",
    )


def test_materially_better_uses_the_threshold() -> None:
    thr = oc.success_threshold()
    # incumbent beaten by LESS than the threshold: the data cannot tell them
    # apart, so this is a speed result, not a reason to switch.
    near = oc.score([row("fides", [-100.0], 1.0), row("scipy_de", [-100.0 - 0.5], 1.0)])
    check(
        "a gap inside the threshold is NOT materially better",
        oc.verdict(near)["materially_better"] is False,
        f"gap 0.5 against threshold {thr:.3f}",
    )
    far = oc.score([row("fides", [-100.0], 1.0), row("scipy_de", [-100.0 - 25.0], 1.0)])
    check(
        "a gap outside the threshold IS materially better",
        oc.verdict(far)["materially_better"] is True,
        f"gap 25.0 against threshold {thr:.3f}",
    )
    check(
        "and the incumbent winning is reported as such",
        oc.verdict(
            oc.score([row("fides", [-100.0], 1.0), row("scipy_de", [-90.0], 1.0)])
        )["incumbent_is_best"]
        is True,
    )


def test_availability_is_by_import() -> None:
    ok, _ = oc.available("fides")
    check("fides is available in this environment", ok)
    ok_unknown, why = oc.available("no_such_optimiser")
    check(
        "an unknown name is refused by name",
        not ok_unknown and "unknown" in why,
        why,
    )
    # every candidate the shipped spec names must at least be a known name,
    # or the gate would refuse at runtime with a spec the repo shipped
    import yaml

    spec = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())
    cands = spec["estimation"]["optimizer_compare"]["candidates"]
    unknown = [c for c in cands if c not in oc.BACKENDS]
    check(
        "every optimiser the shipped spec names is known to the module",
        not unknown,
        f"unknown: {unknown}" if unknown else f"{len(cands)} candidates",
    )
    check(
        "fides is among them — a comparison without the incumbent is meaningless",
        "fides" in cands,
        str(cands),
    )


def test_the_comparison_is_sized_from_the_budget() -> None:
    """The start count is derived from the allowance, so it cannot exceed it."""
    p100 = oc.plan(3, 100, 1.0, fraction=0.35, min_starts=3)
    check(
        "a 100-start estimation affords a usable comparison",
        p100 is not None and p100["n_starts"] >= 3,
        f"{p100['n_starts']} starts each" if p100 else "None",
    )
    check(
        "and it never exceeds the budget it was derived from",
        p100["projected_s"] <= p100["budget_s"],
        f"projected {p100['projected_s']:g}s of {p100['budget_s']:g}s",
    )
    check(
        "a small estimation buys no comparison and returns None rather than failing",
        oc.plan(3, 20, 1.0, fraction=0.35, min_starts=3) is None,
        "a 20-start fit cannot afford 3 starts on each of 3 methods",
    )
    check(
        "an unmeasured per-start time buys nothing either",
        oc.plan(3, 100, None, fraction=0.35, min_starts=3) is None,
        "None rather than a guess",
    )
    asked = oc.plan(3, 20, 1.0, fraction=0.35, min_starts=3, on_request=True)
    check(
        "but a HUMAN asking for that same small comparison gets it",
        asked is not None and asked["n_starts"] == 3 and asked["over_budget"],
        "a fraction of the fit is the wrong bound on something a person typed",
    )
    check(
        "and the wall-clock stop is the projection, not the smaller allowance",
        asked["stop_s"] >= asked["projected_s"],
        f"stop {asked['stop_s']:g}s covers the projected {asked['projected_s']:g}s "
        f"(the allowance alone was {asked['budget_s']:g}s, which would have cut "
        f"the comparison off mid-way)",
    )
    check(
        "an affordable comparison still stops at its allowance",
        p100["stop_s"] == p100["budget_s"] and not p100["over_budget"],
        f"{p100['stop_s']:g}s",
    )
    check(
        "an unmeasured per-start time is refused even on request",
        oc.plan(3, 20, None, fraction=0.35, min_starts=3, on_request=True) is None,
        "asking cannot conjure a projection",
    )
    over = [
        n
        for n in range(1, 2001)
        for pl in [oc.plan(3, n, 1.0, fraction=0.35, min_starts=3)]
        if pl is not None and pl["projected_s"] > pl["budget_s"]
    ]
    check(
        "over every estimation size from 1 to 2000 starts, never over budget",
        not over,
        f"{len(over)} violations" if over else "0 violations",
    )
    import yaml

    est = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())[
        "estimation"
    ]
    c = est["optimizer_compare"]
    n_others = len([x for x in c["candidates"] if x != oc.DEFAULT_OPTIMIZER])
    shipped = oc.plan(
        n_others,
        est["n_starts_default"],
        1.0,
        fraction=c["max_budget_fraction"],
        min_starts=c["min_compare_starts"],
    )
    check(
        "the shipped spec affords a comparison at the default start count",
        shipped is not None,
        (
            f"{shipped['n_starts']} starts each at n={est['n_starts_default']}"
            if shipped
            else "the shipped numbers buy nothing — the feature would never run"
        ),
    )


def test_candidates_are_evidence_ordered() -> None:
    """Every shipped candidate's label carries its benchmark score."""
    import re as _re

    import yaml

    cands = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())[
        "estimation"
    ]["optimizer_compare"]["candidates"]
    labels = {n: oc.BACKENDS[n][1] for n in cands}
    unscored = [n for n, lab in labels.items() if not _re.search(r"\[\d+/30\]", lab)]
    check(
        "every shipped candidate carries its benchmark score",
        not unscored,
        f"unscored: {unscored}" if unscored else ", ".join(labels.values()),
    )
    for name in ("scipy_de", "scipy_powell"):
        check(
            f"{name} is labelled as NOT benchmarked",
            "not benchmarked" in oc.BACKENDS[name][1],
            oc.BACKENDS[name][1],
        )
        check(
            f"and {name} is not in the shipped list",
            name not in cands,
            str(cands),
        )


def test_remedy_separates_more_starts_from_a_worse_optimiser() -> None:
    """Too few starts asks for more starts, not for a different optimiser."""
    # the incumbent ties on BEST but got there far less often: fragile, not
    # wrong, and the remedy is starts.
    fragile = oc.score(
        [
            row("fides", [-100.0] + [-60.0] * 7, 10.0),
            row("scipy_de", [-100.0] * 8, 10.0),
        ]
    )
    v = oc.verdict(fragile)
    check(
        "a tie on best value with a much lower success rate asks for MORE STARTS",
        v["remedy"] == "more_starts",
        f"remedy={v['remedy']} rate={v['incumbent_success_rate']:.0%} "
        f"best={v['best_success_rate']:.0%}",
    )
    check(
        "and it says how many starts, from the observed rate",
        v["starts_for_95pc"] == oc.starts_for_confidence(1 / 8),
        f"{v['starts_for_95pc']} starts for 95% at a 1-in-8 rate",
    )
    check(
        "and it does NOT claim the current answer is wrong",
        "ANSWER is wrong" in v["remedy_detail"] and v["materially_better"] is False,
        v["remedy_detail"][:80],
    )
    # never reached the basin: starts cannot fix an observed rate of zero
    never = oc.score(
        [row("fides", [-60.0] * 8, 10.0), row("scipy_de", [-100.0] * 8, 10.0)]
    )
    v2 = oc.verdict(never)
    check(
        "an incumbent that never reached the basin asks for a DIFFERENT optimiser",
        v2["remedy"] == "different_optimizer" and v2["incumbent_success_rate"] == 0.0,
        f"remedy={v2['remedy']}",
    )
    # comparable rates, comparable values: the optimiser is not the problem
    fine = oc.score(
        [row("fides", [-100.0] * 8, 10.0), row("scipy_de", [-100.2] * 8, 5.0)]
    )
    check(
        "comparable methods ask for nothing",
        oc.verdict(fine)["remedy"] == "none",
        oc.verdict(fine)["remedy"],
    )


def test_a_worse_answer_always_has_a_zero_success_rate() -> None:
    """A method's best is its minimum: a gap beyond the threshold means no success."""
    import random

    thr = oc.success_threshold()
    random.seed(20260919)
    violations = 0
    for _ in range(2000):
        a = [random.uniform(-120, -40) for _ in range(random.randint(1, 8))]
        b = [random.uniform(-120, -40) for _ in range(random.randint(1, 8))]
        inc = oc.score([row("fides", a, 1.0), row("other", b, 1.0)])[0]
        if inc.optimality_gap > thr and inc.n_success > 0:
            violations += 1
    check(
        "gap > threshold implies no successful start, over 2000 random fields",
        violations == 0,
        f"{violations} violations",
    )


def test_starts_for_confidence() -> None:
    check(
        "a 1-in-4 rate needs 11 starts for 95% confidence",
        oc.starts_for_confidence(0.25) == 11,
        f"{oc.starts_for_confidence(0.25)}",
    )
    check(
        "a rarer success needs more starts",
        oc.starts_for_confidence(0.10) > oc.starts_for_confidence(0.25),
        f"{oc.starts_for_confidence(0.10)} vs {oc.starts_for_confidence(0.25)}",
    )
    check(
        "a rate of 0 or 1 has no answer, and says so rather than dividing",
        oc.starts_for_confidence(0.0) is None and oc.starts_for_confidence(1.0) is None,
        "None at both ends",
    )


def test_selection_is_conservative() -> None:
    """Only a conclusive edge displaces the default; a wrong switch costs a fit."""
    thr = oc.success_threshold()
    # 1. a materially better optimum displaces the default
    sel = oc.select(
        oc.score([row("fides", [-90.0] * 4, 10.0), row("cmaes", [-100.0] * 4, 10.0)])
    )
    check(
        "a gap outside the threshold displaces the default",
        sel["selected"] == "cmaes" and sel["conclusive"],
        f"{sel['selected']}: {sel['reason'][:70]}",
    )
    # 2. same answer, far better hit rate, over a sample big enough to count
    sel = oc.select(
        oc.score(
            [
                row_n("fides", [-100.0] + [-60.0] * 7, 10.0, 8),
                row_n("cmaes", [-100.0] * 8, 20.0, 8),
            ]
        )
    )
    check(
        "the same answer found far more reliably displaces the default",
        sel["selected"] == "cmaes",
        f"{sel['selected']}: 12% vs 100% over 8 starts each",
    )
    # 3. a SMALL edge does not
    sel = oc.select(
        oc.score(
            [
                row("fides", [-100.0] * 4, 10.0),
                row("cmaes", [-100.0 - thr / 2] * 4, 5.0),
            ]
        )
    )
    check(
        "an edge inside the likelihood-ratio threshold does NOT displace it",
        sel["selected"] == "fides",
        f"{sel['selected']}: a gap of {thr / 2:.3g} against a threshold of {thr:.3g}",
    )
    # 4. inconclusive keeps the default, and says so
    for label, rows_in in [
        ("only one optimiser ran", [row("fides", [-100.0] * 4, 10.0)]),
        (
            "the default did not run",
            [row("cmaes", [-100.0] * 4, 10.0), row("nlopt_lbfgs", [-100.0] * 4, 9.0)],
        ),
    ]:
        sel = oc.select(oc.score(rows_in))
        check(
            f"inconclusive ({label}) keeps the default and marks itself so",
            sel["selected"] == oc.DEFAULT_OPTIMIZER and sel["conclusive"] is False,
            f"{sel['selected']}, conclusive={sel['conclusive']}",
        )


def test_resolution_order() -> None:
    """An explicit spec value beats a selection in the record, which beats the default."""
    from _record import temp_record
    from _record import work as work_of

    from octomod.workflow_modules.estimation.problem import (
        SELECTION_KEY,
        resolve_optimizer,
    )

    class Spec:
        def __init__(self, value):
            self.value = value

        def get(self, key, default=None):
            return self.value if key == "estimation.optimizer" else default

    # the selection is a record group beside the fitted problem's `cost`
    with temp_record("resolution") as root:
        work = work_of(root, 0)
        (work / SELECTION_KEY).put({"selected": "cmaes", "reason": "measured"})
        name, why = resolve_optimizer(Spec("fides"), work)
        check(
            "an explicit spec value wins over a selection in the record",
            name == "fides" and "explicit" in why,
            f"{name} ({why})",
        )
        name, why = resolve_optimizer(Spec("auto"), work)
        check(
            "auto uses the run's selection when one exists",
            name == "cmaes" and "selected" in why,
            f"{name} ({why})",
        )
        empty = work_of(root, 1)
        name, why = resolve_optimizer(Spec("auto"), empty)
        check(
            "auto falls back to the default when nothing was selected",
            name == oc.DEFAULT_OPTIMIZER and "default" in why,
            f"{name} ({why})",
        )
        (work / SELECTION_KEY).put("not a selection")
        name, _ = resolve_optimizer(Spec("auto"), work)
        check(
            "an unreadable selection is no selection, not a crash",
            name == oc.DEFAULT_OPTIMIZER,
            name,
        )


def test_probe_trigger_reads_a_rate_not_an_outlier() -> None:
    """The probe trigger reads the default's hit rate, not one bad start."""
    from types import SimpleNamespace

    from octomod.workflow_modules.cost_probe.engine import _probe_hit_rate

    # pyPESTO's starts are objects with a `.fval`, and the helper reads them
    # that way, so the stand-in has to be one too.
    class Start:
        def __init__(self, fval):
            self.fval = fval

    def probe(fvals):
        return SimpleNamespace(
            optimize_result=SimpleNamespace(list=[Start(v) for v in fvals])
        )

    rate, why = _probe_hit_rate(probe([33.373, 33.373, 33.373, 33.373, 82.266]), 0.05)
    check(
        "one bad start of five is a rate of 80%, not a disagreement",
        abs(rate - 0.8) < 1e-9,
        why,
    )
    rate, _ = _probe_hit_rate(
        probe([-76.544, -76.544, -76.530, -76.515, -76.515]), 0.05
    )
    check(
        "the oscillator's five starts all agree — a rate of 100%",
        abs(rate - 1.0) < 1e-9,
        f"{rate:.0%}",
    )
    rate, why = _probe_hit_rate(probe([-100.0, -40.0, -40.0, -40.0, -40.0]), 0.05)
    check(
        "a default that reaches its optimum once in five is a rate of 20%",
        abs(rate - 0.2) < 1e-9,
        why,
    )
    rate, why = _probe_hit_rate(probe([]), 0.05)
    check(
        "a probe where nothing converged is a rate of 0, not a crash",
        rate == 0.0 and "finite" in why,
        why,
    )
    import yaml

    floor = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())[
        "estimation"
    ]["optimizer_compare"]["select_probe_rate_below"]
    check(
        "the shipped floor would skip both measured fixtures and fire on the third",
        0.2 < floor <= 0.8,
        f"floor {floor} against rates 80%, 100% and 20%",
    )


def test_a_failed_start_counts_against_the_method() -> None:
    """The rate is over attempted starts; `compare()` drops non-finite fvals."""
    rows = oc.score(
        [
            row_n("fides", [-100.0, -100.0, -60.0, -60.0, -60.0], 10.0, 5),
            row_n("cmaes", [-100.0, -100.0], 10.0, 8),  # 6 of 8 failed
        ]
    )
    by = {r.name: r for r in rows}
    check(
        "a method that failed 6 of 8 starts reads 2/8, not 2/2",
        by["cmaes"].n_attempted == 8,
        f"{by['cmaes'].n_success}/{by['cmaes'].n_attempted}",
    )
    check(
        "and it does not displace the default on a fabricated 100%",
        oc.select(rows)["selected"] == "fides",
        oc.select(rows)["reason"][:80],
    )
    check(
        "the table prints attempts, not survivors",
        any("2/8" in ln for ln in oc.table_lines(rows)),
        [ln for ln in oc.table_lines(rows) if "cmaes" in ln][:1],
    )


def test_verdict_needs_a_resolved_incumbent() -> None:
    """The spec word `auto` matches no row; the verdict needs the resolved name."""
    rows = oc.score(
        [row("fides", [-100.0] * 4, 10.0), row("cmaes", [-101.0] * 4, 10.0)]
    )
    dead = oc.verdict(rows, incumbent="auto")
    check(
        "an unresolved incumbent yields no verdict, so a caller passes the resolved name",
        dead["remedy"] == "inconclusive" and dead["incumbent_gap"] is None,
        f"remedy={dead['remedy']}",
    )
    live = oc.verdict(rows, incumbent="fides")
    check(
        "a resolved one yields a real verdict",
        live["remedy"] != "inconclusive" and live["incumbent_gap"] is not None,
        f"remedy={live['remedy']}, gap={live['incumbent_gap']}",
    )


def test_payload_is_self_describing() -> None:
    rows = oc.score(
        [row("fides", [-100.0, -99.0], 10.0), row("scipy_de", [-101.0], 5.0)]
    )
    payload = oc.as_json(rows)
    check(
        "the artifact defines both metrics in words",
        {"optimality_gap", "overall_efficiency", "success"}
        <= set(payload["metric_definitions"]),
        sorted(payload["metric_definitions"]),
    )
    check(
        "and carries the verdict plus one row per method",
        payload["verdict"]["winner"] == "scipy_de" and len(payload["methods"]) == 2,
    )


def test_one_alpha_decides_everything() -> None:
    """The spec's `success_alpha` moves the successes, the verdict and the switch."""
    rows = oc.score(
        [
            row_n("fides", [-97.0, -97.0], 1.0, 2),
            row_n("cmaes", [-100.0, -100.0], 1.0, 2),
        ],
        alpha=0.001,
    )
    v = oc.verdict(rows, "fides", alpha=0.001)
    check(
        "at the spec's alpha the incumbent's starts count as successful",
        rows[0].n_success == 2,
        f"{rows[0].n_success}/{rows[0].n_attempted} at a threshold of "
        f"{oc.success_threshold(0.001):.2f}",
    )
    check(
        "and the verdict does NOT then claim it reached the basin on none",
        v["remedy"] != "different_optimizer",
        f"remedy={v['remedy']}",
    )
    check(
        "nor does the selection switch on a threshold the spec moved",
        oc.select(rows, alpha=0.001)["selected"] == "fides",
        f"gap 3.0 is inside the spec's {oc.success_threshold(0.001):.2f}",
    )
    check(
        "the same numbers at the shipped alpha DO switch — the knob is live",
        oc.select(oc.score(rows, alpha=0.05), alpha=0.05)["selected"] == "cmaes",
        f"gap 3.0 is outside the shipped {oc.success_threshold(0.05):.2f}",
    )
    check(
        "and the artifact reports the threshold it actually used",
        abs(
            oc.as_json(rows, "fides", alpha=0.001)["verdict"]["threshold"]
            - oc.success_threshold(0.001)
        )
        < 1e-9,
    )


def test_the_spec_vocabulary_has_one_builder() -> None:
    """Every name `estimation.optimizer` accepts builds an optimiser."""
    from octomod.workflow_modules.estimation.problem import build_optimizer

    spec_names = ["auto", "fides", "scipy", *oc.BACKENDS]
    built, failed = [], []
    for name in spec_names:
        ok, _ = oc.available(name) if name in oc.BACKENDS else (True, "")
        if not ok:
            continue
        try:
            build_optimizer(name)
            built.append(name)
        except Exception as exc:
            failed.append(f"{name}: {type(exc).__name__}")
    check(
        "every installable name the spec accepts builds an optimiser",
        not failed,
        f"built {len(built)}" if not failed else f"FAILED {failed}",
    )
    check(
        "including the scipy fallback, which the bake-off's builder rejects",
        "scipy" in built,
        "estimation.optimizer: scipy builds, so S7 profiling can run with it",
    )
    try:
        build_optimizer("not_an_optimiser")
        ok = False
    except ValueError:
        ok = True
    check("and an unknown name is still refused by name", ok)


def test_the_budget_card_projects_the_optimiser_it_just_chose() -> None:
    """After a switch the budget card projects the chosen optimiser's cost."""
    from octomod.workflow_modules.cost_probe.engine import projection_start_s

    probe_s = 1.07
    kept = {"selected": "fides", "default": "fides", "start_s": 1.05}
    switched = {
        "selected": "cmaes",
        "default": "fides",
        "start_s": 9.66,
        "start_s_vs_default": 9.03,
    }
    check(
        "no comparison, no change: the probe's own number",
        projection_start_s(None, probe_s) == (probe_s, ""),
        f"{probe_s}s",
    )
    check(
        "a comparison that kept the default changes nothing either",
        projection_start_s(kept, probe_s) == (probe_s, ""),
        "the probe already timed this optimiser",
    )
    s_switch, line = projection_start_s(switched, probe_s)
    check(
        "a switch projects the CHOSEN optimiser's measured cost",
        s_switch == 9.66,
        f"{s_switch}s per start, not the probe's {probe_s}s — a "
        f"100-start fit is {100 * s_switch:.0f}s, not {100 * probe_s:.0f}s",
    )
    check(
        "and the card says so, with the ratio",
        "cmaes" in line and "9.0x" in line,
        line,
    )


def test_a_gate_comparison_keeps_the_runs_selection() -> None:
    """The gate writes the comparison last, so it must keep the probe's selection."""
    rows = oc.score([row("fides", [-100.0], 1.0), row("cmaes", [-100.0], 2.0)])
    sel = {"selected": "cmaes", "default": "fides", "conclusive": True, "reason": "x"}

    payload = oc.as_json(rows, "cmaes")
    check(
        "a gate comparison on its own carries no selection",
        "selection" not in payload,
        "nothing was chosen HERE — the gate measures, it does not select",
    )
    # the caller reads the `optimizer_selection` record and hands over
    # what it got — a dict, or whatever an absent or damaged group read as
    missing = oc.with_selection(dict(payload), None)
    check(
        "and no selection in the record leaves it that way",
        "selection" not in missing,
        "nothing to say is not the same as saying nothing",
    )
    merged = oc.with_selection(dict(payload), sel)
    check(
        "a selection made at the probe survives the gate's write",
        merged.get("selection", {}).get("selected") == "cmaes",
        f"{merged.get('selection', {}).get('selected')!r} — the report reads this key",
    )
    check(
        "an unreadable selection is no selection, not a crash",
        "selection" not in oc.with_selection(dict(payload), "{not a selection")
        and "selection" not in oc.with_selection(dict(payload), {"reason": "x"}),
    )


def test_the_gate_decides_and_refits_with_the_winner() -> None:
    """A conclusive comparison refits with the winner; otherwise the gate re-asks."""
    # a conclusively better answer: the incumbent never reaches the basin
    rows = oc.score(
        [row("fides", [-100.0, -100.0], 2.0), row("cmaes", [-110.0, -110.0], 4.0)]
    )
    d = oc.gate_decision(rows, "fides", refits_left=2)
    check(
        "a conclusively better optimiser is refitted with, now",
        d["action"] == "refit_with" and d["selection"]["selected"] == "cmaes",
        f"{d['action']} / {d['selection']['selected']}",
    )
    d = oc.gate_decision(rows, "fides", refits_left=0)
    check(
        "…unless the refit budget is spent, when the selection is filed and the "
        "gate is asked again",
        d["action"] == "return_to_gate"
        and d["selection"]["selected"] == "cmaes"
        and "budget" in d["why"],
        f"{d['action']} / {d['why'][:80]}",
    )
    # every method found the same optimum at the same rate: nothing to switch to
    rows = oc.score(
        [row("fides", [-100.0, -100.0], 2.0), row("cmaes", [-100.0, -100.0], 9.0)]
    )
    d = oc.gate_decision(rows, "fides", refits_left=2)
    check(
        "an inconclusive comparison returns to the gate with the incumbent kept",
        d["action"] == "return_to_gate" and d["selection"]["selected"] == "fides",
        f"{d['action']} / {d['selection']['selected']}",
    )
    # judged against the optimiser that produced THIS fit, not against fides
    rows = oc.score(
        [row("cmaes", [-100.0, -100.0], 2.0), row("fides", [-100.0, -100.0], 9.0)]
    )
    d = oc.gate_decision(rows, "cmaes", refits_left=2)
    check(
        "a run that had already switched is compared against what it ran",
        d["selection"]["default"] == "cmaes" and d["selection"]["selected"] == "cmaes",
        f"{d['selection']}",
    )


def main() -> int:
    print("threshold")
    test_threshold()
    print("metrics")
    test_metrics_against_hand_numbers()
    print("unavailable")
    test_unavailable_is_not_a_loss()
    print("materiality")
    test_the_incumbent_runs_first()
    test_materially_better_uses_the_threshold()
    print("budget")
    print("availability")
    test_availability_is_by_import()
    print("budget derivation")
    test_the_comparison_is_sized_from_the_budget()
    print("evidence")
    test_candidates_are_evidence_ordered()
    print("remedy")
    test_remedy_separates_more_starts_from_a_worse_optimiser()
    test_a_worse_answer_always_has_a_zero_success_rate()
    test_starts_for_confidence()
    print("selection")
    test_selection_is_conservative()
    test_resolution_order()
    print("probe trigger")
    test_probe_trigger_reads_a_rate_not_an_outlier()
    print("review fixes")
    test_a_failed_start_counts_against_the_method()
    test_verdict_needs_a_resolved_incumbent()
    print("budget honesty")
    test_the_budget_card_projects_the_optimiser_it_just_chose()
    print("one alpha")
    test_one_alpha_decides_everything()
    test_the_spec_vocabulary_has_one_builder()
    print("artifacts")
    test_a_gate_comparison_keeps_the_runs_selection()
    print("gate decision")
    test_the_gate_decides_and_refits_with_the_winner()
    print("payload")
    test_payload_is_self_describing()
    print()
    return finish(
        "OPTIMIZER COMPARE",
        "OPTIMIZER COMPARE OK — both metrics match hand numbers, an absent "
        "optimiser is not a defeated one, and the budget refuses to guess",
    )


if __name__ == "__main__":
    raise SystemExit(main())
