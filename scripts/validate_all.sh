#!/usr/bin/env bash
# Run all validation gates. Use before merging any branch.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "  ThunderEdge Full Validation Suite"
echo "========================================"

bash "$ROOT/scripts/validate_backend.sh"
echo ""
bash "$ROOT/scripts/validate_frontend.sh"

echo ""
echo "========================================"
echo "  ALL CHECKS PASSED — safe to merge"
echo "========================================"
