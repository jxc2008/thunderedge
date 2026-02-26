import shutil
import os

next_dir = '/vercel/share/v0-project/.next'
if os.path.exists(next_dir):
    shutil.rmtree(next_dir)
    print(f"[v0] Cleared {next_dir}")
else:
    print(f"[v0] {next_dir} does not exist, nothing to clear")
