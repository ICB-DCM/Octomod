"""The record addressed by key: `Node`, `RunStore`, the tree.

Each test pins one property of it:

  1. candidates are enumerated from the record, never `_single`
  2. a write REPLACES: fields of an earlier write do not survive
  3. a neighbour's write never makes a record appear
  4. one malformed entry is left out on load, not fatal
  5. key paths are whole keys — no glob emulation to get wrong
  6. a block of reads is one file open
  7. a marker hashes each slot part once
  8. `commit` and `load` agree on a target without `.h5`
  9. `track_order` is the store's own, not the process's
 10. what goes in comes out: JSON, tables, text, bytes, arrays, copies
 11. the readings no module writes are derived on load — a call's ledger
     rows, a redraft, a dropped candidate — so `failures()` sees them, and a
     candidate's own decision is never invented a second time at round level
 12. a ledger row quoting U+2028 stays one row; a record
     rewritten a thousand times stays small; a 5 MB blob is one value; the
     overlay S3 applies (a list) survives the load; mkstd reads the ledger
 13. a blob stays bytes through `load`, `commit` and
     `show` (and the empty blob stores); a failed write leaves the old
     content, a NUL in a string is escaped; `put` returns the reader's sha;
     a legacy YAML ledger is converted whole and never replaced unparsed;
     `remove` takes what an interrupted restore or copy left behind

What a damaged file does is pinned in `tests/result_store_crash_unit.py`.

    uv run python tests/record_node_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration import round_status  # noqa: E402
from octomod.orchestration.artifacts import ArtifactError  # noqa: E402
from octomod.result import access  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node, RecordMissing  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402
from octomod.result.store import commit, load  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


def test_candidates_never_include_the_single_workdir() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        (tree.work_node(r0, None) / "estimation").put({"best_fval": 1.0})
        assert tree.candidate_ids(r0) == [], tree.candidate_ids(r0)
        r1 = rnd(root, 1)
        for cid in ("base", "a+b", "x/y"):
            (tree.work_node(r1, cid) / "estimation").put({"best_fval": 2.0})
        assert tree.candidate_ids(r1) == sorted(["base", "a+b", "x/y"])
        # an id with `/` is ONE group, and reads back under its own name
        assert (tree.work_node(r1, "x/y") / "estimation").get() == {"best_fval": 2.0}
        assert tree.round_indices(root) == [0, 1]
        rr = access.record_for(root)
        assert rr.round(0).shape == "single" and rr.round(1).shape == "candidate_set"
    print("  candidates     from the record; `_single` is never one; `/` in an id")


def test_a_write_replaces_the_group() -> None:
    with temp_record() as root:
        est = tree.work_node(rnd(root, 0), "a") / "estimation"
        est.put({"best_fval": 1.0, "failure": "degenerate start"})
        (est.parent / "multistart").put_raw({"n_starts": 2, "fval": [1.0, 2.0]})
        est.put({"best_fval": 0.5})
        assert est.get() == {"best_fval": 0.5}, est.get()
        # the multistart is a sibling: the summary's rewrite left it alone
        assert (est.parent / "multistart").get()["n_starts"] == 2
    print("  replace        a rewrite keeps no field of the earlier write")


def test_the_core_alone_is_not_a_report() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        (r0 / "evaluation_core").put({"goal": "prediction", "fit": []})
        (r0 / "attribution").put({"rows": []})
        (r0 / "expansion_offer").put({"approved": True})
        rr = access.record_for(root)
        assert rr.round(0).evaluation is None
        assert access.rounds_with_reports(rr) == []
        assert (
            rr.round(0).expansion is None and access.expansion_dict(rr.round(0)) is None
        )
        assert rr.round(0).expansion_offer == {"approved": True}
        (r0 / "evaluation").put({})
        rr = access.record_for(root)
        assert access.rounds_with_reports(rr) == [(0, {})], "an empty report is one"
    print("  siblings       S7's core, the attribution, the offer make no report")


def test_a_malformed_entry_is_left_out_on_load() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        (r0 / "model/parameters").put([{"id": "k1"}, "a note, not a row"])
        (r0 / "space/axes").put([{"question": "no id"}, {"id": "feedback"}])
        (r0 / "gates").child("broken").put({"passed": True})
        (tree.work_node(r0, None) / "cost").put({"solver_settings": "not a dict"})
        rr = access.record_for(root)
        assert [p.id for p in rr.round(0).model.parameters] == ["k1"]
        assert [a.id for a in rr.round(0).space.axes] == ["feedback"]
        assert "broken" not in rr.round(0).gates
        assert rr.round(0).candidates["_single"].cost.solver_settings is None
        root.store.load()
        assert len(root.store.dropped) == 4, root.store.dropped
    print("  lenient load   4 malformed entries left out and named; the rest reads")


def test_keys_are_whole_and_missing_is_loud() -> None:
    with temp_record() as root:
        n = tree.work_node(rnd(root, 0), "a") / "estimation"
        assert n.key == "rounds/round_0/candidates/a/estimation"
        try:
            n.get()
        except RecordMissing as e:
            assert isinstance(e, ArtifactError) and isinstance(e, KeyError)
            assert "rounds/round_0/candidates/a/estimation" in str(e)
        else:
            raise AssertionError("a missing node read did not raise")
        assert n.get(None) is None and n.text("") == "" and n.table(None) is None
        assert not n.exists() and not n.delete()
    print("  keys           whole record keys; a missing read raises, with the key")


def test_a_block_of_reads_is_one_open() -> None:
    with temp_record() as root:
        r0 = rnd(root, 1)
        for cid in ("a", "b", "c", "d", "e", "f"):
            (tree.work_node(r0, cid) / "estimation").put({"best_fval": 1.0})
        opens = []
        real = h5py.File

        def counting(*a, **k):
            opens.append(a[0])
            return real(*a, **k)

        h5py.File = counting
        try:
            ids = tree.candidate_ids(r0)
            assert len(opens) == 1, len(opens)
            opens.clear()
            with root.store.reading():
                vals = [
                    (tree.work_node(r0, c) / "estimation").get()["best_fval"]
                    for c in ids
                ]
                assert all((tree.work_node(r0, c) / "estimation").exists() for c in ids)
            assert len(opens) == 1 and vals == [1.0] * 6, len(opens)
            opens.clear()
            with root.store.reading():
                (r0 / "x").put({"a": 1})  # a write inside closes the handle ...
                assert (r0 / "x").get() == {"a": 1}  # ... and a read reopens it
        finally:
            h5py.File = real
        assert len(opens) == 2, opens
    print("  sessions       listing 6 candidates: 1 open; 12 reads in a block: 1 open")


def test_a_marker_hashes_each_part_once() -> None:
    from octomod.result import node as node_mod

    with temp_record() as root:
        r0 = rnd(root, 0)
        (r0 / "model/sbml").put_text("<sbml/>")
        (r0 / "model/antimony").put_text("model m\nend")
        calls = []
        real = node_mod.Node.sha

        def counting(self):
            calls.append(self.key)
            return real(self)

        node_mod.Node.sha = counting
        try:
            shas: dict = {}

            class _Ctx:  # the two attributes marker_files reads
                round = r0
                candidate = None

            files = round_status.marker_files(_Ctx, "s1", shas=shas)
            round_status.slot_state(r0, shas=shas)
        finally:
            node_mod.Node.sha = real
        assert set(files) == {"sbml", "antimony"}, files
        assert sorted(calls) == sorted(set(calls)), f"hashed twice: {calls}"
    print("  marker shas    each slot part hashed once per marker")


def test_commit_and_load_agree_on_the_target() -> None:
    with temp_record() as root:
        (root / "run").put({"run_id": "x"})
        rr = access.record_for(root)
        with tempfile.TemporaryDirectory() as d:
            written = commit(rr, Path(d) / "foo")
            assert written == Path(d) / "foo.h5", written
            assert load(Path(d) / "foo").run.run_id == "x"
            assert not (Path(d) / "foo").exists(), "commit made a directory"
    print("  commit         runs/foo is written as runs/foo.h5, which load reads")


def test_track_order_is_scoped_to_our_writes() -> None:
    assert h5py.get_config().track_order is False
    with temp_record() as root:
        (root / "x").put({"z": 1, "a": 2, "m": 3})
        assert list((root / "x").get()) == ["z", "a", "m"], "insertion order lost"
        assert h5py.get_config().track_order is False, "changed for the process"
        with tempfile.TemporaryDirectory() as d:
            with h5py.File(Path(d) / "other.h5", "w") as f:
                f.create_group("z")
                f.create_group("a")
            with h5py.File(Path(d) / "other.h5", "r") as f:
                assert list(f) == ["a", "z"], "another writer's file became ordered"
    print("  track_order    on for the record's groups, off for everyone else's")


def test_what_goes_in_comes_out() -> None:
    with temp_record() as root:
        n = root / "rounds/round_0/data/report"
        payload = {
            "b": [1, 2.5, None, True, "ü"],
            "a": {"nested": {"empty_list": [], "empty": {}}},
            "rows": [{"x": 1}, {"x": 2}],
            "s": "",
        }
        n.put(payload)
        assert n.get() == payload, n.get()
        df = pd.DataFrame(
            {
                "time": [0.0, 1.5, np.nan],
                "id": ["a", None, "c"],
                "n": [1, 2, 3],
                "mixed": ["1", "x", "2.0"],
            }
        )
        t = root / "rounds/round_0/data/measurements"
        t.put_table(df)
        back = t.table()
        assert list(back.columns) == list(df.columns)
        assert back["n"].tolist() == [1, 2, 3]
        assert back["time"].tolist()[:2] == [0.0, 1.5] and pd.isna(back["time"][2])
        assert back["id"].tolist()[0] == "a" and pd.isna(back["id"][1])
        assert back["mixed"].tolist() == ["1", "x", "2.0"]
        txt = root / "rounds/round_0/model/antimony"
        txt.put_text("model m\n  k = 1\nend\n")
        assert txt.text() == "model m\n  k = 1\nend\n"
        blob = root / "rounds/round_0/evidence_sources/paper.pdf"
        blob.put_blob(b"%PDF-\x00\xff")
        assert blob.blob() == b"%PDF-\x00\xff"
        arr = root / "rounds/round_0/candidates/_single/multistart"
        arr.put_raw({"x": np.arange(6.0).reshape(3, 2), "n_starts": 3})
        assert arr.get()["x"] == [[0.0, 1.0], [2.0, 3.0], [4.0, 5.0]]
        # copies: within the file and into another record, arrays and all
        dst = root / "rounds/round_1/data"
        assert (root / "rounds/round_0/data").copy_to(dst)
        assert (dst / "report").get() == payload
        with temp_record("other") as other:
            assert arr.copy_to(other / "rounds/round_0/candidates/_single/multistart")
            got = (other / "rounds/round_0/candidates/_single/multistart").get()
            assert got["n_starts"] == 3
        assert access.record_for(root).round(1).data.report == payload
    print(
        "  round trips    JSON, tables (NaN, None, dtypes), text, bytes, arrays, copies"
    )


def test_readings_are_derived_on_load() -> None:
    with temp_record() as root:
        r0 = rnd(root, 0)
        (r0 / "space/candidates").put([{"id": "a", "label": "the A model"}])
        (tree.work_node(r0, "a") / "estimation").put({"best_fval": 1.0})
        (tree.work_node(r0, "b") / "estimation").put({"best_fval": 2.0})
        (r0 / "agent_calls/construction/prompt").put_text("build it")
        (tree.markers_node(r0, "a")).child("cost").put({"approved_n_starts": 50})
        (tree.work_node(r0, "a") / "cost").put({"compile_s": 1.0})
        (r0 / "status/markers").child("s1").put({"producer": "agent:construction"})
        (r0 / "model/sbml").put_text("<sbml/>")
        for row in (
            {"event": "run_start", "ts": "t0"},
            {"event": "agent_call", "role": "construction", "cost_usd": 0.25},
            {"event": "redraft", "role": "construction", "n_failures": 2},
            {"event": "candidate_dropped", "candidate": "b", "reason": "no fit"},
            {
                "event": "human_gate",
                "module": "evaluation_verdict",
                "approved": True,
                "mode": "file",
                "note": "ok",
            },
        ):
            root.store.append_ledger({"ts": "t", "round": 0, "module": "", **row})
        rr = access.record_for(root)
        r = rr.round(0)
        call = r.agent_calls["construction"]
        assert (
            len(call.calls) == 1 and call.cost_usd == 0.25 and len(call.redrafts) == 1
        )
        assert r.model.producer == "agent:construction"
        assert r.candidates["a"].label == "the A model"
        assert r.candidates["a"].cost.approved_n_starts == 50
        assert r.candidates["b"].dropped is not None
        assert r.decisions["evaluation_verdict"].mode == "file"
        kinds = sorted(f["kind"] for f in rr.failures())
        assert kinds == ["candidate_dropped", "redraft"], kinds
        assert rr.run.n_invocations == 1
    print("  derived        call rows, cost, redraft, drop, producer, decision mode")


def test_second_review_findings() -> None:
    import time as _time

    with temp_record() as root:
        st = root.store
        # a row quoting a line separator is one row, read back whole
        st.append_ledger({"ts": "t", "event": "note", "note": "a\u2028b\u0085c"})
        st.append_ledger({"ts": "t", "event": "note", "note": "next"})
        rows = st.ledger_rows()
        assert [r["note"] for r in rows] == ["a\u2028b\u0085c", "next"], rows
        assert len(access.record_for(root).ledger) == 2
        # growth: 1000 rows and 300 rewrites of a group keep the file small
        t0 = _time.perf_counter()
        for i in range(1000):
            st.append_ledger({"ts": "t", "event": "gate", "i": i, "detail": "x" * 250})
        for i in range(300):
            (root / "rounds/round_0/gates").child(f"g{i % 20}").put(
                {"gate_id": f"g{i % 20}", "tier": "T1", "passed": True, "d": "y" * 500}
            )
        dt = _time.perf_counter() - t0
        size = st.path.stat().st_size
        assert size < 3_000_000, f"the record grew to {size / 1e6:.1f} MB"
        assert len(st.ledger_rows()) == 1002
        # a 5 MB blob is written and read as one opaque value
        big = bytes(range(256)) * 20480
        t1 = _time.perf_counter()
        (root / "rounds/round_0/evidence_sources").child("paper.pdf").put_blob(big)
        assert (root / "rounds/round_0/evidence_sources").child(
            "paper.pdf"
        ).blob() == big
        tb = _time.perf_counter() - t1
        assert tb < 2.0, f"a 5 MB blob took {tb:.1f} s"
        # a candidate's own decision is not invented again for the round
        r0 = rnd(root, 0)
        (tree.work_node(r0, "a") / "decisions").child("estimation_convergence").put(
            {"module": "estimation_convergence", "approved": True, "note": "accept A"}
        )
        (tree.work_node(r0, "a") / "assembly_overlay_applied").put(
            [{"patch": "offset", "as": "obs_x"}]
        )
        (tree.work_node(r0, "a") / "estimation").put({"best_fval": 1.0})
        st.append_ledger(
            {
                "ts": "t",
                "event": "human_gate",
                "module": "estimation_convergence",
                "approved": True,
                "mode": "file",
                "round": 0,
            }
        )
        rr = access.record_for(root)
        assert "estimation_convergence" not in rr.round(0).decisions
        cand = rr.round(0).candidates["a"]
        assert cand.decisions["estimation_convergence"].mode == "file"
        assert cand.assembly_overlay_applied == [{"patch": "offset", "as": "obs_x"}]
        # mkstd's generic load reads the ledger stream as rows
        from octomod.result.store import RunResultStandard

        if RunResultStandard is not None:
            generic = RunResultStandard.load_data(str(st.path))
            assert len(generic.ledger) == len(rr.ledger)
    print(
        f"  robustness     U+2028 row intact; 1000 rows + 300 rewrites → "
        f"{size / 1e6:.2f} MB in {dt:.1f} s; 5 MB blob {tb:.2f} s; no invented decision"
    )


def test_a_store_that_does_not_exist_reads_as_empty() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Node(RunStore(Path(d) / "none.h5"))
        assert not root.exists() and root.children() == []
        assert (root / "run").get(None) is None
        (root / "run").put({"run_id": "none"})  # the first write creates the file
        assert (Path(d) / "none.h5").exists()
    print("  absent store   reads are empty; the first write creates the file")


def test_blobs_stay_bytes_through_load_and_commit() -> None:
    """`load()` keeps every opaque value bytes: decoded to a str it would be
    mangled, and `commit`/`export` would fail on its NULs (VLEN strings
    cannot hold one). The empty blob stores too."""
    from octomod.result.explorer import export_part, list_children, render_value

    raw = b"%PDF-\x00\xff\xfe"
    with temp_record() as root:
        src = rnd(root, 0) / "evidence_sources"
        src.child("paper.pdf").put_blob(raw)
        src.child("empty.bin").put_blob(b"")
        assert src.child("paper.pdf").blob() == raw
        assert src.child("empty.bin").blob() == b""
        assert src.get() == {"paper.pdf": raw, "empty.bin": b""}, src.get()
        rr = root.store.load()
        assert rr.round(0).evidence_sources == {"paper.pdf": raw, "empty.bin": b""}
        with tempfile.TemporaryDirectory() as d:
            copy = commit(rr, Path(d) / "copy")
            other = Node(RunStore(copy))
            assert (rnd(other, 0) / "evidence_sources").child("paper.pdf").blob() == raw
            assert load(copy).round(0).evidence_sources == {
                "paper.pdf": raw,
                "empty.bin": b"",
            }
            # the explorer never prints the bytes, only measures them
            tag = f"<{len(raw)} bytes>"
            assert render_value(src.child("paper.pdf").get()) == tag
            assert tag in render_value(src.get())
            previews = {n: p for n, _, p in list_children(root.store, src.key)}
            assert previews["paper.pdf"] == tag, previews
            out = export_part(root.store, src.child("paper.pdf").key, Path(d) / "p.pdf")
            assert out.read_bytes() == raw
            export_part(root.store, src.key, Path(d) / "sources.yaml")
            export_part(root.store, src.key, Path(d) / "sources.json")
    print("  blobs          bytes stay bytes through load, commit and show; b'' stores")


def test_a_failed_write_leaves_the_old_content() -> None:
    """A value neither h5py nor yaml can store leaves the old group as it
    was, never a partial one — `_write` writes the new group before it drops
    the old — and a NUL in a string is escaped, so it is storable."""
    with temp_record() as root:
        st = root.store
        st.put("k", {"a": 1, "b": "ok"})
        try:
            st.put("k", {"a": 2, "b": object()})
        except Exception:  # noqa: BLE001 - whatever hdfdict raises for it
            pass
        else:
            raise AssertionError("an unstorable value was written")
        assert st.get("k") == {"a": 1, "b": "ok"}, st.get("k")
        assert st.keys("") == ["k"], st.keys("")  # nothing temporary left behind
        # a NUL in a string is stored as its escaped literal, keys included
        n = root / "rounds/round_0/x"
        n.put({"s": "a\x00b", "l": ["\x00"], "k\x00": 1})
        assert n.get() == {"s": "a\\x00b", "l": ["\\x00"], "k\\x00": 1}, n.get()
        (root / "t").put_text("x\x00y")
        assert (root / "t").text() == "x\\x00y"
        # a write KILLED before its move leaves `<name>%tmp` beside the old
        # group: not a child, not a candidate, not in the loaded record — and
        # a real name spelt with `%tmp` is a different raw name (`%25tmp`)
        r0 = root / "rounds/round_0"
        (r0 / "candidates/c1/petab/parameters").put({"columns": [], "data": {}})
        (r0 / "candidates/c1%tmp/note").put_text("a real key, escaped")
        with h5py.File(st.path, "a") as f:
            f["rounds/round_0/candidates"].require_group("c1%tmp").create_dataset(
                "half", data=1
            )
        assert (r0 / "candidates").children() == ["c1", "c1%tmp"], (
            r0 / "candidates"
        ).children()
        assert (r0 / "candidates").get() == {
            "c1": {"petab": {"parameters": {"columns": [], "data": {}}}},
            "c1%tmp": {"note": "a real key, escaped"},
        }, (r0 / "candidates").get()
        walked = {k for k, _ in st.walk("rounds")}
        assert "rounds/round_0/candidates/c1%tmp/note" in walked
        assert "rounds/round_0/candidates/c1%tmp/half" not in walked, walked
        loaded = st.load().round(0).candidates
        assert set(loaded) == {"c1", "c1%tmp"}, set(loaded)
        assert loaded["c1%tmp"].model_extra.get("note") == "a real key, escaped"
        (r0 / "candidates/c1").put({"x": 1})  # the next write of the key cleans up
        with h5py.File(st.path, "r") as f:
            assert "c1%tmp" not in f["rounds/round_0/candidates"]
    print(
        "  failed write   the old content stays; a NUL in a string is escaped; "
        "a killed write's %tmp is invisible"
    )


def test_put_returns_the_sha_of_what_reads_back() -> None:
    """HDF5 stores `[0, 10.0]` as `[0.0, 10.0]` and `[True, 1]` as `[1, 1]`,
    and a marker check computes the sha of the value read, so the sha `put`
    returns is of the value read back, not of the value written."""
    with temp_record() as root:
        n = root / "x"
        for value in ([0, 10.0], [True, 1], {"v": [0, 10.0], "w": [True, 1]}):
            assert n.put(value) == n.sha(), value
        assert n.get() == {"v": [0.0, 10.0], "w": [1, 1]}, n.get()
    print("  put sha        the sha a writer gets is the one a reader computes")


def test_a_legacy_ledger_is_converted_whole() -> None:
    """hdfdict writes a list of dicts as BLOCK yaml, not `- {json}` lines;
    the converter reads its rows whole, so the first append adds one row
    instead of replacing the ledger with it."""
    from mkstd.standards.hdfdict import hdfdict

    from octomod.result.runstore import RecordDamaged

    rows = [
        {"ts": "t0", "event": "run_start", "round": 0},
        {"ts": "t1", "event": "note", "note": "x"},
    ]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "legacy.h5"
        with h5py.File(p, "w") as f:
            hdfdict.dump({"ledger": rows}, f)  # a ledger in hdfdict's own form
        st = RunStore(p)
        assert st.ledger_rows() == rows, st.ledger_rows()
        st.append_ledger({"ts": "t2", "event": "run_end"})
        assert [r["ts"] for r in st.ledger_rows()] == ["t0", "t1", "t2"]
        # a ledger whose rows do not parse is never replaced
        with h5py.File(p, "a") as f:
            del f["ledger"]
            ds = f.create_dataset("ledger", data=np.bytes_("- [unclosed\n"))
            ds.attrs.create("_type_", np.bytes_("yaml"))
        try:
            RunStore(p).append_ledger({"ts": "t3"})
        except RecordDamaged:
            pass
        else:
            raise AssertionError("an unparsable ledger was replaced")
        with h5py.File(p, "r") as f:
            assert f["ledger"][()] == b"- [unclosed\n"
    print("  legacy ledger  block-yaml rows converted whole; unparsable ones kept")


def test_remove_takes_the_leftovers() -> None:
    """`remove()` takes `<id>.h5.damaged`, `<id>.compact.tmp` and
    `<id>.h5.tmp` with the record."""
    with temp_record() as root:
        st = root.store
        (root / "run").put({"run_id": "x"})
        st.checkpoint()
        left = [
            st.path.with_name(st.path.name + ".damaged"),
            st.path.with_name(st.path.name + ".tmp"),
            st.path.with_suffix(".compact.tmp"),
            st.path.with_name(st.path.name + ".abc123.tmp"),  # write_all's
        ]
        for p in left:
            p.write_bytes(b"")
        removed = st.remove()
        assert not any(p.exists() for p in [st.path, st.backup_path, *left])
        assert set(removed) >= {p.name for p in left}, removed
    print("  remove         the damaged file and the temporary copies go too")


if __name__ == "__main__":
    test_candidates_never_include_the_single_workdir()
    test_a_write_replaces_the_group()
    test_the_core_alone_is_not_a_report()
    test_a_malformed_entry_is_left_out_on_load()
    test_keys_are_whole_and_missing_is_loud()
    test_a_block_of_reads_is_one_open()
    test_a_marker_hashes_each_part_once()
    test_commit_and_load_agree_on_the_target()
    test_track_order_is_scoped_to_our_writes()
    test_what_goes_in_comes_out()
    test_readings_are_derived_on_load()
    test_second_review_findings()
    test_a_store_that_does_not_exist_reads_as_empty()
    test_blobs_stay_bytes_through_load_and_commit()
    test_a_failed_write_leaves_the_old_content()
    test_put_returns_the_sha_of_what_reads_back()
    test_a_legacy_ledger_is_converted_whole()
    test_remove_takes_the_leftovers()
    print("RECORD NODE OK")
