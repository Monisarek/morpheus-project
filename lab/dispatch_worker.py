"""Fixed container entry point for the accepted, public Iris protocol."""

import json
from pathlib import Path
import signal

from lab import run_pilot


if __name__ == "__main__":
    signal.alarm(20)
    print(json.dumps(run_pilot(Path("/state/iris-sepal-v1")), allow_nan=False))
