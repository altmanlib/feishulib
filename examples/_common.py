"""Local helpers shared by runnable examples."""

import os
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE pairs without evaluating shell expressions."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
