"""What was already tried, and the advisory "untested first" rule.

  1. the record covers every round's fitted models and every declared axis;
  2. untested axes reach the human's card, free ones marked;
  3. a proposal accounts for every untested axis: fit it, or rule it out with a reason;
  4. the tried-models archive is opt-in, snapshotted into the run, its sha recorded;
  5. the scorer refuses an archive-fed run unless told otherwise;
  6. a gap is a card line, not a refusal;
  7. the context note, the contract and the skill state the same advisory rule;
  8. the archive stays out of the declared input identity;
  9. only a run under the user's runs/ folder appends to it; any other run
     appends nothing and ledgers why.

    uv run python tests/tried_models_unit.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import RecordingLedger  # noqa: E402

from octomod import config  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.workflow_modules.model import tried_models as T  # noqa: E402
from tests._record import ledger_rows, record_at, rnd, run_root  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR


def _run(tmp: Path, name: str = "run"):
    """Round 0 only DECLARES three axes; round 1 enumerates two expansion axes.
    `tmp` is a directory; the run is one record file `<name>.h5` in it."""
    root = record_at(tmp / name)

    def write(rel: str, obj) -> None:
        (root / rel).put(obj)

    # round 0: candidates fitted, three axes declared and none of them bought
    write(
        "rounds/round_0/space/declared",
        [
            {
                "id": "bx11_offtarget",
                "priority": 1,
                "question": "does BX-11 hit KinA?",
                "adds_parameters": [{"id": "f_bx11"}],
            },
            {
                "id": "dose_saturation",
                "priority": 2,
                "question": "does the dose saturate?",
                "adds_parameters": [{"id": "Km_u"}],
            },
            {
                "id": "pool_returns",
                "priority": 3,
                "question": "does ProD return to PreC?",
                "adds_parameters": [],
            },
        ],
    )
    write(
        "rounds/round_0/evaluation",
        {
            "discrimination": {
                "winner": "M2_parallel",
                "criterion": "AIC",
                "candidates": [
                    {"id": "M1_designed", "delta_aic": 33.0, "akaike_weight": 0.0},
                    {"id": "M2_parallel", "delta_aic": 0.0, "akaike_weight": 1.0},
                ],
            }
        },
    )
    write(
        "rounds/round_0/expansion",
        {
            "expanded": True,
            "from_winner": "M2_parallel",
            "axes": ["feedback", "saturable_turnover"],
        },
    )
    # round 1: the bought axes are enumerated and one combination wins
    write(
        "rounds/round_1/space/axes",
        [
            {"id": "feedback", "priority": 1, "adds_parameters": [{"id": "K_fb"}]},
            {
                "id": "saturable_turnover",
                "priority": 2,
                "adds_parameters": [{"id": "Km"}],
            },
        ],
    )
    write(
        "rounds/round_1/evaluation",
        {
            "discrimination": {
                "winner": "feedback+saturable_turnover",
                "criterion": "AIC",
                "candidates": [
                    {"id": "base", "delta_aic": 52.0, "akaike_weight": 0.0},
                    {"id": "feedback", "delta_aic": 27.2, "akaike_weight": 0.0},
                    {
                        "id": "feedback+saturable_turnover",
                        "delta_aic": 0.0,
                        "akaike_weight": 1.0,
                    },
                ],
            }
        },
    )
    return root


def test_the_record_covers_the_whole_run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="c18_rec_"))
    try:
        root = _run(tmp)
        fitted = T.models_fitted_this_run(root)
        rounds = sorted({r["round"] for r in fitted})
        assert rounds == [0, 1], (
            f"the expansion payload must see every round, saw {rounds} — a "
            f"mechanism rejected in round 0 was invisible in round 2"
        )
        assert any(r["model"] == "M1_designed" and r["round"] == 0 for r in fitted)
        base = {r["model"]: r["base_model"] for r in fitted}
        assert base["feedback"] == "M2_parallel", (
            "a verdict is context-dependent, so every row names the base it " "stood on"
        )

        axes = T.declared_axes_this_run(root)
        by_id = {a["id"]: a for a in axes}
        assert len(axes) == 5, sorted(by_id)
        assert by_id["pool_returns"]["status"] == "unbought"
        assert by_id["pool_returns"]["free"] is True, (
            "an axis adding no parameter is FREE: one calibration, cannot "
            "overfit, so leaving it untested is never a saving"
        )
        assert by_id["feedback"]["status"] == "selected"
        assert by_id["feedback"]["best_delta"] == 0.0
        # a discrimination round records what it declared even though it
        # bought candidates rather than axes
        assert by_id["bx11_offtarget"]["declared_in_round"] == 0

        # free-and-untested sorts to the top, because it is the cheapest thing
        # left to try
        assert axes[0]["id"] == "pool_returns", [a["id"] for a in axes]
        assert [a["status"] for a in axes][:3] == ["unbought"] * 3
        print(
            f"  record        {len(fitted)} models over 2 rounds, "
            f"{len(axes)} axes declared, free-and-untested first"
        )
    finally:
        shutil.rmtree(tmp)


def test_untested_axes_reach_the_human() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="c18_card_"))
    try:
        axes = T.declared_axes_this_run(_run(tmp))
        lines = "\n".join(T.untested_card_lines(axes))
        assert "UNTESTED AXES ALREADY DECLARED — 3" in lines
        assert "pool_returns" in lines and "FREE" in lines
        assert "cannot overfit" in lines, "say why free changes the decision"
        assert "does ProD return to PreC?" in lines, "the question, not just the id"
        assert T.untested_card_lines([]) == [], "no untested axes, no section"
        assert (
            T.untested_card_lines([{"id": "x", "status": "selected", "free": True}])
            == []
        )
        print("  card          the untested axes are named, free ones marked")
    finally:
        shutil.rmtree(tmp)


def test_a_proposal_must_account_for_every_untested_axis() -> None:
    """Fit it, or rule it out with a reason. Nothing else counts."""
    untested = {"pool_returns", "bx11_offtarget"}
    both = [{"id": "pool_returns"}, {"id": "bx11_offtarget"}]

    assert T.unaccounted_untested({"axes": both}, untested) == set()
    assert (
        T.unaccounted_untested(
            {
                "untested_axes_addressed": [
                    {
                        "id": "pool_returns",
                        "action": "ruled_out",
                        "why": "no droop there",
                    },
                    {
                        "id": "bx11_offtarget",
                        "action": "ruled_out",
                        "why": "arms agree",
                    },
                ]
            },
            untested,
        )
        == set()
    )
    # claiming to fit without returning the axis is a claim, not a fit
    assert (
        T.unaccounted_untested(
            {"untested_axes_addressed": [{"id": "pool_returns", "action": "fit"}]},
            untested,
        )
        == untested
    )
    # a refusal with no reason is not an argument
    assert (
        T.unaccounted_untested(
            {
                "untested_axes_addressed": [
                    {"id": "pool_returns", "action": "ruled_out", "why": "   "}
                ]
            },
            untested,
        )
        == untested
    )
    # proposing a brand new law while ignoring both leaves both unaccounted for
    assert T.unaccounted_untested({"axes": [{"id": "a_new_law"}]}, untested) == untested
    assert T.unaccounted_untested({}, set()) == set(), "nothing untested, nothing owed"
    print(
        "  rule          fit it or rule it out with a reason; a claim is not " "a fit"
    )


class _Ctx:
    """Just enough run context for the archive functions."""

    def __init__(self, root: Node, testcase_dir: Path, opted_in: bool):
        self.root = root
        # `testcase_dir` is what the run reads (its materialised input); the
        # archive lives beside the source case (or under
        # <runs>/_projects/<project>/), so the fixture supplies both, as the
        # orchestrator does.
        self.testcase_dir = testcase_dir
        self.source_dir = testcase_dir
        self.project = testcase_dir.name
        self.round_idx = 0
        self.cache: dict = {}
        self.ledger = RecordingLedger()
        self.spec = type(
            "S",
            (),
            {
                "get": staticmethod(
                    lambda k, d=None: opted_in if k == "search.use_tried_log" else d
                )
            },
        )()


def test_the_archive_is_opt_in_and_recorded() -> None:
    """The archive (it unblinds a run) is off by default; on, it is snapshotted."""
    tmp = Path(tempfile.mkdtemp(prefix="c18_arch_"))
    try:
        run, tc = record_at(tmp / "run"), tmp / "case"
        tc.mkdir()
        (run / "run").put({})
        T.log_path(tc).write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "run_id": "earlier",
                            "model": "alt_catalysis",
                            "delta": 33.0,
                            "axes_on": ["alt_catalysis"],
                            "base_model": "B",
                            "axes_detail": {
                                "alt_catalysis": {"patch": {"replace_reaction": "J3"}}
                            },
                        }
                    ]
                }
            )
        )

        assert (
            T.snapshot_if_enabled(_Ctx(run, tc, False)) is None
        ), "the archive must be OFF unless the spec says otherwise"
        assert not (run / "tried_log_snapshot").exists()

        ctx = _Ctx(run, tc, True)
        snap = T.snapshot_if_enabled(ctx)
        assert snap and len(snap["entries"]) == 1
        assert (run / "tried_log_snapshot").exists(), (
            "a consumed archive must be copied into the run, or a replay reads "
            "a different archive than the run did"
        )
        meta = (run / "run").get()
        assert meta["tried_log_consumed"]["n_entries"] == 1
        assert meta["tried_log_consumed"]["sha"], "the snapshot's sha is the provenance"
        assert any(r["event"] == "tried_log_consumed" for r in ctx.ledger.rows)
        # taken once, however many cards ask
        T.snapshot_if_enabled(ctx)
        assert sum(r["event"] == "tried_log_consumed" for r in ctx.ledger.rows) == 1

        # a resemblance is EVIDENCE on the card, never a filter
        axes = [
            {"id": "alt_catalysis", "on_antimony_patch": {"replace_reaction": "J3"}},
            {"id": "brand_new", "on_antimony_patch": {"replace_reaction": "J9"}},
        ]
        lines = "\n".join(T.resemblance_lines(axes, snap))
        assert "alt_catalysis" in lines and "earlier" in lines
        assert "brand_new" not in lines, "only axes the archive has seen"
        assert T.resemblance_lines(axes, None) == []
        print(
            "  archive       opt-in, snapshotted once, sha recorded, "
            "resemblance is evidence"
        )
    finally:
        shutil.rmtree(tmp)


def test_the_scorer_refuses_an_archive_fed_run() -> None:
    """Scoring a non-blind run measures the archive, not the system."""
    import subprocess

    src = (REPO / "tests" / "score_against_truth.py").read_text()
    assert "--allow-archive" in src and "REFUSING TO SCORE" in src

    rid = "c18_scorer_probe"
    root = run_root(rid, RUNS)  # the probe run is one record file
    root.store.remove()
    try:
        (rnd(root, 0) / "evaluation").put(
            (
                {
                    "goal": "mechanism_discrimination",
                    "discrimination": {
                        "winner": "w",
                        "decisive": True,
                        "indistinguishable": ["w"],
                        "candidates": [
                            {
                                "id": "w",
                                "aic": 1.0,
                                "delta_aic": 0.0,
                                "akaike_weight": 1.0,
                            }
                        ],
                    },
                }
            ),
        )
        (root / "run").put({"tried_log_consumed": {"sha": "abc123", "n_entries": 4}})
        cmd = [
            sys.executable,
            str(REPO / "tests" / "score_against_truth.py"),
            "--run-id",
            rid,
            "--testcase",
            str(REPO / "testcase" / "abcd_mechanism"),
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
        assert out.returncode == 1, out.stdout[-400:]
        assert "REFUSING TO SCORE" in out.stdout and "not blind" in out.stdout
        assert "abc123" in out.stdout, "name the archive it read"

        allowed = subprocess.run(
            cmd + ["--allow-archive"], capture_output=True, text=True, cwd=REPO
        )
        assert (
            "REFUSING TO SCORE" not in allowed.stdout
        ), "--allow-archive must let a deliberate archive measurement through"
        print("  scorer        refuses an archive-fed run unless told otherwise")
    finally:
        root.store.remove()


def test_a_gap_is_a_card_line_not_a_refusal() -> None:
    """The rule is advisory: the card says, per axis, what the proposal did about it."""
    tmp = Path(tempfile.mkdtemp(prefix="c18_verdicts_"))
    try:
        axes = T.declared_axes_this_run(_run(tmp))
        open_ids = [a["id"] for a in T.untested(axes)]
        assert len(open_ids) == 3, open_ids

        # a proposal that fits one, argues one away and ignores one
        proposal = {
            "axes": [{"id": open_ids[0]}],
            "untested_axes_addressed": [
                {"id": open_ids[0], "action": "fit"},
                {
                    "id": open_ids[1],
                    "action": "ruled_out",
                    "why": "no droop in that arm",
                },
            ],
        }
        lines = T.untested_verdict_lines(proposal, axes)
        joined = "\n".join(lines)
        assert len(lines) == 3, joined
        assert f"{open_ids[0]}: FITTED" in joined, joined
        assert f"{open_ids[1]}: ruled out by the agent: no droop" in joined, joined
        assert "STILL UNACCOUNTED FOR" in joined and open_ids[2] in joined, joined
        assert "your call" in joined, (
            "the line must say whose decision it is — that is what the line "
            f"is for: {joined}"
        )

        # and the card agrees with the definition of "accounted for", rather
        # than carrying a second copy of it
        assert T.unaccounted_untested(proposal, set(open_ids)) == {open_ids[2]}
        assert T.untested_verdict_lines({}, []) == [], "no untested axes, no lines"
        # a claim to fit without returning the axis reads as unaccounted here too
        claim_only = {"untested_axes_addressed": [{"id": open_ids[0], "action": "fit"}]}
        assert all(
            "STILL UNACCOUNTED FOR" in ln
            for ln in T.untested_verdict_lines(claim_only, axes)
        ), T.untested_verdict_lines(claim_only, axes)
        print("  advisory      each untested axis gets a verdict, gaps say 'your call'")
    finally:
        shutil.rmtree(tmp)


def test_the_three_surfaces_say_the_same_thing() -> None:
    """The note, the contract and the skill all carry the rule; none refuses."""
    surfaces = {
        "context note (tried_models.UNTESTED_FIRST_NOTE)": T.UNTESTED_FIRST_NOTE,
        "output contract (agents/__init__.py)": (
            REPO / "octomod" / "agents" / "__init__.py"
        ).read_text(),
        "skill (skills/revision.md)": (REPO / "skills" / "revision.md").read_text(),
    }
    for where, text in surfaces.items():
        assert "untested_axes_addressed" in text, f"{where} never names the field"
        assert "cannot overfit" in text, (
            f"{where} does not say why a free axis is not priced out — the "
            f"reason the rule exists at all"
        )
        assert "advisory" in text.lower(), f"{where} does not say it is advisory"
        assert (
            "human decides" in text or "human decides" in text.lower()
        ), f"{where} does not say who decides instead"
    # and no surface may still threaten a refusal
    for where, text in surfaces.items():
        window = text
        if where.startswith("output contract"):
            window = text.split("untested_axes_addressed", 1)[1][:1200]
        for promise in ("is refused", "asked again, with the missing"):
            assert promise not in window, (
                f"{where} still promises enforcement ({promise!r}) that was "
                f"removed: the ask is advisory"
            )
    print("  one rule      note, contract and skill all say advisory, none refuses")


def test_the_archive_stays_out_of_the_declared_identity() -> None:
    """The archive is off by default, gitignored, and outside the input identity."""
    spec = (REPO / "workflows" / "default.yaml").read_text()
    assert "use_tried_log: false" in spec, "the archive must be OFF by default"
    ignore = (REPO / ".gitignore").read_text()
    assert "testcase/*/tried_models.json" in ignore, (
        "the archive is engine-written and grows every run; committing it "
        "would dirty the tree on every battery"
    )
    # Behavioural, not a grep: the input sha must not move as the archive grows.
    from octomod.orchestration import run_guard

    with tempfile.TemporaryDirectory() as tmp:
        case = Path(tmp)
        (case / "intent.yaml").write_text("question: q\n")
        before = run_guard.input_sha(case)
        T.log_path(case).write_text(json.dumps({"entries": [{"run_id": "x"}]}))
        assert run_guard.input_sha(case) == before, (
            "the archive must be OUT of the input identity, or appending to it "
            "makes a case drift from itself and refuses the next resume"
        )
        assert "tried_models.json" not in run_guard.manifest(case), (
            "and it must not appear in the recorded manifest either, or a "
            "refused resume would name it as the file that moved"
        )
    # a project run's archive lives under the runs directory, ignored wholesale
    assert "runs/" in ignore, (
        "runs/_projects/<project>/tried_models.json is covered by runs/ being "
        "ignored; if that ever stops being true this archive starts getting "
        "committed"
    )
    print("  declarations  archive off by default, ignored, out of the identity")


def test_only_a_run_under_the_users_runs_folder_appends() -> None:
    """A battery, sweep or stub run elsewhere leaves the case's archive alone."""
    from types import SimpleNamespace

    from octomod.orchestration.orchestrator import Orchestrator

    tmp = Path(tempfile.mkdtemp(prefix="c18_where_"))
    saved = config.USER_RUNS_DIR
    try:
        elsewhere, case = tmp / "elsewhere", tmp / "case"
        run = _run(elsewhere, "r_elsewhere")  # elsewhere/r_elsewhere.h5
        (run / "run").put({})
        case.mkdir()

        def append() -> RecordingLedger:
            ledger = RecordingLedger()
            Orchestrator._append_tried_log(
                SimpleNamespace(
                    store=run.store,
                    root=run,
                    testcase_dir=case,
                    project=case.name,
                    ledger=ledger,
                    ctx=SimpleNamespace(round_idx=1),
                )
            )
            return ledger

        config.USER_RUNS_DIR = tmp / "users_runs"
        ledger = append()
        assert not T.log_path(case).exists(), (
            "a run outside the user's runs/ appended its fits to the case's "
            "archive, where a later real run would read them as tried"
        )
        notes = [r.get("note", "") for r in ledger.rows if r["event"] == "note"]
        assert any("not appended" in n for n in notes), notes

        # the same call site, with the run under the user's runs folder
        config.USER_RUNS_DIR = elsewhere
        ledger = append()
        entries = json.loads(T.log_path(case).read_text()).get("entries") or []
        assert entries and {e["run_id"] for e in entries} == {"r_elsewhere"}, entries
        notes = [r.get("note", "") for r in ledger.rows if r["event"] == "note"]
        assert any(f"appended {len(entries)} model(s)" in n for n in notes), notes
    finally:
        config.USER_RUNS_DIR = saved
        shutil.rmtree(tmp)
    print(
        "  where         a run outside the user's runs/ appends nothing and "
        "says so; under it, the archive is appended"
    )


# --- called from the smokes that already own the runs -----------------------


def _root_of(run) -> Node:
    """The smokes hand over a record root; a runs/<id> path still resolves."""
    if isinstance(run, Node):
        return run
    return run_root(Path(run).name, Path(run).parent)


def check_expansion_payload(root: Node) -> None:
    """The tried-models payload reaches the agent, read off a real run's prompt."""
    root = _root_of(root)
    prompt = (rnd(root, 0) / "agent_calls").child("revision") / "prompt"
    assert prompt.exists(), f"no expansion prompt in {root}"
    text = prompt.text()
    for key in (
        "models_fitted_this_run",
        "declared_axes",
        "untested_axes",
        "untested_first",
    ):
        assert f"## {key}" in text or f'"{key}"' in text, (
            f"the expansion payload does not carry {key} — it is in the code "
            f"but not in the prompt"
        )
    assert "already_tried_axes" not in text, (
        "`already_tried_axes` is in the payload: it must carry the whole run's "
        "fitted models, not just this round's axis ids"
    )
    assert "UNTESTED FIRST" in text, "the ask itself is missing from the prompt"
    assert (
        "advisory" in text
    ), "the prompt still presents the ask as enforced; it is advisory"
    stale = [
        e for e in ledger_rows(root) if e.get("gate_id") == "expansion_untested_first"
    ]
    assert not stale, (
        f"an untested-first gate fired: {stale} — the engine has no such gate, "
        f"by decision: a gap belongs on the human's card"
    )
    print(
        "  payload       the whole tried-models payload is in the prompt, no gate row"
    )


def check_declared_axes_record(root: Node) -> None:
    """A discrimination round writes what it DECLARED to its own record
    (`space/declared`)."""
    root = _root_of(root)
    node = rnd(root, 0) / "space/declared"
    assert node.exists(), f"no rounds/round_0/space/declared in {root}"
    declared = node.get()
    assert declared and all(a.get("id") for a in declared), declared
    # The record holds the DECLARATIONS; each axis's status is derived from the
    # run's fitted models, so the record must round-trip into that status.
    resolved = {a["id"]: a for a in T.declared_axes_this_run(root)}
    missing = {str(a["id"]) for a in declared} - set(resolved)
    assert not missing, (
        f"declared axes the status reader cannot see: {sorted(missing)} — the "
        f"record exists but nothing can read it back"
    )
    assert all(
        r["status"] in ("unbought", "rejected", "selected") for r in resolved.values()
    ), resolved
    status = {k: v["status"] for k, v in resolved.items()}
    print(f"  record        space/declared -> {status}")


if __name__ == "__main__":
    test_the_record_covers_the_whole_run()
    test_untested_axes_reach_the_human()
    test_a_proposal_must_account_for_every_untested_axis()
    test_the_archive_is_opt_in_and_recorded()
    test_a_gap_is_a_card_line_not_a_refusal()
    test_the_three_surfaces_say_the_same_thing()
    test_the_archive_stays_out_of_the_declared_identity()
    test_only_a_run_under_the_users_runs_folder_appends()
    print(
        "TRIED MODELS UNIT OK — the whole run is on the record, and an "
        "untested axis is fitted, argued away, or handed to the human"
    )
