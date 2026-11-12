# Getting started

You bring measurements and a question. Before anything runs, the problem is
*staged*: put into one folder that says what was measured, what you want to
know, and what counts as success. Octomod's front end, Claude Code, stages it
with you; this page says what that involves, and how to do it by hand.

## 1 · Install

You need [uv](https://docs.astral.sh/uv/), a C++ compiler (on macOS
`xcode-select --install`; on Linux `build-essential` and `libhdf5-dev`),
graphviz for the report figures, and [Claude Code](https://claude.com/claude-code)
(the `claude` command), logged in in the terminal with `claude auth login`. Then:

```bash
git clone https://github.com/ICB-DCM/Octomod.git
cd Octomod
uv sync
```

The first `uv sync` takes a few minutes. If something does not work, start
`claude` in the folder anyway and say so: checking your machine is the first
thing it does.

A check that the install works, without spending anything (it writes two small
records into `runs/`):

```bash
uv run python tests/golden_path.py toy_phos toy_decay_params
```

Two things to know. The first time you open the folder in Claude Code, accept
the trust dialog: the project's permission rules (`.claude/settings.json`) apply
only after that. And if you use Claude Code's sandbox, run `uv sync` yourself in
a terminal before you start Claude: uv keeps its package cache outside the
project folder, where a sandboxed command cannot write.

## 2 · Stage your problem

A staged problem is one folder, `staging/<project>/`, named after your
problem. Nothing in `staging/` is committed to git.

**Put your data in.** Copy your measurement files (CSV or TSV) into its
`data/` folder, as they are:

```text
staging/my_problem/data/my_measurements.csv
```

Claude reads nothing outside the repository folder (a setting in
`.claude/settings.json`), so the files have to be there before you start.

**What the data files must look like.** The engine does not ask for a fixed
layout. An agent reads each file's header and first rows beside your lab
note, and says which column is what, using the column names as written. A
few things are required, and the run stops with the reason if one is missing:

- **`.csv` (comma) or `.tsv` (tab) only, directly in `data/`.** Files in
  subfolders and other formats are not read. An Excel or LibreOffice
  workbook (`.xlsx`, `.xls`, `.xlsm`, `.ods`) in `data/` stops the run: export
  each sheet you want modelled to its own file, then remove the workbook.
  Which sheet is the data, and which row is the header, is your call.
- **The header row first**, one column per field, one measurement per row.
- **A numeric time column.** A measurement taken at steady state has the
  time `inf`. Rows marked "steady state" in words need `inf` in the time
  cell.
- **Numbers only in the value cells.** No values are edited, interpolated or
  dropped. Rows that look wrong are flagged for you, never removed.

Within that, either shape works:

```text
wide: one column per measured quantity        long: one column names the quantity
dose,time_min,replicate,pR_au,pS_au            dose,time_min,readout,value
0.3,0,1,0.37,0.12                              0.3,0,pR_au,0.37
0.3,5,1,3.01,0.80                              0.3,0,pS_au,0.12
```

Columns for the experimental condition (dose, inhibitor, cell line…), for
replicates, and for a per-row error (SD or SE) are all optional. The units
and the error type (SD, SEM, replicates) are read from your lab note, so
write them there. Measurements that are normalised, fold-change or arbitrary
units are fine, as long as the note says so. The column names you choose
also name the held-out measurements in `testcase.yaml`, e.g. `dose=3`.

**Start Claude in the repository folder and describe your problem** — what you
measured, how, and what you want to know:

```bash
claude
```

Claude then writes the rest of the folder *with* you, asking where it needs
your answer:

```text
staging/my_problem/
  data/            your measurements, never edited
  description.md   the experiment, written as a lab note
  intent.yaml      the question, the system, what counts as success
  testcase.yaml    the time horizon and the measurements held back
  knowledge/       what is known about your system (written by the knowledge module)
  supplied/        optional: a model or a PEtab problem you already have
```

Three of the decisions it asks for are yours alone:

- **Which measurements to hold back.** The engine never sees them while it
  fits, and tests the models on them afterwards. The agent never picks its own
  exam.
- **Whether to search the literature.** Before the first run, a knowledge
  module collects what is known about your system — online if you allow a
  literature search, from the model's own knowledge otherwise — and shows the
  reactions a model of it needs, each graded by how well the sources support
  it.
- **How much support a reaction needs** before it goes unflagged (the
  *support floor*). By default the floor is advisory: the model may use any
  reaction, and each one below the floor, or with no source, is flagged on
  the gate card for you to review. With `grounding: {mode: strict}` in
  `testcase.yaml` it is a limit instead. The first model then holds only
  reactions at or above the floor, so a higher floor gives a first model
  closer to the literature, and a lower one lets the data suggest mechanisms
  sooner. The run does not start until you have chosen.

A measurement taken at steady state has the time `inf`. If your file marks
such rows in words, Claude asks before it changes the time cell, and records
the change in `description.md`.

## 3 · Start a run, and make the decisions

Claude asks before it starts a run, because a run uses your Claude usage. The
run then pauses whenever a person should decide: whether the question is
stated right, which mechanisms to test, how much computing time to spend, and
whether to accept the result. Claude shows you each question with what each
answer would lead to; you answer, and Claude passes your answer on unchanged.

When the run starts, it copies what it reads of your folder into its record,
`runs/<run id>.h5`. Editing the folder afterwards changes nothing in that run:
a changed problem is a copy of the folder, edited, and a new run.

## 4 · Read the results

Start with `runs/<run id>_reports/ANALYSIS.html`: what was asked, every model
tried, which one won, the answer, and what is still open. Claude walks you
through it, and through the reports of each round behind it.

The [walkthrough of a real run](examples/ctd_blind/walkthrough.ipynb) shows
all of this on real data, from the question to the answer.

## Staging by hand

You can write the folder yourself and ask Claude to check it. The files of a
small fixture in the repository, `testcase/toy_phos_knowledge/`, are a
template. Its `intent.yaml`:

```yaml
question: >-
  How does phospho-R respond to ligand dose, and can a calibrated model predict
  the response at the highest dose?
system: synthetic receptor module (toy)
required_entities: [R, Rp]
required_reactions:            # optional: reactions the model must contain
  - equation: R -> Rp
    note: ligand-driven phosphorylation; the ligand enters as a dose, not a species
required_predictions:
  - pR_au time course at dose=3
perturbations:
  - ligand dose 0.3 / 1 / 3 (relative units)
timescale: minutes, horizon 60 min
scope_exclusions:
  - receptor synthesis/degradation
success_criteria:
  - held-out dose=3 normalised RMSE < 0.2
inference_target: prediction   # or parameter_values, mechanism_discrimination
```

and its `testcase.yaml`, which names the held-out measurements by the data
file's own column names (`dose` is a column of its `data/timecourse.csv`) and,
for a literature search, the newest publication year the search may use:

```yaml
name: toy_phos_knowledge
holdout:
  condition_labels:
    - dose=3
research:
  max_publication_year: 2025   # needed by --mode online; refused without it
```

Then run the knowledge module on the folder, and record your floor decision
in `testcase.yaml` (Claude shows you the card and the form):

```bash
./run.sh knowledge --testcase staging/my_problem --mode online --backend llm   # or --mode offline
./run.sh knowledge --testcase staging/my_problem --show                        # the card again
```

The complete description of every file in the folder is in `CLAUDE.md` in the
repository, under "Staging a user's problem".
