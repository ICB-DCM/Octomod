"""T4: the blocking human gate, placed before expensive or hard-to-undo steps.

Delivery modes: `interactive` (terminal y/n, the default), `auto` (test mode,
ledgered as auto-approved) and `file` (the card is written to the record's
`pending_gate` — `./run.sh pending --run-id <id>` prints it — and the run
exits with code 3; a rerun with `--gate-answer y|n [--gate-note "..."]`
resumes at exactly this gate). A declared gate policy is consulted first; its
answers are ledgered mode="policy" with its sha.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from octomod.result.node import Node, pending_node

_FILE_MODE = {
    "enabled": False,
    "root": None,
    "answer": None,
    "note": "",
    # the module of the gate that paused the run, from the record's `pending_gate`
    "pending_module": None,
}
_AUTO_NOTE = {"note": ""}
_QUESTIONS = {"root": None}  # engine-raised questions ride the next gate card
_POLICY = {"policy": None}  # declared answers, consulted before any mode


def configure_policy(policy) -> None:
    """Install the run's gate policy (None: every gate is delivered to a human
    by the configured mode)."""
    _POLICY["policy"] = policy


def policy_in_force():
    return _POLICY["policy"]


def configure_questions(root: Node) -> None:
    """Let every gate card carry the questions the engine has queued for the
    human (octomod.orchestration.interaction.questions) and record their answers. `root` is the run
    record's root node."""
    _QUESTIONS["root"] = root


# How many extra attempts --auto-approve may grant at an exhaustion gate
# (`<module>_redraft_budget`), set by the orchestrator from `retry.auto_grants`.
# None = never configured: an auto run reaching an exhaustion gate is refused.
_AUTO_GRANTS: dict = {"cap": None}


def configure_auto_grants(cap: int) -> None:
    """The auto path's grant cap, from `retry.auto_grants`."""
    _AUTO_GRANTS["cap"] = int(cap)


def configure_auto_note(note: str) -> None:
    """Standing note applied to every auto-approved gate (test mode only)."""
    _AUTO_NOTE["note"] = note or ""


class GatePending(Exception):
    """Raised in file mode when a gate awaits a human answer (the record's
    `pending_gate`)."""

    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(f"gate pending: {payload['module']}")


def configure_file_mode(root: Node, answer: bool | None, note: str = "") -> None:
    """File mode on the run record `root`: the pending gate goes to
    `root/pending_gate`. Store one answer for the resume; the gate that may
    take it is decided at the gate (`_take_stored_answer`, by module and
    round). The pending module is kept for the record and the tests."""
    pending_module = None
    pend = pending_path(root)
    try:
        payload = pend.get(None)
        pending_module = payload.get("module") if isinstance(payload, dict) else None
    except Exception:
        pending_module = None
    _FILE_MODE.update(
        enabled=True,
        root=root,
        answer=answer,
        note=note,
        pending_module=pending_module,
    )


def _take_stored_answer(
    pend: Node, module: str, round_idx, ledger
) -> tuple[bool, str] | None:
    """The stored file-gate answer, if it was given for this gate.

    The record's `pending_gate` is written when a gate pauses and removed
    only when that gate's answer is consumed, so while it exists it names the
    gate the human answered. A different gate reached first on the resume
    leaves the answer unconsumed and pauses there instead. With no pending
    record (a re-entry, a crash) the first gate takes it.
    """
    if _FILE_MODE["answer"] is None:
        return None
    named = _pending_gate(pend)
    # the round is compared only when the pending record carries one
    if named is not None and (
        named[0] != module or (named[1] is not None and named[1] != round_idx)
    ):
        print(
            f"  (the answer given was for {named[0]} (round {named[1]}); this is "
            f"{module} (round {round_idx}) — NOT consumed, pausing here instead)"
        )
        ledger.append(
            "note",
            module=module,
            round_idx=round_idx,
            note=f"file-gate answer bound to {named[0]} (round {named[1]}) was "
            f"not applied to {module} (round {round_idx}); pausing for a fresh "
            f"answer — nothing was answered on the human's behalf",
            gate_answer_discarded=named[0],
        )
        _FILE_MODE["answer"] = None
        return None
    approved, note = bool(_FILE_MODE["answer"]), str(_FILE_MODE["note"] or "")
    _FILE_MODE["answer"] = None
    pend.delete()
    return approved, note


def _pending_gate(pend: Node) -> tuple[str, object] | None:
    """(module, round) of the gate that paused the run, or None when nothing is
    pending or the record is unreadable (an unreadable marker binds nothing)."""
    try:
        p = pend.get(None)
        if not isinstance(p, dict):
            return None
        return str(p.get("module")), p.get("round")
    except Exception:
        return None


def doc_link(path, label: str = "", *, base=None) -> str:
    """A document as a link a reader can open.

    On a TTY an OSC 8 hyperlink showing `label`; otherwise the plain absolute
    `file://` URL (terminals open it on cmd-click), because the file-gate
    driver, the `pending_gate` payload and the tests read captured output as
    text.

    A rendered document is a real file under `runs/<id>_reports/` and
    is linked as above. A `Node` — content of the run record, which no
    browser opens — is given as the command that prints it, `./run.sh show
    --run-id <id> <record key>` (`show_command`).
    """
    import sys as _sys

    if isinstance(path, Node):
        cmd = show_command(path)
        return f"{label}: {cmd}" if label else cmd
    q = Path(path)
    if not q.is_absolute():
        q = (Path(base) if base else Path.cwd()) / q
    url = q.resolve().as_uri() if q.exists() else f"file://{q.resolve()}"
    text = label or q.name
    try:
        tty = bool(_sys.stdout.isatty())
    except Exception:
        tty = False
    if tty:
        # OSC 8: ESC ] 8 ; ; <uri> ESC \ <text> ESC ] 8 ; ; ESC \
        return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"
    return f"{text}: {url}" if label else url


def show_command(node: Node) -> str:
    """The command that prints a part of the run record: what a reader
    is given for record content, since only rendered documents are files."""
    cmd = f"./run.sh show --run-id {node.store.run_id}"
    return f"{cmd} {node.key}" if node.key else cmd


def pending_path(root: Node) -> Node:
    """Where a file-mode gate's pending question lives: `root/pending_gate`."""
    return pending_node(root)


def _doc_path(doc) -> str:
    """What a gate card carries for a document: the file a browser opens for
    a rendered report, the `<record>::<key>` reference for record content."""
    if isinstance(doc, Node):
        return str(doc)
    return str(Path(str(doc)).resolve())


# Evidence lines a gate card prints before deferring to the document it names
# (REPORTING.md, "Prose budgets"); the `pending_gate` payload stays complete.
CARD_EVIDENCE_LINES = 12


# How a signature reads, per delivery mode; a policy answer reads
# `policy(<sha>)`, never as a human's. The mode comes from the ledger row `ask`
# wrote, so the signature and the audit trail cannot disagree.
_SIGNATURE = {
    "interactive": "human (at the terminal)",
    "file": "human (via the front end)",
    "auto": "auto-approved (test mode)",
}


def signature_of(row: dict | None) -> str:
    """How one ledger gate row reads as a signature: the one wording shared by
    the decision records, the ledger and ANALYSIS."""
    if not row:
        return "unrecorded"
    mode = str(row.get("mode") or "")
    if mode == "policy":
        return f"policy({row.get('policy_sha') or '?'})"
    if mode == "recorded":
        # a resume read the decision back; the record remembers the original
        return str(row.get("signed") or "recorded (earlier in this run)")
    return _SIGNATURE.get(mode, mode or "unrecorded")


def signature(ledger, module: str) -> str:
    """Who answered the most recent `module` gate, in words a reader can trust."""
    return signature_of(
        next(
            (
                e
                for e in reversed(ledger.entries())
                if e.get("event") == "human_gate" and e.get("module") == module
            ),
            None,
        )
    )


# How every gate reads its note (`gate_note`), printed under every card that
# lists forms.
FORM_RULE = (
    "(a form counts where it is written as one — `key: value`, `n=…`, or a "
    "bare word on its own line or between commas; a word inside a sentence is "
    "kept as your words and acts on nothing)"
)


def ask_once(
    ctx,
    decision: Node,
    question: str,
    lines: list[str],
    *,
    module: str,
    record_decline: bool = True,
    **kwargs,
) -> tuple[bool, str]:
    """`ask`, made durable: the answer is written to the record node
    `decision` (a `decisions/<gate>` key) before it is acted on, and a later
    pass reads it back instead of re-asking.

    Needed because the file-gate protocol resumes the run at each gate and a
    module's marker is written only after its gate is signed.

    `record_decline=True` records a no, so a resume neither re-asks nor re-pays
    for the work that produced the question (use it where an agent call
    precedes the gate); False leaves a no unrecorded, so the run can be resumed
    and answered differently. An approval is always recorded.
    """
    try:
        decided = decision.get(None)
    except Exception:  # an unreadable record is no record
        decided = None
    if decided is not None:
        if isinstance(decided, dict) and "approved" in decided:
            print(
                f"  ({module}: already answered "
                f"{'yes' if decided['approved'] else 'no'} — resumed from "
                f"{decision.key}, not re-asked)"
            )
            ctx.ledger.append(
                "human_gate",
                module=module,
                round_idx=ctx.round_idx,
                question=question,
                approved=bool(decided["approved"]),
                mode="recorded",
                note=str(decided.get("note", "")),
                signed=str(decided.get("signed") or ""),
            )
            return bool(decided["approved"]), str(decided.get("note", ""))
    approved, note = ask(
        question,
        lines,
        ledger=ctx.ledger,
        module=module,
        round_idx=ctx.round_idx,
        auto=ctx.auto,
        **kwargs,
    )
    if approved or record_decline:
        from octomod.result.autocommit import commit_ctx
        from octomod.result.records import DecisionRecord
        from octomod.result.write import write_record

        write_record(
            decision,
            DecisionRecord,
            {
                "approved": bool(approved),
                "note": note,
                "module": module,
                "round": ctx.round_idx,
                "at": datetime.datetime.now().isoformat(timespec="seconds"),
                # a signed scientific claim must say on whose authority
                "signed": signature(ctx.ledger, module),
            },
        )
        commit_ctx(ctx, why=f"decision:{module}", subject=decision.key)
    return approved, note


def _record_gap_lines(ledger) -> tuple[list[str], list[dict]]:
    """The card's lines for what the run's record lacks, and the gaps
    themselves (`completeness.card_lines`); nothing when the record is
    complete or cannot be reached from `ledger`."""
    root = _QUESTIONS["root"]
    if root is None:
        store = getattr(ledger, "store", None)
        if store is None:
            return [], []
        from octomod.result import node as tree

        root = tree.root(store)
    try:
        from octomod.result import completeness

        return completeness.card_lines(root)
    except Exception:  # noqa: BLE001 — a card is never lost to its gap lines
        return [], []


def ask(
    question: str,
    lines: list[str],
    *,
    ledger,
    module: str,
    round_idx: int = 0,
    auto: bool = False,
    intent: dict | None = None,
    where: str = "",
    consequences: tuple[str, str] | None = None,
    always_show: list[str] | None = None,
    note_forms: list[str] | tuple[str, ...] | None = None,
    documents: list[tuple[str, str]] | None = None,
    uncapped: list[str] | None = None,
) -> tuple[bool, str]:
    """Deliver one gate card and return (approved, note).

    `lines` is evidence and is capped on the card; `always_show` is part of
    the question (a menu, like the numbered engine questions) and is never
    capped. `uncapped` are lines of `lines` printed in their place whatever
    the cap (they do not count against it). The written payload carries every
    line in full. `documents` is
    [(label, absolute path)] — or a record `Node`, given as its `show`
    command — printed as links and carried in the `pending_gate` payload as
    paths, so a front end renders its own. `note_forms`
    is what the gate accepts in the note: printed under the consequences,
    carried in the payload, and reprinted by `?` at the prompt (not an answer).

    A policy answer is taken first; in file mode a stored answer for this gate
    is consumed, otherwise the payload is written and GatePending raised.
    Every answer is ledgered as a `human_gate` row.
    """
    print("\n" + "=" * 72)
    print(f"HUMAN GATE — {module}")
    print("=" * 72)
    if intent:
        # context card: a gate must be answerable without scrolling back
        print(f"  PROBLEM   {intent.get('question', '')}")
        print(
            f"  GOAL      {intent.get('inference_target', '')}"
            f"   ·   SYSTEM  {intent.get('system', '')}"
        )
    if where:
        print(f"  DECIDING  {where}")
    if intent or where:
        print("  " + "-" * 68)
    engine_questions: list[dict] = []
    question_lines: list[str] = []
    if _QUESTIONS["root"] is not None:
        from octomod.orchestration.interaction import questions as _q

        engine_questions = _q.pending(_QUESTIONS["root"])
        question_lines = _q.card_lines(_QUESTIONS["root"])
    # what the record lacks that a finished step should have left
    # (`completeness`): on every card, so the person sees it before deciding
    gap_lines, gaps = _record_gap_lines(ledger)
    gap_row = {"record_gaps": len(gaps)} if gaps else {}
    lines = list(lines) + list(always_show or []) + question_lines + gap_lines
    # only the printed evidence is capped; the menu, the engine questions and
    # the payload keep every line
    menu = list(always_show or [])
    evidence = [
        line
        for line in lines
        if line not in question_lines and line not in menu and line not in gap_lines
    ]
    keep = {line for line in uncapped or [] if line.strip()}
    shown = hidden = 0
    for line in evidence:
        if line in keep:
            print(f"  {line}")
        elif shown < CARD_EVIDENCE_LINES:
            print(f"  {line}")
            shown += 1
        else:
            hidden += 1
    if hidden:
        print(f"  … {hidden} more evidence lines — see the document this card names")
    for line in menu + question_lines + gap_lines:
        print(f"  {line}")
    forms = [str(x) for x in (note_forms or [])]
    docs = [(str(a), b, _doc_path(b)) for a, b in (documents or [])]
    if docs:
        print("  " + "-" * 68)
        for label, doc, path in docs:
            print(f"  {doc_link(doc if isinstance(doc, Node) else path, label)}")

    def _print_card_tail() -> None:
        print(f"\n  {question}")
        if consequences:
            print(f"    y → {consequences[0]}")
            print(f"    n → {consequences[1]}")
        if forms:
            print("    you may also type, after y or n:")
            for form in forms:
                print(f"      {form}")
            print(f"    {FORM_RULE}")

    _print_card_tail()

    def _settle(note_text: str) -> None:
        if engine_questions and _QUESTIONS["root"] is not None:
            from octomod.orchestration.interaction import questions as _q

            _q.mark_shown(
                _QUESTIONS["root"],
                module,
                note_text,
                ledger=ledger,
                round_idx=round_idx,
            )

    policy = _POLICY["policy"]
    if policy is not None and not auto:
        # before the delivery mode, so a policy-covered gate never pauses and
        # never consumes an answer stored for the gate that did pause
        answer = policy.decide(module, ledger, spec=None)
        if answer is not None:
            print(
                f"  -> answered by {policy.profile} policy "
                f"({policy.sha}, {answer.covered_by}): "
                f"{'yes' if answer.approved else 'no'}"
                + (f" ({answer.note})" if answer.note else "")
            )
            ledger.append(
                "human_gate",
                module=module,
                **gap_row,
                round_idx=round_idx,
                question=question,
                approved=bool(answer.approved),
                mode="policy",
                note=answer.note,
                policy_profile=policy.profile,
                policy_sha=policy.sha,
                covered_by=answer.covered_by,
            )
            _settle(answer.note)
            return bool(answer.approved), answer.note
        if policy.profile != "strict":
            # not covered, and the profile lets a human be asked: say so
            print(
                f"  ({policy.profile} policy does not answer this gate "
                f"— it is judgment-shaped; asking)"
            )

    if _FILE_MODE["enabled"] and not auto:
        pend = pending_path(_FILE_MODE["root"])
        taken = _take_stored_answer(pend, module, round_idx, ledger)
        if taken is not None:
            approved, note = taken
            print(
                f"  -> answered via front end: {'yes' if approved else 'no'}"
                + (f" ({note})" if note else "")
            )
            ledger.append(
                "human_gate",
                module=module,
                **gap_row,
                round_idx=round_idx,
                question=question,
                approved=approved,
                mode="file",
                note=note,
            )
            _settle(note)
            if approved:
                return True, note
            return False, note
        payload = {
            "module": module,
            "round": round_idx,
            "question": question,
            "lines": lines,
            "consequences": consequences,
            "intent": intent,
            "where": where,
            "engine_questions": engine_questions,
            # what the record lacks, for a front end to relay as such
            "record_gaps": gaps,
            # so a front end can offer the same options the terminal does
            "note_forms": forms,
            # how the note will be read, for a front end writing it
            **({"form_rule": FORM_RULE} if forms else {}),
            # PATHS, not rendered links: the front end makes its own
            "documents": [{"label": a, "path": b} for a, _doc, b in docs],
        }
        pend.put(payload)
        ledger.append(
            "gate_pending", module=module, round_idx=round_idx, question=question
        )
        raise GatePending(payload)

    if auto:
        # A --gate-note given with --auto-approve is a standing note for every
        # gate, so a token-free test can drive a path that needs an instruction;
        # the ledger still says mode="auto".
        standing = str(_AUTO_NOTE["note"] or "")
        from octomod.orchestration.interaction.policy import COST_GATE_SUFFIXES

        if module.endswith(COST_GATE_SUFFIXES):
            # An exhaustion gate's yes buys another paid call, and a static reply
            # fails the same way every time: auto mode grants the declared
            # allowance once, as the policy layer does, then answers n.
            cap = _AUTO_GRANTS["cap"]
            if cap is None:
                raise RuntimeError(
                    "--auto-approve reached an exhaustion gate with no grant cap "
                    "configured: the orchestrator sets it from retry.auto_grants, "
                    "and a caller that bypasses it may not answer this gate"
                )
            granted = sum(
                int(e.get("granted") or 0)
                for e in ledger.entries()
                if e.get("event") == "redraft_grant"
            )
            if granted >= cap:
                note = (
                    f"auto mode: grant cap ({cap}) reached — {granted} extra "
                    f"attempt(s) already granted; the failing check is on the card "
                    f"above and in the record's gate verdicts (`gates`)"
                )
                print(f"  -> {note}")
                ledger.append(
                    "human_gate",
                    module=module,
                    **gap_row,
                    round_idx=round_idx,
                    question=question,
                    approved=False,
                    mode="auto",
                    note=note,
                )
                _settle(standing)
                return False, note
            remaining = cap - granted
            rest = re.sub(r"\bn\s*=\s*\d+", "", standing).strip()
            note = (
                f"auto-approved (test mode); n={remaining} of the auto grant cap {cap}"
                + (f"; standing note: {rest}" if rest else "")
            )
            print(
                f"  -> auto-approved (test mode): n={remaining}, the auto grant cap is {cap}"
            )
            ledger.append(
                "human_gate",
                module=module,
                **gap_row,
                round_idx=round_idx,
                question=question,
                approved=True,
                mode="auto",
                note=note,
            )
            _settle(standing)
            return True, note
        note = (
            f"auto-approved (test mode); standing note: {standing}"
            if standing
            else "auto-approved (test mode)"
        )
        print(
            "  -> auto-approved (test mode)"
            + (f" with standing note: {standing}" if standing else "")
        )
        ledger.append(
            "human_gate",
            module=module,
            **gap_row,
            round_idx=round_idx,
            question=question,
            approved=True,
            mode="auto",
            note=note,
        )
        _settle(standing)
        return True, note

    prompt = "  [y]es / [n]o" + (
        ", optionally followed by a note ('?' for the options): "
        if forms
        else ", optionally followed by a note: "
    )
    from octomod.orchestration import timing as _timing

    # a person reading the card and typing is `human` time of the
    # account — the one wait inside a session that is not the engine's
    with _timing.span("human", f"gate:{module}", gate=module):
        approved, note = _read_answer(prompt, forms, _print_card_tail)
    ledger.append(
        "human_gate",
        module=module,
        **gap_row,
        round_idx=round_idx,
        question=question,
        approved=approved,
        mode="interactive",
        note=note.strip(),
    )
    _settle(note.strip())
    return approved, note.strip()


def _read_answer(prompt: str, forms, reprint) -> tuple[bool, str]:
    """The interactive loop: y/n plus an optional note; `?` reprints the card
    (`reprint`, the card's own closure)."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            continue
        # `?` reprints the card and is not an answer; checked before the y/n
        # parse, so asking for the options can never sign anything
        if raw in ("?", "??", "help", "h"):
            reprint()
            if not forms:
                print("    (this gate accepts no special note forms)")
            continue
        verdict, _, note = raw.partition(" ")
        verdict = verdict.strip(".,;:!").lower()
        if verdict in ("y", "yes"):
            approved = True
            break
        if verdict in ("n", "no"):
            approved = False
            break
        print("  answer must start with y or n ('?' for the options)")
    return approved, note
