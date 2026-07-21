# 🚀 AI-Powered Google Blogger Automation Dashboard

AI(Gemini, DALL-E/Imagen 등)를 활용하여 당일 트렌드 키워드 추출부터 주제 선정, SEO 최적화 본문(HTML) 및 이미지 생성, 그리고 구글 블로거(Blogger) 최종 발행까지 웹 대시보드에서 일괄 관리할 수 있는 파이썬 기반 블로그 자동화 프로젝트입니다.

---

## 📌 주요 기능 (Features)

1. **트렌드 키워드 수집 및 주제 선정**
   * 당일 이슈/트렌드 키워드 크롤링 및 추천
   * 키워드 기반 타겟 주제 및 제목 자동 생성
2. **AI 기반 SEO 최적화 본문 생성**
   * Google Gemini API 연동
   * 검색 엔진 최적화(SEO)용 소제목 태그(`<h2>`, `<h3>`) 포함 HTML 본문 자동 작성
3. **맞춤형 이미지 자동 생성 및 삽입**
   * 글 주제에 맞는 AI 이미지 생성
   * 이미지 URL 생성 및 HTML 본문 내 태그 삽입
4. **웹 대시보드 관리 (Streamlit 기반)**
   * 코딩 없이 직관적인 웹 인터페이스에서 콘텐츠 확인 및 수정 (Preview & Edit)
   * 원클릭 구글 블로거(Blogger) 자동 발행
5. **Google Blogger API 연동**
   * OAuth 2.0 인증을 통한 안전한 블로그 글 등록

---

## 🛠 기술 스택 (Tech Stack)

* **Language:** Python 3.10+
* **Web Framework:** Streamlit
* **AI Engine:** Google Gemini API (Text), OpenAI DALL-E / Google Imagen (Image)
* **Blog Platform:** Google Blogger (via Blogger API v3)
* **Automation & Tools:** Google Cloud Console OAuth 2.0, Requests, BeautifulSoup4

---

## 🏗 시스템 아키텍처 (Workflow)
