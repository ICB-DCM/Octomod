"""Measurement processing is a declared, closed vocabulary (token-free).

  1. the contract, the skill and the executor agree on the KINDS — one drift test;
  2. every refusal is by name: kind, argument, label, or held-out reference;
  3. each operation does what its name says, and the record carries its numbers;
  4. ctd_blind (read-only): the divisors are the column sums 1.00 / 4.07 / 3.79 / 0.85;
  5. the gate routes to data_extraction, and the agent summary says not to scale twice.

    uv run python tests/data_processing_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "tools"))

from _harness import check, finish  # noqa: E402

from octomod.agents import ROLES  # noqa: E402
from octomod.orchestration.interaction import battery_feedback as bf  # noqa: E402
from octomod.workflow_modules.data import data_processing as dp  # noqa: E402


def _table() -> pd.DataFrame:
    rows = []
    for cond, base in (("c0", 1.0), ("c1", 2.0), ("blank", 0.0)):
        for t in (0.0, 1.0):
            for rep in (1, 2):
                rows.append(
                    {
                        "observable_label": "a",
                        "condition_label": cond,
                        "condition_key": cond,
                        "time": t,
                        "value": base * (1 + t) + 0.5 + 0.01 * rep,
                        "replicate": rep,
                    }
                )
                rows.append(
                    {
                        "observable_label": "b",
                        "condition_label": cond,
                        "condition_key": cond,
                        "time": t,
                        "value": 3 * base * (1 + t) + 0.5 + 0.01 * rep,
                        "replicate": rep,
                    }
                )
    return pd.DataFrame(rows)


def test_one_vocabulary_in_three_places() -> None:
    contract = ROLES["data_extraction"].contract
    skill = (REPO / "skills" / "data_extraction.md").read_text()
    for k in dp.KINDS:
        check(f"contract and skill both name `{k}`", k in contract and k in skill)
    check(
        "the observation contract is told about processing_applied",
        "processing_applied" in ROLES["observation"].contract,
    )
    check(
        "the contract states the holdout rule and the not-operations",
        "HELD OUT" in contract and "clipping" in contract,
    )
    # every kind the vocabulary declares has an executor branch: run each once
    df = _table()
    for k in dp.KINDS:
        op = {"kind": k, "labels": ["a"]}
        if k == "subtract_reference":
            op["reference"] = {"condition_label": "blank"}
        if k == "scale_units":
            op.update({"factor": 2.0, "from_units": "AU", "to_units": "AU2"})
        out, rec = dp.apply([op], df, [])
        check(
            f"`{k}` executes and is recorded",
            rec and rec[0]["kind"] == k and len(out) == len(df),
        )


def test_refusals_are_by_name() -> None:
    df = _table()

    def refused(ops, holdout=()):
        try:
            dp.validate(ops, df, list(holdout))
            return None
        except dp.ProcessingRefused as e:
            return str(e)

    m = refused([{"kind": "log_transform", "labels": ["a"]}])
    check(
        "an unknown kind is refused, listing the legal kinds",
        m and "normalize_by_group_sum" in m and "clipping" in m,
        (m or "ACCEPTED")[:90],
    )
    m = refused([{"kind": "scale_units", "labels": ["a"]}])
    check(
        "a missing argument is named",
        m and "factor" in m and "to_units" in m,
        (m or "ACCEPTED")[:90],
    )
    m = refused([{"kind": "normalize_by_group_sum", "labels": ["zzz"]}])
    check(
        "an unknown label is named with the labels present",
        m and "zzz" in m and "'a'" in m,
        (m or "ACCEPTED")[:90],
    )
    m = refused(
        [
            {
                "kind": "subtract_reference",
                "labels": ["a"],
                "reference": {"condition_label": "c1"},
            }
        ],
        holdout=["c1"],
    )
    check(
        "a held-out reference is refused BY NAME with the usable references",
        m and "HELD-OUT" in m and "'c1'" in m and "blank" in m and "c0" in m,
        (m or "ACCEPTED")[:120],
    )
    check(
        "… and the same reference is fine when c1 is not held out",
        refused(
            [
                {
                    "kind": "subtract_reference",
                    "labels": ["a"],
                    "reference": {"condition_label": "c1"},
                }
            ]
        )
        is None,
    )
    check(
        "dropping rows has no kind — by rule",
        "drop_rows" not in dp.KINDS and "clip" not in " ".join(dp.KINDS),
    )


def test_the_operations_do_what_they_say() -> None:
    df = _table()
    out, rec = dp.apply(
        [{"kind": "normalize_by_group_sum", "labels": ["a", "b"]}], df, []
    )
    cell = out[
        (out["condition_label"] == "c0")
        & (out["time"] == 1.0)
        & (out["replicate"] == 1)
    ]
    check(
        "normalize: the two labels sum to one per cell",
        abs(cell["value"].sum() - 1.0) < 1e-12,
        f"sum {cell['value'].sum():.6f}",
    )
    check(
        "… and the divisor is kept per cell",
        "processing_divisor" in out.columns and len(rec[0]["divisors"]) == 12,
        str(len(rec[0].get("divisors", []))),
    )
    out, rec = dp.apply(
        [
            {
                "kind": "subtract_reference",
                "labels": ["a"],
                "reference": {"condition_label": "blank"},
            }
        ],
        df,
        [],
    )
    a_c0 = out[
        (out["observable_label"] == "a")
        & (out["condition_label"] == "c0")
        & (out["time"] == 1.0)
        & (out["replicate"] == 2)
    ]["value"].iloc[0]
    # raw 2.52 minus the blank's per-time MEAN over its two lanes (0.51, 0.52)
    check(
        "subtract by condition: the reference's per-time mean over replicates",
        abs(a_c0 - (2.52 - 0.515)) < 1e-12,
        f"{a_c0:.6f} (raw 2.52, mean blank 0.515)",
    )
    check(
        "… b untouched, the reference values recorded",
        (
            out[out["observable_label"] == "b"]["value"].values
            == df[df["observable_label"] == "b"]["value"].values
        ).all()
        and rec[0]["reference"]["values"],
    )
    out, rec = dp.apply(
        [{"kind": "subtract_reference", "labels": ["a"], "reference": {"time": 0.0}}],
        df,
        [],
    )
    t0 = out[(out["observable_label"] == "a") & (out["time"] == 0.0)]["value"]
    check(
        "subtract by time: the reference time reads zero afterwards",
        np.allclose(t0, 0.0),
    )
    out, rec = dp.apply(
        [
            {
                "kind": "scale_units",
                "labels": ["b"],
                "factor": 1000.0,
                "from_units": "uM",
                "to_units": "nM",
            }
        ],
        df,
        [],
    )
    check(
        "scale_units: multiplied, units recorded",
        np.allclose(
            out[out["observable_label"] == "b"]["value"],
            1000 * df[df["observable_label"] == "b"]["value"],
        )
        and rec[0]["to_units"] == "nM",
    )
    check(
        "the raw frame is never edited in place",
        np.allclose(df["value"], _table()["value"]),
    )
    check(
        "card lines name the op and the numbers",
        any(
            "row-normalised" in ln or "minus the reference" in ln or " x " in ln
            for ln in dp.card_lines(rec)
        ),
    )
    s = dp.summary_for_agent(rec)
    check(
        "the agent summary says not to scale twice",
        s and "second scale" in s["how_to_read_this"],
    )


def test_ctd_blind_divisors_are_the_column_sums() -> None:
    from probe_processing_ctd import divisors

    got = divisors()
    want = [(0.0, 1.00), (60.0, 4.07), (120.0, 3.79), (960.0, 0.85)]
    ok = len(got) == 4 and all(
        abs(t - wt) < 1e-9 and abs(d - wd) < 0.005
        for (t, d), (wt, wd) in zip(got, want, strict=False)
    )
    check(
        "(b) ctd_blind: the per-time-point divisors are 1.00 / 4.07 / 3.79 / 0.85",
        ok,
        " / ".join(f"{d:.3f}" for _t, d in got),
    )


def test_the_gate_is_attributed_and_declared() -> None:
    check(
        "data_processing_legal routes to data_extraction",
        bf.ATTRIBUTION.get("data_processing_legal") == "data_extraction",
    )
    src = (REPO / "octomod" / "workflow_modules" / "data" / "engine.py").read_text()
    check(
        "the gate is DECLARED in the S2 battery (not only synthesised)",
        '@gate("data_processing_legal", "T0")' in src,
    )


def main() -> int:
    test_one_vocabulary_in_three_places()
    test_refusals_are_by_name()
    test_the_operations_do_what_they_say()
    test_ctd_blind_divisors_are_the_column_sums()
    test_the_gate_is_attributed_and_declared()
    return finish(
        "DATA PROCESSING",
        "DATA PROCESSING OK — a closed vocabulary, refused by name, executed by the engine, numbers recorded",
    )


if __name__ == "__main__":
    sys.exit(main())
