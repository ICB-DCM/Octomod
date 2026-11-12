# M3 · Data extraction

M3 turns your data files into one long measurement table that every model of the run shares. The
`data_extraction` agent says what each column means; the module engine moves the numbers and checks
the table. It also measures the noise of each measured quantity and describes the curves in words,
for later modules. M3 runs once, in round 0, the first pass through the modules; later rounds carry
the table forward and check it again. A table you put in `supplied/` skips the agent but not the
checks.

## What happens

1. The module engine reads only comma- and tab-separated files. A spreadsheet file stops the module
   by name, and so does a data folder with neither kind.
2. The `data_extraction` agent sees the header and first 25 rows of each file and a summary of the
   experimental design, never the model. It maps the columns for time, value, condition, replicate
   and error, with units, and may declare processing steps from a fixed list.
3. The module engine moves the numbers as mapped. Text in a number cell, such as a below-detection
   mark, is refused by name; a failing mapping goes back to the agent with the reason.
4. It runs the declared processing and checks the table: every row well formed, units and an error
   type for every measured quantity. A screen notes negative values and constant series, as findings
   only.
5. It checks that the held-out conditions named in `testcase.yaml` match the table. These are kept
   from fitting to test the models, and processing may not read them.
6. It measures the noise of each quantity from the replicates and describes the curves in words,
   leaving out the held-out conditions.

A failed check goes back to the agent with the check, up to 3 attempts; after that you are asked.

## Agents

| agent | what it does here |
|---|---|
| `data_extraction` | says what each column means, with units and error type; may flag rows, never exclude them or write values |

What each agent is shown is listed in [`docs/ROUTING.md`](../../../docs/ROUTING.md). What it must
return is in its file under [`skills/`](../../../skills/).

## Where it asks you

- **Grant more attempts to fix the table?** When a check still fails after 3 attempts, you can grant
  more, ask the agent again in your own words, or stop the run. Asking in your own words spends no
  attempt. A table you supplied has no agent to ask: fix it and start a new run.
- **Grant more attempts to read the files?** When the mappings still cannot be executed after 3
  attempts, you can grant more or stop.
- Nothing else. The agent's flags reach you later, on the card where M4 asks to compile the models.

## What it writes

The round's data go into the run record: the measurement table, the table before any processing,
the agent's report and the design summary. The noise of each quantity and the curves in words are
kept beside them. Section 4 of each round report, `runs/<id>_reports/round_k/report/report.html`,
plots the data, one figure per measured quantity.

## Reference

<details>
<summary>Exact inputs and outputs of the agents, the checks with their ids, and the answer forms</summary>

### Agents: what each receives and returns

| agent | receives | returns |
|---|---|---|
| `data_extraction` | the intent, the project description, a preview of each data file (the header and first 25 rows, with the total row count), and the experimental design summary (every design column's levels over the whole file, rows and replicates per condition, the absent combinations; no measurement value); never the model; on a redraft the failing check, its own mappings for the labels concerned and the rows built from them | `mappings` per file (time column, value column, condition columns and the label template, replicate column, error column, units), `observable_labels` (label, description, units, error type), `flags`, `notes`; optional `processing` from a closed vocabulary (`normalize_by_group_sum`, `subtract_reference`, `scale_units`) and `below_detection` (what the source did below its detection floor) |

### Checks, with their ids

- **Before the agent** (stops the module): a spreadsheet file in `data/` is refused by name, since
  M3 reads only `.csv` and `.tsv`; a folder with neither stops too.
- **Executing the mappings**: every mapped file and column exists, time and value cells are
  numbers (text such as `<LOD` is refused by name, with its rows), a replicate column has no blank
  cell, an error column holds finite positive numbers, the label template names existing columns,
  and at least one row comes out. A mapping that fails goes back to the agent with the reason.
- **The processing** runs next, on the extracted rows; `data_processing_legal` (blocking) checks
  that every step is in the vocabulary, names labels the table has, and reads no held-out cell.
- `data_rows_well_formed` (blocking): times are numbers (`inf` for a steady-state measurement,
  nothing negative), no value is missing, no (observable, condition, time, replicate) key repeats,
  and condition labels and condition keys match one to one.
- `data_units_and_error_declared` (blocking): every observable declares units (`arbitrary` is
  allowed) and an error type (`sd`, `sem`, `replicates`, `none` or `column`); `column` needs an
  error column, and a below-detection declaration must be well formed.
- `data_holdout_labels_resolve` (blocking): the held-out conditions named in `testcase.yaml`
  match conditions in the table, read as `column=value` pairs on the data's own columns.
- `data_plausibility_screen` (advisory): negative values, series constant to machine precision,
  and the rows a declared detection floor touches, as findings only.

A blocking failure goes back to the agent with the check verbatim, 3 attempts in all. The agent
may flag rows but never exclude them, and no agent writes a value.

### Interaction points, with the answer forms

- **Failure point**, when a blocking check still fails after the agent's 3 attempts:
  `n=<attempts>` grants more, `redraft: <words>` asks the agent again with your words (it does not
  spend an attempt), `n` stops the run. A table you supplied has no agent to ask: fix it and start
  a new run.
- **Failure point for the mappings**, when they still cannot be executed after 3 attempts:
  "Redraft budget exhausted for data_extraction. Grant more attempts?", answered `n=<N>` or `n`.
- Otherwise none. The agent's flags reach you on the compile card in M4.

### What it writes, with the record keys

The round's `data` group: `measurements` (one row per data point: observable label, condition
label, time, value, replicate, and sigma when an error column was mapped), `raw` (the table before
processing, when there was any), `report` (mappings, labels, flags, notes, the processing and its
numbers), `design_summary`, `signals` (the noise character of each observable, measured from every
replicate) and `phenomenology` (the curves in words, without the held-out conditions).
`./run.sh show --run-id <id> rounds/round_0/data/measurements` prints the table.

</details>

## Files

| file | what it is |
|---|---|
| `censoring.py` | Below-detection measurements: declared, not modelled. |
| `curve_forms.py` | Which simple functional form one time series follows, and on what timescale. |
| `data_processing.py` | Measurement processing: a closed vocabulary (`KINDS`) the engine executes. |
| `data_signals.py` | What the data itself says before any model exists: deterministic, no agent. |
| `design_summary.py` | The experimental design of a data file, without any measurement value. |
| `engine.py` | Data extraction and curation. |
| `phenomenology.py` | What the raw curves look like, in the words a modeller says off a plot. |
| `raw_phenomenology.py` | The curves in words, read from the RAW data files before construction. |
