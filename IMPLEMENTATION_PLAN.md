# SVTVision — Cursor Execution Plan (No Code)

This file is the authoritative execution plan for building the SVTVision application using Cursor.

Cursor must implement stages sequentially and must not advance unless the stated exit criteria are met.

## Extracted Images

The following images were extracted from the original PDF document:
- `planA_image_page1_1.png` - Page 1 diagram/screenshot
- `planA_image_page2_2.png` - Page 2 diagram/screenshot
- `planA_image_page4_3.png` - Page 4 diagram/screenshot
- `planA_image_page6_4.png` - Page 6 diagram/screenshot
- `planA_image_page7_5.png` - Page 7 diagram/screenshot
- `planA_image_page9_6.png` - Page 9 diagram/screenshot

## Global Rules (Apply to All Stages)

- Cursor must not skip stages.
- Every stage must provide:
  - Visible UI proof
  - Debug Tree nodes with status, reason, and metrics
  - A self-test runnable via `/api/selftest/run?test=<name>` returning JSON
- All queues must be bounded and drop-oldest.
- Backend and frontend remain strictly separated.
- If a self-test fails, Cursor must stop and fix before continuing.

## PhotonVision-Style Web UI Requirements

The SVTVision frontend must look and feel like PhotonVision. This is a product requirement because it enables rapid, on-robot debugging without attaching a debugger.

### Always-visible layout

1. **Top Bar**
   - App name and build id
   - Global health indicator (OK/WARN/STALE/ERROR)
   - Backend connection indicator (connected / reconnecting)
   - Optional later: CPU/GPU summary

2. **Left Pane - Debug Tree**
   - Expand/collapse hierarchical nodes
   - Each node row shows:
     - status color + state
     - short reason string
     - key metrics (fps, latency, drops, last update age)
   - Clicking a node opens a detail panel with:
     - ring-buffer history (short window)
     - last input/output timestamps
     - current metrics snapshot

3. **Main Pane - Viewer + Tabs**
   - One viewer region
   - Camera selector dropdown (one viewer, switch cameras)
   - Tabs per selected camera:
     - Raw
     - Preprocess
     - Detect Overlay
     - (Later) Pose Overlay
   - Detections table under viewer:
     - tag id, count, last seen, per-frame latency

4. **Right Pane - Controls**
   - Camera open/close
   - Resolution and FPS selector
   - Exposure/gain/saturation controls
   - Apply + Verify status (requested vs actual)
   - (Later) pipeline selection

### Navigation pages

- **Cameras** (default landing)
  - discovery list
  - select camera
  - viewer + tabs
  - controls
- **Settings**
  - global config, logging, retention (later)
- **Self-Test**
  - run tests and show latest report + artifacts
- **Later pages:**
  - Localization
  - Planning
  - Executor

### Real-time data model

Frontend subscribes to:

- **Telemetry channel** (WebSocket or SSE):
  - debug tree updates
  - per-camera metrics
  - detection summaries
  - top faults
- **Video streams** (WebSocket):
  - `/ws/stream?camera=<id>&stage=<raw|preprocess|detect_overlay|pose_overlay>`

### Frontend build modes

- **Dev mode**: frontend dev server with proxy to backend `/api` and `/ws`
- **Prod mode**: frontend build output served by backend for one-command startup

### Cursor debugging requirement

Stage 0 must bring up the full UI shell (Top Bar + Debug Tree + routing + Self-Test page) using simulated nodes, so later stages only "light up" existing UI.

---

## Stage 0 — Repo Skeleton + Run Loop + FE/BE Separation

### Goal
Backend and frontend run locally with a visible Debug Tree (simulated nodes).

### Tasks
- Create repo layout:
  - `backend/`
  - `frontend/`
  - `config/`
  - `docs/`
- Backend boots with:
  - AppOrchestrator
  - ConfigService
  - MessageBus
  - HealthService
  - LoggingService (minimal)
- WebServerAdapter endpoints:
  - `GET /api/system`
  - `GET /api/debug/tree`
- Frontend:
  - loads static assets from backend
  - renders Debug Tree
- SelfTestRunner stub:
  - `/api/selftest/run?test=smoke`

### Verify
- UI loads successfully
- Debug Tree visible with simulated nodes
- Smoke self-test returns `pass=true`

### Exit Criteria
- Single command starts backend
- UI and self-test both work

---

## Stage 1 — Camera Discovery + Deep Capabilities

### Goal
Backend reliably lists cameras with stable IDs and full hardware capability inventory.

### Tasks
- Implement CameraDiscoveryPort
- Implement UVC/V4L2 discovery adapter to collect per camera:
  - stable ID (USB serial preferred)
  - `/dev/video*` mapping
  - USB info: vid, pid, serial, bus, port path, negotiated speed
  - kernel driver/module binding
  - host controller context (lspci entry)
  - V4L2 formats, resolutions, FPS ranges
  - V4L2 controls: min/max/step/default/current
- Domain CameraDiscovery publishes CameraList + CameraDetails
- APIs:
  - `GET /api/cameras`
  - `GET /api/cameras/{id}`
  - `GET /api/cameras/{id}/capabilities`
  - `GET /api/cameras/{id}/controls`
- UI Discovery page:
  - expandable camera details
  - copy-to-clipboard full JSON
- Self-test:
  - `camera_discovery_deep`

### Verify
- Hot-plug camera reflected within 3 seconds
- Details sufficient to debug USB bandwidth issues

### Exit Criteria
- Stable camera IDs
- Self-test PASS (or WARN if no camera)

---

## Stage 2 — Camera Open/Close + Raw Streaming

### Goal
Select a camera and view stable live raw video without capture blocking.

### Tasks
- Implement CameraPort adapter (open/close/capture)
- Implement StreamEncoderPort adapter (WebSocket preferred)
- CameraManager lifecycle + FrameCapture thread
- Bounded frame queue (size=3, drop-oldest)
- APIs:
  - `POST /api/cameras/{id}/open`
  - `POST /api/cameras/{id}/close`
- Stream endpoint:
  - `/ws/stream?camera={id}&stage=raw`
- UI viewer:
  - camera selector
  - FPS and drop counters
- Self-test:
  - `open_stream`

### Verify
- Live video visible
- Metrics update continuously

### Exit Criteria
- Stream runs 5 minutes without freeze or leak

---

## Stage 3 — Camera Settings (Save / Apply / Verify)

### Goal
Change resolution/FPS/exposure from UI and persist to JSON.

### Tasks
- Define `config/cameras.json`
- ConfigService supports versioned apply + rollback
- CameraManager apply + verify (read-back actual values)
- APIs:
  - `GET /api/cameras/{id}/settings`
  - `POST /api/cameras/{id}/settings`
- UI Settings tab showing requested vs actual
- Self-test:
  - `settings_roundtrip`

### Verify
- Restart backend → settings persist
- Stream reflects new resolution/FPS

### Exit Criteria
- Settings persist and verify reliably

---

## Stage 4 — Vision Pipeline + AprilTag Detection

### Goal
Multi-stage vision pipeline with AprilTag detection and overlays.

### Tasks
- Implement PreprocessPort chain: add this to capture thread. 
- From the PreprocessPort till the tag detect all should be in one thread (both cameras)
- Implement TagDetectorPort (CPU AprilTag)
- VisionPipeline orchestrator:
  - Raw → Preprocess → Detect
- Publish StageFrames + AprilTagDetections
- Streams:
  - `/ws/stream?camera={id}&stage=preprocess`
  - `/ws/stream?camera={id}&stage=detect_overlay`
- UI tabs:
  - Raw
  - Preprocess
  - Detect Overlay
- Detection panel:
  - tag IDs, count, last seen, latency
- Self-test:
  - `tag_detect`

### Verify
- Printed tag detected
- Overlay shows corners and ID

### Exit Criteria
- Detection stable and repeatable

---

## Stage 5 — Health + Debug Tree Root-Cause Quality

### Goal
Every failure has a deterministic, visible root cause.

### Tasks
- Standardize metrics (FPS, latency, drops, age)
- Health rules:
  - OK / WARN / STALE / ERROR
- UI Top Faults panel
- Self-test:
  - `health_transitions`

### Verify
- Unplug camera → ERROR with reason
- Freeze frames → STALE with reason

### Exit Criteria
- All failures explainable in Debug Tree

---

## Stage 6 — Validity Envelope

### Goal
Add quality_state and freshness to all control-relevant outputs.

### Tasks
- Add validity envelope to vision outputs
- Classify streams FAST / MEDIUM / SLOW
- API:
  - `GET /api/validity/streams`
- UI validity indicators

### Exit Criteria
- Validity consistent and visible

---

## Stage 7 — Gimbals (Later)

Manual control, safety limits, TRACK_TAG mode, extrinsics.

---

## Stage 8 — Localization + Planning + Executor

Localization fusion, PathPlanner integration, executor accept/reject, safe stop on stale feedback.

---

## Definition of Done

SVTVision is complete when:

- All stages pass self-tests
- Every failure is explainable live
- All intent is validity-tagged and rejectable by roboRIO
- System is debuggable without attaching a debugger
