"""The expansion path end to end through file gates, on the abcd_expansion stub case.

  1. round 0 makes three expansion calls: requests, a bad-axis proposal, one re-call;
  2. four diagnostic requests run cleanly and persist with the final proposal;
  3. the residual-form fit carries a verdict and both null comparisons;
  4. the card shows the agent's base; a plain yes keeps the criterion winner;
  5. a bare yes at round 1's scope gate searches the axes bought at the expansion gate;
  6. round 1 starts from round 0's winner, reuses its fit and states its topology;
  7. round 1's winner carries both mechanisms and closes the misfit;
  8. the expansion and observation prompts carry the full payload;
  9. report.html exists at every verdict pause; the run writes one run_end row;
 10. the verdict card promises an expansion exactly when the engine runs one.

    uv run python tests/expansion_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

from file_gate_loop import drive  # noqa: E402

sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from tests import observation_evidence_unit, tried_models_unit  # noqa: E402
from tests._record import ledger_rows, reports_dir, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

RUN_ID = "expansion_smoke"


def main() -> int:
    root = run_root(RUN_ID)  # the run is one file
    if root.exists():
        root.store.remove()
    # Round 0 buys the one declared axis; round 1's scope gate gets a bare yes,
    # which must honour the axes bought at the expansion gate.
    cards: list[dict] = []
    # The verdict card points the human to report.html, so it must be on disk
    # at the pause itself (and the record's `report_md` with it).
    seen_at_verdict: list[tuple[int, bool, bool]] = []

    def at_pause(payload: dict, root) -> None:
        if payload["module"] != "evaluation_verdict":
            return
        k = payload["round"]
        html = reports_dir(root) / f"round_{k}" / "report" / "report.html"
        seen_at_verdict.append(
            (
                k,
                html.exists(),
                (rnd(root, k) / "report_md").exists(),
            )
        )
        assert html.exists(), (
            f"round {payload['round']}: the verdict card is waiting and "
            f"report.html does not exist yet — the card names a document the "
            f"human cannot open"
        )

    rc, gates = drive(
        "abcd_expansion",
        RUN_ID,
        answers={"model_scope": [("y", "axes: product_feedback"), ("y", "")]},
        collect=cards,
        at_pause=at_pause,
    )
    print(f"exit {rc}; gates: {gates}")
    assert rc == 0, f"run ended {rc}"
    assert gates.count("revision") == 1, "the expansion gate must pause exactly once"
    assert gates.index("revision") < len(gates) - 1, "round 1 must follow the expansion"
    ledger = ledger_rows(root)
    calls = [
        e for e in ledger if e["event"] == "agent_call" and e["role"] == "revision"
    ]
    r0_calls = [e for e in calls if e["round"] == 0]
    assert len(r0_calls) == 3, (
        "expected 3 expansion calls in round 0 (request round, proposal "
        f"with an invalid axis, the single bounded re-call), saw {len(r0_calls)}"
    )
    redrafts = [
        e for e in ledger if e["event"] == "redraft" and e["role"] == "revision"
    ]
    assert (
        len(redrafts) == 1
    ), f"expected exactly one expansion redraft row, saw {redrafts}"
    ghost = [
        e
        for e in ledger
        if e["event"] == "note"
        and "ghost_sink" in str(e.get("note"))
        and "dropped" in str(e.get("note"))
    ]
    assert (
        ghost
    ), "the ghost axis must be dropped by the eager validator with a named note"
    diag = [e for e in ledger if e["event"] == "diagnostic_request"]
    assert len(diag) == 4, f"expected 4 diagnostic requests, saw {len(diag)}"
    bad = [d for d in diag if not d["ok"]]
    assert not bad, f"diagnostics errored: {[d['error'] for d in bad]}"
    r0, r1 = rnd(root, 0), rnd(root, 1)
    state = (r0 / "expansion_diagnostics").get()
    assert (
        state.get("final_proposal") and state["steps"]
    ), "diagnostic loop not persisted"
    kinds = [r["kind"] for r in state["steps"][0]["results"]]
    assert kinds == [
        "residuals_for",
        "fit_residual_form",
        "compare_conditions",
        "simulate_with",
    ], kinds
    form = state["steps"][0]["results"][1]["result"]
    assert "verdict" in form and "delta_bic_vs_ar1" in form, form
    print(
        f"form fit on obs_ProD@c_u1_bx: {form.get('best_form')} — {form['verdict'][:90]}"
    )
    exp = (r0 / "expansion").get()
    assert exp["expanded"] and exp["axes"] == ["basal_route"], exp

    # The stub recommends `base` over the criterion winner: the card shows it,
    # and a plain yes keeps the winner, because the base is the human's choice.
    card = next(c for c in cards if c["module"] == "revision")
    shown = "\n".join(str(x) for x in (card.get("lines") or []))
    assert "BASE FOR THE ENLARGED SPACE" in shown, (
        "the expansion card must offer the base choice when the agent "
        f"recommends one: {shown[-600:]}"
    )
    assert "the agent recommends base" in shown and "why:" in shown, shown[-600:]
    assert exp["expanded_from"] == "product_feedback", (
        "a plain yes must keep the criterion winner as the base — the "
        f"recommendation is shown, not taken: {exp}"
    )
    assert exp["base_was_the_agents_recommendation"] is False, exp
    # Every round's indistinguishable set is a singleton here, so nothing is
    # carried undecided.
    assert exp["carried_undecided"] == [], exp
    d0 = (r0 / "evaluation").get()["discrimination"]
    assert d0["undecided_axes"] == [], d0["undecided_axes"]
    topo = d0["search_topology"]
    assert topo["visited"] >= 2 and topo["union_lattice_models"] >= 2, topo
    print(
        f"round 0 topology: visited {topo['visited']} of "
        f"{topo['union_lattice_models']} ({topo['topology']})"
    )
    # the purchase was honoured without being re-asked, and the ledger says so
    bought = [
        e
        for e in ledger
        if e["event"] == "note"
        and "bought at the previous round's expansion gate" in str(e.get("note"))
    ]
    assert bought, (
        "a bare yes at the expansion round's scope gate must search the "
        "axes already bought, and the ledger must record that it did"
    )
    space = (r1 / "space/axes").get()
    assert not any(
        a.get("frozen") for a in space
    ), f"no bought axis may be frozen by silence: {space}"
    rep1 = (r1 / "evaluation").get()
    d1 = rep1["discrimination"]
    print(
        "round 1 selection:",
        [(c["id"], c["delta_aic"], c["akaike_weight"]) for c in d1["candidates"]],
    )
    assert (
        d1["winner"] == "basal_route"
    ), f"round-1 winner should carry the added route, got {d1['winner']}"
    assert not (rep1.get("misfit_evidence") or {}).get(
        "open"
    ), "misfit should close with both mechanisms"
    # With two rounds, the greedy topology and the cross-round regime are stated.
    topo1 = d1["search_topology"]
    assert topo1["union_lattice_models"] == 4 and topo1["visited"] == 3, topo1
    assert topo1["models_outside_the_lattice"] == [], topo1
    regime = d1["cross_round_comparability"]
    assert regime["across_rounds"] and regime["regime"] == "pure expansion", regime
    print(
        f"round 1 topology: visited {topo1['visited']} of "
        f"{topo1['union_lattice_models']} — the unvisited corner is the one "
        f"combining both mechanisms; cross-round comparability: "
        f"{regime['regime']}"
    )
    # the winner's model has both ingredients
    ant = (tree.model_node(r1, "basal_route") / "antimony").text()
    assert (
        "k_cat_alt" in ant and "K_fb" in ant
    ), "round-1 winner must carry feedback AND the basal route"
    # Round 1's base is exactly round 0's fitted winner: neither probed nor refitted.
    w0 = (r0 / "evaluation").get()["discrimination"]["winner"]
    seed = ((r0 / "expansion").get(None) or {}).get("seed") or {}
    assert seed.get("candidate") == w0, f"round 1 must be seeded from {w0}: {seed}"
    ident = [e for e in ledger if e.get("base_identity") and e.get("round") == 1]
    assert ident and ident[-1]["base_identity"]["identical"], (
        "round 1's base must BE round 0's winner: "
        f"{ident[-1]['base_identity'] if ident else 'no identity row'}"
    )
    not_probed = [e for e in ledger if e.get("fit_on_disk") and e.get("round") == 1]
    reused = [e for e in ledger if e.get("fit_reused") and e.get("round") == 1]
    assert not_probed and reused and "round_0" in str(reused[0].get("reused_from")), (
        "round 1's base is round 0's fitted problem: neither probed nor refitted "
        f"(probe skipped: {len(not_probed)}; fit reused: "
        f"{[e.get('reused_from') for e in reused]})"
    )
    print(
        f"  group C: round 1 seeded from {w0} exactly; its fit reused from "
        f"{reused[0]['reused_from']} — no probe, no refit"
    )
    # Read from the prompt, the only place that shows the payload reached the
    # agent; no untested-first gate fires (the engine has none).
    tried_models_unit.check_expansion_payload(root)
    # Round 0 has both prompts: the observation block and the proposer's payload.
    observation_evidence_unit.check_observation_block(root, 0, "discrimination path")
    observation_evidence_unit.check_same_payload_as_proposer(root, 0)

    # report.html existed at every verdict pause, both rounds.
    assert [r for r, _, _ in seen_at_verdict] == [
        0,
        1,
    ], f"expected a verdict pause in each round, saw {seen_at_verdict}"
    assert all(html and md for _, html, md in seen_at_verdict), seen_at_verdict
    print(
        f"  report.html at the verdict pause: rounds {[r for r,_,_ in seen_at_verdict]}"
    )

    # One run_end row in a two-round run whose second round follows an expansion.
    ends = [e for e in ledger if e["event"] == "run_end"]
    assert len(ends) == 1, (
        f"{len(ends)} run_end rows in a two-round expanded run: "
        f"{[(e.get('outcome'), e.get('winner')) for e in ends]}"
    )
    assert ends[0].get("winner"), ends[0]
    print(f"  run_end: exactly one row, winner {ends[0]['winner']}")

    # The card promises the expansion exactly when the engine performs it, and
    # never on the final round.
    verdicts = [c for c in cards if c["module"] == "evaluation_verdict"]
    assert len(verdicts) == 2, [c["module"] for c in cards]
    promised = [
        "the expansion agent is asked" in str(c.get("consequences", ("", ""))[0])
        for c in verdicts
    ]
    expansion_gates_after = [
        any(g == "revision" for g in gates[gates.index("evaluation_verdict") + 1 :]),
        False,  # nothing follows the last round's verdict
    ]
    assert promised == expansion_gates_after, (
        f"the card promised an expansion {promised} but the engine ran one "
        f"{expansion_gates_after} — the promise and the guard have drifted"
    )
    assert "THE RUN ENDS" in verdicts[-1]["consequences"][0], (
        f"the last round's verdict card does not say the run ends: "
        f"{verdicts[-1]['consequences'][0]}"
    )
    print(
        f"  verdict card: promised an expansion in round(s) "
        f"{[i for i, p in enumerate(promised) if p]}, and the engine ran one there"
    )

    print(
        "EXPANSION SMOKE OK — diagnostics requested, run and persisted; proposal "
        "made once; gate paused once; the missing mechanism recovered in round 1"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
