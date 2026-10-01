"""Verified public source notices for logistics practice questions."""

from pathlib import Path

from django.conf import settings


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


def published_logistics_sources():
    """List only verified rounds with a CSV in this deployed checkout."""
    source_dir = Path(settings.BASE_DIR) / "generated" / "logistics"
    sources = []
    for round_number, title, article_id in LOGISTICS_QNET_SOURCES:
        sittings = [
            {"label": label, "subjects": subjects}
            for sitting, label, subjects in SITTINGS
            if (source_dir / f"logistics_{round_number}-{sitting}.csv").is_file()
        ]
        if sittings:
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
