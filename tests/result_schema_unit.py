"""The result schema documents cannot go stale silently.

Same contract as tests/module_map_unit.py for the figures: the committed
`docs/result_schema.json` and `docs/RESULT-SCHEMA.md` must be what
`tools/make_result_schema.py` produces from the pydantic records, and a build
must be deterministic so a regeneration never shows a spurious diff.

Also asserted: every record class in `octomod/result/` appears on the page,
every tier is one of the declared three, and no field is typed so loosely that
its schema is empty.

    uv run python tests/result_schema_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import make_result_schema as gen  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from octomod.result import model as _model  # noqa: E402
from octomod.result import records as _records  # noqa: E402
from octomod.result import slots as _slots  # noqa: E402
from octomod.result.records import TIERS  # noqa: E402


def _all_records() -> list[type[BaseModel]]:
    out = []
    for mod in (_records, _slots, _model):
        for name in sorted(vars(mod)):
            obj = getattr(mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and obj.__module__ == mod.__name__
            ):
                out.append(obj)
    return out


def test_build_is_deterministic() -> None:
    a = gen.build()
    b = gen.build()
    assert a == b, "two builds differ — something in the walk is unordered"
    print("  determinism   two builds byte-identical")


def test_committed_docs_are_current() -> None:
    js, md = gen.build()
    for path, want in ((gen.SCHEMA_JSON, js), (gen.SCHEMA_MD, md)):
        assert (
            path.exists()
        ), f"{path.relative_to(REPO)} is missing — run tools/make_result_schema.py"
        assert path.read_text() == want, (
            f"{path.relative_to(REPO)} is stale; regenerate with "
            f"`uv run python tools/make_result_schema.py`"
        )
    print(
        "  committed     docs/result_schema.json and RESULT-SCHEMA.md match a fresh build"
    )


def test_page_names_every_record_and_every_tier_is_declared() -> None:
    _, md = gen.build()
    missing = [c.__name__ for c in _all_records() if f"## `{c.__name__}`" not in md]
    assert not missing, f"records absent from RESULT-SCHEMA.md: {missing}"
    bad = []
    for cls in _all_records():
        for name, info in cls.model_fields.items():
            extra = info.json_schema_extra
            t = extra.get("tier", "core") if isinstance(extra, dict) else "core"
            if t not in TIERS:
                bad.append(f"{cls.__name__}.{name}: {t!r}")
    assert not bad, f"fields with an undeclared tier: {bad}"
    print(
        f"  coverage      {len(_all_records())} records on the page, every tier in {TIERS}"
    )


def test_no_field_has_an_empty_schema() -> None:
    schema = json.loads(gen.build_json())
    loose = []
    for rec, body in schema.get("$defs", {}).items():
        for field, sub in (body.get("properties") or {}).items():
            if sub == {} or sub == {"title": field}:
                loose.append(f"{rec}.{field}")
    assert not loose, (
        "fields whose schema accepts anything (an `object`/`Any` annotation): "
        f"{loose} — type them, or the schema promises nothing"
    )
    print("  typed         no property with an empty schema")


if __name__ == "__main__":
    for fn in (
        test_build_is_deterministic,
        test_committed_docs_are_current,
        test_page_names_every_record_and_every_tier_is_declared,
        test_no_field_has_an_empty_schema,
    ):
        print(fn.__name__)
        fn()
    print("OK")
