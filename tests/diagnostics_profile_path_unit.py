"""A `profile_path` request returns one parameter's profile path, read from the record.

The agent view of the report drops the profile paths; the interpreter asks for
one by parameter id through the diagnostics dispatcher:

  1. a known parameter returns ITS path and interval, not another's, and the
     reading note names only fields the path carries;
  2. an unknown id, the report's own `_meta` record, a record with no path and
     a round with no report each come back as an error in the shape every
     kind uses, naming what is available or why there is none;
  3. every request is ledgered, with whether it answered.

    uv run python tests/diagnostics_profile_path_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail, finish  # noqa: E402
from _record import rnd, temp_record  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.evaluation import diagnostics  # noqa: E402

MODULE = "evaluation"


def _profile(xs: list[float], nllh: list[float], ci: list[float]) -> dict:
    """A profile record in the layout the evaluation module writes."""
    low = min(nllh)
    return {
        "ci95": ci,
        "ci_finite": True,
        "ci_width_decades": 0.5,
        "ci_scale": "log10",
        "path": {
            "x_unscaled": xs,
            "nllh": nllh,
            "nllh_threshold": low + 1.92,
            "likelihood_ratio": [1.0 if v == low else 0.5 for v in nllh],
            "ratio_threshold": 0.1465,
            "x_full_scaled": [[x, 0.25] for x in xs],
        },
    }


PROFILES = {
    "_meta": {"x_names": ["k_on", "k_off"]},
    "k_on": _profile([0.1, 0.2, 0.4, 0.8], [12.5, 10.25, 10.0, 11.75], [0.15, 0.6]),
    "k_off": _profile([1.0, 2.0, 4.0], [20.5, 20.0, 21.5], [1.5, 3.0]),
    # a profile that did not run to completion keeps its record, not its path
    "k_cut": {"ci95": [0.01, 0.02], "ci_finite": False, "path": {}},
}


class _Ctx:
    """What the dispatcher and this reader use from a RunContext."""

    def __init__(self, root):
        self.root = root  # the run is one record file
        self.round_idx = 0
        self.candidate = None
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, self.round_idx)


def _ask(ctx: _Ctx, kind: str, args: dict) -> dict:
    return diagnostics.run_request(
        ctx, ["M1"], {"kind": kind, "args": args}, module=MODULE
    )


def test_a_known_parameter_returns_its_own_path(ctx: _Ctx) -> None:
    out = _ask(ctx, "profile_path", {"parameter_id": "k_on"})
    res = out.get("result") or {}
    path = res.get("path") or {}
    want = PROFILES["k_on"]["path"]
    check_detail_on_fail(
        "the request answers, for the parameter it named",
        "error" not in out and res.get("parameter_id") == "k_on",
        str(out.get("error") or res.get("parameter_id")),
    )
    check_detail_on_fail(
        "with that parameter's path and interval, not another's",
        path.get("x_unscaled") == want["x_unscaled"]
        and path.get("nllh") == want["nllh"]
        and res.get("ci95") == PROFILES["k_on"]["ci95"]
        and len(path.get("x_full_scaled") or []) == len(want["x_unscaled"]),
        f"x={path.get('x_unscaled')} nllh={path.get('nllh')} ci={res.get('ci95')}",
    )
    note = str(res.get("how_to_read_this", ""))
    named = [
        f
        for f in ("x_unscaled", "nllh", "nllh_threshold", "likelihood_ratio")
        if f"path.{f}" in note
    ]
    check_detail_on_fail(
        "the reading note names the path's fields, and each one it names is there",
        len(named) == 4 and all(f in path for f in named),
        f"named {named}; path has {sorted(path)}",
    )


def test_what_cannot_be_answered_comes_back_as_an_error(ctx: _Ctx) -> None:
    # the shape another kind returns for a bad argument
    other = _ask(ctx, "residual_curve", {"candidate_id": "no_such_model"})
    shape = set(other)
    unknown = _ask(ctx, "profile_path", {"parameter_id": "k_nowhere"})
    check_detail_on_fail(
        "an unknown parameter id is an error in the shape every kind uses",
        set(unknown) == shape == {"kind", "args", "error"}
        and str(unknown["error"]).startswith("ValueError: ")
        and str(other["error"]).startswith("ValueError: ")
        and unknown["args"] == {"parameter_id": "k_nowhere"},
        f"{sorted(unknown)} vs {sorted(shape)}: {unknown.get('error')}",
    )
    check_detail_on_fail(
        "and it names the parameters that do have a profile, and the one asked for",
        "['k_cut', 'k_off', 'k_on']" in str(unknown.get("error"))
        and "'k_nowhere'" in str(unknown.get("error")),
        str(unknown.get("error")),
    )
    meta = _ask(ctx, "profile_path", {"parameter_id": "_meta"})
    check_detail_on_fail(
        "the report's own `_meta` record is not a parameter",
        "result" not in meta
        and "parameter_id must be one of" in str(meta.get("error")),
        str(meta.get("result") or meta.get("error"))[:160],
    )
    cut = _ask(ctx, "profile_path", {"parameter_id": "k_cut"})
    check_detail_on_fail(
        "a profile that did not run to completion says it has no path",
        "result" not in cut
        and "k_cut has a profile record but no path" in str(cut.get("error")),
        str(cut.get("result") or cut.get("error"))[:160],
    )


def test_a_round_with_no_report_says_where_profiles_come_from() -> None:
    with temp_record("unevaluated") as root:
        _no_report(_Ctx(root))


def _no_report(ctx: _Ctx) -> None:
    out = _ask(ctx, "profile_path", {"parameter_id": "k_on"})
    check_detail_on_fail(
        "before the evaluation module there is nothing to read, and it says so",
        "result" not in out
        and "evaluation_core does not exist yet" in str(out.get("error"))
        and "evaluation module" in str(out.get("error")),
        str(out.get("result") or out.get("error"))[:160],
    )


def test_every_request_is_ledgered(ctx: _Ctx) -> None:
    rows = [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "diagnostic_request" and e.get("kind") == "profile_path"
    ]
    oks = [(r["args"].get("parameter_id"), r["ok"]) for r in rows]
    check_detail_on_fail(
        "each profile_path request is ledgered under the module that asked, "
        "with whether it answered",
        oks
        == [("k_on", True), ("k_nowhere", False), ("_meta", False), ("k_cut", False)]
        and all(r.get("module") == MODULE and r.get("result_sha") for r in rows),
        str(oks),
    )


def main() -> int:
    with temp_record("run") as root:
        ctx = _Ctx(root)
        (ctx.round / "evaluation_core").put({"profiles": PROFILES})
        test_a_known_parameter_returns_its_own_path(ctx)
        test_what_cannot_be_answered_comes_back_as_an_error(ctx)
        test_a_round_with_no_report_says_where_profiles_come_from()
        test_every_request_is_ledgered(ctx)
    return finish(
        "\nPROFILE PATH",
        "\nPROFILE PATH UNIT OK — a profile_path request returns the named "
        "parameter's path from the report, and anything it cannot answer comes "
        "back as a named error, ledgered",
    )


if __name__ == "__main__":
    sys.exit(main())
