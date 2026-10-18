"""Run the packaged app with Python only; Node is unnecessary for the built download."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    os.chdir(ROOT)
    if not (ROOT / "dist/index.html").is_file():
        raise SystemExit("The built app is missing. Use the complete download, or run npm ci and npm run build.")
    if not args.serve:
        if sys.version_info[:2] != (3, 12):
            raise SystemExit("Please install Python 3.12 from python.org, then run this launcher again.")
        env_dir = ROOT / ".venv"
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(env_dir)], check=True)
        print("Preparing Space Studio. The first start downloads dependencies and a 99 MB AI model.", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", "backend/requirements.txt"], check=True)
        subprocess.run([str(python), "-m", "backend.download_model"], check=True)
        command = [str(python), str(Path(__file__).resolve()), "--serve", "--port", str(args.port)]
        if args.no_browser:
            command.append("--no-browser")
        raise SystemExit(subprocess.call(command))

    # Make the existing backend importable when this file is run as a script.
    sys.path.insert(0, str(ROOT))
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from backend.app import app

    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="studio")

    def open_when_ready():
        import json
        for _ in range(120):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/api/health", timeout=1) as response:
                    health = json.load(response)
                if health.get("ready"):
                    webbrowser.open(f"http://127.0.0.1:{args.port}")
                    return
                if health.get("error"):
                    print(f"The app could not start photo processing: {health['error']}", flush=True)
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.25)
        print("The app has not become ready. Check the messages in this window for the startup error.", flush=True)

    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    print("Space Studio is starting. Keep this window open; press Ctrl+C to stop.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, KeyboardInterrupt) as error:
        raise SystemExit(getattr(error, "returncode", 0))
