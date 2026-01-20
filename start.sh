#!/bin/bash
# Single command startup script for PlanA

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting PlanA..."

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
python3 main.py
