#!/usr/bin/env bash
# Bind Agent 1 and Agent 3 to the gateway. From now on all their outbound traffic goes through it.
source "$(dirname "$0")/lib.sh"
cd "$ROOT"
"$PY" deploy/deploy.py agent3 --bind
"$PY" deploy/deploy.py agent1 --bind
