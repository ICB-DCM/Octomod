"""The research check at run start, and the live research probe's shape (not run).

  1. research on without the case's own horizon is refused; any blocklist is recorded;
  2. through the CLI, a case without a horizon exits 2 before any agent is called;
  3. a stub run with a comments-only blocklist ledgers `research_fence` and shows it;
  4. `ctd_blind`'s research is OFF (a flipped flag would void the blind case);
  5. `ctd_positional` and `ctd_countonly` pass the check as staged;
  6. `tools/probe_research_live.py --dry-run` prints the engine's argv, spawns nothing.

    uv run python tests/research_fence_unit.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish, remove_checked  # noqa: E402

from octomod import config  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.model.engine import (  # noqa: E402
    research_enabled,
    research_fence,
)
from tests._record import ledger_rows, reports_dir, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")


def _fence(testcase: dict, blocklist_text: str | None):
    """(record, refusal) for a testcase dict and a blocklist file's text (None = no file)."""
    with tempfile.TemporaryDirectory() as tmp:
        bl = Path(tmp) / "blocklist.txt"
        if blocklist_text is not None:
            bl.write_text(blocklist_text)
        try:
            return research_fence(testcase, SPEC, "case_x", bl), None
        except ValueError as e:
            return None, str(e)


def test_the_check_requires_the_year_and_records_the_blocklist() -> None:
    on = {"research": {"enabled": True, "max_publication_year": 2025}}
    rec, m = _fence({"research": {"enabled": True}}, "some-source\n")
    check(
        "an undeclared horizon is refused, naming the case",
        rec is None and m is not None and "case_x" in m and "max_publication_year" in m,
        (m or "PASSED")[:100],
    )
    for label, text in (
        ("a comments-only blocklist", "# only comments\n"),
        ("an empty blocklist file", ""),
        ("an absent blocklist file", None),
    ):
        rec, m = _fence(on, text)
        check(
            f"{label} is ACCEPTED and recorded as no forbidden sources",
            rec is not None
            and rec["forbidden_sources"] == []
            and rec["note"] == "research on, no forbidden sources"
            and rec["horizon"] == 2025,
            m or str(rec),
        )
    rec, _ = _fence(on, "blocked.example\n# a comment\nother.example\n")
    check(
        "entries are listed, comments dropped",
        rec is not None
        and rec["forbidden_sources"] == ["blocked.example", "other.example"]
        and rec["note"] == "research on, 2 forbidden source(s)",
        str(rec),
    )
    rec, m = _fence({"research": {"enabled": False}}, None)
    check("research off: nothing to record", rec is None and m is None)


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
        timeout=600,
        cwd=REPO,
    )


def test_the_cli_refuses_a_case_without_a_horizon_before_anything_runs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "toy_no_horizon"
        shutil.copytree(REPO / "testcase" / "toy_phos_research", case)
        tc = yaml.safe_load((case / "testcase.yaml").read_text())
        del tc["research"]["max_publication_year"]
        (case / "testcase.yaml").write_text(yaml.safe_dump(tc, sort_keys=False))
        rid = "c36_no_horizon_probe"
        proc = _cli(case, rid)
        check(
            "the CLI exits 2 with `refused:` naming the case",
            proc.returncode == 2
            and "refused:" in proc.stderr
            and "toy_no_horizon" in proc.stderr
            and "max_publication_year" in proc.stderr,
            f"exit {proc.returncode}: {proc.stderr.strip()[-160:]}",
        )
        root = run_root(rid, RUNS)
        ran = bool((rnd(root, 0) / "agent_calls").children())
        check("no agent was called before the refusal", not ran)
        remove_checked(root.store)


def test_an_empty_blocklist_runs_and_is_ledgered_and_shown() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp) / "toy_open_research"
        shutil.copytree(REPO / "testcase" / "toy_phos_research", case)
        (case / "blocklist.txt").write_text("# nothing is off-limits for this case\n")
        rid = "c36_open_research"
        proc = _cli(case, rid)
        root = run_root(rid, RUNS)
        rows = ledger_rows(root)
        check("the run starts and completes", proc.returncode == 0, proc.stderr[-200:])
        fence = [e for e in rows if e.get("event") == "research_fence"]
        check(
            "one `research_fence` row at run start",
            len(fence) == 1
            and rows.index(fence[0])
            == rows.index(next(e for e in rows if e.get("event") == "run_start")) + 1,
            str([e.get("event") for e in rows[:3]]),
        )
        row = fence[0] if fence else {}
        check(
            "the row records the horizon and NO forbidden sources",
            row.get("horizon") == 2025
            and row.get("forbidden_sources") == []
            and row.get("note") == "research on, no forbidden sources",
            json.dumps(row)[:160],
        )
        check(
            "the console says so at run start",
            "research: on — horizon 2025; research on, no forbidden sources"
            in proc.stdout,
        )
        page = reports_dir(root) / "round_0" / "report" / "report.html"
        html = page.read_text() if page.exists() else ""
        ok = "on — horizon 2025, no forbidden sources" in html
        check(
            "the run page header reads the row: research on, horizon, no forbidden sources",
            ok,
            "" if ok else ("header row missing" if html else "no report.html"),
        )
        # with no blocklist entries, the horizon is what drops the stub's item
        drops = [
            e
            for e in rows
            if e.get("event") == "note" and "published after" in str(e.get("note", ""))
        ]
        check("the horizon still filters the stub's 2026 item", bool(drops))
        remove_checked(root.store)


def test_ctd_blind_research_stays_off() -> None:
    tc = yaml.safe_load((REPO / "testcase" / "ctd_blind" / "testcase.yaml").read_text())
    check(
        "ctd_blind's testcase.yaml does not enable research",
        not (tc.get("research") or {}).get("enabled"),
        str(tc.get("research")),
    )
    check(
        "and the workflow default is off, so the case is off",
        research_enabled(tc, SPEC) is False,
    )


def test_the_staged_ctd_cases_start_as_staged() -> None:
    for name in ("ctd_positional", "ctd_countonly"):
        d = REPO / "testcase" / name
        tc = yaml.safe_load((d / "testcase.yaml").read_text())
        try:
            rec = research_fence(tc, SPEC, name, d / "blocklist.txt")
            err = None
        except ValueError as e:
            rec, err = None, str(e)
        check(
            f"{name} passes the check as staged: research on, horizon 2026, no forbidden sources",
            rec is not None
            and rec["horizon"] == 2026
            and rec["forbidden_sources"] == []
            and rec["note"] == "research on, no forbidden sources",
            err or str(rec),
        )
    for name in ("ctd_blind", "ctd_petab"):
        d = REPO / "testcase" / name
        if not d.exists():
            continue
        tc = yaml.safe_load((d / "testcase.yaml").read_text())
        rec = research_fence(tc, SPEC, name, d / "blocklist.txt")
        print(f"  ·  {name}: {'research off' if rec is None else rec['note']}")


def test_the_live_probe_has_the_engine_argv_and_spawns_nothing() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "probe_research_live.py"), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO,
    )
    check("--dry-run exits 0", proc.returncode == 0, proc.stderr[-200:])
    plan = json.loads(proc.stdout)
    from octomod.agents import ONLINE_ROLES
    from octomod.agents.llm_backend import argv

    check(
        "the plan's argv is the engine's for the ONLINE role",
        plan["argv"] == argv(plan["model"], ONLINE_ROLES["research"], plan["effort"])
        and plan["effort"] == SPEC.effort_for_role("research"),
    )
    tools = (
        plan["argv"][plan["argv"].index("--tools") + 1]
        if "--tools" in plan["argv"]
        else ""
    )
    check(
        "--tools WebSearch,WebFetch is the online role's set and --allowedTools the same names is its permission, --strict-mcp-config on, prompt on stdin",
        tools == "WebSearch,WebFetch"
        and "--disallowedTools" not in plan["argv"]
        and plan["argv"].count("--allowedTools") == 1
        and plan["argv"][plan["argv"].index("--allowedTools") + 1]
        == "WebSearch,WebFetch"
        and "--strict-mcp-config" in plan["argv"]
        and plan["prompt_on"] == "stdin",
        " ".join(plan["argv"]),
    )
    check(
        "the horizon is stated and the contract keys named",
        plan["horizon"] == 2025
        and set(plan["contract_keys"]) >= {"evidence_items", "queries_run", "notes"},
    )
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "probe_research_live.py")],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO,
    )
    check(
        "no flag: refuses to spend (exit 2)",
        proc.returncode == 2 and "dry-run" in proc.stderr,
    )


def main() -> int:
    test_the_check_requires_the_year_and_records_the_blocklist()
    test_the_cli_refuses_a_case_without_a_horizon_before_anything_runs()
    test_an_empty_blocklist_runs_and_is_ledgered_and_shown()
    test_ctd_blind_research_stays_off()
    test_the_staged_ctd_cases_start_as_staged()
    test_the_live_probe_has_the_engine_argv_and_spawns_nothing()
    return finish(
        "RESEARCH FENCE",
        "RESEARCH FENCE OK — research on needs the case's own horizon; an empty "
        "blocklist is accepted and ledgered; the staged CTD cases start; ctd_blind stays off",
    )


if __name__ == "__main__":
    sys.exit(main())
