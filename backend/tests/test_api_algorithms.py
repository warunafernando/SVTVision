"""API tests for /api/algorithms CRUD."""

import pytest
from fastapi.testclient import TestClient

import sys
from pathlib import Path
backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))


def test_list_algorithms_empty(client: TestClient):
    """GET /api/algorithms returns 200 and algorithms list."""
    response = client.get("/api/algorithms")
    assert response.status_code == 200
    data = response.json()
    assert "algorithms" in data
    assert isinstance(data["algorithms"], list)


def test_create_and_get_algorithm(client: TestClient):
    """POST /api/algorithms creates, GET returns it."""
    create_resp = client.post(
        "/api/algorithms",
        json={
            "name": "AprilTag Pipeline",
            "nodes": [{"id": "n1", "type": "source", "source_type": "camera"}],
            "edges": [],
            "layout": {"n1": {"x": 50, "y": 50}},
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert "id" in created
    assert created["name"] == "AprilTag Pipeline"

    get_resp = client.get(f"/api/algorithms/{created['id']}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["name"] == "AprilTag Pipeline"
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "n1"
    assert data["layout"]["n1"] == {"x": 50, "y": 50}


def test_update_algorithm(client: TestClient):
    """PUT /api/algorithms/{id} updates algorithm."""
    create_resp = client.post(
        "/api/algorithms",
        json={"name": "Original", "nodes": [], "edges": [], "layout": {}},
    )
    assert create_resp.status_code == 200
    algo_id = create_resp.json()["id"]

    update_resp = client.put(
        f"/api/algorithms/{algo_id}",
        json={"name": "Updated", "nodes": [{"id": "n1"}], "edges": [], "layout": {}},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated"

    data = client.get(f"/api/algorithms/{algo_id}").json()
    assert data["name"] == "Updated"
    assert len(data["nodes"]) == 1


def test_delete_algorithm(client: TestClient):
    """DELETE /api/algorithms/{id} removes algorithm."""
    create_resp = client.post(
        "/api/algorithms",
        json={"name": "ToDelete", "nodes": [], "edges": [], "layout": {}},
    )
    algo_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/api/algorithms/{algo_id}")
    assert delete_resp.status_code == 200

    get_resp = client.get(f"/api/algorithms/{algo_id}")
    assert get_resp.status_code == 404
