import json
import re
from collections import Counter
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand, CommandError

from core.models import Mission
from core.services.content_review import apply_review, content_fingerprint, load_review
from core.services.grading import parse_choice_schema


class Command(BaseCommand):
    help = "Read-only content audit by default; --apply-reviewed applies exact, versioned review entries only."

    def add_arguments(self, parser):
        parser.add_argument("--subject-code", required=True)
        parser.add_argument("--apply-reviewed", action="store_true")
        parser.add_argument("--output")

    def handle(self, *args, **options):
        qs = Mission.objects.filter(subject__code=options["subject_code"]).select_related("subject", "question_image", "concept_unit")
        if not qs.exists():
            raise CommandError("선택한 과목의 문제가 없습니다.")
        manifest = load_review()
        rows, summary = [], Counter()
        for mission in qs.order_by("external_id"):
            decision = apply_review(mission, manifest) if options["apply_reviewed"] else "not_applied"
            problems = []
            choices = parse_choice_schema(mission.answer_schema)
            if mission.question_type in ("choice_one", "error_detect", "true_false"):
                if not choices:
                    problems.append("missing_choices")
                if mission.correct_answer not in {str(c["key"]) for c in choices}:
                    problems.append("answer_not_in_choices")
            if not mission.explanation.strip():
                problems.append("missing_explanation")
            image = getattr(mission, "question_image", None)
            image_exists = bool(image and finders.find(image.static_path))
            if image and not image_exists:
                problems.append("missing_image_file")
            if re.search("[ㄱㄴㄷㄹㅁ]", mission.answer_schema) and not re.search("[ㄱㄴㄷㄹㅁ]", mission.prompt):
                problems.append("image_text_review_required" if image_exists else "missing_statement_context")
            if mission.source_type == "unknown" or not mission.source_reference:
                problems.append("original_source_unverified")
            if not mission.reviewed_on:
                problems.append("content_review_pending")
            summary.update(problems)
            summary["total"] += 1
            summary["reviewed_content"] += bool(mission.reviewed_on)
            summary["mapped_concept"] += bool(mission.concept_unit_id)
            summary["not_available_for_sets"] += not mission.is_usable_for_set
            rows.append({"external_id": mission.external_id, "issues": problems, "decision": decision,
                         "fingerprint": content_fingerprint(mission), "image": image.static_path if image else None})
        report = {"subject": options["subject_code"], "summary": dict(summary), "missions": rows,
                  "note": "구조 검사 통과는 정답·해설·법령 최신성 또는 원출처 검증 완료를 의미하지 않습니다."}
        if options["output"]:
            target = Path(options["output"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps(report["summary"], ensure_ascii=False))
