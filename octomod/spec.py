"""Workflow spec: the declared, hashed configuration the agent cannot edit.

All thresholds, budgets, retry counts and model assignments live here.
Rule 1 of the gate algebra: the agent may not choose its own pass criteria.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

OVERLAY_ENV = "OCTOMOD_SPEC_OVERLAY"

# The search methods the engine implements: `model_space` enumerates the
# declared axes exhaustively. Any other value is refused at run start.
SEARCH_METHODS = ("brute_force",)


def _deep_merge(base: dict, over: dict) -> dict:
    """`over` wins leaf by leaf; dicts merge, everything else replaces."""
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class WorkflowSpec:
    path: Path
    raw: dict = field(repr=False)
    sha: str = ""
    overlay: str | None = None

    @classmethod
    def load(cls, path: Path) -> WorkflowSpec:
        """Load a spec, merging the $OCTOMOD_SPEC_OVERLAY partial spec if set.

        The overlay is merged before the sha is computed, so a run under an
        overlay carries its own workflow_sha, never the base spec's.
        """
        raw = yaml.safe_load(path.read_text())
        overlay_path = os.environ.get(OVERLAY_ENV) or None
        if overlay_path:
            over = yaml.safe_load(Path(overlay_path).read_text()) or {}
            raw = _deep_merge(raw, over)
            raw["_overlay"] = {"path": str(overlay_path), "keys": sorted(over)}
        sha = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16]
        return cls(path=path, raw=raw, sha=sha, overlay=overlay_path)

    def get(self, dotted: str, default=None):
        """spec.get('gates.waterfall.k') -> value."""
        node = self.raw
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def require(self, dotted: str):
        val = self.get(dotted, default=None)
        if val is None:
            raise KeyError(f"workflow spec is missing required key: {dotted}")
        return val

    def validate(self) -> None:
        """Refuse, by name, a declared value the engine cannot honour.

        Raises ValueError for an enumerated key whose value is not implemented,
        rather than silently running the implemented behaviour instead.
        """
        method = str(self.require("search.method"))
        if method not in SEARCH_METHODS:
            raise ValueError(
                f"search.method {method!r} is not implemented; the engine runs "
                f"{list(SEARCH_METHODS)} only"
            )

    def model_for_role(self, role: str) -> str:
        override = self.get("models.override_all")
        if override:
            return override
        return self.get(f"models.{role}", self.require("models.default"))

    def effort_for_role(self, role: str) -> str:
        """The CLI effort level (`--effort`) a role's calls run at.

        Declared in `agents.effort` with the shape of `models` (a default and
        optional per-role keys), so `workflow_sha` covers it.
        """
        return str(
            self.get(f"agents.effort.{role}", self.require("agents.effort.default"))
        )
