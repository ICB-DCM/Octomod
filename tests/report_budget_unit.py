"""The render-side prose budgets, without the pipeline.

  1. every number in `reporting.budget` appears in REPORTING.md's budget table;
  2. clipping honours its limit and marks the cut, at a sentence or word boundary;
  3. every budgeted surface holds on overlong input; every clip leaves a fold or link;
  4. §8 is three groups deep, with every subsection under one of them;
  5. the run page leads with the verdict, inside the first screen;
  6. the evidence-tier column speaks in a reader's words;
  7. the gate card caps evidence, never the menu the human chooses from;
  8. a closed profile wider than the determined box fraction is in a third
     epistemics list, on the card, in the markdown and in the report box;
  9. the run page prints each intent verdict's evidence beneath it, in both
     renderings, clipped with a fold in the html and in full in the markdown;
 10. a discrimination round's three epistemic lists carry no profile-derived
     entry, and its box draws no empty third list beside a profiled winner.

    uv run python tests/report_budget_unit.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.orchestration.interaction import humangate  # noqa: E402
from octomod.reporting import budget  # noqa: E402
from octomod.reporting.model_report import _m3_assumptions  # noqa: E402
from octomod.reporting.round_report import (  # noqa: E402
    Round,
    _misfit_evidence,
    _s8_evaluation,
    _s9_epistemics,
    _s10_narrative,
    _s12_gates,
)
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402
from tests._record import record_at, reports_dir, rnd  # noqa: E402

# Where runs are written: `test_runs/` under the battery (run_all.py sets
# OCTOMOD_RUNS_DIR), `runs/` otherwise; a suite never hard-codes `runs/`.
RUNS = config.RUNS_DIR

# A section's default view fits one screen. Asserting that directly is stronger
# than asserting the arithmetic of the budgets meant to deliver it.
ONE_SCREEN = 2000

LONG = (
    "The residuals show clear positive structure at the two highest doses. "
    "That is consistent with a saturating receptor pool, e.g. a Hill term on "
    "the activation leg rather than the mass-action term the draft carries. "
    "A third sentence adds detail that a three-sentence budget must keep. "
    "A fourth sentence must not survive it, and neither must this fifth one, "
    "which exists only to push the paragraph well past every character limit "
    "that the contract in REPORTING.md declares for a default view."
)


def _strip_nested(html: str, tag: str) -> str:
    """Remove every `tag` element and its content, counting depth so nesting holds."""
    open_re = re.compile(rf"<{tag}\b[^>]*>", re.I)
    close = f"</{tag}>"
    out, i = [], 0
    while i < len(html):
        m = open_re.search(html, i)
        if not m:
            out.append(html[i:])
            break
        out.append(html[i : m.start()])
        depth, j = 1, m.end()
        while depth and j < len(html):
            nxt_open = open_re.search(html, j)
            nxt_close = html.find(close, j)
            if nxt_close < 0:
                j = len(html)
                break
            if nxt_open and nxt_open.start() < nxt_close:
                depth += 1
                j = nxt_open.end()
            else:
                depth -= 1
                j = nxt_close + len(close)
        i = j
    return "".join(out)


def visible(html: str) -> str:
    """The default view: the text outside <details>, <svg>, <style> and <script>."""
    out = html
    for tag in ("details", "svg", "style", "script"):
        out = _strip_nested(out, tag)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", out)).strip()


def fake_round(**over) -> Round:
    """A Round with no record behind it: only the fields these sections read.

    Its nodes point into a record file that does not exist (and is never
    created: nothing here writes), so every read degrades to "absent"."""
    r = object.__new__(Round)
    r.root = Node(RunStore(RUNS / "__none__.h5"))
    r.store = r.root.store
    r.rnd = rnd(r.root, 0)
    r.round_idx = 0
    r.cid, r.cids = None, []
    r.work = tree.work_node(r.rnd, None)
    r.model = tree.model_node(r.rnd, None)
    r.report, r.core, r.interp = {}, {}, {}
    r.goal, r.is_md, r.discrimination = "prediction", False, {}
    # `None`, not "unset": "unset" makes the lazy loader go to the record, and
    # this Round has none. A renderer that needs the PEtab tables must cope with
    # not having them — the report is written on a resumed process too.
    r._tables = None
    r._gate_rows = []
    for k, v in over.items():
        setattr(r, k, v)
    r.rows = lambda event, this_round=True: (  # type: ignore[method-assign]
        r._gate_rows if event == "gate" else []
    )
    return r


# ---- 1. the code and the contract agree -----------------------------------
def test_constants_match_reporting_md() -> None:
    table = REPO / "docs" / "REPORTING.md"
    text = table.read_text()
    section = text[text.index("## Prose budgets") :]
    section = section[: section.index("\n## ", 1)]
    numbers = set(re.findall(r"\d+", section))
    declared = {
        name: getattr(budget, name)
        for name in dir(budget)
        if name.isupper() and isinstance(getattr(budget, name), int)
    }
    declared["CARD_EVIDENCE_LINES"] = humangate.CARD_EVIDENCE_LINES
    missing = {n: v for n, v in declared.items() if str(v) not in numbers}
    assert not missing, (
        f"these constants name a number REPORTING.md's budget table does not: "
        f"{missing} — the contract and the code have drifted"
    )
    print(f"  contract agreement: {len(declared)} constants, all published")


# ---- 2. clipping honours its limit and marks the cut ----------------------
def test_clipping() -> None:
    vis, cut = budget.clip_chars(LONG, 160)
    assert cut and len(vis) <= 162, (len(vis), vis)
    assert vis.endswith("…"), vis
    assert vis.rstrip(" …").endswith("."), f"should cut at a sentence end: {vis!r}"

    vis, cut = budget.clip_chars("word " * 80, 40)
    assert cut and len(vis) <= 42 and vis.endswith("…")
    assert not vis.rstrip(" …").endswith(" "), "word-boundary cut leaves no space"

    vis, cut = budget.clip_chars("under the limit", 160)
    assert not cut and vis == "under the limit"

    vis, cut = budget.clip_sentences(LONG, budget.DIAGNOSIS_SENTENCES)
    assert cut and len(budget.sentences(vis)) == budget.DIAGNOSIS_SENTENCES

    assert len(budget.sentences("Uses e.g. an abbreviation. Then ends.")) == 2
    assert budget.fold("s", "   ") == "", "an empty fold must not be rendered"

    nested = budget.fold("outer", "seen-never" + budget.fold("inner", "also-never"))
    assert visible(nested) == "", (
        "a fold inside a fold must count as folded; if this fails the measure "
        "is under-stripping and every budget assertion below is wrong"
    )
    print(
        "  clipping: limits held, cuts marked, abbreviations intact, "
        "nested folds counted as folded"
    )


# ---- 3. every budgeted surface holds its budget --------------------------
def _assert_budgeted(name: str, html: str, limit: int) -> None:
    text = visible(html)
    assert len(text) <= limit, (
        f"{name}: {len(text)} default-visible chars exceeds its {limit} budget\n"
        f"  {text[:200]}"
    )
    if "…" in text:
        assert "<details>" in html or "href=" in html, (
            f"{name}: text is clipped but the section offers no fold and no "
            f"link to the full wording"
        )
    print(f"  {name:26s} {len(text):5d} visible chars (budget {limit}), fold present")


def test_m3_holds_every_per_decision_budget() -> None:
    """M3 is budgeted per DECISION, as the contract promises, not per section."""
    decisions = [
        {
            "decision": f"decision {i}",
            "confidence": "low",
            "rationale": LONG,
            "alternatives_considered": [f"{LONG} alternative {k}" for k in range(4)],
            "question": LONG,
            "evidence": [
                {"source": "literature", "locator": LONG, "supports": LONG}
                for _ in range(5)
            ],
            "evidence_tier": "transferred",
        }
        for i in range(20)
    ]
    html = _m3_assumptions({"decisions": decisions})
    shown = visible(html)

    # 1. only the least-confident DECISIONS_SHOWN rows are in the default view
    rows = re.findall(r"<tr>", _strip_nested(html, "details"))
    assert len(rows) <= budget.DECISIONS_SHOWN + 1, (
        f"{len(rows) - 1} decision rows visible, contract says "
        f"{budget.DECISIONS_SHOWN}"
    )

    # 2. every budgeted part of every visible cell is inside its own limit
    for cls, limit in (
        ("rationale", budget.DECISION_RATIONALE_CHARS),
        ("alts", budget.DECISION_ALTERNATIVES_CHARS),
        ("qnote", budget.DECISION_QUESTION_CHARS),
    ):
        seen = re.findall(
            rf'class="{cls}"[^>]*>(.*?)</(?:div|span)>',
            _strip_nested(html, "details"),
            re.S,
        )
        assert seen, f"no visible {cls} at all — the part vanished, not budgeted"
        for piece in seen:
            text = visible(piece)
            # "alternatives: " is the label, not the budgeted argument
            text = text.removeprefix("alternatives: ")
            assert len(text) <= limit + 4, (
                f"a visible {cls} is {len(text)} chars against a {limit} "
                f"budget: {text[:120]}"
            )

    # 3. at most EVIDENCE_LINES_SHOWN citations per visible cell
    for cell in re.findall(r"<td>(.*?)</td>", _strip_nested(html, "details"), re.S):
        # the citation spans only: `class="evlist"` is their container, which a
        # prefix match would count as one more citation
        n_ev = len(re.findall(r'class="ev(?: gen)?"', cell))
        assert n_ev <= budget.EVIDENCE_LINES_SHOWN, (
            f"{n_ev} citations visible in one cell, contract says "
            f"{budget.EVIDENCE_LINES_SHOWN}"
        )

    # 4. nothing is DELETED — every clipped original is still in the document
    assert "…" in shown, "overlong input produced no clip at all"
    assert (
        html.count("<details>") >= 4
    ), "clipped text with no fold behind it is a deletion, not a budget"
    for original in (LONG, "alternative 3", "decision 19"):
        assert (
            original in html
        ), f"{original!r} is neither shown nor folded — the record lost it"
    print(
        f"  M3 per-decision            {len(shown):5d} visible chars over "
        f"{len(rows) - 1} rows; every part inside its own budget"
    )


def test_sections_hold_on_overlong_input() -> None:
    many = [f"{LONG} entry {i}" for i in range(12)]

    _assert_budgeted(
        "§9 epistemics",
        _s9_epistemics(
            fake_round(
                interp={
                    "cannot_distinguish": many,
                    "nonetheless_determined": many,
                    "finite_but_poorly_determined": many,
                },
                report={
                    "computed_cannot_distinguish": ["k_on"],
                    "computed_nonetheless_determined": ["k_off"],
                    "computed_finite_but_poorly_determined": ["k_mid"],
                },
            )
        ),
        ONE_SCREEN,
    )

    _assert_budgeted(
        "§10 narrative",
        _s10_narrative(
            fake_round(
                interp={
                    "diagnosis": LONG,
                    "misfit_hypotheses": many,
                    "answers_intent": [
                        {"verdict": "pass", "criterion": LONG, "evidence": LONG}
                        for _ in range(6)
                    ],
                    "recommendation": "revise",
                }
            )
        ),
        ONE_SCREEN,
    )

    _assert_budgeted(
        "§8 misfit indicators",
        _misfit_evidence(
            fake_round(core={"misfit_evidence": {"open": True, "reasons": many}})
        ),
        ONE_SCREEN,
    )

    gates = [
        {
            "gate_id": f"g{i}",
            "tier": "T1",
            "module": "s7",
            "passed": i % 7 != 0,
            "detail": LONG,
        }
        for i in range(40)
    ]
    _assert_budgeted(
        "§12 gate record", _s12_gates(fake_round(_gate_rows=gates)), ONE_SCREEN
    )

    # a clean round hides the whole table behind the count, and hides nothing else
    clean = _s12_gates(
        fake_round(_gate_rows=[dict(g, passed=True, detail="ok") for g in gates])
    )
    assert "<details>" in clean and len(visible(clean)) < 200
    for g in gates:
        assert g["gate_id"] in clean, "a folded row must still be in the document"
    print("  §12 with no failures: record folded, every row still present")


# ---- 4. the one screen a reader is handed is the right screen -------------
#
# SHAPE assertions, not length ones: a budget that holds while the answer sits
# below four tables of provenance is a budget on the wrong thing.

# The three groups §8 must have, in order: what was chosen and why, how far to
# trust it, what is still wrong.
S8_GROUPS = ("What won, and why", "How far to trust it", "What is still wrong")

# Every §8 subsection heading the renderer can emit; each must sit under one of
# the groups above, so a new subsection with no group fails here.
S8_SUBSECTIONS = (
    "Model comparison",
    "Why the winner wins",
    "What each mechanism term buys",
    "Fit metrics",
    "Held-out prediction",
    "Profile likelihood",
    "Information spectrum",
    "Noise-model check",
    "Structural misfit indicators",
    "Checks that ran",
)


def _headings(html: str) -> list[tuple[int, str]]:
    """[(level, text)] for every h2/h3/h4, folded ones included (still structure)."""
    out = []
    for m in re.finditer(r"<h([234])\b[^>]*>(.*?)</h\1>", html, re.S | re.I):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        out.append((int(m.group(1)), text))
    return out


def test_s8_has_three_groups_and_nothing_outside_them() -> None:
    """§8's subsections sit three groups deep, on a round with every §8 feature."""
    r = fake_round(
        is_md=True,
        summary={"best_x_unscaled": {"k1": 0.2, "k2": 1.4}},
        discrimination={
            "winner": "a+b",
            "candidates": [
                {
                    "id": cid,
                    "n_est": 7,
                    "n_data": 42,
                    "nllh": 12.0 + i,
                    "aic": 38.0 + 2 * i,
                    "bic": 44.0 + 2 * i,
                    "delta_aic": 2.0 * i,
                    "akaike_weight": 0.7 if i == 0 else 0.1,
                }
                for i, cid in enumerate(["a+b", "a", "b", "base"])
            ],
        },
        core={
            "fit": [
                {
                    "observable": "obs_A",
                    "condition": "u=1",
                    "n": 21,
                    "rmse": 0.04,
                    "nrmse": 0.03,
                    "residual_lag1_autocorr": 0.1,
                }
            ],
            "holdout": {
                "available": True,
                "groups": [
                    {
                        "label": "u=2",
                        "n": 12,
                        "rmse": 0.05,
                        "nrmse": 0.09,
                        "coverage": 0.92,
                        "rel_width": 0.2,
                    }
                ],
            },
            "profiles": {
                "k1": {
                    "ci_low": 0.1,
                    "ci_high": 0.4,
                    "identifiable": True,
                    "path": {},
                }
            },
            "identifiability": {
                "available": True,
                "method": "residual sensitivities (AMICI) at the MLE, FIM = J^T J",
                "space": "scaled parameter space (as optimised)",
                "n_free": 7,
                "x_names": ["k1", "k2"],
                "eigenvalues_log10": [2.0, -2.02],
                "spread_decades": 4.02,
                "flat_decades_threshold": 8.0,
                "flat_directions": [],
                "eigenvector_composition_smallest": {"k1": 0.7, "k2": -0.7},
                "note": "a spectrum, not a rank",
            },
            "noise_check": {
                "obs_A": {
                    "n": 21,
                    "shapiro_p": 0.4,
                    "rejected": False,
                    "assumed": "normal, proportional",
                }
            },
            "misfit_evidence": {"open": True, "reasons": ["positive at high dose"]},
            "attribution": {
                "available": True,
                "rivals": [
                    {
                        "available": True,
                        "rival": "a",
                        "delta_aic": -4.2,
                        "likelihood_units": -6.2,
                        "parameter_units": 2.0,
                        "contributions": [
                            {
                                "group": "obs_A @ u=1",
                                "delta_aic_units": -4.0,
                                "share": 0.95,
                                "n": 21,
                            }
                        ],
                    }
                ],
                "neutralisation": {
                    "parameters": {
                        "k_fb": {
                            "axis": "a",
                            "neutral_value": 0.0,
                            "delta_nllh": 52.4,
                            "series_moved": 2,
                        }
                    }
                },
            },
            # "Checks that ran" is one line per screen that found NOTHING, so
            # its inputs are the screens' own records, not a list of names
            "latent_states": {
                "available": True,
                "conditions": 1,
                "negative": [],
                "unbounded": [],
                "conserved": [],
            },
            "declared_constants": {"declared": 0, "violated": 0, "rows": []},
        },
        report={},
        interp={"diagnosis": "the winner fits"},
    )
    html = _s8_evaluation(r)
    heads = _headings(html)

    groups = [text for level, text in heads if level == 3]
    assert groups == list(S8_GROUPS), (
        f"§8's groups are {groups}; the declared order is {list(S8_GROUPS)} — "
        f"either a group was added, dropped, renamed, or a subsection is "
        f"still rendering at h3 beside the groups instead of h4 under one"
    )

    # every subsection that rendered sits under a group, and the first thing
    # in the section is a group rather than content
    assert heads and heads[0][0] == 3, (
        f"§8 opens with {heads[:1]} — content before the first group header "
        f"belongs to no group and the reader cannot tell which"
    )
    seen_by_group: dict[str, list[str]] = {g: [] for g in S8_GROUPS}
    current = None
    for level, text in heads:
        if level == 3:
            current = text
        else:
            assert current, f"subsection {text!r} renders outside every group"
            seen_by_group[current].append(text)

    # and the ones this fixture supplies all appear, each exactly once
    flat = [h for hs in seen_by_group.values() for h in hs]
    for want in S8_SUBSECTIONS:
        hits = [h for h in flat if h.startswith(want)]
        assert len(hits) == 1, (
            f"§8 subsection {want!r} rendered {len(hits)} time(s) on a round "
            f"that supplies its input; the headings present are {flat}"
        )

    # the group prose must say what the group is for, not only name it
    for q in re.findall(r'class="grpq"[^>]*>(.*?)</p>', html, re.S):
        assert len(visible(q)) >= 40, f"a group states no question: {q!r}"

    print(
        "  §8 hierarchy   3 groups in the declared order, "
        + "; ".join(f"{g}: {len(v)}" for g, v in seen_by_group.items())
        + " subsection(s), none outside a group"
    )


def _fake_analysis(tmp: Path, *, long_text: str) -> dict:
    """A hand-written run summary (`analysis_report.build`'s keys), fields overlong."""
    root = record_at(tmp / "run")  # the fixture is a record, not a directory
    r0 = rnd(root, 0)
    (r0 / "space/axes").put(
        [
            {
                "id": f"axis_{i}",
                "question": f"{long_text} (axis {i})",
                "priority": i,
            }
            for i in range(6)
        ]
    )
    # the evidence links are rendered only for documents that EXIST (the
    # rendered reports are real files beside the record; decisions_md is in it)
    report = reports_dir(root) / "round_0" / "report"
    report.mkdir(parents=True, exist_ok=True)
    for name in ("report.html", "model_report.html"):
        (report / name).write_text("<h1>evidence</h1>")
    (r0 / "decisions_md").put_text("# decisions\n")
    models = [
        {
            "round": 0,
            "model": f"axis_0+axis_{i}",
            "n_estimated": 6 + i,
            "nllh": 12.0 + i,
            "delta_aic": 0.0 if i == 1 else 2.0 * i,
            "weight": 0.7 if i == 1 else 0.05,
            "selected": i == 1,
            "lineage": long_text,
        }
        for i in range(1, 9)
    ]
    return {
        "run": "budget_shape",
        "record": str(root.store.path),
        # the question and the system are the USER's words (intent.yaml), which
        # the engine must not clip, so they are realistic; every ENGINE-generated
        # field below is deliberately overlong
        "question": "Does the product feed back on its own production?",
        "inference_target": "mechanism_discrimination",
        "system": "A three-species reporter assay under four input levels.",
        "success_criteria": [f"{long_text} #{i}" for i in range(6)],
        "n_rounds": 3,
        "rounds": [
            {
                "round": i,
                "what_changed": long_text,
                "selected": "axis_0+axis_1",
                "selected_structure": "axis_0+axis_1",
            }
            for i in range(3)
        ],
        "models_assessed": models,
        "answer": {
            "selected_model": "axis_0+axis_1",
            "selected_structure": "axis_0+axis_1",
            "decisive": True,
            "indistinguishable_set": ["axis_0+axis_1"],
            "basis": long_text,
        },
        "answers_intent": [
            {"criterion": long_text, "verdict": long_text} for _ in range(6)
        ],
        "still_open": [f"{long_text} open {i}" for i in range(6)],
        "gate_policy": {
            "profile": "strict",
            "sha": "0" * 12,
            "source": "workflows/policies/strict.yaml",
            "answers": [],
            "verdict_signed_by": "human",
        },
        "cost": {
            "agent_calls": 14,
            "usd": 0.0,
            "human_decisions": 3,
            "policy_decisions": 0,
            "auto_decisions": 0,
            "contract_retries": 0,
            "module_redrafts": 0,
            "redraft_grants": 0,
            "attempts_per_call": 1.0,
        },
        "declared_constants": {"declared": 1, "violated": 0, "rows": []},
        "provenance": {
            "workflow_sha": "a" * 12,
            "note": long_text,
            "cross_round_comparability": {
                "across_rounds": True,
                "regime": "same data",
                "why": long_text,
            },
            "search_topology": {
                "n_axes_declared": 6,
                "union_lattice_models": 64,
                "visited": 8,
                "visited_fraction": 0.125,
                "models_outside_the_lattice": [],
                "topology": "exhaustive within a round, greedy across rounds",
                "note": long_text,
            },
        },
        "outcome": "accepted",
    }


def test_the_run_page_leads_with_the_verdict() -> None:
    """The run page's first section is the verdict, inside the first screen."""
    import tempfile

    from octomod.reporting.analysis_report import VERDICT_HEADING, render_html

    long_text = LONG
    with tempfile.TemporaryDirectory() as td:
        summary = _fake_analysis(Path(td), long_text=long_text)
        html = render_html(summary)

    h2s = [text for level, text in _headings(html) if level == 2]
    assert h2s, "the run page has no sections at all"
    assert h2s[0] == VERDICT_HEADING, (
        f"the run page's first section is {h2s[0]!r}; the page contract puts "
        f"{VERDICT_HEADING!r} first, before the picture, the loop and the "
        f"evidence. Full order: {h2s}"
    )

    # the verdict is REACHED, not merely present: everything visible above it
    # has to fit on a screen alongside it
    cut = html.index(f">{VERDICT_HEADING}<")
    above = visible(html[:cut])
    assert len(above) <= ONE_SCREEN, (
        f"{len(above)} visible chars sit above the verdict on the run page "
        f"(budget {ONE_SCREEN}) — the answer is below the fold again:\n"
        f"  {above[:240]}"
    )

    # and the record is still there, below the argument
    for later in (
        "How the analysis got there",
        "The evidence behind this page",
        "Gate policy",
        "What it cost",
    ):
        assert later in h2s, f"the run page dropped {later!r}: {h2s}"
        assert h2s.index(later) > h2s.index(VERDICT_HEADING), (
            f"{later!r} is above the verdict — moving the argument forward "
            f"means moving the provenance down, not deleting it"
        )
    assert "Still open" in h2s and h2s.index("Still open") < h2s.index(
        "How the analysis got there"
    ), f"'Still open' must follow the verdict and precede the loop: {h2s}"

    print(
        f"  run page       {h2s[0]!r} first, {len(above)} visible chars above "
        f"it (budget {ONE_SCREEN}), {len(h2s)} sections, provenance below"
    )


def test_the_evidence_tier_column_speaks_to_a_reader() -> None:
    """The evidence-tier column shows a reader's words; the JSON keeps the machine's."""
    from octomod.reporting.model_report import (
        TIER_COLUMN_NOTE,
        TIER_WORDS,
        tier_words,
    )

    assert TIER_WORDS == {
        "direct": "measured here",
        "transferred": "carried from elsewhere",
        "default": "no source given",
        "to_be_estimated": "fitted",
    }, TIER_WORDS
    # an unknown tier is shown verbatim, never blanked: a value this map has
    # not learned must be visible
    assert tier_words("a_new_tier_someone_added") == "a_new_tier_someone_added"
    assert tier_words(None) == "—"

    decisions = [
        {
            "decision": f"assumption {i}",
            "confidence": "low",
            "rationale": "because",
            "evidence": [],
            "evidence_tier": tier,
        }
        for i, tier in enumerate(TIER_WORDS)
    ]
    html = _m3_assumptions({"decisions": decisions})
    shown = visible(html)

    # the reader's words are on the page
    for machine, reader in TIER_WORDS.items():
        assert reader in shown, f"{machine!r} still shows as itself"
    # the engine's words are NOT the visible label
    assert "to_be_estimated" not in shown, shown[:200]
    assert (
        "evidence tier" not in shown.lower()
    ), "the column heading is still the engine's phrase"
    assert "where the number came from" in shown.lower()

    # the sentence saying what the column is FOR
    assert TIER_COLUMN_NOTE[:40] in shown, "the column is unexplained"
    assert "hardest" in shown, (
        "the note must say which value to look at hardest, or four labels are "
        "still four labels"
    )

    # the machine value survives in the markup for anyone reading the JSON too
    assert 'title="evidence_tier: transferred"' in html
    print(
        f"  evidence tier  {len(TIER_WORDS)} values in the reader's words, "
        f"machine values kept in the markup"
    )


def test_gate_card_cap(capsys=None) -> None:
    """The card caps EVIDENCE, never the menu the human chooses from (`always_show`)."""
    src = Path(
        REPO / "octomod" / "orchestration" / "interaction" / "humangate.py"
    ).read_text()
    assert '"lines": lines,' in src, (
        "the pending_gate payload must carry every line — the cap is on the printed "
        "card only"
    )

    import io
    from contextlib import redirect_stdout

    evidence = [f"evidence line {i}" for i in range(40)]
    menu = ["OPEN STRUCTURAL AXES", "  · axis basal_route (tier top1)"]
    buf = io.StringIO()

    class _Ledger:
        def append(self, *a, **k):
            pass

    with redirect_stdout(buf):
        humangate.ask(
            "pick a scope",
            evidence,
            ledger=_Ledger(),
            module="test_scope",
            auto=True,
            always_show=menu,
        )
    out = buf.getvalue()
    shown = [line for line in evidence if line in out]
    assert len(shown) == humangate.CARD_EVIDENCE_LINES, (
        f"card showed {len(shown)} evidence lines, expected "
        f"{humangate.CARD_EVIDENCE_LINES}"
    )
    assert "more evidence lines" in out, "a capped card must say what it withheld"
    for line in menu:
        assert line in out, f"the choice menu was capped away: {line!r}"
    # lines named `uncapped` print in their place past the cap, and do not
    # count against it
    grounding = ["ESSENTIAL SET: 3 reactions", "SUPPORT FLOOR: medium"]
    buf = io.StringIO()
    with redirect_stdout(buf):
        humangate.ask(
            "pick a scope",
            evidence + grounding,
            ledger=_Ledger(),
            module="test_scope",
            auto=True,
            uncapped=grounding,
        )
    out2 = buf.getvalue()
    assert all(line in out2 for line in grounding), "an uncapped line was capped"
    assert (
        sum(1 for line in evidence if line in out2) == humangate.CARD_EVIDENCE_LINES
    ), "uncapped lines counted against the cap"
    assert f"… {len(evidence) - humangate.CARD_EVIDENCE_LINES} more" in out2
    print(
        f"  gate card: {len(shown)} of {len(evidence)} evidence lines shown, "
        f"menu intact, uncapped lines past the cap, payload complete"
    )


def test_the_third_epistemic_list() -> None:
    """Closed but wide: in neither gated list, in the third, and shown."""
    from types import SimpleNamespace

    from octomod.workflow_modules.evaluation import engine as s7

    class Spec:
        def get(self, key, default=None):
            return default

    def prof(finite, frac):
        return {
            "ci_finite": finite,
            "ci_box_fraction": frac,
            "ci95": [0.5, 2.0],
            "ci_width_decades": 0.6,
        }

    core = {
        "profiles": {
            "p_wide": prof(True, 0.45),
            "p_tight": prof(True, 0.05),
            "p_open": prof(False, 0.7),
            "_meta": {},
        },
        "parameters": {"ensemble_log10_spread": {}},
        "holdout": {"available": False},
    }
    cd = s7._computed_cannot_distinguish(core, Spec())
    nd = s7._computed_determined(core, Spec())
    pdl = s7._computed_poorly_determined(core, Spec())
    assert (cd, nd, pdl) == (["p_open"], ["p_tight"], ["p_wide"]), (cd, nd, pdl)
    core["computed_finite_but_poorly_determined"] = pdl
    interp = s7._with_poorly_determined(
        core,
        {
            "cannot_distinguish": cd,
            "nonetheless_determined": nd,
            # a re-spelled echo of a computed entry, and one of the agent's own
            "finite_but_poorly_determined": ["p_wide ", "k_extra"],
            "diagnosis": "d",
            "answers_intent": [],
            "recommendation": "accept",
        },
    )
    assert interp["finite_but_poorly_determined"] == ["p_wide", "k_extra"], interp
    none = s7._with_poorly_determined(core, {"cannot_distinguish": []})
    assert none["finite_but_poorly_determined"] == ["p_wide"], none

    lines = s7._epistemic_card_lines(interp, Spec())
    head = [x for x in lines if x.startswith("finite but poorly determined (2)")]
    assert head and "over more than 10% of its box" in head[0], lines
    assert "  · p_wide" in lines and lines.index(head[0]) > lines.index(
        "  · p_tight"
    ), lines
    assert not any(
        x.startswith("finite but")
        for x in s7._epistemic_card_lines({"cannot_distinguish": ["a"]}, Spec())
    ), "an empty third list must not reach the card"

    html = _s9_epistemics(
        fake_round(
            interp=interp,
            report={
                "computed_cannot_distinguish": cd,
                "computed_nonetheless_determined": nd,
                "computed_finite_but_poorly_determined": pdl,
            },
        )
    )
    assert "Finite but poorly determined" in html, "the report box has no third list"
    assert "p_wide" in visible(html) and "not well determined" in visible(html)
    bare = _s9_epistemics(fake_round(interp={"cannot_distinguish": ["a"]}, report={}))
    assert "Finite but poorly determined" not in bare, "no profiles, no third list"

    ctx = SimpleNamespace(intent={"question": "q"}, round_idx=0)
    md = s7._render_md(
        ctx,
        {
            "goal": "prediction",
            "best_fval": 1.0,
            "chi2_per_dof": 1.0,
            "fit": [],
            "holdout": {"available": False, "note": "none"},
            "parameters": {"best": {}, "ensemble_log10_spread": {}, "at_bounds": []},
            "profiles": core["profiles"],
            "interpretation": interp,
        },
    )
    tail = md.split("## Finite but poorly determined", 1)
    assert len(tail) == 2 and tail[1].lstrip().startswith("p_wide, k_extra"), md
    print(
        "  third list     closed at 45% of its box: neither gated list; on the "
        "card, in report.md and in the epistemics box"
    )


def test_a_discrimination_round_lists_no_profile_in_any_of_the_three() -> None:
    """The three epistemic lists follow one rule per path. On a discrimination
    round they are about the mechanism (the indistinguishable set or the
    decisive winner, and the winner's flat FIM combinations), so a profiled
    winner's open, wide and tight profiles are in none of them — never a wide
    one listed while the open one, the stronger finding, is shown nowhere."""
    from octomod.workflow_modules.evaluation import engine as s7

    def prof(finite, frac):
        return {"ci_finite": finite, "ci_box_fraction": frac, "ci95": [0.5, 2.0]}

    flat = {
        "available": True,
        "flat_directions": [
            {
                "composition": {"k1": 0.7, "sc": -0.7},
                "reads_as": "0.70*log(k1) -0.70*log(sc)",
            }
        ],
    }
    profiles = {
        "p_wide": prof(True, 0.45),
        "p_tight": prof(True, 0.05),
        "p_open": prof(False, 0.7),
        "_meta": {},
    }
    for decisive, indist in ((True, ["M1"]), (False, ["M1", "M2"])):
        core = {
            "goal": "mechanism_discrimination",
            "discrimination": {
                "winner": "M1",
                "indistinguishable": indist,
                "decisive": decisive,
            },
            "profiles": profiles,
            "identifiability": flat,
            "holdout": {"available": False},
        }
        lists = s7._md_computed_references(core)
        assert set(lists) == {
            "computed_cannot_distinguish",
            "computed_nonetheless_determined",
            "computed_finite_but_poorly_determined",
        }, lists
        named = [e for v in lists.values() for e in v]
        assert not any(
            p in e for e in named for p in profiles
        ), f"a profile-derived entry in a discrimination round's lists: {lists}"
        mech = ["mechanism:M1"] if decisive else ["mechanism:M1", "mechanism:M2"]
        combo = "flat combination (FIM): 0.70*log(k1) -0.70*log(sc)"
        assert lists["computed_cannot_distinguish"] == ([] if decisive else mech) + [
            combo
        ], lists
        assert lists["computed_nonetheless_determined"] == (
            mech if decisive else []
        ), lists
        assert lists["computed_finite_but_poorly_determined"] == [], lists

    # the report box does not draw an empty third column as "looked at" there
    md_round = fake_round(
        is_md=True,
        goal="mechanism_discrimination",
        interp={"cannot_distinguish": [], "nonetheless_determined": ["mechanism:M1"]},
        core={"profiles": profiles},
    )
    assert "Finite but poorly determined" not in _s9_epistemics(md_round), (
        "the discrimination round's box shows an empty third list beside a "
        "profiled winner, which reads as 'no closed-but-wide profile'"
    )
    single = fake_round(interp={"cannot_distinguish": []}, core={"profiles": profiles})
    assert "Finite but poorly determined" in _s9_epistemics(single)
    print(
        "  md lists       a profiled winner's open, wide and tight profiles are "
        "in none of the three lists of a discrimination round"
    )


def test_the_run_page_shows_each_verdicts_evidence() -> None:
    """The sentence that decided a verdict reaches ANALYSIS.md and ANALYSIS.html."""
    import tempfile

    from octomod.reporting.analysis_report import render_html, render_md

    marker = "EVIDENCE-MARKER-7f3a"
    with tempfile.TemporaryDirectory() as td:
        summary = _fake_analysis(Path(td), long_text=LONG)
        summary["answers_intent"] = [
            {
                "criterion": "held-out nRMSE below 0.2",
                "verdict": "pass",
                "evidence": f"nRMSE 0.06 over 12 held-out points {marker}.",
            },
            {
                "criterion": "the band covers 80% of held-out points",
                "verdict": "partial",
                "evidence": f"{LONG} {marker}-long",
            },
            {
                "criterion": "a verdict an agent wrote without evidence",
                "verdict": "fail",
            },
        ]
        md = render_md(summary)
        html = render_html(summary)
    section = md.split("### Against the questions asked at the start", 1)[-1]
    assert f"nRMSE 0.06 over 12 held-out points {marker}." in section, section[:600]
    assert f"{marker}-long" in section, "the markdown must carry the evidence in full"
    shown = visible(html)
    assert marker in shown, "the html shows no evidence beneath the verdict"
    assert (
        f"{marker}-long" not in shown and f"{marker}-long" in html
    ), "a long evidence sentence is clipped in view and kept in a fold"
    assert "a verdict an agent wrote without evidence" in shown
    print(
        "  run page       every intent verdict carries its evidence, in the "
        "markdown in full and in the html clipped with a fold"
    )


if __name__ == "__main__":
    test_the_run_page_shows_each_verdicts_evidence()
    test_the_third_epistemic_list()
    test_a_discrimination_round_lists_no_profile_in_any_of_the_three()
    test_constants_match_reporting_md()
    test_clipping()
    test_m3_holds_every_per_decision_budget()
    test_sections_hold_on_overlong_input()
    test_s8_has_three_groups_and_nothing_outside_them()
    test_the_run_page_leads_with_the_verdict()
    test_the_evidence_tier_column_speaks_to_a_reader()
    test_gate_card_cap()
    print(
        "REPORT BUDGET UNIT OK — contract and code agree; every budgeted "
        "surface holds on overlong input"
    )
