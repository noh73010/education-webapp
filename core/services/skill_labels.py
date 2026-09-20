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
    "LM01": "물류관리총론", "LM02": "물류경영",
    "LM03": "물류표준화와 물류공동화", "LM04": "물류정보화(정보시스템)",
    "LM05": "물류비 회계", "LM06": "공급사슬관리(SCM)",
    "LM07": "친환경 녹색물류와 물류포장", "LM08": "물류아웃소싱과 물류보안",
    "FT01": "화물운송의 기초", "FT02": "공로운송", "FT03": "철도운송",
    "FT04": "해상운송", "FT05": "항공운송", "FT06": "국제복합운송",
    "FT07": "유닛로드시스템(ULS)", "FT08": "수·배송시스템의 합리화",
    "IT01": "국제물류 총론", "IT02": "국제해상운송",
    "IT03": "국제항공운송", "IT04": "국제복합운송 및 국제물류보안",
    "BH01": "보관 및 창고의 기초개념", "BH02": "물류시설과 창고관리시스템",
    "BH03": "물류시설의 계획 및 운영", "BH04": "재고관리시스템",
    "BH05": "하역의 이해", "BH06": "하역운반장비",
    "BH07": "유닛로드시스템과 포장", "BH08": "운송수단별 하역방식",
    "LR01": "물류정책기본법", "LR02": "물류시설의 개발 및 운영에 관한 법률",
    "LR03": "화물자동차 운수사업법", "LR04": "철도사업법",
    "LR05": "항만운송사업법", "LR06": "유통산업발전법",
    "LR07": "농수산물 유통 및 가격안정에 관한 법률",
    # 과거 데이터 입력 호환용 별칭. 화면에서는 코드 대신 한국어 이름만 보여준다.
    "TR01": "화물운송의 기초", "TR02": "공로운송", "TR03": "수·배송시스템의 합리화",
    "TR04": "철도운송", "TR05": "항공운송", "TR06": "해상운송",
    "TR07": "국제복합운송", "TR08": "택배·생활물류",
    "IL01": "국제물류 총론", "IL02": "국제해상운송", "IL03": "국제항공운송",
    "IL04": "국제복합운송 및 국제물류보안",
    "WH01": "보관 및 창고의 기초개념", "WH02": "하역의 이해",
    "LW01": "물류정책기본법", "LW02": "물류시설의 개발 및 운영에 관한 법률",
    "LW03": "유통산업발전법", "LW04": "화물자동차 운수사업법",
    "LW05": "철도사업법", "LW06": "항만운송사업법",
    "LW07": "농수산물 유통 및 가격안정에 관한 법률",
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
