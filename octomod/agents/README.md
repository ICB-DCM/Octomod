# Agents

An agent call asks a model through `claude -p`, without memory, or in tests reads a canned reply. A
module engine names a role, hands it a context, a dictionary of named inputs, and gets back one JSON
object in the role's reply format. The agent has no file or shell access and writes nothing: the
engine checks the reply and stores it in the run record. There are 13 roles; each module's README
says which ones it calls, what each is shown, and what each returns.

The call code is in `__init__.py`, which the Files table below leaves out: `ROLES`, the roles with
the keys each reply must carry and the reply format the prompt states; `build_prompt`;
`granted_tools`, the tools a call may use; and `call_agent`.

## A call, step by step

1. A module engine calls `RunContext.call` in
   [`../orchestration/run_context.py`](../orchestration/run_context.py), or `call_cached`, which
   reuses the reply to the same prompt if it was answered earlier in the round. Before a run, the
   knowledge module calls through `StagingSession.call` in its own engine.
2. The context's keys are checked against the routing table, `ROUTING` in `routing.py`. A key the
   role is not granted stops the run, naming the key. [`docs/ROUTING.md`](../../docs/ROUTING.md) is
   generated from this table.
3. The prompt is built from the role's template, [`skills/<role>.md`](../../skills/), a statement of
   the tools it has, the inputs, and the reply format.
4. A backend answers. `llm` (`llm_backend.py`) runs `claude -p` with the role's model and effort
   from `workflows/default.yaml` (`models`, `agents.effort`), from an empty temporary folder, and
   with no tools except `WebSearch` and `WebFetch` for `research` and for the knowledge module
   online. `stub` (`stub_backend.py`) returns the canned reply from the test case's `stubs/` folder
   at no cost; a new run uses it unless `--backend llm` is given.
5. The reply is checked against its format. The prompt and every reply go into the record at
   `rounds/round_<k>/agent_calls/<name>/`, the role's name unless the call has its own (such as
   `revision_proposal_2`), and an `agent_call` row with the model, the hash of the prompt, and the
   cost goes into the ledger. The knowledge module's calls before a run go to `knowledge/calls/` in
   the staging folder.

Each role's reply format is declared twice: in `ROLES`, as the required keys and the text the prompt
shows, and in [`../result/agent_replies.py`](../result/agent_replies.py), as a class that also checks
the type of each key; `tests/agent_replies_unit.py` fails when the two disagree on the required
keys. What a call can reach on the machine is in [`docs/PERMISSIONS.md`](../../docs/PERMISSIONS.md).

## When a reply fails

- A reply that is not one JSON object, lacks a required key, or has a key of the wrong type goes
  back to the same call with the error quoted, up to `retry.agent_json` (2) more times; then the run
  stops. A canned reply that does not fit stops the run at once.
- A call that times out is repeated only if `retry.agent_timeout` allows it, and a killed call is
  never repeated. `agents.timeout_s` sets the limit; by default there is none.
- A reply that fits its format but fails a check goes back to its agent as a redraft, with the
  checks it failed. Which agent, and when you are asked instead: [`../gates/`](../gates/README.md).

## Reference

<details>
<summary>To change what an agent is shown</summary>

1. Add the key to the role's `sees` list in `ROUTING` (`routing.py`).
2. Add it to the context where the role is called:

   | role | context built in `octomod/` |
   |---|---|
   | `knowledge`, `knowledge_verification` | `workflow_modules/knowledge/engine.py` |
   | `construction`, `research`, `expansion`, `construction_verification` | `workflow_modules/model/engine.py` (`_expansion_context` for `expansion`) |
   | `data_extraction` | `workflow_modules/data/engine.py` |
   | `observation`, `condition`, `assembly_verification` | `workflow_modules/assembly/engine.py` |
   | `interpretation` | `workflow_modules/evaluation/engine.py` |
   | `revision_proposal` | `workflow_modules/revision/engine.py` |
   | `revision` | `orchestration/orchestrator.py` |

3. Say what the input is in `skills/<role>.md`.
4. Regenerate the page with `uv run python tools/make_routing.py`; `tests/routing_unit.py` fails
   until `docs/ROUTING.md` matches the table.

To change what a role returns, change its entry in `ROLES` and its class in `agent_replies.py`.

</details>

## Files

| file | what it is |
|---|---|
| `agent_timing.py` | How long a live agent call usually takes, from this engine's own ledgers. |
| `llm_backend.py` | The live backend: one headless `claude -p` subprocess per typed hole. |
| `payload.py` | What an agent is allowed to see, and how many bytes of it. |
| `routing.py` | Which context keys each agent role is shown. |
| `stub_backend.py` | The stub backend: canned agent replies checked in beside a testcase. |
