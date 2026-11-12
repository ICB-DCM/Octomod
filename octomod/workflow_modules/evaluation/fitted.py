"""A fitted candidate read back from the run record.

One recipe for every reader that needs a candidate's tables, optimum,
assembly and structural-misfit evidence. Condition labels cover the training
conditions only: held-out data never enters the training evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from octomod.result import node as _tree


@dataclass
class Fitted:
    cid: str | None
    tables: object  # PetabTables
    best: dict
    assembly: dict
    long_df: pd.DataFrame | None
    obs_labels: dict[str, str]
    cond_labels: dict[str, str]

    def misfit_evidence(self, spec, fit=None) -> dict:
        """The model-free structural-misfit evidence of this fit; `fit` is the
        fit-metrics block when the caller has one."""
        from octomod.workflow_modules.evaluation.engine import (
            structural_misfit_evidence,
        )

        return structural_misfit_evidence(
            self.tables,
            self.best,
            self.long_df,
            fit or [],
            spec,
            self.obs_labels,
            self.cond_labels,
        )


def floors(evidence: dict) -> dict[str, float]:
    """observable id -> the replicate noise floor the evidence measured."""
    return {
        s["observable"]: s["sigma_replicate"]
        for s in (evidence.get("signals", {}).get("sigma_vs_floor") or [])
    }


def label_maps(
    assembly: dict, trained: set[str] | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """(observable id -> data label, condition id -> data label); with
    `trained`, only the conditions in that set."""
    obs = {
        o["observable_id"]: o["maps_to_label"] for o in assembly.get("observables", [])
    }
    cond = {
        c["condition_id"]: c["maps_to_label"]
        for c in assembly.get("conditions", [])
        if trained is None or str(c["condition_id"]) in trained
    }
    return obs, cond


def trained_conditions(tables) -> set[str]:
    """The condition ids the fit was trained on (the measurement table holds
    no held-out rows)."""
    return set(tables.measurements["simulationConditionId"].astype(str))


def load(ctx, cid: str | None, *, long_df: pd.DataFrame | None = None) -> Fitted:
    """Candidate `cid` of the current round (None: the single-model round).

    `long_df` is the round's long table when the caller already read it.
    Raises ValueError when the candidate has no estimation result.
    """
    from octomod.gates.petab_gates import PetabTables

    cid = str(cid) if cid else None
    work = _tree.work_node(ctx.round, cid)
    summary = work / "estimation"
    if not summary.exists():
        raise ValueError(f"candidate {cid!r} has no estimation result in this round")
    tables = PetabTables.from_work(work, _tree.model_node(ctx.round, cid))
    assembly = (work / "assembly").get({"observables": [], "conditions": []})
    if not isinstance(assembly, dict):
        assembly = {"observables": [], "conditions": []}
    if long_df is None:
        long_node = ctx.round / "data" / "measurements"
        long_df = long_node.table() if long_node.exists() else None
    obs_labels, cond_labels = label_maps(assembly, trained_conditions(tables))
    return Fitted(
        cid=cid,
        tables=tables,
        best=summary.get()["best_x_unscaled"],
        assembly=assembly,
        long_df=long_df,
        obs_labels=obs_labels,
        cond_labels=cond_labels,
    )
