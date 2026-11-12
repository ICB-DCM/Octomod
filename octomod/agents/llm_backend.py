"""The live backend: one headless `claude -p` subprocess per typed hole.

A subprocess, not an SDK client: the provisioned venv takes no new dependencies,
and a saved prompt plus this command line reproduces any call by hand. No session
is carried between calls, so the context is exactly the prompt.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from octomod.agents import AgentCallError, AgentKilled

# How a person may be logged in other than through the CLI's stored login: a
# token, or a cloud provider. These are theirs, not the calling session's.
_LOGIN_VARIABLES = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
)


def _clean_env() -> dict:
    """The environment without the caller's Claude-session variables.

    A pipeline started inside a Claude Code chat would otherwise confuse the child
    CLI (nested-session detection, host-app base URLs); the child uses its own
    login. The variables a login may consist of (`_LOGIN_VARIABLES`) are kept.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if k in _LOGIN_VARIABLES
        or not (k.startswith("CLAUDE") or k == "ANTHROPIC_BASE_URL")
    }


def login_problem() -> str | None:
    """Why the live agents cannot be called, as a sentence; None when they can.

    Asked once before a live run starts, so that a missing or expired login is
    named before anything is written, and not at the first agent call. It asks
    the CLI in the same environment the agent calls get. A check that cannot be
    made (no answer, another way of authenticating) is no refusal.
    """
    if shutil.which("claude") is None:
        return (
            "the `claude` command was not found. Install Claude Code and log in "
            "(`claude auth login`)."
        )
    if any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", *_LOGIN_VARIABLES)):
        return None
    try:
        proc = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=30,
            env=_clean_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return (
            "Claude Code is not logged in in this terminal, or the login has "
            "expired. Run `claude auth login`, then start the run again."
        )
    return None


# Recorded in the ledger when the CLI reports them (cost/latency accounting).
# `duration_api_ms` is the CLI's own split of `duration_ms`: time inside the
# model API (thinking, generating) against the rest (its tools, its own
# work); the time account records both beside the call's wall.
# `modelUsage` is the per-model breakdown `agents.resolved_model` reads the
# resolved model id from.
_META_FIELDS = (
    "model",
    "duration_ms",
    "duration_api_ms",
    "num_turns",
    "total_cost_usd",
    "usage",
    "modelUsage",
)


def _excerpt(text: str, limit: int = 200) -> str:
    """Whitespace-collapsed head of a reply, for error messages."""
    flat = " ".join(text.split())
    return flat[:limit] + ("..." if len(flat) > limit else "")


def _isolated_cwd() -> str:
    """A fresh temporary directory with no repository and no CLAUDE.md above it.

    Claude Code loads context from the ancestors of its cwd and derives its memory
    path from it, so the call runs from a random `tmp` path that names neither the
    run, the case nor the project. Raises AgentCallError if an ancestor holds
    CLAUDE.md, .claude or .git.
    """
    import tempfile

    path = Path(tempfile.mkdtemp())
    for parent in [path, *path.parents]:
        for marker in ("CLAUDE.md", ".claude", ".git"):
            if (parent / marker).exists():
                raise AgentCallError(
                    f"refusing to call an agent from {path}: {parent / marker} "
                    f"is in its ancestor chain and would be loaded as "
                    f"undeclared context"
                )
    return str(path)


def argv(
    model: str, allowed_tools: tuple[str, ...] = (), effort: str | None = None
) -> list[str]:
    """The exact CLI argv of every agent call; the live probes import it from here.

    The prompt is not in the argv (it goes on stdin). `--tools` is an allowlist
    (a denylist cannot name a tool added later): "" for offline roles, the role's
    own set for the online one. `--strict-mcp-config` with no `--mcp-config` keeps
    every user-wide MCP server out. `effort` None leaves the CLI's default.
    """
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--strict-mcp-config",
    ]
    if effort:
        cmd += ["--effort", str(effort)]
    if allowed_tools:
        # `--tools` chooses the set, `--allowedTools` grants the permission:
        # headless `-p` denies a selected tool that is not pre-allowed. One
        # comma-joined value, because the flag is variadic.
        cmd += ["--allowedTools", ",".join(allowed_tools)]
    # last on purpose: `--tools` is variadic, and nothing may follow it
    cmd += ["--tools", ",".join(allowed_tools)]
    return cmd


def run_llm(
    prompt: str,
    model: str,
    timeout_s: int,
    allowed_tools: tuple[str, ...] = (),
    effort: str | None = None,
) -> tuple[str, dict]:
    """Run one agent call; return (reply_text, meta).

    Raises AgentCallError when no reply was obtained and AgentKilled when the CLI
    was killed by a signal; either carries the partial output as `partial_stdout`
    and `partial_stderr` where there was one.
    """
    # The prompt goes on stdin: `--tools` is variadic and would swallow a
    # trailing positional prompt as a tool name.
    cmd = argv(model, allowed_tools, effort)
    call_cwd = _isolated_cwd()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            # no limit when unset: a run may be measuring how long the model needs
            timeout=timeout_s if timeout_s else None,
            env=_clean_env(),
            # an isolated temporary directory, never anything of the run's:
            # the prompt and the reply are archived in the run record
            cwd=call_cwd,
        )
    except subprocess.TimeoutExpired as e:
        # TimeoutExpired carries the output captured before the kill; it is kept
        # so a timed-out call shows how far the agent got.
        def _txt(raw) -> str:
            if raw is None:
                return ""
            return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw

        err = AgentCallError(
            f"`claude -p` timed out after {timeout_s}s (model {model})"
        )
        err.partial_stdout = _txt(e.stdout)
        err.partial_stderr = _txt(e.stderr)
        raise err from e
    except FileNotFoundError as e:
        raise AgentCallError(
            "`claude` CLI not found on PATH; the 'llm' backend requires it"
        ) from e
    finally:
        shutil.rmtree(call_cwd, ignore_errors=True)
    killed_by = (
        -proc.returncode
        if proc.returncode < 0
        else (
            proc.returncode - 128
            if proc.returncode in (128 + 2, 128 + 9, 128 + 15)
            else None
        )
    )
    if killed_by:
        import signal as _signal

        try:
            name = _signal.Signals(killed_by).name
        except ValueError:
            name = f"signal {killed_by}"
        err = AgentKilled(
            f"`claude -p` was killed by {name} (model {model}) — stopped by a "
            f"person or the machine, not a bad reply; not retried"
        )
        err.partial_stdout = proc.stdout or ""
        err.partial_stderr = proc.stderr or ""
        raise err
    if proc.returncode != 0:
        # the CLI's reason usually rides the stdout envelope, not stderr
        reason = proc.stderr.strip()[-300:]
        try:
            env = json.loads(proc.stdout)
            reason = (
                f"{env.get('subtype', 'error')}: "
                f"{_excerpt(str(env.get('result', '')))}"
            ) or reason
        except Exception:
            if proc.stdout.strip():
                reason = (reason + " | stdout: " + _excerpt(proc.stdout.strip())).strip(
                    " |"
                )
        raise AgentCallError(
            f"`claude -p` exited {proc.returncode} (model {model}): "
            f"{reason or '(no output — likely a transient API/network failure)'}"
        )
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # Not the JSON envelope (older CLI, or a plain-text error page):
        # treat stdout as the reply and let extract_json judge it.
        return proc.stdout, {}
    if not isinstance(envelope, dict):
        return proc.stdout, {}
    meta = {k: envelope[k] for k in _META_FIELDS if k in envelope}
    # the isolation is recorded because it is invisible in the artifacts otherwise
    meta["call_cwd_policy"] = "isolated-tempdir"
    meta["mcp_policy"] = "strict-no-config"
    meta["effort"] = effort
    meta["tools"] = ",".join(allowed_tools)
    if envelope.get("is_error"):
        # The CLI can exit 0 and still have failed (max turns, execution error);
        # 'result' is then its error text, which no amount of re-asking fixes.
        raise AgentCallError(
            f"`claude -p` reported {envelope.get('subtype', 'an error')} "
            f"(model {model}): {_excerpt(str(envelope.get('result', '')))}"
        )
    reply = envelope.get("result")
    return (reply if isinstance(reply, str) else proc.stdout), meta


def extract_json(text: str) -> dict:
    """Parse the first balanced JSON object in a reply.

    Models wrap JSON in prose or fences, so the object is brace-matched; the scan
    is string- and escape-aware, so a brace inside a string does not close it.
    Raises AgentCallError when there is no object or it does not parse.
    """
    start = text.find("{")
    if start < 0:
        raise AgentCallError(f"reply contains no JSON object: {_excerpt(text)}")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    raise AgentCallError(
                        f"reply is not valid JSON ({e}): {_excerpt(candidate)}"
                    ) from e
    raise AgentCallError(
        f"reply has an unterminated JSON object (likely truncated): "
        f"{_excerpt(text[start:])}"
    )
