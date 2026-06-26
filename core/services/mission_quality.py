import re
from collections import Counter, defaultdict

from core.models import Mission
from core.services.subjects import resolve_subject


REQUIRED_SECTIONS = ("[CONTEXT]", "[QUESTION]")
STRUCTURE_SECTIONS = ("[TABLE]", "[DATA]", "[RULES]")
PRACTICAL_EXTERNAL_ID_PREFIX = "PRACTICAL_"
BASIC_EXTERNAL_ID_PREFIXES = ("CNT_", "IF_CH_", "IF_ERR_", "IF_VAL_")
BASIC_TITLE_KEYWORDS = (
    "IF 결과 계산",
    "IF 함수 선택",
    "IF 오류 찾기",
    "COUNT 함수 선택",
    "COUNT 오류 찾기",
)
CONTEXTLESS_PATTERNS = (
    re.compile(r"값이\s*\d+\s*일\s*때"),
    re.compile(r"\b\d+\s*이면\s*100\b"),
    re.compile(r"아니면\s*0"),
)


def usable_missions(subject=None):
    qs = Mission.objects.filter(is_usable_for_set=True)
    if subject is not False:
        qs = qs.filter(subject=resolve_subject(subject))
    return qs


def normalize_numbers(text):
    text = re.sub(r"\d+", "{n}", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_quality_context(missions=None):
    missions = list(missions or Mission.objects.all())
    title_counts = Counter(m.title for m in missions if m.title)
    answer_counts = Counter(
        (m.correct_answer or "").strip()
        for m in missions
        if (m.correct_answer or "").strip() in {"0", "100"}
    )

    normalized_prompt_groups = defaultdict(list)
    for mission in missions:
        normalized_prompt_groups[normalize_numbers(mission.prompt)].append(mission.id)

    return {
        "title_counts": title_counts,
        "answer_counts": answer_counts,
        "normalized_prompt_groups": normalized_prompt_groups,
    }


def has_practical_structure(prompt):
    prompt = prompt or ""
    has_required_sections = all(section in prompt for section in REQUIRED_SECTIONS)
    has_context_structure = any(section in prompt for section in STRUCTURE_SECTIONS)
    return has_required_sections and has_context_structure


def get_quality_reasons(mission, context):
    reasons = []
    prompt = (mission.prompt or "").strip()
    title = (mission.title or "").strip()
    correct_answer = (mission.correct_answer or "").strip()
    explanation = (mission.explanation or "").strip()
    external_id = (mission.external_id or "").strip()

    title_counts = context["title_counts"]
    answer_counts = context["answer_counts"]
    normalized_prompt_groups = context["normalized_prompt_groups"]

    if len(prompt) < 30:
        reasons.append("prompt length < 30")

    if title and title_counts[title] >= 3:
        reasons.append(f"same title appears {title_counts[title]} times")

    normalized_prompt = normalize_numbers(prompt)
    normalized_group = normalized_prompt_groups.get(normalized_prompt, [])
    if normalized_prompt and len(normalized_group) >= 3:
        reasons.append(
            f"prompt differs mostly by numbers or repeats structure {len(normalized_group)} times"
        )

    if any(pattern.search(prompt) for pattern in CONTEXTLESS_PATTERNS):
        reasons.append("contextless simple calculation phrase")

    if correct_answer in {"0", "100"} and answer_counts[correct_answer] >= 3:
        reasons.append(
            f"correct_answer {correct_answer} repeats {answer_counts[correct_answer]} times"
        )

    if not has_practical_structure(prompt):
        reasons.append("missing [CONTEXT]/[TABLE or DATA or RULES]/[QUESTION] structure")

    if len(explanation) < 20:
        reasons.append("explanation missing or too short")

    if external_id.startswith(BASIC_EXTERNAL_ID_PREFIXES):
        reasons.append("legacy generated external_id prefix")

    if any(keyword in title for keyword in BASIC_TITLE_KEYWORDS):
        reasons.append("legacy repeated generated title")

    return reasons


def classify_mission_quality(mission, context):
    prompt = (mission.prompt or "").strip()
    explanation = (mission.explanation or "").strip()
    external_id = (mission.external_id or "").strip()
    reasons = get_quality_reasons(mission, context)

    if external_id.startswith(PRACTICAL_EXTERNAL_ID_PREFIX):
        return "practical", True, ["PRACTICAL_ external_id"]

    if (
        has_practical_structure(prompt)
        and len(prompt) >= 120
        and len(explanation) >= 20
    ):
        return "practical", True, ["scenario/practical structure"]

    basic_reason_markers = (
        "prompt length < 30",
        "prompt differs mostly by numbers",
        "contextless simple calculation phrase",
        "explanation missing or too short",
        "correct_answer 0 repeats",
        "correct_answer 100 repeats",
        "legacy generated external_id prefix",
        "legacy repeated generated title",
    )

    if any(
        any(reason.startswith(marker) for marker in basic_reason_markers)
        for reason in reasons
    ):
        return "basic", False, reasons

    return "standard", True, reasons or ["valid standard learning mission"]
