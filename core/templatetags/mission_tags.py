import re
from django import template

register = template.Library()


BLOCK_LABELS = {
    "CONTEXT": "상황",
    "TABLE": "입력 데이터",
    "DATA": "입력 데이터",
    "RULES": "규칙",
    "TEXT": "입력값",
    "QUESTION": "질문",
}


@register.filter
def prompt_blocks(prompt):
    """
    [CONTEXT]...[/CONTEXT] 같은 구조화 프롬프트를
    템플릿에서 순서대로 출력하기 좋게 변환한다.
    """
    prompt = prompt or ""

    pattern = r"\[(CONTEXT|TABLE|DATA|RULES|TEXT|QUESTION)\](.*?)\[/\1\]"
    matches = re.findall(pattern, prompt, flags=re.DOTALL | re.IGNORECASE)

    blocks = []

    for block_type, content in matches:
        block_type = block_type.upper()
        content = content.strip()

        if not content:
            continue

        blocks.append({
            "type": block_type,
            "label": BLOCK_LABELS.get(block_type, block_type),
            "content": content,
        })

    if not blocks and prompt.strip():
        blocks.append({
            "type": "PLAIN",
            "label": "문제",
            "content": prompt.strip(),
        })

    return blocks

@register.filter
def prompt_question(prompt):
    """
    구조화 프롬프트에서 [QUESTION] 블록만 추출한다.
    없으면 원문 일부를 반환한다.
    """
    prompt = prompt or ""

    pattern = r"\[QUESTION\](.*?)\[/QUESTION\]"
    match = re.search(pattern, prompt, flags=re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()

    return prompt.strip()