from django.shortcuts import redirect, render

from core.forms import InquiryForm
from core.services.analytics import record_event
from core.services.access import premium_gating_enabled


def inquiry(request):
    gating_enabled = premium_gating_enabled()
    if request.method == "POST":
        form = InquiryForm(
            request.POST,
            premium_gating_enabled=(gating_enabled or request.POST.get("inquiry_type") == "premium"),
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
        form = InquiryForm(premium_gating_enabled=gating_enabled)

    return render(request, "core/inquiry_form.html", {
        "form": form,
        "premium_gating_enabled": gating_enabled,
    })


def inquiry_done(request):
    return render(request, "core/inquiry_done.html", {
        "premium_gating_enabled": premium_gating_enabled(),
    })
