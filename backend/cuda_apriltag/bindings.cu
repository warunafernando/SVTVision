#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

#include <memory>
#include <string>
#include <vector>
#include <chrono>

extern "C" {
  #include <apriltag/apriltag.h>
  #include <apriltag/tag36h11.h>
  #include <apriltag/tag25h9.h>
  #include <apriltag/common/g2d.h>
}

#include "apriltag_gpu.h"
#include <cuda_runtime.h>

namespace py = pybind11;

namespace {

apriltag_family_t *create_family(const std::string &family_name) {
  if (family_name == "tag36h11") return tag36h11_create();
  if (family_name == "tag25h9") return tag25h9_create();
  // Default/fallback
  return tag36h11_create();
}

void destroy_family(apriltag_family_t *fam, const std::string &family_name) {
  if (!fam) return;
  if (family_name == "tag36h11") { tag36h11_destroy(fam); return; }
  if (family_name == "tag25h9") { tag25h9_destroy(fam); return; }
  tag36h11_destroy(fam);
}

}  // namespace

class CudaAprilTagDetector {
public:
  CudaAprilTagDetector(int width,
                       int height,
                       std::string family,
                       float quad_decimate,
                       int nthreads)
      : width_(width),
        height_(height),
        family_(std::move(family)),
        quad_decimate_(quad_decimate),
        nthreads_(nthreads) {

    td_ = apriltag_detector_create();
    td_->nthreads = nthreads_;
    td_->quad_decimate = quad_decimate_;
    td_->refine_edges = true;

    fam_ = create_family(family_);
    apriltag_detector_add_family(td_, fam_);

    camera_matrix_.fx = 1.0;
    camera_matrix_.fy = 1.0;
    camera_matrix_.cx = 0.0;
    camera_matrix_.cy = 0.0;
    distortion_coefficients_.k1 = 0.0;
    distortion_coefficients_.k2 = 0.0;
    distortion_coefficients_.p1 = 0.0;
    distortion_coefficients_.p2 = 0.0;
    distortion_coefficients_.k3 = 0.0;

    gpu_detector_ = std::make_unique<frc971::apriltag::GpuDetector>(
        static_cast<size_t>(width_), static_cast<size_t>(height_), td_, camera_matrix_, distortion_coefficients_);
  }

  ~CudaAprilTagDetector() {
    gpu_detector_.reset();
    if (td_) {
      apriltag_detector_clear_families(td_);
      apriltag_detector_destroy(td_);
      td_ = nullptr;
    }
    destroy_family(fam_, family_);
    fam_ = nullptr;
  }

  void set_config(float quad_decimate, int nthreads) {
    quad_decimate_ = quad_decimate;
    nthreads_ = nthreads;
    if (td_) {
      td_->quad_decimate = quad_decimate_;
      td_->nthreads = nthreads_;
    }
  }

  py::dict get_config() const {
    py::dict d;
    d["quad_decimate"] = quad_decimate_;
    d["nthreads"] = nthreads_;
    d["family"] = family_;
    d["width"] = width_;
    d["height"] = height_;
    return d;
  }

  py::dict detect(py::array_t<uint8_t, py::array::c_style | py::array::forcecast> gray) {
    auto buf = gray.request();
    if (buf.ndim != 2) {
      throw std::runtime_error("Expected a 2D grayscale uint8 image");
    }
    const int h = static_cast<int>(buf.shape[0]);
    const int w = static_cast<int>(buf.shape[1]);
    if (w != width_ || h != height_) {
      throw std::runtime_error("Input image size does not match detector init (width/height)");
    }

    const uint8_t *image_ptr = static_cast<const uint8_t *>(buf.ptr);

    // Stable two-step pipeline:
    // 1) GPU stage only (quad extraction)
    // 2) CPU decode using helper DecodeTagsFromQuads() (no call to GpuDetector::Detect())
    auto t_gpu0 = std::chrono::steady_clock::now();
    gpu_detector_->DetectGpuOnly(image_ptr);
    // Ensure GPU work is completed for timing + subsequent host access.
    cudaDeviceSynchronize();
    auto t_gpu1 = std::chrono::steady_clock::now();
    const double gpu_stage_ms = std::chrono::duration<double, std::milli>(t_gpu1 - t_gpu0).count();

    // Prepare decode containers
    zarray_t *dets = zarray_create(sizeof(apriltag_detection_t *));
    zarray_t *poly0 = g2d_polygon_create_zeros(4);
    zarray_t *poly1 = g2d_polygon_create_zeros(4);

    const auto &quads = gpu_detector_->FitQuads();

    // CPU decode (single-thread) using libapriltag's quad_decode_index.
    // IMPORTANT: Decode against the ORIGINAL full-resolution grayscale image buffer.
    // CopyGrayHostTo() may return an internal/decimated buffer; using it here can produce garbage decodes.
    image_u8_t im_orig{
        .width = static_cast<int32_t>(width_),
        .height = static_cast<int32_t>(height_),
        .stride = static_cast<int32_t>(width_),
        .buf = const_cast<uint8_t *>(image_ptr),
    };

    // Decode timing (wall time around CPU decode loop)
    auto t_cpu0 = std::chrono::steady_clock::now();
    for (const auto &q : quads) {
      struct quad quad_original;
      std::memcpy(quad_original.p, q.corners, sizeof(q.corners));
      // Quads are produced on the decimated image grid; scale back to full-res pixel coordinates
      // before decoding against the original full-res image buffer.
      for (int i = 0; i < 4; ++i) {
        quad_original.p[i][0] *= quad_decimate_;
        quad_original.p[i][1] *= quad_decimate_;
      }
      quad_original.reversed_border = q.reversed_border;
      quad_original.H = nullptr;
      quad_original.Hinv = nullptr;
      quad_decode_index(td_, &quad_original, &im_orig, nullptr, dets);
    }
    reconcile_detections(dets, poly0, poly1);
    auto t_cpu1 = std::chrono::steady_clock::now();
    const double cpu_decode_ms = std::chrono::duration<double, std::milli>(t_cpu1 - t_cpu0).count();

    py::list detections;
    const int n = zarray_size(dets);
    for (int i = 0; i < n; ++i) {
      apriltag_detection_t *det = nullptr;
      zarray_get(dets, i, &det);
      if (!det) continue;

      py::dict d;
      d["id"] = det->id;
      d["decision_margin"] = det->decision_margin;
      d["center"] = py::make_tuple(det->c[0], det->c[1]);

      py::list corners;
      for (int k = 0; k < 4; ++k) {
        corners.append(py::make_tuple(det->p[k][0], det->p[k][1]));
      }
      d["corners"] = corners;
      detections.append(std::move(d));
    }

    py::dict timings_ms;
    timings_ms["gpu_stage_ms"] = gpu_stage_ms;
    timings_ms["cpu_decode_ms"] = cpu_decode_ms;
    timings_ms["detector_total_ms"] = gpu_stage_ms + cpu_decode_ms;
    timings_ms["num_quads"] = static_cast<int>(quads.size());

    // Clean up decode structures
    apriltag_detections_destroy(dets);
    zarray_destroy(poly0);
    zarray_destroy(poly1);

    py::dict out;
    out["detections"] = detections;
    out["timings_ms"] = timings_ms;
    return out;
  }

  py::dict detect_gpu_only(py::array_t<uint8_t, py::array::c_style | py::array::forcecast> gray) {
    auto buf = gray.request();
    if (buf.ndim != 2) {
      throw std::runtime_error("Expected a 2D grayscale uint8 image");
    }
    const int h = static_cast<int>(buf.shape[0]);
    const int w = static_cast<int>(buf.shape[1]);
    if (w != width_ || h != height_) {
      throw std::runtime_error("Input image size does not match detector init (width/height)");
    }
    const uint8_t *image_ptr = static_cast<const uint8_t *>(buf.ptr);

    auto t_gpu0 = std::chrono::steady_clock::now();
    gpu_detector_->DetectGpuOnly(image_ptr);
    cudaDeviceSynchronize();
    auto t_gpu1 = std::chrono::steady_clock::now();
    const double gpu_stage_ms = std::chrono::duration<double, std::milli>(t_gpu1 - t_gpu0).count();

    py::dict timings_ms;
    timings_ms["gpu_stage_ms"] = gpu_stage_ms;

    py::dict out;
    out["timings_ms"] = timings_ms;
    out["num_quads"] = gpu_detector_->NumQuads();
    return out;
  }

private:
  int width_;
  int height_;
  std::string family_;
  float quad_decimate_;
  int nthreads_;

  apriltag_detector_t *td_{nullptr};
  apriltag_family_t *fam_{nullptr};
  std::unique_ptr<frc971::apriltag::GpuDetector> gpu_detector_;
  frc971::apriltag::CameraMatrix camera_matrix_{};
  frc971::apriltag::DistCoeffs distortion_coefficients_{};
};

PYBIND11_MODULE(_cuda_apriltag, m) {
  m.doc() = "CUDA AprilTag detector bindings (hybrid GPU+CPU pipeline)";

  py::class_<CudaAprilTagDetector>(m, "CudaAprilTagDetector")
      .def(py::init<int, int, std::string, float, int>(),
           py::arg("width"),
           py::arg("height"),
           py::arg("family") = "tag36h11",
           py::arg("quad_decimate") = 2.0f,
           py::arg("nthreads") = 4)
      .def("set_config", &CudaAprilTagDetector::set_config,
           py::arg("quad_decimate"),
           py::arg("nthreads"))
      .def("get_config", &CudaAprilTagDetector::get_config)
      .def("detect", &CudaAprilTagDetector::detect,
           py::arg("gray_uint8"),
           "Detect AprilTags in a 2D uint8 grayscale image.")
      .def("detect_gpu_only", &CudaAprilTagDetector::detect_gpu_only,
           py::arg("gray_uint8"),
           "Run only the GPU stage (quad extraction) and return timings + quad count.");
}

