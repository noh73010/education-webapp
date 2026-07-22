from django.db import transaction
from django.utils import timezone

from core.models import ProblemSet, ProblemSetSession, ProblemSetSessionItem

@transaction.atomic
def create_problem_set_session(*, user, problem_set: ProblemSet, subject=None) -> ProblemSetSession:
    item_qs = problem_set.items.select_related("mission").filter(
        mission__is_usable_for_set=True,
    )
    if subject is not None:
        item_qs = item_qs.filter(mission__subject=subject)

    items = list(item_qs.order_by("order_no"))

    session = ProblemSetSession.objects.create(
        user=user,
        problem_set=problem_set,
        status="in_progress",
        total_count=len(items),
    )

    ProblemSetSessionItem.objects.bulk_create([
        ProblemSetSessionItem(
            problem_set_session=session,
            mission=item.mission,
            order_no=item.order_no,
        )
        for item in items
    ])

    return session


@transaction.atomic
def submit_problem_set_item_answer(
    *, session: ProblemSetSession, mission_id: int, is_correct: bool,
    submitted_answer: str = "", attempt=None,
):
    session_item = (
        session.items
        .select_related("mission")
        .filter(mission_id=mission_id)
        .first()
    )

    if not session_item:
        return None

    session_item.is_correct = is_correct
    session_item.submitted_answer = submitted_answer or ""
    session_item.attempt = attempt
    session_item.submitted_at = timezone.now()
    session_item.save(update_fields=["is_correct", "submitted_answer", "attempt", "submitted_at"])

    return session_item


@transaction.atomic
def record_problem_set_item_review(*, session: ProblemSetSession, mission_id: int, is_correct: bool):
    session_item = session.items.select_for_update().filter(mission_id=mission_id).first()
    if not session_item:
        return None
    session_item.review_attempt_count += 1
    session_item.review_is_correct = is_correct
    session_item.reviewed_at = timezone.now()
    session_item.save(update_fields=["review_attempt_count", "review_is_correct", "reviewed_at"])
    return session_item


@transaction.atomic
def finish_problem_set_session(session: ProblemSetSession) -> ProblemSetSession:
    items = list(session.items.all())

    correct_count = sum(1 for item in items if item.is_correct is True)
    wrong_count = sum(1 for item in items if item.is_correct is False)

    unanswered_count = sum(1 for item in items if item.is_correct is None)
    wrong_count += unanswered_count

    total_count = len(items)
    score = round((correct_count / total_count) * 100) if total_count else 0

    session.status = "completed"
    session.completed_at = timezone.now()
    session.total_count = total_count
    session.correct_count = correct_count
    session.wrong_count = wrong_count
    session.score = score
    session.save(update_fields=[
        "status",
        "completed_at",
        "total_count",
        "correct_count",
        "wrong_count",
        "score",
    ])

    return session


@transaction.atomic
def create_problem_set_session_from_missions(*, user, problem_set: ProblemSet, missions) -> ProblemSetSession:
    missions = list(missions)
    session = ProblemSetSession.objects.create(
        user=user,
        problem_set=problem_set,
        status="in_progress",
        total_count=len(missions),
    )
    ProblemSetSessionItem.objects.bulk_create([
        ProblemSetSessionItem(
            problem_set_session=session,
            mission=mission,
            order_no=index,
        )
        for index, mission in enumerate(missions, start=1)
    ])
    return session
