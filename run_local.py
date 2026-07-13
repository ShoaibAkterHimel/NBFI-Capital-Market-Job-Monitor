from __future__ import annotations

import subprocess
import sys

commands = [
    [sys.executable, "src/bootstrap_companies.py"],
    [sys.executable, "src/discover_careers.py"],
    [sys.executable, "src/scan_jobs.py"],
    [sys.executable, "src/render_dashboard.py"],
]
for command in commands:
    print("+", " ".join(command))
    subprocess.run(command, check=True)
print("Done. Open docs/index.html in a browser.")
