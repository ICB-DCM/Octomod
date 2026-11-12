"""S3 gate battery: the estimation problem is checked before it may cost money.

Everything here runs WITHOUT an AMICI compile (roadrunner + table logic), so
the full battery sits before the human cost gate. Order: cheap referential
checks first, simulation-based checks last.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from octomod.gates import GateResult, gate

# one tokenizer for every formula: the math-word set and both regexes live once
from octomod.workflow_modules.assembly.assembly_edit import PLACEHOLDER as _PLACEHOLDER
from octomod.workflow_modules.assembly.assembly_edit import TOKEN as _TOKEN
from octomod.workflow_modules.assembly.assembly_edit import symbols
from octomod.workflow_modules.model.simwrap import RRModel, SimError, eval_formula


def noise_band(tables, obs_id, cond_id, times, values=None, z: float = 1.0):
    """Per-point `z * sigma` over `times`, for a band a plot adds to a curve.

    Per point because a proportional sigma widens with the signal and an
    additive+proportional one has no single value. Falls back to a flat band
    only when the series cannot be computed, and to zeros rather than nan, so
    a plot degrades to "no noise band" instead of vanishing.
    """
    times = np.asarray(times, dtype=float)
    try:
        return z * np.asarray(
            tables.sigma_series(str(obs_id), str(cond_id), times, values or {}),
            dtype=float,
        )
    except Exception:
        try:
            flat = float(
                resolve_sigmas(tables, values=values or {}).get(str(obs_id), 0.0)
            )
        except Exception:
            flat = 0.0
        if not np.isfinite(flat):
            flat = 0.0
        return z * flat * np.ones_like(times, dtype=float)


def per_condition_sigmas(
    tables: PetabTables, values: dict | None = None
) -> dict[str, dict[str, float]]:
    """{observable: {condition: sigma}} for every observable whose rows name a
    DIFFERENT sigma parameter per condition. Empty for a shared sigma, so
    a caller can test membership. Only constant (bare-parameter or numeric)
    sigmas are resolved to a number; a state-dependent one is nan."""
    values = values or {}
    nominals = {
        str(r["parameterId"]): float(r["nominalValue"])
        for _, r in tables.parameters.iterrows()
        if pd.notna(r.get("nominalValue"))
    }
    out: dict[str, dict[str, float]] = {}
    for _, row in tables.observables.iterrows():
        oid = str(row["observableId"])
        refs = tables.noise_parameter_refs(oid)
        if len(set(refs.values())) <= 1:
            continue
        per: dict[str, float] = {}
        for cid in refs:
            expr = tables.noise_expression(oid, cid)
            try:
                per[cid] = float(expr)
                continue
            except ValueError:
                pass
            if _TOKEN.fullmatch(expr):
                per[cid] = float(values.get(expr, nominals.get(expr, float("nan"))))
            else:
                per[cid] = float("nan")
        out[oid] = per
    return out


def sigma_components(tables: PetabTables, obs_id: str) -> list[str]:
    """The free (non-model) symbols in this observable's resolved sigma, in
    formula order — one for constant or proportional noise, two for
    additive+proportional."""
    expr = tables.noise_expression(obs_id)
    free = symbols(expr) - set(tables.model_entities)
    out: list[str] = []
    for tok in re.findall(r"[A-Za-z_]\w*", expr):
        if tok in free and tok not in out:
            out.append(tok)
    return out


def sigma_kind(tables: PetabTables, obs_id: str) -> str:
    """ "constant" | "proportional" | "multi_component".

    Callers that print or draw ONE sigma need to know which of these they have
    before they show a number, because for the third there is no single sigma
    to show — only `PetabTables.sigma_series`, which is per point.

    **The invariant, asserted in `tests/two_component_noise_unit.py`:**

        resolve_sigmas(...)[oid] is nan  <==>  sigma_kind(...) == "multi_component"

    It is NOT "nan iff not constant": a single-sigma proportional formula is
    state-dependent yet has a meaningful single number, its scale parameter,
    which `resolve_sigmas` returns. A two-symbol formula whose second term is
    a fixed parameter rather than a species is constant across points and
    evaluates to a real number.
    """
    if tables.sigma_is_constant(obs_id):
        return "constant"
    return (
        "multi_component"
        if len(sigma_components(tables, obs_id)) > 1
        else "proportional"
    )


def resolve_sigmas(tables: PetabTables, values: dict | None = None) -> dict[str, float]:
    """Per-observable sigma as ONE number, resolving the PEtab noiseParameters
    placeholder chain: observable noiseFormula -> measurement noiseParameters
    -> parameter table nominal (or the supplied fitted values).

    Returns **nan** when no single number is the sigma: additive+proportional
    noise, where sigma varies with the signal, and a sigma indexed by
    condition (`per_condition_sigmas`). Callers must either handle nan or use
    `PetabTables.sigma_series`, the per-point answer.
    """
    values = values or {}
    nominals = {
        str(r["parameterId"]): float(r["nominalValue"])
        for _, r in tables.parameters.iterrows()
        if pd.notna(r.get("nominalValue"))
    }
    out = {}
    for _, row in tables.observables.iterrows():
        oid = str(row["observableId"])
        # a sigma indexed by condition has no single number — say so with
        # nan (as additive+proportional noise does) and let callers that want
        # the per-condition values use `per_condition_sigmas`
        try:
            if len(set(tables.noise_parameter_refs(oid).values())) > 1:
                out[oid] = float("nan")
                continue
        except Exception:
            pass
        # `noise_expression` resolves the whole placeholder chain, including a
        # multi-entry cell (`s_abs;s_rel`), into an expression.
        source = tables.noise_expression(oid)
        try:
            out[oid] = float(source)
            continue
        except ValueError:
            pass
        if _TOKEN.fullmatch(source):  # a bare parameter id: the constant sigma
            out[oid] = float(values.get(source, nominals.get(source, 1.0))) or 1.0
            continue
        # An EXPRESSION (proportional noise): the constant returned here is
        # its SCALE parameter — the one symbol that is not a model entity —
        # so callers that need a single number get the scale, and callers that
        # need the per-point sigma use PetabTables.sigma_series.
        scale = [
            t
            for t in symbols(source)
            if t not in tables.model_entities and t in set(values) | set(nominals)
        ]
        if len(scale) == 1:
            out[oid] = float(values.get(scale[0], nominals.get(scale[0], 1.0))) or 1.0
        else:
            # Two or more free symbols: a single number exists iff sigma does
            # not depend on the state (`sigma_is_constant`). `sigma_abs +
            # sigma_rel * k`, with k a fixed parameter, is constant: evaluate it.
            try:
                constant = tables.sigma_is_constant(oid)
            except Exception:
                constant = False
            value = float("nan")
            if constant:
                ns = {
                    name: float(values.get(name, nominals.get(name, float("nan"))))
                    for name in symbols(source)
                }
                try:
                    value = float(eval_formula(source, ns))
                except Exception:
                    value = float("nan")
            # nan when sigma is a FUNCTION of the signal: no single number is
            # the sigma. Callers use `PetabTables.sigma_series` instead.
            out[oid] = value
    return out


PREEQ_COLUMN = "preequilibrationConditionId"


def preequilibration_map(*frames) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Which condition each simulation condition is pre-equilibrated from.

    Read off the measurement rows (training and held-out alike). Returns
    ({simulation condition: pre-equilibration condition}, {simulation
    condition: the ids its rows disagree on}); a condition whose rows name no
    pre-equilibration is in neither.
    """
    seen: dict[str, set[str]] = {}
    for df in frames:
        if df is None or not len(df):
            continue
        pre = (
            df[PREEQ_COLUMN]
            if PREEQ_COLUMN in df.columns
            else pd.Series(np.nan, index=df.index)
        )
        for sim, p in zip(df["simulationConditionId"].astype(str), pre, strict=True):
            val = "" if pd.isna(p) else str(p).strip()
            seen.setdefault(sim, set()).add(val)
    mapping = {s: next(iter(v)) for s, v in seen.items() if len(v) == 1 and "" not in v}
    mixed = {s: sorted(v) for s, v in seen.items() if len(v) > 1}
    return mapping, mixed


class PetabTables:
    """The assembled problem as plain tables + the SBML it points at.

    `holdout_measurements` is read only for which conditions pre-equilibrate,
    so a held-out condition simulates the way the compiled problem would."""

    def __init__(
        self,
        observables: pd.DataFrame,
        conditions: pd.DataFrame,
        measurements: pd.DataFrame,
        parameters: pd.DataFrame,
        sbml: str,
        tolerances: dict | None = None,
        holdout_measurements: pd.DataFrame | None = None,
    ):
        self.observables = observables
        self.conditions = conditions
        self.measurements = measurements
        self.parameters = parameters
        self.sbml = sbml
        self.holdout_measurements = holdout_measurements
        self.model = RRModel(sbml, tolerances)
        self._preeq, self._preeq_mixed = preequilibration_map(
            measurements, holdout_measurements
        )
        self._steady: dict = {}  # (pre-equilibration id, overrides) -> state

    def preequilibration_of(self, condition_id: str) -> str | None:
        """The condition `condition_id` is pre-equilibrated from, if any.

        A condition whose measurement rows name different ones (PEtab allows
        it) has no single start state here, and raises SimError by name."""
        cid = str(condition_id)
        if cid in self._preeq_mixed:
            raise SimError(
                f"condition {cid!r}: its measurement rows name different "
                f"pre-equilibration conditions {self._preeq_mixed[cid]}; a "
                f"roadrunner simulation of it has no single start state"
            )
        return self._preeq.get(cid)

    @property
    def preequilibration_only_ids(self) -> set[str]:
        """Conditions that are only ever pre-equilibrated from, never measured."""
        pre = set(self._preeq.values())
        measured = set(self._preeq) | set(self._preeq_mixed)
        measured |= set(self.measurements["simulationConditionId"].astype(str))
        return pre - measured

    def _start_state(
        self, condition_id: str, param_override: dict | None, dyn_override: dict
    ) -> dict[str, float] | None:
        """The species a pre-equilibrated condition starts from (PEtab v1).

        The pre-equilibration condition is simulated to its steady state;
        every species then carries over, except one the simulation condition
        itself sets, which is re-initialised. None without pre-equilibration."""
        pre_id = self.preequilibration_of(condition_id)
        if pre_id is None:
            return None
        over = {
            **self.condition_overrides(pre_id, values=param_override),
            **dyn_override,
        }
        key = (pre_id, tuple(sorted(over.items())))
        if key not in self._steady:
            if len(self._steady) > 256:
                self._steady.clear()
            self._steady[key] = self.model.steady_state(overrides=over)
        reset = set(self.condition_overrides(condition_id, values=param_override))
        return {s: v for s, v in self._steady[key].items() if s not in reset}

    def apply_tolerances(self, tolerances: dict | None) -> dict:
        """Re-apply `simulation.roadrunner` to the loaded model.

        For a caller holding a spec (`make_petab_gates`, whose verdicts record
        a tolerance) when the tables were built without one. Returns what the
        integrator actually holds afterwards."""
        return self.model._apply_tolerances(tolerances)

    @classmethod
    def from_input(cls, inp) -> PetabTables:
        """From a `petab_io.PetabInput` (the record's problem, or one on disk).

        One constructor for every caller, so no call site spells the four
        table reads out by hand — where a caller that passes the location
        itself gets a TypeError at run time instead of at review time."""
        return cls(
            observables=inp.observables,
            conditions=inp.conditions,
            measurements=inp.measurements,
            parameters=inp.parameters,
            sbml=inp.sbml,
            # read only for which conditions pre-equilibrate
            holdout_measurements=inp.holdout,
        )

    @classmethod
    def from_work(cls, work, model) -> PetabTables:
        """The assembled problem of a unit of work (`ctx.work`, `ctx.model`)."""
        from octomod.workflow_modules.assembly import petab_io

        return cls.from_input(petab_io.from_work(work, model))

    def as_input(self):
        from octomod.workflow_modules.assembly.petab_io import PetabInput

        return PetabInput(
            sbml=self.sbml,
            observables=self.observables,
            conditions=self.conditions,
            measurements=self.measurements,
            parameters=self.parameters,
            holdout=self.holdout_measurements,
        )

    @property
    def model_entities(self) -> set[str]:
        """Everything in the model that a name can refer to — floating species,
        BOUNDARY species (a catalyst written `$E`) and global parameters."""
        return set(self.model.entity_ids)

    @property
    def petab_param_ids(self) -> set[str]:
        return set(self.parameters["parameterId"].astype(str))

    def observable_scaling_params(self, obs_id: str) -> set[str]:
        """Parameters in this observable's formula that are NOT model entities
        — i.e. observable-level scaling/offset parameters.

        PEtab expresses a PER-MEASUREMENT scaling as a PLACEHOLDER in the
        formula (`observableParameter1_<obsId>`) whose real parameter names sit
        in the measurement table's `observableParameters` column. `symbols()`
        drops placeholders, so they are counted here, resolved to the names the
        measurement table gives them when it can.
        """
        row = self.observables.set_index("observableId").loc[obs_id]
        formula = str(row["observableFormula"])
        named = symbols(formula) - self.model_entities
        placeholders = {
            tok
            for tok in _TOKEN.findall(formula)
            if _PLACEHOLDER.match(tok) and tok.startswith("observableParameter")
        }
        if not placeholders:
            return named
        return (
            named | self._resolved_observable_parameters(obs_id) or named | placeholders
        )

    def _resolved_observable_parameters(self, obs_id: str) -> set[str]:
        """The real names behind this observable's placeholders, from the
        measurement table's `observableParameters` column (semicolon-separated,
        positional). Numeric overrides are not parameters and are skipped."""
        col = "observableParameters"
        if col not in self.measurements.columns:
            return set()
        rows = self.measurements[
            self.measurements["observableId"].astype(str) == str(obs_id)
        ]
        out: set[str] = set()
        for raw in rows[col].dropna().astype(str):
            for part in raw.split(";"):
                name = part.strip()
                if not name or name.lower() == "nan":
                    continue
                try:
                    float(name)
                except ValueError:
                    out.add(name)
        return out

    def condition_overrides(
        self, condition_id: str, values: dict[str, float] | None = None
    ) -> dict[str, float]:
        """The condition's overrides as numbers.

        A PARAMETER-VALUED entry (`STAT1_tot -> STAT1_tot_Bcell`) resolves to
        `values[id]` when the caller passes a parameter vector (fitted values,
        linear scale), else to the parameter table's nominal, so a gate
        simulation and a post-fit simulation both see the right number. An
        entry that is neither a number nor a table parameter raises ValueError."""
        row = self.conditions.set_index("conditionId").loc[condition_id]
        out = {}
        for col, val in row.items():
            if col in ("conditionId", "conditionName") or pd.isna(val):
                continue
            try:
                out[str(col)] = float(val)
                continue
            except (TypeError, ValueError):
                pass
            pid = str(val).strip()
            if values and pid in values:
                out[str(col)] = float(values[pid])
                continue
            hit = self.parameters.loc[
                self.parameters["parameterId"].astype(str) == pid, "nominalValue"
            ]
            if len(hit) == 0 or pd.isna(hit.iloc[0]):
                raise ValueError(
                    f"condition {condition_id!r}: override {col!r} = {pid!r} is "
                    f"neither a number nor a parameter in the parameter table"
                )
            out[str(col)] = float(hit.iloc[0])
        return out

    def nominal_namespace(self) -> dict[str, float]:
        """Parameter values for formula evaluation: model nominals overlaid
        with the PEtab parameter table nominals (linear scale)."""
        ns = self.model.parameter_values()
        for _, row in self.parameters.iterrows():
            if pd.notna(row.get("nominalValue")):
                ns[str(row["parameterId"])] = float(row["nominalValue"])
        return ns

    def _namespace(
        self,
        condition_id: str,
        times: np.ndarray,
        param_override: dict[str, float] | None = None,
        simulate: bool = True,
    ) -> dict:
        """The evaluation namespace for one condition: nominals overlaid with
        the condition's overrides and the caller's parameter values, plus (when
        `simulate`) every species' trajectory interpolated at `times`.

        A time of `inf` is PEtab's steady-state measurement: it reads the state
        the condition settles to (`RRModel.settled_values`), as AMICI's
        post-equilibration does, never the end of the time course."""
        overrides = self.condition_overrides(condition_id, values=param_override)
        dyn_override = {}
        ns_extra = {}
        if param_override:
            for k, v in param_override.items():
                if k in self.model_entities:
                    dyn_override[k] = v
                else:
                    ns_extra[k] = v
        ns = self.nominal_namespace()
        # condition + explicit overrides win over nominals
        ns.update(overrides)
        ns.update(dyn_override)
        ns.update(ns_extra)
        if simulate:
            times = np.asarray(times, dtype=float)
            steady = np.isposinf(times)
            finite = times[~steady]
            t_end = float(max(finite)) if len(finite) else 1.0
            t_end = t_end if t_end > 0 else 1.0
            sim_overrides = {**overrides, **dyn_override}
            # a pre-equilibrated condition starts where the compiled
            # problem starts it, not at the model's initial values
            start = self._start_state(condition_id, param_override, dyn_override)
            traj = self.model.simulate(
                t_end * 1.0001,
                n_points=201,
                overrides=sim_overrides,
                initial_state=start,
            )
            settled = None
            if steady.any():
                settled = self.model.settled_values(
                    overrides=sim_overrides, initial_state=start
                )
            # species AND assignment-rule parameters: both are functions of the
            # state and need their TIME COURSE here, not the scalar the model
            # last sat at.
            for name in self.model.dynamic_ids:
                values = np.interp(times, traj["time"], traj[name])
                if settled is not None:
                    values = np.where(steady, settled[name], values)
                ns[name] = values
        return ns

    def simulate_observables(
        self,
        condition_id: str,
        times: np.ndarray,
        param_override: dict[str, float] | None = None,
    ) -> dict[str, np.ndarray]:
        """Simulate one condition, evaluate every observable formula at the
        requested times. Returns {observable_id: values}."""
        ns = self._namespace(condition_id, times, param_override)
        out = {}
        for _, row in self.observables.iterrows():
            oid = str(row["observableId"])
            out[oid] = np.asarray(
                eval_formula(self.observable_expression(oid, condition_id), ns),
                dtype=float,
            ) * np.ones_like(times, dtype=float)
        return out

    # noise: the noise formula may be an expression
    def _resolve_placeholders(
        self,
        expr: str,
        obs_id: str,
        column: str,
        prefix: str,
        condition_id: str | None = None,
    ) -> str:
        """Substitute PEtab's `<prefix><n>_<observableId>` placeholders with
        whatever the measurement table's `column` names for that observable.

        One implementation for both placeholder families (`noiseParameter`
        from `noiseParameters`, `observableParameter` from
        `observableParameters`), which resolve by identical rules.
        """
        if column not in self.measurements.columns:
            return expr
        rows = self.measurements[self.measurements["observableId"] == obs_id]
        if condition_id is not None and "simulationConditionId" in rows.columns:
            # a per-condition sigma (or a per-condition scale factor) names
            # a DIFFERENT parameter per condition; resolve for the rows
            # of this condition, and fall back to any row when it has none
            mine = rows[rows["simulationConditionId"].astype(str) == str(condition_id)]
            if len(mine):
                rows = mine
        refs = rows[column].dropna().astype(str).unique()
        if not len(refs):
            return expr
        for k, v in enumerate(str(refs[0]).split(";"), start=1):
            expr = re.sub(rf"\b{prefix}{k}_{re.escape(obs_id)}\b", v.strip(), expr)
        return expr

    def observable_expression(
        self, obs_id: str, condition_id: str | None = None
    ) -> str:
        """The observable's formula with its observable-parameter placeholders
        resolved — the expression that actually defines the observable. With
        `condition_id`, resolved for that condition's rows (a per-condition
        scale factor names a different parameter per condition)."""
        row = self.observables.set_index("observableId").loc[obs_id]
        return self._resolve_placeholders(
            str(row.get("observableFormula", "")),
            obs_id,
            "observableParameters",
            "observableParameter",
            condition_id,
        )

    def noise_expression(self, obs_id: str, condition_id: str | None = None) -> str:
        """The observable's noiseFormula with the PEtab placeholder chain
        resolved to whatever the measurement table names (a parameter id or a
        number) — the expression that actually defines sigma. With
        `condition_id`, resolved for that condition's rows (a per-condition
        sigma names a different parameter per condition)."""
        row = self.observables.set_index("observableId").loc[obs_id]
        expr = self._resolve_placeholders(
            str(row.get("noiseFormula", "")),
            obs_id,
            "noiseParameters",
            "noiseParameter",
            condition_id,
        )
        # a noise formula may also scale with the observable's own parameters
        # (PEtab's flattening of time-point-specific overrides writes them so)
        return self._resolve_placeholders(
            expr, obs_id, "observableParameters", "observableParameter", condition_id
        )

    def noise_parameter_refs(self, obs_id: str) -> dict[str, str]:
        """condition id -> the `noiseParameters` cell that condition's rows
        carry. One distinct value means a shared sigma; several mean the sigma
        is indexed by condition."""
        meas = self.measurements
        if "noiseParameters" not in meas.columns:
            return {}
        rows = meas[meas["observableId"] == obs_id]
        out: dict[str, str] = {}
        for cid, grp in rows.groupby("simulationConditionId"):
            vals = grp["noiseParameters"].dropna().astype(str).unique()
            if len(vals):
                out[str(cid)] = str(vals[0])
        return out

    def sigma_is_constant(self, obs_id: str) -> bool:
        """True when sigma does not depend on the state (no species in the
        expression) — the case every replicate-floor comparison assumes."""
        return not (
            symbols(self.noise_expression(obs_id)) & set(self.model.species_ids)
        )

    def sigma_series(
        self,
        obs_id: str,
        condition_id: str,
        times: np.ndarray,
        param_override: dict[str, float] | None = None,
    ) -> np.ndarray:
        """Per-point sigma for one observable in one condition, whatever the
        noise formula is: a number, a parameter, or an expression in the model
        state (proportional noise)."""
        times = np.asarray(times, dtype=float)
        expr = self.noise_expression(obs_id, condition_id)
        try:
            return np.full(len(times), float(expr))
        except ValueError:
            pass
        ns = self._namespace(
            condition_id,
            times,
            param_override,
            simulate=not self.sigma_is_constant(obs_id),
        )
        val = np.asarray(eval_formula(expr, ns), dtype=float)
        return np.abs(val) * np.ones_like(times, dtype=float)


# ------------------------------------------- a sigma AMICI can compile

# an identifier, never the exponent letter of a number such as 1e-3
_IDENT = re.compile(r"(?<![\w.])[A-Za-z_]\w*")
# the characters a PEtab formula is written in; anything else is not parsed
_FORMULA_CHARS = re.compile(r"[\w\s+\-*/^().,]*")


def _sympify_formula(expr: str):
    """A PEtab formula as a sympy expression, every identifier a real Symbol
    of its own name — `lambda`, `S` or `E` included, which a plain sympify
    reads as Python or sympy names. Raises ValueError for text that is not a
    formula this can read."""
    import sympy as sp

    text = str(expr)
    if not _FORMULA_CHARS.fullmatch(text) or re.search(r"\.\s*[A-Za-z_]", text):
        raise ValueError(f"not a formula this check reads: {expr!r}")
    funcs = {
        "exp": sp.exp,
        "log": sp.log,
        "ln": sp.log,
        "log10": lambda x: sp.log(x, 10),
        "log2": lambda x: sp.log(x, 2),
        "sqrt": sp.sqrt,
        "abs": sp.Abs,
        "min": sp.Min,
        "max": sp.Max,
        "pow": sp.Pow,
        "sin": sp.sin,
        "cos": sp.cos,
        "tan": sp.tan,
    }
    local: dict = {}
    aliases: dict[str, str] = {}

    def _alias(m: re.Match) -> str:
        name = m.group(0)
        called = text[m.end() :].lstrip().startswith("(")
        if called and name in funcs:
            local[f"_f_{name}"] = funcs[name]
            return f"_f_{name}"
        if name == "pi" and not called:
            local["_c_pi"] = sp.pi
            return "_c_pi"
        key = aliases.setdefault(name, f"_s{len(aliases)}_")
        local[key] = sp.Symbol(name, real=True)
        return key

    try:
        return sp.sympify(_IDENT.sub(_alias, text), locals=local, convert_xor=True)
    except (sp.SympifyError, SyntaxError, TypeError) as e:
        raise ValueError(f"not a formula this check reads: {expr!r}") from e


def sigma_state_problem(
    noise_expr: str,
    obs_expr: str,
    states: set[str],
    *,
    rules: set[str] | frozenset[str] = frozenset(),
    obs_id: str | None = None,
    core: str | None = None,
) -> str | None:
    """Why this observable's sigma is refused, or None when it is accepted.

    Where the observable's formula appears whole in the noise formula it
    becomes the prediction `y`, as AMICI's PEtab import does. A symbol of
    `rules` left in the sigma is an undeclared identifier in AMICI's generated
    C++.

    `core` is the observable's own formula without its gain and offset, as an
    agent wrote it. Given, the workflow's rule applies: `core` becomes `y`
    too, and any state left after both substitutions is refused. Nothing is
    solved, so a sigma the formula determines only through algebra is re-asked
    rather than accepted. A sigma written on `core` under a gain or offset
    still has to pass AMICI's elimination below, since that is how AMICI
    reaches the prediction from it, so this rule never accepts what AMICI
    refuses.

    Without `core` (tables nobody in this run wrote), AMICI's own rule: every
    state still in the sigma must be eliminated by solving
    `y = <observable formula>` for it: exactly one solution, and no state left
    after substituting it (the DE model). AMICI takes the state to solve for
    from an unordered set, so this requires the elimination to succeed from
    each of them.

    Expands nothing: the caller passes formulas with their rules expanded. A
    formula this cannot read is left to the syntax gates (None).
    """
    import sympy as sp

    named = set(_IDENT.findall(str(noise_expr)))
    if not named & (set(states) | set(rules)):
        return None
    try:
        sigma = _sympify_formula(noise_expr)
        y_expr = _sympify_formula(obs_expr)
        core_expr = None if core is None else _sympify_formula(core)
    except ValueError:
        return None
    y = sp.Dummy("y", real=True)
    sigma = sigma.subs(y_expr, y)
    who = f"observable {obs_id}" if obs_id else "this observable"
    left_rules = sorted({s.name for s in sigma.free_symbols} & set(rules))
    if left_rules:
        return (
            f"The noise formula of {who} names {left_rules}, which the model "
            f"defines by assignment rule. AMICI's generated sigma code has no "
            f"such identifier, so the build fails. Write the rule's formula in "
            f"its place, or this observable's own formula."
        )
    in_sigma = sorted(
        (s for s in sigma.free_symbols if s.name in states), key=lambda s: s.name
    )
    if core_expr is not None:
        # a formula that names no symbol is a number, and a number is not
        # replaced wherever it occurs
        through = sigma.subs(core_expr, y) if core_expr.free_symbols else sigma
        left = sorted({s.name for s in through.free_symbols} & set(states))
        if left:
            return (
                f"The noise formula of {who} depends on {left} other than "
                f"through this observable's own formula. The noise may depend on "
                f"the model only through this observable's prediction: write "
                f"`sigma_abs + sigma_rel * <this observable's formula>` (with or "
                f"without its gain `sc_obs_x`), a constant, or a gain-scaled "
                f"sigma."
            )
        if not in_sigma:
            return None
    for x in in_sigma:
        if x not in y_expr.free_symbols:
            break
        try:
            solutions = sp.solve(sp.Eq(y, y_expr), x)
        except Exception:
            solutions = []
        if len(solutions) != 1:
            break
        if any(s.name in states for s in sigma.subs(x, solutions[0]).free_symbols):
            break
    else:
        return None
    if core_expr is not None:
        return (
            f"The noise formula of {who} is written on this observable's own "
            f"formula without its gain or offset. AMICI reaches the prediction "
            f"from that only by solving the observable's formula for "
            f"{[s.name for s in in_sigma]}, which does not succeed for each of "
            f"them, so the build can fail. Write it on the whole prediction, "
            f"`sigma_abs + sigma_rel * sc_obs_x * <this observable's formula>` "
            f"(with the offset when it has one), a constant, or a gain-scaled "
            f"sigma."
        )
    return (
        f"The noise formula of {who} depends on {[s.name for s in in_sigma]}, "
        f"which {who}'s own formula does not determine. AMICI computes a "
        f"state-dependent sigma through the observable's own prediction, so "
        f"every state in the sigma must be solvable from this observable's "
        f"formula. Write the noise on this observable's own signal expression "
        f"(`sigma_abs + sigma_rel * sc_obs_x * <this observable's formula>` "
        f"when the error follows the measured signal, or the formula without "
        f"its gain), or use a constant or gain-scaled sigma."
    )


def _cell_value(v) -> str:
    """One condition-table cell as a comparable token: a number by its value
    (`1` and `1.0` are one), an empty cell as empty, an id as itself."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    try:
        return repr(float(v))
    except (TypeError, ValueError):
        return str(v).strip()


def varied_columns(conditions: pd.DataFrame) -> list[str]:
    """The condition-table columns whose value differs between rows.

    A column that holds one value in every row varies nothing. The
    pre-equilibration conditions the measurement tables name are rows of the
    same table, so a quantity a pre-equilibration sets differently from the
    condition it starts is varied too. An empty cell (a species kept where
    the pre-equilibration left it) differs from a set one."""
    out = []
    for col in conditions.columns:
        if col in ("conditionId", "conditionName"):
            continue
        if len({_cell_value(v) for v in conditions[col]}) > 1:
            out.append(str(col))
    return out


def make_petab_gates(
    tables: PetabTables,
    spec,
    *,
    cores: dict[str, str] | None = None,
) -> list:
    """The S3 battery on written tables.

    `cores` maps each observable id to its own formula as the agent wrote it,
    rules expanded, for tables this run's merge wrote from its assembly: the
    sigma check then applies the workflow's rule (`sigma_state_problem` with
    `core`). Without it, as for a supplied problem, the check decides by what
    AMICI compiles.
    """
    # The S3 gates that simulate do so at the DECLARED tolerance, and record
    # it: a comparison of simulated against measured magnitudes is one an
    # undeclared tolerance can move.
    rr_tol = dict(tables.apply_tolerances(spec.get("simulation.roadrunner") or {}))

    def _settings() -> dict:
        return {"solver": "roadrunner/cvode", **rr_tol}

    obs, cond, meas, par = (
        tables.observables,
        tables.conditions,
        tables.measurements,
        tables.parameters,
    )

    @gate("assembly_petablint", "T0")
    def g_lint():
        # the problem is built from the tables and SBML in memory;
        # petablint runs on the object, exactly as it would on files
        from octomod.workflow_modules.assembly.petab_io import lint, load_problem

        ok_lint, msgs = lint(load_problem(tables.as_input()))
        if not ok_lint:
            return GateResult(
                "assembly_petablint",
                "T0",
                False,
                detail="petablint: " + " | ".join(msgs[-4:]),
            )
        return GateResult("assembly_petablint", "T0", True, detail="petablint clean")

    @gate("assembly_formulas_compile_safe", "T0")
    def g_formulas():
        """Every observable and noise formula calls only functions AMICI can
        compile. petablint, roadrunner and Antimony accept `log2`; AMICI does
        not, and the failure otherwise surfaces as a dropped candidate at the
        compile step."""
        from octomod.workflow_modules.assembly.assembly_edit import (
            unsupported_functions,
        )

        bad = []
        for _, row in tables.observables.iterrows():
            for col in ("observableFormula", "noiseFormula"):
                fns = unsupported_functions(str(row.get(col, "")))
                if fns:
                    bad.append(f"{row['observableId']}.{col} calls {fns}")
        if bad:
            return GateResult(
                "assembly_formulas_compile_safe",
                "T0",
                False,
                detail="AMICI cannot compile: "
                + " | ".join(bad)
                + " — write log2(x) as log(x)/log(2)",
            )
        return GateResult(
            "assembly_formulas_compile_safe",
            "T0",
            True,
            detail="every observable/noise formula uses AMICI-compilable functions only",
        )

    @gate("assembly_sigma_through_observable", "T0")
    def g_sigma():
        """Every state-dependent sigma is one AMICI can compile: each state in
        it solvable from its own observable's formula, and no assignment-rule
        symbol left in it. petablint and roadrunner accept both; AMICI's import
        refuses the first and its C++ build fails on the second, for every
        candidate at the compile step. With `cores`, the stricter rule an
        agent's formula meets: the sigma reaches the model only through the
        observable's own formula."""
        rules = set(tables.model.assignment_ids)
        # a boundary species counts as a state too: AMICI imports it as a
        # species, and a sigma on one is refused here rather than at the compile
        states = (
            set(tables.model.species_ids) | set(tables.model.boundary_ids)
        ) - rules
        names = (
            obs["observableName"].astype(str)
            if "observableName" in obs.columns
            else obs["observableId"].astype(str)
        )
        bad: dict[str, str] = {}
        for oid, name in zip(obs["observableId"].astype(str), names, strict=True):
            # a copy flattened per timepoint is named by the assembly's own id,
            # the one the re-asked agent wrote, and reported once
            shown = name if oid.startswith(f"{name}__") else oid
            problem = sigma_state_problem(
                tables.noise_expression(oid),
                tables.observable_expression(oid),
                states,
                rules=rules,
                obs_id=shown,
                core=(cores or {}).get(shown),
            )
            if problem:
                bad.setdefault(shown, problem)
        if bad:
            problems = list(bad.values())
            return GateResult(
                "assembly_sigma_through_observable",
                "T0",
                False,
                detail=" | ".join(problems[:4])
                + (f" | … and {len(problems) - 4} more" if len(problems) > 4 else ""),
            )
        return GateResult(
            "assembly_sigma_through_observable",
            "T0",
            True,
            detail="every sigma is constant in the state or expressible through "
            "its own observable",
        )

    @gate("assembly_observables_resolve", "T0")
    def g_obs():
        """Every observable formula resolves; species references exist."""
        known = tables.model_entities | tables.petab_param_ids
        problems = []
        for _, row in obs.iterrows():
            unresolved = symbols(row["observableFormula"]) - known
            if unresolved:
                problems.append(
                    f"{row['observableId']}: formula references unknown "
                    f"symbols {sorted(unresolved)}"
                )
            unresolved_noise = (
                symbols(row.get("noiseFormula", ""))
                - known
                - set(obs["observableId"].astype(str))
            )
            if unresolved_noise:
                problems.append(
                    f"{row['observableId']}: noiseFormula references unknown "
                    f"symbols {sorted(unresolved_noise)}"
                )
        if problems:
            return GateResult(
                "assembly_observables_resolve",
                "T0",
                False,
                detail=" | ".join(problems[:4]),
            )
        return GateResult(
            "assembly_observables_resolve",
            "T0",
            True,
            detail=f"{len(obs)} observable formulas resolve",
        )

    @gate("assembly_conditions_resolve", "T0")
    def g_cond():
        problems = []
        for col in cond.columns:
            if col in ("conditionId", "conditionName"):
                continue
            if col not in tables.model_entities:
                problems.append(
                    f"condition column {col!r} maps to no model parameter or species"
                )
        if problems:
            return GateResult(
                "assembly_conditions_resolve", "T0", False, detail=" | ".join(problems)
            )
        return GateResult(
            "assembly_conditions_resolve",
            "T0",
            True,
            detail=f"{len(cond)} conditions resolve against the model",
        )

    @gate("assembly_measurements_resolve", "T0")
    def g_meas():
        problems = []
        known_obs = set(obs["observableId"])
        known_cond = set(cond["conditionId"])
        bad_obs = set(meas["observableId"]) - known_obs
        bad_cond = set(meas["simulationConditionId"]) - known_cond
        if bad_obs:
            problems.append(
                f"measurements reference undeclared observables {sorted(bad_obs)}"
            )
        if bad_cond:
            problems.append(
                f"measurements reference undeclared conditions {sorted(bad_cond)}"
            )
        if "preequilibrationConditionId" in meas.columns:
            pre = meas["preequilibrationConditionId"].dropna()
            bad_pre = set(pre.astype(str)) - {""} - known_cond
            if bad_pre:
                problems.append(
                    f"undeclared pre-equilibration conditions {sorted(bad_pre)}"
                )
        # Deliberately no duplicate-row check here: repeated
        # (observable, condition, time) rows are how PEtab encodes replicates.
        # Duplicate detection lives at S2, where replicate identity exists.
        if problems:
            return GateResult(
                "assembly_measurements_resolve",
                "T0",
                False,
                detail=" | ".join(problems[:4]),
            )
        return GateResult(
            "assembly_measurements_resolve",
            "T0",
            True,
            detail=f"{len(meas)} measurement rows resolve",
        )

    @gate("assembly_noise_declared", "T0")
    def g_noise():
        problems = []
        for _, row in obs.iterrows():
            if pd.isna(row.get("noiseFormula")) or str(row.get("noiseFormula")) == "":
                problems.append(f"{row['observableId']}: no noiseFormula")
            if (
                pd.isna(row.get("noiseDistribution"))
                or str(row.get("noiseDistribution")) == ""
            ):
                problems.append(f"{row['observableId']}: no noiseDistribution")
        if problems:
            return GateResult(
                "assembly_noise_declared", "T0", False, detail=" | ".join(problems[:4])
            )
        return GateResult(
            "assembly_noise_declared",
            "T0",
            True,
            detail="every observable declares noise formula + distribution",
        )

    @gate("assembly_parameters_sane", "T0")
    def g_par():
        problems = []
        est = par[par["estimate"] == 1]
        for _, row in est.iterrows():
            lb, ub = row.get("lowerBound"), row.get("upperBound")
            if (
                pd.isna(lb)
                or pd.isna(ub)
                or not np.isfinite([lb, ub]).all()
                or lb >= ub
            ):
                problems.append(f"{row['parameterId']}: unusable bounds [{lb}, {ub}]")
            if row.get("parameterScale") not in ("lin", "log", "log10"):
                problems.append(
                    f"{row['parameterId']}: bad scale {row.get('parameterScale')!r}"
                )
        formula_syms = set()
        for _, row in obs.iterrows():
            formula_syms |= symbols(row["observableFormula"]) | symbols(
                row.get("noiseFormula", "")
            )
        # A parameter referenced through a PEtab placeholder appears in a
        # measurement COLUMN, not in the formula — the formula holds
        # `noiseParameter1_<obs>` / `observableParameter1_<obs>` instead. Both
        # columns are `;`-separated lists when an observable has more than one
        # (a scaling AND an offset), so split before comparing or a
        # legitimately-used pair reads as two orphans.
        for col in ("noiseParameters", "observableParameters"):
            if col in meas.columns:
                for cell in meas[col].dropna().astype(str):
                    formula_syms |= {
                        tok.strip() for tok in cell.split(";") if tok.strip()
                    }
        # A parameter that a CONDITION assigns to a model parameter
        # (`STAT1_tot -> STAT1_tot_Bcell`, PEtab's parameter-valued override)
        # appears in the condition table and nowhere else; it is no orphan.
        for col in cond.columns:
            if col in ("conditionId", "conditionName"):
                continue
            for cell in cond[col].dropna():
                if isinstance(cell, str):
                    formula_syms |= symbols(cell)
        orphans = tables.petab_param_ids - tables.model_entities - formula_syms
        if orphans:
            problems.append(
                f"estimated/table parameters appear nowhere (model or formulas): {sorted(orphans)}"
            )
        if problems:
            return GateResult(
                "assembly_parameters_sane", "T0", False, detail=" | ".join(problems[:4])
            )
        return GateResult(
            "assembly_parameters_sane",
            "T0",
            True,
            detail=f"{int((par['estimate'] == 1).sum())} estimated parameters, "
            f"all bounded and scaled",
        )

    @gate("assembly_connected", "T0")
    def g_connected():
        """No piece of the model is unobserved: every component of its species
        graph holds a species an observable reads, and every quantity the
        condition table varies reaches one of them (`connectivity`). The
        anchors are read from the observable formulas through the model's
        assignment rules; a quantity a formula reads itself reaches that
        readout without the model."""
        from octomod.workflow_modules.model import connectivity

        species = set(connectivity.species_graph(tables.sbml)["species"])
        anchors: set[str] = set()
        read_by_formula: set[str] = set()
        no_species: list[str] = []
        for oid, formula in zip(
            obs["observableId"].astype(str), obs["observableFormula"], strict=True
        ):
            reads = connectivity.formula_reads(tables.sbml, str(formula))
            read_by_formula |= reads
            if reads & species:
                anchors |= reads & species
            else:
                no_species.append(oid)
        varied = set(varied_columns(cond))
        direct = sorted((varied & read_by_formula) - species)
        res = connectivity.assembly_result(
            tables.sbml, anchors, varied - read_by_formula
        )
        notes = []
        if no_species:
            notes.append(
                f"{len(no_species)} observable(s) read no species of the model "
                f"and anchor nothing: {', '.join(no_species[:4])}"
                + (f", … and {len(no_species) - 4} more" if len(no_species) > 4 else "")
            )
        if direct:
            notes.append(
                f"varied and read by an observable formula itself: {', '.join(direct)}"
            )
        if notes:
            res.detail = (" | " if not res.passed else "; ").join([res.detail, *notes])
        return res

    # A THRESHOLD at S3 informs, it never blocks: `assembly_dof` is a ratio against
    # a declared number and `assembly_magnitude_reconciliation` compares simulations
    # at NOMINAL parameters, so both print on the cost card as information.
    # What blocks at S3 is T0 structure and `assembly_preequilibration`.
    @gate("assembly_dof", "T1")
    def g_dof():
        n_est = int((par["estimate"] == 1).sum())
        n_data = len(meas)
        max_ratio = float(spec.get("gates.dof.max_par_per_datapoint", 1.0))
        ratio = n_est / max(n_data, 1)
        passed = ratio <= max_ratio
        return GateResult(
            "assembly_dof",
            "T1",
            passed,
            blocking=False,
            value=f"{n_est}/{n_data}",
            threshold=f"<= {max_ratio} par/point",
            detail="degrees-of-freedom check",
        )

    @gate("assembly_magnitude_reconciliation", "T1", integrates=True)
    def g_magnitude():
        """Simulate at nominals, compare per-observable magnitude to the
        measurements. Orders apart with no scaling parameter -> fail (advisory).
        The most common real-world PEtab bug, caught in seconds."""
        max_gap = float(spec.get("gates.magnitude.max_log10_ratio", 2.0))
        problems, notes = [], []
        for obs_id, grp in meas.groupby("observableId"):
            # A median of EXACTLY zero is not a magnitude (its log10 would be the
            # 1e-300 floor). Half-empty series are normal — a phosphorylation
            # state is empty early and full late — so compare against the median
            # of the non-zero measurements, and say so when there are none.
            _abs = np.abs(grp["measurement"].to_numpy(dtype=float))
            _nonzero = _abs[_abs > 0]
            med_meas = float(np.median(_nonzero)) if _nonzero.size else 0.0
            if _nonzero.size == 0:
                notes.append(
                    f"{obs_id}: every measurement is zero — magnitude undefined"
                )
                continue
            sims = []
            for cond_id, cgrp in grp.groupby("simulationConditionId"):
                times = np.sort(cgrp["time"].unique()).astype(float)
                try:
                    sim = tables.simulate_observables(str(cond_id), times)
                except SimError as e:
                    return GateResult(
                        "assembly_magnitude_reconciliation",
                        "T1",
                        False,
                        blocking=False,
                        detail=f"simulation failed under condition " f"{cond_id}: {e}",
                    )
                sims.extend(np.abs(sim[str(obs_id)]).tolist())
            med_sim = float(np.median(sims)) if sims else 0.0
            gap = abs(np.log10(max(med_sim, 1e-300)) - np.log10(max(med_meas, 1e-300)))
            has_scaling = bool(tables.observable_scaling_params(str(obs_id)))
            if gap > max_gap and not has_scaling:
                problems.append(
                    f"{obs_id}: simulated ~{med_sim:.3g} vs measured ~{med_meas:.3g} "
                    f"({gap:.1f} decades apart, over the non-zero measurements) "
                    f"and no scaling parameter present"
                )
            else:
                notes.append(
                    f"{obs_id}: {gap:.2f} decades"
                    + (" (scaling present)" if has_scaling else "")
                )
        if problems:
            return GateResult(
                "assembly_magnitude_reconciliation",
                "T1",
                False,
                blocking=False,
                threshold=max_gap,
                detail=" | ".join(problems),
            )
        return GateResult(
            "assembly_magnitude_reconciliation",
            "T1",
            True,
            blocking=False,
            threshold=max_gap,
            detail="; ".join(notes),
        )

    @gate("assembly_preequilibration", "T1", integrates=True)
    def g_preeq():
        if (
            "preequilibrationConditionId" not in meas.columns
            or meas["preequilibrationConditionId"].dropna().astype(str).eq("").all()
        ):
            return GateResult(
                "assembly_preequilibration",
                "T1",
                True,
                detail="no pre-equilibration declared; skipped",
            )
        problems = []
        for pre_id in sorted(
            set(meas["preequilibrationConditionId"].dropna().astype(str)) - {""}
        ):
            reached, resid = tables.model.steady_state_reached(
                overrides=tables.condition_overrides(pre_id)
            )
            if not reached:
                problems.append(f"{pre_id}: no steady state (residual {resid:.2e})")
        if problems:
            return GateResult(
                "assembly_preequilibration", "T1", False, detail=" | ".join(problems)
            )
        return GateResult(
            "assembly_preequilibration",
            "T1",
            True,
            detail="all pre-equilibration conditions reach steady state",
        )

    @gate("assembly_sensitivity_coverage", "T1", integrates=True)
    def g_sens():
        """Advisory: finite-difference screen — does the data constrain each
        estimated parameter at all? Plus the FIM eigenvalue spectrum (report
        the spectrum, never a rank verdict)."""
        try:
            est = par[par["estimate"] == 1]
            groups = [
                (str(o), str(c), np.sort(g["time"].unique()).astype(float))
                for (o, c), g in meas.groupby(["observableId", "simulationConditionId"])
            ]
            # sigma-only parameters never move a trajectory — screening them
            # for observable sensitivity is trivially "uncovered" noise. A
            # sigma reaches the problem through the noiseParameters column or
            # written straight into noiseFormula; the resolved noise expression
            # carries both, per condition. A symbol the observable formula also
            # names (a scale factor) does move the trajectory and stays in.
            noise_syms: set[str] = set()
            signal_syms: set[str] = set()
            for o, c, _t in groups:
                noise_syms |= symbols(tables.noise_expression(o, c))
                signal_syms |= symbols(tables.observable_expression(o, c))
            sigma_ids = noise_syms - tables.model_entities - signal_syms
            est_ids = [p for p in est["parameterId"].astype(str) if p not in sigma_ids]
            ns0 = tables.nominal_namespace()

            # sigma is evaluated at nominal, the same for every perturbation
            sigmas = [
                np.maximum(tables.sigma_series(o, c, t), 1e-12) for o, c, t in groups
            ]

            def stacked_sim(param_override):
                # one simulation returns every observable of a condition
                sims: dict = {}
                vals = []
                for (o, c, t), sig in zip(groups, sigmas, strict=True):
                    key = (c, t.tobytes())
                    if key not in sims:
                        sims[key] = tables.simulate_observables(
                            c, t, param_override=param_override
                        )
                    vals.extend((sims[key][o] / sig).tolist())
                return np.asarray(vals)

            y0 = stacked_sim(None)
            dlog = 0.05  # decades
            J = np.zeros((len(y0), len(est_ids)))
            uncovered = []
            for j, pid in enumerate(est_ids):
                theta0 = float(ns0.get(pid, 1.0))
                if theta0 == 0:
                    theta0 = 1e-8
                y1 = stacked_sim({pid: theta0 * 10**dlog})
                J[:, j] = (y1 - y0) / dlog
                rel = np.max(np.abs(y1 - y0) / np.maximum(np.abs(y0), 1e-12))
                if rel < 1e-3:
                    uncovered.append(pid)
            eigs = np.linalg.eigvalsh(J.T @ J)
            eigs = np.clip(eigs, 1e-300, None)
            spread = float(np.log10(eigs.max()) - np.log10(eigs.min()))
            detail = (
                f"FIM eigenvalue spectrum spans {spread:.1f} decades; "
                f"uncovered parameters: {uncovered or 'none'}"
            )
            return GateResult(
                "assembly_sensitivity_coverage",
                "T1",
                True,
                blocking=False,
                value={"log10_eig_spread": round(spread, 2), "uncovered": uncovered},
                detail=detail,
                advisory_findings=uncovered,
            )
        except Exception as e:
            return GateResult(
                "assembly_sensitivity_coverage",
                "T1",
                True,
                blocking=False,
                detail=f"screen unavailable: {e}",
            )

    # ORDER IS ATTRIBUTION: the runner stops at the first blocking failure, and
    # that failure names the role that is re-asked. The checks that read one
    # agent's block run first and say WHICH block; petablint — a structural
    # catch-all over tables the engine wrote — runs after them, so a petablint
    # failure that survives the specific checks is the engine's own and goes
    # to a person, not to an agent.
    out = [
        g_formulas,
        g_obs,
        # after the resolve check, so an unknown symbol is named as one
        g_sigma,
        g_cond,
        g_noise,
        g_par,
        g_meas,
        # after every resolve check, so the graph is read on tables whose
        # names all exist; before petablint, because it names its author
        g_connected,
        g_lint,
        g_dof,
        g_magnitude,
        g_preeq,
        g_sens,
    ]
    # As in sim_gates: one loop over the list the runner walks, so a gate
    # cannot be marked integrating and left unwired.
    for fn in out:
        if getattr(fn, "integrates", False):
            fn.solver_settings = _settings
    return out
