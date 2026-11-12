"""The round report and the model report, rendered from a round's record.

A renderer, not a module: no agent is called and nothing is inferred; every
number and figure is read (or simulated) from the round's record. The
agent's own words appear only in the labelled narrative pocket of section 10.
The section order is a contract (REPORTING.md); a section whose record is
absent renders a visible note, and nothing here may raise.

Each takes the round node `rounds/round_k` and reads it inside one
`store.reading()` block. The rendered documents are REAL files beside the
record, under `runs/<id>_reports/round_k/report/`:

  render_report_html(rnd)       -> str
  write_report_html(rnd)        -> Path  (…_reports/round_k/report/report.html)
  render_model_report_html(rnd) -> str
  write_model_report_html(rnd)  -> Path  (…/model_report.html)
"""

from __future__ import annotations

from octomod.reporting.figures import figure
from octomod.reporting.html import esc, note, page, table
from octomod.reporting.model_report import (
    render_model_report_html,
    write_model_report_html,
)
from octomod.reporting.round_report import render_report_html, write_report_html

__all__ = [
    "esc",
    "figure",
    "note",
    "page",
    "render_model_report_html",
    "render_report_html",
    "table",
    "write_model_report_html",
    "write_report_html",
]
