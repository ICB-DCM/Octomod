"""No benchmark identifier may appear in a skill or a contract.

A skill (`skills/<role>.md`) and the output contract (`octomod/agents/__init__.py`) are
sent on every case, so only the inputs may know the case. Identifiers are read from every
`testcase/*/truth/` and each testcase's model and stub files; ordinary English is untouched.

Names only: a mechanism described without naming anything is invisible here, so a pass is
not evidence of a blind run. The prose audit is a human step.

    uv run python tests/no_benchmark_in_templates.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Ordinary domain vocabulary. Each entry is a claim that the name identifies a
# KIND of thing every model of this sort has, not a particular benchmark's
# secret — so an example may use it and give nothing away.
ALLOWED_GENERIC = {
    # single-letter states and inputs: the alphabet is not a disclosure
    "A",
    "B",
    "C",
    "D",
    "P",
    "X",
    "Y",
    "Z",
    "R",
    "S",
    "u",
    "t",
    # the field's ordinary rate names, by what they DO
    "k1",
    "k2",
    "k3",
    "k_deg",
    "k_cat",
    "k_in",
    "k_out",
    "k_on",
    "k_off",
    "k_act",
    "k_deact",
    "v_max",
    "K_m",
    "fb",
    # field names a truth file uses as JSON keys, not identifiers a benchmark owns;
    # the harvest reads keys as well as values, so a generic key is declared here
    "note",
    "sigma",
    "alpha",
    "system",
    "generator",
    "seed",
    "replicates",
    "conditions",
    "provenance",
    "times_min",  # "time" is already in the Antimony structural group below
    # a conserved total is written <species>tot everywhere in this field
    "Atot",
    "Btot",
    "Ctot",
    "Ptot",
    # a reaction's positional id is the convention every model here uses and
    # carries no mechanism; what a reaction connects does
    *(f"J{i}" for i in range(1, 10)),
    *(f"R{i}" for i in range(1, 10)),
    # words that fall out of reading Python source, not model entities
    "None",
    "True",
    "False",
    "product",
    "substrate",
    "modifier",
    # compartment and structural words Antimony itself requires
    "cell",
    "time",
    "model",
    "end",
    "species",
    "compartment",
    # units and column words that are not model entities
    "uM",
    "min",
    "nM",
    "sec",
}

TEMPLATES = sorted((REPO / "skills").rglob("*.md")) + [
    REPO / "octomod" / "agents" / "__init__.py"
]

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# Where a truth file keeps the model's own names: a short list of places rather
# than a walk of the whole file, because the file's structural keys ("conditions",
# "generator", "noise_sd") are its schema and ordinary English.
ENTITY_MAPS = (
    "states",
    "true_parameters",
    "totals",
    "initial_conditions",
    "parameter_units",
    "noise_sd",
    "noise_sigma",
    "true_axes",
)
ENTITY_LISTS = ("true_winner_axes",)
ENTITY_SCALARS = ("true_mechanism_id", "true_winner")

# A word in the `system` string counts only if it is distinctive on its face:
# CamelCase or carrying a digit. "SynMod-4" is a benchmark's name; "module" and
# "synthetic" are not.
DISTINCTIVE = re.compile(r"^(?=.*(?:[A-Z].*[a-z]|\d))[A-Za-z][A-Za-z0-9_]*$")


def testcase_identifiers() -> dict[str, set[str]]:
    """{identifier: {which testcases own it}}, from truth files, stubs and model text."""
    out: dict[str, set[str]] = {}

    def claim(name: object, case: str) -> None:
        s = str(name)
        if len(s) < 2 or s in ALLOWED_GENERIC or not IDENT.fullmatch(s):
            return
        out.setdefault(s, set()).add(case)
        # and the stems of a compound identifier, since a leak can name the stem;
        # a stem counts only when distinctive on its face (CamelCase or a digit),
        # so `noise_sigma` contributes nothing
        for seg in s.split("_"):
            if len(seg) >= 4 and seg not in ALLOWED_GENERIC and DISTINCTIVE.match(seg):
                out.setdefault(seg, set()).add(case)

    for case_dir in sorted((REPO / "testcase").iterdir()):
        if not case_dir.is_dir():
            continue
        case = case_dir.name
        claim(case, case)  # a skill that names a testcase is itself a leak
        for f in sorted((case_dir / "truth").glob("*.json")):
            data = json.loads(f.read_text())
            if not isinstance(data, dict):
                continue
            for key in ENTITY_MAPS:
                node = data.get(key)
                if isinstance(node, dict):
                    for name in node:
                        claim(name, case)
                elif isinstance(node, list):
                    for name in node:
                        claim(name, case)
            for key in ENTITY_LISTS:
                for name in data.get(key) or []:
                    claim(name, case)
            for key in ENTITY_SCALARS:
                if data.get(key):
                    claim(data[key], case)
            # distinctive words out of the prose too: a `states` map describes the
            # internal names with readout names ("KinA_p, active kinase");
            # `DISTINCTIVE` keeps "KinA_p" and drops "active"
            prose = [str(data.get("system", ""))]
            for key in ENTITY_MAPS + ("discriminating_signature",):
                node = data.get(key)
                if isinstance(node, dict):
                    # strings only: stringifying a bool or None yields
                    # "True"/"None", which are nobody's entities
                    prose += [v for v in node.values() if isinstance(v, str)]
            for word in re.findall(r"[A-Za-z][A-Za-z0-9_]*", " ".join(prose)):
                if DISTINCTIVE.match(word):
                    claim(word, case)
        # the axis ids and species ids a stub declares
        for f in sorted(case_dir.rglob("*.json")):
            if "truth" in f.parts:
                continue
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for key in ("model_space", "candidates"):
                for entry in data.get(key) or []:
                    if not isinstance(entry, dict):
                        continue
                    claim(entry.get("id"), case)
                    for par in entry.get("adds_parameters") or []:
                        if isinstance(par, dict):
                            claim(par.get("id"), case)
            for sp in (data.get("network") or {}).get("species") or []:
                if isinstance(sp, dict):
                    claim(sp.get("id"), case)
                    # a display name is prose ("active sensor", "product")
                    # and counts only when distinctive on its face
                    _name = str(sp.get("name") or "")
                    if DISTINCTIVE.match(_name):
                        claim(_name, case)
            # the readout vocabulary: a data column is staged to the agent, but the
            # same name in a contract's glossary example primes every case with it
            for entry in data.get("observable_labels") or []:
                claim(entry.get("label") if isinstance(entry, dict) else entry, case)
            for entry in data.get("mappings") or []:
                if isinstance(entry, dict):
                    claim(entry.get("observable_label"), case)
            for entry in data.get("observables") or []:
                if isinstance(entry, dict):
                    claim(entry.get("maps_to_label"), case)
                    claim(entry.get("observable_id"), case)
            for sp in (data.get("entity_glossary") or {}).get("species") or []:
                if isinstance(sp, dict):
                    claim(sp.get("id"), case)
            # and the model text: the reaction ids and species its Antimony
            # declares are this benchmark's own vocabulary
            for word in re.findall(
                r"[A-Za-z][A-Za-z0-9_]*", str(data.get("antimony", ""))
            ):
                if DISTINCTIVE.match(word):
                    claim(word, case)
            for par in data.get("parameters") or []:
                if isinstance(par, dict):
                    claim(par.get("id"), case)
    return out


def leaks() -> list[tuple[Path, str, str, set[str]]]:
    """[(template, identifier, the line it is on, which testcases own it)]."""
    owned = testcase_identifiers()
    found = []
    for path in TEMPLATES:
        if not path.exists():
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for ident in set(IDENT.findall(line)):
                if ident in owned:
                    found.append(
                        (path, ident, f"{n}: {line.strip()[:96]}", owned[ident])
                    )
    return found


def main() -> int:
    owned = testcase_identifiers()
    found = leaks()
    print(
        f"{len(owned)} benchmark identifier(s) across "
        f"{len({c for cs in owned.values() for c in cs})} testcase(s); "
        f"{len(TEMPLATES)} template file(s) scanned\n"
    )
    if found:
        by_file: dict[Path, list] = {}
        for path, ident, where, cases in found:
            by_file.setdefault(path, []).append((ident, where, cases))
        print(f"BENCHMARK IDENTIFIERS IN TEMPLATES — {len(found)} occurrence(s):")
        for path, items in by_file.items():
            print(f"\n  {path.relative_to(REPO)}")
            for ident, where, cases in sorted(items):
                print(f"    {ident!r} (owned by {sorted(cases)})")
                print(f"      {where}")
        print(
            "\nA skill and a contract are sent on EVERY case. An identifier a "
            "benchmark owns, written into either, hands the answer to the run "
            "that is supposed to discover it. Re-illustrate on an abstract "
            "system — never on another testcase, which repeats the mistake one "
            "testcase along."
        )
        return 1
    print(
        "NO BENCHMARK IN TEMPLATES OK — no skill and no contract names an "
        "identifier any testcase owns.\n  NAMES ONLY: a mechanism described "
        "without naming anything is invisible here. The prose audit is a human "
        "step and is required before any "
        "blind claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
