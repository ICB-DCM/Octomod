"""The knowledge module's pure parts and its run-start rules, token-free.

  1. the roles are wired: `knowledge` (one role, online only when a call
     asks) and `knowledge_verification`, each with a contract, a reply class,
     a routing row and a skill; `known_facts` reaches the four roles the facts
     are for; the replaced role is gone;
  2. `process_survey` on a hand-written reply: the required reactions first,
     tagged human, whatever the agent wrote; identifiers checked for their
     shape; facts routed to their roles; evidence fenced and tagged;
  3. the reply battery refuses each failure by name, and flags a quote its
     text document does not contain without refusing; a reply is never
     capped: every reaction it carries is kept;
  4. a targeted search's reply: each entry answers a question, by id;
  5. the audit and the verifier, on fakes (no network); a source string with
     no DOI, PMID or URL is checked by the item's `url`;
  6. `write_staged` and `read_staged` round trip;
  7. `intent_lines` on a temporary record: the lists, the floor, and the intent's
     difference from the one the module saw, by key;
  8. `run_start_problems`: missing output, missing floor, required reactions
     moved, a grounding mode that is not one, a declared skip, online without
     a horizon — and the fence row with the grounding mode;
  9. `inputs_read` carries `knowledge/`, text and bytes;
 10. a staging call through the seam archives its prompt, reply and meta.

    uv run python tests/knowledge_unit.py
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402
from _record import temp_record  # noqa: E402

from octomod.orchestration import run_folder  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.knowledge import engine as kn  # noqa: E402
from octomod.workflow_modules.knowledge import reaction_evidence as rxe  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")

INTENT = {
    "question": "does X respond to the stimulus as the module predicts?",
    "system": "a two-state module (unit test)",
    "required_entities": ["X", "Xp"],
    "required_reactions": [
        {"equation": "X -> Xp", "note": "the stimulus drives it"},
        "Xp -> Y",
    ],
    "required_predictions": ["Xp time course"],
    "inference_target": "prediction",
}

SUPPLIED = [
    {
        "source": "a paper the person staged",
        "title": "Staged paper",
        "year": 2020,
        "supports": "X is phosphorylated",
        "url": "file:./paper/staged.txt",
    }
]


def item(**over) -> dict:
    base = {
        "source": "doi:10.1000/unit.1",
        "title": "A unit-test source",
        "year": 2019,
        "locator": "figure 1",
        "supports": "the conversion happens",
        "quote": "the conversion happens",
        "url": "https://doi.org/10.1000/unit.1",
        "evidence_kind": "direct_experimental",
        "context_match": "same_system",
        "context_note": "the same cells",
        "stance": "supports",
    }
    base.update(over)
    return base


def good_reply() -> dict:
    return {
        "system": {
            "summary": "X is activated by the stimulus and returns to X.",
            "scope": "one cell line",
            "unknowns": ["the phosphatase"],
        },
        "species": [
            {
                "id": "X",
                "name": "X",
                "represents": "X",
                "identifiers": {
                    "uniprot": "uniprot:P12345",
                    "go_compartment": "GO:0005829",
                },
            },
            {"id": "Xp", "name": "active X", "represents": "Xp"},
            {"id": "Y", "name": "Y", "represents": ""},
            {"id": "Z", "name": "the phosphatase", "represents": ""},
        ],
        "reactions": [
            {
                "equation": "X -> Xp",
                "required": "req_1",
                "essential": False,
                "evidence": [item(), item(source="lit_1", url="", quote="")],
            },
            {
                "equation": "Xp -> Y",
                "required": "req_2",
                "evidence": [],
            },
            {
                "equation": "Xp -> X",
                "essential": True,
                "modifiers": ["Z"],
                "type": "dephosphorylation",
                "identifiers": {
                    "reactome": "reactome:R-HSA-123456",
                    "rhea": "rhea:12345",
                },
                "evidence": [
                    item(
                        source="doi:10.1000/unit.2",
                        url="https://doi.org/10.1000/unit.2",
                    ),
                    item(
                        source="PMID: 1234567",
                        url="",
                        stance="contradicts",
                        evidence_kind="indirect",
                    ),
                ],
            },
            {
                "equation": "Y ->",
                "essential": False,
                "evidence": [item(source="https://example.org/y", url="")],
            },
        ],
        "facts": [
            {
                "kind": "rate",
                "statement": "X is converted within minutes",
                "value": 0.5,
                "unit": "1/min",
                "applies_to": ["X"],
                "for": ["construction"],
                "evidence": [item()],
            },
            {
                "kind": "assay",
                "statement": "the readout is in arbitrary units",
                "applies_to": "the assay",
                "for": "observation",
                "evidence": [],
            },
            {
                "kind": "response",
                "statement": "a second stimulus activates Y",
                "for": ["expansion", "condition"],
                "evidence": [item(source="doi:10.1000/unit.3")],
            },
        ],
        "queries_run": ["X activation kinetics"],
        "notes": "the phosphatase is not identified",
    }


def survey(reply=None, required=None):
    req = rxe.required_reactions(INTENT) if required is None else required
    return kn.process_survey(
        copy.deepcopy(reply if reply is not None else good_reply()),
        req,
        ["blocked.example"],
        2025,
        kn._lit.normalized(SUPPLIED),
    )


# ------------------------------------------------------------ 1 · the wiring


def test_roles_are_wired() -> None:
    from octomod.agents import (
        ONLINE_ROLES,
        ROLES,
        AgentCallError,
        agent_timing,
        build_prompt,
        granted_tools,
        routing,
        tools_statement,
    )
    from octomod.config import SKILLS_DIR
    from octomod.result.agent_replies import REPLY_CLASSES, required_fields

    for role, keys in (
        (kn.ROLE, {"reactions", "facts", "queries_run", "notes"}),
        (kn.VERIFY_ROLE, {"classifications"}),
    ):
        check(
            f"{role}: a contract, a reply class, a routing row, a skill, a line",
            role in ROLES
            and role in REPLY_CLASSES
            and role in routing.ROUTING
            and (SKILLS_DIR / f"{role}.md").is_file()
            and role in agent_timing.DOING
            and set(required_fields(role)) == set(ROLES[role].required_keys) == keys,
        )
    check(
        "the replaced search role is gone everywhere",
        "reaction_research" not in ROLES
        and "reaction_research" not in routing.ROUTING
        and "reaction_research" not in REPLY_CLASSES
        and "reaction_research" not in ONLINE_ROLES
        and not (SKILLS_DIR / "reaction_research.md").exists(),
    )
    check(
        "one role, two grants: offline unless a call asks; online is research's",
        granted_tools(kn.ROLE) == ()
        and granted_tools(kn.ROLE, False) == ()
        and granted_tools(kn.ROLE, True) == ONLINE_ROLES["research"]
        and granted_tools("research") == ONLINE_ROLES["research"],
    )
    try:
        granted_tools("construction", True)
        widened = True
    except AgentCallError:
        widened = False
    check("a call can narrow a grant, never widen one", not widened)
    online = build_prompt(kn.ROLE, {"mode": "survey"}, SPEC, online=True)
    offline = build_prompt(kn.ROLE, {"mode": "survey"}, SPEC, online=False)
    check(
        "the prompt states the call's grant",
        "TOOLS: WebSearch, WebFetch" in online
        and "TOOLS: none" in offline
        and tools_statement(kn.ROLE) == tools_statement(kn.ROLE, False),
    )
    sees = routing.allowed(kn.ROLE)
    check(
        "knowledge sees the intent, the note, the required reactions, the supplied "
        "literature, the restrictions, and in targeted mode its questions",
        {
            "intent",
            "experiment_description",
            "required_reactions",
            "supplied_literature",
            "restrictions",
            "mode",
            "questions",
            "model_summary",
            "essential_ids",
        }
        <= sees
        and not (
            {"data_file_previews", "data_signals", "design_summary", "data_labels"}
            & sees
        ),
        str(sorted(sees)),
    )
    check(
        "the verifier sees its items and excerpts, and nothing else",
        routing.allowed(kn.VERIFY_ROLE) - set(routing.COMMON) == {"items", "excerpts"},
    )
    check(
        "known_facts reaches construction, the observation model, the condition "
        "encoding and the expansion agent",
        all(
            "known_facts" in routing.allowed(r)
            for r in (
                "construction",
                "observation",
                "condition",
                "revision",
            )
        )
        and all(
            "known_facts" in ROLES[r].contract
            for r in (
                "construction",
                "observation",
                "condition",
                "revision",
            )
        )
        and 'source: "knowledge:<fact id>"' in ROLES["construction"].contract,
    )
    check(
        "the supplied literature reaches the knowledge role",
        "knowledge" in kn._lit.reaches(),
        str(kn._lit.reaches()),
    )


# ------------------------------------------------------------ 2 · the survey


def test_process_survey() -> None:
    d = survey()
    ids = [r["id"] for r in d["reactions"]]
    check(
        "the required reactions come first, then the further ones in reply order",
        ids == ["req_1", "req_2", "rx_1", "rx_2"],
        str(ids),
    )
    r1 = d["reactions"][0]
    check(
        "a required reaction is the person's: required, essential, origin human, "
        "addressed — the agent's `essential: false` changes nothing",
        r1["required"] is True
        and r1["essential"] is True
        and r1["origin"] == "human"
        and r1["addressed"] is True
        and r1["note"] == "the stimulus drives it",
    )
    rx1 = d["reactions"][2]
    check(
        "a further reaction: origin knowledge, essential as given, modifiers kept",
        rx1["origin"] == "knowledge"
        and rx1["essential"] is True
        and rx1["required"] is False
        and rx1["modifiers"] == ["Z"],
    )
    check(
        "evidence items: ids, stance kept, origin knowledge — or human for a "
        "supplied paper cited by its lit_k id",
        [it["id"] for it in r1["evidence"]] == ["req_1.e1", "req_1.e2"]
        and r1["evidence"][0]["origin"] == "knowledge"
        and r1["evidence"][0]["stance"] == "supports"
        and r1["evidence"][1]["origin"] == "human"
        and r1["evidence"][1]["source"] == "a paper the person staged"
        and rx1["evidence"][1]["stance"] == "contradicts",
    )
    x = next(s for s in d["species"] if s["id"] == "X")
    check(
        "species identifiers kept in their canonical spelling",
        x["identifiers"]
        == {"uniprot": "uniprot:P12345", "go_compartment": "go:0005829"},
        str(x["identifiers"]),
    )
    check(
        "reaction identifiers kept",
        rx1["identifiers"]
        == {"reactome": "reactome:R-HSA-123456", "rhea": "rhea:12345"},
    )
    facts = d["facts"]
    check(
        "facts: ids, origin knowledge, `for` as lists, the declared-empty evidence",
        [f["id"] for f in facts] == ["fact_1", "fact_2", "fact_3"]
        and all(f["origin"] == "knowledge" for f in facts)
        and facts[1]["for"] == ["observation"]
        and facts[1]["applies_to"] == ["the assay"]
        and facts[1]["evidence"] == []
        and facts[1]["evidence_declared"] is True,
    )
    check(
        "the facts are routed to the roles they are for",
        [f["id"] for f in kn.facts_for(d, "construction")] == ["fact_1"]
        and [f["id"] for f in kn.facts_for(d, "observation")] == ["fact_2"]
        and [f["id"] for f in kn.facts_for(d, "condition")] == ["fact_3"]
        and [f["id"] for f in kn.facts_for(d, "revision")] == ["fact_3"]
        and kn.facts_by_role(d)
        == {
            "construction": 1,
            "observation": 1,
            "condition": 1,
            "expansion": 1,
        },
    )
    check(
        "the dossier carries its representation's keys",
        {
            "system",
            "species",
            "reactions",
            "facts",
            "queries_run",
            "notes",
            "mode",
            "horizon",
            "forbidden_sources",
            "dropped",
        }
        <= set(d)
        and d["mode"] == "online"
        and d["horizon"] == 2025
        and d["forbidden_sources"] == ["blocked.example"],
    )
    bad = good_reply()
    bad["species"][0]["identifiers"] = {"uniprot": "P12345", "chebi": "chebi:abc"}
    bad["reactions"][2]["identifiers"] = {"kegg": "kegg:R1", "pathway": "x:1"}
    bad["facts"][0]["for"] = ["construction", "reader"]
    bad["reactions"][2]["evidence"].append(
        item(source="Blocked preprint", url="https://blocked.example/x")
    )
    bad["reactions"][2]["evidence"].append(item(source="Late", year=2030))
    d2 = survey(bad)
    x2 = next(s for s in d2["species"] if s["id"] == "X")
    rx = d2["reactions"][2]
    check(
        "a malformed identifier is dropped, each with a note on its entry",
        x2["identifiers"] == {}
        and len(x2["identifier_notes"]) == 2
        and rx["identifiers"] == {}
        and len(rx["identifier_notes"]) == 2,
        str((x2, rx.get("identifier_notes"))),
    )
    check(
        "a role a fact cannot be for is dropped and recorded",
        d2["facts"][0]["for"] == ["construction"]
        and d2["facts"][0]["for_dropped"] == ["reader"],
    )
    check(
        "the fence: the blocklist and the horizon take items out, recorded",
        len(rx["evidence"]) == 2
        and sorted(f["reason"] for f in rx["evidence_dropped"])
        == ["blocklist", "published after 2025"],
    )


# ------------------------------------------------------------ 3 · the battery


def test_battery() -> None:
    req = rxe.required_reactions(INTENT)
    check("a good reply passes", kn.battery(survey(), None, req) == [])

    def fails(edit, *, required=None) -> list[str]:
        r = good_reply()
        edit(r)
        return kn.battery(survey(r, required), None, required or req)

    cases = {
        "an equation that does not parse": (
            lambda r: r["reactions"].append({"equation": "X-P -> X"}),
            "reactions[4] ('X-P -> X') was not kept: equation:",
        ),
        "a required reaction the reply gives no entry": (
            lambda r: r["reactions"].pop(1),
            "gives no entry for required reaction req_2 (Xp -> Y)",
        ),
        "an essential reaction's unclassified item": (
            lambda r: r["reactions"][2]["evidence"][0].pop("context_match"),
            "rx_1.e1 carries no valid context_match: an unclassified item counts 0",
        ),
        "a malformed identifier": (
            lambda r: r["species"][0].update(identifiers={"chebi": "chebi:x"}),
            "species X: identifier chebi='chebi:x' is not of the declared shape",
        ),
        "a source with no DOI, PMID, URL or supplied paper": (
            lambda r: r["reactions"][3]["evidence"].append(
                item(source="Smith et al.", url="")
            ),
            "names no DOI, PMID, URL, database identifier or supplied paper",
        ),
        "an id `species` lacks": (
            lambda r: r["species"].pop(3),
            "the equations use Z, which `species` lacks",
        ),
        "a fact without a kind": (
            lambda r: r["facts"][0].update(kind="opinion"),
            "fact fact_1: kind 'opinion' is not one of",
        ),
        "a fact without a statement": (
            lambda r: r["facts"][0].update(statement=""),
            "fact fact_1 has no statement",
        ),
        "a fact without its evidence list": (
            lambda r: r["facts"][1].pop("evidence"),
            "fact fact_2 carries no evidence list",
        ),
        "a fact for no role": (
            lambda r: r["facts"][0].update({"for": []}),
            "fact fact_1 names no role it is `for`",
        ),
        "no system summary": (
            lambda r: r.pop("system"),
            "the reply carries no `system` object",
        ),
        "no facts list": (
            lambda r: r.pop("facts"),
            "the reply carries no `facts` list",
        ),
        "a `required` id the intent does not have": (
            lambda r: r["reactions"][3].update(required="req_9"),
            "`required: req_9` names no required reaction of the intent",
        ),
    }
    for name, (edit, want) in cases.items():
        got = fails(edit)
        check(
            f"refused by name: {name}",
            any(want in f for f in got),
            " | ".join(got)[:400],
        )
    # the quote check: found, not found, a document that is not text
    d = survey()
    texts = {
        "https://doi.org/10.1000/unit.1": "Here   the conversion\nhappens, in cells.",
        "https://doi.org/10.1000/unit.2": "Nothing about it here.",
    }
    failures = kn.battery(d, texts, req)
    rx1 = d["reactions"][2]
    check(
        "a quote in its text document is found, whitespace normalised",
        d["reactions"][0]["evidence"][0].get("quote_found") is True,
    )
    check(
        "a quote its text document does not contain is flagged, kept, not refused",
        rx1["evidence"][0].get("quote_found") is False
        and len(rx1["evidence"]) == 2
        and failures == [],
        str(failures),
    )
    check(
        "an item whose document is not cached is left unchecked",
        "quote_found" not in rx1["evidence"][1],
    )
    check(
        "a document that is not text is not read for quotes",
        kn.document_text(b"%PDF-1.4 \x00\x01", "application/pdf") is None
        and "happens" in kn.document_text(b"<p>it happens</p>", "text/html"),
    )


# ------------------------------------------------------------ 4 · targeted


def test_targeted() -> None:
    known = survey()["reactions"]
    reply = {
        "reactions": [
            {
                "equation": "Xp -> Y",
                "answers": "q_1",
                "evidence": [item(source="doi:10.1000/unit.9")],
            },
            {"equation": "Y -> X", "answers": "q_7", "evidence": []},
        ],
        "facts": [
            {
                "kind": "rate",
                "statement": "Y returns to X slowly",
                "for": ["construction"],
                "answers": "q_2",
                "evidence": [],
            }
        ],
        "queries_run": [],
        "notes": "",
    }
    d = kn.process_targeted(
        reply,
        [{"id": "q_1", "question": "how does Xp become Y?"}, "is Y recycled?"],
        [],
        2025,
        prefix="s2",
        requested_by="construction",
        known=known,
    )
    rows = d["reactions"]
    check(
        "a targeted reply: its own ids, origin search, the question it answers",
        [r["id"] for r in rows] == ["s2_rx_1", "s2_rx_2"]
        and all(r["origin"] == "search" for r in rows)
        and rows[0]["answers"] == ["q_1"]
        and d["facts"][0]["id"] == "s2_fact_1"
        and d["facts"][0]["answers"] == ["q_2"]
        and [q["id"] for q in d["questions"]] == ["q_1", "q_2"],
        str([(r["id"], r.get("answers")) for r in rows]),
    )
    check(
        "requested_by on every entry; a conversion already known names it",
        all(r.get("requested_by") == "construction" for r in rows)
        and rows[0].get("duplicates") == "req_2",
    )
    got = kn.battery(d)
    check(
        "an entry answering no asked question is refused by name",
        any("answers ['q_7']" in f for f in got),
        " | ".join(got),
    )


# ------------------------------------------------------------ 5 · audit, verifier


def test_audit_and_verify() -> None:
    d = survey()
    d["reactions"][3]["evidence"][0]["source"] = "reactome:R-HSA-123456"
    fetched, resolved, typed = [], [], []

    def cache(url):
        fetched.append(url)
        return {"fetch_status": "cached", "cached_file": f"{len(fetched)}.txt"}

    def resolve(src):
        resolved.append(src)
        return "unresolvable" if "unit.2" in src else "resolved"

    def pub(it):
        typed.append(kn.source_key(it))
        return ["Review"] if "unit.3" in str(it.get("source")) else ["Journal Article"]

    kn.audit(d, cache, True, publication_types=pub, resolve=resolve)
    items = [it for _e, it in kn._all_items(d)]
    check(
        "each distinct document is cached once and each source looked up once",
        len(fetched) == len(set(fetched))
        and len(resolved) == len(set(resolved))
        and len(typed) == len(set(typed)),
    )
    check(
        "every item carries its resolution and class",
        all(it.get("resolution_class") for it in items)
        and d["reactions"][2]["evidence"][0]["resolution_class"] == "unresolvable",
    )
    check(
        "publication types and the metadata class are noted",
        d["facts"][2]["evidence"][0].get("publication_types") == ["Review"]
        and d["facts"][2]["evidence"][0].get("metadata_class") == "review"
        and d["reactions"][3]["evidence"][0].get("metadata_class")
        == "curated_database",
    )
    d = survey()
    texts = {"https://doi.org/10.1000/unit.1": "x " * 900 + "the conversion happens."}
    ex = kn.excerpts_for(d, texts, bound=200)
    check(
        "an excerpt is the text around the quote, bounded",
        "req_1.e1" in ex
        and "the conversion happens" in ex["req_1.e1"]
        and len(ex["req_1.e1"]) <= 200,
    )
    asked = {}

    def call(role, context):
        asked["role"], asked["context"] = role, context
        return {
            "classifications": [
                {
                    "id": "rx_1.e1",
                    "evidence_kind": "indirect",
                    "context_match": "same_system",
                    "stance": "supports",
                    "note": "a mention",
                },
                {"id": "nope.e1", "evidence_kind": "review"},
            ]
        }

    out = kn.verify(d, call, ex)
    target = d["reactions"][2]["evidence"][0]
    check(
        "the verifier is asked about the counting items, with their excerpts",
        asked["role"] == kn.VERIFY_ROLE
        and set(asked["context"]) == {"items", "excerpts"}
        and "req_1.e1" in {i["id"] for i in asked["context"]["items"]},
    )
    check(
        "its classification lands as second_kind / second_context / second_stance",
        target.get("second_kind") == "indirect"
        and target.get("second_context") == "same_system"
        and target.get("second_stance") == "supports"
        and target.get("second_note") == "a mention"
        and out["n_disagree"] == 1
        and out["unknown_ids"] == ["nope.e1"],
        str(out),
    )


def test_citation_target() -> None:
    d = survey()
    target = d["reactions"][2]["evidence"][0]
    target["source"] = "Smith et al., a supplied paper (2012)"
    target["url"] = "https://doi.org/10.1000/unit.9"
    resolved = []

    def resolve(src):
        resolved.append(src)
        return "resolved"

    kn.audit(d, lambda url: {"fetch_status": "cached"}, True, resolve=resolve)
    check(
        "a source string with no DOI, PMID or URL is checked by its `url`",
        "https://doi.org/10.1000/unit.9" in resolved
        and "Smith et al., a supplied paper (2012)" not in resolved
        and target["resolution"] == "resolved",
        str(resolved),
    )
    check(
        "… while a source that names one is checked by it, and a source with "
        "neither is looked up as written",
        kn.citation_target({"source": "doi:10.1000/a", "url": "https://x.org"})
        == "doi:10.1000/a"
        and kn.citation_target({"source": "PMID: 1234567", "url": "https://x.org"})
        == "PMID: 1234567"
        and kn.citation_target({"source": "see https://x.org/a", "url": "file:./b"})
        == "see https://x.org/a"
        and kn.citation_target({"source": "a lab note", "url": ""}) == "a lab note",
    )


def test_no_cap() -> None:
    reply = good_reply()
    reply["reactions"] += [
        {"equation": f"Xp -> P{k}", "essential": False, "evidence": []}
        for k in range(45)
    ]
    reply["species"] += [
        {"id": f"P{k}", "name": f"P{k}", "represents": ""} for k in range(45)
    ]
    d = survey(reply)
    further = [r for r in d["reactions"] if not r.get("required")]
    failures = kn.battery(d, None, rxe.required_reactions(INTENT))
    check(
        "a reply of 47 further reactions keeps every one, and its length is "
        "never a refusal",
        len(further) == 47
        and not any(
            str(x.get("what", "")).startswith("reactions[") for x in d["dropped"]
        )
        and not any("was not kept" in f for f in failures),
        str(failures)[:300],
    )


# ------------------------------------------------------------ 6 · the folder


def test_round_trip(tmp: Path) -> None:
    case = tmp / "roundtrip"
    case.mkdir()
    d = survey()
    metas = [
        {"name": "knowledge.1", "role": "knowledge", "cost_usd": 0.5, "sha": "abc"},
        {"name": "knowledge_verification.1", "role": "knowledge_verification"},
    ]
    (case / "knowledge" / "calls").mkdir(parents=True)
    for m in metas:
        (case / "knowledge" / "calls" / f"{m['name']}.meta.json").write_text(
            json.dumps(m)
        )
    (case / "knowledge" / "sources").mkdir()
    (case / "knowledge" / "sources" / "abc.txt").write_text("a document")
    text = yaml.safe_dump(INTENT, sort_keys=False)
    path = kn.write_staged(case, d, metas, text)
    back = kn.read_staged(case)
    check(
        "write_staged and read_staged round trip",
        path == case / "knowledge" / "knowledge.json"
        and back["knowledge"]["reactions"] == json.loads(json.dumps(d["reactions"]))
        and back["knowledge"]["cost_usd"] == 0.5
        and [c["name"] for c in back["knowledge"]["calls"]]
        == ["knowledge.1", "knowledge_verification.1"]
        and back["intent_before"] == INTENT
        and back["sources"] == ["abc.txt"]
        and len(back["calls"]) == 2,
    )
    check("no folder: None", kn.read_staged(tmp / "nowhere") is None)
    (case / "knowledge" / "knowledge.json").write_text("{not json")
    try:
        kn.read_staged(case)
        refused = False
    except ValueError as e:
        refused = "knowledge.json" in str(e)
    check("an unreadable json is refused by name", refused)


# ------------------------------------------------------------ 7/8 · run start


def _graded(mode="online") -> dict:
    d = survey()
    d["mode"] = mode
    rxe.grade_reactions(d, SPEC)
    d["suggestion"] = rxe.suggest_floor(kn.essential_entries(d), mode=mode)
    return d


def _case(tmp: Path, name: str, *, testcase: dict, intent=None, dossier=None) -> Path:
    case = tmp / name
    (case / "data").mkdir(parents=True)
    (case / "data" / "x.csv").write_text("t,y\n0,1\n")
    (case / "intent.yaml").write_text(
        yaml.safe_dump(intent if intent is not None else INTENT, sort_keys=False)
    )
    (case / "testcase.yaml").write_text(yaml.safe_dump(testcase, sort_keys=False))
    if dossier is not None:
        kn.write_staged(case, dossier, [], yaml.safe_dump(INTENT, sort_keys=False))
    return case


DECIDED = {
    "name": "unit",
    "research": {"max_publication_year": 2025},
    "grounding": {"support_floor": "medium", "floor_step": 1, "decided_by": "human"},
}


def test_run_start(tmp: Path) -> None:
    def problems(case: Path) -> list[str]:
        tc = yaml.safe_load((case / "testcase.yaml").read_text())
        intent = yaml.safe_load((case / "intent.yaml").read_text())
        return kn.run_start_problems(case, tc, intent, SPEC, source="staging/unit")

    ok = _case(tmp, "ok", testcase=DECIDED, dossier=_graded())
    check("a staged, decided case starts", problems(ok) == [], str(problems(ok)))
    got = problems(_case(tmp, "no_json", testcase={"name": "unit"}))
    check(
        "no module output: run the knowledge module first, by name",
        len(got) == 1
        and "run the knowledge module first" in got[0]
        and "./run.sh knowledge --testcase staging/unit" in got[0],
        str(got),
    )
    got = problems(
        _case(
            tmp,
            "no_floor",
            testcase={"name": "unit", "research": {"max_publication_year": 2025}},
            dossier=_graded(),
        )
    )
    check(
        "no floor: decide the support floor, naming the card",
        len(got) == 1
        and "decide the support floor" in got[0]
        and "./run.sh knowledge --show" in got[0],
        str(got),
    )
    bad = copy.deepcopy(DECIDED)
    bad["grounding"]["support_floor"] = "very high"
    got = problems(_case(tmp, "bad_floor", testcase=bad, dossier=_graded()))
    check(
        "a floor that is not a band is refused by name",
        len(got) == 1 and "not usable" in got[0] and "very high" in got[0],
        str(got),
    )
    moved = copy.deepcopy(INTENT)
    moved["required_reactions"].append("Y -> X")
    got = problems(
        _case(tmp, "moved", testcase=DECIDED, intent=moved, dossier=_graded())
    )
    check(
        "the intent's required reactions moved: re-run the module, naming what moved",
        len(got) == 1
        and "re-run the knowledge module" in got[0]
        and "added Y -> X" in got[0],
        str(got),
    )
    no_horizon = {k: v for k, v in DECIDED.items() if k != "research"}
    got = problems(_case(tmp, "horizon", testcase=no_horizon, dossier=_graded()))
    check(
        "online without the case's horizon is refused as the fence refuses it",
        len(got) == 1 and "max_publication_year" in got[0],
        str(got),
    )
    got = problems(
        _case(tmp, "offline", testcase=no_horizon, dossier=_graded("offline"))
    )
    check("offline needs no horizon", got == [], str(got))
    bad = copy.deepcopy(DECIDED)
    bad["grounding"]["mode"] = "lenient"
    got = problems(_case(tmp, "bad_mode", testcase=bad, dossier=_graded()))
    check(
        "a grounding mode that is not one is refused by name, with the modes",
        len(got) == 1
        and "grounding.mode 'lenient'" in got[0]
        and "advisory, strict" in got[0],
        str(got),
    )
    skip = {"name": "unit", "grounding": {"skip": True, "why": "fixture"}}
    check(
        "a declared skip runs as today: nothing refused, no folder needed",
        problems(_case(tmp, "skip", testcase=skip)) == [],
    )
    got = problems(
        _case(tmp, "skip_no_why", testcase={"name": "u", "grounding": {"skip": True}})
    )
    check(
        "a skip without its why is refused by name",
        len(got) == 1 and "why" in got[0],
        str(got),
    )
    row = kn.grounding_fence_row(ok, DECIDED, SPEC)
    check(
        "the fence row: mode, floor, its source, the step, horizon, forbidden sources",
        row["mode"] == "online"
        and row["support_floor"] == "medium"
        and row["floor_source"] == "human"
        and row["floor_step"] == 1
        and row["horizon"] == 2025
        and row["forbidden_sources"] == [],
        str(row),
    )
    strict = copy.deepcopy(DECIDED)
    strict["grounding"]["mode"] = "strict"
    check(
        "the fence row names the grounding mode: advisory by default, the "
        "case's when it declares one",
        row["grounding_mode"] == "advisory"
        and "advisory mode" in row["note"]
        and kn.grounding_fence_row(ok, strict, SPEC)["grounding_mode"] == "strict",
        str(row),
    )
    row = kn.grounding_fence_row(tmp / "skip", skip, SPEC)
    check("… and a skip's row says the skip", row.get("skip") == "fixture", str(row))


def test_s0_lines(tmp: Path) -> None:
    case = _case(tmp, "s0", testcase=DECIDED, dossier=_graded())
    frozen = copy.deepcopy(INTENT)
    frozen["question"] = "a sharper question"
    frozen["scope_exclusions"] = ["synthesis"]
    (case / "intent.yaml").write_text(yaml.safe_dump(frozen, sort_keys=False))
    with temp_record("s0") as root:
        run_folder.snapshot(case, root)
        ctx = SimpleNamespace(
            root=root, testcase_dir=case, testcase=DECIDED, spec=SPEC, round_idx=0
        )
        check("the record holds the module's output", kn.has_staged(ctx))
        lines = kn.intent_lines(ctx, frozen)
        text = "\n".join(lines)
        check(
            "the card: the required and the essential lists with grade and origin",
            "required (2):" in text
            and "req_1  X -> Xp" in text
            and "origin human" in text
            and "essential (1):" in text
            and "rx_1  Xp -> X" in text
            and "origin knowledge" in text,
            text,
        )
        check(
            "the floor and who set it; the facts per role",
            "support floor:   medium (the person), step 1" in text
            and "facts by role:   construction 1" in text,
            text,
        )
        check(
            "the intent's difference names each key that moved, one line each",
            "changed question:" in text
            and "added scope_exclusions:" in text
            and "(2 key(s))" in text,
            text,
        )
        same = kn.intent_lines(ctx, INTENT)
        check(
            "the same intent: no change",
            any("intent vs the one the module saw: no change" in x for x in same),
            "\n".join(same),
        )
    with temp_record("intent_none") as root:
        bare = tmp / "bare"
        (bare / "data").mkdir(parents=True)
        (bare / "intent.yaml").write_text("question: q\n")
        run_folder.snapshot(bare, root)
        ctx = SimpleNamespace(root=root, testcase_dir=bare, testcase={}, spec=SPEC)
        check(
            "no module output: no lines",
            not kn.has_staged(ctx) and kn.intent_lines(ctx) == [],
        )


# ------------------------------------------------------------ 9 · inputs_read


def test_inputs_read(tmp: Path) -> None:
    case = tmp / "inputs"
    (case / "knowledge" / "sources").mkdir(parents=True)
    (case / "knowledge" / "calls").mkdir()
    (case / "stubs").mkdir()
    (case / "sources").mkdir()
    (case / "intent.yaml").write_text("question: q\n")
    (case / "knowledge" / "knowledge.json").write_text(
        json.dumps(
            {"facts": [{"evidence": [{"url": "file:./sources/from_knowledge.txt"}]}]}
        )
    )
    (case / "knowledge" / "intent_before.yaml").write_text("question: q\n")
    (case / "knowledge" / "sources" / "a1b2.txt").write_text("a cached document\n")
    pdf = b"%PDF-1.4\x00\x01\x02 not text"
    (case / "knowledge" / "sources" / "c3d4.pdf").write_bytes(pdf)
    (case / "knowledge" / "calls" / "knowledge.1.prompt.txt").write_text("prompt\n")
    (case / "knowledge" / "calls" / "knowledge.1.meta.json").write_text("{}\n")
    (case / "stubs" / "knowledge.json").write_text(
        json.dumps(
            {"facts": [{"evidence": [{"url": "file:./sources/from_stub_fact.txt"}]}]}
        )
    )
    for name in ("from_knowledge.txt", "from_stub_fact.txt", "unnamed.txt"):
        (case / "sources" / name).write_text(name + "\n")
    got = [p.as_posix() for p in run_folder.inputs_read(case)]
    want = [
        "intent.yaml",
        "knowledge/calls/knowledge.1.meta.json",
        "knowledge/calls/knowledge.1.prompt.txt",
        "knowledge/intent_before.yaml",
        "knowledge/knowledge.json",
        "knowledge/sources/a1b2.txt",
        "knowledge/sources/c3d4.pdf",
        "sources/from_knowledge.txt",
        "sources/from_stub_fact.txt",
        "stubs/knowledge.json",
    ]
    check(
        "inputs_read carries every file under knowledge/, and the case documents a "
        "fact's evidence names",
        got == want,
        str(got),
    )
    with temp_record("inputs") as root:
        run_folder.snapshot(case, root)
        check(
            "the snapshot keeps the bytes of a document that is not text",
            run_folder.read_bytes(root, "knowledge/sources/c3d4.pdf") == pdf
            and run_folder.read_bytes(root, "knowledge/sources/a1b2.txt")
            == b"a cached document\n",
        )
        check(
            "the folder's identity and its snapshot's agree",
            run_folder.manifest(root)
            == {
                rel.as_posix(): __import__("hashlib")
                .sha256((case / rel).read_bytes())
                .hexdigest()[:16]
                for rel in run_folder.inputs_read(case)
            },
        )


# ------------------------------------------------------------ 10 · the call


def test_staging_call(tmp: Path) -> None:
    from octomod.agents import routing

    case = tmp / "call"
    (case / "stubs").mkdir(parents=True)
    (case / "stubs" / "knowledge.json").write_text(json.dumps(good_reply()))
    (case / "stubs" / "knowledge.2.json").write_text(
        json.dumps({**good_reply(), "notes": "the second reply"})
    )
    with kn.StagingSession(case, spec=SPEC, backend="stub") as s:
        r1, m1 = s.call(kn.ROLE, {"mode": "survey", "intent": INTENT}, online=True)
        r2, m2 = s.call(kn.ROLE, {"mode": "survey", "intent": INTENT}, online=False)
        try:
            s.call(kn.ROLE, {"mode": "survey", "data_signals": {}})
            leaked = True
        except routing.RoutingViolation:
            leaked = False
    calls = case / "knowledge" / "calls"
    check(
        "each call's prompt, reply and meta are archived as files, numbered",
        all(
            (calls / f"knowledge.{n}.{ext}").is_file()
            for n in (1, 2)
            for ext in ("prompt.txt", "reply.json", "meta.json")
        ),
        str(sorted(p.name for p in calls.glob("*"))),
    )
    check(
        "the stub sequence is served in order within a session",
        r1["notes"] == good_reply()["notes"] and r2["notes"] == "the second reply",
    )
    prompt1 = (calls / "knowledge.1.prompt.txt").read_text()
    prompt2 = (calls / "knowledge.2.prompt.txt").read_text()
    check(
        "the grant is the call's: the online call's prompt names its tools",
        "TOOLS: WebSearch, WebFetch" in prompt1 and "TOOLS: none" in prompt2,
    )
    check(
        "the meta says the role, the modes, the backend, the prompt's sha, when",
        m1["role"] == "knowledge"
        and m1["mode"] == "survey"
        and m1["search"] == "online"
        and m2["search"] == "offline"
        and m1["backend"] == "stub"
        and m1["sha"]
        and m1["at"],
        str(m1),
    )
    check("the routing table is enforced before the call", not leaked)
    log = (case / "curation" / "STAGING_LOG.md").read_text()
    check(
        "one staging-log line per call",
        log.count("· knowledge.1 ·") == 1 and log.count("· knowledge.2 ·") == 1,
        log,
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="octomod_knowledge_unit_"))
    try:
        print("roles")
        test_roles_are_wired()
        print("survey")
        test_process_survey()
        print("battery")
        test_battery()
        print("targeted")
        test_targeted()
        print("audit and verifier")
        test_audit_and_verify()
        test_citation_target()
        print("no cap on the reply")
        test_no_cap()
        print("folder")
        test_round_trip(tmp)
        print("run start")
        test_run_start(tmp)
        print("S0")
        test_s0_lines(tmp)
        print("inputs")
        test_inputs_read(tmp)
        print("staging call")
        test_staging_call(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return finish(
        "\nknowledge_unit",
        "\nOK — the knowledge role, its reply, its battery, its folder and the "
        "run-start rules",
    )


if __name__ == "__main__":
    sys.exit(main())
