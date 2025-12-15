#!/usr/bin/env bash
# Issue command(s) to a TPC server

# Usage: tpc_cmd.sh <tpc-host-ip> <cmd1> [cmd2 ... cmdN]

set -euo pipefail
PORT=8000

if [ "$#" -lt 2 ]; then
  echo "Usage: tpc_cmd.sh <tpc-host-ip> <cmd1> [cmd2 ... cmdN]" >&2
  exit 1
fi

H="$1"
shift

COMMANDS_JSON=$(python3 - "$@" <<'PY'
import json
import sys

print(json.dumps({"commands": sys.argv[1:]}))
PY
)

HTTP_RESPONSE=$(curl -sS -X POST "http://${H}:${PORT}/run" \
  -H 'Content-Type: application/json' \
  -d "$COMMANDS_JSON" \
  -w '\n%{http_code}')

STATUS=${HTTP_RESPONSE##*$'\n'}
BODY=${HTTP_RESPONSE%$'\n'$STATUS}

if [[ "$STATUS" != "200" ]]; then
  echo "Traffic PC request failed (HTTP ${STATUS})." >&2
  if [[ -n "$BODY" ]]; then
    echo "$BODY" >&2
  fi
  exit 1
fi

echo "$BODY" | python3 -m json.tool
