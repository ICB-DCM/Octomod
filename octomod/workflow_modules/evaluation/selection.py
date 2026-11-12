"""Model selection through PEtab Select.

Each fitted candidate becomes a `petab_select.Model` carrying its NLLH, the
candidates compiled from one structure share one model subspace, and the round
is written as a PEtab Select problem (the round's `selection_files`, the
candidates' problems exported from the record to a temporary directory for
the call). petab_select computes the criteria and weights; the engine's own
arithmetic (`model_space.select`) is cross-checked against it on every
selection, and a disagreement fails a gate rather than falling back.
Calibration stays in the engine.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from octomod.orchestration.ledger import sha256_file
from octomod.result import node as tree
from octomod.result.node import Node
from octomod.workflow_modules.assembly import petab_io

TOL = 1e-6


# Criterion comparability: AIC and BIC compare likelihoods over the same data.
# A different `observableTransformation` puts the likelihood over transformed
# data, so either every candidate shares one transformation per observable or
# the change-of-variables term is added and criteria are in measurement space.
_LOG_BASES = {"log": math.e, "log10": 10.0}


def transformations(observables) -> dict[str, str]:
    """{observable id: transformation}, defaulting to `lin` where unset."""
    if "observableTransformation" not in getattr(observables, "columns", []):
        return {str(r["observableId"]): "lin" for _, r in observables.iterrows()}
    out = {}
    for _, row in observables.iterrows():
        value = str(row.get("observableTransformation") or "lin").strip().lower()
        out[str(row["observableId"])] = value or "lin"
    return out


def jacobian_correction(observables, measurements) -> tuple[float, dict]:
    """The term that puts a transformed likelihood back into measurement space.

    A density over y' = f(y) relates to one over y by
    log L(y) = log L(y') + log|dy'/dy|, so with nllh = -log L,

        nllh_measurement = nllh_transformed + SUM log y   (natural log)
                         = nllh_transformed + SUM (log y + log ln 10)  (log10)

    evaluated at the DATA, because that is where the Jacobian is evaluated. A
    non-positive measurement cannot be log-transformed and is reported rather
    than silently skipped.
    """
    trans = transformations(observables)
    total = 0.0
    detail: dict[str, dict] = {}
    for obs_id, kind in sorted(trans.items()):
        base = _LOG_BASES.get(kind)
        rows = measurements[measurements["observableId"].astype(str) == obs_id]
        values = pd.to_numeric(rows.get("measurement"), errors="coerce").dropna()
        if base is None:
            detail[obs_id] = {
                "transformation": kind,
                "n": int(len(values)),
                "term": 0.0,
            }
            continue
        positive = values[values > 0]
        term = float(np.log(positive).sum())
        if base != math.e:
            term += float(len(positive)) * math.log(math.log(base))
        total += term
        detail[obs_id] = {
            "transformation": kind,
            "n": int(len(values)),
            "n_unusable": int(len(values) - len(positive)),
            "term": round(term, 6),
        }
    return total, detail


def comparable(per_candidate: dict[str, dict[str, str]]) -> tuple[bool, str]:
    """Do these candidates share one transformation per observable?

    Returns (shared, detail). `shared` False means the criteria are over
    different data and need the correction before any comparison.
    """
    if not per_candidate:
        return True, "no candidates"
    observables = sorted({o for t in per_candidate.values() for o in t})
    differing = {}
    for obs_id in observables:
        seen = {t.get(obs_id, "lin") for t in per_candidate.values()}
        if len(seen) > 1:
            differing[obs_id] = sorted(seen)
    if not differing:
        one = next(iter(per_candidate.values()))
        kinds = sorted({one.get(o, "lin") for o in observables})
        return True, (
            f"every candidate uses the same transformation per observable "
            f"({', '.join(kinds)}) — criteria are already over the same data"
        )
    return False, (
        "candidates disagree on the observable transformation, so their raw "
        "likelihoods are over different data: "
        + "; ".join(f"{o}: {' vs '.join(v)}" for o, v in differing.items())
    )


def information_criteria(nllh: float, n_est: int, n_data: int) -> dict[str, float]:
    """AIC and BIC of a fit: every estimated parameter is charged."""
    return {
        "aic": 2 * n_est + 2 * nllh,
        "bic": n_est * float(np.log(max(n_data, 1))) + 2 * nllh,
    }


def apply_correction(
    rows: list[dict], transforms: dict, corrections: dict
) -> tuple[bool, dict]:
    """Put every candidate's likelihood in measurement space, in place.

    Returns (already_shared, the comparability record). Must run before
    anything is compared: the winner, ΔAIC and weights are computed from the
    rows, and petab_select must be handed the same corrected likelihoods.
    """
    shared, detail = comparable(transforms)
    if not shared:
        for row in rows:
            term = float(corrections.get(row["id"], 0.0))
            row["nllh_transformed"] = row["nllh"]
            row["jacobian_correction"] = round(term, 6)
            row["nllh"] = row["nllh"] + term
            row.update(information_criteria(row["nllh"], row["n_est"], row["n_data"]))
    return shared, {
        "shared_transformation": shared,
        "correction_applied": not shared,
        "detail": detail,
        "per_candidate": {
            cid: {
                "transformations": transforms[cid],
                "correction": round(float(corrections.get(cid, 0.0)), 6),
            }
            for cid in transforms
        },
        "reads_as": (
            "criteria are over the same data; no change-of-variables term is needed"
            if shared
            else "criteria are expressed in MEASUREMENT space: the "
            "change-of-variables term was added to each candidate's nllh BEFORE "
            "anything was compared, and nllh_transformed keeps the raw value"
        ),
    }


def petab_select_version() -> str:
    try:
        import importlib.metadata as md

        return md.version("petab-select")
    except Exception:
        return "unknown"


def _criterion(name: str):
    from petab_select import Criterion

    key = name.upper()
    if key == "AICC":
        return Criterion.AICC
    return Criterion[key]


def _input_of(work: Node) -> petab_io.PetabInput:
    """A candidate's assembled problem, from its work group
    (`rounds/<k>/candidates/<id>`) and the candidate's own model beside it."""
    return petab_io.from_work(work, work / "model")


def export_selection(rnd: Node, out: Path) -> Path:
    """Write a round's selection out as petab_select wrote it, so the record's
    interchange files load in a plain petab_select session: `selection_files/`
    beside `candidates/<id>/petab/` (the candidates' problems, exported from
    the record). The files name those problems by relative path, exactly as
    in the temporary directory `run_selection` ran in. Returns the problem
    yaml. For a collaborator re-checking a selection, and for the tests."""
    out = Path(out)
    files = rnd / "selection_files"
    target = out / "selection_files"
    target.mkdir(parents=True, exist_ok=True)
    for name in files.children():
        (target / name).write_text(files.child(name).text())
    for cid in tree.candidate_ids(rnd):
        work = tree.work_node(rnd, cid)
        if (work / "petab/parameters").exists():
            petab_io.export_dir(_input_of(work), out / "candidates" / cid / "petab")
    return target / "petab_select_problem.yaml"


def structure_groups(rows: list[dict]) -> dict[str, list[dict]]:
    """Fitted candidates grouped by the structure they were compiled from.

    Keyed by `estimation.compile_content_hash`, the key the AMICI cache uses,
    so one subspace is always one compile of what was actually built.
    """
    from octomod.workflow_modules.estimation.problem import compile_content_hash

    groups: dict[str, list[dict]] = {}
    for r in rows:
        try:
            key = compile_content_hash(_input_of(r["work"]))
        except (OSError, KeyError):  # `RecordMissing` is a KeyError
            key = f"unknown_{r['id']}"  # a missing artifact groups alone
        groups.setdefault(key, []).append(r)
    return groups


def params_of(work: Node, ps) -> dict:
    """A candidate's parameters as PEtab Select reads them: ESTIMATE or fixed value.

    Part of the encoding's contract: the union of these values over a
    structure's candidates (e.g. `{k: [0.0, ESTIMATE]}`) is its subspace.
    """
    par = (work / "petab/parameters").table()
    return {
        str(p.parameterId): (
            ps.ESTIMATE if int(p.estimate) == 1 else float(p.nominalValue)
        )
        for p in par.itertuples()
    }


def run_selection(
    rnd: Node, rows: list[dict], criterion: str, ledger=None, round_idx: int = 0
) -> dict:
    """Run the PEtab Select side of a selection: models, criteria, weights, files.

    `rows`: one dict per candidate with id, nllh, n_data and work (the
    candidate's work node, `tree.work_node(rnd, id)`, holding petab/ and
    model/). Writes the summary to `rnd / "selection"`, the interchange files
    to `rnd / "selection_files" / <name>` as text, and a `selection` row to
    `ledger` if given.
    Returns {"criterion", "values": {cid: {AIC, AICc, BIC, NLLH}}, "weights":
    {cid: w}, "winner", "files", "model_space_sha", "version"}, or
    {"error": str} when petab_select could not do the job (the caller's gate
    then fails).
    """
    try:
        import petab_select as ps
        from petab_select import Criterion, Method
    except Exception as e:
        return {"error": f"petab_select unavailable: {type(e).__name__}: {e}"}

    # petab_select insists on a PEtab yaml PATH per model subspace. The
    # candidates' problems live in the record, so each is exported to a
    # temporary directory for the length of this call and the interchange
    # files petab_select writes there are copied back into the record as
    # text, under `selection_files/`. The temporary copy is never read by the
    # engine; `export_selection` rebuilds it from the record for anyone who
    # wants to load the files in petab_select again.
    import shutil
    import tempfile

    files_node = rnd / "selection_files"
    tmp_root = Path(tempfile.mkdtemp(prefix="octomod_select_"))
    # the temporary copy mirrors the record's layout — selection_files/ beside
    # candidates/<id>/petab/ — so the yaml paths petab_select records in
    # model_space.tsv name the record keys a reader can resolve
    out_dir = tmp_root / "selection_files"
    out_dir.mkdir(parents=True, exist_ok=True)
    crit = _criterion(criterion)
    models = []
    subspaces = []
    groups = structure_groups(rows)
    subspace_yaml: dict[str, str] = {}
    exported: dict[str, Path] = {}

    def _yaml_of(work: Node) -> Path:
        """The temporary yaml of a candidate's problem (exported once)."""
        key = work.key
        if key not in exported:
            exported[key] = petab_io.export_dir(
                _input_of(work), tmp_root / "candidates" / work.name / "petab"
            )
        return exported[key]

    try:
        for r in rows:
            cid = str(r["id"])
            work = r["work"]
            yaml_path = _yaml_of(work)
            par = (work / "petab/parameters").table()
            best = r.get("best") or {}
            params = {
                str(p.parameterId): (
                    ps.ESTIMATE if int(p.estimate) == 1 else float(p.nominalValue)
                )
                for p in par.itertuples()
            }
            est = {
                str(p.parameterId): float(best.get(str(p.parameterId), p.nominalValue))
                for p in par.itertuples()
                if int(p.estimate) == 1
            }
            m = ps.Model(
                model_subspace_id=cid,
                model_subspace_indices=[0] * len(params),
                criteria={Criterion.NLLH: float(r["nllh"])},
                model_subspace_petab_yaml=yaml_path,
                estimated_parameters=est,
                parameters=params,
                model_id=cid,
            )
            for c in (Criterion.AIC, Criterion.AICC, Criterion.BIC):
                m.compute_criterion(c)  # stores the value on the model
            models.append(m)
        # One subspace per structure: candidates sharing a structure differ only
        # in which parameters are estimated, which is what a subspace expresses
        # (`k_alt: 0;estimate`) and what stepwise/FAMoS neighbourhoods span.
        for skey, members in groups.items():
            values: dict[str, list] = {}
            for r in members:
                for pid, v in params_of(r["work"], ps).items():
                    seen = values.setdefault(pid, [])
                    if v not in seen:
                        seen.append(v)
            # the template is the member with the most estimated parameters, so
            # the subspace only ever fixes relative to it
            template = max(
                members,
                key=lambda r: sum(
                    1 for v in params_of(r["work"], ps).values() if v is ps.ESTIMATE
                ),
            )
            sid = str(template["id"]) if len(members) == 1 else f"structure_{skey[:8]}"
            tmpl_yaml = _yaml_of(template["work"]).resolve()
            subspaces.append(
                ps.ModelSubspace(
                    model_subspace_id=sid,
                    petab_yaml=tmpl_yaml,
                    parameters={k: sorted(v, key=str) for k, v in values.items()},
                )
            )
            subspace_yaml[sid] = os.path.relpath(tmpl_yaml, out_dir.resolve())
        weights = ps.compute_weights(ps.Models(models), crit, as_dict=True)
        by_hash = {m.hash: m for m in models}
        w_by_id = {by_hash[h].model_id: float(w) for h, w in weights.items()}

        space = ps.ModelSpace(subspaces)
        df = space.save()
        if "model_subspace_id" not in df.columns:  # the id is the frame's index
            df = df.reset_index()
        # petab_select writes the yaml paths relative to the cwd; rewrite them
        # relative to the model-space file so the folder is self-contained. By
        # id, not position: the frame has a row per structure, not per candidate.
        df["model_subspace_petab_yaml"] = [
            subspace_yaml.get(str(sid), "") for sid in df["model_subspace_id"]
        ]
        df.to_csv(out_dir / "model_space.tsv", sep="\t", index=False)
        problem = ps.Problem(
            criterion=crit,
            method=Method.BRUTE_FORCE,
            model_space_files=[out_dir / "model_space.tsv"],
            candidate_space_arguments={},
            metaparameters={},
        )
        problem.save(out_dir)
        prob_yaml = out_dir / "petab_select_problem.yaml"
        if not prob_yaml.exists():
            cands = sorted(out_dir.glob("*.yaml"))
            prob_yaml = cands[0] if cands else prob_yaml
        # the fitted models, with their criteria, in the library's own format
        models_path = out_dir / "models.yaml"
        try:
            ps.Models(models).to_yaml(models_path)
        except Exception:  # fall back to a plain dump
            models_path = out_dir / "models.json"
            models_path.write_text(
                json.dumps([json.loads(m.model_dump_json()) for m in models], indent=2)
            )
        # round-trip check: the folder must load in a plain petab_select session
        reloaded = ps.Problem.from_yaml(prob_yaml)
        best = ps.get_best(reloaded, list(models), criterion=crit)
        values = {
            m.model_id: {
                "AIC": float(m.get_criterion(Criterion.AIC)),
                "AICc": float(m.get_criterion(Criterion.AICC)),
                "BIC": float(m.get_criterion(Criterion.BIC)),
                "NLLH": float(m.get_criterion(Criterion.NLLH)),
            }
            for m in models
        }
        # the interchange files go into the record, by name, beside the summary
        # (`out_dir` is the real temporary directory, not the record)
        for f in sorted(out_dir.iterdir()):
            if f.is_file():
                files_node.child(f.name).put_text(f.read_text())
        summary = {
            "criterion": crit.value,
            "values": values,
            "weights": w_by_id,
            "winner": best.model_id,
            "version": petab_select_version(),
            # record keys of the interchange files (`show --run-id <id> <key>`)
            "files": {
                "problem_yaml": files_node.child(prob_yaml.name).key,
                "model_space": files_node.child("model_space.tsv").key,
                "models": files_node.child(models_path.name).key,
            },
            "model_space_sha": sha256_file(out_dir / "model_space.tsv"),
        }
        (rnd / "selection").put(summary)
        if ledger is not None:
            ledger.append(
                "selection",
                module="evaluation",
                round_idx=round_idx,
                tool="petab_select",
                version=summary["version"],
                criterion=crit.value,
                winner=best.model_id,
                model_space_sha=summary["model_space_sha"],
                n_models=len(models),
            )
        return summary
    except Exception as e:
        return {"error": f"petab_select selection failed: {type(e).__name__}: {e}"}
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def crosscheck(local: dict, ps_summary: dict, criterion: str) -> tuple[bool, str]:
    """Check the local arithmetic against petab_select: values, weights, winner.

    They must agree to TOL. Returns (ok, detail).
    """
    if "error" in ps_summary:
        return False, ps_summary["error"]
    crit = criterion.upper()
    key = "AICc" if crit == "AICC" else crit
    problems = []
    lw = {m["model_id"]: m for m in local["models"]}
    for cid, vals in ps_summary["values"].items():
        if cid not in lw:
            problems.append(f"{cid}: not in local selection")
            continue
        dv = abs(vals[key] - lw[cid]["value"])
        if dv > TOL:
            problems.append(
                f"{cid}: {key} local {lw[cid]['value']:.6f} vs "
                f"petab_select {vals[key]:.6f}"
            )
        dw = abs(ps_summary["weights"].get(cid, float("nan")) - lw[cid]["weight"])
        if not dw <= TOL:
            problems.append(
                f"{cid}: weight local {lw[cid]['weight']:.6f} vs "
                f"petab_select {ps_summary['weights'].get(cid)}"
            )
    if ps_summary["winner"] != local["winner"]:
        problems.append(
            f"winner local {local['winner']} vs petab_select " f"{ps_summary['winner']}"
        )
    if problems:
        return False, "; ".join(problems[:5])
    return True, (
        f"petab_select {ps_summary['version']} agrees with the local "
        f"arithmetic on {key}, weights and winner "
        f"({len(ps_summary['values'])} models, tol {TOL})"
    )
