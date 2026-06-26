from django.conf import settings
from django.db import models


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

    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [
            models.Index(fields=["skill", "level"]),
        ]

    def __str__(self):
        return f"[{self.skill}] {self.title}"


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

    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)

    skill = models.CharField(max_length=100, blank=True, default="")

    description = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["skill", "name"]

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


class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mission = models.ForeignKey(Mission, on_delete=models.PROTECT)

    is_correct = models.BooleanField(default=False)
    time_spent_sec = models.PositiveIntegerField(null=True, blank=True)
    submitted_answer = models.TextField(blank=True, default="")
    daily_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "mission", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "daily_date"]),
        ]

    def __str__(self):
        return f"{self.user} / {self.mission} / {'O' if self.is_correct else 'X'}"


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
    submitted_at = models.DateTimeField(null=True, blank=True)

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
    STATUS_CHOICES = [
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

    score = models.PositiveIntegerField(default=0)
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
