# n8n Workflow Integration Guide

## Overview

The **AI Stock Advisor V3 – 10 Stock Video** workflow (`h4TSSIs1oARVEuM3`) uses two HTTP Request nodes to render videos via `bytefyi-render-engine`:

1. **`Create Video`** (`POST /v1/renders`)
2. **`Check Render Status`** (`GET /v1/renders/{{ $json.id }}`)

---

## Node Configuration in n8n (`h4TSSIs1oARVEuM3`)

### 1. `Create Video` (`POST /v1/renders`)
- **Method**: `POST`
- **URL**: `https://bytefyi-render-engine-427780532217.us-central1.run.app/v1/renders`
- **Send Body**: `true` (`JSON`)
- **JSON Body**:
  ```javascript
  ={{ JSON.stringify({ source: $json }) }}
  ```
- **Timeout**: `300000` (5 minutes; actual render finishes in ~16–65 seconds)

### 2. `Check Render Status` (`GET /v1/renders/{{ $json.id }}`)
- **Method**: `GET`
- **URL**: `=https://bytefyi-render-engine-427780532217.us-central1.run.app/v1/renders/{{ $json.id }}`

### 3. `Download Video` & `IG Create` (No Changes Needed)
- **`Download Video`** reads `={{ $json.url }}` and downloads the binary `.mp4` (`mimeType: "video/mp4"`) for **YouTube Shorts** (`Upload to YouTube Shorts`).
- **`IG Create`** reads `={{ $json.url }}` and passes it as `video_url` to `graph-video.facebook.com/v23.0/17841404200133843/media` for **Instagram Reels**.
