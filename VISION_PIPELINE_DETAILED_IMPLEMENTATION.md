# Visual Vision Pipeline – Detailed Implementation (v1)

## v1 Constraints
- Single source
- DAG only
- Ports carry frame_bgr8 only
- Each stage: frame → frame
- SVTVisionOutput required and terminal

## Data Model
Algorithm = { id, name, schema_version, graph }

Graph = nodes + edges + layout

## Node Types
- Source: camera | video | image
- Stage: stage_id resolved from StageRegistry
- Sink: stream, save_video, save_image, svtvision

## Stage Registry
- Registers all stages
- Provides settings schema
- Instantiates runtime stages

## Runtime Compilation
1. Validate graph
2. Extract main path
3. Attach side taps
4. Build execution plan

## Execution Loop
For each frame:
- Run through main path stages
- Dispatch frame to side taps
- Publish to SVTVisionOutput

## Streaming
- StreamTap holds latest frame
- UI connects via WebSocket

## Saving
- SaveVideo / SaveImage consume frames and pass through

## Error Handling
- Validation blocks run
- Runtime errors stop instance safely

## Extensibility
- Multi-port stages
- Detection/pose data
- GPU async stages
