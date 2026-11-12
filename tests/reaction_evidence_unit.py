"""The knowledge module's reactions inside a run, token-free.

    uv run python tests/reaction_evidence_unit.py

What this holds, each on constructed input:

  1. an equation is read one way or refused BY NAME, and two spellings of one
     conversion are one reaction;
  2. `intent.required_reactions` is shape-checked at the intent gate, entry by
     entry, and the intent validator carries the check;
  3. the grade is the ENGINE's: a band from the declared rule table, first
     match wins, explained by the source that earned it and never a number;
     the metadata's class overrides the agent's, the verifier's weaker
     reading grades the item, a contradicting source is flagged and caps the
     band, one paper cited twice counts once, an unresolvable identifier and
     a classification outside the vocabulary never count, a quote not found
     is flagged, offline is not applicable, and the table is checked by name;
  4. the dossier as the module keeps it: each reaction's grade, the source
     that earned it and the items that count, each item saying why when it
     does not;
  5. what an agent is shown: each entry's origin, grade and counting items,
     none of the engine's audit fields; the base set in the same shape; the
     instruction that the base is exactly the set;
  6. the base set: required always, essential at or above the floor, the
     unsupported ones kept by default, `kept` and `dropped`, the admitted
     ones, everything offline; the floor as construction reads it;
  7. the fence: a skip records nothing, the rule table must be declared and
     well-formed, a `reactions:` block and the retired switch are refused;
     the grounding mode: advisory by default, strict per case, a bad word
     refused by name; `model_essential_reactions` in both modes, advisory
     failing only for a required entry the base lacks;
  8. on a record: `active`, the staged dossier copied into round 0 once, the
     view with the admitted reactions, a later round reading round 0's, and
     construction's context — except for a supplied network or a skip;
  9. admission and the floor on a record: a search's reactions admitted at
     the floor with who asked and why, the ones below kept out with their
     band, the floor lowered one band and the search read again, the card;
 10. the wiring: construction's routing row and contract, the reply's
     `missing`, and the retired in-run survey gone;
 11. the annotation of a built model against a hand-written dossier: each
     reaction's label, grade, earning source and origin from the entry it
     matches in every direction its rate law carries, a participant held as a
     parameter left out, and `model_essential_reactions` naming what the base
     lacks and what it carries outside the set; the cards;
 12. the gates in S1 on a record (stub replies, auto-approved): a base
     without an essential reaction fails, is redrafted with the failure and
     no search (nothing was named missing), the next draft passes, and its
     annotation reaches the record, the scope card, the decision record and
     the model report;
 13. the expansion's axes: the expansion agent is shown the round's dossier,
     and each axis is annotated by the reactions its patch adds to the base,
     recorded at the round's `expansion_support`, one card line per axis, and
     nothing run or written when the module is skipped.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check  # noqa: E402

from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.knowledge import reaction_evidence as rx  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
RULES = rx.grading_rules(SPEC)
# a number written as a decimal, never part of an identifier (a DOI's 10.1000)
DECIMAL = re.compile(r"(?<![\w./])\d+\.\d+(?![\w./])")


def refused(eq) -> str | None:
    try:
        rx.parse_equation(eq)
    except rx.EquationError as e:
        return str(e)
    return None


# ------------------------------------------------------------ 1 · equations


def test_equations() -> None:
    p = rx.parse_equation("A + 2 B -> C")
    check(
        "reactants, products and coefficients are read",
        p
        == {
            "reactants": {"A": 1.0, "B": 2.0},
            "products": {"C": 1.0},
            "reversible": False,
        },
        str(p),
    )
    check(
        "two spellings of one conversion are one reaction",
        rx.canonical(rx.parse_equation("B + A->C"))
        == rx.canonical(rx.parse_equation("A + B -> C"))
        == "A + B -> C",
    )
    check(
        "synthesis, degradation and a reversible step read as such",
        rx.canonical(rx.parse_equation("-> A")) == "-> A"
        and rx.canonical(rx.parse_equation("A ->")) == "A ->"
        and rx.parse_equation("A <-> B")["reversible"] is True
        and rx.parse_equation("A => B")["reversible"] is False,
    )
    for bad, why in (
        ("", "empty"),
        ("A B", "no arrow"),
        ("A -> B -> C", "more than one"),
        ("X-P -> A", "not a species id"),
        ("->", "both sides"),
        ("A -> A", "converts nothing"),
    ):
        msg = refused(bad)
        check(
            f"refused by name: {bad!r}",
            msg is not None and why in msg,
            msg or "accepted",
        )


# ------------------------------------------------------ 2 · the intent's field


def test_intent_shape() -> None:
    ok = {"required_reactions": ["A -> B", {"equation": "B -> A", "note": "back"}]}
    check("a string and an object entry pass", rx.intent_problems(ok) == [])
    check("an absent field passes (it is optional)", rx.intent_problems({}) == [])
    cases = (
        ({"required_reactions": "A -> B"}, "must be a LIST"),
        ({"required_reactions": [{"equation": "A -> B", "rate": 1}]}, "unknown key"),
        ({"required_reactions": ["A -> B", "A->B"]}, "repeats"),
        (
            {"required_reactions": [{"equation": "A -> B", "modifiers": "Z"}]},
            "modifiers",
        ),
        ({"required_reactions": ["A to B"]}, "required_reactions[0]"),
    )
    for intent, needle in cases:
        probs = rx.intent_problems(intent)
        check(
            f"refused, naming the entry: {needle}",
            any(needle in p for p in probs),
            "; ".join(probs) or "passed",
        )
    from octomod.orchestration.artifacts import validate_intent

    full = {
        "question": "q",
        "system": "s",
        "required_entities": ["A"],
        "required_predictions": ["p"],
        "timescale": "t",
        "inference_target": "prediction",
        "domain_packs": ["general-dynamics"],
        "success_criteria": ["c"],
        "required_reactions": ["A -> "],
    }
    check(
        "a valid full intent with required reactions passes",
        validate_intent(full) == [],
    )
    full["required_reactions"] = ["A to B"]
    check(
        "the intent validator carries the check (S0 and entry both refuse)",
        any("required_reactions[0]" in p for p in validate_intent(full)),
    )
    req = rx.required_reactions(
        {"required_reactions": ["B + A -> C", {"equation": "C ->"}]}
    )
    check(
        "required reactions get engine ids by position, parsed",
        [(r["id"], r["equation"]) for r in req]
        == [("req_1", "A + B -> C"), ("req_2", "C ->")],
        str([(r["id"], r["equation"]) for r in req]),
    )


# ------------------------------------------------------------ 3 · the grade


def item(
    kind="direct_experimental",
    ctx="same_system",
    res="resolved",
    quote="q",
    src="doi:10.1000/a",
    **extra,
):
    return {
        "source": src,
        "evidence_kind": kind,
        "context_match": ctx,
        "resolution": res,
        "quote": quote,
        **extra,
    }


def graded(*items, rules=None, **kw) -> dict:
    return rx.grade({"id": "rx_1", "evidence": list(items)}, rules or RULES, **kw)


def _numbers(node) -> list:
    """Every float anywhere in a structure: a grade carries none."""
    if isinstance(node, float):
        return [node]
    if isinstance(node, dict):
        return [x for v in node.values() for x in _numbers(v)]
    if isinstance(node, list):
        return [x for v in node for x in _numbers(v)]
    return []


def test_grade() -> None:
    src = iter(f"doi:10.1000/p{k}" for k in range(100))

    def one(kind, ctx, **kw):
        return item(kind, ctx, src=next(src), **kw)

    bands = {
        "high: a direct experiment in this system": graded(
            one("direct_experimental", "same_system")
        ),
        "high: a curated database entry for a related system": graded(
            one("curated_database", "related_system")
        ),
        "high: two independent sources, each earning medium on its own": graded(
            one("direct_experimental", "related_system"),
            one("mechanistic_model", "same_system"),
        ),
        "medium: a direct experiment in a related system": graded(
            one("direct_experimental", "related_system")
        ),
        "medium: a mechanistic model in this system": graded(
            one("mechanistic_model", "same_system")
        ),
        "medium: two independent reviews in this or a related system": graded(
            one("review", "same_system"), one("review", "related_system")
        ),
        "low: one review": graded(one("review", "related_system")),
        "low: a direct experiment in a different system": graded(
            one("direct_experimental", "different_system")
        ),
        "low: a mechanistic model in a different system": graded(
            one("mechanistic_model", "different_system")
        ),
        "low: two independent indirect sources": graded(
            one("indirect", "same_system"), one("indirect", "different_system")
        ),
        "weak: one indirect source": graded(one("indirect", "same_system")),
        "weak: a counting source no stronger rule matches": graded(
            one("curated_database", "different_system")
        ),
        "none: nothing counts": graded(),
    }
    for name, g in bands.items():
        want = name.split(":")[0]
        check(f"the grade — {name}", g["band"] == want, f"{g['band']}: {g}")
    g = bands["high: a direct experiment in this system"]
    check(
        "a grade is explained by the source that earned it, with the rule it "
        "satisfied, and carries no number",
        g["because"]
        == [
            {
                "id": "rx_1.e1",
                "source": "doi:10.1000/p0",
                "evidence_kind": "direct_experimental",
                "context_match": "same_system",
                "rule": "a direct_experimental source in same_system",
            }
        ]
        and g["counting"] == ["rx_1.e1"]
        and not _numbers(g),
        json.dumps(g)[:300],
    )
    two = bands["high: two independent sources, each earning medium on its own"]
    check(
        "…and a two-source grade names both",
        [b["id"] for b in two["because"]] == ["rx_1.e1", "rx_1.e2"]
        and two["because"][0]["rule"]
        == "2 independent sources, each earning medium on its own",
        json.dumps(two["because"]),
    )

    corrected = graded(
        item(publication_types=["Journal Article", "Review"]),
    )
    check(
        "a paper PubMed types a Review is a review whatever the agent says: "
        "low, flagged class_corrected with both",
        corrected["band"] == "low"
        and {
            "flag": "class_corrected",
            "item": "rx_1.e1",
            "agent": "direct_experimental",
            "metadata": "review",
        }
        in corrected["flags"],
        json.dumps(corrected),
    )
    check(
        "the metadata decides a database namespace or host and a model "
        "repository entry; otherwise nothing",
        rx.class_from_metadata({"source": "reactome:R-HSA-912631"})
        == "curated_database"
        and rx.class_from_metadata({"url": "https://www.rhea-db.org/rhea/12345"})
        == "curated_database"
        and rx.class_from_metadata({"source": "KEGG: R00001"}) == "curated_database"
        and rx.class_from_metadata({"url": "https://www.genome.jp/kegg/pathway.html"})
        == "curated_database"
        and rx.class_from_metadata({"source": "BioModels BIOMD0000000019"})
        == "mechanistic_model"
        and rx.class_from_metadata(
            {"url": "https://www.ebi.ac.uk/biomodels/MODEL1204280001"}
        )
        == "mechanistic_model"
        and rx.class_from_metadata({"source": "doi:10.1000/x"}) is None
        and rx.class_from_metadata(
            {"source": "doi:10.1000/x", "publication_types": ["Journal Article"]}
        )
        is None,
    )
    db = graded(item(kind="review", src="reactome:R-HSA-1"))
    check(
        "a Reactome entry the agent read as a review is graded as the database it is",
        db["band"] == "high"
        and db["because"][0]["evidence_kind"] == "curated_database"
        and any(f["flag"] == "class_corrected" for f in db["flags"]),
        json.dumps(db),
    )

    disputed = graded(item(second_kind="indirect"))
    check(
        "the verifier's weaker reading grades the item: weak, flagged "
        "disputed_class with both readings",
        disputed["band"] == "weak"
        and any(
            f["flag"] == "disputed_class"
            and f["agent"]
            == {"evidence_kind": "direct_experimental", "context_match": "same_system"}
            and f["verifier"]
            == {"evidence_kind": "indirect", "context_match": "same_system"}
            and f["graded_as"]["evidence_kind"] == "indirect"
            for f in disputed["flags"]
        ),
        json.dumps(disputed),
    )
    context = graded(item(second_context="related_system"))
    agent_weaker = graded(
        item(kind="review", second_kind="direct_experimental"),
    )
    check(
        "…whichever of the two is the weaker: a context the verifier reads as "
        "related makes medium, and an agent's weaker reading stands",
        context["band"] == "medium" and agent_weaker["band"] == "low",
        f"{context['band']}, {agent_weaker['band']}",
    )
    check(
        "the same reading from both is no dispute",
        not any(
            f["flag"] == "disputed_class"
            for f in graded(item(second_kind="direct_experimental"))["flags"]
        ),
    )

    contested = graded(
        item(src="doi:10.1000/a"),
        item(src="doi:10.1000/b", stance="contradicts"),
    )
    check(
        "a contradicting source earns nothing, flags the reaction contested with "
        "its id, and caps it at medium",
        contested["band"] == "medium"
        and {
            "flag": "contested",
            "item": "rx_1.e2",
            "source": "doi:10.1000/b",
            "capped_at": "medium",
        }
        in contested["flags"]
        and [b["id"] for b in contested["because"]] == ["rx_1.e1"],
        json.dumps(contested),
    )
    uncapped = graded(
        item(src="doi:10.1000/a"),
        item(src="doi:10.1000/b", stance="contradicts"),
        contested_caps_at="none",
    )
    in_table = graded(
        item(src="doi:10.1000/a"),
        item(src="doi:10.1000/b", stance="contradicts"),
        rules={**RULES, "contested_caps_at": "none"},
    )
    only_against = graded(item(stance="contradicts"))
    check(
        "`none` as the switch, here or in the table, is no cap; a reaction "
        "only contradicted is none, and contested",
        uncapped["band"] == "high"
        and in_table["band"] == "high"
        and any(f["flag"] == "contested" for f in uncapped["flags"])
        and only_against["band"] == "none"
        and any(f["flag"] == "contested" for f in only_against["flags"]),
        f"{uncapped['band']}, {in_table['band']}, {only_against['band']}",
    )

    twice = graded(
        item(kind="review", src="doi:10.1000/xyz"),
        item(kind="review", src="https://doi.org/10.1000/XYZ"),
    )
    check(
        "a paper cited twice counts once: one review is low, not two reviews' "
        "medium; the second citation is said",
        twice["band"] == "low"
        and twice["counting"] == ["rx_1.e1"]
        and any(
            f["flag"] == "not_counted"
            and f["item"] == "rx_1.e2"
            and "same source" in f["why"]
            for f in twice["flags"]
        ),
        json.dumps(twice),
    )
    strongest = graded(
        item(kind="review", src="doi:10.1000/xyz"),
        item(kind="direct_experimental", src="doi:10.1000/XYZ"),
    )
    check(
        "…and of two citations of one source the strongest reading counts",
        strongest["band"] == "high" and strongest["counting"] == ["rx_1.e2"],
        json.dumps(strongest),
    )
    check(
        "an unresolvable identifier never counts; network trouble is never " "punished",
        graded(item(res="unresolvable"))["band"] == "none"
        and graded(item(res="unchecked: URLError"))["band"] == "high"
        and graded(item(res="not-checkable"))["band"] == "high",
    )
    check(
        "a classification outside the vocabulary does not count, and says so",
        graded(item(kind="compelling"))["band"] == "none"
        and any(
            "not in the vocabulary" in str(f.get("why"))
            for f in graded(item(kind="compelling"))["flags"]
        ),
    )
    lost = graded(item(quote="ligand drives", quote_found=False))
    bare = graded(item(quote=""))
    check(
        "a quote not found in the cached document, like no quote, still counts "
        "and flags the reaction unquoted",
        lost["band"] == "high"
        and bare["band"] == "high"
        and {
            "flag": "unquoted",
            "item": "rx_1.e1",
            "why": "its quote is not in the cached document",
        }
        in lost["flags"]
        and {"flag": "unquoted", "item": "rx_1.e1", "why": "no quote"} in bare["flags"],
        json.dumps(lost["flags"]),
    )

    dossier = {
        "reactions": [{"id": "rx_1", "evidence": [item()]}],
        "facts": [
            {"id": "f_1", "evidence": [item(kind="review", src="doi:10.1000/f")]}
        ],
    }
    rx.grade_reactions(dossier, SPEC)
    r1, f1 = dossier["reactions"][0], dossier["facts"][0]
    check(
        "grade_reactions writes the grade, the source that earned it, the flags, "
        "the counting ids and the supporting count onto each entry — the facts "
        "too — and each item says how it was graded",
        (r1["grade"], f1["grade"]) == ("high", "low")
        and r1["because"][0]["id"] == "rx_1.e1"
        and r1["counting"] == ["rx_1.e1"]
        and r1["n_sources"] == 1
        and r1["evidence"][0]["counts"] is True
        and r1["evidence"][0]["graded_as"]
        == {"evidence_kind": "direct_experimental", "context_match": "same_system"}
        and dossier["grading"]["contested_caps_at"] == "medium"
        and dossier["grading"]["rules"] == RULES
        and not any(k in r1 for k in ("support", "label", "score")),
        json.dumps(dossier)[:400],
    )
    off = {"mode": "offline", "reactions": [{"id": "rx_1", "evidence": [item()]}]}
    rx.grade_reactions(off, SPEC)
    check(
        "offline, every entry is not_applicable",
        off["reactions"][0]["grade"] == "not_applicable"
        and off["reactions"][0]["because"] == []
        and off["grading"] == {"mode": "offline"},
        json.dumps(off)[:300],
    )
    check(
        "the table is declared configuration, checked by name: an unknown kind, "
        "a missing band, a circular earning rule",
        any(
            "grounding.grading.low[0].kind ['hunch']" in p
            for p in rx.rule_problems({**RULES, "low": [{"kind": "hunch"}]})
        )
        and any(
            "no rules for ['weak']" in p
            for p in rx.rule_problems({b: RULES[b] for b in RULES if b != "weak"})
        )
        and any(
            "cannot make medium" in p
            for p in rx.rule_problems(
                {**RULES, "medium": [{"at_least": 2, "earning": "medium"}]}
            )
        )
        and rx.rule_problems(RULES) == [],
    )
    lines = [rx.because_text(g["band"], g["because"]) for g in bands.values()]
    check(
        "every grade reads as a band and its source, never a decimal",
        not any(DECIMAL.search(x) for x in lines)
        and lines[0] == "high — doi:10.1000/p0 (direct_experimental, same_system)"
        and rx.because_text("none", []) == "none — no source counts"
        and rx.because_text("not_applicable", []).startswith("not applicable"),
        "\n".join(lines),
    )


# ------------------------------------------------------------ 4 · the dossier

SUPPLIED = [
    {
        "id": "lit_1",
        "origin": "human",
        "source": "Two-state model of receptor dephosphorylation (fixture)",
        "title": "A two-state receptor model",
        "year": 2019,
        "locator": "section 2",
        "supports": "the phosphatase returns Rp to R at a first-order rate",
        "quote": "first order in Rp",
        "url": "file:./paper/two_state.txt",
    }
]


def _dossier(resolution: dict[str, str]) -> dict:
    """A survey reply as the knowledge module keeps it, audited and graded;
    `resolution` = source -> the citation check's answer (everything else not
    checkable)."""
    from octomod.workflow_modules.knowledge import engine as kn

    req = rx.required_reactions({"required_reactions": ["R -> Rp"]})
    reply = {
        "reactions": [
            {
                "equation": "R -> Rp",
                "required": "req_1",
                "evidence": [
                    {
                        "source": "note one",
                        "quote": "q",
                        "evidence_kind": "direct_experimental",
                        "context_match": "same_system",
                        "url": "file:./a.txt",
                    },
                    {
                        "source": "doi:10.9999/made-up",
                        "quote": "q",
                        "evidence_kind": "direct_experimental",
                        "context_match": "same_system",
                    },
                ],
            },
            {
                "equation": "Rp -> R",
                "essential": True,
                "evidence": [
                    {
                        "source": "note one",
                        "quote": "q",
                        "evidence_kind": "review",
                        "context_match": "same_system",
                        "url": "file:./a.txt",
                    },
                    {
                        "source": "lit_1",
                        "quote": "first order in Rp",
                        "evidence_kind": "mechanistic_model",
                        "context_match": "related_system",
                    },
                ],
            },
            {
                "equation": "R ->",
                "evidence": [
                    {
                        "source": "note two",
                        "quote": "q",
                        "evidence_kind": "compelling",
                        "context_match": "same_system",
                    }
                ],
            },
        ]
    }
    d = kn.process_survey(reply, req, [], 2025, SUPPLIED, mode="online")
    fetched: list[str] = []

    def cache(url: str) -> dict:
        fetched.append(url)
        return {"fetch_status": "cached" if url else "no-url"}

    kn.audit(d, cache, True, resolve=lambda s: resolution.get(s, "not-checkable"))
    d["_fetched"] = fetched
    return rx.grade_reactions(d, SPEC)


def test_dossier() -> None:
    d = _dossier({"doi:10.9999/made-up": "unresolvable"})
    by = {r["id"]: r for r in d["reactions"]}
    check(
        "each distinct document is fetched once, however many reactions cite it",
        sorted(d.pop("_fetched")) == ["", "file:./a.txt", "file:./paper/two_state.txt"]
        and d["n_documents"] == 2
        and d["n_sources_checked"] == 4,
        str(d)[:300],
    )
    check(
        "a required reaction: its fabricated DOI does not count, the note (not "
        "checkable, a direct experiment in this system) earns high alone",
        (by["req_1"]["grade"], by["req_1"]["n_sources"], by["req_1"]["counting"])
        == ("high", 1, ["req_1.e1"])
        and by["req_1"]["because"][0]["source"] == "note one",
        str((by["req_1"]["grade"], by["req_1"]["because"])),
    )
    check(
        "a review and the human's mechanistic model in a related system: the "
        "model earns medium, the review low — medium, two sources",
        (by["rx_1"]["grade"], by["rx_1"]["n_sources"]) == ("medium", 2)
        and [b["id"] for b in by["rx_1"]["because"]] == ["rx_1.e2"],
        str((by["rx_1"]["grade"], by["rx_1"]["because"])),
    )
    check(
        "an undeclared classification only: none, no source",
        (by["rx_2"]["grade"], by["rx_2"]["n_sources"], by["rx_2"]["counting"])
        == ("none", 0, []),
    )
    it = by["req_1"]["evidence"][0]
    check(
        "every item carries whether it counts, the class it was graded as and "
        "the audit it rests on — no score, no weights",
        {
            "id",
            "origin",
            "source_key",
            "resolution",
            "resolution_class",
            "fetch_status",
            "counts",
            "graded_as",
        }
        <= set(it)
        and not {"score", "weights"} & set(it)
        and set(d["grading"]) == {"rules", "contested_caps_at"},
        sorted(it),
    )
    check(
        "an item that does not count says why",
        "does not resolve" in by["req_1"]["evidence"][1].get("not_counted", "")
        and by["req_1"]["evidence"][1]["counts"] is False,
        str(by["req_1"]["evidence"][1]),
    )
    d2 = _dossier({"doi:10.9999/made-up": "unchecked: URLError"})
    check(
        "the same DOI unreachable instead of unresolvable is not punished: it counts",
        d2["reactions"][0]["counting"] == ["req_1.e1", "req_1.e2"],
        str(d2["reactions"][0]["counting"]),
    )


# ------------------------------------------------ 5 · what an agent is shown


def test_prior_reactions() -> None:
    d = _dossier({"doi:10.9999/made-up": "unresolvable"})
    d.pop("_fetched")
    prior = rx.prior_reactions(d)
    by = {r["id"]: r for r in prior["reactions"]}
    check(
        "every reaction is shown, with its grade, what earned it, whether it is "
        "required or essential, and who proposed it",
        list(by) == ["req_1", "rx_1", "rx_2"]
        and (by["req_1"]["required"], by["req_1"]["grade"]) == (True, "high")
        and by["req_1"]["because"]
        == [{"id": "req_1.e1", "rule": "a direct_experimental source in same_system"}]
        and (by["req_1"]["origin"], by["req_1"]["essential"]) == ("human", True)
        and (by["rx_1"]["origin"], by["rx_1"]["essential"]) == ("knowledge", True)
        and (by["rx_2"]["essential"], by["rx_1"]["required"]) == (False, False)
        and not any(k in r for r in by.values() for k in ("support", "label")),
        str({k: (v["grade"], v["because"], v["origin"]) for k, v in by.items()}),
    )
    check(
        "only the items that count: the fabricated DOI and the undeclared "
        "classification are not shown",
        [it["id"] for it in by["req_1"]["evidence"]] == ["req_1.e1"]
        and by["rx_2"]["evidence"] == []
        and [it["id"] for it in by["rx_1"]["evidence"]] == ["rx_1.e1", "rx_1.e2"],
        str({k: [i["id"] for i in v["evidence"]] for k, v in by.items()}),
    )
    shown = {k for r in prior["reactions"] for it in r["evidence"] for k in it}
    check(
        "what a source says and what it is, never the engine's audit fields",
        shown <= set(rx.PRIOR_ITEM_KEYS)
        and not shown
        & {"counts", "graded_as", "url", "cached_file", "resolution", "source_key"},
        sorted(shown),
    )
    check(
        "the human's paper reaches the agent as theirs",
        by["rx_1"]["evidence"][1]["origin"] == "human",
    )
    check(
        "the species and the notes go with it",
        set(prior) == {"reactions", "species", "notes"},
        sorted(prior),
    )
    contested = rx.prior_reactions(
        {
            "reactions": [
                {
                    "id": "rx_1",
                    "equation": "A -> B",
                    "grade": "medium",
                    "flags": [{"flag": "contested", "item": "rx_1.e2"}],
                }
            ]
        }
    )
    check(
        "a contested reaction says which source contradicts it",
        contested["reactions"][0]["contested_by"] == ["rx_1.e2"],
        str(contested),
    )
    base = rx.base_set(d, "medium")
    rows = rx.essential_rows(base)
    check(
        "construction's `essential_reactions` is the base set in the same shape",
        [r["id"] for r in rows] == ["req_1", "rx_1"]
        and rows == [by["req_1"], by["rx_1"]],
        str([r["id"] for r in rows]),
    )
    check(
        "the instruction says the base is exactly the set, what `missing` and "
        "`set_per_condition` are, and that a grade is a band",
        all(
            w in rx.BASE_INSTRUCTION
            for w in (
                "essential_reactions",
                "EXACTLY this set",
                "add no",
                "`missing`",
                "set_per_condition: true",
                "knowledge:<fact id>",
                "never a probability",
                "verbatim",
                "model_essential_reactions",
                "model_connected",
            )
        ),
    )


# ------------------------------------------------------------ 6 · the base set


def _entry(eid, eq, grade, **flags) -> dict:
    return {
        "id": eid,
        "equation": eq,
        "parsed": rx.parse_equation(eq),
        "grade": grade,
        **flags,
    }


BASE_DOSSIER = {
    "mode": "online",
    "reactions": [
        _entry("req_1", "A -> B", "none", required=True, essential=True),
        _entry("rx_1", "B -> A", "high", essential=True),
        _entry("rx_2", "B -> C", "medium", essential=True),
        _entry("rx_3", "C -> B", "low", essential=True),
        _entry("rx_4", "C ->", "none", essential=True),
        _entry("rx_5", "A -> C", "high", essential=False),
        _entry(
            "r0s1_rx_1",
            "A + C -> B",
            "weak",
            essential=True,
            admitted=True,
            origin="search",
        ),
    ],
}


def test_base_set() -> None:
    def ids(floor) -> list[str]:
        return rx.base_set(BASE_DOSSIER, floor)["ids"]

    check(
        "the base at floor medium: the required reaction whatever its grade, the "
        "essential ones at or above medium, the unsupported one (kept by default), "
        "the admitted one; not the non-essential one",
        ids("medium") == ["req_1", "rx_1", "rx_2", "rx_4", "r0s1_rx_1"],
        str(ids("medium")),
    )
    out = rx.base_set(BASE_DOSSIER, {"band": "medium"})["left_out"]
    check(
        "…the one below the floor is left out, and says why",
        [x["id"] for x in out] == ["rx_3"]
        and out[0]["why"] == "graded low, below the floor medium",
        str(out),
    )
    check(
        "a higher floor takes more out; `none` and a lower floor let everything "
        "essential in",
        ids("high") == ["req_1", "rx_1", "rx_4", "r0s1_rx_1"]
        and ids("low")
        == ids("none")
        == ["req_1", "rx_1", "rx_2", "rx_3", "rx_4", "r0s1_rx_1"],
        f"{ids('high')} {ids('low')}",
    )
    decided = {"band": "high", "kept": ["rx_3"], "dropped": ["rx_4", "req_1"]}
    base = rx.base_set(BASE_DOSSIER, decided)
    check(
        "the person's decisions: `kept` brings an essential in whatever its "
        "grade, `dropped` takes one out — never a required reaction",
        base["ids"] == ["req_1", "rx_1", "rx_3", "r0s1_rx_1"]
        and any(
            x["id"] == "rx_4" and "dropped by the person" in x["why"]
            for x in base["left_out"]
        ),
        str(base),
    )
    offline = {**BASE_DOSSIER, "mode": "offline"}
    check(
        "offline, or at floor not_applicable, every essential not dropped is in",
        rx.base_set(offline, "high")["ids"]
        == rx.base_set(BASE_DOSSIER, "not_applicable")["ids"]
        == ["req_1", "rx_1", "rx_2", "rx_3", "rx_4", "r0s1_rx_1"],
    )
    check(
        "the admissible set is the base set",
        rx.admissible_set(BASE_DOSSIER, "medium")
        == rx.base_set(BASE_DOSSIER, "medium"),
    )
    check(
        "a reaction reaches a floor at or below its band; not_applicable admits "
        "everything, an ungraded entry reaches only none",
        rx.admits("medium", "medium")
        and rx.admits("high", "low")
        and not rx.admits("low", "medium")
        and rx.admits("none", "none")
        and not rx.admits(None, "weak")
        and rx.admits("weak", "not_applicable")
        and rx.admits("not_applicable", "none")
        and not rx.admits("not_applicable", "weak"),
    )
    f = rx.floor_context({"band": "medium", "step": 1, "source": "human"})
    check(
        "construction's `support_floor`: band, step, source and one sentence",
        set(f) == {"band", "step", "source", "words"}
        and f["band"] == "medium"
        and f["words"].startswith("medium: an essential reaction is in the base")
        and "none: no constraint" in rx.floor_words("none")
        and "offline" in rx.floor_words("not_applicable"),
        str(f),
    )
    check(
        "the floor's sources include the engine's lowering",
        rx.FLOOR_SOURCES == ("human", "rule", "schedule", "lowered"),
    )


# ------------------------------------------------------------ 7 · the fence


class _Without:
    """The workflow spec with one key undeclared."""

    def __init__(self, spec, key: str):
        self.spec, self.key = spec, key

    def get(self, dotted: str, default=None):
        return default if dotted == self.key else self.spec.get(dotted, default)


class _With:
    """The workflow spec with one key declared otherwise."""

    def __init__(self, spec, key: str, value):
        self.spec, self.key, self.value = spec, key, value

    def get(self, dotted: str, default=None):
        return self.value if dotted == self.key else self.spec.get(dotted, default)


def test_fence() -> None:
    skip = {"grounding": {"skip": True, "why": "fixture"}}
    check(
        "a declared skip: nothing to record",
        rx.fence(skip, SPEC, "case_x", None) is None,
    )
    staged = {
        "grounding": {"support_floor": "medium", "decided_by": "human"},
        "research": {"max_publication_year": 2024},
    }
    try:
        rx.fence(staged, _Without(SPEC, "grounding.grading"), "case_x", None)
        check("a rule table that is not declared is refused", False, "accepted")
    except ValueError as e:
        check(
            "a rule table that is not declared is refused, naming the case and "
            "the key",
            "case_x" in str(e) and "grounding.grading" in str(e),
            str(e)[:160],
        )
    bent = {**RULES, "medium": [{"kind": "anecdote", "context": "same_system"}]}
    try:
        rx.fence(staged, _With(SPEC, "grounding.grading", bent), "case_x", None)
        check("a malformed rule table is refused", False, "accepted")
    except ValueError as e:
        check(
            "a malformed rule table is refused, naming the rule and the vocabulary",
            "case_x" in str(e)
            and "grounding.grading.medium[0].kind" in str(e)
            and "direct_experimental" in str(e),
            str(e)[:240],
        )
    try:
        rx.fence({"reactions": {"enabled": True}, **staged}, SPEC, "case_x", None)
        check("the renamed block is refused", False, "accepted")
    except ValueError as e:
        check(
            "a `reactions:` block is refused, naming the knowledge module and the "
            "`grounding:` block",
            "case_x" in str(e)
            and "./run.sh knowledge" in str(e)
            and "`grounding:` block" in str(e),
            str(e)[:200],
        )
    with tempfile.TemporaryDirectory() as tmp:
        bl = Path(tmp) / "blocklist.txt"
        bl.write_text("# c\nblocked.example\n")
        rec = rx.fence(staged, SPEC, "case_x", bl)
        bare = rx.fence({}, SPEC, "case_y", None)
    check(
        "a case that builds on the module: the horizon, the forbidden sources and "
        "a note; with no horizon declared, None for it — the module's own refusal "
        "decides whether an online module needs one",
        set(rec) == {"horizon", "forbidden_sources", "note"}
        and rec["horizon"] == 2024
        and rec["forbidden_sources"] == ["blocked.example"]
        and "1 forbidden source" in rec["note"]
        and bare["horizon"] is None,
        f"{rec} {bare}",
    )
    try:
        rx.read_floor_decision({"grounding": {"enabled": True}}, SPEC)
        check("the retired `grounding.enabled` is refused", False, "accepted")
    except ValueError as e:
        check(
            "the retired `grounding.enabled` is refused by name, with the keys "
            "a grounding block takes",
            "enabled" in str(e) and "support_floor" in str(e),
            str(e)[:200],
        )
    check(
        "the workflow spec declares no grounding switch",
        SPEC.get("grounding.enabled", "absent") == "absent",
    )


def test_mode() -> None:
    from types import SimpleNamespace

    floor = {"support_floor": "medium", "decided_by": "human"}

    def ctx(grounding, spec=SPEC):
        return SimpleNamespace(testcase={"grounding": grounding}, spec=spec)

    check(
        "the workflow declares advisory, and a case that declares no mode is "
        "advisory",
        SPEC.get("grounding.mode") == rx.ADVISORY
        and rx.grounding_mode(ctx(floor)) == rx.ADVISORY
        and not rx.strict(ctx(floor)),
    )
    check(
        "a case declares strict (in any case of letters), and a case's mode "
        "stands over the workflow's",
        rx.grounding_mode(ctx({**floor, "mode": "Strict"})) == rx.STRICT
        and rx.strict(ctx({**floor, "mode": "strict"}))
        and rx.grounding_mode(
            ctx({**floor, "mode": "advisory"}, _With(SPEC, "grounding.mode", "strict"))
        )
        == rx.ADVISORY
        and rx.grounding_mode(ctx(floor, _With(SPEC, "grounding.mode", "strict")))
        == rx.STRICT,
    )
    for where, probe in (
        ("the case", lambda: rx.grounding_mode(ctx({**floor, "mode": "lenient"}))),
        (
            "the workflow",
            lambda: rx.grounding_mode(
                ctx(floor, _With(SPEC, "grounding.mode", "lenient"))
            ),
        ),
    ):
        try:
            probe()
            check(f"a bad mode word in {where} is refused", False, "accepted")
        except ValueError as e:
            check(
                f"a bad mode word in {where} is refused by name, with the modes",
                "'lenient'" in str(e)
                and "grounding.mode" in str(e)
                and "advisory, strict" in str(e),
                str(e),
            )


def test_advisory_gate() -> None:
    check_ = {
        "missing": [
            {
                "id": "req_1",
                "equation": "R -> Rp",
                "origin": "human",
                "grade": "high",
                "required": True,
            },
            {
                "id": "rx_1",
                "equation": "Rp -> R",
                "origin": "knowledge",
                "grade": "medium",
                "required": False,
            },
        ],
        "outside": [
            {
                "reaction_id": "J3",
                "direction": "forward",
                "sides": "R -> ",
                "law": "k_loss * R",
                "matches": [],
            }
        ],
        "n_base": 2,
        "n_reactions": 2,
    }
    strict = rx.essential_result(check_, None, rx.STRICT)
    adv = rx.essential_result(check_, None, rx.ADVISORY)
    check(
        "strict: an essential entry the base lacks and a conversion outside the "
        "set each fail the gate, and each is handed back",
        not strict.passed
        and strict.value == {"missing": 2, "outside": 1}
        and len(rx.essential_failures(check_, rx.STRICT)) == 3,
        strict.detail,
    )
    check(
        "advisory: only the required entry the base lacks fails it, and only "
        "that one is handed back",
        not adv.passed
        and adv.value == {"missing": 1, "outside": 0}
        and [f.split(" (")[0] for f in rx.essential_failures(check_, rx.ADVISORY)]
        == ["essential reaction req_1"],
        adv.detail,
    )
    met = {**check_, "missing": check_["missing"][1:]}
    ok = rx.essential_result(met, None, rx.ADVISORY)
    check(
        "advisory, the required entry implemented: the gate passes, and the "
        "essential entry it lacks and the conversion outside the set are "
        "findings in its detail",
        ok.passed
        and rx.essential_failures(met, rx.ADVISORY) == []
        and "advisory" in ok.detail
        and "rx_1 Rp -> R (medium)" in ok.detail
        and "J3 R -> " in ok.detail,
        ok.detail,
    )
    check(
        "a flag names the band, the reaction and its grade, and the axis or "
        "variation that adds it",
        rx.below_floor_line(
            {"reaction_id": "J9", "sides": "A -> B", "entry_id": "rx_7", "band": "low"},
            "medium",
            "axis a1",
        )
        == "⚑ below the floor medium: J9 A -> B — low (rx_7) (axis a1)"
        and rx.below_floor_line({"reaction_id": "J3", "sides": "A -> C"}, "low")
        == "⚑ below the floor low: J3 A -> C — inferred (nothing in the dossier)",
    )


# ------------------------------------------------------------ 8 · on a record

SURVEY = {
    "system": {
        "summary": "R is phosphorylated to Rp and returned by a phosphatase.",
        "scope": "one cell line",
        "unknowns": [],
    },
    "species": [
        {"id": "R", "name": "receptor", "represents": "R"},
        {"id": "Rp", "name": "phosphorylated receptor", "represents": "Rp"},
    ],
    "reactions": [
        {
            "equation": "R -> Rp",
            "required": "req_1",
            "type": "phosphorylation",
            "evidence": [
                {
                    "source": "Note on receptor phosphorylation (fixture)",
                    "year": 2024,
                    "locator": "paragraph 1",
                    "supports": "ligand drives R to Rp",
                    "quote": "ligand drives R to Rp",
                    "url": "file:./sources/note.txt",
                    "evidence_kind": "direct_experimental",
                    "context_match": "same_system",
                    "stance": "supports",
                }
            ],
        },
        {
            "equation": "Rp -> R",
            "essential": True,
            "type": "dephosphorylation",
            "evidence": [
                {
                    "source": "Review of receptor signalling (fixture)",
                    "year": 2019,
                    "locator": "p. 3",
                    "supports": "Rp returns to R",
                    "quote": "Rp returns to R",
                    "url": "file:./sources/review.txt",
                    "evidence_kind": "review",
                    "context_match": "related_system",
                    "stance": "supports",
                }
            ],
        },
        {
            "equation": "Rp ->",
            "essential": True,
            "type": "degradation",
            "evidence": [
                {
                    "source": "Receptor turnover (fixture)",
                    "year": 2018,
                    "locator": "p. 1",
                    "supports": "Rp is degraded over hours",
                    "url": "file:./sources/turnover.txt",
                    "evidence_kind": "indirect",
                    "context_match": "related_system",
                    "stance": "supports",
                }
            ],
        },
    ],
    "facts": [
        {
            "kind": "abundance",
            "statement": "total receptor near 10 units",
            "value": 10,
            "for": ["construction"],
            "evidence": [],
        },
        {
            "kind": "assay",
            "statement": "densitometry in arbitrary units",
            "for": ["observation"],
            "evidence": [],
        },
    ],
    "queries_run": ["receptor (de)phosphorylation (fixture)"],
    "notes": "FIXTURE",
}


def staged_dossier(required=("R -> Rp",), survey=None) -> dict:
    """The knowledge module's dossier for a survey reply, as `knowledge/
    knowledge.json` holds it: processed, audited offline (every document not
    fetched, every source not checkable) and graded online."""
    from octomod.workflow_modules.knowledge import engine as kn

    req = rx.required_reactions({"required_reactions": list(required)})
    d = kn.process_survey(survey or SURVEY, req, [], 2025, mode="online")
    kn.audit(
        d,
        lambda url: {"fetch_status": "cached"},
        True,
        resolve=lambda s: "not-checkable",
    )
    return rx.grade_reactions(d, SPEC)


def _stage(case: Path, dossier: dict | None, grounding: dict) -> None:
    import yaml

    tc = (
        yaml.safe_load((case / "testcase.yaml").read_text())
        if (case / "testcase.yaml").exists()
        else {"name": "unit"}
    )
    tc["grounding"] = grounding
    tc["research"] = {"max_publication_year": 2025}
    (case / "testcase.yaml").write_text(yaml.safe_dump(tc, sort_keys=False))
    if dossier is not None:
        (case / "knowledge").mkdir(exist_ok=True)
        (case / "knowledge" / "knowledge.json").write_text(json.dumps(dossier))


# the strict mode is what these sections test; the advisory mode has its own
FLOOR = {
    "mode": "strict",
    "support_floor": "medium",
    "floor_step": 1,
    "decided_by": "human",
}


def _record_ctx(tmp: Path, root, *, round_idx: int = 0, staged: bool = True):
    """A stub-backend context on `root` whose case holds the knowledge
    module's output (or declares its skip) and supplies one paper."""
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import RunContext
    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    case = tmp / ("case" if staged else "case_skip")
    if not case.exists():
        (case / "stubs").mkdir(parents=True)
        (case / "paper").mkdir()
        (case / "description.md").write_text("R is phosphorylated to Rp.\n")
        (case / "paper" / "two_state.txt").write_text("first order in Rp\n")
        _stage(
            case,
            staged_dossier() if staged else None,
            FLOOR if staged else {"skip": True, "why": "fixture"},
        )
        if not (root / "intent").exists():
            (root / "intent").put(
                {
                    "question": "unit",
                    "system": "toy",
                    "inference_target": "prediction",
                    "domain_packs": ["general-dynamics"],
                    "required_entities": ["R", "Rp"],
                    "required_reactions": ["R -> Rp"],
                }
            )
            _lit.freeze(root, [{k: v for k, v in SUPPLIED[0].items() if k != "id"}])
    return RunContext(
        root=root,
        testcase_dir=case,
        spec=SPEC,
        ledger=Ledger(root.store),
        backend="stub",
        auto=True,
        round_idx=round_idx,
    )


def test_on_a_record() -> None:
    from octomod.agents import routing
    from octomod.workflow_modules.model import engine as model_module
    from tests._record import rnd, temp_record

    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        tmp = Path(d)
        ctx = _record_ctx(tmp, root)
        staged = staged_dossier()
        check("the run builds on the module: active", rx.active(ctx) is True)
        view = rx.dossier_of(ctx)
        node = rnd(root, 0) / rx.DOSSIER_KEY
        copied = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "note" and e.get("artifact") == node.key
        ]
        check(
            "round 0 copies the staged dossier to rounds/round_0/reaction_evidence "
            "once, with a ledger note",
            node.exists()
            and node.get()["reactions"] == json.loads(json.dumps(staged))["reactions"]
            and len(copied) == 1,
            f"{len(copied)} note(s)",
        )
        rx.dossier_of(ctx)
        check(
            "a second read finds the copy and ledgers nothing",
            sum(
                1
                for e in ctx.ledger.entries()
                if e.get("event") == "note" and e.get("artifact") == node.key
            )
            == 1,
        )
        check(
            "the view: the staged reactions, the facts, the grading, the mode, the "
            "system, the round the dossier is in, and nothing admitted yet",
            [r["id"] for r in view["reactions"]] == ["req_1", "rx_1", "rx_2"]
            and {"facts", "grading", "mode", "system", "species"} <= set(view)
            and view["mode"] == "online"
            and view["dossier_round"] == 0
            and view["admitted"] == [],
            str(sorted(view)),
        )
        by = {r["id"]: r["grade"] for r in view["reactions"]}
        check(
            "offline and deterministic: req_1 high, the dephosphorylation low (one "
            "review), the degradation weak",
            by == {"req_1": "high", "rx_1": "low", "rx_2": "weak"},
            str(by),
        )
        context = model_module._construction_context(ctx, None, "prediction")
        ess = context.get("essential_reactions") or []
        check(
            "construction's context: the base at floor medium — the required "
            "reaction; the dephosphorylation and the degradation are below it",
            [r["id"] for r in ess] == ["req_1"]
            and ess[0]["origin"] == "human"
            and context.get("support_floor", {}).get("band") == "medium"
            and context.get("support_floor", {}).get("source") == "human"
            and context.get("knowledge_summary") == staged["system"]
            and [f["id"] for f in context.get("known_facts") or []] == ["fact_1"]
            and context.get("grounding_instruction") == rx.BASE_INSTRUCTION
            and "prior_reactions" not in context
            and not routing.violations("construction", context.keys()),
            str(sorted(context)),
        )
        import dataclasses

        adv = dataclasses.replace(ctx, cache={})
        adv.cache["testcase_yaml"] = {
            **ctx.testcase,
            "grounding": {**FLOOR, "mode": "advisory"},
        }
        advised = model_module._construction_context(adv, None, "prediction")
        check(
            "advisory: the same base set, and the whole dossier beside it as "
            "`prior_reactions` — the entries below the floor included — with the "
            "advisory instruction; strict passes no `prior_reactions`",
            [r["id"] for r in advised.get("essential_reactions") or []] == ["req_1"]
            and advised.get("prior_reactions") == rx.prior_reactions(view)
            and [r["id"] for r in advised["prior_reactions"]["reactions"]]
            == ["req_1", "rx_1", "rx_2"]
            and advised.get("grounding_instruction") == rx.ADVISORY_INSTRUCTION
            and "`prior_reactions`" in rx.ADVISORY_INSTRUCTION
            and not routing.violations("construction", advised.keys())
            and "prior_reactions" not in context,
            str(sorted(advised)),
        )
        (rnd(root, 0) / rx.ADMITTED_KEY).put(
            [
                {
                    **_entry("r0s1_rx_1", "Rp -> R", "medium", essential=True),
                    "origin": "search",
                    "admitted": True,
                    "search": 1,
                }
            ]
        )
        view = rx.dossier_of(ctx)
        check(
            "an admitted reaction joins the view, origin search, and the base",
            [r["id"] for r in view["reactions"]][-1] == "r0s1_rx_1"
            and view["admitted"] == ["r0s1_rx_1"]
            and "r0s1_rx_1" in rx.base_set(view, rx.base_floor(ctx))["ids"],
            str(view["admitted"]),
        )
        ctx2 = _record_ctx(tmp, root, round_idx=2)
        later = rx.dossier_of(ctx2)
        check(
            "a later round reads the most recent round's dossier (round 0 here) "
            "and the reactions every round up to it admitted",
            later["dossier_round"] == 0
            and later["admitted"] == ["r0s1_rx_1"]
            and not (rnd(root, 2) / rx.DOSSIER_KEY).exists(),
            str(later.get("dossier_round")),
        )
        (rnd(root, 0) / "model/network").put({"species": [], "interactions": []})
        context = model_module._construction_context(ctx, None, "prediction")
        check(
            "a supplied network is translated as given: no essential set, a ledger note",
            "essential_reactions" not in context
            and any(
                e.get("event") == "note" and "grounding skipped" in str(e.get("note"))
                for e in ctx.ledger.entries()
            ),
            str(sorted(context)),
        )
        off = _record_ctx(tmp, root, staged=False)
        check(
            "a case that declares its skip does not build on the module",
            rx.active(off) is False
            and "essential_reactions"
            not in model_module._construction_context(off, None, "prediction"),
        )


def test_admission() -> None:
    """A search's reactions admitted at the floor, on a record."""
    from tests._record import temp_record

    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        ctx = _record_ctx(Path(d), root)
        rows = [
            {
                **_entry("r0s1_rx_1", "L + R -> L + Rp", "medium", essential=True),
                "answers": ["q_1"],
                "requested_by": "construction",
                "origin": "search",
            },
            {
                **_entry("r0s1_rx_2", "R -> Rp", "high", essential=True),
                "answers": ["q_1"],
                "duplicates": "req_1",
            },
            {**_entry("r0s1_rx_3", "Rp ->", "low", essential=True), "answers": ["q_2"]},
        ]
        (ctx.round / rx.SEARCH_KEY / "1").put(
            {
                "n": 1,
                "questions": [
                    {"id": "q_1", "equation": "L + R -> L + Rp", "question": "Q one"},
                    {"id": "q_2", "equation": "Rp ->", "question": "Q two"},
                ],
                "reactions": rows,
                "battery_failures": [],
            }
        )
        res = rx.admit(ctx, 1, {"band": "medium"}, in_base=["req_1"])
        admitted = (ctx.round / rx.ADMITTED_KEY).get()
        check(
            "at floor medium: the medium reaction admitted with origin search, who "
            "asked, the question it answers and the search; the duplicate of a "
            "base entry and the low one not, each with why",
            res["admitted"] == ["r0s1_rx_1"]
            and [a["id"] for a in admitted] == ["r0s1_rx_1"]
            and admitted[0]["origin"] == "search"
            and admitted[0]["requested_by"] == "construction"
            and admitted[0]["answers"] == "Q one"
            and admitted[0]["search"] == 1
            and admitted[0]["admitted_at"] == "medium"
            and sorted(b["id"] for b in res["not_admitted"])
            == ["r0s1_rx_2", "r0s1_rx_3"]
            and any("below the floor medium" in b["why"] for b in res["not_admitted"]),
            str(res),
        )
        rec = (ctx.round / rx.SEARCH_KEY / "1").get()
        check(
            "the search record says what it admitted at which floor",
            rec["admission"]["floor"] == "medium"
            and rec["admission"]["admitted"] == ["r0s1_rx_1"],
            str(rec.get("admission")),
        )
        rx.write_floor(ctx, "medium", 1, "human")
        low = rx.lower_floor(ctx, "the base failed twice")
        rows_ = ctx.ledger.entries()
        check(
            "lowering the floor: one band, written with source lowered, a "
            "floor_set and a floor_lowered row",
            low == ("medium", "low")
            and rx.floor_of(ctx) == {"band": "low", "step": 1, "source": "lowered"}
            and any(
                e.get("event") == "floor_lowered"
                and (e.get("from"), e.get("to")) == ("medium", "low")
                for e in rows_
            )
            and [h["band"] for h in rx.floor_history(ctx)] == ["medium", "low"],
            str(low),
        )
        again = rx.admit(ctx, 1, rx.base_floor(ctx), in_base=["req_1"])
        check(
            "read again at the lower floor, the low reaction is admitted; what was "
            "admitted stays",
            again["admitted"] == ["r0s1_rx_3"]
            and [a["id"] for a in (ctx.round / rx.ADMITTED_KEY).get()]
            == ["r0s1_rx_1", "r0s1_rx_3"],
            str(again),
        )
        lines = rx.search_card_lines(ctx)
        check(
            "the card: the floor's history, the search with its questions and "
            "what it admitted",
            lines[0] == "SUPPORT FLOOR this round: medium (human) -> low (lowered)"
            and any("admitted r0s1_rx_1" in x for x in lines)
            and any("Q q_2: Q two" in x for x in lines),
            "\n".join(lines),
        )
        rx.write_floor(ctx, "none", 1, "human")
        check(
            "a floor at none cannot go lower: nothing is written",
            rx.lower_floor(ctx, "again") is None and rx.floor_of(ctx)["band"] == "none",
        )


# ------------------------------------------------------------ 9 · the wiring


def test_role_is_wired() -> None:
    from octomod.agents import ROLES, routing
    from octomod.result.agent_replies import ConstructionReply

    sees = routing.allowed("construction")
    check(
        "construction may receive the base, the floor, the system summary, the "
        "instruction, the engine's finding and, in advisory mode, the whole "
        "dossier",
        {
            "essential_reactions",
            "prior_reactions",
            "support_floor",
            "knowledge_summary",
            "grounding_instruction",
            "known_facts",
            "engine_feedback",
            "engine_feedback_instruction",
        }
        <= sees,
        str(sorted(sees)),
    )
    contract = ROLES["construction"].contract
    check(
        "construction's contract says what the base, `missing` and "
        "`set_per_condition` are; its reply carries no reaction keys",
        'NOTE on "essential_reactions"' in contract
        and 'NOTE on "missing"' in contract
        and 'NOTE on "set_per_condition"' in contract
        and '"missing": []' in contract
        and not any(
            f'"{k}"' in contract
            for k in ("reactions", "reactions_omitted", "reactions_requested")
        )
        and 'NOTE on "prior_reactions"' not in contract,
    )
    check(
        "the reply class types `missing` as a list",
        "missing" in ConstructionReply.model_fields
        and ConstructionReply.model_fields["missing"].annotation == list[Any],
    )
    check(
        "the in-run survey is retired: no search, no carry-forward, no switch",
        not any(
            hasattr(rx, name)
            for name in (
                "search",
                "carry_forward",
                "enabled",
                "ROLE",
                "process_reply",
                "REQUIRED_GATE",
                "GROUNDING_INSTRUCTION",
            )
        ),
    )


# ------------------------------------------------------------ 10 · the annotation


def sbml_of(body: str) -> str:
    """A small model from Antimony: species A, B, C; parameters S and k1-k3."""
    from octomod.gates.build_gates import antimony_to_sbml

    sbml, err = antimony_to_sbml(
        "model m\n  compartment cell = 1;\n  species A in cell = 1;\n"
        "  species B in cell = 0;\n  species C in cell = 0;\n"
        "  S = 1; k1 = 1; k2 = 1; k3 = 1;\n" + body + "end\n"
    )
    assert sbml, err
    return sbml


def entry(eid: str, eq: str, *items, required: bool = False, **extra) -> dict:
    """One graded dossier entry as the record keeps it; `items` are evidence
    kinds (a source in this system, resolved), or (kind, resolution) pairs."""
    parsed = rx.parse_equation(eq)
    evidence = []
    for k, it in enumerate(items, start=1):
        kind, res = it if isinstance(it, tuple) else (it, "resolved")
        evidence.append(
            {
                "id": f"{eid}.e{k}",
                "source": f"{eid} fixture source {k}",
                "locator": f"p. {k}",
                "quote": "q",
                "evidence_kind": kind,
                "context_match": "same_system",
                "resolution": res,
                "source_key": f"{eid}-{k}",
            }
        )
    row = {
        "id": eid,
        "equation": rx.canonical(parsed),
        "parsed": parsed,
        "required": required,
        "evidence": evidence,
        **extra,
    }
    rx.grade_reactions({"reactions": [row]}, SPEC)
    return row


DOSSIER = {
    "reactions": [
        entry("req_1", "A -> B", required=True),
        entry("req_2", "C -> B", required=True),
        entry("rx_1", "B -> C", "curated_database"),
        entry("rx_2", "C -> A", "review"),
        entry("rx_3", "A + S -> C", "review"),
        entry("rx_4", "B -> A", ("curated_database", "unresolvable")),
    ]
}


def test_annotation() -> None:
    sbml = sbml_of(
        "  J1: A -> B; k1*A;\n  J2: B -> C; k2*B;\n  J3: C -> A; k3*C;\n"
        "  J4: A -> C; S*k1*A;\n  J5: C -> ; k3*C;\n  J6: B -> A; k2*B;\n"
    )
    sup = rx.annotate(DOSSIER, sbml, [{"id": "k1"}, {"id": "S"}])
    by = {r["reaction_id"]: r for r in sup["reactions"]}
    fwd = {rid: r["directions"]["forward"] for rid, r in by.items()}
    check(
        "the record has its shape: every reaction, the counts, the inferred, the "
        "required reactions the model lacks, the entries it does not use",
        set(sup)
        == {"reactions", "counts", "inferred", "required_missing", "unused_entries"}
        and list(by) == ["J1", "J2", "J3", "J4", "J5", "J6"]
        and {
            "reaction_id",
            "reactants",
            "products",
            "law",
            "directions",
            "label",
            "as_parameter",
        }
        <= set(by["J1"]),
        str(sorted(sup)),
    )
    check(
        "a reaction that matches a required entry is user-provided, with or "
        "without a source, and its origin is the person's",
        by["J1"]["label"] == rx.USER_PROVIDED
        and fwd["J1"]["entry_id"] == "req_1"
        and fwd["J1"]["required"] is True
        and fwd["J1"]["origin"] == "human"
        and fwd["J1"]["entries"]
        == [{"id": "req_1", "equation": "A -> B", "origin": "human", "grade": "none"}],
        str(fwd["J1"]),
    )
    check(
        "one whose counting item is a curated database is database-supported, "
        "with the entry's grade, the source that earned it and its origin",
        by["J2"]["label"] == rx.DATABASE_SUPPORTED
        and fwd["J2"]["kinds"] == ["curated_database"]
        and fwd["J2"]["n_sources"] == 1
        and fwd["J2"]["grade"] == "high"
        and fwd["J2"]["because"][0]["id"] == "rx_1.e1"
        and fwd["J2"]["origin"] == "knowledge",
        str(fwd["J2"]),
    )
    check(
        "one whose entry has only a review is literature-supported, low; the "
        "block carries no number",
        by["J3"]["label"] == rx.LITERATURE_SUPPORTED
        and (fwd["J3"]["entry_id"], fwd["J3"]["grade"], fwd["J3"]["kinds"])
        == ("rx_2", "low", ["review"])
        and not {"support", "label_band"} & set(fwd["J3"])
        and not _numbers(sup),
        str(fwd["J3"]),
    )
    check(
        "a dossier participant the model holds as a parameter is left out of the "
        "comparison, and recorded",
        by["J4"]["label"] == rx.LITERATURE_SUPPORTED
        and fwd["J4"]["entry_id"] == "rx_3"
        and by["J4"]["as_parameter"] == ["S"],
        str(by["J4"]),
    )
    check(
        "a reaction absent from the dossier is inferred, listed, and shown what "
        "the dossier holds nearby",
        by["J5"]["label"] == rx.INFERRED
        and fwd["J5"] == {"label": rx.INFERRED}
        and "J5" in sup["inferred"]
        and by["J5"]["nearby"]
        and by["J5"]["nearby"][0]["id"] == "req_2",
        str(by["J5"]),
    )
    check(
        "a curated-database entry whose only source does not count supports "
        "nothing: inferred, the entry named",
        by["J6"]["label"] == rx.INFERRED and fwd["J6"]["entry_id"] == "rx_4",
        str(fwd["J6"]),
    )
    check(
        "a one-way law carries no reverse direction",
        all(r["directions"]["backward"] is None for r in sup["reactions"]),
    )
    check(
        "a required entry no reaction implements is required_missing; the "
        "entries no reaction uses are listed",
        sup["required_missing"] == [{"id": "req_2", "equation": "C -> B"}]
        and sup["unused_entries"] == ["req_2"],
        f"{sup['required_missing']}, {sup['unused_entries']}",
    )
    check(
        "the counts, strongest label first",
        sup["counts"]
        == {
            "user_provided": 1,
            "database_supported": 1,
            "literature_supported": 2,
            "inferred": 2,
        }
        and list(sup["counts"])
        == ["user_provided", "database_supported", "literature_supported", "inferred"],
        str(sup["counts"]),
    )

    pair = rx.annotate(
        {"reactions": [entry("rx_1", "A -> B", "review")]},
        sbml_of("  J1: A -> B; k1*A - k2*B;\n"),
    )
    j1 = pair["reactions"][0]
    check(
        "a law kf*A - kr*B over a one-way entry A -> B: forward literature-"
        "supported, the reverse inferred, and the reaction inferred",
        j1["directions"]["forward"]["label"] == rx.LITERATURE_SUPPORTED
        and j1["directions"]["backward"] == {"label": rx.INFERRED}
        and j1["label"] == rx.INFERRED
        and pair["inferred"] == ["J1"],
        str(j1["directions"]),
    )
    fat = rx.annotate(
        {"reactions": [entry("rx_1", "A -> B", "review")]},
        sbml_of("  J1: A => B; k1*A - k2*B;\n"),
    )
    check(
        "…and Antimony's irreversible arrow `=>` does not change that: the law decides",
        fat["reactions"][0]["directions"]["backward"] == {"label": rx.INFERRED},
        str(fat["reactions"][0]["directions"]),
    )
    rev = rx.annotate(
        {"reactions": [entry("rx_1", "A <-> B", "review")]},
        sbml_of("  J1: A -> B; k1*A - k2*B;\n"),
    )
    check(
        "a reversible entry covers both directions of a reversible law",
        rev["reactions"][0]["label"] == rx.LITERATURE_SUPPORTED
        and rev["reactions"][0]["directions"]["backward"]["entry_id"] == "rx_1",
        str(rev["reactions"][0]["directions"]),
    )
    switched = rx.annotate(DOSSIER, sbml_of("  s_on = 0;\n  J2: B -> C; s_on*k2*B;\n"))
    check(
        "a switch parameter at 0 in the model as written still carries the direction",
        switched["reactions"][0]["label"] == rx.DATABASE_SUPPORTED
        and switched["reactions"][0]["directions"]["forward"]["entry_id"] == "rx_1",
        str(switched["reactions"][0]["directions"]),
    )
    turned = rx.annotate(DOSSIER, sbml_of("  J1: B -> A; k1*B;\n"))
    check(
        "a required reaction written the other way round, with a one-way law, is "
        "not implemented: the law never runs A -> B",
        {"id": "req_1", "equation": "A -> B"} in turned["required_missing"]
        and turned["reactions"][0]["directions"]["forward"]["entry_id"] == "rx_4",
        str(turned["required_missing"]),
    )

    # the essential gate: the base is req_1, req_2 and rx_1 (essential, high);
    # rx_2 is described but not essential
    ess = {
        "reactions": [
            entry("req_1", "A -> B", required=True, essential=True),
            entry("req_2", "C -> B", required=True, essential=True),
            entry("rx_1", "B -> C", "curated_database", essential=True),
            entry("rx_2", "C -> A", "review"),
            entry(
                "r0s1_rx_1",
                "A + S -> C",
                "review",
                essential=True,
                admitted=True,
                origin="search",
            ),
        ]
    }
    base = rx.base_set(ess, "medium")
    model = sbml_of("  J1: A -> B; k1*A;\n  J2: B -> C; k2*B;\n  J3: C -> A; k3*C;\n")
    part = rx.annotate(ess, model, [{"id": "S"}])
    chk = rx.essential_check(part, base)
    res = rx.essential_result(chk, part)
    failures = rx.essential_failures(chk)
    check(
        "model_essential_reactions fails naming each entry of the set the model "
        "lacks (with its origin) and each conversion outside it (with the entry "
        "it matches that is not in the base)",
        res.gate_id == "model_essential_reactions"
        and res.tier == "T0"
        and res.blocking
        and not res.passed
        and [m["id"] for m in chk["missing"]] == ["req_2", "r0s1_rx_1"]
        and [o["reaction_id"] for o in chk["outside"]] == ["J3"]
        and chk["outside"][0]["matches"] == ["rx_2"]
        and "req_2 C -> B (human)" in res.detail
        and "r0s1_rx_1 A + S -> C (search)" in res.detail
        and "J3 C -> A" in res.detail
        and any(
            "essential reaction req_2 (C -> B, origin human)" in f for f in failures
        )
        and any(
            "model reaction J3 C -> A; it matches rx_2" in f
            and "name it in `missing`" in f
            for f in failures
        ),
        f"{res.detail} | {failures}",
    )
    whole = sbml_of(
        "  J1: A -> B; k1*A;\n  J2: B -> C; k2*B;\n  J7: C -> B; k3*C;\n"
        "  J8: A -> C; S*k1*A;\n"
    )
    full = rx.annotate(ess, whole, [{"id": "S"}])
    ok = rx.essential_result(rx.essential_check(full, base), full)
    j8 = {r["reaction_id"]: r for r in full["reactions"]}["J8"]["directions"]["forward"]
    check(
        "…and passes when the base implements every entry and nothing else, the "
        "admitted reaction matched with its origin search",
        ok.passed
        and "every one of the 4 essential reaction(s)" in ok.detail
        and not rx.essential_failures(rx.essential_check(full, base))
        and j8["origin"] == "search"
        and j8["entry_id"] == "r0s1_rx_1",
        f"{ok.detail} | {j8}",
    )

    lines = rx.card_lines(sup)
    check(
        "the card: the counts, one line per inferred reaction with its law, the "
        "missing required reaction, and where the sources are",
        lines[0]
        == "REACTIONS — 6 in the model: 1 user-provided, 1 database-supported, "
        "2 literature-supported, 2 inferred"
        and any(
            "⚑ inferred — nothing in the dossier: J5  C ->  law k3 * C" in x
            for x in lines
        )
        and any("J6" in x and "rx_4" in x for x in lines)
        and any("req_2 C -> B" in x for x in lines)
        and "Where each reaction comes from" in lines[-1]
        and sum("⚑ inferred" in x for x in lines) == 2,
        "\n".join(lines),
    )
    pair_line = rx.card_lines(pair)[1]
    check(
        "…and an inferred reverse says the law can go negative, and what the "
        "forward direction matched: its label, its grade and the source that "
        "earned it",
        "the law can go negative, and B -> A is not in the dossier" in pair_line
        and "A -> B is rx_1 (literature-supported; low — rx_1 fixture source 1 "
        "(review, same_system))" in pair_line,
        pair_line,
    )
    check(
        "the card prints bands and sources, never a decimal",
        not any(DECIMAL.search(x) for x in lines + rx.card_lines(pair))
        and any("(high)" in x for x in lines if "nearby" in x),
        "\n".join(lines),
    )
    check(
        "no annotation, no card lines",
        rx.card_lines(None) == [] and rx.set_card_lines({"c1": None}) == [],
    )
    set_lines = rx.set_card_lines({"c1": sup, "c2": pair})
    check(
        "a candidate set: counts per candidate, each inferred reaction once with "
        "the candidates that carry it",
        "c1: 6 reaction(s) — 1 / 1 / 2 / 2" in "\n".join(set_lines)
        and "c2: 1 reaction(s) — 0 / 0 / 0 / 1" in "\n".join(set_lines)
        and any("J5" in x and "[c1]" in x for x in set_lines)
        and any("J1" in x and "[c2]" in x for x in set_lines),
        "\n".join(set_lines),
    )


# ------------------------------------------------ 11 · the gates in S1, on a record

GATE_SURVEY = {
    **SURVEY,
    "reactions": [
        {
            "equation": "Rp -> R",
            "required": "req_1",
            "type": "dephosphorylation",
            "evidence": [
                {
                    "source": "Phosphatase pathway entry (fixture)",
                    "year": 2020,
                    "locator": "entry 1",
                    "supports": "Rp is dephosphorylated back to R",
                    "quote": "dephosphorylated back to R",
                    "url": "file:./sources/entry.txt",
                    "evidence_kind": "curated_database",
                    "context_match": "same_system",
                    "stance": "supports",
                }
            ],
        },
        {
            "equation": "R -> Rp",
            "essential": True,
            "type": "phosphorylation",
            "evidence": [
                {
                    "source": "Review of receptor signalling (fixture)",
                    "year": 2019,
                    "locator": "p. 3",
                    "supports": "ligand drives R to Rp",
                    "quote": "ligand drives R to Rp",
                    "url": "file:./sources/review.txt",
                    "evidence_kind": "review",
                    "context_match": "related_system",
                    "stance": "supports",
                }
            ],
        },
    ],
}


def _s1_ctx(tmp: Path, root):
    """toy_phos staged on the knowledge module with the dephosphorylation
    required and the phosphorylation essential (low, above the floor weak).
    Construction's first draft leaves the dephosphorylation out and names
    nothing missing; its second is toy_phos's own model, which builds it."""
    import copy
    import shutil

    import yaml

    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import RunContext

    case = tmp / "case"
    shutil.copytree(
        REPO / "testcase" / "toy_phos",
        case,
        ignore=shutil.ignore_patterns("make_data.py", "tried_models.json", "truth"),
    )
    _stage(
        case,
        staged_dossier(("Rp -> R",), GATE_SURVEY),
        {"mode": "strict", "support_floor": "weak", "decided_by": "human"},
    )
    stubs = case / "stubs"
    full = json.loads((stubs / "construction.json").read_text())
    first = copy.deepcopy(full)
    first["antimony"] = (
        "\n".join(
            line
            for line in full["antimony"].splitlines()
            if "J2:" not in line and "k_dephos" not in line
        )
        + "\n"
    )
    first["parameters"] = [q for q in full["parameters"] if q["id"] != "k_dephos"]
    (stubs / "construction.1.json").write_text(json.dumps(first))
    (stubs / "construction.2.json").write_text(json.dumps(full))
    intent = yaml.safe_load((case / "intent.yaml").read_text())
    intent["required_reactions"] = ["Rp -> R"]
    (root / "intent").put(intent)
    return RunContext(
        root=root,
        testcase_dir=case,
        spec=SPEC,
        ledger=Ledger(root.store),
        backend="stub",
        auto=True,
    )


def test_gate_on_a_record() -> None:
    import contextlib
    import dataclasses
    import io

    from octomod.orchestration.interaction import retry
    from octomod.reporting.model_report import model_report_path
    from octomod.reporting.render import decisions_md
    from octomod.reporting.round_report import research_line
    from octomod.result.access import record_for
    from octomod.workflow_modules.model import engine as model_module
    from tests._record import rnd, temp_record

    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        ctx = _s1_ctx(Path(d), root)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            model_module.run(ctx)
        printed = out.getvalue()
        rows = ctx.ledger.entries()

        def verdicts(gid: str) -> list:
            return [
                e["passed"]
                for e in rows
                if e.get("event") == "gate" and e.get("gate_id") == gid
            ]

        calls = [
            e
            for e in rows
            if e.get("event") == "agent_call" and e.get("role") == "construction"
        ]
        check(
            "the draft without the required reaction fails model_essential_reactions, "
            "the redraft passes it; model_connected is recorded beside it each time: "
            "two construction calls, no search (nothing was named missing)",
            verdicts(rx.ESSENTIAL_GATE) == [False, True]
            and verdicts("model_connected") == [True, True]
            and verdicts("model_fact_citations") == [True, True]
            and len(calls) == 2
            and not any(e.get("event") == "knowledge_search" for e in rows),
            f"{verdicts(rx.ESSENTIAL_GATE)} {verdicts('model_connected')}, "
            f"{len(calls)} construction call(s)",
        )
        history = retry.AttemptHistory(retry.dossier_of(ctx, "construction"))
        failed = history.attempts[0]["gate_failures"] if history.attempts else []
        prompt = (ctx.agent_calls.child("construction") / "prompt").text()
        check(
            "the failure goes into the redraft dossier as a ladder failure does, "
            "and construction is asked again with it and the base set",
            any("essential reaction req_1 (Rp -> R, origin human)" in f for f in failed)
            and "essential reaction req_1 (Rp -> R, origin human)" in prompt
            and "## essential_reactions" in prompt
            and "## support_floor" in prompt
            and not history.attempts[0].get("search_step"),
            str(failed),
        )
        gate = (ctx.gates / rx.ESSENTIAL_GATE).get()
        check(
            "the passing verdict is in the record with the counts as its detail",
            gate["passed"] is True
            and "1 user-provided, 0 database-supported, 1 literature-supported, "
            "0 inferred" in gate["detail"],
            str(gate),
        )
        sup = (rnd(root, 0) / "model" / rx.SUPPORT_KEY).get()
        by = {r["reaction_id"]: r for r in sup["reactions"]}
        check(
            "the model's annotation is at rounds/round_0/model/reaction_support, "
            "naming the round its dossier is in: the dephosphorylation "
            "user-provided (origin human), the phosphorylation "
            "literature-supported (origin knowledge)",
            sup["dossier_round"] == 0
            and by["J2"]["label"] == rx.USER_PROVIDED
            and by["J2"]["directions"]["forward"]["entry_id"] == "req_1"
            and by["J2"]["directions"]["forward"]["origin"] == "human"
            and by["J1"]["label"] == rx.LITERATURE_SUPPORTED
            and by["J1"]["directions"]["forward"]["entry_id"] == "rx_1"
            and by["J1"]["directions"]["forward"]["origin"] == "knowledge"
            and sup["required_missing"] == []
            and sup["inferred"] == [],
            json.dumps(sup)[:300],
        )
        typed = record_for(root).rounds["round_0"].model
        check(
            "the typed record reads it as the model's field",
            typed is not None and typed.reaction_support == sup,
        )
        knowledge_lines = model_module._knowledge_card_lines(ctx, None)
        check(
            "the scope card carries the reactions line, and its lines on the "
            "essential set — read from the record, as a resumed card reads them — "
            "with the advisory for an intent that varies something no entry marks",
            "REACTIONS — 2 in the model: 1 user-provided, 0 database-supported, "
            "1 literature-supported, 0 inferred" in printed
            and knowledge_lines[0].startswith(
                "ESSENTIAL SET — the base is built from 2 reaction(s) at the support "
                "floor weak (human)"
            )
            and any("set_per_condition" in x for x in knowledge_lines),
            "\n".join(knowledge_lines),
        )
        md = decisions_md(ctx.round)
        check(
            "the decision record has the section, each reaction with its label, "
            "its entry's grade, the source that earned it and its origin, and its "
            "counted sources — no number",
            "## Reactions and their support" in md
            and "`J2` Rp -> R" in md
            and "**user-provided**" in md
            and "(low — Review of receptor signalling (fixture) (review, "
            "related_system); origin knowledge)" in md
            and "(high — Phosphatase pathway entry (fixture) (curated_database, "
            "same_system); origin human)" in md
            and "source: Review of receptor signalling (fixture) [p. 3] — review, "
            "related_system" in md
            and "support 0" not in md
            and "score" not in md,
            md[md.find("## Reactions") : md.find("## Reactions") + 700],
        )
        html = model_report_path(ctx.round).read_text()
        check(
            "the model report's M1 has the block, with its anchor and origins",
            'id="reaction-support"' in html
            and "Where each reaction comes from" in html
            and "Phosphatase pathway entry (fixture)" in html
            and "origin human" in html,
        )
        sbml = (rnd(root, 0) / "model/sbml").text()
        later = dataclasses.replace(ctx, round_idx=1, cache={})
        seeded = model_module._reaction_support(later, sbml, [])
        check(
            "a round-1 model is annotated when only round 0 has a dossier (a "
            "round an expansion seeded searches nothing), and says so",
            seeded is not None
            and seeded["dossier_round"] == 0
            and not (rnd(root, 1) / rx.DOSSIER_KEY).exists()
            and {r["reaction_id"]: r["label"] for r in seeded["reactions"]}
            == {r["reaction_id"]: r["label"] for r in sup["reactions"]},
            json.dumps(seeded)[:300],
        )
        off = dataclasses.replace(ctx, cache={})
        off.cache["testcase_yaml"] = {
            **ctx.testcase,
            "grounding": {"skip": True, "why": "fixture"},
        }
        check(
            "nothing is annotated, and so no gate runs, when the case skips the "
            "module",
            model_module._reaction_support(off, sbml, []) is None
            and model_module._essential_gates(off, {}, {"parameters": []}, sbml)
            == (None, []),
        )
    check(
        "the run page header names the knowledge module, its floor and step",
        research_line(
            [],
            None,
            [
                {
                    "mode": "online",
                    "support_floor": "medium",
                    "floor_source": "human",
                    "floor_step": 1,
                    "horizon": 2025,
                }
            ],
        )
        == "off; knowledge module online, support floor medium (the person's), "
        "step 1, horizon 2025"
        and research_line([], None, []) == "off",
    )


# ------------------------------------------------ 12 · the expansion's axes

BASE_ANT = (
    "model m\n  compartment cell = 1;\n  species A in cell = 1;\n"
    "  species B in cell = 0;\n  species C in cell = 0;\n"
    "  k1 = 1; k2 = 1; k3 = 1;\n  J1: A -> B; k1*A;\nend\n"
)
BASE_PARAMS = [
    {"id": k, "nominal_value": 1.0, "lb": 0.01, "ub": 100.0, "estimate": True}
    for k in ("k1", "k2", "k3")
]
AXIS_DOSSIER = {
    "reactions": [
        entry("rx_1", "B -> C", "review"),
        entry("rx_2", "C -> A", "curated_database"),
    ]
}


def axis(aid: str, patch, **extra) -> dict:
    return {"id": aid, "kind": "structure", "on_antimony_patch": patch, **extra}


AXES = [
    axis("a_lit", [{"append": "J2: B -> C; k2*B;"}]),
    axis("a_inf", [{"append": "J3: A -> C; k3*A;"}]),
    axis("a_both", [{"append": "J2: B -> C; k2*B;"}, {"append": "J3: A -> C; k3*A;"}]),
    axis("a_same", [{"replace_reaction": "J1", "with": "J1: A -> B; k1*A/(1 + C);"}]),
    axis("a_bad", [{"append": "J4: A -> B; k1*(A;"}]),
    {"id": "a_obs", "kind": "observation", "on_assembly_patch": {"add_offset": {}}},
]


def _axes_ctx(tmp: Path, root, *, round_idx: int, grounding: bool = True):
    """The section 8 case at `round_idx` (its skip declared when `grounding`
    is false), with the dossier in round 0 only."""
    return _record_ctx(tmp, root, round_idx=round_idx, staged=grounding)


def test_expansion_axes() -> None:
    from octomod.agents import routing
    from octomod.workflow_modules.model import engine as model_module
    from tests._record import rnd, temp_record

    base, err = rx.base_reactions(BASE_ANT)
    assert base is not None, err
    by = {
        a["id"]: rx.annotate_axis(AXIS_DOSSIER, BASE_ANT, BASE_PARAMS, a, base)
        for a in AXES
    }
    lit = by["a_lit"]
    check(
        "an axis that adds a reaction the dossier describes: that reaction only "
        "(not the base's), literature-supported, with the entry id",
        [r["reaction_id"] for r in lit["reactions"]] == ["J2"]
        and lit["label"] == rx.LITERATURE_SUPPORTED
        and lit["reactions"][0]["directions"]["forward"]["entry_id"] == "rx_1"
        and set(lit) == {"reactions", "label"},
        json.dumps(lit)[:300],
    )
    check(
        "an axis that adds a reaction the dossier lacks is inferred",
        by["a_inf"]["label"] == rx.INFERRED
        and [r["reaction_id"] for r in by["a_inf"]["reactions"]] == ["J3"],
        json.dumps(by["a_inf"])[:300],
    )
    check(
        "an axis adding both carries both, labelled by the weaker",
        [r["label"] for r in by["a_both"]["reactions"]]
        == [rx.LITERATURE_SUPPORTED, rx.INFERRED]
        and by["a_both"]["label"] == rx.INFERRED,
        json.dumps(by["a_both"])[:300],
    )
    check(
        "an axis that rewrites a base reaction, and an observation axis, add no "
        "new reaction",
        by["a_same"] == {"reactions": [], "label": rx.NO_NEW_REACTION}
        and by["a_obs"] == {"reactions": [], "label": rx.NO_NEW_REACTION},
        f"{by['a_same']}, {by['a_obs']}",
    )
    check(
        "a patch whose model does not convert is recorded as such, not raised",
        by["a_bad"]["label"] == rx.NOT_ANNOTATED
        and by["a_bad"]["reactions"] == []
        and "does not convert to SBML" in by["a_bad"]["error"],
        json.dumps(by["a_bad"])[:300],
    )
    rewired = rx.annotate_axis(
        AXIS_DOSSIER,
        BASE_ANT,
        BASE_PARAMS,
        axis("a_rewire", [{"replace_reaction": "J1", "with": "J1: A -> C; k1*A;"}]),
        base,
    )
    check(
        "a replace_reaction that moves a base reaction onto another product is "
        "annotated as a new conversion, with what it replaces",
        [r["reaction_id"] for r in rewired["reactions"]] == ["J1"]
        and rewired["reactions"][0]["replaces"] == "A -> B"
        and rewired["label"] == rx.INFERRED
        and rx.axis_line("a_rewire", rewired)
        == "axis a_rewire: adds J1 A -> C (in place of A -> B) — inferred "
        "(nothing in the dossier)",
        rx.axis_line("a_rewire", rewired),
    )
    gone = rx.annotate_axis(
        AXIS_DOSSIER,
        BASE_ANT,
        BASE_PARAMS,
        axis("a_gone", [{"replace_reaction": "J99", "with": "J99: A -> C; k1*A;"}]),
        base,
    )
    check(
        "a patch that does not apply to the base is recorded as such",
        gone["label"] == rx.NOT_ANNOTATED and "does not apply" in gone["error"],
        str(gone),
    )
    lines = [rx.axis_line(aid, s) for aid, s in by.items()]
    check(
        "one card line per axis: what it adds, the label, the entry with its "
        "grade and the source that earned it, or that the dossier has nothing",
        lines[0] == "axis a_lit: adds J2 B -> C — literature-supported "
        "(rx_1, low — rx_1 fixture source 1 (review, same_system))"
        and not any(DECIMAL.search(x) for x in lines)
        and lines[1] == "axis a_inf: adds J3 A -> C — inferred (nothing in the "
        "dossier)"
        and lines[2].startswith("axis a_both: adds J2 B -> C — literature-supported")
        and "; J3 A -> C — inferred" in lines[2]
        and lines[3] == "axis a_same: no new reaction"
        and lines[4].startswith("axis a_bad: not annotated — the patched model")
        and lines[5] == "axis a_obs: no new reaction",
        "\n".join(lines),
    )

    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        tmp = Path(d)
        ctx0 = _axes_ctx(tmp, root, round_idx=0)
        (rnd(root, 0) / rx.DOSSIER_KEY).put(AXIS_DOSSIER)
        ctx = _axes_ctx(tmp, root, round_idx=2)
        check(
            "an expansion reads the dossier of the most recent round that has "
            "one: round 2 finds round 0's",
            rx.latest_dossier(ctx) == (0, AXIS_DOSSIER)
            and rx.latest_dossier(ctx0) == (0, AXIS_DOSSIER),
            str(rx.latest_dossier(ctx)),
        )
        context, _ = model_module.expansion_biology(ctx, ctx.round / "model", {}, "M0")
        check(
            "the expansion agent is shown the dossier and its own instruction, "
            "which the routing table grants it",
            context.get("prior_reactions") == rx.prior_reactions(AXIS_DOSSIER)
            and context.get("grounding_instruction")
            == rx.EXPANSION_GROUNDING_INSTRUCTION
            and "origin: residual" in rx.EXPANSION_GROUNDING_INSTRUCTION
            and not routing.violations("revision", context.keys()),
            str(sorted(context)),
        )
        record = rx.annotate_axes(ctx, AXES[:3], BASE_ANT, BASE_PARAMS, "M0")
        node = rnd(root, 2) / rx.AXIS_SUPPORT_KEY
        check(
            "the offer's annotation is recorded at the round's expansion_support: "
            "the dossier's round, the base, and each axis's support",
            node.get() == record
            and set(record) == {"dossier_round", "base", "axes"}
            and record["dossier_round"] == 0
            and record["base"] == "M0"
            and list(record["axes"]) == ["a_lit", "a_inf", "a_both"]
            and record["axes"]["a_lit"] == by["a_lit"],
            json.dumps(record)[:300],
        )
        card = rx.axis_card_lines(node.get())
        check(
            "the card's block is read from the record, one line per axis",
            len(card) == 4
            and card[0].startswith(
                "REACTIONS each axis adds, against the reaction " "dossier of round 0"
            )
            and card[1] == "  " + rx.axis_line("a_lit", by["a_lit"]),
            "\n".join(card),
        )
        stale = {**AXES[1], "support": {"reactions": [], "label": "old"}}
        check(
            "a bought axis carries its support into the next round's axes, and "
            "one an earlier offer left on it is replaced or dropped",
            rx.with_support(AXES[0], record)["support"] == by["a_lit"]
            and rx.with_support(stale, record)["support"] == by["a_inf"]
            and "support" not in rx.with_support(stale, None),
        )
        from octomod.result.slots import AxisRecord

        check(
            "the typed axis record reads the support as its field",
            AxisRecord(**rx.with_support(AXES[0], record)).support == by["a_lit"],
        )
        off = _axes_ctx(tmp, root, round_idx=3, grounding=False)
        context, _ = model_module.expansion_biology(off, off.round / "model", {}, "M0")
        check(
            "with the module skipped nothing runs and nothing is written: no "
            "dossier in the context, no annotation, no record",
            "prior_reactions" not in context
            and "grounding_instruction" not in context
            and rx.annotate_axes(off, AXES, BASE_ANT, BASE_PARAMS, "M0") is None
            and not (rnd(root, 3) / rx.AXIS_SUPPORT_KEY).exists(),
            str(sorted(context)),
        )
    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        ctx = _axes_ctx(Path(d), root, round_idx=1, grounding=False)
        check(
            "with no module output and no round holding a dossier, the same: "
            "nothing shown, no axis and no model annotated",
            rx.latest_dossier(ctx) is None
            and rx.expansion_context(ctx) == {}
            and rx.annotate_axes(ctx, AXES, BASE_ANT, BASE_PARAMS, "M0") is None
            and not (rnd(root, 1) / rx.AXIS_SUPPORT_KEY).exists()
            and model_module._reaction_support(
                ctx, sbml_of("  J1: A -> B; k1*A;\n"), []
            )
            is None,
        )


def test_declared_axes_floor() -> None:
    """Construction's own axes are held to the variants' floor: at a medium
    base floor (variants' floor low) an axis adding an undescribed conversion
    is refused, one adding a conversion graded low is kept with its line, an
    observation axis is kept."""
    from octomod.workflow_modules.model import model_space as ms
    from octomod.workflow_modules.model import tried_models as _tried
    from tests._record import rnd, temp_record

    kept_axes = [AXES[0], AXES[5]]
    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        ctx = _axes_ctx(Path(d), root, round_idx=0)
        (rnd(root, 0) / rx.DOSSIER_KEY).put(AXIS_DOSSIER)
        got = ms._hold_to_variants_floor(
            ctx, [AXES[0], AXES[1], AXES[5]], BASE_ANT, BASE_PARAMS
        )
        support = (rnd(root, 0) / rx.S1_AXIS_SUPPORT_KEY).get(None) or {}
        dropped = ms.dropped_axes(ctx, module="model")
        rows = [
            e for e in ctx.ledger.entries() if e.get("event") == "axis_refused_floor"
        ]
        check(
            "the declared axes are annotated at the variants' floor and recorded "
            "beside the round's space",
            [a["id"] for a in got] == [a["id"] for a in kept_axes]
            and support.get("floor") == "low"
            and list(support.get("axes") or {}) == ["a_lit", "a_inf", "a_obs"],
            json.dumps(support)[:300],
        )
        want = (
            "  ⚑ REFUSED axis a_inf: adds J3 A -> C — inferred (nothing in the "
            "dossier) is below the variants' floor low; it can return in an "
            "expansion round, when the floor has come down"
        )
        check(
            "an axis adding an undescribed conversion is refused on the card, in "
            "space/dropped and on one ledger row of model",
            [x["id"] for x in dropped] == ["a_inf"]
            and dropped[0]["refused_floor"]["floor"] == "low"
            and ms.dropped_axes_card_lines(ctx, module="model") == [want]
            and len(rows) == 1
            and rows[0].get("module") == "model"
            and rows[0].get("axis") == "a_inf"
            and rows[0].get("floor") == "low",
            "\n".join(ms.dropped_axes_card_lines(ctx, module="model"))
            + json.dumps(rows)[:300],
        )
        card = rx.axis_card_lines(support)
        check(
            "the kept axis carries its annotation line, the observation axis adds "
            "no conversion",
            "held to the variants' floor low" in card[0]
            and "  axis a_lit: adds J2 B -> C — literature-supported (rx_1, low"
            in "\n".join(card)
            and "  axis a_obs: no new reaction" in card,
            "\n".join(card),
        )
        ms._hold_to_variants_floor(ctx, [AXES[1]], BASE_ANT, BASE_PARAMS)
        untested = {
            a["id"] for a in _tried.untested(_tried.declared_axes_this_run(root))
        }
        check(
            "the refused axis is declared, never fitted, so an expansion offers "
            "it again; a second pass adds no ledger row",
            [a["id"] for a in (rnd(root, 0) / "space/declared").get([])] == ["a_inf"]
            and "a_inf" in untested
            and sum(
                1
                for e in ctx.ledger.entries()
                if e.get("event") == "axis_refused_floor"
            )
            == 1,
            str(untested),
        )
    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        import dataclasses
        from types import SimpleNamespace

        from octomod.orchestration.orchestrator import Orchestrator

        ctx = _axes_ctx(Path(d), root, round_idx=0)
        adv = dataclasses.replace(ctx, cache={})
        adv.cache["testcase_yaml"] = {
            **ctx.testcase,
            "grounding": {**FLOOR, "mode": "advisory"},
        }
        (rnd(root, 0) / rx.DOSSIER_KEY).put(AXIS_DOSSIER)
        got = ms._hold_to_variants_floor(
            adv, [AXES[0], AXES[1], AXES[5]], BASE_ANT, BASE_PARAMS
        )
        support = (rnd(root, 0) / rx.S1_AXIS_SUPPORT_KEY).get(None) or {}
        flag = (
            "  ⚑ below the floor low: J3 A -> C — inferred (nothing in the "
            "dossier) (axis a_inf)"
        )
        check(
            "advisory: every declared axis is kept, nothing refused or dropped, "
            "and the card flags the undescribed conversion below the floor",
            [a["id"] for a in got] == ["a_lit", "a_inf", "a_obs"]
            and not ms.dropped_axes(adv, module="model")
            and not any(
                e.get("event") == "axis_refused_floor" for e in adv.ledger.entries()
            )
            and list(support.get("flagged") or {}) == ["a_inf"]
            and flag in rx.axis_card_lines(support),
            "\n".join(rx.axis_card_lines(support)),
        )
        me = SimpleNamespace(ctx=adv, spec=SPEC)
        record = rx.annotate_axes(adv, AXES[:2], BASE_ANT, BASE_PARAMS, "base")
        floor = {"band": "low", "step": 1, "source": "schedule"}
        offered, held, flags = Orchestrator._split_by_floor(me, AXES[:2], record, floor)
        lines = Orchestrator._floor_card_lines(me, floor, held, flags)
        check(
            "advisory: an expansion offers every axis, and its floor block flags "
            "the addition below the floor instead of refusing the axis",
            [a["id"] for a in offered] == ["a_lit", "a_inf"]
            and held == []
            and flag in lines
            and not any("REFUSED" in x for x in lines)
            and "flagged to the person" in lines[1],
            "\n".join(lines),
        )
    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        off = _axes_ctx(Path(d), root, round_idx=0, grounding=False)
        check(
            "with the module skipped every declared axis is kept, nothing recorded",
            ms._hold_to_variants_floor(off, AXES[:2], BASE_ANT, BASE_PARAMS) == AXES[:2]
            and not (rnd(root, 0) / rx.S1_AXIS_SUPPORT_KEY).exists(),
        )


def test_fact_citations() -> None:
    """`model_fact_citations`: a cited fact the dossier lacks fails by name; a
    cited fact whose value differs from the nominal passes, naming both."""
    dossier = {
        "facts": [
            {"id": "fact_1", "statement": "R is 100 nM", "value": 100, "unit": "nM"},
            {"id": "fact_2", "statement": "fast", "value": "fast"},
        ]
    }

    def p(pid, source, nominal=1.0):
        return {"id": pid, "nominal_value": nominal, "source": source}

    none = rx.fact_citation_result([p("k1", "assumed")], dossier)
    ok = rx.fact_citation_result(
        [p("R0", "knowledge:fact_1", 100.0), p("k2", "knowledge: fact_2.")], dossier
    )
    bad = rx.fact_citation_result([p("k3", "knowledge:fact_9")], dossier)
    conv = rx.fact_citation_result([p("R0", "knowledge:fact_1", 0.1)], dossier)
    check(
        "no citation passes; a cited fact of the dossier passes, its value equal "
        "or not numeric: no advisory",
        none.passed
        and none.detail == "no parameter cites a fact"
        and ok.passed
        and ok.blocking
        and ok.tier == "T1"
        and ok.value == {"citations": 2, "missing": 0}
        and not ok.advisory_findings,
        f"{none.detail} / {ok.detail}",
    )
    check(
        "a citation of a fact the dossier does not have fails by name",
        not bad.passed
        and bad.gate_id == "model_fact_citations"
        and bad.detail == "k3 cites knowledge:fact_9, which the dossier does not have",
        bad.detail,
    )
    from octomod.agents import routing
    from octomod.workflow_modules.model import engine as model_module
    from tests._record import rnd, temp_record

    params = [p("R0", "knowledge:fact_1", 100.0), p("k1", "assumed")]
    with tempfile.TemporaryDirectory() as d, temp_record() as root:
        ctx = _axes_ctx(Path(d), root, round_idx=0)
        (rnd(root, 0) / rx.DOSSIER_KEY).put(
            {
                **AXIS_DOSSIER,
                "facts": [{**dossier["facts"][0], "for": ["construction"]}],
            }
        )
        audit = model_module._audit_fact_context(ctx, {"parameters": params})
        off = _axes_ctx(Path(d), root, round_idx=0, grounding=False)
        check(
            "the construction audit is shown the facts routed to construction and "
            "the parameters citing one, which its routing row grants; nothing "
            "with the module skipped",
            [f["id"] for f in audit.get("known_facts") or []] == ["fact_1"]
            and [x["id"] for x in audit.get("cited_parameters") or []] == ["R0"]
            and not routing.violations("construction_verification", audit.keys())
            and model_module._audit_fact_context(off, {"parameters": params}) == {},
            json.dumps(audit)[:300],
        )
    check(
        "a nominal that differs from the cited value passes with an advisory "
        "naming both numbers",
        conv.passed
        and len(conv.advisory_findings) == 1
        and "R0 = 0.1 cites knowledge:fact_1, whose value is 100 nM"
        in conv.advisory_findings[0]
        and conv.advisory_findings[0] in conv.detail,
        conv.detail,
    )


def main() -> int:
    test_equations()
    test_intent_shape()
    test_grade()
    test_dossier()
    test_prior_reactions()
    test_base_set()
    test_fence()
    test_mode()
    test_advisory_gate()
    test_on_a_record()
    test_admission()
    test_role_is_wired()
    test_annotation()
    test_gate_on_a_record()
    test_expansion_axes()
    test_declared_axes_floor()
    test_fact_citations()
    if FAILS:
        print(f"REACTION EVIDENCE UNIT FAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  · {f}")
        return 1
    print(
        "REACTION EVIDENCE UNIT OK — equations, the intent field, the engine's "
        "grade, the dossier, what construction is shown, the base set, the "
        "fence, the grounding mode and the advisory gate, the round's dossier on "
        "a record, admission and the floor, the "
        "wiring, the annotation, the essential gates in S1, the expansion's "
        "axes, construction's own axes at the variants' floor and the cited facts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
