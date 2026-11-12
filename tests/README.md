# tests: the test battery

The battery runs every suite once without spending anything: the agents are replaced by canned
replies (the stub backend), so only the engine is tested. The GitHub workflows run the style check and
the battery on every pull request and push to main, and the battery again nightly; both leave out the
groups `lb3` and `curves`, which read earlier runs from `runs/`.

```bash
uv run python tests/run_all.py                    # the whole battery, about 12 minutes
uv run python tests/golden_path.py toy_phos toy_decay_params    # a check of the install: two full runs
uv run python tests/<suite>.py                    # one suite
```

`run_all.py` holds the list of suites and their groups. Most suites run under smaller budgets
(`workflows/overlays/quick.yaml`); the ones marked full effort use the default settings.

## testcase/: the prepared problems

`testcase/` holds the small problems the suites run on, each a folder like the ones you stage
yourself: a description, an intent, the settings, data, and the canned replies of the agents
(`stubs/`). The `truth/` folders of the synthetic cases, which `tests/score_against_truth.py` reads,
are not part of this repository; without them the scorer reports that there is nothing to score.
The cases are also the quickest way to see a run:

```bash
./run.sh run --testcase testcase/toy_phos --backend stub --auto-approve
```

## Running the workflow without Claude

The workflow is a command-line program in its own right.

- `--backend stub` uses the canned replies; `--backend llm` calls the real agents and costs money.
- Without `--auto-approve` every interaction point waits for an answer at the terminal.
  `--gate-mode file` is the mode in which Claude drives a run: the run stops at each interaction
  point, and the answer is passed with `--gate-answer`.
- `--run-id <id>` with no `--testcase` resumes a run on the inputs its record holds. `--from-run <id>`
  starts a new run from another run's inputs. `--from-module model|data|assembly|estimation|evaluation`
  re-enters a run at a module.
- `OCTOMOD_RESULT_COMMIT=off` skips the checkpoint copy (`runs/<id>.h5.bak`).
  `OCTOMOD_RECORD_CHECKS=off` skips the completeness checks of the record.

`./run.sh <command> --help` lists every option of a command; [`CLAUDE.md`](../CLAUDE.md) describes
the ones the orchestrating agent uses.
