"""An unfitted observation axis rejoins the search; a human can buy a ruled-out axis.

  1. an unfitted observation axis is carried if the base assembly admits it, else named;
  2. an axis the agent ruled out is not carried by the engine;
  3. `axes: +<id>` buys it over the ruling, ledgered; a structural one meets the ladder;
  4. what cannot be bought is read back as not acted on, with the reason;
  5. the card says what rejoined and offers the form for a ruled-out axis;
  6. the gate is wired: base assembly passed, form on the card, purchase recorded.

    uv run python tests/untested_obs_axis_unit.py
"""

from __future__ import annotations

import sys
import tempfile
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check_detail_on_fail as check  # noqa: E402
from _harness import finish  # noqa: E402
from _record import record_at, rnd  # noqa: E402

from octomod.orchestration.interaction import gate_note  # noqa: E402
from octomod.orchestration.ledger import Ledger  # noqa: E402
from octomod.orchestration.orchestrator import Orchestrator  # noqa: E402
from octomod.workflow_modules.model import model_space  # noqa: E402
from octomod.workflow_modules.model import tried_models as T  # noqa: E402

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
ASM = {
    "observables": [
        {"observable_id": "obs_B", "maps_to_label": "B_total", "formula": "B"}
    ],
    "noise": [{"observable_id": "obs_B", "formula": "sigma_B"}],
    "conditions": [{"condition_id": "c0", "overrides": {}}],
}
AX_ROUTE = {
    "id": "alt_route",
    "kind": "structure",
    "priority": 1,
    "on_antimony_patch": {"append": "R3: A -> ; k3*A"},
    "adds_parameters": [
        {"id": "k3", "lb": 1e-4, "ub": 1.0, "nominal_value": 0.05, "estimate": True}
    ],
}
AX_OFFSET = {
    "id": "b_offset",
    "kind": "observation",
    "priority": 2,
    "on_assembly_patch": {"add_offset": {"observable_label": "B_total"}},
    "adds_parameters": [],
}
AX_GHOST = {
    "id": "ghost",
    "kind": "structure",
    "priority": 3,
    "on_antimony_patch": {"append": "R4: Q -> ; k4*Q"},
    "adds_parameters": [
        {"id": "k4", "lb": 1e-4, "ub": 1.0, "nominal_value": 0.05, "estimate": True}
    ],
}
RULED_OUT = {
    "untested_axes_addressed": [
        {"id": "b_offset", "action": "ruled_out", "why": "no background at t = 0"}
    ]
}


class FakeCtx:
    def __init__(self, root):
        # the run is one record file; `root` is its root node
        self.root = root
        self.round_idx = 1
        self.ledger = Ledger(root)

    @property
    def round(self):
        return rnd(self.root, self.round_idx)


def shim_for(ctx):
    """The orchestrator's own methods on a shim — the engine's rule, not a copy."""
    shim = types.SimpleNamespace(ctx=ctx, root=ctx.root, ledger=ctx.ledger)
    shim._obs_targets = Orchestrator._obs_targets
    shim._declared_axis_problem = types.MethodType(
        Orchestrator._declared_axis_problem, shim
    )
    return shim


def staged() -> tuple[FakeCtx, list[dict]]:
    ctx = FakeCtx(record_at(Path(tempfile.mkdtemp()) / "run"))
    (rnd(ctx.root, 0) / "space/axes").put([AX_ROUTE, AX_OFFSET, AX_GHOST])
    return ctx, T.declared_axes_this_run(ctx.root)


def carry(ctx, declared, proposal, **kw):
    return Orchestrator._carry_untested(
        shim_for(ctx), declared, proposal, BASE, {"k1", "k2"}, set(), **kw
    )


def notes(ctx) -> str:
    return "\n".join(str(e.get("note")) for e in ctx.ledger.entries())


def main() -> int:
    # 1 ---- observation axes rejoin, checked against the base's assembly --
    ctx, declared = staged()
    got = carry(ctx, declared, {}, base_assembly=ASM, obs_taken={})
    ids = [a["id"] for a in got]
    check(
        "an unfitted observation axis rejoins beside a structural one",
        # free axes first — the engine's untested order (tried_models)
        ids == ["b_offset", "alt_route"] and all(a["carried_untested"] for a in got),
        ids,
    )
    check(
        "… and the undeclared-symbol axis does not",
        "ghost" not in ids and "untested axis 'ghost' not carried" in notes(ctx),
        notes(ctx)[-300:],
    )
    ctx, declared = staged()
    got = [a["id"] for a in carry(ctx, declared, {}, base_assembly=None)]
    check(
        "without an assembly to check it against, it is not carried — said why",
        "b_offset" not in got and "no assembly to check" in notes(ctx),
        notes(ctx)[-300:],
    )
    ctx, declared = staged()
    got = [
        a["id"]
        for a in carry(
            ctx, declared, {}, base_assembly=ASM, obs_taken={"B_total": "b_scale"}
        )
    ]
    check(
        "an observable another observation axis claims keeps that one only",
        "b_offset" not in got
        and "already carries the observation axis 'b_scale'" in notes(ctx),
        notes(ctx)[-300:],
    )

    # 2 ---- a ruled-out axis is not carried by the engine ------------------
    ctx, declared = staged()
    got = [
        a["id"]
        for a in carry(ctx, declared, RULED_OUT, base_assembly=ASM, obs_taken={})
    ]
    check("an axis the agent ruled out is not carried", got == ["alt_route"], got)

    # 3 ---- `axes: +<id>` buys it over the ruling ---------------------------
    ladder_calls: list[list[str]] = []
    real = model_space.pregate_ladder

    def fake_ladder(ctx_, ant, par, axes, max_models, t_end, module, *, mode):
        ladder_calls.append([a["id"] for a in axes])
        return list(axes), [], 1, []

    model_space.pregate_ladder = fake_ladder
    try:
        ctx, declared = staged()
        shim = shim_for(ctx)
        on_card = [{**AX_ROUTE, "carried_untested": True}]

        def buy(note, card=on_card):
            reading = gate_note.Reading()
            out = Orchestrator._axes_bought_at_expansion(
                shim,
                note,
                card,
                declared,
                RULED_OUT,
                BASE,
                BASE_PAR,
                ASM,
                100.0,
                8,
                model_space.CANDIDATES,
                reading,
            )
            return out, reading

        got, reading = buy("axes: +b_offset")
        check(
            "`axes: +b_offset` buys the ruled-out observation axis",
            [a["id"] for a in got] == ["b_offset"]
            and got[0]["bought_by_human"]
            and reading.read.get("axes") == "+b_offset",
            f"{got} {reading}",
        )
        rows = [e for e in ctx.ledger.entries() if e.get("bought_by_human")]
        check(
            "… ledgered, with the agent's ruling it overrides",
            rows
            and "ruled out by the agent: no background at t = 0" in rows[-1]["note"],
            str(rows)[:300],
        )
        check(
            "… and an observation axis needs no ladder",
            ladder_calls == [],
            ladder_calls,
        )
        got, reading = buy("axes: +alt_route", card=[])
        check(
            "a structural axis bought by id goes through the pre-compile ladder",
            [a["id"] for a in got] == ["alt_route"] and ladder_calls == [["alt_route"]],
            f"{got} {ladder_calls}",
        )

        # 4 ---- what cannot be bought is read back, with the reason ----------
        got, reading = buy("axes: +alt_route, +ghost, +nothere")
        un = reading.unread
        check(
            "already on the card / does not apply / never declared — each named",
            not got
            and "already on this card" in un.get("+alt_route", "")
            and "undeclared symbol" in un.get("+ghost", "")
            and "not declared in any round" in un.get("+nothere", ""),
            str(un),
        )
        got, reading = buy("axes: b_offset")
        check(
            "`axes: <id>` without + is not acted on here, and says where it is",
            not got and "only adds" in next(iter(reading.unread.values()), ""),
            str(reading.unread),
        )
        got, reading = buy("y")
        check(
            "no axes form, nothing bought",
            not got and not reading.read and not reading.unread,
        )
    finally:
        model_space.pregate_ladder = real

    # 5 ---- the card's verdict lines ----------------------------------------
    ctx, declared = staged()
    lines = "\n".join(
        T.untested_verdict_lines(
            RULED_OUT, declared, carried={"alt_route"}, buy_form=True
        )
    )
    check(
        "the card says what rejoined, and offers the form for a ruled-out axis",
        "alt_route: REJOINS this expansion" in lines
        and "b_offset: ruled out by the agent: no background at t = 0" in lines
        and "`axes: +b_offset` fits it anyway" in lines,
        lines,
    )
    plain = "\n".join(T.untested_verdict_lines(RULED_OUT, declared))
    check(
        "… and without the gate's flags the lines are as before",
        "fits it anyway" not in plain and "REJOINS" not in plain,
        plain,
    )

    # 6 ---- the gate is wired -----------------------------------------------
    src = (REPO / "octomod" / "orchestration" / "orchestrator.py").read_text()
    i = src.index("untested_carried = self._carry_untested(")
    check(
        "the tiers hand the carry the base's assembly and the claimed observables",
        "base_assembly=base_asm" in src[i : i + 400]
        and "obs_taken=" in src[i : i + 400],
    )
    j = src.index("def _maybe_expand_space(")
    body = src[j : src.index("def _assembly_of(", j)]
    check(
        "the + form is on the card and read before the search mode is set",
        '"axes: +<id>, +<id>' in body
        and body.index("self._axes_bought_at_expansion(")
        < body.index("next_mode = _ms.LATTICE"),
    )
    check("the purchase lands in the round's `expansion`", '"bought_by_human":' in body)

    return finish(
        "\nUNTESTED OBSERVATION AXIS",
        "\nUNTESTED OBSERVATION AXIS UNIT OK — unfitted observation axes rejoin, and a ruled-out axis can be bought over the ruling",
    )


if __name__ == "__main__":
    sys.exit(main())
