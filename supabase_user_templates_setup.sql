-- ============================================================
-- AI Hub: User Custom Templates & Strategy
-- Supabase SQL Editor에서 실행하세요.
-- ============================================================

CREATE TABLE IF NOT EXISTS user_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'template',  -- 'template' | 'strategy'
    name        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_templates_user ON user_templates(user_id, type);
