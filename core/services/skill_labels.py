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

LOGISTICS_SKILL_LABELS = {
    "LM01": "물류관리 일반",
    "LM02": "물류시스템 구축",
    "LM03": "SCM과 녹색물류",
    "LM04": "국제물류",
    "TR01": "화물운송의 기초이론",
    "TR02": "화물자동차운송",
    "TR03": "수·배송시스템의 합리화",
    "TR04": "철도운송",
    "TR05": "항공운송",
    "TR06": "해상운송",
    "TR07": "국제복합운송",
    "TR08": "택배·생활물류",
    "IL01": "국제물류관리",
    "IL02": "무역실무",
    "IL03": "해상운송",
    "IL04": "해상보험",
    "IL05": "항공운송",
    "IL06": "컨테이너 운송",
    "IL07": "복합운송",
    "WH01": "보관론",
    "WH02": "하역론",
    "LW01": "물류정책기본법",
    "LW02": "물류시설법",
    "LW03": "유통산업발전법",
    "LW04": "화물자동차 운수사업법",
    "LW05": "철도사업법",
    "LW06": "항만운송사업법",
    "LW07": "농수산물 유통법",
}


def get_skill_label(skill):
    if not skill:
        return ""

    skill = str(skill).strip()

    return SKILL_LABELS.get(
        skill,
        SKILL_LABELS.get(
            skill.lower(),
            LOGISTICS_SKILL_LABELS.get(skill.upper(), skill),
        ),
    )
