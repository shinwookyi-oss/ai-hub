---
description: Monthly AI model catalog update - check all providers for latest models and update app.py
---

# /update-models — AI 모델 카탈로그 업데이트

이 워크플로우는 AI Hub의 모델 카탈로그를 최신 상태로 유지합니다.

## 대상 파일
- `app.py` → `MODEL_CATALOG`, `TIER_MODELS`, `auto_route_model()`

## 실행 순서

### 1. 현재 모델 확인
// turbo
Read the current `MODEL_CATALOG` in `app.py` (around lines 47-60) to see all currently configured models.

### 2. 각 프로바이더 최신 모델 검색
Search the web for latest available API models from each provider:
- **OpenAI**: Search for "OpenAI API latest models available 2026" (gpt-*, o3, o4, etc.)
- **Google**: Search for "Google Gemini API latest models 2026" (gemini-*)
- **Anthropic**: Search for "Anthropic Claude API latest models 2026" (claude-*)
- **xAI**: Search for "xAI Grok API latest models 2026" (grok-*)
- **DeepSeek**: Search for "DeepSeek API latest models 2026" (deepseek-*)
- **Azure**: Check if Azure OpenAI has new model deployments available

### 3. 비교 및 보고
Compare found models with current catalog and present a table to the user:

| Provider | Current Models | Latest Available | Action |
|----------|---------------|------------------|--------|
| OpenAI   | ...           | ...              | Add/Remove/Keep |
| Google   | ...           | ...              | Add/Remove/Keep |
| ...      | ...           | ...              | ... |

Include pricing info if available.

### 4. 사용자 승인 후 업데이트
After user approves the changes:
1. Update `MODEL_CATALOG` in `app.py` — add new models, mark deprecated ones for removal
2. Update `TIER_MODELS` — assign new models to appropriate tiers
3. Update `auto_route_model()` — adjust routing logic for new best models
4. Update `templates/manual.html` — update model descriptions if needed

### 5. 커밋 & 푸시
// turbo
```
git add app.py templates/manual.html
git commit -m "Monthly model update: [describe changes]"
git push
```

## 등급별 모델 배정 기준
- **President**: 모든 모델 접근 가능
- **Director**: High-cost 최고급 모델 제외, 나머지 전부
- **Manager**: Low/Medium 비용 모델 5개
- **Staff**: Low 비용 모델 2개
- **Guest**: 최저 비용 모델 1개

## Auto 라우팅 우선순위
- **복잡한 질문** → 최신 최고급 모델 (현재: gpt-5.2-pro)
- **일반 질문** → 중간급 최신 모델 (현재: gpt-5.2)
- **간단한 질문** → 저비용 모델 (현재: gpt-4o-mini)
