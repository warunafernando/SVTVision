# Plan: Camera Manager Outside Vision Pipeline

## Goal

1. **Cameras are opened by a central camera manager** (outside the vision pipeline), based on config and discovery.
2. **Use-case at open time**: If a camera is assigned **apriltag** use case, open it with **Y plane only (grayscale)** for efficiency; no color needed.
3. **Vision pipeline camera source** only **pulls frames from already-opened cameras**; it does not open or close cameras. Run Pipeline attaches a pipeline to an existing camera; Stop Pipeline detaches only (camera stays open).

---

## Current Behavior (Summary)

| Component | Current behavior |
|-----------|------------------|
| **Camera open** | Cameras are opened by: (a) POST `/api/cameras/{id}/open` (manual), (b) VisionPipelineManager.start() when user runs a pipeline (open_camera with vision_pipeline), (c) _auto_start_cameras() at app startup (open_camera without vision_pipeline, using config resolution). |
| **use_case** | Stored in per-camera config; values in API: `stream_only`, `vision_pipeline`. Code also references `apriltag` (e.g. capture loop uses `use_case == 'apriltag'` for grayscale path) but apriltag is not in the settings API’s valid list. |
| **Vision pipeline** | When user runs a pipeline, we call open_camera(camera_id, device_path, vision_pipeline=vision_pipeline). That opens the device (or closes and reopens if already open) and attaches the pipeline. When user stops the pipeline, we close_camera(camera_id) and unregister StreamTaps. So **pipeline start = open camera**, **pipeline stop = close camera**. |
| **Frame flow** | Single capture thread in CameraService captures raw frames for all open managers; if manager has vision_pipeline and use_case in ('apriltag','vision_pipeline'), frame is enqueued to manager’s raw_frame_queue; vision pipeline thread processes that queue through manager.vision_pipeline. |
| **Apriltag efficiency** | Today we still capture BGR and convert to gray in process_vision_pipeline or in the capture path for stream_only apriltag. No Y-only open. |

---

## Target Behavior

| Area | Target behavior |
|------|------------------|
| **Who opens cameras** | **Camera manager / app startup** (and optional manual open). Discovery + config drive which cameras to open and with which use_case. Vision pipeline never opens or closes devices. |
| **use_case at open** | **apriltag**: open with grayscale-only path (Y plane only; no color). **stream_only** / **vision_pipeline**: open for color (stream or future pipeline attach). Config and API should support `apriltag`, `stream_only`, `vision_pipeline`. |
| **Vision pipeline start** | **Attach only.** Check camera is already open; if not, return error “Open the camera first”. If open, attach the built VisionPipeline to the existing CameraManager (set manager.vision_pipeline and use_case = 'vision_pipeline'), register StreamTaps, and return instance_id. No open_camera() from pipeline start. |
| **Vision pipeline stop** | **Detach only.** Unregister StreamTaps, clear manager.vision_pipeline (and restore use_case if desired). Do **not** close the camera. |
| **Camera source in pipeline** | Graph’s CameraSource node is bound to a camera_id (e.g. from node config). At runtime, frames are **pulled from the already-opened** CameraManager for that camera_id. No open/close in pipeline code. |

---

## Implementation Plan (Phased)

### Phase 1: Central open with use_case and apriltag = Y-only

**1.1 Config and API**

- **Per-camera use_case**  
  - Ensure each camera can have a persisted `use_case` in config (e.g. in `config/cameras/{camera_id}.json` or from cameras.json).  
  - Values: `apriltag` | `stream_only` | `vision_pipeline`.  
  - If missing, default to `stream_only`.

- **Settings API**  
  - Allow `use_case` to be set/read in detector-config or a dedicated settings endpoint; valid list: `['apriltag', 'stream_only', 'vision_pipeline']`.

**1.2 Open logic (CameraService.open_camera)**

- **Input**: camera_id, device_path, resolution (optional), **use_case** (optional; if omitted, read from camera config).
- **Remove**: “open with vision_pipeline” from open_camera signature for pipeline start (Phase 2). For Phase 1, keep backward compatibility or add a separate “open for pipeline” path that still uses use_case from config.
- **Apriltag (use_case == 'apriltag')**:  
  - **Option A (preferred for “Y plane only”)**: In OpenCVCameraAdapter, when use_case is apriltag, try to set a grayscale format (e.g. V4L2 pixel format GREY / `cv2.CAP_PROP_FOURCC` or equivalent) if the driver supports it; otherwise open as now and convert to grayscale in the capture path only (no color frames downstream).  
  - **Option B (simpler)**: Keep current open format (e.g. YUYV/MJPG); in the capture path for this manager, convert to grayscale immediately and only enqueue gray frames (saves bandwidth/memory downstream, not at device).  
  - Document: “Apriltag use_case: open with Y plane only (grayscale). If driver supports GREY, use it; else capture and convert to gray in capture path.”

**1.3 Auto-start and manual open**

- **_auto_start_cameras()**  
  - For each camera that has config (e.g. resolution) and is to be auto-started: call open_camera(camera_id, device_path, resolution_from_config, **use_case_from_config**).  
  - No vision_pipeline passed; use_case comes from config (apriltag → Y-only open/path, stream_only/vision_pipeline → color).

- **POST /api/cameras/{id}/open**  
  - Same idea: open with config resolution and **use_case from config** (or optional body field). No pipeline attached yet.

**1.4 Capture path**

- For managers with use_case **apriltag**: ensure the capture thread only ever passes grayscale frames into the pipeline/queue (either device is opened as gray or we convert once and only push gray). No color path for apriltag.

---

### Phase 2: Vision pipeline only attaches to already-open cameras

**2.1 VisionPipelineManager.start(algorithm_id, target_camera_id)**

- **Do not** call camera_service.open_camera.
- **Do**:
  1. Resolve device_path and algorithm as today (for validation).
  2. **If not** camera_service.is_camera_open(target_camera_id): return (None, "Open the camera first. Use Cameras page or ensure auto_start_cameras and camera config.").
  3. Get manager = camera_service.get_camera_manager(target_camera_id).
  4. Build VisionPipeline + StreamTaps + save_sinks as today.
  5. **Attach**: set manager.vision_pipeline = built pipeline, manager.use_case = 'vision_pipeline' (if not already).
  6. Register StreamTaps in stream_tap_registry; store save_sinks in _save_sinks[target_camera_id]; add/update _instances[target_camera_id].
  7. Return (target_camera_id, None).

**2.2 VisionPipelineManager.stop(instance_id)**

- **Do not** call camera_service.close_camera(instance_id).
- **Do**: Unregister StreamTaps, clear _save_sinks for instance_id (and close save sinks), set _instances[instance_id].state = 'stopped' and manager.vision_pipeline = None (and optionally manager.use_case back to config default). Camera remains open.

**2.3 CameraService**

- Remove the “reopen with vision_pipeline” path from open_camera (no longer open from pipeline start). Optionally add a method `attach_vision_pipeline(camera_id, vision_pipeline)` used by VisionPipelineManager, or keep attachment as a direct set on the manager from VisionPipelineManager.

**2.4 Capture / vision pipeline thread**

- No change to flow: managers that have vision_pipeline and use_case == 'vision_pipeline' are already processed by the vision pipeline thread. We only changed how the pipeline gets onto the manager (attach vs open with pipeline).

---

### Phase 3: Camera source in pipeline = pull from open camera ✅ Implemented

**3.1 Semantics**

- The graph’s **CameraSource** node has config (e.g. `camera_id`). At **run** time, the “source” of frames for that pipeline instance is the **already-opened** CameraManager for that camera_id.
- **Implemented:** When starting a pipeline, the camera to attach to is resolved from the graph: if the algorithm has a CameraSource node with `config.camera_id`, that camera_id is used (so the pipeline pulls from that already-open camera); otherwise the Run target (UI-selected camera) is used. One pipeline instance = one camera (one CameraSource, one target).

**3.2 Optional: multi-camera graphs**

- If later the graph has multiple CameraSource nodes with different camera_ids, then “start pipeline” would need to bind to multiple cameras (e.g. open all required cameras first, then attach one pipeline that pulls from several managers). For this plan, assume **one pipeline instance = one camera** (one CameraSource, one target). Multi-camera can be a follow-up.

---

## File / Component Checklist

| Item | Action |
|------|--------|
| **Config (cameras.json / per-camera JSON)** | Add or document `use_case` (apriltag | stream_only | vision_pipeline). |
| **CameraConfigService** | Read/write use_case; default stream_only. |
| **Web server (settings)** | Allow use_case in valid list including apriltag. |
| **OpenCVCameraAdapter** | Support “grayscale only” for apriltag: GREY format if supported, else convert in capture path. |
| **CameraService.open_camera** | Take use_case from config or param; no vision_pipeline param for “pipeline start” path (Phase 2). |
| **CameraService** | Optional: add attach_vision_pipeline(camera_id, pipeline) or keep attachment in VisionPipelineManager. |
| **AppOrchestrator._auto_start_cameras** | Pass use_case from config when opening. |
| **VisionPipelineManager.start** | Require camera already open; attach pipeline only; do not call open_camera. |
| **VisionPipelineManager.stop** | Detach pipeline only; do not call close_camera. |
| **CameraManager** | Allow setting vision_pipeline and use_case after open (already possible today). |

---

## Testing and Rollback

- **Tests**: Update tests that start/stop pipelines to open the camera first (or mock is_camera_open), and assert stop does not close the camera.
- **Backward compatibility**: If auto_start_cameras is true and config has resolution, cameras open at startup with use_case from config. If a user runs a pipeline without opening the camera first, they get a clear error: “Open the camera first.”
- **Rollback**: Revert VisionPipelineManager to call open_camera/close_camera on start/stop; revert open_camera to accept vision_pipeline and reopen logic; keep use_case and apriltag Y-only as an optional improvement.

---

## Summary

1. **Central camera manager** opens cameras at startup (and/or manual open) using config: **use_case** (apriltag | stream_only | vision_pipeline).
2. **Apriltag use case**: open with **Y plane only** (grayscale format if supported, else convert in capture path).
3. **Vision pipeline**: **Camera source only pulls from already-opened cameras.** Start = attach pipeline to open camera; Stop = detach only. No open/close in pipeline start/stop.

This keeps camera lifecycle and efficiency (apriltag = gray) in one place and makes the vision pipeline a pure consumer of existing camera streams.
