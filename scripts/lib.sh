# Sourced by every script: strict mode, config, helpers.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/config.env" ] || { echo "Copy config.env.example to config.env and fill it in."; exit 1; }
set -a; source "$ROOT/config.env"; set +a
PY="${PY:-$ROOT/.venv/bin/python}"
mkdir -p "$ROOT/build"

# set_config KEY VALUE: write a value into config.env and the current shell
set_config() {
  sed -i.bak "s|^$1=.*|$1=$2|" "$ROOT/config.env" && rm -f "$ROOT/config.env.bak"
  export "$1=$2"; echo "  config.env: $1=$2"
}
render() { python3 "$ROOT/scripts/render.py" "$1"; }
agent_principal() {
  echo "principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/$1"
}
