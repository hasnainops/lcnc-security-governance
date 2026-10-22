"""Local discovery-cycle freshness check; no network calls or credentials."""

import math
import os
from pathlib import Path
import tempfile
import time

STATUS_PATH = Path("/tmp/lcnc-discovery-success")
MAX_AGE_SECONDS = 180


def clear_success(path=STATUS_PATH):
    Path(path).unlink(missing_ok=True)


def record_success(path=STATUS_PATH):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, prefix=".discovery-health-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(str(time.monotonic()))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def is_healthy(path=STATUS_PATH, now=None):
    try:
        with Path(path).open() as stream:
            value = stream.read(128)
        completed = float(value)
        current = time.monotonic() if now is None else now
        age = current - completed
        return math.isfinite(completed) and 0 <= age <= MAX_AGE_SECONDS
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    healthy = is_healthy()
    print("Discovery cycle recent" if healthy else
          "Discovery cycle missing, failed or stale")
    raise SystemExit(0 if healthy else 1)
