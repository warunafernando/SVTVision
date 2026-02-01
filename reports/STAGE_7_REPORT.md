# Stage 7 – StreamTap – Report

## Summary
Stage 7 (StreamTap – WebSocket streaming) has been implemented.

## Completed Tasks

### 1. StreamTap Class
- **File**: `backend/src/plana/domain/stream_tap.py`
- **StreamTap**: Holds the latest frame from a pipeline node
  - `push_frame(frame)` – update latest frame (called by pipeline)
  - `get_frame()` – get latest frame
  - `get_jpeg()` – get latest frame as JPEG bytes (lazy encoding)
  - `get_metrics()` – tap_id, attach_point, frame_count, has_frame, uptime
- **StreamTapFrame**: Dataclass with frame, timestamp, lazy JPEG encoding
- Thread-safe with lock for concurrent push/get

### 2. StreamTapRegistry
- **File**: `backend/src/plana/domain/stream_tap.py`
- Maps (instance_id, tap_id) → StreamTap
- `register_tap(instance_id, tap)` – register on pipeline start
- `unregister_instance(instance_id)` – cleanup on pipeline stop
- `get_tap(instance_id, tap_id)` – get specific tap
- `list_taps(instance_id)` – list all taps for an instance

### 3. VisionPipeline Integration
- **File**: `backend/src/plana/domain/vision_pipeline.py`
- Added `stream_taps` parameter: Dict[stage_name, List[StreamTap]]
- In `process_frame()`, after each stage, dispatches frame to attached StreamTaps
- Updated `from_stages()` classmethod to accept stream_taps

### 4. Pipeline Builder with Taps
- **File**: `backend/src/plana/domain/pipeline_builder.py`
- New function `build_pipeline_with_taps(plan, nodes, logger)`
- Returns (VisionPipeline, List[StreamTap])
- Creates StreamTap instances for side_taps with sink_type="stream_tap"
- Maps attach_point (node_id) → stage_name for correct wiring

### 5. VisionPipelineManager
- **File**: `backend/src/plana/domain/vision_pipeline_manager.py`
- Uses `build_pipeline_with_taps()` instead of `build_pipeline_from_plan_with_nodes()`
- Registers StreamTaps on pipeline start
- Unregisters StreamTaps on pipeline stop
- New methods: `get_stream_tap()`, `list_stream_taps()`

### 6. WebSocket Endpoint
- **Endpoint**: `ws://.../ws/vp/tap/{instance_id}/{tap_id}`
- Streams frames from a specific StreamTap
- Returns JSON: `{type: "frame", tap_id, instance_id, data (base64), metrics}`
- ~30fps polling

### 7. HTTP API
- **GET /api/vp/taps/{instance_id}** – list all StreamTaps for a pipeline instance

### 8. Unit Tests
- **test_stream_tap.py** (7 tests):
  - push_and_get, jpeg_encoding, metrics
  - registry_register_and_get, registry_unregister, registry_list_taps
  - thread_safety
- **test_pipeline_builder_taps.py** (3 tests):
  - build_with_stream_tap, build_with_multiple_stream_taps, build_no_stream_taps

## Test Results
- 58 backend tests pass (48 existing + 10 new)
- StreamTap correctly holds and encodes frames
- Pipeline correctly dispatches to attached StreamTaps
- Registry properly manages tap lifecycle

## Exit Criteria Met
- [x] WebSocket streaming via StreamTap
- [x] StreamTap attached to pipeline nodes
- [x] Registry for tap management
- [x] Unit tests (including thread safety)
