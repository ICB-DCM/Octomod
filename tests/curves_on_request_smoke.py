"""Residual payloads: summaries always, curves for the worst few, the rest on request.

  1. a realistic payload (10 observables x 20 conditions x 4 candidates) fits the cap;
  2. what is omitted stays visible: a rank statistic, and the request that fetches it;
  3. the two request kinds answer on a real run, on both run layouts;
  4. an interpreter that asks gets it: executed, ledgered, carried into the next call.

    uv run python tests/curves_on_request_smoke.py
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod import (  # noqa: E402
    config,  # noqa: E402
)
from octomod.agents import payload as agent_payload  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.evaluation import diagnostics, residuals  # noqa: E402
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR
# the USER's runs folder, not redirected by the battery: this reads a
# previous run of theirs, not one this suite makes
USER_RUNS = config.USER_RUNS_DIR

CAP_KEY = "agents.max_prompt_bytes"


# default.yaml turns tiering off (null), so the tests of the tiering MECHANICS
# state the tier boundaries themselves
HISTORICAL_TIERS = {
    "diagnostics.full_curves_top_n": 5,
    "diagnostics.full_summaries_top_n": 40,
}


class TieredSpec:
    """The default spec with the historical tier boundaries put back."""

    def __init__(self, base: WorkflowSpec):
        self.base = base

    def get(self, dotted, default=None):
        if dotted in HISTORICAL_TIERS:
            return HISTORICAL_TIERS[dotted]
        return self.base.get(dotted, default)

    def require(self, dotted):
        if dotted in HISTORICAL_TIERS:
            return HISTORICAL_TIERS[dotted]
        return self.base.require(dotted)

    def __getattr__(self, name):
        return getattr(self.base, name)


def default_spec() -> WorkflowSpec:
    return WorkflowSpec.load(REPO / "workflows" / "default.yaml")


def interpreter_prompt(root: Node, round_idx: int = 0) -> Node:
    """The interpretation agent's prompt of a round, in the record."""
    return (rnd(root, round_idx) / "agent_calls").child("interpretation") / "prompt"


def spec() -> TieredSpec:
    return TieredSpec(default_spec())


def payload_block(
    prompt: Node, name: str = "residual_diagnostics"
) -> dict | list | None:
    """The named JSON block of an agent prompt, or None if it is not there."""
    if not prompt.exists():
        return None
    m = re.search(rf"\n## {name}\n```json\n(.*?)\n```", prompt.text(), re.S)
    return json.loads(m.group(1)) if m else None


def _series_in(root: Node) -> dict | None:
    block = payload_block(interpreter_prompt(root, 0))
    for cand in (block or {}).get("per_candidate_residuals", {}).values():
        for s in (cand.get("per_series") or {}).values():
            if isinstance(s, dict) and "fit_over_time" in s:
                return s
    return None


def a_real_series(root: Node) -> dict:
    """One series a real run produced, curve included: the sizes below are measured.

    Prefers `root` and falls back to the newest record in the USER's runs folder
    that carries one (`runs/search_smoke` belongs to the `search` suite, which
    removes it on start). The source of the numbers is never relaxed: a series a
    real engine produced, never an invented one.
    """
    found = _series_in(root)
    if found is not None:
        return found
    # every run is a record file; the newest one that carries a curve
    from octomod.result.node import RecordMissing
    from octomod.result.runstore import RunStore

    for store in reversed(RunStore.all_in(USER_RUNS)):
        try:
            found = _series_in(Node(store))
        except (RecordMissing, OSError):
            # a run with no interpreter prompt, or a damaged or foreign file,
            # is skipped; any other error is the reader's and must surface
            found = None
        if found is not None:
            return found
    # an absent fixture is not a defect: SKIP, exit 77, the battery convention
    # for machine-local live runs
    print(
        "SKIP: no run in runs/ carries a residual series with a curve, so there "
        "is no measured template to size this suite's assertions from — a "
        "machine-local live run, and runs/ is gitignored"
    )
    raise SystemExit(77)


def nbytes(obj) -> int:
    return len(json.dumps(obj, indent=2, default=str).encode())


# ------------------------------------------------------ 1. the realistic case


def test_the_realistic_payload_fits_under_the_cap() -> None:
    # preferred, not required: `a_real_series` falls back to any run that
    # carries a curve, because this record belongs to the `search` suite
    template = a_real_series(run_root("search_smoke", USER_RUNS))
    sp = spec()
    # null = no cap; the tiering is still measured against a 250,000-byte cap
    cap = int(sp.get(CAP_KEY) or 250_000)
    n_curves = int(sp.get("diagnostics.full_curves_top_n"))
    n_summaries = int(sp.get("diagnostics.full_summaries_top_n"))

    n_obs, n_cond, n_cand = 10, 20, 4
    labels = [f"obs_{o}@cond_{c}" for o in range(n_obs) for c in range(n_cond)]
    details = {}
    for k in range(n_cand):
        series = {}
        for i, label in enumerate(labels):
            s = copy.deepcopy(template)
            # a descending ranking, so the tiering has something to rank BY
            s["rmse_over_replicate_noise_floor"] = round(5.0 - i * 0.02, 3)
            series[label] = s
        details[f"M{k}"] = {"sigma_vs_replicate_floor": [], "per_series": series}

    untiered = nbytes(agent_payload.for_agents(copy.deepcopy(details)))
    # the two models that carry the argument keep curves
    for cid, det in details.items():
        residuals.thin_series(det, sp, carries_curves=cid in ("M0", "M1"))
    tiered = nbytes(agent_payload.for_agents(details))

    check(
        f"the untiered payload really does not fit ({n_obs}x{n_cond}x{n_cand} "
        f"= {len(labels) * n_cand} series)",
        untiered > cap,
        f"{untiered:,} bytes against a {cap:,} cap",
    )
    check(
        "and the tiered one does, with room",
        tiered < cap * 0.8,
        f"{tiered:,} bytes = {tiered / cap:.0%} of the cap "
        f"({untiered / max(tiered, 1):.1f}x smaller)",
    )
    curves = [
        1
        for det in details.values()
        for s in det["per_series"].values()
        if "fit_over_time" in s
    ]
    check(
        "exactly the declared number of curves survives, on the two models "
        "that carry the argument",
        len(curves) == 2 * n_curves,
        f"{len(curves)} curves for full_curves_top_n={n_curves} x 2 models",
    )
    check(
        "and the declared number of full summaries, per candidate",
        all(len(det["per_series"]) == n_summaries for det in details.values()),
        f"{[len(d['per_series']) for d in details.values()]} "
        f"for full_summaries_top_n={n_summaries}",
    )


def test_every_observable_keeps_a_curve() -> None:
    """The curve budget draws each observable's worst series first, so none is blank."""
    sp = spec()
    n_curves = int(sp.get("diagnostics.full_curves_top_n"))
    # worst-first, and every one of the worst five belongs to obs_A
    series = {}
    for i, (obs, cond) in enumerate(
        [("obs_A", c) for c in range(5)]
        + [("obs_B", c) for c in range(5)]
        + [("obs_C", c) for c in range(5)]
    ):
        series[f"{obs}@c{cond}"] = {
            "rmse_over_replicate_noise_floor": round(9.0 - i * 0.1, 3),
            "fit_over_time": [{"t": 0.0, "measured": 1.0}, {"t": 1.0, "measured": 2.0}],
        }
    det = {"per_series": series}
    residuals.thin_series(det, sp, carries_curves=True)
    drawn = [k for k, v in det["per_series"].items() if "fit_over_time" in v]
    check(
        "the budget is still spent in full",
        len(drawn) == n_curves,
        f"{len(drawn)} of {n_curves}",
    )
    check(
        "and EVERY observable keeps at least one curve, even though the five "
        "worst series all belong to one of them",
        {k.split("@")[0] for k in drawn} == {"obs_A", "obs_B", "obs_C"},
        f"drawn: {sorted(drawn)}",
    )
    check(
        "each observable's own WORST series is the one drawn",
        {"obs_A@c0", "obs_B@c0", "obs_C@c0"} <= set(drawn),
        f"drawn: {sorted(drawn)}",
    )
    check(
        "the remaining budget goes to the worst remaining overall",
        sorted(drawn)[:3] == ["obs_A@c0", "obs_A@c1", "obs_A@c2"],
        f"drawn: {sorted(drawn)}",
    )
    check(
        "and the note says both halves of the rule, so a reader knows why "
        "these series and not the top five",
        "within each observable first" in det["curves_note"]
        and "worst remaining overall" in det["curves_note"],
        det["curves_note"][:130],
    )
    # more observables than budget: the worst N observables get one each
    many = {
        f"obs_{i}@c0": {
            "rmse_over_replicate_noise_floor": round(9.0 - i * 0.1, 3),
            "fit_over_time": [{"t": 0.0}, {"t": 1.0}],
        }
        for i in range(n_curves + 3)
    }
    det2 = {"per_series": many}
    residuals.thin_series(det2, sp, carries_curves=True)
    drawn2 = [k for k, v in det2["per_series"].items() if "fit_over_time" in v]
    check(
        "with more observables than budget, the worst observables get the "
        "curves rather than the budget being exceeded",
        len(drawn2) == n_curves
        and sorted(drawn2) == sorted(f"obs_{i}@c0" for i in range(n_curves)),
        f"{sorted(drawn2)}",
    )


def test_every_observable_keeps_a_summary_too() -> None:
    """Coverage at the summary tier too; curves are drawn only from what it keeps."""
    sp = spec()
    n_summaries = int(sp.get("diagnostics.full_summaries_top_n"))
    n_curves = int(sp.get("diagnostics.full_curves_top_n"))
    # ten observables, twenty conditions each, ranked so that ALL of obs_0's
    # series outrank every other observable's
    series = {}
    for i, (o, c) in enumerate([(o, c) for o in range(10) for c in range(20)]):
        series[f"obs_{o}@cond_{c}"] = {
            "rmse_over_replicate_noise_floor": round(9.0 - i * 0.01, 3),
            "fit_over_time": [{"t": 0.0, "measured": 1.0}, {"t": 1.0, "measured": 2.0}],
        }
    det = {"per_series": series}
    residuals.thin_series(det, sp, carries_curves=True)

    kept = det["per_series"]
    check(
        "the summary budget is spent in full",
        len(kept) == n_summaries,
        f"{len(kept)} of {n_summaries}",
    )
    check(
        "and every observable keeps at least one full summary, so none is "
        "reduced to a bare number while others keep twenty",
        {k.split("@")[0] for k in kept} == {f"obs_{i}" for i in range(10)},
        f"observables with a summary: {sorted({k.split('@')[0] for k in kept})}",
    )
    drawn = [k for k, v in kept.items() if "fit_over_time" in v]
    check(
        "every curve sits on a series the summary tier KEPT — a curve on a "
        "dropped series is a curve thrown away",
        len(drawn) == n_curves and all(k in kept for k in drawn),
        f"{len(drawn)} curves, all within the kept set: {sorted(drawn)}",
    )
    other = det["other_series_rmse_over_replicate_noise_floor"]
    check(
        "and the 160 series below the tier are all still visible as numbers",
        len(other) == 200 - n_summaries,
        f"{len(other)} omitted",
    )
    check(
        "with a note saying every observable is represented above, so a reader "
        "does not think an observable went missing",
        "Every observable keeps at least one full summary" in det["note"],
        det["note"][:130],
    )


def test_the_two_thresholds_live_in_one_place() -> None:
    """Both full specs declare the thresholds and agree; residuals.py has no twin."""
    import yaml

    seen = {}
    for name in ("default.yaml", "test_redraft.yaml"):
        raw = yaml.safe_load((REPO / "workflows" / name).read_text())
        diag = raw.get("diagnostics") or {}
        seen[name] = (diag.get("full_curves_top_n"), diag.get("full_summaries_top_n"))
        check(
            f"{name} declares both thresholds, so they are hashed into "
            f"workflow_sha",
            "full_curves_top_n" in diag and "full_summaries_top_n" in diag,
            f"{seen[name][0]} / {seen[name][1]}",
        )
    check("the two full specs agree", len(set(seen.values())) == 1, str(seen))
    check(
        "and the default declares no tier (null)",
        seen["default.yaml"] == (None, None),
        str(seen["default.yaml"]),
    )
    src = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "residuals.py"
    ).read_text()
    check(
        "residuals.py holds no twin of either number and reads both in one helper",
        "DEFAULT_FULL_CURVES_TOP_N" not in src
        and 'spec.get("diagnostics.full_curves_top_n")' in src
        and 'spec.get("diagnostics.full_summaries_top_n")' in src,
    )


def test_no_tier_keeps_every_series_and_every_curve() -> None:
    """The default spec (null tiers) thins nothing and writes no omission note."""
    series = {
        f"obs_{o}@c{c}": {
            "rmse_over_replicate_noise_floor": float(10 * o + c),
            "fit_over_time": [{"t": 0.0, "measured": 1.0}],
        }
        for o in range(3)
        for c in range(30)
    }
    det = {"per_series": copy.deepcopy(series)}
    residuals.thin_series(det, default_spec(), carries_curves=True)
    kept = det["per_series"]
    check(
        "all 90 series keep their summary and their curve",
        len(kept) == 90 and all("fit_over_time" in s for s in kept.values()),
        f"{len(kept)} series, {sum('fit_over_time' in s for s in kept.values())} curves",
    )
    check(
        "and nothing says a series was dropped",
        not any(k.startswith("other_series_") for k in det) and "note" not in det,
        str(sorted(det)),
    )


# --------------------------------------------- 2. what is omitted stays visible


def test_an_omitted_series_is_still_visible_and_named() -> None:
    sp = spec()
    n_summaries = int(sp.get("diagnostics.full_summaries_top_n"))
    series = {
        f"obs@c{i}": {
            "rmse": 0.1,
            "rmse_over_replicate_noise_floor": round(9.0 - i * 0.1, 3),
            "fit_over_time": [{"t": 0.0, "measured": 1.0}, {"t": 1.0, "measured": 2.0}],
        }
        for i in range(n_summaries + 7)
    }
    det = {"per_series": series}
    residuals.thin_series(det, sp, carries_curves=True)

    other_keys = [k for k in det if k.startswith("other_series_")]
    check(
        "the omitted series are collected under a key that names the statistic "
        "they are ranked by",
        other_keys == ["other_series_rmse_over_replicate_noise_floor"],
        str(other_keys),
    )
    other = det[other_keys[0]]
    check(
        "every omitted series is there, with its rank statistic — an agent "
        "cannot ask for a series it cannot see",
        len(other) == 7 and all(isinstance(v, float) for v in other.values()),
        f"{len(other)} omitted: {list(other.items())[:2]}",
    )
    check(
        "and they are the WORST-ranked ones that were kept, not an arbitrary " "tail",
        min(
            det["per_series"][k]["rmse_over_replicate_noise_floor"]
            for k in det["per_series"]
        )
        >= max(other.values()),
        f"kept min "
        f"{min(det['per_series'][k]['rmse_over_replicate_noise_floor'] for k in det['per_series'])}"
        f" vs omitted max {max(other.values())}",
    )
    check(
        "one line names the request that fetches them, said once for the "
        "candidate rather than once per series",
        "residual_curve(candidate_id, observable_id, condition_id)" in det["note"]
        and det["note"].count("residual_curve") == 1,
        det["note"][:120],
    )
    check(
        "and the curve tier says the same for the series it summarised",
        "residual_curve" in det.get("curves_note", ""),
        det.get("curves_note", "")[:110],
    )
    # a small round is untouched: nothing to tier, so no notes and no tiers
    small = {"per_series": {f"s{i}": {"rmse": 0.1} for i in range(3)}}
    residuals.thin_series(small, sp, carries_curves=True)
    check(
        "a round with few series carries no tiering and no explanation of one",
        list(small) == ["per_series"] and len(small["per_series"]) == 3,
        str(sorted(small)),
    )


def test_the_ranking_says_which_statistic_it_used() -> None:
    """The ranking prefers the floor ratio, falls back to rmse, and names which."""
    check(
        "the floor ratio is preferred",
        residuals.rank_of({"rmse": 0.5, "rmse_over_replicate_noise_floor": 3.0})
        == (3.0, "rmse_over_replicate_noise_floor"),
    )
    check(
        "raw rmse is the fallback when the data carry no replicates",
        residuals.rank_of({"rmse": 0.5}) == (0.5, "rmse"),
    )
    check(
        "and a series with neither ranks last rather than raising",
        residuals.rank_of({}) == (0.0, "none")
        and residuals.rank_of(None) == (0.0, "none"),
    )
    sp = spec()
    n = int(sp.get("diagnostics.full_summaries_top_n"))
    det = {"per_series": {f"s{i}": {"rmse": float(n - i)} for i in range(n + 2)}}
    residuals.thin_series(det, sp, carries_curves=False)
    check(
        "the omitted-series key names the fallback statistic when that is what "
        "ranked them",
        "other_series_rmse" in det,
        str([k for k in det if k.startswith("other_")]),
    )


# ----------------------------------------------- 3. the requests really answer


def test_the_new_kinds_are_whitelisted_and_pure_reads() -> None:
    check(
        "both kinds are in the whitelist the agent is shown",
        "residual_curve" in diagnostics.KINDS and "profile_path" in diagnostics.KINDS,
        str(diagnostics.KINDS),
    )
    check(
        "and both have a runner, so the whitelist cannot promise what the "
        "engine cannot execute",
        set(diagnostics.KINDS) == set(diagnostics._RUNNERS),
        f"kinds {set(diagnostics.KINDS) ^ set(diagnostics._RUNNERS)}",
    )


def check_requests_answer(root: Node, cand_ids: list[str], path_name: str) -> None:
    """The two request kinds on a real run (its record `root`) of either layout
    (`candidates/<id>` or `candidates/_single`); used by other smokes."""
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import RunContext

    ctx = RunContext(
        root=root,
        testcase_dir=root.store.path.parent,
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(root),
        backend="stub",
        auto=True,
    )
    block = payload_block(interpreter_prompt(root, 0))
    assert isinstance(block, dict), (
        "this suite just drove the round that writes that prompt, so a missing "
        "residual_diagnostics block is a defect, not a missing fixture"
    )
    cid = cand_ids[0]
    series = next(
        iter((block["per_candidate_residuals"][cid or "model"]).get("per_series"))
    )
    obs_id, cond_id = series.split("@", 1)

    out = diagnostics.run_request(
        ctx,
        cand_ids,
        {
            "kind": "residual_curve",
            "args": {
                "candidate_id": cid,
                "observable_id": obs_id,
                "condition_id": cond_id,
            },
        },
        module="evaluation",
    )
    assert "error" not in out, f"{path_name}: residual_curve failed: {out['error']}"
    res = out["result"]
    assert res["series"] == series, (path_name, res["series"], series)
    assert res.get("fit_over_time"), f"{path_name}: the curve came back empty"
    assert len(res["fit_over_time"]) >= 2, res["fit_over_time"]

    # a request naming something that does not exist is an ANSWER, not a crash
    bad = diagnostics.run_request(
        ctx,
        cand_ids,
        {
            "kind": "residual_curve",
            "args": {
                "candidate_id": cid,
                "observable_id": "no_such_observable",
                "condition_id": cond_id,
            },
        },
        module="evaluation",
    )
    assert "error" in bad and "not in the problem" in bad["error"], bad
    assert obs_id in bad["error"], (
        f"{path_name}: the refusal does not list what IS available: "
        f"{bad['error'][:120]}"
    )

    core = (rnd(root, 0) / "evaluation_core").get(None) or {}
    pids = [k for k in (core.get("profiles") or {}) if not str(k).startswith("_")]
    if pids:
        got = diagnostics.run_request(
            ctx,
            cand_ids,
            {"kind": "profile_path", "args": {"parameter_id": pids[0]}},
            module="evaluation",
        )
        assert "error" not in got, f"{path_name}: profile_path failed: {got['error']}"
        path = got["result"].get("path") or {}
        # the path's objective field is `nllh`, not `fval`
        assert path.get("x_unscaled") and path.get("nllh"), sorted(path)
        assert len(path["x_unscaled"]) == len(path["nllh"]), (
            f"{path_name}: the profile path is ragged — "
            f"{len(path['x_unscaled'])} points against {len(path['nllh'])}"
        )
        assert got["result"]["ci95"], got["result"]
        note = got["result"]["how_to_read_this"]
        for field in ("x_unscaled", "nllh", "nllh_threshold", "likelihood_ratio"):
            assert f"path.{field}" in note, (
                f"{path_name}: the note does not name path.{field}, and a note "
                f"that names a field the payload lacks is worse than no note"
            )
            assert field in path, f"{path_name}: the note names a missing {field}"
    rows = [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "diagnostic_request" and e.get("module") == "evaluation"
    ]
    assert rows, f"{path_name}: the requests were not ledgered under evaluation"
    print(
        f"  requests      {path_name}: residual_curve on {series} answered, "
        f"{len(rows)} row(s) ledgered as evaluation"
    )


# ----------------------------------------- 4. an interpreter that asks, gets


def test_an_interpreter_that_asks_gets_the_curve() -> None:
    """A stub interpreter that asks for a curve gets it in its second prompt."""
    import shutil
    import tempfile
    import time

    from octomod.cli import main as cli_main

    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "toy_phos"
        shutil.copytree(REPO / "testcase" / "toy_phos", case)
        stub = case / "stubs" / "interpretation.json"
        reply = json.loads(stub.read_text())
        reply["_copy_computed"] = True
        first = dict(reply)
        first["requested_diagnostics"] = [
            {
                "kind": "residual_curve",
                "args": {
                    "candidate_id": "",
                    "observable_id": "obs_pR",
                    "condition_id": "dose_1",
                },
            }
        ]
        (case / "stubs" / "interpretation.1.json").write_text(
            json.dumps(first, indent=2) + "\n"
        )
        (case / "stubs" / "interpretation.2.json").write_text(
            json.dumps(reply, indent=2) + "\n"
        )
        stub.unlink()

        run_id = f"curves_req_{time.strftime('%H%M%S')}"
        rc = cli_main(
            [
                "run",
                "--testcase",
                str(case),
                "--backend",
                "stub",
                "--auto-approve",
                "--run-id",
                run_id,
            ]
        )
        root = run_root(run_id)
        check(
            "the run completes with the interpreter asking once", rc == 0, f"exit {rc}"
        )
        if rc != 0:
            return

        state = rnd(root, 0) / "interpretation_diagnostics"
        check(
            "the request round is persisted, so a resume never re-pays for it",
            state.exists(),
            state.key,
        )
        if state.exists():
            steps = (state.get() or {}).get("steps") or []
            check(
                "one step, one request, and it succeeded",
                len(steps) == 1
                and len(steps[0]["results"]) == 1
                and "error" not in steps[0]["results"][0],
                str(steps[0]["results"][0].get("error") if steps else "no steps"),
            )
        ledger = ledger_rows(root)
        rows = [
            e
            for e in ledger
            if e.get("event") == "diagnostic_request"
            and e.get("kind") == "residual_curve"
        ]
        check(
            "the request is ledgered against the module that asked",
            len(rows) == 1 and rows[0]["module"] == "evaluation" and rows[0]["ok"],
            str(rows[:1]),
        )
        calls = [
            e
            for e in ledger
            if e.get("event") == "agent_call" and e.get("role") == "interpretation"
        ]
        check(
            "the interpreter was asked exactly twice — once, then again with "
            "the answer",
            len(calls) == 2,
            f"{len(calls)} calls",
        )
        prompt = interpreter_prompt(root, 0)
        text = prompt.text()
        check(
            "and the SECOND prompt carries the curve it asked for",
            "## diagnostics_requested" in text and "residual_curve" in text,
            f"blocks: {re.findall(r'## (\w+)', text)}",
        )
        got = payload_block(prompt, "diagnostics_requested")
        check(
            "with the series it named, point by point",
            isinstance(got, list)
            and got[0]["result"]["series"] == "obs_pR@dose_1"
            and got[0]["result"]["fit_over_time"],
            str(got)[:140],
        )
        check(
            "the instruction that offered the channel is in the prompt too",
            "requested_diagnostics" in text and "HONEST COST" in text,
            "",
        )


def check_curves_cover_every_observable(
    root: Node, round_idx: int, path_name: str
) -> None:
    """On a real run, each observable's worst series is drawn; used by other smokes."""
    block = payload_block(interpreter_prompt(root, round_idx))
    assert isinstance(block, dict), (
        f"{root.store.path.stem} round {round_idx} carries no residual_diagnostics "
        f"block; the caller owns this run, so there is nothing to fall back to"
    )
    drew_any = False
    for cid, det in block["per_candidate_residuals"].items():
        series = det.get("per_series") or {}
        drawn = [
            k for k, v in series.items() if isinstance(v, dict) and "fit_over_time" in v
        ]
        if not drawn:
            continue  # a model that carries no curves by design
        drew_any = True
        present = {k.split("@")[0] for k in series}
        covered = {k.split("@")[0] for k in drawn}
        assert covered == present, (
            f"{path_name}/{cid}: {sorted(present - covered)} keep a summary "
            f"but no curve — the interpreter cannot read their residual shape"
        )
        # and each drawn series is that observable's own worst among those kept
        for obs in covered:
            mine = {k: v for k, v in series.items() if k.split("@")[0] == obs}
            worst = max(mine, key=lambda k: residuals.rank_of(mine[k])[0])
            assert worst in drawn, (
                f"{path_name}/{cid}/{obs}: the drawn series is not this "
                f"observable's worst ({worst} is)"
            )
    assert drew_any, f"{path_name}: no candidate carries any curve at all"
    print(f"  coverage      {path_name}: every observable's worst series is drawn")


def main() -> int:
    print("curves on request — summaries always, the rest when asked\n")
    test_the_realistic_payload_fits_under_the_cap()
    test_every_observable_keeps_a_curve()
    test_every_observable_keeps_a_summary_too()
    test_the_two_thresholds_live_in_one_place()
    test_no_tier_keeps_every_series_and_every_curve()
    test_an_omitted_series_is_still_visible_and_named()
    test_the_ranking_says_which_statistic_it_used()
    test_the_new_kinds_are_whitelisted_and_pure_reads()
    test_an_interpreter_that_asks_gets_the_curve()

    print()
    return finish(
        "CURVES ON REQUEST",
        "CURVES ON REQUEST OK — the realistic payload fits, what is omitted "
        "stays visible, and both new kinds answer",
    )


if __name__ == "__main__":
    raise SystemExit(main())
