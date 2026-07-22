import re
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.staticfiles import finders


QUESTION_IMAGE_PREFIX = "images/questions/"
ALLOWED_IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


def normalize_question_image_path(raw_path):
    value = (raw_path or "").strip().replace("\\", "/").lstrip("/")
    for prefix in ("core/static/", "static/"):
        if value.startswith(prefix):
            value = value[len(prefix):]

    path = PurePosixPath(value)
    if not value or ".." in path.parts:
        return ""
    if not value.startswith(QUESTION_IMAGE_PREFIX):
        return ""
    if path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        return ""
    return str(path)


def static_question_image_exists(static_path):
    return bool(static_path and finders.find(static_path))


def _number_signature(value):
    return tuple(int(item) for item in re.findall(r"\d+", value or ""))


def infer_question_image_path(*, subject_code, csv_path, question_number):
    if not subject_code or not question_number:
        return ""

    question_root = (
        Path(settings.BASE_DIR)
        / "core"
        / "static"
        / "images"
        / "questions"
        / subject_code
    )
    if not question_root.exists():
        return ""

    expected_stem = f"q{int(question_number):03d}"
    candidates = [
        path
        for path in question_root.rglob("*")
        if path.is_file()
        and path.stem.lower() == expected_stem
        and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
    ]
    source_numbers = _number_signature(Path(csv_path).stem)
    batch_candidates = []
    for path in candidates:
        parent_numbers = _number_signature(path.parent.name)
        if not source_numbers or not parent_numbers:
            continue
        if len(source_numbers) >= len(parent_numbers) and source_numbers[-len(parent_numbers):] == parent_numbers:
            batch_candidates.append(path)

    if len(batch_candidates) == 1:
        selected = batch_candidates[0]
    elif not source_numbers and len(candidates) == 1:
        selected = candidates[0]
    else:
        selected = None

    if selected is None:
        return ""

    static_root = Path(settings.BASE_DIR) / "core" / "static"
    return selected.relative_to(static_root).as_posix()


def resolve_question_image(*, raw_path, subject_code, csv_path, question_number):
    explicit_path = normalize_question_image_path(raw_path)
    if explicit_path:
        if static_question_image_exists(explicit_path):
            return explicit_path, "csv", False
        return "", "csv", True

    inferred_path = infer_question_image_path(
        subject_code=subject_code,
        csv_path=csv_path,
        question_number=question_number,
    )
    if inferred_path and static_question_image_exists(inferred_path):
        return inferred_path, "filename", False
    return "", "", False
