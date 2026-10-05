"""공인중개사 시험의 단계·과목 구성. 물류관리사 규칙과 분리한다."""

REALTOR_SUBJECT_CODE = "realtor"
REALTOR_EXAM_GUIDE = (
    "https://www.q-net.or.kr/crf005.do?gId=36&gSite=Q&id=crf00503s02"
    "&jmCd=9630&jmInfoDivCcd=B0"
)

REALTOR_SITTINGS = (
    {
        "stage": "first", "label": "1차", "sitting": "1교시", "minutes": 100,
        "courses": ("부동산학개론", "민법 및 민사특별법"),
    },
    {
        "stage": "second", "label": "2차", "sitting": "1교시", "minutes": 100,
        "courses": ("공인중개사법령 및 중개실무", "부동산공법"),
    },
    {
        "stage": "second", "label": "2차", "sitting": "2교시", "minutes": 50,
        "courses": ("부동산공시법 및 부동산세법",),
    },
)
REALTOR_COURSES = tuple(
    course for sitting in REALTOR_SITTINGS for course in sitting["courses"]
)

REALTOR_SOURCE_COURSE_ALIASES = {
    "민법 및 민사특별법 중 부동산 중개 관련 규정": REALTOR_COURSES[1],
    "부동산공법 중 부동산 중개 관련 규정": REALTOR_COURSES[3],
    "부동산공시법령": REALTOR_COURSES[4],
    "부동산세법": REALTOR_COURSES[4],
}


def normalize_realtor_course(course):
    """Map exam-paper section labels to the app's five scored courses."""
    value = (course or "").strip()
    return REALTOR_SOURCE_COURSE_ALIASES.get(value, value)

# Learning areas are intentionally more detailed than the five scored exam
# courses. RE05 and RE06 both belong to the same 2차 2교시 scoring course.
REALTOR_LEARNING_AREAS = (
    {
        "code": "RE01", "title": "부동산학개론", "course": REALTOR_COURSES[0], "stage": "first",
        "chapters": (
            ("RE01-01", "부동산학 총론"),
            ("RE01-02", "부동산 경제론"),
            ("RE01-03", "부동산 시장론"),
            ("RE01-04", "입지 및 공간구조론"),
            ("RE01-05", "부동산 정책론"),
            ("RE01-06", "부동산 투자론"),
            ("RE01-07", "부동산 금융론"),
            ("RE01-08", "부동산 개발 및 관리론"),
            ("RE01-09", "부동산 마케팅 및 이용론"),
            ("RE01-10", "부동산 감정평가론"),
        ),
    },
    {
        "code": "RE02", "title": "민법 및 민사특별법", "course": REALTOR_COURSES[1], "stage": "first",
        "chapters": (
            ("RE02-01", "민법 총칙"),
            ("RE02-02", "물권법 총론"),
            ("RE02-03", "점유권 및 소유권"),
            ("RE02-04", "용익물권"),
            ("RE02-05", "담보물권"),
            ("RE02-06", "계약법 총론"),
            ("RE02-07", "매매 및 교환"),
            ("RE02-08", "임대차"),
            ("RE02-09", "주택·상가 임대차보호법"),
            ("RE02-10", "집합건물·가등기담보 등 민사특별법"),
        ),
    },
    {
        "code": "RE03", "title": "공인중개사법령 및 중개실무", "course": REALTOR_COURSES[2], "stage": "second",
        "chapters": (
            ("RE03-01", "공인중개사 제도 및 자격"),
            ("RE03-02", "중개사무소 개설등록"),
            ("RE03-03", "중개업무 및 중개사무소 운영"),
            ("RE03-04", "개업공인중개사의 의무와 책임"),
            ("RE03-05", "중개계약 및 거래정보망"),
            ("RE03-06", "중개보수 및 실비"),
            ("RE03-07", "지도·감독 및 행정처분"),
            ("RE03-08", "벌칙 및 행정질서벌"),
            ("RE03-09", "부동산 거래신고 및 중개실무"),
        ),
    },
    {
        "code": "RE04", "title": "부동산공법", "course": REALTOR_COURSES[3], "stage": "second",
        "chapters": (
            ("RE04-01", "국토의 계획 및 이용에 관한 법률 총론"),
            ("RE04-02", "도시·군관리계획과 용도지역·지구·구역"),
            ("RE04-03", "개발행위허가 및 기반시설"),
            ("RE04-04", "도시개발법"),
            ("RE04-05", "도시 및 주거환경정비법"),
            ("RE04-06", "건축법"),
            ("RE04-07", "주택법"),
            ("RE04-08", "농지법"),
            ("RE04-09", "공법상 각종 허가·제한 비교"),
            ("RE04-10", "공법 종합 및 사례형"),
        ),
    },
    {
        "code": "RE05", "title": "부동산공시법", "course": REALTOR_COURSES[4], "stage": "second",
        "chapters": (
            ("RE05-01", "공간정보의 구축 및 관리 등에 관한 법률 총론"),
            ("RE05-02", "토지의 등록"),
            ("RE05-03", "지적공부"),
            ("RE05-04", "토지이동 및 지적정리"),
            ("RE05-05", "지적측량"),
            ("RE05-06", "부동산등기법 총론"),
            ("RE05-07", "등기절차 및 각종 권리등기"),
            ("RE05-08", "표시등기·변경등기·말소등기 등"),
        ),
    },
    {
        "code": "RE06", "title": "부동산세법", "course": REALTOR_COURSES[4], "stage": "second",
        "chapters": (
            ("RE06-01", "조세 총론"),
            ("RE06-02", "취득세"),
            ("RE06-03", "등록면허세"),
            ("RE06-04", "재산세"),
            ("RE06-05", "종합부동산세"),
            ("RE06-06", "양도소득세"),
            ("RE06-07", "부동산 관련 기타 조세"),
            ("RE06-08", "부동산 세금 종합계산 및 사례"),
        ),
    },
)
REALTOR_CHAPTERS = {
    code: (area["course"], name)
    for area in REALTOR_LEARNING_AREAS
    for code, name in area["chapters"]
}


def learning_area(code):
    return next((area for area in REALTOR_LEARNING_AREAS if area["code"] == code), None)


def area_for_focus(focus):
    if focus is None:
        return None
    area = learning_area(focus.area_code)
    if area and area["course"] == focus.course:
        return area
    matches = [item for item in REALTOR_LEARNING_AREAS if item["course"] == focus.course]
    return matches[0] if len(matches) == 1 else None


def normalize_realtor_chapter(course, chapter_code):
    code = (chapter_code or "").strip().upper()
    expected = REALTOR_CHAPTERS.get(code)
    if expected is None:
        raise ValueError("공인중개사 챕터 코드는 등록된 RE01-01~RE06-08 중 하나여야 합니다")
    if course != expected[0]:
        raise ValueError(f"{code}의 과목명은 {expected[0]}이어야 합니다")
    return code, expected[1]


def courses_for_path(path):
    return tuple(
        course
        for sitting in REALTOR_SITTINGS
        if path == "both" or sitting["stage"] == path
        for course in sitting["courses"]
    )
