SKILL_CATEGORY = {
    "COUNT": "함수",
    "COUNTA": "함수",
    "IF": "함수",
    "VLOOKUP": "함수",
    "MAX": "함수",
    "MIN": "함수",
    "AVERAGE": "함수",
    "SUMIF": "함수",
    "SUMIFS": "함수",
    "COUNTIFS": "함수",
    "AVERAGEIF": "함수",

    "count": "함수",
    "counta": "함수",
    "if": "함수",
    "vlookup": "함수",
    "max": "함수",
    "min": "함수",
    "average": "함수",
    "sumif": "함수",
    "sumifs": "함수",
    "countifs": "함수",
    "averageif": "함수",

    "chart_axis": "차트",
    "chart_style": "차트",
    "chart_type": "차트",
    "chart_color": "차트",
    "chart_label": "차트",
    "chart_title": "차트",

    "pivot_basic": "피벗테이블",
    "pivot_average": "피벗테이블",

    "macro_basic": "매크로",
    "macro_sum": "매크로",
    "macro_average": "매크로",
    "macro_format": "매크로",

    "scenario": "시나리오",

    "advanced_filter_or": "고급필터",
    "advanced_filter_eval": "고급필터",
}


def get_skill_category(skill):
    if not skill:
        return "기타"

    skill = str(skill).strip()

    return SKILL_CATEGORY.get(
        skill,
        SKILL_CATEGORY.get(skill.lower(), "기타")
    )