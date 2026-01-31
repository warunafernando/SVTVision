# Vision Pipeline Modularity

The vision pipeline is built so you can **change stages easily** without editing core logic.

## Architecture

- **Ports** (interfaces): `PreprocessPort`, `TagDetectorPort`, `PipelineStagePort`
- **VisionPipeline**: runs a **list of stages** in order; each stage has `name` and `process(frame, context) -> (frame, context)`.
- **Stage adapters**: `_PreprocessStage`, `_DetectStage`, `_OverlayStage` wrap `PreprocessPort` / `TagDetectorPort` and implement `PipelineStagePort`.

## Flow

1. **Raw** frame is stored; grayscale is passed into the stage list.
2. **Preprocess** stage: `PreprocessPort.preprocess(gray)` → preprocessed frame.
3. **Detect** stage: `TagDetectorPort.detect(preprocessed)` → fills `context["detections"]`; frame unchanged.
4. **Overlay** stage: `TagDetectorPort.draw_overlay(raw_frame, context["detections"])` → overlay frame.

`context` carries `raw_frame` and `detections` between stages.

## How to change the pipeline

### Reorder stages

Edit `_default_stages()` in `domain/vision_pipeline.py` and change the list order:

```python
def _default_stages(preprocessor, tag_detector):
    return [
        _PreprocessStage(preprocessor),
        _DetectStage(tag_detector),
        _OverlayStage(tag_detector),
    ]
```

### Add a new stage

1. Implement `PipelineStagePort` in a new class (e.g. in `domain/vision_pipeline.py` or an adapter module):

   ```python
   class MyStage(PipelineStagePort):
       @property
       def name(self) -> str:
           return "my_stage"
       def process(self, frame, context):
           # ... do work, update context if needed
           return output_frame, context
   ```

2. Append it to the list in `_default_stages()` or pass a custom `stages=` list into `VisionPipeline(..., stages=[...])`.

### Swap detector

- Keep using `VisionPipeline(preprocessor, tag_detector, logger)`.
- Pass a different adapter that implements `TagDetectorPort` (e.g. another AprilTag backend or a different detector). `_DetectStage` and `_OverlayStage` use whatever `TagDetectorPort` you inject.

### Custom stage list (no preprocessor/tag_detector)

```python
from plana.domain.vision_pipeline import VisionPipeline

stages = [MyPreprocessStage(), MyDetectStage(), MyOverlayStage()]
pipeline = VisionPipeline(None, None, logger, stages=stages)
```

When `stages` is provided, `preprocessor` and `tag_detector` can be `None` (they are only used to build the default list when `stages` is `None`). Ensure your custom stages match the expected `context` keys (`raw_frame`, `detections`) if you rely on overlay.

## Files

| File | Role |
|------|------|
| `ports/pipeline_stage_port.py` | `PipelineStagePort` interface |
| `ports/preprocess_port.py` | `PreprocessPort` interface |
| `ports/tag_detector_port.py` | `TagDetectorPort`, `TagDetection` |
| `domain/vision_pipeline.py` | `VisionPipeline`, `_PreprocessStage`, `_DetectStage`, `_OverlayStage`, `_default_stages()` |
| `adapters/preprocess_adapter.py` | Implements `PreprocessPort` |
| `adapters/apriltag_detector_adapter.py` | Implements `TagDetectorPort` |

## Public API

- `VisionPipeline(preprocessor, tag_detector, logger)` — same constructor; optional `stages=` for custom list.
- `process_frame(raw_frame) -> dict`: always has `"raw"` and `"detections"`; plus one key per stage (`out[stage.name]`). Default pipeline: `"raw"`, `"preprocess"`, `"detect"`, `"detect_overlay"`, `"detections"`.
- `get_latest_frame(stage: str) -> Optional[StageFrame]`: `stage` is `"raw"` or any `stage.name` from the pipeline.
- `get_latest_detections() -> List[TagDetection]`
- `get_metrics() -> Dict`

CameraService and CameraManager do not need changes; they keep building the pipeline with `PreprocessAdapter` and `AprilTagDetectorAdapter`. The stream API validates stage names from the pipeline’s stage list (`valid_stages = ["raw"] + [s.name for s in pipeline._stages]`).
