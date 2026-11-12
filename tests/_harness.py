"""The plumbing the suites share: the check line, the summary, the CLI in-process.

A suite imports what it uses once this directory is on sys.path:

    sys.path.insert(0, str(REPO / "tests"))
    from _harness import FAILS, check, finish  # noqa: E402

The leading underscore keeps it out of the battery: `run_all.py` lists its
suites by name, and this module is imported, never run.
"""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path

FAILS: list[str] = []

# A suite whose fixture is absent exits with this after every other check has
# run: an absent fixture is "cannot run here", not "is broken".
SKIP_EXIT = 77
SKIPPED: list[str] = []


def quick_tier() -> bool:
    """True under the battery's reduced-effort overlay: a suite skips its
    full-effort steps (an AMICI compile) and says so. The battery runs such a
    suite at full effort (`run_all.FULL_EFFORT`), so the steps always run there."""
    from octomod.spec import OVERLAY_ENV

    return Path(os.environ.get(OVERLAY_ENV) or "").name == "quick.yaml"


def check(name: str, ok: bool, detail: str = "") -> None:
    """Print one ✓/✗ line, with the detail when there is one; record a failure."""
    print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(f"{name}: {detail}")


def check_detail_on_fail(name: str, ok: bool, detail: str = "") -> None:
    """`check` for a suite whose details explain failures: a pass prints the name alone."""
    print(
        f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail and not ok else "")
    )
    if not ok:
        FAILS.append(f"{name}: {detail}")


def fixture_or_skip(path: Path, what: str) -> bool:
    """True when `path` exists; otherwise `what` is recorded as skipped and named.

    A machine-local live run exists only where it was made (`runs/` is
    gitignored); `finish` then exits SKIP_EXIT once every other check has run.
    """
    if path.exists():
        return True
    SKIPPED.append(what)
    print(
        f"SKIP: {what} is not on disk — a machine-local live run, and "
        f"runs/ is gitignored, so it exists only where it was made"
    )
    return False


def finish(label: str, ok_line: str) -> int:
    """Print the suite's last lines and return its exit code.

    Any failure: `<label> FAILED — n check(s):` and one bullet each, exit 1.
    Else a skipped fixture: `<label> SKIPPED — …`, exit SKIP_EXIT. Else
    `ok_line`, exit 0. A label that starts with a newline sets the summary off
    by a blank line, as the suite's OK line may.
    """
    if FAILS:
        print(f"{label} FAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  · {f}")
        return 1
    if SKIPPED:
        print(f"{label} SKIPPED — everything else passed; {', '.join(SKIPPED)} absent")
        return SKIP_EXIT
    print(ok_line)
    return 0


def check_records_complete(paths, label: str = "") -> None:
    """A check line per record: nothing the engine's completeness checks
    looked for is missing (`octomod/result/completeness.py`). For a suite
    whose records the battery does not see — removed by the suite, or written
    outside its `test_runs/<suite>` folder."""
    from octomod.result import completeness

    for p in paths:
        found = completeness.gaps(p)
        check(
            f"{label or Path(p).name}: the record holds what each finished step left",
            not found,
            "; ".join(found[:5])
            + (f"; and {len(found) - 5} more" if len(found) > 5 else ""),
        )


def remove_checked(store, label: str = "") -> None:
    """Check the run's record is complete, then remove it (`RunStore.remove`)."""
    if store.path.exists():
        check_records_complete([store.path], label or store.run_id)
    store.remove()


def run_cli_captured(args: list[str]) -> tuple[int, str]:
    """The engine's CLI in this process: its exit code and what it printed."""
    # imported on call, so a suite that never runs the CLI never loads it
    from octomod.cli import main as cli

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli(args)
    return rc, buf.getvalue()


def run_cli(args: list[str]) -> int:
    """The engine's CLI in this process, its console output discarded."""
    return run_cli_captured(args)[0]


class RecordingLedger:
    """A ledger kept in memory: one `{"event": …, **fields}` row per append."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def append(self, event, **kw) -> None:
        self.rows.append({"event": event, **kw})


class CallLedger:
    """A ledger kept in memory: each append's `(args, kwargs)` exactly as passed."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def append(self, *a, **k) -> None:
        self.rows.append((a, k))
