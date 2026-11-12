# M0 · Knowledge

M0 gathers what is known about your system before the intent is frozen. It lists the species, the
essential reactions a base model needs, the facts a model would otherwise invent, and their sources.
The module engine grades all of it and writes the knowledge file, on which M1 and M2 build. It also
suggests an evidence floor: the lowest grade of evidence a reaction needs; below it a reaction is
flagged, and in strict mode kept out of the base model.
M0 runs outside any run, on the staging folder where the project is prepared:

```
./run.sh knowledge --testcase staging/<project> --mode online|offline --backend llm
```

As shown it calls the language model; by default it replays canned replies stored in the folder.

## What happens

1. Before any call, the module engine checks the folder, the mode and the form of your inputs.
   Online mode needs a literature horizon: the latest publication year a source may have.
2. The `knowledge` agent surveys the species, the reactions, marked essential or not, and the facts
   with the agents they are for. It classifies every source but grades nothing.
3. The module engine checks the reply and drops, unread, sources you excluded or past the horizon.
4. Online, it caches every cited document and flags a quote missing from its text. The
   `knowledge_verification` agent then reclassifies each counted source; the weaker reading counts.
5. It grades each reaction and fact from high to none; offline, every grade is "not applicable". It
   suggests as floor the lowest band among supported essential reactions you did not require.
6. You choose the floor on the card; the mode is set in `testcase.yaml`. In strict mode a reaction
   below the floor cannot be added; in advisory mode, the default, it may be added but is flagged.

A failing reply goes back to the agent, up to 3 attempts; then M0 stops and writes no knowledge file.

## Agents

| agent | what it does here |
|---|---|
| `knowledge` | surveys the species, reactions and facts with their sources; online it may search the web; grades nothing |
| `knowledge_verification` | online only: rereads each counted source in its cached text and classifies it again; advisory |
| `knowledge` (targeted) | inside a run, in strict mode: M1 and M2 call it to search for a reaction a draft lacks |

What each agent is shown is listed in [`docs/ROUTING.md`](../../../docs/ROUTING.md). What it must
return is in its file under [`skills/`](../../../skills/).

## Where it asks you

- **Which evidence floor should the models use?** The card lists the essential reactions, the
  suggested floor and its trade-off, and the facts. You can set or remove the floor, and say by how
  many bands each revision round lowers it. You can keep an unsupported essential reaction in the
  base, marked as inferred, or drop it as a candidate for an expansion. Required reactions are
  exempt. The orchestrating agent, not the module, writes your answer into `testcase.yaml`.

## What it writes

M0 writes the knowledge file, `knowledge/knowledge.json`, the cached sources and every call into the
staging folder. A new run of M0 replaces them, and each run of the workflow copies the file and your
floor into its record. Only facts tagged for construction reach an agent; the others are on the card.

## Reference

<details>
<summary>Exact inputs and outputs of the agents, the checks with their ids, and the answer forms</summary>

### Agents: what each receives and returns

| agent | receives | returns |
|---|---|---|
| `knowledge` | the intent (without your papers), the project description, the required reactions with their ids, your papers as claims, and the restrictions (the literature horizon, the excluded sources, never fabricate a source, no evidence is an acceptable answer); online it may search the web, offline it has no tools | `system` (summary, scope, unknowns), `species` with their identifiers, `reactions` marked essential or not, `facts` with their kind and the agents they are for, `queries_run`, `notes`; every source classified by kind, context and stance; it grades nothing |
| `knowledge_verification` | online only: each source the grade counts (id, source, locator, what it supports, the quote, the first classification) and the cached text around the quote; no intent, no project description, no data | `classifications`, one per source, with a note on what in the text decides it; advisory |

Inside a run, in strict mode, M1 and M2 call `knowledge` again in targeted mode (see
[M1, M2](../model/README.md)).

### Checks, in full

- **Before the call** (refused, exit 2, nothing spent): the folder lies outside `runs/` and holds
  an intent; a mode is named; online needs the horizon (`research.max_publication_year` in
  `testcase.yaml`); the required reactions and your papers have a readable shape.
- **On the reply** (blocking): every equation parses, in species ids that `species` lists; every
  required reaction has its own entry; every source on an essential reaction is classified in the
  vocabulary; every source names a DOI, PMID, URL, database identifier or a paper's `lit_k`;
  identifiers have the declared shape; every fact has a kind, a statement, its evidence (or
  `evidence: []`) and its agents; a survey has a `system` summary and a `facts` list. A failing
  reply is asked again with the failures, 3 attempts in all; then the module stops (exit 1) and
  writes no knowledge file.
- **The fence**: a source on the blocklist or after the horizon is dropped before anyone reads it.
- **The audit** (advisory): online, every cited document is cached and every DOI, PMID and URL
  looked up; a quote not found in its cached text is flagged; where PubMed or a database
  identifier settles a source's kind, that kind is used.
- **The grade**: each reaction and fact gets a band (high, medium, low, weak, none) from the rule
  table `grounding.grading` in `workflows/default.yaml`; offline every band is not applicable. A
  source cited twice counts once, a contradicting source marks the entry contested and caps it at
  medium, and where the verifier disagrees the weaker reading grades.
- **The suggested floor**: the lowest band among the supported essential reactions that are not
  required. Required reactions are exempt from the floor.
- **At run start** (refused by the central engine, exit 2): no knowledge file, no usable floor
  decision, required reactions that moved since the module ran, or an online module without a
  horizon.

### Interaction points, with the answer forms

- **Evidence floor**: the floor card ends the command, and `--show` prints it again. It lists the
  essential reactions with grade, source, origin and flags; the essentials no source counts for;
  the suggested floor with its rule, the trade-off, and which essentials leave the base at each
  higher band; the facts per agent; the mode, calls and cost.
- Answers: `floor: <band|none>`, `step: <n>` (bands each revision round lowers it by),
  `keep: <id>, <id>` (an unsupported essential stays in the base, tagged inferred),
  `drop: <id>, <id>` (it leaves the base and becomes a candidate for an expansion). The
  orchestrating agent writes your answer into `testcase.yaml` under `grounding:`; the module never
  writes it. The mode, advisory (the default) or strict, is set there too, not on the card.

### What it writes, with the record keys

In the staging folder: `knowledge/knowledge.json` (the knowledge file), `knowledge/sources/`,
`knowledge/calls/` (each call's prompt, reply and meta), `knowledge/intent_before.yaml`, and one
line per call in `curation/STAGING_LOG.md`; a new run of the module replaces `knowledge/` whole.
A run snapshots the folder into `input`, copies the knowledge file to
`rounds/round_0/reaction_evidence` and writes your floor to `rounds/round_0/space/floor`. Of the
facts, only those tagged for construction reach an agent; the others are on the floor card.

</details>

## Files

| file | what it is |
|---|---|
| `engine.py` | The knowledge module: what is known about the system, gathered BEFORE the intent is frozen, and the refusals that make a run wait for it. |
| `reaction_evidence.py` | The literature behind each reaction a model of the system may contain, and the base construction builds from it. |
| `supplied_literature.py` | Literature the human already has: `intent.supplied_literature`. |
