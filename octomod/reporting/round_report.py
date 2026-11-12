"""report.html — the round's 13 fixed sections, in order.

`Round` is the round's record loaded once: every section reads it and
nothing re-reads the record. The section order is the REPORTING.md contract, so a
section whose artifact is missing renders a note rather than disappearing and
the numbering never shifts under a front end.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from octomod.orchestration import provenance as _pv
from octomod.reporting.budget import (
    DATA_FLAGS_SHOWN,
    DIAGNOSIS_SENTENCES,
    EPISTEMICS_ENTRIES_SHOWN,
    EPISTEMICS_ENTRY_CHARS,
    GATE_DETAIL_CHARS,
    HYPOTHESES_SHOWN,
    INTENT_EVIDENCE_CHARS,
    MISFIT_REASON_CHARS,
    MISFIT_REASONS_SHOWN,
    clip_chars,
    clip_sentences,
    fold,
)
from octomod.reporting.figures import (
    NOISE_REJECT_P,
    PREDICTIVE_Z,
    STEADY_STATE_NOTE,
    cr_levels,
    data_figure,
    draw_cr_envelopes,
    draw_steady_level,
    figure,
    fit_grid_figure,
    has_steady_state,
    mark_steady_state,
    on_time_axis,
    parameter_bounds_figure,
    profile_figures,
    qq_panel,
    rejects_noise,
    steady_state_x,
    waterfall_figure,
    weights_figure,
)
from octomod.reporting.html import (
    esc,
    group,
    kv,
    load_json,
    load_text,
    load_tsv,
    note,
    note_html,
    num,
    page,
    sec,
    stated,
    table,
    trunc,
    verdict_badge,
)
from octomod.reporting.sbml_view import (
    model_tables_or_note,
    network_figure,
    reaction_count,
)
from octomod.result import node as tree
from octomod.result.node import Node
from octomod.workflow_modules.evaluation import profile_projection

# Ensemble members drawn into the fit band. The band is a min/max envelope, so
# a cap changes it only by shrinking; stated in the figure caption.
_ENSEMBLE_CAP = 12


class Round:
    """Everything the renderer knows, loaded once and defensively.

    For a mechanism-discrimination round the model/petab/estimation records
    live per candidate (`rounds/round_k/candidates/<id>/`); the winner is used
    as the 'effective' candidate so sections 3–7 stay filled and clearly
    labelled, rather than blanking out. A single-model round's fitted problem
    is `candidates/_single` and its model the round's own `model`.
    """

    def __init__(self, rnd: Node):
        self.rnd = rnd
        self.store = rnd.store
        self.root = rnd.parent.parent
        try:
            self.round_idx = tree.round_index(rnd)
        except (IndexError, ValueError):
            self.round_idx = 0

        self.intent = load_json(self.root / "intent") or {}
        self.run_meta = load_json(self.root / "run") or {}
        try:
            self.ledger = self.store.ledger_rows()
        except Exception:
            self.ledger = []

        self.report = load_json(rnd / "evaluation") or {}
        self.core = load_json(rnd / "evaluation_core") or {}
        self.candidates = load_json(rnd / "space" / "candidates") or []

        self.discrimination = (
            self.report.get("discrimination") or self.core.get("discrimination") or {}
        )
        self.cids = tree.candidate_ids(rnd)
        self.is_md = bool(self.discrimination) or bool(self.cids)

        # the effective candidate: None for a single-model round
        self.cid: str | None = None
        if self.is_md and self.cids:
            winner = self.discrimination.get("winner")
            self.cid = winner if winner in self.cids else self.cids[0]
        self.work = tree.work_node(rnd, self.cid)
        self.model = tree.model_node(rnd, self.cid)

        self.goal = (
            self.report.get("goal")
            or self.core.get("goal")
            or self.intent.get("inference_target")
            or "unknown"
        )
        self.interp = self.report.get("interpretation") or {}
        self.summary = load_json(self.work / "estimation") or {}
        self.cost = load_json(self.work / "cost") or {}
        self.assembly = (
            load_json(self.work / "assembly")
            or load_json(rnd / "shared_assembly")
            or {}
        )
        self._tables = "unset"
        self._band_note_shown = False  # the method caption is stated once

    def rows(self, event: str, this_round: bool = True) -> list[dict]:
        return [
            e
            for e in self.ledger
            if e.get("event") == event
            and (not this_round or e.get("round") == self.round_idx)
        ]

    @property
    def run_start(self) -> dict:
        rs = [e for e in self.ledger if e.get("event") == "run_start"]
        return rs[0] if rs else {}

    @property
    def sbml(self) -> str | None:
        return load_text(self.model / "sbml")

    def petab_tables(self):
        """PetabTables for the effective candidate, or None. Cached: building it
        loads the SBML into roadrunner."""
        if self._tables != "unset":
            return self._tables
        self._tables = None
        try:
            from octomod.gates.petab_gates import PetabTables

            p = self.work / "petab"
            sbml = self.sbml
            if sbml is None:
                return None
            self._tables = PetabTables(
                observables=(p / "observables").table(),
                conditions=(p / "conditions").table(),
                measurements=(p / "measurements").table(),
                parameters=(p / "parameters").table(),
                sbml=sbml,
                holdout_measurements=(p / "holdout_measurements").table(None),
            )
        except Exception:
            self._tables = None
        return self._tables

    def measurement_frame(self) -> pd.DataFrame | None:
        """observable / condition / time / value / heldout, from the PEtab
        tables when they exist (they carry the train/holdout split), otherwise
        from the long data table."""
        p = self.work / "petab"
        frames = []
        train = load_tsv(p / "measurements")
        if train is not None and len(train):
            frames.append(_petab_to_frame(train, False))
        hold = load_tsv(p / "holdout_measurements")
        if hold is not None and len(hold):
            frames.append(_petab_to_frame(hold, True))
        if frames:
            return pd.concat(frames, ignore_index=True)
        long = load_tsv(self.rnd / "data" / "measurements")
        if long is not None and len(long):
            try:
                out = pd.DataFrame(
                    {
                        "observable": long["observable_label"].astype(str),
                        "condition": long["condition_label"].astype(str),
                        "time": long["time"].astype(float),
                        "value": long["value"].astype(float),
                        "heldout": False,
                    }
                )
                return out
            except Exception:
                return None
        return None


def _real_profiles(prof) -> dict:
    """Profile entries that are parameters; underscore keys (`_meta`) are metadata.

    Rendered as a parameter, metadata would show as an open interval, a false
    identifiability claim.
    """
    if not isinstance(prof, dict):
        return {}
    return {
        k: v
        for k, v in prof.items()
        if isinstance(k, str) and not k.startswith("_") and isinstance(v, dict)
    }


def _petab_to_frame(df: pd.DataFrame, heldout: bool) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observable": df["observableId"].astype(str),
            "condition": df["simulationConditionId"].astype(str),
            "time": df["time"].astype(float),
            "value": df["measurement"].astype(float),
            "heldout": heldout,
        }
    )


# --- 1 header ---------------------------------------------------------------


def _status_badge(r: Round) -> tuple[str, str]:
    if r.goal == "mechanism_discrimination" or r.is_md:
        d = r.discrimination
        if not d:
            return "flag", "discrimination result unavailable"
        winner = d.get("winner", "?")
        dec = "decisive" if d.get("decisive") else "not decisive"
        return ("pass" if d.get("decisive") else "flag", f"winner: {winner} ({dec})")
    if r.goal == "parameter_values":
        raw = r.report.get("profiles") or r.core.get("profiles")
        prof = _real_profiles(raw)
        left = profile_projection.not_profiled(raw)
        if prof and left:
            return (
                "flag",
                f"profiles stopped at the time cap — {len(prof)}/"
                f"{len(prof) + len(left)} profiled",
            )
        if prof:
            n_fin = sum(1 for p in prof.values() if p.get("ci_finite"))
            return "pass", f"profiles complete — {n_fin}/{len(prof)} CIs finite"
        return "flag", "profiles not recorded"
    if r.goal == "prediction":
        if "t2prime_passed" in r.report:
            ok = bool(r.report["t2prime_passed"])
            return (
                "pass" if ok else "fail",
                f"held-out T2′ {'PASS' if ok else 'FAIL'}",
            )
        return "flag", "T2′ verdict not recorded"
    return "flag", "no verdict recorded for this goal"


def _input_files(root: Node) -> int:
    """How many files the record's `input` snapshot holds: every dataset
    under the group, however deep (a file's path keeps its `/`)."""
    try:
        return sum(1 for _k, kind in root.store.walk("input") if kind == "dataset")
    except Exception:
        return 0


def _inputs_line(r: Round) -> str:
    """One header line: what this run was started with, and where it is.

    A run without an `input` snapshot in its record says where it read its
    inputs instead.
    """
    meta = r.run_meta
    src = meta.get("input_source") or meta.get("testcase") or "(not recorded)"
    src = Path(str(src)).name if str(src).startswith("/") else str(src)
    if not meta.get("input_dir") and not (r.root / "input").exists():
        return f"read in place from {esc(src)} (this run predates input/)"
    sha = str(meta.get("input_sha") or "—")
    # the files in the record, not the hashed subset, so the count matches
    # the listing
    n = _input_files(r.root)
    line = (
        f"<code>input</code> (in {esc(r.store.path.name)}) — {n} file(s), "
        f"sha <code>{esc(sha)}</code>, from {esc(src)}"
    )
    if meta.get("started_from"):
        line += f" · started from run <code>{esc(str(meta['started_from']))}</code>"
    return line


def _s1_header(r: Round) -> str:
    testcase = (
        str(r.run_meta.get("project") or "")
        or Path(str(r.run_meta.get("testcase", ""))).name
        or r.store.run_id
    )
    when = r.run_start.get("ts") or ""
    if not when:
        try:
            import datetime

            when = datetime.datetime.fromtimestamp(
                r.store.path.stat().st_mtime
            ).isoformat(timespec="seconds")
        except Exception:
            when = "unknown"
    models = models_with_effort(r.rows("agent_call", False))
    cls, text = _status_badge(r)
    round_label = r.rnd.name.replace("_", " ")
    return (
        '<header class="hdr">'
        f"<h1>{esc(testcase)} — {esc(round_label)}</h1>"
        f'<p class="sub">{esc(str(r.intent.get("question", "")))}</p>'
        f'<div class="badge {cls}">{esc(text)}</div>'
        + kv(
            [
                ("run id", f"<code>{esc(r.store.run_id)}</code>"),
                ("date", esc(when)),
                ("goal", f"<code>{esc(r.goal)}</code>"),
                ("backend", esc(str(r.run_meta.get("backend", "—")))),
                ("agent models", ", ".join(esc(m) for m in models)),
                ("agent isolation", esc(isolation_line(r.rows("agent_call", False)))),
                (
                    "research",
                    esc(
                        research_line(
                            r.rows("research_fence", False),
                            r.rows("supplied_literature", False),
                            r.rows("grounding_fence", False),
                        )
                    ),
                ),
                ("inputs", _inputs_line(r)),
                (
                    "workflow sha",
                    f"<code>{esc(str(r.run_meta.get('workflow_sha', '—')))}</code>",
                ),
                ("engine", esc(str(r.run_meta.get("engine_version", "—")))),
                # `engine_version` is a static string; the commit and its
                # dirtiness are what identify the code
                ("code", _code_row(r)),
                ("versions", esc(_pv.versions_line(r.run_meta.get("provenance")))),
            ]
        )
        + "</header>"
    )


def models_with_effort(agent_calls: list[dict]) -> list[str]:
    """Each model the run's agents ran as, with its effort: `opus (effort xhigh)`.

    A live row without an effort says "not recorded"; a stub row (a canned
    reply, no CLI behind it) carries none.
    """
    out = set()
    for e in agent_calls:
        m = e.get("model")
        if not m:
            continue
        if e.get("backend") == "stub":
            out.add(str(m))
        else:
            out.add(f"{m} (effort {e.get('effort') or 'not recorded'})")
    return sorted(out) or ["—"]


def research_line(
    rows: list[dict],
    supplied_rows: list[dict] | None = None,
    grounding_rows: list[dict] | None = None,
) -> str:
    """The run's research state as one header line.

    From the ledger's `research_fence` row: the horizon and the forbidden
    sources ("no forbidden sources" is a recorded choice); no row means research
    was off. Plus the literature the human supplied, from `supplied_literature`,
    and, from the `grounding_fence` row, the knowledge module: its mode, the
    support floor, who set it and the step — or the case's declared skip.
    """
    if not rows:
        base = "off"
    else:
        e = rows[-1]
        n = len(e.get("forbidden_sources") or [])
        base = f"on — horizon {e.get('horizon')}, " + (
            "no forbidden sources" if n == 0 else f"{n} forbidden source(s)"
        )
    if supplied_rows:
        n_sup = int(supplied_rows[-1].get("n_items") or 0)
        base += (
            f"; {n_sup} literature item(s) supplied by the human "
            f"(construction and observation model)"
        )
    if grounding_rows:
        e = grounding_rows[-1]
        if e.get("skip"):
            base += f"; knowledge module skipped ({e.get('skip')})"
        elif e.get("mode"):
            floor = str(e.get("support_floor")).replace("_", " ")
            who = "the person's" if e.get("floor_source") == "human" else "the rule's"
            base += (
                f"; knowledge module {e.get('mode')}, support floor {floor} "
                f"({who}), step {e.get('floor_step')}"
                + (
                    f", horizon {e.get('horizon')}"
                    if e.get("horizon") is not None
                    else ""
                )
            )
        else:
            base += (
                f"; reactions grounded in the literature (horizon {e.get('horizon')})"
            )
    return base


def isolation_line(agent_calls: list[dict]) -> str:
    """How this run's agent subprocesses were isolated (cwd and MCP policy).

    One line from the ledger's `agent_call` rows; a stub run and a run whose
    rows carry no policy say so.
    """
    if not agent_calls:
        return "no agent calls"
    if all(e.get("backend") == "stub" for e in agent_calls):
        return "stub backend — no subprocess launched, nothing to isolate"
    live = [e for e in agent_calls if e.get("backend") != "stub"]
    cwd = sorted(
        {str(e.get("call_cwd_policy")) for e in live if e.get("call_cwd_policy")}
    )
    mcp = sorted({str(e.get("mcp_policy")) for e in live if e.get("mcp_policy")})
    if not cwd and not mcp:
        return "not recorded — a run from before these were ledgered (cwd and MCP policy unknown)"
    return f"cwd: {', '.join(cwd) or 'not recorded'} · MCP: {', '.join(mcp) or 'not recorded'}"


def _code_row(r: Round) -> str:
    prov = r.run_meta.get("provenance")
    line = _pv.one_line(prov)
    dirty = ((prov or {}).get("git") or {}).get("dirty")
    if dirty:
        return f'<span class="chip fail">{esc(line)}</span>'
    if dirty is None:
        return f'<span class="chip">{esc(line)}</span>'
    return esc(line)


def _against_the_note(r: Round) -> str:
    """First-screen statement that the selected model contradicts a declared constant.

    A violated declaration does not open the misfit flag by itself (the
    measurements take precedence over the note), so a run can end accepted with
    a model that breaks a stated conservation; the reader meets that first.
    """
    from octomod.workflow_modules.model import declared_constants as dc

    summary = r.core.get("declared_constants") or r.report.get("declared_constants")
    return stated(
        "This model contradicts the experiment's own note",
        dc.verdict_prose(summary or {}),
    )


# --- 2 intent ---------------------------------------------------------------


def _s2_intent(r: Round) -> str:
    if not r.intent:
        return note("intent is missing — the frozen question cannot be shown")
    crit = r.intent.get("success_criteria") or []
    crit_html = (
        ('<ul class="crit">' + "".join(f"<li>{esc(c)}</li>" for c in crit) + "</ul>")
        if crit
        else note("no success criteria declared")
    )
    body = kv(
        [
            ("question", esc(str(r.intent.get("question", "—")))),
            ("system", esc(str(r.intent.get("system", "—")))),
            (
                "inference target",
                f"<code>{esc(str(r.intent.get('inference_target', '—')))}</code>",
            ),
            ("success criteria", crit_html),
        ]
    )
    body += (
        "<details><summary>full frozen intent (JSON)</summary>"
        f"<pre>{esc(json.dumps(r.intent, indent=2))}</pre></details>"
    )
    return body


# --- 3 the model ------------------------------------------------------------


def _s3_model(r: Round) -> str:
    if r.is_md:
        return _s3_model_md(r)
    sbml = r.sbml
    parts = [model_tables_or_note(r.model, sbml)]
    ant = load_text(r.model / "antimony")
    if ant:
        parts.append(
            "<details><summary>Antimony source (model/antimony)</summary>"
            f"<pre>{esc(ant)}</pre></details>"
        )
    else:
        parts.append(note("model/antimony is missing"))
    if sbml is not None:
        parts.append(network_figure(sbml))
    return "".join(parts)


def _s3_model_md(r: Round) -> str:
    labels = {
        c.get("id"): c.get("label", "") for c in r.candidates if isinstance(c, dict)
    }
    rows = []
    for cid in r.cids:
        sbml = load_text(tree.model_node(r.rnd, cid) / "sbml")
        nrxn = reaction_count(sbml) if sbml else None
        win = cid == r.discrimination.get("winner")
        rows.append(
            [
                f"<code>{esc(cid)}</code>"
                + (' <span class="chip pass">winner</span>' if win else ""),
                esc(labels.get(cid, "—")),
                "—" if nrxn is None else str(nrxn),
            ]
        )
    parts = [table(["candidate", "label", "reactions"], rows)]
    winner = r.discrimination.get("winner")
    if r.sbml is not None:
        parts.append(f"<h3>Winner: <code>{esc(str(winner or r.cid))}</code></h3>")
        parts.append(model_tables_or_note(r.model, r.sbml))
        ant = load_text(r.model / "antimony")
        if ant:
            parts.append(
                "<details><summary>Antimony source of the winner "
                "(model/antimony)</summary>"
                f"<pre>{esc(ant)}</pre></details>"
            )
        parts.append(network_figure(r.sbml))
    else:
        parts.append(note("no candidate model/sbml found — network figure skipped"))
    return "".join(parts)


# --- 4 the data -------------------------------------------------------------


def _raw_vs_processed(r: Round, rep: dict) -> str:
    """Raw against processed values for the first observable a processing op touched.

    "" when nothing was processed or either table is missing.
    """
    proc = rep.get("processing") or []
    raw = load_tsv(r.rnd / "data" / "raw")
    long = load_tsv(r.rnd / "data" / "measurements")
    if not proc or raw is None or long is None:
        return ""
    label = str(proc[0].get("labels", ["?"])[0])
    key = ["condition_label", "time", "replicate"]
    try:
        a = raw[raw["observable_label"].astype(str) == label][key + ["value"]]
        b = long[long["observable_label"].astype(str) == label][key + ["value"]]
        m = a.merge(b, on=key, suffixes=("_raw", "_processed")).sort_values(key)
    except Exception:
        return note(
            "processing was declared but raw and processed tables could not be aligned"
        )
    shown = m.head(12)
    rows = [
        [
            esc(str(x.condition_label)),
            num(x.time),
            num(x.replicate, "{:.0f}"),
            num(x.value_raw),
            num(x.value_processed),
        ]
        for x in shown.itertuples()
    ]
    ops = "; ".join(
        f"{e.get('kind')} on {', '.join(e.get('labels', []))}" for e in proc
    )
    return (
        f"<p><b>Processing applied by the engine:</b> {esc(ops)} — raw against "
        f"processed for <code>{esc(label)}</code>"
        f"{' (first 12 rows)' if len(m) > 12 else ''}; the raw table is "
        f"<code>data/raw</code>.</p>"
        + table(["condition", "time", "rep", "raw", "processed"], rows)
    )


def _s4_data(r: Round) -> str:
    df = r.measurement_frame()
    if df is None or not len(df):
        return note(
            "no measurements found (petab/measurements and "
            "data/measurements both unavailable)"
        )
    held = sorted(set(df.loc[df["heldout"], "condition"].astype(str)))
    parts = []
    obs_ids = list(dict.fromkeys(df["observable"].astype(str)))
    for obs in obs_ids:
        sub = df[df["observable"].astype(str) == obs]
        parts.append(data_figure(obs, sub))
    rep = load_json(r.rnd / "data" / "report") or {}
    parts.append(_raw_vs_processed(r, rep))
    rows = []
    for lab in rep.get("observable_labels", []) or []:
        rows.append(
            [
                f"<code>{esc(lab.get('label', '—'))}</code>",
                esc(lab.get("description", "—")),
                esc(lab.get("units", "—")),
                esc(lab.get("error_type", "—")),
                num(lab.get("n"), "{:.0f}"),
            ]
        )
    if rows:
        parts.append(
            table(["label", "description", "units", "error", "replicates"], rows)
        )
    # a donor code or barcode becomes a replicate number, so the page says which
    # label each id stands for; ids are assigned per mapping
    rep_rows = []
    for prov in rep.get("provenance") or []:
        if not isinstance(prov, dict) or not prov.get("replicate_labels"):
            continue
        src = str(
            prov.get("filename") or prov.get("file") or prov.get("locator") or "?"
        )
        for label, rid in sorted(
            prov["replicate_labels"].items(), key=lambda kv: kv[1]
        ):
            rep_rows.append([esc(src.split("/")[-1]), esc(str(label)), esc(str(rid))])
    if rep_rows:
        parts.append(
            "<p><b>Replicate ids</b> — assigned per mapping, so the same id under "
            "two observables need not be the same donor or culture:</p>"
            + table(["file", "replicate label in the file", "id"], rep_rows)
        )
    flags = rep.get("flags") or []
    if flags:
        shown = flags[:DATA_FLAGS_SHOWN]
        parts.append(
            '<div class="flagbox"><b>Flags raised at data extraction '
            f"(flag-never-exclude) — {len(flags)}</b><ul>"
            + "".join(
                f"<li>{esc(clip_chars(f, MISFIT_REASON_CHARS)[0])}</li>" for f in shown
            )
            + "</ul>"
            + (
                fold(
                    f"all {len(flags)} flags, in full",
                    "<ul>" + "".join(f"<li>{esc(f)}</li>" for f in flags) + "</ul>",
                )
                if len(flags) > len(shown)
                or any(clip_chars(f, MISFIT_REASON_CHARS)[1] for f in shown)
                else ""
            )
            + "</div>"
        )
    # declared detection floors: the comparison depends on the source's
    # handling, and the page says so beside the counts
    from octomod.workflow_modules.data import censoring as _cen

    # Read the record S2 wrote, never recount: the frame's observable column
    # holds PEtab ids, not extraction labels. Without the record the counts
    # read "not recorded", never invented zeros.
    declared = _cen.declared(rep)
    cen_rows = rep.get("below_detection_summary") or (
        _cen.summary(declared, None) if declared else []
    )
    if cen_rows:
        counted = sorted({str(r.get("counted_on") or "") for r in cen_rows} - {""})
        parts.append(
            '<div class="flagbox"><b>Below-detection measurements declared at data '
            f"extraction — {len(cen_rows)} observable(s)</b><ul>"
            + "".join(f"<li>{esc(line)}</li>" for line in _cen.findings(cen_rows))
            + "</ul>"
            + (
                f"<p><small>counted on {esc('; '.join(counted))}</small></p>"
                if counted
                else ""
            )
            + f"<p>{esc(_cen.CONDITIONAL_SENTENCE)}</p></div>"
        )
    parts.append(
        kv(
            [
                (
                    "rows",
                    f"{len(df)} ({int((~df['heldout']).sum())} training, "
                    f"{int(df['heldout'].sum())} held out)",
                ),
                ("observables", ", ".join(f"<code>{esc(o)}</code>" for o in obs_ids)),
                (
                    "held-out conditions",
                    ", ".join(f"<code>{esc(c)}</code>" for c in held) or "none",
                ),
            ]
        )
    )
    return "".join(parts)


# --- 5 the estimation problem ----------------------------------------------


def _s5_problem(r: Round) -> str:
    p = r.work / "petab"
    parts = []
    if r.cid:
        parts.append(
            note(
                f"tables shown for the winning candidate "
                f"({r.cid}); every candidate shares the "
                f"same measurements and observables"
            )
        )
    par = load_tsv(p / "parameters")
    if par is None or not len(par):
        parts.append(note("petab/parameters missing"))
        n_est = None
    else:
        rows = []
        for _, row in par.iterrows():
            est = int(row.get("estimate", 0) or 0) == 1
            rows.append(
                [
                    f"<code>{esc(row.get('parameterId', '—'))}</code>",
                    esc(row.get("parameterScale", "—")),
                    f"[{num(row.get('lowerBound'))}, {num(row.get('upperBound'))}]",
                    num(row.get("nominalValue")),
                    (
                        '<span class="chip pass">estimated</span>'
                        if est
                        else '<span class="chip mute">fixed</span>'
                    ),
                ]
            )
        parts.append("<h3>Parameters</h3>")
        parts.append(table(["id", "scale", "bounds", "nominal", "status"], rows))
        try:
            n_est = int((par["estimate"] == 1).sum())
        except Exception:
            n_est = None

    obs = load_tsv(p / "observables")
    if obs is None or not len(obs):
        parts.append(note("petab/observables missing"))
    else:
        rows = [
            [
                f"<code>{esc(row.get('observableId', '—'))}</code>",
                f"<code>{esc(row.get('observableFormula', '—'))}</code>",
                esc(row.get("observableTransformation", "lin")),
                f"<code>{esc(row.get('noiseFormula', '—'))}</code>",
                esc(row.get("noiseDistribution", "—")),
            ]
            for _, row in obs.iterrows()
        ]
        parts.append("<h3>Observables</h3>")
        parts.append(
            table(
                ["id", "formula", "transformation", "noise formula", "distribution"],
                rows,
            )
        )

    cond = load_tsv(p / "conditions")
    if cond is None or not len(cond):
        parts.append(note("petab/conditions missing"))
    else:
        headers = [str(c) for c in cond.columns]
        rows = [
            [f"<code>{esc(v)}</code>" if i == 0 else num(v) for i, v in enumerate(row)]
            for row in cond.itertuples(index=False)
        ]
        parts.append("<h3>Conditions</h3>")
        parts.append(table(headers, rows))

    meas = load_tsv(p / "measurements")
    n_data = len(meas) if meas is not None else r.summary.get("n_data")
    ratio = (
        f"{n_est / n_data:.3f} parameters per data point" if n_est and n_data else "—"
    )
    parts.append(
        kv(
            [
                (
                    "degrees of freedom",
                    f"{num(n_est, '{:.0f}')} estimated parameters vs "
                    f"{num(n_data, '{:.0f}')} training data points ({ratio})",
                ),
            ]
        )
    )
    if r.assembly:
        parts.append(
            "<details><summary>assembly rationales (agent-written, "
            "recorded at S3)</summary>"
            f"<pre>{esc(json.dumps(r.assembly, indent=2))}</pre></details>"
        )
    return "".join(parts)


# --- 6 estimation -----------------------------------------------------------


def _convergence_caveat(r: Round, candidate: str | None = None):
    """The human's accept of a failed convergence check for this candidate, or None.

    Read from the accept row `estimation` ledgers, with its failed checks and reason.
    """
    from octomod.workflow_modules.estimation import convergence_record as _cr

    # `getattr`: a Round can be built without a ledger (partial fixtures, tests),
    # and no ledger means no accepts
    accepts = _cr.accepts_by_candidate(getattr(r, "ledger", None) or [])
    if not accepts:
        return None
    key = candidate or getattr(r, "cid", None) or "model"
    return accepts.get(key) or (accepts.get("model") if not candidate else None)


def _convergence_block(rec) -> str:
    """The estimation section's own paragraph: which checks failed, their
    measured values against their thresholds, and the reason given."""
    from octomod.workflow_modules.estimation import convergence_record as _cr

    rows = "".join(
        f"<li><code>{esc(line.split(':')[0])}</code>: "
        f"{esc(line.split(':', 1)[1].strip())}</li>"
        for line in rec.check_lines()
    )
    return (
        '<div class="note"><b>⚑ CONVERGENCE WAS '
        + ("PRE-DECLARED" if rec.pre_declared else "ACCEPTED")
        + ", NOT DEMONSTRATED.</b><br>"
        + esc(rec.headline())
        + f" for <code>{esc(rec.key)}</code>. The post-fit checks that failed, "
        "with what was measured:"
        f"<ul>{rows}</ul>"
        "Reason given: <i>"
        + esc(rec.reason or "(none recorded)")
        + "</i><br>"
        + esc(_cr.caveat_line(rec).rsplit(". ", 1)[-1])
        + "</div>"
    )


def _optimizer_comparison_block(r: Round) -> str:
    """The optimiser comparison, when one was run for this round.

    Names both metrics and says what they mean: a bare efficiency number is not
    self-explanatory.
    """
    payload = load_json(r.work / "optimizer_comparison")
    if not payload:
        return ""
    v = payload.get("verdict") or {}
    rows = [m for m in payload.get("methods") or [] if m.get("available")]
    if not rows:
        return ""
    rows.sort(key=lambda m: (m.get("optimality_gap") is None, m.get("optimality_gap")))
    inc = v.get("incumbent")
    head = (
        "<tr><th>optimiser</th><th>best −log L</th><th>optimality gap</th>"
        "<th>successful starts</th><th>overall efficiency</th></tr>"
    )
    body = ""
    for m in rows:
        star = " *" if m.get("name") == inc else ""
        oe = m.get("overall_efficiency")
        body += (
            f"<tr><td>{esc(str(m.get('label')))}{star}</td>"
            f"<td>{num(m.get('best_fval'), '{:.6g}')}</td>"
            f"<td>{num(m.get('optimality_gap'), '{:.4g}')}</td>"
            f"<td>{m.get('n_success')}/{m.get('n_attempted')}</td>"
            f"<td>{num(oe, '{:.2f}')}</td></tr>"
        )
    missing = [m for m in payload.get("methods") or [] if not m.get("available")]
    miss_line = ""
    if missing:
        miss_line = (
            "<p>"
            + "; ".join(
                f"<b>{esc(str(m.get('label')))}</b> not compared — {esc(str(m.get('reason')))}"
                for m in missing
            )
            + ". An optimiser that was not installed is NOT a losing optimiser: it is "
        )
        miss_line += "scored on neither metric.</p>"
    # the optimiser the engine chose for the fit, and why
    sel = payload.get("selection") or {}
    sel_line = ""
    if sel:
        how = (
            "chosen from this measured comparison"
            if sel.get("conclusive")
            else "kept as the default — the comparison was inconclusive"
        )
        sel_line = (
            f"<p><b>Optimiser for this fit: <code>{esc(str(sel.get('selected')))}"
            f"</code></b> ({how}). {esc(str(sel.get('reason') or ''))}</p>"
        )

    remedy = str(v.get("remedy") or "")
    remedy_line = ""
    if remedy == "more_starts":
        n95 = v.get("starts_for_95pc")
        remedy_line = (
            f"<p><b>What the numbers point at: MORE STARTS, not a different "
            f"optimiser.</b> {esc(str(v.get('remedy_detail') or ''))}"
            + (" The preset for that is <code>refit more_starts</code>." if n95 else "")
            + "</p>"
        )
    elif remedy == "different_optimizer":
        remedy_line = (
            "<p><b>What the numbers point at: a DIFFERENT OPTIMISER.</b> "
            f"{esc(str(v.get('remedy_detail') or ''))}</p>"
        )
    elif remedy == "none":
        remedy_line = (
            "<p><b>The optimiser is not what is wrong here.</b> "
            f"{esc(str(v.get('remedy_detail') or ''))}</p>"
        )
    if v.get("materially_better"):
        verdict_line = (
            f"<p><b>Another optimiser found a better optimum.</b> "
            f"{esc(str(v.get('winner_label')))} beat <code>{esc(str(inc))}</code> by "
            f"{num(v.get('incumbent_gap'), '{:.4g}')} in −log L, which is outside the "
            f"likelihood-ratio threshold of {num(v.get('threshold'), '{:.3g}')} — the "
            f"data can tell these two results apart.</p>"
        )
    elif v.get("incumbent_is_best"):
        verdict_line = (
            f"<p><code>{esc(str(inc))}</code> found the best value any method found. "
            f"Differences below are in cost, not in the answer.</p>"
        )
    else:
        verdict_line = (
            f"<p>The methods ended within the likelihood-ratio threshold of each "
            f"other ({num(v.get('threshold'), '{:.3g}')}), so the data cannot "
            f"distinguish their results. Any difference below is cost, not "
            f"correctness.</p>"
        )
    return (
        '<div class="flagbox"><b>Optimiser comparison</b>'
        f"<table>{head}{body}</table>"
        "<p><i>Optimality gap</i>: this method's best objective minus the best any "
        "method reached — 0 for the winner. <i>Overall efficiency</i>: 1 is best, and "
        "1/OE is how many times longer this method must run to buy one successful "
        "start. A start is <i>successful</i> when it lands within the likelihood-ratio "
        "threshold of the best value found.</p>"
        f"{sel_line}{verdict_line}{remedy_line}{miss_line}"
        "<p>* the optimiser this fit used. The comparison ran on a fraction of the "
        "estimation budget: a method can win here and lose at full start count.</p>"
        "</div>"
    )


def _s6_estimation(r: Round) -> str:
    s = r.summary
    # built before the missing-summary return: an accepted fit whose
    # estimation summary is missing is where the caveat matters most
    _acc = _convergence_caveat(r)
    caveat = _convergence_block(_acc) if _acc is not None else ""
    if not s:
        return caveat + note(
            "estimation summary missing — no waterfall, no cost numbers"
        )
    # first, above the waterfall: the caveat comes before the fit numbers
    parts = [caveat] if caveat else []
    # so does an optimiser comparison bought at the convergence gate
    cmp_block = _optimizer_comparison_block(r)
    if cmp_block:
        parts.append(cmp_block)
    parts.append(waterfall_figure(s))
    par = load_tsv(r.work / "petab" / "parameters")
    parts.append(parameter_bounds_figure(par, s))
    parts.append(
        kv(
            [
                ("optimizer", f"<code>{esc(str(s.get('optimizer', '—')))}</code>"),
                ("seed", num(s.get("seed"), "{:.0f}")),
                ("starts", num(s.get("n_starts"), "{:.0f}")),
                ("best −log L", num(s.get("best_fval"), "{:.6g}")),
                (
                    "projected gradient norm at best",
                    num(s.get("best_projected_grad_norm", s.get("best_grad_norm"))),
                ),
                ("raw gradient norm at best", num(s.get("best_grad_norm"))),
                (
                    "parked at a bound, gradient out of the box",
                    ", ".join(
                        f"<code>{esc(p['id'])}</code> ({esc(p['edge'])})"
                        for p in (s.get("grad_at_active_bounds") or [])
                    )
                    or "none",
                ),
                (
                    "ensemble members (Δ ≤ "
                    f"{num(s.get('ensemble_delta_nllh'), '{:.3g}')})",
                    num(len(s.get("ensemble") or []), "{:.0f}"),
                ),
                (
                    "parameters at bounds",
                    ", ".join(
                        f"<code>{esc(x)}</code>" for x in (s.get("at_bounds") or [])
                    )
                    or "none",
                ),
                (
                    "parameters NEAR a bound",
                    ", ".join(
                        f"<code>{esc(nb['id'])}</code> at "
                        f"{float(nb['position']):.0%} of its box "
                        f"({esc(nb['edge'])} edge)"
                        for nb in (s.get("near_bounds") or [])
                    )
                    or "none",
                ),
            ]
        )
    )
    # a collapsed ensemble is a MISSING instrument, not evidence of
    # identifiability — S7 says so explicitly and the report must not bury it
    rp = r.report.get("parameters") or r.core.get("parameters") or {}
    if isinstance(rp, dict) and rp.get("uncertainty_assessed") is False:
        parts.append(
            '<div class="flagbox"><b>Parameter uncertainty was not assessed by '
            "this multistart.</b><br>"
            + esc(
                str(
                    rp.get(
                        "note",
                        "the multistart ensemble carries no "
                        "identifiability information in either "
                        "direction",
                    )
                )
            )
            + "</div>"
        )
    c = r.cost
    if c:
        ms = c.get("objective_eval_s")
        parts.append("<h3>Cost profile (measured before the spend gate)</h3>")
        parts.append(
            kv(
                [
                    ("compile", f"{num(c.get('compile_s'), '{:.3g}')} s"),
                    (
                        "objective evaluation",
                        f"{num(None if ms is None else ms * 1000.0, '{:.3g}')} ms",
                    ),
                    (
                        "median wall per start",
                        f"{num(c.get('median_start_s'), '{:.3g}')} s",
                    ),
                    (
                        "projected wall",
                        f"{num(c.get('projected_wall_s'), '{:.3g}')} s",
                    ),
                    ("proposed starts", num(c.get("proposed_n_starts"), "{:.0f}")),
                ]
            )
        )
        # the failed probe starts and what AMICI said, as the budget card had it
        from octomod.workflow_modules.cost_probe import solver_messages as _msgs

        said = _msgs.card_lines(c.get("solver_messages"))
        if said:
            parts.append(
                note(said[0])
                + '<ul class="ran">'
                + "".join(f"<li>{esc(line.strip())}</li>" for line in said[1:])
                + "</ul>"
            )
    else:
        parts.append(note("cost profile (cost) missing"))
    return "".join(parts)


# --- 7 fit ------------------------------------------------------------------


def _s7_fit(r: Round) -> str:
    tables = r.petab_tables()
    if tables is None:
        return note(
            "PEtab tables or model/sbml unavailable — the fit grid "
            "cannot be simulated"
        )
    best = (
        r.summary.get("best_x_unscaled")
        or (r.report.get("parameters") or {}).get("best")
        or {}
    )
    if not isinstance(best, dict) or not best:
        return note(
            "no best parameter vector recorded — the fit grid cannot " "be simulated"
        )
    df = r.measurement_frame()
    if df is None or not len(df):
        return note("no measurements to plot against")
    ensemble = [m.get("x_unscaled", {}) for m in (r.summary.get("ensemble") or [])]
    ensemble = [e for e in ensemble if isinstance(e, dict) and e][:_ENSEMBLE_CAP]

    # S7 draws the predictive band from the profile confidence region when
    # profiles exist, and from the multistart ensemble otherwise. The figure
    # must depict whichever one the evaluation actually scored against, or it
    # would contradict the numbers in section 8.
    pu = (
        r.report.get("prediction_uncertainty")
        or r.core.get("prediction_uncertainty")
        or {}
    )
    cr_bands = pu.get("bands") if isinstance(pu, dict) else None

    parts = []
    if r.cid:
        parts.append(note(f"fit of the winning candidate ({r.cid})"))
    parts.append(fit_grid_figure(tables, best, ensemble, df, cr_bands))
    parts.append(_band_method_note(r, pu, cr_bands))
    if cr_bands:
        parts.append(
            note(
                "Nested envelopes: the light band is the 95% confidence region, "
                "the darker one nested inside it the 90%; the line is the best "
                "fit. Open symbols mark held-out conditions, which took no part "
                "in the fit."
            )
        )
    else:
        parts.append(
            note(
                f"Band = min/max over up to {_ENSEMBLE_CAP} ensemble members "
                f"± {PREDICTIVE_Z} σ, σ resolved from the PEtab noise chain at the "
                f"best fit — the fallback when no profile confidence region is "
                f"available. A collapsed ensemble makes this band σ-only: see the "
                f"uncertainty note in section 6. Open symbols mark held-out "
                f"conditions, which took no part in the fit."
            )
        )
    return "".join(parts)


def _band_method_note(r: Round, pu: dict, cr_bands) -> str:
    """State the band's provenance once, where the bands first appear."""
    if not cr_bands or r._band_note_shown:
        return ""
    r._band_note_shown = True
    method = str(
        pu.get("method") or "profile-CI box sampling with " "joint-threshold rejection"
    )
    df = pu.get("df")
    # n_kept counts the retained profile skeleton as well as the accepted box
    # samples, so it is never quoted against n_box_samples alone; the split
    # fields are used when present
    box = pu.get("n_kept_box_samples")
    skel = pu.get("n_kept_skeleton")
    kept = pu.get("n_kept")
    acc = pu.get("acceptance")
    detail = ""
    n_box = pu.get("n_box_samples", "?")
    if pu.get("skeleton_only"):
        # no samples were drawn, so a "kept 0 of 0" count would say nothing
        if isinstance(skel, dict) and skel:
            detail = (
                "; built from "
                + ", ".join(f"{v} skeleton point(s) at α={k}" for k, v in skel.items())
                + ", no rejection samples"
            )
        else:
            detail = "; built from the profile skeleton, no rejection samples"
    elif isinstance(box, dict) and box:
        detail = (
            "; kept "
            + ", ".join(f"{v} at α={k}" for k, v in box.items())
            + f" of {n_box} box samples"
        )
        if isinstance(skel, dict) and any(skel.values()):
            detail += ", plus " + ", ".join(
                f"{v} skeleton point(s) at α={k}" for k, v in skel.items()
            )
    elif isinstance(kept, dict) and kept:
        detail = (
            "; kept "
            + ", ".join(f"{v} at α={k}" for k, v in kept.items())
            + f", from {n_box} box samples and the profile skeleton"
        )
    elif kept is not None:
        detail = f"; kept {kept}, from {n_box} box samples and the profile skeleton"
    # None marks an alpha with no samples to accept: there is no rate to quote
    rates = [v for v in acc.values() if v is not None] if isinstance(acc, dict) else []
    if rates:
        detail += "; acceptance " + ", ".join(
            f"{v:.0%}" if isinstance(v, (int, float)) else str(v) for v in rates
        )
    out = note(
        f"parameter uncertainty: {method}"
        + (f" (df={df})" if df is not None else "")
        + "; observation noise added where bands meet data"
        + detail
    )
    caveat = pu.get("note")
    if caveat:
        out += (
            '<div class="flagbox"><b>Sampling caveat</b> — ' f"{esc(str(caveat))}</div>"
        )
    # a region traced by the profile skeleton alone is undersampled: the band
    # is narrower than the region, and the report says so beside it
    skeleton_only = pu.get("skeleton_only_note")
    if pu.get("skeleton_only") or skeleton_only:
        out += (
            '<div class="flagbox"><b>Confidence region undersampled</b> — '
            f"{esc(str(skeleton_only or 'built from the profile skeleton alone'))}"
            "</div>"
        )
    # a band traced over the outer parameters only is narrower than the truth:
    # a prediction on the measured scale inherits the scaling's uncertainty
    outer_only = pu.get("outer_only_note")
    if outer_only:
        out += (
            '<div class="flagbox"><b>Band covers the outer parameters only'
            f"</b> — {esc(str(outer_only))}</div>"
        )
    return out


# --- 8 evaluation -----------------------------------------------------------


def _s8_fit_metrics(r: Round) -> str:
    """How well the SELECTED model fits the data it was fitted to."""
    parts: list[str] = []
    fit = r.report.get("fit") or r.core.get("fit") or []
    parts.append("<h4>Fit metrics</h4>")
    if fit:
        rows = [
            [
                f"<code>{esc(f.get('observable', '—'))}</code>",
                f"<code>{esc(f.get('condition', '—'))}</code>",
                num(f.get("n"), "{:.0f}"),
                num(f.get("rmse"), "{:.4g}"),
                num(f.get("nrmse"), "{:.4g}"),
                num(f.get("residual_lag1_autocorr"), "{:.3f}"),
            ]
            for f in fit
        ]
        parts.append(
            table(
                ["observable", "condition", "n", "RMSE", "nRMSE", "lag-1 autocorr"],
                rows,
            )
        )
        chi2 = r.report.get("chi2_per_dof", r.core.get("chi2_per_dof"))
        parts.append(kv([("χ² per degree of freedom", num(chi2))]))
    elif r.is_md:
        parts.append(
            note(
                "per-candidate fit metrics are not written for "
                "discrimination rounds; the AIC table above is the "
                "comparison of record"
            )
        )
    else:
        parts.append(note("the evaluation record carries no fit block"))
    return "".join(parts)


def _s8_holdout(r: Round) -> str:
    """The held-out prediction — the primary gate for the prediction goal, and
    the only number here that was not fitted."""
    parts: list[str] = []
    hold = r.report.get("holdout") or r.core.get("holdout") or {}
    parts.append("<h4>Held-out prediction (T2′)</h4>")
    if hold.get("available") and hold.get("groups"):
        parts.append(_holdout_figure(r, hold["groups"]))
        rows = [
            [
                f"<code>{esc(g.get('label', '—'))}</code>",
                num(g.get("n"), "{:.0f}"),
                num(g.get("rmse"), "{:.4g}"),
                num(g.get("nrmse"), "{:.4g}"),
                num(
                    (
                        None
                        if g.get("band_coverage") is None
                        else g["band_coverage"] * 100.0
                    ),
                    "{:.0f}%",
                ),
                num(g.get("band_rel_width"), "{:.3f}"),
            ]
            for g in hold["groups"]
        ]
        parts.append(
            table(
                [
                    "held-out group",
                    "n",
                    "RMSE",
                    "nRMSE",
                    "band coverage",
                    "band rel. width",
                ],
                rows,
            )
        )
    elif hold.get("available") and hold.get("model_averaged"):
        rows = [
            [
                f"<code>{esc(g.get('label', '—'))}</code>",
                num(g.get("rmse")),
                num(g.get("nrmse")),
            ]
            for g in hold["model_averaged"]
        ]
        parts.append("<p><b>Model-averaged held-out prediction</b></p>")
        parts.append(table(["group", "RMSE", "nRMSE"], rows))
    else:
        parts.append(note(str(hold.get("note", "no held-out evaluation recorded"))))
    return "".join(parts)


def _s8_profiles(r: Round) -> str:
    """Per-parameter likelihood profiles: what the data pinned down."""
    parts: list[str] = []
    prof = _real_profiles(r.report.get("profiles") or r.core.get("profiles"))
    parts.append("<h4>Profile likelihood</h4>")
    if prof:
        best = (
            r.summary.get("best_x_unscaled")
            or (r.report.get("parameters") or {}).get("best")
            or {}
        )
        with_path = {
            k: v
            for k, v in prof.items()
            if isinstance(v, dict) and (v.get("path") or {}).get("x_unscaled")
        }
        if with_path:
            parts.append(
                profile_figures(with_path, best if isinstance(best, dict) else {})
            )
        else:
            parts.append(
                note(
                    "this round's evaluation record carries interval endpoints only — no "
                    "profile paths — so the CI table below stands in for the "
                    "profile plots. Runs from the current engine persist the curve."
                )
            )
        rows = [
            [
                f"<code>{esc(pid)}</code>",
                f"[{num((p.get('ci95') or [None, None])[0])}, "
                f"{num((p.get('ci95') or [None, None])[1])}]",
                (
                    '<span class="chip pass">finite</span>'
                    if p.get("ci_finite")
                    else '<span class="chip fail">open</span>'
                ),
                (
                    num(p.get("ci_width_decades"), "{:.3f}")
                    if p.get("ci_width_decades") is not None
                    else f'<span class="chip mute">{esc(str(p.get("ci_scale", "lin")))} '
                    f'scale — {num(p.get("ci_width_scaled"), "{:.4g}")} wide</span>'
                ),
                (
                    f'{num(p.get("ci_box_fraction"), "{:.0%}")}'
                    if p.get("ci_box_fraction") is not None
                    else "—"
                ),
                (
                    '<span class="chip mute">curve</span>'
                    if pid in with_path
                    else '<span class="chip mute">endpoints only</span>'
                ),
            ]
            for pid, p in prof.items()
        ]
        parts.append(
            table(
                [
                    "parameter",
                    "95% CI",
                    "closed?",
                    "width (decades)",
                    "of its box",
                    "stored",
                ],
                rows,
            )
        )
        parts.append(
            note_html(
                "A width is a DECADE count only for a parameter estimated on a "
                "log scale, where it is a ratio; for a linear one the width is "
                "in the parameter's own units and a decade count would be "
                "meaningless (a CI straddling zero has no ratio). <b>The last "
                "column is the comparable one</b>: what fraction of the prior "
                "box the data left. A blocking gate is raised only where the "
                "answer is a fact — a profile that never closes did not bound "
                "its parameter — and where the data clearly narrowed the box. "
                "Everything between is reported, not adjudicated, for the same "
                "reason the FIM here is given as a spectrum and "
                "never a rank verdict."
            )
        )
        raw = r.report.get("profiles") or r.core.get("profiles") or {}
        meta = raw.get("_meta") if isinstance(raw, dict) else None
        left = profile_projection.not_profiled(raw)
        if left:
            stop = (meta or {}).get("not_profiled") or {}
            parts.append(
                note(
                    f"not profiled: time cap — {', '.join(left)}. The automatic "
                    f"profiling stopped after "
                    f"{profile_projection.duration(stop.get('elapsed_s') or 0)}, "
                    f"before a batch that would have taken it past the "
                    f"{float(stop.get('cap_s') or 0):.0f}s cap on the low "
                    f"estimate; `profiles` at the verdict card continues with "
                    f"them ("
                    + profile_projection.describe(stop.get("remaining"), "projected")
                    + ")."
                )
            )
        timing = (meta or {}).get("timing") if isinstance(meta, dict) else None
        if isinstance(timing, dict) and timing.get("per_point_s"):
            parts.append(
                note(
                    f"measured: {int(timing.get('points') or 0):,} profile points "
                    f"in {profile_projection.duration(timing.get('wall_s') or 0)} "
                    f"on {timing.get('workers')} worker(s), "
                    f"{float(timing['per_point_s']):.2g} s per point"
                    + _projected_before(r)
                )
            )
    else:
        skipped = r.report.get("profiles_skipped") or r.core.get("profiles_skipped")
        proj = (
            (r.core.get("profiles_on_request") or {}).get("projection")
            or r.core.get("profiles_projection")
            or {}
        )
        parts.append(
            note(
                (
                    f"profiles not run: {skipped}"
                    if skipped
                    else "no profiles in this round (they run for the parameter_values goal, "
                    "and automatically for the prediction goal when the measured cost "
                    "is under the workflow's auto cap)"
                )
                + (
                    f" — {profile_projection.describe(proj)}"
                    if isinstance(proj, dict)
                    and proj.get("available")
                    and "profiles projected" not in str(skipped or "")
                    else ""
                )
            )
        )
    return "".join(parts)


def _projected_before(r: Round) -> str:
    """The projection the profiling started from, beside what it measured."""
    raw = r.report.get("profiles") or r.core.get("profiles") or {}
    meta = raw.get("_meta") if isinstance(raw, dict) else None
    proj = (
        (meta.get("projection") if isinstance(meta, dict) else None)
        or r.core.get("profiles_projection")
        or r.report.get("profiles_projection")
    )
    if not isinstance(proj, dict) or not proj.get("available"):
        return ""
    return f"; before it ran, {profile_projection.describe(proj)}"


def _s8_evaluation(r: Round) -> str:
    """Section 8, as three groups of subsections rather than a flat list.

    What won and why, then how far to trust it, then what is still wrong: the
    order a modeller asks in. Grouping rather than splitting keeps the
    13-section numbering intact.
    """
    parts = []

    parts.append(
        group(
            "What won, and why",
            "the choice, the evidence that bought it, and how well the chosen "
            "model actually fits — including the data it never saw.",
        )
    )
    if r.is_md:
        parts.append(_md_evaluation(r))
    parts.append(_s8_fit_metrics(r))
    parts.append(_s8_holdout(r))

    parts.append(
        group(
            "How far to trust it",
            "what the data pinned down and what they did not: intervals per "
            "parameter, and which parameter COMBINATIONS the data barely "
            "constrain.",
        )
    )
    parts.append(_s8_profiles(r))
    parts.append(_identifiability(r))
    parts.append(_structural_flat(r))

    parts.append(
        group(
            "What is still wrong",
            "the checks that could contradict the choice above — and, where "
            "one found nothing, that it ran.",
        )
    )
    parts.append(_s8_noise_check(r))
    parts.append(_misfit_evidence(r))
    parts.append(_residual_forms_line(r))
    parts.append(_checks_that_ran(r))
    return "".join(parts)


def _residual_forms_line(r: Round) -> str:
    """One line: the strongest residual's functional form, and where the rest are.

    Written by S7 at the round's `residual_forms`; a round without it (an
    older run, or no fitted series) shows nothing.
    """
    forms = load_json(r.rnd / "residual_forms") or {}
    summary = (
        [str(x) for x in (forms.get("summary") or [])]
        if isinstance(forms, dict)
        else []
    )
    if not summary:
        return ""
    more = (
        f" {len(summary) - 1} more sentence(s), one per observable and stimulus, "
        f"in the round's <code>residual_forms</code> record."
        if len(summary) > 1
        else ""
    )
    return note_html(
        "<b>Residual shape</b> (functional form by small-sample AICc, the "
        "strongest first): " + esc(summary[0]) + more
    )


def _checks_that_ran(r: Round) -> str:
    """One line per screen that ran and found nothing.

    Otherwise "nothing wrong" and "nobody looked" read the same. The wording is
    the gate card's, so the two surfaces cannot drift.
    """
    from octomod.workflow_modules.evaluation import latent_states as ls

    lines: list[str] = []
    latent = r.core.get("latent_states") or r.report.get("latent_states") or {}
    if latent:
        said = ls.card_lines(latent)
        lines += said or [
            "latent-state screen: no condition could be simulated at the fit — "
            "the states nobody measured were NOT checked"
        ]

    constants = r.core.get("declared_constants") or r.report.get("declared_constants")
    if constants is not None:
        rows = (constants or {}).get("rows") or []
        if not rows:
            # `dc.card_lines` is silent when nothing was declared (noise on a
            # gate card); in the report an absent check must not read as passed
            lines.append(
                "declared constants: none were declared, so nothing was "
                "checked against the note"
            )
        else:
            # collapsed per expression, not per row: a declaration is measured
            # once per condition, and `dc.card_lines` lists rows
            exprs = sorted({str(row.get("expression", "?")) for row in rows})
            worst = (constants or {}).get("worst_drift")
            violated = (constants or {}).get("violated") or 0
            measured = (constants or {}).get("measured") or 0
            tol = min(
                (float(row["tolerance"]) for row in rows if row.get("tolerance")),
                default=None,
            )
            if violated:
                # the loud surface is the statement on the first screen; this
                # line points at it rather than saying it again in small type
                lines.append(
                    f"declared constants: {violated} of {measured} "
                    f"measurement(s) of {', '.join(exprs)} contradict the note "
                    f"— stated in full at the top of this report"
                )
            else:
                lines.append(
                    f"declared constants: {', '.join(exprs)} held at the fit in "
                    f"all {measured} measurement(s)"
                    + (
                        f" — worst drift {float(worst):.1%}"
                        if worst is not None
                        else ""
                    )
                    + (f" against a {tol:.0%} tolerance" if tol is not None else "")
                )
            unmeasured = (constants or {}).get("unmeasured") or 0
            if unmeasured:
                lines.append(
                    f"{unmeasured} declared constant(s) could not be measured "
                    f"at the fit — an empty measurement is not a pass"
                )
    if not lines:
        return ""
    return (
        "<h4>Checks that ran</h4>"
        + note(
            "screens whose whole result is an absence. Listed so a reader can "
            "tell a check that passed from a check that never happened."
        )
        + '<ul class="ran">'
        + "".join(f"<li>{esc(line)}</li>" for line in lines)
        + "</ul>"
    )


def _identifiability(r: Round) -> str:
    """The information spectrum at the MLE, never a rank verdict.

    Rank deficiency proves local non-identifiability; full rank proves nothing,
    at one point and under a condition number that makes the tolerance a
    judgement call. So the spread and the flat combinations are reported.
    """
    ident = r.core.get("identifiability") or r.report.get("identifiability") or {}
    if not ident:
        return ""
    if not ident.get("available"):
        return note(
            "information spectrum at the MLE not available: "
            + str(ident.get("note", "no reason recorded"))
        )
    eig = [v for v in (ident.get("eigenvalues_log10") or []) if v is not None]
    flat = ident.get("flat_directions") or []
    head = "<h4>Information spectrum at the MLE</h4>" + kv(
        [
            ("free parameters", num(ident.get("n_free"), "{:.0f}")),
            ("eigenvalue spread", f"{num(ident.get('spread_decades'))} decades"),
            (
                "largest / smallest (log10)",
                f"{num(eig[0])} / {num(eig[-1])}" if eig else "—",
            ),
            ("computed by", esc(str(ident.get("method", "—")))),
            (
                "flat combinations",
                f"{len(flat)} beyond "
                f"{num(ident.get('flat_decades_threshold'))} decades",
            ),
        ]
    )
    body = ""
    if flat:
        body = table(
            ["direction", "decades below the largest", "reads as"],
            [
                [
                    num(d.get("index"), "{:.0f}"),
                    num(d.get("decades_below_largest")),
                    f"<code>{esc(str(d.get('reads_as', '')))}</code>",
                ]
                for d in flat
            ],
        )
    return (
        head
        + body
        + note(
            "A SPECTRUM, not a rank. A direction many decades below the largest "
            "is a parameter combination the data barely constrain; a spectrum "
            "with no such direction proves nothing, because this is a local "
            "screen at one point. A model can be comprehensively "
            "non-identifiable and still predict well — the flat combinations "
            "and the prediction bands are two halves of one sentence, and "
            "neither blocks unless the intent says parameter values are the "
            "deliverable."
        )
    )


def _structural_flat(r: Round) -> str:
    """The structural flat directions found before the fit, as they stand at it.

    Before the fit they are measured near the nominal parameter values; at the
    fit, around the MLE. One table, so a direction found in one place and not
    the other reads as a row, not as two sections that disagree.
    """
    from octomod.workflow_modules.evaluation import structural_nulls as _sn

    ident = r.core.get("identifiability") or r.report.get("identifiability") or {}
    rec = ident.get("structural_recheck") if isinstance(ident, dict) else None
    if not rec:
        return ""
    head = "<h4>Structural flat directions, before the fit and at it</h4>"
    line = _sn.recheck_line(rec) or ""
    if not rec.get("available"):
        return head + note(line)
    rows = []
    for d in rec.get("directions") or []:
        ok = d.get("confirmed_at_mle")
        at_fit = (
            "flat at the fit too"
            if ok is True
            else (
                "not flat at the fit: relative singular value "
                f"{num(d.get('relative_singular_value_at_mle'), '{:.1e}')} there"
                if ok is False
                else esc(str(d.get("why") or "not tested"))
            )
        )
        rows.append(
            [
                f"<code>{esc(str(d.get('reads_as', '')))}</code>",
                num(d.get("relative_singular_value_before"), "{:.1e}"),
                at_fit,
            ]
        )
    for d in rec.get("flat_at_mle_only") or []:
        rows.append(
            [
                f"<code>{esc(str(d.get('reads_as', '')))}</code>",
                "not found",
                "flat at the fit "
                f"({num(d.get('relative_singular_value'), '{:.1e}')} of the "
                "largest)",
            ]
        )
    body = (
        table(["direction", "before the fit (near the nominal)", "at the fit"], rows)
        if rows
        else ""
    )
    return (
        head
        + note(line)
        + body
        + note(
            "A structural direction is flat at every parameter value, so it is "
            "flat near the nominal and around the optimum alike; one flat in "
            "only one of the two places is local, not structural. An indicator: "
            "AIC and BIC charge every estimated parameter. Method: "
            + str(rec.get("method", "—"))
            + " (the candidate's `structural_nulls_at_mle` record)."
        )
    )


def _misfit_evidence(r: Round) -> str:
    """Structural-misfit indicators as a signal row, not a paragraph.

    Measured against the assay's own replicate repeatability, so these are
    informative rather than decisive: the traffic light says which signals
    fired, and each reason is one line with its full wording a fold away.
    """
    ev = r.core.get("misfit_evidence") or r.report.get("misfit_evidence") or {}
    if not ev:
        return ""
    reasons = [str(x) for x in (ev.get("reasons") or [])]
    also = [str(x) for x in (ev.get("also_seen") or [])]
    signals = ev.get("signals") or {}
    if not signals:
        # No per-signal breakdown recorded: name the signals the reasons
        # mention, so the row still says which of the three fired.
        joined = " ".join(reasons).lower()
        signals = {
            k: any(w in joined for w in words)
            for k, words in (
                ("residual structure", ("structure", "runs", "autocorrel")),
                ("repeatability", ("repeatab", "replicate")),
                ("held-out error", ("held-out", "holdout", "nrmse")),
            )
        }
    lights = "".join(
        f'<div class="tl-sig"><span class="tl-dot {"on" if on else "off"}">'
        f"</span>{esc(str(name))}</div>"
        for name, on in signals.items()
    )
    shown = reasons[:MISFIT_REASONS_SHOWN]
    clipped = [clip_chars(x, MISFIT_REASON_CHARS) for x in shown]
    head = "<h4>Structural misfit indicators" + (
        '<span class="count">open</span></h4>'
        if ev.get("open")
        else '<span class="count">quiet</span></h4>'
    )
    body = f'<div class="tl">{lights}</div>' if lights else ""
    if shown:
        body += "<ul>" + "".join(f"<li>{esc(v)}</li>" for v, _ in clipped) + "</ul>"
    elif not lights:
        return ""
    if len(reasons) > len(shown) or any(c for _, c in clipped):
        body += fold(
            f"all {len(reasons)} indicators, in full",
            "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in reasons) + "</ul>",
        )
    if also:
        # reported, and explicitly NOT counted: the residual-shape screen has a
        # deliberately loose threshold, so on its own it is something to look
        # at rather than a finding
        body += note(
            "also seen, and not counted as an indicator: "
            + "; ".join(clip_chars(x, MISFIT_REASON_CHARS)[0] for x in also)
            + " — this screen corroborates a harder signal and does not open "
            "the misfit flag on its own."
        )
    # every indicator's distance from its threshold, fired or not: the lights
    # and "quiet" are verdicts, and this table is the measurement behind them,
    # so it sits above the caveat rather than behind a fold
    from octomod.workflow_modules.evaluation import misfit_margins as _mm

    rows = _mm.margins(ev)
    if rows:
        body += table(
            ["indicator", "measured", "threshold", "fired?", "how close"],
            [
                [
                    esc(e["indicator"]),
                    ("—" if e["value"] is None else f"{e['value']:.4g}"),
                    ("—" if e["threshold"] is None else f"{e['threshold']:.4g}"),
                    (
                        '<span class="chip fail">fired</span>'
                        if e["fired"]
                        else '<span class="chip">no</span>'
                    ),
                    (
                        "not measured"
                        if e["closeness"] is None
                        else f"{e['closeness']:.0%} of the way there"
                    ),
                ]
                for e in rows
            ],
        )
        nearest = _mm.nearest(ev)
        if nearest and not ev.get("open"):
            body += note_html(
                "No indicator fired. The closest was <b>"
                + esc(nearest["indicator"])
                + "</b> — "
                + esc(nearest["reads_as"])
                + ". A quiet indicator is not a statement that the structure "
                "is complete: the verdict gate offers another round either "
                "way, and the decision is yours."
            )
        body += fold(
            "how 'how close' is computed",
            note_html(
                "One number so the indicators can be ranked against each "
                "other, since two are ceilings and one is a p-value: for a "
                "ceiling it is <code>value / threshold</code>, for a p-value "
                "<code>alpha / p</code>. At or above 100% the indicator "
                "fired. Thresholds are the ones this round applied, read "
                "from the <code>evaluation</code> record; a run from before they "
                "were recorded there has none, and the table says so."
            ),
        )

    return (
        head
        + body
        + note(
            "Measured against the assay's own replicate repeatability — "
            "informative, not decisive. The residual figures above carry "
            "the argument; full values are in the evaluation record."
        )
    )


def _s8_noise_check(r: Round) -> str:
    """Post-fit residuals against the noise model the problem assumed.

    A fit can be good and its noise model still wrong; this sub-block says which.
    """
    nc = r.report.get("noise_check") or r.core.get("noise_check") or {}
    head = "<h4>Noise-model check</h4>"
    if not isinstance(nc, dict) or not nc:
        return head + note(
            "no residual noise-model test recorded for this "
            "round (older runs predate the check)"
        )
    panels = "".join(
        qq_panel(str(obs), d if isinstance(d, dict) else {}) for obs, d in nc.items()
    )
    rejected = [
        str(obs)
        for obs, d in nc.items()
        if isinstance(d, dict) and rejects_noise(d.get("p_value"))
    ]
    lead = note(
        "Standardized residuals against the quantiles the assumed noise model "
        f"predicts; points on the dashed identity line mean the assumption "
        f"holds. A panel is flagged when p < {NOISE_REJECT_P}."
    )
    tail = ""
    if rejected:
        tail = (
            '<div class="flagbox"><b>Assumed noise model rejected for '
            + ", ".join(f"<code>{esc(o)}</code>" for o in rejected)
            + ".</b> The fit metrics above are conditioned on a noise model "
            "the residuals do not support, so the σ-dependent quantities "
            "(χ²/dof, band coverage, profile widths) should be read with "
            "that in mind.</div>"
        )
    return head + lead + f'<div class="qqgrid">{panels}</div>' + tail


def _holdout_figure(r: Round, groups: list[dict]) -> str:
    """The held-out conditions alone, with the band that coverage is scored against.

    That band is the confidence envelope plus observation noise: the T2′
    picture, the one place the model is tested rather than fitted.
    """
    tables = r.petab_tables()
    if tables is None:
        return note("PEtab tables unavailable — held-out figure not drawn")
    best = (
        r.summary.get("best_x_unscaled")
        or (r.report.get("parameters") or {}).get("best")
        or {}
    )
    if not isinstance(best, dict) or not best:
        return note("no best parameter vector — held-out figure not drawn")
    frame = r.measurement_frame()
    if frame is None or not len(frame):
        return note("no measurements — held-out figure not drawn")
    hold_df = frame[frame["heldout"]]
    if not len(hold_df):
        return note("held-out rows are not present in this round's artifacts")
    pu = (
        r.report.get("prediction_uncertainty")
        or r.core.get("prediction_uncertainty")
        or {}
    )
    cr_bands = pu.get("bands") if isinstance(pu, dict) else None
    ensemble = [m.get("x_unscaled", {}) for m in (r.summary.get("ensemble") or [])]
    ensemble = [e for e in ensemble if isinstance(e, dict) and e][:_ENSEMBLE_CAP]
    labels = [str(g.get("label")) for g in groups if g.get("label")]
    sources = {str(g.get("label")): g.get("band_source") for g in groups}

    def build(plt):
        from octomod.gates.petab_gates import noise_band

        pairs = []
        for label in labels:
            if "@" not in label:
                continue
            obs, cond = label.split("@", 1)
            pairs.append((label, obs, cond))
        if not pairs:
            raise ValueError("no held-out groups carry an obs@cond label")
        ncol = min(2, len(pairs))
        nrow = int(np.ceil(len(pairs) / ncol))
        fig, axes = plt.subplots(
            nrow, ncol, squeeze=False, figsize=(min(4.6 * ncol, 9.4), 3.2 * nrow)
        )
        flat = [ax for row in axes for ax in row]
        for ax in flat[len(pairs) :]:
            ax.axis("off")
        col = "#8a4b2c"  # held out reads distinct from fit
        for ax, (label, obs, cond) in zip(flat, pairs, strict=False):
            g = hold_df[
                (hold_df["observable"].astype(str) == obs)
                & (hold_df["condition"].astype(str) == cond)
            ]
            g_t = g["time"].to_numpy(dtype=float)
            cr = (cr_bands or {}).get(label)
            if cr and cr.get("time"):
                t = np.asarray(cr["time"], dtype=float)
                # a band point at time inf is the steady state, drawn in a
                # column of its own right of the time course
                on_t = np.isfinite(t)
                t_last = float(t[on_t].max()) if on_t.any() else 0.0
                x_ss = (
                    steady_state_x(t[on_t])
                    if not on_t.all() or np.isposinf(g_t).any()
                    else None
                )
                lvls = cr_levels(cr)
                sig = noise_band(tables, obs, cond, t, best, PREDICTIVE_Z)
                if lvls:  # outermost: envelope + noise
                    lo = np.asarray(cr[f"lo{lvls[0]}"], dtype=float) - sig
                    hi = np.asarray(cr[f"hi{lvls[0]}"], dtype=float) + sig
                    ax.fill_between(
                        t[on_t],
                        lo[on_t],
                        hi[on_t],
                        color=col,
                        alpha=0.09,
                        linewidth=0,
                        zorder=0,
                    )
                    if x_ss is not None and not on_t.all():
                        draw_steady_level(
                            ax,
                            x_ss,
                            t_last,
                            None,
                            col,
                            lo=lo[~on_t][-1],
                            hi=hi[~on_t][-1],
                            alpha=0.09,
                        )
                draw_cr_envelopes(ax, cr, col, x_ss=x_ss, t_last=t_last)
                best_t = np.asarray(cr.get("best") or [], dtype=float)
                ax.plot(
                    t[on_t],
                    best_t[on_t],
                    color=col,
                    linewidth=1.5,
                    zorder=3,
                )
                if x_ss is not None and not on_t.all():
                    draw_steady_level(ax, x_ss, t_last, best_t[~on_t][-1], col)
            else:
                on_g = np.isfinite(g_t)
                tmax = float(g_t[on_g].max()) if on_g.any() else 1.0
                grid = np.linspace(0.0, tmax if tmax > 0 else 1.0, 200)
                t_last = float(grid[-1])
                x_ss = steady_state_x(grid) if np.isposinf(g_t).any() else None
                if x_ss is not None:
                    # the steady state the held-out time-inf rows are scored at
                    grid = np.append(grid, np.inf)
                base = tables.simulate_observables(cond, grid, param_override=best)[obs]
                stack = []
                for m in ensemble:
                    try:
                        stack.append(
                            tables.simulate_observables(cond, grid, param_override=m)[
                                obs
                            ]
                        )
                    except Exception:
                        continue
                arr = np.array(stack) if stack else np.asarray(base)[None, :]
                sig = noise_band(tables, obs, cond, grid, best, PREDICTIVE_Z)
                lo, hi = arr.min(axis=0) - sig, arr.max(axis=0) + sig
                on_grid = np.isfinite(grid)
                ax.fill_between(
                    grid[on_grid],
                    lo[on_grid],
                    hi[on_grid],
                    color=col,
                    alpha=0.14,
                    linewidth=0,
                    zorder=0,
                )
                line = np.asarray(base, dtype=float)
                ax.plot(
                    grid[on_grid], line[on_grid], color=col, linewidth=1.5, zorder=3
                )
                if x_ss is not None:
                    draw_steady_level(
                        ax,
                        x_ss,
                        t_last,
                        line[~on_grid][-1],
                        col,
                        lo=lo[~on_grid][-1],
                        hi=hi[~on_grid][-1],
                    )
            if len(g):
                ax.plot(
                    on_time_axis(g_t, x_ss),
                    g["value"].to_numpy(),
                    linestyle="none",
                    marker="o",
                    markerfacecolor="none",
                    markeredgecolor=col,
                    markeredgewidth=1.2,
                    ms=4.5,
                    zorder=4,
                )
            if x_ss is not None:
                mark_steady_state(ax, x_ss, t_last)
            ax.set_title(f"held out: {label}", fontsize=8.5)
            ax.set_xlabel("time")
            ax.set_ylabel(obs)
        fig.tight_layout()
        return fig

    src = next((s for s in sources.values() if s), None)
    caption = (
        "Held-out conditions only — the model predicting where it was "
        "not fitted. Open symbols are the held-out measurements. "
        + (
            f"Coverage is scored against: {src}."
            if src
            else "Coverage is scored against the outermost band shown."
        )
        + (STEADY_STATE_NOTE if has_steady_state(hold_df) else "")
    )
    fig_html = figure(
        build, caption=caption, fallback="held-out figure unavailable", lead=True
    )
    return fig_html + _band_method_note(r, pu, cr_bands)


def _md_evaluation(r: Round) -> str:
    d = r.discrimination
    if not d:
        return note("no discrimination block in the evaluation record")
    cands = sorted(d.get("candidates") or [], key=lambda c: c.get("aic", 0))
    rows = []
    for c in cands:
        win = c.get("id") == d.get("winner")
        rows.append(
            [
                f"<code>{esc(c.get('id', '—'))}</code>"
                + (' <span class="chip pass">winner</span>' if win else ""),
                num(c.get("n_est"), "{:.0f}"),
                num(c.get("n_flat", 0), "{:.0f}"),
                num(c.get("n_data"), "{:.0f}"),
                num(c.get("nllh"), "{:.4g}"),
                num(c.get("aic"), "{:.5g}"),
                num(c.get("bic"), "{:.5g}"),
                num(c.get("delta_aic"), "{:.3g}"),
                num(c.get("akaike_weight"), "{:.3f}"),
            ]
        )
    parts = [
        "<h4>Model comparison</h4>",
        table(
            [
                "candidate",
                "estimated",
                "structurally flat (indicator)",
                "n data",
                "−log L",
                "AIC",
                "BIC",
                "ΔAIC",
                "Akaike weight",
            ],
            rows,
        ),
        weights_figure(cands, d.get("winner")),
    ]
    if any(c.get("n_flat") for c in cands):
        # an indicator beside the criterion, not inside it
        parts.append(
            note(
                "A structurally flat direction is a parameter combination no output "
                "depends on at any parameter value, found at random points near the "
                "nominal parameter values before the fit "
                "(the candidate's `structural_nulls` record) and re-checked at the winner's "
                "fit below. It is an indicator: AIC and BIC charge every estimated "
                "parameter."
            )
        )
    indist = d.get("indistinguishable") or []
    cls = "flagbox" if len(indist) > 1 else "okbox"
    parts.append(
        f'<div class="{cls}"><b>Statistically indistinguishable set</b> '
        f'(ΔAIC &lt; {num(d.get("delta_aic_threshold"), "{:.3g}")}): '
        + (", ".join(f"<code>{esc(c)}</code>" for c in indist) or "empty")
        + f'<br><b>Verdict:</b> winner <code>{esc(str(d.get("winner")))}</code> — '
        f'{"decisive" if d.get("decisive") else "NOT decisive"} '
        f'(weight threshold {num(d.get("decisive_weight_threshold"), "{:.3g}")})'
        + "</div>"
    )
    parts.append(_search_topology(r))
    parts.append(_attribution(r))
    parts.append(_lattice_encoding(r))
    return "".join(parts)


def _search_topology(r: Round) -> str:
    """What the search covered, and whether criterion values compare across rounds.

    The search is exhaustive within a round and greedy across rounds (the
    stepwise/FAMoS family), so an unvisited corner is not evidence against it.
    """
    d = r.discrimination or {}
    topo = d.get("search_topology") or {}
    regime = d.get("cross_round_comparability") or {}
    if not topo and not regime:
        return ""
    bits = []
    if topo.get("union_lattice_models"):
        frac = topo.get("visited_fraction")
        bits.append(
            f"<b>Search topology:</b> {topo['topology']}. Over the "
            f"{topo['n_axes_declared']} axis/axes declared in this run the union "
            f"space is {topo['union_lattice_models']} models; the search visited "
            f"<b>{topo['visited']}</b>"
            + (f" ({frac:.0%})" if isinstance(frac, (int, float)) else "")
            + ". A corner never visited is not evidence against it — it was not "
            "tried."
        )
        outside = (
            topo.get("outside_status") or topo.get("models_outside_the_lattice") or []
        )
        if outside:
            bits.append(
                "Fitted outside that lattice (whole alternative models rather "
                "than axis combinations): "
                + ", ".join(f"<code>{esc(m)}</code>" for m in outside[:8])
                + "."
            )
    if regime:
        bits.append(
            "<b>Across rounds:</b> criterion values "
            + ("ARE" if regime.get("across_rounds") else "are NOT")
            + f" comparable — {esc(str(regime.get('why', '')))}"
        )
    cls = "okbox" if regime.get("across_rounds", True) else "flagbox"
    return f'<div class="{cls}">' + "<br>".join(bits) + "</div>"


def _attribution(r: Round) -> str:
    """Why the winner wins: which measurements paid for each ΔAIC.

    The likelihood part splits exactly over (observable, condition), read from
    AMICI's own numbers and checked against its per-condition likelihood, down
    to the timepoints of the largest contributor.
    """
    a = r.report.get("attribution") or r.core.get("attribution") or {}
    if not a:
        return ""
    if not a.get("available"):
        return note(f"Mechanism attribution unavailable: {esc(str(a.get('why', '?')))}")
    out = ["<h4>Why the winner wins</h4>"]
    for riv in a.get("rivals") or []:
        if not riv.get("available"):
            out.append(
                note_html(
                    f"vs <code>{esc(str(riv.get('rival')))}</code>: not decomposed "
                    f"— {esc(str(riv.get('why', '?')))}"
                )
            )
            continue
        out.append(
            f"<p><b>vs <code>{esc(str(riv['rival']))}</code></b>: ΔAIC "
            f"{num(riv['delta_aic'], '{:+.2f}')} = "
            f"{num(riv['likelihood_units'], '{:+.2f}')} from the likelihood + "
            f"{num(riv['parameter_units'], '{:+.2f}')} from the parameter count. "
            f"The likelihood part splits over the measurements exactly; the "
            f"parameter part is the price of the extra parameters and splits "
            f"over nothing.</p>"
        )
        rows = [
            [
                f"<code>{esc(c['group'])}</code>",
                num(c["delta_aic_units"], "{:+.2f}"),
                f"{c['share']:.0%}",
                num(c["n"], "{:.0f}"),
            ]
            for c in (riv.get("contributions") or [])[:8]
        ]
        out.append(
            table(["observable @ condition", "AIC units", "share", "n points"], rows)
        )
        detail = riv.get("worst_group_detail") or {}
        pts = detail.get("points") or []
        if pts:
            out.append(
                f"<p>Inside <code>{esc(str(detail.get('group')))}</code>, the "
                f"points that pay:</p>"
            )
            out.append(
                table(
                    ["time", "measured", "winner", esc(str(riv["rival"])), "Δ−log L"],
                    [
                        [
                            num(x["time"], "{:.4g}"),
                            num(x["measured"], "{:.4g}"),
                            num(x["winner_sim"], "{:.4g}"),
                            num(x["rival_sim"], "{:.4g}"),
                            num(x["delta_nllh"], "{:+.3f}"),
                        ]
                        for x in pts
                    ],
                )
            )
    neut = a.get("neutralisation") or {}
    params = neut.get("parameters") or {}
    if params:
        out.append("<h4>What each mechanism term buys</h4>")
        out.append(
            table(
                [
                    "parameter",
                    "axis",
                    "off at",
                    "cost of switching off",
                    "series that move",
                ],
                [
                    [
                        f"<code>{esc(pid)}</code>",
                        f"<code>{esc(str(rec.get('axis')))}</code>",
                        num(rec.get("neutral_value"), "{:g}"),
                        num(rec.get("cost_of_switching_off_aic_units"), "{:+.2f}")
                        + " AIC units",
                        ", ".join(
                            f"<code>{esc(g)}</code>"
                            for g in (rec.get("series_that_move") or [])[:4]
                        )
                        or "none by more than 1σ",
                    ]
                    for pid, rec in params.items()
                    if rec.get("available")
                ],
            )
        )
    elif neut.get("note"):
        out.append(note(esc(str(neut["note"]))))
    for aid, why in (neut.get("refused") or {}).items():
        out.append(
            note_html(
                f"axis <code>{esc(str(aid))}</code> not neutralised: "
                f"{esc(str(why))}"
            )
        )
    rec = a.get("reconciliation") or {}
    if rec.get("winner_drift") is not None:
        out.append(
            note(
                f"The split reproduces AMICI's own per-condition likelihood to "
                f"within {rec.get('split_tolerance')}. Re-evaluating the recorded "
                f"optimum gives {num(rec.get('winner_reevaluated_nllh'), '{:.6f}')} "
                f"against the {num(rec.get('winner_recorded_nllh'), '{:.6f}')} the "
                f"fit recorded there — a drift of "
                f"{num(rec.get('winner_drift'), '{:+.2e}')}, which is solver noise "
                f"between two evaluations of the same point and is not attributed "
                f"to any measurement."
            )
        )
    return "".join(out)


def _lattice_encoding(r: Round) -> str:
    """How the lattice was encoded: a shared supermodel structure or separate builds.

    Supermodel candidates share generated code, so a ΔAIC between two of them is
    a statement about the parameter table alone; separately compiled candidates
    also carry whatever their builds do differently.
    """
    enc = load_json(r.rnd / "model" / "encoding")
    if enc is None:
        return ""
    enc = enc or {}
    absorbed, separated = (
        enc.get("absorbed_axes") or [],
        enc.get("separated_axes") or [],
    )
    if not absorbed:
        return note(
            f"Lattice encoding: one structure per candidate — "
            f"{enc.get('n_models', 0)} model(s), {enc.get('n_structures', 0)} "
            f"compile(s). No axis declared a neutral value that could switch it "
            f"off by the parameter table alone, so ΔAIC compares separately "
            f"generated models."
        )
    ver = (enc.get("verification") or {}).get("checked_to") or {}
    lines = [
        f"<b>Lattice encoding: supermodel</b> — {enc.get('n_models', 0)} candidate(s) "
        f"over {enc.get('n_structures', 0)} structure(s), "
        f"{enc.get('compiles_saved', 0)} AMICI compile(s) saved. Axes absorbed "
        f"into the shared structure: "
        + ", ".join(f"<code>{esc(a)}</code>" for a in absorbed)
        + f". Each one's declared neutral value was simulated against the base "
        f"model and reproduced it to a relative {ver.get('rtol')}, so these "
        f"candidates are EXACTLY nested: same generated code, same integrator, "
        f"and a ΔAIC between them is a statement about the parameter table."
    ]
    if separated:
        lines.append("<br><b>Kept as their own structures:</b><ul>")
        why = enc.get("why_separate") or {}
        lines += [
            f"<li><code>{esc(a)}</code> — {esc(str(why.get(a, 'unrecorded')))}</li>"
            for a in separated
        ]
        lines.append("</ul>")
    return f'<div class="okbox">{"".join(lines)}</div>'


# --- 9 epistemics -----------------------------------------------------------


def _s9_epistemics(r: Round) -> str:
    interp = r.interp
    # `nonetheless_determined` claims something is pinned down; on a fit whose
    # convergence was accepted rather than demonstrated, the claim says so
    _acc = _convergence_caveat(r)
    cd = interp.get("cannot_distinguish") or []
    nd = interp.get("nonetheless_determined") or []
    ccd = (
        r.report.get("computed_cannot_distinguish")
        or r.core.get("computed_cannot_distinguish")
        or []
    )
    cnd = (
        r.report.get("computed_nonetheless_determined")
        or r.core.get("computed_nonetheless_determined")
        or []
    )
    # closed profiles wider than the determined fraction of their box: bounded,
    # not well determined, and in neither list above
    cpd = (
        r.report.get("computed_finite_but_poorly_determined")
        or r.core.get("computed_finite_but_poorly_determined")
        or []
    )
    pd_ = interp.get("finite_but_poorly_determined") or cpd
    # shown whenever profiles ran, so an empty third list reads as looked-at —
    # not on a discrimination round, whose lists carry no profile-derived
    # entry at all (`evaluation._md_computed_references`), so an empty one
    # there would read as a finding about the winner's profiles
    profiled = not r.is_md and any(
        not str(k).startswith("_")
        for k in (r.core.get("profiles") or r.report.get("profiles") or {})
    )
    third = bool(pd_ or cpd or profiled)

    def small(items):
        return (
            ("<code>" + "</code>, <code>".join(esc(i) for i in items) + "</code>")
            if items
            else "empty"
        )

    def col(title, items, computed, chip, wide=False):
        """One badge per entry, one line each, with the full wording a fold away."""
        if not items:
            body = '<p class="none">nothing listed</p>'
            cut_any = False
        else:
            shown = items[:EPISTEMICS_ENTRIES_SHOWN]
            cut_any = len(items) > len(shown)
            rows = []
            for item in shown:
                vis, cut = clip_chars(item, EPISTEMICS_ENTRY_CHARS)
                cut_any |= cut
                rows.append(
                    f'<div class="epi-row"><span class="chip {chip}">'
                    f"{chip.upper()}</span>{esc(vis)}</div>"
                )
            body = "".join(rows)
        return (
            f'<div class="epi-col{" wide" if wide else ""}"><h3>{title}'
            f'<span class="count">{len(items)}</span></h3>'
            + body
            + (
                fold(
                    "every entry, in full",
                    "<ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>",
                )
                if cut_any
                else ""
            )
            + f'<p class="ref">machine-computed reference: {small(computed)}</p></div>'
        )

    inner = (r.report.get("estimated_inner") or r.core.get("estimated_inner")) or {}
    inner_note = ""
    if inner:
        # identifiability is assessed over the outer vector only: an inner
        # parameter is in no profile and no ensemble, so it appears in neither
        # list, and that silence must not read as a clean bill of health
        inner_note = note_html(
            "<b>Not assessed:</b> "
            + ", ".join(f"<code>{esc(str(pid))}</code>" for pid in sorted(inner))
            + " — solved analytically by the inner optimiser at every outer "
            "step (hierarchical estimation). They are estimated parameters and "
            "still count in <i>k</i>, but they are not in the outer vector, so "
            "no profile and no ensemble spread was computed for them and they "
            "appear in neither list above. Their absence is a gap in the "
            "assessment, not a finding about the parameters."
        )
    from octomod.workflow_modules.estimation import convergence_record as _cr

    caveat = (
        note_html(
            "<b>⚑ These claims rest on a fit whose convergence was "
            + ("PRE-DECLARED" if _acc.pre_declared else "ACCEPTED")
            + ", not demonstrated.</b> "
            + esc(_cr.caveat_line(_acc))
            + " <b>&ldquo;Nonetheless determined&rdquo; in particular</b> "
            "asserts that a quantity IS pinned down; it is pinned down "
            "<i>given</i> an optimum nobody demonstrated was reached. See "
            "section 6 for the checks that failed and by how much."
        )
        if _acc is not None
        else ""
    )
    return (
        caveat
        + '<div class="epi">'
        + col("What the data cannot distinguish", cd, ccd, "mute")
        + col("Nonetheless determined", nd, cnd, "pass")
        + (
            col("Finite but poorly determined", pd_, cpd, "flag", wide=True)
            if third
            else ""
        )
        + "</div>"
        + note(
            "The first two lists are the agent's; the reference lines are the "
            "engine's own computation. A two-sided consistency gate "
            "(evaluation_no_overclaim / evaluation_no_underclaim) requires every computed "
            "entry to appear in the agent's list — see section 12."
            + (
                " The third is the engine's: closed profiles wider than the "
                "determined share of their box — bounded, not well determined; "
                "no gate adjudicates it."
                if third
                else ""
            )
        )
        + inner_note
    )


# --- 10 agent narrative -----------------------------------------------------


def _s10_narrative(r: Round) -> str:
    interp = r.interp
    if not interp:
        return (
            '<div class="pocket"><div class="pocket-hd">Agent interpretation '
            "— narrative, not computed</div>"
            + note("no interpretation block in the evaluation record")
            + "</div>"
        )
    parts = [
        '<div class="pocket"><div class="pocket-hd">Agent interpretation '
        "— narrative, not computed</div>"
    ]
    diagnosis = str(interp.get("diagnosis", "—"))
    lead, cut = clip_sentences(diagnosis, DIAGNOSIS_SENTENCES)
    parts.append(
        "<h3>Diagnosis</h3>"
        f"<p>{esc(lead)}</p>"
        + (fold("full diagnosis", f"<p>{esc(diagnosis)}</p>") if cut else "")
    )

    def as_text(m):
        return m if isinstance(m, str) else json.dumps(m, default=str)

    mis = [as_text(m) for m in (interp.get("misfit_hypotheses") or [])]
    parts.append("<h3>Misfit hypotheses</h3>")
    if mis:
        shown = mis[:HYPOTHESES_SHOWN]
        clipped = [clip_chars(m, MISFIT_REASON_CHARS) for m in shown]
        parts.append(
            "<ul>" + "".join(f"<li>{esc(v)}</li>" for v, _ in clipped) + "</ul>"
        )
        if len(mis) > len(shown) or any(c for _, c in clipped):
            parts.append(
                fold(
                    f"all {len(mis)} hypotheses, in full",
                    "<ul>" + "".join(f"<li>{esc(m)}</li>" for m in mis) + "</ul>",
                )
            )
    else:
        parts.append('<p class="none">none proposed</p>')
    ans = interp.get("answers_intent") or []
    parts.append("<h3>Verdicts against the declared success criteria</h3>")
    if ans:
        # A chip plus one line of evidence is the whole default view; the
        # criterion wording is what folds, because the verdict is the claim.
        chips, full_rows, cut_any = [], [], False
        for a in ans:
            ev, cut = clip_chars(str(a.get("evidence", "—")), INTENT_EVIDENCE_CHARS)
            cut_any |= cut
            chips.append(
                '<div class="vrow">'
                + verdict_badge(a.get("verdict"))
                + f'<span class="vev">{esc(ev)}</span></div>'
            )
            full_rows.append(
                [
                    verdict_badge(a.get("verdict")),
                    esc(str(a.get("criterion", "—"))),
                    esc(str(a.get("evidence", "—"))),
                ]
            )
        parts.append('<div class="chipset">' + "".join(chips) + "</div>")
        parts.append(
            fold(
                "each verdict against its criterion, evidence in full",
                table(["verdict", "criterion", "evidence"], full_rows, cls="verdicts"),
                open_=not cut_any and len(ans) <= 2,
            )
        )
    else:
        parts.append(note("no verdicts recorded"))
    parts.append(
        "<h3>Recommendation</h3>"
        f'<p class="rec">{esc(str(interp.get("recommendation", "—")))}</p>'
    )
    parts.append("</div>")
    return "".join(parts)


# --- 11 decision record -----------------------------------------------------


def _s11_decisions(r: Round) -> str:
    text = load_text(r.rnd / "decisions_md")
    if text is None:
        return note(
            "decisions_md was not written for this round — the "
            "per-module agent records are still in "
            "model/build_report, data/report and "
            "the candidate's assembly"
        )
    return (
        "<details open><summary>decisions_md (round decision record, "
        "assembled by the engine from the agents' structured records)"
        "</summary>"
        f'<pre class="md">{esc(text)}</pre></details>'
    )


# --- 12 gate record ---------------------------------------------------------


def _s12_gates(r: Round) -> str:
    gates = r.rows("gate")
    if not gates:
        return note("no gate events recorded for this round in the ledger")
    rows, fail_rows = [], []
    # an advisory check that did not pass is a flag: it is shown beside the
    # failures but not counted as one, because it never stopped the run
    n_fail = n_flag = 0
    for g in gates:
        passed = bool(g.get("passed"))
        blocking = g.get("blocking", True)
        if not passed:
            if blocking:
                n_fail += 1
            else:
                n_flag += 1
        verdict = (
            '<span class="chip pass">PASS</span>'
            if passed
            else '<span class="chip fail">FAIL</span>'
        )
        if not blocking:
            verdict += ' <span class="chip mute">advisory</span>'
        val, thr = g.get("value"), g.get("threshold")
        vt = (
            "—"
            if val is None and thr is None
            else f"{num(val)}{'' if thr is None else ' vs ' + num(thr)}"
        )
        rows.append(
            [
                f"<code>{esc(g.get('gate_id', '—'))}</code>",
                esc(g.get("tier", "—")),
                esc(g.get("module", "—")),
                verdict,
                vt,
                esc(clip_chars(g.get("detail", ""), GATE_DETAIL_CHARS)[0]),
            ]
        )
        if not passed:
            fail_rows.append(rows[-1])
    flagged = f", {n_flag} advisory flag(s) raised" if n_flag else ""
    head = kv(
        [
            (
                "gate events this round",
                f"{len(gates)} — {len(gates) - n_fail - n_flag} passed, "
                f"{n_fail} failed{flagged}",
            )
        ]
    )
    cols = ["gate", "tier", "module", "verdict", "value vs threshold", "detail"]
    full = table(cols, rows, cls="gates")
    if not fail_rows:
        # Nothing failed, so the table is a record rather than a finding: the
        # count above is the claim and the rows stay one click away.
        return head + fold(f"the full record, all {len(gates)} gates", full)
    return (
        head
        + note(
            f"{n_fail} of {len(gates)} gate events failed{flagged}"
            f"{' (an advisory flag never stops the run)' if n_flag else ''}. "
            f"Those rows are below; the complete record follows in the fold."
        )
        + table(cols, fail_rows, cls="gates")
        + fold(f"the full record, all {len(gates)} gates", full)
    )


# --- 13 footer --------------------------------------------------------------


def _s13_footer(r: Round) -> str:
    calls = r.rows("agent_call", False)
    this_round = [c for c in calls if c.get("round") == r.round_idx]
    models = sorted({str(c.get("model")) for c in calls if c.get("model")})
    cost = sum(
        float(c["cost_usd"])
        for c in calls
        if isinstance(c.get("cost_usd"), (int, float))
    )
    known_cost = any(isinstance(c.get("cost_usd"), (int, float)) for c in calls)
    # prompt bytes are recorded on every backend, so payload growth shows on a
    # stub run too, which records no dollars
    sized = [c for c in this_round if isinstance(c.get("prompt_bytes"), int)]
    biggest = max(sized, key=lambda c: c["prompt_bytes"], default=None)
    human = r.rows("human_gate")
    # the record keys this page was rendered from, and whether each is there:
    # run level, then the round, its model and its (effective) fitted problem
    parts = [(r.root, ["intent", "run", "ledger"])]
    parts.append((r.model, ["antimony", "sbml"]))
    # the build report is round-level for a candidate set (S1 writes one
    # report for the whole set), the model's own for a single-model round
    parts.append((r.rnd / "model" if r.cid else r.model, ["build_report"]))
    parts.append((r.rnd, ["data/measurements", "data/report"]))
    parts.append(
        (
            r.work,
            [
                "petab/observables",
                "petab/conditions",
                "petab/measurements",
                "petab/parameters",
                "petab/holdout_measurements",
                "assembly",
                "estimation",
                "cost",
                "starts",
            ],
        )
    )
    parts.append(
        (r.rnd, ["evaluation_core", "evaluation", "report_md", "decisions_md"])
    )
    rows = []
    for base, names in parts:
        for name in names:
            node = base / name
            rows.append(
                [
                    f"<code>{esc(node.key)}</code>",
                    "present" if node.exists() else "missing",
                ]
            )
    return (
        kv(
            [
                (
                    "agent calls",
                    f"{len(this_round)} this round · {len(calls)} in the run",
                ),
                (
                    "models used",
                    ", ".join(f"<code>{esc(m)}</code>" for m in models) or "—",
                ),
                (
                    "summed cost",
                    (
                        f"${cost:.4f}"
                        if known_cost
                        else "not recorded (stub backend records no cost)"
                    ),
                ),
                (
                    "agent prompt bytes",
                    (
                        f"{sum(c['prompt_bytes'] for c in sized):,} this round"
                        f" · largest {biggest['prompt_bytes']:,} "
                        f"(<code>{esc(str(biggest.get('role', '?')))}</code>)"
                        if biggest
                        else "not recorded"
                    ),
                ),
                ("human gates this round", str(len(human))),
            ]
        )
        + "<details><summary>record keys read</summary>"
        + note(f"in {r.store.path.name}")
        + table(["record key", "state"], rows)
        + "</details>"
        + '<p class="colophon">Rendered by octomod.reporting from the '
        "round's record. No language model took part in producing this "
        "page; every number above is read from the run record or simulated "
        "from the model it depicts.</p>"
    )


def render_report_html(rnd: Node) -> str:
    """The whole report as one self-contained HTML string, for the round
    node `rounds/round_k`.

    Never raises: a missing record becomes a note inside its section, and a
    section that fails entirely becomes a note in place of the section.
    """
    with rnd.store.reading():
        return _render(rnd)


def _render(rnd: Node) -> str:
    try:
        r = Round(rnd)
    except Exception as exc:
        r = None
        head = (
            f'<header class="hdr"><h1>{esc(rnd.name)}</h1>'
            f'<div class="badge fail">round could not be loaded</div>'
            f"</header>{note(str(exc))}"
        )
        return page(f"report — {rnd.name}", head)

    sections = [
        ("Intent (frozen)", _s2_intent, ""),
        ("The model", _s3_model, ""),
        ("The data", _s4_data, ""),
        ("The estimation problem", _s5_problem, ""),
        ("Estimation", _s6_estimation, ""),
        ("Fit", _s7_fit, ""),
        ("Evaluation", _s8_evaluation, ""),
        ("Epistemics", _s9_epistemics, ""),
        ("Agent narrative", _s10_narrative, ""),
        ("Decision record", _s11_decisions, ""),
        ("Gate record", _s12_gates, ""),
        ("Provenance", _s13_footer, ""),
    ]
    try:
        body = _s1_header(r) + _against_the_note(r)
    except Exception as exc:
        body = note(f"header unavailable: {trunc(exc, 160)}")
    for i, (title, fn, sub) in enumerate(sections, start=2):
        try:
            content = fn(r)
        except Exception as exc:
            content = note(
                f"section unavailable: {type(exc).__name__}: " f"{trunc(exc, 200)}"
            )
        body += sec(i, title, content, sub)
    testcase = (
        str(r.run_meta.get("project") or "")
        or Path(str(r.run_meta.get("testcase", ""))).name
        or r.store.run_id
    )
    return page(f"{testcase} — {rnd.name} — Octomod report", body)


def report_path(rnd: Node) -> Path:
    """Where the round's rendered report lives: a REAL file beside the
    record, `runs/<id>_reports/round_k/report/report.html`."""
    return rnd.store.reports_dir / rnd.name / "report" / "report.html"


def write_report_html(rnd: Node) -> Path:
    """Render the round `rnd` and write it to `report_path(rnd)`; returns
    that path."""
    path = report_path(rnd)
    html_text = render_report_html(rnd)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text)
    return path
