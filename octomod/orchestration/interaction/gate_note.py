"""One reading of the human's words at a gate, by the same rules at every gate.

A `key: value` / `key=value` form is read wherever it is written (keys are
whole words: `run=3` is not `n=3`). A bare word (`adjoint`) is read only when it
stands alone — the whole note, a line, a part between `;` or `,`, or beside
other forms or a leading `y`/`n` — never inside a sentence. Other words act on
nothing. `report` prints and ledgers what was read and every form word that was
not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CLAUSE = re.compile(r"[\n;,]")
# a key form inside a clause: `key=value` (the value one token) or `key: value`
# (the value the rest of the clause); `1: …` numbered answers are key forms too
_EQ_FORM = re.compile(r"(?<![\w-])[A-Za-z_][\w-]*\s*=\s*\S+")
_COLON_FORM = re.compile(r"(?<![\w-])(?:[A-Za-z_][\w-]*|\d+)\s*:\s*.*$")
_ANSWER_WORDS = {"y", "yes", "n", "no"}
_STRIP = "()[]{}.!?\"'`:"


def clauses(note: str | None) -> list[str]:
    """The note's parts: lines, and the pieces between `;` and `,`."""
    return [c.strip() for c in _CLAUSE.split(note or "") if c.strip()]


def key_value(note: str | None, *keys: str) -> str | None:
    """The value of the first `key: value` / `key=value` form among `keys`
    (case-insensitive), up to the end of its line or the next `;`."""
    for key in keys:
        m = re.search(
            rf"(?<![\w-]){re.escape(key)}\s*[:=]\s*([^\n;]*)", note or "", re.I
        )
        if m:
            return m.group(1).strip()
    return None


def key_list(note: str | None, *keys: str) -> list[str] | None:
    """The values of the first `key: a, b` form among `keys` (case-insensitive),
    split on commas and whitespace, up to the end of its line, a `.` or a `;`;
    None when the note carries no such form."""
    for key in keys:
        m = re.search(
            rf"(?<![\w-]){re.escape(key)}\s*[:=]\s*([^\n.;]*)", note or "", re.I
        )
        if m:
            return [t for t in re.split(r"[,\s]+", m.group(1).strip()) if t]
    return None


_TIER = re.compile(r"(?<![\w-])tier\s*[:=]\s*(base|none|all|top\s*\d+)\b", re.I)


def tier(note: str | None) -> str | None:
    """The `tier:` form as "base", "none", "all" or "top<k>", or None."""
    m = _TIER.search(note or "")
    return m.group(1).lower().replace(" ", "") if m else None


def key_int(note: str | None, key: str) -> int | None:
    """`key=<integer>` as a whole token (`n=50`, `n = 50`), or None."""
    m = re.search(rf"(?<![\w-]){re.escape(key)}\s*=\s*(\d+)(?![\w.])", note or "", re.I)
    return int(m.group(1)) if m else None


def standalone(note: str | None, words) -> set[str]:
    """The `words` that stand alone in the note (see the module rules)."""
    wanted = {str(w).lower(): str(w) for w in words}
    found: set[str] = set()
    for clause in clauses(note):
        rest = _COLON_FORM.sub(" ", _EQ_FORM.sub(" ", clause))
        tokens = [t.strip(_STRIP).lower() for t in rest.split()]
        tokens = [t for t in tokens if t]
        if tokens and tokens[0] in _ANSWER_WORDS:
            tokens = tokens[1:]
        if tokens and all(t in wanted for t in tokens):
            found |= {wanted[t] for t in tokens}
    return found


def mentioned(note: str | None, words) -> set[str]:
    """The `words` that appear anywhere in the note as whole words."""
    return {
        str(w)
        for w in words
        if re.search(rf"(?<![\w-]){re.escape(str(w))}(?![\w-])", note or "", re.I)
    }


@dataclass
class Reading:
    """What a gate took from a note: `read` is what it will act on, `unread`
    the form words it saw and did not act on, each with the reason."""

    read: dict = field(default_factory=dict)
    unread: dict = field(default_factory=dict)

    def line(self) -> str:
        parts = []
        for k, v in self.read.items():
            if v is True:
                parts.append(str(k))
            elif isinstance(v, int):
                parts.append(f"{k}={v}")
            else:
                text = str(v)
                parts.append(f"{k}: {text if len(text) <= 80 else text[:77] + '…'}")
        if not (parts or self.unread):
            return "no form — only your words, for the record"
        # a form that was written and not acted on is named, never summed up
        # as "no form"
        out = " · ".join(parts) if parts else "nothing acted on"
        if self.unread:
            out += " | NOT read: " + "; ".join(
                f"{w} ({why})" for w, why in self.unread.items()
            )
        return out


# the reason given for every form word found inside a sentence
IN_PROSE = "inside a sentence — a form is the word on its own"


def unread_in_prose(note: str | None, words, read: set[str]) -> dict:
    """{word: IN_PROSE} for each of `words` the note mentions but did not
    carry as a form."""
    return {w: IN_PROSE for w in sorted(mentioned(note, words) - set(read))}


def report(
    reading: Reading,
    note: str | None,
    *,
    ledger,
    module: str,
    round_idx: int,
    candidate: str | None = None,
) -> None:
    """Print and ledger what the gate read. Silent for an empty note: there is
    nothing to misread."""
    if not (note or "").strip():
        return
    line = reading.line()
    print(f"  read from your note: {line}")
    extra = {"candidate": candidate} if candidate else {}
    ledger.append(
        "note",
        module=module,
        round_idx=round_idx,
        note=f"read from the human's note: {line}",
        note_read=reading.read,
        note_unread=reading.unread,
        **extra,
    )
