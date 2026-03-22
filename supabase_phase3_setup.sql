-- ============================================================
-- AI Hub Phase 3: Integration Table
-- Supabase SQL Editor에서 실행하세요.
-- ============================================================

CREATE TABLE IF NOT EXISTS integrations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    type        TEXT NOT NULL,   -- 'slack' | 'notion' | 'email' | 'calendar'
    name        TEXT NOT NULL,
    config      JSONB NOT NULL DEFAULT '{}',
    is_active   BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- config 필드 구조 (type별):
--
-- slack:    { "webhook_url": "https://hooks.slack.com/..." }
-- notion:   { "token": "secret_...", "database_id": "..." }
-- email:    { "host": "smtp.gmail.com", "port": 587,
--             "user": "you@gmail.com", "password": "앱 비밀번호",
--             "to": "recipient@example.com" }
-- calendar: { "ical_url": "https://calendar.google.com/calendar/ical/..." }
-- ============================================================
