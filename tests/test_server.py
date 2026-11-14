"""伺服器端點測試（不載入 torch，只驗證 API 骨架）。"""

from fastapi.testclient import TestClient

from opengovideo.server import create_app


def test_health_and_models():
    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        payload = health.json()
        assert payload["status"] == "ok"
        assert payload["models_loaded"] == []
        assert "jobs" in payload

        models = client.get("/models").json()
        keys = {item["key"] for item in models["models"]}
        assert {"animatediff-v1.5", "svd-xt"} <= keys
        assert models["defaults"]["text2video"] == "animatediff-v1.5"


def test_unknown_job_returns_404():
    with TestClient(create_app()) as client:
        assert client.get("/jobs/not-a-job").status_code == 404


def test_invalid_model_is_rejected():
    with TestClient(create_app()) as client:
        response = client.post("/jobs/text2video", json={"prompt": "test", "model": "nope"})
        assert response.status_code == 400


def test_image_request_requires_single_source():
    with TestClient(create_app()) as client:
        response = client.post("/jobs/image2video", json={})
        assert response.status_code == 400
