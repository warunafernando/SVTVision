# SVTVision Vision System

SVTVision is a vision system for FRC robotics with a PhotonVision-style web UI for camera discovery, streaming, AprilTag detection, and on-robot debugging.

## Documentation

- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) — Staged execution plan (Stage 0–7+)
- [backend/PIPELINE_MODULARITY.md](./backend/PIPELINE_MODULARITY.md) — Vision pipeline: stages, ports, how to change
- [backend/VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md](./backend/VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md) — Roadmap: algorithms, stages, settings, visual editor (LabVIEW-style)

## Current Status

- **Backend**: FastAPI on port 8080; camera discovery (UVC/V4L2), camera open/close, resolution/controls, AprilTag vision pipeline (preprocess → detect → overlay), WebSocket streaming by stage (raw, preprocess, detect_overlay), debug tree and top faults, config persistence.
- **Frontend**: React/TypeScript (Vite); Cameras page (discovery, open/close, stream viewer with stage tabs, controls, detections), Settings, Self-Test, Debug Tree, Top Faults, console output (time | level | section | message).
- **Vision pipeline**: Modular stage-based pipeline; stages run in order; output per stage available for streaming and debugging. See [PIPELINE_MODULARITY.md](./backend/PIPELINE_MODULARITY.md).

## Project Structure

```
SVTVision/
├── frontend/           # React/TypeScript frontend
├── backend/            # Python/FastAPI backend
├── config/             # Configuration files
├── docs/               # Documentation
├── IMPLEMENTATION_PLAN.md  # Complete implementation plan
└── README.md
```

## Development

### Development Mode (Recommended for Active Development)

**Two servers - fast refresh and hot reload:**

1. **Start Backend** (Terminal 1):
```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=src python3 main.py
```
Backend runs on `http://localhost:8080`

2. **Start Frontend** (Terminal 2):
```bash
cd frontend
npm install
npm run dev
```
Frontend runs on `http://localhost:3000` with hot reload

**Access:** Open `http://localhost:3000` in your browser
- Frontend dev server provides hot reload
- API calls are automatically proxied from port 3000 → 8080

### Production Mode (Single Command Startup)

**One server - production build:**

```bash
./start.sh
```

**Access:** Open `http://localhost:8080` in your browser
- Backend serves the built frontend static files
- Everything on one port (8080)
- Good for testing production build or single-command startup

## Ports Explained

- **Port 3000**: Frontend dev server (Vite) - only in development mode
- **Port 8080**: Backend server (FastAPI) - always used for API, also serves frontend in production mode

**Why two modes?**
- **Dev mode** (3000): Fast development with hot reload, separate frontend/backend servers
- **Prod mode** (8080): Single command startup, backend serves built frontend (as specified in Stage 0)

## Implementation Stages

- **Stage 0**: Repo skeleton + run loop + FE/BE separation — Complete
- **Stage 1**: Camera discovery + deep capabilities — Complete
- **Stage 2**: Camera open/close + raw streaming — Complete
- **Stage 3**: Camera settings (save/apply/verify) — Complete
- **Stage 4**: Vision pipeline + AprilTag detection — Complete
- **Stage 5+**: Health, debug tree quality, validity, advanced features — in progress

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for full details.

## Vision Pipeline (summary)

- Pipeline is **stage-based**: preprocess → detect → overlay (default).
- Stages implement `PipelineStagePort`; pipeline runs a list of stages.
- **Streaming**: Request by stage name (raw, preprocess, detect_overlay) via WebSocket; each stage debuggable separately.
- **Future**: Algorithms + stages registry, stage settings in UI/config, visual pipeline editor (LabVIEW-style). See [VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md](./backend/VISION_PIPELINE_ALGORITHMS_AND_STAGES_PLAN.md).
