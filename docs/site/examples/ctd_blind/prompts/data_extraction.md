# Prompt · `data_extraction` (round 0)

The **data_extraction** agent reads the data file into measurements (S2). Below is the exact prompt it was sent in this run (24,341 characters), as the record keeps it, followed by its reply. The prompt is the role's instructions (its skill) followed by the inputs the engine chose to show it; nothing else reached the agent. The agent was called 2 times here; the record keeps the prompt and reply of the last call.

[← back to the walkthrough](../walkthrough.ipynb)

## The prompt

````text
# Data extraction: say what the columns of the data files mean

For each file you declare which column is time, which holds the value, which define the condition, which (if any)
holds replicates, and each measured quantity's label, units and error type. The engine moves the numbers; you decide
only what they mean.

## What you receive
`data_file_previews` (header, first rows, total row count), `design_summary` (every design column's levels over the
whole file and the absent combinations, no values), `intent`, `experiment_description` (the lab note). Never the
model: an extraction that knows the mechanism can label a column to suit it.

Where one exists for your role, a curated worked example (good and bad practice, labelled) follows this brief.

## What you return
`mappings`, `observable_labels`, `flags`, `notes`, all required; `processing` and `below_detection` optional (shape,
long-format files and per-row error columns: Output contract). A mapping the engine cannot execute comes back with
the reason.

## Rules that get your reply refused
- Never invent, edit, reorder or drop rows, and never write data values: 431 rows in, 431 rows out.
- Every column you name appears verbatim in the header you were shown: no renaming, no guessing at unseen columns.
- `units` for every quantity, or the literal `arbitrary` for relative, normalised or a.u. readouts.
- `error_type` explicitly (`sd`, `sem`, `replicates`, `none`, or `column` with an `error_column`). Error bars of
  unstated type are not `sd` by default: record what the source says and flag the ambiguity.
- `condition_label_template` uses the condition column names verbatim (`dose={ligand_nM}`) and every column in
  `condition_columns`: the engine builds labels from it, and a dropped column silently merges conditions. The text
  around the placeholders is yours; evaluation and holdouts match on the columns, never on it.
- Flag and rank, never exclude: exclusion is a human decision and is ledgered. A suspicious value goes in `flags`
  with file, column, rows and what looks wrong; an ambiguous column is flagged, not read the convenient way.

## How to judge
- Read the lab note and the header together: `value`, `y`, `signal` say nothing; the note says what was measured.
- SEM against SD is your highest-consequence call: a silent √n error in every likelihood weight that nothing
  downstream reveals. Record `n` wherever given; where the caption and the field's convention disagree, record the
  caption and flag the conflict.
- Repeated (condition, quantity, time) keys with differing values are replicates; without a replicate column,
  duplicates are a flag.
- A measurement taken at steady state rather than at a sampled time (read once the system settled) has the time
  `inf`, PEtab's convention, and is compared against the model's steady state. A time column holding `inf` in those
  rows is mapped like any other. Rows that say "steady state" in words, or in a column of their own, are a flag: the
  engine never reads text as a number, so the file needs `inf` in the time cell, and that edit is the human's.
- Normalised-to-t0, fold-change and percent-of-control data are `arbitrary` with an implicit constraint at the
  reference point: flag it and leave it to the observation model. Time units that disagree with the model's timescale
  are a flag, not a conversion. Two files normalised differently are not commensurable: flag, do not pool. Small
  negatives after background subtraction are usually real.
- **Processing** is a closed vocabulary the engine executes in order, on the rows of one cell (condition, time,
  replicate) or against one declared reference; you declare, it computes, the report shows the numbers:
  `normalize_by_group_sum {labels}` (row normalisation, divisor kept per cell), `subtract_reference {labels,
  reference: {observable_label | condition_label | time}}` (a blank lane, an unstimulated well, t = 0), `scale_units
  {labels, factor, from_units, to_units}`. Declare a step only when the note says the data were processed that way or
  a blank or reference is in the files; an assumption a scale factor can carry is the observation model's. Dropping
  or clipping rows, transformations and anything read from a fit are not processing. A held-out reference condition
  is refused by name and comes back with the usable ones.
- **Below detection.** When the source states a detection floor (an array background, an assay limit, a site not
  detected at t = 0), declare per observable what the source did below it: `rule` `imputed` (a floor or fill value
  written in), `dropped` (rows absent) or `left_as_is`, with `threshold` on the measurement's own scale, or null.
  Declare, never impute, clip or reconstruct: no censored likelihood is fitted, so the declaration is what keeps the
  limitation visible, and an imputed floor swallowed quietly makes every candidate look cleaner than the data justify.

## Mistakes we have seen
- Dropping rows that are blank, negative or "obviously wrong": the silent corruption this module exists to prevent.
- Mapping a column by position, or naming one that does not exist.
- Recording `sd` because the caption said SD when the field reports SEM by convention, or the reverse, silently.
- Treating a.u. as absolute, or inferring units from the size of the numbers.
- Merging two conditions the note distinguishes, or splitting one it does not.
- Interpolating a missing time point, or extending a series to another file's grid.
- Leaving out a dataset judged unreliable.


# Your tools
TOOLS: none. No shell, no file system, no web, no code execution, and no way to inspect data beyond what this prompt contains — the inputs below are everything this role is given, by design. A command, a tool call, or 'let me look at …' written into the reply cannot run and fails the contract. Reply with the JSON object only.

# Inputs

## intent
```json
{
  "question": "Build a model of this CTD phosphorylation time course that explains the measured distributions, and say what it implies about how P-TEFb modifies the substrate. Report explicitly what these data can and cannot establish about the mechanism. In particular, test whether the modification of a repeat changes the rate at which its immediate neighbours in the array are modified, against the alternatives that the rate depends only on how many repeats are already modified (cooperativity between repeats) or on nothing at all, and say which of these the data can and cannot separate. Also test the earlier conclusion, drawn by eye, that the kinase acts distributively rather than processively.",
  "system": "RNA polymerase II CTD (8 heptarepeats, in vitro), phosphorylated by P-TEFb (CDK9/cyclin T1); mass-spectrometry time course",
  "required_entities": [
    "CTD",
    "P-TEFb",
    "ATP"
  ],
  "required_predictions": [
    "the mechanism of phosphorylation that best explains the measured distributions, identified and defended",
    "a statement of which mechanistic questions these data cannot answer"
  ],
  "perturbations": [
    "none \u2014 a single in vitro condition, sampled over time"
  ],
  "timescale": "minutes, horizon 960 min (16 h)",
  "scope_exclusions": [
    "transcription, DNA and the polymerase itself \u2014 this is a purified in vitro assay",
    "the distinction between Ser2 and Ser5 within a repeat (established as mutually exclusive under these conditions; each repeat is one bit)"
  ],
  "success_criteria": [
    "the selected mechanism is reported with its information criterion, its Akaike weight and the indistinguishable set, honestly, whatever they turn out to be",
    "the observation model is stated explicitly, including how predicted amounts are mapped onto relative MS intensities at each time point",
    "any mechanistic question the data cannot resolve is named as unresolved rather than decided"
  ],
  "inference_target": "mechanism_discrimination",
  "domain_packs": [
    "general-dynamics",
    "measurement-tech"
  ]
}
```
## experiment_description
# CTD phosphorylation by P-TEFb — in vitro time course (bench note)

## The system

RNA polymerase II carries a long, flexible tail on its largest subunit called the
C-terminal domain, or CTD. The CTD is not a folded domain: it is a tandem array of
short repeats, each seven amino acids long, with the sequence Tyr–Ser–Pro–Thr–Ser–Pro–Ser.
In human Pol II there are 52 of these heptarepeats. During transcription the CTD is
progressively decorated with phosphate groups, and the resulting pattern of marks is
what recruits and releases the RNA-processing and elongation factors that act on the
polymerase. Which marks are present, and where, is therefore functionally important.

The kinase we are studying here is **P-TEFb** (the CDK9–cyclin T1 complex), which acts
during transcriptional elongation.

## The experiment

This is an **in vitro kinase assay**, not a cellular experiment. There is no
transcription, no DNA, no polymerase — only a purified CTD substrate, purified kinase,
and ATP in buffer.

- **Substrate**: a recombinant CTD construct containing **8 heptarepeats**, not the full
  52. Present at **100 µM**.
- **Kinase**: P-TEFb, catalytic. It is not consumed and its concentration does not change
  over the experiment.
- **ATP**: **3 mM** at the start. Each phosphorylation consumes one ATP.
- **Sampling**: four time points — **0, 1 h, 2 h and 16 h** (0, 60, 120 and 960 minutes).
- **Replication**: one measurement per species per time point. There are **no replicate
  measurements** in this dataset.

## What the readout is, and what it cannot see

The readout is **mass spectrometry** on the intact CTD construct. MS separates the
substrate molecules by mass, and since each phosphate adds a fixed mass, it resolves
**how many of the eight repeats carry a phosphate** — a number between 0 and 8.

**It does not resolve which repeats those are.** A molecule phosphorylated on repeats 1
and 2 and a molecule phosphorylated on repeats 1 and 7 are the same mass and appear in
the same peak. Everything downstream has to live with that: the data are nine numbers per
time point, one for each phosphorylation count, and the positional arrangement behind
those numbers is not observed.

A second point about the chemistry, established previously for this kinase and these
conditions: within a single heptarepeat, phosphorylation happens on **either Ser2 or
Ser5, but not both at once**. So for the purposes of counting, each repeat is either
modified or unmodified — one bit per repeat — and the distinction between the two serine
positions does not need to be tracked.

## The data file, and a caveat you must handle

`data/ctd_ms_timecourse.csv` has one row per time point and nine columns, `phos0_rel`
through `phos8_rel`: the relative MS signal for CTD molecules carrying 0, 1, … 8
phosphates.

**These are relative signal intensities, not concentrations, and they are not comparable
between time points as they stand.** Mass spectrometry reports intensities on an
arbitrary scale that drifts between injections. You can see this directly in the file:
the nine numbers sum to 1.00 at t = 0, to 4.07 at 1 h, to 3.79 at 2 h and to 0.85 at
16 h, even though the total amount of substrate in the tube is conserved throughout.
Any model of this data needs a way to map predicted amounts onto measured intensities,
and that mapping is not the same at every time point.

The measurement error is believed to be additive and normally distributed, with a single
standard deviation for the whole experiment — the same for every peak — that scales from one
time point to the next with that spectrum's overall intensity, the same factor that maps
amounts onto intensities at that time point.

## What is already believed, and what is not settled

Earlier work on this kinase, using this kind of hyperphosphorylation assay in human and
in *Drosophila*, concluded that P-TEFb works **distributively rather than processively**:
that it modifies a repeat, lets go, and rebinds — rather than holding on and running
along the substrate. That conclusion came from looking at the shape of MS distributions
by eye, and was never checked against a quantitative model.

Beyond that, the mechanism is genuinely open. We do not know from these data what governs
the rate at which any individual repeat gets modified, and that is what we would like a
model to tell us. One specific possibility was put to us and we want it tested rather than
assumed either way: that the modification of one repeat changes the rate at which its
immediate neighbours in the array are modified, as opposed to the rate depending only on
how many repeats of the molecule are already modified (cooperativity between repeats,
which was also raised as a possibility to look at), or on nothing at all.

## What can be computed here

Any model that simulates is acceptable, whether it tracks only how many repeats are
modified or which repeats are modified (with eight repeats, 256 configurations). Models
of a few hundred states and a thousand reactions simulate in seconds on the machine this
runs on, so size alone is not a reason to prefer one description over another; choose
the description the question needs. If a possibility can only be represented by tracking
which repeats are modified, we would rather see that model fitted than the question
settled by argument from the counts alone. Such a model can be written out in full, every
state and every reaction listed one by one, and we would rather it were written out than
avoided. The simulator reserves the single letters x, k, p, y, w, h and t, so no species
or parameter may be named with one of them.

## The question

Build a model of this time course that explains the measured distributions, and tell us
what it implies about how P-TEFb modifies the CTD. Be explicit about what these data can
and cannot establish — with eight repeats, four time points and no positional
information, we expect there to be things the data simply cannot decide, and we would
rather know which those are than have them glossed over. We would also like the earlier
conclusion, drawn by eye, that the kinase acts distributively rather than processively,
to be tested against a model and not assumed.

## data_file_previews
```json
{
  "ctd_ms_timecourse.csv": "(file has 4 rows total; preview of first 25)\ntime_min,phos0_rel,phos1_rel,phos2_rel,phos3_rel,phos4_rel,phos5_rel,phos6_rel,phos7_rel,phos8_rel\n0,0.999568752,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0\n60,0.393511301,0.897469038,0.897676748,0.779681099,0.594147075,0.352327675,0.158350845,0.0,0.0\n120,0.060808535,0.190472606,0.398928055,0.624281335,0.82711232,0.855458644,0.641781932,0.194516845,0.0\n960,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.851626189\n"
}
```
## design_summary
```json
{
  "available": true,
  "per_file": {
    "ctd_ms_timecourse.csv": {
      "n_rows": 4,
      "columns": {
        "time_min": {
          "role": "time",
          "dtype": "int64",
          "n_unique": 4,
          "n_missing": 0,
          "levels": [
            0,
            60,
            120,
            960
          ]
        },
        "phos0_rel": {
          "role": "measurement",
          "dtype": "float64",
          "n_unique": 4,
          "n_missing": 0
        },
        "phos1_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.190472606,
            0.897469038
          ]
        },
        "phos2_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.398928055,
            0.897676748
          ]
        },
        "phos3_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.624281335,
            0.779681099
          ]
        },
        "phos4_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.594147075,
            0.82711232
          ]
        },
        "phos5_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.352327675,
            0.855458644
          ]
        },
        "phos6_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 3,
          "n_missing": 0,
          "levels": [
            0.0,
            0.158350845,
            0.641781932
          ]
        },
        "phos7_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 2,
          "n_missing": 0,
          "levels": [
            0.0,
            0.194516845
          ]
        },
        "phos8_rel": {
          "role": "design",
          "dtype": "float64",
          "n_unique": 2,
          "n_missing": 0,
          "levels": [
            0.0,
            0.851626189
          ]
        }
      },
      "design_columns": [
        "phos1_rel",
        "phos2_rel",
        "phos3_rel",
        "phos4_rel",
        "phos5_rel",
        "phos6_rel",
        "phos7_rel",
        "phos8_rel"
      ],
      "time_columns": [
        "time_min"
      ],
      "replicate_columns": [],
      "measurement_columns": [
        "phos0_rel"
      ],
      "factorial": {
        "available": true,
        "factors": [
          "phos1_rel",
          "phos2_rel",
          "phos3_rel",
          "phos4_rel",
          "phos5_rel",
          "phos6_rel",
          "phos7_rel",
          "phos8_rel"
        ],
        "n_full_factorial": 2916,
        "n_present": 4,
        "n_absent": 2912,
        "balanced": false,
        "per_cell": [
          {
            "cell": {
              "phos1_rel": 0.0,
              "phos2_rel": 0.0,
              "phos3_rel": 0.0,
              "phos4_rel": 0.0,
              "phos5_rel": 0.0,
              "phos6_rel": 0.0,
              "phos7_rel": 0.0,
              "phos8_rel": 0.0
            },
            "n_rows": 1,
            "n_time_points": 1
          },
          {
            "cell": {
              "phos1_rel": 0.0,
              "phos2_rel": 0.0,
              "phos3_rel": 0.0,
              "phos4_rel": 0.0,
              "phos5_rel": 0.0,
              "phos6_rel": 0.0,
              "phos7_rel": 0.0,
              "phos8_rel": 0.851626189
            },
            "n_rows": 1,
            "n_time_points": 1
          },
          {
            "cell": {
              "phos1_rel": 0.190472606,
              "phos2_rel": 0.398928055,
              "phos3_rel": 0.624281335,
              "phos4_rel": 0.82711232,
              "phos5_rel": 0.855458644,
              "phos6_rel": 0.641781932,
              "phos7_rel": 0.194516845,
              "phos8_rel": 0.0
            },
            "n_rows": 1,
            "n_time_points": 1
          },
          {
            "cell": {
              "phos1_rel": 0.897469038,
              "phos2_rel": 0.897676748,
              "phos3_rel": 0.779681099,
              "phos4_rel": 0.594147075,
              "phos5_rel": 0.352327675,
              "phos6_rel": 0.158350845,
              "phos7_rel": 0.0,
              "phos8_rel": 0.0
            },
            "n_rows": 1,
            "n_time_points": 1
          }
        ],
        "absent_cells": null,
        "why_not_enumerated": "the full factorial is 2916 cells, over the 200 this payload enumerates; the counts above still hold"
      }
    }
  },
  "how_to_read_this": "Computed from the raw files by the engine \u2014 no model, no agent, no measurement values. `role` is a GUESS from column name and cardinality; correct it if it is wrong, and say so in your reply. `factorial.absent_cells` names the design combinations that are NOT in the file: the preview you are also shown is the first 25 rows only, and a missing cell is usually not visible there."
}
```

# Output contract
{
  "mappings": [{"file": "...", "observable_label": "...", "observable_column": null, "time_column": "...",
                 "value_column": "...", "condition_columns": ["..."], "condition_label_template": "dose={dose}",
                 "replicate_column": null, "error_column": null, "units": "arbitrary",
                 "error_type": "sd|sem|replicates|none|column"}],
  "observable_labels": [{"label": "...", "description": "...", "units": "...", "error_type": "...", "n": null}],
  "flags": ["anything suspicious — flag, never silently exclude"],
  "notes": "...",
  "processing": [{"kind": "subtract_reference", "labels": ["..."], "reference": {"condition_label": "..."},
                  "rationale": "quote the note or name the file feature (a blank row, a reference column)"}],
  "below_detection": [{"observable_label": "...", "threshold": 6.3, "rule": "imputed|dropped|left_as_is",
                       "note": "what the source says it did with values below its detection floor"}]
}
NOTE on LONG-FORMAT files: when one column NAMES the measured
quantity (e.g. `readout` = pStat1 / pStat3 / pStat5) and one column holds the
values, set `observable_column` to that naming column and leave `observable_label`
null; every row is assigned to the label written in that column, and every such
label must appear in `observable_labels`. The observable is NOT a condition:
never put the naming column into `condition_columns`.
NOTE on "error_column": when the file carries a per-row measurement error
on the value's own scale (a sigma, an SE of the summary statistic), name that
column here and set `error_type: "column"` for the labels it covers. The engine
carries it into the estimation problem as a FIXED per-row sigma; the observation
agent's noise formula is then not used for those observables.
NOTE on "below_detection" (OPTIONAL): DECLARE, never fix. When the source
states a detection floor (array background, assay LOD, sites undetectable at
t = 0) say per observable what the SOURCE did with values below it — `imputed`
(a floor or a fill value written into the table), `dropped` (rows absent), or
`left_as_is` (raw values kept). `threshold` is the floor on the measurement's own
scale, or null when the source gives no number. The engine records it, counts
the rows it touches, tells the observation-model agent, and the report states
that the comparison is conditional on the source's handling — no censored
likelihood is fitted. Declaring it is what keeps the limitation visible; a run
that swallows an imputed floor silently makes every candidate look cleaner than
the data justifies.
NOTE on "processing" (OPTIONAL): the ENGINE executes these, in order, on
the extracted table before any check and before any model exists; you compute
nothing. A CLOSED vocabulary of three operations, each a pure function of the
rows in the same cell (condition, time, replicate) or of ONE declared reference:
  normalize_by_group_sum {labels}
        divide each value in `labels` by their sum in the same cell (row
        normalisation); the divisor is kept per cell and shown in the report.
  subtract_reference {labels, reference: {observable_label | condition_label | time}}
        blank / background subtraction against a named reference row set: the
        same cell's other observable, a reference CONDITION (a blank lane, an
        unstimulated well), or a reference TIME (values relative to t = 0).
  scale_units {labels, factor, from_units, to_units}
        multiply by a declared constant; the label's units become `to_units`.
The holdout rule is engine-checked: a reference condition that is HELD OUT is
refused by name and comes back to you. NOT operations here, by rule: dropping
or clipping rows (a human decides exclusions), log or any transformation (the
observation model owns that), anything read from a fit. Declare processing only
when the note states the data WERE processed that way or a blank / reference
exists in the files — where the same assumption can be written model-side (a
per-timepoint or per-condition scale factor), the observation model will do
that instead.
Respond with ONLY a single JSON object matching the contract. No prose, no markdown fences.
````

## The reply

````json
{
 "mappings": [
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos0_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos0_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos1_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos1_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos2_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos2_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos3_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos3_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos4_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos4_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos5_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos5_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos6_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos6_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos7_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos7_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  },
  {
   "file": "ctd_ms_timecourse.csv",
   "observable_label": "CTD_phos8_rel",
   "observable_column": null,
   "time_column": "time_min",
   "value_column": "phos8_rel",
   "condition_columns": [],
   "condition_label_template": "invitro_PTEFb_CTD8",
   "replicate_column": null,
   "error_column": null,
   "units": "arbitrary",
   "error_type": "none"
  }
 ],
 "observable_labels": [
  {
   "label": "CTD_phos0_rel",
   "description": "Relative MS signal of the intact 8-heptarepeat CTD construct carrying 0 phosphates (no repeat modified). Relative intensity on a per-injection arbitrary scale; not comparable across time points without a per-time-point scale factor.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos1_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 1 phosphate (1 of 8 repeats modified, any position; position not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos2_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 2 phosphates (2 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos3_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 3 phosphates (3 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos4_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 4 phosphates (4 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos5_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 5 phosphates (5 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos6_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 6 phosphates (6 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos7_rel",
   "description": "Relative MS signal of CTD molecules carrying exactly 7 phosphates (7 of 8 repeats modified, positions not resolved). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  },
  {
   "label": "CTD_phos8_rel",
   "description": "Relative MS signal of fully phosphorylated CTD molecules (all 8 repeats modified; Ser2/Ser5 mutually exclusive per repeat, so 8 is the maximum). Per-injection arbitrary scale.",
   "units": "arbitrary",
   "error_type": "none",
   "n": 1
  }
 ],
 "flags": [
  "design_summary role guess is WRONG and is corrected here: phos1_rel..phos8_rel are measurement columns (relative MS intensities for 1..8 phosphates), not design factors; their 'levels' are measured values, and the 2916-cell 'factorial' is meaningless. The file has NO condition columns: one in vitro condition (8-repeat CTD 100 uM, P-TEFb catalytic, ATP 3 mM) sampled at 4 times. All 9 phosN_rel columns are mapped as separate observables of that single condition; condition_columns is empty and the label template is a fixed string.",
  "ctd_ms_timecourse.csv, all columns phos0_rel..phos8_rel, all 4 rows: intensities are on a per-injection arbitrary scale that differs between time points (row sums 1.00 at 0 min, 4.07 at 60 min, 3.79 at 120 min, 0.85 at 960 min, matching the lab note) while total substrate is conserved. Values are NOT commensurable across time points as they stand. No processing was declared: the note does not say the data were normalised, and the note's own observation model (a per-time-point factor mapping amounts onto intensities, which also scales the noise SD) belongs model-side. Do not pool or compare raw values across rows.",
  "ctd_ms_timecourse.csv: 19 of 36 measured values are exactly 0.0 (row time_min=0: phos1_rel..phos8_rel; row 60: phos7_rel, phos8_rel; row 120: phos8_rel; row 960: phos0_rel..phos7_rel). The note states additive Gaussian noise of a single SD at every peak, under which a measured empty peak would scatter around zero (including small negatives), not sit at exactly 0.0. These exact zeros look like not-detected or absent peaks written as zero, or idealised values, but the source states no detection floor and no handling rule, so no below_detection entry is declared. Left as is and NOT excluded; the observation model should know that roughly half the likelihood terms are exact zeros of uncertain provenance.",
  "No replicates (n = 1 per species per time point, stated in the note) and no error column. error_type recorded as 'none' because the file carries no error estimate. The note describes the noise model (additive, normal, one SD for the whole experiment shared by all peaks, scaled per time point by the same factor that maps amounts onto intensities); that SD is not given and must be estimated by the observation model. This is not an SD/SEM call: no error bars exist.",
  "Information content is thin for mechanism discrimination. Of 4 time points, t = 0 carries only the initial condition (all substrate unmodified; phos0_rel = 0.99957). t = 960 min carries only completion (only phos8_rel nonzero). Effectively only the 60 and 120 min distributions carry shape information about rates, each losing one degree of freedom to its own scale factor. The readout is phosphate COUNT only (9 mass peaks); which repeats are modified is not observed, so position-dependent (neighbour) effects can only enter through their imprint on count distributions.",
  "time_min = 960 is a sampled time (16 h), not a declared steady-state measurement, and is mapped as 960, not inf. It appears to be at or near completion (all signal in phos8_rel), but treating it as steady state would be a modelling decision, not an extraction edit.",
  "Time units are minutes, consistent with the intent's horizon (960 min). No conversion was made."
 ],
 "notes": "Wide-format file, 4 rows in and 4 rows out, with 9 observables per row: phosN_rel = relative MS intensity of the intact 8-heptarepeat CTD construct carrying N phosphates (N = 0..8). Count only, position not resolved; per the note, Ser2/Ser5 are mutually exclusive within a repeat, so each repeat is one bit and N <= 8. The time column is time_min (minutes: 0, 60, 120, 960). There is one experimental condition, so there are no condition columns, and the fixed label 'invitro_PTEFb_CTD8' is used for every mapping. All units are 'arbitrary': these are per-injection relative intensities, not concentrations. No processing was declared. The note says the scale drifts between injections and must be handled by a per-time-point mapping from amounts to intensities, which also scales the noise SD; that belongs to the observation model, not to a row normalisation here. Row-normalising would also put the noisy sum into the divisor. For the observation model, the note's stated structure is: measured_i(t) = s_t * (amount_i(t) + eps_i,t), eps ~ N(0, sigma) with a single sigma for all peaks and times, and s_t one scale factor per time point. Total substrate is conserved at 100 uM, which links the 9 amounts at each time point. Context for downstream (not an extraction edit): ATP 3 mM exceeds the 0.8 mM needed to fully phosphorylate 100 uM x 8 repeats, so ATP depletion is at most about 27%. Exact-zero entries are flagged and kept as is. No rows were excluded, reordered or edited."
}
````
