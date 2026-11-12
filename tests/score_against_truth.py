"""Score a finished run against a synthetic testcase's ground truth.

Runs outside the pipeline, after the fact: truth/ is never staged into any
agent context, so this scorer is the only component that reads both sides.

  prediction   -> held-out error is in the report; this adds the truth model
  parameters   -> |MLE - theta*| per parameter, and whether theta* is in the CI
  mechanism    -> did the Akaike winner match the true mechanism, decisively?

Usage:
  <venv-python> tests/score_against_truth.py --run-id <id> --testcase testcase/<case>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--testcase", required=True, type=Path)
    ap.add_argument(
        "--map",
        default="",
        metavar="fitted=truth,...",
        help="human-declared correspondence between the FITTED parameter names "
        "(the agent invents its own in a blind run) and the truth names. "
        "Never guessed automatically: a wrong pairing would silently "
        "manufacture a bias number.",
    )
    ap.add_argument(
        "--true-winner",
        default="",
        metavar="candidate_id",
        help="which candidate id corresponds to the truth, when the "
        "truth file names the mechanism in a different vocabulary "
        "(e.g. a model-space search generates ids from axis names). "
        "Never inferred.",
    )
    ap.add_argument(
        "--allow-archive",
        action="store_true",
        help="score a run that READ the testcase tried-log. Refused by "
        "default: a run fed the archive of what earlier runs already found is "
        "not blind, so scoring it measures the archive and not the system.",
    )
    args = ap.parse_args()
    alias = {}
    for pair in filter(None, (p.strip() for p in args.map.split(","))):
        if "=" not in pair:
            print(f"bad --map entry {pair!r}; expected fitted=truth")
            return 1
        f, t = (s.strip() for s in pair.split("=", 1))
        alias[t] = f  # truth name -> fitted name

    truth_path = (
        (
            args.testcase
            if args.testcase.is_absolute()
            else (Path.cwd() / args.testcase)
        ).resolve()
        / "truth"
        / "true_parameters.json"
    )
    if not truth_path.exists():
        print(f"no ground truth at {truth_path} — nothing to score")
        return 1
    truth = json.loads(truth_path.read_text())
    true_params = truth.get("true_parameters") or truth.get("parameters") or {}

    from octomod.result.access import record_for, rounds_with_reports, run_meta
    from octomod.result.node import Node
    from octomod.result.runstore import RunStore

    # the run is one record file, <RUNS>/<id>.h5; the scorer reads its
    # typed record, never a file inside it
    root = Node(RunStore.for_run(RUNS, args.run_id))
    if not root.exists():
        print(f"no run record at {root.store.path} — nothing to score")
        return 1
    rr = record_for(root)
    consumed = run_meta(rr).get("tried_log_consumed") or {}
    if consumed and not args.allow_archive:
        print(
            f"REFUSING TO SCORE {args.run_id}: it read the testcase tried-log "
            f"({consumed.get('n_entries')} entries, sha "
            f"{consumed.get('sha')}), so it was not blind."
        )
        print(
            "A benchmark on an archive-fed run measures the archive, not the "
            "system. Score a blind run, or pass --allow-archive if you meant "
            "to measure the archive."
        )
        return 1
    reports = rounds_with_reports(rr)
    if not reports:
        print(
            f"no round of {args.run_id} has an evaluation "
            f"(rounds/round_k/evaluation) — nothing to score"
        )
        return 1
    last_idx, report = reports[-1]

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(REPO))
        except ValueError:
            return str(p)

    print(
        f"scoring round {last_idx} of {args.run_id} (from its record) against "
        f"{_rel(truth_path)}\n"
    )

    if report["goal"] == "mechanism_discrimination":
        return _score_mechanism(report, truth, args.true_winner)
    return _score_parameters(report, true_params, alias)


def _score_parameters(report: dict, true_params: dict, alias: dict) -> int:
    import math

    best = report["parameters"]["best"]
    profiles = report.get("profiles", {})

    # Name correspondence is REPORTED, never inferred: a blind agent names its
    # own parameters, and silently skipping the unmatched ones would print an
    # empty scorecard that looks like a clean run.
    resolved = {t: alias.get(t, t) for t in true_params}
    unmatched = sorted(t for t, f in resolved.items() if f not in best)
    fitted_free = sorted(
        f
        for f in best
        if f not in set(resolved.values()) and not f.startswith("sigma_")
    )
    print(
        f"parameter correspondence: {len(true_params) - len(unmatched)}/"
        f"{len(true_params)} true parameters matched"
        + (" (via --map)" if alias else "")
    )
    if unmatched:
        print(
            f"  NO COUNTERPART for {unmatched} — either a naming mismatch "
            f"(supply --map) or, if the mapping is complete, a STRUCTURAL "
            f"GAP: the fitted model has no such quantity"
        )
    if fitted_free:
        print(f"  fitted-only (no truth counterpart): {fitted_free}")
    if not any(f in best for f in resolved.values()):
        print(
            "\nNOTHING SCORED: no true parameter resolves to a fitted one. "
            "Supply --map fitted=truth,... — an empty scorecard is not a pass."
        )
        return 1
    print()

    rows = []
    n_cov = n_ci = 0
    for pid, theta in sorted(true_params.items()):
        fid = resolved[pid]
        if fid not in best:
            continue
        mle = float(best[fid])
        err_dec = abs(math.log10(max(mle, 1e-300) / max(float(theta), 1e-300)))
        shown = pid if fid == pid else f"{pid}={fid}"
        line = f"{shown:22s} truth {theta:9.4g}  MLE {mle:9.4g}  |err| {err_dec:5.3f} decades"
        if fid in profiles and not fid.startswith("_") and "ci95" in profiles[fid]:
            lo, hi = profiles[fid]["ci95"]
            inside = lo <= float(theta) <= hi
            n_ci += 1
            n_cov += inside
            line += f"  CI [{lo:.4g}, {hi:.4g}] -> truth {'INSIDE' if inside else 'OUTSIDE'}"
        rows.append(line)
    print("\n".join(rows))
    if n_ci:
        print(
            f"\nprofile-CI coverage of truth: {n_cov}/{n_ci} "
            f"(expect ~19/20 over many parameters/replications at 95%)"
        )
    hold = report.get("holdout", {})
    if hold.get("available"):
        worst = max(g["nrmse"] for g in hold["groups"])
        print(f"held-out worst nRMSE: {worst:.3f}")
    print(
        "\nNOTE: single-dataset coverage is one Bernoulli draw per parameter —"
        "\nthe calibration claim needs replicated synthetic datasets (D2-style)."
    )
    return 0


def _score_mechanism(report: dict, truth: dict, true_winner: str = "") -> int:
    d = report["discrimination"]
    true_mech = truth.get("true_mechanism_id")
    print(f"true mechanism:   {true_mech or '(not declared in truth file)'}")
    print(
        f"winner:           {d['winner']}  "
        f"({'decisive' if d['decisive'] else 'not decisive'})"
    )
    print(f"indistinguishable: {d['indistinguishable']}")
    for r in sorted(d["candidates"], key=lambda r: r["aic"]):
        print(
            f"  {r['id']:24s} dAIC {r['delta_aic']:8.2f}  weight {r['akaike_weight']:.3f}"
        )
    if not true_mech:
        return 0

    honest = (not d["decisive"]) == (len(d["indistinguishable"]) > 1)
    ids = {r["id"] for r in d["candidates"]}
    if true_mech not in ids and not true_winner:
        # The truth names the mechanism in a STAGED candidate set's vocabulary;
        # a model-space search builds ids from axis names, so a correct run can
        # differ in spelling. Never infer the correspondence: a human declares it.
        print(
            f"\nCANNOT SCORE THE WINNER: the truth names {true_mech!r}, which "
            f"is not one of the candidate ids {sorted(ids)}."
        )
        print(
            "These are different naming vocabularies, not necessarily a wrong "
            "answer. Declare the correspondence with "
            "--true-winner <candidate_id> after checking the structures match."
        )
        print(f"decisiveness reporting {'consistent' if honest else 'inconsistent'}")
        return 1

    target = true_winner or true_mech
    correct = d["winner"] == target
    in_set = target in d["indistinguishable"]
    if true_winner:
        print(f"\n(correspondence declared by hand: {target!r} is the truth)")
    verdict = (
        "CORRECT"
        if correct
        else (
            "not the top model, but INSIDE the indistinguishable set"
            if in_set
            else "WRONG"
        )
    )
    print(
        f"\nverdict: winner {verdict}; "
        f"decisiveness reporting {'consistent' if honest else 'inconsistent'}"
    )
    return 0 if (correct or in_set) else 2


if __name__ == "__main__":
    sys.exit(main())
