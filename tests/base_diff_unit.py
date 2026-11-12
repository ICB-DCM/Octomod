"""After a base redraft the card says what moved.

  1. `base_diff` names changed reactions, parameters and other lines; the same model reads "nothing";
  2. `_persist_base` keeps the sent-back base in `base_model_previous` only on a redraft;
  3. both cards carry the lines (the staged smoke checks them end to end).

    uv run python tests/base_diff_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.model import engine as model_module  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402

OLD = """model m
  species A = 1; species B = 0;
  J1: A -> B; k1*A;
  J2: B -> ; k2*B;
  k1 = 0.5; k2 = 0.1;
end
"""
NEW = """model m
  species A = 1; species B = 0; species C = 0;
  J1: A -> B; k1*A/(1 + B/Ki);
  J3: B -> C; k3*B;
  k1 = 0.5; k3 = 0.2; Ki = 1;
end
"""
P_OLD = [
    {"id": "k1", "nominal_value": 0.5, "lb": 1e-3, "ub": 10, "estimate": True},
    {"id": "k2", "nominal_value": 0.1, "lb": 1e-3, "ub": 10, "estimate": True},
]
P_NEW = [
    {"id": "k1", "nominal_value": 0.5, "lb": 1e-3, "ub": 100, "estimate": False},
    {"id": "k3", "nominal_value": 0.2, "lb": 1e-3, "ub": 10, "estimate": True},
    {"id": "Ki", "nominal_value": 1.0, "lb": 1e-2, "ub": 100, "estimate": True},
]


def main() -> int:
    lines = "\n".join(model_module.base_diff(OLD, P_OLD, NEW, P_NEW))
    print(lines)
    for needle in (
        "+1 (J3)",
        "−1 (J2)",
        "rate law changed: J1",
        "parameters: +2 (Ki, k3); −1 (k2)",
        "changed: k1 (ub 10 → 100; estimate True → False)",
        "other lines: +1 / −0",
        "+ species C = 0",
    ):
        assert needle in lines, (needle, lines)
    same = model_module.base_diff(OLD, P_OLD, OLD, P_OLD)
    assert same[-1].endswith("nothing — the redraft returned the same model"), same
    print(
        "  diff          reactions, parameters and other lines; the same model says nothing"
    )

    with temp_record() as root:
        ctx = SimpleNamespace(round=rnd(root, 0), round_idx=0, ledger=Ledger(root))
        model_module._persist_base(
            ctx, {"antimony": OLD, "parameters": P_OLD}, "<sbml/>"
        )
        prev = rnd(root, 0) / "base_model_previous"
        model_module._persist_base(
            ctx, {"antimony": NEW, "parameters": P_NEW}, "<sbml/>"
        )
        assert (
            not prev.exists()
        ), "a base that answers no redraft must not create previous/"
        model_module._persist_base(
            ctx, {"antimony": OLD, "parameters": P_OLD}, "<sbml/>", redrafted=True
        )
        assert (
            prev / "antimony"
        ).text() == NEW, "previous/ must hold the base the person sent back"
        got = "\n".join(
            model_module._base_diff_lines(ctx, {"antimony": OLD, "parameters": P_OLD})
        )
        assert "CHANGED SINCE THE BASE YOU SENT BACK" in got and "J3" in got, got
    print(
        "  kept          the base sent back is kept only when the new one answers a redraft"
    )

    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert 'redrafted="human_feedback" in context' in src
    assert (
        src.count("_base_diff_lines(ctx, construction)") == 2
    ), "both cards carry the diff"
    print(
        "  wired         the draft loop says when it redrafted; both cards show the lines"
    )
    print("\nBASE DIFF UNIT OK — a redrafted base says what moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
