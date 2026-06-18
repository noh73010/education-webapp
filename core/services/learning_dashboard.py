from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from core.models import Attempt, AttemptWrongPattern, ExamSession, UserStreak
from core.services.skill_labels import get_skill_label


LEVELS = [
    {"level": 1, "name": "입문", "min_attempts": 0, "min_accuracy": 0},
    {"level": 2, "name": "기본기", "min_attempts": 10, "min_accuracy": 45},
    {"level": 3, "name": "실전 적응", "min_attempts": 25, "min_accuracy": 60},
    {"level": 4, "name": "합격권", "min_attempts": 45, "min_accuracy": 72},
    {"level": 5, "name": "고득점권", "min_attempts": 70, "min_accuracy": 85},
]


def _percent(part, total):
    return round((part / total) * 100, 1) if total else 0.0


def _recent_attempt_stats(user, limit=50):
    attempts = list(
        Attempt.objects
        .filter(user=user)
        .select_related("mission")
        .order_by("-created_at")[:limit]
    )
    total = len(attempts)
    correct = sum(1 for attempt in attempts if attempt.is_correct)

    return {
        "attempts": attempts,
        "total": total,
        "correct": correct,
        "accuracy": _percent(correct, total),
    }


def get_learning_level(user):
    stats = _recent_attempt_stats(user)
    total = stats["total"]
    accuracy = stats["accuracy"]

    current = LEVELS[0]
    for level in LEVELS:
        if total >= level["min_attempts"] and accuracy >= level["min_accuracy"]:
            current = level

    next_level = None
    for level in LEVELS:
        if level["level"] > current["level"]:
            next_level = level
            break

    if next_level:
        next_condition = (
            f"최근 풀이 {next_level['min_attempts']}개 이상, "
            f"정답률 {next_level['min_accuracy']}% 이상"
        )
    else:
        next_condition = "현재 최고 단계입니다. 실전 감각을 유지하세요."

    return {
        "level": current["level"],
        "name": current["name"],
        "label": f"LV{current['level']} {current['name']}",
        "recent_total": total,
        "recent_accuracy": accuracy,
        "next_condition": next_condition,
        "next_level": next_level,
    }


def get_exam_average(user, limit=3):
    exams = list(
        ExamSession.objects
        .filter(user=user, status="submitted")
        .order_by("-ended_at", "-started_at")[:limit]
    )

    if not exams:
        return None

    return round(sum(exam.score for exam in exams) / len(exams), 1)


def get_pass_readiness(user, streak=None):
    stats = _recent_attempt_stats(user)
    streak = streak or UserStreak.objects.filter(user=user).first()
    current_streak = streak.current_streak if streak else 0
    exam_average = get_exam_average(user)

    accuracy_score = min(stats["accuracy"], 100) * 0.40
    volume_score = min(stats["total"] / 50, 1) * 20
    exam_score = (exam_average if exam_average is not None else 0) * 0.25
    streak_score = min(current_streak / 7, 1) * 15
    score = round(accuracy_score + volume_score + exam_score + streak_score)
    score = max(0, min(score, 100))

    if stats["total"] == 0:
        message = "아직 준비도를 계산할 학습 기록이 부족합니다."
    elif score >= 80:
        message = "실전 점검과 오답 복습으로 마무리할 단계입니다."
    elif score >= 60:
        message = "기본 흐름은 잡혔습니다. 약점 유형을 조금 더 보강하세요."
    elif score >= 35:
        message = "풀이량과 정답률을 함께 끌어올리는 단계입니다."
    else:
        message = "오늘 추천 문제부터 풀며 기본 기록을 쌓아 보세요."

    return {
        "score": score,
        "recent_accuracy": stats["accuracy"],
        "recent_total": stats["total"],
        "exam_average": exam_average,
        "streak_days": current_streak,
        "message": message,
    }


def get_weakness_top3(user):
    skill_rows = list(
        Attempt.objects
        .filter(user=user)
        .values("mission__skill")
        .annotate(
            total=Count("id"),
            wrong=Count("id", filter=Q(is_correct=False)),
        )
        .filter(total__gte=2)
    )

    weaknesses = []
    for row in skill_rows:
        total = row["total"] or 0
        wrong = row["wrong"] or 0
        accuracy = _percent(total - wrong, total)
        weaknesses.append({
            "skill": row["mission__skill"],
            "skill_label": get_skill_label(row["mission__skill"]),
            "total": total,
            "wrong": wrong,
            "accuracy": accuracy,
            "reason": "정답률 낮음",
        })

    pattern_rows = list(
        AttemptWrongPattern.objects
        .filter(attempt__user=user)
        .values(
            "wrong_pattern__skill",
            "wrong_pattern__name",
        )
        .annotate(count=Count("id"))
        .order_by("-count")[:3]
    )

    for row in pattern_rows:
        skill = row["wrong_pattern__skill"] or ""
        weaknesses.append({
            "skill": skill,
            "skill_label": get_skill_label(skill) if skill else "오답 패턴",
            "total": row["count"],
            "wrong": row["count"],
            "accuracy": 0,
            "reason": row["wrong_pattern__name"] or "반복 오답",
        })

    weaknesses.sort(key=lambda item: (item["accuracy"], -item["wrong"], item["skill_label"]))

    unique = []
    seen = set()
    for item in weaknesses:
        key = (item["skill_label"], item["reason"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= 3:
            break

    return unique


def get_coach_message(user, weaknesses, level_info, pass_readiness):
    recent_stats = _recent_attempt_stats(user, limit=20)

    if recent_stats["total"] == 0:
        return {
            "title": "오늘 추천 문제부터 시작하세요",
            "message": "아직 풀이 기록이 부족합니다. 오늘 학습 시작 버튼으로 5문제를 먼저 풀어 보세요.",
        }

    if weaknesses:
        top = weaknesses[0]
        return {
            "title": f"{top['skill_label']} 보강이 우선입니다",
            "message": (
                f"최근 {top['skill_label']} 영역에서 약점 신호가 보입니다. "
                "로드맵 훈련이나 오답 복습을 먼저 진행해 보세요."
            ),
        }

    if pass_readiness["score"] < 60:
        return {
            "title": "풀이량을 조금 더 늘려 보세요",
            "message": "정답률만큼 풀이 기록도 중요합니다. 매일 추천 문제를 풀면 준비도가 안정적으로 올라갑니다.",
        }

    return {
        "title": f"{level_info['label']} 흐름을 유지하세요",
        "message": "현재 학습 흐름이 좋습니다. 모의고사와 오답 복습으로 실전 감각을 유지하세요.",
    }


def get_streak_message(streak):
    today = timezone.localdate()

    if not streak or not streak.last_solved_date:
        return "오늘 첫 문제를 풀면 연속 학습이 시작됩니다."

    if streak.last_solved_date == today:
        return "오늘 학습을 완료했습니다. 내일 다시 풀면 연속 학습이 이어집니다."

    if streak.last_solved_date == today - timedelta(days=1):
        return "오늘 한 문제만 풀어도 연속 학습이 이어집니다."

    return "오늘 학습하면 연속 학습을 새로 시작할 수 있습니다."


def build_learning_dashboard(user, streak=None):
    streak = streak or UserStreak.objects.filter(user=user).first()
    level_info = get_learning_level(user)
    pass_readiness = get_pass_readiness(user, streak=streak)
    weaknesses = get_weakness_top3(user)
    coach = get_coach_message(user, weaknesses, level_info, pass_readiness)

    return {
        "streak_message": get_streak_message(streak),
        "level": level_info,
        "pass_readiness": pass_readiness,
        "weakness_top3": weaknesses,
        "coach": coach,
        "ranking_placeholder": {
            "title": "주간 랭킹 준비 중",
            "message": "개인정보와 경쟁 요소를 신중히 검토한 뒤 선택 기능으로 제공할 예정입니다.",
        },
    }
