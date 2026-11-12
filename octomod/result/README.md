# The run record

A run is one HDF5 file, `runs/<id>.h5`: every input, model, check, agent call, answer, and ledger
row of the run. There is no run folder. Beside the file are its checkpoint copy,
`runs/<id>.h5.bak`, and the rendered reports in `runs/<id>_reports/`; at the end of a run the engine
also adds its fitted models to `tried_models.json`, in the staging folder or in
`runs/_projects/<project>/`. This folder holds the code that writes, validates, and reads the
record.

- **Writing.** A place in the record is named by its record key, such as
  `rounds/round_0/candidates/<id>/petab/measurements`. Module engines write through `Node`
  (`node.py`); `RunStore` (`runstore.py`) is the only class that opens the file, one group per write.
  An artifact written through `write_record` (`write.py`) is first validated against its record
  class, and a payload that does not fit stops the module, naming the field.
- **The schema.** The record classes are pydantic models: `RunResult`, `RoundRecord`, and
  `CandidateRecord` in `model.py`, one class per kind of artifact in `slots.py`, and the leaf
  records in `records.py`. Each field has a tier: `core`, `bulk` (arrays, tables, traces), or `audit`
  (prompts, raw replies, the ledger). `tools/make_result_schema.py` writes
  [`docs/RESULT-SCHEMA.md`](../../docs/RESULT-SCHEMA.md) and `docs/result_schema.json`, the JSON
  Schema a reader can validate a record against, from these classes.
- **Checkpoints.** At every marker, recorded decision, pause, and run end, the record is checked for
  completeness and copied to `runs/<id>.h5.bak` (`autocommit.py`). A damaged file is replaced by
  that copy, so a killed run resumes from its last marker.

## Getting things out

| command | what it does |
|---|---|
| `./run.sh status --run-id <id>` | rounds, candidates, markers, decisions, outcome, the end of the ledger |
| `./run.sh inspect --run-id <id>` | where the run went wrong, in order |
| `./run.sh show --run-id <id> [<key>] [--full]` | prints one part, by record key; without a key, the top level |
| `./run.sh explore --run-id <id>` | a shell to look around: `ls`, `cd`, `cat`, `find`, `gates`, `decisions`, `failures`, `ledger`, `status`, `report`, and `export <key> <file>`, which writes one part to a file |
| `./run.sh export --run-id <id> --out <file>` | a copy of the record as another HDF5 file, for sharing, optionally with fewer tiers or rounds |

`export` never writes SBML or PEtab files, and no command writes a whole PEtab problem. A model
comes out one part at a time, with `./run.sh show --run-id <id> <key> --full > <file>` and the keys
under Reference.

## Reference

<details>
<summary>The commands' options, where a model is, completeness, adding a field</summary>

- `show` prints a group as YAML, or the list of its children if it has any (all of it with
  `--full`), a table as TSV, and a text as itself; long values are shortened unless `--full`.
  `show` and `explore` take `--file <record.h5>` instead of `--run-id`, for a record anywhere.
- `export --tiers core,bulk` keeps the named tiers (`core` always; all three by default), and
  `--rounds 0,2` keeps those rounds in full and of the others only their index, shape, selection,
  decisions, revision, and expansion. Each record that lost a field lists it in `elided`. Such a
  copy needs `--out`; without `--out`, and with nothing left out, `export` prints the path of the
  run's own record and writes nothing.
- A model (`sbml`, `antimony`, `parameters`): a model candidate's at
  `rounds/round_<k>/candidates/<candidate>/model/`; the base the `expansion` agent's candidates
  differ from at `rounds/round_<k>/base_model/`; otherwise the round's model at
  `rounds/round_<k>/model/` (a run with one model, or the base of a round seeded from the one
  before). Its PEtab problem: `rounds/round_<k>/candidates/<candidate>/petab/`,
  with `_single` as the candidate in a run with one model (`observables`, `conditions`,
  `measurements`, `parameters`, `holdout_measurements`, `problem_yaml`).
- Loading the whole record (`RunStore.load`) validates it; a malformed entry is left out and named
  on the terminal. `derive.py` then fills in what no module writes, such as an agent call's cost.
- `completeness.py` checks at each checkpoint that a reader can still see what happened: after `s1`
  the SBML and its parameters, after `s3` the PEtab tables, after `s6` the fit, after `s7` the
  evaluation and the report, and for every agent call its prompt and reply. A gap is written into
  the record under `completeness/` and does not stop the run: cards show it as RECORD INCOMPLETE,
  and `./run.sh status` and `ANALYSIS.html` list it. The test battery fails a suite whose records
  carry one.

### To add a record field

1. Declare it on the class of its artifact, in `model.py`, `slots.py`, or `records.py`:
   `Field(default=None, description="…")`, or `tier("bulk", default=None, description="…")`
   outside the `core` tier.
2. Write it from the module engine, through `write_record` (`write.py`) when its artifact has a
   class. Every class keeps keys it does not declare, so a value under an undeclared name is stored
   without a check and without an error.
3. Regenerate the schema documents with `uv run python tools/make_result_schema.py`;
   `tests/result_schema_unit.py` fails until they match the classes.
4. If a reader needs it once a module has passed, add it to that marker's check in `MODULE_CHECKS`
   (`completeness.py`).

</details>

## Files

| file | what it is |
|---|---|
| `access.py` | The record as the readers' source. |
| `agent_replies.py` | One record per agent role: the reply an agent must return, as a class. |
| `autocommit.py` | Checkpoint the run record where the process may end. |
| `completeness.py` | Is the record complete enough to say what the run did? |
| `derive.py` | What a reader of the record needs that no module writes on its own. |
| `explorer.py` | Explore a run record interactively, or print one part of it. |
| `importer.py` | LEGACY: transcribe a run DIRECTORY into a run record. |
| `model.py` | The root of the result object: RunResult → RoundRecord → CandidateRecord. |
| `node.py` | A location in the run record, addressed by its record key. |
| `records.py` | Leaf records and the conventions every record follows. |
| `runstore.py` | The run IS the file: `runs/<id>.h5`, written and read one group at a time. |
| `slots.py` | One record per artifact slot, in the vocabulary of `round_status.SLOTS`. |
| `store.py` | Whole-record forms: export copies pruned by tier, and the schema. |
| `write.py` | Write an artifact through its record: validate, then write. |
