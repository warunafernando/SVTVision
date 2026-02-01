# Stage 8 – SaveVideo / SaveImage – Report

## Summary
Stage 8 (SaveVideo / SaveImage – file output validation) has been implemented.

## Completed Tasks

### 1. SaveVideoSink
- **File**: `backend/src/plana/domain/save_sinks.py`
- Writes frames to a video file (OpenCV VideoWriter)
- `push_frame(frame)` – opens writer on first frame, writes each frame
- `close()` – releases VideoWriter (call when pipeline stops)
- Config: `path` / `output_path`, `fps` (default 30), `fourcc` (default mp4v)
- Thread-safe

### 2. SaveImageSink
- **File**: `backend/src/plana/domain/save_sinks.py`
- Writes frames to image file(s)
- `push_frame(frame)` – writes frame to file
- Modes: `overwrite` (single file) or `sequence` (frame_00001.jpg, …)
- Config: `path` / `output_path`, `mode` (overwrite | sequence)
- `close()` – no-op (each write is independent)

### 3. Pipeline Builder Integration
- **File**: `backend/src/plana/domain/pipeline_builder.py`
- `build_pipeline_with_taps()` now returns `(pipeline, stream_taps, save_sinks)`
- Creates SaveVideoSink / SaveImageSink for side_taps with `sink_type` save_video / save_image
- Config from `plan.node_configs[side_tap.node_id]` (path, fps, mode)
- All side taps (StreamTap + SaveVideo + SaveImage) added to `side_taps_by_stage` and dispatched by VisionPipeline

### 4. VisionPipelineManager
- **File**: `backend/src/plana/domain/vision_pipeline_manager.py`
- Unpacks `(pipeline, stream_taps, save_sinks)` from `build_pipeline_with_taps()`
- Stores `save_sinks` per instance in `_save_sinks`
- On `stop(instance_id)`, calls `close()` on all save sinks for that instance

### 5. Unit Tests
- **test_save_sinks.py** (7 tests):
  - SaveVideo: opens on first frame, close releases writer, file validation (readable with cv2.VideoCapture), ignores empty frame
  - SaveImage: overwrite mode, sequence mode, file validation (readable with cv2.imread)
- **test_pipeline_builder_taps.py**: added `test_build_with_save_video_and_save_image` (Stage 8)

## File Output Validation
- SaveVideo: output file exists, size > 0, cv2.VideoCapture opens and reads frame with correct shape
- SaveImage: output file exists, size > 0, cv2.imread returns valid image with correct shape

## Test Results
- 66 backend tests pass (58 existing + 8 new)
- SaveVideo and SaveImage produce valid, readable files

## Exit Criteria Met
- [x] SaveVideo / SaveImage side taps
- [x] File output validation
- [x] Close on pipeline stop
- [x] Unit tests
