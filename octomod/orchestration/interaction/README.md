# Interaction points

An interaction point stops the run for a person's answer: `y` or `n`, with a note in their own
words. The interaction points of a run, their ids, the answer forms, how a note is read, and the
three policies are in [the orchestration README](../README.md#interaction-points). This folder
holds the code behind them.

## How a question reaches you

Every interaction point is asked through `ask` in `humangate.py`. It shows the card: the question,
up to 12 lines of evidence, what `y` and `n` lead to, the forms the note may use, the documents to
read, any questions the engine raises, and a RECORD INCOMPLETE line when the record lacks a part.
Then the first of these that applies answers it:

1. `--auto-approve` (tests only; refused together with `--policy`): yes, except that the failure
   points grant at most `retry.auto_grants` (2) extra attempts in all and then answer no.
2. The run's policy, if it covers this card (`policy.py`).
3. In file mode, the answer given with `--gate-answer` and `--gate-note`, if it was given for this
   card; a resume that reaches another card first pauses there and drops the answer. Without one,
   the run pauses (`pending_gate`).
4. At the terminal (the default): you type `y` or `n` and your note on the same line; `?` prints
   the question and its forms again.

Where the answer must survive a resume, `ask_once` writes it into the record and reads it back
instead of asking again.

## The note

`gate_note.py` reads the forms of a note; `redraft:` (`human_redraft.py`) and `fallback:` have their
own patterns. `redraft: <words>` sends the work back to its agent with your words and its previous
reply, and spends none of its attempts. When an agent proposes something that would change what the
data mean, the engine refuses it and puts it on the next card as a numbered question
(`questions.py`); the question and your answer are kept in the record at `questions`.

## When a check keeps failing

`retry.py` keeps every attempt of an agent with the checks it failed, in the record at
`agent_calls/<role>/dossier`, and hands them to the next attempt. When the attempts are spent, or no
agent wrote the failing value, the module asks at its failure point, `<module>_redraft_budget`:
`n=<attempts>` grants more and `n` stops. At M1 with a knowledge file, `floor: <band|none>` sets the
round's evidence floor. At M3 and M4, `redraft: <words>` sends your words instead, and at M4
`fallback: <name>` replaces the failing block with a default from `assembly_defaults.fallbacks` in
`workflows/default.yaml`. Which agent a failed check goes back to is in
[the checks](../../gates/README.md).

## Reference

<details>
<summary>How a policy decides</summary>

`policy.py` reads a policy file, `workflows/policies/<name>.yaml` or a path given to `--policy`:
`answers` per interaction point id, `caps`, and `uncovered: pause` or `stop` for an interaction point
the file does not answer. Cost-shaped interaction points are `assembly_cost_boundary` (the
compile), `cost_boundary_estimation` (the budget), `evaluation_profiling_gate`, and every
`<module>_redraft_budget`; every other id is judgement-shaped. `copilot` answers a cost-shaped one
even when its file does not name it, and pauses at a judgement-shaped one its file does not name.
Above `usd_cap` of agent cost, measured from the ledger, every card goes back to a person (under
`uncovered: stop`, the run stops). `max_expansions` and `redraft_grants` turn a yes at `revision`
and at the failure points into a no once reached. `n_starts`, when set, is the number of starts the
policy approves on the budget card. To write your own, copy a profile, change `answers` and `caps`,
and pass the file with `--policy <path>`.

</details>

## Files

| file | what it is |
|---|---|
| `battery_feedback.py` | A T0/T1 failure at S2/S3 blocks the artifact, never the run. |
| `gate_note.py` | One reading of the human's words at a gate, by the same rules at every gate. |
| `human_redraft.py` | The human as a source of redraft feedback, not only the gates. |
| `humangate.py` | T4: the blocking human gate, placed before expensive or hard-to-undo steps. |
| `policy.py` | Gate policy as declared configuration: the strict, copilot and benchmark profiles. |
| `questions.py` | Questions the engine raises for the human, surfaced on the next gate card. |
| `retry.py` | Redraft dossiers: every prior attempt of a role, as the next call sees it. |
