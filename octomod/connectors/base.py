"""Data-connector contract: how external evidence enters the pipeline.

Why a layer at all: every table an agent reasons over must carry where it came
from, how it was extracted, and what is *not yet known* about it (units, error
structure). Those last two are the fields that actually cause silent modelling
errors downstream — a densitometry column read as a concentration, or
replicates mistaken for a declared sigma — so they are required keys that start
life as the literal string "undeclared" rather than as a plausible guess. An
agent must *declare* them in S2, and the declaration is then an auditable act
in the ledger instead of an assumption nobody wrote down.

Why the interface is thin: connectors rot. Any code that talks
to a remote schema is the first thing to break and the last thing worth
generalising, so this module fixes only the shape that the rest of the pipeline
depends on. Exactly one implementation ships (`local_files`); everything else is
a seam, documented in README.md.
"""

from __future__ import annotations

import datetime
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd

# Vocabularies. Kept small and closed: an unrecognised value is a bug in the
# connector, not a new category to be invented at call time.
SOURCE_KINDS = ["table", "figure", "text"]
EXTRACTION_METHODS = ["file_read", "digitised", "api"]

# Provenance keys the rest of the pipeline is allowed to assume exist.
PROVENANCE_REQUIRED = [
    "source_id",
    "sha256",
    "extraction_method",
    "units",
    "error_spec",
    "retrieved",
]

UNDECLARED_UNITS = "undeclared"
UNDECLARED_ERROR_SPEC = {"type": "undeclared"}


@dataclass
class SourceRef:
    """A pointer to one retrievable thing, cheap to list and to serialise.

    Listing must never require fetching: an agent shown 40 candidate sources
    should be able to choose between them before anything is read or paid for,
    which is why `meta` exists (size, title, caption, accession) and why the
    dataframe does not live here.
    """

    connector: str
    locator: str  # file path, URL, accession — resolvable by `connector` alone
    kind: str  # one of SOURCE_KINDS
    meta: dict = field(default_factory=dict)


@dataclass
class ProvenancedTable:
    """A dataframe that cannot be separated from its provenance.

    The pairing is the point. A bare DataFrame handed between modules loses the
    one thing the S3 gates need in order to fail honestly (magnitude
    reconciliation needs units; the noise-model gate needs the error spec).
    """

    df: pd.DataFrame
    provenance: dict

    def validate(self) -> list[str]:
        """T0-style check: returns a list of problems, empty means fine.

        Deliberately shallow — deep checks belong in gates, not here.
        """
        problems = [
            f"provenance.{k} missing"
            for k in PROVENANCE_REQUIRED
            if k not in self.provenance
        ]
        method = self.provenance.get("extraction_method")
        if method is not None and method not in EXTRACTION_METHODS:
            problems.append(
                f"provenance.extraction_method must be one of "
                f"{EXTRACTION_METHODS}, got {method!r}"
            )
        if not isinstance(self.provenance.get("error_spec", {}), dict):
            problems.append("provenance.error_spec must be a dict")
        return problems


def make_provenance(
    source_id: str,
    sha256: str,
    extraction_method: str,
    retrieved: str | None = None,
    **extra,
) -> dict:
    """Build a provenance dict with the undeclared fields left undeclared.

    Connectors call this instead of writing the dict by hand so that no
    implementation can quietly ship a guessed `units` — the guess has to be
    passed explicitly through `extra`, which makes it visible in review.
    """
    prov = {
        "source_id": source_id,
        "sha256": sha256,
        "extraction_method": extraction_method,
        "units": UNDECLARED_UNITS,
        "error_spec": dict(UNDECLARED_ERROR_SPEC),
        "retrieved": retrieved or datetime.date.today().isoformat(),
    }
    prov.update(extra)
    return prov


class DataConnector(ABC):
    """One source family (a directory, a repository, an API).

    Two required verbs, deliberately: list (cheap, no side effects) and fetch
    (may be expensive). Anything richer — search, filtering, ranking — is the
    caller's job, so that a new connector is a morning's work rather than a
    reimplementation of the retrieval layer.
    """

    name: str = "base"

    @abstractmethod
    def list_sources(self) -> list[SourceRef]:
        """Enumerate what this connector can offer, without fetching any of it."""

    @abstractmethod
    def fetch(self, ref: SourceRef) -> ProvenancedTable:
        """Retrieve one source as a table plus its provenance."""

    def preview(self, ref: SourceRef, n: int = 25) -> str:
        """First `n` rows as CSV text, for putting in a prompt.

        Default implementation goes through `fetch`; a connector whose backend
        can return a head cheaply should override it rather than pay for the
        whole table just to show an agent the column names.
        """
        table = self.fetch(ref)
        buf = io.StringIO()
        table.df.head(n).to_csv(buf, index=False)
        return buf.getvalue()
