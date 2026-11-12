"""Residual structure and noise evidence travel in one payload, to both agents.

  1. |residual|-vs-signal correlation separates proportional from additive noise;
  2. the QQ tail summary tells heavier, lighter and close tails apart;
  3. the base-id convention gives a single-model round a usable key;
  helpers the smoke suites call on the prompts a real run sent:
  4. the observation block is keyed by observable and carries numbers;
  5. the interpreter prompt stays under its byte ceiling, its curves sent as columns;
  6. the interpreter and the proposer are sent the same residual payload.

    uv run python tests/observation_evidence_unit.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.evaluation import residuals  # noqa: E402


def _corr(sim: np.ndarray, resid: np.ndarray) -> float:
    """The statistic as the series builder computes it."""
    return float(np.corrcoef(np.abs(resid), np.abs(sim))[0, 1])


def test_the_statistic_separates_proportional_from_additive_noise() -> None:
    """|residual| growing with the signal is the multiplicative signature."""
    rng = np.random.default_rng(7)
    sim = np.linspace(0.1, 10.0, 60)

    proportional = 0.2 * sim * rng.standard_normal(60)
    additive = 0.2 * rng.standard_normal(60)

    c_prop, c_add = _corr(sim, proportional), _corr(sim, additive)
    assert c_prop > 0.4, f"proportional noise should correlate: {c_prop:.3f}"
    assert abs(c_add) < 0.3, f"additive noise should not: {c_add:.3f}"
    assert c_prop > c_add + 0.3, (c_prop, c_add)
    print(
        f"  statistic     proportional {c_prop:+.2f} vs additive {c_add:+.2f} — "
        f"the signature separates"
    )


def test_the_qq_tail_summary_says_which_way_it_bends() -> None:
    """Heavy and light tails are different complaints about the assumption."""
    theo = list(np.linspace(-2.2, 2.2, 24))
    assert residuals._qq_tail({}) is None, "no qq data, no claim"
    assert residuals._qq_tail({"qq": {"theoretical": [1, 2], "sample": [1, 2]}}) is None

    same = residuals._qq_tail({"qq": {"theoretical": theo, "sample": theo}})
    assert same == "close to the assumed distribution", same
    heavy = residuals._qq_tail(
        {"qq": {"theoretical": theo, "sample": [v * 2.0 for v in theo]}}
    )
    assert heavy == "heavier tails than assumed", heavy
    light = residuals._qq_tail(
        {"qq": {"theoretical": theo, "sample": [v * 0.3 for v in theo]}}
    )
    assert light == "lighter tails than assumed", light
    print("  qq tail       heavier, lighter and close are told apart")


def _prompt(root: Node, round_idx: int, role: str) -> Node:
    """The prompt a run sent to `role` in round `round_idx`."""
    return (tree.round_node(root, round_idx) / "agent_calls").child(role) / "prompt"


def payload_of(prompt: Node, block: str = "residual_diagnostics") -> dict:
    """Return one `## <block>` JSON input from a prompt a real run sent."""
    text = prompt.text()
    m = re.search(rf"\n## {block}\n```json\n(.*?)\n```", text, re.S)
    assert m, f"{prompt.key} carries no {block} block"
    return json.loads(m.group(1))


REQUIRED_FIELDS = (
    "noise_check",
    "qq_tail_deviation",
    "fitted_sigma_vs_replicate_floor",
    "abs_residual_vs_signal_corr_by_condition",
    "abs_residual_vs_signal_corr_median",
)

# The keys of a candidate record: one showing up as an "observable" means the
# builder iterated the record instead of its per-series mapping.
RECORD_KEYS = {"per_series", "sigma_vs_replicate_floor", "error", "note"}


def check_observation_block(root: Node, round_idx: int, path_name: str) -> None:
    """Assert the sent observation block is keyed by observable and has numbers."""
    payload = payload_of(_prompt(root, round_idx, "interpretation"))
    oe = payload["observation_evidence"]
    per_obs = oe.get("per_observable") or {}
    assert per_obs, f"{path_name}: observation_evidence carries no observable at all"

    stray = set(per_obs) & RECORD_KEYS
    assert not stray, (
        f"{path_name}: {sorted(stray)} appear as observable ids — the builder "
        f"iterated the candidate record instead of its per_series mapping"
    )
    # Exact: the observables are precisely those the focus model's series name
    focus = oe["for_model"]
    series = (payload["per_candidate_residuals"].get(focus) or {}).get(
        "per_series"
    ) or {}
    assert series, f"{path_name}: no per_series for the focus model {focus!r}"
    assert set(per_obs) == {k.split("@")[0] for k in series}, (
        f"{path_name}: {sorted(per_obs)} != the observables in the series "
        f"{sorted({k.split('@')[0] for k in series})}"
    )

    for obs_id, rec in per_obs.items():
        missing = [f for f in REQUIRED_FIELDS if f not in rec]
        assert not missing, f"{path_name}: {obs_id} is missing {missing}"

    # An empty measurement is not a pass: the block must carry NUMBERS, or it
    # is a heading an agent is told to read and cannot.
    filled = [
        obs_id
        for obs_id, rec in per_obs.items()
        if (rec.get("noise_check") or {}).get("p_value") is not None
        and (rec.get("fitted_sigma_vs_replicate_floor") or {}).get("ratio") is not None
        and rec.get("abs_residual_vs_signal_corr_by_condition")
    ]
    assert filled, (
        f"{path_name}: every observable's block is empty — the fields are "
        f"present and carry nothing: {json.dumps(per_obs)[:300]}"
    )

    guide = payload["how_to_read_this"]
    for phrase in (
        "differential diagnosis",
        "OBSERVATION axis",
        "propose STRUCTURE",
        "absorbed something into the noise",
    ):
        assert phrase in guide, f"{path_name}: how_to_read_this does not say: {phrase}"
    print(
        f"  observation   {path_name}: {sorted(per_obs)} keyed by observable, "
        f"{len(filled)} carrying numbers"
    )


# Byte ceiling on the interpreter prompt of the largest fixture round
# (search_smoke round 0, 130,578 bytes) with ~5 % room: reverting the compact
# encoding (~19 kB) crosses it, an innocent change does not.
INTERPRETER_PROMPT_CEILING = 137_000


def check_interpreter_prompt_ceiling(root: Node, round_idx: int) -> None:
    """Assert the interpreter prompt is under the ceiling, its curves as columns."""
    prompt = _prompt(root, round_idx, "interpretation")
    n = len(prompt.text().encode())
    assert n <= INTERPRETER_PROMPT_CEILING, (
        f"the interpreter prompt is {n:,} bytes, over the "
        f"{INTERPRETER_PROMPT_CEILING:,} ceiling item 17 established — the "
        f"payload has grown back"
    )
    payload = payload_of(prompt)
    # The encoding, not only the size: not every series carries a curve, so
    # every curve present must be columns.
    curves = [
        s["fit_over_time"]
        for c in payload["per_candidate_residuals"].values()
        for s in (c.get("per_series") or {}).values()
        if isinstance(s, dict) and "fit_over_time" in s
    ]
    assert curves, "no series carries a curve at all — item 18 thinned them away"
    bad = [c for c in curves if not isinstance(c, dict)]
    assert not bad, f"{len(bad)} of {len(curves)} curves are still lists: {bad[:1]}"
    assert (
        "POSITIONALLY ALIGNED" in payload["how_to_read_this"]
    ), "the columns are sent without the sentence that says they are aligned"
    print(f"  prompt bytes  {n:,} of a {INTERPRETER_PROMPT_CEILING:,} ceiling")


def check_same_payload_as_proposer(root: Node, round_idx: int) -> None:
    """Assert the interpreter was sent the same residual payload as the proposer."""
    proposer = _prompt(root, round_idx, "revision")
    interpreter = _prompt(root, round_idx, "interpretation")
    assert proposer.exists() and interpreter.exists(), (
        f"round {round_idx} does not have both prompts: "
        f"{proposer.exists()} / {interpreter.exists()}"
    )
    a, b = payload_of(proposer), payload_of(interpreter)
    assert set(a) == set(b), (sorted(a), sorted(b))
    differing = [
        k
        for k in a
        if json.dumps(a[k], sort_keys=True) != json.dumps(b[k], sort_keys=True)
    ]
    assert not differing, (
        f"the interpreter and the proposer were sent DIFFERENT "
        f"residual_diagnostics: {differing}"
    )
    print(f"  same payload  proposer and interpreter agree on all {len(a)} blocks")


def test_the_single_model_round_uses_a_usable_key() -> None:
    """The base-id convention: the shortest id wins, a lone model is 'model'."""
    from octomod.workflow_modules.evaluation.residuals import base_id_of

    assert base_id_of(["model"]) == "model"
    assert base_id_of(["base", "basal_route", "product_feedback"]) == "base"
    assert base_id_of([]) == ""
    print("  base id       shortest id wins, and a lone model is 'model'")


if __name__ == "__main__":
    test_the_statistic_separates_proportional_from_additive_noise()
    test_the_qq_tail_summary_says_which_way_it_bends()
    test_the_single_model_round_uses_a_usable_key()
    print(
        "OBSERVATION EVIDENCE UNIT OK — both evidence classes in one "
        "payload, and the interpreter sees the fits it interprets"
    )
