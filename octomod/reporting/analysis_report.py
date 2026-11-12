"""The whole-analysis report: one document for the run, not for a round.

What was asked, what models were assessed across every round, which one won,
what the answer to the original question is, and what is still open. It reads
only what the run record already holds — reports, markers, the ledger — so it
can be regenerated for any finished or half-finished run without recomputing
anything, and it never asks an agent for a claim the engine already recorded.
"""

from __future__ import annotations

from pathlib import Path

from octomod.orchestration.interaction import humangate
from octomod.result.node import Node


def lineage(root: Node, round_idx: int, model_id: str) -> str:
    """A round-local id resolved to the structure it actually names.

    Candidate ids are local to their round: after an expansion, `base` means
    "the previous round's winner, with none of the new axes on", which at run
    level reads as though nothing was built. Walk the expansion records back
    to round 0 and name every axis the structure carries.
    """
    return " + ".join(lineage_axes(root, round_idx, model_id)) or model_id


def lineage_axes(root: Node, round_idx: int, model_id: str) -> list[str]:
    """The structure a round-local id names, as an ordered list: the round-0
    candidate first, then every axis the structure carries.

    When an expansion CARRIED undecided axes (`carried_undecided` in that
    round's `expansion` record), the next round's base was the previous base
    WITHOUT them — they were re-searched, and a later model carries one only
    if its own id says so.
    """
    from octomod.result.access import expansion_dict, record_for

    rr = record_for(root)
    contributions: list[tuple[int, list[str]]] = []
    idx, mid = round_idx, model_id
    drop_after: dict[int, set[str]] = {}  # round -> axes NOT inherited from it
    while True:
        if mid and mid != "base":
            contributions.append((idx, [a for a in str(mid).split("+") if a]))
        if idx <= 0:
            break
        prev = rr.rounds.get(f"round_{idx - 1}")
        decided = (expansion_dict(prev) if prev is not None else None) or {}
        if not decided.get("expanded"):
            break
        carried = {str(a) for a in (decided.get("carried_undecided") or [])}
        if carried:
            drop_after[idx - 1] = carried
        mid = str(decided.get("from_winner") or "")
        idx -= 1
    out: list[str] = []
    for r, ids in reversed(contributions):
        # an axis inherited from round r is dropped if any LATER expansion
        # carried it live again (it is then only present if a later id has it)
        dropped = (
            set().union(*(v for k, v in drop_after.items() if k >= r))
            if drop_after
            else set()
        )
        for a in ids:
            if a in dropped and r < round_idx:
                continue
            if a not in out:
                out.append(a)
    return out


def _all_models(rounds: list[tuple[int, dict]], root: Node) -> list[dict]:
    """Every model fitted anywhere in the run, with the round it came from.

    Criterion values are only comparable WITHIN a round — a later round may fit
    different data or a different base — so the round is carried with each row
    and never silently pooled.
    """
    rows = []
    for idx, rep in rounds:
        disc = rep.get("discrimination")
        if disc:
            for c in disc["candidates"]:
                rows.append(
                    {
                        "round": idx,
                        "model": c["id"],
                        "n_estimated": c.get("n_est"),
                        "nllh": c.get("nllh"),
                        "delta_aic": c.get("delta_aic"),
                        "weight": c.get("akaike_weight"),
                        "selected": c["id"] == disc["winner"],
                        "lineage": lineage(root, idx, c["id"]),
                    }
                )
        else:
            rows.append(
                {
                    "round": idx,
                    "model": f"round {idx} model",
                    "n_estimated": None,
                    "nllh": rep.get("best_fval"),
                    "delta_aic": None,
                    "weight": None,
                    "selected": True,
                    "lineage": f"round {idx} model",
                }
            )
    return rows


def build(root: Node) -> dict:
    """The run-level summary, for the run record's root node."""
    from octomod.result import access as _acc

    rr = _acc.record_for(root)
    intent = _acc.intent(rr)
    rounds = _acc.rounds_with_reports(rr)
    ledger = _acc.ledger_rows(rr)
    if not rounds:
        return {"error": "no completed round in this run"}

    final_idx, final = rounds[-1]
    disc = final.get("discrimination")
    ev = final.get("misfit_evidence") or {}
    interp = final.get("interpretation") or {}

    cost = sum(r.get("cost_usd") or 0 for r in ledger if r.get("event") == "agent_call")
    n_calls = sum(1 for r in ledger if r.get("event") == "agent_call")
    # drift toward re-iteration must be visible run over run
    contract_retries = sum(
        max(int(r.get("attempts") or 1) - 1, 0)
        for r in ledger
        if r.get("event") == "agent_call"
    )
    module_redrafts = sum(1 for r in ledger if r.get("event") == "redraft")
    redraft_grants = sum(
        int(r.get("granted") or 0) for r in ledger if r.get("event") == "redraft_grant"
    )
    from octomod.workflow_modules.model import model_space as _ms
    from octomod.workflow_modules.model import tried_models as _tried

    regime = _ms.comparability_regime(root)
    topology = _ms.search_topology(
        _tried.declared_axes_this_run(root), _tried.models_fitted_this_run(root)
    )
    gates = [r for r in ledger if r.get("event") == "human_gate"]
    # WHO answered, counted separately: a policy-answered gate is not a human
    # decision, and a run with a policy in force may have had no human in it
    # at all.
    human = [r for r in gates if r.get("mode") in ("interactive", "file")]
    by_policy = [r for r in gates if r.get("mode") == "policy"]
    by_auto = [r for r in gates if r.get("mode") == "auto"]
    meta = _acc.run_meta(rr)
    gate_policy = (
        {
            "profile": meta.get("policy_profile"),
            "sha": meta.get("policy_sha"),
            "source": (
                Path(str(meta.get("policy"))).name if meta.get("policy") else None
            ),
            "answers": [
                {
                    "module": r.get("module"),
                    "round": r.get("round"),
                    "approved": bool(r.get("approved")),
                    "note": r.get("note") or "",
                    "covered_by": r.get("covered_by") or "",
                }
                for r in by_policy
            ],
            # one definition of how a signature reads, shared with the
            # decision files the engine writes at the gate itself
            "verdict_signed_by": humangate.signature_of(
                next(
                    (
                        r
                        for r in reversed(gates)
                        if r.get("module") == "evaluation_verdict"
                    ),
                    None,
                )
            ),
        }
        if meta.get("policy_profile")
        else None
    )
    end = next((r for r in reversed(ledger) if r.get("event") == "run_end"), {})

    # what the run actually concluded, stated in the engine's own terms
    if disc:
        answer = {
            "selected_model": disc["winner"],
            "selected_structure": lineage(root, rounds[-1][0], disc["winner"]),
            "decisive": disc["decisive"],
            "indistinguishable_set": disc["indistinguishable"],
            "basis": "information criterion over the fitted candidate set",
        }
        if not disc["decisive"]:
            answer["read_this_as"] = (
                f"the data do not separate {len(disc['indistinguishable'])} of the "
                f"fitted structures; the winner is ranked first, not established"
            )
    else:
        hold = final.get("holdout", {})
        answer = {
            "selected_model": f"round {final_idx} model",
            "basis": "single-model calibration",
            "held_out_prediction": (
                {
                    "available": True,
                    "worst_group": max(hold["groups"], key=lambda g: g["nrmse"])[
                        "label"
                    ],
                    "worst_nrmse": round(max(g["nrmse"] for g in hold["groups"]), 4),
                }
                if hold.get("available")
                else {"available": False}
            ),
        }

    still_open = []
    if ev.get("open"):
        still_open += [f"structural misfit: {r}" for r in ev.get("reasons", [])]
    if disc and not disc["decisive"]:
        still_open.append(
            f"selection not decisive — {disc['indistinguishable']} are "
            f"indistinguishable on this data"
        )
    for c in (interp.get("cannot_distinguish") or [])[:6]:
        still_open.append(f"declared undetermined: {str(c)[:120]}")
    # A fit whose convergence a human ACCEPTED rather than demonstrated stays
    # an open question at run level too — per candidate, because candidates
    # are compared and only some of them may carry it.
    from octomod.workflow_modules.estimation import convergence_record as _cr

    for rec in _cr.accepts_by_candidate(ledger).values():
        still_open.append(
            f"convergence {'PRE-' if rec.pre_declared else ''}ACCEPTED, not "
            f"demonstrated for {rec.key}: "
            + "; ".join(rec.check_lines())
            + f" — reason given: {rec.reason[:120] or '(none)'}"
        )

    return {
        "run": root.store.run_id,
        "question": intent.get("question", ""),
        "inference_target": intent.get("inference_target", ""),
        "system": intent.get("system", ""),
        "success_criteria": intent.get("success_criteria", []),
        "n_rounds": len(rounds),
        "rounds": [
            {
                "round": i,
                "what_changed": _what_changed(root, i),
                "selected": (r.get("discrimination") or {}).get("winner")
                or f"round {i} model",
                "selected_structure": lineage(
                    root, i, (r.get("discrimination") or {}).get("winner") or ""
                )
                or f"round {i} model",
            }
            for i, r in rounds
        ],
        "models_assessed": _all_models(rounds, root),
        "answer": answer,
        "answers_intent": interp.get("answers_intent", []),
        # what the expansion agent says lies beyond this data, per round
        "beyond_this_data": beyond_this_data(root),
        # who proposed each reaction of each round's selected model, the
        # floors, the searches and what the floor refused
        "model_origin": model_origin(root, rounds, ledger),
        "still_open": still_open,
        "gate_policy": gate_policy,
        "cost": {
            "agent_calls": n_calls,
            "usd": round(cost, 2),
            "human_decisions": len(human),
            "policy_decisions": len(by_policy),
            "auto_decisions": len(by_auto),
            "contract_retries": contract_retries,
            "module_redrafts": module_redrafts,
            "redraft_grants": redraft_grants,
            "attempts_per_call": round(
                (n_calls + contract_retries) / max(n_calls, 1), 3
            ),
        },
        "outcome": end.get("outcome", "(run not finished)"),
        # the run page reads the axes and the attribution off the round
        # records, so it needs to know where they are: the record file
        "record": str(root.store.path),
        # what this run was STARTED WITH, in the run's own record: the answer
        # beside the question it was put
        "inputs": _inputs(root, meta),
        # whether the record holds what each finished step should have left:
        # the checks up to this point (the final write is checked after it)
        "record_checks": _record_checks(root),
        # which models the agent calls ran on (written at run end from the ledger)
        "models_used": (
            (root / "models_used").get(None)
            if (root / "models_used").exists()
            else None
        ),
        # the run document states a contradicted declaration above its own
        # answer, so the final round's record travels here
        "declared_constants": final.get("declared_constants") or {},
        "provenance": {
            "workflow_sha": meta.get("workflow_sha"),
            # the code that produced these numbers, carried up from the run's
            # metadata: a reproducibility claim that cannot name the commit
            # is not one
            "code": meta.get("provenance") or {},
            # the caveat, stated for the regime this run is actually in
            "note": "every gate verdict, agent call and human decision is in "
            "the run's ledger. " + str((regime or {}).get("why", "")),
            "cross_round_comparability": regime,
            "search_topology": topology,
        },
    }


def input_files(root: Node) -> list[str]:
    """The files of the record's `input` snapshot, as the paths they were
    staged under (a file's `/` is kept in its key), sorted."""
    try:
        keys = [k for k, kind in root.store.walk("input") if kind == "dataset"]
    except Exception:
        return []
    return sorted(k[len("input/") :] if k.startswith("input/") else k for k in keys)


def _inputs(root: Node, meta: dict) -> dict:
    """The `input` snapshot as a reader needs it: the files, the sha they hash
    to, where they came from, and the run they were copied from when there was
    one. A run whose record does not carry its inputs says where it read them
    instead of pretending to a snapshot it never took."""
    snapshotted = (root / "input").exists()
    return {
        "dir": "input" if snapshotted else "",
        "files": input_files(root) if snapshotted else [],
        # not every input file is part of the identity: a data GENERATOR is
        # copied (it is part of what the run was started with) but not hashed,
        # so editing one cannot fail a resume it could not have affected.
        "hashed": len(meta.get("input_files") or {}),
        "sha": meta.get("input_sha") or meta.get("testcase_sha") or "",
        "source": (
            meta.get("input_source") or meta.get("testcase") or "(not recorded)"
        ),
        "project": meta.get("project") or "",
        "started_from": meta.get("started_from") or "",
        "in_place": not snapshotted,
    }


def _what_changed(root: Node, idx: int) -> str:
    """Why this round differs from the one before it — read from the decision
    the human actually approved, not inferred."""
    from octomod.result.access import expansion_dict, record_for, revision_dict

    if idx == 0:
        return "initial model space"
    prev = record_for(root).rounds.get(f"round_{idx - 1}")
    d = expansion_dict(prev) if prev is not None else None
    if d is not None and d.get("expanded"):
        # the round-local id again: at run level, name the structure
        carried = [str(a) for a in (d.get("carried_undecided") or [])]
        base_axes = [
            a
            for a in lineage_axes(root, idx - 1, str(d.get("from_winner") or ""))
            if a not in carried
        ]
        base = " + ".join(base_axes) or str(d.get("from_winner") or "")
        new_axes = [str(a) for a in (d.get("axes") or []) if str(a) not in carried]
        text = f"space expanded on top of {base}"
        if carried:
            text += f", re-searching the undecided {', '.join(carried)}"
        if new_axes:
            text += f", adding {', '.join(new_axes)}"
        return text
    d = revision_dict(prev) if prev is not None else None
    if d is not None and d.get("move"):
        return f"revision move {d['move'].get('type')}({d['move'].get('args')})"
    return "(no recorded decision — check the ledger)"


def beyond_this_data(root: Node) -> list[dict]:
    """Every round's mechanisms the expansion agent named beyond what the data
    can separate, latest round first: `[{round, items}]`.

    Read from the round's recorded expansion decision (`expansion`); a round
    whose agent proposed nothing to buy writes no decision, so its final
    proposal (`expansion_diagnostics`) is read instead. A round that named
    none is left out."""
    from octomod.result import node as tree
    from octomod.workflow_modules.model import model_space as _ms

    out = []
    for k in tree.round_indices(root):
        rnd = tree.round_node(root, k)
        decided = (rnd / "expansion").get(None)
        if isinstance(decided, dict) and "beyond_this_data" in decided:
            items = _ms.beyond_this_data(decided)
        else:
            state = (rnd / "expansion_diagnostics").get(None)
            proposal = state.get("final_proposal") if isinstance(state, dict) else None
            items = _ms.beyond_this_data(proposal if isinstance(proposal, dict) else {})
        if items:
            out.append({"round": int(k), "items": items})
    return sorted(out, key=lambda b: -b["round"])


MODEL_ORIGIN_HEADING = "Where the model came from"
MODEL_ORIGIN_LEDE = (
    "Who proposed each reaction of the model each round selected: the person "
    "(a required reaction), the knowledge module's survey, a targeted search "
    "inside the run — each with the band its sources earned under the declared "
    "rule table — or, where no dossier entry describes it, the agent that wrote "
    "it: construction, the expansions, an expansion. The support floor decided "
    "what could be proposed; the criteria and the data decided what stayed."
)


def _support_rows(node: Node) -> dict[str, dict]:
    """{reaction id: {reactants, products}} of an annotated model, from its
    `reaction_support`; {} when it has none."""
    support = (node / "reaction_support").get(None)
    return {
        str(r.get("reaction_id")): r
        for r in (support or {}).get("reactions") or []
        if isinstance(r, dict) and r.get("reaction_id")
    }


def _same_sides(a: dict, b: dict) -> bool:
    return (set(a.get("reactants") or []), set(a.get("products") or [])) == (
        set(b.get("reactants") or []),
        set(b.get("products") or []),
    )


def _selected_model(root: Node, k: int, rep: dict) -> tuple[str, Node]:
    """(the model's name, its model node) of the model round `k` selected."""
    from octomod.result import node as tree

    rnd = tree.round_node(root, k)
    winner = (rep.get("discrimination") or {}).get("winner")
    if winner:
        return str(winner), tree.model_node(rnd, str(winner))
    return f"round {k} model", rnd / "model"


def _reaction_origin(row: dict, author: str) -> str:
    """Who proposed a model reaction: the proposer of the dossier entry it
    implements (its first carried direction a source backs), else `author`."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    for d in ("forward", "backward"):
        b = (row.get("directions") or {}).get(d)
        if b and b.get("entry_id") and b.get("label") != _rxe.INFERRED:
            return str(b.get("origin") or _rxe.ORIGIN_KNOWLEDGE)
    return author


def _reaction_band(row: dict) -> str:
    """The weakest band over the directions a reaction's law carries: the
    grade of the entry each implements, `none` where it implements none."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    bands = []
    for b in (row.get("directions") or {}).values():
        if b is None:
            continue
        g = _rxe.parse_band(b.get("grade")) if b.get("entry_id") else _rxe.NONE
        bands.append(g or _rxe.NONE)
    return max(bands, key=_rxe.band_rank) if bands else _rxe.NONE


def model_origin(root: Node, rounds: list[tuple[int, dict]], ledger: list) -> dict:
    """ "Where the model came from", per round and for the run, when the run
    builds on the knowledge module: the selected model's reactions counted by
    origin (human, knowledge, search, construction, expansions, expansion) and
    by band, the floor's history, every targeted search (who asked, its
    questions, what it admitted and what not), every axis and variation
    refused for the floor. {} for a run without the module's output."""
    from octomod.result import node as tree
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    fence = [r for r in ledger if r.get("event") == "grounding_fence"]
    built_on = any(
        (tree.round_node(root, k) / _rxe.DOSSIER_KEY).exists()
        for k in tree.round_indices(root)
    )
    if not built_on or (fence and fence[-1].get("skip")):
        return {}
    reports = dict(rounds)
    authors: dict[int, dict[str, str]] = {}
    per_round = []
    for k in tree.round_indices(root):
        rnd = tree.round_node(root, k)
        rep = reports.get(k)
        floors = [
            {"band": r.get("band"), "source": r.get("source"), "note": r.get("note")}
            for r in ledger
            if r.get("event") == "floor_set" and r.get("round") == k
        ]
        entry = {
            "round": k,
            "floor": (rnd / _rxe.FLOOR_KEY).get(None),
            "floor_history": floors,
        }
        if rep is not None:
            name, model = _selected_model(root, k, rep)
            rows = _support_rows(model)
            # what each reaction's author is, when no dossier entry backs it:
            # the base's reactions carry over, what a round adds is its own
            if (rnd / "base_model" / "reaction_support").exists():
                base, added_by, inherit = (
                    _support_rows(rnd / "base_model"),
                    _rxe.ORIGIN_EXPANSION,
                    None,
                )
            elif (
                k > 0
                and (rnd / "model" / "seed").exists()
                and (rnd / "space" / "axes").exists()
            ):
                base, added_by, inherit = (
                    _support_rows(rnd / "model"),
                    _rxe.ORIGIN_REVISION,
                    authors.get(k - 1) or {},
                )
            else:
                base, added_by, inherit = {}, _rxe.ORIGIN_CONSTRUCTION, None
            mine: dict[str, str] = {}
            for rid, row in rows.items():
                was = base.get(rid)
                if was is not None and _same_sides(was, row):
                    mine[rid] = (inherit or {}).get(rid, _rxe.ORIGIN_CONSTRUCTION)
                else:
                    mine[rid] = added_by if base else _rxe.ORIGIN_CONSTRUCTION
            authors[k] = mine
            by_origin = {o: 0 for o in _rxe.REACTION_ORIGINS}
            by_band: dict[str, int] = {}
            for rid, row in rows.items():
                o = _reaction_origin(row, mine[rid])
                by_origin[o] = by_origin.get(o, 0) + 1
                b = _reaction_band(row)
                by_band[b] = by_band.get(b, 0) + 1
            entry.update(
                model=name,
                n_reactions=len(rows),
                by_origin=by_origin,
                by_band={b: by_band[b] for b in _rxe.GRADE_BANDS if by_band.get(b)},
            )
        per_round.append(entry)
    searches = []
    refused = []
    for k in tree.round_indices(root):
        rnd = tree.round_node(root, k)
        group = rnd / _rxe.SEARCH_KEY
        for name in group.children() if group.exists() else []:
            rec = group.child(name).get(None)
            if not isinstance(rec, dict):
                continue
            adm = rec.get("admission") or {}
            searches.append(
                {
                    "round": k,
                    "n": rec.get("n", name),
                    "requested_by": rec.get("requested_by"),
                    "questions": [
                        str(q.get("question") or q.get("equation") or "")
                        for q in rec.get("questions") or []
                        if isinstance(q, dict)
                    ],
                    "floor": adm.get("floor"),
                    "admitted": list(adm.get("admitted") or []),
                    "not_admitted": list(adm.get("not_admitted") or []),
                    "failed": rec.get("failed"),
                }
            )
        for row in (rnd / _rxe.AXIS_REFUSED_KEY).get(None) or []:
            if isinstance(row, dict):
                refused.append({"round": k, "kind": "axis", **row})
    seen_var = set()
    for r in ledger:
        if r.get("event") != "variation_refused_floor":
            continue
        key = (r.get("round"), r.get("candidate"))
        if key in seen_var:
            continue
        seen_var.add(key)
        refused.append(
            {
                "round": r.get("round"),
                "kind": "variation",
                "candidate": r.get("candidate"),
                "floor": r.get("floor"),
                "line": str(r.get("note") or ""),
            }
        )
    return {"rounds": per_round, "searches": searches, "refused": refused}


def _model_origin_md(block: dict) -> list[str]:
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    if not block:
        return []
    L = [f"## {MODEL_ORIGIN_HEADING}", "", MODEL_ORIGIN_LEDE, ""]
    L += [
        "| round | model | reactions | by origin | by band | support floor |",
        "|---|---|---|---|---|---|",
    ]
    for r in block.get("rounds") or []:
        L.append(
            f"| {r['round']} | {r.get('model') or '—'} | {r.get('n_reactions', '—')} | "
            f"{_origin_text(r.get('by_origin'))} | {_band_counts(r.get('by_band'))} | "
            f"{_floor_history_text(r)} |"
        )
    L.append("")
    if block.get("searches"):
        L += ["**Targeted searches**", ""]
        for s in block["searches"]:
            L.append(
                f"- round {s['round']}, search {s['n']}, asked by "
                f"{s.get('requested_by')}: " + "; ".join(s.get("questions") or [])
            )
            L.append(
                "  - "
                + (
                    f"admitted at floor {_rxe.band_text(s.get('floor'))}: "
                    + ", ".join(s["admitted"])
                    if s.get("admitted")
                    else f"nothing admitted at floor {_rxe.band_text(s.get('floor'))}"
                )
            )
            for b in s.get("not_admitted") or []:
                L.append(
                    f"  - not admitted {b.get('id')} {b.get('equation')} — {b.get('why')}"
                )
        L.append("")
    if block.get("refused"):
        L += ["**Refused for the floor**", ""]
        for x in block["refused"]:
            L.append(f"- round {x['round']}: {x.get('line')}")
        L.append("")
    return L


def _origin_text(counts: dict | None) -> str:
    return ", ".join(f"{n} {o}" for o, n in (counts or {}).items() if n) or "—"


def _band_counts(counts: dict | None) -> str:
    return (
        ", ".join(f"{n} {b.replace('_', ' ')}" for b, n in (counts or {}).items() if n)
        or "—"
    )


def _floor_history_text(r: dict) -> str:
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    hist = r.get("floor_history") or []
    if hist:
        return " → ".join(
            f"{_rxe.band_text(h.get('band'))} ({h.get('source')})" for h in hist
        )
    cur = r.get("floor") or {}
    return (
        f"{_rxe.band_text(cur.get('band'))} ({cur.get('source')})"
        if cur.get("band")
        else "—"
    )


BEYOND_LEDE = (
    "Mechanisms the expansion agent names as acting in this system that the "
    "data cannot separate from the selected model, each with the experiment "
    "that would. They were not fitted and are not part of the answer; they are "
    "what the next experiment could decide."
)


def intent_evidence(item: dict) -> str:
    """The evidence behind one `answers_intent` verdict, as one line, or "".

    The interpretation schema names it `evidence`; an item that says it under
    another name (`reason`, `diagnosis`) is read the same way, so no verdict
    reaches the run page without the sentence that decided it.
    """
    for key in ("evidence", "reason", "diagnosis"):
        text = " ".join(str(item.get(key) or "").split())
        if text:
            return text
    return ""


def render_md(summary: dict) -> str:
    if summary.get("error"):
        return f"# Analysis report\n\n{summary['error']}\n"
    L = [
        f"# Analysis report — {summary['run']}",
        "",
        f"**Question.** {summary['question']}",
        "",
        f"*{summary['system']} · goal: {summary['inference_target']} · "
        f"{summary['n_rounds']} round(s) · outcome: `{summary['outcome']}`*",
        "",
    ]

    L += ["## The answer", ""]
    a = summary["answer"]
    L.append(
        f"**{a.get('selected_structure') or a['selected_model']}**, on the "
        f"basis of {a['basis']}."
    )
    if a.get("selected_structure") and a["selected_structure"] != a["selected_model"]:
        L.append("")
        L.append(
            f"<sub>Named `{a['selected_model']}` inside its own round, which is "
            f"how to find it in the record.</sub>"
        )
    if "decisive" in a:
        L.append("")
        L.append(f"- decisive: **{a['decisive']}**")
        L.append(f"- indistinguishable set: `{a['indistinguishable_set']}`")
    if a.get("read_this_as"):
        L += ["", f"> {a['read_this_as']}"]
    if a.get("held_out_prediction", {}).get("available"):
        h = a["held_out_prediction"]
        L += [
            "",
            f"- held-out prediction, worst group `{h['worst_group']}`: "
            f"nRMSE {h['worst_nrmse']}",
        ]
    L.append("")

    if summary["answers_intent"]:
        L += ["### Against the questions asked at the start", ""]
        for v in summary["answers_intent"]:
            if isinstance(v, dict):
                L.append(
                    f"- **{v.get('criterion', v.get('question', '?'))}** — "
                    f"{v.get('verdict', v.get('answer', ''))}"
                )
                # the reasoning behind the verdict, beneath it: a verdict
                # without its evidence cannot be checked from this page
                ev = intent_evidence(v)
                if ev:
                    L.append(f"  - evidence: {ev}")
            else:
                L.append(f"- {v}")
        L.append("")

    if summary.get("beyond_this_data"):
        L += ["## Beyond this data", "", BEYOND_LEDE, ""]
        for block in summary["beyond_this_data"]:
            L.append(f"**Named after round {block['round']}**")
            L.append("")
            for e in block["items"]:
                L.append(f"- **{e['mechanism']}**")
                if e.get("why_not_separable"):
                    L.append(f"  - not separable here: {e['why_not_separable']}")
                if e.get("experiment"):
                    L.append(f"  - the experiment that would: {e['experiment']}")
            L.append("")

    L += ["## Rounds", "", "| round | what changed | selected |", "|---|---|---|"]
    for r in summary["rounds"]:
        L.append(
            f"| {r['round']} | {r['what_changed']} | "
            f"{r.get('selected_structure') or r['selected']} |"
        )
    L.append("")

    L += _model_origin_md(summary.get("model_origin") or {})

    L += [
        "## Every model assessed",
        "",
        "Criterion values compare models WITHIN a round, not across rounds.",
        "",
        "| round | model | n par | −logL | ΔAIC | weight | |",
        "|---|---|---|---|---|---|---|",
    ]

    def f(v, d=2):
        return "—" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else v)

    for m in summary["models_assessed"]:
        L.append(
            f"| {m['round']} | {m.get('lineage') or m['model']} | "
            f"{f(m['n_estimated'])} | "
            f"{f(m['nllh'])} | {f(m['delta_aic'])} | {f(m['weight'], 4)} | "
            f"{'**selected**' if m['selected'] else ''} |"
        )
    L.append("")

    L += ["## Still open", ""]
    if summary["still_open"]:
        L += [f"- {s}" for s in summary["still_open"]]
        L += [
            "",
            "These are stated because they are true, not because the run "
            "failed. A limit declared is worth more than a limit hidden.",
        ]
    else:
        L.append(
            "Nothing recorded as unresolved: no open structural-misfit "
            "evidence, and the selection was decisive."
        )
    L.append("")

    topo = (summary.get("provenance") or {}).get("search_topology") or {}
    if topo.get("union_lattice_models"):
        frac = topo.get("visited_fraction")
        L += [
            "## What the search covered",
            "",
            f"{topo['topology']}. Over the {topo['n_axes_declared']} axis/axes "
            f"declared in this run the union space is "
            f"{topo['union_lattice_models']} models; the search visited "
            f"**{topo['visited']}**"
            + (f" ({frac:.0%})" if isinstance(frac, (int, float)) else "")
            + ". A corner never visited is not evidence against it — it was "
            "not tried.",
            "",
        ]
        outside = (
            topo.get("outside_status") or topo.get("models_outside_the_lattice") or []
        )
        if outside:
            L += [
                "Fitted outside that lattice (whole alternative models rather "
                "than axis combinations): " + ", ".join(f"`{m}`" for m in outside),
                "",
            ]

    gp = summary.get("gate_policy")
    if gp:
        L += [
            "## Gate policy",
            "",
            f"Profile **{gp['profile']}** (`{gp['sha']}`, from `{gp['source']}`). "
            f"{len(gp['answers'])} gate(s) answered by policy, "
            f"{summary['cost']['human_decisions']} by a human.",
            "",
        ]
        if gp["answers"]:
            L += [
                "| gate | round | answer | covered by | note |",
                "|---|---|---|---|---|",
            ]
            L += [
                f"| `{a['module']}` | {a['round']} | "
                f"{'yes' if a['approved'] else 'NO'} | {a['covered_by']} | "
                f"{a['note'] or '—'} |"
                for a in gp["answers"]
            ]
            L.append("")
        if gp.get("verdict_signed_by"):
            L += [
                f"The verdict was signed by **{gp['verdict_signed_by']}**. A "
                f"policy signature is not a human's: it names the file and its "
                f"hash, so the claim can be traced to the configuration that "
                f"made it.",
                "",
            ]

    c = summary["cost"]
    L += [
        "## What it cost",
        "",
        f"{c['agent_calls']} agent calls · ${c['usd']} · "
        f"{c['human_decisions']} human decisions · "
        f"{c.get('module_redrafts', 0)} module redraft(s), "
        f"{c.get('contract_retries', 0)} contract retry(ies), "
        f"{c.get('redraft_grants', 0)} extra attempt(s) granted "
        f"(attempts per call {c.get('attempts_per_call', 1.0)})"
        + (
            f" · {c['policy_decisions']} gate(s) answered by policy"
            if c.get("policy_decisions")
            else ""
        )
        + (
            f" · {c['auto_decisions']} auto-approved (test mode)"
            if c.get("auto_decisions")
            else ""
        )
        + ".",
        "",
        f"*{summary['provenance']['note']}*",
        "",
        "## What this run was started with",
        "",
        _inputs_md(summary),
        "",
        "## How complete the record is",
        "",
        (summary.get("record_checks") or {}).get("line")
        or "no record checks ran (a record from before they existed, or checks turned off)",
        *[f"- {line}" for line in _record_checks_lines(summary)],
        "",
        "## What code produced this",
        "",
        _prov_md(summary),
        "",
    ]
    return "\n".join(L)


def _record_checks(root: Node) -> dict:
    from octomod.result import completeness

    s = completeness.summary(root)
    return {
        "line": completeness.summary_line(root),
        "incomplete": [
            {k: e.get(k) for k in ("checkpoint", "round", "candidate", "missing")}
            for e in s["incomplete"]
        ],
        "errors": [e.get("error") for e in s["errors"]],
    }


def _record_checks_lines(summary: dict) -> list[str]:
    """Each missing part, as `checkpoint · key — what`."""
    rc = summary.get("record_checks") or {}
    out = []
    for e in rc.get("incomplete") or []:
        at = e["checkpoint"] + (
            f", round {e['round']}" if e.get("round") is not None else ""
        )
        at += f", {e['candidate']}" if e.get("candidate") else ""
        out += [f"{at} · {m['key']} — {m['what']}" for m in e.get("missing") or []]
    return out + [f"a check failed: {err}" for err in rc.get("errors") or []]


def _inputs_md(summary: dict) -> str:
    """The terminal-readable half of the Inputs block."""
    i = summary.get("inputs") or {}
    if not i:
        return "(not recorded)"
    lines = [f"source: {i.get('source') or '(not recorded)'}"]
    if i.get("project"):
        lines.append(f"project: {i['project']}")
    if i.get("started_from"):
        lines.append(f"started from run: {i['started_from']}")
    if i.get("in_place"):
        lines.append(
            "this run predates the record carrying its own inputs, so it "
            "read them in place from the path above"
        )
    else:
        lines.append(f"input sha: {i.get('sha') or '(none)'}")
        lines += [f"  - input/{f}" for f in i.get("files") or []]
    return "\n".join(lines)


def _prov_md(summary: dict) -> str:
    """The code identity for the terminal-readable companion."""
    from octomod.orchestration import provenance as _pv

    code = (summary.get("provenance") or {}).get("code") or {}
    lines = [
        _pv.one_line(code),
        "",
        _pv.versions_line(code),
        "",
        _pv.agents_line(code, summary.get("models_used")),
    ]
    if code.get("uv_lock_sha256"):
        lines.append(f"uv.lock {code['uv_lock_sha256']}")
    return "\n".join(lines)


def _aic_figure(summary: dict):
    """One figure that earns its place: how far every model sat from the best
    one, grouped by round. A reader should see the shape of the evidence — one
    model far ahead, or four in a heap — before reading any number."""

    def build(plt):
        rows = [m for m in summary["models_assessed"] if m.get("delta_aic") is not None]
        if not rows:
            # single-model run: no within-round comparison exists, but the
            # round-over-round objective IS comparable (same data, successive
            # models), and it is the only progression the reader has.
            prog = [m for m in summary["models_assessed"] if m.get("nllh") is not None]
            if len(prog) < 2:
                return None
            fig, ax = plt.subplots(figsize=(6.4, 2.8))
            xs = [m["round"] for m in prog]
            ys = [m["nllh"] for m in prog]
            ax.plot(xs, ys, "-o", color="#2f6f68", lw=1.6, ms=5)
            for x, y in zip(xs, ys, strict=False):
                ax.annotate(
                    f"{y:.2f}",
                    (x, y),
                    textcoords="offset points",
                    xytext=(0, 7),
                    ha="center",
                    fontsize=8,
                    color="#2f6f68",
                )
            ax.set_xticks(xs)
            ax.set_xlabel("round")
            ax.set_ylabel("best \u2212logL")
            ax.spines[["top", "right"]].set_visible(False)
            fig.tight_layout()
            return fig
        fig, ax = plt.subplots(figsize=(7.2, max(1.6, 0.42 * len(rows) + 1.0)))
        rows = sorted(rows, key=lambda m: (m["round"], m["delta_aic"]))
        labels = [f"r{m['round']}  {m['model']}" for m in rows]
        vals = [m["delta_aic"] for m in rows]
        sel = [m["selected"] for m in rows]
        y = range(len(rows))
        ax.barh(
            list(y),
            vals,
            color=["#2f6f68" if s else "#c9d3d1" for s in sel],
            edgecolor="none",
            height=0.62,
        )
        ax.set_yticks(list(y))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.set_xlabel("ΔAIC from the best model in that round (0 = selected)")
        ax.axvline(2.0, color="#9a6b1f", lw=1, ls="--")
        ax.text(
            2.0,
            -0.7,
            " ΔAIC 2 — below this the data do not separate them",
            fontsize=7.5,
            color="#9a6b1f",
            va="bottom",
        )
        for i, (v, s) in enumerate(zip(vals, sel, strict=False)):
            ax.text(
                v,
                i,
                f"  {v:.2f}",
                va="center",
                fontsize=7.5,
                color="#2f6f68" if s else "#6b7674",
            )
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        return fig

    return build


# The verdict section's heading, named once, so a check that something comes
# BEFORE the verdict is not pinned to a caption.
VERDICT_HEADING = "What won"


def axes_of(root: Node) -> dict[str, dict]:
    """{axis_id: the axis as declared} over every round of the run.

    The axis's own `question` field is the one plain-language description of a
    mechanism anywhere in the run, written by the agent that proposed it; it
    says what the winning model actually CLAIMS.
    """
    from octomod.result.access import as_artifact, record_for

    rr = record_for(root)
    out: dict[str, dict] = {}
    for k in rr.round_indices:
        space = rr.round(k).space
        if space is None:
            continue
        # `space/declared` first, then `space/axes` — the order they were
        # always read in, so the earliest declaration still wins
        for ax in list(space.declared) + [as_artifact(a) for a in space.axes]:
            if isinstance(ax, dict) and ax.get("id"):
                out.setdefault(str(ax["id"]), ax)
    return out


def axes_carried(model_id: str, known: dict) -> list[str]:
    """Which declared axes this candidate carries.

    A search-path candidate id IS its axis combination (`a+b`), which is why
    one picture of the candidates can be a grid rather than eight network
    diagrams: the candidates differ BY axes, so the axes are the difference.
    Returns [] for a candidate named some other way — the discrimination path
    hands over finished candidates and has no lattice.
    """
    if not model_id or model_id == "base":
        return []
    parts = [p.strip() for p in str(model_id).split("+") if p.strip()]
    if all(p in known for p in parts):
        return parts
    # a LINEAGE names its root first — a discrimination round's candidate, not
    # an axis — then the axes added on top (`root + axis_a + axis_b`); those
    # added axes are what it carries
    if len(parts) > 1 and all(p in known for p in parts[1:]):
        return parts[1:]
    return []


def _what_won(summary: dict, root: Node, esc, note, table) -> list[str]:
    """WHAT WON, in words before ids: what the model claims, what it beat,
    and by how much."""
    a = summary["answer"]
    winner = a.get("selected_structure") or a["selected_model"]
    known = axes_of(root)
    # the axes the FINAL structure carries: resolved through the rounds, not
    # read off a round-local id (which after an expansion names only the last
    # round's additions) nor off the lineage STRING
    final_round = max((m["round"] for m in summary["models_assessed"]), default=0)
    carried = [
        ax for ax in lineage_axes(root, final_round, a["selected_model"]) if ax in known
    ]
    base_name = next(
        (
            ax
            for ax in lineage_axes(root, final_round, a["selected_model"])
            if ax not in known
        ),
        None,
    )
    out = [f"<h2>{VERDICT_HEADING}</h2>"]

    if carried or known:
        # The axes ARE the questions the run set out to answer, so the verdict
        # reads as an answer to each of them, the answer first.
        yes = [ax for ax in known if ax in carried]
        no = [ax for ax in known if ax not in carried]
        bullets = [
            f"<li><strong>Yes</strong> — "
            f'{esc(str(known[ax].get("question") or ax))} '
            f"<code>{esc(ax)}</code></li>"
            for ax in yes
        ] + [
            f"<li><strong>No</strong>, on this evidence — "
            f'{esc(str(known[ax].get("question") or ax))} '
            f"<code>{esc(ax)}</code></li>"
            for ax in no
        ]
        out.append(
            '<p class="lede">The selected structure is '
            + (f"<code>{esc(base_name)}</code>" if base_name else "the base model")
            + " plus "
            + (", ".join(f"<code>{esc(ax)}</code>" for ax in yes) or "nothing")
            + ". Against the questions the space was built to settle:</p>"
        )
        out.append("<ul>" + "".join(bullets) + "</ul>")
    elif a.get("basis") == "single-model calibration":
        # No axes were declared and nothing was compared, so there is no
        # candidate id: `build`'s "round k model" in `selected_model` is a
        # placeholder, not a name to render as the verdict.
        out.append(
            '<p class="lede">One model was calibrated and assessed. No '
            "alternative structure was proposed or fitted, so nothing was "
            "chosen between — what follows is how well that one model did, "
            "not a comparison.</p>"
        )
    else:
        out.append(f'<p class="lede">Selected: <code>{esc(winner)}</code>.</p>')

    # criterion values compare models WITHIN a round: the margin, the weight
    # and "chosen over" are the FINAL round's, not a pool over every round
    final_rows = [m for m in summary["models_assessed"] if m["round"] == final_round]
    beaten = [m for m in final_rows if not m["selected"]]
    margin = min(
        (m["delta_aic"] for m in beaten if m["delta_aic"] is not None), default=None
    )
    sel = next((m for m in final_rows if m["selected"]), {})
    n_all = sum(1 for m in summary["models_assessed"] if not m["selected"])
    rows = [
        [
            "chosen over",
            f"{len(beaten)} other structure(s) in the final round"
            + (f" ({n_all} fitted across all rounds)" if n_all != len(beaten) else ""),
        ]
    ]
    if margin is not None:
        rows.append(
            [
                "nearest rival",
                f"ΔAIC {margin:.2f} — AIC counts fit and parameters together, so a "
                f"rival within about 2 units is not distinguishable by this "
                f"evidence",
            ]
        )
    if sel.get("weight") is not None:
        rows.append(
            [
                "its share of the evidence",
                f"{sel['weight']:.3f} — the Akaike weight, which is that model's "
                f"share of the total evidence ACROSS THE SET THAT WAS FITTED. It "
                f"says nothing about a structure nobody proposed.",
            ]
        )
    rows.append(
        [
            "distinguishable?",
            (
                "yes — one structure stands alone at this evidence"
                if a.get("decisive")
                else "no — these structures are not separated by this evidence: "
                + ", ".join(
                    f"<code>{esc(x)}</code>"
                    for x in a.get("indistinguishable_set") or []
                )
            ),
        ]
    )
    hp = a.get("held_out_prediction") or {}
    if hp.get("available"):
        rows.append(
            [
                "predicted, not fitted",
                f"worst held-out group <code>{esc(hp['worst_group'])}</code> at "
                f"nRMSE {hp['worst_nrmse']} — the error on data the fit never saw, "
                f"as a fraction of that series' own range",
            ]
        )
    out.append(table(["", ""], rows))
    if a.get("read_this_as"):
        out.append(note(a["read_this_as"]))
    return out


def _why_it_won(summary: dict, root: Node, esc, note, table) -> list[str]:
    """WHY: which measurements paid for the win.

    The ΔAIC split over (observable, condition) in the round's attribution is
    the only place the run says what the evidence actually was, rather than
    that there was some.
    """
    winner = (
        summary["answer"].get("selected_structure")
        or summary["answer"]["selected_model"]
    )
    from octomod.result.access import record_for, report_dict

    rr = record_for(root)
    attr = {}
    for k in reversed(rr.round_indices):
        rep = report_dict(rr.round(k))
        if rep:
            attr = rep.get("attribution") or {}
            if attr.get("available"):
                break
    if not attr.get("available"):
        return []
    rivals = [
        r for r in (attr.get("rivals") or []) if r.get("available") and r.get("top")
    ]
    if not rivals:
        return []
    # The nearest DISTINGUISHED rival, not the nearest rival: on a lattice the
    # nearest is usually a model differing by one parameter the fit pins at its
    # bound, which the evidence does not separate, so its shares are noise.
    band = 2.0
    # ONE source for the margin, and therefore for the ORDERING too: the
    # selection table, not the attribution's own re-evaluated ΔAIC.
    table_delta = {}
    for m in summary["models_assessed"]:
        if m["delta_aic"] is None:
            continue
        for key in (m.get("model"), m.get("lineage")):
            if key:
                table_delta[str(key)] = m["delta_aic"]

    def margin_of(r: dict) -> float:
        return abs(table_delta.get(str(r.get("rival")), r.get("delta_aic") or 0))

    # And a rival that is the winner PLUS extra axes can only lose by the
    # parameter penalty: the fit is free to set the extras to nothing and
    # usually does, so comparing against it explains arithmetic rather than
    # evidence. Prefer a rival that LACKS one of the winner's axes; the band
    # rule is the fallback when every rival is a superset.
    known_all = axes_of(root)
    win_axes = set(axes_carried(winner, known_all))

    def is_superset(r: dict) -> bool:
        got = set(axes_carried(str(r.get("rival")), known_all))
        return bool(win_axes) and win_axes <= got

    structural = sorted(
        (r for r in rivals if margin_of(r) > band and not is_superset(r)),
        key=margin_of,
    )
    distinguished = structural or sorted(
        (r for r in rivals if margin_of(r) > band), key=margin_of
    )
    if not distinguished:
        return [
            "<h2>Why it won</h2>",
            note(
                f"Every structure that was fitted sits within about {band:g} "
                f"AIC units of the winner, so this evidence does not separate "
                f"them and there is no difference to attribute. That is itself "
                f"the finding: the run narrowed the space and stopped."
            ),
        ]
    nearest = distinguished[0]
    # ONE number for the margin, taken from the selection table the reader has
    # already seen; the attribution's own ΔAIC differs in the second decimal.
    rid = str(nearest["rival"])
    margin = margin_of(nearest)
    out = ["<h2>Why it won</h2>"]
    paid = nearest["top"][:3]
    out.append(
        f'<p class="lede">Against the nearest structure this evidence does '
        f"separate it from — <code>{esc(rid)}</code>, ΔAIC {margin:.2f} — the "
        f"difference is not spread evenly over the data. It is paid for by "
        f"{len(paid)} measurement group(s):</p>"
    )
    out.append(
        table(
            ["measurement", "share of the difference", "points"],
            [
                [
                    f"<code>{esc(str(g['group']))}</code>",
                    f"{g.get('share', 0) * 100:.0f}%",
                    str(g.get("n", "—")),
                ]
                for g in paid
            ],
        )
    )
    out.append(
        note(
            "Read as: these are the measurements the losing structure could "
            "not reproduce. A verdict paid for by one group is a narrower "
            "claim than one paid for across the design — and either way it "
            "names where to look, and where a new experiment would settle it."
        )
    )
    return out


def _the_candidates(summary: dict, root: Node, esc, figure, table) -> list[str]:
    """ONE PICTURE of the candidates: which axes each carries, ordered by ΔAIC.

    Not a network diff — the candidates are mostly the same graph by
    construction. A grid of on/off cells reads at a glance and its columns ARE
    the questions the run set out to answer.

    On the discrimination path the candidates are not axis combinations, so the
    grid has no columns and the bar chart of distances is the picture instead.
    """
    known = axes_of(root)
    models = [m for m in summary["models_assessed"] if m["delta_aic"] is not None]
    grid = [(m, axes_carried(m.get("model") or "", known)) for m in models]
    usable = [g for g in grid if g[1]] and len(known) >= 2
    out = ["<h2>The candidates</h2>"]
    if not usable:
        out.append(
            figure(
                _aic_figure(summary),
                caption="Distance from the best model in the same round; "
                "criterion values compare WITHIN a round, never across.",
                fallback="no criterion values were recorded for this run",
            )
        )
        return out

    order = sorted(grid, key=lambda g: g[0]["delta_aic"])
    axis_ids = [a for a in known if any(a in c for _m, c in order)]
    worst = max((m["delta_aic"] for m, _ in order), default=1.0) or 1.0
    rows = []
    for m, carried in order:
        cells = [
            (
                '<span class="axon">on</span>'
                if ax in carried
                else '<span class="axoff">·</span>'
            )
            for ax in axis_ids
        ]
        frac = 1.0 - min(m["delta_aic"] / worst, 1.0)
        bar = (
            f'<span class="dbar"><i style="width:{max(frac * 100, 1):.0f}%"></i></span>'
            f' {m["delta_aic"]:.2f}'
        )
        rows.append(
            [esc(m.get("lineage") or m["model"])]
            + cells
            + [
                bar,
                f"{(m.get('weight') or 0):.3f}",
                "<strong>selected</strong>" if m["selected"] else "",
            ]
        )
    out.append(
        table(
            ["structure"] + list(axis_ids) + ["ΔAIC (shorter is better)", "weight", ""],
            rows,
            cls="axgrid",
        )
    )
    out.append(
        '<div class="axlegend">'
        + " · ".join(
            f"<code>{esc(a)}</code> — {esc(str(known[a].get('question') or '')[:88])}"
            for a in axis_ids
        )
        + "</div>"
    )
    return out


def render_html(summary: dict) -> str:
    from octomod.reporting import esc, figure, note, page, table
    from octomod.reporting.html import stated
    from octomod.workflow_modules.model import declared_constants as dc

    if summary.get("error"):
        return page(
            "Analysis report", f"<h1>Analysis report</h1>{note(summary['error'])}"
        )

    S = [f"<h1>Analysis report — {esc(summary['run'])}</h1>"]
    S.append(f"<p class=\"lede\">{esc(summary['question'])}</p>")
    S.append(
        '<p class="meta">'
        f"{esc(summary['system'])} &middot; goal "
        f"<code>{esc(summary['inference_target'])}</code> &middot; "
        f"{summary['n_rounds']} round(s) &middot; outcome "
        f"<code>{esc(summary['outcome'])}</code></p>"
    )

    # Before the answer, not after it: a run can finish ACCEPTED with a model
    # that breaks a declared conservation (a violated note does not open the
    # misfit flag on its own), so the run document says so above its conclusion.
    S.append(
        stated(
            "The selected model contradicts the experiment's own note",
            dc.verdict_prose(summary.get("declared_constants") or {}),
        )
    )

    # The argument first: what was asked (the lede above), what won, WHY, and
    # what is still open — then the picture, then the loop, then the evidence.
    root = _root_of(summary.get("record") or summary.get("run_dir"))
    if root is not None:
        S += _what_won(summary, root, esc, note, table)
        S += _why_it_won(summary, root, esc, note, table)

    S.append("<h2>Still open</h2>")
    if summary["still_open"]:
        S.append(
            "<ul>"
            + "".join(f"<li>{esc(s)}</li>" for s in summary["still_open"])
            + "</ul>"
        )
        S.append(
            note(
                "These are stated because they are true, not because the "
                "run failed. A limit declared is worth more than a limit "
                "hidden."
            )
        )
    else:
        S.append(
            "<p>Nothing recorded as unresolved: no open structural-misfit "
            "evidence, and the selection was decisive.</p>"
        )

    if root is not None:
        S += _the_candidates(summary, root, esc, figure, table)

    S.append("<h2>How the analysis got there</h2>")
    S.append(
        table(
            ["round", "what changed, and why", "selected"],
            [
                [
                    str(r["round"]),
                    esc(r["what_changed"]),
                    f"<code>{esc(r.get('selected_structure') or r['selected'])}</code>",
                ]
                for r in summary["rounds"]
            ],
        )
    )
    if summary["answers_intent"]:
        from octomod.reporting.budget import INTENT_EVIDENCE_CHARS, clip_chars, fold

        S.append("<h3>Against the questions asked at the start</h3><ul>")
        for v in summary["answers_intent"]:
            if isinstance(v, dict):
                ev = intent_evidence(v)
                shown, cut = clip_chars(ev, INTENT_EVIDENCE_CHARS)
                S.append(
                    f"<li><strong>{esc(v.get('criterion', v.get('question', '?')))}"
                    f"</strong> — {esc(v.get('verdict', v.get('answer', '')))}"
                    + (
                        f'<br><span class="note">{esc(shown)}</span>'
                        + (
                            fold("the evidence in full", f"<p>{esc(ev)}</p>")
                            if cut
                            else ""
                        )
                        if ev
                        else ""
                    )
                    + "</li>"
                )
            else:
                S.append(f"<li>{esc(v)}</li>")
        S.append("</ul>")

    S += _model_origin_html(summary.get("model_origin") or {}, esc, note, table)

    if summary.get("beyond_this_data"):
        S.append("<h2>Beyond this data</h2>")
        S.append(f"<p>{esc(BEYOND_LEDE)}</p>")
        for block in summary["beyond_this_data"]:
            S.append(f"<h3>Named after round {int(block['round'])}</h3><ul>")
            for e in block["items"]:
                S.append(
                    f"<li><strong>{esc(e['mechanism'])}</strong>"
                    + (
                        f"<br>not separable here: {esc(e['why_not_separable'])}"
                        if e.get("why_not_separable")
                        else ""
                    )
                    + (
                        f"<br>the experiment that would: {esc(e['experiment'])}"
                        if e.get("experiment")
                        else ""
                    )
                    + "</li>"
                )
            S.append("</ul>")

    # The per-round reports are the EVIDENCE and the audit trail, linked here
    # rather than being the entry point.
    # The rendered reports are real files beside this page (both under
    # `runs/<id>_reports/`), so a relative link reaches them; the decision
    # record is text in the run record, named by the command that shows it.
    if root is not None:
        from octomod.result import node as tree

        reports = root.store.reports_dir
        links = []
        for k in tree.round_indices(root):
            name = f"round_{k}"
            here = []
            for label, rel in (
                ("the round report — fits, gates, uncertainty", "report/report.html"),
                (
                    "the model as built — assumptions and evidence",
                    "report/model_report.html",
                ),
            ):
                if (reports / name / rel).exists():
                    here.append(f'<li><a href="{name}/{rel}">{label}</a></li>')
            decisions = tree.round_node(root, k) / "decisions_md"
            if decisions.exists():
                here.append(
                    "<li>who decided what, and why — "
                    f"<code>./run.sh show --run-id {esc(root.store.run_id)} "
                    f"{esc(decisions.key)}</code></li>"
                )
            if here:
                links.append(
                    f"<p><strong>{esc(name.replace('_', ' '))}</strong></p>"
                    f"<ul>{''.join(here)}</ul>"
                )
        if links:
            S.append("<h2>The evidence behind this page</h2>")
            S.append(
                note(
                    "Everything above is read from these; nothing on this page "
                    "is an agent's summary of them. Open one when you want to "
                    "check a number, not to find out what happened."
                )
            )
            S.append("".join(links))

    gp = summary.get("gate_policy")
    if gp:
        S.append("<h2>Gate policy</h2>")
        S.append(
            f"<p>Profile <b>{gp['profile']}</b> (<code>{gp['sha']}</code>, from "
            f"<code>{gp['source']}</code>). {len(gp['answers'])} gate(s) answered "
            f"by policy, {summary['cost']['human_decisions']} by a human.</p>"
        )
        if gp["answers"]:
            S.append(
                table(
                    ["gate", "round", "answer", "covered by", "note"],
                    [
                        [
                            str(a["module"]),
                            str(a["round"]),
                            "yes" if a["approved"] else "NO",
                            str(a["covered_by"]),
                            str(a["note"] or "—"),
                        ]
                        for a in gp["answers"]
                    ],
                )
            )
        if gp.get("verdict_signed_by"):
            S.append(
                note(
                    f"The verdict was signed by {gp['verdict_signed_by']}. A "
                    f"policy signature is not a human's: it names the file and "
                    f"its hash, so the claim can be traced to the "
                    f"configuration that made it."
                )
            )

    c = summary["cost"]
    S.append("<h2>What it cost</h2>")
    S.append(
        table(
            [
                "agent calls",
                "USD",
                "human decisions",
                "policy decisions",
                "module redrafts",
                "contract retries",
                "extra attempts granted",
                "attempts per call",
            ],
            [
                [
                    str(c["agent_calls"]),
                    f"${c['usd']}",
                    str(c["human_decisions"]),
                    str(c.get("policy_decisions", 0)),
                    str(c.get("module_redrafts", 0)),
                    str(c.get("contract_retries", 0)),
                    str(c.get("redraft_grants", 0)),
                    str(c.get("attempts_per_call", 1.0)),
                ]
            ],
        )
    )
    S.append(note(summary["provenance"]["note"]))

    # What the run was started with, beside what code produced it — both
    # are provenance, and a reader who wants to repeat a run needs both.
    S += _inputs_html(summary, esc, note, table)

    # whether each finished step left what a reader of the record needs
    rc = summary.get("record_checks") or {}
    S.append("<h2>How complete the record is</h2>")
    missing = _record_checks_lines(summary)
    if missing:
        S.append(stated(rc.get("line") or "record checks found gaps", missing))
    else:
        S.append(
            note(
                rc.get("line")
                or "no record checks ran (a record from before they existed, or checks turned off)."
            )
        )

    # The code identity, at the foot of the run document, where a reader
    # checking whether a number can be reproduced will look. A dirty tree is
    # flagged rather than mentioned — development runs are dirty by nature and
    # that is fine; an unrecorded dirty tree is not.
    from octomod.orchestration import provenance as _pv

    _code = (summary.get("provenance") or {}).get("code") or {}
    _dirty = (_code.get("git") or {}).get("dirty")
    S.append("<h2>What code produced this</h2>")
    S.append(
        stated(
            "This run is not reproducible from a commit alone", [_pv.one_line(_code)]
        )
        if _dirty
        else f"<p>{esc(_pv.one_line(_code))}</p>"
    )
    S.append(f'<p class="meta">{esc(_pv.versions_line(_code))}</p>')
    S.append(
        f'<p class="meta">{esc(_pv.agents_line(_code, summary.get("models_used")))}</p>'
    )
    if _code.get("uv_lock_sha256"):
        S.append(
            f'<p class="meta">uv.lock <code>{esc(str(_code["uv_lock_sha256"]))}</code>'
            f" — the digest of the whole resolved environment</p>"
        )
    return page(f"Analysis — {summary['run']}", "\n".join(S))


def _model_origin_html(block: dict, esc, note, table) -> list[str]:
    """The "Where the model came from" block of the run page."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    if not block:
        return []
    S = [f"<h2>{esc(MODEL_ORIGIN_HEADING)}</h2>", f"<p>{esc(MODEL_ORIGIN_LEDE)}</p>"]
    S.append(
        table(
            ["round", "selected model", "reactions", "by origin", "by band", "floor"],
            [
                [
                    str(r["round"]),
                    f"<code>{esc(str(r.get('model') or '—'))}</code>",
                    esc(str(r.get("n_reactions", "—"))),
                    esc(_origin_text(r.get("by_origin"))),
                    esc(_band_counts(r.get("by_band"))),
                    esc(_floor_history_text(r)),
                ]
                for r in block.get("rounds") or []
            ],
        )
    )
    if block.get("searches"):
        S.append("<h3>Targeted searches</h3>")
        S.append(
            table(
                [
                    "round",
                    "search",
                    "asked by",
                    "questions",
                    "admitted",
                    "not admitted",
                ],
                [
                    [
                        str(s["round"]),
                        esc(str(s["n"])),
                        esc(str(s.get("requested_by"))),
                        esc("; ".join(s.get("questions") or [])),
                        esc(
                            (
                                f"at {_rxe.band_text(s.get('floor'))}: "
                                + ", ".join(s["admitted"])
                            )
                            if s.get("admitted")
                            else f"nothing at {_rxe.band_text(s.get('floor'))}"
                        ),
                        esc(
                            "; ".join(
                                f"{b.get('id')} {b.get('equation')} ({b.get('why')})"
                                for b in s.get("not_admitted") or []
                            )
                            or "—"
                        ),
                    ]
                    for s in block["searches"]
                ],
            )
        )
    if block.get("refused"):
        S.append("<h3>Refused for the floor</h3>")
        S.append(
            "<ul>"
            + "".join(
                f"<li>round {esc(str(x['round']))}: {esc(str(x.get('line')))}</li>"
                for x in block["refused"]
            )
            + "</ul>"
        )
        S.append(
            note(
                "A refused axis or variation was never fitted: the floor decides "
                "what may be proposed, and a lower floor or a search that raises "
                "the support admits it in a later round."
            )
        )
    return S


def _inputs_html(summary: dict, esc, note, table) -> list[str]:
    i = summary.get("inputs") or {}
    S = ["<h2>What this run was started with</h2>"]
    if not i:
        return S + [note("no input record for this run.")]
    rows = [["source", esc(str(i.get("source") or "(not recorded)"))]]
    if i.get("project"):
        rows.append(["project", f"<code>{esc(str(i['project']))}</code>"])
    if i.get("started_from"):
        rows.append(
            [
                "started from",
                f"<code>{esc(str(i['started_from']))}</code> — its "
                f"<code>input</code> was copied and edited",
            ]
        )
    if not i.get("in_place"):
        rows.append(["input sha", f"<code>{esc(str(i.get('sha') or '—'))}</code>"])
    S.append(table(["", ""], rows))
    if i.get("in_place"):
        S.append(
            note(
                "This run started before the record carried its own inputs, "
                "so it read them in place from the path above rather than "
                "from a snapshot of its own."
            )
        )
        return S
    files = i.get("files") or []
    if files:
        # record keys, not links: the snapshot lives in the run record, and
        # `show` prints one of them
        S.append(
            '<ul class="files">'
            + "".join(f"<li><code>input/{esc(f)}</code></li>" for f in files)
            + "</ul>"
        )
    if i.get("hashed") and len(files) != i["hashed"]:
        S.append(
            note(
                f"{len(files)} file(s) here, {i['hashed']} of them hashed into "
                f"the input sha. A data generator is copied because it is part "
                f"of what the run was started with, and left out of the sha "
                f"because the run never reads it — editing one must not fail a "
                f"resume it could not have affected."
            )
        )
    S.append(
        note(
            "These files are IN this run's record. The engine copied them "
            "there before the first module and read nothing else for the rest "
            "of the run, so what is above is what produced what is below — "
            "whatever has happened since to the case they came from."
        )
    )
    return S


def _root_of(text: str | None) -> Node | None:
    """The root node of the run record a summary names as text: the record
    file (`runs/<id>.h5`), or — for a summary from a legacy run directory —
    the directory `runs/<id>`, whose record is `runs/<id>.h5`. None when the
    summary names none."""
    if not text:
        return None
    from octomod.result.access import store_of

    return Node(store_of(Path(text)))


def write(root: Node) -> Path:
    """Build the summary for the run record `root`, keep it in the record at
    `analysis`, and render ANALYSIS.md and ANALYSIS.html as REAL files in the
    run's reports directory. Returns the HTML's path."""
    with root.store.reading():
        summary = build(root)
    (root / "analysis").put(summary)
    reports = root.store.reports_dir
    reports.mkdir(parents=True, exist_ok=True)
    # markdown stays as the terminal-readable companion; the HTML is the
    # document, in the same shell as the per-round reports
    (reports / "ANALYSIS.md").write_text(render_md(summary))
    out = reports / "ANALYSIS.html"
    try:
        with root.store.reading():
            html_text = render_html(summary)
    except Exception as e:  # a summary must never fail a finished run
        html_text = f"<pre>analysis report failed to render: {e}</pre>"
    out.write_text(html_text)
    return out
