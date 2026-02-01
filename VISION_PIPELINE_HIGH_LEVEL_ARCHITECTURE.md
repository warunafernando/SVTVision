# Visual Vision Pipeline – High-Level Architecture (v1)

## Purpose
Define the high-level architecture for a LEGO/LabVIEW-style visual vision pipeline in SVTVision.

## Core Principles
- Visual-first pipeline construction
- Algorithms are saved graphs
- Stages are reusable processing blocks
- Single source, DAG only (v1)
- Frame-only data type: frame_bgr8
- Production-safe execution

## Key Concepts
- Algorithm: Persisted graph of nodes and wires
- Nodes: Sources, Stages, Sinks
- Sources: Camera, Video, Image (exactly one)
- Stages: frame → frame processing blocks
- Sinks: StreamTap, SaveVideo, SaveImage, SVTVisionOutput

## Data Flow Model
- One main execution path: Source → SVTVisionOutput
- Zero or more side taps for streaming/saving
- Fan-out allowed, no fan-in

## Visual Editor Layout
- Left: Node Palette
- Center: Pipeline Canvas
- Right: Properties & Controls
- Stream viewer for live debug

## Production Integration
- Algorithms run via VisionPipelineManager
- Same algorithm usable for camera, video, or image inputs

## Non-Goals (v1)
- Multiple sources
- Loops
- Non-frame data types
- In-browser arbitrary code execution
