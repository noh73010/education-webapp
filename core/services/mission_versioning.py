"""Mission content versioning and historical grading invalidation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from django.db import transaction
from django.utils import timezone


CHOICE_GRADING_TYPES = {"choice_one", "true_false", "error_detect"}


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def content_payload(mission) -> dict:
    """Return every learner-visible field whose change creates a new version."""
    return {
        "title": mission.title or "",
        "prompt": mission.prompt or "",
        "answer_schema": mission.answer_schema or "",
        "correct_answer": mission.correct_answer or "",
        "answer_key": mission.answer_key or "",
        "explanation": mission.explanation or "",
        "choice_explanations": mission.choice_explanations or {},
        "concept_summary": mission.concept_summary or "",
        "exam_tip": mission.exam_tip or "",
        "question_type": mission.question_type or "",
        "answer_input_type": mission.answer_input_type or "",
    }


def grading_payload(mission) -> dict:
    """Return only fields that determine whether a submission is correct."""
    payload = {
        "question_type": mission.question_type or "",
        "answer_input_type": mission.answer_input_type or "",
        "correct_answer": mission.correct_answer or "",
        "answer_key": mission.answer_key or "",
    }
    if mission.question_type not in CHOICE_GRADING_TYPES:
        payload["answer_schema"] = mission.answer_schema or ""
    return payload


def mission_content_fingerprint(mission) -> str:
    return _fingerprint(content_payload(mission))


def mission_grading_fingerprint(mission) -> str:
    return _fingerprint(grading_payload(mission))


def mission_snapshot(mission) -> dict:
    """Freeze the question and answer context that the learner actually saw."""
    return {
        "external_id": mission.external_id,
        "content_version": mission.content_version,
        "content_fingerprint": mission.content_fingerprint,
        "grading_fingerprint": mission.grading_fingerprint,
        **content_payload(mission),
    }


def attempt_snapshot_defaults(mission) -> dict:
    content_fingerprint = mission.content_fingerprint or mission_content_fingerprint(mission)
    grading_fingerprint = mission.grading_fingerprint or mission_grading_fingerprint(mission)
    snapshot = {
        "external_id": mission.external_id,
        "content_version": mission.content_version,
        "content_fingerprint": content_fingerprint,
        "grading_fingerprint": grading_fingerprint,
        **content_payload(mission),
    }
    return {
        "mission_content_version": mission.content_version,
        "mission_content_fingerprint": content_fingerprint,
        "mission_grading_fingerprint": grading_fingerprint,
        "mission_snapshot": snapshot,
    }


@dataclass(frozen=True)
class GradingInvalidationImpact:
    attempts: int = 0
    users: int = 0
    user_ids: tuple[int, ...] = ()


@transaction.atomic
def invalidate_attempts_for_grading_change(*, mission, previous_version: int):
    """Preserve historical attempts but remove them from current learning data."""
    from core.models import Attempt, ConfusionCard
    from core.services.weaknesses import rebuild_weaknesses_for_attempt_invalidation

    affected = Attempt.objects.filter(mission=mission, grading_valid=True)
    user_ids = list(affected.values_list("user_id", flat=True).distinct())
    reason = (
        f"문항 버전 {previous_version}→{mission.content_version}: "
        "채점 기준 fingerprint 변경"
    )
    attempt_count = affected.update(
        grading_valid=False,
        grading_invalidated_at=timezone.now(),
        grading_invalidation_reason=reason,
    )
    if not attempt_count:
        return GradingInvalidationImpact()

    ConfusionCard.objects.filter(mission=mission, user_id__in=user_ids).delete()
    rebuild_weaknesses_for_attempt_invalidation(mission=mission, user_ids=user_ids)
    return GradingInvalidationImpact(
        attempts=attempt_count,
        users=len(user_ids),
        user_ids=tuple(user_ids),
    )
