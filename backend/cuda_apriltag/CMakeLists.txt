cmake_minimum_required(VERSION 3.20)

project(cuda_apriltag_detector LANGUAGES CXX CUDA)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

# CUDA arch: allow override via env SVT_CUDA_ARCH, else default 86 (RTX 3050 etc)
if(DEFINED ENV{SVT_CUDA_ARCH})
  set(CMAKE_CUDA_ARCHITECTURES $ENV{SVT_CUDA_ARCH})
else()
  set(CMAKE_CUDA_ARCHITECTURES 86)
endif()

find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(CUDAToolkit REQUIRED)
find_package(PkgConfig REQUIRED)

# pybind11 (from pip) - caller should set CMAKE_PREFIX_PATH to `python3 -m pybind11 --cmakedir`
find_package(pybind11 CONFIG REQUIRED)

pkg_check_modules(APRILTAG REQUIRED apriltag)
pkg_check_modules(GLOG REQUIRED libglog)

find_package(Threads REQUIRED)

set(APRILTAG_CUDA_SRC_DIR "${CMAKE_SOURCE_DIR}/../../AprilTag_CUDA_X86/src/apriltags_cuda/src")
if(NOT DEFINED CCCL_DIR)
  set(CCCL_DIR "${CMAKE_SOURCE_DIR}/third_party/cccl")
endif()

pybind11_add_module(_cuda_apriltag
  bindings.cu
  ${APRILTAG_CUDA_SRC_DIR}/apriltag_gpu.cu
  ${APRILTAG_CUDA_SRC_DIR}/apriltag_detect.cu
  ${APRILTAG_CUDA_SRC_DIR}/cuda_frc971.cu
  ${APRILTAG_CUDA_SRC_DIR}/labeling_allegretti_2019_BKE.cu
  ${APRILTAG_CUDA_SRC_DIR}/line_fit_filter.cu
  ${APRILTAG_CUDA_SRC_DIR}/points.cu
  ${APRILTAG_CUDA_SRC_DIR}/threshold.cu
)

target_include_directories(_cuda_apriltag PRIVATE
  ${APRILTAG_CUDA_SRC_DIR}
  ${APRILTAG_INCLUDE_DIRS}
  ${GLOG_INCLUDE_DIRS}
  ${CUDAToolkit_INCLUDE_DIRS}
  ${CCCL_DIR}/cub
  ${CCCL_DIR}/thrust
  ${CCCL_DIR}/libcudacxx/include
  /usr/local/include
  /usr/local/include/apriltag
  /usr/local/include/apriltag/common
)

target_link_directories(_cuda_apriltag PRIVATE
  ${APRILTAG_LIBRARY_DIRS}
)

target_link_libraries(_cuda_apriltag PRIVATE
  ${APRILTAG_LIBRARIES}
  ${GLOG_LIBRARIES}
  CUDA::cudart
  Threads::Threads
)

target_compile_options(_cuda_apriltag PRIVATE
  $<$<COMPILE_LANGUAGE:CUDA>:--expt-relaxed-constexpr>
)

target_compile_definitions(_cuda_apriltag PRIVATE
  # Reduce verbose logging by default (glog)
  GOOGLE_STRIP_LOG=1
)

set_target_properties(_cuda_apriltag PROPERTIES
  CUDA_SEPARABLE_COMPILATION ON
  POSITION_INDEPENDENT_CODE ON
)

