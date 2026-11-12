"""Matplotlib and SVG plumbing, and the figure builders that take plain data.

Figures are embedded as inline SVG so a report stays one self-contained file.
Every builder degrades: `figure` and `svg_only` return a visible note when the
draw fails, because a figure that cannot be drawn must not end a run.

Builders here take frames, dicts and arrays, never a Round. The two figures
that need a round's loaded artifacts — the held-out panel and the band
provenance note — live with the round report instead, which keeps this module
free of the data model and the package's imports acyclic.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

from octomod.reporting.html import (
    esc,
    note,
    num,
    trunc,
)

# Predictive-band z, matching s7's default gates.predictive_z. The workflow
# spec is not an artifact of the round, so the renderer cannot read the value
# that was actually used; it states the one it drew.
PREDICTIVE_Z = 1.96


_MAX_FIT_PANELS = 24


_RC = {
    "figure.figsize": (6.4, 3.6),
    "figure.dpi": 100,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.bbox": "tight",
    "svg.fonttype": "none",  # text stays text: small files, no glyph-id clash
    "font.size": 8.0,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8.0,
    "xtick.labelsize": 7.0,
    "ytick.labelsize": 7.0,
    "legend.fontsize": 7.0,
    "legend.frameon": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.22,
    "grid.linewidth": 0.5,
    "lines.linewidth": 1.3,
    "lines.markersize": 3.5,
}


_FIG_COUNTER = [0]


def _plt():
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    plt.rcParams.update(_RC)
    return plt


def _svg(fig) -> str:
    """Serialise a figure to inline SVG. The per-figure hash salt keeps
    matplotlib's internal ids (clip paths, gradients) unique, so several
    figures can share one document without cross-referencing each other."""
    plt = _plt()
    _FIG_COUNTER[0] += 1
    plt.rcParams["svg.hashsalt"] = f"octomod-fig-{_FIG_COUNTER[0]}"
    buf = io.StringIO()
    try:
        fig.savefig(buf, format="svg")
    finally:
        plt.close(fig)
    text = buf.getvalue()
    start = text.find("<svg")
    return text[start:] if start >= 0 else ""


def figure(
    build, caption: str = "", fallback: str = "figure unavailable", lead: bool = False
) -> str:
    """build(plt) -> Figure. Any failure becomes a note: a report of a broken
    run must still render. lead=True marks one of the four figures the report
    is organised around (fit, waterfall, parameters vs bounds, profiles)."""
    try:
        plt = _plt()
        fig = build(plt)
        if fig is None:
            return note(fallback)
        svg = _svg(fig)
        if not svg:
            return note(fallback)
    except Exception as exc:  # renderer never raises
        return note(f"{fallback}: {type(exc).__name__}: {trunc(exc, 160)}")
    cap = f"<figcaption>{esc(caption)}</figcaption>" if caption else ""
    cls = "fig lead" if lead else "fig"
    return f'<figure class="{cls}">{svg}{cap}</figure>'


def _svg_only(build, fallback: str) -> str:
    """A bare inline SVG, for figures that live inside their own HTML card
    rather than a <figure> of their own."""
    try:
        plt = _plt()
        fig = build(plt)
        if fig is None:
            return note(fallback)
        return _svg(fig) or note(fallback)
    except Exception as exc:  # renderer never raises
        return note(f"{fallback}: {type(exc).__name__}: {trunc(exc, 120)}")


def _colors(n: int) -> list:
    plt = _plt()
    cmap = plt.get_cmap("tab10")
    return [cmap(i % 10) for i in range(max(n, 1))]


# PEtab's steady-state measurement has the time `inf`, which no time axis can
# hold: a figure draws it in a column of its own right of the last finite time,
# set off by a dotted rule and labelled with this tick.
STEADY_STATE_TICK = "∞"
STEADY_STATE_NOTE = (
    " The column marked ∞ right of the time axis holds the steady-state "
    "measurements (time inf) and, where drawn, the model's steady state."
)


def has_steady_state(frame) -> bool:
    """Whether a measurement frame holds a steady-state row (time inf). Never
    raises: a frame whose time column cannot be read holds none."""
    try:
        return bool(np.isposinf(pd.to_numeric(frame["time"], errors="coerce")).any())
    except Exception:
        return False


def steady_state_x(finite_times) -> float:
    """Where the steady-state column sits: right of the last finite time by an
    eighth of the time window (1 when there is no window)."""
    t = np.asarray(finite_times, dtype=float)
    t = t[np.isfinite(t)]
    if not t.size:
        return 1.0
    lo, hi = min(0.0, float(t.min())), float(t.max())
    return hi + ((hi - lo) / 8.0 if hi > lo else 1.0)


def on_time_axis(times, x_ss: float | None) -> np.ndarray:
    """Times as a figure draws them: `inf` in the steady-state column `x_ss`."""
    t = np.asarray(times, dtype=float).copy()
    if x_ss is not None:
        t[np.isposinf(t)] = x_ss
    return t


def draw_steady_level(
    ax, x_ss: float, t_last: float, value, col, lo=None, hi=None, alpha=0.14
) -> None:
    """The model at steady state, in the steady-state column: its band
    `[lo, hi]` as a block and its value as a short level, each when finite."""
    half = 0.3 * (x_ss - t_last) if x_ss > t_last else 0.3
    xs = [x_ss - half, x_ss + half]
    if lo is not None and hi is not None and np.isfinite([lo, hi]).all():
        ax.fill_between(
            xs, [lo, lo], [hi, hi], color=col, alpha=alpha, linewidth=0, zorder=1
        )
    if value is not None and np.isfinite(value):
        ax.plot(xs, [value, value], color=col, linewidth=1.4, zorder=3)


def mark_steady_state(ax, x_ss: float, t_last: float) -> None:
    """Set the steady-state column off from the time axis: a dotted rule
    between them, and its tick labelled ∞ beside the axis's own ticks."""
    ax.axvline(
        0.5 * (t_last + x_ss), color="#9aa1a7", linestyle=":", linewidth=0.9, zorder=0
    )
    left, _right = ax.get_xlim()
    ticks = [float(t) for t in ax.get_xticks() if left <= t <= t_last]
    ax.set_xticks(ticks + [x_ss])
    ax.set_xticklabels([f"{t:g}" for t in ticks] + [STEADY_STATE_TICK])


_SVG_OPEN = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)


_SVG_SIZE = re.compile(r'\s+(?:width|height)\s*=\s*"[^"]*"', re.IGNORECASE)


_RESPONSIVE = "max-width:100%;height:auto;display:block;margin:auto"


def responsive_svg(svg: str) -> str:
    """Drop the fixed pt width/height Graphviz stamps on the SVG root, keep the
    viewBox, and let CSS scale it, so the whole network fits its frame."""
    m = _SVG_OPEN.search(svg)
    if not m:
        return svg
    tag = _SVG_SIZE.sub("", m.group(0))
    if 'style="' in tag:
        tag = tag.replace('style="', f'style="{_RESPONSIVE};', 1)
    else:
        tag = tag[:-1].rstrip() + f' style="{_RESPONSIVE}">'
    return svg[: m.start()] + tag + svg[m.end() :]


def data_figure(obs: str, sub: pd.DataFrame) -> str:
    steady = has_steady_state(sub)

    def build(plt):
        conds = list(dict.fromkeys(sub["condition"].astype(str)))
        cols = _colors(len(conds))
        fig, ax = plt.subplots(figsize=(6.8, 3.5))
        times = sub["time"].to_numpy(dtype=float)
        finite = times[np.isfinite(times)]
        x_ss = steady_state_x(finite) if steady else None
        any_held = False
        for c, col in zip(conds, cols, strict=False):
            g = sub[sub["condition"].astype(str) == c].sort_values("time")
            heldout = bool(g["heldout"].any())
            any_held = any_held or heldout
            mean = g.groupby("time")["value"].mean()
            # the line joins the time course only: a steady-state point is not
            # the sample after the last one
            on_course = np.isfinite(mean.index.to_numpy(dtype=float))
            ax.plot(
                mean.index.to_numpy(dtype=float)[on_course],
                mean.to_numpy()[on_course],
                color=col,
                alpha=0.30,
                linewidth=1.0,
                zorder=1,
            )
            ax.plot(
                on_time_axis(g["time"], x_ss),
                g["value"].to_numpy(),
                linestyle="none",
                marker="o",
                color=col,
                zorder=2,
                markerfacecolor=("none" if heldout else col),
                markeredgecolor=col,
                markeredgewidth=1.0,
                label=f"{c}" + (" (held out)" if heldout else ""),
            )
        if x_ss is not None:
            mark_steady_state(ax, x_ss, float(finite.max()) if finite.size else 0.0)
        ax.set_xlabel("time")
        ax.set_ylabel(obs)
        ax.set_title(obs)
        ax.legend(loc="best", ncols=2 if len(conds) > 3 else 1)
        if any_held:
            ax.text(
                0.99,
                0.02,
                "open symbols = held out of the fit",
                transform=ax.transAxes,
                ha="right",
                va="bottom",
                fontsize=6.5,
                color="#666666",
            )
        return fig

    steady_note = STEADY_STATE_NOTE if steady else ""
    return figure(
        build,
        caption=f"Measurements for {obs}: one series per "
        f"condition, points are replicates.{steady_note}",
        fallback=f"data figure for {obs} unavailable",
    )


def waterfall_figure(s: dict) -> str:
    """The pyPESTO convention, unconditionally: sorted (fval − best) + 1 on a
    log y-axis, so the best start sits at 1 and the plateau structure is
    readable whatever the absolute objective scale (which can be negative)."""

    def build(plt):
        fvals = [
            float(v)
            for v in (s.get("fvals") or [])
            if v is not None and np.isfinite(float(v))
        ]
        if not fvals:
            fvals = [
                float(x["fval"])
                for x in (s.get("starts") or [])
                if x.get("fval") is not None and np.isfinite(float(x["fval"]))
            ]
        if not fvals:
            raise ValueError("no finite start values recorded")
        f = np.sort(np.asarray(fvals, dtype=float))
        offset = (f - f.min()) + 1.0
        fig, ax = plt.subplots(figsize=(9.0, 3.6))
        x = np.arange(1, len(f) + 1)
        ax.plot(x, offset, marker="o", color="#2c5f8a", linestyle="-")
        ax.set_yscale("log")
        ax.set_ylabel("objective offset (−logL − best + 1)")
        ax.set_xlabel("start, sorted")
        ax.set_title(f"Waterfall — {len(f)} starts, best −logL = {f.min():.6g}")
        return fig

    return figure(
        build,
        caption="Sorted final objective per multistart start, "
        "offset so the best start sits at 1 (log "
        "axis); a flat left plateau is the "
        "convergence evidence.",
        fallback="waterfall unavailable",
        lead=True,
    )


def parameter_bounds_figure(par: pd.DataFrame | None, summary: dict) -> str:
    """Every estimated parameter against its own search interval: is the value
    sensible, and is the optimum sitting on a bound? One row per parameter,
    each with its own axis (log when the PEtab scale is log10) because the
    intervals span different decades and a shared axis would hide the answer."""

    def build(plt):
        if par is None or not len(par):
            raise ValueError("petab/parameters unavailable")
        best = summary.get("best_x_unscaled") or {}
        if not isinstance(best, dict):
            best = {}
        ens = [m.get("x_unscaled", {}) for m in (summary.get("ensemble") or [])]
        ens = [e for e in ens if isinstance(e, dict)]
        at_bounds = set(summary.get("at_bounds") or [])

        rows = []
        for _, row in par.iterrows():
            if int(row.get("estimate", 0) or 0) != 1:
                continue
            pid = str(row.get("parameterId"))
            try:
                lb, ub = float(row.get("lowerBound")), float(row.get("upperBound"))
            except (TypeError, ValueError):
                continue
            if not np.isfinite([lb, ub]).all() or ub <= lb:
                continue
            rows.append((pid, lb, ub, str(row.get("parameterScale", "lin"))))
        if not rows:
            raise ValueError("no estimated parameter has usable bounds")

        n = len(rows)
        fig, axes = plt.subplots(n, 1, squeeze=False, figsize=(8.4, 0.70 * n + 1.0))
        for ax, (pid, lb, ub, scale) in zip((a[0] for a in axes), rows, strict=False):
            hit = pid in at_bounds
            col = "#b3261e" if hit else "#2c5f8a"
            logx = scale == "log10" and lb > 0 and ub > 0
            if logx:
                ax.set_xscale("log")
                ax.set_xlim(lb / 1.6, ub * 1.6)
            else:
                pad = 0.06 * (ub - lb)
                ax.set_xlim(lb - pad, ub + pad)
            # the search interval as a bracket
            ax.hlines(0, lb, ub, color="#b9c0c6", linewidth=2.2, zorder=1)
            for edge in (lb, ub):
                ax.vlines(
                    edge,
                    -0.42,
                    0.42,
                    color=("#b3261e" if hit else "#8a9198"),
                    linewidth=1.6,
                    zorder=2,
                )
            for m in ens:  # ensemble spread as small ticks
                v = m.get(pid)
                if v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                b = best.get(pid)
                if b is not None and abs(v - float(b)) <= 1e-9 * max(
                    abs(float(b)), 1e-12
                ):
                    continue  # identical to best: nothing to show
                ax.vlines(
                    v, -0.26, 0.26, color=col, alpha=0.45, linewidth=0.9, zorder=3
                )
            bv = best.get(pid)
            if bv is not None:
                try:
                    bv = float(bv)
                    ax.plot([bv], [0], marker="o", ms=6.5, color=col, zorder=4)
                    ax.text(
                        1.005,
                        0.5,
                        f"{bv:.4g}" + ("  AT BOUND" if hit else ""),
                        transform=ax.transAxes,
                        va="center",
                        ha="left",
                        fontsize=7,
                        color=col,
                        fontweight="bold" if hit else "normal",
                    )
                except (TypeError, ValueError):
                    pass
            ax.set_ylim(-0.75, 0.75)
            ax.set_yticks([])
            ax.grid(axis="y", visible=False)
            ax.grid(axis="x", alpha=0.18)
            for side in ("left", "right", "top"):
                ax.spines[side].set_visible(False)
            ax.set_ylabel(
                pid + ("  ⚑" if hit else ""),
                rotation=0,
                ha="right",
                va="center",
                fontsize=8,
                color=("#b3261e" if hit else "#191b1d"),
            )
            ax.tick_params(axis="x", labelsize=6.5, pad=1)
        # the best-value annotation sits outside the axes, in the strip `rect`
        # leaves free on the right; the tight save box includes it
        fig.tight_layout(rect=(0, 0, 0.88, 1))
        return fig

    return figure(
        build,
        caption="Each estimated parameter against its own search interval "
        "(log axis where the PEtab scale is log10): bracket = "
        "[lowerBound, upperBound], dot = best fit, faint ticks = "
        "ensemble members, red = flagged at a bound.",
        fallback="parameter-vs-bounds plot unavailable",
        lead=True,
    )


def cr_levels(cr: dict) -> list[int]:
    """Confidence levels present in one band block, widest first."""
    levels = sorted(
        {
            int(k[2:])
            for k in cr
            if k.startswith("lo") and k[2:].isdigit() and f"hi{k[2:]}" in cr
        },
        reverse=True,
    )
    return levels


def draw_cr_envelopes(
    ax,
    cr: dict,
    col,
    pad: float = 0.0,
    x_ss: float | None = None,
    t_last: float | None = None,
) -> None:
    """Nested confidence envelopes: widest lightest, narrowest darkest, so the
    picture reads as 'how much of this is parameter uncertainty'.

    A band point at time `inf` (the steady state) is drawn as a block in the
    steady-state column `x_ss` right of `t_last`, and left out without one."""
    t = np.asarray(cr["time"], dtype=float)
    on_course = np.isfinite(t)
    levels = cr_levels(cr)
    for k, lvl in enumerate(levels):
        lo = np.asarray(cr[f"lo{lvl}"], dtype=float) - (pad if k == 0 else 0.0)
        hi = np.asarray(cr[f"hi{lvl}"], dtype=float) + (pad if k == 0 else 0.0)
        alpha = 0.11 + 0.09 * k
        ax.fill_between(
            t[on_course],
            lo[on_course],
            hi[on_course],
            color=col,
            linewidth=0,
            zorder=1,
            alpha=alpha,
        )
        if x_ss is not None and not on_course.all():
            draw_steady_level(
                ax,
                x_ss,
                t_last if t_last is not None else x_ss,
                None,
                col,
                lo=lo[~on_course][-1],
                hi=hi[~on_course][-1],
                alpha=alpha,
            )


# what the shading is, stated once so the caption cannot drift from the drawing
FIT_GRID_CAPTION = (
    "Best fit on a dense grid against the measurements, per observable × "
    "condition. Shaded = predictive band: darker = parameter uncertainty "
    "(ensemble spread, or nested confidence-region envelopes where profiles "
    "exist); the lightest outer band adds ±1.96σ of the fitted observation "
    "noise, so a measurement should fall inside it."
)


def fit_grid_figure(
    tables,
    best: dict,
    ensemble: list[dict],
    df: pd.DataFrame,
    cr_bands: dict | None = None,
) -> str:
    def build(plt):
        from octomod.gates.petab_gates import noise_band

        obs_ids = [
            o
            for o in dict.fromkeys(df["observable"].astype(str))
            if o in set(tables.observables["observableId"].astype(str))
        ]
        cond_ids = [
            c
            for c in dict.fromkeys(df["condition"].astype(str))
            if c in set(tables.conditions["conditionId"].astype(str))
        ]
        if not obs_ids or not cond_ids:
            raise ValueError(
                "measurement ids do not match the PEtab tables "
                "(long-format data without a PEtab problem?)"
            )
        while len(obs_ids) * len(cond_ids) > _MAX_FIT_PANELS and len(cond_ids) > 1:
            cond_ids = cond_ids[:-1]

        # one simulation pass per (condition, parameter set): every observable
        # comes out of the same trajectory
        sim = {}
        for cond in cond_ids:
            t = df.loc[df["condition"].astype(str) == cond, "time"].to_numpy(float)
            tmax = float(t[np.isfinite(t)].max()) if np.isfinite(t).any() else 0.0
            grid = np.linspace(0.0, tmax if tmax > 0 else 1.0, 200)
            if np.isposinf(t).any():
                # the steady state its time-inf rows are compared against
                grid = np.append(grid, np.inf)
            base = tables.simulate_observables(cond, grid, param_override=best)
            band = []
            for member in ensemble:
                try:
                    band.append(
                        tables.simulate_observables(cond, grid, param_override=member)
                    )
                except Exception:
                    continue
            sim[cond] = (grid, base, band)

        # observable × condition matrix; with one condition the column would
        # be a tall strip, so the observables wrap into a near-square grid
        cells = [(obs, j, cond) for obs in obs_ids for j, cond in enumerate(cond_ids)]
        if len(cond_ids) == 1:
            ncol = int(np.ceil(np.sqrt(len(cells))))
        else:
            ncol = len(cond_ids)
        nrow = int(np.ceil(len(cells) / ncol))
        size = (
            (8.6, 4.4)
            if len(cells) == 1
            else (min(3.1 * ncol, 12.0), max(2.4 * nrow, 2.5))
        )
        fig, axes = plt.subplots(nrow, ncol, squeeze=False, figsize=size)
        flat = [ax for row in axes for ax in row]
        for ax in flat[len(cells) :]:
            ax.axis("off")
        cols = _colors(len(cond_ids))
        for k, (obs, j, cond) in enumerate(cells):
            ax = flat[k]
            grid, base, band = sim[cond]
            col = cols[j]
            # a time-inf grid point is the steady state, drawn in a column of
            # its own right of the time course
            on_grid = np.isfinite(grid)
            cr = (cr_bands or {}).get(f"{obs}@{cond}")
            # the column sits right of everything on the time axis: the data's
            # grid and, when drawn, the band's own times (to t_end, which can
            # run past the last measurement)
            drawn_t = grid[on_grid]
            if cr and cr.get("time"):
                ct_all = np.asarray(cr["time"], dtype=float)
                drawn_t = np.concatenate([drawn_t, ct_all[np.isfinite(ct_all)]])
            t_last = float(drawn_t.max())
            x_ss = None if on_grid.all() else steady_state_x(drawn_t)
            g = df[
                (df["observable"].astype(str) == obs)
                & (df["condition"].astype(str) == cond)
            ]
            heldout = bool(g["heldout"].any()) if len(g) else False
            # the noise band per grid point, not one number added flat along
            # the curve
            sig = noise_band(tables, obs, cond, grid, best, PREDICTIVE_Z)
            if cr and cr.get("time"):
                draw_cr_envelopes(ax, cr, col, x_ss=x_ss, t_last=t_last)
                ct = np.asarray(cr["time"], dtype=float)
                on_ct = np.isfinite(ct)
                best_ct = np.asarray(cr.get("best") or [], dtype=float)
                # The envelopes are parameter uncertainty only; a lighter outer
                # band around the widest one adds the ±1.96σ observation noise,
                # so the band is predictive, as the caption says.
                levels = cr_levels(cr)
                if levels and len(ct):
                    widest = levels[0]
                    sig_ct = np.interp(ct, grid, np.asarray(sig, dtype=float))
                    lo_w = np.asarray(cr[f"lo{widest}"], dtype=float) - sig_ct
                    hi_w = np.asarray(cr[f"hi{widest}"], dtype=float) + sig_ct
                    ax.fill_between(
                        ct[on_ct],
                        lo_w[on_ct],
                        hi_w[on_ct],
                        color=col,
                        alpha=0.06,
                        linewidth=0,
                        zorder=0,
                    )
                    if x_ss is not None and not on_ct.all():
                        draw_steady_level(
                            ax,
                            x_ss,
                            t_last,
                            None,
                            col,
                            lo=lo_w[~on_ct][-1],
                            hi=hi_w[~on_ct][-1],
                            alpha=0.06,
                        )
                ax.plot(
                    ct[on_ct],
                    best_ct[on_ct],
                    color=col,
                    linewidth=1.4,
                    zorder=3,
                )
                if x_ss is not None and not on_ct.all():
                    draw_steady_level(ax, x_ss, t_last, best_ct[~on_ct][-1], col)
            else:
                if band:
                    stack = np.array([b[obs] for b in band if obs in b])
                else:
                    stack = np.asarray(base[obs])[None, :]
                lo, hi = stack.min(axis=0) - sig, stack.max(axis=0) + sig
                line = np.asarray(base[obs], dtype=float)
                ax.fill_between(
                    grid[on_grid],
                    lo[on_grid],
                    hi[on_grid],
                    color=col,
                    alpha=0.14,
                    linewidth=0,
                )
                ax.plot(
                    grid[on_grid], line[on_grid], color=col, linewidth=1.4, zorder=3
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
                    on_time_axis(g["time"], x_ss),
                    g["value"].to_numpy(),
                    linestyle="none",
                    marker="o",
                    color=col,
                    zorder=4,
                    markerfacecolor=("none" if heldout else col),
                    markeredgecolor=col,
                    markeredgewidth=1.0,
                )
            if x_ss is not None:
                mark_steady_state(ax, x_ss, t_last)
            ax.set_title(
                f"{obs} · {cond}" + ("  [held out]" if heldout else ""),
                fontsize=7.5,
            )
            if k + ncol >= len(cells):
                ax.set_xlabel("time")
            if k % ncol == 0 or len(cond_ids) == 1:
                ax.set_ylabel(obs)
        fig.tight_layout()
        return fig

    return figure(
        build,
        caption=FIT_GRID_CAPTION + (STEADY_STATE_NOTE if has_steady_state(df) else ""),
        fallback="fit grid unavailable",
        lead=True,
    )


def profile_figures(profiles: dict, best: dict) -> str:
    """Small multiples of the profile likelihood, plotted as the LIKELIHOOD
    RATIO exp(−(nllh − min)) rather than −logL: the ratio has a fixed [0, 1]
    range and a fixed threshold line, so profiles are comparable across
    parameters and across runs at a glance. The −logL numbers stay in
    the round's evaluation for machines."""

    def build(plt):
        items = [(pid, p) for pid, p in profiles.items()]
        if not items:
            raise ValueError("no profile paths")
        ncol = min(3, len(items))
        nrow = int(np.ceil(len(items) / ncol))
        fig, axes = plt.subplots(
            nrow, ncol, squeeze=False, figsize=(min(3.2 * ncol, 9.4), 2.5 * nrow)
        )
        flat = [ax for row in axes for ax in row]
        for ax in flat[len(items) :]:
            ax.axis("off")
        for ax, (pid, p) in zip(flat, items, strict=False):
            path = p.get("path") or {}
            x = np.asarray(path.get("x_unscaled") or [], dtype=float)
            ratio = path.get("likelihood_ratio")
            nllh = np.asarray(path.get("nllh") or [], dtype=float)
            if ratio:
                y = np.asarray(ratio, dtype=float)
                thr = path.get("ratio_threshold")
            else:
                # a profile stored as −logL only: the ratio is a pure
                # transform of it, so deriving it cannot disagree
                y = np.exp(-(nllh - nllh.min())) if len(nllh) else np.array([])
                nthr = path.get("nllh_threshold")
                thr = (
                    float(np.exp(-(float(nthr) - float(nllh.min()))))
                    if nthr is not None and len(nllh)
                    else None
                )
            n = min(len(x), len(y))
            x, y = x[:n], y[:n]
            keep = np.isfinite(x) & np.isfinite(y)
            x, y = x[keep], y[keep]
            if not len(x):
                ax.axis("off")
                continue
            order = np.argsort(x)
            x, y = x[order], y[order]
            pos = x[x > 0]
            logx = bool(pos.size == x.size) and float(x.max() / x.min()) > 10.0
            ci = p.get("ci95") or []
            if len(ci) == 2 and all(v is not None for v in ci):
                try:
                    ax.axvspan(
                        float(ci[0]),
                        float(ci[1]),
                        color="#2c5f8a",
                        alpha=0.10,
                        linewidth=0,
                        zorder=0,
                    )
                except (TypeError, ValueError):
                    pass
            if thr is not None:
                ax.axhline(
                    float(thr), color="#b3261e", linestyle="--", linewidth=1.0, zorder=2
                )
                ax.text(
                    0.99,
                    float(thr),
                    " 95%",
                    transform=ax.get_yaxis_transform(),
                    ha="right",
                    va="bottom",
                    fontsize=6.2,
                    color="#b3261e",
                )
            ax.plot(x, y, color="#2c5f8a", linewidth=1.4, zorder=3)
            bv = best.get(pid)
            if bv is not None:
                try:
                    ax.plot(
                        [float(bv)],
                        [float(np.max(y))],
                        marker="o",
                        ms=5,
                        color="#136c3a",
                        zorder=4,
                    )
                except (TypeError, ValueError):
                    pass
            if logx:
                ax.set_xscale("log")
            ax.set_ylim(0.0, 1.05)
            ax.set_title(pid, fontsize=8.5)
            ax.set_xlabel(pid + (" (log)" if logx else ""))
            ax.set_ylabel("likelihood ratio")
            ax.tick_params(labelsize=6.5)
        fig.tight_layout()
        return fig

    return figure(
        build,
        caption="Profile likelihood per parameter as a likelihood ratio "
        "exp(−(−logL − best)): dashed red = the 95% threshold "
        "(≈0.147), shaded = the resulting CI, green dot = the best "
        "fit. A profile that stays above the line all the way to a "
        "bound is a flat direction, not an interval.",
        fallback="profile plots unavailable",
        lead=True,
    )


NOISE_REJECT_P = 0.01


def rejects_noise(p) -> bool:
    """A missing or unparseable p-value is not a rejection — say nothing
    rather than flag on a blank."""
    try:
        return p is not None and float(p) < NOISE_REJECT_P
    except (TypeError, ValueError):
        return False


def _assumed_pdf(assumed: str, x: np.ndarray):
    """Standardized pdf of the assumed noise model, or None when we do not
    know the family — drawing the wrong curve would be worse than drawing
    none. Both families are unit-variance, matching standardized residuals."""
    fam = str(assumed or "").strip().lower()
    if fam.startswith("normal") or fam.startswith("gauss"):
        return np.exp(-0.5 * x**2) / np.sqrt(2.0 * np.pi)
    if fam.startswith("laplace"):
        b = 1.0 / np.sqrt(2.0)  # var = 2b^2 = 1
        return np.exp(-np.abs(x) / b) / (2.0 * b)
    return None


def qq_panel(obs: str, d: dict) -> str:
    """One observable's noise card: the QQ plot beside the residual histogram
    with the assumed pdf over it. Same evidence twice, read two ways — the QQ
    shows the tails, the histogram shows the shape."""
    assumed = str(d.get("assumed", "?"))
    qq = d.get("qq") or {}
    theo = qq.get("theoretical") or []
    samp = qq.get("sample") or []
    if not theo or not samp:
        why = d.get("note") or "no residual test recorded for this observable"
        return (
            f'<div class="qq"><div class="qqobs">{esc(obs)}</div>'
            f'<p class="qqmuted">{esc(str(why))}</p></div>'
        )

    p = d.get("p_value")
    rejects = rejects_noise(p)
    accent = "#b3261e" if rejects else "#2c5f8a"

    def build(plt):
        x = np.asarray(theo, dtype=float)
        y = np.asarray(samp, dtype=float)
        n = min(len(x), len(y))
        x, y = x[:n], y[:n]
        keep = np.isfinite(x) & np.isfinite(y)
        x, y = x[keep], y[keep]
        if not len(x):
            raise ValueError("no finite quantile pairs")
        fig, (axq, axh) = plt.subplots(1, 2, figsize=(4.45, 2.05))

        # -- QQ: points against the quantiles the assumption predicts
        lo = float(min(x.min(), y.min()))
        hi = float(max(x.max(), y.max()))
        pad = 0.08 * (hi - lo or 1.0)
        axq.plot(
            [lo - pad, hi + pad],
            [lo - pad, hi + pad],
            linestyle="--",
            linewidth=1.0,
            color="#9aa1a7",
            zorder=1,
        )
        axq.plot(x, y, linestyle="none", marker="o", ms=2.8, color=accent, zorder=2)
        axq.set_xlim(lo - pad, hi + pad)
        axq.set_ylim(lo - pad, hi + pad)
        axq.set_xlabel(f"theoretical ({assumed})", fontsize=6)
        axq.set_ylabel("standardized residual", fontsize=6)
        axq.tick_params(labelsize=5.5)

        # -- histogram of the same residuals, with the assumed pdf over it
        bins = int(min(15, max(5, round(np.sqrt(len(y))))))
        axh.hist(
            y,
            bins=bins,
            density=True,
            color=accent,
            alpha=0.32,
            edgecolor=accent,
            linewidth=0.5,
            zorder=1,
        )
        ylo, yhi = float(y.min()), float(y.max())
        gpad = 0.15 * (yhi - ylo or 1.0)
        grid = np.linspace(ylo - gpad, yhi + gpad, 200)
        pdf = _assumed_pdf(assumed, grid)
        if pdf is not None:
            axh.plot(
                grid, pdf, linestyle="--", linewidth=1.1, color="#9aa1a7", zorder=2
            )
        else:
            axh.text(
                0.5,
                0.94,
                f"pdf for '{assumed}' not drawn",
                transform=axh.transAxes,
                ha="center",
                va="top",
                fontsize=5.5,
                color="#8b9298",
            )
        axh.set_xlabel("standardized residual", fontsize=6)
        axh.set_ylabel("density", fontsize=6)
        axh.tick_params(labelsize=5.5)

        fig.tight_layout(pad=0.6, w_pad=1.2)
        return fig

    caption = f"{d.get('test', 'test')}, n={num(d.get('n'), '{:.0f}')}, " f"p={num(p)}"
    body = _svg_only(build, f"noise-check panels for {obs} unavailable")
    verdict = (
        (
            '<p class="qqnote">residuals reject the assumed noise model — '
            "change_noise_model is a revision candidate</p>"
        )
        if rejects
        else ""
    )
    cls = "qq reject" if rejects else "qq"
    return (
        f'<div class="{cls}"><div class="qqobs">{esc(obs)}</div>{body}'
        f'<p class="qqcap">{esc(caption)}</p>{verdict}</div>'
    )


def weights_figure(cands: list[dict], winner) -> str:
    def build(plt):
        if not cands:
            raise ValueError("no candidates")
        ids = [str(c.get("id")) for c in cands][::-1]
        w = [float(c.get("akaike_weight") or 0.0) for c in cands][::-1]
        fig, ax = plt.subplots(figsize=(6.4, max(1.4, 0.55 * len(ids) + 0.9)))
        cols = ["#2c5f8a" if i != str(winner) else "#137a3a" for i in ids]
        ax.barh(ids, w, color=cols, height=0.55)
        ax.set_xlim(0, 1.0)
        ax.set_xlabel("Akaike weight")
        ax.set_title("Model selection uncertainty")
        for y, v in zip(ids, w, strict=False):
            ax.text(min(v + 0.02, 0.97), y, f"{v:.3f}", va="center", fontsize=7)
        ax.grid(axis="y", visible=False)
        return fig

    return figure(
        build,
        caption="Akaike weights — the honest statement of " "selection uncertainty.",
        fallback="Akaike weight chart unavailable",
    )
