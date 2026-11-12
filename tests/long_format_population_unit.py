"""Long-format mappings, parameter-valued condition overrides and related engine checks.

  1. a long-format mapping reads the observable from a column and a per-row sigma,
     and a text cell where a number belongs is refused by name;
  2. parameter-valued condition overrides resolve, in gate simulations too;
  3. the T0 orphan check counts condition-assigned parameter copies as used, and
     the sensitivity screen leaves out a sigma the noise formula names directly;
  4. the resolved model id comes from the per-model usage breakdown;
  5. a file-gate answer is bound to the module that paused;
  6. a re-entry reopens an ended run;
  7. a cost-boundary redraft invalidates each candidate's assembly and s3 marker.

    uv run python tests/long_format_population_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _record import ledger_rows, record_at, rnd, temp_record  # noqa: E402

from octomod.gates.petab_gates import PetabTables  # noqa: E402
from octomod.orchestration.run_context import ModuleFailure  # noqa: E402
from octomod.result import node as tree  # noqa: E402
from octomod.spec import WorkflowSpec  # noqa: E402
from octomod.workflow_modules.assembly.engine import _override_value  # noqa: E402
from octomod.workflow_modules.data.engine import _execute_mappings  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SPEC = WorkflowSpec.load(REPO / "workflows" / "default.yaml")


class _Ref:
    def __init__(self, name):
        self.locator = f"data/{name}"


class _Table:
    def __init__(self, df, name):
        self.df = df
        self.provenance = {"file": name}


class _Conn:
    def __init__(self, frames):
        self.frames = frames

    def fetch(self, ref):
        name = ref.locator.split("/")[-1]
        return _Table(self.frames[name], name)


def _long_frame():
    return pd.DataFrame(
        {
            "stimulus": ["A", "A", "A", "A", "Ref", "Ref"],
            "population": ["B", "B", "B", "B", "B", "B"],
            "time_min": [0, 0, 0, 5, 0, 5],
            "readout": ["pStat1", "pStat3", "pStat5", "pStat1", "pStat1", "pStat1"],
            "median": [1.0, 0.3, 0.2, 2.0, 1.0, 1.1],
            "sigma": [0.05, 0.03, 0.03, 0.05, 0.05, 0.05],
        }
    )


def _mapping(**over):
    m = {
        "file": "d.csv",
        "observable_label": None,
        "observable_column": "readout",
        "time_column": "time_min",
        "value_column": "median",
        "condition_columns": ["stimulus", "population"],
        "condition_label_template": "stimulus={stimulus}, population={population}",
        "replicate_column": None,
        "error_column": "sigma",
        "units": "arbitrary",
        "error_type": "column",
    }
    m.update(over)
    return m


def test_long_format_observable_column_and_error_column():
    long_df, prov = _execute_mappings(
        {"mappings": [_mapping()]}, _Conn({"d.csv": _long_frame()}), [_Ref("d.csv")]
    )
    assert len(long_df) == 6
    assert set(long_df["observable_label"]) == {"pStat1", "pStat3", "pStat5"}
    # the observable is NOT a condition: two conditions (A, Ref) x one population
    assert long_df["condition_label"].nunique() == 2
    assert not long_df.duplicated(
        subset=["observable_label", "condition_label", "time", "replicate"]
    ).any()
    assert "sigma" in long_df.columns
    assert long_df["sigma"].tolist() == [0.05, 0.03, 0.03, 0.05, 0.05, 0.05]
    print("  long format: 6 rows, 3 observables, 2 conditions, per-row sigma carried")


def test_wide_mappings_unchanged():
    wide = pd.DataFrame({"dose": [1, 1], "t": [0, 5], "y": [0.1, 0.9]})
    m = {
        "file": "w.csv",
        "observable_label": "y_obs",
        "time_column": "t",
        "value_column": "y",
        "condition_columns": ["dose"],
        "condition_label_template": "dose={dose}",
        "replicate_column": None,
        "units": "au",
        "error_type": "none",
    }
    long_df, _ = _execute_mappings(
        {"mappings": [m]}, _Conn({"w.csv": wide}), [_Ref("w.csv")]
    )
    assert list(long_df["observable_label"]) == ["y_obs", "y_obs"]
    assert "sigma" not in long_df.columns
    print("  wide mapping without the new keys: unchanged")


def test_refusals():
    # neither a label nor a column
    try:
        _execute_mappings(
            {"mappings": [_mapping(observable_column=None)]},
            _Conn({"d.csv": _long_frame()}),
            [_Ref("d.csv")],
        )
        raise AssertionError("mapping without label or column was accepted")
    except ModuleFailure as e:
        assert "observable_label" in str(e) and "observable_column" in str(e)
    # a non-positive sigma
    bad = _long_frame()
    bad.loc[2, "sigma"] = 0.0
    try:
        _execute_mappings(
            {"mappings": [_mapping()]}, _Conn({"d.csv": bad}), [_Ref("d.csv")]
        )
        raise AssertionError("sigma = 0 was accepted")
    except ModuleFailure as e:
        assert "finite positive" in str(e)
    print("  refusals: missing label/column, non-positive sigma — both named")


def _csv_mapping(name: str) -> dict:
    return {
        "file": name,
        "observable_label": "y_obs",
        "time_column": "t",
        "value_column": "y",
        "condition_columns": ["dose"],
        "condition_label_template": "dose={dose}",
        "replicate_column": None,
        "units": "au",
        "error_type": "none",
    }


def _from_csv(name: str, text: str):
    """`_execute_mappings` on a csv read the way the local-files connector reads it."""
    import io

    df = pd.read_csv(io.StringIO(text))
    return _execute_mappings(
        {"mappings": [_csv_mapping(name)]}, _Conn({name: df}), [_Ref(name)]
    )


def test_a_cell_that_is_not_a_number_is_refused_by_name():
    """Text in a time or value cell is refused by file, column, row and cell,
    with the remedies — not a bare ValueError that crashes every resume."""
    from octomod.workflow_modules.data.engine import make_data_gates

    for what, text, column, rows, cell in (
        ("value", "dose,t,y\n1,0,0.1\n1,5,<LOD\n1,10,0.9\n", "y", "[3]", "'<LOD'"),
        ("time", "dose,t,y\n1,0h,0.1\n1,5h,0.9\n", "t", "[2, 3]", "'0h'"),
    ):
        try:
            _from_csv("x.csv", text)
        except ModuleFailure as e:
            msg = str(e)
        except ValueError as e:
            raise AssertionError(
                f"text in a {what} cell crashed with a bare ValueError: {e}"
            ) from e
        else:
            raise AssertionError(f"text in a {what} cell was accepted")
        for needed in ("x.csv", repr(column), rows, "header as row 1", cell):
            assert needed in msg, f"{what}: the refusal does not name {needed}: {msg}"
        for remedy in ("below_detection", "map another column", "clean the file"):
            assert remedy in msg, f"{what}: the refusal omits {remedy!r}: {msg}"
    # a blank cell is still a missing value, which the rows check reports
    long_df, _ = _from_csv("b.csv", "dose,t,y\n1,0,0.1\n1,5,\n")
    assert long_df["value"].isna().tolist() == [False, True], long_df
    rows_gate = make_data_gates(long_df, {}, None)[0]()
    assert not rows_gate.passed and "missing measurement values" in rows_gate.detail
    print(
        "  text cells: refused by file, column, row and cell; a blank is still missing"
    )


def test_override_value():
    assert _override_value(30) == 30.0
    assert _override_value("30") == 30.0
    assert _override_value(True) == 1.0
    assert _override_value("STAT1_tot_Bcell") == "STAT1_tot_Bcell"
    for bad in ("3x", "a-b", ""):
        try:
            _override_value(bad)
            raise AssertionError(f"{bad!r} accepted")
        except ModuleFailure:
            pass
    print("  override values: numbers stay numbers, ids stay ids, junk refused")


def test_condition_overrides_resolve_parameter_ids():
    class _Fake:
        conditions = pd.DataFrame(
            {
                "conditionId": ["c_B", "c_T"],
                "u_a": [30.0, 30.0],
                "STAT1_tot": ["STAT1_tot_B", "STAT1_tot_T"],
            }
        )
        parameters = pd.DataFrame(
            {
                "parameterId": ["STAT1_tot_B", "STAT1_tot_T", "kc1"],
                "nominalValue": [1.5, 0.7, 0.2],
            }
        )

    fake = _Fake()
    nominal = PetabTables.condition_overrides(fake, "c_B")
    assert nominal == {"u_a": 30.0, "STAT1_tot": 1.5}
    fitted = PetabTables.condition_overrides(fake, "c_T", values={"STAT1_tot_T": 0.42})
    assert fitted["STAT1_tot"] == 0.42 and fitted["u_a"] == 30.0
    fake.parameters = fake.parameters.iloc[:0]
    try:
        PetabTables.condition_overrides(fake, "c_B")
        raise AssertionError("unknown id resolved")
    except ValueError as e:
        assert "STAT1_tot_B" in str(e)
    print(
        "  parameter-valued overrides: nominal when no vector, fitted when given, unknown id refused"
    )


def test_per_row_sigma_fill_pattern_is_writable():
    """The sigma fill writes to a copy, since `.to_numpy()` can be a read-only view."""
    meas = pd.DataFrame(
        {"observableId": ["a", "b", "a"], "noiseParameters": [None, "sigma_b", None]}
    )
    long = pd.DataFrame({"sigma": [0.05, 0.02, 0.07]})
    mask = meas["observableId"].astype(str).isin({"a"}).to_numpy()
    sig = long["sigma"].to_numpy()
    vals = meas["noiseParameters"].astype(object).to_numpy(copy=True)
    vals[mask] = [f"{float(s):g}" for s in sig[mask]]
    meas["noiseParameters"] = vals
    assert meas["noiseParameters"].tolist() == ["0.05", "sigma_b", "0.07"]
    print("  per-row sigma fill: writable copy, rows aligned")


def _toy_tables(extra_estimated=()):
    """One reaction; each condition gives `k` its own copy, like a population factor."""

    from octomod.gates.build_gates import antimony_to_sbml

    sbml, msg = antimony_to_sbml("model m; A=10; B=0; J0: A->B; k*A; k=0.3; end")
    assert sbml, msg
    par_ids = ["k_B", "k_M", *extra_estimated]
    return PetabTables(
        observables=pd.DataFrame(
            [
                {
                    "observableId": "o",
                    "observableFormula": "B",
                    "observableTransformation": "lin",
                    "noiseFormula": "noiseParameter1_o",
                    "noiseDistribution": "normal",
                }
            ]
        ),
        conditions=pd.DataFrame(
            [{"conditionId": "c_B", "k": "k_B"}, {"conditionId": "c_M", "k": "k_M"}]
        ),
        measurements=pd.DataFrame(
            [
                {
                    "observableId": "o",
                    "simulationConditionId": c,
                    "time": t,
                    "measurement": 1.0,
                    "noiseParameters": "0.1",
                }
                for c in ("c_B", "c_M")
                for t in (1.0, 2.0)
            ]
        ),
        parameters=pd.DataFrame(
            [
                {
                    "parameterId": pid,
                    "parameterScale": "log10",
                    "lowerBound": 1e-3,
                    "upperBound": 1e3,
                    "nominalValue": 0.3,
                    "estimate": 1,
                }
                for pid in par_ids
            ]
        ),
        sbml=sbml,
    )


def _run_gate(tables, gate_id):
    from octomod.gates.petab_gates import make_petab_gates

    # the battery is built from the in-memory tables, no directory
    for g in make_petab_gates(tables, SPEC):
        if getattr(g, "gate_id", "") == gate_id:
            return g()
    raise AssertionError(f"{gate_id} not in the battery")


def test_parameters_sane_counts_condition_overrides():
    """A copy only a condition names is used, not an orphan; an unused one is named."""
    r = _run_gate(_toy_tables(), "assembly_parameters_sane")
    assert r.passed, r.detail
    r = _run_gate(_toy_tables(extra_estimated=("zz",)), "assembly_parameters_sane")
    assert not r.passed and "zz" in str(r.detail), r.detail
    assert "k_B" not in str(r.detail) and "k_M" not in str(r.detail), r.detail


def test_a_sigma_written_into_the_noise_formula_is_not_screened():
    """A sigma the noise formula names directly is a noise parameter, not uncovered."""
    from octomod.gates.build_gates import antimony_to_sbml

    toy = _toy_tables(extra_estimated=("sigma_x",))
    sbml, msg = antimony_to_sbml(
        "model m; A=10; B=0; J0: A->B; k*A; k=0.3; obs_x := B; end"
    )
    assert sbml, msg
    obs = toy.observables.copy()
    obs["noiseFormula"] = "sigma_x * obs_x"
    meas = toy.measurements.copy()
    meas["noiseParameters"] = float("nan")  # the column is there, every cell empty
    tables = PetabTables(
        observables=obs,
        conditions=toy.conditions,
        measurements=meas,
        parameters=toy.parameters,
        sbml=sbml,
    )
    r = _run_gate(tables, "assembly_sensitivity_coverage")
    assert isinstance(r.value, dict), f"the screen did not run: {r.detail}"
    uncovered = r.value["uncovered"]
    assert (
        "sigma_x" not in uncovered
    ), f"a sigma named in noiseFormula was screened as uncovered: {r.detail}"
    assert "k_B" not in uncovered and "k_M" not in uncovered, r.detail
    print("  sens screen  a sigma written into noiseFormula is not called uncovered")


def test_resolved_model_picks_the_model_that_did_the_work():
    """The resolved id is the model with the output tokens, not the first key."""
    from octomod.agents import resolved_model

    meta = {
        "modelUsage": {
            "claude-haiku-4-5-20251001": {
                "inputTokens": 900,
                "outputTokens": 40,
                "costUSD": 0.001,
            },
            "claude-opus-5": {
                "inputTokens": 2,
                "outputTokens": 16525,
                "cacheCreationInputTokens": 42128,
                "costUSD": 0.8656,
            },
        }
    }
    mid, used = resolved_model(meta)
    assert mid == "claude-opus-5", mid
    assert used["claude-opus-5"]["input_tokens"] == 42130, used
    assert used["claude-haiku-4-5-20251001"]["output_tokens"] == 40, used
    assert resolved_model({"model": "x"}) == ("x", {})
    assert resolved_model({}) == (None, {})


def test_file_gate_answer_is_bound_to_the_pausing_module():
    """A stored --gate-answer is consumed only by the gate that paused the run."""
    import contextlib
    import io

    from octomod.orchestration.interaction import humangate
    from octomod.orchestration.ledger import Ledger

    saved = dict(humangate._FILE_MODE)
    try:
        with temp_record() as run_dir:  # the run is a record
            humangate.pending_path(run_dir).put(
                {"module": "assembly_redraft_budget", "question": "?"}
            )
            humangate.configure_file_mode(run_dir, True, "go ahead")
            assert humangate._FILE_MODE["pending_module"] == "assembly_redraft_budget"
            ledger = Ledger(run_dir)
            # a different gate reached first: pause, do not approve
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    humangate.ask(
                        "compile?", [], ledger=ledger, module="assembly_cost_boundary"
                    )
                except humangate.GatePending as gp:
                    payload = (
                        gp.payload
                        if hasattr(gp, "payload")
                        else humangate.pending_path(run_dir).get()
                    )
                else:
                    raise AssertionError(
                        "the cost gate consumed an answer meant for another gate"
                    )
            assert payload["module"] == "assembly_cost_boundary", payload
            rows = ledger_rows(run_dir)
            assert any(
                r.get("gate_answer_discarded") == "assembly_redraft_budget"
                for r in rows
            ), rows
            assert not any(r.get("event") == "human_gate" for r in rows), rows
            # the SAME gate reached: the answer is consumed
            humangate.pending_path(run_dir).put(
                {"module": "assembly_redraft_budget", "question": "?"}
            )
            humangate.configure_file_mode(run_dir, True, "go ahead")
            with contextlib.redirect_stdout(io.StringIO()):
                ok, note = humangate.ask(
                    "again?", [], ledger=ledger, module="assembly_redraft_budget"
                )
            assert ok and note == "go ahead", (ok, note)
    finally:
        humangate._FILE_MODE.clear()
        humangate._FILE_MODE.update(saved)


def test_reentry_reopens_an_ended_run():
    """`run_end` closes a run only until a later `run_start` (a re-entry) follows it."""
    from octomod.orchestration.run_guard import ended_outcome

    ledger = _ledger_record

    stopped = {"event": "run_end", "outcome": "stopped"}
    assert ended_outcome(ledger([{"event": "run_start"}, stopped])) == "stopped"
    assert ended_outcome(ledger([{"event": "run_start"}])) is None
    reentered = ledger(
        [
            {"event": "run_start"},
            stopped,
            {"event": "run_start"},
            stopped,
            {"event": "run_start"},
            {"event": "entry", "module": "entry_assembly"},
            {"event": "gate_pending", "module": "assembly_redraft_budget"},
        ]
    )
    assert ended_outcome(reentered) is None
    finished_after_reentry = ledger(
        [
            {"event": "run_start"},
            stopped,
            {"event": "run_start"},
            {"event": "run_end", "outcome": "finished"},
        ]
    )
    assert ended_outcome(finished_after_reentry) == "finished"
    assert ended_outcome(_fresh_root(create=False)) is None


def _fresh_root(create: bool = True):
    """A record in a new temporary directory, left for the system to clean so
    the nodes stay readable after this returns; `create=False` leaves the file
    unwritten."""
    import tempfile

    root = record_at(Path(tempfile.mkdtemp()) / "run")
    if create:
        root.store.create()
    return root


def _ledger_record(rows):
    """A record whose ledger holds `rows` (was a run dir with ledger.jsonl)."""
    root = _fresh_root()
    for r in rows:
        root.store.append_ledger(r)
    return root


def test_cost_boundary_redraft_invalidates_markers():
    """A cost-boundary redraft clears the shared draft and each unit of work's s3
    state: every candidate's on a candidate set, the round's `_single` for the
    single model."""
    from octomod.workflow_modules.cost_probe.compile_gate import assembly_invalidations

    # record keys relative to the round (nothing is read or written)
    rd = rnd(record_at(Path("/r/run")), 0)

    def rel(n):
        return n.key[len(rd.key) + 1 :]

    got = {rel(x) for x in assembly_invalidations(rd, ["M1", "M2"])}
    assert got == {
        "shared_assembly",
        "candidates/M1/assembly",
        "candidates/M1/markers/s3",
        "candidates/M1/gates/assembly_verification",
        "candidates/M2/assembly",
        "candidates/M2/markers/s3",
        "candidates/M2/gates/assembly_verification",
    }, got
    single = {rel(x) for x in assembly_invalidations(rd, [None])}
    assert single == {
        "shared_assembly",
        "candidates/_single/assembly",
        "status/markers/s3",
        "gates/assembly_verification",
    }, single


class _MiniCtx:
    """A round on a record (`root` is the run record's root node)."""

    def __init__(self, root):
        from octomod.orchestration.ledger import Ledger

        self.root = root
        self.store = root.store
        self.round_idx = 0
        self.candidate = None
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, self.round_idx)

    @property
    def work(self):
        return tree.work_node(self.round, self.candidate)

    @property
    def gates(self):
        return tree.gates_node(self.round, self.candidate)

    @property
    def agent_calls(self):
        return self.round / "agent_calls"


def test_malformed_model_space_is_dropped_not_fatal():
    """A model_space object is read via its `axes`; a non-object entry is dropped."""
    from octomod.workflow_modules.model.model_space import (
        dropped_axes,
        record_assembly_axes,
    )

    with temp_record() as root:
        ctx = _MiniCtx(root)
        replies = {
            "condition": {
                "model_space": {
                    "axes": [{"axis_id": "kdp_split", "alternatives": ["a", "b"]}]
                }
            },
            "observation": {"model_space": ["junk", 3]},
        }
        out = record_assembly_axes(ctx, replies, "model m; A=1; end", [])
        assert out == [], out
        drops = dropped_axes(ctx, module="assembly")
        ids = sorted(d["id"] for d in drops)
        assert ids == ["observation_axis_0", "observation_axis_1"], ids
        assert all("malformed" in d["reason"] for d in drops), drops
        rows = ledger_rows(root)
        assert any(
            "model_space given as an object" in str(r.get("note")) for r in rows
        ), rows


def test_crash_is_not_an_ending():
    """`run_end outcome=crashed` does not end the run; it resumes like a killed one."""
    from octomod.orchestration.run_guard import ended_outcome

    ledger = _ledger_record

    crashed = {"event": "run_end", "outcome": "crashed", "reason": "ValueError: x"}
    assert ended_outcome(ledger([{"event": "run_start"}, crashed])) is None
    assert (
        ended_outcome(
            ledger(
                [
                    {"event": "run_start"},
                    {"event": "run_end", "outcome": "stopped"},
                    {"event": "run_start"},
                    crashed,
                ]
            )
        )
        is None
    )
    assert (
        ended_outcome(
            ledger(
                [
                    {"event": "run_start"},
                    crashed,
                    {"event": "run_start"},
                    {"event": "run_end", "outcome": "finished"},
                ]
            )
        )
        == "finished"
    )


def test_paid_replies_are_reused_when_they_postdate_the_redraft():
    """Both replies are reused when both calls postdate the last redraft, else None."""
    from octomod.workflow_modules.assembly.engine import _paid_replies_to_reuse

    def setup(rows, files=("observation", "condition")):
        ctx = _MiniCtx(_ledger_record(rows))
        for role in files:
            (ctx.agent_calls.child(role) / "reply").put({"from": role})
        return ctx

    redraft = {
        "ts": "2026-09-22T22:04:55",
        "round": 0,
        "event": "note",
        "human_redraft": True,
        "role": "the assembly agents",
    }
    obs = {
        "ts": "2026-09-22T22:06:25",
        "round": 0,
        "event": "agent_call",
        "role": "observation",
    }
    cond = {
        "ts": "2026-09-22T22:12:49",
        "round": 0,
        "event": "agent_call",
        "role": "condition",
    }
    got = _paid_replies_to_reuse(setup([redraft, obs, cond]))
    assert got == ({"from": "observation"}, {"from": "condition"}), got
    later = dict(redraft, ts="2026-09-22T22:30:00")
    assert _paid_replies_to_reuse(setup([redraft, obs, cond, later])) is None
    assert (
        _paid_replies_to_reuse(setup([redraft, obs, cond], files=("observation",)))
        is None
    )
    assert _paid_replies_to_reuse(setup([obs])) is None  # one call only
    assert _paid_replies_to_reuse(setup([obs, cond])) == (
        {"from": "observation"},
        {"from": "condition"},
    )


def test_ln_is_math_not_a_symbol():
    """`ln` is the natural log, for the tokenizer and the gate evaluator alike."""
    from octomod.workflow_modules.assembly.assembly_edit import symbols
    from octomod.workflow_modules.model.simwrap import eval_formula

    assert symbols("ln(pX/5 + sqrt(1 + pX*pX/25))") == {"pX"}
    assert abs(float(eval_formula("ln(exp(2.0))", {})) - 2.0) < 1e-12
    assert (
        abs(float(eval_formula("ln(pX/5 + sqrt(1 + pX*pX/25))", {"pX": 0.0}))) < 1e-12
    )
    # the AMICI-safe rewrite accepts `ln` (renamed to `log`, the rest byte-identical)
    from octomod.workflow_modules.assembly.assembly_edit import amici_safe_formula

    f = "ln(pSTAT1/5 + sqrt(1 + pSTAT1*pSTAT1/25)) + observableParameter1_obs_pStat1"
    assert amici_safe_formula(f) == f.replace("ln(", "log(", 1), amici_safe_formula(f)
    assert (
        amici_safe_formula("kln_A*x + ln (y)") == "kln_A*x + log (y)"
    )  # `\b`: only the call


def test_entry_honours_accepted_convergence_checks():
    """A human-accepted failing check is honoured for that candidate and check only."""
    from octomod.gates import GateResult
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.round_status import _honoured_by_accept

    class Ctx:
        def __init__(self, root, candidate):
            self.ledger = Ledger(root)
            self.candidate = candidate
            self.round_idx = 0

    with temp_record() as root:
        ctx = Ctx(root, "M2")
        ctx.ledger.append(
            "note",
            module="estimation_convergence",
            round_idx=0,
            note="convergence accepted by human for candidate M2: bounds",
            convergence="accepted-by-human",
            failed_checks=["estimation_gradient_norm"],
            failed_measured=[
                {"gate_id": "estimation_gradient_norm", "value": 110, "threshold": 10}
            ],
            accept_reason="bounds",
            candidate="M2",
        )
        grad = GateResult(
            "estimation_gradient_norm", "T2", False, detail="gradient norm 110"
        )
        plateau = GateResult(
            "estimation_waterfall_plateau", "T2", False, detail="plateau 1/100"
        )
        got = _honoured_by_accept(ctx, [grad, plateau])
        assert got == [grad], got
        # another candidate's acceptance does not carry over
        ctx.candidate = "M3"
        assert _honoured_by_accept(ctx, [grad]) == []
        # no acceptance at all
        ctx2 = Ctx(_fresh_root(), "M2")
        assert _honoured_by_accept(ctx2, [grad]) == []
        assert _honoured_by_accept(ctx, []) == []


def test_reentered_evaluation_reasks_its_decisions():
    """A re-entered evaluation re-asks its decisions, but not the round's expansion."""
    from octomod.orchestration.round_status import _MODULE_CACHE_PATTERNS

    pats = _MODULE_CACHE_PATTERNS["evaluation"]
    assert (
        "decisions/evaluation_profile" in pats
        and "decisions/evaluation_verdict" in pats
    ), pats
    # the human's profile request outlives the re-entry; only the gate's
    # answer is asked again
    import fnmatch

    assert not any(
        fnmatch.fnmatch("decisions/evaluation_profile_request", x) for x in pats
    ), pats
    assert not any("expansion" in x for x in pats), pats


def test_a_declined_profiling_gate_is_recorded_where_the_run_goes_on():
    """A declined profiling gate is recorded only where the run continues past it."""
    from octomod.orchestration.interaction import humangate
    from octomod.orchestration.ledger import Ledger
    from octomod.orchestration.run_context import ModuleFailure
    from octomod.workflow_modules.estimation import problem as estimation
    from octomod.workflow_modules.evaluation.engine import _profiles_for

    class Spec:
        def get(self, key, default=None):
            # the projection gate asks only when profiles are not on request
            return False if key == "gates.profiles.on_request" else default

        def require(self, key):
            return 0  # a cap of 0 s: every projection is over it, so the gate asks

    class Ctx:
        def __init__(self, root):
            self.spec = Spec()
            self.ledger = Ledger(root)
            self.round_idx = 1
            self.intent = {}
            self.root = root
            self.candidate = None

        @property
        def round(self):
            return rnd(self.root, self.round_idx)

        @property
        def work(self):
            # no tables here: the profile-reuse check finds nothing
            return tree.work_node(self.round, self.candidate)

        @property
        def model(self):
            return tree.model_node(self.round, self.candidate)

        def marker(self, name):
            return tree.markers_node(self.round, None).child(name)  # absent: median 1 s

    asked = []

    def fake_ask_once(
        ctx, decision, question, lines, *, module, record_decline=True, **kw
    ):
        asked.append(record_decline)
        return False, "no"

    saved = (humangate.ask_once, estimation.make_engine)
    humangate.ask_once = fake_ask_once
    estimation.make_engine = lambda spec, median_s: type("E", (), {"n_procs": 1})()
    try:
        with temp_record() as root:
            core: dict = {}
            _profiles_for(
                Ctx(root),
                core,
                {"x_names": ["k"]},
                "mechanism_discrimination",
                1,
            )
            assert asked == [True], asked
            assert "declined at the profiling gate" in core.get(
                "profiles_skipped", ""
            ), core
            try:
                _profiles_for(
                    Ctx(root),
                    {},
                    {"x_names": ["k"]},
                    "parameter_values",
                    1,
                )
            except ModuleFailure:
                pass
            else:
                raise AssertionError(
                    "a declined gate on parameter_values must stop the run"
                )
            assert asked == [True, False], asked
    finally:
        humangate.ask_once, estimation.make_engine = saved


def test_a_redrafted_round_is_never_a_supplied_problem():
    """A redraft recorded for this round means its tables are not a supplied problem."""
    from octomod.workflow_modules.assembly.engine import _left_by_entry_adapter

    with temp_record() as root:
        ctx = _MiniCtx(root)
        ctx.round_idx = 2
        ctx.candidate = "base"
        petab = ctx.work / "petab"
        (petab / "problem_yaml").put_text("format_version: 1\n")
        assert _left_by_entry_adapter(ctx, petab)  # no redraft on record
        ctx.ledger.append(
            "note",
            module="assembly_cost_boundary",
            round_idx=0,
            note="redraft in round 0",
            human_redraft=True,
        )
        assert _left_by_entry_adapter(ctx, petab)  # another round's redraft
        ctx.ledger.append(
            "note",
            module="assembly_cost_boundary",
            round_idx=2,
            note="human asked the assembly agents to redraft",
            human_redraft=True,
        )
        assert not _left_by_entry_adapter(ctx, petab)


def test_rendered_preequilibration_is_named() -> None:
    """A rendered pre-equilibration is ledgered per merge and named once on the card."""
    from types import SimpleNamespace

    from octomod.gates.build_gates import antimony_to_sbml
    from octomod.orchestration.interaction import battery_feedback
    from octomod.orchestration.ledger import Ledger
    from octomod.workflow_modules.assembly.engine import (
        _record_rendered_preequilibration,
    )

    sbml, msg = antimony_to_sbml(
        "model m; species L = 0; species X = 1; J0: X -> ; k*L*X; k = 1; end"
    )
    assert sbml, msg

    def rendered():
        return [
            {
                "condition": "cond_a",
                "preequilibration_condition": "preeq_cond_a",
                "changed": {"L": [1.0, 0.0]},
                "own": ["L", "k_B"],
            }
        ]

    with temp_record() as root:
        ledger = Ledger(root)
        for cand in ("base", "other"):
            ctx = SimpleNamespace(
                ledger=ledger,
                round_idx=0,
                candidate=cand,
                root=root,
                round=rnd(root, 0),
                gates=tree.gates_node(rnd(root, 0), cand),
            )
            _record_rendered_preequilibration(ctx, rendered(), sbml)
        rows = [e for e in ledger.entries() if e.get("preequilibration_rendered")]
        rec = rows[0]["preequilibration_rendered"][0] if rows else {}
        assert len(rows) == 2 and rec.get("reinitialised") == ["L"], rows
        assert "own" not in rec and rec.get("changed") == {"L": [1.0, 0.0]}, rec
        lines = [
            ln for ln in battery_feedback.card_lines(ctx) if "pre-equilibration" in ln
        ]
        assert len(lines) == 1, lines
        assert (
            "cond_a from preeq_cond_a (L 1 -> 0), re-set at t=0: L" in lines[0]
        ), lines
        ctx.candidate = "none"
        _record_rendered_preequilibration(ctx, [], sbml)
        assert (
            len([e for e in ledger.entries() if e.get("preequilibration_rendered")])
            == 2
        ), "nothing rendered, nothing recorded"
    print("  preeq       a rendered pre-equilibration is ledgered, once on the card")


def main() -> int:
    print("long-format / per-row sigma / parameter-valued overrides — unit checks")
    test_rendered_preequilibration_is_named()
    test_long_format_observable_column_and_error_column()
    test_wide_mappings_unchanged()
    test_refusals()
    test_a_cell_that_is_not_a_number_is_refused_by_name()
    test_override_value()
    test_condition_overrides_resolve_parameter_ids()
    test_per_row_sigma_fill_pattern_is_writable()
    test_parameters_sane_counts_condition_overrides()
    test_a_sigma_written_into_the_noise_formula_is_not_screened()
    test_resolved_model_picks_the_model_that_did_the_work()
    test_file_gate_answer_is_bound_to_the_pausing_module()
    test_reentry_reopens_an_ended_run()
    test_cost_boundary_redraft_invalidates_markers()
    test_malformed_model_space_is_dropped_not_fatal()
    test_crash_is_not_an_ending()
    test_paid_replies_are_reused_when_they_postdate_the_redraft()
    test_ln_is_math_not_a_symbol()
    test_entry_honours_accepted_convergence_checks()
    test_reentered_evaluation_reasks_its_decisions()
    test_a_declined_profiling_gate_is_recorded_where_the_run_goes_on()
    test_a_redrafted_round_is_never_a_supplied_problem()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
