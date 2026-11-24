#!/usr/bin/env bash
# Delete everything the scripts created. Cloud SQL, the agents and Cloud Run bill while they exist.
source "$(dirname "$0")/lib.sh"
set +e
gcloud run services delete "$WEB_SERVICE" --region="$REGION" --project="$PROJECT_ID" --quiet
for p in agent1-egress agent3-egress platform-startup "$A1_POLICY"; do
  gcloud iam policy-bindings delete "$p-binding" --location=global --project="$PROJECT_ID" --quiet
  gcloud iam access-policies delete "$p" --location=global --project="$PROJECT_ID" --quiet
done
for id in "$AGENT1_ID" "$AGENT2_ID" "$AGENT3_ID"; do
  [ -n "$id" ] && curl -s -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    "https://$REGION-aiplatform.googleapis.com/v1/projects/$PROJECT_ID/locations/$REGION/reasoningEngines/$id?force=true" >/dev/null
done
gcloud beta network-security authz-policies delete "$GATEWAY-iap-authzpolicy" --location="$REGION" --project="$PROJECT_ID" --quiet
gcloud beta service-extensions authz-extensions delete "$GATEWAY-iap-authzextension" --location="$REGION" --project="$PROJECT_ID" --quiet
gcloud beta network-services agent-gateways delete "$GATEWAY" --location="$REGION" --project="$PROJECT_ID" --quiet
for s in $(gcloud alpha agent-registry services list --location="$REGION" --project="$PROJECT_ID" --format="value(name.basename())" | grep -E '^(ep-|agent[23]$)'); do
  gcloud alpha agent-registry services delete "$s" --location="$REGION" --project="$PROJECT_ID" --quiet
done
gcloud sql instances delete "$SQL_INSTANCE" --project="$PROJECT_ID" --quiet
gcloud secrets delete "$DB_SECRET" --project="$PROJECT_ID" --quiet
gcloud secrets delete "$SQL_INSTANCE-root-password" --project="$PROJECT_ID" --quiet
gcloud iam service-accounts delete "$WEB_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com" --project="$PROJECT_ID" --quiet
echo "Left in place: the staging bucket $STAGING_BUCKET and the IAM role grants on the project."
