"""A round starts from exactly the model it was seeded from.

An expansion round is built on a model the previous round fitted (the criterion
winner, the human's `base:`, or a rebuilt base with the decided axes). The seed
is that candidate's model records byte for byte and its merged assembly, so the
next round's base is the fitted problem and its fit is reused; `base_identity`
checks that and names any difference. The checker's audit is carried while
the assembly is unchanged.

The seed is the round's `model/seed` record (`rounds/round_<k>/model/
seed`), written by the expansion, never by a module, so no re-entry supersedes
it; the seeded model is the round's `model/{antimony,sbml,parameters,
glossary}`, its data the round's `data` group, its assembly `shared_assembly`.
"""

from __future__ import annotations

from octomod.result import node as tree
from octomod.result.node import Node, RecordMissing

# the transition's record in the round it seeded: its source, the assembly it
# was given (None for a supplied PEtab problem) and the audit that covered it.
SEED_KEY = "model/seed"
MODEL_KEYS = ("antimony", "sbml", "parameters", "glossary")  # under `model/`
MODEL_FILES = MODEL_KEYS  # the older name, kept for callers that still use it
PROBLEM_KEYS = (
    "model/sbml",
    "petab/observables",
    "petab/conditions",
    "petab/measurements",
    "petab/parameters",
)
PROBLEM_FILES = PROBLEM_KEYS
# written by the S3 re-ask machinery about ITS round's shared assembly; a seeded
# round starts its own count
_BOOKKEEPING = ("_version", "_shared_version")


def assembly_content(asm: dict | None) -> dict:
    """An assembly without the per-round bookkeeping, for comparing two."""
    return {k: v for k, v in (asm or {}).items() if k not in _BOOKKEEPING}


def estimated_parameters(work: Node) -> list[str]:
    """The estimated parameter ids of a fitted problem (`…/petab/parameters`)."""
    df = (work / "petab/parameters").table(None)
    if df is None or "estimate" not in df.columns:
        return []
    return sorted(str(x) for x in df.loc[df["estimate"] == 1, "parameterId"])


def _problem_hash(work: Node) -> str | None:
    from octomod.workflow_modules.assembly import petab_io
    from octomod.workflow_modules.estimation.problem import problem_content_hash

    try:
        return problem_content_hash(petab_io.from_work(work, work / "model"))
    except (RecordMissing, OSError, KeyError, ValueError):
        return None


def _audit_record(rnd: Node, work: Node | None, has_overlay: bool) -> dict | None:
    """What audited the seed's assembly in its own round, or None when nothing
    covers all of it (then the next round's checker runs)."""
    shared = sorted(
        (tree.work_node(rnd, c) / "gates/assembly_verification").key
        for c in tree.candidate_ids(rnd)
        if (tree.work_node(rnd, c) / "gates/assembly_verification").exists()
    )
    if not shared:
        # nothing was audited in this round because it inherited its audit;
        # that audit still covers the round's shared assembly while it is the
        # seeded one, but not an overlay the candidate added this round
        if has_overlay:
            return None
        shared_asm = (rnd / "shared_assembly").get(None)
        return carried_audit(rnd, shared_asm) if shared_asm is not None else None
    own = work / "gates/assembly_verification" if work is not None else None
    if has_overlay and (own is None or not own.exists()):
        return None  # the overlay part was never audited
    return {
        "round": rnd.name,
        "records": shared,
        "overlay_audit": (own.key if has_overlay and own else None),
    }


def require_evaluation(ctx) -> None:
    """Refuse, by name, to seed a round from a finished round whose evaluation
    slot does not validate.

    The next round is built from what that report says (the winner, the
    interpretation, the misfit evidence), and a report read back can have
    lost what it said. The slot's own validator decides (`round_status`,
    module `entry_evaluation`); a report already validated at its current
    content is not validated again, so a resumed transition asks once."""
    from octomod.orchestration import round_status
    from octomod.orchestration.run_context import ModuleFailure

    required = round_status.SLOTS["evaluation"]["required"]
    rec = round_status.validation_record(ctx.round, "evaluation", None)
    base = round_status.slot_base(ctx.round, "evaluation", None)
    files = (rec or {}).get("files") or {}
    if (
        str((rec or {}).get("validated_by", "")).startswith("entry_evaluation")
        and all((base / r).exists() for r in required)
        and all(files.get(r) == (base / r).sha() for r in required)
    ):
        return
    n_before = len(ctx.ledger.entries())
    ok, why = round_status.validate(ctx, "evaluation", default_producer="engine")
    if ok:
        return
    failed = [
        str(e.get("gate_id"))
        for e in ctx.ledger.entries()[n_before:]
        if e.get("event") == "gate" and not e.get("passed")
    ]
    raise ModuleFailure(
        f"round {ctx.round_idx} is not seeded from: its evaluation slot "
        f"({', '.join(required)}) does not validate"
        + (f", check {', '.join(failed)} failed" if failed else "")
        + f" — {'; '.join(why)}. The next round would be built from this "
        f"report; rebuild it with --from-module evaluation."
    )


def _round(ctx, nxt) -> Node:
    """The next round's node: given as a round `Node` or as its index."""
    if isinstance(nxt, Node):
        return nxt
    return tree.round_node(ctx.root, int(nxt))


def seed_round(
    ctx,
    nxt,
    *,
    candidate: str | None,
    why: str,
    antimony: str | None = None,
    parameters: list | None = None,
    overlay: list | None = None,
    glossary_from: str | None = None,
    carried: list | None = None,
) -> dict:
    """Write round `nxt`'s starting point and return the record of it.

    `nxt` is the next round's node (`rounds/round_<k+1>`) or its index. With
    `candidate` (a fitted candidate of the current round): its model records
    and its merged assembly, exactly. Without (a rebuilt base, which no
    candidate of the round is): `antimony` + `parameters`, the glossary of
    `glossary_from` (the winner's covers every entity the rebuild can name),
    and the round's shared assembly with `overlay` (the decided observation
    axes) applied.

    `carried` (axes re-declared live for the next round): their observation
    patches are not baked into the base, since the search switches them itself.
    A candidate base that loses a patch is then not the fitted problem:
    the record says so and names what was left out. Writes `model/seed` and
    the next round's `data`, `model/*` and `shared_assembly`, after the source
    round's evaluation slot validates (`require_evaluation`)."""
    from octomod.workflow_modules.assembly import assembly_edit

    require_evaluation(ctx)
    rnd = ctx.round
    nxt = _round(ctx, nxt)
    (rnd / "data").copy_to(nxt / "data")
    shared = (rnd / "shared_assembly").get(None)
    record: dict = {"round": ctx.round_idx, "why": why, "candidate": candidate}

    if candidate is not None:
        work = tree.work_node(rnd, candidate)
        for k in MODEL_KEYS:
            (work / "model" / k).copy_to(nxt / "model" / k)
        merged = work / "assembly"
        own_overlay = (work / "model/assembly_overlay").get([]) or []
        from octomod.workflow_modules.model.model_space import base_overlay_after_carry

        kept = base_overlay_after_carry(own_overlay, carried or [])
        left_out = [o for o in own_overlay if o not in kept]
        if left_out and shared is not None:
            # an undecided axis's patch stays out of the base
            assembly = assembly_edit.apply_overlay(
                shared, kept, assembly_for_refs=shared
            )
            own_overlay = kept
        elif merged.exists():
            assembly = merged.get()
        elif shared is not None:
            assembly = assembly_edit.apply_overlay(
                shared, own_overlay, assembly_for_refs=shared
            )
        else:
            assembly = None  # a supplied PEtab problem has no assembly to carry
        record.update(
            {
                "problem": _problem_hash(work),
                "estimated_parameters": estimated_parameters(work),
                "observation_overlay": own_overlay,
                # the fitted problem's group, whose `multistart` is the fit
                "fit": (work.key if (work / "multistart").exists() else None),
            }
        )
        audit = _audit_record(rnd, work, bool(own_overlay))
        if left_out and shared is not None:
            # base = candidate minus the undecided patches: a different problem
            # than the one fitted, so no fit to reuse and no audit to inherit
            record.update(
                {"problem": None, "fit": None, "left_out_live_patches": left_out}
            )
            audit = None
    else:
        from octomod.gates.build_gates import antimony_to_sbml
        from octomod.orchestration.run_context import ModuleFailure

        sbml, err = antimony_to_sbml(antimony or "")
        if sbml is None:
            raise ModuleFailure(f"the rebuilt expansion base does not build: {err}")
        if glossary_from:
            (tree.work_node(rnd, glossary_from) / "model/glossary").copy_to(
                nxt / "model/glossary"
            )
        (nxt / "model/antimony").put_text(antimony or "")
        (nxt / "model/sbml").put_text(sbml)
        (nxt / "model/parameters").put(list(parameters or []))
        assembly = (
            assembly_edit.apply_overlay(
                shared, list(overlay or []), assembly_for_refs=shared
            )
            if shared is not None
            else None
        )
        record.update(
            {
                "rebuilt": True,
                "problem": None,
                "observation_overlay": list(overlay or []),
                "fit": None,
                # kept so a re-entry can put the rebuilt base back
                "antimony": antimony or "",
                "parameters": list(parameters or []),
                "glossary_from": glossary_from,
            }
        )
        # an overlay rebuilt here was audited on whichever candidates carried
        # it, never as this combination: the next round's checker looks at it
        audit = None if overlay else _audit_record(rnd, None, False)

    content = assembly_content(assembly) if assembly is not None else None
    if content is not None:
        (nxt / "shared_assembly").put(content)
    record["assembly_carried"] = content is not None
    record["audit_carried"] = audit
    (nxt / SEED_KEY).put({"seeded_from": record, "assembly": content, "audit": audit})
    return record


def seed_revision(
    ctx,
    nxt,
    *,
    move: str,
    parameters: list,
    assembly: dict,
) -> dict:
    """Write the `model/seed` of a round a S11 revision move prepared (a move
    that keeps the model: a parameter or an assembly edit), in the same shape
    `seed_round` writes, and return its `seeded_from`.

    `seeded_from` carries the revision's provenance (`via: "revision"`, the
    `move`) and what a re-entry needs to put the round's inputs back
    (`restore_model`, `restore_data`, `restore_revision_assembly`): the source
    round (its `data` was carried), the source model (`source_candidate`,
    None for the round's own model), the model's `parameters` after the move,
    and, as the seed's `assembly`, the edited assembly that pre-seeds S3.
    No `candidate`: the round's model is not a fitted candidate as it is, so
    nothing treats its fit as reusable. No `audit`: the checker looks at the
    edited assembly again."""
    nxt = _round(ctx, nxt)
    record = {
        "round": ctx.round_idx,
        "via": "revision",
        "move": move,
        "why": f"revision move {move}",
        "candidate": None,
        "source_candidate": ctx.candidate,
        "parameters": list(parameters or []),
        "problem": None,
        "fit": None,
        "assembly_carried": assembly is not None,
        "audit_carried": None,
    }
    (nxt / SEED_KEY).put({"seeded_from": record, "assembly": assembly, "audit": None})
    return record


def is_revision(seed: dict | None) -> bool:
    return ((seed or {}).get("seeded_from") or {}).get("via") == "revision"


# ----------------------------------------------------- reading the seed back


def seeded(rnd: Node) -> dict | None:
    got = (rnd / SEED_KEY).get(None)
    return got if isinstance(got, dict) else None


def carried_audit(rnd: Node, shared_assembly: dict | None) -> dict | None:
    """The previous round's audit of this round's shared assembly — only while
    the assembly is still the one that was seeded (a redraft or a re-ask makes
    it another assembly, which nobody has audited)."""
    s = seeded(rnd)
    if not s or not s.get("audit") or shared_assembly is None:
        return None
    if assembly_content(shared_assembly) != assembly_content(s.get("assembly")):
        return None
    return s["audit"]


def restore_shared(rnd: Node) -> bool:
    """Put the seeded assembly back as the round's shared assembly when it is
    missing (a `--from-module assembly` re-entry moves the shared assembly
    aside; in a seeded round it is the seed, an INPUT of S3, not its product).
    The caller checks that no redraft was asked this round — that is the one
    thing that replaces the seed."""
    s = seeded(rnd)
    shared = rnd / "shared_assembly"
    if not s or s.get("assembly") is None or shared.exists() or is_revision(s):
        # a revision's assembly is the single unit's, not a shared one
        # (`restore_revision_assembly`)
        return False
    shared.put(s["assembly"])
    return True


def restore_model(root: Node, rnd: Node) -> bool:
    """Put the seeded MODEL back when it is missing — the model-module twin of
    `restore_shared`.

    A `--from-module model` re-entry moves the model slot's records aside, and
    in a seeded round those records are the seed, an INPUT of S1, not its
    product. Without them the round would be taken for a fresh one and
    construction called again. Returns True when it restored anything."""
    s = seeded(rnd)
    model = rnd / "model"
    if not s or (model / "antimony").exists():
        return False
    src = s.get("seeded_from") or {}
    if src.get("via") == "revision" and src.get("round") is not None:
        # the source round's model with the move's parameters; the edited
        # assembly is the other half of what the revision seeded
        source_model = tree.model_node(
            tree.round_node(root, int(src["round"])), src.get("source_candidate")
        )
        if not (source_model / "antimony").exists():
            return False
        for k in MODEL_KEYS:
            (source_model / k).copy_to(model / k)
        if src.get("parameters"):
            (model / "parameters").put(list(src["parameters"]))
        restore_revision_assembly(rnd)
        return True
    if src.get("candidate") is not None and src.get("round") is not None:
        cand_model = tree.model_node(
            tree.round_node(root, int(src["round"])), str(src["candidate"])
        )
        if not (cand_model / "antimony").exists():
            return False
        for k in MODEL_KEYS:
            (cand_model / k).copy_to(model / k)
        return True
    if src.get("rebuilt") and src.get("antimony"):
        from octomod.gates.build_gates import antimony_to_sbml

        sbml, _err = antimony_to_sbml(src["antimony"])
        if sbml is None:
            return False
        (model / "antimony").put_text(src["antimony"])
        (model / "sbml").put_text(sbml)
        (model / "parameters").put(list(src.get("parameters") or []))
        g = src.get("glossary_from")
        if g and src.get("round") is not None:
            (
                tree.model_node(tree.round_node(root, int(src["round"])), str(g))
                / "glossary"
            ).copy_to(model / "glossary")
        return True
    return False


def restore_revision_assembly(rnd: Node) -> bool:
    """Put a revision round's edited assembly back as its single unit's
    assembly (`candidates/_single/assembly`) when a re-entry moved it aside:
    it is what the revision prepared for S3, an input, not S3's product.
    Returns True when it restored it."""
    s = seeded(rnd)
    if not is_revision(s) or s.get("assembly") is None:
        return False
    target = tree.work_node(rnd, None) / "assembly"
    if target.exists():
        return False
    from octomod.result.slots import AssemblyRecord
    from octomod.result.write import write_record

    write_record(target, AssemblyRecord, s["assembly"])
    return True


def restore_data(root: Node, rnd: Node) -> bool:
    """Put the seeded DATA back when it is missing — the data-module twin of
    `restore_model`.

    `seed_round` copies the source round's `data` into the next round, so in a
    seeded round the measurement table is part of the seed. A `--from-module
    model` re-entry moves the data slot aside with everything downstream; a
    fresh extraction could relabel the conditions so the seeded assembly maps
    none of them. Returns True when it restored anything."""
    s = seeded(rnd)
    if not s:
        return False
    src_round = (s.get("seeded_from") or {}).get("round")
    data = rnd / "data"
    if src_round is None or (data / "measurements").exists():
        return False
    src = tree.round_node(root, int(src_round)) / "data"
    if not (src / "measurements").exists():
        return False
    return src.copy_to(data)


def base_identity(ctx, cand_ids: list[str]) -> dict | None:
    """After S3: is this round's base candidate the problem it was seeded from?

    None for a round that was not seeded from a candidate. Otherwise a record
    that says so, or names every table that differs and the estimated
    parameters gained or lost, so a base that lost what the chosen model
    carried is visible on the card before anything is spent on it."""
    s = seeded(ctx.round)
    source = (s or {}).get("seeded_from") or {}
    if not source.get("candidate"):
        return None
    src_work = tree.work_node(
        tree.round_node(ctx.root, int(source["round"])), str(source["candidate"])
    )
    origin = src_work.key
    if "base" not in cand_ids:
        return {
            "candidate": None,
            "seeded_from": origin,
            "identical": False,
            "why": "no candidate of this round has every axis off",
        }
    base_work = tree.work_node(ctx.round, "base")
    same = _problem_hash(base_work) == source.get("problem") and source.get("problem")
    out = {
        "candidate": "base",
        "seeded_from": origin,
        "identical": bool(same),
        "n_estimated": [
            len(source.get("estimated_parameters") or []),
            len(estimated_parameters(base_work)),
        ],
    }
    if same:
        return out
    theirs = set(source.get("estimated_parameters") or [])
    mine = set(estimated_parameters(base_work))

    def _content(n: Node):
        return n.get(None)

    out["differs_in"] = [
        rel
        for rel in PROBLEM_KEYS
        if _content(src_work / rel) != _content(base_work / rel)
    ]
    out["lost"] = sorted(theirs - mine)
    out["gained"] = sorted(mine - theirs)
    from octomod.workflow_modules.assembly.engine import engine_redraft_this_round

    xml_a = (src_work / "model/sbml").text(None)
    xml_b = (base_work / "model/sbml").text(None)
    encoding = (ctx.round / "model/encoding").get(None)
    if _redraft_asked(ctx):
        out["why"] = (
            "the observation layer was redrafted this round at the human's request"
        )
    elif engine_redraft_this_round(ctx):
        out["why"] = (
            "the observation layer was redrafted this round by the engine, after "
            "a compile failure that named it (the round's `compile_feedback`)"
        )
    elif (
        out["differs_in"] == ["model/sbml"]
        and xml_a is not None
        and xml_b is not None
        and _canonical(xml_a) == _canonical(xml_b)
    ):
        out["why"] = (
            "the SBML differs only in the order of reaction modifiers — the seed "
            "was written before SBML was made canonical, so this run refits it once"
        )
    elif (
        isinstance(encoding, dict)
        and encoding.get("kind") == "supermodel"
        and "model/sbml" in out["differs_in"]
    ):
        out["why"] = (
            "the one-compile encoding built the base with the new axes present "
            "and switched off at their verified neutral values"
        )
    else:
        out["why"] = "unexplained — the seeding should have made them identical"
    return out


def _redraft_asked(ctx) -> bool:
    try:
        from octomod.workflow_modules.assembly.engine import redraft_asked_this_round
    except ImportError:  # the module without the helper: nothing was asked
        return False
    return bool(redraft_asked_this_round(ctx))


def _canonical(xml: str) -> str:
    try:
        from octomod.gates.build_gates import canonical_sbml
    except ImportError:
        return xml
    return canonical_sbml(xml)


def identity_lines(identity: dict | None) -> list[str]:
    """The card's reading of `base_identity`."""
    if not identity:
        return []
    origin = identity["seeded_from"]
    if identity.get("identical"):
        n_seed, _ = identity.get("n_estimated") or [None, None]
        return [
            f"base = {origin} exactly: the same model and the same PEtab tables "
            f"({n_seed} estimated parameters) — its fit is already in the record "
            f"and is reused unless the budget answer asks for more starts or "
            f"other solver settings"
        ]
    if identity.get("candidate") is None:
        return [f"this round was seeded from {origin}, but {identity['why']}"]
    n_seed, n_base = identity.get("n_estimated") or [None, None]
    lines = [
        f"** base is NOT {origin} as seeded: {n_base} estimated parameters "
        f"against {n_seed}; differs in {', '.join(identity.get('differs_in') or []) or '—'} "
        f"— {identity.get('why')} **"
    ]
    if identity.get("lost"):
        lines.append(f"    lost from the seed: {', '.join(identity['lost'])}")
    if identity.get("gained"):
        lines.append(f"    not in the seed: {', '.join(identity['gained'])}")
    return lines
