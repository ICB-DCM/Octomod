"""The gate-policy profiles driven through real stub runs, token-free.

  1. benchmark finishes with no pause; each gate is ledgered mode="policy" with its sha;
  2. copilot pauses at exactly the judgment gates and answers the cost gates itself;
  3. strict pauses at exactly the gates a run with no policy pauses at;
  4. a hole in a benchmark policy stops the run (exit 1), naming the gate;
  5. --auto-approve with --policy is refused (exit 2) before a run starts.

    uv run python tests/policy_modes.py [testcase] [--only benchmark|copilot|strict|hole|refusal]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod import config  # noqa: E402
from tests._record import ledger_rows, pending_gate, rnd, run_root  # noqa: E402
from tests.file_gate_loop import EXPECTED, drive, run_cli  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

PY = sys.executable

# The partition, for the cases this suite knows. A gate here is judgment-shaped
# and therefore the human's; everything else the copilot profile answers.
JUDGMENT = ["intent", "model_scope", "evaluation_verdict"]


def ledger(run_id: str) -> list[dict]:
    return ledger_rows(run_root(run_id, RUNS))


def gate_rows(run_id: str) -> list[dict]:
    return [r for r in ledger(run_id) if r.get("event") == "human_gate"]


SECTIONS = ("benchmark", "copilot", "strict", "hole", "refusal")


def main(case: str = "toy_phos", only: tuple[str, ...] = SECTIONS) -> int:
    stamp = time.strftime("%H%M%S")
    expected_gates = EXPECTED.get(case)
    print(f"sections: {', '.join(only)}\n")

    # 1 ---- benchmark: no human exists, and none is consulted --------------
    if "benchmark" in only:
        rid = f"policy_bench_{case}_{stamp}"
        rc = run_cli(
            [
                "run",
                "--testcase",
                f"testcase/{case}",
                "--backend",
                "stub",
                "--run-id",
                rid,
                "--gate-mode",
                "file",
                "--policy",
                "benchmark",
            ]
        )
        check("benchmark run completes", rc == 0, f"exit {rc}")
        check(
            "benchmark never wrote a pending_gate",
            pending_gate(run_root(rid, RUNS)) is None,
        )
        rows = gate_rows(rid)
        modes = {r.get("mode") for r in rows}
        check(
            "every gate the benchmark run reached was answered by policy",
            modes == {"policy"} and len(rows) >= 4,
            f"{len(rows)} gate(s), modes {sorted(modes)}",
        )
        shas = {r.get("policy_sha") for r in rows}
        meta = (run_root(rid, RUNS) / "run").get()
        check(
            "the ledger's policy sha is the one hashed into the run record",
            len(shas) == 1
            and shas == {meta.get("policy_sha")}
            and meta.get("policy_sha"),
            f"ledger {shas}, meta {meta.get('policy_sha')}",
        )
        check(
            "the run record names the profile and the file it came from",
            meta.get("policy_profile") == "benchmark"
            and str(meta.get("policy") or "").endswith("benchmark.yaml"),
            f"{meta.get('policy_profile')} {meta.get('policy')}",
        )
        check(
            "every policy answer says how the gate was covered",
            all(r.get("covered_by") for r in rows),
            f"{sorted({r.get('covered_by') for r in rows})}",
        )
        if expected_gates:
            check(
                "the benchmark run answered the same gates a human would have",
                [r["module"] for r in rows] == expected_gates,
                f"{[r['module'] for r in rows]} vs {expected_gates}",
            )
        # ANALYSIS must not report a human who was never there, and a
        # policy-signed verdict must not read as a human signature
        ana = (run_root(rid, RUNS) / "analysis").get()
        gp = ana.get("gate_policy") or {}
        check(
            "ANALYSIS names the profile and lists every policy answer",
            gp.get("profile") == "benchmark"
            and gp.get("sha") == meta["policy_sha"]
            and len(gp.get("answers") or []) == len(rows),
            f"{gp.get('profile')}, {len(gp.get('answers') or [])} answer(s)",
        )
        check(
            "ANALYSIS reports ZERO human decisions on an unattended run",
            ana["cost"]["human_decisions"] == 0
            and ana["cost"]["policy_decisions"] == len(rows),
            f"human {ana['cost']['human_decisions']}, "
            f"policy {ana['cost']['policy_decisions']}",
        )
        check(
            "the verdict is signed as policy(<sha>), never as a human",
            gp.get("verdict_signed_by") == f"policy({meta['policy_sha']})",
            f"{gp.get('verdict_signed_by')}",
        )
        signed = (
            (rnd(run_root(rid, RUNS), 0) / "decisions/evaluation_verdict")
            .get()
            .get("signed")
        )
        check(
            "the signature is durable in the record beside the verdict it signs",
            signed == f"policy({meta['policy_sha']})",
            f"{signed}",
        )

    # 2 ---- copilot: the cost gates are the policy's, the rest are ours ----
    if "copilot" in only:
        rid = f"policy_cop_{case}_{stamp}"
        rc, paused = drive(case, rid, extra=["--policy", "copilot"])
        check("copilot run completes", rc == 0, f"exit {rc}")
        check(
            "copilot paused at exactly the judgment gates",
            paused == JUDGMENT,
            f"paused {paused}, expected {JUDGMENT}",
        )
        rows = gate_rows(rid)
        by_policy = sorted({r["module"] for r in rows if r.get("mode") == "policy"})
        by_human = sorted({r["module"] for r in rows if r.get("mode") == "file"})
        if expected_gates:
            cost = sorted(g for g in expected_gates if g not in JUDGMENT)
            check(
                "the cost gates were answered by policy, in the same run",
                by_policy == cost,
                f"policy answered {by_policy}, cost-shaped {cost}",
            )
        check(
            "the judgment gates were answered by the human, not the policy",
            by_human == sorted(JUDGMENT) and not set(by_policy) & set(JUDGMENT),
            f"human answered {by_human}",
        )
        ana = (run_root(rid, RUNS) / "analysis").get()
        check(
            "a human-signed verdict reads as a human, not as the policy",
            (ana.get("gate_policy") or {}).get("verdict_signed_by")
            == "human (via the front end)",
            f"{(ana.get('gate_policy') or {}).get('verdict_signed_by')}",
        )
        check(
            "no gate in the copilot run was recorded as declined",
            all(r.get("approved") for r in rows),
            f"{len(rows)} gate(s), all approved",
        )

    # 3 ---- strict: a policy that answers nothing changes nothing ----------
    if "strict" in only:
        rid = f"policy_strict_{case}_{stamp}"
        rc, paused = drive(case, rid, extra=["--policy", "strict"])
        check("strict run completes", rc == 0, f"exit {rc}")
        if expected_gates:
            check(
                "strict paused at exactly the gates a run with no policy pauses at",
                paused == expected_gates,
                f"{paused} vs {expected_gates}",
            )
        check(
            "strict answered no gate itself",
            not [r for r in gate_rows(rid) if r.get("mode") == "policy"],
        )

    # 4 ---- a hole in a benchmark policy stops the run, naming the gate ----
    #        (the verdict removed: the run must reach it and refuse to sign)
    if "hole" in only:
        hole = Path(tempfile.mkdtemp()) / "holed.yaml"
        full = (REPO / "workflows" / "policies" / "benchmark.yaml").read_text()
        hole.write_text(
            "\n".join(
                line
                for line in full.splitlines()
                if not line.startswith("  evaluation_verdict:")
            )
            + "\n"
        )
        rid = f"policy_hole_{case}_{stamp}"
        proc = subprocess.run(
            [
                PY,
                "-m",
                "octomod",
                "run",
                "--testcase",
                f"testcase/{case}",
                "--backend",
                "stub",
                "--run-id",
                rid,
                "--gate-mode",
                "file",
                "--policy",
                str(hole),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        out = proc.stdout + proc.stderr
        check(
            "a benchmark policy with a hole exits 1 (not 0, and not a crash)",
            proc.returncode == 1,
            f"exit {proc.returncode}",
        )
        check(
            "the message names the gate it did not cover",
            "policy did not cover gate 'evaluation_verdict'" in out,
            out.strip().splitlines()[-1][:120] if out.strip() else "(no output)",
        )
        end = next(
            (r for r in reversed(ledger(rid)) if r.get("event") == "run_end"), {}
        )
        check(
            "the run_end row records the stop and the gate",
            end.get("outcome") == "stopped"
            and end.get("module") == "evaluation_verdict",
            f"{end.get('outcome')} / {end.get('module')}",
        )
        check(
            "the gates before the hole were still answered by policy",
            len([r for r in gate_rows(rid) if r.get("mode") == "policy"]) >= 3,
            f"{len(gate_rows(rid))} gate(s) reached",
        )

    # 5 ---- two answer sources for one gate is refused, not resolved -------
    if "refusal" in only:
        proc = subprocess.run(
            [
                PY,
                "-m",
                "octomod",
                "run",
                "--testcase",
                f"testcase/{case}",
                "--backend",
                "stub",
                "--run-id",
                f"policy_both_{stamp}",
                "--auto-approve",
                "--policy",
                "benchmark",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        check(
            "--auto-approve with --policy is refused (exit 2), no run started",
            proc.returncode == 2
            and not (run_root(f"policy_both_{stamp}", RUNS)).exists(),
            f"exit {proc.returncode}",
        )

    print()
    held = {
        "benchmark": "benchmark ran unattended, with full attribution",
        "copilot": "copilot split the gates with the human",
        "strict": "strict changed nothing",
        "hole": "a hole in the policy stopped the run",
        "refusal": "two answer sources were refused",
    }
    return finish(
        "POLICY MODES",
        "POLICY MODES OK — " + "; ".join(held[k] for k in SECTIONS if k in only),
    )


if __name__ == "__main__":
    argv = sys.argv[1:]
    sections = SECTIONS
    if "--only" in argv:
        i = argv.index("--only")
        sections = tuple(argv[i + 1].split(","))
        unknown = [x for x in sections if x not in SECTIONS]
        if unknown:
            raise SystemExit(f"unknown section(s) {unknown}; known: {list(SECTIONS)}")
        argv = argv[:i]
    raise SystemExit(main(argv[0] if argv else "toy_phos", sections))
