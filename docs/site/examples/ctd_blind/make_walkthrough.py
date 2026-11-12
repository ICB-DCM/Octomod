"""Build the static walkthrough of the CTD run from its record.

    uv run --group docs python docs/site/examples/ctd_blind/make_walkthrough.py

Reads `record/<run>.h5` (the run's one file) and writes, next to this script:

  walkthrough.ipynb   the static page: markdown cells and figures, nothing to run
  explore_record.ipynb  a short notebook that opens the record (executed at build)
  figures/*.svg       the figures the page shows
  prompts/<page>.md   every agent's full prompt, one page per agent and round

Everything on those pages is read from the record; the prose between is the
only hand-written part. Edit this script, never its output, and re-run it when
the record or the prose changes.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import nbformat  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from octomod.result.node import Node  # noqa: E402
from octomod.result.runstore import RunStore  # noqa: E402

RUN_ID = "ctd_blind_local_v3_opus55_20261004_022720"
TESTCASE = "testcase/ctd_blind_local_v3"
RECORD = HERE / "record" / f"{RUN_ID}.h5"
FIG = HERE / "figures"
PROMPTS = HERE / "prompts"
ROUNDS = (0, 1)

# one prompt page per agent call site, in the order they ran: (round, role, job)
PAGES = {
    "construction": (0, "construction", "builds the base model (S1)"),
    "expansion": (0, "expansion", "turns the open questions into candidate models (S1)"),
    "construction_verification": (0, "construction_verification", "independent check of the model and its candidates (S1)"),
    "data_extraction": (0, "data_extraction", "reads the data file into measurements (S2)"),
    "observation": (0, "observation", "maps model states onto what the instrument measures (S3)"),
    "condition": (0, "condition", "encodes the experimental condition (S3)"),
    "assembly_verification": (0, "assembly_verification", "independent check of the assembled estimation problem (S3)"),
    "interpretation": (0, "interpretation", "reads the fits and answers the question (S7, round 0)"),
    "revision": (0, "revision", "reads what the selected model still misses and proposes new mechanisms"),
    "interpretation_round_1": (
        1,
        "interpretation",
        "reads the fits and answers the question (S7, round 1)",
    ),
}
MODULES = [
    ("intent", "S0 intent"),
    ("model", "S1 model"),
    ("data", "S2 data"),
    ("assembly", "S3 assembly"),
    ("cost_probe", "cost probe"),
    ("estimation", "S6 estimation"),
    ("evaluation", "S7 evaluation"),
    ("revision", "expansion"),
]
GATE_LABEL = {
    "intent": "freeze the intent",
    "model_scope": "model scope",
    "assembly_redraft_budget": "assembly failed",
    "assembly_cost_boundary": "compile",
    "cost_boundary_estimation": "estimation budget",
    "evaluation_verdict": "verdict",
    "revision": "buy an expansion round",
}
COLORS = {
    "M1_independent": "#8c8c8c",
    "M2_count_coop": "#d62728",
    "M3_neighbour": "#1f77b4",
    "M4_processive": "#9467bd",
    "M5_neighbour_and_count": "#ff7f0e",
    # "base" (round 1, the round-0 winner refitted) takes the winner's colour in build()
    "product_load_inhibition": "#2ca02c",
}
TIMES = [0.0, 60.0, 120.0, 960.0]
STANDING = "owner's standing answers"

plt.rcParams.update(
    {
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "svg.fonttype": "none",
        "savefig.bbox": "tight",
    }
)


# ------------------------------------------------------------------ reading
def clean(text: str) -> str:
    """The record names the machine it ran on; the page names the repository.
    The record also names the project by its earlier name; the page says Octomod."""
    text = re.sub(r"/Users/[^\s'\"]*?/testcase/", "testcase/", str(text))
    text = re.sub(r"/Users/[^\s'\"]*?/octomod_prototype[^/\s'\"]*/", "", text)
    text = text.replace("<repo>/", "")
    return text.replace("Octomod", "Octomod")


def get(node: Node, default=None):
    try:
        return node.get()
    except Exception:  # noqa: BLE001 — a key a record may not have
        try:
            return node.text()
        except Exception:  # noqa: BLE001
            return default


def load() -> dict:
    root = Node(RunStore(RECORD))
    with root.store.reading():  # one read handle for the many reads below
        return _load(root)


def _load(root: Node) -> dict:
    rows = root.store.ledger_rows()
    rec = {
        "root": root,
        "rows": rows,
        "description": (root / "input" / "description.md").text(),
        "intent": get(root / "intent"),
        "analysis": get(root / "analysis"),
        "timing": get(root / "timing"),
        "data": (root / "input" / "data" / "ctd_ms_timecourse.csv").text(),
        "rounds": {},
        "calls": {},
    }
    for k in ROUNDS:
        rk = root / "rounds" / f"round_{k}"
        cands = rk.child("candidates").children()
        rec["rounds"][k] = {
            "cands": cands,
            "selection": get(rk / "selection"),
            "est": {c: get(rk / "candidates" / c / "estimation") for c in cands},
            "attr": {c: get(rk / "attribution" / "per_candidate" / c / "groups") for c in cands},
            "gates": {c: get(rk / "candidates" / c / "gates") or {} for c in cands},
        }
    for page, (k, role, _) in PAGES.items():
        call = root / "rounds" / f"round_{k}" / "agent_calls" / role
        rec["calls"][page] = {
            "prompt": (call / "prompt").text("") or "",
            "reply": get(call / "reply", {}),
            "rows": [
                r
                for r in rows
                if r.get("event") == "agent_call" and r.get("role") == role and r.get("round") == k
            ],
        }
    return rec


def t0_of(rec) -> float:
    return min(r["t"] for r in rec["rows"] if "t" in r)


def human_gates(rec) -> list[dict]:
    return [r for r in rec["rows"] if r.get("event") == "human_gate"]


def standing(g: dict) -> bool:
    return STANDING in (g.get("note") or "")


def call_cost(rows: list[dict]) -> tuple[float, int]:
    usd = sum(float(r.get("cost_usd") or 0) for r in rows)
    out = sum(
        int(m.get("output_tokens") or 0)
        for r in rows
        for m in (r.get("models_used") or {}).values()
    )
    return usd, out


def fitted(rec, k: int, cand: str) -> dict:
    x = rec["rounds"][k]["est"][cand]["best_x_unscaled"]
    return x if isinstance(x, dict) else ast.literal_eval(x)  # the record's own repr


def n_params(v: dict) -> int:
    return round((v["AIC"] - 2 * v["NLLH"]) / 2)


# ------------------------------------------------------------------ figures
def fig_data(rec) -> str:
    lines = [ln.split(",") for ln in rec["data"].strip().splitlines()]
    head, body = lines[0], lines[1:]
    cols = [i for i, h in enumerate(head) if h.startswith("phos")]
    tcol = head.index("time_min") if "time_min" in head else 0
    fig, axes = plt.subplots(1, len(body), figsize=(9.5, 2.3), sharey=True)
    for ax, row in zip(axes, body, strict=True):
        vals = [float(row[i]) for i in cols]
        ax.bar(range(len(vals)), vals, color="#4c72b0")
        t = float(row[tcol])
        ax.set_title(f"t = {t:g} min\nsum {sum(vals):.2f}")
        ax.set_xticks(range(len(vals)))
        ax.set_xlabel("phosphorylated repeats")
    axes[0].set_ylabel("relative MS intensity")
    fig.suptitle(
        "The data: one spectrum per time point; note the totals drift between injections",
        y=1.2,
    )
    return save(fig, "data.svg")


def fig_timeline(rec) -> str:
    t0 = t0_of(rec)
    hours = lambda t: (t - t0) / 3600  # noqa: E731
    spans = [
        s for s in rec["timing"]["spans"] if s["category"] in ("module", "agent") and s["t1"] - s["t0"] > 1
    ]
    rows = {name: i for i, (name, _) in enumerate(MODULES)}
    fig, ax = plt.subplots(figsize=(10, 3.4))
    # a run waits at a gate from the card being written to the person's answer
    pending = None
    for r in rec["rows"]:
        if r.get("event") == "gate_pending":
            pending = r["t"]
        elif r.get("event") == "human_gate" and pending is not None:
            ax.axvspan(hours(pending), hours(r["t"]), color="#eeeeee", lw=0)
            pending = None
    for s in spans:
        if s["category"] == "module" and s.get("name") in rows:
            a, b = hours(s["t0"]), hours(s["t1"])
            ax.barh(rows[s["name"]], b - a, left=a, color="#c7d7ea", edgecolor="#7a9cc6", lw=0.5)
    for s in spans:
        if s["category"] == "agent" and s.get("module") in rows:
            a, b = hours(s["t0"]), hours(s["t1"])
            ax.barh(rows[s["module"]], b - a, left=a, height=0.45, color="#e8a33d")
    for g in human_gates(rec):
        ax.axvline(hours(g["t"]), color="#b03030", lw=0.8, ls="--")
    r1 = min(r["t"] for r in rec["rows"] if r.get("round") == 1 and "t" in r)
    ax.axvline(hours(r1), color="k", lw=1.2)
    ax.text(hours(r1) + 0.15, -0.9, "round 1 →", fontsize=8)
    ax.text(0.15, -0.9, "round 0", fontsize=8)
    ax.set_yticks(range(len(MODULES)), [label for _, label in MODULES])
    ax.set_ylim(len(MODULES) - 0.4, -1.3)
    ax.set_xlabel("hours since the run started")
    ax.bar(0, 0, color="#c7d7ea", label="module (engine)")
    ax.bar(0, 0, color="#e8a33d", label="agent call")
    ax.bar(0, 0, color="#eeeeee", label="waiting at a gate")
    ax.plot([], [], color="#b03030", ls="--", label="a gate answered")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=7, frameon=False)
    return save(fig, "timeline.svg")


def _parse_group(key: str) -> tuple[int, float] | None:
    m = re.match(r"obs_phos(\d)__sc_ctd_ms_t(\d+)__", key)
    return (int(m.group(1)), float(m.group(2))) if m else None


def fig_fits(rec, k: int) -> str:
    rd = rec["rounds"][k]
    fig, axes = plt.subplots(1, 4, figsize=(11, 2.8), sharey=False)
    first = rd["cands"][0]
    for ax, t in zip(axes, TIMES, strict=True):
        meas = [0.0] * 9
        for key, g in rd["attr"][first].items():
            p = _parse_group(key)
            if p and p[1] == t:
                meas[p[0]] = g["measured"][0]
        ax.bar(range(9), meas, color="#e0e0e0", label="measured")
        for cand in rd["cands"]:
            sim = [0.0] * 9
            for key, g in rd["attr"][cand].items():
                p = _parse_group(key)
                if p and p[1] == t:
                    sim[p[0]] = g["simulated"][0]
            ax.plot(
                range(9),
                sim,
                marker="o",
                ms=3,
                lw=1.8 if cand == rd["selection"]["winner"] else 0.9,
                color=COLORS[cand],
                label=cand,
            )
        ax.set_title(f"t = {t:g} min")
        ax.set_xticks(range(9))
        ax.set_xlabel("phosphorylated repeats")
    axes[0].set_ylabel("relative MS intensity")
    axes[-1].legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(1, 1))
    return save(fig, f"fits_round{k}.svg")


def fig_selection(rec, k: int) -> str:
    sel = rec["rounds"][k]["selection"]
    cands = rec["rounds"][k]["cands"]
    aic = {c: v["AIC"] for c, v in sel["values"].items()}
    best = min(aic.values())
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 0.45 * len(cands) + 0.9))
    a1.barh(cands, [aic[c] - best for c in cands], color=[COLORS[c] for c in cands])
    a1.axvline(2, color="k", lw=0.8, ls="--")
    a1.text(2.3, len(cands) - 0.6, "ΔAIC = 2", fontsize=7)
    a1.set_xlabel("ΔAIC (lower is better)")
    a1.invert_yaxis()
    a2.barh(cands, [sel["weights"][c] for c in cands], color=[COLORS[c] for c in cands])
    a2.axvline(0.7, color="k", lw=0.8, ls="--")
    a2.text(0.71, len(cands) - 0.6, "decisive at 0.70", fontsize=7)
    a2.set_xlim(0, 1.05)
    a2.set_xlabel("Akaike weight")
    a2.set_yticks([])
    a2.invert_yaxis()
    return save(fig, f"selection_round{k}.svg")


def fig_waterfalls(rec, k: int) -> str:
    rd = rec["rounds"][k]
    fig, ax = plt.subplots(figsize=(6, 2.6))
    for cand in rd["cands"]:
        f = rd["est"][cand]["fvals"]
        f = sorted(json.loads(f) if isinstance(f, str) else f)
        best = f[0]
        ax.plot(range(1, len(f) + 1), [v - best + 1e-3 for v in f], color=COLORS[cand], label=cand, lw=1)
    ax.set_yscale("log")
    ax.set_xlabel("start, sorted by final objective")
    ax.set_ylabel("objective − best (+1e-3)")
    ax.legend(fontsize=7, frameon=False)
    return save(fig, f"waterfalls_round{k}.svg")


def save(fig, name: str) -> str:
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / name)
    plt.close(fig)
    return f"figures/{name}"


# ------------------------------------------------------------------ prose
def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append(
            "| "
            + " | ".join(
                str(c).replace("|", "\\|").replace("\n", " ").replace("*", "\\*")
                if not str(c).startswith(("**", "[", "`"))
                else str(c).replace("|", "\\|").replace("\n", " ")
                for c in r
            )
            + " |"
        )
    return "\n".join(out)


def dropdown(title: str, body: str, open_: bool = False) -> str:
    opt = "\n:open:" if open_ else ""
    return f"::::{{dropdown}} {title}{opt}\n{body}\n::::"


def prose(text: str) -> str:
    """An agent's text, not markdown: `[x](t)` is not a link, `a*b` not emphasis,
    `Jp<n>` not an HTML tag."""
    text = re.sub(r"\bmechanism:(\w+)", r"the mechanism of \1", text)
    return text.replace("[", "\\[").replace("*", "\\*").replace("<", "\\<")


def quote(text: str, limit: int | None = None) -> str:
    # an agent's prose, not markdown: `[x](t)` in it is not a link
    text = prose(clean(text).strip())
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return "\n".join("> " + ln if ln else ">" for ln in text.splitlines())


def code(text: str, lang: str = "text") -> str:
    return f"````{lang}\n{clean(text).rstrip()}\n````"


def duration(s: float) -> str:
    s = float(s)
    if s >= 5400:
        return f"{s / 3600:.1f} h"
    return f"{s / 60:.0f} min" if s >= 90 else f"{s:.0f} s"


def prompt_link(page: str) -> str:
    return f"[the full prompt](prompts/{page}.md)"


def decisions_list(decisions: list[dict]) -> str:
    parts = []
    for d in decisions:
        body = [quote(d.get("rationale", ""))]
        if d.get("alternatives_considered"):
            body.append("\n**Alternatives considered.** " + prose(clean(d["alternatives_considered"])))
        meta = [f"confidence: {d.get('confidence')}", f"evidence tier: {d.get('evidence_tier')}"]
        body.append("\n*" + " · ".join(m for m in meta if not m.endswith("None")) + "*")
        title = clean(d["decision"])
        title = title if len(title) <= 160 else title[:160].rsplit(" ", 1)[0] + " …"
        parts.append(dropdown(prose(title), "\n".join(body)))
    return "\n\n".join(parts)


def verdicts(reply: dict) -> str:
    items = reply.get("verdicts", [])
    n_ok = sum(1 for v in items if v.get("ok"))
    overall = reply.get("overall")
    head = (
        f"**The checker's overall call: `{clean(overall)}`** — {n_ok} of {len(items)} "
        "aspects fine, the rest raised as concerns (click an aspect for its note):\n\n"
    )
    return head + "\n\n".join(
        dropdown(
            ("✓ " if v.get("ok") else "⚠ concern · ") + str(v.get("aspect")),
            quote(v.get("note", "")),
        )
        for v in items
    )


def short(cand: str) -> str:
    return {"base": "base", "product_load_inhibition": "PLI"}.get(cand, cand.split("_")[0])


def gate_matrix(rec, k: int, prefix: str) -> str:
    rd = rec["rounds"][k]
    ids = sorted({g for c in rd["cands"] for g in rd["gates"][c] if g.startswith(prefix)})
    rows = []
    for gid in ids:
        cells = []
        for c in rd["cands"]:
            g = rd["gates"][c].get(gid) or {}
            cells.append("✓" if g.get("passed") else ("⚠" if g else "·"))
        rows.append([f"`{gid}`", *cells])
    return md_table(["check", *[short(c) for c in rd["cands"]]], rows)


def gate_flags(rec, k: int, prefix: str) -> str:
    out = []
    rd = rec["rounds"][k]
    for c in rd["cands"]:
        for gid, g in rd["gates"][c].items():
            if gid.startswith(prefix) and not g.get("passed"):
                out.append(f"- **{c}** · `{gid}` ({g.get('tier')}): {prose(clean(g.get('detail', '')))}")
    return "\n".join(out) or "- every check passed for every candidate"


def answer_of(g: dict) -> str:
    return ("yes" if g.get("approved") else "no") + (
        f" — note: `{clean(g['note']).splitlines()[0][:160]}`" if g.get("note") else ""
    )


def human_row(g: dict, t0: float) -> list:
    at = datetime.fromtimestamp(g["t"], tz=timezone.utc).strftime("%H:%M")
    return [
        f"{g.get('round', 0)}",
        GATE_LABEL.get(g["module"], g["module"]),
        g["question"],
        answer_of(g),
        "standing answer" if standing(g) else "at the card",
        f"{(g['t'] - t0) / 3600:.1f} h ({at} UTC)",
    ]


def gate_box(g: dict) -> str:
    ans = "**yes**" if g.get("approved") else "**no**"
    # the whole note quoted: a note of several lines keeps them together
    note = f"\n\n**The note:**\n\n{quote(g['note'])}" if g.get("note") else ""
    how = (
        "applied by the front end from the owner's standing answers"
        if standing(g)
        else "given at the card"
    )
    return (
        ":::{admonition} A gate · "
        + GATE_LABEL.get(g["module"], g["module"])
        + f" (round {g.get('round', 0)})"
        + "\n:class: important\n"
        + f"**The card asked:** {g['question']}\n\n**The answer:** {ans}, {how}.{note}\n:::"
    )


def gates_of(rec, module: str, rnd: int) -> list[dict]:
    return [g for g in human_gates(rec) if g["module"] == module and g.get("round", 0) == rnd]


def failures_in(prompt: str) -> list[str]:
    """The gate failures a redraft prompt carries for its earlier attempts."""
    m = re.search(r"## attempt_history\n```json\n(.*?)\n```", prompt, re.S)
    if not m:
        return []
    hist = json.loads(m.group(1))
    return [f for a in hist.get("attempts", []) for f in a.get("gate_failures", [])]


# ------------------------------------------------------------------ pages
def write_prompt_pages(rec) -> None:
    PROMPTS.mkdir(exist_ok=True)
    for old in PROMPTS.glob("*.md"):
        old.unlink()
    for page, (k, role, what) in PAGES.items():
        call = rec["calls"][page]
        text, reply, n = call["prompt"], call["reply"], len(call["rows"])
        again = ""
        if n > 1:
            # only a redraft's prompt carries its earlier attempts; a call made
            # again after a re-entry starts afresh
            again = (
                f" The agent was called {n} times here; the record keeps the prompt and reply "
                "of the last call"
                + (
                    ", which carries the earlier attempts in its `attempt_history`."
                    if "## attempt_history" in text
                    else "."
                )
            )
        body = [
            f"# Prompt · `{role}` (round {k})",
            "",
            f"The **{role}** agent {what}. Below is the exact prompt it was sent in this "
            f"run ({len(text):,} characters), as the record keeps it, followed by its "
            "reply. The prompt is the role's instructions (its skill) followed by the "
            f"inputs the engine chose to show it; nothing else reached the agent.{again}",
            "",
            "[← back to the walkthrough](../walkthrough.ipynb)",
            "",
            "## The prompt",
            "",
            code(text),
            "",
            "## The reply",
            "",
            code(json.dumps(reply, indent=1, ensure_ascii=False, default=str), "json"),
            "",
        ]
        (PROMPTS / f"{page}.md").write_text("\n".join(body))
    index = ["# All prompts of the CTD run", "", "One page per agent and round, in the order they ran.", ""]
    index += ["```{toctree}", ":maxdepth: 1", ""] + list(PAGES) + ["```", ""]
    (PROMPTS / "index.md").write_text("\n".join(index))


def build(rec) -> list[str]:
    a = rec["analysis"]
    intent = rec["intent"]
    t0 = t0_of(rec)
    hg = human_gates(rec)
    n_standing = sum(1 for g in hg if standing(g))
    # the prose says the first answers were given at the card and the rest were standing
    assert [standing(g) for g in hg] == sorted(standing(g) for g in hg)
    r0, r1 = rec["rounds"][0], rec["rounds"][1]
    sel0, sel1 = r0["selection"], r1["selection"]
    win0, win1 = sel0["winner"], sel1["winner"]
    COLORS["base"] = COLORS[win0]
    tim = rec["timing"]
    cat = {k: v["wall_s"] for k, v in tim["by_category"].items()}
    cost = a.get("cost") or {}
    calls = rec["calls"]
    figs = {
        "data": fig_data(rec),
        "timeline": fig_timeline(rec),
        **{f"fits{k}": fig_fits(rec, k) for k in ROUNDS},
        **{f"selection{k}": fig_selection(rec, k) for k in ROUNDS},
        **{f"waterfalls{k}": fig_waterfalls(rec, k) for k in ROUNDS},
    }
    cells: list[str] = []
    add = cells.append

    # ---------------------------------------------------------------- title
    add(
        f"""# A real run, start to finish: how P-TEFb phosphorylates the RNA polymerase II CTD

This page follows one complete Octomod run on real data, from the question a
scientist brought to the model it arrived at. **Nothing here needs to be run.**
Every prompt, reply, check, number and figure on this page was read from the run's
single result file, `{RUN_ID}.h5` (the *record*); only the explanatory prose was
written by hand. The last section, [Explore the record yourself](explore_record.ipynb),
shows how to open the same file and find all of this directly.

| | |
|---|---|
| **The question** | {clean(intent['question'])} |
| **The data** | {clean(intent['system'])}: 9 phosphorylation states × 4 time points, no replicates |
| **Agents** | {len({r for _, r, _ in PAGES.values()})} roles, {cost.get('agent_calls')} calls to Claude (`claude-opus-5-5`), ${cost.get('usd'):.2f} |
| **Decisions** | {len(hg)} answers at gates: {len(hg) - n_standing} given at the card, {n_standing} applied from standing answers the owner wrote down |
| **Time** | {tim['run_wall_s'] / 3600:.1f} h over {tim['n_sessions']} sessions: agents {cat['agent'] / 3600:.1f} h, fitting and other computation {cat['compute'] / 3600:.1f} h, waiting at gates {cat['waiting_for_human'] / 3600:.1f} h |
| **Models fitted** | round 0: {len(r0['cands'])} candidate mechanisms; round 1: the round-0 winner and {len(r1['cands']) - 1} extension of it; 100 optimiser starts each |
| **Outcome** | `{a['outcome']}`: **{win1}** ({clean(a['answer']['selected_structure'])}) selected decisively, Akaike weight {sel1['weights'][win1]:.3f} |
"""
    )

    # ---------------------------------------------------------------- 1 goal
    files = a["inputs"]["files"]
    what = {
        "blocklist.txt": "words the run must not act on (a research blocklist)",
        "data/ctd_ms_timecourse.csv": "the measurements",
        "description.md": "the bench note, in the user’s words",
        "intent.yaml": "the frozen intent: question and success criteria",
        "testcase.yaml": "run settings (end time, no holdout, knowledge module off for this benchmark)",
    }
    add(
        f"""## 1 · The goal, from the user's side

The user is a biochemist with a small in-vitro dataset: the kinase **P-TEFb** was
mixed with a CTD construct of **8 repeats** and ATP, and mass spectrometry counted
how many repeats carried a phosphate after 0, 1, 2 and 16 hours. They want to know
*how* P-TEFb modifies the CTD, and in particular whether modifying one repeat
changes the rate at which its **neighbours** are modified, or whether the rate
depends only on **how many** repeats are already modified, or on **nothing at all**
— and they want to be told plainly what these data cannot decide.

The problem is a folder of plain files — a bench note, the data file and a short
intent (here `{TESTCASE}`, a local copy of the `ctd_blind` benchmark, whose
published answer the agents never see). The front end (Claude Code in this
repository) started the engine with live agents and relayed every decision:

```bash
./run.sh run --testcase {TESTCASE} --backend llm --run-id {RUN_ID} --gate-mode file
```

The run snapshotted these inputs into its record before the first module, so the
record holds exactly what the agents were given:

{md_table(['file', 'what it is'], [[f, what.get(f, '')] for f in files])}

No measurement is held back as a test: there is one condition and four time
points, and a held-out time point would test its own free scale factor rather
than the mechanism, as `testcase.yaml` explains. The candidates are therefore
compared on an information criterion alone.
"""
    )
    add(dropdown("The bench note (`description.md`), as the user wrote it", quote(rec["description"])))
    add(
        f"""### What counts as success

The intent is **frozen** before anything is built: every later verdict is scored
against it, and the agents may not change it.

- **Inference target:** `{intent['inference_target']}` — pick between mechanisms, not predict a new condition
- **Required predictions:**
{chr(10).join('  - ' + clean(p) for p in intent['required_predictions'])}
- **Success criteria:**
{chr(10).join('  - ' + clean(s) for s in intent['success_criteria'])}
- **Out of scope:**
{chr(10).join('  - ' + clean(s) for s in intent['scope_exclusions'])}

### The data

![The measured spectra]({figs['data']})

Nine relative intensities per time point. Two things make this hard: the totals
drift between injections (1.00, 4.07, 3.79, 0.85) although the amount of CTD is
constant, so every time point needs its own scale; and the instrument sees *how
many* repeats are modified, never *which* ones.
"""
    )

    # ---------------------------------------------------------------- 2 overview
    rows = []
    for page, (k, role, job) in PAGES.items():
        usd, out = call_cost(calls[page]["rows"])
        rows.append(
            [
                f"[`{role}`](prompts/{page}.md)",
                k,
                job,
                len(calls[page]["rows"]),
                f"{len(calls[page]['prompt']):,}",
                f"{out:,}",
                f"${usd:.2f}",
            ]
        )
    add(
        f"""## 2 · The run at a glance

The engine runs a fixed sequence of modules. Agents draft (the model, the reading
of the data, the observation model, the interpretation, and here a proposal for
what the model space lacked); deterministic checks test each draft; independent
checker agents audit them; and the run **stops at a gate** whenever the next step
costs compute or makes a scientific claim.

![Timeline of the run]({figs['timeline']})

This run took {tim['run_wall_s'] / 3600:.1f} hours of wall time in
{tim['n_sessions']} sessions: each gate ends a session, and the next one starts
when the answer arrives. The grey bands are those waits,
{cat['waiting_for_human'] / 3600:.1f} hours in all. The agents (orange) took
{cat['agent'] / 3600:.1f} hours; fitting and the other computation took
{cat['compute'] / 3600:.1f} hours.

**Every agent call** (click a role to read its full prompt and reply):

{md_table(['agent', 'round', 'job', 'calls', 'prompt chars', 'output tokens', 'cost'], rows)}

**Every answer at a gate.** The first {len(hg) - n_standing} were given at the
card. For the rest, the owner wrote down *standing answers* on 4 October —
approve compiling and the default estimation budget, expand once when the
interpreter recommends revising and the expansion's diagnosis names a missing
mechanism, and stop after that one round — and the front end applied them at
each card, naming the standing answer in the note. Every answer went through
the front end in file-gate mode and is recorded as a human decision (the
verdicts read "signed by: {a['gate_policy']['verdict_signed_by']}"); none came
from a policy profile (the run's policy was `{a['gate_policy']['profile']}`).

{md_table(['round', 'gate', 'what the card asked', 'answer', 'how', 'when'], [human_row(g, t0) for g in hg])}
"""
    )

    # ---------------------------------------------------------------- 3 round 0
    add(
        """## 3 · Round 0, step by step

### 3.1 · S0 — freezing the intent

The first stop, before any agent is called: the person confirms the question and
the success criteria, which are then frozen for the rest of the run."""
    )
    add(gate_box(gates_of(rec, "intent", 0)[0]))

    con = calls["construction"]["reply"]
    params = [
        [
            f"`{p['id']}`",
            p.get("nominal_value"),
            p.get("unit", ""),
            "estimated" if p.get("estimate") else "fixed / switch",
            clean(p.get("source", "")),
        ]
        for p in con["parameters"]
    ]
    add(
        f"""### 3.2 · S1 — building the base model (`construction` agent)

The construction agent receives the bench note, the intent and two domain packs
(general dynamics, measurement technology) — {prompt_link('construction')},
{len(calls['construction']['prompt']):,} characters. It has no model to start
from: it must derive one from the note.

Its central decision was how to represent the substrate. Eight repeats, each
modified or not, give 256 configurations, observed only through their 9 counts.
The agent's base tracks only the **count** of modified repeats per molecule
(`CTD_0` … `CTD_8`). As long as every unmodified repeat of a molecule is modified
at the same rate, that lumping is exact. A **neighbour effect** is the one
hypothesis that breaks it, so for that candidate the agent wrote down an exact
rule to *generate* the positional model instead of writing it by hand.

In the base, each free repeat is modified at a rate
`kmod · PTEFb · ATP/(K_ATP + ATP)`, with switches for the hypotheses: `cp`
multiplies the rate by `cp` per mark already on the molecule (count
cooperativity), `q_proc` lets the kinase continue to another repeat before
releasing (processivity), and in the positional model `nb` multiplies it per
modified immediate neighbour. With every switch at its neutral value, all repeats
are modified independently at one rate — the "nothing at all" hypothesis.

{md_table(['parameter', 'nominal', 'unit', 'role', 'why (the agent’s words)'], params)}

**The agent's decisions, each with its rationale** (click to expand):
"""
    )
    add(decisions_list(con["build_report"]["decisions"]))
    add(dropdown("The base model in Antimony (first 60 lines)", code("\n".join(con["antimony"].splitlines()[:60]))))

    var = calls["expansion"]["reply"]
    crow = []
    for c in var["candidates"]:
        sp = [f"`{s['id']}` estimated in [{s['lb']}, {s['ub']}]" for s in c.get("set_parameters", [])]
        adds = [
            f"adds `{p if isinstance(p, str) else p.get('id')}`" for p in c.get("adds_parameters") or []
        ]
        crow.append([f"**{c['id']}**", clean(c["label"]), ", ".join(sp + adds) or "— (the base)"])
    fails = failures_in(calls["expansion"]["prompt"])
    n_first = next(
        r["n_failures"] for r in rec["rows"] if r.get("event") == "redraft" and r.get("role") == "expansion"
    )
    scope = gates_of(rec, "model_scope", 0)
    budget = gates_of(rec, "assembly_redraft_budget", 0)[0]
    redraft_note = next(g["note"] for g in scope if (g.get("note") or "").startswith("redraft:"))
    lint = next(
        r
        for r in rec["rows"]
        if r.get("event") == "gate" and r.get("passed") is False and "petablint" in (r.get("detail") or "")
    )
    add(
        f"""### 3.3 · S1 — the candidates, and a stop on the way (`expansion` agent)

A second agent, the expansion agent ({prompt_link('expansion')}), reads the base
and the intent and declares each candidate as a **difference from the base**:
which switch it turns on, or what it adds.

{md_table(['candidate', 'what it claims', 'what changes from the base'], crow)}

Getting the two positional candidates (M3 and M5) right took four calls and one
stop of the run — every step of it is in the record:

1. **The first draft was refused by a deterministic check** and sent back
   automatically: the patches for M3 and M5 used the generated positional states
   (the "gap classes") without declaring them in the base or in `adds_parameters`
   — {n_first} findings, such as
   > {prose(clean(fails[0]))}
2. **The second draft declared them**, as new *parameters*. It passed the S1
   checks, and the person approved the scope.
3. **At assembly (S3), `petablint` refused the estimation problem** — states
   declared as parameters are extraneous parameters to it:
   > {prose(clean(lint['detail'])[:300])} …

   No agent at that module could be asked to repair it, so the run asked whether to grant another
   attempt or stop, and the person answered **{'yes' if budget.get('approved') else 'no'}**:
   the run ended there.
4. **The person re-entered the same run at the model module**
   (`--from-module model`): nothing upstream was paid for again. At the scope card
   they sent the expansion agent back with their own words:
   > {prose(clean(redraft_note))}
5. The third reply repeated the undeclared-symbol error and was sent back
   automatically; **the fourth passed**, and the person approved the scope again.
"""
    )
    add(decisions_list(var["build_report"]["decisions"]))

    add(
        f"""### 3.4 · S1 — checking the model

Two kinds of check run before anyone is asked. **Deterministic gates** build and
simulate every candidate (a ✓ is a pass, ⚠ a finding):

{gate_matrix(rec, 0, 'model_')}

{gate_flags(rec, 0, 'model_')}

Then an **independent checker agent** ({prompt_link('construction_verification')}) audits the
construction's reasoning against the note — its citations, its support, its
rationales:
"""
    )
    add(verdicts(calls["construction_verification"]["reply"]))
    add(
        """The checker's findings go on the scope card; they do not block the run. The
last scope card of round 0, with the answer that let the candidates go on:"""
    )
    add(gate_box(scope[-1]))

    de = calls["data_extraction"]["reply"]
    add(
        f"""### 3.5 · S2 — reading the data (`data_extraction` agent)

The data agent ({prompt_link('data_extraction')}) maps the CSV onto measurements —
{len(de['mappings'])} observables, one per phosphorylation count — and raises
**flags** about what it saw, which travel to every later agent:
"""
    )
    for f in de.get("flags", []):
        text = clean(f if isinstance(f, str) else f.get("flag") or f.get("note") or json.dumps(f))
        title = re.split(r"(?<=[.:;])\s", text, maxsplit=1)[0]
        add(dropdown(prose(title[:140]), quote(text)))

    o0 = calls["observation"]["reply"]["observables"][0]
    add(
        f"""### 3.6 · S3 — the observation model

The instrument does not measure concentrations. The observation-model agent
({prompt_link('observation')}) decides how each state maps onto a measured
intensity:

- **Formula:** intensity of the *k*-phosphate peak = `{o0['scaling']['scale_parameter']}` (one per time point) × the amount of CTD with *k* modified repeats
- **Noise:** `{o0['noise']['distribution']}`, sd = `{o0['noise']['formula']}` — one standard deviation for the whole experiment, scaled with each spectrum, as the note says
- **Scaling:** `{o0['scaling']['mode']}` per `{o0['scaling']['per']}`, shared by the nine peaks of one injection
"""
    )
    add(dropdown("The agent's rationale for the observation model", quote(o0.get("rationale", ""))))
    add(
        dropdown(
            "The condition encoding (`condition` agent)",
            code(json.dumps(calls["condition"]["reply"], indent=1, ensure_ascii=False)[:4000], "json"),
        )
    )
    add(
        f"""The assembled estimation problem (PEtab) is then checked for every candidate
(the final assembly, after the redraft above):

{gate_matrix(rec, 0, 'assembly_')}

{gate_flags(rec, 0, 'assembly_')}

and audited by a second checker agent ({prompt_link('assembly_verification')}):
"""
    )
    add(verdicts(calls["assembly_verification"]["reply"]))

    probes = [r for r in rec["rows"] if r.get("event") == "marker" and r.get("module") == "cost" and r.get("round") == 0]
    median = {c: r.get("median_start_s") for c, r in zip(r0["cands"], probes, strict=True)}
    probe = [[c, f"{m:.1f} s", r.get("approved_n_starts")] for (c, m), r in zip(median.items(), probes, strict=True)]
    est_gates = gates_of(rec, "cost_boundary_estimation", 0)
    asked_again = [c for c in r0["cands"] if any(f"'{c}'" in g["question"] for g in est_gates)]
    first = r0["cands"][0]
    slower = " and ".join(f"{median[c] / median[first]:.0f}" for c in asked_again)
    add(
        f"""### 3.7 · Compile and budget — the cost gates

Compiling five AMICI models costs minutes, so the person is asked first. After
compiling, a short **cost probe** times a few optimiser starts per candidate and
projects what the full estimation would take; that projection is the budget card.

{md_table(['candidate', 'median time per start (probe)', 'starts approved'], probe)}

The budget was approved on the projection for the first candidate. The engine
does not stretch an approval further than it was given: the positional models
{' and '.join(asked_again)} probed about {slower} times slower than that,
beyond the declared ceiling of 5×, so each was put to the person on its own card
({len(est_gates)} budget cards in all)."""
    )
    for g in gates_of(rec, "assembly_cost_boundary", 0) + est_gates:
        add(gate_box(g))

    add(fit_section(rec, 0, figs, "3.8 · S6 — fitting every candidate"))

    ip0 = calls["interpretation"]["reply"]
    w0 = sel0["weights"][win0]
    add(
        f"""### 3.9 · S7 — comparing the candidates

The engine ranks the candidates by AIC. Two models within ΔAIC 2 are called
**indistinguishable**; the selection is called decisive when the winner's Akaike
weight exceeds 0.70.

![Selection, round 0]({figs['selection0']})

**{win0}** wins decisively, with weight {w0:.3f}. Then the interpretation agent
({prompt_link('interpretation')},
{len(calls['interpretation']['prompt']):,} characters of fits,
residuals, attribution and diagnostics) reads the evidence and writes the answer.
Its recommendation: **`{ip0.get('recommendation')}`** — the winner still misses
systematically, and the agent says where.
"""
    )
    add(interpretation(ip0))
    v0 = gates_of(rec, "evaluation_verdict", 0)[0]
    add(
        """The verdict is a scientific claim, so a person signs it. The engine's own
default was to end the run here, since no misfit indicator was open; the
interpreter disagreed, and the ledger records that disagreement. The standing
answer settled it: one expansion round when the interpreter recommends revising."""
    )
    add(gate_box(v0))

    # ---------------------------------------------------------------- 4 expansion
    se = calls["revision"]["reply"]
    se_fails = failures_in(calls["revision"]["prompt"])
    exp = get(rec["root"] / "rounds" / "round_0" / "expansion") or {}
    arow = [[f"**{ax['id']}**", ax.get("priority"), prose(clean(ax.get("question", "")))] for ax in se["axes"]]
    add(
        f"""## 4 · Round 1: what the model space lacked

### 4.1 · The expansion agent's diagnosis

The space-expansion agent ({prompt_link('revision')}) reads where
**{win0}** still misses, and what no candidate ever varied, and proposes new
**axes**: mechanisms to add to the winner and test. Its first proposal named two
axes that failed the pre-compile simulation check — every model carrying them
drove a state negative within the 16 hours —

{chr(10).join('> ' + prose(clean(f)) for f in se_fails)}

so it was sent back once, automatically, and its second proposal passed:

{md_table(['axis', 'priority', 'the question it tests'], arow)}
"""
    )
    add(dropdown("The agent's diagnosis, in full", quote(se.get("diagnosis", "")), open_=True))
    add(
        dropdown(
            "What the agent says these data cannot separate, whatever is added",
            "\n\n".join(
                f"**{prose(clean(b.get('mechanism', '')))}**\n\n{quote(b.get('why_not_separable', ''))}"
                for b in se.get("beyond_this_data") or []
            ),
        )
    )
    add(
        f"""Buying the round is another computation, so it is a gate. The base for the new
round is the criterion winner, {exp.get('expanded_from', win0)}:"""
    )
    add(gate_box(gates_of(rec, "revision", 0)[0]))
    s3c1 = gates_of(rec, "assembly_cost_boundary", 1)[0]
    add(
        f"""### 4.2 · Round 1: building and fitting the extension

Round 1 needs no new construction: the engine writes each bought axis onto the
base and keeps the base's own model, data reading and observation model. Only one
of the two axes became a candidate. `processive_with_coupling` would estimate the
processivity switch `q_proc` on the base, and the engine treated it as already
carried by the base, which holds `q_proc` at 0 — so processivity on top of the
coupling was **not** tested in this round. The note recorded with the compile
answer says so:

> {prose(clean(s3c1['note']))}
"""
    )
    for g in gates_of(rec, "model_scope", 1) + gates_of(rec, "cost_boundary_estimation", 1):
        add(gate_box(g))
    add(fit_section(rec, 1, figs, "4.3 · S6 — fitting the base and the extension"))
    ip1 = calls["interpretation_round_1"]["reply"]
    w1 = sel1["weights"][win1]
    d1 = sel1["values"]["base"]["AIC"] - sel1["values"][win1]["AIC"]
    add(
        f"""### 4.4 · S7 — comparing again

![Selection, round 1]({figs['selection1']})

**{win1}** wins with weight {w1:.3f}, ΔAIC {d1:.2f} ahead of the base (the
round-0 winner). The interpretation agent of round 1
({prompt_link('interpretation_round_1')}) again recommended
**`{ip1.get('recommendation')}`**; the standing answer allowed one expansion round,
already used, so the run ended here, with the second recommendation recorded and
not bought.
"""
    )
    add(interpretation(ip1))
    add(gate_box(gates_of(rec, "evaluation_verdict", 1)[0]))

    # ---------------------------------------------------------------- 5 models
    every = []
    best = sel1["values"][win1]["AIC"]
    for k in ROUNDS:
        rd = rec["rounds"][k]
        for c in rd["cands"]:
            if k == 1 and c == "base":
                continue  # the round-0 winner, refitted as the base
            v = rd["selection"]["values"][c]
            x = fitted(rec, k, c)
            shown = {n: x[n] for n in ("cp", "nb", "q_proc", "kon_I") if n in x}
            on = [
                f"`{n}` = {float(val):.3g}"
                for n, val in shown.items()
                if float(val) != {"cp": 1.0, "nb": 1.0}.get(n, 0.0)
            ]
            every.append(
                [
                    f"**{c}**" + (" (selected)" if c == win1 else ""),
                    k,
                    ", ".join(on) or "— (independent repeats)",
                    n_params(v),
                    f"{v['NLLH']:.2f}",
                    f"{v['AIC'] - best:.2f}",
                ]
            )
    add(
        f"""## 5 · The models side by side

Every model the run fitted, on the same data and the same likelihood, so the AIC
values compare across rounds (ΔAIC against the selected model; the base of round
1 is {win0}, refitted, and appears once):

{md_table(['model', 'round', 'mechanism terms (fitted)', 'parameters', '−log L', 'ΔAIC'], every)}

How each fits the data — bars: measured; lines: each candidate's prediction at its
best fit, the selected model of the round drawn thicker. Round 0:

![Fits of every candidate, round 0]({figs['fits0']})

Independent repeats (grey) cannot produce the broad spectrum at 60 minutes, where
unmodified and heavily modified molecules coexist; the coupled models can. Round 1
— the base against the extension:

![Fits of the base and the extension, round 1]({figs['fits1']})

The extension changes the shape only slightly: it lets the kinase slow as product
accumulates, which moves the 60- and 120-minute spectra closer to the data, as the
interpretation's attribution details.
"""
    )

    # ---------------------------------------------------------------- 6 answer
    crit = "\n".join(
        f"- `{c['verdict']}` — {prose(clean(c['criterion']))}" for c in ip1.get("answers_intent") or []
    )
    still = "\n".join(f"- {prose(clean(x))}" for x in ip1.get("cannot_distinguish") or [])
    determined = "\n".join(f"- {prose(clean(x))}" for x in ip1.get("nonetheless_determined") or [])
    add(
        f"""## 6 · The answer, and what stays open

**Selected:** {win1} — {clean(a['answer']['selected_structure'])} — by AIC over
every candidate fitted, decisively (Akaike weight {w1:.3f}), with no other model
indistinguishable. Rates that depend on nothing are
rejected; both coupling terms are away from neutral; and a slowdown that grows as
product accumulates improves the fit, though what causes it is listed below as
undetermined. What the coupling *is* — a neighbour effect, or a count-dependent
rate with a more flexible profile — these count-only data cannot decide, and the
run says so rather than claiming it.

**Against the success criteria the user set at the start** (round 1):

{crit}

**Determined nonetheless:**

{determined}

**Declared undetermined** — stated because they are true, not because the run failed:

{still}
"""
    )

    # ---------------------------------------------------------------- 7 cost
    prov = a["provenance"]["code"]
    vers = prov.get("versions") or {}
    add(
        f"""## 7 · Cost, time and provenance

| | |
|---|---|
| agent calls | {cost.get('agent_calls')} · ${cost.get('usd'):.2f} |
| answers at gates | {cost.get('human_decisions')} ({len(hg) - n_standing} at the card, {n_standing} from standing answers) · policy `{a['gate_policy']['profile']}` (every gate asks a person) |
| redrafts | {cost.get('module_redrafts')} automatic (the expansion agent twice, the expansion agent once), one at the person's request, and one stop and re-entry |
| wall time | {tim['run_wall_s'] / 3600:.1f} h in {tim['n_sessions']} sessions · agents {cat['agent'] / 3600:.1f} h · computation {cat['compute'] / 3600:.1f} h · waiting at gates {cat['waiting_for_human'] / 3600:.1f} h |
| code | commit `{(prov.get('git') or {}).get('commit', '')[:7]}` (with uncommitted changes) |
| versions | {', '.join(f'{k} {v}' for k, v in vers.items())} |

## 8 · Where to go next

- **[Explore the record yourself](explore_record.ipynb)** — open this run's file in
  Python and find every item on this page.
- **[All prompts](prompts/index.md)** — every agent's full prompt and reply.
- **The engine's own reports for this run** —
  <a href="../../ctd_blind_reports/ANALYSIS.html">ANALYSIS</a> ·
  round 0: <a href="../../ctd_blind_reports/round_0/report/model_report.html">model report</a>,
  <a href="../../ctd_blind_reports/round_0/report/report.html">evaluation report</a> ·
  round 1: <a href="../../ctd_blind_reports/round_1/report/report.html">evaluation report</a>
"""
    )
    return cells


def fit_section(rec, k: int, figs: dict, title: str) -> str:
    rd = rec["rounds"][k]
    names = ["kmod", "cp", "nb", "q_proc", "kon_I", "sigma_ctd_ms"]
    present = [n for n in names if any(n in fitted(rec, k, c) for c in rd["cands"])]
    rows = []
    for c in rd["cands"]:
        x = fitted(rec, k, c)
        rows.append(
            [f"**{c}**", f"{rd['est'][c]['best_fval']:.2f}"]
            + [f"{float(x[n]):.3g}" if n in x else "" for n in present]
        )
    at_bound = sorted({b for c in rd["cands"] for b in rd["est"][c].get("at_bounds") or []})
    return f"""### {title}

Each candidate was fitted from 100 random starts. The **waterfall** shows the
final objective of every start, sorted: a flat plateau at the left means many
starts found the same best fit, so the optimum is trustworthy.

![Multistart waterfalls, round {k}]({figs[f'waterfalls{k}']})

{md_table(['candidate', 'best −log L', *[f'`{n}`' for n in present]], rows)}

At a bound in some fit: {', '.join(f'`{b}`' for b in at_bound) or 'nothing'}.
"""


def interpretation(ip: dict) -> str:
    return "\n\n".join(
        [
            dropdown("The agent's diagnosis, in full", quote(ip.get("diagnosis", ""))),
            dropdown(
                "Its answer, criterion by criterion",
                "\n\n".join(
                    f"**{prose(clean(c['criterion']))}** — `{c['verdict']}`\n\n{quote(c['evidence'])}"
                    for c in ip.get("answers_intent") or []
                ),
            ),
            dropdown(
                "What would fit better: the agent's ranked hypotheses for the remaining misfit",
                "\n\n".join(quote(h) for h in ip.get("misfit_hypotheses") or []),
            ),
        ]
    )


EXPLORE = [
    (
        "md",
        """# Explore the record yourself

The [walkthrough](walkthrough.ipynb) was generated from one file, the run's
*record*. This notebook opens that file and finds the same things directly, to
show what the record holds and how to reach it. In practice you will mostly ask
the front end (Claude Code) about a run and it reads the record for you, with
`./run.sh status`, `show` and `explore`; this is what it reads.

To run it yourself, open it from this folder in a Jupyter kernel using the
repository's environment (`uv sync --group docs`). The outputs below were
produced when the documentation was built.""",
    ),
    (
        "code",
        f"""import sys
from pathlib import Path

REPO = Path.cwd().resolve().parents[3]  # docs/site/examples/ctd_blind -> the repo
sys.path.insert(0, str(REPO))

from octomod.result.node import Node
from octomod.result.runstore import RunStore

store = RunStore(Path("record/{RUN_ID}.h5"))
root = Node(store)  # the record, addressed by key
root.children()""",
    ),
    ("md", "Every part of the run has a **key**. What was asked, and how it ended:"),
    ("code", """print((root / "intent" / "question").get())
(root / "outcome").get()"""),
    (
        "md",
        """The **ledger** is the run's diary: every module, check, agent call and decision,
in order, with timestamps.""",
    ),
    (
        "code",
        """import pandas as pd

ledger = pd.DataFrame(store.ledger_rows())
ledger["event"].value_counts().head(10)""",
    ),
    ("md", "Every agent call, with its round, model, cost and duration:"),
    (
        "code",
        """calls = ledger[ledger["event"] == "agent_call"]
calls[["round", "module", "role", "model_resolved", "prompt_bytes", "cost_usd", "duration_s"]]""",
    ),
    ("md", "Every answer at a gate, and the note that came with it:"),
    (
        "code",
        """ledger[ledger["event"] == "human_gate"][["round", "module", "approved", "note"]]""",
    ),
    (
        "md",
        """Each agent's **prompt** and validated **reply** sit under its round's
`agent_calls`. Here, the start of the prompt the expansion agent received, and
one of the candidates it proposed:""",
    ),
    (
        "code",
        """call = root / "rounds" / "round_0" / "agent_calls" / "expansion"
print(call.child("prompt").text()[:1200])""",
    ),
    (
        "code",
        """candidate = call.child("reply").get()["candidates"][2]
{k: candidate[k] for k in ("id", "label", "adds_parameters")}""",
    ),
    ("md", "The fit of every candidate in both rounds, and each round's model selection:"),
    (
        "code",
        """rows = []
for rnd in ("round_0", "round_1"):
    cands = root / "rounds" / rnd / "candidates"
    for cid in cands.children():
        est = cands.child(cid).child("estimation").get()
        x = est["best_x_unscaled"]
        rows.append({"round": rnd, "candidate": cid, "-log L": est["best_fval"],
                     **{p: x.get(p) for p in ("kmod", "cp", "nb", "kon_I")}})
pd.DataFrame(rows).set_index(["round", "candidate"]).round(4)""",
    ),
    (
        "code",
        """sel = (root / "rounds" / "round_1" / "selection").get()
pd.DataFrame(sel["values"]).T.assign(weight=pd.Series(sel["weights"])).round(3)""",
    ),
    (
        "md",
        """Per data point, the record keeps the measured value beside each candidate's
prediction at its fit — enough to redraw any fit without simulating:""",
    ),
    (
        "code",
        """import re

import matplotlib.pyplot as plt

groups = (root / "rounds" / "round_1" / "attribution" / "per_candidate" / sel["winner"] / "groups").get()
points = []
for key, g in groups.items():
    m = re.match(r"obs_phos(\\d)__sc_ctd_ms_t(\\d+)__", key)
    points.append((int(m.group(2)), int(m.group(1)), g["measured"][0], g["simulated"][0]))
df = pd.DataFrame(points, columns=["time", "phosphates", "measured", "simulated"])
fig, axes = plt.subplots(1, 4, figsize=(11, 2.5))
for ax, (t, d) in zip(axes, df.sort_values("phosphates").groupby("time")):
    ax.bar(d["phosphates"], d["measured"], color="#ddd", label="measured")
    ax.plot(d["phosphates"], d["simulated"], "o-", color="#2ca02c", label=sel["winner"])
    ax.set_title(f"t = {t} min")
axes[0].legend(fontsize=7);""",
    ),
    (
        "md",
        """The same file also loads as one **typed object**, validated against the
schema (`docs/RESULT-SCHEMA.md`), for code that wants attributes rather than
keys:""",
    ),
    (
        "code",
        """run = store.load()
run.outcome.winner, [run.round(k).selection.winner for k in (0, 1)]""",
    ),
    (
        "md",
        f"""From a terminal, the same record reads with the engine's CLI (the run file
must sit in `runs/`):

```bash
./run.sh status  --run-id {RUN_ID}
./run.sh show    --run-id {RUN_ID} rounds/round_1/decisions_md
./run.sh explore --run-id {RUN_ID}     # ls, cd, cat, gates, ledger …
```""",
    ),
]


def write_explore_notebook() -> None:
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(src) if kind == "md" else nbformat.v4.new_code_cell(src)
        for kind, src in EXPLORE
    ]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    # the one page the documentation build executes
    nb.metadata["mystnb"] = {"execution_mode": "force"}
    nbformat.write(nb, HERE / "explore_record.ipynb")


def main() -> int:
    rec = load()
    # figures are written fresh: one from an earlier record must not linger
    for old in FIG.glob("*.svg"):
        old.unlink()
    write_prompt_pages(rec)
    cells = build(rec)
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell(clean(c)) for c in cells]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nbformat.write(nb, HERE / "walkthrough.ipynb")
    write_explore_notebook()
    print(f"wrote {HERE / 'walkthrough.ipynb'}: {len(cells)} cells, figures in {FIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
