#!/usr/bin/env bash
# Validation gate for frontend changes.
# Agents MUST run this and pass before reporting a task done.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Frontend Validation ==="

echo "[1/2] TypeScript typecheck..."
npx tsc --noEmit
echo "  PASS"

echo "[2/2] Next.js build..."
npm run build
echo "  PASS"

echo "=== All frontend checks passed ==="
