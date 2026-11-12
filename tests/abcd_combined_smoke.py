"""The combined abcd case: AIC picks the mechanism, T2' is judged per candidate.

  1. `data_holdout_labels_resolve` passes for the staged `u=0.25,bx11=1`;
  2. each candidate holds out exactly that cell (48 rows), none of it in training;
  3. every `candidates/<id>/gates/evaluation_t2prime_holdout` exists: M3 passes, M1_chain fails;
  4. `evaluation`: T2' per candidate, computed `t2prime_passed`, the truth's winner;
  5. `report_md`'s discrimination table shows T2' beside every candidate;
  6. the verdict card shows T2' beside every weight;
  7. the run completes and scores against truth;
  8. `_rule3` holds on every branch: nobody, the winner, a loser, everybody fails.

    uv run python tests/abcd_combined_smoke.py
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.result import node as tree  # noqa: E402
from tests._record import rnd, run_root  # noqa: E402
from tests.abcd_smoke import ledger, run_case  # noqa: E402

CASE = "abcd_combined"
HELD_OUT = {"u": 0.25, "bx11": 1}
CANDIDATES = {"M1_chain", "M2_feedforward", "M3_ff_feedback"}


def unit_rule3() -> None:
    from octomod.workflow_modules.evaluation.engine import _rule3

    # AIC: A -182, B -186, C -218 -> criterion ranking C, B, A
    fits = [
        {
            "model_id": "A",
            "axes_on": [],
            "n_estimated": 9,
            "nllh": -100.0,
            "n_data": 96,
        },
        {
            "model_id": "B",
            "axes_on": [],
            "n_estimated": 10,
            "nllh": -103.0,
            "n_data": 96,
        },
        {
            "model_id": "C",
            "axes_on": [],
            "n_estimated": 11,
            "nllh": -120.0,
            "n_data": 96,
        },
    ]
    # nobody fails: the criterion's verdict stands untouched
    v = _rule3("C", fits, set(), "AIC", 2.0, 0.7)
    assert v["winner"] == "C" and v["override"] is None and v["t2prime_passed"], v
    # the criterion winner fails the held-out cell: the same criterion over the
    # survivors — B beats A by dAIC 4, decisive at weight 0.88
    v = _rule3("C", fits, {"C"}, "AIC", 2.0, 0.7)
    assert v["winner"] == "B" and v["t2prime_passed"], v
    assert v["override"]["criterion_winner"] == "C", v
    assert v["override"]["chosen"] == "B", v
    assert v["override"]["excluded_by_t2prime"] == ["C"], v
    assert v["indistinguishable"] == ["B"] and v["decisive"] is True, v
    # a loser fails: nothing changes, the failure is on record beside its weight
    v = _rule3("C", fits, {"A"}, "AIC", 2.0, 0.7)
    assert v["winner"] == "C" and v["override"] is None and v["t2prime_passed"], v
    # everybody fails: no different winner, the honest ending
    v = _rule3("C", fits, {"A", "B", "C"}, "AIC", 2.0, 0.7)
    assert v["winner"] == "C" and v["override"] is None, v
    assert v["t2prime_passed"] is False, v
    print("  Rule 3 unit: nobody / winner / loser / everybody failing — OK")


def _prod_id(work) -> str:
    asm = (work / "assembly").get()
    ids = [
        o["observable_id"]
        for o in asm["observables"]
        if "ProD" in str(o.get("maps_to_label", "")) or "ProD" in o["observable_id"]
    ]
    assert len(ids) == 1, ids
    return ids[0]


class _Tee(io.TextIOBase):
    """Copies stdout: under --auto-approve the console is the card's only record."""

    def __init__(self, real):
        self.real, self.buf = real, io.StringIO()

    def write(self, s):
        self.real.write(s)
        self.buf.write(s)
        return len(s)

    def flush(self):
        self.real.flush()


def smoke() -> None:
    rid = f"smoke_abcd_comb_{time.strftime('%H%M%S')}"
    tee = _Tee(sys.stdout)
    with contextlib.redirect_stdout(tee):
        rc = run_case(CASE, rid)
    console = tee.buf.getvalue()
    root = run_root(rid)  # the run is one file
    r0 = rnd(root, 0)
    rows = ledger(rid)

    # (1) the staged holdout resolves against the data's own columns
    g = [e for e in rows if e.get("gate_id") == "data_holdout_labels_resolve"]
    assert g and g[-1]["passed"], g

    # (2) every candidate's held-out table is exactly the (0.25, 1) cell
    cands = tree.candidate_ids(r0)
    assert set(cands) == CANDIDATES, cands
    for cid in cands:
        petab = tree.work_node(r0, cid) / "petab"
        hold = (petab / "holdout_measurements").table()
        train = (petab / "measurements").table()
        cond = (petab / "conditions").table()
        assert len(hold) == 48, (cid, len(hold))
        assert len(train) == 96 * 3 - 48, (cid, len(train))
        held_ids = set(hold["simulationConditionId"].astype(str))
        assert len(held_ids) == 1, held_ids
        row = cond.set_index("conditionId").loc[next(iter(held_ids))]
        assert float(row["u"]) == HELD_OUT["u"], row.to_dict()
        assert int(row["bx11"]) == HELD_OUT["bx11"], row.to_dict()
        assert not held_ids & set(train["simulationConditionId"].astype(str))
    print(f"  held-out table per candidate: 48 rows, all at {HELD_OUT}; training 240")

    # (3) T2' per candidate, persisted under the candidate's gates/. M1_chain
    # fails on ProD: a RegB-only chain cannot make ProD under BX-11 at any setting.
    t2 = {}
    for cid in cands:
        verdict = tree.gates_node(r0, cid).child("evaluation_t2prime_holdout")
        assert verdict.exists(), f"{verdict.key} missing"
        t2[cid] = verdict.get()
    for cid in sorted(t2):
        rec = t2[cid]
        print(
            f"  T2' {cid:16s} passed={rec['passed']!s:5s} value={rec['value']} "
            f"threshold={rec['threshold']}  {str(rec['detail'])[:150]}"
        )
    assert t2["M3_ff_feedback"]["passed"] is True, t2["M3_ff_feedback"]
    assert t2["M1_chain"]["passed"] is False, t2["M1_chain"]
    prod = _prod_id(tree.work_node(r0, "M1_chain"))
    assert prod in str(t2["M1_chain"]["detail"]), (prod, t2["M1_chain"]["detail"])
    t2rows = [e for e in rows if e.get("gate_id") == "evaluation_t2prime_holdout"]
    assert len(t2rows) == 3, [(e.get("module"), e.get("passed")) for e in t2rows]

    # (4) the report carries T2' per candidate; the run-level flag is computed
    rep = (r0 / "evaluation").get()
    d = rep["discrimination"]
    assert set(d["t2prime"]) == CANDIDATES, d["t2prime"]
    assert d["t2prime"]["M1_chain"]["passed"] is False, d["t2prime"]["M1_chain"]
    assert d["t2prime"]["M3_ff_feedback"]["passed"] is True
    assert rep["t2prime_passed"] is True and d["t2prime_passed"] is True, rep.get(
        "t2prime_passed"
    )
    assert d["t2prime_override"] is None, d["t2prime_override"]
    truth = json.loads(
        (REPO / "testcase" / CASE / "truth" / "true_parameters.json").read_text()
    )
    assert d["winner"] == truth["true_mechanism_id"], (d["winner"], truth)
    assert rep["holdout"]["available"], rep["holdout"]
    assert set(rep["holdout"]["per_candidate"]) == CANDIDATES, rep["holdout"]
    print(
        f"  AIC table: "
        f"{[(r['id'], r['delta_aic'], r['akaike_weight']) for r in d['candidates']]}"
    )

    # (5) report_md: the discrimination table shows T2' beside every candidate
    md = (r0 / "report_md").text()
    assert "T2' (held-out)" in md, "report_md has no T2' column"
    for cid in CANDIDATES:
        line = next(x for x in md.splitlines() if x.startswith(f"| {cid} |"))
        assert ("| pass" in line) or ("| FAIL" in line), line
    m1 = next(x for x in md.splitlines() if x.startswith("| M1_chain |"))
    assert "| FAIL" in m1, m1

    # (6) the verdict card the human saw carries T2' beside every weight
    assert "T2' FAIL" in console and "T2' pass" in console, "card lines lack T2'"
    card = [x for x in console.splitlines() if "T2' FAIL" in x or "T2' pass" in x]
    assert len(card) >= 3, card
    print("  verdict card lines:\n    " + "\n    ".join(x.strip() for x in card[:6]))

    # (7) an honest complete ending, scored against truth
    end = [e for e in rows if e["event"] == "run_end"][-1]
    assert end["outcome"] == "completed", end
    assert rc == 0, f"expected exit 0, got {rc}"
    scorer = subprocess.run(
        [
            sys.executable,
            str(REPO / "tests" / "score_against_truth.py"),
            "--run-id",
            rid,
            "--testcase",
            str(REPO / "testcase" / CASE),
        ],
        capture_output=True,
        text=True,
    )
    print(scorer.stdout)
    assert scorer.returncode == 0, scorer.stderr[-800:]
    print("ABCD COMBINED SMOKE OK — criterion picks M3, T2' per candidate on record")


if __name__ == "__main__":
    unit_rule3()
    smoke()
