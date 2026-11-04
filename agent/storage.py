"""Atomic JSON checkpoints with a bounded retry for transient Windows sharing locks."""

import json
import os
from pathlib import Path
import time
import uuid


def publish_directory(source, destination):
    """Publish a new case without replacing an existing revision.

    Windows scanners can briefly lock a completely written staging directory.
    Retry only access/sharing failures; never merge or overwrite a destination.
    """
    source, destination = Path(source), Path(destination)
    delays = (0.01, 0.02, 0.04, 0.08, 0.16)
    for attempt in range(len(delays) + 1):
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"A case already exists at {destination}")
        try:
            source.rename(destination)
            return
        except OSError as exc:
            transient = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33}
            if not transient or attempt == len(delays):
                raise
            time.sleep(delays[attempt])


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
