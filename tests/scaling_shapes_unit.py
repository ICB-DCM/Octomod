"""Per-timepoint and per-condition scaling are expressible, render, and compile.

  1. the contract, the skill, `assembly_edit` and `NOISE_SHAPES` share one vocabulary;
  2. the seam checks refuse every malformed shape by name;
  3. `shared_across_conditions: false` is honoured as `per: condition`;
  4. compiled with AMICI, `rdata.y` and `rdata.sigmay` reproduce a planted gain;
  5. hierarchical: unpinned factors are inner and solved; gain-scaled noise is refused;
  6. a live run's dropped axis: its intent is a legal patch, its literal is refused;
  7. a held-out condition's flattened observable ids all exist in the problem.

    uv run python tests/scaling_shapes_unit.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))


logging.disable(logging.CRITICAL)

from _harness import check, finish, fixture_or_skip  # noqa: E402
from _record import ledger_rows, record_at, rnd, run_root  # noqa: E402

from octomod import (  # noqa: E402
    config,  # noqa: E402
)
from octomod.agents import ROLES  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import (  # noqa: E402
    assembly_edit,
    hierarchical,
    petab_io,
)
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402
from octomod.workflow_modules.estimation.problem import build_problem  # noqa: E402
from octomod.workflow_modules.model import model_space  # noqa: E402

# The user's runs folder, not the battery's redirected one: this reads their
# previous runs, not runs this suite makes.
USER_RUNS = config.USER_RUNS_DIR

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
KDEG, A0, SIG = 0.3, 10.0, 0.2
TIMES = [0.0, 1.0, 2.0, 4.0]
GAIN = {0.0: 1.0, 1.0: 2.0, 2.0: 0.5, 4.0: 4.0}


def _sbml() -> str:
    import antimony

    antimony.loadAntimonyString(
        f"model m; A={A0}; B=0; J0: A->B; kdeg*A; kdeg={KDEG}; end"
    )
    return antimony.getSBMLString(antimony.getMainModuleName())


def _state(t: float) -> tuple[float, float]:
    A = A0 * np.exp(-KDEG * t)
    return A, A0 - A


class Ctx:
    def __init__(self, root, spec=SPEC, holdout: list[str] | None = None):
        # `root` is a temp directory; the run is one record file inside it
        root = record_at(Path(root) / "run")
        self.root, self.store = root, root.store
        self.round_idx, self.candidate = 0, None
        self.spec, self.ledger, self.cache = spec, Ledger(root), {}
        self._holdout = holdout or []

    @property
    def round(self):
        return rnd(self.root, 0)

    @property
    def work(self):
        return tree.work_node(self.round, None)

    @property
    def model(self):
        return tree.model_node(self.round, None)

    def problem(self) -> petab_io.PetabInput:
        """The rendered problem, as `build_problem` takes it."""
        return petab_io.from_work(self.work, self.model)

    @property
    def testcase(self) -> dict:
        return {"holdout": {"condition_labels": list(self._holdout)}}


class HierSpec:
    """default.yaml with the hierarchical knob ON."""

    def __init__(self, base):
        self.base = base

    def get(self, k, d=None):
        return True if k == "estimation.hierarchical" else self.base.get(k, d)

    def require(self, k):
        return True if k == "estimation.hierarchical" else self.base.require(k)


def _reply(noise: str, scaling: dict) -> dict:
    return {
        "observables": [
            {
                "observable_id": oid,
                "maps_to_label": lbl,
                "formula": sp,
                "transformation": "lin",
                "noise": {
                    "distribution": "normal",
                    "formula": noise.replace("<o>", oid),
                    "estimate_sigma": True,
                },
                "scaling": dict(scaling),
                "rationale": "-",
            }
            for oid, lbl, sp in (("obs_a", "peakA", "A"), ("obs_b", "peakB", "B"))
        ]
    }


def _long_df(conditions=("c0",)) -> pd.DataFrame:
    rows = []
    for ci, c in enumerate(conditions):
        for t in TIMES:
            A, B = _state(t)
            g = GAIN[t] * (1.0 + ci)  # a second condition doubles every gain
            rows.append(
                {
                    "observable_label": "peakA",
                    "condition_label": c,
                    "condition_key": c,
                    "time": t,
                    "value": g * A,
                }
            )
            rows.append(
                {
                    "observable_label": "peakB",
                    "condition_label": c,
                    "condition_key": c,
                    "time": t,
                    "value": g * B,
                }
            )
    return pd.DataFrame(rows)


def _render(reply: dict, root: Path, spec=SPEC, conditions=("c0",), holdout=None):
    """Render `reply` into a fresh record; returns (ctx, the `petab` node)."""
    ctx = Ctx(root, spec, holdout)
    sbml = _sbml()
    (ctx.model / "sbml").put_text(sbml)
    (ctx.model / "parameters").put(
        [
            {
                "id": "kdeg",
                "nominal_value": KDEG,
                "lb": 1e-3,
                "ub": 1e3,
                "estimate": True,
            }
        ]
    )
    problems = S3._observation_reply_problems(
        reply, ["peakA", "peakB"], {"A", "B", "kdeg"}
    )
    assert not problems, problems
    obs, noise, scaling = S3.split_observation_reply(reply)
    assembly = {
        "observables": obs,
        "noise": noise,
        "scaling": scaling,
        "conditions": [
            {
                "condition_id": c,
                "maps_to_label": c,
                "overrides": {},
                "preequilibration": False,
            }
            for c in conditions
        ],
    }
    petab = ctx.work / "petab"
    S3._merge_to_petab(ctx, assembly, sbml, _long_df(conditions), petab)
    return ctx, petab


PER_TIME = {
    "mode": "factor",
    "scale_parameter": "sc_ms",
    "per": "timepoint",
    "shared_across_observables": "ms",
}


# ------------------------------------------------------------------ 1 drift


def test_one_vocabulary_in_four_places() -> None:
    contract = ROLES["observation"].contract
    skill = (REPO / "skills" / "observation.md").read_text()
    for per in assembly_edit.SCALING_PER:
        check(
            f"contract and skill both offer per: {per}",
            f'"{per}"' in contract and f"`per: {per}`" in skill or per in skill,
        )
    for field in assembly_edit.SCALING_FIELDS:
        check(
            f"contract and skill both name `{field}`",
            field in contract and field in skill,
        )
    check(
        "change_scaling is a kind",
        "change_scaling" in assembly_edit.KINDS
        and "change_scaling" in assembly_edit.OBSERVABLE_KINDS,
    )
    for role in ("observation", "construction", "revision"):
        check(
            f"{role}'s contract names change_scaling",
            "change_scaling" in ROLES[role].contract,
        )
    names = [n for n, _f, _w in S3.NOISE_SHAPES]
    check(
        "NOISE_SHAPES carries the gain-scaled shape", "gain-scaled" in names, str(names)
    )
    check(
        "contract and skill both offer it",
        "gain-scaled" in contract and "gain-scaled" in skill,
    )
    check(
        "the assembly_edit docstring lists change_scaling",
        "change_scaling" in assembly_edit.__doc__,
    )
    # the contract, the skill and the code agree on every kind
    missing = [k for k in assembly_edit.KINDS if not (k in contract and k in skill)]
    check(
        "every patch kind is named in both the contract and the skill",
        not missing,
        ", ".join(missing) or f"all {len(assembly_edit.KINDS)} kinds",
    )


# ------------------------------------------------------------- 2 seam checks


def test_malformed_shapes_are_refused_by_name() -> None:
    def probs(sc_a: dict, sc_b: dict | None = None) -> list[str]:
        r = _reply("sigma_<o>", sc_a)
        if sc_b is not None:
            r["observables"][1]["scaling"] = dict(sc_b)
        return S3._observation_reply_problems(r, ["peakA", "peakB"], {"A", "B", "kdeg"})

    cases = {
        "per outside the vocabulary": (
            {"mode": "factor", "per": "weekly"},
            None,
            "scaling.per must be one of",
        ),
        "pin with one factor": (
            {"mode": "factor", "per": "observable", "pin_first_to_one": True},
            None,
            "pin_first_to_one needs per=timepoint",
        ),
        "per timepoint with mode none": (
            {"mode": "none", "per": "timepoint"},
            None,
            "declares a factor; mode is 'none'",
        ),
        "shared is not a name": (
            {"mode": "factor", "per": "timepoint", "shared_across_observables": 3},
            None,
            "GROUP",
        ),
        "group members disagree": (
            {"mode": "factor", "per": "timepoint", "shared_across_observables": "g"},
            {"mode": "factor", "per": "condition", "shared_across_observables": "g"},
            "disagree on per",
        ),
    }
    for name, (a, b, needle) in cases.items():
        got = probs(a, b)
        check(
            f"refused by name: {name}",
            any(needle in p for p in got),
            "; ".join(got) or "ACCEPTED",
        )
    check("the well-formed shape passes", not probs(PER_TIME))
    kinds_msg = ""
    try:
        assembly_edit.patch_kind({"a": 1, "b": 2})
    except ValueError as e:
        kinds_msg = str(e)
    check(
        "a malformed patch names the legal kinds",
        "change_scaling" in kinds_msg,
        kinds_msg[:80],
    )


# ------------------------------------------- 3 shared_across_conditions honoured


def test_shared_across_conditions_false_is_per_condition() -> None:
    reply = _reply(
        "sigma_<o>",
        {
            "mode": "factor",
            "scale_parameter": "sc_x",
            "shared_across_conditions": False,
        },
    )
    _o, _n, scaling = S3.split_observation_reply(reply)
    check(
        "the legacy field becomes per: condition",
        all(s["per"] == "condition" for s in scaling),
        str([s["per"] for s in scaling]),
    )
    with tempfile.TemporaryDirectory() as tmp:
        ctx, pdir = _render(
            _reply(
                "sigma_<o>",
                {"mode": "factor", "per": "condition", "scale_parameter": "sc_x"},
            ),
            Path(tmp),
            conditions=("c0", "c1"),
        )
        meas = (pdir / "measurements").table()
        par = (pdir / "parameters").table()
        by_cond = meas.groupby("simulationConditionId")["observableParameters"].agg(
            lambda s: sorted(set(s))
        )
        check(
            "one factor per condition, named by the condition",
            by_cond["c0"] == ["sc_x_c0"]
            and by_cond["c1"] == ["sc_x_c1"]
            and {"sc_x_c0", "sc_x_c1"} <= set(par["parameterId"]),
            str(dict(by_cond)),
        )
        obs = (pdir / "observables").table()
        check(
            "per-condition needs no flattening (AMICI accepts it)",
            len(obs) == 2,
            f"{len(obs)} observables",
        )
        prob, _pp, _cs = build_problem(ctx.problem(), {}, SPEC)
        check("and it compiles", prob is not None)


# ------------------------------------------------- 4 rdata.y reads the gain back


def _read_back(
    inp: petab_io.PetabInput, want: dict[str, float], gain_scaled: bool
) -> tuple[float, float]:
    prob, pp, _cs = build_problem(inp, {}, SPEC)
    free = [prob.x_names[i] for i in prob.x_free_indices]
    x = np.array([np.log10(want[n]) for n in free])
    out = prob.objective(x, return_dict=True, sensi_orders=(0,))
    rd = out["rdatas"][0]
    obs_ids = list(prob.objective.amici_model.get_observable_ids())
    ts = list(rd.ts)
    worst_y = worst_s = 0.0
    for _, r in pp.measurement_df.iterrows():
        j, i = obs_ids.index(r["observableId"]), ts.index(float(r["time"]))
        worst_y = max(worst_y, abs(rd.y[i, j] - float(r["measurement"])))
        expected = GAIN[float(r["time"])] * SIG if gain_scaled else SIG
        worst_s = max(worst_s, abs(rd.sigmay[i, j] - expected))
    return worst_y, worst_s


def test_amici_reproduces_the_planted_gain() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ctx, pdir = _render(
            _reply("sigma_<o>", {**PER_TIME, "pin_first_to_one": True}), Path(tmp)
        )
        par = (pdir / "parameters").table().set_index("parameterId")
        obs = (pdir / "observables").table()
        check(
            "the first factor is pinned: nominal 1, estimate 0",
            par.loc["sc_ms_t0", "estimate"] == 0
            and par.loc["sc_ms_t0", "nominalValue"] == 1.0,
        )
        check(
            "the other three are estimated",
            all(
                par.loc[f"sc_ms_{S3._time_tag(t)}", "estimate"] == 1 for t in TIMES[1:]
            ),
        )
        check(
            "flattened for AMICI, names kept",
            len(obs) == 8 and set(obs["observableName"]) == {"obs_a", "obs_b"},
            f"{len(obs)} observables",
        )
        notes = [r["note"] for r in ledger_rows(ctx.root) if "note" in r]
        check("the flatten is ledgered", any("flattened for AMICI" in n for n in notes))
        want = {
            "kdeg": KDEG,
            "sigma_obs_a": SIG,
            "sigma_obs_b": SIG,
            **{f"sc_ms_{S3._time_tag(t)}": GAIN[t] for t in TIMES},
        }
        wy, ws = _read_back(ctx.problem(), want, gain_scaled=False)
        check(
            "rdata.y == gain(t) x state(t) at every measured time",
            wy < 1e-5,
            f"max |Δ| = {wy:.2e}",
        )
        check("constant sigma unchanged by the gain", ws < 1e-12, f"max |Δ| = {ws:.2e}")
    with tempfile.TemporaryDirectory() as tmp:
        ctx, pdir = _render(_reply("sc_ms * sigma_ms", PER_TIME), Path(tmp))
        obs = (pdir / "observables").table()
        check(
            "gain-scaled noise renders as observable placeholder x noise placeholder",
            all(
                f.startswith("observableParameter1_") and "noiseParameter1_" in f
                for f in obs["noiseFormula"]
            ),
            obs["noiseFormula"].iloc[0],
        )
        want = {
            "kdeg": KDEG,
            "sigma_ms": SIG,
            **{f"sc_ms_{S3._time_tag(t)}": GAIN[t] for t in TIMES},
        }
        wy, ws = _read_back(ctx.problem(), want, gain_scaled=True)
        check("rdata.y still reads the gain back", wy < 1e-5, f"max |Δ| = {wy:.2e}")
        check(
            "rdata.sigmay == gain(t) x sigma at every point",
            ws < 1e-12,
            f"max |Δ| = {ws:.2e}",
        )


# ------------------------------------------------------------- 5 hierarchical


def test_hierarchical_solves_the_unpinned_factors() -> None:
    hs = HierSpec(SPEC)
    with tempfile.TemporaryDirectory() as tmp:
        ctx, pdir = _render(
            _reply("sigma_<o>", {**PER_TIME, "pin_first_to_one": True}),
            Path(tmp),
            spec=hs,
        )
        par = (pdir / "parameters").table()
        inner = hierarchical.inner_ids(par)
        check(
            "the three unpinned factors are marked inner, the pinned one is not",
            inner == ["sc_ms_t1", "sc_ms_t2", "sc_ms_t4"],
            str(inner),
        )
        prob, _pp, _cs = build_problem(ctx.problem(), {}, hs)
        free = [prob.x_names[i] for i in prob.x_free_indices]
        check(
            "the outer problem is kdeg and the two sigmas",
            free == ["kdeg", "sigma_obs_a", "sigma_obs_b"],
            str(free),
        )
        x = np.array([np.log10(v) for v in (KDEG, SIG, SIG)])
        out = prob.objective(x, return_dict=True, sensi_orders=(0,))
        got = sorted(float(v) for v in out.get("inner_parameters", []))
        want = sorted(np.log10([GAIN[1.0], GAIN[2.0], GAIN[4.0]]))
        check(
            "pyPESTO's inner solve returns the planted gains",
            len(got) == 3 and np.allclose(got, want, atol=1e-6),
            f"{got} vs {want}",
        )
    marks, reasons = hierarchical.marks(
        {
            "noise": [
                {
                    "observable_id": "o",
                    "distribution": "normal",
                    "formula": "sc_g * sigma_g",
                    "estimate_sigma": True,
                }
            ],
            "scaling": [
                {
                    "observable_id": "o",
                    "mode": "factor",
                    "scale_parameter": "sc_g",
                    "per": "timepoint",
                }
            ],
        },
        hs,
    )
    check(
        "gain-scaled noise is refused for hierarchical, with the reason",
        marks == {} and any("not a bare sigma" in r for r in reasons),
        "; ".join(reasons)[:100],
    )


# -------------------------------------------------------- 6 live-run replay


def test_blind_4s_intent_is_expressible_and_its_literal_is_refused() -> None:
    # the live run is one record, runs/live_ctd_blind_4.h5
    blind = run_root("live_ctd_blind_4", USER_RUNS)
    if not fixture_or_skip(blind.store.path, "runs/live_ctd_blind_4.h5"):
        return
    run = rnd(blind, 0)
    reply = ((run / "agent_calls").child("observation") / "reply").get()
    shared = (run / "shared_assembly").get()
    model = tree.model_node(run, tree.candidate_ids(run)[0])
    ant = (model / "antimony").text()
    pars = {str(p["id"]) for p in (model / "parameters").get()}
    with tempfile.TemporaryDirectory() as tmp:
        ctx = Ctx(Path(tmp))
        literal = dict(reply["model_space"][0])
        _axes, dropped = model_space.validate_axes(
            ctx, [literal], ant, pars, module="unit", base_assembly=shared
        )
        reason = dropped[0]["reason"] if dropped else ""
        check(
            "the literal reply is dropped (an invented shape)",
            bool(dropped),
            reason[:90],
        )
        check(
            "and the drop names change_scaling among the legal kinds",
            "change_scaling" in reason,
            reason[:120],
        )
        wanted = literal["on_assembly_patch"]["observation"]["scaling"]
        intent = {
            "id": literal["id"],
            "question": literal["question"],
            "priority": 1,
            "on_assembly_patch": {
                "change_scaling": {
                    "observable_ids": wanted["applies_to_observables"],
                    "per": "timepoint" if wanted.get("per_timepoint") else "observable",
                    "shared_across_observables": (
                        "ctd_ms" if wanted.get("shared_across_observables") else False
                    ),
                }
            },
        }
        axes, dropped = model_space.validate_axes(
            ctx, [intent], ant, pars, module="unit", base_assembly=shared
        )
        check(
            "what the agent MEANT is one legal patch, accepted",
            len(axes) == 1 and not dropped,
            str([d["reason"][:80] for d in dropped]),
        )
        applied = assembly_edit.apply_overlay(
            shared, [intent["on_assembly_patch"]], assembly_for_refs=shared
        )
        check(
            "applied, every peak shares one per-timepoint set",
            all(
                s["per"] == "timepoint" and s["scale_parameter"] == "sc_ctd_ms"
                for s in applied["scaling"]
            ),
            str(applied["scaling"][0]),
        )


# ---------------------------------------------------- 7 holdout stays consistent


def test_a_held_out_condition_shares_the_flattened_ids() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _ctx, pdir = _render(
            _reply("sigma_<o>", PER_TIME),
            Path(tmp),
            conditions=("c0", "c1"),
            holdout=["c1"],
        )
        obs = set((pdir / "observables").table()["observableId"])
        train = (pdir / "measurements").table()
        hold = (pdir / "holdout_measurements").table()
        check(
            "held-out rows exist and are the held-out condition",
            len(hold) == 8 and set(hold["simulationConditionId"]) == {"c1"},
            f"{len(hold)} rows",
        )
        check(
            "every held-out observable id is one the model has",
            set(hold["observableId"]) <= obs,
            str(sorted(set(hold["observableId"]) - obs)[:3]),
        )
        # petab's flatten groups by (observableParameters, noiseParameters,
        # condition), so the held-out condition owns its own flattened ids, each
        # naming its assembly observable through observableName
        names = (
            (pdir / "observables").table().set_index("observableId")["observableName"]
        )
        held = sorted(set(hold["observableId"]))
        check(
            "each held-out flattened id maps back to an assembly observable",
            set(names.loc[held]) == {"obs_a", "obs_b"},
            str(sorted(set(names.loc[held]))),
        )
        check(
            "held-out ids carry their own condition in the group key (petab's rule)",
            all(o.endswith("__c1") for o in held)
            and all(o.endswith("__c0") for o in train["observableId"]),
            str(held[:2]),
        )


def main() -> int:
    test_one_vocabulary_in_four_places()
    test_malformed_shapes_are_refused_by_name()
    test_shared_across_conditions_false_is_per_condition()
    test_amici_reproduces_the_planted_gain()
    test_hierarchical_solves_the_unpinned_factors()
    test_blind_4s_intent_is_expressible_and_its_literal_is_refused()
    test_a_held_out_condition_shares_the_flattened_ids()
    return finish(
        "SCALING SHAPES",
        "SCALING SHAPES OK — per-timepoint and per-condition scaling render, compile, and read back",
    )


if __name__ == "__main__":
    sys.exit(main())
