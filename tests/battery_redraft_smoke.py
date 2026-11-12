"""Failed S3 checks reach their author, then a person, via the file-gate protocol.

  reask (a)  a formula naming a missing symbol re-asks observation once;
        (a') an override naming a missing symbol re-asks condition only;
  gate  (b)  a spent seam budget pauses at S3; `fallback:` is applied and signed;
        (c)  `redraft:` words reach the agent under human_feedback, uncharged;
        (f)  an axis in an invented shape is dropped, returned, and on the card.

    uv run python tests/battery_redraft_smoke.py --only reask|gate
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO))

from _harness import check, finish  # noqa: E402
from file_gate_loop import drive  # noqa: E402

from octomod import config  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.assembly.petab_io import table_text  # noqa: E402
from tests._record import ledger_rows, rnd, run_root, work  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR


def _ledger(root: Node) -> list[dict]:
    return ledger_rows(root)


def _calls_of(root: Node, role: str) -> Node:
    """`rounds/round_0/agent_calls/<role>`: what the role was sent and said."""
    return (rnd(root, 0) / "agent_calls").child(role)


def _petab_text(root: Node, table: str) -> str:
    """A table of round 0's fitted problem, as the TSV text PEtab reads."""
    return table_text((work(root, 0) / "petab" / table).table())


def _calls(rows: list[dict], role: str) -> int:
    return sum(
        1 for e in rows if e.get("event") == "agent_call" and e.get("role") == role
    )


def _run(case: str, tag: str, answers=None, collect=None):
    run_id = f"c32_{tag}_{time.strftime('%H%M%S')}"
    rc, gates = drive(case, run_id, answers=answers, collect=collect)
    return rc, gates, run_root(run_id, RUNS)


# ------------------------------------------------------------------ reask


def test_a_observables_resolve_reasks_the_observation_agent_once() -> None:
    rc, gates, root = _run("toy_phos_battery", "a")
    rows = _ledger(root)
    check("(a) the run completes", rc == 0, f"exit {rc}; gates {gates}")
    reasks = [e for e in rows if e.get("event") == "redraft_attributed"]
    check(
        "(a) exactly one redraft_attributed row, for the right gate and role",
        len(reasks) == 1
        and reasks[0]["gate_id"] == "assembly_observables_resolve"
        and reasks[0]["role"] == "observation",
        str([(e.get("gate_id"), e.get("role")) for e in reasks]),
    )
    check(
        "(a) observation called twice, construction and condition once",
        _calls(rows, "observation") == 2
        and _calls(rows, "construction") == 1
        and _calls(rows, "condition") == 1,
        f"obs {_calls(rows, 'observation')} / constr {_calls(rows, 'construction')} / cond {_calls(rows, 'condition')}",
    )
    prompt = (_calls_of(root, "observation") / "prompt").text()
    check(
        "(a) the re-ask prompt carries the gate detail VERBATIM",
        "assembly_observables_resolve" in prompt
        and "Rp_total" in prompt
        and "battery_feedback" in prompt,
    )
    check("(a) … and the agent's OWN formula line", '"formula": "Rp_total"' in prompt)
    check(
        "(a) no gate paused for it — the budget held",
        "assembly_redraft_budget" not in gates,
        str(gates),
    )
    dec = (rnd(root, 0) / "decisions_md").text()
    check(
        "(a) decisions_md names the re-ask",
        "re-asked **observation** after `assembly_observables_resolve`" in dec,
    )
    obs = _petab_text(root, "observables")
    check(
        "(a) the final problem carries the repaired formula",
        "Rp_total" not in obs and "Rp" in obs,
    )


def test_a_prime_conditions_resolve_reasks_the_condition_agent_only() -> None:
    rc, gates, root = _run("toy_phos_battery_cond", "aprime")
    rows = _ledger(root)
    check("(a') the run completes", rc == 0, f"exit {rc}; gates {gates}")
    reasks = [e for e in rows if e.get("event") == "redraft_attributed"]
    check(
        "(a') one re-ask, of condition after assembly_conditions_resolve",
        len(reasks) == 1
        and reasks[0]["role"] == "condition"
        and reasks[0]["gate_id"] == "assembly_conditions_resolve",
        str([(e.get("gate_id"), e.get("role")) for e in reasks]),
    )
    check(
        "(a') observation NOT re-called",
        _calls(rows, "observation") == 1 and _calls(rows, "condition") == 2,
        f"obs {_calls(rows, 'observation')} / cond {_calls(rows, 'condition')}",
    )
    prompt = (_calls_of(root, "condition") / "prompt").text()
    check(
        "(a') the re-ask carries the check and the agent's own override",
        "assembly_conditions_resolve" in prompt and "Stim" in prompt,
    )


# ------------------------------------------------------------------- gate


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_b_fallback_is_applied_only_on_the_signed_answer() -> None:
    before = _sha(
        REPO / "testcase" / "toy_phos_battery_fallback" / "stubs" / "observation.1.json"
    )
    cards: list[dict] = []
    rc, gates, root = _run(
        "toy_phos_battery_fallback",
        "b",
        answers={"assembly_redraft_budget": ("y", "fallback: additive-noise")},
        collect=cards,
    )
    rows = _ledger(root)
    check(
        "(b) the gate paused AT S3, once, before the cost boundary",
        gates.count("assembly_redraft_budget") == 1
        and gates.index("assembly_redraft_budget")
        < gates.index("assembly_cost_boundary"),
        str(gates),
    )
    card = next((c for c in cards if c["module"] == "assembly_redraft_budget"), {})
    check(
        "(b) the card offered the fallback form and named the declared fallbacks",
        any("fallback: <name>" in f for f in card.get("note_forms", []))
        and any("additive-noise" in ln for ln in card.get("lines", [])),
        str(card.get("note_forms"))[:200],
    )
    check("(b) the run then completes", rc == 0, f"exit {rc}")
    obs = _petab_text(root, "observables")
    par = _petab_text(root, "parameters")
    check(
        "(b) every noiseFormula is the constant placeholder",
        "noiseParameter1_obs_pR" in obs and "noiseParameter2" not in obs,
    )
    check("(b) one sigma_<obs> row", "sigma_obs_pR" in par)
    fbs = [e for e in rows if e.get("event") == "assembly_fallback"]
    check(
        "(b) assembly_fallback ledgered, signed by the human, naming the fallback",
        len(fbs) == 1
        and fbs[0]["fallback"] == "additive-noise"
        and "human" in str(fbs[0]["signed"]).lower(),
        str([(e.get("fallback"), e.get("signed")) for e in fbs]),
    )
    check(
        "(b) the agent's stub reply on disk is byte-identical",
        _sha(
            REPO
            / "testcase"
            / "toy_phos_battery_fallback"
            / "stubs"
            / "observation.1.json"
        )
        == before,
    )
    reply_recorded = (_calls_of(root, "observation") / "reply").get()
    check(
        "(b) the ACCEPTED reply in agent_calls still carries the agent's four-symbol formula",
        reply_recorded["observables"][0]["noise"]["formula"].startswith("s1 + s2"),
    )
    check(
        "(b) the rewritten block is written BESIDE it",
        (_calls_of(root, "observation") / "fallback_applied").exists(),
    )
    check(
        "(b) observation called exactly three times (the fallback bought no call)",
        _calls(rows, "observation") == 3,
        str(_calls(rows, "observation")),
    )
    dec = (rnd(root, 0) / "decisions_md").text()
    check(
        "(b) decisions_md records the fallback and who signed",
        "fallback `additive-noise`" in dec,
    )


def test_c_redraft_words_reach_the_agent_uncharged() -> None:
    rc, gates, root = _run(
        "toy_phos_battery_fallback",
        "c",
        answers={"assembly_redraft_budget": ("y", "redraft: add a scaling factor")},
    )
    rows = _ledger(root)
    check(
        "(c) the run completes after the human's words",
        rc == 0,
        f"exit {rc}; gates {gates}",
    )
    prompt = (_calls_of(root, "observation") / "prompt").text()
    check(
        "(c) the next prompt carries the words verbatim under human_feedback",
        "human_feedback" in prompt and "add a scaling factor" in prompt,
    )
    dossier = (_calls_of(root, "observation") / "dossier").get()
    check(
        "(c) the budget was NOT charged: the dossier still holds the three seam failures and no grant",
        len(dossier["attempts"]) == 3 and not dossier.get("grants"),
        f"{len(dossier['attempts'])} attempts, grants {dossier.get('grants')}",
    )
    check(
        "(c) the human's request is ledgered as the human's",
        any(
            e.get("human_redraft") and "add a scaling factor" in str(e.get("note"))
            for e in rows
        ),
    )
    check(
        "(c) observation called four times: three failed drafts and the redraft",
        _calls(rows, "observation") == 4,
        str(_calls(rows, "observation")),
    )


def test_f_a_dropped_axis_returns_to_its_author_and_is_on_the_card() -> None:
    cards: list[dict] = []
    rc, gates, root = _run("toy_phos_battery_axis", "f", collect=cards)
    rows = _ledger(root)
    check("(f) the run completes", rc == 0, f"exit {rc}; gates {gates}")
    reasks = [
        e
        for e in rows
        if e.get("event") == "redraft_attributed"
        and e.get("gate_id") == "model_space_axes"
    ]
    check(
        "(f) one re-ask for the dropped axis, of observation",
        len(reasks) == 1
        and reasks[0]["role"] == "observation"
        and reasks[0].get("dropped") == ["blot_drift_scaling"],
        str(reasks),
    )
    prompt = (_calls_of(root, "observation") / "prompt").text()
    check(
        "(f) the re-ask names the axis, the reason and the legal kinds",
        "blot_drift_scaling" in prompt
        and "exactly one kind" in prompt
        and "change_scaling" in prompt,
    )
    dropped = (rnd(root, 0) / "space/dropped").get()
    check(
        "(f) the drop is persisted with its author",
        dropped
        and dropped[0]["id"] == "blot_drift_scaling"
        and dropped[0]["declared_by"] == "observation",
        str(dropped)[:160],
    )
    card = next((c for c in cards if c["module"] == "assembly_cost_boundary"), {})
    check(
        "(f) the S3 cost card lists the drop by author and reason",
        any(
            "blot_drift_scaling" in ln and "DROPPED" in ln and "observation" in ln
            for ln in card.get("lines", [])
        ),
        str([ln for ln in card.get("lines", []) if "DROP" in ln])[:200],
    )
    dec = (rnd(root, 0) / "decisions_md").text()
    check(
        "(f) decisions_md names the dropped axis",
        "blot_drift_scaling" in dec and "was dropped" in dec,
    )


def main(argv: list[str]) -> int:
    only = argv[argv.index("--only") + 1] if "--only" in argv else "all"
    if only in ("reask", "all"):
        test_a_observables_resolve_reasks_the_observation_agent_once()
        test_a_prime_conditions_resolve_reasks_the_condition_agent_only()
    if only in ("gate", "all"):
        test_b_fallback_is_applied_only_on_the_signed_answer()
        test_c_redraft_words_reach_the_agent_uncharged()
        test_f_a_dropped_axis_returns_to_its_author_and_is_on_the_card()
    return finish(
        "BATTERY REDRAFT",
        f"BATTERY REDRAFT OK ({only}) — a failed check reaches its author, then a person; nothing ends the run on its own",
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
