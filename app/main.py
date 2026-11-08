import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.renderer import render_html_to_png, render_timeline_payload_to_mp4

RENDERS_DIR = os.environ.get("RENDERS_DIR", "/tmp/bytefyi_renders")
os.makedirs(RENDERS_DIR, exist_ok=True)

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "").strip()

app = FastAPI(
    title="ByteFYI Institutional Video Render Engine",
    description="Cloud-native JSON timeline video rendering microservice (/v1/renders) powered by Pillow + FFmpeg on Google Cloud Run.",
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
        "service": "bytefyi-render-engine",
        "version": "1.0.0",
        "renders_dir": RENDERS_DIR,
    }


@app.post("/v1/renders")
async def create_render(request: Request) -> JSONResponse:
    """
    Render a declarative JSON timeline payload (`{ "source": { ... } }`) into an H.264/AAC MP4 video.
    Renders synchronously within the HTTP request so Cloud Run CPU stays allocated for the full render.
    """
    _cleanup_old_renders()
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    if isinstance(body, list):
        if not body:
            raise HTTPException(status_code=400, detail="Empty payload list")
        body = body[0]

    render_id = str(uuid.uuid4())
    mp4_path = os.path.join(RENDERS_DIR, f"{render_id}.mp4")
    meta_path = os.path.join(RENDERS_DIR, f"{render_id}.json")
    base_url = _resolve_base_url(request)
    video_url = f"{base_url}/renders/{render_id}.mp4"

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
        stats = await asyncio.to_thread(render_timeline_payload_to_mp4, body, mp4_path)
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


def _get_latest_render_meta(request: Request) -> JSONResponse:
    """Return the most recently completed render metadata in RENDERS_DIR."""
    try:
        json_files = [
            os.path.join(RENDERS_DIR, fn)
            for fn in os.listdir(RENDERS_DIR)
            if fn.endswith(".json")
        ]
        json_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for jf in json_files:
            with open(jf) as f:
                meta = json.load(f)
            if meta.get("status") == "succeeded":
                return JSONResponse(content=meta)
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="No completed renders found")


@app.get("/v1/renders")
@app.get("/v1/renders/")
def get_latest_render(request: Request):
    return _get_latest_render_meta(request)


@app.api_route("/v1/renders/{render_id}", methods=["GET", "HEAD"])
def get_render_status(render_id: str, request: Request):
    """
    Retrieve status and download URL for a completed or active render (`GET /v1/renders/{id}`).
    Also streams the MP4 file directly if requested with a `.mp4` suffix.
    """
    if render_id in ("undefined", "null", ""):
        return _get_latest_render_meta(request)
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


@app.api_route("/renders/{render_id}.mp4", methods=["GET", "HEAD"])
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


@app.post("/v1/image")
@app.post("/v1/html-to-image")
@app.post("/api/v1/generateImage")
async def create_html_image(request: Request) -> JSONResponse:
    """
    Render an HTML/CSS snippet into a PNG image (drop-in replacement for HTMLCSSToImg / PDFMunk).
    Returns `image_url` and `url` pointing to `/renders/{id}.png`.
    """
    _cleanup_old_renders()
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    if isinstance(body, list):
        if not body:
            raise HTTPException(status_code=400, detail="Empty payload list")
        body = body[0]

    render_id = str(uuid.uuid4())
    png_path = os.path.join(RENDERS_DIR, f"{render_id}.png")
    base_url = _resolve_base_url(request)
    image_url = f"{base_url}/renders/{render_id}.png"

    try:
        stats = await asyncio.to_thread(render_html_to_png, body, png_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"HTML-to-image render failed: {exc}")

    result = {
        "id": render_id,
        "status": "succeeded",
        "image_url": image_url,
        "url": image_url,
        "output_format": "png",
        "width": stats["width"],
        "height": stats["height"],
        "file_size": stats["file_size"],
        "render_time_seconds": stats["render_time_seconds"],
    }
    return JSONResponse(content=result, status_code=200)


@app.api_route("/renders/{render_id}.png", methods=["GET", "HEAD"])
def serve_rendered_png(render_id: str):
    """Stream the rendered PNG image with proper image/png MIME headers."""
    png_path = os.path.join(RENDERS_DIR, f"{render_id}.png")
    if not os.path.exists(png_path):
        raise HTTPException(status_code=404, detail=f"Image {render_id}.png not found")
    return FileResponse(
        png_path,
        media_type="image/png",
        filename=f"{render_id}.png",
    )

