from fastapi.testclient import TestClient

from muselens.api import app
from muselens.index import VectorIndex


def test_health_reports_service_status() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["indexed_images"] == 0
    assert isinstance(response.json()["model_loaded"], bool)


def test_empty_library_can_be_searched_without_loading_clip() -> None:
    with TestClient(app) as client:
        app.state.index = VectorIndex()
        response = client.post("/v1/search/text", json={"query": "sunset", "top_k": 5})
    assert response.status_code == 200
    assert response.json() == []
