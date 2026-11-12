"""A human `redraft:` at the cost boundary is delivered, not only ledgered (token-free).

The fixture `toy_super_redraft` ships the observation reply as a sequence:
.1.json has no scaling, .2.json puts a scale factor `sc_P` on the P_uM channel.

  1. the compile boundary pauses twice: once for the redraft, once with its result;
  2. every candidate's observables table changes and now carries `sc_P`;
  3. the ledger attributes the redraft to a human at `assembly_cost_boundary`;
  4. observation is called twice and construction once, no budget spent;
  5. the second prompt carries the human's words, and the run completes;
  6. on the single-model path (toy_phos) the same card takes the same redraft:
     S3 runs again after it, the checker audits the new draft, the card is asked
     again, and the run goes on to the budget gate.

    uv run python tests/cost_boundary_redraft_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

from _harness import check, finish  # noqa: E402
from _record import ledger_rows, pending_gate, rnd, run_root, work  # noqa: E402
from file_gate_loop import drive  # noqa: E402

from octomod.result.node import candidate_ids  # noqa: E402
from octomod.workflow_modules.assembly.petab_io import table_text  # noqa: E402

CASE = "toy_super_redraft"
REQUEST = "add a scaling factor sc_P on the P_uM channel"


def _ledger(root) -> list[dict]:
    return ledger_rows(root)


def _calls(rows: list[dict], role: str) -> int:
    return sum(
        1 for e in rows if e.get("event") == "agent_call" and e.get("role") == role
    )


def _reused(rows: list[dict], role: str) -> int:
    """Asks of `role` served from the record: the prompt was byte-identical to
    one already answered this round (`RunContext.call_cached`)."""
    return sum(
        1
        for e in rows
        if e.get("event") == "note"
        and e.get("module") == role
        and "reply reused from the record" in str(e.get("note"))
    )


def _table(node) -> str:
    df = node.table(None)
    return table_text(df) if df is not None else ""


def _observables(root) -> dict[str, str]:
    """Each candidate's PEtab observables table (as TSV text), from the record."""
    out = {}
    for cid in candidate_ids(rnd(root, 0)):
        node = work(root, 0, cid) / "petab/observables"
        if node.exists():
            out[cid] = _table(node)
    return out


def main() -> int:
    run_id = f"cbredraft_{time.strftime('%H%M%S')}"
    root = run_root(run_id)
    paused: dict = {}

    def at_pause(payload: dict, rd) -> None:
        # the FIRST compile boundary is the state the human redrafts from; its
        # passed s3 markers must not stop the candidates being re-assembled
        if payload["module"] == "assembly_cost_boundary" and "before" not in paused:
            paused["before"] = _observables(rd)
            paused["markers_before"] = sorted(
                (work(rd, 0, cid) / "markers/s3").key
                for cid in candidate_ids(rnd(rd, 0))
                if (work(rd, 0, cid) / "markers/s3").exists()
            )
            paused["card"] = payload

    t0 = time.time()
    rc, gates = drive(
        CASE,
        run_id,
        answers={
            "model_scope": [("y", "tier: top1")],
            "assembly_cost_boundary": [("y", f"redraft: {REQUEST}"), ("y", "")],
            # the budget gate's own documented form; the protocol under test
            # does not get truer with more starts
            "cost_boundary_estimation": [("y", "n=20")],
        },
        at_pause=at_pause,
    )
    print(f"exit {rc}; gates: {gates} ({time.time() - t0:.0f}s)")
    check("the run completes", rc == 0, f"exit {rc}; gates {gates}")
    check(
        "the compile boundary paused twice: once to take the redraft, once with "
        "the redrafted assembly",
        gates.count("assembly_cost_boundary") == 2,
        str(gates),
    )
    card = paused.get("card") or {}
    check(
        "the compile-boundary card ADVERTISES the redraft form",
        any("redraft:" in str(f) for f in card.get("note_forms") or []),
        str(card.get("note_forms"))[:200],
    )
    before = paused.get("before") or {}
    check(
        "every candidate had an observables table and a passed s3 marker when the "
        "human redrafted",
        len(before) >= 2 and len(paused.get("markers_before") or []) == len(before),
        f"{sorted(before)} / {paused.get('markers_before')}",
    )
    after = _observables(root)
    changed = sorted(c for c in before if after.get(c) != before[c])
    check(
        "every candidate's observables table CHANGED after the redraft — the "
        "request was delivered, not only ledgered",
        bool(before) and changed == sorted(before),
        f"changed {changed} of {sorted(before)}",
    )
    # a scale factor is a PEtab observable-parameter PLACEHOLDER in
    # observables.tsv (visible to pyPESTO's hierarchical inner problem) and its
    # real id, `sc_P`, in the measurement table's observableParameters column
    placeholder = "observableParameter1_obs_P_uM"
    check(
        "… and now carries the requested scale factor's placeholder, which it "
        "did not before",
        bool(before)
        and all(placeholder in after.get(c, "") for c in before)
        and not any(placeholder in before[c] for c in before),
    )
    for c in sorted(before):
        petab = work(root, 0, c) / "petab"
        meas = _table(petab / "measurements")
        pars = _table(petab / "parameters")
        check(
            f"{c}: `sc_P` is named in the measurement table and estimated in the "
            f"parameter table",
            "sc_P" in meas and "sc_P" in pars,
        )
    rows = _ledger(root)
    check(
        "the ledger attributes the redraft to a human at the cost boundary",
        any(
            e.get("event") == "note"
            and e.get("human_redraft") is True
            and e.get("module") == "assembly_cost_boundary"
            and REQUEST in str(e.get("note"))
            for e in rows
        ),
    )
    check(
        "observation called twice, construction once (the redraft did "
        "not re-roll the model)",
        _calls(rows, "observation") == 2 and _calls(rows, "construction") == 1,
        f"obs {_calls(rows, 'observation')} / constr {_calls(rows, 'construction')}",
    )
    prompt = (rnd(root, 0) / "agent_calls/observation/prompt").text("") or ""
    check(
        "the second observation prompt carries the human's words under "
        "human_feedback",
        "human_feedback" in prompt and REQUEST in prompt,
    )
    check(
        "the redraft did not spend the agent's retry budget",
        not any(e.get("event") == "redraft_grant" for e in rows)
        and "assembly_redraft_budget" not in gates,
        str(gates),
    )
    check_the_single_model_path()
    return finish(
        "\nCOST-BOUNDARY REDRAFT",
        "\ncost-boundary redraft: delivered, re-assembled, attributed",
    )


def check_the_single_model_path() -> None:
    """The single model's compile card is the same card, asked after S3: a
    redraft there removes S3's marker, so the assembly is drafted again."""
    request = "add a background offset on the pR_au readout"
    run_id = f"cbredraft_single_{time.strftime('%H%M%S')}"
    root = run_root(run_id)
    rc, gates = drive(
        "toy_phos",
        run_id,
        answers={"assembly_cost_boundary": [("y", f"redraft: {request}"), ("y", "")]},
        max_gates=4,
    )
    pending = pending_gate(root)
    waiting = pending["module"] if pending is not None else None
    print(f"single model: exit {rc}; gates: {gates}; waiting at {waiting}")
    check(
        "single model: the compile card paused twice, then the budget gate waits",
        gates[-2:] == ["assembly_cost_boundary", "assembly_cost_boundary"]
        and rc == 3
        and waiting == "cost_boundary_estimation",
        f"{gates} then {waiting} (exit {rc})",
    )
    rows = _ledger(root)
    check(
        "single model: the redraft is attributed to a human at the compile card",
        any(
            e.get("event") == "note"
            and e.get("human_redraft") is True
            and e.get("module") == "assembly_cost_boundary"
            and request in str(e.get("note"))
            for e in rows
        ),
    )
    assembly_markers = [
        e for e in rows if e.get("event") == "marker" and e.get("module") == "s3"
    ]
    # toy_phos has one observation stub, so the redrafted tables are the first
    # draft's and the checker's second ask is byte-identical: it is ASKED again
    # and served from the record, not paid for twice
    checker_asks = _calls(rows, "assembly_verification") + _reused(
        rows, "assembly_verification"
    )
    check(
        "single model: S3 ran again after the redraft (two s3 markers), and the "
        "observation and checker agents were asked again, construction once",
        len(assembly_markers) == 2
        and _calls(rows, "observation") == 2
        and checker_asks == 2
        and _calls(rows, "construction") == 1,
        f"s3 markers {len(assembly_markers)}, obs {_calls(rows, 'observation')}, "
        f"checker asks {checker_asks} ({_calls(rows, 'assembly_verification')} paid, "
        f"{_reused(rows, 'assembly_verification')} reused), "
        f"constr {_calls(rows, 'construction')}",
    )
    prompt = (rnd(root, 0) / "agent_calls/observation/prompt").text("") or ""
    check(
        "single model: the second observation prompt carries the human's words",
        "human_feedback" in prompt and request in prompt,
    )


if __name__ == "__main__":
    sys.exit(main())
