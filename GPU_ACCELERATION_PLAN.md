# GPU Acceleration Plan for RTX 3050 + CUDA

## Current Status

- ✅ **RTX 3050 Detected**: Compute Capability 8.6, CUDA Driver 590.48.01
- ❌ **OpenCV CUDA**: Not available (opencv-python-headless has no CUDA support)
- ❌ **Current Pipeline**: 100% CPU-based

## Overview

This plan outlines how to leverage the RTX 3050 GPU to accelerate the vision pipeline, focusing on preprocessing operations which are the current bottleneck.

## Phase 1: Setup & Infrastructure

### 1.1 Install OpenCV with CUDA Support

**Options:**
- **Option A**: Install `opencv-contrib-python` (may include CUDA modules)
- **Option B**: Build OpenCV from source with CUDA (complex, but full control)
- **Option C**: Use pre-built wheel with CUDA support (if available)

**Recommended**: Start with Option A, fallback to Option B if needed.

**Verification:**
```python
import cv2
print("CUDA devices:", cv2.cuda.getCudaEnabledDeviceCount())
print("CUDA available:", cv2.cuda.getCudaEnabledDeviceCount() > 0)
```

### 1.2 GPU Memory Manager

Create a GPU memory manager to:
- Reuse GpuMat buffers (avoid allocations)
- Manage CUDA streams for async operations
- Track GPU memory usage
- Handle memory cleanup

### 1.3 GPU Detection & Fallback

- Detect GPU availability at startup
- Log GPU status in debug tree
- Automatic fallback to CPU if GPU unavailable
- Configuration option to force CPU mode

## Phase 2: GPU-Accelerated Preprocessing

### 2.1 Create CudaPreprocessAdapter

**CPU → GPU Operation Mapping:**

| CPU Operation | GPU Equivalent | Speedup Expected |
|--------------|----------------|------------------|
| `cv2.cvtColor()` | `cv2.cuda.cvtColor()` | 3-5x |
| `cv2.GaussianBlur()` | `cv2.cuda.GaussianBlur()` | 4-6x |
| `cv2.adaptiveThreshold()` | `cv2.cuda.adaptiveThreshold()` | 2-4x |
| `cv2.morphologyEx()` | `cv2.cuda.morphologyEx()` | 5-8x |

**Implementation:**
- Create `CudaPreprocessAdapter` implementing `PreprocessPort`
- Use `cv2.cuda.GpuMat` for all operations
- Keep operations on GPU (minimize transfers)

### 2.2 Memory Transfer Optimization

**Strategy:**
1. Upload frame to GPU once: `gpu_frame = cv2.cuda.GpuMat(cpu_frame)`
2. All preprocessing on GPU: `gpu_blurred`, `gpu_thresholded`
3. Download only final result: `result = gpu_result.download()`

**Minimize Transfers:**
- Keep preprocessed frame on GPU if possible
- Only download when needed for CPU-based detection

### 2.3 Batch Processing

For multiple cameras:
- Process frames in parallel using CUDA streams
- Batch upload/download operations
- Overlap computation with memory transfers

## Phase 3: AprilTag Detection

### 3.1 Current Limitation

- `apriltag` library is CPU-only
- No direct GPU alternative available

### 3.2 Hybrid Approach

**Optimal Strategy:**
- **Preprocessing**: GPU (fast, parallel)
- **Detection**: CPU (apriltag library)
- **Transfer**: Download preprocessed frame only (minimal overhead)

**Performance:**
- Preprocessing on GPU: ~5-10ms (vs 20-30ms CPU)
- Transfer to CPU: ~1-2ms
- Detection on CPU: ~10-20ms
- **Total**: ~16-32ms (vs 30-50ms CPU-only)

### 3.3 Future Options

If detection becomes bottleneck:
- TensorRT-optimized detection model
- Custom CUDA kernel for tag detection
- OpenCV DNN with GPU backend

## Phase 4: Frame Encoding/Decoding

### 4.1 JPEG Encoding

- Current: CPU-based (`cv2.imencode()`)
- GPU option: NPP (NVIDIA Performance Primitives)
- **Decision**: Keep CPU encoding (fast enough, simpler)

### 4.2 Video Codec (Future)

- NVENC for H.264/H.265 encoding
- Useful for recording/streaming

## Phase 5: Performance Monitoring

### 5.1 GPU Metrics

Track:
- GPU utilization %
- GPU memory usage (allocated/free)
- Processing latency (GPU vs CPU)
- Throughput (frames/second)
- Memory transfer times

### 5.2 Debug Tree Integration

Add GPU status node:
```
Vision Pipeline
├── GPU Status (OK/WARN/ERROR)
│   ├── Device: RTX 3050
│   ├── Utilization: 45%
│   ├── Memory: 512MB / 8192MB
│   └── Preprocessing: GPU (3.2x faster)
├── Preprocess (GPU)
└── Tag Detection (CPU)
```

## Implementation Steps

### Step 1: Install OpenCV with CUDA
```bash
# Try opencv-contrib-python first
pip install opencv-contrib-python

# Or build from source (if needed)
# See: https://docs.opencv.org/master/d6/d15/tutorial_building_tegra_cuda.html
```

### Step 2: Create CudaPreprocessAdapter
- Implement `PreprocessPort` interface
- Use `cv2.cuda` operations
- Handle GPU memory management

### Step 3: Add GPU Detection
- Check CUDA availability at startup
- Select adapter (GPU or CPU) based on availability
- Log selection in debug tree

### Step 4: Update CameraService
- Use GPU adapter when available
- Fallback to CPU adapter
- Per-camera GPU/CPU selection

### Step 5: Add GPU Metrics
- Track GPU utilization
- Monitor memory usage
- Compare GPU vs CPU performance

### Step 6: Testing & Optimization
- Benchmark performance
- Optimize memory transfers
- Tune batch sizes

## Expected Performance Gains

### Preprocessing (1920x1200 @ 50fps)
- **CPU**: ~20-30ms per frame
- **GPU**: ~5-10ms per frame
- **Speedup**: 3-5x

### Overall Pipeline
- **Current**: ~30-50ms per frame (CPU preprocessing + detection)
- **With GPU**: ~16-32ms per frame (GPU preprocessing + CPU detection)
- **Speedup**: 2-3x

### Benefits
- Higher FPS at high resolutions
- Lower CPU usage (free for other tasks)
- Better scalability for multiple cameras
- More headroom for future features

## Risks & Mitigation

### Risk 1: OpenCV CUDA Build Complexity
**Mitigation**: Start with pre-built packages, document build process

### Risk 2: Memory Transfer Overhead
**Mitigation**: Minimize transfers, batch operations, use streams

### Risk 3: GPU Memory Limits
**Mitigation**: Monitor usage, implement memory pooling, limit concurrent operations

### Risk 4: Compatibility (No GPU)
**Mitigation**: Always maintain CPU fallback, test both paths

### Risk 5: AprilTag Still CPU-Bound
**Mitigation**: Acceptable - preprocessing is the bottleneck, detection is fast enough

## Configuration

Add to camera config:
```json
{
  "preprocessing": {
    "use_gpu": true,  // Auto-detect, can override
    "gpu_device_id": 0,
    "batch_size": 1
  }
}
```

## Testing Plan

1. **Unit Tests**: GPU adapter functionality
2. **Integration Tests**: Full pipeline with GPU
3. **Performance Tests**: Benchmark GPU vs CPU
4. **Stress Tests**: Multiple cameras, high FPS
5. **Fallback Tests**: GPU unavailable scenarios

## Success Criteria

- ✅ GPU preprocessing 2-3x faster than CPU
- ✅ Overall pipeline 1.5-2x faster
- ✅ Stable detection (no regressions)
- ✅ CPU fallback works correctly
- ✅ GPU metrics visible in debug tree
- ✅ No memory leaks

## Timeline

- **Phase 1** (Setup): 1-2 hours
- **Phase 2** (Implementation): 2-3 hours
- **Phase 3** (Testing): 1-2 hours
- **Total**: 4-7 hours

## Next Steps

1. Review and approve plan
2. Install OpenCV with CUDA support
3. Implement CudaPreprocessAdapter
4. Test and benchmark
5. Deploy and monitor
