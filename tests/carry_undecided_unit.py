"""Carrying undecided axes into the next round uses the axes, not their summaries.

  1. `declared_axis_dicts` returns full axes; the status table stays a summary;
  2. the enumerator refuses a summary (it carries no patch), naming the fix;
  3. the orchestrator's carry reads the axes through `declared_axis_dicts`.

    uv run python tests/carry_undecided_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _record import rnd, temp_record  # noqa: E402

from octomod.workflow_modules.model import supermodel, tried_models  # noqa: E402

AXIS = {
    "id": "loop",
    "priority": 2,
    "question": "loop?",
    "on_antimony_patch": {
        "append": "species H in cell;\nH = 0;\nJ: -> H; cell * eta * A;"
    },
    "adds_parameters": [
        {"id": "eta", "lb": 0, "ub": 10, "nominal_value": 0.1, "neutral_value": 0}
    ],
}


def main() -> int:
    with temp_record() as run:
        return _main(run)


def _main(run) -> int:
    (rnd(run, 0) / "space/declared").put([AXIS])
    full = tried_models.declared_axis_dicts(run)
    assert full["loop"]["on_antimony_patch"] and isinstance(
        full["loop"]["adds_parameters"][0], dict
    )
    summary = {a["id"]: a for a in tried_models.declared_axes_this_run(run)}
    assert summary["loop"]["adds_parameters"] == ["eta"], summary["loop"]
    assert (
        "on_antimony_patch" not in summary["loop"]
    ), "the status table is a summary, by design"
    # the enumerator refuses a summary with a message that names the fix
    try:
        supermodel.neutral_split(summary["loop"])
    except TypeError as e:
        assert "declared_axis_dicts" in str(e) and "loop" in str(e)
    else:
        raise AssertionError("a summary must not pass for an axis")
    assert supermodel.neutral_split(full["loop"])[0][0]["id"] == "eta"
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    i = src.index("def _carry_undecided(")
    body = src[i : src.index("\n    def ", i + 10)]
    assert (
        "declared_axis_dicts(self.root)" in body
    ), "the carry must use the axes themselves"
    print(
        "CARRY UNDECIDED UNIT OK — undecided axes are carried as axes, not as their summaries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
