# Orchestration

The central engine is deterministic code that runs the workflow modules of a run in order, round
after round. It calls each module engine and, between rounds, the `revision` agent. It waits at every
interaction point for your answer and writes the run-level parts of the run record, `runs/<id>.h5`.
No agent writes the record.

## A run, step by step

1. You prepare the project with the orchestrating agent and run the knowledge module with
   `./run.sh knowledge`. It suggests an evidence floor: the lowest grade of evidence a reaction
   needs; below it a reaction is flagged, and in strict mode kept out of the base model.
2. Unless the project skips the knowledge module, a run is refused without its knowledge file and
   your floor, or after required reactions changed. The run reads only its own copy of the folder.
3. You freeze the intent. M1 builds the base model, M2 the model candidates; you decide what to fit.
4. M3 extracts the data, once per run. M4 builds one PEtab problem per candidate; you approve the
   compile.
5. For each model candidate, M5 compiles and probes it, you approve the budget, and M6 fits it.
6. M7 evaluates the fits and you give the verdict. Revision proposes the next round; a yes starts it.
   At the end the central engine writes `runs/<id>_reports/ANALYSIS.html`.

## Rounds

A round runs the modules and ends in a verdict; round 0 starts at M1. With several model candidates,
the next round starts at M2 from the chosen base model, with its data, assembly and fit. Only the
new candidates are fitted. With one model, a move to the reactions or rate laws sends the next round
back to M1. Any other move edits the assembly or the parameters. Rounds have no cap while a person
answers; declining the verdict or the revision ends the run. A run nobody answers stops after 3
rounds; `--max-rounds <n>` lowers that.

## Interaction points

The code calls an interaction point a gate. With `--gate-mode file` the run writes the question, the
evidence, what each answer leads to and the answer forms, then pauses. `./run.sh pending` prints it,
and the run command again with `--gate-answer` and `--gate-note` answers it. You answer through the
orchestrating agent, which is instructed never to answer a question itself. Standing instructions
are a declared policy, set with `--policy`. `strict`, the default, answers nothing; `copilot`
answers cost questions within its caps; `benchmark` answers from a file.

## Redrafts and retries

- A reply in the wrong format goes back with the error quoted; a third failure stops the run.
- A reply that fails a check goes back to its agent with the reason, as a redraft, up to 3 attempts.
  Then you are asked for more attempts, a lower floor (at M1, with a knowledge file), or a stop.
- A redraft you ask for at a card carries your words and the agent's previous reply, and spends no
  attempt. A prompt already answered in the round is read from the record, not paid again.

## Stopping, resuming, re-entering

Each module leaves a marker when its checks pass, and the record is saved at every marker, answer
and pause. `--run-id <id>` alone resumes a paused or crashed run, unless its settings or inputs
changed. An ended run is refused under its id: take a new `--run-id`, delete it with `--overwrite`,
or re-enter its latest round with `--from-module`. Wrong inputs need a new run with `--testcase`.

## Reference

<details>
<summary>Exact interaction point ids, thresholds, exit codes and answer forms</summary>

### A run, step by step, with the interaction point ids

1. Staging, then the knowledge module (M0, `./run.sh knowledge`); unless the settings skip M0, the
   run is refused without its knowledge file or your floor decision, or if required reactions moved.
2. The staged folder is copied into the record's `input` group; the run reads only that copy.
3. Intent freeze: the intent's checks, then the interaction point `intent`.
4. M1 model building: the base model (and `model_base_scope` when enabled in the settings).
5. M2 model expansion: the model candidates, then `model_scope`.
6. M3 data: the measurement table; its agent runs once per run.
7. M4 PEtab assembly: one PEtab problem per model candidate, then `assembly_cost_boundary`.
8. M5 compile and cost probe, per model candidate, then `cost_boundary_estimation`.
9. M6 estimation, per model candidate after its M5; `estimation_convergence` if a check fails.
10. M7 evaluation and interpretation, then `evaluation_verdict`.
11. Revision, then `revision` (with one model, `revision_proposal`): a yes starts the next round;
    at the end of the run the central engine writes `runs/<id>_reports/ANALYSIS.html`.

### Rounds, in full

A round runs the modules and ends in a verdict; rounds count from 0 (`rounds/round_k`), and round 0
starts at M1. With several model candidates (the target `mechanism_discrimination`, or expansions
bought at `model_scope`) the `revision` agent proposes, and the next round starts at M2, seeded from
the chosen base model as it is, with its data, assembly and fit (`round_seed.py`); only the new
model candidates are fitted. With one model the `revision_proposal` agent proposes one move: a move
to the reactions or rate laws sends the next round to construction (M1) with a directive, any other
carries the model and edits the assembly or the parameters. Rounds have no cap while a person
answers the verdict and the revision approval; declining one ends the run. A run nobody answers
(`--auto-approve`, or a policy that buys rounds) stops after 3 rounds; `--max-rounds <n>` lowers it.

### Interaction points, with the answer forms

The code calls an interaction point a gate (`interaction/humangate.py`). The module engine writes an
interaction request: the question, the evidence, the consequence of `y` and of `n`, the answer forms
it reads from a note, and the documents behind it; questions the engine raises (an agent proposal
refused because it would change what the data mean) ride on the next card, numbered. With
`--gate-mode file` the run writes it to `pending_gate` and exits with 3; `./run.sh pending` prints
it, and the run command again with `--gate-answer y|n --gate-note "..."` answers that gate only.

You answer through the orchestrating agent, which relays the card and your words and is instructed
never to answer a gate itself. Standing instructions are a declared policy, hashed into the run:
`--policy strict|copilot|benchmark|<file>` (`workflows/policies/`). `strict`, the default, answers
nothing; `copilot` answers the cost gates (compile, budget, profiling, redraft budgets) within its
caps and pauses at judgement gates; `benchmark` answers from the file and stops at a gate it does
not cover. `--auto-approve` (tests) answers yes everywhere and is refused with `--policy`.

Every answer is a `human_gate` ledger row saying how it was given (terminal, file, policy with its
sha, auto); a gate whose answer must survive a resume also writes `rounds/round_k/decisions/<gate>`
with the note and who signed (a policy signs as `policy(<sha>)`). A note form counts only where
written as one (`key: value`, `n=…`, a bare word on its own line or between commas), and most
cards print what they read from the note and what they ignored.

### Redrafts and retries, in full

- A reply that breaks its output contract goes back with the error quoted; a third failure stops the run.
- A reply that fails a blocking check goes back to its agent as a redraft with the output attempt
  history (every earlier attempt and the checks it failed), 3 attempts in all; then the failure
  point `<module>_redraft_budget` asks you for more attempts (`n=<N>`), a floor (M1, with a
  knowledge file), or a stop.
- `redraft: <words>` at a card sends the work back with your words and the agent's previous reply;
  it spends no attempt, and the card is asked again.
- The engine sends work back in its own name: a failed data or assembly check to the agent that
  wrote the value, a compile or fit failure naming the observation model to the observation agent
  (once per round), dropped revisions to the `revision` agent (1 repair).
- A prompt identical to one already answered in the round is read from the record, not paid again.

### Stopping, resuming, re-entering, with the exit codes

Each module writes a marker when its checks pass, the next refuses to start without it, and the
record is checkpointed at every marker, answer and pause. Exit codes: 0 finished, 3 paused, 1
stopped (failed check, declined card, unmet held-out test, refused run id), 2 refused at start.

- `--run-id <id>` alone resumes a paused, crashed or killed run from its record and markers, with
  the backend it started with; after a refused note, it asks that gate again.
- A paused run whose settings or inputs changed since it started is refused, naming what moved.
- An ended run is refused under its id: take a new `--run-id`, delete it with `--overwrite`, or
  re-enter the latest round with `--from-module model|data|assembly|estimation|evaluation`: every
  upstream slot is checked and refused by name if missing or invalid, that module and all after it
  run afresh, and what they replace moves to the round's `superseded/`.
- Wrong inputs need a new run (`--testcase <edited folder>`); `--from-run <id>` reuses a run's inputs
  unchanged. `./run.sh status` shows each round's markers, `./run.sh inspect` where a run went wrong.

### Where the code is

The central engine (`orchestrator.py`) is deterministic code that runs the workflow modules of a run
in order, round after round. It calls each module engine and, between rounds, the `revision` agent,
waits at every interaction point for an answer, and writes the run-level parts of the run record,
`runs/<id>.h5`; no agent writes the record. `interaction/` holds the interaction points and redrafts.

</details>

## Files

| file | what it is |
|---|---|
| `artifacts.py` | Artifact validation, and reading the files a testcase supplies. |
| `ledger.py` | Append-only run ledger. |
| `orchestrator.py` | The orchestrator — code, not an agent. |
| `provenance.py` | Which code and numerics stack produced a run's numbers. |
| `reuse.py` | Reuse instead of recompute: fingerprints for the expensive products of a run. |
| `round_seed.py` | A round starts from exactly the model it was seeded from. |
| `round_status.py` | Round status — the slot contract, computed, never indexed twice. |
| `rounds.py` | How many rounds a run may take, and how that is said on a card or record. |
| `run_context.py` | Module runners. |
| `run_folder.py` | The run record carries its own inputs: the `input/` group of `runs/<id>.h5`. |
| `run_guard.py` | Run-id safety: an existing run is never silently reused. |
| `timing.py` | Where the wall clock went: every second of a run, attributed. |
| `interaction/` | 8 files; see its README |
