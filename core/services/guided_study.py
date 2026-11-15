"""Bounded, explainable plans; counts describe study evidence, never pass odds."""
from collections import Counter, defaultdict, deque
import heapq
from datetime import timedelta
from django.utils import timezone
from django.db.models import Exists, OuterRef
from core.models import Attempt, Mission, StudyProfile, SubjectStudyPlan, LearningExposure
from core.services.course_focus import learning_scope
from core.services.review_schedule import get_mission_review_states
from core.services.exam_dates import goal_for
from core.services.learning_experience import reviewed_concept, progress_evidence


def build_guided_plan(user, subject, *, today=None):
    today = today or timezone.localdate()
    settings = SubjectStudyPlan.objects.filter(user=user, subject=subject).first()
    profile = StudyProfile.objects.filter(user=user).first()
    minutes = settings.daily_minutes if settings else (profile.daily_minutes if profile else 10)
    limit = {5:3, 10:5, 20:10}.get(minutes, 5)
    scope, label = learning_scope(user, subject)
    if settings and settings.all_courses:
        scope, label = {}, subject.name + ' 전체 과목'
    bank = list(Mission.objects.filter(subject=subject, is_usable_for_set=True, source_enabled=True,
        **scope).exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR).exclude(question_type='manual')
        .select_related('concept_unit', 'subject').order_by('pk'))
    ids = [m.pk for m in bank]
    states = get_mission_review_states(user, ids, today=today)
    attempts = Attempt.objects.valid_for_learning().filter(user=user, mission_id__in=ids)
    done = set(attempts.filter(created_at__date=today).values_list('mission_id', flat=True))
    viewed = set(LearningExposure.objects.filter(user=user, mission_id__in=ids).values_list('mission_id',flat=True))
    held = set(LearningExposure.objects.filter(user=user, mission_id__in=ids,
        known_until__gt=timezone.now()).values_list('mission_id',flat=True))
    # Reading an answer today must not masquerade as a new-question assessment.
    recent_views = set(LearningExposure.objects.filter(user=user, mission_id__in=ids,
        viewed_at__gte=timezone.now()-timedelta(days=1)).values_list('mission_id',flat=True))
    available = [m for m in bank if m.pk not in done | held | recent_views]
    due = sorted([m for m in available if states.get(m.pk,{}).get('is_due')],
        key=lambda m:(states[m.pk].get('priority',2),states[m.pk]['due_date'],m.pk))
    new = [m for m in available if m.pk not in states and m.pk not in viewed]
    chapter_usage = Counter((m.course,m.chapter_code) for m in bank if m.pk in states)
    # Round-robin across less-practised chapters, rather than filling one chapter first.
    chapters = defaultdict(deque)
    for m in new:
        chapters[(m.course, m.chapter_code)].append(m)
    heap = [(chapter_usage[key], key) for key in chapters]
    heapq.heapify(heap)
    balanced = []
    while heap:
        usage, key = heapq.heappop(heap)
        balanced.append(chapters[key].popleft())
        if chapters[key]:
            heapq.heappush(heap, (usage + 1, key))
    goal = goal_for(user,subject)
    days = (goal.target_date-today).days if goal else None
    review_slots = max(1, round(limit * (.8 if days is not None and 0 <= days <= 7 else .5)))
    chosen = due[:review_slots]
    remaining = limit-len(chosen)
    chosen += balanced[:remaining]
    chosen += due[review_slots:review_slots+limit-len(chosen)]
    failed_units = {a.mission.concept_unit_id for a in attempts.filter(
        is_correct=False, created_at__date__lte=today-timedelta(days=3),
        mission__concept_unit__isnull=False).select_related('mission__concept_unit', 'mission__subject')
        if reviewed_concept(a.mission)}
    # A first encounter in a reviewed group is a targeted application check.
    for m in chosen:
        state = states.get(m.pk,{})
        if state.get('is_due'):
            reason = {'wrong':'전에 틀린 내용', 'uncertain':'확신 없이 맞힌 내용', 'mastered':'시간이 지난 내용'}.get(state['status'],'맞힌 내용')
            m.plan_reason = reason+'을 다시 확인해요.'
        elif m.pk in viewed:
            m.plan_reason = '해설을 읽은 내용을 직접 풀어 확인해요.'
        else:
            m.plan_reason = '아직 풀지 않은 문제로 이 단원을 확인해요.'
    # Replace at most one new slot; never add work beyond the chosen workload.
    target = next((m for m in balanced if m.concept_unit_id in failed_units and reviewed_concept(m)),None)
    if target:
        if target not in chosen:
            pos = next((i for i in range(len(chosen)-1,-1,-1) if chosen[i].pk not in states),None)
            if pos is not None: chosen[pos]=target
        if target in chosen: target.plan_reason='전에 틀린 개념을 처음 푸는 다른 문제로 확인해요.'
    changed_ids = set(Attempt.objects.filter(user=user,mission_id__in=ids,grading_valid=False)
        .values_list('mission_id',flat=True)) - set(states)
    changed = [m for m in available if m.pk in changed_ids]
    if changed:
        m=changed[0];m.plan_reason='내용이 수정되어 현재 문제로 다시 확인해요.'
        if m not in chosen:
            if len(chosen)<limit:chosen.append(m)
            else:chosen[-1]=m
    # Previously read material may fill empty slots, but not today and not held.
    for m in available:
        if len(chosen)>=limit:break
        if m.pk not in states and m not in chosen:
            m.plan_reason='해설을 읽은 내용을 직접 풀어 확인해요.';chosen.append(m)
    stable = sum(s['status']=='mastered' and not s['is_due'] for s in states.values())
    previous_same = attempts.filter(mission_id=OuterRef('mission_id'),
        created_at__lte=OuterRef('created_at')-timedelta(days=3))
    recent = list(attempts.filter(created_at__date__gte=today-timedelta(days=6))
        .annotate(has_delayed_same=Exists(previous_same))
        .select_related('mission__concept_unit','mission__subject').order_by('-created_at','-pk')[:100])
    evidence=[];seen=set()
    for a in recent:
        if a.mission_id in seen:continue
        seen.add(a.mission_id)
        if not a.has_delayed_same and a.mission.concept_unit_id not in failed_units:
            continue
        item=progress_evidence(user,a)
        if item and item['label'] in ('다른 문제에서도 확인했어요','시간이 지난 뒤 다시 확인'):
            evidence.append({'attempt':a,**item})
        if len(evidence)>=5:break
    unvisited_chapters = len({(m.course,m.chapter_code) for m in bank if m.chapter_code}
        - {(m.course,m.chapter_code) for m in bank if m.pk in states and m.chapter_code})
    return {'missions':chosen,'label':label,'minutes':minutes,'limit':limit,'size':len(chosen),
        'has_content':bool(bank),'all_courses':bool(settings and settings.all_courses),'days_left':days,'goal':goal,
        'stable_count':stable,'evidence':evidence,'has_unvisited':bool(unvisited_chapters),
        'tight_schedule': days is not None and 0<=days and unvisited_chapters>(days+1)*limit,
        'changed_count':len(changed),'has_due':bool(due),'has_more_due':len(due)>sum(m in due for m in chosen)}
