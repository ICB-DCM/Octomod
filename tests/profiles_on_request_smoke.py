"""Profile likelihoods are computed only on request, by default at the end.

  1. with no request nothing is computed; the report core says why and at what cost;
  2. parameter_values still profiles (the estimates are the deliverable);
  3. `--profiles "<why>"` computes them with no second question; a resume honours it;
  4. `profiles` at the verdict card removes the verdict and pin, writes the request;
  5. the card's profiles line and form appear only while none were asked for;
  6. the CLI declares `--profiles WHY` and refuses it beside `--skip-profiles`;
  7. end to end on toy_phos: `y` + `profiles` computes them and asks the card again.

    uv run python tests/profiles_on_request_smoke.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish, run_cli_captured  # noqa: E402

from octomod import config  # noqa: E402
from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure, RunContext  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.evaluation import engine as s7  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    record_at,
    rnd,
    run_root,
    run_store,
)

RUNS = config.RUNS_DIR
RUN_ID = "profiles_on_request_smoke"


class _Spec:
    def __init__(self, **kv):
        self.kv = kv

    def get(self, key, default=None):
        return self.kv.get(key, default)

    def require(self, key):
        return self.kv.get(key, 0)


def _new_root() -> Node:
    """A throwaway run record in a fresh temporary directory."""
    root = record_at(Path(tempfile.mkdtemp(prefix="octomod_test_")) / "run.h5")
    root.store.create()
    (root / "intent").put({})
    return root


def _ctx(root: Node, **kw):
    ctx = RunContext(
        root=root,
        testcase_dir=root.store.path.parent / "input",
        spec=_Spec(
            **{"estimation.engine": "serial", "gates.profiles_auto.max_projected_s": 0}
        ),
        ledger=Ledger(root.store),
        backend="stub",
        auto=False,
        round_idx=0,
    )
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


def _stage_problem(root: Node) -> dict:
    """The two records a projection reads (the fitted problem's parameter
    table and the probe's `cost`), and the summary beside them."""
    import pandas as pd

    wk = tree.work_node(tree.round_node(root, 0), None)
    (wk / "petab/parameters").put_table(
        pd.DataFrame(
            [
                {
                    "parameterId": k,
                    "parameterScale": "log10",
                    "lowerBound": 0.001,
                    "upperBound": 1000,
                    "nominalValue": 1,
                    "estimate": 1,
                }
                for k in ("k1", "k2")
            ]
        )
    )
    (wk / "cost").put({"median_start_s": 0.5})
    return {"x_names": ["k1", "k2"], "best_x_unscaled": {"k1": 1.0, "k2": 10.0}}


def units() -> None:
    root = _new_root()
    ctx = _ctx(root)
    core: dict = {}
    s7._profiles_for(ctx, core, _stage_problem(root), "mechanism_discrimination", 2)
    check(
        "no request: not computed, the core says why",
        core.get("profiles_skipped") == s7.PROFILES_NOT_REQUESTED
        and "profiles" not in core,
        str(core),
    )
    proj = (core.get("profiles_on_request") or {}).get("projection") or {}
    check(
        "… and what it would cost, as a low and a high end",
        0 < (proj.get("low_s") or 0) <= (proj.get("high_s") or 0)
        and proj.get("per_point_source") == "cost probe range",
        str(core.get("profiles_on_request")),
    )
    check("… ledgered", any(r.get("profiles_on_request") for r in ctx.ledger.entries()))

    asked = []
    real_ask, real_prof = humangate.ask_once, s7._profiles
    humangate.ask_once = lambda *a, **k: (asked.append(k.get("module")), (False, "no"))[
        1
    ]
    s7._profiles = lambda ctx_, summary, **kw: {
        "_meta": {"x_names": ["k1"]},
        "k1": {"ci95": [0.1, 0.2]},
    }
    try:
        try:
            s7._profiles_for(
                _ctx(_new_root()),
                {},
                {"x_names": ["k1"]},
                "parameter_values",
                1,
            )
        except ModuleFailure:
            pass
        check(
            "parameter_values still reaches the profiling rule",
            asked == ["evaluation_profiling_gate"],
            str(asked),
        )

        root2 = _new_root()
        ctx2 = _ctx(root2, request_profiles="the final model")
        core2: dict = {}
        s7._profiles_for(
            ctx2, core2, {"x_names": ["k1"]}, "mechanism_discrimination", 1
        )
        dec = (ctx2.round / s7.PROFILE_REQUEST).get()
        check(
            "--profiles computes them, with no second question",
            "k1" in (core2.get("profiles") or {})
            and asked == ["evaluation_profiling_gate"],
            str(core2),
        )
        check(
            "… persisted for the round as the human's request",
            dec.get("requested") == "the final model" and dec.get("by") == "human",
            str(dec),
        )
        core3: dict = {}
        s7._profiles_for(
            _ctx(root2),
            core3,
            {"x_names": ["k1"]},
            "mechanism_discrimination",
            1,
        )
        check(
            "a persisted request is honoured on the resume",
            "k1" in (core3.get("profiles") or {}),
            str(core3),
        )
    finally:
        humangate.ask_once, s7._profiles = real_ask, real_prof

    # the verdict card's form
    root4 = _new_root()
    ctx4 = _ctx(root4)
    verdict = ctx4.round / s7.VERDICT_DECISION
    pin = ctx4.agent_calls / s7.INTERPRETATION_PIN
    verdict.put({"approved": True, "note": "profiles"})
    pin.put({"recommendation": "accept"})
    check(
        "a note without the form takes nothing",
        s7._take_profiles_request(ctx4, {}, "y looks good") is False
        and verdict.exists(),
    )
    took = s7._take_profiles_request(ctx4, {}, "profiles")
    dec = (ctx4.round / s7.PROFILE_REQUEST).get(None) or {}
    check(
        "`profiles` is taken: the verdict record gone, the request written, the pin dropped",
        took
        and not verdict.exists()
        and dec.get("form") == "profiles"
        and not pin.exists(),
        str(dec),
    )
    check(
        "… and read back",
        any(
            "read from the human's note: profiles" in str(r.get("note"))
            for r in ctx4.ledger.entries()
        ),
    )
    check(
        "profiles already in the report are not requested again",
        s7._take_profiles_request(ctx4, {"profiles": {"k1": {}}}, "profiles") is False,
    )

    lines, forms = s7._profiles_card_lines(
        {
            "profiles_skipped": s7.PROFILES_NOT_REQUESTED,
            "profiles_on_request": {
                "projection": {
                    "available": True,
                    "n_parameters": 32,
                    "points_low": 600,
                    "points_high": 1200,
                    "per_point_low_s": 9.0,
                    "per_point_high_s": 9.0,
                    "per_point_source": "cost probe range",
                    "workers": 9,
                    "low_s": 600,
                    "high_s": 1200,
                }
            },
        }
    )
    check(
        "the card says profiles are on request, with the cost range, and offers the form",
        lines
        and "~10–20 min" in lines[0]
        and "600–1,200 points over 32 parameters" in lines[0]
        and forms
        and forms[0].startswith("profiles "),
        f"{lines} {forms}",
    )
    check(
        "… and says nothing once they were asked for",
        s7._profiles_card_lines({"profiles": {"k1": {}}}) == ([], []),
    )

    src = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    check(
        "both verdict gates re-run their module on a taken request",
        "if _take_profiles_request(ctx, core, _note):\n        return run(ctx, None, rounds_left)"
        in src
        and "if _take_profiles_request(ctx, core, note):\n        return _run_md(ctx, cand_ids, rounds_left)"
        in src,
    )
    spec = (REPO / "workflows" / "default.yaml").read_text()
    check("the spec declares it", "profiles:\n    on_request: true" in spec)
    out = subprocess.run(
        [sys.executable, "-m", "octomod", "run", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout
    both = subprocess.run(
        [
            sys.executable,
            "-m",
            "octomod",
            "run",
            "--testcase",
            "testcase/toy_phos",
            "--profiles",
            "a",
            "--skip-profiles",
            "b",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    check(
        "the CLI declares --profiles WHY and refuses it beside --skip-profiles",
        "--profiles WHY" in out and both.returncode == 2 and "opposite" in both.stderr,
        f"rc={both.returncode} {both.stderr[-200:]}",
    )


def end_to_end() -> None:
    run_store(RUN_ID, RUNS).remove()
    root = run_root(RUN_ID, RUNS)
    base = [
        "run",
        "--testcase",
        "testcase/toy_phos",
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--gate-mode",
        "file",
    ]
    rc, out = run_cli_captured(base)
    verdicts: list[dict] = []
    answered_profiles = False
    for _ in range(30):
        if rc != 3:
            break
        payload = pending_gate(root) or {}
        if payload["module"] == "evaluation_verdict":
            verdicts.append(payload)
            if not answered_profiles:
                answered_profiles = True
                rc, out = run_cli_captured(
                    base + ["--gate-answer", "y", "--gate-note", "profiles"]
                )
                continue
        rc, out = run_cli_captured(base + ["--gate-answer", "y"])
    check("end to end: the run finished", rc == 0, f"rc={rc} {out[-300:]}")
    first = (
        "\n".join(
            str(x)
            for x in (verdicts[0].get("always_show") or verdicts[0].get("lines") or [])
        )
        if verdicts
        else ""
    )
    forms = verdicts[0].get("note_forms") if verdicts else []
    check(
        "the first verdict card says profiles are on request and offers the form",
        "PROFILES: not computed" in first
        and any(str(f).startswith("profiles ") for f in forms or []),
        f"{first[-400:]} {forms}",
    )
    check(
        "`y` + `profiles` asked the verdict card again",
        len(verdicts) == 2,
        f"{len(verdicts)} verdict cards",
    )
    core = (rnd(root, 0) / "evaluation_core").get()
    real = [k for k in core.get("profiles") or {} if not str(k).startswith("_")]
    check(
        "… and the signed round has its profiles",
        bool(real) and "profiles_skipped" not in core,
        str(core.get("profiles_skipped")),
    )
    rows = ledger_rows(root)
    check(
        "the request is on the ledger as the human's",
        any(r.get("profiles_requested") for r in rows),
    )


def main() -> int:
    units()
    end_to_end()
    return finish(
        "\nPROFILES ON REQUEST",
        "\nPROFILES ON REQUEST OK — profiles run when a human asks, and the card they are asked at is asked again",
    )


if __name__ == "__main__":
    sys.exit(main())
