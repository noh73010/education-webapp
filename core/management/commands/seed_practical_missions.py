from django.core.management.base import BaseCommand

from core.models import Mission


MISSIONS = [
    {
        "external_id": "PRACTICAL_COUNT_FEATURE_001",
        "title": "출석표 결석 횟수 함수 선택",
        "skill": "COUNT",
        "learning_type": "feature",
        "question_type": "choice_one",
        "answer_input_type": "none",
        "level": 2,
        "prompt": """[CONTEXT]
학원 출석표에서 B2:B31에는 출석 상태가 입력되어 있다. 값은 출석, 지각, 결석 중 하나다.

[DATA]
B열: 출석 상태

[QUESTION]
결석이라고 입력된 학생 수만 세려면 어떤 함수가 가장 적절한가?""",
        "answer_schema": "A|COUNT\nB|COUNTA\nC|COUNTIF\nD|AVERAGE",
        "correct_answer": "C",
        "explanation": "특정 조건인 '결석'과 일치하는 셀 수를 세야 하므로 COUNTIF가 적절합니다.",
        "wrong_pattern_code": "COUNTIF_CONDITION",
        "variation_group": "practical_count_attendance",
    },
    {
        "external_id": "PRACTICAL_COUNT_RESULT_001",
        "title": "주문번호 입력 건수 계산",
        "skill": "COUNTA",
        "learning_type": "result",
        "question_type": "value_answer",
        "answer_input_type": "number",
        "level": 2,
        "prompt": """[CONTEXT]
온라인 주문 목록에서 주문번호가 입력된 행만 실제 주문으로 본다.

[DATA]
A2:A8 주문번호
A2=O-1001
A3=O-1002
A4=
A5=O-1004
A6=취소
A7=
A8=O-1007

[QUESTION]
=COUNTA(A2:A8)의 결과는 얼마인가?""",
        "answer_schema": "",
        "correct_answer": "5",
        "explanation": "COUNTA는 비어 있지 않은 셀을 모두 세므로 O-1001, O-1002, O-1004, 취소, O-1007까지 총 5개입니다.",
        "wrong_pattern_code": "COUNT_COUNTA_CONFUSION",
        "variation_group": "practical_counta_orders",
    },
    {
        "external_id": "PRACTICAL_COUNT_ERROR_001",
        "title": "COUNT와 COUNTA 오류 진단",
        "skill": "COUNT",
        "learning_type": "error",
        "question_type": "error_detect",
        "answer_input_type": "none",
        "level": 2,
        "prompt": """[CONTEXT]
담당자는 주문번호가 입력된 주문 건수를 세려고 한다. 주문번호는 O-1001 같은 문자 코드다.

[DATA]
A2:A50 주문번호

[QUESTION]
=COUNT(A2:A50)을 사용했더니 결과가 0에 가깝게 나온다. 가장 알맞은 오류 원인은?""",
        "answer_schema": "A|COUNT는 문자 코드가 입력된 셀을 세지 못한다\nB|COUNT는 빈칸만 센다\nC|COUNT는 조건이 반드시 필요하다\nD|COUNT는 날짜 데이터만 센다",
        "correct_answer": "A",
        "explanation": "주문번호가 문자 코드라면 COUNT가 아니라 COUNTA로 비어 있지 않은 셀을 세야 합니다.",
        "wrong_pattern_code": "COUNT_TEXT_RANGE",
        "variation_group": "practical_count_error_text_code",
    },
    {
        "external_id": "PRACTICAL_IF_FEATURE_001",
        "title": "합격 불합격 표시 함수 선택",
        "skill": "IF",
        "learning_type": "feature",
        "question_type": "choice_one",
        "answer_input_type": "none",
        "level": 2,
        "prompt": """[CONTEXT]
자격증 모의고사 점수표에서 점수가 60점 이상이면 합격, 아니면 불합격을 표시해야 한다.

[DATA]
C열: 점수
D열: 판정 결과

[QUESTION]
D2에 입력할 판정 함수로 가장 적절한 것은?""",
        "answer_schema": "A|SUM\nB|IF\nC|COUNT\nD|VLOOKUP",
        "correct_answer": "B",
        "explanation": "점수 조건에 따라 서로 다른 텍스트를 반환해야 하므로 IF 함수가 적절합니다.",
        "wrong_pattern_code": "IF_FUNCTION_SELECT",
        "variation_group": "practical_if_pass_fail",
    },
    {
        "external_id": "PRACTICAL_IF_RESULT_001",
        "title": "배송비 면제 여부 결과 예측",
        "skill": "IF",
        "learning_type": "result",
        "question_type": "short_answer",
        "answer_input_type": "text",
        "level": 2,
        "prompt": """[CONTEXT]
쇼핑몰 주문표에서 주문금액이 50000원 이상이면 배송비를 무료로 표시한다.

[DATA]
B2 주문금액 = 65000

[RULES]
C2 수식 =IF(B2>=50000,"무료","3000원")

[QUESTION]
C2에 표시되는 결과는 무엇인가?""",
        "answer_schema": "",
        "correct_answer": "무료",
        "explanation": "65000은 50000 이상이므로 IF의 참 값인 '무료'가 표시됩니다.",
        "wrong_pattern_code": "IF_RESULT_BRANCH",
        "variation_group": "practical_if_shipping",
    },
    {
        "external_id": "PRACTICAL_IF_ERROR_001",
        "title": "IF 거짓값 누락 오류 진단",
        "skill": "IF",
        "learning_type": "error",
        "question_type": "error_detect",
        "answer_input_type": "none",
        "level": 2,
        "prompt": """[CONTEXT]
성적표에서 60점 이상이면 합격, 아니면 불합격을 표시하려고 한다.

[DATA]
C2 점수 = 55

[QUESTION]
=IF(C2>=60,"합격") 수식의 가장 큰 문제점은?""",
        "answer_schema": "A|거짓일 때 표시할 값이 없다\nB|IF는 숫자 비교를 할 수 없다\nC|합격에는 따옴표를 쓰면 안 된다\nD|C2는 수식에서 참조할 수 없다",
        "correct_answer": "A",
        "explanation": "합격이 아닌 경우 표시할 '불합격' 값이 빠져 있어 조건이 거짓일 때 원하는 결과를 만들 수 없습니다.",
        "wrong_pattern_code": "IF_MISSING_FALSE",
        "variation_group": "practical_if_error_missing_false",
    },
    {
        "external_id": "PRACTICAL_VLOOKUP_FEATURE_001",
        "title": "상품코드 단가 조회 함수 선택",
        "skill": "VLOOKUP",
        "learning_type": "feature",
        "question_type": "choice_one",
        "answer_input_type": "none",
        "level": 2,
        "prompt": """[CONTEXT]
주문서의 상품코드를 기준으로 상품표에서 단가를 가져오려고 한다.

[DATA]
주문서 B열: 상품코드
상품표 F:H = 상품코드, 상품명, 단가

[QUESTION]
상품코드로 단가를 조회할 때 가장 적절한 함수는?""",
        "answer_schema": "A|COUNTIF\nB|IF\nC|VLOOKUP\nD|COUNTA",
        "correct_answer": "C",
        "explanation": "상품코드가 상품표의 첫 열에 있고 오른쪽 열의 단가를 가져와야 하므로 VLOOKUP이 적절합니다.",
        "wrong_pattern_code": "VLOOKUP_FUNCTION_SELECT",
        "variation_group": "practical_vlookup_price",
    },
    {
        "external_id": "PRACTICAL_VLOOKUP_RESULT_001",
        "title": "상품코드 단가 조회 결과",
        "skill": "VLOOKUP",
        "learning_type": "result",
        "question_type": "value_answer",
        "answer_input_type": "number",
        "level": 3,
        "prompt": """[CONTEXT]
주문서에서 상품코드 P-200의 단가를 상품표에서 조회한다.

[TABLE]
F2:H5 상품표
P-100 | 마우스 | 12000
P-200 | 키보드 | 25000
P-300 | 모니터 | 180000
P-400 | 케이블 | 5000

[RULES]
=VLOOKUP("P-200",F2:H5,3,FALSE)

[QUESTION]
수식의 결과는 얼마인가?""",
        "answer_schema": "",
        "correct_answer": "25000",
        "explanation": "P-200이 있는 행에서 범위의 세 번째 열인 단가 25000을 반환합니다.",
        "wrong_pattern_code": "VLOOKUP_COL_INDEX",
        "variation_group": "practical_vlookup_result_price",
    },
    {
        "external_id": "PRACTICAL_VLOOKUP_ERROR_001",
        "title": "VLOOKUP 열 번호 오류 진단",
        "skill": "VLOOKUP",
        "learning_type": "error",
        "question_type": "error_detect",
        "answer_input_type": "none",
        "level": 3,
        "prompt": """[CONTEXT]
상품코드로 단가를 가져와야 하는데 상품명이 반환되고 있다.

[TABLE]
F:H = 상품코드, 상품명, 단가

[QUESTION]
=VLOOKUP(B2,F:H,2,FALSE)를 사용했을 때 단가 대신 상품명이 나오는 가장 직접적인 이유는?""",
        "answer_schema": "A|열 번호가 상품명 열인 2로 지정되어 있다\nB|FALSE를 써서 정확히 일치한다\nC|상품코드는 첫 열에 있어야 한다\nD|범위에 H열이 포함되어 있다",
        "correct_answer": "A",
        "explanation": "F:H 범위에서 2번째 열은 상품명이고 단가는 3번째 열이므로 열 번호를 3으로 지정해야 합니다.",
        "wrong_pattern_code": "VLOOKUP_WRONG_COL_INDEX",
        "variation_group": "practical_vlookup_error_col_index",
    },
    {
        "external_id": "PRACTICAL_VLOOKUP_ERROR_002",
        "title": "VLOOKUP 첫 열 조건 오류 진단",
        "skill": "VLOOKUP",
        "learning_type": "error",
        "question_type": "error_detect",
        "answer_input_type": "none",
        "level": 3,
        "prompt": """[CONTEXT]
상품코드로 단가를 조회하려고 하지만 계속 #N/A가 발생한다.

[TABLE]
F:H = 상품명, 상품코드, 단가

[QUESTION]
=VLOOKUP(B2,F:H,3,FALSE)에서 가장 중요한 구조적 문제는?""",
        "answer_schema": "A|조회하려는 상품코드가 범위의 첫 번째 열에 있지 않다\nB|열 번호 3은 사용할 수 없다\nC|FALSE는 근사값 검색이다\nD|VLOOKUP은 텍스트를 조회할 수 없다",
        "correct_answer": "A",
        "explanation": "VLOOKUP은 조회값을 지정 범위의 첫 번째 열에서 찾습니다. 상품코드가 두 번째 열이면 범위를 상품코드 열부터 잡아야 합니다.",
        "wrong_pattern_code": "VLOOKUP_LOOKUP_COL_NOT_FIRST",
        "variation_group": "practical_vlookup_error_first_col",
    },
    {
        "external_id": "PRACTICAL_COUNTA_FEATURE_001",
        "title": "비어 있지 않은 주문번호 함수 선택",
        "skill": "COUNTA",
        "learning_type": "feature",
        "question_type": "choice_one",
        "answer_input_type": "none",
        "level": 2,
        "prompt": """[CONTEXT]
주문 관리표에서 주문번호가 입력된 행을 실제 접수된 주문으로 본다. 주문번호는 문자와 숫자가 섞인 코드다.

[DATA]
A열: 주문번호

[QUESTION]
빈칸을 제외하고 주문번호가 입력된 셀 수를 세려면 어떤 함수가 가장 적절한가?""",
        "answer_schema": "A|COUNT\nB|COUNTA\nC|AVERAGE\nD|VLOOKUP",
        "correct_answer": "B",
        "explanation": "주문번호는 문자 코드일 수 있으므로 숫자만 세는 COUNT가 아니라 비어 있지 않은 셀을 세는 COUNTA가 적절합니다.",
        "wrong_pattern_code": "COUNT_COUNTA_CONFUSION",
        "variation_group": "practical_counta_feature_orders",
    },
    {
        "external_id": "PRACTICAL_COUNT_RESULT_002",
        "title": "숫자 점수 입력 개수 계산",
        "skill": "COUNT",
        "learning_type": "result",
        "question_type": "value_answer",
        "answer_input_type": "number",
        "level": 2,
        "prompt": """[CONTEXT]
채점표에서 실제 숫자 점수가 입력된 학생 수만 세려고 한다.

[DATA]
C2:C8 점수
C2=80
C3=결시
C4=95
C5=
C6=70
C7=보류
C8=60

[QUESTION]
=COUNT(C2:C8)의 결과는 얼마인가?""",
        "answer_schema": "",
        "correct_answer": "4",
        "explanation": "COUNT는 숫자만 세므로 80, 95, 70, 60 네 개만 계산합니다.",
        "wrong_pattern_code": "COUNT_TEXT_IGNORED",
        "variation_group": "practical_count_scores",
    },
]


class Command(BaseCommand):
    help = "Seed practical COUNT, COUNTA, IF, and VLOOKUP missions"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for mission_data in MISSIONS:
            external_id = mission_data["external_id"]
            defaults = {
                **mission_data,
                "quality_level": "practical",
                "is_quality_checked": True,
                "is_usable_for_set": True,
                "answer_key": mission_data["correct_answer"],
            }
            defaults.pop("external_id")

            _, created = Mission.objects.update_or_create(
                external_id=external_id,
                defaults=defaults,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Practical missions seeded. created={created_count} updated={updated_count}"
            )
        )
