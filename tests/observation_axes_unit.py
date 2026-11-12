"""The observation layer is a modelling choice, so assembly agents may declare axes.

  1. both assembly agents are offered `model_space`, and it stays optional;
  2. what they declare is appended to the S1 space and attributed to its author;
  3. a human can pick candidates by index, including ranges;
  4. an index outside the list is dropped, never clamped;
  5. the model-selection note form is declared for the gate cards;
  6. the combined-space card offers only the forms that are honoured;
  7. an observation axis kept at S3 reaches the compile card as the combined
     space, and construction's axes and a bought axis do not;
  8. a candidate set's compile card carries the data flags and the checker's
     summary, as the single model's does.

    uv run python tests/observation_axes_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import CallLedger  # noqa: E402

from octomod.agents import ROLES  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.model import model_space as ms  # noqa: E402
from tests._record import rnd, temp_record  # noqa: E402


class _Ctx:
    def __init__(self, root: Node):
        self.root = root
        self.store = root.store
        self.round = rnd(root, 0)
        self.round_idx = 0
        self.candidate = None
        self.ledger = CallLedger()
        self.spec = {}


def test_both_assembly_agents_may_declare_a_space():
    for role in ("observation", "condition"):
        rs = ROLES[role]
        assert "model_space" in rs.contract, f"{role} is not offered an axis"
        assert "OPTIONAL" in rs.contract, f"{role}: an axis must not be mandatory"
        assert "model_space" not in rs.required_keys, (
            f"{role}: declaring a space became REQUIRED, so an agent with "
            f"nothing to declare would have to invent one"
        )
    print("  offered       both assembly agents may declare axes, optionally")


def test_assembly_axes_append_and_are_attributed(root: Node):
    ctx = _Ctx(root)
    # an S1 space already exists
    ms.space_path(ctx).put([{"id": "structural_axis", "priority": 1}])
    (ctx.round / "shared_assembly").put(
        {
            "observables": [{"observable_id": "obs_x", "maps_to_label": "x_obs"}],
            "noise": [],
            "scaling": [],
            "conditions": [],
        },
    )

    fresh = ms.record_assembly_axes(
        ctx,
        {
            "observation": {
                "model_space": [
                    {
                        "id": "per_timepoint_scaling",
                        "priority": 1,
                        "question": "does the readout carry a background offset?",
                        "default": "off",
                        # the shape `assembly_edit` applies, as in the
                        # end-to-end observation-axis fixture
                        "on_assembly_patch": {
                            "add_offset": {"observable_label": "x_obs"}
                        },
                        "adds_parameters": [],
                    }
                ]
            },
            "condition": {},
        },
        "model m() species x; k = 1; end",
        [{"id": "k"}],
    )
    space = ms.space_path(ctx).get()
    ids = [a["id"] for a in space]
    assert "structural_axis" in ids, f"the S1 axis was replaced: {ids}"
    assert fresh, (
        "the assembly axis was rejected, so this test would have passed "
        "without exercising the append path at all — the reason is in the "
        f"ledger: {ctx.ledger.rows[-1] if ctx.ledger.rows else 'nothing logged'}"
    )
    assert "per_timepoint_scaling" in ids, ids
    got = next(a for a in space if a["id"] == "per_timepoint_scaling")
    assert got.get("declared_by") == "observation", got
    assert got.get("kind") == "observation", got
    print("  appended      the S1 axis survives; the new one names its author")


def test_a_human_can_pick_models_by_index():
    assert ms.parse_model_selection("y models: 6, 9, 10, 12, 25", 32) == [
        6,
        9,
        10,
        12,
        25,
    ]
    assert ms.parse_model_selection("y models: 1-4, 9", 32) == [1, 2, 3, 4, 9]
    assert ms.parse_model_selection("y models: all", 4) == [1, 2, 3, 4]
    for quiet in ("y tier: base", "y axes: scaling", "y", "", None):
        assert ms.parse_model_selection(quiet, 32) is None, quiet
    print("  by index      'models: 6, 9, 10, 12, 25' and ranges both parse")


def test_an_out_of_range_index_is_dropped_not_clamped():
    got = ms.parse_model_selection("y models: 3, 99", 32)
    assert got == [3], f"expected the 99 to be dropped, got {got}"
    assert (
        ms.parse_model_selection("y models: 99, 100", 32) is None
    ), "a selection entirely outside the list must not silently become 'all'"
    print("  out of range  dropped, never clamped onto a model nobody chose")


def test_the_form_is_declared_for_the_cards():
    assert "models:" in ms.MODEL_SELECTION_FORM
    assert "ranges" in ms.MODEL_SELECTION_FORM
    print("  declared      the note form exists for a gate card to print")


def test_the_card_promises_only_what_is_honoured():
    """The combined-space card lists the combinations but offers no unread form."""
    card = "\n".join(
        ms.combined_space_card_lines(
            ["M1", "M2"],
            [
                {
                    "id": "per_timepoint_scaling",
                    "priority": 1,
                    "default": "off",
                    "question": "one scale per time point?",
                    "declared_by": "observation",
                }
            ],
            8,
        )
    )
    assert "COMBINATIONS" in card and "M1  +  per_timepoint_scaling" in card
    assert "RECORDED, not bought" in card, "the card must say what it will not do"
    assert (
        "CAVEAT" in card and "CONDITIONAL" in card
    ), "the sequential caveat is the reason this gate exists"
    for unhonoured in ("models:", "tier: all"):
        assert unhonoured not in card, (
            f"the card offers {unhonoured!r} but nothing consumes it for the "
            f"combined space yet — advertise it when it works, not before"
        )
    assert (
        ms.combined_space_card_lines(["M1"], [], 8) == []
    ), "no observation axes means no second decision to present"
    print("  honest card   shows the combinations, promises only the sequential fit")


class _CardCtx:
    """What the compile card reads from a RunContext, over a real ledger — on
    a record (`root` is the run record's root node)."""

    def __init__(self, root: Node):
        from octomod.orchestration.ledger import Ledger

        self.root = root
        self.store = root.store
        self.round_idx = 0
        self.candidate = None
        self.ledger = Ledger(root)
        self.spec = {"search.max_models": 8}

    @property
    def round(self) -> Node:
        return rnd(self.root, self.round_idx)

    @property
    def work(self) -> Node:
        return tree.work_node(self.round, self.candidate)

    @property
    def gates(self) -> Node:
        return tree.gates_node(self.round, self.candidate)

    @property
    def agent_calls(self) -> Node:
        return self.round / "agent_calls"


def _stage_compile_round(rd: Node, cand_ids: list[str]) -> None:
    """A round after S3: each candidate's s3 marker, the data report, the
    declared space."""
    from octomod.workflow_modules.assembly.engine import checker_summary

    # the shared assembly is audited in the first candidate's pass; the second
    # carries an overlay whose delta audit raised a concern
    audits = [
        ["checker[noise]: ok", "checker[scaling]: ok", "checker[units]: ok"],
        ["checker[offset]: CONCERN — the offset absorbs the basal level"],
    ]
    for i, cid in enumerate(cand_ids):
        marker = tree.markers_node(rd, cid).child("s3")
        marker.put(
            {
                "n_estimated": 5 + i,
                "n_train": 40,
                "n_holdout": 8,
                "checker_summary": checker_summary(audits[i] if i < 2 else []),
                "producer": "agent:assembly",
            }
        )
    (rd / "data" / "report").put(
        {"flags": ["small negative values at early times are noise — kept"]},
    )
    (rd / "space" / "axes").put(
        [
            {"id": "feedback", "kind": "structural", "declared_by": "construction"},
            {
                "id": "readout_offset",
                "kind": "observation",
                "priority": 1,
                "question": "construction's own reading of the readout",
                "declared_by": "construction",
            },
            {
                "id": "per_timepoint_scaling",
                "kind": "observation",
                "priority": 1,
                "default": "off",
                "question": "one scale per time point?",
                "declared_by": "observation",
            },
            {
                "id": "dose_own_rate",
                "kind": "observation",
                "priority": 2,
                "default": "off",
                "question": "does the top dose enter through its own rate?",
                "declared_by": "condition",
            },
            {
                "id": "k_split",
                "kind": "parameter_split",
                "priority": 4,
                "question": "is k the same in every population?",
                "declared_by": "observation",
            },
            {
                "id": "bought_offset",
                "kind": "observation",
                "priority": 3,
                "question": "carried from the previous round and bought",
                "declared_by": "observation",
            },
        ],
    )


def test_the_compile_card_shows_the_assembly_axes():
    """The combined space is on the compile card whenever S3 kept an axis."""
    from octomod.workflow_modules.cost_probe import compile_gate

    with temp_record("card_run") as root:
        rd = rnd(root, 0)
        cands = ["base", "base+bought_offset"]
        _stage_compile_round(rd, cands)
        card = "\n".join(compile_gate.card_lines(_CardCtx(root), cands))
    assert "COMBINATIONS" in card and "THE OBSERVATION LAYER" in card, (
        "an observation axis the assembly agents kept did not reach the compile "
        f"card:\n{card}"
    )
    for aid, author in (
        ("per_timepoint_scaling", "observation"),
        ("dose_own_rate", "condition"),
    ):
        assert f". {aid} (base = off)" in card, f"{aid} is not listed:\n{card}"
        assert f"declared by: {author}" in card, card
    assert "readout_offset" not in card, "construction's axis is the scope gate's"
    assert "k_split" not in card, "a parameter split is not an observation reading"
    assert (
        ". bought_offset (base" not in card
    ), "an axis a candidate carries was bought: it is fitted, not an open choice"
    assert "2 structure(s) x 4 observation variant(s) = 8" in card, card
    print("  compile card  S3's observation axes are shown as the combined space")


def test_the_candidate_card_carries_flags_and_checker():
    from octomod.orchestration.interaction import humangate
    from octomod.workflow_modules.cost_probe import compile_gate

    with temp_record("card_run_flags") as root:
        rd = rnd(root, 0)
        cands = ["M1", "M2"]
        _stage_compile_round(rd, cands)
        lines = compile_gate.card_lines(_CardCtx(root), cands)
        # the decision record is a record key, printed as its show command
        decisions = humangate.show_command(rd / "decisions_md")
    assert lines[:3] == [
        "M1: 5 estimated parameters, 40 training points — battery passed",
        "M2: 6 estimated parameters, 40 training points — battery passed",
        f"full reasoning of every agent: {decisions}",
    ], lines[:3]
    assert "data flags: 1 recorded, none blocking (full list: data/report)" in lines
    assert "M1: independent checker: 3 aspects audited, no concerns" in lines, lines
    concern = "M2: checker[offset]: CONCERN — the offset absorbs the basal level"
    pointer = "  (full checker reasoning: decisions_md · gates/assembly_verification)"
    assert concern in lines and lines.count(pointer) == 1, lines
    assert lines.index(pointer) > lines.index(concern), lines
    assert not any(ln.startswith("M2: independent") for ln in lines), lines
    print("  compile card  a candidate set's card carries the flags and the checker")


if __name__ == "__main__":
    with temp_record() as root:
        test_both_assembly_agents_may_declare_a_space()
        test_assembly_axes_append_and_are_attributed(root)
        test_a_human_can_pick_models_by_index()
        test_an_out_of_range_index_is_dropped_not_clamped()
        test_the_form_is_declared_for_the_cards()
        test_the_card_promises_only_what_is_honoured()
        test_the_compile_card_shows_the_assembly_axes()
        test_the_candidate_card_carries_flags_and_checker()
    print(
        "OBSERVATION AXES UNIT OK — the assembly agents may declare where the "
        "observation layer is open, and a human may pick candidates by hand"
    )
