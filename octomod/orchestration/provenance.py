"""Which code and numerics stack produced a run's numbers.

Collects the git commit (plus a digest of `git diff HEAD` for a dirty tree), the
versions of the packages that move fitted numbers, the `uv.lock` digest, the
machine the numbers were measured on and the agents the run was set up with
(backend, the declared model and effort per role, the CLI's version), for the
run record's `run` group, the `run_start` ledger row and the reports; and,
from the ledger, which models the agent calls actually ran on (`models_used`). Never raises: a field that
cannot be determined records why, so "git not available" and "clean tree"
never look alike.
"""

from __future__ import annotations

import functools
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The packages whose version can move a fitted number; the lockfile digest
# covers the rest of the environment.
PACKAGES = (
    "pypesto",
    "amici",
    "petab",
    "petab_select",
    "numpy",
    "scipy",
)


def _git(*args: str) -> str | None:
    """A READ-ONLY git command, or None if it cannot be answered."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def git_state() -> dict:
    """The commit, whether the tree is dirty, and what the difference is.

    `dirty` is None — not False — when it could not be determined, because
    "clean" is a claim and "unknown" is not.
    """
    head = _git("rev-parse", "HEAD")
    if head is None:
        return {
            "commit": None,
            "dirty": None,
            "why": "git not available, or this tree is not a repository",
        }
    status = _git("status", "--porcelain")
    if status is None:
        return {"commit": head, "dirty": None, "why": "git status failed"}
    dirty = bool(status.strip())
    out: dict = {
        "commit": head,
        "commit_short": head[:7],
        "dirty": dirty,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "committed_at": _git("show", "-s", "--format=%cI", "HEAD"),
    }
    if dirty:
        # only a digest and the shape of the diff, which can be large and
        # contain anything: enough to tell two dirty runs of one commit apart
        diff = _git("diff", "HEAD")
        out["diff_sha256"] = (
            hashlib.sha256(diff.encode()).hexdigest()[:16] if diff is not None else None
        )
        out["files_changed"] = len(
            [line for line in status.splitlines() if line.strip()]
        )
        out["untracked"] = len(
            [line for line in status.splitlines() if line.startswith("??")]
        )
    return out


def package_versions() -> dict:
    """{name: version or a reason it is missing} for the numerics stack."""
    from importlib import metadata

    out: dict[str, str] = {"python": sys.version.split()[0]}
    for name in PACKAGES:
        try:
            out[name] = metadata.version(name.replace("_", "-"))
        except Exception:
            # a pinned-but-unimported package still has metadata, so a failure
            # here means genuinely absent rather than merely not loaded
            try:
                mod = __import__(name)
                out[name] = str(getattr(mod, "__version__", "installed, no version"))
            except Exception:
                out[name] = "not installed"
    return out


def lockfile() -> dict:
    """The `uv.lock` digest, so the whole resolved environment has an id."""
    lock = REPO / "uv.lock"
    if not lock.exists():
        return {"uv_lock_sha256": None, "why": "uv.lock not present"}
    data = lock.read_bytes()
    return {
        "uv_lock_sha256": hashlib.sha256(data).hexdigest()[:16],
        "uv_lock_bytes": len(data),
    }


@functools.cache
def cli_version(command: str = "claude") -> str:
    """`<command> --version`, or why it could not be read. Asked once per
    process (a run start and its resumes in one process share it), and given
    5 s: a CLI that does not answer by then is recorded as such, not waited on."""
    try:
        out = subprocess.run(
            [command, "--version"], capture_output=True, text=True, timeout=5
        )
    except FileNotFoundError:
        return f"{command} not found"
    except Exception as e:  # noqa: BLE001 — a version is a fact, never a failure
        return f"{command} --version failed: {type(e).__name__}"
    text = (out.stdout or out.stderr).strip()
    return text.splitlines()[0] if text else f"{command} --version printed nothing"


def agent_setup(spec, backend: str) -> dict:
    """What the agents were set up with, as declared: the backend, the model
    and effort each role is configured for (the spec's `models` and
    `agents.effort`, default and per-role keys), and for live agents the CLI
    that runs them and its version. What the calls RAN on is `models_used`."""

    def block(key: str) -> dict:
        value = spec.get(key, None)
        return dict(value) if isinstance(value, dict) else {}

    out: dict = {
        "backend": backend,
        "models": block("models"),
        "effort": block("agents.effort"),
    }
    if backend == "llm":
        out["cli"] = {"command": "claude", "version": cli_version("claude")}
    return out


def models_used(rows: list[dict]) -> dict:
    """Which models the agent calls ran on, from the ledger's `agent_call`
    rows: per model the roles, calls, tokens and cost; per role its model
    (as asked and as resolved) and effort."""
    by_model: dict[str, dict] = {}
    by_role: dict[str, dict] = {}
    for r in rows:
        if r.get("event") != "agent_call":
            continue
        role = str(r.get("role") or "?")
        resolved = r.get("model_resolved") or r.get("model")
        used = r.get("models_used") or ({resolved: {}} if resolved else {})
        for name, u in used.items():
            m = by_model.setdefault(
                str(name),
                {
                    "roles": [],
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                },
            )
            if role not in m["roles"]:
                m["roles"].append(role)
            m["calls"] += 1
            for k in ("input_tokens", "output_tokens"):
                m[k] += int((u or {}).get(k) or 0)
            m["cost_usd"] = round(
                m["cost_usd"] + float((u or {}).get("cost_usd") or 0), 6
            )
        rr = by_role.setdefault(
            role, {"calls": 0, "models": [], "asked": [], "effort": []}
        )
        rr["calls"] += 1
        for k, v in (
            ("models", resolved),
            ("asked", r.get("model")),
            ("effort", r.get("effort")),
        ):
            if v and v not in rr[k]:
                rr[k].append(v)
    return {"by_model": by_model, "by_role": by_role}


def write_models_used(root) -> None:
    """The record's `models_used` group, from its ledger (pauses, run end)."""
    rows = root.store.ledger_rows()
    if any(r.get("event") == "agent_call" for r in rows):
        (root / "models_used").put(models_used(rows))


def collect() -> dict:
    """Everything, for the record's `run` group and the `run_start` ledger row."""
    from octomod.orchestration.timing import machine

    # what hardware the numbers were measured on (a wall time from
    # another machine is not comparable; a CPU time per unit of work is)
    return {
        "git": git_state(),
        "versions": package_versions(),
        "machine": machine(),
        **lockfile(),
    }


def one_line(prov: dict | None) -> str:
    """The code identity in one sentence, for a report or a console banner.

    Uncommitted changes are stated in words, not as a flag a reader can miss.
    """
    g = (prov or {}).get("git") or {}
    commit = g.get("commit_short") or (g.get("commit") or "")[:7]
    if not commit:
        return f"code: commit UNKNOWN — {g.get('why', 'not recorded')}"
    if g.get("dirty") is None:
        return f"code: commit {commit}, dirtiness UNKNOWN ({g.get('why', '?')})"
    if not g["dirty"]:
        return f"code: commit {commit}, clean tree"
    n = g.get("files_changed")
    return (
        f"code: commit {commit} plus UNCOMMITTED CHANGES"
        + (f" in {n} file(s)" if n else "")
        + (f", diff {g['diff_sha256']}" if g.get("diff_sha256") else "")
        + " — this run is NOT reproducible from the commit alone"
    )


def agents_line(prov: dict | None, used: dict | None) -> str:
    """The agents in one sentence: the models the calls ran on (with calls,
    tokens and cost), else the backend and models declared; the CLI version."""
    setup = (prov or {}).get("agents") or {}
    by_model = (used or {}).get("by_model") or {}
    if by_model:
        parts = [
            f"{m} ({u['calls']} call(s), {u['input_tokens']:,} in / "
            f"{u['output_tokens']:,} out tokens, ${u['cost_usd']:.2f})"
            for m, u in sorted(by_model.items())
        ]
        text = "agents ran on " + "; ".join(parts)
    elif setup:
        models = setup.get("models") or {}
        text = (
            f"agents: backend {setup.get('backend')}, models "
            f"{models.get('override_all') or models.get('default') or '?'} (declared)"
        )
    else:
        return "agents: not recorded (a record from before the agent setup was kept)"
    cli = setup.get("cli") or {}
    return text + (f" · CLI {cli['version']}" if cli.get("version") else "")


def versions_line(prov: dict | None) -> str:
    """The numerics stack in one sentence."""
    v = (prov or {}).get("versions") or {}
    if not v:
        return "package versions: not recorded for this run"
    order = ["python", *PACKAGES]
    return "versions: " + " · ".join(
        f"{k} {v[k]}" for k in order if k in v and v[k] != "not installed"
    )
