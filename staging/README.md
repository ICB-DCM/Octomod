# staging/

Your problems, one folder each, before they become runs. Nothing in here is
committed except this file.

Put your measurements in `staging/<project>/data/`, with `<project>` named after
your problem, and run `claude` in the repository root. Claude reads nothing
outside the repository folder (a setting in `.claude/settings.json`), so the
files have to be here before you start.

Claude writes the rest of the folder with you:

```
staging/<project>/
  data/            your measurements (CSV or TSV), never edited
  description.md   the experiment, written as a lab note
  intent.yaml      the question, the system, what counts as success
  testcase.yaml    the time horizon and the conditions held out
  supplied/        optional: a model or a PEtab problem you already have
```

A run copies what it reads from here into its record, `runs/<id>.h5`, before
its first module. Editing a folder after its run started changes nothing in
that run; a changed problem is a new folder and a new run. The full layout is
in `CLAUDE.md`, under "Staging a user's problem".
