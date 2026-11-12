"""Checkpoint the run record where the process may end.

Every workflow module writes into the record directly, so the record is current by
construction and nothing needs committing. What this module does is the
crash-safety measure — a consistent copy of the file, `<id>.h5.bak`, taken at
every marker and decision (the points a resume replays from) and at the
moments the run stops of its own accord (a gate pause, the end of the run,
the final document write). A copy costs a few milliseconds for a few MB.
`RunStore._open` falls back to that copy for a reader when the main file is
damaged, and restores it over the damaged file for the writer, so a killed
run resumes from its last marker.

`commit_run`/`commit_ctx` are the names the engine calls at those points; a
`why` that is none of them is a no-op. `OCTOMOD_RESULT_COMMIT=off` disables
the checkpoints (a battery that measures timing).

Before each checkpoint the record is audited for completeness
(`completeness.check`): what must be in it by this point is looked for, and
what is missing is written into the record, so the checkpoint carries the
finding. `OCTOMOD_RECORD_CHECKS=off` disables the audit alone.
"""

from __future__ import annotations

import os
from pathlib import Path

from octomod.result.runstore import RecordDamaged

CHECKPOINT_AT = ("gate_pending", "run_end", "final")
CHECKPOINT_PREFIXES = ("marker:", "decision:")


def enabled() -> bool:
    return os.environ.get("OCTOMOD_RESULT_COMMIT", "on").lower() not in (
        "off",
        "0",
        "false",
        "no",
    )


def _store(run):
    return getattr(run, "store", run)


def checks_enabled() -> bool:
    return os.environ.get("OCTOMOD_RECORD_CHECKS", "on").lower() not in (
        "off",
        "0",
        "false",
        "no",
    )


def commit_run(
    run,
    ledger=None,
    *,
    why: str,
    round_idx: int = 0,
    candidate: str | None = None,
    subject: str | None = None,
) -> Path | None:
    """Checkpoint the record when `why` is a stopping point; else nothing.
    `candidate` names the unit a per-candidate marker certifies; `subject` the
    record key a decision was just written to."""
    if why not in CHECKPOINT_AT and not why.startswith(CHECKPOINT_PREFIXES):
        return None
    store = _store(run)
    if why in ("gate_pending", "run_end", "final"):
        # which models the agent calls ran on, summed from the ledger, where
        # the process may end — so the record and its checkpoint carry it
        try:
            from octomod.orchestration import provenance
            from octomod.result import node as tree

            provenance.write_models_used(tree.root(store))
        except RecordDamaged:
            raise
        except Exception:  # noqa: BLE001 — a summary never ends a run
            pass
    if checks_enabled():
        from octomod.orchestration import timing as _timing
        from octomod.result import completeness

        with _timing.span("record", "completeness", why=why):
            completeness.check(
                store, why, round_idx=round_idx, candidate=candidate, subject=subject
            )
    if not enabled():
        return None
    from octomod.orchestration import timing as _timing

    try:
        if why in ("run_end", "final"):
            # the run's own writes are over: reclaim what replaced groups
            # left behind before the last checkpoint is taken of it
            with _timing.span("record", "compact"):
                store.compact()
        # a checkpoint verifies the whole file and copies it — at every
        # marker and decision, so it is most of what the engine's own time is
        with _timing.span("record", "checkpoint", why=why):
            return store.checkpoint()
    except RecordDamaged:
        # the ONE failure a checkpoint must not swallow: the file was damaged
        # and has just been restored from the last checkpoint, so everything
        # this process wrote since is gone — the run stops, and its resume
        # starts from the last good marker
        raise
    except Exception as e:  # noqa: BLE001 - a safety copy must never end a run
        if ledger is not None:
            ledger.append(
                "note",
                module=why,
                round_idx=round_idx,
                note=f"record checkpoint failed: {type(e).__name__}: {str(e)[:300]}",
                swallowed=True,
            )
        return None


def commit_ctx(ctx, *, why: str, subject: str | None = None) -> Path | None:
    """`commit_run` for a RunContext."""
    return commit_run(
        ctx.store,
        ctx.ledger,
        why=why,
        round_idx=ctx.round_idx,
        candidate=getattr(ctx, "candidate", None),
        subject=subject,
    )
