#!/usr/bin/env bash
# The Agent Gateway, plus the IAP authorization extension and policy (in DRY_RUN).
source "$(dirname "$0")/lib.sh"
render "$ROOT/gateway/agent-gateway.yaml.tmpl" > "$ROOT/build/agent-gateway.yaml"
render "$ROOT/gateway/iap-authz-extension.yaml.tmpl" > "$ROOT/build/iap-authz-extension.yaml"
render "$ROOT/gateway/iap-authz-policy.yaml.tmpl" > "$ROOT/build/iap-authz-policy.yaml"
gcloud beta network-services agent-gateways import "$GATEWAY" --location="$REGION" --project="$PROJECT_ID" \
  --source="$ROOT/build/agent-gateway.yaml" --quiet
gcloud beta service-extensions authz-extensions import "$GATEWAY-iap-authzextension" --location="$REGION" \
  --project="$PROJECT_ID" --source="$ROOT/build/iap-authz-extension.yaml" --quiet
gcloud beta network-security authz-policies import "$GATEWAY-iap-authzpolicy" --location="$REGION" \
  --project="$PROJECT_ID" --source="$ROOT/build/iap-authz-policy.yaml" --quiet
