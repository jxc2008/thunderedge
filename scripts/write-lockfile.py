#!/usr/bin/env python3
import subprocess
import sys
import os
import shutil

project_root = "/vercel/share/v0-project"
lock_path = os.path.join(project_root, "package-lock.json")

print(f"[v0] Project root: {project_root}")
print(f"[v0] package.json exists: {os.path.exists(os.path.join(project_root, 'package.json'))}")
print(f"[v0] cwd before run: {os.getcwd()}")

# Remove stale lock file
if os.path.exists(lock_path):
    os.remove(lock_path)
    print("[v0] Removed old package-lock.json")

# Run npm install --package-lock-only with explicit cwd
result = subprocess.run(
    ["npm", "install", "--package-lock-only", "--legacy-peer-deps"],
    cwd=project_root,
    capture_output=True,
    text=True,
    env={**os.environ, "npm_config_prefix": project_root}
)

print(f"[v0] returncode: {result.returncode}")
print(f"[v0] stdout: {result.stdout[-2000:]}")
print(f"[v0] stderr: {result.stderr[-2000:]}")

# Check primary location
if os.path.exists(lock_path):
    print(f"[v0] SUCCESS: package-lock.json at {lock_path} ({os.path.getsize(lock_path)} bytes)")
    sys.exit(0)

# npm sometimes writes to cwd instead of the specified cwd — search common locations
print("[v0] Not found at project root, searching fallback locations...")
for candidate_dir in [os.getcwd(), "/home", "/home/vercel-sandbox", "/tmp"]:
    candidate = os.path.join(candidate_dir, "package-lock.json")
    if os.path.exists(candidate):
        shutil.copy(candidate, lock_path)
        print(f"[v0] Copied from {candidate} to {lock_path} ({os.path.getsize(lock_path)} bytes)")
        sys.exit(0)

print("[v0] ERROR: package-lock.json was not created anywhere")
sys.exit(1)
