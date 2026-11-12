"""S11 — revision proposal. High freedom, bounded by a closed move grammar.

The agent diagnoses and proposes; the grammar bounds what a proposal can be;
cycle detection by configuration hash makes non-termination impossible rather
than unlikely; the human approves each round (each one costs a calibration).
"""

from __future__ import annotations

import json

from octomod.agents import payload as _payload
from octomod.orchestration import rounds as _rounds
from octomod.orchestration import (
    timing,  # noqa: E402
)
from octomod.orchestration.interaction import humangate
from octomod.orchestration.ledger import sha256_text
from octomod.orchestration.run_context import ModuleFailure, RunContext
from octomod.result import node as tree
from octomod.result.autocommit import commit_ctx
from octomod.result.node import Node
from octomod.result.slots import AssemblyRecord, RevisionRecord
from octomod.result.write import write_record

# move type -> required args. The grammar IS the boundary: nothing else applies.
MOVE_SPECS: dict[str, list[str]] = {
    "change_noise_model": ["observable_id", "new_distribution"],
    "add_offset": ["observable_id"],
    "remove_scaling": ["observable_id"],
    "change_observable_formula": ["observable_id", "new_formula"],
    "fix_parameter": ["parameter_id", "value"],
    "free_parameter": ["parameter_id"],
    "change_bounds": ["parameter_id", "lb", "ub"],
    "change_kinetic_law": ["reaction_id", "directive"],
    "add_reaction": ["directive"],
    "remove_reaction": ["reaction_id"],
    "stop": [],
}
MODEL_MOVES = {"change_kinetic_law", "add_reaction", "remove_reaction"}

GRAMMAR_TEXT = "\n".join(f"- {t}({', '.join(args)})" for t, args in MOVE_SPECS.items())


def _write_revision(ctx: RunContext, decision: Node, payload: dict) -> None:
    """The round's revision decision, validated and committed."""
    write_record(decision, RevisionRecord, payload)
    commit_ctx(ctx, why="decision:revision_proposal", subject=decision.key)


def _param_identity(params: list[dict]) -> str:
    """The estimation-relevant face of the parameter table: which parameters
    are estimated, over what bounds, and at what fixed values. Part of the
    config hash because `change_bounds`, `fix_parameter` and `free_parameter`
    change neither the Antimony nor the assembly."""
    rows = sorted(
        (
            str(p.get("id")),
            bool(p.get("estimate", True)),
            repr(p.get("lb")),
            repr(p.get("ub")),
            repr(p.get("nominal_value")),
        )
        for p in params
    )
    return json.dumps(rows)


def _assembly_identity(asm: dict | None) -> str:
    """The assembly as hashed text — canonical (sorted keys), so the record's
    copy and a pre-flight edit of it hash alike whatever their key order."""
    if asm is None:
        return "{}"
    return json.dumps(asm, indent=2, sort_keys=True, default=str) + "\n"


def _model_source(model: Node) -> str:
    """The model's identity text: its Antimony, or — a PEtab-entry round may
    carry SBML only (antimony reconstruction is best-effort) — its SBML."""
    ant = (model / "antimony").text(None)
    return ant if ant is not None else (model / "sbml").text()


def config_hash(rnd: Node) -> str:
    """Identity of a tried configuration of a single-model round
    (`rounds/round_k`): the model source + the assembly decisions + the
    parameter table's estimation face. Two rounds with the same hash are the
    same experiment."""
    model = tree.model_node(rnd, None)
    asm = (tree.work_node(rnd, None) / "assembly").get(None)
    par = (model / "parameters").get(None)
    return sha256_text(
        _model_source(model)
        + _assembly_identity(asm)
        + (_param_identity(par) if par is not None else "[]")
    )


@timing.phase("revision_proposal")
def run(
    ctx: RunContext, report: dict, history: list[dict], rounds_left: int
) -> dict | None:
    """Returns the applied move (next round prepared), or None to stop."""
    # A decided revision is durable: a resume must not re-run the agent and
    # overwrite a move the human already approved.
    decision = ctx.round / "revision"
    decided = decision.get(None)
    if decided is not None:
        print(
            "  (revision already decided for this round — resumed from "
            f"{decision.key}: {decided.get('move', {}).get('type', 'stop')})"
        )
        return decided if decided.get("move") else None

    # Misfit signals are indicators, not deciders: no threshold here ends or
    # extends a run (biological variability legitimately widens a sigma/floor
    # ratio). A stop proposed while they are open goes to the human.
    ev = report.get("misfit_evidence") or {}
    misfit_open = bool(ev.get("open")) and bool(
        ctx.spec.get("gates.misfit.escalate_stop", True)
    )
    # Each earlier move travels with its rationale and falsifiers, so the agent
    # can check the predictions it registered.
    rich_history = []
    for h in history:
        entry = {
            "round": h["round"],
            "move": h.get("move"),
            "best_fval": h.get("best_fval"),
        }
        d = (tree.round_node(ctx.root, h["round"]) / "revision").get(None)
        if d is not None:
            if d.get("move"):
                entry["move"] = d["move"]
                entry["your_rationale_then"] = d.get("motivated_by")
                entry["what_you_predicted_and_your_falsifiers"] = d.get(
                    "expected_effect"
                )
        rich_history.append(entry)

    context = {
        "intent": ctx.intent,
        "experiment_description": ctx.description,  # the lab note
        # the agent-facing view: the full report is far too large for a prompt
        "evaluation_report": _payload.core_for_agents(report),
        "move_grammar": GRAMMAR_TEXT,
        "history": rich_history,
        "rounds_left": _rounds.as_record(rounds_left),
    }
    # Standing structural questions raised at construction and deferred by the
    # human, with the human's own answer. These are the loop's memory of what
    # it already suspected and has not yet tested.
    from octomod.workflow_modules.model.engine import open_questions_path

    oq_node = open_questions_path(ctx)
    if oq_node.exists():
        oq = [
            q for q in oq_node.get() if q.get("status") in ("open", "deferred_by_human")
        ]
        if oq:
            context["open_structural_questions"] = {
                "questions": oq,
                "instruction": "These were raised by the model-construction module and "
                "deferred by the human, often with a CONDITION attached "
                "('let the residuals tell us'). Check each one against "
                "the evidence in this report before proposing anything "
                "new: if the condition the human named has now been met, "
                "the deferred question is the move to make, and say so "
                "explicitly. A question you raised yourself and never "
                "returned to is the most likely place the model is wrong.",
            }
    if misfit_open:
        context["structural_misfit_indicators"] = {
            "evidence": ev.get("reasons", []),
            "instruction": "These are model-free measurements against the assay's own "
            "replicate repeatability. They are INDICATORS, not verdicts: "
            "a fitted sigma above a floor built from technical replicates "
            "can have innocent causes (biological variability between "
            "cultures, day effects). Weigh them as evidence, not as a "
            "rule. What they do say is that the intent's headline "
            "criterion being met is not by itself a reason to stop — a "
            "structurally wrong model can hit one required prediction. If "
            "a missing process is the best explanation, propose the move "
            "that tests it; if you still judge stopping right, say so and "
            "say what would change your mind. Either way a human decides "
            "next, so an informative suggestion beats a cautious one.",
        }
    from octomod.orchestration.interaction import retry as _retry

    max_attempts = int(ctx.spec.get("retry.module_draft", 2)) + 1
    # the dossier of rejected moves; `history` stays the rounds already
    # evaluated, which the pre-flight cycle check below compares against.
    # Every pass replays this loop from its first ask, so the dossier is
    # rebuilt from nothing as the replay rejects the same moves: attempt n
    # must carry exactly the rejections before it, or its prompt differs from
    # the one already answered and the call is paid again. What an earlier
    # pass recorded tells a replayed rejection from a new one.
    attempts = _retry.AttemptHistory(_retry.dossier_of(ctx, "revision_proposal"))
    recorded, attempts.attempts = attempts.attempts, []
    move = None
    for _attempt in range(max_attempts):
        if attempts.attempts:  # every rejected move so far, not only the last
            context["attempt_history"] = attempts.as_context()
        # Every ask here precedes a gate, and the file-gate protocol re-runs
        # this module on each answer: each ask is cached under its own name, so
        # a resume reads the reply the human was shown instead of paying for
        # a new one that the stored answer would then approve unseen.
        proposal = ctx.call_cached(
            "revision_proposal", context, name=f"revision_proposal_{_attempt + 1}"
        )
        candidate = proposal["move"]
        err = _validate_move(candidate, ctx)
        if (
            err is None
            and candidate["type"] not in MODEL_MOVES
            and candidate["type"] != "stop"
        ):
            # non-model moves are cycle-checked pre-flight: apply the move to
            # the assembly and the parameter table as _prepare_next_round
            # would, then hash the same three parts config_hash() does
            next_asm = _edited_assembly(ctx, candidate)
            next_par = _edited_parameters(ctx, candidate)
            ant = _model_source(ctx.model)
            asm_text = _assembly_identity(
                next_asm if (ctx.work / "assembly").exists() else None
            )
            h = sha256_text(ant + asm_text + _param_identity(next_par))
            if any(h == past.get("config_hash") for past in history):
                err = (
                    f"move reproduces an already-evaluated configuration "
                    f"(hash {h}) — propose something else or stop"
                )
        if err is None:
            move = proposal
            break
        entry = attempts.add([err], {"rejected_move": candidate})
        k = entry["attempt"]
        if len(recorded) >= k and recorded[k - 1] == entry:
            continue  # the pass that made this rejection ledgered it
        ctx.ledger.append(
            "redraft",
            module="revision_proposal",
            round_idx=ctx.round_idx,
            role="revision_proposal",
            attempt=entry["attempt"],
            n_failures=1,
            localized=False,
        )
    if move is None:
        raise ModuleFailure(
            "revision agent exhausted its budget without a "
            "valid, novel move (every attempt: "
            f"{_retry.dossier_of(ctx, 'revision_proposal').key})"
        )

    if move["move"]["type"] == "stop":
        ctx.ledger.append(
            "note",
            module="revision_proposal",
            round_idx=ctx.round_idx,
            note=f"agent proposes stop: {move['motivated_by']}",
        )
        if not misfit_open:
            _write_revision(
                ctx,
                decision,
                {
                    "move": None,
                    "why": "agent proposed stop; misfit " "indicators clean",
                },
            )
            return None
        # a stop against open misfit indicators is the human's call. Asked
        # once: the resume that answers the approval gate below replays this
        # module, and must neither ask this gate again nor hand it the answer
        # stored for that one; a no is recorded too (`record_decline`), since
        # the agent was paid for the proposal the card shows.
        keep_going, note = humangate.ask_once(
            ctx,
            ctx.round / "decisions/revision_proposal_stop_vs_revise",
            "The agent suggests stopping, but the misfit indicators are not "
            "clean. Spend another round on a structural revision?",
            [
                "the agent's reason for stopping:",
                f"  {str(move['motivated_by'])[:400]}",
                "misfit indicators — measured against the assay's own replicate "
                "repeatability, informative but NOT decisive (a fitted sigma "
                "above a technical-replicate floor has innocent causes too):",
                *(f"  · {r}" for r in ev.get("reasons", [])),
                f"rounds: {_rounds.remain(rounds_left)}",
            ],
            module="revision_proposal_stop_vs_revise",
            record_decline=True,
            intent=ctx.intent,
            consequences=(
                "the agent is asked for its best structural move, "
                "which you then approve or reject (a round costs a "
                "full calibration)",
                "the loop ends here; the report carries the "
                "indicators as an open, unexplained defect",
            ),
        )
        if not keep_going:
            _write_revision(
                ctx,
                decision,
                {
                    "move": None,
                    "why": "human ended the loop with the "
                    "misfit indicators still open",
                },
            )
            return None
        context["human_override"] = (
            "A human read your stop proposal alongside the misfit indicators "
            "and asked for a structural revision instead"
            + (f", with this instruction: {note}" if note else "")
            + ". Propose the single move most likely to explain the "
            "indicators — typically a missing process in the part of the "
            "network where the residuals or the inflated sigma sit. 'stop' "
            "is not a useful answer to this request."
        )
        move = None
        for _attempt in range(max_attempts):
            proposal = ctx.call_cached(
                "revision_proposal",
                context,
                name=f"revision_override_{_attempt + 1}",
            )
            candidate = proposal["move"]
            err = _validate_move(candidate, ctx)
            if err is None and candidate["type"] == "stop":
                err = (
                    "the human explicitly asked for a structural move "
                    "instead of stopping; propose one"
                )
            if err is None:
                move = proposal
                break
            context["previous_attempt_errors"] = err
            ctx.ledger.append(
                "note",
                module="revision_proposal",
                round_idx=ctx.round_idx,
                note=f"post-override move rejected: {err}",
            )
        if move is None:
            ctx.ledger.append(
                "note",
                module="revision_proposal",
                round_idx=ctx.round_idx,
                note="agent produced no structural move after the "
                "human override; loop ends",
            )
            _write_revision(
                ctx,
                decision,
                {"move": None, "why": "no structural move after the " "human override"},
            )
            return None

    # asked once, and a no recorded: the proposal on the card was paid for
    approved, _ = humangate.ask_once(
        ctx,
        ctx.round / "decisions/revision_proposal",
        "Approve this revision? (another round costs a full calibration)",
        [
            f"move: {move['move']['type']}({move['move']['args']})",
            f"motivated by: {move['motivated_by']}",
            f"expected effect: {move['expected_effect']}",
            f"after this one: {_rounds.remain(rounds_left - 1)}",
        ],
        module="revision_proposal",
        record_decline=True,
        intent=ctx.intent,
        consequences=(
            "the move is applied and the next round runs the full "
            "pipeline again (another calibration's cost)",
            "loop ends; the current model stands as the result",
        ),
    )
    if not approved:
        _write_revision(
            ctx,
            decision,
            {"move": None, "why": "human declined the proposed revision"},
        )
        return None

    _prepare_next_round(ctx, move["move"])
    _write_revision(ctx, decision, move)  # durable: a resume must not re-decide
    return move


def _validate_move(move: dict, ctx: RunContext) -> str | None:
    mtype = move.get("type")
    if mtype not in MOVE_SPECS:
        return f"move type {mtype!r} is not in the grammar:\n{GRAMMAR_TEXT}"
    missing = [a for a in MOVE_SPECS[mtype] if a not in move.get("args", {})]
    if missing:
        return f"move {mtype} missing required args {missing}"
    args = move.get("args", {})
    if "observable_id" in args:
        asm = (ctx.work / "assembly").get()
        known = {o["observable_id"] for o in asm["observables"]}
        if args["observable_id"] not in known:
            return (
                f"unknown observable {args['observable_id']!r} (have {sorted(known)})"
            )
    if "parameter_id" in args:
        params = (ctx.model / "parameters").get()
        if args["parameter_id"] not in {p["id"] for p in params}:
            return (
                f"parameter {args['parameter_id']!r} is not a dynamic model "
                f"parameter — this move class only touches those"
            )
    return None


def _edited_assembly(ctx: RunContext, move: dict) -> dict:
    """Assembly-side moves go through the shared executor (assembly_edit) —
    the same code the model-space enumerator uses for observation axes, so the
    two callers cannot disagree about an edit."""
    from octomod.workflow_modules.assembly import assembly_edit

    asm = (ctx.work / "assembly").get()
    return assembly_edit.apply_move(asm, move)


def _edited_parameters(ctx: RunContext, move: dict) -> list[dict]:
    """Apply a parameter-side move to the parameter list. Shared by the
    pre-flight cycle check and by _prepare_next_round so the two can never
    disagree about what a move produces."""
    params = (ctx.model / "parameters").get()
    t, args = move["type"], move.get("args", {})
    if t not in ("fix_parameter", "free_parameter", "change_bounds"):
        return params
    for p in params:
        if p["id"] != args.get("parameter_id"):
            continue
        if t == "fix_parameter":
            p["estimate"] = False
            p["nominal_value"] = float(args["value"])
        elif t == "free_parameter":
            p["estimate"] = True
        else:
            p["lb"], p["ub"] = float(args["lb"]), float(args["ub"])
    return params


def _prepare_next_round(ctx: RunContext, move: dict) -> None:
    nxt = tree.round_node(ctx.root, ctx.round_idx + 1)
    # data always carries forward — no move in the grammar touches it
    (ctx.round / "data").copy_to(nxt / "data")

    t = move["type"]
    args = move.get("args", {})
    if t in MODEL_MOVES:
        # model is redrafted by construction under a directive; assembly is
        # NOT carried (sub-agents re-run against the new model)
        directive = {
            "change_kinetic_law": f"Change the kinetic law of reaction "
            f"{args.get('reaction_id')}: {args.get('directive')}",
            "add_reaction": f"Add a reaction: {args.get('directive')}",
            "remove_reaction": f"Remove reaction {args.get('reaction_id')} and "
            f"anything only it justified",
        }[t]
        (nxt / "directive").put_text(directive + "\n")
    else:
        # model carries forward; edited assembly pre-seeds S3 (sub-agents skipped)
        from octomod.orchestration import round_seed

        ctx.model.copy_to(tree.model_node(nxt, None))
        if t in ("fix_parameter", "free_parameter", "change_bounds"):
            params = _edited_parameters(ctx, move)
            (tree.model_node(nxt, None) / "parameters").put(params)
            asm = (ctx.work / "assembly").get()
        else:
            params = (ctx.model / "parameters").get([]) or []
            asm = _edited_assembly(ctx, move)
        write_record(tree.work_node(nxt, None) / "assembly", AssemblyRecord, asm)
        # the round_seed shape (`seeded_from: {round, via: "revision", move,
        # …}`), so a re-entry of the next round gets its model, data and
        # edited assembly back instead of re-extracting and redrafting them
        round_seed.seed_revision(ctx, nxt, move=t, parameters=params, assembly=asm)
