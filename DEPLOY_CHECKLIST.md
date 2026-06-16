# Deploy Checklist

이 프로젝트는 Django 기반 컴활 2급 학습 서비스다. Render 배포 전에는 기능 추가보다 환경변수, DB, 정적 파일, migration, smoke check를 먼저 확인한다.

## Render 배포 요약

Render Web Service 설정:

- Build Command:
  ```bash
  pip install -r requirements.txt && python manage.py collectstatic --noinput
  ```
- Start Command:
  ```bash
  gunicorn myproject.wsgi:application
  ```
- `Procfile`도 같은 start command를 사용한다.
- `render.yaml`을 사용할 경우 PostgreSQL과 Web Service를 Blueprint로 생성할 수 있다.

## 필수 환경변수

Render Dashboard > Environment에 등록한다.

```text
DJANGO_SECRET_KEY=실제_운영용_긴_비밀키
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=your-service-name.onrender.com,your-custom-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-service-name.onrender.com,https://your-custom-domain.com
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SESSION_COOKIE_SECURE=1
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SECURE_PROXY_SSL_HEADER=1
DATABASE_URL=Render PostgreSQL 연결 문자열
```

주의:

- `DEBUG=0`은 운영 배포에서 필수다.
- `DJANGO_SECRET_KEY`는 예시값이 아닌 실제 운영용 비밀키를 사용한다.
- `DJANGO_ALLOWED_HOSTS`에는 Render 도메인과 실제 커스텀 도메인을 모두 넣는다.
- `DJANGO_CSRF_TRUSTED_ORIGINS`에는 반드시 `https://`를 포함한 origin을 넣는다.
- 운영에서는 `python manage.py runserver`를 사용하지 않는다.

## Render 배포 순서

1. GitHub에 프로젝트를 push한다.

2. Render에서 PostgreSQL을 생성한다.

3. Render에서 Web Service를 생성하고 GitHub 저장소를 연결한다.

4. Build Command를 설정한다.

   ```bash
   pip install -r requirements.txt && python manage.py collectstatic --noinput
   ```

5. Start Command를 설정한다.

   ```bash
   gunicorn myproject.wsgi:application
   ```

6. 환경변수를 등록한다.

7. PostgreSQL의 `DATABASE_URL`을 Web Service 환경변수에 연결한다.

8. 첫 배포를 실행한다.

9. Render Shell에서 migration을 적용한다.

   ```bash
   python manage.py migrate
   ```

10. 관리자 계정을 생성한다.

    ```bash
    python manage.py createsuperuser
    ```

11. 실전형 문제가 부족하면 seed를 실행한다.

    ```bash
    python manage.py seed_practical_missions
    python manage.py apply_mission_quality
    ```

12. smoke check를 실행한다.

    ```bash
    python manage.py smoke_check
    ```

13. 가능하면 테스트도 실행한다.

    ```bash
    python manage.py test core.tests
    ```

## 로컬 배포 전 검증

로컬에서 최소한 아래 명령을 통과시킨 뒤 push한다.

```powershell
py -3 manage.py check
py -3 manage.py test core.tests
py -3 manage.py smoke_check
```

운영 설정에 가까운 check:

```powershell
$env:DJANGO_DEBUG='0'
$env:DJANGO_SECRET_KEY='temporary-local-check-secret'
$env:DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1'
$env:DJANGO_CSRF_TRUSTED_ORIGINS='https://example.com'
py -3 manage.py check
```

## 배포 후 확인 URL

브라우저에서 아래 URL을 직접 확인한다.

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

확인 기준:

- `/` 랜딩 페이지가 정상 표시된다.
- `/signup/` 회원가입이 가능하다.
- `/login/` 로그인이 가능하다.
- `/missions/`는 로그인 후 학습 홈이 정상 표시된다.
- `/stats/`, `/problem-sets/`가 오류 없이 열린다.
- `/premium/`에 무료/프리미엄 안내가 표시된다.
- `/inquiry/`에서 프리미엄 신청/문의 제출이 가능하다.
- `/admin-dashboard/`는 staff 계정만 접근 가능하다.
- `/admin/`에서 관리자 로그인이 가능하다.

## 무료/프리미엄 운영 확인

무료 계정:

- 오답노트가 최근 5개 제한으로 보이는지 확인한다.
- 패턴 집중 훈련을 하루 2회 시도하면 제한 안내가 나오는지 확인한다.
- 실전 모의고사를 하루 2회 시도하면 제한 안내가 나오는지 확인한다.
- 시험 결과 상세 약점 분석이 제한되는지 확인한다.

프리미엄 계정:

- 오답노트 전체가 보이는지 확인한다.
- 패턴 집중 훈련 제한이 완화되는지 확인한다.
- 실전 모의고사 제한이 완화되는지 확인한다.
- 시험 결과 상세 약점 분석이 보이는지 확인한다.

## 수동 프리미엄 부여

1. staff 계정으로 `/admin/`에 로그인한다.
2. `Core > User accesses`로 이동한다.
3. username으로 사용자를 검색한다.
4. 대상 `UserAccess` row를 선택한다.
5. admin action `선택 사용자 30일 프리미엄 부여`를 실행한다.
6. `is_premium=True`, `premium_started_at`, `premium_ended_at`을 확인한다.
7. 해제가 필요하면 admin action `선택 사용자 프리미엄 해제`를 실행한다.

## DB 안전 수칙

- migration, seed, 품질 적용 command 실행 전 DB를 백업한다.
- Render PostgreSQL은 운영 DB이므로 seed나 품질 command 실행 전 대상 환경을 반드시 확인한다.
- `seed_practical_missions`는 practical 문제를 추가/갱신한다.
- `apply_mission_quality`는 Mission을 삭제하지 않지만 품질 등급과 사용 가능 여부를 갱신한다.
- 삭제성 cleanup command는 백업 없이 실행하지 않는다.
