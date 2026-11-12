"""What code produced a number: the commit, its dirtiness, package versions, the lockfile.

  1. it never raises and never blocks a run: no git, no repo, a moved import;
  2. "unknown" and "clean" are different answers, as are "not recorded" and "recorded as absent";
  3. a dirty tree is stated in words, with a diff digest to tell two dirty runs apart;
  4. an old run says "not recorded" rather than borrowing today's state.

    uv run python tests/provenance_unit.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration import provenance as pv  # noqa: E402
from octomod.reporting.analysis_report import render_html, render_md  # noqa: E402
from tests._record import record_at  # noqa: E402

# the user's runs folder, deliberately not redirected by the battery: this
# reads a previous run of theirs, not a run this suite makes
USER_RUNS = config.USER_RUNS_DIR


def test_it_records_this_tree() -> None:
    p = pv.collect()
    git = p["git"]
    if git["commit"] is None:  # pragma: no cover - not a repo
        assert git["why"], "an absent commit must carry a reason"
        print(f"  (not a git repo: {git['why']}) — skipping the git assertions")
    else:
        assert re.fullmatch(r"[0-9a-f]{40}", git["commit"]), git["commit"]
        assert git["commit_short"] == git["commit"][:7]
        assert isinstance(git["dirty"], bool), "dirtiness must be decided, not guessed"
        # cross-checked against git itself, so this asserts the WORLD rather
        # than the module's own opinion of it
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO,
            capture_output=True,
            text=True,
        ).stdout
        assert git["dirty"] is bool(status.strip()), (
            f"the module says dirty={git['dirty']} and git says "
            f"{bool(status.strip())}"
        )
        if git["dirty"]:
            assert git["diff_sha256"], (
                "a dirty run must carry a diff digest, or two dirty runs of "
                "the same commit cannot be told apart"
            )
            assert git["files_changed"] >= 1

    v = p["versions"]
    for name in ("python", "pypesto", "amici", "petab", "numpy", "scipy"):
        assert name in v, f"{name} is not recorded"
        assert v[name] != "not installed", f"{name} reads as absent in this venv"
    assert p["uv_lock_sha256"], "the lockfile digest identifies the whole environment"
    print(
        f"  this tree     {git.get('commit_short') or '—'} "
        f"dirty={git.get('dirty')} · {len(v)} versions · lock "
        f"{str(p['uv_lock_sha256'])[:8]}"
    )


def test_unknown_and_clean_are_different_answers() -> None:
    """The property that makes the record worth reading."""
    clean = {"git": {"commit": "a" * 40, "commit_short": "a" * 7, "dirty": False}}
    dirty = {
        "git": {
            "commit": "b" * 40,
            "commit_short": "b" * 7,
            "dirty": True,
            "diff_sha256": "cafe1234",
            "files_changed": 78,
        }
    }
    unknown = {"git": {"commit": None, "dirty": None, "why": "git not available"}}
    undecided = {"git": {"commit": "c" * 40, "dirty": None, "why": "git status failed"}}

    assert "clean tree" in pv.one_line(clean)
    assert "UNCOMMITTED CHANGES" in pv.one_line(dirty)
    assert "78 file(s)" in pv.one_line(dirty) and "cafe1234" in pv.one_line(dirty)
    assert "NOT reproducible" in pv.one_line(
        dirty
    ), "a dirty run must say what it costs, in words — a flag is missable"
    assert "UNKNOWN" in pv.one_line(unknown) and "git not available" in pv.one_line(
        unknown
    )
    assert "dirtiness UNKNOWN" in pv.one_line(undecided), (
        "a known commit with undetermined dirtiness must not read as clean — "
        "that is the one reading that would be a lie"
    )
    lines = {pv.one_line(x) for x in (clean, dirty, unknown, undecided)}
    assert len(lines) == 4, f"two states read the same: {lines}"

    # and an absent record says so rather than rendering blank
    assert "UNKNOWN" in pv.one_line(None) and "UNKNOWN" in pv.one_line({})
    assert "not recorded" in pv.versions_line(None)
    print("  four states   clean · dirty · no git · undecided all read differently")


def test_it_cannot_break_a_run() -> None:
    """No git, a broken import, a missing lockfile: values, never exceptions."""
    import importlib

    real = pv._git
    try:
        pv._git = lambda *a: None  # type: ignore[assignment]
        out = pv.git_state()
        assert out["commit"] is None and out["dirty"] is None and out["why"]
        assert pv.one_line({"git": out})  # renders, does not raise
    finally:
        pv._git = real  # type: ignore[assignment]

    real_pkgs = pv.PACKAGES
    try:
        pv.PACKAGES = ("definitely_not_a_real_package_xyz",)  # type: ignore
        v = pv.package_versions()
        assert v["definitely_not_a_real_package_xyz"] == "not installed"
        assert "python" in v, "python's version needs no import and must survive"
    finally:
        pv.PACKAGES = real_pkgs  # type: ignore

    importlib.reload(pv)
    assert pv.collect()["versions"]["python"], "reload must leave it working"
    print("  never raises  no git, absent packages, reload — all values")


def _fake_summary(code: dict | None) -> dict:
    return {
        "run": "prov",
        "record": None,
        "question": "does it record the code?",
        "inference_target": "prediction",
        "system": "a test",
        "success_criteria": [],
        "n_rounds": 1,
        "rounds": [
            {"round": 0, "what_changed": "initial", "selected": "round 0 model"}
        ],
        "models_assessed": [],
        "answer": {
            "selected_model": "round 0 model",
            "basis": "single-model calibration",
        },
        "answers_intent": [],
        "still_open": [],
        "gate_policy": {
            "profile": "strict",
            "sha": "0" * 12,
            "source": "workflows/policies/strict.yaml",
            "answers": [],
            "verdict_signed_by": "human",
        },
        "cost": {
            "agent_calls": 1,
            "usd": 0.0,
            "human_decisions": 1,
            "policy_decisions": 0,
            "auto_decisions": 0,
            "contract_retries": 0,
            "module_redrafts": 0,
            "redraft_grants": 0,
            "attempts_per_call": 1.0,
        },
        "declared_constants": {},
        "provenance": {
            "workflow_sha": "d" * 16,
            "note": "the ledger has everything.",
            "cross_round_comparability": {"across_rounds": True, "why": "one round"},
            "search_topology": {},
            "code": code or {},
        },
        "outcome": "accepted",
    }


def test_the_run_document_states_it_both_ways() -> None:
    dirty = {
        "git": {
            "commit": "e" * 40,
            "commit_short": "e" * 7,
            "dirty": True,
            "diff_sha256": "beef5678",
            "files_changed": 3,
        },
        "versions": {"python": "3.13.12", "pypesto": "0.6.0", "numpy": "2.5.2"},
        "uv_lock_sha256": "1234abcd",
    }
    html = render_html(_fake_summary(dirty))
    assert "What code produced this" in html, "the run document must state the code"
    assert "UNCOMMITTED CHANGES" in html and "beef5678" in html
    assert "1234abcd" in html, "the lockfile digest must reach the page"
    assert "pypesto 0.6.0" in html
    # flagged, not merely mentioned — `stated()` is the unmissable device
    assert 'class="against"' in html, (
        "a dirty run must be FLAGGED on the run page; a sentence in a footer "
        "is how a dirty run ships without anyone noticing"
    )
    md = render_md(_fake_summary(dirty))
    assert "## What code produced this" in md and "UNCOMMITTED CHANGES" in md

    clean = {
        "git": {"commit": "f" * 40, "commit_short": "f" * 7, "dirty": False},
        "versions": {"python": "3.13.12"},
    }
    html_clean = render_html(_fake_summary(clean))
    assert "clean tree" in html_clean
    assert 'class="against"' not in html_clean, (
        "a clean run must not be flagged — a device that fires every time "
        "teaches a reader to skip it"
    )

    # AN OLD RUN: recorded nothing, and must say so rather than borrow today's
    old = render_html(_fake_summary(None))
    assert "UNKNOWN" in old and "not recorded" in old
    assert "clean tree" not in old, (
        "a run with no provenance must never read as a clean one — that is "
        "the reading that would make the record worse than useless"
    )
    print("  run document  dirty flagged, clean plain, old run says 'not recorded'")


def test_a_fresh_run_meta_carries_it() -> None:
    """The newest run on disk recorded provenance, checked on its `run` record."""
    # each run is one record file, <runs>/<id>.h5; newest first
    records = sorted(
        USER_RUNS.glob("*.h5"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    found = None
    for path in records:
        try:
            meta = (record_at(path) / "run").get(None)
        except OSError:  # a record another process is writing right now
            continue
        if isinstance(meta, dict) and "provenance" in meta:
            found = (path, meta)
            break
    if found is None:  # pragma: no cover - no run on disk has provenance
        print("  (no run on disk records provenance yet — nothing to check)")
        return
    path, meta = found
    prov = meta["provenance"]
    assert prov.get("git") and "dirty" in prov["git"], prov
    assert prov.get("versions", {}).get("python"), prov
    assert pv.one_line(prov) and "UNKNOWN" not in pv.one_line(prov), (
        f"a run recorded on this machine should know its own commit: "
        f"{pv.one_line(prov)}"
    )
    print(f"  fresh run     {path.stem} recorded " f"{pv.one_line(prov)[:58]}…")


if __name__ == "__main__":
    test_it_records_this_tree()
    test_unknown_and_clean_are_different_answers()
    test_it_cannot_break_a_run()
    test_the_run_document_states_it_both_ways()
    test_a_fresh_run_meta_carries_it()
    print(
        "PROVENANCE UNIT OK — the commit, its dirtiness and the numerics "
        "stack are recorded, stated in words, and never guessed"
    )
