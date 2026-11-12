"""The S1 required-entities and no-dynamics advisory checks say what they found.

  1. an entry matches by id/name or via the glossary's `denotes`, named to confirm;
  2. an unmatched entry is named; a sentence-length one gets the short-id hint;
  3. a model quiet only because its inputs are off says so, naming the inputs;
  4. a model dead with every input on says NO DYNAMICS; a moving model says so;
  5. S1 hands the gate the glossary.

    uv run python tests/advisory_checks_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402

from octomod.gates.build_gates import antimony_to_sbml  # noqa: E402
from octomod.gates.sim_gates import make_sim_gates  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")


OFF = """model m
  compartment cell = 1;
  species B in cell = 1;
  species Bp in cell = 0;
  species PTP in cell = 1;
  L_a = 0; L_b = 0; k = 0.5; kd = 0.2;
  J1: B -> Bp; k*L_b*B;
  J2: Bp -> B; kd*PTP*Bp;
end
"""
DEAD = """model m
  compartment cell = 1;
  species X in cell = 0;
  species Y in cell = 0;
  k = 0.5;
  J1: X -> Y; k*X;
end
"""
GLOSSARY = {
    "species": [
        {
            "id": "PTP",
            "denotes": "protein tyrosine phosphatase that removes the phosphate from Bp",
        },
        {"id": "Bp", "denotes": "phosphorylated B"},
    ],
    "parameters": [{"id": "L_b", "denotes": "presence of ligand b (0/1)"}],
}


def _gates(ant: str, required=None, glossary=None) -> dict:
    sbml, err = antimony_to_sbml(ant)
    assert sbml, err
    out = {}
    for g in make_sim_gates(
        sbml, 10.0, {}, SPEC, required_entities=required, glossary=glossary
    ):
        r = g()
        out[r.gate_id] = r
    return out


def main() -> int:
    req = [
        "B",
        "phosphatase",
        "the enzyme that dephosphorylates B in every cell population and condition",
    ]
    r = _gates(OFF, req, GLOSSARY)["model_required_entities"]
    via = (r.value or {}).get("via_glossary") or {}
    check(
        "an id matches directly; a generic word through the glossary, named for the human",
        via == {"phosphatase": "PTP"}
        and "'phosphatase' → PTP" in r.detail
        and "confirm" in r.detail,
        r.detail,
    )
    check(
        "what matches nothing is still named, with the short-id hint for a sentence",
        r.value["missing"] == [req[2]] and "reads as a sentence" in r.detail,
        r.detail,
    )
    r0 = _gates(OFF, req, None)["model_required_entities"]
    check(
        "without a glossary the generic word is unmatched, as before",
        "phosphatase" in r0.value["missing"],
        r0.detail,
    )
    r1 = _gates(OFF, ["B", "PTP"], GLOSSARY)["model_required_entities"]
    check(
        "all by id/name reads as before",
        r1.detail == "all required entities matched by id/name",
        r1.detail,
    )

    d = _gates(OFF)["model_no_dynamics_screen"]
    check(
        "quiet only because the inputs are off: said, naming the input that moves it",
        "inputs are off" in d.detail
        and d.value["responds_to"] == ["L_b"]
        and set(d.value["inputs_off"]) == {"L_a", "L_b"}
        and "NO DYNAMICS" not in d.detail,
        d.detail,
    )
    dd = _gates(DEAD)["model_no_dynamics_screen"]
    check(
        "a model dead with every input on still says NO DYNAMICS",
        dd.detail.startswith("NO DYNAMICS"),
        dd.detail,
    )
    moving = OFF.replace("L_b = 0;", "L_b = 1;")
    dm = _gates(moving)["model_no_dynamics_screen"]
    check(
        "a model that moves says so",
        dm.detail == "model responds over the horizon",
        dm.detail,
    )

    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    i = src.index("sim_gates += make_sim_gates(")
    check(
        "S1 hands the gate the glossary",
        "glossary=" in src[i : i + 400] and '"glossary"' in src[i - 700 : i],
    )

    return finish(
        "\nADVISORY CHECKS",
        "\nADVISORY CHECKS UNIT OK — the entity check reads the glossary, and a quiet base says its inputs are off",
    )


if __name__ == "__main__":
    sys.exit(main())
