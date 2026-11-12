"""Observation-layer axes in the model space, end to end, token-free.

testcase/abcd_obsaxis declares one structural axis (basal_route) and one
observation axis (prod_offset = add_offset on the ProD readout); buying both
gives four models, two of which differ from the others only in an overlay.

  1. the observation axis reaches the scope gate and is enumerated;
  2. 4 candidates, each with a battery-clean PEtab problem;
  3. only the offset candidates resolve `off_obs_ProD` and estimate it;
  4. the overlay application is recorded (`assembly_overlay_applied` + ledger);
  5. the selection reports over all four; the petab_select cross-check passes.

    uv run python tests/obsaxis_smoke.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.gates.petab_gates import PetabTables  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from tests._record import ledger_rows, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

RUN_ID = "obsaxis_smoke"


def main() -> int:
    root = run_root(RUN_ID, RUNS)  # the run is one file
    if root.exists():
        root.store.remove()
    cmd = [
        str(REPO / "run.sh"),
        "run",
        "--testcase",
        "testcase/abcd_obsaxis",
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--auto-approve",
        "--gate-note",
        "axes: basal_route, prod_offset; lattice",
    ]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    if "prod_offset" not in out.split("OPEN STRUCTURAL AXES")[-1][:2000]:
        print(out[-3000:])
        print("FAIL: the observation axis never reached the scope gate")
        return 1
    r0 = rnd(root, 0)
    cands = (r0 / "space/candidates").get()
    ids = sorted(c["id"] for c in cands)
    print(f"candidates: {ids}")
    if len(cands) != 4:
        print(out[-3000:])
        print(f"FAIL: expected 4 models from 2 axes, got {len(cands)}")
        return 1
    ledger = ledger_rows(root)
    for c in cands:
        cid = c["id"]
        wd = tree.work_node(r0, cid)
        # Assert the RESOLVED expression, not the formula text: the offset enters
        # through PEtab's placeholder (`observableParameter1_obs_ProD` in the
        # formula, `off_obs_ProD` in the measurements column).
        tables = PetabTables.from_work(wd, tree.model_node(r0, cid))
        par = tables.parameters
        prod = tables.observable_expression("obs_ProD")
        has_off = "off_obs_ProD" in prod
        want_off = "prod_offset" in cid
        if has_off != want_off:
            print(
                f"FAIL: {cid}: resolved observable expression {prod!r} — overlay "
                f"{'missing' if want_off else 'leaked'}"
            )
            return 1
        if want_off:
            if "off_obs_ProD" not in set(par["parameterId"]):
                print(f"FAIL: {cid}: offset parameter not in petab/parameters")
                return 1
            if not (wd / "assembly_overlay_applied").exists():
                print(f"FAIL: {cid}: overlay application not recorded")
                return 1
            if c.get("assembly_overlay") != [
                {"add_offset": {"observable_label": "ProD"}}
            ]:
                print(
                    f"FAIL: {cid}: space/candidates lacks the overlay: {c.get('assembly_overlay')}"
                )
                return 1
        s3 = [
            e
            for e in ledger
            if e.get("event") == "gate"
            and e.get("module") == "assembly"
            and not e["passed"]
            and e.get("blocking")
        ]
        if s3:
            print(f"FAIL: blocking S3 battery failures: {s3[:2]}")
            return 1
    notes = [
        e
        for e in ledger
        if e.get("event") == "note"
        and "applied observation-axis overlay" in str(e.get("note"))
    ]
    if len(notes) != 2:
        print(f"FAIL: expected 2 overlay-application notes, saw {len(notes)}")
        return 1
    report = (r0 / "evaluation").get()
    disc = report.get("discrimination") or {}
    if len(disc.get("candidates", [])) != 4:
        print("FAIL: selection did not report all four candidates")
        return 1
    xg = [e for e in ledger if e.get("gate_id") == "evaluation_selection_crosscheck"]
    if not xg or not xg[-1]["passed"]:
        print(f"FAIL: petab_select cross-check missing/failed: {xg}")
        return 1
    print("selection:")
    for c in sorted(disc["candidates"], key=lambda c: c["delta_aic"]):
        print(
            f"  {c['id']:28s} k={c['n_est']:2d}  dAIC {c['delta_aic']:8.2f}  weight {c['akaike_weight']:.4f}"
        )
    space = (r0 / "space/axes").get()
    kinds = {a["id"]: a.get("kind") for a in space}
    if kinds != {"basal_route": "structure", "prod_offset": "observation"}:
        print(f"FAIL: axis kinds not recorded: {kinds}")
        return 1
    print(
        "\nOBSAXIS SMOKE OK — observation axis declared, bought, enumerated as an "
        "overlay, merged per candidate, battery-clean, selected over"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
