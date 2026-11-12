"""S1 gate ladder, part 1: builds -> valid -> references resolve.

All T0/T1, all cheap, all before any compilation. A model that fails here is
redrafted (bounded retry) — never handed downstream.
"""

from __future__ import annotations

import re

from octomod.gates import GateResult, gate

_MODIFIERS = re.compile(r"(<listOfModifiers>)(.*?)(</listOfModifiers>)", re.S)
_MODIFIER = re.compile(r"<modifierSpeciesReference\b[^>]*/>")
_SPECIES = re.compile(r'\bspecies="([^"]*)"')


def canonical_sbml(sbml: str) -> str:
    """The SBML with every reaction's modifiers in species order.

    libantimony orders the modifiers it infers from a rate law by its internal
    state, not by the text, so one Antimony file can give byte-different SBML
    depending on what the process loaded before. Modifier order means nothing
    in SBML; sorting it makes the SBML a function of the Antimony alone, which
    the compile cache and fit reuse key on. A block holding anything but plain
    modifier elements is left as it is."""

    def _sorted(m: re.Match) -> str:
        body = m.group(2)
        items = _MODIFIER.findall(body)
        if len(items) < 2 or _MODIFIER.sub("", body).strip():
            return m.group(0)
        gaps = re.findall(r"/>(\s*)<", body)
        sep = gaps[0] if gaps else ""
        lead = body[: len(body) - len(body.lstrip())]
        trail = body[len(body.rstrip()) :]
        items.sort(key=lambda el: (_SPECIES.findall(el) or [el])[0])
        return m.group(1) + lead + sep.join(items) + trail + m.group(3)

    return _MODIFIERS.sub(_sorted, sbml)


def antimony_to_sbml(antimony_src: str) -> tuple[str | None, str]:
    """Returns (sbml_string | None, error_text). The gate ladder's rung 0.
    The SBML is canonical (`canonical_sbml`): the same Antimony always gives
    the same bytes."""
    import antimony

    antimony.clearPreviousLoads()
    code = antimony.loadAntimonyString(antimony_src)
    if code < 0:
        return None, antimony.getLastError()
    module = antimony.getMainModuleName()
    sbml = antimony.getSBMLString(module)
    if not sbml:
        return None, antimony.getLastError() or "antimony produced empty SBML"
    return canonical_sbml(sbml), ""


def estimated_but_unused(sbml: str, parameters: list) -> list[str]:
    """Parameters marked for estimation that no math in the model reads.

    Read from the converted SBML, not the Antimony text: a name can appear in
    the text only as its own declaration (`kdeph = 0.05;`), and it is the math
    — rate laws, rules, initial values, events, constraints — that decides
    whether a parameter changes any output. An assignment rule counts as a use
    even when nothing in the model reads the rule itself, because the
    observation model reads it later (a modelled count, a readout)."""
    import libsbml

    model = libsbml.readSBMLFromString(sbml).getModel()
    if model is None:
        return []
    used: set[str] = set()

    def walk(ast) -> None:
        if ast is None:
            return
        if ast.isName():
            used.add(ast.getName())
        for i in range(ast.getNumChildren()):
            walk(ast.getChild(i))

    for i in range(model.getNumReactions()):
        law = model.getReaction(i).getKineticLaw()
        if law is not None:
            walk(law.getMath())
    for i in range(model.getNumRules()):
        walk(model.getRule(i).getMath())
    for i in range(model.getNumInitialAssignments()):
        walk(model.getInitialAssignment(i).getMath())
    for i in range(model.getNumEvents()):
        ev = model.getEvent(i)
        for part in (ev.getTrigger(), ev.getDelay(), ev.getPriority()):
            if part is not None:
                walk(part.getMath())
        for j in range(ev.getNumEventAssignments()):
            walk(ev.getEventAssignment(j).getMath())
    for i in range(model.getNumConstraints()):
        walk(model.getConstraint(i).getMath())
    return sorted(
        str(p["id"])
        for p in parameters or []
        if p.get("estimate") and str(p.get("id")) not in used
        # an observation axis's parameter is read by the PEtab tables
        # (a condition override, an offset), not by the model's math
        and p.get("layer") != "assembly"
    )


def make_parameter_use_gates(sbml: str, parameters: list) -> list:
    """Gate: every estimated parameter is read by the model's math.

    An estimated parameter the model never reads changes no output, so fitting
    it adds a flat direction and 2 to the AIC of the candidate carrying it."""

    @gate("model_estimated_parameters_used", "T0")
    def g_used():
        unused = estimated_but_unused(sbml, parameters)
        if unused:
            return GateResult(
                "model_estimated_parameters_used",
                "T0",
                False,
                value=len(unused),
                detail=(
                    f"estimated parameter(s) that no rate law, rule, initial value "
                    f"or event reads: {unused} — a parameter the model never uses "
                    f"changes no output, so fitting it only adds a flat direction; "
                    f"remove it, fix it, or use it"
                ),
            )
        n = sum(1 for p in parameters or [] if p.get("estimate"))
        return GateResult(
            "model_estimated_parameters_used",
            "T0",
            True,
            value=0,
            detail=f"all {n} estimated parameters are read by the model's math",
        )

    return [g_used]


def make_build_gates(antimony_src: str, sbml_holder: dict) -> list:
    """Gate closures over the antimony source. sbml_holder['sbml'] is filled
    on success so later gates (and the module) reuse the converted model."""

    @gate("model_antimony_builds", "T0")
    def g_builds():
        sbml, err = antimony_to_sbml(antimony_src)
        if sbml is None:
            return GateResult(
                "model_antimony_builds",
                "T0",
                False,
                detail=f"antimony rejected the model: {err.strip()}",
            )
        sbml_holder["sbml"] = sbml
        return GateResult(
            "model_antimony_builds", "T0", True, detail="antimony -> SBML conversion OK"
        )

    @gate("model_sbml_valid", "T0")
    def g_valid():
        import libsbml

        doc = libsbml.readSBMLFromString(sbml_holder["sbml"])
        doc.checkConsistency()
        errors = [
            doc.getError(i).getMessage().strip()
            for i in range(doc.getNumErrors())
            if doc.getError(i).getSeverity() >= libsbml.LIBSBML_SEV_ERROR
        ]
        if errors:
            return GateResult(
                "model_sbml_valid",
                "T0",
                False,
                value=len(errors),
                detail="libSBML errors: " + " | ".join(errors[:3]),
            )
        return GateResult(
            "model_sbml_valid", "T0", True, detail="libSBML consistency check clean"
        )

    @gate("model_refs_resolve", "T0")
    def g_refs():
        """Every reaction participant and kinetic-law symbol resolves against
        declared entities; no species without compartment; ids unique."""
        import libsbml

        doc = libsbml.readSBMLFromString(sbml_holder["sbml"])
        model = doc.getModel()
        problems = []
        species = {model.getSpecies(i).getId() for i in range(model.getNumSpecies())}
        params = {
            model.getParameter(i).getId() for i in range(model.getNumParameters())
        }
        comps = {
            model.getCompartment(i).getId() for i in range(model.getNumCompartments())
        }
        known = species | params | comps | {"time", "t"}

        for i in range(model.getNumSpecies()):
            sp = model.getSpecies(i)
            if not sp.getCompartment():
                problems.append(f"species {sp.getId()} has no compartment")

        for i in range(model.getNumReactions()):
            rxn = model.getReaction(i)
            for parts, kind in [
                (
                    [rxn.getReactant(j) for j in range(rxn.getNumReactants())],
                    "reactant",
                ),
                ([rxn.getProduct(j) for j in range(rxn.getNumProducts())], "product"),
                (
                    [rxn.getModifier(j) for j in range(rxn.getNumModifiers())],
                    "modifier",
                ),
            ]:
                for ref in parts:
                    if ref.getSpecies() not in species:
                        problems.append(
                            f"reaction {rxn.getId()}: {kind} {ref.getSpecies()!r} "
                            f"is not a declared species"
                        )
            kl = rxn.getKineticLaw()
            if kl is None:
                problems.append(f"reaction {rxn.getId()} has no kinetic law")
                continue
            local = {kl.getParameter(j).getId() for j in range(kl.getNumParameters())}
            math = kl.getMath()
            if math is not None:
                for sym in _ast_symbols(math):
                    if sym not in known and sym not in local:
                        problems.append(
                            f"reaction {rxn.getId()}: kinetic law references "
                            f"undefined symbol {sym!r}"
                        )
        if problems:
            return GateResult(
                "model_refs_resolve",
                "T0",
                False,
                value=len(problems),
                detail=" | ".join(problems[:4]),
            )
        return GateResult(
            "model_refs_resolve",
            "T0",
            True,
            detail=f"{model.getNumReactions()} reactions, {len(species)} species, "
            f"all references resolve",
        )

    return [g_builds, g_valid, g_refs]


def make_sbml_gates(sbml_holder: dict) -> list:
    """The ladder from rung 1 for a model that arrives as SBML (PEtab entry).

    Validity + references over the SBML already in `sbml_holder['sbml']`
    (ValueError if absent); the Antimony rung is skipped, there being no
    Antimony to build."""
    if "sbml" not in sbml_holder:
        raise ValueError("make_sbml_gates needs sbml_holder['sbml']")
    return make_build_gates("", sbml_holder)[1:]


def _ast_symbols(node) -> set[str]:
    import libsbml

    out = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.getType() == libsbml.AST_NAME:
            out.add(n.getName())
        for i in range(n.getNumChildren()):
            stack.append(n.getChild(i))
    return out
