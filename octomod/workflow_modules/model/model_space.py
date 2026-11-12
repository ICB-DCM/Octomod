"""Model space: the structural questions, written down and searched.

The agents declare the axes they are unsure about; the engine validates them,
enumerates the models, fits them and selects by a criterion; the human decides
at a gate how much of the space to buy. The space is an artifact in the
record (`rounds/round_k/space/axes`).
"""

from __future__ import annotations

import re

from octomod.orchestration.interaction import gate_note
from octomod.result import node as _tree
from octomod.result.slots import AxisRecord
from octomod.result.write import write_records
from octomod.workflow_modules.model import antimony_text as _at

# the two ways a bought set of axes is searched (see `n_models`)
CANDIDATES, LATTICE = "candidates", "lattice"
SEARCH_MODE_KEY = "search_mode"  # in the round's `space/`


def space_path(ctx):
    """The round's declared axes (`rounds/round_k/space/axes`)."""
    return ctx.round / "space/axes"


def dropped_path(ctx):
    """The axes `validate_axes` dropped this round (`space/dropped`)."""
    return ctx.round / "space/dropped"


def dropped_axes(ctx, module: str | None = None) -> list[dict]:
    """Every axis dropped this round, with its reason and author; `module` filters.

    Persisted in `space/dropped` so the gate card can show every drop.
    """
    rows = dropped_path(ctx).get(None) or []
    return [r for r in rows if module is None or r.get("module") == module]


def dropped_axes_card_lines(ctx, module: str | None = None) -> list[str]:
    """One line per dropped axis; one the floor refused reads `⚑ REFUSED`."""
    return [
        (
            f"  ⚑ REFUSED axis {d['id']}: {d.get('reason')}"
            if d.get("refused_floor")
            else f"  axis {d['id']} declared by {d.get('declared_by', '?')}, "
            f"DROPPED: {str(d.get('reason'))[:200]}"
        )
        for d in dropped_axes(ctx, module)
    ]


def declared_axes(ctx, only_live: bool = False) -> list[dict]:
    """This round's declared axes; `only_live` leaves out the frozen ones.

    `frozen` records the last selection, not a deletion: the scope gate sees every
    axis and can re-ask, so a misread note never removes an axis for good.
    """
    axes = space_path(ctx).get(None)
    if axes is None:
        return []
    return [a for a in axes if not a.get("frozen")] if only_live else axes


def patch_steps(patch) -> list[dict]:
    """An axis's Antimony patch as a list of single patches (a dict is a list of one).

    One axis may need several edits (pruning five reactions is one hypothesis).
    `validate_axes` normalises every recorded axis to the list form; `apply_patch`
    and `supermodel.replaced_reactions` also accept a bare dict.
    """
    if not patch:
        return []
    if isinstance(patch, list):
        return [p for p in patch if isinstance(p, dict)]
    return [patch] if isinstance(patch, dict) else []


def undeclared_symbols(base_antimony: str, axis: dict) -> list[str]:
    """Symbols an axis's patch uses without the base or the axis declaring them.

    Checked here because an undeclared symbol yields valid-looking Antimony and a
    roadrunner load failure gates later. Comments are prose, and a reaction id, a
    `species`/`var`/`const` line or an initial value is a declaration, not a use.
    """
    pieces: list[str] = []
    for patch in patch_steps(axis.get("on_antimony_patch")):
        pieces.append(str(patch.get("with", "")))
        app = patch.get("append")
        pieces += [str(x) for x in app] if isinstance(app, list) else [str(app or "")]
    declared_here, lines = _at.split_reaction_declarations("\n".join(pieces))
    body: list[str] = []
    for line in lines:
        # a `species X in cell, Y in cell;` line and an initial value `X = 0;`
        # declare X
        sp = re.match(r"\s*(?:species|var|const)\s+(.*?);?\s*$", line)
        if sp:
            for part in sp.group(1).split(","):
                name = re.match(r"\s*\$?([A-Za-z_]\w*)", part)
                if name:
                    declared_here.add(name.group(1))
            continue
        init = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*[-+0-9.eE]+\s*;?\s*$", line)
        if init:
            declared_here.add(init.group(1))
            continue
        body.append(line)
    used = _at.identifiers(" ".join(body))
    known = _at.identifiers(base_antimony) | _at.KEYWORDS | declared_here
    known |= {str(p.get("id")) for p in (axis.get("adds_parameters") or [])}
    # Antimony's own vocabulary (`time`, the standard functions) needs no declaration
    from octomod.workflow_modules.assembly.assembly_edit import MATH_WORDS

    known |= set(MATH_WORDS)
    return sorted(s for s in used - known if not s.isdigit())


def _required_lost(ctx, base_antimony: str, parameter_ids, axis: dict) -> list:
    """The required reactions an axis's patch takes out of the base, with the
    knowledge module's output in the run (`reaction_evidence.axis_required_lost`);
    [] otherwise, and for a context that cannot say (a validation outside a
    run)."""
    if any(
        getattr(ctx, name, None) is None
        for name in ("root", "testcase", "testcase_dir", "spec")
    ):
        return []
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    return _rxe.axis_required_lost(ctx, base_antimony, parameter_ids, axis)


def declaring_role(module: str) -> str:
    """The agent that declares axes at `module`, for an axis that does not name one.

    Construction declares at S1, the assembly agents at S3 and the expansion
    agent after a selection round; the gate card prints this as the axis's
    author, so an expansion axis is never shown as the assembly agents' own.
    """
    if module == "model":
        return "construction"
    if module.startswith("assembly"):
        return "assembly"
    return module


def validate_axes(
    ctx,
    proposed: list[dict],
    base_antimony: str,
    parameter_ids: set[str],
    module: str,
    base_assembly: dict | None = None,
    dof: tuple[int, int, float] | None = None,
    split_context: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Validate proposed axes before any human pays; return (accepted, dropped).

    An axis is a structural patch (`on_antimony_patch`) or an observation-layer
    patch (`on_assembly_patch`), never both; one that cannot be applied is dropped
    here, named, in the ledger and `dropped_axes.json`. `dof` (n_est, n_data,
    max_ratio) drops an axis over the DOF limit; `split_context` ({condition_values,
    base_parameters, trained_ids}) resolves `split_parameter` axes.
    """
    from octomod.workflow_modules.assembly import assembly_edit

    entities = _at.identifiers(base_antimony or "")
    axes, dropped = [], []
    seen_ids: set[str] = set()
    obs_targets: dict[str, str] = {}
    for i, a in enumerate(proposed or []):
        aid = str(a.get("id") or f"axis_{i}")
        # the one place a patch's shape is normalised: from here on an axis's
        # Antimony patch is a list of steps, in the record and in every reader
        steps = patch_steps(a.get("on_antimony_patch"))
        if steps:
            a = {**a, "on_antimony_patch": steps}
        has_ant = bool(steps)
        has_asm = bool(a.get("on_assembly_patch"))

        _declared_by = a.get("declared_by")

        def drop(reason: str, *, aid: str = aid, declared_by=_declared_by) -> None:
            # aid binds at definition time, so a drop always names the axis of
            # its own iteration even if a later edit defers the call
            dropped.append({"id": aid, "reason": reason})
            ctx.ledger.append(
                "note",
                module=module,
                round_idx=ctx.round_idx,
                note=f"model-space axis {aid!r} dropped: {reason}",
            )
            # persisted for the gate card and for the re-ask that hands the drop
            # back to its author
            p = dropped_path(ctx)
            rows = list(p.get(None) or [])
            rows.append(
                {
                    "id": aid,
                    "reason": reason,
                    "module": module,
                    "declared_by": declared_by or declaring_role(module),
                }
            )
            p.put(rows)

        if aid in seen_ids:
            drop("duplicate axis id")
            continue
        if has_ant and has_asm:
            drop(
                "an axis carries either on_antimony_patch or on_assembly_patch, "
                "never both"
            )
            continue
        if not (has_ant or has_asm):
            continue  # an axis that cannot be applied is a comment, not an axis
        is_split = False
        if has_asm and not has_ant:
            try:
                _k, _args = assembly_edit.patch_kind(a["on_assembly_patch"])
            except ValueError:
                _k, _args = None, {}
            is_split = _k == "split_parameter"
            if is_split and not _args.get("copies_by_condition"):
                # the engine writes the copies before any rule is applied, so the
                # DOF check and the card count them
                sc = split_context or {}
                if (
                    base_assembly is None
                    or sc.get("condition_values") is None
                    or sc.get("base_parameters") is None
                ):
                    drop(
                        "split_parameter is resolved against the data's conditions "
                        "and the base's parameter rows, which exist from the first "
                        "assembly on — propose it at the expansion gate"
                    )
                    continue
                resolved, problems = assembly_edit.resolve_split(
                    _args,
                    base_assembly,
                    sc["condition_values"],
                    sc["base_parameters"],
                    sc.get("trained_ids"),
                )
                if problems:
                    drop("; ".join(problems))
                    continue
                a = {**a, **resolved}
        adds = {str(p.get("id")) for p in (a.get("adds_parameters") or [])}
        if dof is not None:
            # an axis on sparse data would fail the DOF gate after purchase
            n_est, n_data, max_ratio = dof
            n_added = sum(
                1 for p in (a.get("adds_parameters") or []) if p.get("estimate", True)
            )
            if is_split and n_added:
                n_added -= 1  # the split parameter itself leaves the table
            if n_added and (n_est + n_added) / max(n_data, 1) > max_ratio:
                drop(
                    f"adds {n_added} estimated parameter(s): {n_est + n_added}/{n_data} "
                    f"parameters per data point exceeds the DOF limit {max_ratio}"
                )
                continue
        if has_ant:
            missing = undeclared_symbols(base_antimony, a)
            if missing:
                drop(
                    f"its patch uses symbol(s) {missing} that the model does not "
                    f"declare and the axis does not add — a new species must be "
                    f"declared in an `append` block (species, initial value, "
                    f"reactions); `replace_reaction` alone cannot introduce one"
                )
                continue
            # each `replace_reaction` must name a reaction of the model as the
            # earlier steps leave it (a later step may replace an appended one)
            text, bad = base_antimony or "", None
            for step in patch_steps(a.get("on_antimony_patch")):
                rid = step.get("replace_reaction")
                if rid:
                    real, how = resolve_reaction_id(text, str(rid))
                    if real is None:
                        ids = _at.reaction_ids(text)
                        bad = (
                            f"replace_reaction names {rid!r}, which is "
                            f"{'ambiguous among' if how == 'ambiguous' else 'not one of'} "
                            f"the model's reactions: {ids[:40]}"
                        )
                        break
                    if how == "respelt":
                        ctx.ledger.append(
                            "note",
                            module=module,
                            round_idx=ctx.round_idx,
                            note=f"model-space axis {aid!r}: replace_reaction {rid!r} is "
                            f"applied to the model's {real!r} (the only reaction id equal "
                            f"to it ignoring case and underscores)",
                        )
                text, _ok = _apply_step(text, step)
            if bad:
                drop(bad)
                continue
            # a required reaction is the person's: an axis that takes one out
            # of the base is refused whatever it would buy
            lost = _required_lost(ctx, base_antimony, parameter_ids, a)
            if lost:
                from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

                reason = _rxe.required_removal_reason(lost)
                drop(reason)
                note = f"axis {aid!r} refused: {reason}"
                # an offer validated again on a resume refuses it again: one row
                if not any(
                    e.get("event") == "axis_refused_required"
                    and e.get("round") == ctx.round_idx
                    and e.get("note") == note
                    for e in ctx.ledger.entries()
                ):
                    ctx.ledger.append(
                        "axis_refused_required",
                        module=module,
                        round_idx=ctx.round_idx,
                        axis=aid,
                        reactions=[x.get("reaction_id") for x in lost],
                        required=[x.get("id") for x in lost],
                        note=note,
                    )
                continue
            kind = "structure"
        else:
            problems = assembly_edit.validate_patch(
                a["on_assembly_patch"],
                model_entities=entities,
                parameter_ids=set(parameter_ids) | adds,
                adds=adds,
                assembly=base_assembly,
            )
            if problems:
                drop("; ".join(problems))
                if any("reinterprets the data" in pr for pr in problems):
                    # refused as an axis, but put to the human as a numbered
                    # question on the next gate card
                    from octomod.orchestration.interaction import questions as _q

                    args = next(iter(a["on_assembly_patch"].values()), {})
                    target = (
                        args.get("condition_id") or args.get("condition_label") or "?"
                    )
                    _q.raise_for_human(
                        ctx,
                        topic=f"condition {target}",
                        question=(
                            f"the agent proposed changing what condition "
                            f"{target!r} MEANS (axis {aid!r}: "
                            f"{assembly_edit.describe(a['on_assembly_patch'])[:120]}) "
                            f"— refused as a search axis. Re-stage the data "
                            f"with that reading, or keep the encoding as is?"
                        ),
                        raised_by=module,
                        detail=str(a.get("rationale", ""))[:200],
                    )
                continue
            try:
                k, args = assembly_edit.patch_kind(a["on_assembly_patch"])
            except ValueError as e:
                drop(str(e))
                continue
            targets = assembly_edit.patch_targets(a["on_assembly_patch"])
            clash = next((t for t in targets if t in obs_targets), None)
            if clash is not None:
                # one observation axis per observable per round; a group
                # `change_scaling` claims each observable it names
                drop(
                    f"a second observation axis on {clash!r} (already "
                    f"{obs_targets[clash]!r}); one observation axis per "
                    f"observable per round"
                )
                continue
            for target in targets:
                obs_targets[str(target)] = aid
            kind = "parameter_split" if is_split else "observation"
        seen_ids.add(aid)
        try:  # 1 = most load-bearing; declaration order when not given
            priority = int(a.get("priority"))
            if priority < 1:
                raise ValueError
        except (TypeError, ValueError):
            priority = len(axes) + 1
        axes.append(
            {
                "id": aid,
                "kind": kind,
                "question": a.get("question", ""),
                "default": "on" if str(a.get("default", "off")) == "on" else "off",
                "priority": priority,
                "priority_reason": str(a.get("priority_reason", "") or ""),
                "on_antimony_patch": a.get("on_antimony_patch"),
                "on_assembly_patch": a.get("on_assembly_patch"),
                "adds_parameters": a.get("adds_parameters") or [],
                "rationale": a.get("rationale", ""),
                "discriminating_evidence": a.get("discriminating_evidence", ""),
                # which agent proposed it: construction, assembly or expansion
                "declared_by": a.get("declared_by") or declaring_role(module),
                # an expansion axis says what proposed it: the residuals, or
                # the biology (the packs, the literature); construction's and
                # the assembly agents' axes come before any fit and carry none
                **({"origin": axis_origin(a)} if module == "revision" else {}),
                "frozen": False,
            }
        )
    return axes, dropped


# where an expansion axis came from, as its card line says it
ORIGINS = {"residual": "the residuals", "biology": "the biology"}


def axis_origin(axis: dict) -> str:
    """`biology` when the expansion agent says the axis came from the biology
    (the domain packs, the literature), else `residual` — the default, for an
    absent or unrecognised value too."""
    return (
        "biology"
        if str(axis.get("origin") or "").strip().lower() == "biology"
        else "residual"
    )


def expansion_axis_lines(axes: list[dict]) -> list[str]:
    """The expansion card's lines for its axes: rank, id, kind, where the axis
    came from (an axis that records an origin), the question, why this rank,
    and what separates on from off."""
    lines: list[str] = []
    for a in axes:
        origin = a.get("origin")
        came_from = f" (from {ORIGINS[origin]})" if origin in ORIGINS else ""
        lines.append(
            f"  {a.get('priority', '?')}. {a.get('id')} [{a.get('kind')}]"
            f"{came_from}: {str(a.get('question'))[:150]}"
        )
        if a.get("priority_reason"):
            lines.append(f"      why this rank: {str(a['priority_reason'])[:150]}")
        lines.append(
            f"      separated by: {str(a.get('discriminating_evidence'))[:150]}"
        )
    return lines


BEYOND_KEYS = ("mechanism", "why_not_separable", "experiment")


def beyond_this_data(proposal: dict | None) -> list[dict]:
    """The expansion reply's `beyond_this_data`: mechanisms the agent thinks
    act in the system but this data cannot separate, each with why and the
    experiment that would. Entries without a mechanism are dropped; a reply
    without the field (every stub) has none."""
    out: list[dict] = []
    for e in (proposal or {}).get("beyond_this_data") or []:
        if not isinstance(e, dict):
            continue
        entry = {k: " ".join(str(e.get(k) or "").split()) for k in BEYOND_KEYS}
        if entry["mechanism"]:
            out.append(entry)
    return out


def beyond_card_lines(items: list[dict]) -> list[str]:
    """The expansion card's block for what lies beyond this data, or [] when
    the agent named nothing."""
    if not items:
        return []
    lines = [
        "BEYOND THIS DATA — mechanisms the agent names that this data cannot "
        "separate (not axes; nothing here is bought; recorded in expansion.json):"
    ]
    for e in items:
        lines.append(f"  · {e['mechanism'][:200]}")
        if e.get("why_not_separable"):
            lines.append(f"      not separable here: {e['why_not_separable'][:200]}")
        if e.get("experiment"):
            lines.append(f"      the experiment that would: {e['experiment'][:200]}")
    return lines


def ladder_check(
    antimony: str, parameters: list[dict], t_end: float, spec, required_entities=None
) -> tuple[bool, list[str]]:
    """Run the S1 build and simulation gates quietly on one model: (passed, details).

    No gate verdicts, no ledger rows, no compile (roadrunner only): cheap enough to
    run on a whole proposed space before a human pays for it.
    """
    from octomod.gates.build_gates import make_build_gates
    from octomod.gates.sim_gates import make_sim_gates

    holder: dict = {}
    failures: list[str] = []
    try:
        for g in make_build_gates(antimony, holder):
            r = g()
            if not r.passed and r.blocking:
                return False, [r.detail]
        est_bounds = {
            p["id"]: (float(p["lb"]), float(p["ub"]))
            for p in parameters
            if p.get("estimate") and p.get("lb") is not None
            # an observation axis's parameters (a condition's copy, a split's
            # copies) are not in the model, and the box gate sets every id it gets
            and p.get("layer") != "assembly"
        }
        for g in make_sim_gates(
            holder["sbml"], t_end, est_bounds, spec, required_entities=required_entities
        ):
            r = g()
            if not r.passed and r.blocking:
                failures.append(r.detail)
    except Exception as e:  # a crashing check is a failed check
        failures.append(f"{type(e).__name__}: {e}")
    return not failures, failures


def pregate_ladder(
    ctx,
    base_antimony: str,
    base_parameters: list[dict],
    axes: list[dict],
    max_models: int,
    t_end: float,
    module: str,
    *,
    mode: str = LATTICE,
) -> tuple[list[dict], list[dict], int, list[dict]]:
    """Run the ladder on every model of the proposed space before the human gate.

    An axis whose every combination fails is dropped, named; a failing combination
    of otherwise viable axes is reported (it is dropped at enumeration). Returns
    (viable axes, dropped [{id, reason}], n_viable_models, failing_combinations).
    """
    models = enumerate_models(
        base_antimony,
        base_parameters,
        axes,
        max_models,
        t_end=t_end,
        one_at_a_time=(mode == CANDIDATES),
    )
    results = {}
    for m in models:
        ok, why = ladder_check(
            m["antimony"],
            m["parameters"],
            t_end,
            ctx.spec,
            required_entities=ctx.intent.get("required_entities"),
        )
        results[m["model_id"]] = (ok, why, m["axes_on"])
    dropped, viable = [], []
    for a in axes:
        carrying = [
            (mid, ok, why) for mid, (ok, why, on) in results.items() if a["id"] in on
        ]
        if carrying and not any(ok for _, ok, _ in carrying):
            why = next((w for _, ok, w in carrying if w), ["unknown failure"])
            reason = (
                f"every combination carrying {a['id']!r} fails the pre-compile "
                f"ladder: {why[0][:160]}"
            )
            dropped.append({"id": a["id"], "reason": reason})
            ctx.ledger.append(
                "note",
                module=module,
                round_idx=ctx.round_idx,
                note=f"model-space axis {a['id']!r} dropped: {reason}",
            )
        else:
            viable.append(a)
    failing = [
        {"model_id": mid, "axes_on": on, "reason": why[0][:160]}
        for mid, (ok, why, on) in results.items()
        if not ok and all(x in {v["id"] for v in viable} for x in on)
    ]
    if failing:
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"pre-gate ladder: {len(failing)} combination(s) of viable "
            f"axes fail and will be dropped at enumeration: "
            f"{[f['model_id'] for f in failing]}",
        )
    n_viable = sum(
        1
        for mid, (ok, _, on) in results.items()
        if ok and all(x in {v["id"] for v in viable} for x in on)
    )
    return viable, dropped, n_viable, failing


def by_priority(axes: list[dict]) -> list[dict]:
    """Priority order, 1 first; declaration order breaks ties."""
    return sorted(axes, key=lambda a: (int(a.get("priority", 10**6)), 0))


# A bought set of axes is searched as candidates, the base plus each axis on its
# own (k+1 models), unless the spec (`search.lattice: true`) or the gate note
# (`lattice`) asks for every on/off combination (2^k).
def n_models(k: int, mode: str) -> int:
    """How many models k searched axes are, in `mode`."""
    return 2**k if mode == LATTICE else k + 1


def search_mode(ctx) -> str:
    """This round's search mode: what a gate recorded for it, else the spec."""
    recorded = search_mode_node(ctx.round).get(None)
    if isinstance(recorded, dict):
        mode = str(recorded.get("mode", ""))
        if mode in (CANDIDATES, LATTICE):
            return mode
    return LATTICE if ctx.spec.get("search.lattice", False) else CANDIDATES


def search_mode_node(rnd):
    """Where a gate's recorded search mode lives: `rounds/round_k/space/search_mode`."""
    return rnd / "space" / SEARCH_MODE_KEY


def record_search_mode(rnd, mode: str, source: str) -> None:
    """`rnd`: the round node (`ctx.round`)."""
    search_mode_node(rnd).put({"mode": mode, "source": source})


def lattice_requested(note: str | None) -> bool:
    """`lattice` on its own, or `search: lattice`, in a gate note (gate_note rules)."""
    from octomod.orchestration.interaction import gate_note

    return bool(gate_note.standalone(note, ["lattice"])) or (
        (gate_note.key_value(note, "search") or "").lower().startswith("lattice")
    )


def search_mode_line(k: int, mode: str) -> str:
    """How the card states what k bought axes cost, in both modes."""
    if mode == LATTICE:
        return (
            f"{n_models(k, LATTICE)} model(s): every on/off combination of the "
            f"{k} axis/axes (one at a time would be {n_models(k, CANDIDATES)})"
        )
    return (
        f"{n_models(k, CANDIDATES)} model(s): the base plus each axis on its own "
        f"(`lattice` in the note buys every combination: {n_models(k, LATTICE)})"
    )


def max_axes(max_models: int, mode: str = LATTICE) -> int:
    """How many axes the hard ceiling admits: 2^n <= max_models for a lattice,
    n + 1 <= max_models one axis at a time."""
    if mode == CANDIDATES:
        return max(int(max_models) - 1, 0)
    n = 0
    while 2 ** (n + 1) <= max(int(max_models), 1):
        n += 1
    return n


def cap_axes(
    live: list[dict],
    max_models: int,
    undecided_ids: set[str] | None = None,
    *,
    mode: str = LATTICE,
) -> tuple[list[dict], list[dict]]:
    """Enforce the ceiling: undecided axes first, then priority; (kept, dropped)."""
    n_max = max_axes(max_models, mode)
    undecided = set(undecided_ids or ())
    ordered = sorted(
        live,
        key=lambda a: (0 if a["id"] in undecided else 1, int(a.get("priority", 10**6))),
    )
    return ordered[:n_max], ordered[n_max:]


def parse_recommended_tier(
    construction: dict | None, n_axes: int, already_bought: bool = False
) -> dict:
    """The agent's recommended tier: how many axes it considers necessary.

    With `already_bought` (the axes were approved at an expansion gate) the default
    is all of them. `source` is "agent" when the reply carried a recommendation,
    "engine" for a default.
    """
    rec = (construction or {}).get("recommended_tier")
    tier, reasoning = None, ""
    if isinstance(rec, dict):
        tier = str(rec.get("tier", "")).strip().lower()
        reasoning = str(rec.get("reasoning", "") or "")
    elif isinstance(rec, str):
        tier = rec.strip().lower()
    k = None
    if tier in ("base", "none", "0", "top0"):
        k = 0
    elif tier and tier.startswith("top"):
        try:
            k = int(tier[3:].strip() or 0)
        except ValueError:
            k = None
    elif tier in ("all", "*"):
        k = n_axes
    if k is None:
        if already_bought:
            return {
                "k": n_axes,
                "label": f"top{n_axes}",
                "given": False,
                "source": "engine",
                "already_bought": True,
                "reasoning": "these axes were bought at the expansion gate of "
                "the previous round; searching all of them is what "
                "that purchase means",
            }
        return {
            "k": 0,
            "label": "base",
            "given": False,
            "source": "engine",
            "already_bought": False,
            "reasoning": "no tier recommendation was returned, so the engine "
            "defaults to base: one model, whose fits and residuals "
            "are read before any lattice is bought",
        }
    k = max(0, min(k, n_axes))
    return {
        "k": k,
        "label": "base" if k == 0 else f"top{k}",
        "reasoning": reasoning,
        "given": True,
        "source": "agent",
        "already_bought": already_bought,
    }


def tier_card_lines(
    axes: list[dict],
    max_models: int,
    recommended: dict,
    unit: str = "one calibration each",
    *,
    mode: str = LATTICE,
) -> list[str]:
    """The scope-gate tiers: base only · top-k · all, each with its model
    count in this round's search mode, the agent's recommendation, and how to
    answer."""
    ordered = by_priority(axes)
    n_max = max_axes(max_models, mode)
    lines = [
        "",
        "OPEN AXES the agent is unsure about — testable against the data "
        "rather than decided by opinion (priority order, 1 = most load-bearing):",
    ]
    for a in ordered:
        lines.append(
            f"  {a.get('priority', '?')}. {a['id']} [{a.get('kind', 'structure')}] "
            f"(base = {a['default']}): {str(a.get('question', ''))[:150]}"
        )
        if a.get("priority_reason"):
            lines.append(f"       why this rank: {str(a['priority_reason'])[:150]}")
        if a.get("discriminating_evidence"):
            lines.append(
                f"       separated by: {str(a['discriminating_evidence'])[:150]}"
            )
    lines.append(
        f"TIERS ({unit}; hard ceiling search.max_models = {max_models} "
        f"-> at most {n_max} axes searched at once"
        + (
            f"; {max_axes(max_models, LATTICE)} as a lattice"
            if mode == CANDIDATES
            else ""
        )
        + "):"
    )
    lines.append(
        "  tier: base   -> 1 model   — reconnaissance: get one model working, "
        "read its fits and residuals, let the expansion loop propose from evidence"
    )
    for k in range(1, len(ordered) + 1):
        ids = [a["id"] for a in ordered[:k]]
        over = (
            ""
            if k <= n_max
            else f"   (over the ceiling: only the top {n_max} would be searched)"
        )
        label = f"top{k}" if k < len(ordered) else f"all (= top{k})"
        lines.append(
            f"  tier: {label:5s}-> {n_models(k, mode)} model(s) — axes: {', '.join(ids)}{over}"
        )
    who = (
        "agent recommends"
        if recommended.get("source") == "agent"
        else "no recommendation from the agent; the engine defaults to"
    )
    lines.append(
        f"  {who}: {recommended['label']} "
        f"({n_models(recommended['k'], mode) if recommended['k'] else 1} model(s)) — "
        f"{recommended['reasoning'][:220]}"
    )
    lines.append(
        f"  search: {'one axis at a time on the base' if mode == CANDIDATES else 'every on/off combination'}"
        f" — for all bought axes, {search_mode_line(len(ordered), mode)}"
    )
    if recommended.get("already_bought"):
        lines.append(
            "  -> these axes were APPROVED at the expansion gate; answering "
            "nothing searches all of them. A tier or axes list here narrows "
            "that purchase; 'n' stops the run."
        )
    else:
        lines.append(
            "  -> answer in the note:  tier: base  |  tier: top<k>  |  "
            "tier: all  |  axes: <id>, <id>   (no instruction = no search, "
            "nothing is spent)"
        )
    return lines


# The roles that declare axes at S3; `record_assembly_axes` names each axis's
# author by the reply it came from.
ASSEMBLY_ROLES = ("observation", "condition")


def assembly_observation_axes(ctx, structures: list[str]) -> list[dict]:
    """The live observation axes the assembly agents declared and no structure
    in `structures` carries: the observation layer's open choices, as the
    compile card shows them.

    An axis a structure id carries (`base+<axis>`) was bought and is fitted as
    that structure, so it is not an open choice beside it."""
    authors = set(ASSEMBLY_ROLES) | {declaring_role("assembly")}
    bought = {part for s in structures for part in str(s).split("+")}
    return [
        a
        for a in declared_axes(ctx, only_live=True)
        if a.get("kind") == "observation"
        and a.get("declared_by") in authors
        and a.get("id") not in bought
    ]


def combined_space_card_lines(
    structures: list[str], obs_axes: list[dict], max_models: int
) -> list[str]:
    """The second scope card: chosen structures crossed with the observation axes.

    Every combination is numbered so a person can pick by hand. Plain `y` fits the
    structures against the agents' chosen observation model, so an unattended
    answer never buys the cross-product.
    """
    if not obs_axes:
        return []
    ordered = by_priority(obs_axes)
    n_full = len(structures) * (2 ** len(ordered))
    lines = [
        "",
        "THE OBSERVATION LAYER is a modelling choice too. The assembly agents "
        "declared where they judge more than one reading DEFENSIBLE:",
    ]
    for a in ordered:
        lines.append(
            f"  {a.get('priority', '?')}. {a['id']} (base = {a.get('default', 'off')})"
            f": {str(a.get('question', ''))[:140]}"
        )
        lines.append(f"       declared by: {a.get('declared_by', 'assembly')}")
    lines.append(
        f"COMBINATIONS ({len(structures)} structure(s) x "
        f"{2 ** len(ordered)} observation variant(s) = {n_full}):"
    )
    combos = _combination_labels(structures, ordered)
    shown = combos if len(combos) <= 24 else combos[:24]
    for i, label in enumerate(shown, 1):
        lines.append(f"  {i:>3}. {label}")
    if len(shown) < len(combos):
        lines.append(f"   ... and {len(combos) - len(shown)} more (see the report)")
    lines += [
        f"  THIS ROUND fits the {len(structures)} structure(s) against the "
        f"observation model the agents chose — sequential, {len(structures)} "
        f"fit(s). The axes above are RECORDED, not bought: they are offered at "
        f"the expansion gate, where the residuals can argue for them.",
        "  CAVEAT, and the reason you are shown this at all: a structure "
        "ranking is CONDITIONAL on the observation model it was fitted with. "
        "If every candidate fits badly, suspect the observation layer before "
        "concluding anything about the mechanism.",
    ]
    if n_full > max_models:
        lines.append(
            f"  (the full cross-product would be {n_full} fits, over "
            f"search.max_models = {max_models})"
        )
    return lines


def _combination_labels(structures: list[str], axes: list[dict]) -> list[str]:
    """Every (structure, axis on/off) pair, in the order the enumerator uses,
    so the number a human types means the same model the engine builds."""
    import itertools

    out = []
    for st in structures:
        for bits in itertools.product((0, 1), repeat=len(axes)):
            on = [a["id"] for a, b in zip(axes, bits, strict=False) if b]
            out.append(f"{st}  +  {', '.join(on) if on else 'base observation model'}")
    return out


def axes_for_gate(ctx, construction: dict | None) -> tuple[list[dict], dict | None]:
    """This round's declared axes for the card that prices them, and their reply.

    A fresh reply is validated and recorded now. On a resume the space is read
    back from the record, or, if the previous pass died before `record_axes`,
    re-validated from the cached construction reply (no new agent call). The
    reply is None on a resume that has none.
    """
    if construction is None and not space_path(ctx).exists():
        cached = ctx.agent_calls.child("construction") / "reply"
        if cached.exists():
            construction = cached.get()
            ctx.ledger.append(
                "note",
                module="model",
                round_idx=ctx.round_idx,
                note="model space was never recorded; re-validated from the "
                "saved construction reply (no new agent call)",
            )
    if construction is not None:
        return record_axes(ctx, construction), construction
    return declared_axes(ctx), None


def record_axes(ctx, construction: dict) -> list[dict]:
    """Persist the construction agent's declared axes. Called at S1, before
    the scope gate, so the gate can ask which of them to buy."""
    base = construction.get("antimony", "")
    base_asm = (ctx.round / "shared_assembly").get(None)
    # a draft's space, drops included, replaces the previous draft's
    dp = dropped_path(ctx)
    if dp.exists():
        rows = dp.get(None) or []
        dp.put([r for r in rows if r.get("module") != "model"])
    space_path(ctx).delete()
    axes, _dropped = validate_axes(
        ctx,
        construction.get("model_space") or [],
        base,
        {str(p.get("id")) for p in (construction.get("parameters") or [])},
        module="model",
        base_assembly=base_asm,
    )
    axes = _hold_to_variants_floor(ctx, axes, base, construction.get("parameters"))
    if axes:
        write_records(space_path(ctx), AxisRecord, axes)
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"model space declared: {[a['id'] for a in axes]}",
        )
    return axes


def _hold_to_variants_floor(
    ctx, axes: list[dict], base_antimony: str, base_parameters
) -> list[dict]:
    """The axes construction declared, held to the variants' floor with the
    knowledge module's output in the run (`reaction_evidence.hold_declared_axes`):
    a refused axis is dropped with its reason in `space/dropped`
    (`refused_floor`), one `axis_refused_floor` row per axis and floor, and
    kept in `space/declared`, from where a later expansion offers it again,
    annotated at that round's floor. The axes kept are returned."""
    if any(
        getattr(ctx, name, None) is None
        for name in ("root", "testcase", "testcase_dir", "spec")
    ):
        return axes
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    kept, refused = _rxe.hold_declared_axes(
        ctx, axes, base_antimony, list(base_parameters or [])
    )
    declared = ctx.round / "space/declared"
    if refused:
        declared.put([r["axis"] for r in refused])
    elif declared.exists():
        declared.delete()
    if not refused:
        return kept
    p = dropped_path(ctx)
    rows = list(p.get(None) or [])
    seen = {
        (e.get("axis"), e.get("floor"))
        for e in ctx.ledger.entries()
        if e.get("event") == "axis_refused_floor"
        and e.get("round") == ctx.round_idx
        and e.get("module") == "model"
    }
    for r in refused:
        aid = str(r["axis"]["id"])
        refs = r["reactions"]
        rows.append(
            {
                "id": aid,
                "reason": r["reason"],
                "module": "model",
                "declared_by": r["axis"].get("declared_by") or declaring_role("model"),
                "refused_floor": {"floor": r["floor"], "reactions": refs},
            }
        )
        if (aid, r["floor"]) in seen:
            continue
        ctx.ledger.append(
            "axis_refused_floor",
            module="model",
            round_idx=ctx.round_idx,
            axis=aid,
            reaction=refs[0].get("reaction_id") if refs else None,
            band=refs[0].get("band") if refs else None,
            reactions=[x.get("reaction_id") for x in refs],
            bands=[x.get("band") for x in refs],
            floor=r["floor"],
            note=f"refused from the declared space: axis {aid}: {r['reason']}",
        )
    p.put(rows)
    return kept


def _drop_malformed(
    ctx, role: str, aid: str, reason: str, module: str = "assembly"
) -> None:
    """Record an unreadable axis declaration exactly like a `validate_axes` drop."""
    ctx.ledger.append(
        "note",
        module=module,
        round_idx=ctx.round_idx,
        note=f"model-space axis {aid!r} dropped: {reason}",
    )
    p = dropped_path(ctx)
    rows = list(p.get(None) or [])
    rows.append({"id": aid, "reason": reason, "module": module, "declared_by": role})
    p.put(rows)


def record_assembly_axes(ctx, replies: dict, base_antimony: str, base_params) -> list:
    """Persist observation-layer axes declared by the assembly agents.

    They are appended to what S1 declared, never replacing it; the human is asked
    about the combination at the cost boundary.
    """
    proposed: list[dict] = []
    for role, reply in (replies or {}).items():
        declared = (reply or {}).get("model_space") or []
        # The contract's model_space is a list of axis objects; `{"axes": [...]}`
        # is read, any other shape is a dropped declaration with a reason.
        if isinstance(declared, dict):
            inner = declared.get("axes")
            ctx.ledger.append(
                "note",
                module="assembly",
                round_idx=ctx.round_idx,
                note=f"{role}: model_space given as an object, not a list"
                + (
                    " — its 'axes' list is read"
                    if isinstance(inner, list)
                    else " and carries no 'axes' list — ignored"
                ),
            )
            declared = inner if isinstance(inner, list) else []
        if not isinstance(declared, list):
            _drop_malformed(
                ctx,
                role,
                f"{role}_model_space",
                f"model_space is a {type(declared).__name__}, not a list of axes",
            )
            continue
        for i, a in enumerate(declared):
            if not isinstance(a, dict):
                _drop_malformed(
                    ctx,
                    role,
                    f"{role}_axis_{i}",
                    f"malformed axis declaration ({type(a).__name__}, not an object)",
                )
                continue
            a = dict(a)
            if "id" not in a and a.get("axis_id"):
                a["id"] = str(a["axis_id"])  # the contract's key; `axis_id` is kept too
            a.setdefault("declared_by", role)
            proposed.append(a)
    if not proposed:
        return []
    shared = ctx.round / "shared_assembly"
    axes, dropped = validate_axes(
        ctx,
        proposed,
        base_antimony,
        {str(p.get("id")) for p in (base_params or [])},
        module="assembly",
        base_assembly=shared.get(None),
    )
    if not axes:
        return []
    path = space_path(ctx)
    existing = path.get(None) or []
    known = {a["id"] for a in existing}
    fresh = [a for a in axes if a["id"] not in known]
    if fresh:
        write_records(path, AxisRecord, existing + fresh)
        ctx.ledger.append(
            "note",
            module="assembly",
            round_idx=ctx.round_idx,
            note=(
                f"assembly declared {len(fresh)} observation-layer axis(es): "
                f"{[a['id'] for a in fresh]}"
                + (f"; dropped {[d['id'] for d in dropped]}" if dropped else "")
            ),
            declared_by="assembly",
        )
    return fresh


def freeze_axes(ctx, keep_ids: set[str] | None) -> None:
    """Human's answer at the scope gate: axes not kept are frozen at their
    default and excluded from the search. `None` keeps everything."""
    path = space_path(ctx)
    if keep_ids is None:
        return
    axes = path.get(None)
    if axes is None:
        return
    for a in axes:
        a["frozen"] = a["id"] not in keep_ids
    write_records(path, AxisRecord, axes)
    frozen = [a["id"] for a in axes if a["frozen"]]
    if frozen:
        ctx.ledger.append(
            "note",
            module="model",
            round_idx=ctx.round_idx,
            note=f"human froze model-space axes {frozen} at their "
            f"defaults; they are not searched",
        )


def parse_axis_selection(note: str, axes: list[dict]) -> set[str] | None:
    """Read the human's scope-gate note for an axis selection.

    Accepts 'axes: a, b', 'axes: all', 'axes: none', or bare axis ids. Absent
    any of those, returns None = keep the agent's proposal untouched. The
    parser is deliberately dumb: an unparsed note must never silently drop an
    axis, it must leave the space as declared.
    """
    if not note:
        return None
    tokens = gate_note.key_list(note, "axes", "axis")
    word = gate_note.tier(note)
    if word and tokens is None:
        # the human buys a tier: base (no search), the top-k axes by the agent's
        # priority, or all. An explicit `axes:` list wins when both appear.
        if word in ("base", "none"):
            return set()
        if word == "all":
            return {a["id"] for a in axes}
        return {a["id"] for a in by_priority(axes)[: int(word[3:])]}
    if tokens is None:
        # bare axis ids count only when they stand alone: an id inside a
        # sentence is prose
        named = gate_note.standalone(note, [a["id"] for a in axes])
        return named or None
    tokens = [t.lower() for t in tokens]
    # the first token decides a collective word: "axes: all - the enlarged space"
    # means all of them
    if tokens and tokens[0] in ("all", "*", "everything"):
        return {a["id"] for a in axes}
    if tokens and tokens[0] in ("none", "-", "no", "nothing"):
        return set()
    hit = {a["id"] for a in axes if a["id"].lower() in set(tokens)}
    # nothing recognised: the space stays as declared (an id elsewhere in the
    # note is prose and selects nothing)
    return hit or None


def base_overlay_after_carry(winner_overlay: list, carried: list[dict]) -> list:
    """The observation-layer patches a next round's base inherits from the winner.

    Every patch of the winner's overlay except those of axes carried live again
    (undecided), which the search switches itself; a decided observation axis
    must not revert in the next round.
    """
    live = [
        a.get("on_assembly_patch")
        for a in (carried or [])
        if a.get("on_assembly_patch")
    ]
    return [o for o in (winner_overlay or []) if o not in live]


def human_added_axes(
    note: str | None, axes: list[dict], pool: dict[str, dict]
) -> list[dict]:
    """Axes the note's `axes:` list names from earlier in the run (`pool`, id -> axis).

    Only axes not on this round's card, so one dropped at the ceiling can be bought
    back. Returned axes are marked `human_added` and unfrozen; the caller validates
    structural ones against the base and persists the round's list.
    """
    tokens = [t.lower() for t in gate_note.key_list(note, "axes", "axis") or []]
    if not tokens:
        return []
    here = {str(a.get("id")).lower() for a in axes}
    by_lower = {k.lower(): v for k, v in pool.items()}
    out: list[dict] = []
    seen: set[str] = set()
    for tok in tokens:
        if tok in here or tok in seen or tok not in by_lower:
            continue
        seen.add(tok)
        out.append({**by_lower[tok], "frozen": False, "human_added": True})
    return out


MODEL_SELECTION_FORM = (
    "models: 6, 9, 10       fit exactly these, by their number in the list "
    "above (ranges like 6-9 work)"
)


def parse_model_selection(note: str, n_models: int) -> list[int] | None:
    """Which enumerated models the human picked by number (`models: 6, 9, 10`).

    Returns 1-based indices as printed, sorted and de-duplicated (ranges like 6-9
    work), or None when the note does not pick. An index outside the list is
    dropped, not clamped.
    """
    if not note or n_models <= 0:
        return None
    m = re.search(r"\bmodels?\s*[:=]\s*([^\n;]*)", str(note), re.I)
    if not m:
        return None
    body = m.group(1).strip().lower()
    if body.startswith(("all", "*", "everything")):
        return list(range(1, n_models + 1))
    picked: set[int] = set()
    for tok in re.split(r"[,\s]+", body):
        if not tok:
            continue
        rng = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", tok)
        if rng:
            lo, hi = int(rng.group(1)), int(rng.group(2))
            picked.update(range(min(lo, hi), max(lo, hi) + 1))
            continue
        if tok.isdigit():
            picked.add(int(tok))
    inside = sorted(i for i in picked if 1 <= i <= n_models)
    return inside or None


def search_topology(
    declared: list[dict], fitted: list[dict], *, mode: str | None = None
) -> dict:
    """How much of the union lattice the search visited.

    The search is local within a round (one axis at a time on the base, or every
    combination with `lattice`) and greedy across rounds. A fitted model sits at
    its actual corner: its base's corner (minus axes re-declared live) plus its own
    axes. A model that is not an axis combination is listed outside the lattice
    with its round and outcome; a lattice anchored on one has it as its root.
    """
    axis_ids = {str(a.get("id")) for a in declared or []}
    rows = sorted(fitted or [], key=lambda r: int(r.get("round") or 0))
    place: dict[tuple[int, str], tuple[str, frozenset] | None] = {}
    points: dict[str, set] = {}
    outside, outside_status = [], []
    for row in rows:
        r, mid = int(row.get("round") or 0), str(row.get("model") or "")
        if not mid:
            continue
        base = str(row.get("base_model") or "")
        if r == 0 or not base or base == "round-0 base":
            root, bc = "the round-0 base", frozenset()
        else:
            parent = place.get((r - 1, base))
            if parent is None:
                root, bc = f"{base} (round {r - 1})", frozenset()
            else:
                root = parent[0]
                bc = parent[1] - set(row.get("base_carried_undecided") or [])
        tokens = [t for t in mid.split("+") if t]
        if mid == "base" or (tokens and all(t in axis_ids for t in tokens)):
            pt = (root, bc | (frozenset() if mid == "base" else frozenset(tokens)))
            place[(r, mid)] = pt
            points.setdefault(root, set()).add(pt[1])
        else:
            place[(r, mid)] = None
            outside.append(mid)
            nllh = row.get("nllh")
            outside_status.append(
                f"{mid} (round {r}, fitted"
                + (
                    f", -log L {float(nllh):.2f}"
                    if isinstance(nllh, (int, float))
                    else ""
                )
                + (", selected" if row.get("selected") else "")
                + ")"
            )
    n = len(axis_ids)
    total = 2**n if n else 0
    latest_root = None
    for row in reversed(rows):
        pt = place.get((int(row.get("round") or 0), str(row.get("model") or "")))
        if pt is not None:
            latest_root = pt[0]
            break
    visited = len(points.get(latest_root, set())) if latest_root else 0
    within = (
        "one axis at a time on each round's base"
        if mode == CANDIDATES
        else "exhaustive within a round" if mode == LATTICE else "local within a round"
    )
    return {
        "n_axes_declared": n,
        "union_lattice_models": total,
        "visited": visited,
        "visited_fraction": (round(visited / total, 4) if total else None),
        "lattice_root": latest_root,
        "visited_by_root": {k: len(v) for k, v in sorted(points.items())},
        "models_outside_the_lattice": sorted(set(outside)),
        "outside_status": outside_status,
        "search_mode": mode,
        "topology": f"{within}, greedy across rounds",
        "note": (
            "the union space over every axis declared in this run is "
            f"{total or 'not defined (no axes declared)'} models; the search "
            f"visited {visited} of them"
            + (
                f", on {latest_root}"
                if latest_root and latest_root != "the round-0 base"
                else ""
            )
            + ". Corners never visited are not evidence against — they were "
            "not tried. The same family as stepwise/FAMoS."
        ),
    }


def comparability_regime(root) -> dict:
    """Whether criterion values are comparable across rounds in this run.

    Not in the general loop, where a revision move can change the observation
    model; yes in a pure expansion run, which carries the data and the shared
    assembly forward unchanged and only enlarges the model space.
    `root`: the run record's root node.
    """
    rounds = [_tree.round_node(root, k) for k in _tree.round_indices(root)]
    if len(rounds) <= 1:
        return {
            "across_rounds": True,
            "regime": "single round",
            "why": "one round, so there is no cross-round comparison to caveat",
        }
    revised = [d.name for d in rounds if (d / "revision").exists()]
    gaps = []
    for prev, cur in zip(rounds, rounds[1:], strict=False):
        rec = prev / "expansion"
        ok = False
        try:
            ok = bool((rec.get(None) or {}).get("expanded"))
        except Exception:  # an unreadable record is no record
            ok = False
        if not ok:
            gaps.append(f"{cur.name} did not come from an expansion of {prev.name}")
    if revised or gaps:
        return {
            "across_rounds": False,
            "regime": "general loop",
            "why": "; ".join(
                ([f"revision moves in {revised}"] if revised else []) + gaps
            )
            + " — an S11 move can change the observation model, and a criterion "
            "over different data is not comparable",
        }
    return {
        "across_rounds": True,
        "regime": "pure expansion",
        "why": (
            f"every round after the first came from an expansion, which copies "
            f"the data and the shared assembly forward unchanged and only "
            f"enlarges the model space: the criterion is over the same data in "
            f"all {len(rounds)} rounds, so the values ARE comparable across them"
        ),
    }


def undecided_axes(models: list[dict], indistinguishable: list[str]) -> list[str]:
    """Axes the statistically indistinguishable set disagrees on.

    The data did not settle such an axis, so it is not frozen at the winner's
    setting: frozen means decided or declined.
    """
    members = [m for m in models if m["model_id"] in set(indistinguishable)]
    if len(members) < 2:
        return []  # a set of one settled everything it contains
    seen: dict[str, set[bool]] = {}
    for m in members:
        on = set(m.get("axes_on") or [])
        for aid in {a for mm in members for a in (mm.get("axes_on") or [])}:
            seen.setdefault(aid, set()).add(aid in on)
    return sorted(aid for aid, states in seen.items() if len(states) > 1)


def enumerate_with_encoding(
    base_antimony: str,
    base_parameters: list[dict],
    axes: list[dict],
    max_models: int,
    *,
    t_end: float,
    keep_base: bool = False,
    one_at_a_time: bool = False,
) -> dict:
    """Every on/off combination of the axes, grouped by structure (`supermodel`).

    Each model is a complete (antimony, parameters) pair; the base (all axes at
    their defaults) is always present, and `one_at_a_time` gives the base plus each
    axis on its own. Neutralisable axes share one structure, hence one AMICI
    compile. Returns {"models": [...], "encoding": {...}}; `encoding` says which
    axes were absorbed, which stayed separate and why.
    """
    from octomod.workflow_modules.model import supermodel

    return supermodel.enumerate_grouped(
        base_antimony,
        base_parameters,
        axes,
        max_models,
        t_end=t_end,
        keep_base=keep_base,
        one_at_a_time=one_at_a_time,
    )


def enumerate_models(
    base_antimony: str,
    base_parameters: list[dict],
    axes: list[dict],
    max_models: int,
    *,
    t_end: float,
    one_at_a_time: bool = False,
) -> list[dict]:
    """The models of `enumerate_with_encoding`, without the encoding record.

    `t_end` has no default: every declared neutral value is verified by simulation.
    """
    return enumerate_with_encoding(
        base_antimony,
        base_parameters,
        axes,
        max_models,
        t_end=t_end,
        one_at_a_time=one_at_a_time,
    )["models"]


def declare_parameter(antimony_src: str, p: dict) -> str:
    """Add `<id> = <nominal>;` before `end` unless the id is already declared.

    Shared with `supermodel`, so both encoders declare a parameter the same way.
    """
    pid = str(p["id"])
    if re.search(rf"^\s*{re.escape(pid)}\s*=", antimony_src, re.M):
        return antimony_src
    value = p.get("nominal_value")
    if value is None:
        lb, ub = p.get("lb"), p.get("ub")
        value = (float(lb) * float(ub)) ** 0.5 if lb and ub else 1.0
    unit = f"   // {p['unit']}" if p.get("unit") else ""
    line = f"  {pid} = {value};{unit}\n"
    idx = antimony_src.rfind("end")
    if idx < 0:
        return antimony_src + line
    return antimony_src[:idx] + line + antimony_src[idx:]


def _norm_id(s: str) -> str:
    return re.sub(r"[_\s]", "", str(s)).lower()


def resolve_reaction_id(antimony_src: str, rid: str) -> tuple[str | None, str]:
    """The base reaction a `replace_reaction` id means, as (id, how).

    Itself when present ("exact"), else the one reaction id equal to it ignoring
    case and underscores ("respelt"), else None ("missing" or "ambiguous").
    """
    rid = str(rid).strip()
    if re.search(rf"^\s*{re.escape(rid)}\s*:", antimony_src, re.M):
        return rid, "exact"
    ids = _at.reaction_ids(antimony_src)
    hits = [i for i in ids if _norm_id(i) == _norm_id(rid)]
    if len(hits) == 1:
        return hits[0], "respelt"
    return None, "ambiguous" if hits else "missing"


def apply_patch(antimony_src: str, patch) -> tuple[str, bool]:
    """Apply one axis's Antimony patch, all steps or none: (source, applied).

    Two mechanical step forms: replace a named reaction's line, or append lines.
    """
    steps = patch_steps(patch)
    out = antimony_src
    for step in steps:
        out, ok = _apply_step(out, step)
        if not ok:
            return antimony_src, False
    return (out, True) if steps else (antimony_src, False)


def _apply_step(antimony_src: str, patch: dict) -> tuple[str, bool]:
    if "replace_reaction" in patch and patch.get("with"):
        rid = str(patch["replace_reaction"]).strip()
        real, _how = resolve_reaction_id(antimony_src, rid)
        if real is None:
            return antimony_src, False
        pattern = re.compile(rf"^\s*{re.escape(real)}\s*:.*$", re.M)
        # keep the BASE's reaction id: the new line may spell it the agent's way
        new_line = re.sub(
            rf"^\s*{re.escape(rid)}\s*:", f"{real}:", patch["with"].strip(), count=1
        )
        return pattern.sub(lambda _m: "  " + new_line, antimony_src, count=1), True
    if patch.get("append"):
        lines = (
            patch["append"]
            if isinstance(patch["append"], str)
            else "\n".join(patch["append"])
        )
        idx = antimony_src.rfind("end")
        if idx < 0:
            return antimony_src + "\n" + lines + "\n", True
        return (
            antimony_src[:idx] + "  " + lines.strip() + "\n" + antimony_src[idx:],
            True,
        )
    return antimony_src, False


def select(
    fits: list[dict],
    criterion: str,
    delta_indistinguishable: float,
    decisive_weight: float,
) -> dict:
    """Information-criterion selection over fitted models.

    Criterion names follow petab_select's vocabulary; the arithmetic is local, so
    a failed petab-select import cannot block a verdict.
    """
    import math

    scored = []
    for f in fits:
        n_par, nllh, n_data = f["n_estimated"], f["nllh"], f["n_data"]
        if criterion.upper() == "BIC":
            value = 2 * nllh + n_par * math.log(max(n_data, 2))
        elif criterion.upper() == "AICC":
            denom = max(n_data - n_par - 1, 1)
            value = 2 * nllh + 2 * n_par + (2 * n_par * (n_par + 1)) / denom
        else:
            value = 2 * nllh + 2 * n_par
        scored.append({**f, "criterion": criterion.upper(), "value": value})
    best = min(s["value"] for s in scored)
    for s in scored:
        s["delta"] = s["value"] - best
        s["weight"] = math.exp(-s["delta"] / 2)
    tot = sum(s["weight"] for s in scored) or 1.0
    for s in scored:
        s["weight"] /= tot
    scored.sort(key=lambda s: s["value"])
    indistinguishable = [
        s["model_id"] for s in scored if s["delta"] <= delta_indistinguishable
    ]
    return {
        "criterion": criterion.upper(),
        "winner": scored[0]["model_id"],
        "winner_axes_on": scored[0]["axes_on"],
        "decisive": scored[0]["weight"] >= decisive_weight,
        "indistinguishable": indistinguishable,
        "undecided_axes": undecided_axes(scored, indistinguishable),
        "models": [
            {
                k: s[k]
                for k in (
                    "model_id",
                    "axes_on",
                    "n_estimated",
                    "nllh",
                    "value",
                    "delta",
                    "weight",
                )
            }
            for s in scored
        ],
    }
