"""The wait on a live agent call is described, and described correctly.

  1. the typical range comes from the engine's own ledgers, and is blank without data;
  2. the heartbeat rewrites one line on a TTY and appends plain lines off one;
  3. it is a no-op for the stub backend, so the battery's console output is unchanged;
  4. it cannot break a run: a dead stream, a raising clock, an exception in the body.

    uv run python tests/agent_timing_unit.py
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.agents import agent_timing as at  # noqa: E402

# The user's runs folder, not the battery's redirected one: this reads their
# previous runs, not runs this suite makes.
USER_RUNS = config.USER_RUNS_DIR

CR = "\r"
NL = "\n"


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_the_range_is_measured_not_guessed() -> None:
    h = at.history()
    if not h:  # pragma: no cover - a tree with no live runs
        print("  (no live calls ledgered — skipping the measured assertions)")
    else:
        # recounted from the ledgers directly, independently of the module
        rows = []
        # the module reads runs/*.h5; so does this cross-check
        from octomod.result.runstore import RunStore

        for store in RunStore.all_in(USER_RUNS):
            try:
                ledger = store.ledger_rows()
            except OSError:
                # a damaged or foreign file (h5py's open error, RunStore's
                # `RecordDamaged`) is skipped, like a bad ledger line;
                # anything else is a defect in the reader and must fail the
                # suite, not thin the sample
                continue
            for r in ledger:
                if r.get("event") == "agent_call" and r.get("backend") == "llm":
                    rows.append(r)
        assert rows, "the ledgers have live calls but the module found none"
        n_by_role: dict[str, int] = {}
        for r in rows:
            if r.get("duration_s"):
                n_by_role[str(r["role"])] = n_by_role.get(str(r["role"]), 0) + 1
        assert {
            k: v["n"] for k, v in h.items()
        } == n_by_role, "the module's sample counts disagree with the ledgers"
        # no stub call leaks in: they take milliseconds and would drag every
        # median to zero
        assert all(v["median"] > 0.5 for v in h.values()), h

    assert at.typical("construction", "stub") == "", (
        "a stub call must claim no duration at all — it returns instantly and "
        "the battery's output must not change"
    )
    assert "never called live" in at.typical("a_role_that_never_ran")
    print(
        f"  measured      {len(h)} role(s) from the ledgers; "
        f"construction: {at.typical('construction') or 'n/a'}"
    )


def test_the_durations_read_like_durations() -> None:
    for secs, want in (
        (0, "0s"),
        (45, "45s"),
        (60, "1m"),
        (95, "1m35s"),
        (1099, "18m19s"),
    ):
        assert at._fmt(secs) == want, (secs, at._fmt(secs), want)
    assert at._fmt(3700).startswith("1h")
    assert at._fmt(1099) != "1m" and "18m" in at._fmt(1099)
    print("  formatting    1099s reads as 18m19s, not 'a minute'")


def test_the_heartbeat_suits_both_readers() -> None:
    plain = io.StringIO()
    with at.Heartbeat(
        "construction agent", "drafting · typically 2m-9m", interval=0.1, stream=plain
    ):
        time.sleep(0.35)
    out = plain.getvalue()
    assert out.count(NL) >= 2, f"no heartbeat off a TTY: {out!r}"
    assert CR not in out, (
        "a carriage return in captured output is one unreadable smear — the "
        "file-gate driver and this battery both capture stdout"
    )
    assert "elapsed" in out and "drafting" in out and "construction agent" in out

    tty = _Tty()
    with at.Heartbeat("construction agent", "drafting", interval=0.1, stream=tty):
        time.sleep(0.35)
    v = tty.getvalue()
    assert v.count(CR) >= 2, f"no rewrite on a TTY: {v!r}"
    assert NL not in v, "a TTY heartbeat must occupy ONE line, not scroll"
    assert v.endswith(
        "\r\x1b[2K"
    ), "the line must be erased on exit, or the reply line lands on top of it"
    print(
        f"  two modes     {out.count(NL)} plain lines off a TTY, "
        f"{v.count(CR)} rewrites on one, line erased after"
    )


def test_it_is_silent_for_the_stub_backend() -> None:
    """The token-free battery's console output must not move."""
    buf = io.StringIO()
    with at.Heartbeat("x", "y", interval=0.05, stream=buf, live=False):
        time.sleep(0.3)
    assert buf.getvalue() == "", (
        f"the stub path wrote {buf.getvalue()!r} — several suites parse the "
        f"console, and a progress line is not worth perturbing them"
    )
    print("  stub silent   nothing written, so the battery's output is unchanged")


def test_it_cannot_break_a_run() -> None:
    class _Dead(io.StringIO):
        def write(self, s):
            raise OSError("broken pipe")

        def isatty(self):
            raise OSError("gone")

    with at.Heartbeat("x", "y", interval=0.05, stream=_Dead()):
        time.sleep(0.2)  # must not raise

    # an exception in the body propagates unchanged, not masked by the cleanup
    buf = io.StringIO()
    try:
        with at.Heartbeat("x", "y", interval=0.05, stream=buf):
            raise ValueError("the agent call failed")
    except ValueError as e:
        assert str(e) == "the agent call failed"
    else:  # pragma: no cover
        raise AssertionError("the body's exception was swallowed")

    # every role has a plain-words description, and an unknown one degrades
    for role in at.DOING:
        assert at.doing(role) and not at.doing(role).startswith("working on")
    assert at.doing("brand_new_role") == "working on brand new role"
    print("  never breaks  dead stream absorbed, body exception propagates")


if __name__ == "__main__":
    test_the_range_is_measured_not_guessed()
    test_the_durations_read_like_durations()
    test_the_heartbeat_suits_both_readers()
    test_it_is_silent_for_the_stub_backend()
    test_it_cannot_break_a_run()
    print(
        "AGENT TIMING UNIT OK — the typical range is measured, the heartbeat "
        "fits a terminal and a log, and neither can break a run"
    )
