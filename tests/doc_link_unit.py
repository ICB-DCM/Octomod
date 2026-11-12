"""Documents a gate card names must be openable by a click.

  1. one helper, `humangate.doc_link`, so the rule lives once;
  2. OSC 8 on a TTY, a plain absolute `file://` URL otherwise (logs stay plain);
  3. the payload carries paths, not rendered links: the front end renders its own;
  4. every surface that names a document to a human routes it through the helper;
  5. record content is not a file: a record node is named by the command that
     prints it, `./run.sh show --run-id <id> <record key>`.

    uv run python tests/doc_link_unit.py
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod import config  # noqa: E402
from octomod.orchestration.interaction import humangate  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

ESC = "\x1b"
OSC8 = f"{ESC}]8;;"


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_both_forms_are_openable() -> None:
    target = REPO / "README.md"
    if not target.exists():
        target = REPO / "tests" / "run_all.py"

    plain = humangate.doc_link(target, "the round report")
    assert plain.startswith("the round report: file://"), plain
    assert str(target.resolve()) in plain, "the path must be ABSOLUTE"
    assert ESC not in plain, (
        "an escape sequence in captured output is unreadable — the file-gate "
        "driver and this battery both read it"
    )

    old = sys.stdout
    sys.stdout = _Tty()
    try:
        linked = humangate.doc_link(target, "the round report")
    finally:
        sys.stdout = old
    assert linked.startswith(OSC8) and linked.endswith(f"{OSC8}{ESC}\\")
    assert "the round report" in linked
    assert target.resolve().as_uri() in linked
    # the display text is the LABEL, so a long path does not wrap the card line;
    # ESC]8;;<url>ESC\<text>ESC]8;;ESC\ — the display text sits between the
    # first ESC\ and the closing OSC 8, so both delimiters have to come off
    visible = linked.split(f"{ESC}\\")[1].split(OSC8)[0]
    assert visible == "the round report", repr(visible)

    # a relative path is resolved, not passed through
    rel = humangate.doc_link("tests/run_all.py", "x")
    assert "file:///" in rel and ".." not in rel

    # a document that does not exist yet is still linkable rather than crashing
    missing = humangate.doc_link(RUNS / "nope" / "x.html", "x")
    assert missing.startswith("x: file://") and "nope" in missing

    # record content is no file: it is named by the command that prints it
    with temp_record("doclink") as root:
        node = rnd(root, 0) / "decisions_md"
        shown = humangate.doc_link(node, "the decisions")
    assert shown == (
        "the decisions: ./run.sh show --run-id doclink rounds/round_0/decisions_md"
    ), shown
    assert ESC not in shown and "file://" not in shown, shown
    print(
        "  two forms     plain file:// off a TTY, OSC 8 on one, label as text; "
        "a record node as its show command"
    )


def test_the_payload_carries_paths_not_escapes() -> None:
    """The payload carries absolute paths, never escapes or pre-made URLs."""
    with tempfile.TemporaryDirectory() as td, temp_record("doclink") as root:
        doc = Path(td) / "report.html"  # a rendered document: a real file
        doc.write_text("<h1>evidence</h1>")
        humangate.configure_file_mode(root, None, "")
        try:
            try:
                with redirect_stdout(io.StringIO()):
                    humangate.ask(
                        "Sign off?",
                        ["evidence"],
                        ledger=RecordingLedger(),
                        module="evaluation_verdict",
                        consequences=("ends", "stops"),
                        documents=[("the round report", str(doc))],
                    )
            except humangate.GatePending:
                pass
            else:  # pragma: no cover
                raise AssertionError("file mode must pause")
            payload = humangate.pending_path(root).get()
        finally:
            humangate._FILE_MODE.update(enabled=False, root=None, answer=None, note="")

    docs = payload["documents"]
    assert docs == [{"label": "the round report", "path": str(doc.resolve())}], docs
    assert ESC not in json.dumps(payload), (
        "an escape sequence reached the payload — the front end renders its "
        "own link and cannot read a terminal control code"
    )
    assert not any(
        "file://" in str(x) for x in payload["documents"]
    ), "the payload carries a PATH; the URL is a rendering choice"
    print("  payload       {label, absolute path}, no escapes, no pre-made URL")


def test_the_card_prints_them() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        humangate.ask(
            "Proceed?",
            ["evidence"],
            ledger=RecordingLedger(),
            module="test_gate",
            auto=True,
            consequences=("a", "b"),
            documents=[("the round report", str(REPO / "tests" / "run_all.py"))],
        )
    out = buf.getvalue()
    assert "the round report" in out and "file://" in out
    # and a card with no documents prints no separator for them
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        humangate.ask(
            "Proceed?",
            ["evidence"],
            ledger=RecordingLedger(),
            module="test_gate",
            auto=True,
            consequences=("a", "b"),
        )
    assert "file://" not in buf2.getvalue()
    print("  card          documents printed as links, absent when none")


def test_every_named_document_goes_through_the_helper() -> None:
    """No surface may hand-roll a path where a reader is expected to click."""
    surfaces = {
        "octomod/orchestration/orchestrator.py": 4,  # 2 stop lines, run dir, final report, analysis
        "octomod/workflow_modules/model/engine.py": 2,  # both scope gates
        "octomod/workflow_modules/evaluation/engine.py": 2,  # both verdict gates
    }
    for rel, _least in surfaces.items():
        src = (REPO / rel).read_text()
        assert "doc_link(" in src or "documents=" in src, (
            f"{rel} names a document to a human and does not route it through "
            f"humangate.doc_link / documents="
        )
    # and the scope card carries no bare relative path
    s1 = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert (
        "model report: report/model_report.html" not in s1
    ), "the un-clickable relative string is still on a card"
    print(
        f"  coverage      {len(surfaces)} surfaces route documents through one helper"
    )


if __name__ == "__main__":
    test_both_forms_are_openable()
    test_the_payload_carries_paths_not_escapes()
    test_the_card_prints_them()
    test_every_named_document_goes_through_the_helper()
    print(
        "DOC LINK UNIT OK — one helper, a link on a TTY, a plain URL in a "
        "log, and paths rather than escapes in the payload"
    )
