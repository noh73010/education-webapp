# core/services/exam_analysis.py

def build_exam_analysis(exam, skill_rows, wrong_items):
    """
    시험 결과를 바탕으로 약점 분석 문장과 추천 복습 스킬을 만든다.
    반환값:
    {
        "summary_lines": [...],
        "weak_skills": [...],
        "strong_skills": [...],
        "time_comment": "...",
        "pass_probability": 0,
        "pass_label": "...",
    }
    """

    summary_lines = []
    weak_skills = []
    strong_skills = []

    # 1) 전체 점수 기반 총평
    if exam.score >= 85:
        summary_lines.append("전체 성적은 안정적입니다. 실전 감각만 더 다듬으면 됩니다.")
    elif exam.score >= 70:
        summary_lines.append("기본기는 갖춰졌지만 일부 스킬에서 흔들립니다.")
    elif exam.score >= 50:
        summary_lines.append("핵심 유형은 알고 있지만 취약 영역이 분명합니다.")
    else:
        summary_lines.append("아직 전반적인 보강이 필요합니다. 기초 스킬부터 다시 점검해야 합니다.")

    # 2) 스킬별 강점/약점 분류
    sorted_rows = sorted(skill_rows, key=lambda r: (r["accuracy"], r["total"]))
    for row in sorted_rows:
        skill = row["mission__skill"]
        acc = row["accuracy"]
        total = row["total"]

        if total == 0:
            continue

        if acc <= 50:
            weak_skills.append({
                "skill": skill,
                "accuracy": acc,
                "total": total,
            })
        elif acc >= 80:
            strong_skills.append({
                "skill": skill,
                "accuracy": acc,
                "total": total,
            })

    if weak_skills:
        top_weak = weak_skills[0]
        summary_lines.append(
            f"가장 취약한 스킬은 {top_weak['skill']}이며 정답률은 {top_weak['accuracy']}%입니다."
        )

    if len(weak_skills) >= 2:
        second_weak = weak_skills[1]
        summary_lines.append(
            f"{second_weak['skill']}도 보강이 필요합니다. 현재 정답률은 {second_weak['accuracy']}%입니다."
        )

    if strong_skills:
        top_strong = sorted(strong_skills, key=lambda r: (-r["accuracy"], -r["total"]))[0]
        summary_lines.append(
            f"상대적으로 안정적인 스킬은 {top_strong['skill']}이며 정답률은 {top_strong['accuracy']}%입니다."
        )

    # 3) 시간 관리 코멘트
    unanswered_count = sum(1 for item in wrong_items if item.user_answer_correct is None)

    if unanswered_count >= 5:
        time_comment = f"미응답 문제가 {unanswered_count}개입니다. 시간 관리가 약한 편입니다."
    elif unanswered_count >= 1:
        time_comment = f"미응답 문제가 {unanswered_count}개 있습니다. 후반 운영을 더 안정화해야 합니다."
    else:
        time_comment = "모든 문제에 응답했습니다. 시간 관리는 비교적 안정적입니다."

    summary_lines.append(time_comment)

    # 4) 복습 추천 문장
    if weak_skills:
        review_targets = ", ".join(skill["skill"] for skill in weak_skills[:3])
        summary_lines.append(f"다음 복습 우선순위는 {review_targets} 입니다.")
    else:
        summary_lines.append("특정 취약 스킬이 두드러지지 않습니다. 실전 반복으로 안정성을 높이면 됩니다.")

    # 5) 합격 확률 계산
    # 컴활 2급 기준: 60점 이상을 합격권으로 간주
    base_score = exam.score
    pass_score = 60
    gap = pass_score - base_score

    # 1차: 합격 기준과의 거리로 기본 확률 설정
    if gap <= 0:
        # 이미 합격선 이상이면 80% 이상에서 시작
        pass_probability = 80 + min(abs(gap) * 0.5, 15)
    else:
        # 합격선 미달이면 점수 차이만큼 빠르게 감소
        pass_probability = max(5, 60 - gap * 2)

    # 2차: 약점 스킬이 많으면 감점
    pass_probability -= min(len(weak_skills) * 4, 12)

    # 3차: 미응답 문제는 시간 관리 취약으로 추가 감점
    pass_probability -= min(unanswered_count * 1.0, 8)

    # 4차: 강점 스킬은 소폭 보정
    pass_probability += min(len(strong_skills) * 2, 6)

    # 범위 고정
    pass_probability = max(1, min(99, round(pass_probability)))

    if pass_probability >= 85:
        pass_label = "합격권"
    elif pass_probability >= 65:
        pass_label = "합격권 근접"
    elif pass_probability >= 40:
        pass_label = "보강 필요"
    else:
        pass_label = "위험"

    # 6) 합격까지 부족한 문제 수 계산
    pass_score = 60
    total_questions = exam.total_questions or 40
    required_correct = int(total_questions * pass_score / 100)

    missing_to_pass = max(required_correct - exam.correct_count, 0)
    surplus_after_pass = max(exam.correct_count - required_correct, 0)

    if missing_to_pass > 0:
        pass_gap_text = f"합격까지 부족한 문제 수: {missing_to_pass}문제"
    else:
        pass_gap_text = f"합격선 충족 / 여유 {surplus_after_pass}문제"

    # 7) 약점 → 합격 연결 문장
    if missing_to_pass > 0 and weak_skills:
        top_targets = weak_skills[:2]

        improvement_lines = []
        for skill in top_targets:
            improvement_lines.append(
                f"{skill['skill']} 정답률을 {min(skill['accuracy'] + 30, 80)}% 수준까지 올리면"
            )

        improvement_text = " / ".join(improvement_lines)

        pass_strategy_text = (
            f"현재 상태에서 합격까지 약 {missing_to_pass}문제 부족합니다. "
            f"{improvement_text} 합격권 진입이 가능합니다."
        )
    else:
        pass_strategy_text = "현재 합격권입니다. 실수만 줄이면 안정적으로 합격 가능합니다."

    return {
        "summary_lines": summary_lines,
        "weak_skills": weak_skills[:3],
        "strong_skills": strong_skills[:3],
        "time_comment": time_comment,
        "pass_probability": pass_probability,
        "pass_label": pass_label,
        "required_correct": required_correct,
        "missing_to_pass": missing_to_pass,
        "surplus_after_pass": surplus_after_pass,
        "pass_gap_text": pass_gap_text,
        "pass_strategy_text": pass_strategy_text,
    }