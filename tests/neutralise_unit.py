"""Switching the winner's mechanism term off at its declared neutral value.

The winner of a discrimination round carries one axis, `alt_route`: a basal
phosphorylation leg `R -> Rp; k_alt*R` on the toy cycle, whose parameter
declares `neutral_value: 0`. A second axis it carries, `mystery`, declares
none. S7's attribution (`_md_attribution`, the caller of
`attribution.neutralise`) is run on that round with the fit replaced by a
recorded point:

  1. `k_alt` is neutralised and `mystery` is refused by name, in the returned
     record, in the round's `attribution` record and on the card;
  2. the term switched off is the model without the leg: the off likelihood
     equals the base cycle's own at the same point;
  3. the record prices it (twice the likelihood difference) and names the
     series that move by more than one sigma, each by its worst shift;
  4. the ledger counts the neutralised term.

    uv run python tests/neutralise_unit.py
"""

from __future__ import annotations

import contextlib
import io
import logging
import math
import shutil
import sys
import tempfile
from pathlib import Path

import libsbml
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check_detail_on_fail, finish  # noqa: E402
from _record import rnd, temp_record, work  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.evaluation import attribution  # noqa: E402
from octomod.workflow_modules.evaluation import engine as S7  # noqa: E402

SOURCE = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
WINNER = "alt_route+mystery"
K_ALT = 0.05  # the leg's value at the recorded point
ALT = {
    "id": "alt_route",
    "kind": "structural",
    "question": "is there a basal phosphorylation route?",
    "on_antimony_patch": [{"append": "J3: R -> Rp; k_alt*R"}],
    "adds_parameters": [
        {
            "id": "k_alt",
            "nominal_value": K_ALT,
            "lb": 1e-4,
            "ub": 1.0,
            "estimate": True,
            "neutral_value": 0.0,
            "denotes": "basal phosphorylation rate",
        }
    ],
}
# carried by the winner, with no value at which its term is known to be off
MYSTERY = {
    "id": "mystery",
    "kind": "structural",
    "on_antimony_patch": [{"append": "J4: Rp -> ; k_myst*Rp"}],
    "adds_parameters": [
        {"id": "k_myst", "nominal_value": 0.0, "lb": 0, "ub": 1, "estimate": False}
    ],
}


def _winner_petab(dest: Path) -> Path:
    """The toy cycle's problem with the basal leg added and `k_alt` estimated."""
    shutil.copytree(SOURCE, dest)
    doc = libsbml.readSBMLFromString((dest / "model.xml").read_text())
    model = doc.getModel()
    k = model.createParameter()
    k.setId("k_alt")
    k.setValue(K_ALT)
    k.setConstant(True)
    rxn = model.createReaction()
    rxn.setId("J3")
    rxn.setReversible(False)
    sub = rxn.createReactant()
    sub.setSpecies("R")
    sub.setStoichiometry(1.0)
    sub.setConstant(True)
    prod = rxn.createProduct()
    prod.setSpecies("Rp")
    prod.setStoichiometry(1.0)
    prod.setConstant(True)
    rxn.createKineticLaw().setMath(libsbml.parseL3Formula("k_alt * R"))
    (dest / "model.xml").write_text(libsbml.writeSBMLToString(doc))
    par = pd.read_csv(dest / "parameters.tsv", sep="\t")
    par = pd.concat(
        [
            par,
            pd.DataFrame(
                [
                    {
                        "parameterId": "k_alt",
                        "parameterScale": "log10",
                        "lowerBound": 1e-4,
                        "upperBound": 1.0,
                        "nominalValue": K_ALT,
                        "estimate": 1,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    par.to_csv(dest / "parameters.tsv", sep="\t", index=False)
    return dest


# a sigma other than 1, so a shift and a shift in sigma units differ
SIGMA = 0.25


def _point(petab_dir: Path) -> dict:
    """The recorded point: the table's nominal values, at the sigma above."""
    par = pd.read_csv(petab_dir / "parameters.tsv", sep="\t")
    point = {str(r.parameterId): float(r.nominalValue) for r in par.itertuples()}
    return {**point, "sigma_obs_pR": SIGMA}


def _stage(root: Path, run) -> tuple[RunContext, Path]:
    """A finished discrimination round whose winner carries both axes.

    The run is the record `run`; the winner's PEtab problem is built as
    files under `root` (an input, as the toy case is) and put into the record."""
    case = root / "input"
    case.mkdir(parents=True)
    (case / "testcase.yaml").write_text("name: neutralise\nt_end: 10\n")
    (run / "intent").put({"question": "is there a basal route?"})
    r0 = rnd(run, 0)
    (r0 / "space/axes").put([ALT, MYSTERY])
    # the construction-module check found the declared value neutralises
    (r0 / "model/encoding").put(
        {"verification": {"per_axis": {"alt_route": {"neutralizes": True}}}}
    )
    cand = work(run, 0, WINNER)
    petab_dir = _winner_petab(root / "winner_petab")
    petab_io.to_record(petab_io.from_dir(petab_dir), cand / "petab")
    (cand / "model/sbml").put_text((petab_dir / "model.xml").read_text())
    (cand / "estimation").put(
        {"best_fval": float("nan"), "best_x_unscaled": _point(petab_dir)}
    )
    ctx = RunContext(
        root=run,
        testcase_dir=case,
        spec=SPEC,
        ledger=Ledger(run),
        backend="stub",
        auto=False,
    )
    return ctx, petab_dir


def main() -> int:
    with tempfile.TemporaryDirectory() as td, temp_record("run") as run:
        ctx, petab_dir = _stage(Path(td), run)
        rows = [{"id": WINNER, "n_est": 5, "delta_aic": 0.0}]
        with contextlib.redirect_stdout(io.StringIO()):
            out = S7._md_attribution(ctx, rows, WINNER)
        on_disk = (ctx.round / "attribution").get(None) or {}
        neut = on_disk.get("neutralisation") or {}
        rec = (neut.get("parameters") or {}).get("k_alt") or {}
        check_detail_on_fail(
            "the winner's two axes are both considered",
            on_disk.get("axes_on") == ["alt_route", "mystery"],
            str(on_disk.get("axes_on")),
        )
        check_detail_on_fail(
            "k_alt is neutralised at its declared value, under its axis, as verified",
            rec.get("available") is True
            and rec.get("axis") == "alt_route"
            and rec.get("neutral_value") == 0.0
            and rec.get("denotes") == "basal phosphorylation rate"
            and rec.get("verified_by_simulation") is True,
            str({k: v for k, v in rec.items() if k != "series"})[:300],
        )
        check_detail_on_fail(
            "the axis with no neutral value is refused by name, and nothing of it "
            "is simulated",
            "no neutral_value" in str((neut.get("refused") or {}).get("mystery"))
            and set(neut.get("parameters") or {}) == {"k_alt"},
            str(neut.get("refused")),
        )

        # the term off is the model without it: the base cycle at the same point
        cache: dict = {}
        base = attribution.evaluate_at_mle(
            petab_io.from_dir(SOURCE),
            {"best_x_unscaled": _point(SOURCE), "best_fval": float("nan")},
            cache,
        )
        off, on = rec.get("nllh_off"), rec.get("nllh_on")
        check_detail_on_fail(
            "switched off, the winner's likelihood is the base cycle's own",
            base.get("available")
            and off is not None
            and math.isclose(off, base["total"], rel_tol=1e-6, abs_tol=1e-6),
            f"off {off} · base {base.get('total')}",
        )
        winner_eval = (on_disk.get("per_candidate") or {}).get(WINNER) or {}
        check_detail_on_fail(
            "switched on, it is the winner's evaluation at its recorded point, and "
            "the leg matters there",
            on is not None
            and on == winner_eval.get("total")
            and off is not None
            and abs(off - on) > 1.0,
            f"on {on} · off {off}",
        )
        check_detail_on_fail(
            "the cost of switching it off is twice the likelihood difference",
            off is not None
            and on is not None
            and math.isclose(
                rec.get("cost_of_switching_off_aic_units", float("nan")),
                2 * (off - on),
                rel_tol=1e-12,
            ),
            str(rec.get("cost_of_switching_off_aic_units")),
        )
        series = rec.get("series") or []
        groups = sorted((winner_eval.get("groups") or {}).keys())
        worst = [s.get("worst_shift_in_sigma", 0.0) for s in series]
        check_detail_on_fail(
            "every measured series is reported, worst shift first, in sigma units",
            sorted(s.get("group") for s in series) == groups
            and len(groups) == 3
            and worst == sorted(worst, reverse=True)
            and all(
                s["mean_shift_in_sigma"] <= s["worst_shift_in_sigma"] for s in series
            ),
            str(
                [
                    (s.get("group"), round(s.get("worst_shift_in_sigma", 0), 3))
                    for s in series
                ]
            ),
        )
        # the shift of one series recomputed here, from the winner's own
        # evaluation with the leg off, in units of that series' sigma
        by_hand = attribution.evaluate_at_mle(
            petab_io.from_dir(petab_dir),
            {"best_x_unscaled": _point(petab_dir), "best_fval": float("nan")},
            cache,
            overrides={"k_alt": 0.0},
        )
        top = series[0]["group"] if series else ""
        g_on = (winner_eval.get("groups") or {}).get(top) or {}
        g_off = (by_hand.get("groups") or {}).get(top) or {}
        expect = (
            max(
                abs(a - b) / s
                for a, b, s in zip(
                    g_off["simulated"], g_on["simulated"], g_on["sigma"], strict=True
                )
            )
            if g_on and g_off
            else None
        )
        check_detail_on_fail(
            "the worst shift is the largest |off - on| over the series' own sigma",
            expect is not None
            and math.isclose(series[0]["worst_shift_in_sigma"], expect, rel_tol=1e-9),
            f"{top}: {series[0]['worst_shift_in_sigma'] if series else None} vs {expect}",
        )
        check_detail_on_fail(
            "the series that move are those shifted by at least one sigma",
            rec.get("series_that_move")
            == [s["group"] for s in series if s["worst_shift_in_sigma"] >= 1.0]
            and len(rec.get("series_that_move") or []) >= 1,
            str(rec.get("series_that_move")),
        )
        compact = ((out or {}).get("neutralisation") or {}).get("parameters") or {}
        card = attribution.card_lines({"available": True, "rivals": []}, neut)
        check_detail_on_fail(
            "the report's compact record and the card carry it, and the refusal",
            compact.get("k_alt", {}).get("series_that_move")
            == rec.get("series_that_move")
            and any(
                ln.startswith("switching k_alt off (axis alt_route, neutral 0)")
                for ln in card
            )
            and any(ln.startswith("axis mystery not neutralised") for ln in card),
            str(card),
        )
        notes = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "note"
            and str(e.get("note", "")).startswith("mechanism attribution:")
        ]
        check_detail_on_fail(
            "the ledger counts one neutralised term",
            len(notes) == 1 and "1 term(s) neutralised" in str(notes[0].get("note")),
            str([n.get("note") for n in notes]),
        )
    return finish(
        "\nNEUTRALISE",
        "\nNEUTRALISE UNIT OK — the winner's term is switched off at its declared "
        "neutral value, equals the model without it, and is priced and located "
        "per series; an undeclared one is refused",
    )


if __name__ == "__main__":
    sys.exit(main())
