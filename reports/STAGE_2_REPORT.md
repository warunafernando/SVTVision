# Stage 2 – Canvas – Implementation Report

**Date:** 2026-02-01  
**Reference:** VISION_PIPELINE_CURSOR_IMPLEMENTATION_AND_VALIDATION.md

## Objectives
- Drag/drop nodes
- Wire connections
- Enforce single input rule

## Implementation

### Frontend
| Item | Status | Details |
|------|--------|---------|
| Node Palette | ✔ Done | Sources, Stages, Sinks with fixed items |
| Drag from palette | ✔ Done | Draggable palette items with dataTransfer |
| Drop on canvas | ✔ Done | Canvas dropzone creates node at drop position |
| Node rendering | ✔ Done | Nodes with input/output port circles |
| Wire connections | ✔ Done | MouseDown on output → MouseUp on input creates edge |
| Single input rule | ✔ Done | Connecting to occupied input replaces existing edge |
| VPNode, VPEdge types | ✔ Done | Added to frontend types |

### Palette Items (Fixed for Stage 2)
| Category | Items |
|----------|-------|
| Sources | CameraSource, VideoFileSource, ImageFileSource |
| Stages | preprocess_cpu, detect_apriltag_cpu, overlay |
| Sinks | StreamTap, SaveVideo, SaveImage, SVTVisionOutput |

### Backend
| Item | Status | Details |
|------|--------|---------|
| Single-input validation | ✔ Done | Already in Stage 1 graph_model |
| test_vp_validate_rejects_multiple_inputs_same_port | ✔ Done | API test for single-input rule |

### Tests
| Test | Location | Result |
|------|----------|--------|
| Palette renders Sources, Stages, Sinks | Palette.test.tsx | ✔ PASS |
| Palette renders node types | Palette.test.tsx | ✔ PASS |
| Canvas shows empty hint | PipelineCanvas.test.tsx | ✔ PASS |
| Canvas creates node on drop | PipelineCanvas.test.tsx | ✔ PASS |
| Canvas calls onGraphChange | PipelineCanvas.test.tsx | ✔ PASS |
| API rejects multiple inputs to same port | test_api_vp.py | ✔ PASS |

## Validation
- **Frontend:** 7 tests pass (Palette 4, PipelineCanvas 3)
- **Backend:** 16 tests pass (including single-input validation)
- **Build:** Frontend builds successfully
- **Behavior:** Drag node from palette → drops on canvas → node appears with ports; wire from output to input enforces single-input (replaces existing edge)

## Files Created/Modified
- `frontend/src/types/index.ts` (modified: VPNode, VPEdge)
- `frontend/src/components/vp/Palette.tsx` (new)
- `frontend/src/components/vp/Palette.css` (new)
- `frontend/src/components/vp/PipelineCanvas.tsx` (new)
- `frontend/src/components/vp/PipelineCanvas.css` (new)
- `frontend/src/components/vp/Palette.test.tsx` (new)
- `frontend/src/components/vp/PipelineCanvas.test.tsx` (new)
- `frontend/src/styles/vp/` (new)
- `frontend/src/pages/VisionPipelinePage.tsx` (modified: Palette + Canvas)
- `frontend/src/styles/VisionPipelinePage.css` (modified: vp-content-stage2 layout)
- `frontend/package.json` (modified: vitest, testing-library)
- `frontend/vite.config.ts` (modified: test config)
- `frontend/src/test/setup.ts` (new)
- `backend/tests/test_api_vp.py` (modified: single-input test)

## Next: Stage 3 – Stage Registry
- Backend registry
- Dynamic palette
- Unit tests for discovery
