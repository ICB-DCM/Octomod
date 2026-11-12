"""The support floor and the grade's helpers, token-free.

    uv run python tests/grade_floor_unit.py

What this holds, each on constructed input:

  1. the band vocabulary: its order, `lower_band` never below `none`, and
     `not_applicable` staying where it is;
  2. `suggest_floor` on crafted essential reactions: every one high gives
     high; one medium gives medium; one with no counting source is a
     decision, not a floor of none; the required ones are exempt; offline is
     not applicable; `leaves_at` names what leaves the base at each higher
     band;
  3. the floor card: every essential with its grade, the source that earned
     it and its origin, the unsupported ones as decisions, the suggestion and
     its reason, the trade-off, what leaves at each higher band, the forms,
     the decision when there is one, and never a decimal;
  4. the decision block of testcase.yaml: read and defaulted, refused by
     name when it is not a decision, absent when there is none; a skip
     declared with its why, refused without one;
  5. the floor on a record: round 0's floor read from the case, written at
     `space/floor` with a `floor_set` row, preferred once written, and a
     second identical write silent;
  6. the connector: PubMed's publication types through a fake fetch — a DOI
     looked up to its PMID, a PMID directly, nothing for a source with
     neither, None on network trouble, one lookup per identifier;
  7. the spec's readers of the floor, the searches and the verifier.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.knowledge import reaction_evidence as rx  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
# a number written as a decimal, never part of an identifier (a DOI's 10.1000)
DECIMAL = re.compile(r"(?<![\w./])\d+\.\d+(?![\w./])")


def refusal(fn, *args) -> str | None:
    try:
        fn(*args)
    except ValueError as e:
        return str(e)
    return None


# ------------------------------------------------------------ 1 · the bands


def test_bands() -> None:
    check(
        "the bands, strongest first",
        rx.GRADE_BANDS == ("high", "medium", "low", "weak", "none", "not_applicable")
        and [rx.band_rank(b) for b in rx.GRADE_BANDS] == [0, 1, 2, 3, 4, 5],
    )
    check(
        "lower_band steps down and never below none",
        rx.lower_band("high") == "medium"
        and rx.lower_band("medium", 2) == "weak"
        and rx.lower_band("low", 5) == "none"
        and rx.lower_band("none") == "none"
        and rx.lower_band("high", 0) == "high",
    )
    check(
        "not_applicable stays; `not applicable` is read as it",
        rx.lower_band("not_applicable") == "not_applicable"
        and rx.band_rank("not applicable") == 5
        and rx.band_rank("High") == 0,
    )
    why = refusal(rx.band_rank, "certain")
    check(
        "a word that is not a band is refused, naming the bands",
        why is not None and "high, medium, low, weak, none, not_applicable" in why,
        str(why),
    )
    check(
        "a negative step is refused",
        refusal(rx.lower_band, "high", -1) is not None,
    )


# ------------------------------------------------------------ 2 · the rule


def ess(eid, grade, *, required=False, eq="A -> B", origin=None, because=None):
    row = {
        "id": eid,
        "equation": eq,
        "essential": True,
        "required": required,
        "grade": grade,
        "because": (
            because
            if because is not None
            else (
                []
                if grade in ("none", "not_applicable")
                else [
                    {
                        "id": f"{eid}.e1",
                        "source": f"{eid} fixture source",
                        "evidence_kind": "direct_experimental",
                        "context_match": "same_system",
                    }
                ]
            )
        ),
        "flags": [],
    }
    if origin:
        row["origin"] = origin
    return row


def test_suggestion() -> None:
    all_high = [ess("rx_1", "high"), ess("rx_2", "high")]
    s = rx.suggest_floor(all_high)
    check(
        "every essential high: the suggestion is high, and no higher band to leave at",
        s["band"] == "high" and s["unsupported"] == [] and s["leaves_at"] == {},
        json.dumps(s),
    )
    one_medium = [ess("rx_1", "high"), ess("rx_2", "medium"), ess("rx_3", "high")]
    s = rx.suggest_floor(one_medium)
    check(
        "one essential medium: medium, and the reason names it and its source",
        s["band"] == "medium"
        and "rx_2" in s["why"]
        and "rx_2 fixture source" in s["why"]
        and s["leaves_at"] == {"high": ["rx_2"]},
        json.dumps(s),
    )
    with_unsupported = one_medium + [ess("rx_4", "none")]
    s = rx.suggest_floor(with_unsupported)
    check(
        "an essential with no counting source is a decision, not a floor of none",
        s["band"] == "medium" and s["unsupported"] == ["rx_4"],
        json.dumps(s),
    )
    required_low = [
        ess("req_1", "weak", required=True),
        ess("req_2", "none", required=True),
        ess("rx_1", "high"),
    ]
    s = rx.suggest_floor(required_low)
    check(
        "the required ones are exempt: a weak and an unsupported required "
        "reaction neither lower the suggestion nor become decisions",
        s["band"] == "high" and s["unsupported"] == [] and s["leaves_at"] == {},
        json.dumps(s),
    )
    s = rx.suggest_floor([ess("rx_1", "none"), ess("req_1", "high", required=True)])
    check(
        "no supported essential outside the required ones: none",
        s["band"] == "none" and s["unsupported"] == ["rx_1"],
        json.dumps(s),
    )
    offline = [ess("rx_1", "not_applicable"), ess("rx_2", "not_applicable")]
    check(
        "offline — every essential not applicable, or the mode said — gives "
        "not_applicable",
        rx.suggest_floor(offline)["band"] == "not_applicable"
        and rx.suggest_floor(all_high, mode="offline")["band"] == "not_applicable"
        and rx.suggest_floor(offline)["leaves_at"] == {},
    )
    mixed = [
        ess("rx_1", "high"),
        ess("rx_2", "medium"),
        ess("rx_3", "low"),
        ess("rx_4", "weak"),
        ess("req_1", "weak", required=True),
        {"id": "rx_9", "equation": "C -> D", "grade": "weak"},
    ]
    s = rx.suggest_floor(mixed)
    check(
        "raising the floor names what leaves the base at each higher band — the "
        "required one never, a reaction that is not essential not at all",
        s["band"] == "weak"
        and s["leaves_at"]
        == {
            "high": ["rx_2", "rx_3", "rx_4"],
            "medium": ["rx_3", "rx_4"],
            "low": ["rx_4"],
        },
        json.dumps(s["leaves_at"]),
    )


# ------------------------------------------------------------ 3 · the card


def test_card() -> None:
    entries = [
        ess("req_1", "low", required=True, eq="R -> Rp"),
        ess("rx_1", "high", eq="Rp -> R", origin="knowledge"),
        ess("rx_2", "medium", eq="R + L -> RL"),
        ess("rx_3", "none", eq="RL -> R + L"),
    ]
    entries[1]["flags"] = [
        {"flag": "contested", "item": "rx_1.e2", "source": "x", "capped_at": None},
        {"flag": "not_counted", "item": "rx_1.e3", "why": "its identifier does not"},
    ]
    s = rx.suggest_floor(entries)
    lines = rx.floor_card_lines(entries, s)
    text = "\n".join(lines)
    check(
        "the essentials, each with its grade, the source that earned it and its "
        "origin, the required one marked",
        lines[0].startswith("ESSENTIAL REACTIONS — 4, 1 required")
        and any(
            x.strip().startswith("req_1  R -> Rp  [required, origin human]  low — ")
            for x in lines
        )
        and any(
            "rx_1  Rp -> R  [origin knowledge]  high — rx_1 fixture source "
            "(direct_experimental, same_system)" in x
            for x in lines
        ),
        text,
    )
    check(
        "a flag is shown under its reaction; a source that does not count is not",
        any("⚑ contested by rx_1.e2" in x for x in lines)
        and not any("rx_1.e3" in x for x in lines),
        text,
    )
    check(
        "the unsupported essential is a decision, with the default said",
        any(x.startswith("NO SOURCE COUNTS") and "plain yes" in x for x in lines)
        and any(x.strip() == "rx_3  RL -> R + L" for x in lines),
        text,
    )
    check(
        "the suggestion with its reason, the trade-off sentence, what leaves at "
        "each higher band, and the forms",
        any(x.startswith("SUGGESTED FLOOR: medium — rx_2") for x in lines)
        and f"TRADE-OFF: {rx.TRADE_OFF}." in lines
        and "a higher floor buys a literature-informed baseline and slower "
        "discovery; a lower one buys data-driven mechanisms sooner" in rx.TRADE_OFF
        and "  at floor high: rx_2 leave(s) the base" in lines
        and all(f in text for f in rx.FLOOR_FORMS.values())
        and set(rx.FLOOR_FORMS) == {"floor", "step", "keep", "drop"}
        and rx.FLOOR_FORMS["floor"] == "floor: <band|none>",
        text,
    )
    check("no decimal anywhere on the card", not any(DECIMAL.search(x) for x in lines))
    decided = rx.floor_card_lines(
        entries,
        s,
        {
            "support_floor": "low",
            "floor_step": 1,
            "decided_by": "human",
            "note": "keep the binding",
            "dropped": ["rx_3"],
            "kept": [],
        },
    )
    check(
        "the decision, when there is one, closes the card",
        decided[-1]
        == 'DECISION: floor low, step 1, decided by human; dropped rx_3 — "keep the '
        'binding"',
        decided[-1],
    )
    off = [ess("rx_1", "not_applicable")]
    off_lines = rx.floor_card_lines(off, rx.suggest_floor(off))
    check(
        "offline: no grade and no floor apply, and no trade-off is offered",
        any(x.startswith("SUGGESTED FLOOR: not applicable") for x in off_lines)
        and not any(x.startswith("TRADE-OFF") for x in off_lines)
        and any("not applicable (offline" in x for x in off_lines),
        "\n".join(off_lines),
    )


# ------------------------------------------------------------ 4 · the decision block


def test_decision_block() -> None:
    d = rx.read_floor_decision(
        {"grounding": {"support_floor": "medium", "decided_by": "rule"}}, SPEC
    )
    check(
        "a decision is read whole, the step from the spec when the case gives none",
        d
        == {
            "support_floor": "medium",
            "floor_step": 1,
            "decided_by": "rule",
            "note": "",
            "dropped": [],
            "kept": [],
        },
        json.dumps(d),
    )
    d = rx.read_floor_decision(
        {
            "grounding": {
                "support_floor": "none",
                "floor_step": 2,
                "decided_by": "human",
                "note": "the data should decide",
                "dropped": ["rx_2", "rx_3"],
                "kept": "rx_4",
            }
        },
        SPEC,
    )
    check(
        "…with the person's own step, note, and the ids they dropped and kept",
        d["support_floor"] == "none"
        and d["floor_step"] == 2
        and d["dropped"] == ["rx_2", "rx_3"]
        and d["kept"] == ["rx_4"]
        and d["note"] == "the data should decide",
        json.dumps(d),
    )
    check(
        "no support_floor, or no grounding block: no decision",
        rx.read_floor_decision({"grounding": {"floor_step": 1}}, SPEC) is None
        and rx.read_floor_decision({}, SPEC) is None,
    )
    bad = {
        "a floor that is not a band": (
            {"support_floor": "certain", "decided_by": "human"},
            "high, medium, low, weak, none, not_applicable",
        ),
        "a decision nobody made": ({"support_floor": "low"}, "human, rule"),
        "a step that is not a whole number": (
            {"support_floor": "low", "decided_by": "human", "floor_step": 1.5},
            "grounding.floor_step",
        ),
        "an unknown key": (
            {"support_floor": "low", "decided_by": "human", "floor": "low"},
            "unknown key(s) ['floor']",
        ),
        "an id both dropped and kept": (
            {
                "support_floor": "low",
                "decided_by": "human",
                "dropped": ["rx_1"],
                "kept": ["rx_1"],
            },
            "both dropped and kept",
        ),
    }
    for name, (block, words) in bad.items():
        why = refusal(rx.read_floor_decision, {"grounding": block}, SPEC)
        check(f"refused by name: {name}", why is not None and words in why, str(why))
    check(
        "a skip is declared with its why",
        rx.skip_declared({"grounding": {"skip": True, "why": "benchmark"}})
        == "benchmark"
        and rx.skip_declared({"grounding": {"skip": False}}) is None
        and rx.skip_declared({"grounding": {"support_floor": "low"}}) is None
        and rx.skip_declared({}) is None,
    )
    why = refusal(rx.skip_declared, {"grounding": {"skip": True}})
    check(
        "a skip without a why is refused, saying how to write it",
        why is not None and 'why: "<benchmark | fixture>"' in why,
        str(why),
    )
    check(
        "a case that skips the module declares no floor",
        "has no floor"
        in str(
            refusal(
                rx.skip_declared,
                {"grounding": {"skip": True, "why": "fixture", "support_floor": "low"}},
            )
        ),
    )


# ------------------------------------------------------------ 5 · on a record


class _Ctx:
    """The parts of a run context the floor reads: the record, the round,
    the case's testcase.yaml, the spec and the ledger."""

    def __init__(self, root, testcase: dict, round_idx: int = 0):
        from octomod.orchestration.ledger import Ledger
        from octomod.result import node as tree

        self.root, self.testcase, self.spec = root, testcase, SPEC
        self.round_idx = round_idx
        self.round = tree.round_node(root, round_idx)
        self.ledger = Ledger(root.store)


def test_on_a_record() -> None:
    from tests._record import ledger_rows, rnd, temp_record

    case = {"grounding": {"support_floor": "medium", "decided_by": "human"}}
    with temp_record() as root:
        ctx = _Ctx(root, case)
        check(
            "round 0's floor is the case's decision until one is written",
            rx.floor_of(ctx) == {"band": "medium", "step": 1, "source": "human"}
            and not (rnd(root, 0) / rx.FLOOR_KEY).exists(),
            str(rx.floor_of(ctx)),
        )
        check(
            "a case with no decision has no floor",
            rx.floor_of(_Ctx(root, {}, round_idx=3)) is None,
        )
        rec = rx.write_floor(ctx, "medium", 1, "human")
        node = rnd(root, 0) / rx.FLOOR_KEY
        rows = [e for e in ledger_rows(root) if e.get("event") == "floor_set"]
        check(
            "written at rounds/round_0/space/floor, with a floor_set row",
            node.exists()
            and node.get() == rec == {"band": "medium", "step": 1, "source": "human"}
            and len(rows) == 1
            and rows[0]["band"] == "medium"
            and rows[0]["source"] == "human"
            and rows[0]["artifact"] == node.key,
            json.dumps(rows)[:300],
        )
        rx.write_floor(ctx, "medium", 1, "human")
        check(
            "the same floor written again ledgers nothing: a resume is silent",
            sum(1 for e in ledger_rows(root) if e.get("event") == "floor_set") == 1,
        )
        ctx1 = _Ctx(root, case, round_idx=1)
        rx.write_floor(ctx1, rx.lower_band("medium"), 1, "schedule")
        check(
            "a later round's written floor is preferred to the case's decision",
            rx.floor_of(ctx1) == {"band": "low", "step": 1, "source": "schedule"}
            and rx.floor_of(ctx)["band"] == "medium",
            str(rx.floor_of(ctx1)),
        )
        check(
            "a floor that is not a band, and a source nobody is, are refused",
            refusal(rx.write_floor, ctx, "certain", 1, "human") is not None
            and "human, rule, schedule"
            in str(refusal(rx.write_floor, ctx, "low", 1, "agent")),
        )


# ------------------------------------------------------------ 6 · the connector


def test_publication_types() -> None:
    from octomod.connectors import web_cache

    web_cache._PUBLICATION_TYPES.clear()
    asked: list[str] = []

    def fake(url: str):
        asked.append(url)
        if "esearch" in url:
            return json.dumps({"esearchresult": {"idlist": ["31234567"]}})
        if "id=31234567" in url:
            return json.dumps(
                {"result": {"31234567": {"pubtype": ["Journal Article", "Review"]}}}
            ).encode()
        if "id=20000001" in url:
            return json.dumps(
                {"result": {"20000001": {"pubtype": ["Journal Article"]}}}
            )
        raise OSError("no network in a unit test")

    got = web_cache.publication_types("Smith 2019, doi:10.1000/ABC.1", fetch=fake)
    check(
        "a DOI is looked up to its PMID, then the PMID's publication types",
        got == ["Journal Article", "Review"]
        and len(asked) == 2
        and "esearch" in asked[0]
        and "10.1000%2Fabc.1%5Bdoi%5D" in asked[0]
        and "esummary" in asked[1],
        f"{got} {asked}",
    )
    again = web_cache.publication_types(
        {"source": "Smith", "url": "https://doi.org/10.1000/abc.1"}, fetch=fake
    )
    check(
        "the answer is kept for the process: the same DOI is not looked up twice",
        again == got and len(asked) == 2,
        str(asked),
    )
    check(
        "a PMID is summarised directly, whether written PMID or as a PubMed URL",
        web_cache.publication_types("PMID: 20000001", fetch=fake) == ["Journal Article"]
        and web_cache.publication_types(
            "https://pubmed.ncbi.nlm.nih.gov/20000001/", fetch=fake
        )
        == ["Journal Article"],
    )
    check(
        "a source with neither DOI nor PMID asks nothing, and gives None",
        web_cache.publication_types("general knowledge", fetch=fake) is None
        and web_cache.publication_types("reactome:R-HSA-1", fetch=fake) is None,
    )
    before = len(asked)
    check(
        "network trouble gives None — never held against a source — and is not "
        "kept, so a later call may succeed",
        web_cache.publication_types("PMID 30000001", fetch=fake) is None
        and "pmid:30000001" not in web_cache._PUBLICATION_TYPES
        and len(asked) == before + 1,
    )

    def nothing(url: str):
        return json.dumps({"esearchresult": {"idlist": []}})

    check(
        "a DOI PubMed does not know gives None",
        web_cache.publication_types("doi:10.1000/unknown", fetch=nothing) is None,
    )
    item = {
        "source": "doi:10.1000/abc.1",
        "evidence_kind": "direct_experimental",
        "context_match": "same_system",
        "publication_types": got,
    }
    check(
        "…and its answer is what the grade's metadata class reads",
        rx.class_from_metadata(item) == "review",
    )


# ------------------------------------------------------------ 7 · the spec


class _With:
    def __init__(self, key: str, value):
        self.key, self.value = key, value

    def get(self, dotted: str, default=None):
        return self.value if dotted == self.key else SPEC.get(dotted, default)


def test_spec_readers() -> None:
    check(
        "the floor's step, the variants' offset, the search caps and the verifier "
        "are read from the spec",
        rx.floor_step(SPEC) == 1
        and rx.variants_offset(SPEC) == 1
        and rx.search_caps(SPEC) == {"per_redraft": 1, "per_round": 1}
        and rx.verify_enabled(SPEC) is True
        and rx.contested_cap(SPEC) == "medium",
    )
    check(
        "the rule table is declared, with a list for every band from high to weak",
        set(rx.grading_rules(SPEC)) == {"high", "medium", "low", "weak"}
        and rx.rule_problems(rx.grading_rules(SPEC)) == [],
    )
    check(
        "a step that is not a whole number is refused by name; `none` is no cap",
        "grounding.floor_step"
        in str(refusal(rx.floor_step, _With("grounding.floor_step", "one")))
        and rx.contested_cap(_With("grounding.contested_caps_at", "none")) is None,
    )
    retired = [
        k
        for k in (
            "kind_weight",
            "context_weight",
            "resolution_weight",
            "no_quote_weight",
            "labels",
        )
        if SPEC.get(f"grounding.{k}") is not None
    ] + [
        n
        for n in (
            "score_item",
            "combine",
            "label_of",
            "score_reactions",
            "rubric",
            "labels",
            "WEAK_BAND",
            "NO_BAND",
        )
        if hasattr(rx, n)
    ]
    check(
        "the weights, the labels and the arithmetic are gone",
        not retired,
        ", ".join(retired),
    )


def main() -> int:
    test_bands()
    test_suggestion()
    test_card()
    test_decision_block()
    test_on_a_record()
    test_publication_types()
    test_spec_readers()
    return finish(
        "GRADE FLOOR",
        "GRADE FLOOR OK — the bands, the floor's suggestion and card, the case's "
        "decision, the floor on a record, the publication types and the spec's "
        "readers",
    )


if __name__ == "__main__":
    sys.exit(main())
