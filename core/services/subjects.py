from core.models import Mission, Subject


DEFAULT_SUBJECT_CODE = "comhwal2"
DEFAULT_SUBJECT_NAME = "컴활 2급"
DEFAULT_SUBJECT_DESCRIPTION = "컴퓨터활용능력 2급 실기/필기 대비 학습"
LOGISTICS_SUBJECT_CODE = "logistics"
LOGISTICS_SUBJECT_NAME = "물류관리사"
LOGISTICS_SUBJECT_DESCRIPTION = "물류관리사 자격시험 대비 학습"
CURRENT_SUBJECT_SESSION_KEY = "current_subject_code"


def get_default_subject():
    subject, _ = Subject.objects.get_or_create(
        code=DEFAULT_SUBJECT_CODE,
        defaults={
            "name": DEFAULT_SUBJECT_NAME,
            "description": DEFAULT_SUBJECT_DESCRIPTION,
            "is_active": True,
        },
    )
    return subject


def ensure_default_subject_assignments():
    subject = get_default_subject()
    updated_count = Mission.objects.filter(subject__isnull=True).update(subject=subject)
    return subject, updated_count


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
    default_subject = get_default_subject()
    logistics_subject = ensure_logistics_subject()
    return [default_subject, logistics_subject]


def get_active_subjects():
    subjects = list(Subject.objects.filter(is_active=True).order_by("name", "code"))
    if subjects:
        return subjects
    return [get_default_subject()]


def resolve_subject(subject=None):
    if subject is None:
        return get_default_subject()

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

    default_subject = Subject.objects.filter(
        code=DEFAULT_SUBJECT_CODE,
        is_active=True,
    ).first()
    active_subject = Subject.objects.filter(is_active=True).order_by("name", "code").first()
    subject = default_subject or active_subject or get_default_subject()
    request.session[CURRENT_SUBJECT_SESSION_KEY] = subject.code
    request.session.modified = True
    return subject, True
