"""PEtab problems in memory — the libraries never read the run's record.

`petab.Problem.from_yaml(path)` is the one call that needs a directory of
files: petab resolves the yaml's relative paths and reads five tables from
disk, and pyPESTO, AMICI and petab_select take the problem from petab. Here
the same `petab.v1.Problem` is built from a
`PetabInput` — the four tables, the optional held-out measurements and the
SBML text — so every consumer downstream (`pypesto.petab.PetabImporter`,
`petab.lint.lint_problem`, the flattening of timepoint-specific overrides)
receives an object and asks nothing of the file system.

A `PetabInput` comes from the run record (`from_record`: the assembled
problem at `…/candidates/<id>/petab`) or from a PEtab problem on disk that is
an INPUT — a testcase's `supplied/petab`, a published deposit a test compares
against (`from_dir`). `export_dir` is the one concession the other way, for
petab_select, which insists on a yaml path per model subspace: a temporary,
disposable copy for the length of the call.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pandas as pd

TABLES = ("observables", "conditions", "measurements", "parameters")
HOLDOUT = "holdout_measurements"


@dataclass
class PetabInput:
    """An assembled PEtab problem, in memory."""

    sbml: str
    observables: pd.DataFrame
    conditions: pd.DataFrame
    measurements: pd.DataFrame
    parameters: pd.DataFrame
    holdout: pd.DataFrame | None = None
    problem_yaml: dict = field(default_factory=dict)

    def tables(self) -> dict[str, pd.DataFrame]:
        return {name: getattr(self, name) for name in TABLES}

    def with_tables(self, **tables) -> PetabInput:
        return replace(self, **tables)


# ------------------------------------------------------------- from / to


def sbml_for(petab, model) -> str:
    """The SBML of an assembled problem: the copy beside the tables when the
    legacy importer transcribed one there (`petab/sbml`, from a legacy run
    directory's `petab/model.xml`), else the model's (`model/sbml` — where every module,
    the supplied-PEtab adapter included, writes it)."""
    here = petab / "sbml"
    if here.exists():
        return here.text()
    return (model / "sbml").text()


def from_record(petab, sbml: str | None = None, *, model=None) -> PetabInput:
    """The problem at a record node `…/petab`. The SBML is given, or read
    through `sbml_for(petab, model)`."""
    if sbml is None:
        if model is None:
            raise ValueError("from_record needs the SBML text or the model node")
        sbml = sbml_for(petab, model)
    hold = petab / HOLDOUT
    return PetabInput(
        sbml=sbml,
        holdout=hold.table() if hold.exists() else None,
        problem_yaml=(petab / "problem_yaml").get({}),
        **{name: (petab / name).table() for name in TABLES},
    )


def from_work(work, model) -> PetabInput:
    """The fitted problem of a unit of work (`ctx.work`, `ctx.model`)."""
    return from_record(work / "petab", model=model)


def to_record(inp: PetabInput, petab) -> None:
    """Write every table (and the yaml, and a held-out table when present)."""
    for name, df in inp.tables().items():
        (petab / name).put_table(df)
    if inp.holdout is not None:
        (petab / HOLDOUT).put_table(inp.holdout)
    if inp.problem_yaml:
        (petab / "problem_yaml").put(inp.problem_yaml)


def from_dir(path: Path, yaml_name: str | None = None) -> PetabInput:
    """A PEtab problem on disk (an input, never the run): its yaml, resolved
    relative to the yaml, exactly one file per table."""
    import yaml

    path = Path(path)
    if path.is_file():
        yaml_path = path
    elif yaml_name:
        yaml_path = path / yaml_name
    else:
        found = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
        if not found:
            raise FileNotFoundError(f"no PEtab yaml in {path}")
        yaml_path = next((p for p in found if p.name == "problem.yaml"), found[0])
    spec = yaml.safe_load(yaml_path.read_text()) or {}
    p0 = (spec.get("problems") or [{}])[0]

    def one(key: str) -> Path:
        files = p0.get(key) or []
        if len(files) != 1:
            raise ValueError(f"{yaml_path}: expected one entry in {key}, got {files}")
        return _resolve(yaml_path, files[0])

    par = spec.get("parameter_file")
    par = par if isinstance(par, str) else (par or [None])[0]
    return PetabInput(
        sbml=one("sbml_files").read_text(),
        observables=_read_table(one("observable_files")),
        conditions=_read_table(one("condition_files")),
        measurements=_read_table(one("measurement_files")),
        parameters=_read_table(_resolve(yaml_path, par)),
        holdout=(
            _read_table(yaml_path.parent / "holdout_measurements.tsv")
            if (yaml_path.parent / "holdout_measurements.tsv").exists()
            else None
        ),
        problem_yaml=spec,
    )


def _resolve(yaml_path: Path, rel: str) -> Path:
    cand = yaml_path.parent / rel
    if cand.exists():
        return cand
    cand = yaml_path.parent / Path(rel).name
    if cand.exists():
        return cand
    raise FileNotFoundError(f"{yaml_path} references {rel!r}, which does not exist")


def _read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t" if path.suffix != ".csv" else ",")


# ------------------------------------------------------------ the library


def load_problem(inp: PetabInput):
    """A `petab.v1.Problem` from the tables and the SBML, in memory.

    The tables are indexed the way petab indexes them when it reads from
    disk (`observableId`, `conditionId`, `parameterId`), because
    `lint_problem` and the AMICI importer look them up by index. The
    parameter table keeps its column order; petab's own reader does the same.
    """
    import petab.v1 as petab
    from petab.v1.models.sbml_model import SbmlModel

    return petab.Problem(
        model=SbmlModel.from_string(inp.sbml),
        observable_df=petab.get_observable_df(inp.observables.copy()),
        condition_df=petab.get_condition_df(inp.conditions.copy()),
        measurement_df=petab.get_measurement_df(inp.measurements.copy()),
        parameter_df=petab.get_parameter_df(inp.parameters.copy()),
    )


def lint(problem) -> tuple[bool, list[str]]:
    """`petab.lint.lint_problem` on the object, with what it logged."""
    import io
    import logging

    import petab.v1 as petab

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.getLogger("petab").addHandler(handler)
    try:
        has_errors = petab.lint.lint_problem(problem)
    finally:
        logging.getLogger("petab").removeHandler(handler)
    msgs = [line for line in buf.getvalue().splitlines() if line.strip()]
    return (not has_errors), msgs


def table_text(df: pd.DataFrame) -> str:
    """A table as the TSV text PEtab would read — what content hashes use."""
    return df.to_csv(sep="\t", index=False)


def export_dir(inp: PetabInput, out: Path) -> Path:
    """Write the problem as real files under `out` (a temporary directory),
    for a library that insists on paths. Returns the yaml path. The copy is
    never read back by the engine."""
    import yaml

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in inp.tables().items():
        df.to_csv(out / f"{name}.tsv", sep="\t", index=False)
    if inp.holdout is not None:
        inp.holdout.to_csv(out / f"{HOLDOUT}.tsv", sep="\t", index=False)
    (out / "model.xml").write_text(inp.sbml)
    spec = dict(inp.problem_yaml or {"format_version": 1})
    spec["parameter_file"] = "parameters.tsv"
    spec["problems"] = [
        {
            "sbml_files": ["model.xml"],
            "condition_files": ["conditions.tsv"],
            "measurement_files": ["measurements.tsv"],
            "observable_files": ["observables.tsv"],
        }
    ]
    yaml_path = out / "problem.yaml"
    yaml_path.write_text(yaml.safe_dump(spec, sort_keys=False))
    return yaml_path
