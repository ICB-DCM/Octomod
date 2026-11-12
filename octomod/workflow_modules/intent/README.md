# Intent

At the start of a run, before any model is built, the intent is checked and frozen; this is a step
of the run, not one of the eight workflow modules. The intent states your question, the system, what
the model must contain and predict, and how success is judged. It is written in the staging folder,
where a project is prepared before a run. The engine in this folder checks it, shows it beside the
knowledge file, which holds what the knowledge module found, and asks you to freeze it. Every later
check, the interpretation and the verdict are scored against the frozen intent.

## What happens

1. The central engine refuses to start if the knowledge file or your evidence floor is missing, or if
   required reactions changed since. The floor is the lowest grade of evidence a reaction needs;
   below it a reaction is flagged, and in strict mode kept out of the base model. Benchmark and test
   cases may skip both.
2. The engine checks that every required entry of the intent is filled in. The inference
   target, what the run is for, must be one of 3 kinds.
3. Each required reaction must read as an equation, and each named domain pack must exist. Your
   papers must be well formed and from no excluded source, and, when a latest publication year is
   set, not published after it.
4. When the raw data files can be read without ambiguity, it describes their curves in words. The
   held-out conditions, kept from fitting to test the models, are left out.
5. It shows you the intent beside the knowledge file's findings, and you decide whether to freeze it.
   A frozen intent starts round 0 at M1; a round is one pass from model building to revision.

A failed check stops the run before you are asked, with a message naming the entry to fix in
`intent.yaml`. Nothing has been spent at that point.

## Agents

No agent: this step is deterministic.

## Where it asks you

- **Freeze this intent?** Everything after it is scored against it. The card shows the intent and
  your papers. With a knowledge file it adds the reactions with their grades, the floor and who set
  it, the facts, and the intent's changes since. You can freeze it, and the run starts. Or you
  can stop, edit the intent in the staging folder and start a new run. If the required reactions
  changed, run the knowledge module again first.

## What it writes

The frozen intent goes into the run record, `runs/<id>.h5`, with your papers frozen beside it but
kept apart. Only the agents allowed to see the papers receive them. Section 2 of each round report,
`runs/<id>_reports/round_k/report/report.html`, shows the frozen intent.

## Reference

<details>
<summary>Exact checks and answer forms</summary>

### Checks, in full

Every check here stops the run before the question is asked, with a message that names the entry
to fix in `intent.yaml`. Nothing has been spent at that point.

- The required entries are present and not empty: question, system, required entities, required
  predictions, timescale, inference target, domain packs, success criteria.
- The inference target is `prediction`, `parameter_values` or `mechanism_discrimination`.
- Each required reaction is an equation the engine can read: `A -> B`, or an entry with
  `equation`, `note` and `modifiers`.
- The intent fits the run record's schema for the intent.
- Each domain pack named resolves to a pack in `knowledge/packs/`.
- Each of your papers has the declared shape, names no source on the blocklist, and lies inside
  the literature horizon when `testcase.yaml` declares one.
- A benchmark case that supplies literature also declares its horizon and says in its `truth/`
  folder that the literature is staged on purpose.

The central engine refuses the run even earlier, at start, when the knowledge file or the floor
decision is missing, when the required reactions moved since the knowledge module ran, or when an
online knowledge module has no horizon (see [M0](../knowledge/README.md)).

### Interaction points, with the answer forms

- **Intent freeze**: "Freeze this intent? Everything downstream is scored against it." The
  interaction request shows the question, the system, the inference target, the required
  predictions and reactions, the success criteria, the domain packs and your papers.
- With a knowledge file it adds the required and essential reactions with grade, source and
  origin, the evidence floor and who set it, the facts per agent, and each key of the intent that
  changed since the knowledge module saw it.
- A last line says how many sentences describe the curves in the raw data files, or why none do,
  which held-out conditions they leave out, and the command that prints them.
- `y` freezes the intent, and the run enters round 0 at M1.
- `n` stops the run. Edit the intent in the staging folder and start a new run; when the required
  reactions changed, run the knowledge module again first.

### What it writes, with the record keys

`intent` holds the frozen intent without your papers. `supplied_literature` holds the papers as
typed claims, frozen beside it and kept apart, so that only the agents allowed to see them do.
`phenomenology_raw` holds the curves in words read from the raw data files, when the files can be
read without ambiguity. Your answer is in the ledger; `./run.sh show --run-id <id> intent` prints
the frozen intent.

</details>

## Files

| file | what it is |
|---|---|
| `engine.py` | Freeze the intent. |
