"""A T0/T1 failure at S2/S3 blocks the artifact, never the run.

`ATTRIBUTION` names the role that wrote the value a gate checks; a failure no
agent authored goes to a person. The re-ask carries the failing check verbatim,
the role's own block, the merged rows built from it and the legal vocabulary,
and shares the role's dossier and `retry.module_draft` budget with the seam
checks. When the budget is spent, the failure-point gate offers more attempts,
a redraft, a declared fallback (applied only on a signed answer) or a stop.
"""

from __future__ import annotations

import json
import re

# gate id -> the role whose output it checks. None = unattributable: the value
# was written by the engine or is a model property, and an agent asked to
# "fix" it would mask an engine bug.
ATTRIBUTION: dict[str, str | None] = {
    "assembly_observables_resolve": "observation",
    "assembly_noise_declared": "observation",
    "assembly_conditions_resolve": "condition",
    "assembly_parameters_sane": "observation",  # only for assembly-created rows
    "data_rows_well_formed": "data_extraction",
    "data_units_and_error_declared": "data_extraction",
    "data_holdout_labels_resolve": "data_extraction",
    "data_processing_legal": "data_extraction",  # a declared op the engine refuses
    "assembly_petablint": None,
    "assembly_formulas_compile_safe": "observation",  # an AMICI-unknown function in a formula
    # a sigma that reaches the model other than through its own observable
    "assembly_sigma_through_observable": "observation",
    "assembly_measurements_resolve": None,
    # the condition-encoding agent declares each pre-equilibration (a dict of
    # overrides on a measured condition); the engine only renders the row
    "assembly_preequilibration": "condition",
    # refusals the merge raises about a value an agent wrote
    "assembly_merge_noise": "observation",
    "assembly_merge_observables": "observation",
    "assembly_merge_conditions": "condition",
    # the model, its readouts and its inputs meet here: the finding decides
    # (`role_for`); a piece of the model no readout sees is construction's
    "assembly_connected": "construction",
}
# which role answers for each part `connectivity.culprit` blames: a readout
# the model does not have was mapped by the observation agent, a varied
# quantity that reaches no readout was chosen by the condition encoding, and
# a piece of the model no readout sees is the model's own
CONNECTED_ROLE = {
    "readout": "observation",
    "input": "condition",
    "model": "construction",
}
# roles the S3 loop can re-ask; any other attributed role is upstream of the
# assembly, and its failure is not repaired here
ASSEMBLY_ROLES = ("observation", "condition")
# Thresholds at S3 inform and never block, so these never reach `attribute`.
ADVISORY = (
    "assembly_dof",
    "assembly_magnitude_reconciliation",
    "assembly_sensitivity_coverage",
    "assembly_verification",
    "data_plausibility_screen",
)
# a parameter row the ASSEMBLY created — the one kind of parameters_sane
# failure an agent can answer for
_ASSEMBLY_PARAM = re.compile(r"\b(sc_\w+|off_\w+|sigma\w*)\b")

# which merged table a gate reads, so the payload shows the rows the ENGINE
# built from the block — never a measurement value for a role without them
TABLE_FOR_GATE = {
    "assembly_observables_resolve": "observables",
    "assembly_noise_declared": "observables",
    "assembly_formulas_compile_safe": "observables",
    "assembly_sigma_through_observable": "observables",
    "assembly_conditions_resolve": "conditions",
    "assembly_preequilibration": "conditions",
    "assembly_parameters_sane": "parameters",
}
ID_COLUMN = {
    "observables": "observableId",
    "conditions": "conditionId",
    "parameters": "parameterId",
}


def role_for(result) -> str | None:
    """The role a failing gate re-asks, or None."""
    gid = str(result.gate_id)
    if gid == "assembly_connected":
        from octomod.workflow_modules.model.connectivity import culprit

        return CONNECTED_ROLE.get(culprit(result.detail) or "model")
    if gid == "assembly_parameters_sane":
        return "observation" if _ASSEMBLY_PARAM.search(str(result.detail)) else None
    return ATTRIBUTION.get(gid)


def attribute(results) -> tuple[str | None, list]:
    """(role to re-ask, the blocking failures) for a battery's results.

    The first blocking failure decides the role, so an unattributable failure
    ahead of an attributable one goes to a person.
    """
    failing = [r for r in results if not r.passed and r.blocking]
    if not failing:
        return None, []
    return role_for(failing[0]), failing


def gate_record(result) -> dict:
    """The failing check, verbatim — what the card and the re-ask both show."""
    return {
        "gate_id": result.gate_id,
        "tier": result.tier,
        "detail": str(result.detail),
        "value": result.value,
        "threshold": result.threshold,
    }


def implicated_ids(detail: str, candidates) -> list[str]:
    """Every candidate id the detail names verbatim, in candidate order.

    A condition's pre-equilibration row, which the engine renders as
    `preeq_<id>`, names the measured condition it belongs to."""
    from octomod.workflow_modules.assembly.engine import PREEQ_PREFIX

    text = str(detail)
    pre = re.escape(PREEQ_PREFIX)
    return [
        c for c in candidates if re.search(rf"\b(?:{pre})?{re.escape(str(c))}\b", text)
    ]


def observation_block(reply: dict, ids: list[str]) -> list[dict]:
    """The agent's own entries (formula, noise, scaling) for the implicated observables.

    All of them when none is named; never the merged TSV.
    """
    obs = [o for o in (reply.get("observables") or []) if isinstance(o, dict)]
    picked = [o for o in obs if str(o.get("observable_id")) in set(ids)] or obs
    keep = (
        "observable_id",
        "maps_to_label",
        "formula",
        "transformation",
        "noise",
        "scaling",
    )
    return [{k: o.get(k) for k in keep if k in o} for o in picked]


def condition_block(reply: dict, ids: list[str]) -> list[dict]:
    conds = [c for c in (reply.get("conditions") or []) if isinstance(c, dict)]
    picked = [c for c in conds if str(c.get("condition_id")) in set(ids)] or conds
    keep = ("condition_id", "maps_to_label", "overrides", "preequilibration")
    return [{k: c.get(k) for k in keep if k in c} for c in picked]


def extraction_block(reply: dict, labels: list[str]) -> list[dict]:
    maps = [m for m in (reply.get("mappings") or []) if isinstance(m, dict)]
    picked = [m for m in maps if str(m.get("observable_label")) in set(labels)] or maps
    return picked


def table_rows(petab, gate_id: str, ids: list[str], cap: int = 12) -> list[dict]:
    """The merged rows the gate actually read, for the implicated ids.
    `petab` is the unit of work's assembled problem node (`ctx.work / "petab"`)."""

    name = TABLE_FOR_GATE.get(gate_id)
    if not name:
        return []
    df = (petab / name).table(None)
    if df is None:
        return []
    col = ID_COLUMN[name]
    if ids and col in df.columns:
        wanted = [str(i) for i in ids]
        if name == "conditions":
            # a measured condition's pre-equilibration row is rendered from
            # the same declaration, so the agent sees both
            from octomod.workflow_modules.assembly.engine import PREEQ_PREFIX

            wanted += [PREEQ_PREFIX + i for i in wanted]
        df = df[df[col].astype(str).isin(wanted)]
    return json.loads(df.head(cap).to_json(orient="records"))


def legal_vocabulary(gate_id: str, model_summary: dict | None) -> dict:
    """What the role MAY name, where the engine can say so."""
    ms = model_summary or {}
    ents = sorted(set(ms.get("species") or []) | set(ms.get("parameters") or []))
    if gate_id in (
        "assembly_observables_resolve",
        "assembly_conditions_resolve",
        "assembly_preequilibration",
        "assembly_parameters_sane",
        "assembly_connected",
    ):
        return {
            "model_entities": ents,
            "note": "species INCLUDING boundary species, and parameters — the "
            "only symbols a formula or an override may name",
        }
    if gate_id in ("assembly_noise_declared", "assembly_sigma_through_observable"):
        from octomod.workflow_modules.assembly.engine import noise_shape_help

        return {"noise_shapes": noise_shape_help()}
    return {}


def feedback(
    gate: dict,
    role: str | None,
    your_block,
    merged_rows: list[dict],
    vocabulary: dict,
    dropped_axes: list[dict] | None = None,
) -> dict:
    """The `battery_feedback` payload key (docs/ROUTING.md)."""
    out = {
        "gate": gate,
        "your_block": your_block,
        "merged_rows": merged_rows,
        "legal_vocabulary": vocabulary,
        "instruction": (
            "A deterministic check on the estimation problem the engine BUILT "
            "from your reply failed. `gate` is the check and its evidence, "
            "verbatim. `your_block` is what YOU wrote for the implicated ids; "
            "`merged_rows` is what the engine rendered from it. Fix exactly "
            "what the check names, keep everything that passed, and return the "
            "SAME contract in full. If the merged rows do not correspond to "
            "your block — if the engine built something you did not write — "
            "say so in your rationale instead of working around it."
        ),
    }
    if dropped_axes:
        out["dropped_axes"] = dropped_axes
        out["dropped_axes_instruction"] = (
            "These model-space axes you declared were DROPPED before anyone "
            "paid for them, each with its reason. Re-declare each one in a "
            "legal shape — `on_assembly_patch` is a dict with exactly one kind "
            "as key, the kinds are listed in `legal_kinds` — or leave it out "
            "and say why."
        )
    return out


_FALLBACK_RE = re.compile(r"\bfallback\s*:\s*(?P<name>[A-Za-z][\w\-]*)", re.I)


def fallback_names(spec) -> list[str]:
    return sorted((spec.get("assembly_defaults.fallbacks") or {}).keys())


def fallback_form(spec) -> str:
    names = ", ".join(fallback_names(spec)) or "(none declared)"
    return (
        f"fallback: <name>   rewrite the attributed block to a declared default "
        f"({names}) and re-merge — applied only on YOUR signed answer; the "
        f"agent's reply stays in the record untouched"
    )


def parse_fallback(note: str | None) -> str | None:
    if not note:
        return None
    m = _FALLBACK_RE.search(str(note))
    return m.group("name") if m else None


def apply_fallback(name: str, assembly: dict, spec) -> tuple[dict, dict]:
    """(rewritten assembly, what it replaced) for a declared fallback name.

    The shape each name produces is described beside it in
    `workflows/default.yaml`. Raises ValueError for an undeclared name (with
    the legal list) and for a declared one this function has no rewrite for.
    """
    import copy

    declared = spec.get("assembly_defaults.fallbacks") or {}
    if name not in declared:
        raise ValueError(
            f"fallback {name!r} is not declared; legal: {sorted(declared)} "
            f"(workflows/default.yaml, assembly_defaults.fallbacks)"
        )
    asm = copy.deepcopy(assembly)
    ids = [str(o["observable_id"]) for o in asm.get("observables") or []]
    if name == "additive-noise":
        replaced = {"noise": asm.get("noise")}
        asm["noise"] = [
            {
                "observable_id": oid,
                "distribution": "normal",
                "formula": f"sigma_{oid}",
                "estimate_sigma": True,
                "rationale": "fallback additive-noise: a constant sigma per observable, estimated (signed at the S3 failure-point gate)",
            }
            for oid in ids
        ]
    elif name == "scaling":
        replaced = {"scaling": asm.get("scaling")}
        asm["scaling"] = [
            {
                "observable_id": oid,
                "mode": "factor",
                "scale_parameter": f"sc_{oid}",
                "offset_parameter": None,
                "per": "observable",
                "shared_across_observables": False,
                "pin_first_to_one": False,
                "shared_across_conditions": True,
                "rationale": "fallback scaling: one factor per observable, shared across conditions (signed at the S3 failure-point gate)",
            }
            for oid in ids
        ]
    elif name == "no-scaling":
        replaced = {"scaling": asm.get("scaling")}
        asm["scaling"] = [
            {
                "observable_id": oid,
                "mode": "none",
                "scale_parameter": None,
                "offset_parameter": None,
                "per": "observable",
                "shared_across_observables": False,
                "pin_first_to_one": False,
                "shared_across_conditions": True,
                "rationale": "fallback no-scaling: the data taken as calibrated (signed at the S3 failure-point gate)",
            }
            for oid in ids
        ]
    else:  # declared in the yaml but not implemented here: refuse loudly
        raise ValueError(
            f"fallback {name!r} is declared but this engine has no rewrite for "
            f"it — add one in battery_feedback.apply_fallback or remove the "
            f"declaration"
        )
    return asm, replaced


def fallback_into_reply(name: str, reply: dict, spec) -> tuple[dict, dict]:
    """`apply_fallback` applied to the observation agent's reply.

    Used when the seam checks, not the battery, spent the budget, so no
    assembly exists yet.
    """
    import copy

    obs = [o for o in (reply.get("observables") or []) if isinstance(o, dict)]
    asm = {
        "observables": [{"observable_id": str(o.get("observable_id"))} for o in obs],
        "noise": [
            dict(o.get("noise") or {}, observable_id=str(o.get("observable_id")))
            for o in obs
        ],
        "scaling": [
            dict(o.get("scaling") or {}, observable_id=str(o.get("observable_id")))
            for o in obs
        ],
    }
    new_asm, replaced = apply_fallback(name, asm, spec)
    out = copy.deepcopy(reply)
    by_id_noise = {n["observable_id"]: n for n in new_asm["noise"]}
    by_id_scaling = {s["observable_id"]: s for s in new_asm["scaling"]}
    for o in out["observables"]:
        oid = str(o.get("observable_id"))
        if "noise" in replaced:
            n = by_id_noise[oid]
            o["noise"] = {
                "distribution": n["distribution"],
                "formula": n["formula"],
                "estimate_sigma": n["estimate_sigma"],
            }
        if "scaling" in replaced:
            s = by_id_scaling[oid]
            o["scaling"] = {
                k: s.get(k)
                for k in (
                    "mode",
                    "scale_parameter",
                    "offset_parameter",
                    "per",
                    "shared_across_observables",
                    "pin_first_to_one",
                )
            }
    return out, replaced


def failure_point_gate(
    ctx,
    module: str,
    role: str | None,
    failing: list,
    your_block,
    history,
    budget: int,
    *,
    offer_fallbacks: bool,
) -> tuple[str, object]:
    """Ask the human at the failure point what to do with the blocked artifact.

    Returns ("more", n), ("redraft", text), ("fallback", name) or ("stop", None).
    Not `ask_once`: the gate re-asks after each spent grant, and a resume reads
    each decision back from what its answer wrote (a grant in the role's
    dossier, a fallback in the assembly in the record, a redraft in the ledger).
    """
    from octomod.orchestration.interaction import human_redraft, humangate

    spec = ctx.spec
    lines = []
    for r in failing[:3]:
        g = gate_record(r)
        lines.append(f"FAILED [{g['tier']}] {g['gate_id']}: {g['detail'][:400]}")
    if len(history) if history is not None else 0:
        lines.append(
            f"{role}: {len(history)} attempt(s) so far failed a check (budget {budget})"
        )
        for a in history.attempts[-3:]:
            lines.append(
                f"  attempt {a['attempt']}: "
                + " | ".join(f[:110] for f in a["gate_failures"][:2])
            )
    block_txt = json.dumps(your_block, default=str)
    lines.append(
        f"the agent's own block ({role or 'assembly'}): "
        + (block_txt if len(block_txt) <= 600 else block_txt[:600] + " …")
    )
    if role is None:
        lines.append(
            "UNATTRIBUTABLE: this check reads what the engine wrote, or a "
            "property of the model — no agent authored the failing value. "
            "`redraft:` re-does the whole assembly with your words; a fallback "
            "rewrites one block; `n` stops."
        )
    forms = []
    if role is not None:
        forms.append(
            f"n=<attempts>       grant that many further attempts to {role} (default 1)"
        )
    forms.append(human_redraft.NOTE_FORM)
    if offer_fallbacks and fallback_names(spec):
        forms.append(fallback_form(spec))
        for name, rec in (spec.get("assembly_defaults.fallbacks") or {}).items():
            lines.append(f"  fallback {name}: {rec.get('description', '')}")
    forms.append("n                  stop the run here, honestly")
    question = (
        f"{module}: a blocking check failed and "
        + (f"{role} has spent its redraft budget" if role else "no agent can be asked")
        + ". Grant more attempts, send your own words, apply a declared fallback, or stop?"
    )
    approved, note = humangate.ask(
        question,
        lines,
        ledger=ctx.ledger,
        module=f"{module}_redraft_budget",
        round_idx=ctx.round_idx,
        auto=ctx.auto,
        intent=ctx.intent,
        where="the failure point — the ARTIFACT is blocked; the run is not",
        consequences=(
            "the assembly is repaired here and the battery re-runs; nothing "
            "downstream has run on the blocked artifact",
            "the run stops here; the failing checks are in the record's gates",
        ),
        note_forms=forms,
    )
    if not approved:
        return "stop", None
    fb = parse_fallback(note)
    if fb is not None:
        if fb not in fallback_names(spec):
            ctx.ledger.append(
                "note",
                module=module,
                round_idx=ctx.round_idx,
                note=f"fallback {fb!r} refused: not declared (legal: {fallback_names(spec)}); treated as one more attempt",
            )
        else:
            return "fallback", fb
    rd = human_redraft.parse(note)
    if rd:
        return "redraft", rd
    if role is None:
        # a bare `y` redrafts the whole assembly, once per round: the same
        # unattributable failure after a full redraft is not an authoring problem
        prior = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "note"
            and e.get("human_redraft")
            and e.get("round") == ctx.round_idx
            and e.get("role") == "the assembly agents"
        ]
        if prior:
            ctx.ledger.append(
                "note",
                module=module,
                round_idx=ctx.round_idx,
                note=(
                    "the whole assembly was already redrafted once this round and the "
                    "same unattributable check failed again — stopping honestly rather "
                    "than looping the agents against an engine invariant"
                ),
            )
            return "stop", None
        return "redraft", (
            "re-do the assembly: the battery failed on "
            + "; ".join(f"{r.gate_id} — {str(r.detail)[:160]}" for r in failing[:2])
        )
    from octomod.orchestration.interaction import gate_note

    asked = gate_note.key_int(note, "n")
    n = max(1, min(asked, 10)) if asked is not None else 1
    history.add_grant(n)
    ctx.ledger.append(
        "redraft_grant",
        module=module,
        round_idx=ctx.round_idx,
        role=role,
        granted=n,
        attempts_so_far=len(history),
        grants_total=history.grants_total,
    )
    return "more", n


def card_lines(ctx, module: str = "assembly") -> list[str]:
    """Card lines for what this round's battery feedback did.

    Every re-ask, fallback, dropped candidate and axis, and the advisory checks'
    numbers, read from the ledger and the gate verdicts in the record (never
    in-memory state) so a resumed run shows the same.
    """
    from octomod.workflow_modules.model import model_space

    rows = [
        e
        for e in ctx.ledger.entries()
        if e.get("round") == ctx.round_idx and e.get("module") == module
    ]
    out: list[str] = []
    # once per card: this candidate's latest merge, else the round's latest —
    # a re-asked encoding merges again, and only the last merge is in the record
    preeq = [
        e
        for e in rows
        if e.get("event") == "note" and e.get("preequilibration_rendered")
    ]
    mine = [e for e in preeq if e.get("candidate") == getattr(ctx, "candidate", None)]
    if preeq:
        out.append(f"  ⚑ {(mine or preeq)[-1].get('note')}")
    for e in rows:
        if e.get("event") == "redraft_attributed":
            out.append(
                f"  re-asked {e.get('role')} after {e.get('gate_id')} "
                f"(attempt {e.get('attempt')})"
            )
        elif e.get("event") == "assembly_fallback":
            out.append(
                f"  FALLBACK {e.get('fallback')} applied to {e.get('role')}'s block, "
                f"signed by {e.get('signed')} — the agent's reply is untouched in the record"
            )
        elif e.get("event") == "candidate_dropped":
            out.append(
                f"  candidate {e.get('candidate')} DROPPED: {str(e.get('reason'))[:160]}"
            )
    out += model_space.dropped_axes_card_lines(ctx, module=module)
    pre = ctx.gates.child("assembly_preequilibration")
    if preeq and pre.exists():
        # the steady-state screen is part of what the person approves
        try:
            g = pre.get()
            mark = "ok" if g.get("passed") else "FAILED"
            out.append(
                f"  assembly_preequilibration ({mark}): {str(g.get('detail'))[:220]}"
            )
        except Exception:
            pass
    for gid in ("assembly_magnitude_reconciliation", "assembly_dof"):
        p = ctx.gates.child(gid)
        if p.exists():
            try:
                g = p.get()
            except Exception:
                continue
            mark = "ok" if g.get("passed") else "INFORMATION, not a stop"
            val = (
                f" [{g.get('value')} of {g.get('threshold')}]"
                if g.get("value") is not None
                else ""
            )
            out.append(f"  {gid} ({mark}){val}: {str(g.get('detail'))[:220]}")
    return out
