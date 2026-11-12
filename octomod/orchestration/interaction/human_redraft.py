"""The human as a source of redraft feedback, not only the gates.

A `redraft: <what to change>` in a gate note sends the agent's work back with
the person's words. Two rules:

* **a human redraft does not spend the retry budget.** That budget bounds
  failure — how often an agent may fail its own gates before a human is asked
  to extend it; a person asking for a different model has not failed anything.
* **the request is delivered verbatim and attributed.** It reaches the agent as
  the human's words and the ledger records who asked and for what; it is never
  laundered into the engine's own reasoning.

The engine is the other source, through the same loop: a compile failure that
names an agent's block goes back to that agent (`compile_feedback`), and it
reaches the agent as the ENGINE's finding (`engine_feedback`), never under the
human's keys or in the human's words — the attribution rule runs both ways.
"""

from __future__ import annotations

import re

HUMAN = "human"
ENGINE = "engine"


class RedraftRequested(Exception):
    """A human, or the engine, asked for the agent's work to be redone.

    Raised by a gate (source `human`) or by the candidate loop after a compile
    failure that names the agent's block (source `engine`), and caught by the
    module's draft loop. An exception rather than a return value because the
    gate sits several frames inside that loop, and threading a sentinel back
    through every path is how a signal gets dropped on one of them.
    """

    def __init__(self, text: str, role: str, source: str = HUMAN):
        super().__init__(f"{role}: {text}")
        self.text = text
        self.role = role
        self.source = source


# One phrasing, declared as data so the gate cards, the file-gate payload and
# this parser cannot drift apart.
NOTE_FORM = (
    "redraft: <what to change>   send it back to the agent with your words "
    "(does not spend the retry budget)"
)

_REDRAFT = re.compile(
    r"\bredraft\s*:\s*(?P<text>.+?)(?=\s+(?:tier|axes)\s*:|\s+\d+\s*:|$)",
    re.I | re.S,
)

# A discrimination round is built in two calls (the base by construction, each
# candidate as a difference by `expansion`). On the scope card `redraft:` goes
# to the expansions; `redraft base:` sends the base back to construction and the
# expansions are rebuilt on it.
NOTE_FORM_BASE = (
    "redraft base: <what to change>   send the BASE back to construction; the "
    "expansion are then rebuilt on it (does not spend the retry budget)"
)

_REDRAFT_BASE = re.compile(
    r"\bredraft\s+base\s*:\s*(?P<text>.+?)(?=\s+(?:tier|axes)\s*:|\s+\d+\s*:|$)",
    re.I | re.S,
)


def _requested(pattern: re.Pattern, note: str | None) -> str | None:
    m = pattern.search(str(note)) if note else None
    return (m.group("text").strip() or None) if m else None


def parse_base(note: str | None) -> str | None:
    """The human's request to redraft the BASE of a staged discrimination
    round, or None. Same stopping rules as `parse`."""
    return _requested(_REDRAFT_BASE, note)


def previous_reply(ctx, role: str) -> dict | None:
    """The role's own last accepted reply in this round, or None.

    `call_agent` writes every accepted reply to the record's
    `agent_calls/<role>/reply`, so the reply a person just reviewed is there
    until the next call of that role overwrites it — read it BEFORE that call.
    It is the role's own output, made only from what the routing table lets
    that role see, so handing it back cannot show the role anything it was not
    already shown."""
    try:
        reply = (ctx.agent_calls.child(role) / "reply").get(None)
    except Exception:
        return None
    return reply if isinstance(reply, dict) else None


def parse(note: str | None) -> str | None:
    """The human's redraft request, or None.

    Stops at the next declared form (`tier:`, `axes:`, `1:`) so a note that
    combines them does not swallow the rest — a person writing
    `redraft: use the full positional space  tier: base` means both.
    """
    return _requested(_REDRAFT, note)


def record(
    ctx,
    module: str,
    role: str,
    text: str,
    attempt: int | None = None,
    source: str = HUMAN,
) -> None:
    """Ledger the request, attributed to who made it: the human, or the engine
    (`source=ENGINE`, flagged `engine_redraft` and never `human_redraft`, which
    the assembly module reads as a person's request)."""
    if source == ENGINE:
        ctx.ledger.append(
            "note",
            module=module,
            round_idx=getattr(ctx, "round_idx", 0),
            note=f"the engine asked {role} to redraft: {text[:300]}",
            engine_redraft=True,
            role=role,
            attempt=attempt,
        )
        return
    ctx.ledger.append(
        "note",
        module=module,
        round_idx=getattr(ctx, "round_idx", 0),
        note=f"human asked {role} to redraft: {text[:300]}",
        human_redraft=True,
        role=role,
        attempt=attempt,
    )


def context_for(
    text: str,
    role: str,
    previous: dict | None = None,
    *,
    source: str = HUMAN,
    addressed_to: str | None = None,
    step: str | None = None,
) -> dict:
    """What the agent is told: the person's words, marked plainly as a human's
    and not a failed check's, and the reply they are about.

    `previous` is the reply the person reviewed. It passed its gates, so the
    dossier of failed drafts does not hold it; with it the agent revises that
    reply instead of re-rolling.

    With `source=ENGINE` the text is the engine's finding and the keys say so
    (`engine_feedback`, carrying `source` and the role it is `addressed_to`);
    a role it is not addressed to is told to keep its reply. `step` names what
    the engine ran on the reply, when it is not the estimation problem."""
    if source == ENGINE:
        return _engine_context(text, role, previous, addressed_to or role, step)
    base = (
        "A HUMAN read your previous reply and asked for this change. It is "
        "not a gate failure and nothing you produced was invalid — they "
        f"want the {role} done differently. "
    )
    if previous is not None:
        keep = (
            "Your previous reply is `previous_reply`, exactly as you returned "
            "it. Return the SAME contract: revise THAT reply to do what they "
            "asked, changing only what their request implicates, and keep every "
            "id, name, value, bound and rate law it does not implicate exactly "
            "as it is there — the engine compares the two replies and shows the "
            "person every difference. "
        )
    else:
        keep = (
            "Return the SAME contract, revised to do what they asked, changing "
            "what their request implicates and keeping the rest. "
        )
    out = {
        "human_feedback": text,
        "human_feedback_instruction": (
            base
            + keep
            + "If what they ask for is not possible, or would break something "
            "they may not have considered, say so plainly in your build report "
            "and do the closest thing that is defensible — do not silently "
            "ignore it, and do not comply in a way you believe is wrong without "
            "saying why."
        ),
    }
    if previous is not None:
        out["previous_reply"] = previous
    return out


def _engine_context(
    finding: str,
    role: str,
    previous: dict | None,
    addressed_to: str,
    step: str | None = None,
) -> dict:
    """The engine's finding as the agent sees it: under the engine's keys,
    with the role it is addressed to, and never in a person's voice."""
    if role == addressed_to:
        ran = step or "a step it ran on the estimation problem built from your reply"
        head = (
            f"The ENGINE, not a person, sent your previous reply back: {ran} "
            "failed, and the failure names your block. `engine_feedback.finding` "
            "is that failure verbatim, with what the engine did about it. "
        )
        keep = (
            "Your previous reply is `previous_reply`, exactly as you returned "
            "it. Return the SAME contract in full: revise THAT reply to remove "
            "what the failure names, and keep every id, name, value and bound it "
            "does not name exactly as it is there. "
            if previous is not None
            else "Return the SAME contract in full, changing what the failure "
            "names and keeping the rest. "
        )
        tail = (
            "If the failure cannot be removed from your block, say so plainly in "
            "your rationale and do the closest thing that is defensible."
        )
    else:
        head = (
            f"The ENGINE, not a person, sent the {addressed_to} reply back after "
            "a step it ran failed on what that role wrote; "
            "`engine_feedback.finding` is the failure verbatim. It is not "
            "addressed to you, and nothing you returned was found wrong. "
        )
        keep = (
            "Your previous reply is `previous_reply`: return it unchanged, the "
            "SAME contract in full, unless the revised draft you are shown "
            "requires a change; then say in your rationale what changed and why."
            if previous is not None
            else "Return the SAME contract, changing only what the revised draft "
            "you are shown requires."
        )
        tail = ""
    out = {
        "engine_feedback": {
            "source": ENGINE,
            "addressed_to": addressed_to,
            "finding": finding,
        },
        "engine_feedback_instruction": head + keep + tail,
    }
    if previous is not None:
        out["previous_reply"] = previous
    return out


def with_previous(ctx, role: str, feedback: dict | None) -> dict:
    """A cached feedback block (the assembly modules keep one in
    `ctx.cache["_human_feedback"]` for BOTH of their agents) completed with
    THIS role's own previous reply. Empty when nobody asked: a plain call's
    prompt must not change, or `call_cached` would pay for it again. An
    engine-sourced block stays the engine's, addressed to the role it names."""
    if not feedback:
        return {}
    engine = feedback.get("engine_feedback")
    if isinstance(engine, dict):
        return context_for(
            str(engine.get("finding") or ""),
            role,
            previous_reply(ctx, role),
            source=ENGINE,
            addressed_to=engine.get("addressed_to"),
        )
    return context_for(feedback["human_feedback"], role, previous_reply(ctx, role))


def raise_if_asked(
    ctx,
    note,
    *,
    module: str,
    role: str,
    decision_path=None,
    invalidate=(),
) -> None:
    """Turn a `redraft:` in a gate note into a RedraftRequested, or do nothing.

    Two pieces of bookkeeping the callers must not each reinvent:

    * the gate's own DECISION record is removed, so the next pass asks again
      rather than reading back the answer the person has just superseded;
    * any CACHED artifact the agent's reply produced is removed too. An
      assembly is cached in `assembly` / `shared_assembly` precisely so it is
      not redrafted for free, and leaving it would hand the human back the
      very thing they objected to.

    `decision_path` and `invalidate` are record `Node`s. Nodes that do not
    exist are skipped: a caller naming an artifact this run never wrote is
    normal, not an error.
    """
    from octomod.orchestration.interaction import gate_note

    text = parse(note)
    gate_note.report(
        gate_note.Reading(
            read={"redraft": text} if text else {},
            unread=(
                {} if text else gate_note.unread_in_prose(note, ["redraft"], set())
            ),
        ),
        note,
        ledger=ctx.ledger,
        module=module,
        round_idx=ctx.round_idx,
    )
    if text:
        send_back(ctx, module, role, text, remove=[decision_path, *invalidate])


def send_back(ctx, module: str, role: str, text: str, *, remove=()) -> None:
    """Record a person's redraft request, remove the record nodes that would
    read back the superseded answer or reply (missing ones are skipped), and
    raise RedraftRequested for `role`."""
    record(ctx, module, role, text)
    for node in remove:
        if node is None:
            continue
        try:
            node.delete()
        except Exception:
            pass
    raise RedraftRequested(text, role)
