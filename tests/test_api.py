import json
import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "bytefyi-render-engine"


def test_full_timeline_render_and_status_flow():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "execution_6550_payload.json")
    with open(fixture_path) as f:
        payload = json.load(f)

    # Test with a short 3-second subset for fast unit test verification
    short_payload = {
        "source": {
            "output_format": "mp4",
            "width": 1080,
            "height": 1920,
            "frame_rate": 30,
            "duration": 3.0,
            "elements": [
                el
                for el in payload["source"]["elements"]
                if el.get("type") != "audio" and float(el.get("time") or 0) < 3.0
            ],
        }
    }

    post_resp = client.post(
        "/v1/renders",
        json=short_payload,
        headers={"Authorization": "Bearer test-token"},
    )
    assert post_resp.status_code == 200
    render_meta = post_resp.json()
    assert render_meta["status"] == "succeeded"
    assert render_meta["output_format"] == "mp4"
    assert render_meta["width"] == 1080
    assert render_meta["height"] == 1920
    render_id = render_meta["id"]

    # Poll GET /v1/renders/{id}
    status_resp = client.get(f"/v1/renders/{render_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["id"] == render_id
    assert status_data["status"] == "succeeded"

    # Verify HEAD and GET on /renders/{id}.mp4
    head_resp = client.head(f"/renders/{render_id}.mp4")
    assert head_resp.status_code == 200
    assert head_resp.headers["content-type"] == "video/mp4"

    mp4_resp = client.get(f"/renders/{render_id}.mp4")
    assert mp4_resp.status_code == 200
    assert mp4_resp.headers["content-type"] == "video/mp4"
    assert len(mp4_resp.content) > 10000
