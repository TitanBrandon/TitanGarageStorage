"""Fetch the pinned model with TLS verification and a fixed SHA-256 check."""

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from backend.model import MODEL_BYTES, MODEL_PATH, MODEL_SHA256, MODEL_URL


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main() -> None:
    if MODEL_PATH.is_file() and sha256(MODEL_PATH) == MODEL_SHA256:
        print("Depth model already present and checksum verified.")
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    pending: Path | None = None
    try:
        request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "TitanWalkthrough/0.1"})
        with urllib.request.urlopen(request, timeout=90) as response:
            with tempfile.NamedTemporaryFile(dir=MODEL_PATH.parent, suffix=".download", delete=False) as output:
                pending = Path(output.name)
                count = 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > MODEL_BYTES:
                        raise RuntimeError("Model download exceeded its expected size.")
                    output.write(chunk)
        if count != MODEL_BYTES or sha256(pending) != MODEL_SHA256:
            raise RuntimeError("Model checksum verification failed; the downloaded file will not be used.")
        os.replace(pending, MODEL_PATH)
        print("Depth model downloaded and SHA-256 verified.")
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
