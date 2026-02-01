# Visual Vision Pipeline – Cursor Implementation & Validation (v1)

## Purpose
Step-by-step Cursor execution plan with tests and validation.

## Stage 0 – Skeleton
- Add /vision-pipeline UI route
- Backend /api/vp stubs

## Stage 1 – Graph Model
- Graph data structures
- DAG + single-source validation
- Unit tests for invalid graphs

## Stage 2 – Canvas
- Drag/drop nodes
- Wire connections
- Enforce single input rule

## Stage 3 – Stage Registry
- Backend registry
- Dynamic palette
- Unit tests for discovery

## Stage 4 – Algorithm Store
- Save/load graph JSON
- Persistence tests

## Stage 5 – Runtime Compiler
- Main path + side tap extraction
- Unit tests

## Stage 6 – Execution
- Frame loop
- Integration with camera/video

## Stage 7 – StreamTap
- WebSocket streaming
- Reconnect tests

## Stage 8 – SaveVideo / SaveImage
- File output validation

## Stage 9 – New Stage Workflow
- Plugin-based stage addition
- Palette auto-update

## Acceptance Criteria
- AprilTag CPU algorithm built, saved, run, and streamed successfully
