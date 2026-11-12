"""Fast regressions, each on one predicate, string or ordering; no pipeline run.

  1. an expanded round's exit code 0 counts as an expansion that took over;
  2. report.html at the verdict pause is asserted in expansion_smoke instead;
  3. the verdict card promises an expansion only when a round remains;
  4. the scope card's closing sentence follows what was already bought;
  5. round-local ids resolve to the structure they name, in the rendered verdict;
  6. the evidence tier reads the source/locator pair, not the source alone;
  7. the candidate card shows the declared axes and tier; candidates are the menu;
  8. the model report states shared assumptions once and drops no candidate;
  9. candidates are compared in one drawing, with the laws side by side;
 10. the residual-shape screen corroborates only, and is reported in also_seen.

    uv run python tests/live_blind_3_unit.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402
from tests._record import record_at, rnd  # noqa: E402

# the USER's runs folder, not redirected by the battery: this reads a
# previous run of theirs, not one this suite makes
USER_RUNS = config.USER_RUNS_DIR


def test_run_end_written_once() -> None:
    """A successful expanded round returns 0, and 0 is not "no expansion"."""
    from octomod.orchestration.orchestrator import expansion_took_over

    assert expansion_took_over(0) is True, (
        "0 is the SUCCESS exit code of an expanded round; reading it as "
        "'no expansion' is what wrote three run_end rows"
    )
    for code in (1, 3, 2):
        assert expansion_took_over(code) is True
    assert (
        expansion_took_over(None) is False
    ), "None is the only value that means the round did not expand"
    # that the CALL SITE uses this predicate is asserted in `expansion_smoke`:
    # a two-round expanded run leaves exactly one `run_end` row
    print("  run_end       0 counts as an expansion that took over")


def test_report_html_exists_before_the_verdict_ask() -> None:
    """Asserted in `expansion_smoke`: report.html is on disk at each verdict pause."""
    print("  report.html   asserted at the verdict PAUSE in expansion_smoke")


def test_card_never_promises_a_skipped_expansion() -> None:
    """The card's "expansion agent is asked next" must match the guard."""
    from octomod.orchestration.orchestrator import rounds_left_after

    assert rounds_left_after(0, 3) == 2
    assert rounds_left_after(2, 3) == 0, "the last round has none left"
    assert rounds_left_after(0, 1) == 0, "a single-round run expands never"

    # the card's own words, from the function that produces them — no fixture
    # ends its LAST round with the misfit still open, so only this reaches it
    from octomod.workflow_modules.evaluation.engine import md_verdict_consequences

    promise = "the expansion agent is asked"
    yes, no = md_verdict_consequences(misfit_open=True, rounds_left=2)
    assert promise in yes and "2 round(s) left" in yes, yes

    yes, _ = md_verdict_consequences(misfit_open=True, rounds_left=0)
    assert (
        promise not in yes
    ), f"the last round promises a step the orchestrator will skip: {yes}"
    assert "stays OPEN" in yes and "unexplained" in yes, (
        f"with no rounds left the card must say the misfit stays open and "
        f"unexplained rather than implying it will be pursued: {yes}"
    )
    assert "no rounds are left" in yes, yes

    for rounds in (0, 3, None):
        yes, _ = md_verdict_consequences(misfit_open=False, rounds_left=rounds)
        assert promise not in yes and "THE RUN ENDS" in yes, (rounds, yes)

    assert no == "run stops here without an accepted verdict"
    # rounds_left=None with the misfit open is the conservative reading: no
    # count means no promise.
    yes, _ = md_verdict_consequences(misfit_open=True, rounds_left=None)
    assert promise not in yes, yes
    print("  verdict card  expansion promised only when a round remains")


def test_scope_card_sentence_matches_what_was_bought() -> None:
    """An expansion-seeded scope card must not repeat the round-0 sentence."""
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    tree = ast.parse(src)
    # the sentence must live inside a conditional on `bought`, not be appended
    # unconditionally
    stays = "the round stays single-model "
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        text = ast.unparse(node)
        if stays in text:
            assert "bought" in text, (
                "the sentence is conditional on something other than whether "
                "the axes were already bought: " + text[:160]
            )
            assert (
                "already bought" in text
            ), "the bought branch must say the axes are already bought"
            assert (
                "un-buy" in text
            ), "and must warn that naming none would un-buy the round"
            found = True
    assert found, (
        "the round-0 sentence is still appended unconditionally; an "
        "expansion-seeded card will contradict itself"
    )
    print("  scope card    closing sentence follows what was already bought")


def test_lineage_resolves_round_local_ids() -> None:
    """`base` is meaningless at run level; name the structure it stands for."""
    import shutil
    import tempfile

    from octomod.reporting.analysis_report import lineage

    # round 0's winner is expanded by two axes, round 1's combination winner by
    # one more: round 2's `base` is that round-1 winner
    tmp_dir = Path(tempfile.mkdtemp(prefix="lb3_lineage_"))
    tmp = record_at(tmp_dir / "run")  # the run is one record file
    try:
        for idx, exp in (
            (
                0,
                {
                    "expanded": True,
                    "from_winner": "M2_parallel_kina_route",
                    "axes": [
                        "prod_inhibits_regb_activation",
                        "saturable_prod_turnover",
                    ],
                },
            ),
            (
                1,
                {
                    "expanded": True,
                    "from_winner": "prod_inhibits_regb_activation+saturable_prod_turnover",
                    "axes": ["regb_p_deactivates_kina"],
                },
            ),
        ):
            (rnd(tmp, idx) / "expansion").put(exp)
        (rnd(tmp, 2) / "model/seed").put({"from_round": 1})

        full = (
            "M2_parallel_kina_route + prod_inhibits_regb_activation "
            "+ saturable_prod_turnover"
        )
        assert lineage(tmp, 2, "base") == full, lineage(tmp, 2, "base")
        assert lineage(tmp, 0, "M2_parallel_kina_route") == "M2_parallel_kina_route"
        assert lineage(tmp, 2, "regb_p_deactivates_kina") == (
            full + " + regb_p_deactivates_kina"
        )
        # a combo id is split so every axis is named once, in order
        assert (
            lineage(tmp, 1, "prod_inhibits_regb_activation+saturable_prod_turnover")
            == full
        )

        # a round that did not expand stops the walk rather than inventing depth
        (rnd(tmp, 1) / "expansion").put({"expanded": False})
        assert lineage(tmp, 2, "base") == "base", (
            "with no expansion recorded there is no lineage to report, and the "
            "id must come back unchanged rather than borrowing an older round's"
        )
    finally:
        shutil.rmtree(tmp_dir)

    # and the run-level documents must use it, not the raw id
    src = (REPO / "octomod" / "reporting" / "analysis_report.py").read_text()
    assert '"selected_structure": lineage(' in src
    # asserted on the RENDERED documents, html and markdown, which are written
    # separately: the verdict names the structure, not a round-local id

    from octomod.reporting.analysis_report import (
        VERDICT_HEADING,
        build,
        render_html,
        render_md,
    )

    # a FINISHED run, not merely the newest: the `analysis` group is the last
    # thing a run writes, and the newest run may be one another suite is still
    # writing, which `build()` would read half-written. A run is one record
    # file, runs/<id>.h5
    runs = [
        s
        for s in RunStore.all_in(USER_RUNS)
        if s.exists("rounds/round_0/evaluation") and s.exists("analysis")
    ]
    if not runs:
        # an absent fixture is not a defect: one SKIP line, exit 77
        print(
            "SKIP: no FINISHED run in runs/ (an `analysis` in its record) to check "
            "the run-level documents against — a machine-local live run, and runs/ "
            "is gitignored, so it exists only where it was made"
        )
        raise SystemExit(77)
    run = Node(max(runs, key=lambda s: s.mtime_ns() or 0))
    run_name = run.store.path.name
    summary = build(run)
    structure = (
        summary["answer"].get("selected_structure")
        or summary["answer"]["selected_model"]
    )
    html, md = render_html(summary), render_md(summary)
    verdict = html.index(VERDICT_HEADING)

    # the VERDICT SECTION, not a byte window after the heading: a window reaches
    # into later sections whose tables name the model legitimately
    nxt = html.find("<h2>", verdict)
    head = html[verdict : nxt if nxt > verdict else len(html)]

    from octomod.reporting.analysis_report import axes_carried, axes_of

    # four cases, mirroring `_what_won`'s own condition (`if carried or known:
    # ... elif single: ... else: ...`); a winner with no structure NAME to print
    # is asserted on the words the verdict uses instead
    known = axes_of(run)
    carried = axes_carried(structure, known)
    single = summary["answer"].get("basis") == "single-model calibration"
    if carried:
        # a lattice winner: the structure has a real name, printed in words
        # ("M4 plus a, b"), so every PART must be named
        parts = [p.strip() for p in str(structure).split("+") if p.strip()]
        assert all(part in head for part in parts), (
            f"the html verdict section does not name the structure "
            f"{structure!r} ({run_name})"
        )
    elif known:
        # axes were declared and the winner carries none: the verdict answers
        # each declared question with a No
        assert "the base model plus nothing" in head, (
            f"axes were declared and the winner carries none, so the verdict "
            f"must say the base won rather than print {structure!r} "
            f"({run_name}); it reads: {head[:300]}"
        )
    elif single:
        # nothing declared or compared: `selected_model` is the placeholder
        # "round k model", which must not be printed as a name
        assert "One model was calibrated" in head, (
            f"nothing was compared on this run, so the verdict must say so in "
            f"words rather than print the placeholder {structure!r} "
            f"({run_name}); the verdict section reads: {head[:300]}"
        )
        assert f"<code>{structure}</code>" not in head, (
            f"the verdict prints the placeholder {structure!r} as though it "
            f"were an identifier ({run_name})"
        )
    else:
        # a discrimination winner handed over with its own id and no lattice
        assert structure in head, (
            f"the html verdict section does not name the winner {structure!r} "
            f"({run_name})"
        )
    md_head = md[: md.index("\n## ", md.index("##")) + 1200]
    assert (structure in md_head) or (
        not carried and ("base model plus nothing" in md_head or single)
    ), f"the markdown verdict does not name the structure {structure!r}"
    tables = src.count("m.get('lineage') or m['model']") + src.count(
        'm.get("lineage") or m["model"]'
    )
    assert (
        tables == 2
    ), f"both model tables must name the structure; found {tables} of 2"
    print("  lineage       round-local ids resolved to the structure they name")


def test_evidence_tier_survives_a_generic_source_with_a_real_locator() -> None:
    """The demotion rule reads the source/locator PAIR, not `source` alone."""
    from octomod.workflow_modules.model.engine import (
        evidence_points_somewhere as points,
    )

    # a category source whose locator points at the lab note
    assert points(
        {
            "source": "general knowledge",
            "locator": "experiment description, 'The parts, as designed'",
        }
    ), "a category source with a real locator IS a pointer"

    # and the placeholders the agent writes when it has nothing must not count,
    # or the rule could never demote anything
    for empty in ("n/a", "", "none", "-", "TBD", "unknown"):
        assert not points({"source": "general knowledge", "locator": empty}), empty

    # a named category needs no locator; a claim on the note or a paper does
    assert points({"source": "database", "locator": ""})
    assert points({"source": "literature", "locator": "10.1234/x, figure 2"})
    assert not points(
        {"source": "literature", "locator": ""}
    ), "citing the literature without saying where is a claim, not evidence"
    assert not points({"source": "lab_note", "locator": "n/a"})
    assert points({"source": "lab_note", "locator": "the pool does not change"})

    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert (
        "evidence_points_somewhere(e) for e in ev" in src
    ), "the demotion site must ask the named rule"
    assert (
        '"general knowledge", "n/a"' not in src
    ), "a source-only blacklist is in the demotion path"
    contract = (REPO / "octomod" / "agents" / "__init__.py").read_text()
    assert "lab_note|literature|database|general_knowledge" in contract, (
        "the contract must offer source as an enum, so the agent stops "
        "putting a category where a pointer belongs"
    )
    assert "REQUIRED for lab_note and literature" in contract
    print("  evidence      tier reads the source/locator pair")


def test_md_candidate_card_shows_the_declared_axes_and_tier() -> None:
    """The candidate card shows the declared axes and tier, for information only."""
    from octomod.workflow_modules.model.engine import _declared_space_lines as space

    assert space(None) == [] and space({}) == []
    assert space({"model_space": []}) == [], "no axes, no section"

    reply = {
        "model_space": [
            {
                "id": "prod_loss_returns_to_prec",
                "priority": 3,
                "question": "Does the slow loss of ProD leave the system?",
            },
            {
                "id": "bx11_offtarget_kina",
                "priority": 1,
                "question": "Does BX-11 also inhibit KinA activation?",
            },
        ],
        "recommended_tier": {
            "tier": "base",
            "reasoning": "four candidates is the spend",
        },
    }
    out = space(reply)
    body = "\n".join(out)
    for axis in ("prod_loss_returns_to_prec", "bx11_offtarget_kina"):
        assert axis in body, f"{axis} is still hidden"
    assert "tier base" in body and "the agent recommends" in body
    assert "four candidates is the spend" in body, "the reasoning is the useful part"
    assert (
        "none is fitted this round" in body
    ), "the card must not imply these axes are being bought here"
    # priority order, not reply order
    assert body.index("bx11_offtarget_kina") < body.index("prod_loss_returns_to_prec")

    # and the candidate set travels as the menu, so the evidence cap on the
    # card can never hide the thing the gate is buying
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    assert "always_show=menu," in src
    assert (
        src.count("always_show=menu,") == 2
    ), "both the scope gate and the candidate gate should protect their menu"
    print(
        "  candidate card declared axes and tier are visible; candidates are "
        "the menu"
    )


def test_model_report_renders_shared_assumptions_once() -> None:
    """Shared assumptions render once in M3; a candidate's own still get their block."""
    import shutil
    import tempfile

    from octomod.reporting.model_report import _m3_shared, _per_candidate

    build = {
        "decisions": [
            {
                "decision": "the pool is not conserved",
                "confidence": "medium",
                "rationale": "ProD is lost by J6 with nothing returning to PreC",
                "evidence_tier": "default",
            }
        ]
    }
    tmp_dir = Path(tempfile.mkdtemp(prefix="lb3_m3_"))
    tmp = rnd(record_at(tmp_dir / "run"), 0)  # a round of a record
    try:
        (tmp / "model/build_report").put(build)
        cands = []
        for cid in ("M1_designed", "M2_parallel", "M3_kina", "M4_feedback"):
            (tree.model_node(tmp, cid) / "parameters").put([])
            cands.append(cid)

        class _R:
            rnd = tmp

        out = _m3_shared(_R(), cands)
        assert out.count("the pool is not conserved") == 1, (
            f"the shared assumptions are rendered "
            f"{out.count('the pool is not conserved')} times, not once"
        )
        for cid in ("M1_designed", "M4_feedback"):
            assert cid in out, "the block must name every candidate it covers"
        assert "one construction reply built all 4 candidates" in out

        # a candidate with its OWN assumptions still gets its own block
        own = {
            "decisions": [
                {
                    "decision": "this one is different",
                    "confidence": "low",
                    "evidence_tier": "default",
                }
            ]
        }
        (tree.model_node(tmp, cands[1]) / "build_report").put(own)
        out2 = _m3_shared(_R(), cands)
        assert "this one is different" in out2 and "the pool is not conserved" in out2
        assert out2.count("<h3>") == 2, "two distinct reports, two blocks"

        # and M1/M4 show one candidate open with the rest folded, nothing dropped
        joined = _per_candidate(
            cands,
            {"M1_designed": "the designed cascade"},
            lambda cid: f"<p>body of {cid}</p>",
        )
        assert joined.count("<details>") == 3, "all but the first must fold"
        for cid in ("M1_designed", "M2_parallel", "M3_kina", "M4_feedback"):
            assert f"body of {cid}" in joined, f"{cid} was dropped, not deferred"
        assert "the designed cascade" in joined, "labels survive"
    finally:
        shutil.rmtree(tmp_dir)
    print(
        "  model report  shared assumptions once; candidates deferred, " "never dropped"
    )


SBML_HEAD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" '
    'level="3" version="1"><model id="m">'
    '<listOfCompartments><compartment id="cell" size="1" constant="true"/>'
    "</listOfCompartments>"
)


def _sbml(species: list[str], reactions: list[tuple[str, str, str, str]]) -> str:
    """Minimal SBML: species, and (id, reactant, product, law-in-MathML-ci)."""
    sp = "".join(
        f'<species id="{s}" compartment="cell" initialConcentration="1" '
        f'hasOnlySubstanceUnits="false" boundaryCondition="false" '
        f'constant="false"/>'
        for s in species
    )
    rx = "".join(
        f'<reaction id="{rid}" reversible="false">'
        f'<listOfReactants><speciesReference species="{a}" stoichiometry="1" '
        f'constant="true"/></listOfReactants>'
        f'<listOfProducts><speciesReference species="{b}" stoichiometry="1" '
        f'constant="true"/></listOfProducts>'
        f'<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        f"<apply><times/><ci>{law}</ci><ci>{a}</ci></apply></math></kineticLaw>"
        f"</reaction>"
        for rid, a, b, law in reactions
    )
    return (
        SBML_HEAD
        + f"<listOfSpecies>{sp}</listOfSpecies>"
        + f"<listOfReactions>{rx}</listOfReactions></model></sbml>"
    )


def test_candidates_are_compared_in_one_drawing() -> None:
    """Candidates share one drawing, coloured by what varies, with laws side by side."""
    from octomod.reporting.sbml_view import (
        compare_models,
        comparison_figure,
        comparison_table,
    )

    same_topology = [
        ("cand_a", _sbml(["A", "B"], [("J1", "A", "B", "k_slow")])),
        ("cand_b", _sbml(["A", "B"], [("J1", "A", "B", "k_fast")])),
    ]
    diff = compare_models(same_topology)
    assert diff["differ_by"].startswith("rate laws only"), diff["differ_by"]
    assert diff["varies"] == ["J1"]
    assert diff["reactions"]["J1"]["law_differs"] is True
    assert diff["reactions"]["J1"]["all"] is True, "the reaction is in both"

    # the table is what makes them comparable: one column per candidate
    tbl = comparison_table(same_topology)
    assert "k_slow" in tbl and "k_fast" in tbl, "both laws must be readable"
    assert tbl.count("<th>") == 3, "reaction + one column per candidate"
    assert "&lt;code&gt;" not in tbl, (
        "the table helper escapes headers, so markup in one renders as " "literal text"
    )
    for cid in ("cand_a", "cand_b"):
        assert f"<th>{cid}</th>" in tbl

    # a topology difference is reported as one
    topo = [
        ("cand_a", _sbml(["A", "B"], [("J1", "A", "B", "k1")])),
        (
            "cand_b",
            _sbml(["A", "B", "C"], [("J1", "A", "B", "k1"), ("J2", "B", "C", "k2")]),
        ),
    ]
    d2 = compare_models(topo)
    assert d2["differ_by"] == "topology and laws"
    assert d2["species"]["C"]["in"] == ["cand_b"]
    assert d2["reactions"]["J2"]["all"] is False

    # against the previous round's selection, what this round ADDED is marked
    carried = _sbml(["A", "B"], [("J1", "A", "B", "k1")])
    d3 = compare_models(topo, carried=carried)
    assert d3["reactions"]["J2"]["new"] is True, "J2 is new relative to the base"
    assert d3["reactions"]["J1"]["new"] is False, "J1 was carried"
    assert d3["carried"] is True

    # identical candidates are called out rather than silently drawn
    twins = [("a", carried), ("b", carried)]
    assert "does not discriminate" in comparison_table(twins)

    # the figure never raises, and says what it is showing
    fig = comparison_figure(same_topology)
    assert "drawn once" in fig and "law differs" in fig
    assert 'class="legend"' in fig, "colour needs a key or it means nothing"
    assert comparison_figure([]) and "no candidate models" in comparison_figure([])
    print("  comparison    one drawing, colour keyed, laws side by side")


def test_the_shape_screen_corroborates_and_never_decides() -> None:
    """The residual-shape screen corroborates; alone it lands in `also_seen`."""
    src = (
        REPO / "octomod" / "workflow_modules" / "evaluation" / "engine.py"
    ).read_text()
    assert (
        'out["open"] = bool(hard)' in src
    ), "the misfit flag must open on a HARD signal only"
    assert 'out["reasons"] = hard + (soft if hard else [])' in src, (
        "the screen should join the reasons when something harder fired, and "
        "not otherwise"
    )
    assert 'out["also_seen"] = [] if hard else soft' in src, (
        "fired alone it must still be REPORTED, or the change hides a signal "
        "instead of demoting it"
    )
    # the two hard tests keep their power
    body = src.split("hard: list[str] = []")[1].split('out["open"]')[0]
    assert "hard.append(" in body and body.count("hard.append(") >= 1
    assert (
        "soft.append(" in body and body.count("soft.append(") == 1
    ), "exactly one signal is the loose screen"
    # and it is not a silent replacement of the detail records another site reads
    assert 'out["signals"]["residual_shape_only"]' in src, (
        "signals accumulates per-observable records that section 8 reads; "
        "replacing the dict would destroy them"
    )
    # reported in both places a human looks
    assert "also seen, NOT counted as an indicator" in src, "the verdict card"
    rr = (REPO / "octomod" / "reporting" / "round_report.py").read_text()
    assert "also seen, and not counted as an indicator" in rr, "section 8"
    spec = (REPO / "workflows" / "default.yaml").read_text()
    assert (
        "That\n                               # is ENFORCED" in spec
    ), "the comment and the behaviour must agree, and say so"
    print(
        "  shape screen  corroborates only; reported in also_seen, flag " "stays shut"
    )


if __name__ == "__main__":
    test_run_end_written_once()
    test_report_html_exists_before_the_verdict_ask()
    test_card_never_promises_a_skipped_expansion()
    test_scope_card_sentence_matches_what_was_bought()
    test_lineage_resolves_round_local_ids()
    test_evidence_tier_survives_a_generic_source_with_a_real_locator()
    test_md_candidate_card_shows_the_declared_axes_and_tier()
    test_model_report_renders_shared_assumptions_once()
    test_candidates_are_compared_in_one_drawing()
    test_the_shape_screen_corroborates_and_never_decides()
    print("LIVE BLIND 3 UNIT OK")
