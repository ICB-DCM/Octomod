"""Every legacy run DIRECTORY transcribes into a run record and survives
HDF5.

The engine writes `runs/<id>.h5` directly, addressed by record key; the
importer is the LEGACY path, `./run.sh import-legacy --run-dir <dir>`, for
legacy run directories. It is a TRANSCRIPTION: every file goes, through
its codec, to the record key the engine writes that artifact to today
(`importer.LEGACY_NAMES`), into a NEW record file. Its fixtures are
directories, by design; the directory sweep skips the records (`runs/*.h5`),
which get a sweep of their own (the newest finished ones load and round-trip).

If the importer cannot transcribe a run, the record cannot describe that run.
Two levels:

  fixtures   the two runs the design document traces by hand —
             `runs/expansion_smoke` (search, then expansion) and
             `runs/smoke_abcd_pred_170117` (single model, then revision) —
             transcribed into a throwaway record, with the facts that page
             states asserted one by one on the typed record read back;
  sweep      every other run directory under `runs/` (newest first, capped
             unless --all) must transcribe with no unreadable file and no
             file the table does not know, and round-trip through HDF5 with
             zero differences;
  input      the input rows, on a fabricated legacy folder: its `input/`
             took the whole case, and the record keeps what a run reads of
             it (`run_folder.inputs_read`), listing the rest as skipped.

`runs/` is gitignored and empty on a fresh checkout, so the fixture and sweep
levels SKIP with a reason rather than failing when nothing is on disk.

    uv run python tests/result_import_unit.py [--all] [--limit N]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration import run_folder  # noqa: E402
from octomod.result import commit, load  # noqa: E402
from octomod.result.access import record_for  # noqa: E402
from octomod.result.importer import ImportReport, import_run, resolve  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402

RUNS = config.RUNS_DIR


@contextlib.contextmanager
def transcribed(run_dir: Path):
    """`run_dir` transcribed into a throwaway record: (report, typed record)."""
    with tempfile.TemporaryDirectory() as d:
        store = RunStore(Path(d) / f"{run_dir.name}.h5")
        rep = import_run(run_dir, store)
        yield rep, record_for(store)


def _clean(rep: ImportReport, where: str) -> None:
    """Every file was transcribed or deliberately skipped: none unreadable,
    none the table does not know."""
    assert not rep.failed, f"{where}: unreadable files:\n  " + "\n  ".join(
        rep.failed[:15]
    )
    assert not rep.unknown, f"{where}: files the table does not know:\n  " + (
        "\n  ".join(rep.unknown[:15])
    )


def _diffs(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in set(x) | set(y):
            if k not in x or k not in y:
                yield f"{path}/{k}: only on one side"
                continue
            yield from _diffs(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        if len(x) != len(y):
            yield f"{path}: length {len(x)} vs {len(y)}"
            return
        for i, (u, v) in enumerate(zip(x, y, strict=False)):
            yield from _diffs(u, v, f"{path}[{i}]")
    else:
        if (
            isinstance(x, float)
            and isinstance(y, float)
            and math.isnan(x)
            and math.isnan(y)
        ):
            return
        if x != y:
            yield f"{path}: {x!r} != {y!r}"


def _roundtrip(rr, where: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        back = load(commit(rr, Path(d) / "roundtrip.h5"))
    diffs = list(_diffs(rr.model_dump(), back.model_dump()))
    assert not diffs, f"{where}: HDF5 round trip changed the record:\n  " + "\n  ".join(
        diffs[:15]
    )


def _finished(run_dir: Path) -> bool:
    """The fixture runs are re-made by their own smoke suites (`expansion_smoke`
    is `tests/expansion_smoke.py`'s run id), so under the battery one may be
    mid-flight; the facts asserted here are about a FINISHED run."""
    ledger = run_dir / "ledger.jsonl"
    return ledger.exists() and '"run_end"' in ledger.read_text()


def test_expansion_fixture() -> None:
    run_dir = RUNS / "expansion_smoke"
    if not run_dir.is_dir():
        print("  SKIP: runs/expansion_smoke is not on this machine")
        return
    if not _finished(run_dir):
        print(
            "  SKIP: runs/expansion_smoke has not finished (its suite may be running)"
        )
        return
    with transcribed(run_dir) as (rep, rr):
        _clean(rep, "expansion_smoke")
        _check_expansion(rr)


def _check_expansion(rr) -> None:
    assert rr.round_indices == [0, 1]
    assert rr.outcome and rr.outcome.outcome == "completed"
    r0, r1 = rr.round(0), rr.round(1)
    assert r0.shape == "candidate_set" and set(r0.candidates) == {
        "base",
        "product_feedback",
    }
    assert r0.selection and r0.selection.winner == "product_feedback"
    assert r0.selection.criterion == "AIC" and len(r0.selection.values) == 2
    # petab_select's own files are the round's `selection_files`, as text
    assert {"models.yaml", "model_space.tsv"} <= set(r0.selection_files)
    assert len(yaml.safe_load(r0.selection_files["models.yaml"])) == 2
    assert (
        r0.expansion and r0.expansion.expanded and r0.expansion.axes == ["basal_route"]
    )
    # the offer and the diagnostics are the round's own siblings
    assert r0.expansion_offer and r0.expansion_offer.get("approved") is True
    assert r0.expansion_diagnostics and r0.expansion_diagnostics.get("steps")
    assert "revision" in r0.agent_calls
    assert any(
        e.event == "redraft" and (e.model_extra or {}).get("role") == "revision"
        for e in rr.ledger
    ), "the ghost_sink redraft is on record"
    # …and the typed readings `derive` fills from it on load
    assert r0.agent_calls["revision"].redrafts, "the call's redrafts"
    assert any(f["kind"] == "redraft" for f in rr.failures()), "failures() sees it"
    assert set(r0.decisions) >= {
        "model_scope",
        "assembly_cost_boundary",
        "evaluation_verdict",
    }
    # the human gates a directory kept only in its ledger are in the ledger
    asked = {e.module for e in rr.ledger if e.event == "human_gate"}
    assert asked >= {
        "model_scope",
        "assembly_cost_boundary",
        "cost_boundary_estimation",
        "evaluation_verdict",
        "revision",
    }, sorted(asked)
    pf = r0.candidates["product_feedback"]
    assert pf.estimation and pf.estimation.n_starts == 100
    assert pf.starts and pf.starts.n_rows == 100, "every start, from starts.csv"
    assert (
        pf.multistart and pf.multistart.get("n_starts") == 100
    ), "every start's end point, from optimize_result.h5"
    assert len(pf.multistart["x"]) == 100, "the arrays hold every start, not a count"
    assert pf.petab and pf.petab.measurements.n_rows == 192
    assert int(pf.petab.parameters.to_dataframe().estimate.sum()) == 10
    assert (pf.markers.get("s3") or {}).get("n_estimated") == 10
    assert pf.petab.n_estimated == 10 and pf.petab.n_train == 192, "derived sizes"
    assert pf.cost and pf.cost.proposed_n_starts == 100
    assert (pf.markers.get("cost") or {}).get("approved_n_starts") == 100
    assert pf.cost.approved_n_starts == 100, "derived from the cost marker"
    assert (
        "estimation_waterfall_plateau" in pf.gates
        and pf.gates["estimation_waterfall_plateau"].passed
    )
    assert (
        not pf.gates["evaluation_t2prime_holdout"].passed
        and not pf.gates["evaluation_t2prime_holdout"].blocking
    )
    # what round 1 was seeded with, and who is recorded as producing it
    assert r1.shape == "candidate_set" and set(r1.candidates) == {"base", "basal_route"}
    assert (
        r1.status and (r1.status.markers.get("s1") or {}).get("producer")
    ) == "seeded-from-previous-round", (
        "the expansion seed must not be labelled user-supplied"
    )
    assert r1.model and r1.model.antimony, "round 1's seeded model is transcribed"
    assert r1.model.producer == "seeded-from-previous-round", "derived from s1"
    axes = {a.id: a for a in (r1.space.axes if r1.space else [])}
    assert "basal_route" in axes, "the declared axis reaches round 1's space"
    assert axes["basal_route"].frozen is False
    assert r1.selection and r1.selection.winner == "basal_route"
    assert (
        r1.data
        and r1.data.measurements
        and r1.data.measurements.n_rows == r0.data.measurements.n_rows
    ), "data is carried forward whole"
    assert (
        r0.data.n_rows == r0.data.measurements.n_rows == r1.data.n_rows
    ), "the derived row count is the table's"
    assert r0.status and set(r0.status.markers) >= {
        "s1",
        "s2",
        "s7",
        "candidate_compile",
    }
    _roundtrip(rr, "expansion_smoke")
    print(
        f"  expansion_smoke   2 rounds, winner {r1.selection.winner}, "
        f"{len(rr.ledger)} ledger rows, HDF5 lossless"
    )


def test_revision_fixture() -> None:
    run_dir = RUNS / "smoke_abcd_pred_170117"
    if not run_dir.is_dir() or not _finished(run_dir):
        print("  SKIP: runs/smoke_abcd_pred_170117 is not on this machine (finished)")
        return
    with transcribed(run_dir) as (rep, rr):
        _clean(rep, "smoke_abcd_pred_170117")
        _check_revision(rr)


def _check_revision(rr) -> None:
    assert rr.round_indices == [0, 1]
    r0, r1 = rr.round(0), rr.round(1)
    assert r0.shape == "single" and list(r0.candidates) == ["_single"]
    single = r0.candidates["_single"]
    assert single.model is None, "the single candidate's model IS the round's"
    assert r0.model and r0.model.antimony
    assert single.estimation and single.estimation.n_starts == 100
    assert single.petab and single.petab.holdout_measurements.n_rows == 48
    assert int(single.petab.parameters.to_dataframe().estimate.sum()) == 9
    assert single.petab.n_estimated == 9 and single.petab.n_holdout == 48, "derived"
    assert r0.evaluation and r0.evaluation.t2prime_passed is False
    assert (r0.evaluation.interpretation or {}).get("recommendation") == "revise"
    assert r0.revision and r0.revision.move["type"] == "add_reaction"
    # the revised configuration's hash and optimum are the history's
    assert rr.history and rr.history[0]["round"] == 0
    assert rr.history[0]["config_hash"] and rr.history[0]["best_fval"] is not None
    assert r0.gates and not single.gates, "single round: gates kept once, on the round"
    assert "estimation_waterfall_plateau" in r0.gates
    assert r1.directive and r1.directive.startswith("Add a reaction")
    assert r1.evaluation is None, "the smoke stopped after S3"
    assert (
        r1.status and (r1.status.markers.get("s1") or {}).get("producer")
    ) == "agent:construction"
    assert r1.model and r1.model.producer == "agent:construction", "derived from s1"
    assert any(q.raised_round == 0 for q in rr.questions)
    assert rr.outcome and rr.outcome.outcome == "stopped"
    assert any(f["kind"] == "run_end" for f in rr.failures())
    _roundtrip(rr, "smoke_abcd_pred_170117")
    print("  smoke_abcd_pred   single → revision, DIRECTIVE carried, HDF5 lossless")


def test_sweep(limit: int | None) -> None:
    if not RUNS.exists():
        print("  SKIP: no runs/ directory on this machine")
        return
    dirs = [
        p
        for p in RUNS.iterdir()
        if p.is_dir()  # records are files (runs/*.h5); only directories import
        and not p.name.startswith("_")
        and ((p / "run_meta.json").exists() or (p / "ledger.jsonl").exists())
        and _finished(p)
    ]
    if not dirs:
        print("  SKIP: runs/ holds no run directories")
        return
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if limit is not None:
        dirs = dirs[:limit]
    t0 = time.time()
    failures: list[str] = []
    n_rounds = 0
    for d in dirs:
        try:
            with transcribed(d) as (rep, rr):
                _clean(rep, d.name)
                n_rounds += len(rr.rounds)
                _roundtrip(rr, d.name)
        except Exception as e:  # noqa: BLE001 - collected and reported together
            failures.append(f"{d.name}: {type(e).__name__}: {str(e)[:200]}")
    assert not failures, (
        f"{len(failures)} of {len(dirs)} run directories did not transcribe or "
        f"round-trip:\n  " + "\n  ".join(failures[:20])
    )
    print(
        f"  sweep             {len(dirs)} runs, {n_rounds} rounds transcribed and "
        f"round-tripped in {time.time() - t0:.0f} s"
    )


def test_input_rows() -> None:
    """The input rows: `input/source.json` becomes `input_source`, every other
    `input/` file keeps its path under `input/`, and of a legacy folder's
    `input/` only what a run reads is written — the rest is skipped, never
    unknown. Fabricated, so it runs on a fresh checkout."""
    assert resolve("input/source.json") == ("input_source", "json")
    assert resolve("input/data/x.csv") == ("input/data/x.csv", "input")
    intent = (
        "question: q\n"
        "supplied_literature:\n"
        "  - source: a methods section\n"
        "    supports: the assay's floor\n"
        "    url: file:./paper/cited.md\n"
    )
    files = {
        "intent.yaml": intent,
        "description.md": "# lab note\n",
        "testcase.yaml": "name: legacy\n",
        "data/x.csv": "t,y\n0,1\n",
        "stubs/construction.json": "{}\n",
        "paper/cited.md": "the cited methods\n",
        "paper/uncited.pdf": "%PDF-1.4\n",
        "raw_fcs/A01.fcs": "raw instrument bytes\n",
        "preprocessing/gate.py": "print('gating')\n",
        "curation/STAGING-LOG.md": "# log\n",
        "notes/call.md": "what was said\n",
        "make_data.py": "print('a generator')\n",
        ".DS_Store": "finder\n",
        "source.json": json.dumps({"run_id": "legacy_input", "project": "legacy"}),
    }
    with tempfile.TemporaryDirectory() as d:
        run_dir = Path(d) / "legacy_input"
        for rel, text in files.items():
            (run_dir / "input" / rel).parent.mkdir(parents=True, exist_ok=True)
            (run_dir / "input" / rel).write_text(text)
        (run_dir / "ledger.jsonl").write_text(
            json.dumps({"event": "run_start", "ts": "now"}) + "\n"
        )
        store = RunStore(Path(d) / "legacy_input.h5")
        rep = import_run(run_dir, store)
        _clean(rep, "legacy_input")
        root = Node(store)
        want = [r.as_posix() for r in run_folder.inputs_read(run_dir / "input")]
        assert want == [
            "data/x.csv",
            "description.md",
            "intent.yaml",
            "paper/cited.md",
            "stubs/construction.json",
            "testcase.yaml",
        ], want
        assert run_folder.entries(root) == want, run_folder.entries(root)
        not_read = {
            f"input/{rel}" for rel in files if rel not in want and rel != "source.json"
        }
        assert set(rep.skipped) == not_read, sorted(set(rep.skipped) ^ not_read)
        assert (root / run_folder.SOURCE_KEY).get()["run_id"] == "legacy_input"
    print(
        f"  input rows        {len(want)} of {len(files) - 1} input files kept (what "
        f"a run reads), {len(rep.skipped)} skipped, input_source written"
    )


def _ended(store: RunStore) -> bool:
    try:
        return any(r.get("event") == "run_end" for r in store.ledger_rows())
    except Exception:  # noqa: BLE001 - an unreadable record is not a finished run
        return False


def test_record_sweep(limit: int = 10) -> None:
    """The newest finished records the ENGINE wrote (`runs/*.h5`) load
    with their derived readings and round-trip through HDF5 unchanged — the
    readers' path, which the directory sweep above never exercises."""
    stores = [s for s in RunStore.all_in(RUNS) if _ended(s)]  # oldest first
    if not stores:
        print("  SKIP: runs/ holds no finished record")
        return
    stores = stores[-limit:]
    t0 = time.time()
    failures: list[str] = []
    n_rounds = 0
    for s in stores:
        try:
            rr = s.load()
            n_rounds += len(rr.rounds)
            _roundtrip(rr, s.run_id)
        except Exception as e:  # noqa: BLE001 - collected and reported together
            failures.append(f"{s.run_id}: {type(e).__name__}: {str(e)[:200]}")
    assert not failures, (
        f"{len(failures)} of {len(stores)} records did not load or round-trip:\n  "
        + "\n  ".join(failures[:20])
    )
    print(
        f"  records           {len(stores)} runs/*.h5, {n_rounds} rounds loaded and "
        f"round-tripped in {time.time() - t0:.0f} s"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all", action="store_true", help="sweep every run, not the newest 12"
    )
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    for name, fn in (
        ("test_input_rows", test_input_rows),
        ("test_expansion_fixture", test_expansion_fixture),
        ("test_revision_fixture", test_revision_fixture),
    ):
        print(name)
        fn()
    print("test_sweep")
    test_sweep(None if args.all else args.limit)
    print("test_record_sweep")
    test_record_sweep()
    print("OK")
