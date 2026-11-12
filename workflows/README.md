# workflows: the settings of a run

Everything an agent may not choose for itself is declared here: which model each
agent uses, the budgets for redrafts, the thresholds of the checks, the number
of optimisation starts, the criteria of model selection. The engine reads the
file once at the start of a run and stores it in the run record, so a record
always says under which settings it was produced.

| file | what it is |
|---|---|
| `default.yaml` | the settings every run uses unless told otherwise; each value has a comment saying what it controls |
| `policies/strict.yaml` | the default policy: every interaction point reaches a person |
| `policies/copilot.yaml`, `policies/benchmark.yaml` | declared policies under which named interaction points are answered by a rule; the record says which policy was in force |
| `overlays/quick.yaml` | smaller budgets, laid over `default.yaml` by the test battery so that it runs in minutes |
| `test_redraft.yaml` | a variant used by the tests of the redraft loop |

To run with other settings, copy `default.yaml`, change it, and pass it with
`--workflow <file>`. To use a policy, pass `--policy <name>`.
