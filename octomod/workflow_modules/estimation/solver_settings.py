"""Turn declared solver settings into calls on live AMICI solver/model objects.

A declared key that reaches no setter raises rather than being skipped, and
every write is read back (a setter that does not throw has not necessarily
taken the value). `simulation.amici` and `estimation.refit_presets` name the
same keys through this one map, so a key cannot work at one entry point and be
dead at the other.
"""

from __future__ import annotations

# key -> ((snake_case stem, camelCase stem), cast). AMICI moved from camelCase
# to snake_case, so both spellings are tried; if neither exists, applying raises.
_SOLVER: dict[str, tuple[tuple[str, str], type]] = {
    "atol": (("absolute_tolerance", "AbsoluteTolerance"), float),
    "rtol": (("relative_tolerance", "RelativeTolerance"), float),
    "maxsteps": (("max_steps", "MaxSteps"), int),
    "sens_atol": (("absolute_tolerance_fsa", "AbsoluteToleranceFSA"), float),
    "sens_rtol": (("relative_tolerance_fsa", "RelativeToleranceFSA"), float),
    "newton_maxsteps": (("newton_max_steps", "NewtonMaxSteps"), int),
    "newton_damping_factor_lower_bound": (
        ("newton_damping_factor_lower_bound", "NewtonDampingFactorLowerBound"),
        float,
    ),
    "steadystate_tol_factor": (
        ("steady_state_tolerance_factor", "SteadyStateToleranceFactor"),
        float,
    ),
}
# these take an AMICI enum, resolved by name from the spec string
_SOLVER_ENUM = {
    "sensi_method": (("sensitivity_method", "SensitivityMethod"), "SensitivityMethod"),
}
# and this one lives on the MODEL, not the solver
_MODEL_ENUM = {
    "sensitivity_mode": (
        ("steady_state_sensitivity_mode", "SteadyStateSensitivityMode"),
        "SteadyStateSensitivityMode",
    ),
}

ALL_KEYS = tuple(sorted({*_SOLVER, *_SOLVER_ENUM, *_MODEL_ENUM}))


class SolverSettingError(Exception):
    """A declared setting could not be applied. Never swallowed."""


def _bind(obj, stems: tuple[str, str]):
    """The (setter, getter) pair for the first stem the object has, else None.

    The getter is None when the object has only the setter.
    """
    for stem in stems:
        snake = "_" in stem
        set_name = f"set_{stem}" if snake else f"set{stem}"
        get_name = f"get_{stem}" if snake else f"get{stem}"
        if hasattr(obj, set_name):
            return getattr(obj, set_name), getattr(obj, get_name, None)
    return None


def _amici_enum(enum_name: str, value: str):
    import amici.sim.sundials as sd

    enum = getattr(sd, enum_name, None)
    if enum is None:
        raise SolverSettingError(f"this AMICI has no {enum_name} enum")
    member = getattr(enum, str(value), None)
    if member is None:
        # AMICI's enums subclass int, so `dir()` lists int methods too;
        # `__members__` holds only the members.
        legal = sorted(getattr(enum, "__members__", {}))
        raise SolverSettingError(f"{enum_name} has no member {value!r}; legal: {legal}")
    return member


def apply_amici(solver, model, settings: dict) -> dict:
    """Apply `settings`, a flat dict over ALL_KEYS, to a live AMICI solver/model.

    Returns the values read back. `None` leaves a key untouched, so AMICI's own
    default applies. Raises SolverSettingError for an unknown key, a key that
    reaches no setter, or a value that does not read back.
    """
    applied: dict = {}
    for key, value in settings.items():
        if value is None:
            continue
        if key not in ALL_KEYS:
            raise SolverSettingError(
                f"unknown solver setting {key!r}; legal: {list(ALL_KEYS)}"
            )
        if key in _SOLVER:
            stems, cast = _SOLVER[key]
            bound = _bind(solver, stems)
            target, want = "solver", cast(value)
        elif key in _SOLVER_ENUM:
            stems, enum_name = _SOLVER_ENUM[key]
            bound = _bind(solver, stems)
            target, want = "solver", _amici_enum(enum_name, value)
        else:
            stems, enum_name = _MODEL_ENUM[key]
            bound = _bind(model, stems)
            target, want = "model", _amici_enum(enum_name, value)
        if bound is None:
            raise SolverSettingError(
                f"declared setting {key!r} reaches no setter on the AMICI "
                f"{target} (tried set_{stems[0]} and set{stems[1]}): a key in "
                f"the spec that reaches no setter would silently change "
                f"nothing. Fix the map in solver_settings.py."
            )
        setter, getter = bound
        setter(want)
        if getter is None:
            # no getter to confirm with: record what was asked for, and say so
            applied[key] = {"set": value, "unverified": "no getter on this AMICI"}
            continue
        got = getter()
        # Floats compare exactly (a rounded tolerance is not the declared one);
        # enums read back as ints.
        if isinstance(want, float):
            ok = float(got) == float(want)
            applied[key] = float(got)
        else:
            ok = int(got) == int(want)
            applied[key] = int(got)
        if not ok:
            raise SolverSettingError(
                f"AMICI ignored {key}={value!r}: reads back {got!r}"
            )
    return applied


def restore(solver, model, snapshot: dict) -> None:
    """Reset a solver and model to a `read_back` snapshot of their built state.

    A declared `null` never resets a key, so without this a setting applied for
    one problem (e.g. `sensi_method: adjoint`) would stay on a cached solver
    for the next. Enum keys are given as the ints `read_back` records.
    """
    import amici.sim.sundials as sd

    for key, value in snapshot.items():
        if key in _SOLVER:
            stems, cast = _SOLVER[key]
            bound, want = _bind(solver, stems), cast(value)
        elif key in _SOLVER_ENUM:
            stems, enum_name = _SOLVER_ENUM[key]
            bound, want = _bind(solver, stems), getattr(sd, enum_name)(int(value))
        elif key in _MODEL_ENUM:
            stems, enum_name = _MODEL_ENUM[key]
            bound, want = _bind(model, stems), getattr(sd, enum_name)(int(value))
        else:
            continue
        if bound is not None:
            bound[0](want)


def flatten_spec(spec) -> dict:
    """`simulation.amici` (with its steady_state sub-block) as one flat dict."""
    amici = dict(spec.get("simulation.amici") or {})
    steady = dict(amici.pop("steady_state", None) or {})
    return {**amici, **steady}


def read_back(solver, model) -> dict:
    """What the solver and model actually hold, for keys this AMICI has a getter for."""
    out: dict = {}
    for key, (stems, _cast) in _SOLVER.items():
        b = _bind(solver, stems)
        if b and b[1] is not None:
            out[key] = b[1]()
    for key, (stems, _e) in _SOLVER_ENUM.items():
        b = _bind(solver, stems)
        if b and b[1] is not None:
            out[key] = int(b[1]())
    for key, (stems, _e) in _MODEL_ENUM.items():
        b = _bind(model, stems)
        if b and b[1] is not None:
            out[key] = int(b[1]())
    return out
