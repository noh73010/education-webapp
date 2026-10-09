from datetime import timedelta
from django.db.models import OuterRef, Subquery, Q, Exists
from django.utils import timezone
from core.models import Attempt, Mission
from core.services.course_focus import learning_scope


def scoped_attempts(user, subject):
    scope, label = learning_scope(user, subject)
    qs = Attempt.objects.valid_for_learning().filter(user=user, mission__subject=subject)
    if scope:
        qs = qs.filter(**{"mission__" + key: value for key, value in scope.items()})
    return qs, label


def review_plan(user, subject, limit=5):
    qs, label = scoped_attempts(user, subject)
    latest = qs.filter(mission_id=OuterRef("mission_id")).order_by("-created_at", "-pk").values("pk")[:1]
    due = qs.filter(pk=Subquery(latest), mission__is_usable_for_set=True).exclude(
        mission__review_status=Mission.REVIEW_CONFIRMED_ERROR,
    ).exclude(mission__question_type="manual").filter(
        Q(is_correct=False) | (~Q(confidence_level=Attempt.CONFIDENCE_CERTAIN) & Q(created_at__date__lt=timezone.localdate()))
    ).select_related("mission").order_by("created_at", "pk")
    count = due.count()
    attempts = list(due[:limit])
    return {"label": label, "count": count, "attempts": attempts,
            "mission_ids": [row.mission_id for row in attempts], "minutes": len(attempts), "size": len(attempts)}


def weekly_changes(user, subject):
    qs, label = scoped_attempts(user, subject)
    today = timezone.localdate()
    start = today - timedelta(days=6)
    recent = qs.filter(created_at__date__gte=start, created_at__date__lte=today)
    previous = qs.filter(created_at__date__gte=start - timedelta(days=7), created_at__date__lt=start)
    def totals(rows):
        total = rows.count()
        correct = rows.filter(is_correct=True).count()
        return {"total": total, "correct": correct, "rate": round(correct * 100 / total, 1) if total else None,
                "days": rows.order_by().values("created_at__date").distinct().count()}
    latest = recent.filter(mission_id=OuterRef("mission_id")).order_by("-created_at", "-pk").values("pk")[:1]
    certain = recent.filter(pk=Subquery(latest), is_correct=True, confidence_level=Attempt.CONFIDENCE_CERTAIN)
    prior_wrong = qs.filter(mission_id=OuterRef("mission_id"), is_correct=False,
                            created_at__lte=OuterRef("created_at") - timedelta(days=3))
    delayed = certain.annotate(had_delayed_wrong=Exists(prior_wrong)).filter(had_delayed_wrong=True)
    return {"label": label, "start": start, "end": today, "recent": totals(recent), "previous": totals(previous),
            "delayed_count": delayed.count(), "delayed": list(delayed.select_related("mission").order_by("-created_at", "-pk")[:3]), "remaining": review_plan(user, subject)["count"]}
