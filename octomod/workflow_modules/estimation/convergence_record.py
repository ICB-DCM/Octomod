"""What the human decided about convergence, read back from the ledger.

Any claim resting on a fit whose convergence was ACCEPTED rather than
demonstrated has to carry that caveat. Accepts are scoped per candidate: each
candidate has its own fit, so one candidate's accept must not attach to the
claims of candidates that converged cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A budget-gate pre-declaration covers a shallow plateau and a loose gradient,
# never integration failures: whoever waived plateaus in advance has not been
# shown a crash rate.
PREDECLARABLE = ("estimation_waterfall_plateau", "estimation_gradient_norm")
NOT_PREDECLARABLE = ("estimation_integration_failures",)


@dataclass
class ConvergenceAccept:
    """One candidate's accepted-not-demonstrated convergence."""

    candidate: str | None
    reason: str
    failed_checks: list[str] = field(default_factory=list)
    measured: list[dict] = field(default_factory=list)
    pre_declared: bool = False

    @property
    def key(self) -> str:
        return self.candidate or "model"

    def headline(self) -> str:
        how = (
            "PRE-DECLARED at the budget gate, before the fit ran"
            if self.pre_declared
            else "accepted at the convergence gate, after seeing the numbers"
        )
        return f"convergence {how}"

    def check_lines(self) -> list[str]:
        """Each failed check as `id: measured X against threshold Y`."""
        by_id = {str(m.get("gate_id")): m for m in self.measured}
        out = []
        for gid in self.failed_checks:
            m = by_id.get(gid, {})
            val, thr = m.get("value"), m.get("threshold")
            if val is None and thr is None:
                out.append(f"{gid}: failed (no measurement recorded)")
            else:
                out.append(f"{gid}: measured {val} against threshold {thr}")
        return out


def accepts_by_candidate(ledger_entries) -> dict[str, ConvergenceAccept]:
    """Every convergence accept in this run, keyed by candidate.

    `ledger_entries` is an iterable of ledger dicts — the report already holds
    them, so this does no IO. A later accept for the same candidate replaces an
    earlier one: the gate re-asks after a refit, and the last answer is the one
    the fit was kept under.
    """
    out: dict[str, ConvergenceAccept] = {}
    for e in ledger_entries or []:
        if str(e.get("convergence", "")) not in (
            "accepted-by-human",
            "pre-declared-by-human",
        ):
            continue
        rec = ConvergenceAccept(
            candidate=e.get("candidate"),
            reason=str(e.get("accept_reason") or e.get("note") or "").strip(),
            failed_checks=list(e.get("failed_checks") or []),
            measured=list(e.get("failed_measured") or []),
            pre_declared=str(e.get("convergence")) == "pre-declared-by-human",
        )
        out[rec.key] = rec
    return out


def caveat_line(rec: ConvergenceAccept) -> str:
    """The sentence every downstream claim on this fit has to carry."""
    return (
        f"Convergence for {rec.key} was {'pre-' if rec.pre_declared else ''}"
        f"ACCEPTED, not demonstrated: "
        + "; ".join(rec.check_lines())
        + f". Reason given: {rec.reason or '(none recorded)'}. "
        "Every claim below rests on that fit."
    )


def measured_from_results(results) -> list[dict]:
    """The failed gates' own numbers, for the ledger row.

    Recorded at accept time because a refit rewrites `gates/<id>.json`.
    """
    return [
        {
            "gate_id": r.gate_id,
            "tier": r.tier,
            "value": r.value,
            "threshold": r.threshold,
            "detail": r.detail,
        }
        for r in results
        if not r.passed and r.blocking
    ]
