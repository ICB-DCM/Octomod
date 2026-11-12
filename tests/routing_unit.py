"""The routing table is the source, and the page cannot drift from it (token-free).

  1. every role has a row and every row a role;
  2. `construction` is blind to the data: every data-bearing key is refused;
  3. enforcement is wired at the one seam, before the prompt is built;
  4. docs/ROUTING.md is generated from the table and current;
  5. a violation names the key and what is granted;
  6. the common keys reach every role;
  7. the table accepts every context-key set past ledgers recorded;
  8. the expansion agent sees the domain packs and, with research on, the
     items the research role retrieved for it: filtered, frozen once, reused;
  9. construction's context carries the curve descriptors in words exactly
     when the round holds data/phenomenology, and nothing else of
     the data.

    .venv/bin/python tests/routing_unit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from octomod import config  # noqa: E402
from octomod.agents import (  # noqa: E402
    ROLES,  # noqa: E402
    routing,  # noqa: E402
)

# The user's runs folder, deliberately not redirected by the battery: this
# reads existing runs, not ones this suite makes.
USER_RUNS = config.USER_RUNS_DIR


def test_every_role_has_a_row_and_every_row_a_role():
    """A role with no row cannot be called at all (enforce raises KeyError)."""
    assert set(ROLES) == set(routing.ROUTING), {
        "roles without a routing row": sorted(set(ROLES) - set(routing.ROUTING)),
        "rows without a role": sorted(set(routing.ROUTING) - set(ROLES)),
    }
    print(f"  coverage      {len(ROLES)} roles, {len(routing.ROUTING)} rows, same set")


def test_construction_is_blind_to_the_data():
    """No key that carries or summarises measurements reaches construction."""
    forbidden = (
        "data_file_previews",
        "data_signals",
        "design_summary",
        "data_labels",
        "measurements_long",
        "residual_diagnostics",
        "selection_table",
        "evaluation_report",
    )
    granted = routing.allowed("construction")
    leaked = [k for k in forbidden if k in granted]
    assert not leaked, f"construction is granted {leaked}"
    for key in forbidden:
        try:
            routing.enforce("construction", ["intent", key])
        except routing.RoutingViolation as e:
            assert key in str(e), e
        else:
            raise AssertionError(f"enforce() let {key!r} through to construction")
    print(
        f"  blind         construction refuses all {len(forbidden)} data-bearing keys"
    )


def test_enforce_is_wired_at_the_one_seam():
    """Enforced at the call site, where a module's own context dict cannot bypass it."""
    src = (REPO / "octomod" / "orchestration" / "run_context.py").read_text()
    assert (
        "routing.enforce(role, context.keys())" in src
    ), "RunContext.call must enforce routing before the prompt is built"
    i, j = src.index("routing.enforce("), src.index("out = call_agent(")
    assert i < j, "enforcement must run BEFORE the agent call, not after"
    print("  wired         RunContext.call enforces before the prompt is built")


def test_the_page_is_generated_and_current():
    path = REPO / "docs" / "ROUTING.md"
    assert path.exists(), "docs/ROUTING.md is missing; run tools/make_routing.py"
    assert path.read_text() == routing.render_markdown(), (
        "docs/ROUTING.md is stale; regenerate with "
        "`.venv/bin/python tools/make_routing.py`"
    )
    print("  page          docs/ROUTING.md matches the table byte for byte")


def test_a_violation_names_the_key_and_what_is_granted():
    """A violation is actionable from the terminal: the key, the page, the grant."""
    try:
        routing.enforce("observation", ["intent", "truth_curves"])
    except routing.RoutingViolation as e:
        msg = str(e)
    else:
        raise AssertionError("no violation raised")
    assert "truth_curves" in msg and "ROUTING.md" in msg, msg
    assert "granted:" in msg and "data_signals" in msg, msg
    print("  message       names the key, the page, and what IS granted")


def test_common_keys_reach_every_role():
    """Retries and human redrafts can happen on any call, so every role gets COMMON."""
    for role in routing.ROUTING:
        for key in routing.COMMON:
            assert key in routing.allowed(role), (role, key)
    print(f"  common        {len(routing.COMMON)} keys granted to every role")


def test_the_table_matches_what_the_engine_actually_sent():
    """Every context-key set in the user's past ledgers, replayed against the table."""
    seen: dict[str, set] = {}
    # runs are records (runs/*.h5); legacy runs are directories
    from octomod.result.runstore import RunStore

    def _ledgers():
        for store in RunStore.all_in(USER_RUNS)[-200:]:
            try:
                yield store.ledger_rows()
            except Exception:  # noqa: BLE001 - a foreign or broken file is skipped
                continue
        for led in sorted(USER_RUNS.glob("*/ledger.jsonl"))[:200]:
            rows = []
            for line in led.open():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
            yield rows

    for rows in _ledgers():
        for rec in rows:
            if rec.get("context_keys") and rec.get("module") in routing.ROUTING:
                seen.setdefault(rec["module"], set()).update(rec["context_keys"])
    if not seen:
        # `runs/` is the user's gitignored folder, so a fresh checkout has no
        # history to replay; an absent fixture is not a defect, so the check
        # says it was skipped and the other checks still assert.
        print(
            "  history       SKIPPED — no ledger with context_keys under "
            f"{USER_RUNS.name}/, so the table was NOT checked against history. "
            "That check needs runs this machine has actually made."
        )
        return
    bad = {
        r: routing.violations(r, k) for r, k in seen.items() if routing.violations(r, k)
    }
    assert not bad, f"the table would have rejected past runs: {bad}"
    print(
        f"  history       {len(seen)} roles replayed from past ledgers, none rejected"
    )


# the canned research reply the expansion asks for: one item inside the
# horizon, one past it (the engine drops it before any agent sees it)
_EXPANSION_RESEARCH = {
    "evidence_items": [
        {
            "source": "Product inhibition of the A-to-B step (fixture)",
            "title": "Product inhibition of the conversion step",
            "year": 2021,
            "locator": "figure 3",
            "supports": "B inhibits its own formation from A",
            "quote": "B inhibits its own formation",
            "url": "",
        },
        {
            "source": "Late result (fixture)",
            "title": "A result past the horizon",
            "year": 2027,
            "locator": "abstract",
            "supports": "would settle it",
            "quote": "",
            "url": "",
        },
    ],
    "queries_run": ["A B conversion feedback (fixture)"],
    "notes": "FIXTURE",
}


def _expansion_ctx(tmp: Path, research: str):
    """A round-0 context whose case has research `research` ('on', 'off' at
    expansion, or 'none'), a winner's model in the record, and a canned research
    reply."""
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import RunContext
    from octomod.result import node as tree
    from octomod.spec import WorkflowSpec
    from tests._record import record_at

    case = tmp / "case"
    (case / "stubs").mkdir(parents=True)
    yaml_text = "name: unit\n"
    if research != "none":
        yaml_text += "research:\n  enabled: true\n  max_publication_year: 2025\n"
    if research == "off":
        yaml_text += "  at_expansion: false\n"
    (case / "testcase.yaml").write_text(yaml_text)
    (case / "description.md").write_text("A converts to B; B is lost.\n")
    (case / "stubs" / "research.json").write_text(json.dumps(_EXPANSION_RESEARCH))
    run = record_at(tmp / "run.h5")
    run.store.create()
    (run / "intent").put(
        {
            "question": "unit",
            "system": "toy",
            "inference_target": "prediction",
            "domain_packs": ["general-dynamics"],
        }
    )
    ctx = RunContext(
        root=run,
        testcase_dir=case,
        spec=WorkflowSpec.load(REPO / "workflows" / "default.yaml"),
        ledger=Ledger(run.store),
        backend="stub",
        auto=True,
    )
    mdir = tree.model_node(ctx.round, "M1")
    (mdir / "antimony").put_text(
        "model m\n  R1: A -> B; k1*A\n  R2: B -> ; k2*B\n"
        "  A = 1; B = 0; k1 = 0.1; k2 = 0.05\nend\n"
    )
    (mdir / "glossary").put(
        {
            "species": [
                {"id": "A", "denotes": "the precursor pool"},
                {"id": "B", "denotes": "the product"},
            ]
        }
    )
    return ctx, mdir


def _research_calls(ctx) -> int:
    return sum(
        1
        for e in ctx.ledger.entries()
        if e.get("event") == "agent_call" and e.get("role") == "research"
    )


def test_the_expansion_sees_the_packs_and_the_research_it_asked_for():
    """The biology side of the expansion agent's payload: the intent's domain
    packs always, and with research on, what the research role found for THIS
    model's misfit — filtered by the case's fence, frozen in the round, reused
    on a resume, and archived apart from construction's research call."""
    import tempfile

    from octomod.agents import build_prompt
    from octomod.workflow_modules.model import engine as model_module

    for key in ("domain_packs", "retrieved_evidence", "evidence_instruction"):
        assert key in routing.allowed("revision"), key
    for key in ("model_summary", "misfit_summary", "instruction"):
        assert key in routing.allowed("research"), key
    ev = {"open": True, "reasons": ["obs_B: residual sigma 1.5x the replicate floor"]}
    with tempfile.TemporaryDirectory() as d:
        ctx, mdir = _expansion_ctx(Path(d), "on")
        add, lines = model_module.expansion_biology(ctx, mdir, ev, "M1")
        routing.enforce("revision", ["intent", *add])
        assert add.get("domain_packs") == ctx.pack_texts() and add["domain_packs"].get(
            "general-dynamics"
        ), sorted(add)
        items = add.get("retrieved_evidence") or []
        assert [(i.get("id"), i.get("origin")) for i in items] == [
            ("res_1", "research")
        ], items
        frozen = ctx.round / model_module.EXPANSION_EVIDENCE
        snap = frozen.get()
        assert len(snap["items"]) == 1 and [x["reason"] for x in snap["dropped"]] == [
            "published after 2025"
        ], snap
        prompt = build_prompt("revision", {"intent": ctx.intent, **add}, None)
        pack_line = next(
            ln
            for ln in add["domain_packs"]["general-dynamics"].splitlines()
            if ln.strip()
        )
        # the prompt carries the pack as JSON, so the line as JSON escapes it
        assert "## domain_packs" in prompt and json.dumps(pack_line)[1:-1] in prompt
        assert "Product inhibition of the conversion step" in prompt
        assert "A result past the horizon" not in prompt
        # the expansion's own research call: a flat entry of its own, research_expansion
        asked = (ctx.agent_calls / "research_expansion/prompt").text()
        for want in (
            "## model_summary",
            "R1: A -> B; k1*A",
            "the precursor pool",
            "## misfit_summary",
            "1.5x the replicate floor",
            "## instruction",
            "## restrictions",
        ):
            assert want in asked, want
        assert not (
            ctx.agent_calls.child("research") / "reply"
        ).exists(), "the expansion's research reply overwrote construction's slot"
        assert any(
            "1 literature item" in ln and model_module.EXPANSION_EVIDENCE in ln
            for ln in lines
        ), lines
        # a resume: the frozen snapshot, no second call
        add2, lines2 = model_module.expansion_biology(ctx, mdir, ev, "M1")
        assert _research_calls(ctx) == 1, _research_calls(ctx)
        assert add2 == add and lines2 == lines
        assert any(
            e.get("event") == "note" and "reused" in str(e.get("note"))
            for e in ctx.ledger.entries()
        )
    with tempfile.TemporaryDirectory() as d:
        # the agent was already asked in this round without research (a paused
        # legacy run): asking again would pay for items nobody reads
        ctx, mdir = _expansion_ctx(Path(d), "on")
        (ctx.round / "expansion_diagnostics").put(
            {"steps": [], "final_proposal": {"axes": []}}
        )
        add, lines = model_module.expansion_biology(ctx, mdir, ev, "M1")
        assert _research_calls(ctx) == 0 and "retrieved_evidence" not in add
        assert any("not run" in ln for ln in lines), lines
    for research in ("off", "none"):
        with tempfile.TemporaryDirectory() as d:
            ctx, mdir = _expansion_ctx(Path(d), research)
            add, lines = model_module.expansion_biology(ctx, mdir, ev, "M1")
            assert sorted(add) == ["domain_packs"], (research, sorted(add))
            assert _research_calls(ctx) == 0 and not lines, (research, lines)
    print(
        "  expansion     packs always; with research on, the retrieved items "
        "(fenced, frozen once, reused, archived apart from construction's)"
    )


def test_construction_reads_the_curve_descriptors_when_the_round_has_them():
    """The construction payload carries `data_phenomenology` (sentences and how
    to read them) when the round's data group holds the record, and not
    otherwise; the keys it sends still pass the construction row."""
    import tempfile

    from octomod.workflow_modules.data import phenomenology
    from octomod.workflow_modules.model import engine as model_module

    sentences = [
        "y under stimulus: rises (half-maximum by ~5), plateaus by ~20 in "
        "every condition; monotone in dose."
    ]
    with tempfile.TemporaryDirectory() as d:
        ctx, _ = _expansion_ctx(Path(d), "none")
        before = model_module._construction_context(ctx, None, "prediction")
        assert "data_phenomenology" not in before, sorted(before)
        phenomenology.node(ctx.round).put(
            {"available": True, "sentences": sentences, "descriptors": []}
        )
        after = model_module._construction_context(ctx, None, "prediction")
        view = after.get("data_phenomenology")
        assert isinstance(view, dict), sorted(after)
        assert view["sentences"] == sentences, view
        assert view["how_to_read_this"] == phenomenology.HOW_TO_READ
        routing.enforce("construction", after.keys())
        extra = set(after) - set(before)
        assert extra == {"data_phenomenology"}, extra
    print(
        "  descriptors   construction gets the curve descriptors when the round "
        "has them, and only then"
    )


if __name__ == "__main__":
    test_every_role_has_a_row_and_every_row_a_role()
    test_construction_is_blind_to_the_data()
    test_enforce_is_wired_at_the_one_seam()
    test_the_page_is_generated_and_current()
    test_a_violation_names_the_key_and_what_is_granted()
    test_common_keys_reach_every_role()
    test_the_table_matches_what_the_engine_actually_sent()
    test_the_expansion_sees_the_packs_and_the_research_it_asked_for()
    test_construction_reads_the_curve_descriptors_when_the_round_has_them()
    print("ROUTING UNIT OK — construction stays blind and the page cannot drift")
