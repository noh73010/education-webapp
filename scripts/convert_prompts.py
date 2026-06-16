import csv
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


BLOCK_NAMES = ["CONTEXT", "RULES", "TABLE", "DATA", "TEXT", "QUESTION"]


def extract_block(prompt: str, block_name: str) -> str:
    pattern = rf"\[{block_name}\]\s*(.*?)\s*\[/{block_name}\]"
    match = re.search(pattern, prompt, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def normalize_line(line: str) -> str:
    return " ".join((line or "").strip().split())


def format_table_block(table_text: str) -> str:
    if not table_text:
        return ""

    lines = [normalize_line(line) for line in table_text.splitlines() if normalize_line(line)]
    if not lines:
        return ""

    formatted = ["[입력 데이터]"]
    formatted.extend(lines)
    return "\n".join(formatted)


def format_data_block(data_text: str) -> str:
    if not data_text:
        return ""

    lines = [normalize_line(line) for line in data_text.splitlines() if normalize_line(line)]
    if not lines:
        return ""

    formatted = ["[입력 데이터]"]
    for line in lines:
        formatted.append(line)
    return "\n".join(formatted)


def format_text_block(text_text: str) -> str:
    if not text_text:
        return ""

    lines = [normalize_line(line) for line in text_text.splitlines() if normalize_line(line)]
    if not lines:
        return ""

    formatted = ["[입력값]"]
    formatted.extend(lines)
    return "\n".join(formatted)


def format_rules_block(rules_text: str) -> str:
    if not rules_text:
        return ""

    raw_lines = [line.strip() for line in rules_text.splitlines() if line.strip()]
    if not raw_lines:
        return ""

    formatted = ["[규칙]"]
    for line in raw_lines:
        clean = normalize_line(line)
        if clean.startswith("-"):
            formatted.append(clean)
        else:
            formatted.append(f"- {clean}")
    return "\n".join(formatted)


def format_context_block(context_text: str) -> str:
    if not context_text:
        return "다음 조건을 기준으로 결과를 구하세요."

    lines = [normalize_line(line) for line in context_text.splitlines() if normalize_line(line)]
    return "\n".join(lines)


def format_question_block(question_text: str, answer_input_type: str) -> str:
    if question_text:
        lines = [normalize_line(line) for line in question_text.splitlines() if normalize_line(line)]
        question = " ".join(lines)
    else:
        if answer_input_type == "number":
            question = "결과 값을 입력하세요."
        elif answer_input_type == "date":
            question = "날짜 결과를 입력하세요."
        else:
            question = "결과를 입력하세요."

    # 문장 끝 통일
    question = question.replace("입력하시오.", "입력하세요.")
    question = question.replace("구하시오.", "구하세요.")
    question = question.replace("계산하시오.", "계산하세요.")
    question = question.replace("판정하시오.", "판정하세요.")

    question = question.lstrip("👉").strip()

    return question


def rebuild_prompt(title: str, prompt: str, answer_input_type: str) -> str:
    prompt = (prompt or "").strip()

    context_text = extract_block(prompt, "CONTEXT")
    rules_text = extract_block(prompt, "RULES")
    table_text = extract_block(prompt, "TABLE")
    data_text = extract_block(prompt, "DATA")
    text_text = extract_block(prompt, "TEXT")
    question_text = extract_block(prompt, "QUESTION")

    # 태그 구조가 아예 없는 경우는 그대로 반환
    has_structured_blocks = any([
        context_text,
        rules_text,
        table_text,
        data_text,
        text_text,
        question_text,
    ])
    if not has_structured_blocks:
        return prompt

    parts = []

    parts.append(f"{title}".strip())
    parts.append("")
    parts.append(format_context_block(context_text))

    rules_block = format_rules_block(rules_text)
    if rules_block:
        parts.append("")
        parts.append(rules_block)

    if table_text:
        parts.append("")
        parts.append(format_table_block(table_text))
    elif data_text:
        parts.append("")
        parts.append(format_data_block(data_text))
    elif text_text:
        parts.append("")
        parts.append(format_text_block(text_text))

    parts.append("")
    parts.append(format_question_block(question_text, answer_input_type))

    result = "\n".join(parts).strip()

    # 빈 줄 과다 정리
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def convert_csv(input_path: str, output_path: str) -> None:
    input_file = Path(input_path)
    output_file = Path(output_path)

    converted_count = 0
    untouched_count = 0

    with input_file.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError("CSV 헤더를 읽을 수 없습니다.")

        rows = list(reader)

    for row in rows:
        old_prompt = (row.get("prompt") or "").strip()
        title = (row.get("title") or "").strip()
        answer_input_type = (row.get("answer_input_type") or "").strip()

        new_prompt = rebuild_prompt(
            title=title,
            prompt=old_prompt,
            answer_input_type=answer_input_type,
        )

        if new_prompt != old_prompt:
            converted_count += 1
        else:
            untouched_count += 1

        row["prompt"] = new_prompt

    with output_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"변환 완료")
    print(f"- 입력 파일: {input_file}")
    print(f"- 출력 파일: {output_file}")
    print(f"- 변환됨: {converted_count}개")
    print(f"- 그대로 유지: {untouched_count}개")


if __name__ == "__main__":
    convert_csv(
        input_path=BASE_DIR / "missions_fixed.csv",
        output_path=BASE_DIR / "missions_fixed_pretty.csv",
    )