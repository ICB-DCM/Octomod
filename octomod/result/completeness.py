"""Is the record complete enough to say what the run did?

Every module writes into the record as it goes, and `round_status.SLOTS` says
the few parts a DOWNSTREAM module cannot live without. Neither says whether a
reader of the finished record can still see what happened: the model a module
built but not its parameters, a fit without its multistart, an agent call on
the ledger whose prompt and reply never reached the record. A part left out by
accident looks exactly like a part that was never needed — until somebody
reads the record and cannot answer a question from it.

`check` is the audit for that. It runs at the points the record is
checkpointed (`autocommit.commit_run`): every marker (a module passed), every
decision, every pause, the end of the run and the final document write. Each
checkpoint has a declared list of what must be in the record by then
(`EXPECTED` below, conditional on who produced the slot and on the shape of
the round), and the result is written into the record itself, one entry per
checkpoint — `completeness/run/<run_end|final|gate_pending>`,
`completeness/round_k/<module>/<unit>` for a marker and
`completeness/round_k/decision_<module>/<unit>` for a decision, the unit being
the candidate or `_round`:

    {checkpoint, round, candidate, at, checked: [what was looked for],
     missing: [{key, what}], error}

A finding is reported, never enforced: the run goes on, the console says what
is missing, `status` and the analysis report show it, and the test battery
fails a suite whose records carry one (`tests/run_all.py`). A check that
itself fails records its error; it never fails the run.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from octomod.result import node as tree
from octomod.result.node import Node
from octomod.result.runstore import RecordDamaged

KEY = "completeness"
TABLE_FIELDS = {"columns", "data", "elided"}  # what a stored `Table` holds


@dataclass
class Finding:
    """What one checkpoint looked for and what it did not find."""

    checked: list[str] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)

    def need(self, node: Node, what: str, *, nonempty: bool = True) -> bool:
        """`node` must exist (and, by default, hold something)."""
        self.checked.append(node.key)
        ok = _present(node, nonempty)
        if not ok:
            self.missing.append({"key": node.key, "what": what})
        return ok

    def require(self, ok: bool, key: str, what: str) -> bool:
        """A condition that is not one key's presence."""
        self.checked.append(key)
        if not ok:
            self.missing.append({"key": key, "what": what})
        return ok


def _present(node: Node, nonempty: bool) -> bool:
    """Decided from the node's shape (one read, nothing decoded): a stored
    `Table` is present when it has rows, any other group when it has
    children; only a leaf is decoded, to tell an empty one from a full one.
    A dict that happens to carry a `columns` key has other children beside
    it and is not mistaken for an empty table, and a large group (the
    multistart) is never decoded only to say that it exists."""
    try:
        if not node.exists():
            return False
        if not nonempty:
            return True
        kids = node.children()
        if kids:
            if "columns" in kids and set(kids) <= TABLE_FIELDS:
                df = node.table(None)
                return df is not None and not df.empty
            return True
        try:
            value = node.get(None)
        except Exception:  # noqa: BLE001 — a leaf of a kind this check does not read
            return True
        if value is None:
            return False
        if isinstance(value, (str, list, dict, tuple)):
            return len(value) > 0
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------ what is expected
def _marker(rnd: Node, cid: str | None, name: str) -> dict:
    node = tree.markers_node(rnd, cid) / name
    return (node.get(None) or {}) if node.exists() else {}


def _round_calls(f: Finding, root: Node, rnd: Node) -> None:
    """Every agent the ledger says was called in this round left its prompt
    and reply. Read from the ledger, not from a slot's producer: a seeded or
    expansion round carries an `agent:` producer from the round it was seeded
    from without calling that agent again."""
    k = tree.round_index(rnd)
    rows = [
        r
        for r in root.store.ledger_rows()
        if r.get("event") == "agent_call" and r.get("round", 0) == k
    ]
    _calls(f, root, rows)


def _gates(f: Finding, rnd: Node, cid: str | None, prefix: str, what: str) -> None:
    gates = tree.gates_node(rnd, cid)
    names = gates.children() if gates.exists() else []
    f.require(
        any(n.startswith(prefix) for n in names),
        f"{gates.key}/{prefix}*",
        f"the {what} checks' verdicts",
    )


def _units(rnd: Node, cid: str | None, marker: dict | None = None) -> list[str | None]:
    """The units a round-level marker certifies: the candidates the marker
    names (S1 lists them), else every candidate group of a candidate round,
    else the round's own model."""
    if cid is not None:
        return [cid]
    named = (marker or {}).get("candidates")
    if isinstance(named, list) and named:
        return [str(c) for c in named]
    return tree.candidate_ids(rnd) or [None]


def _s1(f: Finding, rnd: Node, cid: str | None) -> None:
    mk = _marker(rnd, cid, "s1")
    producer = str(mk.get("producer") or "")
    by_agent = producer.startswith("agent:")
    for unit in _units(rnd, cid, mk):
        model = tree.model_node(rnd, unit)
        f.need(model / "sbml", "the model as SBML")
        f.need(model / "parameters", "the parameter table")
        if by_agent:
            # an agent writes Antimony; a supplied PEtab problem has it only
            # when the SBML round-trips (`adapt_supplied_petab`)
            f.need(model / "antimony", "the model as Antimony")
            # written even when construction gave no entries: an empty
            # glossary is a reply's content, not a part left out
            f.need(model / "glossary", "what each model entity denotes", nonempty=False)
        _gates(f, rnd, unit, "model_", "model (S1)")
    if by_agent:
        f.need(rnd / "model" / "build_report", "construction's decisions")


def _s2(f: Finding, rnd: Node, cid: str | None) -> None:
    # the producer decides nothing here: the agent call is the ledger's
    f.need(rnd / "data" / "measurements", "the measurements the fit uses")
    f.need(rnd / "data" / "report", "the data module's report")


def _s3(f: Finding, rnd: Node, cid: str | None) -> None:
    mk = _marker(rnd, cid, "s3")
    work = tree.work_node(rnd, cid)
    for part, what in (
        ("problem_yaml", "the PEtab problem file"),
        ("observables", "the observable table"),
        ("conditions", "the condition table"),
        ("measurements", "the measurement table"),
        ("parameters", "the parameter table"),
    ):
        f.need(work / "petab" / part, what)
    _gates(f, rnd, cid, "assembly_", "assembly (S3)")
    if str(mk.get("producer") or "") == "agent:assembly":
        # a candidate of a shared assembly holds its own copy, as does an
        # inherited one: the encoding the fit was built from
        f.need(work / "assembly", "the assembly's observation and condition encoding")


def _cost(f: Finding, rnd: Node, cid: str | None) -> None:
    f.need(tree.work_node(rnd, cid) / "cost", "the cost probe and the approved budget")


def _s6(f: Finding, rnd: Node, cid: str | None) -> None:
    work = tree.work_node(rnd, cid)
    est = work / "estimation"
    if f.need(est, "the fit summary"):
        value = est.get(None) or {}
        for k in ("best_fval", "x_names", "best_x_unscaled", "fvals"):
            f.require(k in value, f"{est.key}#{k}", f"the fit summary's {k}")
    f.need(work / "multistart", "the multistart result as pyPESTO produced it")
    _gates(f, rnd, cid, "estimation_", "estimation (S6)")


def _s7(f: Finding, rnd: Node, cid: str | None) -> None:
    has_evaluation = f.need(rnd / "evaluation", "the round's evaluation")
    f.need(rnd / "evaluation_core", "the evaluation's computed core")
    f.need(rnd / "report_md", "the round's report")
    # only the one key is decoded, not the whole evaluation a second time
    disc = rnd / "evaluation" / "discrimination"
    discriminated = has_evaluation and disc.exists() and bool(disc.get(None))
    if discriminated:
        sel = rnd / "selection"
        if f.need(sel, "the model selection"):
            value = sel.get(None) or {}
            for k in ("winner", "values", "weights"):
                f.require(k in value, f"{sel.key}#{k}", f"the selection's {k}")
    # the decision record is rendered from construction's and the assembly's
    # own records, so it exists exactly when an agent built one of them
    built_by_agent = any(
        str(_marker(rnd, unit, module).get("producer") or "").startswith("agent:")
        for module in ("s1", "s3")
        for unit in [None, *tree.candidate_ids(rnd)]
    )
    if built_by_agent:
        f.need(rnd / "decisions_md", "the decision record of the agents' reasoning")


MODULE_CHECKS = {
    "s1": _s1,
    "s2": _s2,
    "s3": _s3,
    "cost": _cost,
    "s6": _s6,
    "s7": _s7,
}


def _decision(
    f: Finding, root: Node, rnd: Node, module: str, subject: str | None
) -> None:
    """The decision just written: at `subject` when the writer names it (a
    gate's decision lives where its caller keeps it — a candidate's fit
    holds `decisions/estimation_convergence`), else at the round's `decisions/<module>`.
    """
    if module == "revision_proposal":  # the revision move is the round's `revision`
        f.need(root / subject if subject else rnd / "revision", "the revision move")
        return
    node = root / subject if subject else rnd / "decisions" / module
    if f.need(node, f"the decision at {module}"):
        value = node.get(None) or {}
        for k in ("approved", "signed", "at"):
            f.require(k in value, f"{node.key}#{k}", f"the decision's {k}")


def _call_kept(root: Node, io: str) -> bool:
    """An agent call's reply and prompt are where its ledger row says, or in a
    copy a re-entry moved aside (`rounds/round_k/superseded/<module>_<stamp>/`)."""
    base = io.rsplit("/", 1)[0]
    if (root / io).exists() and (root / base / "prompt").exists():
        return True
    parts = io.split("/")
    if len(parts) >= 3 and parts[0] == "rounds":
        rnd = root / parts[0] / parts[1]
        rest = "/".join(parts[2:])
        sup = rnd / "superseded"
        for s in sup.children() if sup.exists() else []:
            moved = sup / s / rest
            if moved.exists() and (moved.parent / "prompt").exists():
                return True
    return False


def _calls(f: Finding, root: Node, rows: list[dict]) -> None:
    """Every agent call on the ledger has its prompt and reply in the record."""
    for i, r in enumerate(rows):
        if r.get("event") != "agent_call":
            continue
        io = str(r.get("io") or "")
        where = io or f"ledger[{i}]"
        f.require(
            bool(io) and _call_kept(root, io),
            where,
            f"the prompt and reply of the {r.get('role')} call the ledger records",
        )


def _agents(f: Finding, root: Node, rows: list[dict]) -> None:
    """Which agents the run was set up with, and which models its calls ran
    on: the declared setup in the run's provenance, a resolved model on
    every live call, and the record's summary of them."""
    meta = (root / "run").get(None) if (root / "run").exists() else None
    prov = (meta or {}).get("provenance") or {}
    f.require(
        bool(prov.get("agents")),
        "run#provenance.agents",
        "the agents the run was set up with (backend, models, effort, CLI)",
    )
    calls = [r for r in rows if r.get("event") == "agent_call"]
    for i, r in enumerate(calls):
        if r.get("backend") == "llm":
            # the resolved id when the CLI reported its usage; else the model
            # the call was made with, which is all a reply without a usage
            # block lets the record say (`agents.resolved_model`)
            f.require(
                bool(r.get("model_resolved") or r.get("models_used") or r.get("model")),
                str(r.get("io") or f"agent_call[{i}]") + "#model",
                f"the model the {r.get('role')} call ran on",
            )
    if calls:
        f.need(root / "models_used", "which models the agent calls ran on")


def _run_level(f: Finding, root: Node, rows: list[dict], *, final: bool) -> None:
    run = root / "run"
    if f.need(run, "the run's metadata"):
        meta = run.get(None) or {}
        for k in ("run_id", "backend", "workflow_sha"):
            f.require(bool(meta.get(k)), f"{run.key}#{k}", f"the run's {k}")
        f.require(
            (root / "input").exists() or bool(meta.get("testcase_sha")),
            "input",
            "what the run was started with (`input`, or a legacy run's testcase_sha)",
        )
    if (root / "input").exists():
        f.need(root / "input_source", "where the run's input came from")
    events = [r.get("event") for r in rows]
    f.require("run_start" in events, "ledger#run_start", "the run's start row")
    _calls(f, root, rows)
    _agents(f, root, rows)
    ends = [r for r in rows if r.get("event") == "run_end"]
    # these checkpoints follow the row: the orchestrator appends it first
    if not f.require(bool(ends), "ledger#run_end", "the run's end row"):
        return
    if not str(ends[-1].get("outcome") or "").startswith("completed"):
        return
    # a completed run: what it set out to do, and the round that answered it
    f.need(root / "intent", "the frozen intent")
    rounds = tree.round_indices(root)
    if f.require(bool(rounds), "rounds", "the rounds the run completed") and rounds:
        last = tree.round_node(root, max(rounds))
        f.require(
            (tree.markers_node(last, None) / "s7").exists(),
            f"{last.key}/markers/s7",
            "the final round's evaluation marker",
        )
    if final:
        f.need(root / "analysis", "the analysis report's summary")


# ------------------------------------------------------------ the check
def _where(why: str, round_idx: int, candidate: str | None) -> tuple[str, int | None]:
    """The entry's record key, and the round it is about (None: the run)."""
    if why.startswith("marker:"):
        name = why.split(":", 1)[1]
        unit = candidate or "_round"
        return f"{KEY}/round_{round_idx}/{name}/{unit}", round_idx
    if why.startswith("decision:"):
        module = why.split(":", 1)[1]
        return (
            f"{KEY}/round_{round_idx}/decision_{module}/{candidate or '_round'}",
            round_idx,
        )
    return f"{KEY}/run/{why}", None


def run_checks(
    root: Node,
    why: str,
    *,
    round_idx: int = 0,
    candidate: str | None = None,
    subject: str | None = None,
) -> Finding:
    """What the record must hold at checkpoint `why`, and what it lacks."""
    f = Finding()
    if why.startswith("marker:"):
        name = why.split(":", 1)[1]
        fn = MODULE_CHECKS.get(name)
        if fn is not None:
            rnd = tree.round_node(root, round_idx)
            fn(f, rnd, candidate)
            if name in ("s1", "s2", "s3", "s7") and candidate is None:
                _round_calls(f, root, rnd)
    elif why.startswith("decision:"):
        module = why.split(":", 1)[1]
        # the expansion decision is the round's `expansion`, committed without
        # its round index, so it is checked where that round's markers are
        if module != "revision":
            _decision(f, root, tree.round_node(root, round_idx), module, subject)
    elif why in ("run_end", "final"):
        _run_level(f, root, root.store.ledger_rows(), final=why == "final")
    elif why == "gate_pending":
        pending = tree.pending_node(root)
        if f.need(pending, "the question the paused run is waiting on"):
            value = pending.get(None) or {}
            for k in ("module", "question"):
                f.require(bool(value.get(k)), f"{pending.key}#{k}", f"the card's {k}")
        rows = root.store.ledger_rows()
        _calls(f, root, rows)
        _agents(f, root, rows)
    return f


def check(
    root_or_store,
    why: str,
    *,
    round_idx: int = 0,
    candidate: str | None = None,
    subject: str | None = None,
) -> dict | None:
    """Run the checks for checkpoint `why` and write the entry into the record.

    Returns the entry (None when `why` is not a checkpoint this audits). A
    check that fails records its error instead of raising; the one exception
    is `RecordDamaged`, which stops the run wherever it is met.
    """
    root = (
        root_or_store if isinstance(root_or_store, Node) else tree.root(root_or_store)
    )
    if not (
        why.startswith(("marker:", "decision:"))
        or why in ("run_end", "final", "gate_pending")
    ):
        return None
    if why.startswith("marker:") and why.split(":", 1)[1] not in MODULE_CHECKS:
        return None  # a marker with nothing declared for it (candidate_compile)
    key, rnd = _where(why, round_idx, candidate)
    entry: dict[str, Any] = {
        "checkpoint": why,
        "round": rnd,
        "candidate": candidate,
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "checked": [],
        "missing": [],
        "error": None,
    }
    try:
        f = run_checks(
            root, why, round_idx=round_idx, candidate=candidate, subject=subject
        )
        entry["checked"], entry["missing"] = f.checked, f.missing
    except RecordDamaged:
        raise  # the file was restored under us: the checkpoint's own rule applies
    except Exception as e:  # noqa: BLE001 — an audit never fails the run
        entry["error"] = f"{type(e).__name__}: {e}"[:500]
    try:
        (root / key).put(entry)  # the JSON round trip and NUL escape of every artifact
    except RecordDamaged:
        raise
    except Exception as e:  # noqa: BLE001
        entry["error"] = f"could not write the entry: {type(e).__name__}: {e}"[:500]
    if entry["missing"]:
        where = (
            f" (round {rnd}{', ' + candidate if candidate else ''})"
            if rnd is not None
            else ""
        )
        listed = "; ".join(f"{m['key']} — {m['what']}" for m in entry["missing"][:6])
        more = len(entry["missing"]) - 6
        print(
            f"  ⚠ record check after {why}{where}: {len(entry['missing'])} part(s) "
            f"missing: {listed}" + (f"; and {more} more" if more > 0 else "")
        )
    return entry


# ------------------------------------------------------------ reading
def entries(root: Node) -> list[dict]:
    """Every checkpoint's entry in the record, in no particular order. The
    group is decoded once and walked in memory: a card reads it at every gate."""
    top = root / KEY
    if not top.exists():
        return []
    try:
        tree_ = top.get(None) or {}
    except Exception:  # noqa: BLE001 — an unreadable group: nothing to report
        return []
    out: list[dict] = []

    def walk(value) -> None:
        if not isinstance(value, dict):
            return
        if "checkpoint" in value:
            out.append(value)
            return
        for child in value.values():
            walk(child)

    walk(tree_)
    return out


def _dropped(root: Node, k) -> set[str]:
    """The candidates round `k` dropped (`space/dropped`): their entries no
    longer describe anything the result rests on."""
    if k is None:
        return set()
    node = tree.round_node(root, int(k)) / "space" / "dropped"
    try:
        value = node.get(None) if node.exists() else None
    except Exception:  # noqa: BLE001
        return set()
    ids = set()
    for d in value or []:
        ids.add(str(d.get("id") if isinstance(d, dict) else d))
    return ids


def summary(root: Node) -> dict:
    """{checkpoints, incomplete: [entries with something missing], errors},
    leaving out the entries of candidates their round dropped."""
    dropped: dict = {}
    kept = []
    for e in entries(root):
        k = e.get("round")
        if k not in dropped:
            dropped[k] = _dropped(root, k)
        if e.get("candidate") and e["candidate"] in dropped[k]:
            continue
        kept.append(e)
    return {
        "checkpoints": len(kept),
        "incomplete": [e for e in kept if e.get("missing")],
        "errors": [e for e in kept if e.get("error")],
    }


def forget(root: Node, round_idx: int, modules) -> None:
    """Drop round `round_idx`'s entries for `modules` (their markers) and for
    the decisions those modules asked: a re-entry moved their records aside,
    and the next pass checks them again. A gate's id begins with the marker
    of the module that asks it (`estimation_convergence`, `cost_probe`); the S11
    revision follows the evaluation it revises. Never raises: a stale entry
    is not worth a failed re-entry."""
    try:
        rk = root / KEY / f"round_{int(round_idx)}"
        if not rk.exists():
            return
        names = {str(s) for s in modules}
        if "s7" in names:
            names.add("s11")
        # a gate's id begins with its module's word (`estimation_convergence`),
        # not with the module's marker code (`s6`)
        words = {
            {
                "s0": "intent",
                "s1": "model",
                "s2": "data",
                "s3": "assembly",
                "s6": "estimation",
                "s7": "evaluation",
                "s11": "revision_proposal",
            }.get(n, n)
            for n in names
        }
        for child in rk.children():
            gate = child[len("decision_") :] if child.startswith("decision_") else None
            if child in names or (
                gate and any(gate == w or gate.startswith(w + "_") for w in words)
            ):
                (rk / child).delete()
    except RecordDamaged:
        raise  # the file was restored under us: the run's own rule applies
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ record checks: stale entries not dropped ({type(e).__name__}: {e})")


def forget_run(root: Node) -> None:
    """Drop the run-level entries (pause, run end, final) at a new start: they
    described how the previous process ended, and this one checks its own.
    Never raises, like `forget`."""
    try:
        node = root / KEY / "run"
        if node.exists():
            node.delete()
    except RecordDamaged:
        raise  # the file was restored under us: the run's own rule applies
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ record checks: stale entries not dropped ({type(e).__name__}: {e})")


def summary_line(root: Node) -> str | None:
    """One line for `status` and the analysis report (None before any check)."""
    s = summary(root)
    if not s["checkpoints"]:
        return None
    if not s["incomplete"] and not s["errors"]:
        return f"record checks: {s['checkpoints']} checkpoint(s), nothing missing"
    n_missing = sum(len(e["missing"]) for e in s["incomplete"])
    first = s["incomplete"][0]["missing"][0]["key"] if s["incomplete"] else ""
    return (
        f"record checks: {s['checkpoints']} checkpoint(s), {n_missing} part(s) "
        f"missing at {len(s['incomplete'])}"
        + (f" (first: {first})" if first else "")
        + (f", {len(s['errors'])} check error(s)" if s["errors"] else "")
    )


def gaps(path) -> list[str]:
    """What the checks recorded as missing in the record at `path`, one line
    per part (`<file> after <checkpoint>: <key> — <what>`); a record that
    cannot be read is one line saying so. What the battery fails a suite for."""
    from pathlib import Path

    from octomod.result.runstore import RunStore

    path = Path(path)
    try:
        s = summary(tree.root(RunStore(path)))
    except Exception as e:  # noqa: BLE001
        return [
            f"{path.name}: its record checks could not be read ({type(e).__name__}: {e})"
        ]
    out = []
    for e in s["incomplete"]:
        where = e["checkpoint"] + (f" {e['candidate']}" if e.get("candidate") else "")
        out += [
            f"{path.name} after {where}: {m['key']} — {m['what']}" for m in e["missing"]
        ]
    out += [
        f"{path.name} after {e['checkpoint']}: the check failed: {e['error']}"
        for e in s["errors"]
    ]
    return out


CARD_GAPS = 5  # missing parts listed on a gate card; the rest are counted


def card_lines(root: Node) -> tuple[list[str], list[dict]]:
    """What a gate card says about the record's gaps: a headline, the first
    `CARD_GAPS` missing parts (each with the checkpoint after which it was
    looked for) and where to read the rest; and the gaps as data, for the
    pending-gate payload. Nothing when nothing is missing."""
    s = summary(root)
    gaps = [
        {
            "checkpoint": e.get("checkpoint"),
            "round": e.get("round"),
            "candidate": e.get("candidate"),
            "key": m["key"],
            "what": m["what"],
        }
        for e in s["incomplete"]
        for m in e.get("missing") or []
    ]
    errors = [e for e in s["errors"] if e.get("error")]
    if not gaps and not errors:
        return [], []
    lines = [
        (
            (
                f"⚠ RECORD INCOMPLETE — {len(gaps)} part(s) a finished step should "
                "have left in the record are missing; the run goes on, but the "
                "record cannot show them:"
            )
            if gaps
            else "⚠ RECORD CHECKS — a completeness check could not run:"
        )
    ]
    for g in gaps[:CARD_GAPS]:
        at = g["checkpoint"] + (f", {g['candidate']}" if g.get("candidate") else "")
        lines.append(f"    after {at}: {g['key']} — {g['what']}")
    if len(gaps) > CARD_GAPS:
        lines.append(f"    … and {len(gaps) - CARD_GAPS} more")
    if errors:
        lines.append(f"    {len(errors)} record check(s) could not run")
    lines.append(f"    every gap: ./run.sh status --run-id {root.store.run_id}")
    return lines, gaps
