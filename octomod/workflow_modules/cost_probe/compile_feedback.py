"""A compile or fit failure that names the observation model goes back to its author, once per round.

The candidate loop drops a candidate AMICI cannot build or fit, and the round
goes on with the others. When the failure's text names the observation model
(`solver_messages.attribute_compile_error`) and this round's observation agent
drafted the assembly, the failure goes back to that agent first: its lines and
the rows of the candidate's PEtab observables table the compiler read, as the
engine's finding (`RedraftRequested` with source `engine`, caught by the
orchestrator's assemble-compile-fit loop, which re-drafts the shared assembly
and rebuilds every candidate on it). One per round, recorded in the round's
`compile_feedback` so a resume reads it back instead of spending another, and
hands the finding back when the agent never answered it. When it is spent,
when the round carried its assembly (no reply of this round to return to), or
when the failure names no block, the candidate is dropped as before.

The redraft rebuilds the round, so it removes what would read back the old
assembly: the shared draft and every candidate's merge, S3 marker and checker
verdict. From the compile on it is a re-entry at estimation in every respect,
and it sets the estimation module's records aside exactly as that re-entry does
(`round_status.invalidate_from`, then `round_status.supersede_slots`): the
compile approval and every unit of work's cost and fit markers, recorded
decisions and solver overrides are forgotten, and the cost profiles, the fits,
the round's and each candidate's `estimation_settings` and a candidate's
remembered `budget_declined` are moved under the round's `superseded/`. A
problem rebuilt on a new observation model is never compiled on an old yes, a
fit of the old one is not a fit of it, and a decline or a solver choice made on
the old problem is made again on the rebuilt one: the compile card and the
budget gates are asked again. The engine-feedback ledger row names what was
set aside.
"""

from __future__ import annotations

import datetime
import re

KEY = "compile_feedback"
ROLE = "observation"
MODULE = "candidate_compile"
ROWS_KEPT = 40
HEAD_CHARS = 300


def spent(rnd) -> dict | None:
    """This round's engine redraft, if one was sent, else None. `rnd` is the
    round's node (`ctx.round`).

    The record is the decision: an unreadable body loses its details, not the
    fact that the redraft was spent."""
    node = rnd / KEY
    if not node.exists():
        return None
    try:
        rec = node.get(None)
    except Exception:
        rec = {}
    return rec if isinstance(rec, dict) else {}


def named_ids(text: str, ids) -> list[str]:
    """The ids the failure names, in table order.

    An id counts where it stands alone or ends a longer PEtab name
    (`noiseParameter1_obs_x`, `sigma_obs_x`), not where it begins one."""
    text = str(text)
    return [
        i
        for i in ids
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9_])", text)
    ]


def offending_rows(work, text: str) -> tuple[list[str], str]:
    """(the observable ids the failure names, the rows of the unit of work's
    observables table the compiler read for them, as the TSV text PEtab
    reads) — every row when it names none. `work` is the fitted problem's
    group (`ctx.work`); its table is `petab/observables`."""
    from octomod.workflow_modules.assembly import petab_io

    try:
        df = (work / "petab/observables").table(None)
    except Exception:  # an unreadable table has no rows to quote
        return [], ""
    if df is None:
        return [], ""
    if "observableId" not in df.columns:
        return [], petab_io.table_text(df.head(ROWS_KEPT))
    ids = named_ids(text, df["observableId"].astype(str).tolist())
    picked = df[df["observableId"].astype(str).isin(ids)] if ids else df
    return ids, petab_io.table_text(picked.head(ROWS_KEPT))


def finding(candidate: str, lines: list[str], ids: list[str], rows: str) -> str:
    """The engine's finding, in the engine's voice: what failed, what AMICI
    said, the rows it read, and what the agent is asked to return."""
    which = (
        f"the rows of the observables table for the ids it names ({', '.join(ids)})"
        if ids
        else "every row of the observables table (it names no observable id)"
    )
    return (
        f"The AMICI compile or fit of candidate {candidate!r} failed, and the "
        f"failure names the observation model. AMICI reported:\n"
        + "\n".join(f"  {ln}" for ln in lines)
        + f"\nThese are {which}, as the compiler read them:\n{rows.rstrip()}\n"
        "Change what the error names and return the same contract in full."
    )


def invalidate(ctx, cand_ids) -> dict[str, list[str]]:
    """Remove what the rebuild must not read back: what a redraft at the
    compile card removes (`compile_gate.assembly_invalidations`: the shared
    draft, each candidate's merge, S3 marker and checker verdict), and from
    the compile on what a re-entry at estimation sets aside, by the
    re-entry's own two calls: `round_status.invalidate_from` (the markers,
    the recorded decisions and the solver overrides in `cost`, in the round
    and in every unit of work), then `round_status.supersede_slots` (the
    estimation module's records moved under the round's `superseded/`). A
    record that is not there is nothing to remove.

    Returns what was set aside, keyed as the ledger row carries it: the keys
    moved (`superseded_files`), the decisions forgotten (`forgotten_decisions`) and
    the cost records whose override was dropped (`dropped_solver_overrides`),
    each relative to the round."""
    from octomod.orchestration import round_status as rs
    from octomod.workflow_modules.cost_probe import compile_gate

    for node in compile_gate.assembly_invalidations(ctx.round, list(cand_ids)):
        try:
            node.delete()
        except OSError:
            pass
    _removed, forgotten, dropped = rs.invalidate_from(ctx, "estimation")
    superseded = rs.supersede_slots(ctx, "estimation")
    return {
        "superseded_files": superseded,
        "forgotten_decisions": forgotten,
        "dropped_solver_overrides": dropped,
    }


def send_back_if_owed(ctx, candidate: str, exc: BaseException, cand_ids) -> None:
    """Raise the engine redraft for this failure when one is owed.

    Returns (and the caller drops the candidate) when the failure names no
    block, when this round has no reply of the observation agent to return it
    to, or when this round's redraft is spent. Otherwise removes what the
    rebuild must not read back, records the redraft (the round's
    `compile_feedback`, and one ledger row naming what was set aside), and
    raises RedraftRequested with source `engine` for the observation agent.
    The removal comes first: one that fails leaves the redraft unspent, so a
    resume sends it again rather than rebuilding on what was not removed."""
    from octomod.orchestration.interaction import human_redraft as _hr
    from octomod.workflow_modules.cost_probe import solver_messages as _msgs

    lines = _msgs.failure_lines(exc)
    text = "\n".join(lines)
    role = _msgs.attribute_compile_error(text)
    if role is None:
        return
    head = " | ".join(lines)[:HEAD_CHARS]
    if not (ctx.agent_calls.child(role) / "reply").exists():
        ctx.ledger.append(
            "note",
            module=MODULE,
            round_idx=ctx.round_idx,
            candidate=candidate,
            role=role,
            note=(
                f"candidate {candidate}: its compile or fit failure names the "
                f"observation model, and this round carried its assembly — no "
                f"reply of this round to return it to: {head}"
            ),
        )
        return
    if spent(ctx.round) is not None:
        return
    ids, rows = offending_rows(ctx.work, text)
    body = finding(candidate, lines, ids, rows)
    set_aside = invalidate(ctx, cand_ids)
    record = ctx.round / KEY
    record.put(
        {
            "role": role,
            "candidate": candidate,
            "attempt": 1,
            "error_head": head,
            "observable_ids": ids,
            "finding": body,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
    )
    ctx.ledger.append(
        "note",
        module=MODULE,
        round_idx=ctx.round_idx,
        candidate=candidate,
        role=role,
        engine_feedback=True,
        error_head=head,
        observable_ids=ids,
        **set_aside,
        note=(
            f"the engine sent candidate {candidate}'s compile or fit failure "
            f"back to {role} — the engine's finding, not a person's request; "
            f"once per round ({record.key}): {head}"
        ),
    )
    # the round's budget reference was measured on the old problem
    ctx.cache.pop("_budget_reference", None)
    raise _hr.RedraftRequested(body, role, source=_hr.ENGINE)


def drop_reason(head: str, spent_before: dict | None) -> str:
    """The `candidate_dropped` reason; it says so when this round's engine
    redraft was spent before this failure."""
    if spent_before is None:
        return f"compile or fit failed — {head}"
    who = spent_before.get("candidate")
    return (
        "compile or fit failed after one engine redraft of the observation "
        "model this round"
        + (f" (sent for candidate {who})" if who else "")
        + f" — {head}"
    )


def restore(ctx) -> None:
    """On a resume, hand the finding back when the agent never answered it.

    The block lives in the process that raised the redraft; the finding is in
    the round's `compile_feedback`. When this round's engine redraft has no
    accepted reply of its role after it (`agent_call` is ledgered only for
    one), the process stopped before the agent answered — a timeout, a kill —
    and without the finding the agent would redraft blind on a budget already
    spent."""
    from octomod.orchestration.interaction import human_redraft as _hr

    if ctx.cache.get("_human_feedback"):
        return
    rec = spent(ctx.round)
    if not rec or not rec.get("finding"):
        return
    role = str(rec.get("role") or ROLE)
    rows = [e for e in ctx.ledger.entries() if e.get("round") == ctx.round_idx]
    sent = max(
        (
            str(e.get("ts", ""))
            for e in rows
            if e.get("event") == "note" and e.get("engine_feedback")
        ),
        default="",
    )
    answered = any(
        e.get("event") == "agent_call"
        and e.get("role") == role
        and str(e.get("ts", "")) >= sent
        for e in rows
    )
    if sent and not answered:
        ctx.cache["_human_feedback"] = _hr.context_for(
            str(rec["finding"]), role, source=_hr.ENGINE
        )


def consumed(ctx) -> None:
    """The engine's finding answers one assembly pass: once every candidate is
    assembled on it, it is not handed to a later call."""
    fb = ctx.cache.get("_human_feedback")
    if isinstance(fb, dict) and "engine_feedback" in fb:
        ctx.cache.pop("_human_feedback", None)


def card_lines(ctx) -> list[str]:
    """For the compile card: the engine redraft this round, when one was sent."""
    rec = spent(ctx.round)
    if rec is None:
        return []
    return [
        f"the engine sent candidate {rec.get('candidate')}'s compile failure back "
        f"to {rec.get('role') or ROLE} once this round ({(ctx.round / KEY).key}): "
        f"{str(rec.get('error_head') or '')[:200]} — this card is asked again on "
        f"the redrafted assembly"
    ]
