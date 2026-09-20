"""Read-only change detection for generated mission sources."""

from __future__ import annotations

import hashlib
from pathlib import Path


TRACKED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def tracked_generated_files(source_dir: Path, image_dir: Path) -> list[Path]:
    source_dir = Path(source_dir).resolve()
    image_dir = Path(image_dir).resolve()
    paths = []
    if source_dir.is_dir():
        paths.extend(path for path in source_dir.rglob("*.csv") if path.is_file())
    if image_dir.is_dir():
        paths.extend(
            path
            for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in TRACKED_IMAGE_SUFFIXES
        )
    return sorted(paths, key=lambda path: str(path).casefold())


def generated_sources_fingerprint(source_dir: Path, image_dir: Path) -> str:
    """Hash names and bytes so same-size edits and new images are detected."""
    roots = (Path(source_dir).resolve(), Path(image_dir).resolve())
    digest = hashlib.sha256()
    files = tracked_generated_files(*roots)
    for path in files:
        root_index = 0 if path.is_relative_to(roots[0]) else 1
        relative = path.relative_to(roots[root_index]).as_posix()
        digest.update(f"{root_index}:{relative}\0".encode("utf-8"))
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    digest.update(f"files:{len(files)}".encode("ascii"))
    return digest.hexdigest()
