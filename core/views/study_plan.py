from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from core.models import SubjectStudyPlan
from core.services.subjects import get_current_subject
from core.services.guided_study import build_guided_plan
from core.services.daily_review import start_study_queue
from core.services.analytics import record_event


@login_required
def study_plan(request):
    subject, _ = get_current_subject(request)
    error = None
    if request.method == 'POST':
        minutes = request.POST.get('minutes')
        scope = request.POST.get('scope')
        if minutes not in ('5','10','20') or scope not in ('selected','all'):
            error = '학습 분량과 범위를 다시 선택해 주세요.'
        else:
            SubjectStudyPlan.objects.update_or_create(user=request.user,subject=subject,
                defaults={'daily_minutes':int(minutes),'all_courses':scope=='all'})
            messages.success(request,'학습 계획을 저장했어요. 다음 학습부터 반영됩니다.')
            return redirect('study_plan')
    record_event(request.user, "study_plan_view", page="study_plan", metadata={"subject":subject.code})
    return render(request,'core/study_plan.html',{'plan':build_guided_plan(request.user,subject),
        'current_subject':subject,'error':error})


@login_required
@require_POST
def study_plan_start(request):
    subject, _ = get_current_subject(request)
    plan = build_guided_plan(request.user,subject)
    if not plan['missions']:
        messages.info(request,'지금 필요한 추천 학습을 마쳤어요. 다음 복습 때 이어가세요.' if plan['has_content'] else '이 범위의 문제는 준비 중이에요. 다른 과목을 선택해 주세요.')
        return redirect('study_plan')
    record_event(request.user, "study_plan_start", page="study_plan", metadata={"subject":subject.code,"size":plan["size"],"minutes":plan["minutes"],"all_courses":plan["all_courses"]})
    start_study_queue(request,subject,plan['missions'],label=plan['label'],mode='today',limit=10)
    state=request.session['daily_review_state']
    state['reasons']={str(m.pk):m.plan_reason for m in plan['missions']}
    request.session['daily_review_state']=state
    return redirect('mission_detail',mission_id=plan['missions'][0].pk)
