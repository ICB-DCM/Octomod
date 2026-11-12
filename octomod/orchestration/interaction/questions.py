"""Questions the engine raises for the human, surfaced on the next gate card.

An agent proposal that would change what the data means (e.g. a
reinterpretation-class condition axis) is refused and queued here as a question
(`raise_for_human`, the run's `pending_questions` record). `humangate.ask`
(configured with the record root by the orchestrator) shows the pending
questions on the next gate card and in the `pending_gate` payload;
`mark_shown` then moves them, with the gate module and the human's note, to
the run-level `questions` record.
"""

from __future__ import annotations

import datetime

from octomod.result.node import Node


def pending_node(root: Node) -> Node:
    return root / "pending_questions"


def open_node(root: Node) -> Node:
    return root / "questions"


def _load(node: Node) -> list:
    try:
        return list(node.get([]))
    except Exception:
        return []


def raise_for_human(
    ctx, topic: str, question: str, raised_by: str, detail: str = ""
) -> dict:
    """Queue a question for the next human gate. Deduplicated by (topic,
    question) so a validator that runs twice does not ask twice."""
    node = pending_node(ctx.root)
    pending = _load(node)
    if any(q.get("topic") == topic and q.get("question") == question for q in pending):
        return pending[
            [
                i
                for i, q in enumerate(pending)
                if q.get("topic") == topic and q.get("question") == question
            ][0]
        ]
    q = {
        "id": f"r{ctx.round_idx}_engine_{len(pending) + 1}",
        "raised_by": raised_by,
        "raised_round": ctx.round_idx,
        "topic": topic,
        "question": question,
        "detail": detail,
        "raised_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
    }
    pending.append(q)
    node.put(pending)
    ctx.ledger.append(
        "question_raised",
        module=raised_by,
        round_idx=ctx.round_idx,
        question_id=q["id"],
        topic=topic,
        question=question,
    )
    return q


def pending(root: Node) -> list[dict]:
    return _load(pending_node(root))


def card_lines(root: Node) -> list[str]:
    """The lines a gate card appends when engine questions are pending."""
    qs = pending(root)
    if not qs:
        return []
    lines = [
        "",
        "QUESTIONS THE ENGINE RAISES FOR YOU (known things are never "
        "changed — they are put to you; answer in the note by number):",
    ]
    for k, q in enumerate(qs, 1):
        lines.append(f"  Q{k}. {q['question']}")
        if q.get("detail"):
            lines.append(f"       ({str(q['detail'])[:160]})")
    return lines


def mark_shown(
    root: Node, module: str, note: str, ledger=None, round_idx: int = 0
) -> None:
    """Move every pending question to the `questions` record with the gate
    that showed it and what the human wrote."""
    qs = pending(root)
    if not qs:
        return
    opened = _load(open_node(root))
    known = {q.get("id") for q in opened}
    for q in qs:
        rec = dict(q)
        rec["status"] = "answered_at_gate" if note else "shown_at_gate"
        rec["shown_at_gate"] = module
        rec["human_answer"] = note or "(approved without a note)"
        if rec["id"] not in known:
            opened.append(rec)
        if ledger is not None:
            ledger.append(
                "question_shown",
                module=module,
                round_idx=round_idx,
                question_id=q["id"],
                topic=q["topic"],
                human_note=note,
            )
    open_node(root).put(opened)
    pending_node(root).delete()
