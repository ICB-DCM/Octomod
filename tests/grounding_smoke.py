"""The knowledge module inside a run, end to end: construction builds the base
from the essential set; a base that names what it lacks gets a targeted
search, and what reaches the support floor is admitted; a second failure
lowers the floor one band; a third goes to the person. Driven through file
gates, as the front end drives a run, token-free and offline.

The fixture `toy_phos_knowledge` holds the knowledge module's output (its
`knowledge/`, made by the stub module) and the person's floor, medium.
Construction's first draft writes the ligand as a species: it does not
implement the required R -> Rp, carries L + R -> L + Rp outside the set, and
names that conversion in `missing`. The targeted search returns it graded
medium, it is admitted, and the second draft holds the ligand as the dose
parameter L, which implements the required reaction and the admitted one.
Every source is a fixture document fetched over `file:`, which the citation
check reads as not checkable, so every grade is deterministic.

  (a) the fixture: the usual single-model gate sequence; the fence and floor
      rows; one search, one admission, recorded with origin `search`;
      `model_essential_reactions` failing then passing, `model_connected` passing;
      the redraft's prompt carrying the failure and the admitted reaction;
      the annotation's origins; the scope card, the decision record, the
      model report and the run page;
  (b) the search finds the conversion at low: not admitted at medium; the
      second failure lowers the floor to low, the search is read again at it
      (no second call), the conversion is admitted, and the run completes;
  (c) the searches find nothing usable, twice: the third failure pauses at
      the exhaustion gate, whose card carries the floor's history and both
      searches; answered `floor: none`, the floor is the person's, the
      searches are read again at it and the fourth draft passes;
  (d) a second draft with a species no reaction touches fails `model_connected`
      by name, is redrafted on the budget, and the run completes;
  (e) advisory mode: the first draft is the fixture's second plus a receptor
      loss nothing in the dossier describes and a turnover the dossier grades
      below the floor; it passes, no search runs, the annotation labels the
      loss inferred, and the scope card flags both.

The fixture declares `mode: strict`, which (a)–(d) test; (e) declares
advisory. The variants are temporary copies of the fixture and run
concurrently.

    uv run python tests/grounding_smoke.py
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check, finish, remove_checked  # noqa: E402
from file_gate_loop import drive_cards  # noqa: E402

from octomod import config  # noqa: E402
from octomod.workflow_modules.knowledge import reaction_evidence as rxe  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    reports_dir,
    rnd,
    run_root,
    run_store,
)

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR

CASE = REPO / "testcase" / "toy_phos_knowledge"
# the pauses of a single-model prediction round, in order; the knowledge
# module adds none inside the run
SEQUENCE = [
    "intent",
    "model_scope",
    "assembly_cost_boundary",
    "cost_boundary_estimation",
    "evaluation_verdict",
]
EXHAUSTION = "model_redraft_budget"
ADMITTED = "r0s1_rx_1"
# the words `model_essential_reactions` hands back to construction
MISSING = "essential reaction req_1 (R -> Rp, origin human) is in no model reaction"
OUTSIDE = "model reaction J1 L + R -> L + Rp is not in the essential set"


def _stub(case: Path, name: str) -> dict:
    return json.loads((case / "stubs" / name).read_text())


def _put_stub(case: Path, name: str, reply: dict) -> None:
    (case / "stubs" / name).write_text(json.dumps(reply, indent=2))


def _variant(where: Path, name: str) -> Path:
    """A temporary copy of the fixture under its own name, its staged
    knowledge module included."""
    case = where / name
    shutil.copytree(CASE, case)
    return case


def _cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, "-m", "octomod", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _calls(rows: list[dict], role: str) -> int:
    return sum(
        1 for e in rows if e.get("event") == "agent_call" and e.get("role") == role
    )


def _verdicts(rows: list[dict], gate_id: str) -> list:
    return [
        e.get("passed")
        for e in rows
        if e.get("event") == "gate" and e.get("gate_id") == gate_id
    ]


def _events(rows: list[dict], event: str) -> list[dict]:
    return [e for e in rows if e.get("event") == event]


def _card(cards: list[dict], module: str) -> list[str]:
    card = next((c for c in cards if c.get("module") == module), {})
    return [str(x) for x in card.get("lines") or []]


# ------------------------------------------------------------ the variants


def make_low(where: Path) -> Path:
    """The search finds the conversion at low; the second draft repeats the
    first, the third is the fixture's second."""
    case = _variant(where, "toy_phos_knowledge_low")
    found = _stub(case, "knowledge_targeted.1.json")
    item = found["reactions"][0]["evidence"][0]
    item["evidence_kind"] = "review"
    item["supports"] = "a review of related receptors describes the ligand step"
    _put_stub(case, "knowledge_targeted.1.json", found)
    first = _stub(case, "construction.1.json")
    second = _stub(case, "construction.2.json")
    _put_stub(case, "construction.2.json", first)
    _put_stub(case, "construction.3.json", second)
    return case


def make_nothing(where: Path) -> Path:
    """Both searches find nothing usable: the first returns nothing, the
    second a conversion no source counts for. Every draft keeps the ligand as
    a species; the second names one more conversion missing."""
    case = _variant(where, "toy_phos_knowledge_nothing")
    _put_stub(
        case,
        "knowledge_targeted.1.json",
        {
            "reactions": [],
            "facts": [],
            "queries_run": ["ligand dose receptor phosphorylation (fixture)"],
            "notes": "FIXTURE: nothing found for the question.",
        },
    )
    _put_stub(
        case,
        "knowledge_targeted.2.json",
        {
            "reactions": [
                {
                    "equation": "L + R -> LR",
                    "answers": "q_2",
                    "essential": True,
                    "type": "binding",
                    "description": "ligand binding to the receptor",
                    "evidence": [],
                }
            ],
            "facts": [],
            "queries_run": ["ligand receptor binding (fixture)"],
            "notes": "FIXTURE: the binding step is named, with no source.",
        },
    )
    first = _stub(case, "construction.1.json")
    again = copy.deepcopy(first)
    again["missing"].append(
        {
            "equation": "L + R -> LR",
            "why": "the ligand may act through a bound complex before the "
            "phosphorylation",
        }
    )
    _put_stub(case, "construction.2.json", again)
    _put_stub(case, "construction.3.json", again)
    # after `floor: none` at the exhaustion card the binding step is admitted:
    # the fourth draft holds the ligand as the dose and implements it
    bound = _stub(CASE, "construction.2.json")
    bound["antimony"] = (
        bound["antimony"]
        .replace(
            "  species Rp in cell = 0;\n",
            "  species Rp in cell = 0;\n  species LR in cell = 0;\n",
        )
        .replace(
            "  k_dephos = 0.2;\n",
            "  k_dephos = 0.2;\n  k_bind = 0.01;\n  J3: R -> LR; k_bind * L * R;\n",
        )
    )
    bound["parameters"].append(
        {**bound["parameters"][0], "id": "k_bind", "nominal_value": 0.01}
    )
    bound["entity_glossary"]["species"].append(
        {
            "id": "LR",
            "denotes": "ligand-bound receptor",
            "unit_convention": "same normalised amount scale as R",
            "lump_membership": "LR is the single bound state",
        }
    )
    bound["missing"] = []
    _put_stub(case, "construction.4.json", bound)
    return case


def make_stray(where: Path) -> Path:
    """The second draft is the fixture's second with a species X that no
    reaction touches; the third is the fixture's second."""
    case = _variant(where, "toy_phos_knowledge_stray")
    second = _stub(case, "construction.2.json")
    stray = copy.deepcopy(second)
    stray["antimony"] = stray["antimony"].replace(
        "  species Rp in cell = 0;\n",
        "  species Rp in cell = 0;\n  species X in cell = 1;\n",
    )
    stray["network"]["species"].append(
        {"id": "X", "name": "a species no reaction touches", "compartment": "cell"}
    )
    stray["entity_glossary"]["species"].append(
        {
            "id": "X",
            "denotes": "a stray species",
            "unit_convention": "normalised amount",
            "lump_membership": "X is one pool",
        }
    )
    _put_stub(case, "construction.2.json", stray)
    _put_stub(case, "construction.3.json", second)
    return case


def make_advisory(where: Path) -> Path:
    """Advisory mode; one draft, the fixture's second with J3 R -> (a receptor
    loss, nothing in the dossier) and J4 Rp -> (the survey's rx_2, graded
    weak, below the floor medium), both at fixed rates."""
    import yaml

    case = _variant(where, "toy_phos_knowledge_advisory")
    tc = yaml.safe_load((case / "testcase.yaml").read_text())
    tc["grounding"]["mode"] = "advisory"
    (case / "testcase.yaml").write_text(yaml.safe_dump(tc, sort_keys=False))
    draft = _stub(case, "construction.2.json")
    draft["antimony"] = draft["antimony"].replace(
        "  k_dephos = 0.2;\n",
        "  k_dephos = 0.2;\n  k_loss = 0.0001;\n  k_turn = 0.0001;\n"
        "  J3: R -> ; k_loss * R;\n  J4: Rp -> ; k_turn * Rp;\n",
    )
    for pid in ("k_loss", "k_turn"):
        draft["parameters"].append(
            {
                **draft["parameters"][1],
                "id": pid,
                "nominal_value": 0.0001,
                "estimate": False,
                "source": "a slow loss at a fixed rate",
            }
        )
    _put_stub(case, "construction.1.json", draft)
    (case / "stubs" / "construction.2.json").unlink()
    return case


# ------------------------------------------------------------ (a) the fixture


def check_fixture(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    check("the run completes", rc == 0, "" if rc == 0 else f"exit {rc}: {tail}")
    check(
        "it pauses at the gates of a single-model prediction round, in order",
        modules == SEQUENCE,
        str(modules),
    )
    fence = _events(rows, "grounding_fence")
    check(
        "a `grounding_fence` row at run start: the module online, the floor "
        "medium, set by the person, the step, the horizon and the blocklist",
        fence
        and fence[0].get("module") == "run_start"
        and fence[0].get("mode") == "online"
        and fence[0].get("support_floor") == "medium"
        and fence[0].get("floor_source") == "human"
        and fence[0].get("floor_step") == 1
        and fence[0].get("horizon") == 2025
        and fence[0].get("forbidden_sources") == ["blocked-preprints.example"],
        json.dumps(fence[:1])[:400],
    )
    floors = _events(rows, "floor_set")
    check(
        "one `floor_set` row: round 0's floor, medium, the person's; no floor "
        "was lowered",
        [(e.get("band"), e.get("source")) for e in floors] == [("medium", "human")]
        and not _events(rows, "floor_lowered")
        and (r0 / rxe.FLOOR_KEY).get(None)
        == {"band": "medium", "step": 1, "source": "human"},
        json.dumps(floors)[:300],
    )
    dossier = (r0 / rxe.DOSSIER_KEY).get(None) or {}
    staged = json.loads((CASE / "knowledge" / "knowledge.json").read_text())
    check(
        "the staged dossier is copied into round 0 from the record's input",
        [r.get("id") for r in dossier.get("reactions") or []]
        == [r["id"] for r in staged["reactions"]]
        == ["req_1", "rx_1", "rx_2"]
        and (root / "input" / "knowledge" / "knowledge.json").exists(),
        str([r.get("id") for r in dossier.get("reactions") or []]),
    )
    check(
        "construction twice, the knowledge role once — a targeted search archived "
        "under its own name, served its own stub",
        _calls(rows, "construction") == 2
        and _calls(rows, "knowledge") == 1
        and (r0 / "agent_calls/knowledge_targeted_1/reply").get(None)
        == json.loads((CASE / "stubs" / "knowledge_targeted.1.json").read_text()),
        f"{_calls(rows, 'construction')} construction, "
        f"{_calls(rows, 'knowledge')} knowledge",
    )
    searches = _events(rows, "knowledge_search")
    check(
        "one `knowledge_search` row: its question, one reaction found, one "
        "admitted at floor medium",
        len(searches) == 1
        and searches[0].get("n") == 1
        and searches[0].get("n_found") == 1
        and searches[0].get("n_admitted") == 1
        and searches[0].get("admitted") == [ADMITTED]
        and searches[0].get("floor") == "medium"
        and "L + R -> L + Rp" in str(searches[0].get("questions")),
        json.dumps(searches)[:400],
    )
    search = (r0 / rxe.SEARCH_KEY / "1").get(None) or {}
    found = (search.get("reactions") or [{}])[0]
    check(
        "the search is frozen at rounds/round_0/knowledge_search/1: its "
        "questions, the reaction graded medium with its origin and who asked, "
        "its cost, and what it admitted",
        [q.get("equation") for q in search.get("questions") or []]
        == ["L + R -> L + Rp"]
        and (found.get("id"), found.get("grade"), found.get("origin"))
        == (ADMITTED, "medium", "search")
        and found.get("requested_by") == "construction"
        and "cost" in search
        and search.get("online") is True
        and (search.get("admission") or {}).get("admitted") == [ADMITTED],
        json.dumps({k: search.get(k) for k in ("questions", "admission", "cost")})[
            :400
        ],
    )
    admitted = (r0 / rxe.ADMITTED_KEY).get(None) or []
    check(
        "rounds/round_0/knowledge_admitted holds it: origin search, asked by "
        "construction, the question it answers, the search that found it",
        [a.get("id") for a in admitted] == [ADMITTED]
        and admitted[0].get("origin") == "search"
        and admitted[0].get("requested_by") == "construction"
        and "L + R -> L + Rp" in str(admitted[0].get("answers"))
        and admitted[0].get("search") == 1
        and admitted[0].get("admitted_at") == "medium",
        json.dumps(admitted)[:300],
    )
    check(
        "`model_essential_reactions` failed once, then passed; `model_connected` "
        "passed both times",
        _verdicts(rows, rxe.ESSENTIAL_GATE) == [False, True]
        and _verdicts(rows, "model_connected") == [True, True],
        f"{_verdicts(rows, rxe.ESSENTIAL_GATE)} {_verdicts(rows, 'model_connected')}",
    )
    attempts = ((r0 / "agent_calls/construction/dossier").get(None) or {}).get(
        "attempts"
    ) or [{}]
    grants = ((r0 / "agent_calls/construction/dossier").get(None) or {}).get(
        "grants"
    ) or []
    check(
        "the failed draft is in construction's dossier with what it named "
        "missing and the rung it took; the engine's redraft costs no budget",
        len(attempts) == 1
        and any(MISSING in f for f in attempts[0].get("gate_failures") or [])
        and any(OUTSIDE in f for f in attempts[0].get("gate_failures") or [])
        and attempts[0].get("search_step") == "search"
        and [q.get("equation") for q in attempts[0].get("missing") or []]
        == ["L + R -> L + Rp"]
        and [g.get("why") for g in grants] == ["knowledge_search"],
        json.dumps({"attempts": attempts, "grants": grants})[:400],
    )
    prompt = (r0 / "agent_calls/construction/prompt").text("")
    ess = prompt[prompt.find("## essential_reactions") :][:4000]
    check(
        "the redraft's prompt carries the engine's finding — the failures and "
        "what was admitted — and the base set with the admitted reaction",
        "## engine_feedback" in prompt
        and MISSING in prompt
        and OUTSIDE in prompt
        and "Admitted into the essential set (origin search)" in prompt
        and ADMITTED in ess
        and '"origin": "search"' in ess
        and "## support_floor" in prompt
        and "## grounding_instruction" in prompt,
        prompt[prompt.find("## engine_feedback") :][:600],
    )
    notes = [e for e in rows if e.get("event") == "note" and e.get("engine_redraft")]
    check(
        "the engine's redraft is ledgered as the engine's, never as a person's",
        len(notes) == 1
        and notes[0].get("role") == "construction"
        and not any(e.get("human_redraft") for e in rows if e.get("event") == "note"),
        json.dumps(notes)[:300],
    )
    support = (r0 / "model" / rxe.SUPPORT_KEY).get(None) or {}
    blocks = {
        (r.get("reaction_id"), way): b
        for r in support.get("reactions") or []
        for way, b in (r.get("directions") or {}).items()
        if b
    }
    j1 = blocks.get(("J1", "forward")) or {}
    j2 = blocks.get(("J2", "forward")) or {}
    origins = {x.get("origin") for b in blocks.values() for x in b.get("entries") or []}
    check(
        "model/reaction_support: J1 implements the required req_1 (human) and the "
        "admitted reaction (search), the dose held as a parameter; J2 the "
        "survey's rx_1 (knowledge)",
        [(x.get("id"), x.get("origin")) for x in j1.get("entries") or []]
        == [("req_1", "human"), (ADMITTED, "search")]
        and j1.get("origin") == "human"
        and [(x.get("id"), x.get("origin")) for x in j2.get("entries") or []]
        == [("rx_1", "knowledge")]
        and origins == {"human", "knowledge", "search"}
        and next(r for r in support["reactions"] if r["reaction_id"] == "J1").get(
            "as_parameter"
        )
        == ["L"],
        json.dumps({f"{k[0]} {k[1]}": v for k, v in blocks.items()})[:500],
    )
    lines = _card(cards, "model_scope")
    check(
        "the scope card carries the REACTIONS line, the essential set with its "
        "origins, and the search",
        any(x.startswith("REACTIONS — 2 in the model") for x in lines)
        and any(
            x.startswith("ESSENTIAL SET — the base is built from 3 reaction(s)")
            and "1 human, 1 knowledge, 1 search" in x
            for x in lines
        )
        and any(
            "search 1" in x and f"1 admitted at floor medium: {ADMITTED}" in x
            for x in lines
        ),
        "\n".join(
            x for x in lines if "REACTION" in x or "ESSENTIAL" in x or "search" in x
        ),
    )
    md = (r0 / "decisions_md").text("")
    check(
        "the decision record: the reactions with their origins, and the engine's "
        "redraft",
        "## Reactions and their support" in md
        and "origin human" in md
        and "origin knowledge" in md
        and f"`{ADMITTED}` (origin search" in md
        and "the engine asked construction to redraft" in md,
        md[md.find("## Reactions") :][:500],
    )
    rep = reports_dir(root) / "round_0" / "report"
    model_html = rep / "model_report.html"
    html = model_html.read_text() if model_html.exists() else ""
    check(
        "the model report's block has its anchor and the origins",
        'id="reaction-support"' in html
        and "Where each reaction comes from" in html
        and "origin human" in html
        and f"{ADMITTED} (origin search)" in html,
        str(model_html),
    )
    page = rep / "report.html"
    page_html = page.read_text() if page.exists() else ""
    check(
        "the run page header names the knowledge module, its floor and step",
        "knowledge module online, support floor medium (the person&#x27;s), step 1"
        in page_html
        or "knowledge module online, support floor medium (the person's), step 1"
        in page_html,
        str(page),
    )
    from octomod.result.access import record_for

    typed = record_for(root).rounds["round_0"]
    check(
        "the typed record reads the search, the admitted list and the floor",
        "1" in (typed.knowledge_search or {})
        and [a.get("id") for a in typed.knowledge_admitted or []] == [ADMITTED]
        and typed.space is not None
        and (typed.space.floor or {}).get("band") == "medium",
    )


# ------------------------------------------------------------ (b) found at low


def check_low(rid: str, result) -> None:
    rc, modules, _cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    check(
        "found at low: the run completes with the usual gate sequence",
        rc == 0 and modules == SEQUENCE,
        str(modules) if rc == 0 else f"exit {rc}, {modules}: {tail}",
    )
    searches = _events(rows, "knowledge_search")
    check(
        "… the one search admits nothing at floor medium, and says so",
        len(searches) == 1
        and searches[0].get("n_admitted") == 0
        and "nothing admitted at floor medium" in str(searches[0].get("note"))
        and [b.get("band") for b in searches[0].get("not_admitted") or []] == ["low"],
        json.dumps(searches)[:400],
    )
    lowered = _events(rows, "floor_lowered")
    check(
        "… the second failure lowers the floor one band, medium to low, with why",
        len(lowered) == 1
        and (lowered[0].get("from"), lowered[0].get("to")) == ("medium", "low")
        and "second time" in str(lowered[0].get("why")),
        json.dumps(lowered)[:300],
    )
    check(
        "… space/floor reads low, set by the engine's lowering, beside the "
        "person's first floor",
        (r0 / rxe.FLOOR_KEY).get(None)
        == {"band": "low", "step": 1, "source": "lowered"}
        and [e.get("source") for e in _events(rows, "floor_set")]
        == ["human", "lowered"],
        str((r0 / rxe.FLOOR_KEY).get(None)),
    )
    admitted = (r0 / rxe.ADMITTED_KEY).get(None) or []
    check(
        "… the search read again at low admits the conversion, with no second "
        "call; three drafts",
        [(a.get("id"), a.get("admitted_at")) for a in admitted] == [(ADMITTED, "low")]
        and _calls(rows, "knowledge") == 1
        and _calls(rows, "construction") == 3
        and _verdicts(rows, rxe.ESSENTIAL_GATE) == [False, False, True],
        f"{admitted and admitted[0].get('admitted_at')}, "
        f"{_calls(rows, 'knowledge')} knowledge, "
        f"{_verdicts(rows, rxe.ESSENTIAL_GATE)}",
    )


# ------------------------------------------------------------ (c) nothing usable


def check_nothing(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    rows = ledger_rows(root)
    check(
        "nothing usable twice: the run pauses at the exhaustion gate after the "
        "third failed draft",
        rc == 3 and modules == ["intent", EXHAUSTION],
        f"exit {rc}, {modules}: {tail[-400:]}",
    )
    searches = _events(rows, "knowledge_search")
    check(
        "… two searches, the second only for the question the first did not ask; "
        "neither admits anything",
        [e.get("n") for e in searches] == [1, 2]
        and [e.get("n_admitted") for e in searches] == [0, 0]
        and "L + R -> LR" in str(searches[1].get("questions"))
        and "L + R -> L + Rp" not in str(searches[1].get("questions"))
        and _calls(rows, "knowledge") == 2
        and _calls(rows, "construction") == 3
        and _verdicts(rows, rxe.ESSENTIAL_GATE) == [False, False, False],
        json.dumps([(e.get("n"), e.get("questions")) for e in searches])[:400],
    )
    lines = _card(cards, EXHAUSTION)
    check(
        "… the card carries the floor's history and each search's questions and "
        "admissions",
        "SUPPORT FLOOR this round: medium (human) -> low (lowered)" in lines
        and any(x.startswith("  search 1") and "nothing admitted" in x for x in lines)
        and any(x.startswith("  search 2") and "nothing admitted" in x for x in lines)
        and any("Q q_2: L + R -> LR" in x for x in lines),
        "\n".join(lines),
    )


def check_floor_answer(rid: str, case: Path) -> None:
    """`floor: none` at the exhaustion card: the round's floor is the person's,
    the searches are read again at it, and construction is asked again."""
    root = run_root(rid, RUNS)
    proc = _cli(
        [
            "run",
            "--run-id",
            rid,
            "--gate-mode",
            "file",
            "--gate-answer",
            "y",
            "--gate-note",
            "floor: none",
        ]
    )
    rows = ledger_rows(root)
    floor = (rnd(root, 0) / rxe.FLOOR_KEY).get(None) or {}
    support = (rnd(root, 0) / "model" / rxe.SUPPORT_KEY).get(None) or {}
    origins = {
        str(b.get("entry_id")): b.get("origin")
        for r in support.get("reactions") or []
        for b in (r.get("directions") or {}).values()
        if b
    }
    check(
        "`floor: none` at the exhaustion card: the floor is the person's (a "
        "floor_set row), read back, and the fourth draft with the admitted "
        "binding step passes to the scope card",
        proc.returncode == 3
        and (pending_gate(root) or {}).get("module") == "model_scope"
        and floor.get("band") == rxe.NONE
        and floor.get("source") == "human"
        and [e.get("source") for e in _events(rows, "floor_set")][-1] == "human"
        and "floor: none" in proc.stdout
        and _calls(rows, "construction") == 4
        and _verdicts(rows, rxe.ESSENTIAL_GATE)[-1] is True
        and "search" in origins.values(),
        f"exit {proc.returncode}, floor {floor}, origins {origins}: "
        + json.dumps(
            [
                (e.get("gate_id"), str(e.get("detail"))[:300])
                for e in rows
                if e.get("event") == "gate" and e.get("passed") is False
            ][-4:]
        ),
    )


# ------------------------------------------------------------ (d) a stray species


def check_stray(rid: str, result) -> None:
    rc, modules, _cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    failed = [
        e
        for e in rows
        if e.get("event") == "gate"
        and e.get("gate_id") == "model_connected"
        and not e.get("passed")
    ]
    check(
        "a stray species: `model_connected` fails the second draft, naming it",
        _verdicts(rows, "model_connected") == [True, False, True]
        and len(failed) == 1
        and "species X takes part in no reaction" in str(failed[0].get("detail")),
        json.dumps(failed)[:400],
    )
    attempts = ((r0 / "agent_calls/construction/dossier").get(None) or {}).get(
        "attempts"
    ) or []
    check(
        "… the failure reaches construction's dossier; nothing was named "
        "missing, so no search runs for it and the budget pays for the redraft",
        len(attempts) == 2
        and any("model_connected" in f for f in attempts[1].get("gate_failures") or [])
        and not attempts[1].get("search_step")
        and _calls(rows, "knowledge") == 1,
        json.dumps(attempts[-1:])[:400],
    )
    check(
        "… and the third draft passes: the run completes",
        rc == 0 and modules == SEQUENCE,
        str(modules) if rc == 0 else f"exit {rc}, {modules}: {tail}",
    )


# ------------------------------------------------------------ (e) advisory mode


def check_advisory(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    check(
        "advisory: the run completes through the usual gates",
        rc == 0 and modules == SEQUENCE,
        str(modules) if rc == 0 else f"exit {rc}, {modules}: {tail}",
    )
    fence = _events(rows, "grounding_fence")
    gates = [
        e
        for e in rows
        if e.get("event") == "gate" and e.get("gate_id") == rxe.ESSENTIAL_GATE
    ]
    check(
        "… the fence row names the mode; the one draft passes "
        "`model_essential_reactions`, the conversions outside the set a finding in "
        "its detail; no search runs and construction is called once",
        fence
        and fence[0].get("grounding_mode") == "advisory"
        and [g.get("passed") for g in gates] == [True]
        and "advisory" in str(gates[0].get("detail"))
        and "J3 R ->" in str(gates[0].get("detail"))
        and _calls(rows, "construction") == 1
        and _calls(rows, "knowledge") == 0
        and not _events(rows, "knowledge_search"),
        json.dumps(gates)[:400],
    )
    prompt = (r0 / "agent_calls/construction/prompt").text("")
    check(
        "… construction is told the dossier is prior knowledge, not a fence",
        "prior knowledge, not a fence" in prompt
        and "`missing` is not needed" in prompt,
    )
    support = (r0 / "model" / rxe.SUPPORT_KEY).get(None) or {}
    by = {r.get("reaction_id"): r for r in support.get("reactions") or []}
    j4 = ((by.get("J4") or {}).get("directions") or {}).get("forward") or {}
    check(
        "… the annotation labels the loss inferred and matches the turnover to "
        "the survey's rx_2",
        (by.get("J3") or {}).get("label") == rxe.INFERRED
        and j4.get("entry_id") == "rx_2",
        json.dumps({k: v.get("label") for k, v in by.items()}),
    )
    lines = _card(cards, "model_scope")
    check(
        "… and the scope card flags both: the inferred loss, the turnover below "
        "the floor, the essential set read as prior knowledge",
        any(x.startswith("REACTIONS — 4 in the model") for x in lines)
        and any("⚑ inferred" in x and "J3" in x for x in lines)
        and any(
            "⚑ below the floor medium: J4 Rp -> " in x and "weak (rx_2)" in x
            for x in lines
        )
        and any(
            x.startswith("ESSENTIAL SET — prior knowledge (advisory)") for x in lines
        ),
        "\n".join(x for x in lines if "⚑" in x or "ESSENTIAL" in x or "REACT" in x),
    )


def main() -> int:
    t0 = time.time()
    stamp = time.strftime("%H%M%S")
    where = Path(tempfile.mkdtemp(prefix="octomod_grounding_"))
    runs = {
        "fixture": (f"grounding_{stamp}", CASE, None),
        "low": (f"grounding_low_{stamp}", make_low(where), None),
        "nothing": (f"grounding_nothing_{stamp}", make_nothing(where), EXHAUSTION),
        "stray": (f"grounding_stray_{stamp}", make_stray(where), None),
        "advisory": (f"grounding_advisory_{stamp}", make_advisory(where), None),
    }
    passed = False
    try:
        with ThreadPoolExecutor(max_workers=len(runs)) as pool:
            futures = {
                key: pool.submit(drive_cards, case, rid, None, stop)
                for key, (rid, case, stop) in runs.items()
            }
            results = {key: f.result() for key, f in futures.items()}
        print("(a) the fixture, through file gates")
        check_fixture(runs["fixture"][0], results["fixture"])
        print("(b) the conversion found at low")
        check_low(runs["low"][0], results["low"])
        print("(c) nothing usable, twice")
        check_nothing(runs["nothing"][0], results["nothing"])
        check_floor_answer(runs["nothing"][0], runs["nothing"][1])
        print("(d) a species no reaction touches")
        check_stray(runs["stray"][0], results["stray"])
        print("(e) advisory mode")
        check_advisory(runs["advisory"][0], results["advisory"])
        passed = not FAILS
    finally:
        # a failing run's records are its evidence: run_all keeps them
        for rid, _case, _stop in runs.values() if passed else ():
            remove_checked(run_store(rid, RUNS))
        shutil.rmtree(where, ignore_errors=True)
    return finish(
        "GROUNDING",
        f"GROUNDING OK — the base from the essential set, the targeted search and "
        f"its admission, the floor lowered, the exhaustion gate and the floor "
        f"answered there, the graph check, advisory mode, "
        f"the record and the reports, offline ({time.time() - t0:.0f}s)",
    )


if __name__ == "__main__":
    sys.exit(main())
