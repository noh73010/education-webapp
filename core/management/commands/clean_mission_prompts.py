from django.core.management.base import BaseCommand
from core.models import Mission


REMOVE_CHARS = [
    "👉",
    "📌",
    "💡",
    "🔥",
    "🎯",
    "✅",
    "❌",
    "⭐",
    "✔",
    "☑",
]


class Command(BaseCommand):
    help = "Remove emoji-like markers from Mission prompts and explanations"

    def handle(self, *args, **options):
        updated_count = 0

        for mission in Mission.objects.all():
            old_prompt = mission.prompt or ""
            old_explanation = mission.explanation or ""

            new_prompt = old_prompt
            new_explanation = old_explanation

            for ch in REMOVE_CHARS:
                new_prompt = new_prompt.replace(ch, "")
                new_explanation = new_explanation.replace(ch, "")

            new_prompt = new_prompt.strip()
            new_explanation = new_explanation.strip()

            if new_prompt != old_prompt or new_explanation != old_explanation:
                mission.prompt = new_prompt
                mission.explanation = new_explanation
                mission.save(update_fields=["prompt", "explanation"])
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"문제 문구 정리 완료: {updated_count}개 수정"
            )
        )