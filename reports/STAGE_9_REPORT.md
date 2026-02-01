# Stage 9 – New Stage Workflow – Report

## Summary
Stage 9 (Plugin-based stage addition, Palette auto-update) has been implemented.

## Completed Tasks

### 1. StageRegistry (Backend)
- **File**: `backend/src/plana/domain/stage_registry.py`
- **custom_pipeline_stages.json**: Custom stages persisted in `config/custom_pipeline_stages.json`
- **add_stage(stage_def)**: Register a custom stage; validates id, ports; rejects built-in id override; persists to file
- **remove_stage(stage_id)**: Remove only custom stages; updates file
- **is_custom_stage(stage_id)**: Returns True for plugin-added stages
- **list_stages()**: Now includes `"custom": True` for plugin-added stages
- **_load_custom_stages()**: Loads custom stages on init; **_save_custom_stages()**: Persists on add/remove

### 2. API (Backend)
- **POST /api/vp/stages**: Body = stage definition (id, name, label, type "stage", ports, settings_schema?). Adds custom stage; returns { ok, id }. 400 if invalid or built-in id.
- **DELETE /api/vp/stages/{stage_id}**: Removes custom stage; returns { ok, id }. 400 if not custom or not found.
- **GET /api/vp/stages**: Unchanged; response stages now include `custom: true` for plugin-added stages.

### 3. Frontend – Palette Auto-Update
- **Refresh button**: "↻" in Node Palette header; refetches GET /api/vp/stages and updates palette (Stage 9).
- **addVPStage**, **removeVPStage**: New helpers in `frontend/src/utils/vpApi.ts`.
- **handleSaveNewStage**: Tries addVPStage first; on success refetches palette; on failure falls back to localStorage (offline).
- **handleDeleteCustomStage**: For server custom stages calls removeVPStage then refreshPalette; for local-only removes from localStorage.
- **PaletteItem.custom**: Set from API; used to show delete button and choose server vs local delete.
- **Stages list**: Merges registry stages (built-in + server custom) with localStorage custom stages (no duplicates).

### 4. Unit Tests
- **test_stage_registry.py**: add_stage, add_stage_rejects_builtin_id, remove_stage, is_custom_stage, list_stages_includes_custom_flag (5 new tests).
- **test_api_vp.py**: test_vp_stages_post_add_custom_stage, test_vp_stages_delete_removes_custom_stage (2 new tests).

## Test Results
- 73 backend tests pass (66 existing + 7 new).
- Frontend build succeeds.

## Exit Criteria Met
- [x] Plugin-based stage addition (add_stage, persist, API POST).
- [x] Palette auto-update (Refresh button, refetch; new stage persists to server and appears on refresh).
