"""Read unambiguous JSON and publish fresh files without replacing existing work."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def write_new(path, data):
    """Publish complete bytes to a new path, including when two writers race."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as directory:
        staged = Path(directory) / "output"
        staged.write_bytes(data)
        os.link(staged, path)
