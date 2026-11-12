"""What a discrimination round's expansions add is held to the variants'
floor, end to end through file gates, token-free and offline.

The fixture `abcd_mechanism_knowledge` holds the knowledge module's output
(its `knowledge/`, made by the stub module) and the person's floor, high. The
round is built in two calls: construction writes the base (the designed
module), the expansions write three candidates as declared differences from
it. The variants' floor is medium, one band below the base's.
M2_feedforward adds a conversion whose reactants and products are the designed
conversion's, which the dossier grades high; M4_sequestration adds the
sequestration of active RegB by the product, which the dossier grades low, and
names it in `missing`.

  (a) the fixture: the expansions are shown the base's essential set, the
      dossier and the variants' floor; the round's one targeted search, asked
      by the expansions, returns the sequestration from a direct experiment in
      a related module (medium): it is admitted at the variants' floor, it is
      not part of the base, and the variation is kept; its annotation, the
      scope card, the model report and ANALYSIS say so;
  (b) the search finds the sequestration only in a review (low): nothing is
      admitted, M4_sequestration is dropped with the reason on the scope card
      and a ledger row, and the rest of the round runs;
  (c) the reading a discrimination round whose construction reply writes the
      candidates itself is held to: a candidate that lacks an essential
      reaction, or adds a conversion below the variants' floor, is named by
      `essential_check` and `floor_refusals`; at a floor of none nothing is
      refused.

    uv run python tests/floor_variants_smoke.py
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
    work,
)

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR

CASE = REPO / "testcase" / "abcd_mechanism_knowledge"
# the pauses of a discrimination round that ends at its verdict
SEQUENCE = [
    "intent",
    "model_scope",
    "assembly_cost_boundary",
    "cost_boundary_estimation",
    "evaluation_verdict",
]
CANDIDATES = ["M1_chain", "M2_feedforward", "M4_sequestration"]
ADMITTED = "r0s1_rx_1"
# the answers the front end gives: the verdict ends the run
ANSWERS = {"evaluation_verdict": ("y", "expand: no")}


def _events(rows: list[dict], event: str) -> list[dict]:
    return [e for e in rows if e.get("event") == event]


def _card(cards: list[dict], module: str) -> list[str]:
    card = next((c for c in cards if c.get("module") == module), {})
    return [str(x) for x in (card.get("lines") or []) + (card.get("always_show") or [])]


def make_review_only(where: Path) -> Path:
    """The search finds the sequestration in a review only (low)."""
    case = where / "abcd_mechanism_knowledge_review"
    shutil.copytree(CASE, case)
    path = case / "stubs" / "knowledge_targeted.1.json"
    found = json.loads(path.read_text())
    item = found["reactions"][0]["evidence"][0]
    item["evidence_kind"] = "review"
    item["supports"] = (
        "a note on related modules mentions that the product may bind the regulator"
    )
    path.write_text(json.dumps(found, indent=2))
    return case


# ------------------------------------------------------------ (a) the fixture


def check_fixture(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    check("the run completes", rc == 0, "" if rc == 0 else f"exit {rc}: {tail}")
    check(
        "it pauses at the gates of a discrimination round, in order",
        modules == SEQUENCE,
        str(modules),
    )
    prompt = (r0 / "agent_calls/expansion/prompt").text("")
    vf = prompt[prompt.find("## variants_floor") :][:1500]
    check(
        "the expansions are shown the base's essential set, the dossier with "
        "every entry's origin and grade, the variants' floor in words, the "
        "facts for construction and the instruction",
        all(
            h in prompt
            for h in (
                "## essential_reactions",
                "## prior_reactions",
                "## variants_floor",
                "## known_facts",
                "## grounding_instruction",
            )
        )
        and '"band": "medium"' in vf
        and '"base": "high"' in vf
        and "is refused and its candidate dropped" in vf,
        vf[:500],
    )
    searches = _events(rows, "knowledge_search")
    check(
        "one `knowledge_search` row, asked by the expansions for the conversion "
        "they named missing, admitting it at the variants' floor",
        len(searches) == 1
        and searches[0].get("requested_by") == "expansion"
        and searches[0].get("admitted") == [ADMITTED]
        and searches[0].get("floor") == "medium"
        and "Ba + D -> BD" in str(searches[0].get("questions")),
        json.dumps(searches)[:400],
    )
    admitted = (r0 / rxe.ADMITTED_KEY).get(None) or []
    check(
        "rounds/round_0/knowledge_admitted holds it: origin search, asked by the "
        "expansion, admitted at medium, and not an essential of the base",
        [a.get("id") for a in admitted] == [ADMITTED]
        and admitted[0].get("origin") == "search"
        and admitted[0].get("requested_by") == "expansion"
        and admitted[0].get("admitted_at") == "medium"
        and admitted[0].get("essential") is False
        and not rxe.base_set(
            {
                "reactions": list((r0 / rxe.DOSSIER_KEY).get()["reactions"]) + admitted,
                "admitted": [ADMITTED],
            },
            "high",
        )["ids"].count(ADMITTED),
        json.dumps(admitted)[:300],
    )
    cands = [c.get("id") for c in (r0 / "space/candidates").get(None) or []]
    check(
        "every variation is kept and fitted: no `variation_refused_floor` row",
        cands == CANDIDATES and not _events(rows, "variation_refused_floor"),
        str(cands),
    )
    support = (work(root, 0, "M4_sequestration") / "model" / rxe.SUPPORT_KEY).get(
        None
    ) or {}
    j8 = next(
        (r for r in support.get("reactions") or [] if r.get("reaction_id") == "J8"),
        {},
    )
    fwd = (j8.get("directions") or {}).get("forward") or {}
    check(
        "M4_sequestration's J8 implements the admitted entry (origin search, "
        "medium) beside the review's (low), and its annotation records the "
        "variants' floor it was held to",
        fwd.get("entry_id") == ADMITTED
        and fwd.get("origin") == "search"
        and fwd.get("grade") == "medium"
        and "rx_7" in (fwd.get("also_matches") or [])
        and support.get("floor")
        == {"band": "medium", "base": "high", "offset": 1, "held_to": "variants"},
        json.dumps({"J8": fwd, "floor": support.get("floor")})[:500],
    )
    lines = _card(cards, "model_scope")
    check(
        "the scope card names the variants' floor and the search with what it "
        "admitted",
        any(
            x.startswith("VARIANTS' FLOOR: medium (the base's floor high")
            for x in lines
        )
        and any(
            "search 1 (asked by the expansions)" in x
            and f"admitted at floor medium: {ADMITTED}" in x
            for x in lines
        ),
        "\n".join(x for x in lines if "FLOOR" in x or "search" in x),
    )
    html_path = reports_dir(root) / "round_0" / "report" / "model_report.html"
    html = html_path.read_text() if html_path.exists() else ""
    check(
        "the model report's block of each variation says the floor it was held to",
        "held to the variants&#x27; floor medium" in html
        or "held to the variants' floor medium" in html,
        str(html_path),
    )
    origin = ((root / "analysis").get(None) or {}).get("model_origin") or {}
    check(
        'ANALYSIS holds "Where the model came from": the round\'s counts by '
        "origin and band, the floor, and the expansions' search with what it "
        "admitted",
        [r.get("round") for r in origin.get("rounds") or []] == [0]
        and sum((origin["rounds"][0].get("by_origin") or {}).values())
        == origin["rounds"][0].get("n_reactions")
        and [
            (s.get("requested_by"), s.get("admitted"))
            for s in origin.get("searches") or []
        ]
        == [("expansion", [ADMITTED])]
        and "Where the model came from"
        in (reports_dir(root) / "ANALYSIS.html").read_text(),
        json.dumps(origin)[:500],
    )


# ------------------------------------------------------------ (b) review only


def check_review_only(rid: str, result) -> None:
    rc, modules, cards, tail = result
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    check(
        "found in a review only: the round still runs to its verdict",
        rc == 0 and modules == SEQUENCE,
        str(modules) if rc == 0 else f"exit {rc}, {modules}: {tail}",
    )
    searches = _events(rows, "knowledge_search")
    check(
        "… the search admits nothing at the variants' floor, and says why",
        len(searches) == 1
        and searches[0].get("admitted") == []
        and [b.get("band") for b in searches[0].get("not_admitted") or []] == ["low"],
        json.dumps(searches)[:400],
    )
    refused = _events(rows, "variation_refused_floor")
    reason = (
        "below the variants' floor medium: J8 Ba + D -> BD, graded low (rx_7) — a "
        "search may raise its support"
    )
    check(
        "… M4_sequestration is refused by name: one `variation_refused_floor` "
        "row with the reaction, its band and the floor",
        len(refused) == 1
        and refused[0].get("candidate") == "M4_sequestration"
        and refused[0].get("reactions") == ["J8"]
        and refused[0].get("bands") == ["low"]
        and refused[0].get("floor") == "medium"
        and reason in str(refused[0].get("note")),
        json.dumps(refused)[:400],
    )
    lines = _card(cards, "model_scope")
    report = (r0 / "model/build_report").get(None) or {}
    check(
        "… it is dropped from the set with the reason on the scope card and in "
        "the build report; the other two are fitted",
        [c.get("id") for c in (r0 / "space/candidates").get(None) or []]
        == ["M1_chain", "M2_feedforward"]
        and any(x == f"DROPPED M4_sequestration: {reason}" for x in lines)
        and [d.get("id") for d in report.get("dropped_candidates") or []]
        == ["M4_sequestration"]
        and len(
            ((r0 / "evaluation").get(None) or {})
            .get("discrimination", {})
            .get("candidates")
            or []
        )
        == 2,
        "\n".join(x for x in lines if "DROPPED" in x or "search" in x),
    )
    origin = ((root / "analysis").get(None) or {}).get("model_origin") or {}
    check(
        "… and ANALYSIS lists the variation refused for the floor",
        any(
            x.get("kind") == "variation" and x.get("candidate") == "M4_sequestration"
            for x in origin.get("refused") or []
        ),
        json.dumps(origin.get("refused"))[:300],
    )


# ------------------------------------------------------------ (c) the reading


def check_reading() -> None:
    """The reading the floor applies to a candidate, on a crafted dossier: a
    candidate lacking an essential reaction and adding one below the floor."""
    from octomod.gates.build_gates import antimony_to_sbml

    def entry(eid, eq, grade, essential=True):
        return {
            "id": eid,
            "equation": eq,
            "parsed": rxe.parse_equation(eq),
            "grade": grade,
            "essential": essential,
            "evidence": [],
        }

    dossier = {
        "reactions": [
            entry("rx_1", "A -> B", "high"),
            entry("rx_2", "B -> C", "high"),
            entry("rx_3", "B -> D", "low", essential=False),
            entry("rx_4", "C -> D", "medium", essential=False),
        ]
    }
    ant = (
        "model m\n  species A = 1, B = 0, C = 0, D = 0\n  k1 = 1; k3 = 1; k4 = 1\n"
        "  J1: A -> B; k1*A\n  J3: B -> D; k3*B\n  J4: C -> D; k4*C\nend\n"
    )
    sbml, err = antimony_to_sbml(ant)
    support = rxe.annotate(dossier, sbml, [])
    base = rxe.base_set(dossier, "high")
    missing = rxe.essential_check(support, base)["missing"]
    allowed = rxe.admitted_at(dossier, "medium", exempt=set(base["ids"]))
    refusals = rxe.floor_refusals(support["reactions"], allowed, "medium")
    check(
        "a candidate lacking rx_2 and adding B -> D (low) is named: the missing "
        "essential, and the one conversion below medium; C -> D (medium) passes",
        [m["id"] for m in missing] == ["rx_2"]
        and [(r["reaction_id"], r["band"], r["entry_id"]) for r in refusals]
        == [("J3", "low", "rx_3")],
        json.dumps({"missing": missing, "refusals": refusals})[:400],
    )
    check(
        "the refusal in the words of the gate",
        rxe.variant_refusal_reason(refusals, "medium")
        == "below the variants' floor medium: J3 B -> D, graded low (rx_3) — a "
        "search may raise its support",
        rxe.variant_refusal_reason(refusals, "medium"),
    )
    check(
        "at a floor of none, or offline, nothing is refused",
        rxe.floor_refusals(support["reactions"], set(), "none") == []
        and rxe.floor_refusals(support["reactions"], set(), "not_applicable") == [],
    )


def main() -> int:
    t0 = time.time()
    stamp = time.strftime("%H%M%S")
    where = Path(tempfile.mkdtemp(prefix="octomod_floorvariants_"))
    runs = {
        "fixture": (f"floorvariants_{stamp}", CASE),
        "review": (f"floorvariants_review_{stamp}", make_review_only(where)),
    }
    passed = False
    try:
        with ThreadPoolExecutor(max_workers=len(runs)) as pool:
            futures = {
                key: pool.submit(drive_cards, case, rid, ANSWERS)
                for key, (rid, case) in runs.items()
            }
            results = {key: f.result() for key, f in futures.items()}
        print("(a) the fixture, through file gates")
        check_fixture(runs["fixture"][0], results["fixture"])
        print("(b) the conversion found in a review only")
        check_review_only(runs["review"][0], results["review"])
        print("(c) the reading of a candidate the construction reply writes")
        check_reading()
        passed = not FAILS
    finally:
        # a failing run's records are its evidence: run_all keeps them
        for rid, _case in runs.values() if passed else ():
            remove_checked(run_store(rid, RUNS))
        shutil.rmtree(where, ignore_errors=True)
    return finish(
        "FLOOR VARIANTS",
        f"FLOOR VARIANTS OK — the variants' floor, the expansions' search and its "
        f"admission, a refused variation dropped by name, the record and the "
        f"reports ({time.time() - t0:.0f}s)",
    )


if __name__ == "__main__":
    sys.exit(main())
