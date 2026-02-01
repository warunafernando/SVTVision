"""
Pipeline Builder - Stage 6, 7, 8.
Builds VisionPipeline from ExecutionPlan by resolving stage_ids to PipelineStagePort instances.
Also creates StreamTaps (Stage 7) and SaveVideo/SaveImage sinks (Stage 8).
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from ..ports.pipeline_stage_port import PipelineStagePort
from ..services.logging_service import LoggingService
from .vision_pipeline import VisionPipeline
from .runtime_compiler import ExecutionPlan
from .stream_tap import StreamTap
from .save_sinks import SaveVideoSink, SaveImageSink


# Map stage_id → stage name (used by _PreprocessStage, _DetectStage, etc.)
STAGE_ID_TO_NAME = {
    "preprocess_cpu": "preprocess",
    "detect_apriltag_cpu": "detect",
    "overlay_cpu": "detect_overlay",
}


def build_pipeline_from_plan_with_nodes(
    plan: ExecutionPlan,
    nodes: List[Dict[str, Any]],
    logger: LoggingService,
) -> Optional[VisionPipeline]:
    """
    Build VisionPipeline from ExecutionPlan + node list (for stage_id lookup).
    Does NOT create StreamTaps - use build_pipeline_with_taps for that.
    """
    result = build_pipeline_with_taps(plan, nodes, logger)
    return result[0] if result else None


def build_pipeline_with_taps(
    plan: ExecutionPlan,
    nodes: List[Dict[str, Any]],
    logger: LoggingService,
) -> Optional[Tuple[VisionPipeline, List[StreamTap], List[Union[SaveVideoSink, SaveImageSink]]]]:
    """
    Build VisionPipeline + StreamTaps + SaveVideo/SaveImage sinks from ExecutionPlan.
    Returns (pipeline, stream_taps, save_sinks) or None if build fails.
    Caller must call close() on save_sinks when pipeline stops.
    """
    from ..adapters.preprocess_adapter import PreprocessAdapter
    from ..adapters.apriltag_detector_adapter import AprilTagDetectorAdapter
    from .vision_pipeline import _PreprocessStage, _DetectStage, _OverlayStage

    node_by_id = {n.get("id", ""): n for n in nodes}
    node_configs = plan.node_configs or {}
    stages: List[PipelineStagePort] = []
    node_id_to_stage_name: Dict[str, str] = {}

    preprocessor = PreprocessAdapter(logger)
    tag_family = "tag36h11"
    for node in nodes:
        if node.get("stage_id") == "detect_apriltag_cpu":
            cfg = node_configs.get(node.get("id", ""), {})
            tag_family = str(cfg.get("tag_family", "tag36h11"))
            break
    tag_detector = AprilTagDetectorAdapter(logger, family=tag_family)

    for node_id in plan.main_path:
        node = node_by_id.get(node_id)
        if not node:
            continue
        ntype = node.get("type", "")
        stage_id = node.get("stage_id") or node.get("id", "")

        if ntype == "source" or ntype == "sink":
            continue

        if ntype != "stage":
            continue

        config = node_configs.get(node_id, {})
        if not config:
            config = {}

        stage_name = STAGE_ID_TO_NAME.get(stage_id)
        if stage_id == "preprocess_cpu":
            preprocessor.set_config({
                "blur_kernel_size": config.get("blur_kernel_size", 3),
                "adaptive_block_size": config.get("adaptive_block_size", 15),
                "adaptive_c": config.get("adaptive_c", 3),
                "threshold_type": config.get("threshold_type", "adaptive"),
                "morphology": config.get("morphology", False),
            })
            stages.append(_PreprocessStage(preprocessor))
            node_id_to_stage_name[node_id] = "preprocess"
        elif stage_id == "detect_apriltag_cpu":
            stages.append(_DetectStage(tag_detector))
            node_id_to_stage_name[node_id] = "detect"
        elif stage_id == "overlay_cpu":
            stages.append(_OverlayStage(tag_detector))
            node_id_to_stage_name[node_id] = "detect_overlay"
        else:
            logger.warning(f"[PipelineBuilder] Unknown stage_id: {stage_id}, skipping")
            return None

    if not stages:
        logger.warning("[PipelineBuilder] No stages built")
        return None

    # Stage 7 & 8: Create StreamTaps and SaveVideo/SaveImage sinks for side taps
    stream_taps: List[StreamTap] = []
    save_sinks: List[Union[SaveVideoSink, SaveImageSink]] = []
    side_taps_by_stage: Dict[str, List[Any]] = {}  # Any = StreamTap | SaveVideoSink | SaveImageSink (push_frame)

    for side_tap in plan.side_taps:
        attach_stage = node_id_to_stage_name.get(side_tap.attach_point)
        if not attach_stage:
            logger.warning(f"[PipelineBuilder] Side tap attach_point {side_tap.attach_point} not found in stages")
            continue
        if attach_stage not in side_taps_by_stage:
            side_taps_by_stage[attach_stage] = []

        config = plan.node_configs.get(side_tap.node_id, {})

        if side_tap.sink_type == "stream_tap":
            tap = StreamTap(tap_id=side_tap.node_id, attach_point=side_tap.attach_point)
            stream_taps.append(tap)
            side_taps_by_stage[attach_stage].append(tap)
            logger.info(f"[PipelineBuilder] Created StreamTap {tap.tap_id} attached to {attach_stage}")
        elif side_tap.sink_type == "save_video":
            path = config.get("path") or config.get("output_path") or f"output_{side_tap.node_id}.mp4"
            fps = float(config.get("fps", 30.0))
            sink = SaveVideoSink(
                sink_id=side_tap.node_id,
                attach_point=side_tap.attach_point,
                output_path=path,
                fps=fps,
                logger=logger,
            )
            save_sinks.append(sink)
            side_taps_by_stage[attach_stage].append(sink)
            logger.info(f"[PipelineBuilder] Created SaveVideoSink {sink.sink_id} -> {path}")
        elif side_tap.sink_type == "save_image":
            path = config.get("path") or config.get("output_path") or f"output_{side_tap.node_id}.jpg"
            mode = str(config.get("mode", "overwrite"))
            sink = SaveImageSink(
                sink_id=side_tap.node_id,
                attach_point=side_tap.attach_point,
                output_path=path,
                mode=mode,
                logger=logger,
            )
            save_sinks.append(sink)
            side_taps_by_stage[attach_stage].append(sink)
            logger.info(f"[PipelineBuilder] Created SaveImageSink {sink.sink_id} -> {path}")

    pipeline = VisionPipeline.from_stages(stages, logger, stream_taps=side_taps_by_stage)
    return (pipeline, stream_taps, save_sinks)
