"""Regenerate docs/ROUTING.md from the routing table in octomod/agents/routing.py.

    .venv/bin/python tools/make_routing.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from octomod.agents import routing  # noqa: E402

if __name__ == "__main__":
    out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "ROUTING.md"
    out.write_text(routing.render_markdown())
    print(f"wrote {out}")
