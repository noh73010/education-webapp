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
    from core.services.review_schedule import get_mission_review_states
    from core.services.efficient_learning import suppressed_ids
    candidates = list(qs.filter(pk=Subquery(latest), mission__is_usable_for_set=True).exclude(
        mission__review_status=Mission.REVIEW_CONFIRMED_ERROR,
    ).exclude(mission__question_type="manual").select_related("mission").order_by("created_at", "pk"))
    states = get_mission_review_states(user, [a.mission_id for a in candidates])
    excluded = suppressed_ids(user)
    due = [a for a in candidates if states.get(a.mission_id, {}).get('is_due') and a.mission_id not in excluded]
    due.sort(key=lambda a:(states[a.mission_id].get('priority',2), states[a.mission_id]['due_date'], a.pk))
    count = len(due)
    attempts = due[:limit]
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
    certain = recent.filter(pk=Subquery(latest), is_correct=True).filter(
        Q(confidence_level=Attempt.CONFIDENCE_CERTAIN) | Q(confidence_level="", learning_evidence=True))
    prior_wrong = qs.filter(mission_id=OuterRef("mission_id"), is_correct=False,
                            created_at__lte=OuterRef("created_at") - timedelta(days=3))
    delayed = certain.annotate(had_delayed_wrong=Exists(prior_wrong)).filter(had_delayed_wrong=True)
    return {"label": label, "start": start, "end": today, "recent": totals(recent), "previous": totals(previous),
            "delayed_count": delayed.count(), "delayed": list(delayed.select_related("mission").order_by("-created_at", "-pk")[:3]), "remaining": review_plan(user, subject)["count"]}


def start_study_queue(request, subject, missions, *, label, mode='', limit=5):
    ids = list(dict.fromkeys(m.pk for m in missions))[:limit]
    for key in list(request.session.keys()):
        if key.startswith(('problem_set_', 'pattern_training_', 'learning_type_training_', 'review_')):
            request.session.pop(key, None)
    request.session.pop('explanation_next', None)
    request.session['review_mission_ids'] = ids
    request.session['review_current_index'] = 0
    request.session['daily_review_state'] = {'subject_id':subject.pk,'label':label,
        'mission_ids':ids,'attempt_ids':[],'viewed_ids':[],'study_mode':mode}


def advance_study_queue(request, subject, mission, attempt=None):
    from django.urls import reverse
    ids = request.session.get('review_mission_ids', [])
    if mission.pk not in ids:
        return None
    index = ids.index(mission.pk)
    if request.session.get('review_current_index', index) != index:
        return None
    state = request.session.get('daily_review_state', {})
    is_daily = state.get('subject_id') == subject.pk and state.get('mission_ids') == ids
    if is_daily:
        key, value = ('attempt_ids', attempt.pk) if attempt else ('viewed_ids', mission.pk)
        state[key] = list(dict.fromkeys(state.get(key, []) + [value]))
        request.session['daily_review_state'] = state
    allowed = set(Mission.objects.filter(pk__in=ids[index+1:],subject=subject,is_usable_for_set=True).exclude(
        review_status=Mission.REVIEW_CONFIRMED_ERROR).values_list('pk',flat=True))
    next_index = index+1
    while next_index < len(ids) and ids[next_index] not in allowed:
        next_index += 1
    if next_index < len(ids):
        request.session['review_current_index'] = next_index
        return reverse('mission_detail',args=[ids[next_index]])
    exam_id=request.session.get('review_return_exam_id')
    for key in ('review_mission_ids','review_current_index','review_return_exam_id'):
        request.session.pop(key,None)
    if is_daily:
        return reverse('daily_review_result')
    return reverse('exam_result',args=[exam_id]) if exam_id else reverse('mission_list')
