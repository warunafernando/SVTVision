"""Pytest fixtures for SVTVision tests."""

import pytest
from pathlib import Path

import sys
backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.app_orchestrator import AppOrchestrator


@pytest.fixture
def app():
    """Create FastAPI app for testing."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_dir = project_root / "config"
    frontend_dist = project_root / "frontend" / "dist"
    orchestrator = AppOrchestrator(config_dir, frontend_dist)
    return orchestrator.start()


@pytest.fixture
def client(app):
    """Create test client."""
    from fastapi.testclient import TestClient
    return TestClient(app)
