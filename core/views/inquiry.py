from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import InquiryForm
from core.models import Inquiry
from core.services.analytics import record_event
from core.services.access import premium_gating_enabled
from core.services.inquiry_access import is_inquiry_owner


def inquiry(request):
    gating_enabled = premium_gating_enabled()
    if request.method == "POST":
        form = InquiryForm(
            request.POST,
            premium_gating_enabled=(gating_enabled or request.POST.get("inquiry_type") == "premium"),
            user=request.user,
        )
        if form.is_valid():
            inquiry_obj = form.save(commit=False)
            if request.user.is_authenticated:
                inquiry_obj.user = request.user
            inquiry_obj.save()

            record_event(
                request.user,
                "submit_inquiry",
                page="inquiry",
                metadata={"inquiry_type": inquiry_obj.inquiry_type},
            )
            return redirect("inquiry_done")
    else:
        form = InquiryForm(premium_gating_enabled=gating_enabled, user=request.user)

    return render(request, "core/inquiry_form.html", {
        "form": form,
        "premium_gating_enabled": gating_enabled,
    })


def inquiry_done(request):
    return render(request, "core/inquiry_done.html", {
        "premium_gating_enabled": premium_gating_enabled(),
    })


@login_required
def my_inquiries(request):
    inquiries = Paginator(Inquiry.objects.filter(user=request.user), 20).get_page(request.GET.get("page"))
    return render(request, "core/my_inquiries.html", {"inquiries": inquiries})


@login_required
def inquiry_detail(request, inquiry_id):
    inquiry_obj = get_object_or_404(Inquiry, pk=inquiry_id)
    owner = is_inquiry_owner(request.user)
    if inquiry_obj.user_id != request.user.id and not owner:
        raise Http404
    return render(request, "core/inquiry_detail.html", {"inquiry": inquiry_obj, "is_inquiry_owner": owner})


@login_required
def inquiry_inbox(request):
    if not is_inquiry_owner(request.user):
        raise Http404
    inquiries = Paginator(Inquiry.objects.select_related("user"), 20).get_page(request.GET.get("page"))
    return render(request, "core/inquiry_inbox.html", {"inquiries": inquiries})


@login_required
@require_POST
def inquiry_reply(request, inquiry_id):
    if not is_inquiry_owner(request.user):
        raise Http404
    inquiry_obj = get_object_or_404(Inquiry, pk=inquiry_id)
    reply = request.POST.get("reply", "").strip()
    if inquiry_obj.user_id is None and request.POST.get("guest_contacted") != "yes":
        return render(request, "core/inquiry_detail.html", {
            "inquiry": inquiry_obj,
            "is_inquiry_owner": True,
            "reply_error": "비회원에게 이메일로 별도 연락한 뒤 확인해 주세요.",
        }, status=400)
    if not reply or len(reply) > 10000:
        return render(request, "core/inquiry_detail.html", {
            "inquiry": inquiry_obj,
            "is_inquiry_owner": True,
            "reply_error": "답변을 1~10,000자로 입력하세요.",
        }, status=400)
    inquiry_obj.staff_reply = reply
    inquiry_obj.replied_at = timezone.now()
    inquiry_obj.status = "done"
    inquiry_obj.save(update_fields=["staff_reply", "replied_at", "status", "updated_at"])
    return redirect("inquiry_detail", inquiry_id=inquiry_obj.pk)
