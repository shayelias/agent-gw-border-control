#!/usr/bin/env bash
# The web app on Cloud Run behind IAP. Its service account may sign JWTs as itself (no key file).
source "$(dirname "$0")/lib.sh"
SA="$WEB_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
gcloud iam service-accounts create "$WEB_SA_NAME" --project="$PROJECT_ID" --display-name="Agent demo web app" || true
for r in aiplatform.user logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="roles/$r" --condition=None --quiet >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$SA" --project="$PROJECT_ID" \
  --member="serviceAccount:$SA" --role=roles/iam.serviceAccountTokenCreator --quiet >/dev/null
E="projects/$PROJECT_NUMBER/locations/$REGION/reasoningEngines"
gcloud beta run deploy "$WEB_SERVICE" --source="$ROOT/web" --project="$PROJECT_ID" --region="$REGION" \
  --iap --no-allow-unauthenticated --service-account="$SA" --quiet \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,REGION=$REGION,GATEWAY=$GATEWAY,A1_POLICY=$A1_POLICY,WEB_SA=$SA,\
AGENT1_RESOURCE=$E/$AGENT1_ID,AGENT2_RESOURCE=$E/$AGENT2_ID,AGENT3_RESOURCE=$E/$AGENT3_ID,\
AGENT2_ENDPOINT=$AGENT2_ENDPOINT,AGENT3_ENDPOINT=$AGENT3_ENDPOINT,\
IAP_AUDIENCE=/projects/$PROJECT_NUMBER/locations/$REGION/services/$WEB_SERVICE"
gcloud run services add-iam-policy-binding "$WEB_SERVICE" --region="$REGION" --project="$PROJECT_ID" \
  --member="serviceAccount:service-$PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker --quiet >/dev/null
gcloud beta iap web add-iam-policy-binding --resource-type=cloud-run --service="$WEB_SERVICE" --region="$REGION" \
  --project="$PROJECT_ID" --member="$IAP_MEMBER" --role=roles/iap.httpsResourceAccessor --quiet >/dev/null
gcloud run services describe "$WEB_SERVICE" --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)"
