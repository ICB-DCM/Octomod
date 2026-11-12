"""The record is complete enough to say what the run did (`completeness.py`).

Each test builds a small record by hand and checks one property:

  1. a module that left everything passes, and a part left out is named, with
     the record key and what it was for;
  2. what is expected follows who produced the slot: an agent's model needs
     its glossary and the agent's prompt and reply, a supplied one does not;
     a candidate round checks every candidate's model;
  3. an agent call on the ledger needs its prompt and reply in the record,
     where its row says or in a copy a re-entry moved aside;
  4. the run-level checks: a completed run needs its intent and its final
     evaluation, a stopped one only what every run has;
  4b. the agents' models: the summary of what the calls ran on, a live call
     without its model named, a run without its declared agent setup named;
  5. the entry is written into the record at its checkpoint and replaced by
     the next check of the same checkpoint; the summary reads them back;
  6. a check never fails the run: a broken record gives an entry with the
     error, and `commit_run` writes the entry before the checkpoint copy;
  7. the next gate card says what the record lacks — in its printed lines and
     in the paused payload — and the decision row records how many gaps it
     showed;
  8. stale entries do not outlive what they describe: a dropped candidate's,
     a re-entered module's, a previous process's ending;
  9. the battery fails a suite whose records carry a gap
     (`run_all.record_gaps`).

    uv run python tests/record_completeness_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import completeness  # noqa: E402
from octomod.result import node as tree  # noqa: E402

SBML = "<sbml/>"


def _model(model, *, glossary: bool = True) -> None:
    model.child("sbml").put_text(SBML)
    model.child("antimony").put_text("model m\nend")
    model.child("parameters").put([{"id": "k", "nominal_value": 1.0}])
    if glossary:
        model.child("glossary").put({"k": {"denotes": "a rate"}})


def _call(r0, role: str) -> None:
    call = r0 / "agent_calls" / role
    call.child("prompt").put_text(f"# {role}\nthe prompt")
    call.child("reply").put({"ok": True})


def _missing(entry: dict) -> list[str]:
    return [m["key"] for m in entry["missing"]]


def test_a_complete_module_passes_and_a_gap_is_named() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        _model(tree.model_node(r0, None))
        (r0 / "model" / "build_report").put({"decisions": []})
        (r0 / "gates" / "model_sbml_valid").put({"passed": True})
        (tree.markers_node(r0, None) / "s1").put({"producer": "agent:construction"})
        _call(r0, "construction")
        Ledger(root.store).append(
            "agent_call",
            role="construction",
            io="rounds/round_0/agent_calls/construction/reply",
        )
        entry = completeness.check(root, "marker:s1", round_idx=0)
        check(
            "a module that left everything has nothing missing",
            entry["missing"] == [] and len(entry["checked"]) >= 6,
            str(entry["missing"]),
        )
        (r0 / "model" / "parameters").delete()
        (r0 / "agent_calls" / "construction" / "prompt").delete()
        entry = completeness.check(root, "marker:s1", round_idx=0)
        miss = _missing(entry)
        check(
            "the parameter table and the agent call it lost are named as missing",
            "rounds/round_0/model/parameters" in miss
            and "rounds/round_0/agent_calls/construction/reply" in miss,
            str(miss),
        )
        check(
            "each gap says what it was for",
            all(m["what"] for m in entry["missing"]),
            str(entry["missing"]),
        )


def test_what_is_expected_follows_the_producer_and_the_round() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        _model(tree.model_node(r0, None), glossary=False)
        (r0 / "gates" / "model_sbml_valid").put({"passed": True})
        (tree.markers_node(r0, None) / "s1").put({"producer": "user-supplied"})
        entry = completeness.check(root, "marker:s1", round_idx=0)
        check(
            "a supplied model needs no glossary and no agent call",
            entry["missing"] == [],
            str(entry["missing"]),
        )
        (r0 / "model" / "antimony").delete()
        entry = completeness.check(root, "marker:s1", round_idx=0)
        check(
            "nor Antimony: a supplied SBML that does not round-trip has none",
            entry["missing"] == [],
            str(entry["missing"]),
        )
        (r0 / "model" / "antimony").put_text("model m\nend")
        (tree.markers_node(r0, None) / "s1").put({"producer": "agent:construction"})
        miss = _missing(completeness.check(root, "marker:s1", round_idx=0))
        check(
            "an agent's model needs its glossary and construction's decisions",
            "rounds/round_0/model/glossary" in miss
            and "rounds/round_0/model/build_report" in miss,
            str(miss),
        )
        check(
            "but no agent call the ledger does not record in this round (a "
            "seeded round carries the producer without calling again)",
            not any("agent_calls" in m for m in miss),
            str(miss),
        )
        (r0 / "model" / "glossary").put({})
        miss = _missing(completeness.check(root, "marker:s1", round_idx=0))
        check(
            "an empty glossary is the reply's content, not a part left out",
            "rounds/round_0/model/glossary" not in miss,
            str(miss),
        )
    with temp_record() as root:
        r0 = rnd(root, 0)
        for cid in ("M0", "M1"):
            _model(tree.model_node(r0, cid))
            (tree.gates_node(r0, cid) / "model_sbml_valid").put({"passed": True})
        (tree.model_node(r0, "M1") / "sbml").delete()
        _model(tree.model_node(r0, "M2_dropped"))
        (tree.model_node(r0, "M2_dropped") / "sbml").delete()
        (tree.markers_node(r0, None) / "s1").put(
            {"producer": "engine", "candidates": ["M0", "M1"]}
        )
        miss = _missing(completeness.check(root, "marker:s1", round_idx=0))
        check(
            "a candidate round checks each candidate its marker names, not the round's",
            miss == ["rounds/round_0/candidates/M1/model/sbml"],
            str(miss),
        )
        (tree.markers_node(r0, None) / "s7").put({})
        (r0 / "evaluation").put({"x": 1})
        (r0 / "evaluation_core").put({"x": 1})
        (r0 / "report_md").put_text("# report")
        miss = _missing(completeness.check(root, "marker:s7", round_idx=0))
        check(
            "a round S7 did not discriminate needs no selection",
            "rounds/round_0/selection" not in miss,
            str(miss),
        )
        (r0 / "evaluation").put({"discrimination": {"winner": "M0"}})
        miss = _missing(completeness.check(root, "marker:s7", round_idx=0))
        check(
            "a round S7 discriminated needs its selection",
            "rounds/round_0/selection" in miss,
            str(miss),
        )
        check(
            "and no decision record when no agent built the model or the assembly",
            "rounds/round_0/decisions_md" not in miss,
            str(miss),
        )


def test_every_agent_call_on_the_ledger_is_kept() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        ledger = Ledger(root.store)
        ledger.append("run_start")
        _call(r0, "construction")
        io = "rounds/round_0/agent_calls/construction/reply"
        ledger.append("agent_call", role="construction", io=io)
        lost = "rounds/round_0/agent_calls/data_extraction/reply"
        ledger.append("agent_call", role="data_extraction", io=lost)
        moved = r0 / "superseded" / "evaluation_20261001_120000" / "agent_calls"
        (moved / "interpretation" / "prompt").put_text("p")
        (moved / "interpretation" / "reply").put({"ok": True})
        aside = "rounds/round_0/agent_calls/interpretation/reply"
        ledger.append("agent_call", role="interpretation", io=aside)
        miss = _missing(completeness.check(root, "gate_pending"))
        check(
            "a call whose prompt and reply never reached the record is named",
            lost in miss,
            str(miss),
        )
        check(
            "a call kept where its row says, or moved aside by a re-entry, is not",
            io not in miss and aside not in miss,
            str(miss),
        )


def _run_meta(root) -> None:
    (root / "run").put(
        {
            "run_id": "x",
            "backend": "stub",
            "workflow_sha": "abc",
            "provenance": {
                "agents": {"backend": "stub", "models": {"default": "opus"}}
            },
        }
    )
    root.child("input").child("description.md").put_text("a note")
    (root / "input_source").put({"source": "testcase/x"})


def test_the_run_level_checks_follow_the_outcome() -> None:
    with temp_record() as root:
        _run_meta(root)
        ledger = Ledger(root.store)
        ledger.append("run_start")
        ledger.append("run_end", outcome="stopped", reason="a gate failed")
        entry = completeness.check(root, "run_end")
        check(
            "a stopped run needs only what every run has",
            entry["missing"] == [],
            str(entry["missing"]),
        )
        ledger.append("run_start")
        ledger.append("run_end", outcome="completed")
        miss = _missing(completeness.check(root, "final"))
        check(
            "a completed run needs its intent, its rounds and the analysis",
            {"intent", "rounds", "analysis"} <= set(miss),
            str(miss),
        )
        with temp_record() as fresh:
            _run_meta(fresh)
            Ledger(fresh.store).append("run_start")
            miss = _missing(completeness.check(fresh, "run_end"))
            check(
                "the run's end row is required where the run has ended",
                "ledger#run_end" in miss,
                str(miss),
            )
        (root / "run").put({"run_id": "x"})
        root.child("input").delete()
        miss = _missing(completeness.check(root, "run_end"))
        check(
            "the run's metadata and its inputs are required",
            "run#backend" in miss and "input" in miss,
            str(miss),
        )


def test_the_models_the_agents_ran_on_are_recorded() -> None:
    from octomod.orchestration import provenance

    rows = [
        {
            "event": "agent_call",
            "role": "construction",
            "backend": "llm",
            "model": "opus",
            "model_resolved": "claude-opus-5-5",
            "effort": "max",
            "models_used": {
                "claude-opus-5-5": {
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cost_usd": 1.5,
                }
            },
        },
        {
            "event": "agent_call",
            "role": "construction",
            "backend": "llm",
            "model": "opus",
            "model_resolved": "claude-opus-5-5",
            "effort": "max",
            "models_used": {
                "claude-opus-5-5": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cost_usd": 0.5,
                }
            },
        },
    ]
    used = provenance.models_used(rows)
    m = used["by_model"]["claude-opus-5-5"]
    check(
        "the summary sums each model's calls, tokens and cost",
        m["calls"] == 2
        and m["input_tokens"] == 11
        and m["output_tokens"] == 22
        and abs(m["cost_usd"] - 2.0) < 1e-9
        and m["roles"] == ["construction"],
        str(m),
    )
    check(
        "and says per role what was asked, what it resolved to and the effort",
        used["by_role"]["construction"]
        == {
            "calls": 2,
            "models": ["claude-opus-5-5"],
            "asked": ["opus"],
            "effort": ["max"],
        },
        str(used["by_role"]),
    )
    with temp_record() as root:
        _run_meta(root)
        ledger = Ledger(root.store)
        ledger.append("run_start")
        _call(rnd(root, 0), "construction")
        io = "rounds/round_0/agent_calls/construction/reply"
        ledger.append("agent_call", role="construction", backend="llm", io=io)
        miss = _missing(completeness.check(root, "gate_pending"))
        check(
            "a live call without the model it ran on is named, as is the summary",
            f"{io}#model" in miss and "models_used" in miss,
            str(miss),
        )
        ledger.append(
            "agent_call", role="construction", backend="llm", model="opus", io=io
        )
        miss = _missing(completeness.check(root, "gate_pending"))
        check(
            "a call whose reply had no usage block is named by the model it "
            "was made with, not flagged",
            sum(m == f"{io}#model" for m in miss) == 1,
            str(miss),
        )
        provenance.write_models_used(root)
        miss = _missing(completeness.check(root, "gate_pending"))
        check(
            "the summary, once written, is found",
            "models_used" not in miss,
            str(miss),
        )
        (root / "run").put({"run_id": "x", "backend": "llm", "workflow_sha": "abc"})
        miss = _missing(completeness.check(root, "run_end"))
        check(
            "a run whose provenance lacks the agents' setup is named",
            "run#provenance.agents" in miss,
            str(miss),
        )


def test_the_entry_is_written_and_read_back() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        (tree.markers_node(r0, None) / "cost").put({})
        completeness.check(root, "marker:cost", round_idx=0, candidate="M0")
        key = "completeness/round_0/cost/M0"
        first = (root / key).get(None)
        check(
            "the entry is in the record under its checkpoint and unit",
            first is not None and first["checkpoint"] == "marker:cost",
            str(first),
        )
        (tree.work_node(r0, "M0") / "cost").put({"median_start_s": 1.0})
        completeness.check(root, "marker:cost", round_idx=0, candidate="M0")
        again = (root / key).get(None)
        check(
            "the next check of the same checkpoint replaces it",
            again["missing"] == [],
            str(again),
        )
        s = completeness.summary(root)
        check(
            "the summary reads every entry back",
            s["checkpoints"] == 1 and s["incomplete"] == [],
            str(s),
        )
        check(
            "and says it in one line",
            "nothing missing" in (completeness.summary_line(root) or ""),
            str(completeness.summary_line(root)),
        )
        check(
            "a checkpoint with nothing declared for it writes no entry",
            completeness.check(root, "marker:candidate_compile", round_idx=0) is None
            and completeness.check(root, "not_a_checkpoint") is None
            and completeness.summary(root)["checkpoints"] == 1,
        )


def test_a_check_never_fails_the_run() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        (tree.markers_node(r0, None) / "s6").put({})

        def broken(*_a, **_k):
            raise RuntimeError("a rule that cannot read this record: bad\x00byte")

        real = completeness.MODULE_CHECKS["s6"]
        completeness.MODULE_CHECKS["s6"] = broken
        try:
            entry = completeness.check(root, "marker:s6", round_idx=0)
        finally:
            completeness.MODULE_CHECKS["s6"] = real
        check(
            "a rule that raises gives an entry with its error, not an exception",
            entry is not None and "cannot read this record" in str(entry["error"]),
            str(entry),
        )
        check(
            "and the error is in the record, where the summary counts it, "
            "NUL byte and all (written as every artifact is)",
            len(completeness.summary(root)["errors"]) == 1
            and "bad" in str((root / "completeness/round_0/s6/_round").get(None)),
        )
        (tree.work_node(r0, None) / "estimation").put_table(pd.DataFrame({"a": []}))
        miss = _missing(completeness.check(root, "marker:s6", round_idx=0))
        check(
            "an empty table is not a fit summary",
            "rounds/round_0/candidates/_single/estimation" in miss,
            str(miss),
        )
        (r0 / "data" / "report").put({"columns": ["t", "y"], "n_rows": 3})
        miss = _missing(completeness.check(root, "marker:s2", round_idx=0))
        check(
            "a dict that carries a `columns` key is not taken for an empty table",
            "rounds/round_0/data/report" not in miss,
            str(miss),
        )
    with temp_record() as root:
        r0 = rnd(root, 0)
        (tree.markers_node(r0, None) / "s2").put({"producer": "engine"})
        from octomod.result.autocommit import commit_run

        commit_run(root.store, None, why="marker:s2", round_idx=0)
        backup = root.store.backup_path
        from octomod.result.runstore import RunStore

        copy = tree.root(RunStore(backup)) if backup.exists() else None
        check(
            "commit_run writes the entry before the checkpoint copy is taken",
            copy is not None and (copy / "completeness/round_0/s2/_round").exists(),
            str(backup),
        )


def test_the_next_gate_card_says_what_the_record_lacks() -> None:
    from octomod.orchestration.interaction import humangate

    with temp_record() as root:
        r0 = rnd(root, 0)
        (tree.markers_node(r0, None) / "s2").put({"producer": "engine"})
        completeness.check(root, "marker:s2", round_idx=0)
        lines, gaps = completeness.card_lines(root)
        check(
            "the card lines name each missing part after its checkpoint",
            lines
            and lines[0].startswith("⚠ RECORD INCOMPLETE")
            and any(
                "after marker:s2: rounds/round_0/data/measurements" in x for x in lines
            )
            and any("./run.sh status --run-id" in x for x in lines),
            str(lines),
        )
        check(
            "and the gaps travel as data for the payload",
            [g["key"] for g in gaps]
            == ["rounds/round_0/data/measurements", "rounds/round_0/data/report"],
            str(gaps),
        )
        # a paused card (file mode): the payload carries the gaps and the
        # printed lines; an auto-approved one ledgers how many it showed
        ledger = Ledger(root.store)
        humangate.configure_questions(root)
        humangate.configure_file_mode(root, None)
        try:
            humangate.ask(
                "Go on?", ["some evidence"], ledger=ledger, module="assembly_test"
            )
            payload = None
        except humangate.GatePending as g:
            payload = g.payload
        finally:
            humangate._FILE_MODE.update(enabled=False, root=None)
        check(
            "a paused card's payload carries the gaps and their lines",
            payload is not None
            and len(payload["record_gaps"]) == 2
            and any(str(x).startswith("⚠ RECORD INCOMPLETE") for x in payload["lines"]),
            str(payload and payload.get("record_gaps")),
        )
        humangate.ask("Go on?", [], ledger=ledger, module="assembly_test", auto=True)
        row = [r for r in root.store.ledger_rows() if r.get("event") == "human_gate"][
            -1
        ]
        check(
            "the decision row records how many gaps the card showed",
            row.get("record_gaps") == 2,
            str(row),
        )
        humangate.configure_questions(None)
    with temp_record() as root:
        check(
            "a complete record puts nothing on the card",
            completeness.card_lines(root) == ([], []),
        )


def test_stale_entries_do_not_outlive_what_they_describe() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        for cid in ("M0", "M1"):
            (tree.markers_node(r0, cid) / "s6").put({})
            completeness.check(root, "marker:s6", round_idx=0, candidate=cid)
        check(
            "two candidates' fits missing are two gaps",
            len(completeness.summary(root)["incomplete"]) == 2,
        )
        (r0 / "space" / "dropped").put([{"id": "M1", "why": "below the floor"}])
        check(
            "a candidate its round dropped no longer counts",
            [e["candidate"] for e in completeness.summary(root)["incomplete"]]
            == ["M0"],
            str(completeness.summary(root)["incomplete"]),
        )
        conv = tree.work_node(r0, "M0") / "decisions" / "estimation_convergence"
        conv.put({"approved": True, "at": "now"})  # no `signed`: a gap
        completeness.check(
            root,
            "decision:estimation_convergence",
            round_idx=0,
            candidate="M0",
            subject=conv.key,
        )
        scope = r0 / "decisions" / "assembly_scope"
        scope.put({"approved": True, "signed": "human", "at": "now"})
        completeness.check(root, "decision:assembly_scope", round_idx=0)
        completeness.forget(root, 0, ["s6", "s7"])
        left = completeness.entries(root)
        check(
            "a re-entry's invalidated modules leave no entries behind, their "
            "decisions' included",
            [e["checkpoint"] for e in left] == ["decision:assembly_scope"],
            str([e["checkpoint"] for e in left]),
        )
        completeness.check(root, "run_end")
        completeness.forget_run(root)
        check(
            "a new start drops how the previous process ended",
            not (root / "completeness" / "run").exists(),
        )


def test_the_battery_fails_a_suite_with_a_gap() -> None:
    import run_all

    with temp_record("gappy") as root:
        r0 = rnd(root, 0)
        (tree.markers_node(r0, None) / "s2").put({"producer": "engine"})
        completeness.check(root, "marker:s2", round_idx=0)
        gaps = run_all.record_gaps(root.store.path.parent)
        check(
            "the record a suite left is read for its gaps",
            any("data/measurements" in g for g in gaps),
            str(gaps),
        )
    check(
        "a folder with no records has none",
        run_all.record_gaps(REPO / "docs") == [],
    )


def main() -> int:
    test_a_complete_module_passes_and_a_gap_is_named()
    test_what_is_expected_follows_the_producer_and_the_round()
    test_every_agent_call_on_the_ledger_is_kept()
    test_the_run_level_checks_follow_the_outcome()
    test_the_models_the_agents_ran_on_are_recorded()
    test_the_entry_is_written_and_read_back()
    test_a_check_never_fails_the_run()
    test_the_next_gate_card_says_what_the_record_lacks()
    test_stale_entries_do_not_outlive_what_they_describe()
    test_the_battery_fails_a_suite_with_a_gap()
    return finish(
        "\nRECORD COMPLETENESS",
        "\nRECORD COMPLETENESS OK — each checkpoint names what it needs, follows "
        "who produced it, keeps every agent call, and never fails a run",
    )


if __name__ == "__main__":
    sys.exit(main())
