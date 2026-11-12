"""A stdio MCP server with one tool, `probe_marker`: the isolation probe's control.

Handed to `claude -p` via `--mcp-config`, its tool must be listed; listed without that
config, a user-wide MCP server reached the agent. Answers `initialize`, `tools/list`,
`tools/call` and `ping`; newline-delimited JSON-RPC, flushed per message.

    uv run python tools/probe_mcp_server.py          # speaks JSON-RPC on stdio
"""

from __future__ import annotations

import json
import sys

TOOL = {
    "name": "probe_marker",
    "description": "Isolation probe marker: exists only so its name can be listed.",
    "inputSchema": {"type": "object", "properties": {}},
}


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> dict | None:
    """The response for one request, or None for a notification."""
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:  # a notification (e.g. notifications/initialized)
        return None
    if method == "initialize":
        proto = (msg.get("params") or {}).get("protocolVersion", "2024-11-05")
        result = {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "probe", "version": "0.1"},
        }
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "probe_marker reached"}]}
    elif method == "ping":
        result = {}
    else:
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(msg)
        if reply is not None:
            _send(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
