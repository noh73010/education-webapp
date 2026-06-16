SKILL_LABELS = {
    "count": "COUNT",
    "counta": "COUNTA",
    "if": "IF",
    "sumif": "SUMIF",
    "sumifs": "SUMIFS",
    "vlookup": "VLOOKUP",
    "max": "MAX",
    "min": "MIN",
    "average": "AVERAGE",
    "averageif": "AVERAGEIF",
    "averageif_roundup": "AVERAGEIF + ROUNDUP",

    "advanced_filter_or": "고급필터 OR 조건",
    "basic_input": "기본 입력",
    "basic_memo": "메모 입력",

    "chart_axis": "차트 축 설정",
    "chart_label": "차트 레이블",
    "chart_series": "차트 계열",
    "chart_type": "차트 종류",

    "conditional_if": "조건 판단",
    "conditional_formula": "조건 수식",

    "custom_money_format": "천단위 통화 표시",
    "data_table": "데이터 표",

    "iferror_choose_mid": "IFERROR 오류 처리",

    "index_match_max": "INDEX/MATCH 최대값",

    "macro_average": "매크로 평균",
    "macro_format": "매크로 서식",
    "macro_sum": "매크로 합계",

    "proper": "영문 대소문자 변환",

    "right_if": "RIGHT + IF",

    "text_concat": "문자열 결합",
    "text_split": "문자열 분리",

    "vlookup_band": "VLOOKUP 구간 조회",

    "workday": "WORKDAY 날짜 계산",
    "hour_minute": "시각 계산",

    "cell_align": "셀 정렬",
    "cell_format": "셀 서식",
    "rank_eq": "동순위 처리",
    "large_if": "LARGE 조건 계산",
}


def get_skill_label(skill):
    if not skill:
        return ""

    skill = str(skill).strip()

    return SKILL_LABELS.get(
        skill,
        SKILL_LABELS.get(skill.lower(), skill)
    )