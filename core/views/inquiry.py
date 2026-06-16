from django.shortcuts import redirect, render

from core.forms import InquiryForm
from core.services.analytics import record_event


def inquiry(request):
    if request.method == "POST":
        form = InquiryForm(request.POST)
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
        form = InquiryForm()

    return render(request, "core/inquiry_form.html", {
        "form": form,
    })


def inquiry_done(request):
    return render(request, "core/inquiry_done.html")
