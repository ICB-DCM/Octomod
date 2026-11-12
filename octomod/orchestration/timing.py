"""Where the wall clock went: every second of a run, attributed.

A run's wall time is what a person waits for, and the ledger's own rows do
not say what it was spent on: `agent_call` rows carry a duration, the cost
probe carries its own, and the rest — compiling, profiling, rendering, the
engine between them, a human reading a gate card — is nowhere. This module
makes the accounting close: the run's wall time equals the sum of the values
in the record's `timing` group, by construction.

Three sources, one table:

  * every ledger row carries `t`, the epoch time to the millisecond (the
    `ts` string is to the second and stays for reading); the boundary rows
    (`run_start`, `run_end`, `gate_pending`) also carry `cpu_s`, the
    process's CPU so far;
  * a `span` row is appended when a timed block ends — `span(category, name)`
    around a block, `phase(name)` around a module's `run` — with `t0`, `t1`,
    `wall_s`, `cpu_s` (the process AND its finished children: the
    multistart's workers, `claude -p`, the compiler), its `depth` and what
    its children cost (`n_children`, `children_wall_s`, `children_cpu_s`),
    known at runtime from the stack of open spans rather than inferred from
    times. Categories: `agent` (one LLM call: the CLI's wall, split into
    `api_s`, time inside the model API, and `tools_s`, the rest of the CLI's
    own clock), `compute` (compile, cost probe, multistart, comparison,
    profiles, holdout, identifiability, …), `render` (documents), `human`
    (an interactive gate wait), `io` (fetching literature), `record` (the
    record's own checkpoints and compaction), `module` (a whole module). A
    compute span also carries its WORK — `n_starts`, `n_fval`, `n_grad`,
    `n_points`, the `n_procs` it ran on — because time per unit of work is
    what compares across machines and wall time is not;
  * the sessions: a run is one or more PROCESSES — every file-gate pause ends
    one and the answer starts the next — bounded by `run_start` and
    `run_end`/`gate_pending` rows. The gap between two sessions is the time a
    human (or the front end) took at the gate: `waiting_for_human_s`. A
    session that lost its end row (killed) ends at its last row, and the
    gap after it is `unaccounted_s`, not a human's.

The account (`summarize`):

    run_wall_s     = Σ sessions.wall_s + waiting_for_human_s + unaccounted_s
    session.wall_s = Σ self time of its non-module spans + session.engine_s
    session.cpu_s  = Σ self CPU of its non-module spans + session.engine_cpu_s

A span's SELF time is its wall minus its children's: a model-averaged
holdout that contains per-candidate holdouts contributes only its own
overhead, and each holdout its own time — nothing counts twice. A module's
self time is the engine's (`engine_s`: reading and writing the record,
gates, prompts, printing between the timed blocks). `residual_s` is what the
account could not explain: the unaccounted gap after a killed session.

Comparing across machines. Wall time belongs to one machine on one day: a
multistart on 22 cores is a fifth of the same multistart on 4. So beside
every wall there is a CPU time (independent of how many cores were free and
of the load, not of the CPU's speed), a `parallelism` (cpu / wall: how many
cores the block actually kept busy), the work it did, and the cost per unit
of work (`cpu_s_per_start`, `cpu_s_per_fval`, `cpu_s_per_point`) — and the
account says what it ran on (`machine`: CPU model and count, memory, the
load average at the time; no hostname, the record is shared). Agent `api_s`
is the provider's time and compares across machines but not across models
or days.

Rows that would land AFTER a session's end row (`run_end`, `gate_pending`
must stay the last rows a reader finds: the front end and `suplit` read them
there) are kept in memory and written with the `timing` group, flagged
`late`; the session they belong to is extended over them, and that end is
carried forward so a resumed run's account agrees with the paused one.

Nothing here decides anything, and nothing here may stop a run: a span whose
row cannot be written is lost, not raised. It is a number for a person, and
for the question the next design round asks first: what would make this
faster?
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import functools
import os
import time
from collections.abc import Iterator
from typing import Any

# ------------------------------------------------------------- the binding
# The orchestrator attaches its RunContext for the length of the process, so a
# timed block deep in a library (`estimation.run_multistart`) can find the
# ledger, the round and the candidate at the moment it ends. Unattached (a
# unit test, a tool), a span is a plain timer that records nothing.
_CTX: Any = None
_MODULE: list[str] = []  # the stack of open module names (outermost first)
_OPEN: list[dict] = []  # the stack of open spans: parentage at runtime
_LATE: list[dict] = []  # spans that ended after the session's end row

CATEGORIES = ("agent", "compute", "render", "human", "io", "record", "module")
END_EVENTS = ("run_end", "gate_pending")
# the work a compute span may report; summed per block, except n_procs (max)
UNITS = ("n_starts", "n_fval", "n_grad", "n_hess", "n_points", "n_profiles")
# keys a span's detail may not overwrite in its ledger row
# (`module` is a detail `phase` passes on purpose; the span consumes it)
_RESERVED = frozenset({"ts", "t", "round", "event", "category", "name", "t0", "t1"})


def attach(ctx) -> None:
    global _CTX
    _CTX = ctx
    _MODULE.clear()
    _OPEN.clear()
    _LATE.clear()


def detach() -> None:
    global _CTX
    _CTX = None
    _MODULE.clear()
    _OPEN.clear()


def now() -> float:
    return time.time()


def cpu_now() -> float:
    """CPU seconds this process AND its finished children have used (user +
    system): the multistart's workers, `claude -p`, AMICI's compiler. Wall
    time is what a person waits; CPU time is what the work cost, and it is
    the number that survives a change of core count or machine load.
    `os.times` rather than `resource`, so the first ledger row can be written
    on any platform."""
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


def machine() -> dict:
    """What this ran on: enough to read a wall time from another machine.
    Never a normalisation — a fingerprint beside the numbers. No hostname:
    the record is what people share."""
    import platform
    import subprocess

    out: dict = {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "cpu_model": None,
        "memory_gb": None,
        "load_avg_1m": None,
    }
    try:
        with open("/proc/cpuinfo") as fh:
            for line in fh:
                if line.lower().startswith("model name"):
                    out["cpu_model"] = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    if not out["cpu_model"] and platform.system() == "Darwin":
        try:
            out["cpu_model"] = (
                subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                ).stdout.strip()
                or None
            )
        except (OSError, subprocess.SubprocessError):
            pass
    if not out["cpu_model"]:
        out["cpu_model"] = platform.processor() or None
    try:
        pages, page = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
        out["memory_gb"] = round(pages * page / 1e9, 1)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        out["load_avg_1m"] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass
    return out


def _session_ended(ledger) -> bool:
    """True once the session's last row is on the ledger (`run_end` or
    `gate_pending`): anything timed after that must not follow it there."""
    try:
        rows = ledger.entries()
    except (
        Exception
    ):  # noqa: BLE001 - a ledger that cannot be read is not ours to append to
        return True
    # the most recent session boundary decides: a `note` the engine writes
    # after `run_end` (the tried-models archive) does not reopen the session
    for row in reversed(rows):
        ev = row.get("event")
        if ev in END_EVENTS:
            return True
        if ev == "run_start":
            return False
    return False


def _record(row: dict) -> None:
    """Append the span row — or keep it for the group when the session has
    ended. NEVER raises: a lost span is a lost reading, and a record that
    was just restored from its checkpoint (`store.recovered`) is not written
    into by the account either (the process stops)."""
    ctx = _CTX
    if ctx is None:
        return
    try:
        row = {
            "round": ctx.round_idx,
            "candidate": ctx.candidate,
            **row,
        }
        if getattr(ctx.store, "recovered", False) or _session_ended(ctx.ledger):
            row["late"] = True
            _LATE.append(row)
            return
        payload = {
            k: v
            for k, v in row.items()
            if k not in ("round", "module") and v is not None
        }
        ctx.ledger.append(
            "span", module=row.get("module") or "", round_idx=row["round"], **payload
        )
    except Exception as e:  # noqa: BLE001 - a reading, never a reason to stop
        print(f"  ⚑ timing span not recorded: {type(e).__name__}: {str(e)[:120]}")


@contextlib.contextmanager
def span(category: str, name: str, **detail) -> Iterator[dict]:
    """Time a block; on exit append one `span` row (also when it raised —
    `ok: false` — because a module that paused at a gate or died in a compile
    still spent that time). The yielded dict takes late detail
    (`with span("agent", role) as s: …; s["api_s"] = …`; a compute block
    adds its work units the same way). Parentage is the stack of open spans,
    so a parent knows what its children cost when it closes."""
    if category not in CATEGORIES:
        raise ValueError(f"unknown timing category {category!r}; one of {CATEGORIES}")
    bad = _RESERVED.intersection(detail)
    if bad:
        raise ValueError(f"span detail may not use the row's own keys: {sorted(bad)}")
    t0 = time.time()
    p0 = time.perf_counter()
    c0 = cpu_now()
    info: dict = dict(detail)
    frame = {"n_children": 0, "children_wall_s": 0.0, "children_cpu_s": 0.0}
    _OPEN.append(frame)
    ok = True
    try:
        yield info
    except BaseException:
        ok = False
        raise
    finally:
        _OPEN.pop()
        wall = time.perf_counter() - p0
        cpu = max(0.0, cpu_now() - c0)
        if _OPEN:  # tell the parent what this child cost
            parent = _OPEN[-1]
            parent["n_children"] += 1
            parent["children_wall_s"] += wall
            parent["children_cpu_s"] += cpu
        module = info.pop("module", None) or (_MODULE[-1] if _MODULE else "")
        _record(
            {
                "category": category,
                "name": name,
                "module": module,
                "t0": round(t0, 3),
                "t1": round(t0 + wall, 3),
                "wall_s": round(wall, 3),
                # the process and its finished children: workers, subprocesses
                "cpu_s": round(cpu, 3),
                "depth": len(_OPEN),
                "n_children": frame["n_children"],
                "children_wall_s": round(frame["children_wall_s"], 3),
                "children_cpu_s": round(frame["children_cpu_s"], 3),
                "ok": ok,
                **{k: v for k, v in info.items() if v is not None},
            }
        )


def phase(name: str, category: str = "module"):
    """Decorate a module's `run` (or an orchestrator step) as one span named
    `name`. Only the OUTERMOST entry of a name is timed: a refit re-enters
    `estimation.run` from inside itself, and that is one module, not two."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            if name in _MODULE:
                return fn(*args, **kwargs)
            _MODULE.append(name)
            try:
                with span(category, name, module=name):
                    return fn(*args, **kwargs)
            finally:
                _MODULE.pop()

        return wrapped

    return deco


def timed(category: str, name: str, **detail):
    """Decorate a function as one `category` span named `name` (a compute
    block, a render), inside whatever module is open."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            with span(category, name, **detail):
                return fn(*args, **kwargs)

        return wrapped

    return deco


def current_module() -> str:
    return _MODULE[-1] if _MODULE else ""


# ------------------------------------------------------------ the account
def _t(row: dict) -> float | None:
    """A row's time as a float: `t` when the row has one, else its `ts`
    string to the second (legacy records, whose rows carry no `t`)."""
    t = row.get("t")
    if isinstance(t, (int, float)):
        return float(t)
    ts = row.get("ts")
    if isinstance(ts, str) and ts:
        try:
            return _dt.datetime.fromisoformat(ts).timestamp()
        except ValueError:
            return None
    return None


def _r(x: float) -> float:
    return round(float(x), 3) + 0.0


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and v == v else None


def sessions_of(
    rows: list[dict],
    *,
    ended_at: float | None = None,
    cpu_at_end: float | None = None,
    ends: dict[int, float] | None = None,
) -> list[dict]:
    """The processes a run consisted of, from its `run_start` and end rows.

    `ended_at` (and `cpu_at_end`) close a session still open in the ledger
    (the one writing the account, whose end row is not there yet — or a
    killed one, whose end is then its last row and is said to be). `ends`
    are the effective ends an earlier account recorded (a paused session
    runs on past its `gate_pending` row: the checkpoint, the account); they
    are honoured so the final account agrees with the one at the pause."""
    out: list[dict] = []
    cur: dict | None = None
    last_t: float | None = None
    for row in rows:
        t = _t(row)
        if t is None:
            continue
        ev = row.get("event")
        if ev == "run_start":
            if cur is not None:  # a session with no end row: killed
                cur.update(ended=last_t, ended_by="killed")
                out.append(cur)
            startup = _num(row.get("startup_s")) or 0.0
            started = t - startup
            if out and out[-1]["ended"] is not None:
                # a resume launched while the paused process was still
                # checkpointing: no overlap, the earlier session owns the time
                started = max(started, out[-1]["ended"])
            cur = {
                "index": len(out),
                # the process began `startup_s` before its first row (imports,
                # the spec, the guard): that is wall time too
                "started": started,
                "startup_s": _r(startup),
                "ended": None,
                "ended_by": None,
                # the process's CPU at its end row is the session's CPU: the
                # count began with the process
                "cpu_s": None,
            }
        elif ev in END_EVENTS and cur is not None:
            cur.update(
                ended=t,
                ended_by=(
                    ev if ev != "run_end" else f"run_end:{row.get('outcome') or ''}"
                ),
                cpu_s=_num(row.get("cpu_s")),
            )
            out.append(cur)
            cur = None
        last_t = t
    if cur is not None:
        if ended_at is not None:
            cur.update(
                ended=max(ended_at, cur["started"]), ended_by="open", cpu_s=cpu_at_end
            )
        else:
            cur.update(ended=last_t, ended_by="killed")
        out.append(cur)
    for s in out:
        stored = (ends or {}).get(s["index"])
        if stored is not None and s["ended"] is not None and stored > s["ended"]:
            s["ended"] = float(stored)
    for a, b in zip(out, out[1:], strict=False):
        if a["ended"] is not None and a["ended"] > b["started"]:
            b["started"] = a["ended"]
    for s in out:
        s["wall_s"] = _r(max(0.0, (s["ended"] or s["started"]) - s["started"]))
        if s["cpu_s"] is not None:
            s["cpu_s"] = _r(s["cpu_s"])
        s["started_iso"] = _dt.datetime.fromtimestamp(s["started"]).isoformat(
            timespec="milliseconds"
        )
    return out


def _spans_of(rows: list[dict]) -> list[dict]:
    return [
        dict(r)
        for r in rows
        if r.get("event") == "span" and isinstance(r.get("t0"), (int, float))
    ]


def _self_times(spans: list[dict]) -> None:
    """What each span contributes: its wall and CPU minus its children's.
    Known from the row when it was written by this module (`n_children`,
    `children_*`); for legacy rows without them, inferred from containment
    (a span containing another contributes nothing — the leaf rule).
    A module span never contributes: its self time is the engine's."""
    for a in spans:
        a["leaf"] = a.get("n_children", 0) == 0 and a.get("category") != "module"
        if a.get("category") == "module":
            a["self_wall_s"] = 0.0
            a["self_cpu_s"] = 0.0
            continue
        if "children_wall_s" in a:
            a["self_wall_s"] = _r(
                max(0.0, float(a.get("wall_s") or 0.0) - float(a["children_wall_s"]))
            )
            a["self_cpu_s"] = _r(
                max(0.0, float(a.get("cpu_s") or 0.0) - float(a["children_cpu_s"]))
            )
            continue
        parent = False
        for b in spans:
            if a is b:
                continue
            if (
                b["t0"] >= a["t0"]
                and b["t1"] <= a["t1"]
                and (b["t1"] - b["t0"]) < (a["t1"] - a["t0"])
            ):
                parent = True
                break
        a["leaf"] = not parent
        a["self_wall_s"] = 0.0 if parent else _r(float(a.get("wall_s") or 0.0))
        a["self_cpu_s"] = 0.0 if parent else _r(float(a.get("cpu_s") or 0.0))


def _bucket(acc: dict, key: str, s: dict) -> None:
    b = acc.setdefault(key, {"wall_s": 0.0, "cpu_s": None, "n": 0})
    b["wall_s"] += float(s.get("self_wall_s") or 0.0)
    if s.get("cpu_s") is not None:  # wall-only rows leave the CPU unknown
        b["cpu_s"] = (b["cpu_s"] or 0.0) + float(s.get("self_cpu_s") or 0.0)
    b["n"] += 1
    for u in UNITS:
        v = _num(s.get(u))
        if v is not None:
            b[u] = int(b.get(u, 0) + v)
    v = _num(s.get("n_procs"))
    if v is not None:
        b["n_procs"] = max(int(b.get("n_procs", 0)), int(v))


def _finish(b: dict) -> None:
    """Readings from the sums: how parallel the block ran, and the cost per
    unit of work, which is the number to compare across machines."""
    if b.get("wall_s") and b.get("cpu_s") is not None:
        b["parallelism"] = _r(b["cpu_s"] / b["wall_s"])
    for u, label in (("n_starts", "start"), ("n_fval", "fval"), ("n_points", "point")):
        if b.get(u):
            if b.get("cpu_s") is not None:
                b[f"cpu_s_per_{label}"] = round(b["cpu_s"] / b[u], 4)
            b[f"wall_s_per_{label}"] = round(b["wall_s"] / b[u], 4)


def summarize(
    rows: list[dict],
    *,
    extra_spans: list[dict] | None = None,
    ended_at: float | None = None,
    cpu_at_end: float | None = None,
    session_ends: dict[int, float] | None = None,
) -> dict:
    """The account, from the ledger rows (and spans kept back from it)."""
    spans = _spans_of(rows) + [dict(s) for s in (extra_spans or [])]
    spans.sort(key=lambda s: (s["t0"], -(s["t1"] - s["t0"])))
    _self_times(spans)
    sessions = sessions_of(
        rows, ended_at=ended_at, cpu_at_end=cpu_at_end, ends=session_ends
    )
    if sessions and ended_at is not None:
        # the writing process: its session runs to NOW, not to its end row —
        # the analysis render and this account come after `run_end` and are
        # its time and its CPU too (the `late` spans)
        last = sessions[-1]
        if last["ended"] is None or ended_at > last["ended"]:
            last["ended"] = ended_at
        if cpu_at_end is not None:
            last["cpu_s"] = _r(cpu_at_end)
    # a late span belongs to the session it followed, which is extended over
    # it (the checkpoint after `gate_pending`, the analysis after `run_end`)
    for s in spans:
        s["session"] = None
        for i, ses in enumerate(sessions):
            nxt = sessions[i + 1]["started"] if i + 1 < len(sessions) else None
            if s["t0"] >= ses["started"] and (nxt is None or s["t0"] < nxt):
                s["session"] = ses["index"]
                if ses["ended"] is not None and s["t1"] > ses["ended"]:
                    if s.get("late"):
                        ses["ended"] = s["t1"]
                    else:
                        s["t1"] = ses["ended"]
                        s["wall_s"] = _r(max(0.0, s["t1"] - s["t0"]))
                break
    for ses in sessions:
        ses["wall_s"] = _r(max(0.0, (ses["ended"] or ses["started"]) - ses["started"]))
    by_category: dict[str, dict] = {}
    by_module: dict[str, dict] = {}
    by_round: dict[str, dict] = {}
    agents: dict[str, dict] = {}
    compute: dict[str, dict] = {}
    for s in spans:
        if s.get("category") == "module":
            # the module's whole wall, engine time included — beside the
            # self sums a reader sees what the module cost end to end
            st = by_module.setdefault(
                str(s.get("name")), {"wall_s": 0.0, "cpu_s": None, "n": 0}
            )
            st["total_s"] = _r(st.get("total_s", 0.0) + float(s.get("wall_s") or 0.0))
            if s.get("cpu_s") is not None:
                st["total_cpu_s"] = _r(
                    st.get("total_cpu_s", 0.0) + float(s.get("cpu_s") or 0.0)
                )
            continue
        cat = str(s.get("category") or "")
        _bucket(by_category, cat, s)
        st = by_module.setdefault(
            str(s.get("module") or "(between modules)"),
            {"wall_s": 0.0, "cpu_s": None, "n": 0},
        )
        st["wall_s"] += float(s.get("self_wall_s") or 0.0)
        st["n"] += 1
        st[cat + "_s"] = _r(
            st.get(cat + "_s", 0.0) + float(s.get("self_wall_s") or 0.0)
        )
        if s.get("cpu_s") is not None:
            st["cpu_s"] = (st["cpu_s"] or 0.0) + float(s.get("self_cpu_s") or 0.0)
            st[cat + "_cpu_s"] = _r(
                st.get(cat + "_cpu_s", 0.0) + float(s.get("self_cpu_s") or 0.0)
            )
        _bucket(by_round, f"round_{s.get('round', 0)}", s)
        if cat == "agent":
            a = agents.setdefault(
                str(s.get("name")),
                {"n": 0, "wall_s": 0.0, "cpu_s": None, "api_s": 0.0, "tools_s": 0.0},
            )
            a["n"] += 1
            a["wall_s"] += float(s.get("self_wall_s") or 0.0)
            if s.get("cpu_s") is not None:
                a["cpu_s"] = (a["cpu_s"] or 0.0) + float(s.get("self_cpu_s") or 0.0)
            a["api_s"] += float(s.get("api_s") or 0.0)
            a["tools_s"] += float(s.get("tools_s") or 0.0)
        elif cat == "compute":
            _bucket(compute, str(s.get("name")), s)
    if "agent" in by_category:
        by_category["agent"]["api_s"] = _r(sum(a["api_s"] for a in agents.values()))
        by_category["agent"]["tools_s"] = _r(sum(a["tools_s"] for a in agents.values()))
    for b in list(compute.values()) + list(by_category.values()):
        _finish(b)
    # each session: the self time inside it, and the residual is the engine's
    # own — in wall and, when the session's CPU is known, in CPU
    self_wall: dict[int, float] = {}
    self_cpu: dict[int, float] = {}
    for s in spans:
        if s["session"] is not None and s.get("category") != "module":
            k = s["session"]
            self_wall[k] = self_wall.get(k, 0.0) + float(s.get("self_wall_s") or 0.0)
            self_cpu[k] = self_cpu.get(k, 0.0) + float(s.get("self_cpu_s") or 0.0)
    engine_total = 0.0
    engine_cpu = 0.0
    cpu_known = bool(sessions)
    for ses in sessions:
        timed_ = self_wall.get(ses["index"], 0.0)
        ses["timed_s"] = _r(timed_)
        ses["engine_s"] = _r(max(0.0, ses["wall_s"] - timed_))
        engine_total += ses["engine_s"]
        ses["timed_cpu_s"] = _r(self_cpu.get(ses["index"], 0.0))
        if ses.get("cpu_s") is None:
            cpu_known = False
            continue
        over = ses["timed_cpu_s"] - ses["cpu_s"]
        ses["engine_cpu_s"] = _r(max(0.0, -over))
        if over > 0.05:
            # a child reaped inside a span but started before it (or one
            # that outlived its span): the leaf's CPU exceeds the process's
            ses["cpu_overshoot_s"] = _r(over)
        engine_cpu += ses["engine_cpu_s"]
        if ses["wall_s"]:
            ses["parallelism"] = _r(ses["cpu_s"] / ses["wall_s"])
    by_category["engine"] = {
        "wall_s": _r(engine_total),
        "cpu_s": _r(engine_cpu) if cpu_known else None,
        "n": len(sessions),
    }
    waiting = 0.0
    unaccounted = 0.0
    for a, b in zip(sessions, sessions[1:], strict=False):
        if a["ended"] is None:
            continue
        gap = max(0.0, b["started"] - a["ended"])
        if a["ended_by"] == "killed":
            unaccounted += gap  # nobody was asked anything: the process died
        else:
            waiting += gap
    by_category["waiting_for_human"] = {
        "wall_s": _r(waiting),
        "cpu_s": 0.0,
        "n": sum(1 for a in sessions[:-1] if a["ended_by"] != "killed"),
    }
    if unaccounted:
        by_category["unaccounted"] = {
            "wall_s": _r(unaccounted),
            "cpu_s": None,
            "n": sum(1 for a in sessions[:-1] if a["ended_by"] == "killed"),
        }
    run_wall = 0.0
    if sessions:
        last_end = sessions[-1]["ended"] or sessions[-1]["started"]
        run_wall = max(0.0, last_end - sessions[0]["started"])
    # exact by construction: the sessions and the gaps tile the run, so the
    # only unexplained time is the gap after a killed session (summing the
    # rounded walls instead would leave a ±ms residual that means nothing)
    accounted = run_wall - unaccounted
    run_cpu = (
        _r(sum(float(s["cpu_s"]) for s in sessions if s.get("cpu_s") is not None))
        if cpu_known
        else None
    )
    for d in (by_category, by_module, by_round, agents, compute):
        for v in d.values():
            for k in list(v):
                if isinstance(v[k], float) and not k.endswith(
                    ("_start", "_fval", "_point")
                ):
                    v[k] = _r(v[k])
    return {
        "run_wall_s": _r(run_wall),
        "run_cpu_s": run_cpu,
        "parallelism": _r(run_cpu / run_wall) if run_cpu and run_wall else None,
        "accounted_s": _r(accounted),
        "residual_s": _r(run_wall - accounted),
        "unaccounted_s": _r(unaccounted),
        "n_sessions": len(sessions),
        "waiting_for_human_s": _r(waiting),
        "sessions": sessions,
        "by_category": by_category,
        "by_module": by_module,
        "by_round": by_round,
        "agents": agents,
        "compute": compute,
        "spans": spans,
        "note": (
            "run_wall_s = sum(sessions.wall_s) + waiting_for_human_s + "
            "unaccounted_s (the gap after a killed session); each session.wall_s "
            "= the self time of its spans (agent, compute, render, human, io, "
            "record; a span's wall minus its children's) + engine_s (the engine's "
            "own work between them; a module's self time). residual_s = "
            "unaccounted_s. cpu_s is the process + its finished children "
            "(user+sys): what the work cost, comparable across core counts and "
            "load; parallelism = cpu_s / wall_s; cpu_s_per_start / per_fval / "
            "per_point are the per-unit costs to compare across machines; "
            "`machine` is what it ran on."
        ),
    }


def is_stale(acc: dict | None, rows: list[dict]) -> bool:
    """True when the ledger has moved past the account: a session it does
    not know (a resume that was killed before writing), or rows after the
    last session it closed."""
    if not acc:
        return True
    # only starts the account could place (a row with no readable time is
    # no session, in the stored account or in a rebuilt one)
    n_starts = sum(
        1 for r in rows if r.get("event") == "run_start" and _t(r) is not None
    )
    sessions = acc.get("sessions") or []
    if len(sessions) < n_starts:
        return True
    if sessions:
        ended = sessions[-1].get("ended")
        # only rows that are the account's business: a boundary or a span
        # (the tried-models note the engine writes after run_end is neither)
        last = max(
            (
                t
                for t in (
                    _t(r)
                    for r in rows
                    if r.get("event") in ("run_start", "span", *END_EVENTS)
                )
                if t is not None
            ),
            default=None,
        )
        if ended is not None and last is not None and last > ended + 0.5:
            return True
    return False


def rebuild(acc: dict | None, rows: list[dict]) -> dict:
    """The account from the ledger, keeping what only an earlier account
    knew: its late spans and the effective ends of its sessions."""
    kept = [s for s in ((acc or {}).get("spans") or []) if s.get("late")]
    ends = {
        int(s["index"]): float(s["ended"])
        for s in ((acc or {}).get("sessions") or [])
        if s.get("ended") is not None and s.get("ended_by") != "open"
    }
    out = summarize(rows, extra_spans=kept, session_ends=ends)
    if acc and acc.get("machine"):
        out["machine"] = acc["machine"]
    for s in out["spans"]:
        s.pop("session", None)
    return out


def write(ctx, *, ended_at: float | None = None) -> dict | None:
    """Write the account to the record's `timing` group: at every pause and at
    run end, so the file carries it; `derive` rebuilds it for a record that
    lost its process before this ran."""
    if ctx is None:
        return None
    try:
        rows = ctx.ledger.entries()
        node = ctx.root / "timing"
        earlier = node.get(None) if node.exists() else None
        kept = [s for s in ((earlier or {}).get("spans") or []) if s.get("late")]
        ends = {
            int(s["index"]): float(s["ended"])
            for s in ((earlier or {}).get("sessions") or [])
            if s.get("ended") is not None and s.get("ended_by") != "open"
        }
        # late spans of THIS session are not on the ledger; earlier sessions'
        # were written with the group and are carried forward, as are the
        # ends those sessions ran to
        acc = summarize(
            rows,
            extra_spans=kept + list(_LATE),
            ended_at=ended_at or now(),
            cpu_at_end=cpu_now(),
            session_ends=ends,
        )
        acc["written_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        acc["machine"] = machine()
        for s in acc["spans"]:
            s.pop("session", None)
        node.put(acc)
        return acc
    except Exception as e:  # noqa: BLE001 - the account must never end a run
        print(f"  ⚑ timing account not written: {type(e).__name__}: {str(e)[:200]}")
        return None


def fmt(seconds: float | None) -> str:
    """Seconds a person can read: 0.25s, 4.2s, 3m05s, 1h02m."""
    if seconds is None:
        return "?"
    s = float(seconds)
    if s < 1:
        return f"{s:.2f}s"
    if s < 60:
        return f"{s:.1f}s" if s < 10 else f"{s:.0f}s"
    m, sec = divmod(int(round(s)), 60)
    if m < 60:
        return f"{m}m{sec:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def one_line(acc: dict | None) -> str:
    """The account in one line, for `status`."""
    if not acc:
        return (
            "time: no account (the run predates the time account, "
            "or its record was cut short)"
        )
    cats = acc.get("by_category") or {}
    n = acc.get("n_sessions") or 0
    if not acc.get("spans"):
        return (
            f"time: {fmt(acc.get('run_wall_s'))} wall over {n} session(s), "
            f"waiting at gates {fmt(acc.get('waiting_for_human_s'))}; the rest is "
            f"unattributed (no spans: the run predates the time account)"
        )

    def part(key: str, label: str) -> str | None:
        v = (cats.get(key) or {}).get("wall_s")
        if not v:
            return None
        extra = ""
        if key == "agent" and cats[key].get("api_s"):
            extra = f" (model {fmt(cats[key]['api_s'])})"
        return f"{label} {fmt(v)}{extra}"

    parts = [
        p
        for p in (
            part("agent", "agents"),
            part("compute", "compute"),
            part("render", "render"),
            part("human", "human"),
            part("io", "io"),
            part("record", "record"),
            part("engine", "engine"),
            part("waiting_for_human", "waiting at gates"),
            part("unaccounted", "unaccounted (killed)"),
        )
        if p
    ]
    cpu = acc.get("run_cpu_s")
    cpu_txt = (
        f" (cpu {fmt(cpu)}, {float(acc.get('parallelism') or 0):.1f} cores busy)"
        if cpu and acc.get("parallelism")
        else ""
    )
    return (
        f"time: {fmt(acc.get('run_wall_s'))} wall{cpu_txt} over {n} session(s) = "
        + " + ".join(parts)
    )
