from datetime import datetime


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().split()).lower()


def try_parse_number(value: str):
    text = (value or "").strip().replace(",", "")
    return float(text)


def try_parse_date(value: str):
    text = (value or "").strip()

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise ValueError("지원하지 않는 날짜 형식입니다.")


def grade_answer(*, question_type: str, answer_input_type: str, submitted_answer: str, correct_answer: str):
    submitted_answer = (submitted_answer or "").strip()
    correct_answer = (correct_answer or "").strip()

    if not submitted_answer:
        return {
            "is_correct": False,
            "error": "답안을 입력하고 제출하세요.",
        }
    # 선택형 / OX / 오류찾기형
    if question_type in ("choice_one", "true_false", "error_detect"):
        return {
            "is_correct": normalize_text(submitted_answer) == normalize_text(correct_answer),
            "error": None,
        }
    # 숫자형
    if answer_input_type == "number":
        try:
            user_value = try_parse_number(submitted_answer)
            correct_value = try_parse_number(correct_answer)
        except ValueError:
            return {
                "is_correct": False,
                "error": "숫자 형식으로 입력해야 합니다.",
            }

        return {
            "is_correct": user_value == correct_value,
            "error": None,
        }

    # 날짜형
    if answer_input_type == "date":
        try:
            user_date = try_parse_date(submitted_answer)
            correct_date = try_parse_date(correct_answer)
        except ValueError:
            return {
                "is_correct": False,
                "error": "날짜 형식이 올바르지 않습니다. 예: 2024-03-25",
            }

        return {
            "is_correct": user_date == correct_date,
            "error": None,
        }

    # 텍스트형
    return {
        "is_correct": normalize_text(submitted_answer) == normalize_text(correct_answer),
        "error": None,
    }
    
def parse_answer_schema(schema_text: str):
    items = []

    for line in (schema_text or "").splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            continue

        label, input_type, correct_answer = parts
        items.append({
            "label": label,
            "input_type": input_type,
            "correct_answer": correct_answer,
        })

    return items

def parse_choice_schema(schema_text: str):
    choices = []

    for line in (schema_text or "").splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("|", 1)]
        if len(parts) != 2:
            continue

        key, label = parts
        choices.append({
            "key": key,
            "label": label,
        })

    return choices


def grade_multi_answer(*, submitted_answers: list[str], schema_text: str):
    schema_items = parse_answer_schema(schema_text)

    results = []
    all_correct = True
    has_error = False
    error_message = None

    for idx, item in enumerate(schema_items):
        submitted = submitted_answers[idx].strip() if idx < len(submitted_answers) else ""

        result = grade_answer(
            question_type="multi",
            answer_input_type=item["input_type"],
            submitted_answer=submitted,
            correct_answer=item["correct_answer"],
        )

        row = {
            "label": item["label"],
            "input_type": item["input_type"],
            "submitted_answer": submitted,
            "correct_answer": item["correct_answer"],
            "is_correct": result["is_correct"],
            "error": result["error"],
        }
        results.append(row)

        if result["error"] is not None:
            has_error = True
            if error_message is None:
                error_message = f"{item['label']}: {result['error']}"

        if not result["is_correct"]:
            all_correct = False

    return {
        "is_correct": all_correct and not has_error,
        "error": error_message,
        "results": results,
    }