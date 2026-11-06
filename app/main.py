import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.renderer import render_creatomate_payload_to_mp4

RENDERS_DIR = os.environ.get("RENDERS_DIR", "/tmp/creatomate_renders")
os.makedirs(RENDERS_DIR, exist_ok=True)

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "").strip()

app = FastAPI(
    title="Creatomate-Compatible Institutional Video Renderer",
    description="Drop-in self-hosted replacement for Creatomate (/v1/renders) powered by Pillow + FFmpeg on Google Cloud Run.",
    version="1.0.0",
)


def _resolve_base_url(request: Request) -> str:
    """Resolve external HTTPS base URL on Cloud Run or local dev."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or "localhost:8080"
    return f"{proto}://{host}"


def _cleanup_old_renders(max_age_seconds: int = 7200) -> None:
    """Keep /tmp disk usage bounded by removing renders older than max_age_seconds."""
    now = time.time()
    try:
        for fn in os.listdir(RENDERS_DIR):
            fpath = os.path.join(RENDERS_DIR, fn)
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
                os.unlink(fpath)
    except Exception:
        pass


def _maybe_upload_to_gcs(local_mp4: str, render_id: str) -> Optional[str]:
    """Optionally upload rendered MP4 to Google Cloud Storage if GCS_BUCKET_NAME is configured."""
    if not GCS_BUCKET_NAME:
        return None
    try:
        from google.cloud import storage  # type: ignore

        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob_name = f"renders/{render_id}.mp4"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_mp4, content_type="video/mp4")
        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"
    except Exception as exc:
        print(f"[gcs] Falling back to direct Cloud Run MP4 URL ({exc})")
        return None


@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "creatomate-render-service",
        "version": "1.0.0",
        "renders_dir": RENDERS_DIR,
    }


@app.post("/v1/renders")
async def create_render(request: Request) -> JSONResponse:
    """
    Drop-in replacement for POST https://api.creatomate.com/v1/renders.
    Accepts `{ "source": { ... } }` and renders the MP4 synchronously within ~6-10s
    so Cloud Run CPU stays allocated for the entire render.
    """
    _cleanup_old_renders()
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    # Creatomate sometimes receives a list or single object
    if isinstance(body, list):
        if not body:
            raise HTTPException(status_code=400, detail="Empty payload list")
        body = body[0]

    render_id = str(uuid.uuid4())
    mp4_path = os.path.join(RENDERS_DIR, f"{render_id}.mp4")
    meta_path = os.path.join(RENDERS_DIR, f"{render_id}.json")
    base_url = _resolve_base_url(request)
    video_url = f"{base_url}/renders/{render_id}.mp4"

    # Write initial 'rendering' metadata
    initial_meta = {
        "id": render_id,
        "status": "rendering",
        "url": video_url,
        "output_format": "mp4",
        "render_scale": 1,
    }
    with open(meta_path, "w") as f:
        json.dump(initial_meta, f)

    try:
        stats = render_creatomate_payload_to_mp4(body, mp4_path)
    except Exception as exc:
        failed_meta = {
            "id": render_id,
            "status": "failed",
            "error_message": str(exc),
            "output_format": "mp4",
        }
        with open(meta_path, "w") as f:
            json.dump(failed_meta, f)
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}")

    gcs_url = _maybe_upload_to_gcs(mp4_path, render_id)
    if gcs_url:
        video_url = gcs_url

    final_meta = {
        "id": render_id,
        "status": "succeeded",
        "url": video_url,
        "output_format": "mp4",
        "render_scale": 1,
        "width": stats["width"],
        "height": stats["height"],
        "frame_rate": stats["frame_rate"],
        "duration": stats["duration"],
        "file_size": stats["file_size"],
        "render_time_seconds": stats["render_time_seconds"],
    }
    with open(meta_path, "w") as f:
        json.dump(final_meta, f)

    return JSONResponse(content=final_meta, status_code=200)


@app.get("/v1/renders/{render_id}")
def get_render_status(render_id: str, request: Request):
    """
    Drop-in replacement for GET https://api.creatomate.com/v1/renders/{id}.
    Also serves the MP4 file if requested with a `.mp4` suffix.
    """
    if render_id.endswith(".mp4"):
        clean_id = render_id[:-4]
        return serve_rendered_mp4(clean_id)

    meta_path = os.path.join(RENDERS_DIR, f"{render_id}.json")
    mp4_path = os.path.join(RENDERS_DIR, f"{render_id}.mp4")

    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        return JSONResponse(content=meta)

    if os.path.exists(mp4_path):
        base_url = _resolve_base_url(request)
        return JSONResponse(
            content={
                "id": render_id,
                "status": "succeeded",
                "url": f"{base_url}/renders/{render_id}.mp4",
                "output_format": "mp4",
                "file_size": os.path.getsize(mp4_path),
            }
        )

    raise HTTPException(status_code=404, detail=f"Render {render_id} not found")


@app.get("/renders/{render_id}.mp4")
def serve_rendered_mp4(render_id: str):
    """Stream the rendered MP4 video with proper video/mp4 MIME headers for YouTube & Instagram."""
    mp4_path = os.path.join(RENDERS_DIR, f"{render_id}.mp4")
    if not os.path.exists(mp4_path):
        raise HTTPException(status_code=404, detail=f"Video {render_id}.mp4 not found")
    return FileResponse(
        mp4_path,
        media_type="video/mp4",
        filename=f"{render_id}.mp4",
    )
