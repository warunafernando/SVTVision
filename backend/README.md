# SVTVision Backend

Python/FastAPI backend for SVTVision: camera discovery, open/close, streaming, AprilTag vision pipeline, debug tree, and config.

## Structure

```
backend/
├── src/plana/
│   ├── adapters/           # External adapters
│   │   ├── web_server.py   # FastAPI app, REST + WebSocket
│   │   ├── opencv_camera.py
│   │   ├── uvc_v4l2_discovery.py
│   │   ├── preprocess_adapter.py
│   │   ├── apriltag_detector_adapter.py
│   │   ├── mjpeg_encoder.py
│   │   └── selftest_runner.py
│   ├── domain/             # Domain logic
│   │   ├── camera_service.py
│   │   ├── camera_manager.py
│   │   ├── vision_pipeline.py
│   │   ├── camera_discovery.py
│   │   ├── debug_tree.py
│   │   └── debug_tree_manager.py
│   ├── ports/               # Interfaces
│   │   ├── camera_port.py
│   │   ├── camera_discovery_port.py
│   │   ├── preprocess_port.py
│   │   ├── tag_detector_port.py
│   │   ├── pipeline_stage_port.py
│   │   └── stream_encoder_port.py
│   ├── services/
│   │   ├── config_service.py
│   │   ├── logging_service.py
│   │   ├── health_service.py
│   │   ├── message_bus.py
│   │   └── camera_config_service.py
│   └── app_orchestrator.py
├── main.py
├── requirements.txt
├── PIPELINE_MODULARITY.md
└── VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md
```

## Vision pipeline

- **Modular stages**: Preprocess → Detect → Overlay (default). Stages implement `PipelineStagePort`; pipeline runs a list of stages.
- **Streaming**: WebSocket stream by stage (`raw`, `preprocess`, `detect_overlay`).
- **Docs**: [PIPELINE_MODULARITY.md](./PIPELINE_MODULARITY.md) — how to change stages; [VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md](./VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md) — algorithms, stage settings, visual editor roadmap.

## API (summary)

| Endpoint | Description |
|----------|-------------|
| `GET /api/system` | App name, build ID |
| `GET /api/debug/tree` | Debug tree structure |
| `GET /api/debug/top-faults` | Top faults from debug tree |
| `GET /api/selftest/run` | Run self-test |
| `GET /api/cameras` | Discovered cameras |
| `GET /api/cameras/{id}` | Camera details |
| `GET /api/cameras/{id}/capabilities` | Camera capabilities |
| `GET /api/cameras/{id}/controls` | Camera controls |
| `GET /api/cameras/{id}/settings` | Current settings |
| `GET /api/cameras/{id}/detector-config` | Detector/use_case config |
| `GET /api/cameras/{id}/preprocessing-config` | Preprocessing config |
| `POST /api/cameras/{id}/settings` | Apply settings |
| `POST /api/cameras/{id}/open` | Open camera |
| `POST /api/cameras/{id}/close` | Close camera |
| `GET /api/cameras/{id}/status` | Open/closed, resolution, FPS |
| `GET /api/cameras/{id}/detection_stats` | Detection stats |
| `POST /api/cameras/{id}/controls` | Set controls |
| `WebSocket /ws/stream?camera=&stage=` | Video stream (raw / preprocess / detect_overlay) |

## Run

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=src python3 main.py
```

Server: `http://localhost:8080` (or `http://127.0.0.1:8080`).
