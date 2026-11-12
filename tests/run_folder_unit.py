"""A run carries its own inputs, and the run record is the record.

The run is one file, `runs/<id>.h5`; its inputs are the record's `input`
group (beside `input_source`, a legacy run folder's `input/source.json`), and
its rendered documents live under `runs/<id>_reports/`.

  a. `--testcase` snapshots what a run reads into `input` (no `truth/`, no staging files); the `run` record and ledger agree on the sha;
  b. a run started from an in-record `input` group, with no `--testcase`, walks the stub golden path;
  c. editing a file under `input` mid-run refuses the resume and names the file;
  d. neither `--testcase` nor `input` is refused by name, before anything is spent;
  e. an `input` copied from another run records `started_from` (`input_source` travels with it);
  f. a run record without `input` still opens in `status` and `report`, and still resumes;
  g. a project run under the user's runs/ appends to
     `<runs>/_projects/<project>/tried_models.json` for the next one; the
     suite's own runs, which live elsewhere, append nothing and say so.

    uv run python tests/run_folder_unit.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check_records_complete, finish  # noqa: E402
from _record import ledger_rows, pending_gate, reports_dir, run_root  # noqa: E402

from octomod.orchestration import run_folder, run_guard  # noqa: E402


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(f"{name}: {detail}")


def engine(*args: str, runs_dir: Path, cwd: Path | None = None):
    """The engine as an operator invokes it, in its own runs directory."""
    env = dict(os.environ)
    env["OCTOMOD_RUNS_DIR"] = str(runs_dir)
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    return subprocess.run(
        [sys.executable, "-m", "octomod", *args],
        cwd=str(cwd or REPO),
        env=env,
        capture_output=True,
        text=True,
    )


def stub_run(*args: str, runs_dir: Path):
    return engine(
        "run", "--backend", "stub", "--auto-approve", *args, runs_dir=runs_dir
    )


def stage_case(source: Path, dest: Path) -> Path:
    """A staged case folder on disk holding what a run reads of `source`
    (`run_folder.inputs_read`; `run_folder.snapshot` writes into a record, so
    a folder copy is made here)."""
    dest.mkdir(parents=True, exist_ok=True)
    for rel in run_folder.inputs_read(source):
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, dest / rel)
    return dest


def input_files(root) -> list[str]:
    """Every file of the record's `input` group (relative posix paths)."""
    return run_folder.entries(root)


# --------------------------------------------------------------- a. snapshot

# What section (a) built, so the overwrite section can re-use a finished
# --testcase run instead of paying for another one. This suite is the quick
# tier's critical path, so a fixture two sections both need is built once.
SNAPSHOT: dict = {}


def test_a_testcase_start_snapshots_and_excludes_truth(tmp: Path) -> None:
    runs = tmp / "runs_a"
    rid = "runfolder_snap"
    # A case of our own, carrying BOTH things the snapshot must leave behind.
    # Fabricated rather than borrowed so the exclusion is proved against files
    # that certainly exist — and so this suite never goes near a real truth/.
    case = tmp / "case_a"
    stage_case(REPO / "testcase" / "toy_phos", case)
    (case / "truth").mkdir(parents=True, exist_ok=True)
    (case / "truth" / "ANSWER.txt").write_text("the answer this run must not see\n")
    (case / "tried_models.json").write_text('{"entries": []}\n')
    # and what a staging folder carries beside its inputs, which no run reads
    staging = {
        "raw_fcs/plate_A01.fcs": "raw instrument bytes\n",
        "curation/STAGING-LOG.md": "# log\n",
        "notes/call.md": "what the user said\n",
        "make_data.py": "print('a generator')\n",
        "ASSUMPTIONS.md": "# assumptions\n",
    }
    for rel, text in staging.items():
        (case / rel).parent.mkdir(parents=True, exist_ok=True)
        (case / rel).write_text(text)
    read = [r.as_posix() for r in run_folder.inputs_read(case)]

    rc = stub_run("--testcase", str(case), "--run-id", rid, runs_dir=runs)
    check("a --testcase start completes", rc.returncode == 0, rc.stderr[-300:])
    SNAPSHOT.update(runs=runs, rid=rid, case=case)
    root = run_root(rid, runs)
    inp = run_folder.input_node(root)
    check("it wrote input/", inp.exists())
    for want in ("intent.yaml", "description.md", "testcase.yaml", "data"):
        check(f"input/ carries {want}", inp.child(want).exists())
    # the two exclusions, which are the whole reason the snapshot is not `cp -R`
    check(
        "the source case really does carry both, so the exclusions mean something",
        (case / "truth" / "ANSWER.txt").exists()
        and (case / "tried_models.json").exists(),
    )
    check("truth/ is NOT in the snapshot", not inp.child("truth").exists())
    check(
        "not one file of it, however deep",
        not [f for f in input_files(root) if Path(f).name == "ANSWER.txt"],
    )
    check(
        "tried_models.json is NOT in the snapshot",
        not [f for f in input_files(root) if Path(f).name == "tried_models.json"],
    )
    check(
        "nor any staging file a run does not read",
        not set(staging) & set(input_files(root)),
        str(sorted(set(staging) & set(input_files(root)))),
    )
    check(
        "the snapshot is exactly what a run reads of the case",
        input_files(root) == read,
        f"{input_files(root)} vs {read}",
    )

    meta = (root / "run").get()
    check("run_meta records the input sha", bool(meta.get("input_sha")))
    check("run_meta records the project", meta.get("project") == "case_a")
    check(
        "run_meta records a per-file manifest, which is what names a drifted file",
        len(meta.get("input_files") or {}) >= 4,
        str(len(meta.get("input_files") or {})),
    )
    check(
        "the recorded sha is the sha of what is on disk",
        meta["input_sha"] == run_guard.input_sha(root),
    )
    rows = ledger_rows(root)
    snap = [r for r in rows if r.get("producer") == "snapshot"]
    check("a ledger artifact row records the snapshot", len(snap) == 1)
    if snap:
        check(
            "and it agrees with run_meta on the sha, and names the source",
            snap[0].get("sha") == meta["input_sha"]
            and snap[0].get("source", "").endswith("case_a"),
            f"{snap[0].get('sha')} vs {meta['input_sha']}",
        )


# ------------------------------------------------------------- b. in place


def author_input(root, case: str = "toy_phos"):
    """An `input` group authored in the record, copied from a staged case so its content is good."""
    if not root.store.exists_on_disk():
        root.store.create()
    run_folder.snapshot(REPO / "testcase" / case, root)
    return run_folder.input_node(root)


def test_an_authored_input_runs_with_no_testcase(tmp: Path) -> None:
    # the project fixture's first run is exactly this case: an `input` group
    # authored in the record, a timestamped run id, no --testcase
    runs, rid, _second = project_fixture(tmp)
    root = run_root(rid, runs)
    check(
        "a run with NO --testcase completes on its own input/",
        PROJECT["first_rc"].returncode == 0,
        PROJECT["first_rc"].stderr[-400:],
    )
    check(
        "it produced the run-level document",
        (reports_dir(root) / "ANALYSIS.html").exists(),
    )
    check(
        "it produced a round report",
        (reports_dir(root) / "round_0" / "report").is_dir(),
    )
    meta = (root / "run").get()
    check(
        "the project is the run id with its timestamp removed",
        meta.get("project") == "proj",
        str(meta.get("project")),
    )
    check(
        "and `testcase` is empty, because there was none",
        meta.get("testcase") == "",
        repr(meta.get("testcase")),
    )
    check(
        "the inputs say so in words",
        meta.get("input_source") == "authored in place",
        str(meta.get("input_source")),
    )


# ------------------------------------------- b2. --testcase after a snapshot


def test_an_edited_testcase_after_a_snapshot_is_refused(tmp: Path) -> None:
    """Once the record holds its `input` snapshot, a `--testcase` passed again
    is compared with it: identical proceeds on the record's inputs, edited is
    refused by name (never reuse silently). No engine run."""
    runs = tmp / "runs_b2"
    runs.mkdir(parents=True, exist_ok=True)
    case = stage_case(REPO / "testcase" / "toy_phos", tmp / "b2_case" / "toy_phos")
    rid = "b2_other_name"  # not the case's name: the project must come from the record
    root = run_root(rid, runs)
    first = run_folder.plan(root, case)
    check("a fresh --testcase plans a snapshot", first.mode == "snapshot", first.mode)
    got = run_folder.materialise(first, root, run_id=rid)
    run_folder.release(got)
    check(
        "release removes the materialised input directory",
        not Path(got.dir).exists(),
        str(got.dir),
    )

    same = run_folder.plan(root, case)
    check(
        "an unedited --testcase proceeds on the record's inputs",
        same.mode == "in_record" and same.matched == case.resolve(),
        f"{same.mode} {same.matched}",
    )
    check(
        "… with the project the record stored",
        same.project == "toy_phos",
        same.project,
    )
    resumed = run_folder.plan(root, None)
    check(
        "a --run-id-only resume keeps the stored project and source case",
        resumed.mode == "in_record"
        and resumed.project == "toy_phos"
        and resumed.source == case.resolve()
        and resumed.matched is None,
        f"{resumed.project} {resumed.source} {resumed.matched}",
    )

    data = sorted((case / "data").rglob("*.*"))[0]
    data.write_text(data.read_text() + "\n")
    try:
        run_folder.plan(root, case)
        refused = None
    except run_guard.RunIdRefused as e:
        refused = str(e)
    check(
        "an edited --testcase after the snapshot is refused",
        refused is not None,
        "planned without a refusal",
    )
    rel = data.relative_to(case).as_posix()
    check(
        "… naming the edited file and the ways on",
        refused is not None
        and f"{rel} — edited" in refused
        and "--overwrite" in refused
        and "--from-run" in refused,
        (refused or "")[:400],
    )
    fresh = run_folder.plan(root, case, overwrite=True)
    check(
        "--overwrite takes a fresh snapshot of the edited case",
        fresh.mode == "snapshot",
        fresh.mode,
    )


# --------------------------------------------------------------- c. drift


def test_an_interrupted_snapshot_is_taken_again(tmp: Path) -> None:
    """A kill in the first second of a run can leave an `input` group without
    its pending mark cleared (set before the first file, cleared after the last): that is not the run's
    inputs, and not an edit to refuse — the next start takes the snapshot
    again. The crash suite's placed kill can land there. No engine run."""
    runs = tmp / "runs_b3"
    runs.mkdir(parents=True, exist_ok=True)
    case = stage_case(REPO / "testcase" / "toy_phos", tmp / "b3_case" / "toy_phos")
    rid = "b3_cut_short"
    root = run_root(rid, runs)
    got = run_folder.materialise(run_folder.plan(root, case), root, run_id=rid)
    run_folder.release(got)
    check("a whole snapshot is complete", run_folder.is_complete(root))
    # what the kill leaves: part of the files, the pending mark still set
    (root / run_folder.PENDING_KEY).put({"from": str(case)})
    for rel in run_folder.entries(root)[: len(run_folder.entries(root)) // 2]:
        run_folder._entry(run_folder.input_node(root), Path(rel)).delete()
    check("a cut-short snapshot is not complete", not run_folder.is_complete(root))
    again = run_folder.plan(root, case)
    check(
        "the next start takes the snapshot again instead of refusing an 'edit'",
        again.mode == "snapshot",
        again.mode,
    )
    got = run_folder.materialise(again, root, run_id=rid)
    run_folder.release(got)
    check(
        "and it is whole afterwards, identical to the case",
        run_folder.is_complete(root)
        and run_guard.manifest(root) == run_guard.manifest(case),
    )


def test_editing_input_mid_run_refuses_the_resume_naming_the_file(tmp: Path) -> None:
    runs = tmp / "runs_c"
    rid = "runfolder_drift"
    root = run_root(rid, runs)
    author_input(root)
    # pause it at the first gate rather than running it out
    rc = engine(
        "run",
        "--run-id",
        rid,
        "--backend",
        "stub",
        "--gate-mode",
        "file",
        runs_dir=runs,
    )
    check("the run pauses at a gate (exit 3)", rc.returncode == 3, str(rc.returncode))
    check("and leaves a pending gate", pending_gate(root) is not None)

    # resuming untouched is fine — the guard must not refuse its own snapshot
    rc = engine(
        "run",
        "--run-id",
        rid,
        "--backend",
        "stub",
        "--gate-mode",
        "file",
        "--gate-answer",
        "y",
        runs_dir=runs,
    )
    check(
        "an untouched resume is NOT refused",
        rc.returncode in (0, 3),
        f"exit {rc.returncode}: {rc.stderr[-200:]}",
    )

    # now move one input file, the way an over-helpful editor would
    victim = run_folder.input_node(root).child("description.md")
    victim.put_text(victim.text() + "\n\n(an edit made while paused)\n")
    rc = engine(
        "run",
        "--run-id",
        rid,
        "--backend",
        "stub",
        "--gate-mode",
        "file",
        "--gate-answer",
        "y",
        runs_dir=runs,
    )
    msg = rc.stdout + rc.stderr
    check("the resume is refused (exit 1)", rc.returncode == 1, str(rc.returncode))
    check("the refusal says the inputs drifted", "drifted" in msg)
    check(
        "and NAMES the file, not just the digest",
        "description.md — edited" in msg,
        msg[-300:],
    )


# ------------------------------------------------------------- d. no inputs


def test_no_testcase_and_no_input_is_refused_by_name(tmp: Path) -> None:
    runs = tmp / "runs_d"
    rid = "runfolder_nothing"
    rc = stub_run("--run-id", rid, runs_dir=runs)
    msg = rc.stdout + rc.stderr
    check("refused (exit 2)", rc.returncode == 2, str(rc.returncode))
    check("the refusal names --testcase", "--testcase" in msg)
    check("and names the input/ folder it wanted", "input" in msg)
    check(
        "nothing was spent: no run record, no ledger",
        not run_root(rid, runs).store.exists_on_disk(),
    )
    # and with neither a run-id nor a testcase there is nothing to name at all
    rc = stub_run(runs_dir=runs)
    check(
        "--run-id-less and --testcase-less is refused too",
        rc.returncode == 2,
        str(rc.returncode),
    )


# ---------------------------------------------------------- e. started_from


PROJECT: dict = {}


def project_fixture(tmp: Path) -> tuple[Path, str, str]:
    """Two runs of one project, the second a copy of the first's `input/`;
    built once, and section (b) reads the first as its authored-input run."""
    if PROJECT:
        return PROJECT["runs"], PROJECT["first"], PROJECT["second"]
    runs = tmp / "runs_proj"
    first, second = "proj_20260921_100000", "proj_20260921_110000"
    inp = author_input(run_root(first, runs))
    inp.child("MINE.txt").put_text("a file only the user has\n")
    rc = stub_run("--run-id", first, runs_dir=runs)
    check("the first project run completes", rc.returncode == 0, rc.stderr[-300:])
    PROJECT["first_rc"] = rc
    # what the front end does for a follow-up: copy input/, edit, run
    run_folder.copy_inputs(run_root(first, runs), run_root(second, runs))
    note = run_folder.input_node(run_root(second, runs)).child("description.md")
    note.put_text(note.text() + "\n\n(round two: the same problem, revised)\n")
    rc = stub_run("--run-id", second, runs_dir=runs)
    check("the follow-up run completes", rc.returncode == 0, rc.stderr[-300:])
    PROJECT.update(runs=runs, first=first, second=second)
    return runs, first, second


def test_a_copied_input_records_started_from(tmp: Path) -> None:
    runs, first, second = project_fixture(tmp)
    meta = (run_root(second, runs) / "run").get()
    check(
        "the follow-up records where its inputs came from",
        meta.get("started_from") == first,
        str(meta.get("started_from")),
    )
    src = (run_root(second, runs) / run_folder.SOURCE_KEY).get()
    check(
        "and input_source now names the run that owns it",
        src.get("run_id") == second and src.get("started_from") == first,
        json.dumps(src),
    )
    first_meta = (run_root(first, runs) / "run").get()
    check(
        "the first run started from nothing, and says so",
        first_meta.get("started_from") is None,
        str(first_meta.get("started_from")),
    )


# ----------------------------------------------------------- e2. overwrite


def test_overwrite_keeps_inputs_the_user_authored(tmp: Path) -> None:
    """`--overwrite` keeps an authored `input/` (the only copy) and re-takes a snapshot."""
    runs, _first, rid = project_fixture(tmp)
    root = run_root(rid, runs)
    inp = run_folder.input_node(root)
    rc = stub_run("--run-id", rid, "--overwrite", runs_dir=runs)
    check("and --overwrite re-runs it", rc.returncode == 0, rc.stderr[-300:])
    check("input/ survived", inp.exists())
    check("including a file the engine never wrote", inp.child("MINE.txt").exists())
    check(
        "what the engine wrote was rebuilt",
        (reports_dir(root) / "ANALYSIS.html").exists(),
    )
    check(
        "and the console said what it kept",
        "kept input/" in rc.stdout,
        [x for x in rc.stdout.splitlines() if "overwrite" in x][:1],
    )

    # the other half, on the finished --testcase run section (a) already made
    runs2, rid2, case = SNAPSHOT["runs"], SNAPSHOT["rid"], SNAPSHOT["case"]
    inp2 = run_folder.input_node(run_root(rid2, runs2))
    inp2.child("STRAY.txt").put_text("left over from before\n")
    rc = stub_run(
        "--testcase", str(case), "--run-id", rid2, "--overwrite", runs_dir=runs2
    )
    check("a --testcase run overwrites too", rc.returncode == 0, rc.stderr[-300:])
    check(
        "and its input/ is a fresh snapshot, so a stray file does not outlive it",
        not inp2.child("STRAY.txt").exists(),
    )


# ------------------------------------------------------------- f. no input/


def test_a_run_dir_from_before_the_record_still_opens_and_still_resumes(
    tmp: Path,
) -> None:
    """A run record with no input/ reads its testcase and is checked under `testcase_sha`."""
    # the finished --testcase run of section (a), re-run by (e2)'s --overwrite:
    # strip its input/ and restore `testcase_sha`, as a run from before
    # input/ groups carries
    runs, rid, case = SNAPSHOT["runs"], SNAPSHOT["rid"], SNAPSHOT["case"]
    root = run_root(rid, runs)
    check(
        "the seed run is a finished --testcase run",
        (root / "run").get(None) is not None and pending_gate(root) is None,
    )
    # the group and its source record (a legacy run folder keeps both under input/)
    run_folder.input_node(root).delete()
    (root / run_folder.SOURCE_KEY).delete()
    meta = (root / "run").get()
    for key in ("input_sha", "input_dir", "input_source", "input_files", "project"):
        meta.pop(key, None)
    meta["testcase_sha"] = run_guard.input_sha(case)
    (root / "run").put(meta)
    check("the fixture has no input/", not run_folder.input_node(root).exists())

    rc = engine("status", "--run-id", rid, runs_dir=runs)
    check("`status` still opens it", rc.returncode == 0, rc.stderr[-200:])
    check("and prints its markers", "round_0" in rc.stdout, rc.stdout[:200])
    rc = engine("report", "--run-id", rid, runs_dir=runs)
    check("`report` still renders it", rc.returncode == 0, rc.stderr[-200:])
    rc = engine("report", "--run-id", rid, "--analysis", runs_dir=runs)
    check("and so does the run-level ANALYSIS", rc.returncode == 0, rc.stderr[-200:])
    check("which is on disk", (reports_dir(root) / "ANALYSIS.html").exists())

    # and a resume of it re-enters without being snapshotted out from under it
    rc = stub_run(
        "--testcase",
        str(case),
        "--run-id",
        rid,
        "--from-module",
        "evaluation",
        runs_dir=runs,
    )
    check(
        "a run from before input/ folders re-enters without being refused",
        rc.returncode == 0,
        f"exit {rc.returncode}: {(rc.stdout + rc.stderr)[-400:]}",
    )
    check(
        "and it was NOT silently converted to a snapshot mid-life",
        not run_folder.input_node(root).exists(),
    )


# ------------------------------------------------------------- g. archive


def test_a_project_run_keeps_its_archive_under_projects(tmp: Path) -> None:
    from types import SimpleNamespace

    from _harness import RecordingLedger

    from octomod import config
    from octomod.orchestration.orchestrator import Orchestrator

    runs, first, second = project_fixture(tmp)
    archive = runs / "_projects" / "proj" / "tried_models.json"
    # the fixture's runs live under this suite's own runs folder, not the
    # user's: their fits must not reach a later real run as tried
    check(
        "a run outside the user's runs/ appends nothing to the archive",
        not archive.exists(),
        str(archive),
    )
    not_appended = []
    for rid in (first, second):
        rows = ledger_rows(run_root(rid, runs))
        not_appended.append(
            any(
                r.get("module") == "tried_models"
                and "not appended" in str(r.get("note", ""))
                for r in rows
            )
        )
    check("and each of them ledgers why", all(not_appended), str(not_appended))
    # the engine's own call site, for runs the user's runs/ folder holds
    saved = config.USER_RUNS_DIR, config.PROJECTS_DIR
    config.USER_RUNS_DIR, config.PROJECTS_DIR = runs, runs / "_projects"
    try:
        for rid in (first, second):
            Orchestrator._append_tried_log(
                SimpleNamespace(
                    store=run_root(rid, runs).store,
                    root=run_root(rid, runs),
                    testcase_dir=None,
                    project="proj",
                    ledger=RecordingLedger(),
                    ctx=SimpleNamespace(round_idx=0),
                )
            )
    finally:
        config.USER_RUNS_DIR, config.PROJECTS_DIR = saved
    check(
        "under the user's runs/ it appended to <runs>/_projects/<project>/"
        "tried_models.json",
        archive.exists(),
        str(archive),
    )
    if not archive.exists():
        return
    entries = json.loads(archive.read_text()).get("entries") or []
    check("the archive holds the project's models", bool(entries), str(len(entries)))
    check(
        "and nothing was written beside a testcase, because there is no testcase",
        not (REPO / "testcase" / "proj").exists(),
    )
    # both runs are in it — that is exactly what keying on `project` buys
    check(
        "the archive accumulated across both runs of the project",
        {e.get("run_id") for e in entries} == {first, second},
        str(sorted({str(e.get("run_id")) for e in entries})),
    )
    from octomod.workflow_modules.model import tried_models as T

    check(
        "and the resolver points a project run there, a testcase run beside its case",
        T.archive_for(None, "proj").name == "proj"
        and T.archive_for(REPO / "testcase" / "toy_phos", "toy_phos").name
        == "toy_phos",
    )


# ------------------------------------------------- the cache does not follow


def test_the_compile_cache_is_the_same_under_both_runs_dirs() -> None:
    """AMICI_CACHE_DIR stays at the repo root: not under RUNS_DIR, not in the user's runs/."""
    code = "from octomod import config; print(config.AMICI_CACHE_DIR)"
    seen = set()
    for runs in ("runs", "test_runs/x", str(Path(tempfile.gettempdir()) / "elsewhere")):
        env = dict(os.environ, OCTOMOD_RUNS_DIR=runs)
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
        )
        seen.add(out.stdout.strip())
    check(
        "AMICI_CACHE_DIR is the same wherever runs are written",
        len(seen) == 1,
        "; ".join(sorted(seen)),
    )
    check(
        "and it is .amici_cache at the repo root, not under any runs directory",
        seen == {str(REPO / ".amici_cache")},
        "; ".join(sorted(seen)),
    )


# --------------------------------------------------- the sweep, held in place


def test_no_suite_spells_the_runs_directory_itself() -> None:
    """No suite spells `runs/` itself, and each extends sys.path before importing the engine."""
    import ast

    # `run_all.py` is where the user's directory is DEFINED (it checks that the
    # battery left it alone), and this file states the pattern it forbids.
    exempt = {"run_all.py", "run_folder_unit.py"}
    literal, ordering = [], []
    anchor = "sys.path.insert(0, str(REPO))"
    for path in sorted((REPO / "tests").glob("*.py")):
        src = path.read_text()
        lines = src.splitlines()
        if path.name not in exempt:
            for i, line in enumerate(lines, 1):
                code = line.split("#", 1)[0]
                if 'REPO / "runs"' in code or 'REPO.glob("runs/' in code:
                    literal.append(f"{path.name}:{i}")
        a = next((i for i, x in enumerate(lines) if x.strip() == anchor), None)
        if a is None:
            continue
        # ast, not a regex: an `import octomod` inside a string template a
        # suite hands to a CHILD process is not this file's import at all
        first = min(
            (
                n.lineno
                for n in ast.parse(src).body
                if isinstance(n, (ast.Import, ast.ImportFrom))
                and (getattr(n, "module", "") or "").startswith("octomod")
            ),
            default=None,
        )
        if first is not None and first < a + 1:
            ordering.append(f"{path.name}:{first} imports before line {a + 1}")
    check(
        "no suite spells the runs directory literally",
        not literal,
        "; ".join(literal),
    )
    check(
        "every suite puts REPO on sys.path before importing the engine",
        not ordering,
        "; ".join(ordering),
    )
    # and the one place the literal is allowed says what it is for
    runner = (REPO / "tests" / "run_all.py").read_text()
    check(
        "run_all.py names the user's directory exactly once, to check it is untouched",
        runner.count('REPO / "runs"') == 1 and "USER_RUNS" in runner,
        str(runner.count('REPO / "runs"')),
    )


def main() -> int:
    t0 = time.perf_counter()
    tmp = Path(tempfile.mkdtemp(prefix="runfolder_"))
    try:
        print("a. --testcase snapshots what a run reads into input/, never truth/")
        test_a_testcase_start_snapshots_and_excludes_truth(tmp)
        print("b. an authored input/ runs with no --testcase")
        test_an_authored_input_runs_with_no_testcase(tmp)
        print("b2. an edited --testcase after a snapshot is refused, unedited proceeds")
        test_an_edited_testcase_after_a_snapshot_is_refused(tmp)
        print("b3. an interrupted snapshot is taken again, not refused as an edit")
        test_an_interrupted_snapshot_is_taken_again(tmp)
        print("c. editing input/ mid-run refuses the resume, naming the file")
        test_editing_input_mid_run_refuses_the_resume_naming_the_file(tmp)
        print("d. no testcase and no input/ is refused before anything is spent")
        test_no_testcase_and_no_input_is_refused_by_name(tmp)
        print("e. a copied input/ records started_from")
        test_a_copied_input_records_started_from(tmp)
        print("e2. --overwrite keeps inputs the user authored, re-takes a snapshot")
        test_overwrite_keeps_inputs_the_user_authored(tmp)
        print(
            "f. a run record from before input/ groups still opens, renders and resumes"
        )
        test_a_run_dir_from_before_the_record_still_opens_and_still_resumes(tmp)
        print("g. a project run archives under _projects/<project>/")
        test_a_project_run_keeps_its_archive_under_projects(tmp)
        print("h. the compile cache does not follow the runs directory")
        test_the_compile_cache_is_the_same_under_both_runs_dirs()
        print("i. no suite spells `runs/`, and every suite imports in order")
        test_no_suite_spells_the_runs_directory_itself()
        # the suite's runs live in its own folders, which the battery does not
        # scan: each record must still hold what its finished steps left
        print("j. every run's record is complete")
        check_records_complete(sorted(tmp.rglob("*.h5")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return finish(
        "\nRUN FOLDER",
        f"\nRUN FOLDER OK — the run folder is the record: two ways in, the "
        f"snapshot takes what a run reads and never truth, drift names the "
        f"file, and the archive has a home ({time.perf_counter() - t0:.0f}s)",
    )


if __name__ == "__main__":
    sys.exit(main())
