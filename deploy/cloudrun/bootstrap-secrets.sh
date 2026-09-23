#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID first}"

gcloud config set project "$GCP_PROJECT_ID" >/dev/null
gcloud services enable secretmanager.googleapis.com

read -rsp "Supabase service_role key: " SUPABASE_SERVICE_ROLE_KEY
echo
read -rsp "AEE internal token (press Enter to generate): " AEE_INTERNAL_TOKEN
echo

if [[ -z "$AEE_INTERNAL_TOKEN" ]]; then
  AEE_INTERNAL_TOKEN="$(openssl rand -hex 32)"
fi

for secret in nadid-supabase-service-role nadid-aee-internal-token; do
  if ! gcloud secrets describe "$secret" >/dev/null 2>&1; then
    gcloud secrets create "$secret" --replication-policy=automatic
  fi
done

printf '%s' "$SUPABASE_SERVICE_ROLE_KEY" | \
  gcloud secrets versions add nadid-supabase-service-role --data-file=-

printf '%s' "$AEE_INTERNAL_TOKEN" | \
  gcloud secrets versions add nadid-aee-internal-token --data-file=-

unset SUPABASE_SERVICE_ROLE_KEY
unset AEE_INTERNAL_TOKEN

echo "Secrets stored in Google Secret Manager."
