"""Every declared setting is honoured, and every code default is the yaml's.

  1. every leaf key of `default.yaml` but `name`/`version` is read in `octomod/`;
  2. every `spec.get(<key>, <literal>)` names a yaml key with the same value;
  3. no `spec.get(<key>, <name>)` twin default remains;
  4. every `spec.require(<key>)` names a key present in both full specs;
  5. no declared number loads as text;
  6. the README's two suite counts equal `tests/run_all.py`'s registry.

    uv run python tests/spec_keys_unit.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

PKG = REPO / "octomod"
DEFAULT_YAML = REPO / "workflows" / "default.yaml"
FULL_SPECS = (DEFAULT_YAML, REPO / "workflows" / "test_redraft.yaml")
# the two keys that describe the FILE rather than a setting
META_KEYS = {"name", "version"}

# ------------------------------------------------------------ the two sides


def leaves(node, prefix: str = "") -> dict[str, object]:
    """Dotted leaf key -> value, over a loaded yaml tree."""
    if isinstance(node, dict):
        out: dict[str, object] = {}
        for k, v in node.items():
            out.update(leaves(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    return {prefix: node}


def _receiver_is_spec(func: ast.AST, in_spec_module: bool) -> bool:
    """True when the receiver is named `spec`, or is `self` inside spec.py itself."""
    if not isinstance(func, ast.Attribute):
        return False
    obj = func.value
    if isinstance(obj, ast.Name):
        return obj.id == "spec" or (in_spec_module and obj.id == "self")
    if isinstance(obj, ast.Attribute):
        return obj.attr == "spec"
    return False


def _literal(node: ast.AST):
    """(True, value) for a literal default, (False, None) for a computed one."""
    try:
        return True, ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return False, None


def spec_reads(pkg: Path) -> dict:
    """Every spec read in the package: keys, prefixes, defaults, twins, requires."""
    exact: set[str] = set()
    prefixes: set[str] = set()
    defaults: list[tuple] = []
    twins: list[tuple] = []
    required: list[tuple] = []
    dynamic = 0
    for path in sorted(pkg.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        rel = path.relative_to(pkg.parent)  # labels stay valid on a foreign tree
        in_spec_module = path.name == "spec.py"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _receiver_is_spec(
                node.func, in_spec_module
            ):
                continue
            method = node.func.attr
            if method not in ("get", "require"):
                continue
            if not node.args:
                continue
            key_node = node.args[0]
            where = f"{rel}:{node.lineno}"
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                key = key_node.value
                exact.add(key)
                if method == "require":
                    required.append((key, where))
                    continue
                default = node.args[1] if len(node.args) > 1 else None
                for kw in node.keywords:
                    if kw.arg == "default":
                        default = kw.value
                if default is None:
                    continue
                ok, value = _literal(default)
                if ok:
                    if value is not None:
                        defaults.append((key, value, where))
                else:
                    twins.append((key, ast.unparse(default), where))
            elif isinstance(key_node, ast.JoinedStr) and key_node.values:
                first = key_node.values[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    prefixes.add(first.value.rstrip("."))
                else:
                    dynamic += 1
            else:
                dynamic += 1
    return {
        "exact": exact,
        "prefixes": prefixes,
        "defaults": defaults,
        "twins": twins,
        "required": required,
        "dynamic": dynamic,
    }


def is_read(key: str, reads: dict) -> bool:
    parts = key.split(".")
    for i in range(1, len(parts) + 1):
        if ".".join(parts[:i]) in reads["exact"]:
            return True
    return any(key == p or key.startswith(p + ".") for p in reads["prefixes"])


# ------------------------------------------------------------------ checks


def unread_keys(pkg: Path, spec_yaml: Path) -> list[str]:
    declared = leaves(yaml.safe_load(spec_yaml.read_text()))
    reads = spec_reads(pkg)
    return sorted(k for k in declared if k not in META_KEYS and not is_read(k, reads))


def disagreeing_defaults(pkg: Path, spec_yaml: Path) -> list[str]:
    declared = leaves(yaml.safe_load(spec_yaml.read_text()))
    out = []
    for key, literal, where in spec_reads(pkg)["defaults"]:
        if key not in declared:
            out.append(
                f"{where}: spec.get({key!r}, {literal!r}) — key ABSENT from the yaml"
            )
        elif declared[key] != literal:
            out.append(
                f"{where}: spec.get({key!r}, {literal!r}) but the yaml says "
                f"{declared[key]!r}"
            )
    return out


def test_every_declared_key_is_read() -> None:
    declared = leaves(yaml.safe_load(DEFAULT_YAML.read_text()))
    reads = spec_reads(PKG)
    check(
        "the crossing is not empty on either side",
        len(declared) > 50 and len(reads["exact"]) > 50,
        f"{len(declared)} leaf keys, {len(reads['exact'])} literal reads, "
        f"{len(reads['prefixes'])} prefix reads, {reads['dynamic']} dynamic",
    )
    unread = unread_keys(PKG, DEFAULT_YAML)
    check(
        "every leaf key in default.yaml is read by something in octomod/",
        not unread,
        ", ".join(unread) or f"all {len(declared) - len(META_KEYS)} settings read",
    )


def test_every_code_default_equals_the_yaml() -> None:
    reads = spec_reads(PKG)
    bad = disagreeing_defaults(PKG, DEFAULT_YAML)
    check(
        "every spec.get(key, literal) names a yaml key with the SAME value",
        not bad,
        "; ".join(bad) or f"{len(reads['defaults'])} literal defaults agree",
    )
    check(
        "no spec.get(key, <name>) twin default remains",
        not reads["twins"],
        "; ".join(f"{w}: {k} <- {e}" for k, e, w in reads["twins"])
        or "none — a required key or a literal equal to the yaml, nowhere else",
    )


def test_every_required_key_is_in_both_full_specs() -> None:
    reads = spec_reads(PKG)
    check(
        "the engine requires at least the keys it was made to require",
        {k for k, _ in reads["required"]}
        >= {
            "search.method",
            "assembly_defaults.max_noise_components",
            # agents.max_prompt_bytes is not required: null means no cap, so
            # payload.prompt_cap reads it with spec.get
            "gates.misfit.alpha",
            "uncertainty.profile_next_guess",
        },
        f"{len(reads['required'])} require() sites",
    )
    for spec_yaml in FULL_SPECS:
        declared = leaves(yaml.safe_load(spec_yaml.read_text()))
        missing = sorted({k for k, _ in reads["required"] if k not in declared})
        check(
            f"every required key is declared in {spec_yaml.name}",
            not missing,
            ", ".join(missing) or "all present",
        )


_NUMERIC_TEXT = re.compile(r"[-+]?\d+(\.\d*)?([eE][-+]?\d+)?")


def numeric_strings(node, prefix: str = "") -> list[str]:
    """Leaves that are strings reading as numbers (PyYAML loads `1.0e3` as text)."""
    if isinstance(node, dict):
        out = []
        for k, v in node.items():
            out += numeric_strings(v, f"{prefix}.{k}" if prefix else str(k))
        return out
    if isinstance(node, list):
        out = []
        for i, v in enumerate(node):
            out += numeric_strings(v, f"{prefix}[{i}]")
        return out
    if isinstance(node, str) and _NUMERIC_TEXT.fullmatch(node.strip()):
        return [f"{prefix} = {node!r}"]
    return []


def test_no_declared_number_loads_as_text() -> None:
    for spec_yaml in FULL_SPECS:
        bad = numeric_strings(yaml.safe_load(spec_yaml.read_text()))
        check(
            f"{spec_yaml.name}: every number that looks like a number IS one",
            not bad,
            "; ".join(bad) or "no numeric text",
        )


def test_the_readme_counts_equal_the_registry() -> None:
    import run_all  # the registry itself; importing it runs nothing

    n_suites, n_full = len(run_all.SUITES), len(run_all.FULL_EFFORT)
    readme = (REPO / "README.md").read_text()
    m = re.search(r"\((\d+) suites, (\d+) of them at full effort", readme)
    check(
        "README states both counts in the one sentence this test reads",
        m is not None,
        "expected '(N suites, M of them at full effort'",
    )
    if m:
        check(
            "README's counts equal run_all.py's registry",
            (int(m.group(1)), int(m.group(2))) == (n_suites, n_full),
            f"README {m.group(1)}/{m.group(2)} vs registry {n_suites}/{n_full}",
        )


def main() -> int:
    test_every_declared_key_is_read()
    test_every_code_default_equals_the_yaml()
    test_every_required_key_is_in_both_full_specs()
    test_no_declared_number_loads_as_text()
    test_the_readme_counts_equal_the_registry()
    return finish(
        "SPEC KEYS",
        "SPEC KEYS OK — every declared setting is read, every code default is "
        "the yaml's, every required key is in both specs",
    )


if __name__ == "__main__":
    sys.exit(main())
