"""Candidates as declared differences from one tested base.

The construction agent writes the BASE, the engine tests it, and a second call
writes each candidate as a DIFFERENCE from it, which this module turns into the
complete candidate. A candidate therefore differs from the base only in what it
declares, and its parameter list is the base's full list with those changes.

A difference has three optional parts, applied in this order:

* `set_parameters` — change EXISTING base parameters: a switch value, an
  estimate flag, bounds (`{"id", "nominal_value"?, "estimate"?, "lb"?, "ub"?}`);
* `on_antimony_patch` — the axis grammar (`model_space.apply_patch`): replace a
  named reaction's line, or append lines; one patch or a list of them;
* `adds_parameters` — complete entries for any symbol a patch introduces.

Changes are applied mechanically; every problem names the candidate and the
symbol, so the repair call can fix exactly that.
"""

from __future__ import annotations

import copy
import json
import re

from octomod.workflow_modules.model.model_space import (
    apply_patch,
    declare_parameter,
    undeclared_symbols,
)

# fields a `set_parameters` entry may change; anything else is refused by name
# rather than silently dropped
SETTABLE = ("nominal_value", "estimate", "lb", "ub", "source", "evidence_tier")


def _patches(variation: dict) -> list[dict]:
    raw = variation.get("on_antimony_patch")
    if not raw:
        return []
    return [p for p in (raw if isinstance(raw, list) else [raw]) if p]


def _set_value_line(antimony: str, pid: str, value) -> str:
    """Make the model's own `pid = value;` agree with the table's nominal value,
    so the S1 ladder simulates the candidate that will be fitted. Several
    assignments may share a line (`kcat = 1; kinh = 1;`); `:=` rules are not
    touched."""
    pattern = re.compile(rf"(?<![\w.]){re.escape(pid)}(\s*)=(\s*)([^;\n]+);")
    if pattern.search(antimony):
        return pattern.sub(
            lambda m: f"{pid}{m.group(1)}={m.group(2)}{value};", antimony, count=1
        )
    return declare_parameter(antimony, {"id": pid, "nominal_value": value})


def materialize(base: dict, variation: dict) -> tuple[dict | None, list[str]]:
    """The complete candidate for one declared difference, or the problems.

    `base` is the tested base reply (its `antimony` and full `parameters`);
    `variation` is one entry of the expansions reply. Problems name the
    candidate, so a list of them from several candidates reads unambiguously.
    """
    cid = str(variation.get("id") or "").strip()
    tag = cid or "(no id)"
    problems: list[str] = []
    if not cid:
        problems.append("a candidate has no id")
    antimony = str(base.get("antimony") or "")
    params = copy.deepcopy(list(base.get("parameters") or []))
    by_id = {str(p.get("id")): p for p in params}

    for change in variation.get("set_parameters") or []:
        pid = str(change.get("id") or "").strip()
        if pid not in by_id:
            problems.append(
                f"{tag}: set_parameters names {pid!r}, which is not a base "
                f"parameter — a new symbol belongs in adds_parameters"
            )
            continue
        unknown = sorted(k for k in change if k not in ("id",) + SETTABLE)
        if unknown:
            problems.append(
                f"{tag}: set_parameters[{pid}] carries {unknown}; only "
                f"{list(SETTABLE)} can be changed"
            )
        entry = by_id[pid]
        for k in SETTABLE:
            if k in change:
                entry[k] = change[k]
        if entry.get("estimate") and (
            entry.get("lb") is None or entry.get("ub") is None
        ):
            problems.append(f"{tag}: {pid} is estimated but has no lb/ub")
        if "nominal_value" in change:
            antimony = _set_value_line(antimony, pid, change["nominal_value"])

    adds = [dict(p) for p in variation.get("adds_parameters") or []]
    for p in adds:
        pid = str(p.get("id") or "").strip()
        if not pid:
            problems.append(f"{tag}: an adds_parameters entry has no id")
        elif pid in by_id:
            problems.append(
                f"{tag}: adds_parameters redeclares base parameter {pid!r} — "
                f"change it with set_parameters instead"
            )
    for patch in _patches(variation):
        missing = undeclared_symbols(
            str(base.get("antimony") or ""),
            {"on_antimony_patch": patch, "adds_parameters": adds},
        )
        if missing:
            problems.append(
                f"{tag}: a patch uses symbol(s) {missing} that neither the base "
                f"nor adds_parameters declares"
            )
        antimony, applied = apply_patch(antimony, patch)
        if not applied:
            what = patch.get("replace_reaction") or "(append)"
            problems.append(
                f"{tag}: patch {what!r} did not apply — replace_reaction must name "
                f"a reaction id of the base exactly"
            )
    for p in adds:
        if p.get("id") and str(p["id"]) not in by_id:
            params.append(p)
            antimony = declare_parameter(antimony, p)

    if problems:
        return None, problems
    return (
        {
            "id": cid,
            "label": variation.get("label", ""),
            "rationale": variation.get("rationale", ""),
            "antimony": antimony,
            "parameters": params,
            "entity_glossary": variation.get("entity_glossary") or {},
            "difference": {
                "set_parameters": list(variation.get("set_parameters") or []),
                "on_antimony_patch": _patches(variation),
                "adds_parameters": adds,
            },
        },
        [],
    )


def _fingerprint(cand: dict) -> str:
    lines = sorted(
        line.strip() for line in cand["antimony"].splitlines() if line.strip()
    )
    pars = sorted(
        json.dumps(
            {k: p.get(k) for k in ("id", "nominal_value", "estimate", "lb", "ub")},
            sort_keys=True,
            default=str,
        )
        for p in cand["parameters"]
    )
    return json.dumps([lines, pars])


def materialize_all(base: dict, expansion: list[dict]) -> tuple[list[dict], list[str]]:
    """Every candidate, or every problem. A set is judged whole: two candidates
    that come out identical are a problem of the SET (a declared difference
    that changes nothing), and so are duplicate ids."""
    cands, problems, seen = [], [], {}
    for v in expansion:
        cand, probs = materialize(base, v)
        problems += probs
        if cand is None:
            continue
        if cand["id"] in {c["id"] for c in cands}:
            problems.append(f"duplicate candidate id {cand['id']!r}")
            continue
        fp = _fingerprint(cand)
        if fp in seen:
            problems.append(
                f"{cand['id']} is identical to {seen[fp]} once built — its "
                f"declared difference changes nothing"
            )
            continue
        seen[fp] = cand["id"]
        cands.append(cand)
    return cands, problems


def difference_lines(cand: dict) -> list[str]:
    """What this candidate changes relative to the base, one short phrase per
    change, for the scope card. By construction this IS everything that differs:
    the card cannot omit a difference the model has."""
    d = cand.get("difference") or {}
    out = []
    for c in d.get("set_parameters") or []:
        bits = []
        if "nominal_value" in c:
            bits.append(f"= {c['nominal_value']}")
        if "estimate" in c:
            bits.append(
                f"estimated [{c.get('lb', '?')}, {c.get('ub', '?')}]"
                if c["estimate"]
                else "fixed"
            )
        elif "lb" in c or "ub" in c:
            bits.append(f"bounds [{c.get('lb', '?')}, {c.get('ub', '?')}]")
        out.append(f"{c.get('id')} {' '.join(bits)}".strip())
    for p in d.get("on_antimony_patch") or []:
        if p.get("replace_reaction"):
            out.append(f"reaction {p['replace_reaction']} replaced")
        elif p.get("append"):
            n = (
                len(p["append"])
                if isinstance(p["append"], list)
                else len(str(p["append"]).strip().splitlines())
            )
            out.append(f"{n} line(s) appended")
    for p in d.get("adds_parameters") or []:
        out.append(f"+ {p.get('id')}")
    return out or ["(the base itself)"]
