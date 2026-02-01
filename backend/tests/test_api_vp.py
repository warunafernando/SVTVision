"""Tests for Vision Pipeline (VP) API stubs - Stage 0."""

import pytest
from fastapi.testclient import TestClient


def test_vp_info_returns_200(client: TestClient):
    """GET /api/vp returns 200 and stub info."""
    response = client.get("/api/vp")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data.get("status") == "skeleton"
    assert "message" in data


def test_vp_stages_returns_registry(client: TestClient):
    """GET /api/vp/stages returns 200 and stages/sources/sinks from StageRegistry (Stage 3)."""
    response = client.get("/api/vp/stages")
    assert response.status_code == 200
    data = response.json()
    assert "stages" in data
    assert "sources" in data
    assert "sinks" in data
    assert isinstance(data["stages"], list)
    assert isinstance(data["sources"], list)
    assert isinstance(data["sinks"], list)
    stage_ids = [s["id"] for s in data["stages"]]
    assert "preprocess_cpu" in stage_ids
    assert "detect_apriltag_cpu" in stage_ids


def test_vp_algorithms_returns_empty_list(client: TestClient):
    """GET /api/vp/algorithms returns 200 and algorithms list (empty stub)."""
    response = client.get("/api/vp/algorithms")
    assert response.status_code == 200
    data = response.json()
    assert "algorithms" in data
    assert isinstance(data["algorithms"], list)


def test_vp_validate_valid_graph(client: TestClient):
    """POST /api/vp/validate accepts valid graph, returns valid=True."""
    response = client.post(
        "/api/vp/validate",
        json={
            "nodes": [
                {"id": "n1", "type": "source", "source_type": "camera"},
                {"id": "n2", "type": "stage", "stage_id": "preprocess_cpu"},
                {"id": "n3", "type": "sink", "sink_type": "stream_tap"},
            ],
            "edges": [
                {"id": "e1", "source_node": "n1", "source_port": "out", "target_node": "n2", "target_port": "in"},
                {"id": "e2", "source_node": "n2", "source_port": "out", "target_node": "n3", "target_port": "in"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_vp_validate_invalid_graph(client: TestClient):
    """POST /api/vp/validate rejects invalid graph (no source), returns valid=False."""
    response = client.post(
        "/api/vp/validate",
        json={
            "nodes": [
                {"id": "n1", "type": "stage"},
                {"id": "n2", "type": "sink"},
            ],
            "edges": [
                {"id": "e1", "source_node": "n1", "source_port": "out", "target_node": "n2", "target_port": "in"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


def test_vp_compile_returns_plan(client: TestClient):
    """POST /api/vp/compile compiles graph and returns execution plan (Stage 5)."""
    response = client.post(
        "/api/vp/compile",
        json={
            "nodes": [
                {"id": "n1", "type": "source", "source_type": "camera"},
                {"id": "n2", "type": "stage", "stage_id": "preprocess_cpu"},
                {"id": "n3", "type": "sink", "sink_type": "svt_output"},
            ],
            "edges": [
                {"id": "e1", "source_node": "n1", "source_port": "frame", "target_node": "n2", "target_port": "frame"},
                {"id": "e2", "source_node": "n2", "source_port": "frame", "target_node": "n3", "target_port": "frame"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert "plan" in data
    plan = data["plan"]
    assert plan["main_path"] == ["n1", "n2", "n3"]
    assert plan["side_taps"] == []


def test_vp_compile_rejects_missing_svt_output(client: TestClient):
    """POST /api/vp/compile returns valid=False when no SVTVisionOutput."""
    response = client.post(
        "/api/vp/compile",
        json={
            "nodes": [
                {"id": "n1", "type": "source", "source_type": "camera"},
                {"id": "n2", "type": "sink", "sink_type": "stream_tap"},
            ],
            "edges": [
                {"id": "e1", "source_node": "n1", "source_port": "frame", "target_node": "n2", "target_port": "frame"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) > 0


def test_vp_validate_rejects_multiple_inputs_same_port(client: TestClient):
    """POST /api/vp/validate rejects graph with multiple inputs to same port (Stage 2 single-input rule)."""
    response = client.post(
        "/api/vp/validate",
        json={
            "nodes": [
                {"id": "n1", "type": "source", "source_type": "camera"},
                {"id": "n2", "type": "source", "source_type": "video_file"},
                {"id": "n3", "type": "stage", "stage_id": "preprocess_cpu"},
            ],
            "edges": [
                {"id": "e1", "source_node": "n1", "source_port": "out", "target_node": "n3", "target_port": "in"},
                {"id": "e2", "source_node": "n2", "source_port": "out", "target_node": "n3", "target_port": "in"},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("2 inputs" in err or "max 1" in err for err in data["errors"])


# --- Stage 9: Plugin-based stage addition ---


def test_vp_stages_post_add_custom_stage(client: TestClient):
    """POST /api/vp/stages adds a custom stage; GET returns it with custom=True."""
    def_ = {
        "id": "custom_test_stage",
        "name": "TestStage",
        "label": "Test Stage",
        "type": "stage",
        "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": [{"name": "frame", "type": "frame"}]},
        "settings_schema": [],
    }
    response = client.post("/api/vp/stages", json=def_)
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("id") == "custom_test_stage"
    get_resp = client.get("/api/vp/stages")
    assert get_resp.status_code == 200
    stages = get_resp.json()["stages"]
    custom = next((s for s in stages if s["id"] == "custom_test_stage"), None)
    assert custom is not None
    assert custom.get("custom") is True


def test_vp_stages_delete_removes_custom_stage(client: TestClient):
    """DELETE /api/vp/stages/{id} removes only custom stages."""
    client.post(
        "/api/vp/stages",
        json={
            "id": "custom_to_remove",
            "name": "ToRemove",
            "type": "stage",
            "ports": {"inputs": [], "outputs": []},
        },
    )
    response = client.delete("/api/vp/stages/custom_to_remove")
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    get_resp = client.get("/api/vp/stages")
    stages = get_resp.json()["stages"]
    assert not any(s["id"] == "custom_to_remove" for s in stages)
    # Cannot remove built-in
    del_resp = client.delete("/api/vp/stages/preprocess_cpu")
    assert del_resp.status_code == 400
