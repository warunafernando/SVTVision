# Plan: AprilTag Detection Pipeline with Maximum GPU Use (Two Cameras)

**Scope:** Plan only — no implementation. Goal: run AprilTag detection for two cameras with as much work as possible on GPU, in the most efficient way.

**Constraints:** (1) We already have the camera manager; all video must come from the existing CameraService + CameraManager flow. (2) **What runs on GPU vs CPU** is made explicit in §2. (3) **Every pipeline step** must expose a **viewable debug frame** that shows **both cameras together** (e.g. side-by-side) for debugging (§3) and an **FPS counter** (§4). (4) The **AprilTag page** must provide **Start/Stop** buttons, **settings** for the algorithm, and a **view of the frames** (debug frames per step) (§5).

---

## 0. Video from the Existing Camera Manager (Do Not Replace)

Video is supplied **only** by the current camera stack:

- **CameraService** holds one **CameraManager** per open camera and runs:
  - **One capture thread:** Round-robins all open cameras; for each, calls `manager.camera_port.capture_frame_raw()` and pushes the raw frame with `manager.enqueue_raw_frame(raw_frame)` into that manager’s **`raw_frame_queue`** (maxsize=1).
  - **One consumer thread** (`_vision_pipeline_loop`): For the AprilTag two-camera design, each iteration gets **two images from the queues of the camera manager (one for each camera)** and processes both **in parallel** through the entire pipeline till the end (see §7–8). Today it round-robins; for each manager either:
    - **With pipeline attached:** Calls `manager.process_vision_pipeline()`, which gets one frame from **`manager.get_raw_frame(timeout=0.0)`** (i.e. from that manager’s `raw_frame_queue`), runs the vision pipeline, and pushes result JPEG into **`manager.frame_queue`** and updates pipeline stage buffers and detections.
    - **Without pipeline (stream_only / apriltag today):** Gets one frame with `manager.get_raw_frame(timeout=0.0)`, encodes to JPEG (e.g. GPU nvJPEG), and appends to **`manager.frame_queue`**.

- **CameraManager** (per camera) owns:
  - **`raw_frame_queue`** — filled by capture thread, drained by consumer (or by `process_vision_pipeline()` inside the consumer).
  - **`frame_queue`** — filled by consumer with JPEG bytes for streaming; read by WebSocket/API via `manager.get_latest_frame(stage)`.
  - **`vision_pipeline`** — optional; when set, `process_vision_pipeline()` runs: get raw from `get_raw_frame()` → pipeline.process_frame() → write to `frame_queue` and pipeline stage/detection state.

**Plan principle:** The AprilTag GPU pipeline **gets its input from the camera manager** (via `manager.get_raw_frame()` in the existing consumer loop and inside `process_vision_pipeline()`). No new capture paths, no new queues for “video in.” Changes are limited to: (1) each iteration, get **two images from the camera manager queues (one for each camera)** and (2) put those two **in parallel through the entire process till the end** (preprocess → detect → overlay → encode), then write each result to the corresponding manager's `frame_queue` and detections. The pipeline uses GPU stages (preprocess_gpu, detect_apriltag_gpu, etc.) where possible.

---

## 1. Current State Summary

| Stage | Current | GPU today? |
|-------|---------|------------|
| **Capture** | OpenCV `VideoCapture.read()` per camera | No (CPU) |
| **Raw → grayscale (AprilTag path)** | In consumer: CuPy BGR→Y when encoding for stream | Yes (CuPy) for stream encode only |
| **Preprocess** | Optional in pipeline: CPU or GPU (CuPy / OpenCV CUDA) | Yes (preprocess_gpu) |
| **AprilTag detect** | Python `apriltag` (C library, CPU) | **No** |
| **Overlay** | CPU (draw on frame) | No |
| **Encode to JPEG** | nvJPEG (CUDA) when available | Yes |
| **Flow for “AprilTag” use case** | Cameras open with use_case=apriltag → consumer only encodes for stream; **no pipeline attached**, so **no detection runs** | N/A |
| **Flow when pipeline runs** | Vision Pipeline page “Run” → pipeline attached → one consumer thread round-robins all cameras | Detection runs only here |

**Two cameras today:** One capture thread iterates all cameras; one consumer thread iterates all cameras (round-robin). No batching, no parallel GPU work across cameras.

**Existing GPU assets:** CuPy (BGR→gray, preprocess_gpu), nvJPEG (encode), optional OpenCV CUDA (preprocess). Repo also has `AprilTag_CUDA_X86` (CUDA kernels for AprilTag).

---

## 2. Execution Location: What Runs on GPU vs CPU (Target Design)

The following table makes explicit **where each part of the pipeline runs** in the target design. “GPU” means the workload runs on the GPU (CuPy, OpenCV CUDA, nvJPEG, or AprilTag CUDA); “CPU” means it runs on the CPU. Data movement (upload/download) is noted where relevant.

| Step | Execution location | Notes |
|------|---------------------|--------|
| **Capture** | **CPU** | OpenCV `VideoCapture.read()` per camera; frames in host memory. |
| **Upload (raw → GPU)** | **CPU → GPU** | One-time upload per frame when pipeline starts; only if next stage is on GPU. |
| **Preprocess** (blur, grayscale, threshold) | **GPU** | CuPy or OpenCV CUDA (`preprocess_gpu`). Input and output stay on GPU when possible. |
| **AprilTag detect** | **GPU** (target) / **CPU** (fallback) | Target: AprilTag CUDA. Fallback: CPU `apriltag` library (requires download from GPU for that step only). |
| **Overlay** (draw corners/IDs) | **GPU** (optional) / **CPU** | Target: draw on GPU (CuPy/OpenCV CUDA). Fallback: CPU OpenCV draw. |
| **Encode to JPEG** | **GPU** | nvJPEG. If frame is on GPU, encode from device buffer if API allows; else one download then encode. |
| **Download (if needed)** | **GPU → CPU** | Only when a stage requires CPU (e.g. CPU detector fallback, or nvJPEG that accepts only host buffer). |
| **Streaming / API** | **CPU** | JPEG bytes in `frame_queue`; WebSocket/REST serve to clients. |

**Summary:** Capture and coordination = **CPU**. Preprocess, detect (target), overlay (optional), encode = **GPU**. Minimize GPU↔CPU copies; only detections (and optional single upload/download per frame) cross the boundary when using full GPU path.

---

## 3. Debug Frames at Every Step (Requirement)

For debugging, **every step** of the AprilTag pipeline must expose a **viewable debug frame** that shows **both cameras together** in one image (e.g. side-by-side or a single composite) so that each stage’s output for both cameras can be inspected at once.

| Pipeline step | Debug frame content | How it is exposed (conceptual) |
|---------------|---------------------|---------------------------------|
| **1. Raw** | **Both cameras together** — unprocessed images (e.g. camera A | camera B side-by-side). | One composite debug frame for “raw”; e.g. `get_latest_frame("raw")` returning a single JPEG that contains both cameras. |
| **2. Preprocess** | **Both cameras together** — preprocess output for each (blurred/grayscale/thresholded), e.g. side-by-side. | One composite debug frame for “preprocess” stage. |
| **3. Detect** | **Both cameras together** — input to detector (or preprocess view) for each camera, e.g. side-by-side. | One composite debug frame for “detect”, or reuse preprocess composite. |
| **4. Overlay** | **Both cameras together** — frames with tag corners and IDs drawn for each camera, e.g. side-by-side. | One composite debug frame for “detect_overlay” stage. |
| **5. Encode (final)** | **Both cameras together** — final encoded content for each camera (or the two streams in one view). | One composite or combined view for the “final” debug stage. |

**Requirement:** The pipeline must provide **one viewable debug frame per step** (raw, preprocess, detect, overlay, final/encode), and **each of these must show both cameras together** (e.g. one image with camera A and camera B side-by-side or otherwise combined). In the UI or via an API, a user selects a step and sees **both cameras at that step in a single debug view**. No step should be “invisible” for debugging; implementation can compose the two camera outputs into one frame per step (e.g. horizontal concatenation) before exposing it.

---

## 4. FPS Counters per Step (Requirement)

**Each step** of the AprilTag pipeline must have an **FPS counter** so that throughput and bottlenecks can be measured at every stage (and per camera where applicable).

| Step | FPS counter scope | Purpose |
|------|-------------------|--------|
| **Capture** | Per camera | Frames captured per second from the device (input to pipeline). |
| **Preprocess** | Per camera (or per pipeline instance) | Frames per second leaving the preprocess stage. |
| **Detect** | Per camera (or per pipeline instance) | Frames per second leaving the detect stage (detections produced). |
| **Overlay** | Per camera (or per pipeline instance) | Frames per second leaving the overlay stage. |
| **Encode** | Per camera (or per pipeline instance) | Frames per second of encoded JPEGs written to `frame_queue`. |
| **End-to-end (per camera)** | Per camera | Frames per second of complete pipeline output (stream FPS) for that camera. |

**Requirement:** The system must expose FPS (or equivalent rate) for each of the above so that debug UIs or APIs can display them (e.g. in the debug tree, on the AprilTag page, or in stream metrics). Counters can be derived from frame timestamps or frame counts over a sliding window; implementation detail is left to code.

---

## 5. AprilTag Page: Start/Stop, Settings, and Frame View (Requirement)

The **AprilTag** subsection (the page added in the nav after Discovery) must provide controls to run the AprilTag pipeline and to inspect its output. All of the following are **requirements** for that page.

### 5.1 Start and Stop buttons

- **Start button:** Starts the AprilTag detection pipeline (two cameras, parallel through the full pipeline as in §6–7). When pressed, the system attaches the default AprilTag pipeline to the two camera managers (or the cameras selected for AprilTag), and the consumer begins processing frames from both cameras in parallel. The button must be clearly visible and actionable only when the pipeline is not running (e.g. disabled or hidden when running).
- **Stop button:** Stops the AprilTag pipeline. Detaches the pipeline from the camera managers (or stops the two-camera AprilTag processing path) so that cameras may continue streaming without detection, or remain open for other use. The button must be visible and actionable only when the pipeline is running (e.g. disabled or hidden when stopped).
- **State:** The page must show the current state (e.g. “Stopped” / “Running”) so the user knows whether the algorithm is active. Start/Stop are the primary controls for this algorithm.

### 5.2 Settings for the algorithm

- The AprilTag page must expose **settings** for the algorithm so the user can configure the pipeline without leaving the page. At least the following (or their equivalents) must be configurable:
  - **Tag family** (e.g. tag36h11, tag25h9, tag16h5).
  - **Preprocess** parameters (e.g. blur kernel size, threshold type, adaptive block size / C, morphology) as in the existing preprocess stage.
  - **Detect** options if any (e.g. decimation, edge refinement).
- Settings may be applied on **Start** (take effect when pipeline starts) or **Apply** (apply to running pipeline if supported). The plan does not prescribe apply-on-start vs live apply; implementation chooses. Settings must be persisted or remembered per session where appropriate.

### 5.3 View of the frames (debug frames on the AprilTag page)

- The AprilTag page must include a **view of the frames** produced by the pipeline. This view shows the **debug frames** defined in §3: one composite image per step that shows **both cameras together** (e.g. side-by-side).
- **Requirement:** The page must provide:
  - A **frame viewer** (or equivalent) that displays the current debug frame for a **selected step** (raw, preprocess, detect, overlay, final/encode). The user can select which step to view (e.g. dropdown or tabs); the viewer then shows the composite “both cameras together” image for that step, updated live while the pipeline is running.
  - Optionally, multiple viewers or a grid showing several steps at once; at minimum, one viewer with step selection is required.
- The viewer must consume the same debug frames exposed by the backend (§3) — e.g. via an API or WebSocket that returns the composite JPEG (or frame) for the selected stage. When the pipeline is stopped, the viewer may show the last frame or a placeholder; behavior is an implementation detail.
- **FPS counters** (§4) must be visible on the AprilTag page for each step (or a summary), so the user can correlate the frame view with throughput (e.g. next to the viewer or in a small panel).

**Summary:** The AprilTag subsection must have **Start** and **Stop** buttons for the algorithm, **settings** for the algorithm (tag family, preprocess, and any detect options), and a **frame view** that shows the debug frames (both cameras together) for the selected pipeline step, with FPS counters available on the same page.

---

## 6. Where GPU Can Be Used (and How)

### 6.1 Decode (if input were compressed)

- **Today:** Raw frames from V4L2/OpenCV (no decode).
- **Future:** If you ever ingest MJPEG/H264 from cameras, GPU decode (NVDEC) would sit here. **Out of scope** for “two USB cameras + raw” unless you change capture path.

### 6.2 Preprocess (blur, grayscale, threshold)

- **Already available:** `preprocess_gpu` (CuPy or OpenCV CUDA). Use it in the AprilTag pipeline so preprocessing is on GPU.
- **Efficiency:** Keep frames on GPU (CuPy/cv2.cuda) as long as possible; only download when the next stage requires CPU (e.g. current CPU AprilTag detector).

### 6.3 AprilTag detection (main target)

- **Current:** CPU only (`apriltag_detector_adapter.py` → `apriltag` C library).
- **Options:**
  - **A. AprilTag CUDA (recommended if you want max GPU):** Use the existing `AprilTag_CUDA_X86` (or equivalent) so detection runs on GPU. Then grayscale (and ideally preprocessing) stays on GPU → GPU detect → only detections (small structs) come back to CPU. Overlay/encode can then use GPU frame again.
  - **B. Keep CPU detector but minimize data movement:** Preprocess on GPU, download only the grayscale frame to CPU for `apriltag.detect()`. Saves no GPU on the detect step but reduces CPU preprocessing and keeps a single code path.
  - **C. Other GPU detectors:** If you later swap to a different GPU-capable tag/object detector (e.g. NN-based), the same “preprocess on GPU → detect on GPU → overlay/encode on GPU” pipeline applies.

**Recommendation:** Plan for **A** (AprilTag CUDA) as the “max GPU” path, with **B** as fallback when CUDA AprilTag is unavailable.

### 6.4 Overlay (draw corners/IDs)

- **Today:** CPU (OpenCV draw on numpy array).
- **GPU option:** Draw on GPU (e.g. CuPy/OpenCV CUDA) so the frame never comes back to CPU until encode. Smaller win than moving detection to GPU but keeps the pipeline more GPU-centric.

### 6.5 Encode to JPEG (stream / recording)

- **Already GPU:** nvJPEG. Keep using it. If the frame is on GPU after overlay, pass GPU buffer to nvJPEG (if API supports it) to avoid a final download.

---

## 7. Two-Camera: Two Images from Queues, Parallel Through Entire Pipeline

### 7.1 Get two images from the camera manager (one per camera)

- **Each consumer iteration:** Take **exactly two** raw frames from the camera manager queues — **one from each camera**:
  - Frame A = `manager_A.get_raw_frame(timeout=0.0)` (from manager A’s `raw_frame_queue`).
  - Frame B = `manager_B.get_raw_frame(timeout=0.0)` (from manager B’s `raw_frame_queue`).
- If only one camera has a frame, process that one (or skip and wait next iteration; policy choice). If both have frames, **both** are processed in parallel (see 3.2). No new queues; only the two existing managers’ queues.

### 7.2 Put both frames in parallel through the entire process till the end

- **Parallel** means: the **two** frames (one per camera) are processed through the **full** pipeline — preprocess → detect → overlay → encode — **in parallel**, then results are written back to the correct manager.
- **Two ways to implement “parallel” (design choice):**
  - **Option A — Concurrent tasks:** Run two concurrent tasks (e.g. threads or async tasks). Task 1: take frame A → preprocess → detect → overlay → encode → write to manager A’s `frame_queue` and detections. Task 2: take frame B → same pipeline → write to manager B’s `frame_queue` and detections. Both run at the same time; GPU may be shared (e.g. sequential kernel launches from two threads) or each task uses the pipeline in a thread-safe way.
  - **Option B — Batch of 2:** Keep one consumer thread. Collect frame A and frame B. Run **one** batch of 2 through preprocess (GPU), then **one** batch of 2 through detect (GPU), then overlay and encode for both (batch or two sequential), then write result A to manager A and result B to manager B. Requires pipeline/GPU APIs to support batch size 2 and correct association of each output to its manager.
- **Recommendation:** Option B (batch of 2) gives better GPU utilization and a single thread; Option A is simpler if the pipeline is per-frame and not batch-aware. Choose based on whether AprilTag CUDA (and preprocess/encode) can accept and return batch of 2 with correct per-frame association.

### 7.3 Per-camera queues (use existing CameraManager queues)

- **Use existing CameraManager queues:** Each camera already has its own **`raw_frame_queue`** and **`frame_queue`**. Do not add new video queues.
- **Consumer loop (revised):** Each iteration, get **two** images from the queues of the camera manager — one from manager A’s `raw_frame_queue`, one from manager B’s `raw_frame_queue`. Run both through the entire pipeline **in parallel** (Option A or B above). Write pipeline output for camera A to **manager A’s** `frame_queue` and detections; output for camera B to **manager B’s** `frame_queue` and detections.
- **Fairness:** Taking one frame per camera per iteration keeps both streams fed; processing both in parallel avoids one camera delaying the other.

### 7.4 Where to run the pipeline (attach to CameraManager)

- **Today:** AprilTag detection runs only when a pipeline is started from the Vision Pipeline page; that path sets **`manager.vision_pipeline`** and **`manager.use_case = "vision_pipeline"`**. The “AprilTag” use case in the Cameras page does **not** attach a pipeline, so the consumer only encodes for stream and never calls `process_vision_pipeline()`.
- **Plan:** When a camera is opened with use_case=apriltag, **attach a default AprilTag pipeline to that camera’s CameraManager** (set `manager.vision_pipeline` to a built pipeline and keep `manager.use_case` so the consumer calls `manager.process_vision_pipeline()`). Frames still come from **`manager.get_raw_frame()`** inside `process_vision_pipeline()` (i.e. from that manager’s `raw_frame_queue`). No new video source.
- **Optionally** allow the same “Run pipeline” flow from the Vision Pipeline page, but ensure that pipeline uses GPU stages when available.

**Efficiency:** Use one shared pipeline **definition** (preprocess_gpu → detect → overlay). Each CameraManager can hold its own pipeline instance (or a shared stateless GPU detector). Two cameras = two managers; each gets frames from its own `raw_frame_queue` and writes to its own `frame_queue`; same stages and, where possible, shared GPU detector.

### 7.5 Capture thread (unchanged — already in CameraService)

- **No change.** CameraService already has one capture thread that round-robins all open cameras and enqueues raw frames into each manager’s `raw_frame_queue`. The plan does not add or replace this; video continues to come only from the camera manager flow.

---

## 8. Recommended High-Level Architecture (Two Images, Parallel Through End — Using Camera Manager)

- **Capture (unchanged):** CameraService’s single capture thread round-robins all cameras; for each manager it calls `manager.camera_port.capture_frame_raw()` and `manager.enqueue_raw_frame(raw_frame)` → frames land in each **manager.raw_frame_queue**.
- **Consumer (revised for two-camera parallel):** Each iteration:
  1. **Get two images from the queues of the camera manager — one for each camera:**  
     `frame_A = manager_A.get_raw_frame(timeout=0.0)`, `frame_B = manager_B.get_raw_frame(timeout=0.0)` (from each manager’s `raw_frame_queue`).
  2. **Put those two in parallel through the entire process till the end:**  
     Run both frames through the full pipeline (Preprocess → Detect → Overlay → Encode) **in parallel** — either two concurrent tasks (one per frame) or one batch-of-2 through each stage, depending on implementation choice (see §7.2).
  3. **Write results back to the correct manager:**  
     Result for camera A → **manager_A.frame_queue** and manager A’s pipeline detections; result for camera B → **manager_B.frame_queue** and manager B’s pipeline detections.
- **Streaming / API (unchanged):** WebSocket and REST continue to read from each **manager.frame_queue** and pipeline state via the same manager APIs.

**Data flow (target), all via camera manager:**  
Camera A → **manager_A.raw_frame_queue** ← consumer gets frame_A  
Camera B → **manager_B.raw_frame_queue** ← consumer gets frame_B  
→ **[frame_A and frame_B in parallel]** → Preprocess (GPU) → Detect (GPU) → Overlay (GPU) → Encode (GPU)  
→ JPEG A → **manager_A.frame_queue** → client A  
→ JPEG B → **manager_B.frame_queue** → client B  
No new video paths; only the processing is two-frames-in-parallel and GPU-heavy.

---

## 9. Phased Implementation Plan (Conceptual — Two Images, Parallel Through End)

**Phase 1 – Enable AprilTag pipeline and two-frame pull**

- When a camera is opened with use_case=apriltag, **attach a default AprilTag pipeline to that camera’s CameraManager** so the consumer runs the pipeline path.
- **Consumer change:** Each iteration, **get two images from the queues of the camera manager (one for each camera):** `frame_A = manager_A.get_raw_frame(0)`, `frame_B = manager_B.get_raw_frame(0)`. Run both through the pipeline **in parallel** (e.g. two threads or two async tasks, each running the full pipeline for one frame), then write result A to **manager_A.frame_queue** and detections, result B to **manager_B.frame_queue** and detections. No round-robin “process A then B”; both are in flight at once.
- **Result:** AprilTag detection runs for both cameras; two frames per iteration, processed in parallel through the entire pipeline; preprocessing on GPU, detection on CPU. Video in/out remains camera manager only.

**Phase 2 – Integrate AprilTag CUDA (detect on GPU); keep two-frame parallel**

- Add `detect_apriltag_gpu` and use it in the default AprilTag pipeline. **Keep** the same two-frame flow: get two images from the two managers’ queues, put both in parallel through the full pipeline (preprocess_gpu → detect_apriltag_gpu → overlay → encode), write each result to the correct manager.
- **Result:** Preprocess + detect on GPU; two frames still processed in parallel through the entire process till the end; video source and destination remain the camera manager.

**Phase 3 – Batch-of-2 through pipeline (required for best efficiency)**

- **Why not optional:** The plan goal is “most efficient” for two cameras. Processing both frames as a **batch of 2** through each GPU stage gives better GPU utilization and lower overhead than two separate single-frame passes. So Phase 3 is **required** unless the GPU/API does not support batch-of-2 (in that case, keep two concurrent tasks from Phase 1/2).
- **Implementation:** Collect frame A and frame B, run preprocess as batch of 2, detect as batch of 2 (AprilTag CUDA must support batch or be extended to), overlay and encode for both (batch or two sequential), then dispatch result A to manager A and result B to manager B. Same “two images from queues, parallel through entire process till the end,” implemented as a single batch through each stage.
- **Result:** Best GPU utilization; one consumer iteration = two frames in, two frames out, both processed in parallel (as a batch) till the end.

**Phase 4 – Overlay and encode on GPU end-to-end (required for maximum GPU use)**

- **Why not optional:** The plan goal is “as much as possible use of GPU.” If overlay and encode stay on CPU, frames are downloaded after detect and the pipeline is only partly on GPU. Moving overlay and encode to GPU (and encoding from GPU buffer) keeps the whole pipeline on GPU and minimizes GPU↔CPU copies. So Phase 4 is **required** to meet the “maximum GPU use” goal; use CPU fallbacks only when the stack does not support GPU overlay or nvJPEG from device buffer.
- **Implementation:** Overlay on GPU (CuPy or OpenCV CUDA); encode from GPU buffer (nvJPEG if supported). **Two-frame parallel** unchanged: both frames still go through the full pipeline in parallel; only more stages are on GPU.
- **Result:** Maximum GPU use from preprocess through encode; two images per iteration from the camera manager queues, both in parallel through the entire process till the end.

---

## 10. Dependencies and Risks

| Item | Note |
|------|------|
| **AprilTag_CUDA_X86** | Must build and expose a Python-callable API (e.g. one frame in → list of detections out) that matches or adapts to `TagDetectorPort`. Check license and ABI compatibility with your Python/CUDA stack. |
| **CuPy / OpenCV CUDA** | Already used. Ensure one preprocess path keeps frames on GPU and passes them to the GPU detector without unnecessary downloads. |
| **nvJPEG** | Already used. Confirm whether it can encode from a GPU buffer (e.g. device pointer) to avoid a final download. |
| **Single GPU** | One consumer and optional batching avoid multi-GPU complexity and keep the design simple for “two cameras, one machine.” |
| **Latency** | Round-robin with at most one frame per camera per iteration keeps latency balanced; batching may add one frame of delay if you wait for both cameras before running the batch. |
| **Fallback** | Always keep a CPU AprilTag path (current adapter) when GPU detector or CUDA is unavailable. |

---

## 11. Summary

- **Video source:** All video comes from the **existing camera manager**. Each iteration the consumer gets **two images from the queues of the camera manager — one for each camera** (one from each manager’s `raw_frame_queue`). No new video path.
- **Two-frame parallel:** The **two** frames are put **in parallel through the entire process till the end** (preprocess → detect → overlay → encode). Results are written to the corresponding manager’s `frame_queue` and detections. Implementation can be two concurrent tasks (one per frame) or one batch-of-2 through each stage.
- **What runs where (see §2):** Capture = **CPU**. Preprocess, detect (target), overlay (optional), encode = **GPU**. Upload/download only where needed; minimize GPU↔CPU copies.
- **Debug frames (see §3):** **Every step** must expose **one viewable debug frame** that shows **both cameras together** (e.g. side-by-side in one image): raw, preprocess, detect, overlay, and final/encode. Each step is one composite view for debugging.
- **FPS counters (see §4):** **Each step** must have an **FPS counter**: capture (per camera), preprocess, detect, overlay, encode, and end-to-end per camera. Expose them for debug UI or API (e.g. debug tree, AprilTag page, stream metrics).
- **AprilTag page (see §5):** The AprilTag subsection must have **Start** and **Stop** buttons for the algorithm, **settings** for the algorithm (tag family, preprocess, detect options), and a **frame view** that shows the debug frames (both cameras together) for the selected pipeline step, with FPS counters on the same page.
- **Implementation order:** (1) Attach default AprilTag pipeline when use_case=apriltag and change consumer to get two frames (one per camera) and process both in parallel through the full pipeline; (2) Add detect_apriltag_gpu; (3) Implement parallel as **batch-of-2** (required for best efficiency; see §9 Phase 3); (4) Move **overlay and encode to GPU** end-to-end (required for maximum GPU use; see §9 Phase 4). Ensure debug frames and FPS counters are included for every step.

No code changes are specified in this document; it is a plan only.
