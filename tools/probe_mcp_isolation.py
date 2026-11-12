"""Probe whether an MCP server declared outside the argv reaches an agent call.

Five calls (A-E) vary `--strict-mcp-config`, `--mcp-config` and a relocated user config,
never the real `~/.claude.json`; each tool list is written to `record/review/`.

    uv run python tools/probe_mcp_isolation.py --dry-run     # the argvs only, spawns nothing
    uv run python tools/probe_mcp_isolation.py --live        # spends usage
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.agents.llm_backend import _clean_env, _isolated_cwd, argv  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402

SERVER = REPO / "tools" / "probe_mcp_server.py"
PROMPT = (
    "List every tool name available to you, one per line, exactly as spelled, "
    "and nothing else. If you have no tools, reply with the single word NONE."
)
STRICT = "--strict-mcp-config"


def mcp_config() -> dict:
    return {
        "mcpServers": {
            "probe": {"command": sys.executable, "args": [str(SERVER)]},
        }
    }


def _effort() -> str:
    """The declared effort for an offline role, which the engine passes on every call."""
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    return spec.effort_for_role("construction")


def variants(model: str, config_path: str, user_config_dir: str) -> list[dict]:
    engine = argv(model, effort=_effort())
    assert STRICT in engine, "the engine argv does not carry the isolation flag"
    without_flag = [a for a in engine if a != STRICT]
    env_d = {"CLAUDE_CONFIG_DIR": user_config_dir}
    return [
        {
            "label": "A",
            "what": "the engine argv minus the isolation flag",
            "argv": without_flag,
            "env_overrides": {},
            "expect": "marker ABSENT today only because ~/.claude.json declares no server",
        },
        {
            "label": "B",
            "what": "the engine's argv as it is",
            "argv": engine,
            "env_overrides": {},
            "expect": "marker absent",
        },
        {
            "label": "C",
            "what": "A plus --mcp-config <probe.json> (positive control)",
            "argv": without_flag + ["--mcp-config", config_path],
            "env_overrides": {},
            "expect": "marker MUST appear (mcp__probe__probe_marker)",
        },
        {
            "label": "D",
            "what": "A with CLAUDE_CONFIG_DIR holding a user config declaring the server",
            "argv": without_flag,
            "env_overrides": env_d,
            "expect": "marker appears => the user-wide gap is demonstrated",
        },
        {
            "label": "E",
            "what": "D plus --strict-mcp-config",
            "argv": engine,
            "env_overrides": env_d,
            "expect": "marker absent => the flag closes the gap",
        },
    ]


def dry_run(model: str) -> dict:
    """Everything the live run would do, as data. Spawns nothing."""
    return {
        "model": model,
        "effort": _effort(),
        "prompt": PROMPT,
        "prompt_on": "stdin",
        "mcp_config": mcp_config(),
        "config_path": "<tmpdir>/probe.json",
        "user_config_dir": "<tmpdir>/claude_config (holds .claude.json with the same mcpServers)",
        "variants": variants(model, "<tmpdir>/probe.json", "<tmpdir>/claude_config"),
        "writes": "record/review/<date>_mcp_probe_tool_lists.md",
    }


def live(model: str) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="mcp_probe_"))
    cfg = tmp / "probe.json"
    cfg.write_text(json.dumps(mcp_config(), indent=2))
    user_dir = tmp / "claude_config"
    user_dir.mkdir()
    (user_dir / ".claude.json").write_text(json.dumps(mcp_config(), indent=2))
    lines = [
        f"# MCP isolation probe — {date.today().isoformat()}",
        "",
        f"model `{model}`; prompt on stdin: `{PROMPT}`",
        "",
    ]
    for v in variants(model, str(cfg), str(user_dir)):
        env = _clean_env()
        env.update(v["env_overrides"])
        cwd = _isolated_cwd()
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                v["argv"],
                input=PROMPT,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
                cwd=cwd,
            )
            out = proc.stdout
            rc = proc.returncode
        except subprocess.TimeoutExpired as e:
            out, rc = f"TIMEOUT after 300 s; partial: {e.stdout!r}", -1
        finally:
            try:
                os.rmdir(cwd)
            except OSError:
                pass
        reply = out
        try:
            env_json = json.loads(out)
            reply = str(env_json.get("result", out))
        except (json.JSONDecodeError, AttributeError):
            pass
        marker = "probe_marker" in reply
        lines += [
            f"## {v['label']} — {v['what']}",
            "",
            f"argv: `{' '.join(v['argv'])}`  ",
            f"env overrides: `{v['env_overrides'] or '{}'}`  ",
            f"expect: {v['expect']}  ",
            f"exit {rc}, {time.perf_counter() - t0:.1f} s, marker present: **{marker}**",
            "",
            "```",
            reply.strip(),
            "```",
            "",
        ]
        print(f"{v['label']}: exit {rc}, marker={marker}")
    out_path = (
        REPO
        / "record"
        / "review"
        / f"{date.today().isoformat()}_mcp_probe_tool_lists.md"
    )
    out_path.write_text("\n".join(lines))
    print(f"wrote {out_path}")
    return 0


def main(args: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print the five argvs; spawn nothing"
    )
    ap.add_argument(
        "--live", action="store_true", help="run the five calls (spends usage)"
    )
    ap.add_argument("--model", default="haiku")
    ns = ap.parse_args(args)
    if ns.dry_run:
        print(json.dumps(dry_run(ns.model), indent=2))
        return 0
    if ns.live:
        return live(ns.model)
    print(
        "refusing to spend usage without --live; use --dry-run to see the shape",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
