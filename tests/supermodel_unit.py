"""The supermodel encoding: what it absorbs, what it refuses, and what it verifies.

  1. with nothing declared it reduces exactly to an independent per-candidate encoder;
  2. neutralizable axes share one structure, each off-state pinned at neutral values;
  3. with keep_base the all-off member is the base model itself;
  4. an axis with no parameter, a textual neutral value, or on observables is refused;
  5. a log10 off-state of 0 and a neutral value outside the box are accepted;
  6. axes sharing a reaction, or one parameter with two off-states, are separated;
  7. a wrong neutral value is caught by simulation, per axis;
  8. a neutral strength suffices when its K is inert; a K that is not is caught;
  9. the neutrality gate is recorded, non-blocking, and the encoding persisted;
 10. candidates group by SBML structure for the PEtab Select subspaces.

    uv run python tests/supermodel_unit.py
"""

from __future__ import annotations

import itertools
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.model import model_space, supermodel  # noqa: E402
from tests._record import record_at, rnd, work  # noqa: E402

BASE = """model cell
  R1: A -> B; k1*A;
  A = 1; B = 0; k1 = 0.5;
end
"""
BASE_PAR = [
    {"id": "k1", "lb": 1e-3, "ub": 10.0, "nominal_value": 0.5, "estimate": True}
]
T_END = 10.0


def par(pid, *, lb=0.0, ub=1.0, nominal=0.1, neutral=None):
    p = {"id": pid, "lb": lb, "ub": ub, "nominal_value": nominal, "estimate": True}
    if neutral is not None:
        p["neutral_value"] = neutral
    return p


def ax(aid, patch, adds):
    return {"id": aid, "on_antimony_patch": patch, "adds_parameters": adds}


# an added route, off at rate 0
ALT = ax("alt_route", {"append": "R2: A -> C; k2*A"}, [par("k2", neutral=0.0)])
# a saturation written as a strength that is off at 0, rather than a Km whose
# off-state is infinity
SAT = ax(
    "sat_law",
    {"replace_reaction": "R1", "with": "R1: A -> B; k1*A/(1+beta*A)"},
    [par("beta", ub=10.0, nominal=1.0, neutral=0.0)],
)


def reference_enumerate(base_antimony, base_parameters, axes, max_models):
    """The per-candidate encoding, reimplemented to check the reduction against."""
    out = []
    for bits in itertools.product([False, True], repeat=len(axes)):
        on = [a for a, b in zip(axes, bits, strict=False) if b]
        ant, params, overlay, ok = base_antimony, list(base_parameters), [], True
        for a in on:
            if a.get("on_assembly_patch"):
                overlay.append(a["on_assembly_patch"])
            else:
                ant, applied = model_space.apply_patch(ant, a["on_antimony_patch"])
                if not applied:
                    ok = False
                    break
            for p in a["adds_parameters"]:
                if p["id"] not in {q["id"] for q in params}:
                    params = params + [dict(p)]
                ant = model_space.declare_parameter(ant, p)
        if not ok:
            continue
        ids = [a["id"] for a in on]
        out.append(
            {
                "model_id": "base" if not ids else "+".join(ids),
                "axes_on": ids,
                "antimony": ant,
                "parameters": params,
                "assembly_overlay": overlay,
                "n_estimated": sum(1 for p in params if p.get("estimate", True)),
            }
        )
        if len(out) >= max_models:
            break
    return out


class FakeCtx:
    """Just the surface `_record_encoding` touches."""

    def __init__(self, root):
        self.root = root  # the record root: the run is one file
        self.round_idx = 0
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, 0)


def main() -> int:
    # 1 ---- EXACT reduction when nothing is declared ----------------------
    plain = [
        ax("alt_route", {"append": "R2: A -> C; k2*A"}, [par("k2", lb=1e-4)]),
        ax(
            "sat_law",
            {"replace_reaction": "R1", "with": "R1: A -> B; k1*A/(1+A/Km)"},
            [par("Km", lb=1e-3, ub=10.0, nominal=1.0)],
        ),
    ]
    ref = reference_enumerate(BASE, BASE_PAR, plain, 8)
    got = model_space.enumerate_with_encoding(BASE, BASE_PAR, plain, 8, t_end=T_END)
    fields = (
        "model_id",
        "axes_on",
        "antimony",
        "parameters",
        "assembly_overlay",
        "n_estimated",
    )
    identical = len(ref) == len(got["models"]) and all(
        all(a[f] == b[f] for f in fields)
        for a, b in zip(ref, got["models"], strict=False)
    )
    check(
        "with nothing declared, the encoder reduces EXACTLY to the old one",
        identical,
        f"{len(ref)} vs {len(got['models'])} candidates, every field equal={identical}",
    )
    check(
        "and says so, naming each axis's missing declaration",
        got["encoding"]["kind"] == "separate"
        and all(
            "no neutral_value" in r for r in got["encoding"]["why_separate"].values()
        ),
        f"{got['encoding']['why_separate']}",
    )

    # 2 ---- the supermodel: one structure, parameter tables apart ---------
    res = model_space.enumerate_with_encoding(
        BASE, BASE_PAR, [ALT, SAT], 8, t_end=T_END
    )
    enc, models = res["encoding"], res["models"]
    check(
        "two neutralizable axes give 4 candidates over ONE structure",
        len(models) == 4 and enc["n_structures"] == 1 and enc["compiles_saved"] == 3,
        f"{len(models)} models, {enc['n_structures']} structure(s), "
        f"{enc['compiles_saved']} saved",
    )
    check(
        "every candidate is the same model text",
        len({m["antimony"] for m in models}) == 1,
    )
    by_id = {m["model_id"]: m for m in models}
    base_cand = by_id["base"]
    fixed = {
        p["id"]: p["nominal_value"]
        for p in base_cand["parameters"]
        if p.get("fixed_at_neutral")
    }
    check(
        "the base candidate pins both axis parameters at their neutral values",
        fixed == {"k2": 0.0, "beta": 0.0}
        and not any(
            p.get("estimate") for p in base_cand["parameters"] if p["id"] in fixed
        ),
        f"{fixed}",
    )
    check(
        "the all-on candidate pins nothing",
        not [
            p
            for p in by_id["alt_route+sat_law"]["parameters"]
            if p.get("fixed_at_neutral")
        ],
    )
    check(
        "candidate ids still follow DECLARATION order",
        sorted(by_id) == sorted(["base", "alt_route", "sat_law", "alt_route+sat_law"]),
        f"{sorted(by_id)}",
    )
    check(
        "n_estimated separates the candidates, which is what the criterion reads",
        [
            by_id[k]["n_estimated"]
            for k in ("base", "alt_route", "sat_law", "alt_route+sat_law")
        ]
        == [1, 2, 2, 3],
        f"{[by_id[k]['n_estimated'] for k in ('base', 'alt_route', 'sat_law', 'alt_route+sat_law')]}",
    )

    # 2b --- an expansion round's base stays the model it was --------------
    kept = model_space.enumerate_with_encoding(
        BASE, BASE_PAR, [ALT, SAT], 8, t_end=T_END, keep_base=True
    )
    kept_by_id = {m["model_id"]: m for m in kept["models"]}
    check(
        "keep_base: the all-off member is the base model itself, not the "
        "structure with the axes switched off",
        kept_by_id["base"]["antimony"] == BASE
        and kept_by_id["base"]["parameters"] == BASE_PAR
        and kept_by_id["base"]["fixed_at_neutral"] == [],
        kept_by_id["base"].get("encoding"),
    )
    check(
        "keep_base: every other member is untouched and the base is one more "
        "structure",
        all(
            kept_by_id[k]["antimony"] == by_id[k]["antimony"]
            and kept_by_id[k]["parameters"] == by_id[k]["parameters"]
            for k in by_id
            if k != "base"
        )
        and kept["encoding"]["n_structures"] == 2,
        f"{kept['encoding']['n_structures']} structure(s)",
    )

    # 3 ---- the refusals, one per rule -----------------------------------
    cases = {
        "an axis that adds no parameter at all": (
            ax("free", {"append": "R2: A -> C; k1*A"}, []),
            "adds no parameter",
        ),
        "a non-numeric neutral value": (
            ax("texty", {"append": "R2: A -> C; kz*A"}, [par("kz", neutral="off")]),
            "non-numeric",
        ),
    }
    for name, (axis, expect) in cases.items():
        ok, why = supermodel.axis_neutralizable(axis)
        check(f"refused: {name}", not ok and expect in why, why)

    # ---- and the two things that are NOT refused --------------------------
    #      A log10 off-state of 0 and a neutral value outside the box are fine:
    #      the box constrains estimation, and pyPESTO unscales -inf back to 0.
    logscale = ax(
        "logscale", {"append": "R2: A -> C; kx*A"}, [par("kx", lb=1e-5, neutral=0.0)]
    )
    ok, why = supermodel.axis_neutralizable(logscale)
    check(
        "a log10-scaled parameter with an off-state of 0 is ACCEPTED",
        ok,
        why or "accepted",
    )
    outside = ax(
        "outside",
        {"append": "R2: A -> C; ky*A"},
        [par("ky", lb=0.1, ub=1.0, neutral=0.0)],
    )
    ok, why = supermodel.axis_neutralizable(outside)
    check(
        "a neutral value outside the estimation box is ACCEPTED",
        ok,
        why or "accepted — a fixed value is not an estimated value",
    )
    # and it really does neutralize, by simulation, on a log-scaled axis
    v_log = supermodel.verified_partition(BASE, [logscale], T_END)
    check(
        "and the log-scaled axis is absorbed after its declaration is VERIFIED",
        [str(a["id"]) for a in v_log["neutral"]] == ["logscale"]
        and v_log["verification"]["per_axis"]["logscale"]["neutralizes"] is True,
        f"{v_log['verification']['per_axis']}",
    )

    obs = {
        "id": "offset",
        "on_assembly_patch": {"add_offset": {"observable_label": "x"}},
        "adds_parameters": [par("off_x", neutral=0.0)],
    }
    ok, why = supermodel.axis_neutralizable(obs)
    check(
        "refused: an observation axis (the model is untouched)",
        not ok and "model is untouched" in why,
        why,
    )

    # 4 ---- non-interference: same reaction, and same parameter id -------
    clash_rxn = [
        ax(
            "sat_a",
            {"replace_reaction": "R1", "with": "R1: A -> B; k1*A/(1+b1*A)"},
            [par("b1", ub=10.0, nominal=1.0, neutral=0.0)],
        ),
        ax(
            "sat_b",
            {"replace_reaction": "R1", "with": "R1: A -> B; k1*A*(1+b2*B)"},
            [par("b2", ub=10.0, nominal=1.0, neutral=0.0)],
        ),
    ]
    part = supermodel.partition(clash_rxn)
    check(
        "two axes replacing ONE reaction are both separated, each naming the other",
        not part["neutral"]
        and "sat_b" in part["why_separate"]["sat_a"]
        and "sat_a" in part["why_separate"]["sat_b"],
        f"{part['why_separate'].get('sat_a', '')[:90]}",
    )

    clash_par = [
        ax("uses_p_off_at_0", {"append": "R2: A -> C; p*A"}, [par("p", neutral=0.0)]),
        ax(
            "uses_p_off_at_1",
            {"append": "R3: A -> E; k1*A*(p-1)"},
            [par("p", ub=10.0, nominal=2.0, neutral=1.0)],
        ),
    ]
    part = supermodel.partition(clash_par)
    check(
        "two axes reusing ONE parameter with different off-states are separated",
        not part["neutral"]
        and "two off-states" in part["why_separate"]["uses_p_off_at_0"],
        f"{part['why_separate'].get('uses_p_off_at_0', '')[:110]}",
    )
    agree = [
        ax("a1", {"append": "R2: A -> C; q*A"}, [par("q", neutral=0.0)]),
        ax("a2", {"append": "R3: A -> E; q*A"}, [par("q", neutral=0.0)]),
    ]
    check(
        "but two axes AGREEING on one parameter's off-state still compose",
        len(supermodel.partition(agree)["neutral"]) == 2,
    )

    # 5 ---- verification: honest, and a lie ------------------------------
    v = supermodel.verified_partition(BASE, [ALT, SAT], T_END)
    check(
        "an honest declaration is verified by simulation and absorbed",
        [str(a["id"]) for a in v["neutral"]] == ["alt_route", "sat_law"]
        and all(x["neutralizes"] for x in v["verification"]["per_axis"].values()),
        f"{v['verification']['per_axis']}",
    )
    LIE = ax(
        "sat_lie",
        {"replace_reaction": "R1", "with": "R1: A -> B; k1*A/(1+beta*A)"},
        [par("beta", ub=10.0, nominal=1.0, neutral=1.0)],  # 1 does NOT turn it off
    )
    v = supermodel.verified_partition(BASE, [ALT, LIE], T_END)
    check(
        "a WRONG neutral value is caught by simulation and separated",
        [str(a["id"]) for a in v["neutral"]] == ["alt_route"]
        and v["verification"]["per_axis"]["sat_lie"]["neutralizes"] is False,
        f"absorbed {[str(a['id']) for a in v['neutral']]}",
    )
    check(
        "the reason quotes the measured mismatch, not just a verdict",
        "relative difference" in v["why_separate"]["sat_lie"],
        v["why_separate"]["sat_lie"][:120],
    )
    check(
        "per axis, not all-or-nothing: the honest axis keeps its place",
        v["verification"]["per_axis"]["alt_route"]["neutralizes"] is True,
    )

    # 5b --- a neutral value on the STRENGTH alone suffices ------------------
    #        `k*A/(K + A)` has no honest off-state for K, but k = 0 makes K
    #        irrelevant.
    STRENGTH_K = ax(
        "sat_kK",
        {"replace_reaction": "R1", "with": "R1: A -> B; k1*A + k_s*A/(K_s + A)"},
        [
            par("k_s", ub=5.0, nominal=0.3, neutral=0.0),
            par("K_s", lb=1e-2, ub=10.0, nominal=0.5),  # no neutral value
        ],
    )
    ok, why = supermodel.axis_neutralizable(STRENGTH_K)
    check(
        "an axis whose strength declares a neutral value is neutralizable "
        "although its K declares none",
        ok,
        why,
    )
    v = supermodel.verified_partition(BASE, [STRENGTH_K], T_END)
    check(
        "… and the simulation VERIFIES it: k_s = 0 with K_s at nominal "
        "reproduces the base model",
        [str(a["id"]) for a in v["neutral"]] == ["sat_kK"]
        and v["verification"]["per_axis"]["sat_kK"]["neutralizes"] is True,
        f"{v['why_separate']} {v['verification']['per_axis']}",
    )
    enc = supermodel.enumerate_grouped(BASE, BASE_PAR, [STRENGTH_K], 8, t_end=T_END)
    off = next(m for m in enc["models"] if m["model_id"] == "base")
    on = next(m for m in enc["models"] if m["model_id"] == "sat_kK")
    off_p = {p["id"]: p for p in off["parameters"]}
    on_p = {p["id"]: p for p in on["parameters"]}
    check(
        "the OFF candidate fixes the strength at 0 AND the K at its nominal, "
        "neither estimated",
        off_p["k_s"]["estimate"] is False
        and off_p["k_s"]["nominal_value"] == 0.0
        and off_p["K_s"]["estimate"] is False
        and off_p["K_s"]["nominal_value"] == 0.5
        and off_p["K_s"].get("inert_at_neutral") is True
        and off_p["K_s"].get("fixed_at_neutral") is True,
        f"k_s={off_p['k_s']} K_s={off_p['K_s']}",
    )
    check(
        "the ON candidate estimates both",
        on_p["k_s"].get("estimate", True) is True
        and on_p["K_s"].get("estimate", True) is True
        and "inert_at_neutral" not in on_p["K_s"],
    )
    check(
        "one compiled structure for the two candidates, k differs by two",
        enc["encoding"]["n_structures"] == 1
        and enc["encoding"]["compiles_saved"] == 1
        and off["n_estimated"] == on["n_estimated"] - 2
        and sorted(off["fixed_at_neutral"]) == ["K_s", "k_s"],
        f"{enc['encoding']['n_structures']} structure(s), "
        f"n_est off={off['n_estimated']} on={on['n_estimated']}, "
        f"fixed={off['fixed_at_neutral']}",
    )
    K_ONLY = ax(
        "k_only",
        {"replace_reaction": "R1", "with": "R1: A -> B; k1*A/(K_o + A)"},
        [par("K_o", lb=1e-2, ub=10.0, nominal=0.5)],
    )
    ok, why = supermodel.axis_neutralizable(K_ONLY)
    check(
        "an axis in which NO parameter declares a neutral value is refused, "
        "naming the parameter",
        not ok and "K_o" in why and "neutral_value" in why,
        why,
    )
    # a lie about inertness is caught the way a wrong neutral value is: here
    # the strength does not multiply the K term, so k_n = 0 leaves it standing
    NOT_INERT = ax(
        "sat_notinert",
        {"replace_reaction": "R1", "with": "R1: A -> B; k1*A/(K_n + A) + k_n*A"},
        [
            par("k_n", ub=5.0, nominal=0.3, neutral=0.0),
            par("K_n", lb=1e-2, ub=10.0, nominal=0.5),
        ],
    )
    v = supermodel.verified_partition(BASE, [NOT_INERT], T_END)
    check(
        "a K that is NOT inert at the strength's zero is caught by simulation "
        "and separated",
        [str(a["id"]) for a in v["neutral"]] == []
        and v["verification"]["per_axis"]["sat_notinert"]["neutralizes"] is False
        and "relative difference" in v["why_separate"]["sat_notinert"],
        f"{v['why_separate']}",
    )
    from octomod.agents import ROLES

    check(
        "construction AND revision are told the rule",
        all(
            "switches the whole term off" in ROLES[r].contract
            and "neutral_value" in ROLES[r].contract
            for r in ("construction", "revision")
        ),
    )

    # 6 ---- the gate record ----------------------------------------------
    from octomod.workflow_modules.model.engine import _record_encoding

    for label, axes, expect_pass in (
        ("honest", [ALT, SAT], True),
        ("with a lie", [ALT, LIE], False),
    ):
        ctx = FakeCtx(record_at(Path(tempfile.mkdtemp()) / "run"))
        enc = model_space.enumerate_with_encoding(BASE, BASE_PAR, axes, 8, t_end=T_END)[
            "encoding"
        ]
        _record_encoding(ctx, enc)
        rec = (ctx.round / "gates").child("model_supermodel_neutrality").get({})
        check(
            f"the neutrality gate is recorded and {'passes' if expect_pass else 'fails'} ({label})",
            rec.get("passed") is expect_pass and rec.get("tier") == "T1",
            f"passed={rec.get('passed')} detail={str(rec.get('detail'))[:80]}",
        )
        check(
            f"the gate is non-blocking, so a false declaration costs no round ({label})",
            rec.get("blocking") is False,
        )
        check(
            f"the encoding is persisted for the report to read ({label})",
            (ctx.round / "model/encoding").exists(),
        )

    # 7 ---- the PEtab Select side: one subspace per STRUCTURE -------------
    #        No canned axis declares a neutral value, so the candidate work
    #        groups are built here from the static PEtab fixture: two share a structure.
    from octomod.workflow_modules.evaluation import selection as _sel

    fixture = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
    if not (fixture / "problem.yaml").exists():
        check("the static PEtab fixture is present", False, f"missing {fixture}")
    else:
        base_inp = petab_io.from_dir(fixture)
        fixture_sbml = (fixture / "model.xml").read_text()
        root = record_at(Path(tempfile.mkdtemp()) / "select")
        rows = []
        for cid, fix_last, tweak_sbml in (
            ("shared_on", False, False),
            ("shared_off", True, False),  # same structure, one parameter pinned
            ("other_structure", False, True),  # different SBML
        ):
            wd = work(root, 0, cid)
            frame = base_inp.parameters.copy()
            target = str(frame[frame.estimate == 1].parameterId.iloc[-1])
            if fix_last:
                frame.loc[frame.parameterId == target, "estimate"] = 0
                frame.loc[frame.parameterId == target, "nominalValue"] = 0.0
            petab_io.to_record(base_inp.with_tables(parameters=frame), wd / "petab")
            sbml = fixture_sbml
            if tweak_sbml:
                sbml = sbml.replace(
                    "</model>", "<!-- a different structure --></model>"
                )
            (wd / "model/sbml").put_text(sbml)
            rows.append({"id": cid, "work": wd, "pinned": target if fix_last else None})

        groups = _sel.structure_groups(rows)
        sizes = sorted(len(v) for v in groups.values())
        check(
            "candidates over one structure group together, a different SBML apart",
            sizes == [1, 2],
            f"group sizes {sizes} over {len(groups)} group(s)",
        )
        shared = next(v for v in groups.values() if len(v) == 2)
        check(
            "the group is the pair that shares the SBML, not the pair that shares an id prefix",
            {r["id"] for r in shared} == {"shared_on", "shared_off"},
            f"{sorted(r['id'] for r in shared)}",
        )
        # and the alternatives a subspace would declare for that pair
        try:
            import petab_select as ps

            values: dict[str, list] = {}
            for r in shared:
                for pid, v in _sel.params_of(r["work"], ps).items():
                    values.setdefault(pid, [])
                    if v not in values[pid]:
                        values[pid].append(v)
            pinned = next(r["pinned"] for r in shared if r["pinned"])
            check(
                "the shared parameter carries BOTH alternatives — the native encoding",
                sorted(map(str, values[pinned])) == sorted(["0.0", str(ps.ESTIMATE)]),
                f"{pinned}: {values[pinned]}",
            )
            multi = {k: v for k, v in values.items() if len(v) > 1 and k != pinned}
            check(
                "and a parameter both candidates estimate carries just the one",
                not multi,
                (
                    f"unexpectedly multi-valued: {multi}"
                    if multi
                    else "only the pinned one varies"
                ),
            )
        except ImportError as e:
            check("petab_select is importable", False, str(e))

    print()
    return finish(
        "SUPERMODEL",
        "SUPERMODEL OK — absorbs what it can verify, refuses the rest by name",
    )


if __name__ == "__main__":
    raise SystemExit(main())
