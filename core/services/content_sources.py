"""Q-Net source notices for published content, independent of import state."""


# Add a round only after checking its Q-Net page and reuse conditions.
LOGISTICS_QNET_SOURCES = (
    (25, "2021년 제25회 물류관리사 자격시험 기출문제", "5208820"),
    (26, "2022년 제26회 물류관리사 자격시험 기출문제", "5210918"),
    (27, "2023년 제27회 물류관리사 자격시험 기출문제", "5212214"),
    (28, "2024년 제28회 물류관리사 자격시험 기출문제", "5213611"),
    (29, "2025년 제29회 물류관리사 기출문제", "5240725"),
)

SITTINGS = (
    (1, "1교시", "물류관리론 · 화물운송론 · 국제물류론"),
    (2, "2교시", "보관하역론 · 물류관련법규"),
)


def logistics_source_notices():
    """List checked source publications, not currently available questions."""
    sources = []
    for round_number, title, article_id in LOGISTICS_QNET_SOURCES:
        sittings = [
            {"label": label, "subjects": subjects}
            for sitting, label, subjects in SITTINGS
        ]
        sources.append({
            "round_number": round_number,
            "title": title,
            "qnet_url": (
                "https://www.q-net.or.kr/cst003.do"
                f"?artlSeq={article_id}&boardId=Q004&gId=61"
                "&gSite=L&id=cst00302&menuType=cst00309"
            ),
            "sittings": sittings,
        })
    return sources


REALTOR_QNET_SOURCES = (
    (35, "2024년 제35회 공인중개사 자격시험 문제지", "5214724"),
    (36, "2025년 제36회 공인중개사 자격시험 시험문제지", "5247125"),
)

REALTOR_SITTINGS = (
    ("1차", "부동산학개론 · 민법 및 민사특별법"),
    ("2차 1교시", "공인중개사법령 및 중개실무 · 부동산공법"),
    ("2차 2교시", "부동산공시법 · 부동산세법"),
)


def realtor_source_notices():
    """Show the two checked Q-Net publications used by the current CSVs."""
    return [
        {
            "round_number": round_number,
            "title": title,
            "qnet_url": (
                "https://www.q-net.or.kr/cst003.do"
                f"?artlSeq={article_id}&boardId=Q004&gId=08"
                "&gSite=L&id=cst00302&menuType=cst00309"
            ),
            "sittings": [
                {"label": label, "subjects": subjects}
                for label, subjects in REALTOR_SITTINGS
            ],
        }
        for round_number, title, article_id in REALTOR_QNET_SOURCES
    ]
