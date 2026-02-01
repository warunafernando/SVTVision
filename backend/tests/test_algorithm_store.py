"""Unit tests for AlgorithmStore."""

import pytest
import tempfile
from pathlib import Path
import sys
backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.domain.algorithm_store import AlgorithmStore


@pytest.fixture
def tmp_config():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_save_and_list(tmp_config):
    store = AlgorithmStore(tmp_config)
    algo_id = store.save(None, "MyPipeline", [{"id": "n1"}], [{"id": "e1"}], {"n1": {"x": 10, "y": 20}})
    assert algo_id
    items = store.list_all()
    assert len(items) == 1
    assert items[0]["name"] == "MyPipeline"
    assert items[0]["id"] == algo_id


def test_get(tmp_config):
    store = AlgorithmStore(tmp_config)
    store.save(None, "Test", [{"id": "n1"}], [], {})
    items = store.list_all()
    algo_id = items[0]["id"]
    data = store.get(algo_id)
    assert data is not None
    assert data["name"] == "Test"
    assert data["nodes"] == [{"id": "n1"}]
    assert data["edges"] == []


def test_update(tmp_config):
    store = AlgorithmStore(tmp_config)
    algo_id = store.save(None, "Original", [{"id": "n1"}], [], {})
    store.save(algo_id, "Updated", [{"id": "n1"}, {"id": "n2"}], [], {})
    data = store.get(algo_id)
    assert data["name"] == "Updated"
    assert len(data["nodes"]) == 2


def test_delete(tmp_config):
    store = AlgorithmStore(tmp_config)
    algo_id = store.save(None, "ToDelete", [{"id": "n1"}], [], {})
    assert store.delete(algo_id) is True
    assert store.get(algo_id) is None
    assert store.delete(algo_id) is False
