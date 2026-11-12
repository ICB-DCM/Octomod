"""The knowledge module end to end on a stub fixture, and the run start it
gates. Token-free and offline: every source is a case document fetched over
`file:`, which the citation check reads as not checkable without the network.

The fixture is a temporary copy of `toy_phos_knowledge` with a survey of its own:
the required phosphorylation R -> Rp with one direct source; the
dephosphorylation Rp -> R, essential, with two sources that each earn medium
and one that contradicts it; a degradation that is not essential; one fact for
construction and one assay fact for the observation model; and a stubbed
verifier that reads one of the dephosphorylation's sources as a related system.

  (a) `knowledge --mode offline`: the folder is written, every grade is
      `not_applicable`, no verifier is asked, the card is printed;
  (b) `knowledge --mode online`: the folder is replaced, the documents cached,
      every entry graded — the dephosphorylation `medium`, contested and
      disputed — the verifier's second classifications on the items, the
      suggested floor `medium`, the card printed; `--show` prints it again;
  (c) a run on that folder without `grounding.support_floor` is refused by
      name at run start; with the person's floor it starts, and its ledger has
      the `grounding_fence` row and round 0's floor; the intent card shows the
      module's lines; a required reaction added after the module ran is
      refused by name;
  (d) `grounding: {skip: true, why: fixture}` with no `knowledge/` starts as
      today; with neither, the run is refused: run the module first.

    uv run python tests/knowledge_cli_smoke.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402

from tests._record import ledger_rows, pending_gate, rnd, run_root  # noqa: E402

SOURCE = REPO / "testcase" / "toy_phos_knowledge"
NOTE = "file:./sources/receptor_note.txt"
MODEL = "file:./sources/phosphatase_model.txt"
DISPUTE = "file:./sources/phosphatase_dispute.txt"
TURNOVER = "file:./sources/receptor_turnover.txt"


def _item(source, url, quote, kind, context, stance="supports", **over) -> dict:
    return {
        "source": source,
        "title": source.split(" — ")[0],
        "year": 2021,
        "locator": "paragraph 2",
        "supports": quote or "what the note says",
        "quote": quote,
        "url": url,
        "evidence_kind": kind,
        "context_match": context,
        "context_note": "the receptor module or a related receptor",
        "stance": stance,
        **over,
    }


SURVEY = {
    "system": {
        "summary": "A receptor phosphorylated by its ligand and returned by a "
        "constitutive phosphatase.",
        "scope": "the receptor module in one cell line, and one related receptor",
        "unknowns": ["whether the phosphatase is the only route back"],
    },
    "species": [
        {
            "id": "R",
            "name": "unphosphorylated receptor",
            "represents": "R",
            "identifiers": {"go_compartment": "go:0005886"},
        },
        {"id": "Rp", "name": "phosphorylated receptor", "represents": "Rp"},
    ],
    "reactions": [
        {
            "equation": "R -> Rp",
            "required": "req_1",
            "essential": True,
            "type": "phosphorylation",
            "description": "ligand-driven phosphorylation",
            "evidence": [
                _item(
                    "Receptor module phosphorylation kinetics — a note (fixture, 2024)",
                    NOTE,
                    "ligand addition drives phosphorylation of R to Rp within minutes",
                    "direct_experimental",
                    "same_system",
                )
            ],
        },
        {
            "equation": "Rp -> R",
            "essential": True,
            "type": "dephosphorylation",
            "description": "constitutive dephosphorylation",
            "evidence": [
                _item(
                    "Receptor module phosphorylation kinetics — a note (fixture, 2024)",
                    NOTE,
                    "a constitutive phosphatase returns Rp to R",
                    "direct_experimental",
                    "same_system",
                ),
                _item(
                    "A two-state model of receptor phosphorylation — a note "
                    "(fixture, 2021)",
                    MODEL,
                    "writes the dephosphorylation of Rp as first order in Rp",
                    "mechanistic_model",
                    "related_system",
                ),
                _item(
                    "A dispute over the phosphatase — a note (fixture, 2022)",
                    DISPUTE,
                    "did not slow the return of Rp to R",
                    "direct_experimental",
                    "related_system",
                    stance="contradicts",
                ),
            ],
        },
        {
            "equation": "Rp ->",
            "essential": False,
            "type": "degradation",
            "description": "degradation after internalisation, over hours",
            "evidence": [
                _item(
                    "Receptor turnover in a related receptor family — a note "
                    "(fixture, 2018)",
                    TURNOVER,
                    "",
                    "indirect",
                    "related_system",
                )
            ],
        },
    ],
    "facts": [
        {
            "kind": "timescale",
            "statement": "phosphorylation of R to Rp follows ligand within minutes",
            "value": 5,
            "unit": "min",
            "applies_to": ["R", "Rp"],
            "for": ["construction"],
            "evidence": [
                _item(
                    "Receptor module phosphorylation kinetics — a note (fixture, 2024)",
                    NOTE,
                    "ligand addition drives phosphorylation of R to Rp within minutes",
                    "direct_experimental",
                    "same_system",
                )
            ],
        },
        {
            "kind": "assay",
            "statement": "phospho-R is read by densitometry in arbitrary units, "
            "background-subtracted",
            "applies_to": ["the pR_au readout"],
            "for": ["observation"],
            "evidence": [],
        },
    ],
    "queries_run": ["receptor phosphorylation kinetics (fixture)"],
    "notes": "FIXTURE: the assay fact has no source beyond the lab note.",
}

VERIFIER = {
    "classifications": [
        {
            "id": "req_1.e1",
            "evidence_kind": "direct_experimental",
            "context_match": "same_system",
            "stance": "supports",
            "note": "the note shows the conversion in these cells",
        },
        {
            "id": "rx_1.e1",
            "evidence_kind": "direct_experimental",
            "context_match": "related_system",
            "stance": "supports",
            "note": "read as the related line",
        },
        {
            "id": "rx_1.e2",
            "evidence_kind": "mechanistic_model",
            "context_match": "related_system",
            "stance": "supports",
            "note": "a model of a related receptor",
        },
        {
            "id": "rx_1.e3",
            "evidence_kind": "direct_experimental",
            "context_match": "related_system",
            "stance": "contradicts",
            "note": "argues against the phosphatase route",
        },
        {
            "id": "rx_2.e1",
            "evidence_kind": "indirect",
            "context_match": "related_system",
            "stance": "supports",
            "note": "correlational, over hours",
        },
        {
            "id": "fact_1.e1",
            "evidence_kind": "direct_experimental",
            "context_match": "same_system",
            "stance": "supports",
            "note": "within minutes",
        },
    ]
}


# the case documents the stubbed items name, written into the copy so the
# suite reads only what it declares
DOCUMENTS = {
    "receptor_note.txt": (
        "Receptor module phosphorylation kinetics — a note (fixture document).\n\n"
        "In cells expressing the receptor module, ligand addition drives\n"
        "phosphorylation of R to Rp within minutes; a constitutive phosphatase\n"
        "returns Rp to R.\n"
    ),
    "phosphatase_model.txt": (
        "A two-state model of receptor phosphorylation — a note (fixture document).\n"
        "\nA published two-state model of a related receptor writes the\n"
        "dephosphorylation of Rp as first order in Rp.\n"
    ),
    "phosphatase_dispute.txt": (
        "A dispute over the phosphatase — a note (fixture document).\n\n"
        "In a related receptor line, blocking the constitutive phosphatase did not\n"
        "slow the return of Rp to R, which argues against a phosphatase route.\n"
    ),
    "receptor_turnover.txt": (
        "Receptor turnover in a related receptor family — a note (fixture "
        "document).\n\nOver several hours, phosphorylated receptors of a related "
        "family are internalised and degraded.\n"
    ),
}


def make_case(where: Path, name: str, *, stubs: bool = True) -> Path:
    """A copy of the source fixture as the knowledge module's staging folder:
    its data, lab note, intent and blocklist; the survey and the verifier
    stubbed; the documents the stubbed items cite; no grounding block yet."""
    case = where / name
    shutil.copytree(SOURCE, case)
    # the source fixture's own module replies and its staged output: this
    # suite stages the module itself, from the replies below
    # `knowledge*.json` also matches the verifier's `knowledge_verification*.json`
    for stale in list((case / "stubs").glob("knowledge*.json")):
        stale.unlink()
    shutil.rmtree(case / "knowledge", ignore_errors=True)
    (case / "sources").mkdir(exist_ok=True)
    for doc, text in DOCUMENTS.items():
        (case / "sources" / doc).write_text(text)
    tc = yaml.safe_load((case / "testcase.yaml").read_text())
    tc = {
        "name": name,
        "holdout": tc["holdout"],
        "supplied": {},
        "research": {"max_publication_year": 2025},
    }
    (case / "testcase.yaml").write_text(yaml.safe_dump(tc, sort_keys=False))
    if stubs:
        (case / "stubs" / "knowledge.json").write_text(json.dumps(SURVEY, indent=2))
        (case / "stubs" / "knowledge_verification.json").write_text(
            json.dumps(VERIFIER, indent=2)
        )
    return case


def env(runs: Path) -> dict:
    out = dict(os.environ)
    # the battery's own runs directory when it sets one; never `runs/`
    out.setdefault("OCTOMOD_RUNS_DIR", str(runs))
    return out


def cli(args: list[str], runs: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, "-m", "octomod", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=900,
        env=env(runs),
    )


def runs_dir(runs: Path) -> Path:
    return Path(env(runs)["OCTOMOD_RUNS_DIR"])


def start(case: Path, run_id: str, runs: Path) -> subprocess.CompletedProcess:
    return cli(
        [
            "run",
            "--testcase",
            str(case),
            "--backend",
            "stub",
            "--run-id",
            run_id,
            "--gate-mode",
            "file",
        ],
        runs,
    )


def _set_grounding(case: Path, block: dict | None) -> None:
    tc = yaml.safe_load((case / "testcase.yaml").read_text())
    tc.pop("grounding", None)
    if block is not None:
        tc["grounding"] = block
    (case / "testcase.yaml").write_text(yaml.safe_dump(tc, sort_keys=False))


def _entries(d: dict) -> dict:
    return {e["id"]: e for e in (d.get("reactions") or []) + (d.get("facts") or [])}


def test_offline(case: Path, runs: Path) -> None:
    p = cli(
        [
            "knowledge",
            "--testcase",
            str(case),
            "--mode",
            "offline",
            "--backend",
            "stub",
        ],
        runs,
    )
    check("offline: the module exits 0", p.returncode == 0, p.stdout + p.stderr)
    folder = case / "knowledge"
    d = json.loads((folder / "knowledge.json").read_text())
    grades = {k: e.get("grade") for k, e in _entries(d).items()}
    check(
        "offline: every reaction and fact is graded not_applicable",
        d["mode"] == "offline"
        and set(grades) == {"req_1", "rx_1", "rx_2", "fact_1", "fact_2"}
        and set(grades.values()) == {"not_applicable"},
        str(grades),
    )
    calls = sorted(x.name for x in (folder / "calls").glob("*"))
    check(
        "offline: one survey call archived, no verifier asked",
        calls
        == [
            "knowledge.1.meta.json",
            "knowledge.1.prompt.txt",
            "knowledge.1.reply.json",
        ],
        str(calls),
    )
    prompt = (folder / "calls" / "knowledge.1.prompt.txt").read_text()
    check("offline: the call was granted no tools", "TOOLS: none" in prompt)
    check(
        "offline: the intent as it stood is kept beside the output",
        (folder / "intent_before.yaml").read_text()
        == (case / "intent.yaml").read_text(),
    )
    check(
        "offline: the card is printed, the suggestion not applicable",
        "ESSENTIAL REACTIONS" in p.stdout
        and "SUGGESTED FLOOR: not applicable" in p.stdout
        and "FACTS — 2" in p.stdout,
        p.stdout[-1500:],
    )
    log = (case / "curation" / "STAGING_LOG.md").read_text()
    check(
        "offline: one staging-log line",
        log.count("· knowledge.1 · survey, offline ·") == 1,
        log,
    )


def test_online(case: Path, runs: Path) -> str:
    p = cli(
        ["knowledge", "--testcase", str(case), "--mode", "online", "--backend", "stub"],
        runs,
    )
    check("online: the module exits 0", p.returncode == 0, p.stdout + p.stderr)
    folder = case / "knowledge"
    d = json.loads((folder / "knowledge.json").read_text())
    e = _entries(d)
    grades = {k: v.get("grade") for k, v in e.items()}
    check(
        "online: every entry graded — required high, the dephosphorylation "
        "medium, the degradation weak, the facts high and none",
        grades
        == {
            "req_1": "high",
            "rx_1": "medium",
            "rx_2": "weak",
            "fact_1": "high",
            "fact_2": "none",
        },
        str(grades),
    )
    flags = {f.get("flag") for f in e["rx_1"].get("flags") or []}
    check(
        "online: the dephosphorylation is contested and its disputed class shown",
        {"contested", "disputed_class"} <= flags,
        str(flags),
    )
    first = e["rx_1"]["evidence"][0]
    check(
        "online: the verifier's second classification is on the item",
        first.get("second_context") == "related_system"
        and first.get("second_kind") == "direct_experimental"
        and first.get("second_stance") == "supports"
        and d.get("verification", {}).get("n_disagree") == 1,
        json.dumps({k: first.get(k) for k in first if k.startswith("second")}),
    )
    check(
        "online: each quote found in its cached case document",
        all(
            it.get("quote_found") is True
            for ent in e.values()
            for it in ent.get("evidence") or []
            if it.get("quote")
        )
        and len(list((folder / "sources").glob("*"))) == 4,
        str(sorted(x.name for x in (folder / "sources").glob("*"))),
    )
    check(
        "online: the suggested floor is medium, and at high the dephosphorylation "
        "leaves the base",
        (d.get("suggestion") or {}).get("band") == "medium"
        and (d["suggestion"].get("leaves_at") or {}).get("high") == ["rx_1"],
        str(d.get("suggestion")),
    )
    calls = sorted(x.name for x in (folder / "calls").glob("*.meta.json"))
    check(
        "online: the survey and the verifier archived; the offline run's output replaced",
        calls == ["knowledge.1.meta.json", "knowledge_verification.1.meta.json"]
        and d["mode"] == "online",
        str(calls),
    )
    prompt = (folder / "calls" / "knowledge.1.prompt.txt").read_text()
    check(
        "online: the survey was granted research's tools; the verifier none",
        "TOOLS: WebSearch, WebFetch" in prompt
        and "TOOLS: none"
        in (folder / "calls" / "knowledge_verification.1.prompt.txt").read_text(),
    )
    check(
        "online: the card — bands, the contested flag, the suggestion, the "
        "trade-off, the forms",
        "SUGGESTED FLOOR: medium" in p.stdout
        and "contested by rx_1.e3" in p.stdout
        and "TRADE-OFF:" in p.stdout
        and "floor: <band|none>" in p.stdout,
        p.stdout[-2500:],
    )
    log = (case / "curation" / "STAGING_LOG.md").read_text()
    check(
        "online: the staging log gains a line per call",
        log.count("· knowledge.1 ·") == 2
        and log.count("knowledge_verification.1") == 1,
        log,
    )
    return p.stdout


def test_show(case: Path, runs: Path, printed: str) -> None:
    p = cli(["knowledge", "--testcase", str(case), "--show"], runs)
    card = p.stdout.strip()
    check(
        "--show prints the card again from the folder, nothing called",
        p.returncode == 0
        and card
        and card in printed
        and len(list((case / "knowledge" / "calls").glob("*.meta.json"))) == 2,
        p.stdout + p.stderr,
    )


def test_run_start(case: Path, runs: Path) -> None:
    p = start(case, "kncli_nofloor", runs)
    check(
        "a run without the person's floor is refused by name, exit 2",
        p.returncode == 2 and "decide the support floor" in p.stderr,
        (p.stdout + p.stderr)[-800:],
    )
    _set_grounding(case, {"support_floor": "medium", "decided_by": "human"})
    p = start(case, "kncli_floor", runs)
    check(
        "with the person's floor the run starts and pauses at the intent card",
        p.returncode == 3,
        (p.stdout + p.stderr)[-1500:],
    )
    root = run_root("kncli_floor", runs_dir(runs))
    rows = ledger_rows(root)
    fence = [r for r in rows if r.get("event") == "grounding_fence"]
    check(
        "the grounding_fence row: mode, floor, its source, step, horizon, blocklist",
        len(fence) == 1
        and fence[0].get("mode") == "online"
        and fence[0].get("support_floor") == "medium"
        and fence[0].get("floor_source") == "human"
        and fence[0].get("floor_step") == 1
        and fence[0].get("horizon") == 2025
        and fence[0].get("forbidden_sources") == ["blocked-preprints.example"],
        str(fence),
    )
    floor = (rnd(root, 0) / "space/floor").get(None)
    check(
        "round 0's floor is written from the person's decision, and ledgered",
        floor == {"band": "medium", "step": 1, "source": "human"}
        and any(r.get("event") == "floor_set" for r in rows),
        str(floor),
    )
    card = json.dumps(pending_gate(root) or {})
    check(
        "the intent card shows the module's lines: lists, floor, the intent's diff",
        "req_1  R -> Rp" in card
        and "rx_1  Rp -> R" in card
        and "support floor:   medium (the person)" in card
        and "intent vs the one the module saw: no change" in card,
        card[:2000],
    )
    check(
        "the record holds the module's folder",
        (root / "input" / "knowledge" / "knowledge.json").exists(),
    )
    intent = yaml.safe_load((case / "intent.yaml").read_text())
    before = (case / "intent.yaml").read_text()
    intent["required_reactions"].append({"equation": "Rp ->"})
    (case / "intent.yaml").write_text(yaml.safe_dump(intent, sort_keys=False))
    p = start(case, "kncli_moved", runs)
    check(
        "a required reaction added after the module ran is refused by name",
        p.returncode == 2
        and "re-run the knowledge module" in p.stderr
        and "added Rp ->" in p.stderr,
        (p.stdout + p.stderr)[-800:],
    )
    (case / "intent.yaml").write_text(before)


def test_skip(where: Path, runs: Path) -> None:
    case = make_case(where, "knowledge_skip", stubs=False)
    p = start(case, "kncli_unstaged", runs)
    check(
        "no module output and no skip: refused, run the knowledge module first",
        p.returncode == 2 and "run the knowledge module first" in p.stderr,
        (p.stdout + p.stderr)[-800:],
    )
    _set_grounding(case, {"skip": True, "why": "fixture"})
    p = start(case, "kncli_skip", runs)
    check(
        "a declared skip starts as today, with no knowledge/ folder",
        p.returncode == 3 and not (case / "knowledge").exists(),
        (p.stdout + p.stderr)[-1500:],
    )
    root = run_root("kncli_skip", runs_dir(runs))
    fence = [r for r in ledger_rows(root) if r.get("event") == "grounding_fence"]
    check(
        "… its fence row records the skip, and round 0 has no floor",
        len(fence) == 1
        and fence[0].get("skip") == "fixture"
        and not (rnd(root, 0) / "space/floor").exists(),
        str(fence),
    )


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="octomod_knowledge_cli_"))
    runs = tmp / "runs"
    try:
        case = make_case(tmp, "knowledge_cli")
        print("offline")
        test_offline(case, runs)
        print("online")
        printed = test_online(case, runs)
        print("show")
        test_show(case, runs, printed)
        print("run start")
        test_run_start(case, runs)
        print("skip")
        test_skip(tmp, runs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return finish(
        "\nknowledge_cli_smoke",
        "\nOK — the knowledge module on a stub fixture, and the run start it gates",
    )


if __name__ == "__main__":
    sys.exit(main())
