"""The epistemic reference end to end, and an echo that must not break it.

  1. a lowered FIM threshold reaches flat directions on a real run;
  2. every computed flat combination reaches the gate's reference;
  3. the blocking consistency gate runs and passes on those entries;
  4. a re-spelled echo of a real entry (minus sign, decimals, spacing, prose) passes;
  5. exact string equality would have failed every one of those re-spellings;
  6. dropping the entry altogether still fails, and the detail quotes it;
  7. an identifier the round's problem lacks fails `evaluation_names_exist` by name,
     while the engine's own entries and a worded entry pass.

    uv run python tests/epistemic_echo_smoke.py [testcase]
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod import config  # noqa: E402
from octomod.workflow_modules.evaluation import engine as s7  # noqa: E402
from octomod.workflow_modules.evaluation import identifiability as ident  # noqa: E402
from tests._record import ledger_rows, rnd, run_root, work  # noqa: E402

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR

# low enough that the toys' own spectra (2.4-2.9 decades) produce flat
# directions, a state no fixture reaches; the declared default stays 8.0
FLAT_DECADES = 1.0


def staged_testcase(case: str, into: Path) -> Path:
    """A testcase copy whose stub echoes the computed sets, not a hard-coded []."""
    dst = into / case
    shutil.copytree(REPO / "testcase" / case, dst)
    stub = dst / "stubs" / "interpretation.json"
    reply = json.loads(stub.read_text())
    reply["_copy_computed"] = True
    stub.write_text(json.dumps(reply, indent=2) + "\n")
    return dst


def run_with_flat_directions(case: str, tmp: Path):
    from octomod.cli import main

    overlay = tmp / "flat_overlay.yaml"
    overlay.write_text(f"gates:\n  fim:\n    flat_decades: {FLAT_DECADES}\n")
    run_id = f"epistemic_{case}_{time.strftime('%H%M%S')}"
    previous = os.environ.get("OCTOMOD_SPEC_OVERLAY")
    os.environ["OCTOMOD_SPEC_OVERLAY"] = str(overlay)
    try:
        rc = main(
            [
                "run",
                "--testcase",
                str(staged_testcase(case, tmp)),
                "--backend",
                "stub",
                "--auto-approve",
                "--run-id",
                run_id,
            ]
        )
    finally:
        if previous is None:
            os.environ.pop("OCTOMOD_SPEC_OVERLAY", None)
        else:
            os.environ["OCTOMOD_SPEC_OVERLAY"] = previous
    return rc, run_root(run_id)


def respellings(entry: str) -> dict[str, str]:
    """The entry re-spelled as a language model might; identical variants dropped."""
    body = entry.split(": ", 1)[1] if ": " in entry else entry
    candidates = {
        "unicode minus (U+2212)": entry.replace("-", "−"),
        "en dash (U+2013)": entry.replace("-", "–"),
        "one decimal": entry.replace(".00", ".0"),
        "spaces around the operators": entry.replace("*", " * ").replace("-", " - "),
        "wrapped in prose": f"the flat combination (FIM) {body} is unconstrained here",
        "lower-cased marker": entry.replace("(FIM)", "(fim)"),
    }
    return {k: v for k, v in candidates.items() if v != entry}


def main(case: str = "toy_phos") -> int:
    print(f"epistemic reference + echo — {case}\n")
    with tempfile.TemporaryDirectory() as tmp:
        rc, root = run_with_flat_directions(case, Path(tmp))

    check("the run completes with flat directions present", rc == 0, f"exit {rc}")
    core = (rnd(root, 0) / "evaluation_core").get()
    screen = core.get("identifiability") or {}
    computed_flat = ident.computed_flat_combinations(screen)
    check(
        "lowering the threshold does reach flat directions — otherwise this "
        "whole file asserts nothing",
        len(computed_flat) > 0,
        f"{len(screen.get('flat_directions') or [])} direction(s), "
        f"{len(computed_flat)} with a composition to name",
    )
    if not computed_flat:
        print("\nEPISTEMIC ECHO FAILED — no flat direction to test with")
        return 1

    # ---- every computed flat combination is fed to the gate --------------
    fed = core.get("computed_cannot_distinguish") or []
    missing = [e for e in computed_flat if e not in fed]
    check(
        "every computed flat combination reaches the gate's reference — the "
        "regression guard against an assignment that overwrites them",
        not missing,
        f"{len(fed)} entries fed; missing {missing}",
    )

    # ---- the gate agreed, on the run itself ------------------------------
    ledger = ledger_rows(root)
    overclaim = [e for e in ledger if e.get("gate_id") == "evaluation_no_overclaim"]
    check(
        "and the blocking consistency gate ran and passed on those entries",
        overclaim and overclaim[-1]["passed"],
        str(overclaim[-1]["detail"] if overclaim else "the gate never ran"),
    )

    # ---- re-spelled echoes, measured on what this run computed -----------
    interp_ok = {
        "cannot_distinguish": list(fed),
        "nonetheless_determined": list(core["computed_nonetheless_determined"]),
        "answers_intent": [{"criterion": "c", "verdict": "pass"}],
    }
    # a direction over TWO parameters, so the minus-sign variants are real: the
    # sign is the trade-off, and the character an agent most likely retypes
    entry = next((e for e in computed_flat if "-" in e), computed_flat[0])
    variants = respellings(entry)
    check(
        "the entry under test has enough plausible re-spellings to mean " "something",
        len(variants) >= 4,
        f"{len(variants)} variants of {entry!r}",
    )
    for label, echoed in variants.items():
        interp = dict(interp_ok)
        interp["cannot_distinguish"] = [
            echoed if e == entry else e for e in interp_ok["cannot_distinguish"]
        ]
        res = s7._consistency_results(core, interp)[0]
        check(
            f"a real entry re-spelled — {label} — still passes", res.passed, res.detail
        )

    # and exact string equality would NOT have passed them
    old_style_failures = [
        label
        for label, echoed in variants.items()
        if entry not in {echoed if e == entry else e for e in fed}
    ]
    check(
        "exact string equality would have failed EVERY one of them — the "
        "live-run stop this fix removes was real, not hypothetical",
        len(old_style_failures) == len(variants),
        f"{len(old_style_failures)} of {len(variants)} would have stopped the run",
    )

    # ---- and it is still a gate -----------------------------------------
    interp = dict(interp_ok)
    interp["cannot_distinguish"] = [e for e in fed if e != entry]
    res = s7._consistency_results(core, interp)[0]
    check(
        "dropping the entry altogether still fails, and the detail quotes it",
        not res.passed and entry in res.detail,
        res.detail[:120],
    )

    # ---- what the agent ADDS must exist ---------------------------------
    # The checks above compare the lists with the engine's and never ask
    # whether an addition names anything at all, so a parameter of a process
    # the model does not contain could be credited as determined. Checked on
    # this run's own round, read from its record.
    names = s7._problem_names(rnd(root, 0))
    estimated = (work(root, 0) / "petab/parameters").table()
    estimated = estimated.loc[estimated["estimate"] == 1, "parameterId"]
    check(
        "the names are read from the record: every estimated parameter of the "
        "fitted problem is among them",
        len(estimated) > 0 and set(map(str, estimated)) <= names["ids"],
        f"{len(names['ids'])} id(s) read; estimated {sorted(map(str, estimated))}",
    )
    real = s7._consistency_results(core, interp_ok, names)[-1]
    check(
        "the engine's own entries — flat combinations included — all name "
        "something this problem has",
        real.gate_id == "evaluation_names_exist" and real.passed,
        real.detail[:160],
    )
    interp = dict(interp_ok)
    interp["nonetheless_determined"] = list(interp_ok["nonetheless_determined"]) + [
        "k_ghost",
        "obs_ghost@dose_3",
        "mechanism:M9",
        "the plateau at the top dose",
    ]
    bad = s7._consistency_results(core, interp, names)[-1]
    check(
        "an identifier the problem lacks fails the gate, each one named; words "
        "are interpretation and pass",
        not bad.passed
        and bad.blocking
        and all(
            x in bad.detail for x in ("k_ghost", "obs_ghost@dose_3", "mechanism:M9")
        )
        and "plateau" not in bad.detail,
        bad.detail[:200],
    )
    check(
        "without the problem's names the gate is not added (callers that only "
        "compare the lists see three results, as before)",
        len(s7._consistency_results(core, interp_ok)) == 3,
    )

    print()
    return finish(
        "EPISTEMIC ECHO",
        f"EPISTEMIC ECHO OK — {len(computed_flat)} flat combination(s) computed, "
        f"fed and echoed; the gate reads the claim, not its spelling",
    )


if __name__ == "__main__":
    raise SystemExit(main(*(sys.argv[1:] or [])))
