"""Gate framework.

A gate is a deterministic predicate over artifacts. It returns a GateResult;
it never mutates anything. A failed blocking gate stops the run — it does not
produce a warning and continue.

Tiers: T0 schema · T1 mathematical · T2 statistical (declared thresholds) ·
T2' held-out predictive · T3 judgment (verification agent, advisory by
construction) · T4 human (handled by humangate, not here).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class GateResult:
    gate_id: str
    tier: str  # T0 | T1 | T2 | T2prime | T3
    passed: bool
    blocking: bool = True
    value: object = None  # computed quantity
    threshold: object = None  # declared threshold it was compared against
    detail: str = ""
    advisory_findings: list = field(default_factory=list)
    # The solver settings the verdict was reached under: a stiff model can fail
    # at one tolerance and integrate at another. Stamped by `run_gate_set` for
    # every gate declared `integrates=True`, never at the call site.
    solver_settings: dict | None = None

    def summary(self, tier: bool = False) -> str:
        """One line for a reader; the tier is shown only with `tier=True`.

        The tier always stays on the dataclass, the `gate` ledger row,
        `gates/<id>.json` and the report's gate table.
        """
        label = HUMAN_LABELS.get(self.gate_id, self.gate_id)
        extra = ""
        if self.value is not None:
            extra = f"  [{_num(self.value)}" + (
                f" of {_num(self.threshold)}]" if self.threshold is not None else "]"
            )
        detail = self.detail
        if len(detail) > 300:  # T3 audits can run to essays; the terminal gets
            detail = detail[:300] + f" … [full text: gates/{self.gate_id}]"
        pre = f"[{self.tier}] " if tier else ""
        if self.passed:
            mark = "✓" if self.blocking else "•"
            return f"  {mark} {pre}{label}{extra} — {detail}"
        if self.blocking:
            return f"  ✗ FAILED {pre}{label}{extra} — {detail}"
        return f"  ⚑ flag {pre}{label}{extra} — {detail}"


def _num(x) -> str:
    """A measured quantity as a person reads it (thousands separators, yes/no).

    Not a unit system: a gate that wants units puts them in its own `detail`.
    """
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, dict):  # a table of quantities: say how big, not what
        return f"{len(x)} entr{'y' if len(x) == 1 else 'ies'}"
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        return f"{x:,.4g}" if abs(x) >= 1000 else f"{x:.4g}"
    return str(x)


# Plain-English gate names for terminal/report display; ids stay machine-stable.
HUMAN_LABELS = {
    # the observation reply's seam checks, as ONE result on the card at
    # the failure point (never run through the battery, so never among the gates)
    "assembly_observation_seam": "observation reply passes its seam checks",
    "model_declared_constants": "the note says constant — does this model keep it?",
    "evaluation_selection_comparable": "the candidates were scored comparably",
    "model_antimony_builds": "model builds (Antimony → SBML)",
    "model_sbml_valid": "SBML is valid",
    "model_refs_resolve": "every reference resolves",
    "model_estimated_parameters_used": "every estimated parameter is read by the model",
    "model_simulates_nominal": "simulates at nominal parameters",
    "model_nonnegative_states": "states stay non-negative",
    "model_simulates_across_box": "simulates across the parameter bounds box",
    "model_conservation_laws": "conservation-law scan (advisory)",
    "model_supermodel_neutrality": "declared neutral values actually neutralize",
    "data_rows_well_formed": "measurement rows well-formed",
    "data_units_and_error_declared": "units + error type declared",
    "data_holdout_labels_resolve": "held-out conditions resolve",
    "data_processing_legal": "processing steps are legal and declared",
    "data_plausibility_screen": "data plausibility screen (advisory)",
    "assembly_petablint": "petablint",
    "assembly_observables_resolve": "observable formulas resolve",
    "assembly_conditions_resolve": "conditions map to model entities",
    "assembly_measurements_resolve": "measurements reference declared ids",
    "assembly_noise_declared": "noise model declared per observable",
    "assembly_formulas_compile_safe": "every formula uses functions AMICI can compile",
    "assembly_sigma_through_observable": "every sigma reaches the model only through its own observable",
    "assembly_parameters_sane": "parameters bounded and scaled",
    "assembly_merge_noise": "the noise model can be rendered",
    "assembly_merge_observables": "every observable maps onto its own data label",
    "assembly_merge_conditions": "every condition override can be rendered",
    "assembly_dof": "degrees of freedom",
    "assembly_magnitude_reconciliation": "simulation vs data magnitude",
    "assembly_preequilibration": "pre-equilibration reaches steady state",
    "assembly_sensitivity_coverage": "sensitivity coverage + FIM spectrum (advisory)",
    "assembly_verification": "independent checker audit (advisory)",
    "estimation_waterfall_plateau": "waterfall plateau (convergence)",
    "estimation_gradient_norm": "projected gradient norm at optimum",
    "estimation_integration_failures": "integration-failure fraction",
    "estimation_parameters_at_bounds": "parameters at bounds (flag)",
    "evaluation_no_overclaim": "no overclaiming (flat ⇒ declared undetermined)",
    "evaluation_no_underclaim": "no underclaiming (tight ⇒ credited)",
    "evaluation_answers_intent_complete": "intent criteria all answered",
    "evaluation_names_exist": "the interpretation names only what the problem has",
    "evaluation_t2prime_holdout": "held-out prediction (T2′ — the primary gate)",
    "evaluation_noise_model_check": "residuals vs assumed noise model",
    "evaluation_structure_at_optimum": "structural checks repeated at the fitted optimum",
    "evaluation_structural_misfit_open": "structural-misfit indicators (vs the assay's own repeatability)",
    "evaluation_selection_crosscheck": "selection arithmetic cross-checked against petab_select",
    "agent_prompt_bytes": "agent prompt within the declared byte cap (no cap: size recorded)",
    "entry_intent_schema": "entry: intent well-formed",
    "entry_compiled_profile": "entry: cost profile present",
    "entry_evaluation_schema": "entry: evaluation report well-formed",
    "model_no_dynamics_screen": "dynamics present at nominal (screen)",
    "model_required_entities": "user-required entities findable",
    "model_verification": "independent construction audit (advisory)",
    "model_glossary_complete": "entity glossary covers every species",
    "model_essential_reactions": "every essential reaction is in the model, and none outside the set",
    "model_connected": "every piece of the model holds a required entity, and every varied quantity reaches one",
    "model_fact_citations": "every fact a parameter cites is a fact of the dossier",
    "assembly_connected": "every piece of the model is seen by a readout, and every varied quantity reaches one",
}


class GateFailure(Exception):
    """Raised by the runner when a blocking gate fails."""

    def __init__(self, result: GateResult):
        self.result = result
        # tier=True: an exception message is read after the fact, by an auditor
        super().__init__(result.summary(tier=True))


def _verbose_gates() -> bool:
    """Whether to print every passing gate line (`OCTOMOD_VERBOSE_GATES`).

    An environment variable, not a spec key: the spec is hashed into
    `workflow_sha` and compared on resume, so turning on verbosity must not
    invalidate a paused run.
    """
    import os

    return os.environ.get("OCTOMOD_VERBOSE_GATES", "").strip() not in ("", "0")


def failure_summary(results: list, module: str, gate_dir=None) -> str:
    """Why the battery failed, in words, for the message that ends a run.

    Blocking failures only, each with its tier and detail: the tier says
    whether a failure is arguable (T2/T3) or not (T0/T1).
    """
    bad = [r for r in results if not r.passed and r.blocking]
    if not bad:
        return f"{module}: a gate battery failed but no blocking gate reported it"
    head = f"{module}: {len(bad)} blocking check(s) failed " f"of {len(results)} run"
    lines = [head]
    for r in bad:
        detail = str(r.detail or "no detail recorded").strip()
        lines.append(f"  ✗ [{r.tier}] {r.gate_id}")
        for part in detail.split(" | "):
            lines.append(f"      {part}")
    if gate_dir is not None:
        where = getattr(gate_dir, "key", None) or gate_dir
        lines.append(f"  evidence: the record, {where}")
    return "\n".join(lines)


def run_gate_set(
    gates: list,
    gate_dir,
    ledger,
    module: str,
    round_idx: int = 0,
    stop_on_fail: bool = True,
) -> tuple[bool, list[GateResult]]:
    """Run gates in declared (cheap-to-expensive) order.

    Returns (all_blocking_passed, results). Every result, pass or fail, is
    written to `gate_dir` (a record node: `ctx.gates`, one child per gate id)
    and ledgered as a `gate` row.
    """
    # one pass, one set of verdicts: a pass that stops at its first blocking
    # failure must not leave an earlier pass's verdicts for the gates it skipped
    for gate_fn in gates:
        gid = getattr(gate_fn, "gate_id", None)
        if gid:
            gate_dir.child(gid).delete()
    results: list[GateResult] = []
    quiet: list[GateResult] = []
    ok = True
    for gate_fn in gates:
        try:
            res = gate_fn()
        except Exception as e:  # a gate that crashes is a failed gate, loudly
            res = GateResult(
                gate_id=getattr(gate_fn, "gate_id", gate_fn.__name__),
                tier=getattr(gate_fn, "tier", "T1"),
                passed=False,
                detail=f"gate crashed: {type(e).__name__}: {e}",
            )
        # The gate-maker attaches a settings callable because the model is
        # built lazily inside the first gate: there is nothing to read before.
        if getattr(gate_fn, "integrates", False) and res.solver_settings is None:
            src = getattr(gate_fn, "solver_settings", None)
            try:
                res.solver_settings = dict(src()) if callable(src) else None
            except Exception as e:
                res.solver_settings = {"unavailable": f"{type(e).__name__}: {e}"}
            if res.solver_settings is None:
                # an integrating gate with no settings is a wiring bug; the
                # artifact says so instead of looking like a non-integrating gate
                res.solver_settings = {
                    "unavailable": "the gate declares integrates=True but its "
                    "maker attached no solver_settings callable"
                }
        results.append(res)
        gate_dir.child(res.gate_id).put(asdict(res))
        ledger.append(
            "gate",
            module=module,
            round_idx=round_idx,
            gate_id=res.gate_id,
            tier=res.tier,
            passed=res.passed,
            blocking=res.blocking,
            value=res.value,
            threshold=res.threshold,
            detail=res.detail,
            solver_settings=res.solver_settings,
        )
        # Passing blocking gates collapse into one summary line; failures and
        # flags print in full at once. `OCTOMOD_VERBOSE_GATES=1` prints all.
        if _verbose_gates() or not (res.passed and res.blocking):
            print(res.summary())
        else:
            quiet.append(res)
        if not res.passed and res.blocking:
            ok = False
            if stop_on_fail:
                break
    if quiet and not _verbose_gates():
        first = quiet[0].gate_id.split("_")[0]
        print(
            f"  ✓ {len(quiet)} check(s) passed"
            + (f" ({first})" if all(g.gate_id.startswith(first) for g in quiet) else "")
            + " — every one is in the ledger and in the record's gates"
        )
    return ok, results


def gate(gate_id: str, tier: str, integrates: bool = False):
    """Decorator attaching the gate id, tier and `integrates` flag.

    `integrates=True` declares that the verdict depends on an ODE solve; the
    runner then requires a `solver_settings` callable attached by the
    gate-maker. `INTEGRATION_GATES` lists these gates, and
    `tests/solver_settings_unit.py` checks that the two agree.
    """

    def wrap(fn):
        fn.gate_id = gate_id
        fn.tier = tier
        fn.integrates = integrates
        return fn

    return wrap


# Every gate whose verdict depends on an ODE solve. Declared here rather than
# inferred, so the test has something to hold the code to: a gate that starts
# integrating and is not added here fails `tests/solver_settings_unit.py`.
INTEGRATION_GATES = frozenset(
    {
        "model_simulates_nominal",
        "model_nonnegative_states",
        "model_simulates_across_box",
        "model_no_dynamics_screen",
        "assembly_magnitude_reconciliation",
        "assembly_preequilibration",
        "assembly_sensitivity_coverage",
    }
)
