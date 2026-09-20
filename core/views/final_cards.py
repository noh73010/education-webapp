from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.models import ConfusionCard, UserWeakness
from core.services.learning_concepts import get_answer_display
from core.services.learning_experience import reviewed_concept
from core.services.subjects import get_current_subject


@login_required
def final_cards(request):
    subject, _ = get_current_subject(request)
    cards = list(
        ConfusionCard.objects.filter(
            user=request.user,
            subject=subject,
            mastered=False,
            mission__is_usable_for_set=True,
        )
        .exclude(mission__review_status="confirmed_error")
        .select_related("mission", "mission__concept_unit")
        .order_by("next_review_at", "-times_seen")[:20]
    )
    for card in cards:
        card.selected_display = get_answer_display(card.mission, card.selected_answer)
        card.correct_display = get_answer_display(card.mission, card.correct_answer)
        card.reviewed_concept = reviewed_concept(card.mission)
    weaknesses = list(
        UserWeakness.objects.filter(user=request.user, subject=subject)
        .exclude(status=UserWeakness.STATUS_MASTERED)
        .select_related("wrong_pattern").order_by("-severity", "next_review_at")[:10]
    )
    return render(request, "core/final_cards.html", {
        "current_subject": subject, "cards": cards, "weaknesses": weaknesses,
    })
