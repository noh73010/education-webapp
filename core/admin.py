from django.contrib import admin
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
    AttemptWrongPattern
)


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "skill", "level", "question_type", "is_usable_for_set", "is_quality_checked", "created_at")
    list_filter = ("skill", "level", "question_type", "answer_input_type", "is_usable_for_set", "is_quality_checked")
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
    list_filter = ("is_premium",)
    search_fields = ("user__username",)
    list_select_related = ("user",)
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