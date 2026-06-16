from django.core.management.base import BaseCommand

from core.services.analytics import get_analytics_summary


class Command(BaseCommand):
    help = "Print a compact user behavior analytics summary."

    def handle(self, *args, **options):
        summary = get_analytics_summary(recent_limit=0, top_limit=5)

        self.stdout.write(f"총 가입자: {summary['total_users']}")
        self.stdout.write(f"오늘 가입자: {summary['today_users']}")
        self.stdout.write(f"오늘 문제 풀이 완료 수: {summary['today_mission_finish_count']}")
        self.stdout.write(f"오늘 모의고사 시작 수: {summary['today_exam_start_count']}")
        self.stdout.write(f"오늘 모의고사 완료 수: {summary['today_exam_finish_count']}")
        self.stdout.write(f"오늘 패턴훈련 시작 수: {summary['today_pattern_start_count']}")
        self.stdout.write(f"오늘 패턴훈련 완료 수: {summary['today_pattern_finish_count']}")
        self.stdout.write(f"오늘 프리미엄 안내 방문 수: {summary['today_premium_page_view_count']}")
        self.stdout.write("")
        self.stdout.write("최근 7일 이벤트 TOP5")

        if not summary["popular_events"]:
            self.stdout.write("- 이벤트 없음")
            return

        for index, row in enumerate(summary["popular_events"], start=1):
            self.stdout.write(f"{index}. {row['event_type']}: {row['count']}")
