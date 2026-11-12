"""S0 — freeze the intent.

The anti-goal-drift device: everything downstream is scored against this
record (`intent`), so the system cannot quietly redefine the task into
something it can do. Human gate blocking: only the user knows what they meant.
"""

from __future__ import annotations

import yaml

from octomod.config import KNOWLEDGE_DIR
from octomod.orchestration import (
    timing,  # noqa: E402
)
from octomod.orchestration.artifacts import validate_intent
from octomod.orchestration.interaction import humangate
from octomod.orchestration.run_context import ModuleFailure, RunContext
from octomod.workflow_modules.knowledge import engine as _kn
from octomod.workflow_modules.knowledge import supplied_literature as _lit
from octomod.workflow_modules.knowledge.reaction_evidence import required_reactions


@timing.phase("intent")
def run(ctx: RunContext) -> None:
    if (ctx.root / "intent").exists():
        return

    intent_path = ctx.testcase_dir / "intent.yaml"
    if not intent_path.exists():
        raise ModuleFailure(f"this run's input/ has no intent.yaml: {intent_path}")
    intent = yaml.safe_load(intent_path.read_text())

    problems = validate_intent(intent)
    # the record's own check runs here, before the gate, so a
    # staging mistake reaches the person as a refusal to ask, not as a stop
    # after they approved
    from pydantic import ValidationError as _VE

    from octomod.result.slots import IntentRecord

    try:
        IntentRecord.model_validate(intent)
    except _VE as e:
        problems += [
            f"intent.yaml: {'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()[:6]
        ]
    # Every declared domain pack must resolve: a mis-selected pack fails silently.
    for pack in intent.get("domain_packs", []):
        if not (KNOWLEDGE_DIR / pack / "pack.yaml").exists():
            problems.append(
                f"domain pack {pack!r} does not resolve to an existing pack"
            )
    # Supplied literature is fenced before anything is spent: a forbidden
    # source or a post-horizon paper is refused by name.
    supplied = _lit.items(intent)
    problems += _lit.problems(intent)
    if supplied and not _lit.problems(intent):
        # A benchmark case is recognised by `truth/`, so this takes the SOURCE
        # case: the run's snapshot never carries `truth/` and is named `input`.
        hp = _lit.horizon_problem(ctx.testcase, supplied, ctx.project, ctx.source_dir)
        if hp:
            problems.append(hp)
        horizon = (ctx.testcase.get("research") or {}).get("max_publication_year")
        problems += _lit.fence_refusals(
            supplied,
            _lit.read_blocklist(ctx.testcase_dir / "blocklist.txt"),
            int(horizon) if horizon is not None else None,
        )
        # Against the source case too: on the snapshot this would always pass.
        if ctx.source_dir is not None:
            decl = _lit.declaration_problem(ctx.source_dir, intent)
            if decl:
                problems.append(decl)
    if problems:
        raise ModuleFailure("intent rejected (T0): " + " | ".join(problems))

    # what construction will read of the data before extraction: the curves in
    # words from the raw files, or the rule that kept them from it
    from octomod.workflow_modules.data import raw_phenomenology as _raw

    raw_lines = _raw.intent_card_lines(ctx)
    # what the knowledge module said before this intent was frozen: the
    # required and essential reactions with their grades and origins, the
    # floor, and what moved in the intent since the module saw it
    knowledge_lines = _kn.intent_lines(ctx, intent) if _kn.has_staged(ctx) else []
    approved, _ = humangate.ask(
        "Freeze this intent? Everything downstream is scored against it.",
        [
            f"question:          {intent['question']}",
            f"system:            {intent['system']}",
            f"inference_target:  {intent['inference_target']}",
            f"required:          {intent['required_predictions']}",
            *(
                # the reactions the model must contain, as the engine reads them
                [
                    "required_reactions: "
                    + "; ".join(
                        f"{r['id']} {r['equation']}" for r in required_reactions(intent)
                    )
                ]
                if intent.get("required_reactions")
                else []
            ),
            f"success_criteria:  {intent['success_criteria']}",
            f"domain_packs:      {intent['domain_packs']}",
            *_lit.card_lines(supplied),
            *knowledge_lines,
            *raw_lines,
        ],
        ledger=ctx.ledger,
        module="intent",
        round_idx=ctx.round_idx,
        auto=ctx.auto,
        consequences=(
            "intent is frozen; every downstream verdict is scored against it",
            "run stops; edit the testcase's intent.yaml and rerun",
        ),
    )
    if not approved:
        raise ModuleFailure("user declined to freeze the intent")

    from octomod.result.write import write_record

    # The supplied items get their own run-level record, kept out of `intent`
    # (which reaches more roles than the literature may). Written before
    # `intent`, so a resume that finds `intent` finds the snapshot too.
    lit_sha = _lit.freeze(ctx.root, supplied)
    if lit_sha:
        horizon = (ctx.testcase.get("research") or {}).get("max_publication_year")
        ctx.ledger.append(
            "artifact",
            module="intent",
            artifact=_lit.FROZEN_KEY,
            sha=lit_sha,
            producer="user+validation",
            n_items=len(supplied),
            year_fenced=horizon is not None,
            horizon=horizon,
            note=(
                f"{len(supplied)} supplied literature item(s) frozen with the "
                f"intent; kept out of `intent` so only {_lit.reaches_text()} "
                f"receive them (construction_verification does not: an auditor reading the same "
                f"claims is not independent of them); "
                + (
                    f"year-fenced at the declared horizon {horizon}"
                    if horizon is not None
                    else "NOT year-fenced: the case declares no "
                    "research.max_publication_year (optional for an application "
                    "case; required for a benchmark case)"
                )
            ),
        )
    sha = write_record(
        ctx.root / "intent", IntentRecord, _lit.strip_from_intent(intent)
    )
    ctx.ledger.append(
        "artifact",
        module="intent",
        artifact="intent",
        sha=sha,
        producer="user+validation",
    )
