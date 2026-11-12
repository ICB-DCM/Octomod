# The CTD example

- `record/ctd_blind_local_v3_opus55_20261004_022720.h5` — the run's record, as the engine wrote it except for one anonymisation: the machine-local temporary folder in three `data/report/provenance` entries is replaced by `<tmp>/`, and the file is compacted so no earlier copy remains
- `make_walkthrough.py` — writes `walkthrough.ipynb`, `explore_record.ipynb`, `figures/` and `prompts/` from the record
- `../../_extra/ctd_blind_reports/` — the engine's HTML reports of the run, rendered from the record with `./run.sh report`

Regenerate after changing the script: `uv run --group docs python docs/site/examples/ctd_blind/make_walkthrough.py`.
