# 🤖 AI 블로그 자동화 대시보드

Google Trends → AI 콘텐츠 생성 → 이미지 생성 → Google Blogger 발행까지 전 과정을 자동화하는 Flask 기반 웹 앱.

---

## 🔄 전체 파이프라인

```
트렌드 수집 → 키워드 선택 → 주제 추천 → 본문 생성 → 이미지 생성 → Blogger 발행
 (구글/네이버)    (수동)      (vLLM/Claude) (vLLM/Claude) (Pollinations 등) (OAuth 2.0)
```

---

## 🏗️ 기술 스택

| 분류 | 기술 | 비고 |
|------|------|------|
| 웹 프레임워크 | Flask ≥ 3.0 | 서버 세션 기반 대시보드 |
| LLM (1순위) | vLLM (자체 호스팅) | Google Gemma 4 31B-it, OpenAI 호환 API |
| LLM (fallback) | Anthropic Claude API | claude-sonnet-4-6 기본값 |
| 이미지 생성 | Pollinations.ai | 무료, API 키 불필요 (기본값) |
| 이미지 생성 | HuggingFace SD XL | 무료 토큰 필요 |
| 이미지 생성 | DALL-E 3 | 유료, OpenAI API 키 필요 |
| 트렌드 수집 | Loword API + Google Trends RSS + signal.bz | 실시간 급상승 검색어 |
| 발행 | Google Blogger API v3 | OAuth 2.0 (PKCE S256) |
| 발행 | 네이버 블로그 (Playwright) | 공식 API 없음, UI 자동화 |
| 환경 변수 | python-dotenv | `.env` 파일 |

---

## 📁 프로젝트 구조

```
blog/
├── flask_app.py              # 메인 Flask 앱 (대시보드/로그인/발행)
├── app.py                    # 이전 Streamlit 앱 (레거시)
├── requirements.txt          # Python 패키지 목록
├── .env                      # 환경 변수 (API 키 등, git 제외)
├── .env.example              # 환경 변수 예시
├── client_secret.json        # Google OAuth 클라이언트 비밀키 (git 제외)
├── token.json                # Google OAuth 토큰 (git 제외, 자동 생성)
├── data/                     # 로컬 저장 포스팅 (JSON)
├── naver_setup.py            # 네이버 최초 1회 수동 로그인 → 세션 저장 스크립트
├── naver_session.json        # 네이버 로그인 세션 (git 제외, naver_setup.py로 자동 생성)
├── naver_errors/             # 네이버 발행 실패 시 스크린샷 저장 (git 제외)
└── modules/
    ├── trend_collector.py    # 트렌드 수집 (Loword + Google RSS + signal.bz)
    ├── content_generator.py  # LLM 콘텐츠 생성 (vLLM → Claude 자동 fallback)
    ├── image_generator.py    # 이미지 생성 (다중 프로바이더, 자동 fallback)
    ├── blogger_publisher.py  # Google Blogger API 발행 (PKCE OAuth)
    └── naver_blog_poster.py  # 네이버 블로그 발행 (Playwright UI 자동화)
```

---

## ⚙️ 환경 변수 (.env)

```env
# LLM 서버 (vLLM)
LLM_ADDR=http://192.168.1.1:8000
LLM_MODEL=google/gemma-4-31b-it
LLM_API_KEY=EMPTY

# LLM Fallback / 이미지
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6

# 이미지 생성
IMAGE_PROVIDER=pollinations        # pollinations | huggingface | claude | dalle
OPENAI_API_KEY=sk-...              # DALL-E 3용 (선택)
HUGGINGFACE_TOKEN=hf_...           # HuggingFace SD XL용 (선택)

# Google Blogger
BLOGGER_BLOG_ID=1234567890123456789
BLOGGER_BLOG_URL=https://superipnet.blogspot.com   # 네이버 글 상하단에 넣을 방문 링크

# 네이버 블로그 (Playwright UI 자동화, 공식 API 없음)
NAVER_ID=your_naver_id
NAVER_PW=your_naver_password
NAVER_BLOG_ID=your_naver_blog_id
```

---

## 🚀 실행 방법

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. Playwright 브라우저 설치 (네이버 블로그 발행에 필요, 최초 1회)
playwright install chromium

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일 편집 후 API 키/네이버 계정 입력

# 4. (네이버 발행 사용 시) 최초 1회 수동 로그인 → 세션 저장
python naver_setup.py

# 5. 앱 실행
python flask_app.py

# 또는 run.sh 사용
bash run.sh
```

---

## 🟢 네이버 블로그 발행 설정

네이버 블로그는 공식 발행 API가 없어 Playwright로 실제 브라우저(Chromium)를 자동 조작해 발행합니다.

### 1. Playwright Chromium 설치 (최초 1회)

```bash
pip install playwright
playwright install chromium
```

### 2. `.env`에 네이버 계정 입력

```env
NAVER_ID=네이버_아이디
NAVER_PW=네이버_비밀번호
NAVER_BLOG_ID=블로그_아이디   # blog.naver.com/{여기} 의 {} 부분
```

### 3. 최초 1회 로그인 (세션 저장)

**앱에서 바로 (권장 — 터미널/VNC 불필요)**

설정 탭 → 🟢 네이버 블로그 섹션 → **🔑 네이버 로그인 시작** 클릭.
캡차 등 추가 인증이 뜨면 그 화면이 그대로 앱에 표시되니, 화면을 보고 정답을 입력한 뒤 **제출**을 누르면 됩니다.
세션은 자동으로 `naver_session.json`에 저장됩니다.

**GUI가 있는 환경 (터미널에서 직접, 대안)**

```bash
python naver_setup.py
```

- 브라우저 창이 자동으로 열리며 네이버 로그인 페이지로 이동합니다.
- 브라우저 안에서 **직접** 아이디/비밀번호를 입력하고, 캡차나 2단계 인증이 뜨면 함께 처리합니다.
- 로그인이 완료되면 자동으로 감지해 `naver_session.json`에 로그인 세션을 저장하고 종료합니다. (최대 5분 대기)

**GUI 없는 서버 (완전 headless)**

```bash
python naver_setup.py --headless
```

- `.env`의 `NAVER_ID` / `NAVER_PW`로 자동 로그인을 시도합니다. 브라우저 창이 뜨지 않아 X윈도우가 없는 서버에서도 실행됩니다.
- 네이버가 캡차나 2단계 인증을 요구하면(서버 IP가 낯설 때 자주 발생) 자동 로그인은 실패하며, `naver_errors/`에 스크린샷이 저장됩니다. 이 경우 GUI가 있는 PC에서 플래그 없이 실행해 수동으로 로그인한 뒤, 생성된 `naver_session.json`을 서버의 블로그 폴더로 복사하세요.

로그인 세션이 저장되면 앱에서 "🟢 네이버 발행" 버튼으로 발행할 수 있습니다.

### 4. 세션 만료 / 로그인 실패 시 재설정

발행 시도 시 아래와 같은 오류가 뜨면 세션이 만료되었거나 자동 로그인이 캡차·2단계 인증에 막힌 경우입니다.

```
네이버 자동 로그인 실패 (캡차 또는 2단계 인증으로 추정됩니다). ...
```

해결 방법:

```bash
# 1. 만료된 세션 파일 삭제
rm naver_session.json

# 2. 세션 재발급 (서버라면 --headless, GUI 환경이면 플래그 없이)
python naver_setup.py --headless
```

- 발행이 실패하면 `naver_errors/` 폴더에 실패 시점의 스크린샷이 저장되니, 어느 단계에서 막혔는지 확인할 때 참고하세요.
- 네이버가 Smart Editor의 화면 구조(클래스명 등)를 변경하면 `modules/naver_blog_poster.py`의 셀렉터 업데이트가 필요할 수 있습니다.
- 배포 파이프라인은 `playwright install chromium`(브라우저 바이너리)까지만 자동 실행합니다. 서버에 Chromium 실행에 필요한 OS 라이브러리(libnss3 등)가 없다면 최초 1회 아래 명령을 서버에서 직접 실행해주세요:
  ```bash
  sudo venv/bin/playwright install-deps chromium
  ```

---

## 🔑 Google Blogger OAuth 설정

### 1. Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. **APIs & Services > Library** → **Blogger API v3** 활성화
3. **Credentials > Create Credentials > OAuth 2.0 Client ID**
4. **애플리케이션 유형: Desktop app** 선택 ← 반드시 Desktop app!
5. JSON 다운로드 → `client_secret.json` 으로 저장

### 2. 앱에서 인증

1. 설정 탭 → `client_secret.json` 업로드
2. **🔗 인증 URL 생성** 클릭
3. URL을 브라우저에서 열고 Google 계정 승인
4. 브라우저가 `http://localhost/?code=...` 로 이동 → **"연결할 수 없음" 오류는 정상!**
5. 브라우저 주소창의 전체 URL 복사
6. 앱의 입력창에 붙여넣기 → **✅ 인증 완료** 클릭

### ⚠️ 자주 발생하는 오류

| 오류 | 원인 | 해결 |
|------|------|------|
| `redirect_uri_mismatch` | Web app 타입 OAuth 클라이언트 | Desktop app 타입으로 재생성 |
| `invalid_grant: Missing code verifier` | 이전 URL로 재시도 | 인증 URL 재생성 후 다시 시도 |
| `HttpError 403` | 블로그 소유자 계정으로 인증 안 됨 | 해당 블로그 소유자 구글 계정으로 OAuth 재인증 |
| `HttpError 404` | 블로그 ID 오류 | Blogger 대시보드 URL에서 숫자 ID 재확인 |

---

## 🔒 앱 로그인 게이트

### ✅ 현재 사용 중: 구글 계정 방식 (2026-07-28~ 재활성화)

`app.py`의 `_LOGIN_GATE_ENABLED = True`로 다시 켜져 있습니다. 원인 불명의
`invalid_grant`가 하루 종일 반복돼 한때 꺼뒀었지만(README 하단 "현재 상태"
섹션 참고), 사용자 요청으로 재활성화함 — 재현되는지는 계속 지켜봐야 함.

### 🔁 대체 수단: 비밀번호 방식

구글 로그인이 또 막히면 쓸 수 있도록 비밀번호 로그인도 코드로 남겨뒀습니다.
**구글 게이트가 켜져 있는 동안은 자동으로 건너뛰어지므로(`app.py`의
`_password_configured() and not _LOGIN_GATE_ENABLED` 조건)**, 지금은 `.env`에
`APP_PASSWORD`를 설정해도 비밀번호 화면이 뜨지 않습니다. 구글이 다시 막히면
`app.py`의 `_LOGIN_GATE_ENABLED = False`로 바꾸면 즉시 비밀번호 방식으로 전환됩니다.

- 설정: 서버 `.env`에 `APP_PASSWORD=원하는_비밀번호` 추가 후 재배포/재시작.
- 로그인 상태는 서명된 쿠키(`blog_auth_token`, 30일)로 유지.
- 구현: `modules/app_auth.py`의 `check_password()` / `make_password_session_token()` / `verify_password_session_token()`.
- 로그아웃 시 쿠키 삭제 직후 rerun하면 삭제가 브라우저에 반영되기 전이라 로그아웃이
  안 된 것처럼 보이는 레이스가 있어(구글 로그인 때와 동일 원인), rerun 대신 새로고침
  안내 메시지로 처리하도록 고쳐둠.

### 🔧 구글 계정 방식 설정 방법

#### 1. Google Cloud Console에서 별도 OAuth 클라이언트 생성

Blogger 연동용 `client_secret.json`(Desktop app 타입)과는 **다른, 별도의 클라이언트**가 필요합니다.
Desktop app 타입은 로그인 후 실제 사이트로 자동 복귀가 안 되기 때문입니다.

1. [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services > Credentials**
2. **Create Credentials > OAuth 2.0 Client ID**
3. **애플리케이션 유형: Web application** 선택 ← Blogger용과 다름, 반드시 Web application!
4. **승인된 리디렉션 URI**에 앱 접속 주소를 정확히 등록 (예: `https://blog.superip.net`)
5. JSON 다운로드 → `login_client_secret.json` 으로 저장

#### 2. 앱에서 설정

1. 설정 탭 → **🔒 앱 로그인 (구글 계정)** 섹션
2. **앱 접속 주소**: 위 리디렉션 URI와 정확히 일치하는 값 입력
3. **로그인 허용 구글 이메일**: 접근을 허용할 계정 1개 입력
4. `login_client_secret.json` 업로드
5. **💾 설정 저장** 클릭

저장 직후부터 로그인 게이트가 켜집니다. 다음 접속부터 구글 로그인 화면이 먼저 뜨고,
지정한 이메일로 로그인해야만 대시보드가 보입니다.

#### 로그인 방식

"🔑 구글 계정으로 로그인" 링크를 누르면 같은 탭에서 구글 로그인 화면으로 이동했다가,
로그인을 마치면 자동으로 이 앱으로 돌아옵니다 (새 창 없이, 모바일 포함 모든 환경에서 동일하게 동작).

#### ⚠️ 주의

- 이메일을 잘못 입력하고 저장하면 본인도 접근이 막힐 수 있습니다. 이 경우 서버에서
  `.env`의 `ALLOWED_GOOGLE_EMAIL`을 수정하거나 `login_client_secret.json`을 지우면
  게이트가 다시 꺼집니다.
- 로그인 상태는 서명된 쿠키(`blog_auth_token`, 30일)로 유지되며, 서버가 재시작되거나
  새로고침해도 자동으로 복원됩니다.

#### 🚧 현재 상태 (2026-07-27): 로그인 게이트 임시 비활성화

`app.py` 상단의 `_LOGIN_GATE_ENABLED = False` 플래그로 로그인 게이트를 꺼둔 상태입니다.
원인 불명의 `invalid_grant` 오류가 코드를 여러 번 고쳐도 반복돼(아래 변경 이력 참고),
사용자 요청으로 임시 비활성화했습니다. 관련 코드/모듈은 전부 그대로 남아있어
`_LOGIN_GATE_ENABLED = True`로 한 줄만 되돌리면 즉시 재활성화됩니다.

**다시 켜기 전에 확인/시도해볼 것 (우선순위 순):**
1. Google Cloud Console → OAuth 동의 화면 → "대상" 메뉴에서 게시 상태 확인.
   테스트 사용자를 등록해도(테스트 사용자 1명까지 확인) 여전히 `invalid_grant`가
   났었음 — 오전엔 테스트 사용자 0명으로도 로그인이 됐었다는 사용자 증언과
   모순되므로, 테스트유저 문제만으로는 설명 안 됨. "앱 게시"로 프로덕션 전환
   시도해볼 것 (openid/email 스코프만 써서 구글 별도 심사 불필요).
2. `login_client_secret.json`의 client_secret이 Google Cloud Console에서
   재발급/삭제된 적 있는지 확인 (재발급됐다면 서버의 파일을 새로 받은 것으로 교체).
3. 승인된 리디렉션 URI(`https://blog.superip.net`, 슬래시 없음)는 확인 완료 — 정확히 일치함.
4. 디버깅 로그: `modules/app_auth.py`의 `complete_login()`은 한때
   `google_auth_oauthlib.Flow` 대신 `requests`로 토큰 엔드포인트를 직접 호출해
   구글의 원본 응답을 그대로 노출하도록 바꿨었는데(커밋 701b752), 그래도
   `{"error": "invalid_grant", "error_description": "Bad Request"}` 라는 뭉뚱그린
   응답만 나와 추가 단서를 못 얻었음. 다시 시도할 때 이 방식을 참고해 더 상세한
   진단이 필요할 수 있음.
5. PC와 모바일 모두에서 재현됐고, 시간이 지나도(수 시간) 자연 해소되지 않아
   "구글 rate limit" 가설은 기각됨.

---

## 🖼️ 이미지 생성 프로바이더

전부 AI로 신규 생성된 이미지만 사용합니다 — 저작권자가 있는 실사 스톡 사진(Picsum 등)은 쓰지 않습니다.

| 프로바이더 | API 키 | 속도 | 품질 | 비고 |
|-----------|--------|------|------|------|
| `pollinations` | 불필요 | 보통 (10-30초) | AI 생성 | 기본값, 자동 fallback |
| `huggingface` | 필요 (무료) | 느림 | AI 생성 | SD XL 모델 |
| `claude` | 필요 | 보통 | AI 생성 | Claude가 프롬프트 강화 후 Pollinations |
| `dalle` | 필요 (유료) | 보통 | 최고 | DALL-E 3 |

**Fallback 순서**: 지정 프로바이더 → `pollinations` (키 없이 항상 시도 가능한 AI 생성 프로바이더)

---

## 🤖 LLM 자동 Fallback

```
vLLM 서버 요청
    ↓ 성공
vLLM 응답 반환
    ↓ 실패/오류
Claude API 요청
    ↓ 성공
Claude 응답 반환
    ↓ 실패
RuntimeError 발생
```

사이드바에서 현재 사용 중인 LLM과 모델명 실시간 확인 가능.

---

## 📝 AI 감지 회피 (Google AdSense 최적화)

콘텐츠 생성 프롬프트에 다음을 적용하여 사람이 쓴 글처럼 자연스럽게 작성:

- 문장 길이 불규칙 (짧은 문장 ↔ 긴 문장 혼재)
- 구체적 숫자·날짜·경험담 포함
- 구어체·감탄사·수사적 질문 사용
- AI 전형 표현 회피 ("~에 대해 알아보겠습니다" → "~얘기 해볼게요")
- E-E-A-T (경험·전문성·권위성·신뢰성) 반영
- 태그 8~10개 (핵심 키워드 + 연관 검색어 + 카테고리)

---

## 📋 주요 변경 이력

| 날짜 | 변경 내용 |
|------|-----------|
| 2026-08-08 | 네이버 수동 발행 UI 추가 — 발행 화면에 "네이버 수동 발행용 (블록별 복사)" 패널 신설. `naver_content_html`을 최상위 태그 단위(h2/p/div+img/ul 등)로 잘라(`_split_content_blocks`) 블록별 복사 버튼 제공, 이미지 블록은 다운로드/클립보드 이미지 복사 버튼 제공(fetch→blob→Clipboard API, 실패 시 새 탭 열기로 폴백). 자동 발행이 막히거나 수동으로 붙여넣고 싶을 때 사용. |
| 2026-08-08 | "AI 수정 적용" 클릭 시 에러 나던 문제 — **원인은 재현 못 함** (실제 서버 접근/스크린샷 없이 로컬에서는 LLM API 키가 없어 재현 불가, .env에 NAVER_* 만 있고 LLM_ADDR/ANTHROPIC_API_KEY는 로컬에 없음). 대신 다음 방어적 개선을 적용: (1) 지시사항 빈 값으로 제출되던 경로 차단(`required` + 서버측 검증), (2) refine 실패해도 기존 본문이 그대로 보존되도록 명확히 함, (3) `refine_content` 실패/빈 응답 시 사용자에게 구체적 안내 메시지 표시, (4) 모든 액션의 예외를 `app.logger.exception`으로 서버 로그에 풀 traceback 남기도록 추가 — 다음에 재현되면 서버 로그(`journalctl` 등)에서 정확한 원인을 볼 수 있음. (5) refine 폼에서 본문 전체를 매번 hidden input으로 왕복 전송하던 부분 제거하고 서버가 세션에 든 `ws["post_content_html"]`을 직접 사용하도록 변경(중복 전송 제거, 잠재적 인코딩/WAF 이슈 가능성 축소). **다음에 에러 재현되면 실제 에러 메시지/화면 캡처를 받아 정확한 원인으로 좁혀야 함.** |
| 2026-08-01 | 교차 링크 디자인 개선 — Blogger는 카드형 스타일 박스로, 네이버는 URL을 별도 문단으로 분리해 에디터 자동 링크 인식 가능성 높임 |
| 2026-08-01 | /settings POST 시 간헐적으로 나던 "405 Not Allowed / nginx" 원인 규명 — nginx 자체가 아니라 앞단 WAF가 특정 요청을 차단한 것이었음. 서버 쪽 WAF 설정에서 해결 (코드 변경 없음) |
| 2026-08-01 | 네이버용 콘텐츠를 발행 시점이 아닌 생성 시점(퀵 작성/이미지 생성 완료 직후)에 미리 만들어 캐싱 — 키워드 하나로 Blogger용/네이버용 두 버전이 거의 동시에 준비됨 |
| 2026-08-01 | 네이버·Blogger 교차 링크 추가(네이버는 텍스트, Blogger는 실제 링크), 네이버 발행 시 Blogger 원문과 다르게 재작성(중복 콘텐츠 방지). "동시 발행" 버튼 제거하고 각각 따로 발행하도록 변경, 그 과정에서 네이버 발행 단독 클릭 시 나던 TypeError 버그도 수정 |
| 2026-08-01 | 트렌드 수집을 IT 뉴스 전용으로 전환 — 로워드(네이버+구글 실시간 검색어)·signal.bz 제거하고 Google News IT/테크 토픽 RSS(한국어)만 사용 |
| 2026-08-01 | 블로그 방향을 IT 분야 집중으로 전환. 주제 추천 프롬프트를 "검색량은 있지만 문서 수 적은 IT 롱테일 키워드 10개, 초보가 상위노출 노리기 좋은 순서로 정렬" 방식으로 개편 |
| 2026-07-31 | 본문+이미지 동시 작성(백그라운드 스레드) 기능 추가, 발행 화면 상단에 실시간 진행상황 표시(자동/수동 새로고침), 발행 완료 후 "새 글 쓰기" 버튼으로 초기화 |
| 2026-07-31 | 발행 페이지에 "구글+네이버 동시 발행" 버튼 추가, 콘텐츠 생성 시 Google News RSS(영어판)로 해외 매체도 검색해 근거로 활용(반드시 한국어 번역 인용), 본문 생성·수정·이미지 삽입 시점마다 로컬(data/)에 자동 저장 |
| 2026-07-31 | 애드센스 "가치 낮은 콘텐츠" 반려 대응 — Blogger 라벨이 매 글 자유형 태그 8~10개로 그대로 들어가 50개 넘게 산발적으로 쌓이던 문제 수정. 콘텐츠 생성 시 고정 카테고리(이슈/뉴스, 건강정보, 라이프, 테크/IT, 엔터테인먼트) 중 하나를 태그 맨 앞에 포함하고, Blogger 발행 시 라벨 최대 5개로 제한 |
| 2026-07-27 | 주제 추천 프롬프트 수정 — 경쟁 심한 대표 키워드(인물명/사건명) 대신 검색 경쟁이 낮은 구체적 하위 주제를 우선 추천하도록 변경 |
| 2026-07-27 | 이미지 생성에 무료 이미지(Openverse CC 라이선스) 옵션 추가 시도 → 사용자 요청으로 원복 (AI 생성 이미지 자동 삽입 방식 그대로 유지) |
| 2026-07-27 | 로그인 쿠키가 URL 인코딩(`%40`,`%3A`) 안 풀려 파싱 실패하던 버그 수정 → 새로고침해도 로그인 유지되는 것 확인 |
| 2026-07-27 | app.py에 `from __future__ import annotations` 누락으로 Python 3.9(운영 서버 버전)에서 `str \| None` 문법이 즉시 크래시하던 버그 수정 |
| 2026-07-27 | OAuth 콜백을 서버 메모리(`_pending_verifiers`) 의존 없이 state 파라미터에 code_verifier를 실어 보내는 stateless 방식으로 재설계 |
| 2026-07-27 | 사이드바 메뉴가 사라지는 버그 수정 — 헤더를 CSS로 완전히 숨기면 사이드바 토글 버튼까지 사라짐 → `.streamlit/config.toml`의 `toolbarMode="minimal"`로 교체 |
| 2026-07-27 | 로그아웃 시 쿠키 컨트롤러의 `dict.pop()`이 KeyError로 크래시하던 버그 수정 (try/except 방어) |
| 2026-07-27 | 크롬 자동 번역 팝업 제거 (`html lang="ko"`, `translate="no"`, `<meta name="google" content="notranslate">`) |
| 2026-07-27 | **미해결**: 로그인 시 원인 불명의 `invalid_grant` 오류가 반복 발생 (PC/모바일 모두, 시간 경과에도 미해소). 여러 차례 원인 조사·재설계·롤백을 거쳤으나 근본 원인 특정 실패 → 사용자 요청으로 로그인 게이트 임시 비활성화(`app.py`의 `_LOGIN_GATE_ENABLED = False`). 자세한 내용은 위 "🚧 현재 상태" 섹션 참고 |
| 2026-07-26 | 구글 로그인 팝업 방식 시도 후 모바일 호환 문제로 단순 리디렉션 방식으로 원복, 네이버 로그인을 앱 화면에서 캡차 포함 직접 처리 가능하도록 추가 |
| 2026-07-25 | 트렌드 수집에 signal.bz 추가, 본문 가독성(줄간격·자간·여백) 개선 |
| 2026-07-25 | 구글 계정 로그인 게이트 추가 (지정 이메일만 접근 허용), 콘텐츠 생성 시 실제 검색 결과 반영, Blogger 포스팅 삭제 기능 |
| 2026-07-24 | 이미지 생성에서 Picsum(실사 스톡 사진) 제거 — 전 프로바이더 AI 신규 생성으로 통일 |
| 2026-07-23 | naver_setup.py에 --headless 옵션 추가 (GUI 없는 서버에서 ID/PW 자동 로그인) |
| 2026-07-22 | 구글/네이버 발행 버튼 분리 (독립 실행), 배포 파이프라인 안정화 |
| 2026-07-22 | 네이버 블로그 동시 발행 기능 추가 (Playwright UI 자동화) |
| 2026-07-22 | AI 감지 회피 프롬프트 강화, 태그 8~10개로 확대 |
| 2026-07-22 | OAuth PKCE S256 직접 구현 (invalid_grant 오류 해결) |
| 2026-07-22 | OAuth Flow 클래스로 교체 (InstalledAppFlow PKCE 문제 해결) |
| 2026-07-22 | OAuth 클라이언트 타입 감지 (installed/web) 및 안내 개선 |
| 2026-07-22 | 블로그 연결 테스트 기능 추가 (test_blog_connection) |
| 2026-07-22 | 로컬 data 폴더 저장 기능 추가 |
| 2026-07-22 | 전체화면 로딩 모달 추가 (CSS st.spinner 오버레이) |
| 2026-07-22 | vLLM → Claude 자동 fallback 구현 |
| 2026-07-22 | 이미지 다중 프로바이더 + 자동 fallback (Pollinations/Picsum/HF/DALL-E) |
| 2026-07-22 | 사이드바 네비게이션으로 UI 전면 개편 (탭 → 사이드바) |
| 2026-07-22 | 매뉴얼 페이지 추가 |
