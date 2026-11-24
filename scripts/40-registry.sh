#!/usr/bin/env bash
# Register the destinations the agents may reach: Google API hosts, plus Agent 2 and Agent 3.
source "$(dirname "$0")/lib.sh"
HOSTS="agentregistry.googleapis.com logging.googleapis.com logging.mtls.googleapis.com telemetry.googleapis.com
telemetry.mtls.googleapis.com cloudtrace.googleapis.com cloudtrace.mtls.googleapis.com monitoring.googleapis.com
monitoring.mtls.googleapis.com cloudresourcemanager.googleapis.com cloudresourcemanager.mtls.googleapis.com
iamcredentials.googleapis.com iamcredentials.mtls.googleapis.com aiplatform.googleapis.com aiplatform.mtls.googleapis.com
${REGION}-aiplatform.googleapis.com ${REGION}-aiplatform.mtls.googleapis.com aiplatform.${REGION}.rep.googleapis.com"
for h in $HOSTS; do
  gcloud alpha agent-registry services create "ep-$(echo "$h" | tr . -)" --project="$PROJECT_ID" --location="$REGION" \
    --display-name="api-$h" --endpoint-spec-type=no-spec --interfaces="url=https://$h,protocolBinding=http-json" \
    --quiet >/dev/null && echo "  registered $h"
done
for n in 2 3; do
  id_var="AGENT${n}_ID"
  gcloud alpha agent-registry services create "agent$n" --project="$PROJECT_ID" --location="$REGION" \
    --display-name="Agent$n" --endpoint-spec-type=no-spec \
    --interfaces="url=https://${REGION}-aiplatform.mtls.googleapis.com/v1beta1/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${!id_var},protocolBinding=jsonrpc" \
    --quiet >/dev/null && echo "  registered Agent $n"
done
sleep 10   # endpoints appear shortly after their services
ep() { gcloud alpha agent-registry endpoints list --location="$REGION" --project="$PROJECT_ID" \
  --filter="displayName=$1" --format="value(name.basename())" | head -1; }
set_config AGENT2_ENDPOINT "$(ep Agent2)"
set_config AGENT3_ENDPOINT "$(ep Agent3)"
