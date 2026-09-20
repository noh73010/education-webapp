from django.db import migrations


CURRICULUM = [
    ("물류관리론", [("LM01", "물류관리총론"), ("LM02", "물류경영"),
      ("LM03", "물류표준화와 물류공동화"), ("LM04", "물류정보화(정보시스템)"),
      ("LM05", "물류비 회계"), ("LM06", "공급사슬관리(SCM)"),
      ("LM07", "친환경 녹색물류와 물류포장"), ("LM08", "물류아웃소싱과 물류보안")]),
    ("화물운송론", [("FT01", "화물운송의 기초"), ("FT02", "공로운송"),
      ("FT03", "철도운송"), ("FT04", "해상운송"), ("FT05", "항공운송"),
      ("FT06", "국제복합운송"), ("FT07", "유닛로드시스템(ULS)"),
      ("FT08", "수·배송시스템의 합리화")]),
    ("국제물류론", [("IT01", "국제물류 총론"), ("IT02", "국제해상운송"),
      ("IT03", "국제항공운송"), ("IT04", "국제복합운송 및 국제물류보안")]),
    ("보관하역론", [("BH01", "보관 및 창고의 기초개념"),
      ("BH02", "물류시설과 창고관리시스템"), ("BH03", "물류시설의 계획 및 운영"),
      ("BH04", "재고관리시스템"), ("BH05", "하역의 이해"),
      ("BH06", "하역운반장비"), ("BH07", "유닛로드시스템과 포장"),
      ("BH08", "운송수단별 하역방식")]),
    ("물류관련법규", [("LR01", "물류정책기본법"),
      ("LR02", "물류시설의 개발 및 운영에 관한 법률"),
      ("LR03", "화물자동차 운수사업법"), ("LR04", "철도사업법"),
      ("LR05", "항만운송사업법"), ("LR06", "유통산업발전법"),
      ("LR07", "농수산물 유통 및 가격안정에 관한 법률")]),
]
PREFIX_MAP = {"TR": "FT", "IL": "IT", "WH": "BH", "LW": "LR"}


def correct_logistics_curriculum(apps, schema_editor):
    Subject = apps.get_model("core", "Subject")
    Mission = apps.get_model("core", "Mission")
    WrongPattern = apps.get_model("core", "WrongPattern")
    CertificationPolicy = apps.get_model("core", "CertificationPolicy")
    CertificationArea = apps.get_model("core", "CertificationArea")
    logistics = Subject.objects.filter(code="logistics").first()
    if not logistics:
        return

    names = {code: (course, name) for course, chapters in CURRICULUM for code, name in chapters}
    for mission in Mission.objects.filter(subject=logistics).iterator():
        old_code = (mission.chapter_code or "").upper()
        new_code = PREFIX_MAP.get(old_code[:2], old_code[:2]) + old_code[2:] if old_code else ""
        if new_code in names:
            course, name = names[new_code]
            mission.chapter_code = new_code
            mission.chapter_name = name
            mission.course = course
            mission.skill = new_code
            mission.wrong_pattern_code = f"LOGISTICS_{new_code}"
            mission.variation_group = f"LOGISTICS_{new_code}"
            mission.save(update_fields=[
                "chapter_code", "chapter_name", "course", "skill",
                "wrong_pattern_code", "variation_group",
            ])

    for old_prefix, new_prefix in PREFIX_MAP.items():
        for pattern in WrongPattern.objects.filter(
            subject=logistics, code__startswith=f"LOGISTICS_{old_prefix}"
        ):
            new_code = pattern.code.replace(f"LOGISTICS_{old_prefix}", f"LOGISTICS_{new_prefix}", 1)
            if not WrongPattern.objects.filter(subject=logistics, code=new_code).exists():
                pattern.code = new_code
                pattern.skill = pattern.skill.replace(old_prefix, new_prefix, 1)
                pattern.save(update_fields=["code", "skill"])

    for course, chapters in CURRICULUM:
        for chapter_code, chapter_name in chapters:
            WrongPattern.objects.update_or_create(
                subject=logistics, code=f"LOGISTICS_{chapter_code}",
                defaults={
                    "name": f"{chapter_name} 핵심 개념 혼동", "skill": chapter_code,
                    "description": f"{course}의 {chapter_name}에서 반복되는 개념 오답",
                    "minimum_evidence": 2,
                    "remediation_message": f"{chapter_name} 핵심 개념을 비교·구분한 뒤 변형 문제로 재평가합니다.",
                },
            )

    policy = CertificationPolicy.objects.filter(subject=logistics).first()
    if policy:
        CertificationArea.objects.filter(policy=policy).delete()
        for order, (course, chapters) in enumerate(CURRICULUM, start=1):
            prefix = chapters[0][0][:2]
            CertificationArea.objects.create(
                policy=policy, code=prefix, name=course, course=course,
                chapter_prefix=prefix, weight=20, passing_floor=40, order=order,
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0035_certificationarea_certificationpolicy_userweakness_and_more")]
    operations = [migrations.RunPython(correct_logistics_curriculum, migrations.RunPython.noop)]
