"""The human hands construction a paper they already have (token-free).

  1. pure functions: the shape check, the fence, the declaration and attribution;
  2. a stub run hands the items to exactly the declared roles, frozen, cached, ledgered;
  3. a blocklisted source or a post-horizon year is refused at the intent gate, by name;
  4. a malformed item (no `supports`) is refused the same way;
  5. a truth/ case must declare `supplied-literature` and a horizon, or is refused.

    uv run python tests/supplied_literature_unit.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check  # noqa: E402

from octomod import config  # noqa: E402
from octomod.workflow_modules.knowledge import supplied_literature as lit  # noqa: E402
from tests._record import ledger_rows, reports_dir, rnd, run_root  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR


ITEM_A = {
    "source": "Fixture Note (2024) — receptor module phosphorylation",
    "title": "Receptor module phosphorylation kinetics",
    "year": 2024,
    "locator": "section 1",
    "supports": "ligand-driven phosphorylation reversed by a constitutive phosphatase",
    "quote": "reversed by a constitutive phosphatase",
    "url": "file:./paper/receptor_note.txt",
}
ITEM_B = {
    "source": "doi:10.0000/fixture.second",
    "title": "A second supplied source with no document",
    "year": 2022,
    "locator": "figure 2",
    "supports": "the dose response saturates above the highest dose used",
}


# ------------------------------------------------------------ 1. pure functions


def test_shape_check_names_the_bad_item() -> None:
    check("no key: no problems", lit.problems({}) == [] and lit.items({}) == [])
    check(
        "well-formed items pass", lit.problems({"supplied_literature": [ITEM_A]}) == []
    )
    bad = lit.problems({"supplied_literature": [ITEM_A, {"source": "x"}]})
    check(
        "a missing `supports` is named by index",
        any("supplied_literature[1].supports" in p for p in bad),
        str(bad),
    )
    bad = lit.problems({"supplied_literature": [{**ITEM_A, "year": "2024"}]})
    check("a string year is refused", any(".year" in p for p in bad), str(bad))
    bad = lit.problems({"supplied_literature": {"source": "x", "supports": "y"}})
    check("a non-list is refused", bool(bad) and "LIST" in bad[0], str(bad))
    bad = lit.problems({"supplied_literature": [{**ITEM_A, "doi": "x"}]})
    check("an unknown key is named", any("unknown key" in p for p in bad), str(bad))


def test_the_fence_refuses_by_name() -> None:
    r = lit.fence_refusals([ITEM_A, ITEM_B], ["fixture.second"], None)
    check(
        "a blocklist entry matching the source refuses THAT item, by name",
        len(r) == 1 and "[1]" in r[0] and "fixture.second" in r[0],
        str(r),
    )
    r = lit.fence_refusals([ITEM_A, ITEM_B], [], 2023)
    check(
        "a year after the declared horizon refuses THAT item",
        len(r) == 1 and "[0]" in r[0] and "2024" in r[0] and "2023" in r[0],
        str(r),
    )
    check(
        "the fence function itself does not judge the year without a horizon "
        "(the intent gate requires one whenever literature is supplied)",
        lit.fence_refusals([ITEM_A, ITEM_B], [], None) == [],
    )
    check(
        "a match on the url counts too",
        len(lit.fence_refusals([ITEM_A], ["receptor_note"], None)) == 1,
    )


def test_a_benchmark_case_must_declare_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tc = Path(tmp) / "case"
        (tc / "truth").mkdir(parents=True)
        intent = {"supplied_literature": [ITEM_B]}
        p = lit.declaration_problem(tc, intent)
        check(
            "truth/ + supplied literature + no declaration is refused, naming the line",
            p is not None and lit.DECLARATION in p,
            str(p),
        )
        (tc / "truth" / "STAGED-ON-PURPOSE.txt").write_text(
            "supplied-literature   # the case builds on a published paper\n"
        )
        check("declared: accepted", lit.declaration_problem(tc, intent) is None)
        check(
            "no truth/: nothing to declare",
            lit.declaration_problem(tc / "x", intent) is None,
        )
        check("no items: nothing to declare", lit.declaration_problem(tc, {}) is None)


def test_attribution_counts_origins() -> None:
    sup = lit.normalized([ITEM_A, ITEM_B])
    check(
        "normalized items carry id, origin and every contract key",
        [s["id"] for s in sup] == ["lit_1", "lit_2"]
        and all(s["origin"] == "human" for s in sup)
        and all(k in sup[1] for k in lit.ITEM_KEYS),
        str(sup[1]),
    )
    research = [{"source": "PMID:12345", "title": "found online", "origin": "research"}]
    decisions = [
        {"decision": "d1", "evidence": [{"source": "lit_1", "supports": "..."}]},
        {
            "decision": "d2",
            "evidence": [{"source": ITEM_B["source"], "supports": "..."}],
        },
        {"decision": "d3", "evidence": [{"source": "PMID:12345"}]},
        {"decision": "d4", "evidence": []},
    ]
    att = lit.attribution(decisions, sup, research)
    check(
        "attribution: two decisions lean on the human's items, one on research, one on neither",
        att["leaned_on_human"] == ["d1", "d2"]
        and att["leaned_on_research"] == ["d3"]
        and att["cited_neither"] == 1,
        json.dumps(att),
    )
    ten = lit.normalized([ITEM_B] * 10)  # lit_1 … lit_10
    only_ten = [{"decision": "d10", "evidence": [{"source": "lit_10", "supports": ""}]}]
    att = lit.attribution(only_ten, ten[:1], [])
    check(
        "lit_1 does not match a citation of lit_10 (word-bounded ids)",
        att["leaned_on_human"] == [] and att["cited_neither"] == 1,
        json.dumps(att),
    )


# ------------------------------------------------------------ the stub runs


def _copy_toy(
    tmp: Path, name: str, items: list[dict], horizon: int | None = 2026
) -> Path:
    case = tmp / name
    shutil.copytree(REPO / "testcase" / "toy_phos", case)
    if horizon is not None:
        # a case that supplies literature declares its horizon; research itself
        # stays off
        tc = yaml.safe_load((case / "testcase.yaml").read_text())
        tc["research"] = {"enabled": False, "max_publication_year": int(horizon)}
        (case / "testcase.yaml").write_text(yaml.safe_dump(tc, sort_keys=False))
    (case / "paper").mkdir()
    (case / "paper" / "receptor_note.txt").write_text(
        "Receptor module phosphorylation kinetics (fixture).\n"
        "Ligand-driven phosphorylation is reversed by a constitutive phosphatase.\n"
    )
    intent = yaml.safe_load((case / "intent.yaml").read_text())
    intent["supplied_literature"] = items
    (case / "intent.yaml").write_text(yaml.safe_dump(intent, sort_keys=False))
    return case


def _cli(case: Path, rid: str) -> subprocess.CompletedProcess:
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


def _ledger(rid: str) -> list[dict]:
    root = run_root(rid, RUNS)
    return ledger_rows(root) if root.exists() else []


def test_a_run_hands_the_items_to_construction() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # an APPLICATION case: no truth/, no horizon declared — accepted, and the
        # S0 row records that the items are not year-fenced
        case = _copy_toy(Path(tmp), "toy_phos_lit", [ITEM_A, ITEM_B], horizon=None)
        rid = f"c52_suplit_{time.strftime('%H%M%S')}"
        proc = _cli(case, rid)
        check(
            "the run finishes with supplied literature in the intent",
            proc.returncode == 0,
            f"exit {proc.returncode}: {proc.stderr.strip()[-300:]}",
        )
        root = run_root(rid, RUNS)
        r0 = rnd(root, 0)
        rows = _ledger(rid)
        sup = (r0 / "supplied_evidence").get()
        check(
            "supplied_evidence is frozen: two items, origin human, ids lit_1/lit_2",
            [it["id"] for it in sup["items"]] == ["lit_1", "lit_2"]
            and all(it["origin"] == "human" for it in sup["items"]),
            json.dumps(sup)[:300],
        )
        cached = [it for it in sup["items"] if it.get("fetch_status") == "cached"]
        check(
            "the staged document (file: url beside the data) is cached for audit",
            sup.get("n_cached") == 1
            and len(cached) == 1
            and (r0 / "evidence_sources").child(cached[0]["cached_file"]).exists(),
            json.dumps([it.get("fetch_status") for it in sup["items"]]),
        )
        check(
            "the item without a url is recorded as no-url, not dropped",
            any(it.get("fetch_status") == "no-url" for it in sup["items"]),
        )
        calls = r0 / "agent_calls"
        prompt = (calls.child("construction") / "prompt").text()
        check(
            "the construction prompt carries retrieved_evidence with origin human and lit_1",
            "## retrieved_evidence" in prompt
            and '"origin": "human"' in prompt
            and '"id": "lit_1"' in prompt
            # json.dumps escapes the em-dash in ITEM_A's source as \u2014, so the
            # ASCII title is the string to look for
            and ITEM_A["title"] in prompt and ITEM_B["supports"] in prompt,
        )
        check(
            "the prompt says what origin means",
            "## evidence_instruction" in prompt and "`human`" in prompt,
        )
        # the items stay out of `intent`, which reaches other roles too; the
        # run-level snapshot holds them
        intent_rec = (root / "intent").get()
        frozen = (root / "supplied_literature").get()
        check(
            "`intent` is written WITHOUT the items; the run-level snapshot holds them",
            "supplied_literature" not in intent_rec
            and len(frozen["items"]) == 2
            and frozen["reaches"]
            == [
                "construction",
                "knowledge",
                "observation",
                "revision",
            ],
        )
        # every text about who receives the items is built from the one list
        from octomod.workflow_modules.knowledge import supplied_literature as _sl

        card = " ".join(_sl.card_lines([{"source": "x", "supports": "y"}]))
        intent_src = (
            REPO / "octomod" / "workflow_modules" / "intent" / "engine.py"
        ).read_text()
        check(
            "the intent card and the S0 note name every role the routing grants",
            frozen["reaches"] == _sl.reaches()
            and "construction, knowledge, observation and " "revision" in card
            and "_lit.reaches_text()" in intent_src
            and "only construction and the" not in intent_src,
        )
        prompts = {
            role: text
            for role in calls.children()
            if (text := (calls.child(role) / "prompt").text(None)) is not None
        }
        carriers = sorted(
            role
            for role, text in prompts.items()
            if ITEM_A["title"] in text or ITEM_B["supports"] in text
        )
        # revision is in this round's agent_calls only when the round
        # expanded, so it is expected only then
        expected = ["construction", "observation"] + (
            ["revision"] if any(role.startswith("revision") for role in prompts) else []
        )
        check(
            "EXACTLY the declared roles carry the supplied claims — construction, "
            "observation and revision when it ran (not the "
            "interpreter, not construction_verification, not the data-side roles)",
            carriers == expected,
            f"carried by: {carriers}",
        )
        obs_prompt = prompts.get("observation", "")
        check(
            "the observation-model agent gets them under its own key, with lit ids",
            "## supplied_literature" in obs_prompt and '"id": "lit_1"' in obs_prompt,
        )
        n_prompts = len(prompts)
        check(
            "and there were other prompts to leak into",
            n_prompts >= 5,
            f"{n_prompts} prompts archived",
        )
        art = [
            e
            for e in rows
            if e.get("event") == "artifact"
            and e.get("artifact") == "supplied_literature"
        ]
        check(
            "the snapshot is ledgered as an artifact with its sha at the intent gate",
            len(art) == 1 and art[0].get("sha") and art[0].get("n_items") == 2,
        )
        check(
            "an application case without a horizon is accepted and the row says "
            "the items are NOT year-fenced",
            len(art) == 1
            and art[0].get("year_fenced") is False
            and "NOT year-fenced" in str(art[0].get("note")),
            str(art[0].get("note"))[-160:] if art else "no row",
        )
        sl = [e for e in rows if e.get("event") == "supplied_literature"]
        check(
            "the ledger records what was handed over",
            len(sl) == 1
            and sl[0]["n_items"] == 2
            and sl[0]["n_cached"] == 1
            and ITEM_A["source"][:40] in sl[0]["sources"][0],
            json.dumps(sl)[:300],
        )
        att = [e for e in rows if e.get("event") == "evidence_attribution"]
        check(
            "the ledger records which decisions leaned on which origin",
            len(att) == 1
            and att[0]["n_supplied_items"] == 2
            and att[0]["n_decisions"] > 0
            and "cite the human's supplied literature" in att[0]["note"],
            json.dumps(att)[:300],
        )
        check(
            "no research call was made (research is off for this case)",
            not any(
                e.get("event") == "agent_call" and e.get("role") == "research"
                for e in rows
            ),
        )
        from octomod.reporting.render import decisions_md

        md = decisions_md(r0)
        check(
            "decisions_md lists the items under 'supplied by the human'",
            "supplied by the human" in md and "lit_1" in md and ITEM_B["source"] in md,
        )
        check(
            "decisions_md renders the attribution row (which decisions leaned on what)",
            "Which literature the build leaned on" in md
            and "cite the human's supplied literature (2 item(s))" in md,
        )
        check(
            "the ledger row records the bytes and seconds the cache cost",
            isinstance(sl[0].get("bytes_cached"), int)
            and sl[0]["bytes_cached"] > 0
            and "cache_seconds" in sl[0],
            json.dumps({k: sl[0].get(k) for k in ("bytes_cached", "cache_seconds")}),
        )
        html_dir = reports_dir(root) / "round_0" / "report"
        rep_html = (html_dir / "report.html").read_text()
        check(
            "the round report header says literature was supplied, beside 'research: off'",
            "2 literature item(s) supplied by the human (construction and "
            "observation model)" in rep_html,
        )
        html = (html_dir / "model_report.html").read_text()
        check(
            "model_report.html M5 shows the supplied literature with its origin",
            "Supplied by the human" in html
            and "lit_2" in html
            and "document cached" in html,
        )
        # resume idempotency: a second S1 pass reuses the snapshot rather than
        # re-caching — the note is the evidence
        check(
            "the snapshot names its origin and count",
            (r0 / "supplied_evidence").get()["origin"] == "human",
        )


def test_the_fence_refuses_at_the_intent_gate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _copy_toy(Path(tmp), "toy_phos_lit_blocked", [ITEM_A, ITEM_B])
        (case / "blocklist.txt").write_text("# fixture\nfixture.second\n")
        rid = "c52_suplit_blocked"
        proc = _cli(case, rid)
        out = proc.stdout + proc.stderr
        check(
            "a forbidden supplied source stops the run at the intent gate, naming the item",
            proc.returncode == 1
            and "intent rejected" in out
            and "supplied_literature[1]" in out
            and "fixture.second" in out,
            f"exit {proc.returncode}: {out.strip()[-300:]}",
        )
        rows = _ledger(rid)
        check(
            "nothing was spent: no agent call before the refusal",
            rows and not any(e.get("event") == "agent_call" for e in rows),
        )
        check(
            "the ledger ends with run_end stopped, reason in words",
            rows
            and rows[-1].get("event") == "run_end"
            and rows[-1].get("outcome") == "stopped"
            and "forbidden" in str(rows[-1].get("reason")),
            str(rows[-1])[:200] if rows else "no ledger",
        )


def test_the_horizon_is_required_for_benchmark_cases_only() -> None:
    """A benchmark case (truth/) must declare its horizon; an application need not."""
    with tempfile.TemporaryDirectory() as tmp:
        bench = Path(tmp) / "bench"
        (bench / "truth").mkdir(parents=True)
        p = lit.horizon_problem({}, [ITEM_A], "bench", bench)
        check(
            "pure: a truth/ case without a horizon is refused, naming the case and key",
            p is not None and "'bench'" in p and "max_publication_year" in p,
            str(p)[:120],
        )
        check(
            "pure: an application case (no truth/) without a horizon is accepted",
            lit.horizon_problem({}, [ITEM_A], "app", Path(tmp) / "app") is None,
        )
        check(
            "pure: a declared horizon, or nothing supplied, passes either way",
            lit.horizon_problem(
                {"research": {"max_publication_year": 2026}}, [ITEM_A], "bench", bench
            )
            is None
            and lit.horizon_problem({}, [], "bench", bench) is None,
        )
        case = _copy_toy(
            Path(tmp), "toy_phos_lit_bench_nohorizon", [ITEM_B], horizon=None
        )
        (case / "truth").mkdir()
        (case / "truth" / "STAGED-ON-PURPOSE.txt").write_text("supplied-literature\n")
        proc = _cli(case, "c52_suplit_bench_nohorizon")
        out = proc.stdout + proc.stderr
        check(
            "through the CLI: the benchmark copy is refused at the intent gate",
            proc.returncode == 1
            and "intent rejected" in out
            and "research.max_publication_year" in out,
            f"exit {proc.returncode}: {out.strip()[-300:]}",
        )
        rows = _ledger("c52_suplit_bench_nohorizon")
        check(
            "nothing was spent",
            bool(rows) and not any(e.get("event") == "agent_call" for e in rows),
        )


def test_a_post_horizon_item_is_refused_when_the_case_declares_one() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _copy_toy(Path(tmp), "toy_phos_lit_horizon", [ITEM_A], horizon=2023)
        proc = _cli(case, "c52_suplit_horizon")
        out = proc.stdout + proc.stderr
        check(
            "a 2024 item against a declared 2023 horizon is refused by name",
            proc.returncode == 1 and "after this case's declared horizon 2023" in out,
            f"exit {proc.returncode}: {out.strip()[-300:]}",
        )


def test_a_malformed_item_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _copy_toy(
            Path(tmp), "toy_phos_lit_bad", [{"source": "a paper", "year": 2020}]
        )
        proc = _cli(case, "c52_suplit_malformed")
        out = proc.stdout + proc.stderr
        check(
            "an item without `supports` is refused at the intent gate, by index",
            proc.returncode == 1 and "supplied_literature[0].supports" in out,
            f"exit {proc.returncode}: {out.strip()[-300:]}",
        )


def test_an_undeclared_benchmark_case_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = _copy_toy(Path(tmp), "toy_phos_lit_truth", [ITEM_B])
        (case / "truth").mkdir()
        (case / "truth" / "true_model.md").write_text("fixture\n")
        proc = _cli(case, "c52_suplit_undeclared")
        out = proc.stdout + proc.stderr
        check(
            "truth/ without the declaration is refused at the intent gate",
            proc.returncode == 1 and "supplied-literature" in out and "truth/" in out,
            f"exit {proc.returncode}: {out.strip()[-300:]}",
        )


def main() -> int:
    print("pure functions")
    test_shape_check_names_the_bad_item()
    test_the_fence_refuses_by_name()
    test_a_benchmark_case_must_declare_it()
    test_attribution_counts_origins()
    print("refusals at the intent gate (each stops before any agent call)")
    test_the_fence_refuses_at_the_intent_gate()
    test_the_horizon_is_required_for_benchmark_cases_only()
    test_a_post_horizon_item_is_refused_when_the_case_declares_one()
    test_a_malformed_item_is_refused()
    test_an_undeclared_benchmark_case_is_refused()
    print("a stub run with supplied literature")
    test_a_run_hands_the_items_to_construction()
    if FAILS:
        print(f"\nSUPPLIED LITERATURE FAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print(
        "\nSUPPLIED LITERATURE UNIT OK — the human's papers reach construction as "
        "retrieved_evidence (origin: human), cached, ledgered, fenced and declared"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
