"""Learner-controlled exposure and scoped study queues; views never count as answers."""
from datetime import timedelta
from collections import defaultdict
from django.utils import timezone
from django.db.models import Q
from core.models import Attempt, Mission, LearningExposure
from core.services.review_schedule import get_mission_review_states


def suppressed_ids(user):
    states = get_mission_review_states(user, Attempt.objects.valid_for_learning().filter(user=user).values_list('mission_id', flat=True).distinct())
    ids = {pk for pk, state in states.items() if state['status'] == 'mastered' and not state['is_due']}
    ids.update(LearningExposure.objects.filter(Q(known_until__gt=timezone.now()) | Q(viewed_at__gt=timezone.now()-timedelta(days=1)), user=user).values_list('mission_id', flat=True))
    return ids


def scoped_missions(subject):
    return Mission.objects.filter(subject=subject, is_usable_for_set=True).exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR)


def alternatives(user, mission, limit=3):
    qs = scoped_missions(mission.subject).exclude(pk=mission.pk)
    # Only explicit concept links qualify; sharing a chapter is insufficient.
    if mission.concept_unit_id and mission.concept_unit.reviewed_on and mission.concept_unit.reviewed_on <= timezone.localdate() and mission.concept_unit.subject_id == mission.subject_id:
        qs = qs.filter(concept_unit_id=mission.concept_unit_id)
    else:
        return []
    return list(qs.exclude(pk__in=LearningExposure.objects.filter(user=user).values("mission_id")).exclude(pk__in=Attempt.objects.valid_for_learning().filter(user=user).values('mission_id')).exclude(pk__in=suppressed_ids(user)).order_by('pk')[:limit])


def chapter_rows(user, subject):
    missions = list(scoped_missions(subject).only('pk', 'course', 'chapter_code', 'chapter_name'))
    states = get_mission_review_states(user, [m.pk for m in missions])
    exposures = set(LearningExposure.objects.filter(user=user, mission__subject=subject).values_list('mission_id', flat=True))
    rows = {}
    for m in missions:
        key = (m.course, m.chapter_code)
        row = rows.setdefault(key, dict(course=m.course, code=m.chapter_code, name=m.chapter_name or m.course or '미분류', new=0, review=0, confirm=0, mastered=0, viewed=0))
        status = states.get(m.pk, {}).get('status', 'new')
        bucket = {'wrong':'review', 'uncertain':'review', 'mastered':'mastered', 'confirm':'confirm'}.get(status, 'new')
        row[bucket] += int(not (bucket == 'new' and m.pk in exposures))
        row['viewed'] += int(m.pk in exposures)
    return sorted(rows.values(), key=lambda r:(r['course'],r['code']))
