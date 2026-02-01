#!/bin/bash
# Single command startup script for SVTVision

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting SVTVision..."

# Free port 8080 if in use (avoid "address already in use")
if command -v fuser &>/dev/null; then
  fuser -k 8080/tcp 2>/dev/null || true
  sleep 1
fi

# Check if frontend is built
if [ ! -d "frontend/dist" ]; then
    echo "Building frontend..."
    cd frontend
    npm install --quiet
    npm run build
    cd ..
fi

# Check if backend dependencies are installed
if [ ! -d "backend/.venv" ] && [ ! -f "backend/requirements_installed.flag" ]; then
    echo "Installing backend dependencies..."
    cd backend
    python3 -m pip install -r requirements.txt --quiet --break-system-packages
    touch requirements_installed.flag
    cd ..
fi

# Start backend (which will serve frontend in prod mode)
echo "Starting backend server..."
cd backend
if [ -f ".venv/bin/python" ]; then
  .venv/bin/python main.py
else
  python3 main.py
fi
