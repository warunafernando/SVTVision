#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

PYBIND11_CMAKE_DIR="$(python3 -m pybind11 --cmakedir)"

CCCL_DIR="${SCRIPT_DIR}/third_party/cccl"
if [ ! -d "${CCCL_DIR}/cub" ]; then
  echo "[cuda_apriltag] CCCL not found; cloning into ${CCCL_DIR}"
  mkdir -p "${SCRIPT_DIR}/third_party"
  rm -rf "${CCCL_DIR}"
  git clone --depth 1 --branch v2.3.2 https://github.com/NVIDIA/cccl.git "${CCCL_DIR}"
fi

BUILD_DIR="${SCRIPT_DIR}/build"
mkdir -p "${BUILD_DIR}"

CUDA_ARCH="${SVT_CUDA_ARCH:-86}"
BUILD_TYPE="${BUILD_TYPE:-Release}"

echo "[cuda_apriltag] Building with CUDA arch=${CUDA_ARCH} type=${BUILD_TYPE}"

cmake -S "${SCRIPT_DIR}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE="${BUILD_TYPE}" \
  -DCMAKE_PREFIX_PATH="${PYBIND11_CMAKE_DIR}" \
  -DCCCL_DIR="${CCCL_DIR}" \
  -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCH}"

cmake --build "${BUILD_DIR}" -j"$(nproc)"

# Copy built module into backend import path
OUT_SO="$(ls -1 "${BUILD_DIR}"/_cuda_apriltag*.so | head -n 1)"
DEST_DIR="${BACKEND_DIR}/src/plana/adapters"
mkdir -p "${DEST_DIR}"
cp -f "${OUT_SO}" "${DEST_DIR}/"

echo "[cuda_apriltag] Installed $(basename "${OUT_SO}") -> ${DEST_DIR}/"

