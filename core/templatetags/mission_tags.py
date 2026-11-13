import re
from django import template
from django.utils.html import strip_tags

register = template.Library()


@register.filter
def readable_figure(static_path):
    from core.services.question_visuals import question_visual
    return question_visual(static_path)


@register.filter
def prompt_blocks(prompt):
    from core.services.question_layout import question_blocks
    return question_blocks(prompt)

@register.filter
def prompt_question(prompt):
    """
    구조화 프롬프트에서 [QUESTION] 블록만 추출한다.
    없으면 원문 일부를 반환한다.
    """
    prompt = prompt or ""

    pattern = r"\[QUESTION\](.*?)(?:\[/QUESTION\]|$)"
    match = re.search(pattern, prompt, flags=re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()

    return prompt.strip()


@register.filter
def question_excerpt(prompt, limit=60):
    """Return a compact learner-facing question title from a Mission prompt."""
    try:
        limit = max(20, int(limit))
    except (TypeError, ValueError):
        limit = 60

    question = strip_tags(prompt_question(prompt))
    question = re.sub(
        r"\[/?(?:CONTEXT|TABLE|DATA|RULES|TEXT|QUESTION)\]",
        " ",
        question,
        flags=re.IGNORECASE,
    )
    question = re.sub(r"\s+", " ", question).strip()

    if len(question) <= limit:
        return question

    return f"{question[:limit].rstrip()}..."
