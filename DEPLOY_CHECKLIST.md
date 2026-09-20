# Deploy Checklist

자격증 학습 시스템을 Render에 배포하기 전 확인할 항목입니다.

## Render 배포 설정

초기 공개 운영의 기본 비용 구성은 `render.yaml`에 다음처럼 고정한다.

- Web Service: `free` (15분 미사용 시 절전)
- PostgreSQL: `0.1c-256mb` 유료 플랜
- PostgreSQL 저장공간: 1GB
- 2026-09 공식 가격 기준 예상 비용: 월 $6.25부터(환율·세금·초과 사용량 별도)

무료 PostgreSQL은 30일 후 만료되어 회원 학습 기록을 보존할 수 없으므로 운영에 사용하지 않는다. 사용자 증가나 첫 접속 지연 문제가 확인되면 Web Service만 `0.5c-512mb` 유료 플랜으로 올린다.

Render Web Service 설정:

```bash
Build Command: pip install -r requirements.txt && python manage.py collectstatic --noinput
Start Command: sh scripts/render_start.sh
```

`render.yaml`을 사용할 경우 위 설정과 PostgreSQL 연결이 함께 적용됩니다. 시작 스크립트는 migration을 먼저 적용한 뒤 생성 문제를 동기화하고 Gunicorn을 실행합니다. migration 실패는 배포를 중단하지만, 문제 파일 동기화 실패는 경고를 남기고 기존 DB 내용으로 서버를 시작합니다.

## generated 문제 동기화

`generated/<subject-code>/`에 추가한 CSV는 웹 요청이나 `AppConfig.ready()`에서 가져오지 않습니다. 로컬에서는 파일을 추가한 뒤 다음 명령을 명시적으로 실행합니다.

```powershell
py -3 manage.py sync_generated_missions --subject-code logistics --create-problem-sets
```

실제 DB를 바꾸기 전에 확인하려면 `--dry-run`을 추가합니다. CI처럼 한 파일의 오류도 실패 코드로 처리해야 하는 환경에서는 `--fail-on-error`를 추가합니다.

```powershell
py -3 manage.py sync_generated_missions --subject-code logistics --create-problem-sets --dry-run
py -3 manage.py sync_generated_missions --subject-code logistics --create-problem-sets --fail-on-error
```

명령은 기존 `import_missions`를 재사용하고 파일별로 실패를 격리합니다. 각 파일 및 전체 요약에 `created`, `updated`, `skipped`, `errors`가 표시되며, 같은 파일을 다시 실행해도 중복 Mission을 만들지 않습니다. 새 자격증은 해당 `Subject.code`와 같은 하위 폴더를 만든 뒤 `--subject-code`만 바꿔 실행합니다.

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
NAVER_OAUTH_CLIENT_ID=네이버_개발자센터에서_발급한_Client_ID
NAVER_OAUTH_CLIENT_SECRET=네이버_개발자센터에서_발급한_Client_Secret
GOOGLE_OAUTH_CLIENT_ID=Google_Cloud에서_발급한_Client_ID
GOOGLE_OAUTH_CLIENT_SECRET=Google_Cloud에서_발급한_Client_Secret
```

주의:

- `DJANGO_DEBUG=0`은 운영 배포에서 필수입니다.
- `DJANGO_SECRET_KEY`는 예시값이 아닌 실제 운영용 비밀키를 사용합니다.
- `DJANGO_ALLOWED_HOSTS`에는 Render 도메인과 실제 연결 도메인을 모두 넣습니다.
- `DJANGO_CSRF_TRUSTED_ORIGINS`에는 `https://`를 포함한 origin을 넣습니다.
- 운영에서는 `python manage.py runserver`를 사용하지 않습니다.

## 네이버 로그인 설정

- 자격 증명은 코드나 Git에 저장하지 않고 로컬 `.env`와 Render Dashboard의
  Environment에만 `NAVER_OAUTH_CLIENT_ID`, `NAVER_OAUTH_CLIENT_SECRET` 이름으로
  등록합니다.
- 로컬 개발의 서비스 URL은 `http://127.0.0.1:8888`, Callback URL은
  `http://127.0.0.1:8888/accounts/naver/login/callback/`입니다.
- 현재 Render 서비스의 Callback URL은
  `https://comhal-study.onrender.com/accounts/naver/login/callback/`입니다.
- 네이버 개발자센터의 애플리케이션 > API 설정에서 `PC 웹` 환경을 추가하고,
  실제로 사용할 서비스 URL과 Callback URL을 문자 단위로 동일하게 등록합니다.
  프로토콜, 호스트, 포트, 마지막 `/`가 달라지지 않게 주의합니다.
- 환경변수를 추가하거나 변경한 뒤에는 Django 프로세스를 다시 시작합니다.
  설정이 완전한 provider만 로그인/회원가입 화면에 표시됩니다.

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
6. `scripts/render_start.sh`가 시작 시 migration과 생성 문제 동기화를 실행했는지 Render 로그에서 확인합니다. 수동 확인 또는 재실행은 다음 명령을 사용합니다.

```bash
python manage.py migrate
python manage.py sync_generated_missions --subject-code logistics --create-problem-sets
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
