"""The fit grid's shading is what its caption says it is.

  1. one caption constant names both layers (parameter uncertainty, observation noise);
  2. the figure carries it with and without confidence regions;
  3. with confidence regions the rendered SVG also draws the ±1.96σ noise band;
  4. the figures' z is the shipped spec's gates.predictive_z (the held-out check's);
  5. too few profile points to fit an ellipsoid: the region is the skeleton
     alone, no samples are drawn, acceptance is None, and the report flags the
     band as undersampled.

    uv run python tests/fit_band_unit.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check, finish  # noqa: E402

from octomod.gates.petab_gates import PetabTables  # noqa: E402
from octomod.reporting import figures  # noqa: E402

PETAB = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"


def _tables() -> PetabTables:
    return PetabTables(
        observables=pd.read_csv(PETAB / "observables.tsv", sep="\t"),
        conditions=pd.read_csv(PETAB / "conditions.tsv", sep="\t"),
        measurements=pd.read_csv(PETAB / "measurements.tsv", sep="\t"),
        parameters=pd.read_csv(PETAB / "parameters.tsv", sep="\t"),
        sbml=(PETAB / "model.xml").read_text(),
    )


class _Spec:
    """The spec's dotted `get`, every key at its default."""

    def get(self, dotted: str, default=None):
        return default


class _Problem:
    """Two free log10 parameters; the objective counts its calls, since the
    skeleton-only path must draw no samples."""

    x_names = ["k1", "k2"]
    x_free_indices = [0, 1]
    lb_full = [-3.0, -3.0]
    ub_full = [3.0, 3.0]

    def __init__(self) -> None:
        self.calls = 0

    def objective(self, x) -> float:
        self.calls += 1
        return 0.0


class _Tables:
    """One observable, linear in k1: the envelope moves only if a skeleton point
    with k1 away from the best fit is in it."""

    def simulate_observables(self, cond_id, times, param_override):
        return {"obs": np.asarray(times, dtype=float) * float(param_override["k1"])}


def _skeleton_only_band() -> None:
    from types import SimpleNamespace

    from octomod.reporting.round_report import _band_method_note
    from octomod.workflow_modules.evaluation.uncertainty import confidence_region_band

    best_nllh = 10.0
    # one point per profile under the joint threshold (chi2(0.95, 2)/2 ≈ 3.0):
    # two skeleton points, where an ellipsoid over two parameters needs four
    profiles = {
        "_meta": {"x_names": ["k1", "k2"]},
        "k1": {
            "path": {
                "x_unscaled": [10**-0.5, 10**0.2, 10**0.5],
                "nllh": [best_nllh + 9.0, best_nllh + 0.5, best_nllh + 9.0],
                "x_full_scaled": [[-0.5, 0.0], [0.2, 0.0], [0.5, 0.0]],
            }
        },
        "k2": {
            "path": {
                "x_unscaled": [10**-0.5, 10**-0.2, 10**0.5],
                "nllh": [best_nllh + 9.0, best_nllh + 0.5, best_nllh + 9.0],
                "x_full_scaled": [[0.0, -0.5], [0.0, -0.2], [0.0, 0.5]],
            }
        },
    }
    problem = _Problem()
    times = np.linspace(0.0, 4.0, 5)
    try:
        out = confidence_region_band(
            problem,
            _Tables(),
            profiles,
            {"k1": "log10", "k2": "log10"},
            {"k1": 1.0, "k2": 1.0},
            best_nllh,
            {("obs", "c0"): times},
            _Spec(),
            rng_seed=0,
        )
        err = ""
    except Exception as exc:  # the check reports it rather than aborting the suite
        out, err = {}, f"{type(exc).__name__}: {exc}"
    check("too few skeleton points: the band is built, no exception", not err, err)
    if err:
        return
    check(
        "too few skeleton points: no samples drawn, the method says skeleton only",
        problem.calls == 0
        and out.get("n_box_samples") == 0
        and str(out.get("method", "")).startswith("profile skeleton only"),
        f"objective calls {problem.calls}, n_box_samples "
        f"{out.get('n_box_samples')}, method {out.get('method')!r}",
    )
    check(
        "too few skeleton points: acceptance is None at every alpha",
        set(out.get("acceptance", {})) == {"0.95", "0.9"}
        and all(v is None for v in out["acceptance"].values()),
        str(out.get("acceptance")),
    )
    check(
        "too few skeleton points: the region is flagged as undersampled",
        out.get("skeleton_only") is True
        and "undersampled" in str(out.get("skeleton_only_note", ""))
        and "note" not in out,
        str(out.get("skeleton_only_note")),
    )
    band = out.get("bands", {}).get("obs@c0", {})
    hi, best_line = band.get("hi95", []), band.get("best", [])
    check(
        "too few skeleton points: the envelope is traced by the skeleton points",
        out.get("n_kept_skeleton", {}).get("0.95") == 2
        and len(hi) == len(times)
        and hi[-1] > best_line[-1] + 1.0,
        f"n_kept_skeleton {out.get('n_kept_skeleton')}, hi95 end "
        f"{hi[-1] if hi else None} vs best end {best_line[-1] if best_line else None}",
    )
    html = _band_method_note(
        SimpleNamespace(_band_note_shown=False), out, out.get("bands")
    )
    check(
        "the report flags the undersampled region and quotes no acceptance rate",
        "Confidence region undersampled" in html
        and "no rejection samples" in html
        and "acceptance" not in html
        and "None" not in html,
        html[:300],
    )


def main() -> int:
    import yaml

    spec_z = yaml.safe_load((REPO / "workflows" / "default.yaml").read_text())["gates"][
        "predictive_z"
    ]
    check(
        "the figures draw the z the held-out check uses",
        figures.PREDICTIVE_Z == spec_z,
        f"{figures.PREDICTIVE_Z} vs {spec_z}",
    )
    tables = _tables()
    par = pd.read_csv(PETAB / "parameters.tsv", sep="\t")
    best = dict(
        zip(par["parameterId"], par["nominalValue"].astype(float), strict=False)
    )
    meas = pd.read_csv(PETAB / "measurements.tsv", sep="\t")
    df = pd.DataFrame(
        {
            "observable": meas["observableId"],
            "condition": meas["simulationConditionId"],
            "time": meas["time"],
            "value": meas["measurement"],
            "heldout": False,
        }
    )
    df = df[df["condition"] == "dose_1"]  # one panel is enough to count polygons

    check(
        "the caption names both layers: parameter uncertainty and observation noise",
        "parameter uncertainty" in figures.FIT_GRID_CAPTION
        and "observation" in figures.FIT_GRID_CAPTION
        and "1.96" in figures.FIT_GRID_CAPTION,
        figures.FIT_GRID_CAPTION[:120],
    )
    plain = figures.fit_grid_figure(tables, best, [], df, cr_bands=None)
    check(
        "without confidence regions the figure renders and carries the caption",
        "<svg" in plain and "observation" in plain and "1.96" in plain,
        plain[:160] if "<svg" not in plain else "svg rendered",
    )
    # a confidence-region block for the one panel, on its own time grid
    t = np.linspace(0.0, float(df["time"].max()), 25)
    sim = np.asarray(
        tables.simulate_observables("dose_1", t, param_override=best)["obs_pR"]
    )
    cr = {
        "obs_pR@dose_1": {
            "time": t.tolist(),
            "best": sim.tolist(),
            "lo95": (sim - 0.3).tolist(),
            "hi95": (sim + 0.3).tolist(),
            "lo68": (sim - 0.15).tolist(),
            "hi68": (sim + 0.15).tolist(),
        }
    }
    with_cr = figures.fit_grid_figure(tables, best, [], df, cr_bands=cr)
    check(
        "with confidence regions the figure renders and carries the same caption",
        "<svg" in with_cr and "observation" in with_cr,
    )
    # matplotlib writes each fill_between as one PolyCollection group: two
    # envelopes + the noise band = three, against ONE fill in the ensemble
    # branch; counted on the rendered SVG, because the drawing is the claim
    n_plain = plain.count("PolyCollection")
    n_cr = with_cr.count("PolyCollection")
    check(
        "the confidence-region branch draws an extra filled band — the noise",
        n_cr == n_plain + 2,
        f"PolyCollections: plain {n_plain}, with CR {n_cr} (expected +2: two "
        f"envelopes replace one band, plus the noise band)",
    )
    _skeleton_only_band()
    return finish("\nFIT BAND", "\nfit band: the shading is what the caption says")


if __name__ == "__main__":
    sys.exit(main())
