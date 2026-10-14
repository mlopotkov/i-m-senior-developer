#!/bin/bash
set -euo pipefail
if [[ "${1:-}" == plugin && "${2:-}" == eval ]]; then
  for argument in "$@"; do
    if [[ "$argument" == --keep-temp ]]; then
      exec /usr/local/share/npm-global/bin/claude "$@"
    fi
  done
  exec /usr/local/share/npm-global/bin/claude "$@" --keep-temp
fi
exec /usr/local/share/npm-global/bin/claude "$@"
