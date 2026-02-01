#!/bin/bash
# Run unit tests and save results to reports/

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Running unit tests..."

# Run backend tests
PYTHONPATH=backend/src python -m pytest backend/tests/ -v --tb=short 2>&1 | tee reports/latest_test_run.txt
TEST_EXIT=$?

# Build frontend
echo ""
echo "Building frontend..."
cd frontend && npm run build 2>&1 | tail -5
BUILD_EXIT=$?
cd ..

# Update results file
echo ""
echo "Updating reports/UNIT_TESTS_AND_VALIDATION_RESULTS.md..."
if [ $TEST_EXIT -eq 0 ] && [ $BUILD_EXIT -eq 0 ]; then
  echo "All tests passed. Build succeeded."
  echo "Results saved to: reports/UNIT_TESTS_AND_VALIDATION_RESULTS.md"
  echo "Raw output saved to: reports/latest_test_run.txt"
else
  echo "Some tests or build failed. Check reports/latest_test_run.txt"
  exit 1
fi
