"""Gate policy as declared configuration: the strict, copilot and benchmark profiles.

strict answers no gate; copilot answers cost-shaped gates under its caps and
pauses at judgment-shaped ones; benchmark answers every gate from the file and
stops at one it does not cover. A policy answer is ledgered mode="policy" with
the policy sha. `--auto-approve` is separate: every gate yes, mode="auto".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from octomod.config import WORKFLOWS_DIR
from octomod.orchestration.interaction import gate_note

POLICIES_DIR = WORKFLOWS_DIR / "policies"

# Gate module ids by shape. A gate id not in either set is judgment-shaped by
# default (the conservative reading: pause rather than answer).
COST_GATES = {
    "assembly_cost_boundary",
    "cost_boundary_estimation",
    "evaluation_profiling_gate",
}
COST_GATE_SUFFIXES = ("_redraft_budget",)
JUDGMENT_GATES = {
    "intent",
    # accepting a failed convergence check is a scientific judgement, not a purchase
    "estimation_convergence",
    "model_scope",
    "revision",
    "revision_proposal_stop_vs_revise",
    "revision_proposal",
    "evaluation_verdict",
}

# `max_expansions` is kept small: policy must not buy mechanisms without bound.
DEFAULT_CAPS = {
    "usd_cap": 20.0,
    "max_rounds": None,
    "max_expansions": 1,
    "n_starts": None,
    "redraft_grants": 1,
}


class PolicyUncovered(Exception):
    """A gate the policy does not cover under `uncovered: stop`: the run stops."""

    def __init__(self, module: str, why: str):
        self.module = module
        self.why = why
        super().__init__(f"policy did not cover gate {module!r}: {why}")


def gate_shape(module: str) -> str:
    if module in COST_GATES or module.endswith(COST_GATE_SUFFIXES):
        return "cost"
    return "judgment"


@dataclass(frozen=True)
class PolicyAnswer:
    """What the policy answered, and on what authority.

    `covered_by` is "declared" (the profile names the gate), "shape:cost" (answered
    because the gate is cost-shaped) or "cap:<name>" (a cap turned an approval
    into a refusal); the ledger records it beside mode="policy".
    """

    approved: bool
    note: str
    covered_by: str


@dataclass
class Policy:
    profile: str
    caps: dict
    answers: dict
    uncovered: str  # "pause" | "stop"
    sha: str = ""
    source: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, profile_or_path: str | Path | None) -> Policy:
        """Load a profile by name (workflows/policies/<name>.yaml) or from a path.

        None loads copilot. That is not what "no `--policy` flag" means: the CLI
        then passes `strict`, which answers nothing, so every gate reaches a
        human. Raises FileNotFoundError for an unknown profile, ValueError for a
        strict file that declares answers.
        """
        if profile_or_path is None:
            profile_or_path = "copilot"
        p = Path(str(profile_or_path))
        if not p.exists():
            p = POLICIES_DIR / f"{profile_or_path}.yaml"
        if not p.exists():
            raise FileNotFoundError(
                f"no policy at {profile_or_path!r} (profiles: "
                f"{sorted(x.stem for x in POLICIES_DIR.glob('*.yaml'))})"
            )
        raw = yaml.safe_load(p.read_text()) or {}
        profile = str(raw.get("profile", p.stem))
        caps = {**DEFAULT_CAPS, **(raw.get("caps") or {})}
        answers = {
            str(k): (v if isinstance(v, dict) else {"answer": v})
            for k, v in (raw.get("answers") or {}).items()
        }
        uncovered = str(
            raw.get("uncovered") or ("stop" if profile == "benchmark" else "pause")
        )
        if profile == "strict" and answers:
            # a file that asks for something and gets nothing is worse than a
            # file that is refused
            raise ValueError(
                f"{p.name}: profile 'strict' answers no gate, but declares "
                f"{sorted(answers)} — use copilot with those answers, or drop them"
            )
        sha = hashlib.sha256(
            json.dumps(raw, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return cls(
            profile=profile,
            caps=caps,
            answers=answers,
            uncovered=uncovered,
            sha=sha,
            source=str(p),
            raw=raw,
        )

    def decide(self, module: str, ledger, spec=None) -> PolicyAnswer | None:
        """The policy's answer to this gate, or None when it has none.

        None means the caller pauses for a human; under `uncovered: stop` an
        uncovered gate raises PolicyUncovered instead. A cap never widens an
        approval: it turns the answer into a refusal naming the cap, or hands the
        gate back.
        """
        if self.profile == "strict":
            # answers nothing, even if the file declares answers (`load` refuses them)
            return None
        shape = gate_shape(module)
        declared = self.answers.get(module)
        if declared is None and self.profile == "copilot" and shape != "cost":
            # judgment gates are the human's; `uncovered` still decides what
            # "not covered" means
            if self.uncovered == "stop":
                raise PolicyUncovered(
                    module, "judgment-shaped, and this profile answers only cost gates"
                )
            return None
        if declared is None:
            if self.uncovered == "stop":
                raise PolicyUncovered(module, "no declared answer for this gate")
            if shape != "cost":
                return None
            # a cost-shaped gate the profile does not name is answered by shape
            # and recorded as a default, not as a declared decision
            ans, covered_by = {"answer": "y"}, "shape:cost"
        else:
            ans, covered_by = declared, "declared"
        approved = str(ans.get("answer", "y")).lower().startswith("y")
        note = str(ans.get("note", "") or "")

        # Measured, never projected: the cap is spent-so-far from the ledger.
        spent = self.spent_usd(ledger)
        cap = self.caps.get("usd_cap")
        if cap is not None and spent > float(cap):
            why = f"measured agent cost ${spent:.2f} exceeds usd_cap {cap}"
            if self.uncovered == "stop":
                raise PolicyUncovered(module, why)
            return None  # copilot: hand every gate back to the human
        entries = ledger.entries() if ledger is not None else []
        if module == "revision" and approved:
            n_exp = sum(
                1
                for e in entries
                if e.get("event") == "human_gate"
                and e.get("module") == "revision"
                and e.get("approved")
                and e.get("mode") == "policy"
            )
            allow = int(self.caps.get("max_expansions") or 0)
            if n_exp >= allow:
                return PolicyAnswer(
                    False,
                    f"policy cap max_expansions={allow} reached",
                    "cap:max_expansions",
                )
        if module.endswith(COST_GATE_SUFFIXES):
            granted = sum(
                int(e.get("granted") or 0)
                for e in entries
                if e.get("event") == "redraft_grant"
            )
            allow = int(self.caps.get("redraft_grants") or 0)
            if granted >= allow:
                return PolicyAnswer(
                    False,
                    f"policy cap redraft_grants={allow} reached",
                    "cap:redraft_grants",
                )
            if approved and gate_note.key_int(note, "n") is None:
                note = f"{note} n={allow - granted}".strip()
        if module == "cost_boundary_estimation" and approved:
            n = self.caps.get("n_starts")
            if n and gate_note.key_int(note, "n") is None:
                note = f"{note} n={int(n)}".strip()
        return PolicyAnswer(approved, note.strip(), covered_by)

    @staticmethod
    def spent_usd(ledger) -> float:
        """Agent cost measured so far, from the ledger. A stub run spends 0."""
        entries = ledger.entries() if ledger is not None else []
        return sum(
            float(e.get("cost_usd") or 0)
            for e in entries
            if e.get("event") == "agent_call"
        )

    def clamp_rounds(self, max_rounds: int | None) -> int | None:
        """Apply the policy's round cap: it may lower `max_rounds`, never raise it.

        `max_rounds=None` (no cap) becomes the policy cap when one is set.
        """
        cap = self.caps.get("max_rounds")
        if cap is None:
            return max_rounds
        return int(cap) if max_rounds is None else min(int(max_rounds), int(cap))

    def describe(self) -> str:
        return (
            f"policy {self.profile} ({self.sha}) from {Path(self.source).name}"
            f" · uncovered gate: {self.uncovered}"
        )


def write_default_profiles() -> None:
    """Write the three shipped profiles to workflows/policies/."""
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    (POLICIES_DIR / "strict.yaml").write_text(
        """# strict — every human gate pauses for a live human; the policy answers nothing.
profile: strict
caps: {}
answers: {}
uncovered: pause
"""
    )
    (POLICIES_DIR / "copilot.yaml").write_text(
        """# copilot (default) — cost-shaped gates are answered by policy under the caps;
# judgment-shaped gates (intent, scope/axes, expansion, stop-vs-revise, verdict)
# pause for the human. The overnight unit: run to the next judgment gate.
profile: copilot
caps:
  usd_cap: 20.0          # measured agent cost above this hands every gate back
  max_expansions: 1      # expansion purchases policy may make per run
  redraft_grants: 1      # extra redraft attempts policy may grant per run
  n_starts: null         # null = the spec's proposed start count
answers:
  assembly_cost_boundary: {answer: y}
  cost_boundary_estimation: {answer: y}
  evaluation_profiling_gate: {answer: y}
  model_redraft_budget: {answer: y}
  model_expansion_redraft_budget: {answer: y}   # cost-shaped, like the other budget gates
  data_redraft_budget: {answer: y}
  # the S3 gate at the failure point. `y` grants one more attempt to the
  # attributed agent, exactly as at s1/s2 — never a fallback: a fallback
  # changes what the run builds, so pre-answering one unattended is a decision
  # this profile leaves to a person.
  assembly_redraft_budget: {answer: y}
uncovered: pause
"""
    )
    (POLICIES_DIR / "benchmark.yaml").write_text(
        """# benchmark — no human exists. Every gate reached must be covered here; an
# uncovered gate stops the run honestly (exit 1, "policy did not cover gate X").
# A benchmark run is fully specified by (testcase, workflow spec, this file).
profile: benchmark
caps:
  usd_cap: 50.0
  max_expansions: 1      # policy must not become an unbounded mechanism-buying machine
  redraft_grants: 1
  n_starts: null
answers:
  intent: {answer: y}
  model_scope: {answer: y, note: "tier: all"}   # capped by search.max_models
  model_base_scope: {answer: y}                       # the optional base gate — no human to look at the base
  assembly_cost_boundary: {answer: y}
  cost_boundary_estimation: {answer: y}
  evaluation_profiling_gate: {answer: y}
  revision: {answer: y}                     # then declined once max_expansions is reached
  revision_proposal_stop_vs_revise: {answer: n}
  revision_proposal: {answer: y}
  evaluation_verdict: {answer: y}                          # signed: policy(<sha>), never as a human
  # a benchmark has no human to judge whether a crossed convergence check
  # is expected for this model, and accepting one unattended would let an
  # unconverged fit become a recorded result. It stops instead — the failure is
  # in the ledger with the check that crossed.
  estimation_convergence: {answer: n}
  model_redraft_budget: {answer: y}
  model_expansion_redraft_budget: {answer: y}   # one more attempt for the candidate expansions, like s1/s2
  data_redraft_budget: {answer: y}
  assembly_redraft_budget: {answer: y}   # one more attempt, like s1/s2; never a fallback
uncovered: stop
"""
    )


if __name__ == "__main__":
    write_default_profiles()
    print("wrote", sorted(p.name for p in POLICIES_DIR.glob("*.yaml")))
