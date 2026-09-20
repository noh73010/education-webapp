# PROJECT_CONTEXT.md

## Render 초기 공개 운영 구성 (2026-09-14)

- 초기 무료 사용자 모집 단계의 배포는 Render Blueprint(`render.yaml`)를 사용한다.
- 웹은 `free`, PostgreSQL은 기록 보존을 위해 유료 최소 플랜 `0.1c-256mb`와 1GB 저장공간을 사용한다. 2026-09 공식 가격 기준 예상 비용은 월 $6.25부터이며 환율·세금·초과 사용량은 별도다.
- 무료 PostgreSQL은 30일 만료 정책 때문에 실제 회원 데이터 저장에 사용하지 않는다. 웹의 15분 유휴 절전이 사용자 경험을 해치기 시작하면 웹만 `0.5c-512mb`로 올린다.
- 운영 비밀값은 Render Environment에만 저장한다. `DJANGO_SECRET_KEY`는 Blueprint가 생성하고 Google/Naver OAuth 값은 `sync: false`로 입력받는다.
- `DATABASE_URL`은 Blueprint가 `comhal-study-db`의 내부 연결 문자열을 주입한다. 시작 시 migration과 생성 문제 동기화 후 Gunicorn을 실행한다.
- 로컬 SQLite와 자동화 task/state/log/attachment는 배포 소스에 포함하지 않는다. 과거 SQLite 백업도 Git 추적에서 제거한다.
- 생성 문제 CSV는 `챕터`/`문제이미지`와 `분류코드`/`이미지` 열 이름을 모두 지원한다. 배포 전 7개 파일 660문항을 두 번 동기화해 두 번째 실행에서 신규·갱신 0건임을 확인했다.

## 비정형 곡선 중심 UI 개선 (2026-09-07)

- 공통 화면의 동일한 회색 테두리·흰 사각 카드 반복을 줄이고, 반투명 표면과 넓은 여백, 비대칭 모서리, 부드러운 배경 그라데이션을 적용했다.
- 주요 행동 버튼은 캡슐형으로 통일하고, 모바일 하단 메뉴는 화면 가장자리에서 떨어진 플로팅 내비게이션으로 변경했다.
- 오늘 학습·약점·성장 카드는 각각 형태와 색조를 달리하되 기존 파랑/주황/초록 의미 체계는 유지한다.
- 문제 풀이, 학습 상태, 문제 목록에도 같은 시각 언어를 적용했으며 HTML 구조와 학습/채점 로직은 변경하지 않았다.
- 애니메이션 감소 환경설정을 존중하며 모바일·태블릿·PC 반응형 구조를 유지한다.

## 전체 기능 무료 운영 모드 (2026-09-07)

- 현재는 가입한 모든 회원에게 오답노트 전체, 패턴 집중 훈련, 모든 모의고사 모드, 상세 약점 분석과 추천 복습을 제한 없이 제공한다.
- 회원의 `UserAccess.is_premium` 값은 그대로 보존하며, 무료 운영을 위해 회원 등급 데이터를 일괄 변경하지 않는다.
- 기능 접근 판정은 `core.services.access.has_full_learning_access()`로 중앙화했다.
- `.env`의 `DJANGO_PREMIUM_GATING_ENABLED=0`이 현재 기본 운영값이다. 향후 무료/유료 플랜을 구분할 준비가 끝난 뒤 이 값을 `1`로 바꾸면 기존 무료 회원 한도가 다시 적용된다.
- 무료 운영 중에는 서비스 소개와 이용 안내에서 유료 신청 대신 모든 기능이 무료라는 사실과 향후 변경 사전 안내 원칙을 보여준다.

## 약점 집중 훈련 맥락 표시 (2026-09-07)

- 패턴 집중 훈련에서 일반 문제 화면을 재사용하되, 활성 훈련 문제일 때만 상단에
  훈련명, 추천 이유, 현재 순서, 남은 문제, 예상 시간과 진행 막대를 표시한다.
- 세션의 패턴 코드와 문제 ID를 그대로 신뢰하지 않고 현재 Subject, 현재 Mission 및
  실제 WrongPattern과 일치하는 경우에만 훈련 컨텍스트를 만든다. 다른 자격증이나
  일반 문제에는 배너가 노출되지 않는다.
- 제출 버튼은 중간 문제에서 `다음 훈련 문제`, 마지막 문제에서 `훈련 결과 확인`으로
  바뀐다. 기존 3문제 제한, 채점, 결과 저장, 약점 생명주기와 Queue 흐름은 유지한다.
- 데이터 모델 migration은 필요 없다. 컨텍스트 생성은
  `core/services/pattern_training_context.py`에서 담당한다.

## 모바일 학습 코치 첫 화면 (2026-09-06)

- 학습 홈의 첫 화면은 `오늘의 학습`, `지금 가장 위험한 약점`, `최근 좋아진 점` 세 카드만
  우선 노출한다. 로드맵, 모의고사, 최근 기록, 문제 검색과 상세 학습 도구는 하나의
  접힌 영역에 두어 필요한 사용자가 펼쳐본다.
- 오늘 행동은 파란색, 약점 확인과 복습은 주황색, 개선 근거는 초록색으로 통일했다.
  빨간색은 과락이나 입력 오류처럼 실제 위험 상태에만 사용한다.
- 약점 카드는 미극복 `UserWeakness` 중 상태와 심각도를 고려해 한 개만 고르고
  `3문제 복습 시작`처럼 다음 행동과 분량을 명시한다. 최근 개선 카드는 극복한 약점,
  과거 오답을 다시 맞힌 기록, 연속 학습 근거 순으로 과장 없이 한 가지 변화를 보여준다.
- 모바일은 한 열, 태블릿은 오늘 학습 전체 폭과 보조 카드 두 열, PC는 세 열로 배치한다.
  표 대신 세로 카드와 짧은 진행 막대를 사용하며 학습 완료 시 작은 성취 표시를 제공한다.
  애니메이션 감소 설정(`prefers-reduced-motion`)도 존중한다.
- 데이터 모델 migration은 필요 없다. 핵심 회귀 테스트는
  `core.tests.test_personalized_learning`과 `core.tests.test_responsive_layout`에 있다.

## 실제 수험생 사용 점검 개선 (2026-09-05)

- 시험 점수에서는 미응답을 기존처럼 0점으로 계산하지만, 실제 제출하지 않은 문항은
  `Attempt`로 만들지 않는다. 따라서 조기 제출·시간 만료의 미응답이 오답노트,
  정답률, 약점 지도, 반복 오답 추천을 오염시키지 않는다.
- 시험 결과는 정답/오답/미응답을 분리한다. 영역별 성적과 약점 복습 추천은 실제
  답안을 제출한 문항만 사용하며, 미응답은 별도 안내한다.
- 일반 문제의 정답 결과에도 해설을 표시한다. 확신도는 기본 선택하지 않으며 사용자가
  직접 선택하지 않으면 빈 값으로 저장해 `헷갈려요`로 임의 추정하지 않는다.
- 물류관리사 화면의 LM/FT/IT/BH/LR 내부 코드는 표준 챕터명으로 변환한다. 오답노트,
  통계, 시험 결과에서는 내부 패턴 코드와 원본 파일성 제목을 학습자에게 노출하지 않는다.
- 학습 홈의 최근 기록에 일반 문제 풀이도 포함한다. 전체 로드맵은 접어서 제공하며,
  문제은행 총 문제 수 대신 `시작 전/학습 중/복습 필요` 같은 학습 상태를 표시한다.
- 이 변경은 데이터 모델 migration이 필요 없다. 과거 버전에서 이미 미응답을 오답
  `Attempt`로 저장한 기존 기록은 자동 삭제하지 않으므로 운영 정리가 필요하면 사용자와
  범위를 확인한 뒤 별도 데이터 보정 절차를 사용한다.

## 모의고사 3모드 (2026-09-04)

- /exam/에서 짧은 실전 연습(10문제/10분), 과목별(40문제/40분), 실전 2교시를 선택한다.
  과목별 40분은 앱 연습 기준이다. 물류관리사 실전은 1교시 물류관리론/화물운송론/
  국제물류론 각 40문제·120분, 2교시 보관하역론/물류관련법규 각 40문제·80분이다.
- core/services/exam_modes.py에 시험 구성/출제/판정을 분리했다. 기존 제출·임시저장 재사용.
  0042_exam_modes는 ExamSession.mode_config와 previous_sitting, waiting 상태만 추가한다.
  레거시 시험은 빈 config로 보존하며, 기존 service 호출과 mode 없는 POST도 유지한다.
- 실전 시작 시 두 교시의 문제를 모두 확보한다. 과목별 준비 부족 시 전체 생성 롤백.
  자동 채점 가능한 사용 허용 선택형 문제만, 과목별 정확한 수량·중복 없이 출제한다.
  미풀이 우선이며 이전 풀이 포함 수를 기록한다. 매일 새로운 200문제를 보장하지 않는다.
- 2교시는 대기 상태로 예약되며 1교시 완료 후 CSRF POST로 직접 시작한다.
  그때 시작시각을 설정한다. 대기 시험은 답안 저장/종료 불가. 재시작 버튼으로 시각을 리셋하지 않는다.
  생성/재개 endpoint는 사용자 행 잠금으로 중복 생성을 막는다. 무료 새 시험 제한은
  기존처럼 세 모드 합계 하루 1회이며 재개/2교시는 횟수를 소모하지 않는다.
- 생성 당시 과목별 문제 매핑과 기준을 JSON에 보존한다. 실전 두 교시가 완료되어야
  과목별 정답수×2.5점으로 각 40점 이상 및 전체 평균 60점 이상을 모두 판정한다.
  레거시 정수 요약 점수는 판정에 사용하지 않는다. 짧은/과목별은 전체 합격 판정 제외.
  기록 화면에서 모드 혼합 평균/가짜 합격률을 제거하고 각 시험 결과로 연결한다.
- 다른 자격증은 짧은/과목 연습을 지원하고 실전 blueprint 등록 전에는 실전 모드를 제공하지 않는다.
  운영 배포 전 DB 백업 및 migrate 필요. 테스트는 core.tests.test_exam_modes.
- 현재 로컬의 출제 가능 국제물류론은 39문항으로 실전/해당 과목 40문제 구성이 부족하다.
  실전 시작 버튼에 준비 중을 안내한다. 보류 문항 재검수 또는 검수된 새 문항 추가가 필요하며
  문제 수를 맞추기 위해 보류 해제·중복 출제하지 않는다.

## 반응형 화면 보강 (2026-09-04)

- base.html의 기존 CSS 뒤에 core/responsive.css를 추가했다. 768px 이하 단일 열,
  769px 이상 로드맵/학습 상태 2열, 1100px 이상 로드맵 3열 및 미제출 문제/답안
  2열 배치. 전체 최대 너비 1280px. :has 미지원 환경은 기존 단일 열로 유지된다.
- 화면 크기 변경 시 동일 폼을 유지한다. 채점/저장/DB는 변경하지 않는다.
  표의 영역 내 스크롤, 키보드 포커스, 터치 높이, 모바일 입력 크기와 safe-area 보강.
- 실제 모바일·태블릿·PC 브라우저 검증은 아직 미완료다.

## 추가 품질 보강 (2026-09-04)

- `0041_exam_reliability_and_review_sources`: 시험 문항별 임시답안/저장시각/제출답안과
  ConceptUnit.references를 추가. 로컬 DB 백업 후 적용했으며 운영 DB 적용은 별도 필요하다.
- 모의고사에도 shared mission_draft.js를 사용한다. exam item을 제출 영수증으로 사용하고
  user → exam 행 잠금 순서와 최초 제출만 인정하는 서비스로 중복 저장/덮어쓰기를 방지한다.
  시험 종료/Attempt 반영도 재호출 안전성을 보강했다. 무료 일일 제한은 새 시험에만 적용한다.
  앱 전환 시 표시 타이머는 경과 시간을 반영하며, 서버 만료 후 답안은 받지 않는다.
  제출 전 결과 주소 접근은 미제출 문항으로 돌려보내고, 만료 시 종료 처리를 수행한다.
- 시험 결과 템플릿의 깨진 한글/HTML을 복구하고 모바일 목록으로 표시한다.
  임의 계산된 합격 확률/합격 보장을 표시하지 않고 해당 시험의 관측 결과만 제공한다.
  기존 analysis 서비스의 호환 필드는 유지한다.
- `audit_learning_content --subject-code logistics`는 기본 읽기 전용 구조 검사다.
  `--apply-reviewed`는 `core/data/logistics_review.json`의 정확한 내용 해시에 해당하는
  검수/보류만 적용한다. import_missions에서도 적용하여 재수입 시 보류가 풀리지 않게 한다.
  해시는 지문/선택지/정답/해설에 대한 것이다. 이미지 원문 대조는 별도 사람 검수가 필요하다.
- 실제 로컬 270문항 중 6문항에 3개 개념 비교 자료와 근거 URL을 연결했다.
  원출처 270문항은 여전히 미확인으로 유지한다. 참고 자료를 기출 원출처로 가장하지 않는다.
  나머지 264문항 내용 검수와 이미지 지문 14문항 대조는 완료로 간주하지 않는다.
  7R 근거 불명확 1문항, 판단 지문/이미지 누락 1문항은 자동 출제 보류. 정답·기록은 삭제하지 않는다.
- 테스트: test_exam_reliability, test_content_review 및 기존 core 회귀.
  최종 core.tests 168개 통과, Django check 및 migration 일관성 검사 통과.
  393×883 임시 DB 브라우저에서 복원/제출/완료 결과 67점(정답 2/3) 및 한글 표시 확인.
  실기기와 운영 서버는 미검증. 전체 git diff --check는 기존 CSV 파일 끝 빈 줄 1건이 남아 있다.
  기기별 실제 수용 테스트/배포 절차는 `docs/MOBILE_ACCEPTANCE.md` 참조.

## 수험자 첫 방문·모바일 학습 품질 개선 (2026-09-04)

- migration `0040_learning_experience`는 기존 문제/기록을 삭제하지 않고 선택 필드와
  ConceptUnit, LearningStart, MissionWork를 추가한다. 적용 전 로컬 SQLite 백업을
  `.local-backups/`에 보관한다(개인정보 포함 가능, Git 제외). 배포 서버에서도 백업 후 migrate 필요.
- Mission의 source_type(unknown/past/adapted/original), source_reference, reviewed_on을
  문제 화면에 표시한다. 기본은 미등록이며 기존 품질 플래그나 파일명으로 검수·출처를 추정하지 않는다.
  CSV 선택 컬럼 `문제구분/출처/검수일` 또는 `source_type/source_reference/reviewed_on`도 지원한다.
  컬럼이 없으면 기존 값을 보존한다. 검수일 형식은 YYYY-MM-DD, 운영자가 실제 근거를 확인해 입력한다.
- `/missions/<id>/report/`는 로그인/CSRF/현재 과목 검증 후 기존 Inquiry에 mission FK와
  오류 내용을 저장한다. 같은 미처리 신고의 재전송은 중복 생성하지 않는다. 관리자 문의에서 처리한다.
- 일반 문제 및 mission_detail을 공유하는 세트/훈련은 MissionWork UUID로 임시저장과
  제출 영수증을 관리한다. 임시저장은 Attempt를 만들지 않는다. 브라우저 폼은 같은 UUID로
  재전송하며 DB transaction과 사용자 행 잠금 안에서 1회 저장 후 원래 결과/다음 화면으로 보낸다.
  토큰 없는 레거시 직접 POST는 기존 동작을 유지하므로 이 중복 방지 계약에 포함되지 않는다.
  PostgreSQL에서 행 잠금으로 직렬화하며 SQLite 동시 쓰기 잠금 오류 시 재시도가 필요할 수 있다.
- 새 JS는 서버 임시저장, 탭 sessionStorage 보조 복원, 오프라인 안내, 제출 버튼 중복 클릭 방지,
  통신 시간 초과 안내와 제출 여부 확인 링크를 제공한다. 완전한 오프라인 학습 기능은 아니다.
  home은 현재 과목의 가장 최근 미제출 답안을 이어 풀기로 제공한다. 별도 exam_take 시험도
  0041에서 임시저장과 중복 제출 방지를 추가했다. 시험 메뉴에서 풀던 시험으로 재개한다.
- `/learning-start/`에서 과목별 경험 수준과 선택형 최대 3문제 진단을 제공한다. 강제 진입 없음.
  경험에 따른 시작 안내를 표시하고, 준비된 다른 챕터의 객관식 문제로 확인한다. 진단 결과는
  실제 응답이 있는 범위만 안내하며 전체 실력/합격 확률을 주장하지 않는다. 시험일은 StudyProfile 재사용.
- ConceptUnit은 같은 Subject의 문제를 운영자가 명시적으로 연결하는 검수된 개념 묶음이다.
  비교 설명/짧은 예시/검수일을 입력한다. 2회 이상 틀린 문제는 이 자료를 먼저 보여주고
  동일 개념의 다른 문제로 안내한다. 자료가 없으면 해설·이론을 우선하며 준비 중이라고 명시한다.
  일반 챕터·variation_group만으로 특정 개념 혼동을 단정하거나 비교 자료를 자동 생성하지 않는다.
- 홈/통계/개별 결과는 오늘 정답, 3일 후 동일 문제 재확인, 검수된 동일 개념의 처음 보는
  다른 문제 정답을 구분한다. 마지막 항목은 이전 오답 이후 3일 경과 및 확실함 응답이 필요하다.
  이 또한 한 번의 확인이지 완전한 숙련이나 합격 보장이 아니라고 안내한다.
- 학습 기록 초기화는 MissionWork(임시저장/영수증), LearningStart(진단)를 함께 삭제한다.
  탈퇴는 CASCADE로 제거한다. 출처·개념 자료와 공유 문제는 사용자 초기화 대상이 아니다.
- 테스트: core.tests.test_learning_experience. 실제 출처 확인·개념 비교 콘텐츠 검수는
  운영자의 콘텐츠 작업이며 개발 테스트만으로 완료된 것으로 간주하지 않는다.

## 회원 학습 기록 초기화 및 탈퇴 (2026-09-04)

- `/account-settings/`에 계정 관리 화면을 추가했다. 모바일 메뉴, 내 기록, 시험일 설정에서 접근한다.
- 초기화는 현재 과목에 한정하지 않고 본인의 모든 Subject에 걸친 Attempt 및 오답 연결,
  DailyMission, 시험/세트 세션과 답안, 패턴 훈련, 약점, 혼동 카드, streak, 학습 이벤트를 삭제한다.
  계정/프리미엄 권한/StudyProfile/문의/비학습 이벤트와 공유 문제 콘텐츠는 유지한다.
- 탈퇴는 auth user 및 CASCADE 관계(소셜 연결 포함)를 삭제한다. SET_NULL인 Inquiry와
  UserEvent는 개인 내용이 남지 않도록 먼저 삭제한다. 외부 소셜 계정/권한은 별도로 관리한다.
- 로그인 + CSRF POST + 정확한 확인 문구 + 동의가 필수다. 일반 계정은 현재 비밀번호를
  확인하고, 소셜 전용 계정은 allauth 인증 기록의 최근 socialaccount 로그인 시각을 확인한다.
  유효시간은 allauth REAUTHENTICATION_TIMEOUT을 따른다. 지난 경우 재로그인이 필요하다.
- 삭제 서비스는 transaction.atomic 및 사용자 행 잠금을 사용한다. 기본 DB 세션에서 해당
  회원의 활성 세션만 제거하고 현재 요청도 로그아웃하여 오래된 훈련 결과 재사용을 방지한다.
  세션 백엔드를 변경할 경우 이 무효화 정책도 함께 변경해야 한다. 실행 중인 동시 제출을
  완전히 직렬화하는 기능은 아니므로 초기화 전 다른 탭/기기의 학습을 종료해야 한다.
- 데이터 스키마 변경 없음. core.tests.test_account_settings가 권한/CSRF/삭제 범위/
  다과목/타회원 격리/소셜 인증/세션/트랜잭션을 검증한다. 운영 데이터는 개발 중 삭제하지 않는다.

## 모바일 적응형 학습 루프 (2026-09-03)

- 학습 홈에서 사용자가 오늘 가능한 시간을 `5분 / 10분 / 20분`으로 선택한다.
  `StudyProfile.daily_minutes`에 저장하며 각각 3문제, 5문제, 최대 10문제 처방을
  새로 구성한다. 다른 자격증도 같은 DailyMission 엔진을 사용한다.
- 틀린 직후에는 모든 선택지 설명을 길게 펼치지 않고 내가 선택한 답과 정답만 먼저
  비교하는 `30초 오답 교정`을 제공한다. 같은 variation group 문제가 있으면 유사
  문제 1개로 즉시 확인할 수 있다.
- 오답은 다음 날, 오답 후 정답은 3일 뒤 복습한다. 정답이어도 `찍었어요` 또는
  `헷갈려요`로 기록한 문제는 다음 날 `확신 보강` 대상으로 다시 추천한다.
- D-Day는 foundation/intensive/review/final 단계로 변환한다. 시험 3일 전부터는
  새 범위보다 개인 혼동 카드가 있으면 이를 오늘의 최우선 행동으로 안내한다.
- `/final-cards/`는 사용자가 실제로 틀리거나 찍은 선택지와 미해결 약점만 모은 개인별
  시험 직전 노트다. 일반 요약집이나 전체 문제 재고를 노출하지 않는다.

## 수험자 중심 학습 통계 (2026-09-03)

- 통계 화면의 `학습 단계별 진행률`과 문제 재고형 표를 제거했다. 내부 챕터 코드,
  획일적인 `결과 예측형`, 웹 전체 문제 수는 수험자 화면에 노출하지 않는다.
- 대신 실제 시험 범위명과 `학습 전 / 학습 중 / 복습 필요 / 약점 발견 /
  집중 훈련 중 / 재평가 예정 / 안정적` 상태, 그리고 바로 실행할 다음 행동을 보여준다.
- 문제 총량은 추천과 상태 계산에 내부적으로만 사용한다. 화면에서는 다양한 기출·변형
  문제가 학습 기록에 따라 계속 추천된다는 경험을 전달한다.
- 물류관리사는 표준 챕터명을 사용하고, 향후 자격증은 Mission의 course/chapter 정보를
  사용하므로 내부 코드 체계를 수험자에게 노출하지 않고 확장할 수 있다.
- 풀이·약점 기록이 없는 `학습 전` 챕터는 통계에서 개별 나열하지 않는다. 기록이
  없으면 오늘 학습 CTA 하나만 표시하고, 기록이 생기면 최우선 범위 1개와 다른 범위
  최대 4개만 먼저 보여준다. 나머지는 사용자가 원할 때만 `전체 보기`로 펼친다.

## 컴활2급 과목 종료 및 다중 자격증 확장 유지 (2026-09-03)

- `comhwal2`는 더 이상 활성 과목이 아니며 migration `0039`가 기존 레코드를
  비활성화한다. 풀이 기록과 연결 데이터의 안전을 위해 물리 삭제하지 않는다.
- 과목 선택 화면, 기본 세션 복구, `seed_subjects`에서 컴활2급을 생성하거나
  노출하지 않는다. 이전 컴활2급 세션은 자동으로 활성 기본 과목으로 복구된다.
- 현재 기본 진입 과목은 `logistics`지만 플랫폼은 물류관리사 전용 구조가 아니다.
  새 자격증은 고유 `Subject.code`, 문제 데이터, 필요 시 자격증 정책/커리큘럼을
  추가하면 선택 화면에 함께 노출된다.
- 과목이 명시되지 않은 CSV를 특정 자격증에 자동 귀속하지 않는다. `--subject-code`,
  CSV의 `subject_code`, 또는 등록된 과목 코드 폴더를 명시해야 한다.

## Personalized multi-certificate learning engine (2026-09-01)

- 물류관리사를 기준 구현으로 3단계 개인화 학습 구조를 도입했다. 새 자격증은
  `Subject`별 설정과 분류표를 추가해 같은 엔진을 사용한다.
- 1단계: `WrongPattern`은 이제 `Subject`에 속하며 코드는 자격증 안에서만 유일하다.
  물류관리사 35개 챕터에는 `LOGISTICS_<chapter_code>` 패턴이 생성되고, 문제의
  `wrong_pattern_code`와 `variation_group`이 같은 코드로 연결된다. 기존 데이터는
  migration `0035`가 보정하며 한국어 CSV import도 이 규칙을 자동 적용한다.
- 2단계: `UserWeakness`가 약점을 `suspected -> active -> training -> review_due ->
  mastered`로 관리하고, 극복 후 다시 틀리면 `relapsed`로 전환한다. 반복 오답 2회로
  약점이 확정되고, 집중 훈련 80점 이상이면 3일 뒤 재평가 대상이 되며 재평가 정답
  3회로 극복 처리된다. 활성·재발·재평가 패턴은 일일 추천에서 우선된다.
- 3단계: `CertificationPolicy`와 `CertificationArea`가 자격증별 합격점, 과락 기준,
  시험 문항/시간, 준비도 최소 근거량과 평가 영역을 정의한다. 물류관리사는 5개
  시험과목과 과락 40점/평균 합격 기준 60점을 사용한다. 준비도는 최근 정답률,
  영역 균형, 모의고사, 약점 극복, 영역 커버리지를 함께 계산하며 기록 부족·모의고사
  없음·과락 위험을 명시적으로 표시하고 점수를 제한한다.
- 운영자가 Django Admin에서 자격증 정책/영역, 과목별 오답 패턴과 사용자 약점 상태를
  확인할 수 있다. 새 자격증 추가 시 정책과 영역, 문제별 패턴 매핑을 먼저 구성해야 한다.
- 2026-09-02에 물류관리사 로드맵을 원본 문제 데이터의 공식 내부 분류인 35챕터로
  정정했다. 표준 코드는 `LM01~LM08`, `FT01~FT08`, `IT01~IT04`, `BH01~BH08`,
  `LR01~LR07`이다. 예전 내부 별칭 `TR/IL/WH/LW`는 import 호환 입력으로만
  받아 각각 `FT/IT/BH/LR`로 정규화한다. migration `0036`이 기존 Mission과
  오답 패턴·자격증 평가영역을 새 코드로 전환하고, `0037`은 더 이상 유효하지 않은
  과거 패턴을 `LEGACY_` 코드로 보존한다. 현재 원본 CSV 3개에는 270문제가 있으며
  35챕터 중 `FT07`, `BH08`은 아직 문제 데이터가 없어 로드맵에 준비 중으로 표시된다.
- 로드맵의 화면 표시 번호는 35개 전체의 전역 순번이 아니다. 각 시험과목 안에서
  `01`부터 다시 시작한다. 따라서 물류관리론 `01~08`, 화물운송론 `01~08`,
  국제물류론 `01~04`, 보관하역론 `01~08`, 물류관련법규 `01~07`로 표시한다.
- 모바일 학습 홈은 오늘 문제 수·예상 시간·추천 이유·진행률과 `오늘 학습 시작`을
  최우선으로 표시한다. 준비도/레벨/약점은 `내 학습 상태` 접이식 패널에 넣고,
  35챕터 로드맵도 시험과목별 접기/펼치기로 표시하며 현재 추천 과목만 기본으로 연다.
  각 과목 요약에는 풀이 수와 진행률이 표시된다. 하단 고정 메뉴는 `홈 / 학습 /
  오답 / 내 기록` 4개로 단순화했다. 오늘 학습 완료 화면은 `UserWeakness`의 상태를
  쉬운 한국어로 보여주고 가능한 경우 약점 집중 훈련으로 바로 연결한다.

## Local mobile development via Cloudflare Quick Tunnel (2026-08-19)

- This is a temporary development-only path from an external phone to the
  Django server running on the home Windows PC. It is separate from Render and
  from the GitHub Issue/Codex automation pipeline.
- Django loads the project-root `.env` without overriding process environment
  variables. Run it locally with `py -3 manage.py runserver 127.0.0.1:8000`;
  binding to `0.0.0.0` and opening the Windows firewall are not required.
- Set `DJANGO_DEBUG=1` and set `DJANGO_TUNNEL_HOST` to the exact lowercase
  hostname printed by Quick Tunnel, such as `sample.trycloudflare.com`. Do not
  include `https://`, a port, a path, or a wildcard.
- When DEBUG is enabled, that single host is appended to `ALLOWED_HOSTS` and
  `https://<host>` is appended to `CSRF_TRUSTED_ORIGINS`. The forwarded HTTPS
  header is honored for the localhost tunnel. When DEBUG is disabled the tunnel
  setting is ignored, preserving Render's host, CSRF, HTTPS, and cookie policy.
- Start Quick Tunnel separately with `cloudflared tunnel --url
  http://127.0.0.1:8000`. Quick Tunnel hostnames can change after restart; only
  `DJANGO_TUNNEL_HOST` needs to change, followed by a Django server restart.
- The public URL temporarily exposes the local development application. Keep
  sessions short, use non-sensitive test data/accounts, avoid exposing debug
  tracebacks to untrusted people, and stop `cloudflared` immediately afterward.
  Admin and every normally public route remain reachable through the tunnel.
- OAuth is separate from basic tunnel verification. Testing it also requires
  provider credentials and exact registered callbacks at
  `https://<host>/accounts/google/login/callback/`,
  `https://<host>/accounts/naver/login/callback/`, and
  `https://<host>/accounts/kakao/login/callback/`.

## Social login (GitHub Issue #10, 2026-08-19)

- `/login/` and `/signup/` support Google, Naver, and Kakao OAuth through `django-allauth`.
- OAuth client IDs and secrets are loaded only from provider-specific environment variables.
- Provider callbacks are served under `/accounts/<provider>/login/callback/`.
- Social signups automatically create the same `UserAccess` record as local signups and record a signup analytics event.
- OAuth handshakes start with CSRF-protected POST requests. Matching email addresses are not automatically connected to existing local accounts.
- Provider app credentials and callback URL examples are documented in `.env.example`.
- The local username/password login remains available when OAuth credentials are absent; only fully configured provider buttons are rendered.
- Login and signup reuse `registration/includes/social_login_buttons.html` for the provider buttons, and the login page presents local signup as a full-width high-contrast call-to-action.
- Render runs database migrations before Gunicorn in the start command so the
  deployment works on both free and paid web-service plans. The migration is
  forward-only and idempotent; it does not delete data or roll migrations back.
- Render uses the latest Python 3.13 patch for Django 6.0 compatibility.
- `django-allauth` is pinned to the published 65.18.0 release. A previous pin to
  the nonexistent 65.19.1 release caused `pip install -r requirements.txt` to
  fail before the server could start.
- Naver login uses the settings-based allauth app configuration from
  `NAVER_OAUTH_CLIENT_ID` and `NAVER_OAUTH_CLIENT_SECRET`; do not also create a
  database `SocialApp` for Naver. The login endpoint is `/accounts/naver/login/`
  and the callback is derived from the current request origin at
  `/accounts/naver/login/callback/`.
- The verified local callback for port 8888 is
  `http://127.0.0.1:8888/accounts/naver/login/callback/`. Behind Render's HTTPS
  proxy it is `https://comhal-study.onrender.com/accounts/naver/login/callback/`
  when `DJANGO_SECURE_PROXY_SSL_HEADER=1` is configured.
- Regression tests parse the real Naver authorization redirect and assert both
  local HTTP and Render-proxied HTTPS callback URLs. Real OAuth secrets remain
  outside the repository in `.env` or deployment environment variables.
- Social login normally creates the internal user automatically from the
  provider identity; learners are not asked to invent another username or
  enter an email after Google/Naver/Kakao authentication. The internal
  username remains an implementation detail.
- If a provider returns an email already used by another member, automatic
  email authentication and automatic account merging remain disabled. The
  styled `templates/socialaccount/signup.html` explains the conflict without
  exposing editable signup fields and directs the learner to sign in to the
  existing member first.
- `/account-settings/` lists configured and already connected social providers.
  An authenticated member can explicitly connect another provider using
  allauth's CSRF-protected `process=connect` flow; a successful connection
  returns to account settings. This is the supported way to use Google and
  Naver with the same learning history.
- Connected providers are not automatically disconnected from the custom
  account screen. This avoids leaving a social-only member without a usable
  login method. Member deletion still removes local social credentials through
  the existing cascade behavior.

## Automation task pipeline (2026-08-11)

- GitHub Issue bodies and user comments support PNG, JPEG, and WebP image
  attachments. `automation/attachments.py` extracts GitHub-hosted attachment
  URLs, downloads them through the authenticated GitHub session, and stores
  them under `automation/attachments/issue_<number>/issue/` or
  `comment_<comment_id>/`. This runtime directory is ignored by Git.
- Downloads allow only HTTPS `github.com/user-attachments/assets/`,
  `user-images.githubusercontent.com`, and
  `private-user-images.githubusercontent.com` URLs. GitHub's current attachment
  redirect target, `github-production-user-asset-6210df.s3.amazonaws.com`, is
  also accepted only for its numeric-owner image-object path shape. The prior
  omission of this host caused real Issue #10 JPEG downloads to fail at the
  redirect allowlist check even though GitHub returned valid images. Every
  redirect target is
  checked before it is requested. HTTP errors, timeouts, unsupported MIME
  types, MIME/extension mismatches, invalid image signatures, and files above
  `AUTOMATION_ATTACHMENT_MAX_BYTES` are skipped without losing the text task.
  Error metadata tells Codex that the image was unavailable, so it must not
  claim to have seen it.
- Attachment failures log structured, secret-safe diagnostics including Issue,
  source, failure stage, host, HTTP status, MIME type, and reason. Signed query
  strings, authorization headers, and tokens are never logged.
- `GitHubIssueClient` owns a Session with Bearer authorization, GitHub Accept,
  and API-Version headers. The attachment downloader may use those headers for
  the initial `github.com/user-attachments/assets/...` request, but explicitly
  removes all three on request preparation after a validated redirect to a
  non-GitHub attachment host. The S3 request retains its complete AWS signed
  query and uses that query as its only authorization mechanism.
- Read-only reproduction with both Issue #12 URLs confirmed the operational
  failure: GitHub returned 302, the signed S3 URL returned 400 when the GitHub
  Session headers were retained, and the same URL returned 200 `image/png` when
  those headers were removed. Both files passed size, MIME, and PNG signature
  validation and were written successfully to a temporary attachment store.
  A new Issue/comment remains the required end-to-end watcher and Codex
  `--image` operational check; existing completed Issue #12 tasks are not
  requeued.
- Samsung Browser/Android JPG attachments can contain valid vendor metadata
  after the JPEG EOI marker. A real Issue #13 screenshot was a complete,
  baseline EXIF JPEG (`1080x2316`, RGB) followed by 191 bytes ending in Samsung
  `SEFT` metadata. The old `data.endswith(FF D9)` check rejected it even though
  an independent decoder verified the image. JPEG validation now parses marker
  boundaries, segment lengths, SOF, one or more SOS entropy streams, byte
  stuffing/restart markers, and EOI. It accepts JFIF, EXIF, progressive, and
  safe post-EOI vendor metadata while rejecting truncated streams and bodies
  that are HTML, text, or a different image type. MIME, extension, size,
  redirect allowlist, and GitHub-to-S3 credential isolation checks still run
  independently. This uses no new runtime image dependency; Pillow was used
  only as an installed local diagnostic cross-check.
- Attachment filenames use a canonical URL SHA-256 key and each source scope
  keeps an atomic `attachments.json` manifest without URL query strings. This
  provides restart-safe download deduplication without a database or leaking
  signed query parameters.
- Conversation tasks place logical `이미지 N` metadata immediately after the
  user message that supplied it. Issue images and earlier user-comment images
  are included again in later follow-up tasks in chronological order, allowing
  requests such as "아까 이미지 기준으로 수정해줘". The structure can later
  add recent-N selection, summaries, retention, or capacity cleanup; images are
  retained now because follow-up conversations reuse them.
- Watcher-generated attachment metadata uses an exact `[첨부 이미지]` header
  followed immediately by `- 이미지 N: <local path>` entries. The worker only
  parses entries inside those blocks, plus the legacy exact `첨부 이미지:`
  header for already queued history files. It never treats `이미지 N:` text in
  user or Codex prose as a filesystem path. Download-failure entries are
  ignored; real files must resolve under `AUTOMATION_ATTACHMENTS_DIR`, retain
  their document order, and use a supported image suffix before becoming Codex
  `--image` arguments.
- `RealCodexProcessor` validates every task image path under the configured
  attachment root and invokes Codex CLI 0.147.0 using `codex exec --image
  <path>... --sandbox workspace-write --output-last-message <response> -`.
  Paths are passed as Unicode argument-list entries with `shell=False`, so
  Windows spaces and Korean paths require no manual quoting. Text prompts still
  use UTF-8 stdin, and all existing response/comment/Queue behavior is unchanged.
- The worker intentionally inherits the signed-in user's Codex configuration,
  model, and default profile, but overrides `model_reasoning_effort` to `high`
  through the official CLI `--config` option. `CODEX_REASONING_EFFORT=high` is a
  required `.env` setting. It keeps `workspace-write`. Codex CLI 0.147.0 rejects
  an explicit `--sandbox workspace-write` combined with `--approve-for-me`, so
  the worker does not pass an approval option and relies on the established
  workspace-write behavior.
- The Codex subprocess inherits the parent environment. The worker dynamically
  places the project `.venv/Scripts` (Windows) or `.venv/bin` directory first in
  the child PATH and sets `VIRTUAL_ENV`; no user-specific installation path is
  hardcoded. The running interpreter and a discovered Windows `py` launcher
  remain fallback candidates only. The project `.venv` is ignored by Git.
- Worker startup performs one preflight before polling, not once per cycle. It
  verifies the resolved project root, prefers the executable project `.venv`
  Python, records its version, imports Django and records its version, and
  resolves/runs the configured Codex CLI version with `shell=False`. A missing
  `.venv` may use a verified `py -3` fallback on Windows (or `python3`/`python`
  elsewhere); an existing but unusable `.venv`, failed Django import, or missing
  Codex CLI stops startup before any task is claimed.
- The development-partner preamble tells Codex to use
  `.venv\\Scripts\\python.exe` on Windows or `.venv/bin/python` elsewhere for
  validation. Django changes should run `manage.py check` and relevant tests;
  automation changes should run unittest discovery through that interpreter.
  Unrun checks are never reported as passed, and any failed validation must use
  `validation=failed` so the existing quality-gate warning is preserved.
- `automation/issue_watcher.py` polls GitHub Issues and writes unseen issues to
  `automation/tasks/pending/`.
- The watcher also polls comments on every open Issue. Each unseen user comment
  becomes `issue_<issue_number>_comment_<comment_id>.md` in `pending/`; the task
  contains the Issue title/body, the conversation through that comment, explicit
  user/Codex roles, and the current request. No Issue template is required.
- Comment discovery is restart-safe without a database. Queue filenames across
  `pending/`, `processing/`, and `done/` are the authoritative comment-ID
  deduplication records, while per-Issue GitHub `since` cursors are atomically
  stored under `automation/state/` to reduce API traffic.
- Comments previously posted by this automation are identified by the GitHub
  comment IDs in `automation/logs/*.commented` and are never queued again.
  Comments from other GitHub Bot accounts are also ignored, preventing an
  automated response loop even when the GitHub token user also writes requests.
- GitHub Issue는 고정 템플릿 없이 제목과 본문을 하나의 자연어 메시지로
  취급한다. 작업 파일에는 `# Issue <number>`, 제목, 본문만 저장한다.
- `.github/ISSUE_TEMPLATE/`의 기존 기능 요청 템플릿은 제거했다. GitHub의
  빈 Issue 작성 화면에서 메신저처럼 제목과 본문만 자유롭게 입력하며,
  저장소 규칙과 실행 지침은 Issue 작성자에게 반복 입력시키지 않고
  watcher와 worker가 담당한다.
- `automation/codex_worker.py` moves Markdown tasks through the filesystem queue:
  `pending/` -> `processing/` -> `done/`.
- The worker uses `RealCodexProcessor`, which invokes `codex exec --sandbox
  workspace-write -` from the project root.
- The processor prepends a development-partner preamble that instructs Codex to
  read `PROJECT_CONTEXT.md`, read `AGENTS.md` when present, preserve the existing
  project structure, and understand the Issue as a natural-language conversation
  rather than a fixed template. The complete stored Issue Markdown is appended
  unchanged and the combined prompt is passed through UTF-8 text stdin. The
  worker stores stdout/stderr under `automation/logs/` and only moves successful
  tasks to `done/`.
- The preamble distinguishes analysis/design requests from implementation,
  forbids evidence-free edits when required images or diagnostics are missing,
  permits independent text-only work to continue, and requires task-appropriate
  validation plus a final self-review. It also requires a machine-readable
  `AUTOMATION_RESULT` line. The worker stores this as a per-task `quality.json`,
  removes the marker from the public comment, and visibly warns when changed
  code failed validation, was not validated, or has no trustworthy status.
- Windows and Linux both use a direct argument list with `shell=False`. Windows
  does not wrap `codex.cmd` with `cmd.exe /c`. The command ends with the official
  `-` sentinel, and `subprocess.run(input=task_prompt, text=True,
  encoding="utf-8")` sends the complete Unicode prompt through stdin.
- Before starting Codex, the worker stores the exact combined prompt as
  `automation/logs/issue_<number>.prompt.md`. This audit log is preserved for
  successful runs, non-zero exits, launch failures, and timeouts alongside the
  existing stdout/stderr logs.
- The worker passes `--output-last-message
  automation/logs/issue_<number>.response.md` to Codex CLI and stores only the
  final assistant message in that UTF-8 Markdown file. Existing prompt, stdout,
  and stderr logs remain available for diagnostics. A zero exit code without a
  readable, non-empty response is treated as a processing failure, so the task
  does not move to `done/`.
- After Codex succeeds and `.response.md` validation passes, the worker posts
  that file's content unchanged to the source Issue through
  `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`. It reuses the
  watcher's GitHub API client and the existing `GITHUB_*` settings; prompt,
  stdout, and stderr are never included in the comment.
- The task moves to `done/` only after the comment POST succeeds. GitHub HTTP or
  network errors leave the task in `processing/` with all Codex logs preserved.
  The worker validates that `issue_<number>.md` matches its `# Issue <number>`
  header before publishing.
- A successful POST writes `automation/logs/issue_<number>.commented` containing
  the GitHub comment ID. This marker prevents another POST during a local retry;
  a crash after GitHub accepts a comment but before the marker is written remains
  a small unavoidable duplicate window without remote idempotency support.
- Follow-up tasks use stem-specific response and marker files, for example
  `issue_12_comment_123.response.md` and `issue_12_comment_123.commented`.
  The worker validates both `# Issue` and `# Comment` headers, publishes the
  response back to the original Issue, and then moves the follow-up task to
  `done/` using the unchanged queue lifecycle.
- `CODEX_TASK_TIMEOUT_SECONDS` limits each Codex run. Timeout, launch failure,
  and non-zero exit codes keep the task in `processing/` and preserve logs.
- Alternative processors can still implement the `TaskProcessor` protocol and be
  injected into `CodexWorker`.
- If processing raises an exception, the task remains in `processing/` for
  inspection or an explicit retry policy.
- Worker startup and polling scan only `pending/`; they do not automatically
  reclaim files already left in `processing/`. After confirming that no
  `.commented` marker or conflicting pending/done task exists, retry an
  option-parsing failure by stopping the worker and moving that one task from
  `processing/` back to `pending/`, then restart the worker. This explicit move
  prevents silent duplicate execution after crashes.
- Queue paths, state/log paths, polling intervals, API options, and log levels are loaded from
  `.env`. The watcher checks all three queue directories before creating a task,
  so completed issues are not recreated.

## Signup flow (GitHub Issue #2, 2026-08-11)

- `/signup/` uses `core.forms.SignupForm`, based on Django's
  `UserCreationForm`, with Korean labels and browser autocomplete attributes.
- The Django language is Korean so built-in Django/allauth signup labels, help
  text, and validation messages are localized. The signup page's login link uses
  a dedicated high-contrast blue style.
- Successful signup creates both the auth user and its `UserAccess` row in one
  database transaction, then logs the user in explicitly through Django's
  `ModelBackend`, records one `signup` event, and redirects to `/missions/`.
  The explicit backend is required because the project also keeps allauth's
  authentication backend enabled for social login.
- Invalid submissions render field-specific validation errors without creating
  a user. An already authenticated user is redirected to `/missions/`.
- Signup behavior is covered by `core/tests/test_signup.py`.

> AI 인수인계용 프로젝트 문서. 사람이 읽기 위한 README가 아니라, 다음 대화의 AI가 이 파일 하나만 읽고 개발을 이어받도록 작성한다.
> 기준일: 2026-07-22
> 프로젝트 루트: `C:\노세영\코딩\프로젝트\컴활2급`
> 현재 우선순위: `물류관리사(logistics)`를 운영하면서 이후 자격증을 `Subject` 기반으로 확장한다.

---

## 1. 프로젝트 개요

### 프로젝트 목적

Django 기반 다중 자격증 학습 웹앱이다. 현재 활성 자격증은 물류관리사이며, 이후 다른 자격증을 같은 학습 엔진에 추가한다.

### 서비스 대상

- 자격증 수험생: 현재 물류관리사, 이후 추가되는 자격증
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

- `logistics`: 물류관리사, 현재 활성 기본 과목

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

과목/자격증 단위. `code`는 unique + db_index. 현재 활성 핵심 코드는 `logistics`이며 새 코드를 추가할 수 있다.

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

- `DEFAULT_SUBJECT_CODE = "logistics"` (기존 내부 호출부 호환 이름)
- `LOGISTICS_SUBJECT_CODE = "logistics"`
- `get_current_subject(request)`가 현재 과목을 반환하고 세션이 비어 있으면 default subject를 저장한다.
- `seed_platform_subjects()`로 현재 활성 기본 과목인 물류관리사를 생성.
- null subject Mission을 임의 과목에 연결하지 않는다. import 시 `subject_code`를 명시한다.

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
- 마지막 추천 문제를 풀면 오늘 정답률, 가장 취약했던 영역, 영역별 오답 수와 다음 복습 행동을 완료 화면에 표시한다.
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

- `Subject.code`: 현재 `logistics`; 이후 자격증마다 고유 코드 추가
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

- `subject_code`가 없으면 데이터 혼입을 막기 위해 해당 행을 건너뛴다.
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

현재 활성 기본 자격증인 `logistics` Subject 생성/갱신.

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
2. 물류관리사에 종속된 단일 과목 구조로 만들지 말고 `Subject` 확장성을 유지한다.
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
## 모바일 개인 학습 코치 (2026-09-02)

- 문제 제출 시 `찍었어요 / 헷갈려요 / 확실해요` 확신도를 기록한다. 맞혔더라도 찍은 문제는 약점 후보로 남긴다.
- 틀린 선택지와 찍은 답은 `ConfusionCard`로 저장하여 홈의 개인 혼동 카드에서 재학습한다. 같은 문제를 확실하게 맞히면 카드를 완료 처리한다.
- 물류관리사 35개 챕터를 약점 생명주기(관찰, 집중 필요, 훈련, 재평가, 극복, 재발)와 연결한 약점 지도를 제공한다.
- 패턴 집중 훈련은 모바일에서 부담 없이 끝낼 수 있도록 한 세션 3문제로 제한한다.
- 홈의 기본 학습 제안은 5문제·약 10분 처방이며, 3일 이상 공백이면 3분 복귀 학습 메시지를 우선한다.
- 오늘 가능한 시간 선택은 5분=3문제, 10분=5문제, 20분=10문제로 추천 제한과 예상 시간을 함께 변경한다. 추천 서비스는 화면의 선택값을 전달받으며 고정 5문제로 자르지 않는다.
- 학습 홈의 첫 행동은 `오늘 N분 학습 시작`으로 고정하고, `처음 푸는 문제`, `전에 틀린 문제`처럼 학습자 언어를 사용한다. 시험 전 카드는 보조 복습으로 둔다. 모의고사의 별표 표시는 점수와 무관하게 최종 제출 전에 다시 볼 문항을 표시하는 기능임을 화면에서 설명한다.
- `StudyProfile.target_exam_date`를 기준으로 D-Day와 기간별 행동 전략을 표시한다.
- 합격 준비도는 점수만 표시하지 않고 과락 위험, 미해결 약점, 모의고사 부족을 구체적인 다음 행동으로 번역한다.
- 마이그레이션 `0038_mobile_personal_coach`가 기본 원터치 오답 원인 5개를 함께 생성한다.

## 학습 신뢰성·복습 연결 개선 (2026-09-08)

### 문제 검수와 오류 문항

- `Mission.review_status`는 `unreviewed`(미검수), `verified`(검수 완료), `confirmed_error`(오류 확인·출제 중지)를 구분한다.
- 일반 사용자의 오류 신고(`Inquiry`)와 운영자의 콘텐츠 판정은 별개다. 신고 접수만으로 문항이 자동 중지되지 않는다.
- `confirmed_error` 문항은 `is_usable_for_set=False`가 강제되며, import나 품질 점검 명령이 묵시적으로 다시 활성화할 수 없다. 새 추천·문제 세트·집중 훈련·모의고사에서 제외한다.
- 검수 매니페스트는 문제 본문·선택지·정답·해설의 정확한 fingerprint에만 적용한다. 내용이 달라지면 검수 완료 상태를 승계하지 않는다.
- 철도/화물자동차 경제적 효용거리 문항의 표준 원본은 `500,000 / (5,000 - 2,500) = 200km`, 선택지 3번이다.

### 안전한 재평가

- `regrade_mission_records --external-id ...`는 기본 dry-run이며 현재 fingerprint, 영향 Attempt/시험/세트 수와 자동 판정 불가 기록을 출력한다.
- 실제 적용에는 `--apply --confirm-fingerprint <dry-run 값>`이 모두 필요하다. 하나의 트랜잭션 안에서 기존 제출 답안은 보존하고 정오답, 시험·세트 점수, 오답 패턴, 혼동 카드, 약점 파생 상태를 재계산한다. 같은 명령을 다시 실행해도 추가 변경이 없어야 한다.
- 과거 `PatternTrainingSession`은 문항별 FK를 저장하지 않았으므로 과거 집계값은 추측해 고치지 않는다. 새 훈련 결과는 세션에 `attempt_id`를 보관하여 해설과 오답 재훈련에 사용한다.
- 운영 DB에는 import나 재평가를 임의 적용하지 않는다. 먼저 dry-run을 검토하고 DB 백업 후 명시적으로 적용한다.

### 문제 세트와 학습 상태

- 자동 문제 세트는 `ProblemSet.generation_key`(`자격증|과목|챕터|배치`)를 안정 식별자로 사용한다. 부분 CSV import도 해당 챕터의 DB 전체 문항으로 세트를 다시 구성한다.
- 세트 메타데이터의 챕터와 실제 모든 문항의 챕터·자격증·출제 가능 상태가 일치해야 추천된다. 오래된 자동 세트는 과거 세션 보존을 위해 삭제하지 않고 비활성화한다.
- `rebuild_generated_problem_sets --subject-code <code>`는 기본 dry-run이며 `--apply`를 지정해야 실제 세트를 동기화한다.
- 한 번의 정답이나 같은 날 반복 정답은 숙달로 표현하지 않는다. `이번에 맞힘`, `맞혔지만 확신 부족`, `반복 복습 필요`, `시간이 지난 뒤 다시 맞힘`, `근거가 쌓인 안정 상태`를 공용 판정으로 사용한다. 안정 상태는 확신 있는 정답과 3일 이상의 재평가 간격이 필요하다.

### 집중 훈련·오답·시험

- 집중 훈련 결과는 틀린 문제를 먼저 보여주고 문제·내 답·정답·등록 해설·검수된 ConceptUnit을 표시한다. 개념 자료가 없으면 준비 중이라고 명시하며 결과 조회 자체로 Attempt를 만들지 않는다.
- 오답노트는 과거 Attempt의 읽기 전용 `해설 확인`과 새 Attempt를 만들 수 있는 `다시 풀기`를 분리한다.
- 시험 진행 중 답안의 기준 저장소는 `ExamSessionMission.draft_answers`다. 이전·다음·건너뛰기·번호 이동·검토 표시를 사용해 최종 제출 전까지 수정할 수 있다. 별도의 저장 확인 링크는 두지 않고 `저장 중`, `답안이 저장됐어요`, `저장하지 못했어요` 상태를 `aria-live` 영역에 자동 표시한다.
- 명시적 최종 제출 또는 서버 기준 시간 종료 때만 답안을 확정 채점하고 Attempt를 한 번 동기화한다. 미응답은 시험 점수에서는 0점이지만 Attempt·오답·약점에는 기록하지 않는다.
- 홈은 현재 자격증의 진행 중 시험과 저장한 응답 수를 보여주며 이어하기 링크를 제공한다.

### 현재 무료 정책과 남은 제한

- `PREMIUM_GATING_ENABLED=False`인 동안 모든 학습 기능은 무료다. 기존 `UserAccess`와 premium 선택지는 향후 정책 전환을 위해 모델에 남기되 무료 화면에서는 프리미엄 신청을 노출하지 않는다.
- 기존 진행 중 시험에 나중에 `confirmed_error`로 판정된 문항이 포함된 경우 문항을 조용히 삭제하지 않는다. 시험 구성과 과거 답안을 보존하고 운영자가 재시작/무효화 정책을 결정해야 한다.
- 실제 휴대폰 실기 검증은 별도다. 자동 테스트와 반응형 CSS 검사는 실제 Android/iOS 브라우저 검증을 대신하지 않는다.
- 현재 저장소의 `.venv` launcher는 원래 가리키던 Python 3.13 설치 경로를 찾지 못해 직접 실행할 수 없다. 로컬 검증에서는 번들 Python 3.12와 `.venv/Lib/site-packages`를 사용했으며, 운영 전 `.venv`를 재생성해야 한다.

## 생성 문제 동기화·실전 모의고사 UX (2026-09-11)

### generated 문제 반영

- `sync_generated_missions --subject-code <code> --create-problem-sets`가 `generated/<code>/`의 모든 CSV를 결정적 순서로 동기화한다. 실제 행 처리 규칙은 기존 `import_missions`만 사용하며 별도 importer를 만들지 않는다.
- 동기화는 `external_id` 기준으로 멱등하며 파일별·전체 `created/updated/skipped/errors`를 출력한다. 한 파일의 오류는 다른 파일 처리를 막지 않고, `--fail-on-error`를 지정한 CI에서만 마지막에 실패 코드로 처리한다.
- 웹 요청과 `AppConfig.ready()`에서는 DB를 쓰지 않는다. 로컬은 관리 명령을 명시적으로 실행하고, Render는 `scripts/render_start.sh`에서 migration 후 best-effort로 동기화한다. 동기화 자체가 실패해도 기존 DB로 Gunicorn을 시작한다.
- `confirmed_error`와 출제 보류 상태는 재동기화가 임의로 해제하지 않으며 모의고사 출제에서 계속 제외한다.
- 2026-09-11 기준 `generated/logistics`의 6개 CSV, 총 600문항을 로컬 DB에 동기화했다. `core/static/images/questions/logistics`의 PNG 66개는 모두 `MissionImage`에 연결되어 있으며 디스크 미존재·미연결 경로가 없다.
- `logistics_27-2.csv`는 44번과 45번 행 사이의 누락된 줄바꿈을 복구하고, 실제 `27회-2` 이미지 폴더와 달랐던 11개 경로를 바로잡았다. 이후 재동기화 dry-run은 `created=0, updated=0, skipped=600, errors=0`으로 멱등성을 확인했다.

### 실전 기록과 점수

- 실전 1교시와 2교시는 DB의 연결된 두 `ExamSession`을 유지하되 `exam_history`에서 하나의 카드로 묶는다. 교시별 상태·점수, 5과목 점수, 전체 평균과 최종 판정을 함께 표시한다.
- 상태별 CTA는 `2교시 시작`, `이어서 풀기`, `결과 보기`, 두 교시 완료 시 `종합 결과 보기`다. 2교시 타이머는 사용자가 시작할 때만 갱신된다.
- `ExamSession.score`는 `FloatField`이며 모든 시험 백분율은 소수 첫째 자리까지 계산한다. 따라서 15/120은 DB·결과·기록·통계에서 12.5점이다. 정수 점수는 화면에서 불필요한 `.0` 없이 표시한다.

### 모바일 결과·저장 안정성

- 시험 결과 첫 흐름은 최종 판정과 과목별 점수, 약점 3개, 대표 오답 5개를 우선한다. 전체 오답은 별도 URL에서 서버 사이드 20개 단위로 조회하며, 오답노트도 20개 단위 페이지네이션과 필터 querystring을 유지한다.
- 기본 `window.confirm()` 대신 응답·미응답·다시 볼 문항 수와 변경 불가 안내를 포함한 접근 가능한 `<dialog>`를 사용한다. Escape, 키보드 포커스, 명확한 취소/최종 제출 동작을 제공한다.
- 자동 임시 저장과 다음 문항 이동 POST를 Promise queue로 직렬화하여 SQLite 쓰기 경합을 피한다. 통신 실패 시 선택 답안은 sessionStorage와 폼에 유지하며 `저장 다시 시도` 동작을 제공한다. 최종 채점과 Attempt 동기화의 기존 멱등성은 유지한다.

## 문항 버전·과거 채점 무효화·변경 감시 (2026-09-12)

- `Mission.content_version`, `content_fingerprint`, `grading_fingerprint`가 문항의 변경 이력을 식별한다. 지문·보기·해설 등의 변경은 content version을 올리지만, 객관식의 정답 번호 등 실제 채점 기준이 바뀔 때만 grading fingerprint가 바뀐다.
- 모든 새 `Attempt`는 풀이 당시 문항 버전, 두 fingerprint와 지문·보기·정답·해설 snapshot을 저장한다. migration `0045_mission_content_versioning`은 기존 문항과 Attempt도 현재 상태를 version 1로 backfill하며 기록을 삭제하거나 재채점하지 않는다.
- 채점 fingerprint 변경 시 기존 유효 Attempt는 `grading_valid=False`와 무효 시각·사유를 기록한다. 원본 Attempt와 오답 원인/패턴 연결은 보존하되 통계, 오답노트, 추천, 로드맵, 약점 계산에서는 제외한다. 해당 사용자의 파생 약점과 혼동 카드는 남은 유효 Attempt만으로 재구성한다.
- `import_missions`와 `sync_generated_missions`는 문항 변경으로 무효화된 Attempt 수와 영향받은 사용자 수를 로그에 표시한다. 동일 CSV를 다시 실행하는 멱등성은 유지한다.
- `watch_generated_missions`는 `generated/<subject>` CSV 및 해당 정적 이미지 파일의 이름과 바이트 fingerprint를 별도 프로세스에서 감시한다. 변경 시 기존 멱등 동기화를 실행하고 실패하면 다음 주기에 재시도한다. 웹 요청과 `AppConfig.ready()`에서는 DB를 쓰지 않는다.
- 로컬 자동 감시는 `python manage.py watch_generated_missions --subject-code logistics`를 별도 터미널에서 실행한다. 주기는 `.env`의 `DJANGO_GENERATED_MISSION_WATCH_INTERVAL_SECONDS`로 설정한다. Render는 기존 `scripts/render_start.sh`의 migration 후 1회 동기화를 유지한다.
- 2026-09-12 최초 실제 감시 실행에서 `logistics_27-1.csv`와 DB가 달랐던 66문항을 갱신했고, 정답이 변경된 문항을 과거에 푼 사용자 1명의 Attempt 4건을 보존 상태로 무효화했다.
