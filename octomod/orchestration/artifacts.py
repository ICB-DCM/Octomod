"""Artifact validation, and reading the files a testcase supplies.

Artifacts are the engine's typed pieces of state. Inter-module state is the
artifact set and nothing else: if a module needs information, it must be a
declared field in one of these.

Every artifact a run produces lives in the run's HDF5 record and is
read and written through `octomod.result.node.Node` (`ctx.work / "estimation"`
…). What this module holds is (a) validation — required-field checking,
deliberately light; the deep checks are the gates' job, not the serializer's
— (b) the readers/writers for REAL files: a testcase's inputs (`supplied/`,
`data/`, `truth/`), fixtures a test builds on disk, and exports. They refuse
a record node, loudly, so a record artifact cannot be written to the file
system by mistake — and (c) the PEtab timepoint-specificity check and the
flattening remedy, which take the in-memory tables (`petab_io.PetabInput`).
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pandas as pd

from octomod.orchestration.ledger import sha256_text


class ArtifactError(Exception):
    """A malformed artifact. T0 hard floor: do not iterate against this."""


def _file(path) -> Path:
    if hasattr(path, "store") and hasattr(path, "key"):
        raise TypeError(
            f"{path!r} is in the run record: use the node's get/put, not a "
            "file reader"
        )
    return Path(path)


def write_json(path, obj: dict | list) -> str:
    """A JSON file (a fixture, an export). Returns the sha16 of its text."""
    path = _file(path)
    text = json.dumps(obj, indent=2, default=str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    return sha256_text(text)


_REQUIRED = object()


def read_json(path, default=_REQUIRED):
    """The JSON file at `path`. A missing file raises ArtifactError unless
    `default` is given, which is then returned; a corrupt file always raises.
    (A record node reads with `node.get(default)`.)"""
    path = _file(path)
    if not path.exists():
        if default is _REQUIRED:
            raise ArtifactError(f"missing artifact: {path}")
        return default
    return json.loads(path.read_text())


def read_json_or(path, default):
    """The JSON at `path`, or `default` when it is missing, unreadable or not
    valid JSON. Never raises for a file: for a reader whose record may
    legitimately be absent or half-written, where no answer is the answer. A
    shape check (dict or list) stays with the caller, which knows what it
    expects. (A record node is refused, as everywhere here: `node.get(default)`
    is its form.)"""
    path = _file(path)
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_tsv(path, df: pd.DataFrame) -> str:
    """A table file. `.csv` names are written comma-separated."""
    path = _file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep="\t" if path.suffix != ".csv" else ",", index=False)
    return sha256_text(path.read_text())


def read_tsv(path) -> pd.DataFrame:
    path = _file(path)
    if not path.exists():
        raise ArtifactError(f"missing artifact: {path}")
    return pd.read_csv(path, sep="\t" if path.suffix != ".csv" else ",")


# ---------------------------------------------------------------- intent

INTENT_REQUIRED = [
    "question",
    "system",
    "required_entities",
    "required_predictions",
    "timescale",
    "inference_target",
    "domain_packs",
    "success_criteria",
]

INFERENCE_TARGETS = ["prediction", "parameter_values", "mechanism_discrimination"]


def validate_intent(intent: dict) -> list[str]:
    """T0 checks on the frozen intent. Returns list of failures (empty = pass)."""
    problems = []
    for key in INTENT_REQUIRED:
        if key not in intent or intent[key] in (None, "", []):
            problems.append(f"intent.{key} missing or empty")
    target = intent.get("inference_target")
    if target not in INFERENCE_TARGETS:
        problems.append(
            f"intent.inference_target must be one of {INFERENCE_TARGETS}, got {target!r}"
        )
    # OPTIONAL: the reactions the model must contain, beside the entities it
    # must contain; each an equation the engine can read
    from octomod.workflow_modules.knowledge.reaction_evidence import intent_problems

    problems += intent_problems(intent)
    return problems


# ------------------------------------------------- timepoint-specific overrides

# a value no PEtab id can take, standing in for a blank cell while grouping
_NO_PREEQUILIBRATION = "\x00none"


def timepoint_specific(measurement_df, **kwargs) -> bool:
    """petab's `measurement_table_has_timepoint_specific_mappings`, right about
    a partly blank `preequilibrationConditionId` column.

    petab groups the rows twice, once keeping blank cells and once dropping
    them, so a table in which only some conditions pre-equilibrate reads as
    timepoint-specific when nothing is, and AMICI then refuses to import it. A
    blank cell gets a value of its own for the comparison only; the table is
    not changed."""
    col = "preequilibrationConditionId"
    if measurement_df is not None and col in measurement_df.columns:
        blank = measurement_df[col].isna()
        if blank.any() and not blank.all():
            measurement_df = measurement_df.copy()
            measurement_df[col] = (
                measurement_df[col].astype(object).where(~blank, _NO_PREEQUILIBRATION)
            )
    return bool(_petab_timepoint_check()(measurement_df, **kwargs))


_PETAB_CHECK: list = []  # petab's own check, captured before any patch


def _petab_timepoint_check():
    if not _PETAB_CHECK:
        from petab.v1 import lint

        _PETAB_CHECK.append(lint.measurement_table_has_timepoint_specific_mappings)
    return _PETAB_CHECK[0]


@contextlib.contextmanager
def timepoint_check_patched():
    """AMICI's PEtab import asks petab's check by module attribute; for the
    duration of an import it asks `timepoint_specific` instead."""
    from petab.v1 import lint

    real = _petab_timepoint_check()
    lint.measurement_table_has_timepoint_specific_mappings = timepoint_specific
    try:
        yield
    finally:
        lint.measurement_table_has_timepoint_specific_mappings = real


def flatten_timepoint_specific(inp, include_holdout: bool = True):
    """Split every observable whose observable/noise parameters are overridden
    PER TIMEPOINT into one observable per override group — PEtab's own remedy
    (`flatten_timepoint_specific_output_overrides`) for AMICI's refusal to
    import such a problem. `inp` is a `petab_io.PetabInput`; returns
    `(flattened input, info)`, where the observable and measurement tables
    — and the held-out measurements when `include_holdout` and present — are
    rewritten with the SAME flattened ids (the held-out rows must name the
    observables the model actually has). `observableName` carries the
    original id.

    Used by the supplied-PEtab adapter and by the assembly renderer
    (`per: timepoint` scaling). `info` is {"n_before", "n_after", "renamed":
    {original: [flattened]}}, or None (and `inp` unchanged) when nothing was
    timepoint-specific. The check is `timepoint_specific` above — petab's
    own, right about a partly blank pre-equilibration column.
    """
    import pandas as pd
    from petab.v1.core import flatten_timepoint_specific_output_overrides

    has_timepoint_specific = timepoint_specific

    from octomod.workflow_modules.assembly.petab_io import load_problem

    pp = load_problem(inp)
    main = pp.measurement_df.copy()
    main = main.drop(columns=[c for c in main.columns if str(c).startswith("Unnamed:")])
    hold = inp.holdout if include_holdout else None
    if not has_timepoint_specific(main) and not (
        hold is not None and len(hold) and has_timepoint_specific(hold)
    ):
        return inp, None
    # flatten over the UNION so a held-out row at a time the training rows
    # also have gets the same flattened id; a marker column splits them back
    marker = "__octomod_split"
    parts = [main.assign(**{marker: "measurements"})]
    if hold is not None and len(hold):
        parts.append(hold.assign(**{marker: "holdout"}))
    union = pd.concat(parts, ignore_index=True)
    n_before = len(pp.observable_df)
    before_ids = list(pp.measurement_df["observableId"].astype(str))
    pp.measurement_df = union
    flatten_timepoint_specific_output_overrides(pp)
    obs_out = pp.observable_df.copy()
    # the original id survives as the display name; the adapter set this
    # convention and round_status reads it back
    obs_out["observableName"] = [
        _original_observable_id(str(fid), before_ids) for fid in obs_out.index
    ]
    flat = pp.measurement_df
    renamed: dict[str, list[str]] = {}
    for orig, fid in zip(
        union["observableId"].astype(str),
        flat["observableId"].astype(str),
        strict=False,
    ):
        if fid not in renamed.setdefault(orig, []):
            renamed[orig].append(fid)

    def rows(which: str):
        return flat[flat[marker] == which].drop(columns=[marker]).reset_index(drop=True)

    out = inp.with_tables(
        observables=obs_out.reset_index(),
        measurements=rows("measurements"),
        holdout=rows("holdout") if (hold is not None and len(hold)) else inp.holdout,
    )
    return out, {"n_before": n_before, "n_after": len(obs_out), "renamed": renamed}


def _original_observable_id(flattened_id: str, original_ids: list[str]) -> str:
    """`p_0__xi_0_s_t0__sd__condition1` -> `p_0`: the longest original id the
    flattened id starts with, so an original id containing `__` still resolves."""
    hits = [
        o
        for o in set(original_ids)
        if flattened_id == o or flattened_id.startswith(o + "__")
    ]
    return max(hits, key=len) if hits else flattened_id
