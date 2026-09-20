import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Mission, MissionImage, ProblemSet, ProblemSetItem, Subject
from core.services.logistics_curriculum import normalize_logistics_chapter
from core.services.mission_images import resolve_question_image
from core.services.content_review import apply_review, load_review
from core.services.subjects import LOGISTICS_SUBJECT_CODE
from core.services.weaknesses import default_pattern_code, ensure_subject_learning_configuration


VALID_DIFFICULTIES = {"하", "중", "상"}
VALID_LEARNING_TYPES = {"result", "feature", "error", "next_action", "procedure"}
VALID_QUESTION_TYPES = {
    "manual",
    "short_answer",
    "value_answer",
    "choice_one",
    "true_false",
    "error_detect",
}
DIFFICULTY_LEVELS = {"하": 1, "중": 2, "상": 3}
KOREAN_REQUIRED_COLUMNS = {"번호", "과목", "난이도", "문제", "정답", "해설"}
KOREAN_CHAPTER_COLUMNS = {"챕터", "분류코드"}


def mission_import_state(mission):
    """Return persisted import-relevant state for accurate sync counters."""
    if mission is None:
        return None
    mission.refresh_from_db()
    mission_state = tuple(
        (field.attname, getattr(mission, field.attname))
        for field in mission._meta.concrete_fields
        if field.name not in {"id", "created_at"}
    )
    try:
        image = mission.question_image
    except MissionImage.DoesNotExist:
        image_state = None
    else:
        image_state = (image.static_path, image.alt_text, image.source)
    return mission_state, image_state


def optional_learning_feedback(row, *, korean_schema=False):
    """Return only feedback fields explicitly present in the source CSV."""
    data = {}
    source_columns = {"source_type": "문제구분", "source_reference": "출처", "reviewed_on": "검수일"}
    for field, korean_column in source_columns.items():
        column = korean_column if korean_schema else field
        if column not in row:
            continue
        value = (row.get(column) or "").strip()
        if field == "source_type":
            value = {"기출": "past", "기출 변형": "adapted", "자체 제작": "original", "출처 미등록": "unknown"}.get(value, value or "unknown")
            if value not in dict(Mission.SOURCE_TYPES):
                raise ValueError("문제구분은 unknown/past/adapted/original 중 하나여야 합니다")
        elif field == "reviewed_on":
            value = datetime.strptime(value, "%Y-%m-%d").date() if value else None
        elif len(value) > 300:
            raise ValueError("출처는 300자 이내여야 합니다")
        data[field] = value
    concept_column = "핵심개념" if korean_schema else "concept_summary"
    tip_column = "시험팁" if korean_schema else "exam_tip"
    if concept_column in row:
        data["concept_summary"] = (row.get(concept_column) or "").strip()
    if tip_column in row:
        data["exam_tip"] = (row.get(tip_column) or "").strip()

    explanations = {}
    has_choice_columns = False
    for number in range(1, 6):
        column_candidates = (
            (f"보기{number}해설",)
            if korean_schema
            else (f"choice_{number}_explanation", f"choice{number}_explanation")
        )
        for column in column_candidates:
            if column in row:
                has_choice_columns = True
                value = (row.get(column) or "").strip()
                if value:
                    explanations[str(number)] = value
                break

    if not korean_schema and "choice_explanations" in row:
        has_choice_columns = True
        raw_value = (row.get("choice_explanations") or "").strip()
        if raw_value:
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError as error:
                raise ValueError("choice_explanations가 올바른 JSON이 아닙니다") from error
            if not isinstance(parsed, dict):
                raise ValueError("choice_explanations는 JSON 객체여야 합니다")
            explanations.update({str(key): str(value).strip() for key, value in parsed.items() if str(value).strip()})

    if has_choice_columns:
        data["choice_explanations"] = explanations
    return data


def infer_answer_input_type(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return "text"

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            datetime.strptime(text, fmt)
            return "date"
        except ValueError:
            pass

    if re.fullmatch(r"-?\d+(\.\d+)?", text.replace(",", "")):
        return "number"
    return "text"


def parse_chapter(raw_chapter):
    value = (raw_chapter or "").strip()
    match = re.match(r"^([A-Za-z]{2}\d{2})\s*(?:[.|]\s*)?(.*)$", value)
    if not match:
        return "", value
    return match.group(1).upper(), match.group(2).strip()


def source_slug(csv_path):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", Path(csv_path).stem).strip("-").upper()
    return slug[:35] or "CSV"


def build_choice_schema(row):
    choices = []
    for number in range(1, 6):
        label = (row.get(f"보기{number}") or "").strip()
        if label:
            choices.append(f"{number}|{label}")
    return "\n".join(choices)


def normalize_korean_row(row, *, csv_path, subject_code):
    number_text = (row.get("번호") or "").strip()
    if not number_text.isdigit():
        raise ValueError("번호가 숫자가 아닙니다")

    number = int(number_text)
    course = (row.get("과목") or "").strip()
    chapter_code, chapter_name = parse_chapter(row.get("챕터") or row.get("분류코드"))
    if subject_code == LOGISTICS_SUBJECT_CODE:
        chapter_code, chapter_name = normalize_logistics_chapter(chapter_code, chapter_name)

    difficulty = (row.get("난이도") or "").strip()
    prompt = (row.get("문제") or "").strip()
    correct_answer = (row.get("정답") or "").strip()
    explanation = (row.get("해설") or "").strip()
    answer_schema = build_choice_schema(row)
    choice_count = len(answer_schema.splitlines())

    if not course or not chapter_code or not prompt:
        raise ValueError("과목, 챕터 코드 또는 문제가 비어 있습니다")
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"invalid difficulty: {difficulty}")
    if not correct_answer.isdigit() or not 1 <= int(correct_answer) <= choice_count:
        raise ValueError("정답 번호가 보기 범위를 벗어납니다")

    batch_label = Path(csv_path).stem.replace("_", " ")
    external_id = f"{subject_code.upper()}-{chapter_code}-{source_slug(csv_path)}-{number:04d}"
    data = {
        "external_id": external_id[:100],
        "subject_code": subject_code,
        "course": course,
        "chapter_code": chapter_code,
        "chapter_name": chapter_name,
        "difficulty": difficulty,
        "title": f"{batch_label} · {course} {number}번",
        "skill": chapter_code,
        "level": DIFFICULTY_LEVELS[difficulty],
        "prompt": prompt,
        "answer_key": correct_answer,
        "question_type": "choice_one",
        "learning_type": "result",
        "answer_input_type": "none",
        "correct_answer": correct_answer,
        "explanation": explanation,
        "answer_schema": answer_schema,
        "wrong_pattern_code": default_pattern_code(subject_code, chapter_code),
        "variation_group": default_pattern_code(subject_code, chapter_code) or chapter_code,
        "image_raw_path": (row.get("문제이미지") or row.get("이미지") or "").strip(),
        "question_number": number,
        "quality_defaults": {
            "is_quality_checked": True,
            "quality_level": "standard",
            "is_usable_for_set": True,
        },
    }
    data.update(optional_learning_feedback(row, korean_schema=True))
    return data


def normalize_standard_row(row, *, subject_code):
    external_id = ((row.get("external_id") or "").strip() or (row.get("id") or "").strip())
    course = (row.get("course") or "").strip()
    chapter_code = (row.get("chapter_code") or "").strip()
    chapter_name = (row.get("chapter_name") or "").strip()
    if subject_code == LOGISTICS_SUBJECT_CODE:
        chapter_code, chapter_name = normalize_logistics_chapter(chapter_code, chapter_name)

    difficulty = (row.get("difficulty") or "").strip()
    title = (row.get("title") or "").strip()
    prompt = (row.get("prompt") or "").strip()
    correct_answer = (row.get("correct_answer") or "").strip()
    answer_input_type = (row.get("answer_input_type") or "").strip() or "text"
    learning_type = (row.get("learning_type") or "").strip() or "result"
    question_type = (row.get("question_type") or "").strip()
    skill = (
        (row.get("skill_auto") or "").strip()
        or (row.get("skill_group") or "").strip()
        or chapter_code
        or course
    )

    if not external_id:
        raise ValueError("external_id/id가 비어 있습니다")
    if not title or not skill:
        raise ValueError("title 또는 skill이 비어 있습니다")
    if difficulty and difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"invalid difficulty: {difficulty}")
    if learning_type not in VALID_LEARNING_TYPES:
        learning_type = "result"
    if question_type not in VALID_QUESTION_TYPES:
        question_type = "value_answer" if answer_input_type in ("number", "date") else "short_answer"

    level_text = (row.get("level") or "1").strip()
    if not level_text.isdigit():
        raise ValueError("level이 숫자가 아닙니다")

    data = {
        "external_id": external_id,
        "subject_code": subject_code,
        "course": course,
        "chapter_code": chapter_code,
        "chapter_name": chapter_name,
        "difficulty": difficulty,
        "title": title,
        "skill": skill,
        "level": int(level_text),
        "prompt": prompt,
        "answer_key": (row.get("answer_key") or "").strip(),
        "question_type": question_type,
        "learning_type": learning_type,
        "answer_input_type": answer_input_type,
        "correct_answer": correct_answer,
        "explanation": (row.get("explanation") or "").strip(),
        "answer_schema": (row.get("answer_schema") or "").strip(),
        "wrong_pattern_code": (row.get("wrong_pattern_code") or "").strip(),
        "variation_group": (row.get("variation_group") or "").strip(),
        "image_raw_path": (
            (row.get("question_image") or "").strip()
            or (row.get("image_path") or "").strip()
            or (row.get("image") or "").strip()
        ),
        "question_number": (row.get("number") or row.get("question_number") or "").strip(),
        "quality_defaults": {},
    }
    data.update(optional_learning_feedback(row))
    return data


def sync_generated_problem_sets(missions):
    """Rebuild only affected canonical chapters from all current DB missions.

    The stable generation key prevents a renamed chapter from silently reusing a
    set whose items belong to another chapter. Historical sets are deactivated,
    never deleted, so completed sessions remain readable.
    """
    affected = {}
    for mission in missions:
        affected[(mission.subject_id, mission.course, mission.chapter_code)] = mission.chapter_name

    created_count = 0
    updated_count = 0
    deactivated_count = 0
    for (subject_id, course, chapter_code), chapter_name in affected.items():
        grouped_missions = list(
            Mission.objects.filter(
                subject_id=subject_id,
                course=course,
                chapter_code=chapter_code,
                is_usable_for_set=True,
            )
            .exclude(review_status=Mission.REVIEW_CONFIRMED_ERROR)
            .order_by("external_id")
        )
        if not grouped_missions:
            continue
        ordered = sorted(grouped_missions, key=lambda mission: mission.external_id)
        expected_keys = []
        for chunk_index in range(0, len(ordered), 10):
            chunk = ordered[chunk_index:chunk_index + 10]
            subject = chunk[0].subject
            set_number = (chunk_index // 10) + 1
            title = f"[자동] {subject.name} · {course} · {chapter_name or chapter_code} {set_number}"
            generation_key = f"{subject.code}|{course}|{chapter_code}|{set_number}"
            expected_keys.append(generation_key)
            problem_set, created = ProblemSet.objects.update_or_create(
                generation_key=generation_key[:200],
                defaults={
                    "title": title[:200],
                    "skill_group": chapter_code,
                    "level": max(1, round(sum(m.level for m in chunk) / len(chunk))),
                    "set_type": "training",
                    "description": "CSV 문제를 기반으로 자동 구성된 학습 세트입니다.",
                    "is_active": True,
                },
            )
            problem_set.items.all().delete()
            ProblemSetItem.objects.bulk_create([
                ProblemSetItem(problem_set=problem_set, mission=mission, order_no=index, role="core")
                for index, mission in enumerate(chunk, start=1)
            ])
            created_count += int(created)
            updated_count += int(not created)
        stale_sets = (
            ProblemSet.objects
            .filter(
                title__startswith="[자동]",
                is_active=True,
                items__mission__subject_id=subject_id,
                items__mission__course=course,
                items__mission__chapter_code=chapter_code,
            )
            .exclude(generation_key__in=expected_keys)
            .distinct()
        )
        deactivated_count += stale_sets.update(is_active=False)
    return created_count, updated_count, deactivated_count


class Command(BaseCommand):
    help = "Import or update missions from one CSV file or every CSV below a directory"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)
        parser.add_argument("--subject-code", default="")
        parser.add_argument("--create-problem-sets", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        review_manifest = load_review()
        source_path = Path(options["csv_path"])
        if source_path.is_dir():
            csv_paths = sorted(source_path.rglob("*.csv"))
        elif source_path.is_file():
            csv_paths = [source_path]
        else:
            raise CommandError(f"CSV path does not exist: {source_path}")
        if not csv_paths:
            raise CommandError(f"No CSV files found: {source_path}")

        subject_cache = {subject.code: subject for subject in Subject.objects.all()}
        for configured_subject in subject_cache.values():
            ensure_subject_learning_configuration(configured_subject)
        override_subject_code = options["subject_code"].strip()
        created_count = updated_count = skipped_count = 0
        image_linked_count = image_missing_count = 0
        invalidated_attempt_count = 0
        affected_user_ids = set()
        imported_missions = []

        for csv_path in csv_paths:
            with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
                reader = csv.DictReader(csv_file)
                fieldnames = set(reader.fieldnames or [])
                is_korean_schema = (
                    KOREAN_REQUIRED_COLUMNS.issubset(fieldnames)
                    and bool(KOREAN_CHAPTER_COLUMNS.intersection(fieldnames))
                )
                inferred_subject_code = csv_path.parent.name if csv_path.parent.name in subject_cache else ""

                for row_number, row in enumerate(reader, start=2):
                    row_subject_code = (row.get("subject_code") or "").strip()
                    subject_code = override_subject_code or row_subject_code or inferred_subject_code
                    if subject_code:
                        subject = subject_cache.get(subject_code)
                        if subject is None:
                            skipped_count += 1
                            self.stdout.write(f"SKIP unknown subject_code={subject_code} ({csv_path.name}:{row_number})")
                            continue
                    else:
                        skipped_count += 1
                        self.stdout.write(
                            "SKIP missing subject_code; use --subject-code or a registered "
                            f"subject folder ({csv_path.name}:{row_number})"
                        )
                        continue

                    try:
                        if is_korean_schema:
                            data = normalize_korean_row(row, csv_path=csv_path, subject_code=subject_code)
                        else:
                            data = normalize_standard_row(row, subject_code=subject_code)
                    except ValueError as error:
                        skipped_count += 1
                        self.stdout.write(f"SKIP {error} ({csv_path.name}:{row_number})")
                        continue

                    quality_defaults = data.pop("quality_defaults")
                    image_raw_path = data.pop("image_raw_path")
                    question_number = data.pop("question_number")
                    external_id = data.pop("external_id")
                    data.pop("subject_code", None)
                    data.update(quality_defaults)
                    data["subject"] = subject

                    # Earlier releases rewrote FT/IT/BH/LR to internal aliases,
                    # so the chapter portion of Korean external IDs changed.
                    # Reuse that row by its stable source-file/number suffix
                    # instead of creating a duplicate during taxonomy repair.
                    existing_mission = Mission.objects.filter(external_id=external_id).first()
                    previous_state = mission_import_state(existing_mission)
                    if is_korean_schema and existing_mission is None:
                        external_parts = external_id.split("-", 2)
                        if len(external_parts) == 3:
                            legacy_matches = Mission.objects.filter(
                                subject=subject,
                                external_id__endswith=f"-{external_parts[2]}",
                            )
                            if legacy_matches.count() == 1:
                                legacy_mission = legacy_matches.first()
                                previous_state = mission_import_state(legacy_mission)
                                legacy_mission.external_id = external_id
                                legacy_mission.save(update_fields=["external_id"])

                    mission, created = Mission.objects.update_or_create(
                        external_id=external_id,
                        defaults=data,
                    )
                    grading_impact = getattr(mission, "_grading_change_impact", {})
                    invalidated_attempt_count += grading_impact.get("attempts", 0)
                    affected_user_ids.update(grading_impact.get("user_ids", ()))
                    apply_review(mission, review_manifest)
                    imported_missions.append(mission)

                    image_path, image_source, explicit_missing = resolve_question_image(
                        raw_path=image_raw_path,
                        subject_code=subject_code,
                        csv_path=csv_path,
                        question_number=question_number,
                    )
                    if image_path:
                        MissionImage.objects.update_or_create(
                            mission=mission,
                            defaults={
                                "static_path": image_path,
                                "alt_text": f"{mission.title} 문제 자료",
                                "source": image_source,
                            },
                        )
                        image_linked_count += 1
                    elif explicit_missing:
                        image_missing_count += 1
                        self.stderr.write(f"IMAGE MISSING {csv_path.name}:{row_number} {image_raw_path}")

                    current_state = mission_import_state(mission)
                    if created:
                        created_count += 1
                    elif previous_state != current_state:
                        updated_count += 1
                    else:
                        skipped_count += 1

        set_created = set_updated = set_deactivated = 0
        if options["create_problem_sets"]:
            unique_missions = list({mission.id: mission for mission in imported_missions}.values())
            set_created, set_updated, set_deactivated = sync_generated_problem_sets(unique_missions)

        if options["dry_run"]:
            transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            "Import complete: "
            f"files={len(csv_paths)}, created={created_count}, updated={updated_count}, skipped={skipped_count}, "
            f"invalidated_attempts={invalidated_attempt_count}, affected_users={len(affected_user_ids)}, "
            f"images_linked={image_linked_count}, images_missing={image_missing_count}, "
            f"sets_created={set_created}, sets_updated={set_updated}, "
            f"sets_deactivated={set_deactivated}, dry_run={options['dry_run']}"
        ))
