"""An axis the data did not decide stays live, rather than frozen by ranking.

The tie is synthetic (every stub round's indistinguishable set is a singleton);
the predicate, the carry over real Antimony patches and the ceiling are real.

  1. an axis the indistinguishable set disagrees on is undecided;
  2. with nothing undecided, the winner is the next base exactly;
  3. an undecided axis ON in the winner is dropped from the rebuilt base and carried;
  4. the rebuilt base builds to valid SBML;
  5. with no base on disk the carry falls back to the winner, and says so;
  6. a fitted base-plus-decided candidate is itself the next base;
  7. a decided observation axis goes to the rebuilt base's assembly;
  8. the ceiling keeps the undecided axes first;
  9. the base-choice note form parses, with the engine's own regex.

    uv run python tests/undecided_unit.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.workflow_modules.model import model_space  # noqa: E402
from tests._record import ledger_rows, record_at, rnd, work  # noqa: E402

BASE = """model cell
  R1: A -> B; k1*A;
  R2: B -> ; k2*B;
  A = 1; B = 0; k1 = 0.5; k2 = 0.1;
end
"""
BASE_PAR = [
    {"id": "k1", "lb": 1e-3, "ub": 10.0, "nominal_value": 0.5, "estimate": True},
    {"id": "k2", "lb": 1e-3, "ub": 10.0, "nominal_value": 0.1, "estimate": True},
]

AX_SAT = {
    "id": "saturating_R1",
    "kind": "structure",
    "priority": 1,
    "on_antimony_patch": {
        "replace_reaction": "R1",
        "with": "R1: A -> B; k1*A/(1+A/Km)",
    },
    "adds_parameters": [
        {"id": "Km", "lb": 1e-2, "ub": 100.0, "nominal_value": 1.0, "estimate": True}
    ],
    "frozen": False,
}
AX_ALT = {
    "id": "alt_route",
    "kind": "structure",
    "priority": 2,
    "on_antimony_patch": {"append": "R3: A -> C; k3*A"},
    "adds_parameters": [
        {"id": "k3", "lb": 1e-4, "ub": 1.0, "nominal_value": 0.05, "estimate": True}
    ],
    "frozen": False,
}


class FakeCtx:
    def __init__(self, root):
        self.root = root  # the record's root Node: the run is one file
        self.round_idx = 0
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, 0)


def staged_ctx(with_base: bool = True) -> FakeCtx:
    """A round with its declared space in the record (`space/axes`) and,
    unless told otherwise, its base model and parameters, as a real one is."""
    ctx = FakeCtx(record_at(Path(tempfile.mkdtemp()) / "run"))
    (ctx.round / "space/axes").put([AX_SAT, AX_ALT])
    if with_base:
        (ctx.round / "model/antimony").put_text(BASE)
        (ctx.round / "model/parameters").put(BASE_PAR)
    return ctx


def carry(ctx, report, winner, win_ant, win_par):
    """The orchestrator's own `_carry_undecided`, unbound: the rule, not a copy."""
    from octomod.orchestration.orchestrator import Orchestrator

    class Shim:
        pass

    shim = Shim()
    shim.ctx = ctx
    shim.root = ctx.root
    shim.ledger = ctx.ledger
    return Orchestrator._carry_undecided(shim, report, winner, win_ant, win_par)


def main() -> int:
    # 1 ---- the predicate ------------------------------------------------
    models = [
        {
            "model_id": "saturating_R1+alt_route",
            "axes_on": ["saturating_R1", "alt_route"],
        },
        {"model_id": "saturating_R1", "axes_on": ["saturating_R1"]},
        {"model_id": "alt_route", "axes_on": ["alt_route"]},
        {"model_id": "base", "axes_on": []},
    ]
    check(
        "an axis the set disagrees on is undecided",
        model_space.undecided_axes(models, ["saturating_R1+alt_route", "saturating_R1"])
        == ["alt_route"],
        f"{model_space.undecided_axes(models, ['saturating_R1+alt_route', 'saturating_R1'])}",
    )
    check(
        "an axis the whole set agrees on is NOT undecided",
        model_space.undecided_axes(models, ["saturating_R1+alt_route", "saturating_R1"])
        == ["alt_route"],
    )
    check(
        "a set of one decided everything it contains",
        model_space.undecided_axes(models, ["saturating_R1+alt_route"]) == [],
    )
    check(
        "a set spanning every model leaves both axes undecided",
        model_space.undecided_axes(models, [m["model_id"] for m in models])
        == ["alt_route", "saturating_R1"],
    )
    check(
        "select() reports it, so the round's record carries it",
        model_space.select(
            [
                {
                    "model_id": m["model_id"],
                    "axes_on": m["axes_on"],
                    "n_estimated": 2 + len(m["axes_on"]),
                    "nllh": -100.0 - 0.1 * len(m["axes_on"]),
                    "n_data": 40,
                }
                for m in models
            ],
            "AIC",
            100.0,  # a threshold that makes every model indistinguishable
            0.7,
        )["undecided_axes"]
        == ["alt_route", "saturating_R1"],
    )

    # 2 ---- nothing undecided: the winner seeds the next round -----------
    ctx = staged_ctx()
    carried, ant, par, seed = carry(
        ctx,
        {"discrimination": {"undecided_axes": [], "indistinguishable": ["x"]}},
        "saturating_R1",
        "WINNER ANTIMONY",
        [{"id": "k1", "nominal_value": 9.9}],
    )
    check(
        "with nothing undecided, the base is the winner exactly as before",
        carried == []
        and ant == "WINNER ANTIMONY"
        and par == [{"id": "k1", "nominal_value": 9.9}]
        and seed is None,
        f"carried={carried}; seed={seed}",
    )

    # 3 ---- the UNDECIDED axis is ON in the winner: the hard case --------
    #        (the one a naive implementation quietly skips)
    ctx = staged_ctx()
    winner = "saturating_R1+alt_route"
    win_par = [
        {"id": "k1", "lb": 1e-3, "ub": 10.0, "nominal_value": 0.77, "estimate": True},
        {"id": "k2", "lb": 1e-3, "ub": 10.0, "nominal_value": 0.22, "estimate": True},
        {"id": "Km", "lb": 1e-2, "ub": 100.0, "nominal_value": 3.3, "estimate": True},
        {"id": "k3", "lb": 1e-4, "ub": 1.0, "nominal_value": 0.04, "estimate": True},
    ]
    carried, ant, par, seed = carry(
        ctx,
        {
            "discrimination": {
                "undecided_axes": ["alt_route"],
                "indistinguishable": [winner, "saturating_R1"],
            }
        },
        winner,
        "WINNER ANTIMONY",
        win_par,
    )
    check(
        "no candidate of the round is base-plus-decided here, so it is a rebuild",
        seed == {"candidate": None, "overlay": []},
        f"{seed}",
    )
    check(
        "the undecided axis is carried, marked as such",
        [a["id"] for a in carried] == ["alt_route"]
        and carried[0].get("carried_undecided") is True,
        f"{[a['id'] for a in carried]}",
    )
    check(
        "the rebuilt base KEEPS the decided axis's patch",
        "k1*A/(1+A/Km)" in ant,
        "saturating_R1 was decided (both tied models carry it), so it stays",
    )
    check(
        "and DROPS the undecided axis's patch, so it can be searched again",
        "R3: A -> C" not in ant,
        "alt_route was not decided, so it is not inherited",
    )
    check(
        "the base is rebuilt from the ROUND's base, not from the winner",
        ant != "WINNER ANTIMONY" and "R2: B -> ; k2*B" in ant,
    )
    by_id = {p["id"]: p for p in par}
    check(
        "the winner's FITTED values survive as start hints for what remains",
        by_id["k1"]["nominal_value"] == 0.77 and by_id["Km"]["nominal_value"] == 3.3,
        f"k1={by_id['k1']['nominal_value']} Km={by_id['Km']['nominal_value']}",
    )
    check(
        "the decided axis's parameter is in the base table",
        "Km" in by_id,
        f"{sorted(by_id)}",
    )
    check(
        "the dropped axis's parameter is NOT — it comes back with the axis",
        "k3" not in by_id,
        f"{sorted(by_id)}",
    )
    check(
        "every parameter the rebuilt model uses is declared in it",
        all(f"{pid} =" in ant or f"{pid}=" in ant for pid in by_id),
        f"{[pid for pid in by_id if f'{pid} =' not in ant and f'{pid}=' not in ant]}",
    )
    notes = ledger_rows(ctx.root)
    check(
        "the decision is ledgered, naming the set that failed to settle it",
        any(
            "stay LIVE" in str(n.get("note", ""))
            and "alt_route" in str(n.get("note", ""))
            and "saturating_R1" in str(n.get("note", ""))
            for n in notes
        ),
        next(
            (
                str(n["note"])[:150]
                for n in notes
                if "stay LIVE" in str(n.get("note", ""))
            ),
            "(no note)",
        ),
    )

    # 4 ---- the base model has to still build ----------------------------
    from octomod.gates.build_gates import antimony_to_sbml

    sbml, err = antimony_to_sbml(ant)
    check("the rebuilt base builds to valid SBML", sbml is not None, err)

    # 5 ---- a missing base is a refusal, not a wrong base ----------------
    bare = staged_ctx(with_base=False)  # the space is declared; no base antimony
    assert not (bare.round / "model/antimony").exists()  # no base written
    carried2, ant2, par2, seed2 = carry(
        bare,
        {
            "discrimination": {
                "undecided_axes": ["alt_route"],
                "indistinguishable": [winner, "saturating_R1"],
            }
        },
        winner,
        "WINNER ANTIMONY",
        win_par,
    )
    check(
        "with no base in the record it falls back to the winner and SAYS so",
        carried2 == [] and ant2 == "WINNER ANTIMONY" and seed2 is None,
        f"carried={carried2}",
    )
    notes2 = ledger_rows(bare.root)
    check(
        "and the fallback is ledgered, not silent",
        any("could not be carried" in str(n.get("note", "")) for n in notes2),
    )

    # 5b --- base-plus-decided already FITTED this round is the next base
    #        itself (its files and its fit), not a rebuild
    ctx = staged_ctx()
    member = work(ctx.root, 0, "saturating_R1") / "model"
    (member / "antimony").put_text("MEMBER ANTIMONY")
    (member / "parameters").put([{"id": "k1"}])
    report = {
        "discrimination": {
            "undecided_axes": ["alt_route"],
            "indistinguishable": [winner, "saturating_R1"],
            "candidates": [{"id": winner}, {"id": "saturating_R1"}, {"id": "base"}],
        }
    }
    carried3, ant3, par3, seed3 = carry(ctx, report, winner, "WINNER ANTIMONY", win_par)
    check(
        "the fitted candidate that IS base-plus-decided seeds the next round",
        seed3 == {"candidate": "saturating_R1", "overlay": []}
        and ant3 == "MEMBER ANTIMONY"
        and par3 == [{"id": "k1"}]
        and [a["id"] for a in carried3] == ["alt_route"],
        f"{seed3}",
    )
    (ctx.round / "model/encoding").put(
        {"kind": "supermodel", "absorbed_axes": ["alt_route"]}
    )
    _, ant4, _, seed4 = carry(ctx, report, winner, "WINNER ANTIMONY", win_par)
    check(
        "… but not when the undecided axis was ABSORBED into its structure "
        "(it would carry the axis's terms, and the axis could not be searched again)",
        seed4 == {"candidate": None, "overlay": []} and ant4 != "MEMBER ANTIMONY",
        f"{seed4}",
    )
    AX_OBS = {
        "id": "obs_offset",
        "kind": "observation",
        "priority": 3,
        "on_assembly_patch": {"add_offset": {"observable_id": "obs_B"}},
        "adds_parameters": [],
        "frozen": False,
    }
    ctx = staged_ctx()
    # the axes come from the round's own `space/axes`
    (ctx.round / "space/axes").put([AX_SAT, AX_ALT, AX_OBS])
    winner_obs = "saturating_R1+alt_route+obs_offset"
    _, _, _, seed5 = carry(
        ctx,
        {
            "discrimination": {
                "undecided_axes": ["alt_route"],
                "indistinguishable": [winner_obs, "saturating_R1+obs_offset"],
            }
        },
        winner_obs,
        "WINNER ANTIMONY",
        win_par,
    )
    check(
        "a DECIDED observation axis goes to the rebuilt base's assembly "
        "(rather than vanishing — neither baked in nor re-declared)",
        seed5 == {"candidate": None, "overlay": [AX_OBS["on_assembly_patch"]]},
        f"{seed5}",
    )

    # 6 ---- the ceiling keeps the undecided axes FIRST -------------------
    live = [
        {"id": "new_a", "priority": 1},
        {"id": "new_b", "priority": 2},
        {"id": "alt_route", "priority": 9},
    ]
    kept, dropped = model_space.cap_axes(live, 4, {"alt_route"})
    check(
        "an undecided axis outranks a higher-priority NEW axis under the ceiling",
        [a["id"] for a in kept] == ["alt_route", "new_a"]
        and [a["id"] for a in dropped] == ["new_b"],
        f"kept {[a['id'] for a in kept]}, dropped {[a['id'] for a in dropped]}",
    )

    # 7 ---- the base-choice parse ----------------------------------------
    #        pinned here: `expansion_smoke` cannot answer `base: base` without
    #        breaking the assertion its fixture exists for
    import re as _re

    PARSE = r"\b(?:base|expand_from)\s*[:=]\s*([A-Za-z0-9_+.-]+)"
    cases = {
        "y base: M2_kina": "M2_kina",
        "base=alt_route+sat": "alt_route+sat",
        "expand_from: base": "base",
        "yes, build on it — base: cand_1": "cand_1",
        "  BASE : Mixed_Case-9  ": "Mixed_Case-9",
    }
    for note, want in cases.items():
        m = _re.search(PARSE, note, _re.I)
        check(
            f"the base choice parses out of {note!r}",
            m is not None and m.group(1) == want,
            f"{m.group(1) if m else None} (wanted {want})",
        )
    for note in (
        "y",
        "",
        "looks fine, the basement is flooded",
        "y axes: a, b",
        "n",
    ):
        hit = _re.search(PARSE, note, _re.I)
        check(
            f"no base is read from {note!r}",
            hit is None,
            f"wrongly read {hit.group(1)}" if hit else "nothing read, as it should be",
        )
    in_source = PARSE in (
        REPO / "octomod" / "orchestration" / "orchestrator.py"
    ).read_text().replace("\\\\", "\\")
    check(
        "the engine's regex is the one tested here, not a copy of it",
        in_source,
        "same pattern" if in_source else "orchestrator.py has drifted from this test",
    )

    print()
    return finish(
        "UNDECIDED",
        "UNDECIDED OK — an axis the data did not decide is not frozen by ranking",
    )


if __name__ == "__main__":
    raise SystemExit(main())
