# Connectors

A connector brings material from outside the engine into a run and records
where it came from. There are 2.

- `local_files.py` reads the user's data files. `LocalFilesConnector` lists
  every `.csv` and `.tsv` file directly inside a folder, not in its subfolders,
  and returns each as a table with its provenance: the path, a hash of the
  bytes, how it was read, and the date. `unreadable_spreadsheets()` names the
  workbooks (`.xlsx`, `.xlsm`, `.xls`, `.ods`) beside them, so that the engine
  refuses them instead of skipping them.
- `web_cache.py` fetches and caches the sources that the knowledge module and
  the `research` agent cite, and the papers a user supplies, so that a check of
  a citation and a rerun do not depend on the web. Each fetch is recorded with
  its outcome: cached, too large, or unreachable. It also answers 2 questions
  the engine, never an agent, asks of a cited source: does its DOI, PMID or URL
  resolve (`resolve_source`), and which kind of publication is it in PubMed
  (`publication_types`).

`base.py` defines the contract that `LocalFilesConnector` implements:
`SourceRef`, a pointer to one source that can be listed without fetching it;
`ProvenancedTable`, a table with its provenance (source, hash, extraction
method, units, error model, retrieval date); `DataConnector`, the interface
with `list_sources()`, `fetch()` and `preview()`; and `make_provenance()`,
which sets the units and the error model to `undeclared`, not to a guess.
