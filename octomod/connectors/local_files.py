"""The one connector that actually ships: delimited files in a directory.

Why this one and only this one: it is what every test case and every staged
real dataset uses, and it is the only backend whose failure modes are entirely
local. It also pins down what "provenance" costs in practice — a hash of the
bytes and a date — so that a remote connector added later has a concrete
standard to meet rather than an abstract one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from octomod.connectors.base import (
    DataConnector,
    ProvenancedTable,
    SourceRef,
    make_provenance,
)

# Extension -> pandas separator. Non-recursive and closed on purpose: a nested
# tree of half-named exports is exactly the situation where an agent silently
# picks the wrong file, so the staging step must flatten it deliberately.
SEPARATORS = {".csv": ",", ".tsv": "\t"}

# Spreadsheet exports we deliberately do NOT read. list_sources() skips every
# unknown suffix silently, which is right for a stray README and wrong for a
# workbook: "no data files" in a directory that visibly holds one sends the
# reader hunting a path bug, and a workbook NEXT TO a csv disappeared entirely.
# Naming them is the whole fix — the conversion stays a human step, because
# which sheet and which header row are modelling decisions.
SPREADSHEET_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".ods"}


def unreadable_spreadsheets(root: Path | str) -> list[str]:
    """Spreadsheet files directly inside `root` that `list_sources` skips."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in SPREADSHEET_SUFFIXES
    )


def sha256_file(path: Path) -> str:
    """16 hex chars of the file bytes — matches octomod.orchestration.ledger.sha256_file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


class LocalFilesConnector(DataConnector):
    """Every *.csv / *.tsv directly inside `root`."""

    name = "local_files"

    def __init__(self, root: Path | str):
        self.root = Path(root)

    def list_sources(self) -> list[SourceRef]:
        """Sorted so that a run over an unchanged directory is reproducible."""
        if not self.root.is_dir():
            raise FileNotFoundError(f"connector root is not a directory: {self.root}")
        refs = []
        for path in sorted(self.root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SEPARATORS:
                continue
            refs.append(
                SourceRef(
                    connector=self.name,
                    locator=str(path),
                    kind="table",
                    meta={"filename": path.name, "bytes": path.stat().st_size},
                )
            )
        return refs

    def fetch(self, ref: SourceRef) -> ProvenancedTable:
        path = Path(ref.locator)
        sep = SEPARATORS.get(path.suffix.lower())
        if sep is None:
            raise ValueError(
                f"{self.name} handles {sorted(SEPARATORS)}, not {path.suffix!r}"
            )
        df = pd.read_csv(path, sep=sep)
        # units and error_spec stay "undeclared": the file gives us bytes and a
        # header row, and nothing in either is evidence about either question.
        prov = make_provenance(
            source_id=str(path),
            sha256=sha256_file(path),
            extraction_method="file_read",
            separator=sep,
            n_rows=int(len(df)),
            columns=[str(c) for c in df.columns],
        )
        return ProvenancedTable(df=df, provenance=prov)
