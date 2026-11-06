# n8n Workflow Integration Guide

## Overview

The **AI Stock Advisor V3 – 10 Stock Video** workflow (`h4TSSIs1oARVEuM3`) uses two HTTP Request nodes to render videos:

1. **`Create Video - Creatomate`** (`POST /v1/renders`)
2. **`Check Render Status`** (`GET /v1/renders/{{ $json.id }}`)

Because `creatomate-render-service` is 100% API-compatible with Creatomate, only the **base URL** in those two nodes changes.

---

## Node Configuration in n8n (`h4TSSIs1oARVEuM3`)

### 1. `Create Video - Creatomate`
- **Method**: `POST`
- **URL**: `https://<YOUR-CLOUD-RUN-URL>/v1/renders`
- **Send Body**: `true` (`JSON`)
- **JSON Body**:
  ```javascript
  ={{ JSON.stringify({ source: $json }) }}
  ```
- **Timeout**: `300000` (5 minutes; actual render finishes in ~10–18 seconds)

### 2. `Check Render Status`
- **Method**: `GET`
- **URL**: `=https://<YOUR-CLOUD-RUN-URL>/v1/renders/{{ $json.id }}`

### 3. `Download Video` & `IG Create` (No Changes Needed)
- **`Download Video`** reads `={{ $json.url }}` and downloads the binary `.mp4` (`mimeType: "video/mp4"`) for **YouTube Shorts** (`Upload to YouTube Shorts`).
- **`IG Create`** reads `={{ $json.url }}` and passes it as `video_url` to `graph-video.facebook.com/v23.0/17841404200133843/media` for **Instagram Reels**.
