# ⚡ AI Hub

**Multi-AI Platform** — ChatGPT, Gemini, Azure OpenAI, Claude, Grok을 하나의 인터페이스에서 사용하는 통합 AI 플랫폼

🌐 **Live Demo**: [shinwookyi-ai.onrender.com](https://shinwookyi-ai.onrender.com)

---

## ✨ Features

### 🤖 5개 AI 프로바이더 통합
| Provider | Model | API |
|----------|-------|-----|
| **ChatGPT** | gpt-4o-mini | OpenAI |
| **Gemini** | gemini-2.5-flash | Google AI |
| **Azure OpenAI** | gpt-4o-mini | Microsoft Azure |
| **Claude** | claude-sonnet-4 | Anthropic |
| **Grok** | grok-3-mini-fast | xAI |

### 🎯 7가지 대화 모드
- 💬 **Chat** — 개별 AI와 1:1 대화
- 🔄 **Compare All** — 모든 AI에게 동시에 질문하고 답변 비교
- ⚔️ **Debate** — AI vs AI 토론
- 🗣️ **Discussion** — 모든 AI가 참여하는 라운드 토빈 토론
- 🏆 **Best Answer** — 모든 AI 답변 중 최고를 투표로 선정
- 🎭 **Persona Debate** — 페르소나 역할극 토론
- 🧠 **Persona Discussion** — 페르소나 집단 토론 (다수 참여)

### 👤 20+ 페르소나 시스템
역사적 인물과 전문가 페르소나로 AI가 그 관점에서 답변:

| 카테고리 | 페르소나 |
|----------|---------|
| 비즈니스 | Elon Musk, Steve Jobs, J.P. Morgan |
| 전략 | Sun Tzu, Sima Yi (사마의), Tokugawa Ieyasu |
| 철학 | Nietzsche, Schopenhauer |
| 과학 | Nikola Tesla, Thomas Edison |
| 심리/프로파일링 | Carl Jung, FBI Profiler |
| 동양학 | I Ching Master (주역), Saju Master (사주) |
| 어시스턴트 | Personal Assistant, Devil's Advocate |
| 기타 | Albert Einstein, Donald Trump |

### 📊 시각화 (Visualization)
- **Markdown** 렌더링 (표, 코드 하이라이팅)
- **Mermaid** 다이어그램 (플로우차트, 시퀀스 등)
- **Chart.js** 차트 (파이, 바, 라인 차트)

### 📁 파일 지원
- 멀티 파일 업로드 (드래그 앤 드롭)
- PDF, DOCX, XLSX, CSV, TXT 등 지원
- URL 가져오기 (웹페이지 분석)

### 💾 대화 기록 (Supabase)
- 클라우드 DB에 대화 자동 저장
- 이전 대화 조회/검색
- 대화 삭제

### 🌐 자동 언어 감지
- 한국어, 영어, 일본어 등 자동 감지
- 사용자 언어로 답변

---

## 🚀 Quick Start

### 필수 요구사항
- Python 3.10+
- API Keys (1개 이상): OpenAI, Gemini, Anthropic, xAI

### 설치

```bash
git clone https://github.com/shinwookyi-oss/ai-hub.git
cd ai-hub
pip install -r requirements.txt
```

### 환경변수 설정

```bash
# 필수 (최소 1개)
export OPENAI_API_KEY=sk-...
export GEMINI_API_KEY=AIza...
export ANTHROPIC_API_KEY=sk-ant-...
export GROK_API_KEY=xai-...

# 선택
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT=https://...

# 대화 기록 (Supabase)
export SUPABASE_URL=https://xxx.supabase.co
export SUPABASE_KEY=eyJ...

# 로그인 (기본값: admin / aihub2026)
export APP_USERNAME=admin
export APP_PASSWORD=your_password
```

### 실행

```bash
python app.py
```

👉 http://localhost:5000 접속

---

## 🌐 Cloud Deployment (Render)

1. GitHub 리포를 Render에 연결
2. **Environment Variables** 에 API 키 추가
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300`

---

## 📁 Project Structure

```
ai-hub/
├── app.py              # Flask 메인 앱 (UI + API + 인증)
├── ai_hub.py           # AIHub 코어 클래스 (5 프로바이더, 페르소나)
├── requirements.txt    # Python 의존성
├── Procfile            # Render/Heroku 배포 설정
└── .gitignore
```

---

## 🔧 Tech Stack

- **Backend**: Python, Flask
- **Frontend**: Vanilla HTML/CSS/JS (Genspark-style split panel)
- **AI SDKs**: OpenAI, Google GenAI, Anthropic
- **Database**: Supabase (PostgreSQL)
- **Hosting**: Render
- **Visualization**: Mermaid.js, Chart.js, Marked.js

---

## 📄 License

Private project

---

## 👨‍💻 Author

**shinwookyi-oss**
