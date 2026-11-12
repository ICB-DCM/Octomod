"""The ΔAIC decomposition and term neutralisation: the split must add up.

  1. the per-point split equals AMICI's own likelihood to 1e-9;
  2. the per-group contributions sum to the likelihood half of the ΔAIC;
  3. the likelihood half plus the parameter half equal the whole ΔAIC;
  4. a split that is not exact is not shown at all;
  5. a rival that could not be evaluated is named, not dropped;
  6. a neutral value that is undeclared or shown not to neutralise is refused.

The two "candidates" are the static PEtab fixture at two parameter points: the
decomposition is a statement about two points, whatever produced them.

    uv run python tests/attribution_unit.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.evaluation import attribution  # noqa: E402
from tests._record import record_at  # noqa: E402


def axis(aid, pid, **kw):
    p = {"id": pid, "lb": 0.0, "ub": 1.0, "nominal_value": 0.1, "estimate": True}
    p.update(kw)
    return {
        "id": aid,
        "on_antimony_patch": {"append": f"R9: A -> Z; {pid}*A"},
        "adds_parameters": [p],
    }


def main() -> int:
    fixture = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
    if not (fixture / "problem.yaml").exists():
        check("the static PEtab fixture is present", False, f"missing {fixture}")
        return 1

    # the fixture is a PEtab problem ON DISK, an input: read it as one
    inp = petab_io.from_dir(fixture)
    par = inp.parameters
    nominal = {str(r.parameterId): float(r.nominalValue) for r in par.itertuples()}
    target = str(par[par.estimate == 1].parameterId.iloc[0])

    cache: dict = {}
    # two points: the nominal one, and one with a dynamic parameter moved
    rival_point = dict(nominal)
    rival_point[target] = float(nominal[target]) * 1.6
    evals = {
        "winner": attribution.evaluate_at_mle(
            inp, {"best_x_unscaled": nominal, "best_fval": float("nan")}, cache
        ),
        "rival": attribution.evaluate_at_mle(
            inp,
            {"best_x_unscaled": rival_point, "best_fval": float("nan")},
            cache,
        ),
    }

    # 1 ---- the split is EXACT against AMICI's own likelihood --------------
    for cid, ev in evals.items():
        check(
            f"{cid}: evaluated, and the split matches AMICI's own likelihood",
            ev.get("available") and ev.get("split_exact"),
            f"available={ev.get('available')} mismatch="
            f"{ev.get('split_mismatch', float('nan')):.3e} "
            f"worst-condition={ev.get('worst_condition_mismatch', float('nan')):.3e}"
            + (f" why={ev.get('why')}" if not ev.get("available") else ""),
        )
    check(
        "the two points really do differ, so the checks are not vacuous",
        abs(evals["winner"]["total"] - evals["rival"]["total"]) > 1.0,
        f"Δnllh {evals['rival']['total'] - evals['winner']['total']:+.4f}",
    )
    check(
        "every measured group carries its points, sigmas and contributions",
        all(
            g["n"] == len(g["times"]) == len(g["sigma"]) == len(g["point_nllh"])
            for g in evals["winner"]["groups"].values()
        )
        and len(evals["winner"]["groups"]) > 0,
        f"{len(evals['winner']['groups'])} group(s)",
    )

    # 2 ---- the decomposition adds up -------------------------------------
    dec = attribution.decompose("winner", evals, {"winner": 4, "rival": 3})
    check("the decomposition is available", dec.get("available"), dec.get("why", ""))
    riv = (dec.get("rivals") or [{}])[0]
    contributions = sum(c["delta_aic_units"] for c in riv.get("contributions") or [])
    check(
        "the per-group contributions sum to the LIKELIHOOD half of the ΔAIC",
        abs(contributions - riv["likelihood_units"]) < 1e-9,
        f"{contributions:+.9f} vs {riv['likelihood_units']:+.9f}",
    )
    check(
        "likelihood half + parameter half = the whole ΔAIC",
        abs(riv["likelihood_units"] + riv["parameter_units"] - riv["delta_aic"]) < 1e-9,
        f"{riv['likelihood_units']:+.4f} + {riv['parameter_units']:+.4f} "
        f"= {riv['delta_aic']:+.4f}",
    )
    # the winner has 4 parameters, the rival 3:
    # ΔAIC(rival − winner) = 2·Δnllh + 2·(k_rival − k_winner) = 2·Δnllh − 2,
    # so the parameter half is NEGATIVE here
    check(
        "the parameter half is 2*(k_rival - k_winner): the winner PAYS for "
        "its extra parameter",
        abs(riv["parameter_units"] - (-2.0)) < 1e-12,
        f"{riv['parameter_units']}",
    )
    # …and the split equals the discrimination table, computed independently
    aic_w = 2 * 4 + 2 * evals["winner"]["total"]
    aic_r = 2 * 3 + 2 * evals["rival"]["total"]
    table = {"winner": aic_w - min(aic_w, aic_r), "rival": aic_r - min(aic_w, aic_r)}
    check(
        "the split's ΔAIC IS the table's ΔAIC (rival minus winner)",
        abs(riv["delta_aic"] - (table["rival"] - table["winner"])) < 1e-9,
        f"split {riv['delta_aic']:+.4f} vs table {table['rival'] - table['winner']:+.4f}",
    )
    dec_t = attribution.decompose(
        "winner", evals, {"winner": 4, "rival": 3}, table_delta_aic=table
    )
    riv_t = dec_t["rivals"][0]
    check(
        "handed the table, the decomposition reconciles against it and reports agreement",
        riv_t.get("matches_table") is True
        and dec_t["reconciliation"]["table_checked"] is True
        and dec_t["reconciliation"]["table_mismatches"] == [],
        f"{riv_t.get('matches_table')} {dec_t['reconciliation'].get('table_mismatches')}",
    )
    dec_bad = attribution.decompose(
        "winner",
        evals,
        {"winner": 4, "rival": 3},
        table_delta_aic={"winner": 0.0, "rival": table["rival"] + 12.0},
    )
    check(
        "a table that disagrees is NAMED as a mismatch, never shown as agreement",
        dec_bad["reconciliation"]["table_mismatches"] == ["rival"],
        str(dec_bad["reconciliation"]["table_mismatches"]),
    )
    # a candidate with no finite optimum has an empty best vector: nothing to
    # decompose, and no KeyError either
    dead = attribution.evaluate_at_mle(
        inp, {"best_fval": float("inf"), "best_x_unscaled": {}}, cache
    )
    check(
        "a rival whose every start failed is refused with 'no finite optimum', not a KeyError",
        not dead.get("available")
        and "no finite optimum" in dead.get("why", "")
        and "estimation_convergence" in dead.get("why", ""),
        str(dead.get("why"))[:120],
    )
    check(
        "shares are normalised over the absolute contributions",
        abs(sum(c["share"] for c in riv["contributions"]) - 1.0) < 1e-3,
        f"{sum(c['share'] for c in riv['contributions']):.4f}",
    )
    check(
        "contributions are ordered by how much they explain",
        [abs(c["delta_nllh"]) for c in riv["contributions"]]
        == sorted((abs(c["delta_nllh"]) for c in riv["contributions"]), reverse=True),
    )

    # 3 ---- per-timepoint detail ------------------------------------------
    g = riv["contributions"][0]["group"]
    pts = attribution.per_timepoint(evals["winner"], evals["rival"], g)
    check(
        "per-timepoint detail is capped and ordered by what it explains",
        0 < len(pts) <= attribution.TOP_POINTS
        and [abs(x["delta_nllh"]) for x in pts]
        == sorted((abs(x["delta_nllh"]) for x in pts), reverse=True),
        f"{len(pts)} point(s)",
    )
    check(
        "and carries both models' simulated values beside the measurement",
        all(
            {"time", "measured", "winner_sim", "rival_sim", "delta_nllh"} <= set(x)
            for x in pts
        ),
    )

    # 4 ---- when the split is NOT exact, nothing is shown -----------------
    broken = {
        "winner": {**evals["winner"], "split_exact": False, "split_mismatch": 0.4},
        "rival": evals["rival"],
    }
    ref = attribution.decompose("winner", broken, {"winner": 4, "rival": 3})
    check(
        "a non-exact split refuses the whole decomposition, naming the mismatch",
        not ref.get("available") and "4.000e-01" in str(ref.get("why", "")),
        str(ref.get("why", ""))[:130],
    )
    partial = {
        "winner": evals["winner"],
        "rival": evals["rival"],
        "crashed": {"available": False, "why": "simulation failed"},
    }
    ref2 = attribution.decompose(
        "winner", partial, {"winner": 4, "rival": 3, "crashed": 3}
    )
    bad = next(r for r in ref2["rivals"] if r["rival"] == "crashed")
    check(
        "a rival that could not be evaluated is NAMED, not dropped",
        ref2["available"]
        and len(ref2["rivals"]) == 2
        and not bad["available"]
        and "simulation failed" in bad["why"],
        f"{bad}",
    )

    # 5 ---- neutralisation: what it will and will not touch ---------------
    good = axis("alt_route", "k_alt", neutral_value=0.0)
    no_decl = axis("mystery", "k_myst")
    logscale = axis("logged", "k_log", lb=1e-5, neutral_value=0.0)
    mech = attribution.mechanism_parameters(
        [good, no_decl, logscale],
        ["alt_route", "mystery", "logged"],
        {},
    )
    check(
        "a log10-scaled parameter with an off-state of 0 is usable",
        "k_log" in mech["usable"],
        f"usable: {sorted(mech['usable'])}",
    )
    check(
        "a usable declaration is usable",
        "k_alt" in mech["usable"] and mech["usable"]["k_alt"]["neutral_value"] == 0.0,
        f"{sorted(mech['usable'])}",
    )
    check(
        "an axis with no declaration is refused, naming the field",
        "no neutral_value" in mech["refused"].get("mystery", ""),
        mech["refused"].get("mystery", ""),
    )

    check(
        "an axis the winner does not carry is not considered at all",
        not attribution.mechanism_parameters([good], [], {})["usable"],
    )

    # the simulation check of the neutral declaration is consulted, both ways
    verified = {"verification": {"per_axis": {"alt_route": {"neutralizes": True}}}}
    mech_ok = attribution.mechanism_parameters([good], ["alt_route"], verified)
    check(
        "a declaration the simulation check verified is marked as verified",
        mech_ok["usable"]["k_alt"]["verified_by_simulation"] is True,
    )
    disproved = {
        "verification": {
            "per_axis": {
                "alt_route": {
                    "neutralizes": False,
                    "why": "A: worst relative difference 6.3e-01",
                }
            }
        }
    }
    mech_no = attribution.mechanism_parameters([good], ["alt_route"], disproved)
    check(
        "a declaration the simulation check DISPROVED is refused, for that reason",
        not mech_no["usable"]
        and "shown NOT to neutralize" in mech_no["refused"].get("alt_route", ""),
        mech_no["refused"].get("alt_route", "")[:130],
    )

    # overriding a log10-scaled parameter to exactly 0 works: -inf in the
    # scaled vector unscales back to 0 before AMICI sees it
    scaled_off = attribution.evaluate_at_mle(
        inp,
        {"best_x_unscaled": nominal, "best_fval": float("nan")},
        cache,
        overrides={target: 0.0},
    )
    check(
        "a log10-scaled parameter can be switched off at exactly 0",
        scaled_off.get("available")
        and scaled_off.get("split_exact")
        and abs(scaled_off["total"] - evals["winner"]["total"]) > 1.0,
        f"available={scaled_off.get('available')} "
        f"nllh {scaled_off.get('total')} vs {evals['winner']['total']} "
        f"({scaled_off.get('why', '')})",
    )
    unknown = attribution.evaluate_at_mle(
        inp,
        {"best_x_unscaled": nominal, "best_fval": float("nan")},
        cache,
        overrides={"not_a_parameter": 1.0},
    )
    check(
        "an override naming an unknown parameter is refused",
        not unknown.get("available") and "unknown parameter" in unknown.get("why", ""),
        unknown.get("why", ""),
    )

    # 6 ---- compact() keeps what is read and drops what is not ------------
    neut = {"parameters": {}, "refused": mech["refused"], "note": "nothing usable"}
    comp = attribution.compact(dec, neut, evals, "winner")
    blob = json.dumps(comp)
    check(
        "the compact record drops the per-point arrays",
        "point_nllh" not in blob and "sigma" not in blob,
        f"{len(blob)} chars against "
        f"{len(json.dumps({'d': dec, 'e': evals}))} for the full record",
    )
    check(
        "but keeps the per-group split and the worst group's points",
        comp["rivals"][0].get("contributions")
        and comp["rivals"][0].get("worst_group_detail", {}).get("points"),
    )
    check(
        "and names where the full record lives",
        comp.get("full_record") == "attribution",
    )
    check(
        "the reconciliation travels with it",
        (comp.get("reconciliation") or {}).get("split_tolerance")
        == attribution.SPLIT_TOL,
    )

    # 7 ---- the prose a human and the interpreter read --------------------
    lines = attribution.card_lines(comp, neut)
    check(
        "the card names the ΔAIC, both halves, and where it was paid",
        any("ΔAIC" in ln and "likelihood" in ln and "paid at" in ln for ln in lines),
        lines[0] if lines else "(no lines)",
    )
    check(
        "and says which axes were not neutralised, and why",
        any("not neutralised" in ln for ln in lines),
        f"{[ln for ln in lines if 'not neutralised' in ln][:1]}",
    )
    check(
        "an unavailable decomposition produces one honest line, not silence",
        attribution.card_lines({"available": False, "why": "nope"})
        == ["mechanism attribution unavailable: nope"],
    )

    # 8 ---- what a diagnostic swallows is recorded ------------------------
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import RunContext
    from octomod.spec import WorkflowSpec
    from octomod.workflow_modules.evaluation.engine import _md_attribution

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = record_at(tmp / "run")  # the run is one record file
        ctx = RunContext(
            root=root,
            testcase_dir=tmp,
            spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
            ledger=Ledger(root),
            backend="stub",
            auto=True,
        )
        out = _md_attribution(ctx, [{"id": "M_nope", "n_est": 3}], "M_nope")
        check(
            "a candidate that cannot be evaluated does not kill the round",
            out.get("available") is False and out.get("why"),
            str(out.get("why"))[:90],
        )
        swallowed = [e for e in ctx.ledger.entries() if e.get("swallowed")]
        check(
            "and the exception it absorbed is in the ledger, not only in the "
            "return value — an absence with no cause is the defect nobody "
            "notices",
            len(swallowed) == 1
            and "candidate M_nope not evaluated" in swallowed[0]["note"]
            and "RecordMissing" in swallowed[0]["note"],
            (swallowed[0]["note"][:120] if swallowed else "no swallowed row"),
        )

    print()
    return finish(
        "ATTRIBUTION",
        "ATTRIBUTION OK — the split adds up, and refuses to be shown when it cannot",
    )


if __name__ == "__main__":
    raise SystemExit(main())
