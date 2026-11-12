"""With `select_when: probe_rate_low`, the cost probe's own starts are the incumbent's row.

`_maybe_select_optimizer` is driven as the cost probe calls it, on a small
quadratic problem the challengers solve on every start, with a probe whose
default reached its optimum on one start of five:

  1. the rate is below the floor, so a comparison runs: the challengers only,
     never the default, and the default's row is built from the probe (its
     name, its five starts, one success, the probe's wall time) and put first;
  2. the challengers' far better rate on the same optimum switches the run:
     the selection is written where the fit reads it (`resolve_optimizer`),
     beside the comparison table, and ledgered;
  3. a probe at or above the floor runs nothing, builds no row, and says why;
  4. with the shipped `never`, the probe path builds no row and writes nothing.

    uv run python tests/probe_selection_unit.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check_detail_on_fail, finish  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.cost_probe import engine as cost_profile  # noqa: E402
from octomod.workflow_modules.estimation import optimizer_compare as oc  # noqa: E402
from octomod.workflow_modules.estimation import problem as estimation  # noqa: E402
from tests._record import temp_record  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
SEED = int(SPEC.get("estimation.seed"))
MEDIAN_START_S = 0.4
N_ESTIMATION_STARTS = 100
OPTIMUM, X_STAR = -100.0, np.array([1.0, 2.0])
# the default reached the optimum on one probe start of five, and one start
# failed outright: it counts against the default as an attempt
LOW_PROBE = [OPTIMUM, -40.0, -40.0, -40.0, float("nan")]
LOW_FINITE = LOW_PROBE[:4]
HIGH_PROBE = [OPTIMUM] * 5


# one challenger that needs no optional backend, so the outcome does not
# depend on what is installed
CANDIDATES = [oc.DEFAULT_OPTIMIZER, "scipy_lbfgsb"]


class Spec:
    """The shipped spec with `select_when` set and a one-challenger candidate set."""

    def __init__(self, base, select_when: str):
        self.base, self.select_when = base, select_when

    def get(self, k, d=None):
        if k == "estimation.optimizer_compare.select_when":
            return self.select_when
        if k == "estimation.optimizer_compare.candidates":
            return list(CANDIDATES)
        return self.base.get(k, d)

    def require(self, k):
        return self.base.require(k)


class Ctx:
    """What the selection reads off a RunContext."""

    def __init__(self, root: Node, spec):
        self.root, self.round_idx, self.candidate = root, 0, None
        self.spec, self.ledger = spec, Ledger(root.store)

    @property
    def work(self) -> Node:
        """The fitted problem's group of round 0 (`…/candidates/_single`)."""
        return tree.work_node(tree.round_node(self.root, 0), None)


def _problem():
    """A quadratic every gradient method solves from any start in the box."""
    import pypesto

    def fun(x):
        return float(np.sum((x - X_STAR) ** 2) + OPTIMUM)

    def grad(x):
        return 2.0 * (x - X_STAR)

    def hess(x):
        return 2.0 * np.eye(len(x))

    return pypesto.Problem(
        objective=pypesto.Objective(fun=fun, grad=grad, hess=hess),
        lb=np.array([-5.0, -5.0]),
        ub=np.array([5.0, 5.0]),
    )


class _Start:
    """A probe start as pyPESTO leaves it: an object with a `.fval`."""

    def __init__(self, fval):
        self.fval = fval


def _probe(fvals: list[float]):
    return SimpleNamespace(
        optimize_result=SimpleNamespace(list=[_Start(v) for v in fvals])
    )


@contextlib.contextmanager
def _recorded():
    """`row_from_probe` and `compare`, recorded and still the engine's own."""
    seen: dict[str, list] = {"rows": [], "compared": []}
    row0, compare0 = oc.row_from_probe, oc.compare

    def row(*a, **k):
        r = row0(*a, **k)
        seen["rows"].append(r)
        return r

    def compare(*a, **k):
        seen["compared"].append(list(k.get("methods") or []))
        return compare0(*a, **k)

    oc.row_from_probe, oc.compare = row, compare
    try:
        yield seen
    finally:
        oc.row_from_probe, oc.compare = row0, compare0


def _select(ctx: Ctx, probe):
    buf = io.StringIO()
    with _recorded() as seen, contextlib.redirect_stdout(buf):
        sel = cost_profile._maybe_select_optimizer(
            ctx,
            _problem(),
            SEED,
            MEDIAN_START_S,
            probe,
            N_ESTIMATION_STARTS,
        )
    return sel, seen, buf.getvalue()


def _notes(ctx: Ctx) -> list[str]:
    return [
        str(e.get("note"))
        for e in ctx.ledger.entries()
        if e.get("event") == "note" and e.get("module") == "cost_probe"
    ]


def test_a_low_rate_compares_on_the_probes_row(root: Node) -> None:
    ctx = Ctx(root, Spec(SPEC, "probe_rate_low"))
    sel, seen, printed = _select(ctx, _probe(LOW_PROBE))
    others = [c for c in CANDIDATES if c != oc.DEFAULT_OPTIMIZER]
    check_detail_on_fail(
        "a rate below the floor runs the comparison, on the challengers only",
        seen["compared"] == [others] and "struggling" in printed,
        f"{seen['compared']} · {printed[:200]}",
    )
    row = seen["rows"][0] if len(seen["rows"]) == 1 else None
    check_detail_on_fail(
        "the default's row is built from the probe: its name, label, finite "
        "values, all five attempts and the probe's wall time",
        row is not None
        and row.name == oc.DEFAULT_OPTIMIZER
        and row.label == oc.BACKENDS[oc.DEFAULT_OPTIMIZER][1]
        and row.available
        and row.fvals == LOW_FINITE
        and row.n_attempted == len(LOW_PROBE)
        and abs(row.wall_s - MEDIAN_START_S * len(LOW_PROBE)) < 1e-12,
        repr(row)[:240],
    )
    table = (ctx.work / "optimizer_comparison").get(None)
    methods = (table or {}).get("methods") or []
    first = methods[0] if methods else {}
    check_detail_on_fail(
        "in the comparison table it comes first, one success in five attempts "
        "(four finite) at the probe's wall time",
        first.get("name") == oc.DEFAULT_OPTIMIZER
        and first.get("n_attempted") == 5
        and first.get("n_finite") == 4
        and first.get("n_success") == 1
        and first.get("best_fval") == OPTIMUM
        and first.get("wall_s") == round(MEDIAN_START_S * 5, 3)
        and [m["name"] for m in methods[1:]] == others,
        str(first),
    )
    rates = {
        m["name"]: m["n_success"] / m["n_attempted"]
        for m in methods
        if m.get("n_attempted")
    }
    check_detail_on_fail(
        "the challengers reach the same optimum on every start",
        all(rates.get(c) == 1.0 for c in others),
        str(rates),
    )
    on_disk = (ctx.work / estimation.SELECTION_KEY).get(None)
    check_detail_on_fail(
        "the 20% rate the probe measured switches the run to a challenger",
        isinstance(sel, dict)
        and sel.get("default") == oc.DEFAULT_OPTIMIZER
        and sel.get("selected") in others
        and sel.get("conclusive") is True
        and "20%" in str(sel.get("reason"))
        and on_disk == sel,
        str(sel)[:240],
    )
    name, why = estimation.resolve_optimizer(ctx.spec, ctx.work)
    check_detail_on_fail(
        "the fit reads that selection back",
        name == (sel or {}).get("selected")
        and why.startswith("selected by comparison"),
        f"{name}: {why[:120]}",
    )
    rows = [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "note" and e.get("optimizer_selection")
    ]
    check_detail_on_fail(
        "and the ledger records the selection with its reason",
        len(rows) == 1
        and rows[0].get("optimizer_selection") == sel
        and f"optimiser selected: {(sel or {}).get('selected')}"
        in str(rows[0].get("note")),
        str(rows)[:240],
    )


def test_a_rate_at_the_floor_runs_nothing(root: Node) -> None:
    ctx = Ctx(root, Spec(SPEC, "probe_rate_low"))
    sel, seen, _printed = _select(ctx, _probe(HIGH_PROBE))
    check_detail_on_fail(
        "a probe at or above the floor compares nothing and builds no row",
        sel is None and seen == {"rows": [], "compared": []},
        f"{sel} · {seen}",
    )
    check_detail_on_fail(
        "and ledgers why, with the rate",
        any(
            n.startswith(
                "optimiser comparison not run: the default reached its best on "
                "5 of 5 probe starts (100%"
            )
            for n in _notes(ctx)
        ),
        str(_notes(ctx)),
    )
    check_detail_on_fail(
        "no selection is written",
        not (ctx.work / estimation.SELECTION_KEY).exists(),
    )


def test_never_builds_no_row(root: Node) -> None:
    ctx = Ctx(root, SPEC)
    check_detail_on_fail(
        "the shipped spec never selects at the probe",
        SPEC.get("estimation.optimizer_compare.select_when") == "never",
        str(SPEC.get("estimation.optimizer_compare.select_when")),
    )
    sel, seen, _printed = _select(ctx, _probe(LOW_PROBE))
    check_detail_on_fail(
        "with `never`, even a 20% probe builds no row and runs nothing",
        sel is None
        and seen == {"rows": [], "compared": []}
        and not ctx.work.exists()
        and _notes(ctx) == [],
        f"{sel} · {seen} · {_notes(ctx)}",
    )


def main() -> int:
    # one throwaway record per case, so each case's ledger holds only its own
    # rows
    with temp_record("low") as root:
        test_a_low_rate_compares_on_the_probes_row(root)
    with temp_record("high") as root:
        test_a_rate_at_the_floor_runs_nothing(root)
    with temp_record("never") as root:
        test_never_builds_no_row(root)
    return finish(
        "\nPROBE SELECTION",
        "\nPROBE SELECTION UNIT OK — a low probe rate buys a comparison whose "
        "incumbent row is the probe's own, the selection is written where the fit "
        "reads it, and `never` builds nothing",
    )


if __name__ == "__main__":
    sys.exit(main())
