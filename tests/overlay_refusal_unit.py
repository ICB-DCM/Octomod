"""A refusal caused by a candidate's observation-axis overlay drops that candidate; it never crashes.

A candidate set on a carried shared assembly: no observation-model agent was called this round,
so the round's `agent_calls` hold no observation-model reply. The candidate's overlay rewrites
`obs_x` to a formula its shared sigma is not written on, and the merge refuses it
(`assembly_merge_noise`).

  1. that refusal on the overlay's own observable raises CandidateDefect naming the candidate and
     the check, and calls no agent — also when the overlay names its observable by data label;
  2. a check that names no observable is the overlay's when the shared assembly passed on another
     candidate, and not otherwise; a resolve check keeps its own rule;
  3. the same refusal on an observable the overlay did not touch, with the shared assembly not yet
     passed elsewhere, reaches the failure-point gate: the role has no reply of this round in the
     record, the ledger says so, and nothing reads the missing reply;
  4. through the orchestrator's candidate loop and the real S3 module: `candidate_dropped` for the
     overlay candidate, the others kept, the round continues to the compile card.

    uv run python tests/overlay_refusal_unit.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check, finish  # noqa: E402
from _record import record_at  # noqa: E402

from octomod.gates import GateResult  # noqa: E402
from octomod.orchestration.artifacts import ArtifactError  # noqa: E402
from octomod.orchestration.interaction import battery_feedback  # noqa: E402
from octomod.orchestration.interaction.retry import dossier_of  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.orchestrator import Orchestrator  # noqa: E402
from octomod.orchestration.run_context import (  # noqa: E402
    ModuleFailure,
    RunContext,
    as_candidate,
)
from octomod.reporting import render as _render  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as assembly_module  # noqa: E402
from octomod.workflow_modules.cost_probe import compile_gate  # noqa: E402
from octomod.workflow_modules.data import engine as data_module  # noqa: E402

S3 = assembly_module
SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
CAND = "floor_x"
ANT = """
model overlay_refusal
  species A, B;
  A = 10; B = 0;
  kdeg = 0.3; lod = 0.5;
  J0: A -> B; kdeg*A;
end
"""
# not B: once the overlay rewrites the formula, the shared sigma on B does not
# reach the model through it
FLOOR = "B * B / (B + lod)"


class Ctx(RunContext):
    """A RunContext on a throwaway record, round 0, for one candidate: what the
    merge and the S3 battery loop read — also what a re-ask would build its
    context from, so a path that reaches the re-ask gets as far as the reply it
    reads. The round's `agent_calls` hold no assembly agent's reply."""

    description = "A decays into B."

    def __init__(self, root: Node, candidate: str = CAND):
        super().__init__(
            root=root,
            testcase_dir=REPO / "testcase" / "toy_phos",
            spec=SPEC,
            ledger=Ledger(root),
            backend="stub",
            auto=False,
            candidate=candidate,
        )
        self.calls: list[str] = []

    @property
    def intent(self) -> dict:
        return {"question": "does A decay into B?"}

    @property
    def testcase(self) -> dict:
        return {"holdout": {"condition_labels": []}}

    def pack_texts(self, pack_ids=None) -> dict:
        return {}

    def call(self, role: str, context: dict, calls=None, name=None) -> dict:
        self.calls.append(role)
        raise AssertionError(f"no agent may be called here; {role} was")


def _record(tmp: str) -> Node:
    """A fresh record for one scenario."""
    root = record_at(Path(tmp) / "overlay_refusal")
    root.store.create()
    return root


def _sbml() -> str:
    import antimony

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    return antimony.getSBMLString(antimony.getMainModuleName())


def _obs(oid: str, label: str, formula: str, noise: str) -> dict:
    return {
        "observable_id": oid,
        "maps_to_label": label,
        "formula": formula,
        "transformation": "lin",
        "noise": {"distribution": "normal", "formula": noise, "estimate_sigma": True},
        "scaling": {"mode": "none"},
        "rationale": "-",
    }


def _shared(y_noise: str = "sy_abs + sy_rel * A") -> dict:
    """The shared assembly: a two-component sigma on each observable's own species."""
    reply = {
        "observables": [
            _obs("obs_x", "x", "B", "sx_abs + sx_rel * B"),
            _obs("obs_y", "y", "A", y_noise),
        ]
    }
    obs, noise, scaling = S3.split_observation_reply(reply)
    return {
        "observables": obs,
        "noise": noise,
        "scaling": scaling,
        "conditions": [
            {
                "condition_id": "c0",
                "maps_to_label": "c0",
                "overrides": {},
                "preequilibration": False,
            }
        ],
    }


def _long_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "observable_label": lab,
                "condition_label": "c0",
                "condition_key": "c0",
                "time": t,
                "value": val,
            }
            for t in (0.0, 1.0, 2.0, 4.0, 8.0)
            for lab, val in (
                ("x", 10.0 * (1.0 - 0.74**t)),
                ("y", 10.0 * 0.74**t),
            )
        ]
    )


def _stage_candidate(model: Node, overlay: list[dict]) -> None:
    """A candidate's model, and the overlay the model-space enumerator wrote."""
    (model / "sbml").put_text(_sbml())
    (model / "parameters").put(
        [
            {"id": p, "nominal_value": v, "lb": 1e-3, "ub": 1e3, "estimate": True}
            for p, v in (("kdeg", 0.3), ("lod", 0.5))
        ]
    )
    (model / "assembly_overlay").put(overlay)


def _merge(ctx: Ctx, overlay: list[dict], shared: dict):
    """The candidate's assembly as the module writes it (shared + overlay), then
    the merge: its refusal, or None."""
    _stage_candidate(ctx.model, overlay)
    with contextlib.redirect_stdout(io.StringIO()):
        asm = S3._write_assembly(ctx, shared)
        return S3._merge_or_refusal(ctx, asm, _sbml(), _long_df(), ctx.work / "petab")


def _battery(ctx: Ctx, refusal, *, reused_shared: bool):
    """The S3 battery loop on the refusal: (the exception it raised or its
    return, what it printed)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            out = S3._battery_with_feedback(
                ctx,
                ctx.work / "petab",
                _sbml(),
                _long_df(),
                {},
                supplied=False,
                reused_shared=reused_shared,
                refusal=refusal,
            )
    except Exception as e:  # noqa: BLE001 — the outcome under test
        return e, buf.getvalue()
    return out, buf.getvalue()


def _first(out) -> str:
    """An outcome's type and the first line of its message."""
    return f"{type(out).__name__}: {str(out).splitlines()[0] if str(out) else ''}"[:240]


def _rows(ctx, event: str) -> list[dict]:
    return [e for e in ctx.ledger.entries() if e.get("event") == event]


class _patched:
    """Module attributes replaced for a block and restored after it."""

    def __init__(self, *triples):
        self.triples, self.saved = triples, []

    def __enter__(self):
        for obj, name, value in self.triples:
            self.saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)
        return self

    def __exit__(self, *exc):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)
        return False


def _floor_overlay(**target) -> list[dict]:
    return [
        {
            "change_observable_formula": {
                **(target or {"observable_id": "obs_x"}),
                "new_formula": FLOOR,
            }
        }
    ]


# ------------------------------------------------ 1. the overlay's own check


def test_the_overlay_refusal_is_the_candidates_defect() -> None:
    for how, target in (
        ("by id", {"observable_id": "obs_x"}),
        ("by data label", {"observable_label": "x"}),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = Ctx(_record(tmp))
            refusal = _merge(ctx, _floor_overlay(**target), _shared())
            applied = ctx.work / "assembly_overlay_applied"
            check(
                f"[{how}] the merge refuses the overlay's formula as assembly_merge_noise on obs_x",
                isinstance(refusal, GateResult)
                and refusal.gate_id == "assembly_merge_noise"
                and "observable obs_x" in str(refusal.detail)
                and applied.exists(),
                str(refusal)[:200],
            )
            check(
                f"[{how}] the round has no observation-model reply in the record",
                not (ctx.agent_calls.child("observation") / "reply").exists(),
            )
            for reused in (True, False):
                out, printed = _battery(ctx, refusal, reused_shared=reused)
                check(
                    f"[{how}, shared passed elsewhere: {reused}] CandidateDefect "
                    f"naming the candidate and the check",
                    isinstance(out, S3.CandidateDefect)
                    and out.candidate == CAND
                    and "its observation axis makes the assembly fail assembly_merge_noise"
                    in out.reason
                    and "obs_x" in out.reason,
                    _first(out) + (" · " + printed[-160:] if printed else ""),
                )
            check(
                f"[{how}] no agent was called and no re-ask was attributed",
                not ctx.calls and not _rows(ctx, "redraft_attributed"),
                f"calls={ctx.calls}",
            )


# ------------------------------------ 2. a check that names no observable


def test_a_check_naming_no_observable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Ctx(_record(tmp))
        refusal = _merge(ctx, _floor_overlay(), _shared())
        assert isinstance(refusal, GateResult), refusal
        vague = GateResult(
            "assembly_formulas_compile_safe",
            "T0",
            False,
            detail="a formula names a function AMICI does not know",
        )
        out, _ = _battery(ctx, vague, reused_shared=True)
        check(
            "the shared assembly passed elsewhere: the overlay is what differs — "
            "CandidateDefect",
            isinstance(out, S3.CandidateDefect)
            and "fail assembly_formulas_compile_safe" in out.reason,
            _first(out),
        )
        stops: list[dict] = []

        def _stop(ctx_, module, role, failing, block, history, budget, **kw):
            stops.append({"role": role, "gate": failing[0].gate_id})
            return "stop", None

        with _patched((battery_feedback, "failure_point_gate", _stop)):
            out, _ = _battery(ctx, vague, reused_shared=False)
        check(
            "not passed elsewhere: not the overlay's — it goes to the failure point",
            type(out) is ModuleFailure and len(stops) == 1,
            _first(out) + f" · {stops}",
        )
        resolve = GateResult(
            "assembly_conditions_resolve",
            "T0",
            False,
            detail="condition c0 overrides k_missing, which the model does not define",
        )
        out, _ = _battery(ctx, resolve, reused_shared=True)
        check(
            "a resolve check naming no observable keeps its own rule and reason",
            isinstance(out, S3.CandidateDefect)
            and "the shared assembly passed on another candidate" in out.reason
            and "observation axis" not in out.reason,
            _first(out),
        )
        check("no agent was called", not ctx.calls, str(ctx.calls))


# -------------------------- 3. another observable's refusal, nobody to ask


def test_a_refusal_the_overlay_did_not_cause_reaches_the_failure_point() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Ctx(_record(tmp))
        # a harmless overlay on obs_x; the shared sigma of obs_y names B, which
        # is not obs_y's own formula (A)
        harmless = [
            {
                "change_noise_model": {
                    "observable_id": "obs_x",
                    "new_distribution": "laplace",
                }
            }
        ]
        refusal = _merge(ctx, harmless, _shared(y_noise="sy_abs + sy_rel * B"))
        check(
            "the merge refuses obs_y, which the overlay did not touch",
            isinstance(refusal, GateResult)
            and refusal.gate_id == "assembly_merge_noise"
            and battery_feedback.implicated_ids(refusal.detail, ["obs_x", "obs_y"])
            == ["obs_y"],
            str(refusal)[:200],
        )
        stops: list[dict] = []

        def _stop(ctx_, module, role, failing, block, history, budget, **kw):
            stops.append(
                {
                    "role": role,
                    "gate": failing[0].gate_id,
                    "block": block,
                    "history": history,
                }
            )
            return "stop", None

        with _patched((battery_feedback, "failure_point_gate", _stop)):
            out, printed = _battery(ctx, refusal, reused_shared=False)
        check(
            "it does not crash: the stop at the failure point is an honest ModuleFailure",
            type(out) is ModuleFailure and not isinstance(out, ArtifactError),
            _first(out),
        )
        check(
            "the failure-point gate was reached once, as the path where nobody can be asked",
            len(stops) == 1
            and stops[0]["role"] is None
            and stops[0]["gate"] == "assembly_merge_noise"
            and stops[0]["history"] is None,
            str([{k: v for k, v in s.items() if k != "block"} for s in stops]),
        )
        notes = [
            e
            for e in _rows(ctx, "note")
            if "no reply of this round in the record to re-ask" in str(e.get("note"))
        ]
        check(
            "the ledger says the role had no reply of this round in the record",
            len(notes) == 1
            and notes[0].get("role") == "observation"
            and notes[0].get("candidate") == CAND
            and str(notes[0].get("note", "")).startswith("observation:"),
            str(notes)[:240],
        )
        check(
            "… and the console says where the check went",
            "goes to the failure point" in printed,
            printed.strip().splitlines()[-1][:200] if printed.strip() else "",
        )
        check(
            "no agent was called and no attempt was charged",
            not ctx.calls
            and not _rows(ctx, "redraft_attributed")
            and not dossier_of(ctx, "observation").exists(),
            f"calls={ctx.calls}",
        )


# ------------------------------------------- 4. the orchestrator's loop


class _Stop(Exception):
    """Raised at the compile card: the assembly loop is what is under test."""

    def __init__(self, cand_ids):
        super().__init__("compile card")
        self.cand_ids = list(cand_ids)


class _Orch:
    """The candidate loop on a stand-in orchestrator."""

    _fit_and_select_once = Orchestrator._fit_and_select_once

    def __init__(self, ctx):
        self.ctx, self.ledger = ctx, ctx.ledger
        self.root, self.store = ctx.root, ctx.store

    def _remerge_stale_candidates(self, cand_ids):
        pass


def test_the_candidate_loop_drops_it_and_keeps_the_others() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        case = tmp / "input"
        case.mkdir()
        (case / "testcase.yaml").write_text(
            "name: overlay_refusal\nt_end: 8\nholdout:\n  condition_labels: []\n"
        )
        root = _record(tmp_s)
        (root / "intent").put(
            {
                "question": "does A decay into B?",
                "system": "toy",
                "inference_target": "mechanism_discrimination",
            }
        )
        ctx = RunContext(
            root=root,
            testcase_dir=case,
            spec=SPEC,
            ledger=Ledger(root),
            backend="stub",
            auto=False,
        )
        called: list[str] = []

        def _no_agent(role, context, calls=None, name=None):
            called.append(role)
            raise AssertionError(f"no agent may be called here; {role} was")

        ctx.call = _no_agent
        rnd = ctx.round
        (rnd / "data/measurements").put_table(_long_df())
        (rnd / "data/report").put({"flags": []})
        for m in ("s1", "s2"):
            ctx.round_markers.child(m).put({"producer": "unit test"})
        # the carried shared assembly, audited where it was built
        (rnd / "shared_assembly").put({**_shared(), "_version": 1})
        cands = ["base", CAND, "other"]
        for cid in cands:
            with as_candidate(ctx, cid):
                _stage_candidate(ctx.model, _floor_overlay() if cid == CAND else [])
        assembled: list[str] = []
        real_run = S3.run

        def _s3(c):
            assembled.append(c.candidate)
            if c.candidate == CAND:
                real_run(c)  # the real module: merge, refusal, battery loop

        buf = io.StringIO()
        patches = _patched(
            (data_module, "run", lambda c: None),
            (assembly_module, "run", _s3),
            (_render, "decisions_md", lambda rd_: ""),
            (compile_gate, "ask", lambda c, ids: (_ for _ in ()).throw(_Stop(ids))),
        )
        try:
            with patches, contextlib.redirect_stdout(buf):
                _Orch(ctx)._fit_and_select_once(list(cands))
            out = None
        except _Stop as e:
            out = e
        except Exception as e:  # noqa: BLE001 — the outcome under test
            out = e
        check(
            "the round continues to the compile card with the other candidates",
            isinstance(out, _Stop) and out.cand_ids == ["base", "other"],
            (
                f"reached with {out.cand_ids}"
                if isinstance(out, _Stop)
                else _first(out) + " · " + buf.getvalue()[-240:]
            ),
        )
        check(
            "every candidate was assembled in turn",
            assembled == cands,
            str(assembled),
        )
        drops = [
            e for e in ctx.ledger.entries() if e.get("event") == "candidate_dropped"
        ]
        check(
            "one candidate_dropped, for the overlay candidate, at assembly, with the check",
            len(drops) == 1
            and drops[0].get("candidate") == CAND
            and drops[0].get("module") == "assembly"
            and str(drops[0].get("reason", "")).startswith(
                "its observation axis makes the assembly fail assembly_merge_noise"
            ),
            str(drops)[:300],
        )
        printed = [ln for ln in buf.getvalue().splitlines() if "dropped" in ln]
        check(
            "the drop is printed by name",
            len(printed) == 1 and f"candidate {CAND} dropped" in printed[0],
            f"{len(printed)} line(s)",
        )
        check("no agent was called", not called, str(called))


def main() -> int:
    test_the_overlay_refusal_is_the_candidates_defect()
    test_a_check_naming_no_observable()
    test_a_refusal_the_overlay_did_not_cause_reaches_the_failure_point()
    test_the_candidate_loop_drops_it_and_keeps_the_others()
    return finish(
        "\nOVERLAY REFUSAL UNIT",
        "\nOVERLAY REFUSAL UNIT OK — an overlay's refusal drops its candidate by name, "
        "another refusal with nobody to ask goes to the failure point, and nothing "
        "reads a reply that is not in the record",
    )


if __name__ == "__main__":
    sys.exit(main())
