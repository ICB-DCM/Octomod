"""`adjoint` at the budget gate states its cost and re-measures before it projects.

  1. `solver_probe.ADJOINT_CONSEQUENCE` (no FIM Hessian, BFGS) is quoted by probe and card;
  2. after `adjoint` the probe re-runs: both medians kept, re-projected, ledgered, returned.

    uv run python tests/adjoint_reprobe_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import temp_record, work  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.cost_probe import engine as cost_profile  # noqa: E402
from octomod.workflow_modules.cost_probe import solver_probe  # noqa: E402
from octomod.workflow_modules.estimation.problem import make_engine  # noqa: E402


class _Opt:
    def __init__(self, fval, time):
        self.fval, self.time = fval, time


class _FakeResult:
    def __init__(self, fvals, time):
        self.optimize_result = type("R", (), {})()
        self.optimize_result.list = [_Opt(f, time) for f in fvals]


class _Ctx:
    def __init__(self, root):
        self.spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
        self.root = root
        self.ledger = Ledger(root.store)
        self.round_idx = 0
        self.candidate = "M2"
        # the candidate's work group: where the cost profile is written
        self.work = work(root, 0, "M2")


def main() -> int:
    forms = cost_profile._solver_note_forms({}, {"proposed_sensi_method": "adjoint"})
    adj = [f for f in forms if f.lstrip().startswith("adjoint")]
    check(
        "the adjoint note form says the FIM Hessian goes and Fides runs BFGS",
        len(adj) == 1
        and "BFGS" in adj[0]
        and "FIM Hessian" in adj[0]
        and "SLOWER" in adj[0],
        adj[0][:160] if adj else str(forms),
    )
    check(
        "…and when it is worth it (ratio ~20x or > ~50 parameters), and that a re-probe follows",
        adj and "20x" in adj[0] and "50" in adj[0] and "re-run" in adj[0],
    )
    check(
        "the same sentence is the one the sensitivity probe's proposal carries",
        solver_probe.ADJOINT_CONSEQUENCE in adj[0]
        and "ADJOINT_CONSEQUENCE"
        in Path(solver_probe.__file__).read_text().split("def sensitivity_probe")[1],
    )
    check(
        "no adjoint proposal, no adjoint form",
        not any(
            "adjoint" in f
            for f in cost_profile._solver_note_forms(
                {}, {"proposed_sensi_method": "forward"}
            )
        ),
    )

    real = cost_profile.run_multistart
    try:
        cost_profile.run_multistart = lambda problem, n, seed, spec, **kw: _FakeResult(
            [40.0 + i for i in range(n)], 3.0
        )
        with temp_record() as root:
            ctx = _Ctx(root)
            profile = {
                "median_start_s": 0.5,
                "projected_wall_s": 50.0,
                "probe_fvals": [40.0],
            }
            median = cost_profile._reprobe_after_override(
                ctx, None, profile, n_probe=5, seed=1, n_approved=100
            )
            engine = make_engine(ctx.spec, 3.0)
            n_par = int(getattr(engine, "n_procs", 1) or 1)
            expected = 3.0 * 100 / max(1, min(n_par, 100))
            check("the re-probe returns the adjoint median", median == 3.0, str(median))
            check(
                "the profile keeps the forward median AND the adjoint probe, and re-projects from the new one",
                profile["forward_median_start_s"] == 0.5
                and profile["median_start_s"] == 3.0
                and profile["adjoint_probe"]["median_start_s"] == 3.0
                and profile["adjoint_probe"]["slowdown_vs_forward"] == 6.0
                and abs(profile["projected_wall_s"] - round(expected, 1)) < 1e-6,
                f"{json.dumps({k: profile[k] for k in ('forward_median_start_s', 'median_start_s', 'projected_wall_s')})} "
                f"adjoint_probe={profile['adjoint_probe']}",
            )
            on_disk = (ctx.work / "cost").get({})
            check(
                "the candidate's `cost` record carries the re-probe",
                on_disk.get("adjoint_probe", {}).get("median_start_s") == 3.0,
            )
            rows = list(ctx.ledger.entries())
            note = next((r for r in rows if r.get("adjoint_reprobe")), None)
            check(
                "the ledger names the re-probe, the slowdown and BFGS, for this candidate",
                note is not None
                and "6.0x" in note["note"]
                and "BFGS" in note["note"]
                and note.get("candidate") == "M2",
                str(note)[:200] if note else "no row",
            )
    finally:
        cost_profile.run_multistart = real
    return finish(
        "\nADJOINT RE-PROBE",
        "\nadjoint re-probe: the projection is measured on the optimiser that will run",
    )


if __name__ == "__main__":
    sys.exit(main())
