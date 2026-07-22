# PROJECT_CONTEXT.md

> AI 인수인계용 프로젝트 문서. 사람이 읽기 위한 README가 아니라, 다음 대화의 AI가 이 파일 하나만 읽고 개발을 이어받도록 작성한다.
> 기준일: 2026-07-22
> 프로젝트 루트: `C:\노세영\코딩\프로젝트\컴활2급`
> 현재 우선순위: 기존 `컴활2급(comhwal2)` 기능을 보존하면서 `물류관리사(logistics)` 과목 개발에 집중한다.

---

## 1. 프로젝트 개요

### 프로젝트 목적

Django 기반 자격증 학습 웹앱이다. 사용자는 과목을 선택한 뒤 문제 풀이, 일일 추천, 문제 세트, 모의시험, 오답노트, 통계, 패턴 훈련을 통해 반복 학습한다. 현재 하나의 서비스에서 `컴활 2급`과 `물류관리사`를 같이 운영하며, 지금 개발 초점은 물류관리사 과목이다.

### 서비스 대상

- 자격증 수험생: 현재 컴활2급, 물류관리사
- 운영자/관리자: Django Admin과 자체 admin dashboard에서 문제, 과목, 프리미엄 권한, 문의, 이벤트, 시험/세트 결과 관리

### 현재 개발 단계

- 단일 Django 앱 `core` 중심의 MVP/초기 운영 단계
- 회원가입, 로그인, 과목 선택, Mission 풀이, Daily 추천, ProblemSet, Exam, Wrong note, Stats, Inquiry, Premium 제한, Admin 기능 구현
- `Subject` 모델과 `Mission.subject`를 도입해 다과목 구조로 확장 중
- 물류관리사 전용 커리큘럼/챕터 로드맵이 코드 상수로 구현됨

### 향후 확장 계획

- `Subject`를 기준으로 자격증을 계속 추가
- 과목별 커리큘럼/로드맵 서비스 추가
- 물류관리사 CSV 변환/import 파이프라인 정식화
- 문제 세트/시험을 과목별로 더 명확히 격리
- 실제 결제 연동, 랭킹, 개인화 추천, 학습 리포트 추가 가능

### 지원 예정 자격증

현재 코드 기준:

- `comhwal2`: 컴활 2급, 기본/기존 과목
- `logistics`: 물류관리사, 현재 개발 집중 과목

향후 자격증 추가 시 `Subject(code=...)`를 만들고 모든 `Mission`에 subject를 연결해야 한다.

### 핵심 비즈니스 로직

- 모든 학습 콘텐츠의 중심은 `Mission`
- 사용자의 풀이 기록은 `Attempt`
- 과목 격리는 `Subject`와 세션 키 `current_subject_code`
- 문제 세트는 `ProblemSet`, `ProblemSetItem`, `ProblemSetSession`, `ProblemSetSessionItem`
- 모의시험은 `ExamSession`, `ExamSessionMission`
- 일일 추천은 `DailyMission`
- 오답은 `WrongReason` 수동 원인과 `WrongPattern` 자동 패턴으로 관리
- 무료/프리미엄 제한은 `UserAccess.is_premium`

---

## 2. 기술 스택

- Framework: Django
- Language: Python, Django Template HTML, CSS
- Database: 로컬 SQLite, 배포 PostgreSQL via `DATABASE_URL`
- 배포: Render Web Service + Render PostgreSQL
- 주요 라이브러리: `Django>=6.0,<6.1`, `dj-database-url`, `gunicorn`, `psycopg[binary]`, `whitenoise`
- 인증: Django 기본 auth, `LoginView`, `LogoutView`, `UserCreationForm`
- Static: WhiteNoise, `STATIC_ROOT = BASE_DIR / "staticfiles"`
- Media: 별도 `MEDIA_ROOT`/`MEDIA_URL` 없음

주의: `settings.py` 생성 주석은 Django 5.2.10을 언급하지만 `requirements.txt`는 Django 6.0을 요구한다. 실제 설치/배포 전 호환성 확인이 필요하다.

---

## 3. 프로젝트 구조

```text
컴활2급/
├─ active/                         # 현재 활성 CSV
├─ archive/                        # 과거 CSV 백업
├─ core/
│  ├─ admin.py                     # Django Admin 등록/액션
│  ├─ forms.py                     # InquiryForm
│  ├─ models.py                    # 전체 도메인 모델
│  ├─ management/commands/         # seed/import/품질/smoke 명령
│  ├─ migrations/                  # 0001~0034 migration
│  ├─ services/                    # 비즈니스 로직
│  ├─ static/core/style.css
│  ├─ static/images/questions/logistics/
│  ├─ templates/core/              # 주요 화면
│  ├─ templates/registration/      # login/signup
│  ├─ templatetags/
│  ├─ tests/                       # TestCase 테스트
│  └─ views/                       # FBV 화면 로직
├─ generated/
│  └─ logistics/                   # 물류관리사 원본 CSV
├─ myproject/
│  ├─ settings.py
│  ├─ urls.py
│  ├─ wsgi.py
│  └─ asgi.py
├─ scripts/                        # CSV/프롬프트 보조 스크립트
├─ staticfiles/                    # collectstatic 결과
├─ templates/                      # 404/500
├─ db.sqlite3
├─ DEPLOY_CHECKLIST.md
├─ manage.py
├─ Procfile
├─ render.yaml
└─ requirements.txt
```

### 앱 역할과 의존 관계

```text
myproject.urls
  -> core.views.*
      -> core.services.*
          -> core.models
      -> core.models
core.admin
  -> core.models
core.management.commands.*
  -> core.models, core.services.*
core.templates
  <- core.views context
```

현재 Django 앱은 사실상 `core` 하나이며, 여러 도메인을 내부 모듈로 나눈 구조다.

---

## 4. 데이터베이스 구조

### 주요 모델

#### Subject

과목/자격증 단위. `code`는 unique + db_index. 현재 핵심 코드는 `comhwal2`, `logistics`.

필드: `code`, `name`, `description`, `is_active`, `created_at`

#### Mission

문제/학습 단위의 중심 모델.

핵심 필드:

- `external_id`: unique, db_index. CSV import 기준키
- `subject`: `Subject` FK, `PROTECT`
- `course`, `chapter_code`, `chapter_name`: 물류관리사 로드맵 핵심
- `difficulty`
- `skill`, `level`
- `prompt`, `answer_key`
- `question_type`: `manual`, `short_answer`, `value_answer`, `choice_one`, `true_false`, `error_detect`
- `learning_type`: `result`, `feature`, `error`, `next_action`, `procedure`
- `answer_input_type`: `none`, `text`, `number`, `date`
- `correct_answer`, `explanation`, `answer_schema`
- `choice_explanations`: 선택지 번호를 key로 하는 선택지별 해설 JSON
- `concept_summary`: 해당 문제 풀이에 직접 필요한 검수된 핵심 개념
- `exam_tip`: 시험장에서 정답/오답을 구분하는 실전 팁
- `wrong_pattern_code`, `variation_group`
- `is_quality_checked`, `quality_level`, `is_usable_for_set`, `quality_note`

인덱스:

- `external_id` unique + db_index
- `(skill, level)`
- `(subject, course, chapter_code)`

#### Attempt

사용자 풀이 기록. `mission`은 `PROTECT`, `user`는 `CASCADE`.

필드: `user`, `mission`, `is_correct`, `time_spent_sec`, `submitted_answer`, `daily_date`, `created_at`

인덱스: `(user, mission, -created_at)`, `(user, -created_at)`, `(user, daily_date)`

#### DailyMission

사용자별 일일 추천 Mission 고정 저장. unique `(user, date, mission)`.

#### UserStreak

연속 학습일 기록. `user` OneToOne.

#### UserAccess

프리미엄 권한. `user` OneToOne, `is_premium`, 기간 필드.

#### WrongReason / AttemptWrongReason

수동 오답 원인 마스터와 Attempt 연결. `AttemptWrongReason` unique `(attempt, wrong_reason)`.

#### WrongPattern / AttemptWrongPattern

반복 오답 패턴과 Attempt 연결. `AttemptWrongPattern` unique `(attempt, wrong_pattern)`.

#### ProblemSet / ProblemSetItem

문제 세트와 포함 Mission. `ProblemSetItem` unique `(problem_set, order_no)`.

#### ProblemSetSession / ProblemSetSessionItem

사용자별 문제 세트 풀이 세션과 세션 내 Mission 상태. `ProblemSetSessionItem` unique `(problem_set_session, order_no)`.

#### ExamSession / ExamSessionMission

모의시험 세션과 시험 내 Mission. `ExamSessionMission` unique `(exam_session, order_no)`. `ExamSession.attempts_synced`로 Attempt 중복 반영 방지.

#### UserEvent

행동 로그. `event_type`, `page`, `metadata`, `created_at`. 인덱스 `(event_type, -created_at)`, `(user, -created_at)`.

#### Inquiry

문의/프리미엄 신청/버그 제보. `inquiry_type`, `status`, `created_at`, `updated_at`.

#### PatternTrainingSession

오답 패턴 집중 훈련 결과.

### ERD 텍스트

```text
User 1 ── 1 UserAccess
User 1 ── 1 UserStreak
User 1 ── N Attempt
User 1 ── N DailyMission
User 1 ── N ProblemSetSession
User 1 ── N ExamSession
User 1 ── N PatternTrainingSession
User 1 ── N UserEvent
User 1 ── N Inquiry

Subject 1 ── N Mission
Mission 1 ── N Attempt
Mission 1 ── N DailyMission
Mission 1 ── N ProblemSetItem
Mission 1 ── N ProblemSetSessionItem
Mission 1 ── N ExamSessionMission

Attempt 1 ── N AttemptWrongReason ── N WrongReason
Attempt 1 ── N AttemptWrongPattern ── N WrongPattern
WrongPattern 1 ── N PatternTrainingSession

ProblemSet 1 ── N ProblemSetItem ── N Mission
ProblemSet 1 ── N ProblemSetSession
ProblemSetSession 1 ── N ProblemSetSessionItem ── N Mission

ExamSession 1 ── N ExamSessionMission ── N Mission
```

### 향후 확장 포인트

- `ProblemSet`에 직접 `subject` FK 없음. 현재는 `items__mission__subject`로 필터링한다.
- `ExamSession`에 직접 `subject` FK 없음. 현재는 `items__mission__subject`로 필터링한다.
- 데이터가 커지면 두 모델에 `subject` FK 추가를 검토한다.
- 물류관리사 커리큘럼은 코드 상수라 관리자 수정 불가. 장기적으로 DB 모델화 가능.

---

## 5. URL 구조

```text
/                                  -> landing
/subjects/<str:subject_code>/       -> select_subject
/inquiry/                           -> inquiry
/inquiry/done/                      -> inquiry_done
/admin/                             -> Django admin
/admin-dashboard/                   -> admin_dashboard
/login/                             -> AnalyticsLoginView
/logout/                            -> LogoutView
/signup/                            -> signup
/missions/                          -> mission_list
/missions/<int:mission_id>/         -> mission_detail
/missions/learning-type/<skill>/<learning_type>/start/  -> learning_type_training_start
/missions/learning-type/<skill>/<learning_type>/result/ -> learning_type_training_result
/problem-sets/                      -> problem_set_list
/problem-sets/<int:set_id>/         -> problem_set_detail
/problem-sets/<int:set_id>/start/   -> problem_set_start
/problem-sets/result/<int:session_id>/ -> problem_set_result
/problem-sets/result/<int:session_id>/wrong-retry/ -> problem_set_wrong_retry
/problem-sets/result/<int:session_id>/wrong-retry/result/ -> problem_set_wrong_retry_result
/pattern-training/<str:pattern_code>/start/ -> pattern_training_start
/pattern-training/<str:pattern_code>/result/ -> pattern_training_result
/stats/                             -> stats
/wrong-notes/                       -> wrong_notes
/exam/                              -> exam_start
/exam/create/                       -> exam_create
/exam/<int:exam_id>/<int:order_no>/ -> exam_take
/exam/<int:exam_id>/submit/         -> exam_submit
/exam/<int:exam_id>/result/         -> exam_result
/exam/<int:exam_id>/recommend-start/ -> exam_recommend_start
/exam/history/                      -> exam_history
/premium/                           -> premium_info
```

공개 화면은 `/`, `/login/`, `/signup/`, `/inquiry/`, `/inquiry/done/`. 학습 관련 화면은 로그인 필요. `/admin-dashboard/`는 staff만 접근.

---

## 6. 화면 구조

- 첫 화면: `landing.html`, 과목 목록 표시 및 선택. 선택 시 세션에 `current_subject_code` 저장 후 `/missions/`.
- 로그인: `registration/login.html`, 로그인 성공 이벤트 기록.
- 회원가입: `registration/signup.html`, 가입 후 `UserAccess` 생성 및 자동 로그인.
- 대시보드/학습 홈: `mission_list.html`. 사실상 메인 대시보드. Mission 목록, daily 추천, 문제 세트 추천, streak, dashboard, 물류관리사 챕터 로드맵 또는 컴활 learning_type 로드맵 표시. 오늘 학습에는 총 문제 수, 예상 시간, `새 학습/오답 복습/약점 보완/실력 유지` 구성을 표시한다.
- 학습/문제 풀이: `mission_detail.html`. 일반 풀이, daily, problem set, wrong retry, pattern training, learning type training, exam review 흐름을 공유.
- 시험: `exam_start.html`, `exam_take.html`, `exam_result.html`, `exam_history.html`.
- 통계: `stats.html`.
- 오답노트: `wrong_notes.html`.
- 관리자: Django `/admin/`, 자체 `/admin-dashboard/`.
- 프리미엄: `premium_info.html`, 제한 안내 `premium_required.html`.
- 문의: `inquiry_form.html`, `inquiry_done.html`.

---

## 7. 핵심 서비스 로직

### 로그인 흐름

`AnalyticsLoginView.form_valid()` -> Django 로그인 처리 -> `record_event(user, "login", page="login")` -> `/missions/`.

### 과목 선택 흐름

`landing` POST 또는 `/subjects/<code>/` -> active Subject 확인 -> `set_current_subject()` -> 세션 `current_subject_code` 저장 -> `/missions/`.

### Subject 처리

`core/services/subjects.py`:

- `DEFAULT_SUBJECT_CODE = "comhwal2"`
- `LOGISTICS_SUBJECT_CODE = "logistics"`
- `get_current_subject(request)`가 현재 과목을 반환하고 세션이 비어 있으면 default subject를 저장한다.
- `seed_platform_subjects()`로 기본 과목과 물류관리사 과목 생성.
- `ensure_default_subject_assignments()`로 null subject Mission을 기본 과목에 연결.

### Mission 조회

- `mission_list`: 현재 과목 Mission만 조회. 검색(q), skill, level, sort 적용. Attempt annotation 후 페이지당 10개.
- `mission_detail`: `Mission(id=mission_id, subject=current_subject)`로 조회. 다른 과목 Mission 접근 차단.

### 추천 로직

Daily 추천:

- `get_or_create_daily_recommendations()`
- 오늘 추천이 있으면 재사용, reset이면 삭제 후 재생성
- `DailyMission`에 저장
- 기본 5문제
- subject가 있으면 반드시 subject 기준 필터
- 기존 학습 순서는 `미학습 챕터 -> 현재 챕터 문제 -> 약점 복습`을 유지한다.
- `build_daily_study_plan()`이 추천 문제의 선정 이유와 약 2분/문제 기준 예상 시간을 계산한다.
- `review_schedule.py`는 별도 상태 테이블 없이 최근 Attempt 3개를 이용해 복습 시점을 파생한다. 최근 오답은 다음 날, 오답 후 1회 정답은 3일 후 확인하고, 최근 연속 2회 정답은 숙련으로 본다.

Mission 추천:

- `get_recommended_missions()`
- 최근 20개 Attempt로 사용자 level 결정
- 약점 skill 우선
- 미시도 3개 + 약점 2개
- 날짜/user 기반 stable hash로 하루 동안 고정
- 복습 예정일이 지난 문제는 약점 후보 안에서 우선한다.

### 문제별 학습 피드백

`core/services/learning_feedback.py`를 일반 문제 결과와 문제세트 결과가 공유한다.

- 기본 해설과 사용자 답/정답 비교
- `Mission.choice_explanations`가 있으면 선택지별 해설 표시
- `Mission.concept_summary`가 있으면 키워드 규칙보다 우선하여 문제 전용 핵심 개념으로 표시
- `Mission.exam_tip`이 있으면 시험장에서 구분하는 법으로 표시
- 새 필드가 비어 있는 기존 문제는 기존 `explanation`과 `learning_concepts.py` 자동 연결을 사용하므로 하위 호환된다.

ProblemSet 추천:

- `get_problem_set_recommendations()`
- 최근 completed ProblemSetSession 평균 점수로 target level 결정
- today_sets, review_sets, weak_sets, weak_patterns, pattern_missions 반환

### 시험 생성

`create_exam_session(user, subject, total_questions=40)`:

- 현재 과목의 `is_usable_for_set=True` Mission 대상
- skill별 균등 선발 시도 후 부족분 보충
- 40문제 미만이면 `ValueError`
- `ExamSessionMission` bulk_create
- 제출/시간 만료/마지막 문제 후 `finish_exam_session()`
- 결과를 `sync_exam_to_attempts()`로 Attempt에 반영, `attempts_synced=True`로 중복 방지

### 오답 저장

일반 Mission 제출은 `save_attempt()`를 사용한다.

- DailyMission이면 `Attempt.daily_date` 저장
- 오답이면 `AttemptWrongReason` 연결 가능
- Mission의 `wrong_pattern_code`가 있으면 `WrongPattern` 찾아 `AttemptWrongPattern` 생성
- streak 업데이트

### 통계 계산

`stats`는 현재 과목 기준으로 Attempt를 조회한다.

- 기간 필터: all/7/30
- 누적 Attempt 통계
- 스킬별 정답률
- 오답 원인 TOP
- 오답 패턴 TOP
- Mission별 최신 Attempt 기준 현재 상태
- learning_type별 진행률

물류관리사 챕터 로드맵은 `build_logistics_chapter_roadmap()`에서 chapter_code별 total/attempted/solved를 계산한다.

---

## 8. 현재 구현 상태

### 구현 완료

- Django 기본 구조
- 회원가입/로그인/로그아웃
- UserEvent 기반 로그인/가입/학습/시험/패턴/문의 이벤트 기록
- Subject 모델과 과목 선택
- Mission subject/course/chapter/difficulty 확장
- Mission 목록/상세 풀이
- 자동채점/수동채점
- Attempt 저장, 오답 원인, 오답 패턴 연결
- Daily 5문제 추천
- 오늘 학습 구성/예상 시간/추천 이유 안내
- Attempt 기반 복습 시점 계산
- 선택지별 해설, 문제 전용 핵심 개념, 시험 팁 표시
- Streak
- ProblemSet 시작/결과/오답 재도전
- ProblemSet 추천
- PatternTraining
- Exam 생성/응시/제출/결과/기록
- Exam 결과 Attempt 동기화
- Stats
- Wrong notes
- Premium 권한 및 일부 무료 제한
- Inquiry
- Admin dashboard
- Django Admin 등록 및 UserAccess admin action
- Render 배포 설정
- smoke_check
- Subject/물류관리사 회귀 테스트
- 물류관리사 커리큘럼/챕터 로드맵

### 미구현/부분 구현

- 실제 결제 연동 없음
- `payments.py`는 URL에 연결되지 않은 것으로 보임
- 물류관리사 원본 CSV는 import 표준 컬럼과 다름
- 문제 이미지 처리/표시 규칙 자동화 미흡
- 물류관리사 ProblemSet 자동 생성 미검증
- `ProblemSet.subject`, `ExamSession.subject` 직접 FK 없음
- 한글 choice/label 문자열 일부 인코딩/표시 깨짐
- 랭킹 기능 placeholder
- Media 설정 없음

---

## 9. 수정 시 절대 건드리면 안 되는 부분

- `Subject.code`: `comhwal2`, `logistics`
- 세션 키: `current_subject_code`
- `Mission.external_id` unique 기준
- `Mission.subject` 기반 과목 격리
- `Mission.is_usable_for_set` 필터
- `save_attempt()`를 우회한 Attempt 저장 금지에 가깝게 관리
- `ExamSession.attempts_synced` 중복 방지
- `ProblemSetSession`/`ExamSession` 점수 계산
- `DailyMission` unique `(user, date, mission)`
- `Mission` 삭제보다 `is_usable_for_set=False` 우선

새 쿼리 작성 시 `Mission.objects...`가 나오면 현재 과목 필터가 필요한지 반드시 확인한다.

---

## 10. 개발 규칙

### 코드 스타일

- FBV 중심
- View는 request/session/template 흐름 담당
- 핵심 계산/저장은 `core/services/`
- 운영 명령은 `core/management/commands/`
- 회귀 위험이 있으면 `core/tests/`에 테스트 추가

### 네이밍

- Subject code는 lowercase ASCII 권장
- 물류관리사 Mission external_id는 `LOG-[A-Z]{2}\d{2}-\d{4}` 패턴
- 물류관리사 chapter_code 예: `LM01`, `TR01`, `IL01`, `WH01`, `LW01`
- question_type: `manual`, `short_answer`, `value_answer`, `choice_one`, `true_false`, `error_detect`
- learning_type: `result`, `feature`, `error`, `next_action`, `procedure`

### Subject 추가 방법

1. `Subject` 생성 또는 `subjects.py` seed 함수 확장.
2. `seed_platform_subjects()`에 포함.
3. 모든 CSV에 `subject_code` 추가.
4. 과목 전용 커리큘럼이 필요하면 service 추가.
5. 과목 선택/mission_list/통계/오답/시험/세트가 격리되는지 테스트.

### Mission 추가 방법

1. CSV 작성.
2. `subject_code` 명시.
3. `external_id`, `title`, `skill` 필수.
4. 자동채점이면 `question_type`, `answer_input_type`, `correct_answer`, `answer_schema` 확인.
5. `python manage.py import_missions <csv_path>`.
6. `python manage.py smoke_check`.

### CSV Import 규칙

`import_missions.py` 표준 컬럼:

```text
external_id 또는 id
subject_code
course
chapter_code
chapter_name
difficulty
title
prompt
answer_schema
correct_answer
explanation
learning_type
question_type
answer_input_type
wrong_pattern_code
variation_group
answer_key
skill_auto 또는 skill_group
level
choice_explanations(JSON) 또는 choice_1_explanation~choice_5_explanation
concept_summary
exam_tip
```

한글 물류관리사 CSV는 선택 컬럼 `보기1해설~보기5해설`, `핵심개념`, `시험팁`을 사용할 수 있다. 이 선택 컬럼이 CSV에 아예 없으면 기존 DB의 상세 피드백 값을 덮어쓰지 않는다.

- `subject_code`가 없으면 기본 과목 `comhwal2`로 들어간다.
- `subject_code=logistics`이면 external_id가 `LOG-[A-Z]{2}\d{2}-\d{4}`를 만족해야 한다.
- unknown subject_code, invalid difficulty, invalid logistics external_id는 skip.
- `번호,과목,챕터,난이도,문제,보기1~보기5,정답,해설` 형식의 한글 물류관리사 CSV도 직접 import한다.

### Migration 규칙

- 모델 변경 후 migration 생성.
- 운영 적용 전 DB 백업.
- Mission/Attempt/Session 관련 변경은 데이터 손실 위험이 크므로 특히 신중.
- `smoke_check`가 `0028_userevent`, `0030_subject_mission_subject`, `0034_mission_learning_feedback`, Inquiry migration 적용 여부를 확인한다.
- 최신 스키마 migration은 `0034_mission_learning_feedback`이다.

---

## 11. 관리 명령어

```bash
python manage.py seed_subjects
```

`comhwal2`, `logistics` Subject 생성/갱신.

```bash
python manage.py ensure_default_subject
```

기본 Subject 생성 및 subject null Mission을 default subject에 연결.

```bash
python manage.py import_missions <csv_path>
```

CSV를 `external_id` 기준으로 Mission 생성/갱신.

```bash
python manage.py smoke_check
```

DB, migration, env, URL reverse, template, Mission quality, Subject, staff user 상태 점검.

기타:

- `analytics_summary`: 사용자 행동 요약
- `apply_mission_quality`: Mission 품질 등급/사용 가능 여부 적용
- `audit_mission_quality`: 품질 의심 항목 출력, 데이터 변경 없음
- `classify_learning_types --dry-run`: learning_type 자동 분류
- `clean_mission_prompts`: prompt/explanation 정리
- `create_problem_sets`: 시나리오 Mission 기반 문제 세트 생성
- `create_wrong_patterns`: 기본 WrongPattern 생성
- `dedupe_missions`: `(title, skill)` 중복 제거. 운영 DB에서 백업 없이 실행 금지
- `mark_low_quality_missions`: 저품질 Mission을 세트에서 제외
- `seed_practical_missions`: 컴활 실전 Mission seed

---

## 12. 테스트

주요 테스트는 `core/tests/`에 있다.

- `test_admin_dashboard.py`: staff 접근 제어
- `test_analytics.py`: 이벤트 기록
- `test_exam_session.py`: 진행 중 시험 재개
- `test_inquiry.py`: 문의
- `test_landing.py`: 랜딩/과목 선택
- `test_signup.py`: 회원가입/UserAccess
- `test_smoke_check.py`: smoke_check
- `test_subjects.py`: Subject/물류관리사/CSV import/과목 격리 핵심
- `test_user_flow_links.py`: 주요 링크
- `test_learning_guidance.py`: 오늘 학습 계획, 복습 시점, 상세 오답 피드백, 신규/기존 CSV 호환성

실행:

```powershell
py -3 manage.py check
py -3 manage.py test core.tests
py -3 manage.py smoke_check
```

물류관리사/Subject 수정 후 우선:

```powershell
py -3 manage.py test core.tests.test_subjects
py -3 manage.py test core.tests.test_landing
```

---

## 13. 환경설정

`settings.py` 주요 설정:

- `SECRET_KEY = DJANGO_SECRET_KEY` 또는 dev fallback
- `DEBUG = DJANGO_DEBUG == "1"`
- `ALLOWED_HOSTS = DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS = DJANGO_CSRF_TRUSTED_ORIGINS`
- 운영에서 DEBUG false이고 secret이 default면 RuntimeError
- `DATABASES`는 `dj_database_url.config()`
- `LANGUAGE_CODE = "en-us"`
- `TIME_ZONE = "Asia/Seoul"`
- `LOGIN_URL = "/login/"`
- `LOGIN_REDIRECT_URL = "/missions/"`
- `LOGOUT_REDIRECT_URL = "/login/"`

`.env.example` 환경변수:

```text
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SESSION_COOKIE_SECURE
DJANGO_CSRF_COOKIE_SECURE
DJANGO_SECURE_PROXY_SSL_HEADER
DJANGO_WHITENOISE_MANIFEST_STRICT
DATABASE_URL
```

Render:

- build: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- start: `gunicorn myproject.wsgi:application`
- DB: Render PostgreSQL `comhal-study-db`

---

## 14. TODO 우선순위

### ★★★★★ 매우 중요

- 물류관리사 원본 CSV를 import 표준 스키마로 변환하는 파이프라인 구현
- 모든 물류관리사 Mission에 `subject_code=logistics`, `course`, `chapter_code`, `chapter_name`, `difficulty` 정확히 매핑
- 물류관리사 import 후 컴활 Mission과 섞이지 않는지 검증
- Django 버전 불일치 확인
- 깨진 한글 문자열/인코딩 정리
- `test_subjects` 안정 통과 확인

### ★★★★ 중요

- 물류관리사 문제 이미지 경로/렌더링 규칙 확정
- 물류관리사 전용 ProblemSet 생성 로직 구현/검증
- 시험 40문제 미만일 때 UX 개선
- `ProblemSet.subject`, `ExamSession.subject` 추가 검토
- 무료/프리미엄 제한 정책 테스트 강화

### ★★★ 보통

- `payments.py` 사용 여부 정리
- `core/tests.py`와 `core/tests/` 구조 정리
- curriculum DB화 검토
- 관리자 course/chapter 필터 편의성 개선
- 랭킹 placeholder 구현 여부 결정

---

## 15. 향후 개발 로드맵

### 단기

- 물류관리사 CSV 변환 스크립트 작성
- 변환 CSV import
- 물류관리사 chapter roadmap/mission list/detail 검증
- 문제 이미지 표시 검증
- Subject 격리 테스트 통과

### 중기

- 물류관리사 전용 ProblemSet 자동 생성
- 물류관리사 모의시험 구성 규칙 개선
- `ProblemSet.subject`, `ExamSession.subject` migration 검토
- 프리미엄 정책 강화
- 관리자 필터 개선

### 장기

- 다자격증 플랫폼 구조 일반화
- 과목별 curriculum DB 모델화
- 실제 결제 연동
- 개인화 추천 고도화
- 학습 리포트/랭킹/알림
- 대량 문제 import/검수 자동화

---

## 16. AI 인수인계 정보

### 가장 중요한 규칙

1. 현재 우선순위는 `물류관리사(logistics)`.
2. 기존 `컴활2급(comhwal2)` 기능을 깨면 안 된다.
3. 모든 사용자 화면의 Mission/Attempt/ProblemSet/Exam 조회는 현재 Subject 기준이어야 한다.
4. Mission 삭제보다 `is_usable_for_set=False`.
5. import 기준은 `external_id`.
6. 물류관리사 external_id는 `LOG-[A-Z]{2}\d{2}-\d{4}`.
7. `mission_detail`은 여러 학습 흐름이 공유하므로 세션 키 충돌 주의.

### 깨면 안 되는 부분

- `get_current_subject()`
- `mission_list`의 logistics/default 분기
- `save_attempt()`
- `finish_exam_session()`과 `sync_exam_to_attempts()`
- ProblemSetSession 완료 계산
- UserAccess 기반 제한
- smoke_check 검증 항목

### 현재 기술 부채

- Django 버전 불일치
- 한글 문자열 인코딩/표시 문제
- ProblemSet/ExamSession 직접 subject FK 없음
- 물류관리사 CSV와 import schema 불일치
- `missions.py`가 매우 큼
- `mission_detail` nested handler가 많음
- `wrong_notes` 최신 Attempt 조회가 비효율적
- `order_by("?")` 성능 이슈 가능
- 실제 결제 미구현

### 알려진 버그/리스크

- 물류관리사 CSV 그대로 import 불가
- difficulty choices/VALID_DIFFICULTIES 문자열 깨짐 가능
- Mission subject null 데이터가 있으면 과목 격리 문제
- 무료 시험/패턴 훈련 제한이 과목별이 아니라 사용자 전체 기준으로 보임
- 프로젝트 루트의 `아이디 비번.txt`는 민감정보 포함 여부와 Git 추적 여부 확인 필요

### 앞으로 먼저 할 작업

1. 물류관리사 CSV 변환 스크립트 작성
2. 표준 import CSV 생성
3. `seed_subjects`
4. `import_missions`
5. `test_subjects`
6. `/missions/`에서 물류관리사만 노출 확인
7. 문제 이미지와 객관식 채점 검증

---

## 17. 전체 코드 분석

### 사용하지 않는 코드 후보

- `core/views/payments.py`: 현재 URL 연결 확인 안 됨
- `core/tests.py`: 주요 테스트는 `core/tests/`에 있음
- `scripts/*`: 현재 운영 흐름에서 사용 여부 확인 필요
- `archive/*`: 런타임 사용 아님

### 중복 코드

- learning_type label 변환 로직 반복
- Mission display용 accuracy/last 계산 반복
- exam_result와 exam_recommend_start의 분석 로직 유사
- subject 필터링이 여러 view에 반복되어 누락 위험

### 리팩토링 후보

- `mission_detail` 흐름별 service 분리
- learning_type label helper 통합
- ProblemSet/ExamSession subject FK 추가
- wrong_notes 최신 Attempt 조회 최적화
- 물류관리사 CSV 변환 command 정식화

### 성능 개선 포인트

- `order_by("?")` 제거 또는 대체
- wrong_notes N+1성 최신 attempt 조회 개선
- mission_list annotation 비용 모니터링
- ProblemSet/ExamSession subject join 비용 개선

### 보안 개선 포인트

- 운영 SECRET_KEY/DEBUG/ALLOWED_HOSTS/CSRF 설정 확인
- 결제 도입 시 webhook signature 검증
- UserEvent metadata에 민감정보 저장 금지
- 루트의 `아이디 비번.txt` 관리

### 확장성 개선 포인트

- Subject 중심 구조 유지
- curriculum 모델화
- 과목별 import adapter
- ProblemSet/ExamSession subject 직접화
- grading 전략 분리

---

## 빠른 시작 체크리스트

```powershell
cd C:\노세영\코딩\프로젝트\컴활2급
py -3 manage.py check
py -3 manage.py test core.tests.test_subjects
py -3 manage.py seed_subjects
```

물류관리사 작업 순서:

1. `generated/logistics/logistics_29-1.csv`, `logistics_29-2.csv`를 표준 import CSV로 변환한다.
2. 변환 결과에 `subject_code=logistics`와 `external_id=LOG-...`를 넣는다.
3. `python manage.py import_missions <converted.csv>` 실행.
4. `/`에서 물류관리사 선택.
5. `/missions/`, `/stats/`, `/wrong-notes/`, `/exam/`, `/problem-sets/`에서 컴활 데이터와 섞이지 않는지 확인.

마지막 주의: 이 프로젝트의 핵심은 다과목화다. 새 기능에서 Mission 전체를 조회하면 거의 반드시 과목 섞임 버그가 생긴다. 항상 현재 Subject를 기준으로 데이터를 읽는다.

---

## 코덱스 작업 규칙

이 프로젝트를 수정할 때 다음 순서를 고정적으로 따른다.

1. 코드를 바로 수정하지 않고 현재 구조, 영향 파일, 기존 기능을 먼저 분석한다.
2. 구현 계획을 세운 후 기존 아키텍처, 코딩 스타일, 네이밍과 공용 컴포넌트를 우선 재사용한다.
3. 하드코딩과 임시방편을 피하고 Subject 확장성과 기존 데이터 하위 호환성을 유지한다.
4. 구현 후 관련 파일 전체, 문법/import, migration, 회귀 테스트와 정적 파일을 검증한다.
5. 변경된 프로젝트 구조, 모델, URL, 화면, 비즈니스 로직 및 구현 방식을 이 문서에 갱신한다.
6. 최종 보고에는 변경 파일, 작업 내용, 검증 결과, 잠재 문제와 본 문서 갱신 내용을 포함한다.
