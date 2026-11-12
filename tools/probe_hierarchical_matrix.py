"""Probe which inner-optimisation cells the pinned pyPESTO supports, and how it fails.

Each cell (inner set x noise x scale) is fitted plainly, then the hierarchical objective
is compared at the plain optimum: a supported cell must agree, an unsupported one raise.
Writes docs/hierarchical_matrix.json; --out splices the table into its marker block.

    uv run python tools/probe_hierarchical_matrix.py [--out docs/MODULARITY.md]
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# truth for the synthetic problem
K_TRUE, A0, SCALE_TRUE, OFFSET_TRUE, SIGMA_TRUE = 0.35, 8.0, 2.5, 1.0, 0.3
TIMES = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
N_STARTS = 8
NLLH_TOL = 1e-2  # objective agreement between the two paths
MARK_BEGIN = "<!-- HIERARCHICAL-PROBE-BEGIN -->"
MARK_END = "<!-- HIERARCHICAL-PROBE-END -->"

SBML_ANT = """model decay
  compartment cell = 1;
  species A in cell = 8;
  k1 = 0.35;
  J1: A -> ; k1 * A;
end
"""


def _sbml(path: Path) -> None:
    import antimony

    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(SBML_ANT) >= 0, antimony.getLastError()
    path.write_text(antimony.getSBMLString(antimony.getMainModuleName()))


def write_problem(d: Path, inner_types, distribution: str, scale: str) -> Path:
    """A PEtab problem whose scaling, offset and sigma are inner-eligible, with
    the members of `inner_types` marked `parameterType` (a set: pyPESTO couples
    scaling with offset, and the assembly creates all three together)."""
    d.mkdir(parents=True, exist_ok=True)
    _sbml(d / "model.xml")
    rng = np.random.default_rng(20260907)
    rows = []
    for cond, a0 in (("c1", A0), ("c2", A0 * 0.5)):
        for t in TIMES:
            for _rep in (1, 2):
                truth = SCALE_TRUE * (a0 * np.exp(-K_TRUE * t)) + OFFSET_TRUE
                rows.append(
                    {
                        "observableId": "obs_A",
                        "simulationConditionId": cond,
                        "time": t,
                        "measurement": float(truth + rng.normal(0, SIGMA_TRUE)),
                        "observableParameters": "sc_obs;off_obs",
                        "noiseParameters": "sigma_obs",
                    }
                )
    pd.DataFrame(rows).to_csv(d / "measurements.tsv", sep="\t", index=False)
    pd.DataFrame(
        [{"conditionId": "c1", "A": A0}, {"conditionId": "c2", "A": A0 * 0.5}]
    ).to_csv(d / "conditions.tsv", sep="\t", index=False)
    # the canonical hierarchical encoding: inner parameters enter through
    # placeholders, not baked into the formula
    pd.DataFrame(
        [
            {
                "observableId": "obs_A",
                "observableFormula": "observableParameter1_obs_A * A + observableParameter2_obs_A",
                "observableTransformation": "lin",
                "noiseFormula": "noiseParameter1_obs_A",
                "noiseDistribution": distribution,
            }
        ]
    ).to_csv(d / "observables.tsv", sep="\t", index=False)

    inner_ids = {"scaling": "sc_obs", "offset": "off_obs", "sigma": "sigma_obs"}
    wanted = {
        inner_ids[t]: t
        for t in ([inner_types] if isinstance(inner_types, str) else inner_types)
    }
    par = [
        {
            "parameterId": "k1",
            "parameterScale": "log10",
            "lowerBound": 1e-3,
            "upperBound": 1e2,
            "nominalValue": K_TRUE,
            "estimate": 1,
            "parameterType": "",
        },
        {
            "parameterId": "sc_obs",
            "parameterScale": "lin",
            "lowerBound": 1e-3,
            "upperBound": 1e3,
            "nominalValue": SCALE_TRUE,
            "estimate": 1,
            "parameterType": "",
        },
        {
            "parameterId": "off_obs",
            "parameterScale": "lin",
            "lowerBound": -1e2,
            "upperBound": 1e2,
            "nominalValue": OFFSET_TRUE,
            "estimate": 1,
            "parameterType": "",
        },
        {
            "parameterId": "sigma_obs",
            "parameterScale": "lin",
            "lowerBound": 1e-3,
            "upperBound": 1e2,
            "nominalValue": SIGMA_TRUE,
            "estimate": 1,
            "parameterType": "",
        },
    ]
    for row in par:
        if row["parameterId"] in wanted:
            kind = wanted[row["parameterId"]]
            row["parameterType"] = kind
            # an offset spanning zero has no log scale; PEtab rejects the
            # problem before pyPESTO sees it, so the cell is not expressible
            row["parameterScale"] = "lin" if kind == "offset" else scale
            # The table keeps finite bounds for the plain reference (an infinite
            # range has no startpoint distribution); the hierarchical build
            # applies pyPESTO's own `correct_parameter_df_bounds`.
    pd.DataFrame(par).to_csv(d / "parameters.tsv", sep="\t", index=False)
    import yaml

    yaml_path = d / "problem.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "format_version": 1,
                "parameter_file": "parameters.tsv",
                "problems": [
                    {
                        "sbml_files": ["model.xml"],
                        "condition_files": ["conditions.tsv"],
                        "measurement_files": ["measurements.tsv"],
                        "observable_files": ["observables.tsv"],
                    }
                ],
            }
        )
    )
    return yaml_path


def build(yaml_path: Path, hierarchical: bool, out_dir: Path):
    """A pypesto Problem for one encoding."""
    import os

    import petab.v1 as petab
    from pypesto.petab import PetabImporter

    from octomod.config import SWIG_BIN

    # A model module must be wrapped by the SAME swig that built this venv's
    # AMICI core, or it fails at LOAD time with a misleading AttributeError on
    # a SwigPyObject. Any code that compiles AMICI outside
    # estimation.build_problem sets this itself.
    os.environ["SWIG"] = str(SWIG_BIN)
    problem = petab.Problem.from_yaml(str(yaml_path))
    if hierarchical:
        from pypesto.hierarchical.petab import correct_parameter_df_bounds

        # pyPESTO's own corrector puts inner parameters on the bounds it
        # mandates; the plain reference keeps the finite ones in the table
        problem.parameter_df = correct_parameter_df_bounds(problem.parameter_df)
    importer = PetabImporter(
        problem,
        output_folder=str(out_dir),
        model_name=f"m_{out_dir.name}",
        validate_petab=False,
        hierarchical=hierarchical,
    )
    return importer.create_problem()


def minimise(prob) -> tuple[float, dict]:
    """(best objective, {name: scaled value}) of a small seeded multistart."""
    import logging

    import pypesto.optimize

    np.random.seed(7)
    res = pypesto.optimize.minimize(
        problem=prob,
        optimizer=pypesto.optimize.FidesOptimizer(verbose=logging.ERROR),
        n_starts=N_STARTS,
        engine=pypesto.engine.SingleCoreEngine(),
        progress_bar=False,
        filename=None,
    )
    best = None
    for o in res.optimize_result.list:
        if (
            o.fval is not None
            and np.isfinite(o.fval)
            and (best is None or o.fval < best.fval)
        ):
            best = o
    if best is None:
        raise RuntimeError("no start converged to a finite objective")
    x = np.asarray(best.x, dtype=float)
    names = list(prob.x_names)
    return float(best.fval), {names[i]: float(x[i]) for i in range(len(names))}


def fit(yaml_path: Path, hierarchical: bool, out_dir: Path) -> float:
    """Best objective of a small seeded multistart, or raise."""
    import logging
    import os

    import petab.v1 as petab
    import pypesto.optimize
    from pypesto.petab import PetabImporter

    from octomod.config import SWIG_BIN

    # A model module must be wrapped by the SAME swig that built this venv's
    # AMICI core, or it fails at LOAD time with a misleading AttributeError on
    # a SwigPyObject. Any code that compiles AMICI outside
    # estimation.build_problem has to set this itself.
    os.environ["SWIG"] = str(SWIG_BIN)
    problem = petab.Problem.from_yaml(str(yaml_path))
    importer = PetabImporter(
        problem,
        output_folder=str(out_dir),
        model_name=f"m_{out_dir.name}",
        validate_petab=False,
        hierarchical=hierarchical,
    )
    prob = importer.create_problem()
    np.random.seed(7)
    res = pypesto.optimize.minimize(
        problem=prob,
        optimizer=pypesto.optimize.FidesOptimizer(verbose=logging.ERROR),
        n_starts=N_STARTS,
        engine=pypesto.engine.SingleCoreEngine(),
        progress_bar=False,
        filename=None,
    )
    fvals = [
        o.fval
        for o in res.optimize_result.list
        if o.fval is not None and np.isfinite(o.fval)
    ]
    if not fvals:
        raise RuntimeError("no start converged to a finite objective")
    return float(min(fvals))


SUPPORTED_NOISE = ("normal",)
SUPPORTED_SCALE = ("lin",)


def expectation(inner_types, distribution: str, scale: str) -> tuple[bool, str]:
    """(supported, why) from the DOCUMENTED contract, before anything is run."""
    kinds = set(inner_types)
    if distribution not in SUPPORTED_NOISE:
        return False, f"{distribution} noise is not supported (Gaussian only)"
    if scale not in SUPPORTED_SCALE and kinds - {"offset"}:
        return False, f"{scale}-scaled inner parameters are not supported"
    if ("scaling" in kinds) != ("offset" in kinds):
        return False, (
            "scaling and offset must be marked inner together; one of "
            "a pair inner and the other an ordinary estimated "
            "observableParameter is not a supported configuration"
        )
    return True, "documented as supported"


def classify(inner_types, distribution: str, scale: str, tmp: Path) -> dict:
    label = "+".join(inner_types) if not isinstance(inner_types, str) else inner_types
    d = tmp / f"{label.replace('+', '_')}_{distribution}_{scale}"
    supported, why = expectation(inner_types, distribution, scale)
    cell = {
        "parameterType": label,
        "noiseDistribution": distribution,
        "parameterScale": scale,
        "expected": "supported" if supported else "unsupported",
        "expectation_reason": why,
    }
    yaml_path = write_problem(d, inner_types, distribution, scale)
    try:
        plain = build(yaml_path, False, d / "amici_plain")
        f_plain, x_plain = minimise(plain)
    except Exception as e:  # noqa: BLE001 — the plain path is the reference
        cell.update(
            verdict="reference failed",
            detail=f"the PLAIN fit failed, so "
            f"this cell says nothing about hierarchical: "
            f"{type(e).__name__}: {' '.join(str(e).split())[:140]}",
        )
        return cell
    cell["plain_nllh"] = round(f_plain, 4)
    try:
        hier = build(yaml_path, True, d / "amici_hier")
    except Exception as e:  # noqa: BLE001
        msg = " ".join(f"{type(e).__name__}: {e}".split())[:200]
        cell.update(
            verdict="raises (safe)" if not supported else "raises",
            detail=(
                f"refuses loudly, as an unsupported cell should: {msg}"
                if not supported
                else msg
            ),
        )
        return cell

    # the exact identity: is it even the same function at the same point?
    try:
        free = [str(hier.x_names[i]) for i in hier.x_free_indices]
        f_hier_at_plain = float(
            hier.objective(np.array([x_plain[n] for n in free], dtype=float))
        )
    except Exception as e:  # noqa: BLE001
        cell.update(
            verdict="objectives disagree",
            detail=f"could not evaluate at the plain optimum: "
            f"{type(e).__name__}: {e}",
        )
        return cell
    cell["hier_at_plain_optimum"] = round(f_hier_at_plain, 4)
    same_function = abs(f_hier_at_plain - f_plain) <= NLLH_TOL

    if not supported:
        # the outcome the engine cannot defend against: no error, and a number
        # that is not the likelihood the problem declared
        cell.update(
            verdict="SILENTLY WRONG" if not same_function else "works anyway",
            detail=(
                f"accepted an unsupported cell without raising, and at the "
                f"plain optimum its objective reads {f_hier_at_plain:.4f} "
                f"where the declared likelihood reads {f_plain:.4f} — it is "
                f"computing a different likelihood and saying nothing"
                if not same_function
                else "accepted without raising and agrees with the declared "
                "likelihood at the plain optimum; undocumented but not "
                "observably wrong here"
            ),
        )
        return cell
    if not same_function:
        cell.update(
            verdict="objectives disagree",
            detail=(
                f"a SUPPORTED cell whose objective reads "
                f"{f_hier_at_plain:.4f} at the plain optimum where the "
                f"plain one reads {f_plain:.4f} — not the same function "
                f"at the same point"
            ),
        )
        return cell
    try:
        f_hier, _x = minimise(hier)
    except Exception as e:  # noqa: BLE001
        cell.update(
            verdict="raises", detail=" ".join(f"{type(e).__name__}: {e}".split())[:200]
        )
        return cell
    cell["hier_nllh"] = round(f_hier, 4)
    cell["delta"] = round(f_hier - f_plain, 4)
    if abs(f_hier - f_plain) <= NLLH_TOL:
        cell.update(verdict="works", detail="same function, same optimum")
    elif f_hier < f_plain - NLLH_TOL:
        cell.update(
            verdict="works",
            detail=f"same function; hierarchical reached a "
            f"BETTER optimum by {f_plain - f_hier:.3f}",
        )
    else:
        cell.update(
            verdict="SILENTLY WRONG",
            detail=f"right function, but the fit lands {f_hier - f_plain:.3f} "
            f"above the plain optimum without raising",
        )
    return cell


def render(cells: list[dict]) -> str:
    import importlib.metadata as md

    ver = md.version("pypesto")
    lines = [
        f"**Measured on pypesto {ver} (this venv), "
        f"`tools/probe_hierarchical_matrix.py`.** The `expected` column is the "
        f"DOCUMENTED contract, fixed before anything ran; the verdict is what the "
        f"installed library did. Each cell fits a one-species synthetic problem "
        f"plainly, then checks an exact identity — at the plain optimum the "
        f"hierarchical objective must read the same number, since it re-solves "
        f"inner parameters that are already optimal there — and only then compares "
        f"the two optima ({N_STARTS} seeded starts, tolerance {NLLH_TOL}). "
        f"`raises (safe)` is the RIGHT outcome for an unsupported cell. "
        f"**`SILENTLY WRONG` is the only outcome the engine cannot defend against**: no "
        f"error, and a number that is not the likelihood the problem declared.",
        "",
        "| inner set | noise | scale | expected | verdict | plain −logL | hier @ plain opt | detail |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        lines.append(
            f"| {c['parameterType']} | {c['noiseDistribution']} | "
            f"{c['parameterScale']} | {c['expected']} | **{c['verdict']}** | "
            f"{c.get('plain_nllh', '—')} | {c.get('hier_at_plain_optimum', '—')} | "
            f"{c.get('detail', '')} |"
        )
    sup = [c for c in cells if c["expected"] == "supported"]
    sup_ok = [c for c in sup if c["verdict"] == "works"]
    bad = [c for c in cells if c["verdict"] == "SILENTLY WRONG"]
    safe = [c for c in cells if c["verdict"] == "raises (safe)"]
    lines += [
        "",
        f"**{len(sup_ok)} of {len(sup)} documented-supported cells verified.** "
        f"{len(safe)} unsupported cell(s) refused loudly, which is the correct "
        f"behaviour. "
        + (
            f"**{len(bad)} cell(s) came back SILENTLY WRONG** — accepted without "
            f"raising while computing a different likelihood: "
            f"{sorted({(c['parameterType'], c['noiseDistribution'], c['parameterScale']) for c in bad})}. "
            f"The ENGINE must refuse these, since the library will not."
            if bad
            else "No silently-wrong cell found."
        ),
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="markdown file with the HIERARCHICAL-PROBE markers to splice into",
    )
    ap.add_argument("--keep", action="store_true", help="keep the temp problems")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="hier_probe_"))
    cells = []
    # The sets the engine can emit, plus one-at-a-time cells: pyPESTO couples a
    # scaling with its offset, so marking one of the pair inner is unsupported,
    # and the matrix shows it.
    GRID = [
        ("sigma",),
        ("scaling", "offset"),
        ("scaling", "offset", "sigma"),
        ("scaling",),
        ("offset",),
    ]
    try:
        for inner, dist, scale in itertools.product(
            GRID, ("normal", "laplace"), ("lin", "log10")
        ):
            print(f"  probing {'+'.join(inner)} × {dist} × {scale} ...", flush=True)
            cell = classify(list(inner), dist, scale, tmp)
            print(
                f"    -> {cell['verdict']}: {cell.get('detail', '')[:110]}", flush=True
            )
            cells.append(cell)
    finally:
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)

    table = render(cells)
    print("\n" + table)
    (REPO / "docs" / "hierarchical_matrix.json").write_text(
        json.dumps(cells, indent=2) + "\n"
    )
    if args.out:
        text = args.out.read_text()
        block = f"{MARK_BEGIN}\n{table}\n{MARK_END}"
        if MARK_BEGIN in text and MARK_END in text:
            head, rest = text.split(MARK_BEGIN, 1)
            _old, tail = rest.split(MARK_END, 1)
            args.out.write_text(head + block + tail)
        else:
            args.out.write_text(
                text.rstrip() + "\n\n### Hierarchical support matrix\n\n" + block + "\n"
            )
        print(f"\nspliced into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
