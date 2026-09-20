"""Presentation data for exam history without changing stored exam relationships."""

from core.services.exam_modes import mode_result
from core.services.exams import exact_exam_score


FINISHED_STATUSES = {"submitted", "expired"}


def _session_summary(exam):
    finished = exam.status in FINISHED_STATUSES
    return {
        "exam": exam,
        "status": exam.status,
        "status_label": exam.get_status_display(),
        "finished": finished,
        "score": exact_exam_score(exam) if finished else None,
        "correct_count": exam.correct_count,
        "total_questions": exam.total_questions,
    }


def _individual_card(exam):
    summary = _session_summary(exam)
    if exam.status == "in_progress":
        action = {"kind": "link", "label": "이어서 풀기", "exam_id": exam.pk}
    elif exam.status in FINISHED_STATUSES:
        action = {"kind": "link", "label": "결과 보기", "exam_id": exam.pk}
    else:
        action = None
    return {
        "key": f"exam-{exam.pk}",
        "is_full": False,
        "title": exam.title,
        "started_at": exam.started_at,
        "session": summary,
        "action": action,
    }


def _full_card(first, second):
    first_summary = _session_summary(first)
    second_summary = _session_summary(second) if second else None
    both_finished = bool(
        second
        and first.status in FINISHED_STATUSES
        and second.status in FINISHED_STATUSES
    )

    if first.status == "in_progress":
        action = {"kind": "link", "label": "이어서 풀기", "exam_id": first.pk}
    elif second and second.status == "waiting" and first.status in FINISHED_STATUSES:
        action = {"kind": "post", "label": "2교시 시작", "exam_id": second.pk}
    elif second and second.status == "in_progress":
        action = {"kind": "link", "label": "이어서 풀기", "exam_id": second.pk}
    elif both_finished:
        action = {"kind": "link", "label": "종합 결과 보기", "exam_id": second.pk}
    elif first.status in FINISHED_STATUSES:
        action = {"kind": "link", "label": "결과 보기", "exam_id": first.pk}
    else:
        action = None

    result = mode_result(second if both_finished else first)
    return {
        "key": f"full-{first.pk}",
        "is_full": True,
        "title": "실전 모의고사",
        "started_at": first.started_at,
        "first": first_summary,
        "second": second_summary,
        "course_rows": result["rows"] if both_finished else [],
        "average": result["average"] if both_finished else None,
        "verdict": result["label"] if both_finished else None,
        "action": action,
    }


def build_exam_history_cards(exams):
    """Group a full exam's two persisted sessions into one history card."""
    sessions = list(exams)
    by_id = {exam.pk: exam for exam in sessions}
    second_by_first = {
        exam.previous_sitting_id: exam
        for exam in sessions
        if exam.mode_config.get("mode") == "full" and exam.previous_sitting_id
    }
    cards = []
    for exam in sessions:
        mode = exam.mode_config.get("mode")
        if mode == "full" and exam.previous_sitting_id in by_id:
            continue
        if mode == "full" and not exam.previous_sitting_id:
            cards.append(_full_card(exam, second_by_first.get(exam.pk)))
        else:
            cards.append(_individual_card(exam))
    return sorted(cards, key=lambda card: card["started_at"], reverse=True)
