"""One rule for a run's inputs: the record keeps what the run reads, nothing else.

`run_folder.inputs_read` lists what a run reads from a case; the snapshot
copies that list, `run_guard.manifest` hashes it as the input identity, and
the legacy importer transcribes it. Checked on a fabricated case carrying
every kind of file a staging folder holds, with no engine run:

  1. the list is exactly the fixed files, `data/`, `supplied/`, `stubs/`,
     `knowledge/` and the documents an evidence item names by a `file:` url;
  2. the snapshot copies exactly that list, byte for byte;
  3. the identity of the folder and of its snapshot agree, and moves only
     when a listed file moves;
  4. a record holding more than the list (a whole-case snapshot) has
     the folder's identity;
  5. the legacy importer keeps the same list and skips the rest;
  6. no case in the library lists a file under `truth/`.

    uv run python tests/inputs_read_unit.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402
from _record import temp_record  # noqa: E402

from octomod.orchestration import run_folder, run_guard  # noqa: E402
from octomod.workflow_modules.knowledge import supplied_literature as lit  # noqa: E402

INTENT = """\
question: does the fabricated case list what a run reads?
supplied_literature:
  - source: a paper staged beside the data
    supports: a claim
    url: file:./paper/cited.pdf
  - source: a methods section, named without ./
    supports: the assay's floor
    url: file:paper/methods.md
  - source: a paper the user has not staged yet
    supports: a claim
    url: file:./paper/missing.pdf
  - source: a leak the snapshot must refuse to carry
    supports: nothing
    url: file:./truth/ANSWER.txt
  - source: a file outside the case
    supports: nothing
    url: file:../outside.txt
  - source: a paper on the web
    supports: a claim
    url: https://doi.org/10.0000/example
"""

RESEARCH_STUB = {
    "evidence_items": [
        {
            "source": "a fixture's research reply",
            "supports": "a claim",
            "url": "file:./sources/note.txt",
        }
    ]
}

KNOWLEDGE_STUB = {
    "reactions": [
        {
            "equation": "A -> B",
            "evidence": [
                {
                    "source": "a fixture's knowledge survey",
                    "supports": "A becomes B",
                    "url": "file:./sources/reaction_note.txt",
                }
            ],
        },
        "not an object: names nothing",
    ],
    "queries_run": [],
    "notes": "",
}

# what a run reads of the case below
READ = [
    "blocklist.txt",
    "data/sub/y.tsv",
    "data/x.csv",
    "description.md",
    "intent.yaml",
    "knowledge/intent_before.yaml",
    "knowledge/knowledge.json",
    "knowledge/sources/0a1b.txt",
    "paper/cited.pdf",
    "paper/methods.md",
    "sources/note.txt",
    "sources/reaction_note.txt",
    "stubs/construction.json",
    "stubs/knowledge.json",
    "stubs/research.json",
    "supplied/model.ant",
    "supplied/petab/problem.yaml",
    "testcase.yaml",
]

# and everything a staging folder carries beside it, which no run reads
NOT_READ = [
    "data/.DS_Store",
    "stubs/__pycache__/stub.cpython-313.pyc",
    "paper/uncited.pdf",
    "sources/other.txt",
    "raw_fcs/A01.fcs",
    "raw_fcs/A02.fcs",
    "preprocessing/gate.py",
    "curation/STAGING-LOG.md",
    "notes/call.md",
    "make_data.py",
    "ASSUMPTIONS.md",
    "tried_models.json",
    "source.json",
    "truth/ANSWER.txt",
]


def make_case(where: Path) -> Path:
    case = where / "case"
    content = {rel: f"{rel}\n" for rel in READ + NOT_READ}
    content["intent.yaml"] = INTENT
    content["stubs/research.json"] = json.dumps(RESEARCH_STUB, indent=2)
    content["stubs/knowledge.json"] = json.dumps(KNOWLEDGE_STUB, indent=2)
    content["stubs/construction.json"] = "{}\n"
    content["source.json"] = json.dumps({"run_id": "elsewhere"})
    for rel, text in content.items():
        (case / rel).parent.mkdir(parents=True, exist_ok=True)
        (case / rel).write_text(text)
    (where / "outside.txt").write_text("outside the case\n")
    return case


def test_the_url_reading() -> None:
    named = {
        "file:./paper/x.pdf": PurePosixPath("paper/x.pdf"),
        "file:paper/x.pdf": PurePosixPath("paper/x.pdf"),
        "file:/paper/x.pdf": PurePosixPath("paper/x.pdf"),
        "file:///abs/x.pdf": None,
        "https://doi.org/10.0/x": None,
        "": None,
        None: None,
    }
    got = {url: lit.case_document(url) for url in named}
    check(
        "a file: url names a case-relative path; an absolute or web url names none",
        got == named,
        str({k: v for k, v in got.items() if named[k] != v}),
    )


def test_the_list(case: Path) -> None:
    got = [r.as_posix() for r in run_folder.inputs_read(case)]
    check("inputs_read lists exactly what a run reads", got == READ, str(got))
    check(
        "… sorted, relative, files only",
        got == sorted(got)
        and all(not Path(r).is_absolute() and (case / r).is_file() for r in got),
    )
    for rel, why in (
        ("paper/cited.pdf", "a supplied-literature url names it"),
        ("paper/methods.md", "named without ./"),
        ("sources/note.txt", "a stub research reply names it"),
        ("sources/reaction_note.txt", "a stub knowledge reply names it"),
        ("knowledge/knowledge.json", "the knowledge module's output"),
    ):
        check(f"{rel} is listed: {why}", rel in got)
    check(
        "a named file that does not exist is left out",
        "paper/missing.pdf" not in got,
    )
    check(
        "a url into truth/ or out of the case lists nothing",
        not [r for r in got if r.startswith(("truth", ".."))]
        and "outside.txt" not in "".join(got),
    )
    check(
        "no staging file is listed",
        not set(NOT_READ) & set(got),
        str(sorted(set(NOT_READ) & set(got))),
    )


def test_the_snapshot(case: Path) -> None:
    with temp_record("snap") as root:
        copied = run_folder.snapshot(case, root)
        check("snapshot copies exactly the list", copied == READ, str(copied))
        check("… and the record holds nothing else", run_folder.entries(root) == READ)
        same = all(
            run_folder.read_bytes(root, rel) == (case / rel).read_bytes()
            for rel in READ
        )
        check("… byte for byte", same)
        check("… and is complete", run_folder.is_complete(root))
        folder, record = run_guard.manifest(case), run_guard.manifest(root)
        check(
            "the folder and its snapshot have one identity",
            folder == record and list(folder) == READ,
            f"{sorted(folder)} vs {sorted(record)}",
        )


def test_the_identity(case: Path) -> None:
    base = run_guard.input_sha(case)
    with (case / "notes" / "call.md").open("a") as f:
        f.write("- appended while the run is paused\n")
    (case / "raw_fcs" / "A03.fcs").write_bytes(b"\x00\x01 a new raw file\n")
    (case / "paper" / "uncited.pdf").write_text("replaced\n")
    (case / "make_data.py").write_text("print('regenerated')\n")
    check(
        "appending to notes/, adding a raw file, editing an unnamed paper or the "
        "generator: same sha",
        run_guard.input_sha(case) == base,
    )
    before = run_guard.manifest(case)
    (case / "paper" / "cited.pdf").write_text("a corrected scan\n")
    check(
        "editing a paper an item names: a different sha",
        run_guard.input_sha(case) != base,
    )
    (case / "paper" / "cited.pdf").write_text("paper/cited.pdf\n")
    check("put back, the sha is back", run_guard.input_sha(case) == base)
    with (case / "data" / "x.csv").open("a") as f:
        f.write("an edited row\n")
    now = run_guard.manifest(case)
    check("editing data/x.csv: a different sha", run_guard.sha_of(now) != base)
    check(
        "… and the drift names that file alone",
        run_guard.drifted(before, now) == ["data/x.csv — edited"],
        str(run_guard.drifted(before, now)),
    )
    (case / "data" / "x.csv").write_text("data/x.csv\n")


def test_a_wider_record(case: Path) -> None:
    """An `input` group holding the whole case, as a whole-case snapshot
    wrote it, has the folder's identity: the rule, not the group's extent,
    decides what is hashed."""
    with temp_record("wide") as root:
        inp = run_folder.input_node(root)
        every = sorted(p.relative_to(case) for p in case.rglob("*") if p.is_file())
        for rel in every:
            run_folder._put_file(inp, rel, (case / rel).read_bytes())
        check(
            "the group holds more than the list",
            len(run_folder.entries(root)) > len(READ),
            str(len(run_folder.entries(root))),
        )
        check(
            "and its identity is still the folder's",
            run_guard.manifest(root) == run_guard.manifest(case),
            str(sorted(set(run_guard.manifest(root)) ^ set(run_guard.manifest(case)))),
        )


def test_the_importer(case: Path, where: Path) -> None:
    from octomod.result.importer import import_run
    from octomod.result.node import Node
    from octomod.result.runstore import RunStore

    run_dir = where / "legacy_run"
    shutil.copytree(case, run_dir / "input")
    (run_dir / "ledger.jsonl").write_text(
        json.dumps({"event": "run_start", "ts": "now"}) + "\n"
    )
    store = RunStore(where / "legacy_run.h5")
    rep = import_run(run_dir, store)
    kept = run_folder.entries(Node(store))
    listed = [r.as_posix() for r in run_folder.inputs_read(run_dir / "input")]
    check(
        "the importer keeps the same list of a legacy input/ folder",
        kept == READ == listed,
        str(kept),
    )
    every = {
        p.relative_to(run_dir).as_posix()
        for p in (run_dir / "input").rglob("*")
        if p.is_file()
    }
    rest = every - {f"input/{rel}" for rel in READ} - {"input/source.json"}
    check(
        "… and reports the rest as skipped, not unknown",
        set(rep.skipped) == rest and not rep.unknown and not rep.failed,
        str(sorted(set(rep.skipped) ^ rest) + rep.unknown + rep.failed),
    )
    check(
        "input/source.json still becomes input_source",
        (Node(store) / run_folder.SOURCE_KEY).get().get("run_id") == "elsewhere",
    )


def test_no_case_lists_truth() -> None:
    leaks = [
        f"{case.name}/{rel}"
        for case in sorted((REPO / "testcase").iterdir())
        if case.is_dir()
        for rel in run_folder.inputs_read(case)
        if "truth" in rel.parts
    ]
    check("no case in the library lists a file under truth/", not leaks, str(leaks))


def main() -> int:
    t0 = time.perf_counter()
    where = Path(tempfile.mkdtemp(prefix="inputs_read_"))
    try:
        case = make_case(where)
        print("1. a file: url names a case-relative path")
        test_the_url_reading()
        print("2. inputs_read lists what a run reads, nothing else")
        test_the_list(case)
        print("3. the snapshot copies exactly that list")
        test_the_snapshot(case)
        print("4. the identity moves only when a listed file moves")
        test_the_identity(case)
        print("5. a record holding the whole case has the folder's identity")
        test_a_wider_record(case)
        print("6. the legacy importer keeps the same list")
        test_the_importer(case, where)
        print("7. no case in the library lists truth/")
        test_no_case_lists_truth()
    finally:
        shutil.rmtree(where, ignore_errors=True)
    return finish(
        "\nINPUTS READ",
        f"\nINPUTS READ OK — the snapshot, the input identity and the importer "
        f"keep what a run reads, nothing else ({time.perf_counter() - t0:.1f}s)",
    )


if __name__ == "__main__":
    sys.exit(main())
