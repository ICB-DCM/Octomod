"""Octomod prototype — a gated, artifact-typed agentic pipeline for
mechanistic model construction and calibration on pyPESTO / AMICI / PEtab.

The orchestrator is code. Agents fill typed holes. Gates are hard stops.
"""

__version__ = "0.1.0"

# when this process began importing the engine — the interpreter's
# start-up (pyPESTO, AMICI, pandas) is seconds of a run's wall that no ledger
# row would otherwise see; the run_start row records the gap as `startup_s`
import time as _time  # noqa: E402

PROCESS_T0 = _time.time()
