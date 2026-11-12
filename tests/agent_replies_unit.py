"""Every agent role has a reply class, and it agrees with the role's contract.

`agents.ROLES[role].required_keys` and `result.agent_replies.REPLY_CLASSES[role]`
describe the same reply; this suite keeps them equal so neither can drift.
Every canned reply under `testcase/*/stubs/` must fit its class — the stub
backend is held to exactly the contract a live reply is held to — and a reply
of the wrong SHAPE (a string where a dict is promised) is reported at the seam.

    uv run python tests/agent_replies_unit.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.agents import ROLES, _missing_keys  # noqa: E402
from octomod.result.agent_replies import (  # noqa: E402
    REPLY_CLASSES,
    contract_failures,
    required_fields,
)


def test_every_role_has_a_class_with_the_same_required_keys() -> None:
    missing = sorted(set(ROLES) - set(REPLY_CLASSES))
    assert not missing, f"roles without a reply class: {missing}"
    stray = sorted(set(REPLY_CLASSES) - set(ROLES))
    assert not stray, f"reply classes for roles that do not exist: {stray}"
    for role, rs in ROLES.items():
        assert set(required_fields(role)) == set(rs.required_keys), (
            f"{role}: class requires {sorted(required_fields(role))}, "
            f"RoleSpec requires {sorted(rs.required_keys)}"
        )
    print(f"  registry      {len(ROLES)} roles, one class each, required keys agree")


def _role_of(stub: Path) -> str:
    name = stub.stem
    for role in sorted(ROLES, key=len, reverse=True):
        if name == role or re.fullmatch(rf"{re.escape(role)}[_.]?\d+", name):
            return role
    return name


def test_every_stub_fits_its_class() -> None:
    stubs = sorted((REPO / "testcase").glob("*/stubs/*.json"))
    assert stubs, "no stubs found under testcase/"
    bad = []
    n = 0
    for p in stubs:
        role = _role_of(p)
        if role not in REPLY_CLASSES:
            continue
        n += 1
        try:
            parsed = json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001
            bad.append(f"{p.relative_to(REPO)}: not JSON ({e})")
            continue
        if isinstance(parsed, list):  # a numbered sequence in one file
            items = [x for x in parsed if isinstance(x, dict)]
        else:
            items = [parsed]
        for item in items:
            f = contract_failures(role, item)
            if f:
                bad.append(f"{p.relative_to(REPO)}: {f[:3]}")
    assert not bad, "stubs that do not fit their reply class:\n  " + "\n  ".join(bad)
    print(f"  stubs         {n} canned replies fit their classes")


def test_shape_errors_are_reported_at_the_seam() -> None:
    f = contract_failures(
        "revision_proposal",
        {"move": "add_reaction", "motivated_by": "x", "expected_effect": "y"},
    )
    assert f and "move" in f[0], f
    f = contract_failures("revision", {"axes": [], "diagnosis": "d"})
    assert any("stop_instead" in x for x in f), f
    f = contract_failures("construction", "not even a dict")
    assert f and "JSON object" in f[0], f
    # the seam's own check carries the typed failure back to the agent
    seam = _missing_keys(
        {"axes": "none", "diagnosis": "d", "stop_instead": True},
        ROLES["revision"],
    )
    assert any("axes" in x for x in seam), seam
    assert (
        contract_failures(
            "revision", {"axes": [], "diagnosis": "d", "stop_instead": False}
        )
        == []
    )
    print("  seam          a mistyped key is a contract failure, quoted back by field")


if __name__ == "__main__":
    for fn in (
        test_every_role_has_a_class_with_the_same_required_keys,
        test_every_stub_fits_its_class,
        test_shape_errors_are_reported_at_the_seam,
    ):
        print(fn.__name__)
        fn()
    print("OK")
