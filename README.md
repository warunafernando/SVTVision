# SVTVision Vision System

SVTVision is a vision system for FRC robotics with a PhotonVision-style web UI for rapid on-robot debugging.

## Implementation Plan

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for the complete execution plan.

## Current Status

**Stage 0 Complete**: ✅ Backend and frontend integrated.

- Backend services fully implemented (AppOrchestrator, ConfigService, MessageBus, HealthService, LoggingService)
- API endpoints: `/api/system`, `/api/debug/tree`, `/api/selftest/run`
- Frontend fetches data from backend API
- Debug Tree with simulated nodes visible in UI
- Single command startup via `./start.sh`
- Self-test endpoint returns `pass=true`

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
python3 main.py
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

The project follows a staged implementation plan:

- **Stage 0**: Repo skeleton + run loop + FE/BE separation ✅ **COMPLETE**
- **Stage 1**: Camera discovery + deep capabilities
- **Stage 2**: Camera open/close + raw streaming
- **Stage 3**: Camera settings (save/apply/verify)
- **Stage 4**: Vision pipeline + AprilTag detection
- **Stage 5**: Health + Debug Tree root-cause quality
- **Stage 6**: Validity envelope
- **Stage 7+**: Advanced features

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for complete details.
