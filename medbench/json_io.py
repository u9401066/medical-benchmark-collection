"""Read unambiguous JSON and publish fresh files without replacing existing work."""

import os
from uuid import uuid4


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
    # A private temporary directory can propagate an owner-only Windows ACL to the final hard link.
    staged = path.parent / (".medbench-" + uuid4().hex + ".tmp")
    stream = staged.open("xb")
    try:
        with stream:
            stream.write(data)
        os.link(staged, path)
    finally:
        staged.unlink(missing_ok=True)
