"""The convergence gate buys an optimiser comparison, end to end through the real engine.

`compare` at `estimation_convergence` runs the bake-off, writes, ledgers and reports it, and returns
to the gate. The overlay raises `gates.waterfall.k` above the start count to fire the gate:
under-starting alone does not, since the engine's solver tolerances keep fides reliable here.

    uv run python tests/optimizer_compare_smoke.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check, finish  # noqa: E402
from _record import ledger_rows, pending_gate, reports_dir, run_root, work  # noqa: E402

from octomod import config  # noqa: E402

# `test_runs/` under the battery (tests/run_all.py sets OCTOMOD_RUNS_DIR),
# `runs/` otherwise; a suite never spells `runs/` itself.
RUNS = config.RUNS_DIR

CASE = "toy_oscillator_multimodal"
N_STARTS = 4


def drive(run_id: str, overlay: Path, answers: dict) -> tuple[int, list[str]]:
    """Answer file gates from `answers` by module (`y` elsewhere); return (rc, paused gates)."""
    from octomod.cli import main as cli

    base = [
        "run",
        "--testcase",
        f"testcase/{CASE}",
        "--backend",
        "stub",
        "--run-id",
        run_id,
        "--gate-mode",
        "file",
    ]
    # the run is one file, <RUNS>/<id>.h5; the gate is a group of it
    root = run_root(run_id, RUNS)
    seen: list[str] = []
    previous = os.environ.get("OCTOMOD_SPEC_OVERLAY")
    os.environ["OCTOMOD_SPEC_OVERLAY"] = str(overlay)
    try:
        rc = cli(base)
        for _ in range(40):
            if rc != 3:
                break
            payload = pending_gate(root)
            assert payload is not None, "exit 3 without a pending gate in the record"
            seen.append(payload["module"])
            spec = answers.get(payload["module"], ("y", ""))
            if isinstance(spec, list):
                spec = spec.pop(0) if spec else ("y", "")
            ans, note = spec
            cmd = base + ["--gate-answer", ans]
            if note:
                cmd += ["--gate-note", note]
            rc = cli(cmd)
    finally:
        if previous is None:
            os.environ.pop("OCTOMOD_SPEC_OVERLAY", None)
        else:
            os.environ["OCTOMOD_SPEC_OVERLAY"] = previous
    return rc, seen


def main() -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    # Too few starts for a problem with five basins. The comparison's size is not
    # set here: on a fit this small the budget derivation falls to
    # `min_compare_starts`, because a human asked for the comparison by name.
    overlay = tmp / "force_convergence_gate.yaml"
    overlay.write_text(
        "estimation:\n"
        f"  n_starts_default: {N_STARTS}\n"
        f"  n_starts_bounds: [1, {N_STARTS}]\n"
        "gates:\n"
        "  waterfall:\n"
        # above the start count, so the plateau check cannot pass and the
        # convergence gate fires deterministically
        f"    k: {N_STARTS + 2}\n"
    )
    run_id = f"optcompare_{time.strftime('%H%M%S')}"

    print(f"run: {run_id} — {N_STARTS} starts, waterfall k forced to {N_STARTS + 2}")
    rc, gates = drive(
        run_id,
        overlay,
        # `compare` at the convergence gate, then accept: the comparison is
        # not a decision, it returns to the same gate for a real answer.
        {
            "estimation_convergence": [
                ("y", "compare"),
                ("y", "accept the comparison explains it"),
            ]
        },
    )
    root = run_root(run_id, RUNS)
    # a sibling of `cost` in the fitted problem's group of the record
    art = work(root, 0) / "optimizer_comparison"

    check(
        "the convergence gate fired",
        "estimation_convergence" in gates,
        f"gates: {gates}",
    )
    if not art.exists():
        check(
            "the comparison record was written",
            False,
            f"missing {art.key} — exit {rc}, gates {gates}",
        )
        print("\nOPTIMIZER COMPARE SMOKE FAILED")
        for f in FAILS:
            print(f"  · {f}")
        return 1
    payload = art.get()
    v = payload["verdict"]
    check("the comparison record was written", True, art.key)
    ran = [m for m in payload["methods"] if m["available"]]
    check(
        "more than one optimiser actually ran",
        len(ran) > 1,
        f"{[m['name'] for m in ran]}",
    )
    check(
        "every method carries both metrics",
        all(
            m["optimality_gap"] is not None and m["overall_efficiency"] is not None
            for m in ran
        ),
        f"{[(m['name'], m['optimality_gap'], m['overall_efficiency']) for m in ran]}",
    )
    check(
        "the remedy is named",
        v.get("remedy") in {"more_starts", "different_optimizer", "none"},
        f"remedy={v.get('remedy')}",
    )
    # THE point of the suite: an under-started incumbent must not be blamed.
    check(
        "an under-started fit asks for MORE STARTS, not a different optimiser",
        v.get("remedy") != "different_optimizer"
        or v.get("incumbent_success_rate") == 0,
        f"remedy={v.get('remedy')} rate={v.get('incumbent_success_rate')} "
        f"detail={str(v.get('remedy_detail'))[:120]}",
    )
    if v.get("remedy") == "more_starts":
        check(
            "and it says how many starts, from the observed rate",
            isinstance(v.get("starts_for_95pc"), int) and v["starts_for_95pc"] > 0,
            f"{v.get('starts_for_95pc')} starts for 95%",
        )
    # the probe-time selection is not exercised here: the automatic path refuses a
    # comparison a four-start fit cannot afford; its merge into this artifact is
    # unit tested in `optimizer_compare_unit.py`
    led = ledger_rows(root)
    check(
        "the ledger records the comparison",
        any("optimiser comparison: winner=" in str(r.get("note", "")) for r in led),
        "",
    )
    html = (reports_dir(root) / "round_0" / "report" / "report.html").read_text()
    check(
        "the round report shows the table and explains both metrics",
        "Optimiser comparison" in html
        and "Optimality gap" in html
        and "Overall efficiency" in html,
        "",
    )
    check(
        "the run finished after the comparison returned to the gate",
        rc == 0,
        f"exit {rc}, gates {gates}",
    )
    check(
        "the comparison gate was asked twice (compare, then a real answer)",
        gates.count("estimation_convergence") >= 2,
        f"{gates.count('estimation_convergence')} pause(s) at estimation_convergence",
    )

    print()
    return finish(
        "OPTIMIZER COMPARE SMOKE",
        f"OPTIMIZER COMPARE SMOKE OK — the gate bought a comparison, "
        f"{len(ran)} optimisers ran, and the remedy was {v.get('remedy')}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
