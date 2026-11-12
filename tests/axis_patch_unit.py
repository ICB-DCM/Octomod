"""Axis Antimony patches: comments are prose, and a patch may be a list.

  1. a reaction replaced by a comment line does not have the comment read as symbols;
  2. an axis that removes several reactions sends a list of patches, and every reader takes it.

    uv run python tests/axis_patch_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import FAILS, check  # noqa: E402

from octomod.workflow_modules.model import (  # noqa: E402
    antimony_text,
    model_space,
    supermodel,
)

BASE = """model cell
  R1: A -> B; k1*A;
  R2: B -> C; k2*B;
  R3: C -> ; k3*C;
  A = 1; B = 0; C = 0; k1 = 0.5; k2 = 0.2; k3 = 0.1;
end
"""


def main() -> int:
    print("comments are not symbols")
    removal = {
        "id": "no_r1",
        "on_antimony_patch": {
            "replace_reaction": "R1",
            "with": "  // R1 removed (axis no_r1 on): A is only a tracer pool",
        },
    }
    missing = model_space.undeclared_symbols(BASE, removal)
    check("comment prose is not read as symbols", missing == [], f"got {missing}")
    for style in ("# R1 removed, axis on", "/* R1 removed, axis on */"):
        ax = {"id": "x", "on_antimony_patch": {"replace_reaction": "R1", "with": style}}
        got = model_space.undeclared_symbols(BASE, ax)
        check(f"comment style {style[:2]!r} stripped", got == [], f"got {got}")
    real = {
        "id": "typo",
        "on_antimony_patch": {
            "replace_reaction": "R1",
            "with": "R1: A -> B; kx*A; // note",
        },
    }
    got = model_space.undeclared_symbols(BASE, real)
    check("a real undeclared symbol is still caught", got == ["kx"], f"got {got}")
    ant, ok = model_space.apply_patch(BASE, removal["on_antimony_patch"])
    check("a comment replacement removes the reaction", ok and "R1:" not in ant)

    print("a patch may be a list of steps")
    prune = {
        "id": "prune",
        "on_antimony_patch": [
            {"replace_reaction": "R2", "with": "  // R2 removed (axis prune on)"},
            {"replace_reaction": "R3", "with": "  // R3 removed (axis prune on)"},
        ],
    }
    try:
        got = model_space.undeclared_symbols(BASE, prune)
        check("list patch: symbol check runs", got == [], f"got {got}")
    except Exception as e:  # a reader that assumes one dict raises here
        check("list patch: symbol check runs", False, f"{type(e).__name__}: {e}")
    ant, ok = model_space.apply_patch(BASE, prune["on_antimony_patch"])
    check(
        "list patch: every step applied",
        ok and "R2:" not in ant and "R3:" not in ant and "R1:" in ant,
    )
    bad = [
        {"replace_reaction": "R2", "with": "  // R2 removed"},
        {"replace_reaction": "R9", "with": "R9: C -> ; k3*C;"},
    ]
    ant, ok = model_space.apply_patch(BASE, bad)
    check("list patch: all or nothing", not ok and ant == BASE)
    ant, ok = model_space.apply_patch(BASE, [])
    check("empty list does not apply", not ok and ant == BASE)
    check(
        "replaced_reactions lists every step",
        supermodel.replaced_reactions(prune) == ["R2", "R3"],
        f"got {supermodel.replaced_reactions(prune)}",
    )
    check(
        "replaced_reactions keeps the one-dict form",
        supermodel.replaced_reactions(removal) == ["R1"],
    )

    print("interference across list patches is still refused")
    other = {
        "id": "r3_swap",
        "on_antimony_patch": {"replace_reaction": "R3", "with": "R3: C -> ; k3*C*C;"},
        "adds_parameters": [],
    }
    with_par = [
        dict(
            a,
            adds_parameters=[
                {
                    "id": f"s_{a['id']}",
                    "lb": 0.0,
                    "ub": 1.0,
                    "nominal_value": 0.5,
                    "neutral_value": 0.0,
                    "scale": "lin",
                    "estimate": True,
                }
            ],
        )
        for a in (prune, other)
    ]
    parts = supermodel.partition(with_par)
    sep = {str(a.get("id")) for a in parts.get("separate", [])}
    check(
        "two axes replacing R3 (one via a list) are not composed",
        {"prune", "r3_swap"} <= sep,
        f"separate={sorted(sep)}",
    )

    print("a draft's space replaces the previous draft's")
    from octomod.orchestration.ledger import Ledger
    from tests._record import rnd, temp_record

    class FakeCtx:
        def __init__(self, root):
            self.root = root
            self.round_idx = 0
            self.ledger = Ledger(root)

        @property
        def round(self):
            return rnd(self.root, 0)

        @property
        def agent_calls(self):
            return self.round / "agent_calls"

    with temp_record() as root:
        ctx = FakeCtx(root)
        stale = [
            {
                "id": "old",
                "reason": "stale",
                "module": "model",
                "declared_by": "construction",
            },
            {
                "id": "obs",
                "reason": "kept",
                "module": "assembly",
                "declared_by": "assembly",
            },
        ]
        model_space.dropped_path(ctx).put(stale)
        model_space.space_path(ctx).put([{"id": "old_axis"}])
        reply = {
            "antimony": BASE,
            "parameters": [{"id": "k1"}, {"id": "k2"}, {"id": "k3"}],
            "model_space": [removal, prune],
        }
        axes = model_space.record_axes(ctx, reply)
        ids = [a["id"] for a in axes]
        check(
            "both removal axes survive validation",
            ids == ["no_r1", "prune"],
            f"got {ids}",
        )
        rows = model_space.dropped_path(ctx).get()
        check(
            "the previous draft's S1 drops are cleared, other modules' kept",
            [r["id"] for r in rows] == ["obs"],
            f"got {[r['id'] for r in rows]}",
        )
        check(
            "the space on disk is this draft's",
            [a["id"] for a in model_space.space_path(ctx).get()] == ["no_r1", "prune"],
        )
        model_space.record_axes(
            ctx, {"antimony": BASE, "parameters": [], "model_space": []}
        )
        check(
            "a draft with no axes leaves no stale space behind",
            not model_space.space_path(ctx).exists(),
        )

    print("a resume recovers a space that was never recorded, and can be redrafted")
    with temp_record() as root:
        ctx = FakeCtx(root)
        (ctx.agent_calls.child("construction") / "reply").put(reply)
        axes, construction = model_space.axes_for_gate(ctx, None)
        check(
            "the scope gate re-validates the saved reply when the space is missing",
            [a["id"] for a in axes] == ["no_r1", "prune"] and construction is not None,
            f"got {[a['id'] for a in axes]}",
        )
        check(
            "and records it for the next resume", model_space.space_path(ctx).exists()
        )
        axes2, construction2 = model_space.axes_for_gate(ctx, None)
        check(
            "a resume with the space on disk reads it back, no reply in hand",
            [a["id"] for a in axes2] == ["no_r1", "prune"] and construction2 is None,
        )
    src = (REPO / "octomod" / "workflow_modules" / "model" / "engine.py").read_text()
    j = src.index("return _run_single(ctx, model, t_end, author)")
    check(
        "a redraft on the resumed path is caught, not raised past the draft loop",
        "except _hr.RedraftRequested" in src[j : j + 200],
    )
    check(
        "the caught redraft reaches the agent as human feedback",
        "_take_human_redraft(ctx, context, redraft)" in src,
    )
    g = src.index('"Is this the right model scope to spend compute on?"')
    tail = src[g : src.index("= _resolve_search(", g)]
    check(
        "the axes scope gate honours `redraft:` before reading the note as axes",
        '_raise_if_redraft_asked(ctx, scope_note, "model_scope")' in tail,
    )

    print("a constant an axis orphans is not estimated in that structure")
    pars = [
        {"id": k, "lb": 1e-12, "ub": 1e8, "nominal_value": 0.1, "estimate": True}
        for k in ("k1", "k2", "k3")
    ]
    zero_r2 = {
        "id": "zero_r2",
        "on_antimony_patch": {"replace_reaction": "R2", "with": "R2: B -> C; 0;"},
    }
    models = model_space.enumerate_models(BASE, pars, [zero_r2], 8, t_end=10.0)
    by_id = {m["model_id"]: m for m in models}

    def est(m: dict) -> set[str]:
        return {p["id"] for p in m["parameters"] if p.get("estimate", True)}

    check(
        "base estimates all three",
        est(by_id["base"]) == {"k1", "k2", "k3"},
        f"got {sorted(est(by_id['base']))}",
    )
    check(
        "the R2-removed model does not estimate k2",
        est(by_id["zero_r2"]) == {"k1", "k3"},
        f"got {sorted(est(by_id['zero_r2']))}",
    )
    check(
        "n_estimated follows",
        by_id["zero_r2"]["n_estimated"] == by_id["base"]["n_estimated"] - 1,
        f"{by_id['zero_r2']['n_estimated']} vs {by_id['base']['n_estimated']}",
    )
    check(
        "a declaration is not a use",
        "k2"
        not in antimony_text.used_symbols("model m\n R2: B -> C; 0;\n k2 = 0.2;\nend"),
    )
    check(
        "a rate law is a use",
        "k2"
        in antimony_text.used_symbols(
            "model m\n R2: B -> C; k2*B; // k9\n k2 = 0.2;\nend"
        ),
    )
    check(
        "a comment is not a use",
        "k9"
        not in antimony_text.used_symbols("model m\n R2: B -> C; k2*B; // k9\nend"),
    )
    base_unused = [{"id": "kx", "estimate": True}]
    check(
        "a constant the base never used is left alone",
        supermodel.fix_orphaned(BASE, BASE, base_unused)[0]["estimate"] is True,
    )

    print("the expansion base is built by the lattice's own recipe")
    ant, params, ok = supermodel.build_structure(
        BASE, pars, [zero_r2], nominal_hints={"k1": 0.9, "k3": None}
    )
    by_id = {p["id"]: p for p in params}
    check("the decided patch is applied", ok and "R2: B -> C; 0;" in ant)
    check(
        "the constant it orphaned is fixed, not estimated",
        by_id["k2"]["estimate"] is False and by_id["k2"].get("orphaned_by_structure"),
    )
    check("fitted values survive as start hints", by_id["k1"]["nominal_value"] == 0.9)
    check(
        "a hint of None leaves the table's nominal", by_id["k3"]["nominal_value"] == 0.1
    )
    osrc = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    c = osrc.index("def _carry_undecided(")
    body = osrc[c : osrc.index("\n    def ", c + 10)]
    check(
        "the expansion path uses that recipe, not a copy of it",
        "_sm.build_structure(" in body and "declared_axes(self.ctx)" in body,
    )
    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}):")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("axis patch unit: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
