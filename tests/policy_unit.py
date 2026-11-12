"""Gate policy as declared configuration: the partition, the caps, the drift alarms.

  1. strict answers nothing; copilot answers exactly the cost-shaped gates;
  2. benchmark covers every gate the engine raises, or stops naming the uncovered one;
  3. usd_cap, max_expansions, redraft grants, n_starts and max_rounds act as caps;
  4. gate ids are read from the engine source, so a new gate lands here by itself;
  5. the shipped yamls are byte-identical to the writer that generates them;
  6. no gate call site sits inside a try that catches broadly.

    uv run python tests/policy_unit.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from _harness import check, finish  # noqa: E402

from octomod.orchestration.interaction import policy as P  # noqa: E402


class FakeLedger:
    """Just the surface `Policy.decide` reads."""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = list(rows or [])

    def entries(self) -> list[dict]:
        return self.rows


# --------------------------------------------------------------- gate discovery
def engine_gates() -> tuple[set[str], set[str]]:
    """Every gate the engine raises: (literal module ids, f-string module-id tails)."""
    literals: set[str] = set()
    templates: set[str] = set()
    for path in sorted((REPO / "octomod").rglob("*.py")):
        if path.name == "humangate.py":
            continue  # the delivery layer, not a gate site
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr in ("ask", "ask_once")):
                continue
            module = next((k.value for k in node.keywords if k.arg == "module"), None)
            if isinstance(module, ast.Constant) and isinstance(module.value, str):
                literals.add(module.value)
            elif isinstance(module, ast.JoinedStr):
                tail = "".join(
                    v.value
                    for v in module.values
                    if isinstance(v, ast.Constant) and isinstance(v.value, str)
                )
                templates.add(tail)
    return literals, templates


BROAD = {"Exception", "BaseException"}


def broad_catchers_on_gate_paths(root: Path | None = None) -> list[str]:
    """Gate call sites inside a `try` whose handler would swallow PolicyUncovered."""
    out: list[str] = []
    for path in sorted((root or (REPO / "octomod")).rglob("*.py")):
        tree = ast.parse(path.read_text())
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr in ("ask", "ask_once")):
                continue
            if not any(k.arg == "module" for k in node.keywords):
                continue
            cur = node
            while cur in parents:
                up = parents[cur]
                if isinstance(up, ast.Try) and any(
                    cur is b or cur in set(ast.walk(b)) for b in up.body
                ):
                    for h in up.handlers:
                        t = h.type
                        names = (
                            ["<bare>"]
                            if t is None
                            else (
                                [t.id]
                                if isinstance(t, ast.Name)
                                else (
                                    [e.id for e in t.elts if isinstance(e, ast.Name)]
                                    if isinstance(t, ast.Tuple)
                                    else []
                                )
                            )
                        )
                        if any(n in BROAD or n == "<bare>" for n in names):
                            out.append(
                                f"{path.name}:{node.lineno} inside try at "
                                f"{up.lineno} catching {names}"
                            )
                cur = up
    return out


def main() -> int:
    literals, templates = engine_gates()
    print(f"\nengine gates read from source: {sorted(literals)}")
    print(f"dynamically named: {sorted(templates)}\n")

    strict = P.Policy.load("strict")
    copilot = P.Policy.load("copilot")
    bench = P.Policy.load("benchmark")
    empty = FakeLedger()

    # 1 ---- strict answers nothing, by construction ------------------------
    unanswered = all(strict.decide(g, empty) is None for g in literals)
    check("strict answers no gate", unanswered, f"{len(literals)} gate ids")

    # 2 ---- the copilot partition ------------------------------------------
    answered, paused = [], []
    for g in sorted(literals):
        (answered if copilot.decide(g, empty) is not None else paused).append(g)
    cost = sorted(g for g in literals if P.gate_shape(g) == "cost")
    judgment = sorted(g for g in literals if P.gate_shape(g) == "judgment")
    check(
        "copilot answers exactly the cost-shaped gates",
        answered == cost,
        f"answered {answered}, cost-shaped {cost}",
    )
    check(
        "copilot pauses at exactly the judgment-shaped gates",
        paused == judgment,
        f"paused {paused}",
    )

    # 3 ---- every dynamically named gate is cost-shaped by SUFFIX ----------
    #        (a judgment gate whose id is built at runtime could not be
    #        declared in a yaml, so the partition must not depend on one)
    check(
        "dynamically named gates are covered by a declared suffix",
        all(t in P.COST_GATE_SUFFIXES for t in templates),
        f"{sorted(templates)} vs {P.COST_GATE_SUFFIXES}",
    )

    # 4 ---- benchmark covers every gate the engine raises ------------------
    uncovered = []
    for g in sorted(literals):
        try:
            if bench.decide(g, empty) is None:
                uncovered.append(g)
        except P.PolicyUncovered:
            uncovered.append(g)
    check(
        "benchmark.yaml covers every gate in the engine",
        not uncovered,
        f"uncovered: {uncovered}" if uncovered else "all declared",
    )

    # 5 ---- an uncovered gate stops honestly, naming the gate --------------
    try:
        bench.decide("a_gate_nobody_declared", empty)
        check("uncovered gate raises under uncovered:stop", False, "no exception")
    except P.PolicyUncovered as e:
        check(
            "uncovered gate raises under uncovered:stop, naming the gate",
            e.module == "a_gate_nobody_declared" and "a_gate_nobody_declared" in str(e),
            str(e),
        )
    check(
        "the same gate merely pauses under uncovered:pause",
        copilot.decide("a_gate_nobody_declared", empty) is None,
    )

    # 5b --- `uncovered` is authoritative, not the profile NAME -------------
    strict_stop = P.Policy(
        profile="copilot",
        caps=dict(P.DEFAULT_CAPS),
        answers={},
        uncovered="stop",
        sha="deadbeef",
        source="synthetic",
    )
    try:
        strict_stop.decide("evaluation_verdict", empty)
        check(
            "a copilot profile with uncovered:stop stops at a judgment gate",
            False,
            "no exception",
        )
    except P.PolicyUncovered as e:
        check(
            "a copilot profile with uncovered:stop stops at a judgment gate",
            e.module == "evaluation_verdict" and "judgment-shaped" in str(e),
            str(e),
        )

    # 5c --- a file that asks for something it cannot get is REFUSED --------
    import tempfile as _tf

    bad = Path(_tf.mkdtemp()) / "bad_strict.yaml"
    bad.write_text("profile: strict\nanswers:\n  evaluation_verdict: {answer: y}\n")
    try:
        P.Policy.load(bad)
        check("a strict profile that declares answers is refused", False, "loaded")
    except ValueError as e:
        check(
            "a strict profile that declares answers is refused, naming them",
            "evaluation_verdict" in str(e) and "strict" in str(e),
            str(e),
        )

    # 6 ---- a cost gate added later is answered by SHAPE, and says so ------
    shaped = P.Policy(
        profile="copilot",
        caps=dict(P.DEFAULT_CAPS),
        answers={},
        uncovered="pause",
        sha="deadbeef",
        source="synthetic",
    )
    ans = shaped.decide("assembly_cost_boundary", empty)
    check(
        "an undeclared cost gate is answered by shape, recorded as a default",
        ans is not None and ans.approved and ans.covered_by == "shape:cost",
        f"{ans}",
    )
    check(
        "an undeclared judgment gate is not answered by shape",
        shaped.decide("evaluation_verdict", empty) is None,
    )

    # 7 ---- usd_cap is MEASURED, and hands the decision back --------------
    spent = FakeLedger(
        [
            {"event": "agent_call", "cost_usd": 12.5},
            {"event": "agent_call", "cost_usd": 9.0},
        ]
    )
    check(
        "spent_usd sums the ledger's measured agent cost",
        abs(P.Policy.spent_usd(spent) - 21.5) < 1e-9,
        f"{P.Policy.spent_usd(spent)}",
    )
    check(
        "copilot over usd_cap hands every gate back to the human",
        copilot.decide("assembly_cost_boundary", spent) is None,
        f"cap {copilot.caps['usd_cap']}, spent 21.5",
    )
    over = FakeLedger([{"event": "agent_call", "cost_usd": 77.0}])
    try:
        bench.decide("assembly_cost_boundary", over)
        check("benchmark over usd_cap stops honestly", False, "no exception")
    except P.PolicyUncovered as e:
        check(
            "benchmark over usd_cap stops with the MEASURED total in the message",
            "77.00" in str(e) and "usd_cap" in str(e),
            str(e),
        )

    # 8 ---- max_expansions: policy must not buy mechanism without bound ----
    first = bench.decide("revision", empty)
    check(
        "the first policy expansion is approved",
        first is not None and first.approved,
        f"{first}",
    )
    used = FakeLedger(
        [
            {
                "event": "human_gate",
                "module": "revision",
                "approved": True,
                "mode": "policy",
            }
        ]
    )
    second = bench.decide("revision", used)
    check(
        "the second is refused, naming the cap",
        second is not None
        and not second.approved
        and "max_expansions" in second.note
        and second.covered_by == "cap:max_expansions",
        f"{second}",
    )
    human = FakeLedger(
        [
            {
                "event": "human_gate",
                "module": "revision",
                "approved": True,
                "mode": "file",
            }
        ]
    )
    still = bench.decide("revision", human)
    check(
        "a HUMAN's expansion does not consume the policy's cap",
        still is not None and still.approved,
        f"{still}",
    )

    # 9 ---- redraft grants: capped, and the note carries the count ---------
    grant = bench.decide("model_redraft_budget", empty)
    check(
        "a redraft grant under the cap carries n= in the note",
        grant is not None and grant.approved and "n=1" in grant.note,
        f"{grant}",
    )
    used_grant = FakeLedger([{"event": "redraft_grant", "granted": 1}])
    refused = bench.decide("model_redraft_budget", used_grant)
    check(
        "a redraft grant at the cap is refused, naming the cap",
        refused is not None
        and not refused.approved
        and "redraft_grants" in refused.note,
        f"{refused}",
    )

    # 10 --- n_starts rides the budget gate's note, and never overwrites ----
    with_n = P.Policy(
        profile="benchmark",
        caps={**P.DEFAULT_CAPS, "n_starts": 40},
        answers={"cost_boundary_estimation": {"answer": "y"}},
        uncovered="stop",
        sha="deadbeef",
        source="synthetic",
    )
    a = with_n.decide("cost_boundary_estimation", empty)
    check(
        "n_starts cap rides the budget note", a is not None and "n=40" in a.note, f"{a}"
    )
    declared_n = P.Policy(
        profile="benchmark",
        caps={**P.DEFAULT_CAPS, "n_starts": 40},
        answers={"cost_boundary_estimation": {"answer": "y", "note": "n=7"}},
        uncovered="stop",
        sha="deadbeef",
        source="synthetic",
    )
    b = declared_n.decide("cost_boundary_estimation", empty)
    check(
        "a declared n= in the note is not overwritten by the cap",
        b is not None and b.note == "n=7",
        f"{b}",
    )

    # 11 --- max_rounds is a CAP: policy may only lower the budget ----------
    capped = P.Policy(
        profile="benchmark",
        caps={**P.DEFAULT_CAPS, "max_rounds": 2},
        answers={},
        uncovered="stop",
        sha="deadbeef",
        source="synthetic",
    )
    check(
        "max_rounds lowers a larger budget and never raises a smaller one",
        capped.clamp_rounds(5) == 2 and capped.clamp_rounds(1) == 1,
        f"5 -> {capped.clamp_rounds(5)}, 1 -> {capped.clamp_rounds(1)}",
    )
    check(
        "no max_rounds cap leaves the budget alone",
        bench.clamp_rounds(9) == 9,
    )

    # 12 --- the sha identifies the FILE's content -------------------------
    check(
        "the sha is stable across loads",
        P.Policy.load("benchmark").sha == bench.sha,
    )
    check(
        "the three profiles have three distinct shas",
        len({strict.sha, copilot.sha, bench.sha}) == 3,
        f"{strict.sha} {copilot.sha} {bench.sha}",
    )

    # 13 --- DRIFT ALARM: the shipped yamls are what the writer writes ------
    import re

    src = (REPO / "octomod" / "orchestration" / "interaction" / "policy.py").read_text()
    blocks = re.findall(
        r'\(POLICIES_DIR / "(\w+)\.yaml"\)\.write_text\(\n        """(.*?)"""\n    \)',
        src,
        re.S,
    )
    check(
        "the writer still contains all three profiles",
        {n for n, _ in blocks} == {"strict", "copilot", "benchmark"},
        f"{sorted(n for n, _ in blocks)}",
    )
    drifted = [
        n
        for n, body in blocks
        if (REPO / "workflows" / "policies" / f"{n}.yaml").read_text() != body
    ]
    check(
        "every shipped profile is byte-identical to the writer's text",
        not drifted,
        f"drifted: {drifted}" if drifted else "3 files identical",
    )

    # 14 --- DRIFT ALARM: an honest stop must be able to REACH the caller ---
    #        (Orchestrator.run turns a PolicyUncovered into exit 1 naming the
    #        gate; a broad `except` on the way would swallow the stop)
    swallowed = broad_catchers_on_gate_paths()
    check(
        "no gate call site sits inside a try that catches broadly",
        not swallowed,
        "; ".join(swallowed) if swallowed else "every gate can raise out",
    )
    # and the alarm demonstrably fires on the thing it is looking for
    import tempfile

    synthetic = Path(tempfile.mkdtemp())
    (synthetic / "swallower.py").write_text(
        "def f(ctx):\n"
        "    try:\n"
        "        humangate.ask('q', [], ledger=None, module='intent')\n"
        "    except Exception:\n"
        "        pass\n"
    )
    (synthetic / "clean.py").write_text(
        "def g(ctx):\n" "    humangate.ask('q', [], ledger=None, module='intent')\n"
    )
    fired = broad_catchers_on_gate_paths(synthetic)
    check(
        "the alarm fires on a gate wrapped in a broad except, and only on it",
        len(fired) == 1 and "swallower.py" in fired[0],
        f"{fired}",
    )

    print()
    return finish(
        "POLICY UNIT",
        "POLICY UNIT OK — the partition, the caps, and both drift alarms hold",
    )


if __name__ == "__main__":
    raise SystemExit(main())
