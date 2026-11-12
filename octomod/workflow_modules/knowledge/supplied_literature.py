"""Literature the human already has: `intent.supplied_literature`.

Items in the research contract's shape (`ITEM_KEYS`), frozen at the intent gate
into their own run-level record and handed to construction as `retrieved_evidence`
tagged `origin: human`. Agents receive the claims, never the document (cached
into the run for audit). The research fence applies (blocklist, and the year
horizon where declared), and a benchmark case with `truth/` must declare both
its horizon and `supplied-literature` in `truth/STAGED-ON-PURPOSE.txt`.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from octomod.result.node import Node

# the research contract's item shape (`agents/__init__.py`, role `research`)
ITEM_KEYS = ("source", "title", "year", "locator", "supports", "quote", "url")
REQUIRED_KEYS = ("source", "supports")
ORIGIN_HUMAN = "human"
ORIGIN_RESEARCH = "research"
# the line a benchmark case writes in truth/STAGED-ON-PURPOSE.txt to declare it
DECLARATION = "supplied-literature"


def items(intent: dict) -> list[dict]:
    """The supplied items as a list — `[]` when the intent has none. Shape is
    not checked here (see `problems`)."""
    raw = (intent or {}).get("supplied_literature")
    if not raw:
        return []
    return list(raw) if isinstance(raw, (list, tuple)) else [raw]


def case_document(url) -> PurePosixPath | None:
    """The case-relative path a `file:` url names, or None.

    `file:./paper/x.pdf`, `file:paper/x.pdf` and `file:/paper/x.pdf` all name
    `paper/x.pdf`: the path after `file:`, leading slashes dropped, read
    against the case folder the run reads (`octomod.connectors.web_cache.cache_source`
    joins it to its `base_dir`, and the input snapshot carries the file it
    names). An absolute `file:///…` and every other url name no case file."""
    url = str(url or "")
    if not url.startswith("file:") or url.startswith("file:///"):
        return None
    rel = url[len("file:") :].lstrip("/")
    return PurePosixPath(rel) if rel else None


def problems(intent: dict) -> list[str]:
    """T0 shape check, in the intent validator's vocabulary; returns failures
    (empty = pass). A bad item is named by its index in `intent.yaml`."""
    raw = (intent or {}).get("supplied_literature")
    if raw in (None, [], {}):
        return []
    if not isinstance(raw, list):
        return [
            "intent.supplied_literature must be a LIST of evidence items "
            f"({', '.join(ITEM_KEYS)}), got {type(raw).__name__}"
        ]
    out: list[str] = []
    for k, it in enumerate(raw):
        where = f"intent.supplied_literature[{k}]"
        if not isinstance(it, dict):
            out.append(f"{where} is not an object (an item has {ITEM_KEYS})")
            continue
        for key in REQUIRED_KEYS:
            if not str(it.get(key) or "").strip():
                out.append(f"{where}.{key} missing or empty")
        year = it.get("year")
        if year is not None and not (
            isinstance(year, int) and not isinstance(year, bool)
        ):
            out.append(f"{where}.year must be an integer year, got {year!r}")
        unknown = sorted(set(it) - set(ITEM_KEYS))
        if unknown:
            out.append(
                f"{where} carries unknown key(s) {unknown}; the shape is "
                f"{list(ITEM_KEYS)}"
            )
    return out


def read_blocklist(path: Path | None) -> list[str]:
    """`blocklist.txt` entries: one per line, `#` comments and blanks dropped.
    An absent file is an empty list — a recorded choice, never an error."""
    if path is None or not Path(path).exists():
        return []
    return [
        ln.strip()
        for ln in Path(path).read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _blob(it: dict) -> str:
    return " ".join(str(it.get(k, "")) for k in ("source", "title", "url")).casefold()


def fence_refusals(
    supplied: list[dict], forbidden_sources: list[str], horizon: int | None
) -> list[str]:
    """The refusals the fence makes, each naming the item. Same matching as the
    engine-side filter on research items (`model._maybe_research`): a
    blocklist entry is a case-folded substring of the item's source, title or
    url; the horizon is exclusive above (`year > horizon`)."""
    out: list[str] = []
    for k, it in enumerate(supplied):
        if not isinstance(it, dict):
            continue
        name = str(it.get("source") or it.get("title") or f"item {k}")[:90]
        blob = _blob(it)
        hit = [b for b in forbidden_sources if b.casefold() in blob]
        if hit:
            out.append(
                f"intent.supplied_literature[{k}] ({name!r}) names a forbidden "
                f"source {hit} — blocklist.txt applies to supplied literature too; "
                f"a human may add evidence, not bypass the fence"
            )
        year = it.get("year")
        if (
            horizon is not None
            and isinstance(year, int)
            and not isinstance(year, bool)
            and year > int(horizon)
        ):
            out.append(
                f"intent.supplied_literature[{k}] ({name!r}) is dated {year}, "
                f"after this case's declared horizon {horizon} "
                f"(testcase.yaml research.max_publication_year)"
            )
    return out


def horizon_problem(
    testcase: dict, supplied: list[dict], case_name: str, testcase_dir: Path | None
) -> str | None:
    """The refusal for a benchmark case (one with a `truth/` folder) that
    supplies literature without declaring `research.max_publication_year` in
    testcase.yaml, or None. An application case need not declare it: its items
    are then not year-fenced, and the S0 artifact row records
    `year_fenced: false`."""
    if not supplied:
        return None
    horizon = (testcase.get("research") or {}).get("max_publication_year")
    if horizon is not None:
        return None
    if testcase_dir is None or not (Path(testcase_dir) / "truth").is_dir():
        return None
    return (
        f"testcase {case_name!r} carries a truth/ folder AND supplies literature "
        f"(intent.supplied_literature) but declares no "
        f"`research.max_publication_year` in its testcase.yaml — a benchmark case "
        f"that supplies literature declares its horizon, research on or off, so the "
        f"year fence applies to what it hands construction. Declare it, or remove "
        f"the supplied literature."
    )


def declaration_problem(testcase_dir: Path, intent: dict) -> str | None:
    """A case with a `truth/` folder that supplies literature must say so in
    `truth/STAGED-ON-PURPOSE.txt` (the line `supplied-literature`). Returns the
    refusal, or None."""
    tc = Path(testcase_dir)
    if not items(intent) or not (tc / "truth").is_dir():
        return None
    p = tc / "truth" / "STAGED-ON-PURPOSE.txt"
    declared = set()
    if p.exists():
        for line in p.read_text(errors="ignore").splitlines():
            term = line.split("#", 1)[0].strip().lower()
            if term:
                declared.add(term)
    if DECLARATION in declared:
        return None
    return (
        f"{tc.name} carries a truth/ folder AND intent.supplied_literature: a "
        f"benchmark case that supplies literature must declare it — add the line "
        f"`{DECLARATION}` (reason after `#`) to truth/STAGED-ON-PURPOSE.txt, and "
        f"make sure the items name nothing the truth uses"
    )


def normalized(supplied: list[dict]) -> list[dict]:
    """The items as construction receives them: every contract key present,
    `origin: human`, and a stable `id` (`lit_1`, `lit_2`, …) the build report
    can cite when the source string is long."""
    out = []
    for k, it in enumerate(supplied, start=1):
        row = {key: it.get(key) for key in ITEM_KEYS}
        row["id"] = f"lit_{k}"
        row["origin"] = ORIGIN_HUMAN
        out.append(row)
    return out


def card_lines(supplied: list[dict]) -> list[str]:
    """What the intent gate shows about the supplied literature."""
    if not supplied:
        return []
    out = [
        f"supplied_literature: {len(supplied)} item(s) the human hands to "
        f"{reaches_text()} (origin: human; the fence applies):"
    ]
    for k, it in enumerate(supplied, start=1):
        src = str(it.get("source") or "?")[:70]
        year = f" ({it.get('year')})" if it.get("year") else ""
        loc = f" [{it.get('locator')}]" if it.get("locator") else ""
        out.append(
            f"  lit_{k}: {src}{year}{loc} — {str(it.get('supports') or '')[:80]}"
        )
    return out


def _bounded(key: str, text: str) -> bool:
    """`key` occurs in `text` and is not part of a longer identifier."""
    import re

    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", text) is not None


def attribution(decisions: list, supplied: list[dict], research: list[dict]) -> dict:
    """Which decisions leaned on which origin, from the build report's evidence
    entries. A decision cites an item when one of its evidence entries'
    `source`, `locator` or `supports` text contains the item's `id`, its
    `source` string, its `title`, or its `url` (case-folded). Counts, and the
    ids of decisions per origin — read by the ledger and `decisions_md`."""

    def keys_of(it: dict) -> list[str]:
        ks = [
            str(it.get(k) or "").casefold().strip()
            for k in ("id", "source", "title", "url")
        ]
        return [k for k in ks if len(k) >= 4]

    sup_keys = [keys_of(it) for it in supplied]
    res_keys = [keys_of(it) for it in research]
    leaned_human, leaned_research, cited_none = [], [], []
    for i, d in enumerate(decisions or []):
        evs = [e for e in (d.get("evidence") or []) if isinstance(e, dict)]
        text = " ".join(
            str(e.get(k) or "") for e in evs for k in ("source", "locator", "supports")
        ).casefold()
        label = str(d.get("decision") or f"decision {i}")[:60]
        # bounded by non-word characters, so `lit_1` cannot match `lit_10`
        hit_h = any(any(_bounded(k, text) for k in ks) for ks in sup_keys)
        hit_r = any(any(_bounded(k, text) for k in ks) for ks in res_keys)
        if hit_h:
            leaned_human.append(label)
        if hit_r:
            leaned_research.append(label)
        if not hit_h and not hit_r:
            cited_none.append(label)
    return {
        "n_decisions": len(decisions or []),
        "n_supplied_items": len(supplied),
        "n_research_items": len(research),
        "leaned_on_human": leaned_human,
        "leaned_on_research": leaned_research,
        "cited_neither": len(cited_none),
    }


# The items are frozen into their own run-level record and kept out of
# `intent` and `ctx.intent`, because many roles are granted `intent`: only
# the roles the routing table grants `supplied_literature` receive them.
# `construction_verification` does not: an auditor that reads the claims construction
# used is not independent of them.

FROZEN_KEY = "supplied_literature"


def reaches() -> list[str]:
    """The roles the frozen items reach: construction (as retrieved_evidence,
    origin: human) and every role the routing table lets see
    `supplied_literature`. The one source for every text that names them."""
    from octomod.agents import routing

    return ["construction"] + [
        r
        for r, row in routing.ROUTING.items()
        if r != "construction" and "supplied_literature" in row.get("sees", ())
    ]


def reaches_text() -> str:
    """'construction, knowledge, observation and revision'."""
    who = reaches()
    return who[0] if len(who) == 1 else ", ".join(who[:-1]) + " and " + who[-1]


def frozen_node(root: Node) -> Node:
    return root / FROZEN_KEY


def freeze(root: Node, supplied: list[dict]) -> str | None:
    """Write the run-level snapshot at the intent gate. Returns its sha, or
    None when the intent supplies nothing (no empty record is written — an
    absent record means "none supplied", and the S1 ledger says so)."""
    if not supplied:
        return None
    return frozen_node(root).put(
        {
            "items": list(supplied),
            "frozen_at": "intent",
            "reaches": reaches(),
            "note": (
                "literature the human staged in intent.supplied_literature; kept "
                f"OUT of the intent so that only {reaches_text()} receive it: "
                "construction as retrieved_evidence (origin: human), every other "
                "role as supplied_literature (the routing table grants it)"
            ),
        },
    )


def load_frozen(root: Node) -> list[dict]:
    """The items S0 froze, or [] — the only source S1 reads."""
    try:
        return list(frozen_node(root).get({}).get("items") or [])
    except Exception:  # noqa: BLE001
        return []


def strip_from_intent(intent: dict) -> dict:
    """The intent as every agent may see it: without the supplied items."""
    return {k: v for k, v in (intent or {}).items() if k != "supplied_literature"}
