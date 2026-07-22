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
└── modules/
    ├── trend_collector.py    # 트렌드 수집 (Loword + Google RSS)
    ├── content_generator.py  # LLM 콘텐츠 생성 (vLLM → Claude 자동 fallback)
    ├── image_generator.py    # 이미지 생성 (다중 프로바이더, 자동 fallback)
    └── blogger_publisher.py  # Google Blogger API 발행 (PKCE OAuth)
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
IMAGE_PROVIDER=pollinations        # pollinations | picsum | huggingface | claude | dalle
OPENAI_API_KEY=sk-...              # DALL-E 3용 (선택)
HUGGINGFACE_TOKEN=hf_...           # HuggingFace SD XL용 (선택)

# Google Blogger
BLOGGER_BLOG_ID=1234567890123456789
```

---

## 🚀 실행 방법

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일 편집 후 API 키 입력

# 3. 앱 실행
streamlit run app.py --server.port 8501

# 또는 run.sh 사용
bash run.sh
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

| 프로바이더 | API 키 | 속도 | 품질 | 비고 |
|-----------|--------|------|------|------|
| `pollinations` | 불필요 | 보통 (10-30초) | AI 생성 | 기본값, 자동 fallback |
| `picsum` | 불필요 | 빠름 (1-2초) | 실사 사진 | 항상 성공, 2순위 fallback |
| `huggingface` | 필요 (무료) | 느림 | AI 생성 | SD XL 모델 |
| `claude` | 필요 | 보통 | AI 생성 | Claude가 프롬프트 강화 후 Pollinations |
| `dalle` | 필요 (유료) | 보통 | 최고 | DALL-E 3 |

**Fallback 순서**: 지정 프로바이더 → `pollinations` → `picsum`

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
