"""Unit tests for StageRegistry discovery."""

import pytest
from pathlib import Path
import tempfile
import json

from plana.domain.stage_registry import StageRegistry, _default_stages, _default_sources, _default_sinks


def test_default_stages():
    """Default stages include preprocess_cpu, detect_apriltag_cpu, overlay_cpu."""
    stages = _default_stages()
    ids = [s["id"] for s in stages]
    assert "preprocess_cpu" in ids
    assert "detect_apriltag_cpu" in ids
    assert "overlay_cpu" in ids


def test_default_stages_have_ports():
    """Each default stage has inputs and outputs."""
    for s in _default_stages():
        assert "ports" in s
        assert "inputs" in s["ports"]
        assert "outputs" in s["ports"]
        assert isinstance(s["ports"]["inputs"], list)
        assert isinstance(s["ports"]["outputs"], list)


def test_default_sources():
    """Default sources include camera, video_file, image_file."""
    sources = _default_sources()
    ids = [s["id"] for s in sources]
    assert "camera" in ids
    assert "video_file" in ids
    assert "image_file" in ids


def test_default_sinks():
    """Default sinks include stream_tap, save_video, svt_output."""
    sinks = _default_sinks()
    ids = [s["id"] for s in sinks]
    assert "stream_tap" in ids
    assert "save_video" in ids
    assert "svt_output" in ids


def test_stage_registry_list_stages(tmp_path):
    """StageRegistry.list_stages returns registered stages."""
    registry = StageRegistry(tmp_path)
    stages = registry.list_stages()
    assert len(stages) >= 3
    stage_ids = [s["id"] for s in stages]
    assert "preprocess_cpu" in stage_ids
    assert "detect_apriltag_cpu" in stage_ids


def test_stage_registry_list_sources(tmp_path):
    """StageRegistry.list_sources returns registered sources."""
    registry = StageRegistry(tmp_path)
    sources = registry.list_sources()
    assert len(sources) >= 3
    assert any(s["id"] == "camera" for s in sources)


def test_stage_registry_list_sinks(tmp_path):
    """StageRegistry.list_sinks returns registered sinks."""
    registry = StageRegistry(tmp_path)
    sinks = registry.list_sinks()
    assert len(sinks) >= 4
    assert any(s["id"] == "stream_tap" for s in sinks)


def test_stage_registry_list_all(tmp_path):
    """StageRegistry.list_all returns stages, sources, sinks."""
    registry = StageRegistry(tmp_path)
    data = registry.list_all()
    assert "stages" in data
    assert "sources" in data
    assert "sinks" in data
    assert len(data["stages"]) >= 3
    assert len(data["sources"]) >= 3
    assert len(data["sinks"]) >= 4


def test_stage_registry_get_stage(tmp_path):
    """StageRegistry.get_stage returns stage by id."""
    registry = StageRegistry(tmp_path)
    stage = registry.get_stage("preprocess_cpu")
    assert stage is not None
    assert stage["id"] == "preprocess_cpu"
    assert "ports" in stage
    assert "settings_schema" in stage


def test_stage_registry_get_stage_unknown(tmp_path):
    """StageRegistry.get_stage returns None for unknown id."""
    registry = StageRegistry(tmp_path)
    assert registry.get_stage("unknown_stage") is None


def test_stage_registry_load_from_config(tmp_path):
    """StageRegistry loads from config file when present."""
    config_file = tmp_path / "pipeline_stages.json"
    config_file.write_text(json.dumps({
        "stages": [
            {"id": "preprocess_cpu", "label": "Custom Preprocess"},
            {"id": "custom_stage", "name": "CustomStage", "label": "Custom", "execution_type": "cpu",
             "type": "stage", "ports": {"inputs": [], "outputs": []}, "settings_schema": []},
        ],
    }))
    registry = StageRegistry(tmp_path)
    stage = registry.get_stage("preprocess_cpu")
    assert stage is not None
    assert stage["label"] == "Custom Preprocess"
    custom = registry.get_stage("custom_stage")
    assert custom is not None
    assert custom["name"] == "CustomStage"


# --- Stage 9: Plugin-based stage addition ---


def test_stage_registry_add_stage(tmp_path):
    """Stage 9: add_stage registers a custom stage and persists to custom_pipeline_stages.json."""
    registry = StageRegistry(tmp_path)
    initial_count = len(registry.list_stages())
    def_ = {
        "id": "custom_my_filter",
        "name": "MyFilter",
        "label": "My Filter",
        "type": "stage",
        "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": [{"name": "frame", "type": "frame"}]},
        "settings_schema": [],
    }
    assert registry.add_stage(def_) is True
    assert len(registry.list_stages()) == initial_count + 1
    stage = registry.get_stage("custom_my_filter")
    assert stage is not None
    assert stage["name"] == "MyFilter"
    stages_list = registry.list_stages()
    custom_stage = next((s for s in stages_list if s["id"] == "custom_my_filter"), None)
    assert custom_stage is not None
    assert custom_stage.get("custom") is True
    assert (tmp_path / "custom_pipeline_stages.json").exists()
    custom_file = json.loads((tmp_path / "custom_pipeline_stages.json").read_text())
    assert len(custom_file["stages"]) == 1
    assert custom_file["stages"][0]["id"] == "custom_my_filter"


def test_stage_registry_add_stage_rejects_builtin_id(tmp_path):
    """Stage 9: add_stage returns False when id conflicts with built-in."""
    registry = StageRegistry(tmp_path)
    def_ = {
        "id": "preprocess_cpu",
        "name": "Override",
        "type": "stage",
        "ports": {"inputs": [], "outputs": []},
    }
    assert registry.add_stage(def_) is False
    assert registry.get_stage("preprocess_cpu")["name"] != "Override"


def test_stage_registry_remove_stage(tmp_path):
    """Stage 9: remove_stage removes only custom stages."""
    registry = StageRegistry(tmp_path)
    registry.add_stage({
        "id": "custom_x",
        "name": "X",
        "type": "stage",
        "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": [{"name": "frame", "type": "frame"}]},
    })
    assert registry.get_stage("custom_x") is not None
    assert registry.remove_stage("custom_x") is True
    assert registry.get_stage("custom_x") is None
    assert registry.remove_stage("preprocess_cpu") is False
    assert registry.get_stage("preprocess_cpu") is not None


def test_stage_registry_is_custom_stage(tmp_path):
    """Stage 9: is_custom_stage returns True only for plugin-added stages."""
    registry = StageRegistry(tmp_path)
    assert registry.is_custom_stage("preprocess_cpu") is False
    registry.add_stage({"id": "custom_y", "name": "Y", "type": "stage", "ports": {"inputs": [], "outputs": []}})
    assert registry.is_custom_stage("custom_y") is True


def test_stage_registry_list_stages_includes_custom_flag(tmp_path):
    """Stage 9: list_stages includes 'custom': True for plugin-added stages."""
    registry = StageRegistry(tmp_path)
    stages = registry.list_stages()
    builtin_ids = {s["id"] for s in _default_stages()}
    for s in stages:
        if s["id"] in builtin_ids:
            assert s.get("custom") is False
        else:
            assert s.get("custom") is True
    registry.add_stage({"id": "custom_z", "name": "Z", "type": "stage", "ports": {"inputs": [], "outputs": []}})
    stages = registry.list_stages()
    custom_z = next((s for s in stages if s["id"] == "custom_z"), None)
    assert custom_z is not None
    assert custom_z.get("custom") is True
