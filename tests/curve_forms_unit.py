"""The functional-form library, the residual sentences and the data phenomenology.

  1. a planted exponential is named, with its τ within 20 %;
  2. pure noise reads as the constant;
  3. a planted rise-and-fall is named, τ1 < τ2, both τ recovered;
  4. too few points return the constant with a note, and 4 points try no peak;
  5. three residuals with agreeing timescales group into one sentence, the
     fourth is named as disagreeing, and a dose-scaled amplitude is said;
  6. `residual_forms` reaches the expansion payload and the interpreter's, is
     written beside the report, and is trimmed rows first, sentences last;
  7. toy_phos's own table reads as rising curves that plateau, larger at the
     higher dose, with the held-out dose not described and no value in sight;
  8. construction is granted those sentences and still refused every value,
     and the compile card prints them;
  9. toy_phos's raw csv, read before any table exists, gives the curated
     table's sentences for the same series, the held-out dose excluded;
 10. every acceptance rule rejects by name, and a holdout that does not
     resolve against the raw columns produces nothing at all;
 11. on the run's seams: the raw reading is written and ledgered once, is
     construction's view until S2's exists, puts one line on the intent card
     (a rejection too), and after S2 is checked against the curated reading,
     ledgered, and put on the compile card, agreeing or not;
 12. a stub run of toy_phos shows the raw reading on the intent card and in
     the round-0 construction prompt, writes and ledgers the phenomenology at
     S2, shows it and the raw reading's agreement on the compile card, and
     ends with residual forms in the interpreter's prompt and a residual-shape
     line in the report.

    uv run python tests/curve_forms_unit.py
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402
from _record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    reports_dir,
    rnd,
    run_root,
    temp_record,
)

from octomod.agents import (  # noqa: E402
    build_prompt,
    payload,
    routing,  # noqa: E402
)
from octomod.workflow_modules.data import curve_forms as cf  # noqa: E402
from octomod.workflow_modules.data import data_signals, phenomenology  # noqa: E402
from octomod.workflow_modules.evaluation import residuals  # noqa: E402

T = np.arange(0.0, 121.0, 10.0)
TT = np.repeat(T, 2)  # two replicates per time point
T8 = np.array([0, 5, 15, 30, 50, 75, 100, 120], dtype=float)


def rng(seed: int = 4242):
    return np.random.default_rng(seed)


# ---------------------------------------------------------------- the library


def test_planted_exponential() -> None:
    r = rng()
    n, form_ok, within = 30, 0, 0
    taus, amps = [], []
    for _ in range(n):
        y = 8.0 * np.exp(-TT / 40.0) + r.normal(0.0, 0.3, len(TT))
        f = cf.fit_series(TT, y, sigma=0.3)
        form_ok += f["form"] == "exponential" and f["direction"] == "decay"
        amps.append(f["amplitude"])
        if f["timescales"]:
            taus.append(f["timescales"][0])
            within += abs(f["timescales"][0] - 40.0) / 40.0 <= 0.2
    check(
        "a planted exponential decay is named in at least 90 % of realisations",
        form_ok >= 0.9 * n,
        f"{form_ok}/{n}",
    )
    check(
        "and its τ is within 20 % of the planted 40 in at least 90 % of them",
        within >= 0.9 * n,
        f"{within}/{n}, median τ {np.median(taus):.1f}",
    )
    check(
        "its amplitude is the planted 8 in units of σ = 0.3 (within 20 %)",
        abs(np.median(amps) - 8.0 / 0.3) <= 0.2 * 8.0 / 0.3,
        f"median amplitude {np.median(amps):.1f} σ",
    )
    rise = cf.fit_series(
        TT, 5.0 - 5.0 * np.exp(-TT / 20.0) + r.normal(0, 0.2, len(TT)), 0.2
    )
    check(
        "a rising exponential reads as a rise, amplitude signed and in σ units",
        rise["form"] == "exponential"
        and rise["direction"] == "rise"
        and rise["amplitude"] < 0
        and rise["amplitude_units"] == "sigma",
        f"{rise['form']} {rise['direction']} amplitude {rise['amplitude']}",
    )


def test_the_simpler_form_stands() -> None:
    """Each step up in complexity must beat the form chosen before it by the
    margin, not only the constant."""
    m = cf.MIN_DELTA_AICC
    cases = [
        ({"constant": 100.0, "linear": 99.0, "exponential": 98.5}, "constant"),
        ({"constant": 100.0, "linear": 60.0, "exponential": 60.0 - m / 2}, "linear"),
        (
            {
                "constant": 100.0,
                "linear": 90.0,
                "exponential": 50.0,
                "rise_and_fall": 49.0,
            },
            "exponential",
        ),
        (
            {
                "constant": 100.0,
                "linear": 90.0,
                "exponential": 50.0,
                "rise_and_fall": 40.0,
            },
            "rise_and_fall",
        ),
        ({"constant": 100.0, "linear": None, "exponential": 80.0}, "exponential"),
        ({"constant": None, "linear": 10.0}, "constant"),
    ]
    got = [(cf.choose(scores), want) for scores, want in cases]
    check(
        "a more complex form displaces the simpler one only by the AICc margin",
        all(g == w for g, w in got),
        str(got),
    )


def test_noise_reads_as_constant() -> None:
    r = rng(7)
    for label, t, sigma in (
        ("8 samples, σ known", T8, 1.0),
        ("8 samples, σ profiled", T8, None),
        ("13 x 2 samples, σ known", TT, 1.0),
    ):
        n = 200
        forms = [
            cf.fit_series(t, r.normal(0.0, 1.0, len(t)), sigma)["form"]
            for _ in range(n)
        ]
        const = forms.count("constant")
        check(
            f"pure noise reads as the constant ({label}) in at least 90 %",
            const >= 0.9 * n,
            f"{const}/{n}; otherwise {sorted(set(forms) - {'constant'})}",
        )


def test_planted_rise_and_fall() -> None:
    r = rng(11)
    n, ok = 30, 0
    t1s, t2s = [], []
    for _ in range(n):
        y = 6.0 * (np.exp(-TT / 60.0) - np.exp(-TT / 15.0)) + r.normal(0, 0.3, len(TT))
        f = cf.fit_series(TT, y, sigma=0.3)
        if f["form"] == "rise_and_fall" and f["direction"] == "peak":
            ok += 1
            t1, t2 = f["timescales"]
            t1s.append(t1)
            t2s.append(t2)
    check(
        "a planted rise-and-fall is named as a peak in at least 90 % of realisations",
        ok >= 0.9 * n,
        f"{ok}/{n}",
    )
    check(
        "with τ1 < τ2 in every one",
        all(a < b for a, b in zip(t1s, t2s, strict=True)),
        f"{list(zip(t1s, t2s, strict=True))[:3]} …",
    )
    check(
        "and both median τ within 20 % of the planted 15 and 60",
        abs(np.median(t1s) - 15) / 15 <= 0.2 and abs(np.median(t2s) - 60) / 60 <= 0.2,
        f"median τ1 {np.median(t1s):.1f}, τ2 {np.median(t2s):.1f}",
    )
    f = cf.fit_series(TT, 6.0 * (np.exp(-TT / 60.0) - np.exp(-TT / 15.0)), 0.3)
    sh = cf.shape(f)
    check(
        "its shape: a half-maximum before the peak, the peak inside the window",
        sh["rise_half_time"] is not None
        and sh["rise_half_time"] < sh["peak_time"] < 120
        and sh["returns_toward_baseline"] is True,
        f"half {sh['rise_half_time']}, peak {sh['peak_time']}",
    )


def test_too_few_points() -> None:
    f3 = cf.fit_series([0, 10, 20, 0, 10, 20], [0, 5, 9, 0.5, 5.5, 8.5])
    check(
        "three time points return the constant, with a note that says why",
        f3["form"] == "constant" and "too few" in (f3["note"] or ""),
        str(f3["note"]),
    )
    f4 = cf.fit_series(
        np.repeat([0.0, 10.0, 20.0, 40.0], 3),
        np.repeat([0.0, 6.0, 9.0, 9.9], 3) + rng(3).normal(0, 0.1, 12),
        0.1,
    )
    check(
        "four time points try an exponential but never a rise-and-fall, and say so",
        "rise_and_fall" not in f4["aicc"]
        and "rise-and-fall needs 5" in (f4["note"] or ""),
        f"{f4['form']}; {f4['note']}",
    )


# -------------------------------------------------------------- aggregation


def _row(obs, cond, attrs, fit, early="above"):
    return {
        "observable": obs,
        "condition": cond,
        "attributes": attrs,
        "fit": fit,
        "early_sign": early,
    }


def test_aggregation_sentence() -> None:
    r = rng(5)
    rows = []
    for pop, tau, dose, amp in (
        ("B", 30.0, "1", 3.0),
        ("NK", 40.0, "3", 5.0),
        ("CD4T", 50.0, "10", 8.0),
    ):
        y = amp * np.exp(-TT / tau) + r.normal(0, 0.3, len(TT))
        rows.append(
            _row(
                "pSTAT1",
                f"c_{pop}",
                {"stimulus": "IFNa", "population": pop, "dose": dose},
                cf.fit_series(TT, y, 0.3),
            )
        )
    drift = 0.04 * TT + r.normal(0, 0.3, len(TT))
    rows.append(
        _row(
            "pSTAT1",
            "c_Mono",
            {"stimulus": "IFNa", "population": "Mono", "dose": "1"},
            cf.fit_series(TT, drift, 0.3),
        )
    )
    forms = [r["fit"]["form"] for r in rows]
    check(
        "the fixture's series read as planted",
        forms == ["exponential"] * 3 + ["linear"],
        str(forms),
    )
    [(weight, text)] = cf.aggregate_residuals(rows, "M1 (selected)")
    print(f"    {text}")
    check(
        "one sentence for the stratum, the three agreeing series leading it",
        text.startswith(
            "M1 (selected): residual of pSTAT1 under stimulus=IFNa: exponential "
            "decay in population B, CD4T, NK"
        )
        and "(3 series)" in text,
        text,
    )
    span = re.search(r"τ (\d+)–(\d+)", text)
    check(
        "their timescales stated as the span of the group, within the factor of two",
        span is not None and int(span.group(2)) <= 2 * int(span.group(1)),
        text,
    )
    check(
        "the disagreeing series is named, with its own form and where it sits",
        "disagrees: linear drift upward in population Mono at dose 1" in text,
        text,
    )
    check(
        "the amplitude is in σ units and its growth with dose is said",
        " σ" in text and "larger at higher dose" in text,
        text,
    )
    check("the weight is the largest shaped amplitude", weight > 10, str(weight))
    # a factor-two rule, not "same form": τ 5 does not join τ 40
    fast = copy.deepcopy(rows[:2])
    fast[1]["fit"] = cf.fit_series(
        TT, 5.0 * np.exp(-TT / 12.0) + r.normal(0, 0.3, len(TT)), 0.3
    )
    groups = cf.clusters(fast)
    check(
        "two decays whose τ differ by more than a factor of two are two groups",
        len(groups) == 2,
        str([[g2["fit"]["timescales"] for g2 in g] for g in groups]),
    )


# -------------------------------------------------- the residual payloads


class _Spec:
    def get(self, key, default=None):
        return default

    def require(self, key):
        raise KeyError(key)


class _Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event, **kw):
        self.rows.append({"event": event, **kw})

    def entries(self):
        return list(self.rows)


class _Tables:
    def __init__(self, meas: pd.DataFrame, sim):
        self.measurements = meas
        self._sim = sim

    def simulate_observables(self, cond_id, times, param_override=None):
        return {"y": self._sim(cond_id, np.asarray(times, float))}


def _fake_round(root):
    """A fitted two-candidate round: three populations share one planted
    residual decay, the fourth drifts instead."""
    r = rng(17)
    pops = {"B": (4.0, 40.0), "NK": (5.0, 35.0), "CD4T": (4.5, 45.0), "Mono": None}
    rows, long_rows, conds = [], [], []
    for pop, planted in pops.items():
        cid = f"c_{pop}"
        label = f"stimulus=IFNa, population={pop}"
        conds.append({"condition_id": cid, "maps_to_label": label})
        for t in TT:
            base = 10.0 * (1 - np.exp(-t / 20.0))
            extra = planted[0] * np.exp(-t / planted[1]) if planted else 0.03 * t
            v = base + extra + r.normal(0, 0.3)
            rows.append(
                {
                    "observableId": "y",
                    "simulationConditionId": cid,
                    "time": t,
                    "measurement": v,
                }
            )
            long_rows.append(
                {
                    "observable_label": "y",
                    "condition_label": label,
                    "condition_key": f"population={pop}|stimulus=IFNa",
                    "time": t,
                    "value": v,
                }
            )
    meas = pd.DataFrame(rows)
    (rnd(root, 0) / "data/measurements").put_table(pd.DataFrame(long_rows))

    class F:
        def __init__(self, cid):
            self.cid = cid
            self.tables = _Tables(meas, lambda c, t: 10.0 * (1 - np.exp(-t / 20.0)))
            self.best = {"k": 1.0}
            self.assembly = {"conditions": conds, "observables": []}
            self.long_df = None

        def misfit_evidence(self, spec, fit=None):
            return {
                "signals": {
                    "sigma_vs_floor": [
                        {"observable": "y", "sigma_replicate": 0.3, "ratio": 1.0}
                    ]
                }
            }

    class Ctx:
        spec = _Spec()
        ledger = _Ledger()
        round_idx = 0

    ctx = Ctx()
    ctx.root = root
    ctx.round = rnd(root, 0)
    return ctx, F


def test_residual_forms_reach_both_agents() -> None:
    from octomod.workflow_modules.evaluation import engine as evaluation_module
    from octomod.workflow_modules.evaluation import fitted

    with temp_record("curve_forms") as root:
        ctx, F = _fake_round(root)
        real = fitted.load
        fitted.load = lambda ctx, cid, long_df=None: F(cid)
        try:
            diag = residuals.expansion_payload(ctx, ["M1", "M1_fb"], "M1_fb", core={})
            interp = evaluation_module._interpreter_residuals(
                ctx, {"discrimination": {"winner": "M1_fb"}}, ["M1", "M1_fb"]
            )
        finally:
            fitted.load = real
        forms = diag.get("residual_forms") or {}
        summary = forms.get("summary") or []
        print("    " + "\n    ".join(summary))
        check(
            "the expansion payload carries residual_forms: a row per series of "
            "the selected model and of the base",
            len(forms.get("per_series") or []) == 8
            and {r["model"] for r in forms["per_series"]} == {"M1", "M1_fb"},
            str(len(forms.get("per_series") or [])),
        )
        check(
            "the selected model's sentence comes first and groups the three "
            "agreeing populations, naming the drifting one",
            summary
            and summary[0].startswith(
                "M1_fb (selected): residual of y under stimulus=IFNa"
            )
            and "exponential decay" in summary[0]
            and "population B, CD4T, NK" in summary[0]
            and "disagrees: linear drift upward" in summary[0],
            summary[0] if summary else "(none)",
        )
        check(
            "the base's sentence follows it",
            len(summary) == 2 and summary[1].startswith("M1 (base)"),
            str(summary[1:]),
        )
        check(
            "the interpreter's residual payload carries the same block",
            (interp.get("residual_forms") or {}).get("summary") == summary,
        )
        on_disk = (rnd(root, 0) / residuals.RESIDUAL_FORMS_KEY).get({})
        check(
            "and S7 writes it beside the report, where the report line reads it",
            on_disk.get("summary") == summary,
        )
        agent_view = payload.for_agents(diag)
        check(
            "it survives the agent view",
            (agent_view.get("residual_forms") or {}).get("summary") == summary,
        )
        for role in ("interpretation", "revision"):
            routing.enforce(role, ["intent", "residual_diagnostics"])
        check("both roles are granted the block that carries it", True)

        # the declared degrade order: rows first, sentences last
        context = {"residual_diagnostics": copy.deepcopy(agent_view)}
        steps = [name for name, _floor in payload.PAYLOAD_BUDGET]
        check(
            "the per-series rows are the FIRST step of the declared order and "
            "the sentences the LAST",
            steps[0] == "residual_form_rows" and steps[-1] == "residual_form_summary",
            str(steps),
        )
        payload._trim_residual_form_rows(context, 0, lambda: False)
        block = context["residual_diagnostics"]["residual_forms"]
        check(
            "the rows step removes the rows, keeps the sentences, and names the "
            "request that fits one series back",
            "per_series" not in block
            and block["summary"] == summary
            and payload.FORM_REQUEST in block["per_series_trimmed"],
        )
        many = {"residual_forms": {"summary": [f"s{i}" for i in range(12)]}}
        payload._trim_residual_form_summary(many, 4, lambda: False)
        check(
            "the sentences step halves from the end down to its floor, the "
            "strongest (first) kept",
            many["residual_forms"]["summary"] == ["s0", "s1", "s2", "s3"]
            and payload.TRIM_MARK in many["residual_forms"]["summary_trimmed"],
            str(many["residual_forms"]["summary"]),
        )


# ------------------------------------------------------- data phenomenology


def _toy_phos_long() -> pd.DataFrame:
    from octomod.workflow_modules.data.engine import parse_declared_label

    raw = pd.read_csv(REPO / "testcase" / "toy_phos" / "data" / "timecourse.csv")
    labels = raw["dose"].map(lambda d: f"dose={d:g}")
    return pd.DataFrame(
        {
            "observable_label": "pR_au",
            "condition_label": labels,
            "condition_key": labels.map(parse_declared_label),
            "time": raw["time_min"],
            "value": raw["pR_au"],
            "replicate": raw["replicate"],
        }
    )


def _numbers_are_one_figure(sentences, allowed: set[str]) -> list[str]:
    """Every number in the sentences that is neither a condition label's value
    nor a one-significant-figure time."""
    bad = []
    for s in sentences:
        for tok in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", s):
            if tok in allowed:
                continue
            digits = tok.replace(".", "").strip("0")
            if len(digits) > 1:
                bad.append(tok)
    return bad


def _ctx(tmp: Path, root, holdout: list[str]):
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import RunContext
    from octomod.spec import WorkflowSpec

    (tmp / "input").mkdir(parents=True, exist_ok=True)
    (tmp / "input" / "testcase.yaml").write_text(
        "name: t\nholdout:\n  condition_labels: " + json.dumps(holdout) + "\n"
    )
    return RunContext(
        root=root,
        testcase_dir=tmp / "input",
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(root),
        backend="stub",
        auto=True,
    )


def test_toy_phos_phenomenology() -> None:
    long_df = _toy_phos_long()
    held = data_signals.held_out_keys(long_df, ["dose=3"])
    signals = data_signals.compute(long_df, held)
    ph = phenomenology.build(signals)
    sentences = ph["sentences"]
    print("    " + "\n    ".join(sentences))
    text = " ".join(sentences)
    check(
        "toy_phos's curves read as rises that plateau",
        len(sentences) == 1 and "rises" in text and "plateaus" in text,
        text,
    )
    check("and as larger at the higher dose", "larger at the higher dose" in text, text)
    check(
        "the held-out dose is not described, and the artifact says it was left out",
        "dose 3" not in text
        and "dose=3" not in text
        and ph["excluded_conditions"] == ["dose=3"],
        str(ph["excluded_conditions"]),
    )
    bad = _numbers_are_one_figure(sentences, {"0.3", "1", "3"})
    check(
        "no measurement value appears: every number is a condition label's "
        "value or a time at one significant figure",
        not bad,
        str(bad),
    )
    check(
        "the descriptors in the artifact carry no value either: shape words, "
        "one-figure times and buckets",
        not _numbers_are_one_figure([json.dumps(ph["descriptors"])], {"0.3", "1", "3"}),
        json.dumps(ph["descriptors"])[:200],
    )

    with tempfile.TemporaryDirectory() as tmp, temp_record("phenomenology") as root:
        ctx = _ctx(Path(tmp), root, ["dose=3"])
        check(
            "no table yet: construction is given nothing",
            phenomenology.for_construction(ctx) is None,
        )
        # a table staged before S1 (a revision round's carried data/, or a
        # supplied table) is described on the spot, the holdout excluded
        (ctx.round / "data/measurements").put_table(long_df)
        spot = phenomenology.for_construction(ctx)
        check(
            "a table already in the round is described before S2 writes the artifact",
            spot is not None and spot["sentences"] == sentences,
            str(spot),
        )
        written = phenomenology.write(ctx, signals)
        rows = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "data_phenomenology" and e.get("module") == "data"
        ]
        check(
            "S2 writes data/phenomenology into the record and ledgers it",
            phenomenology.node(ctx.round).exists()
            and len(rows) == 1
            and rows[0]["n_sentences"] == 1
            and rows[0]["excluded_conditions"] == ["dose=3"],
            str(rows),
        )
        view = phenomenology.for_construction(ctx)
        check(
            "construction's view is the sentences and how to read them, nothing else",
            set(view) == {"sentences", "how_to_read_this"}
            and view["sentences"] == written["sentences"],
            str(sorted(view)),
        )
        # the key passes the construction seam, and the prompt carries it
        routing.enforce(
            "construction", ["intent", "experiment_description", "data_phenomenology"]
        )
        prompt = build_prompt(
            "construction",
            {"intent": {"question": "q"}, "data_phenomenology": view},
            None,
        )
        check(
            "the construction prompt carries the sentences under data_phenomenology",
            "## data_phenomenology" in prompt and sentences[0] in prompt,
        )

        # the compile card prints them where the data flags print
        from octomod.workflow_modules.cost_probe import compile_gate

        lines = compile_gate.card_lines(ctx, [None])
        check(
            "the compile card carries the sentences beside the data flags",
            any("WHAT THE CURVES LOOK LIKE" in ln for ln in lines)
            and any(sentences[0] in ln for ln in lines),
            "\n".join(lines[:6]),
        )


def test_construction_still_blind_to_values() -> None:
    granted = routing.allowed("construction")
    check("construction is granted data_phenomenology", "data_phenomenology" in granted)
    refused = []
    for key in (
        "data_signals",
        "data_file_previews",
        "design_summary",
        "measurements_long",
        "residual_diagnostics",
    ):
        try:
            routing.enforce("construction", ["intent", key])
        except routing.RoutingViolation:
            refused.append(key)
    check(
        "and still refused every value-bearing key",
        len(refused) == 5,
        str(refused),
    )
    never = " ".join(routing.ROUTING["construction"]["never"])
    check(
        "its never rule still says measurement values stay out, and says why "
        "the descriptors are allowed",
        "measurement values" in never
        and "data_phenomenology" in never
        and "shape and timescale" in never
        and "into a fit" in never,
        never[:160],
    )
    others = [
        r
        for r in routing.ROUTING
        if r != "construction" and "data_phenomenology" in routing.allowed(r)
    ]
    check("no other role is handed it", not others, str(others))


# ------------------------------------ the raw-file reading, before construction

TOY_CSV = REPO / "testcase" / "toy_phos" / "data" / "timecourse.csv"


def _raw_data(tmp: Path, edit=None, name: str = "timecourse.csv") -> Path:
    """toy_phos's raw csv in a temporary data/ folder: copied byte for byte,
    or rewritten through `edit` (a DataFrame -> DataFrame)."""
    d = tmp / "data"
    d.mkdir(parents=True, exist_ok=True)
    if edit is None:
        shutil.copy(TOY_CSV, d / name)
    else:
        edit(pd.read_csv(TOY_CSV)).to_csv(d / name, index=False)
    return d


def _curated_toy_phos() -> dict:
    """What S2's path builds from toy_phos's table, the holdout excluded."""
    long_df = _toy_phos_long()
    held = data_signals.held_out_keys(long_df, ["dose=3"])
    return data_signals.compute(long_df, held)


def test_raw_reading_of_toy_phos() -> None:
    from octomod.workflow_modules.data import raw_phenomenology as raw

    curated = phenomenology.build(_curated_toy_phos())
    with tempfile.TemporaryDirectory() as tmp:
        rec = raw.derive(_raw_data(Path(tmp)), ["dose=3"])
    print("    " + "\n    ".join(rec.get("sentences") or [str(rec)]))
    check(
        "toy_phos's raw csv is accepted, every rule held, tagged as read from "
        "the raw files",
        rec.get("available") is True
        and rec.get("source") == "raw files"
        and rec.get("rules_held") == list(raw.RULES),
        str({k: rec.get(k) for k in ("available", "rule", "why")}),
    )
    check(
        "its sentences are the curated table's sentences for the same series",
        rec.get("sentences") == curated["sentences"],
        f"{rec.get('sentences')} vs {curated['sentences']}",
    )
    check(
        "and its descriptors are the curated ones, series by series",
        rec.get("descriptors") == curated["descriptors"],
    )
    check(
        "the held-out dose is left out, resolved by the S3 parser's "
        "column=value pairs against the raw column",
        rec.get("excluded_conditions") == ["dose=3"]
        and (rec.get("holdout") or {}).get("resolved") == {"dose=3": ["dose=3"]}
        and "dose 3" not in " ".join(rec.get("sentences") or []),
        str(rec.get("holdout")),
    )
    check(
        "no measurement value in the sentences or the descriptors",
        not _numbers_are_one_figure(
            list(rec.get("sentences") or []) + [json.dumps(rec.get("descriptors"))],
            {"0.3", "1", "3"},
        ),
    )
    check(
        "the file record names the columns and their roles, nothing else",
        rec.get("files")
        == {
            "timecourse.csv": {
                "time_column": "time_min",
                "measurement_columns": ["pR_au"],
                "design_columns": ["dose"],
                "replicate_column": "replicate",
            }
        },
        str(rec.get("files")),
    )


def _jitter(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time_min"] = df["time_min"] + np.arange(len(df)) * 1e-3
    return df


RAW_REJECTIONS = [
    # (what, edit, holdout, the rule named, a phrase of the reason)
    (
        "a file with two time-like columns",
        lambda df: df.assign(time_h=df["time_min"] / 60.0),
        ["dose=3"],
        "one_time_column",
        "2 time-like columns (time_min, time_h)",
    ),
    (
        "a file with 3 time points",
        lambda df: df[df["time_min"].isin([0.0, 5.0, 10.0])],
        ["dose=3"],
        "time_values",
        "has 3 distinct values",
    ),
    (
        "a series with 3 time points while the file has 6",
        lambda df: df[~((df["dose"] == 1.0) & (df["time_min"] >= 20.0))],
        ["dose=3"],
        "series_time_points",
        "pR_au under dose=1 has 3 distinct time point(s)",
    ),
    (
        "a readout that reads as time only through the `sec…` prefix",
        lambda df: df.rename(columns={"time_min": "timepoint", "pR_au": "secretion"}),
        [],
        "time_unambiguous",
        "secretion reads as time only through",
    ),
    (
        "a second time axis the pattern misses",
        lambda df: df.assign(timepoint=df["time_min"]),
        ["dose=3"],
        "time_unambiguous",
        "besides time_min, timepoint names a time too",
    ),
    (
        "a time column whose every row is its own value",
        _jitter,
        ["dose=3"],
        "time_unambiguous",
        "every row carries its own time_min value",
    ),
    (
        "a spread column beside the readout",
        lambda df: df.assign(pR_sd=0.5),
        ["dose=3"],
        "error_columns",
        "pR_sd reads as a spread",
    ),
    (
        "an identifier-like column",
        lambda df: df.assign(sample=[f"s{i}" for i in range(len(df))]),
        ["dose=3"],
        "design_levels",
        "sample has more than 16 levels",
    ),
    (
        "a holdout naming a column the file does not have",
        None,
        ["concentration=3"],
        "holdout_resolves",
        "names concentration, which is not a design column",
    ),
    (
        "a holdout matching no raw row",
        None,
        ["dose=5"],
        "holdout_resolves",
        "matches no raw row",
    ),
    (
        "a holdout with no column=value pair",
        None,
        ["high dose"],
        "holdout_resolves",
        "names no column=value pair",
    ),
]


def test_raw_rejections() -> None:
    from octomod.workflow_modules.data import raw_phenomenology as raw

    for what, edit, holdout, rule, phrase in RAW_REJECTIONS:
        with tempfile.TemporaryDirectory() as tmp:
            rec = raw.derive(_raw_data(Path(tmp), edit), holdout)
        check(
            f"{what}: nothing produced, rule {rule} named",
            rec.get("available") is False
            and rec.get("rule") == rule
            and phrase in str(rec.get("why"))
            and "sentences" not in rec
            and "descriptors" not in rec,
            f"{rec.get('rule')}: {rec.get('why')}",
        )
    with tempfile.TemporaryDirectory() as tmp:
        d = _raw_data(Path(tmp))
        shutil.copy(TOY_CSV, d / "again.csv")
        rec = raw.derive(d, ["dose=3"])
    check(
        "two files holding the same series: nothing produced, rule files_disjoint",
        rec.get("rule") == "files_disjoint" and "in 2 files" in str(rec.get("why")),
        f"{rec.get('rule')}: {rec.get('why')}",
    )
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "data").mkdir()
        rec = raw.derive(Path(tmp) / "data", [])
    check(
        "no data file: nothing produced, rule data_files",
        rec.get("rule") == "data_files",
        f"{rec.get('rule')}: {rec.get('why')}",
    )


def _raw_ctx(tmp: Path, root, holdout: list[str], edit=None):
    """A round-0 context on the record `root` whose input holds toy_phos's raw
    csv, with a frozen intent in the record."""
    ctx = _ctx(tmp, root, holdout)
    _raw_data(ctx.testcase_dir, edit)
    (root / "intent").put(
        {
            "question": "q",
            "system": "toy",
            "inference_target": "prediction",
            "domain_packs": ["general-dynamics"],
        }
    )
    return ctx


def _raw_rows(ctx) -> list[dict]:
    return [
        e
        for e in ctx.ledger.entries()
        if e.get("event") == "data_phenomenology" and e.get("source") == "raw files"
    ]


def test_raw_reading_on_the_run_seams() -> None:
    from octomod.workflow_modules.cost_probe import compile_gate
    from octomod.workflow_modules.data import raw_phenomenology as raw
    from octomod.workflow_modules.model import engine as model_module

    with tempfile.TemporaryDirectory() as tmp, temp_record("raw_seams") as root:
        ctx = _raw_ctx(Path(tmp), root, ["dose=3"])
        lines = raw.intent_card_lines(ctx)
        rec = raw.node(ctx.root).get()
        check(
            "accepted: the reading is written to the run-level phenomenology_raw "
            "and ledgered as data_phenomenology from the raw files",
            raw.node(ctx.root).key == "phenomenology_raw"
            and rec.get("available")
            and len(_raw_rows(ctx)) == 1
            and _raw_rows(ctx)[0]["excluded_conditions"] == ["dose=3"],
            str(_raw_rows(ctx)),
        )
        check(
            "the intent card says construction will read it, with the holdout, "
            "and names the record key, not a file",
            len(lines) == 1
            and "read from the raw files" in lines[0]
            and "dose=3" in lines[0]
            and lines[0].endswith(" phenomenology_raw")
            and ".json" not in lines[0],
            str(lines),
        )
        context = model_module._construction_context(ctx, None, "prediction")
        view = context.get("data_phenomenology")
        check(
            "construction's view is the raw reading until the round holds a "
            "table: its sentences, how to read them, and where they came from",
            isinstance(view, dict)
            and view["sentences"] == rec["sentences"]
            and view["how_to_read_this"] == raw.HOW_TO_READ
            and view["source"] == "raw files",
            str(view),
        )
        check(
            "read back, not derived again: still one ledger row",
            len(_raw_rows(ctx)) == 1,
        )
        routing.enforce("construction", context.keys())
        prompt = build_prompt("construction", context, None)
        check(
            "the construction prompt carries the raw sentences",
            "## data_phenomenology" in prompt
            and rec["sentences"][0] in prompt
            and '"source": "raw files"' in prompt,
        )

        # S2 writes the curated reading: construction's view switches to it,
        # the raw one is checked against it, ledgered, and on the compile card
        phenomenology.write(ctx, _curated_toy_phos())
        view2 = phenomenology.for_construction(ctx)
        check(
            "once S2's artifact exists, construction reads it, not the raw one",
            set(view2) == {"sentences", "how_to_read_this"}
            and view2["how_to_read_this"] == phenomenology.HOW_TO_READ,
            str(sorted(view2)),
        )
        checks = [
            e
            for e in ctx.ledger.entries()
            if e.get("event") == "data_phenomenology_check"
        ]
        check(
            "after S2 the agreement is ledgered: both matched series agree",
            len(checks) == 1
            and checks[0]["n_matched"] == 2
            and checks[0]["n_agree"] == 2
            and checks[0]["n_disagree"] == 0,
            str(checks),
        )
        card = compile_gate.card_lines(ctx, [None])
        check(
            "and the compile card carries the agreement line",
            any("agrees with the curated table on all 2 matched" in ln for ln in card),
            "\n".join(card),
        )
        # the curated table reads dose 1 as a peak: a shape disagreement
        data_node = phenomenology.node(ctx.round)
        s2 = data_node.get()
        for r in s2["descriptors"]:
            if r["condition"] == "dose=1":
                r.update(form="rise_and_fall", direction="peak", peak_near="20")
        data_node.put(s2)
        card = raw.check_card_lines(ctx)
        check(
            "a shape disagreement puts the raw and the curated reading on the card",
            len(card) == 1
            and "the raw-file reading of pR_au under dose=1 said an exponential "
            "rise" in card[0]
            and "the curated table says a rise and fall (half-change by ~5, peak "
            "near ~20)" in card[0],
            str(card),
        )

    curated = phenomenology.build(_curated_toy_phos())
    slow = copy.deepcopy(curated)
    for r in slow["descriptors"]:
        if r["condition"] == "dose=0.3":
            r["half_change_by"] = str(5 * float(r["half_change_by"]))
    chk = raw.compare(curated, slow, None)
    check(
        "a timescale more than a factor of two apart is a disagreement too",
        [d["on"] for d in chk["disagreements"]] == ["timescale"]
        and chk["n_agree"] == 1,
        str(chk),
    )
    renamed = copy.deepcopy(curated)
    for r in renamed["descriptors"]:
        r["observable"] = "pR"
    report = {
        "mappings": [
            {
                "value_column": "pR_au",
                "observable_label": "pR",
                "condition_columns": ["dose"],
            }
        ]
    }
    matched = raw.compare(curated, renamed, report)
    unmatched = raw.compare(curated, renamed, None)
    check(
        "names are matched through S2's own mappings; without them a renamed "
        "label is unmatched and the card says so",
        matched["n_matched"] == 2
        and unmatched["n_matched"] == 0
        and "could not be matched" in raw.check_line(unmatched),
        f"{matched['n_matched']} / {unmatched['n_matched']}",
    )

    with tempfile.TemporaryDirectory() as tmp, temp_record("raw_reject") as root:
        ctx = _raw_ctx(
            Path(tmp), root, ["dose=3"], lambda df: df[df["time_min"].isin([0, 5, 10])]
        )
        lines = raw.intent_card_lines(ctx)
        view = phenomenology.for_construction(ctx)
        rows = _raw_rows(ctx)
        check(
            "rejected: nothing in the record, one ledger row naming the rule, "
            "construction given nothing",
            not raw.node(ctx.root).exists()
            and view is None
            and len(rows) == 1
            and rows[0]["rule"] == "time_values"
            and "rule time_values" in rows[0]["note"],
            str(rows),
        )
        check(
            "and one line on the intent card: construction reads the lab note only",
            len(lines) == 1
            and lines[0].startswith(
                "curve descriptors: not derived from the raw files — "
            )
            and lines[0].endswith("; construction reads the lab note only"),
            str(lines),
        )
    with tempfile.TemporaryDirectory() as tmp, temp_record("raw_holdout") as root:
        ctx = _raw_ctx(Path(tmp), root, ["concentration=3"])
        view = phenomenology.for_construction(ctx)
        check(
            "a holdout that does not resolve against the raw columns: nothing "
            "at all reaches construction",
            view is None
            and not raw.node(ctx.root).exists()
            and [e["rule"] for e in _raw_rows(ctx)] == ["holdout_resolves"],
            str(_raw_rows(ctx)),
        )
    with tempfile.TemporaryDirectory() as tmp, temp_record("raw_moot") as root:
        ctx = _raw_ctx(Path(tmp), root, ["dose=3"])
        (ctx.testcase_dir / "supplied").mkdir()
        (ctx.testcase_dir / "supplied" / "model.ant").write_text("model m\nend\n")
        check(
            "a supplied model makes the raw reading moot: nothing derived or said",
            raw.intent_card_lines(ctx) == [] and not _raw_rows(ctx),
        )

    # everything downstream of construction reads the S2 version: the raw
    # reading is read by the construction view, the intent card and the check;
    # the legacy importer names its key only to transcribe an old run into it
    allowed = {
        "workflow_modules/data/phenomenology.py",
        "workflow_modules/data/raw_phenomenology.py",
        "workflow_modules/cost_probe/compile_gate.py",
        "workflow_modules/intent/engine.py",
        # the legacy importer maps an old file onto the key, and the typed
        # schema declares the field: neither reads the reading for an agent
        "result/importer.py",
        "result/model.py",
    }
    readers = sorted(
        str(p.relative_to(REPO / "octomod"))
        for p in (REPO / "octomod").rglob("*.py")
        if "raw_phenomenology" in p.read_text() or raw.KEY in p.read_text()
    )
    check(
        "nothing downstream of construction reads the raw reading",
        set(readers) <= allowed,
        str(readers),
    )


def _drive(runs_dir: Path, run_id: str) -> tuple[int, list[dict]]:
    """toy_phos through its file gates with the stub backend, every gate
    answered `y`; (exit code, the gate payloads in order)."""
    env = dict(os.environ, OCTOMOD_RUNS_DIR=str(runs_dir))
    base = [
        sys.executable,
        "-m",
        "octomod",
        "run",
        "--testcase",
        "testcase/toy_phos",
        "--backend",
        "stub",
        "--run-id",
        run_id,
        "--gate-mode",
        "file",
    ]
    root = run_root(run_id, runs_dir)
    cards = []

    def call(extra):
        return subprocess.run(
            base + extra, cwd=REPO, env=env, capture_output=True, text=True
        ).returncode

    rc = call([])
    for _ in range(12):
        if rc != 3:
            break
        cards.append(pending_gate(root))
        rc = call(["--gate-answer", "y"])
    return rc, cards


def test_a_stub_run_carries_both() -> None:
    # the battery's own runs directory, else a temporary one: never `runs/`
    root = os.environ.get("OCTOMOD_RUNS_DIR")
    with tempfile.TemporaryDirectory() as tmp:
        runs_dir = Path(root) if root else Path(tmp)
        # a fresh id per process: a kept runs directory must not refuse it
        run_id = f"curveforms_toy_phos_{os.getpid()}"
        rc, cards = _drive(runs_dir, run_id)
        root = run_root(run_id, runs_dir)
        run = rnd(root, 0)
        check("the stub run of toy_phos ends 0", rc == 0, f"exit {rc}")
        ph = (run / phenomenology.KEY).get({})
        led = ledger_rows(root)
        raw = (root / "phenomenology_raw").get({})
        raw_rows = [
            e
            for e in led
            if e.get("event") == "data_phenomenology" and e.get("source") == "raw files"
        ]
        check(
            "before construction the raw files were read, the held-out dose "
            "excluded, and ledgered once",
            raw.get("source") == "raw files"
            and raw.get("excluded_conditions") == ["dose=3"]
            and len(raw_rows) == 1,
            str(raw_rows),
        )
        intent_card = next((c for c in cards if c["module"] == "intent"), {"lines": []})
        check(
            "the intent card says so in one line",
            sum("curve descriptors:" in ln for ln in intent_card["lines"]) == 1
            and any("read from the raw files" in ln for ln in intent_card["lines"]),
            "\n".join(intent_card["lines"]),
        )
        prompt = (run / "agent_calls/construction/prompt").text("")
        check(
            "the round-0 construction prompt carries the raw sentences",
            "## data_phenomenology" in prompt
            and bool(raw.get("sentences"))
            and raw["sentences"][0] in prompt
            and '"source": "raw files"' in prompt,
        )
        check(
            "S2 wrote the phenomenology with the held-out dose excluded, and "
            "ledgered it; its sentences are the raw ones",
            ph.get("excluded_conditions") == ["dose=3"]
            and any(
                e.get("event") == "data_phenomenology" and e.get("module") == "data"
                for e in led
            )
            and ph.get("sentences") == raw.get("sentences"),
            str(ph.get("excluded_conditions")),
        )
        checks = [e for e in led if e.get("event") == "data_phenomenology_check"]
        check(
            "after S2 the raw reading's agreement with the curated one is ledgered",
            len(checks) == 1
            and checks[0]["n_matched"] == 2
            and checks[0]["n_disagree"] == 0,
            str(checks),
        )
        sig = (run / "data/signals").get()
        described = {r["condition"] for r in sig["curve_descriptors"]["per_series"]}
        check(
            "the curve descriptors beside the signals skip the held-out dose too",
            described == {"dose=0.3", "dose=1"},
            str(sorted(described)),
        )
        compile_card = next(
            (c for c in cards if c["module"] == "assembly_cost_boundary"), {"lines": []}
        )
        check(
            "the compile card shows the sentences",
            any(ph["sentences"][0] in ln for ln in compile_card["lines"]),
            "\n".join(compile_card["lines"][:8]),
        )
        check(
            "and the raw reading's agreement line",
            any(
                "agrees with the curated table on all 2 matched" in ln
                for ln in compile_card["lines"]
            ),
            "\n".join(compile_card["lines"][:10]),
        )
        prompt = (run / "agent_calls/interpretation/prompt").text()
        check(
            "the interpreter's prompt carries the residual forms",
            '"residual_forms"' in prompt and '"summary"' in prompt,
        )
        forms = (run / residuals.RESIDUAL_FORMS_KEY).get({})
        html = (reports_dir(root) / "round_0" / "report" / "report.html").read_text()
        check(
            "and the report's residual section has its line",
            forms.get("summary") and "Residual shape</b>" in html,
            str(forms.get("summary"))[:160],
        )


def main() -> int:
    print("the functional-form library")
    test_planted_exponential()
    test_the_simpler_form_stands()
    test_noise_reads_as_constant()
    test_planted_rise_and_fall()
    test_too_few_points()
    print("\naggregation into sentences")
    test_aggregation_sentence()
    print("\nresidual forms in the agents' payloads")
    test_residual_forms_reach_both_agents()
    print("\ndata phenomenology on toy_phos")
    test_toy_phos_phenomenology()
    test_construction_still_blind_to_values()
    print("\nthe raw-file reading, before construction")
    test_raw_reading_of_toy_phos()
    test_raw_rejections()
    test_raw_reading_on_the_run_seams()
    print("\na stub run of toy_phos, end to end")
    test_a_stub_run_carries_both()
    print()
    return finish(
        "CURVE FORMS",
        "CURVE FORMS OK — forms are named from the data, grouped in words, and "
        "construction reads shapes, never values",
    )


if __name__ == "__main__":
    raise SystemExit(main())
