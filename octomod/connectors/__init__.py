"""Data connectors. See README.md for the contract and the deferred seams."""

from octomod.connectors.base import DataConnector, ProvenancedTable, SourceRef
from octomod.connectors.local_files import LocalFilesConnector

__all__ = ["DataConnector", "ProvenancedTable", "SourceRef", "LocalFilesConnector"]
