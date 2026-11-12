"""The stub backend: canned agent replies checked in beside a testcase.

Runs the whole machine for zero tokens with fixed replies, checked against the
same contract as live ones, so a pipeline bug can be told apart from a model bug.
A role answered differently on successive calls ships `<role>.1.json`,
`<role>.2.json`, …: the k-th call in the run (counted from the ledger, so a
resume keeps counting) gets the k-th file, then `<role>.json`; past both the
call fails, because a duplicate agent call is a bug the tests must see.

A call archived under a name of its own of the form `<family>_<n>`
(`knowledge_targeted_1`, `research_request_2`) reads its FAMILY's replies,
`<family>.<k>.json` then `<family>.json`, the k-th call of that family in the
run the k-th file, when the case ships any; otherwise the role's. A role in
`NAMED_STUBS_ONLY` reads only its family's: its own replies serve another
purpose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from octomod.agents import AgentCallError

_SEQ = re.compile(r"^(?P<role>.+)\.(?P<k>\d+)\.json$")
# a call's archive name that names a family of calls: `<family>_<n>`, with an
# optional suffix after the number (`knowledge_targeted_1_retry`)
_FAMILY = re.compile(r"(?P<family>[A-Za-z][A-Za-z_]*?)_\d+(?:_\w+)?")
# roles whose named calls read only their family's replies: the knowledge
# role's own (`knowledge.<n>.json`) are the survey's, served to the staging
# step, never to a targeted search inside a run
NAMED_STUBS_ONLY = frozenset({"knowledge"})


def stub_family(name: str | None, role: str) -> str | None:
    """The family of replies a call archived under `name` reads, or None when
    it reads its role's: a name of the form `<family>_<n>`."""
    if not name or name == role:
        return None
    m = _FAMILY.fullmatch(str(name))
    return m.group("family") if m else None


def has_replies(stubs_dir: Path | None, family: str) -> bool:
    """Does the case ship a reply for this family (`<family>.json` or a
    numbered sequence)?"""
    if stubs_dir is None:
        return False
    d = Path(stubs_dir)
    return (d / f"{family}.json").exists() or bool(sequence_files(d, family))


def call_name(io) -> str:
    """The archive name of a call from its ledger row's `io` (the record key
    of its accepted reply, `…/agent_calls/<name>/reply`)."""
    parts = str(io or "").strip("/").split("/")
    return parts[-2] if len(parts) >= 2 else ""


def sequence_files(stubs_dir: Path, role: str) -> dict[int, Path]:
    """{k: path} for the role's numbered replies, if any."""
    out: dict[int, Path] = {}
    for p in Path(stubs_dir).glob(f"{role}.*.json"):
        m = _SEQ.match(p.name)
        if m and m.group("role") == role:
            out[int(m.group("k"))] = p
    return out


def stub_path(stubs_dir: Path, role: str, call_index: int = 0) -> Path:
    """The canned reply for the (call_index + 1)-th call of `role` in this run.

    One file per role is the default: <stubs_dir>/<role>.json, served to every
    call. A numbered sequence takes precedence for the calls it covers.
    """
    d = Path(stubs_dir)
    numbered = sequence_files(d, role)
    if not numbered:
        return d / f"{role}.json"
    want = call_index + 1
    if want in numbered:
        return numbered[want]
    single = d / f"{role}.json"
    if single.exists():
        return single
    raise AgentCallError(
        f"stub backend: role {role!r} has a reply sequence of length "
        f"{max(numbered)} but this is call {want} of the run — either the engine "
        f"called the role more often than the test expected (a duplicate call), "
        f"or the sequence needs another file: {d / f'{role}.{want}.json'}"
    )


def load_stub(stubs_dir: Path, role: str, call_index: int = 0) -> dict:
    """Parse the canned reply for one role. Every error names the file, since
    the fix is always to add or edit that file."""
    path = stub_path(stubs_dir, role, call_index)
    if not path.exists():
        raise AgentCallError(
            f"stub backend: no canned reply for role {role!r} at {path}"
        )
    try:
        reply = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise AgentCallError(f"stub {path} is not valid JSON: {e}") from e
    if not isinstance(reply, dict):
        raise AgentCallError(
            f"stub {path} must be a JSON object, got {type(reply).__name__}"
        )
    return reply
