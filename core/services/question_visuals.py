"""Readable representations of exact, versioned exam figures.

Text is equivalent to the inspected image, never an explanation or answer key.
Unknown or replaced assets retain the ordinary image renderer.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings


@lru_cache(maxsize=1)
def _catalog():
    path = Path(__file__).resolve().parents[1] / "data" / "question_visuals.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def _asset_matches(filename, expected_digest, mtime_ns, size):
    return hashlib.sha256(Path(filename).read_bytes()).hexdigest() == expected_digest


def question_visual(static_path):
    entry = _catalog().get(str(static_path))
    if not entry:
        return None
    root = Path(settings.BASE_DIR) / "core" / "static"
    filename = (root / static_path).resolve()
    if not filename.is_relative_to(root.resolve()):
        return None
    try:
        stat = filename.stat()
        if not _asset_matches(str(filename), entry["sha256"], stat.st_mtime_ns, stat.st_size):
            return None
    except OSError:
        return None
    return entry
