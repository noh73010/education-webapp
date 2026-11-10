from datetime import timedelta
from django.contrib.auth.decorators import login_required
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
        missions = [m for m in missions if states.get(m.pk, {}).get('status') in ('wrong', 'uncertain') and m.pk not in suppressed]
        missions.sort(key=lambda m:(not states[m.pk]['is_due'], states[m.pk]['due_date'], m.pk))
    elif mode == 'history':
        seen = set(Attempt.objects.valid_for_learning().filter(user=request.user).values_list('mission_id',flat=True))
        seen.update(LearningExposure.objects.filter(user=request.user).values_list('mission_id', flat=True))
        missions = [m for m in missions if m.pk in seen]
    else:
        missions = []
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
        if value in ('guessed', 'unsure', 'certain'):
            attempt.confidence_level = value
            attempt.save(update_fields=['confidence_level'])
        next_url = request.POST.get('next', '')
        suffix = ''
        if next_url.startswith('/') and not next_url.startswith('//') and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            suffix = '&' + urlencode({'next': next_url})
        return redirect(reverse('mission_detail', args=[mission.pk]) + f'?attempt={attempt.pk}' + suffix)
    if action == 'known':
        exposure = get_object_or_404(LearningExposure, user=request.user, mission=mission)
        exposure.known_until = timezone.now() + timedelta(days=7)
        exposure.save()
    elif action == 'view':
        LearningExposure.objects.update_or_create(user=request.user, mission=mission, defaults={})
    return redirect(reverse('mission_detail', args=[mission.pk]) + '?explanation=1')
