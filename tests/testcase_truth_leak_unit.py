"""What an agent reads of a testcase must not name the case's own answer.

  1. description.md and parsed intent.yaml name no mechanism word or value from truth/;
  2. a truth case that supplies literature declares it in STAGED-ON-PURPOSE.txt;
  3. a term declared in truth/STAGED-ON-PURPOSE.txt (one per line) is allowed.

    uv run python tests/testcase_truth_leak_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

MECHANISM_WORDS = (
    "cooperativ",
    "neighbour",
    "neighbor",
    "adjacent",
    "directional",
    "processiv",
    "allosteric",
    "feedback",
    "autocatal",
    "saturab",
    "michaelis",
    "cooperation",
)


def _mechanism_values(tc: Path) -> set[str]:
    """Mechanism parameter values only; times and concentrations are the experiment."""
    out: set[str] = set()
    for f in sorted((tc / "truth").glob("*.json")):
        try:
            d = json.loads(f.read_text(errors="ignore"))
        except Exception:  # noqa: BLE001
            continue
        for key in ("true_parameters", "fitted"):
            block = d.get(key)
            if isinstance(block, dict):
                for v in block.values():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        s = f"{float(v):g}"
                        # a value with real information content, not 0/1/2
                        if len(s.lstrip("-0.")) >= 3:
                            out.add(s)
    return out


def _declared(tc: Path) -> set[str]:
    p = tc / "truth" / "STAGED-ON-PURPOSE.txt"
    if not p.exists():
        return set()
    out = set()
    for line in p.read_text(errors="ignore").splitlines():
        term = line.split("#", 1)[0].strip().lower()
        if term:
            out.add(term)
    return out


def main() -> int:
    cases = sorted(
        p
        for p in (REPO / "testcase").iterdir()
        if p.is_dir() and (p / "truth").is_dir()
    )
    if not cases:
        print("no testcase carries a truth/ folder — nothing to check")
        return 0

    failures, n_declared = [], 0
    for tc in cases:
        truth_text = " ".join(
            f.read_text(errors="ignore").lower()
            for f in (tc / "truth").glob("*")
            if f.is_file()
        )
        words = {w for w in MECHANISM_WORDS if w in truth_text}
        values = _mechanism_values(tc)
        declared = _declared(tc)

        staged = {}
        d = tc / "description.md"
        if d.exists():
            staged["description.md"] = d.read_text(errors="ignore")
        i = tc / "intent.yaml"
        if i.exists():
            staged["intent.yaml (parsed)"] = json.dumps(yaml.safe_load(i.read_text()))

        hits, ok_hits = [], []
        for where, text in staged.items():
            low = text.lower()
            for term in sorted(words | values):
                if term.lower() in low:
                    (ok_hits if term.lower() in declared else hits).append(
                        (where, term)
                    )
        # A benchmark case that supplies literature declares it: the engine's
        # intent-gate rule, checked on the staged tree so no case is committed
        # in a state the engine refuses.
        if i.exists():
            from octomod.workflow_modules.knowledge import supplied_literature as _lit

            decl = _lit.declaration_problem(tc, yaml.safe_load(i.read_text()) or {})
            if decl:
                hits.append(("intent.yaml supplied_literature", "undeclared"))
                print(f"  {tc.name}: {decl}")
        n_declared += len(ok_hits)
        if hits:
            failures.append((tc.name, hits))
        else:
            extra = f", {len(ok_hits)} declared" if ok_hits else ""
            print(
                f"  {tc.name:18s} clean — truth uses {len(words)} mechanism word(s), "
                f"{len(values)} mechanism value(s){extra}"
            )

    if failures:
        print("\nFAILED — a case names its own answer in what an agent reads:")
        for name, hits in failures:
            for where, term in hits:
                print(f"  {name}: {term!r} in {where}")
        print(
            "\nEither remove it, or declare it in truth/STAGED-ON-PURPOSE.txt "
            "(one term per line, reason after '#')."
        )
        return 1

    print(
        f"\nTESTCASE TRUTH LEAK UNIT OK — {len(cases)} case(s) checked; "
        f"{n_declared} declared inclusion(s); no undeclared mechanism word or "
        f"mechanism value in any staged file"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
