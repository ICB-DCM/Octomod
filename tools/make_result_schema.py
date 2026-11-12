"""Generate docs/result_schema.json and docs/RESULT-SCHEMA.md from the record.

The schema is READ from the pydantic classes in `octomod/result/`, never
written by hand: a document that has to be remembered goes stale, and
`tests/result_schema_unit.py` fails when either output differs from a fresh
build. Regenerate with

    uv run python tools/make_result_schema.py

`result_schema.json` is the JSON Schema mkstd generates for the HDF5 record
(the validator any reader can use without this repository). `RESULT-SCHEMA.md`
is the same information for a person: every record, every field, its type,
its tier and its description, so the sharing skill's `--tiers` has a page to
point at.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, get_args, get_origin

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pydantic import BaseModel  # noqa: E402

from octomod.result import model as _model  # noqa: E402
from octomod.result import records as _records  # noqa: E402
from octomod.result import slots as _slots  # noqa: E402
from octomod.result.store import schema_json  # noqa: E402

SCHEMA_JSON = REPO / "docs" / "result_schema.json"
SCHEMA_MD = REPO / "docs" / "RESULT-SCHEMA.md"


def _type_name(tp: Any) -> str:
    """A readable type: `dict[str, GateRecord]`, `Table | None`, `list[float]`."""
    if tp is None or tp is type(None):
        return "None"
    if isinstance(tp, type):
        return tp.__name__
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is None:
        return str(tp).replace("typing.", "")
    import types
    import typing

    if origin in (typing.Union, types.UnionType):
        return " | ".join(_type_name(a) for a in args)
    if origin is typing.Literal:
        return " | ".join(repr(a) for a in args)
    name = getattr(origin, "__name__", str(origin))
    if args:
        return f"{name}[{', '.join(_type_name(a) for a in args)}]"
    return name


def _tier(info) -> str:
    extra = info.json_schema_extra
    return str(extra.get("tier", "core")) if isinstance(extra, dict) else "core"


def _records_in_order() -> list[type[BaseModel]]:
    """Root first, then every record reachable from it, in a stable order."""
    seen: list[type[BaseModel]] = []

    def walk(cls: type[BaseModel]) -> None:
        if cls in seen or cls is BaseModel:
            return
        seen.append(cls)
        for info in cls.model_fields.values():
            for sub in _model_types(info.annotation):
                walk(sub)

    walk(_model.RunResult)
    # records not reachable from the root are still part of the vocabulary
    for mod in (_records, _slots, _model):
        for name in sorted(vars(mod)):
            obj = getattr(mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj not in seen
                and obj.__module__ == mod.__name__
            ):
                seen.append(obj)
    return seen


def _model_types(tp: Any) -> list[type[BaseModel]]:
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return [tp]
    out: list[type[BaseModel]] = []
    for a in get_args(tp) or ():
        out += _model_types(a)
    return out


def build_md() -> str:
    lines = [
        "# The result record — every field, its type and its tier",
        "",
        "<!-- GENERATED from octomod/result/ by tools/make_result_schema.py.",
        "     Do not edit by hand: tests/result_schema_unit.py fails on drift. -->",
        "",
        "One record per run — the run IS the file `runs/<id>.h5`, written group by",
        "group as the engine runs (`runstore.py`, hdfdict; mkstd's `Hdf5Standard` produces",
        "this schema); the JSON Schema a reader validates against without this",
        "repository is [`result_schema.json`](result_schema.json).",
        "",
        "**Tiers.** `core` is what a reader needs to understand the answer and is",
        "always kept; `bulk` holds arrays, traces and tables; `audit` holds prompts,",
        "raw replies and the ledger. A copy made with fewer tiers lists what it",
        "dropped in each record's `elided`.",
        "",
        f"Schema version **{_records.SCHEMA_VERSION}**. Every record allows extra",
        "keys, so agent-authored content whose shape varies is kept whole.",
        "",
    ]
    for cls in _records_in_order():
        doc = (cls.__doc__ or "").strip().splitlines()
        first = doc[0].strip() if doc else ""
        lines += [f"## `{cls.__name__}`", ""]
        if first:
            lines += [first, ""]
        lines += ["| field | type | tier | description |", "|---|---|---|---|"]
        for name, info in cls.model_fields.items():
            if name == "elided":
                continue
            desc = (info.description or "").replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{name}` | `{_type_name(info.annotation)}` | {_tier(info)} | {desc} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_json() -> str:
    schema = json.loads(schema_json())
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def build() -> tuple[str, str]:
    return build_json(), build_md()


def main() -> int:
    js, md = build()
    for path, content in ((SCHEMA_JSON, js), (SCHEMA_MD, md)):
        changed = not path.exists() or path.read_text() != content
        path.write_text(content)
        print(f"{'wrote' if changed else 'unchanged'} {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
