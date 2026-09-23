#!/usr/bin/env bash
set -euo pipefail

REGION="${REGION:-asia-south1}"
AR_REPOSITORY="${AR_REPOSITORY:-nadid}"
SUPABASE_URL="${SUPABASE_URL:-https://jcyfhfpulckpsdaiecoe.supabase.co}"

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID first}"
: "${SUPABASE_PUBLISHABLE_KEY:?Set SUPABASE_PUBLISHABLE_KEY first}"

gcloud config set project "$GCP_PROJECT_ID" >/dev/null

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com

if ! gcloud artifacts repositories describe "$AR_REPOSITORY" \
  --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Nadid production containers"
fi

for secret in nadid-supabase-service-role nadid-aee-internal-token; do
  if ! gcloud secrets describe "$secret" >/dev/null 2>&1; then
    echo "Missing Secret Manager secret: $secret" >&2
    echo "Create the two secrets before deployment; never place values in GitHub." >&2
    exit 1
  fi
done

RUNTIME_SA="nadid-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$RUNTIME_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create nadid-runtime \
    --display-name="Nadid runtime"
fi

gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --quiet >/dev/null

gcloud builds submit \
  --config deploy/cloudrun/cloudbuild.yaml \
  --substitutions="_REGION=$REGION,_REPOSITORY=$AR_REPOSITORY,_NEXT_PUBLIC_SUPABASE_URL=$SUPABASE_URL,_NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$SUPABASE_PUBLISHABLE_KEY" \
  .

IMAGE_ROOT="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPOSITORY}"

gcloud run deploy nadid-aee \
  --image "${IMAGE_ROOT}/nadid-aee:latest" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --cpu 2 \
  --memory 4Gi \
  --concurrency 2 \
  --timeout 300 \
  --min 0 \
  --max 5 \
  --set-secrets="AEE_INTERNAL_TOKEN=nadid-aee-internal-token:latest"

AEE_URL="$(gcloud run services describe nadid-aee \
  --region "$REGION" \
  --format='value(status.url)')"

gcloud run worker-pools deploy nadid-worker \
  --image "${IMAGE_ROOT}/nadid-worker:latest" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --instances 1 \
  --cpu 1 \
  --memory 1Gi \
  --set-env-vars="SUPABASE_URL=$SUPABASE_URL,AEE_BACKEND_URL=$AEE_URL,WORKER_POLL_INTERVAL_MS=2000,WORKER_MAINTENANCE_INTERVAL_MS=3600000,NADID_STALE_UPLOAD_HOURS=24" \
  --set-secrets="SUPABASE_SERVICE_ROLE_KEY=nadid-supabase-service-role:latest,AEE_INTERNAL_TOKEN=nadid-aee-internal-token:latest"

gcloud run deploy nadid-web \
  --image "${IMAGE_ROOT}/nadid-web:latest" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 1Gi \
  --concurrency 40 \
  --timeout 60 \
  --min 0 \
  --max 20 \
  --set-env-vars="NEXT_PUBLIC_SUPABASE_URL=$SUPABASE_URL,NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=$SUPABASE_PUBLISHABLE_KEY,AEE_BACKEND_URL=$AEE_URL,NADID_MAX_FILE_MB=100,NADID_MAX_UPLOADS_PER_DAY=20,NADID_MAX_ACTIVE_UPLOADS=3" \
  --set-secrets="SUPABASE_SERVICE_ROLE_KEY=nadid-supabase-service-role:latest,AEE_INTERNAL_TOKEN=nadid-aee-internal-token:latest"

WEB_URL="$(gcloud run services describe nadid-web \
  --region "$REGION" \
  --format='value(status.url)')"

echo
echo "Nadid web: $WEB_URL"
echo "Nadid AEE: $AEE_URL"
echo "Check readiness: $WEB_URL/api/health/ready"
