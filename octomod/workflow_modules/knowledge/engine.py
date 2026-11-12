"""The knowledge module: what is known about the system, gathered BEFORE the
intent is frozen, and the refusals that make a run wait for it.

1. **The survey** (`./run.sh knowledge --testcase <folder> --mode
   online|offline`, `run_survey`): one call of the role `knowledge` in mode
   `survey` — online (WebSearch and WebFetch, fenced exactly like research)
   when the person allows a literature search, offline otherwise. It returns
   what is known about the system, its species with their identifiers, every
   reaction it finds with the ESSENTIAL ones flagged, and the FACTS a model
   needs beyond its reactions, each with evidence items it CLASSIFIES and
   never grades.
2. **The engine keeps the reply** (`process_survey`): the intent's required
   reactions first, written by the engine from the intent (`req_k`, origin
   `human`) so the agent can neither drop nor relabel one; every equation
   parsed, every evidence item fenced and given its origin, every identifier
   checked for its shape, every fact routed to the roles it is for. The reply
   battery (`battery`) refuses a reply by name, and the agent is asked again
   with the failures.
3. **The audit** (`audit`): every distinct document cached into the folder,
   every identifier looked up, the publication types read (online), the
   metadata class noted. The optional verifier (`verify`, one advisory call of
   `knowledge_verification`) reads each counting item again from the cached
   document's text around its quote.
4. **The grade and the floor** are `reaction_evidence`'s: the engine grades
   every reaction and fact, suggests a support floor and prints the floor
   card; the PERSON decides the floor, and the front end writes the decision
   into testcase.yaml (`grounding: {support_floor, floor_step, decided_by,
   note, dropped, kept}`). This module never writes it.
5. **The folder** (`write_staged`, `read_staged`): `knowledge/knowledge.json`,
   the cached documents under `knowledge/sources/`, every call's prompt,
   reply and meta under `knowledge/calls/`, and `knowledge/intent_before.yaml`,
   the intent as it stood when the module ran. A run snapshots all of it
   (`run_folder.inputs_read`), so the record holds what the module said.
6. **Run start** (`run_start_problems`, `grounding_fence_row`): a case that
   declares no skip cannot start without the module's output and the
   person's floor, nor after its required reactions moved; each refusal names
   its fix. S0's card shows the required and essential lists, the floor and
   the intent's difference from the one the module saw (`intent_lines`).

Outside a run there is no `RunContext`: a staging call (`StagingSession`) goes
through the same seam a run's does — the routing table, `agents.call_agent`
with the call's own grant, its contract and its stubs — into a scratch record
that is discarded, and leaves its prompt, reply and meta as files.
"""

from __future__ import annotations

import datetime
import html
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

import yaml

from octomod.workflow_modules.knowledge import supplied_literature as _lit
from octomod.workflow_modules.knowledge.reaction_evidence import (
    EquationError,
    canonical,
    fence_items,
    parse_equation,
    required_reactions,
    resolution_class,
    restrictions_text,
    source_key,
    supplied_index,
)

ROLE = "knowledge"
VERIFY_ROLE = "knowledge_verification"
# the role's two modes, the context key `mode`
SURVEY, TARGETED = "survey", "targeted"
# the module's two search modes, the dossier's `mode`
ONLINE, OFFLINE = "online", "offline"
SEARCH_MODES = (ONLINE, OFFLINE)

# the staging folder's layout
FOLDER = "knowledge"
DOSSIER_FILE = "knowledge.json"
SOURCES_DIR = "sources"
CALLS_DIR = "calls"
INTENT_BEFORE = "intent_before.yaml"
STAGING_LOG = Path("curation") / "STAGING_LOG.md"

# who proposed an entry: the person (a required reaction), the survey, a
# targeted search inside a run
ORIGIN_HUMAN = _lit.ORIGIN_HUMAN
ORIGIN = "knowledge"
ORIGIN_SEARCH = "search"

# the contract's vocabulary (agents.ROLES["knowledge"])
EVIDENCE_KINDS = (
    "direct_experimental",
    "mechanistic_model",
    "curated_database",
    "review",
    "indirect",
)
CONTEXT_MATCHES = ("same_system", "related_system", "different_system")
STANCES = ("supports", "contradicts")
FACT_KINDS = (
    "abundance",
    "expression",
    "rate",
    "affinity",
    "timescale",
    "stoichiometry",
    "response",
    "assay",
    "unknown",
)
# the roles a fact is for, and the routing-table role each names
FACT_ROLES = ("construction", "observation", "condition", "expansion")
FACT_ROLE_OF = {
    "construction": "construction",
    "observation": "observation",
    "condition": "condition",
    "expansion": "revision",
}

# the declared shape of each identifier, `namespace:id` (the namespace
# case-folded before the match)
SPECIES_IDENTIFIERS = {
    "uniprot": re.compile(
        r"uniprot:(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
        r"(?:-\d+)?"
    ),
    "chebi": re.compile(r"chebi:\d+"),
    "pubchem": re.compile(r"pubchem:\d+"),
    "hgnc": re.compile(r"hgnc:\d+"),
    "go_compartment": re.compile(r"go:\d{7}"),
}
REACTION_IDENTIFIERS = {
    "reactome": re.compile(r"reactome:R-[A-Z]{3}-\d+(?:\.\d+)?"),
    "kegg": re.compile(r"kegg:R\d{5}"),
    "rhea": re.compile(r"rhea:\d+"),
}
SHAPE_EXAMPLE = {
    "uniprot": "uniprot:P12345",
    "chebi": "chebi:15422",
    "pubchem": "pubchem:5957",
    "hgnc": "hgnc:1234",
    "go_compartment": "go:0005829",
    "reactome": "reactome:R-HSA-123456",
    "kegg": "kegg:R00001",
    "rhea": "rhea:12345",
}

# what makes a source checkable: a DOI, a PMID, a URL (a case document by
# `file:` included), a database or model-repository identifier; a supplied
# paper is checkable by its `lit_k` id
_DOI = re.compile(r"10\.\d{4,9}/\S+")
_PMID = re.compile(r"pmid\D{0,3}\d{4,9}", re.I)
_DB_SOURCE = re.compile(
    r"\b(reactome:R-[A-Z]{3}-\d+|kegg:R\d{5}|rhea:\d+|BIOMD\d{4,}|MODEL\d{6,})",
    re.I,
)

# how much of a cached document the verifier reads around an item's quote
EXCERPT_CHARS = 1500

# the evidence item as the module keeps it: the reaction dossier's item plus
# the stance, and the question a targeted search answers
_ITEM_EXTRA = ("stance",)


# ------------------------------------------------------------ identifiers


def _one_identifier(value, key: str, shapes: dict) -> tuple[str | None, str | None]:
    """(the identifier in its canonical spelling, None) or (None, why not)."""
    text = str(value or "").strip()
    if ":" not in text:
        return None, (
            f"identifier {key}={text!r} is not a namespace:id string "
            f"(e.g. {SHAPE_EXAMPLE[key]})"
        )
    ns, rest = text.split(":", 1)
    canon = f"{ns.strip().lower()}:{rest.strip()}"
    if not shapes[key].fullmatch(canon):
        return None, (
            f"identifier {key}={text!r} is not of the declared shape "
            f"(e.g. {SHAPE_EXAMPLE[key]})"
        )
    return canon, None


def identifiers(raw, shapes: dict) -> tuple[dict, list[str]]:
    """The identifiers of one species or reaction, each checked for its
    declared shape: `({key: id or [ids]}, [notes on what was dropped])`. A key
    outside the vocabulary and a malformed identifier are dropped, each with
    a note; a well-formed one keeps the agent's shape (one string, or a
    list)."""
    if raw in (None, {}, []):
        return {}, []
    if not isinstance(raw, dict):
        return {}, [
            f"identifiers must be an object {{{', '.join(shapes)}}}, got "
            f"{type(raw).__name__}"
        ]
    kept: dict = {}
    notes: list[str] = []
    for key, value in raw.items():
        key = str(key).strip().lower()
        if key not in shapes:
            notes.append(
                f"identifier key {key!r} is not one of {', '.join(shapes)} — dropped"
            )
            continue
        values = value if isinstance(value, list) else [value]
        good = []
        for v in values:
            canon, why = _one_identifier(v, key, shapes)
            if canon is None:
                notes.append(f"{why} — dropped")
            elif canon not in good:
                good.append(canon)
        if good:
            kept[key] = good if isinstance(value, list) else good[0]
    return kept, notes


# ------------------------------------------------------------ evidence items


def _items(raw, blocklist, horizon, index, origin: str) -> tuple[list, list]:
    """(kept, fenced): each item through the reaction dossier's fence, with
    the stance kept beside the fields the fence copies, and the origin of an
    item nobody supplied set to who found it (`knowledge`, or `search` for a
    targeted search)."""
    kept, fenced = [], []
    if not isinstance(raw, list):
        return kept, fenced
    for it in raw:
        k, f = fence_items([it], blocklist, horizon, index)
        for row in k:
            for key in _ITEM_EXTRA:
                if isinstance(it, dict) and it.get(key) not in (None, ""):
                    row[key] = it[key]
            if row.get("origin") == _lit.ORIGIN_RESEARCH:
                row["origin"] = origin
        kept += k
        fenced += f
    return kept, fenced


def _checkable(item: dict) -> bool:
    """Does the item name a source the engine can check or the person owns?"""
    if item.get("origin") == ORIGIN_HUMAN:
        return True
    src = str(item.get("source") or "").strip()
    url = str(item.get("url") or "").strip()
    blob = f"{src} {url}"
    return bool(
        _DOI.search(blob)
        or _PMID.search(blob)
        or _DB_SOURCE.search(blob)
        or url.startswith(("http://", "https://", "file:"))
        or src.startswith(("http://", "https://"))
    )


def _all_items(dossier: dict):
    """(entry, item) for every evidence item of every reaction and fact."""
    for key in ("reactions", "facts"):
        for entry in dossier.get(key) or []:
            for it in entry.get("evidence") or []:
                if isinstance(it, dict):
                    yield entry, it


def _number_items(entry: dict) -> None:
    for k, it in enumerate(entry.get("evidence") or [], start=1):
        it["id"] = f"{entry['id']}.e{k}"


# ------------------------------------------------------------ the reply


def _ids(raw) -> list[str]:
    ok = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    return [str(x) for x in (raw or []) if isinstance(x, str) and ok.fullmatch(x)]


def _text_list(raw) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw if str(x).strip()]
    return [str(raw)]


def _required_row(r: dict) -> dict:
    row = {
        "id": r["id"],
        "equation": r["equation"],
        "written": r.get("written", r["equation"]),
        "parsed": r["parsed"],
        "modifiers": list(r.get("modifiers") or []),
        "type": "",
        "description": "",
        "required": True,
        "essential": True,
        "origin": ORIGIN_HUMAN,
        "identifiers": {},
        # whether the agent's reply gave this reaction an entry of its own
        "addressed": False,
        "evidence": [],
        "evidence_dropped": [],
    }
    if r.get("note"):
        row["note"] = r["note"]
    return row


def _merge_reaction(row: dict, raw: dict, kept, fenced) -> None:
    row["evidence"] += kept
    row["evidence_dropped"] += fenced
    for fld in ("type", "description"):
        if raw.get(fld) and not row.get(fld):
            row[fld] = str(raw[fld])
    mods = [m for m in _ids(raw.get("modifiers")) if m not in row["modifiers"]]
    row["modifiers"] += mods
    ids, notes = identifiers(raw.get("identifiers"), REACTION_IDENTIFIERS)
    for key, value in ids.items():
        row["identifiers"].setdefault(key, value)
    if notes:
        row.setdefault("identifier_notes", []).extend(notes)


def _reactions(
    raw_list,
    required: list[dict],
    blocklist,
    horizon,
    index,
    *,
    origin: str,
    prefix: str,
    dropped: list,
) -> list[dict]:
    """The reply's reactions as the module keeps them: the required rows
    first (from the intent, whatever the agent wrote), then one row per
    distinct further conversion, in reply order, numbered `<prefix>_1`, …
    Every conversion the reply carries is kept: the knowledge role's reply
    is not capped."""
    req_by_id = {r["id"]: r for r in required}
    req_by_eq = {r["equation"]: r for r in required}
    req_rows = {r["id"]: _required_row(r) for r in required}
    extra: dict[str, dict] = {}
    for k, raw in enumerate(raw_list if isinstance(raw_list, list) else []):
        if not isinstance(raw, dict):
            dropped.append({"what": f"reactions[{k}]", "reason": "not an object"})
            continue
        try:
            parsed = parse_equation(raw.get("equation"))
        except EquationError as e:
            dropped.append(
                {
                    "what": f"reactions[{k}]",
                    "equation": str(raw.get("equation"))[:200],
                    "reason": f"equation: {e}",
                }
            )
            continue
        eq = canonical(parsed)
        named = str(raw.get("required") or "").strip()
        target = req_by_id.get(named) or req_by_eq.get(eq)
        kept, fenced = _items(raw.get("evidence"), blocklist, horizon, index, origin)
        if target is not None:
            row = req_rows[target["id"]]
            row["addressed"] = True
            if eq != target["equation"]:
                # the agent's spelling of a required reaction: the person's
                # equation stands, and the agent's is on the record beside it
                row.setdefault("agent_equations", [])
                if eq not in row["agent_equations"]:
                    row["agent_equations"].append(eq)
        elif eq in extra:
            row = extra[eq]
            row["essential"] = row["essential"] or bool(raw.get("essential"))
        else:
            row = extra[eq] = {
                "equation": eq,
                "parsed": parsed,
                "modifiers": [],
                "type": "",
                "description": "",
                "required": False,
                "essential": bool(raw.get("essential")),
                "origin": origin,
                "identifiers": {},
                "evidence": [],
                "evidence_dropped": [],
            }
        if named and named not in req_by_id:
            row.setdefault("notes", []).append(
                f"`required: {named}` names no required reaction of the intent"
            )
        if raw.get("answers") not in (None, ""):
            row.setdefault("answers_given", [])
            if str(raw["answers"]) not in row["answers_given"]:
                row["answers_given"].append(str(raw["answers"]))
        _merge_reaction(row, raw, kept, fenced)
    # the id first, so a reader of knowledge.json finds each entry by it
    numbered = [
        {"id": f"{prefix}_{n}", **row} for n, row in enumerate(extra.values(), start=1)
    ]
    rows = list(req_rows.values()) + numbered
    for row in rows:
        _number_items(row)
    return rows


def _species(raw_list, dropped: list) -> list[dict]:
    out: dict[str, dict] = {}
    ok = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for k, s in enumerate(raw_list if isinstance(raw_list, list) else []):
        if not isinstance(s, dict) or not ok.fullmatch(str(s.get("id") or "")):
            dropped.append(
                {
                    "what": f"species[{k}]",
                    "reason": "not an object with an identifier `id` (letters, "
                    "digits and _, not starting with a digit)",
                }
            )
            continue
        sid = str(s["id"])
        ids, notes = identifiers(s.get("identifiers"), SPECIES_IDENTIFIERS)
        row = out.setdefault(
            sid,
            {
                "id": sid,
                "name": str(s.get("name") or ""),
                "represents": str(s.get("represents") or ""),
                "identifiers": {},
            },
        )
        for key, value in ids.items():
            row["identifiers"].setdefault(key, value)
        if notes:
            row.setdefault("identifier_notes", []).extend(notes)
    return list(out.values())


def _facts(
    raw_list, blocklist, horizon, index, *, origin: str, prefix: str, dropped: list
) -> list[dict]:
    """The reply's facts: each with its id (`<prefix>_1`, …), its kind and
    statement as given (the battery checks them), its `for` roles checked
    against the four the engine routes to, its evidence fenced."""
    out = []
    for k, raw in enumerate(raw_list if isinstance(raw_list, list) else []):
        if not isinstance(raw, dict):
            dropped.append({"what": f"facts[{k}]", "reason": "not an object"})
            continue
        kept, fenced = _items(raw.get("evidence"), blocklist, horizon, index, origin)
        roles = [r.strip().lower() for r in _text_list(raw.get("for"))]
        row = {
            "id": f"{prefix}_{len(out) + 1}",
            "kind": str(raw.get("kind") or "").strip().lower(),
            "statement": str(raw.get("statement") or "").strip(),
            "value": raw.get("value"),
            "unit": str(raw.get("unit") or ""),
            "applies_to": _text_list(raw.get("applies_to")),
            "for": [r for r in roles if r in FACT_ROLES],
            "origin": origin,
            # whether the reply gave the list at all: `evidence: []` is the
            # mark that none was found, a missing key is not
            "evidence_declared": isinstance(raw.get("evidence"), list),
            "evidence": kept,
            "evidence_dropped": fenced,
        }
        bad = [r for r in roles if r not in FACT_ROLES]
        if bad:
            row["for_dropped"] = bad
        if raw.get("answers") not in (None, ""):
            row["answers_given"] = [str(raw["answers"])]
        _number_items(row)
        out.append(row)
    return out


def _system(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    return {
        "summary": str(raw.get("summary") or "").strip(),
        "scope": str(raw.get("scope") or "").strip(),
        "unknowns": _text_list(raw.get("unknowns")),
    }


def process_survey(
    reply: dict,
    required: list[dict],
    blocklist: list[str],
    horizon: int | None,
    supplied: list[dict] | None = None,
    *,
    mode: str = ONLINE,
) -> dict:
    """The survey reply as the module keeps it — the first form of the
    model's representation (`knowledge/knowledge.json`).

    `reactions`: the intent's required reactions first (`req_k`, `required`
    and `essential` true, origin `human`, whatever the agent wrote — its
    evidence for one is attached by the `required` id it gave, else by
    equation), then every further conversion once, in reply order (`rx_1`,
    …, origin `knowledge`, `essential` as the agent says). `species` with
    their identifiers, `facts` (`fact_1`, …, origin `knowledge`, `for`
    checked against the four roles), `system`, `queries_run`, `notes`,
    `mode` (online | offline), `horizon`, `forbidden_sources`, and `dropped`:
    each entry not kept and why. Every evidence item is fenced (blocklist,
    horizon) and given its origin; every identifier is checked for its shape,
    a malformed one dropped with a note on its entry. Pure: no network, no
    grade."""
    reply = reply if isinstance(reply, dict) else {}
    index = supplied_index(supplied)
    dropped: list[dict] = []
    reactions = _reactions(
        reply.get("reactions"),
        required,
        blocklist,
        horizon,
        index,
        origin=ORIGIN,
        prefix="rx",
        dropped=dropped,
    )
    lacks = [
        key
        for key, kind in (("system", dict), ("facts", list), ("reactions", list))
        if not isinstance(reply.get(key), kind)
    ]
    return {
        "kind": SURVEY,
        "mode": mode,
        "system": _system(reply.get("system")),
        "species": _species(reply.get("species"), dropped),
        "reactions": reactions,
        "facts": _facts(
            reply.get("facts"),
            blocklist,
            horizon,
            index,
            origin=ORIGIN,
            prefix="fact",
            dropped=dropped,
        ),
        "queries_run": _text_list(reply.get("queries_run")),
        "notes": str(reply.get("notes") or ""),
        "horizon": horizon,
        "forbidden_sources": list(blocklist),
        "dropped": dropped,
        "reply_lacks": lacks,
    }


def _questions(questions) -> list[dict]:
    """The targeted search's questions, each with an id (`q_1`, … by position
    when the caller gave none)."""
    out = []
    for k, q in enumerate(questions or [], start=1):
        if isinstance(q, dict):
            row = dict(q)
            row["id"] = str(q.get("id") or f"q_{k}")
        else:
            row = {"id": f"q_{k}", "question": str(q)}
        out.append(row)
    return out


def process_targeted(
    reply: dict,
    questions,
    blocklist: list[str],
    horizon: int | None,
    supplied: list[dict] | None = None,
    *,
    mode: str = ONLINE,
    prefix: str = "s1",
    requested_by: str | None = None,
    known: list[dict] | None = None,
) -> dict:
    """A targeted search's reply as the module keeps it: the same reactions
    and facts as a survey's (ids `<prefix>_rx_1`, `<prefix>_fact_1`, origin
    `search`), each carrying `answers` — the ids of the questions it answers,
    those the reply named that are among `questions` — and, for a reaction
    whose conversion is already in `known` (the essential set), `duplicates`:
    that entry's id. `requested_by` (construction, expansions, expansion) is
    written on every entry. The questions themselves are kept beside."""
    reply = reply if isinstance(reply, dict) else {}
    qs = _questions(questions)
    ids = {q["id"] for q in qs}
    index = supplied_index(supplied)
    dropped: list[dict] = []
    reactions = _reactions(
        reply.get("reactions"),
        [],
        blocklist,
        horizon,
        index,
        origin=ORIGIN_SEARCH,
        prefix=f"{prefix}_rx",
        dropped=dropped,
    )
    facts = _facts(
        reply.get("facts"),
        blocklist,
        horizon,
        index,
        origin=ORIGIN_SEARCH,
        prefix=f"{prefix}_fact",
        dropped=dropped,
    )
    by_eq = {
        str(e.get("equation")): str(e.get("id"))
        for e in known or []
        if isinstance(e, dict) and e.get("id")
    }
    for row in reactions + facts:
        given = row.pop("answers_given", [])
        row["answers"] = [a for a in given if a in ids]
        unknown = [a for a in given if a not in ids]
        if unknown:
            row["answers_unknown"] = unknown
        if requested_by:
            row["requested_by"] = requested_by
        if row.get("equation") in by_eq:
            row["duplicates"] = by_eq[row["equation"]]
    lacks = [
        key
        for key, kind in (("facts", list), ("reactions", list))
        if not isinstance(reply.get(key), kind)
    ]
    return {
        "kind": TARGETED,
        "mode": mode,
        "questions": qs,
        "reactions": reactions,
        "facts": facts,
        "queries_run": _text_list(reply.get("queries_run")),
        "notes": str(reply.get("notes") or ""),
        "horizon": horizon,
        "forbidden_sources": list(blocklist),
        "dropped": dropped,
        "reply_lacks": lacks,
    }


# ------------------------------------------------------------ the battery


def normalise_text(text) -> str:
    """Text as the quote check compares it: Unicode-normalised, whitespace
    collapsed."""
    t = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"\s+", " ", t).strip()


def document_text(data: bytes, content_type: str = "") -> str | None:
    """A cached document as text for the quote check, or None when it is not
    text (a PDF, an image): markup stripped from HTML and XML."""
    ctype = str(content_type or "").lower()
    if data is None or b"\x00" in data[:4096]:
        return None
    if ctype and not ctype.startswith("text/") and "xml" not in ctype:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if "html" in ctype or "xml" in ctype:
        text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return text


def _text_for(item: dict, cached_texts: dict | None) -> str | None:
    if not cached_texts:
        return None
    for key in (item.get("cached_file"), item.get("url")):
        if key and key in cached_texts and cached_texts[key] is not None:
            return cached_texts[key]
    return None


def check_quotes(dossier: dict, cached_texts: dict | None) -> None:
    """`quote_found` on every item that gives a quote and whose cached
    document is text: True when the quote occurs in it (whitespace-normalised
    containment), False when not — a quote not found counts as no quote. An
    item whose document is not text, or was not cached, is left unchecked."""
    for _entry, it in _all_items(dossier):
        quote = normalise_text(it.get("quote"))
        text = _text_for(it, cached_texts)
        if not quote or text is None:
            it.pop("quote_found", None)
            continue
        it["quote_found"] = quote in normalise_text(text)


def _where(entry: dict, it: dict | None = None) -> str:
    what = "fact" if "statement" in entry else "reaction"
    head = f"{what} {entry.get('id')}"
    if what == "reaction":
        head += f" ({entry.get('equation')})"
    return head + (f", item {it.get('id')}" if it is not None else "")


def battery(
    dossier: dict, cached_texts: dict | None = None, required: list | None = None
) -> list[str]:
    """The knowledge reply battery, deterministic, before anything is graded:
    every failure as a sentence the agent is asked again with. [] = the reply
    passes.

    Every reaction parses; every required reaction of the intent is present
    with `required: true` and has an entry of the agent's own; every item of
    an essential reaction carries its classification (`evidence_kind`,
    `context_match`, `stance` — an item without one counts 0); every
    identifier has its declared shape; every source names a DOI, a PMID, a
    URL, a database identifier or a supplied paper's `lit_k`; a survey's
    `species` cover every id its equations use; every fact has a kind, a
    statement, its evidence (or `evidence: []`, the mark that none was found)
    and its `for` roles; a survey without a `system` summary or a `facts`
    list is refused. A targeted reply's entries each answer one of its
    questions. The quote check (`check_quotes`) runs here too: a quote not
    found in its text document is flagged on the item, never refused."""
    out: list[str] = []
    kind = dossier.get("kind") or SURVEY
    for key in dossier.get("reply_lacks") or []:
        if key == "system" and kind == SURVEY:
            out.append(
                "the reply carries no `system` object: give {summary, scope, "
                "unknowns} — what is known about this system for this question"
            )
        elif key == "facts":
            out.append(
                "the reply carries no `facts` list: give one — each fact a model of "
                "this system needs, or [] when you found none, said in `notes`"
            )
        elif key == "reactions":
            out.append("the reply carries no `reactions` list")
    system = dossier.get("system")
    if kind == SURVEY and isinstance(system, dict) and not system.get("summary"):
        out.append("`system.summary` is empty: say what is known about this system")
    for d in dossier.get("dropped") or []:
        eq = f" ({d['equation']!r})" if d.get("equation") else ""
        out.append(f"{d['what']}{eq} was not kept: {d['reason']}")
    reactions = [r for r in dossier.get("reactions") or [] if isinstance(r, dict)]
    have = {r.get("id"): r for r in reactions if r.get("required")}
    for r in required or []:
        if r["id"] not in have:
            out.append(
                f"required reaction {r['id']} ({r['equation']}) is not in the "
                f"module's reactions with `required: true`"
            )
    for r in reactions:
        if r.get("required") and not r.get("addressed") and kind == SURVEY:
            out.append(
                f"the reply gives no entry for required reaction {r['id']} "
                f"({r['equation']}): give it one, carrying `required: "
                f'"{r["id"]}"` — with `evidence: []` when you found nothing'
            )
        for note in r.get("notes") or []:
            out.append(f"{_where(r)}: {note}")
    for r in reactions:
        if not r.get("essential"):
            continue
        for it in r.get("evidence") or []:
            missing = [
                name
                for name, vocab in (
                    ("evidence_kind", EVIDENCE_KINDS),
                    ("context_match", CONTEXT_MATCHES),
                    ("stance", STANCES),
                )
                if str(it.get(name) or "").strip().lower() not in vocab
            ]
            if missing:
                out.append(
                    f"{_where(r, it)} carries no valid {', '.join(missing)}: an "
                    f"unclassified item counts 0 — classify it in the contract's "
                    f"vocabulary"
                )
    for entry in reactions + list(dossier.get("species") or []):
        for note in entry.get("identifier_notes") or []:
            name = (
                f"species {entry.get('id')}"
                if "equation" not in entry
                else _where(entry)
            )
            out.append(f"{name}: {note}; give it in the declared shape or leave it out")
    for entry, it in _all_items(dossier):
        if not _checkable(it):
            out.append(
                f"{_where(entry, it)} names no DOI, PMID, URL, database identifier "
                f"or supplied paper (`lit_k`) — source {str(it.get('source'))[:80]!r}: "
                f"give one, or leave the item out"
            )
    if kind == SURVEY:
        used: set[str] = set()
        for r in reactions:
            p = r.get("parsed") or {}
            used |= set(p.get("reactants") or {}) | set(p.get("products") or {})
            used |= set(r.get("modifiers") or [])
        named = {s.get("id") for s in dossier.get("species") or []}
        lacking = sorted(used - named)
        if lacking:
            out.append(
                f"the equations use {', '.join(lacking)}, which `species` lacks: "
                f"give each an entry (id, name, represents, identifiers)"
            )
    for f in dossier.get("facts") or []:
        if f.get("kind") not in FACT_KINDS:
            out.append(
                f"{_where(f)}: kind {f.get('kind') or '(none)'!r} is not one of "
                f"{' | '.join(FACT_KINDS)}"
            )
        if not f.get("statement"):
            out.append(f"{_where(f)} has no statement")
        if not f.get("evidence") and not f.get("evidence_declared"):
            out.append(
                f"{_where(f)} carries no evidence list: give its evidence items, or "
                f"`evidence: []` with the reason in `notes` when none was found"
            )
        if f.get("for_dropped"):
            out.append(
                f"{_where(f)}: `for` names {f['for_dropped']}, which are not among "
                f"{', '.join(FACT_ROLES)}"
            )
        if not f.get("for"):
            out.append(
                f"{_where(f)} names no role it is `for` ({', '.join(FACT_ROLES)})"
            )
    if kind == TARGETED:
        for entry in reactions + list(dossier.get("facts") or []):
            if entry.get("answers_unknown"):
                out.append(
                    f"{_where(entry)} answers {entry['answers_unknown']}, which are "
                    f"not the ids of the questions asked"
                )
            elif not entry.get("answers"):
                out.append(
                    f"{_where(entry)} names no question it answers (`answers`: a "
                    f"question id)"
                )
    check_quotes(dossier, cached_texts)
    return out


# ------------------------------------------------------------ the audit


_URL = re.compile(r"https?://", re.I)


def citation_target(item: dict) -> str:
    """What the citation check looks up for an item: its `source` when that
    names a DOI, a PMID or a URL, else its `url` when it has one — a supplied
    paper often carries its DOI there, not in the source string."""
    src = str(item.get("source") or "")
    if _DOI.search(src) or _PMID.search(src) or _URL.search(src):
        return src
    return str(item.get("url") or "").strip() or src


def audit(
    dossier: dict,
    cache,
    check_citations: bool,
    publication_types=None,
    resolve=None,
    unchecked_why: str = "verification.citation_check is off",
) -> None:
    """Every distinct document cached (`cache(url)` stores one and returns the
    connector's status record) and every distinct identifier looked up
    (`resolve(citation_target(item))`, default
    `octomod.connectors.web_cache.resolve_source`) —
    once, however many entries cite it — the outcome on each item as
    `resolution` and `resolution_class`. Online, `publication_types(item)`
    (the connector's PubMed lookup) fills `publication_types`; with the
    check off, every item reads `unchecked: <unchecked_why>`. What the
    metadata alone decides of the item's class is noted as `metadata_class`
    (`reaction_evidence.class_from_metadata`); the grade applies it."""
    from octomod.workflow_modules.knowledge.reaction_evidence import class_from_metadata

    if resolve is None and check_citations:
        from octomod.connectors.web_cache import resolve_source as resolve
    fetched: dict[str, dict] = {}
    resolved: dict[str, str] = {}
    typed: dict[str, list | None] = {}
    for _entry, it in _all_items(dossier):
        url = str(it.get("url") or "")
        if url not in fetched:
            fetched[url] = cache(url)
        it.update(fetched[url])
        src = citation_target(it)
        if not check_citations:
            it["resolution"] = f"unchecked: {unchecked_why}"
        else:
            if src not in resolved:
                resolved[src] = resolve(src)
            it["resolution"] = resolved[src]
        it["resolution_class"] = resolution_class(it["resolution"])
        if publication_types is not None:
            key = source_key(it)
            if key not in typed:
                typed[key] = publication_types(it)
            if typed[key] is not None:
                it["publication_types"] = list(typed[key])
        meta = class_from_metadata(it)
        if meta is not None:
            it["metadata_class"] = meta
    dossier["n_documents"] = sum(1 for u in fetched if u)
    dossier["n_documents_cached"] = sum(
        1 for v in fetched.values() if v.get("fetch_status") == "cached"
    )
    dossier["n_sources_checked"] = len(resolved)


def excerpts_for(dossier: dict, cached_texts: dict | None, bound: int = EXCERPT_CHARS):
    """{item id: the cached document's text around the item's quote}, at most
    `bound` characters each, for the items whose quote was found in a text
    document; an item with no such excerpt is left out."""
    out: dict[str, str] = {}
    for _entry, it in _all_items(dossier):
        text = _text_for(it, cached_texts)
        quote = normalise_text(it.get("quote"))
        if text is None or not quote:
            continue
        flat = normalise_text(text)
        at = flat.find(quote)
        if at < 0:
            continue
        pad = max(0, (bound - len(quote)) // 2)
        lo = max(0, at - pad)
        out[str(it.get("id"))] = flat[lo : lo + bound]
    return out


VERIFY_ITEM_KEYS = (
    "id",
    "source",
    "locator",
    "supports",
    "quote",
    "evidence_kind",
    "context_match",
    "context_note",
    "stance",
)


def verify(dossier: dict, call, excerpts: dict) -> dict:
    """One advisory call of `knowledge_verification` (`call(role, context)`)
    on every counting item (`reaction_evidence.counting_items`), with the
    cached document's text around each quote; its classification lands on
    each item as `second_kind`, `second_context`, `second_stance` (and
    `second_note`) before the grade reads them. Returns what it did: `{n_items,
    n_classified, n_disagree, unknown_ids}`; no call when nothing counts."""
    from octomod.workflow_modules.knowledge.reaction_evidence import counting_items

    items: dict[str, dict] = {}
    for key in ("reactions", "facts"):
        for entry in dossier.get(key) or []:
            for it in counting_items(entry):
                items[str(it.get("id"))] = it
    if not items:
        return {"n_items": 0, "n_classified": 0, "n_disagree": 0, "unknown_ids": []}
    payload = {
        "items": [
            {k: it.get(k) for k in VERIFY_ITEM_KEYS if it.get(k) not in (None, "")}
            for it in items.values()
        ],
        "excerpts": {k: v for k, v in excerpts.items() if k in items},
    }
    # the role spelled out: the module map reads who calls a role off literal
    # names at the call site
    reply = call("knowledge_verification", payload)
    n, disagree, unknown = 0, 0, []
    for c in (reply or {}).get("classifications") or []:
        if not isinstance(c, dict):
            continue
        it = items.get(str(c.get("id")))
        if it is None:
            unknown.append(str(c.get("id")))
            continue
        n += 1
        second = {
            "second_kind": str(c.get("evidence_kind") or "").strip().lower(),
            "second_context": str(c.get("context_match") or "").strip().lower(),
            "second_stance": str(c.get("stance") or "").strip().lower(),
        }
        it.update({k: v for k, v in second.items() if v})
        if c.get("note"):
            it["second_note"] = str(c["note"])
        if (
            second["second_kind"] != str(it.get("evidence_kind") or "").lower()
            or second["second_context"] != str(it.get("context_match") or "").lower()
            or (
                second["second_stance"]
                and second["second_stance"] != str(it.get("stance") or "").lower()
            )
        ):
            disagree += 1
    return {
        "n_items": len(items),
        "n_classified": n,
        "n_disagree": disagree,
        "unknown_ids": unknown,
    }


# ------------------------------------------------------------ the folder


def folder(case_dir) -> Path:
    return Path(case_dir) / FOLDER


def write_staged(case_dir, dossier: dict, calls_meta: list[dict], intent) -> Path:
    """The module's output in the staging folder: `knowledge/knowledge.json`
    (the dossier, the calls that made it and their cost), `knowledge/
    intent_before.yaml` (the intent as it stood — its own text when `intent`
    is the file's text, else the dict dumped), beside `knowledge/sources/` and
    `knowledge/calls/`, which the audit and the calls wrote. Returns the json's
    path."""
    root = folder(case_dir)
    (root / SOURCES_DIR).mkdir(parents=True, exist_ok=True)
    (root / CALLS_DIR).mkdir(parents=True, exist_ok=True)
    costs = [m.get("cost_usd") for m in calls_meta if m.get("cost_usd") is not None]
    record = {
        **dossier,
        "calls": [
            {
                k: m.get(k)
                for k in (
                    "name",
                    "role",
                    "mode",
                    "search",
                    "backend",
                    "model",
                    "effort",
                    "cost_usd",
                    "sha",
                    "at",
                )
            }
            for m in calls_meta
        ],
        "cost_usd": round(sum(costs), 4) if costs else None,
        "written_at": _now(),
    }
    text = (
        intent if isinstance(intent, str) else yaml.safe_dump(intent, sort_keys=False)
    )
    (root / INTENT_BEFORE).write_text(text)
    path = root / DOSSIER_FILE
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return path


def read_staged(case_dir) -> dict | None:
    """What the module left in a staging folder: `{"knowledge": the json,
    "intent_before": the intent it saw (a dict, or None), "calls": [each
    call's meta], "sources": [the cached documents' names]}`. None when there
    is no `knowledge/knowledge.json`; ValueError naming the file when it is
    not readable JSON."""
    root = folder(case_dir)
    path = root / DOSSIER_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"{path} is not readable JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{path} holds {type(data).__name__}, not an object")
    before = None
    if (root / INTENT_BEFORE).is_file():
        try:
            before = yaml.safe_load((root / INTENT_BEFORE).read_text())
        except yaml.YAMLError:
            before = None
    calls = []
    for p in sorted((root / CALLS_DIR).glob("*.meta.json")):
        try:
            calls.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    sources = sorted(p.name for p in (root / SOURCES_DIR).glob("*") if p.is_file())
    return {
        "knowledge": data,
        "intent_before": before if isinstance(before, dict) else None,
        "calls": calls,
        "sources": sources,
    }


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------ the staging call


class StagingSession:
    """The seam a staging call passes through, outside a run: the routing
    table, `agents.call_agent` with the call's own grant, its contract, the
    case's stubs — into a scratch record (the prompt budget, the ledger row
    and the raw replies need one) that is discarded when the session closes.
    What stays is written into the staging folder: each call's prompt, reply
    and meta under `knowledge/calls/<role>.<n>.*`, and one line per call in
    `curation/STAGING_LOG.md`. The stub backend serves `stubs/<role>.json`,
    or `stubs/<role>.<n>.json` for the n-th call of the role in the session."""

    def __init__(self, case_dir, *, spec, backend: str):
        from octomod.orchestration.ledger import Ledger
        from octomod.result.node import Node
        from octomod.result.runstore import RunStore

        self.case_dir = Path(case_dir)
        self.spec = spec
        self.backend = backend
        self._tmp = Path(tempfile.mkdtemp(prefix="octomod_knowledge_"))
        self.store = RunStore(self._tmp / "staging.h5")
        self.store.create()
        self.ledger = Ledger(self.store)
        self.calls = Node(self.store) / "calls"
        self.metas: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _n(self, role: str) -> int:
        return 1 + sum(1 for m in self.metas if m.get("role") == role)

    def call(
        self, role: str, context: dict, *, online: bool = False
    ) -> tuple[dict, dict]:
        """One agent call: `(reply, meta)`. `online` is the call's grant
        (`agents.granted_tools`); the prompt says it."""
        from octomod.agents import AgentCallError, agent_timing, call_agent, routing

        n = self._n(role)
        name = f"{role}.{n}"
        live = self.backend == "llm"
        model = self.spec.model_for_role(role) if live else "stub"
        doing = agent_timing.doing(role)
        print(f"  → {role} agent ({model}) — {doing}")
        # what the role may be shown, before the prompt is built
        routing.enforce(role, context.keys())
        meta = {
            "name": name,
            "role": role,
            "mode": str(context.get("mode") or ""),
            "search": ONLINE if online else OFFLINE,
            "backend": self.backend,
            "at": _now(),
        }
        error = None
        with agent_timing.Heartbeat(f"{role} agent", doing, live=live):
            try:
                reply = call_agent(
                    role,
                    context,
                    spec=self.spec,
                    backend=self.backend,
                    calls=self.calls,
                    ledger=self.ledger,
                    module=role,
                    stubs_dir=self.case_dir / "stubs",
                    name=name,
                    online=online,
                )
            except AgentCallError as e:
                reply, error = None, e
        row = next(
            (
                r
                for r in reversed(self.ledger.entries())
                if r.get("event") in ("agent_call", "agent_call_aborted")
                and r.get("role") == role
            ),
            {},
        )
        meta.update(
            model=row.get("model"),
            model_resolved=row.get("model_resolved"),
            effort=row.get("effort"),
            cost_usd=row.get("cost_usd"),
            sha=row.get("prompt_sha"),
            prompt_bytes=row.get("prompt_bytes"),
            attempts=row.get("attempts"),
            duration_s=row.get("duration_s"),
        )
        if error is not None:
            meta["aborted"] = str(error)[:400]
        self._archive(name, reply, meta)
        self.metas.append(meta)
        if error is not None:
            raise error
        cost = meta.get("cost_usd")
        print(
            f"  ← {role} returned"
            + (f" (${cost:.2f})" if isinstance(cost, (int, float)) else "")
            + f"; prompt and reply in {FOLDER}/{CALLS_DIR}/{name}.*"
        )
        return reply, meta

    def _archive(self, name: str, reply, meta: dict) -> None:
        calls = folder(self.case_dir) / CALLS_DIR
        calls.mkdir(parents=True, exist_ok=True)
        prompt = (self.calls.child(name) / "prompt").text(None)
        if prompt is not None:
            (calls / f"{name}.prompt.txt").write_text(prompt)
        if reply is not None:
            (calls / f"{name}.reply.json").write_text(
                json.dumps(reply, indent=2, default=str) + "\n"
            )
        (calls / f"{name}.meta.json").write_text(
            json.dumps(meta, indent=2, default=str) + "\n"
        )
        log_call(self.case_dir, meta)


def call_staged(
    role: str,
    context: dict,
    *,
    spec,
    backend: str,
    case_dir,
    online: bool,
    session: StagingSession | None = None,
) -> tuple[dict, dict]:
    """One staging call outside a run: `(reply, meta)`, archived under the
    case's `knowledge/calls/`. A `session` carries the numbering and the stub
    sequence across the calls of one module run; without one, the call has a
    session of its own."""
    if session is not None:
        return session.call(role, context, online=online)
    with StagingSession(case_dir, spec=spec, backend=backend) as own:
        return own.call(role, context, online=online)


def log_call(case_dir, meta: dict) -> None:
    """One line in the case's `curation/STAGING_LOG.md` per call: the role,
    its modes, the model, the cost and the prompt's sha."""
    path = Path(case_dir) / STAGING_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    cost = meta.get("cost_usd")
    line = (
        f"- {meta.get('at')} · {meta.get('name')} · {meta.get('mode') or '-'}, "
        f"{meta.get('search')} · {meta.get('backend')} · model "
        f"{meta.get('model_resolved') or meta.get('model') or '-'} · "
        + (f"${cost:.4f}" if isinstance(cost, (int, float)) else "cost not reported")
        + f" · prompt sha {meta.get('sha') or '-'}"
        + (" · ABORTED" if meta.get("aborted") else "")
        + "\n"
    )
    new = not path.exists()
    with path.open("a") as f:
        if new:
            f.write(
                "# Staging log\n\nOne line per knowledge-module call: when, which "
                "call, its modes, the backend, the model, the cost, the prompt's "
                "sha.\n\n"
            )
        f.write(line)


# ------------------------------------------------------------ the survey


def search_fence(case_dir, testcase: dict, mode: str) -> tuple[dict, list[str]]:
    """The fence a survey obeys: `({"horizon", "forbidden_sources"},
    problems)`. Online, the case must declare its literature horizon
    (`research.max_publication_year`, the one horizon a case has); the
    blocklist applies in both modes."""
    year = ((testcase or {}).get("research") or {}).get("max_publication_year")
    problems = []
    if mode == ONLINE and year is None:
        problems.append(horizon_refusal(Path(case_dir).name))
    blocklist = _lit.read_blocklist(Path(case_dir) / "blocklist.txt")
    return {
        "horizon": int(year) if year is not None else None,
        "forbidden_sources": blocklist,
    }, problems


def horizon_refusal(case_name: str) -> str:
    return (
        f"testcase {case_name!r} searches the literature (the knowledge module in "
        f"online mode) but declares no `research.max_publication_year` in its "
        f"testcase.yaml — the horizon belongs to the case. Declare it, or run the "
        f"module offline"
    )


def survey_payload(intent: dict, description: str, fence: dict, supplied) -> dict:
    """What the survey call is shown: the intent (without the supplied
    items), the lab note, the required reactions with their ids, the supplied
    literature, the restrictions and the mode."""
    required = required_reactions(intent)
    payload = {
        "mode": SURVEY,
        "intent": _lit.strip_from_intent(intent),
        "experiment_description": description,
        "required_reactions": [
            {
                "id": r["id"],
                "equation": r["equation"],
                **({"note": r["note"]} if r.get("note") else {}),
            }
            for r in required
        ],
    }
    if supplied:
        payload["supplied_literature"] = supplied
    payload["restrictions"] = restrictions_text(
        fence["horizon"], fence["forbidden_sources"]
    )
    return payload


def _cached_texts(sources_dir: Path, dossier: dict) -> dict[str, str | None]:
    """{cached file name: its text, or None when it is not text}."""
    out: dict[str, str | None] = {}
    for _entry, it in _all_items(dossier):
        name = it.get("cached_file")
        if not name or name in out:
            continue
        path = sources_dir / str(name)
        if path.is_file():
            out[name] = document_text(path.read_bytes(), it.get("content_type") or "")
    return out


def _cache_into(sources: Path, case_dir: Path, search: str):
    """The audit's `cache(url)`: into the folder's `sources/`. Offline, only a
    case document (`file:`) is read; nothing is fetched from the web."""
    from octomod.connectors.web_cache import cache_source

    def cache(url: str) -> dict:
        if search == OFFLINE and not str(url).startswith("file:"):
            return {"fetch_status": "not fetched: offline"}
        return cache_source(url, sources, base_dir=case_dir)

    return cache


def run_survey(case_dir, *, mode: str, backend: str, spec) -> dict:
    """The module, start to end, on a staging folder: the fence, the survey
    call with its retry budget (`retry.module_draft` + 1, the battery's
    failures handed back as `previous_attempt_errors`), the audit, the
    verifier (online, `grounding.verify`), the grade, the suggested floor,
    and the folder written. Returns `{"ok", "problems", "path", "dossier",
    "suggestion", "cost_usd", "calls"}`; `ok` False (and no knowledge.json)
    when the fence refuses or the reply never passes its battery."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    case = Path(case_dir)
    testcase = _load_yaml(case / "testcase.yaml") or {}
    intent_text = (case / "intent.yaml").read_text()
    intent = yaml.safe_load(intent_text) or {}
    description = (
        (case / "description.md").read_text()
        if (case / "description.md").exists()
        else ""
    )
    fence, problems = search_fence(case, testcase, mode)
    problems += _rxe.intent_problems(intent) + _lit.problems(intent)
    if problems:
        return {"ok": False, "problems": problems, "path": None}
    supplied = _lit.normalized(_lit.items(intent))
    required = required_reactions(intent)
    # a module run replaces the module's previous output as a whole
    root = folder(case)
    if root.exists():
        shutil.rmtree(root)
    (root / SOURCES_DIR).mkdir(parents=True)
    (root / CALLS_DIR).mkdir(parents=True)
    online = mode == ONLINE
    payload = survey_payload(intent, description, fence, supplied)
    attempts = int(spec.get("retry.module_draft", 2)) + 1
    cache = _cache_into(root / SOURCES_DIR, case, mode)
    # offline, nothing is looked up on the web: every identifier is unchecked
    check = online and bool(spec.get("verification.citation_check", True))
    unchecked_why = (
        "verification.citation_check is off"
        if online
        else "the module ran offline, nothing was looked up"
    )
    pub = None
    if online:
        from octomod.connectors.web_cache import publication_types

        pub = publication_types
    with StagingSession(case, spec=spec, backend=backend) as session:
        failures: list[str] = []
        dossier = None
        for attempt in range(1, attempts + 1):
            reply, _meta = session.call("knowledge", payload, online=online)
            dossier = process_survey(
                reply,
                required,
                fence["forbidden_sources"],
                fence["horizon"],
                supplied,
                mode=mode,
            )
            audit(
                dossier,
                cache,
                check,
                publication_types=pub,
                unchecked_why=unchecked_why,
            )
            texts = _cached_texts(root / SOURCES_DIR, dossier)
            failures = battery(dossier, texts, required)
            if not failures:
                break
            print(
                f"  ⚑ knowledge reply refused by its battery (attempt {attempt} of "
                f"{attempts}): {len(failures)} failure(s)"
            )
            for f in failures[:12]:
                print(f"      {f}")
            payload = {
                **payload,
                "previous_attempt_errors": failures,
                "previous_reply": reply,
            }
        metas = list(session.metas)
        if failures:
            return {
                "ok": False,
                "problems": failures,
                "path": None,
                "calls": metas,
                "cost_usd": _cost(metas),
            }
        verified = None
        if online and _rxe.verify_enabled(spec):
            from octomod.agents import AgentCallError

            try:
                verified = verify(
                    dossier,
                    lambda role, ctx: session.call(role, ctx, online=False)[0],
                    excerpts_for(dossier, texts),
                )
            except AgentCallError as e:
                # advisory: a verifier that gave no usable reply leaves the
                # first classifications to grade alone, and says so
                verified = {"error": str(e)[:400]}
                print(f"  ⚑ the verifier gave no usable reply: {str(e)[:200]}")
            dossier["verification"] = verified
        metas = list(session.metas)
    _rxe.grade_reactions(dossier, spec)
    suggestion = _rxe.suggest_floor(essential_entries(dossier), mode=mode)
    dossier["suggestion"] = suggestion
    path = write_staged(case, dossier, metas, intent_text)
    return {
        "ok": True,
        "problems": [],
        "path": path,
        "dossier": dossier,
        "suggestion": suggestion,
        "cost_usd": _cost(metas),
        "calls": metas,
        "verification": verified,
    }


def _cost(metas: list[dict]) -> float | None:
    costs = [m.get("cost_usd") for m in metas if m.get("cost_usd") is not None]
    return round(sum(costs), 4) if costs else None


def _load_yaml(path: Path):
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text())


def essential_entries(dossier: dict) -> list[dict]:
    """The essential set: the required reactions and the survey's essential
    ones, in dossier order."""
    return [
        r
        for r in dossier.get("reactions") or []
        if isinstance(r, dict) and (r.get("essential") or r.get("required"))
    ]


def facts_by_role(dossier: dict) -> dict[str, int]:
    """How many facts are for each of the four roles."""
    return {
        role: sum(1 for f in dossier.get("facts") or [] if role in (f.get("for") or []))
        for role in FACT_ROLES
    }


def facts_for(dossier: dict, role: str) -> list[dict]:
    """The facts routed to one routing-table role (`construction`,
    `observation`, `condition`, `revision`), as that
    role's `known_facts`."""
    wanted = {k for k, v in FACT_ROLE_OF.items() if v == role}
    keys = (
        "id",
        "kind",
        "statement",
        "value",
        "unit",
        "applies_to",
        "grade",
        "because",
        "origin",
    )
    return [
        {k: f.get(k) for k in keys if f.get(k) not in (None, "", [])}
        for f in dossier.get("facts") or []
        if wanted & set(f.get("for") or [])
    ]


def card_lines(case_dir, spec) -> list[str]:
    """The floor card as `./run.sh knowledge` prints it: the grade module's
    card (the essentials with their bands, the unsupported ones as decisions,
    the suggestion, the trade-off, the forms), then the facts per role and
    the module's cost; the decision the case already records, when it has
    one."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    staged = read_staged(case_dir)
    if staged is None:
        return [
            f"no {FOLDER}/{DOSSIER_FILE} in {case_dir}: the knowledge module has not "
            f"completed here — run ./run.sh knowledge --testcase {case_dir} "
            f"--mode online|offline"
        ]
    dossier = staged["knowledge"]
    testcase = _load_yaml(Path(case_dir) / "testcase.yaml") or {}
    decision = _decision(testcase, spec)
    lines = list(
        _rxe.floor_card_lines(
            essential_entries(dossier), dossier.get("suggestion") or {}, decision
        )
    )
    by_role = facts_by_role(dossier)
    lines.append(
        f"FACTS — {len(dossier.get('facts') or [])} for the model beyond its "
        f"reactions: " + ", ".join(f"{k} {v}" for k, v in by_role.items())
    )
    for f in dossier.get("facts") or []:
        lines.append(
            f"  {f.get('id')} [{f.get('kind')}] {str(f.get('statement'))[:100]} — "
            f"{_band(f.get('grade'))} · for {', '.join(f.get('for') or [])}"
        )
    cost = dossier.get("cost_usd")
    n_calls = len(dossier.get("calls") or [])
    lines.append(
        f"module: {dossier.get('mode')} survey, {n_calls} call(s), "
        + (f"${cost:.2f}" if isinstance(cost, (int, float)) else "no cost reported")
        + f"; the folder is {Path(case_dir) / FOLDER}"
    )
    return lines


def _band(grade) -> str:
    if isinstance(grade, dict):
        grade = grade.get("band")
    return str(grade or "not graded").replace("_", " ")


def _decision(testcase: dict, spec):
    """The floor decision testcase.yaml records, or None when it records
    none (the card is then asked, not answered)."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    own = (testcase or {}).get("grounding")
    if not isinstance(own, dict) or "support_floor" not in own:
        return None
    try:
        return _rxe.read_floor_decision(testcase, spec)
    except ValueError:
        return None


# ------------------------------------------------------------ run start


def _case_dir(ctx_or_case) -> Path:
    return Path(getattr(ctx_or_case, "testcase_dir", ctx_or_case))


def floor_problems(testcase: dict, spec, where="<folder>") -> list[str]:
    """What is wrong with the case's floor decision, each naming the fix; []
    when testcase.yaml records a usable one. `where` names the folder in the
    card's command."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    card = f"./run.sh knowledge --show --testcase {where}"
    own = (testcase or {}).get("grounding")
    if not isinstance(own, dict) or own.get("support_floor") in (None, ""):
        return [
            "testcase.yaml records no support floor (`grounding.support_floor`) — "
            f"decide the support floor: the card is {card}, and the person's "
            "answer goes into testcase.yaml as grounding: {support_floor, "
            "floor_step, decided_by, note}"
        ]
    try:
        _rxe.read_floor_decision(testcase, spec)
    except ValueError as e:
        return [
            f"testcase.yaml's floor decision is not usable: {e} — decide the "
            f"support floor again: the card is {card}"
        ]
    return []


def required_moved(dossier: dict, intent: dict) -> tuple[list[str], list[str]]:
    """(added, removed): the intent's required reactions against the module's
    required rows, by conversion."""
    now = {r["equation"] for r in required_reactions(intent or {})}
    then = {
        str(r.get("equation"))
        for r in dossier.get("reactions") or []
        if isinstance(r, dict) and r.get("required")
    }
    return sorted(now - then), sorted(then - now)


def run_start_problems(
    ctx_or_case, testcase: dict, intent: dict | None, spec, *, source=None
) -> list[str]:
    """The refusals at run start, each naming its fix; [] when the run may
    start. Nothing is refused for a case that declares its skip
    (`grounding: {skip: true, why: …}`); otherwise the folder must hold the
    module's output (`knowledge/knowledge.json`), testcase.yaml the person's
    floor (and a `grounding.mode`, when it declares one, that is a mode), the
    intent the required reactions the module saw, and an online module's case
    its horizon. `source` names the folder in the messages
    (default: the case directory)."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    try:
        if _rxe.skip_declared(testcase or {}):
            return []
    except ValueError as e:
        return [f"testcase.yaml's grounding block is not usable: {e}"]
    case = _case_dir(ctx_or_case)
    where = source or case
    fix = f"./run.sh knowledge --testcase {where} --mode online|offline"
    try:
        staged = read_staged(case)
    except ValueError as e:
        return [
            f"the knowledge module's output is unreadable ({e}) — run it again: {fix}"
        ]
    if staged is None:
        return [
            f"the case holds no {FOLDER}/{DOSSIER_FILE} — run the knowledge module "
            f"first: {fix}"
        ]
    dossier = staged["knowledge"]
    out = floor_problems(testcase, spec, where)
    try:
        _rxe.case_mode(testcase or {})
    except ValueError as e:
        out.append(
            f"testcase.yaml's {e} (advisory: the dossier is prior knowledge and "
            f"what it does not back is flagged; strict: the base is exactly the "
            f"essential set)"
        )
    added, removed = required_moved(dossier, intent or {})
    if added or removed:
        out.append(
            "re-run the knowledge module: the intent's required reactions moved "
            "since it ran ("
            + "; ".join(
                x
                for x in (
                    f"added {', '.join(added)}" if added else "",
                    f"removed {', '.join(removed)}" if removed else "",
                )
                if x
            )
            + f") — {fix}"
        )
    if dossier.get("mode") == ONLINE and (
        ((testcase or {}).get("research") or {}).get("max_publication_year") is None
    ):
        out.append(horizon_refusal(Path(str(where)).name))
    return out


def staged_intent(ctx_or_case) -> dict | None:
    """The case's intent.yaml as the run reads it, or None when it is absent
    or malformed (S0 refuses that by name)."""
    path = _case_dir(ctx_or_case) / "intent.yaml"
    try:
        data = yaml.safe_load(path.read_text()) if path.is_file() else None
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def write_round0_floor(ctx, spec):
    """Round 0's support floor at run start, from the person's decision in
    testcase.yaml (`reaction_evidence.write_floor`, source `human` or `rule`),
    written once: a resume finds it and changes nothing. None when the case
    records no decision."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    band, step, source = floor_fields(_decision(ctx.testcase or {}, spec))
    if band is None:
        return None
    previous = ctx.round_idx
    ctx.round_idx = 0
    try:
        # a floor the person set later at a card of round 0 stands
        if (ctx.round / _rxe.FLOOR_KEY).exists():
            return None
        return _rxe.write_floor(ctx, band, step, source)
    finally:
        ctx.round_idx = previous


def grounding_fence_row(ctx_or_case, testcase: dict, spec, blocklist=None) -> dict:
    """The `grounding_fence` ledger row's fields: the module's mode, the
    support floor and who set it (`human` | `rule`), the step, the grounding
    mode (advisory | strict), the horizon and the forbidden sources — or, for
    a case that declares its skip, the skip and its why."""
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe

    case = _case_dir(ctx_or_case)
    if blocklist is None:
        blocklist = _lit.read_blocklist(case / "blocklist.txt")
    year = ((testcase or {}).get("research") or {}).get("max_publication_year")
    why = _rxe.skip_declared(testcase or {})
    if why:
        return {
            "skip": str(why),
            "horizon": year,
            "forbidden_sources": list(blocklist),
            "note": f"the knowledge module is skipped: {why}",
        }
    staged = read_staged(case) or {"knowledge": {}}
    decision = _decision(testcase, spec) or {}
    band, step, source = floor_fields(decision)
    mode = staged["knowledge"].get("mode")
    grounding = _rxe.mode_of(testcase, spec)
    return {
        "mode": mode,
        "support_floor": band,
        "floor_source": source,
        "floor_step": step,
        "grounding_mode": grounding,
        "horizon": year,
        "forbidden_sources": list(blocklist),
        "note": (
            f"the knowledge module ran {mode}; support floor {band} "
            f"({'the person' if source == 'human' else 'the rule'}), step {step}; "
            f"{grounding} mode"
        ),
    }


def floor_fields(decision) -> tuple:
    """(band, step, source) of a floor decision as `read_floor_decision`
    returns it: source `human` when the person decided it, `rule` when they
    took the suggestion unchanged."""
    d = decision if isinstance(decision, dict) else {}
    band = d.get("support_floor", d.get("band"))
    step = d.get("floor_step", d.get("step"))
    by = str(d.get("decided_by") or d.get("source") or "").strip().lower()
    return band, step, ("rule" if by == "rule" else "human")


# ------------------------------------------------------------ the targeted search

# one retry when the reply fails its battery: the search is one call per
# redraft, and a refused reply is handed back once with its failures
TARGETED_ATTEMPTS = 2


def targeted_questions(missing) -> list[dict]:
    """A construction reply's `missing` as the targeted search's questions:
    `{id, equation, why, question}` per readable entry, `q_1`, … in order, a
    repeated equation asked once."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in missing if isinstance(missing, list) else []:
        if isinstance(m, dict):
            eq = " ".join(str(m.get("equation") or "").split())
            why = " ".join(str(m.get("why") or "").split())
        else:
            eq, why = " ".join(str(m or "").split()), ""
        if not eq:
            continue
        try:
            key = canonical(parse_equation(eq))
        except EquationError:
            key = eq
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": f"q_{len(out) + 1}",
                "equation": eq,
                "why": why,
                "question": f"{eq} — {why}" if why else eq,
            }
        )
    return out


def _record_texts(sources, dossier: dict) -> dict[str, str | None]:
    """{cached file name: its text, or None when it is not text}, from the
    documents the audit froze into the round (`evidence_sources`)."""
    out: dict[str, str | None] = {}
    for _entry, it in _all_items(dossier):
        name = it.get("cached_file")
        if not name or name in out:
            continue
        data = sources.child(str(name)).blob(None)
        if data is not None:
            out[name] = document_text(data, it.get("content_type") or "")
    return out


def _call_cost(ctx, name: str) -> float | None:
    """The cost the ledger recorded for the call archived under `name`."""
    for e in reversed(ctx.ledger.entries()):
        if e.get("event") in ("agent_call", "agent_call_aborted") and (
            f"/{name}/" in str(e.get("io") or "")
        ):
            c = e.get("cost_usd")
            return float(c) if isinstance(c, (int, float)) else None
    return None


def targeted_search(
    ctx,
    questions,
    n: int,
    *,
    model_summary: dict,
    essential_ids=(),
    requested_by: str = "construction",
    known: list[dict] | None = None,
) -> dict:
    """The round's n-th targeted search, frozen at
    `rounds/round_k/knowledge_search/<n>`: ONE call of the `knowledge` role
    in `targeted` mode (online when the staged module ran online, fenced like
    the survey), archived under `agent_calls/knowledge_targeted_<n>`. The
    reply goes through `process_targeted` (origin `search`, `requested_by` on
    every entry, a duplicate of a `known` entry marked), the battery (a
    refused reply is asked once more with `previous_attempt_errors`), the
    audit (its documents cached into the round's `evidence_sources`, its
    citations resolved when online) and the grade. The record holds the
    questions, the graded reactions and facts, the calls and their cost; a
    reply refused twice keeps its failures (`battery_failures`) and admits
    nothing. A resume reads the record back and calls nothing; a failed call
    is frozen as failed, so a resume does not pay for it again."""
    from octomod.agents import AgentCallError, AgentKilled
    from octomod.workflow_modules.knowledge import reaction_evidence as _rxe
    from octomod.workflow_modules.model import engine as _s1

    node = ctx.round / _rxe.SEARCH_KEY / str(n)
    if node.exists():
        return node.get()
    staged = _rxe.staged_dossier(ctx) or {}
    mode = staged.get("mode") if staged.get("mode") in SEARCH_MODES else OFFLINE
    online = mode == ONLINE
    blocklist = _lit.read_blocklist(Path(ctx.testcase_dir) / "blocklist.txt")
    year = ((ctx.testcase or {}).get("research") or {}).get("max_publication_year")
    horizon = int(year) if year is not None else None
    supplied = _lit.normalized(_lit.load_frozen(ctx.root))
    qs = _questions(questions)
    payload = {
        "mode": TARGETED,
        "intent": _lit.strip_from_intent(ctx.intent or {}),
        "questions": qs,
        "model_summary": model_summary,
        "essential_ids": list(essential_ids or []),
        "restrictions": restrictions_text(horizon, blocklist),
    }
    if supplied:
        payload["supplied_literature"] = supplied
    sources = ctx.round / _rxe.SOURCES_KEY

    def cache(url: str) -> dict:
        if not online and not str(url).startswith("file:"):
            return {"fetch_status": "not fetched: offline"}
        return _s1._cache_source(ctx, url, sources)

    check = online and bool(ctx.spec.get("verification.citation_check", True))
    unchecked_why = (
        "verification.citation_check is off"
        if online
        else "the module ran offline, nothing was looked up"
    )
    pub = None
    if online:
        from octomod.connectors.web_cache import publication_types

        pub = publication_types
    names: list[str] = []
    failures: list[str] = []
    result: dict = {}
    failed = None
    for attempt in range(1, TARGETED_ATTEMPTS + 1):
        name = f"knowledge_targeted_{n}" + ("" if attempt == 1 else "_retry")
        names.append(name)
        try:
            # the role spelled out: the module map reads who calls a role off
            # literal names at the call site
            reply = ctx.call("knowledge", payload, name=name, online=online)
        except AgentKilled:
            raise  # a person stopped it: not a reply to work around
        except AgentCallError as e:
            failed = str(e)[:400]
            break
        result = process_targeted(
            reply,
            qs,
            blocklist,
            horizon,
            supplied,
            mode=mode,
            prefix=f"r{ctx.round_idx}s{n}",
            requested_by=requested_by,
            known=known,
        )
        audit(
            result,
            cache,
            check,
            publication_types=pub,
            unchecked_why=unchecked_why,
        )
        failures = battery(result, _record_texts(sources, result))
        if not failures:
            break
        print(
            f"  ⚑ targeted search {n}: the reply was refused by its battery (attempt "
            f"{attempt} of {TARGETED_ATTEMPTS}): {len(failures)} failure(s)"
        )
        payload = {
            **payload,
            "previous_attempt_errors": failures,
            "previous_reply": reply,
        }
    if result:
        _rxe.grade_reactions(result, ctx.spec)
    costs = [c for c in (_call_cost(ctx, nm) for nm in names) if c is not None]
    record = {
        "n": int(n),
        "requested_by": requested_by,
        "mode": mode,
        "online": online,
        "questions": qs,
        "reactions": list(result.get("reactions") or []),
        "facts": list(result.get("facts") or []),
        "queries_run": list(result.get("queries_run") or []),
        "notes": str(result.get("notes") or ""),
        "dropped": list(result.get("dropped") or []),
        "horizon": horizon,
        "forbidden_sources": list(blocklist),
        "grading": result.get("grading"),
        "n_documents": result.get("n_documents", 0),
        "n_documents_cached": result.get("n_documents_cached", 0),
        "battery_failures": list(failures),
        "failed": failed,
        "calls": names,
        "cost": {
            "usd": round(sum(costs), 4) if costs else None,
            "n_calls": len(names) - (1 if failed else 0),
        },
    }
    node.put(record)
    return record


# ------------------------------------------------------------ S0


def _staged_text(ctx, rel: str) -> str | None:
    """A file of the run's inputs: the record's `input` group, else the
    directory the run reads (a legacy run)."""
    from octomod.orchestration import run_folder

    root = getattr(ctx, "root", None)
    if root is not None and rel in run_folder.entries(root):
        return run_folder.read_bytes(root, rel).decode("utf-8", errors="replace")
    path = Path(ctx.testcase_dir) / rel
    return path.read_text() if path.is_file() else None


def has_staged(ctx) -> bool:
    return _staged_text(ctx, f"{FOLDER}/{DOSSIER_FILE}") is not None


def staged_dossier(ctx) -> dict | None:
    """The module's `knowledge/knowledge.json` as the run reads it (the
    record's `input` group), or None when the inputs hold none or it is not
    a readable object."""
    text = _staged_text(ctx, f"{FOLDER}/{DOSSIER_FILE}")
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _short(value, limit: int = 80) -> str:
    text = json.dumps(value, default=str, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def intent_diff(before: dict | None, now: dict | None) -> list[str]:
    """One line per top-level key that was added, removed or changed between
    the intent the module saw and the one being frozen; `["no change"]` when
    they are equal."""
    before, now = dict(before or {}), dict(now or {})
    out = []
    for key in now:
        if key not in before:
            out.append(f"added {key}: {_short(now[key])}")
    for key in before:
        if key not in now:
            out.append(f"removed {key} (was {_short(before[key])})")
    for key in now:
        if key in before and before[key] != now[key]:
            out.append(
                f"changed {key}: {_short(before[key], 60)} -> {_short(now[key], 60)}"
            )
    return out or ["no change"]


def grade_text(entry: dict) -> str:
    """`medium — <source> (direct_experimental, related_system)`: an entry's
    band and the source that earned it."""
    band = _band(entry.get("grade"))
    if band == "not applicable":
        return "not applicable (offline)"
    because = entry.get("because") or []
    if not because:
        return band
    first = because[0] if isinstance(because[0], dict) else {}
    return (
        f"{band} — {str(first.get('source') or first.get('id'))[:60]} "
        f"({first.get('evidence_kind')}, {first.get('context_match')})"
    )


def _entry_line(r: dict) -> str:
    return (
        f"    {r.get('id')}  {r.get('equation')} — {grade_text(r)} · origin "
        f"{r.get('origin')}"
    )


def intent_lines(ctx, intent: dict | None = None) -> list[str]:
    """The intent card's knowledge lines: the required and the essential
    reactions with their grade, the source that earned it and their origin;
    the support floor and who set it; the facts per role; and the intent
    being frozen against the one the module saw (`knowledge/
    intent_before.yaml`), one line per added, removed or changed key. []
    when the run's inputs hold no module output. `intent` is the intent
    being frozen (default: the run's intent.yaml)."""
    text = _staged_text(ctx, f"{FOLDER}/{DOSSIER_FILE}")
    if text is None:
        return []
    try:
        dossier = json.loads(text)
    except ValueError:
        return [f"knowledge: {FOLDER}/{DOSSIER_FILE} is not readable JSON"]
    if intent is None:
        raw = _staged_text(ctx, "intent.yaml")
        intent = yaml.safe_load(raw) if raw else {}
    before_text = _staged_text(ctx, f"{FOLDER}/{INTENT_BEFORE}")
    before = yaml.safe_load(before_text) if before_text else None
    rows = [r for r in dossier.get("reactions") or [] if isinstance(r, dict)]
    required = [r for r in rows if r.get("required")]
    essential = [r for r in rows if r.get("essential") and not r.get("required")]
    band, step, source = floor_fields(_decision(getattr(ctx, "testcase", {}), ctx.spec))
    by_role = facts_by_role(dossier)
    lines = [
        f"knowledge:         the module ran {dossier.get('mode')} — "
        f"{len(required)} required, {len(essential)} further essential "
        f"reaction(s), {len(dossier.get('facts') or [])} fact(s)",
        f"  support floor:   {str(band).replace('_', ' ')} "
        f"({'the person' if source == 'human' else 'the rule'}), step {step}",
        f"  required ({len(required)}):",
        *[_entry_line(r) for r in required],
        f"  essential ({len(essential)}):",
        *[_entry_line(r) for r in essential],
        "  facts by role:   " + ", ".join(f"{k} {v}" for k, v in by_role.items()),
    ]
    if before is None:
        lines.append(
            f"  intent vs the one the module saw: no {FOLDER}/{INTENT_BEFORE} to "
            f"compare"
        )
        return lines
    diff = intent_diff(before, intent)
    if diff == ["no change"]:
        lines.append("  intent vs the one the module saw: no change")
    else:
        lines.append(f"  intent vs the one the module saw ({len(diff)} key(s)):")
        lines += [f"    {d}" for d in diff]
    return lines
