"""One live research-agent call with the engine's exact argv, recorded.

Never run by the battery. `--live` spends usage and writes
`record/review/<date>_research_probe.md` (argv, the envelope's tool use, wall time,
items and URL fetches); `--dry-run` prints the plan and spawns nothing.

    uv run python tools/probe_research_live.py --dry-run
    uv run python tools/probe_research_live.py --live [--model haiku]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.agents import ONLINE_ROLES, ROLES, build_prompt  # noqa: E402
from octomod.agents.llm_backend import _clean_env, _isolated_cwd, argv  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402

HORIZON = 2025
CONTEXT = {
    "intent": {
        "question": "Which published models describe ligand-induced receptor phosphorylation with dephosphorylation by a constitutive phosphatase, and what kinetic forms do they use?",
        "system": "a generic receptor phosphorylation module (no specific protein)",
        "inference_target": "parameter_values",
    },
    "experiment_description": "A harmless, generic query used only to test the ONLINE role's plumbing.",
    "restrictions": (
        f"HARD RULES: use only literature published up to {HORIZON} inclusive. NEVER "
        f"consult, cite, or search for these excluded sources: ['probe-blocklist.example']. "
        f"Never fabricate a source; returning fewer or zero items is acceptable."
    ),
}


def plan(model: str) -> dict:
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    prompt = build_prompt("research", CONTEXT, spec)
    effort = spec.effort_for_role("research")
    return {
        "role": "research",
        "model": model,
        "effort": effort,
        "argv": argv(model, ONLINE_ROLES["research"], effort),
        "prompt_on": "stdin",
        "prompt_bytes": len(prompt.encode()),
        "allowed_tools": list(ONLINE_ROLES["research"]),
        "horizon": HORIZON,
        "contract_keys": list(ROLES["research"].required_keys),
        "cwd_policy": "fresh tempdir outside any repository (_isolated_cwd)",
        "writes": "record/review/<date>_research_probe.md",
        "records": [
            "envelope tool uses (or their absence)",
            "wall time",
            "items and URLs",
            "cache_source status per URL",
        ],
    }


def live(model: str) -> int:
    from octomod.connectors.web_cache import cache_source

    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    prompt = build_prompt("research", CONTEXT, spec)
    effort = spec.effort_for_role("research")
    cwd = _isolated_cwd()
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            argv(model, ONLINE_ROLES["research"], effort),
            input=prompt,
            capture_output=True,
            text=True,
            timeout=900,
            env=_clean_env(),
            cwd=cwd,
        )
    finally:
        try:
            os.rmdir(cwd)
        except OSError:
            pass
    wall = time.perf_counter() - t0
    lines = [
        f"# Research probe — {date.today().isoformat()}",
        "",
        f"model `{model}`, {wall:.0f} s, exit {proc.returncode}",
        "",
    ]
    lines += [
        "argv: `" + " ".join(argv(model, ONLINE_ROLES["research"], effort)) + "`",
        f"cwd: {cwd} (removed)",
        "",
    ]
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError:
        env = None
    if env is None:
        lines += [
            "NOT a JSON envelope. stdout:",
            "```",
            proc.stdout[:3000],
            "```",
            "stderr:",
            "```",
            proc.stderr[:2000],
            "```",
        ]
    else:
        tool_keys = [k for k in env if "tool" in k.lower()]
        lines += [
            f"envelope keys: {sorted(env)}",
            f"tool-use record in the envelope: {tool_keys or 'NONE — the envelope does not say whether WebSearch ran'}",
            "",
        ]
        reply = env.get("result", "")
        lines += ["reply:", "```", str(reply)[:6000], "```", ""]
        try:
            parsed = json.loads(reply) if isinstance(reply, str) else reply
            items = parsed.get("evidence_items", [])
            out_dir = REPO / "record" / "review" / "research_probe_sources"
            for it in items:
                rec = cache_source(str(it.get("url", "")), out_dir)
                lines.append(
                    f"- {it.get('year')} · {it.get('source')} · url {it.get('url')} · cache: {rec.get('fetch_status')} {rec.get('bytes', '')}"
                )
        except Exception as e:  # the reply is the finding either way
            lines.append(
                f"reply not parseable as the contract: {type(e).__name__}: {e}"
            )
    out = REPO / "record" / "review" / f"{date.today().isoformat()}_research_probe.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")
    return 0


def main(args: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="print the plan; spawn nothing"
    )
    ap.add_argument(
        "--live", action="store_true", help="make the one call (spends usage)"
    )
    ap.add_argument("--model", default="haiku")
    ns = ap.parse_args(args)
    if ns.dry_run:
        print(json.dumps(plan(ns.model), indent=2))
        return 0
    if ns.live:
        return live(ns.model)
    print(
        "refusing to spend usage without --live; use --dry-run to see the plan",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
