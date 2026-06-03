import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "generated" / "missions_scenario.csv"


def save_csv(rows, filename=OUTPUT_FILE):
    fieldnames = [
        "id",
        "title",
        "skill_auto",
        "level",
        "prompt",
        "question_type",
        "answer_input_type",
        "correct_answer",
        "answer_schema",
        "explanation",
        "wrong_pattern_code",
        "variation_group",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_prompt(*, title, context, table, rules, question):
    return f"""[CONTEXT]
{context}
[/CONTEXT]

[TABLE]
{table}
[/TABLE]

[RULES]
{rules}
[/RULES]

[QUESTION]
{question}
[/QUESTION]"""


def make_choice_schema(choices):
    return "\n".join(f"{key}|{text}" for key, text in choices)


def generate_counta_scenarios():
    rows = []

    rows.append({
        "id": "SCN_COUNTA_001",
        "title": "비어있지 않은 주문번호 개수 계산",
        "skill_auto": "COUNTA",
        "level": 1,
        "prompt": build_prompt(
            title="비어있지 않은 주문번호 개수 계산",
            context="쇼핑몰 주문 관리표입니다. 주문번호가 입력된 행만 실제 주문으로 봅니다.",
            table="""행 | 주문번호 | 고객명 | 결제상태
1 | A-1001 | 김민수 | 결제완료
2 | A-1002 | 이지은 | 결제완료
3 |        | 박도윤 | 취소
4 | A-1003 | 최서연 | 결제대기
5 |        | 한지호 | 취소""",
            rules="""- 주문번호가 비어 있으면 실제 주문 건수에서 제외합니다.
- 주문번호가 입력된 행만 셉니다.""",
            question="실제 주문 건수는 몇 건인가요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "3",
        "answer_schema": "",
        "explanation": "주문번호가 있는 행은 A-1001, A-1002, A-1003 총 3건입니다. Excel에서는 COUNTA로 비어있지 않은 셀 개수를 셀 수 있습니다.",
        "wrong_pattern_code": "",
        "variation_group": "",
    })

    rows.append({
        "id": "SCN_COUNTA_002",
        "title": "COUNTA 함수 선택",
        "skill_auto": "COUNTA",
        "level": 1,
        "prompt": build_prompt(
            title="COUNTA 함수 선택",
            context="출석부에서 이름이 입력된 학생 수를 세려고 합니다.",
            table="""번호 | 이름 | 출석여부
1 | 김민수 | 출석
2 | 이지은 | 출석
3 |       | 결석
4 | 최서연 | 출석""",
            rules="""- 이름이 입력된 셀만 셉니다.
- 빈 셀은 제외합니다.""",
            question="이 상황에서 가장 적절한 함수는 무엇인가요?",
        ),
        "question_type": "choice_one",
        "answer_input_type": "text",
        "correct_answer": "B",
        "answer_schema": make_choice_schema([
            ("A", "=COUNT(B2:B5)"),
            ("B", "=COUNTA(B2:B5)"),
            ("C", "=SUM(B2:B5)"),
            ("D", "=AVERAGE(B2:B5)"),
        ]),
        "explanation": "COUNT는 숫자만 세고, COUNTA는 비어있지 않은 셀을 셉니다.",
        "wrong_pattern_code": "",
        "variation_group": "",
    })

    rows.append({
        "id": "SCN_COUNTA_003",
        "title": "COUNT 사용 오류 찾기",
        "skill_auto": "COUNTA",
        "level": 1,
        "prompt": build_prompt(
            title="COUNT 사용 오류 찾기",
            context="담당자가 고객명이 입력된 행의 개수를 세려고 합니다.",
            table="""행 | 고객명
1 | 김민수
2 | 이지은
3 |
4 | 최서연""",
            rules="""- 고객명은 문자 데이터입니다.
- 빈 셀은 제외해야 합니다.""",
            question="=COUNT(B1:B4)를 사용했을 때 생기는 문제는 무엇인가요?",
        ),
        "question_type": "error_detect",
        "answer_input_type": "text",
        "correct_answer": "B",
        "answer_schema": make_choice_schema([
            ("A", "범위가 너무 짧다"),
            ("B", "문자 데이터는 COUNT로 세지 못한다"),
            ("C", "SUM 함수를 써야 한다"),
            ("D", "항상 4가 나온다"),
        ]),
        "explanation": "COUNT는 숫자 데이터만 셉니다. 고객명처럼 문자 데이터 개수를 세려면 COUNTA가 적절합니다.",
        "wrong_pattern_code": "COUNT_CONFUSION",
        "variation_group": "COUNT_CONFUSION",
    })

    return rows


def generate_if_scenarios():
    rows = []

    rows.append({
        "id": "SCN_IF_001",
        "title": "합격 여부 판단",
        "skill_auto": "IF",
        "level": 1,
        "prompt": build_prompt(
            title="합격 여부 판단",
            context="자격시험 결과표입니다. 점수가 60점 이상이면 합격, 아니면 불합격입니다.",
            table="""이름 | 점수
김민수 | 75
이지은 | 58
최서연 | 60""",
            rules="""- 60점 이상이면 합격입니다.
- 60점 미만이면 불합격입니다.""",
            question="이지은의 판정 결과를 입력하세요.",
        ),
        "question_type": "value_answer",
        "answer_input_type": "text",
        "correct_answer": "불합격",
        "answer_schema": "",
        "explanation": "이지은의 점수는 58점입니다. 60점 미만이므로 불합격입니다.",
        "wrong_pattern_code": "",
        "variation_group": "",
    })

    rows.append({
        "id": "SCN_IF_002",
        "title": "IF 함수 수식 선택",
        "skill_auto": "IF",
        "level": 1,
        "prompt": build_prompt(
            title="IF 함수 수식 선택",
            context="B2 셀의 점수가 60점 이상이면 합격, 아니면 불합격을 표시하려고 합니다.",
            table="""셀 | 값
B2 | 75""",
            rules="""- 조건은 B2>=60 입니다.
- 참이면 합격입니다.
- 거짓이면 불합격입니다.""",
            question="올바른 수식은 무엇인가요?",
        ),
        "question_type": "choice_one",
        "answer_input_type": "text",
        "correct_answer": "A",
        "answer_schema": make_choice_schema([
            ("A", '=IF(B2>=60,"합격","불합격")'),
            ("B", '=IF(B2<60,"합격","불합격")'),
            ("C", '=SUM(B2>=60,"합격","불합격")'),
            ("D", '=COUNT(B2>=60)'),
        ]),
        "explanation": "60점 이상이면 합격이므로 조건식은 B2>=60이어야 합니다.",
        "wrong_pattern_code": "IF_DIRECTION",
        "variation_group": "IF_DIRECTION",
    })

    rows.append({
        "id": "SCN_IF_003",
        "title": "IF 수식 오류 찾기",
        "skill_auto": "IF",
        "level": 2,
        "prompt": build_prompt(
            title="IF 수식 오류 찾기",
            context="점수에 따라 합격/불합격을 표시하려고 합니다.",
            table="""셀 | 값
B2 | 45""",
            rules="""- 60점 이상이면 합격입니다.
- 60점 미만이면 불합격입니다.""",
            question='=IF(B2>=60,"합격") 수식의 문제점은 무엇인가요?',
        ),
        "question_type": "error_detect",
        "answer_input_type": "text",
        "correct_answer": "C",
        "answer_schema": make_choice_schema([
            ("A", "조건식이 없다"),
            ("B", "참일 때 값이 없다"),
            ("C", "거짓일 때 값이 없다"),
            ("D", "B2 셀은 사용할 수 없다"),
        ]),
        "explanation": "IF 함수는 조건, 참일 때 값, 거짓일 때 값의 구조가 필요합니다.",
        "wrong_pattern_code": "IF_MISSING_FALSE",
        "variation_group": "IF_MISSING_FALSE",
    })

    return rows


def generate_sumif_scenarios():
    rows = []

    rows.append({
        "id": "SCN_SUMIF_001",
        "title": "부서별 매출 합계 계산",
        "skill_auto": "SUMIF",
        "level": 2,
        "prompt": build_prompt(
            title="부서별 매출 합계 계산",
            context="부서별 매출 데이터입니다. 영업팀의 매출 합계를 구해야 합니다.",
            table="""부서 | 매출
영업 | 120000
관리 | 80000
영업 | 150000
개발 | 200000
영업 | 100000""",
            rules="""- 부서가 영업인 행만 합산합니다.
- 관리, 개발 부서는 제외합니다.""",
            question="영업팀의 총 매출은 얼마인가요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "370000",
        "answer_schema": "",
        "explanation": "영업팀 매출은 120000 + 150000 + 100000 = 370000입니다.",
        "wrong_pattern_code": "",
        "variation_group": "",
    })

    rows.append({
        "id": "SCN_SUMIF_002",
        "title": "SUMIF 수식 선택",
        "skill_auto": "SUMIF",
        "level": 2,
        "prompt": build_prompt(
            title="SUMIF 수식 선택",
            context="A열에는 부서명, B열에는 매출이 있습니다. 영업팀 매출만 합산하려고 합니다.",
            table="""A열 | B열
영업 | 120000
관리 | 80000
영업 | 150000
개발 | 200000""",
            rules="""- 조건 범위는 A열입니다.
- 합계 범위는 B열입니다.
- 조건은 영업입니다.""",
            question="올바른 수식은 무엇인가요?",
        ),
        "question_type": "choice_one",
        "answer_input_type": "text",
        "correct_answer": "A",
        "answer_schema": make_choice_schema([
            ("A", '=SUMIF(A1:A4,"영업",B1:B4)'),
            ("B", '=SUMIF(B1:B4,"영업",A1:A4)'),
            ("C", '=COUNTIF(A1:A4,"영업",B1:B4)'),
            ("D", '=SUM(A1:A4,"영업",B1:B4)'),
        ]),
        "explanation": "SUMIF는 조건범위, 조건, 합계범위 순서입니다.",
        "wrong_pattern_code": "",
        "variation_group": "",
    })

    return rows


def generate_vlookup_scenarios():
    rows = []

    rows.append({
        "id": "SCN_VLOOKUP_001",
        "title": "상품코드로 단가 찾기",
        "skill_auto": "VLOOKUP",
        "level": 2,
        "prompt": build_prompt(
            title="상품코드로 단가 찾기",
            context="상품코드를 기준으로 상품표에서 단가를 찾아야 합니다.",
            table="""상품코드 | 상품명 | 단가
A001 | 키보드 | 30000
A002 | 마우스 | 15000
A003 | 모니터 | 180000

찾을 상품코드: A002""",
            rules="""- 상품코드는 첫 번째 열에서 찾습니다.
- 단가는 세 번째 열에 있습니다.
- 정확히 일치하는 상품코드를 찾아야 합니다.""",
            question="A002의 단가는 얼마인가요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "15000",
        "answer_schema": "",
        "explanation": "A002는 마우스이고 단가는 15000입니다.",
        "wrong_pattern_code": "",
        "variation_group": "",
    })

    rows.append({
        "id": "SCN_VLOOKUP_002",
        "title": "상품코드로 단가 조회",
        "skill_auto": "VLOOKUP",
        "level": 2,
        "prompt": build_prompt(
            title="상품코드로 단가 조회",
            context="상품코드를 기준으로 단가를 찾으려고 합니다.",
            table="""1열: 상품코드
2열: 상품명
3열: 단가
4열: 재고""",
            rules="""- 찾을 값은 상품코드입니다.
- 반환할 값은 단가입니다.""",
            question="단가를 가져오려면 열 번호를 몇으로 지정해야 하나요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "3",
        "answer_schema": "",
        "explanation": "단가는 범위의 세 번째 열에 있으므로 열 번호는 3입니다.",
        "wrong_pattern_code": "VLOOKUP_COL_INDEX",
        "variation_group": "VLOOKUP_COL_INDEX",
    })

    rows.append({
        "id": "SCN_VLOOKUP_004",
        "title": "상품코드로 재고 조회",
        "skill_auto": "VLOOKUP",
        "level": 2,
        "prompt": build_prompt(
            title="상품코드로 재고 조회",
            context="상품코드를 기준으로 상품표에서 재고 수량을 찾으려고 합니다.",
            table="""1열: 상품코드
2열: 상품명
3열: 단가
4열: 재고""",
            rules="""- 찾을 값은 상품코드입니다.
- 반환할 값은 재고입니다.""",
            question="재고를 가져오려면 열 번호를 몇으로 지정해야 하나요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "4",
        "answer_schema": "",
        "explanation": "재고는 범위의 네 번째 열에 있으므로 열 번호는 4입니다.",
        "wrong_pattern_code": "VLOOKUP_COL_INDEX",
        "variation_group": "VLOOKUP_COL_INDEX",
    })

    rows.append({
        "id": "SCN_VLOOKUP_005",
        "title": "상품코드로 할인율 조회",
        "skill_auto": "VLOOKUP",
        "level": 2,
        "prompt": build_prompt(
            title="상품코드로 할인율 조회",
            context="상품코드를 기준으로 할인율을 찾으려고 합니다.",
            table="""1열: 상품코드
2열: 상품명
3열: 단가
4열: 재고
5열: 할인율""",
            rules="""- 찾을 값은 상품코드입니다.
- 반환할 값은 할인율입니다.""",
            question="할인율을 가져오려면 열 번호를 몇으로 지정해야 하나요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "5",
        "answer_schema": "",
        "explanation": "할인율은 범위의 다섯 번째 열에 있으므로 열 번호는 5입니다.",
        "wrong_pattern_code": "VLOOKUP_COL_INDEX",
        "variation_group": "VLOOKUP_COL_INDEX",
    })

    rows.append({
        "id": "SCN_VLOOKUP_006",
        "title": "거래처코드로 담당자 조회",
        "skill_auto": "VLOOKUP",
        "level": 2,
        "prompt": build_prompt(
            title="거래처코드로 담당자 조회",
            context="거래처코드를 기준으로 담당자를 찾으려고 합니다.",
            table="""1열: 거래처코드
2열: 거래처명
3열: 지역
4열: 담당자""",
            rules="""- 찾을 값은 거래처코드입니다.
- 반환할 값은 담당자입니다.""",
            question="담당자를 가져오려면 열 번호를 몇으로 지정해야 하나요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "4",
        "answer_schema": "",
        "explanation": "담당자는 범위의 네 번째 열에 있으므로 열 번호는 4입니다.",
        "wrong_pattern_code": "VLOOKUP_COL_INDEX",
        "variation_group": "VLOOKUP_COL_INDEX",
    })

    rows.append({
        "id": "SCN_VLOOKUP_007",
        "title": "상품코드로 제조사 조회",
        "skill_auto": "VLOOKUP",
        "level": 2,
        "prompt": build_prompt(
            title="상품코드로 제조사 조회",
            context="상품코드를 기준으로 제조사를 찾으려고 합니다.",
            table="""1열: 상품코드
2열: 상품명
3열: 제조사
4열: 단가""",
            rules="""- 찾을 값은 상품코드입니다.
- 반환할 값은 제조사입니다.""",
            question="제조사를 가져오려면 열 번호를 몇으로 지정해야 하나요?",
        ),
        "question_type": "value_answer",
        "answer_input_type": "number",
        "correct_answer": "3",
        "answer_schema": "",
        "explanation": "제조사는 범위의 세 번째 열에 있으므로 열 번호는 3입니다.",
        "wrong_pattern_code": "VLOOKUP_COL_INDEX",
        "variation_group": "VLOOKUP_COL_INDEX",
    })

    rows.append({
        "id": "SCN_VLOOKUP_003",
        "title": "VLOOKUP 오류 찾기",
        "skill_auto": "VLOOKUP",
        "level": 3,
        "prompt": build_prompt(
            title="VLOOKUP 오류 찾기",
            context="상품명을 기준으로 단가를 찾으려고 다음 수식을 작성했습니다.",
            table="""A열 | B열 | C열
상품코드 | 상품명 | 단가
A001 | 키보드 | 30000
A002 | 마우스 | 15000""",
            rules="""- VLOOKUP은 찾을 값이 범위의 첫 번째 열에 있어야 합니다.
- 현재 찾으려는 값은 상품명입니다.""",
            question='=VLOOKUP("마우스",A2:C3,3,FALSE)의 문제점은 무엇인가요?',
        ),
        "question_type": "error_detect",
        "answer_input_type": "text",
        "correct_answer": "B",
        "answer_schema": make_choice_schema([
            ("A", "FALSE를 쓰면 안 된다"),
            ("B", "찾을 값인 상품명이 범위의 첫 번째 열에 있지 않다"),
            ("C", "열 번호는 항상 1이어야 한다"),
            ("D", "단가는 숫자라서 찾을 수 없다"),
        ]),
        "explanation": "VLOOKUP은 지정한 범위의 첫 번째 열에서 찾을 값을 검색합니다. 상품명은 두 번째 열이므로 이 수식은 구조가 잘못되었습니다.",
        "wrong_pattern_code": "VLOOKUP_FIRST_COL",
        "variation_group": "VLOOKUP_FIRST_COL",
    })
    
    rows.append({
        "id": "SCN_VLOOKUP_008",
        "title": "거래처명으로 담당자 조회 오류 찾기",
        "skill_auto": "VLOOKUP",
        "level": 3,
        "prompt": build_prompt(
            title="거래처명으로 담당자 조회 오류 찾기",
            context="거래처명을 기준으로 담당자를 찾으려고 다음 수식을 작성했습니다.",
            table="""A열 | B열 | C열
거래처코드 | 거래처명 | 담당자
C001 | 한빛상사 | 김민수
C002 | 대한유통 | 이지은""",
            rules="""- VLOOKUP은 지정한 범위의 첫 번째 열에서 찾을 값을 검색합니다.
- 현재 찾으려는 값은 거래처명입니다.""",
            question='=VLOOKUP("대한유통",A2:C3,3,FALSE)의 문제점은 무엇인가요?',
        ),
        "question_type": "error_detect",
        "answer_input_type": "text",
        "correct_answer": "B",
        "answer_schema": make_choice_schema([
            ("A", "FALSE를 사용하면 안 된다"),
            ("B", "찾을 값인 거래처명이 범위의 첫 번째 열에 있지 않다"),
            ("C", "열 번호는 3이 아니라 1이어야 한다"),
            ("D", "담당자는 문자라서 찾을 수 없다"),
        ]),
        "explanation": "VLOOKUP은 범위의 첫 번째 열에서 찾을 값을 검색합니다. 거래처명은 두 번째 열이므로 이 수식은 구조가 맞지 않습니다.",
        "wrong_pattern_code": "VLOOKUP_FIRST_COL",
        "variation_group": "VLOOKUP_FIRST_COL",
    })

    rows.append({
        "id": "SCN_VLOOKUP_009",
        "title": "상품명으로 제조사 조회 오류 찾기",
        "skill_auto": "VLOOKUP",
        "level": 3,
        "prompt": build_prompt(
            title="상품명으로 제조사 조회 오류 찾기",
            context="상품명을 기준으로 제조사를 찾으려고 다음 수식을 작성했습니다.",
            table="""A열 | B열 | C열 | D열
상품코드 | 상품명 | 제조사 | 단가
P001 | 키보드 | 한빛전자 | 30000
P002 | 마우스 | 대한전자 | 15000""",
            rules="""- VLOOKUP은 지정한 범위의 첫 번째 열에서 찾을 값을 검색합니다.
- 현재 찾으려는 값은 상품명입니다.""",
            question='=VLOOKUP("마우스",A2:D3,3,FALSE)의 문제점은 무엇인가요?',
        ),
        "question_type": "error_detect",
        "answer_input_type": "text",
        "correct_answer": "B",
        "answer_schema": make_choice_schema([
            ("A", "제조사는 세 번째 열이 아니므로 오류다"),
            ("B", "찾을 값인 상품명이 범위의 첫 번째 열에 있지 않다"),
            ("C", "FALSE 대신 TRUE를 써야 한다"),
            ("D", "상품코드는 숫자가 아니라서 찾을 수 없다"),
        ]),
        "explanation": "VLOOKUP은 지정 범위의 첫 번째 열에서 값을 찾습니다. 상품명은 두 번째 열에 있으므로 현재 범위 A2:D3에서는 상품명 기준 조회가 어렵습니다.",
        "wrong_pattern_code": "VLOOKUP_FIRST_COL",
        "variation_group": "VLOOKUP_FIRST_COL",
    })
     
    return rows

        


def generate_all():
    rows = []
    rows += generate_counta_scenarios()
    rows += generate_if_scenarios()
    rows += generate_sumif_scenarios()
    rows += generate_vlookup_scenarios()
    return rows


if __name__ == "__main__":
    rows = generate_all()
    save_csv(rows)

    print(f"CSV 생성 완료: {OUTPUT_FILE}")
    print(f"생성 문제 수: {len(rows)}개")
    print("다음 명령으로 import 하세요:")
    print(f"python manage.py import_missions {OUTPUT_FILE}")