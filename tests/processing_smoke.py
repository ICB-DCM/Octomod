"""Blank subtraction, through the file-gate driver on `toy_phos_blank`.

The data carry a ~0.5 AU membrane background and blank lanes at dose 0;
`data_extraction.1.json` names the HELD-OUT `dose=3` as its blank reference,
`.2.json` names `dose=0`.

  1. the held-out reference is refused by name and data_extraction is re-asked;
  2. `data/measurements` is raw minus the matching blank lane; raw is preserved;
  3. the data signals and the observation agent's prompt see the processed data;
  4. the op is on the S3 cost card and in decisions_md.

    uv run python tests/processing_smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

from _harness import check, finish  # noqa: E402
from file_gate_loop import drive  # noqa: E402

from octomod import config  # noqa: E402
from tests._record import ledger_rows, rnd, run_root, work  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR


def main() -> int:
    cards: list[dict] = []
    run_id = f"c34_blank_{time.strftime('%H%M%S')}"
    rc, gates = drive("toy_phos_blank", run_id, collect=cards)
    root = run_root(run_id, RUNS)
    r0 = rnd(root, 0)
    calls = r0 / "agent_calls"
    rows = ledger_rows(root)
    end = [e for e in rows if e.get("event") == "run_end"]
    outcome = end[-1].get("outcome") if end else None
    # `completed_t2prime_unmet` is an honest verdict here: a subtracted mean blank
    # injects an error shared by every lane at a time point, which the within-cell
    # replicate floor cannot see, so the held-out T2' check reads it as misfit.
    check(
        "the run reaches the verdict and ends honestly",
        "evaluation_verdict" in gates
        and outcome in ("completed", "completed_t2prime_unmet"),
        f"exit {rc}; outcome {outcome}; gates {gates}",
    )
    t2 = [
        e
        for e in rows
        if e.get("event") == "gate" and e.get("gate_id") == "evaluation_t2prime_holdout"
    ]
    check(
        "the held-out condition was evaluated (on the processed rows)",
        bool(t2) and "dose_3" in str(t2[-1].get("detail")),
        str(t2[-1].get("detail"))[:120] if t2 else "no T2' row",
    )
    # (c) the held-out reference was refused by name and went back to its author
    reasks = [
        e
        for e in rows
        if e.get("event") == "redraft_attributed" and e.get("module") == "data"
    ]
    check(
        "(c) one re-ask of data_extraction after data_processing_legal",
        len(reasks) == 1
        and reasks[0]["role"] == "data_extraction"
        and reasks[0]["gate_id"] == "data_processing_legal",
        str([(e.get("gate_id"), e.get("role")) for e in reasks]),
    )
    prompt = (calls.child("data_extraction") / "prompt").text()
    check(
        "(c) the re-ask names the held-out label, the rule and the usable references",
        "dose=3" in prompt
        and "HELD-OUT" in prompt
        and "dose=0" in prompt
        and "battery_feedback" in prompt,
    )
    check(
        "(c) … and carries the agent's own processing block verbatim",
        '"kind": "subtract_reference"' in prompt and "held-out dose=3" in prompt,
    )
    gate_rows = [
        e
        for e in rows
        if e.get("event") == "gate" and e.get("gate_id") == "data_processing_legal"
    ]
    check(
        "(c) the processing gate is in the ledger: refused, then passed",
        len(gate_rows) >= 2
        and gate_rows[0]["passed"] is False
        and gate_rows[-1]["passed"] is True,
        str([g["passed"] for g in gate_rows]),
    )
    # (a) processed = raw - matching blank lane; raw preserved; holdout rows processed alike
    raw = (r0 / "data/raw").table()
    proc = (r0 / "data/measurements").table()
    check(
        "(a) data/raw preserved with the same rows",
        len(raw) == len(proc) and "processing_reference" not in raw.columns,
    )
    blank = raw[raw["condition_label"] == "dose=0"].groupby("time")["value"].mean()
    worst = 0.0
    keyed = ["condition_label", "time", "replicate"]
    for r_raw, r_proc in zip(
        raw.sort_values(keyed).itertuples(),
        proc.sort_values(keyed).itertuples(),
        strict=False,
    ):
        expected = r_raw.value - blank.loc[r_raw.time]
        worst = max(worst, abs(r_proc.value - expected))
    check(
        "(a) every processed value is raw minus the mean blank lane at the same time",
        worst < 1e-9,
        f"max |Δ| = {worst:.2e}",
    )
    held = proc[proc["condition_label"] == "dose=3"]
    check(
        "(a) the held-out condition's rows are in the table and processed identically",
        len(held) > 0 and held["processing_reference"].notna().all(),
    )
    rep = (r0 / "data/report").get()
    check(
        "(a) data/report carries the op with the resolved reference values",
        rep.get("processing")
        and rep["processing"][0]["kind"] == "subtract_reference"
        and rep["processing"][0]["reference"].get("values"),
    )
    petab_hold = (work(root, 0) / "petab/holdout_measurements").table()
    check(
        "(a) the PEtab holdout table carries processed values",
        len(petab_hold) == len(held)
        and np.allclose(sorted(petab_hold["measurement"]), sorted(held["value"])),
    )
    # (e) the signals the observation agent sees were computed on the processed table
    sig = (r0 / "data/signals").get()
    sup = sig["per_observable"]["pR_au"]["support"]
    check(
        "(e) data_signals computed on the PROCESSED table (its min is the processed min)",
        abs(
            sup["min"]
            - round(float(proc[proc["observable_label"] == "pR_au"]["value"].min()), 6)
        )
        < 1e-5,
        f"signals min {sup['min']} vs processed {proc['value'].min():.6f} / raw {raw['value'].min():.6f}",
    )
    check(
        "(e) processing_applied travels with the signals",
        sig.get("processing_applied")
        and sig["processing_applied"]["ops"][0]["kind"] == "subtract_reference",
    )
    obs_prompt = (calls.child("observation") / "prompt").text()
    check(
        "(e) … and reaches the observation agent's archived prompt",
        "processing_applied" in obs_prompt and "subtract_reference" in obs_prompt,
    )
    # visibility: the S3 cost card and decisions_md
    card = next((c for c in cards if c["module"] == "assembly_cost_boundary"), {})
    check(
        "the S3 cost card lists the op with its reference",
        any("processing:" in ln and "dose=0" in ln for ln in card.get("lines", [])),
        str([ln for ln in card.get("lines", []) if "processing" in ln])[:160],
    )
    dec = (r0 / "decisions_md").text()
    check(
        "decisions_md carries the op and its rationale",
        "subtract_reference" in dec and "blank lanes" in dec,
    )
    return finish(
        "PROCESSING SMOKE",
        "PROCESSING SMOKE OK — a held-out reference refused by name, the blank subtracted by the engine, every consumer shows it",
    )


if __name__ == "__main__":
    sys.exit(main())
