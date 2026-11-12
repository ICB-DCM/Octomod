# PERMISSIONS — what an agent can see, do and reach

Three independent mechanisms, none of which relies on the model behaving. Each is enforced in one place, so
there is one thing to read and one thing to change.

Companion page: [`ROUTING.md`](ROUTING.md) is generated from the routing table and lists every key each role
is granted.

---

## 1 · Context — what it sees

An **allow-list per role**, in `octomod/agents/routing.py`. `enforce()` runs at the single seam every agent call
passes through (`RunContext.call`; outside a run, the knowledge module's staging call, `knowledge.StagingSession`,
calls it the same way), and a key nobody granted **raises** rather than warns:

> *"the routing rules are the blind benchmark's whole basis, and a payload that leaks past them invalidates
> every result it touches."*

Thirteen roles. The rule that carries the most weight is `construction`: it sees intent, the experiment
description, domain packs, retrieved literature and what the measured curves look like in words
(`data_phenomenology`: shape and timescale, never a value), and **no measurement value, no data preview,
no noise statistic — and not the design summary either**, even though that carries only metadata:

> *"'measurement metadata' is a line that needs arguing every time it is applied, and a rule you have to
> argue is a rule that eventually goes the other way."*

`docs/ROUTING.md` is generated from the same table by `tools/make_routing.py`, with a test that fails when
the page and the table disagree — the page cannot drift.

**`never` is not enforcement.** Only `sees` is an allow-list. A role's `never` entries record *why* a key is
absent, so a later reader adding one can tell "nobody needed it yet" from "this is load-bearing".

## 2 · Tools — what it can do

An **allow-list on the CLI**, built in `llm_backend.argv()` and nowhere else, so the probes import the
engine's own shape instead of restating it:

| role | `--tools` | `--allowedTools` |
|---|---|---|
| every offline role | `""` — the built-in set switched off entirely | — |
| `research` | `WebSearch,WebFetch` | `WebSearch,WebFetch` |
| `knowledge`, online mode (the call asks: `agents.granted_tools`) | `WebSearch,WebFetch` | `WebSearch,WebFetch` |
| `knowledge`, offline mode | `""` | — |

`ONLINE_ROLES` holds the two grants (`research`, `knowledge`); every other role, `knowledge_verification`
included, is offline. `knowledge` is also in `PER_CALL_GRANT`: it is online only when a call asks for it
(`online=True` — the staged survey in `--mode online`, and a targeted search inside a run whose survey ran
online) and offline otherwise, so a caller that says nothing places an offline call; a call can narrow a
role's grant, never widen one (`granted_tools` refuses an online call of a role that has none).

Two details that are easy to get wrong and were both learned the hard way:

- **`--allowedTools` is the permission, `--tools` is the set.** Headless `-p` has no human to approve a call,
  so a tool that is selected but not pre-allowed is denied at the call. The first live research probe came
  back with every WebSearch *"ATTEMPTED, BLOCKED"* and zero evidence items.
- **An allow-list, never a denylist.** The MCP probe found **22 built-in tools** the previous
  13-name denylist did not name — `Workflow`, `SendMessage`, `CronCreate`, … — none of which existed when
  that list was written. *A denylist cannot name a tool nobody has added yet.* `--disallowedTools` and
  `_DISALLOWED_TOOLS` are gone.

Every prompt also states its own tools in a `# Your tools` section, because a run once had construction try
to `ls` data it has no tools for.

**MCP: none reaches any role, by construction.** `claude -p` loads MCP servers from the user-wide config
whatever the cwd is; `--strict-mcp-config` restricts the set to `--mcp-config`, and none is ever passed.

## 3 · Process — where it runs

- **One fresh `claude -p` subprocess per typed hole.** No session is carried between holes, so context is
  exactly what the module put in the prompt and nothing the model remembers.
- **A directory that inherits nothing.** `_isolated_cwd()` makes a neutral `tempfile.mkdtemp()` path and then
  walks its ancestors, **refusing to run** if any of them holds `CLAUDE.md`, `.claude` or `.git`. The prefix
  is neutral on purpose: a probe once read the project's name off its own path, twice, because Claude Code
  also derives its per-project memory path from the cwd.
- **A stripped environment.** `_clean_env()` removes every `CLAUDE*` variable and `ANTHROPIC_BASE_URL`, so a
  pipeline started from inside a Claude Code chat does not confuse the child CLI.
- **The prompt goes on stdin**, never in the argv.
- **`--effort` is declared by the workflow** (`agents.effort`), so `workflow_sha` covers it and the ledger
  records it. Before that, every live call ran at an effort level no workflow declared.

## 4 · Human permissions — the gate policy

Who may answer a gate is itself declared configuration (`octomod/orchestration/interaction/policy.py`), and the ledger never
pretends otherwise: a policy-answered gate is recorded `mode="policy"` with the policy sha, and a
policy-signed verdict reads `signed: policy(<sha>)`, never as a human.

| profile | behaviour |
|---|---|
| `strict` | every human gate pauses for a live human; the policy answers nothing. **This is what no `--policy` flag gives you** — the `run` command in `cli.main` passes an unset `--policy` on as `strict` ("Unset = strict"), and `Orchestrator.__init__` loads it with `Policy.load`: a profile with no answers, so every gate reaches a person, and the run records the profile and its sha |
| `copilot` | **cost**-shaped gates (compile boundary, estimation budget, profiling, redraft grants) are answered by policy under declared caps; **judgment**-shaped gates (intent freeze, scope/axes, expansion, stop-vs-revise, verdict) pause |
| `benchmark` | no human exists; every gate reached must be covered by a pre-declared answer, and an uncovered gate **stops the run honestly** |

Expansion purchases under policy are capped (`max_expansions`, default 1): *whether the loop knows when to
stop adding mechanism is untested, so policy must not become an unbounded mechanism-buying machine pointed at
exactly that spot.*

`--auto-approve` is the test-suite primitive only.

---

## 5 · How this was verified

Asserted against mocks in the battery; asked of the CLI itself by two **opt-in live probes**, which spend
usage and are therefore not in the battery. Both import `argv`, `_isolated_cwd` and `_clean_env` from the
engine — *a probe that builds its own invocation is testing a different program than the one that runs.*

| probe | result after the isolation fixes |
|---|---|
| `tests/isolation_probe.py` | `claude_md` NONE · `memory` NONE · `location` clean |
| `tools/probe_mcp_isolation.py` | no MCP tool under the engine's argv; the positive control fires with `--mcp-config` |
| functional tool test | a token file placed on disk, the offline argv asked to read it → `NONE`, `num_turns 1`, `permission_denials []`, and the model's "tool call" written as **text** inside its reply |

That last row is the method, not a detail. Asked to *list* its tools under `--tools ""`, the model listed a
plausible set that does not exist:

> **A probe that asks a model what it can do measures the model's beliefs; only a functional test measures
> the capability.**

## 6 · What is still open — state this when the topic comes up

1. **Both isolation breaches were found by a probe, late, not by design.** The repository's `CLAUDE.md`
   (10 849 bytes) was loaded into **every subagent call for the project's whole history** until a probe found it,
   because the "isolated" cwd was inside the repository. The temp-directory prefix carried the project's name
   until the fix after that. Isolation is a property you test — from the exact cwd, with the exact argv — not one you
   declare.
2. **`never` is documentation, not enforcement** (§1).
3. **`research` and `knowledge` (online mode) reach the open web by design.** What comes back is untrusted text
   that enters a later prompt. Nothing currently treats retrieved content as hostile.
4. **The worst contamination was not in the data path at all.** `skills/revision.md` described a
   hidden mechanism's signature in nearly the words its own answer key uses, naming nothing — so every check
   looked at the data and correctly reported that the blind property held. Five runs' claims were retracted.
   Two guards now run on every battery (`testcase_truth_leak_unit`, `no_benchmark_in_templates`), but the
   identifier guard covers *names*, and that is not the whole leak. **Prompt templates are experimental
   apparatus and need the same contamination discipline as the data.**
5. **Nothing isolates the model from its own training data.** A blind benchmark cannot be blind to what the
   model already knows.
