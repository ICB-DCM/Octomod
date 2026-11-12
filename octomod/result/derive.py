"""What a reader of the record needs that no module writes on its own.

The engine writes each artifact into the record as it produces it;
several fields of the typed record are not artifacts but READINGS of others —
an agent call's ledger rows and cost, a slot's producer (from its marker), the
problem's size, the approved start count, a candidate's label and whether it
was dropped, the module a gate belongs to, a decision's mode. No module writes
them, and without them `RunResult.failures()` would see no redraft and no
dropped candidate, so `derive` fills them from the record itself, on every
load, and never overwrites a value a module did write.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from octomod.orchestration.interaction import human_redraft
from octomod.result.model import RunResult
from octomod.result.records import DecisionRecord, LedgerEvent

_PRODUCERS = {
    "engine",
    "human",
    "policy",
    "user-supplied",
    "seeded-from-previous-round",
    "unknown",
}


def _producer(s: Any) -> str | None:
    s = str(s or "")
    if s in _PRODUCERS or s.startswith("agent:"):
        return s
    return None


def module_of_gates(rows: list[dict]) -> dict[tuple, str]:
    """(round, gate id) → the module that ran it, from the ledger's own `gate`
    rows — what the run did, not what a registry says a gate belongs to."""
    out: dict[tuple, str] = {}
    for r in rows:
        if r.get("event") == "gate" and r.get("gate_id") and r.get("module"):
            out.setdefault((r.get("round"), r["gate_id"]), str(r["module"]))
    return out


def _event(row: dict) -> LedgerEvent | None:
    try:
        return LedgerEvent.model_validate(row)
    except ValidationError:
        return None


def _unset(obj, name: str) -> bool:
    return name not in obj.model_fields_set


def _set(obj, name: str, value: Any) -> None:
    """Fill a field the module did not write; a written value stands."""
    if value is None or not _unset(obj, name):
        return
    setattr(obj, name, value)


def derive(rr: RunResult) -> RunResult:
    rows = [e.model_dump(exclude_unset=True, exclude={"elided"}) for e in rr.ledger]
    by_round: dict[int, list[dict]] = {}
    for r in rows:
        k = r.get("round")
        by_round.setdefault(k if isinstance(k, int) else 0, []).append(r)
    _run(rr, rows)
    module_of = module_of_gates(rows)
    for k in rr.round_indices:
        _round(rr, k, by_round.get(k, []), module_of)
    return rr


def _run(rr: RunResult, rows: list[dict]) -> None:
    starts = [r for r in rows if r.get("event") == "run_start"]
    if starts:
        _set(rr.run, "started_at", starts[0].get("ts"))
        _set(rr.run, "n_invocations", len(starts))
    # the time account. The engine writes `timing` at every pause and
    # at run end; a record cut short before that (a killed process) still
    # gets the account its ledger supports — with the open session ending at
    # its last row, which is the honest end of what is known.
    if starts:
        from octomod.orchestration import timing as _timing
        from octomod.result.model import TimingRecord

        try:
            stored = (
                rr.timing.model_dump(exclude_none=True)
                if rr.timing is not None
                else None
            )
            # absent, or behind the ledger (a resumed process killed before it
            # wrote; a record restored from the checkpoint taken before the
            # account): rebuilt, keeping what only the stored account knew
            if _timing.is_stale(stored, rows):
                acc = _timing.rebuild(stored, rows)
                acc["note"] = (acc.get("note") or "") + (
                    " (derived on load: the run wrote no account)"
                    if stored is None
                    else " (rebuilt on load: the ledger ran past the stored account)"
                )
                rr.timing = TimingRecord.model_validate(acc)
        except Exception:  # noqa: BLE001 - a reading, never a reason to fail a load
            pass
    fence = next((r for r in rows if r.get("event") == "research_fence"), None)
    if fence:
        _set(rr.run, "research_fence", {k: v for k, v in fence.items() if k != "event"})


def _round(rr: RunResult, k: int, rows: list[dict], module_of: dict) -> None:
    rnd = rr.round(k)
    markers = (rnd.status.markers if rnd.status else {}) or {}

    def marker(name: str, own: dict | None = None) -> dict:
        m = (own or {}).get(name) or markers.get(name)
        return m if isinstance(m, dict) else {}

    # ---- producers and sizes, from the markers that certified the slots
    if rnd.model is not None:
        _set(rnd.model, "producer", _producer(marker("s1").get("producer")))
    if rnd.data is not None:
        _set(rnd.data, "producer", _producer(marker("s2").get("producer")))
        if rnd.data.measurements is not None:
            _set(rnd.data, "n_rows", rnd.data.measurements.n_rows)

    decl = {
        str(c.get("id")): c
        for c in ((rnd.space.candidates if rnd.space else []) or [])
        if isinstance(c, dict) and c.get("id") is not None
    }
    for cid, cand in rnd.candidates.items():
        own = cand.markers or {}
        single = cid == "_single"
        if cand.model is not None:
            _set(cand.model, "producer", _producer(marker("s1", own).get("producer")))
        if cand.petab is not None:
            p, s3 = cand.petab, marker("s3", own)
            _set(p, "producer", _producer(s3.get("producer")))
            _set(p, "n_estimated", s3.get("n_estimated") or _n_estimated(p))
            _set(
                p,
                "n_train",
                s3.get("n_train")
                or (p.measurements.n_rows if p.measurements else None),
            )
            _set(
                p,
                "n_holdout",
                s3.get("n_holdout")
                or (p.holdout_measurements.n_rows if p.holdout_measurements else None),
            )
        if cand.cost is not None:
            _set(
                cand.cost,
                "approved_n_starts",
                marker("cost", own).get("approved_n_starts"),
            )
        meta = decl.get(cid) or {}
        _set(cand, "label", meta.get("label"))
        _set(cand, "rationale", meta.get("rationale"))
        m = re.search(r"axes on = \[(.*?)\]", str(meta.get("rationale") or ""))
        if m:
            _set(
                cand,
                "axes_on",
                [a.strip().strip("'\"") for a in m.group(1).split(",") if a.strip()],
            )
        if not single:
            dropped = next(
                (
                    r
                    for r in rows
                    if r.get("event") == "candidate_dropped"
                    and r.get("candidate") == cid
                ),
                None,
            )
            if dropped:
                _set(cand, "dropped", _event(dropped))
        for g in cand.gates.values():
            _gate(g, k, None if single else cid, module_of)
    for g in rnd.gates.values():
        _gate(g, k, None, module_of)

    # ---- agent calls: the ledger's rows for the role in this round. A row
    # goes to the entry whose reply key is the row's `io` (a role asked under
    # a record name of its own — `research_expansion` — is not the plain
    # role's call); a row without an `io` naming an entry falls back to its
    # role.
    from octomod.result.runstore import key as _key

    reply_suffix = {
        name: f"/agent_calls/{_key(name)}/reply" for name in rnd.agent_calls
    }

    def _entry_of(r: dict) -> str | None:
        io = str(r.get("io") or "")
        if io:
            for name, suffix in reply_suffix.items():
                if io.endswith(suffix) or io == suffix.lstrip("/"):
                    return name
        role = r.get("role")
        return role if role in rnd.agent_calls else None

    call_rows: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("event") == "agent_call":
            name = _entry_of(r)
            if name is not None:
                call_rows.setdefault(name, []).append(r)
    for role, call in rnd.agent_calls.items():
        calls = [e for e in (_event(r) for r in call_rows.get(role, [])) if e]
        redrafts = [
            e
            for e in (
                _event(r)
                for r in rows
                if r.get("event") == "redraft" and r.get("role") == role
            )
            if e
        ]
        if calls:
            _set(call, "calls", calls)
            # the ledger's cost is whatever the backend reported, unvalidated
            # (`meta.get("total_cost_usd")`): only a number counts, as in
            # `retry.py`, so one "n/a" row cannot make the record unloadable
            costs = [
                float(v)
                for v in ((c.model_extra or {}).get("cost_usd") for c in calls)
                if isinstance(v, (int, float))
            ]
            if costs:
                _set(call, "cost_usd", sum(costs))
        if redrafts:
            _set(call, "redrafts", redrafts)

    # ---- decisions: the ledger's human_gate rows give mode and question,
    # and a gate answered without a decision record still is a decision.
    # Decisions are recorded at round level, per candidate (a candidate's
    # cost boundary, its convergence gate) and as the expansion offer; a
    # module recorded in ANY of those is not invented again at round level.
    gate_rows = [r for r in rows if r.get("event") == "human_gate"]
    recorded: list[tuple[Any, str]] = [(d, s) for s, d in rnd.decisions.items()]
    for cand in rnd.candidates.values():
        recorded += [(d, s) for s, d in cand.decisions.items()]
    have = {d.module or s for d, s in recorded} | {s for _, s in recorded}
    offer = rnd.expansion_offer if isinstance(rnd.expansion_offer, dict) else None
    if offer is not None:
        have.add(str(offer.get("module") or "revision"))
    # A module may be asked more than once (a `redraft:` answer makes S1 delete
    # its decision and ask again on resume): the decision on record is the
    # LATEST answer, so its mode and time come from the last row, and a
    # redraft row is not a decision to be invented — the module was re-asked.
    for d, s in recorded:
        row = next(
            (r for r in reversed(gate_rows) if r.get("module") == (d.module or s)),
            None,
        )
        if row:
            _set(d, "mode", row.get("mode"))
            _set(d, "question", row.get("question"))
            _set(d, "at", row.get("ts"))
    for r in gate_rows:
        module = str(r.get("module"))
        if module in have or human_redraft.parse(r.get("note")):
            continue
        try:
            rnd.decisions[module] = DecisionRecord(
                module=module,
                question=r.get("question"),
                approved=r.get("approved"),
                note=str(r.get("note") or ""),
                mode=r.get("mode"),
                at=r.get("ts"),
                round=k,
                source_file=None,
            )
        except ValidationError:
            continue
        have.add(module)


def _gate(g, k: int, cid: str | None, module_of: dict) -> None:
    _set(g, "module", module_of.get((k, g.gate_id)))
    _set(g, "round", k)
    _set(g, "candidate", cid)


def _n_estimated(petab) -> int | None:
    t = petab.parameters
    if t is None or "estimate" not in (t.data or {}):
        return None
    try:
        return int(sum(int(v or 0) for v in t.data["estimate"]))
    except (TypeError, ValueError):
        return None
