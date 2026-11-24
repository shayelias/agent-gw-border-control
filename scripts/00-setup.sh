#!/usr/bin/env bash
# APIs, the staging bucket, and a local Python environment for the deploy scripts.
source "$(dirname "$0")/lib.sh"
gcloud services enable aiplatform.googleapis.com agentregistry.googleapis.com networkservices.googleapis.com \
  networksecurity.googleapis.com iap.googleapis.com iamcredentials.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudresourcemanager.googleapis.com logging.googleapis.com --project="$PROJECT_ID"
gcloud storage buckets create "$STAGING_BUCKET" --project="$PROJECT_ID" --location="$REGION" 2>/dev/null || true
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements-dev.txt"
