#!/usr/bin/env python3
"""Main entry point for PlanA backend."""

import sys
from pathlib import Path
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from plana.app_orchestrator import AppOrchestrator


def main():
    """Main entry point."""
    # Paths
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"
    frontend_dist = project_root / "frontend" / "dist"
    
    # Create orchestrator
    orchestrator = AppOrchestrator(config_dir, frontend_dist)
    
    # Start application
    app = orchestrator.start()
    
    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )


if __name__ == "__main__":
    main()
