"""Which observation parameters pyPESTO's hierarchical estimation may solve
analytically (scaling, offset), and which it must not.

The value is in the refusals, which pyPESTO 0.6.0 does not make itself: a
laplace observable is silently fitted as Gaussian; a scaling solved inner while
its offset stays outer gives a wrong objective with nothing raised (a lone
scaling is exact). Sigma is never marked: an inner log10 sigma raises
NotImplementedError, and the assembly writes sigma rows as log10.
"""

from __future__ import annotations

import re

# What a parameter is marked as, in pyPESTO's own vocabulary.
SCALING, OFFSET, SIGMA = "scaling", "offset", "sigma"


def _is_bare_parameter(formula: str) -> bool:
    """The one noise shape the hierarchical inner solve is derived for: a single
    identifier. A number is excluded too (there is no sigma to solve for), as is
    every other shape `_render_noise` renders."""
    return bool(re.fullmatch(r"[A-Za-z_]\w*", str(formula).strip()))


def marks(
    assembly: dict, spec, scaling_ids: dict[str, list[str]] | None = None
) -> tuple[dict[str, str], list[str]]:
    """({parameter_id: parameterType}, reasons nothing was marked or was skipped).

    `scaling_ids`: the ESTIMATED factor ids the renderer wrote per observable
    (several for `per: timepoint` / `per: condition`, without the pinned one),
    so every inner scaling is marked and a fixed parameter never is. Without
    it, the assembly's `scale_parameter` stem is marked, which is exact for
    `per: observable`.

    Marks are empty when the knob is off, when a noise model is one the library
    mishandles, or when no observable has a supported shape. Each case returns
    a reason for the caller to ledger, so a run never claims a method it did
    not use.
    """
    if not bool(spec.get("estimation.hierarchical", False)):
        return {}, []

    reasons: list[str] = []
    noise_by_obs = {
        str(n.get("observable_id")): n for n in (assembly.get("noise") or [])
    }
    scaling_by_obs = {
        str(s.get("observable_id")): s for s in (assembly.get("scaling") or [])
    }

    laplace = sorted(
        oid
        for oid, n in noise_by_obs.items()
        if str(n.get("distribution", "normal")).lower() == "laplace"
    )
    if laplace:
        return {}, [
            f"hierarchical estimation DISABLED for this problem: observable(s) "
            f"{laplace} declare a laplace noise distribution, and pyPESTO's "
            f"hierarchical package hardcodes the Gaussian likelihood — it would "
            f"fit them as Gaussian and raise nothing. Refused here instead of "
            f"trusting the library to refuse it."
        ]

    # The closed-form inner optimum for a scaling assumes sigma does not depend
    # on the scaled prediction (additive normal noise). Any other noise formula
    # gets a wrong optimum with nothing raised, so only a bare sigma passes.
    unsafe = sorted(
        (oid, str(n.get("formula", "")))
        for oid, n in noise_by_obs.items()
        if not _is_bare_parameter(str(n.get("formula", "")))
    )
    if unsafe:
        shown = ", ".join(f"{oid} ({f!r})" for oid, f in unsafe[:4])
        return {}, [
            f"hierarchical estimation DISABLED for this problem: observable(s) "
            f"{shown} declare a noise formula that is not a bare sigma "
            f"parameter. pyPESTO's hierarchical inner solve handles "
            f"independent ADDITIVE NORMAL noise only — its closed-form optimum for "
            f"a scaling parameter assumes sigma is independent of the scaled "
            f"prediction, which proportional and additive+proportional noise "
            f"both violate. It would return a confidently wrong answer and "
            f"raise nothing. Refused here instead of trusting the library to "
            f"refuse it; the run continues as plain estimation."
        ]

    out: dict[str, str] = {}
    for oid, sc in sorted(scaling_by_obs.items()):
        mode = str(sc.get("mode", "none"))
        sc_par = sc.get("scale_parameter")
        off_par = sc.get("offset_parameter")
        factor_ids = (
            list((scaling_ids or {}).get(oid) or [])
            if scaling_ids is not None and oid in (scaling_ids or {})
            else ([str(sc_par)] if sc_par else [])
        )
        if mode == "factor_offset" and factor_ids and off_par:
            # scaling and offset inner together: the coupled case, exact
            for fid in factor_ids:
                out[fid] = SCALING
            out[str(off_par)] = OFFSET
        elif mode == "factor" and factor_ids:
            # a lone scaling: exact, and the most common shape
            for fid in factor_ids:
                out[fid] = SCALING
        elif mode == "offset" and off_par:
            reasons.append(
                f"{oid}: an offset with no scaling is a cell nobody has "
                f"measured, so it stays an ordinary outer parameter. The "
                f"neighbouring cell (scaling inner, offset outer) is silently "
                f"WRONG in this library version, which is reason enough not to "
                f"guess at this one."
            )
        elif mode not in ("none", ""):
            reasons.append(f"{oid}: unrecognised scaling mode {mode!r}, left outer")

    # sigma: deliberately never marked — see the module docstring
    if any(n.get("estimate_sigma") for n in noise_by_obs.values()):
        reasons.append(
            "sigma parameters stay OUTER: pyPESTO raises NotImplementedError "
            "for a log/log10 inner sigma and the assembly writes them log10, "
            "and the cell measured exact has sigma outside anyway"
        )
    if not out:
        reasons.append(
            "nothing to solve analytically: no observable declares a scaling "
            "or offset this version handles"
        )
    return out, reasons


def enabled_for(parameters) -> bool:
    """Does this PEtab parameter table ask for hierarchical estimation?

    Read from the table rather than passed beside it, so `build_problem` cannot
    be handed a flag that disagrees with the file. `parameterType` is part of
    the problem cache key, not the compile key: a hierarchical and a plain fit
    of one structure share one compiled model.
    """
    return bool(inner_ids(parameters))


# An unmarked cell is blank in the file and comes back from a CSV round-trip as
# NaN, whose str() is the non-empty "nan": every spelling here means unmarked.
_BLANK = {"", "nan", "none", "<na>"}


def inner_ids(parameters) -> list[str]:
    """The parameters this table marks for the inner problem, in table order."""
    if "parameterType" not in getattr(parameters, "columns", []):
        return []
    out = []
    for pid, kind in zip(
        parameters["parameterId"], parameters["parameterType"], strict=False
    ):
        if str(kind).strip().lower() not in _BLANK:
            out.append(str(pid))
    return out
