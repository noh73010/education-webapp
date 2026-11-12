from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.urls import reverse
from django.http import HttpResponseBadRequest
from django.utils.http import url_has_allowed_host_and_scheme
from urllib.parse import urlencode
from django.utils import timezone
from core.models import Attempt, LearningExposure
from core.services.subjects import get_current_subject
from core.services.efficient_learning import scoped_missions, suppressed_ids, chapter_rows, alternatives
from core.services.review_schedule import get_mission_review_states


@login_required
def study_library(request):
    subject, _ = get_current_subject(request)
    course = request.GET.get('course', '')
    chapter = request.GET.get('chapter', '')
    mode = request.GET.get('mode', '')
    qs = scoped_missions(subject)
    if course:
        qs = qs.filter(course=course)
    if chapter or request.GET.get('scope') == 'chapter':
        qs = qs.filter(chapter_code=chapter)
    missions = list(qs.order_by('pk'))
    states = get_mission_review_states(request.user, [m.pk for m in missions])
    suppressed = suppressed_ids(request.user)
    if mode == 'new':
        viewed = LearningExposure.objects.filter(user=request.user).values_list('mission_id', flat=True)
        attempted = Attempt.objects.valid_for_learning().filter(user=request.user).values_list('mission_id', flat=True)
        excluded = set(viewed) | set(attempted) | suppressed
        missions = [m for m in missions if m.pk not in excluded]
    elif mode == 'review':
        missions = [m for m in missions if (states.get(m.pk, {}).get('status') in ('wrong', 'uncertain') or states.get(m.pk, {}).get('is_due')) and m.pk not in suppressed]
        missions.sort(key=lambda m:(not states[m.pk]['is_due'], states[m.pk]['due_date'], m.pk))
    elif mode == 'history':
        seen = set(Attempt.objects.valid_for_learning().filter(user=request.user).values_list('mission_id',flat=True))
        seen.update(LearningExposure.objects.filter(user=request.user).values_list('mission_id', flat=True))
        missions = [m for m in missions if m.pk in seen]
    else:
        missions = []
    if request.GET.get('start') == '1' and missions:
        from core.services.daily_review import start_study_queue
        start_study_queue(request, subject, missions, label=course or subject.name, mode=mode)
        return redirect('mission_detail', mission_id=missions[0].pk)
    return render(request, 'core/study_library.html', {'subject':subject, 'chapters':chapter_rows(request.user,subject), 'study_missions':Paginator(missions,30).get_page(request.GET.get('page')), 'remaining':len(missions), 'mode':mode, 'course':course, 'chapter':chapter, 'scope':request.GET.get('scope', '')})


@login_required
@require_POST
def learning_signal(request, mission_id):
    subject, _ = get_current_subject(request)
    mission = get_object_or_404(scoped_missions(subject), pk=mission_id)
    action = request.POST.get('action')
    if action == 'confidence':
        attempt_id = request.POST.get('attempt', '')
        if not attempt_id.isdigit():
            return HttpResponseBadRequest('올바른 풀이 기록을 선택해 주세요.')
        attempt = get_object_or_404(Attempt, pk=attempt_id, user=request.user, mission=mission)
        value = request.POST.get('confidence', '')
        if value not in ('guessed', 'unsure', 'certain'):
            return HttpResponseBadRequest('올바른 확신도를 선택해 주세요.')
        latest = Attempt.objects.valid_for_learning().filter(user=request.user,mission=mission).order_by('-created_at','-pk').first()
        if latest is None or latest.pk != attempt.pk:
            messages.info(request, '더 최근의 풀이가 있어 마지막 기록을 유지했어요.')
            destination = reverse('mission_detail',args=[mission.pk])
            if latest:
                destination += f'?attempt={latest.pk}'
            return redirect(destination)
        attempt.confidence_level = value
        attempt.save(update_fields=['confidence_level'])
        if value in ('guessed', 'unsure'):
            LearningExposure.objects.filter(user=request.user,mission=mission).update(known_until=None)
        messages.success(request, f"✓ ‘{attempt.get_confidence_level_display()}’로 저장됐어요. 복습 안내에 반영됩니다.")
        next_url = request.POST.get('next', '')
        if next_url.startswith('/') and not next_url.startswith('//') and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect('next_learning_mission', mission_id=mission.pk)
    if action == 'known':
        exposure = get_object_or_404(LearningExposure, user=request.user, mission=mission)
        exposure.known_until = timezone.now() + timedelta(days=7)
        exposure.save()
    elif action == 'view':
        LearningExposure.objects.update_or_create(user=request.user, mission=mission, defaults={})
        from core.services.daily_review import advance_study_queue
        destination = advance_study_queue(request, subject, mission)
        if destination:
            request.session['explanation_next'] = {'mission_id':mission.pk,'url':destination}
    return redirect(reverse('mission_detail', args=[mission.pk]) + '?explanation=1')


@login_required
def next_learning_mission(request, mission_id):
    subject, _ = get_current_subject(request)
    current = get_object_or_404(scoped_missions(subject), pk=mission_id)
    attempted = Attempt.objects.valid_for_learning().filter(user=request.user).values('mission_id')
    viewed = LearningExposure.objects.filter(user=request.user).values('mission_id')
    candidates = scoped_missions(subject).filter(course=current.course).exclude(pk=current.pk).exclude(pk__in=attempted).exclude(pk__in=viewed).exclude(pk__in=suppressed_ids(request.user))
    mission = candidates.filter(chapter_code=current.chapter_code).order_by('pk').first() or candidates.order_by('chapter_code','pk').first()
    if mission:
        return redirect('mission_detail', mission_id=mission.pk)
    return render(request, 'core/study_pause.html', {'subject': subject, 'course': current.course})
