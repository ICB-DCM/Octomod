"""The literature behind each reaction a model of the system may contain, and
the base construction builds from it.

The knowledge module runs before the intent is frozen (`octomod/workflow_modules/knowledge/engine.py`)
and leaves its dossier in the staging folder (`knowledge/knowledge.json`),
which every run snapshots into its record (`input/knowledge/…`). What this
module does with it inside the run:

1. **The intent names the reactions the model MUST contain**
   (`intent.required_reactions`); the module keeps each one, `required`,
   whatever the literature says, beside the ESSENTIAL reactions a base model
   of the system needs and everything else it found.
2. **The engine grades each entry** (`grade`). A grade is a BAND — high,
   medium, low, weak, none — decided from the strongest qualifying evidence
   under the declared rule table (`grounding.grading` in the workflow spec),
   first matching rule wins, and explained by the source that earned it.
   Never arithmetic: no weight, no product, no number on any card. Only an
   item that passes the preconditions counts at all: its identifier is not
   unresolvable, it is inside the fence, its class is in the vocabulary, and
   one paper cited twice is one source. What the metadata decides (a
   database namespace, a model repository, a publication typed a review)
   overrides the agent's class; a verifier's reading that differs grades by
   the weaker; a contradicting source flags the reaction `contested` and caps
   it. Offline, nothing is graded: `not_applicable`.
3. **The support floor** (`suggest_floor`, `read_floor_decision`,
   `floor_of`): the band a reaction's grade must reach to enter the base. The
   engine suggests it from the essential reactions' grades; the person
   decides it, and the round records it at `space/floor`.
4. **The round's dossier** (`dossier_of`): round 0 copies the staged dossier
   to `rounds/round_0/reaction_evidence` once; the view adds the reactions a
   targeted search admitted (`rounds/round_k/knowledge_admitted`, origin
   `search`). A later round reads the most recent round's (`latest_dossier`).
5. **Construction builds the BASE from the essential set** (`base_set`,
   `essential_rows`, `BASE_INSTRUCTION`): the required reactions, the
   essential ones at or above the floor, the unsupported ones the person did
   not drop, and the admitted ones — every one implemented, no conversion
   added. A conversion the base cannot do without is named in the reply's
   `missing`, and the engine searches for it.
6. **The engine annotates the model it built** (`annotate`): every reaction,
   in every direction its rate law can carry, is matched to the dossier by
   its reactant and product species and labelled `user-provided`,
   `database-supported`, `literature-supported` or `inferred`, with the
   origin and grade of the entries it matches. The record is the model's
   `reaction_support`; `model_essential_reactions` (`essential_check`) fails a
   base that lacks an entry of the set or carries a conversion outside it.
7. **The expansion agent is shown the same dossier** (`expansion_context`),
   and every axis it proposes is annotated by the reactions its patch adds to
   the base (`annotate_axes`), recorded at the round's `expansion_support`
   and put to the person on the expansion card, one line per axis.
8. **What a round ADDS is held to a floor below the base's**
   (`floor_refusals`): a discrimination round's expansions at the variants'
   floor (`variants_floor`: the base's lowered by `grounding.variants_offset`),
   an expansion's axes at the floor of the round it seeds (`scheduled_floor`:
   the round's lowered by its step, or the person's). An added conversion no
   entry at that floor describes is refused by name, after the round's one
   targeted search; a required reaction leaves the model only by the
   person's edit of the intent (`axis_required_lost`).

How binding 5, 6 and 8 are is the grounding MODE (`grounding_mode`: the
case's `grounding.mode`, else the workflow's). `strict` is as written above.
`advisory` treats the dossier as prior knowledge: construction may add any
reaction (`ADVISORY_INSTRUCTION`), `model_essential_reactions` blocks only a
required reaction the base lacks, no search ladder runs, and whatever a
round adds below its floor stays and is flagged on its card
(`below_floor_line`) — the floor decides what is flagged, the data what stays.
"""

from __future__ import annotations

import re

# the ledger module of the dossier's copy into the round and of its notes
MODULE = "model_grounding"
# the round's copy of the staged dossier, beside `evidence` and
# `expansion_evidence`
DOSSIER_KEY = "reaction_evidence"
# where the run holds the knowledge module's output: the staging folder's
# `knowledge/knowledge.json`, snapshotted into the record's `input` group
STAGED_DOSSIER = "knowledge/knowledge.json"
# the documents a targeted search cites, beside the research role's
SOURCES_KEY = "evidence_sources"
# a model's annotation against the dossier, at its model node
SUPPORT_KEY = "reaction_support"
# the gate a base fails when it lacks an entry of the essential set, or
# carries a conversion outside it
ESSENTIAL_GATE = "model_essential_reactions"
# the round's targeted searches (children `1`, `2`, …) and the reactions they
# admitted into the base
SEARCH_KEY = "knowledge_search"
ADMITTED_KEY = "knowledge_admitted"

# where a model reaction comes from, weakest first: a reaction is labelled
# with the weakest of the directions its rate law can carry
USER_PROVIDED = "user-provided"
DATABASE_SUPPORTED = "database-supported"
LITERATURE_SUPPORTED = "literature-supported"
INFERRED = "inferred"
SUPPORT_LABELS = (INFERRED, LITERATURE_SUPPORTED, DATABASE_SUPPORTED, USER_PROVIDED)
# the evidence kind that makes a matched entry database-supported
DATABASE_KIND = "curated_database"

# the research contract's evidence item, plus the classification the grade
# is decided from: what kind of evidence, how close its system, and whether it
# supports or contradicts the reaction
ITEM_KEYS = (
    "source",
    "title",
    "year",
    "locator",
    "supports",
    "quote",
    "url",
    "evidence_kind",
    "context_match",
    "context_note",
    "stance",
)
RESOLUTION_CLASSES = ("resolved", "unchecked", "not_checkable", "unresolvable")


# ------------------------------------------------------------ equations


class EquationError(ValueError):
    """An equation the engine cannot read; the message says what is wrong."""


_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TERM = re.compile(
    r"^(?:(?P<n>\d+(?:\.\d+)?)\s*\*?\s*)?(?P<id>[A-Za-z_][A-Za-z0-9_]*)$"
)
# an empty side: synthesis `-> A`, degradation `A ->`
_EMPTY_SIDE = {"", "0", "null", "none", "nothing", "{}", "∅", "ø"}
# longest first, so `<->` is never read as `->` with a stray `<`
_ARROWS = (
    ("<->", True),
    ("<=>", True),
    ("⇌", True),
    ("->", False),
    ("=>", False),
    ("→", False),
)


def _side(text: str, where: str) -> dict[str, float]:
    t = text.strip()
    if t.lower() in _EMPTY_SIDE:
        return {}
    out: dict[str, float] = {}
    for term in t.split("+"):
        m = _TERM.match(term.strip())
        if not m:
            raise EquationError(
                f"{where} term {term.strip()!r} is not a species id (letters, "
                f"digits and _, not starting with a digit), optionally with a "
                f"coefficient ('2 A')"
            )
        sid = m.group("id")
        out[sid] = out.get(sid, 0.0) + float(m.group("n") or 1)
    return out


def parse_equation(text) -> dict:
    """`"A + 2 B -> C"` -> `{"reactants": {"A": 1.0, "B": 2.0},
    "products": {"C": 1.0}, "reversible": False}`.

    `->`, `=>` and `→` are one direction; `<->`, `<=>` and `⇌` are reversible.
    Either side may be empty (synthesis `-> A`, degradation `A ->`), not both.
    Species are identifiers, because the construction agent must be able to
    use them verbatim as Antimony ids — that is what lets the engine check a
    model reaction against the entry it implements."""
    s = str(text or "").strip()
    if not s:
        raise EquationError("empty equation")
    arrow = next(((a, rev) for a, rev in _ARROWS if a in s), None)
    if arrow is None:
        raise EquationError(f"no arrow in {s!r} — write 'reactants -> products'")
    token, reversible = arrow
    if s.count(token) != 1:
        raise EquationError(f"more than one {token!r} in {s!r}")
    lhs, rhs = s.split(token)
    for other, _ in _ARROWS:
        if other in lhs or other in rhs:
            raise EquationError(f"more than one arrow in {s!r}")
    reactants = _side(lhs, "reactant")
    products = _side(rhs, "product")
    if not reactants and not products:
        raise EquationError(f"both sides of {s!r} are empty")
    if reactants == products:
        raise EquationError(f"{s!r} converts nothing: both sides are the same")
    return {"reactants": reactants, "products": products, "reversible": reversible}


def _coef(n: float) -> str:
    return "" if n == 1 else (f"{int(n)} " if float(n).is_integer() else f"{n:g} ")


def canonical(parsed: dict) -> str:
    """One spelling per reaction, species sorted, so two ways of writing the
    same conversion compare equal: `"B + A->C"` and `"A + B -> C"` are one."""

    def side(d: dict) -> str:
        return " + ".join(f"{_coef(n)}{sid}" for sid, n in sorted(d.items()))

    arrow = "<->" if parsed.get("reversible") else "->"
    return f"{side(parsed['reactants'])} {arrow} {side(parsed['products'])}".strip()


def participants(row: dict) -> set[str]:
    p = row["parsed"]
    return set(p["reactants"]) | set(p["products"]) | set(row.get("modifiers") or [])


# ------------------------------------------------ the intent's required reactions

REQUIRED_ITEM_KEYS = ("equation", "note", "modifiers")


def required_reactions(intent: dict) -> list[dict]:
    """The intent's `required_reactions` with engine ids (`req_1`, `req_2`, …
    by position), each parsed. `[]` when the intent names none. The shape was
    checked at the intent gate (`intent_problems`); an entry that still does
    not parse is skipped here rather than raised, and keeps its position."""
    raw = (intent or {}).get("required_reactions")
    if not raw:
        return []
    out = []
    for k, it in enumerate(raw if isinstance(raw, list) else [raw], start=1):
        eq = it.get("equation") if isinstance(it, dict) else it
        try:
            parsed = parse_equation(eq)
        except EquationError:
            continue
        row = {
            "id": f"req_{k}",
            "equation": canonical(parsed),
            "written": str(eq).strip(),
            "parsed": parsed,
        }
        if isinstance(it, dict):
            if it.get("note"):
                row["note"] = str(it["note"])
            if it.get("modifiers"):
                row["modifiers"] = [str(m) for m in it["modifiers"]]
        out.append(row)
    return out


def intent_problems(intent: dict) -> list[str]:
    """T0 shape check on `intent.required_reactions`, in the intent
    validator's vocabulary. An entry is an equation string (`"A -> B"`) or an
    object `{equation, note, modifiers}`; each failure names its index, since
    the human fixes it by editing `intent.yaml`."""
    raw = (intent or {}).get("required_reactions")
    if raw in (None, [], ""):
        return []
    if not isinstance(raw, list):
        return [
            "intent.required_reactions must be a LIST of reactions — 'A -> B', "
            f"or {{equation, note, modifiers}} — got {type(raw).__name__}"
        ]
    out: list[str] = []
    seen: dict[str, int] = {}
    for k, it in enumerate(raw):
        where = f"intent.required_reactions[{k}]"
        if isinstance(it, dict):
            unknown = sorted(set(it) - set(REQUIRED_ITEM_KEYS))
            if unknown:
                out.append(
                    f"{where} carries unknown key(s) {unknown}; an entry is "
                    f"'A -> B' or {{{', '.join(REQUIRED_ITEM_KEYS)}}}"
                )
            mods = it.get("modifiers")
            if mods is not None and not (
                isinstance(mods, list)
                and all(isinstance(m, str) and _ID.fullmatch(m) for m in mods)
            ):
                out.append(f"{where}.modifiers must be a list of species ids")
            eq = it.get("equation")
        elif isinstance(it, str):
            eq = it
        else:
            out.append(f"{where} is neither an equation string nor an object")
            continue
        try:
            c = canonical(parse_equation(eq))
        except EquationError as e:
            out.append(f"{where}: {e}")
            continue
        if c in seen:
            out.append(f"{where} repeats intent.required_reactions[{seen[c]}] ({c})")
        seen.setdefault(c, k)
    return out


# ------------------------------------------------------------ configuration


def active(ctx) -> bool:
    """Whether the run builds on the knowledge module's output: its inputs
    hold the module's dossier (`knowledge/knowledge.json`, the record's
    `input/knowledge/…`) and the case declares no skip. A malformed
    `grounding:` block was refused at run start by name, so it reads as no
    skip here."""
    try:
        if skip_declared(getattr(ctx, "testcase", None) or {}):
            return False
    except ValueError:
        pass
    cache = getattr(ctx, "cache", None)
    if isinstance(cache, dict) and "_knowledge_active" in cache:
        return bool(cache["_knowledge_active"])
    from octomod.workflow_modules.knowledge import engine as _kn

    on = _kn.has_staged(ctx)
    if isinstance(cache, dict):
        # the inputs are the record's snapshot: they do not change in a run
        cache["_knowledge_active"] = on
    return on


ADVISORY = "advisory"
STRICT = "strict"
GROUNDING_MODES = (ADVISORY, STRICT)


def _mode_word(value, where: str) -> str:
    word = _word(value)
    if word not in GROUNDING_MODES:
        raise ValueError(
            f"{where} {value!r} is not a grounding mode — accepted: "
            f"{', '.join(GROUNDING_MODES)}"
        )
    return word


def case_mode(testcase: dict) -> str | None:
    """The mode testcase.yaml's `grounding:` block declares, checked by name;
    None when it declares none."""
    block = _grounding_block(testcase)
    if not block or "mode" not in block:
        return None
    return _mode_word(block.get("mode"), "grounding.mode")


def mode_of(testcase: dict | None, spec) -> str:
    """The grounding mode of a case under a workflow spec: the case's
    `grounding.mode`, else the workflow's, else advisory."""
    own = case_mode(testcase or {})
    if own is not None:
        return own
    if spec is None:
        return ADVISORY
    return _mode_word(
        spec.get("grounding.mode", "advisory"), "the workflow's grounding.mode"
    )


def grounding_mode(ctx) -> str:
    """How the run holds what it builds to the dossier: `advisory` (the
    dossier is prior knowledge; what it does not back is flagged to the
    person) or `strict` (the base is exactly the essential set; additions
    below their floor are refused) — `mode_of` the run's case and spec."""
    return mode_of(getattr(ctx, "testcase", None), getattr(ctx, "spec", None))


def strict(ctx) -> bool:
    return grounding_mode(ctx) == STRICT


def _count(value, key: str) -> int:
    """A declared whole number of at least 0, or a refusal naming its key."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a whole number of at least 0, got {value!r}")
    return value


def floor_step(spec) -> int:
    """How many bands an expansion round lowers the support floor by."""
    return _count(spec.get("grounding.floor_step", 1), "grounding.floor_step")


def variants_offset(spec) -> int:
    """How many bands below the base's floor a discrimination round's
    expansions may add a reaction at."""
    return _count(spec.get("grounding.variants_offset", 1), "grounding.variants_offset")


def search_caps(spec) -> dict[str, int]:
    """The targeted searches the engine may spend: `per_redraft` (a
    construction redraft) and `per_round` (the expansions of a round, an
    expansion)."""
    return {
        "per_redraft": _count(
            spec.get("grounding.search.per_redraft", 1),
            "grounding.search.per_redraft",
        ),
        "per_round": _count(
            spec.get("grounding.search.per_round", 1), "grounding.search.per_round"
        ),
    }


def verify_enabled(spec) -> bool:
    """Whether an online survey's counting items are re-classified by the
    advisory verifier; offline there is nothing to verify."""
    return bool(spec.get("grounding.verify", True))


def fence(testcase: dict, spec, case_name: str, blocklist_path) -> dict | None:
    """Run start, before anything is spent. A `reactions:` block is refused by
    name; a case that builds on the knowledge module needs the grade's rule
    table declared and well-formed, refused here by name. Returns the
    horizon (`research.max_publication_year`, the one horizon a case has, or
    None), the forbidden sources and a note; None for a case that declares
    its skip. What the module itself needs at run start — its output, the
    person's floor, the horizon of an online module — is
    `knowledge.run_start_problems`'s."""
    if "reactions" in (testcase or {}):
        raise ValueError(
            f"testcase {case_name!r} declares a `reactions:` block; the reaction "
            f"literature is the knowledge module's (./run.sh knowledge), and its "
            f"decision goes into testcase.yaml's `grounding:` block. Rename the "
            f"block."
        )
    try:
        if skip_declared(testcase or {}):
            return None
    except ValueError:
        # a malformed block is refused by name with the module's refusals
        return None
    try:
        grading_rules(spec)
        contested_cap(spec)
    except ValueError as e:
        raise ValueError(f"testcase {case_name!r}: {e}") from e
    from pathlib import Path

    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    year = ((testcase or {}).get("research") or {}).get("max_publication_year")
    entries = _lit.read_blocklist(Path(blocklist_path) if blocklist_path else None)
    return {
        "horizon": int(year) if year is not None else None,
        "forbidden_sources": entries,
        "note": (
            "construction builds on the knowledge module's essential reactions, "
            + (
                "no forbidden sources"
                if not entries
                else f"{len(entries)} forbidden source(s)"
            )
        ),
    }


# ------------------------------------------------------------ the grade

# what an evidence item is classified by, each strongest first: the order
# breaks a tie between two readings of one item the rule table grades alike
EVIDENCE_KINDS = (
    "direct_experimental",
    "curated_database",
    "mechanistic_model",
    "review",
    "indirect",
)
CONTEXT_MATCHES = ("same_system", "related_system", "different_system")
STANCES = ("supports", "contradicts")
SUPPORTS, CONTRADICTS = STANCES

# an entry's grade, strongest first: `none` when no source counts for it,
# `not_applicable` when nothing was searched (offline)
GRADE_BANDS = ("high", "medium", "low", "weak", "none", "not_applicable")
NONE = "none"
NOT_APPLICABLE = "not_applicable"
# the bands a rule earns; the rule table declares a list for each
RULE_BANDS = GRADE_BANDS[:4]
# what a rule may say
RULE_KEYS = ("kind", "context", "at_least", "earning", "any")
# what the grade says beside the band, per evidence item
GRADE_FLAGS = (
    "contested",
    "disputed_class",
    "class_corrected",
    "unquoted",
    "not_counted",
)


def _band_word(band) -> str:
    """A band as written, in the vocabulary's spelling: case-folded, with
    `not applicable` read as `not_applicable`."""
    return re.sub(r"[\s-]+", "_", str("" if band is None else band).strip().lower())


def band_rank(band) -> int:
    """0 for `high`, the strongest, up to 5 for `not_applicable`; a word
    outside the vocabulary is refused by name."""
    b = _band_word(band)
    if b not in GRADE_BANDS:
        raise ValueError(
            f"{band!r} is not a grade band — accepted: {', '.join(GRADE_BANDS)}"
        )
    return GRADE_BANDS.index(b)


def lower_band(band, steps: int = 1) -> str:
    """The band `steps` below `band`, never below `none`; `not_applicable`
    has nothing to lower and stays."""
    b = GRADE_BANDS[band_rank(band)]
    if b == NOT_APPLICABLE:
        return b
    n = _count(steps, "a band step")
    return GRADE_BANDS[min(band_rank(b) + n, band_rank(NONE))]


def _words(value) -> list[str] | None:
    """A rule's `kind` or `context`: one word or a list of words; None when
    the rule leaves it open."""
    if value is None:
        return None
    raw = value if isinstance(value, (list, tuple)) else [value]
    return [str(v).strip().lower() for v in raw]


def _rule_problems(rule, where: str, band: str) -> list[str]:
    if not isinstance(rule, dict) or not rule:
        return [f"{where} is not a rule: write {{kind: <k>, context: <c>}}"]
    out = []
    unknown = sorted(set(map(str, rule)) - set(RULE_KEYS))
    if unknown:
        out.append(f"{where} carries unknown key(s) {unknown}; accepted {RULE_KEYS}")
    if "any" in rule:
        if rule.get("any") is not True or len(rule) != 1:
            out.append(f"{where}: `any` is written alone, as {{any: true}}")
        return out
    n = rule.get("at_least", 1)
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        out.append(f"{where}.at_least must be a whole number of at least 1, got {n!r}")
    if "earning" in rule:
        earning = _band_word(rule.get("earning"))
        if "at_least" not in rule:
            out.append(f"{where}: `earning` needs `at_least: <n>` beside it")
        if set(rule) & {"kind", "context"}:
            out.append(f"{where}: `earning` stands without `kind` or `context`")
        if earning not in RULE_BANDS:
            out.append(
                f"{where}.earning {rule.get('earning')!r} is not a band a rule "
                f"earns — accepted {', '.join(RULE_BANDS)}"
            )
        elif band in RULE_BANDS and RULE_BANDS.index(earning) <= RULE_BANDS.index(band):
            out.append(
                f"{where}: sources earning {earning} cannot make {band} — the band "
                f"they each earn is a weaker one"
            )
        return out
    kinds = _words(rule.get("kind"))
    if not kinds:
        out.append(f"{where} names no `kind`")
    else:
        bad = [k for k in kinds if k not in EVIDENCE_KINDS]
        if bad:
            out.append(
                f"{where}.kind {bad} is not in the vocabulary — accepted "
                f"{' | '.join(EVIDENCE_KINDS)}"
            )
    contexts = _words(rule.get("context"))
    if contexts is not None:
        bad = [c for c in contexts if c not in CONTEXT_MATCHES]
        if bad or not contexts:
            out.append(
                f"{where}.context {bad or contexts} is not in the vocabulary — "
                f"accepted {' | '.join(CONTEXT_MATCHES)}"
            )
    return out


def rule_problems(rules) -> list[str]:
    """Every way a declared rule table is not well-formed, each by name; []
    when it is. A table maps each band from `high` to `weak` to its list of
    rules (`contested_caps_at` may sit beside them)."""
    if not isinstance(rules, dict) or not rules:
        return [
            "grounding.grading is not declared — the grade is decided by a "
            "declared rule table (band -> list of rules), never an engine default"
        ]
    out = []
    for band, lst in rules.items():
        where = f"grounding.grading.{band}"
        if band == "contested_caps_at":
            try:
                _cap_word(lst)
            except ValueError as e:
                out.append(f"{where}: {e}")
            continue
        if band not in RULE_BANDS:
            out.append(
                f"{where}: {band!r} is not a band a rule earns — accepted "
                f"{', '.join(RULE_BANDS)}"
            )
            continue
        if not isinstance(lst, list) or not lst:
            out.append(f"{where} must be a non-empty list of rules")
            continue
        for k, rule in enumerate(lst):
            out += _rule_problems(rule, f"{where}[{k}]", band)
    missing = [b for b in RULE_BANDS if b not in rules]
    if missing:
        out.append(
            f"grounding.grading declares no rules for {missing} — every band from "
            f"high to weak has its list"
        )
    return out


def grading_rules(spec) -> dict:
    """The declared rule table (`grounding.grading`), refused by name when it
    is missing or not well-formed: a grade decided by rules nobody declared is
    the agent-picks-its-own-criteria failure in another place."""
    raw = spec.get("grounding.grading")
    problems = rule_problems(raw)
    if problems:
        raise ValueError(
            "the workflow spec's grounding.grading is not a usable rule table: "
            + "; ".join(problems)
        )
    return dict(raw)


def _cap_word(value) -> str | None:
    """The band a contested entry is capped at, or None for no cap
    (`none`)."""
    if value is None or value is False:
        return None
    b = _band_word(value)
    if b == NONE:
        return None
    if b not in RULE_BANDS:
        raise ValueError(
            f"contested_caps_at {value!r} is not a band — accepted "
            f"{', '.join(RULE_BANDS)}, or none for no cap"
        )
    return b


def contested_cap(spec) -> str | None:
    """`grounding.contested_caps_at`: the band a contested entry is capped
    at, or None when the switch is `none`."""
    return _cap_word(spec.get("grounding.contested_caps_at", "medium"))


def resolution_class(status) -> str:
    """`octomod.connectors.web_cache.resolve_source`'s answer, as a precondition reads
    it. Network trouble, a check switched off and a check never run are all
    `unchecked` — never punished as fabrication."""
    s = str(status or "").strip().lower()
    if s == "resolved":
        return "resolved"
    if s == "unresolvable":
        return "unresolvable"
    if s in ("not-checkable", "not_checkable"):
        return "not_checkable"
    return "unchecked"


_DOI = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
_PMID = re.compile(r"pmid\D{0,3}(\d{4,9})", re.I)


def source_key(item: dict) -> str:
    """What makes two items the SAME source: the DOI, else the PMID, else the
    URL, else the source string — so one paper cited twice counts once.
    Independence is this proxy and nothing more: two papers from one lab are
    two sources."""
    blob = " ".join(str(item.get(k) or "") for k in ("source", "url"))
    m = _DOI.search(blob)
    if m:
        return "doi:" + m.group(0).rstrip(".,;)").lower()
    m = _PMID.search(blob)
    if m:
        return "pmid:" + m.group(1)
    url = str(item.get("url") or "").strip().lower().rstrip("/")
    if url.startswith(("http://", "https://")):
        return re.sub(r"^https?://(www\.)?", "", url)
    return re.sub(
        r"\s+", " ", str(item.get("source") or item.get("title") or "").strip().lower()
    )


# a curated pathway or reaction database, by identifier namespace or host
_DATABASE = re.compile(
    r"\b(reactome|kegg|rhea)\s*:|reactome\.org|kegg\.jp|genome\.jp/(kegg|dbget-bin)"
    r"|rhea-db\.org",
    re.I,
)
# a model repository entry: a BioModels identifier or host
_MODEL_ID = re.compile(r"\b(BIOMD\d{4,}|MODEL\d{6,})\b")
_MODEL_HOST = re.compile(r"\bbiomodels\s*:|biomodels\.net|ebi\.ac\.uk/biomodels", re.I)


def class_from_metadata(item: dict) -> str | None:
    """The evidence kind an item's metadata decides without reading it:
    `curated_database` for a database namespace or host, `mechanistic_model`
    for a BioModels entry, `review` when its publication types (PubMed's,
    `publication_types`, filled by the connector when online) include a
    review; None when the metadata decides nothing, and the agent's reading
    stands."""
    blob = " ".join(str(item.get(k) or "") for k in ("source", "url"))
    if _DATABASE.search(blob):
        return "curated_database"
    if _MODEL_ID.search(blob) or _MODEL_HOST.search(blob):
        return "mechanistic_model"
    types = item.get("publication_types")
    if isinstance(types, (list, tuple)) and any(
        "review" in str(t).lower().split() for t in types
    ):
        return "review"
    return None


def _word(value) -> str:
    return str(value or "").strip().lower()


def _single_rule(rule: dict) -> bool:
    """Can one item satisfy this rule on its own?"""
    return "earning" not in rule and int(rule.get("at_least", 1)) <= 1


def _matches(rule: dict, kind: str, context: str) -> bool:
    if rule.get("any") is True:
        return True
    kinds, contexts = _words(rule.get("kind")), _words(rule.get("context"))
    return bool(kinds) and kind in kinds and (contexts is None or context in contexts)


def _single_band(kind: str, context: str, rules: dict) -> str:
    """The band one supporting item of this class earns on its own."""
    for band in RULE_BANDS:
        if any(
            _single_rule(r) and _matches(r, kind, context)
            for r in rules.get(band) or []
        ):
            return band
    return NONE


def _strength(kind: str, context: str, rules: dict | None) -> tuple:
    """Smaller is stronger: the band the class earns alone under the table,
    then the vocabulary's own order."""
    k = EVIDENCE_KINDS.index(kind) if kind in EVIDENCE_KINDS else len(EVIDENCE_KINDS)
    c = (
        CONTEXT_MATCHES.index(context)
        if context in CONTEXT_MATCHES
        else len(CONTEXT_MATCHES)
    )
    b = band_rank(_single_band(kind, context, rules)) if rules else 0
    return (b, k, c)


def _classified(kind: str, context: str) -> bool:
    return kind in EVIDENCE_KINDS and context in CONTEXT_MATCHES


def _classify(item: dict, iid: str, rules: dict | None) -> dict:
    """One evidence item as the grade reads it: the class it is graded as,
    its stance, what is said about it, and why it does not count (None when
    it passes the preconditions)."""
    flags: list[dict] = []
    agent = (_word(item.get("evidence_kind")), _word(item.get("context_match")))
    second = None
    if item.get("second_kind") or item.get("second_context"):
        second = (
            _word(item.get("second_kind")) or agent[0],
            _word(item.get("second_context")) or agent[1],
        )
    meta = class_from_metadata(item)
    if meta is not None:
        if agent[0] != meta:
            flags.append(
                {
                    "flag": "class_corrected",
                    "item": iid,
                    "agent": agent[0] or "(none)",
                    "metadata": meta,
                }
            )
        agent = (meta, agent[1])
        if second is not None:
            second = (meta, second[1])
    reading = agent
    if second is not None and second != agent:
        if not _classified(*second):
            why = "the verifier's reading is outside the vocabulary; the agent's stands"
        elif not _classified(*agent):
            reading, why = second, "the agent's reading is outside the vocabulary"
        else:
            # the WEAKER reading grades the item; on a tie the verifier's
            reading = max(
                (agent, second), key=lambda r: (_strength(*r, rules), r is second)
            )
            why = "the weaker of the two readings grades the item"
        flags.append(
            {
                "flag": "disputed_class",
                "item": iid,
                "agent": {"evidence_kind": agent[0], "context_match": agent[1]},
                "verifier": {"evidence_kind": second[0], "context_match": second[1]},
                "graded_as": {"evidence_kind": reading[0], "context_match": reading[1]},
                "why": why,
            }
        )
    kind, context = reading
    stance = _word(item.get("stance")) or SUPPORTS
    why_not = None
    if resolution_class(item.get("resolution")) == "unresolvable":
        why_not = "its identifier does not resolve"
    elif kind not in EVIDENCE_KINDS:
        why_not = f"evidence_kind {kind or '(none)'!r} is not in the vocabulary"
    elif context not in CONTEXT_MATCHES:
        why_not = f"context_match {context or '(none)'!r} is not in the vocabulary"
    elif stance not in STANCES:
        why_not = f"stance {stance!r} is neither supports nor contradicts"
    return {
        "id": iid,
        "source": str(item.get("source") or item.get("title") or ""),
        "source_key": str(item.get("source_key") or source_key(item)),
        "kind": kind,
        "context": context,
        "stance": stance,
        "flags": flags,
        "why_not": why_not,
    }


def _readings(entry: dict, rules: dict | None) -> list[tuple[dict, dict]]:
    """(item, reading) for every evidence item of an entry, in order, with
    the preconditions applied: an unresolvable identifier or a classification
    outside the vocabulary does not count, and of the items citing one source
    only the strongest counts."""
    out: list[tuple[dict, dict]] = []
    kept: dict[str, int] = {}
    for k, it in enumerate(entry.get("evidence") or [], start=1):
        if not isinstance(it, dict):
            continue
        r = _classify(it, str(it.get("id") or f"{entry.get('id')}.e{k}"), rules)
        out.append((it, r))
        if r["why_not"]:
            continue
        j = kept.get(r["source_key"])
        if j is None:
            kept[r["source_key"]] = len(out) - 1
            continue
        other = out[j][1]
        if _strength(r["kind"], r["context"], rules) < _strength(
            other["kind"], other["context"], rules
        ):
            other["why_not"] = f"the same source as {r['id']}, which counts"
            kept[r["source_key"]] = len(out) - 1
        else:
            r["why_not"] = f"the same source as {other['id']}, which counts"
    return out


def counting_items(entry: dict, rules: dict | None = None) -> list[dict]:
    """The evidence items that count for an entry — those that pass the
    preconditions: an identifier that is not unresolvable, a classification
    in the vocabulary, one item per source (the strongest), inside the fence
    (a fenced item is in `evidence_dropped`, never here). A graded entry
    answers from its own record (`counting`); without it the items are
    read again, under `rules` when given."""
    items = [it for it in entry.get("evidence") or [] if isinstance(it, dict)]
    ids = entry.get("counting")
    if rules is None and isinstance(ids, list):
        wanted = {str(i) for i in ids}
        return [it for it in items if str(it.get("id")) in wanted]
    return [it for it, r in _readings(entry, rules) if not r["why_not"]]


def _satisfies(rule: dict, supporting: list[dict], rules: dict) -> list[dict]:
    """The readings that satisfy one rule, or [] when it is not satisfied."""
    if rule.get("any") is True:
        return supporting[:1]
    n = int(rule.get("at_least", 1))
    if "earning" in rule:
        floor = band_rank(rule["earning"])
        hits = [
            r
            for r in supporting
            if band_rank(_single_band(r["kind"], r["context"], rules)) <= floor
        ]
    else:
        hits = [r for r in supporting if _matches(rule, r["kind"], r["context"])]
    return hits[:n] if len(hits) >= n else []


def rule_text(rule: dict) -> str:
    """A rule as a reader reads it."""
    if rule.get("any") is True:
        return "any counting source"
    n = int(rule.get("at_least", 1))
    if "earning" in rule:
        return f"{n} independent sources, each earning {rule['earning']} on its own"
    kinds = " or ".join(_words(rule.get("kind")) or [])
    contexts = _words(rule.get("context"))
    head = f"a {kinds} source" if n == 1 else f"{n} independent {kinds} sources"
    return head + (f" in {' or '.join(contexts)}" if contexts else "")


def grade(entry: dict, rules: dict, *, contested_caps_at="medium") -> dict:
    """An entry's grade: the BAND the strongest qualifying evidence earns
    under the declared rule table — bands tried strongest first, the first
    satisfied rule deciding — explained by the source(s) that earned it.
    Never arithmetic: nothing is weighted, multiplied or summed.

    `{"band", "because": [{id, source, evidence_kind, context_match, rule}],
    "flags": [...], "counting": [item ids], "readings": [...]}`. No counting
    item gives `none`. A counting item that contradicts the entry never earns
    a band: it flags the entry `contested` and caps its band at
    `contested_caps_at` (`none` in the table or here: no cap). A verifier's
    reading (`second_kind`, `second_context`) that differs from the agent's
    grades the item by the weaker of the two, flagged `disputed_class`; a
    metadata class (`class_from_metadata`) overrides both, flagged
    `class_corrected`. A counting item with no quote, or whose quote is not
    in its cached document (`quote_found: False`), counts, flagged
    `unquoted`."""
    table = dict(rules or {})
    cap = _cap_word(table.pop("contested_caps_at", contested_caps_at))
    problems = rule_problems(table)
    if problems:
        raise ValueError("not a usable rule table: " + "; ".join(problems))
    readings = _readings(entry, table)
    flags = [f for _, r in readings for f in r["flags"]]
    counting = [(it, r) for it, r in readings if not r["why_not"]]
    flags += [
        {"flag": "not_counted", "item": r["id"], "why": r["why_not"]}
        for _, r in readings
        if r["why_not"]
    ]
    for it, r in counting:
        if not str(it.get("quote") or "").strip():
            flags.append({"flag": "unquoted", "item": r["id"], "why": "no quote"})
        elif it.get("quote_found") is False:
            flags.append(
                {
                    "flag": "unquoted",
                    "item": r["id"],
                    "why": "its quote is not in the cached document",
                }
            )
    supporting = [r for _, r in counting if r["stance"] == SUPPORTS]
    against = [r for _, r in counting if r["stance"] == CONTRADICTS]
    band, earned, won = NONE, [], None
    for b in RULE_BANDS:
        for rule in table.get(b) or []:
            earned = _satisfies(rule, supporting, table)
            if earned:
                band, won = b, rule
                break
        if earned:
            break
    if against:
        capped = cap is not None and band_rank(band) < band_rank(cap)
        if capped:
            band = cap
        flags += [
            {
                "flag": "contested",
                "item": r["id"],
                "source": r["source"],
                "capped_at": cap if capped else None,
            }
            for r in against
        ]
    return {
        "band": band,
        "because": [
            {
                "id": r["id"],
                "source": r["source"],
                "evidence_kind": r["kind"],
                "context_match": r["context"],
                "rule": rule_text(won),
            }
            for r in earned
        ],
        "flags": flags,
        "counting": [r["id"] for _, r in counting],
        "readings": [
            {
                "id": r["id"],
                "counts": not r["why_not"],
                "graded_as": {
                    "evidence_kind": r["kind"],
                    "context_match": r["context"],
                },
                "stance": r["stance"],
                **({"not_counted": r["why_not"]} if r["why_not"] else {}),
            }
            for _, r in readings
        ],
    }


def _not_graded(entry: dict) -> None:
    entry.update(grade=NOT_APPLICABLE, because=[], flags=[], counting=[], n_sources=0)


def grade_reactions(dossier: dict, spec) -> dict:
    """Every entry of the dossier graded by the engine, in place: each
    reaction (and each fact, when the dossier has `facts`) gains `grade`
    (the band), `because` (the source(s) that earned it), `flags`,
    `counting` (the ids of the items that count) and `n_sources` (how many
    independent sources support it); each evidence item says whether it
    counts, the class it was graded as, and why not when it does not. An
    offline dossier (`mode: offline`) searched nothing: every grade is
    `not_applicable`. The table the dossier was graded by is recorded beside
    it (`grading`). The dossier is returned."""
    offline = _word(dossier.get("mode")) == "offline"
    rules = None if offline else grading_rules(spec)
    cap = None
    if not offline:
        # the table's own switch, when it carries one, before the spec's
        cap = (
            _cap_word(rules["contested_caps_at"])
            if "contested_caps_at" in rules
            else contested_cap(spec)
        )
    for key in ("reactions", "facts"):
        for entry in dossier.get(key) or []:
            if not isinstance(entry, dict):
                continue
            items = [it for it in entry.get("evidence") or [] if isinstance(it, dict)]
            for k, it in enumerate(items, start=1):
                if not it.get("id"):
                    it["id"] = f"{entry.get('id')}.e{k}"
            if offline:
                _not_graded(entry)
                continue
            g = grade(entry, rules, contested_caps_at=cap)
            audit = {r["id"]: r for r in g["readings"]}
            for it in items:
                r = audit.get(str(it.get("id"))) or {}
                it["resolution_class"] = resolution_class(it.get("resolution"))
                it["counts"] = bool(r.get("counts"))
                it["graded_as"] = r.get("graded_as")
                it.pop("not_counted", None)
                if r.get("not_counted"):
                    it["not_counted"] = r["not_counted"]
            entry["grade"] = g["band"]
            entry["because"] = g["because"]
            entry["flags"] = g["flags"]
            entry["counting"] = g["counting"]
            entry["n_sources"] = sum(
                1 for r in g["readings"] if r["counts"] and r["stance"] == SUPPORTS
            )
    dossier["grading"] = (
        {"mode": "offline"}
        if offline
        else {"rules": rules, "contested_caps_at": cap if cap is not None else NONE}
    )
    return dossier


def band_text(band) -> str:
    """A band as a card prints it."""
    b = _band_word(band) or NONE
    return "not applicable" if b == NOT_APPLICABLE else b


def because_text(band, because) -> str:
    """`medium — <source> (direct_experimental, related_system)`: the band
    and the source(s) that earned it, the way every card says a grade."""
    b = _band_word(band) or NONE
    if b == NOT_APPLICABLE:
        return "not applicable (offline: nothing was searched)"
    if not because:
        return "none — no source counts" if b == NONE else band_text(b)
    shown = "; ".join(
        f"{x.get('source') or x.get('id')} ({x.get('evidence_kind')}, "
        f"{x.get('context_match')})"
        for x in because
    )
    return f"{band_text(b)} — {shown}"


def flag_text(flag: dict) -> str:
    """One flag of a grade, as a card prints it."""
    name, iid = flag.get("flag"), flag.get("item")
    if name == "contested":
        cap = flag.get("capped_at")
        return f"contested by {iid} ({flag.get('source')})" + (
            f" — capped at {cap}" if cap else ""
        )
    if name == "disputed_class":
        a, v = flag.get("agent") or {}, flag.get("verifier") or {}
        g = flag.get("graded_as") or {}
        return (
            f"disputed class of {iid}: the agent read {a.get('evidence_kind')}, "
            f"{a.get('context_match')}; the verifier {v.get('evidence_kind')}, "
            f"{v.get('context_match')}; graded as {g.get('evidence_kind')}, "
            f"{g.get('context_match')}"
        )
    if name == "class_corrected":
        return (
            f"class of {iid} corrected from its metadata: {flag.get('agent')} -> "
            f"{flag.get('metadata')}"
        )
    return f"{name} {iid}: {flag.get('why')}"


# ------------------------------------------------------------ the search


def restrictions_text(horizon: int | None, blocklist: list[str]) -> str:
    return (
        (
            f"HARD RULES: use only literature published up to {horizon} inclusive. "
            if horizon is not None
            else "HARD RULES: "
        )
        + f"NEVER consult, cite, or search for these excluded sources: "
        f"{blocklist or '(none listed)'}. Never fabricate a source; a reaction "
        f"with no evidence, or no reaction at all, is an acceptable answer."
    )


def supplied_index(supplied: list[dict] | None) -> dict[str, dict]:
    """The human's staged items by every handle an evidence item may cite
    them with: their `lit_k` id and their source key."""
    index: dict[str, dict] = {}
    for it in supplied or []:
        for handle in (str(it.get("id") or "").strip().lower(), source_key(it)):
            if handle:
                index.setdefault(handle, it)
    return index


def _with_origin(row: dict, index: dict[str, dict]) -> dict:
    """An evidence item that cites one of the human's staged items is that
    item: its identity (source, title, year, url, and the locator when the
    agent gave none) is the human's, and its origin `human`; the agent's
    reading of it for this reaction (`supports`, `quote`, the classification)
    stays the agent's. Any other item was found by the search."""
    from octomod.workflow_modules.knowledge import supplied_literature as _lit

    handles = (str(row.get("source") or "").strip().lower(), source_key(row))
    own = next((index[h] for h in handles if h and h in index), None)
    if own is None:
        row["origin"] = _lit.ORIGIN_RESEARCH
        return row
    for k in ("source", "title", "year", "url"):
        if own.get(k) not in (None, ""):
            row[k] = own[k]
    if not row.get("locator") and own.get("locator"):
        row["locator"] = own["locator"]
    row["origin"] = _lit.ORIGIN_HUMAN
    return row


def fence_items(items, blocklist: list[str], horizon: int | None, index=None):
    """(kept, fenced): the same fence research items pass — a blocklist entry
    is a case-folded substring of source, title or url; the horizon is
    exclusive above. Each kept item carries its origin and its source key."""
    kept, fenced = [], []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = _with_origin({k: it.get(k) for k in ITEM_KEYS}, index or {})
        blob = " ".join(str(row.get(k) or "") for k in ("source", "title", "url"))
        year = row.get("year")
        if any(b.casefold() in blob.casefold() for b in blocklist):
            fenced.append({"item": row, "reason": "blocklist"})
        elif (
            horizon is not None
            and isinstance(year, (int, float))
            and not isinstance(year, bool)
            and year > horizon
        ):
            fenced.append({"item": row, "reason": f"published after {horizon}"})
        else:
            row["source_key"] = source_key(row)
            kept.append(row)
    return kept, fenced


# ------------------------------------------------------------ construction

# what construction is shown of an evidence item: what the source says and
# what it is, never the engine's audit fields
PRIOR_ITEM_KEYS = (
    "id",
    "source",
    "title",
    "year",
    "locator",
    "supports",
    "quote",
    "evidence_kind",
    "context_match",
    "stance",
    "origin",
)


# who proposed an entry: the person (a required reaction), the knowledge
# module's survey, a targeted search inside the run
ORIGIN_HUMAN = "human"
ORIGIN_KNOWLEDGE = "knowledge"
ORIGIN_SEARCH = "search"
# who wrote a model reaction no dossier entry describes: construction (the
# base), the expansions of a discrimination round, an expansion's axes
ORIGIN_CONSTRUCTION = "construction"
ORIGIN_EXPANSION = "expansion"
ORIGIN_REVISION = "revision"
REACTION_ORIGINS = (
    ORIGIN_HUMAN,
    ORIGIN_KNOWLEDGE,
    ORIGIN_SEARCH,
    ORIGIN_CONSTRUCTION,
    ORIGIN_EXPANSION,
    ORIGIN_REVISION,
)
# who asked for a targeted search: construction for its base, the expansions,
# the expansion agent, or the person at the expansion card
REQUESTED_BY_CONSTRUCTION = "construction"
REQUESTED_BY_EXPANSION = "expansion"
REQUESTED_BY_REVISION = "revision"
REQUESTED_BY_HUMAN = "human"


def origin_of(entry: dict) -> str:
    """Who proposed a dossier entry: its own `origin`, else `human` for a
    required one and `knowledge` for the rest."""
    own = str((entry or {}).get("origin") or "").strip()
    if own:
        return own
    return ORIGIN_HUMAN if (entry or {}).get("required") else ORIGIN_KNOWLEDGE


def _prior_item(it: dict) -> dict:
    return {k: it[k] for k in PRIOR_ITEM_KEYS if it.get(k) not in (None, "")}


def _prior_row(r: dict) -> dict:
    """One dossier entry as an agent is shown it: what it is, who proposed it,
    its grade and what earned it, and only the evidence that counts for it
    (an item that does not count is not something to build on or cite)."""
    out = {
        "id": r["id"],
        "equation": r["equation"],
        "modifiers": list(r.get("modifiers") or []),
        "type": r.get("type") or "",
        "description": r.get("description") or "",
        "required": bool(r.get("required")),
        "essential": bool(r.get("essential") or r.get("required")),
        "origin": origin_of(r),
        "grade": r.get("grade"),
        "because": [
            {"id": b.get("id"), "rule": b.get("rule")} for b in r.get("because") or []
        ],
        "evidence": [_prior_item(it) for it in counting_items(r)],
    }
    against = [
        f.get("item")
        for f in r.get("flags") or []
        if isinstance(f, dict) and f.get("flag") == "contested"
    ]
    if against:
        out["contested_by"] = against
    for key in ("requested_by", "answers"):
        if r.get(key) not in (None, "", []):
            out[key] = r[key]
    return out


def prior_reactions(dossier: dict) -> dict:
    """What an agent is shown of the whole dossier: every reaction with its
    origin, its grade, the item(s) that earned it and the rule they
    satisfied, and only the evidence that counts for it."""
    return {
        "reactions": [
            _prior_row(r)
            for r in dossier.get("reactions") or []
            if isinstance(r, dict) and r.get("id")
        ],
        "species": list(dossier.get("species") or []),
        "notes": str(dossier.get("notes") or ""),
    }


def essential_rows(base: dict) -> list[dict]:
    """The base set as construction is shown it (`essential_reactions`): each
    entry in `prior_reactions`' shape."""
    return [_prior_row(r) for r in (base or {}).get("reactions") or []]


BASE_INSTRUCTION = (
    "`essential_reactions` is the BASE you build: the reactions a base model of "
    "this system needs, from the knowledge module that ran before the intent was "
    "frozen and from the searches the engine ran for you. Each entry carries its "
    "`origin` (`human`: the intent requires it; `knowledge`: the module's survey; "
    "`search`: a targeted search that answered a conversion you named missing), "
    "its `grade` (a band from a declared rule table, with the source that earned "
    "it in `because` — an ordinal band, never a probability) and the evidence "
    "that counts for it; `support_floor` says in words what an entry's grade had "
    "to reach to be here. The base is EXACTLY this set: implement every entry, in "
    "a direction its rate law carries, with its species ids verbatim, and add no "
    "conversion the set lacks. Kinetics, modifiers, parameters, initial values "
    "and the glossary are yours. A participant the model holds as a parameter "
    "(a dose, a clamped input) keeps the entry's id as the parameter's id: the "
    "engine then compares the entry without it and records it under "
    "`as_parameter` in the model's annotation. When the model cannot be complete "
    "without a conversion the set lacks, build the best model the set allows and "
    "name each missing conversion in `missing` (`{equation, why}`, species ids "
    "verbatim): the engine searches the literature for it, admits what reaches "
    "the support floor, and asks you again with it. Mark every quantity the "
    "experimental conditions set (a dose, an inhibitor level, a genotype switch) "
    "with `set_per_condition: true` on its entry in `parameters`, in "
    "`network.species` or in the glossary. A parameter value taken from one of "
    '`known_facts` carries `source: "knowledge:<fact id>"`. Where a decision '
    "rests on an entry, cite its evidence ids (`req_1.e1`, `rx_2.e1`) in that "
    "decision's `evidence`. `knowledge_summary` is what is known about this "
    "system, the scope of that knowledge and what is unknown. After you reply, "
    "the engine checks that every entry is implemented and nothing else is "
    "(`model_essential_reactions`), and that every piece of the species graph "
    "holds a required entity, so no part of the model is unobserved "
    "(`model_connected`)."
)

ADVISORY_INSTRUCTION = (
    "`essential_reactions` is what the literature and databases describe for "
    "this system, from the knowledge module that ran before the intent was "
    "frozen: each entry with its `origin` (`human`: the intent requires it; "
    "`knowledge`: the module's survey), its `grade` (a band from a declared rule "
    "table, with the source that earned it in `because` — an ordinal band, never "
    "a probability) and the evidence that counts for it; `support_floor` says in "
    "words what an entry's grade had to reach to be listed. `prior_reactions` "
    "is the whole dossier — every reaction it describes, graded, essential or "
    "not, below the floor or not: the entries outside `essential_reactions` are "
    "candidates you may use where the question needs them. It is all prior "
    "knowledge, not a fence: build the model the question and the data need "
    "from the biology, using these entries where they apply, with their species "
    "ids verbatim where a reaction is taken from one. Implement every `required: "
    "true` entry, in a direction its rate law carries. You may add any reaction "
    "the model needs — a mechanical or observation process (a drift, a "
    "background), one copy of a reaction per population or compartment, a "
    "mechanism nothing here describes: every reaction is annotated afterwards "
    "against these entries, and each one the dossier does not back is shown to "
    "the person with your rationale, so the build report says why each is "
    "there. Kinetics, modifiers, parameters, initial values and the glossary are "
    "yours. A participant the model holds as a parameter (a dose, a clamped "
    "input) keeps the entry's id as the parameter's id. `missing` is not needed: "
    "nothing you add is refused for its support. Mark every quantity the "
    "experimental conditions set (a dose, an inhibitor level, a genotype switch) "
    "with `set_per_condition: true` on its entry in `parameters`, in "
    "`network.species` or in the glossary. A parameter value taken from one of "
    '`known_facts` carries `source: "knowledge:<fact id>"`. Where a decision '
    "rests on an entry, cite its evidence ids (`req_1.e1`, `rx_2.e1`) in that "
    "decision's `evidence`. `knowledge_summary` is what is known about this "
    "system, the scope of that knowledge and what is unknown. After you reply, "
    "the engine checks that every required entry is implemented "
    "(`model_essential_reactions`) and that every piece of the species graph holds "
    "a required entity, so no part of the model is unobserved (`model_connected`)."
)

EXPANSION_GROUNDING_INSTRUCTION = (
    "`prior_reactions` lists the reactions the literature already describes for "
    "this system, as a search found them before the first model was built: each "
    "with its sources and a `grade` the engine decided from them — a band (high, "
    "medium, low, weak, none) from a declared rule table, with the source that "
    "earned it (`because`), never a probability. An axis that adds one of them "
    "cites its evidence ids (`rx_2.e1`) in its `rationale`, and its `origin: "
    "biology` is then backed by a source the person can read. A mechanism nothing "
    "here describes is still admissible, as `origin: residual`: the data decide "
    "whether it stays, not this list. After you reply, the engine annotates every "
    "reaction an axis adds against these entries, and the card shows the person, "
    "per axis, the entry it matches and its grade, or that nothing here describes "
    "it; where an axis takes a reaction from an entry, use its species ids "
    "verbatim, so the annotation can match it."
)

EXPANSION_FLOOR_INSTRUCTION = (
    "`prior_reactions` lists the reactions the literature describes for this "
    "system — the knowledge module's survey, and every reaction a targeted search "
    "of this run admitted (origin `search`) — each with its sources and a `grade` "
    "the engine decided from them: a band (high, medium, low, weak, none) from a "
    "declared rule table, with the source that earned it (`because`), never a "
    "probability. `support_floor` is the floor of the round your axes are fitted "
    "in: an axis whose patch adds a conversion graded below it, or one no entry "
    "describes, is REFUSED from the offer, by name, before the person sees it. "
    "When the axis you would propose needs such a conversion, ask for the search "
    "(`requested_research`, one per expansion round): the knowledge role looks for "
    "it, the engine grades what it finds, and what reaches the floor joins "
    "`prior_reactions` before your axes are judged. An axis that changes a rate "
    "law or a switch adds no conversion and is never refused for the floor; an "
    "axis that removes a required reaction is refused whatever the floor. An axis "
    "that adds an entry cites its evidence ids (`rx_2.e1`) in its `rationale`; "
    "use the entry's species ids verbatim, so the annotation can match it. The "
    "floor decides what may be proposed; the data decide, by the criterion, what "
    "stays."
)

# the advisory mode's: the floor flags what an axis adds, it refuses nothing
EXPANSION_ADVISORY_INSTRUCTION = EXPANSION_GROUNDING_INSTRUCTION + (
    " `support_floor` is the floor of the round your axes are fitted in: an axis "
    "that adds a conversion graded below it, or one no entry describes, is "
    "offered all the same and flagged to the person on the card. An axis that "
    "removes a required reaction is refused."
)


# ------------------------------------------------------------ the annotation


def _sbml_reactions(sbml: str) -> dict[str, dict]:
    """{reaction id: its reactant and product species as written, and its rate
    law as text}. SBML's `reversible` flag is not read — see `rate_directions`
    for what decides a reaction's direction."""
    import libsbml

    m = libsbml.readSBMLFromString(sbml).getModel()
    out = {}
    for i in range(m.getNumReactions()):
        rx = m.getReaction(i)
        law = rx.getKineticLaw()
        out[rx.getId()] = {
            "reactants": {
                rx.getReactant(j).getSpecies() for j in range(rx.getNumReactants())
            },
            "products": {
                rx.getProduct(j).getSpecies() for j in range(rx.getNumProducts())
            },
            "law": (
                libsbml.formulaToL3String(law.getMath())
                if law is not None and law.getMath() is not None
                else "(no rate law)"
            ),
        }
    return out


# the probe's random states, per call; with the one-hot states before them a
# law that can change sign is found at once, and every state is deterministic
RATE_PROBE_STATES = 48


def rate_directions(sbml: str, seed: int = 20260914) -> dict[str, dict]:
    """{reaction id: {"forward": bool, "backward": bool}} — which way each
    reaction's RATE LAW can carry flux, read by evaluating the law as the
    simulator will. Never read from the arrow.

    Antimony's arrow only sets SBML's `reversible` flag (`->` true, `=>`
    false), and the simulator ignores that flag: `A => B; kf*A - kr*B` runs
    B -> A whenever kr*B > kf*A, and `A -> B; kf*A` never runs backwards
    although its flag says it may. The law decides.

    Probed on a fixed set of states: every species at 1, each species alone
    at 1, then random states with some species at exactly 0 — and with every
    free parameter kept at its sign but varied over decades, because a switch
    parameter at 0 in the model as written (a discrimination base's feature
    switch) does not make a reaction structurally absent. A reaction whose law cannot be evaluated at
    a state is read at the others. Deterministic for a seed."""
    import numpy as np

    from octomod.workflow_modules.model.simwrap import RRModel

    m = RRModel(sbml)
    rr = m.rr
    rids = list(rr.model.getReactionIds())
    species = list(m.species_ids) + list(m.boundary_ids)
    assigned = set(m.assignment_ids)
    nominal = {p: float(rr.getValue(p)) for p in m.parameter_ids if p not in assigned}
    rng = np.random.default_rng(seed)

    def scaled(v: float) -> float:
        return (np.sign(v) or 1.0) * (abs(v) or 1.0) * 10 ** rng.uniform(-3, 3)

    states: list[tuple[dict, dict]] = [({s: 1.0 for s in species}, dict(nominal))]
    unit = {p: (np.sign(v) or 1.0) for p, v in nominal.items()}
    states += [({x: float(x == s) for x in species}, unit) for s in species]
    for _ in range(RATE_PROBE_STATES):
        states.append(
            (
                {
                    s: 0.0 if rng.random() < 0.25 else 10 ** rng.uniform(-3, 3)
                    for s in species
                },
                {p: scaled(v) for p, v in nominal.items()},
            )
        )
    out = {r: {"forward": False, "backward": False} for r in rids}
    for values, pars in states:
        for s, v in values.items():
            try:
                rr.setValue(f"[{s}]", float(v))
            except Exception:
                pass  # a rule-determined species keeps what its rule says
        for p, v in pars.items():
            try:
                rr.setValue(p, float(v))
            except Exception:
                pass
        try:
            rates = rr.model.getReactionRates()
        except Exception:
            continue
        for r, v in zip(rids, rates, strict=False):
            if not np.isfinite(v):
                continue
            if v > 1e-12:
                out[r]["forward"] = True
            elif v < -1e-12:
                out[r]["backward"] = True
    return out


def _covers(parsed: dict, reactants: set, products: set) -> bool:
    """Does a dossier entry cover the conversion reactants -> products? One
    way, or either way when the entry is itself reversible."""
    r, p = set(parsed["reactants"]), set(parsed["products"])
    if (r, p) == (set(reactants), set(products)):
        return True
    return bool(parsed.get("reversible")) and (p, r) == (set(reactants), set(products))


def _fmt_sides(reactants: set, products: set) -> str:
    return f"{' + '.join(sorted(reactants))} -> {' + '.join(sorted(products))}".strip()


def _sbml_ids(sbml: str) -> tuple[set[str], set[str]]:
    """(species ids, parameter ids) of an SBML model."""
    import libsbml

    m = libsbml.readSBMLFromString(sbml).getModel()
    species = {m.getSpecies(i).getId() for i in range(m.getNumSpecies())}
    params = {m.getParameter(i).getId() for i in range(m.getNumParameters())}
    return species, params


def _parameter_ids(model_parameters) -> set[str]:
    """The ids of a parameter table (rows with an `id`) or a list of ids."""
    out: set[str] = set()
    for p in model_parameters or []:
        pid = p.get("id") if isinstance(p, dict) else p
        if isinstance(pid, str) and pid:
            out.add(pid)
    return out


def counted_items(entry: dict) -> list[dict]:
    """The evidence items that count for a dossier entry (`counting_items`)."""
    return counting_items(entry)


def _supporting(entry: dict) -> list[dict]:
    """The counting items that support the entry: a contradicting source
    counts, and backs nothing."""
    return [
        it for it in counting_items(entry) if _word(it.get("stance")) != CONTRADICTS
    ]


def _kinds(entry: dict) -> list[str]:
    """The classes of the entry's supporting sources, as they were graded."""
    return sorted(
        {
            _word((it.get("graded_as") or {}).get("evidence_kind"))
            or _word(it.get("evidence_kind"))
            for it in _supporting(entry)
        }
        - {""}
    )


def _grade_rank(entry: dict) -> int:
    """The rank of an entry's grade, `none` for an entry never graded."""
    return band_rank(_grade_of(entry))


def entry_label(entry: dict) -> str:
    """The label a model reaction takes from the dossier entry it matches:
    `user-provided` when the intent requires the entry, else
    `database-supported` when a supporting source of it is a curated
    database, else `literature-supported` when any source supports it, else
    `inferred` — an entry no counting source supports backs nothing."""
    if entry.get("required"):
        return USER_PROVIDED
    if DATABASE_KIND in _kinds(entry):
        return DATABASE_SUPPORTED
    if _supporting(entry):
        return LITERATURE_SUPPORTED
    return INFERRED


def _as_compared(entry: dict, species: set, params: set) -> tuple[dict, list[str]]:
    """The entry's conversion as it is compared with the model's reactions,
    and the participants left out of the comparison: one that is not a species
    of the model but is one of its parameters is held as a parameter (a dose,
    a clamped input) and takes no part in the reaction's sides."""
    p = entry["parsed"]
    held = sorted(
        s
        for s in set(p.get("reactants") or {}) | set(p.get("products") or {})
        if s not in species and s in params
    )
    return (
        {
            "reactants": {
                s: n for s, n in (p.get("reactants") or {}).items() if s not in held
            },
            "products": {
                s: n for s, n in (p.get("products") or {}).items() if s not in held
            },
            "reversible": bool(p.get("reversible")),
        },
        held,
    )


# entries named beside an inferred reaction as what the dossier holds nearby
NEARBY_SHOWN = 3


def _nearby(
    m: dict, entries: list[dict], compared: dict, matched: set[str], used: set[str]
) -> list[dict]:
    """The dossier entries that share a species with a model reaction without
    matching it: those no model reaction uses first (an alternative the model
    did not take), then the most shared species, then the strongest grade."""
    here = set(m["reactants"]) | set(m["products"])
    ranked = []
    for k, e in enumerate(entries):
        if e["id"] in matched:
            continue
        c = compared[e["id"]][0]
        shared = here & (set(c["reactants"]) | set(c["products"]))
        if shared:
            key = (e["id"] in used, -len(shared), _grade_rank(e), k)
            ranked.append((key, e))
    return [
        {"id": e["id"], "equation": e["equation"], "grade": _grade_of(e)}
        for _, e in sorted(ranked, key=lambda t: t[0])[:NEARBY_SHOWN]
    ]


def annotate(dossier: dict, sbml: str, model_parameters=None) -> dict:
    """Every reaction of the model, annotated against the round's dossier —
    the record `reaction_support` at the model's node.

    A reaction is matched in each direction its RATE LAW can carry
    (`rate_directions`, never the arrow) to the dossier entries that cover
    that conversion by reactant and product species sets (`_covers`; a
    participant the model holds as a parameter is left out and recorded in
    `as_parameter`). Each carried direction takes the label of its best
    matched entry (`entry_label`) and that entry's grade, the source that
    earned it and who proposed it (`origin`: human, knowledge, search), with
    every entry the direction implements in `entries`; or `inferred` when
    nothing matches. The reaction's own label is the weakest of its
    directions, so a reversible law over a one-way entry is `inferred` for
    its reverse and as a whole.

    `required_missing` names each required entry no model reaction carries;
    `unused_entries` the entries no model reaction matches."""
    entries = [
        e
        for e in (dossier or {}).get("reactions") or []
        if isinstance(e, dict) and e.get("id") and isinstance(e.get("parsed"), dict)
    ]
    model = _sbml_reactions(sbml)
    species, sbml_params = _sbml_ids(sbml)
    params = sbml_params | _parameter_ids(model_parameters)
    compared = {e["id"]: _as_compared(e, species, params) for e in entries}
    dirs = rate_directions(sbml) if model else {}
    rank = {lab: k for k, lab in enumerate(SUPPORT_LABELS)}
    used: set[str] = set()
    rows = []
    found: dict[str, tuple[dict, set[str]]] = {}
    for rid, m in model.items():
        can = dirs.get(rid) or {}
        if not (can.get("forward") or can.get("backward")):
            # a law the probe could not evaluate at any state is read as written
            can = {"forward": True, "backward": False}
        blocks: dict[str, dict | None] = {}
        matched: set[str] = set()
        held: set[str] = set()
        for d in ("forward", "backward"):
            if not can.get(d):
                blocks[d] = None
                continue
            src, dst = (
                (m["reactants"], m["products"])
                if d == "forward"
                else (m["products"], m["reactants"])
            )
            hits = [e for e in entries if _covers(compared[e["id"]][0], src, dst)]
            if not hits:
                blocks[d] = {"label": INFERRED}
                continue
            # the first of the strongest: required, then database, then
            # literature, then by grade; ties keep the dossier's order
            best = max(hits, key=lambda e: (rank[entry_label(e)], -_grade_rank(e)))
            blocks[d] = {
                "label": entry_label(best),
                "entry_id": best["id"],
                "equation": best["equation"],
                "required": bool(best.get("required")),
                "grade": _grade_of(best),
                "because": list(best.get("because") or []),
                "n_sources": int(best.get("n_sources") or 0),
                "kinds": _kinds(best),
                "origin": origin_of(best),
                "also_matches": [e["id"] for e in hits if e is not best],
                # every entry this direction implements, the best first: who
                # proposed each and its grade
                "entries": [
                    {
                        "id": e["id"],
                        "equation": e["equation"],
                        "origin": origin_of(e),
                        "grade": _grade_of(e),
                    }
                    for e in [best] + [x for x in hits if x is not best]
                ],
            }
            for e in hits:
                matched.add(e["id"])
                held |= set(compared[e["id"]][1])
        used |= matched
        label = min(
            (b["label"] for b in blocks.values() if b is not None), key=rank.__getitem__
        )
        rows.append(
            {
                "reaction_id": rid,
                "reactants": sorted(m["reactants"]),
                "products": sorted(m["products"]),
                "law": m["law"],
                "directions": blocks,
                "label": label,
                "as_parameter": sorted(held),
                "nearby": [],
            }
        )
        found[rid] = (m, matched)
    # what the dossier holds near each inferred reaction, once every
    # reaction's matches are known
    for row in rows:
        if row["label"] == INFERRED:
            m, matched = found[row["reaction_id"]]
            row["nearby"] = _nearby(m, entries, compared, matched, used)
    return {
        "reactions": rows,
        "counts": {
            lab.replace("-", "_"): sum(1 for r in rows if r["label"] == lab)
            for lab in reversed(SUPPORT_LABELS)
        },
        "inferred": [r["reaction_id"] for r in rows if r["label"] == INFERRED],
        "required_missing": [
            {"id": e["id"], "equation": e["equation"]}
            for e in entries
            if e.get("required") and e["id"] not in used
        ],
        "unused_entries": [e["id"] for e in entries if e["id"] not in used],
    }


# ------------------------------------------------ the essential reactions' gate


def _entries_of(block: dict) -> list[str]:
    """The ids of every entry one carried direction implements."""
    if not block or not block.get("entry_id"):
        return []
    listed = [str(x.get("id")) for x in block.get("entries") or [] if x.get("id")]
    return listed or [str(block["entry_id"])] + [
        str(x) for x in block.get("also_matches") or []
    ]


def essential_check(support: dict, base: dict) -> dict:
    """What `model_essential_reactions` reads off a model's annotation against
    the base set (`base_set`, which is also what a model reaction may
    implement): `missing`, each entry of the set no model reaction implements
    in a direction its law carries; `outside`, each carried direction of a
    model reaction that implements no entry of the set — with the entries it
    does match (a non-essential one, one below the floor), when it matches
    any."""
    rows = [e for e in (base or {}).get("reactions") or [] if isinstance(e, dict)]
    ids = {str(e.get("id")) for e in rows}
    unused = {str(x) for x in (support or {}).get("unused_entries") or []}
    missing = [
        {
            "id": str(e.get("id")),
            "equation": e.get("equation"),
            "origin": origin_of(e),
            "grade": _grade_of(e),
            "required": bool(e.get("required")),
        }
        for e in rows
        if str(e.get("id")) in unused
    ]
    outside = []
    for r in (support or {}).get("reactions") or []:
        for way, block in (r.get("directions") or {}).items():
            if block is None:
                continue
            hit = _entries_of(block)
            if set(hit) & ids:
                continue
            outside.append(
                {
                    "reaction_id": r.get("reaction_id"),
                    "direction": way,
                    "sides": reaction_sides(r, backward=way == "backward"),
                    "law": r.get("law"),
                    "matches": hit,
                }
            )
    return {
        "missing": missing,
        "outside": outside,
        "n_base": len(ids),
        "n_reactions": len((support or {}).get("reactions") or []),
    }


def _outside_text(o: dict) -> str:
    way = (
        " (the direction its law runs backwards)"
        if o["direction"] == "backward"
        else ""
    )
    held = (
        f"; it matches {', '.join(o['matches'])} in the dossier, which is not in "
        f"the base"
        if o.get("matches")
        else ""
    )
    return f"{o['reaction_id']} {o['sides']}{way}{held}"


def _blocking(check: dict, mode: str) -> tuple[list[dict], list[dict]]:
    """(missing, outside) as they fail the gate: strict, every entry the model
    lacks and every conversion outside the set; advisory, only a required
    entry the model lacks."""
    missing = list((check or {}).get("missing") or [])
    if mode == ADVISORY:
        return [m for m in missing if m.get("required")], []
    return missing, list((check or {}).get("outside") or [])


def essential_failures(check: dict, mode: str = STRICT) -> list[str]:
    """`model_essential_reactions`'s failures, in the words the redraft dossier
    hands back to construction: one per entry of the set the model lacks, one
    per conversion outside it (advisory: only a required entry it lacks)."""
    missing, outside = _blocking(check, mode)
    out = [
        f"essential reaction {m['id']} ({m['equation']}, origin {m['origin']}) is "
        f"in no model reaction, in any direction its rate law carries — implement "
        f"it with these species ids (a participant the model holds as a parameter "
        f"keeps the entry's id as the parameter's)"
        for m in missing
    ]
    out += [
        f"model reaction {_outside_text(o)} is not in the essential set — name it "
        f"in `missing` (equation, why): the engine searches for it, or build the "
        f"model without it"
        for o in outside
    ]
    return out


def counts_text(support: dict) -> str:
    c = (support or {}).get("counts") or {}
    return (
        f"{c.get('user_provided', 0)} user-provided, "
        f"{c.get('database_supported', 0)} database-supported, "
        f"{c.get('literature_supported', 0)} literature-supported, "
        f"{c.get('inferred', 0)} inferred"
    )


def essential_result(check: dict, support: dict | None = None, mode: str = STRICT):
    """`model_essential_reactions` (T0, blocking): strict, the base implements
    every entry of the essential set, in a direction its rate law carries,
    and no conversion outside it; advisory, it implements every required
    entry, and an essential entry it lacks or a conversion outside the set is
    a finding in the detail, shown to the person, never a failure."""
    from octomod.gates import GateResult

    missing, outside = _blocking(check, mode)
    parts = []
    if missing:
        parts.append(
            "missing: "
            + "; ".join(f"{m['id']} {m['equation']} ({m['origin']})" for m in missing)
        )
    if outside:
        parts.append(
            "outside the essential set: "
            + "; ".join(_outside_text(o) for o in outside)
            + " — name each in `missing`"
        )
    counts = (
        f"{(check or {}).get('n_reactions', 0)} model reaction(s): "
        f"{counts_text(support or {})}"
    )
    if parts:
        detail = " | ".join(parts)
    elif mode == ADVISORY:
        noted = [
            f"{m['id']} {m['equation']} ({band_text(m.get('grade'))})"
            for m in (check or {}).get("missing") or []
        ]
        seen = [_outside_text(o) for o in (check or {}).get("outside") or []]
        detail = (
            "advisory: the base implements every required reaction; "
            + (f"essential not implemented: {'; '.join(noted)}; " if noted else "")
            + (f"outside the essential set: {'; '.join(seen)}; " if seen else "")
            + counts
        )
    else:
        detail = (
            f"the base implements every one of the "
            f"{(check or {}).get('n_base', 0)} essential reaction(s) and nothing "
            f"else; {counts}"
        )
    # the id is spelled out: the module map reads gate ids off GateResult calls
    return GateResult(
        "model_essential_reactions",
        "T0",
        not missing and not outside,
        value={"missing": len(missing), "outside": len(outside)},
        detail=detail,
    )


# a parameter's citation of a fact, as construction is told to write it
FACT_CITATION = re.compile(r"knowledge:\s*([A-Za-z_]\w*)")


def _number(x) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fact_citation_result(parameters, dossier: dict | None):
    """`model_fact_citations` (T1, blocking): every `knowledge:<fact id>` in a
    parameter's `source` names a fact of the dossier. A cited fact with a
    numeric value and a unit that differs from the parameter's nominal passes,
    and the detail names both numbers: a unit conversion is legitimate."""
    import math

    from octomod.gates import GateResult

    facts = {
        str(f["id"]): f
        for f in (dossier or {}).get("facts") or []
        if isinstance(f, dict) and f.get("id")
    }
    missing: list[str] = []
    advisory: list[str] = []
    n = 0
    for p in parameters or []:
        if not isinstance(p, dict):
            continue
        for fid in FACT_CITATION.findall(str(p.get("source") or "")):
            n += 1
            fact = facts.get(fid)
            if fact is None:
                missing.append(
                    f"{p.get('id')} cites knowledge:{fid}, which the dossier does "
                    f"not have"
                )
                continue
            value = _number(fact.get("value"))
            nominal = _number(p.get("nominal_value", p.get("value")))
            if value is None or nominal is None or not fact.get("unit"):
                continue
            if not math.isclose(value, nominal, rel_tol=1e-6):
                advisory.append(
                    f"advisory: {p.get('id')} = {nominal:g} cites knowledge:{fid}, "
                    f"whose value is {value:g} {fact['unit']} — a unit conversion is "
                    f"legitimate; check that it is one"
                )
    if missing:
        detail = "; ".join(missing)
    elif n:
        detail = f"{n} citation(s) of a fact, each a fact of the dossier" + (
            " | " + " | ".join(advisory) if advisory else ""
        )
    else:
        detail = "no parameter cites a fact"
    # the id is spelled out: the module map reads gate ids off GateResult calls
    return GateResult(
        "model_fact_citations",
        "T1",
        not missing,
        value={"citations": n, "missing": len(missing)},
        detail=detail,
        advisory_findings=advisory,
    )


# ------------------------------------------------------------ the cards

# where a card sends the reader for each reaction's matched entry and sources
REPORT_POINTER = "the model report, M1 'Where each reaction comes from'"


def reaction_sides(r: dict, backward: bool = False) -> str:
    """An annotated reaction as `reactants -> products`, or the other way
    round for the direction its law carries backwards."""
    a, b = set(r.get("reactants") or []), set(r.get("products") or [])
    return _fmt_sides(b, a) if backward else _fmt_sides(a, b)


def summary_line(support: dict) -> str:
    n = len((support or {}).get("reactions") or [])
    return f"REACTIONS — {n} in the model: {counts_text(support)}"


def _direction_parts(r: dict) -> list[str]:
    """What the dossier holds for each direction an inferred reaction's law
    carries, one phrase each; [] when it holds nothing for any of them."""
    dirs = {d: b for d, b in (r.get("directions") or {}).items() if b is not None}
    missing = [d for d, b in dirs.items() if b.get("label") == INFERRED]
    held = {d: b for d, b in dirs.items() if b.get("label") != INFERRED}
    if not held and not any(dirs[d].get("entry_id") for d in missing):
        return []
    parts = []
    for d in missing:
        way = reaction_sides(r, backward=d == "backward")
        if dirs[d].get("entry_id"):
            parts.append(
                f"{way} is {dirs[d]['entry_id']}, and none of its sources counts"
            )
        elif d == "backward":
            parts.append(f"the law can go negative, and {way} is not in the dossier")
        else:
            parts.append(f"{way} is not in the dossier")
    parts += [
        f"{reaction_sides(r, backward=d == 'backward')} is {b['entry_id']} "
        f"({b['label']}; {because_text(b.get('grade'), b.get('because'))})"
        for d, b in held.items()
    ]
    return parts


def inferred_line(r: dict) -> str:
    """One inferred reaction as the card puts it to the person: the reaction
    as written, its law, the direction the dossier does not hold, and what it
    holds nearby."""
    head = f"{r['reaction_id']}  {reaction_sides(r)}  law {r['law']}"
    parts = _direction_parts(r)
    text = (
        f"⚑ inferred — {head}: " + "; ".join(parts)
        if parts
        else f"⚑ inferred — nothing in the dossier: {head}"
    )
    near = r.get("nearby") or []
    if near:
        text += "; nearby in the dossier: " + ", ".join(
            f"{x['id']} {x['equation']} ({band_text(x.get('grade'))})" for x in near
        )
    return text


def card_lines(support: dict | None, where: str = REPORT_POINTER) -> list[str]:
    """What a card says about the model's reactions: the counts, one line per
    inferred reaction — what the person is asked about — and where each
    reaction's sources are. Nothing without an annotation."""
    if not support:
        return []
    lines = [summary_line(support)]
    lines += [
        f"  {inferred_line(r)}"
        for r in support.get("reactions") or []
        if r.get("label") == INFERRED
    ]
    lines += [
        f"  ⚑ required, and in no model reaction: {m['id']} {m['equation']}"
        for m in support.get("required_missing") or []
    ]
    lines.append(f"  (each reaction's matched entry and counted sources: {where})")
    return lines


def set_card_lines(supports: dict[str, dict], where: str = REPORT_POINTER) -> list[str]:
    """The same for a candidate set: the counts per candidate, then each
    inferred reaction once, with the candidates that carry it."""
    supports = {cid: s for cid, s in (supports or {}).items() if s}
    if not supports:
        return []
    lines = [
        "REACTIONS per candidate — user-provided / database-supported / "
        "literature-supported / inferred:"
    ]
    flagged: dict[str, list[str]] = {}
    for cid, s in supports.items():
        c = s.get("counts") or {}
        lines.append(
            f"  {cid}: {len(s.get('reactions') or [])} reaction(s) — "
            f"{c.get('user_provided', 0)} / {c.get('database_supported', 0)} / "
            f"{c.get('literature_supported', 0)} / {c.get('inferred', 0)}"
        )
        for r in s.get("reactions") or []:
            if r.get("label") == INFERRED:
                flagged.setdefault(inferred_line(r), []).append(cid)
        for m in s.get("required_missing") or []:
            flagged.setdefault(
                f"⚑ required, and in no model reaction: {m['id']} {m['equation']}", []
            ).append(cid)
    lines += [f"  {text}  [{', '.join(cids)}]" for text, cids in flagged.items()]
    lines.append(f"  (each reaction's matched entry and counted sources: {where})")
    return lines


# ------------------------------------------------------------ the expansion

# the expansion's annotation of its axes, in the round the expansion is asked in
AXIS_SUPPORT_KEY = "expansion_support"
# the annotation of the axes construction declares at S1, beside the round's
# declared space
S1_AXIS_SUPPORT_KEY = "space/axis_support"
# an axis's label when it adds no reaction the base lacks, and when the model
# it builds could not be annotated (the record says why)
NO_NEW_REACTION = "no new reaction"
NOT_ANNOTATED = "not annotated"


def latest_dossier(ctx) -> tuple[int, dict] | None:
    """(round, dossier) of the most recent round, this one or earlier, that
    has a reaction dossier: an expansion makes no search of its own, and a
    round an earlier expansion seeded has none. None when no round has one."""
    from octomod.result import node as _tree

    for k in range(int(ctx.round_idx), -1, -1):
        dossier = (_tree.round_node(ctx.root, k) / DOSSIER_KEY).get(None)
        if dossier:
            return k, dossier
    return None


def dossier_round_of(support: dict | None, own_round: int) -> int:
    """The round whose dossier an annotation was made against: the one it
    names (`dossier_round`), else its own round."""
    k = (support or {}).get("dossier_round")
    try:
        return int(k)
    except (TypeError, ValueError):
        return int(own_round)


def expansion_context(ctx, floor: dict | None = None) -> dict:
    """What the expansion agent is shown of the dossier: `prior_reactions`
    (the round's view, `dossier_of`: the staged reactions and those a search
    admitted) with its instruction, when the run builds on the knowledge
    module; else nothing, so its prompt is what it was. With the floor of the
    round the expansion seeds, `support_floor` says it in words and the
    instruction says what it refuses (`EXPANSION_FLOOR_INSTRUCTION`, strict)
    or flags (`EXPANSION_ADVISORY_INSTRUCTION`, advisory)."""
    if not active(ctx):
        return {}
    view = dossier_of(ctx)
    if not view.get("reactions"):
        return {}
    out = {
        "prior_reactions": prior_reactions(view),
        "grounding_instruction": EXPANSION_GROUNDING_INSTRUCTION,
    }
    if floor:
        band = _floor_band(floor)
        mode = grounding_mode(ctx)
        out["support_floor"] = {
            "band": band,
            "step": floor.get("step"),
            "source": floor.get("source"),
            "words": expansion_floor_words(band, mode=mode),
        }
        out["grounding_instruction"] = (
            EXPANSION_ADVISORY_INSTRUCTION
            if mode == ADVISORY
            else EXPANSION_FLOOR_INSTRUCTION
        )
    return out


def base_reactions(antimony: str) -> tuple[dict[str, dict] | None, str]:
    """({reaction id: its reactant and product species and its law}, "") of a
    model given as Antimony, converted as a draft is; (None, the error) when
    it does not convert."""
    from octomod.gates.build_gates import antimony_to_sbml

    try:
        sbml, err = antimony_to_sbml(antimony or "")
        return (_sbml_reactions(sbml), "") if sbml else (None, err)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _not_annotated(why: str) -> dict:
    return {"reactions": [], "label": NOT_ANNOTATED, "error": why[:400]}


def annotate_axis(
    dossier: dict,
    base_antimony: str,
    base_parameters,
    axis: dict,
    base: dict[str, dict],
) -> dict:
    """One expansion axis against the dossier: `{"reactions": [...], "label":
    ...}` — each reaction its patch adds as `annotate` labels it in the model
    the axis builds, and the weakest of their labels, or `no new reaction`.
    A reaction is new when the base (`base_reactions`) has no reaction of its
    id, or has one with other reactants or products: a `replace_reaction`
    that rewires a base reaction onto other species is a conversion the base
    does not carry, and its row says what it replaces (`replaces`).

    The model is the one the lattice fits (`supermodel.build_structure`: the
    patch applied, the parameters it adds declared), converted as a draft is.
    A patch that does not apply, a model that does not convert and one whose
    reactions cannot be read are each recorded as `not annotated` with the
    reason, never raised: the annotation informs the card, it gates nothing."""
    if not axis.get("on_antimony_patch") or axis.get("on_assembly_patch"):
        return {"reactions": [], "label": NO_NEW_REACTION}
    from octomod.gates.build_gates import antimony_to_sbml
    from octomod.workflow_modules.model import supermodel

    try:
        antimony, parameters, applied = supermodel.build_structure(
            base_antimony, list(base_parameters or []), [axis]
        )
    except Exception as e:
        return _not_annotated(
            f"its patch could not be applied: {type(e).__name__}: {e}"
        )
    if not applied:
        return _not_annotated("its patch does not apply to the base")
    try:
        sbml, err = antimony_to_sbml(antimony)
    except Exception as e:
        sbml, err = None, f"{type(e).__name__}: {e}"
    if not sbml:
        return _not_annotated(f"the patched model does not convert to SBML: {err}")
    try:
        support = annotate(dossier, sbml, parameters)
    except Exception as e:
        return _not_annotated(
            f"the patched model's reactions could not be read: {type(e).__name__}: {e}"
        )
    rank = {lab: k for k, lab in enumerate(SUPPORT_LABELS)}
    new = new_reactions(support, base)
    out = {
        "reactions": new,
        "label": (
            min((r["label"] for r in new), key=rank.__getitem__)
            if new
            else NO_NEW_REACTION
        ),
    }
    lost = required_lost(support, base)
    if lost:
        out["required_lost"] = lost
    return out


def new_reactions(support: dict | None, base: dict[str, dict]) -> list[dict]:
    """The reactions of an annotated model that its base (`base_reactions`)
    does not carry: an id the base lacks, or a kept id whose reactants or
    products moved — a conversion the base does not carry, whose row says what
    it replaces (`replaces`). What a patch or a declared difference ADDS."""
    new = []
    for r in (support or {}).get("reactions") or []:
        was = base.get(r["reaction_id"])
        if was is None:
            new.append(r)
        elif (set(r["reactants"]), set(r["products"])) != (
            set(was["reactants"]),
            set(was["products"]),
        ):
            new.append({**r, "replaces": _fmt_sides(was["reactants"], was["products"])})
    return new


def required_lost(support: dict | None, base: dict[str, dict]) -> list[dict]:
    """The required entries a patched model no longer implements although its
    base does — an entry in the patched model's `required_missing` that some
    base reaction's conversion covers: `{id, equation, reaction_id, sides}`,
    the base reaction named. What a removal axis takes out that only the person
    may take out."""
    out = []
    for m in (support or {}).get("required_missing") or []:
        try:
            parsed = parse_equation(m.get("equation"))
        except EquationError:
            continue
        for rid, was in (base or {}).items():
            if _covers(parsed, set(was["reactants"]), set(was["products"])):
                out.append(
                    {
                        "id": m.get("id"),
                        "equation": m.get("equation"),
                        "reaction_id": rid,
                        "sides": _fmt_sides(was["reactants"], was["products"]),
                    }
                )
                break
    return out


def annotate_axes(
    ctx, axes: list[dict], base_antimony: str, base_parameters, base_id: str
) -> dict | None:
    """Every axis of an expansion offer annotated against the round's dossier
    (`dossier_of`) and recorded at the round's `expansion_support`:
    `{"dossier_round", "base", "axes": {axis id: support}}`, which the card
    reads and the next round's axes carry (`with_support`). None, and nothing
    run or written, when the run does not build on the knowledge module or no
    round has a dossier."""
    if not active(ctx):
        return None
    dossier = dossier_of(ctx)
    if not dossier.get("reactions"):
        return None
    k = int(dossier.get("dossier_round") or 0)
    base, err = base_reactions(base_antimony)
    out: dict[str, dict] = {}
    for a in axes:
        out[str(a.get("id"))] = (
            annotate_axis(dossier, base_antimony, base_parameters, a, base)
            if base is not None
            else _not_annotated(f"the base does not convert to SBML: {err}")
        )
    record = {"dossier_round": k, "base": base_id, "axes": out}
    (ctx.round / AXIS_SUPPORT_KEY).put(record)
    return record


def hold_declared_axes(
    ctx, axes: list[dict], base_antimony: str, base_parameters
) -> tuple[list[dict], list[dict]]:
    """(kept, refused): the axes construction declares at S1, held to the
    variants' floor (`variants_floor`) as a variation's additions are — each
    annotated against the round's dossier (`annotate_axis`) and recorded at
    `S1_AXIS_SUPPORT_KEY` (`{dossier_round, base, floor, axes}`), and an axis
    whose patch adds a conversion graded below that floor, or one no entry
    describes, refused (`floor_refusals`) with `{axis, reactions, floor,
    reason}`. An observation axis and one that adds no conversion are never
    refused. In advisory mode nothing is refused: each such axis is kept and
    its additions recorded under `flagged` (`{axis id: refusals}`), which the
    card prints. Every axis kept, and nothing written, when the run does not
    build on the knowledge module or no round has a dossier."""
    node = ctx.round / S1_AXIS_SUPPORT_KEY
    if not axes or not active(ctx):
        if node.exists():
            node.delete()
        return list(axes or []), []
    view = dossier_of(ctx)
    if not view.get("reactions"):
        return list(axes), []
    vf = variants_floor(ctx)
    base, err = base_reactions(base_antimony)
    support = {
        str(a.get("id")): (
            annotate_axis(view, base_antimony, base_parameters, a, base)
            if base is not None
            else _not_annotated(f"the base does not convert to SBML: {err}")
        )
        for a in axes
    }
    record = {
        "dossier_round": int(view.get("dossier_round") or 0),
        "base": "construction",
        "floor": vf["band"],
        "axes": support,
    }
    base_ids = set(base_set(view, base_floor(ctx))["ids"])
    allowed = admitted_at(
        view, vf["band"], exempt=base_ids | exempt_ids(view, base_floor(ctx))
    )
    advisory = grounding_mode(ctx) == ADVISORY
    kept, refused, flagged = [], [], {}
    for a in axes:
        refs = floor_refusals(
            support[str(a.get("id"))].get("reactions") or [], allowed, vf["band"]
        )
        if refs and advisory:
            flagged[str(a.get("id"))] = refs
        if not refs or advisory:
            kept.append(a)
            continue
        refused.append(
            {
                "axis": a,
                "reactions": refs,
                "floor": vf["band"],
                "reason": declared_axis_refusal_reason(refs, vf["band"]),
            }
        )
    if advisory:
        record["mode"] = ADVISORY
        record["flagged"] = flagged
    node.put(record)
    return kept, refused


def declared_axis_refusal_reason(refusals: list[dict], band) -> str:
    """`adds J9 A -> B — inferred (nothing in the dossier) is below the
    variants' floor low; it can return in an expansion round, when the floor
    has come down`."""
    what = "; ".join(
        f"{refused_reaction_text(r)} — {refused_grade_text(r)} is below the "
        f"variants' floor {band_text(band)}"
        for r in refusals
    )
    return (
        f"adds {what}; it can return in an expansion round, when the floor has "
        f"come down"
    )


def with_support(axis: dict, record: dict | None) -> dict:
    """The axis with its `support` from the offer's record, and without one an
    earlier offer left on it: an annotation describes the base it was made
    against."""
    out = {k: v for k, v in axis.items() if k != "support"}
    s = ((record or {}).get("axes") or {}).get(str(axis.get("id")))
    if s is not None:
        out["support"] = s
    return out


def axis_reaction_text(r: dict) -> str:
    """One reaction an axis adds, as its card line puts it: the reaction, its
    label, and the entry it rests on with that entry's grade and the source
    that earned it, or what the dossier holds and lacks for an inferred one."""
    head = f"{r['reaction_id']} {reaction_sides(r)}" + (
        f" (in place of {r['replaces']})" if r.get("replaces") else ""
    )
    if r.get("label") == INFERRED:
        parts = _direction_parts(r)
        return (
            f"{head} — {INFERRED} ("
            + ("; ".join(parts) if parts else "nothing in the dossier")
            + ")"
        )
    held: list[str] = []
    for b in (r.get("directions") or {}).values():
        if b is None or not b.get("entry_id"):
            continue
        text = f"{b['entry_id']}, {because_text(b.get('grade'), b.get('because'))}"
        if text not in held:
            held.append(text)
    return f"{head} — {r.get('label')} ({'; '.join(held)})"


def axis_line(axis_id: str, support: dict) -> str:
    """`axis <id>: adds J9 A -> B — literature-supported (rx_3, medium —
    <the source that earned it>)`, one line per axis whatever it adds."""
    if support.get("label") == NOT_ANNOTATED:
        return f"axis {axis_id}: {NOT_ANNOTATED} — {support.get('error')}"
    rows = support.get("reactions") or []
    if not rows:
        return f"axis {axis_id}: {NO_NEW_REACTION}"
    return f"axis {axis_id}: adds " + "; ".join(axis_reaction_text(r) for r in rows)


def axis_card_lines(record: dict | None) -> list[str]:
    """The expansion card's block for what each axis adds, from the offer's
    record; nothing without one."""
    axes = (record or {}).get("axes") or {}
    if not axes:
        return []
    held = "flagged below" if record.get("mode") == ADVISORY else "held to"
    lines = [
        f"REACTIONS each axis adds, against the reaction dossier of round "
        f"{record.get('dossier_round')} (each grade is a band from the declared "
        f"rule table, with the source that earned it"
        + (
            f"; {held} the variants' floor {band_text(record['floor'])}"
            if record.get("floor")
            else ""
        )
        + "):"
    ]
    lines += [f"  {axis_line(aid, s)}" for aid, s in axes.items()]
    lines += [
        f"  {below_floor_line(ref, record.get('floor'), f'axis {aid}')}"
        for aid, refs in (record.get("flagged") or {}).items()
        for ref in refs
    ]
    return lines


# ------------------------------------------------------------ the support floor

# the round's floor, beside the round's model space
FLOOR_KEY = "space/floor"
# who set a round's floor: the person, the suggestion taken unchanged, the
# schedule an expansion round lowers it by, or the engine lowering it one band
# after a base failed its essential set twice
FLOOR_SOURCES = ("human", "rule", "schedule", "lowered")
# what a testcase.yaml `grounding:` block may carry
GROUNDING_CASE_KEYS = (
    "mode",
    "skip",
    "why",
    "support_floor",
    "floor_step",
    "decided_by",
    "note",
    "dropped",
    "kept",
)
# the floor a case may declare: a band, `none` (no constraint), or
# `not_applicable` (offline, equivalent to none)
FLOOR_BANDS = GRADE_BANDS
DECIDERS = ("human", "rule")

# the forms of the floor card, as the person writes them
FLOOR_FORMS = {
    "floor": "floor: <band|none>",
    "step": "step: <n>",
    "keep": "keep: <id>, <id>",
    "drop": "drop: <id>, <id>",
}
_FORM_MEANING = {
    "floor": "the support floor; none sets no constraint",
    "step": "bands each expansion round lowers it by",
    "keep": "an unsupported essential kept in the base, tagged inferred",
    "drop": "an essential taken out of the base, a candidate for the variants",
}
TRADE_OFF = (
    "a higher floor buys a literature-informed baseline and slower discovery; "
    "a lower one buys data-driven mechanisms sooner"
)


def _essential(e) -> bool:
    return isinstance(e, dict) and bool(e.get("essential") or e.get("required"))


def _grade_of(e: dict) -> str:
    b = _band_word(e.get("grade"))
    return b if b in GRADE_BANDS else NONE


def suggest_floor(entries, *, mode: str | None = None) -> dict:
    """The SUGGESTED support floor, a rule: the lowest band among the
    supported essential reactions that are not required (the required ones
    are the person's and exempt). An essential with no counting source does
    not pull the suggestion down: it is listed in `unsupported`, a decision
    for the floor card. No supported essential gives `none`; an offline
    survey (`mode`, or every essential `not_applicable`) gives
    `not_applicable`.

    `{"band", "why", "unsupported": [ids], "leaves_at": {band: [ids]}}` —
    `leaves_at` names, for every band above the suggestion, the essentials
    that would leave the base at that floor."""
    ess = [e for e in entries or [] if _essential(e)]
    if _word(mode) == "offline" or (
        ess and all(_grade_of(e) == NOT_APPLICABLE for e in ess)
    ):
        return {
            "band": NOT_APPLICABLE,
            "why": "offline: nothing was searched, so no grade and no floor apply",
            "unsupported": [],
            "leaves_at": {},
        }
    free = [e for e in ess if not e.get("required")]
    supported = [e for e in free if _grade_of(e) not in (NONE, NOT_APPLICABLE)]
    unsupported = [str(e.get("id")) for e in free if _grade_of(e) == NONE]
    if not supported:
        band = NONE
        why = (
            "no essential reaction outside the required ones has a counting "
            "source, so the floor constrains nothing"
        )
    else:
        low = max(supported, key=lambda e: band_rank(_grade_of(e)))
        band = _grade_of(low)
        why = (
            f"{low.get('id')} ({low.get('equation', '?')}) is the lowest-graded "
            f"supported essential reaction: {because_text(band, low.get('because'))}"
        )
    leaves_at = {
        b: [
            str(e.get("id"))
            for e in supported
            if band_rank(_grade_of(e)) > band_rank(b)
        ]
        for b in RULE_BANDS
        if band_rank(b) < band_rank(band)
    }
    return {
        "band": band,
        "why": why,
        "unsupported": unsupported,
        "leaves_at": leaves_at,
    }


def floor_card_lines(
    entries, suggestion: dict, decision: dict | None = None
) -> list[str]:
    """The floor card: every essential reaction with its grade, the source
    that earned it and its origin (the required ones marked), the unsupported
    ones as decisions, the suggestion with its reason, the trade-off in one
    sentence, what leaves the base at each higher band, the forms, and the
    decision when one is recorded."""
    ess = [e for e in entries or [] if _essential(e)]
    band = _band_word((suggestion or {}).get("band")) or NONE
    n_req = sum(1 for e in ess if e.get("required"))
    lines = [
        f"ESSENTIAL REACTIONS — {len(ess)}, {n_req} required (the person's: in "
        f"the base whatever their grade): each with its grade and the source "
        f"that earned it"
    ]
    for e in ess:
        origin = e.get("origin") or ("human" if e.get("required") else "knowledge")
        tag = ("required, " if e.get("required") else "") + f"origin {origin}"
        lines.append(
            f"  {e.get('id')}  {e.get('equation', '?')}  [{tag}]  "
            f"{because_text(e.get('grade'), e.get('because'))}"
        )
        lines += [
            f"      ⚑ {flag_text(f)}"
            for f in e.get("flags") or []
            if isinstance(f, dict) and f.get("flag") != "not_counted"
        ]
    by_id = {str(e.get("id")): e for e in ess}
    unsupported = list((suggestion or {}).get("unsupported") or [])
    if unsupported:
        lines.append(
            "NO SOURCE COUNTS for these essentials — each is a decision: keep it "
            "in the base, tagged inferred (the default on a plain yes: the module "
            "says the model does not work without it), or drop it to a candidate "
            "for the variants:"
        )
        lines += [
            f"  {eid}  {(by_id.get(eid) or {}).get('equation', '?')}"
            for eid in unsupported
        ]
    lines.append(
        f"SUGGESTED FLOOR: {band_text(band)} — {(suggestion or {}).get('why')}"
    )
    if band != NOT_APPLICABLE:
        lines.append(f"TRADE-OFF: {TRADE_OFF}.")
        for b, ids in ((suggestion or {}).get("leaves_at") or {}).items():
            lines.append(
                f"  at floor {b}: "
                + (
                    f"{', '.join(ids)} leave(s) the base"
                    if ids
                    else "no essential leaves the base"
                )
            )
    lines.append(
        "FORMS: "
        + " · ".join(f"{f} ({_FORM_MEANING[k]})" for k, f in FLOOR_FORMS.items())
    )
    if decision:
        floor = decision.get("support_floor", decision.get("band"))
        step = decision.get("floor_step", decision.get("step"))
        who = decision.get("decided_by", decision.get("source"))
        text = f"DECISION: floor {band_text(floor)}, step {step}, decided by {who}"
        if decision.get("dropped"):
            text += f"; dropped {', '.join(map(str, decision['dropped']))}"
        if decision.get("kept"):
            text += f"; kept {', '.join(map(str, decision['kept']))}"
        if decision.get("note"):
            text += f' — "{decision["note"]}"'
        lines.append(text)
    return lines


def _grounding_block(testcase: dict) -> dict | None:
    """testcase.yaml's `grounding:` block, its keys checked by name; None
    when the case has none."""
    block = (testcase or {}).get("grounding")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError(
            f"testcase.yaml's `grounding:` must be a mapping, got "
            f"{type(block).__name__}"
        )
    unknown = sorted(set(map(str, block)) - set(GROUNDING_CASE_KEYS))
    if unknown:
        raise ValueError(
            f"testcase.yaml's `grounding:` carries unknown key(s) {unknown}; "
            f"accepted: {', '.join(GROUNDING_CASE_KEYS)}"
        )
    return block


def skip_declared(testcase: dict) -> str | None:
    """The `why` of `grounding: {skip: true, why: "<benchmark | fixture>"}`,
    the case's declaration that it runs without the knowledge module; None
    when it declares no skip. A skip without a why is refused by name."""
    block = _grounding_block(testcase)
    if not block or "skip" not in block:
        return None
    skip = block.get("skip")
    if not isinstance(skip, bool):
        raise ValueError(f"grounding.skip must be true or false, got {skip!r}")
    if not skip:
        return None
    why = block.get("why")
    if not isinstance(why, str) or not why.strip():
        raise ValueError(
            "grounding.skip is declared without a why — write grounding: {skip: "
            'true, why: "<benchmark | fixture>"}'
        )
    if "support_floor" in block:
        raise ValueError(
            "grounding declares both skip and support_floor — a case that skips "
            "the knowledge module has no floor"
        )
    return why.strip()


def _id_list(value, key: str) -> list[str]:
    if value in (None, ""):
        return []
    raw = [v.strip() for v in value.split(",")] if isinstance(value, str) else value
    if not isinstance(raw, list) or not all(
        isinstance(v, str) and _ID.fullmatch(v.strip()) for v in raw
    ):
        raise ValueError(f"grounding.{key} must be a list of entry ids, got {value!r}")
    return [v.strip() for v in raw if v.strip()]


def read_floor_decision(testcase: dict, spec) -> dict | None:
    """The person's floor decision from testcase.yaml's `grounding:` block,
    validated by name: `{support_floor, floor_step, decided_by, note,
    dropped, kept}` — the floor a band, `none` or `not_applicable`; the step
    a whole number (the spec's `grounding.floor_step` when the case gives
    none); who decided, `human` or `rule` (the suggestion taken unchanged).
    None when the block declares no `support_floor`."""
    block = _grounding_block(testcase)
    if not block or "support_floor" not in block:
        return None
    floor = _band_word(block.get("support_floor"))
    if floor not in FLOOR_BANDS:
        raise ValueError(
            f"grounding.support_floor {block.get('support_floor')!r} is not a "
            f"floor — accepted: {', '.join(FLOOR_BANDS)}"
        )
    step = (
        _count(block["floor_step"], "grounding.floor_step")
        if "floor_step" in block
        else floor_step(spec)
    )
    who = _word(block.get("decided_by"))
    if who not in DECIDERS:
        raise ValueError(
            f"grounding.decided_by {block.get('decided_by')!r} says nobody — "
            f"accepted: {', '.join(DECIDERS)} (the suggestion taken unchanged)"
        )
    note = block.get("note", "")
    if not isinstance(note, str):
        raise ValueError(f"grounding.note must be text, got {note!r}")
    dropped = _id_list(block.get("dropped"), "dropped")
    kept = _id_list(block.get("kept"), "kept")
    both = sorted(set(dropped) & set(kept))
    if both:
        raise ValueError(f"grounding lists {both} as both dropped and kept")
    return {
        "support_floor": floor,
        "floor_step": step,
        "decided_by": who,
        "note": note,
        "dropped": dropped,
        "kept": kept,
    }


def floor_of(ctx) -> dict | None:
    """The round's support floor, `{band, step, source}`: the record at
    `rounds/round_k/space/floor` when one is written, else the case's own
    decision (`read_floor_decision`, round 0's floor). None when the case
    declares no floor."""
    node = ctx.round / FLOOR_KEY
    if node.exists():
        return node.get()
    d = read_floor_decision(ctx.testcase, ctx.spec)
    if d is None:
        return None
    return {
        "band": d["support_floor"],
        "step": d["floor_step"],
        "source": d["decided_by"],
    }


def write_floor(
    ctx, band, step: int, source: str, *, note: str = "", module: str = MODULE
) -> dict:
    """Write the round's floor at `rounds/round_k/space/floor` and ledger it
    as a `floor_set` row. Writing the floor the round already holds changes
    nothing and ledgers nothing, so a resume is silent."""
    b = GRADE_BANDS[band_rank(band)]
    n = _count(step, "the floor step")
    who = _word(source)
    if who not in FLOOR_SOURCES:
        raise ValueError(
            f"a floor's source {source!r} is not one of {', '.join(FLOOR_SOURCES)}"
        )
    record = {"band": b, "step": n, "source": who}
    node = ctx.round / FLOOR_KEY
    if node.exists() and node.get() == record:
        return record
    was = node.get() if node.exists() else None
    sha = node.put(record)
    ctx.ledger.append(
        "floor_set",
        module=module,
        round_idx=ctx.round_idx,
        artifact=node.key,
        sha=sha,
        band=b,
        step=n,
        source=who,
        previous=(was or {}).get("band"),
        note=note
        or f"support floor {band_text(b)}, step {n}, set by {who} for round "
        f"{ctx.round_idx}",
    )
    return record


# ------------------------------------------------ the round's dossier and its base

# what the round's view carries of the staged dossier beside its reactions
VIEW_KEYS = (
    "kind",
    "mode",
    "system",
    "species",
    "facts",
    "grading",
    "notes",
    "horizon",
    "forbidden_sources",
    "suggestion",
)


def staged_dossier(ctx) -> dict | None:
    """The knowledge module's dossier as the run was started with it (the
    record's `input/knowledge/knowledge.json`), or None when the inputs hold
    none or it is not a readable object."""
    from octomod.workflow_modules.knowledge import engine as _kn

    return _kn.staged_dossier(ctx)


def _round_node(ctx, k: int):
    from octomod.result import node as _tree

    return _tree.round_node(ctx.root, k)


def admitted_reactions(ctx) -> list[dict]:
    """Every reaction a targeted search admitted, in this round and the rounds
    before it (`rounds/round_k/knowledge_admitted`), in the order admitted: a
    revision round builds on the base the round it revises was built from."""
    out: list[dict] = []
    seen: set[str] = set()
    for k in range(0, int(ctx.round_idx) + 1):
        for e in (_round_node(ctx, k) / ADMITTED_KEY).get(None) or []:
            if isinstance(e, dict) and e.get("id") and str(e["id"]) not in seen:
                seen.add(str(e["id"]))
                out.append(e)
    return out


def dossier_of(ctx) -> dict:
    """The round's dossier, as construction, the gates and the annotation
    read it. Round 0 copies the staged dossier to
    `rounds/round_0/reaction_evidence` once (a resume finds the copy and
    changes nothing); a later round reads the most recent round that has one
    (`latest_dossier`). The view is that dossier's own keys (`VIEW_KEYS`) with
    `reactions` = its reactions followed by every reaction a targeted search
    admitted (`admitted_reactions`, origin `search`), and `dossier_round`, the
    round the dossier is in. `{}` when the run holds no module output."""
    first = _round_node(ctx, 0) / DOSSIER_KEY
    if not first.exists():
        staged = staged_dossier(ctx)
        if not staged:
            return {}
        sha = first.put(staged)
        rows = [r for r in staged.get("reactions") or [] if isinstance(r, dict)]
        n_ess = sum(1 for r in rows if r.get("essential") or r.get("required"))
        ctx.ledger.append(
            "note",
            module=MODULE,
            round_idx=0,
            artifact=first.key,
            sha=sha,
            note=(
                f"the knowledge module's dossier ({staged.get('mode')}) copied from "
                f"the run's inputs ({STAGED_DOSSIER}) into {first.key}: "
                f"{len(rows)} reaction(s), {n_ess} essential, "
                f"{len(staged.get('facts') or [])} fact(s)"
            ),
        )
    found = latest_dossier(ctx)
    if found is None:
        return {}
    k, dossier = found
    staged_rows = [r for r in dossier.get("reactions") or [] if isinstance(r, dict)]
    have = {str(r.get("id")) for r in staged_rows}
    admitted = [a for a in admitted_reactions(ctx) if str(a.get("id")) not in have]
    view = {key: dossier.get(key) for key in VIEW_KEYS if key in dossier}
    view["reactions"] = staged_rows + admitted
    view["admitted"] = [str(a["id"]) for a in admitted]
    view["dossier_round"] = k
    return view


def base_floor(ctx) -> dict:
    """The round's floor as the base is built from it: `floor_of`'s `{band,
    step, source}` with the person's `kept` and `dropped` ids from the case's
    decision. A round with no floor reads as `none`, no constraint."""
    floor = dict(floor_of(ctx) or {})
    if not floor:
        floor = {"band": NONE, "step": floor_step(ctx.spec), "source": "rule"}
    try:
        d = read_floor_decision(ctx.testcase or {}, ctx.spec) or {}
    except ValueError:
        d = {}
    floor["kept"] = list(d.get("kept") or [])
    floor["dropped"] = list(d.get("dropped") or [])
    return floor


def _floor_band(floor) -> str:
    raw = (
        floor.get("band", floor.get("support_floor"))
        if isinstance(floor, dict)
        else floor
    )
    b = _band_word(raw)
    return b if b in GRADE_BANDS else NONE


def parse_band(text) -> str | None:
    """A band as a person writes it (`Medium`, `not applicable`), in the
    vocabulary's spelling, or None when it is not one."""
    b = _band_word(text)
    return b if b in GRADE_BANDS else None


def floor_band(floor) -> str:
    """The band of a floor given as a record (`{band, …}`), a case decision
    (`{support_floor, …}`) or a bare band; `none` for anything else."""
    return _floor_band(floor)


def admits(grade, floor) -> bool:
    """Does an entry graded `grade` reach the floor? Every entry reaches
    `not_applicable` (offline, no floor); otherwise its band is at or above the
    floor's (`band_rank`), and an entry nobody graded reaches only `none`."""
    band = _floor_band(floor)
    if band == NOT_APPLICABLE:
        return True
    g = _band_word(grade)
    if g not in GRADE_BANDS or g == NOT_APPLICABLE:
        g = NONE
    return band_rank(g) <= band_rank(band)


def base_set(dossier: dict, floor) -> dict:
    """The essential reactions the base is built from, at the round's floor
    (`base_floor`: a dict with `band`, `kept`, `dropped`; a bare band reads as
    that band with no decisions).

    In the base: every required reaction, whatever its grade (the person's);
    every reaction a targeted search for construction admitted (it reached the
    floor it was admitted at — one a search for the expansions or an expansion
    admitted is a reaction they may add, not part of the base); every
    essential one whose grade is at or above the floor
    band, or whose id is in `kept`; an essential with no counting source
    (graded `none`) unless the person dropped it — keeping it, tagged
    inferred, is the floor card's default. Out: an id in `dropped`, and an
    essential graded below the floor. Offline (a `not_applicable` floor, or an
    offline dossier), every essential not dropped is in.

    `{"floor", "reactions": [entries], "ids": [...], "left_out": [{id,
    equation, grade, why}]}`, in dossier order."""
    band = _floor_band(floor)
    kept = (
        set(map(str, (floor or {}).get("kept") or []))
        if isinstance(floor, dict)
        else set()
    )
    dropped = (
        set(map(str, (floor or {}).get("dropped") or []))
        if isinstance(floor, dict)
        else set()
    )
    offline = band == NOT_APPLICABLE or _word((dossier or {}).get("mode")) == "offline"
    admitted = set(map(str, (dossier or {}).get("admitted") or []))
    base: list[dict] = []
    left_out: list[dict] = []
    for e in (dossier or {}).get("reactions") or []:
        if not isinstance(e, dict) or not e.get("id"):
            continue
        eid = str(e["id"])
        if e.get("required"):
            base.append(e)
            continue
        if eid in admitted or e.get("admitted"):
            if requested_by(e) == REQUESTED_BY_CONSTRUCTION:
                base.append(e)
            continue
        if not e.get("essential"):
            continue
        g = _grade_of(e)
        out = {"id": eid, "equation": e.get("equation"), "grade": g}
        if eid in dropped:
            left_out.append({**out, "why": "dropped by the person at the floor card"})
        elif offline or eid in kept or g == NONE or admits(g, band):
            base.append(e)
        else:
            left_out.append(
                {
                    **out,
                    "why": f"graded {band_text(g)}, below the floor {band_text(band)}",
                }
            )
    return {
        "floor": band,
        "reactions": base,
        "ids": [str(e["id"]) for e in base],
        "left_out": left_out,
    }


def admissible_set(dossier: dict, floor) -> dict:
    """What a model reaction of the base may implement: the base set itself —
    a conversion outside it is named in `missing` and searched for."""
    return base_set(dossier, floor)


def floor_words(band) -> str:
    """One sentence on what a floor lets into the base."""
    b = _band_word(band)
    if b == NOT_APPLICABLE:
        return (
            "not applicable: the knowledge module ran offline, nothing was graded, "
            "so every essential reaction is in the base"
        )
    if b == NONE:
        return (
            "none: no constraint — every essential reaction is in the base, "
            "whatever its sources"
        )
    return (
        f"{band_text(b)}: an essential reaction is in the base when its "
        f"strongest qualifying evidence earns {band_text(b)} or better under the "
        f"declared rule table; the required ones are in whatever their grade, an "
        f"essential with no counting source is in unless the person dropped it, "
        f"and a reaction a search finds enters at this floor"
    )


def floor_context(floor) -> dict:
    """The round's floor as construction is shown it: `{band, step, source,
    words}`."""
    f = floor if isinstance(floor, dict) else {"band": floor}
    band = _floor_band(f)
    return {
        "band": band,
        "step": f.get("step"),
        "source": f.get("source"),
        "words": floor_words(band),
    }


def requested_by(entry: dict) -> str:
    """Who asked for the search that found an admitted entry: construction
    (for the base), the expansions, an expansion, or the person at a card."""
    return str((entry or {}).get("requested_by") or REQUESTED_BY_CONSTRUCTION)


def _entry_of_search(row: dict, n: int, question: str, band: str) -> dict:
    """A reaction a search returned, as the admitted list keeps it: essential
    when construction asked for it (it joins the base), a reaction the round
    may add otherwise."""
    out = {
        k: v
        for k, v in row.items()
        if k not in ("admitted", "not_admitted", "duplicates", "answers_unknown")
    }
    who = requested_by(row)
    out.update(
        origin=ORIGIN_SEARCH,
        requested_by=who,
        answers=question,
        search=int(n),
        admitted=True,
        admitted_at=band,
        essential=who == REQUESTED_BY_CONSTRUCTION,
        required=False,
    )
    return out


def _question_text(q: dict) -> str:
    return str(q.get("question") or q.get("equation") or q.get("id") or "")


def admit(ctx, n: int, floor, in_base=()) -> dict:
    """Admit the reactions of the round's search `n` whose grade reaches the
    floor (`admits`) into `rounds/round_k/knowledge_admitted`, each with
    origin `search`, who asked, the question it answers and the search that
    found it. A reaction already admitted stays; one duplicating an entry the
    base already holds (`in_base`) is not admitted twice; one below the floor
    stays in the search record as `not_admitted` with its band. A search the
    battery refused admits nothing. The search's own `admission` block says
    what it admitted at which floor. Returns `{"admitted": [new ids],
    "not_admitted": [{id, equation, band}], "floor"}`."""
    node = ctx.round / SEARCH_KEY / str(n)
    record = node.get(None) or {}
    band = _floor_band(floor)
    have = list((ctx.round / ADMITTED_KEY).get(None) or [])
    have_ids = {str(e.get("id")) for e in have if isinstance(e, dict)}
    base_ids = set(map(str, in_base or ()))
    qs = {
        str(q.get("id")): q
        for q in record.get("questions") or []
        if isinstance(q, dict)
    }
    new: list[str] = []
    below: list[dict] = []
    refused = bool(record.get("battery_failures"))
    for r in record.get("reactions") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        rid = str(r["id"])
        if rid in have_ids:
            continue
        if refused:
            below.append(
                {
                    "id": rid,
                    "equation": r.get("equation"),
                    "band": _grade_of(r),
                    "why": "the reply was refused by its battery",
                }
            )
            continue
        if r.get("duplicates") and str(r["duplicates"]) in base_ids:
            below.append(
                {
                    "id": rid,
                    "equation": r.get("equation"),
                    "band": _grade_of(r),
                    "why": f"already in the base as {r['duplicates']}",
                }
            )
            continue
        if not admits(r.get("grade"), band):
            below.append(
                {
                    "id": rid,
                    "equation": r.get("equation"),
                    "band": _grade_of(r),
                    "why": f"graded {band_text(_grade_of(r))}, below the floor "
                    f"{band_text(band)}",
                }
            )
            continue
        answered = [qs[a] for a in r.get("answers") or [] if a in qs]
        question = "; ".join(_question_text(q) for q in answered) or (
            _question_text((record.get("questions") or [{}])[0])
        )
        have.append(_entry_of_search(r, n, question, band))
        have_ids.add(rid)
        new.append(rid)
    if new:
        (ctx.round / ADMITTED_KEY).put(have)
    admission = {
        "floor": band,
        "admitted": sorted(
            {str(e["id"]) for e in have if isinstance(e, dict) and e.get("search") == n}
        ),
        "not_admitted": below,
    }
    if record and record.get("admission") != admission:
        record["admission"] = admission
        node.put(record)
    return {"admitted": new, "not_admitted": below, "floor": band}


def searches(ctx) -> list[tuple[int, dict]]:
    """(n, record) of every targeted search of this round, in order."""
    group = ctx.round / SEARCH_KEY
    if not group.exists():
        return []
    out = []
    for name in group.children():
        try:
            k = int(name)
        except ValueError:
            continue
        rec = group.child(name).get(None)
        if isinstance(rec, dict):
            out.append((k, rec))
    return sorted(out, key=lambda t: t[0])


def lower_floor(ctx, why: str, *, module: str = "model") -> tuple[str, str] | None:
    """Lower the round's floor one band (`lower_band`, never below none):
    written at `space/floor` with source `lowered` (a `floor_set` row) and
    ledgered as `floor_lowered` (from, to, why). None, and nothing written,
    when the floor cannot go lower."""
    cur = floor_of(ctx) or {"band": NONE, "step": floor_step(ctx.spec)}
    was = _floor_band(cur)
    to = lower_band(was)
    if to == was:
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=ctx.round_idx,
            note=f"the support floor is {band_text(was)} and cannot go lower: {why}",
        )
        return None
    step = cur.get("step")
    step = (
        step
        if isinstance(step, int) and not isinstance(step, bool)
        else floor_step(ctx.spec)
    )
    write_floor(
        ctx,
        to,
        step,
        "lowered",
        note=f"support floor lowered from {band_text(was)} to {band_text(to)}: {why}",
        module=module,
    )
    ctx.ledger.append(
        "floor_lowered",
        module=module,
        round_idx=ctx.round_idx,
        artifact=(ctx.round / FLOOR_KEY).key,
        why=why,
        note=f"support floor lowered one band, {band_text(was)} -> {band_text(to)}: {why}",
        **{"from": was, "to": to},
    )
    return was, to


def floor_history(ctx) -> list[dict]:
    """Every floor this round was given, in order, from its `floor_set` rows:
    `{band, source, note}`; the round's current floor alone when no row names
    it (a floor carried in from the case)."""
    rows = [
        {"band": e.get("band"), "source": e.get("source"), "note": e.get("note")}
        for e in ctx.ledger.entries()
        if e.get("event") == "floor_set" and e.get("round") == ctx.round_idx
    ]
    if rows:
        return rows
    cur = floor_of(ctx)
    return (
        [{"band": cur.get("band"), "source": cur.get("source"), "note": ""}]
        if cur
        else []
    )


def search_card_lines(ctx) -> list[str]:
    """What a card says about the round's floor and its targeted searches: the
    floor's history, then each search with its questions, what it found and
    what it admitted — a search that admitted nothing says so. Nothing when
    the round searched nothing and its floor never moved."""
    hist = floor_history(ctx)
    found = searches(ctx)
    if not found and len(hist) <= 1:
        return []
    lines = [
        "SUPPORT FLOOR this round: "
        + " -> ".join(f"{band_text(h.get('band'))} ({h.get('source')})" for h in hist)
    ]
    for n, rec in found:
        qs = [q for q in rec.get("questions") or [] if isinstance(q, dict)]
        adm = rec.get("admission") or {}
        rows = [r for r in rec.get("reactions") or [] if isinstance(r, dict)]
        head = (
            f"  search {n} ({rec.get('mode')}, asked by {rec.get('requested_by')}): "
            f"{len(rows)} reaction(s) found, "
        )
        if rec.get("battery_failures"):
            head += "the reply was refused by its battery — nothing admitted"
        elif adm.get("admitted"):
            head += (
                f"{len(adm['admitted'])} admitted at floor "
                f"{band_text(adm.get('floor'))}: {', '.join(adm['admitted'])}"
            )
        else:
            head += f"nothing admitted at floor {band_text(adm.get('floor'))}"
        lines.append(head)
        lines += [f"    Q {q.get('id')}: {_question_text(q)[:200]}" for q in qs]
        by_id = {str(r.get("id")): r for r in rows}
        for rid in adm.get("admitted") or []:
            r = by_id.get(rid) or {}
            lines.append(
                f"    admitted {rid} {r.get('equation')} — "
                f"{because_text(r.get('grade'), r.get('because'))}"
            )
        for b in adm.get("not_admitted") or []:
            lines.append(
                f"    not admitted {b.get('id')} {b.get('equation')} — {b.get('why')}"
            )
    return lines


# ------------------------------------------------ the floor on what a round adds

# the round's record of the axes an expansion offer refused for the floor
AXIS_REFUSED_KEY = "axis_refused"


def exempt_ids(dossier: dict | None, floor=None) -> set[str]:
    """The entries no floor holds back from a reaction a round adds: every
    required one (the person's) and every essential the person dropped from
    the base to a candidate for the variants (`dropped` of `base_floor`)."""
    out = {
        str(e.get("id"))
        for e in (dossier or {}).get("reactions") or []
        if isinstance(e, dict) and e.get("id") and e.get("required")
    }
    if isinstance(floor, dict):
        out |= set(map(str, floor.get("dropped") or []))
    return out


def admitted_at(dossier: dict | None, band, exempt=()) -> set[str]:
    """The ids of the dossier entries a reaction a round adds may implement at
    the floor `band`: every entry whose grade reaches it (`admits`), and every
    id in `exempt`."""
    ids = set(map(str, exempt or ()))
    for e in (dossier or {}).get("reactions") or []:
        if isinstance(e, dict) and e.get("id") and admits(e.get("grade"), band):
            ids.add(str(e["id"]))
    return ids


def floor_refusals(rows, allowed, band) -> list[dict]:
    """Each reaction of `rows` (annotated reactions a round adds) with a
    direction its rate law carries that implements no entry in `allowed`:
    `{reaction_id, sides, direction, band, entry_id, equation}` for the
    weakest such direction — `band` the grade of the entry it matches best,
    `none` with no `entry_id` when it matches nothing (an inferred addition,
    below any floor but `none`). Nothing is refused at a floor of `none` or
    `not_applicable`."""
    if _floor_band(band) in (NONE, NOT_APPLICABLE):
        return []
    allowed = set(map(str, allowed or ()))
    out = []
    for r in rows or []:
        worst = None
        for way, block in (r.get("directions") or {}).items():
            if block is None or set(_entries_of(block)) & allowed:
                continue
            g = _band_word(block.get("grade")) if block.get("entry_id") else NONE
            g = g if g in GRADE_BANDS else NONE
            here = {
                "direction": way,
                "band": g,
                "entry_id": block.get("entry_id"),
                "equation": block.get("equation"),
            }
            if worst is None or band_rank(g) > band_rank(worst["band"]):
                worst = here
        if worst is None:
            continue
        row = {
            "reaction_id": r.get("reaction_id"),
            "sides": reaction_sides(r, backward=worst["direction"] == "backward"),
            **worst,
        }
        if r.get("replaces"):
            row["replaces"] = r["replaces"]
        out.append(row)
    return out


def refused_reaction_text(ref: dict) -> str:
    """`J9 A -> B`, and what it replaces when it rewires a base reaction."""
    return f"{ref.get('reaction_id')} {ref.get('sides')}" + (
        f" (in place of {ref['replaces']})" if ref.get("replaces") else ""
    )


def refused_grade_text(ref: dict) -> str:
    """`low (rx_7)`, or `inferred (nothing in the dossier)`."""
    if ref.get("entry_id"):
        return f"{band_text(ref.get('band'))} ({ref['entry_id']})"
    return f"{INFERRED} (nothing in the dossier)"


def axis_refusal_line(axis_id: str, refusals: list[dict], band) -> str:
    """`axis <id>: adds J9 A -> B — low (rx_7) is below the floor medium; a
    search may raise it`."""
    what = "; ".join(
        f"{refused_reaction_text(r)} — {refused_grade_text(r)} is below the floor "
        f"{band_text(band)}"
        for r in refusals
    )
    return f"axis {axis_id}: adds {what}; a search may raise it"


def below_floor_line(ref: dict, band, owner: str = "") -> str:
    """`⚑ below the floor medium: J9 A -> B — low (rx_7)`: what advisory mode
    shows the person where strict mode refuses; `owner` names the axis or
    variation that adds it."""
    text = (
        f"⚑ below the floor {band_text(band)}: {refused_reaction_text(ref)} — "
        f"{refused_grade_text(ref)}"
    )
    return f"{text} ({owner})" if owner else text


def model_below_floor(support: dict | None, dossier: dict | None, floor) -> list:
    """Each reaction of a model's annotation that implements a dossier entry
    graded below the base's `floor` and nothing at it (`floor_refusals`
    against the base set and the entries the floor admits): what advisory
    mode flags on the scope card beside the inferred reactions, which have
    their own lines."""
    band = _floor_band(floor)
    allowed = admitted_at(
        dossier,
        band,
        exempt=set(base_set(dossier or {}, floor)["ids"]) | exempt_ids(dossier, floor),
    )
    return [
        r
        for r in floor_refusals((support or {}).get("reactions") or [], allowed, band)
        if r.get("entry_id")
    ]


def variant_refusal_reason(refusals: list[dict], band) -> str:
    """The expansions gate's refusal of one variation, by name: `below the
    variants' floor medium: J9 A -> B, graded low (rx_7) — a search may raise
    its support`."""
    what = "; ".join(
        f"{refused_reaction_text(r)}, "
        + (
            f"graded {refused_grade_text(r)}"
            if r.get("entry_id")
            else refused_grade_text(r)
        )
        for r in refusals
    )
    return (
        f"below the variants' floor {band_text(band)}: {what} — a search may raise "
        f"its support"
    )


def variants_floor(ctx) -> dict:
    """The floor a discrimination round's expansions add a reaction at: the
    base's floor (`base_floor`) lowered by `grounding.variants_offset`
    (`lower_band`, never below none; `not_applicable` stays) — `{band, base,
    offset, dropped, words}`."""
    base = base_floor(ctx)
    was = _floor_band(base)
    off = variants_offset(ctx.spec)
    band = lower_band(was, off)
    return {
        "band": band,
        "base": was,
        "offset": off,
        "dropped": list(base.get("dropped") or []),
        "words": variants_floor_words(band, was, off, mode=grounding_mode(ctx)),
    }


def variants_floor_words(
    band, base=None, offset: int | None = None, *, mode: str = STRICT
) -> str:
    """One sentence on what the variants' floor lets a variation add."""
    b = _floor_band(band)
    how = (
        f" (the base's floor {band_text(base)} lowered by {offset} band(s))"
        if base is not None and offset is not None
        else ""
    )
    if mode == ADVISORY and b not in (NONE, NOT_APPLICABLE):
        return (
            f"{band_text(b)}{how}: a variation may add any conversion; one the "
            f"dossier describes below {band_text(b)}, or one no entry describes, is "
            f"kept and flagged to the person on the card"
        )
    if b == NOT_APPLICABLE:
        return (
            "not applicable: the knowledge module ran offline, nothing was graded, "
            "so a variation may add any conversion"
        )
    if b == NONE:
        return (
            f"none{how}: no constraint — a variation may add any conversion, "
            f"described in the dossier or not"
        )
    return (
        f"{band_text(b)}{how}: a variation may add a conversion the dossier "
        f"describes at {band_text(b)} or better under the declared rule table (a "
        f"required reaction whatever its grade); one graded below it, or one no "
        f"entry describes, is refused and its candidate dropped — name it in "
        f"`missing` and the engine searches for it, once this round, before the "
        f"refusal"
    )


VARIATIONS_INSTRUCTION = (
    "`essential_reactions` is the base's essential set, which `base_model` "
    "implements; `prior_reactions` is every reaction the knowledge module and the "
    "round's searches describe for this system, each with its `origin` and its "
    "`grade` (a band from a declared rule table, with the source that earned it "
    "— never a probability). A candidate keeps every reaction of the base and "
    "may ADD a conversion: `variants_floor` says in words which grades may be "
    "added. Take an added conversion from `prior_reactions`, with its species ids "
    "verbatim, so the engine can match it; a conversion you need that no entry at "
    "that floor describes goes in `missing` (`{equation, why}`, species ids "
    "verbatim): the engine runs one targeted literature search for this round's "
    "`missing`, admits what reaches the floor, and then refuses — dropping its "
    "candidate from the set, named on the card — every variation that still adds "
    "a conversion below the floor. A candidate that differs only in its rate laws "
    "or switches adds no conversion and is never refused for the floor."
)

VARIATIONS_ADVISORY_INSTRUCTION = (
    "`essential_reactions` is the base's essential set, what the literature "
    "describes for it; `prior_reactions` is every reaction the knowledge module "
    "describes for this system, each with its `origin` and its `grade` (a band "
    "from a declared rule table, with the source that earned it — never a "
    "probability). Both are prior knowledge, not a fence. A candidate keeps every "
    "reaction of the base and may ADD any conversion the hypothesis needs; where "
    "it takes one from `prior_reactions`, use its species ids verbatim, so the "
    "engine can match it. Every addition is annotated, and one graded below "
    "`variants_floor`, or one no entry describes, is kept and flagged to the "
    "person on the card with your rationale; `missing` is not needed."
)


# ------------------------------------------------ the floor an expansion seeds


def step_of(floor, spec) -> int:
    """The bands a floor record's schedule lowers by: its own `step` (a
    person's `step:` is recorded there for the rounds after), else
    `grounding.floor_step`."""
    step = (floor or {}).get("step") if isinstance(floor, dict) else None
    if isinstance(step, int) and not isinstance(step, bool) and step >= 0:
        return step
    return floor_step(spec)


def recorded_floor(ctx, k: int | None = None) -> dict | None:
    """The floor round `k` (default: this round) holds: its `space/floor`,
    else the most recent earlier round's, else the case's own decision
    (round 0's) — `{band, step, source}`; None when the run records none."""
    k = int(ctx.round_idx if k is None else k)
    for j in range(k, -1, -1):
        rec = (_round_node(ctx, j) / FLOOR_KEY).get(None)
        if isinstance(rec, dict) and rec.get("band"):
            return rec
    try:
        d = read_floor_decision(ctx.testcase or {}, ctx.spec)
    except ValueError:
        return None
    if d is None:
        return None
    return {
        "band": d["support_floor"],
        "step": d["floor_step"],
        "source": d["decided_by"],
    }


def scheduled_floor(ctx) -> dict | None:
    """The floor the schedule gives the round an expansion of this round
    seeds: this round's floor (`recorded_floor`) lowered by its step
    (`lower_band`, never below none; `not_applicable` stays) — `{band, step,
    from}`; None when the run records no floor."""
    cur = recorded_floor(ctx)
    if cur is None:
        return None
    step = step_of(cur, ctx.spec)
    was = _floor_band(cur)
    return {"band": lower_band(was, step), "step": step, "from": was}


def next_floor(ctx) -> dict | None:
    """The floor recorded for the round an expansion of this round seeds
    (`rounds/round_{k+1}/space/floor`), or None."""
    rec = (_round_node(ctx, int(ctx.round_idx) + 1) / FLOOR_KEY).get(None)
    return rec if isinstance(rec, dict) and rec.get("band") else None


def write_next_floor(ctx, band, step: int, source: str, *, note: str = "") -> dict:
    """`write_floor` for the round an expansion of this round seeds, from this
    round's context: the record at `rounds/round_{k+1}/space/floor` and its
    `floor_set` row, which names round k + 1."""
    previous = ctx.round_idx
    ctx.round_idx = int(previous) + 1
    try:
        return write_floor(ctx, band, step, source, note=note, module="revision")
    finally:
        ctx.round_idx = previous


def floor_from_text(floor: dict | None) -> str:
    """How a round's floor was set, in words: `medium (the schedule: high
    lowered by 1)`, `low (the person's)`."""
    if not floor:
        return "no floor"
    b = band_text(floor.get("band"))
    src = floor.get("source")
    if src == "schedule":
        return (
            f"{b} (the schedule: {band_text(floor.get('from'))} lowered by "
            f"{floor.get('step')})"
            if floor.get("from")
            else f"{b} (the schedule)"
        )
    if src == "human":
        return f"{b} (the person's)"
    if src == "rule":
        return f"{b} (the suggestion, taken unchanged)"
    if src == "lowered":
        return f"{b} (lowered by the engine after a base failed twice)"
    return b


def expansion_floor_words(band, *, mode: str = STRICT) -> str:
    """One sentence on what an expansion round's floor lets an axis add."""
    b = _floor_band(band)
    if mode == ADVISORY and b not in (NONE, NOT_APPLICABLE):
        return (
            f"{band_text(b)}: an axis may add any conversion; one the dossier "
            f"describes below {band_text(b)}, or one no entry describes, is offered "
            f"and flagged to the person on the card"
        )
    if b == NOT_APPLICABLE:
        return (
            "not applicable: the knowledge module ran offline, nothing was graded, "
            "so an axis may add any conversion"
        )
    if b == NONE:
        return (
            "none: no constraint — an axis may add any conversion, described in the "
            "dossier or not"
        )
    return (
        f"{band_text(b)}: an axis may add a conversion the dossier describes at "
        f"{band_text(b)} or better under the declared rule table (a required "
        f"reaction whatever its grade); an axis that adds one graded below it, or "
        f"one no entry describes, is refused from the offer — unless the search you "
        f"may request (`requested_research`) finds it at this floor first"
    )


# ------------------------------------------------ a required reaction is the person's


def axis_required_lost(ctx, base_antimony: str, parameter_ids, axis: dict) -> list:
    """The required entries an axis's patch takes out of a base that implements
    them (`required_lost`, read off the patched model's annotation as
    `annotate_axis` makes it); [] when the run does not build on the knowledge
    module, the dossier holds no required entry, or the axis touches no
    reaction."""
    if not active(ctx) or not axis.get("on_antimony_patch"):
        return []
    view = dossier_of(ctx)
    if not any(
        isinstance(e, dict) and e.get("required") for e in view.get("reactions") or []
    ):
        return []
    base, _err = base_reactions(base_antimony)
    if base is None:
        return []
    params = [{"id": str(p)} for p in parameter_ids or ()]
    got = annotate_axis(view, base_antimony, params, axis, base)
    return list(got.get("required_lost") or [])


def required_removal_reason(lost: list[dict]) -> str:
    """Why an axis that removes a required reaction is refused, in the words
    of the card and the ledger."""
    what = "; ".join(
        f"{x.get('reaction_id')} ({x.get('sides')}), which implements the required "
        f"reaction {x.get('id')} {x.get('equation')}"
        for x in lost
    )
    return (
        f"it removes {what} — a required reaction is the person's: it leaves the "
        f"model only when the intent's required_reactions is edited, and a new "
        f"run is started from the edited folder"
    )
