# 🤖 AI 블로그 자동화 대시보드

Google Trends → AI 콘텐츠 생성 → 이미지 생성 → Google Blogger 발행까지 전 과정을 자동화하는 Streamlit 기반 웹 앱.

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
| 웹 프레임워크 | Streamlit ≥ 1.35 | 사이드바 네비게이션, session_state |
| LLM (1순위) | vLLM (자체 호스팅) | Google Gemma 4 31B-it, OpenAI 호환 API |
| LLM (fallback) | Anthropic Claude API | claude-sonnet-4-6 기본값 |
| 이미지 생성 | Pollinations.ai | 무료, API 키 불필요 (기본값) |
| 이미지 생성 | HuggingFace SD XL | 무료 토큰 필요 |
| 이미지 생성 | DALL-E 3 | 유료, OpenAI API 키 필요 |
| 트렌드 수집 | Loword API + Google Trends RSS | 실시간 급상승 검색어 |
| 발행 | Google Blogger API v3 | OAuth 2.0 (PKCE S256) |
| 발행 | 네이버 블로그 (Playwright) | 공식 API 없음, UI 자동화 |
| 환경 변수 | python-dotenv | `.env` 파일 |

---

## 📁 프로젝트 구조

```
blog/
├── app.py                    # 메인 Streamlit 앱 (사이드바 네비게이션)
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
    ├── trend_collector.py    # 트렌드 수집 (Loword + Google RSS)
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
streamlit run app.py --server.port 8501

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

**GUI가 있는 환경 (권장 — 캡차·2단계 인증 대응 가능)**

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
