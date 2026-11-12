"""Live, opt-in: does a subagent call actually carry nothing from this repo?

  1. the engine's own isolated cwd is outside the repository (printed with argv);
  2. three questions (instructions, memory, location) return no leak marker.

Not in the battery: it spends subscription usage. It imports the engine's own
`_isolated_cwd`, `_clean_env` and `argv`, so it probes the invocation that runs.

    .venv/bin/python tests/isolation_probe.py            # ~3 haiku calls
    .venv/bin/python tests/isolation_probe.py --keep-cwd # leave the tempdir
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.agents.llm_backend import _clean_env, _isolated_cwd, argv  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402

MODEL = "haiku"

# Each asks the agent to report context it would only have if something leaked;
# none hints at what a leak looks like, so a clean answer cannot echo the question.
QUESTIONS = {
    "claude_md": (
        "Do you have any project instructions, a CLAUDE.md, a system prompt "
        "addition, or any persona description in your context right now? "
        "If yes, quote its first line verbatim. If no, reply exactly: NONE."
    ),
    "memory": (
        "Do you have any user memory, MEMORY.md, or remembered facts from "
        "previous sessions in your context? If yes, quote one verbatim. "
        "If no, reply exactly: NONE."
    ),
    "location": (
        "What can you tell about the project or directory you are running in, "
        "from anything in your context including your working directory path? "
        "List every specific name you can see. If nothing, reply exactly: NONE."
    ),
}

# Strings that must not come back: what the repository's own context carries.
LEAK_MARKERS = (
    "Octomod front end",
    "octomod",
    "CLAUDE.md",
    "ground truth",
    "benchmark",
    "truth/",
    "testcase",
    "score_against_truth",
    "gate",
    "pyPESTO",
)


def ask(question: str, cwd: str) -> tuple[str, list[str]]:
    """One call, with the engine's own argv and the workflow's declared effort."""
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    cmd = argv(MODEL, effort=spec.effort_for_role("construction"))
    proc = subprocess.run(
        cmd,
        input=question,
        cwd=cwd,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"`claude -p` exited {proc.returncode}: {proc.stderr.strip()[-400:]}"
        )
    try:
        env = json.loads(proc.stdout)
        reply = str(env.get("result", ""))
    except json.JSONDecodeError:
        reply = proc.stdout
    return reply.strip(), cmd


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="isolation_probe")
    ap.add_argument(
        "--keep-cwd", action="store_true", help="do not delete the temp cwd"
    )
    args = ap.parse_args(argv)

    cwd = _isolated_cwd()
    print("ISOLATION PROBE — live, token-spending\n")
    print(f"  cwd     {cwd}")
    print(f"  model   {MODEL}")
    print(f"  repo    {REPO}")
    # recorded beside the verdict, so the result states where it was obtained
    inside = str(REPO) in str(Path(cwd).resolve())
    print(f"  cwd inside repo?  {'YES — BUG' if inside else 'no'}\n")

    failures: list[str] = []
    try:
        for name, question in QUESTIONS.items():
            reply, cmd = ask(question, cwd)
            if name == "claude_md":
                print(f"  argv    {' '.join(cmd[:7])} … ({len(cmd) - 7} denied)")
                print(f"  stdin   the prompt ({len(question)} chars)\n")
            one = " ".join(reply.split())
            hits = [m for m in LEAK_MARKERS if m.lower() in reply.lower()]
            verdict = "LEAK" if hits else "clean"
            print(f"  [{verdict:5}] {name}")
            print(f"           reply: {one[:220]}")
            if hits:
                print(f"           markers: {hits}")
                failures.append(f"{name}: {hits}")
            print()
    finally:
        if args.keep_cwd:
            print(f"  kept    {cwd}")
        else:
            shutil.rmtree(cwd, ignore_errors=True)

    if failures:
        print("ISOLATION PROBE FAILED — context reached the subagent:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(
        "ISOLATION PROBE OK — nothing from this repository reached the "
        "subagent, from the engine's own cwd and argv"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
