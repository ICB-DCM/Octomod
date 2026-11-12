"""Escaping, small HTML builders, record loaders, and the page shell.

The leaf of the reporting package: it imports no other reporting module.
`import html` below is the standard library's (absolute imports never shadow
it). Every loader takes a record `Node` and returns a falsy default rather
than raising: a missing record renders a visible note; report rendering must
never kill a run.
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octomod.result.node import Node


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def trunc(x, n: int = 120) -> str:
    s = str(x)
    return s if len(s) <= n else s[: n - 1] + "…"


def num(x, fmt: str = "{:.4g}") -> str:
    """A number for a table cell: None and NaN become an em dash, anything
    unparseable its escaped text. Never raises."""
    if x is None:
        return "—"
    if isinstance(x, (list, tuple, dict)):
        return esc(trunc(json.dumps(x, default=str), 60))
    try:
        v = float(x)
    except (TypeError, ValueError):
        return esc(trunc(x, 60))
    if v != v:
        return "—"
    return fmt.format(v)


def load_json(node: Node):
    """The record data at `node` (a dict, list, string or number), or None."""
    try:
        return node.get(None)
    except Exception:
        return None


def load_tsv(node: Node):
    """The `Table` at `node` as a DataFrame, or None."""
    try:
        return node.table(None)
    except Exception:
        return None


def load_text(node: Node) -> str | None:
    """The text dataset at `node`, or None."""
    try:
        return node.text(None)
    except Exception:
        return None


def note(text: str) -> str:
    """A note from plain TEXT. Escapes, so any string is safe to pass."""
    return f'<p class="note">{esc(text)}</p>'


def note_html(markup: str) -> str:
    """A note whose caller built the markup deliberately: <b>, <code> and the
    like survive. Separate from `note`, which escapes and stays the safe default
    for arbitrary text. Escape any INTERPOLATED value with `esc` yourself.
    """
    return f'<p class="note">{markup}</p>'


def table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    """Cells are raw HTML: callers escape what needs escaping. Kept explicit
    so verdict badges and <code> can live inside a cell."""
    if not rows:
        return note("no rows")
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    klass = f' class="{cls}"' if cls else ""
    return (
        f'<div class="tw"><table{klass}><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def kv(pairs: list[tuple[str, str]]) -> str:
    items = "".join(
        f'<div class="k">{esc(k)}</div><div class="v">{v}</div>' for k, v in pairs
    )
    return f'<div class="kv">{items}</div>'


def verdict_badge(v: str) -> str:
    v = str(v or "").lower()
    cls = (
        "pass" if v.startswith("pass") else ("fail" if v.startswith("fail") else "flag")
    )
    return f'<span class="chip {cls}">{esc(v.upper() or "—")}</span>'


def group(title: str, answers: str) -> str:
    """A GROUP header inside a section, with the question the group answers."""
    return f'<h3 class="grp">{esc(title)}</h3>' f'<p class="grpq">{esc(answers)}</p>'


def stated(title: str, lines: list[str]) -> str:
    """A decision the reader must not be able to miss.

    Body size and flagged, unlike `note`, which is muted because it is for
    asides. Empty in, empty out: a heading with nothing under it teaches a
    reader to skip the device.
    """
    if not lines:
        return ""
    body = "".join(f"<p>{esc(ln)}</p>" for ln in lines)
    return f'<div class="against"><p><b>{esc(title)}</b></p>{body}</div>'


def sec(idx: int, title: str, body: str, sub: str = "", cls: str = "") -> str:
    subline = f'<p class="sub">{esc(sub)}</p>' if sub else ""
    klass = f"sec {cls}".strip()
    return (
        f'<section class="{klass}" id="s{idx}">'
        f'<h2><span class="n">{idx}</span>{esc(title)}</h2>'
        f"{subline}{body}</section>"
    )


_CSS = """
:root{--ink:#191b1d;--mute:#6a7075;--rule:#e4e6e8;--soft:#f7f8f9;
 --pass:#136c3a;--fail:#b3261e;--flag:#8a5300;--blue:#2c5f8a}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#fff;color:var(--ink);font-size:15px;line-height:1.55;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,
 "Helvetica Neue",sans-serif}
main{max-width:900px;margin:0 auto;padding:34px 24px 72px}
h1{font-size:24px;line-height:1.25;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:17px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--rule);
 display:flex;align-items:baseline;gap:10px;letter-spacing:-.005em}
h2 .n{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;
 min-width:1.4em}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);
 margin:22px 0 8px;font-weight:600}
p{margin:0 0 10px}
.sec{margin:34px 0 0}
.hdr{padding-bottom:20px;border-bottom:2px solid var(--ink)}
.sub{color:var(--mute);margin:0 0 14px}
.badge{display:inline-block;font-weight:600;font-size:14px;padding:7px 14px;
 border-radius:4px;margin:2px 0 16px;border:1px solid}
.badge.pass{color:var(--pass);background:#eef7f1;border-color:#bfe0cc}
.badge.fail{color:var(--fail);background:#fdefee;border-color:#f0c4c1}
.badge.flag{color:var(--flag);background:#fdf5e7;border-color:#eeddb8}
.kv{display:grid;grid-template-columns:190px 1fr;gap:5px 16px;font-size:13.5px;
 margin:0 0 12px}
.kv .k{color:var(--mute)}
.kv .v{min-width:0;overflow-wrap:anywhere}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em;
 background:var(--soft);padding:1px 4px;border-radius:3px}
pre{background:var(--soft);border:1px solid var(--rule);border-radius:4px;
 padding:12px 14px;overflow-x:auto;font-size:12px;line-height:1.45;
 font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;margin:0 0 12px}
pre.listing{background:#fbfbfa}
pre.md{white-space:pre-wrap}
details{margin:0 0 12px;font-size:14px}
summary{cursor:pointer;color:var(--blue);padding:4px 0;font-size:13.5px}
.tw{overflow-x:auto;margin:0 0 14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--rule);
 vertical-align:top}
th{font-weight:600;color:var(--mute);font-size:11.5px;text-transform:uppercase;
 letter-spacing:.05em;border-bottom:1px solid #c9cdd1;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
td{font-variant-numeric:tabular-nums}
table.verdicts td:nth-child(3){font-variant-numeric:normal;font-size:12.5px;
 color:#3b4045}
table.gates td:last-child{font-size:12px;color:#3b4045;font-variant-numeric:normal}
.chip{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.05em;
 padding:1px 6px;border-radius:3px;white-space:nowrap}
.chip.pass{color:var(--pass);background:#e8f3ec}
.chip.fail{color:var(--fail);background:#fbeae9}
.chip.flag{color:var(--flag);background:#fbf1e0}
.chip.mute{color:var(--mute);background:#eef0f1}
.note{font-size:12.5px;color:var(--mute);background:var(--soft);
 border-left:3px solid #d3d7da;padding:8px 12px;border-radius:0 3px 3px 0}
.none{color:var(--mute);font-size:13px;font-style:italic}
/* the one picture of a space: which axes each candidate carries, ordered by distance */
table.axgrid td{text-align:center}
table.axgrid td:first-child{text-align:left;font-family:ui-monospace,monospace;
 font-size:12.5px}
.axon{display:inline-block;min-width:26px;padding:1px 5px;border-radius:3px;
 background:#e7f5ef;color:#065f46;font-size:11px;font-weight:600}
.axoff{color:#cbd5e1}
.dbar{display:inline-block;width:96px;height:9px;background:#eef0f1;
 border-radius:2px;vertical-align:middle;overflow:hidden}
.dbar i{display:block;height:100%;background:#94a3b8}
.axlegend{font-size:12.5px;color:var(--mute);margin:6px 0 14px;line-height:1.6}
ul.ran{margin:6px 0 0;padding-left:20px;font-size:13.5px}
ul.ran li{margin:3px 0}
.against{font-size:14px;background:#fdf5e7;border-left:4px solid var(--flag);
 padding:11px 14px;margin:14px 0}
.against p{margin:0 0 7px}
.against p:last-child{margin:0}
.against b{color:var(--flag)}
.legend{display:flex;flex-wrap:wrap;gap:7px 16px;margin:2px 0 12px;
 font-size:12.5px;color:#3b4045}
.legend .swatch{display:flex;align-items:center;gap:6px}
.legend .swatch i{width:13px;height:13px;border-radius:3px;border:1.6px solid;
 flex:0 0 auto}
.epi-row{display:flex;gap:8px;align-items:baseline;font-size:13.5px;
 padding:3px 0;border-bottom:1px solid #f0f2f3}
.epi-row:last-child{border-bottom:none}
.epi-row .chip{flex:0 0 auto}
h3.grp{font-size:15px;text-transform:none;letter-spacing:-.005em;color:var(--ink);
 margin:30px 0 2px;padding-top:14px;border-top:2px solid var(--rule);font-weight:600}
.grpq{font-size:12.5px;color:var(--mute);margin:0 0 14px;font-style:italic}
h4{font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);
 margin:20px 0 8px;font-weight:600}
h3 .count{margin-left:7px;font-size:11px;color:var(--mute);background:var(--soft);
 padding:1px 6px;border-radius:8px;font-variant-numeric:tabular-nums}
.chipset{margin:0 0 10px}
.vrow{display:flex;gap:9px;align-items:baseline;padding:4px 0;
 border-bottom:1px solid #f0f2f3}
.vrow:last-child{border-bottom:none}
.vev{font-size:13px;color:#3b4045;min-width:0;overflow-wrap:anywhere}
.tl{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}
.tl-sig{display:flex;gap:6px;align-items:center;font-size:12.5px;
 border:1px solid var(--rule);border-radius:14px;padding:3px 11px 3px 8px}
.tl-dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
.tl-dot.on{background:var(--flag)}
.tl-dot.off{background:#cfd4d7}
.crit{margin:0;padding-left:18px}
.crit li{margin:0 0 3px}
.fig{margin:6px 0 16px;padding:0;text-align:center}
.fig svg{max-width:100%;height:auto}
.fig.net{border:1px solid var(--rule);border-radius:4px;padding:14px;
 background:#fdfdfc}
.fig.net svg{max-width:100%;height:auto;display:block;margin:auto}
.fig.net h4{margin:0 0 6px;font-size:12.5px;color:var(--mute);text-align:left}
h4{font-size:12px;text-transform:uppercase;letter-spacing:.05em;
 color:var(--mute);margin:16px 0 6px;font-weight:600}
table.model td:nth-child(1){white-space:nowrap}
table.model td code{background:none;padding:0}
table.model td:last-child{font-variant-numeric:normal}
.qqgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin:0 0 14px}
.qq{border:1px solid var(--rule);border-radius:4px;padding:10px;
 background:#fdfdfc}
.qq.reject{border:1.5px solid #e3c98f;background:#fdf8ec}
.qq svg{max-width:100%;height:auto;display:block;margin:auto}
.qqobs{font-size:12px;font-weight:600;margin-bottom:4px}
.qqcap{font-size:11px;color:var(--mute);margin:6px 0 0;line-height:1.4}
.qqnote{font-size:11px;color:#8a5300;font-weight:600;margin:6px 0 0;
 line-height:1.35}
.qqmuted{font-size:12px;color:var(--mute);font-style:italic;margin:6px 0 0}
.mods{display:block;margin-top:3px;font-size:11.5px;color:var(--mute)}
.derived{color:#5a6570;font-style:italic}
.mute{color:var(--mute)}
figcaption{font-size:11.5px;color:var(--mute);margin-top:4px;text-align:left}
/* the four figures a modeller reads first: fit, waterfall, parameters vs
   bounds, profiles. Tables support them; they do not lead. */
.fig.lead{margin:10px 0 22px}
.fig.lead figcaption{font-size:12px;color:#4a5055}
.flagbox{border:1px solid #eeddb8;background:#fdf9f0;border-radius:4px;
 padding:10px 14px;font-size:13px;margin:0 0 14px}
.okbox{border:1px solid #bfe0cc;background:#f3f9f5;border-radius:4px;
 padding:10px 14px;font-size:13px;margin:0 0 14px}
.flagbox ul,.okbox ul{margin:6px 0 0;padding-left:18px}
.epi{display:grid;grid-template-columns:1fr 1fr;gap:20px;border:1px solid var(--rule);
 border-radius:4px;padding:16px 18px;margin:0 0 14px;background:#fcfcfb}
.epi h3{margin-top:0}
.epi .epi-col.wide{grid-column:1/-1}
.epi ul{margin:0;padding-left:18px;font-size:13.5px}
.epi li{margin:0 0 5px}
.ref{font-size:11.5px;color:var(--mute);margin:10px 0 0;
 border-top:1px dotted var(--rule);padding-top:7px;overflow-wrap:anywhere}
.pocket{background:#f6f4ef;border-left:4px solid #b99a56;border-radius:0 4px 4px 0;
 padding:6px 20px 16px}
.pocket-hd{font-size:11.5px;font-weight:700;letter-spacing:.09em;
 text-transform:uppercase;color:#7d6631;margin:12px 0 4px}
.pocket h3{margin-top:16px}
.pocket .rec{font-weight:600}
.pocket pre,.pocket table{background:#fffdf8}
.colophon{font-size:11.5px;color:var(--mute);margin-top:20px;
 border-top:1px solid var(--rule);padding-top:12px}
.askbox{border:1px solid #e3c98f;background:#fdf8ec;border-radius:4px;
 padding:14px 18px;font-size:14px;margin:0 0 16px}
.asks{margin:12px 0 0;padding-left:22px}
.asks li{margin:0 0 14px}
.ask{font-weight:600;margin:0 0 4px}
.askmeta{font-size:12.5px;color:#57606a;margin:0}
.tier{display:inline-block;font-size:11px;padding:1px 6px;border-radius:3px;
 white-space:nowrap}
.tier-default{color:#8a5300;background:#fbf1e0}
.tier-transferred{color:#8a6a1f;background:#fdf8ea}
.tier-direct{color:var(--pass);background:#e8f3ec}
.tier-none{color:var(--mute);background:#eef0f1}
.conf{font-variant-numeric:tabular-nums;font-weight:600}
.conf.lo{color:#b3261e}
.conf.hi{color:#3b4045}
table.assumptions{table-layout:fixed}
table.assumptions th:nth-child(1),table.assumptions td:nth-child(1){width:70%}
table.assumptions th:nth-child(2),table.assumptions td:nth-child(2){width:18%}
table.assumptions th:nth-child(3),table.assumptions td:nth-child(3){width:12%}
table.assumptions td{font-variant-numeric:normal;overflow-wrap:break-word}
table.assumptions tbody td{padding-top:12px;padding-bottom:12px}
.dtext{font-weight:600}
/* the argument the model rests on: primary content, full reading size */
.rationale{margin:7px 0 0;font-size:13.5px;line-height:1.5;color:#22262a;
 border-left:3px solid #c3ccd4;padding-left:11px}
.evlist{margin:8px 0 0;padding-left:11px;border-left:3px solid #eceff1}
.ev{display:block;font-size:12px;line-height:1.45;color:#3b4045}
.ev.gen{color:#8b9298}
.ev .loc{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
 font-size:.92em;color:#57606a}
.prec{margin:8px 0 0;font-size:11.5px;color:#9aa1a7;font-style:italic}
.alts{margin:8px 0 0;font-size:12px;color:#6a7075}
.demoted{display:block;margin-top:5px;font-size:10.5px;font-weight:600;
 line-height:1.3;color:#8a5300;background:#fbf1e0;border:1px solid #eeddb8;
 border-radius:3px;padding:3px 5px}
.qnote{display:block;margin-top:8px;font-size:12px;color:#7d6631;
 border-left:2px solid #d8c48b;padding-left:8px}
@media (max-width:720px){.kv{grid-template-columns:1fr}
 .epi{grid-template-columns:1fr}
 .qqgrid{grid-template-columns:1fr}}
@media print{main{max-width:none;padding:0}
 body{font-size:11pt}
 .sec{break-inside:avoid-page}
 details{display:block}
 details>summary{list-style:none}
 .fig{break-inside:avoid}
 a{color:inherit;text-decoration:none}}
"""


def page(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>{_CSS}</style>\n"
        f"</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )
