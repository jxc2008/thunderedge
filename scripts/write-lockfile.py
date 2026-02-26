#!/usr/bin/env python3
"""
Writes a package-lock.json for the project by running `npm install --package-lock-only`
from the correct working directory using subprocess with an explicit cwd.
"""
import subprocess
import sys
import os

project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
project_root = os.path.realpath(project_root)

print(f"[v0] Project root: {project_root}")
print("[v0] Running npm install --package-lock-only ...")

result = subprocess.run(
    ["npm", "install", "--package-lock-only", "--legacy-peer-deps"],
    cwd=project_root,
    capture_output=True,
    text=True
)

print("STDOUT:", result.stdout[-3000:] if result.stdout else "(none)")
print("STDERR:", result.stderr[-3000:] if result.stderr else "(none)")

if result.returncode != 0:
    print(f"[v0] FAILED with return code {result.returncode}")
    sys.exit(1)

lock_path = os.path.join(project_root, "package-lock.json")
if os.path.exists(lock_path):
    size = os.path.getsize(lock_path)
    print(f"[v0] package-lock.json written successfully ({size} bytes)")
else:
    print("[v0] ERROR: package-lock.json was not created")
    sys.exit(1)
