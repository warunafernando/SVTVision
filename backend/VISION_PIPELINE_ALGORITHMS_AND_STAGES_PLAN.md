# Vision Pipeline: Algorithms and Stages — Architecture Plan

This document describes a plan to evolve the vision pipeline so that:

1. **Algorithms** define high-level vision flows (AprilTag CPU, AprilTag hybrid, object detection CPU/GPU, vSLAM). Each algorithm is an ordered list of **stage references**.
2. **Stages** are reusable processing units. The same stage (e.g. preprocess, threshold) can be shared across algorithms. Each stage has an **execution type** (CPU, GPU, hybrid).
3. **Stage settings** are configurable per stage; each stage can expose a **settings schema** and **get/set config**. Settings are shown in the UI and **saved in camera config**.
4. **Debug streaming** exposes output from each stage for debugging, but only when that stage is the active debug target (stream requested for that stage).
5. **Visual pipeline editor (LabVIEW-style)** in the web GUI: build the algorithm by placing nodes (sources, stages, sinks) and connecting them. Each stage is debuggable individually; web streaming can be attached to the **input** or **output** of any stage. Inputs to a stage can come from another stage or from a video/image file (or live camera); outputs can go to another stage or to save as video/image.

---

## 1. Concepts

### 1.1 Stage

- **What**: A single processing step with a well-defined interface: `process(frame, context) -> (frame, context)`.
- **Identity**: Each stage has a unique **stage_id** (e.g. `preprocess_cpu`, `detect_apriltag_hybrid`, `overlay`) and a **name** for display/streaming.
- **Execution type**: One of `cpu`, `gpu`, `hybrid`. Used for:
  - Monitoring and UI (show which stages are CPU/GPU/hybrid).
  - Optionally selecting implementation (e.g. preprocess_cpu vs preprocess_gpu are different stage instances with different backends).
- **Reuse**: The same logical stage (e.g. “preprocess”) can exist in multiple variants (preprocess_cpu, preprocess_gpu). Different algorithms reference the variant they need. Stages are **shared** in the sense that one stage definition (one id) can be used in many algorithms.

**Stage registry**: All available stages are registered (e.g. in config or a `StageRegistry`). Each entry: `stage_id`, `name`, `execution_type`, and a factory or adapter that implements `PipelineStagePort`.

**Stage settings**: A stage can expose configurable settings (e.g. preprocess: blur_kernel_size, adaptive_block_size; detector: family, decimate). Each such stage provides a **settings schema** (for the UI) and **get_config** / **set_config** (for reading and persisting values). Settings are stored **per camera** in config and shown in the **interface** (see §1.4).

### 1.2 Algorithm

- **What**: A named vision pipeline = ordered list of **stage_ids** plus optional algorithm-specific config.
- **Examples**:
  - `apriltag_cpu`: [raw, preprocess_cpu, detect_apriltag_cpu, overlay]
  - `apriltag_hybrid`: [raw, preprocess_gpu, detect_apriltag_hybrid, overlay]
  - `object_detection_cpu`: [raw, preprocess_cpu, detect_object_cpu, overlay]
  - `object_detection_gpu`: [raw, preprocess_gpu, detect_object_gpu, overlay]
  - `vslam`: [raw, preprocess_cpu, track_vslam, map_update, overlay] (example; actual stages TBD)

- **Runtime**: When a camera is assigned an algorithm, the vision pipeline is built by **resolving** each stage_id to a `PipelineStagePort` instance (from the registry). The existing `VisionPipeline` then runs that list of stages in order. No change to the core loop.

### 1.3 Execution type (CPU / GPU / hybrid)

- **Per stage**: Each registered stage has `execution_type: "cpu" | "gpu" | "hybrid"`.
- **Implementation**: Different stage_ids imply different implementations (e.g. `preprocess_cpu` uses CPU blur/threshold; `preprocess_gpu` uses CUDA). Sharing is at the **stage_id** level: two algorithms both using `preprocess_cpu` get the same stage implementation.
- **Monitoring**: Backend and UI can show per-stage execution type and, in the future, per-stage timing (CPU vs GPU).

### 1.4 Stage settings (config + UI)

- **What**: Each stage can expose **adjustable settings** (e.g. preprocess: blur_kernel_size, adaptive_block_size, threshold_type, morphology; detector: family, decimate). The backend and UI need to know **what** settings exist, their **type**, **default**, and **constraints** (min/max, enum) so the interface can show the right controls and validate input.
- **Schema**: Each configurable stage declares a **settings schema**: list of fields, each with at least `key`, `type` (`number` | `boolean` | `string` | `enum`), `default`; optionally `min`, `max`, `step`, `options` (for enum), `label`, `description`. Example (preprocess):
  - `{ "key": "blur_kernel_size", "type": "number", "default": 3, "min": 0, "max": 31, "step": 2, "label": "Blur kernel size" }`
  - `{ "key": "threshold_type", "type": "enum", "default": "adaptive", "options": ["adaptive", "binary"], "label": "Threshold type" }`
- **Config storage**: Settings are stored **per camera** so each camera can have different stage tuning. In camera config (e.g. `config/cameras/<camera_id>.json`), use a single key such as **`stage_settings`** (or `pipeline.stage_settings`):
  - `stage_settings`: object keyed by **stage_id** (or stage name), value = object of key-value settings for that stage.
  - Example: `"stage_settings": { "preprocess_cpu": { "blur_kernel_size": 5, "adaptive_block_size": 15 }, "detect_apriltag_cpu": { "family": "tag36h11" } }`
  - When building the pipeline for a camera, after resolving each stage from the registry, apply that camera’s `stage_settings[stage_id]` to the stage (call `set_config(...)`).
- **Backward compatibility**: Current camera config uses `preprocessing: { ... }` for the single preprocess stage. During migration, map `preprocessing` into `stage_settings.preprocess_cpu` (or the active preprocess stage_id) when reading, and when writing back, continue to write under `stage_settings`; optionally keep writing a top-level `preprocessing` for older clients.
- **API** (backend):
  - **GET** `/api/cameras/{camera_id}/stage-settings` — Returns for the camera’s current algorithm: for each stage that has settings, the **schema** (list of field specs) and **current values** (from the live stage instance or from config). Response shape e.g. `{ "stages": [ { "stage_id": "preprocess_cpu", "name": "Preprocess (CPU)", "schema": [...], "values": { "blur_kernel_size": 3, ... } }, ... ] }`. If camera has no pipeline/open, return empty or 404.
  - **PATCH** (or **PUT**) `/api/cameras/{camera_id}/stage-settings` — Body: `{ "stage_id": "preprocess_cpu", "values": { "blur_kernel_size": 5 } }`. Backend applies to the stage instance (if pipeline is running) and **persists** to camera config (`stage_settings[stage_id]`). Returns updated schema + values for that stage or 400 on validation error.
- **UI** (frontend):
  - When a camera is selected and has an active pipeline, show a **“Stage settings”** (or “Pipeline settings”) section.
  - List each stage in the current algorithm that has settings. For each stage, show the stage name and a **form** built from the schema: number → slider or number input, boolean → toggle, enum → dropdown. Bind inputs to the **current values** from GET stage-settings.
  - On change: either **debounced PATCH** per field/stage, or a **“Save”** button that PATCHes the current form state. Optionally show “Saved” / “Saving…” / error.
  - Ensure all settings displayed in the UI are **saved in config** via the PATCH endpoint (backend writes to camera config file or config service).
- **Port interface**: Stages that support settings implement optional methods: `get_settings_schema() -> List[SettingSpec]`, `get_config() -> Dict[str, Any]`, `set_config(config: Dict[str, Any]) -> bool`. The pipeline or registry does not require every stage to support these; only stages that do will appear in the stage-settings API and UI.

---

## 2. Data model (config / code)

### 2.1 Stage definitions

Stages can be defined in config and/or code.

**Option A — Config-driven (recommended for flexibility)**  
e.g. `config/pipeline_stages.json`:

```json
{
  "stages": [
    { "id": "preprocess_cpu", "name": "Preprocess (CPU)", "execution_type": "cpu", "adapter": "preprocess", "params": {}, "settings_schema": [
      { "key": "blur_kernel_size", "type": "number", "default": 3, "min": 0, "max": 31, "step": 2, "label": "Blur kernel size" },
      { "key": "adaptive_block_size", "type": "number", "default": 15, "min": 3, "max": 51, "step": 2, "label": "Adaptive block size" }
    ]},
    { "id": "preprocess_gpu", "name": "Preprocess (GPU)", "execution_type": "gpu", "adapter": "preprocess_gpu", "params": {} },
    { "id": "detect_apriltag_cpu", "name": "AprilTag Detect (CPU)", "execution_type": "cpu", "adapter": "apriltag_detector", "params": { "family": "tag36h11" }, "settings_schema": [
      { "key": "family", "type": "enum", "default": "tag36h11", "options": ["tag36h11", "tag25h9"], "label": "Tag family" }
    ]},
    { "id": "detect_apriltag_hybrid", "name": "AprilTag Detect (Hybrid)", "execution_type": "hybrid", "adapter": "apriltag_detector_cuda", "params": {} },
    { "id": "detect_object_cpu", "name": "Object Detect (CPU)", "execution_type": "cpu", "adapter": "object_detector", "params": {} },
    { "id": "detect_object_gpu", "name": "Object Detect (GPU)", "execution_type": "gpu", "adapter": "object_detector_gpu", "params": {} },
    { "id": "overlay", "name": "Overlay", "execution_type": "cpu", "adapter": "overlay", "params": {} }
  ]
}
```

**Option B — Code-only**: Stages registered in a `StageRegistry` in code; algorithms still reference stage_ids. Config only lists algorithm definitions.

**Hybrid**: Default stages live in code (backward compat); optional config overlay adds or overrides stages by id.

### 2.2 Algorithm definitions

e.g. `config/pipeline_algorithms.json` (or same file as stages):

```json
{
  "algorithms": [
    { "id": "apriltag_cpu", "name": "AprilTag (CPU)", "stage_ids": ["preprocess_cpu", "detect_apriltag_cpu", "overlay"] },
    { "id": "apriltag_hybrid", "name": "AprilTag (Hybrid)", "stage_ids": ["preprocess_gpu", "detect_apriltag_hybrid", "overlay"] },
    { "id": "object_detection_cpu", "name": "Object Detection (CPU)", "stage_ids": ["preprocess_cpu", "detect_object_cpu", "overlay"] },
    { "id": "object_detection_gpu", "name": "Object Detection (GPU)", "stage_ids": ["preprocess_gpu", "detect_object_gpu", "overlay"] },
    { "id": "vslam", "name": "vSLAM", "stage_ids": ["preprocess_cpu", "track_vslam", "overlay"] }
  ]
}
```

- **Camera assignment**: Each camera has an **algorithm_id** (e.g. from camera config or use_case). Current `use_case: "apriltag"` can map to `algorithm_id: "apriltag_cpu"` for backward compatibility.

### 2.3 Camera config and stage_settings

Camera config (e.g. `config/cameras/<camera_id>.json`) holds device and pipeline settings. Include **stage_settings** for per-camera, per-stage tuning:

```json
{
  "brightness": 0,
  "contrast": 17,
  "resolution": { "width": 1920, "height": 1200, "fps": 50 },
  "use_case": "apriltag",
  "stage_settings": {
    "preprocess_cpu": {
      "blur_kernel_size": 3,
      "adaptive_block_size": 15,
      "adaptive_c": 3,
      "morphology": false
    },
    "detect_apriltag_cpu": {
      "family": "tag36h11"
    }
  }
}
```

- **Reading**: When building the pipeline, load `stage_settings` from camera config and call `set_config(stage_settings[stage_id])` on each stage that supports it. If `preprocessing` exists and `stage_settings` has no preprocess entry, map `preprocessing` → `stage_settings.preprocess_cpu` for backward compat.
- **Writing**: When the user changes settings in the UI, PATCH `/api/cameras/{id}/stage-settings`; backend merges into `stage_settings[stage_id]` and persists the full camera config (so all stage settings are saved).

---

## 3. Pipeline runtime (minimal change)

- **VisionPipeline** continues to accept a **list of stages** (each implementing `PipelineStagePort`) and runs them in order. No change to the core loop.
- **Build step**: When opening a camera with a given `algorithm_id`:
  1. Look up the algorithm by id.
  2. Resolve each `stage_id` in `algorithm.stage_ids` to a `PipelineStagePort` instance (from StageRegistry / factory).
  3. Construct `VisionPipeline(..., stages=resolved_stages)`.

So algorithms and stage registry live **above** the existing pipeline; the pipeline itself stays stage-based and algorithm-agnostic.

---

## 4. Debug streaming (per-stage, only when debugging that stage)

**Requirement**: Monitor output from each stage for debug via streaming, but only during debug of that stage.

**Interpretation**:

- **“Debug of that stage”** = user (or client) explicitly requests a stream for that stage (e.g. “show me preprocess output for camera X”).
- **Mechanism**: Reuse the existing **stream-by-stage** API: client connects to the stream endpoint with `camera_id` and `stage=<stage_name>`. The backend sends frames only for that stage (from `get_latest_frame(stage)`). So “debugging stage X” = connecting to the stream with `stage=X`.

**Behavior**:

- Every stage in the current algorithm has a **stage name** (from `PipelineStagePort.name` or from config). That name is what the client uses in `stage=...`.
- **No broadcast of all stages**: The client requests one stage per stream connection. So we only stream the stage that is being debugged (the one requested). No extra “stream everything” mode required.
- **Optional “debug mode” flag per camera**: If desired, we can add a per-camera flag like `debug_stages: ["preprocess_cpu"]` that restricts which stages **retain** their latest frame for streaming (to save memory when not debugging). When `debug_stages` is empty or absent, retain all stages (current behavior). When non-empty, only those stages’ outputs are stored for `get_latest_frame()`. This way “only during debug” can mean “only when that stage is in the debug set,” and we only pay the storage cost for stages we care about. Implementation detail: pipeline could accept an optional `retain_stages: Set[str]` and only push to `_stage_frames` for those stages (plus always retain raw). Default: retain all (current behavior).

**Summary**:

- **Streaming**: Existing “request stream by stage” already gives “monitor output from each stage for debug.” Restrict to “only during debug of that stage” by (a) only sending the requested stage (already so), and optionally (b) only retaining frames for stages that are in a “debug set” for that camera.
- **API**: Keep `GET /stream?camera_id=&stage=<stage_name>`. Stage names = stage names from the algorithm’s resolved stages. Valid stages = `["raw"] + [s.name for s in pipeline._stages]` (already done).

---

## 5. Backward compatibility

- **use_case**: Keep `use_case` in camera config and API. Map `use_case: "apriltag"` → `algorithm_id: "apriltag_cpu"` (or a default algorithm that matches current behavior). Other use_cases can map to other algorithms (e.g. `object-detection` → `object_detection_cpu`).
- **Current pipeline**: The default AprilTag pipeline (preprocess → detect → overlay) becomes the algorithm `apriltag_cpu` with stages `preprocess_cpu`, `detect_apriltag_cpu`, `overlay`. Same behavior, just expressed as algorithm + stage_ids.
- **Streaming**: No change to stream contract; stage names remain the ones provided by the stages in the active algorithm.

---

## 6. Visual pipeline editor (LabVIEW-style UI)

The algorithm is built **visually** in the web GUI: drag-and-drop **nodes** onto a **canvas**, then **connect** output ports to input ports with **wires**. The layout is LabVIEW-like (data-flow graph). Connections define where each stage gets its input and where its output goes; **debug points** attach web streaming to the input or output of any stage so each stage can be debugged individually.

### 6.1 Nodes

- **Source nodes** (inputs to the graph):
  - **Live camera**: stream from a selected camera (raw frames).
  - **Video file**: play a video file (path or upload); frames fed into the graph.
  - **Image file**: single image or sequence; frames fed into the graph.
  - Each source has one or more **output ports** (e.g. “frame”, “metadata”).

- **Stage nodes** (processing):
  - Each **stage** from the stage registry appears as a node (e.g. Preprocess, AprilTag Detect, Overlay). A stage node has **input port(s)** (e.g. “frame”) and **output port(s)** (e.g. “frame”, “detections”).
  - Double-click or panel opens **stage settings** (schema-based form); settings are saved in config as in §1.4.

- **Sink nodes** (outputs from the graph):
  - **Save as video**: connect a frame output to this sink; backend writes frames to a video file (path/format configurable).
  - **Save as image**: connect a frame output to this sink; save current frame or sequence as image(s).
  - **Debug viewer**: connects to a **single** port (input or output of any stage, or a source output). When connected, that port’s data is available for **web streaming** (the existing stream API), so the user can view that stage’s input or output in the browser. Each stage can have its own debug viewer (input and/or output); each stage is debuggable individually.

### 6.2 Connections (wires)

- **Valid connections** (output port → input port):
  - Source output (camera / video file / image file) → stage input.
  - Stage A output → stage B input (any two stages; can form DAGs, but runtime may restrict to linear or acyclic for simplicity).
  - Stage output (or source output) → sink input: **Save video**, **Save image**.
  - Any **frame** output or **frame** input → **Debug viewer** input (to stream that point for debug).
- **Type matching**: Ports have types (e.g. `frame`, `detections`, `metadata`). A wire can only connect an output type to a compatible input type (e.g. frame → frame). UI disallows invalid connections.
- **One driver per input**: Each input port receives at most one wire (single producer). Multiple outputs can fan out from one output port to several inputs (e.g. one preprocess output → detect and → debug viewer).

### 6.3 Debug points and web streaming

- **Debug point** = a **Debug viewer** node attached to a specific port (input or output of a stage, or source output). That port’s data is the “stream” for that viewer.
- **Per-stage debugging**: The user can add a debug viewer on the **input** of a stage and another on the **output** of the same stage, so they see both sides of that stage. Each stage is debuggable individually; multiple stages can have debug viewers at once (each viewer shows one stream).
- **Web streaming**: The existing stream endpoint (e.g. `GET /stream?camera_id=&stage=...`) is generalized: “stream” is identified by **graph + port** (e.g. algorithm/pipeline instance + node id + port name + input vs output). So “stage X output” and “stage X input” are two distinct stream targets. Backend serves the latest frame at that port when the client requests that stream. Only when a debug viewer is connected (or “subscribed”) to that port do we need to retain/broadcast that frame (optional: retain only ports that have an active debug viewer to save memory).

### 6.4 Data flow summary

| Input to a stage (source)   | Output from a stage (sink)  |
|-----------------------------|-----------------------------|
| Another stage’s output      | Another stage’s input       |
| Live camera (source node)   | Save as video (sink node)   |
| Video file (source node)    | Save as image (sink node)   |
| Image file (source node)    | Debug viewer (web stream)   |

- **Input** to each stage: from a **different stage** (upstream in the graph) or from a **source** (camera, video file, image file).
- **Output** from each stage: to a **different stage** (downstream), or to **save as video**, or to **save as image**, or to a **debug viewer** (web streaming for that port).

### 6.5 Graph representation and persistence

- **Graph model**: The visual editor manipulates a **graph**: nodes (sources, stages, sinks) and edges (wires: output_port_id → input_port_id). Each node has a unique id, type, and port list; each edge has source node+port and target node+port.
- **Persistence**: The graph is the **algorithm** definition (or an extended form of it). Save in config as e.g. `pipeline_graph` or as the canonical representation of an algorithm: nodes + edges + optional positions (for canvas layout). So “algorithm” can be either a linear list of stage_ids (current) or a full graph (visual editor). Backward compat: linear algorithm → one source (camera) + chain of stages + optional sinks; graph algorithm → arbitrary DAG.
- **API**: GET/PUT or PATCH for “pipeline graph” per camera or per algorithm: `GET /api/cameras/{id}/pipeline-graph` (nodes, edges, layout); `PUT /api/cameras/{id}/pipeline-graph` (save graph + persist). Stage settings remain in `stage_settings` as today.

### 6.6 UI behavior (high level)

- **Canvas**: Pan/zoom canvas; drag nodes from a **palette** (Sources, Stages, Sinks) onto the canvas. Drag from an output port to an input port to create a wire; disconnect by clicking the wire and deleting or via context menu.
- **Debug viewers**: From palette, add “Debug viewer” node; connect its input to the desired port (output of stage X or input of stage X). That viewer then shows the stream for that port; the existing web stream API is used to feed the viewer (stream id = graph + node + port).
- **Run**: “Run” or “Start” applies the graph: backend builds the pipeline from the graph (topological order of stages, resolve sources/sinks), starts feeding sources and consuming sinks. Debug viewers receive streams for their connected ports.
- **Save**: Saving the graph persists nodes, edges, and layout; stage settings are already saved via stage-settings API. Graph is stored in camera config or algorithm config.

---

## 7. Implementation phases (suggested)

### Phase 1 — Stage registry and execution type

- Extend **PipelineStagePort** (or stage metadata) with optional **execution_type** (`cpu` | `gpu` | `hybrid`) and a **stage_id** for identity.
- Introduce a **StageRegistry** (in code or loaded from config) that maps `stage_id` → stage factory or instance. Register current stages (preprocess, detect, overlay) with ids and execution types.
- No algorithm model yet: CameraService still builds the pipeline as today (e.g. default stages for use_case `apriltag`), but stages are resolved from the registry by id.

### Phase 2 — Algorithms

- Add **algorithm** definitions (config or code): id, name, list of stage_ids.
- Camera config (or use_case) selects **algorithm_id**. When creating the pipeline for a camera, resolve the algorithm’s stage_ids to stages and pass that list to VisionPipeline.
- Map `use_case: "apriltag"` → default algorithm `apriltag_cpu` so existing configs keep working.

### Phase 2.5 — Stage settings (schema, config, API, UI)

- **Schema**: Define a **SettingSpec** type (key, type, default, min, max, step, options, label, description). Stages that have settings implement `get_settings_schema()`, `get_config()`, `set_config()` (PreprocessAdapter already has get/set_config; add schema).
- **Config**: Add **stage_settings** to camera config; keyed by stage_id, values = settings dict. When building the pipeline, apply `stage_settings[stage_id]` to each stage. When saving from UI, persist into camera config.
- **API**: GET `/api/cameras/{id}/stage-settings` (schema + current values per stage); PATCH `/api/cameras/{id}/stage-settings` (body: stage_id + values; apply to stage and save to config).
- **UI**: “Stage settings” (or “Pipeline settings”) section when a camera with pipeline is selected; for each stage with settings, render a form from schema (sliders, toggles, dropdowns); load from GET, save via PATCH so all settings are shown and saved in config.

### Phase 3 — More algorithms and stages

- Add stage definitions and implementations for: AprilTag hybrid, object detection (CPU/GPU), and optionally vSLAM placeholder stages.
- Add corresponding algorithms that reference these stages. Enable selection in UI/config via algorithm_id or use_case.

### Phase 4 — Debug streaming policy (optional)

- Add optional **retain_stages** (or “debug stages”) per camera: only retain stage outputs for those stages (and raw) to reduce memory when not debugging. When empty/absent, retain all (current behavior).
- UI: “Debug stage” dropdown per camera = which stage’s stream is being viewed; optionally sync that to backend as the single “retain” stage for that camera.

### Phase 5 — Visual pipeline editor (LabVIEW-style)

- **Graph model**: Define **pipeline graph** (nodes + edges). Node types: source (camera, video file, image file), stage (from registry), sink (save video, save image, debug viewer). Edges: output_port → input_port with type checking.
- **Backend**: Persist graph in config (`pipeline_graph`: nodes, edges, layout). API: GET/PUT `/api/cameras/{id}/pipeline-graph` (or per-algorithm). Runtime: build pipeline from graph (topological order; resolve sources/sinks); support “stream by port” (input or output of any stage) for debug viewers. Optional: file sources/sinks (video/image upload, save path).
- **Frontend**: **Canvas** (pan/zoom); **palette** of node types (Sources, Stages, Sinks). Drag nodes onto canvas; draw wires from output port to input port; add Debug viewer nodes and connect to input or output of any stage. Each stage debuggable individually; connect web stream to that port. Save/load graph via API; stage settings still via stage-settings API.
- **Streaming**: Extend stream API so “stream” can be identified by graph + node + port (input vs output). Debug viewer in UI subscribes to that stream and displays it.

---

## 8. File and component layout (suggested)

| Component | Responsibility |
|-----------|----------------|
| `ports/pipeline_stage_port.py` | Keep `PipelineStagePort`; add optional `stage_id`, `execution_type`; optional `get_settings_schema()`, `get_config()`, `set_config()` for configurable stages. |
| `domain/stage_registry.py` (new) | StageRegistry: register stages by id, resolve stage_id → `PipelineStagePort`. Load from config or use code defaults. |
| `domain/algorithm_registry.py` (new) | AlgorithmRegistry: load algorithms (id, name, stage_ids); resolve algorithm_id → list of stage_ids. |
| `domain/vision_pipeline.py` | Unchanged core loop. Accept stages list; optionally accept `retain_stages` to limit which stage outputs are stored. |
| `domain/camera_service.py` | When creating pipeline: get algorithm_id from config/use_case → resolve stage_ids → resolve stages; apply camera’s `stage_settings[stage_id]` to each stage; VisionPipeline(..., stages=...). |
| `config/pipeline_stages.json` (optional) | Stage definitions (id, name, execution_type, adapter, params). |
| `config/pipeline_algorithms.json` (optional) | Algorithm definitions (id, name, stage_ids). |
| `config/cameras/<id>.json` | Camera config including **stage_settings**: `{ "<stage_id>": { "<key>": <value>, ... }, ... }`. All stage settings shown in UI are saved here via PATCH. |
| `adapters/web_server.py` | Stream: valid_stages from pipeline (already done). **Stage settings**: GET/PATCH `/api/cameras/{id}/stage-settings` (return schema + values; apply and persist to camera config). |
| Frontend (e.g. ControlsPane / StageSettings) | “Stage settings” section when camera selected: list stages with settings, render form from schema (sliders, toggles, dropdowns); load GET stage-settings, save via PATCH so settings are stored in config. |
| **Frontend — Visual pipeline editor** | **LabVIEW-style canvas**: palette (Sources: camera, video file, image file; Stages from registry; Sinks: save video, save image, debug viewer). Drag nodes; connect output ports to input ports (wires); type-check connections. Debug viewer node: connect to input or output of any stage → web stream for that port. Save/load graph via GET/PUT pipeline-graph. Each stage debuggable individually. |
| **Backend — Pipeline graph** | **Graph API**: GET/PUT `/api/cameras/{id}/pipeline-graph` (nodes, edges, layout). **Runtime**: build pipeline from graph (topological order); resolve source/sink nodes (camera, file, save, debug). **Stream by port**: stream endpoint accepts graph+node+port (input or output) for debug viewers. Optional: file upload for video/image source; save path for video/image sink. |

---

## 9. Summary

- **Algorithms** = named lists of **stage_ids** (e.g. apriltag_cpu, apriltag_hybrid, object_detection_gpu, vslam), or a **graph** (nodes + edges) when using the visual editor.
- **Stages** = reusable units with **stage_id**, **name**, **execution_type** (cpu/gpu/hybrid), shared across algorithms via a **StageRegistry**. Stages can expose **settings** (schema + get/set config).
- **Stage settings** = per-stage configurable options; schema + GET/PATCH `/api/cameras/{id}/stage-settings`; **saved in camera config** under **stage_settings**; UI shows all settings and persists via PATCH.
- **Pipeline runtime** = VisionPipeline runs a list of stages; list built from algorithm’s stage_ids or **from the graph** (visual editor); stage_settings applied at build time.
- **Debug streaming** = stream by stage name or by **graph + node + port** (input or output of any stage). Each stage **debuggable individually**; web streaming attachable to input or output of each stage.
- **Visual pipeline editor (LabVIEW-style)** = build algorithm in **web GUI**: **nodes** (sources: camera, video file, image file; stages; sinks: save video, save image, debug viewer) and **wires** (output port → input port). **Input** to each stage = from another stage or from video/image/camera. **Output** from each stage = to another stage or **save as video/image** or **debug viewer** (web stream). Debug points connect streaming to **input or output** of any stage; each stage debuggable individually. Graph saved via GET/PUT pipeline-graph.

This keeps the pipeline tightly modular: add or change behavior by defining stages/algorithms in config/code or by **editing the graph in the visual editor**; expose knobs via schema + get/set_config on stages.
