#!/usr/bin/env bash
# Create the three agents (unbound), then give each agent identity only the roles it needs.
source "$(dirname "$0")/lib.sh"
cd "$ROOT"
for a in agent2 agent3 agent1; do        # Agent 1 last: it needs the other two IDs
  id="$("$PY" deploy/deploy.py "$a" | tail -1)"
  set_config "$(echo "$a" | tr a-z A-Z)_ID" "$id"
done
grant() { gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$1" --role="roles/$2" --condition=None --quiet >/dev/null && echo "  $2"; }
for id in "$AGENT1_ID" "$AGENT3_ID"; do
  m="$(agent_principal "$id")"; echo "roles for engine $id:"
  for r in aiplatform.user aiplatform.agentDefaultAccess agentregistry.viewer browser logging.logWriter monitoring.metricWriter; do grant "$m" "$r"; done
done
m="$(agent_principal "$AGENT2_ID")"; echo "roles for engine $AGENT2_ID:"
for r in aiplatform.user cloudsql.client logging.logWriter; do grant "$m" "$r"; done
gcloud secrets add-iam-policy-binding "$DB_SECRET" --project="$PROJECT_ID" --member="$m" \
  --role=roles/secretmanager.secretAccessor --quiet >/dev/null && echo "  secretAccessor on $DB_SECRET"
