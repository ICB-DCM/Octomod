"""Antimony source as text: the symbol-level reading needed before compiling.

One reading, shared by every caller:

  comments (`//`, `#`, `/* */`) are prose, never symbols;
  a reaction line's own id (`R1: A -> B; ...`) is a declaration, not a use;
  a plain numeric declaration (`k1 = 0.5;`) declares its symbol, it does not
    use it.

Pure functions over strings; no context, no files.
"""

from __future__ import annotations

import re

# Words Antimony reserves that a regex identifier scan would otherwise report
# as symbols a model "uses" or fails to declare.
KEYWORDS = frozenset({"cell", "end", "model", "species", "compartment", "const", "var"})

_IDENT = re.compile(r"\b([A-Za-z_]\w*)\b")
_REACTION_LINE = re.compile(r"\s*([A-Za-z_]\w*)\s*:(.*)$")
# `R1: A -> B; rate` (or `=>`): an id, a colon that is not `:=` (an assignment
# rule), then an arrow. An event (`E1: at ...`) carries no arrow.
_REACTION_DECL = re.compile(r"^\s*([A-Za-z_]\w*)\s*:(?!=).*(?:->|=>)")
_NUMERIC_DECL = re.compile(
    r"^\s*(?:const\s+|var\s+)?[A-Za-z_]\w*\s*=\s*[-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?\s*;?\s*$"
)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(re.sub(r"(//|#).*$", "", ln) for ln in text.splitlines())


def identifiers(text: str) -> set[str]:
    """Every identifier outside comments, keywords included."""
    return set(_IDENT.findall(strip_comments(text)))


def reaction_ids(text: str) -> list[str]:
    """The ids of the reactions the text declares, in declaration order, once each."""
    ids = []
    for line in strip_comments(text).splitlines():
        m = _REACTION_DECL.match(line)
        if m:
            ids.append(m.group(1))
    return list(dict.fromkeys(ids))


def reaction_lines(text: str) -> list[tuple[str, str]]:
    """(id, the declaring line, stripped) for each reaction, in declaration
    order, once each: the reaction as the model states it, on one line."""
    out: dict[str, str] = {}
    for line in strip_comments(text).splitlines():
        m = _REACTION_DECL.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = " ".join(line.split())
    return list(out.items())


def split_reaction_declarations(text: str) -> tuple[set[str], list[str]]:
    """(reaction ids the text declares, the lines with those ids removed)."""
    declared: set[str] = set()
    body: list[str] = []
    for line in strip_comments(text).splitlines():
        m = _REACTION_LINE.match(line)
        if m:
            declared.add(m.group(1))
            body.append(m.group(2))
        else:
            body.append(line)
    return declared, body


def used_symbols(text: str) -> set[str]:
    """Symbols the model USES: every identifier outside comments and outside
    plain numeric declarations (`k1 = 0.5;` declares k1, it does not use it)."""
    used: set[str] = set()
    for line in strip_comments(text).splitlines():
        for stmt in line.split(";"):
            if not stmt.strip() or _NUMERIC_DECL.match(stmt + ";"):
                continue
            used |= set(_IDENT.findall(stmt))
    return used
