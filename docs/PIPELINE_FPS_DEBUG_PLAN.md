# Pipeline FPS Debug Plan: Why 12 FPS and How to Increase It

**Context:** The AprilTag pipeline reports ~12 FPS while target is 50 FPS (camera config). This document outlines a plan to debug the bottleneck and increase throughput.

---

## 1. Current Architecture Summary

| Component | Implementation | Notes |
|-----------|----------------|-------|
| **Resolution** | 1920×1200 @ 50 fps | ~2.3M pixels per frame (config: `cameras.json`) |
| **Capture** | OpenCV `VideoCapture.read()` | CPU, single thread round-robin |
| **raw_frame_queue** | `maxsize=1` | One frame per camera; consumer must keep up or frames drop |
| **Preprocess** | `PreprocessAdapter` (CPU) | Gaussian blur, adaptive threshold on full res |
| **AprilTag detect** | `AprilTagDetectorAdapter` (CPU) | `apriltag` C library, `quad_decimate=1.0`, `nthreads=1` |
| **Overlay** | OpenCV draw (CPU) | Draw corners, IDs on frame |
| **Encode** | `encode_frame_to_jpeg` (nvJPEG when available) | GPU; may have host↔device copy |
| **Consumer** | `_vision_pipeline_loop` | Single thread, `ThreadPoolExecutor` for parallel cameras |

---

## 2. Hypothesized Bottlenecks (Most Likely First)

### 2.1 AprilTag CPU detection (primary suspect)
- **Why:** CPU AprilTag at full resolution (2.3M pixels) is known to be slow; 12 FPS is typical for 1920×1200.
- **Evidence:** `quad_decimate=1.0` = full resolution; `nthreads=1` limits CPU parallelism.
- **Quick win:** Increase `quad_decimate` to 2.0 (4× fewer pixels) or 4.0; increase `nthreads` to 2–4.

### 2.2 Preprocess (CPU)
- **Why:** `cv2.adaptiveThreshold` on 1920×1200 is expensive; Gaussian blur scales with pixels.
- **Evidence:** Preprocess runs before detect on full-resolution frame.
- **Quick win:** Use GPU preprocess (`preprocess_gpu` / `CUDAPreprocessAdapter`) if available; or reduce resolution before preprocess.

### 2.3 Resolution
- **Why:** 1920×1200 is large; all stages (preprocess, detect, overlay, encode) scale with resolution.
- **Quick win:** Run AprilTag at lower resolution (e.g. 960×600) if camera supports it; or downscale before pipeline.

### 2.4 Consumer loop / threading
- **Why:** `sleep(0.01)` when no work; single consumer; GIL may serialize CPU work.
- **Evidence:** Parallel cameras use `ThreadPoolExecutor`, but AprilTag is CPU-bound and GIL limits gains.
- **Quick win:** Ensure no unnecessary sleeps; verify capture is not starved.

### 2.5 Capture vs consumer contention
- **Why:** `raw_frame_queue` maxsize=1; if consumer is slow, capture overwrites and drops frames.
- **Evidence:** `frames_dropped` in metrics; `last_frame_time` drives FPS calc.
- **Note:** Dropping frames is expected when pipeline can’t keep up; the fix is speeding the pipeline, not the queue.

### 2.6 JPEG encode / GPU transfer
- **Why:** If frame is on CPU, nvJPEG may require upload; composite debug frames may add extra work.
- **Lower priority:** Likely small compared to AprilTag+preprocess.

---

## 3. Instrumentation Plan (Measure Before Optimizing)

### 3.1 Add per-stage wall-clock timing
Instrument `VisionPipeline.process_frame()` and `CameraManager._run_pipeline_on_frame()`:

- `t_preprocess` (ms)
- `t_detect` (ms)
- `t_overlay` (ms)
- `t_encode` (ms)
- `t_total` (ms)

Log or expose via metrics (e.g. `/api/apriltag/status` → `stage_timings_ms`).

### 3.2 Add consumer-loop timing
In `_vision_pipeline_loop`:
- Time from `get_raw_frame` to completion per camera
- Count frames processed per second over a 1s window
- Log `processed_any` vs `sleep(0.01)` frequency

### 3.3 Add capture metrics
- `frames_dropped` per camera (already exists)
- Capture loop iteration rate (optional)

### 3.4 Expected outcome
After instrumentation:
- If `t_detect` dominates (e.g. >60 ms) → AprilTag is bottleneck → apply §4.1–4.3
- If `t_preprocess` dominates → preprocess bottleneck → apply §4.4–4.5
- If `t_encode` dominates → encode/transfer bottleneck → apply §4.6

---

## 4. Optimization Plan (Ranked by Impact / Effort)

### 4.1 Increase AprilTag `quad_decimate` (high impact, low effort)
**File:** `backend/src/plana/adapters/apriltag_detector_adapter.py`

- Change `quad_decimate=1.0` → `2.0` (or make configurable via API).
- `quad_decimate=2.0` → 4× fewer pixels → ~2–4× faster detect, with some loss in small-tag range.
- `quad_decimate=4.0` → 16× fewer pixels → even faster; test detection accuracy.

**Config:** Add `quad_decimate` to AprilTag settings (API + UI) so it can be tuned without code change.

### 4.2 Increase AprilTag `nthreads` (medium impact, low effort)
**File:** `backend/src/plana/adapters/apriltag_detector_adapter.py`

- Change `nthreads=1` → `2` or `4` (match CPU cores).
- AprilTag library can use multiple threads for quad detection.

**Config:** Add `nthreads` to AprilTag settings.

### 4.3 Lower AprilTag input resolution (high impact, medium effort)
**Options:**
- **A.** Configure camera for 960×600 (or similar) when `use_case=apriltag`.
- **B.** Downscale frame before pipeline: e.g. `cv2.resize(..., (960, 600))` at pipeline entry; run AprilTag on smaller frame; scale detections back for overlay.
- **C.** Use `quad_decimate` as a soft downscale (already in §4.1).

**Config:** Add `apriltag_resolution` or `downscale_factor` to pipeline/API settings.

### 4.4 Use GPU preprocess (medium impact, medium effort)
**Current:** Default AprilTag pipeline uses `PreprocessAdapter` (CPU).

**Change:** Use `preprocess_gpu` / `CUDAPreprocessAdapter` or `GpuPreprocessAdapter` when building the AprilTag pipeline, if the stage registry and builder support it.

**File:** `backend/src/plana/domain/camera_service.py` — where `VisionPipeline` is built for `use_case=apriltag`.

**Note:** Requires CuPy/OpenCV CUDA; fallback to CPU if unavailable.

### 4.5 Simplify preprocess (low–medium impact, low effort)
**File:** `backend/src/plana/adapters/preprocess_adapter.py`

- Reduce `adaptive_block_size` (e.g. 15 → 11) if quality allows.
- Use binary threshold instead of adaptive when possible (faster).
- Reduce `blur_kernel_size` (e.g. 3 → 1 or 0) if edges remain acceptable.

**Config:** Expose these in API; allow A/B testing.

### 4.6 Minimize GPU↔CPU copies (low impact, medium effort)
- Keep frames on GPU through preprocess → detect (when AprilTag GPU is available).
- Ensure overlay output can be passed to nvJPEG without a round-trip to CPU when possible.
- **Long-term:** AprilTag CUDA (§4.7) keeps whole pipeline on GPU.

### 4.7 AprilTag CUDA (high impact, high effort)
**Per:** `docs/APRILTAG_GPU_PIPELINE_PLAN.md` Phase 2–4.

- Integrate `AprilTag_CUDA_X86` or equivalent GPU detector.
- Run detect on GPU; avoid download for CPU detector.
- Target: 30–50+ FPS at 1920×1200.

---

## 5. Recommended Order of Execution

1. **Instrument** (§3): Add per-stage timing; run pipeline; identify which stage dominates.
2. **Quick wins:**
   - Set `quad_decimate=2.0` (and optionally make it configurable).
   - Set `nthreads=2` or `4`.
3. **Verify:** Re-run; confirm FPS improvement (e.g. 12 → 25+).
4. **If still low:**
   - Try GPU preprocess (§4.4).
   - Try lower resolution or downscale (§4.3).
5. **Long-term:** AprilTag CUDA (§4.7) for maximum FPS at full resolution.

---

## 6. Success Criteria

- **Short-term:** Pipeline FPS ≥ 25 (with `quad_decimate=2.0` and `nthreads` increase).
- **Medium-term:** Pipeline FPS ≥ 40 with GPU preprocess and/or lower resolution.
- **Long-term:** Pipeline FPS ≥ 50 (match camera) with AprilTag CUDA and full GPU pipeline.

---

## 7. Files to Modify (Reference)

| File | Purpose |
|------|---------|
| `backend/src/plana/adapters/apriltag_detector_adapter.py` | `quad_decimate`, `nthreads` |
| `backend/src/plana/domain/vision_pipeline.py` | Per-stage timing |
| `backend/src/plana/domain/camera_manager.py` | Optional: encode timing |
| `backend/src/plana/domain/camera_service.py` | Use `preprocess_gpu` for AprilTag; config injection |
| `backend/src/plana/adapters/web_server.py` | AprilTag settings API (`quad_decimate`, `nthreads`) |
| `frontend/.../AprilTagPage.tsx` | Settings UI for `quad_decimate`, `nthreads` |
| `config/cameras.json` | Optional: separate resolution for AprilTag |

---

*Plan created: 2025-02-09. Update as instrumentation results become available.*
