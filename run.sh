#!/usr/bin/env bash
# Convenience wrapper: always the project venv, always from the repo root.
#   ./run.sh run --testcase testcase/<case> --backend stub --auto-approve
# Machine-portable resolution (mirrors octomod/config.py):
#   $OCTOMOD_PYTHON  >  ./.venv (uv sync)  >  ../octomod_venv
set -e
cd "$(dirname "$0")"
if [[ -n "$OCTOMOD_PYTHON" && -x "$OCTOMOD_PYTHON" ]]; then
  exec "$OCTOMOD_PYTHON" -m octomod "$@"
fi
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m octomod "$@"
fi
if [[ -x ../octomod_venv/bin/python ]]; then
  exec ../octomod_venv/bin/python -m octomod "$@"
fi
echo "No project environment found. Run:  uv sync   (see README)" >&2
exit 1
