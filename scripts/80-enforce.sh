#!/usr/bin/env bash
# Switch the gateway from DRY_RUN to enforce. Check the would-deny log first (see README).
source "$(dirname "$0")/lib.sh"
render "$ROOT/gateway/iap-authz-extension.yaml.tmpl" | grep -v "iamEnforcementMode" > "$ROOT/build/iap-authz-extension-enforce.yaml"
gcloud beta service-extensions authz-extensions import "$GATEWAY-iap-authzextension" --location="$REGION" \
  --project="$PROJECT_ID" --source="$ROOT/build/iap-authz-extension-enforce.yaml" --quiet
echo "Enforcing. Policy changes can take a few minutes to apply."
