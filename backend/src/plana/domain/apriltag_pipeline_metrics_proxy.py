"""AprilTag-only pipeline metrics proxy.

Purpose:
- DO NOT change the core VisionPipeline implementation.
- For the AprilTag pipeline only, expose a breakdown of detect() time
  alongside existing stage timings (preprocess/detect/detect_overlay).

How:
- Wrap a VisionPipeline instance and delegate everything except get_metrics().
- In get_metrics(), inject extra keys into metrics["stage_timings_ms"] using the
  detector's last detect() breakdown:
    - detect.ensure_grayscale
    - detect.to_uint8
    - detect.apriltag_detect_call
    - detect.convert_results
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ApriltagPipelineMetricsProxy:
    def __init__(self, inner_pipeline: Any, tag_detector: Any):
        self._inner = inner_pipeline
        self._tag_detector = tag_detector

    # ---- Delegate pipeline API used across the project ----
    def process_frame(self, raw_frame):
        return self._inner.process_frame(raw_frame)

    def get_latest_frame(self, stage: str):
        return self._inner.get_latest_frame(stage)

    def get_latest_detections(self):
        return self._inner.get_latest_detections()

    def update_preprocess_config(self, config: Dict[str, Any]) -> bool:
        return self._inner.update_preprocess_config(config)

    def update_tag_detector_config(self, config: Dict[str, Any]) -> bool:
        return self._inner.update_tag_detector_config(config)

    def get_tag_detector_config(self) -> Optional[Dict[str, Any]]:
        return self._inner.get_tag_detector_config()

    # ---- Metrics injection (AprilTag pipeline only) ----
    def get_metrics(self) -> Dict[str, Any]:
        metrics = self._inner.get_metrics()

        stage_timings = metrics.get("stage_timings_ms")
        if not isinstance(stage_timings, dict):
            return metrics

        parts = None
        if self._tag_detector is not None and hasattr(self._tag_detector, "get_last_detect_parts_ms"):
            try:
                parts = self._tag_detector.get_last_detect_parts_ms()
            except Exception:
                parts = None

        if isinstance(parts, dict) and parts:
            # Add breakdown keys alongside preprocess/detect/detect_overlay
            # Use the latest observed values (ms) and round for readability.
            for k in ("ensure_grayscale", "to_uint8", "apriltag_detect_call", "convert_results"):
                if k in parts:
                    try:
                        stage_timings[f"detect.{k}"] = round(float(parts[k]), 1)
                    except Exception:
                        continue

            # CUDA-specific (if present): these are provided by CUDA adapter.
            for k in ("gpu_stage_ms", "cpu_decode_ms", "detector_total_ms"):
                if k in parts:
                    try:
                        stage_timings[f"detect.{k}"] = round(float(parts[k]), 1)
                    except Exception:
                        continue
            # num_quads is a COUNT, not ms; keep it out of stage_timings_ms so UI doesn't misread it.
            if "num_quads" in parts:
                try:
                    metrics["detect_num_quads"] = int(round(float(parts["num_quads"])))
                except Exception:
                    pass

            # Optional: keep a convenient subtotal for the detect() breakdown
            try:
                subtotal = 0.0
                for k in ("ensure_grayscale", "to_uint8", "apriltag_detect_call", "convert_results"):
                    if k in parts:
                        subtotal += float(parts[k])
                stage_timings["detect.parts_total"] = round(subtotal, 1)
            except Exception:
                pass

        metrics["stage_timings_ms"] = stage_timings
        return metrics

