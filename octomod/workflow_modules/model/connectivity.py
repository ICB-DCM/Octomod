"""Whether the data sees every piece of a model, and whether what the conditions vary reaches it.

The species graph has one node per state species. Two species are neighbours
when they appear in the same reaction as reactant, product, modifier or a
symbol its rate law reads; a rate rule and an event join the species they
assign to the species their math reads, because they are dynamics too. The
rate law decides membership, not the SBML modifier list: Antimony can leave a
species the law reads out of that list.

An assignment rule is a definition, not dynamics: a quantity it defines is
read as what its rule reads, wherever it is read (a law that reads
`free_E := E_tot - ES` reads ES). A quantity an assignment rule defines, a
species or a parameter, is therefore no node of its own, and as an anchor it
stands for the state species its rule reads. So a rule never joins two
pieces, whichever way its variable is declared.

The directed relation says which species a species can MOVE. A reaction's
rate moves every species the reaction changes (net stoichiometry not zero),
so every species its law reads, and every declared modifier, moves both its
reactants and its products; a reactant moves the products even when the law
does not read it (a constant flux still converts it). A law that reads its
own product (a reversible law, product inhibition) therefore carries the
product back to the reactants, read from the law as written, never from
SBML's `reversible` flag. A rate rule or an event moves the species it
assigns. An input that is a parameter enters through the species whose rate
of change reads it (`input_species`).

The rule (`problems`): no piece of the model is unobserved — every connected
component of the graph holds at least one anchor, because a piece no anchor
sees has parameters the data cannot inform — and, when the conditions vary
something, every varied quantity reaches at least one anchor. Several pieces
pass when each is observed (a signalling cascade and a readout drift summed
into one count). At S1 the anchors are the species matched to the required
entities; at assembly they are the species the observables read. Cheap and
deterministic: no simulation, no fitted value.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from octomod.gates import GateResult

# an identifier in a PEtab formula; intersected with the model's own ids, so
# a function name or a placeholder never becomes a reference
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# names listed in one sentence before the rest are counted
_SHOW = 8


@dataclass(frozen=True)
class _Parts:
    """The parts of an SBML model the graph is built from, parsed once."""

    species: tuple[str, ...]  # every species, in model order
    symbols: frozenset[str]  # every id a formula can name
    reactions: dict = field(default_factory=dict)  # rid -> dict
    # variable -> the ids its math reads, per kind of definition
    assignment: dict = field(default_factory=dict)
    rate: dict = field(default_factory=dict)
    initial: dict = field(default_factory=dict)
    # (the ids trigger, delay and assignments read, the variables assigned)
    events: tuple = ()

    @property
    def derived(self) -> set[str]:
        """The species an assignment rule defines: values, not states."""
        return set(self.species) & set(self.assignment)

    @property
    def states(self) -> tuple[str, ...]:
        derived = self.derived
        return tuple(s for s in self.species if s not in derived)


def _math_names(math) -> set[str]:
    """Every name an AST reads (a function call's name is not a reference)."""
    import libsbml

    out: set[str] = set()
    if math is None:
        return out
    stack = [math]
    while stack:
        node = stack.pop()
        if node.getType() == libsbml.AST_NAME:
            out.add(node.getName())
        for i in range(node.getNumChildren()):
            stack.append(node.getChild(i))
    return out


@functools.lru_cache(maxsize=16)
def _parts(sbml: str) -> _Parts:
    import libsbml

    doc = libsbml.readSBMLFromString(sbml)
    model = doc.getModel() if doc is not None else None
    if model is None:
        raise ValueError("the SBML cannot be read: it holds no model")
    species = tuple(s.getId() for s in model.getListOfSpecies())
    symbols = set(species)
    symbols |= {p.getId() for p in model.getListOfParameters()}
    symbols |= {c.getId() for c in model.getListOfCompartments()}

    def _stoich(ref) -> float:
        return float(ref.getStoichiometry()) if ref.isSetStoichiometry() else 1.0

    reactions: dict[str, dict] = {}
    for rx in model.getListOfReactions():
        symbols.add(rx.getId())
        net: dict[str, float] = {}
        for ref in rx.getListOfReactants():
            net[ref.getSpecies()] = net.get(ref.getSpecies(), 0.0) - _stoich(ref)
        for ref in rx.getListOfProducts():
            net[ref.getSpecies()] = net.get(ref.getSpecies(), 0.0) + _stoich(ref)
        law = rx.getKineticLaw()
        names: set[str] = set()
        if law is not None:
            names = _math_names(law.getMath())
            # a local parameter shadows a global id of the same name
            local = {q.getId() for q in law.getListOfParameters()}
            local |= {q.getId() for q in law.getListOfLocalParameters()}
            names -= local
        reactions[rx.getId()] = {
            "reactants": {r.getSpecies() for r in rx.getListOfReactants()},
            "products": {r.getSpecies() for r in rx.getListOfProducts()},
            "modifiers": {m.getSpecies() for m in rx.getListOfModifiers()},
            "law_names": names,
            "changed": {s for s, v in net.items() if abs(v) > 1e-12},
        }
    assignment: dict[str, set[str]] = {}
    rate: dict[str, set[str]] = {}
    for rule in model.getListOfRules():
        if rule.isAssignment():
            assignment[rule.getVariable()] = _math_names(rule.getMath())
        elif rule.isRate():
            rate[rule.getVariable()] = _math_names(rule.getMath())
    initial = {
        ia.getSymbol(): _math_names(ia.getMath())
        for ia in model.getListOfInitialAssignments()
    }
    events = []
    for ev in model.getListOfEvents():
        reads: set[str] = set()
        if ev.isSetTrigger():
            reads |= _math_names(ev.getTrigger().getMath())
        if ev.isSetDelay():
            reads |= _math_names(ev.getDelay().getMath())
        assigned = set()
        for ea in ev.getListOfEventAssignments():
            reads |= _math_names(ea.getMath())
            assigned.add(ea.getVariable())
        events.append((frozenset(reads), frozenset(assigned)))
    return _Parts(
        species=species,
        symbols=frozenset(symbols),
        reactions=reactions,
        assignment=assignment,
        rate=rate,
        initial=initial,
        events=tuple(events),
    )


def _through_rules(p: _Parts, names: set[str]) -> set[str]:
    """`names` and everything their definitions read: an assignment-rule
    variable (a parameter or a species) opens into what its rule reads, and
    so does a parameter a rate rule drives. A state species stays itself."""
    states = set(p.states)
    out: set[str] = set()
    stack = list(names)
    while stack:
        n = stack.pop()
        if n in out:
            continue
        out.add(n)
        if n in states:
            continue
        stack.extend(p.assignment.get(n, ()))
        if n not in p.species:
            stack.extend(p.rate.get(n, ()))
    return out


def species_graph(sbml: str) -> dict:
    """The species graph of an SBML model.

    {"species": [state species, in model order], "edges": {species:
    neighbours}, "directed": {species: the species it can move}, "reactions":
    {rid: {"reactants", "products", "modifiers", "law_refs"}}, "derived":
    {species an assignment rule defines: the state species it reads}}.
    `law_refs` are the species the rate law reads, through the model's
    assignment rules. A species with no reaction, rate rule or event is a
    node with no edges."""
    p = _parts(sbml)
    states = set(p.states)
    edges: dict[str, set[str]] = {s: set() for s in p.states}
    directed: dict[str, set[str]] = {s: set() for s in p.states}

    def _join(group: set[str]) -> None:
        for a in group:
            edges[a] |= group - {a}

    def _move(sources: set[str], targets: set[str]) -> None:
        for s in sources:
            directed[s] |= targets - {s}

    reactions = {}
    for rid, rx in p.reactions.items():
        law_refs = _through_rules(p, rx["law_names"]) & states
        reactants = rx["reactants"] & states
        products = rx["products"] & states
        modifiers = _through_rules(p, rx["modifiers"]) & states
        reactions[rid] = {
            "reactants": set(reactants),
            "products": set(products),
            "modifiers": set(modifiers),
            "law_refs": set(law_refs),
        }
        _join(reactants | products | modifiers | law_refs)
        changed = rx["changed"] & states
        _move(reactants | modifiers | law_refs, products & changed)
        _move(modifiers | law_refs, reactants & changed)
    for var, reads in p.rate.items():
        if var in states:
            refs = _through_rules(p, set(reads)) & states
            _join(refs | {var})
            _move(refs, {var})
    for reads, assigned in p.events:
        refs = _through_rules(p, set(reads)) & states
        for var in assigned & states:
            _join(refs | {var})
            _move(refs, {var})
    derived = {
        d: _through_rules(p, set(p.assignment[d])) & states
        for d in p.species
        if d in p.derived
    }
    return {
        "species": list(p.states),
        "edges": edges,
        "directed": directed,
        "reactions": reactions,
        "derived": derived,
    }


def components(graph: dict) -> list[set[str]]:
    """The connected components of the species graph, largest first (ties by
    their first id, so the order is the same on every run)."""
    edges = graph["edges"]
    seen: set[str] = set()
    out: list[set[str]] = []
    for s in graph["species"]:
        if s in seen:
            continue
        comp = {s}
        stack = [s]
        while stack:
            for n in edges.get(stack.pop(), ()):
                if n not in comp:
                    comp.add(n)
                    stack.append(n)
        seen |= comp
        out.append(comp)
    return sorted(out, key=lambda c: (-len(c), min(c)))


def _downstream(graph: dict, source: str) -> set[str]:
    """Every species `source` reaches along the directed relation, itself included."""
    directed = graph["directed"]
    if source not in directed:
        return set()
    out = {source}
    stack = [source]
    while stack:
        for n in directed.get(stack.pop(), ()):
            if n not in out:
                out.add(n)
                stack.append(n)
    return out


def reaches(graph: dict, sources: set[str], targets: set[str]) -> dict[str, set[str]]:
    """For each source species, the targets it reaches along the directed
    relation. A source that is itself a target reaches it; a source that is
    not a state species reaches nothing. A parameter input is passed as the
    species `input_species` maps it to."""
    targets = set(targets)
    return {s: _downstream(graph, s) & targets for s in sources}


def input_species(sbml: str, inputs: set[str]) -> dict[str, set[str]]:
    """For each input id, the species it enters the model through.

    A species maps to itself. A parameter (or a compartment) maps to every
    species whose rate of change or value its math reaches: the species a
    reaction whose law reads it changes, the variable of a rule or an event
    that reads it, and a species whose initial assignment reads it — through
    any chain of assignment rules and initial assignments of other
    parameters. An id the model does not have maps to nothing."""
    p = _parts(sbml)
    species = set(p.species)
    # parameter -> the parameters whose definition reads it
    feeds: dict[str, set[str]] = {}
    for defs in (p.assignment, p.rate, p.initial):
        for var, reads in defs.items():
            if var in species:
                continue
            for r in reads:
                feeds.setdefault(r, set()).add(var)
    out: dict[str, set[str]] = {}
    for i in inputs:
        if i in species:
            out[i] = {i}
            continue
        if i not in p.symbols:
            out[i] = set()
            continue
        chain = {i}
        stack = [i]
        while stack:
            for q in feeds.get(stack.pop(), ()):
                if q not in chain:
                    chain.add(q)
                    stack.append(q)
        touched: set[str] = set()
        for rx in p.reactions.values():
            if rx["law_names"] & chain:
                touched |= rx["changed"] & species
        for defs in (p.assignment, p.rate, p.initial):
            for var, reads in defs.items():
                if var in species and set(reads) & chain:
                    touched.add(var)
        for reads, assigned in p.events:
            if reads & chain:
                touched |= assigned & species
        out[i] = touched
    return out


def formula_reads(sbml: str, formula: str) -> set[str]:
    """The model ids a PEtab formula reads, through the model's assignment
    rules (an observable of `total := A + B` reads total, A and B).
    Placeholders and PEtab-only parameters are not model ids, and drop out."""
    p = _parts(sbml)
    named = set(_IDENT.findall(str(formula or ""))) & p.symbols
    return _through_rules(p, named) & p.symbols


def _names(ids, limit: int = _SHOW) -> str:
    ids = sorted(ids)
    shown = ", ".join(ids[:limit])
    if len(ids) > limit:
        shown += f", … and {len(ids) - limit} more"
    return "{" + shown + "}"


# The opening words of each finding, which `culprit` reads back: a failing
# check's detail is the only thing the battery's routing sees.
_LEAD = {
    "no_species": "the model has no species",
    "unobserved": "a piece of the model no readout sees: ",
    "anchor_unknown": "anchor not in the model: ",
    "input_unknown": "input not in the model: ",
    "input_idle": "input moves nothing: ",
    "input_unreached": "input reaches no anchor: ",
}


def _anchor_states(p: _Parts, anchors: set[str]) -> dict[str, set[str]]:
    """Each anchor as the state species it stands for: itself, or what its
    assignment rule reads (a species or a parameter the rule defines); empty
    for an id that is neither."""
    states = set(p.states)
    return {
        a: (
            {a}
            if a in states
            else (_through_rules(p, {a}) & states if a in p.assignment else set())
        )
        for a in anchors
    }


def _findings(sbml: str, anchors: set[str], inputs: set[str]) -> list[tuple[str, str]]:
    """(kind, sentence) for every breach of the rule, in the order a redraft
    reads them: the pieces no anchor sees, the anchors the model does not
    have, then the inputs. With no anchor in the model at all, which pieces
    the data sees is not judged; a species that takes part in nothing still
    fails."""
    p = _parts(sbml)
    graph = species_graph(sbml)
    anchors = set(anchors or ())
    stands = _anchor_states(p, anchors)
    known = set().union(*stands.values()) if stands else set()
    out: list[tuple[str, str]] = []
    comps = components(graph)
    if not comps:
        return [("no_species", _LEAD["no_species"])]
    # a species with dynamics of its own (a synthesis, a decay) is a piece of
    # one; a species with none takes part in nothing
    dynamic = {
        s
        for rx in graph["reactions"].values()
        for part in ("reactants", "products", "modifiers", "law_refs")
        for s in rx[part]
    }
    dynamic |= set(p.rate) | {v for _, assigned in p.events for v in assigned}
    for comp in comps:
        if comp & known:
            continue
        if len(comp) == 1 and not comp & dynamic:
            (s,) = comp
            out.append(
                (
                    "unobserved",
                    f"{_LEAD['unobserved']}species {s} takes part in no "
                    f"reaction, rate rule or event — connect it to the model or "
                    f"remove it",
                )
            )
        elif known:
            out.append(
                (
                    "unobserved",
                    f"{_LEAD['unobserved']}{_names(comp)} — its parameters are "
                    f"invisible to the data; connect it to an observed piece, "
                    f"observe it, or remove it",
                )
            )
    for a in sorted(anchors):
        if stands.get(a):
            continue
        why = (
            "is defined by an assignment rule that reads no species"
            if a in p.assignment
            else "is not a species of the model"
        )
        out.append(("anchor_unknown", f"{_LEAD['anchor_unknown']}{a} {why}"))
    if not inputs or not known:
        return out
    entry = input_species(sbml, set(inputs))
    # an anchor an assignment rule defines is reached by what its rule reads
    ruled = {a: _through_rules(p, {a}) for a in anchors if a in p.assignment}
    for i in sorted(inputs):
        via = entry.get(i) or set()
        if i not in p.symbols:
            out.append(
                (
                    "input_unknown",
                    f"{_LEAD['input_unknown']}{i} is not an id of the model",
                )
            )
            continue
        if i in p.derived:
            out.append(
                (
                    "input_idle",
                    f"{_LEAD['input_idle']}{i} is defined by an assignment rule, "
                    f"which no condition can set",
                )
            )
            continue
        if not via:
            out.append(
                (
                    "input_idle",
                    f"{_LEAD['input_idle']}{i} is read by no rate law, rule, "
                    f"initial assignment or event of the model",
                )
            )
            continue
        if any(({i} | via) & reads for reads in ruled.values()):
            continue
        if set().union(*reaches(graph, via, known).values()):
            continue
        moved = set().union(*(_downstream(graph, s) for s in via))
        out.append(
            (
                "input_unreached",
                f"{_LEAD['input_unreached']}{i} moves "
                f"{_names(moved) if moved else 'no state species'} and none of "
                f"the anchors {_names(known, 5)} — the model needs the conversion "
                f"that carries it to one",
            )
        )
    return out


def problems(
    sbml: str, *, anchors: set[str], inputs: set[str] | None = None
) -> list[str]:
    """The breaches of the rule, as sentences a redraft can act on; [] when
    every component of the species graph holds an anchor and every input
    reaches one. An empty `inputs` (a pure time series) applies the component
    rule alone; so does an anchor set with no species of the model in it."""
    return [s for _, s in _findings(sbml, set(anchors or ()), set(inputs or ()))]


def culprit(detail: str) -> str | None:
    """Which part of a problem a failed check's detail blames: `readout` (an
    anchor the model does not have), `model` (a piece of the model no anchor
    sees), `input` (a varied quantity that reaches no anchor), in that order;
    None when the detail names none."""
    text = str(detail or "")

    def _has(*kinds: str) -> bool:
        return any(_LEAD[k] in text for k in kinds)

    if _has("anchor_unknown"):
        return "readout"
    if _has("unobserved", "no_species"):
        return "model"
    if _has("input_unknown", "input_idle", "input_unreached"):
        return "input"
    return None


def _verdict(sbml: str, anchors, inputs, what: str) -> tuple[bool, str]:
    """(passed, detail) of the rule: the problems when failing, the counts when
    passing. An SBML that cannot be read fails, by name."""
    anchors = set(anchors or ())
    inputs = set(inputs or ())
    try:
        graph = species_graph(sbml)
        found = problems(sbml, anchors=anchors, inputs=inputs)
    except Exception as e:
        return False, f"the species graph cannot be read: {type(e).__name__}: {e}"
    head = f"anchors ({what}): {_names(anchors) if anchors else 'none'}"
    if found:
        # the findings first: a reader that cuts the detail short keeps them
        return False, " | ".join([*found, head])
    n_sp, n_rx = len(graph["species"]), len(graph["reactions"])
    comps = components(graph)
    stands = _anchor_states(_parts(sbml), anchors)
    if not any(stands.values()):
        pieces = f"{len(comps)} piece(s), none judged: no anchor is in the model"
    elif len(comps) == 1:
        pieces = f"one piece, observed: {_names(comps[0], 3)}"
    else:
        pieces = f"{len(comps)} pieces, each observed: " + " · ".join(
            _names(c, 3) for c in comps
        )
    parts = [head, f"{n_sp} species, {n_rx} reactions; {pieces}"]
    if not inputs:
        parts.append("no quantity varies across conditions: the component rule alone")
    elif not any(stands.values()):
        parts.append(f"{len(inputs)} input(s) not checked: no anchor to reach")
    else:
        parts.append(f"{len(inputs)} input(s), each reaching an anchor")
    return True, "; ".join(parts)


def model_result(sbml: str, anchors, inputs) -> GateResult:
    """`model_connected` on a built model: the anchors are the species matched to
    the required entities, the inputs what the construction reply marks
    `set_per_condition`."""
    ok, detail = _verdict(sbml, anchors, inputs, "the required entities")
    return GateResult("model_connected", "T0", ok, detail=detail)


def assembly_result(sbml: str, anchors, inputs) -> GateResult:
    """`assembly_connected` on the assembled problem: the anchors are the species
    the observables read, the inputs what the condition table varies."""
    ok, detail = _verdict(sbml, anchors, inputs, "the species the observables read")
    return GateResult("assembly_connected", "T0", ok, detail=detail)
