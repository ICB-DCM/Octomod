"""The MCP isolation probe has the right shape before anyone spends usage on it.

  1. `--dry-run` prints variants A-E (`claude -p`, prompt on stdin), spawning nothing;
  2. the probe imports the engine's `argv`, so its shape cannot drift from a real call;
  3. the stdio server answers `initialize` and lists exactly the `probe_marker` tool;
  4. with no flag the probe refuses (exit 2) rather than spending.

    uv run python tests/mcp_probe_unit.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "tools" / "probe_mcp_isolation.py"
SERVER = REPO / "tools" / "probe_mcp_server.py"
STRICT = "--strict-mcp-config"


def _dry() -> dict:
    proc = subprocess.run(
        [sys.executable, str(PROBE), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_dry_run_prints_the_five_variants_and_spawns_nothing():
    d = _dry()
    v = {x["label"]: x for x in d["variants"]}
    assert sorted(v) == ["A", "B", "C", "D", "E"], sorted(v)
    for label, x in v.items():
        cmd = x["argv"]
        assert cmd[:2] == ["claude", "-p"], f"{label}: {cmd[:2]}"
        assert "--output-format" in cmd and "json" in cmd, label
        assert d["prompt"] not in cmd, f"{label}: the prompt is a positional argument"
        assert (
            "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""
        ), f'{label}: an offline role must hold no tool (--tools ""): {cmd}'
        assert "--disallowedTools" not in cmd, f"{label}: the denylist is back"
    assert STRICT not in v["A"]["argv"] and STRICT in v["B"]["argv"]
    assert "--mcp-config" in v["C"]["argv"] and STRICT not in v["C"]["argv"]
    assert (
        "--mcp-config"
        not in v["A"]["argv"] + v["B"]["argv"] + v["D"]["argv"] + v["E"]["argv"]
    )
    assert (
        v["D"]["env_overrides"].get("CLAUDE_CONFIG_DIR")
        and STRICT not in v["D"]["argv"]
    )
    assert v["E"]["env_overrides"].get("CLAUDE_CONFIG_DIR") and STRICT in v["E"]["argv"]
    assert d["prompt_on"] == "stdin"
    assert "probe" in d["mcp_config"]["mcpServers"]
    print(
        "  dry-run       five variants, A without the flag, B with, C the positive control"
    )


def test_the_probe_imports_the_engine_argv():
    src = PROBE.read_text()
    assert "from octomod.agents.llm_backend import" in src and "argv" in src, (
        "the probe restates the argv instead of importing it — it would test a shape "
        "the engine does not run"
    )
    sys.path.insert(0, str(REPO))
    from octomod.agents.llm_backend import argv

    d = _dry()
    b = next(x for x in d["variants"] if x["label"] == "B")
    assert b["argv"] == argv(
        d["model"], effort=d["effort"]
    ), "variant B is not the engine's argv"
    assert "--effort" in b["argv"], "the probe's argv carries no declared effort"
    print("  engine argv   variant B == llm_backend.argv(model)")


def test_the_server_lists_exactly_the_marker_tool():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    msgs = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "nonsense/method"},
    ]
    out, err = proc.communicate(
        "\n".join(json.dumps(m) for m in msgs) + "\n", timeout=30
    )
    assert proc.returncode == 0, err
    replies = [json.loads(line) for line in out.splitlines() if line.strip()]
    by_id = {r["id"]: r for r in replies}
    assert set(by_id) == {
        1,
        2,
        3,
    }, f"replies for ids {sorted(by_id)} (notification must get none)"
    assert by_id[1]["result"]["serverInfo"]["name"] == "probe"
    tools = [t["name"] for t in by_id[2]["result"]["tools"]]
    assert tools == ["probe_marker"], tools
    assert by_id[3]["error"]["code"] == -32601
    print(
        "  server        initialize ok; tools/list == ['probe_marker']; unknown method -> -32601"
    )


def test_no_flag_means_no_spending():
    proc = subprocess.run(
        [sys.executable, str(PROBE)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO,
    )
    assert proc.returncode == 2 and "dry-run" in proc.stderr, (
        proc.returncode,
        proc.stderr,
    )
    print("  refuses       no flag -> exit 2, nothing spawned")


if __name__ == "__main__":
    test_dry_run_prints_the_five_variants_and_spawns_nothing()
    test_the_probe_imports_the_engine_argv()
    test_the_server_lists_exactly_the_marker_tool()
    test_no_flag_means_no_spending()
    print(
        "MCP PROBE UNIT OK — the probe's five argvs have the right shape, its "
        "server lists the marker, and nothing here spent a token"
    )
