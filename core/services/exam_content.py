"""Immutable question context for a sitting; catalog revisions cannot change its grade."""
from copy import copy
from types import SimpleNamespace

from core.services.mission_versioning import mission_snapshot


def exam_question_snapshot(mission):
    return {**mission_snapshot(mission),
            'learning_revision': mission.learning_revision,
            **{field: getattr(mission, field) for field in
               ('course', 'chapter_code', 'chapter_name', 'skill', 'level')}}


def frozen_exam_mission(item):
    snapshot = item.question_snapshot
    if not snapshot:
        return item.mission  # Completed legacy records have no reconstructible source.
    mission = copy(item.mission)
    mission._state = copy(item.mission._state)
    mission._state.fields_cache = dict(item.mission._state.fields_cache)
    for field in ('title', 'prompt', 'answer_schema', 'correct_answer', 'answer_key',
                  'explanation', 'choice_explanations', 'concept_summary', 'exam_tip',
                  'question_type', 'answer_input_type', 'content_version', 'content_fingerprint',
                  'grading_fingerprint', 'learning_revision', 'course', 'chapter_code',
                  'chapter_name', 'skill', 'level'):
        if field in snapshot:
            setattr(mission, field, snapshot[field])
    image = snapshot.get('image_path', '')
    mission._state.fields_cache['question_image'] = SimpleNamespace(static_path=image) if image else None
    return mission


def exam_item_is_current(item):
    snapshot = item.question_snapshot
    return not snapshot or (
        snapshot.get('learning_revision', 1) == item.mission.learning_revision
        and snapshot.get('grading_fingerprint') == item.mission.grading_fingerprint)


def current_content_exams(queryset):
    """Old invalid records must not poison a new sitting on the revised question."""
    from django.db.models import Exists, OuterRef, F, Q, IntegerField
    from django.db.models.functions import Cast
    from django.db.models.fields.json import KeyTextTransform
    from core.models import Attempt, ExamSessionMission
    items = ExamSessionMission.objects.filter(exam_session_id=OuterRef("pk"))
    invalid_attempt = Attempt.objects.filter(user_id=OuterRef("exam_session__user_id"),
        mission_id=OuterRef("mission_id"), grading_valid=False)
    legacy = items.filter(question_snapshot={}).annotate(invalid=Exists(invalid_attempt)).filter(invalid=True)
    stale = items.exclude(question_snapshot={}).annotate(
        frozen_revision=Cast(KeyTextTransform("learning_revision", "question_snapshot"), IntegerField()),
        frozen_grading=KeyTextTransform("grading_fingerprint", "question_snapshot"),
    ).filter(Q(frozen_revision__isnull=True) | ~Q(frozen_revision=F("mission__learning_revision")) |
             Q(frozen_grading__isnull=True) | ~Q(frozen_grading=F("mission__grading_fingerprint")))
    return queryset.annotate(_stale_content=Exists(stale), _stale_legacy=Exists(legacy)).filter(
        _stale_content=False, _stale_legacy=False)
