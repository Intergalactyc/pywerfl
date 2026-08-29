"""
Resolves the default pywerfl data workspace used by ingestion scripts loader when no explicit workspace path is given.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "PYWERFL_DATA_DIR"
DEFAULT = Path.home() / ".pywerfl"


def default_workspace() -> Path:
    return Path(os.environ.get(ENV_VAR, DEFAULT))
