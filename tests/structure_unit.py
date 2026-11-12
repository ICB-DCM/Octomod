"""Structural invariants of the engine package, checked by AST.

  1. no orphan modules: each is imported somewhere or marked `STAGED — wired by C<k>`;
  2. no cross-module underscore imports, ratcheted against `KNOWN_UNDERSCORE_IMPORTS`.

    uv run python tests/structure_unit.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "octomod"

# Known cross-module underscore imports, as (importing module, source module,
# name). Empty: a new entry here is a new private coupling.
KNOWN_UNDERSCORE_IMPORTS: set[tuple[str, str, str]] = set()

STAGED = "STAGED — wired by C"


def modules() -> dict[str, Path]:
    """Engine modules by dotted name; `__init__`/`__main__` count only as importers."""
    return {
        p.relative_to(PKG).with_suffix("").as_posix().replace("/", "."): p
        for p in PKG.rglob("*.py")
        if p.name not in ("__init__.py", "__main__.py")
    }


def importer_sources() -> dict[str, Path]:
    """Every file whose imports count: the modules, the package files and the suites."""
    out = dict(modules())
    for p in list(PKG.rglob("__init__.py")) + list(PKG.rglob("__main__.py")):
        out[p.relative_to(PKG).as_posix()] = p
    for p in (REPO / "tests").glob("*.py"):
        out[f"tests/{p.name}"] = p
    return out


def _imports(tree: ast.AST) -> list[tuple[str, str]]:
    """[(module, imported_name)] for every import in one file."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = (node.module or "").removeprefix("octomod.")
            for alias in node.names:
                out.append((mod, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name.removeprefix("octomod."), ""))
    return out


def main() -> int:
    mods = modules()
    short = {name.rsplit(".", 1)[-1]: name for name in mods}
    trees = {name: ast.parse(path.read_text()) for name, path in mods.items()}
    all_trees = {
        name: ast.parse(path.read_text()) for name, path in importer_sources().items()
    }

    # ---- 1. no orphan modules --------------------------------------------
    imported: set[str] = set()
    for tree in all_trees.values():
        for mod, imported_name in _imports(tree):
            # a module is referenced as the import's module (`from octomod.x
            # import y`) or as its name (`from octomod import x`); both count
            candidates = [mod, mod.rsplit(".", 1)[-1]]
            if imported_name:
                candidates += [
                    f"{mod}.{imported_name}".removeprefix("octomod."),
                    imported_name,
                ]
            for cand in candidates:
                if cand in mods:
                    imported.add(cand)
                elif cand in short:
                    imported.add(short[cand])
    orphans, staged = [], []
    for name, path in mods.items():
        if name in imported:
            continue
        (
            staged if path.read_text().lstrip().startswith('"""' + STAGED) else orphans
        ).append(name)
    print(
        f"modules: {len(mods)} · imported: {len(imported)} · "
        f"staged (dormant by declaration): {sorted(staged)}"
    )
    assert not orphans, (
        f"module(s) neither imported nor marked STAGED: {sorted(orphans)} — "
        f"wire them, delete them, or mark them '{STAGED}<k>' on the docstring's "
        f"first line"
    )

    # ---- 2. cross-module underscore imports, ratcheted --------------------
    found: set[tuple[str, str, str]] = set()
    for name, tree in trees.items():
        for mod, imported_name in _imports(tree):
            if not imported_name.startswith("_") or imported_name.startswith("__"):
                continue
            src = mod.rsplit(".", 1)[-1]
            if src in short and short[src] != name:
                found.add((name.rsplit(".", 1)[-1], src, imported_name))
    new = found - KNOWN_UNDERSCORE_IMPORTS
    fixed = KNOWN_UNDERSCORE_IMPORTS - found
    print(
        f"cross-module underscore imports: {len(found)} "
        f"(known {len(KNOWN_UNDERSCORE_IMPORTS)})"
    )
    assert not new, (
        f"NEW cross-module underscore import(s): {sorted(new)} — a name starting "
        f"with '_' is private to its module; export a public name instead"
    )
    assert not fixed, (
        f"these cross-module underscore imports are gone: {sorted(fixed)} — good; "
        f"now remove them from KNOWN_UNDERSCORE_IMPORTS so the ratchet tightens"
    )
    print("STRUCTURE UNIT OK — no orphan modules; the underscore ratchet holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
