"""Profiles: the engine is chosen from what one profile costs, and a human can
decline them up front with `--skip-profiles "<why>"`.

    uv run python tests/skip_profiles_unit.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger  # noqa: E402
from _record import record_at, rnd, work  # noqa: E402

from octomod.orchestration.run_context import ModuleFailure  # noqa: E402
from octomod.workflow_modules.evaluation import engine as s7  # noqa: E402


class _Spec:
    def __init__(self, **kv):
        self.kv = kv

    def get(self, key, default=None):
        return self.kv.get(key, default)

    def require(self, key):
        return self.kv[key]


def _record():
    """A throwaway run record (the run is one file); S7 keeps a round's
    profile request in it (`decisions/evaluation_profile_request`)."""
    root = record_at(Path(tempfile.mkdtemp()) / "run")
    root.store.create()
    return root


def _ctx(skip, root=None, candidate=None, **spec):
    """What `_profiles_for` reads off a RunContext: the round and the fitted
    problem's group (empty here, so no profile fingerprint can be taken)."""
    root = root if root is not None else _record()
    return types.SimpleNamespace(
        spec=_Spec(**spec),
        ledger=RecordingLedger(),
        round_idx=0,
        skip_profiles=skip,
        candidate=candidate,
        root=root,
        store=root.store,
        round=rnd(root, 0),
        work=work(root, 0, candidate),
        model=work(root, 0, candidate) / "model",
    )


def main() -> int:
    import pypesto.engine

    # --- engine: a 1.2 s start is serial as a multistart, parallel as a profile
    from octomod.workflow_modules.evaluation import profile_projection as pp

    # n_procs pinned: the default (cpu_count - 1) is one process on a 2-core
    # runner, and a pool of one is serial whatever the task costs
    ctx = _ctx(None, **{"estimation.engine": "auto", "estimation.n_procs": 2})
    sched = pp.schedule()
    # a parameter in a 6-decade box, optimum in the middle, walking to both bounds
    rows = pp.plan([pp.Box("k", 0.0, -3.0, 3.0)], sched, 1.92)
    one = pp.one_profile_high_s(rows, pp.point_cost(ctx.spec, 1.2))
    assert one > 1.2 * 20, one
    eng = s7._profile_engine(ctx, one)
    assert isinstance(eng, pypesto.engine.MultiProcessEngine), type(eng)
    assert isinstance(s7._profile_engine(ctx, 0.75), pypesto.engine.SingleCoreEngine)
    assert isinstance(s7._profile_engine(ctx, None), pypesto.engine.SingleCoreEngine)
    print(
        f"  engine        one profile ({rows[0]['points_high']} points to the bounds, "
        f"{one:.0f} s at the high end) is the dispatch unit"
    )

    # --- skip: ledgered, reported, and refused where profiles are the deliverable
    ctx = _ctx("round 0 is a selection round; profiles ran 3.5 h serially")
    core: dict = {}
    s7._profiles_for(ctx, core, {"n_starts": 1}, "mechanism_discrimination", 26)
    assert core["profiles_skipped"].startswith("skipped at the human's request"), core
    notes = [r for r in ctx.ledger.rows if r.get("human_decision")]
    assert len(notes) == 1 and "3.5 h" in notes[0]["note"], ctx.ledger.rows
    print("  skip          recorded as the human's decision, with their reason")

    # ...and persisted for the round: the next resume (no flag) remembers it

    root = _record()
    ctx = _ctx("selection round, skip", root)
    core = {}
    s7._profiles_for(ctx, core, {"n_starts": 1}, "mechanism_discrimination", 26)
    assert (rnd(root, 0) / s7.PROFILE_REQUEST).exists()
    ctx2 = _ctx(None, root, **{"estimation.engine": "auto"})
    core2: dict = {}
    s7._profiles_for(ctx2, core2, {"n_starts": 1}, "mechanism_discrimination", 26)
    assert core2.get("profiles_skipped", "").endswith("selection round, skip"), core2
    assert any(
        "remembered" in r.get("note", "") for r in ctx2.ledger.rows
    ), ctx2.ledger.rows
    print(
        "  skip          remembered on resume, so answering the verdict does not re-profile"
    )

    # --- reuse: profiles persisted earlier in the round for the same model are not recomputed
    root2 = _record()
    prof = {
        "_meta": {"x_names": ["k_A", "k_H"]},
        "k_A": {"ci95": [0.1, 0.5], "ci_finite": True},
    }
    saved = rnd(root2, 0) / "evaluation_core"
    saved.put({"discrimination": {"winner": "M2"}, "profiles": prof})
    ctx = _ctx(None, root2, "M2", **{"estimation.engine": "auto"})
    core3: dict = {}
    s7._profiles_for(
        ctx,
        core3,
        {"x_names": ["k_A", "k_H"], "n_starts": 1},
        "mechanism_discrimination",
        2,
    )
    assert core3.get("profiles") == prof, core3
    assert any(
        f"reused from {saved.key}" in r.get("note", "") for r in ctx.ledger.rows
    ), ctx.ledger.rows
    # a different winner or parameter set does not reuse (falls through to the cost marker path)
    ctx = _ctx(None, root2, "M3", **{"estimation.engine": "auto"})
    core4: dict = {}
    try:
        s7._profiles_for(
            ctx,
            core4,
            {"x_names": ["k_A", "k_H"], "n_starts": 1},
            "mechanism_discrimination",
            2,
        )
    except AttributeError:
        pass  # the stub ctx is not a RunContext: reaching it proves the reuse branch was NOT taken
    assert "profiles" not in core4
    assert core4.get("profiles_skipped") == s7.PROFILES_NOT_REQUESTED, core4
    print(
        "  reuse         profiles computed earlier in the round are read back, not recomputed"
    )

    ctx = _ctx("just skip")
    try:
        s7._profiles_for(ctx, {}, {"n_starts": 1}, "parameter_values", 3)
    except ModuleFailure as e:
        assert "refused" in str(e)
        print("  skip          refused for parameter_values, as the gate's decline is")
    else:
        raise AssertionError("parameter_values must not skip profiles")

    # nothing set: the ordinary path is untouched (spec disabled short-circuits)
    ctx = _ctx(None, **{"gates.profiles_auto.enabled": False})
    core = {}
    s7._profiles_for(ctx, core, {}, "prediction", 3)
    assert core["profiles_skipped"] == "profiles disabled in the workflow spec"

    # --- CLI advertises it
    out = subprocess.run(
        [sys.executable, "-m", "octomod", "run", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout
    assert "--skip-profiles WHY" in out, out[-600:]
    print("  cli           `run --skip-profiles WHY` is a declared option")
    print(
        "SKIP PROFILES UNIT OK — profiles dispatch per profile, and a human can decline them up front"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
