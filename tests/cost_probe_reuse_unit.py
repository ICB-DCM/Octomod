"""A budget approval is reused only while a candidate's probe matches the approved one.

  1. `reuse_verdict` names why it refuses: a non-finite probe, or an off-ratio speed;
  2. on a real problem a finite probe reuses; an all-inf one is gated, `n` drops it;
  3. a probe 10x slower than the approved one is re-asked with ratio and ceiling.

    uv run python tests/cost_probe_reuse_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import ledger_rows, temp_record  # noqa: E402

from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.cost_probe import engine as cost_profile  # noqa: E402

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"


# ------------------------------------------------------------ 1. the verdict


def test_verdict_is_pure_and_names_its_reasons() -> None:
    ref = {"candidate": "M1", "median_start_s": 0.4}
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [51.4, 51.5, 60.0], "median_start_s": 0.5}, ref, 5.0
    )
    check("a finite probe at the approved speed reuses the approval", ok and not why)
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [float("inf")] * 5, "median_start_s": 0.019}, ref, 5.0
    )
    check(
        "an all-inf probe refuses the reuse and says non-finite",
        not ok and any("non-finite" in r for r in why),
        str(why),
    )
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [50.0, float("inf")], "median_start_s": 0.4}, ref, 5.0
    )
    check(
        "one inf start of two is enough to refuse",
        not ok and "1 of 2" in why[0],
        str(why),
    )
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [50.0, 51.0], "median_start_s": 2.4}, ref, 5.0
    )
    check(
        "6x slower than the approved candidate refuses, naming ratio and ceiling",
        not ok and "6x" in why[0] and "5x" in why[0] and "'M1'" in why[0],
        str(why),
    )
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [50.0, 51.0], "median_start_s": 0.05}, ref, 5.0
    )
    check(
        "8x FASTER refuses too — the projection is wrong either way", not ok, str(why)
    )
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [50.0, 51.0], "median_start_s": 1.6}, ref, 5.0
    )
    check("4x slower is inside the declared ceiling and reuses", ok, str(why))
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [50.0, 51.0], "median_start_s": 9.0}, None, 5.0
    )
    check("no reference: a finite probe reuses (only finiteness can be checked)", ok)
    ok, why = cost_profile.reuse_verdict(
        {"probe_fvals": [float("inf")], "median_start_s": 0.01}, None, 5.0
    )
    check("no reference: an inf probe still refuses", not ok)


# ------------------------------------------------------- 2./3. the real gate


class _Opt:
    def __init__(self, fval, time):
        self.fval, self.time, self.x = fval, time, None


class _FakeResult:
    def __init__(self, fvals, time):
        self.optimize_result = type("R", (), {})()
        self.optimize_result.list = [_Opt(f, time) for f in fvals]


def _context(root, candidate: str) -> RunContext:
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    ctx = RunContext(
        root=root,
        testcase_dir=REPO / "testcase" / "toy_phos_petab",
        spec=spec,
        ledger=Ledger(root),
        backend="stub",
        auto=False,
    )
    (root / "intent").put(
        {
            "question": "unit test",
            "system": "toy",
            "inference_target": "mechanism_discrimination",
        }
    )
    ctx.candidate = candidate
    inp = petab_io.from_dir(PETAB)
    if not (ctx.work / "petab/measurements").exists():
        petab_io.to_record(inp, ctx.work / "petab")
    (ctx.model / "sbml").put_text(inp.sbml)
    ctx.set_marker("s3", producer="unit test")
    return ctx


def _run(ctx, preapproved, reference, answer=None, note=""):
    ctx.cache["_budget_reference"] = reference
    humangate.configure_file_mode(ctx.root, answer, note)
    try:
        n = cost_profile.run(
            ctx, ask_human=False, n_candidates=3, preapproved_n=preapproved
        )
        return "returned", n
    except humangate.GatePending as e:
        return "gate", e.payload
    except cost_profile.BudgetDeclinedForCandidate as e:
        return "declined", e


def test_a_real_probe_reuses_or_reasks() -> None:
    import logging

    logging.disable(logging.WARNING)
    cache: dict = {}
    with temp_record("probe_reuse") as tmp:
        # -- a finite probe, no reference yet: the approval is reused ----------
        ctx = _context(tmp, "cand_finite")
        ctx.cache.update(cache)
        kind, out = _run(ctx, 30, None)
        marker = ctx.marker("cost").get()
        check(
            "a finite probe with no reference reuses the approval and says so",
            kind == "returned" and out == 30 and marker.get("reused_approval") is True,
            f"{kind} {out} {marker}",
        )
        prof = (ctx.work / "cost").get()
        real_median = float(prof["median_start_s"])
        check(
            "the probe record has finite objectives",
            all(v not in (float("inf"), None) for v in prof["probe_fvals"]),
            str(prof["probe_fvals"]),
        )
        cache = dict(
            ctx.cache
        )  # the compiled problem, so the next builds are cache hits

        # -- an all-inf probe with a reference: a GATE, not a silent reuse ----
        real_multistart = cost_profile.run_multistart
        cost_profile.run_multistart = lambda problem, n, seed, spec, **kw: (
            _FakeResult([float("inf")] * n, 0.019)
        )
        try:
            ctx = _context(tmp, "cand_laplace")
            ctx.cache.update(cache)
            ref = {
                "candidate": "cand_finite",
                "median_start_s": real_median,
                "n_starts": 30,
            }
            kind, payload = _run(ctx, 30, ref)
            check(
                "an all-inf probe raises the budget gate for THIS candidate",
                kind == "gate" and payload["module"] == "cost_boundary_estimation",
                f"{kind}",
            )
            if kind == "gate":
                lines = "\n".join(payload["lines"])
                check(
                    "the card says the approval is NOT reused, and why",
                    "NOT reused" in lines
                    and "non-finite" in lines
                    and "'cand_finite'" in lines,
                    lines[:300],
                )
                check(
                    "the question names the candidate and the projection is its own",
                    "'cand_laplace'" in payload["question"]
                    and "differs" in payload["question"],
                    payload["question"],
                )
                check(
                    "`n` is documented as DROPPING the candidate, not stopping the run",
                    "DROPPED" in payload["consequences"][1],
                    str(payload["consequences"]),
                )
                check(
                    "the proposed count is the round's approved 30, not the spec's 100",
                    "with 30 starts" in payload["question"],
                    payload["question"],
                )
            rows = ledger_rows(tmp)
            check(
                "the refusal is ledgered with its reasons and the reference candidate",
                any(
                    e.get("reuse_refused")
                    and e.get("reference_candidate") == "cand_finite"
                    and e.get("candidate") == "cand_laplace"
                    for e in rows
                ),
            )
            prof = (ctx.work / "cost").get()
            check(
                "the cost profile records the refusal", bool(prof.get("reuse_refused"))
            )
            # -- the human answers `n`: the candidate is dropped, named --------
            ctx = _context(tmp, "cand_laplace")
            ctx.cache.update(cache)
            kind, exc = _run(ctx, 30, ref, answer=False)
            check(
                "`n` at the re-asked gate raises BudgetDeclinedForCandidate naming it",
                kind == "declined"
                and getattr(exc, "candidate", None) == "cand_laplace",
                f"{kind} {exc}",
            )
            check(
                "… which the orchestrator treats as a candidate drop, not control flow",
                "BudgetDeclinedForCandidate" not in _control_flow_names(),
            )
            # -- the human answers `y n=12`: fitted with its own answer ---------
            # (another candidate: the `n` above is remembered for cand_laplace,
            # whose card is not asked again this round)
            ctx = _context(tmp, "cand_laplace_yes")
            ctx.cache.update(cache)
            kind, n = _run(ctx, 30, ref, answer=True, note="n=12")
            marker = ctx.marker("cost").get()
            check(
                "`y n=12` approves this candidate alone: 12 starts, re-asked, not the reference",
                kind == "returned"
                and n == 12
                and marker.get("reasked") is True
                and marker.get("budget_reference") is False,
                f"{kind} {n} {marker}",
            )
            check(
                "… and the round's reference candidate is unchanged",
                ctx.cache["_budget_reference"]["candidate"] == "cand_finite",
            )
            # -- 10x slower, finite: re-asked with the ratio on the card --------
            cost_profile.run_multistart = lambda problem, n, seed, spec, **kw: (
                _FakeResult([51.0 + i for i in range(n)], max(real_median, 1e-3) * 10)
            )
            ctx = _context(tmp, "cand_slow")
            ctx.cache.update(cache)
            kind, payload = _run(ctx, 30, ref)
            check(
                "a 10x slower probe is re-asked with the ratio and ceiling on the card",
                kind == "gate" and "ceiling is 5x" in "\n".join(payload["lines"]),
                f"{kind} "
                + (
                    "\n".join(payload["lines"])[:200]
                    if kind == "gate"
                    else str(payload)
                ),
            )
        finally:
            cost_profile.run_multistart = real_multistart
            humangate.configure_file_mode(tmp, None)
            humangate._FILE_MODE["enabled"] = False


def _control_flow_names() -> set[str]:
    from octomod.orchestration import orchestrator

    return set(orchestrator._CONTROL_FLOW_NAMES)


def main() -> int:
    test_verdict_is_pure_and_names_its_reasons()
    test_a_real_probe_reuses_or_reasks()
    return finish(
        "\nPROBE REUSE",
        "\nprobe reuse: every candidate's probe is read, and a mismatch asks",
    )


if __name__ == "__main__":
    sys.exit(main())
