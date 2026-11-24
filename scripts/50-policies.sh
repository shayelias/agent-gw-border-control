#!/usr/bin/env bash
# Create the egress access policies and bind each one to the gateway.
source "$(dirname "$0")/lib.sh"
for p in agent1-egress agent3-egress platform-startup "$A1_POLICY"; do
  tmpl="$ROOT/policies/$p.json.tmpl"; [ -f "$tmpl" ] || tmpl="$ROOT/policies/a1-to-agents.json.tmpl"
  render "$tmpl" > "$ROOT/build/$p.json"
  gcloud iam access-policies create "$p" --details-rules="$ROOT/build/$p.json" --location=global --project="$PROJECT_ID"
  gcloud iam policy-bindings create "$p-binding" --location=global --project="$PROJECT_ID" \
    --policy="projects/$PROJECT_ID/locations/global/accessPolicies/$p" \
    --target-resource="//networkservices.googleapis.com/projects/$PROJECT_ID/locations/$REGION/agentGateways/$GATEWAY"
done
