"""A subagent must not stand inside the repository (token-free).

Claude Code walks the ancestors of its cwd, so a call made from inside the
repository would load its CLAUDE.md as context no prompt records.

  1. the CLI's cwd has no `CLAUDE.md`, `.claude/` or `.git` in its ancestor chain;
  2. the cwd carries neither the run id nor the testcase name;
  3. it is outside the repository, so never where the prompt and the reply are
     archived (the record's `rounds/round_k/agent_calls/<role>`);
  4. it is removed afterwards, whether the call succeeds or fails;
  5. an offline role holds no tool at all: `--tools ""`, an allowlist;
  6. the cwd policy and effort land on the `agent_call` row and the run page;
  7. every argv: `--strict-mcp-config`, one `--tools`, the declared `--effort`;
  8. the temp path names nothing: not the run, the case or the project.

    uv run python tests/call_cwd_unit.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.agents import llm_backend as lb  # noqa: E402
from tests._record import record_at, rnd  # noqa: E402

MARKERS = ("CLAUDE.md", ".claude", ".git")


class _Proc:
    returncode = 0
    stdout = '{"result": "{\\"ok\\": 1}", "model": "m"}'
    stderr = ""


def _capture(
    monkey_raises: Exception | None = None,
    allowed_tools: tuple[str, ...] = (),
    effort: str | None = None,
):
    """Run one real call with subprocess.run faked; return what it was handed."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cwd"] = kw.get("cwd")
        seen["cmd"] = list(cmd)
        seen["stdin"] = kw.get("input")
        seen["existed"] = Path(kw["cwd"]).is_dir()
        if monkey_raises:
            raise monkey_raises
        return _Proc()

    real = subprocess.run
    subprocess.run = fake_run
    try:
        lb.run_llm(
            "prompt",
            "haiku",
            10,
            allowed_tools=allowed_tools,
            effort=effort,
        )
    except Exception:
        pass
    finally:
        subprocess.run = real
    return seen


def test_no_context_marker_stands_above_the_cwd():
    seen = _capture()
    cwd = Path(seen["cwd"])
    assert seen["existed"], "the cwd did not exist when the CLI was launched"
    bad = [
        str(parent / m)
        for parent in [cwd, *cwd.parents]
        for m in MARKERS
        if (parent / m).exists()
    ]
    assert not bad, f"undeclared context in the ancestor chain: {bad[:3]}"
    print(f"  isolated      no {'/'.join(MARKERS)} above {cwd.name}")


def test_the_cwd_is_not_the_io_dir():
    # the call's archive is the run record, under runs/ inside the
    # repository: a cwd outside the repository is never where it lives
    seen = _capture()
    assert str(REPO) not in str(seen["cwd"]), "the cwd is inside the repository"
    print("  not io_dir    the record keeps the archive; the CLI stands elsewhere")


def test_the_path_names_nothing_about_the_run():
    seen = _capture()
    low = str(seen["cwd"]).lower()
    for leak in ("live_blind", "ctd", "abcd", "toy_", "blind", "testcase"):
        assert leak not in low, f"the cwd path carries {leak!r}: {seen['cwd']}"
    # Claude Code derives its memory path from the cwd, so the prefix must not
    # name the project either
    for leak in ("pypesto", "pesto", "prototype", "agent_call"):
        assert (
            leak not in low
        ), f"the cwd path carries the project's name: {seen['cwd']}"
    print(
        "  anonymous     the path names neither the run, the testcase nor the project"
    )


def test_it_is_cleaned_up_even_when_the_call_fails():
    ok = _capture()
    assert not Path(ok["cwd"]).exists(), "the temp cwd outlived a successful call"
    bad = _capture(monkey_raises=FileNotFoundError("no claude"))
    assert not Path(bad["cwd"]).exists(), "the temp cwd outlived a FAILED call"
    print("  cleaned up    removed on success and on failure")


def test_an_offline_role_holds_no_tool_at_all():
    """`--tools ""` on the real argv switches off every built-in tool, `Skill` too."""
    cmd = _capture()["cmd"]
    assert "--tools" in cmd, f"no --tools on the argv: {cmd}"
    assert cmd[cmd.index("--tools") + 1] == "", f"an offline role holds tools: {cmd}"
    assert cmd[-2:] == ["--tools", ""], f"--tools must be last (it is variadic): {cmd}"
    for flag in (
        "--disallowedTools",
        "--allowedTools",
        "--disallowed-tools",
        "--allowed-tools",
    ):
        assert flag not in cmd, f"a second tool mechanism is on the argv: {flag}"
    print('  no tools      --tools "" for an offline role; no denylist, no second list')


def test_the_policies_reach_the_ledger_row_and_the_run_page():
    """A real call's `agent_call` row carries both policies; the run page shows them."""
    import json
    import tempfile

    from octomod.agents import call_agent
    from octomod.orchestration.ledger import Ledger
    from octomod.reporting import round_report as rr
    from octomod.spec import WorkflowSpec

    class _Proc:
        returncode = 0
        stdout = json.dumps(
            {
                "result": json.dumps({"conditions": []}),
                "model": "m",
                "total_cost_usd": 0.01,
                "usage": {"input_tokens": 1},
            }
        )
        stderr = ""

    real = subprocess.run
    subprocess.run = lambda cmd, **kw: _Proc()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = record_at(Path(tmp) / "run")  # one record file
            ledger = Ledger(root)
            spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
            call_agent(
                "condition",
                {"experiment_description": "x", "condition_labels": []},
                spec=spec,
                backend="llm",
                calls=rnd(root, 0) / "agent_calls",
                ledger=ledger,
                module="assembly",
            )
            rows = [e for e in ledger.entries() if e["event"] == "agent_call"]
            assert rows, "no agent_call row was written"
            assert rows[0].get("call_cwd_policy") == "isolated-tempdir", rows[0]
            assert rows[0].get("mcp_policy") == "strict-no-config", rows[0]
            declared = spec.effort_for_role("condition")
            assert rows[0].get("effort") == declared, (rows[0].get("effort"), declared)
            (root / "run").put({"backend": "llm"})
            (root / "intent").put({"question": "q"})
            html = rr._s1_header(rr.Round(rnd(root, 0)))
            assert (
                "agent isolation" in html
                and "isolated-tempdir" in html
                and "strict-no-config" in html
            ), html[:400]
            assert f"(effort {declared})" in html, html[:600]
            print(
                "  recorded      agent_call row carries both policies and the effort; "
                "the run page shows them beside the model"
            )
    finally:
        subprocess.run = real
    stub_rows = [{"backend": "stub", "call_cwd_policy": None, "mcp_policy": None}]
    assert "stub backend" in rr.isolation_line(stub_rows)
    assert "not recorded" in rr.isolation_line([{"backend": "llm"}])
    assert rr.models_with_effort([{"backend": "llm", "model": "opus"}]) == [
        "opus (effort not recorded)"
    ]
    assert rr.models_with_effort([{"backend": "stub", "model": "stub"}]) == ["stub"]
    print(
        "  honest        a stub run and a run from before cwd was recorded each "
        "read as what they are"
    )


def test_the_allowlist_is_the_one_tool_mechanism_and_no_mcp_server_reaches_any_role():
    """The real argv, offline and research: no MCP server, one tool set, stdin."""
    offline = _capture(effort="xhigh")["cmd"]
    online = _capture(allowed_tools=("WebSearch", "WebFetch"), effort="xhigh")["cmd"]
    for label, cmd in (("offline", offline), ("research", online)):
        assert "--strict-mcp-config" in cmd, f"{label}: no --strict-mcp-config"
        assert "--mcp-config" not in cmd, f"{label}: an --mcp-config IS passed"
        assert (
            cmd[:2] == ["claude", "-p"] and "prompt" not in cmd
        ), f"{label}: the prompt must travel on stdin, never as an argument"
        assert cmd.count("--tools") == 1, f"{label}: {cmd}"
        assert "--disallowedTools" not in cmd, f"{label}: the denylist is back"
        assert cmd[cmd.index("--effort") + 1] == "xhigh", f"{label}: {cmd}"
    assert offline[offline.index("--tools") + 1] == "", offline
    assert (
        "--allowedTools" not in offline
    ), f"offline: a permission grant for no tool: {offline}"
    assert online[online.index("--tools") + 1] == "WebSearch,WebFetch", online
    # `--tools` selects, `--allowedTools` pre-approves: headless has no human to
    # approve a call, so without the grant WebSearch is denied at the call
    assert online.count("--allowedTools") == 1, online
    assert online[online.index("--allowedTools") + 1] == "WebSearch,WebFetch", online
    assert online.index("--allowedTools") < online.index("--tools"), (
        "--tools must stay last (variadic)",
        online,
    )
    # the probes import THIS function; it must be what the call actually runs
    assert offline == lb.argv("haiku", effort="xhigh") and online == lb.argv(
        "haiku", ("WebSearch", "WebFetch"), "xhigh"
    ), "argv() and the real call disagree — the probes would test the wrong shape"
    # an undeclared effort is never invented by the engine's shape
    assert "--effort" not in lb.argv("haiku"), lb.argv("haiku")
    print(
        '  one list      --tools "" / WebSearch,WebFetch; --effort declared; '
        "--strict-mcp-config on every call, no --mcp-config ever"
    )


if __name__ == "__main__":
    test_no_context_marker_stands_above_the_cwd()
    test_the_cwd_is_not_the_io_dir()
    test_the_path_names_nothing_about_the_run()
    test_it_is_cleaned_up_even_when_the_call_fails()
    test_an_offline_role_holds_no_tool_at_all()
    test_the_policies_reach_the_ledger_row_and_the_run_page()
    test_the_allowlist_is_the_one_tool_mechanism_and_no_mcp_server_reaches_any_role()
    print(
        "CALL CWD UNIT OK — a subagent stands outside the repository, in a "
        "directory that names nothing, holds no tool it was not granted, and "
        "runs at the effort the workflow declares"
    )
