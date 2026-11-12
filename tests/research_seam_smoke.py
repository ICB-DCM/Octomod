"""The research seam, exercised WITHOUT network.

`toy_phos_research` stubs a research reply with three items: one accepted (its
document a local `file:` URL), one past the 2025 horizon, one on the blocklist.

  1. one item is accepted, with its id and origin; two are dropped, reasons named;
  2. the accepted item's document is cached over file:, and the drops are ledgered;
  3. construction's prompt carries the accepted item and neither dropped one;
  4. the research role is called once, as a stub;
  5. before the expansion agent (a copy of `abcd_expansion` with research on),
     the research role is asked about what the selected model lacks, its items
     are fenced, frozen in the round and handed to the expansion agent with the
     domain packs, and a resume reuses them without a second call;
  6. the agent's biology-origin axis and its beyond-this-data list reach the
     card, the round's `expansion` record and ANALYSIS.md;
  7. the expansion agent asks for a literature search of its own
     (`requested_research`, beside its diagnostic requests): the research role
     is called with its questions, the snapshot is frozen in the round's
     `research_requests/1`, the next expansion call carries the items and
     `research_answered`, a second request is refused by name, the card lists
     the questions with how many items each returned, and a resume calls
     nothing again.

    uv run python tests/research_seam_smoke.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish, run_cli_captured  # noqa: E402

from octomod import config  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from tests._record import (  # noqa: E402
    ledger_rows,
    pending_gate,
    reports_dir,
    rnd,
    run_root,
    run_store,
)

# where runs are written: `test_runs/` under the battery (tests/run_all.py
# sets OCTOMOD_RUNS_DIR), `runs/` otherwise — never spell `runs/` here
RUNS = config.RUNS_DIR

EXPANSION_RUN = "research_at_expansion_smoke"
# the expansion's research reply: one item inside the horizon, one past it
FOUND = {
    "source": "KinA acts on PreC directly (fixture)",
    "title": "A direct KinA route to ProD",
    "year": 2022,
    "locator": "figure 2",
    "supports": "KinA converts PreC to ProD without RegB",
    "quote": "without RegB",
    "url": "",
}
LATE = {
    "source": "Late preprint (fixture)",
    "title": "A preprint past this case's horizon",
    "year": 2030,
    "locator": "abstract",
    "supports": "would settle it",
    "quote": "",
    "url": "",
}
BEYOND = {
    "mechanism": "a slow second phosphatase on RegB_p",
    "why_not_separable": "every arm is sampled after it would have acted",
    "experiment": "a 2-minute-resolution washout after u=4",
}
# what the expansion agent asks the literature, beside its diagnostics
QUESTIONS = [
    "Is a conversion of PreC to ProD catalysed by KinA without RegB described?",
    "Is ProD reported to feed back on RegB activation?",
]
SECOND_ASK = ["Is a ProD phosphatase described for this module?"]
# the research role's answer to them: one item for the first question, and one
# for the second past the case's horizon, dropped before any agent reads it
ANSWER = {
    "source": "KinA converts PreC in a RegB-null background (fixture)",
    "title": "PreC conversion survives loss of RegB",
    "year": 2021,
    "locator": "figure 4",
    "supports": "ProD accumulates when RegB is absent",
    "quote": "accumulates when RegB is absent",
    "url": "",
    "question": 1,
}
LATE_ANSWER = {
    "source": "Late feedback preprint (fixture)",
    "title": "A feedback preprint past the horizon",
    "year": 2031,
    "locator": "abstract",
    "supports": "ProD feeds back on RegB",
    "quote": "",
    "url": "",
    "question": 2,
}


def _expansion_fixture() -> Path:
    """`abcd_expansion` with research on: construction's research call finds
    nothing, the expansion's finds FOUND and LATE; the expansion agent asks for
    its diagnostics and a literature search at once (answered with ANSWER and
    LATE_ANSWER), asks for a second search (refused), then proposes as the case
    does, marking basal_route as from the biology and naming BEYOND."""
    case = Path(tempfile.mkdtemp()) / "abcd_expansion_research"
    shutil.copytree(
        REPO / "testcase" / "abcd_expansion",
        case,
        ignore=shutil.ignore_patterns("truth"),
    )
    with (case / "testcase.yaml").open("a") as f:
        f.write("\nresearch:\n  enabled: true\n  max_publication_year: 2025\n")
    stubs = case / "stubs"
    (stubs / "research.1.json").write_text(
        json.dumps(
            {"evidence_items": [], "queries_run": [], "notes": "FIXTURE: construction"}
        )
    )
    (stubs / "research.2.json").write_text(
        json.dumps(
            {
                "evidence_items": [FOUND, LATE],
                "queries_run": ["KinA PreC ProD route (fixture)"],
                "notes": "FIXTURE: before expansion",
            }
        )
    )
    (stubs / "research.3.json").write_text(
        json.dumps(
            {
                "evidence_items": [ANSWER, LATE_ANSWER],
                "queries_run": ["KinA PreC RegB-null (fixture)"],
                "notes": "FIXTURE: the search the expansion agent asked for",
            }
        )
    )
    # the case's sequence (diagnostics, proposal, repair) becomes: diagnostics
    # AND a search, a second search, proposal, repair
    replies = [
        json.loads((stubs / f"revision.{k}.json").read_text()) for k in (1, 2, 3)
    ]
    replies[0]["requested_research"] = QUESTIONS
    again = {
        "diagnosis": "FIXTURE: one more search before proposing",
        "requested_research": SECOND_ASK,
        "axes": [],
        "stop_instead": False,
    }
    for proposal in replies[1:]:
        for axis in proposal.get("axes") or []:
            if axis.get("id") == "basal_route":
                axis["origin"] = "biology"
        proposal["beyond_this_data"] = [BEYOND]
    for k, reply in enumerate([replies[0], again, *replies[1:]], start=1):
        (stubs / f"revision.{k}.json").write_text(json.dumps(reply, indent=2))
    return case


def _rows(root: Node) -> list[dict]:
    return ledger_rows(root)


def _research_calls(root: Node) -> int:
    return sum(
        1
        for e in _rows(root)
        if e.get("event") == "agent_call" and e.get("role") == "research"
    )


def _spy_on_agent_calls() -> tuple[list[tuple[str, dict]], object]:
    """Record the payload of every agent call from here on (role, the keys
    this suite reads); returns the record and the original method."""
    from octomod.orchestration.run_context import RunContext

    seen: list[tuple[str, dict]] = []
    real = RunContext.call

    def spy(self, role, context, calls=None, name=None):
        keep = (
            "questions",
            "model_summary",
            "retrieved_evidence",
            "research_answered",
            "research_refused",
            "research_instruction",
        )
        seen.append((role, json.loads(json.dumps({k: context.get(k) for k in keep}))))
        return real(self, role, context, calls=calls, name=name)

    RunContext.call = spy
    return seen, real


def check_research_before_expansion() -> None:
    from octomod.orchestration.run_context import RunContext

    seen, real = _spy_on_agent_calls()
    try:
        _check_research_before_expansion(seen)
    finally:
        RunContext.call = real


def _check_research_before_expansion(seen: list[tuple[str, dict]]) -> None:
    run_store(EXPANSION_RUN, RUNS).remove()
    root = run_root(EXPANSION_RUN, RUNS)
    case = _expansion_fixture()
    base = [
        "run",
        "--testcase",
        str(case),
        "--backend",
        "stub",
        "--run-id",
        EXPANSION_RUN,
        "--gate-mode",
        "file",
    ]
    rd0 = rnd(root, 0)

    def card() -> tuple[str, list[str]]:
        payload = pending_gate(root) or {}
        return payload.get("module", ""), [str(x) for x in payload.get("lines") or []]

    rc, out = run_cli_captured(base)
    scope = [("y", "axes: product_feedback")]
    for _ in range(30):
        if rc != 3 or card()[0] == "revision":
            break
        ans, note = scope.pop(0) if card()[0] == "model_scope" and scope else ("y", "")
        rc, out = run_cli_captured(
            base + ["--gate-answer", ans] + (["--gate-note", note] if note else [])
        )
    module, lines = card()
    check(
        "the run pauses at the expansion card",
        rc == 3 and module == "revision",
        f"rc={rc} {out[-400:]}",
    )
    check(
        "the research role was asked three times: for construction, before "
        "expansion, and once for the expansion agent's own questions",
        _research_calls(root) == 3,
        str(_research_calls(root)),
    )
    snap = (rd0 / "expansion_evidence").get(None) or {}
    check(
        "the expansion's items are fenced and frozen in the round: one kept, one dropped",
        [(i.get("id"), i.get("origin"), i.get("title")) for i in snap.get("items", [])]
        == [("res_1", "research", FOUND["title"])]
        and [d["reason"] for d in snap.get("dropped", [])] == ["published after 2025"],
        json.dumps(snap)[:300],
    )
    prompt = ((rd0 / "agent_calls").child("revision") / "prompt").text("")
    check(
        "the expansion agent's prompt carries the domain packs and the kept item only",
        "## domain_packs" in prompt
        and "## retrieved_evidence" in prompt
        and FOUND["title"] in prompt
        and LATE["title"] not in prompt,
    )
    # the expansion's own research call: a flat entry of its own, research_expansion
    asked = (rd0 / "agent_calls/research_expansion/prompt").text("")
    check(
        "the research role was told the selected model and where it misfits",
        "## model_summary" in asked and "## misfit_summary" in asked,
        asked[:200],
    )
    shown = "\n".join(lines)
    check(
        "the card says how many items the research role retrieved",
        "research before this proposal: 1 literature item" in shown,
        shown[:600],
    )
    check(
        "the card marks the basal_route axis as from the biology",
        any("basal_route" in x and "(from the biology)" in x for x in lines),
        shown[:600],
    )
    check(
        "the card lists what lies beyond this data, with its experiment",
        "BEYOND THIS DATA" in shown
        and BEYOND["mechanism"] in shown
        and BEYOND["experiment"] in shown,
        shown[-600:],
    )

    # 7 ---- the search the expansion agent asked for --------------------------
    research_payloads = [c for r, c in seen if r == "research"]
    expansion_payloads = [c for r, c in seen if r == "revision"]
    check(
        "the research role was handed the expansion agent's questions and the model",
        len(research_payloads) == 3
        and research_payloads[2].get("questions") == QUESTIONS
        and bool(research_payloads[2].get("model_summary"))
        and all(not p.get("questions") for p in research_payloads[:2]),
        json.dumps([p.get("questions") for p in research_payloads])[:300],
    )
    req_call = rd0 / "agent_calls/research_request_1"
    req_prompt = (req_call / "prompt").text("")
    check(
        "… archived apart from the pre-search, the questions in its prompt",
        "## questions" in req_prompt
        and QUESTIONS[0] in req_prompt
        and "## questions" not in asked
        and (rd0 / "agent_calls/research/prompt").exists(),
        req_call.key,
    )
    req_snap = (rd0 / "research_requests/1").get(None) or {}
    check(
        "its items are fenced and frozen in the round, numbered after the pre-search's",
        [
            (i.get("id"), i.get("title"), i.get("answers_question"))
            for i in req_snap.get("items", [])
        ]
        == [("res_2", ANSWER["title"], QUESTIONS[0])]
        and [d["reason"] for d in req_snap.get("dropped", [])]
        == ["published after 2025"]
        and req_snap.get("questions") == QUESTIONS,
        json.dumps(req_snap)[:400],
    )
    after = expansion_payloads[1] if len(expansion_payloads) > 1 else {}
    check(
        "the next expansion call carries the items and `research_answered`",
        [i.get("id") for i in after.get("retrieved_evidence") or []]
        == ["res_1", "res_2"]
        and after.get("research_answered") == QUESTIONS
        and not after.get("research_refused"),
        json.dumps(after)[:400],
    )
    refused_payload = expansion_payloads[2] if len(expansion_payloads) > 2 else {}
    check(
        "a second request is refused by name and the agent asked once more",
        "research already requested this round"
        in str((refused_payload.get("research_refused") or {}).get("why"))
        and (refused_payload.get("research_refused") or {}).get("questions")
        == SECOND_ASK,
        json.dumps(refused_payload.get("research_refused"))[:300],
    )
    rows = [e for e in _rows(root) if e.get("event") == "expansion_research_requested"]
    check(
        "both requests are ledgered with their questions: answered, refused",
        [(r.get("status"), r.get("questions")) for r in rows]
        == [("answered", QUESTIONS), ("refused", SECOND_ASK)],
        json.dumps(rows)[:400],
    )
    check(
        "the card lists the questions asked and how many items each returned",
        any(QUESTIONS[0] in x and "Q1 (1 item(s))" in x for x in lines)
        and any(QUESTIONS[1] in x and "Q2 (0 item(s))" in x for x in lines)
        and "(research_requests/1)" in shown,
        shown[:900],
    )
    check(
        "… and the refused request, by name",
        any("research already requested this round" in x for x in lines)
        and SECOND_ASK[0] in shown,
        shown[:900],
    )

    # a resume without an answer asks the same card, reusing the snapshot
    rc, out = run_cli_captured(base)
    check(
        "a resume asks the card again without a second research call",
        rc == 3 and card()[0] == "revision" and _research_calls(root) == 3,
        f"rc={rc} calls={_research_calls(root)}",
    )
    check(
        "… and the resumed card still lists the questions",
        pending_gate(root) is not None
        and any("Q1 (1 item(s))" in x for x in card()[1]),
    )
    check(
        "… and the reuse is ledgered",
        any(
            e.get("event") == "note"
            and "expansion evidence snapshot reused" in str(e.get("note"))
            for e in _rows(root)
        ),
    )
    rc, out = run_cli_captured(base + ["--gate-answer", "n"])
    decided = (rd0 / "expansion").get(None) or {}
    check(
        "a declined expansion records the list in the round's expansion",
        decided.get("expanded") is False
        and decided.get("beyond_this_data") == [BEYOND],
        json.dumps(decided)[:300],
    )
    md_path = reports_dir(root) / "ANALYSIS.md"
    md = md_path.read_text() if md_path.exists() else ""
    check(
        "ANALYSIS.md collects it under 'Beyond this data'",
        "## Beyond this data" in md and BEYOND["mechanism"] in md,
        f"rc={rc}",
    )
    check(
        "the research role was still called only three times",
        _research_calls(root) == 3,
        str(_research_calls(root)),
    )


def main() -> int:
    from octomod.cli import main as cli_main

    rid = f"c36_seam_{time.strftime('%H%M%S')}"
    rc = cli_main(
        [
            "run",
            "--testcase",
            str(REPO / "testcase" / "toy_phos_research"),
            "--backend",
            "stub",
            "--auto-approve",
            "--run-id",
            rid,
        ]
    )
    root = run_root(rid, RUNS)
    r0 = rnd(root, 0)
    rows = ledger_rows(root)
    check("the run completes with research on", rc == 0, f"exit {rc}")
    ev = (r0 / "evidence").get()
    check(
        "one item accepted, two dropped",
        len(ev["items"]) == 1 and len(ev["dropped"]) == 2,
        f"{len(ev['items'])} / {len(ev['dropped'])}",
    )
    check(
        "the accepted item carries the id and origin the contract promises",
        ev["items"][0].get("id") == "res_1"
        and ev["items"][0].get("origin") == "research",
        json.dumps({k: ev["items"][0].get(k) for k in ("id", "origin")}),
    )
    reasons = sorted(d["reason"] for d in ev["dropped"])
    check(
        "the drops name their reasons: blocklist and the horizon",
        reasons == ["blocklist", "published after 2025"],
        str(reasons),
    )
    acc = ev["items"][0]
    check(
        "the accepted item is the 2024 note",
        acc["year"] == 2024 and "fixture" in acc["source"],
    )
    check(
        "its document was cached by the engine over file:, no network",
        acc.get("fetch_status") == "cached"
        and str(acc.get("bytes", 0)) != "0"
        and (r0 / "evidence_sources").child(acc["cached_file"]).exists(),
        str({k: acc.get(k) for k in ("fetch_status", "cached_file", "bytes")}),
    )
    note = [
        e
        for e in rows
        if e.get("event") == "note" and "evidence filter dropped" in str(e.get("note"))
    ]
    check(
        "the drop note is ledgered with both reasons",
        note
        and "blocklist" in note[0]["note"]
        and "published after 2025" in note[0]["note"],
        str(note[0]["note"])[:120] if note else "no note",
    )
    prompt = ((r0 / "agent_calls").child("construction") / "prompt").text()
    # the archived prompt is JSON with ensure_ascii, so a source with an em dash
    # appears as `\u2014`; assert on the ASCII title instead of the source string
    check(
        "construction's archived prompt carries the accepted item (retrieved_evidence, its title)",
        "retrieved_evidence" in prompt and acc["title"] in prompt,
    )
    check(
        "… and neither dropped item",
        "Past-horizon result" not in prompt
        and "blocked-preprints.example" not in prompt,
    )
    calls = [
        e
        for e in rows
        if e.get("event") == "agent_call" and e.get("role") == "research"
    ]
    check(
        "the research role was called once, as a stub",
        len(calls) == 1 and calls[0]["backend"] == "stub",
    )
    check(
        "the accepted item's URL is a file: URL — the battery fetched nothing over the network",
        str(acc.get("url", "")).startswith("file:"),
    )
    check_research_before_expansion()
    return finish(
        "RESEARCH SEAM",
        "RESEARCH SEAM OK — the filter, the drop note, the source cache, construction's evidence and the research before expansion ran in the battery, offline",
    )


if __name__ == "__main__":
    sys.exit(main())
