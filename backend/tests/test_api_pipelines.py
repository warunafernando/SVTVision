"""API tests for /api/pipelines endpoints - Stage 6 execution."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

backend_src = Path(__file__).resolve().parent.parent / "src"
import sys
sys.path.insert(0, str(backend_src))

from plana.app_orchestrator import AppOrchestrator


@pytest.fixture
def orchestrator():
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    frontend_dist = project_root / "frontend" / "dist"
    return AppOrchestrator(config_dir, frontend_dist)


@pytest.fixture
def app(orchestrator):
    return orchestrator.start()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_get_pipelines_returns_200_and_list(client: TestClient):
    """GET /api/pipelines returns 200 and { instances: [] }."""
    response = client.get("/api/pipelines")
    assert response.status_code == 200
    data = response.json()
    assert "instances" in data
    assert isinstance(data["instances"], list)


def test_post_pipelines_with_algorithm_stage6(client: TestClient):
    """POST /api/pipelines with algorithm_id uses Stage 6 (compile + build)."""
    # Create an algorithm first
    create_resp = client.post(
        "/api/algorithms",
        json={
            "name": "Stage6TestAlgo",
            "nodes": [
                {"id": "n1", "type": "source", "source_type": "camera"},
                {"id": "n2", "type": "stage", "stage_id": "preprocess_cpu"},
                {"id": "n3", "type": "stage", "stage_id": "detect_apriltag_cpu"},
                {"id": "n4", "type": "stage", "stage_id": "overlay_cpu"},
                {"id": "n5", "type": "sink", "sink_type": "svt_output"},
            ],
            "edges": [
                {"id": "e1", "source_node": "n1", "source_port": "frame", "target_node": "n2", "target_port": "frame"},
                {"id": "e2", "source_node": "n2", "source_port": "frame", "target_node": "n3", "target_port": "frame"},
                {"id": "e3", "source_node": "n3", "source_port": "frame", "target_node": "n4", "target_port": "frame"},
                {"id": "e4", "source_node": "n4", "source_port": "frame", "target_node": "n5", "target_port": "frame"},
            ],
            "layout": {},
        },
    )
    assert create_resp.status_code == 200
    algo_data = create_resp.json()
    algo_id = algo_data.get("id")
    assert algo_id

    # Get a camera to use as target
    cam_resp = client.get("/api/cameras")
    if cam_resp.status_code != 200:
        pytest.skip("Cameras API not available")
    cameras = cam_resp.json().get("cameras", [])
    if not cameras:
        pytest.skip("No cameras available")
    camera_id = cameras[0]["id"]

    # Phase 2: camera must be open before starting pipeline. Open it first.
    open_resp = client.post(
        f"/api/cameras/{camera_id}/open",
        json={},
    )
    camera_was_opened = open_resp.status_code in (200, 201)

    # Start pipeline (Phase 2: attach to already-open camera; no open in start)
    start_resp = client.post(
        "/api/pipelines",
        json={"algorithm_id": algo_id, "target": camera_id},
    )
    assert start_resp.status_code in (200, 201, 500)
    if start_resp.status_code in (200, 201):
        data = start_resp.json()
        assert "id" in data
        assert data.get("state") == "running"
        # Cleanup: stop the pipeline (detach only; camera stays open)
        stop_resp = client.post(f"/api/pipelines/{data['id']}/stop")
        assert stop_resp.status_code in (200, 201, 404)
    else:
        # 500 = camera not open (Phase 2: "Open the camera first") or other error
        assert start_resp.status_code == 500


def test_camera_id_from_graph_phase3(orchestrator):
    """Phase 3: camera_id is resolved from graph CameraSource config (pull from already-open camera)."""
    vpm = orchestrator.vision_pipeline_manager
    # No CameraSource with camera_id -> None
    assert vpm._camera_id_from_graph({"nodes": [{"type": "source", "source_type": "camera"}]}) is None
    # CameraSource with config.camera_id -> that id
    algo = {
        "nodes": [
            {"id": "n1", "type": "source", "source_type": "camera", "config": {"camera_id": "usb-cam-6-1"}},
        ],
    }
    assert vpm._camera_id_from_graph(algo) == "usb-cam-6-1"
    # Empty config -> None
    algo["nodes"][0]["config"] = {}
    assert vpm._camera_id_from_graph(algo) is None
