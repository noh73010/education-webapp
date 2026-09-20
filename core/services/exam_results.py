"""Read-only helpers for presenting one exam attempt without changing its data."""

from core.models import ExamSession


FINAL_EXAM_STATUSES = ("submitted", "expired")


def result_sessions(exam):
    """Return the completed sittings that belong on the same result screen.

    A full mock exam is created as a linked pair.  The waiting/in-progress second
    sitting is intentionally omitted so it is never counted as unanswered before
    the learner has completed it.
    """
    if (exam.mode_config or {}).get("mode") != "full":
        return [exam]

    first = exam.previous_sitting if exam.previous_sitting_id else exam
    sessions = [first]
    second = ExamSession.objects.filter(previous_sitting=first).first()
    if second and second.user_id == first.user_id and second.status in FINAL_EXAM_STATUSES:
        sessions.append(second)
    return sessions


def representative_wrong_items(wrong_items, weak_skills, limit=5):
    """Pick a small, stable sample while representing the weakest skills first."""
    selected = []
    selected_ids = set()
    for weak in weak_skills:
        match = next(
            (
                item
                for item in wrong_items
                if item.pk not in selected_ids and item.mission.skill == weak["skill"]
            ),
            None,
        )
        if match:
            selected.append(match)
            selected_ids.add(match.pk)
        if len(selected) == limit:
            return selected

    for item in wrong_items:
        if item.pk not in selected_ids:
            selected.append(item)
            selected_ids.add(item.pk)
        if len(selected) == limit:
            break
    return selected
