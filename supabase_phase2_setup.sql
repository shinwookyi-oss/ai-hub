-- ============================================================
-- AI Hub Phase 2: Automation Tables
-- Supabase SQL Editor에서 실행하세요.
-- ============================================================

-- 1. Schedules (자동 스케줄)
CREATE TABLE IF NOT EXISTS schedules (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT NOT NULL,
    name         TEXT NOT NULL,
    schedule_expr TEXT NOT NULL,          -- e.g. 'daily 09:00', 'weekly mon 09:00'
    prompt       TEXT NOT NULL,
    provider     TEXT DEFAULT 'chatgpt',
    folder_id    UUID REFERENCES folders(id) ON DELETE SET NULL,
    is_active    BOOLEAN DEFAULT true,
    is_running   BOOLEAN DEFAULT false,   -- 중복 실행 방지 락
    last_run_at  TIMESTAMPTZ,
    next_run_at  TIMESTAMPTZ,
    last_result  TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- 2. Workflows (다단계 AI 워크플로우)
CREATE TABLE IF NOT EXISTS workflows (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    steps       JSONB NOT NULL DEFAULT '[]',   -- [{name, prompt, provider}, ...]
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- 3. Webhooks (외부 이벤트 트리거)
CREATE TABLE IF NOT EXISTS webhooks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT NOT NULL,
    name                TEXT NOT NULL,
    token               TEXT UNIQUE NOT NULL,   -- 공개 엔드포인트 토큰
    prompt_template     TEXT NOT NULL,          -- {{payload}}, {{payload.field}} 사용 가능
    provider            TEXT DEFAULT 'chatgpt',
    folder_id           UUID REFERENCES folders(id) ON DELETE SET NULL,
    is_active           BOOLEAN DEFAULT true,
    last_triggered_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Row Level Security (선택 — Supabase RLS 사용 시)
-- ALTER TABLE schedules ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE webhooks  ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 설치 완료 후 Render 환경 변수 추가 (선택):
--   SCHEDULER_SECRET = <임의의 긴 문자열>
--     → GET /api/schedules/check?secret=<값> 로 외부 크론 트리거 가능
--     → UptimeRobot / GitHub Actions cron에서 매 5분마다 호출 권장
-- ============================================================
