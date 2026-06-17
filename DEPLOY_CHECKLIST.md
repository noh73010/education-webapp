# Deploy Checklist

컴활 2급 실전형 학습 시스템을 Render에 배포하기 전 확인할 항목입니다.

## Render 배포 설정

Render Web Service 설정:

```bash
Build Command: pip install -r requirements.txt && python manage.py collectstatic --noinput
Start Command: gunicorn myproject.wsgi:application
```

`render.yaml`을 사용할 경우 위 설정과 PostgreSQL 연결이 함께 적용됩니다.

## 필수 환경변수

Render Dashboard > Environment에 등록합니다.

```text
DJANGO_SECRET_KEY=실제_운영용_긴_비밀키
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-service-name.onrender.com,your-custom-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-service-name.onrender.com,https://your-custom-domain.com
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SECURE_PROXY_SSL_HEADER=1
DJANGO_WHITENOISE_MANIFEST_STRICT=0
DATABASE_URL=Render PostgreSQL 연결 문자열
```

주의:

- `DJANGO_DEBUG=0`은 운영 배포에서 필수입니다.
- `DJANGO_SECRET_KEY`는 예시값이 아닌 실제 운영용 비밀키를 사용합니다.
- `DJANGO_ALLOWED_HOSTS`에는 Render 도메인과 실제 연결 도메인을 모두 넣습니다.
- `DJANGO_CSRF_TRUSTED_ORIGINS`에는 `https://`를 포함한 origin을 넣습니다.
- 운영에서는 `python manage.py runserver`를 사용하지 않습니다.

## Static Files 확인

Render의 WhiteNoise + Manifest static storage 환경에서는 배포 빌드 중 `collectstatic`이 반드시 실행되어야 합니다.

확인 명령:

```bash
python manage.py findstatic core/style.css --verbosity 2
python manage.py collectstatic --noinput
```

`ValueError: Missing staticfiles manifest entry for 'core/style.css'`가 발생하면 다음을 확인합니다.

- `core/static/core/style.css` 파일이 존재하는지 확인
- Build Command에 `python manage.py collectstatic --noinput`이 포함되어 있는지 확인
- Render에서 Clear build cache 후 재배포
- `DJANGO_WHITENOISE_MANIFEST_STRICT=0` 환경변수가 등록되어 있는지 확인

## 배포 순서

1. GitHub에 프로젝트를 push합니다.
2. Render에서 PostgreSQL을 생성합니다.
3. Render에서 Web Service를 만들고 GitHub 저장소를 연결합니다.
4. 환경변수를 등록합니다.
5. 첫 배포를 실행합니다.
6. Render Shell에서 migration을 적용합니다.

```bash
python manage.py migrate
```

7. 관리자 계정을 생성합니다.

```bash
python manage.py createsuperuser
```

8. 실전형 문제가 부족하면 seed와 품질 적용 명령을 실행합니다.

```bash
python manage.py seed_practical_missions
python manage.py apply_mission_quality
```

9. smoke check를 실행합니다.

```bash
python manage.py smoke_check
```

10. 가능하면 테스트도 실행합니다.

```bash
python manage.py test core.tests
```

## 로컬 검증

push 전 최소 확인:

```powershell
py -3 manage.py check
py -3 manage.py test core.tests
py -3 manage.py smoke_check
```

운영 설정에 가까운 정적파일 확인:

```powershell
$env:DJANGO_DEBUG='0'
$env:DJANGO_SECRET_KEY='temporary-local-check-secret'
$env:DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1'
$env:DJANGO_CSRF_TRUSTED_ORIGINS='https://example.com'
py -3 manage.py collectstatic --noinput
py -3 manage.py check
```

## 배포 후 확인 URL

브라우저에서 직접 확인합니다.

- `/`
- `/signup/`
- `/login/`
- `/missions/`
- `/stats/`
- `/problem-sets/`
- `/premium/`
- `/inquiry/`
- `/admin-dashboard/`
- `/admin/`

## 무료/프리미엄 운영 확인

무료 계정:

- 오답노트가 최근 5개 제한으로 보이는지 확인합니다.
- 패턴 집중 훈련을 하루 2회 시도하면 제한 안내가 나오는지 확인합니다.
- 실전 모의고사를 하루 2회 시도하면 제한 안내가 나오는지 확인합니다.
- 시험 결과 상세 약점 분석이 제한되는지 확인합니다.

프리미엄 계정:

- 오답노트 전체가 보이는지 확인합니다.
- 패턴 집중 훈련 제한이 완화되는지 확인합니다.
- 실전 모의고사 제한이 완화되는지 확인합니다.
- 시험 결과 상세 약점 분석이 보이는지 확인합니다.

## 수동 프리미엄 부여

1. staff 계정으로 `/admin/`에 로그인합니다.
2. `Core > User accesses`로 이동합니다.
3. username으로 사용자를 검색합니다.
4. 대상 `UserAccess` row를 선택합니다.
5. admin action `선택 사용자 30일 프리미엄 부여`를 실행합니다.
6. `is_premium=True`, `premium_started_at`, `premium_ended_at`을 확인합니다.
7. 해제가 필요하면 admin action `선택 사용자 프리미엄 해제`를 실행합니다.

## DB 안전 수칙

- migration, seed, 품질 적용 command 실행 전 DB를 백업합니다.
- 운영 DB에서 seed나 품질 command를 실행하기 전 현재 데이터 상태를 확인합니다.
- `seed_practical_missions`는 practical 문제를 추가하거나 갱신합니다.
- `apply_mission_quality`는 Mission을 삭제하지 않고 품질 등급과 사용 가능 여부만 갱신합니다.
- 삭제성 cleanup command는 백업 없이 실행하지 않습니다.
