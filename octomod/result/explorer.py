"""Explore a run record interactively, or print one part of it.

The run is one HDF5 file; this is how a person looks inside it
without writing h5py. Two entry points:

    ./run.sh explore --run-id <id>            an interactive shell
    ./run.sh show    --run-id <id> [<key>]    one group or dataset, then exit

Keys are record keys (`rounds/round_0/candidates/base/estimation`,
`rounds/round_0/decisions_md`), absolute or relative to the shell's current
group; there is no second, file-shaped name for anything. Inside the shell,
`cd` moves through the tree, `ls` lists, `cat` prints a group as YAML, a
`Table` as TSV text, a text dataset as its text and any other dataset as its
value, and the reading verbs — `gates`, `decisions`, `failures`, `ledger`,
`status` — answer the questions a reader has before they know the tree. `report` renders a round's
HTML on demand (a real file under `runs/<id>_reports/`); `export` writes one
part to a JSON, YAML or text file. Nothing here writes into the record.
"""

from __future__ import annotations

import cmd
import json
import shlex
import sys
from pathlib import Path
from typing import Any

import yaml

from octomod.result import node as tree
from octomod.result.node import Node
from octomod.result.runstore import RunStore
from octomod.result.runstore import key as _key_of

FOLD = 400  # characters of a long string shown by `cat` before it is folded


# ------------------------------------------------------------------ helpers


def _normalise(path: str) -> str:
    """`a/b/../c/.` → `a/c`; never climbs above the root."""
    out: list[str] = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if out:
                out.pop()
            continue
        out.append(seg)
    return "/".join(out)


def resolve_key(store: RunStore, arg: str, cwd: str = "") -> str | None:
    """A record key from what a person typed: a key relative to the shell's
    current group, or an absolute one (a leading `/`, or simply a key from the
    root). None when nothing matches."""
    raw = (arg or "").strip()
    if raw in ("", "."):
        return cwd
    candidates = []
    if cwd and not raw.startswith("/"):
        candidates.append(_normalise(f"{cwd}/{raw}"))
    candidates.append(_normalise(raw))
    for c in candidates:
        if c == "":
            return ""
        if store.exists(c):
            return c
        # a segment typed as the id it names (a `%` in it) rather than escaped
        escaped = _key_of(*c.split("/"))
        if escaped != c and store.exists(escaped):
            return escaped
    return None


def _child_key(parent: str, name: str) -> str:
    """The key of child `name` (an unescaped name, as `keys` lists it)."""
    return f"{parent}/{_key_of(name)}" if parent else _key_of(name)


def _fold(value: Any, full: bool) -> Any:
    """Long strings shortened for the screen, recursively; opaque bytes (a
    cached paper) are never printed, only measured — `export` writes them."""
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > FOLD and not full:
        return value[:FOLD] + f"… [{len(value) - FOLD} more chars; `cat --full`]"
    if isinstance(value, dict):
        return {k: _fold(v, full) for k, v in value.items()}
    if isinstance(value, list):
        numeric = all(isinstance(v, (int, float)) for v in value)
        if len(value) > 60 and numeric and not full:
            return value[:60] + [f"… [{len(value) - 60} more values; `cat --full`]"]
        return [_fold(v, full) for v in value]
    return value


def _as_table(data: Any):
    """A stored `Table` as a DataFrame, or None when `data` is not one."""
    if not (
        isinstance(data, dict)
        and isinstance(data.get("columns"), list)
        and isinstance(data.get("data"), dict)
        and set(data) <= {"columns", "data", "elided"}
    ):
        return None
    try:
        from octomod.result.records import Table

        return Table.model_validate(data).to_dataframe()
    except Exception:  # noqa: BLE001 - a dict that only looks like a table
        return None


def render_value(data: Any, full: bool = False) -> str:
    """A `Table` as TSV text, a group as YAML, a text as text, a scalar as
    itself."""
    df = _as_table(data)
    if df is not None:
        text = df.to_csv(sep="\t", index=False)
        return text if full or len(text) <= FOLD * 10 else _fold(text, False)
    if isinstance(data, str):
        return data if full or len(data) <= FOLD * 4 else _fold(data, False)
    if isinstance(data, (dict, list)):
        return yaml.safe_dump(
            _fold(data, full), sort_keys=False, allow_unicode=True, width=100
        )
    return str(_fold(data, full))


def list_children(store: RunStore, key: str) -> list[tuple[str, str, str]]:
    """(name, 'group'|'dataset', preview) for the direct children of `key`."""
    out = []
    with store.reading():
        for name in store.keys(key):
            child = _child_key(key, name)
            grand = store.keys(child)
            if set(grand) in ({"columns", "data"}, {"columns", "data", "elided"}):
                df = _as_table(store.get(child))
                if df is not None:
                    t, preview = "dataset", f"table {len(df)} × {len(df.columns)}"
                    out.append((name, t, preview))
                    continue
            if grand:
                t, preview = "group", f"{len(grand)} item(s)"
            else:
                v = store.get(child)
                if isinstance(v, dict):  # an empty group
                    t, preview = "group", "0 item(s)"
                else:
                    t = "dataset"
                    v = _fold(v, True)  # bytes → `<n bytes>`
                    s = v if isinstance(v, str) else json.dumps(v, default=str)
                    preview = (s[:70] + "…") if len(s) > 70 else s
            out.append((name, t, preview.replace("\n", "⏎")))
    return out


# ------------------------------------------------------------ the readers


def gates_lines(store: RunStore, round_idx: int | None = None) -> list[str]:
    lines = []
    root = Node(store)
    with store.reading():
        rounds = tree.round_indices(root)
        for k in rounds:
            if round_idx is not None and k != round_idx:
                continue
            lines += _round_gate_lines(tree.round_node(root, k))
    return lines or ["(no gates recorded)"]


def _round_gate_lines(rnd: Node) -> list[str]:
    lines = []
    rname = rnd.name
    places = [("", tree.gates_node(rnd, None))]
    for cid in tree.candidate_ids(rnd):
        places.append((cid, tree.gates_node(rnd, cid)))
    for cid, gnode in places:
        for gid in gnode.children():
            g = gnode.child(gid).get({}) or {}
            if not isinstance(g, dict):
                continue
            mark = "✓" if g.get("passed") else "✗"
            blocking = "" if g.get("blocking", True) else " (advisory)"
            who = f" [{cid}]" if cid else ""
            lines.append(
                f"{rname}{who}  {mark} {gid} ({g.get('tier', g.get('tier_level', '?'))})"
                f"{blocking}: {str(g.get('detail') or '')[:110]}"
            )
    return lines


def decisions_lines(store: RunStore) -> list[str]:
    lines = []
    root = Node(store)
    with store.reading():
        for k in tree.round_indices(root):
            rnd = tree.round_node(root, k)
            places = [rnd / "decisions"] + [
                tree.work_node(rnd, cid) / "decisions"
                for cid in (rnd / "candidates").children()
            ]
            for dnode in places:
                for module in dnode.children():
                    d = dnode.child(module).get({}) or {}
                    if not isinstance(d, dict) or "approved" not in d:
                        continue
                    lines.append(
                        f"{rnd.name}  {module}: {'yes' if d.get('approved') else 'no'}"
                        f" — signed {d.get('signed') or '?'}"
                        + (f"; note: {d.get('note')}" if d.get("note") else "")
                    )
    return lines or ["(no decisions recorded)"]


def ledger_lines(store: RunStore, n: int = 20, event: str | None = None) -> list[str]:
    rows = store.ledger_rows()
    if event:
        rows = [r for r in rows if r.get("event") == event]
    else:  # spans only when asked for by name (`ledger 20 span`)
        rows = [r for r in rows if r.get("event") != "span"]
    out = []
    for r in rows[-n:]:
        extra = (
            r.get("gate_id") or r.get("note") or r.get("reason") or r.get("role") or ""
        )
        out.append(
            f"{r.get('ts', '')} r{r.get('round', 0)} [{r.get('module', '')}] "
            f"{r.get('event', '')} {str(extra)[:100]}"
        )
    return out or ["(no ledger rows)"]


def failures_lines(store: RunStore) -> list[str]:
    try:
        rr = store.load()
    except Exception as e:  # noqa: BLE001 - say what is wrong with the record
        return [f"(the record does not validate: {type(e).__name__}: {str(e)[:200]})"]
    fails = rr.failures()
    if not fails:
        return ["nothing went wrong that the record knows of"]
    out = []
    for f in fails:
        where = f"round {f['round']}" if f.get("round") is not None else "run"
        cand = f" [{f['candidate']}]" if f.get("candidate") else ""
        out.append(
            f"{where}{cand}  {f['kind']:18s} {f['id']}: {str(f.get('detail') or '')[:160]}"
        )
    return out


def status_lines(store: RunStore) -> list[str]:
    """Rounds, candidates, markers, decisions, outcome, then the ledger tail —
    what `./run.sh status` prints."""
    from octomod.orchestration import timing as _timing
    from octomod.result.access import record_for

    record = record_for(store)
    out = [
        f"{store.run_id}: {len(record.rounds)} round(s), outcome "
        f"{record.outcome.outcome if record.outcome else 'open'} ({store.path})",
        # where the wall time went, in one line (`show timing` for all of it)
        _timing.one_line(
            record.timing.model_dump(exclude_none=True) if record.timing else None
        ),
    ]
    # whether each finished step left what it should in the record
    from octomod.result import completeness
    from octomod.result import node as tree

    root = tree.root(store)
    line = completeness.summary_line(root)
    if line:
        out.append(line)
        for e in completeness.summary(root)["incomplete"][:5]:
            for m in e["missing"][:3]:
                out.append(
                    f"  missing after {e['checkpoint']}: {m['key']} — {m['what']}"
                )
    for k in record.round_indices:
        r = record.round(k)
        markers = sorted((r.status.markers if r.status else {}).keys())
        out.append(f"round_{k} [{r.shape}]: markers {markers}")
        for cid, c in r.candidates.items():
            have = [
                n
                for n, v in (
                    ("model", c.model or (cid == "_single" and r.model)),
                    ("petab", c.petab),
                    ("cost", c.cost),
                    ("estimation", c.estimation),
                )
                if v
            ]
            cm = sorted(c.markers.keys()) if c.markers else []
            extra = (
                f" best_fval={c.estimation.best_fval:.4g}"
                if c.estimation and c.estimation.best_fval is not None
                else ""
            )
            out.append(
                f"  candidate {cid}: {', '.join(have)}{extra}"
                + (f" markers {cm}" if cm else "")
            )
        if r.selection and r.selection.winner:
            out.append(
                f"  selection: {r.selection.criterion} winner {r.selection.winner}"
            )
        for d in r.decisions.values():
            out.append(
                f"  decision {d.module}: {'yes' if d.approved else 'no'} "
                f"({d.mode or '?'}){' — ' + d.note if d.note else ''}"
            )
        if r.revision and r.revision.move:
            out.append(f"  revision: {r.revision.move.get('type')}")
        if r.expansion and r.expansion.expanded:
            out.append(
                f"  expansion: axes {getattr(r.expansion, 'axes', None)} "
                f"→ round {r.expansion.next_round}"
            )
    rows = store.ledger_rows()
    if rows:
        out.append("")
        out.append("last ledger entries:")
        # the span rows are the time account's, not a reader's tail
        for e in [r for r in rows if r.get("event") != "span"][-8:]:
            out.append(
                f"  {e.get('ts', '')} [{e.get('module', '')}] {e.get('event', '')} "
                f"{e.get('gate_id', e.get('note', ''))}"
            )
    return out


def export_part(store: RunStore, key: str, out: Path) -> Path:
    """A blob (a cached paper) is written as the bytes it is; inside a group
    exported as YAML or JSON it appears as `<n bytes>`. The ledger is a byte
    stream in the record and is exported as its rows."""
    from octomod.result.runstore import LEDGER_KEY

    data = store.ledger_rows() if key == LEDGER_KEY else store.get(key)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        out.write_bytes(data)
    elif out.suffix in (".yaml", ".yml"):
        out.write_text(
            yaml.safe_dump(_fold(data, True), sort_keys=False, allow_unicode=True)
        )
    elif out.suffix == ".json":
        out.write_text(json.dumps(_fold(data, True), indent=2, default=str) + "\n")
    else:
        out.write_text(data if isinstance(data, str) else render_value(data, True))
    return out


# --------------------------------------------------------------- the shell


class Explorer(cmd.Cmd):
    intro = (
        "Octomod record explorer — `help` lists the verbs; `ls`, `cd`, `cat` "
        "walk the tree; `gates`, `decisions`, `failures`, `ledger`, `status` "
        "read it; `quit` leaves."
    )

    def __init__(self, store: RunStore, stdout=None):
        super().__init__(stdout=stdout or sys.stdout)
        self.store = store
        self.cwd = ""
        self.prompt = f"{store.run_id}:/> "

    # -- navigation ---------------------------------------------------------
    def _key(self, arg: str) -> str | None:
        key = resolve_key(self.store, arg, self.cwd)
        if key is None:
            self._say(f"no such record key: {arg!r}")
        return key

    def _say(self, text: str) -> None:
        self.stdout.write(text + "\n")

    def do_ls(self, arg: str) -> None:
        """ls [key] — list the children of a group (default: here)."""
        key = self._key(arg) if arg else self.cwd
        if key is None:
            return
        rows = list_children(self.store, key)
        if not rows:
            v = self.store.get(key)
            self._say(render_value(v))
            return
        width = max(len(n) for n, _, _ in rows)
        for name, kind, preview in rows:
            tag = "/" if kind == "group" else " "
            self._say(f"  {name + tag:{width + 1}s}  {preview}")

    def do_cd(self, arg: str) -> None:
        """cd <key> — move to a group (`cd ..` up, `cd` to the root)."""
        if not arg.strip():
            self.cwd = ""
        else:
            key = self._key(arg)
            if key is None:
                return
            self.cwd = key
        self.prompt = f"{self.store.run_id}:/{self.cwd}> "

    def do_pwd(self, arg: str) -> None:
        """pwd — where you are."""
        self._say("/" + self.cwd)

    def do_cat(self, arg: str) -> None:
        """cat [--full] <key> — a group as YAML, a table as TSV, a text as
        its text, any other dataset as its value. Long strings and arrays are
        folded unless --full."""
        parts = shlex.split(arg)
        full = "--full" in parts
        parts = [p for p in parts if p != "--full"]
        key = self._key(parts[0] if parts else "")
        if key is None:
            return
        self._say(render_value(self.store.get(key), full))

    def do_find(self, arg: str) -> None:
        """find <text> — every key containing <text>."""
        text = arg.strip().lower()
        hits = [k for k, _ in self.store.walk("") if text in k.lower()]
        for k in hits[:200]:
            self._say("  " + k)
        if len(hits) > 200:
            self._say(f"  … {len(hits) - 200} more")
        if not hits:
            self._say("(nothing)")

    # -- reading ------------------------------------------------------------
    def do_gates(self, arg: str) -> None:
        """gates [round] — every gate verdict, failed ones marked ✗."""
        k = int(arg) if arg.strip().isdigit() else None
        for line in gates_lines(self.store, k):
            self._say("  " + line)

    def do_decisions(self, arg: str) -> None:
        """decisions — who decided what, at which gate."""
        for line in decisions_lines(self.store):
            self._say("  " + line)

    def do_failures(self, arg: str) -> None:
        """failures — where things went wrong, in order."""
        for line in failures_lines(self.store):
            self._say("  " + line)

    def do_ledger(self, arg: str) -> None:
        """ledger [n] [event] — the last n rows (default 20), optionally one event."""
        parts = arg.split()
        n = int(parts[0]) if parts and parts[0].isdigit() else 20
        event = (
            parts[1]
            if len(parts) > 1
            else (parts[0] if parts and not parts[0].isdigit() else None)
        )
        for line in ledger_lines(self.store, n, event):
            self._say("  " + line)

    def do_status(self, arg: str) -> None:
        """status — rounds, candidates, markers, decisions, outcome."""
        for line in status_lines(self.store):
            self._say(line)

    def do_report(self, arg: str) -> None:
        """report [round] — render the round's HTML report beside the record
        (runs/<id>_reports/round_k/report/report.html)."""
        from octomod.reporting import write_report_html

        root = Node(self.store)
        rounds = tree.round_indices(root)
        if not rounds:
            self._say("(no rounds)")
            return
        k = int(arg.strip()) if arg.strip().isdigit() else rounds[-1]
        rnd = tree.round_node(root, k)
        if not rnd.exists():
            self._say(f"no such round: {rnd.key}")
            return
        self._say(str(write_report_html(rnd)))

    def do_export(self, arg: str) -> None:
        """export <key> <file> — one group or dataset to a .json/.yaml/.txt file
        (a table to .tsv as TSV text)."""
        parts = shlex.split(arg)
        if len(parts) != 2:
            self._say("usage: export <key> <file>")
            return
        key = self._key(parts[0])
        if key is None:
            return
        self._say(str(export_part(self.store, key, Path(parts[1]))))

    # -- leaving ------------------------------------------------------------
    def do_quit(self, arg: str) -> bool:
        """quit — leave the explorer."""
        return True

    do_exit = do_q = do_EOF = do_quit

    def emptyline(self) -> None:  # a bare Enter does nothing (cmd repeats by default)
        return

    def default(self, line: str) -> None:
        key = resolve_key(self.store, line.strip(), self.cwd)
        if key is not None:
            self.do_cat(line)
        else:
            self._say(f"unknown verb or key: {line!r} (`help` lists the verbs)")


def show(store: RunStore, key: str | None, full: bool = False) -> int:
    """`./run.sh show`: one part of the record to stdout."""
    if not store.exists_on_disk():
        print(f"no such run: {store.path}", file=sys.stderr)
        return 1
    if not key:
        for name, kind, preview in list_children(store, ""):
            print(f"  {name + ('/' if kind == 'group' else ' '):24s} {preview}")
        return 0
    k = resolve_key(store, key)
    if k is None:
        print(f"no such record key in {store.path.name}: {key!r}", file=sys.stderr)
        return 1
    rows = list_children(store, k)
    if set(store.keys(k)) <= {"columns", "data", "elided"}:
        rows = []  # a Table (or a dataset): shown whole, as TSV text
    if rows and not full:
        width = max(len(n) for n, _, _ in rows)
        for name, kind, preview in rows:
            print(
                f"  {name + ('/' if kind == 'group' else ' '):{width + 1}s}  {preview}"
            )
        return 0
    print(render_value(store.get(k), full), end="")
    return 0
