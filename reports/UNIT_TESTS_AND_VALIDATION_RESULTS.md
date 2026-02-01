# Unit Tests and Validation Results

**Date:** 2026-02-01  
**Project:** SVTVision – Vision Pipeline Implementation

---

## Test Run Summary

| Metric | Result |
|--------|--------|
| **Backend Tests** | 16 passed |
| **Frontend Tests** | 7 passed |
| **Backend Test Failures** | 0 |
| **Frontend Build** | Success |
| **Overall Status** | PASS |

---

## Backend Unit Tests (pytest)

### test_api_vp.py – Vision Pipeline API Stubs (Stage 0)
| Test | Result | Description |
|------|--------|-------------|
| test_vp_info_returns_200 | PASS | GET /api/vp returns stub info |
| test_vp_stages_returns_empty_list | PASS | GET /api/vp/stages returns empty list |
| test_vp_algorithms_returns_empty_list | PASS | GET /api/vp/algorithms returns empty list |
| test_vp_validate_valid_graph | PASS | POST /api/vp/validate accepts valid graph |
| test_vp_validate_invalid_graph | PASS | POST /api/vp/validate rejects invalid graph |
| test_vp_validate_rejects_multiple_inputs_same_port | PASS | Rejects multiple inputs to same port (Stage 2) |

### test_graph_model.py – Graph Model (Stage 1)
| Test | Result | Description |
|------|--------|-------------|
| test_valid_dag_passes | PASS | Valid DAG (linear chain) passes |
| test_cycle_detected | PASS | Cycle detected in graph |
| test_single_source_valid | PASS | Exactly one source, all reachable |
| test_no_source_fails | PASS | No source node fails validation |
| test_multiple_sources_fails | PASS | Multiple sources fail validation |
| test_unreachable_node_fails | PASS | Unreachable node fails validation |
| test_single_input_per_port_valid | PASS | One input per port passes |
| test_multiple_inputs_same_port_fails | PASS | Multiple inputs to same port fails |
| test_validate_graph_valid_passes | PASS | Full validation passes for valid graph |
| test_validate_graph_invalid_raises | PASS | GraphValidationError raised for invalid graph |

---

### Palette.test.tsx – Node Palette (Stage 2)
| Test | Result | Description |
|------|--------|-------------|
| renders Sources, Stages, Sinks | PASS | Palette sections visible |
| renders CameraSource, VideoFileSource, ImageFileSource | PASS | Source nodes listed |
| renders preprocess_cpu and detect_apriltag_cpu | PASS | Stage nodes listed |
| renders StreamTap, SaveVideo, SaveImage, SVTVisionOutput | PASS | Sink nodes listed |

### PipelineCanvas.test.tsx – Canvas (Stage 2)
| Test | Result | Description |
|------|--------|-------------|
| shows empty hint when no nodes | PASS | Placeholder text visible |
| creates node on drop from palette | PASS | Drop creates node |
| calls onGraphChange when nodes change | PASS | Callback invoked |

## Validation Checks

### Stage 0 – Skeleton
- [x] `/vision-pipeline` UI route exists
- [x] Backend `/api/vp` stubs respond
- [x] GET /api/vp returns 200
- [x] GET /api/vp/stages returns 200
- [x] GET /api/vp/algorithms returns 200

### Stage 2 – Canvas
- [x] Drag/drop nodes from palette
- [x] Wire connections (output port → input port)
- [x] Single input rule (replace existing edge)
- [x] Palette: Sources, Stages, Sinks
- [x] Canvas: nodes with ports

### Stage 1 – Graph Model
- [x] Graph data structures (GraphNode, GraphEdge, PipelineGraph)
- [x] DAG validation (no cycles)
- [x] Single-source validation
- [x] Single-input-per-port validation
- [x] POST /api/vp/validate accepts valid graph
- [x] POST /api/vp/validate rejects invalid graph with errors

### Build
- [x] Frontend builds successfully (vite build)
- [x] Backend tests run (pytest)

---

## Command Reference

```bash
# Run backend unit tests
cd /home/svt/FRC/SVTVision
PYTHONPATH=backend/src python -m pytest backend/tests/ -v --tb=short

# Build frontend
cd frontend && npm run build
```

---

## Raw Test Output (Last Run)

```
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.0.2, pluggy-1.6.0
plugins: anyio-4.12.1
collected 15 items

backend/tests/test_api_vp.py::test_vp_info_returns_200 PASSED
backend/tests/test_api_vp.py::test_vp_stages_returns_empty_list PASSED
backend/tests/test_api_vp.py::test_vp_algorithms_returns_empty_list PASSED
backend/tests/test_api_vp.py::test_vp_validate_valid_graph PASSED
backend/tests/test_api_vp.py::test_vp_validate_invalid_graph PASSED
backend/tests/test_graph_model.py::test_valid_dag_passes PASSED
backend/tests/test_graph_model.py::test_cycle_detected PASSED
backend/tests/test_graph_model.py::test_single_source_valid PASSED
backend/tests/test_graph_model.py::test_no_source_fails PASSED
backend/tests/test_graph_model.py::test_multiple_sources_fails PASSED
backend/tests/test_graph_model.py::test_unreachable_node_fails PASSED
backend/tests/test_graph_model.py::test_single_input_per_port_valid PASSED
backend/tests/test_graph_model.py::test_multiple_inputs_same_port_fails PASSED
backend/tests/test_graph_model.py::test_validate_graph_valid_passes PASSED
backend/tests/test_graph_model.py::test_validate_graph_invalid_raises PASSED

======================== 16 passed, 6 warnings =========================

Frontend:
  Palette.test.tsx: 4 passed
  PipelineCanvas.test.tsx: 3 passed
  Total: 7 passed
```

---

*Generated by SVTVision validation pipeline*
