"""Static environment configuration and path resolution.

Environment facts live here (venv, SWIG); run-tunable knobs live in the
workflow spec (workflows/*.yaml). Nothing else may hardcode paths.
"""

from __future__ import annotations

import os
import shutil as _shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# The provisioned environment (never created by the engine), resolved in order:
# OCTOMOD_PYTHON, the uv-managed .venv in the repo, a venv at ../octomod_venv.
_CANDIDATES = [
    (Path(os.environ["OCTOMOD_PYTHON"]) if os.environ.get("OCTOMOD_PYTHON") else None),
    REPO_ROOT / ".venv" / "bin" / "python",
    REPO_ROOT.parent / "octomod_venv" / "bin" / "python",
]
VENV_PYTHON = next(
    (p for p in _CANDIDATES if p and p.exists()), REPO_ROOT / ".venv" / "bin" / "python"
)
# Model modules must be wrapped by the same swig that built the venv's AMICI
# core, or they fail at load time with a misleading AttributeError: prefer the
# venv's own swig, else the one on PATH.
_venv_swig = VENV_PYTHON.parent / "swig"
SWIG_BIN = (
    _venv_swig
    if _venv_swig.exists()
    else Path(_shutil.which("swig") or "/usr/bin/swig")
)

# `runs/` is the user's folder; the test battery sets OCTOMOD_RUNS_DIR to
# write elsewhere. An env var, not a spec key: the output directory is not a
# modelling decision and must not move `workflow_sha`.
USER_RUNS_DIR = REPO_ROOT / "runs"
RUNS_DIR = (
    Path(os.environ["OCTOMOD_RUNS_DIR"]).expanduser()
    if os.environ.get("OCTOMOD_RUNS_DIR")
    else USER_RUNS_DIR
)
if not RUNS_DIR.is_absolute():
    RUNS_DIR = REPO_ROOT / RUNS_DIR
# Run ids are directory names inside RUNS_DIR; a leading underscore is reserved
# for the engine's own folders (`_projects/`, `_amici_cache/`).
RESERVED_RUN_PREFIX = "_"
# Per-project cross-run archive: a run started from its own `input/` has no
# testcase folder for its tried-models log, so the log lives here by project.
PROJECTS_DIR = RUNS_DIR / "_projects"

SKILLS_DIR = REPO_ROOT / "skills"
KNOWLEDGE_DIR = REPO_ROOT / "knowledge" / "packs"
WORKFLOWS_DIR = REPO_ROOT / "workflows"

# Shared AMICI model cache, keyed by SBML content hash, so an unchanged model
# skips the C++ compile. Pinned to the repo root, independent of RUNS_DIR, so the
# test battery reuses it and the runs folder holds only runs.
AMICI_CACHE_DIR = REPO_ROOT / ".amici_cache"


def assert_venv() -> None:
    """The engine must run inside the provisioned venv (AMICI, pyPESTO, ...)."""
    if not VENV_PYTHON.exists():
        raise RuntimeError(
            "No project environment found. Set it up with:\n"
            "  uv sync            (inside the repo; needs https://docs.astral.sh/uv/)\n"
            "then run via ./run.sh or `uv run python -m octomod ...`.\n"
            "(Alternative: create a venv from requirements.txt and set "
            "OCTOMOD_PYTHON to its python.)"
        )
    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        raise RuntimeError(
            f"Run with the project venv python:\n  {VENV_PYTHON} -m octomod ...\n"
            f"(currently: {sys.executable})"
        )
