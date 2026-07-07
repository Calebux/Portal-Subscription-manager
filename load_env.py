#!/usr/bin/env python3
"""
Minimal .env loader for the standalone Python scripts — mirrors load-env.js.
Reads .env from the script's own resolved directory, so it finds the right
file whether the script is invoked directly or through a ~/.hermes symlink
(Path.resolve() follows symlinks to the real file location).
"""

import os
from pathlib import Path


def load_hermes_env():
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value
