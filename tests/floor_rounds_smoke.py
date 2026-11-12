"""The support floor across expansion rounds, end to end through file gates,
token-free and offline.

The fixture `abcd_expansion_knowledge` holds the knowledge module's output
(its `knowledge/`, made by the stub module) and the person's floor, high, with
a step of one band. The intent requires the RegB-catalysed conversion of the
precursor. Round 0's base is the designed module, every reaction graded high.
At round 0's expansion the expansion agent asks for a targeted search about a
product-driven inactivation of active KinA, which finds it in one
correlational remark (weak), then proposes three axes: the product
inactivating active RegB (described in a related module, medium), the product
inactivating active KinA (nothing in the dossier reaches a floor), and the
removal of the required conversion. Round 1's agent proposes the KinA axis
again.

  1. round 0 runs at the floor high, the person's;
  2. the first expansion card shows round 1's floor from the schedule, medium,
     with the forms `floor:`, `step:` and `search:`; the RegB axis is offered,
     the KinA axis refused by name after the agent's own search, and the
     removal axis refused by name as the removal of a required reaction;
  3. the answer `floor: low, step: 2` is read back and recorded as the
     person's: round 1's `space/floor` is low, step 2, source human;
  4. the refusals are on the record: `axis_refused_floor`, the round's
     `axis_refused`, `axis_refused_required`;
  5. the second expansion card shows round 2's floor from the schedule, low
     lowered by the person's step to none, where the KinA axis is offered; the
     answer `n` ends the run and leaves no round 2 behind;
  6. ANALYSIS holds "Where the model came from": each round's counts by origin
     and band, the floor's history, the search and the refused axis;
  7. a copy whose expansion agent asks for no search: the person's `search:`
     at the card spends the round's one search (asked by the person), the card
     is asked again with what it found and the search spent, and the answer
     `n` leaves no round 1 behind.

The two runs are concurrent; the copy lives in a temporary directory.

    uv run python tests/floor_rounds_smoke.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check, finish, remove_checked  # noqa: E402
from file_gate_loop import drive_cards  # noqa: E402

from octomod import config  # noqa: E402
from octomod.workflow_modules.knowledge import reaction_evidence as rxe  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    reports_dir,
    rnd,
    run_root,
    run_store,
)

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR

CASE = REPO / "testcase" / "abcd_expansion_knowledge"
REGB, KINA, REMOVAL = (
    "product_inactivates_regb",
    "product_inactivates_kina",
    "no_regb_route",
)
# the answers the front end gives, per gate, in order
ANSWERS = {
    "model_scope": [("y", "axes: product_feedback"), ("y", "")],
    "evaluation_verdict": [("y", "expand: yes"), ("y", "expand: yes")],
    "revision": [("y", "floor: low, step: 2"), ("n", "")],
}
# the copy's answers: the person's search at the first card, then no
QUESTION = "Is ProD described as inactivating active KinA without being consumed?"
SEARCH_ANSWERS = {
    "model_scope": [("y", "axes: product_feedback")],
    "evaluation_verdict": [("y", "expand: yes")],
    "revision": [("y", f"search: {QUESTION}"), ("n", "")],
}
KINA_REFUSED = (
    f"axis {KINA}: adds J8 Aa + D -> D — inferred (nothing in the dossier) is below "
    f"the floor {{band}}; a search may raise it"
)


def _events(rows: list[dict], event: str, round_idx: int | None = None) -> list[dict]:
    return [
        e
        for e in rows
        if e.get("event") == event
        and (round_idx is None or e.get("round") == round_idx)
    ]


def _lines(card: dict) -> list[str]:
    return [str(x) for x in (card.get("lines") or []) + (card.get("always_show") or [])]


def make_no_agent_search(where: Path) -> Path:
    """The fixture without the expansion agent's search request: its proposal
    comes first, and the person may spend the round's search."""
    case = where / "abcd_expansion_knowledge_person_search"
    shutil.copytree(CASE, case)
    stubs = case / "stubs"
    (stubs / "revision.1.json").unlink()
    for k in (2, 3, 4):
        (stubs / f"revision.{k}.json").rename(stubs / f"revision.{k - 1}.json")
    return case


def check_fixture(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    rows = ledger_rows(root)
    r0, r1 = rnd(root, 0), rnd(root, 1)
    ends = _events(rows, "run_end")
    check(
        "the run ends at the second expansion card's no, after two rounds and "
        "two expansion cards",
        rc in (0, 1)
        and modules.count("revision") == 2
        and len(ends) == 1
        and str(ends[0].get("outcome")).startswith("completed"),
        f"exit {rc}, {modules}: {tail[-400:]}",
    )
    check(
        "1. round 0 runs at the floor high, the person's",
        (r0 / rxe.FLOOR_KEY).get(None) == {"band": "high", "step": 1, "source": "human"}
        and [(e.get("band"), e.get("source")) for e in _events(rows, "floor_set", 0)]
        == [("high", "human")],
        str((r0 / rxe.FLOOR_KEY).get(None)),
    )
    offers = [c for c in cards if c.get("module") == "revision"]
    first = _lines(offers[0]) if offers else []
    forms = [str(f) for f in (offers[0].get("note_forms") if offers else []) or []]
    check(
        "2. the first expansion card names round 1's floor from the schedule, "
        "medium, and declares the forms floor:, step: and search:",
        any(
            x.startswith(
                "SUPPORT FLOOR for round 1: medium (the schedule: high lowered by 1)"
            )
            for x in first
        )
        and any(f.startswith("floor: <band|none>") for f in forms)
        and any(f.startswith("step: <n>") for f in forms)
        and any(f.startswith("search: <question>") for f in forms),
        "\n".join(x for x in first if "FLOOR" in x) + " | " + str(forms)[:300],
    )
    proposed = first[
        : next((i for i, x in enumerate(first) if "REACTIONS each" in x), len(first))
    ]
    check(
        "   … the RegB axis is offered; the KinA axis is refused by name, after "
        "the agent's own search found it at weak",
        any(f"{REGB} [structure]" in x for x in proposed)
        and not any(f"{KINA} [structure]" in x for x in proposed)
        and any(KINA_REFUSED.format(band="medium") in x for x in first)
        and any(
            x.startswith("The agent asked for a targeted search (knowledge_search/1)")
            and "nothing admitted at floor medium" in x
            for x in first
        ),
        "\n".join(x for x in first if KINA in x or "targeted search" in x),
    )
    check(
        "   … the removal of the required conversion is refused by name, and "
        "the card says only the intent removes it",
        any(
            x.strip().startswith(f"· DROPPED {REMOVAL}:")
            and "the required reaction req_1 -> D" in x
            and "only when the intent's required_reactions is edited" in x
            for x in first
        ),
        "\n".join(x for x in first if REMOVAL in x),
    )
    searches = _events(rows, "knowledge_search", 0)
    check(
        "   … the agent's search is the knowledge role's, asked by the "
        "expansion, frozen at knowledge_search/1",
        len(searches) == 1
        and searches[0].get("requested_by") == "revision"
        and searches[0].get("admitted") == []
        and ((r0 / rxe.SEARCH_KEY / "1").get(None) or {}).get("requested_by")
        == "revision",
        json.dumps(searches)[:300],
    )
    reads = [
        e
        for e in _events(rows, "note", 0)
        if "read from the human's note" in str(e.get("note"))
        and (e.get("note_read") or {}).get("floor")
    ]
    check(
        "3. `floor: low, step: 2` is read back and recorded as the person's",
        reads
        and reads[-1].get("note_read") == {"floor": "low", "step": 2}
        and (r1 / rxe.FLOOR_KEY).get(None)
        == {"band": "low", "step": 2, "source": "human"}
        and [(e.get("band"), e.get("source")) for e in _events(rows, "floor_set", 1)]
        == [("medium", "schedule"), ("low", "human")],
        json.dumps([e.get("note_read") for e in reads])
        + " "
        + str((r1 / rxe.FLOOR_KEY).get(None)),
    )
    refused = _events(rows, "axis_refused_floor", 0)
    record = (r0 / rxe.AXIS_REFUSED_KEY).get(None) or []
    required = _events(rows, "axis_refused_required", 0)
    check(
        "4. the refusals are on the record: one `axis_refused_floor` row at "
        "the floor the answer left, the round's `axis_refused`, one "
        "`axis_refused_required` row",
        [
            (e.get("axis"), e.get("reaction"), e.get("band"), e.get("floor"))
            for e in refused
        ]
        == [(KINA, "J8", "none", "low")]
        and [(x.get("axis"), x.get("for_round"), x.get("floor")) for x in record]
        == [(KINA, 1, "low")]
        and [(e.get("axis"), e.get("required")) for e in required]
        == [(REMOVAL, ["req_1"])],
        json.dumps({"rows": refused, "required": required})[:500],
    )
    exp0 = (r0 / "expansion").get(None) or {}
    check(
        "   … round 1 is seeded with the RegB axis alone, and the decision "
        "records the floor and the refused axis",
        [a.get("id") for a in (r1 / "space/axes").get(None) or []] == [REGB]
        and exp0.get("floor") == {"band": "low", "step": 2, "source": "human"}
        and exp0.get("refused_for_floor") == [KINA],
        json.dumps({k: exp0.get(k) for k in ("axes", "floor", "refused_for_floor")}),
    )
    second = _lines(offers[1]) if len(offers) > 1 else []
    exp1 = (r1 / "expansion").get(None) or {}
    check(
        "5. the second card: round 2's floor is the schedule's, low lowered by "
        "the person's step to none, and the KinA axis is offered",
        any(
            x.startswith(
                "SUPPORT FLOOR for round 2: none (the schedule: low lowered by 2)"
            )
            for x in second
        )
        and any(f"{KINA} [structure]" in x for x in second)
        and not any("REFUSED" in x for x in second)
        and [
            (e.get("band"), e.get("step"), e.get("source"))
            for e in _events(rows, "floor_set", 2)
        ]
        == [("none", 2, "schedule")],
        "\n".join(x for x in second if "FLOOR" in x or KINA in x),
    )
    check(
        "   … the no leaves no round 2 behind; the decision keeps the floor",
        not rnd(root, 2).exists()
        and exp1.get("expanded") is False
        and exp1.get("floor") == {"band": "none", "step": 2, "source": "schedule"},
        json.dumps({k: exp1.get(k) for k in ("expanded", "floor")}),
    )
    origin = ((root / "analysis").get(None) or {}).get("model_origin") or {}
    by_round = {r.get("round"): r for r in origin.get("rounds") or []}
    check(
        '6. ANALYSIS holds "Where the model came from": counts by origin and '
        "band per round, the floor's history, the search, the refused axis",
        set(by_round) == {0, 1}
        and (by_round[0].get("by_origin") or {}).get("human") == 1
        and (by_round[0].get("by_origin") or {}).get("knowledge") == 5
        and by_round[0].get("by_band") == {"high": 6}
        and [
            (h.get("band"), h.get("source"))
            for h in by_round[1].get("floor_history") or []
        ]
        == [("medium", "schedule"), ("low", "human")]
        and [
            (s.get("round"), s.get("requested_by"))
            for s in origin.get("searches") or []
        ]
        == [(0, "revision")]
        and [x.get("axis") for x in origin.get("refused") or []] == [KINA]
        and "Where the model came from"
        in (reports_dir(root) / "ANALYSIS.html").read_text(),
        json.dumps(origin)[:600],
    )
    prompt = (r0 / "agent_calls/revision/prompt").text("")
    check(
        "   the expansion agent was shown the floor it proposes under and the "
        "question its search answered",
        "## support_floor" in prompt
        and '"band": "medium"' in prompt[prompt.find("## support_floor") :][:400]
        and "is REFUSED from the offer" in prompt
        and "## research_answered" in prompt,
        prompt[prompt.find("## support_floor") :][:300],
    )
    from octomod.result.access import record_for

    typed = record_for(root).rounds["round_0"]
    check(
        "   the typed record reads the refusals and the offer's floor",
        [x.get("axis") for x in typed.axis_refused or []] == [KINA]
        and typed.expansion is not None
        and (typed.expansion.floor or {}).get("band") == "low"
        and typed.expansion.refused_for_floor == [KINA],
    )


def check_person_search(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    offers = [c for c in cards if c.get("module") == "revision"]
    check(
        "7. the person's search: the card is asked twice in round 0, and the no "
        "ends the run",
        rc in (0, 1) and len(offers) == 2 and modules.count("evaluation_verdict") == 1,
        f"exit {rc}, {modules}: {tail[-400:]}",
    )
    first = _lines(offers[0]) if offers else []
    second = _lines(offers[1]) if len(offers) > 1 else []
    searches = _events(rows, "knowledge_search", 0)
    check(
        "   … the first card offers the round's one search; the answer spends it "
        "on the person's question, asked by the person, and reads it back",
        any("targeted search is not spent" in x for x in first)
        and [(e.get("requested_by"), e.get("admitted")) for e in searches]
        == [("human", [])]
        and QUESTION in str(searches[0].get("questions") if searches else "")
        and any(
            "read from the human's note" in str(e.get("note"))
            and (e.get("note_read") or {}).get("search") == QUESTION
            for e in _events(rows, "note", 0)
        ),
        json.dumps(searches)[:300],
    )
    check(
        "   … the card is asked again with what the search found, the search "
        "spent, and the KinA axis still refused at medium",
        any(
            x.startswith("You asked for a targeted search (knowledge_search/1)")
            and "nothing admitted at floor medium" in x
            for x in second
        )
        and any("targeted search is spent" in x for x in second)
        and any(KINA_REFUSED.format(band="medium") in x for x in second),
        "\n".join(x for x in second if "search" in x or KINA in x),
    )
    exp0 = (r0 / "expansion").get(None) or {}
    check(
        "   … the no leaves no round 1 behind; the decision keeps the floor and "
        "the refusal",
        not rnd(root, 1).exists()
        and exp0.get("expanded") is False
        and exp0.get("floor") == {"band": "medium", "step": 1, "source": "schedule"}
        and exp0.get("refused_for_floor") == [KINA],
        json.dumps(
            {k: exp0.get(k) for k in ("expanded", "floor", "refused_for_floor")}
        ),
    )


def main() -> int:
    t0 = time.time()
    stamp = time.strftime("%H%M%S")
    where = Path(tempfile.mkdtemp(prefix="octomod_floorrounds_"))
    runs = {
        "fixture": (f"floorrounds_{stamp}", CASE, ANSWERS),
        "search": (
            f"floorrounds_search_{stamp}",
            make_no_agent_search(where),
            SEARCH_ANSWERS,
        ),
    }
    passed = False
    try:
        with ThreadPoolExecutor(max_workers=len(runs)) as pool:
            futures = {
                key: pool.submit(drive_cards, case, rid, script, max_gates=30)
                for key, (rid, case, script) in runs.items()
            }
            results = {key: f.result() for key, f in futures.items()}
        print("the fixture, through two expansion cards")
        check_fixture(runs["fixture"][0], results["fixture"])
        print("the person's search at the expansion card")
        check_person_search(runs["search"][0], results["search"])
        passed = not FAILS
    finally:
        # a failing run's records are its evidence: run_all keeps them
        for rid, _case, _script in runs.values() if passed else ():
            remove_checked(run_store(rid, RUNS))
        shutil.rmtree(where, ignore_errors=True)
    return finish(
        "FLOOR ROUNDS",
        f"FLOOR ROUNDS OK — the floor per round by the schedule and the person, "
        f"axes refused below it and for a required reaction, the expansion's "
        f"search, the record and ANALYSIS ({time.time() - t0:.0f}s)",
    )


if __name__ == "__main__":
    sys.exit(main())
