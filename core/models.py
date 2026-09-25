import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


class Subject(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Mission(models.Model):
    SOURCE_TYPES = [("unknown", "출처 미등록"), ("past", "기출"),
                    ("adapted", "기출 변형"), ("original", "자체 제작")]
    REVIEW_UNREVIEWED = "unreviewed"
    REVIEW_VERIFIED = "verified"
    REVIEW_CONFIRMED_ERROR = "confirmed_error"
    REVIEW_STATUS_CHOICES = [
        (REVIEW_UNREVIEWED, "검수 전"),
        (REVIEW_VERIFIED, "검수 완료"),
        (REVIEW_CONFIRMED_ERROR, "오류 확인 · 출제 중지"),
    ]
    source_type = models.CharField(max_length=12, choices=SOURCE_TYPES, default="unknown")
    source_reference = models.CharField(max_length=300, blank=True, default="")
    reviewed_on = models.DateField(null=True, blank=True)
    review_status = models.CharField(
        max_length=24,
        choices=REVIEW_STATUS_CHOICES,
        default=REVIEW_UNREVIEWED,
        db_index=True,
    )
    concept_unit = models.ForeignKey("ConceptUnit", on_delete=models.SET_NULL, null=True, blank=True)

    def clean(self):
        super().clean()
        if self.concept_unit_id and self.concept_unit.subject_id != self.subject_id:
            raise ValidationError({"concept_unit": "같은 자격증의 개념만 연결할 수 있습니다."})

    QUESTION_TYPE_CHOICES = [
        ("manual", "수동 확인형"),
        ("short_answer", "단답 입력형"),
        ("value_answer", "값 입력형"),
        ("choice_one", "객관식 단일 선택형"),
        ("true_false", "O/X 판단형"),
        ("error_detect", "오류 찾기형"),
    ]

    ANSWER_INPUT_TYPE_CHOICES = [
        ("none", "입력 없음"),
        ("text", "텍스트"),
        ("number", "숫자"),
        ("date", "날짜"),
    ]

    QUALITY_LEVEL_CHOICES = [
        ("basic", "basic"),
        ("standard", "standard"),
        ("practical", "practical"),
    ]
    DIFFICULTY_CHOICES = [
        ("하", "하"),
        ("중", "중"),
        ("상", "상"),
    ]

    external_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )

    title = models.CharField(max_length=200)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="missions",
    )
    course = models.CharField(max_length=100, blank=True, default="")
    chapter_code = models.CharField(max_length=20, blank=True, default="")
    chapter_name = models.CharField(max_length=200, blank=True, default="")
    difficulty = models.CharField(
        max_length=1,
        choices=DIFFICULTY_CHOICES,
        blank=True,
        default="",
    )
    skill = models.CharField(max_length=100)
    level = models.PositiveSmallIntegerField(default=1)
    prompt = models.TextField()
    answer_key = models.TextField(blank=True, default="")

    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default="manual",
    )
    LEARNING_TYPE_CHOICES = [
        ("result", "결과 예측형"),
        ("feature", "기능 선택형"),
        ("error", "오류 진단형"),
        ("next_action", "다음 행동형"),
        ("procedure", "절차 순서형"),
    ]

    learning_type = models.CharField(
        max_length=20,
        choices=LEARNING_TYPE_CHOICES,
        default="result",
    )
    answer_input_type = models.CharField(
        max_length=20,
        choices=ANSWER_INPUT_TYPE_CHOICES,
        default="none",
    )
    correct_answer = models.TextField(blank=True, default="")
    explanation = models.TextField(blank=True, default="")
    choice_explanations = models.JSONField(default=dict, blank=True)
    concept_summary = models.TextField(blank=True, default="")
    exam_tip = models.TextField(blank=True, default="")
    answer_schema = models.TextField(blank=True, default="")
    wrong_pattern_code = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )
    variation_group = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    is_quality_checked = models.BooleanField(default=False)
    quality_level = models.CharField(
        max_length=20,
        choices=QUALITY_LEVEL_CHOICES,
        default="basic",
    )
    is_usable_for_set = models.BooleanField(default=True)
    quality_note = models.TextField(blank=True, default="")

    content_version = models.PositiveIntegerField(default=1)
    content_fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)
    grading_fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [
            models.Index(fields=["skill", "level"]),
            models.Index(fields=["subject", "course", "chapter_code"]),
        ]

    def save(self, *args, **kwargs):
        from core.services.mission_versioning import (
            invalidate_attempts_for_grading_change,
            mission_content_fingerprint,
            mission_grading_fingerprint,
        )

        previous = None
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "content_version", "content_fingerprint", "grading_fingerprint"
            ).first()

        new_content_fingerprint = mission_content_fingerprint(self)
        new_grading_fingerprint = mission_grading_fingerprint(self)
        previous_version = previous["content_version"] if previous else 1
        content_changed = bool(
            previous
            and previous["content_fingerprint"]
            and previous["content_fingerprint"] != new_content_fingerprint
        )
        grading_changed = bool(
            previous
            and previous["grading_fingerprint"]
            and previous["grading_fingerprint"] != new_grading_fingerprint
        )

        self.content_version = previous_version + 1 if content_changed else max(previous_version, 1)
        self.content_fingerprint = new_content_fingerprint
        self.grading_fingerprint = new_grading_fingerprint

        # A confirmed error is an editorial decision. Imports cannot silently
        # make it eligible again.
        if self.review_status == self.REVIEW_CONFIRMED_ERROR:
            self.is_usable_for_set = False
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            required = {"content_version", "content_fingerprint", "grading_fingerprint"}
            if self.review_status == self.REVIEW_CONFIRMED_ERROR:
                required.add("is_usable_for_set")
            kwargs["update_fields"] = set(update_fields) | required

        self._grading_change_impact = {"attempts": 0, "users": 0, "user_ids": ()}
        with transaction.atomic():
            result = super().save(*args, **kwargs)
            if grading_changed:
                impact = invalidate_attempts_for_grading_change(
                    mission=self,
                    previous_version=previous_version,
                )
                self._grading_change_impact = {
                    "attempts": impact.attempts,
                    "users": impact.users,
                    "user_ids": impact.user_ids,
                }
            return result

    def __str__(self):
        return f"[{self.skill}] {self.title}"


class MissionImage(models.Model):
    mission = models.OneToOneField(
        Mission,
        on_delete=models.CASCADE,
        related_name="question_image",
    )
    static_path = models.CharField(max_length=500)
    alt_text = models.CharField(max_length=300, blank=True, default="")
    source = models.CharField(max_length=30, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["mission_id"]

    def __str__(self):
        return f"{self.mission.external_id} / {self.static_path}"


class WrongReason(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
class WrongPattern(models.Model):
    """
    반복되는 오답 유형 정의
    예:
    - COUNT/COUNTA 혼동
    - VLOOKUP 열번호 오류
    - IF 조건 반대로 작성
    """

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, null=True, blank=True,
        related_name="wrong_patterns",
    )
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=200)

    skill = models.CharField(max_length=100, blank=True, default="")

    description = models.TextField(blank=True, default="")
    minimum_evidence = models.PositiveSmallIntegerField(default=2)
    remediation_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["skill", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "code"], name="unique_wrong_pattern_per_subject"
            ),
        ]

    def __str__(self):
        return f"{self.skill} - {self.name}"


class AttemptWrongPattern(models.Model):
    """
    사용자의 풀이에서 발생한 오답 패턴 기록
    """

    attempt = models.ForeignKey(
        "Attempt",
        on_delete=models.CASCADE,
        related_name="wrong_patterns",
    )

    wrong_pattern = models.ForeignKey(
        "WrongPattern",
        on_delete=models.CASCADE,
        related_name="attempts",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("attempt", "wrong_pattern")]


class UserWeakness(models.Model):
    STATUS_SUSPECTED = "suspected"
    STATUS_ACTIVE = "active"
    STATUS_TRAINING = "training"
    STATUS_REVIEW_DUE = "review_due"
    STATUS_MASTERED = "mastered"
    STATUS_RELAPSED = "relapsed"
    STATUS_CHOICES = [
        (STATUS_SUSPECTED, "의심"), (STATUS_ACTIVE, "약점 확정"),
        (STATUS_TRAINING, "집중 훈련 중"), (STATUS_REVIEW_DUE, "재평가 대기"),
        (STATUS_MASTERED, "극복"), (STATUS_RELAPSED, "재발"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weaknesses")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="user_weaknesses")
    wrong_pattern = models.ForeignKey(WrongPattern, on_delete=models.CASCADE, related_name="user_weaknesses")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUSPECTED)
    severity = models.PositiveSmallIntegerField(default=0)
    confidence = models.PositiveSmallIntegerField(default=0)
    recent_failure_count = models.PositiveIntegerField(default=0)
    consecutive_successes = models.PositiveIntegerField(default=0)
    first_detected_at = models.DateTimeField(auto_now_add=True)
    last_detected_at = models.DateTimeField(auto_now=True)
    last_trained_at = models.DateTimeField(null=True, blank=True)
    next_review_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "subject", "wrong_pattern"], name="unique_user_subject_weakness"
        )]
        indexes = [
            models.Index(fields=["user", "subject", "status"]),
            models.Index(fields=["user", "next_review_at"]),
        ]


class CertificationPolicy(models.Model):
    subject = models.OneToOneField(Subject, on_delete=models.CASCADE, related_name="certification_policy")
    passing_score = models.PositiveSmallIntegerField(default=60)
    minimum_area_score = models.PositiveSmallIntegerField(default=40)
    exam_question_count = models.PositiveIntegerField(default=0)
    exam_duration_minutes = models.PositiveIntegerField(default=0)
    readiness_min_attempts = models.PositiveIntegerField(default=30)
    recent_attempt_window = models.PositiveIntegerField(default=100)
    required_mock_exam_count = models.PositiveSmallIntegerField(default=1)
    source_note = models.TextField(blank=True, default="")


class CertificationArea(models.Model):
    policy = models.ForeignKey(CertificationPolicy, on_delete=models.CASCADE, related_name="areas")
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=100)
    course = models.CharField(max_length=100, blank=True, default="")
    chapter_prefix = models.CharField(max_length=20, blank=True, default="")
    weight = models.PositiveSmallIntegerField(default=20)
    passing_floor = models.PositiveSmallIntegerField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "code"]
        constraints = [models.UniqueConstraint(
            fields=["policy", "code"], name="unique_certification_area"
        )]


class AttemptQuerySet(models.QuerySet):
    def valid_for_learning(self):
        return self.filter(grading_valid=True)


class Attempt(models.Model):
    CONFIDENCE_GUESSED = "guessed"
    CONFIDENCE_UNSURE = "unsure"
    CONFIDENCE_CERTAIN = "certain"
    CONFIDENCE_CHOICES = [
        (CONFIDENCE_GUESSED, "찍었어요"),
        (CONFIDENCE_UNSURE, "헷갈렸어요"),
        (CONFIDENCE_CERTAIN, "확실했어요"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mission = models.ForeignKey(Mission, on_delete=models.PROTECT)

    is_correct = models.BooleanField(default=False)
    time_spent_sec = models.PositiveIntegerField(null=True, blank=True)
    submitted_answer = models.TextField(blank=True, default="")
    confidence_level = models.CharField(
        max_length=12, choices=CONFIDENCE_CHOICES, blank=True, default=""
    )
    mission_content_version = models.PositiveIntegerField(default=1)
    mission_content_fingerprint = models.CharField(max_length=64, blank=True, default="")
    mission_grading_fingerprint = models.CharField(max_length=64, blank=True, default="")
    mission_snapshot = models.JSONField(default=dict, blank=True)
    grading_valid = models.BooleanField(default=True, db_index=True)
    grading_invalidated_at = models.DateTimeField(null=True, blank=True)
    grading_invalidation_reason = models.CharField(max_length=300, blank=True, default="")
    daily_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AttemptQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["user", "mission", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "daily_date"]),
        ]

    def __str__(self):
        return f"{self.user} / {self.mission} / {'O' if self.is_correct else 'X'}"

    def save(self, *args, **kwargs):
        if self.mission_id and not self.mission_content_fingerprint:
            from core.services.mission_versioning import attempt_snapshot_defaults

            for field, value in attempt_snapshot_defaults(self.mission).items():
                setattr(self, field, value)
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {
                    "mission_content_version",
                    "mission_content_fingerprint",
                    "mission_grading_fingerprint",
                    "mission_snapshot",
                }
        return super().save(*args, **kwargs)


class AttemptWrongReason(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE)
    wrong_reason = models.ForeignKey(WrongReason, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("attempt", "wrong_reason")


class DailyMission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField()
    mission = models.ForeignKey(Mission, on_delete=models.PROTECT)

    class Meta:
        unique_together = ("user", "date", "mission")
        indexes = [
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self):
        return f"{self.user} / {self.date} / {self.mission_id}"


class UserStreak(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    current_streak = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    last_solved_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return (
            f"{self.user} / current={self.current_streak} / "
            f"best={self.best_streak} / last={self.last_solved_date}"
        )


class StudyProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_profile"
    )
    target_exam_date = models.DateField(null=True, blank=True)
    daily_minutes = models.PositiveSmallIntegerField(default=10)
    updated_at = models.DateTimeField(auto_now=True)


class ConfusionCard(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="confusion_cards"
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="confusion_cards")
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name="confusion_cards")
    selected_answer = models.TextField(blank=True, default="")
    correct_answer = models.TextField(blank=True, default="")
    times_seen = models.PositiveIntegerField(default=1)
    mastered = models.BooleanField(default=False)
    next_review_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user", "mission", "selected_answer"], name="unique_user_confusion_choice"
        )]
        indexes = [models.Index(fields=["user", "subject", "mastered", "next_review_at"])]


class UserAccess(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_premium = models.BooleanField(default=False)
    premium_started_at = models.DateTimeField(null=True, blank=True)
    premium_ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} / premium={self.is_premium}"


class UserEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=50, db_index=True)
    page = models.CharField(max_length=200, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} / {self.user_id or 'anonymous'} / {self.created_at:%Y-%m-%d %H:%M}"


class Inquiry(models.Model):
    mission = models.ForeignKey(Mission, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="error_reports")
    INQUIRY_TYPE_CHOICES = [
        ("premium", "프리미엄 신청"),
        ("bug", "오류 제보"),
        ("question", "일반 문의"),
        ("other", "기타 문의"),
    ]

    STATUS_CHOICES = [
        ("new", "새 문의"),
        ("in_progress", "처리 중"),
        ("done", "완료"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=200)
    inquiry_type = models.CharField(
        max_length=20,
        choices=INQUIRY_TYPE_CHOICES,
        default="question",
    )
    message = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["inquiry_type", "status"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_inquiry_type_display()} / {self.name} / {self.status}"


class ProblemSet(models.Model):
    SET_TYPE_CHOICES = [
        ("training", "훈련 세트"),
        ("review", "복습 세트"),
        ("exam_like", "실전형 세트"),
    ]

    title = models.CharField(max_length=200)
    generation_key = models.CharField(max_length=200, blank=True, default="", db_index=True)
    skill_group = models.CharField(max_length=100, blank=True, default="")
    level = models.PositiveSmallIntegerField(default=1)
    set_type = models.CharField(
        max_length=30,
        choices=SET_TYPE_CHOICES,
        default="training",
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["skill_group", "level"]),
            models.Index(fields=["set_type", "is_active"]),
        ]
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["generation_key"],
                condition=~models.Q(generation_key=""),
                name="unique_generated_problem_set_key",
            ),
        ]

    def __str__(self):
        return f"[{self.get_set_type_display()}] {self.title}"


class ProblemSetItem(models.Model):
    ROLE_CHOICES = [
        ("core", "핵심"),
        ("review", "복습"),
        ("challenge", "도전"),
    ]

    problem_set = models.ForeignKey(
        ProblemSet,
        on_delete=models.CASCADE,
        related_name="items",
    )
    mission = models.ForeignKey(
        Mission,
        on_delete=models.PROTECT,
        related_name="problem_set_items",
    )
    order_no = models.PositiveIntegerField()
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default="core",
    )

    class Meta:
        unique_together = ("problem_set", "order_no")
        ordering = ["order_no"]
        indexes = [
            models.Index(fields=["problem_set", "order_no"]),
            models.Index(fields=["mission"]),
        ]

    def __str__(self):
        return f"{self.problem_set_id} / {self.order_no} / {self.mission_id}"


class ProblemSetSession(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "진행중"),
        ("completed", "완료"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    problem_set = models.ForeignKey(
        ProblemSet,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    total_count = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    score = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-started_at"]),
            models.Index(fields=["problem_set", "-started_at"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} / {self.problem_set.title} / {self.status}"


class ProblemSetSessionItem(models.Model):
    problem_set_session = models.ForeignKey(
        ProblemSetSession,
        on_delete=models.CASCADE,
        related_name="items",
    )
    mission = models.ForeignKey(Mission, on_delete=models.PROTECT)
    order_no = models.PositiveIntegerField()
    is_correct = models.BooleanField(null=True, blank=True)
    submitted_answer = models.TextField(blank=True, default="")
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="problem_set_session_items",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    review_attempt_count = models.PositiveIntegerField(default=0)
    review_is_correct = models.BooleanField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("problem_set_session", "order_no")
        ordering = ["order_no"]
        indexes = [
            models.Index(fields=["problem_set_session", "order_no"]),
            models.Index(fields=["mission"]),
        ]

    def __str__(self):
        return f"{self.problem_set_session_id} / {self.order_no} / {self.mission_id}"


class ExamSession(models.Model):
    mode_config = models.JSONField(default=dict, blank=True)
    previous_sitting = models.OneToOneField("self", null=True, blank=True,
        on_delete=models.CASCADE, related_name="next_sitting")
    STATUS_CHOICES = [
        ("waiting", "시작 대기"),
        ("in_progress", "진행중"),
        ("submitted", "제출완료"),
        ("expired", "시간종료"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200, default="실전 모의고사")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    time_limit_min = models.PositiveIntegerField(default=40)
    total_questions = models.PositiveIntegerField(default=40)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress",
    )

    score = models.FloatField(default=0)
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    attempts_synced = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.user} / {self.title} / {self.status}"


class ExamSessionMission(models.Model):
    draft_answers = models.JSONField(default=dict, blank=True)
    draft_updated_at = models.DateTimeField(null=True, blank=True)
    submitted_answer = models.TextField(blank=True, default="")
    is_marked_for_review = models.BooleanField(default=False)
    exam_session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="items",
    )
    mission = models.ForeignKey(Mission, on_delete=models.PROTECT)

    order_no = models.PositiveIntegerField()
    user_answer_correct = models.BooleanField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("exam_session", "order_no")
        ordering = ["order_no"]
        indexes = [
            models.Index(fields=["exam_session", "order_no"]),
        ]

    def __str__(self):
        return f"{self.exam_session_id} / {self.order_no} / {self.mission_id}"
    
    
class PatternTrainingSession(models.Model):
    user = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="pattern_training_sessions",
    )

    wrong_pattern = models.ForeignKey(
        "WrongPattern",
        on_delete=models.CASCADE,
        related_name="training_sessions",
    )

    total = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    wrong = models.PositiveIntegerField(default=0)
    score = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.wrong_pattern.name} - {self.score}점"


class ConceptUnit(models.Model):
    """Editor-curated concept group, never inferred from a chapter code."""
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    comparison = models.TextField(help_text="헷갈리는 개념의 차이")
    example = models.TextField(blank=True)
    references = models.JSONField(default=list, blank=True, help_text="개념 검수 근거 URL 목록. 문제 원출처와 구분합니다.")
    reviewed_on = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.subject} / {self.title}"


class LearningStart(models.Model):
    EXPERIENCE_CHOICES = [("new", "처음 공부해요"), ("review", "이론을 한 번 봤어요"),
                          ("retry", "시험에 다시 도전해요")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    experience = models.CharField(max_length=12, choices=EXPERIENCE_CHOICES)
    diagnostic_ids = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "subject"], name="unique_learning_start")]


class CourseFocus(models.Model):
    """The learner's chosen course within a qualification, not a new Subject."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    course = models.CharField(max_length=100)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "subject"], name="unique_course_focus")]


class MissionWork(models.Model):
    """An unfinished draft becomes a submission receipt, retained for safe retries."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE)
    answers = models.JSONField(default=dict, blank=True)
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, null=True, blank=True)
    return_url = models.CharField(max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "mission"],
                       condition=models.Q(attempt__isnull=True), name="unique_pending_mission_work")]
