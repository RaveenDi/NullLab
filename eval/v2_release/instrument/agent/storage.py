"""Atomic JSON checkpoints with a bounded retry for transient Windows sharing locks."""

import json
import os
from pathlib import Path
import time
import uuid


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
        for attempt in range(7):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # A concurrent local reader or sync scanner may briefly deny
                # replacement. Never truncate the last complete checkpoint.
                if attempt == 6:
                    raise
                time.sleep(0.01 * 2 ** attempt)
    finally:
        temporary.unlink(missing_ok=True)
