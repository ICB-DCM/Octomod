# Reporting

This folder renders the documents a person reads, from the run record alone. No agent is called:
every number is read from the record, and every figure is drawn from it or simulated from the
recorded model. The agents' own words appear in labelled places, such as the interpretation and the
decision record in the round report and quoted decisions in the model report. A section whose part
of the record is missing shows a note instead, and a document that fails to render never stops a
run. The documents are files in `runs/<id>_reports/`, beside the record; each HTML page is
self-contained, with its figures inline, and can be rendered again at any time.

| document in `runs/<id>_reports/` | what it shows | written |
|---|---|---|
| `round_<k>/report/model_report.html` | the models as built: the network, the points needing your input, the assumptions ranked by uncertainty, the results of the checks, and the sources | by the module engine of M1 and M2, before you decide what to fit |
| `round_<k>/report/report.html` | the round in 13 fixed sections: the intent, the model, the data, the estimation and the fit, the evaluation, the agent's interpretation, the decisions, the checks, and the agent calls | by the module engine of M7, before the verdict card and again after your answer |
| `ANALYSIS.html`, `ANALYSIS.md` | the run: what was asked, every model assessed across the rounds, which one won, the answer, and what is still open | by the central engine at the end of a run, not when it stops early |

The sections of the model report are labelled M1 to M5; they are not the workflow modules.

To render them again, for example for a run that stopped: `./run.sh report --run-id <id>` writes
the latest round's `report.html`, `--round <k>` another round's, `--model` adds the model report,
and `--analysis` writes `ANALYSIS` instead.

[`docs/REPORTING.md`](../../docs/REPORTING.md) is the contract for these documents: every section and
the part of the record it is filled from, the limits on the length of text, and the conventions of
the figures.

## Reference

<details>
<summary>Which file renders what, and the texts kept in the record</summary>

- `model_report.py`, `round_report.py`, and `analysis_report.py` render the three documents;
  `analysis_report.py` also keeps the run's summary in the record at `analysis`.
- `sbml_view.py` draws the model's tables and network diagram for both round documents, with
  graphviz when it is installed and with matplotlib otherwise. `figures.py` holds the figure
  plumbing and most figures, `html.py` the page shell.
- `budget.py` holds the limits on the length of text, which `docs/REPORTING.md` publishes;
  `tests/report_budget_unit.py` fails when the two disagree. Text over a limit is moved into a fold
  or a link, never deleted.
- `render.py` builds the texts that are kept in the record, not as files: the round's decision
  record, `rounds/round_<k>/decisions_md` (who decided what, and why, assembled from the agents'
  structured replies), and the model as a Mermaid diagram, `…/model/mermaid`. It also builds the
  model's text view on a card. The round's report in Markdown, `rounds/round_<k>/report_md`, is
  written by the module engine of M7.

</details>

## Files

| file | what it is |
|---|---|
| `analysis_report.py` | The whole-analysis report: one document for the run, not for a round. |
| `budget.py` | Render-side prose budgets and the clipping that enforces them. |
| `figures.py` | Matplotlib and SVG plumbing, and the figure builders that take plain data. |
| `html.py` | Escaping, small HTML builders, record loaders, and the page shell. |
| `model_report.py` | Model_report.html — M1 to M5, the model as built. |
| `render.py` | Text and mermaid views derived from the typed record. |
| `round_report.py` | Report.html — the round's 13 fixed sections, in order. |
| `sbml_view.py` | SBML rendered two ways: as species, reaction and parameter tables, and as a network diagram. |
