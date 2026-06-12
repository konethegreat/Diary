"""Entry point.

    python run.py          # serve (logs to data/server.log when headless)
    python run.py --dev    # develop: auto-reload, logs to the console

The Windows scheduled task runs this with pythonw.exe (no console), so in
non-dev mode stdout/stderr are pointed at a log file before uvicorn starts.
"""
import os
import sys

import uvicorn

if __name__ == "__main__":
    dev = "--dev" in sys.argv
    if not dev:
        os.makedirs("data", exist_ok=True)
        log = open(os.path.join("data", "server.log"), "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=dev)
