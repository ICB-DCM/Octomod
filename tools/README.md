# tools: for developers

Scripts that are not part of a run. A user of the workflow does not need them.

| file | what it does |
|---|---|
| `make_result_schema.py` | writes `docs/result_schema.json` and `docs/RESULT-SCHEMA.md` from the record's classes in `octomod/result/`; a test fails when the two are out of date |
| `make_routing.py` | writes `docs/ROUTING.md`, what each agent is shown, from the routing table in the code; a test fails when it is out of date |
| `probe_hierarchical_matrix.py`, `probe_profile_options.py` | measure which hierarchical-estimation and profiling options of the pinned pyPESTO behave correctly; they produced the tables in `docs/MODULARITY.md` |
| `probe_mcp_isolation.py`, `probe_mcp_server.py` | check that an agent call cannot reach a tool server it was not given; used by the test battery |
| `probe_research_live.py` | one live call of the research agent with the engine's exact command; the battery runs only its dry run |
| `probe_processing_ctd.py` | prints the per-time-point sums the data processing finds in the CTD example; used by one test |

Run any of them from the repository root, for example
`uv run python tools/make_routing.py`.
