import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import Attempt, Mission, Subject
from core.services.logistics_curriculum import (
    build_logistics_chapter_roadmap,
    get_logistics_curriculum,
)
from core.services.mission_quality import usable_missions
from core.services.subjects import (
    CURRENT_SUBJECT_SESSION_KEY,
    DEFAULT_SUBJECT_CODE,
    LOGISTICS_SUBJECT_CODE,
    get_default_subject,
    seed_platform_subjects,
)


LOGISTICS_STANDARD_COLUMNS = [
    "external_id",
    "subject_code",
    "course",
    "chapter_code",
    "chapter_name",
    "difficulty",
    "title",
    "prompt",
    "answer_schema",
    "correct_answer",
    "explanation",
    "learning_type",
    "question_type",
    "answer_input_type",
    "wrong_pattern_code",
    "variation_group",
]


class SubjectPlatformTests(TestCase):
    def create_mission(self, external_id, subject=None, is_usable=True):
        return Mission.objects.create(
            external_id=external_id,
            subject=subject,
            title=f"{external_id} title",
            skill="COUNT",
            level=1,
            prompt="[CONTEXT]\n출석표\n[DATA]\nA1:A5\n[QUESTION]\n결석 횟수를 확인하세요.",
            correct_answer="1",
            explanation="COUNT 계열 함수 학습 테스트 문제입니다.",
            quality_level="practical",
            is_quality_checked=True,
            is_usable_for_set=is_usable,
        )

    def create_logistics_mission(self, external_id="LOG-LM01-0100", chapter_code="LM01"):
        seed_platform_subjects()
        subject = Subject.objects.get(code=LOGISTICS_SUBJECT_CODE)
        return Mission.objects.create(
            external_id=external_id,
            subject=subject,
            course="물류관리론",
            chapter_code=chapter_code,
            chapter_name="물류관리 일반",
            difficulty="하",
            title=f"{chapter_code} 테스트 문제",
            skill=chapter_code,
            level=1,
            prompt="[CONTEXT] 물류관리 [QUESTION] 물류관리의 기본 목적은?",
            correct_answer="2",
            answer_schema="1|재고 확대|2|서비스와 비용 균형",
            explanation="물류관리는 고객 서비스와 물류비의 균형을 관리합니다.",
            learning_type="result",
            question_type="choice_one",
            answer_input_type="none",
            quality_level="practical",
            is_quality_checked=True,
            is_usable_for_set=True,
        )

    def write_csv(self, tmpdir, rows):
        csv_path = Path(tmpdir) / "missions.csv"
        csv_path.write_text("\n".join(rows), encoding="utf-8-sig")
        return csv_path

    def test_sample_csv_uses_standard_logistics_columns(self):
        sample_path = Path(settings.BASE_DIR) / "generated" / "logistics_missions_sample.csv"

        with sample_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(reader.fieldnames, LOGISTICS_STANDARD_COLUMNS)
        self.assertGreaterEqual(len(rows), 1)
        self.assertLessEqual(len(rows), 2)
        self.assertTrue(all(row["subject_code"] == LOGISTICS_SUBJECT_CODE for row in rows))
        self.assertTrue(all(row["external_id"].startswith("LOG-") for row in rows))

    def test_ensure_default_subject_command_assigns_legacy_missions(self):
        mission = self.create_mission("SUBJECT_LEGACY", subject=None)
        out = StringIO()

        call_command("ensure_default_subject", stdout=out)
        mission.refresh_from_db()

        self.assertEqual(mission.subject.code, DEFAULT_SUBJECT_CODE)
        self.assertTrue(Subject.objects.filter(code=DEFAULT_SUBJECT_CODE).exists())
        self.assertIn("Default subject ready", out.getvalue())

    def test_usable_missions_filters_by_default_subject(self):
        default_subject = get_default_subject()
        other_subject = Subject.objects.create(code="sqld", name="SQLD")
        default_mission = self.create_mission("SUBJECT_DEFAULT", subject=default_subject)
        self.create_mission("SUBJECT_SQLD", subject=other_subject)

        missions = list(usable_missions())

        self.assertIn(default_mission, missions)
        self.assertTrue(all(mission.subject_id == default_subject.id for mission in missions))

    def test_mission_list_works_with_default_subject(self):
        subject = get_default_subject()
        self.create_mission("SUBJECT_HOME", subject=subject)
        user = User.objects.create_user(username="learner", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)

    def test_mission_list_sets_default_subject_when_session_is_empty(self):
        subject = get_default_subject()
        self.create_mission("SUBJECT_HOME_FALLBACK", subject=subject)
        user = User.objects.create_user(username="fallback", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[CURRENT_SUBJECT_SESSION_KEY], subject.code)

    def test_seed_subjects_command_creates_logistics_subject(self):
        out = StringIO()

        call_command("seed_subjects", stdout=out)

        self.assertTrue(
            Subject.objects.filter(
                code=LOGISTICS_SUBJECT_CODE,
                is_active=True,
            ).exists()
        )
        self.assertIn("logistics", out.getvalue())

    def test_logistics_subject_without_missions_does_not_break_mission_list(self):
        seed_platform_subjects()
        user = User.objects.create_user(username="logistics", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)

    def test_logistics_curriculum_has_five_courses_and_27_chapters(self):
        curriculum = get_logistics_curriculum()

        self.assertEqual(len(curriculum), 5)
        self.assertEqual(
            sum(len(course["chapters"]) for course in curriculum),
            28,
        )
        self.assertEqual(curriculum[0]["course"], "물류관리론")
        self.assertEqual(curriculum[0]["chapters"][0]["chapter_code"], "LM01")
        self.assertEqual(curriculum[0]["chapters"][0]["display_no"], "01")
        self.assertEqual(curriculum[1]["chapters"][0]["chapter_code"], "TR01")
        self.assertEqual(curriculum[1]["chapters"][0]["display_no"], "01")
        self.assertEqual(curriculum[-1]["chapters"][-1]["chapter_code"], "LW07")

    def test_logistics_roadmap_includes_empty_chapters(self):
        seed_platform_subjects()
        subject = Subject.objects.get(code=LOGISTICS_SUBJECT_CODE)
        user = User.objects.create_user(username="roadmap_empty", password="pass12345")

        roadmap = build_logistics_chapter_roadmap(user, subject)

        self.assertEqual(len(roadmap), 5)
        self.assertEqual(sum(len(course["chapters"]) for course in roadmap), 28)
        lm01 = roadmap[0]["chapters"][0]
        self.assertEqual(lm01["chapter_code"], "LM01")
        self.assertEqual(lm01["display_no"], "01")
        self.assertEqual(lm01["total_count"], 0)
        self.assertEqual(lm01["status"], "문제 준비 중")
        tr01 = roadmap[1]["chapters"][0]
        self.assertEqual(tr01["chapter_code"], "TR01")
        self.assertEqual(tr01["display_no"], "01")

    def test_logistics_roadmap_counts_existing_chapter_missions(self):
        mission = self.create_logistics_mission()
        user = User.objects.create_user(username="roadmap_counts", password="pass12345")
        Attempt.objects.create(user=user, mission=mission, is_correct=True)

        roadmap = build_logistics_chapter_roadmap(user, mission.subject)
        lm01 = roadmap[0]["chapters"][0]

        self.assertEqual(lm01["total_count"], 1)
        self.assertEqual(lm01["attempted_count"], 1)
        self.assertEqual(lm01["solved_count"], 1)
        self.assertEqual(lm01["status"], "완료")

    def test_mission_list_uses_logistics_chapter_roadmap_for_logistics_subject(self):
        self.create_logistics_mission()
        user = User.objects.create_user(username="logistics_roadmap", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_logistics_subject"])
        self.assertEqual(len(response.context["logistics_chapter_roadmap"]), 5)
        self.assertContains(response, "물류관리사 학습 로드맵")
        self.assertContains(response, "01. 물류관리 일반")
        self.assertContains(response, "02. 물류시스템 구축")
        self.assertNotContains(response, "LM01 물류관리 일반")
        self.assertNotContains(response, "TR03")
        self.assertNotContains(response, "IL02")

    def test_mission_list_keeps_learning_type_roadmap_for_default_subject(self):
        subject = get_default_subject()
        self.create_mission("DEFAULT_ROADMAP_001", subject=subject)
        user = User.objects.create_user(username="default_roadmap", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = DEFAULT_SUBJECT_CODE
        session.save()

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["is_logistics_subject"])
        self.assertIn("learning_roadmap", response.context)
        self.assertContains(response, "함수별로 기능 선택")

    def test_logistics_subject_does_not_show_default_subject_mission(self):
        seed_platform_subjects()
        default_subject = get_default_subject()
        self.create_mission("SUBJECT_DEFAULT_ONLY", subject=default_subject)
        user = User.objects.create_user(username="logistics_only", password="pass12345")
        self.client.force_login(user)
        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()

        response = self.client.get(reverse("mission_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "SUBJECT_DEFAULT_ONLY title")

    def test_import_missions_reads_standard_logistics_external_id_schema(self):
        seed_platform_subjects()

        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_csv(tmpdir, [
                ",".join(LOGISTICS_STANDARD_COLUMNS),
                "LOG-IL02-0001,logistics,국제물류론,IL02,무역실무,중,무역조건 비용 판단,[CONTEXT] CIF 조건 [QUESTION] 매도인 부담 항목은?,1|운임|2|보험료,2,CIF 조건 설명,result,choice_one,none,LOGISTICS_INCOTERMS,LOG-IL02",
            ])

            out = StringIO()
            call_command("import_missions", str(csv_path), stdout=out)

        mission = Mission.objects.get(external_id="LOG-IL02-0001")
        self.assertEqual(mission.subject.code, LOGISTICS_SUBJECT_CODE)
        self.assertEqual(mission.course, "국제물류론")
        self.assertEqual(mission.chapter_code, "IL02")
        self.assertEqual(mission.chapter_name, "무역실무")
        self.assertEqual(mission.difficulty, "중")
        self.assertEqual(mission.skill, "IL02")
        self.assertEqual(mission.learning_type, "result")
        self.assertEqual(mission.question_type, "choice_one")
        self.assertEqual(mission.answer_input_type, "none")
        self.assertIn("created=1", out.getvalue())
        self.assertIn("skipped=0", out.getvalue())

    def test_import_missions_updates_duplicate_external_id(self):
        seed_platform_subjects()

        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_csv(tmpdir, [
                ",".join(LOGISTICS_STANDARD_COLUMNS),
                "LOG-LM01-0001,logistics,물류관리론,LM01,물류관리 일반,하,첫 제목,[CONTEXT] 물류관리 [QUESTION] 목적은?,1|비용|2|서비스,2,첫 설명,result,choice_one,none,LOGISTICS_BASIC,LOG-LM01",
            ])
            call_command("import_missions", str(csv_path), stdout=StringIO())

            csv_path = self.write_csv(tmpdir, [
                ",".join(LOGISTICS_STANDARD_COLUMNS),
                "LOG-LM01-0001,logistics,물류관리론,LM01,물류관리 일반,하,수정된 제목,[CONTEXT] 물류관리 [QUESTION] 목적은?,1|비용|2|서비스,2,수정된 설명,result,choice_one,none,LOGISTICS_BASIC,LOG-LM01",
            ])
            out = StringIO()
            call_command("import_missions", str(csv_path), stdout=out)

        mission = Mission.objects.get(external_id="LOG-LM01-0001")
        self.assertEqual(mission.title, "수정된 제목")
        self.assertIn("updated=1", out.getvalue())

    def test_import_missions_without_subject_code_uses_default_subject(self):
        default_subject = get_default_subject()

        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_csv(tmpdir, [
                "id,title,skill_auto,level,prompt,correct_answer,explanation",
                "LEGACY_IMPORT_001,기존 CSV 확인,COUNT,1,기존 CSV도 동작해야 합니다,1,기존 CSV 설명",
            ])

            call_command("import_missions", str(csv_path), stdout=StringIO())

        mission = Mission.objects.get(external_id="LEGACY_IMPORT_001")
        self.assertEqual(mission.subject_id, default_subject.id)
        self.assertEqual(mission.course, "")
        self.assertEqual(mission.chapter_code, "")
        self.assertEqual(mission.difficulty, "")

    def test_import_missions_skips_invalid_difficulty(self):
        seed_platform_subjects()

        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_csv(tmpdir, [
                ",".join(LOGISTICS_STANDARD_COLUMNS),
                "LOG-LM01-9999,logistics,물류관리론,LM01,물류관리 일반,특상,잘못된 난이도,[CONTEXT] 테스트 [QUESTION] 테스트,1|정답,1,스킵되어야 합니다,result,choice_one,none,LOGISTICS_BASIC,LOG-LM01",
            ])

            out = StringIO()
            call_command("import_missions", str(csv_path), stdout=out)

        self.assertFalse(Mission.objects.filter(external_id="LOG-LM01-9999").exists())
        self.assertIn("SKIP invalid difficulty", out.getvalue())
        self.assertIn("skipped=1", out.getvalue())

    def test_imported_logistics_mission_is_only_visible_on_logistics_home(self):
        seed_platform_subjects()

        with TemporaryDirectory() as tmpdir:
            csv_path = self.write_csv(tmpdir, [
                ",".join(LOGISTICS_STANDARD_COLUMNS),
                "LOG-LM01-0002,logistics,물류관리론,LM01,물류관리 일반,하,물류관리사 전용 테스트 문제,[CONTEXT] 물류관리 [QUESTION] 목적은?,1|비용|2|서비스,2,물류관리사 전용 설명,result,choice_one,none,LOGISTICS_BASIC,LOG-LM01",
            ])
            call_command("import_missions", str(csv_path), stdout=StringIO())

        user = User.objects.create_user(username="subject_screen", password="pass12345")
        self.client.force_login(user)

        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = LOGISTICS_SUBJECT_CODE
        session.save()
        logistics_response = self.client.get(reverse("mission_list"))

        session = self.client.session
        session[CURRENT_SUBJECT_SESSION_KEY] = DEFAULT_SUBJECT_CODE
        session.save()
        default_response = self.client.get(reverse("mission_list"))

        self.assertContains(logistics_response, "목적은?")
        self.assertNotContains(logistics_response, "물류관리사 전용 테스트 문제")
        self.assertNotContains(default_response, "목적은?")
