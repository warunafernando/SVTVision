"""
Pipeline Builder - Stage 6, 7, 8.
Builds VisionPipeline from ExecutionPlan by resolving stage_ids to PipelineStagePort instances.
Also creates StreamTaps (Stage 7) and SaveVideo/SaveImage sinks (Stage 8).
"""

import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from ..ports.pipeline_stage_port import PipelineStagePort
from ..services.logging_service import LoggingService
from .vision_pipeline import VisionPipeline
from .runtime_compiler import ExecutionPlan
from .stream_tap import StreamTap
from .save_sinks import SaveVideoSink, SaveImageSink


# Default directory for SaveVideo/SaveImage when path is missing or relative
DEFAULT_SAVE_DIR = "/home/svt/Documents"


def _random_output_filename(ext: str) -> str:
    """Return a random filename under DEFAULT_SAVE_DIR: output_<timestamp>_<random>.<ext>."""
    base = f"output_{int(time.time() * 1000)}_{random.randint(10000, 99999)}"
    return f"{base}.{ext}"


def _resolve_save_path(config: Dict[str, Any], default_ext: str) -> str:
    """Resolve output path: use config path if absolute, else DEFAULT_SAVE_DIR/<random filename>."""
    raw = (config.get("path") or config.get("output_path") or "").strip()
    if raw and os.path.isabs(raw):
        return raw
    if raw:
        name = os.path.basename(raw)
    else:
        name = _random_output_filename(default_ext)
    return os.path.join(DEFAULT_SAVE_DIR, name)


# Map stage_id → stage name (used by _PreprocessStage, _DetectStage, etc.)
STAGE_ID_TO_NAME = {
    "preprocess_cpu": "preprocess",
    "preprocess_gpu": "preprocess",
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
    from ..adapters.gpu_preprocess_adapter import GpuPreprocessAdapter
    from ..adapters.apriltag_detector_adapter import AprilTagDetectorAdapter
    from .vision_pipeline import _PreprocessStage, _DetectStage, _OverlayStage

    node_by_id = {n.get("id", ""): n for n in nodes}
    node_configs = plan.node_configs or {}
    stages: List[PipelineStagePort] = []
    node_id_to_stage_name: Dict[str, str] = {}

    preprocessor_cpu = PreprocessAdapter(logger)
    preprocessor_gpu = GpuPreprocessAdapter(logger)
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

        # Prefer raw node config from request (what the user set in the UI); fallback to plan's node_configs
        raw_config = node.get("config")
        if isinstance(raw_config, dict):
            config = dict(raw_config)
        else:
            config = dict(node_configs.get(node_id, {}))
        # Ensure defaults for preprocess so adapter always gets all keys
        if stage_id in ("preprocess_cpu", "preprocess_gpu"):
            _preprocess_defaults = {
                "blur_kernel_size": 3, "adaptive_block_size": 15, "adaptive_c": 3,
                "threshold_type": "adaptive", "adaptive_thresholding": False, "contrast_normalization": False,
                "binary_threshold": 127, "morphology": False, "morph_kernel_size": 3,
            }
            for k, v in _preprocess_defaults.items():
                if k not in config:
                    config[k] = v
            logger.info(
                f"[PipelineBuilder] Preprocess {stage_id} node_id={node_id}: "
                f"blur={config.get('blur_kernel_size')} adaptive_thr={config.get('adaptive_thresholding')} "
                f"contrast_norm={config.get('contrast_normalization')} morph={config.get('morphology')}"
            )
        stage_name = STAGE_ID_TO_NAME.get(stage_id)
        if stage_id == "preprocess_cpu":
            preprocessor_cpu.set_config({
                "blur_kernel_size": config.get("blur_kernel_size", 3),
                "adaptive_block_size": config.get("adaptive_block_size", 15),
                "adaptive_c": config.get("adaptive_c", 3),
                "threshold_type": config.get("threshold_type", "adaptive"),
                "adaptive_thresholding": config.get("adaptive_thresholding", False),
                "contrast_normalization": config.get("contrast_normalization", False),
                "binary_threshold": config.get("binary_threshold", 127),
                "morphology": config.get("morphology", False),
                "morph_kernel_size": config.get("morph_kernel_size", 3),
            })
            stages.append(_PreprocessStage(preprocessor_cpu))
            node_id_to_stage_name[node_id] = "preprocess"
        elif stage_id == "preprocess_gpu":
            preprocessor_gpu.set_config({
                "blur_kernel_size": config.get("blur_kernel_size", 3),
                "adaptive_block_size": config.get("adaptive_block_size", 15),
                "adaptive_c": config.get("adaptive_c", 3),
                "threshold_type": config.get("threshold_type", "adaptive"),
                "adaptive_thresholding": config.get("adaptive_thresholding", False),
                "contrast_normalization": config.get("contrast_normalization", False),
                "binary_threshold": config.get("binary_threshold", 127),
                "morphology": config.get("morphology", False),
                "morph_kernel_size": config.get("morph_kernel_size", 3),
            })
            stages.append(_PreprocessStage(preprocessor_gpu))
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

    # Stage 7 & 8: Create StreamTaps and SaveVideo/SaveImage sinks for side taps
    stream_taps: List[StreamTap] = []
    save_sinks: List[Union[SaveVideoSink, SaveImageSink]] = []
    side_taps_by_stage: Dict[str, List[Any]] = {}  # Any = StreamTap | SaveVideoSink | SaveImageSink (push_frame)

    main_path_set = set(plan.main_path)

    for side_tap in plan.side_taps:
        attach_stage = node_id_to_stage_name.get(side_tap.attach_point)
        if not attach_stage:
            # Attach point may be the source node (no stage): use special key for raw frame taps
            if side_tap.attach_point in main_path_set:
                attach_stage = "__source__"
            else:
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
            path = _resolve_save_path(config, "mp4")
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
            path = _resolve_save_path(config, "jpg")
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

    # When graph has no StreamTap (e.g. Camera → SaveVideo only), add a preview tap so user can see video
    if not stream_taps and plan.main_path:
        source_node_id = plan.main_path[0]
        preview_tap = StreamTap(tap_id="preview", attach_point=source_node_id)
        stream_taps.append(preview_tap)
        if "__source__" not in side_taps_by_stage:
            side_taps_by_stage["__source__"] = []
        side_taps_by_stage["__source__"].append(preview_tap)
        logger.info("[PipelineBuilder] Added preview StreamTap (no StreamTap in graph)")

    # Allow zero stages when graph is source → StreamTap only (we have __source__ taps)
    if not stages and "__source__" not in side_taps_by_stage:
        logger.warning("[PipelineBuilder] No stages and no source taps built")
        return None

    pipeline = VisionPipeline.from_stages(stages, logger, stream_taps=side_taps_by_stage)
    return (pipeline, stream_taps, save_sinks)
