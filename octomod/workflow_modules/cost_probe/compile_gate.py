"""The compile boundary: the one card before the first real compute.

Asked once per round, after S3, on both paths: for the round's candidate set,
or for the single model (`cand_ids == [None]`). Everything before it is cheap
and redoable; after it AMICI compiles and the probe starts run. The answer is
recorded at the round's `decisions/assembly_cost_boundary` and the `candidate_compile`
marker says the card was signed, so a resume reads the answer back instead of
asking again, and a `--from-module estimation` re-entry, which forgets both,
asks it again.

A `redraft:` in the note sends the assembly back to the agents that wrote it
(RedraftRequested, caught by the caller's assemble-and-ask loop) after removing
what S3 would otherwise read back as already done.
"""

from __future__ import annotations

from octomod.orchestration.interaction import human_redraft as _hr
from octomod.orchestration.interaction import humangate
from octomod.orchestration.run_context import ModuleFailure, NoteRefused
from octomod.result import node as _tree
from octomod.result.node import Node

ROLE = "the assembly agents"
WHERE = (
    "the cost boundary — everything before this was cheap and redoable; "
    "everything after costs compile + optimisation time"
)


def decision_node(rnd: Node) -> Node:
    """Where the round's compile answer is recorded, on both paths (the
    round's `decisions/assembly_cost_boundary`)."""
    return rnd / "decisions" / "assembly_cost_boundary"


def is_single(cand_ids: list[str | None]) -> bool:
    return list(cand_ids) == [None]


def assembly_invalidations(rnd: Node, cand_ids: list[str | None]) -> list[Node]:
    """Every record a redraft of the assembly must remove before S3 runs again:
    the shared draft, and for each unit of work (the round's `_single` for the
    single model) the merged copy, the `s3` marker and the checker's verdict.
    S3 checks its marker first, so a marker left behind answers "already
    passed" over caches that no longer exist; the verdict is about the
    assembly the person just sent back, so the redrafted one is unaudited
    until the checker runs again."""
    out = [rnd / "shared_assembly"]
    for cid in cand_ids:
        out.append(_tree.work_node(rnd, cid) / "assembly")
        out.append(_tree.markers_node(rnd, cid).child("s3"))
        out.append(_tree.gates_node(rnd, cid).child("assembly_verification"))
    return out


def _s3_record(ctx, cid: str | None) -> dict:
    """What S3 recorded about this unit of work's problem (its marker payload)."""
    try:
        rec = _tree.markers_node(ctx.round, cid).child("s3").get({})
    except Exception:  # an unreadable marker records nothing
        return {}
    return rec if isinstance(rec, dict) else {}


def user_supplied(ctx, cand_ids: list[str | None]) -> bool:
    """The single model's problem was supplied whole: no agent assembled it,
    so there is no agent reasoning to point to and nobody to redraft it."""
    return (
        is_single(cand_ids) and _s3_record(ctx, None).get("producer") == "user-supplied"
    )


def _problem_counts(ctx, cid: str | None) -> tuple:
    """(estimated parameters, training points, held-out points) as S3 counted
    them, or counted from the tables when the marker carries no count (an
    entry marker set over a supplied problem)."""
    rec = _s3_record(ctx, cid)
    counts = (rec.get("n_estimated"), rec.get("n_train"), rec.get("n_holdout"))
    if None not in counts:
        return counts
    petab = _tree.work_node(ctx.round, cid) / "petab"

    def _rows(name: str):
        p = petab / name
        return p.table() if p.exists() else None

    pars, meas, hold = (
        _rows(n) for n in ("parameters", "measurements", "holdout_measurements")
    )
    counted = (
        int((pars["estimate"] == 1).sum()) if pars is not None else None,
        len(meas) if meas is not None else None,
        len(hold) if hold is not None else 0,
    )
    return tuple(
        c if c is not None else k for c, k in zip(counts, counted, strict=True)
    )


def _checker_lines(ctx, cand_ids: list[str | None]) -> list[str]:
    """The independent checker's summary from each S3 pass, named by candidate
    on a candidate set; the pointer to the full reasoning is printed once."""
    lines: list[str] = []
    pointers: list[str] = []
    for cid in cand_ids:
        for line in _s3_record(ctx, cid).get("checker_summary") or []:
            if line.startswith("  "):
                if line not in pointers:
                    pointers.append(line)
            else:
                lines.append(line if cid is None else f"{cid}: {line}")
    return lines + pointers


def _identity_lines(ctx, cand_ids: list[str]) -> list[str]:
    """A seeded round's base must be the model it was seeded from: checked
    before anything is compiled, with every difference named, and ledgered once
    per round."""
    from octomod.orchestration import round_seed as _seed

    identity = _seed.base_identity(ctx, cand_ids)
    if identity is None:
        return []
    lines = _seed.identity_lines(identity)
    if not any(
        e.get("round") == ctx.round_idx and e.get("base_identity")
        for e in ctx.ledger.entries()
    ):
        ctx.ledger.append(
            "note",
            module="assembly_cost_boundary",
            round_idx=ctx.round_idx,
            note=" ".join(lines),
            base_identity=identity,
        )
    return lines


def card_lines(ctx, cand_ids: list[str | None]) -> list[str]:
    """The compile card's evidence, in one order for both paths: each problem,
    the pointer to the agents' reasoning (when agents assembled it), the data
    flags and what the curves look like (and whether the raw-file reading
    construction was given agrees), the checker, then (on a candidate set) the
    base identity and the observation layer's open choices, and last what the
    battery feedback and the data processing did."""
    from octomod.workflow_modules.assembly import engine as _s3
    from octomod.workflow_modules.data import phenomenology as _ph
    from octomod.workflow_modules.data import raw_phenomenology as _raw
    from octomod.workflow_modules.model import model_space as _ms

    single = is_single(cand_ids)
    lines = []
    for cid in cand_ids:
        n_est, n_train, n_hold = _problem_counts(ctx, cid)
        if single:
            lines.append(
                f"estimation problem: {n_est} estimated parameters, {n_train} "
                f"training points, {n_hold} held-out points"
            )
        else:
            lines.append(
                f"{cid}: {n_est} estimated parameters, {n_train} training "
                f"points — battery passed"
            )
    if not user_supplied(ctx, cand_ids):
        lines.append(
            "full reasoning of every agent: "
            f"{humangate.show_command(ctx.round / 'decisions_md')}"
        )
    report = (ctx.round / "data" / "report").get({})
    lines += _s3.flag_lines(report.get("flags") if isinstance(report, dict) else [])
    # what the curves look like, in the words construction is given of the data
    lines += _ph.card_lines((ctx.round / "data" / "phenomenology").get(None))
    # and whether the raw-file reading construction was given agrees with it
    lines += _raw.check_card_lines(ctx)
    lines += _checker_lines(ctx, cand_ids)
    if not single:
        lines += _identity_lines(ctx, cand_ids)
        # the first card at which the observation layer exists, so the combined
        # space (structures crossed with the assembly agents' axes) is shown here
        lines += _ms.combined_space_card_lines(
            cand_ids,
            _ms.assembly_observation_axes(ctx, cand_ids),
            int(ctx.spec.get("search.max_models", 8)),
        )
    # re-asks, fallbacks, dropped candidates and axes, the advisory checks'
    # numbers, the processing ops — information, never a stop
    lines += _s3.feedback_card_lines(ctx)
    # why this card is asked again: the engine redrafted the observation model
    # after a compile failure named it, so the problem it approves is new
    from octomod.workflow_modules.cost_probe import compile_feedback as _cf

    lines += _cf.card_lines(ctx)
    return lines


def ask(ctx, cand_ids: list[str | None]) -> None:
    """Ask the compile card for `cand_ids` unless this round's marker says it
    was signed. A no stops the run (unrecorded, so a resume can answer again);
    a `redraft:` raises RedraftRequested for the caller's loop."""
    if ctx.has_marker("candidate_compile"):
        print("  (compile boundary already approved — resumed from marker)")
        return
    single = is_single(cand_ids)
    n = len(cand_ids)
    # nothing to send back to when no agent assembled the problem
    supplied = user_supplied(ctx, cand_ids)
    decision = decision_node(ctx.round)
    approved, note = humangate.ask_once(
        ctx,
        decision,
        (
            "Approve AMICI compile + cost probe? (everything after this costs "
            "real compute)"
            if single
            else f"Approve AMICI compile + cost probe for {n} candidates?"
        ),
        card_lines(ctx, cand_ids),
        module="assembly_cost_boundary",
        record_decline=False,
        intent=ctx.intent,
        note_forms=() if supplied else (_hr.NOTE_FORM,),
        where=WHERE,
        consequences=(
            (
                "AMICI compiles and probe starts run now (first real compute; "
                "the measured budget gate follows)"
                if single
                else f"all {n} candidates compile and probe now (budget gate follows)"
            ),
            "run stops before any expensive step",
        ),
    )
    if not approved:
        raise ModuleFailure("user stopped at the cost boundary")
    if supplied and _hr.parse(note):
        decision.delete()
        raise NoteRefused(
            "the compile card's `redraft:` goes back to the assembly agents, and "
            "no agent assembled this problem: it was supplied whole as PEtab "
            "(input/supplied/petab). To change it, stage the record's input "
            "as a new run's input, edit supplied/petab/ there and start that "
            "run; a resume of this one asks the compile card again.",
            gate="assembly_cost_boundary",
        )
    # the assembly agents authored what this card approves, so this is where a
    # person says the observation model needs a scaling factor
    _hr.raise_if_asked(
        ctx,
        note,
        module="assembly_cost_boundary",
        role=ROLE,
        decision_path=decision,
        invalidate=assembly_invalidations(ctx.round, cand_ids),
    )
    ctx.set_marker("candidate_compile", n_candidates=0 if single else n)
