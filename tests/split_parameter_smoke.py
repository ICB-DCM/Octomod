"""A `split_parameter` axis bought at expansion is resolved and fitted the next round.

A copy of `testcase/abcd_expansion` whose second expansion reply proposes one
axis, `split_parameter {parameter_id: k_cat1, by: bx11}`, and whose third
proposes nothing, so the run ends after round 1. Token-free; full effort.

  1. the expansion card shows the axis as `parameter_split` and buys it;
  2. round 1's model space holds it resolved: a copy per bx11 value in every condition;
  3. round 1 fits the split: both copies estimated, k_cat1 out of the table;
  4. the run ends cleanly.

    uv run python tests/split_parameter_smoke.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish, run_cli  # noqa: E402
from _record import pending_gate, rnd, run_root, work  # noqa: E402

from octomod import config  # noqa: E402
from octomod.result.node import candidate_ids  # noqa: E402

RUNS = config.RUNS_DIR
RUN_ID = "split_parameter_smoke"
AXIS_ID = "kcat1_by_inhibitor"


def _fixture() -> Path:
    case = Path(tempfile.mkdtemp()) / "abcd_expansion_split"
    shutil.copytree(
        REPO / "testcase" / "abcd_expansion",
        case,
        ignore=shutil.ignore_patterns("truth"),
    )
    stubs = case / "stubs"
    (stubs / "revision.2.json").write_text(
        json.dumps(
            {
                "diagnosis": "STUB (split smoke): the ProD conversion may run at a different rate with "
                "the inhibitor present; one copy of k_cat1 per bx11 arm tests it.",
                "axes": [
                    {
                        "id": AXIS_ID,
                        "question": "Is k_cat1 the same with and without BX-11?",
                        "default": "off",
                        "on_assembly_patch": {
                            "split_parameter": {"parameter_id": "k_cat1", "by": "bx11"}
                        },
                        "adds_parameters": [],
                        "rationale": "the BX-11 residuals are a difference in speed, not in shape",
                        "discriminating_evidence": "obs_ProD in c_u1_bx against c_u1",
                        "priority": 1,
                    }
                ],
                "stop_instead": False,
            },
            indent=2,
        )
    )
    (stubs / "revision.3.json").write_text(
        json.dumps(
            {
                "diagnosis": "STUB (split smoke, round 1): nothing further to propose.",
                "axes": [],
                "stop_instead": True,
            },
            indent=2,
        )
    )
    return case


def _by(df: pd.DataFrame | None, column: str) -> pd.DataFrame:
    """A PEtab table indexed by its id column (the record keeps it a column)."""
    if df is None:
        return pd.DataFrame()
    return df.set_index(column) if column in df.columns else df


def main() -> int:
    root = run_root(RUN_ID, RUNS)  # the run is one record file
    if root.exists():
        root.store.remove()
    case = _fixture()
    base = [
        "run",
        "--testcase",
        str(case),
        "--backend",
        "stub",
        "--run-id",
        RUN_ID,
        "--gate-mode",
        "file",
    ]
    cards: list[dict] = []
    scope = [("y", "axes: product_feedback")]
    rc = run_cli(base)
    for _ in range(40):
        if rc != 3:
            break
        payload = pending_gate(root)
        cards.append(payload)
        ans, note = (
            scope.pop(0) if payload["module"] == "model_scope" and scope else ("y", "")
        )
        rc = run_cli(
            base + ["--gate-answer", ans] + (["--gate-note", note] if note else [])
        )
    check("the run ends cleanly", rc == 0, f"rc={rc}")

    card = next((c for c in cards if c["module"] == "revision"), {})
    shown = "\n".join(str(x) for x in card.get("lines") or [])
    check(
        "the expansion card shows the split as parameter_split",
        f"{AXIS_ID} [parameter_split]" in shown,
        shown[-700:],
    )
    exp = (rnd(root, 0) / "expansion").get(None) or {}
    check(
        "… and bought it",
        exp.get("expanded") and exp.get("axes") == [AXIS_ID],
        str(exp)[:300],
    )

    space = (rnd(root, 1) / "space/axes").get(None) or []
    ax = next((a for a in space if a.get("id") == AXIS_ID), {})
    patch = (ax.get("on_assembly_patch") or {}).get("split_parameter") or {}
    copies = patch.get("copies_by_condition") or {}
    asm = (rnd(root, 0) / "shared_assembly").get(None)
    cond_ids = {c["condition_id"] for c in asm["conditions"]} if asm else set()
    check(
        "round 1's model space holds it resolved: a copy in every condition",
        copies
        and set(copies) == cond_ids
        and set(copies.values()) == {"k_cat1_0", "k_cat1_1"},
        f"{copies} vs {sorted(cond_ids)}",
    )
    check(
        "… with the copies' rows written by the engine",
        sorted(p["id"] for p in ax.get("adds_parameters") or [])
        == ["k_cat1_0", "k_cat1_1"],
        str(ax.get("adds_parameters"))[:300],
    )

    r1 = rnd(root, 1)
    fitted = []
    for cid in candidate_ids(r1) if r1.exists() else []:
        table = (work(root, 1, cid) / "petab" / "parameters").table(None)
        if table is not None and "k_cat1_1" in table.to_csv(sep="\t"):
            fitted.append(work(root, 1, cid))
    check(
        "round 1 built a candidate carrying the split",
        len(fitted) == 1,
        str([d.key for d in fitted]),
    )
    if fitted:
        d = fitted[0]
        par = _by((d / "petab" / "parameters").table(None), "parameterId")
        cond = _by((d / "petab" / "conditions").table(None), "conditionId")
        check(
            "both copies estimated, k_cat1 out of the parameter table",
            {"k_cat1_0", "k_cat1_1"} <= set(par.index)
            and "k_cat1" not in par.index
            and int(par.loc["k_cat1_1", "estimate"]) == 1,
            str(sorted(par.index)),
        )
        check(
            "every condition reads its arm's copy",
            "k_cat1" in cond.columns
            and set(cond["k_cat1"]) == {"k_cat1_0", "k_cat1_1"},
            str(cond.get("k_cat1")),
        )
        best = ((d / "estimation").get(None) or {}).get("best_x_unscaled", {})
        check(
            "… and it was fitted",
            "k_cat1_0" in best and "k_cat1_1" in best,
            str(list(best))[:300],
        )
    shutil.rmtree(case.parent, ignore_errors=True)
    return finish(
        "\nSPLIT PARAMETER SMOKE",
        "\nSPLIT PARAMETER SMOKE OK — a split proposed at the expansion gate is resolved, seeded, rendered and fitted",
    )


if __name__ == "__main__":
    sys.exit(main())
