# PlanA Backend

Backend services for PlanA vision system.

## Structure

```
backend/
├── src/
│   └── plana/
│       ├── services/          # Core services
│       │   ├── logging_service.py
│       │   ├── config_service.py
│       │   ├── health_service.py
│       │   └── message_bus.py
│       ├── domain/            # Domain models
│       │   ├── debug_tree.py
│       │   └── debug_tree_manager.py
│       ├── adapters/          # External adapters
│       │   ├── web_server.py
│       │   └── selftest_runner.py
│       ├── app_orchestrator.py
│       └── __init__.py
├── main.py                    # Entry point
└── requirements.txt
```

## Services

- **AppOrchestrator**: Coordinates application startup and lifecycle
- **ConfigService**: Manages application configuration
- **HealthService**: Tracks system and component health
- **MessageBus**: Pub/sub message bus for component communication
- **LoggingService**: Application-wide logging
- **DebugTreeManager**: Manages debug tree with simulated nodes (Stage 0)

## API Endpoints

- `GET /api/system` - System information
- `GET /api/debug/tree` - Debug tree structure
- `GET /api/selftest/run?test=<name>` - Run self-test

## Development

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Server

```bash
python3 main.py
```

Server runs on `http://localhost:8080` by default.

## Stage 0 Status

✅ All Stage 0 requirements implemented:
- Repo skeleton created
- All services initialized
- API endpoints working
- Frontend static file serving
- Self-test runner stub
