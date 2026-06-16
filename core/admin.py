from django.contrib import admin
from django.utils import timezone
from datetime import timedelta
from .models import (
    Mission,
    Attempt,
    WrongReason,
    AttemptWrongReason,
    DailyMission,
    UserAccess,
    ProblemSet,
    ProblemSetItem,
    ProblemSetSession,
    ProblemSetSessionItem,
    WrongPattern,
    AttemptWrongPattern,
    ExamSession,
    ExamSessionMission,
    Inquiry,
    PatternTrainingSession,
    UserEvent,
)


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "skill",
        "level",
        "question_type",
        "learning_type",
        "quality_level",
        "is_usable_for_set",
        "is_quality_checked",
        "created_at",
    )

    list_filter = (
        "skill",
        "level",
        "question_type",
        "learning_type",
        "quality_level",
        "answer_input_type",
        "is_usable_for_set",
        "is_quality_checked",
    )
    search_fields = ("title", "prompt", "skill", "correct_answer", "explanation")
    ordering = ("-created_at",)
    list_per_page = 50


@admin.register(WrongReason)
class WrongReasonAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    ordering = ("name",)
    list_per_page = 50


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mission", "is_correct", "created_at")
    list_filter = ("is_correct", "mission__skill", "mission__level")
    search_fields = ("user__username", "mission__title", "mission__skill")
    ordering = ("-created_at",)
    list_select_related = ("user", "mission")
    list_per_page = 50
    date_hierarchy = "created_at"


@admin.register(AttemptWrongReason)
class AttemptWrongReasonAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "wrong_reason")
    list_filter = ("wrong_reason",)
    search_fields = ("attempt__user__username", "attempt__mission__title", "wrong_reason__name")
    list_select_related = ("attempt", "wrong_reason")
    list_per_page = 50
    
@admin.register(DailyMission)
class DailyMissionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "date", "mission")
    list_filter = ("date", "mission__skill", "mission__level")
    search_fields = ("user__username", "mission__title", "mission__skill")
    ordering = ("-date",)
    list_select_related = ("user", "mission")
    list_per_page = 50
    
@admin.register(UserAccess)
class UserAccessAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "is_premium", "premium_started_at", "premium_ended_at")
    list_filter = ("is_premium", "premium_started_at", "premium_ended_at")
    search_fields = ("user__username",)
    list_select_related = ("user",)
    list_per_page = 50
    actions = ("grant_30_days_premium", "revoke_premium")

    @admin.action(description="선택 사용자 30일 프리미엄 부여")
    def grant_30_days_premium(self, request, queryset):
        now = timezone.now()
        updated_count = 0

        for access in queryset:
            start_base = access.premium_ended_at if (
                access.is_premium
                and access.premium_ended_at
                and access.premium_ended_at > now
            ) else now

            access.is_premium = True
            access.premium_started_at = now
            access.premium_ended_at = start_base + timedelta(days=30)
            access.save(update_fields=[
                "is_premium",
                "premium_started_at",
                "premium_ended_at",
            ])
            updated_count += 1

        self.message_user(request, f"{updated_count}명에게 30일 프리미엄을 부여했습니다.")

    @admin.action(description="선택 사용자 프리미엄 해제")
    def revoke_premium(self, request, queryset):
        now = timezone.now()
        updated_count = queryset.update(
            is_premium=False,
            premium_ended_at=now,
        )
        self.message_user(request, f"{updated_count}명의 프리미엄을 해제했습니다.")
    

@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "user", "page", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("user__username", "event_type", "page")
    ordering = ("-created_at",)
    list_select_related = ("user",)
    list_per_page = 50
    date_hierarchy = "created_at"
    readonly_fields = ("user", "event_type", "page", "metadata", "created_at")

    def changelist_view(self, request, extra_context=None):
        today = timezone.localdate()
        today_count = UserEvent.objects.filter(created_at__date=today).count()
        extra_context = extra_context or {}
        extra_context["title"] = f"User events - today {today_count}"
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ("id", "inquiry_type", "status", "name", "contact", "user", "created_at")
    list_filter = ("inquiry_type", "status", "created_at")
    search_fields = ("name", "contact", "message", "user__username")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("user",)
    ordering = ("-created_at",)
    list_per_page = 50


@admin.register(ProblemSet)
class ProblemSetAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "skill_group", "level", "set_type", "is_active", "created_at")
    list_filter = ("set_type", "is_active", "level", "skill_group")
    search_fields = ("title", "skill_group", "description")
    ordering = ("-created_at",)
    list_per_page = 50


@admin.register(ProblemSetItem)
class ProblemSetItemAdmin(admin.ModelAdmin):
    list_display = ("id", "problem_set", "order_no", "mission", "role")
    list_filter = ("role", "problem_set__set_type")
    search_fields = ("problem_set__title", "mission__title", "mission__skill")
    ordering = ("problem_set", "order_no")
    list_select_related = ("problem_set", "mission")
    list_per_page = 100
    
@admin.register(ProblemSetSession)
class ProblemSetSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "problem_set",
        "status",
        "total_count",
        "correct_count",
        "wrong_count",
        "score",
        "started_at",
        "completed_at",
    )
    list_filter = ("status", "problem_set__set_type")
    search_fields = ("user__username", "problem_set__title")
    ordering = ("-started_at",)
    list_select_related = ("user", "problem_set")
    list_per_page = 50


@admin.register(ProblemSetSessionItem)
class ProblemSetSessionItemAdmin(admin.ModelAdmin):
    list_display = ("id", "problem_set_session", "order_no", "mission", "is_correct", "submitted_at")
    list_filter = ("is_correct",)
    search_fields = ("problem_set_session__problem_set__title", "mission__title")
    ordering = ("problem_set_session", "order_no")
    list_select_related = ("problem_set_session", "mission")
    list_per_page = 100
    
@admin.register(WrongPattern)
class WrongPatternAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "skill",
        "code",
        "name",
        "created_at",
    )

    search_fields = (
        "code",
        "name",
        "skill",
    )

    list_filter = (
        "skill",
    )


@admin.register(AttemptWrongPattern)
class AttemptWrongPatternAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "attempt",
        "wrong_pattern",
        "created_at",
    )

    list_filter = (
        "wrong_pattern",
    )
@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "title",
        "status",
        "score",
        "correct_count",
        "wrong_count",
        "started_at",
        "ended_at",
    )
    list_filter = ("status", "started_at")
    search_fields = ("user__username", "title")
    ordering = ("-started_at",)
    list_select_related = ("user",)
    list_per_page = 50


@admin.register(ExamSessionMission)
class ExamSessionMissionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "exam_session",
        "order_no",
        "mission",
        "user_answer_correct",
        "submitted_at",
    )
    list_filter = ("user_answer_correct",)
    search_fields = (
        "exam_session__user__username",
        "mission__title",
        "mission__skill",
    )
    ordering = ("exam_session", "order_no")
    list_select_related = ("exam_session", "mission")
    list_per_page = 100


@admin.register(PatternTrainingSession)
class PatternTrainingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "wrong_pattern",
        "score",
        "correct",
        "wrong",
        "total",
        "created_at",
    )
    list_filter = ("wrong_pattern", "created_at")
    search_fields = ("user__username", "wrong_pattern__name", "wrong_pattern__code")
    ordering = ("-created_at",)
    list_select_related = ("user", "wrong_pattern")
    list_per_page = 50
