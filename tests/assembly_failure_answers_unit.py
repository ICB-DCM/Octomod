"""`redraft:` and `fallback:` at the gate S3 asks when its battery stays blocked.

The observation block names a sigma it does not estimate, so the merge refuses
it (`assembly_merge_noise`, routed like a failing T0 check to observation),
and the role's redraft budget is already spent. The S3 battery loop
(`_battery_with_feedback`) then asks `assembly_redraft_budget`, driven here
in file-gate mode with no agent reachable:

  1. with no answer stored the gate pauses, and its card offers both forms;
  2. `fallback: additive-noise` rewrites the noise block, is signed by the
     human and ledgered as `assembly_fallback`, written beside the agent's
     untouched reply, and the battery re-runs to a pass on the rewritten block;
  3. `redraft: <words>` sends the words back to observation as the
     human's (RedraftRequested), removes the superseded assembly files and
     ledgers the request, spending no attempt;
  4. an unattributable failure's redraft goes to the assembly agents as a whole;
  5. a grant (`n=1`) goes back to the agent that must rewrite the refused
     block, whether the refused merge left no tables or an earlier merge's.

    uv run python tests/assembly_failure_answers_unit.py
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
logging.disable(logging.WARNING)

from _harness import check_detail_on_fail, finish  # noqa: E402
from _record import ledger_rows, record_at  # noqa: E402

from octomod.gates import GateResult  # noqa: E402
from octomod.orchestration.interaction import human_redraft, humangate  # noqa: E402
from octomod.orchestration.interaction.retry import (  # noqa: E402
    AttemptHistory,
    dossier_of,
)
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.run_context import RunContext  # noqa: E402
from octomod.result.node import Node  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly import engine as S3  # noqa: E402

SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")
GATE = "assembly_redraft_budget"
ROLE = "observation"
WORDS = "use one constant sigma per observable"
BUDGET = int(SPEC.get("retry.module_draft", 2))


class Ctx(RunContext):
    """A RunContext on a throwaway record (the run is one file), round 0,
    single model: what the S3 battery loop and its failure-point gate read."""

    def __init__(self, root: Node):
        super().__init__(
            root=root,
            testcase_dir=REPO / "testcase" / "toy_phos",
            spec=SPEC,
            ledger=Ledger(root),
            backend="stub",
            auto=False,
        )

    @property
    def intent(self) -> dict:
        return {"question": "does A decay into B?"}

    @property
    def testcase(self) -> dict:
        return {"holdout": {"condition_labels": []}}

    def call(self, role: str, context: dict) -> dict:
        raise AssertionError(f"no agent may be called here; {role} was")


class AnsweringCtx(Ctx):
    """A run whose observation-model agent answers the re-ask with `reply`."""

    description = "A decays into B."

    def __init__(self, root: Node, reply: dict):
        super().__init__(root)
        self.reply, self.calls = reply, []

    def pack_texts(self, pack_ids=None) -> dict:
        return {}

    def call(self, role: str, context: dict, calls=None) -> dict:
        self.calls.append(role)
        (self.agent_calls.child(role) / "reply").put(self.reply)
        return json.loads(json.dumps(self.reply))


def _sbml() -> str:
    import antimony

    antimony.loadAntimonyString("model m; A=10; B=0; J0: A->B; kdeg*A; kdeg=0.3; end")
    return antimony.getSBMLString(antimony.getMainModuleName())


# the agent's reply: a sigma it names but does not estimate, which the merge
# cannot render (a fixed sigma is a number or comes from the data)
REPLY = {
    "observables": [
        {
            "observable_id": "obs_b",
            "maps_to_label": "b",
            "formula": "B",
            "transformation": "lin",
            "noise": {
                "distribution": "normal",
                "formula": "sigma_fixed_b",
                "estimate_sigma": False,
            },
            "scaling": {"mode": "none"},
            "rationale": "-",
        }
    ]
}


def _long_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "observable_label": "b",
                "condition_label": "c0",
                "condition_key": "c0",
                "time": t,
                "value": 10.0 * (1.0 - 0.74 ** (t / 1.0)),
            }
            for t in (0.0, 1.0, 2.0, 4.0, 8.0)
        ]
    )


def _record(path: Path) -> Node:
    """A fresh record for one scenario."""
    root = record_at(path)
    root.store.create()
    return root


def _param_ids(df) -> list[str]:
    """The parameterId values of a PEtab parameter table, index or column."""
    if df is None:
        return []
    if "parameterId" in df.columns:
        return sorted(df["parameterId"])
    return sorted(df.index)


def _stage(root: Node, ctx=None, stale_tables: bool = False):
    """A run at S3 whose observation block is refused and whose budget is spent.

    `stale_tables`: an earlier merge of this round wrote tables, which the
    refused merge leaves in the record."""
    ctx = ctx or Ctx(root)
    sbml = _sbml()
    (ctx.model / "parameters").put(
        [{"id": "kdeg", "nominal_value": 0.3, "lb": 1e-3, "ub": 1e3, "estimate": True}],
    )
    (ctx.agent_calls.child(ROLE) / "reply").put(REPLY)
    obs, noise, scaling = S3.split_observation_reply(REPLY)
    assembly = {
        "observables": obs,
        "noise": noise,
        "scaling": scaling,
        "conditions": [
            {
                "condition_id": "c0",
                "maps_to_label": "c0",
                "overrides": {},
                "preequilibration": False,
            }
        ],
    }
    if stale_tables:
        from octomod.orchestration.interaction import battery_feedback

        earlier, _ = battery_feedback.apply_fallback("additive-noise", assembly, SPEC)
        with contextlib.redirect_stdout(io.StringIO()):
            gone = S3._merge_or_refusal(
                ctx,
                S3._write_assembly(ctx, earlier),
                sbml,
                _long_df(),
                ctx.work / "petab",
            )
        assert gone is None, f"the earlier merge was refused: {gone}"
    assembly = S3._write_assembly(ctx, assembly)
    (ctx.round / "shared_assembly").put(assembly)
    history = AttemptHistory(dossier_of(ctx, ROLE))
    for i in range(BUDGET):
        history.add([f"assembly_merge_noise: draft {i + 1} still names a fixed id"], {})
    with contextlib.redirect_stdout(io.StringIO()):
        refusal = S3._merge_or_refusal(
            ctx, assembly, sbml, _long_df(), ctx.work / "petab"
        )
    return ctx, sbml, refusal


@contextlib.contextmanager
def _file_gate(root: Node):
    """The gate module in file mode for this run, put back as found after."""
    saved = (
        dict(humangate._FILE_MODE),
        dict(humangate._QUESTIONS),
        dict(humangate._POLICY),
    )
    humangate.configure_policy(None)
    humangate.configure_questions(root)
    try:
        yield
    finally:
        humangate._FILE_MODE.clear()
        humangate._FILE_MODE.update(saved[0])
        humangate._QUESTIONS.clear()
        humangate._QUESTIONS.update(saved[1])
        humangate._POLICY.clear()
        humangate._POLICY.update(saved[2])


def _battery(ctx: Ctx, sbml: str, refusal):
    """The S3 battery loop as the module runs it: (outcome, printed).

    The outcome is the returned (tables, results), or the exception it raised.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            out = S3._battery_with_feedback(
                ctx,
                ctx.work / "petab",
                sbml,
                _long_df(),
                {},
                supplied=False,
                reused_shared=False,
                refusal=refusal,
            )
    except Exception as e:  # noqa: BLE001 — the outcome under test
        return e, buf.getvalue()
    return out, buf.getvalue()


def _rows(ctx: Ctx, event: str) -> list[dict]:
    return [e for e in ledger_rows(ctx.root) if e.get("event") == event]


def _dossier(ctx: Ctx, role: str = ROLE) -> tuple[int, int]:
    h = AttemptHistory(dossier_of(ctx, role))
    return len(h), h.grants_total


def test_the_refusal_is_staged(ctx: Ctx, refusal) -> None:
    check_detail_on_fail(
        "the merge refuses the unestimated sigma as a failing T0 check",
        isinstance(refusal, GateResult)
        and refusal.gate_id == "assembly_merge_noise"
        and not refusal.passed
        and "sigma_fixed_b" in str(refusal.detail),
        str(refusal),
    )


def test_the_gate_pauses_and_offers_both_forms(ctx: Ctx, sbml: str, refusal) -> None:
    humangate.configure_file_mode(ctx.root, None)
    out, _printed = _battery(ctx, sbml, refusal)
    payload = out.payload if isinstance(out, humangate.GatePending) else {}
    forms = " | ".join(payload.get("note_forms") or [])
    check_detail_on_fail(
        "with no answer stored, the failure-point gate pauses at S3",
        isinstance(out, humangate.GatePending) and payload.get("module") == GATE,
        repr(out)[:200],
    )
    check_detail_on_fail(
        "its card offers `redraft:`, `fallback: <name>` and the declared fallbacks",
        "redraft:" in forms
        and "fallback: <name>" in forms
        and any("additive-noise" in str(ln) for ln in payload.get("lines") or []),
        forms[:240],
    )


def test_fallback_is_applied_signed_and_ledgered(ctx: Ctx, sbml: str, refusal):
    humangate.configure_file_mode(ctx.root, True, "fallback: additive-noise")
    out, printed = _battery(ctx, sbml, refusal)
    check_detail_on_fail(
        "the battery re-runs on the rewritten block and passes",
        isinstance(out, tuple) and len(out) == 2,
        f"{out!r}"[:240] + " · " + printed[-240:],
    )
    beside = (ctx.agent_calls.child(ROLE) / "fallback_applied").get(None) or {}
    signed = "human (via the front end)"
    check_detail_on_fail(
        "the fallback is written beside the reply: its name, role, signature, "
        "and the block it replaced",
        beside.get("fallback") == "additive-noise"
        and beside.get("role") == ROLE
        and beside.get("signed") == signed
        and (beside.get("replaced") or {}).get("noise", [{}])[0].get("formula")
        == "sigma_fixed_b",
        str(beside)[:240],
    )
    rows = _rows(ctx, "assembly_fallback")
    row = rows[0] if len(rows) == 1 else {}
    check_detail_on_fail(
        "one `assembly_fallback` ledger row, at S3, signed by the human",
        len(rows) == 1
        and row.get("module") == "assembly"
        and row.get("role") == ROLE
        and row.get("fallback") == "additive-noise"
        and row.get("signed") == signed
        and str(row.get("written_beside", "")).endswith(f"{ROLE}/fallback_applied"),
        str(rows)[:240],
    )
    asm = (ctx.work / "assembly").get(None) or {}
    noise = (asm.get("noise") or [{}])[0]
    par_ids = _param_ids((ctx.work / "petab" / "parameters").table(None))
    check_detail_on_fail(
        "the assembly carries the rewritten, estimated sigma and the problem "
        "renders it",
        noise.get("formula") == "sigma_obs_b"
        and noise.get("estimate_sigma") is True
        and "sigma_obs_b" in par_ids,
        f"{noise} · {par_ids}",
    )
    check_detail_on_fail(
        "the agent's reply in the record is untouched",
        (ctx.agent_calls.child(ROLE) / "reply").get(None) == REPLY,
    )
    check_detail_on_fail(
        "the fallback bought no attempt: the dossier is as it was",
        _dossier(ctx) == (BUDGET, 0),
        str(_dossier(ctx)),
    )


def test_redraft_goes_back_to_the_role(ctx: Ctx, sbml: str, refusal) -> None:
    humangate.configure_file_mode(ctx.root, True, f"redraft: {WORDS}")
    out, _printed = _battery(ctx, sbml, refusal)
    check_detail_on_fail(
        "`redraft:` raises RedraftRequested for observation with the words",
        isinstance(out, human_redraft.RedraftRequested)
        and out.role == ROLE
        and out.text == WORDS,
        repr(out)[:200],
    )
    fb = ctx.cache.get("_human_feedback") or {}
    check_detail_on_fail(
        "the words are held for the re-assembly, marked as a human's",
        fb == human_redraft.context_for(WORDS, ROLE) and WORDS in json.dumps(fb),
        str(fb)[:200],
    )
    check_detail_on_fail(
        "the superseded assembly files are removed, so nothing reads them back",
        not (ctx.work / "assembly").exists()
        and not (ctx.round / "shared_assembly").exists(),
    )
    notes = [e for e in _rows(ctx, "note") if e.get("human_redraft")]
    gates = [e for e in _rows(ctx, "human_gate") if e.get("module") == GATE]
    check_detail_on_fail(
        "the request is ledgered as the human's, at S3, naming the role",
        len(notes) == 1
        and notes[0].get("module") == "assembly"
        and notes[0].get("role") == ROLE
        and notes[0].get("note") == f"human asked {ROLE} to redraft: {WORDS}",
        str(notes)[:240],
    )
    check_detail_on_fail(
        "the answer that sent it is ledgered with the note, from the front end",
        len(gates) == 1
        and gates[0].get("mode") == "file"
        and gates[0].get("note") == f"redraft: {WORDS}",
        str(gates)[:240],
    )
    check_detail_on_fail(
        "the redraft spends no attempt and applies no fallback",
        _dossier(ctx) == (BUDGET, 0) and not _rows(ctx, "assembly_fallback"),
        str(_dossier(ctx)),
    )


def test_an_unattributable_redraft_goes_to_the_assembly(ctx: Ctx, sbml: str) -> None:
    lint = GateResult("assembly_petablint", "T0", False, detail="petablint: 1 error")
    humangate.configure_file_mode(ctx.root, True, f"redraft: {WORDS}")
    out, _printed = _battery(ctx, sbml, lint)
    check_detail_on_fail(
        "a check no agent authored sends the words to the assembly agents",
        isinstance(out, human_redraft.RedraftRequested)
        and out.role == "the assembly agents"
        and out.text == WORDS,
        repr(out)[:200],
    )


# the agent's repair: the sigma it named is now estimated
REPAIRED = {
    "observables": [
        {
            **REPLY["observables"][0],
            "noise": {
                "distribution": "normal",
                "formula": "sigma_obs_b",
                "estimate_sigma": True,
            },
        }
    ]
}


def test_a_grant_goes_back_to_the_agent(root: Node, *, stale_tables: bool) -> None:
    where = "an earlier merge's tables" if stale_tables else "no tables"
    ctx = AnsweringCtx(root, REPAIRED)
    ctx, sbml, refusal = _stage(root, ctx, stale_tables=stale_tables)
    with _file_gate(ctx.root):
        humangate.configure_file_mode(ctx.root, True, "n=1")
        out, printed = _battery(ctx, sbml, refusal)
    check_detail_on_fail(
        f"({where}) `n=1` after a refused merge re-asks observation once",
        ctx.calls == [ROLE],
        f"calls {ctx.calls}; outcome {out!r}"[:300] + " · " + printed[-200:],
    )
    check_detail_on_fail(
        f"({where}) the battery then passes on the rewritten block",
        isinstance(out, tuple) and len(out) == 2,
        f"{out!r}"[:240] + " · " + printed[-240:],
    )
    asm = (ctx.work / "assembly").get(None) or {}
    noise = (asm.get("noise") or [{}])[0]
    check_detail_on_fail(
        f"({where}) the problem carries the agent's repair, not the tables left "
        f"before the refusal",
        noise.get("formula") == "sigma_obs_b"
        and noise.get("estimate_sigma") is True
        and not _rows(ctx, "assembly_fallback"),
        str(noise),
    )
    attributed = [
        e.get("gate_id")
        for e in _rows(ctx, "redraft_attributed")
        if e.get("role") == ROLE
    ]
    check_detail_on_fail(
        f"({where}) the grant is in the dossier and the re-ask names the refusal",
        _dossier(ctx) == (BUDGET + 1, 1) and attributed == ["assembly_merge_noise"],
        f"{_dossier(ctx)} · {attributed}",
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        ctx, sbml, refusal = _stage(_record(base / "fallback"))
        test_the_refusal_is_staged(ctx, refusal)
        with _file_gate(ctx.root):
            test_the_gate_pauses_and_offers_both_forms(ctx, sbml, refusal)
            test_fallback_is_applied_signed_and_ledgered(ctx, sbml, refusal)
        ctx, sbml, refusal = _stage(_record(base / "redraft"))
        with _file_gate(ctx.root):
            test_redraft_goes_back_to_the_role(ctx, sbml, refusal)
        ctx, sbml, _refusal = _stage(_record(base / "unattributed"))
        with _file_gate(ctx.root):
            test_an_unattributable_redraft_goes_to_the_assembly(ctx, sbml)
        test_a_grant_goes_back_to_the_agent(_record(base / "grant"), stale_tables=False)
        test_a_grant_goes_back_to_the_agent(
            _record(base / "grant_stale"), stale_tables=True
        )
    return finish(
        "\nS3 FAILURE ANSWERS",
        "\nS3 FAILURE ANSWERS UNIT OK — at the blocked S3 battery a `fallback:` is "
        "applied, signed and ledgered, a `redraft:` goes back to its role "
        "uncharged, with the superseded files removed, and a grant re-asks the "
        "role that must rewrite",
    )


if __name__ == "__main__":
    sys.exit(main())
