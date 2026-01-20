# SVTVision Frontend

PhotonVision-style web UI for SVTVision vision system.

## Features

- **Always-visible layout**:
  - Top Bar: App name, build ID, health indicator, connection status
  - Left Pane: Debug Tree with hierarchical nodes, status colors, metrics
  - Main Pane: Camera viewer with tabs (Raw/Preprocess/Detect Overlay), detections table
  - Right Pane: Camera controls (open/close, resolution, FPS, exposure, gain)

- **Navigation pages**:
  - Cameras (default landing)
  - Settings
  - Self-Test

## Development

### Prerequisites

- Node.js 18+ and npm

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`.

The dev server is configured to proxy API requests to `http://localhost:8080` (backend).

### Build for Production

```bash
npm run build
```

The build output will be in the `dist/` directory.

## Project Structure

```
frontend/
├── src/
│   ├── components/     # Reusable UI components
│   │   ├── TopBar.tsx
│   │   ├── DebugTree.tsx
│   │   ├── ViewerPane.tsx
│   │   └── ControlsPane.tsx
│   ├── pages/          # Page components
│   │   ├── CamerasPage.tsx
│   │   ├── SettingsPage.tsx
│   │   └── SelfTestPage.tsx
│   ├── styles/         # CSS files
│   ├── types/          # TypeScript type definitions
│   ├── utils/          # Utility functions and mock data
│   ├── App.tsx         # Main app component with routing
│   └── main.tsx        # Entry point
├── public/             # Static assets
└── package.json
```

## Mock Data

Currently uses simulated data for Debug Tree nodes (before Stage 0). The backend will provide real data once Stage 0 is implemented.
