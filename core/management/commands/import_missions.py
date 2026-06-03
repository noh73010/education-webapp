import csv
import re
from datetime import datetime

from django.core.management.base import BaseCommand
from core.models import Mission


def infer_answer_input_type(answer: str) -> str:
    text = (answer or "").strip()

    if not text:
        return "text"

    date_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
    ]
    for fmt in date_formats:
        try:
            datetime.strptime(text, fmt)
            return "date"
        except ValueError:
            pass

    number_text = text.replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?", number_text):
        return "number"

    return "text"


class Command(BaseCommand):
    help = "Import or update missions from CSV"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        csv_path = options["csv_path"]

        created_count = 0
        updated_count = 0
        skipped_count = 0
        skip_debug_count = 0

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                external_id = (row.get("id") or "").strip()

                title = (row.get("title") or "").strip()
                skill = (
                    (row.get("skill_auto") or "").strip()
                    or (row.get("skill_group") or "").strip()
                )

                if not external_id and not title and not skill:
                    skipped_count += 1
                    if skip_debug_count < 20:
                        print("스킵(완전 빈 행):", row)
                        skip_debug_count += 1
                    continue

                if not external_id:
                    skipped_count += 1
                    if skip_debug_count < 20:
                        print("스킵(id 누락):", row)
                        skip_debug_count += 1
                    continue

                if not title or not skill:
                    skipped_count += 1
                    if skip_debug_count < 20:
                        print("스킵(title/skill 누락):", row)
                        skip_debug_count += 1
                    continue

                raw_answer_key = (row.get("answer_key") or "").strip()

                correct_answer = (row.get("correct_answer") or "").strip()
                answer_input_type = (row.get("answer_input_type") or "").strip() or "text"
                question_type = (row.get("question_type") or "").strip()

                valid_question_types = (
                    "manual",
                    "short_answer",
                    "value_answer",
                    "choice_one",
                    "true_false",
                    "error_detect",
                )

                if question_type not in valid_question_types:
                    if answer_input_type in ("number", "date"):
                        question_type = "value_answer"
                    else:
                        question_type = "short_answer"

                obj, created = Mission.objects.update_or_create(
                    external_id=external_id,
                    defaults={
                        "title": title,
                        "skill": skill,
                        "level": int((row.get("level") or "1").strip()),
                        "prompt": (row.get("prompt") or "").strip(),
                        "answer_key": raw_answer_key,
                        "question_type": question_type,
                        "answer_input_type": answer_input_type,
                        "correct_answer": correct_answer,
                        "explanation": (row.get("explanation") or "").strip(),
                        "answer_schema": (row.get("answer_schema") or "").strip(),
                        "wrong_pattern_code": (row.get("wrong_pattern_code") or "").strip(),
                        "variation_group": (row.get("variation_group") or "").strip(),
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"완료: 생성 {created_count}개 / 수정 {updated_count}개 / 빈값 스킵 {skipped_count}개"
            )
        )