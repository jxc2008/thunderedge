#!/usr/bin/env bash
# Validation gate for data/database changes. Alias for validate_backend.sh.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/validate_backend.sh"
