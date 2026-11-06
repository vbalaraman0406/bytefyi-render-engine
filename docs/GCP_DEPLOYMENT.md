# Google Cloud Run Deployment Guide

## 1. Prerequisites

- **Google Cloud Project**: `vish-cloud`
- **Service Name**: `bytefyi-render-engine`
- **Region**: `us-central1`

---

## 2. Deployment Command

Deploy directly from source using Google Cloud Build and Cloud Run:

```bash
gcloud run deploy bytefyi-render-engine \
  --source . \
  --project vish-cloud \
  --region us-central1 \
  --allow-unauthenticated \
  --cpu 2 \
  --memory 2Gi \
  --timeout 300 \
  --max-instances 1 \
  --quiet
```

### Resource & Scaling Flags Explained
| Flag | Value | Purpose |
| :--- | :--- | :--- |
| `--cpu` | `2` | Allocates 2 vCPUs for fast FFmpeg `libx264` encoding. |
| `--memory` | `2Gi` | Provides ample RAM for `1080×1920` RGB frame buffers and `/tmp` MP4 storage. |
| `--timeout` | `300` | Allows up to 5 minutes per synchronous render request. |
| `--max-instances` | `1` | Ensures `POST /v1/renders`, `GET /v1/renders/{id}`, and `GET /renders/{id}.mp4` hit the same container instance holding `/tmp/bytefyi_renders/{id}.mp4`. |
| `--allow-unauthenticated` | enabled | Allows n8n Cloud and Instagram's Graph API (`video_url` crawler) to fetch the rendered `.mp4` over HTTPS. |

---

## 3. Verifying the Deployed Service

- **Production Cloud Run Service URL**: `https://bytefyi-render-engine-427780532217.us-central1.run.app`

```bash
# 1. Health check
curl -sS https://bytefyi-render-engine-427780532217.us-central1.run.app/health

# 2. Trigger a test render
curl -sS -X POST https://bytefyi-render-engine-427780532217.us-central1.run.app/v1/renders \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/execution_6550_payload.json
```
