# Where Camera Outputs Connect to Streaming

This document traces how camera frames get from capture to the WebSocket stream the frontend displays.

## Overview

```
Camera (V4L2) → OpenCV capture → raw_frame_queue → Consumer thread (encode) → frame_queue → WebSocket /ws/stream → Frontend
```

---

## 1. Capture (camera → raw frames)

**File:** `backend/src/plana/domain/camera_service.py`

- **`_capture_loop()`** (single thread for all cameras):
  - Calls `manager.camera_port.capture_frame_raw()` for each open camera (implemented in **`opencv_camera.py`** as `cv2.VideoCapture.read()`).
  - Pushes each raw numpy frame into that camera’s **`raw_frame_queue`** via `manager.enqueue_raw_frame(raw_frame)`.

**File:** `backend/src/plana/domain/camera_manager.py`

- **`raw_frame_queue`**: `queue.Queue(maxsize=1)` — holds the latest raw frame only.
- **`enqueue_raw_frame(raw_frame)`**: Puts the captured frame into `raw_frame_queue` (drops older frame if full).

So: **camera output** is connected to **in-memory raw frames** in each `CameraManager.raw_frame_queue`.

---

## 2. Raw → JPEG and into stream queue

**File:** `backend/src/plana/domain/camera_service.py`

- **`_vision_pipeline_loop()`** (consumer thread):
  - For each open camera: `raw_frame = manager.get_raw_frame(timeout=0.0)` (reads from `raw_frame_queue`).
  - For **stream_only** or **apriltag**: encodes to JPEG (`encode_frame_to_jpeg()` from **`gpu_frame_encoder.py`**), then:
    - **`manager.frame_queue.append(frame_data)`** — this is where camera output is written into the **streaming** queue.

**File:** `backend/src/plana/domain/camera_manager.py`

- **`frame_queue`**: `deque(maxlen=10)` — holds the latest JPEG bytes for streaming (raw stage).
- **`get_latest_frame(stage="raw")`**: Returns `self.frame_queue[-1]` (latest JPEG) when `stage == "raw"`.

So: **camera output** is connected to **streaming** by the consumer loop filling **`CameraManager.frame_queue`** with JPEG bytes.

---

## 3. Streaming: WebSocket reads from `frame_queue`

**File:** `backend/src/plana/adapters/web_server.py`

- **WebSocket endpoint:** `@self.app.websocket("/ws/stream")` (around line 729).
- Query params: `camera`, `stage` (e.g. `raw`).
- Loop:
  - **`frame_data = manager.get_latest_frame(stage)`** — this reads from the same **`frame_queue`** (for `stage="raw"`) or from the vision pipeline’s stage frames (for other stages).
  - Sends JSON to the client: `{"type": "frame", "data": "<base64 JPEG>", "metrics": ..., "detections": ...}`.
  - Sleeps by `1/target_fps` to throttle send rate.

So: **streaming** is connected to **camera output** at this line: **`frame_data = manager.get_latest_frame(stage)`** in **`web_server.py`** (around line 767). That call returns the latest JPEG that was appended to **`manager.frame_queue`** by the consumer thread.

---

## 4. Frontend (stream → UI)

**File:** `frontend/src/components/ViewerPane.tsx`

- Connects to: **`${getWsBaseUrl()}/ws/stream?camera=${selectedCameraId}&stage=${selectedStage}`** (e.g. `stage=raw`).
- On each WebSocket message: decodes base64 `data` and sets it as the image `src` to display the stream.

---

## Summary: connection points

| Step | Location | What connects to what |
|------|----------|------------------------|
| 1 | `camera_service._capture_loop()` | Camera (OpenCV) → `CameraManager.raw_frame_queue` |
| 2 | `camera_service._vision_pipeline_loop()` | `raw_frame_queue` → encode to JPEG → `CameraManager.frame_queue` |
| 3 | `web_server.py` WebSocket `/ws/stream` | **`manager.get_latest_frame(stage)`** → reads **`frame_queue`** → sends to client |
| 4 | `ViewerPane.tsx` | WebSocket URL → receives frames and displays in `<img>` |

So: **camera outputs are connected to streaming** in two places:

1. **Producer side:** when the consumer thread appends JPEG bytes to **`manager.frame_queue`** in **`camera_service._vision_pipeline_loop()`** (and when a vision pipeline is used, pipeline results also feed into what `get_latest_frame(stage)` returns).
2. **Consumer side:** when the **`/ws/stream`** handler in **`web_server.py`** calls **`manager.get_latest_frame(stage)`** and sends that frame over the WebSocket.

For **vision_pipeline** use case, `get_latest_frame(stage)` returns frames from **`VisionPipeline.get_latest_frame(stage)`** (preprocess/detect_overlay, etc.) instead of `frame_queue`; the pipeline is fed from the same `raw_frame_queue` via **`manager.process_vision_pipeline()`** in the same consumer loop.
