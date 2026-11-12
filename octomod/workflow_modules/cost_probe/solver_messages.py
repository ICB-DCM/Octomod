"""What AMICI said while the cost probe's starts ran, counted by kind.

A failed start is a count on the budget card; why it failed is a sentence a
reader can act on. AMICI attaches a log item to every simulation's
`ReturnData.messages` and forwards each one to the `amici` logger, so the
probe's starts run under a handler that counts them by kind (`Capture`). A
start that failed is then read once more at its start point, with
`return_dict=True`, whose `rdatas` carry each condition's `status` and messages
(`at_point`): that attributes a kind to the start itself, and on an AMICI that
exposes no messages the status codes are classified instead, and the record
says so. Nothing here changes what the run does.

A compile or fit that raised is read here too: `failure_lines` collects what
the failure says (its cause chain and the compiler's error lines), and
`attribute_compile_error` names the role whose block it names, so the candidate
loop can send it back to that role before dropping the candidate.
"""

from __future__ import annotations

import logging
import re

import numpy as np

# (kind, pattern over the message text, label, what it means). Checked in
# order: a forward failure's text can carry its cause, and the cause wins.
CLASSES: tuple[tuple[str, str, str, str], ...] = (
    (
        "sigma_nonpositive",
        r"sigma\s*<=\s*0",
        "sigma at or below zero",
        "the noise formula reaches zero where the state does; a proportional "
        "noise model (sigma·X) needs a floor, e.g. sigma_abs + sigma_rel·X",
    ),
    (
        "overflow",
        r"\b(nan|inf|-inf)\b value|not finite|overflow",
        "a value that overflowed",
        "a start that overflowed: the bounds admit parameter values the model "
        "cannot integrate",
    ),
    (
        "equilibration",
        r"equilibration|steady.state",
        "pre-equilibration failure",
        "a steady state the conditions start from was not reached",
    ),
    (
        "forward_failure",
        r"forward (simulation|problem)|failed to integrate|maximum number of "
        r"steps|mxstep|error test|convergence test|right-hand side routine",
        "forward integration failure",
        "stiffness or an unbounded state: the integrator could not advance",
    ),
)
OTHER = ("other", "another AMICI message", "not a known kind; the example is verbatim")
_COMPILED = [(k, re.compile(p, re.I), lab, why) for k, p, lab, why in CLASSES]
EXAMPLES_KEPT = 2
EXAMPLE_CHARS = 160

# AMICI's return codes, by name, for an AMICI whose ReturnData carries no
# messages. NOT_RUN is a consequence (a condition skipped after an earlier one
# failed), never a cause, and is not counted.
_STATUS_KIND = {
    "AMICI_TOO_MUCH_WORK": "forward_failure",
    "AMICI_TOO_MUCH_ACC": "forward_failure",
    "AMICI_ERR_FAILURE": "forward_failure",
    "AMICI_CONV_FAILURE": "forward_failure",
    "AMICI_LSETUP_FAIL": "forward_failure",
    "AMICI_RHSFUNC_FAIL": "forward_failure",
    "AMICI_FIRST_RHSFUNC_ERR": "forward_failure",
    "AMICI_UNRECOVERABLE_ERROR": "forward_failure",
    "AMICI_MAX_TIME_EXCEEDED": "forward_failure",
    "AMICI_T_OVERFLOW": "forward_failure",
    "AMICI_NO_STEADY_STATE": "equilibration",
    "AMICI_ERROR": "other",
}
NOT_RUN = "AMICI_NOT_RUN"


def classify(text: str) -> str:
    """The kind of one AMICI message, or `other`."""
    for kind, pattern, _label, _why in _COMPILED:
        if pattern.search(str(text)):
            return kind
    return OTHER[0]


def _status_names() -> dict[int, str]:
    """{code: name} from the installed AMICI; the kinds' own names otherwise."""
    names: dict[int, str] = {}
    try:
        import amici.sim.sundials as sd

        for name in [*_STATUS_KIND, NOT_RUN]:
            value = getattr(sd, name, None)
            if isinstance(value, int):
                names.setdefault(int(value), name)
    except Exception:  # no AMICI: no names to read
        pass
    return names


def classify_status(code: int) -> str | None:
    """The kind of one failed status code; None for success and for not-run."""
    code = int(code)
    if code >= 0:
        return None
    name = _status_names().get(code)
    if name == NOT_RUN:
        return None
    return _STATUS_KIND.get(name or "", OTHER[0])


class Tally:
    """Messages counted by kind, with a few verbatim examples each."""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self.examples: dict[str, list[str]] = {}

    def add(self, text: str, kind: str | None = None) -> str:
        kind = kind or classify(text)
        self.counts[kind] = self.counts.get(kind, 0) + 1
        kept = self.examples.setdefault(kind, [])
        # compared as kept: two long messages that differ only past the cut
        # are one example, however many processes counted them
        text = " ".join(str(text).split())[:EXAMPLE_CHARS]
        if len(kept) < EXAMPLES_KEPT and text not in kept:
            kept.append(text)
        return kind

    def table(self) -> list[dict]:
        """One row per kind, most frequent first, known kinds before `other`."""
        meaning = {k: (lab, why) for k, _p, lab, why in CLASSES}
        meaning[OTHER[0]] = OTHER[1:]
        rows = [
            {
                "kind": k,
                "count": n,
                "label": meaning.get(k, OTHER[1:])[0],
                "sentence": meaning.get(k, OTHER[1:])[1],
                "examples": list(self.examples.get(k) or []),
            }
            for k, n in self.counts.items()
        ]
        return sorted(rows, key=lambda r: (r["kind"] == OTHER[0], -r["count"]))


class Capture(logging.Handler):
    """Counts the messages AMICI forwards to its logger while the block runs.

    Warnings and errors only: AMICI's debug items describe a simulation, they
    do not report a failure. Only this process's simulations reach it; a
    start dispatched to a worker process is counted there by the worker's own
    `Capture` (`start_engine`) and added back here with `absorb`.
    """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.tally = Tally()
        self.n_messages = 0
        self._logger = logging.getLogger("amici")

    def emit(self, record):
        try:
            self.tally.add(record.getMessage())
            self.n_messages += 1
        except Exception:  # a log line that cannot be read is not counted
            pass

    def __enter__(self):
        self._logger.addHandler(self)
        return self

    def __exit__(self, *exc):
        self._logger.removeHandler(self)
        return False

    def counted(self) -> dict:
        """What this capture counted, picklable: a worker returns it."""
        return {
            "counts": dict(self.tally.counts),
            "examples": {k: list(v) for k, v in self.tally.examples.items()},
            "n_messages": self.n_messages,
        }

    def absorb(self, counted: dict) -> None:
        """Add what another process's `Capture` counted (`counted()`)."""
        self.n_messages += int(counted.get("n_messages") or 0)
        examples = counted.get("examples") or {}
        for kind, n in (counted.get("counts") or {}).items():
            self.tally.counts[kind] = self.tally.counts.get(kind, 0) + int(n)
            kept = self.tally.examples.setdefault(kind, [])
            for text in examples.get(kind) or []:
                if len(kept) < EXAMPLES_KEPT and text not in kept:
                    kept.append(text)


def _field(rdata, name):
    try:
        return rdata[name]
    except Exception:
        return getattr(rdata, name, None)


def at_point(problem, x) -> dict:
    """One objective call at `x` (the FREE vector), read condition by condition.

    Returns {"conditions": [{"status", "messages": [text, ...]}], "has_messages"}:
    `has_messages` is False when this AMICI's ReturnData has no `messages`, and
    the caller then classifies the status codes. Never raises.
    """
    try:
        out = problem.objective(
            np.asarray(x, dtype=float), sensi_orders=(0,), return_dict=True
        )
    except Exception as exc:
        return {"conditions": [], "has_messages": False, "error": str(exc)}
    rows, has_messages = [], False
    for rdata in (out or {}).get("rdatas") or []:
        status = _field(rdata, "status")
        items = _field(rdata, "messages")
        if items is not None:
            has_messages = True
        texts = []
        for item in list(items or []):
            # AMICI's LogSeverity: error 0, warning 1, debug 2
            if int(getattr(item, "severity", 1)) > 1:
                continue
            texts.append(str(getattr(item, "message", item)))
        rows.append(
            {
                "status": int(status) if status is not None else None,
                "messages": texts,
            }
        )
    return {"conditions": rows, "has_messages": has_messages}


def _free(problem, x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    free = list(getattr(problem, "x_free_indices", range(len(x))))
    return x[free] if len(x) != len(free) else x


def probe_record(problem, starts, captured: Capture | None) -> dict:
    """The probe's failures and AMICI's messages, as the card and the ledger read them.

    `starts` are the probe's `OptimizerResult`s. The table counts every message
    the starts' simulations produced (`captured`); each failed start (a
    non-finite objective) is also read at its start point, which names its own
    kind and supplies the table when nothing was captured.
    """
    starts = list(starts or [])
    failed = [
        o
        for o in starts
        if getattr(o, "fval", None) is None or not np.isfinite(float(o.fval))
    ]
    tally = captured.tally if captured is not None else Tally()
    from_log = bool(captured is not None and captured.n_messages)
    per_start, fallback, any_messages = [], Tally(), False
    for o in failed:
        x0 = getattr(o, "x0", None)
        if x0 is None:
            per_start.append({"start": str(getattr(o, "id", "?")), "kinds": []})
            continue
        read = at_point(problem, _free(problem, x0))
        any_messages |= bool(read.get("has_messages"))
        kinds = []
        for cond in read["conditions"]:
            if cond["messages"]:
                kinds += [fallback.add(t) for t in cond["messages"]]
            elif not read.get("has_messages") and cond["status"] is not None:
                kind = classify_status(cond["status"])
                if kind:
                    kinds.append(fallback.add(f"AMICI status {cond['status']}", kind))
        per_start.append(
            {
                "start": str(getattr(o, "id", "?")),
                "kinds": sorted(set(kinds)),
                "statuses": [c["status"] for c in read["conditions"]],
            }
        )
    table = tally.table() if from_log else fallback.table()
    if from_log:
        source = (
            "AMICI's ReturnData messages, forwarded to its logger, over every "
            "simulation of the probe's starts"
        )
    elif failed and not any_messages:
        source = (
            "AMICI status codes at each failed start's start point: this AMICI "
            "exposes no messages, so the kinds are read from the codes"
        )
    elif failed:
        source = (
            "AMICI's ReturnData messages at each failed start's start point; "
            "none reached the logger while the starts ran"
        )
    else:
        source = "AMICI's messages over every simulation of the probe's starts: none"
    return {
        "available": True,
        "n_starts": len(starts),
        "n_failed": len(failed),
        "source": source,
        "messages_available": bool(from_log or any_messages or not failed),
        "table": table,
        "per_failed_start": per_start,
    }


def card_lines(rec: dict | None) -> list[str]:
    """For the budget card: failed starts, then what AMICI said, kind by kind."""
    if not rec or not rec.get("available"):
        return []
    table = rec.get("table") or []
    n, k = int(rec.get("n_starts") or 0), int(rec.get("n_failed") or 0)
    if not table and not k:
        return []
    out = [f"probe starts that failed: {k} of {n}"]
    if table:
        out[0] += " — what AMICI reported, by kind:"
        out += [f"  {r['count']}× {r['label']} — {r['sentence']}" for r in table[:5]]
        if len(table) > 5:
            out.append(
                f"  (+{len(table) - 5} more kinds in the candidate's `cost` "
                f"record, under solver_messages)"
            )
        if not rec.get("messages_available"):
            out.append(
                "  (read from AMICI status codes: this AMICI exposes no messages)"
            )
    return out


def ledger_note(rec: dict | None) -> str:
    """One line for the ledger: the counts by kind, or that AMICI said nothing."""
    if not rec or not rec.get("available"):
        return "solver messages over the probe: not read"
    table = rec.get("table") or []
    head = (
        f"solver messages over the probe's {rec.get('n_starts', 0)} starts "
        f"({rec.get('n_failed', 0)} failed): "
    )
    if not table:
        return head + "AMICI reported nothing"
    return head + "; ".join(f"{r['count']}× {r['label']}" for r in table)


# What names the observation model in the text of a failed compile or fit: its
# observables and their sigmas and noise formulas, AMICI's own words for a sigma
# that depends on a state, the sources AMICI generates for the observation
# function, and the ids PEtab gives the observation layer. A failure naming none
# of them is the model's (an SBML parameter without a value, a rate law the
# importer cannot read) and has no observation block to go back to.
OBSERVATION_MARKERS: tuple[str, ...] = (
    r"state-dependent observables",
    r"observable",
    r"sigma",
    r"noise",
    r"(?<![A-Za-z0-9])obs_[A-Za-z0-9_]",
    r"(?<![A-Za-z0-9])(?:y|dydx|dydp|Jy|dJydy|dJydsigma)\.(?:cpp|h)\b",
)
_OBSERVATION = [re.compile(p, re.I) for p in OBSERVATION_MARKERS]
FAILURE_LINES_KEPT = 12
FAILURE_LINE_CHARS = 300
# a path in a compiler line names the build folder, not the defect
_PATH = re.compile(r"(?:/[^\s/:'\"]+)+/([^\s/:'\"]+)")
_ERROR_LINE = re.compile(r"\berrors?\b", re.I)


def attribute_compile_error(text: str) -> str | None:
    """The role whose block a compile or fit failure names, or None.

    `observation` when the text names the observation layer; None
    otherwise, and the failure stays the candidate's own defect."""
    text = str(text or "")
    return "observation" if any(p.search(text) for p in _OBSERVATION) else None


def failure_lines(exc: BaseException) -> list[str]:
    """The lines a compile or fit failure carries, as a reader needs them.

    Each exception in the chain with its type, because the SBML importer wraps
    the cause (`State-dependent observables are not supported, …`) in a message
    of its own; and the compiler's error lines, because a failed build carries
    them in the process output rather than in the exception's message. Paths
    are cut to the file name. Capped at `FAILURE_LINES_KEPT` lines."""
    lines: list[str] = []
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        lines.append(f"{type(e).__name__}: {e}")
        out = getattr(e, "output", None) or getattr(e, "stderr", None)
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(out, str):
            lines += [ln for ln in out.splitlines() if _ERROR_LINE.search(ln)]
        e = e.__cause__ or (None if e.__suppress_context__ else e.__context__)
    kept = []
    for ln in lines:
        ln = _PATH.sub(r"\1", " ".join(str(ln).split()))
        if ln and ln not in kept:
            kept.append(ln[:FAILURE_LINE_CHARS])
    return kept[:FAILURE_LINES_KEPT]
