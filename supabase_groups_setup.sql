-- ============================================================
-- AI Hub: User Groups + Integration Scopes
-- Supabase SQL Editor에서 실행하세요.
-- ============================================================

-- 1. Groups 테이블
CREATE TABLE IF NOT EXISTS groups (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_by  TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- 2. Group Members 테이블
CREATE TABLE IF NOT EXISTS group_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL,
    role        TEXT DEFAULT 'member',  -- 'admin' | 'member'
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(group_id, user_id)
);

-- 3. Integrations 테이블에 scope 컬럼 추가
ALTER TABLE integrations
    ADD COLUMN IF NOT EXISTS scope TEXT DEFAULT 'personal',  -- 'personal' | 'group' | 'global'
    ADD COLUMN IF NOT EXISTS group_id UUID REFERENCES groups(id) ON DELETE SET NULL;

-- ============================================================
-- scope 의미:
--   personal → user_id 소유자만 사용
--   group    → group_id에 속한 멤버 모두 사용
--   global   → 모든 유저 사용 (admin만 설정 가능)
-- ============================================================
