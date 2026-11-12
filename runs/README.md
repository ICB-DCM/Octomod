# runs/

What the engine writes, one record per run. Nothing in here is committed
except this file.

```
runs/
  <id>.h5          the run: its inputs, every artifact, gate verdict,
                   decision and agent call, as one HDF5 record
  <id>.h5.bak      its checkpoint
  <id>_reports/    the rendered documents; start with ANALYSIS.html
  _projects/       what earlier runs of one problem already fitted
```

Only the engine writes here: never edit a file in this folder. Read a run with
`./run.sh status --run-id <id>`, `./run.sh show --run-id <id> <key>` or
`./run.sh explore --run-id <id>` rather than opening the record yourself. The
test battery writes to `test_runs/`, never here, so everything in this folder
is a run somebody asked for.
