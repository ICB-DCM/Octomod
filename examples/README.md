# examples: the paper's four problems

One folder per application run shown in the main text, exported from the run
record's `input/` group: exactly what the workflow received. Not tests, not
staged problems. To rerun one, copy it into `staging/` and start Claude, or run
it directly and answer each interaction point at the terminal:

```bash
cp -r examples/ctd staging/ctd
claude          # "run the staged problem ctd"
./run.sh run --testcase staging/ctd --backend llm --run-id ctd_rerun
```

A rerun uses `workflows/default.yaml` as committed; the model, effort and settings
of each original run are in its record. The agents' replies will differ from the
original runs, which are on Zenodo with every reply. An example with a
`knowledge/` folder starts from that knowledge file; delete the folder to run the
knowledge module again (`./run.sh knowledge --testcase staging/<name> --mode online
--backend llm`). The CTD example runs without the knowledge module, by its
`testcase.yaml`.

| folder | paper | record on Zenodo |
|---|---|---|
| `ctd/` | Results 1 | `ctd_blind_local_v3_opus55_20261004_022720.h5` |
| `macrophage/` | Results 2, first run | `macrophage_xue_20260929_210535.h5` |
| `macrophage_recalibration/` | Results 2, second run, started from the recalibrated model of the first | `macrophage_xue_v2_20260930_131832.h5` |
| `pbmc/` | Results 3 | `bodenmiller2012_crosstalk_r5_20260930_232653.h5` |
| `sphingolipid/` | Results 4, first of six runs | `sphingolipid_metabolism_20260929_120748.h5`; the other five are on Zenodo |

Each folder holds `description.md` (the project description), `intent.yaml`
(the intent), `testcase.yaml` (the staged settings and the held-out
declaration; no run of the paper declared a held-out condition), `data/`,
and, where the run used them, `knowledge/` (the knowledge module's output
with its calls), `supplied/` (the macrophage recalibration's supplied model;
for the sphingolipid problem the supplied network, the original PEtab problem,
and the full lipidomics table, kept as provenance beside the data file the run
read), and `blocklist.txt`.

Two things are not here, and `REMOVED.md` in a folder says which. The two
files the macrophage intents name as supplied literature,
`paper/macrophage_xue-main.pdf` and `paper/1-s2.0-S107476131400034X-mmc1.pdf`
(Xue et al. 2014, doi:10.1016/j.immuni.2014.01.006, and its supplement), are
to be placed under those names in `paper/` of the staged copy by whoever
reruns those two; a named file that is missing is left out silently. And the
web pages and PDFs the knowledge module fetched, which
`knowledge/knowledge.json` names by identifier.

The sphingolipid data were generated for the paper (Moore Dillems, Thiele);
see the paper's data availability statement.
