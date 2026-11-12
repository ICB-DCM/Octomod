"""Write an artifact through its record: validate, then write.

A module that writes
the estimation summary, the evaluation, an assembly, the revision, the
expansion, the intent, the cost profile, a decision or the
model space passes its payload through the record class that describes that
artifact. The payload is written as it was — into the run record at the
node the module names — so nothing downstream notices, but a payload
that does not fit its declared shape stops the module here, with the field
named, instead of being found by a reader three modules later.

`ArtifactError` is the T0 hard floor of `octomod/orchestration/artifacts.py`: a
malformed artifact is not something to iterate against.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from octomod.orchestration.artifacts import ArtifactError


def validate_record(record_cls: type[BaseModel], payload: Any, where: str) -> BaseModel:
    """Validate `payload` against `record_cls`, naming the field on failure."""
    try:
        return record_cls.model_validate(payload)
    except ValidationError as e:
        lines = "; ".join(
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in e.errors()[:6]
        )
        raise ArtifactError(
            f"{where} does not fit its record {record_cls.__name__}: {lines}"
        ) from e


def write_record(node, record_cls: type[BaseModel], payload: Any) -> str:
    """Validate `payload` as a `record_cls`, then write it unchanged at the
    record node `node`. Returns the sha16 `Node.put` returns."""
    validate_record(record_cls, payload, node.key)
    return node.put(payload)


def write_records(node, record_cls: type[BaseModel], rows: list) -> str:
    """The list form: every row is validated as a `record_cls`."""
    for i, row in enumerate(rows):
        validate_record(record_cls, row, f"{node.key}[{i}]")
    return node.put(rows)
