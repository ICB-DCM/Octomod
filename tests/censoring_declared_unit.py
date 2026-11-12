"""Below-detection measurements are declared, counted and reported, never modelled.

  1. a bad label, rule or threshold is refused by index; the summary counts the rows;
  2. the extraction contract, its skill and `censoring.RULES` name the same rules;
  3. a good declaration passes T0 and is an advisory finding; a bad one fails T0;
  4. a stub run with a declared floor carries it to data, prompt, ledger and report;
  5. a declaration corrected on the re-ask is what the run carries.

    uv run python tests/censoring_declared_unit.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check  # noqa: E402

from octomod import config  # noqa: E402
from octomod.agents import ROLES  # noqa: E402
from octomod.workflow_modules.data import censoring as cen  # noqa: E402
from octomod.workflow_modules.data.engine import make_data_gates  # noqa: E402
from tests._record import ledger_rows, reports_dir, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR


def _table() -> pd.DataFrame:
    rows = []
    for cond in ("c0", "c1"):
        for t, v in ((0.0, 6.0), (1.0, 6.3), (2.0, 7.5), (3.0, 9.0)):
            rows.append(
                {
                    "observable_label": "a",
                    "condition_label": cond,
                    "condition_key": cond,
                    "time": t,
                    "value": v,
                    "replicate": 1,
                }
            )
    return pd.DataFrame(rows)


GOOD = [{"observable_label": "a", "threshold": 6.3, "rule": "imputed", "note": "floor"}]


def test_pure() -> None:
    check("well-formed passes", cen.problems(GOOD, ["a"]) == [])
    bad = cen.problems(
        [{"observable_label": "zz", "rule": "fixed", "threshold": "low", "x": 1}], ["a"]
    )
    check(
        "label, rule, threshold and unknown key are each named by index",
        len(bad) == 4 and all("below_detection[0]" in b for b in bad),
        str(bad),
    )
    s = cen.summary(GOOD, _table())
    check(
        "the summary counts the rows at or below the threshold",
        s[0]["n_rows"] == 8 and s[0]["n_at_or_below_threshold"] == 4,
        json.dumps(s),
    )
    line = cen.findings(s)[0]
    check(
        "the finding names label, rule and count",
        "a:" in line and "imputed" in line and "4 of 8" in line,
        line,
    )
    agent = cen.for_agent(s)
    check(
        "the agent block says what to do at the floor",
        agent is not None and "conditional" in agent["how_to_read_this"],
    )
    check("no declarations: nothing for the agent", cen.for_agent([]) is None)
    s = cen.summary(GOOD, _table(), counted_on="the raw table")
    check(
        "the summary records which table it counted on",
        s[0]["counted_on"] == "the raw table",
    )
    s = cen.summary(GOOD, None)
    line = cen.findings(s)[0]
    check(
        "no table: the counts are None and the line says so — never 0 of 0",
        s[0]["n_rows"] is None
        and "counts not recorded" in line
        and "0 of 0" not in line,
        line,
    )


def test_drift() -> None:
    contract = ROLES["data_extraction"].contract
    check(
        "the extraction contract offers below_detection with every rule",
        "below_detection" in contract and all(r in contract for r in cen.RULES),
    )
    skill = (REPO / "skills" / "data_extraction.md").read_text()
    check(
        "the extraction skill says declare, never fix",
        "below_detection" in skill and all(f"`{r}`" in skill for r in cen.RULES),
    )
    obs = (REPO / "skills" / "observation.md").read_text()
    check(
        "the observation skill knows the key it will see",
        "data_signals.below_detection" in obs,
    )


def _gates(report: dict):
    ctx = SimpleNamespace(testcase={}, spec=None)
    return {g.gate_id: g for g in make_data_gates(_table(), report, ctx)}


def test_s2_gates() -> None:
    base = {
        "observable_labels": [
            {"label": "a", "units": "arbitrary", "error_type": "replicates"}
        ],
        "mappings": [{"observable_label": "a"}],
    }
    g = _gates({**base, "below_detection": GOOD})
    r = g["data_units_and_error_declared"]()
    check(
        "a well-formed declaration passes T0 and is named in the detail",
        r.passed and "1 below-detection declaration" in r.detail,
        r.detail,
    )
    r = g["data_plausibility_screen"]()
    check(
        "the advisory screen reports it with the count",
        r.passed
        and not r.blocking
        and any("imputed" in f for f in r.advisory_findings),
        r.detail,
    )
    g = _gates(
        {**base, "below_detection": [{"observable_label": "nope", "rule": "imputed"}]}
    )
    r = g["data_units_and_error_declared"]()
    check(
        "an undeclared label fails T0, naming the entry",
        not r.passed and "below_detection[0].observable_label 'nope'" in r.detail,
        r.detail,
    )
    g = _gates(base)
    r = g["data_units_and_error_declared"]()
    check(
        "no declaration: the gate reads as before", r.passed and "below" not in r.detail
    )


def test_stub_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "toy_phos_floor"
        shutil.copytree(REPO / "testcase" / "toy_phos", case)
        stub = case / "stubs" / "data_extraction.json"
        d = json.loads(stub.read_text())
        d["below_detection"] = [
            {
                "observable_label": "pR_au",
                "threshold": 0.05,
                "rule": "left_as_is",
                "note": "fixture: densitometry floor stated by the source",
            }
        ]
        stub.write_text(json.dumps(d, indent=2))
        rid = f"c51_floor_{time.strftime('%H%M%S')}"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "octomod",
                "run",
                "--testcase",
                str(case),
                "--backend",
                "stub",
                "--auto-approve",
                "--run-id",
                rid,
                "--overwrite",
            ],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=REPO,
        )
        check(
            "the run finishes with a declared floor",
            proc.returncode == 0,
            f"exit {proc.returncode}: {proc.stderr.strip()[-300:]}",
        )
        r0 = rnd(run_root(rid), 0)
        rep = (r0 / "data/report").get()
        check(
            "data/report carries the declaration",
            rep.get("below_detection")
            and rep["below_detection"][0]["rule"] == "left_as_is",
        )
        summ = (rep.get("below_detection_summary") or [{}])[0]
        check(
            "the RECORDED count is 36 rows, 3 at or below the floor, on the raw values",
            summ.get("n_rows") == 36
            and summ.get("n_at_or_below_threshold") == 3
            and "raw extracted values" in str(summ.get("counted_on")),
            json.dumps(summ),
        )
        sig = (r0 / "data/signals").get()
        blk = sig.get("below_detection") or {}
        check(
            "data/signals carries the agent block with the row count",
            blk.get("declared")
            and blk["declared"][0]["n_rows"] > 0
            and "conditional" in blk.get("how_to_read_this", ""),
            json.dumps(blk)[:200],
        )
        prompt = ((r0 / "agent_calls").child("observation") / "prompt").text()
        check(
            "the observation-model prompt names the floor",
            '"below_detection"' in prompt and "left_as_is" in prompt,
        )
        rows = ledger_rows(run_root(rid))
        check(
            "the ledger notes the declaration",
            any("below-detection declared" in str(e.get("note")) for e in rows),
        )
        gate = (r0 / "gates").child("data_units_and_error_declared").get()
        check(
            "the T0 declaration gate names it in its detail",
            gate["passed"] and "1 below-detection declaration" in gate["detail"],
            gate["detail"],
        )
        html = (
            reports_dir(run_root(rid)) / "round_0" / "report" / "report.html"
        ).read_text()
        check(
            "report.html says the comparison is conditional on the source's handling",
            "Below-detection measurements declared" in html
            and "conditional on it" in html
            and "left_as_is" in html,
        )
        check(
            "report.html shows the RECORDED numbers — 3 of 36 rows — not a recount",
            "3 of 36 rows at or below 0.05" in html and "0 of 0" not in html,
        )
        check(
            "the report names the replicate ids per file (dd624d6's table has a reader)",
            "Replicate ids" in html and "replicate label in the file" in html,
        )
        check(
            "the page discloses that the observation-model agent was shown the floor",
            "shown to the observation-model agent" in html,
        )
        check(
            "and the ledger notes it at S3, beside the call",
            any(
                "observation-model agent is shown 1 below-detection"
                in str(e.get("note"))
                and e.get("module") == "assembly"
                for e in rows
            ),
        )


def _stub_run(case: Path, rid: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "octomod",
            "run",
            "--testcase",
            str(case),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            rid,
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=REPO,
    )


def test_a_corrected_declaration_survives_the_re_ask() -> None:
    """The entry corrected on the re-ask is what the run carries, not an empty list."""
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "toy_phos_floor_reask"
        shutil.copytree(REPO / "testcase" / "toy_phos", case)
        single = case / "stubs" / "data_extraction.json"
        d = json.loads(single.read_text())
        single.unlink()
        bad = dict(d)
        bad["below_detection"] = [
            {"observable_label": "not_a_label", "threshold": 0.05, "rule": "imputed"}
        ]
        good = dict(d)
        good["below_detection"] = [
            {
                "observable_label": "pR_au",
                "threshold": 0.05,
                "rule": "imputed",
                "note": "fixture: corrected on the re-ask",
            }
        ]
        (case / "stubs" / "data_extraction.1.json").write_text(
            json.dumps(bad, indent=2)
        )
        (case / "stubs" / "data_extraction.2.json").write_text(
            json.dumps(good, indent=2)
        )
        rid = f"c51_reask_{time.strftime('%H%M%S')}"
        proc = _stub_run(case, rid)
        check(
            "the run finishes after the declaration gate re-asked once",
            proc.returncode == 0,
            f"exit {proc.returncode}: {proc.stderr.strip()[-300:]}",
        )
        root = run_root(rid)
        rows = ledger_rows(root)
        calls = [
            e
            for e in rows
            if e.get("event") == "agent_call" and e.get("role") == "data_extraction"
        ]
        reasked = [
            e
            for e in rows
            if e.get("event") == "redraft_attributed"
            and e.get("gate_id") == "data_units_and_error_declared"
        ]
        check(
            "data_extraction was called twice, the second time for the declaration gate",
            len(calls) == 2 and len(reasked) == 1,
            f"{len(calls)} calls, {len(reasked)} attributed re-asks",
        )
        rep = (rnd(root, 0) / "data/report").get()
        decl = rep.get("below_detection") or []
        check(
            "the CORRECTED declaration is what the run carries",
            len(decl) == 1
            and decl[0]["observable_label"] == "pR_au"
            and "corrected" in decl[0].get("note", ""),
            json.dumps(decl),
        )
        gate = (rnd(root, 0) / "gates").child("data_units_and_error_declared").get()
        check(
            "the gate that passed did so WITH one declaration, not with none",
            gate["passed"] and "1 below-detection declaration" in gate["detail"],
            gate["detail"],
        )
        sig = (rnd(root, 0) / "data/signals").get()
        check(
            "and the signals carry the corrected entry to the observation agent",
            (sig.get("below_detection") or {}).get("declared", [{}])[0].get("rule")
            == "imputed",
        )


def main() -> int:
    print("pure functions")
    test_pure()
    print("drift")
    test_drift()
    print("S2 gates")
    test_s2_gates()
    print("stub run")
    test_stub_run()
    print("re-ask keeps the corrected declaration (review finding 1)")
    test_a_corrected_declaration_survives_the_re_ask()
    if FAILS:
        print(f"\nCENSORING DECLARED FAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print(
        "\nCENSORING DECLARED UNIT OK — a detection floor is declared, counted, told to "
        "the observation agent and stated on the report; no likelihood changed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
