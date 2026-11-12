"""Cheap SBML simulation via roadrunner (no compilation), plus observable
formula evaluation.

Used by the pre-compile gate ladder and by ensemble prediction, which must
answer in seconds; the AMICI path sits behind the human cost gate. Condition
overrides are applied to global parameters and species initial values by id;
events and per-condition observable parameters are not supported. A
steady-state measurement (PEtab's time `inf`) is read where a long simulation
settles (`RRModel.settled_values`).
"""

from __future__ import annotations

import math

import numpy as np


class SimError(Exception):
    pass


_EVAL_FUNCS = {
    "exp": np.exp,
    "log": np.log,
    "ln": np.log,  # the spelling sympy/PEtab/libSBML share
    "log10": np.log10,
    "log2": np.log2,
    "sqrt": np.sqrt,
    "abs": np.abs,
    "min": np.minimum,
    "max": np.maximum,
    "pow": np.power,
    "pi": math.pi,
}


def eval_formula(formula: str, namespace: dict):
    """Evaluate a PEtab-style math expression against a namespace of
    numbers / numpy arrays. '^' is translated to '**'. Raises SimError with
    the offending symbol on unresolved references — that error message is a
    gate's evidence."""
    expr = str(formula).replace("^", "**")
    ns = dict(_EVAL_FUNCS)
    ns.update(namespace)
    try:
        return eval(compile(expr, "<formula>", "eval"), {"__builtins__": {}}, ns)
    except NameError as e:
        raise SimError(f"formula {formula!r}: unresolved symbol ({e})") from e
    except Exception as e:
        raise SimError(f"formula {formula!r}: {e}") from e


def _assignment_rule_targets(sbml: str) -> set[str]:
    """Ids assigned by an SBML assignmentRule — quantities that are FUNCTIONS
    of the state and therefore have a time course, however they are declared.
    PySB emits every observable as a parameter of this kind."""
    import libsbml

    doc = libsbml.readSBMLFromString(sbml)
    model = doc.getModel()
    if model is None:
        raise SimError("libsbml could not parse the SBML when listing rules")
    return {
        str(model.getRule(i).getVariable())
        for i in range(model.getNumRules())
        if model.getRule(i).isAssignment()
    }


def _import_roadrunner():
    """`import roadrunner`, with libpython preloaded if the loader cannot find
    it on its own.

    roadrunner's extension links libpython by soname. A uv-managed
    (python-build-standalone) interpreter keeps that library inside its own
    install, off the loader path, so on Linux the import can fail with "cannot
    open shared object file". Setting `LD_LIBRARY_PATH` in-process is too late;
    dlopening the library sysconfig names with RTLD_GLOBAL is not.
    """
    try:
        import roadrunner

        return roadrunner
    except ImportError as first:
        if "libpython" not in str(first):
            raise
        import ctypes
        import os
        import sysconfig

        libdir = sysconfig.get_config_var("LIBDIR")
        soname = sysconfig.get_config_var("INSTSONAME") or sysconfig.get_config_var(
            "LDLIBRARY"
        )
        cand = os.path.join(libdir or "", soname or "")
        if not (libdir and soname and os.path.exists(cand)):
            raise
        ctypes.CDLL(cand, mode=ctypes.RTLD_GLOBAL)
        import roadrunner

        return roadrunner


class RRModel:
    """A loaded roadrunner instance with reset/override/simulate helpers."""

    # roadrunner's own defaults (measured on roadrunner 2.10.0), so a reader
    # can see what the declared tolerances change from
    RR_DEFAULTS = {"atol": 1e-12, "rtol": 1e-6}
    _SETTING_NAMES = {"atol": "absolute_tolerance", "rtol": "relative_tolerance"}

    def __init__(self, sbml: str, tolerances: dict | None = None):
        """`tolerances` is `simulation.roadrunner` from the workflow spec.

        None keeps roadrunner's installed defaults, which makes a gate verdict
        depend on the roadrunner version; pass the spec block wherever one is
        in reach.
        """
        roadrunner = _import_roadrunner()

        try:
            self.rr = roadrunner.RoadRunner(sbml)
        except Exception as e:
            raise SimError(f"roadrunner failed to load SBML: {e}") from e
        self.tolerances = self._apply_tolerances(tolerances)
        # `resetToOrigin` keeps an initial value set through `init([X])` — and
        # with it the loss of X's initial assignment — for every later
        # simulation; the state saved here has both, and is loaded back before
        # a simulation that does not set X again (roadrunner 2.10)
        self._origin_state = self.rr.saveStateS()
        self._init_overridden: set[str] = set()
        self.species_ids = list(self.rr.model.getFloatingSpeciesIds())
        self.parameter_ids = list(self.rr.model.getGlobalParameterIds())
        # Boundary species (`$E` in Antimony) are not floating species but can
        # be set, overridden or referenced: they join `entity_ids`, not
        # `species_ids` (the state the conservation/non-negativity screens check).
        self.boundary_ids = list(self.rr.model.getBoundarySpeciesIds())
        self.entity_ids = (
            list(self.species_ids) + list(self.boundary_ids) + list(self.parameter_ids)
        )
        # Parameters driven by an assignment rule (PySB writes every observable
        # this way) are functions of the state and need a time course. Read
        # from the SBML: roadrunner's `getAssignmentRuleIds` varies by version.
        self.assignment_ids = [
            p for p in self.parameter_ids if p in _assignment_rule_targets(sbml)
        ]
        # constants keep their scalar reading; only the driven ones need a path
        self.dynamic_ids = list(self.species_ids) + list(self.assignment_ids)

    def _apply_tolerances(self, tolerances: dict | None) -> dict:
        """Set the declared tolerances, then read back what the integrator holds.

        Raises SimError for an unknown key or a value that did not take; the
        returned dict is what the integrator actually has, which the gate
        verdict records.
        """
        integ = self.rr.getIntegrator()
        want = {k: v for k, v in (tolerances or {}).items() if v is not None}
        unknown = sorted(set(want) - set(self._SETTING_NAMES))
        if unknown:
            raise SimError(
                f"unknown roadrunner tolerance key(s) {unknown}; "
                f"legal: {sorted(self._SETTING_NAMES)}"
            )
        for key, value in want.items():
            name = self._SETTING_NAMES[key]
            integ.setValue(name, float(value))
            got = float(integ.getValue(name))
            if got != float(value):
                raise SimError(
                    f"roadrunner ignored {key}={value!r}: the integrator "
                    f"reports {name}={got!r} after the set"
                )
        # kept, so reloading the origin state can restore what was applied
        self.tolerances = {
            key: float(integ.getValue(name))
            for key, name in self._SETTING_NAMES.items()
        }
        return dict(self.tolerances)

    def _reset_to_origin(self, setting: set[str]) -> None:
        """The model as loaded, for a simulation that overrides `setting`."""
        self.rr.resetToOrigin()
        if self._init_overridden - setting:
            self.rr.loadStateS(self._origin_state)
            # the saved state carries the integrator settings of its moment
            self._apply_tolerances(self.tolerances)
            self._init_overridden = set()

    def _apply_overrides(self, overrides: dict[str, float]) -> None:
        known = set(self.entity_ids)
        unknown = [k for k in overrides if k not in known]
        if unknown:
            raise SimError(
                f"condition override target {unknown[0]!r} is not a model "
                f"parameter, species or boundary species"
            )
        # species first: setting an `init([X])` resets the global parameters
        # set before it, so a parameter override would silently revert
        for key, val in overrides.items():
            if key in self.species_ids or key in self.boundary_ids:
                # override the *initial* value so it survives within this run
                self._init_overridden.add(key)
                try:
                    self.rr.setValue(f"init([{key}])", float(val))
                except Exception:
                    self.rr.setValue(f"init({key})", float(val))
                self.rr.setValue(f"[{key}]", float(val))
        for key, val in overrides.items():
            if key in self.parameter_ids:
                self.rr.setValue(key, float(val))

    def simulate(
        self,
        t_end: float,
        n_points: int = 101,
        overrides: dict[str, float] | None = None,
        times: np.ndarray | None = None,
        initial_state: dict[str, float] | None = None,
    ) -> dict[str, np.ndarray]:
        """Simulate from t=0; returns {'time': ..., species_id: ...}.
        Raises SimError on integration failure.

        Override order matters: an SBML initialAssignment (species = parameter)
        sees a changed parameter only if reset() runs after the override, so
        the sequence is origin -> set species, then globals -> reset -> simulate.
        `initial_state` (species -> concentration, e.g. a pre-equilibrated
        state) is set last, so it wins over initial values and assignments."""
        self._reset_to_origin(set(overrides or ()))
        if overrides:
            self._apply_overrides(overrides)
            self.rr.reset()  # re-evaluate initial assignments with new globals
        for key, val in (initial_state or {}).items():
            self.rr.setValue(f"[{key}]", float(val))
        self.rr.timeCourseSelections = (
            ["time"] + [f"[{s}]" for s in self.species_ids] + list(self.assignment_ids)
        )
        try:
            if times is not None:
                times = np.asarray(times, dtype=float)
                res = self.rr.simulate(times=times)
            else:
                res = self.rr.simulate(0.0, float(t_end), int(n_points))
        except Exception as e:
            raise SimError(f"integration failed: {e}") from e
        data = np.asarray(res)
        if not np.all(np.isfinite(data)):
            raise SimError("integration produced non-finite values")
        out = {"time": data[:, 0]}
        for i, name in enumerate(self.species_ids + self.assignment_ids):
            out[name] = data[:, i + 1]
        return out

    def steady_state(
        self, overrides: dict[str, float] | None = None, t_probe: float = 1e5
    ) -> dict[str, float]:
        """The state a long simulation under `overrides` ends in.

        The state a pre-equilibrated condition starts from. Whether it IS a
        steady state is `steady_state_reached`'s question, asked at S3."""
        traj = self.simulate(t_probe, n_points=51, overrides=overrides)
        return {s: float(traj[s][-1]) for s in self.species_ids}

    def settled_values(
        self,
        overrides: dict[str, float] | None = None,
        initial_state: dict[str, float] | None = None,
        t_probe: float = 1e5,
        rel_tol: float = 1e-4,
        extend: float = 100.0,
    ) -> dict[str, float]:
        """Every species and assignment-rule quantity where a long simulation
        under `overrides` ends: what a steady-state measurement (PEtab's
        `time = inf`) is compared against.

        AMICI post-equilibrates from the last finite time point until the
        state settles; with no events here, that is the state this reaches
        from the condition's own start (`initial_state`, e.g. a
        pre-equilibrated one). Whether it did settle is AMICI's verdict,
        reported at the probe (`solver_probe.steady_state_report`).

        AMICI integrates for as long as settling takes, so a state still
        moving at `t_probe` (a slow system) is followed `extend` times further
        before it is read. When that run fails (unbounded growth) the
        `t_probe` read stands; a state that never settles (an oscillator)
        reads an arbitrary point either way, and AMICI's post-equilibration
        fails there, which the budget card names. A state that has settled by
        `t_probe` is read exactly as before."""
        traj = self.simulate(
            t_probe, n_points=51, overrides=overrides, initial_state=initial_state
        )
        if self._last_step_change(traj) > rel_tol:
            try:
                traj = self.simulate(
                    t_probe * extend,
                    n_points=51,
                    overrides=overrides,
                    initial_state=initial_state,
                )
            except SimError:
                pass  # the t_probe read stands
        return {name: float(traj[name][-1]) for name in self.dynamic_ids}

    def _last_step_change(self, traj: dict[str, np.ndarray]) -> float:
        """The largest relative change over a trajectory's last sample
        interval. Each quantity is scaled by its own size along the run, so
        one that ends at zero does not turn rounding noise into a large
        relative change."""
        worst = 0.0
        for name in self.dynamic_ids:
            x = traj[name]
            scale = max(abs(x[-1]), 1e-6 * float(np.max(np.abs(x))), 1e-12)
            worst = max(worst, abs(x[-1] - x[-2]) / scale)
        return worst

    def steady_state_reached(
        self,
        overrides: dict[str, float] | None = None,
        t_probe: float = 1e5,
        rel_tol: float = 1e-6,
    ) -> tuple[bool, float]:
        """Pre-equilibration check: simulate long, compare last two points."""
        traj = self.simulate(t_probe, n_points=201, overrides=overrides)
        rel_change = 0.0
        for s in self.species_ids:
            x = traj[s]
            scale = max(abs(x[-1]), 1e-12)
            rel_change = max(rel_change, abs(x[-1] - x[-2]) / scale)
        return rel_change < rel_tol, rel_change

    def parameter_values(self) -> dict[str, float]:
        """Every NAMED constant a formula may refer to: global parameters and
        boundary species. A boundary species is a fixed amount, so a formula
        referring to one needs its value exactly as it needs a parameter's."""
        names = list(self.parameter_ids) + list(self.boundary_ids)
        return {p: float(self.rr.getValue(p)) for p in names}
