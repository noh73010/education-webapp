from core.models import Subject


LOGISTICS_SUBJECT_CODE = "logistics"
LOGISTICS_SUBJECT_NAME = "물류관리사"
LOGISTICS_SUBJECT_DESCRIPTION = "물류관리사 자격시험 대비 학습"
CURRENT_SUBJECT_SESSION_KEY = "current_subject_code"

# 이전 호출부 호환용 이름이다. 기본 진입은 물류관리사지만 새 자격증도
# Subject 레코드를 추가하는 동일한 방식으로 지원한다.
DEFAULT_SUBJECT_CODE = LOGISTICS_SUBJECT_CODE


def ensure_logistics_subject():
    subject, _ = Subject.objects.update_or_create(
        code=LOGISTICS_SUBJECT_CODE,
        defaults={
            "name": LOGISTICS_SUBJECT_NAME,
            "description": LOGISTICS_SUBJECT_DESCRIPTION,
            "is_active": True,
        },
    )
    return subject


def seed_platform_subjects():
    logistics_subject = ensure_logistics_subject()
    from core.services.weaknesses import ensure_subject_learning_configuration
    ensure_subject_learning_configuration(logistics_subject)
    return [logistics_subject]


def get_primary_subject():
    subject = Subject.objects.filter(
        code=LOGISTICS_SUBJECT_CODE, is_active=True,
    ).first()
    if subject:
        return subject
    subject = Subject.objects.filter(is_active=True).order_by("name", "code").first()
    return subject or ensure_logistics_subject()


# 제거 전 이름을 사용하는 내부 모듈을 위한 호환 별칭. 컴활2급은 생성하지 않는다.
get_default_subject = get_primary_subject


def get_active_subjects():
    subjects = list(Subject.objects.filter(is_active=True).order_by("name", "code"))
    return subjects or [ensure_logistics_subject()]


def resolve_subject(subject=None):
    if subject is None:
        return get_primary_subject()
    if isinstance(subject, Subject):
        return subject
    return Subject.objects.get(code=subject)


def set_current_subject(request, subject):
    subject = resolve_subject(subject)
    request.session[CURRENT_SUBJECT_SESSION_KEY] = subject.code
    request.session.modified = True
    return subject


def get_current_subject(request):
    subject_code = request.session.get(CURRENT_SUBJECT_SESSION_KEY)
    if subject_code:
        subject = Subject.objects.filter(code=subject_code, is_active=True).first()
        if subject:
            return subject, False

    subject = get_primary_subject()
    request.session[CURRENT_SUBJECT_SESSION_KEY] = subject.code
    request.session.modified = True
    return subject, True
