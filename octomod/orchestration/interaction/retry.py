"""Redraft dossiers: every prior attempt of a role, as the next call sees it.

`AttemptHistory` keeps each attempt's gate failures and an engine-derived draft
summary (entity counts, failing lines, change versus the previous attempt),
size-capped and persisted in the record beside the agent call
(`agent_calls/<role>/dossier`) so a resume carries it.
Localized failures ask for a minimal edit, whose collateral-change ratio is
recorded but never blocks. `exhaustion_gate` asks the human for more attempts.
"""

from __future__ import annotations

import difflib
import json
import re

_RID = re.compile(r"\b(J\d+|R\d+|v\d+|r\d+)\b")
_QUOTED = re.compile(r"'([A-Za-z_]\w*)'")


def dossier_of(ctx, role: str):
    """The record node of `role`'s attempt dossier in the current round."""
    return ctx.agent_calls.child(role) / "dossier"


class AttemptHistory:
    """Every prior attempt of one role in one module, plus the extra attempts a
    human granted at the exhaustion gate.

    Grants are persisted because the exhaustion gate pauses: on resume the
    engine must know the grant happened, or the gate is re-asked and its answer
    consumed by whichever gate the resume reaches first.
    """

    def __init__(self, node, cap_chars: int = 8000):
        """`node`: where the dossier lives in the record — the role's
        `agent_calls/<role>/dossier` (`dossier_of(ctx, role)`)."""
        self.node = node
        self.cap_chars = cap_chars
        self.attempts: list[dict] = []
        self.grants: list[dict] = []
        # The attempt whose draft passed the gate ladder, or None. The dossier
        # lists failures only, so without this a failed attempt on disk reads
        # as "the last draft failed" even after a later draft passed.
        self.passed_attempt: int | None = None
        # False for a dossier without a `passed_attempt` field (older format);
        # the module may backfill it from the artifacts only a passed draft writes
        self.has_pass_record = True
        try:
            data = node.get(None)
            if isinstance(data, dict):
                self.attempts = list(data.get("attempts", []))
                self.grants = list(data.get("grants", []))
                self.passed_attempt = data.get("passed_attempt")
                self.has_pass_record = "passed_attempt" in data
        except Exception:
            self.attempts = []
            self.grants = []
            self.passed_attempt = None

    @property
    def grants_total(self) -> int:
        return sum(int(g.get("granted") or 0) for g in self.grants)

    def add_grant(self, n: int, why: str | None = None) -> None:
        """`n` further attempts; `why` names who granted them when it is not
        the exhaustion gate (a person's redraft, the engine's search)."""
        import datetime

        grant = {
            "granted": int(n),
            "after_attempts": len(self.attempts),
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if why:
            grant["why"] = str(why)
        self.grants.append(grant)
        self._persist()

    # ------------------------------------------------------------ recording
    def add(
        self,
        failures: list[str],
        draft_summary: dict | None = None,
        previous_text: str | None = None,
        current_text: str | None = None,
        implicated: set[str] | None = None,
        extra: dict | None = None,
    ) -> dict:
        entry = {
            "attempt": len(self.attempts) + 1,
            "gate_failures": [str(f) for f in failures],
            "draft_summary": draft_summary or {},
        }
        # what the module records beside the failures (what the draft named
        # missing, how the engine answered it)
        entry.update(extra or {})
        if previous_text is not None and current_text is not None:
            entry["what_changed_vs_previous"] = diff_summary(
                previous_text, current_text, implicated or set()
            )
        self.attempts.append(entry)
        # a new failure means the draft on disk is a failed one again
        self.passed_attempt = None
        self._persist()
        return entry

    def mark_passed(self) -> None:
        """The draft just produced passed its ladder: the cached reply is the
        one a resume may reuse, however many attempts failed before it."""
        self.passed_attempt = len(self.attempts) + 1
        self._persist()

    def clear_passed(self) -> None:
        """A fresh agent call is about to replace the cached reply."""
        self.passed_attempt = None
        self._persist()

    @property
    def last_draft_failed(self) -> bool:
        """True when the newest draft in the record is one that failed its gates —
        the only case minimal-repair mode is about."""
        return bool(self.attempts) and self.passed_attempt is None

    def _persist(self) -> None:
        self.has_pass_record = True
        self.node.put(
            {
                "attempts": self.attempts,
                "grants": self.grants,
                "passed_attempt": self.passed_attempt,
            }
        )

    def __len__(self) -> int:
        return len(self.attempts)

    # ------------------------------------------------------------ the prompt
    def as_context(self) -> dict:
        """Size-capped: every attempt keeps its one-line verdicts; the oldest
        attempts lose their details first."""
        out = [dict(a) for a in self.attempts]
        text = json.dumps(out, default=str)
        i = 0
        while len(text) > self.cap_chars and i < len(out):
            out[i] = {
                "attempt": out[i]["attempt"],
                "gate_failures": [f[:160] for f in out[i]["gate_failures"]],
                "details_truncated": True,
            }
            text = json.dumps(out, default=str)
            i += 1
        return {
            "attempts": out,
            "instruction": (
                "Every attempt so far, oldest first, with its gate failures and what "
                "each draft looked like. Do not re-propose what an earlier attempt "
                "already tried; fix the failures named and keep everything that "
                "passed. If `minimal_repair` is present, return a MINIMAL edit of "
                "the previous draft — the engine measures how much you changed "
                "beyond what the failures implicated."
            ),
        }


# ------------------------------------------------------------ summaries


def antimony_summary(antimony: str, failures: list[str]) -> dict:
    """Entity counts + the failing lines verbatim (lines mentioning any reaction
    id or quoted symbol that a failure names)."""
    lines = antimony.splitlines()
    n_species = sum(1 for line in lines if line.strip().startswith("species "))
    n_reactions = sum(1 for line in lines if re.match(r"\s*\w+\s*:\s*.*->", line))
    n_params = sum(
        1 for line in lines if re.match(r"\s*[A-Za-z_]\w*\s*=\s*[-\d.]", line)
    )
    names = implicated_names(failures)
    failing = [
        line.strip()
        for line in lines
        if any(re.search(rf"\b{re.escape(nm)}\b", line) for nm in names)
    ][:12]
    return {
        "n_species": n_species,
        "n_reactions": n_reactions,
        "n_parameters": n_params,
        "implicated": sorted(names),
        "failing_lines": failing,
    }


def implicated_names(failures: list[str]) -> set[str]:
    names: set[str] = set()
    for f in failures:
        names |= set(_RID.findall(str(f)))
        names |= set(_QUOTED.findall(str(f)))
        for m in re.finditer(
            r"(?:reaction|species|parameter|symbol)s?\s+([A-Za-z_]\w*)", str(f)
        ):
            names.add(m.group(1))
    return {n for n in names if n not in {"the", "a", "an"}}


def localized(failures: list[str]) -> bool:
    """Failures that name reactions, symbols or species are localized — the
    case for a minimal repair rather than a re-roll."""
    return bool(failures) and bool(implicated_names(failures))


def diff_summary(previous: str, current: str, implicated: set[str]) -> dict:
    """Lines changed between two drafts, and how many of the changed lines the
    failures did NOT implicate (collateral). Advisory: a legitimate fix may
    propagate; the number is reported so drift toward re-rolling is visible."""
    prev_lines = [line.strip() for line in previous.splitlines() if line.strip()]
    cur_lines = [line.strip() for line in current.splitlines() if line.strip()]
    changed = [line for line in cur_lines if line not in set(prev_lines)] + [
        line for line in prev_lines if line not in set(cur_lines)
    ]
    collateral = [
        line
        for line in changed
        if not any(re.search(rf"\b{re.escape(n)}\b", line) for n in implicated)
    ]
    ratio = round(len(collateral) / len(changed), 3) if changed else 0.0
    sim = difflib.SequenceMatcher(None, prev_lines, cur_lines).ratio()
    return {
        "n_lines_changed": len(changed),
        "n_collateral_lines": len(collateral),
        "collateral_change_ratio": ratio,
        "similarity": round(sim, 3),
        "changed_lines_sample": changed[:8],
    }


# ------------------------------------------------------------ exhaustion gate


def exhaustion_gate(
    ctx,
    module: str,
    role: str,
    history: AttemptHistory,
    budget: int,
    extra_lines: list[str] | None = None,
    set_floor=None,
) -> int:
    """The redraft budget is spent. Ask the human for N more attempts (priced
    with the measured per-call cost so far) or stop. Returns the number of
    extra attempts granted (0 = stop). The grant is ledgered. `extra_lines`
    go on the card before the price: what the engine already tried beyond the
    attempts (the searches it ran, the floor it lowered). With `set_floor`
    (a callable taking the band as written, returning None when it acted or
    the reason it did not), the card also takes `floor: <band|none>`: the
    round's floor as the person's, applied before the grant."""
    from octomod.orchestration.interaction import humangate

    calls = [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "agent_call" and e.get("role") == role
    ]
    costs = [
        c.get("cost_usd") for c in calls if isinstance(c.get("cost_usd"), (int, float))
    ]
    per_call = (sum(costs) / len(costs)) if costs else None
    durations = [
        c.get("duration_s")
        for c in calls
        if isinstance(c.get("duration_s"), (int, float))
    ]
    lines = [f"{role}: {len(history)} attempt(s) failed their gates (budget {budget})"]
    for a in history.attempts:
        lines.append(
            f"  attempt {a['attempt']}: "
            + " | ".join(f[:110] for f in a["gate_failures"][:3])
        )
    lines += list(extra_lines or [])
    lines.append(
        f"measured cost so far: {len(calls)} call(s)"
        + (
            f", ${sum(costs):.2f} total, ${per_call:.2f} per call"
            if per_call is not None
            else ", cost not recorded (stub backend)"
        )
        + (f", ~{sum(durations) / len(durations):.0f}s per call" if durations else "")
    )
    lines.append(
        "answer 'y n=<N>' to grant N more attempts (default 1), 'n' to stop"
        + ("; 'y floor: <band|none>' sets the round's floor" if set_floor else "")
    )
    approved, note = humangate.ask(
        f"Redraft budget exhausted for {role}. Grant more attempts?",
        lines,
        ledger=ctx.ledger,
        module=f"{module}_redraft_budget",
        round_idx=ctx.round_idx,
        auto=ctx.auto,
        intent=ctx.intent,
        where="a cost boundary — every extra attempt is another agent call",
        consequences=(
            "the agent is re-asked, with the full dossier of every attempt " "so far",
            "the run stops here; the failing checks are in the record's gates",
        ),
        note_forms=[
            "n=<attempts>  grant that many further attempts (default 1)",
            "(nothing)     grant one further attempt",
        ]
        + (
            [
                "floor: <band|none>  the round's floor, as yours: the round's "
                "searches are read again at it and the agent is asked again"
            ]
            if set_floor
            else []
        ),
    )
    if not approved:
        return 0
    from octomod.orchestration.interaction import gate_note

    # a whole `n=` token, so "run=3" does not read as n=3
    asked = gate_note.key_int(note, "n")
    n = max(1, min(asked, 10)) if asked is not None else 1
    reading = gate_note.Reading(read={"n": n} if asked is not None else {})
    words = gate_note.key_list(note, "floor") if set_floor else None
    if words:
        why = set_floor(words[0])
        if why:
            reading.unread[f"floor: {words[0]}"] = why
        else:
            reading.read["floor"] = words[0]
    gate_note.report(
        reading,
        note,
        ledger=ctx.ledger,
        module=module,
        round_idx=ctx.round_idx,
    )
    # persisted before anything is spent, so a resume reads the grant rather
    # than re-asking or letting the next gate take this gate's answer
    history.add_grant(n)
    ctx.ledger.append(
        "redraft_grant",
        module=module,
        round_idx=ctx.round_idx,
        role=role,
        granted=n,
        attempts_so_far=len(history),
        grants_total=history.grants_total,
    )
    return n
