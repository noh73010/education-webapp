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


def courses_for_path(path):
    return tuple(
        course
        for sitting in REALTOR_SITTINGS
        if path == "both" or sitting["stage"] == path
        for course in sitting["courses"]
    )
