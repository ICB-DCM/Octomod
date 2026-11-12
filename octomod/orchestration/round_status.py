"""Round status — the slot contract, computed, never indexed twice.

`SLOTS` says which parts of the record each artifact slot holds, which of
them a downstream module cannot live without, and which marker certifies the
slot. Everything else about a round's state is COMPUTED from the record and
its markers: `slot_state(round)` gives, per slot, where it lives, the sha of
each part, who produced it (agent:<role> | engine | user-supplied), which
battery validated it and whether a part changed since. The marker carries
the slot's shas itself (`marker_files`, stamped by `set_marker`), and
`set_marker` writes the computed state into the round's `status` group, so
there is no separate index: a second source of truth is the stated anti-goal
(renderer-vs-artifact drift is a recorded bug class).
The one thing a validator itself records is its own verdict
(`status/validations`), so a resumed transition asks once.

Slot validators are the existing gate batteries, repackaged per slot: the
model slot validates by the S1 build/sim ladder, the data slot by the S2
checks, the petab slot by the S3 battery, the estimation slot by the S6 gates.
Running them writes the usual gate verdicts and ledger rows under the module
name `entry_<slot>`, so an entry is audited like any other module.

Modular entry (`run --from-module <module>`, and `supplied/petab`): every
upstream slot is validated and the run refuses with the NAMED missing or
invalid slot — the error message is the instruction, as with markers. Markers
stay the DAG instrument: `set_marker` stamps the slot's shas into the marker,
`require_marker` checks the slot is intact against them, so there is one
mechanism, not two coexisting ones. An explicit re-entry moves the
invalidated slots' records aside (`superseded/<module>_<stamp>/…`),
forgets the gate decisions those modules recorded and drops stale solver
overrides, so nothing in the record can masquerade as an input to the module
being redone.
"""

from __future__ import annotations

import datetime

from octomod.result import node as tree

# ------------------------------------------------------------------ schema

SCHEMA_VERSION = 2  # of the slot-state shape (2: record keys)

# A candidate's recorded `n` at its re-asked budget gate, relative to its
# fitted problem's group: `cost_profile.DECLINED_KEY`, spelled out here so
# the index does not import the estimation stack.
DECLINED_BUDGET = "budget_declined"

# Where a slot lives. "run": the record root · "round": the round ·
# "model": the unit of work's model (the candidate's, else the round's) ·
# "work": the unit of work's fitted problem (`candidates/<id>`, or `_single`).
# "model" and "work" are PER CANDIDATE in a candidate-set round.
SLOTS: dict[str, dict] = {
    "intent": {
        "scope": "run",
        "parts": ["intent"],
        "required": ["intent"],
        "marker": None,
    },
    "model": {
        "scope": "model",
        "parts": [
            "antimony",
            "sbml",
            "parameters",
            "build_report",
            "network",
            "glossary",
        ],
        "required": ["sbml"],
        "marker": "s1",
    },
    "data": {
        "scope": "round",
        "parts": [
            "data/measurements",
            "data/report",
            "data/signals",
            "data/phenomenology",
        ],
        "required": ["data/measurements", "data/report"],
        "marker": "s2",
    },
    "petab": {
        "scope": "work",
        "parts": [
            "petab/problem_yaml",
            "petab/observables",
            "petab/conditions",
            "petab/measurements",
            "petab/parameters",
            "petab/holdout_measurements",
            "assembly",
        ],
        "required": [
            "petab/observables",
            "petab/conditions",
            "petab/measurements",
            "petab/parameters",
        ],
        "marker": "s3",
    },
    "compiled": {
        "scope": "work",
        "parts": ["cost"],
        "required": ["cost"],
        "marker": "cost",
    },
    "estimation": {
        "scope": "work",
        "parts": ["estimation", "starts"],
        "required": ["estimation"],
        "marker": "s6",
    },
    "evaluation": {
        "scope": "round",
        "parts": ["evaluation_core", "evaluation", "report_md", "residual_forms"],
        "required": ["evaluation"],
        "marker": "s7",
    },
    "selection": {
        "scope": "round",
        "parts": ["space/axes", "space/candidates", "expansion", "selection"],
        "required": [],
        "marker": None,
    },
    "decisions": {
        "scope": "round",
        "parts": ["decisions_md", "revision"],
        "required": [],
        "marker": None,
    },
}

PER_CANDIDATE = ("model", "work")

MARKER_TO_SLOT = {v["marker"]: k for k, v in SLOTS.items() if v["marker"]}

# Pipeline modules a run may be entered at, the slots each one PRODUCES, and
# the markers that module's completion sets. Order matters: entering at module k
# requires every slot produced before k and invalidates every marker from k on.
MODULES: list[tuple[str, list[str], list[str]]] = [
    ("model", ["model"], ["s1"]),
    ("data", ["data"], ["s2"]),
    ("assembly", ["petab"], ["s3"]),
    ("estimation", ["compiled", "estimation"], ["candidate_compile", "cost", "s6"]),
    ("evaluation", ["evaluation"], ["s7"]),
]
MODULE_NAMES = [s[0] for s in MODULES]
MODULE_ALIASES = {
    "s1": "model",
    "construction": "model",
    "s2": "data",
    "s3": "assembly",
    "petab": "assembly",
    "s6": "estimation",
    "cost": "estimation",
    "s7": "evaluation",
    "profiling": "evaluation",
    "report": "evaluation",
}


def normalise_module(name: str) -> str:
    key = str(name).strip().lower()
    key = MODULE_ALIASES.get(key, key)
    if key not in MODULE_NAMES:
        raise ValueError(
            f"unknown module {name!r}; known: {MODULE_NAMES} "
            f"(aliases: {sorted(MODULE_ALIASES)})"
        )
    return key


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------- places


def slot_base(rnd, slot: str, cid: str | None):
    """The node a slot's parts are relative to, in round `rnd` for the unit
    of work `cid` (a candidate id, or None for the round's own)."""
    scope = SLOTS[slot]["scope"]
    if scope == "run":
        return tree.Node(rnd.store, "")
    if scope == "model":
        return tree.model_node(rnd, cid)
    if scope == "work":
        return tree.work_node(rnd, cid)
    return rnd


def _base(ctx, slot: str):
    return slot_base(ctx.round, slot, ctx.candidate)


def declared_candidates(rnd) -> list[str]:
    """Candidate ids the round declared (`space/candidates`), else []."""
    rows = (rnd / "space/candidates").get([])
    try:
        return [str(c["id"]) for c in rows if isinstance(c, dict) and "id" in c]
    except TypeError:
        return []


def slot_parts(base, slot: str, shas: dict | None = None) -> dict[str, str]:
    """{part: sha16} of the slot's parts present under `base`. `shas` is a
    memo keyed by record key, shared by the callers of one marker write."""
    memo = {} if shas is None else shas
    out = {}
    with base.store.reading():
        for rel in SLOTS[slot]["parts"]:
            n = base / rel
            if n.key not in memo:
                memo[n.key] = n.sha() if n.exists() else None
            if memo[n.key] is not None:
                out[rel] = memo[n.key]
    return out


def marker_files(ctx, marker: str, shas: dict | None = None) -> dict[str, str]:
    """The shas `set_marker` stamps into the marker.

    The marker itself carries the slot's shas, so `check_intact` compares
    against what the battery actually validated, and there is no second copy
    to fall out of step.
    """
    slot = MARKER_TO_SLOT.get(marker)
    if slot is None:
        return {}
    return slot_parts(_base(ctx, slot), slot, shas)


# --------------------------------------------------- the validators' record

# A validator's own verdict, so a slot validated at its current content is not
# validated again (`round_seed.require_evaluation` reads it before seeding the
# next round). `status/validations/<cid | _round>/<slot>`: validated_by,
# validated_at, producer, and the shas of the parts it saw.
VALIDATIONS_KEY = "status/validations"
_ROUND = "_round"


def validation_node(rnd, slot: str, cid: str | None):
    return (rnd / VALIDATIONS_KEY).child(cid or _ROUND).child(slot)


def validation_record(rnd, slot: str, cid: str | None) -> dict | None:
    rec = validation_node(rnd, slot, cid).get(None)
    return rec if isinstance(rec, dict) else None


def record_validation(
    ctx, slot: str, validated_by: str | None, default_producer: str = "engine"
) -> dict:
    """Record that `slot` validated (by `validated_by`) at its current content
    — or, with `validated_by=None`, only who produced it. `default_producer`
    names the producer only when no marker or earlier record names one: an
    entry validates what a person supplied, a round seed what the engine
    made."""
    rnd = ctx.round
    marker = _marker(rnd, ctx.candidate, SLOTS[slot]["marker"])
    if marker is None and ctx.candidate is not None:
        marker = _marker(rnd, None, SLOTS[slot]["marker"])
    previous = validation_record(rnd, slot, ctx.candidate) or {}
    rec = {
        "key": _base(ctx, slot).key,
        "files": slot_parts(_base(ctx, slot), slot),
        "producer": (marker or {}).get("producer")
        or previous.get("producer")
        or default_producer,
        "recorded_at": _now(),
    }
    if validated_by:
        rec["validated_by"] = validated_by
        rec["validated_at"] = rec["recorded_at"]
    elif previous.get("validated_at"):
        rec["validated_by"] = previous.get("validated_by")
        rec["validated_at"] = previous["validated_at"]
    validation_node(rnd, slot, ctx.candidate).put(rec)
    return rec


def _slot_entry(base, slot: str, marker: dict | None, shas: dict, validation) -> dict:
    parts = slot_parts(base, slot, shas)
    rec = {
        "key": base.key,
        "files": [{"part": k, "sha16": v} for k, v in parts.items()],
        "present": all(r in parts for r in SLOTS[slot]["required"]),
        # a marker without a producer was set by an engine module; a slot no
        # marker owns is the engine's by construction; an unset slot has none
        "producer": (marker or {}).get("producer")
        or (validation or {}).get("producer")
        or (
            "engine" if (marker is not None or SLOTS[slot]["marker"] is None) else None
        ),
    }
    if marker is not None:
        rec["validated_by"] = (
            marker.get("validated_by") or f"{SLOTS[slot]['marker']} gates"
        )
        rec["validated_at"] = marker.get("at")
        stamped = marker.get("files")
        if isinstance(stamped, dict):
            rec["drifted"] = sorted(
                rel for rel, sha in stamped.items() if parts.get(rel) not in (None, sha)
            )
    elif validation and validation.get("validated_at"):
        # no marker certifies the slot, but its own validator ran on it
        rec["validated_by"] = validation.get("validated_by")
        rec["validated_at"] = validation.get("validated_at")
    return rec


def _marker(rnd, cid: str | None, name: str | None) -> dict | None:
    if not name:
        return None
    m = tree.markers_node(rnd, cid).child(name).get(None)
    return m if isinstance(m, dict) else ({} if m is not None else None)


def slot_state(rnd, shas: dict | None = None) -> dict:
    """Every slot's state for a round, computed from the record and markers.

    Shape: {"slots": {slot: entry}, "candidates": {cid: {slot: entry}}} with
    `entry` = key, files (part + sha16), present, producer, and — when the
    slot's marker is set — validated_by, validated_at and the parts whose sha
    drifted since the marker was stamped.
    """
    memo = {} if shas is None else shas
    cids = declared_candidates(rnd)
    out: dict = {"slots": {}, "candidates": {}}
    with rnd.store.reading():
        for slot, spec in SLOTS.items():
            marker = _marker(rnd, None, spec["marker"])
            base = slot_base(rnd, slot, None)
            val = validation_record(rnd, slot, None)
            if spec["scope"] in PER_CANDIDATE and cids:
                n_present = 0
                for cid in cids:
                    entry = _slot_entry(
                        slot_base(rnd, slot, cid),
                        slot,
                        _marker(rnd, cid, spec["marker"]),
                        memo,
                        validation_record(rnd, slot, cid),
                    )
                    out["candidates"].setdefault(cid, {})[slot] = entry
                    n_present += bool(entry["present"])
                rec = _slot_entry(base, slot, marker, memo, val)
                rec["candidates_present"] = n_present
                rec["present"] = rec["present"] or n_present == len(cids)
                out["slots"][slot] = rec
            else:
                out["slots"][slot] = _slot_entry(base, slot, marker, memo, val)
    return out


def load(rnd) -> dict:
    """The slot state of a round (`slots`, `candidates`, with the schema
    version and the round's name), computed from the record."""
    state = slot_state(rnd)
    return {
        "schema_version": SCHEMA_VERSION,
        "round": rnd.name,
        "slots": state["slots"],
        "candidates": state["candidates"],
    }


def _drift(base, stamped: dict | None, prefix: str = "") -> list[str]:
    out = []
    for rel, sha in (stamped or {}).items():
        n = base / rel
        if n.exists() and n.sha() != sha:
            out.append(prefix + rel)
    return out


def check_intact(ctx, marker: str) -> tuple[list[str], list[str]]:
    """(missing required parts, parts whose sha drifted since the marker was
    stamped) for the slot a marker owns. Missing is a hard stop for
    require_marker; drift is reported, not fatal — a same-content rewrite is
    legitimate and common."""
    slot = MARKER_TO_SLOT.get(marker)
    if slot is None:
        return [], []
    rnd = ctx.round
    cids = (
        declared_candidates(rnd)
        if (SLOTS[slot]["scope"] in PER_CANDIDATE and ctx.candidate is None)
        else []
    )
    with ctx.store.reading():
        if cids:
            # a candidate-set round: the slot lives in every candidate
            missing, drifted = [], []
            for cid in cids:
                base = slot_base(rnd, slot, cid)
                missing += [
                    f"{cid}: {r}"
                    for r in SLOTS[slot]["required"]
                    if not (base / r).exists()
                ]
                m = _marker(rnd, cid, marker) or {}
                drifted += _drift(base, m.get("files"), f"{cid}: ")
            return missing, drifted
        base = _base(ctx, slot)
        missing = [r for r in SLOTS[slot]["required"] if not (base / r).exists()]
        # the unit of work's marker first, else the round's (candidate work
        # sees the shared upstream markers)
        m = _marker(rnd, ctx.candidate, marker)
        if m is None:
            m = _marker(rnd, None, marker)
        return missing, _drift(base, (m or {}).get("files"))


# ------------------------------------------------------------ validators


def validate(
    ctx, slot: str, default_producer: str = "user-supplied"
) -> tuple[bool, list[str]]:
    """Run the slot's validator battery. Returns (ok, human-readable reasons).
    Every gate result is persisted with the unit of work's gates and ledgered
    under the module name `entry_<slot>`, so an entry leaves the same evidence
    a module does. `default_producer` names the producer only when no marker
    names one: an entry validates what a person supplied, a round seed what
    the engine made."""
    from octomod.gates import run_gate_set

    # A CANDIDATE-SET round keeps its per-candidate slots under each candidate,
    # where `slot_state` and the drift check read them, so they are validated
    # there: a discrimination round never has a round-level model, and looking
    # for one would refuse every re-entry of such a run with "slot 'model':
    # missing ['model/model.xml']" — while entry-anywhere exists precisely so
    # entry works everywhere. A refusal there is expensive: a construction of
    # five candidates measured eleven minutes and a 65 KB reply, and the only
    # way forward would be to build them again.
    if SLOTS[slot]["scope"] in PER_CANDIDATE and ctx.candidate is None:
        cids = declared_candidates(ctx.round)
        if cids:
            return _validate_candidates(
                ctx, slot, cids, default_producer=default_producer
            )

    base = _base(ctx, slot)
    missing = [r for r in SLOTS[slot]["required"] if not (base / r).exists()]
    if missing:
        return False, [f"slot {slot!r}: missing {missing} under {base.key or '/'}"]
    module = f"entry_{slot}"
    try:
        gates = _gates_for(ctx, slot, base)
    except Exception as e:  # a validator that cannot even be built is a failure
        return False, [
            f"slot {slot!r}: validator could not run: " f"{type(e).__name__}: {e}"
        ]
    if gates is None:
        record_validation(
            ctx, slot, validated_by="schema check", default_producer=default_producer
        )
        return True, [f"slot {slot!r}: present (schema check only)"]
    ok, results = run_gate_set(
        gates, ctx.gates, ctx.ledger, module, round_idx=ctx.round_idx
    )
    failing = [r for r in results if not r.passed and r.blocking]
    # A check the human ACCEPTED at the convergence gate — ledgered with its
    # reason and the numbers shown — does not refuse the fit built on it at
    # entry. The caveat the report carries is unchanged.
    honoured = _honoured_by_accept(ctx, failing)
    for r in honoured:
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"{r.gate_id} failed at entry ({r.detail}) but was ACCEPTED by "
            f"the human at the convergence gate for "
            f"{ctx.candidate or 'this model'} — honoured as validated-with-caveat",
            honoured_accept=True,
            gate_id=r.gate_id,
        )
    reasons = [r.detail for r in failing if r not in honoured]
    if ok or not reasons:
        record_validation(
            ctx,
            slot,
            validated_by=f"{module} battery"
            + (" (accepted checks honoured)" if honoured else ""),
            default_producer=default_producer,
        )
        line = (
            f"slot {slot!r}: {sum(1 for r in results if r.passed)}/"
            f"{len(results)} checks passed"
        )
        if honoured:
            line += (
                f"; {len(honoured)} failing check(s) honoured as accepted by the "
                f"human: {[r.gate_id for r in honoured]}"
            )
        return True, [line]
    # The FALLBACK when the ledger holds no acceptance for this candidate is
    # the gate's own decision record. With a ledger record, the rule above
    # governs: only the checks the person saw are honoured.
    accepted = human_accepted_fit(base) if slot == "estimation" else None
    if accepted is not None and _accept_record(ctx) is None:
        # The post-fit checks failed exactly as they did when the fit was made,
        # and a human ACCEPTED that failure then, with a reason, in
        # `decisions/estimation_convergence`; refusing now would overrule it.
        record_validation(
            ctx,
            slot,
            validated_by=f"{module} battery; failed check(s) accepted by the human "
            f"at {accepted.get('at')}: {str(accepted.get('note', ''))[:160]}",
            default_producer=default_producer,
        )
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"slot 'estimation' accepted on entry: {len(reasons)} failed check(s) "
            f"were accepted by the human when the fit was made "
            f"(decisions/estimation_convergence, {accepted.get('at')}); not re-asked",
            candidate=ctx.candidate,
        )
        return True, [
            f"slot {slot!r}: {len(reasons)} failed check(s) accepted by the human "
            f"when the fit was made ({'; '.join(r[:60] for r in reasons)})"
        ]
    return False, [f"slot {slot!r}: {r}" for r in reasons]


def _accept_record(ctx):
    """The ledger's LAST convergence acceptance for this candidate, or None."""
    from octomod.workflow_modules.estimation import convergence_record as _cr

    try:
        accepts = _cr.accepts_by_candidate(ctx.ledger.entries())
    except Exception:
        return None
    return accepts.get(getattr(ctx, "candidate", None) or "model")


def _honoured_by_accept(ctx, failing: list) -> list:
    """The failing checks that the ledger's LAST convergence acceptance for
    this candidate names in `failed_checks`. Anything else stays a failure:
    an acceptance covers the checks a person saw, not the slot."""
    if not failing:
        return []
    rec = _accept_record(ctx)
    if rec is None:
        return []
    covered = set(rec.failed_checks or [])
    return [r for r in failing if str(r.gate_id) in covered]


def human_accepted_fit(work) -> dict | None:
    """The recorded human decision that accepted this fit's failed post-fit
    checks, or None. `…/decisions/estimation_convergence` is written by the
    convergence gate with `approved` and the human's note; an `approved:
    false` or a `refit` answer is not an acceptance."""
    try:
        d = (work / "decisions/estimation_convergence").get(None)
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get("approved"):
        return None
    note = str(d.get("note") or "").strip().lower()
    if note.startswith("refit") or note.startswith("stop"):
        return None
    return d


def _validate_candidates(
    ctx, slot: str, cids: list[str], default_producer: str = "user-supplied"
) -> tuple[bool, list[str]]:
    """Validate a per-candidate slot in EVERY candidate of the round.

    The slot is only valid if every candidate's copy is: a discrimination round
    fits all of them, so one broken candidate is a broken round. Reasons name
    the candidate, because "the model slot is invalid" is useless when there
    are five of them.
    """
    was = ctx.candidate
    ok_all, reasons = True, []
    try:
        for cid in cids:
            if (
                slot == "estimation"
                and (tree.work_node(ctx.round, cid) / DECLINED_BUDGET).exists()
            ):
                # dropped by the human's `n` at its re-asked budget gate, not
                # left unfinished: the round's evaluation reads the candidates
                # it fitted
                reasons.append(
                    f"{cid}: not fitted — the human declined its estimation "
                    f"budget ({DECLINED_BUDGET}); dropped from the round, not required"
                )
                continue
            ctx.candidate = cid
            ok, why = validate(ctx, slot, default_producer=default_producer)
            ok_all = ok_all and ok
            reasons += [f"{cid}: {w}" for w in why]
    finally:
        ctx.candidate = was
    head = (
        f"slot {slot!r}: {len(cids)} candidate(s) validated"
        if ok_all
        else f"slot {slot!r}: invalid in at least one of {len(cids)} candidate(s)"
    )
    return ok_all, [head, *reasons]


def _gates_for(ctx, slot: str, base):

    if slot == "intent":
        from octomod.gates import GateResult, gate
        from octomod.orchestration.artifacts import validate_intent

        problems = validate_intent((base / "intent").get())

        @gate("entry_intent_schema", "T0")
        def g_intent():
            return GateResult(
                "entry_intent_schema",
                "T0",
                not problems,
                detail=" | ".join(problems) or "intent well-formed",
            )

        return [g_intent]

    if slot == "model":
        from octomod.gates.build_gates import make_build_gates, make_sbml_gates
        from octomod.gates.sim_gates import make_sim_gates

        holder: dict = {}
        ant = (base / "antimony").text(None)
        sbml_text = (base / "sbml").text()
        if ant is not None:
            gates = make_build_gates(ant, holder)
        else:
            holder["sbml"] = sbml_text
            gates = make_sbml_gates(holder)
        params = (base / "parameters").get([])
        from octomod.workflow_modules.model.simwrap import RRModel

        entities = set()
        try:
            m = RRModel(sbml_text)
            entities = set(m.entity_ids)  # species + boundary species + parameters
        except Exception:
            pass
        est_bounds = {
            p["id"]: (float(p["lb"]), float(p["ub"]))
            for p in params
            if p.get("estimate")
            and p.get("lb") is not None
            and (not entities or p["id"] in entities)
        }
        t_end = float(ctx.testcase.get("t_end", 100.0))
        gates += make_sim_gates(
            sbml_text,
            t_end,
            est_bounds,
            ctx.spec,
            required_entities=ctx.intent.get("required_entities"),
        )
        return gates

    if slot == "data":
        from octomod.workflow_modules.data.engine import make_data_gates

        long_df = (base / "data/measurements").table()
        report = (base / "data/report").get()
        return make_data_gates(long_df, report, ctx)

    if slot == "petab":
        from octomod.gates.petab_gates import PetabTables, make_petab_gates

        tables = PetabTables.from_work(base, ctx.model)
        return make_petab_gates(tables, ctx.spec)

    if slot == "estimation":
        from octomod.gates.fit_gates import make_fit_gates

        return make_fit_gates((base / "estimation").get(), ctx.spec)

    if slot == "compiled":
        from octomod.gates import GateResult, gate

        prof = (base / "cost").get()

        @gate("entry_compiled_profile", "T0")
        def g_compiled():
            ok = "median_start_s" in prof and "compile_s" in prof
            return GateResult(
                "entry_compiled_profile",
                "T0",
                ok,
                detail=(
                    "cost profile present"
                    if ok
                    else "the cost profile lacks the measured fields"
                ),
            )

        return [g_compiled]

    if slot == "evaluation":
        from octomod.gates import GateResult, gate

        rep = (base / "evaluation").get()

        @gate("entry_evaluation_schema", "T0")
        def g_eval():
            missing = [k for k in ("goal", "interpretation") if k not in rep]
            return GateResult(
                "entry_evaluation_schema",
                "T0",
                not missing,
                detail=(
                    f"the evaluation lacks {missing}"
                    if missing
                    else "the evaluation carries goal + interpretation"
                ),
            )

        return [g_eval]

    return None  # selection / decisions: presence only


# ------------------------------------------------------------ modular entry

# The DECISION records a module's gates write. `ask_once` reads them back so a
# RESUME never re-asks a signed question; an explicit `--from-module` re-entry
# forgets them, since its point is to answer differently. Keys are relative
# to the round AND to every candidate's group; the evaluation entry also
# forgets the interpretation pinned before the verdict gate.
MODULE_DECISIONS: dict[str, tuple[str, ...]] = {
    # re-entering at model rebuilds the candidate set or the lattice, so the
    # scope answer given for the OLD set must be asked again (the optional
    # base gate's answer, `decisions/model_base`, is kept: not listed)
    "model": ("decisions/model_scope",),
    # the compile approval, asked once per round on both paths
    # (`compile_gate`). It approves the compile and probe, so every re-entry at
    # estimation or upstream forgets it, and a rebuilt problem is never
    # compiled on an old yes.
    "estimation": (
        "decisions/assembly_cost_boundary",
        "decisions/estimation_convergence",
    ),
    "evaluation": (
        "decisions/evaluation_verdict",
        "agent_calls/interpretation/pinned",
        # the revision gates' answers (s11): a re-evaluated round is a new
        # verdict, so whether to revise it is asked again
        "decisions/revision_proposal_stop_vs_revise",
        "decisions/revision_proposal",
    ),
}


def _bases(ctx) -> list:
    """The round, its own unit of work (`candidates/_single`: a single-model
    round's fit and the decisions recorded on it, e.g. `estimation_convergence`), and
    every candidate the round declared (`space/candidates`)."""
    rnd = ctx.round
    return [rnd, tree.work_node(rnd, None)] + [
        tree.work_node(rnd, c) for c in declared_candidates(rnd)
    ]


def invalidate_from(ctx, module: str) -> tuple[list[str], list[str], list[str]]:
    """Remove what `module` and everything downstream own, in the round AND
    in every candidate's group: the module markers, the gate DECISIONS those
    modules recorded, and a solver override in the cost profile (`cost`) that
    the re-entered fit will not apply. Returns (markers removed, decisions
    forgotten, cost records whose override was dropped).
    """
    module = normalise_module(module)
    rnd = ctx.round
    bases = _bases(ctx)
    removed: list[str] = []
    forgotten: list[str] = []
    dropped: list[str] = []
    for m in markers_from(module):
        for base in bases:
            if base.name == tree.SINGLE:
                continue  # a single-model round's markers are the round's
            markers = tree.markers_node(rnd, None if base == rnd else base.name)
            if markers.child(m).delete():
                removed.append(m)
        # the unit of work's own markers, when it is not a declared candidate
        if ctx.marker(m).delete():
            removed.append(m)
    seen = False
    for name, _slots, _markers in MODULES:
        if name == module:
            seen = True
        if not seen:
            continue
        for rel in MODULE_DECISIONS.get(name, ()):
            for base in bases:
                n = base / rel
                if n.delete():
                    forgotten.append(_rel(rnd, n))
    if module in ("model", "data", "assembly", "estimation"):
        for base in bases:
            for prof_node in _cost_nodes(rnd, base):
                d = prof_node.get(None)
                if isinstance(d, dict) and d.get("gate_overrides"):
                    d["gate_overrides_dropped_on_reentry"] = d.pop("gate_overrides")
                    d["gate_overrides_note"] = (
                        "dropped when estimation was re-entered or the problem "
                        "rebuilt: the next fit runs on the spec's declared solver "
                        "settings unless the budget gate is answered again with "
                        "an override"
                    )
                    prof_node.put(d)
                    dropped.append(_rel(rnd, prof_node))
    return removed, forgotten, dropped


def _cost_nodes(rnd, base) -> list:
    """Where a cost profile can be, for `base`: a unit of work's own group
    (`_single` or a candidate); the round itself holds none."""
    if base == rnd:
        return []
    return [base / "cost"]


def _rel(rnd, node) -> str:
    """A node's key relative to the round, for ledger rows and messages."""
    prefix = rnd.key + "/"
    return node.key[len(prefix) :] if node.key.startswith(prefix) else node.key


def required_before(module: str) -> list[str]:
    """Slots that must be valid to enter at `module`."""
    out: list[str] = ["intent"]
    for name, slots, _ in MODULES:
        if name == module:
            break
        out += slots
    return out


def markers_from(module: str) -> list[str]:
    """Markers that `module` and everything after it own — invalidated on entry."""
    out: list[str] = []
    seen = False
    for name, _, markers in MODULES:
        if name == module:
            seen = True
        if seen:
            out += markers
    return out


def _supplied_problem_slot(ctx, module: str) -> str | None:
    """The slot `module` produces, when the target round records it as the
    user's own supplied PEtab problem; None when entry there is open.

    Keyed on the round's recorded producer, so a later round whose model an
    agent rebuilt re-enters like any other. The input's `supplied/petab` is a
    precondition too: `user-supplied` is also the producer a seeded round's
    model and a slot first recorded by an entry validator carry, and neither
    is a problem the user supplied whole."""
    from pathlib import Path

    if MODULE_NAMES.index(module) >= MODULE_NAMES.index("estimation"):
        return None
    if not (Path(ctx.testcase_dir) / "supplied" / "petab").is_dir():
        return None
    status = slot_state(ctx.round)
    cands = status.get("candidates") or {}
    if ctx.candidate is not None:
        cands = {ctx.candidate: cands.get(ctx.candidate) or {}}
    for slot in dict((name, slots) for name, slots, _ in MODULES)[module]:
        records = [(status.get("slots") or {}).get(slot)] + [
            (entry or {}).get(slot) for entry in cands.values()
        ]
        if any((rec or {}).get("producer") == "user-supplied" for rec in records):
            return slot
    return None


def enter(ctx, module: str, *, invalidate: bool = True) -> None:
    """Validate every upstream slot, mark the upstream modules as passed
    (producer recorded as found or `user-supplied`), and invalidate the entry
    module and everything downstream so they run afresh. Refuses — with the
    named slot and the failing check — rather than starting a run on an
    artifact nobody validated.

    `invalidate=False` is for the case where entry is IMPLIED rather than asked
    for: a testcase with `supplied/petab` enters at estimation on every
    invocation, including the resume that only answers a gate. Invalidating
    there throws away finished work: a resume that exists only to answer the
    profiling gate would re-run the multistart (measured: a 100-start
    multistart, 93 minutes). Upstream slots are still validated; nothing
    is trusted that was not checked. What makes this safe is that the two
    mechanisms are complementary: `run_guard` already REFUSES a resume whose
    staged inputs moved, so invalidation is only needed when a human asks for a
    re-entry with `--from-module`, which is exactly when it stays on.

    A problem supplied whole as PEtab (`input/supplied/petab`) refuses entry
    at model, data and assembly by name in a round whose slot for that module
    is the user's own (recorded `user-supplied`): nothing upstream of
    estimation produced it, so there is nothing there to redo. A later round
    whose slot an agent produced re-enters like any other."""
    from octomod.orchestration.run_context import ModuleFailure

    module = normalise_module(module)
    # A problem supplied whole as PEtab has no producer upstream of estimation:
    # re-entering there would draft a model for a problem the user supplied,
    # or read a data folder the input does not have. Refused before anything
    # is validated or moved, so the finished run stays as it was.
    supplied_slot = _supplied_problem_slot(ctx, module)
    if supplied_slot is not None:
        raise ModuleFailure(
            f"entry at {module!r} refused — this run's problem was supplied whole "
            f"as a PEtab problem (input/supplied/petab), and "
            f"{ctx.round.name}'s {supplied_slot!r} slot is recorded as "
            f"user-supplied in the round's status, so no module upstream of "
            f"estimation has anything to re-run there: the model, data and "
            f"assembly slots are the user's own. Open instead: --from-module "
            f"estimation or --from-module evaluation on this run; or, if the "
            f"supplied problem itself was wrong, a new run with an edited "
            f"input (start it with --from-run {ctx.store.run_id} and edit its "
            f"input/ group, or stage the case again and run with --testcase). "
            f"Nothing was run."
        )
    print(
        f"\n▶ ENTRY at module {module!r} — validating everything upstream "
        f"before any agent or compute runs"
    )
    failures = []
    for slot in required_before(module):
        ok, reasons = validate(ctx, slot)
        for r in reasons:
            print(f"  {'✓' if ok else '✗'} {r}")
        if not ok:
            failures += reasons
    if failures:
        raise ModuleFailure(
            f"entry at {module!r} refused — upstream slot(s) missing or invalid: "
            + " | ".join(failures)
            + " (supply or fix the named artifact; nothing was run)"
        )
    # upstream markers: set where absent, so the modules skip cleanly
    for name, slots, markers in MODULES:
        if name == module:
            break
        for m in markers:
            if not ctx.has_marker(m):
                # the producer the slot's own validator recorded, else: an
                # absent marker's slot was supplied, by definition
                status = slot_state(ctx.round)
                producers = {
                    (status.get("slots", {}).get(s) or {}).get("producer")
                    for s in slots
                }
                producer = next((p for p in producers if p), "user-supplied")
                ctx.set_marker(
                    m,
                    producer=producer,
                    entry=True,
                    validated_by=f"entry_{'+'.join(slots)} battery",
                )
    # entry module + downstream: invalidate, unless entry was implied. Markers,
    # recorded gate decisions and stale solver overrides alike, in the round
    # and in every candidate's group — and the invalidated slots' RECORDS
    # moved aside.
    removed: list[str] = []
    forgotten: list[str] = []
    dropped: list[str] = []
    superseded: list[str] = []
    if invalidate:
        removed, forgotten, dropped = invalidate_from(ctx, module)
        # A marker is not the artifact: a module that finds its old output takes
        # it as carried forward or pre-seeded. The invalidated slots' RECORDS
        # are moved aside — never deleted — into `superseded/<module>_<stamp>/`
        # so nothing in the record can masquerade as an input to the module
        # being redone.
        superseded = supersede_slots(ctx, module)
    ctx.ledger.append(
        "entry",
        module=f"entry_{module}",
        round_idx=ctx.round_idx,
        from_module=module,
        validated=required_before(module),
        invalidated_markers=sorted(set(removed)),
        superseded_files=superseded,
        forgotten_decisions=forgotten,
        dropped_solver_overrides=dropped,
        entry_implied=not invalidate,
    )
    if removed:
        print(
            f"  invalidated downstream markers {sorted(set(removed))} — those "
            f"modules run again from here"
        )
    if forgotten:
        print(
            f"  forgot recorded gate decisions {forgotten} — those gates ask "
            f"again (re-entry means the answer may change)"
        )
    if dropped:
        print(
            f"  dropped stale solver overrides in {dropped} — the re-entered fit "
            f"runs on the spec's declared settings unless chosen again"
        )
    if superseded:
        print(
            f"  moved {len(superseded)} artifact(s) of the invalidated modules "
            f"aside under {SUPERSEDED_KEY}/ (kept, not deleted)"
        )


def slots_from(module: str) -> list[str]:
    """Slots that `module` and everything after it produce."""
    out: list[str] = []
    seen = False
    for name, slots, _ in MODULES:
        if name == module:
            seen = True
        if seen:
            out += slots
    return out


# Where a re-entry keeps what it moved aside: `rounds/round_<k>/superseded/
# <module>_<stamp>/<the same keys, relative to the round>`.
SUPERSEDED_KEY = "superseded"


def supersede_slots(ctx, module: str) -> list[str]:
    """Move the records of every slot produced from `module` onward into
    `superseded/<module>_<stamp>/`, preserving their keys relative to the
    round. Per-candidate slots are collected from the round's own unit of
    work AND every candidate's group. Returns the relative keys moved (for
    the ledger)."""
    rnd = ctx.round
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_root = rnd / SUPERSEDED_KEY / f"{module}_{stamp}"
    moved: list[str] = []

    def _move(src):
        if not src.exists():
            return
        rel = _rel(rnd, src)
        src.copy_to(dest_root / rel)
        src.delete()
        moved.append(rel)

    units = [None, tree.SINGLE, *declared_candidates(rnd)]
    for slot in slots_from(module):
        slot_spec = SLOTS.get(slot) or {}
        scope = slot_spec.get("scope", "round")
        if scope in PER_CANDIDATE:
            for cid in units:
                base = slot_base(rnd, slot, cid)
                for rel in slot_spec.get("parts", []):
                    _move(base / rel)
        elif scope == "round":
            for rel in slot_spec.get("parts", []):
                _move(rnd / rel)
    # Not slot parts, but the same masquerade: a module's cached agent replies
    # (its attempt dossier included) and the round-level shared assembly S3
    # pre-seeds from. A module re-entered "afresh" must not inherit them.
    seen_entry = False
    for name, _slots, _markers in MODULES:
        if name == module:
            seen_entry = True
        if not seen_entry:
            continue
        for src in _module_caches(rnd, name):
            _move(src)
    # what the record checks found for those modules describes the records
    # just moved aside; the modules' next pass is checked afresh
    from octomod.result import completeness

    completeness.forget(ctx.root, ctx.round_idx, markers_from(module))
    return moved


# Per-module caches that are not slot artifacts yet would be read as inputs by
# the re-entered module (see supersede_slots). Keys relative to the round; an
# `agent_calls/<prefix>*` entry names every agent call whose role starts with
# the prefix (its prompt, reply and attempt dossier are one group).
_MODULE_CACHE_PATTERNS: dict[str, list[str]] = {
    "data": ["agent_calls/data_extraction*"],
    "assembly": [
        "shared_assembly",
        # the round's engine redraft answers the replies being moved aside; a
        # fresh draft has its own
        "compile_feedback",
        "agent_calls/observation*",
        "agent_calls/condition*",
        "agent_calls/assembly_verification*",
        # a role's fallback lives beside its reply
        "agent_calls/*/fallback_applied",
    ],
    # the solver choices a human made at this module's gates (the
    # round's budget gate, a re-asked one, the refits) are the module's
    # DECISIONS — re-entering it is how they are made again, and a kept record
    # would silently re-apply the old ones to every build of the new pass
    "estimation": [
        "estimation_settings",
        "candidates/*/estimation_settings",
        # a candidate's `n` at its re-asked budget gate is a decision made at
        # this module's gate too: re-entering at estimation is how it is made
        # again, and a kept record would drop the candidate unasked
        f"candidates/*/{DECLINED_BUDGET}",
    ],
    # a re-entered evaluation must ASK its own ask_once gates again — the
    # human is re-entering to give a different answer. Only the profiling
    # gate's answer: the human's own profile request
    # (`decisions/evaluation_profile_request`) is KEPT across the re-entry
    "evaluation": [
        "decisions/evaluation_profile",
        "decisions/evaluation_verdict",
        "agent_calls/interpretation*",
    ],
}


def _module_caches(rnd, module: str) -> list:
    """The nodes `_MODULE_CACHE_PATTERNS[module]` names in this round."""
    import fnmatch

    out = []
    for pattern in _MODULE_CACHE_PATTERNS.get(module, []):
        parent_key, _, leaf = pattern.rpartition("/")
        if "*" in parent_key:
            # `candidates/*/<leaf>`: one level of wildcard group
            head, _, tail = parent_key.partition("/*")
            tail = tail.strip("/")
            parents = []
            for c in (rnd / head).children():
                p = (rnd / head).child(c)
                parents.append(p / tail if tail else p)
        else:
            parents = [rnd / parent_key if parent_key else rnd]
        for parent in parents:
            if "*" in leaf:
                out += [
                    parent.child(name)
                    for name in parent.children()
                    if fnmatch.fnmatch(name, leaf)
                ]
            else:
                out.append(parent / leaf)
    return out


# ----------------------------------------------- supplied PEtab adapter


def adapt_supplied_petab(ctx) -> None:
    """Derive the model and data slots from a user-supplied PEtab problem so
    the run can enter at estimation. This is the adapter docs/MODULARITY.md
    names as where the work is: SBML normalisation, parameter-table conventions,
    measurement rows -> the engine's long table with semantic condition keys,
    and the staged holdout split.

    The problem is read from the inputs (`supplied/petab/`, an INPUT on
    disk) and written into the record as the round's model and data slots
    and the fitted problem's tables. The petab slot itself is validated by the
    S3 battery at entry; the model slot by the ladder (SBML entry, Antimony
    reconstructed when antimony can); the data slot by the S2 checks.
    Construction is never called: the supplied problem IS the model, so it
    enters as a validated petab slot (docs/MODULARITY.md).
    """
    import pandas as pd
    import yaml

    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.assembly import petab_io
    from octomod.workflow_modules.data.engine import condition_key, parse_declared_label

    src_dir = ctx.testcase_dir / "supplied" / "petab"
    try:
        found = sorted(src_dir.glob("*.yaml")) + sorted(src_dir.glob("*.yml"))
        if not found:
            raise ModuleFailure("supplied/petab has no problem yaml")
        yaml_path = next((p for p in found if p.name == "problem.yaml"), found[0])
        spec = yaml.safe_load(yaml_path.read_text()) or {}
        if len(spec.get("problems") or [{}]) != 1:
            raise ModuleFailure("supplied PEtab yaml must describe exactly one problem")
        inp = petab_io.from_dir(yaml_path)
    except ModuleFailure:
        raise
    except (FileNotFoundError, ValueError) as e:
        raise ModuleFailure(f"supplied PEtab: {e}") from e

    model = ctx.round / "model"
    petab = ctx.work / "petab"
    sbml = inp.sbml
    (model / "sbml").put_text(sbml)
    # Antimony reconstruction: the ladder's first rung and the human-readable
    # source both want it; when antimony cannot round-trip the SBML the model
    # slot validates from the SBML directly and says so.
    try:
        import antimony

        antimony.clearPreviousLoads()
        if antimony.loadSBMLString(sbml) >= 0:
            src = antimony.getAntimonyString(antimony.getMainModuleName())
            if src:
                (model / "antimony").put_text(src if src.endswith("\n") else src + "\n")
    except Exception as e:
        ctx.ledger.append(
            "note",
            module="seed",
            round_idx=ctx.round_idx,
            note=f"antimony reconstruction unavailable: {e}",
        )

    # the tables, as an assembled problem holds them; the yaml names them the
    # way `petab_io.export_dir` writes them
    inp = inp.with_tables(
        holdout=None,
        problem_yaml={
            "format_version": inp.problem_yaml.get("format_version", 1),
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

    # AMICI refuses to import a problem whose observable or noise parameters
    # are overridden per timepoint ("please flatten the problem and try
    # again"). PEtab's own remedy is to split such an observable into one
    # observable per override group; the deposit that first exercised this
    # adapter (CTD, one xi_t override per timepoint) does exactly that in its
    # own run script. Flattening renames observables, so the ledger records
    # the rename rather than letting the report quietly change its labels.
    from octomod.orchestration.artifacts import flatten_timepoint_specific

    inp, flat = flatten_timepoint_specific(inp, include_holdout=False)
    if flat is not None:
        ctx.ledger.append(
            "note",
            module="seed",
            round_idx=ctx.round_idx,
            note=(
                "supplied PEtab had timepoint-specific observable/noise "
                "parameter overrides; flattened for AMICI "
                f"({flat['n_before']} observables -> {flat['n_after']}). "
                "Observable ids in the report are the flattened ids; the "
                "observableName column carries the supplied name."
            ),
        )

    # model/parameters: the engine's declaration of the DYNAMIC parameters
    # (model entities only — observable/noise parameters belong to the tables)
    from octomod.workflow_modules.model.simwrap import RRModel

    entities = set()
    try:
        m = RRModel(sbml)
        entities = set(m.entity_ids)  # species + boundary species + parameters
    except Exception as e:
        raise ModuleFailure(f"supplied SBML does not load in roadrunner: {e}") from e
    par = inp.parameters
    params = []
    for _, r in par.iterrows():
        pid = str(r["parameterId"])
        if pid not in entities:
            continue
        params.append(
            {
                "id": pid,
                "nominal_value": float(r.get("nominalValue", 1.0)),
                "unit": "",
                "evidence_tier": "user-supplied",
                "source": "supplied PEtab parameter table",
                "estimate": bool(int(r.get("estimate", 0))),
                "lb": float(r.get("lowerBound", 1e-5)),
                "ub": float(r.get("upperBound", 1e5)),
            }
        )
    (model / "parameters").put(params)

    # measurements -> the engine's long table, with semantic condition keys
    meas = inp.measurements
    cond = inp.conditions.set_index("conditionId")
    keys = {}
    for cid, row in cond.iterrows():
        vals = {c: v for c, v in row.items() if c != "conditionName" and pd.notna(v)}
        keys[str(cid)] = condition_key(vals)
    rows = []
    rep_counter: dict[tuple, int] = {}
    for _, r in meas.iterrows():
        k = (str(r["observableId"]), str(r["simulationConditionId"]), float(r["time"]))
        rep_counter[k] = rep_counter.get(k, 0) + 1
        rows.append(
            {
                "observable_label": k[0],
                "condition_label": k[1],
                "condition_key": keys.get(k[1], ""),
                "time": k[2],
                "value": float(r["measurement"]),
                "replicate": rep_counter[k],
            }
        )
    long_df = pd.DataFrame(rows)
    obs_tbl = inp.observables
    obs_names = {}
    if "observableName" in obs_tbl.columns:
        obs_names = {
            str(r["observableId"]): str(r["observableName"])
            for _, r in obs_tbl.iterrows()
            if pd.notna(r.get("observableName"))
        }
    data = ctx.round / "data"
    (data / "measurements").put_table(long_df)
    (data / "report").put(
        {
            "mappings": [],
            "observable_labels": [
                {
                    "label": o,
                    "description": (
                        f"{obs_names[o]} (as supplied, PEtab observable)"
                        if o in obs_names
                        else "as supplied (PEtab observable)"
                    ),
                    "units": "as supplied (PEtab)",
                    "error_type": "replicates",
                    "n": None,
                }
                for o in sorted(long_df["observable_label"].unique())
            ],
            "flags": [],
            "notes": "PEtab problem supplied by the user; measurements "
            "taken verbatim from its measurement table",
            "provenance": [{"source": str(yaml_path), "kind": "petab"}],
        },
    )

    # holdout split, by the staged declaration (condition ids or column=value keys)
    holdout_labels = ctx.testcase.get("holdout", {}).get("condition_labels", [])
    hold_mask = pd.Series(False, index=meas.index)
    for h in holdout_labels:
        k = parse_declared_label(h)
        hit = meas["simulationConditionId"].astype(str) == str(h)
        if k:
            hit |= meas["simulationConditionId"].astype(str).map(keys) == k
        if not hit.any():
            raise ModuleFailure(
                f"declared holdout {h!r} matches no condition in the "
                f"supplied PEtab problem (ids {sorted(keys)})"
            )
        hold_mask |= hit
    if hold_mask.any():
        inp = inp.with_tables(holdout=meas[hold_mask], measurements=meas[~hold_mask])
    petab_io.to_record(inp, petab)
    # the producer of these slots is the user, recorded where the slot state
    # reads it (no marker names one yet)
    for slot in ("model", "data", "petab"):
        record_validation(
            ctx, slot, validated_by=None, default_producer="user-supplied"
        )
    ctx.ledger.append(
        "artifact",
        module="seed",
        round_idx=ctx.round_idx,
        artifact="model, data, petab (derived from supplied PEtab)",
        producer="user-supplied",
        n_dynamic_params=len(params),
        n_measurements=len(meas),
        n_holdout=int(hold_mask.sum()),
    )
    print(
        f"  supplied PEtab adapted: {len(params)} dynamic parameters, "
        f"{len(meas)} measurements ({int(hold_mask.sum())} held out) — "
        f"construction and assembly agents will NOT be called"
    )


# ---------------------------------------------------------------- reporting


def summary_lines(rnd) -> list[str]:
    """The slot state of a round in words — computed, never read from an index."""
    state = slot_state(rnd)
    lines = [f"{rnd.name}: slot state (computed from the record)"]
    for slot, rec in state["slots"].items():
        by = str(rec.get("validated_by", "—"))
        if slot == "evaluation" and by.startswith("entry_evaluation battery"):
            # evaluation is the last module, so no entry validates its slot:
            # `round_seed.require_evaluation` does, before seeding the next
            # round, and the stored value is the validator's module name
            by += " (the slot's own validator, run before the next round was seeded)"
        lines.append(
            f"  {slot:11s} {'present' if rec.get('present') else 'MISSING':8s} "
            f"producer={rec.get('producer')} "
            f"validated={rec.get('validated_at', '—')} "
            f"by={by}" + (f" drifted={rec['drifted']}" if rec.get("drifted") else "")
        )
    for cid, slots in state["candidates"].items():
        lines.append(f"  candidate {cid}:")
        for slot, rec in slots.items():
            lines.append(
                f"    {slot:11s} {'present' if rec.get('present') else 'MISSING':8s} "
                f"validated={rec.get('validated_at', '—')}"
            )
    return lines
