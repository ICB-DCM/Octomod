---
name: results
description: Work with a run's single record file (runs/<id>.h5) — read a run's state, find where it went wrong, show one part of it, open the interactive explorer for the user, and make a smaller copy for a collaborator. Use this whenever someone asks to share results, wants to know what happened in a run, wants to look inside a run, or needs the run as one file.
---

# Results

Every run IS one file: `runs/<id>.h5`. The engine writes every artifact into
it as the run goes — model, data, PEtab tables, the multistart's arrays, every
gate verdict, every human decision, every agent prompt and reply, the ledger —
so it is current at every pause and at the end. Beside it sit only its
checkpoint (`runs/<id>.h5.bak`) and the rendered HTML (`runs/<id>_reports/`).
Its fields are listed in `docs/RESULT-SCHEMA.md`.
You never write this file yourself, and you
never open it with h5py — the CLI below is how it is read.

## What you can do with it

**Read a run's state** — instead of listing anything:

```
./run.sh status  --run-id <id>     # rounds, candidates, markers, decisions, outcome, ledger tail
./run.sh inspect --run-id <id>     # where things went wrong, in order
./run.sh pending --run-id <id>     # the gate a paused run is waiting at, as JSON
```

`inspect` lists every failed blocking gate, dropped candidate, agent redraft
and stopped outcome, each with the round and candidate it belongs to. Lead
with that list when someone asks "what happened?", then show the part it
names.

**Show one part** — by its record key (the `RunResult` tree,
`docs/RESULT-SCHEMA.md`); long strings and arrays are folded unless `--full`:

```
./run.sh show --run-id <id>                                              # the top level
./run.sh show --run-id <id> rounds/round_0/evaluation                    # the round's report
./run.sh show --run-id <id> rounds/round_0/decisions_md
./run.sh show --run-id <id> rounds/round_0/agent_calls/construction/prompt --full
./run.sh show --run-id <id> rounds/round_0/candidates/base/estimation    # a candidate's fit
```

Where things are: a round's model `rounds/round_k/model/{antimony,sbml,
mermaid,parameters,…}` (a candidate's own under `candidates/<id>/model`), its
data `…/data/measurements`, the fitted problem `…/candidates/<id>/petab/<table>`
(`_single` for a single-model round), the fit `…/candidates/<id>/estimation`,
gate verdicts `…/gates/<gate_id>`, decisions `…/decisions/<module>`, agent
calls `…/agent_calls/<role>/{prompt,reply}`; at the top `run`, `intent`,
`questions`, `outcome`. The ledger is `ledger` (`./run.sh status` prints its
tail).

**Let the person look around** — the interactive explorer is for THEM, not
for you; offer it when they want to browse rather than be told:

```
./run.sh explore --run-id <id>
```

Inside: `ls`, `cd`, `pwd`, `cat [--full] <key>`, `find <text>`, and the
reading verbs `gates [round]`, `decisions`, `failures`, `ledger [n] [event]`,
`status`, `report [round]` (renders the HTML on demand), `export <key>
<file>` (one part to a `.json`/`.yaml`/`.txt` file), `quit`. It navigates
record keys (`cd rounds/round_0/candidates`, `cd ..`).

**Make a copy for a collaborator** — smaller, still valid against the same
schema, honest about what it leaves out:

```
./run.sh export --run-id <id> --tiers core                 --out <path>.h5
./run.sh export --run-id <id> --tiers core,bulk --rounds 2 --out <path>.h5
```

- `--tiers core` keeps what a reader needs to understand the answer and drops
  the arrays, traces and tables (`bulk`) and the prompts, raw replies and
  ledger (`audit`). Every record that lost a field lists it in `elided`.
- `--rounds k` keeps round k in full and reduces every other round to its
  index, selection and decisions.
- `--out` is required for a pruned copy: the run's own record is never pruned
  in place.

Before sharing, say what tier the copy carries and what it does not: a
`core` copy has the winner, the fits' summaries and every decision, but no
start points and no prompts. If the collaborator needs to re-check an
optimum, they need `bulk`.

**Read it in Python** (a notebook, a scorer, a comparison across runs):

```python
from octomod.result import load
rr = load("runs/<id>.h5")
rr.round(0).candidates["base"].estimation.best_fval
rr.failures()

from octomod.result.runstore import RunStore
st = RunStore("runs/<id>.h5")
st.get("rounds/round_0/candidates/base/estimation")   # one group as a dict
st.ledger_rows()
```

The file is HDF5 through mkstd; the JSON Schema a reader can validate against
without this repository is `docs/result_schema.json`. Do not produce JSON or
YAML copies as a matter of course — HDF5 is the record; a text rendering is
for a specific purpose someone asked for (`explore`'s `export <key> <file>`
is that purpose).

**A run made before the record existed** is a directory `runs/<id>/`. Turn it into a
record with `./run.sh import-legacy --run-dir runs/<id>/`, then use the
commands above.

## What stays out of the file

Renderings: `report.html`, `model_report.html`, `ANALYSIS.html`, figures.
They live in `runs/<id>_reports/`; regenerate them with `./run.sh report
--run-id <id> [--round k] [--model] [--analysis]`. They are derived from the
record and are never a source.

## Rules that carry over from CLAUDE.md

- You never edit anything under `runs/`; `export --out` writes elsewhere.
- Costs and numbers you quote come from the record or the ledger, never from
  your own estimate.
- A shared copy is a scientific claim leaving the machine: state its tier,
  its outcome, and whether the run's verdict was signed by a human, a policy
  or `auto`.
