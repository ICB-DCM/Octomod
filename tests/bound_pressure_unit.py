"""The expansion agent sees which fitted parameters the box holds back, and how hard.

  1. `bound_pressure` lists each parameter at a bound or within 2 % of one, no more;
  2. rows are ordered by the size of the pressing gradient component;
  3. a candidate with no fit in the record is skipped; the caller's candidate is restored;
  4. the expansion context, the skill and routing (revision only) carry it;
  5. on the machine-local run, `kdeph` heads the round-1 leader's list (else skipped).

    uv run python tests/bound_pressure_unit.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402
from _record import rnd, run_root, temp_record, work  # noqa: E402

from octomod import config  # noqa: E402
from octomod.agents import routing  # noqa: E402
from octomod.workflow_modules.evaluation.residuals import (  # noqa: E402
    BOUND_PRESSURE_NOTE,
    bound_pressure,
)

LIVE_RUN = "bodenmiller2012_20260924_201837"
LIVE_ROUND = 1


class Ctx:
    def __init__(self, round_node):
        self.round = round_node
        self.candidate = "caller_was_here"


PARAMS = (
    "parameterId\tparameterScale\tlowerBound\tupperBound\tnominalValue\testimate\n"
    "kdeph\tlog10\t0.001\t2\t0.1\t1\n"
    "c_bc\tlog10\t0.002\t10\t1\t1\n"
    "kprot\tlog10\t0.01\t100\t1\t1\n"
    "k_near\tlog10\t0.001\t1000\t1\t1\n"
    "k_mid\tlog10\t0.001\t1000\t1\t1\n"
)
SUMMARY = {
    "best_x_unscaled": {
        "kdeph": 2.0,
        "c_bc": 0.002,
        "kprot": 100.0,
        "k_near": 0.00115,
        "k_mid": 1.0,
    },
    "at_bounds": ["kdeph", "c_bc", "kprot"],
    "grad_at_active_bounds": [
        {"id": "c_bc", "edge": "lower", "component": 0.009768},
        {"id": "kdeph", "edge": "upper", "component": -57.293234},
    ],
    "near_bounds": [
        {"id": "k_near", "edge": "lower", "position": 0.0101, "from_edge": 0.0101},
        {"id": "k_mid", "edge": "lower", "position": 0.04, "from_edge": 0.04},
    ],
}


def main() -> int:
    with temp_record() as root:
        return _main(root)


def _main(root) -> int:
    wd = work(root, 1, "M1")
    (wd / "estimation").put(SUMMARY)
    (wd / "petab/parameters").put_table(pd.read_csv(io.StringIO(PARAMS), sep="\t"))
    ctx = Ctx(rnd(root, 1))
    got = bound_pressure(ctx, ["M1", "M_unfitted"])
    rows = {r["id"]: r for r in got.get("M1", [])}
    check(
        "at-bound parameters are listed with edge, bound, value and component",
        rows.get("kdeph")
        == {
            "id": "kdeph",
            "edge": "upper",
            "bound": 2.0,
            "value": 2.0,
            "scale": "log10",
            "at_bound": True,
            "pressing": True,
            "gradient_component": -57.29,
        },
        rows.get("kdeph"),
    )
    check(
        "an at-bound parameter the fit does not press on says so",
        rows.get("kprot", {}).get("edge") == "upper"
        and rows["kprot"]["pressing"] is False
        and rows["kprot"]["gradient_component"] is None
        and rows["kprot"]["bound"] == 100.0,
        rows.get("kprot"),
    )
    check(
        "within 2 % of a bound is listed; 4 % in is not",
        rows.get("k_near", {}).get("at_bound") is False
        and rows["k_near"]["bound"] == 0.001
        and "k_mid" not in rows,
        str(rows)[:400],
    )
    check(
        "ordered by the pressing component",
        [r["id"] for r in got["M1"]][:2] == ["kdeph", "c_bc"],
        [r["id"] for r in got["M1"]],
    )
    check(
        "a candidate with no fit in the record is skipped, the caller's candidate restored",
        "M_unfitted" not in got and ctx.candidate == "caller_was_here",
        f"{list(got)} {ctx.candidate}",
    )

    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    i = src.index("_pressure = bound_pressure(self.ctx, cand_ids)")
    check(
        "the expansion context carries it, with how to read it",
        'context["bound_pressure"]' in src[i : i + 900]
        and "BOUND_PRESSURE_NOTE" in src[i - 400 : i + 900],
    )
    check(
        "… a note that says what a large and a zero component mean",
        "bound-limited" in BOUND_PRESSURE_NOTE and "not needed" in BOUND_PRESSURE_NOTE,
    )
    others = [
        r
        for r in routing.ROUTING
        if r != "revision" and "bound_pressure" in routing.allowed(r)
    ]
    check(
        "routed to revision only",
        "bound_pressure" in routing.allowed("revision") and not others,
        others,
    )
    # whitespace-normalised: the skill wraps its lines at a fixed width
    skill = " ".join((REPO / "skills" / "revision.md").read_text().split())
    check(
        "the skill says how to use it",
        "read `bound_pressure` before believing a fit converged" in skill
        and "holding back" in skill
        and "pinned parameters your axes release" in skill,
    )

    live_root = run_root(LIVE_RUN, config.USER_RUNS_DIR)
    if (
        live_root.store.path.exists()
        and (
            work(live_root, LIVE_ROUND, "pstat1_protected_pool") / "estimation"
        ).exists()
    ):
        live = bound_pressure(
            Ctx(rnd(live_root, LIVE_ROUND)), ["pstat1_protected_pool"]
        )["pstat1_protected_pool"]
        head = live[0] if live else {}
        check(
            "live: kdeph heads the round-1 leader's list, pressing on its upper bound 2.0",
            head.get("id") == "kdeph"
            and head.get("bound") == 2.0
            and head.get("gradient_component", 0) < -50,
            str(head),
        )
    else:
        print("  live          (machine-local run not in the record store — skipped)")

    return finish(
        "\nBOUND PRESSURE",
        "\nBOUND PRESSURE UNIT OK — the expansion agent sees which parameters the box holds back, and how hard",
    )


if __name__ == "__main__":
    sys.exit(main())
