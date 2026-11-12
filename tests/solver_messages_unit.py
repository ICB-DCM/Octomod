"""The budget card says why probe starts failed, not only how many did.

  1. AMICI's own message texts are classified by kind: sigma at or below zero,
     a forward integration failure, a value that overflowed, a pre-equilibration
     failure, anything else verbatim; status codes classify the same kinds, and
     a condition AMICI skipped after an earlier failure is not a cause;
  2. the card lines: the failed-start count, then count × kind with its sentence,
     and a note when the kinds were read from status codes;
  3. on a real AMICI problem with proportional noise on a state that starts at
     zero (toy_phos_petab's problem, `sigma * Rp`, Rp(0) = 0), the probe's
     per-start call reads the sigma message from `rdatas`, and the probe's
     starts under the capture count it once per start;
  4. an AMICI without ReturnData messages falls back to the status codes, and
     the record says so.

    uv run python tests/solver_messages_unit.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.workflow_modules.cost_probe import solver_messages as sm  # noqa: E402

SIGMA_TEXT = "sigma at or below zero"
SIGMA_SENTENCE = "a proportional noise model (sigma·X) needs a floor"


def test_kinds() -> None:
    texts = {
        "sigma_nonpositive": (
            "[dose_0p3][OTHER] AMICI simulation failed: Encountered sigma <= 0 in "
            "sigmay (obs_pR, ExpData::id=dose_0p3, t=0)! value: 0.000000"
        ),
        "forward_failure": (
            "AMICI forward simulation failed at t = 3.5: AMICI failed to integrate "
            "the forward problem"
        ),
        "overflow": "AMICI encountered a NaN value for xdot[3] (x3, xdot) at t=2",
        "equilibration": "AMICI equilibration failed at t=1e+05.",
        "other": "something AMICI has not said before",
    }
    got = {k: sm.classify(t) for k, t in texts.items()}
    check(
        "AMICI's own texts are classified by kind",
        all(got[k] == k for k in texts),
        str(got),
    )
    check(
        "a forward failure whose text carries its cause is classified by the cause",
        sm.classify(
            "AMICI forward simulation failed at t = 2: AMICI encountered a NaN "
            "value for xdot[0] (x0, xdot) at t=2"
        )
        == "overflow",
    )
    check(
        "a step-limit failure is a forward integration failure",
        sm.classify(
            "Reached maximum number of steps 10000 before reaching tout at t=5."
        )
        == "forward_failure",
    )
    check(
        "status codes: too much work is a forward failure, a general error is "
        "'other', success and a skipped condition are no cause",
        sm.classify_status(-1) == "forward_failure"
        and sm.classify_status(-4) == "forward_failure"
        and sm.classify_status(-81) == "equilibration"
        and sm.classify_status(-99) == "other"
        and sm.classify_status(-1001) is None
        and sm.classify_status(0) is None,
        str([sm.classify_status(c) for c in (-1, -4, -81, -99, -1001, 0)]),
    )


def test_card_lines() -> None:
    tally = sm.Tally()
    for _ in range(68):
        tally.add("Encountered sigma <= 0 in sigmay (obs_X, t=0)! value: 0")
    for _ in range(123):
        tally.add("AMICI forward simulation failed at t = 2: CVODE error")
    rec = {
        "available": True,
        "n_starts": 5,
        "n_failed": 2,
        "table": tally.table(),
        "messages_available": True,
    }
    lines = sm.card_lines(rec)
    check(
        "the failed-start count first, then count × kind, most frequent first",
        lines[0] == "probe starts that failed: 2 of 5 — what AMICI reported, by kind:"
        and lines[1].startswith("  123× forward integration failure — stiffness")
        and lines[2].startswith(f"  68× {SIGMA_TEXT} — ")
        and SIGMA_SENTENCE in lines[2],
        str(lines),
    )
    check(
        "at most two examples per kind are kept, verbatim",
        [len(r["examples"]) for r in rec["table"]] == [1, 1],
        str([r["examples"] for r in rec["table"]]),
    )
    check(
        "nothing failed and nothing said: no card lines",
        sm.card_lines({"available": True, "n_starts": 5, "n_failed": 0, "table": []})
        == [],
    )
    status = sm.card_lines({**rec, "messages_available": False})
    check(
        "kinds read from status codes say so",
        status[-1]
        == "  (read from AMICI status codes: this AMICI exposes no messages)",
        str(status[-1:]),
    )
    check(
        "the ledger line counts every kind",
        sm.ledger_note(rec)
        == "solver messages over the probe's 5 starts (2 failed): 123× forward "
        f"integration failure; 68× {SIGMA_TEXT}",
        sm.ledger_note(rec),
    )


def _proportional_noise_problem(tmp: Path):
    """toy_phos_petab's problem with the noise `sigma * Rp`, and Rp(0) = 0."""
    from octomod.workflow_modules.assembly import petab_io
    from octomod.workflow_modules.estimation.problem import build_problem

    src = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
    dst = tmp / "petab"
    shutil.copytree(src, dst)
    obs = dst / "observables.tsv"
    text = obs.read_text()
    assert "noiseParameter1_obs_pR\tnormal" in text, text
    obs.write_text(
        text.replace(
            "noiseParameter1_obs_pR\tnormal", "noiseParameter1_obs_pR * Rp\tnormal"
        )
    )
    problem, petab_problem, _ = build_problem(petab_io.from_dir(dst), {}, None)
    return problem, petab_problem


def test_on_amici(tmp: Path) -> None:
    from octomod.workflow_modules.estimation.problem import run_multistart

    problem, petab_problem = _proportional_noise_problem(tmp)
    x = np.asarray(petab_problem.x_nominal_free_scaled, dtype=float)
    read = sm.at_point(problem, x)
    texts = [t for c in read["conditions"] for t in c["messages"]]
    check(
        "the per-start call reads the sigma message from rdatas",
        read["has_messages"]
        and any(sm.classify(t) == "sigma_nonpositive" for t in texts),
        str(read)[:300],
    )

    class Spec:
        def get(self, key, default=None):
            return {"estimation.optimizer": "fides", "estimation.engine": "serial"}.get(
                key, default
            )

    with sm.Capture() as captured:
        result = run_multistart(problem, 3, 0, Spec())
    rec = sm.probe_record(problem, result.optimize_result.list, captured)
    top = (rec["table"] or [{}])[0]
    check(
        "the probe's starts, captured: every start failed, and the table names "
        "the sigma kind",
        rec["n_starts"] == 3
        and rec["n_failed"] == 3
        and top.get("kind") == "sigma_nonpositive"
        and top.get("count", 0) >= 3
        and "over every simulation of the probe's starts" in rec["source"],
        str({k: rec.get(k) for k in ("n_starts", "n_failed", "source")}) + f" {top}",
    )
    check(
        "each failed start is attributed its own kind",
        all(s["kinds"] == ["sigma_nonpositive"] for s in rec["per_failed_start"]),
        str(rec["per_failed_start"]),
    )
    lines = sm.card_lines(rec)
    check(
        "the card says why: the sigma kind and its sentence",
        lines
        and lines[0].startswith("probe starts that failed: 3 of 3")
        and any(SIGMA_TEXT in x and SIGMA_SENTENCE in x for x in lines),
        str(lines),
    )
    print(f"    card: {lines}")


def test_status_fallback() -> None:
    class RData(dict):
        """A ReturnData with a status and no `messages` field at all."""

        def __getitem__(self, key):
            if key == "messages":
                raise KeyError(key)
            return dict.__getitem__(self, key)

    class Problem:
        x_free_indices = [0]

        def objective(self, x, sensi_orders=(0,), return_dict=False):
            return {
                "fval": float("inf"),
                "rdatas": [RData(status=-1), RData(status=-1001)],
            }

    class Start:
        def __init__(self, i, fval=float("inf")):
            self.id, self.fval, self.x0 = str(i), fval, np.zeros(1)

    rec = sm.probe_record(Problem(), [Start(0), Start(1), Start(2, 4.2)], None)
    check(
        "no messages: the status codes are classified, the skipped condition is "
        "not, and a finite start is not read",
        rec["table"]
        and rec["table"][0]["kind"] == "forward_failure"
        and rec["table"][0]["count"] == 2
        and len(rec["table"]) == 1
        and (rec["n_starts"], rec["n_failed"]) == (3, 2)
        and not rec["messages_available"]
        and "status codes" in rec["source"],
        str(rec),
    )


def test_debug_items_are_not_failures() -> None:
    from types import SimpleNamespace as Item

    class Problem:
        x_free_indices = [0]

        def objective(self, x, sensi_orders=(0,), return_dict=False):
            items = [
                Item(severity=2, identifier="DEBUG", message="a step was taken"),
                Item(severity=0, identifier="OTHER", message="Encountered sigma <= 0"),
            ]
            return {"rdatas": [{"status": -99, "messages": items}]}

    read = sm.at_point(Problem(), np.zeros(1))
    check(
        "AMICI's debug items describe a simulation and are not read as failures",
        read["conditions"][0]["messages"] == ["Encountered sigma <= 0"],
        str(read),
    )


def main() -> int:
    test_kinds()
    test_debug_items_are_not_failures()
    test_card_lines()
    test_status_fallback()
    test_on_amici(Path(tempfile.mkdtemp()))
    return finish(
        "SOLVER MESSAGES",
        "SOLVER MESSAGES OK — the budget card counts AMICI's messages by kind and "
        "says what each one means",
    )


if __name__ == "__main__":
    sys.exit(main())
