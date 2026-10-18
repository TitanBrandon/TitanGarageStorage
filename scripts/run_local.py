"""Run the built, authenticated website against a separately configured worker."""

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    os.chdir(ROOT)
    if not (ROOT / "dist/index.html").is_file():
        raise SystemExit("Build the website first: npm ci, then npm run build. See README.md for worker setup.")
    if len(os.environ.get("SITE_PASSWORD", "")) < 16:
        raise SystemExit("Set SITE_PASSWORD to a private password of at least 16 characters, then restart. Sign in as titan. See README.md.")
    if not os.environ.get("WORKER_URL") or not os.environ.get("WORKER_TOKEN"):
        print("Reconstruction worker is not configured. The website will show setup instructions; it cannot create models yet.", flush=True)
    if not args.serve:
        if sys.version_info[:2] != (3, 12):
            raise SystemExit("This launcher uses Python 3.12. The normal website does not require a local Python installation.")
        env_dir = ROOT / ".venv"
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(env_dir)], check=True)
        print("Preparing the lightweight website dependencies. Blender runs on the configured worker.", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", "backend/requirements-hosted.txt"], check=True)
        command = [str(python), str(Path(__file__).resolve()), "--serve", "--port", str(args.port)]
        if args.no_browser:
            command.append("--no-browser")
        raise SystemExit(subprocess.call(command))

    sys.path.insert(0, str(ROOT))
    import uvicorn
    from backend.hosted import app

    def open_when_ready():
        for _ in range(120):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/healthz", timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(f"http://127.0.0.1:{args.port}")
                        return
            except OSError:
                pass
            time.sleep(0.25)
        print("The website did not become ready. Check the startup messages in this window.", flush=True)

    if not args.no_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    print("Space Studio is starting on loopback. Sign in as titan with SITE_PASSWORD. Press Ctrl+C to stop the website.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, KeyboardInterrupt) as error:
        raise SystemExit(getattr(error, "returncode", 0))
