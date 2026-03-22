-- User Model Access Overrides
-- Allows Owner to add/remove/fix models for specific users
-- action: 'add' (grant access), 'remove' (revoke), 'fixed' (bypass auto-routing)
CREATE TABLE IF NOT EXISTS user_model_access (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  username TEXT NOT NULL,
  model_id TEXT NOT NULL,
  action TEXT DEFAULT 'add',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(username, model_id)
);

CREATE INDEX IF NOT EXISTS idx_user_model_access_username ON user_model_access(username);
