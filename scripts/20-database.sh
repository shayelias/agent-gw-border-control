#!/usr/bin/env bash
# Cloud SQL (MySQL), the Agent 2 database user, its password in Secret Manager, and the demo table.
source "$(dirname "$0")/lib.sh"
umask 077
ROOT_PW="$(openssl rand -base64 24)"; APP_PW="$(openssl rand -base64 24)"
gcloud sql instances create "$SQL_INSTANCE" --project="$PROJECT_ID" --region="$REGION" \
  --database-version=MYSQL_8_0 --edition=ENTERPRISE --tier=db-f1-micro --root-password="$ROOT_PW"
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT_ID"
gcloud sql users create "$DB_USER" --host=% --instance="$SQL_INSTANCE" --project="$PROJECT_ID" --password="$APP_PW"
printf %s "$ROOT_PW" | gcloud secrets create "$SQL_INSTANCE-root-password" --project="$PROJECT_ID" \
  --replication-policy=automatic --data-file=-
printf %s "$APP_PW" | gcloud secrets create "$DB_SECRET" --project="$PROJECT_ID" \
  --replication-policy=automatic --data-file=-
unset ROOT_PW APP_PW
"$PY" "$ROOT/sql/init_db.py"
echo "Note: Cloud SQL gives API-created users the cloudsqlsuperuser role. Revoke it from $DB_USER for least privilege."
