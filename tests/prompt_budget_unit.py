"""How many bytes an agent is sent, and what is in them.

  1. the agent view keeps every reading and summarises the sampled curves, at under 10% the size;
  2. an over-cap payload degrades in `PAYLOAD_BUDGET`'s order, every step noted; under it, untouched;
  3. the cap is on the call and blocking: a payload still over it is refused and ledgered;
  4. the cap lives in one place: both full specs declare it and the code holds no twin.

    uv run python tests/prompt_budget_unit.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import yaml  # noqa: E402
from _harness import FAILS, check  # noqa: E402

from octomod import config  # noqa: E402
from octomod.agents import (  # noqa: E402
    build_prompt,
    build_prompt_within_budget,
    call_agent,
    payload,
)
from octomod.gates import GateFailure  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.reporting import render  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from tests._record import record_at, rnd, run_root  # noqa: E402


def synthetic_core() -> dict:
    """A report_core with 11 profiles of 324-point paths and 15 bands of 61 points."""
    profiles = {"_meta": {"x_names": [f"p{i}" for i in range(11)]}}
    for i in range(11):
        profiles[f"p{i}"] = {
            "ci95": [0.1 * (i + 1), 0.3 * (i + 1)],
            "ci_finite": True,
            "ci_width_decades": 0.4 + 0.01 * i,
            "ci_box_fraction": 0.02 + 0.001 * i,
            "path": {
                "x_unscaled": [0.1 + 0.001 * j for j in range(324)],
                "fval": [100.0 + 0.01 * j for j in range(324)],
            },
        }
    bands = {}
    for i in range(15):
        t = [float(2 * j) for j in range(61)]
        best = [0.01 * j for j in range(61)]
        bands[f"obs_{i}@cond_{i}"] = {
            "time": t,
            "best": best,
            "lo95": [b - 0.05 for b in best],
            "hi95": [b + 0.05 for b in best],
            "lo90": [b - 0.04 for b in best],
            "hi90": [b + 0.04 for b in best],
        }
    return {
        "goal": "mechanism_discrimination",
        "computed_cannot_distinguish": ["1.00*log(a) - 1.00*log(b)"],
        "computed_nonetheless_determined": ["p3"],
        "holdout": {"available": True, "groups": [{"label": "g", "nrmse": 0.1}]},
        "discrimination": {"winner": "M3", "rows": [{"id": "M3", "aic": 1.0}]},
        "profiles": profiles,
        "prediction_uncertainty": {
            "method": "profile-skeleton",
            "df": 11,
            "n_kept": 4000,
            "bands": bands,
        },
        "attribution": {"available": True, "winner": "M3", "rivals": []},
    }


class StubSpec:
    """Only the keys the prompt path reads, so the test states its own threshold."""

    def __init__(self, cap: int | None):
        self.cap = cap  # None = no cap, as `agents.max_prompt_bytes: null`

    def get(self, dotted, default=None):
        if dotted == "agents.max_prompt_bytes":
            return self.cap
        return default

    def require(self, dotted):
        val = self.get(dotted)
        if val is None:
            raise KeyError(dotted)
        return val

    def model_for_role(self, role):
        return "stub"


def nbytes(obj) -> int:
    return len(json.dumps(obj, indent=2, default=str).encode())


# ------------------------------------------------------------------ the view


def test_the_view_keeps_the_reading_and_drops_the_curve() -> None:
    core = synthetic_core()
    view = payload.core_for_agents(core)

    check(
        "every top-level key survives the trim",
        set(view) == set(core),
        f"lost {sorted(set(core) - set(view))}, gained {sorted(set(view) - set(core))}",
    )
    untouched = [k for k in core if k not in ("profiles", "prediction_uncertainty")]
    same = [k for k in untouched if view[k] == core[k]]
    check(
        "every key that is not a sampled curve is byte-identical",
        sorted(same) == sorted(untouched),
        f"changed: {sorted(set(untouched) - set(same))}",
    )
    check(
        "no profile in the view carries its path array",
        all(
            "path" not in rec
            for pid, rec in view["profiles"].items()
            if isinstance(rec, dict) and pid != "_meta"
        ),
    )
    kept = {"ci95", "ci_finite", "ci_width_decades", "ci_box_fraction"}
    check(
        "but the whole READING of each profile survives",
        all(
            kept <= set(rec)
            for pid, rec in view["profiles"].items()
            if pid != "_meta" and isinstance(rec, dict)
        ),
        f"p0 keys {sorted(view['profiles']['p0'])}",
    )
    check(
        "and the view says where the dropped arrays are",
        payload.FULL_RECORD in view["profiles"]["_meta"]["paths_dropped"],
        view["profiles"]["_meta"].get("paths_dropped", "")[:60],
    )
    check(
        "the per-timepoint band arrays are gone, one summary per band remains",
        "bands" not in view["prediction_uncertainty"]
        and len(view["prediction_uncertainty"]["bands_summary"]) == 15,
        f"{sorted(view['prediction_uncertainty'])}",
    )
    check(
        "the band summary names its denominator, and says it is not the " "holdout one",
        "band_rel_width" in view["prediction_uncertainty"]["bands_note"],
        view["prediction_uncertainty"]["bands_note"][-90:],
    )
    before, after = nbytes(core), nbytes(view)
    check(
        "the large recorded payload lands under a tenth of its size",
        after < 0.1 * before,
        f"{before:,} -> {after:,} bytes ({after / before:.1%})",
    )


def test_the_band_summary_is_arithmetically_what_it_claims() -> None:
    # widest at t=20 by construction; median width is 1.0
    t = [0.0, 10.0, 20.0, 30.0]
    band = {
        "time": t,
        "best": [0.0, 1.0, 2.0, 4.0],
        "lo95": [0.0, 0.5, 0.0, 3.5],
        "hi95": [1.0, 1.5, 3.0, 4.5],
    }
    s = payload.band_summary(band)
    check("n_points is the number of timepoints", s["n_points"] == 4, str(s))
    check(
        "the widest 95% band is found", s["width95_max"] == 3.0, str(s["width95_max"])
    )
    check("and located in time", s["width95_max_at_t"] == 20.0, str(s))
    check("the median width is the median", s["width95_median"] == 1.0, str(s))
    # the view's ratio divides by the range of the best trajectory (4.0), not by
    # the range of the measurements, which holdout.groups[].band_rel_width uses
    check(
        "the ratio divides by the best-trajectory range, not the data range",
        s["width95_max_over_best_range"] == 0.75,
        f"{s['width95_max_over_best_range']} (3.0/4.0 = 0.75; a data range of "
        f"1.5 would have given 2.0)",
    )
    ragged = payload.band_summary({"time": [0.0, 1.0], "lo95": [0.0], "hi95": [1.0]})
    check(
        "a ragged band is refused, not silently summarised",
        "summary_unavailable" in ragged,
        str(ragged),
    )
    flat = payload.band_summary(
        {"time": [0.0, 1.0], "best": [1.0, 1.0], "lo95": [0.9, 0.9], "hi95": [1.1, 1.1]}
    )
    check(
        "a flat trajectory gets no ratio rather than a division by zero",
        "width95_max_over_best_range" not in flat and flat["width95_max"] > 0,
        str(flat),
    )


def test_a_core_without_the_heavy_keys_is_returned_unchanged() -> None:
    small = {"goal": "prediction", "holdout": {"available": False}}
    check(
        "a core with no profiles and no bands passes through untouched",
        payload.core_for_agents(small) == small,
    )
    check(
        "and a non-dict is not mangled",
        payload.core_for_agents(None) is None,
    )


# ------------------------------------------ the same numbers, without the packaging


def test_a_number_is_reported_to_the_precision_it_has() -> None:
    r = payload.round_for_agents
    # 4 significant figures by default: `"rmse": 0.04957945933148761` states
    # twelve digits of a quantity whose noise floor is 0.05
    check(
        "a small measurement keeps 4 significant figures",
        r(0.04957945933148761) == 0.04958,
    )
    check(
        "and a tiny one keeps them too, not four decimals",
        r(4.558691955480754e-06) == 4.559e-06,
    )
    # Above 100, significant figures are coarser than the differences that
    # matter: an AIC of -451.46 at 4 s.f. is -451.5, and the ΔAIC ≤ 2 band the
    # same numbers are compared against would be invisible.
    check(
        "a large number gets fixed decimals, so a half-unit AIC gap survives",
        r(-451.4639623486721) == -451.464 and r(-451.9639) != r(-451.4639),
        f"{r(-451.4639623486721)} vs {r(-451.9639)}",
    )
    check("a timepoint is a coordinate: 3 decimals", r(5.0001234, "t") == 5.0)
    check(
        "a residual in noise units: 2 decimals, the third digit is noise",
        r(0.7312, "in_noise_units") == 0.73
        and r(0.7312, "residual_in_noise_units") == 0.73,
    )
    check("an int is exact — a count of 16 points is not a measurement", r(16) == 16)
    check(
        "a bool is an answer, not a quantity",
        r(True) is True and r(False) is False,
    )
    check("a string passes through", r("obs_pR@dose_1") == "obs_pR@dose_1")
    check("None passes through", r(None) is None)
    check("NaN and inf survive rather than raising", str(r(float("nan"))) == "nan")


def test_a_per_point_block_becomes_aligned_columns() -> None:
    rows = [
        {"t": 0.0, "measured": 0.01, "simulated": 0.0, "residual_in_noise_units": 0.19},
        {
            "t": 5.0,
            "measured": 0.1033,
            "simulated": 0.0647,
            "residual_in_noise_units": 0.7312,
        },
    ]
    cols = payload.columnise(rows)
    check(
        "every field is named once instead of once per point",
        set(cols) == {"t", "measured", "simulated", "residual_in_noise_units"},
        str(sorted(cols)),
    )
    check(
        "and the arrays are positionally aligned with the rows they replaced",
        cols["t"] == [0.0, 5.0] and cols["measured"] == [0.01, 0.1033],
        str(cols),
    )
    check(
        "values are rounded by their own field on the way in",
        cols["residual_in_noise_units"] == [0.19, 0.73],
        str(cols["residual_in_noise_units"]),
    )
    check(
        "no per-block note and no redundant count — the arrays give their own "
        "length, and a convention repeated per series costs more than the "
        "packaging it replaced",
        "n" not in cols and "_columns" not in cols,
        str(sorted(cols)),
    )

    # THE refusal that makes this safe
    mixed = [{"group": "a", "share": 0.5}, {"group": "b", "share": 0.5}]
    check(
        "a block with a label in it keeps its record form",
        payload.columnise(mixed) == mixed,
    )
    ragged = [{"t": 0.0, "x": 1.0}, {"t": 1.0}]
    check("ragged records keep their record form", payload.columnise(ragged) == ragged)
    check("a single row is left alone", payload.columnise(rows[:1]) == rows[:1])
    check("so is an empty list, and a non-list", payload.columnise([]) == [])
    nested = [{"t": 0.0, "x": {"deep": 1}}, {"t": 1.0, "x": {"deep": 2}}]
    check(
        "a record with a nested value keeps its form",
        payload.columnise(nested) == nested,
    )


def test_the_column_convention_is_stated_once() -> None:
    rows = [{"t": 0.0, "v": 1.0}, {"t": 1.0, "v": 2.0}]
    many = {
        "how_to_read_this": "read the fits.",
        "per_candidate_residuals": {
            f"cand{i}": {
                "per_series": {f"s{j}": {"fit_over_time": list(rows)} for j in range(6)}
            }
            for i in range(4)
        },
    }
    out = payload.for_agents(many)
    text = json.dumps(out)
    check(
        "the alignment convention appears exactly ONCE in the whole payload",
        text.count("POSITIONALLY ALIGNED") == 1,
        f"{text.count('POSITIONALLY ALIGNED')} occurrences over 24 series",
    )
    check(
        "and it is appended to how_to_read_this, where a reader is already "
        "being told how to read the block",
        "POSITIONALLY ALIGNED" in out["how_to_read_this"],
        out["how_to_read_this"][:60],
    )
    check(
        "every series really was reshaped",
        all(
            isinstance(s["fit_over_time"], dict)
            for c in out["per_candidate_residuals"].values()
            for s in c["per_series"].values()
        ),
    )
    # a payload with no per-point block explains no convention it does not use
    plain = payload.for_agents({"how_to_read_this": "read it.", "x": 1.23456789})
    check(
        "a payload with nothing reshaped carries no column note",
        plain["how_to_read_this"] == "read it." and "_columns" not in plain,
        str(plain),
    )
    # and with no guide to append to, the note gets its own key rather than
    # being dropped
    noguide = payload.for_agents({"a": {"fit_over_time": list(rows)}})
    check(
        "with no how_to_read_this the convention still gets stated",
        "POSITIONALLY ALIGNED" in noguide.get("_columns", ""),
        str(sorted(noguide)),
    )


def test_nothing_is_lost_and_the_artifact_is_untouched() -> None:
    """A re-encoding, not a trim: every key survives, and nothing in the record changes."""
    core = synthetic_core()
    core["attribution"]["rivals"] = [
        {
            "rival": "M1",
            "delta_aic": 224.20531234,
            "contributions": [
                {"group": "obs@c1", "share": 0.271234, "delta_nllh": 31.6274811635},
                {"group": "obs@c2", "share": 0.201234, "delta_nllh": 21.6274811635},
            ],
            "worst_group_detail": {
                "group": "obs@c1",
                "points": [
                    {"time": 0.0, "measured": 1.5918494745, "delta_nllh": 4.34115692},
                    {"time": 5.0, "measured": 2.5918494745, "delta_nllh": 5.34115692},
                ],
            },
        }
    ]
    before = json.loads(json.dumps(core, default=str))
    # `for_agents` alone, not `core_for_agents`: the band summarisation drops the
    # band arrays on purpose, and a real loss here would hide behind that one
    view = payload.for_agents(core)

    check(
        "the input is not mutated — evaluation_core in the record is the artifact "
        "and an agent view may never edit it",
        json.dumps(core, sort_keys=True, default=str)
        == json.dumps(before, sort_keys=True, default=str),
    )

    def keys_of(obj, prefix=""):
        out = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                out.add(f"{prefix}/{k}")
                out |= keys_of(v, f"{prefix}/{k}")
        elif isinstance(obj, list):
            for v in obj:
                out |= keys_of(v, f"{prefix}[]")
        return out

    lost = keys_of(before) - keys_of(view)
    # the reshaped blocks' own field names move from inside a list to inside a
    # dict, so their path changes; nothing else may disappear
    reshaped = {k for k in lost if "/points[]/" in k or "/fit_over_time[]/" in k}
    check(
        "item 17 drops no key at all — it re-encodes, it does not trim",
        not (lost - reshaped),
        f"lost: {sorted(lost - reshaped)[:6]}",
    )
    check(
        "and the only paths that moved are the reshaped per-point blocks",
        bool(reshaped),
        f"{sorted(reshaped)}",
    )

    rival = view["attribution"]["rivals"][0]
    check(
        "a table with labels in it stays a table",
        isinstance(rival["contributions"], list)
        and rival["contributions"][0]["group"] == "obs@c1",
        str(rival["contributions"])[:90],
    )
    check(
        "the per-timepoint block becomes columns",
        isinstance(rival["worst_group_detail"]["points"], dict)
        and rival["worst_group_detail"]["points"]["time"] == [0.0, 5.0],
        str(rival["worst_group_detail"]["points"])[:110],
    )
    check(
        "and every number in it came down to reporting precision",
        rival["worst_group_detail"]["points"]["measured"] == [1.592, 2.592]
        and rival["contributions"][0]["delta_nllh"] == 31.63,
        str(rival["worst_group_detail"]["points"]["measured"]),
    )


# ------------------------------------------------------------------- the cap


def test_every_prompt_states_its_tools() -> None:
    """Every prompt states its role's tools, matching the argv's allowlist."""
    from octomod.agents import ONLINE_ROLES, build_prompt, tools_statement

    offline = build_prompt("construction", {"intent": "q"}, StubSpec(250_000))
    check(
        "an offline role's prompt says TOOLS: none, before the inputs",
        "# Your tools" in offline
        and "TOOLS: none" in offline
        and offline.index("TOOLS: none") < offline.index("# Inputs"),
        offline[offline.find("# Your tools") : offline.find("# Your tools") + 80],
    )
    online = build_prompt("research", {"intent": "q"}, StubSpec(250_000))
    names = ", ".join(ONLINE_ROLES["research"])
    check(
        "the online role's prompt names exactly its allowlist",
        f"TOOLS: {names}" in online and "TOOLS: none" not in online,
        online[online.find("TOOLS:") : online.find("TOOLS:") + 60],
    )
    check(
        "the statement is deterministic per role, so prompt_sha still identifies the ask",
        tools_statement("construction") == tools_statement("construction")
        and tools_statement("construction") != tools_statement("research"),
    )


def test_the_gate_reports_where_the_bytes_are() -> None:
    spec = StubSpec(1000)
    ctx = {"intent": "x" * 100, "report_core": {"blob": "y" * 5000}}
    res = payload.prompt_budget("interpretation", "z" * 5000, spec, ctx)
    check("over the cap fails", not res.passed, res.detail)
    check(
        "and it is blocking — after the degrade order, the alternative to "
        "stopping is paying",
        res.blocking,
    )
    check("tier is T0", res.tier == "T0", res.tier)
    check(
        "value and threshold are the measured bytes and the declared cap",
        res.value == 5000 and res.threshold == 1000,
        f"{res.value} vs {res.threshold}",
    )
    check(
        "the detail names the largest input, so the operator knows what to trim",
        "report_core" in res.detail,
        res.detail[:160],
    )
    check(
        "and names the knob to raise",
        "agents.max_prompt_bytes" in res.detail,
    )
    check(
        "and says the degrade order already ran, so the operator is not told "
        "to trim by hand what the engine has already trimmed",
        "degrade order" in res.detail,
        res.detail[:160],
    )
    ok = payload.prompt_budget("construction", "z" * 500, spec, ctx)
    check("under the cap passes", ok.passed and ok.value == 500, ok.detail)

    # GateResult.summary() clips a detail over 300 chars and points at
    # gates/<id>, which this gate does not write (it lives beside the prompt in
    # agent_calls/<role>), so the detail must never clip
    long_ctx = {f"key_{i}_{'n' * 60}": {"v": "y" * 4000} for i in range(6)}
    worst = payload.prompt_budget(
        "interpretation", "z" * 900_000, StubSpec(1000), long_ctx
    )
    check(
        "the failure detail stays inside the summary's 300-char clip, so it "
        "never points at a gate verdict this gate does not write",
        len(worst.detail) <= payload.SUMMARY_CLIP
        and "full text" not in worst.summary(),
        f"{len(worst.detail)} chars; ends '{worst.detail[-24:]}'",
    )


def test_the_cap_is_enforced_on_the_call_not_merely_computed() -> None:
    """Drive `call_agent` on a payload the budget cannot shrink (one opaque string)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = record_at(Path(tmp) / "run")  # the run is one record file
        ledger = Ledger(tmp)
        calls_node = rnd(tmp, 0) / "agent_calls"
        stubs = REPO / "testcase" / "toy_phos" / "stubs"
        if not stubs.exists():  # pragma: no cover - fixture guard
            check("toy_phos stubs are present", False, str(stubs))
            return
        big = {"intent": "q", "report_core": {"blob": "y" * 200_000}}
        print("    (the FAILED gate line below is this test's own refusal)")
        raised = None
        try:
            call_agent(
                "interpretation",
                big,
                spec=StubSpec(50_000),
                backend="stub",
                calls=calls_node,
                ledger=ledger,
                module="evaluation",
                stubs_dir=stubs,
            )
        except GateFailure as exc:
            raised = exc
        check(
            "a payload the degrade order cannot shrink stops the call",
            raised is not None,
            type(raised).__name__ if raised else "call_agent returned a reply",
        )
        prompt_node = calls_node.child("interpretation") / "prompt"
        check(
            "the refused prompt is in the record — a gate that discards its "
            "evidence leaves nothing to trim",
            prompt_node.exists() and len(prompt_node.text()) > 200_000,
            f"{prompt_node.exists()}",
        )
        rows = ledger.entries()
        gate_rows = [r for r in rows if r.get("gate_id") == "agent_prompt_bytes"]
        check(
            "the gate is ledgered as a FAILED, BLOCKING check, with the role, "
            "the bytes and the cap",
            len(gate_rows) == 1
            and gate_rows[0]["passed"] is False
            and gate_rows[0]["blocking"] is True
            and gate_rows[0]["threshold"] == 50_000
            and gate_rows[0]["role"] == "interpretation",
            str(gate_rows[-1] if gate_rows else rows),
        )
        check(
            "no payload_trimmed row was written — there was nothing to trim, "
            "and a step that removed nothing must not claim it did",
            not [r for r in rows if r.get("event") == "payload_trimmed"],
        )
        check(
            "and no agent_call row was written — nothing was paid for",
            not [r for r in rows if r.get("event") == "agent_call"],
        )
        check(
            "the GateResult travels with the exception, so the caller can "
            "report the numbers",
            raised is not None and raised.result.value > 200_000,
            str(getattr(raised, "result", None)),
        )

        # ... and the same call under a cap that admits it goes through
        run_b = record_at(tmp.store.path.parent / "b")
        ledger2 = Ledger(run_b)
        call_agent(
            "interpretation",
            big,
            spec=StubSpec(500_000),
            backend="stub",
            calls=rnd(run_b, 0) / "agent_calls",
            ledger=ledger2,
            module="evaluation",
            stubs_dir=stubs,
        )
        calls = [r for r in ledger2.entries() if r.get("event") == "agent_call"]
        check(
            "under the cap the call happens and its row carries prompt_bytes",
            len(calls) == 1 and calls[0].get("prompt_bytes", 0) > 200_000,
            str(calls[0].get("prompt_bytes") if calls else "no call"),
        )
        passed = [
            r
            for r in ledger2.entries()
            if r.get("gate_id") == "agent_prompt_bytes" and r.get("passed")
        ]
        check("and the passing gate is ledgered too, not only the failing one", passed)


def test_the_default_lives_in_one_place_with_one_value() -> None:
    """The cap has no code twin; both full specs declare it, the default as `null`."""
    declared = {}
    for name in ("default.yaml", "test_redraft.yaml"):
        raw = yaml.safe_load((REPO / "workflows" / name).read_text())
        agents = raw.get("agents") or {}
        declared[name] = agents.get("max_prompt_bytes")
        check(
            f"{name} declares the key, so its value is hashed into workflow_sha",
            "max_prompt_bytes" in agents,
            str(declared[name]),
        )
    check(
        "the two full specs declare the SAME value",
        len(set(declared.values())) == 1,
        str(declared),
    )
    src = (REPO / "octomod" / "agents" / "payload.py").read_text()
    check(
        "payload.py holds no twin of the number and reads the key in one place",
        "DEFAULT_MAX_PROMPT_BYTES" not in src
        and src.count('"agents.max_prompt_bytes"') == 1
        and "def prompt_cap(" in src,
    )
    spec = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    check(
        "and the default spec declares no cap (null), read back as None",
        payload.prompt_cap(spec) is None and declared["default.yaml"] is None,
        str(spec.get("agents.max_prompt_bytes")),
    )


def test_no_cap_trims_nothing_and_still_records_the_size() -> None:
    """`null` means no cap: nothing is trimmed, the gate passes and ledgers the size."""
    spec = StubSpec(None)
    context = {"intent": "q", "residual_diagnostics": {"x": "y" * 400_000}}
    render = lambda c: str(c)  # noqa: E731
    prompt, ctx_out, trims = payload.fit_to_budget(context, spec, render)
    check(
        "a 400 kB payload under no cap comes back untouched, no trims",
        ctx_out is context and trims == [] and prompt == render(context),
        f"{len(prompt.encode()):,} bytes, {len(trims)} trim(s)",
    )
    res = payload.prompt_budget("interpretation", prompt, spec, context)
    check(
        "the gate passes, keeps its blocking tier, and records the size",
        res.passed
        and res.blocking
        and res.value == len(prompt.encode())
        and res.threshold is None
        and "no cap" in res.detail,
        res.detail,
    )
    with tempfile.TemporaryDirectory() as tmp:
        line = payload.cost_gate_line(Ledger(record_at(Path(tmp) / "run")), spec)
    check("the cost line says there is no cap", "no cap" in line, line)


# ------------------------------------------------------------------ the budget

ARCHIVED_RUN = "live_ctd_positional_1"
# The run is archived as a legacy run DIRECTORY (real files, read only); an
# imported copy is the record `runs/<id>.h5`, read by record key.
ARCHIVED_PROMPT = REPO.joinpath(
    "runs", ARCHIVED_RUN, "round_0", "agent_io", "interpretation_prompt.txt"
)
ARCHIVED_KEY = "rounds/round_0/agent_calls/interpretation/prompt"


def _archived_prompt() -> str | None:
    """The archived S7 prompt, from the legacy directory or the record."""
    if ARCHIVED_PROMPT.exists():
        return ARCHIVED_PROMPT.read_text()
    root = run_root(ARCHIVED_RUN, config.USER_RUNS_DIR)
    if root.exists():
        return (root / ARCHIVED_KEY).text(None)
    return None


# the cap the archived run was held to, and the size of the prompt it refused
LIVE_CAP = 250_000
LIVE_PROMPT_BYTES = 453_497

SKIPPED: list[str] = []


def skip(name: str, why: str) -> None:
    print(f"  · SKIPPED {name} — {why}")
    SKIPPED.append(f"{name}: {why}")


def degradable_context(
    n_obs: int = 8, n_cond: int = 6, n_cand: int = 4, n_terms: int = 60
) -> dict:
    """An S7 discrimination payload whose degradable blocks each miss a small cap alone."""
    labels = [f"obs_{i}@cond_{j}" for i in range(n_obs) for j in range(n_cond)]
    bands = {
        label: {
            "n_points": 61,
            "t_range": [0.0, 120.0],
            "best_range": 1.0 + k,
            "width95_median": 0.01 * (k + 1),
            "width95_max": 0.1 * (k + 1),
            "width95_max_at_t": 10.0,
            "width95_max_over_best_range": 0.05 * (k + 1),
        }
        for k, label in enumerate(labels)
    }
    rivals = [
        {
            "rival": f"M{r}",
            "available": True,
            "delta_aic": 10.0 * r,
            "delta_nllh": 5.0 * r,
            "contributions": [
                {
                    "group": f"{labels[k % len(labels)]}",
                    "observable": f"obs_{k % n_obs}",
                    "condition": f"cond_{k % n_cond}",
                    "delta_nllh": float(n_terms - k),
                    "delta_aic_units": 2.0 * (n_terms - k),
                    "n": 24,
                    "share": (n_terms - k) / n_terms,
                }
                for k in range(n_terms)
            ],
        }
        for r in range(1, 4)
    ]
    per_candidate = {
        f"M{c}": {
            "transformations": {f"obs_{i}": "lin" for i in range(n_obs * n_cond)},
            "correction": 0.0,
            "by_observable": {
                f"obs_{i}": {"transformation": "lin", "n": 24, "term": 0.0}
                for i in range(n_obs * n_cond)
            },
        }
        for c in range(1, n_cand + 1)
    }
    residuals = {
        f"M{c}": {
            "per_series": {
                label: {
                    "rmse": 1.0 / (1 + labels.index(label)),
                    "n_timepoints": 6,
                    "largest_deviation": {"at_time": 5.0, "signed_residual": 0.2},
                    "residual_sign_pattern_over_time": "++--+-",
                    "n_sign_runs": 4,
                    "lag1_autocorr": 0.1,
                    "fit_over_time": {
                        "t": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                        "measured": [0.1] * 6,
                        "simulated": [0.2] * 6,
                    },
                }
                for label in labels
            }
        }
        for c in range(1, n_cand + 1)
    }
    # the declared-constant drift table repeats its prose once per condition
    constants = [
        {
            "expression": f"C{k} + D{k}",
            "tolerance": 0.01,
            "locator": "intent scope_exclusions: 'the pool is conserved over the horizon' "
            * 2,
            "why": "The pool only interconverts between its forms; its total is fixed by construction. "
            * 3,
            "condition": f"cond_{j}",
            "at_t0": 1.0,
            "worst": 1.0 + (0.03 if (k == 4 and j == 0) else 1e-6),
            "at_time": 50.0,
            "drift": 0.03 if (k == 4 and j == 0) else 1e-6,
            "within_tolerance": not (k == 4 and j == 0),
        }
        for k in range(5)
        for j in range(n_cond)
    ]
    return {
        "intent": "does the neighbour term earn its parameter?",
        "report_core": {
            "goal": "mechanism_discrimination",
            "declared_constants": {
                "declared": 5,
                "measured": 5,
                "unmeasured": 0,
                "violated": 1,
                "worst_drift": 0.03,
                "rows": constants,
            },
            "discrimination": {
                "winner": "M1",
                "candidates": [
                    {"id": f"M{c}", "aic": 100.0 + c, "delta_aic": float(c)}
                    for c in range(1, n_cand + 1)
                ],
                "comparability": {
                    "shared_transformation": True,
                    "correction_applied": False,
                    "per_candidate": per_candidate,
                },
            },
            "prediction_uncertainty": {
                "method": "profile-skeleton",
                "bands_summary": bands,
                "bands_note": payload.BANDS_NOTE,
            },
            "attribution": {
                "available": True,
                "winner": "M1",
                "full_record": "attribution",
                "rivals": rivals,
            },
        },
        "residual_diagnostics": {
            "per_candidate_residuals": residuals,
            # the selected model's and the base's residual forms: one row per
            # series, one sentence per observable
            "residual_forms": {
                "per_series": [
                    {
                        "model": model,
                        "series": label,
                        "form": "exponential",
                        "direction": "decay",
                        "timescales": [30.0 + k],
                        "amplitude": 2.5,
                        "amplitude_units": "sigma",
                        "peak_time": None,
                        "r2": 0.8,
                        "n": 12,
                        "delta_aicc_vs_constant": 9.1,
                    }
                    for model in ("M1", "M2")
                    for k, label in enumerate(labels)
                ],
                "summary": [
                    f"M1 (selected): residual of obs_{i}: exponential decay, τ "
                    f"30–40 in cond_0, cond_1; amplitude 2–3 σ (2 series)."
                    for i in range(n_obs)
                ],
                "how_to_read_this": "the residual's form, grouped",
            },
            "how_to_read_this": "read the SHAPE",
        },
    }


def test_a_payload_under_the_cap_is_untouched() -> None:
    """A payload that never crosses the cap cannot tell the budget exists."""
    core = payload.core_for_agents(synthetic_core())
    context = {"intent": "q", "report_core": core}
    spec = StubSpec(5_000_000)
    plain = build_prompt("interpretation", context, spec)
    budgeted, out_ctx, trims = build_prompt_within_budget(
        "interpretation", context, spec
    )
    check(
        "the prompt is byte-identical to the one built without the budget",
        budgeted == plain,
        f"{len(budgeted.encode()):,} vs {len(plain.encode()):,} bytes",
    )
    check("no trims are claimed", trims == [], str(trims))
    check(
        "and the caller's own context object comes back, unmutated and uncopied",
        out_ctx is context and "bands_summary" in core["prediction_uncertainty"],
    )
    check(
        "no trim mark reached the payload",
        payload.TRIM_MARK not in budgeted,
    )


def test_the_degrade_order_is_the_declared_one() -> None:
    """Over a range of caps, the steps taken are a prefix of `PAYLOAD_BUDGET`."""
    # 14 candidates, so candidate detail (floor 6) has something to remove
    context = degradable_context(n_cand=14)
    declared = [name for name, _floor in payload.PAYLOAD_BUDGET]
    full = len(build_prompt("interpretation", context, StubSpec(10**9)).encode())
    taken_per_cap = []
    # 0.03 is below what every other step leaves, so the last step (the
    # residual-form sentences) is reached too
    for fraction in (0.98, 0.9, 0.75, 0.6, 0.45, 0.3, 0.15, 0.08, 0.03):
        cap = int(full * fraction)
        prompt, _ctx, trims = build_prompt_within_budget(
            "interpretation", context, StubSpec(cap)
        )
        steps = [t["step"] for t in trims]
        taken_per_cap.append((cap, steps, len(prompt.encode())))
        check(
            f"at cap {cap:,} the steps taken are the declared order's first "
            f"{len(steps)}",
            steps == declared[: len(steps)],
            f"{steps} vs {declared}",
        )
        check(
            f"and every step at cap {cap:,} reports bytes that only went down",
            all(t["bytes_after"] <= t["bytes_before"] for t in trims),
            str([(t["bytes_before"], t["bytes_after"]) for t in trims]),
        )
    counts = [len(s) for _c, s, _n in taken_per_cap]
    check(
        "a tighter cap never takes fewer steps",
        counts == sorted(counts),
        str(counts),
    )
    check(
        "the tightest cap here takes every declared step",
        counts[-1] == len(declared),
        f"{counts[-1]} of {len(declared)}: {taken_per_cap[-1][1]}",
    )
    check(
        "and after six degrades the CALLER's context is untouched — the "
        "interpreter reuses it for the diagnostics loop and the consistency "
        "retry, and evaluation_core in the record is built from the same objects",
        len(build_prompt("interpretation", context, StubSpec(10**9)).encode()) == full,
        f"{full:,} bytes",
    )


def test_every_degraded_block_says_so_and_names_the_way_back() -> None:
    """Every shortened block says so in the prompt text the agent reads."""
    context = degradable_context()
    full = len(build_prompt("interpretation", context, StubSpec(10**9)).encode())
    prompt, _ctx, trims = build_prompt_within_budget(
        "interpretation", context, StubSpec(int(full * 0.3))
    )
    check("all seven steps ran on this payload", len(trims) == 7, str(len(trims)))
    for key in (
        "per_series_trimmed",
        "constants_trimmed",
        "bands_trimmed",
        "residuals_trimmed",
        "rivals_trimmed",
        "tables_trimmed",
        "rival_residuals_trimmed",
    ):
        check(f"the payload carries {key}", f'"{key}"' in prompt)
    check(
        "every step's notice carries the one mark an agent can search for",
        prompt.count(payload.TRIM_MARK) == 7,
        f"{prompt.count(payload.TRIM_MARK)} occurrence(s)",
    )
    forms = _ctx["residual_diagnostics"]["residual_forms"]
    check(
        "the residual-form rows went FIRST and the sentences stayed: the "
        "summary states the rows, and the notice names the request that fits "
        "one series back",
        "per_series" not in forms
        and len(forms["summary"]) == 8
        and payload.FORM_REQUEST in prompt
        and trims[0]["step"] == "residual_form_rows",
        f"{sorted(forms)}; first step {trims[0]['step']}",
    )
    # the rivals' summaries go, the selected model's stay
    dets = _ctx["residual_diagnostics"]["per_candidate_residuals"]
    check(
        "the selected model keeps its residual summaries through every step; "
        "the rivals keep one number per series",
        "per_series" in dets["M1"]
        and all(
            "per_series" not in dets[c] and dets[c].get("other_series_rmse")
            for c in ("M2", "M3", "M4")
        ),
        str({c: sorted(d) for c, d in dets.items()}),
    )
    check(
        "the residual notice names the request that fetches a series back, "
        "by name and with its arguments",
        payload.CURVE_REQUEST in prompt,
        payload.CURVE_REQUEST,
    )
    check(
        "each shortened rival table says how many of how many terms it kept",
        prompt.count('"contributions_trimmed"') == 3,
        f"{prompt.count('\"contributions_trimmed\"')} rival(s)",
    )
    check(
        "the selection table survives every step — it is the answer the round "
        "exists to produce",
        '"candidates"' in prompt and '"delta_aic"' in prompt,
    )
    check(
        "every dropped residual series still carries its rank statistic, so "
        "the agent can see it exists and how bad it is",
        '"other_series_rmse"' in prompt,
    )


def test_a_step_with_nothing_to_remove_claims_nothing() -> None:
    """A halving step at or below its floor writes no ledger row and no notice."""
    context = degradable_context(n_obs=4, n_cond=1, n_cand=2, n_terms=3)
    full = len(build_prompt("interpretation", context, StubSpec(10**9)).encode())
    prompt, _ctx, trims = build_prompt_within_budget(
        "interpretation", context, StubSpec(int(full * 0.3))
    )
    steps = [t["step"] for t in trims]
    check(
        "4 observables against a floor of 4 leaves the residual step nothing "
        "to remove, and it says nothing",
        "residual_series" not in steps and '"residuals_trimmed"' not in prompt,
        str(steps),
    )
    check(
        "3 attribution terms against a floor of 3 likewise",
        "attribution_rivals" not in steps and '"rivals_trimmed"' not in prompt,
        str(steps),
    )
    check(
        "4 residual-form sentences against a floor of 4 likewise",
        "residual_form_summary" not in steps and '"summary_trimmed"' not in prompt,
        str(steps),
    )
    check(
        "while the one-shot steps, which have no floor, still collapse",
        steps
        == [
            "residual_form_rows",
            "declared_constants",
            "prediction_bands",
            "discrimination_tables",
            "rival_residuals",
        ],
        str(steps),
    )


def test_the_archived_over_cap_payload_now_fits() -> None:
    """An archived over-cap prompt (machine-local, read-only) fits once rebuilt through the budget."""
    text = _archived_prompt()
    if text is None:
        skip(
            "the archived live_ctd_positional_1 S7 payload fits the cap",
            f"neither {ARCHIVED_PROMPT.relative_to(REPO)} nor "
            f"runs/{ARCHIVED_RUN}.h5::{ARCHIVED_KEY} is on this machine "
            f"(runs/ is gitignored)",
        )
        return
    check(
        "the archive is the 453,497-byte prompt the run was refused on",
        len(text.encode()) == LIVE_PROMPT_BYTES,
        f"{len(text.encode()):,} bytes",
    )
    head, context, tail = _split_prompt(text)

    def render(ctx: dict) -> str:
        parts = [head, "\n\n# Inputs\n"]
        for key, value in ctx.items():
            parts.append(f"\n## {key}\n")
            parts.append(
                value
                if isinstance(value, str)
                else "```json\n" + json.dumps(value, indent=2, default=str) + "\n```"
            )
        parts.append(tail)
        return "".join(parts)

    check(
        "and it round-trips: the parsed context renders back to the same bytes",
        len(render(context).encode()) == LIVE_PROMPT_BYTES,
        f"{len(render(context).encode()):,} bytes",
    )
    prompt, _ctx, trims = payload.fit_to_budget(context, StubSpec(LIVE_CAP), render)
    n = len(prompt.encode())
    check(
        f"rebuilt through the budget it lands under the {LIVE_CAP:,}-byte cap",
        n <= LIVE_CAP,
        f"{n:,} bytes ({n / LIVE_PROMPT_BYTES:.0%} of what was refused)",
    )
    steps = [t["step"] for t in trims]
    declared = [name for name, _f in payload.PAYLOAD_BUDGET]
    check(
        "and it took every applicable declared step, in the declared order, to get there",
        steps == [name for name in declared if name in steps]
        and {
            "prediction_bands",
            "residual_series",
            "attribution_rivals",
            "discrimination_tables",
        }
        <= set(steps),
        str([(t["step"], t["bytes_before"], t["bytes_after"]) for t in trims]),
    )
    for key in (
        "bands_trimmed",
        "residuals_trimmed",
        "rivals_trimmed",
        "tables_trimmed",
    ):
        check(f"the rebuilt TEXT carries {key}", f'"{key}"' in prompt)
    check(
        "the rebuilt TEXT tells the agent it may ask for a series by name",
        payload.CURVE_REQUEST in prompt and payload.TRIM_MARK in prompt,
    )
    check(
        "the winner and its selection table survive the whole budget",
        "M5_neighbour_dir" in prompt and '"candidates"' in prompt,
    )
    check(
        "the profile intervals — the run's actual finding — are untouched",
        '"ci_finite"' in prompt,
    )


def _split_prompt(text: str) -> tuple[str, dict, str]:
    """An archived prompt back into (skill text, context, contract), undoing `build_prompt`."""
    import re

    marker = "\n\n# Inputs\n"
    i = text.index(marker)
    rest = text[i + len(marker) :]
    j = rest.index("\n\n# Output contract\n")
    head, body, tail = text[:i], rest[:j], rest[j:]
    parts = re.split(r"\n## (\w[\w.]*)\n", "\n" + body)
    context: dict = {}
    for key, raw in zip(parts[1::2], parts[2::2], strict=True):
        raw = raw.strip()
        context[key] = (
            json.loads(raw[len("```json") :].rsplit("```", 1)[0])
            if raw.startswith("```json")
            else raw
        )
    return head, context, tail


def test_every_trim_is_ledgered_and_read_back_by_a_human_document() -> None:
    """Every trim is ledgered and read back for the human in `decisions_md`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = record_at(Path(tmp) / "run")  # the run is one record file
        stubs = REPO / "testcase" / "toy_phos" / "stubs"
        if not stubs.exists():  # pragma: no cover - fixture guard
            check("toy_phos stubs are present", False, str(stubs))
            return
        r0 = rnd(tmp, 0)
        ledger = Ledger(tmp)
        # 14 candidates, so candidate detail (floor 6) has something to remove
        context = degradable_context(n_cand=14)
        # the cap this payload degrades exactly to: at cap 1 every step runs and
        # stops at its floor, so that size exercises the whole order and still fits
        floor_prompt, _c, _t = build_prompt_within_budget(
            "interpretation", context, StubSpec(1)
        )
        cap = len(floor_prompt.encode())
        call_agent(
            "interpretation",
            context,
            spec=StubSpec(cap),
            backend="stub",
            calls=r0 / "agent_calls",
            ledger=ledger,
            module="evaluation",
            stubs_dir=stubs,
        )
        rows = ledger.entries()
        trims = [r for r in rows if r.get("event") == "payload_trimmed"]
        check(
            "one payload_trimmed row per degrade step, each naming what it did "
            "and the bytes before and after",
            len(trims) == len(payload.PAYLOAD_BUDGET)
            and all(
                r.get("what")
                and r.get("role") == "interpretation"
                and r["bytes_before"] >= r["bytes_after"]
                for r in trims
            ),
            str(
                [
                    (r.get("step"), r.get("bytes_before"), r.get("bytes_after"))
                    for r in trims
                ]
            ),
        )
        check(
            "the degraded payload passed the gate — the run continues instead "
            "of ending at its last step",
            [r for r in rows if r.get("gate_id") == "agent_prompt_bytes"][0]["passed"],
        )
        check(
            "and the call happened",
            len([r for r in rows if r.get("event") == "agent_call"]) == 1,
        )
        prompt_recorded = (
            (r0 / "agent_calls").child("interpretation") / "prompt"
        ).text()
        check(
            "the prompt in the record is the DEGRADED one — the evidence is what "
            "was actually sent",
            len(prompt_recorded.encode()) <= cap
            and payload.TRIM_MARK in prompt_recorded,
            f"{len(prompt_recorded.encode()):,} bytes vs cap {cap:,}",
        )

        md = render.decisions_md(r0)
        check(
            "decisions_md reads those rows back for the human",
            "payload budget" in md.lower() and all(str(r["step"]) in md for r in trims),
            md[md.lower().find("payload budget") :][:200] or "(no section)",
        )


def test_the_order_and_the_floors_are_one_declared_table() -> None:
    """No step in the order lacks code behind it, and no step's code is unreachable."""
    names = [name for name, _floor in payload.PAYLOAD_BUDGET]
    check(
        "every step in the declared order has an implementation",
        set(names) == set(payload._STEPS),
        f"{names} vs {sorted(payload._STEPS)}",
    )
    check(
        "the order has no duplicates — a step that ran twice would report two "
        "different 'before' sizes for one block",
        len(names) == len(set(names)),
        str(names),
    )
    check(
        "every floor is a non-negative int (0 = one-shot, nothing to halve)",
        all(isinstance(f, int) and f >= 0 for _n, f in payload.PAYLOAD_BUDGET),
        str(payload.PAYLOAD_BUDGET),
    )
    src = (REPO / "octomod" / "agents" / "payload.py").read_text()
    check(
        "the constant names the spec key it is waiting to become, so the open "
        "item cannot be lost",
        "agents.payload_budget" in src and "TODO: declare this under" in src,
    )
    declared = [
        (
            yaml.safe_load((REPO / "workflows" / name).read_text()).get("agents") or {}
        ).get("payload_budget")
        for name in ("default.yaml", "test_redraft.yaml")
    ]
    check(
        "and no spec declares it yet — the item is open ON PURPOSE: a new "
        "yaml key moves workflow_sha and would lock a paused run out of its "
        "re-entry (delete this check when the key lands)",
        declared == [None, None],
        str(declared),
    )


# measured on the full battery (the ledger's own prompt_bytes)
MEASURED_LARGEST = 128_171  # interpretation on search_smoke
REGRESSION_INTERPRETER = 426_717  # an oversized interpreter payload the cap must refuse
REGRESSION_REVISION = 310_028  # an oversized revision payload the cap must refuse


HISTORICAL_CAP = 250_000  # the argued cap, checked when default.yaml declares none


def test_the_cap_is_bounded_from_both_sides() -> None:
    """The cap clears the largest legitimate prompt and still refuses both oversized ones."""
    declared = payload.prompt_cap(
        WorkflowSpec.load(REPO / "workflows" / "default.yaml")
    )
    check(
        "the default declares a cap, or none at all (null) — never a text value",
        declared is None or isinstance(declared, int),
        str(declared),
    )
    cap = HISTORICAL_CAP if declared is None else declared
    check(
        "the cap clears the largest legitimate prompt with real headroom — "
        "residual curves and attribution both scale with candidates x points",
        cap >= 1.5 * MEASURED_LARGEST,
        f"cap {cap:,} vs measured {MEASURED_LARGEST:,} ({cap / MEASURED_LARGEST:.2f}x)",
    )
    check(
        "and still refuses both payloads it exists to catch",
        cap < REGRESSION_REVISION and cap < REGRESSION_INTERPRETER,
        f"cap {cap:,} vs {REGRESSION_REVISION:,} (revision) and "
        f"{REGRESSION_INTERPRETER:,} (interpreter)",
    )


def test_the_cost_gate_line_is_measured_not_projected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Ledger(record_at(Path(tmp) / "run"))
        spec = StubSpec(150_000)
        line = payload.cost_gate_line(ledger, spec)
        check(
            "before any agent call the line says so rather than showing a zero",
            "no agent call yet" in line and "150,000" in line,
            line,
        )
        ledger.append("agent_call", role="construction", prompt_bytes=40_000)
        ledger.append("agent_call", role="interpretation", prompt_bytes=9_000)
        line = payload.cost_gate_line(ledger, spec)
        check(
            "afterwards it names the count, the total and the largest role",
            "2 call(s)" in line and "49,000" in line and "construction" in line,
            line,
        )


def main() -> int:
    print("prompt payload — the view, the budget, and the cap on the call\n")
    test_the_view_keeps_the_reading_and_drops_the_curve()
    test_the_band_summary_is_arithmetically_what_it_claims()
    test_a_core_without_the_heavy_keys_is_returned_unchanged()
    test_a_number_is_reported_to_the_precision_it_has()
    test_a_per_point_block_becomes_aligned_columns()
    test_the_column_convention_is_stated_once()
    test_nothing_is_lost_and_the_artifact_is_untouched()
    test_a_payload_under_the_cap_is_untouched()
    test_the_degrade_order_is_the_declared_one()
    test_every_degraded_block_says_so_and_names_the_way_back()
    test_a_step_with_nothing_to_remove_claims_nothing()
    test_the_archived_over_cap_payload_now_fits()
    test_every_trim_is_ledgered_and_read_back_by_a_human_document()
    test_the_order_and_the_floors_are_one_declared_table()
    test_the_gate_reports_where_the_bytes_are()
    test_the_cap_is_enforced_on_the_call_not_merely_computed()
    test_the_default_lives_in_one_place_with_one_value()
    test_no_cap_trims_nothing_and_still_records_the_size()
    test_the_cap_is_bounded_from_both_sides()
    test_the_cost_gate_line_is_measured_not_projected()

    print()
    if FAILS:
        print(f"PROMPT BUDGET FAILED — {len(FAILS)} check(s):")
        for f in FAILS:
            print(f"  · {f}")
        return 1
    if SKIPPED:
        print(f"({len(SKIPPED)} check(s) SKIPPED for a missing fixture:)")
        for s in SKIPPED:
            print(f"  · {s}")
    print(
        "PROMPT BUDGET OK — the view keeps the reading; the payload degrades "
        "in the declared order; the cap stops what will not fit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
