"""S3 — estimation problem assembly.

Two agents decide: the observation model (mapping, transformation, noise and
scaling as one observation function) and the condition encoding; roles are
split only where a deterministic gate checks the seam between them. A
deterministic merge writes the PEtab tables, a gate battery checks them, and a
verification agent audits the judgment calls. The module records what the
compile card shows about the problem in its marker; the card itself is asked
after the module, once per round (`compile_gate`).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from octomod.gates import GateResult, run_gate_set
from octomod.gates.petab_gates import (
    PetabTables,
    make_petab_gates,
    sigma_state_problem,
)
from octomod.orchestration import (
    timing,  # noqa: E402
)
from octomod.orchestration.interaction import humangate
from octomod.orchestration.run_context import ModuleFailure, RunContext
from octomod.result import node as tree
from octomod.result.slots import AssemblyRecord
from octomod.result.write import write_record
from octomod.workflow_modules.assembly import petab_io
from octomod.workflow_modules.assembly.assembly_edit import (
    NOISE_PER,
    SCALING_PER,
    preequilibration_overrides,
    symbols,
)
from octomod.workflow_modules.data.engine import parse_declared_label
from octomod.workflow_modules.estimation.problem import FITTABLE_NOISE_DISTRIBUTIONS


class MergeRefusal(ModuleFailure):
    """A refusal the MERGE raises about a value an agent wrote — a noise
    formula, an observable mapping, a condition override.

    Routed exactly like a failing T0 check (`_battery_with_feedback`): back to
    the role that wrote the value with the refusal verbatim, then to a person
    with the named fallbacks. Refusals about the testcase or the engine
    (holdout labels, an older S2 table, unmapped labels) stay ModuleFailures."""

    def __init__(self, detail: str, *, gate_id: str):
        super().__init__(detail)
        self.gate_id = gate_id
        self.detail = detail


def _merge_or_refusal(ctx, assembly: dict, sbml: str, long_df, petab):
    """Merge; a MergeRefusal comes back as the failing T0 check it is (and is
    ledgered as one), None when the merge went through."""
    try:
        _merge_to_petab(ctx, assembly, sbml, long_df, petab)
        return None
    except MergeRefusal as e:
        res = GateResult(e.gate_id, "T0", False, detail=e.detail)
        ctx.ledger.append(
            "gate",
            module="assembly",
            round_idx=ctx.round_idx,
            gate_id=e.gate_id,
            tier="T0",
            passed=False,
            blocking=True,
            value=None,
            threshold=None,
            detail=e.detail,
            merge_refusal=True,
        )
        print(f"  ✗ [T0] {e.gate_id}: {e.detail[:160]}")
        return res


@timing.phase("assembly")
def run(ctx: RunContext) -> None:
    """Assemble and validate — redrafting the assembly when a human asks for
    something different at the battery's failure-point gate. The compile card
    that follows is the orchestrator's (`compile_gate`), for both paths."""
    from octomod.orchestration.interaction import human_redraft as _hr

    while True:
        try:
            return _run_once(ctx)
        except _hr.RedraftRequested as req:
            ctx.cache["_human_feedback"] = _hr.context_for(req.text, req.role)
            print(f"  → re-assembling at your request: {req.text[:90]}")


def _run_once(ctx: RunContext) -> None:
    if ctx.marker("s3").exists():
        print("  (already passed — resumed from marker; assembled problem stands)")
        return
    ctx.require_marker("s1", needed_by="assembly")
    ctx.require_marker("s2", needed_by="assembly")

    petab = ctx.work / "petab"
    shared = ctx.round / "shared_assembly"
    sbml = (ctx.model / "sbml").text()
    long_df = (ctx.round / "data/measurements").table()
    data_report = (ctx.round / "data/report").get()
    _restore_seeded_assembly(ctx)
    warn_revision_move_not_carried(ctx)

    # A user-supplied problem is what the testcase declares, or tables the entry
    # adapter staged with no assembly and no agent draft this round — never the
    # leftovers of a failed merge whose assembly a redraft removed.
    declared_supplied = bool((ctx.testcase.get("supplied") or {}).get("petab"))
    supplied = declared_supplied or _left_by_entry_adapter(ctx, petab)
    _drafted_here = True  # a supplied problem is audited like a first draft
    refusal = None  # a merge refusal is the battery's first failing check
    if supplied:
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note="petab problem user-supplied; sub-agents skipped, battery not",
        )
    else:
        _shared_before = shared.exists()
        assembly = _get_or_draft_assembly(ctx, sbml, long_df, data_report)
        _drafted_here = not _shared_before
        refusal = _merge_or_refusal(ctx, assembly, sbml, long_df, petab)

    # ---- deterministic battery, with feedback -------------------------------
    # A blocking failure blocks the ARTIFACT, never the run: it goes back to
    # the role that authored the value, then to a person with named fallbacks.
    tables, results = _battery_with_feedback(
        ctx,
        petab,
        sbml,
        long_df,
        data_report,
        supplied=supplied,
        refusal=refusal,
        reused_shared=(
            ctx.candidate is not None and shared.exists() and not _drafted_here
        ),
    )

    # ---- verification agent (T3 — real, not decisive) ---------------------
    # The assembly describes the DATA, so a candidate set shares one
    # (`shared_assembly`) and it is audited once; the PEtab battery above
    # still runs for every candidate, because the tables differ.
    verification_lines = []
    reused_shared = ctx.candidate is not None and shared.exists() and not _drafted_here
    # "already audited" rests on an audit record, not on the shared assembly's
    # existence: a resume after a battery failure reuses an unaudited assembly
    if reused_shared and not _shared_audited(ctx):
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=f"candidate {ctx.candidate}: shared assembly reused but no "
            f"assembly_verification record exists this round — checker runs",
        )
        reused_shared = False
    if reused_shared:
        audited_here = _audited_by_a_candidate(ctx)
        carried = None if audited_here else _carried_audit(ctx)
        where = ""
        if carried:
            where = f" in {carried['round']}, where this round's seed was built ({', '.join(carried['records'][:3])}"
            if carried.get("overlay_audit"):
                where += f"; its overlay: {carried['overlay_audit']}"
            where += ")"
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=f"candidate {ctx.candidate}: shared assembly "
            f"already audited{where} — checker not re-run",
            audit_carried=bool(carried),
        )
        ov_applied = ctx.work / "assembly_overlay_applied"
        if ov_applied.exists() and ctx.spec.get(
            "verification.assembly_overlay_delta", True
        ):
            # audit only the overlay's DELTA: the shared assembly was audited
            # once; what is new here is what this candidate changed
            verification_lines = _audit_overlay_delta(ctx, petab, data_report)
    if ctx.spec.get("verification.s3", True) and not reused_shared:
        # cached: the checker runs before the compile gate, and the resume
        # that answers that gate re-runs this module, so an uncached call is
        # paid twice per round under the file-gate protocol
        verdict = ctx.call_cached(
            "assembly_verification",
            {
                "intent": ctx.intent,
                "experiment_description": ctx.description,
                "entity_glossary": _glossary(ctx),
                "observables_tsv": _table_text(petab, "observables"),
                "conditions_tsv": _table_text(petab, "conditions"),
                "parameters_tsv": _table_text(petab, "parameters"),
                "data_flags": data_report.get("flags", []),
                "domain_packs": ctx.pack_texts(),
            },
        )
        concerns = [v for v in verdict["verdicts"] if not v.get("ok")]
        res = GateResult(
            "assembly_verification",
            "T3",
            True,
            blocking=False,
            value=verdict["overall"],
            detail="; ".join(f"{v['aspect']}: {v['note']}" for v in concerns)
            or "independent checker raised no concerns",
            advisory_findings=concerns,
        )
        run_gate_set(
            [lambda r=res: r],
            ctx.gates,
            ctx.ledger,
            "assembly",
            round_idx=ctx.round_idx,
        )

        # card lines are a digest — the terminal is not the evidence layer.
        # Full notes: the gate verdict `assembly_verification` and `decisions_md`.
        def _digest(note: str, cap: int = 280) -> str:
            return note if len(note) <= cap else note[:cap].rsplit(" ", 1)[0] + " …"

        verification_lines = [
            f"checker[{v['aspect']}]: "
            + ("ok" if v.get("ok") else f"CONCERN — {_digest(v['note'])}")
            for v in verdict["verdicts"]
        ]

    # ---- what the compile card shows about this problem ------------------
    n_train = len(tables.measurements)
    hold_df = (petab / petab_io.HOLDOUT).table(None)
    n_hold = len(hold_df) if hold_df is not None else 0
    from octomod.reporting.render import decisions_md

    decisions_node = ctx.round / "decisions_md"
    decisions_node.put_text(decisions_md(ctx.round))
    n_est = int((tables.parameters["estimate"] == 1).sum())
    # the checker's digest travels with the marker: the compile card is asked
    # after this module, also by a resume or a re-entry that skips it
    ctx.set_marker(
        "s3",
        n_estimated=n_est,
        n_train=n_train,
        n_holdout=n_hold,
        checker_summary=checker_summary(
            verification_lines,
            where=f"{decisions_node.key} · {ctx.gates.child('assembly_verification').key}",
        ),
        producer="user-supplied" if supplied else "agent:assembly",
    )


def flag_lines(flags, report_key: str = "data/report") -> list[str]:
    """The data flags as the compile card shows them: the count and the first
    three. Triage, not deletion: the complete record is the round's
    `data/report` (`report_key` names it for the card)."""
    flags = list(flags or [])
    if not flags:
        return []
    out = [
        f"data flags: {len(flags)} recorded, none blocking "
        f"(full list: {report_key})"
    ]
    out += [f"  ⚑ {str(f)[:110]}" for f in flags[:3]]
    if len(flags) > 3:
        out.append(f"  … and {len(flags) - 3} more in the record")
    return out


def checker_summary(
    verification_lines: list[str],
    where: str = "decisions_md · gates/assembly_verification",
) -> list[str]:
    """The independent checker's verdicts as the compile card shows them: one
    line when it raised no concern, else every concern and where its reasoning
    is (`where`: the record keys). Empty when the checker did not run in this
    pass."""
    concerns = [line for line in verification_lines if "CONCERN" in line]
    if concerns:
        return concerns + [f"  (full checker reasoning: {where})"]
    if verification_lines:
        return [
            f"independent checker: {len(verification_lines)} aspects "
            f"audited, no concerns"
        ]
    return []


# ---------------------------------------------------------------- sub-agents


def _audit_overlay_delta(ctx: RunContext, petab, data_report) -> list[str]:
    """Independent checker over an observation-axis overlay: the changed
    entries only, against the shared assembly they modify. Advisory, like
    every T3 verdict; recorded per candidate as the gate verdict
    `assembly_verification`."""
    from octomod.agents import AgentCallError

    shared = (ctx.round / "shared_assembly").get()
    asm = (ctx.work / "assembly").get()
    applied = (ctx.work / "assembly_overlay_applied").get()
    delta = {}
    for key in ("observables", "noise", "scaling", "conditions"):
        idk = "condition_id" if key == "conditions" else "observable_id"
        before = {e[idk]: e for e in shared.get(key, [])}
        for e in asm.get(key, []):
            if before.get(e[idk]) != e:
                delta.setdefault(key, []).append(
                    {"before": before.get(e[idk]), "after": e}
                )
    audit_ctx = {
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        "audit_scope": (
            "This candidate applies an OBSERVATION-AXIS overlay to "
            "an assembly that was already audited. Audit ONLY the "
            "changed entries below — is the alternative observation "
            "model a legitimate hypothesis about the measurement "
            "process, or a fit device?"
        ),
        "overlay": applied,
        "changed_entries": delta,
        "observables_tsv": _table_text(petab, "observables"),
        "data_flags": data_report.get("flags", []),
    }
    # The question depends on the overlay and the assembly, not the model
    # structure, so one answer serves every candidate asking it word for word.
    # Stored beside the checker's call (`agent_calls/assembly_verification/
    # overlay_audits/<key>`), so a re-entry at assembly supersedes it.
    import hashlib
    import json as _json

    key = hashlib.sha256(
        _json.dumps(audit_ctx, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    store = ctx.agent_calls.child("assembly_verification") / "overlay_audits" / key
    try:
        if store.exists():
            kept = store.get()
            verdict = kept["verdict"]
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=(
                    f"candidate {ctx.candidate}: overlay delta audit reused — the "
                    f"identical question was answered for candidate "
                    f"{kept.get('audited_for')!r} this round; no agent call"
                ),
                overlay_audit_reused=kept.get("audited_for"),
            )
            print(
                f"  overlay audit: identical to candidate {kept.get('audited_for')!r}'s "
                f"— reusing its verdict, no agent call"
            )
        else:
            verdict = ctx.call("assembly_verification", audit_ctx)
            store.put({"verdict": verdict, "audited_for": ctx.candidate})
    except AgentCallError as e:
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=f"overlay delta audit skipped: {e}",
        )
        return []
    concerns = [v for v in verdict["verdicts"] if not v.get("ok")]
    res = GateResult(
        "assembly_verification",
        "T3",
        True,
        blocking=False,
        value=verdict["overall"],
        detail=(
            (
                "overlay delta: "
                + "; ".join(f"{v['aspect']}: {v['note']}" for v in concerns)
            )
            if concerns
            else "overlay delta audit raised no concerns"
        ),
        advisory_findings=concerns,
    )
    run_gate_set(
        [lambda r=res: r],
        ctx.gates,
        ctx.ledger,
        "assembly",
        round_idx=ctx.round_idx,
    )
    return [
        f"checker[{v['aspect']}]: "
        + ("ok" if v.get("ok") else f"CONCERN — {v['note'][:200]}")
        for v in verdict["verdicts"]
    ]


def _table_text(petab, name: str) -> str:
    """One assembled table as the TSV text PEtab would read — what the
    verification agent is shown."""
    return petab_io.table_text((petab / name).table())


def _audited_by_a_candidate(ctx: RunContext) -> bool:
    """Does any candidate of this round carry a `gates/assembly_verification`
    verdict — the only thing that proves an audit happened this round?"""
    return any(
        (tree.work_node(ctx.round, cid) / "gates/assembly_verification").exists()
        for cid in tree.candidate_ids(ctx.round)
    )


def _shared_audited(ctx: RunContext) -> bool:
    """Has the round's shared assembly been through the independent checker?
    True when any candidate of this round carries a `assembly_verification` verdict
    — the only thing that proves an audit happened — or when the round was
    seeded with an assembly the previous round audited and it is still that
    assembly (`round_seed.carried_audit`)."""
    if _audited_by_a_candidate(ctx):
        return True
    return _carried_audit(ctx) is not None


def _carried_audit(ctx: RunContext) -> dict | None:
    from octomod.orchestration import round_seed as _seed

    shared = ctx.round / "shared_assembly"
    return _seed.carried_audit(ctx.round, shared.get(None))


def _restore_seeded_assembly(ctx: RunContext) -> None:
    """In a seeded round the shared assembly IS the seed — an input of this
    module, not its product. A `--from-module assembly` re-entry moves
    the record aside with the module's products; it is put back, unless a redraft
    was asked this round (by a human, or by the engine after a compile failure
    that named the observation model), which is the one thing that replaces it."""
    from octomod.orchestration import round_seed as _seed

    if (
        ctx.candidate is None
        or redraft_asked_this_round(ctx)
        or engine_redraft_this_round(ctx)
    ):
        return
    if _seed.restore_shared(ctx.round):
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=(
                "shared assembly restored from the round's `model/seed`: in a seeded "
                "round it is the model the round started from, so a re-entry "
                "re-merges it rather than asking the agents for a new one (a "
                "redraft is how to replace it)"
            ),
        )


def warn_revision_move_not_carried(ctx: RunContext) -> str | None:
    """A revision round whose move edited the ASSEMBLY (a noise model, an
    offset, a scaling: `assembly_edit.MOVE_TO_PATCH`) starts from the edited
    assembly S11 seeded. A `--from-module assembly` re-entry sets that aside with
    the module's products, and the assembly agents rebuild from the model and the
    data — which do not carry the move. The rebuilt assembly may therefore not
    contain it, and nothing else would say so: warn, on the console and in the
    ledger, and build as asked. A move on the MODEL (a parameter fixed or freed,
    bounds changed) lives in the model and is not affected.

    Returns the warning, or None when there is nothing to warn about."""
    from octomod.orchestration import round_seed as _seed
    from octomod.workflow_modules.assembly import assembly_edit

    seed = _seed.seeded(ctx.round)
    if not _seed.is_revision(seed):
        return None
    frm = seed.get("seeded_from") or {}
    move = frm.get("move") or {}
    if isinstance(move, str):
        # the seed names the move's TYPE; its arguments are in the revision
        # the previous round recorded
        prev = frm.get("round")
        rev = (
            (tree.round_node(ctx.root, int(prev)) / "revision").get(None)
            if isinstance(prev, int)
            else None
        )
        recorded = (rev or {}).get("move") if isinstance(rev, dict) else None
        move = (
            recorded
            if isinstance(recorded, dict) and recorded.get("type") == move
            else {"type": move}
        )
    if move.get("type") not in assembly_edit.MOVE_TO_PATCH:
        return None
    if (ctx.work / "assembly").exists() or redraft_asked_this_round(ctx):
        return None
    what = f"{move.get('type')} {move.get('args') or {}}"
    warning = (
        f"this round was created by the revision move `{what}`, which edited the "
        f"assembly; the re-entry set that assembly aside and the agents are "
        f"building a new one from the model and the data, which do NOT carry the "
        f"move — check that the new assembly contains it (or state it in a "
        f"redraft note at the assembly card)"
    )
    print(f"  ⚑ {warning}")
    ctx.ledger.append(
        "note",
        module="assembly",
        round_idx=ctx.round_idx,
        note=f"WARNING: {warning}",
        revision_move_not_reapplied=True,
        move=move,
    )
    return warning


def redraft_asked_this_round(ctx: RunContext) -> bool:
    """A human asked the assembly agents to redraft in this round (ledgered at
    the gate, so it survives the process that received it)."""
    return any(
        e.get("round") == ctx.round_idx
        and e.get("event") == "note"
        and e.get("human_redraft")
        for e in ctx.ledger.entries()
    )


def _is_engine_redraft(e: dict) -> bool:
    return e.get("event") == "note" and bool(e.get("engine_feedback"))


def engine_redraft_this_round(ctx: RunContext) -> bool:
    """The engine sent a compile failure back to an assembly agent in this
    round (`compile_feedback`; ledgered, so it survives the process that sent
    it). Kept apart from `redraft_asked_this_round`: it is not a person's."""
    return any(
        e.get("round") == ctx.round_idx and _is_engine_redraft(e)
        for e in ctx.ledger.entries()
    )


def _left_by_entry_adapter(ctx: RunContext, petab) -> bool:
    """Tables the entry adapter staged for a problem the testcase does not
    declare as supplied: a `problem_yaml` with no assembly and no agent draft
    this round.

    An expansion round inherits its assembly and never calls the observation
    agent, so after a human redraft removed the candidate's `assembly` its old
    tables would match this signal. A supplied problem is never redrafted by
    agents, so a redraft on record rules it out.
    """
    return (
        (petab / "problem_yaml").exists()
        and not (ctx.work / "assembly").exists()
        and not (ctx.agent_calls.child("observation") / "reply").exists()
        and not redraft_asked_this_round(ctx)
    )


def _paid_replies_to_reuse(ctx: RunContext) -> tuple[dict, dict] | None:
    """Both assembly agents' replies in the record, written AFTER the last
    redraft of this round (a human's, or the engine's after a compile failure)
    — so they already answer it — else None.

    A resume after a crash between the agent calls and the merge would
    otherwise call both agents again without the human's words (the redraft
    text lives only in the process that received it). A redraft raised
    in-process is always younger than the replies in the record, so it still
    redrafts.
    """
    obs_p = ctx.agent_calls.child("observation") / "reply"
    cond_p = ctx.agent_calls.child("condition") / "reply"
    if not (obs_p.exists() and cond_p.exists()):
        return None
    rows = [e for e in ctx.ledger.entries() if e.get("round") == ctx.round_idx]
    last_redraft = max(
        (
            str(e.get("ts", ""))
            for e in rows
            if (e.get("event") == "note" and e.get("human_redraft"))
            or _is_engine_redraft(e)
        ),
        default="",
    )

    def _last_call(role: str) -> str | None:
        ts = [
            str(e.get("ts", ""))
            for e in rows
            if e.get("event") == "agent_call" and e.get("role") == role
        ]
        return max(ts) if ts else None

    t_obs, t_cond = _last_call("observation"), _last_call("condition")
    if not t_obs or not t_cond or t_obs < last_redraft or t_cond < last_redraft:
        return None
    obs, cond = obs_p.get(None), cond_p.get(None)
    if not isinstance(obs, dict) or not isinstance(cond, dict):
        return None
    return obs, cond


def _get_or_draft_assembly(ctx: RunContext, sbml: str, long_df, data_report) -> dict:
    """The candidate's `assembly`, drafted by the agents when none exists.

    The assembly record is the merge's single source of truth; revision moves
    in later rounds edit it rather than the rendered tables. In mechanism
    discrimination the assembly agents run ONCE per round (the assembly
    describes the DATA, which candidates share); the per-candidate battery
    still validates it against each candidate's model."""
    data_obs_labels = sorted(long_df["observable_label"].unique())
    path = ctx.work / "assembly"
    if path.exists():  # pre-seeded by a revision move — OR left by a failed try
        cached = path.get()
        stale = sorted(
            {str(o.get("maps_to_label")) for o in cached.get("observables", [])}
            - set(data_obs_labels)
        )
        if stale:
            # existence alone cannot tell a revision pre-seed from one a
            # crashed attempt left behind, so it is checked against the data
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=f"discarded unusable assembly (maps_to_label {stale} "
                f"not in the measurements {data_obs_labels}) — redrafting",
            )
            print(
                f"  (discarding an unusable assembly from an earlier "
                f"attempt: labels {stale} do not exist in the data — "
                f"redrafting)"
            )
        else:
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note="assembly pre-seeded by revision move",
            )
            return cached
    shared = ctx.round / "shared_assembly"
    if ctx.candidate is not None and shared.exists():
        asm = _with_overlay(ctx, shared.get())
        write_record(path, AssemblyRecord, asm)
        return asm

    obs_ctx, labels, model_summary, glossary, data_obs_labels = _observation_context(
        ctx, sbml, long_df, data_report
    )
    reused = _paid_replies_to_reuse(ctx)
    if reused is not None:
        reply, conditions = reused
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note="assembly agents' replies reused from the record: both post-date "
            "the last redraft of this round, so they already answer it — "
            "no agent call",
        )
        print(
            "  (reusing both assembly agents' replies from the record — they "
            "post-date the last redraft; no agent call)"
        )
        reply = _draft_observation_reply(
            ctx, obs_ctx, reply, data_obs_labels, model_summary
        )
        cond_ctx = _condition_context(ctx, labels, model_summary, glossary, reply)
    else:
        reply = ctx.call("observation", obs_ctx)
        reply = _draft_observation_reply(
            ctx, obs_ctx, reply, data_obs_labels, model_summary
        )
        cond_ctx = _condition_context(ctx, labels, model_summary, glossary, reply)
        conditions = ctx.call("condition", cond_ctx)
    # the agents that AUTHOR the observation layer may declare where it is
    # open; an axis the engine cannot apply goes BACK to its author once, and
    # every drop is printed on the card that approves the space
    reply, conditions = _record_axes_with_reask(
        ctx, reply, conditions, sbml, obs_ctx, cond_ctx, data_obs_labels, model_summary
    )
    obs_block, noise_block, scaling_block = split_observation_reply(reply)
    assembly = {
        "observables": obs_block,
        "noise": noise_block,
        "scaling": scaling_block,
        "conditions": conditions["conditions"],
    }
    if ctx.candidate is not None:
        # the shared base is the DRAFT; each candidate's own `assembly` is
        # the draft plus that candidate's observation-axis overlay
        write_record(shared, AssemblyRecord, assembly)
        assembly = _with_overlay(ctx, assembly)
    write_record(path, AssemblyRecord, assembly)
    return assembly


def _design_summary_for(ctx) -> dict:
    """S2's design summary, if this round has one.

    Absent for a supplied-PEtab entry, where there are no raw files to
    summarise — the key is then simply not in the context, which the routing
    table allows (it grants keys, it does not require them)."""
    summary = (ctx.round / "data/design_summary").get(None)
    if summary is None:
        return {}
    return {"design_summary": summary} if summary.get("available") else {}


def _with_overlay(ctx: RunContext, asm: dict) -> dict:
    """Apply the candidate's observation-axis overlay (from the model_space
    enumerator) to the shared assembly. Labels are resolved against the base
    assembly HERE — the first moment it exists for a construction-declared
    axis — and a reference that does not resolve stops this candidate with the
    axis named, never as a downstream battery mystery."""
    ov_node = ctx.model / "assembly_overlay"
    if not ov_node.exists():
        return asm
    from octomod.workflow_modules.assembly import assembly_edit

    overlay = ov_node.get()
    if not overlay:
        return asm
    try:
        out = assembly_edit.apply_overlay(asm, overlay, assembly_for_refs=asm)
    except ValueError as e:
        raise ModuleFailure(
            f"candidate {ctx.candidate}: observation axis could "
            f"not be applied to the shared assembly — {e}"
        ) from e
    (ctx.work / "assembly_overlay_applied").put(
        [{"patch": p, "as": assembly_edit.describe(p)} for p in overlay]
    )
    ctx.ledger.append(
        "note",
        module="assembly",
        round_idx=ctx.round_idx,
        note=f"candidate {ctx.candidate}: applied observation-axis "
        f"overlay {[assembly_edit.describe(p) for p in overlay]}",
    )
    return out


_TRANSFORMATIONS = ("lin", "log", "log10")
# owned by the estimation path: accepted here <=> fittable there
_DISTRIBUTIONS = FITTABLE_NOISE_DISTRIBUTIONS
_SCALING_MODES = ("none", "factor", "factor_offset", "offset")


# ------------------------------------------------------ no dead ends at S3


def feedback_card_lines(ctx: RunContext) -> list[str]:
    """What the battery feedback did this round and every processing op the
    data went through, as compile-card lines (information, never a stop)."""
    from octomod.orchestration.interaction import battery_feedback as _bf
    from octomod.workflow_modules.data import data_processing as _dp

    lines = _bf.card_lines(ctx, module="assembly")
    # every processing op the data went through, with its numbers
    rep = (ctx.round / "data/report").get(None)
    if rep is not None:
        lines += [
            f"  {ln}" for ln in _dp.card_lines((rep or {}).get("processing") or [])
        ]
    return lines


# A resolve failure on a candidate whose SHARED assembly already passed on
# another candidate is that candidate's own defect (its model lacks an entity
# the shared formula names): dropped with a note, never a re-ask.
RESOLVE_GATES = (
    "assembly_observables_resolve",
    "assembly_conditions_resolve",
    "assembly_measurements_resolve",
    # the graph check reads the same names: a piece this model leaves
    # unobserved, or a varied quantity it carries to no readout, where another
    # model's did not
    "assembly_connected",
)
# hard ceiling on battery -> feedback -> battery cycles per module run; the
# budget and the human's grants bound the agent calls, this bounds the loop
MAX_FEEDBACK_CYCLES = 12


class CandidateDefect(ModuleFailure):
    """One candidate's model cannot carry the shared assembly. The
    orchestrator drops the candidate and continues."""

    def __init__(self, candidate: str, reason: str):
        super().__init__(f"candidate {candidate}: {reason}")
        self.candidate = candidate
        self.reason = reason


def _nominal_magnitudes(ctx: RunContext) -> dict:
    """What each species does at NOMINAL parameters, read from the S1 gate that
    already integrated it — never a second integration here."""
    # the unit of work's gate verdicts, then the round's
    for gates in (ctx.gates, ctx.round / "gates"):
        p = gates.child("model_simulates_nominal")
        if p.exists():
            try:
                val = (p.get() or {}).get("value") or {}
            except Exception:
                continue
            mags = val.get("nominal_magnitudes") if isinstance(val, dict) else None
            if mags:
                return {
                    "per_species": mags,
                    "caveat": (
                        "simulated at NOMINAL parameters, which are placeholders — a "
                        "mismatch of orders of magnitude against the data's support "
                        "is weak evidence for a scaling parameter, a unit mismatch, "
                        "or nothing at all. It informs your scaling block; the engine "
                        "does not block on it, because a magnitude alone cannot "
                        "tell those three apart."
                    ),
                }
    return {
        "per_species": {},
        "caveat": "not available: the S1 nominal simulation left no record",
    }


def _observation_context(ctx: RunContext, sbml: str, long_df, data_report) -> tuple:
    """The observation agent's payload, built ONCE here so a battery re-ask
    hands the agent exactly the context it drafted from, plus the feedback."""
    data_obs_labels = sorted(long_df["observable_label"].unique())
    model_summary = _model_summary(sbml)
    # The labels the merge will demand come from the DATA: if the report lost
    # them (a carried-forward round), fall back to the measurement table
    # rather than handing the agent an empty list to guess from.
    declared = data_report.get("observable_labels") or []
    labels = {
        "observable_labels": declared
        or [{"label": label} for label in data_obs_labels],
        "condition_labels": sorted(long_df["condition_label"].unique()),
        "maps_to_label_must_be_one_of": data_obs_labels,
    }
    glossary = _glossary(ctx)
    # ONE role authors the observation function: mapping, transformation +
    # noise and scaling are one decision whose coherence no gate can check.
    # The engine splits the reply into the assembly's blocks.
    obs_ctx = {
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        "model_summary": model_summary,
        "entity_glossary": glossary,
        "data_labels": labels,
        "domain_packs": ctx.pack_texts(),
    }
    # The replicates' verdict on the error model, and ONLY that: this role
    # authors the noise formula. No structural hints: those would be
    # construction's, and construction never sees measurement values.
    _sig_node = ctx.round / "data/signals"
    if _sig_node.exists():
        _signals = _sig_node.get() or {}
        # `support` (zeros, negatives, min/max, dynamic range, log legality)
        # is what the agent weighs the model's nominal magnitudes against
        if _signals.get("below_detection"):
            # the agent that authors the noise formula is about to see the
            # declared floor, so the noise shape it returns may depend on it:
            # ledgered here beside the call rather than left implicit
            n_decl = len((_signals.get("below_detection") or {}).get("declared") or [])
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=(
                    f"the observation-model agent is shown {n_decl} "
                    f"below-detection declaration(s) as measurement evidence; the "
                    f"noise shape it chooses may depend on them (no censored "
                    f"likelihood is fitted)"
                ),
            )
        obs_ctx["data_signals"] = {
            "per_observable": {
                label: {"noise": rec.get("noise"), "support": rec.get("support")}
                for label, rec in (_signals.get("per_observable") or {}).items()
            },
            # what the engine DID to the table this agent maps onto
            "processing_applied": _signals.get("processing_applied"),
            # the declared detection floors and what the source did below
            # them — the noise shape must be honest AT the floor
            "below_detection": _signals.get("below_detection"),
            "how_to_read_this": (
                "Measured from the replicates, no model involved: the slope of "
                "log(replicate spread) on log(signal) is 0 for constant error "
                "and 1 for proportional. `error_model` is stated only when the "
                "interval excludes one of those — an `inconclusive` verdict "
                "means these replicates cannot separate them, and you should "
                "argue from the measurement process instead of treating the "
                "number as an answer. Nothing here constrains the MODEL; it is "
                "evidence about the observation function you are authoring."
            ),
        }
    # each assembly agent gets the person's words WITH its own previous reply,
    # so a redraft revises what they reviewed instead of re-rolling it
    from octomod.orchestration.interaction import human_redraft as _hr

    obs_ctx.update(
        _hr.with_previous(ctx, "observation", ctx.cache.get("_human_feedback"))
    )
    model_summary["nominal_magnitudes"] = _nominal_magnitudes(ctx)
    obs_ctx["model_summary"] = model_summary
    # the literature the human staged (a methods section records the assay,
    # units, detection floor and error structure), read from the snapshot S0
    # froze (`intent` is written without it), with construction's `lit_k` ids
    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    _sup = _lit.normalized(_lit.load_frozen(ctx.root))
    if _sup:
        obs_ctx["supplied_literature"] = {
            "items": _sup,
            "how_to_read_this": (
                "Literature the person who staged this problem already has, as "
                "typed claims (origin: human) — the same items construction was "
                "given. Use what they say about the MEASUREMENT: the assay, its "
                "units and whether they are absolute, its detection floor, how "
                "replicates were made, on which scale the error is additive. "
                "Cite an item by its id (lit_1) in the rationale where it decided "
                "something. You see the claim, never the document; do not "
                "attribute to an item anything beyond its supports/quote."
            ),
        }
    return obs_ctx, labels, model_summary, glossary, data_obs_labels


def _condition_context(ctx: RunContext, labels, model_summary, glossary, reply) -> dict:
    from octomod.orchestration.interaction.human_redraft import (
        with_previous as _hr_with_previous,
    )

    obs_block, _n, _s = split_observation_reply(reply)
    return {
        **_hr_with_previous(ctx, "condition", ctx.cache.get("_human_feedback")),
        # the perturbations it encodes are the intent's
        "intent": ctx.intent,
        "experiment_description": ctx.description,
        "condition_labels": labels["condition_labels"],
        "model_summary": model_summary,
        "entity_glossary": glossary,
        # alignment by routing: the condition agent sees the observation
        # function it must be consistent with; enforcement stays with the battery
        "observation_draft": {"observables": obs_block},
        # the encoding follows the DESIGN, so it is shown the design
        **_design_summary_for(ctx),
        # the builder's view of the starting point, which pre-equilibration
        # is decided against
        **_basal_state_for(ctx),
    }


def _basal_state_for(ctx: RunContext) -> dict:
    """The construction agent's `basal_state`, when its build report has one."""
    for model in (ctx.model, ctx.round / "model"):
        node = model / "build_report"
        if node.exists():
            basal = (node.get() or {}).get("basal_state")
            return {"basal_state": basal} if basal else {}
    return {}


def _seam_gate_result(problems: list[str]):
    """The seam checks as ONE failing result, for the card at the failure point."""
    return GateResult(
        "assembly_observation_seam", "T0", False, detail=" | ".join(problems[:4])
    )


def _raise_redraft(ctx: RunContext, text: str, role: str) -> None:
    """A person's words go back to the attributed role, uncharged (raises
    RedraftRequested). Same bookkeeping as `raise_if_asked`."""
    from octomod.orchestration.interaction import human_redraft as _hr

    ctx.cache["_human_feedback"] = _hr.context_for(text, role)
    _hr.send_back(
        ctx,
        "assembly",
        role,
        text,
        remove=[ctx.work / "assembly", ctx.round / "shared_assembly"],
    )


def _record_fallback(
    ctx: RunContext, role: str, name: str, replaced: dict, module: str
) -> None:
    """A fallback is a SIGNED decision: who, which, what it replaced — ledgered,
    and written beside the agent's untouched reply."""
    signed = humangate.signature(ctx.ledger, f"{module}_redraft_budget")
    side = ctx.agent_calls.child(role) / "fallback_applied"
    side.put({"fallback": name, "signed": signed, "replaced": replaced, "role": role})
    ctx.ledger.append(
        "assembly_fallback",
        module=module,
        round_idx=ctx.round_idx,
        role=role,
        fallback=name,
        signed=signed,
        replaced=replaced,
        written_beside=side.key,
    )
    print(
        f"  → fallback {name} applied to {role}'s block (signed: {signed}); the reply in the record is untouched"
    )


def _draft_observation_reply(
    ctx: RunContext,
    obs_ctx: dict,
    reply: dict,
    data_obs_labels: list,
    model_summary: dict,
) -> dict:
    """Seam checks, retried against the merged reply — one dossier per role per
    module, one budget (`retry.module_draft`), then the gate at the failure point
    instead of a stop. Battery failures re-enter through the same function, so
    seam and battery attempts share the count."""
    from octomod.orchestration.interaction import battery_feedback as _bf
    from octomod.orchestration.interaction import retry as _retry

    history = _retry.AttemptHistory(_retry.dossier_of(ctx, "observation"))
    model_ents = set(model_summary.get("species") or []) | set(
        model_summary.get("parameters") or []
    )
    rule_formulas = model_summary.get("assignment_rule_formulas") or {}
    states = set(model_summary.get("species") or []) - set(rule_formulas)
    budget = int(ctx.spec.get("retry.module_draft", 2))
    for _cycle in range(MAX_FEEDBACK_CYCLES):
        problems = _observation_reply_problems(
            reply,
            data_obs_labels,
            model_ents,
            rule_formulas=rule_formulas,
            states=states,
        )
        if not problems:
            return reply
        entry = history.add(
            problems,
            {
                "observables": [
                    {
                        "observable_id": o.get("observable_id"),
                        "maps_to_label": o.get("maps_to_label"),
                        "formula": o.get("formula"),
                        "transformation": o.get("transformation"),
                    }
                    for o in reply.get("observables") or []
                    if isinstance(o, dict)
                ]
            },
        )
        ctx.ledger.append(
            "redraft",
            module="assembly",
            round_idx=ctx.round_idx,
            role="observation",
            attempt=entry["attempt"],
            n_failures=len(problems),
            localized=True,
        )
        if len(history) < budget + history.grants_total:
            obs_ctx["attempt_history"] = history.as_context()
            obs_ctx["attempt_history"]["instruction"] += (
                f" Every maps_to_label MUST be exactly one of {data_obs_labels} — these are "
                f"the labels the data extraction assigned, not the source file's column names."
                f" Legal noise shapes: {noise_shape_help()}."
            )
            reply = ctx.call("observation", obs_ctx)
            continue
        decision, arg = _bf.failure_point_gate(
            ctx,
            "assembly",
            "observation",
            [_seam_gate_result(problems)],
            _bf.observation_block(reply, []),
            history,
            budget,
            offer_fallbacks=True,
        )
        if decision == "more":
            continue  # the grant is in the dossier; the loop re-asks
        if decision == "redraft":
            _raise_redraft(ctx, str(arg), "observation")
        if decision == "fallback":
            reply, replaced = _bf.fallback_into_reply(str(arg), reply, ctx.spec)
            _record_fallback(ctx, "observation", str(arg), replaced, "assembly")
            continue
        raise ModuleFailure(
            "observation model reply still fails its seam checks and the human "
            f"stopped: {' | '.join(problems[:4])}"
        )
    raise ModuleFailure("observation model: feedback cycles exhausted (engine ceiling)")


def _record_axes_with_reask(
    ctx: RunContext,
    reply: dict,
    conditions: dict,
    sbml: str,
    obs_ctx: dict,
    cond_ctx: dict,
    data_obs_labels: list,
    model_summary: dict,
) -> tuple[dict, dict]:
    """Record the assembly agents' axes; a drop goes back to its author ONCE,
    charged to the role's dossier like any failed declaration."""
    from octomod.orchestration.interaction import battery_feedback as _bf
    from octomod.orchestration.interaction import retry as _retry
    from octomod.workflow_modules.model import model_space as _ms

    base_ant = (ctx.model / "antimony").text(sbml)
    base_pars = (ctx.model / "parameters").get([])
    before = len(_ms.dropped_axes(ctx, module="assembly"))
    _ms.record_assembly_axes(
        ctx,
        {"observation": reply, "condition": conditions},
        base_ant,
        base_pars,
    )
    drops = _ms.dropped_axes(ctx, module="assembly")[before:]
    if not drops or ctx.cache.get("_s3_axis_reask_done"):
        return reply, conditions
    ctx.cache["_s3_axis_reask_done"] = True  # one bounded call per module run
    from octomod.workflow_modules.assembly.assembly_edit import KINDS

    for role in ("observation", "condition"):
        mine = [d for d in drops if d.get("declared_by") == role]
        if not mine:
            continue
        history = _retry.AttemptHistory(_retry.dossier_of(ctx, role))
        entry = history.add(
            [f"axis {d['id']} dropped: {d['reason']}" for d in mine],
            {"dropped_axes": mine},
        )
        ctx.ledger.append(
            "redraft_attributed",
            module="assembly",
            round_idx=ctx.round_idx,
            role=role,
            gate_id="model_space_axes",
            attempt=entry["attempt"],
            dropped=[d["id"] for d in mine],
        )
        fb = _bf.feedback(
            {
                "gate_id": "model_space_axes",
                "tier": "T0",
                "detail": "; ".join(f"{d['id']}: {d['reason']}" for d in mine),
            },
            role,
            (reply if role == "observation" else conditions).get("model_space"),
            [],
            {"legal_kinds": sorted(KINDS), "kinds_arguments": KINDS},
            dropped_axes=mine,
        )
        base_ctx = dict(obs_ctx if role == "observation" else cond_ctx)
        base_ctx["attempt_history"] = history.as_context()
        base_ctx["battery_feedback"] = fb
        new_reply = ctx.call(role, base_ctx)
        if role == "observation":
            reply = _draft_observation_reply(
                ctx, obs_ctx, new_reply, data_obs_labels, model_summary
            )
        else:
            conditions = new_reply
        _ms.record_assembly_axes(
            ctx,
            {"observation": reply, "condition": conditions},
            base_ant,
            base_pars,
        )
    return reply, conditions


def _write_assembly(ctx: RunContext, assembly: dict) -> dict:
    """The candidate's `assembly` (and the round's `shared_assembly` for a
    candidate set), stamped so a candidate merged against an OLDER shared base
    can be found and re-merged."""
    shared = ctx.round / "shared_assembly"
    if ctx.candidate is not None:
        version = (
            int((shared.get() or {}).get("_version", 0)) + 1 if shared.exists() else 1
        )
        base = {k: v for k, v in assembly.items() if k != "_version"}
        base["_version"] = version
        write_record(shared, AssemblyRecord, base)
        assembly = _with_overlay(
            ctx, {k: v for k, v in base.items() if k != "_version"}
        )
        assembly["_shared_version"] = version
    write_record(ctx.work / "assembly", AssemblyRecord, assembly)
    return assembly


def _overlay_targets(applied: list, assembly: dict) -> set[str]:
    """The observable ids the applied overlay changed, read from the
    candidate's `assembly_overlay_applied` record (a list of {"patch", "as"}).
    A label is
    resolved against the assembly the patch went into, as `_with_overlay`
    resolved it; one that no longer resolves counts as written."""
    from octomod.workflow_modules.assembly import assembly_edit

    out: set[str] = set()
    for entry in applied or []:
        patch = entry.get("patch") if isinstance(entry, dict) else None
        if not isinstance(patch, dict):
            continue
        try:
            out |= set(
                assembly_edit.patch_targets(assembly_edit.resolve_refs(patch, assembly))
            )
        except ValueError:
            try:
                out |= set(assembly_edit.patch_targets(patch))
            except ValueError:
                continue
    return out


def _overlay_caused(ctx: RunContext, gate, *, reused_shared: bool) -> bool:
    """True when a blocking failure on a candidate is its observation-axis
    overlay's own defect: the observables the check names include one the
    overlay changed, or the check names none of the assembly's observables and
    the shared assembly passed on another candidate, so the overlay is the only
    part of the observation layer that differs. Such a failure is not the
    shared block's author's to repair, and a carried round has no reply of its
    own to hand back. A resolve check that names no observable keeps its own
    rule (`RESOLVE_GATES`): its cause is the model, not the overlay."""
    from octomod.orchestration.interaction import battery_feedback as _bf

    applied = (ctx.work / "assembly_overlay_applied").get(None)
    if ctx.candidate is None or not applied:
        return False
    assembly = (
        (ctx.work / "assembly").get(None)
        or (ctx.round / "shared_assembly").get(None)
        or {}
    )
    obs_ids = [
        str(o.get("observable_id"))
        for o in assembly.get("observables") or []
        if isinstance(o, dict) and o.get("observable_id")
    ]
    implicated = set(_bf.implicated_ids(gate.detail, obs_ids))
    if not implicated:
        return reused_shared and gate.gate_id not in RESOLVE_GATES
    return bool(implicated & _overlay_targets(applied, assembly))


def _battery_with_feedback(
    ctx: RunContext,
    petab,
    sbml: str,
    long_df,
    data_report,
    *,
    supplied: bool,
    reused_shared: bool,
    refusal=None,
):
    """Run the S3 battery; on a blocking failure route it:
    to the role that authored the value, with the check verbatim and its own
    block; to a person at the failure point when the budget is spent or nobody
    can be asked (a role with no reply of this round in the record cannot be); to
    the orchestrator as a CandidateDefect when the candidate's own
    observation-axis overlay caused it (`_overlay_caused`) or the shared
    assembly already passed on another candidate. Returns (tables, results)."""
    from octomod.gates import failure_summary
    from octomod.orchestration.interaction import battery_feedback as _bf
    from octomod.orchestration.interaction import retry as _retry

    def _tables():
        return PetabTables.from_input(petab_io.from_record(petab, sbml=sbml))

    budget = int(ctx.spec.get("retry.module_draft", 2))
    pending = refusal  # a merge refusal is routed like a failing T0 check
    for _cycle in range(MAX_FEEDBACK_CYCLES):
        if pending is not None:
            ok, results = False, [pending]
            pending = None
        else:
            tables = _tables()
            ok, results = run_gate_set(
                make_petab_gates(
                    tables,
                    ctx.spec,
                    cores=None if supplied else _assembled_cores(ctx, sbml),
                ),
                ctx.gates,
                ctx.ledger,
                "assembly",
                round_idx=ctx.round_idx,
            )
        if ok:
            return tables, results
        role, failing = _bf.attribute(results)
        gate = failing[0]
        if supplied:
            role = None  # nobody authored a supplied problem's tables
        elif _overlay_caused(ctx, gate, reused_shared=reused_shared):
            raise CandidateDefect(
                str(ctx.candidate),
                f"its observation axis makes the assembly fail {gate.gate_id}: "
                f"{gate.detail[:200]}",
            )
        if reused_shared and gate.gate_id in RESOLVE_GATES and role is not None:
            raise CandidateDefect(
                str(ctx.candidate),
                f"the shared assembly passed on another candidate but {gate.gate_id} "
                f"fails here — this model lacks what the shared formula names: {gate.detail[:200]}",
            )
        if role is not None and role not in _bf.ASSEMBLY_ROLES:
            _upstream_defect(ctx, role, gate, results)
        if role is not None and _reply(ctx, role) is None:
            # a round that carried its assembly called no assembly agent: there
            # is no block of this round to hand back, so nobody can be asked
            note = (
                f"{role}: no reply of this round in the record to re-ask — the "
                f"check goes to the failure point"
            )
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                candidate=ctx.candidate,
                role=role,
                gate_id=gate.gate_id,
                note=note,
            )
            print(f"  → {note}")
            role = None
        assembly = (ctx.work / "assembly").get() if not supplied else None
        history = _retry.AttemptHistory(_retry.dossier_of(ctx, role)) if role else None
        if role is not None and len(history) < budget + history.grants_total:
            assembly = _reask_after_gate(
                ctx,
                role,
                gate,
                assembly,
                petab,
                sbml,
                long_df,
                data_report,
                history,
            )
            pending = _merge_or_refusal(ctx, assembly, sbml, long_df, petab)
            continue
        block = None
        if role == "observation":
            rep = _reply(ctx, "observation") or {}
            block = _bf.observation_block(
                rep,
                _bf.implicated_ids(
                    gate.detail,
                    [o.get("observable_id") for o in rep.get("observables") or []],
                ),
            )
        elif role == "condition":
            rep = _reply(ctx, "condition") or {}
            block = _bf.condition_block(
                rep,
                _bf.implicated_ids(
                    gate.detail,
                    [c.get("condition_id") for c in rep.get("conditions") or []],
                ),
            )
        decision, arg = _bf.failure_point_gate(
            ctx,
            "assembly",
            role,
            failing,
            block,
            history,
            budget,
            offer_fallbacks=not supplied,
        )
        if decision == "more":
            # the grant belongs to the role that must rewrite, so the failure
            # is carried to the next cycle instead of re-read from the tables:
            # a refused merge wrote none, or left an earlier merge's behind
            pending = gate
            continue
        if decision == "redraft":
            if supplied:
                raise ModuleFailure(
                    "nothing to redraft: the estimation problem was user-supplied; "
                    + failure_summary(results, "S3 assembly", ctx.gates)
                )
            _raise_redraft(ctx, str(arg), role or "the assembly agents")
        if decision == "fallback":
            assembly, replaced = _bf.apply_fallback(str(arg), assembly, ctx.spec)
            _record_fallback(ctx, role or "observation", str(arg), replaced, "assembly")
            assembly = _write_assembly(ctx, assembly)
            pending = _merge_or_refusal(ctx, assembly, sbml, long_df, petab)
            continue
        raise ModuleFailure(failure_summary(results, "S3 assembly", ctx.gates))
    raise ModuleFailure("S3 battery: feedback cycles exhausted (engine ceiling)")


def _upstream_defect(ctx: RunContext, role: str, gate, results) -> None:
    """A check the battery attributes to a role upstream of the assembly (a
    piece of the model no readout sees): the assembly agents cannot repair
    it, so it is never re-asked here. A candidate is dropped; a single
    model stops the module, naming the model module as the one to re-enter."""
    from octomod.gates import failure_summary

    note = (
        f"{gate.gate_id} blames the model itself ({role}'s), which the "
        f"assembly agents cannot repair"
    )
    ctx.ledger.append(
        "note",
        module="assembly",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
        role=role,
        gate_id=gate.gate_id,
        note=note,
    )
    if ctx.candidate is not None:
        raise CandidateDefect(str(ctx.candidate), f"{note}: {str(gate.detail)[:200]}")
    raise ModuleFailure(
        failure_summary(results, "S3 assembly", ctx.gates)
        + f"\n  {note}: re-enter at the model module (--from-module model) with a "
        f"model whose every piece a readout sees"
    )


def _reask_after_gate(
    ctx: RunContext,
    role: str,
    gate,
    assembly: dict,
    petab,
    sbml: str,
    long_df,
    data_report,
    history,
) -> dict:
    """Re-ask ONE role with the failing check verbatim, its own block and the
    merged rows; rebuild the assembly from the repaired reply."""
    from octomod.orchestration.interaction import battery_feedback as _bf

    obs_ctx, labels, model_summary, glossary, data_obs_labels = _observation_context(
        ctx, sbml, long_df, data_report
    )
    entry = history.add([f"{gate.gate_id}: {gate.detail}"], {"gate": gate.gate_id})
    ctx.ledger.append(
        "redraft_attributed",
        module="assembly",
        round_idx=ctx.round_idx,
        role=role,
        gate_id=gate.gate_id,
        attempt=entry["attempt"],
    )
    print(
        f"  → {gate.gate_id} failed; re-asking {role} with the check and its own block (attempt {entry['attempt']})"
    )
    if role == "observation":
        rep = _reply(ctx, "observation") or {}
        ids = _bf.implicated_ids(
            gate.detail,
            [str(o.get("observable_id")) for o in rep.get("observables") or []],
        )
        fb = _bf.feedback(
            _bf.gate_record(gate),
            role,
            _bf.observation_block(rep, ids),
            _bf.table_rows(petab, gate.gate_id, ids),
            _bf.legal_vocabulary(gate.gate_id, model_summary),
        )
        obs_ctx["attempt_history"] = history.as_context()
        obs_ctx["battery_feedback"] = fb
        new_reply = ctx.call("observation", obs_ctx)
        new_reply = _draft_observation_reply(
            ctx, obs_ctx, new_reply, data_obs_labels, model_summary
        )
        o, n, sc = split_observation_reply(new_reply)
        assembly = {**assembly, "observables": o, "noise": n, "scaling": sc}
    else:  # condition
        rep = _reply(ctx, "condition") or {}
        ids = _bf.implicated_ids(
            gate.detail,
            [str(c.get("condition_id")) for c in rep.get("conditions") or []],
        )
        obs_reply = _reply(ctx, "observation") or {"observables": []}
        cond_ctx = _condition_context(ctx, labels, model_summary, glossary, obs_reply)
        cond_ctx["attempt_history"] = history.as_context()
        cond_ctx["battery_feedback"] = _bf.feedback(
            _bf.gate_record(gate),
            role,
            _bf.condition_block(rep, ids),
            _bf.table_rows(petab, gate.gate_id, ids),
            _bf.legal_vocabulary(gate.gate_id, model_summary),
        )
        new_conditions = ctx.call("condition", cond_ctx)
        assembly = {**assembly, "conditions": new_conditions["conditions"]}
    assembly = {k: v for k, v in assembly.items() if not k.startswith("_")}
    return _write_assembly(ctx, assembly)


def _reply(ctx: RunContext, role: str):
    """The role's last reply this round (`agent_calls/<role>/reply`)."""
    return (ctx.agent_calls.child(role) / "reply").get(None)


def _observation_reply_problems(
    reply: dict,
    data_obs_labels: list[str],
    model_entities: set[str] | None = None,
    rule_formulas: dict[str, str] | None = None,
    states: set[str] | None = None,
) -> list[str]:
    """T0 seam checks on the merged observation-model reply, phrased so the
    agent can fix each one specifically.

    `model_entities` lets this check the noise formula is RENDERABLE here,
    where a failure costs one re-ask, rather than at the merge. `states` (the
    model's species) lets it check the sigma reaches the model only through
    the observable's own formula, both with `rule_formulas` expanded.
    """
    problems = []
    # the engine creates these during assembly, so a formula naming one is not
    # naming a free sigma parameter; derived from the reply so the seam check
    # and the assembly agree about what counts as "non-model"
    declared_pars = set()
    for o in reply.get("observables") or []:
        if isinstance(o, dict) and isinstance(o.get("scaling"), dict):
            for key in ("scale_parameter", "offset_parameter"):
                if o["scaling"].get(key):
                    declared_pars.add(str(o["scaling"][key]))
    obs = reply.get("observables")
    if not isinstance(obs, list) or not obs:
        return ["'observables' must be a non-empty list"]
    seen_ids: set[str] = set()
    for o in obs:
        oid = str(o.get("observable_id", "")).strip()
        where = f"observable {oid or '(no id)'}"
        if not oid:
            problems.append("an observable has no observable_id")
        elif oid in seen_ids:
            problems.append(f"{where}: duplicate observable_id")
        seen_ids.add(oid)
        if str(o.get("maps_to_label")) not in set(data_obs_labels):
            problems.append(
                f"{where}: maps_to_label {o.get('maps_to_label')!r} is not one "
                f"of the data labels"
            )
        if not str(o.get("formula", "")).strip():
            problems.append(f"{where}: empty formula")
        if o.get("transformation", "lin") not in _TRANSFORMATIONS:
            problems.append(
                f"{where}: transformation must be one of {_TRANSFORMATIONS}"
            )
        noise = o.get("noise") or {}
        if (
            not isinstance(noise, dict)
            or noise.get("distribution") not in _DISTRIBUTIONS
        ):
            problems.append(
                f"{where}: noise.distribution must be one of {_DISTRIBUTIONS}"
            )
        if (
            isinstance(noise, dict)
            and (noise.get("per") or "observable") not in NOISE_PER
        ):
            problems.append(f"{where}: noise.per must be one of {NOISE_PER}")
        if not isinstance(noise, dict) or not str(noise.get("formula", "")).strip():
            problems.append(
                f"{where}: noise.formula missing — legal shapes are "
                + noise_shape_help()
            )
        elif model_entities is not None and oid:
            # renderable HERE, where a mistake costs one re-ask
            try:
                _render_noise(
                    str(noise.get("formula")),
                    oid,
                    model_entities,
                    declared_pars,
                )
            except NoiseFormulaError as e:
                problems.append(f"{where}: {e}. Legal shapes: {noise_shape_help()}")
            else:
                problem = (
                    _sigma_seam_problem(o, rule_formulas or {}, states)
                    if states is not None
                    else None
                )
                if problem:
                    problems.append(f"{where}: {problem}")
        sc = o.get("scaling") or {}
        if isinstance(sc, dict) and sc and sc.get("mode", "none") not in _SCALING_MODES:
            problems.append(f"{where}: scaling.mode must be one of {_SCALING_MODES}")
        if isinstance(sc, dict) and sc:
            problems += _scaling_shape_problems(where, sc)
    problems += _scaling_group_problems(obs)
    return problems


def _sigma_seam_problem(o: dict, rules: dict[str, str], states: set[str]) -> str | None:
    """`sigma_state_problem` on the agent's own formula and noise formula,
    rules expanded, on the workflow's rule (the formula is its own `core`); a
    scaling stem such as `sc_obs_x` is an ordinary symbol here. The caller's
    prefix names the observable. A rule set that cannot expand is the merge's
    to report."""
    formula = str(o.get("formula", ""))
    noise = str((o.get("noise") or {}).get("formula", ""))
    try:
        formula, noise = expand_rules(formula, rules), expand_rules(noise, rules)
    except ValueError:
        return None
    return sigma_state_problem(noise, formula, states, rules=set(rules), core=formula)


def _assembled_cores(ctx: RunContext, sbml: str) -> dict[str, str] | None:
    """Each observable's own formula as the agent wrote it, rules expanded,
    read from the assembly the merge wrote these tables from (`ctx.work /
    "assembly"`); None when there is none. A formula whose rules cannot expand
    is left out: the merge reports it."""
    assembly = (ctx.work / "assembly").get(None)
    if not isinstance(assembly, dict):
        return None
    rules = _model_summary(sbml)["assignment_rule_formulas"]
    cores: dict[str, str] = {}
    for o in assembly.get("observables") or []:
        if not isinstance(o, dict) or not o.get("observable_id"):
            continue
        try:
            cores[str(o["observable_id"])] = expand_rules(
                str(o.get("formula", "")), rules
            )
        except ValueError:
            continue
    return cores


def _scaling_shape_problems(where: str, sc: dict) -> list[str]:
    """The three fields a per-timepoint / per-condition factor needs, each
    refused by name so the re-ask says what to change."""
    out = []
    per = sc.get("per", "observable") or "observable"
    if per not in SCALING_PER:
        out.append(f"{where}: scaling.per must be one of {SCALING_PER}, not {per!r}")
    shared = sc.get("shared_across_observables", False)
    if shared not in (False, None) and not (isinstance(shared, str) and shared.strip()):
        out.append(
            f"{where}: scaling.shared_across_observables is false or a GROUP "
            f"NAME shared by every observable that declares it"
        )
    if sc.get("pin_first_to_one") and per == "observable":
        out.append(
            f"{where}: scaling.pin_first_to_one needs per=timepoint or "
            f"per=condition — one factor has no 'first' to pin"
        )
    if per != "observable" and str(sc.get("mode", "none")) == "none":
        out.append(
            f"{where}: scaling.per={per!r} declares a factor; mode is 'none'. "
            f"Use mode 'factor' (or 'factor_offset')"
        )
    return out


def _scaling_group_problems(observables: list) -> list[str]:
    """Observables sharing one parameter SET must agree on how it is indexed."""
    groups: dict[str, list[tuple[str, dict]]] = {}
    for o in observables:
        sc = o.get("scaling") if isinstance(o, dict) else None
        if isinstance(sc, dict) and isinstance(
            sc.get("shared_across_observables"), str
        ):
            groups.setdefault(sc["shared_across_observables"], []).append(
                (str(o.get("observable_id")), sc)
            )
    out = []
    for group, members in groups.items():
        for key in ("per", "mode", "pin_first_to_one"):
            vals = {
                repr(sc.get(key, "observable" if key == "per" else None))
                for _, sc in members
            }
            if len(vals) > 1:
                out.append(
                    f"scaling group {group!r}: its members disagree on {key} "
                    f"({', '.join(sorted(vals))}) — one parameter set needs one shape"
                )
        stems = {
            sc.get("scale_parameter") for _, sc in members if sc.get("scale_parameter")
        }
        if len(stems) > 1:
            out.append(
                f"scaling group {group!r}: members name different scale_parameter "
                f"stems {sorted(stems)}; name one (or none, and the engine uses sc_{group})"
            )
    return out


def split_observation_reply(reply: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """The merged reply -> the assembly's three observation blocks, in the
    shapes the merge renderer, assembly_edit, S11 moves, overlays and
    `decisions_md` read. The single rationale lives with the observable; the
    noise and scaling entries point at it."""
    obs_block, noise_block, scaling_block = [], [], []
    for o in reply["observables"]:
        oid = str(o["observable_id"])
        rationale = str(o.get("rationale", ""))
        noise = o.get("noise") or {}
        sc = o.get("scaling") or {"mode": "none"}
        obs_block.append(
            {
                "observable_id": oid,
                "maps_to_label": o.get("maps_to_label"),
                "formula": str(o.get("formula")),
                "transformation": o.get("transformation", "lin"),
                "rationale": rationale,
            }
        )
        noise_block.append(
            {
                "observable_id": oid,
                "distribution": noise.get("distribution", "normal"),
                "formula": str(noise.get("formula", f"sigma_{oid}")),
                "estimate_sigma": bool(noise.get("estimate_sigma", True)),
                # what the sigma is indexed by (`observable` | `condition`)
                "per": str(noise.get("per") or "observable"),
                "rationale": "(argued with the observable's rationale — one observation function)",
            }
        )
        mode = sc.get("mode", "none") or "none"
        shared_obs = sc.get("shared_across_observables", False) or False
        # `per` is what the factor is indexed by; `shared_across_conditions:
        # false` is read as `per: condition`
        per = sc.get("per") or (
            "condition"
            if sc.get("shared_across_conditions", True) is False
            else "observable"
        )
        scaling_block.append(
            {
                "observable_id": oid,
                "mode": mode,
                "scale_parameter": (
                    sc.get("scale_parameter")
                    or (
                        f"sc_{shared_obs or oid}"
                        if mode in ("factor", "factor_offset")
                        else None
                    )
                ),
                "offset_parameter": (
                    sc.get("offset_parameter")
                    or (f"off_{oid}" if mode in ("factor_offset", "offset") else None)
                ),
                "per": str(per),
                "shared_across_observables": shared_obs,
                "pin_first_to_one": bool(sc.get("pin_first_to_one", False)),
                "shared_across_conditions": per != "condition",
                "rationale": "(argued with the observable's rationale — one observation function)",
            }
        )
    return obs_block, noise_block, scaling_block


def _glossary(ctx: RunContext) -> dict:
    """The builder's entity glossary: what each species denotes, its unit
    convention, what it lumps — the intent that ids and formulas alone do not
    carry. Read from the candidate's model, then the round's; absent, an
    explicit statement rather than a silent empty dict."""
    for model in (ctx.model, ctx.round / "model"):
        node = model / "glossary"
        if node.exists():
            gl = node.get()
            if gl.get("species") or gl.get("parameters"):
                return gl
    ctx.ledger.append(
        "note",
        module="assembly",
        round_idx=ctx.round_idx,
        note="no entity glossary — assembly maps from structure alone",
    )
    return {
        "note": "no glossary supplied for this model — map from the model "
        "structure and the experiment description alone, and say so "
        "in your rationale where the mapping is a guess",
        "species": [],
        "parameters": [],
    }


def _model_summary(sbml: str) -> dict:
    import libsbml

    m = libsbml.readSBMLFromString(sbml).getModel()
    return {
        "species": [m.getSpecies(i).getId() for i in range(m.getNumSpecies())],
        "parameters": [m.getParameter(i).getId() for i in range(m.getNumParameters())],
        # variables defined by assignment rule, and their formulas. An agent may
        # name them in any formula; the merge expands them in the observable and
        # noise formulas it writes, because AMICI can compile a state-dependent
        # sigma only when it can solve the observable's own formula for that
        # state, and a rule symbol left in a sigma is an undeclared identifier
        # in the generated C++
        "assignment_rules": [
            m.getRule(i).getVariable()
            for i in range(m.getNumRules())
            if m.getRule(i).isAssignment()
        ],
        "assignment_rule_formulas": _rule_formulas(m),
        "reactions": [
            {
                "id": m.getReaction(i).getId(),
                "formula": (
                    libsbml.formulaToString(m.getReaction(i).getKineticLaw().getMath())
                    if m.getReaction(i).getKineticLaw()
                    else ""
                ),
            }
            for i in range(m.getNumReactions())
        ],
    }


def _rule_formulas(m) -> dict[str, str]:
    """{variable: formula} for every assignment rule of a libsbml model, in the
    infix spelling PEtab formulas use (`^`, `ln`). Function definitions are
    inlined and numbers carry no units: the formula is pasted into a PEtab
    formula, where neither exists."""
    import libsbml

    settings = libsbml.L3ParserSettings()
    settings.setParseUnits(False)
    fds = m.getListOfFunctionDefinitions()
    out: dict[str, str] = {}
    for i in range(m.getNumRules()):
        rule = m.getRule(i)
        if not rule.isAssignment() or rule.getMath() is None:
            continue
        math = rule.getMath().deepCopy()
        if fds.size():
            libsbml.SBMLTransforms.replaceFD(math, fds)
        out[rule.getVariable()] = libsbml.formulaToL3StringWithSettings(math, settings)
    return out


# ---------------------------------------------------------------- the merge


# the id of the conditions row a measured condition is pre-equilibrated from
PREEQ_PREFIX = "preeq_"


def _floating_species(sbml: str) -> set[str]:
    """Species with a state: the ones a pre-equilibration carries over."""
    import libsbml

    m = libsbml.readSBMLFromString(sbml).getModel()
    return {
        m.getSpecies(i).getId()
        for i in range(m.getNumSpecies())
        if not m.getSpecies(i).getBoundaryCondition()
    }


def _record_rendered_preequilibration(
    ctx: RunContext, rendered: list[dict], sbml: str
) -> None:
    """Say which conditions pre-equilibrate, from which row, with what changed.

    Ledgered once per merge and printed on the compile card
    (`battery_feedback` reads the row). A species the measured condition sets
    is re-initialised after pre-equilibration (PEtab v1), which is how a
    stimulus written as an initial amount enters at t=0; the line names them,
    because every other species starts from the steady state."""
    if not rendered:
        return
    species = _floating_species(sbml)
    for r in rendered:
        r["reinitialised"] = sorted(set(r.pop("own")) & species)

    def _fmt(v) -> str:
        if v is None:
            return "model value"
        return f"{v:g}" if isinstance(v, float) else str(v)

    parts = []
    for r in rendered[:4]:
        changed = ", ".join(
            f"{k} {_fmt(a)} -> {_fmt(b)}" for k, (a, b) in r["changed"].items()
        )
        parts.append(
            f"{r['condition']} from {r['preequilibration_condition']} "
            f"({changed or 'no override changed'})"
            + (
                f", re-set at t=0: {', '.join(r['reinitialised'])}"
                if r["reinitialised"]
                else ""
            )
        )
    line = (
        f"pre-equilibration rendered for {len(rendered)} condition(s): "
        + "; ".join(parts)
        + (f"; … and {len(rendered) - 4} more" if len(rendered) > 4 else "")
        + " — each starts from the steady state of its pre-eq row "
        "(assembly_preequilibration screens that it settles)"
    )
    print(f"  ⚑ {line}")
    ctx.ledger.append(
        "note",
        module="assembly",
        round_idx=ctx.round_idx,
        candidate=ctx.candidate,
        note=line,
        preequilibration_rendered=rendered,
    )


def _merge_to_petab(
    ctx: RunContext, assembly: dict, sbml: str, long_df: pd.DataFrame, petab
) -> None:
    """Deterministic: agents decided, code renders — into the unit of work's
    `petab` group (`ctx.work / "petab"`). Seam mismatches surface here as
    MergeRefusal (routed like a T0 check), ModuleFailure, or downstream in the
    battery — by design."""
    spec = ctx.spec
    noise_by_obs = {n["observable_id"]: n for n in assembly["noise"]}
    scaling_by_obs = {s["observable_id"]: s for s in assembly["scaling"]}
    # which conditions are HELD OUT, needed while rendering a per-condition
    # sigma (a held-out condition's sigma has no training row to fit it). The
    # same rule the split at the bottom applies, computed once on labels/keys.
    hold_cond_ids = _holdout_condition_ids(ctx, assembly, long_df)

    # observables — noise goes through the canonical PEtab placeholder
    # (noiseParameter1_<obs> + a noiseParameters column): the amici 1.0
    # importer maps a bare parameter id in noiseFormula to sigma=0 silently.
    obs_rows = []
    extra_params: list[dict] = []
    noise_override: dict[str, str | None] = {}  # observableId -> noiseParameters value
    per_row_sigma_obs: set[str] = (
        set()
    )  # observables whose sigma is per row, from the data
    # observableId -> the placeholders in formula order, each either one id for
    # every row or an id PER ROW keyed by time tag / condition id
    obs_placeholders: dict[str, list[tuple[str, dict[str, str]]]] = {}
    scaling_ids_by_obs: dict[str, list[str]] = {}  # the ESTIMATED factor ids
    summary = _model_summary(sbml)
    model_ents = set(summary["species"]) | set(summary["parameters"])
    rule_formulas = summary["assignment_rule_formulas"]
    sigma_states = set(summary["species"]) - set(rule_formulas)
    n_obs_expanded = n_noise_expanded = 0
    rules_named: set[str] = set()
    for o in assembly["observables"]:
        oid = o["observable_id"]
        if oid not in noise_by_obs:
            raise MergeRefusal(
                f"seam mismatch: noise model missing for {oid}",
                gate_id="assembly_merge_noise",
            )
        formula = str(o["formula"])
        sc = scaling_by_obs.get(oid, {"mode": "none"})
        assembly_pars: set[str] = set()
        placeholder_map: dict[str, str] = {}
        # Scaling and offset always go through PEtab observable-parameter
        # placeholders (ids in `observableParameters`), like sigma: pyPESTO's
        # hierarchical inner problem sees only these override columns.
        placeholders: list[tuple[str, dict[str, str]]] = []
        if sc["mode"] in ("factor", "factor_offset"):
            # ONE placeholder whatever `per` says; each measurement ROW names
            # its real parameter (`sc_<stem>`, `sc_<stem>_t60` by time, or
            # `sc_<stem>_<cond>` by condition) in observableParameters.
            per = str(sc.get("per") or "observable")
            stem = (
                sc.get("scale_parameter")
                or f"sc_{sc.get('shared_across_observables') or oid}"
            )
            ids_by_key, first_key = _scaling_ids(per, stem, oid, assembly, long_df)
            placeholders.append((per, ids_by_key))
            formula = f"observableParameter{len(placeholders)}_{oid} * ({formula})"
            placeholder_map[stem] = f"observableParameter{len(placeholders)}_{oid}"
            estimated: list[str] = []
            for key, sid in ids_by_key.items():
                pinned = bool(sc.get("pin_first_to_one")) and key == first_key
                # the absolute scale is pinned EITHER by a fixed model total (the
                # contract's other option) or by this: the first factor fixed at 1
                extra_params.append(
                    _scale_param_row(sid, spec, estimate=0 if pinned else 1)
                )
                if not pinned:
                    estimated.append(sid)
            scaling_ids_by_obs[oid] = estimated
            assembly_pars.add(stem)
            assembly_pars.update(ids_by_key.values())
        if sc["mode"] in ("factor_offset", "offset"):
            off_par = sc.get("offset_parameter") or f"off_{oid}"
            placeholders.append(("observable", {"__const__": off_par}))
            formula = f"{formula} + observableParameter{len(placeholders)}_{oid}"
            placeholder_map[off_par] = f"observableParameter{len(placeholders)}_{oid}"
            extra_params.append(_offset_param_row(off_par, spec))
            assembly_pars.add(off_par)
        obs_placeholders[oid] = placeholders
        noise = noise_by_obs[oid]
        # a per-row sigma that came WITH the data (S2 `error_column`) IS the
        # noise model: fixed, one number per row in `noiseParameters` below;
        # the agent's noise formula is then not rendered
        lab_of_oid = next(
            (
                str(o.get("maps_to_label"))
                for o in assembly["observables"]
                if str(o.get("observable_id")) == str(oid)
            ),
            None,
        )
        _rows_of = (
            long_df["observable_label"].astype(str) == lab_of_oid
            if lab_of_oid is not None
            else pd.Series(False, index=long_df.index)
        )
        data_sigma = (
            "sigma" in long_df.columns
            and bool(_rows_of.any())
            and bool(long_df.loc[_rows_of, "sigma"].notna().all())
        )
        if data_sigma:
            noise_formula = f"noiseParameter1_{oid}"
            override = None
            per_row_sigma_obs.add(str(oid))
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=f"{oid}: noise fixed per row from the data's error column "
                f"(S2 error_type=column); the agent's noise formula "
                f"{str(noise.get('formula'))!r} is not rendered",
            )
        else:
            if str(noise.get("formula", "")).strip().lower() in ("from_data", "data"):
                raise MergeRefusal(
                    f"{oid}: noise formula 'from_data' but the measurement table "
                    f"carries no per-row sigma for label {lab_of_oid!r} — declare an "
                    f"`error_column` at data extraction, or give a noise formula",
                    gate_id="assembly_merge_noise",
                )
            sigma_ids, noise_formula, override = _render_noise(
                str(noise["formula"]),
                oid,
                model_ents,
                assembly_pars,
                max_components=int(
                    spec.require("assembly_defaults.max_noise_components")
                ),
                placeholder_map=placeholder_map,
            )
            per_noise = str(noise.get("per") or "observable")
            if per_noise == "condition" and sigma_ids:
                # One sigma SET per condition, named per row in noiseParameters;
                # none for a HELD-OUT condition (nothing in training fits it and
                # petablint refuses it), so resolving one fails loudly.
                conds = _conditions_measured(oid, assembly, long_df)
                per_row: dict[str, str] = {}
                n_estimated = 0
                for cid in conds:
                    ids = [f"{sid}_{cid}" for sid in sigma_ids]
                    per_row[cid] = ";".join(ids)
                    if cid in hold_cond_ids:
                        continue
                    for sid in ids:
                        row = _sigma_param_row(sid, spec)
                        if not noise.get("estimate_sigma"):
                            row["estimate"] = 0
                        else:
                            n_estimated += 1
                        extra_params.append(row)
                override = per_row
                ctx.ledger.append(
                    "note",
                    module="assembly",
                    round_idx=ctx.round_idx,
                    note=(
                        f"per-condition sigma on {oid}: {sigma_ids} x "
                        f"{len(conds)} condition(s) -> {n_estimated} estimated sigma "
                        f"parameter(s), each counted in k"
                        + (
                            f"; held-out {sorted(set(conds) & hold_cond_ids)}: no "
                            f"sigma parameter (nothing in training would fit it; "
                            f"T2' compares against the replicate floor)"
                            if set(conds) & hold_cond_ids
                            else ""
                        )
                    ),
                    noise_per_condition=True,
                    observable=oid,
                    sigma_parameters=[per_row[c] for c in conds],
                )
            elif noise.get("estimate_sigma"):
                # one row per component. Two-component noise needs both the
                # floor and the slope estimated, and a missing row is not a
                # degraded fit — PEtab cannot resolve the placeholder at all.
                for sid in sigma_ids:
                    extra_params.append(_sigma_param_row(sid, spec))
            elif sigma_ids:
                # a bare id with estimate_sigma=false would be undeclared and
                # surface only as petablint "Missing parameter(s)". A FIXED
                # sigma is a number, or it comes from the data; refuse here.
                raise MergeRefusal(
                    f"{oid}: noise formula {str(noise['formula'])!r} names "
                    f"{sigma_ids} with estimate_sigma=false — a fixed sigma must "
                    f"be a number (e.g. '0.05') or come from the data's error "
                    f"column (S2 `error_column`); an undeclared parameter cannot "
                    f"be fixed",
                    gate_id="assembly_merge_noise",
                )
        noise_override[oid] = override
        # Assignment-rule symbols are expanded into their formulas in BOTH
        # formulas, so the written table never carries a rule id: AMICI
        # expresses a state-dependent sigma through the observable's own
        # prediction, which it can do only when the observable is written in
        # the same species, and a rule symbol left in a sigma fails its C++
        # build. Counted here, ledgered once below.
        try:
            expanded = expand_rules(formula, rule_formulas)
            expanded_noise = expand_rules(noise_formula, rule_formulas)
            # the agent's own formula, before its gain and offset: the one a
            # sigma may reach the model through
            core = expand_rules(str(o["formula"]), rule_formulas)
        except ValueError as e:
            raise ModuleFailure(f"observable {oid}: {e}") from e
        rules_named |= (symbols(formula) | symbols(noise_formula)) & set(rule_formulas)
        n_obs_expanded += expanded != formula
        n_noise_expanded += expanded_noise != noise_formula
        formula, noise_formula = expanded, expanded_noise
        # AMICI-safe spelling of both formulas: `log2(x)` passes Antimony,
        # roadrunner and petablint but not AMICI's compiler. Ledgered when it
        # changes anything; an unknown function is refused by name.
        from octomod.workflow_modules.assembly.assembly_edit import (
            amici_safe_formula as _safe,
        )

        try:
            safe_formula = _safe(formula)
            safe_noise = _safe(noise_formula)
        except ValueError as e:
            raise MergeRefusal(
                f"observable {oid}: {e}", gate_id="assembly_merge_observables"
            ) from e
        if safe_formula != formula or safe_noise != noise_formula:
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=(
                    f"formula normalised for AMICI on {oid}: "
                    f"{formula!r} -> {safe_formula!r}"
                    + (
                        f"; noise {noise_formula!r} -> {safe_noise!r}"
                        if safe_noise != noise_formula
                        else ""
                    )
                ),
                observable=oid,
            )
            formula, noise_formula = safe_formula, safe_noise
        # the belt for the seam check: the rows exactly as AMICI will read them
        problem = sigma_state_problem(
            noise_formula,
            formula,
            sigma_states,
            rules=set(rule_formulas),
            obs_id=oid,
            core=core,
        )
        if problem:
            raise MergeRefusal(problem, gate_id="assembly_merge_noise")
        obs_rows.append(
            {
                "observableId": oid,
                "observableFormula": formula,
                "observableTransformation": o.get("transformation", "lin"),
                "noiseFormula": noise_formula,
                "noiseDistribution": noise["distribution"],
            }
        )
    if n_obs_expanded or n_noise_expanded:
        named = sorted(rules_named)
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            candidate=ctx.candidate,
            note=(
                f"assignment-rule symbols expanded in {n_obs_expanded} observable "
                f"and {n_noise_expanded} noise formulas for the compile: "
                + ", ".join(named[:8])
                + (f" … and {len(named) - 8} more" if len(named) > 8 else "")
            ),
            rules_expanded=named,
        )
    obs_df = pd.DataFrame(obs_rows)

    # conditions
    cond_rows = []
    # an override is a NUMBER (the condition fixes that quantity) or a
    # PARAMETER ID (the condition gets its own estimated copy of the model
    # parameter — PEtab's own mechanism, `STAT1_tot -> STAT1_tot_Bcell`)
    id_overrides: dict[str, str] = {}  # new parameter id -> model parameter copied
    id_keys: set[str] = set()
    numeric_keys: set[str] = set()

    def _condition_row(cid: str, overrides: dict) -> dict:
        row = {"conditionId": cid}
        for k, v in overrides.items():
            val = _override_value(v)
            if isinstance(val, str):
                if val == k:
                    raise MergeRefusal(
                        f"condition {cid}: override {k!r} -> {val!r} "
                        f"names the parameter itself; a parameter-valued override "
                        f"must name a NEW id (e.g. {k}_<level>)",
                        gate_id="assembly_merge_conditions",
                    )
                prev = id_overrides.get(val)
                if prev is not None and prev != k:
                    raise MergeRefusal(
                        f"override id {val!r} is used for both {prev!r} and {k!r}",
                        gate_id="assembly_merge_conditions",
                    )
                id_overrides[val] = k
                id_keys.add(k)
            else:
                numeric_keys.add(k)
            row[k] = val
        return row

    # A pre-equilibrated condition gets a second row: a copy of its own with
    # the declared pre-equilibration overrides on top (a parameter id stays
    # the same id, so the steady state is the same group's), named
    # `preeq_<condition>` in the measurements' preequilibrationConditionId.
    measured_ids = {str(c["condition_id"]) for c in assembly["conditions"]}
    preeq_of: dict[str, str] = {}  # measured condition id -> its pre-eq row id
    preeq_rendered: list[dict] = []
    for c in assembly["conditions"]:
        cid = str(c["condition_id"])
        own = dict(c.get("overrides") or {})
        cond_rows.append(_condition_row(cid, own))
        try:
            pre = preequilibration_overrides(c.get("preequilibration"))
        except ValueError as e:
            raise MergeRefusal(
                f"condition {cid}: {e}", gate_id="assembly_merge_conditions"
            ) from e
        if pre is None:
            continue
        pre_id = f"{PREEQ_PREFIX}{cid}"
        if pre_id in measured_ids:
            raise MergeRefusal(
                f"condition {cid}: its pre-equilibration condition is named "
                f"{pre_id!r}, which is already a measured condition's id — "
                f"rename that condition",
                gate_id="assembly_merge_conditions",
            )
        cond_rows.append(_condition_row(pre_id, {**own, **pre}))
        preeq_of[cid] = pre_id
        preeq_rendered.append(
            {
                "condition": cid,
                "preequilibration_condition": pre_id,
                "changed": {
                    k: [
                        _override_value(own[k]) if k in own else None,
                        v,
                    ]
                    for k, v in pre.items()
                    if k not in own or _override_value(own[k]) != v
                },
                "own": sorted(own),
            }
        )
    # PEtab reads a blank condition cell as the model's value, so an estimated
    # parameter overridden in only some conditions would read its nominal
    # there: refused. A fixed one is written out.
    split_by_id = {p["id"]: p for p in (ctx.model / "parameters").get()}
    for k in sorted(id_keys):
        blank = [r["conditionId"] for r in cond_rows if k not in r]
        if not blank or k not in split_by_id:
            continue  # a non-parameter key is refused by name below
        if split_by_id[k].get("estimate"):
            raise MergeRefusal(
                f"override {k!r} is split into per-condition copies in some "
                f"conditions only, and {k!r} is ESTIMATED: the conditions without "
                f"a copy ({blank[:4]}{' …' if len(blank) > 4 else ''}) would read "
                f"its nominal value, not its estimate (a blank PEtab condition "
                f"cell is the model's value) — give every condition its own id, "
                f"or split a fixed parameter",
                gate_id="assembly_merge_conditions",
            )
        for r in cond_rows:
            if k not in r:
                r[k] = float(split_by_id[k]["nominal_value"])
        numeric_keys.add(k)
    numeric_only_keys = numeric_keys - id_keys
    cond_df = pd.DataFrame(cond_rows).fillna(np.nan)
    if (
        "conditionId" not in cond_df.columns
        or cond_df["conditionId"].duplicated().any()
    ):
        raise MergeRefusal(
            "condition encoding produced missing/duplicate condition ids",
            gate_id="assembly_merge_conditions",
        )

    # parameters — dynamic parameters from S1 + assembly-created ones. A
    # condition-table-controlled parameter must NOT appear in the parameter
    # table: a PEtab rule the engine enforces rather than the agents.
    condition_controlled = set(cond_df.columns) - {"conditionId", "conditionName"}
    dyn_params = (ctx.model / "parameters").get()
    # a parameter split into per-condition copies IS estimated — through
    # its copies — so the estimate/condition conflict applies to numeric-only
    # overrides
    conflict = [
        p["id"]
        for p in dyn_params
        if p["id"] in numeric_only_keys and p.get("estimate")
    ]
    if conflict:
        raise MergeRefusal(
            f"parameters {conflict} are condition-controlled AND marked for "
            f"estimation — pick one: estimate it (remove from conditions) or "
            f"let conditions set it (estimate: false)",
            gate_id="assembly_merge_conditions",
        )
    dropped = [p["id"] for p in dyn_params if p["id"] in condition_controlled]
    if dropped:
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=f"kept condition-controlled parameters out of the "
            f"parameter table (PEtab rule): {dropped}",
        )
    par_rows = [
        _dynamic_param_row(p) for p in dyn_params if p["id"] not in condition_controlled
    ]
    seen = {r["parameterId"] for r in par_rows}
    # one parameter row per override id, inheriting scale, bounds, nominal and
    # the estimate flag from the model parameter it copies
    by_id = {p["id"]: p for p in dyn_params}
    declared_copies: list[str] = []
    for new_id, base in sorted(id_overrides.items()):
        if base not in by_id:
            raise MergeRefusal(
                f"override id {new_id!r} copies {base!r}, which is not a model "
                f"parameter with a nominal value (the model's `parameters`) — species and "
                f"assembly-created parameters cannot be split per condition",
                gate_id="assembly_merge_conditions",
            )
        own = by_id.get(new_id)
        if own is not None and own.get("layer") == "assembly":
            # an observation axis DECLARED this copy, and its own row (bounds,
            # estimate flag) is already in the table; copying the overridden
            # parameter's row would inherit ITS estimate flag instead
            if new_id in model_ents:
                raise MergeRefusal(
                    f"override id {new_id!r} collides with a model entity",
                    gate_id="assembly_merge_conditions",
                )
            declared_copies.append(new_id)
            continue
        if new_id in model_ents or new_id in seen:
            raise MergeRefusal(
                f"override id {new_id!r} collides with an existing model entity "
                f"or parameter",
                gate_id="assembly_merge_conditions",
            )
        par_rows.append(_dynamic_param_row({**by_id[base], "id": new_id}))
        seen.add(new_id)
    if id_overrides:
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=f"{len(id_overrides)} per-condition parameter copies "
            f"created from {sorted(id_keys)}: {sorted(id_overrides)}"
            + (
                f"; declared by an observation axis, with their own rows: "
                f"{declared_copies}"
                if declared_copies
                else ""
            ),
        )
    for r in extra_params:
        if r["parameterId"] not in seen:
            par_rows.append(r)
            seen.add(r["parameterId"])
    par_df = pd.DataFrame(par_rows)

    # which observation parameters pyPESTO may solve analytically, marked in
    # the TABLE so `build_problem` reads it off the problem rather than from a
    # flag that could disagree; the parameter table is outside the compile key
    from octomod.workflow_modules.assembly import hierarchical as _hier

    hier_marks, hier_reasons = _hier.marks(
        assembly, spec, scaling_ids=scaling_ids_by_obs
    )
    if hier_marks:
        par_df["parameterType"] = [
            hier_marks.get(str(pid), "") for pid in par_df["parameterId"]
        ]

    # measurements (training) + holdout_measurements
    # observables must PARTITION the data labels: with two observables on one
    # label, the label -> observable dict below would keep only the last
    _by_lab: dict[str, list[str]] = {}
    for o in assembly["observables"]:
        _by_lab.setdefault(str(o["maps_to_label"]), []).append(str(o["observable_id"]))
    _dups = {k: v for k, v in _by_lab.items() if len(v) > 1}
    if _dups:
        raise MergeRefusal(
            f"observables map many-to-one onto data labels: {_dups} — every "
            f"observable needs its own data label (a long-format file needs "
            f"`observable_column` at data extraction, not a condition column)",
            gate_id="assembly_merge_observables",
        )
    obs_by_label = {
        o["maps_to_label"]: o["observable_id"] for o in assembly["observables"]
    }
    cond_by_label = {
        c["maps_to_label"]: c["condition_id"] for c in assembly["conditions"]
    }
    missing_obs = set(long_df["observable_label"]) - set(obs_by_label)
    missing_cond = set(long_df["condition_label"]) - set(cond_by_label)
    if missing_obs or missing_cond:
        raise ModuleFailure(
            f"seam mismatch: unmapped observable labels {sorted(missing_obs)}; "
            f"unmapped condition labels {sorted(missing_cond)}"
        )

    meas_df = pd.DataFrame(
        {
            "observableId": long_df["observable_label"].map(obs_by_label),
            "simulationConditionId": long_df["condition_label"].map(cond_by_label),
            "measurement": long_df["value"],
            "time": long_df["time"],
        }
    )
    if preeq_of:
        # every row of a pre-equilibrated condition names its pre-eq row; a
        # blank cell is PEtab's "none", so the other conditions start from the
        # model's initial values
        meas_df.insert(
            2,
            "preequilibrationConditionId",
            meas_df["simulationConditionId"].astype(str).map(preeq_of),
        )
    # per row: a shared sigma is one string for the observable; a per-condition
    # sigma is a mapping condition id -> that condition's parameter names
    meas_df["noiseParameters"] = [
        _noise_parameters_for(noise_override.get(str(oid)), cid)
        for oid, cid in zip(
            meas_df["observableId"], meas_df["simulationConditionId"], strict=False
        )
    ]
    if per_row_sigma_obs:
        # the data's own sigma, row by row, for the observables that carry one
        # (meas_df is built from long_df's columns, so positions align)
        mask = meas_df["observableId"].astype(str).isin(per_row_sigma_obs).to_numpy()
        sig = long_df["sigma"].to_numpy()
        # copy=True: under pandas copy-on-write `.to_numpy()` may hand back a
        # read-only view, and the assignment below would raise
        # "assignment destination is read-only"
        vals = meas_df["noiseParameters"].astype(object).to_numpy(copy=True)
        vals[mask] = [f"{float(s):g}" for s in sig[mask]]
        meas_df["noiseParameters"] = vals
    if any(obs_placeholders.values()):
        meas_df["observableParameters"] = [
            _observable_parameters_for(obs_placeholders.get(str(oid), []), t, cid)
            for oid, t, cid in zip(
                meas_df["observableId"],
                meas_df["time"],
                meas_df["simulationConditionId"],
                strict=False,
            )
        ]

    for reason in hier_reasons:
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=f"hierarchical estimation: {reason}",
        )
    if hier_marks:
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=(
                f"hierarchical estimation ON — {hier_marks} solved "
                f"analytically per outer step; they remain ESTIMATED parameters "
                f"and still count in k"
            ),
        )
    # Holdout split on semantic condition KEYS (data column vocabulary), never
    # on display labels — see data.condition_key. Row-aligned with long_df.
    holdout_labels = ctx.testcase.get("holdout", {}).get("condition_labels", [])
    if "condition_key" not in long_df.columns:
        raise ModuleFailure(
            f"{(ctx.round / 'data/measurements').key} lacks condition_key — "
            "produced by an older S2; re-run S2"
        )
    row_keys = long_df["condition_key"].fillna("")
    is_hold = pd.Series(False, index=long_df.index)
    for h in holdout_labels:
        k = parse_declared_label(h)
        hit = long_df["condition_label"] == h
        if k:
            hit |= row_keys == k
        if not hit.any():
            raise ModuleFailure(
                f"declared holdout {h!r} matches no measurement rows "
                f"(keys present: {sorted(set(row_keys))})"
            )
        is_hold |= hit
    train_df, hold_df = meas_df[~is_hold], meas_df[is_hold]
    if len(train_df) == 0:
        raise ModuleFailure("holdout split left zero training measurements")

    (ctx.model / "sbml").put_text(sbml)  # ensure present
    # the yaml names the tables the way `petab_io.export_dir` writes them
    inp = petab_io.PetabInput(
        sbml=sbml,
        observables=obs_df,
        conditions=cond_df,
        measurements=train_df,
        parameters=par_df,
        holdout=hold_df,
        problem_yaml={
            "format_version": 1,
            "parameter_file": "parameters.tsv",
            "problems": [
                {
                    "sbml_files": ["model.xml"],
                    "condition_files": ["conditions.tsv"],
                    "measurement_files": ["measurements.tsv"],
                    "observable_files": ["observables.tsv"],
                }
            ],
        },
    )
    petab_io.to_record(inp, petab)
    n_obs_written = len(obs_df)
    if any(per == "timepoint" for phs in obs_placeholders.values() for per, _ in phs):
        # AMICI refuses timepoint-specific overrides; PEtab's remedy splits the
        # observable per override group. Ledgered, because downstream tables
        # carry the flattened ids and `observableName` the assembly's own.
        # Flattened from the tables as stored (held-out measurements included)
        # and written back.
        from octomod.orchestration.artifacts import flatten_timepoint_specific

        flat_inp, flat = flatten_timepoint_specific(
            petab_io.from_record(petab, sbml=sbml)
        )
        if flat is not None:
            petab_io.to_record(flat_inp, petab)
            n_obs_written = flat["n_after"]
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=(
                    f"per-timepoint scaling declared; problem flattened for "
                    f"AMICI ({flat['n_before']} observables -> {flat['n_after']}); "
                    f"observableName carries the assembly's observable id"
                ),
                flattened=flat["renamed"],
            )
    _record_rendered_preequilibration(ctx, preeq_rendered, sbml)
    ctx.ledger.append(
        "artifact",
        module="assembly",
        round_idx=ctx.round_idx,
        artifact=petab.key,
        n_obs=n_obs_written,
        n_cond=len(cond_df),
        n_train=len(train_df),
        n_holdout=len(hold_df),
    )


def _time_tag(t) -> str:
    """`60.0` -> `t60`, `0.5` -> `t0p5`, `-1` -> `tm1`: a parameter-id-safe time."""
    return "t" + f"{float(t):g}".replace("-", "m").replace(".", "p")


def _scaling_ids(
    per: str, stem: str, oid: str, assembly: dict, long_df: pd.DataFrame
) -> tuple[dict[str, str], str | None]:
    """The real parameter id behind the scale placeholder, per ROW KEY.

    `observable`: {"__const__": stem}. `timepoint`: one id per distinct
    measurement time over the rows of this observable — or of every observable
    in its shared group, so the group's set covers every time any member is
    measured at — keyed by time tag. `condition`: one per condition id the
    group is measured under. Also returns the FIRST key (earliest time / first
    condition in assembly order), which `pin_first_to_one` fixes at 1.
    """
    if per == "observable":
        return {"__const__": stem}, "__const__"
    sc_by = {s["observable_id"]: s for s in assembly.get("scaling", [])}
    group = sc_by.get(oid, {}).get("shared_across_observables")
    members = (
        [
            o
            for o in assembly["observables"]
            if sc_by.get(o["observable_id"], {}).get("shared_across_observables")
            == group
        ]
        if group
        else [o for o in assembly["observables"] if o["observable_id"] == oid]
    )
    labels = {str(o.get("maps_to_label")) for o in members}
    rows = long_df[long_df["observable_label"].astype(str).isin(labels)]
    if per == "timepoint":
        times = sorted({float(t) for t in rows["time"]})
        ids = {_time_tag(t): f"{stem}_{_time_tag(t)}" for t in times}
        return ids, (_time_tag(times[0]) if times else None)
    cond_by_label = {
        c["maps_to_label"]: c["condition_id"] for c in assembly.get("conditions", [])
    }
    present = {cond_by_label.get(lbl) for lbl in rows["condition_label"].astype(str)}
    ordered = [
        c["condition_id"]
        for c in assembly.get("conditions", [])
        if c["condition_id"] in present
    ]
    ids = {cid: f"{stem}_{cid}" for cid in ordered}
    return ids, (ordered[0] if ordered else None)


def _conditions_measured(oid: str, assembly: dict, long_df: pd.DataFrame) -> list[str]:
    """Condition ids this observable has measurement rows in, in assembly order."""
    label = next(
        (
            str(o.get("maps_to_label"))
            for o in assembly["observables"]
            if o["observable_id"] == oid
        ),
        None,
    )
    rows = long_df[long_df["observable_label"].astype(str) == label]
    cond_by_label = {
        c["maps_to_label"]: c["condition_id"] for c in assembly.get("conditions", [])
    }
    present = {cond_by_label.get(lbl) for lbl in rows["condition_label"].astype(str)}
    return [
        c["condition_id"]
        for c in assembly.get("conditions", [])
        if c["condition_id"] in present
    ]


def _holdout_condition_ids(ctx: RunContext, assembly: dict, long_df) -> set[str]:
    """The condition ids the staged holdout names — by display label or by
    semantic key, the same two ways the split below matches them."""
    labels = (ctx.testcase.get("holdout") or {}).get("condition_labels") or []
    cond_by_label = {
        c["maps_to_label"]: c["condition_id"] for c in assembly.get("conditions", [])
    }
    keys = (
        long_df["condition_key"].fillna("")
        if "condition_key" in long_df.columns
        else None
    )
    out: set[str] = set()
    for h in labels:
        k = parse_declared_label(h)
        hit = long_df["condition_label"] == h
        if k and keys is not None:
            hit |= keys == k
        for lbl in long_df.loc[hit, "condition_label"].astype(str).unique():
            cid = cond_by_label.get(lbl)
            if cid:
                out.add(str(cid))
    return out


def _noise_parameters_for(override, condition_id) -> str | None:
    """The `noiseParameters` cell for one measurement row."""
    if isinstance(override, dict):
        return override.get(str(condition_id))
    return override


def _observable_parameters_for(
    placeholders: list[tuple[str, dict[str, str]]], time, condition_id
) -> str | None:
    """The `observableParameters` cell for one measurement row."""
    parts = []
    for per, ids_by_key in placeholders:
        if per == "observable":
            parts.append(ids_by_key["__const__"])
        elif per == "timepoint":
            parts.append(ids_by_key[_time_tag(time)])
        else:
            parts.append(ids_by_key[str(condition_id)])
    return ";".join(parts) if parts else None


class NoiseFormulaError(ValueError):
    """A noise formula the engine cannot render into PEtab.

    A ValueError and NOT a ModuleFailure, deliberately: it is a recoverable
    authoring mistake, caught by the seam checks (`_observation_reply_problems`)
    and re-asked rather than ending the run.
    """


# What a signal-dependent sigma may be written on, for both shapes that have one.
_SIGNAL = (
    "The signal expression is this observable's own formula, with or without "
    "its gain `sc_obs_x`; a sigma on any other state of the model is refused "
    "and re-asked. Assignment-rule symbols are fine; the engine expands them"
)
# The noise shapes the engine can render, stated once. The contract in
# `agents/__init__.py` and `skills/observation.md` quote this list and
# must stay in step with it.
NOISE_SHAPES = (
    (
        "constant",
        "sigma_obs_x",
        "one scale, independent of signal — the right "
        "default when replicate spread does not follow magnitude",
    ),
    (
        "proportional",
        "sigma_obs_x * <this observable's signal expression>",
        "spread scales with "
        "signal; degenerates to zero sigma wherever the signal is zero. " + _SIGNAL,
    ),
    (
        "additive+proportional",
        "sigma_abs + sigma_rel * <this observable's signal expression>",
        "two components: a floor plus a signal-dependent term. The right shape "
        "for a readout that CONTAINS ZEROS — pure proportional puts sigma=0 "
        "there and the likelihood diverges, pure constant misses the scale at "
        "high signal. " + _SIGNAL,
    ),
    (
        "gain-scaled",
        "sc_obs_x * sigma_obs_x",
        "the error scales with the observable's own SCALE FACTOR, not with the "
        "signal: a per-acquisition gain multiplies signal and noise alike, so a "
        "series whose scaling is per timepoint or per condition carries "
        "the same factor into sigma. `sc_obs_x` is the scale_parameter you "
        "declared in `scaling`; the engine renders it as the observable "
        "placeholder, so each row's sigma uses that row's gain",
    ),
)


def _render_noise(
    expr: str,
    oid: str,
    model_entities: set[str],
    assembly_pars: set[str],
    max_components: int = 3,
    placeholder_map: dict[str, str] | None = None,
) -> tuple[list[str], str, str | None]:
    """Turn the noise agent's sigma expression into PEtab.

    Returns (sigma parameter ids in index order, noiseFormula, noiseParameters
    value). A bare id or a number goes through the canonical placeholder
    (noiseParameter1_<obs> + the measurement column) — a bare parameter id in
    noiseFormula is legal PEtab but the amici 1.0 importer maps it to sigma=0
    silently. An EXPRESSION keeps its shape, with each non-model symbol (up to
    `max_components`) rendered through its own placeholder, numbered by first
    appearance in the formula:

        sigma_abs + sigma_rel * B
        -> noiseParameter1_obs + noiseParameter2_obs * B, "sigma_abs;sigma_rel"

    A symbol the model defines by assignment rule is a model symbol like any
    other here; the merge expands it afterwards (`expand_rules`).

    Raises NoiseFormulaError for an empty formula or more components than
    `max_components`.
    """
    import re as _re

    expr = expr.strip()
    if not expr:
        raise NoiseFormulaError(f"noise formula for {oid} is empty")
    try:
        float(expr)
        return [], f"noiseParameter1_{oid}", expr
    except ValueError:
        pass
    if _re.fullmatch(r"[A-Za-z_]\w*", expr):
        return [expr], f"noiseParameter1_{oid}", expr
    free = symbols(expr) - set(model_entities) - set(assembly_pars)
    # first appearance, so the index a reader infers from the formula is the
    # index the measurement column uses
    order: list[str] = []
    for tok in _re.findall(r"[A-Za-z_]\w*", expr):
        if tok in free and tok not in order:
            order.append(tok)
    if len(order) > max_components:
        raise NoiseFormulaError(
            f"noise formula for {oid} names {len(order)} non-model parameters "
            f"{order}, over the {max_components} this engine renders"
        )
    rendered = expr
    # gain-scaled noise: the declared scale parameter becomes the observable
    # placeholder (each row resolves it to its own gain), substituted BEFORE
    # the sigma placeholders so the stem is never taken for a sigma
    for stem, placeholder in (placeholder_map or {}).items():
        rendered = _re.sub(rf"\b{_re.escape(stem)}\b", placeholder, rendered)
    if not order:  # fully defined by the model (or numbers): literal formula
        return [], rendered, None
    for i, sigma_id in enumerate(order, start=1):
        rendered = _re.sub(
            rf"\b{_re.escape(sigma_id)}\b", f"noiseParameter{i}_{oid}", rendered
        )
    return order, rendered, ";".join(order)


def noise_shape_help() -> str:
    """The legal shapes, for a re-ask card or a contract. One source."""
    return "; ".join(f"{name} (`{form}`)" for name, form, _why in NOISE_SHAPES)


# ----------------------------------- assignment rules, expanded for the compile

# how deep one assignment rule may name another before expansion gives up
MAX_RULE_DEPTH = 10
# a rule reference: an identifier wrapped whole in parentheses, so `sc * (MS0)`
# expands without doubling them, or bare — never the exponent letter of a
# number such as 1e-3
_RULE_REF = re.compile(r"\(\s*([A-Za-z_]\w*)\s*\)|(?<![\w.])([A-Za-z_]\w*)")


def _named(text: str) -> set[str]:
    """The identifiers `text` names, as the expansion reads them."""
    return {m.group(1) or m.group(2) for m in _RULE_REF.finditer(str(text))}


def expand_rules(expr: str, rules: dict[str, str]) -> str:
    """`expr` with every assignment-rule symbol replaced by `(its formula)`,
    repeated to a fixed point so a rule that names a rule expands too. Pure.

    Raises ValueError naming the rules when they form a cycle or nest deeper
    than MAX_RULE_DEPTH."""
    text = str(expr)
    if not rules:
        return text

    def _sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return f"({rules[name]})" if name in rules else m.group(0)

    for _ in range(MAX_RULE_DEPTH):
        new = _RULE_REF.sub(_sub, text)
        if new == text:
            return text
        text = new
    left = sorted(_named(text) & set(rules))
    if not left:
        return text
    for start in left:
        cycle = _rule_cycle(start, rules)
        if cycle:
            raise ValueError(
                f"the assignment rules {' -> '.join(cycle)} form a cycle, so "
                f"the formula cannot be written without them"
            )
    raise ValueError(
        f"the assignment rules nest deeper than {MAX_RULE_DEPTH} levels; still "
        f"unexpanded: {left[:4]}"
    )


def _rule_cycle(start: str, rules: dict[str, str]) -> list[str] | None:
    """The first cycle of rule references reachable from `start`, closed on
    its first rule (`a -> b -> a`), or None."""
    refs = {r: sorted(_named(f) & set(rules)) for r, f in rules.items()}
    path: list[str] = []
    done: set[str] = set()

    def visit(node: str) -> list[str] | None:
        if node in path:
            return path[path.index(node) :] + [node]
        if node in done:
            return None
        path.append(node)
        for nxt in refs.get(node, []):
            found = visit(nxt)
            if found:
                return found
        path.pop()
        done.add(node)
        return None

    return visit(start)


# ------------------------------------------------- parameter row defaults
# Workflow-owned defaults for parameters the assembly creates (scaling, offset,
# sigma). Declared in the spec, not chosen by any agent.


def param_scale(p: dict) -> str:
    """The estimation scale a model parameter's PEtab row will declare.

    Public because it is a CONTRACT, not a detail: callers check whether a
    parameter's scale can express its declared neutral value (0 is -inf on
    log10), and reading the rule from anywhere but here would let the two
    drift apart.
    """
    return "log10" if float(p.get("lb", 1e-5)) > 0 else "lin"


def _override_value(v):
    """A condition override value: a float, or a parameter id. Anything else is
    refused by name — a typo must not become a silent zero."""
    import re as _re

    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    if _re.fullmatch(r"[A-Za-z_]\w*", s):
        return s
    raise MergeRefusal(
        f"condition override value {v!r} is neither a number nor a parameter id",
        gate_id="assembly_merge_conditions",
    )


def _dynamic_param_row(p: dict) -> dict:
    lb, ub = float(p.get("lb", 1e-5)), float(p.get("ub", 1e5))
    return {
        "parameterId": p["id"],
        "parameterScale": param_scale(p),
        "lowerBound": lb,
        "upperBound": ub,
        "nominalValue": float(p["nominal_value"]),
        "estimate": 1 if p.get("estimate") else 0,
    }


def _scale_param_row(pid: str, spec, estimate: int = 1) -> dict:
    """`estimate=0` is the pinned factor of a per-timepoint/per-condition set
    (`pin_first_to_one`): nominal 1, never fitted."""
    lb, ub = (float(v) for v in spec.require("assembly_defaults.scaling_bounds"))
    return {
        "parameterId": pid,
        "parameterScale": "log10",
        "lowerBound": lb,
        "upperBound": ub,
        "nominalValue": 1.0,
        "estimate": int(estimate),
    }


def _offset_param_row(pid: str, spec) -> dict:
    lb, ub = (float(v) for v in spec.require("assembly_defaults.offset_bounds"))
    return {
        "parameterId": pid,
        "parameterScale": "lin",
        "lowerBound": lb,
        "upperBound": ub,
        "nominalValue": 0.0,
        "estimate": 1,
    }


def _sigma_param_row(pid: str, spec) -> dict:
    lb, ub = (float(v) for v in spec.require("assembly_defaults.sigma_bounds"))
    return {
        "parameterId": pid,
        "parameterScale": "log10",
        "lowerBound": lb,
        "upperBound": ub,
        "nominalValue": 1.0,
        "estimate": 1,
    }
