"""Render-side prose budgets and the clipping that enforces them.

The renderer enforces the budgets, never the agents; the ledger, the decision
record (`decisions_md`) and the agent calls stay exhaustive. Every number is published in REPORTING.md and
`tests/report_budget_unit.py` fails if the two disagree. Clipping only moves text
into a fold or a link; nothing is deleted.
"""

from __future__ import annotations

import re

# Contract numbers: REPORTING.md, "Prose budgets".
MISFIT_REASON_CHARS = 160
MISFIT_REASONS_SHOWN = 3
EPISTEMICS_ENTRY_CHARS = 120
EPISTEMICS_ENTRIES_SHOWN = 6
DIAGNOSIS_SENTENCES = 3
HYPOTHESES_SHOWN = 3
INTENT_EVIDENCE_CHARS = 160
DECISION_RATIONALE_CHARS = 200
DECISIONS_SHOWN = 8
EVIDENCE_LINES_SHOWN = 2
# A decision cell's alternatives and question get the rationale's limit: each is
# an argument whose first line is the claim and whose remainder is context.
DECISION_ALTERNATIVES_CHARS = 200
DECISION_QUESTION_CHARS = 200
GATE_DETAIL_CHARS = 200
DATA_FLAGS_SHOWN = 6

# Sentence enders, and the abbreviations that are not one. Cutting "et al."
# into a sentence boundary would end a claim mid-citation.
_ENDER = re.compile(r"(?<=[.!?])\s+")
_NOT_AN_ENDER = re.compile(r"(?:\b(?:e\.g|i\.e|cf|vs|et al|approx|Fig|Eq|no)\.)$", re.I)

# Below this fraction of the limit a sentence boundary is not worth taking:
# one sentence out of a long paragraph reads as a fragment, not a summary.
_MIN_SENTENCE_FRACTION = 0.4


def sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping abbreviations intact.

    A fragment with no word character (such as a clip's ellipsis) is not counted.
    """
    out: list[str] = []
    for piece in _ENDER.split(str(text).strip()):
        if out and _NOT_AN_ENDER.search(out[-1]):
            out[-1] = out[-1] + " " + piece
        else:
            out.append(piece)
    return [s for s in out if s and re.search(r"\w", s)]


def clip_chars(text, limit: int) -> tuple[str, bool]:
    """Return (visible, was_clipped). Cuts at a sentence boundary when the text
    has one far enough in, else at a word boundary, and marks the cut."""
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s, False
    head = s[:limit]
    parts = sentences(head)
    if len(parts) > 1:
        keep = " ".join(parts[:-1])
        if len(keep) >= _MIN_SENTENCE_FRACTION * limit:
            return keep + " …", True
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return cut.rstrip(",;:") + " …", True


def clip_sentences(text, limit: int) -> tuple[str, bool]:
    """Return (visible, was_clipped) keeping at most `limit` sentences."""
    parts = sentences(text)
    if len(parts) <= limit:
        return " ".join(parts), False
    return " ".join(parts[:limit]) + " …", True


def fold(summary: str, body: str, *, open_: bool = False) -> str:
    """Wrap `body` in a <details> fold; "" for an empty body."""
    if not str(body).strip():
        return ""
    return (
        f'<details{" open" if open_ else ""}><summary>{summary}</summary>'
        f"{body}</details>"
    )
