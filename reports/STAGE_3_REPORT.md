# Stage 3 – Stage Registry – Report

## Summary
Stage 3 (Stage Registry) has been implemented as specified in `VISION_PIPELINE_CURSOR_IMPLEMENTATION_AND_VALIDATION.md`.

## Completed Tasks

### 1. Backend StageRegistry
- **File**: `backend/src/plana/domain/stage_registry.py`
- **Features**:
  - `StageRegistry` class with `list_stages()`, `list_sources()`, `list_sinks()`, `list_all()`
  - `get_stage(id)`, `get_source(id)`, `get_sink(id)` for lookup
  - Built-in stages: `preprocess_cpu`, `detect_apriltag_cpu`, `overlay_cpu` with ports and `settings_schema`
  - Built-in sources: `camera`, `video_file`, `image_file`
  - Built-in sinks: `stream_tap`, `save_video`, `save_image`, `svt_output`
  - Optional load from `config/pipeline_stages.json` (merge/add stages)
  - Fallback to code defaults when config absent or invalid

### 2. API Integration
- **Updated**: `backend/src/plana/adapters/web_server.py`
  - `GET /api/vp/stages` returns `{ stages, sources, sinks }` from StageRegistry
- **Updated**: `backend/src/plana/app_orchestrator.py`
  - Creates `StageRegistry(config_dir, logger)` and passes to `WebServerAdapter`

### 3. Dynamic Palette (Frontend)
- **Updated**: `frontend/src/components/vp/Palette.tsx`
  - Fetches stages from `GET /api/vp/stages` on mount
  - Maps API response to `PaletteItem` format
  - Falls back to `FALLBACK_ITEMS` when API is unavailable
  - Merges custom stages from `localStorage` with registry stages
- **Updated**: `frontend/src/utils/vpApi.ts`
  - Added `fetchVPStages()`, `VPStagesResponse`, `VPStageMeta`

### 4. Unit Tests
- **File**: `backend/tests/test_stage_registry.py` (11 tests)
  - `test_default_stages`, `test_default_stages_have_ports`
  - `test_default_sources`, `test_default_sinks`
  - `test_stage_registry_list_stages`, `list_sources`, `list_sinks`, `list_all`
  - `test_stage_registry_get_stage`, `get_stage_unknown`
  - `test_stage_registry_load_from_config`
- **Updated**: `backend/tests/test_api_vp.py`
  - `test_vp_stages_returns_registry` – expects `stages`, `sources`, `sinks` with `preprocess_cpu`, `detect_apriltag_cpu`

## Test Results
- Backend: 17 passed
- Frontend: 7 passed (2 skipped)

## Exit Criteria Met
- [x] Backend registry implemented
- [x] Dynamic palette fetches from API
- [x] Unit tests for discovery
