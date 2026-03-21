---
description: AI Hub 스타일 점검 및 업그레이드 워크플로우
---

# AI Hub Style Check & Upgrade

이 워크플로우는 AI Hub의 CSS, PPTX, 문서 스타일을 최신 트렌드에 맞춰 점검하고 업그레이드합니다.

## 점검 대상 파일
- `static/css/style.css` — 전체 UI 디자인 시스템
- `templates/index.html` — 채팅 메시지 스타일, 마크다운 렌더링
- `app.py` — PPTX 슬라이드 생성 테마
- `templates/login.html` — 로그인 페이지 디자인

## 워크플로우 단계

### 1. 현재 스타일 분석
// turbo
현재 `style.css` 파일을 열어 아래 항목을 점검합니다:
- 폰트 크기 / line-height / letter-spacing
- 색상 팔레트 (accent, text, background)
- 마크다운 요소 스타일 (h1~h3, code, blockquote, table)
- 모바일 반응형 레이아웃
- 다크/라이트 테마 일관성

### 2. 최신 트렌드 비교
아래 기준으로 현재 스타일을 평가합니다:

**Typography 트렌드:**
- 컴팩트한 line-height (1.4~1.6)
- Negative letter-spacing (-0.01~-0.02em)
- 시스템 폰트 스택 또는 Inter/Pretendard

**색상 트렌드:**
- 글래스모피즘 (반투명 배경 + backdrop-blur)
- 그라데이션 악센트 (linear-gradient)
- 뉴트럴 텍스트 색상 (#d1d5db, #9ca3af)

**레이아웃 트렌드:**
- Rounded corners (12~16px)
- Subtle shadows + glow effects
- Micro-animations (hover, fade-in)

**코드 블록 트렌드:**
- VS Code 스타일 다크 배경
- 좌측 악센트 보더
- 복사 버튼 (구현 예정)

**PPTX 트렌드:**
- 상단/하단 악센트 바
- 페이지 번호
- 일관된 컬러 팔레트

### 3. 개선점 리스트 생성
점검 결과를 표 형태로 정리합니다:

```
| 항목 | 현재 | 최신 트렌드 | 우선순위 | 수정 필요 |
|------|------|-----------|---------|---------|
| line-height | ? | 1.4~1.6 | 높음 | ✅/❌ |
| ...
```

### 4. 사용자 승인
개선점 리스트를 사용자에게 보여주고 승인을 받습니다.

### 5. 스타일 적용
승인된 항목을 `style.css`, `app.py`, `index.html`에 적용합니다.

### 6. Git commit & push
// turbo
변경사항을 커밋하고 푸시합니다.
