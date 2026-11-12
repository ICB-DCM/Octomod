"""The entity-glossary coverage rule, without the engine.

  1. coverage, per model: every species resolves in the shared glossary or the candidate's own;
  2. stray, per set: an entry is a typo only when no model of the set has that species.

    uv run python tests/glossary_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# sys.path is extended above so the suite runs from a checkout with nothing
# installed, which is why the engine import cannot sit at the top of the file.
from octomod.workflow_modules.model.engine import (  # noqa: E402
    glossary_problems,
    glossary_set_problems,
    merged_glossary,
)


def model(name: str, species: list[str]) -> str:
    body = "\n".join(f"  species {s} in cell = 0;" for s in species)
    rxns = "\n".join(f"  J{i}: -> {s}; k1;" for i, s in enumerate(species, 1))
    return f"model {name}\n  compartment cell = 1;\n{body}\n  k1 = 0.1;\n{rxns}\nend\n"


def sbml(name: str, species: list[str]) -> str:
    from octomod.gates.build_gates import antimony_to_sbml

    out, err = antimony_to_sbml(model(name, species))
    assert out, f"fixture model did not build: {err}"
    return out


def entry(sid: str, denotes: str = "what it denotes") -> dict:
    return {"id": sid, "denotes": denotes, "unit_convention": "uM"}


def main() -> int:
    A, B, C = sbml("mA", ["A", "B"]), sbml("mB", ["A", "C"]), sbml("mC", ["A"])

    # ---- single model -----------------------------------------------------
    good = {
        "entity_glossary": {"species": [entry("A"), entry("B")], "parameters": []},
        "antimony": model("mA", ["A", "B"]),
    }
    assert glossary_problems(good, A) == [], glossary_problems(good, A)

    missing = {"entity_glossary": {"species": [entry("A")], "parameters": []}}
    probs = glossary_problems(missing, A)
    assert any(
        "without a glossary entry" in p and "'B'" in p.replace('"', "'") for p in probs
    ), probs

    blank = {
        "entity_glossary": {"species": [entry("A"), entry("B", "  ")], "parameters": []}
    }
    assert any("no 'denotes' text" in p for p in glossary_problems(blank, A))

    typo = {
        "entity_glossary": {
            "species": [entry("A"), entry("B"), entry("Bx")],
            "parameters": [],
        }
    }
    probs = glossary_problems(typo, A)
    assert any("names species the model lacks" in p and "Bx" in p for p in probs), probs
    print("single model: coverage, blank denotes and a stray entry all caught")

    # ---- candidate set ----------------------------------------------------
    # a shared glossary covering the UNION; each candidate carries a subset
    shared = {
        "entity_glossary": {
            "species": [entry("A"), entry("B"), entry("C")],
            "parameters": [],
        },
        "antimony": model("mA", ["A", "B"]),
    }
    survivors = [({"id": "M1"}, A), ({"id": "M2"}, B), ({"id": "M3"}, C)]
    probs = glossary_set_problems(shared, survivors)
    assert probs == [], f"a shared glossary covering the union must pass: {probs}"
    print("candidate set: an entry for a species only ONE candidate has is legal")

    # the same glossary plus a genuine typo: in no candidate, in no base model
    with_typo = {
        "entity_glossary": {
            "species": [entry("A"), entry("B"), entry("C"), entry("Dtypo")],
            "parameters": [],
        },
        "antimony": model("mA", ["A", "B"]),
    }
    probs = glossary_set_problems(with_typo, survivors)
    assert len(probs) == 1 and "Dtypo" in probs[0], probs
    assert "no model in this candidate set has" in probs[0], probs[0]
    assert "'A', 'B', 'C'" in probs[0].replace(
        '"', "'"
    ), f"the union must be named: {probs[0]}"
    print("candidate set: an entry matching NO candidate still fails, named —")
    print(f"  {probs[0][:150]}")

    # reported ONCE for the set, not once per candidate
    assert sum(1 for p in probs if "Dtypo" in p) == 1

    # coverage still per candidate: M2 needs C, and nothing supplies it
    thin = {
        "entity_glossary": {"species": [entry("A"), entry("B")], "parameters": []},
        "antimony": model("mA", ["A", "B"]),
    }
    probs = glossary_set_problems(thin, survivors)
    assert any("M2" in p and "without a glossary entry" in p for p in probs), probs
    assert not any("M1" in p or "M3" in p for p in probs), probs
    print(
        "candidate set: coverage is still checked per candidate (M2 flagged, M1/M3 not)"
    )

    # a candidate's OWN entry satisfies coverage without touching the shared one
    own = [
        ({"id": "M1"}, A),
        ({"id": "M2", "entity_glossary": {"species": [entry("C")]}}, B),
    ]
    assert glossary_set_problems(thin, own) == [], glossary_set_problems(thin, own)
    assert {e["id"] for e in merged_glossary(thin, own[1][0])["species"]} == {
        "A",
        "B",
        "C",
    }
    print("candidate set: a candidate's own entry covers what the shared one omits")

    # the base model counts toward the union even if no survivor has that species
    base_only = {
        "entity_glossary": {"species": [entry("A"), entry("Z")], "parameters": []},
        "antimony": model("mZ", ["A", "Z"]),
    }
    probs = glossary_set_problems(base_only, [({"id": "M3"}, C)])
    assert probs == [], f"a species the BASE model has is not stray: {probs}"
    print("candidate set: the base model's species count toward the union")

    print("GLOSSARY UNIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
