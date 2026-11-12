"""Two cache keys, and what each one is allowed to notice.

The C++ build does not depend on the parameter table; with one key, candidates over a shared
structure would share a problem and inherit each other's free set and fixed values.

  1. a change the compiler sees moves both keys;
  2. a change only the runtime sees moves the problem key and not the compile key;
  3. on `toy_phos_petab`, a second parameter table reuses the compile and matches a fresh build.

    uv run python tests/compile_cache_unit.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.workflow_modules.assembly import petab_io  # noqa: E402
from octomod.workflow_modules.estimation.problem import (  # noqa: E402
    COMPILED_TABLES,
    RUNTIME_TABLES,
    compile_content_hash,
    problem_content_hash,
)

SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m"/>
</sbml>
"""


def scratch(**tables: str) -> petab_io.PetabInput:
    """A minimal PEtab-shaped input (the problem is in memory, and the
    hashes read its tables and SBML, not PEtab semantics). A keyword names a
    table whose content is changed; `sbml=` replaces the SBML."""
    sbml = tables.pop("sbml", SBML)

    def table(name: str) -> pd.DataFrame:
        return pd.DataFrame({"id": [tables.get(name, f"# {name}")]})

    return petab_io.PetabInput(
        sbml=sbml, **{name: table(name) for name in (*COMPILED_TABLES, *RUNTIME_TABLES)}
    )


def main() -> int:
    base = scratch()
    c0, p0 = compile_content_hash(base), problem_content_hash(base)
    check("the two keys are not the same key", c0 != p0, f"{c0} vs {p0}")

    # ---- every table, in both directions --------------------------------
    for name in COMPILED_TABLES:
        inp = scratch(**{name: "CHANGED"})
        c, p = compile_content_hash(inp), problem_content_hash(inp)
        check(
            f"a change to {name} moves the compile key",
            c != c0 and p != p0,
            f"compile {'moved' if c != c0 else 'STUCK'}, "
            f"problem {'moved' if p != p0 else 'STUCK'}",
        )
    for name in RUNTIME_TABLES:
        inp = scratch(**{name: "CHANGED"})
        c, p = compile_content_hash(inp), problem_content_hash(inp)
        check(
            f"a change to {name} moves ONLY the problem key",
            c == c0 and p != p0,
            f"compile {'STUCK (right)' if c == c0 else 'moved (wrong)'}, "
            f"problem {'moved (right)' if p != p0 else 'STUCK (wrong)'}",
        )

    # ---- the SBML is the model, so it moves both ------------------------
    inp = scratch(sbml=SBML.replace('id="m"', 'id="other"'))
    check(
        "a change to the SBML moves both keys",
        compile_content_hash(inp) != c0 and problem_content_hash(inp) != p0,
    )

    # ---- the parameter table is the ONLY runtime table ------------------
    #      (a table added later defaults to being treated as compiled, which is
    #      the safe side of the mistake, but it must be a deliberate choice)
    check(
        "the runtime table set is exactly the parameter table",
        RUNTIME_TABLES == ("parameters",),
        f"{RUNTIME_TABLES}",
    )
    check(
        "the observable table is compiled (formulas and noise ARE compiled)",
        "observables" in COMPILED_TABLES,
    )

    # ---- and the claim itself, on a real problem ------------------------
    src = REPO / "testcase" / "toy_phos_petab" / "supplied" / "petab"
    if not (src / "problem.yaml").exists():
        check("the static PEtab fixture is present", False, f"missing {src}")
    else:
        # the fixture is an INPUT on disk; the problem is built in memory
        inp_a = petab_io.from_dir(src)
        par = inp_a.parameters.copy()
        # fix the last estimated parameter: exactly the shape of a supermodel
        # axis switched OFF
        target = str(par[par.estimate == 1].parameterId.iloc[-1])
        cache: dict = {}
        from octomod.workflow_modules.estimation.problem import build_problem

        prob_a, pp_a, t_a = build_problem(inp_a, cache)
        n_free_a = len(prob_a.x_free_indices)

        par.loc[par.parameterId == target, "estimate"] = 0
        inp_b = inp_a.with_tables(parameters=par)
        t0 = time.perf_counter()
        prob_b, pp_b, compile_b = build_problem(inp_b, cache)
        t_b = time.perf_counter() - t0

        check(
            "the same structure with a different parameter table is a NEW problem",
            len(prob_b.x_free_indices) == n_free_a - 1
            and target not in [prob_b.x_names[i] for i in prob_b.x_free_indices],
            f"free {n_free_a} -> {len(prob_b.x_free_indices)}, {target} fixed",
        )
        check(
            "and it did NOT recompile",
            compile_b < 1.0,
            f"{compile_b:.2f}s of compile (first build reported {t_a:.2f}s)",
        )
        print(f"    build wall: first {t_a:.2f}s, second {t_b:.2f}s")

        # the value, not just the shape: a right free set over a stale module
        # would look like a pass
        import numpy as np

        nom = pp_b.x_nominal_scaled
        free = [nom[i] for i in prob_b.x_free_indices]
        shared_val = float(prob_b.objective(free))
        shared_grad = np.asarray(prob_b.objective(free, sensi_orders=(1,)))
        fresh, _, _ = build_problem(inp_b, {})  # same problem, fresh in-memory cache
        fresh_val = float(fresh.objective(free))
        fresh_grad = np.asarray(fresh.objective(free, sensi_orders=(1,)))
        check(
            "the shared module gives the same objective as a fresh build",
            np.isclose(shared_val, fresh_val, rtol=0, atol=1e-9),
            f"{shared_val!r} vs {fresh_val!r}",
        )
        check(
            "and the same gradient — what the optimiser actually walks on",
            np.allclose(shared_grad, fresh_grad, rtol=0, atol=1e-9),
            f"max |d| = {float(np.max(np.abs(shared_grad - fresh_grad))):.2e}",
        )

    print()
    return finish(
        "COMPILE CACHE", "COMPILE CACHE OK — each key notices exactly what it should"
    )


if __name__ == "__main__":
    raise SystemExit(main())
