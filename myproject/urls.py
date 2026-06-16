from django.contrib import admin
from django.urls import path
from django.contrib.auth import views as auth_views

from core.views import (
    AnalyticsLoginView,
    admin_dashboard,
    inquiry,
    inquiry_done,
    landing,
    mission_list,
    mission_detail,
    stats,
    wrong_notes,
    pattern_training,

    exam_start,
    exam_create,
    exam_take,
    exam_submit,
    exam_result,
    exam_recommend_start,
    exam_history,

    premium_info,

    problem_set_list,
    problem_set_detail,
    problem_set_start,
    problem_set_result,
    problem_set_wrong_retry,
    problem_set_wrong_retry_result,
    signup,
)
from core.views.missions import (
    learning_type_training_start,
    learning_type_training_result,
)

urlpatterns = [
    path("", landing, name="landing"),
    path("inquiry/", inquiry, name="inquiry"),
    path("inquiry/done/", inquiry_done, name="inquiry_done"),

    path("admin/", admin.site.urls),
    path("admin-dashboard/", admin_dashboard, name="admin_dashboard"),

    path(
        "login/",
        AnalyticsLoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path("signup/", signup, name="signup"),

    # missions
    path("missions/", mission_list, name="mission_list"),
    
    path(
        "missions/learning-type/<str:skill>/<str:learning_type>/start/",
        learning_type_training_start,
        name="learning_type_training_start",
    ),
    
    path(
        "missions/learning-type/<str:skill>/<str:learning_type>/result/",
        learning_type_training_result,
        name="learning_type_training_result",
    ),

    path(
        "missions/<int:mission_id>/",
        mission_detail,
        name="mission_detail",
    ),

    # problem sets
    path(
        "problem-sets/",
        problem_set_list,
        name="problem_set_list",
    ),

    path(
        "problem-sets/<int:set_id>/",
        problem_set_detail,
        name="problem_set_detail",
    ),

    path(
        "problem-sets/<int:set_id>/start/",
        problem_set_start,
        name="problem_set_start",
    ),

    path(
        "problem-sets/result/<int:session_id>/",
        problem_set_result,
        name="problem_set_result",
    ),

    path(
        "problem-sets/result/<int:session_id>/wrong-retry/",
        problem_set_wrong_retry,
        name="problem_set_wrong_retry",
    ),

    path(
        "problem-sets/result/<int:session_id>/wrong-retry/result/",
        problem_set_wrong_retry_result,
        name="problem_set_wrong_retry_result",
    ),

    # pattern training
    path(
        "pattern-training/<str:pattern_code>/start/",
        pattern_training.pattern_training_start,
        name="pattern_training_start",
    ),

    path(
        "pattern-training/<str:pattern_code>/result/",
        pattern_training.pattern_training_result,
        name="pattern_training_result",
    ),

    # stats
    path("stats/", stats, name="stats"),

    path(
        "wrong-notes/",
        wrong_notes,
        name="wrong_notes",
    ),

    # exams
    path("exam/", exam_start, name="exam_start"),

    path(
        "exam/create/",
        exam_create,
        name="exam_create",
    ),

    path(
        "exam/<int:exam_id>/<int:order_no>/",
        exam_take,
        name="exam_take",
    ),

    path(
        "exam/<int:exam_id>/submit/",
        exam_submit,
        name="exam_submit",
    ),

    path(
        "exam/<int:exam_id>/result/",
        exam_result,
        name="exam_result",
    ),

    path(
        "exam/<int:exam_id>/recommend-start/",
        exam_recommend_start,
        name="exam_recommend_start",
    ),

    path(
        "exam/history/",
        exam_history,
        name="exam_history",
    ),

    # premium
    path(
        "premium/",
        premium_info,
        name="premium_info",
    ),
]
