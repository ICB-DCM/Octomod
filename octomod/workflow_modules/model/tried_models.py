"""What was already tried, within a run and across runs.

Within a run: the cross-round table of every model fitted — id, axes on,
round, within-round ΔAIC and weight, the base it stood on — replaces the
current round's bare id list in the expansion agent's context, so a mechanism
rejected in round 0 is visible when round 2 proposes.

Across runs (opt-in): an archive `tried_models.json` is appended at run end by
the ENGINE (never an agent) — in `testcase/<case>/` for a run started from a
staged case, in `<runs>/_projects/<project>/` for a run started from its own
inputs. It is consumed only when `search.use_tried_log` is true, and then
SNAPSHOTTED into the run record (`tried_log_snapshot`, sha in the `run`
record) so the run stays replayable; it reaches construction and expansion as
EVIDENCE with the standing note that a "tried" verdict is context-dependent
(rejected in WHICH space, against WHICH base, on WHAT data) — never as an
exclusion. The engine never drops a proposed axis for matching the log; a
resemblance is a gate-card line for the human or policy to weigh. A run that
consumed the log says so in its `run` record, and the truth scorer refuses it
unless told otherwise — otherwise the benchmark measures the archive, not the
system.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from octomod.orchestration import run_folder
from octomod.orchestration.artifacts import read_json, write_json
from octomod.orchestration.ledger import sha256_file
from octomod.result import node as tree
from octomod.result.node import Node

STANDING_NOTE = (
    "context-dependent verdicts, not exclusions: a model rejected in one "
    "space, against one base, on one dataset, may be right in another — "
    "weigh, do not filter"
)


# ------------------------------------------------------------ within a run


def models_fitted_this_run(root: Node, current: dict | None = None) -> list[dict]:
    """Every model fitted anywhere in the run so far, with the round, the axes
    that were on, its within-round criterion standing, and the base it stood on.

    Read off the run's record: the round's report, its model space and the
    previous round's expansion decision. `root` is the run record's root
    node. `current` is the round being evaluated right now ({"round",
    "candidates", "winner", "criterion"}), whose evaluation is not written
    yet."""
    from octomod.result.access import (
        as_artifact,
        expansion_dict,
        record_for,
        report_dict,
    )

    rr = record_for(root)
    indices = list(rr.round_indices)
    if current is not None and int(current["round"]) not in indices:
        indices = sorted({*indices, int(current["round"])})
    rows: list[dict] = []
    for idx in indices:
        rnd = rr.rounds.get(f"round_{idx}")
        if current is not None and idx == int(current["round"]):
            rep = {
                "discrimination": {
                    "candidates": current["candidates"],
                    "winner": current["winner"],
                    "criterion": current.get("criterion", "AIC"),
                }
            }
        else:
            rep = report_dict(rnd) if rnd is not None else None
            if not rep:
                continue
        space = {
            a["id"]: a
            for a in (
                as_artifact(ax)
                for ax in (rnd.space.axes if rnd is not None and rnd.space else [])
            )
            if a and a.get("id")
        }
        base, carried = None, []
        prev = rr.rounds.get(f"round_{idx - 1}")
        if prev is not None:
            exp = expansion_dict(prev)
            if exp is not None:
                # the candidate the round was BUILT ON (the human's `base:`
                # when given), and the axes it re-declared live rather than
                # inherited
                base = exp.get("expanded_from") or exp.get("from_winner")
                carried = list(exp.get("carried_undecided") or [])
        disc = rep.get("discrimination")
        if disc:
            for c in disc["candidates"]:
                axes_on = [a for a in str(c["id"]).split("+") if a in space]
                rows.append(
                    {
                        "round": idx,
                        "model": c["id"],
                        "axes_on": axes_on,
                        "axes_in_space": sorted(space),
                        "n_estimated": c.get("n_est"),
                        "nllh": c.get("nllh"),
                        "criterion": disc.get("criterion", "AIC"),
                        "delta": c.get("delta", c.get("delta_aic")),
                        "weight": c.get("weight", c.get("akaike_weight")),
                        "selected": c["id"] == disc["winner"],
                        "base_model": base or "round-0 base",
                        "base_carried_undecided": carried,
                    }
                )
        else:
            rows.append(
                {
                    "round": idx,
                    "model": f"round {idx} model",
                    "axes_on": [],
                    "axes_in_space": sorted(space),
                    "n_estimated": None,
                    "nllh": rep.get("best_fval"),
                    "criterion": None,
                    "delta": None,
                    "weight": None,
                    "selected": True,
                    "base_model": base,
                }
            )
    return rows


# ADVISORY, not a gate. The agent is ASKED to account for every untested axis,
# and told plainly what happens if it does not: the gap becomes a line on the
# human's card and the human decides. A T0 gate with a retry would turn a
# judgement about which mechanism is worth fitting into a contract failure —
# and the engine is not the right party to that judgement. The ask stays firm
# because the behaviour is what we want; nothing enforces it.
UNTESTED_FIRST_NOTE = (
    "UNTESTED FIRST. `untested_axes` lists mechanisms already DECLARED in this "
    "run that no fitted model has ever carried. Before proposing a new law, "
    "account for every one of them in `untested_axes_addressed`: either "
    "action 'fit' (return it in `axes`, patched to the selected model) or "
    "action 'ruled_out' with `why` citing the residual evidence that excludes "
    "it. A FREE axis (adds no parameter) costs one calibration and cannot "
    "overfit, so 'too expensive' is never a reason to leave one untested. "
    "Re-proposing a mechanism already rejected is allowed only if you name what "
    "has changed in the background and quote its previous standing. This is "
    "advisory, not a contract: an axis you leave unaccounted for is shown to "
    "the human as unaccounted for, beside your proposal, and the human decides "
    "whether that is acceptable."
)


def unaccounted_untested(proposal: dict, untested_ids: set[str]) -> set[str]:
    """Which already-declared, never-fitted axes the proposal still ignores.

    An axis counts as accounted for only two ways:
      fitted     it is in `axes`, patched onto the selected model. Saying
                 action "fit" without returning the axis is a claim, not a fit,
                 so the id must actually appear.
      ruled out  action "ruled_out" WITH a reason. A refusal without one is
                 not an argument; without this rule a free axis can go
                 untested round after round.
    """
    proposed = {
        str(a.get("id"))
        for a in (proposal.get("axes") or [])
        if isinstance(a, dict) and a.get("id")
    }
    accounted = set(proposed)
    for entry in proposal.get("untested_axes_addressed") or []:
        if not isinstance(entry, dict):
            continue
        aid, action = str(entry.get("id")), str(entry.get("action"))
        if action == "fit" and aid in proposed:
            accounted.add(aid)
        elif action == "ruled_out" and str(entry.get("why", "")).strip():
            accounted.add(aid)
    return set(untested_ids) - accounted


# The two places a round's axes are written: the enumerated space, and the
# axes a DISCRIMINATION round only declared. One definition, because two
# readers need it — the status table below, and the expansion path that puts an
# untested axis back into the lattice (answer 0b(b)). Record keys under the
# round (`access.axes_declared` reads the same two, in this order).
AXIS_KEYS = ("space/axes", "space/declared")


def declared_in_round(rnd: Node) -> list[dict]:
    """Every axis dict this round (`rounds/round_k`) declared, in either of its
    two records — read off the run's record."""
    from octomod.result.access import axes_declared, record_for, round_of

    rr = record_for(rnd)
    rec = round_of(rr, rnd)
    return axes_declared(rec) if rec is not None else []


def declared_axis_dicts(root: Node) -> dict[str, dict]:
    """{axis id -> the axis as declared}, earliest declaration winning.

    The status table (`declared_axes_this_run`) carries a SUMMARY per axis, on
    purpose: it rides in the expansion agent's context and does not need every
    patch. Anything that has to APPLY an axis needs the axis itself, and this
    is where it comes from.
    """
    from octomod.result.access import axes_declared, record_for

    rr = record_for(root)
    out: dict[str, dict] = {}
    for idx in rr.round_indices:
        for axis in axes_declared(rr.round(idx)):
            out.setdefault(str(axis["id"]), axis)
    return out


def declared_axes_this_run(root: Node) -> list[dict]:
    """Every axis DECLARED anywhere in the run, and what became of it.

    An axis is declared once and then either bought and fitted, or left.
    Without this list the left ones are invisible: a FREE axis declared in
    round 0 and priced last is never fitted, and later proposers invent laws
    for the arm it would have repaired. "Untested first" needs that list to
    exist, so this builds it.

    Status per axis, in the order a modeller cares about:
      unbought   declared, never on any fitted model — the thing to try next
      rejected   fitted and beaten, with the best standing it achieved
      selected   on the winning model of some round
    A FREE axis (`adds_parameters: []`) costs one calibration and cannot
    overfit, so leaving it untested is never a saving.
    """
    from octomod.result.access import axes_declared, record_for

    fitted = models_fitted_this_run(root)
    rr = record_for(root)
    out: dict[str, dict] = {}
    for idx in rr.round_indices:
        # the enumerated space, plus the axes a discrimination round only
        # DECLARED — both are "declared in this run"
        declared = axes_declared(rr.round(idx))
        if not declared:
            continue
        for axis in declared:
            if not isinstance(axis, dict) or not axis.get("id"):
                continue
            aid = str(axis["id"])
            if aid in out:
                continue
            out[aid] = {
                "id": aid,
                "declared_in_round": idx,
                "priority": axis.get("priority"),
                "question": axis.get("question", ""),
                "kind": axis.get("kind", ""),
                "free": not (axis.get("adds_parameters") or []),
                "adds_parameters": [
                    str(pp.get("id"))
                    for pp in (axis.get("adds_parameters") or [])
                    if isinstance(pp, dict)
                ],
                "status": "unbought",
                "best_delta": None,
                "against_base": None,
                "fitted_on": [],
            }
    for row in fitted:
        for aid in row.get("axes_on") or []:
            rec = out.get(aid)
            if rec is None:
                continue
            rec["fitted_on"].append(row["model"])
            delta = row.get("delta")
            if rec["status"] == "unbought":
                rec["status"] = "rejected"
                rec["against_base"] = row.get("base_model")
            if row.get("selected"):
                rec["status"] = "selected"
            if delta is not None and (
                rec["best_delta"] is None or float(delta) < float(rec["best_delta"])
            ):
                rec["best_delta"] = float(delta)
    order = {"unbought": 0, "rejected": 1, "selected": 2}
    return sorted(
        out.values(),
        key=lambda r: (
            order.get(r["status"], 3),
            not r["free"],
            r["priority"] if isinstance(r["priority"], int) else 99,
            r["id"],
        ),
    )


def untested(axes: list[dict]) -> list[dict]:
    """The declared axes no fitted model has ever carried."""
    return [a for a in axes if a.get("status") == "unbought"]


def untested_card_lines(axes: list[dict]) -> list[str]:
    """What the human sees about axes nobody has tried yet."""
    open_axes = untested(axes)
    if not open_axes:
        return []
    out = [
        f"UNTESTED AXES ALREADY DECLARED — {len(open_axes)}, oldest first. A "
        f"mechanism nobody has fitted is cheaper to settle than a new one:"
    ]
    for a in open_axes:
        cost = (
            "FREE — one calibration, cannot overfit"
            if a["free"]
            else (f"adds {', '.join(a['adds_parameters'])}")
        )
        out.append(
            f"  · {a['id']} (round {a['declared_in_round']}, "
            f"priority {a['priority']}; {cost})"
        )
        if a.get("question"):
            out.append(f"      {str(a['question'])[:96]}")
    return out


def untested_verdict_lines(
    proposal: dict, axes: list[dict], *, carried=(), buy_form: bool = False
) -> list[str]:
    """One line per already-declared, never-fitted axis: what this proposal did
    about it.

    "Untested first" is advisory, so this card is the ONLY consumer of
    `unaccounted_untested` — the human reads the gap and decides; no gate
    refuses the proposal. It lives beside that function on purpose: two
    copies of the notion of "accounted for" drift.
    `carried` axes are those the engine carried back into the expansion.
    """
    open_axes = untested(axes)
    if not open_axes:
        return []
    proposed = {
        str(a.get("id")) for a in (proposal.get("axes") or []) if isinstance(a, dict)
    }
    addressed = {
        str(e.get("id")): e
        for e in (proposal.get("untested_axes_addressed") or [])
        if isinstance(e, dict)
    }
    unaccounted = unaccounted_untested(proposal, {a["id"] for a in open_axes})
    out = []
    for a in open_axes:
        aid = a["id"]
        if aid in proposed:
            verdict = "FITTED in this expansion"
        elif aid in set(carried):
            # the engine carried it back (never fitted, not ruled out)
            verdict = "REJOINS this expansion with its declared priority"
        elif aid in unaccounted:
            verdict = "STILL UNACCOUNTED FOR by the agent — your call"
        else:
            why = str((addressed.get(aid) or {}).get("why", ""))[:120]
            verdict = f"ruled out by the agent: {why}" if why else "ruled out"
            if buy_form:
                verdict += f" — `axes: +{aid}` fits it anyway"
        out.append(f"      → {aid}: {verdict}")
    return out


# ------------------------------------------------------------ across runs


def log_path(archive_dir: Path) -> Path:
    return Path(archive_dir) / "tried_models.json"


def archive_for(source_dir: Path | None, project: str) -> Path:
    """Which folder holds this run's cross-run archive.

    A run started from a testcase uses `testcase/<case>/`; a run started from
    its own inputs uses `<runs>/_projects/<project>/`, keyed by project (not
    by input hash, since a follow-up run always edits something).
    """
    if source_dir is not None:
        return Path(source_dir)
    return run_folder.archive_dir(project)


def archive_for_ctx(ctx) -> Path:
    """The archive of the run a context belongs to: from the context's
    `source_dir` and `project` when it carries them, else from the `run`
    record (`testcase`, `project`)."""
    source = getattr(ctx, "source_dir", None)
    project = getattr(ctx, "project", None)
    if source is None or not project:
        meta = (ctx.root / "run").get({}) or {}
        if source is None and meta.get("testcase"):
            source = Path(str(meta["testcase"]))
        project = (
            project
            or meta.get("project")
            or run_folder.project_of(ctx.root.store.run_id, source)
        )
    return archive_for(source, str(project))


def append_run(root: Node, archive_dir: Path, run_meta: dict) -> int:
    """Engine-written at run end: every fitted model of this run, with the
    space it sat in and the provenance that makes the verdict interpretable.
    The archive is a real file (`archive_for`); the run is its record."""
    rows = models_fitted_this_run(root)
    if not rows:
        return 0
    path = log_path(archive_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    archive = read_json(path, default={"entries": [], "note": STANDING_NOTE})
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    axes_text = {}
    for idx in tree.round_indices(root):
        for a in (tree.round_node(root, idx) / "space/axes").get(None) or []:
            axes_text[a["id"]] = {
                "question": a.get("question", ""),
                "patch": a.get("on_antimony_patch") or a.get("on_assembly_patch"),
            }
    for r in rows:
        archive["entries"].append(
            {
                **r,
                "run_id": root.store.run_id,
                "recorded_at": stamp,
                "workflow_sha": run_meta.get("workflow_sha"),
                "policy_sha": run_meta.get("policy_sha"),
                "axes_detail": {a: axes_text.get(a) for a in r["axes_on"]},
            }
        )
    write_json(path, archive)
    return len(rows)


def snapshot_for_run(ctx) -> dict | None:
    """Consume the archive: copy it into the run record (`tried_log_snapshot`,
    replayable), record its sha in the `run` record, return the snapshot (or
    None when there is nothing)."""
    src = log_path(archive_for_ctx(ctx))
    if not src.exists():
        return None
    dst = ctx.root / "tried_log_snapshot"
    dst.put(read_json(src))
    meta_node = ctx.root / "run"
    meta = meta_node.get({})
    meta["tried_log_consumed"] = {
        "source": str(src),
        # the archive file's own sha: the bytes the snapshot was taken from
        "sha": sha256_file(src),
        "n_entries": len(dst.get({}).get("entries", [])),
    }
    meta_node.put(meta)
    ctx.ledger.append(
        "tried_log_consumed",
        module="search",
        round_idx=ctx.round_idx,
        sha=meta["tried_log_consumed"]["sha"],
        n_entries=meta["tried_log_consumed"]["n_entries"],
    )
    return dst.get()


def snapshot_if_enabled(ctx) -> dict | None:
    """The archive, but only when the spec opted in, and snapshotted once.

    Consuming it makes a run non-blind, so the decision is a single spec knob
    and the act is recorded in the `run` record. Cached on the run context: the
    snapshot is taken once even though several gate cards ask for it.
    """
    if not ctx.spec.get("search.use_tried_log", False):
        return None
    if "tried_log" not in ctx.cache:
        try:
            ctx.cache["tried_log"] = snapshot_for_run(ctx)
        except Exception:  # an archive must never end a run
            ctx.cache["tried_log"] = None
    return ctx.cache["tried_log"]


def resemblance_lines(axes: list[dict], snapshot: dict | None) -> list[str]:
    """Gate-card lines: a proposed axis that resembles an archived one (same id,
    or the same patch text) — surfaced with the archived verdict, never filtered."""
    if not snapshot:
        return []
    lines = []
    for a in axes:
        hits = []
        for e in snapshot.get("entries", []):
            det = (e.get("axes_detail") or {}).get(a["id"])
            same_id = a["id"] in (e.get("axes_on") or [])
            same_patch = det and det.get("patch") == (
                a.get("on_antimony_patch") or a.get("on_assembly_patch")
            )
            if same_id or same_patch:
                hits.append(e)
        if not hits:
            continue
        best = min(
            hits,
            key=lambda e: (
                e.get("delta") if isinstance(e.get("delta"), (int, float)) else 1e9
            ),
        )
        verdict = (
            "selected"
            if best.get("selected")
            else (
                f"rejected at Δ{best.get('criterion') or 'AIC'} {best.get('delta')}"
                if best.get("delta") is not None
                else "fitted"
            )
        )
        lines.append(
            f"  · axis {a['id']!r} resembles a model tried in run {best.get('run_id')} "
            f"(round {best.get('round')}, base {best.get('base_model')}): {verdict}; "
            f"{len(hits)} archived fit(s). {STANDING_NOTE}."
        )
    return lines
