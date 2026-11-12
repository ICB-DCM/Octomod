"""The run result object: every result of a run as one typed record, one file.

The record is the ONLY store: the run is `runs/<id>.h5`, and there is no run
directory. Every artifact has a record key and, where it has a record class,
a validated shape, so no reader globs for files and no second index can
disagree with what is stored.

  records.py    the leaf records — gate, ledger row, decision, agent call,
                table, provenance — and the tier annotation every field carries
  slots.py      one record per artifact slot of `round_status.SLOTS`, plus the
                revision, expansion and model-space records
  model.py      the root: RunResult → RoundRecord → CandidateRecord
  runstore.py   RunStore — the one class that touches the file: group-wise
                put/get/copy, one-handle read sessions, the appendable
                ledger, load (lenient)/write_all, verify and checkpoint
                (crash safety), compact, remove
  node.py       Node — a location in the record by record key, with typed
                accessors (get/put, text, table, blob), and where each part
                of a round lives (model, gates, markers, candidates)
  explorer.py   `./run.sh explore` (interactive) and `show` (one part)
  store.py      whole-record forms: export copies pruned by tier, the schema
  write.py      validated writes: a module's payload passes its record class
  access.py     the readers' source: `record_for(run)` and artifact views
  autocommit.py the checkpoint at every marker, decision, pause and run end
  agent_replies.py  one reply class per agent role, checked at the seam
  importer.py   LEGACY: a run directory transcribed into a record
                (`./run.sh import-legacy`); the one place the directory's
                file names are known

The engine WRITES through this package (every artifact into the record, the
ones with a record class validated on the way) and READS through it (modules,
renderers, the analysis report, the tried-models memory, the decision record, the
truth scorer, the CLI). The libraries the engine drives receive in-memory
objects built from the record (`octomod/workflow_modules/assembly/petab_io.py`, `estimation`).
"""

from octomod.result.model import (  # noqa: F401
    CandidateRecord,
    RoundRecord,
    RunMeta,
    RunOutcome,
    RunResult,
)
from octomod.result.node import Node  # noqa: F401
from octomod.result.records import (  # noqa: F401
    SCHEMA_VERSION,
    TIERS,
    AgentCallRecord,
    DecisionRecord,
    FileRef,
    GateRecord,
    LedgerEvent,
    QuestionRecord,
    Record,
    Table,
)
from octomod.result.runstore import RunStore  # noqa: F401
from octomod.result.store import (  # noqa: F401
    RunResultStandard,
    commit,
    load,
    prune,
    schema_json,
)
