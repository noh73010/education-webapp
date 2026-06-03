import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


REQUIRED_FIELDS = [
    "id",
    "title",
    "skill_auto",
    "level",
    "prompt",
    "question_type",
    "answer_input_type",
    "correct_answer",
    "answer_schema",
    "explanation",
    "wrong_pattern_code",
    "variation_group",
]


CHOICE_TYPES = {"choice_one", "true_false", "error_detect"}
AUTO_GRADE_TYPES = {
    "short_answer",
    "value_answer",
    "choice_one",
    "true_false",
    "error_detect",
}


def validate_csv(csv_path: str):
    path = Path(csv_path)

    if not path.exists():
        print(f"파일 없음: {path}")
        return False

    errors = []
    seen_ids = set()

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames != REQUIRED_FIELDS:
            errors.append("CSV 헤더가 기준과 다릅니다.")

        for row_no, row in enumerate(reader, start=2):
            mission_id = (row.get("id") or "").strip()
            title = (row.get("title") or "").strip()
            skill = (row.get("skill_auto") or "").strip()
            level = (row.get("level") or "").strip()
            prompt = (row.get("prompt") or "").strip()
            question_type = (row.get("question_type") or "").strip()
            answer_input_type = (row.get("answer_input_type") or "").strip()
            correct_answer = (row.get("correct_answer") or "").strip()
            answer_schema = (row.get("answer_schema") or "").strip()
            explanation = (row.get("explanation") or "").strip()

            prefix = f"{row_no}행 / {mission_id or 'ID없음'}"

            if not mission_id:
                errors.append(f"{prefix}: id 없음")

            if mission_id in seen_ids:
                errors.append(f"{prefix}: id 중복")
            seen_ids.add(mission_id)

            if not title:
                errors.append(f"{prefix}: title 없음")

            if not skill:
                errors.append(f"{prefix}: skill_auto 없음")

            if not level.isdigit():
                errors.append(f"{prefix}: level 숫자 아님")

            if len(prompt) < 80:
                errors.append(f"{prefix}: prompt가 너무 짧음")

            if "[CONTEXT]" not in prompt or "[QUESTION]" not in prompt:
                errors.append(f"{prefix}: 구조화 태그 부족")

            if question_type in CHOICE_TYPES and not answer_schema:
                errors.append(f"{prefix}: 선택형인데 answer_schema 없음")

            if question_type in AUTO_GRADE_TYPES and not correct_answer:
                errors.append(f"{prefix}: 자동채점형인데 correct_answer 없음")

            if not explanation:
                errors.append(f"{prefix}: explanation 없음")

            if answer_input_type not in {"none", "text", "number", "date"}:
                errors.append(f"{prefix}: answer_input_type 값 이상함")

    if errors:
        print("검증 실패")
        for error in errors:
            print("-", error)
        return False

    print("검증 통과")
    return True


if __name__ == "__main__":
    validate_csv(BASE_DIR / "generated" / "missions_scenario.csv")