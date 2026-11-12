"""The `candidate_detail` degrade step keeps per-candidate detail for the few that matter.

Tables, residual records and rival decompositions survive for the winner, its tied set and
the best K by AIC; the rest are named and dropped, and the selection table is untouched.

    uv run python tests/candidate_detail_unit.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.agents import payload  # noqa: E402


class Spec:
    def __init__(self, cap):
        self.cap = cap

    def require(self, key):
        assert key == "agents.max_prompt_bytes"
        return self.cap

    # the cap may be null (no cap), so the engine reads it with `get`
    def get(self, key, default=None):
        assert key == "agents.max_prompt_bytes"
        return self.cap


def context(n=20):
    ids = [f"M{i}" for i in range(1, n + 1)]
    cands = [
        {"id": c, "aic": 100.0 + i, "delta_aic": float(i), "n_est": 5}
        for i, c in enumerate(ids)
    ]
    return {
        "report_core": {
            "discrimination": {
                "candidates": cands,
                "winner": "M1",
                "indistinguishable": ["M1", "M2"],
            },
            "parameters": {
                c: {f"p{k}": {"value": k * 0.1, "lb": 0, "ub": 1} for k in range(12)}
                for c in ids
            },
            "attribution": {
                "winner": "M1",
                "full_record": "report/attribution.json",
                "rivals": [
                    {
                        "rival": c,
                        "delta_aic": float(i),
                        "contributions": [{"group": "g", "delta_nllh": 1.0}] * 3,
                    }
                    for i, c in enumerate(ids[1:], 1)
                ],
            },
            "profiles": {
                "_meta": {"x_names": ["p0"]},
                "p0": {"ci95": [0.1, 0.2], "ci_finite": True},
            },
        },
        "residual_diagnostics": {
            "per_candidate_residuals": {
                c: {
                    "per_series": {
                        f"obs_{j}@cond": {"rmse": 0.3, "n_timepoints": 8}
                        for j in range(6)
                    }
                }
                for c in ids
            },
        },
    }


def render(ctx):
    return json.dumps(ctx, indent=2)


def main() -> int:
    ctx = context(20)
    full = len(render(ctx).encode())
    fits_calls = []
    working = copy.deepcopy(ctx)
    what = payload._trim_candidate_detail(
        working,
        6,
        lambda: (fits_calls.append(1), len(render(working).encode()) <= full * 0.45)[1],
    )
    assert what, "the step must report what it removed"
    rc = working["report_core"]
    kept = set(rc["parameters"])
    assert {"M1", "M2"} <= kept, kept  # winner + indistinguishable always survive
    assert kept == set(
        working["residual_diagnostics"]["per_candidate_residuals"]
    ), "the same candidates survive in every block"
    assert all(
        r["rival"] in kept for r in rc["attribution"]["rivals"]
    ), "rivals trimmed to the same set"
    assert (
        len(rc["discrimination"]["candidates"]) == 20
    ), "the selection table is untouched"
    assert rc["profiles"] == ctx["report_core"]["profiles"], "profiles untouched"
    assert (
        payload.TRIM_MARK in rc["parameters_trimmed"]
        and "M20" in rc["parameters_trimmed"]
    )
    assert payload.TRIM_MARK in rc["attribution"]["rivals_by_candidate_trimmed"]
    assert (
        payload.TRIM_MARK
        in working["residual_diagnostics"]["per_candidate_residuals_trimmed"]
    )
    # the floor: never below 6 + the always-kept set
    tight = copy.deepcopy(ctx)
    payload._trim_candidate_detail(tight, 6, lambda: False)
    assert len(tight["report_core"]["parameters"]) == 6, len(
        tight["report_core"]["parameters"]
    )
    # through the whole budget: an over-cap payload of this shape lands under the cap
    prompt, out, trims = payload.fit_to_budget(ctx, Spec(int(full * 0.45)), render)
    assert len(prompt.encode()) <= full * 0.45, len(prompt)
    assert trims[-1]["step"] == "candidate_detail", [t["step"] for t in trims]
    assert len(json.dumps(ctx).encode()) == len(
        json.dumps(context(20)).encode()
    ), "caller's context untouched"
    # the expansion agent's context: a bare selection table, a string winner,
    # residual records and an evaluation_report.parameters table
    ids = [f"M{i}" for i in range(1, 21)]
    exp = {
        "selected_model": "M1",
        "selection_table": [
            {"id": c, "aic": 100.0 + i, "delta_aic": float(i), "nllh": 50.0}
            for i, c in enumerate(ids)
        ],
        "residual_diagnostics": {
            "per_candidate_residuals": {
                c: {"per_series": {"o@c": {"rmse": 0.3}}} for c in ids
            }
        },
        "evaluation_report": {"parameters": {c: {"p": {"value": 1}} for c in ids}},
    }
    w = copy.deepcopy(exp)
    assert payload._trim_candidate_detail(w, 6, lambda: False)
    keptx = set(w["residual_diagnostics"]["per_candidate_residuals"])
    assert keptx == set(w["evaluation_report"]["parameters"]), keptx
    assert {"M1", "M2", "M3"} <= keptx and len(
        keptx
    ) == 6, keptx  # rows within 2 AIC + best 6
    assert len(w["selection_table"]) == 20 and w["selected_model"] == "M1"
    # no selection table: the step claims nothing
    nosel = copy.deepcopy(ctx)
    del nosel["report_core"]["discrimination"]
    assert payload._trim_candidate_detail(nosel, 6, lambda: False) == ""
    print(
        "CANDIDATE DETAIL UNIT OK — a large lattice keeps the winner, its set and the best K in the prompt; the rest are named, not lost"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
