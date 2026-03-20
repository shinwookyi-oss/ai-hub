"""
AI Hub Web App (Cloud Deployment Version)
==========================================
Includes login authentication for security.

Environment Variables (set in Render Dashboard):
  OPENAI_API_KEY       - ChatGPT API key
  GEMINI_API_KEY       - Gemini API key
  AZURE_OPENAI_API_KEY - Azure OpenAI API key
  AZURE_OPENAI_ENDPOINT - Azure endpoint URL
  CLAUDE_API_KEY       - Claude (Anthropic) API key
  GROK_API_KEY         - Grok (xAI) API key
  APP_USERNAME         - Login username (default: admin)
  APP_PASSWORD         - Login password (default: aihub2026)
  SECRET_KEY           - Flask session secret (auto-generated if not set)
  SUPABASE_URL         - Supabase project URL
  SUPABASE_KEY         - Supabase anon public key
"""

import os
import tempfile
import secrets
import hashlib
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
import time

from flask import Flask, request, jsonify, session, redirect, url_for

from ai_hub import AIHub

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(hours=int(os.getenv("SESSION_TIMEOUT_HOURS", "2")))

hub = AIHub()

APP_USERNAME = os.getenv("APP_USERNAME", "admin")
_raw_password = os.getenv("APP_PASSWORD", "aihub2026")

# Password hashing: SHA-256 with salt
def _hash_password(pw: str) -> str:
    salt = os.getenv("PASSWORD_SALT", "aihub_salt_2026")
    return hashlib.sha256(f"{salt}:{pw}".encode()).hexdigest()

APP_PASSWORD_HASH = _hash_password(_raw_password)


# ──────────────────────────── Rate Limiting (Tiered) ────────────────────────

class RateLimiter:
    """In-memory tiered rate limiter per IP."""
    TIERS = {
        "admin":   None,                               # unlimited
        "premium": {"requests": 60,  "window": 60},   # 60 req/min
        "free":    {"requests": 20,  "window": 60},   # 20 req/min
    }

    def __init__(self):
        self.requests = defaultdict(list)  # ip -> [timestamps]

    def is_allowed(self, ip: str, tier: str = "free") -> bool:
        cfg = self.TIERS.get(tier, self.TIERS["free"])
        if cfg is None:
            return True  # admin: unlimited
        now = time.time()
        self.requests[ip] = [t for t in self.requests[ip] if now - t < cfg["window"]]
        if len(self.requests[ip]) >= cfg["requests"]:
            return False
        self.requests[ip].append(now)
        return True

    def remaining(self, ip: str, tier: str = "free") -> int:
        cfg = self.TIERS.get(tier, self.TIERS["free"])
        if cfg is None:
            return -1  # unlimited
        now = time.time()
        self.requests[ip] = [t for t in self.requests[ip] if now - t < cfg["window"]]
        return max(0, cfg["requests"] - len(self.requests[ip]))

    def tier_info(self, tier: str = "free") -> dict:
        cfg = self.TIERS.get(tier, self.TIERS["free"])
        if cfg is None:
            return {"tier": tier, "max_requests": "unlimited", "window_seconds": 0}
        return {"tier": tier, "max_requests": cfg["requests"], "window_seconds": cfg["window"]}


api_limiter = RateLimiter()
login_limiter = RateLimiter()  # uses 'free' tier (20 attempts/min) for login

UPLOAD_DIR = tempfile.mkdtemp(prefix="aihub_uploads_")

# ──────────────────────────── Supabase ────────────────────────────

supabase_client = None
supabase_admin = None  # service_role client for admin ops (bypasses RLS)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("  ✅ Supabase connected")
        if SUPABASE_SERVICE_KEY:
            supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            print("  ✅ Supabase admin (service_role) connected")
        else:
            supabase_admin = supabase_client  # fallback
            print("  ⚠️ No SUPABASE_SERVICE_KEY, admin ops use anon key")
    except Exception as e:
        print(f"  ⚠️ Supabase init failed: {e}")
else:
    print("  ⚠️ Supabase not configured (no SUPABASE_URL/KEY)")


# ──────────────────────────── Authentication ────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"success": False, "error": "Session expired. Please refresh and login again."}), 401
            return redirect(url_for("login_page"))
        # Session timeout check
        last_active = session.get("last_active")
        if last_active:
            try:
                elapsed = (datetime.utcnow() - datetime.fromisoformat(last_active)).total_seconds()
                if elapsed > app.permanent_session_lifetime.total_seconds():
                    session.clear()
                    if request.path.startswith("/api/"):
                        return jsonify({"success": False, "error": "Session timed out. Please login again."}), 401
                    return redirect(url_for("login_page"))
            except Exception:
                pass
        session["last_active"] = datetime.utcnow().isoformat()
        # Tiered rate limiting for API calls
        if request.path.startswith("/api/"):
            ip = request.remote_addr or "unknown"
            tier = session.get("user_tier", os.getenv("USER_TIER", "owner"))
            if not api_limiter.is_allowed(ip, tier):
                info = api_limiter.tier_info(tier)
                return jsonify({
                    "success": False,
                    "error": f"Rate limit exceeded ({info['max_requests']} req/{info['window_seconds']}s for {tier} tier). Try again shortly.",
                    "tier": tier,
                    "limit": info["max_requests"]
                }), 429
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Hub - Login</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: #0a0a0f;
            color: #e0e0f0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-box {
            width: 380px;
            padding: 40px;
            background: #12121a;
            border: 1px solid #2a2a3e;
            border-radius: 16px;
            text-align: center;
        }
        h1 {
            font-size: 28px;
            background: linear-gradient(135deg, #a29bfe, #74b9ff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        .subtitle { color: #8888aa; font-size: 13px; margin-bottom: 30px; }
        input {
            width: 100%;
            padding: 12px 16px;
            margin-bottom: 14px;
            border: 1px solid #2a2a3e;
            border-radius: 10px;
            background: #1a1a2e;
            color: #e0e0f0;
            font-size: 14px;
            font-family: 'Inter', sans-serif;
            outline: none;
        }
        input:focus { border-color: #6c5ce7; }
        button {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(135deg, #6c5ce7, #5a4bd1);
            color: white;
            font-size: 15px;
            font-weight: 600;
            font-family: 'Inter', sans-serif;
            cursor: pointer;
            transition: all 0.2s;
            margin-top: 6px;
        }
        button:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(108,92,231,0.4); }
        .error { color: #ff6b6b; font-size: 13px; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>AI Hub</h1>
        <p style="font-size:13px;color:#888;margin-top:4px;">By Shinwook Yi</p>
        <p class="subtitle">ChatGPT | Gemini | Azure | Claude | Grok</p>
        ERROR_MSG
        <form method="POST">
            <input type="text" name="username" placeholder="Username" autofocus required>
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if not login_limiter.is_allowed(ip):
            return LOGIN_HTML.replace("ERROR_MSG", '<p class="error">Too many login attempts. Please wait and try again.</p>')
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        pw_hash = _hash_password(password)
        # Try Supabase users table first
        user_found = False
        if supabase_client:
            try:
                res = supabase_client.table("users").select("*").eq("username", username).eq("is_active", True).execute()
                if res.data and len(res.data) > 0:
                    db_user = res.data[0]
                    if db_user["password_hash"] == pw_hash:
                        session.permanent = True
                        session["logged_in"] = True
                        session["user_id"] = db_user["id"]
                        session["username"] = db_user["username"]
                        session["user_tier"] = db_user.get("tier", "free")
                        session["display_name"] = db_user.get("display_name", username)
                        session["last_active"] = datetime.utcnow().isoformat()
                        session["login_time"] = datetime.utcnow().isoformat()
                        session["must_change_password"] = bool(db_user.get("must_change_password"))
                        # Update last_login
                        try:
                            supabase_client.table("users").update({"last_login": datetime.utcnow().isoformat()}).eq("id", db_user["id"]).execute()
                        except Exception:
                            pass
                        return redirect("/")
                    else:
                        user_found = True  # user exists but wrong password
            except Exception:
                pass  # Supabase error, fall through to env var
        # Fallback: env var credentials
        if not user_found and username == APP_USERNAME and pw_hash == APP_PASSWORD_HASH:
            session.permanent = True
            session["logged_in"] = True
            session["user_id"] = "env_admin"
            session["username"] = username
            session["user_tier"] = "owner"
            session["display_name"] = "Owner"
            session["last_active"] = datetime.utcnow().isoformat()
            session["login_time"] = datetime.utcnow().isoformat()
            return redirect("/")
        return LOGIN_HTML.replace("ERROR_MSG", '<p class="error">Invalid credentials</p>')
    return LOGIN_HTML.replace("ERROR_MSG", "")


def _seed_admin_user():
    """Auto-create admin user in Supabase if none exists."""
    if not supabase_client:
        return
    try:
        res = supabase_client.table("users").select("id").eq("tier", "owner").limit(1).execute()
        if not res.data:
            supabase_client.table("users").insert({
                "username": APP_USERNAME,
                "password_hash": APP_PASSWORD_HASH,
                "tier": "owner",
                "display_name": "System Owner",
                "is_active": True,
            }).execute()
            print("  ✅ Admin user seeded in Supabase")
            
        # Ensure shinwookyi is upgraded to owner
        try:
            supabase_admin.table("users").update({"tier": "owner"}).eq("username", "shinwookyi").execute()
            print("  ✅ Ensured shinwookyi is owner")
        except Exception as e:
            print(f"  ⚠️ Failed to force-upgrade shinwookyi: {e}")
            
    except Exception as e:
        print(f"  ⚠️ Admin seed skipped: {e}")


# Admin-only decorator
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user_tier") != "owner":
            return jsonify({"success": False, "error": "Owner access required"}), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ──────────────────────────── Main Page ────────────────────────────

MAIN_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0a0a0f; --surface: #12121a; --surface2: #1a1a2e;
            --border: #2a2a3e; --text: #e0e0f0; --text2: #8888aa;
            --accent: #6c5ce7; --accent2: #a29bfe; --green: #00d2a0;
            --orange: #fdcb6e; --red: #ff6b6b; --blue: #74b9ff;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
        .header {
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border-bottom: 1px solid var(--border);
            padding: 12px 20px; flex-shrink: 0;
            display: flex; align-items: center; justify-content: space-between;
        }
        .header h1 {
            font-size: 19px; font-weight: 700;
            background: linear-gradient(135deg, var(--accent2), var(--blue));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .header-right { display: flex; gap: 14px; align-items: center; }
        .status-dots { display: flex; gap: 10px; }
        .status-dot { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text2); }
        .status-dot .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 6px var(--green); }
        .status-dot .dot.off { background: var(--red); box-shadow: 0 0 6px var(--red); }
        .logout-btn {
            padding: 5px 12px; border: 1px solid var(--border); border-radius: 6px;
            background: var(--surface2); color: var(--text2); font-size: 12px;
            text-decoration: none; transition: all 0.2s;
        }
        .logout-btn:hover { border-color: var(--red); color: var(--red); }
        /* Header tabs */
        .header-tabs { display:flex; gap:6px; align-items:center; }
        .header-tab { padding:5px 12px; border:1px solid var(--border); border-radius:20px; background:var(--surface2); color:var(--text2); font-size:11px; font-family:'Inter',sans-serif; cursor:pointer; transition:all 0.2s; white-space:nowrap; }
        .header-tab:hover { border-color:var(--accent); color:var(--text); }
        .header-tab.active { border-color:var(--accent); background:#2a2058; color:var(--accent2); }
        .sidebar-toggle { border:none; background:none; color:var(--text2); cursor:pointer; font-size:18px; padding:2px 6px; transition:all 0.2s; }
        .sidebar-toggle:hover { color:var(--accent2); }
        /* Session info strip */
        .info-strip { display:flex; gap:16px; align-items:center; padding:3px 20px; background:#0d0d18; border-bottom:1px solid #1a1a2e; font-size:10px; color:var(--text2); flex-shrink:0; overflow-x:auto; }
        .info-strip span { white-space:nowrap; }
        .info-strip .label { color:#666; }
        .info-strip .value { color:var(--accent2); margin-left:3px; }
        /* 3-column layout */
        .container { display: flex; flex: 1; overflow: hidden; }
        .sidebar {
            width: 220px; min-width: 220px; flex-shrink: 0;
            background: var(--surface); border-right: 1px solid var(--border);
            padding: 12px; overflow-y: auto; transition: width 0.3s, min-width 0.3s, padding 0.3s;
        }
        .sidebar.hidden-sidebar { width:0; min-width:0; padding:0; overflow:hidden; border-right:none; }
        .sidebar-section { display:none; }
        .sidebar-section.active { display:block; }
        .sidebar h3 {
            font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px;
            color: var(--text2); margin-bottom: 10px; margin-top: 16px;
        }
        .sidebar h3:first-child { margin-top: 0; }
        .mode-btn {
            width: 100%; padding: 9px 12px; border: 1px solid var(--border);
            border-radius: 8px; background: var(--surface2);
            color: var(--text); font-size: 13px; font-family: 'Inter', sans-serif; cursor: pointer;
            margin-bottom: 5px; text-align: left; transition: all 0.2s;
        }
        .mode-btn:hover { border-color: var(--accent); background: #1e1e3a; }
        .mode-btn.active { border-color: var(--accent); background: #2a2058; }
        .collapsed { display: none; }
        .collapsed.open { display: block; }
        .persona-grid { margin-bottom: 8px; }
        .persona-group-header {
            font-size: 11px; color: var(--accent2); padding: 6px 0 4px; margin-top: 6px;
            border-bottom: 1px solid #2a2a3e; margin-bottom: 5px; font-weight: 600;
            cursor: pointer; display: flex; align-items: center; gap: 4px;
        }
        .persona-group-header:hover { color: var(--green); }
        .persona-group-header .pg-toggle { font-size: 9px; transition: transform 0.2s; }
        .persona-group-header .pg-toggle.collapsed { transform: rotate(-90deg); }
        .persona-group-body { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 4px; }
        .persona-group-body.collapsed { display: none; }
        .persona-chip {
            padding: 6px 8px; border-radius: 8px; font-size: 11px;
            border: 1px solid var(--border); cursor: pointer;
            text-align: center; transition: all 0.2s; color: var(--text2);
            background: var(--surface2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .persona-chip:hover { border-color: var(--accent); }
        .persona-chip.selected { border-color: var(--green); background: #1a3a2a; color: var(--green); }
        .persona-chip .mem-badge {
            display: inline-block; background: var(--accent); color: #fff; font-size: 8px;
            padding: 1px 4px; border-radius: 8px; margin-left: 3px; vertical-align: top;
        }
        .persona-memory-panel {
            display: none; margin-top: 6px; padding: 8px; background: #12121a;
            border: 1px solid #2a2a3e; border-radius: 8px; font-size: 11px;
        }
        .persona-memory-panel.active { display: block; }
        .mem-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; color: var(--accent2); }
        .mem-header span { font-weight: 600; }
        .mem-list { max-height: 150px; overflow-y: auto; }
        .mem-item {
            display: flex; justify-content: space-between; align-items: flex-start; gap: 6px;
            padding: 4px 6px; margin-bottom: 3px; background: #1a1a2e; border-radius: 5px;
            color: var(--text2); line-height: 1.3;
        }
        .mem-item .mem-del { cursor: pointer; color: #666; font-size: 10px; flex-shrink: 0; }
        .mem-item .mem-del:hover { color: var(--red); }
        .mem-actions { display: flex; gap: 4px; margin-top: 6px; }
        .mem-actions button {
            flex: 1; padding: 4px; font-size: 10px; border: 1px solid #2a2a3e;
            background: var(--surface2); color: var(--text2); border-radius: 5px; cursor: pointer;
        }
        .mem-actions button:hover { border-color: var(--accent); }
        .main-panel { display: flex; flex-direction: column; flex: 1; min-width: 0; border-right: 1px solid var(--border); }
        .chat-area { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
        /* Output panel */
        .output-panel { display: flex; flex-direction: column; width: 42%; min-width: 320px; background: #0d0d14; }
        .output-panel-header {
            padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
            background: var(--surface); display: flex; align-items: center; justify-content: space-between;
        }
        .output-panel-title { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
        .output-panel-badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; border: 1px solid var(--green); color: var(--green); background: #0a2a1a; display: none; }
        .output-action-btn { padding: 5px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface2); color: var(--text2); font-size: 11px; font-family: 'Inter', sans-serif; cursor: pointer; transition: all 0.2s; }
        .output-action-btn:hover { border-color: var(--accent2); color: var(--accent2); }
        .output-area { flex: 1; overflow-y: auto; padding: 22px; }
        /* Doc formatting */
        .doc-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text2); text-align: center; gap: 10px; }
        .doc-empty .ei { font-size: 36px; opacity: 0.25; }
        .doc-query { background: var(--surface2); border-left: 3px solid var(--accent); border-radius: 0 8px 8px 0; padding: 10px 14px; font-size: 14px; font-weight: 500; color: var(--text); margin-bottom: 18px; }
        .doc-sec-title { font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--accent2); margin: 18px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
        .doc-provider { margin-bottom: 14px; }
        .doc-provider-name { font-size: 11px; font-weight: 600; color: var(--text2); margin-bottom: 5px; display: flex; align-items: center; gap: 5px; }
        .doc-provider-name .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); display: inline-block; }
        .doc-provider-name .ti { font-size: 10px; color: var(--text2); font-weight: 400; }
        .doc-answer { font-size: 13px; line-height: 1.75; color: #c0c0d8; white-space: pre-wrap; word-break: break-word; }
        .doc-divider { border: none; border-top: 1px solid var(--border); margin: 14px 0; }
        .doc-round { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 13px; margin-bottom: 8px; }
        .doc-round-meta { font-size: 10px; color: var(--text2); margin-bottom: 4px; }
        .doc-round-speaker { font-size: 12px; font-weight: 600; color: var(--accent2); margin-bottom: 4px; }
        .doc-round-text { font-size: 13px; line-height: 1.6; color: #c0c0d8; }
        .doc-verdict { background: #2a1a08; border: 1px solid var(--orange); border-radius: 8px; padding: 12px; margin-top: 12px; }
        .doc-verdict-label { font-size: 10px; color: var(--orange); font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
        .doc-verdict-text { font-size: 13px; line-height: 1.6; color: #e8d0b0; }
        .doc-winner { background: #0a2a1a; border: 1px solid var(--green); border-radius: 8px; padding: 10px 13px; margin-top: 10px; }
        .doc-winner-label { font-size: 10px; color: var(--green); font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
        .doc-winner-text { font-size: 13px; color: #a0f0c0; }
        .doc-footer { font-size: 10px; color: var(--text2); margin-top: 18px; padding-top: 10px; border-top: 1px solid var(--border); display: flex; justify-content: space-between; }
        .message { margin-bottom: 16px; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .msg-header {
            font-size: 12px; font-weight: 600; color: var(--accent2);
            margin-bottom: 5px; display: flex; align-items: center; gap: 8px;
        }
        .msg-header .badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; background: var(--accent); color: white; }
        .msg-header .time { font-size: 10px; color: var(--text2); font-weight: 400; }
        .msg-body {
            background: var(--surface2); border: 1px solid var(--border); border-radius: 12px;
            padding: 12px 16px; font-size: 14px; line-height: 1.6; white-space: pre-wrap;
        }
        .msg-body.user-msg { background: #1e1e3a; border-color: var(--accent); max-width: 70%; margin-left: auto; }
        .msg-body.system-msg { background: #1a2a3a; border-color: var(--blue); font-size: 13px; }
        .msg-body.judge-msg { background: #2a1a2a; border-color: var(--orange); }
        .msg-body.error-msg { background: #2a1a1a; border-color: var(--red); color: var(--red); }
        .compare-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
        .compare-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
        .compare-card .provider { font-size: 12px; font-weight: 600; color: var(--accent2); margin-bottom: 6px; }
        .compare-card .content { font-size: 13px; line-height: 1.5; }
        .compare-card .meta { font-size: 11px; color: var(--text2); margin-top: 6px; }
        .input-area { padding: 14px 20px; border-top: 1px solid var(--border); background: var(--surface); }
        .file-bar {
            display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
            padding: 7px 12px; background: var(--surface2); border: 1px dashed var(--border);
            border-radius: 8px; font-size: 12px; color: var(--text2); transition: all 0.2s;
        }
        .file-bar.has-file { border-color: var(--green); background: #1a2a2a; border-style: solid; }
        .file-bar .file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--green); font-weight: 500; }
        .file-bar .file-size { color: var(--text2); font-size: 11px; }
        .upload-btn {
            padding: 5px 12px; border: 1px solid var(--border); border-radius: 6px;
            background: var(--surface2); color: var(--text); font-size: 12px;
            font-family: 'Inter', sans-serif; cursor: pointer; transition: all 0.2s;
        }
        .upload-btn:hover { border-color: var(--accent); }
        .remove-file-btn { background: none; border: none; color: var(--red); cursor: pointer; font-size: 14px; padding: 2px 6px; }
        .file-bar.dragover { border-color: var(--accent); background: #1e1e3a; border-style: solid; }
        .url-bar {
            display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
            padding: 7px 12px; background: var(--surface2); border: 1px solid var(--border);
            border-radius: 8px; font-size: 12px; color: var(--text2); transition: all 0.2s;
        }
        .url-bar.has-url { border-color: var(--blue); background: #1a1a2e; }
        .persona-selectors { display: flex; gap: 12px; margin-bottom: 10px; }
        .persona-selectors select {
            padding: 7px 10px; border: 1px solid var(--border); border-radius: 8px;
            background: var(--surface2); color: var(--text); font-family: 'Inter', sans-serif; font-size: 13px;
        }
        .persona-selectors label { font-size: 12px; color: var(--text2); margin-bottom: 3px; display: block; }
        .input-row { display: flex; gap: 10px; align-items: flex-end; }
        .input-row textarea {
            flex: 1; padding: 14px 16px; border: 1px solid var(--border); border-radius: 10px;
            background: var(--surface2); color: var(--text); font-size: 14px;
            font-family: 'Inter', sans-serif; outline: none; transition: border-color 0.2s;
            resize: vertical; min-height: 50px; height: 80px; max-height: 400px; line-height: 1.5;
        }
        .input-row textarea:focus { border-color: var(--accent); }
        .input-row textarea::placeholder { color: var(--text2); }
        .send-btn {
            padding: 11px 22px; border: none; border-radius: 10px;
            background: linear-gradient(135deg, var(--accent), #5a4bd1);
            color: white; font-size: 14px; font-weight: 600;
            font-family: 'Inter', sans-serif; cursor: pointer; transition: all 0.2s;
        }
        .send-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(108,92,231,0.4); }
        .send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .loading { display: inline-flex; align-items: center; gap: 8px; color: var(--text2); font-size: 13px; }
        .loading .spinner {
            width: 16px; height: 16px; border: 2px solid var(--border);
            border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .hidden { display: none !important; }
        /* ── Chat History ── */
        .history-section { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; }
        .new-chat-btn {
            width: 100%; padding: 9px 12px; border: 1px dashed var(--accent);
            border-radius: 8px; background: transparent; color: var(--accent2);
            font-size: 13px; font-family: 'Inter', sans-serif; cursor: pointer;
            margin-bottom: 8px; text-align: center; transition: all 0.2s;
        }
        .new-chat-btn:hover { background: #1e1e3a; border-style: solid; }
        .history-list { max-height: 200px; overflow-y: auto; }
        .history-item {
            padding: 7px 10px; border-radius: 6px; font-size: 12px;
            cursor: pointer; margin-bottom: 3px; transition: all 0.15s;
            display: flex; justify-content: space-between; align-items: center;
            color: var(--text2); white-space: nowrap; overflow: hidden;
        }
        .history-item:hover { background: var(--surface2); color: var(--text); }
        .history-item.active { background: #2a2058; color: var(--accent2); }
        .history-item .title { flex: 1; overflow: hidden; text-overflow: ellipsis; }
        .history-item .del-btn {
            opacity: 0; border: none; background: none; color: var(--red);
            cursor: pointer; font-size: 12px; padding: 0 4px; transition: opacity 0.2s;
        }
        .history-item:hover .del-btn { opacity: 1; }
        .history-empty { font-size: 11px; color: var(--text2); text-align: center; padding: 10px; }
        /* ── Markdown rendering ── */
        .md-body h1,.md-body h2,.md-body h3{color:var(--accent2);margin:10px 0 6px;}
        .md-body h1{font-size:18px;} .md-body h2{font-size:16px;} .md-body h3{font-size:14px;}
        .md-body p{margin:6px 0;line-height:1.6;font-size:13px;}
        .md-body ul,.md-body ol{padding-left:20px;margin:6px 0;font-size:13px;}
        .md-body li{margin:3px 0;line-height:1.5;}
        .md-body strong{color:var(--text);font-weight:600;}
        .md-body em{color:var(--text2);font-style:italic;}
        .md-body code{background:#1e1e3a;padding:2px 6px;border-radius:4px;font-size:12px;color:#f8c555;font-family:monospace;}
        .md-body pre{background:#1e1e3a;padding:12px;border-radius:8px;overflow-x:auto;margin:8px 0;}
        .md-body pre code{padding:0;font-size:12px;}
        .md-body table{border-collapse:collapse;width:100%;margin:8px 0;font-size:12px;}
        .md-body th{background:#1a1a2e;color:var(--accent2);padding:8px 10px;border:1px solid var(--border);text-align:left;}
        .md-body td{padding:6px 10px;border:1px solid var(--border);color:var(--text);}
        .md-body tr:nth-child(even){background:#12121a;}
        .md-body blockquote{border-left:3px solid var(--accent);padding:6px 12px;color:var(--text2);margin:8px 0;background:#1a1a2e;}
        .md-body hr{border:none;border-top:1px solid var(--border);margin:10px 0;}
        .md-body a{color:var(--accent2);text-decoration:underline;}
        /* ── Mermaid ── */
        .mermaid{background:#1a1a2e;padding:16px;border-radius:10px;margin:10px 0;text-align:center;}
        /* ── Chart ── */
        .chart-container{background:#12121a;border:1px solid var(--border);border-radius:10px;padding:16px;margin:10px 0;}
        .chart-container canvas{max-height:350px;}
        /* ── Spreadsheet ── */
        .ss-wrapper{background:#0d0d14;border:1px solid var(--border);border-radius:10px;overflow:hidden;margin:10px 0;}
        .ss-toolbar{display:flex;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);background:var(--surface);align-items:center;flex-wrap:wrap;}
        .ss-toolbar span{font-size:13px;font-weight:600;color:var(--accent2);}
        .ss-toolbar .ss-info{font-size:11px;color:var(--text2);margin-left:auto;}
        .ss-scroll{overflow:auto;max-height:65vh;}
        .ss-table{border-collapse:collapse;width:100%;font-size:12px;font-family:'Inter',monospace;}
        .ss-table th,.ss-table td{border:1px solid #2a2a3e;padding:5px 8px;text-align:left;white-space:nowrap;min-width:60px;}
        .ss-table thead th{background:#1a1a2e;color:var(--accent2);font-weight:600;position:sticky;top:0;z-index:2;font-size:11px;text-align:center;}
        .ss-table thead th.ss-corner{z-index:3;min-width:40px;width:40px;}
        .ss-table .ss-rownum{background:#14141e;color:var(--text2);font-size:10px;text-align:center;min-width:40px;width:40px;position:sticky;left:0;z-index:1;font-weight:600;}
        .ss-table tbody td{color:var(--text);background:#0d0d14;cursor:text;transition:background 0.15s;}
        .ss-table tbody td:hover{background:#1a1a2e;}
        .ss-table tbody td:focus{outline:2px solid var(--accent);outline-offset:-2px;background:#1e1e3a;}
        .ss-table tbody tr:nth-child(even) td:not(.ss-rownum){background:#10101a;}
        .ss-table tbody tr:nth-child(even) td:hover{background:#1a1a2e;}
        @media(max-width:768px){.ss-scroll{max-height:55vh;} .ss-table{font-size:11px;} .ss-table th,.ss-table td{padding:4px 6px;min-width:50px;}}
        /* ── Mobile Toggle ── */
        .mobile-menu-btn {
            display: none; border: none; background: none; color: var(--text);
            font-size: 22px; cursor: pointer; padding: 4px 8px;
        }
        .mobile-panel-tabs {
            display: none; border-bottom: 1px solid var(--border); background: var(--surface);
        }
        .mobile-panel-tabs button {
            flex: 1; padding: 10px; border: none; border-bottom: 2px solid transparent;
            background: none; color: var(--text2); font-size: 13px;
            font-family: 'Inter', sans-serif; cursor: pointer; transition: all 0.2s;
        }
        .mobile-panel-tabs button.active { color: var(--accent2); border-bottom-color: var(--accent); }
        /* ── Responsive ── */
        @media (max-width: 768px) {
            .mobile-menu-btn { display: block; }
            .mobile-panel-tabs { display: flex; }
            .header h1 { font-size: 16px; }
            .status-dots { display: none; }
            .container { flex-direction: column; }
            .sidebar {
                position: fixed; top: 48px; left: 0; bottom: 0; z-index: 100;
                width: 260px; transform: translateX(-100%); transition: transform 0.3s;
                box-shadow: 4px 0 20px rgba(0,0,0,0.5);
            }
            .sidebar.open { transform: translateX(0); }
            .sidebar-overlay {
                display: none; position: fixed; inset: 0; top: 48px;
                background: rgba(0,0,0,0.5); z-index: 99;
            }
            .sidebar-overlay.open { display: block; }
            .main-panel { border-right: none; width: 100%; }
            .output-panel { display: none; width: 100%; min-width: 0; }
            .output-panel.mobile-show { display: flex; flex: 1; }
            .main-panel.mobile-hide { display: none; }
            .header { padding: 10px 14px; }
            .input-area { padding: 10px 14px; }
            .chat-area { padding: 10px; }
            .compare-grid { grid-template-columns: 1fr; }
            .persona-group-body { grid-template-columns: 1fr 1fr 1fr; }
        }
        /* ── Voice Buttons ── */
        .mic-btn {
            padding: 11px 14px; border: none; border-radius: 10px;
            background: var(--surface2); border: 1px solid var(--border);
            color: var(--text2); font-size: 18px; cursor: pointer;
            transition: all 0.2s; font-family: 'Inter', sans-serif;
        }
        .mic-btn:hover { border-color: var(--accent); color: var(--accent2); }
        .mic-btn.recording { background: #3a1a1a; border-color: var(--red); color: var(--red); animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
        .speak-btn {
            border: none; background: none; color: var(--text2); cursor: pointer;
            font-size: 14px; padding: 2px 6px; transition: all 0.2s; opacity: 0.6;
        }
        .speak-btn:hover { color: var(--accent2); opacity: 1; }
        .speak-btn.speaking { color: var(--green); opacity: 1; }
        /* ── Admin Panel Modal ── */
        .admin-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:250; }
        .admin-overlay.open { display:flex; align-items:center; justify-content:center; }
        .admin-modal { background:#0d0d1a; border:1px solid var(--border); border-radius:16px; width:90%; max-width:750px; max-height:85vh; display:flex; flex-direction:column; overflow:hidden; }
        .admin-header { padding:16px 20px; border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; }
        .admin-header h2 { font-size:18px; margin:0; }
        .admin-body { padding:16px 20px; overflow-y:auto; flex:1; }
        .admin-table { width:100%; border-collapse:collapse; font-size:12px; }
        .admin-table th { text-align:left; padding:8px 6px; color:var(--text2); border-bottom:1px solid var(--border); font-size:10px; text-transform:uppercase; }
        .admin-table td { padding:8px 6px; border-bottom:1px solid rgba(255,255,255,0.05); vertical-align:middle; }
        .admin-table tr:hover { background:rgba(255,255,255,0.03); }
        .tier-badge { padding:2px 8px; border-radius:10px; font-size:10px; font-weight:600; }
        .tier-owner { background:#2d1f5e; color:#a78bfa; }
        .tier-admin { background:#374151; color:#d1d5db; }
        .tier-premium { background:#1f3a2d; color:#6ee7b7; }
        .tier-free { background:#1f2937; color:#9ca3af; }
        .admin-add-form { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
        .admin-add-form input, .admin-add-form select { padding:7px 10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); color:var(--text); font-size:12px; font-family:'Inter',sans-serif; }
        .admin-add-form input { flex:1; min-width:100px; }
        .admin-add-form button { padding:7px 14px; border:none; border-radius:8px; background:var(--green); color:#fff; font-size:12px; font-weight:600; cursor:pointer; }
        .admin-btn-sm { border:none; background:none; cursor:pointer; font-size:13px; padding:2px 5px; opacity:0.7; }
        .admin-btn-sm:hover { opacity:1; }
        .settings-btn { border:none; background:none; color:var(--text2); cursor:pointer; font-size:16px; padding:4px 8px; transition:all 0.2s; }
        .settings-btn:hover { color:var(--accent2); }
        /* ── Workspace Modal ── */
        .ws-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:200; }
        .ws-overlay.open { display:flex; align-items:center; justify-content:center; }
        .ws-modal { background:#0d0d1a; border:1px solid var(--border); border-radius:16px; width:90%; max-width:700px; max-height:85vh; display:flex; flex-direction:column; }
        .ws-header { padding:16px 20px; border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; }
        .ws-header h2 { font-size:18px; margin:0; }
        .ws-close { border:none; background:none; color:var(--text2); font-size:22px; cursor:pointer; }
        .ws-body { flex:1; overflow-y:auto; padding:16px 20px; display:flex; gap:16px; }
        .ws-folders { width:200px; min-width:160px; border-right:1px solid var(--border); padding-right:14px; }
        .ws-files { flex:1; min-width:0; }
        .ws-folder-item { padding:8px 12px; border:1px solid var(--border); border-radius:8px; margin-bottom:6px; cursor:pointer; font-size:13px; transition:all 0.2s; display:flex; justify-content:space-between; align-items:center; }
        .ws-folder-item:hover { border-color:var(--accent); }
        .ws-folder-item.active { border-color:var(--green); background:#0a2a1a; }
        .ws-folder-item .folder-actions { display:none; align-items:center; gap:6px; }
        .ws-folder-item:hover .folder-actions { display:flex; }
        .ws-file-item { padding:10px 14px; border:1px solid var(--border); border-radius:8px; margin-bottom:6px; cursor:pointer; transition:all 0.2s; }
        .ws-file-item:hover { border-color:var(--accent2); background:#1a1a2e; }
        .ws-file-type { font-size:10px; color:var(--text2); text-transform:uppercase; }
        .ws-file-name { font-size:14px; font-weight:500; }
        .ws-file-date { font-size:11px; color:var(--text2); }
        .ws-btn { padding:7px 14px; border:1px solid var(--border); border-radius:8px; background:var(--surface2); color:var(--text); font-size:12px; cursor:pointer; font-family:'Inter',sans-serif; transition:all 0.2s; }
        .ws-btn:hover { border-color:var(--accent); }
        .ws-btn-green { border-color:var(--green); color:var(--green); }
        .ws-editor { width:100%; min-height:200px; background:#12121f; border:1px solid var(--border); border-radius:8px; padding:12px; color:var(--text); font-family:'Inter',sans-serif; font-size:13px; resize:vertical; outline:none; }
        .ws-editor:focus { border-color:var(--accent); }
        @media(max-width:768px) { .ws-body{flex-direction:column;} .ws-folders{width:100%;border-right:none;border-bottom:1px solid var(--border);padding-right:0;padding-bottom:12px;} }
    </style>
</head>
<body>
    <div class="header">
        <div style="display:flex;align-items:center;gap:10px;">
            <button class="mobile-menu-btn" onclick="toggleSidebar()">☰</button>
            <button class="sidebar-toggle" id="sidebarToggleBtn" onclick="toggleSidebarCollapse()" title="Toggle sidebar">◀</button>
            <h1>⚡ AI Hub <span style="font-size:12px;font-weight:400;color:var(--text2);">by Shinwook Yi</span></h1>
        </div>
        <div class="header-tabs" id="headerTabs">
            <button class="header-tab active" id="tabMode" onclick="switchSidebarTab('mode')" data-i18n="mode">Mode</button>
            <button class="header-tab" id="tabProvider" onclick="switchSidebarTab('provider')">AI</button>
            <button class="header-tab" id="tabPersona" onclick="switchSidebarTab('persona')" data-i18n="persona">Persona</button>
        </div>
        <div class="header-right">
            <div class="status-dots" id="statusDots"></div>
            <button class="settings-btn" id="adminBtn" onclick="openAdmin()" title="Admin Settings" style="display:none;">⚙️</button>
            <a href="/logout" class="logout-btn" data-i18n="logout">Logout</a>
        </div>
    </div>
    <div class="info-strip" id="infoStrip">
        <span><span class="label">First:</span><span class="value" id="infoFirst">—</span></span>
        <span><span class="label">Last:</span><span class="value" id="infoLast">—</span></span>
        <span><span class="label">Total:</span><span class="value" id="infoTotal">—</span></span>
        <span><span class="label">Session:</span><span class="value" id="infoSession">0:00</span></span>
        <span><span class="label">IP:</span><span class="value" id="infoIp">—</span></span>
        <span><span class="label">Location:</span><span class="value" id="infoLocation">—</span></span>
    </div>
    <div class="mobile-panel-tabs" id="mobileTabs">
        <button class="active" onclick="showMobilePanel('chat')">💬 Chat</button>
        <button onclick="showMobilePanel('output')">📄 Output</button>
    </div>
    <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
    <!-- Admin Panel Modal -->
    <div class="admin-overlay" id="adminOverlay" onclick="if(event.target===this)closeAdmin()">
        <div class="admin-modal">
            <div class="admin-header">
                <h2>⚙️ User Management</h2>
                <button class="ws-close" onclick="closeAdmin()">×</button>
            </div>
            <div class="admin-body">
                <table class="admin-table">
                    <thead><tr><th>User</th><th>Display Name</th><th>Email</th><th>Phone</th><th>Temp PW</th><th>Tier</th><th>Status</th><th>Last Login</th><th>Actions</th></tr></thead>
                    <tbody id="adminUserList"><tr><td colspan="9" style="color:var(--text2);">Loading...</td></tr></tbody>
                </table>
                <div class="admin-add-form" id="adminAddForm">
                    <input type="text" id="newUsername" placeholder="Username" style="width:100px;">
                    <input type="password" id="newPassword" placeholder="Password" style="width:100px;">
                    <input type="text" id="newDisplayName" placeholder="Display Name" style="width:120px;">
                    <input type="email" id="newEmail" placeholder="Email" style="width:140px;">
                    <input type="tel" id="newPhone" placeholder="Phone" style="width:120px;">
                    <select id="newTier"><option value="free">Free</option><option value="premium">Premium</option><option value="admin">Admin</option><option value="owner">Owner</option></select>
                    <button onclick="adminAddUser()">+ Add</button>
                </div>
            </div>
        </div>
    </div>
    <div class="container">
    <!-- Workspace Modal -->
    <div class="ws-overlay" id="wsOverlay" onclick="if(event.target===this)closeWorkspace()">
        <div class="ws-modal">
            <div class="ws-header">
                <h2 data-i18n="workspace">📂 My Workspace</h2>
                <button class="ws-close" onclick="closeWorkspace()">×</button>
            </div>
            <div class="ws-body">
                <div class="ws-folders">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <span style="font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;" data-i18n="folders">Folders</span>
                        <button class="ws-btn ws-btn-green" onclick="createFolder()" style="padding:4px 10px;font-size:11px;">+ New</button>
                    </div>
                    <div id="wsFolderList"></div>
                </div>
                <div class="ws-files">
                    <div style="font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Files</div>
                    <div id="wsFileList"><div style="color:var(--text2);font-size:13px;">Select a folder to view files</div></div>
                </div>
            </div>
        </div>
    </div>
        <div class="sidebar" id="mainSidebar">
            <button class="mode-btn" style="background:#1a1a3a;border-color:var(--accent);margin-bottom:12px;" onclick="openWorkspace()" data-i18n="workspace">📂 My Workspace</button>
            <!-- Mode Section -->
            <div class="sidebar-section active" id="sectionMode">
            <h3 style="cursor:pointer;font-size:11px;color:var(--text2);margin:6px 0 4px;" onclick="toggleModeGroup('modeBasic')">🎯 <span data-i18n="mode">Mode</span> <span id="modeBasicArrow" style="float:right;">▼</span></h3>
            <div id="modeBasic">
                <button class="mode-btn" data-mode="chat" onclick="setMode('chat')" data-i18n="chat">💬 Chat</button>
                <button class="mode-btn" data-mode="compare" onclick="setMode('compare')" data-i18n="compare">🔄 Compare All</button>
                <button class="mode-btn" data-mode="debate" onclick="setMode('debate')" data-i18n="debate">⚔️ Debate</button>
                <button class="mode-btn" data-mode="discuss" onclick="setMode('discuss')" data-i18n="discuss">🗣️ Discussion</button>
                <button class="mode-btn" data-mode="best" onclick="setMode('best')" data-i18n="best">🏆 Best Answer</button>
            </div>
            </div>
            <!-- Provider Section -->
            <div class="sidebar-section" id="sectionProvider">
            <h3 data-i18n="provider">Provider</h3>
            <button class="mode-btn active" data-provider="chatgpt" onclick="setProvider('chatgpt')">ChatGPT</button>
            <button class="mode-btn" data-provider="gemini" onclick="setProvider('gemini')">Gemini</button>
            <button class="mode-btn" data-provider="azure" onclick="setProvider('azure')">Azure OpenAI</button>
            <button class="mode-btn" data-provider="claude" onclick="setProvider('claude')">Claude</button>
            <button class="mode-btn" data-provider="grok" onclick="setProvider('grok')">Grok</button>
            </div>
            <!-- Persona Section -->
            <div class="sidebar-section" id="sectionPersona">
            <h3 style="display:flex;justify-content:space-between;align-items:center;"><span data-i18n="persona">Persona</span> <span style="display:flex;gap:4px;"><button onclick="resetHiddenPersonas()" title="숨긴 페르소나 복원" style="font-size:10px;padding:2px 6px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text2);cursor:pointer;">↺</button><button onclick="addCustomPersona()" style="font-size:10px;padding:2px 8px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--accent2);cursor:pointer;" data-i18n="custom">+ Custom</button><button onclick="switchSidebarTab('persona')" title="사이드바 닫기" style="font-size:12px;padding:2px 7px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text2);cursor:pointer;">✕</button></span></h3>
            <!-- Persona Modes at top of Persona tab -->
            <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px;">
                <button class="mode-btn" data-mode="persona_debate" onclick="setMode('persona_debate')" data-i18n="p_debate">🎭 Persona Debate</button>
                <button class="mode-btn" data-mode="persona_discuss" onclick="setMode('persona_discuss')" data-i18n="p_discuss">🧠 Persona Discussion</button>
                <button class="mode-btn" data-mode="persona_report" onclick="setMode('persona_report')" data-i18n="p_report">📊 Multi-Report</button>
                <button class="mode-btn" data-mode="persona_vote" onclick="setMode('persona_vote')" data-i18n="vote">🗳️ Persona Vote</button>
                <button class="mode-btn" data-mode="persona_chain" onclick="setMode('persona_chain')" data-i18n="chain">🔗 Chain Analysis</button>
            </div>
            <div style="font-size:10px;color:var(--text2);margin:8px 0 4px;text-transform:uppercase;letter-spacing:1px;border-top:1px solid var(--border);padding-top:8px;">Active Persona</div>
            <div class="persona-grid" id="personaGrid"></div>
            <div class="persona-memory-panel" id="personaMemoryPanel">
                <div class="mem-header"><span>🧠 <span id="memPersonaName">Persona</span> Memory</span><span style="display:flex;align-items:center;gap:8px;"><span id="memCount">0</span><span onclick="togglePersona(currentPersona)" title="닫기" style="cursor:pointer;color:var(--text2);font-size:14px;line-height:1;padding:2px 4px;border-radius:3px;" onmouseover="this.style.color='var(--text)'" onmouseout="this.style.color='var(--text2)'">✕</span></span></div>
                <div class="mem-list" id="memList"></div>
                <div class="mem-actions">
                    <button onclick="addPersonaMemory()" data-i18n="add_mem">+ Add Memory</button>
                    <button onclick="clearPersonaMemory()" data-i18n="clear_all">🗑 Clear All</button>
                </div>
            </div>
            </div>
            <!-- History always visible -->
            <div class="history-section">
                <h3 data-i18n="history">Chat History</h3>
                <button class="new-chat-btn" onclick="newConversation()" data-i18n="new_chat">+ New Chat</button>
                <div class="history-list" id="historyList">
                    <div class="history-empty">Loading...</div>
                </div>
            </div>
        </div>
        <div class="main-panel">
            <div class="chat-area" id="chatArea"></div>
            <div class="input-area">
                <div class="persona-selectors hidden" id="personaSelectors">
                    <div><label data-i18n="lbl_for">FOR</label><select id="personaFor"></select></div>
                    <div><label data-i18n="lbl_against">AGAINST</label><select id="personaAgainst"></select></div>
                </div>
                <div id="personaMultiSelect" style="display:none; flex-wrap:wrap; gap:6px; margin-bottom:10px; padding:8px; background:#1a1a2e; border:1px solid #2a2a3e; border-radius:10px;">
                    <div style="width:100%; font-size:11px; color:#8888aa; margin-bottom:4px;" data-i18n="select_personas">Select personas (2+):</div>
                    <div id="personaCheckboxes" style="display:flex; flex-wrap:wrap; gap:6px;"></div>
                </div>
                <div id="dmPanel" style="display:none; margin-bottom:10px; padding:8px; background:#1a1a2e; border:1px solid #2a2a3e; border-radius:10px; font-size:11px;">
                    <div style="color:#8888aa; margin-bottom:4px;" data-i18n="dm_title">⚖️ Decision Matrix Setup</div>
                    <div style="margin-bottom:4px;"><label style="color:var(--text2);" data-i18n="dm_options">Options (comma-sep):</label>
                        <input id="dmOptions" style="width:100%;padding:4px 6px;background:#12121a;border:1px solid #2a2a3e;border-radius:5px;color:var(--text);font-size:11px;" placeholder="Option A, Option B, Option C"></div>
                    <div style="margin-bottom:4px;"><label style="color:var(--text2);" data-i18n="dm_criteria">Criteria (comma-sep):</label>
                        <input id="dmCriteria" style="width:100%;padding:4px 6px;background:#12121a;border:1px solid #2a2a3e;border-radius:5px;color:var(--text);font-size:11px;" placeholder="Cost, Risk, Revenue, Feasibility"></div>
                    <div style="display:flex;flex-wrap:wrap;gap:6px;" id="dmPersonaCheckboxes"></div>
                </div>
                <div style="display:flex;gap:4px;margin-bottom:6px;">
                    <button onclick="toggleInputTools()" style="padding:3px 8px;font-size:10px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--accent2);cursor:pointer;" title="Show/hide tools" data-i18n="tools">📎 Tools ▾</button>
                    <button onclick="exportPDF()" style="padding:3px 8px;font-size:10px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text2);cursor:pointer;" title="Export output to PDF">📄 PDF</button>
                </div>
                <div id="inputToolsPanel" style="display:none;">
                <div style="display:flex;gap:4px;margin-bottom:6px;">
                    <button onclick="savePrompt()" style="padding:3px 8px;font-size:10px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text2);cursor:pointer;" title="Save current input as prompt template" data-i18n="save_prompt">📋 Save Prompt</button>
                    <button onclick="loadPrompts()" style="padding:3px 8px;font-size:10px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text2);cursor:pointer;" title="Load saved prompts" data-i18n="load_prompt">📂 Load Prompt</button>
                </div>
                <div class="file-bar" id="fileBar">
                    <span>📎</span>
                    <span id="fileLabel" data-i18n="file_drop">Drop file(s) or Browse (TXT, PDF, CSV, DOCX...)</span>
                    <span class="file-name hidden" id="fileName"></span>
                    <span class="file-size hidden" id="fileSize"></span>
                    <button class="remove-file-btn hidden" id="removeFileBtn" onclick="removeFile()">✕ Clear</button>
                    <button class="upload-btn" onclick="document.getElementById('fileInput').click()">Browse</button>
                    <input type="file" id="fileInput" accept=".txt,.pdf,.csv,.md,.json,.py,.js,.html,.css,.xml,.log,.docx,.xlsx,.mp3,.wav,.m4a,.ogg,.webm" style="display:none" multiple>
                </div>
                <div class="url-bar" id="urlBar">
                    <span>🌐</span>
                    <input type="text" id="urlInput" placeholder="https://... 웹사이트 URL 입력 후 Enter" style="flex:1;background:none;border:none;outline:none;color:var(--text);font-size:12px;font-family:'Inter',sans-serif;">
                    <button class="upload-btn" id="urlFetchBtn" onclick="fetchUrl()">Fetch</button>
                </div>
                </div>
                <div class="input-row">
                    <textarea id="userInput" placeholder="Type your message..." autofocus></textarea>
                    <button class="mic-btn" id="micBtn" onclick="toggleMic()" title="Voice Input">🎙️</button>
                    <button class="send-btn" id="sendBtn" onclick="send()" data-i18n="send">Send</button>
                </div>
            </div>
        </div>
        <div class="output-panel">
            <div class="output-panel-header">
                <div class="output-panel-title">
                    📄 Result Document
                    <span class="output-panel-badge" id="outputBadge">✓ Ready</span>
                </div>
                <div style="display:flex;gap:6px;">
                    <button class="output-action-btn" id="vizBtn" onclick="visualize()" data-i18n="visualize">📊 Visualize</button>
                    <button class="output-action-btn" onclick="copyOutput()" data-i18n="copy">Copy</button>
                    <select id="exportSelect" class="output-action-btn" style="background:var(--bg2);color:var(--text);border:1px solid var(--border);cursor:pointer;outline:none;" onchange="if(this.value){exportDocument(this.value);this.value='';}">
                        <option value="" disabled selected>📥 Download ▾</option>
                        <option value="html">HTML</option>
                        <option value="word">Word (.doc)</option>
                        <option value="pdf">PDF</option>
                        <option value="excel">Excel (.xls)</option>
                        <option value="csv">CSV</option>
                    </select>
                    <button class="output-action-btn" onclick="clearOutput()" data-i18n="clear">Clear</button>
                </div>
            </div>
            <div class="output-area" id="outputArea">
                <div class="doc-empty"><div class="ei">📝</div><p style="font-size:13px;">AI 분석 결과가<br>여기에 문서화됩니다</p></div>
            </div>
        </div>
    </div>
    <script>
        // ── i18n: Browser Language Detection & Translation ──
        const LANG = (navigator.language || navigator.userLanguage || 'en').slice(0,2);
        const I18N = {
            en: {
                mode:'🎯 Mode', provider:'Provider', persona:'Persona', custom:'+ Custom',
                chat:'💬 Chat', compare:'🔄 Compare All', debate:'⚔️ Debate', discuss:'🗣️ Discussion',
                best:'🏆 Best Answer', p_debate:'🎭 Persona Debate', p_discuss:'🧠 Persona Discussion',
                p_report:'📊 Multi-Report', dm:'⚖️ Decision Matrix', chain:'🔗 Chain Analysis',
                vote:'🗳️ Persona Vote', history:'Chat History', new_chat:'+ New Chat',
                workspace:'📂 My Workspace', folders:'Folders', files:'Files', new_folder:'+ New',
                select_folder:'Select a folder to view files', logout:'Logout',
                result:'📄 Result Document', ready:'✓ Ready', visualize:'📊 Visualize',
                copy:'Copy', clear:'Clear', empty_output:'AI analysis results\nwill be documented here',
                ph_chat:'Type your message...', ph_compare:'Ask all AIs...', ph_debate:'Debate topic...',
                ph_discuss:'Discussion topic...', ph_best:'Question for best answer...',
                ph_p_debate:'Persona debate topic...', ph_p_discuss:'Topic for group discussion...',
                ph_p_report:'Topic for multi-persona report...', ph_dm:'(Configure options above, then type topic)',
                ph_chain:'Topic for chain analysis (select personas ↑)...',
                ph_vote:'Proposal to vote on (select personas ↑)...',
                send:'Send', memory:'Memory', add_mem:'+ Add Memory', clear_all:'🗑 Clear All',
                save_prompt:'📋 Save Prompt', load_prompt:'📂 Load Prompt', pdf:'📄 PDF',
                dm_title:'⚖️ Decision Matrix Setup', dm_options:'Options (comma-sep):',
                dm_criteria:'Criteria (comma-sep):', select_personas:'Select personas (2+):',
                select_eval:'Select evaluators:', loading:'Loading...', new_note:'📝 New Note',
                save_chat:'💬 Save Chat', save_slides:'📊 Save Slides', save_file:'💾 Save File',
                pin:'📌', ask_ai:'🤖 Ask AI', continue_ai:'▶ Continue', develop:'🔨 Develop',
                grp_persona:'🎭 Persona Modes', grp_analysis:'📐 Analysis Modes',
                tools:'📎 Tools ▾', file_drop:'Drop file(s) or Browse (TXT, PDF, CSV, DOCX...)',
                lbl_for:'FOR', lbl_against:'AGAINST', browse:'Browse', fetch:'Fetch',
                download:'📥 Download ▾',
            },
            ko: {
                mode:'🎯 모드', provider:'제공자', persona:'페르소나', custom:'+ 커스텀',
                chat:'💬 채팅', compare:'🔄 전체 비교', debate:'⚔️ 토론', discuss:'🗣️ 토의',
                best:'🏆 최적 답변', p_debate:'🎭 페르소나 토론', p_discuss:'🧠 페르소나 토의',
                p_report:'📊 다중 리포트', dm:'⚖️ 결정 매트릭스', chain:'🔗 체인 분석',
                vote:'🗳️ 페르소나 투표', history:'대화 기록', new_chat:'+ 새 대화',
                workspace:'📂 내 작업공간', folders:'폴더', files:'파일', new_folder:'+ 새로 만들기',
                select_folder:'폴더를 선택하세요', logout:'로그아웃',
                result:'📄 결과 문서', ready:'✓ 준비됨', visualize:'📊 시각화',
                copy:'복사', clear:'지우기', empty_output:'AI 분석 결과가\n여기에 문서화됩니다',
                ph_chat:'메시지를 입력하세요...', ph_compare:'모든 AI에게 질문...', ph_debate:'토론 주제...',
                ph_discuss:'토의 주제...', ph_best:'최적 답변 질문...', ph_p_debate:'페르소나 토론 주제...',
                ph_p_discuss:'그룹 토의 주제...', ph_p_report:'다중 페르소나 리포트 주제...',
                ph_dm:'(위에서 옵션 설정 후 주제 입력)', ph_chain:'체인 분석 주제 (위에서 페르소나 선택)...',
                ph_vote:'투표할 제안 (위에서 페르소나 선택)...',
                send:'전송', memory:'메모리', add_mem:'+ 기억 추가', clear_all:'🗑 전체 삭제',
                save_prompt:'📋 프롬프트 저장', load_prompt:'📂 프롬프트 불러오기', pdf:'📄 PDF',
                dm_title:'⚖️ 결정 매트릭스 설정', dm_options:'옵션 (쉼표 구분):',
                dm_criteria:'기준 (쉼표 구분):', select_personas:'페르소나 선택 (2명 이상):',
                select_eval:'평가자 선택:', loading:'로딩 중...', new_note:'📝 새 노트',
                save_chat:'💬 대화 저장', save_slides:'📊 슬라이드 저장', save_file:'💾 파일 저장',
                pin:'📌', ask_ai:'🤖 AI에게 질문', continue_ai:'▶ 이어하기', develop:'🔨 발전',
                grp_persona:'🎭 페르소나 모드', grp_analysis:'📐 분석 모드',
                tools:'📎 도구 ▾', file_drop:'파일 드래그 또는 찾아보기 (TXT, PDF, CSV, DOCX...)',
                lbl_for:'찬성', lbl_against:'반대', browse:'찾기', fetch:'가져오기',
                download:'📥 다운로드 ▾',
            },
            ja: {
                mode:'モード', provider:'プロバイダー', persona:'ペルソナ', custom:'+ カスタム',
                chat:'💬 チャット', compare:'🔄 全比較', debate:'⚔️ ディベート', discuss:'🗣️ ディスカッション',
                best:'🏆 ベスト回答', p_debate:'🎭 ペルソナ討論', p_discuss:'🧠 ペルソナ議論',
                p_report:'📊 マルチレポート', dm:'⚖️ 意思決定', chain:'🔗 チェーン分析',
                vote:'🗳️ ペルソナ投票', history:'チャット履歴', new_chat:'+ 新規チャット',
                workspace:'📂 ワークスペース', folders:'フォルダ', files:'ファイル', new_folder:'+ 新規',
                select_folder:'フォルダを選択', logout:'ログアウト',
                result:'📄 結果文書', ready:'✓ 準備完了', visualize:'📊 可視化',
                copy:'コピー', clear:'クリア', empty_output:'AI分析結果が\nここに表示されます',
                ph_chat:'メッセージを入力...', send:'送信', memory:'メモリ',
                add_mem:'+ メモリ追加', clear_all:'🗑 全削除',
                save_prompt:'📋 保存', load_prompt:'📂 読込', pdf:'📄 PDF',
                dm_title:'⚖️ 意思決定マトリックス', dm_options:'選択肢 (カンマ区切り):',
                dm_criteria:'基準 (カンマ区切り):', select_personas:'ペルソナ選択 (2+):',
                select_eval:'評価者選択:', loading:'読込中...',
                grp_persona:'🎭 ペルソナモード', grp_analysis:'📐 分析モード',
                tools:'📎 ツール ▾', file_drop:'ファイルをドロップまたは参照 (TXT, PDF, CSV, DOCX...)',
                lbl_for:'賀成', lbl_against:'反対', browse:'参照', fetch:'取得',
                download:'📥 ダウンロード ▾',
            },
            zh: {
                mode:'模式', provider:'提供商', persona:'角色', custom:'+ 自定义',
                chat:'💬 聊天', compare:'🔄 全部比较', debate:'⚔️ 辩论', discuss:'🗣️ 讨论',
                best:'🏆 最佳答案', p_debate:'🎭 角色辩论', p_discuss:'🧠 角色讨论',
                p_report:'📊 多角色报告', dm:'⚖️ 决策矩阵', chain:'🔗 链式分析',
                vote:'🗳️ 角色投票', history:'聊天记录', new_chat:'+ 新对话',
                workspace:'📂 工作空间', logout:'退出',
                result:'📄 结果文档', ready:'✓ 就绪', visualize:'📊 可视化',
                copy:'复制', clear:'清除', send:'发送', memory:'记忆',
                grp_persona:'🎭 角色模式', grp_analysis:'📐 分析模式',
                tools:'📎 工具 ▾', file_drop:'拖放文件或浏览 (TXT, PDF, CSV, DOCX...)',
                lbl_for:'赞成', lbl_against:'反对', browse:'浏览', fetch:'获取',
                download:'📥 下载 ▾',
            },
            es: {
                mode:'Modo', provider:'Proveedor', persona:'Persona', custom:'+ Personalizar',
                chat:'💬 Chat', compare:'🔄 Comparar', debate:'⚔️ Debate', discuss:'🗣️ Discusión',
                best:'🏆 Mejor Respuesta', p_debate:'🎭 Debate Persona', p_discuss:'🧠 Discusión Persona',
                p_report:'📊 Multi-Reporte', dm:'⚖️ Matriz', chain:'🔗 Análisis Cadena',
                vote:'🗳️ Votación', history:'Historial', new_chat:'+ Nuevo Chat',
                workspace:'📂 Espacio', logout:'Salir',
                result:'📄 Documento', ready:'✓ Listo', visualize:'📊 Visualizar',
                copy:'Copiar', clear:'Limpiar', send:'Enviar', memory:'Memoria',
                download:'📥 Descargar ▾',
            },
        };
        function t(key) { return (I18N[LANG]||{})[key] || (I18N['en']||{})[key] || key; }
        function applyLang() {
            document.querySelectorAll('[data-i18n]').forEach(function(el) {
                const key = el.getAttribute('data-i18n');
                const val = t(key);
                if (el.tagName === 'INPUT') el.placeholder = val;
                else el.textContent = val;
            });
            document.querySelectorAll('[data-i18n-title]').forEach(function(el) {
                el.title = t(el.getAttribute('data-i18n-title'));
            });
        }
        const PH_MAP = {
            chat:t('ph_chat'), compare:t('ph_compare')||'Ask all AIs...', debate:t('ph_debate')||'Debate topic...',
            discuss:t('ph_discuss')||'Discussion topic...', best:t('ph_best')||'Question for best answer...',
            persona_debate:t('ph_p_debate')||'Persona debate topic...', persona_discuss:t('ph_p_discuss')||'Topic for group discussion...',
            persona_report:t('ph_p_report')||'Topic for multi-persona report...', decision_matrix:t('ph_dm')||'(Configure options above)',
            persona_chain:t('ph_chain')||'Topic for chain analysis...', persona_vote:t('ph_vote')||'Proposal to vote on...',
        };

        let currentMode='chat', currentProvider='chatgpt', currentPersona='',
            uploadedFileContent='', uploadedFileName='',
            uploadedFiles=[];  // array of {name, content, size, chars}
        let personas = PERSONA_DATA;
        let personaGroups = PERSONA_GROUPS_DATA;
        const CURRENT_USERNAME = 'USERNAME_DATA';
        const USER_TIER = 'USER_TIER_DATA';
        const chatArea = document.getElementById('chatArea');
        const outputArea = document.getElementById('outputArea');

        function initStatus() {
            const status = AI_STATUS;
            const c = document.getElementById('statusDots');
            c.innerHTML = '';
            for (const [n,s] of Object.entries(status)) {
                c.innerHTML += `<div class="status-dot"><span class="dot ${s==='Ready'?'':'off'}"></span>${n}</div>`;
            }
        }
        
        function getCustomPersonas() {
            try { return JSON.parse(localStorage.getItem('customPersonas_' + CURRENT_USERNAME) || '[]'); }
            catch(e) { return []; }
        }
        function saveCustomPersonas(pcs) {
            localStorage.setItem('customPersonas_' + CURRENT_USERNAME, JSON.stringify(pcs));
        }

        function addCustomPersona() {
            let limit = 0;
            if (USER_TIER === 'premium') limit = 5;
            else if (USER_TIER === 'admin') limit = 10;
            else if (USER_TIER === 'owner') limit = Infinity;
            
            let pcs = getCustomPersonas();
            if (pcs.length >= limit) {
                alert(`Your tier (${USER_TIER}) allows up to ${limit} custom personas.`);
                return;
            }

            const name = prompt(t('new_persona_name') || "Enter Custom Persona Name (e.g. My AI):");
            if (!name) return;
            
            const traits = prompt("Enter Persona traits to Auto-Generate instructions using AI.\n(Or leave blank to write manually)");
            
            if (traits && traits.trim() !== '') {
                generateCustomPersonaPrompt(name, traits);
            } else {
                const promptText = prompt(t('new_persona_prompt') || "Enter Persona Instructions:");
                if (!promptText) return;
                saveAndRenderNewPersona(name, promptText);
            }
        }
        async function generateCustomPersonaPrompt(name, traits) {
            var loadId = addLoading('Generating Persona Instructions...');
            try {
                var ai_req = `You are an expert prompt engineer. Create a system instruction for an AI assistant based on the following traits: "${traits}". Output ONLY the raw system instructions, no conversational text, no markdown.`;
                var resp = await fetch('/api/chat', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: ai_req, provider: currentProvider || 'chatgpt', mode: 'chat'})
                });
                var data = await resp.json();
                removeLoading(loadId);
                var aiText = data.response || data.responses?.[0]?.response || '';
                if (!aiText) { alert("Failed to generate instructions."); return; }
                
                var finalPrompt = prompt("Generated prompt (you can edit):", aiText.trim());
                if (!finalPrompt) return;
                saveAndRenderNewPersona(name, finalPrompt);
            } catch(e) { 
                removeLoading(loadId); 
                alert('Error generating: ' + e.message); 
            }
        }
        function saveAndRenderNewPersona(name, promptText) {
            const newKey = 'custom_' + Date.now();
            let pcs = getCustomPersonas();
            pcs.push({ key: newKey, name: name, prompt: promptText });
            saveCustomPersonas(pcs);
            initPersonas();
            togglePersona(newKey);
            addMessage('System', `Custom persona "${name}" added!`, 'system-msg');
        }
        function deleteCustomPersona(key, event) {
            if(event) event.stopPropagation();
            if(!confirm("이 커스텀 페르소나를 삭제하겠습니까?\n(저장된 메모리/성향 기록도 함께 삭제됩니다)")) return;
            let pcs = getCustomPersonas();
            pcs = pcs.filter(p => p.key !== key);
            saveCustomPersonas(pcs);
            delete personas[key];
            if(currentPersona === key) togglePersona('');
            // Also delete all memories for this persona from Supabase
            fetch('/api/persona/' + key + '/memory/clear', {method:'DELETE'})
                .catch(() => {}); // silently ignore if no memories
            initPersonas();
        }
        function hidePersona(key, event) {
            if(event) event.stopPropagation();
            if(!confirm('이 페르소나를 목록에서 숨기겠습니까?\n(아래 Reset 버튼으로 복원 가능)')) return;
            let hidden = JSON.parse(localStorage.getItem('hiddenPersonas') || '[]');
            if(!hidden.includes(key)) hidden.push(key);
            localStorage.setItem('hiddenPersonas', JSON.stringify(hidden));
            if(currentPersona === key) togglePersona('');
            initPersonas();
        }
        function resetHiddenPersonas() {
            localStorage.removeItem('hiddenPersonas');
            initPersonas();
            addMessage('System', '숨긴 페르소나가 모두 복원됐습니다.', 'system-msg');
        }
        function initPersonas() {
            const g=document.getElementById('personaGrid'),
                  f=document.getElementById('personaFor'),
                  a=document.getElementById('personaAgainst');
            g.innerHTML=''; f.innerHTML=''; a.innerHTML='';
            const cb=document.getElementById('personaCheckboxes'); cb.innerHTML='';

            let groupsToRender = JSON.parse(JSON.stringify(personaGroups));
            const hiddenPersonas = JSON.parse(localStorage.getItem('hiddenPersonas') || '[]');
            // Filter hidden built-in personas from each group
            groupsToRender = groupsToRender.map(gr => ({...gr, personas: gr.personas.filter(p => !hiddenPersonas.includes(p.key))})).filter(gr => gr.personas.length > 0);
            const cps = getCustomPersonas();
            if (cps.length > 0) {
                cps.forEach(p => { personas[p.key] = { name: p.name, prompt: p.prompt, icon: "👤", group: "custom" }; });
                groupsToRender.unshift({
                    key: 'custom_group', name: 'My Custom Personas', icon: '👤',
                    personas: cps
                });
            }

            groupsToRender.forEach(function(group) {
                g.innerHTML += `<div class="persona-group-header" onclick="togglePersonaGroup('${group.key}')">`
                    + `<span class="pg-toggle" id="pgToggle_${group.key}">▼</span> ${group.icon} ${group.name}</div>`;
                g.innerHTML += `<div class="persona-group-body" id="pgBody_${group.key}">`
                    + group.personas.map(function(p) {
                        const isCustom = p.key.startsWith('custom_');
                        const delTitle = isCustom ? 'Delete persona' : 'Hide persona (can restore)';
                        const delHtml = `<span title="${delTitle}" style="float:right;color:var(--red);padding-left:10px;cursor:pointer;opacity:0.6;" onclick="${isCustom ? `deleteCustomPersona('${p.key}',event)` : `hidePersona('${p.key}',event)`}">×</span>`;
                        return `<div class="persona-chip" data-key="${p.key}" onclick="togglePersona('${p.key}')">${p.name}${delHtml}</div>`;
                    }).join('') + '</div>';
                // Populate debate selectors and checkboxes with group headers
                f.innerHTML += `<optgroup label="${group.icon} ${group.name}">`
                    + group.personas.map(function(p) { return `<option value="${p.key}">${p.name}</option>`; }).join('')
                    + '</optgroup>';
                a.innerHTML += `<optgroup label="${group.icon} ${group.name}">`
                    + group.personas.map(function(p) { return `<option value="${p.key}">${p.name}</option>`; }).join('')
                    + '</optgroup>';
                cb.innerHTML += `<div style="width:100%;font-size:10px;color:var(--accent2);margin-top:6px;">${group.icon} ${group.name}</div>`;
                group.personas.forEach(function(p) {
                    cb.innerHTML += `<label style="display:flex;align-items:center;gap:4px;padding:4px 8px;background:#12121a;border:1px solid #2a2a3e;border-radius:6px;font-size:11px;cursor:pointer;"><input type="checkbox" value="${p.key}" class="persona-cb"> ${p.name}</label>`;
                });
            });
            const keys=Object.keys(personas);
            if (keys.length>=2) a.value=keys[1];
        }
        function togglePersonaGroup(key) {
            var body = document.getElementById('pgBody_' + key);
            var toggle = document.getElementById('pgToggle_' + key);
            if (body) body.classList.toggle('collapsed');
            if (toggle) toggle.classList.toggle('collapsed');
        }
        async function loadPersonaMemory(personaKey) {
            const panel = document.getElementById('personaMemoryPanel');
            if (!personaKey) { panel.classList.remove('active'); return; }
            try {
                const [memRes, convRes] = await Promise.all([
                    fetch('/api/persona/' + personaKey + '/memory').then(r=>r.json()),
                    fetch('/api/persona/' + personaKey + '/conversations').then(r=>r.json()).catch(()=>({conversations:[]}))
                ]);
                const list = document.getElementById('memList');
                const name = personas[personaKey] || personaKey;
                const memCount = (memRes.memories||[]).length;
                const convCount = (convRes.conversations||[]).length;
                document.getElementById('memPersonaName').textContent = name;
                document.getElementById('memCount').textContent = memCount + convCount;
                list.innerHTML = '';
                // Show insights
                if (memRes.memories && memRes.memories.length > 0) {
                    list.innerHTML += '<div style="color:var(--accent);font-size:10px;font-weight:600;margin:4px 0;">💡 Insights (' + memCount + ')</div>';
                    memRes.memories.forEach(function(m) {
                        list.innerHTML += '<div class="mem-item"><span>' + escapeHtml(m.content) + '</span>'
                            + '<span class="mem-del" onclick="deleteMemory(\'' + m.id + '\')">&times;</span></div>';
                    });
                }
                // Show Q&A history
                if (convRes.conversations && convRes.conversations.length > 0) {
                    list.innerHTML += '<div style="color:var(--accent2);font-size:10px;font-weight:600;margin:6px 0 4px;">💬 Q&A History (' + convCount + ')</div>';
                    convRes.conversations.forEach(function(c) {
                        list.innerHTML += '<div class="mem-item" style="flex-direction:column;gap:2px;">'
                            + '<div style="color:var(--accent);font-size:9px;">Q: ' + escapeHtml((c.question||'').slice(0,100)) + '</div>'
                            + '<div style="font-size:9px;">A: ' + escapeHtml((c.answer||'').slice(0,150)) + '</div></div>';
                    });
                }
                if (!memCount && !convCount) {
                    list.innerHTML = '<div style="color:#555;padding:8px;text-align:center;">No memories yet. Conversations will auto-generate memories.</div>';
                }
                panel.classList.add('active');
            } catch(e) { panel.classList.remove('active'); }
        }
        async function addPersonaMemory() {
            if (!currentPersona) return;
            var content = prompt('Add memory for ' + (personas[currentPersona]||currentPersona) + ':');
            if (!content) return;
            await fetch('/api/persona/' + currentPersona + '/memory', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({content: content})
            });
            loadPersonaMemory(currentPersona);
        }
        async function deleteMemory(memId) {
            await fetch('/api/persona/memory/' + memId, {method:'DELETE'});
            loadPersonaMemory(currentPersona);
        }
        async function clearPersonaMemory() {
            if (!currentPersona) return;
            if (!confirm('Clear all memories for ' + (personas[currentPersona]||currentPersona) + '?')) return;
            await fetch('/api/persona/' + currentPersona + '/memory/clear', {method:'DELETE'});
            loadPersonaMemory(currentPersona);
        }
        function setMode(m) {
            currentMode=m;
            document.querySelectorAll('.mode-btn[data-mode]').forEach(b=>b.classList.remove('active'));
            document.querySelector(`.mode-btn[data-mode="${m}"]`)?.classList.add('active');
            document.getElementById('personaSelectors').classList.toggle('hidden', m!=='persona_debate');
            const multiModes = ['persona_discuss','persona_report','persona_chain','persona_vote'];
            const isMulti = multiModes.includes(m);
            document.getElementById('personaMultiSelect').style.display = isMulti ? 'flex' : 'none';
            document.getElementById('dmPanel').style.display = (m==='decision_matrix') ? 'block' : 'none';
            document.getElementById('userInput').placeholder = PH_MAP[m] || t('ph_chat');
        }
        function setProvider(p) {
            currentProvider=p;
            document.querySelectorAll('.mode-btn[data-provider]').forEach(b=>b.classList.remove('active'));
            document.querySelector(`.mode-btn[data-provider="${p}"]`)?.classList.add('active');
        }
        function togglePersona(k) {
            const chips=document.querySelectorAll('.persona-chip');
            if(currentPersona===k){currentPersona='';chips.forEach(c=>c.classList.remove('selected'));loadPersonaMemory('');}
            else{currentPersona=k;chips.forEach(c=>c.classList.toggle('selected',c.dataset.key===k));loadPersonaMemory(k);}
        }
        function addMessage(h,b,cls='',badge='',time='') {
            const m=document.createElement('div');m.className='message';
            let bH=badge?`<span class="badge">${badge}</span>`:'';
            let tH=time?`<span class="time">${time}</span>`:'';
            m.innerHTML=`<div class="msg-header">${h} ${bH} ${tH}</div><div class="msg-body ${cls}">${escapeHtml(b)}</div>`;
            chatArea.appendChild(m);chatArea.scrollTop=chatArea.scrollHeight;
        }
        // Initialize mermaid with dark theme
        mermaid.initialize({startOnLoad:false, theme:'dark', securityLevel:'loose'});
        let chartInstance = null;

        function renderMarkdown(text) {
            if(typeof marked === 'undefined') return `<pre>${escapeHtml(text)}</pre>`;
            // Configure marked
            marked.setOptions({breaks:true, gfm:true});
            return `<div class="md-body">${marked.parse(text)}</div>`;
        }
        async function renderMermaid(container) {
            const blocks = container.querySelectorAll('pre code.language-mermaid, .mermaid');
            for(const block of blocks) {
                const code = block.textContent;
                const div = document.createElement('div');
                div.className = 'mermaid';
                div.textContent = code;
                block.closest('pre') ? block.closest('pre').replaceWith(div) : block.replaceWith(div);
            }
            try { await mermaid.run({nodes: container.querySelectorAll('.mermaid')}); } catch(e) {}
        }
        function showDoc(html, query='', footer='') {
            const ts = new Date().toLocaleTimeString();
            outputArea.innerHTML = `
                ${query ? `<div class="doc-query">${escapeHtml(query)}</div>` : ''}
                ${html}
                <div class="doc-footer"><span>${ts}</span><span>${escapeHtml(footer)}</span></div>`;
            outputArea.scrollTop = 0;
            document.getElementById('outputBadge').style.display = 'inline-flex';
            renderMermaid(outputArea);
        }
        function showDocMarkdown(text, query='', footer='') {
            showDoc(renderMarkdown(text), query, footer);
        }
        function clearOutput() {
            outputArea.innerHTML = '<div class="doc-empty"><div class="ei">📝</div><p style="font-size:13px;">Result will appear here</p></div>';
            document.getElementById('outputBadge').style.display = 'none';
            if(chartInstance) { chartInstance.destroy(); chartInstance = null; }
        }
        // ── Spreadsheet ──
        var ssData = null;
        function parseTabularData(text) {
            if (!text || !text.trim()) return null;
            var lines = text.split('\n').filter(function(l){return l.trim();});
            if (lines.length < 2) return null;
            var sep = '\t';
            if (lines[0].indexOf('\t') < 0 && lines[0].indexOf(',') >= 0) sep = ',';
            var rows = [];
            for (var i = 0; i < lines.length; i++) {
                var cells;
                if (sep === ',') {
                    cells = []; var cur = ''; var inQ = false;
                    for (var c = 0; c < lines[i].length; c++) {
                        var ch = lines[i][c];
                        if (ch === '"') { inQ = !inQ; }
                        else if (ch === ',' && !inQ) { cells.push(cur.trim()); cur = ''; }
                        else { cur += ch; }
                    }
                    cells.push(cur.trim());
                } else {
                    cells = lines[i].split(sep);
                }
                if (cells.length > 1 || rows.length > 0) rows.push(cells);
            }
            if (rows.length < 2 || rows[0].length < 2) return null;
            return rows;
        }
        function colLetter(n) {
            var s = ''; n++;
            while (n > 0) { n--; s = String.fromCharCode(65 + (n % 26)) + s; n = Math.floor(n / 26); }
            return s;
        }
        function renderSpreadsheet(rows, title, fileName) {
            if (!rows || rows.length < 2) return;
            ssData = rows;
            var maxCols = 0;
            rows.forEach(function(r){if(r.length>maxCols)maxCols=r.length;});
            var html = '<div class="ss-wrapper">';
            html += '<div class="ss-toolbar">';
            html += '<span>📊 ' + (title || 'Spreadsheet') + '</span>';
            html += '<button class="ws-btn" style="font-size:11px;" onclick="ssAnalyze()">🤖 AI 분석</button>';
            html += '<button class="ws-btn" style="font-size:11px;" onclick="ssExportCSV()">💾 CSV</button>';
            html += '<span class="ss-info">' + (rows.length-1) + ' rows × ' + maxCols + ' cols</span>';
            html += '</div>';
            html += '<div class="ss-scroll"><table class="ss-table"><thead><tr>';
            html += '<th class="ss-corner"></th>';
            for (var c = 0; c < maxCols; c++) html += '<th>' + colLetter(c) + '</th>';
            html += '</tr><tr><th class="ss-rownum" style="background:#1a1a2e;">H</th>';
            for (var c = 0; c < maxCols; c++) html += '<th style="color:var(--green);">' + escapeHtml(rows[0][c]||'') + '</th>';
            html += '</tr></thead><tbody>';
            var maxRows = Math.min(rows.length, 501);
            for (var r = 1; r < maxRows; r++) {
                html += '<tr><td class="ss-rownum">' + r + '</td>';
                for (var c = 0; c < maxCols; c++) {
                    html += '<td contenteditable="true" data-r="'+r+'" data-c="'+c+'">' + escapeHtml(rows[r] && rows[r][c] ? rows[r][c] : '') + '</td>';
                }
                html += '</tr>';
            }
            if (rows.length > 501) {
                html += '<tr><td class="ss-rownum">...</td>';
                for (var c = 0; c < maxCols; c++) html += '<td style="color:var(--text2);font-style:italic;">+' + (rows.length-501) + ' more</td>';
                html += '</tr>';
            }
            html += '</tbody></table></div></div>';
            if (fileName) {
                html = '<div class="doc-query">' + escapeHtml(fileName) + '</div>' + html;
            }
            outputArea.innerHTML = html;
            document.getElementById('outputBadge').style.display = 'inline-flex';
            if (window.innerWidth <= 768) showMobilePanel('output');
        }
        function ssAnalyze() {
            if (!ssData || !ssData.length) return;
            var header = ssData[0].join(', ');
            var sample = ssData.slice(1, Math.min(11, ssData.length)).map(function(r){return r.join(', ');}).join('\n');
            var input = document.getElementById('userInput');
            input.value = '다음 스프레드시트 데이터를 분석해 주세요.\n\n헤더: ' + header + '\n\n샘플 데이터 (처음 10행):\n' + sample + '\n\n총 ' + (ssData.length-1) + '행입니다. 주요 패턴, 통계, 인사이트를 알려주세요.';
            send();
        }
        function ssExportCSV() {
            if (!ssData) return;
            var csv = ssData.map(function(r){return r.map(function(c){return '"'+(c||"").replace(/"/g,'""')+'"';}).join(',');}).join('\n');
            var blob = new Blob([csv], {type:'text/csv'});
            var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
            a.download = 'spreadsheet.csv'; a.click();
        }
        function isTabularContent(text, fileName) {
            if (!text) return false;
            var fn = (fileName || '').toLowerCase();
            if (fn.endsWith('.csv') || fn.endsWith('.xlsx') || fn.endsWith('.xls') || fn.endsWith('.tsv')) return true;
            var lines = text.split('\n').filter(function(l){return l.trim();});
            if (lines.length < 3) return false;
            var tabCount = 0; var commaCount = 0;
            for (var i = 0; i < Math.min(5, lines.length); i++) {
                tabCount += (lines[i].match(/\t/g) || []).length;
                commaCount += (lines[i].match(/,/g) || []).length;
            }
            return (tabCount >= 5) || (commaCount >= 10 && lines.length >= 3);
        }
        function copyOutput() {
            navigator.clipboard.writeText(outputArea.innerText).then(() => {
                const b = document.querySelector('.output-action-btn');
                b.textContent = 'Copied!'; setTimeout(() => b.textContent = 'Copy', 1500);
            });
        }
        function exportDocument(format) {
            var content = outputArea.innerText;
            var html = outputArea.innerHTML;
            if (!content || content.includes('AI 분석 결과가')) { alert('No content to export'); return; }
            var title = 'AI_Hub_Export_' + new Date().toISOString().slice(0,10);
            
            if (format === 'pdf') {
                window.print();
            } else if (format === 'html') {
                var fullHtml = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>'+title+'</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:30px;line-height:1.6;color:#333;margin:0 auto;max-width:900px;}</style></head><body>' + html + '</body></html>';
                var blob = new Blob([fullHtml], {type: 'text/html;charset=utf-8;'});
                var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
                a.download = title + '.html'; a.click();
            } else if (format === 'word') {
                var docHtml = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8"><title>'+title+'</title></head><body>' + html + '</body></html>';
                var blob = new Blob(['\ufeff', docHtml], {type: 'application/msword'});
                var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
                a.download = title + '.doc'; a.click();
            } else if (format === 'csv') {
                var csv = content.split('\\n').map(l => '"' + l.replace(/"/g,'""') + '"').join('\\n');
                var blob = new Blob(['\ufeff', csv], {type: 'text/csv;charset=utf-8;'});
                var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
                a.download = title + '.csv'; a.click();
            } else if (format === 'excel') {
                var xlsHtml = '<html xmlns:x="urn:schemas-microsoft-com:office:excel"><head><meta charset="utf-8"></head><body>' + html + '</body></html>';
                var blob = new Blob(['\ufeff', xlsHtml], {type: 'application/vnd.ms-excel'});
                var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
                a.download = title + '.xls'; a.click();
            }
        }
        async function visualize() {
            const btn = document.getElementById('vizBtn');
            const currentText = outputArea.innerText;
            const fileCtx = uploadedFileContent ? uploadedFileContent.slice(0,8000) : '';
            const context = fileCtx || currentText.slice(0, 8000);
            if(!context.trim()) { addMessage('Error','먼저 파일을 업로드하거나 AI 응답이 있어야 합니다.','error-msg'); return; }
            btn.textContent = '⏳ Analyzing...'; btn.disabled = true;
            try {
                const resp = await fetch('/api/visualize', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({context})
                });
                const ct = resp.headers.get('content-type') || '';
                if(!ct.includes('application/json')) { addMessage('Error','세션 만료 또는 서버 오류. 새로고침 후 다시 시도해주세요.','error-msg'); return; }
                const r = await resp.json();
                if(r.success && r.chart_data) {
                    renderChart(r.chart_data, r.title || '📊 Data Visualization');
                } else if(r.diagram) {
                    const div = document.createElement('div');
                    div.innerHTML = `<div class="doc-sec-title">🗺️ ${r.title||'Diagram'}</div><div class="mermaid">${r.diagram}</div>`;
                    outputArea.prepend(div);
                    renderMermaid(outputArea);
                } else {
                    addMessage('Error', r.error || 'Visualization failed', 'error-msg');
                }
            } catch(e) { addMessage('Error', 'Viz error: '+e.message, 'error-msg'); }
            btn.textContent = '📊 Visualize'; btn.disabled = false;
        }
        function renderChart(data, title) {
            if(chartInstance) chartInstance.destroy();
            const container = document.createElement('div');
            container.className = 'chart-container';
            container.innerHTML = `<div class="doc-sec-title">${title}</div><canvas id="vizChart"></canvas>`;
            outputArea.prepend(container);
            const ctx = document.getElementById('vizChart').getContext('2d');
            chartInstance = new Chart(ctx, {
                type: data.type || 'bar',
                data: {
                    labels: data.labels,
                    datasets: data.datasets.map((ds,i) => ({
                        ...ds,
                        backgroundColor: ds.backgroundColor || ['#6c5ce7','#74b9ff','#00cec9','#fd79a8','#fdcb6e','#55efc4'][i%6],
                        borderColor: ds.borderColor || 'transparent',
                        borderWidth: 1
                    }))
                },
                options: {
                    responsive:true, plugins:{legend:{labels:{color:'#e0e0f0'}},
                    title:{display:!!data.title, text:data.title, color:'#e0e0f0'}},
                    scales: data.type==='pie'||data.type==='doughnut' ? {} : {
                        x:{ticks:{color:'#8888aa'},grid:{color:'#2a2a3e'}},
                        y:{ticks:{color:'#8888aa'},grid:{color:'#2a2a3e'}}
                    }
                }
            });
            outputArea.scrollTop = 0;
            document.getElementById('outputBadge').style.display = 'inline-flex';
        }
        function addCompareCards(results) {
            const m=document.createElement('div');m.className='message';
            let h='<div class="compare-grid">';
            for(const r of results){
                h+=`<div class="compare-card ${r.success?'':'error-msg'}">
                    <div class="provider">${r.provider} (${r.model})</div>
                    <div class="content">${escapeHtml(r.success?r.content:r.error)}</div>
                    <div class="meta">${r.elapsed_seconds}s</div></div>`;
            }
            h+='</div>';m.innerHTML=h;chatArea.appendChild(m);chatArea.scrollTop=chatArea.scrollHeight;
        }
        function addLoading(id){const m=document.createElement('div');m.className='message';m.id=id;
            m.innerHTML='<div class="loading"><div class="spinner"></div>Processing...</div>';
            chatArea.appendChild(m);chatArea.scrollTop=chatArea.scrollHeight;}
        function removeLoading(id){document.getElementById(id)?.remove();}
        function escapeHtml(t){if(!t)return'';const d=document.createElement('div');d.textContent=t;return d.innerHTML;}
        async function safeFetch(url, options) {
            const resp = await fetch(url, options);
            const ct = resp.headers.get('content-type') || '';
            if (!ct.includes('application/json')) {
                if (resp.status === 401) throw new Error('세션 만료 — 페이지를 새로고침하고 다시 로그인해주세요.');
                if (resp.status >= 500) throw new Error(`서버 오류 (${resp.status}) — 잠시 후 다시 시도해주세요.`);
                throw new Error(`응답 오류 (${resp.status}) — 새로고침 후 다시 시도해주세요.`);
            }
            return resp.json();
        }

        // File upload
        const fileInput=document.getElementById('fileInput'), fileBar=document.getElementById('fileBar');
        fileInput.addEventListener('change',async e=>{for(const f of e.target.files) await uploadFile(f);});
        fileBar.addEventListener('dragover',e=>{e.preventDefault();fileBar.classList.add('dragover');});
        fileBar.addEventListener('dragleave',()=>{fileBar.classList.remove('dragover');});
        fileBar.addEventListener('drop',async e=>{
            e.preventDefault();fileBar.classList.remove('dragover');
            if(e.dataTransfer.files.length) {
                for(const f of e.dataTransfer.files) await uploadFile(f);
            }
        });

        async function uploadFile(file) {
            const fd=new FormData(); fd.append('file',file);
            try{
                const resp = await fetch('/api/upload', {method:'POST', body:fd});
                const ct = resp.headers.get('content-type') || '';
                if (!ct.includes('application/json')) {
                    if (resp.status === 401) {
                        addMessage('Error', '⚠️ 세션 만료. 페이지를 새로고침하고 다시 로그인해주세요.', 'error-msg');
                    } else {
                        addMessage('Error', `서버 오류 (${resp.status}). 잠시 후 다시 시도해주세요.`, 'error-msg');
                    }
                    return;
                }
                const r = await resp.json();
                if(r.success){
                    // Add to uploadedFiles array
                    uploadedFiles.push({name: r.filename, content: r.content, size: r.size, chars: r.char_count});
                    // Combine all file contents
                    uploadedFileContent = uploadedFiles.map(f => `=== ${f.name} ===\n${f.content}`).join('\n\n');
                    uploadedFileName = uploadedFiles.map(f=>f.name).join(', ');
                    const kb=(r.size/1024).toFixed(1);
                    document.getElementById('fileLabel').classList.add('hidden');
                    document.getElementById('fileName').textContent = uploadedFiles.length > 1
                        ? `${uploadedFiles.length}개 파일 (송: ${uploadedFileName})`
                        : r.filename;
                    document.getElementById('fileName').classList.remove('hidden');
                    document.getElementById('fileSize').textContent = uploadedFiles.length > 1
                        ? `여러 파일`
                        : `${kb} KB`;
                    document.getElementById('fileSize').classList.remove('hidden');
                    document.getElementById('removeFileBtn').classList.remove('hidden');
                    fileBar.classList.add('has-file');
                    addMessage('System',`📄 업로드: ${r.filename} (${kb} KB, ${r.char_count.toLocaleString()}자)${
                        uploadedFiles.length > 1 ? ` — 역대 업로드 ${uploadedFiles.length}개` : ''
                    }`,'system-msg');
                    // Auto-render spreadsheet for CSV/Excel
                    if (isTabularContent(r.content, r.filename)) {
                        var rows = parseTabularData(r.content);
                        if (rows) renderSpreadsheet(rows, r.filename, r.filename);
                    }
                }else{addMessage('Error',r.error||'Upload failed','error-msg');}
            }catch(e){addMessage('Error','업로드 오류: '+e.message,'error-msg');}
        }
        function removeFile(){
            uploadedFileContent='';uploadedFileName='';uploadedFiles=[];
            document.getElementById('fileLabel').classList.remove('hidden');
            document.getElementById('fileName').classList.add('hidden');
            document.getElementById('fileSize').classList.add('hidden');
            document.getElementById('removeFileBtn').classList.add('hidden');
            fileBar.classList.remove('has-file');fileInput.value='';
        }

        // URL bar setup
        const urlInput = document.getElementById('urlInput');
        urlInput.addEventListener('keydown', e => { if(e.key==='Enter') fetchUrl(); });

        async function fetchUrl() {
            const url = urlInput.value.trim();
            if(!url) return;
            const btn = document.getElementById('urlFetchBtn');
            btn.textContent = 'Loading...'; btn.disabled = true;
            try {
                const r = await fetch('/api/fetch_url', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({url})
                }).then(r => r.json());
                if(r.success) {
                    uploadedFileContent = r.content;
                    uploadedFileName = `[웹페이지] ${r.title}`;
                    document.getElementById('urlBar').classList.add('has-url');
                    addMessage('System', `🌐 URL 로드 완료: ${r.title}\n${r.url}\n(${r.char_count.toLocaleString()} 글자)`, 'system-msg');
                    addMessage('System', '이제 질문을 입력하면 이 웹페이지 내용을 바탕으로 분석합니다.', 'system-msg');
                } else {
                    addMessage('Error', 'URL 로드 실패: ' + r.error, 'error-msg');
                }
            } catch(e) {
                addMessage('Error', 'URL 로드 오류: ' + e.message, 'error-msg');
            }
            btn.textContent = 'Fetch'; btn.disabled = false;
        }

        async function send() {
            const input=document.getElementById('userInput'), text=input.value.trim();
            if(!text) return;
            let prompt=text;
            if(uploadedFileContent) {
                const q = text || '이 파일의 내용을 분석하고 요약해 주세요.';
                // Divide char limit proportionally among all files
                const maxChars = 100000;
                let chunk, truncNote;
                if(uploadedFiles.length > 1) {
                    const perFile = Math.floor(maxChars / uploadedFiles.length);
                    const parts = uploadedFiles.map(f => {
                        const c = f.content.slice(0, perFile);
                        const note = f.content.length > perFile ? ` [${perFile.toLocaleString()}자로 축약]` : '';
                        return `=== ${f.name}${note} ===\n${c}`;
                    });
                    chunk = parts.join('\n\n');
                    truncNote = `\n\n[📎 총 ${uploadedFiles.length}개 파일, 파일당 최대 ${perFile.toLocaleString()}자]`;
                } else {
                    chunk = uploadedFileContent.slice(0, maxChars);
                    truncNote = uploadedFileContent.length > maxChars
                        ? `\n\n[⚠️ 파일이 길어 처음 ${maxChars.toLocaleString()}자만 전송됨. 총 ${uploadedFileContent.length.toLocaleString()}자]`
                        : '';
                }
                prompt = `아래는 업로드된 파일 "${uploadedFileName}"의 내용입니다. 이 내용을 바탕으로 사용자의 질문에 답하거나 분석해 주세요.\n\n--- 파일 내용 시작 ---\n${chunk}${truncNote}\n--- 파일 내용 끝 ---\n\n사용자 질문: ${q}`;
            }
            input.value=''; document.getElementById('sendBtn').disabled=true;
            addMessage('You',text,'user-msg');
            const loadId='load-'+Date.now(); addLoading(loadId);
            try {
                let result;
                if(currentMode==='chat'){
                    result=await safeFetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({prompt,provider:currentProvider,persona:currentPersona})});
                    removeLoading(loadId);
                    if(result.success) {
                        addMessage(result.provider,result.content,'',result.model,result.elapsed_seconds+'s');
                        const persona_label = currentPersona ? `Persona: ${currentPersona}` : result.provider;
                        showDoc(`<div class="doc-sec-title">💬 Response</div><div class="doc-provider"><div class="doc-provider-name"><span class="dot"></span>${escapeHtml(result.provider)} <span class="ti">${result.elapsed_seconds}s · ${result.model}</span></div><div class="doc-answer">${escapeHtml(result.content)}</div></div>`, text, persona_label);
                    }
                    else addMessage('Error',result.error,'error-msg');
                } else if(currentMode==='compare'){
                    result=await safeFetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({prompt})});
                    removeLoading(loadId); addCompareCards(result.results);
                    let docCards = result.results.map(r => `<div class="doc-provider"><div class="doc-provider-name"><span class="dot ${r.success?'':'off'}"></span>${escapeHtml(r.provider)} <span class="ti">${r.elapsed_seconds}s · ${r.model}</span></div><div class="doc-answer">${escapeHtml(r.success?r.content:'Error: '+r.error)}</div></div><hr class="doc-divider">`).join('');
                    showDoc(`<div class="doc-sec-title">🔄 All AI Responses</div>${docCards}`, text, 'Compare All');
                } else if(currentMode==='debate'){
                    result=await safeFetch('/api/debate',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({topic:text})});
                    removeLoading(loadId);
                    addMessage('System',`DEBATE: ${text}\n${result.for_name} vs ${result.against_name}`,'system-msg');
                    for(const e of result.debate_log) addMessage(`${e.speaker} (${e.side})`,e.content,'',`Round ${e.round}`);
                    addMessage(`Judge (${result.judge})`,result.judgment,'judge-msg','VERDICT');
                    let debRounds = result.debate_log.map(e=>`<div class="doc-round"><div class="doc-round-meta">Round ${e.round} · ${e.side}</div><div class="doc-round-speaker">${escapeHtml(e.speaker)}</div><div class="doc-round-text">${escapeHtml(e.content)}</div></div>`).join('');
                    showDoc(`<div class="doc-sec-title">⚔️ Debate Log</div>${debRounds}<div class="doc-verdict"><div class="doc-verdict-label">⚖️ Verdict — ${escapeHtml(result.judge)}</div><div class="doc-verdict-text">${escapeHtml(result.judgment)}</div></div>`, text, `${result.for_name} vs ${result.against_name}`);
                } else if(currentMode==='discuss'){
                    result=await safeFetch('/api/discuss',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({topic:text})});
                    removeLoading(loadId);
                    const disParticipants = result.participants || [];
                    addMessage('System',`DISCUSSION: ${text}`,'system-msg');
                    for(const e of (result.discussion_log||[])) addMessage(e.speaker,e.content,'',`Round ${e.round}`);
                    addMessage('Summary',result.summary||result.error,'judge-msg','CONCLUSION');
                    let disRounds = (result.discussion_log||[]).map(e=>`<div class="doc-round"><div class="doc-round-meta">Round ${e.round}</div><div class="doc-round-speaker">${escapeHtml(e.speaker)}</div><div class="doc-round-text">${escapeHtml(e.content)}</div></div>`).join('');
                    showDoc(`<div class="doc-sec-title">🗣️ Discussion</div>${disRounds}<div class="doc-verdict"><div class="doc-verdict-label">📌 Conclusion</div><div class="doc-verdict-text">${escapeHtml(result.summary||result.error||'')}</div></div>`, text, `Participants: ${disParticipants.join(', ')}`);
                } else if(currentMode==='best'){
                    result=await safeFetch('/api/best',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({question:text})});
                    removeLoading(loadId);
                    addMessage('System',`Finding Best: ${text}`,'system-msg');
                    addCompareCards(result.answers);
                    for(const e of result.evaluations) addMessage(`${e.evaluator}`,e.evaluation,'','EVAL');
                    addMessage('Winner',`${result.winner}\nVotes: ${JSON.stringify(result.votes)}`,'judge-msg','WINNER');
                    let bestCards = result.answers.map(r=>`<div class="doc-provider"><div class="doc-provider-name"><span class="dot"></span>${escapeHtml(r.provider)} <span class="ti">${r.elapsed_seconds}s</span></div><div class="doc-answer">${escapeHtml(r.success?r.content:'Error: '+r.error)}</div></div><hr class="doc-divider">`).join('');
                    showDoc(`<div class="doc-sec-title">🏆 Best Answer</div>${bestCards}<div class="doc-winner"><div class="doc-winner-label">🏆 Winner</div><div class="doc-winner-text">${escapeHtml(result.winner)}</div></div>`, text, `Votes: ${JSON.stringify(result.votes)}`);
                } else if(currentMode==='persona_debate'){
                    const p1=document.getElementById('personaFor').value, p2=document.getElementById('personaAgainst').value;
                    result=await safeFetch('/api/persona_debate',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({topic:text,persona_for:p1,persona_against:p2})});
                    removeLoading(loadId);
                    addMessage('System',`${result.for_name} vs ${result.against_name}: ${text}`,'system-msg');
                    for(const e of result.debate_log) addMessage(`${e.speaker} (${e.side})`,e.content,'',`Round ${e.round}`);
                    addMessage(`Judge (${result.judge})`,result.judgment,'judge-msg','VERDICT');
                    let pdRounds = result.debate_log.map(e=>`<div class="doc-round"><div class="doc-round-meta">Round ${e.round} · ${e.side}</div><div class="doc-round-speaker">${escapeHtml(e.speaker)}</div><div class="doc-round-text">${escapeHtml(e.content)}</div></div>`).join('');
                    showDoc(`<div class="doc-sec-title">🎭 Persona Debate</div>${pdRounds}<div class="doc-verdict"><div class="doc-verdict-label">⚖️ Verdict</div><div class="doc-verdict-text">${escapeHtml(result.judgment)}</div></div>`, text, `${result.for_name} vs ${result.against_name}`);
                } else if(currentMode==='persona_discuss'){
                    const sel=Array.from(document.querySelectorAll('.persona-cb:checked')).map(c=>c.value);
                    if(sel.length<2){removeLoading(loadId);addMessage('Error','Select at least 2 personas.','error-msg');}
                    else{
                        result=await safeFetch('/api/persona_discuss',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({topic:prompt,personas:sel})});
                        removeLoading(loadId);
                        const pdsParticipants = result.participants || [];
                        addMessage('System',`GROUP DISCUSSION: ${text}\nParticipants: ${pdsParticipants.join(', ')}`,'system-msg');
                        for(const e of (result.discussion_log||[])) addMessage(e.speaker,e.content,'',`Round ${e.round}`);
                        addMessage('Synthesis',result.synthesis||result.error,'judge-msg','CONCLUSION');
                        let pdsRounds = (result.discussion_log||[]).map(e=>`<div class="doc-round"><div class="doc-round-meta">Round ${e.round}</div><div class="doc-round-speaker">${escapeHtml(e.speaker)}</div><div class="doc-round-text">${escapeHtml(e.content)}</div></div>`).join('');
                        showDoc(`<div class="doc-sec-title">🧠 Persona Group Discussion</div>${pdsRounds}<div class="doc-verdict"><div class="doc-verdict-label">💡 Synthesis</div><div class="doc-verdict-text">${escapeHtml(result.synthesis||result.error||'')}</div></div>`, text, `Participants: ${pdsParticipants.join(', ')}`);
                    }
                } else if(currentMode==='persona_report'){
                    const sel=Array.from(document.querySelectorAll('.persona-cb:checked')).map(c=>c.value);
                    if(sel.length<1){removeLoading(loadId);addMessage('Error','Select at least 1 persona.','error-msg');}
                    else{
                        result=await safeFetch('/api/persona_report',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({topic:prompt,personas:sel,provider:currentProvider})});
                        removeLoading(loadId);
                        if(result.error){addMessage('Error',result.error,'error-msg');}
                        else{
                            let anaCards=(result.analyses||[]).map(a=>`<div class="doc-provider"><div class="doc-provider-name"><span class="dot"></span>${escapeHtml(a.persona_name)}</div><div class="doc-answer">${escapeHtml(a.analysis)}</div></div><hr class="doc-divider">`).join('');
                            addMessage('System',`MULTI-PERSONA REPORT: ${text}\n${(result.analyses||[]).map(a=>a.persona_name).join(', ')}`,'system-msg');
                            addMessage('Report',result.report||'','judge-msg','EXECUTIVE REPORT');
                            showDoc(`<div class="doc-sec-title">📊 Multi-Persona Report (${result.persona_count} perspectives)</div>${anaCards}<div class="doc-verdict"><div class="doc-verdict-label">📋 Executive Report</div><div class="doc-verdict-text">${escapeHtml(result.report||'')}</div></div>`, text, `Report: ${result.persona_count} personas`);
                        }
                    }
                } else if(currentMode==='decision_matrix'){
                    const opts=document.getElementById('dmOptions').value.split(',').map(s=>s.trim()).filter(Boolean);
                    const crit=document.getElementById('dmCriteria').value.split(',').map(s=>s.trim()).filter(Boolean);
                    const sel=Array.from(document.querySelectorAll('#dmPersonaCheckboxes input:checked')).map(c=>c.value);
                    if(opts.length<2||crit.length<1||sel.length<1){removeLoading(loadId);addMessage('Error','Need ≥2 options, ≥1 criteria, ≥1 persona','error-msg');}
                    else{
                        result=await safeFetch('/api/decision_matrix',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({options:opts,criteria:crit,personas:sel})});
                        removeLoading(loadId);
                        if(result.error){addMessage('Error',result.error,'error-msg');}
                        else{
                            let evalCards=(result.evaluations||[]).map(e=>`<div class="doc-provider"><div class="doc-provider-name"><span class="dot"></span>${escapeHtml(e.persona_name)}</div><div class="doc-answer">${escapeHtml(e.evaluation)}</div></div><hr class="doc-divider">`).join('');
                            addMessage('System',`DECISION MATRIX: ${opts.join(' vs ')}`,'system-msg');
                            addMessage('Matrix Result',result.synthesis||'','judge-msg','SCORECARD');
                            showDoc(`<div class="doc-sec-title">⚖️ Decision Matrix</div><div style="font-size:11px;color:var(--text2);margin-bottom:8px;">Options: ${opts.join(', ')} | Criteria: ${crit.join(', ')}</div>${evalCards}<div class="doc-verdict"><div class="doc-verdict-label">📊 Final Scorecard</div><div class="doc-verdict-text">${escapeHtml(result.synthesis||'')}</div></div>`, text, `Matrix: ${opts.join(' vs ')}`);
                        }
                    }
                } else if(currentMode==='persona_chain'){
                    const sel=Array.from(document.querySelectorAll('.persona-cb:checked')).map(c=>c.value);
                    if(sel.length<2){removeLoading(loadId);addMessage('Error','Select at least 2 personas for chain.','error-msg');}
                    else{
                        result=await safeFetch('/api/persona_chain',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({topic:prompt,personas:sel,provider:currentProvider})});
                        removeLoading(loadId);
                        if(result.error){addMessage('Error',result.error,'error-msg');}
                        else{
                            let chainCards=(result.chain||[]).map(c=>`<div class="doc-round"><div class="doc-round-meta">Step ${c.step}</div><div class="doc-round-speaker">${escapeHtml(c.persona_name)}</div><div class="doc-round-text">${escapeHtml(c.analysis)}</div></div>`).join('');
                            addMessage('System',`CHAIN ANALYSIS: ${text}`,'system-msg');
                            (result.chain||[]).forEach(c=>addMessage(c.persona_name,c.analysis,'',`Step ${c.step}`));
                            addMessage('Conclusion',result.conclusion||'','judge-msg','FINAL');
                            showDoc(`<div class="doc-sec-title">🔗 Chain Analysis (${result.steps} steps)</div>${chainCards}<div class="doc-verdict"><div class="doc-verdict-label">🎯 Final Conclusion</div><div class="doc-verdict-text">${escapeHtml(result.conclusion||'')}</div></div>`, text, `Chain: ${result.steps} steps`);
                        }
                    }
                } else if(currentMode==='persona_vote'){
                    const sel=Array.from(document.querySelectorAll('.persona-cb:checked')).map(c=>c.value);
                    if(sel.length<2){removeLoading(loadId);addMessage('Error','Select at least 2 personas.','error-msg');}
                    else{
                        result=await safeFetch('/api/persona_vote',{method:'POST',headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({proposal:prompt,personas:sel,provider:currentProvider})});
                        removeLoading(loadId);
                        if(result.error){addMessage('Error',result.error,'error-msg');}
                        else{
                            const t=result.tally||{};
                            const voteColors={APPROVE:'#4caf50',OPPOSE:'#f44336',CONDITIONAL:'#ff9800',ABSTAIN:'#666'};
                            let voteCards=(result.votes||[]).map(v=>{
                                const col=voteColors[v.vote]||'#666';
                                return `<div class="doc-provider"><div class="doc-provider-name"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${col};margin-right:6px;"></span>${escapeHtml(v.persona_name)} <span style="color:${col};font-weight:600;">${v.vote}</span></div><div class="doc-answer">${escapeHtml(v.response)}</div></div><hr class="doc-divider">`;
                            }).join('');
                            let tallyBar=`<div style="display:flex;gap:10px;margin:8px 0;font-size:12px;font-weight:600;"><span style="color:#4caf50;">✅ ${t.APPROVE||0}</span><span style="color:#f44336;">❌ ${t.OPPOSE||0}</span><span style="color:#ff9800;">⚠️ ${t.CONDITIONAL||0}</span></div>`;
                            let decisionCol=result.decision==='APPROVED'?'#4caf50':result.decision==='REJECTED'?'#f44336':'#ff9800';
                            addMessage('System',`VOTE: ${text}\nResult: ${result.decision} (${t.APPROVE||0} approve, ${t.OPPOSE||0} oppose, ${t.CONDITIONAL||0} conditional)`,'system-msg');
                            addMessage('Summary',result.summary||'','judge-msg',result.decision);
                            showDoc(`<div class="doc-sec-title">🗳️ Persona Voting (${result.total_votes} votes)</div>${tallyBar}<div style="text-align:center;font-size:18px;font-weight:700;color:${decisionCol};margin:10px 0;">${result.decision}</div>${voteCards}<div class="doc-verdict"><div class="doc-verdict-label">📋 Summary</div><div class="doc-verdict-text">${escapeHtml(result.summary||'')}</div></div>`, text, `Vote: ${result.decision}`);
                        }
                    }
                }
            }catch(e){removeLoading(loadId);addMessage('Error',e.message,'error-msg');}
            document.getElementById('sendBtn').disabled=false;input.focus();
        }
        document.getElementById('userInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});

        // ── Convenience: Prompt Library ──
        async function savePrompt() {
            const input=document.getElementById('userInput').value.trim();
            if(!input){addMessage('System','Type a prompt first to save it.','system-msg');return;}
            const name=prompt('Save prompt as:',input.slice(0,50));
            if(!name)return;
            await fetch('/api/prompts',{method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({name:name,prompt:input,mode:currentMode,personas:currentPersona?[currentPersona]:[]})});
            addMessage('System','✅ Prompt saved: '+name,'system-msg');
        }
        async function loadPrompts() {
            const r=await fetch('/api/prompts').then(r=>r.json());
            const list=r.prompts||[];
            if(!list.length){addMessage('System','No saved prompts yet.','system-msg');return;}
            let html='<div class="doc-sec-title">📋 Prompt Library</div>';
            list.forEach(function(p){
                html+=`<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;margin:4px 0;background:#1a1a2e;border:1px solid #2a2a3e;border-radius:6px;">
                    <div style="cursor:pointer;flex:1;" onclick="document.getElementById('userInput').value='${escapeHtml(p.prompt).replace(/'/g,"\\'")}';"><div style="font-weight:600;font-size:12px;">${escapeHtml(p.name)}</div><div style="font-size:10px;color:var(--text2);">${escapeHtml((p.prompt||'').slice(0,80))}</div></div>
                    <span style="cursor:pointer;color:#666;font-size:12px;" onclick="deletePrompt('${p.id}')">&times;</span></div>`;
            });
            showDoc(html,'Prompt Library','📋 Prompts');
        }
        async function deletePrompt(id){await fetch('/api/prompts/'+id,{method:'DELETE'});loadPrompts();}

        // ── Convenience: PDF Export ──
        function exportPDF() {
            const output=document.getElementById('outputArea');
            if(!output||!output.innerHTML.trim()){addMessage('System','Nothing to export. Generate output first.','system-msg');return;}
            const w=window.open('','_blank');
            w.document.write(`<html><head><title>AI Hub Export</title><style>body{font-family:'Inter',sans-serif;max-width:800px;margin:40px auto;padding:20px;color:#333;line-height:1.6;}h1{color:#1a1a2e;border-bottom:2px solid #6c5ce7;padding-bottom:8px;}.doc-sec-title{font-size:18px;font-weight:700;margin:20px 0 10px;}.doc-provider-name{font-weight:600;margin:8px 0;}.doc-answer{margin:8px 0 16px;padding:10px;background:#f8f9fa;border-radius:8px;white-space:pre-wrap;}.doc-verdict{margin:20px 0;padding:15px;background:#f0f4ff;border:1px solid #6c5ce7;border-radius:8px;}.doc-verdict-label{font-weight:700;}.doc-round{margin:10px 0;padding:10px;background:#f8f9fa;border-radius:6px;}.doc-round-speaker{font-weight:600;}.doc-divider{border:none;border-top:1px solid #eee;margin:10px 0;}@media print{body{margin:0;}}</style></head><body><h1>AI Hub Report</h1><div style="font-size:12px;color:#666;margin-bottom:20px;">${new Date().toLocaleString()}</div>`+output.innerHTML+'</body></html>');
            w.document.close();
            setTimeout(function(){w.print();},500);
        }



        // ── Convenience: Custom Persona ──
        function addCustomPersona() {
            const name=prompt('Persona display name:');
            if(!name)return;
            const key=name.toLowerCase().replace(/[^a-z0-9]+/g,'_');
            const desc=prompt('Describe this persona\'s role and expertise:');
            if(!desc)return;
            fetch('/api/add_custom_persona',{method:'POST',headers:{'Content-Type':'application/json'},
                body:JSON.stringify({key:key,name:name,prompt:desc})}).then(function(){
                    personas[key]=name;
                    const g=document.getElementById('personaGrid');
                    const lastBody=g.querySelector('.persona-group-body:last-child');
                    if(lastBody)lastBody.innerHTML+=`<div class="persona-chip" data-key="${key}" onclick="togglePersona('${key}')">${name}</div>`;
                    addMessage('System','✅ Custom persona added: '+name,'system-msg');
                });
        }

        // ── Init Decision Matrix Checkboxes ──
        function initDmCheckboxes() {
            const c=document.getElementById('dmPersonaCheckboxes');
            c.innerHTML='<div style="width:100%;font-size:10px;color:var(--accent2);margin-bottom:4px;">Select evaluators:</div>';
            personaGroups.forEach(function(group){
                group.personas.forEach(function(p){
                    c.innerHTML+=`<label style="display:flex;align-items:center;gap:4px;padding:3px 6px;background:#12121a;border:1px solid #2a2a3e;border-radius:5px;font-size:10px;cursor:pointer;"><input type="checkbox" value="${p.key}"> ${p.name}</label>`;
                });
            });
        }

        // ── Conversation History (Supabase) ──
        let currentConvId = null;
        let supabaseEnabled = false;

        async function initHistory() {
            try {
                const r = await fetch('/api/conversations').then(r=>r.json());
                supabaseEnabled = r.supabase;
                if (!supabaseEnabled) {
                    document.getElementById('historyList').innerHTML = '<div class="history-empty">No DB connected</div>';
                    return;
                }
                renderHistory(r.conversations || []);
            } catch(e) {
                document.getElementById('historyList').innerHTML = '<div class="history-empty">Error loading</div>';
            }
        }

        function renderHistory(convs) {
            const list = document.getElementById('historyList');
            if (!convs.length) {
                list.innerHTML = '<div class="history-empty">No conversations yet</div>';
                return;
            }
            list.innerHTML = convs.map(c => {
                const active = c.id === currentConvId ? ' active' : '';
                const date = new Date(c.updated_at).toLocaleDateString();
                return `<div class="history-item${active}" onclick="loadConversation('${c.id}')">
                    <span class="title">${escapeHtml(c.title)}</span>
                    <button class="del-btn" onclick="event.stopPropagation();deleteConversation('${c.id}')" title="Delete">🗑</button>
                </div>`;
            }).join('');
        }

        async function newConversation() {
            currentConvId = null;
            chatArea.innerHTML = '';
            if (typeof docPanel !== 'undefined' && docPanel) docPanel.innerHTML = '';
            initHistory();
        }

        async function ensureConversation(firstMsg) {
            if (currentConvId || !supabaseEnabled) return;
            try {
                const title = firstMsg.substring(0, 50);
                const r = await fetch('/api/conversations', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({title: title, mode: currentMode})
                }).then(r=>r.json());
                if (r.conversation) currentConvId = r.conversation.id;
            } catch(e) { console.log('Conv create error:', e); }
        }

        async function saveMsg(data) {
            if (!currentConvId || !supabaseEnabled) return;
            try {
                await fetch(`/api/conversations/${currentConvId}/messages`, {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify(data)
                });
            } catch(e) { console.log('Save msg error:', e); }
        }

        async function loadConversation(convId) {
            currentConvId = convId;
            chatArea.innerHTML = '';
            initHistory();
            try {
                const r = await fetch(`/api/conversations/${convId}/messages`).then(r=>r.json());
                for (const m of (r.messages || [])) {
                    if (m.role === 'user') {
                        addMessage('You', m.content, 'user-msg');
                    } else {
                        addMessage(m.speaker || m.provider || 'AI', m.content, '', m.badge || m.model || '', m.elapsed_seconds ? m.elapsed_seconds+'s' : '');
                    }
                }
            } catch(e) { addMessage('Error', 'Failed to load conversation', 'error-msg'); }
        }

        async function deleteConversation(convId) {
            if (!confirm('Delete this conversation?')) return;
            try {
                await fetch(`/api/conversations/${convId}`, {method:'DELETE'});
                if (currentConvId === convId) { currentConvId = null; chatArea.innerHTML = ''; }
                initHistory();
            } catch(e) { console.log('Delete error:', e); }
        }

        // Patch send() to auto-save messages
        const _origSend = send;
        send = async function() {
            const text = document.getElementById('userInput').value.trim();
            if (text && supabaseEnabled) {
                await ensureConversation(text);
                saveMsg({role:'user', content:text, update_title: !currentConvId});
            }
            await _origSend();
            // Refresh history after sending
            if (supabaseEnabled) setTimeout(()=>initHistory(), 1000);
        };

        // ── Mobile Responsive ──
        function toggleSidebar() {
            document.querySelector('.sidebar').classList.toggle('open');
            document.getElementById('sidebarOverlay').classList.toggle('open');
        }
        function showMobilePanel(panel) {
            const tabs = document.querySelectorAll('.mobile-panel-tabs button');
            tabs.forEach(t => t.classList.remove('active'));
            const mp = document.querySelector('.main-panel');
            const op = document.querySelector('.output-panel');
            if (panel === 'chat') {
                tabs[0].classList.add('active');
                if(mp) { mp.classList.remove('mobile-hide'); }
                if(op) { op.classList.remove('mobile-show'); }
            } else {
                tabs[1].classList.add('active');
                if(mp) { mp.classList.add('mobile-hide'); }
                if(op) { op.classList.add('mobile-show'); }
            }
        }
        // Auto-close sidebar on mobile when mode/provider is selected
        const origSetMode = setMode;
        setMode = function(m) { origSetMode(m); if(window.innerWidth<=768) toggleSidebar(); };
        const origSetProvider = setProvider;
        setProvider = function(p) { origSetProvider(p); if(window.innerWidth<=768) toggleSidebar(); };

        // ── Admin Panel ──
        function initAdmin() {
            if (USER_TIER === 'owner') {
                document.getElementById('adminBtn').style.display = 'inline-block';
            }
        }
        function openAdmin() {
            document.getElementById('adminOverlay').classList.add('open');
            adminLoadUsers();
        }
        function closeAdmin() {
            document.getElementById('adminOverlay').classList.remove('open');
        }
        async function adminLoadUsers() {
            const tbody = document.getElementById('adminUserList');
            tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text2);">Loading...</td></tr>';
            try {
                const res = await fetch('/api/admin/users');
                const data = await res.json();
                if (!data.success) { tbody.innerHTML = `<tr><td colspan="8" style="color:var(--red);">${data.error}</td></tr>`; return; }
                if (!data.users.length) { tbody.innerHTML = '<tr><td colspan="8" style="color:var(--text2);">No users yet</td></tr>'; return; }
                tbody.innerHTML = data.users.map(u => {
                    const tierClass = `tier-${u.tier}`;
                    const lastLogin = u.last_login ? new Date(u.last_login).toLocaleDateString() : '-';
                    const statusIcon = u.is_active ? '🟢' : '🔴';
                    return `<tr>
                        <td><strong>${u.username}</strong></td>
                        <td><input type="text" id="editName_${u.id}" value="${escapeHtml(u.display_name||'')}" style="width:90px;background:#1a1a2e;color:var(--text);border:1px solid var(--border);border-radius:4px;font-size:11px;padding:3px;" onchange="adminUpdateField('${u.id}', 'display_name', this.value)"></td>
                        <td><input type="email" id="editEmail_${u.id}" value="${escapeHtml(u.email||'')}" style="width:120px;background:#1a1a2e;color:var(--text);border:1px solid var(--border);border-radius:4px;font-size:11px;padding:3px;" onchange="adminUpdateField('${u.id}', 'email', this.value)"></td>
                        <td><input type="tel" id="editPhone_${u.id}" value="${escapeHtml(u.phone||'')}" style="width:100px;background:#1a1a2e;color:var(--text);border:1px solid var(--border);border-radius:4px;font-size:11px;padding:3px;" onchange="adminUpdateField('${u.id}', 'phone', this.value)"></td>
                        <td style="white-space:nowrap;">
                          ${u.temp_password ? `<span id="tmpPwSpan_${u.id}" style="font-family:monospace;font-size:11px;cursor:pointer;color:var(--accent2);" title="클릭하면 표시됩니다" onclick="this.textContent=this.textContent==='●●●●'?'${escapeHtml(u.temp_password)}':'●●●●'">●●●●</span>` : '<span style="color:var(--text2);font-size:11px;">-</span>'}
                          <button class="admin-btn-sm" onclick="adminSetTempPw('${u.id}','${u.username}')" title="임시 비밀번호 설정" style="margin-left:4px;">🔑</button>
                          ${u.temp_password ? `<button class="admin-btn-sm" onclick="adminClearTempPw('${u.id}')" title="임시 비밀번호 삭제" style="margin-left:2px;color:var(--red);">✕</button>` : ''}
                        </td>
                        <td><select onchange="adminUpdateTier('${u.id}',this.value)" style="background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:5px;padding:2px 5px;font-size:11px;">
                            <option value="free" ${u.tier==='free'?'selected':''}>Free</option>
                            <option value="premium" ${u.tier==='premium'?'selected':''}>Premium</option>
                            <option value="admin" ${u.tier==='admin'?'selected':''}>Admin</option>
                            <option value="owner" ${u.tier==='owner'?'selected':''}>Owner</option>
                        </select></td>
                        <td><button class="admin-btn-sm" onclick="adminToggleActive('${u.id}',${!u.is_active})">${statusIcon}</button></td>
                        <td style="font-size:11px;color:var(--text2);">${lastLogin}</td>
                        <td><button class="admin-btn-sm" onclick="adminDeleteUser('${u.id}','${u.username}')" title="Delete">🗑️</button></td>
                    </tr>`;
                }).join('');
            } catch(e) { tbody.innerHTML = `<tr><td colspan="9" style="color:var(--red);">Error: ${e.message}</td></tr>`; }
        }
        async function adminAddUser() {
            const username = document.getElementById('newUsername').value.trim();
            const password = document.getElementById('newPassword').value.trim();
            const display_name = document.getElementById('newDisplayName').value.trim() || username;
            const tier = document.getElementById('newTier').value;
            if (!username || !password) { alert('Username and password are required'); return; }
            try {
                const res = await fetch('/api/admin/users', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({username, password, display_name, tier})
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('newUsername').value = '';
                    document.getElementById('newPassword').value = '';
                    document.getElementById('newDisplayName').value = '';
                    document.getElementById('newEmail').value = '';
                    document.getElementById('newPhone').value = '';
                    adminLoadUsers();
                } else { alert(data.error); }
            } catch(e) { alert('Error: ' + e.message); }
        }
        async function adminDeleteUser(id, name) {
            if (!confirm(`Delete user "${name}"? This cannot be undone.`)) return;
            try {
                const res = await fetch(`/api/admin/users/${id}`, {method:'DELETE'});
                const data = await res.json();
                if (data.success) adminLoadUsers();
                else alert(data.error);
            } catch(e) { alert('Error: ' + e.message); }
        }
        async function adminToggleActive(id, active) {
            try {
                await fetch(`/api/admin/users/${id}`, {
                    method:'PUT', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({is_active: active})
                });
                adminLoadUsers();
            } catch(e) { alert('Error: ' + e.message); }
        }
        async function adminUpdateTier(id, tier) {
            try {
                await fetch(`/api/admin/users/${id}`, {
                    method:'PUT', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({tier})
                });
            } catch(e) { alert('Error: ' + e.message); }
        }
        async function adminSetTempPw(id, username) {
            const pw = prompt(`"${username}" 의 임시 비밀번호를 입력하세요:`);
            if (pw === null) return;
            if (!pw.trim()) { alert('비밀번호를 입력해주세요.'); return; }
            try {
                const res = await fetch(`/api/admin/users/${id}`, {
                    method:'PUT', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({temp_password: pw.trim()})
                });
                const data = await res.json();
                if (data.success) adminLoadUsers();
                else alert(data.error);
            } catch(e) { alert('Error: ' + e.message); }
        }
        async function adminClearTempPw(id) {
            if (!confirm('임시 비밀번호를 삭제하겠습니까?')) return;
            try {
                const res = await fetch(`/api/admin/users/${id}`, {
                    method:'PUT', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({temp_password: null})
                });
                const data = await res.json();
                if (data.success) adminLoadUsers();
                else alert(data.error);
            } catch(e) { alert('Error: ' + e.message); }
        }

        // ── UI Toggle Functions ──
        let currentSidebarTab = 'mode';
        function switchSidebarTab(tab) {
            const sidebar = document.getElementById('mainSidebar');
            // If clicking the same tab, toggle sidebar
            if (currentSidebarTab === tab && !sidebar.classList.contains('hidden-sidebar')) {
                sidebar.classList.add('hidden-sidebar');
                document.getElementById('sidebarToggleBtn').textContent = '▶';
                return;
            }
            // Ensure sidebar is visible
            sidebar.classList.remove('hidden-sidebar');
            document.getElementById('sidebarToggleBtn').textContent = '◀';
            currentSidebarTab = tab;
            // Switch sections
            document.querySelectorAll('.sidebar-section').forEach(s => s.classList.remove('active'));
            document.getElementById('section' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add('active');
            // Highlight active tab
            document.querySelectorAll('.header-tab').forEach(t => t.classList.remove('active'));
            document.getElementById('tab' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add('active');
        }
        function toggleSidebarCollapse() {
            const sidebar = document.getElementById('mainSidebar');
            const btn = document.getElementById('sidebarToggleBtn');
            sidebar.classList.toggle('hidden-sidebar');
            btn.textContent = sidebar.classList.contains('hidden-sidebar') ? '▶' : '◀';
        }
        function toggleModeGroup(id) {
            const el = document.getElementById(id);
            const arrow = document.getElementById(id + 'Arrow');
            el.classList.toggle('collapsed');
            if (arrow) arrow.textContent = el.classList.contains('collapsed') ? '▶' : '▼';
        }
        function toggleInputTools() {
            const p = document.getElementById('inputToolsPanel');
            p.style.display = p.style.display === 'none' ? 'block' : 'none';
        }
        // Mode names for header label
        const MODE_LABELS = {chat:t('chat'),compare:t('compare'),debate:t('debate'),discuss:t('discuss'),best:t('best'),persona_debate:t('p_debate'),persona_discuss:t('p_discuss'),persona_report:t('p_report'),decision_matrix:t('dm'),persona_chain:t('chain'),persona_vote:t('vote')};
        const PROVIDER_LABELS = {chatgpt:'ChatGPT',gemini:'Gemini',azure:'Azure',claude:'Claude',grok:'Grok'};
        // Wrap setMode to update header label + auto-expand groups
        const origSetMode2 = setMode;
        setMode = function(m) {
            origSetMode2(m);
            document.getElementById('tabMode').textContent = MODE_LABELS[m] || m;
            const personaModes = ['persona_debate','persona_discuss','persona_report','persona_vote'];
            const analysisModes = ['decision_matrix','persona_chain'];
            if (personaModes.includes(m)) {
                document.getElementById('modePersona').classList.remove('collapsed');
                document.getElementById('modePersonaArrow').textContent = '▼';
            }
            if (analysisModes.includes(m)) {
                document.getElementById('modeAnalysis').classList.remove('collapsed');
                document.getElementById('modeAnalysisArrow').textContent = '▼';
            }
        };
        // Wrap setProvider to update header label
        const origSetProvider2 = setProvider;
        setProvider = function(p) {
            origSetProvider2(p);
            document.getElementById('tabProvider').textContent = PROVIDER_LABELS[p] || p;
        };

        // ── Session Info ──
        let sessionStartSecs = 0;
        function fmtDuration(secs) {
            const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
            return h > 0 ? h + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0')
                         : m + ':' + String(s).padStart(2,'0');
        }
        function fmtDate(iso) {
            if (!iso || iso === 'N/A (env admin)') return iso || '—';
            try { const d = new Date(iso); return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}); }
            catch(e) { return iso; }
        }
        function fmtTotalTime(mins) {
            if (!mins) return '0m';
            const h = Math.floor(mins / 60), m = mins % 60;
            return h > 0 ? h + 'h ' + m + 'm' : m + 'm';
        }
        function initSessionInfo() {
            fetch('/api/user/session-info').then(r=>r.json()).then(d => {
                document.getElementById('infoFirst').textContent = fmtDate(d.first_login);
                document.getElementById('infoLast').textContent = fmtDate(d.last_login);
                document.getElementById('infoTotal').textContent = fmtTotalTime(d.total_time_minutes);
                document.getElementById('infoIp').textContent = d.ip || '—';
                document.getElementById('infoLocation').textContent = d.location || '—';
                sessionStartSecs = d.current_session_seconds || 0;
                document.getElementById('infoSession').textContent = fmtDuration(sessionStartSecs);
                // Live timer
                setInterval(function() {
                    sessionStartSecs++;
                    document.getElementById('infoSession').textContent = fmtDuration(sessionStartSecs);
                }, 1000);
                // Force password change if temp password was set by admin
                if (d.must_change_password) showForcedPasswordChange();
            }).catch(()=>{});
        }
        function showForcedPasswordChange() {
            const overlay = document.createElement('div');
            overlay.id = 'forcedPwOverlay';
            overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;';
            overlay.innerHTML = `
                <div style="background:#12121a;border:1px solid #a29bfe;border-radius:16px;padding:32px;width:360px;text-align:center;">
                    <div style="font-size:32px;margin-bottom:12px;">🔑</div>
                    <h3 style="color:#a29bfe;margin-bottom:8px;">임시 비밀번호 변경 필요</h3>
                    <p style="color:#8888aa;font-size:13px;margin-bottom:20px;">관리자가 임시 비밀번호를 설정했습니다.<br>계속하려면 새 비밀번호를 설정해주세요.</p>
                    <input id="fpCurrentPw" type="password" placeholder="현재 (임시) 비밀번호" style="width:100%;padding:10px;margin-bottom:10px;background:#1a1a2e;color:#fff;border:1px solid #2a2a3e;border-radius:8px;font-size:13px;">
                    <input id="fpNewPw" type="password" placeholder="새 비밀번호 (4자 이상)" style="width:100%;padding:10px;margin-bottom:10px;background:#1a1a2e;color:#fff;border:1px solid #2a2a3e;border-radius:8px;font-size:13px;">
                    <input id="fpConfirmPw" type="password" placeholder="새 비밀번호 확인" style="width:100%;padding:10px;margin-bottom:16px;background:#1a1a2e;color:#fff;border:1px solid #2a2a3e;border-radius:8px;font-size:13px;">
                    <div id="fpError" style="color:#ff6b6b;font-size:12px;margin-bottom:10px;display:none;"></div>
                    <button onclick="submitForcedPasswordChange()" style="width:100%;padding:12px;background:linear-gradient(135deg,#a29bfe,#74b9ff);color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;">비밀번호 변경</button>
                </div>`;
            document.body.appendChild(overlay);
        }
        async function submitForcedPasswordChange() {
            const cur = document.getElementById('fpCurrentPw').value;
            const np = document.getElementById('fpNewPw').value;
            const cp = document.getElementById('fpConfirmPw').value;
            const err = document.getElementById('fpError');
            if (np !== cp) { err.textContent = '새 비밀번호가 일치하지 않습니다.'; err.style.display='block'; return; }
            if (np.length < 4) { err.textContent = '비밀번호는 4자 이상이어야 합니다.'; err.style.display='block'; return; }
            try {
                const res = await fetch('/api/user/change-password', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({current_password: cur, new_password: np})
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('forcedPwOverlay').remove();
                    addMessage('System', '✅ 비밀번호가 변경됐습니다. 이제 새 비밀번호로 로그인하세요.', 'system-msg');
                } else { err.textContent = data.error || '오류가 발생했습니다.'; err.style.display='block'; }
            } catch(e) { err.textContent = '네트워크 오류: ' + e.message; err.style.display='block'; }
        }

        initStatus(); initPersonas(); initHistory(); initDmCheckboxes(); applyLang(); initAdmin(); initSessionInfo();

        // ── Voice Support (Web Speech API) ──
        let recognition = null;
        let isRecording = false;
        const micBtn = document.getElementById('micBtn');

        // Speech-to-Text
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SR();
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.lang = navigator.language || 'en-US';
            recognition.onstart = function() { isRecording = true; micBtn.classList.add('recording'); micBtn.textContent = String.fromCodePoint(9209,65039); };
            recognition.onend = function() { isRecording = false; micBtn.classList.remove('recording'); micBtn.textContent = String.fromCodePoint(127897,65039); };
            recognition.onresult = function(e) {
                var t = '';
                for (var i = e.resultIndex; i < e.results.length; i++) t += e.results[i][0].transcript;
                document.getElementById('userInput').value = t;
                if (e.results[e.results.length-1].isFinal) setTimeout(function(){ send(); }, 300);
            };
            recognition.onerror = function() { isRecording = false; micBtn.classList.remove('recording'); micBtn.textContent = String.fromCodePoint(127897,65039); };
        } else {
            micBtn.style.display = 'none';
        }

        function toggleMic() {
            if (!recognition) return;
            if (isRecording) recognition.stop(); else recognition.start();
        }

        // Text-to-Speech (OpenAI TTS with browser fallback)
        var currentAudio = null;
        async function speakText(text) {
            if (currentAudio) { currentAudio.pause(); currentAudio = null; }
            if (window.speechSynthesis) window.speechSynthesis.cancel();
            var cleaned = text.replace(/[#*`_~>|\\-]/g, '').replace(/\n+/g, '. ').substring(0, 4000);
            try {
                var resp = await fetch('/api/tts', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text: cleaned, voice: 'nova'})
                });
                if (resp.ok) {
                    var ct = resp.headers.get('content-type') || '';
                    if (ct.indexOf('audio') >= 0) {
                        var blob = await resp.blob();
                        currentAudio = new Audio(URL.createObjectURL(blob));
                        currentAudio.play();
                        return;
                    }
                }
            } catch(e) { console.log('TTS fallback:', e); }
            if ('speechSynthesis' in window) {
                var u = new SpeechSynthesisUtterance(cleaned);
                u.lang = navigator.language || 'en-US';
                window.speechSynthesis.speak(u);
            }
        }

        // Audio file transcription (Whisper)
        async function transcribeAudio(file) {
            try {
                var fd = new FormData();
                fd.append('file', file);
                var loadId = addLoading('Transcribing audio...');
                var resp = await fetch('/api/transcribe', {method: 'POST', body: fd});
                var data = await resp.json();
                removeLoading(loadId);
                if (data.success) {
                    addMessage('System', 'Transcription: ' + file.name, 'system-msg');
                    document.getElementById('userInput').value = data.text;
                    send();
                } else {
                    addMessage('Error', data.error || 'Transcription failed', 'error-msg');
                }
            } catch(e) { addMessage('Error', 'Transcription error: ' + e.message, 'error-msg'); }
        }

        // Add speaker buttons to AI messages
        var chatObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                m.addedNodes.forEach(function(node) {
                    if (node.nodeType !== 1) return;
                    var mb = node.querySelector ? node.querySelector('.msg-body:not(.user-msg):not(.system-msg)') : null;
                    if (mb && !mb.querySelector('.speak-btn')) {
                        var btn = document.createElement('button');
                        btn.className = 'speak-btn';
                        btn.title = 'Read aloud';
                        btn.textContent = String.fromCodePoint(128266);
                        btn.onclick = function() { speakText(mb.textContent); };
                        var hdr = node.querySelector('.msg-header');
                        if (hdr) hdr.appendChild(btn);
                    }
                });
            });
        });
        chatObserver.observe(chatArea, { childList: true });

        // ── Slide Generation ──
        async function generateSlides(topic) {
            if (!topic) { topic = prompt('Enter presentation topic:'); if (!topic) return; }
            var loadId = addLoading('Generating slides...');
            try {
                var prompt_text = 'Create a presentation about: ' + topic + '. Return ONLY valid JSON array with this exact format: [{"title":"Title Slide","content":"Subtitle","bullets":[]},{"title":"Slide 2 Title","content":"","bullets":["Point 1","Point 2","Point 3"]}]. Create 6-10 slides. No markdown, no explanation, ONLY the JSON array.';
                var resp = await safeFetch('/api/chat', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: prompt_text, provider: currentProvider || 'gemini', mode: 'chat'})
                });
                var data = await resp.json();
                removeLoading(loadId);
                var aiText = data.response || data.responses?.[0]?.response || '';
                // Extract JSON from response
                var jsonMatch = aiText.match(/\[[\s\S]*\]/);
                if (!jsonMatch) { addMessage('Error', 'Could not parse slides. Try again.', 'error-msg'); return; }
                var slides = JSON.parse(jsonMatch[0]);
                currentSlides = slides;
                currentSlideTopic = topic;
                // Show in output panel
                showSlidesPreview(slides, topic);
                addMessage('System', 'Slides generated! Check Output panel for preview & download.', 'system-msg');
                // Switch to output on mobile
                if (window.innerWidth <= 768) showMobilePanel('output');
            } catch(e) { removeLoading(loadId); addMessage('Error', 'Slides error: ' + e.message, 'error-msg'); }
        }
        var currentSlides = null;
        var currentSlideTopic = '';

        function showSlidesPreview(slides, topic) {
            var outputArea = document.querySelector('.output-area') || document.getElementById('outputArea');
            if (!outputArea) return;
            var html = '<div style="margin-bottom:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">';
            html += '<span style="font-size:18px;font-weight:700;color:var(--accent2);">Presentation: ' + topic + '</span>';
            html += '<button onclick="downloadPptx()" style="padding:8px 16px;border:1px solid var(--green);border-radius:8px;background:#0a2a1a;color:var(--green);cursor:pointer;font-family:Inter,sans-serif;font-size:12px;">Download PPTX</button>';
            html += '<button onclick="toggleSlideshow()" style="padding:8px 16px;border:1px solid var(--accent);border-radius:8px;background:#1a1a3a;color:var(--accent2);cursor:pointer;font-family:Inter,sans-serif;font-size:12px;">Slideshow</button>';
            html += '</div>';
            slides.forEach(function(s, i) {
                html += '<div style="background:#12121f;border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:12px;">';
                html += '<div style="font-size:11px;color:var(--text2);margin-bottom:8px;">Slide ' + (i+1) + '</div>';
                html += '<div style="font-size:' + (i===0?'24px':'18px') + ';font-weight:700;color:#e0e0ff;margin-bottom:12px;">' + s.title + '</div>';
                if (s.content) html += '<div style="color:#aaa;font-size:14px;margin-bottom:8px;">' + s.content + '</div>';
                if (s.bullets && s.bullets.length) {
                    s.bullets.forEach(function(b) { html += '<div style="color:#bbb;font-size:14px;padding:4px 0 4px 16px;">• ' + b + '</div>'; });
                }
                html += '</div>';
            });
            outputArea.innerHTML = html;
        }

        async function downloadPptx() {
            if (!currentSlides) return;
            try {
                var resp = await fetch('/api/slides', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({slides: currentSlides, title: currentSlideTopic})
                });
                if (resp.ok) {
                    var blob = await resp.blob();
                    var a = document.createElement('a');
                    a.href = URL.createObjectURL(blob);
                    a.download = (currentSlideTopic || 'presentation') + '.pptx';
                    a.click();
                }
            } catch(e) { addMessage('Error', 'Download failed: ' + e.message, 'error-msg'); }
        }

        function toggleSlideshow() {
            if (!currentSlides) return;
            var w = window.open('', '_blank');
            var html = '<!DOCTYPE html><html><head><title>' + currentSlideTopic + '</title>';
            html += '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.min.css">';
            html += '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/theme/black.min.css">';
            html += '<style>.reveal{font-family:Inter,sans-serif;} .reveal h2{color:#e0e0ff;} .reveal li{font-size:0.85em;margin:8px 0;}</style></head>';
            html += '<body><div class="reveal"><div class="slides">';
            currentSlides.forEach(function(s, i) {
                html += '<section>';
                html += '<h2>' + s.title + '</h2>';
                if (s.content) html += '<p style="color:#aaa;">' + s.content + '</p>';
                if (s.bullets && s.bullets.length) {
                    html += '<ul style="text-align:left;">';
                    s.bullets.forEach(function(b) { html += '<li>' + b + '</li>'; });
                    html += '</ul>';
                }
                html += '</section>';
            });
            html += '</div></div>';
            html += '<script src="https://cdn.jsdelivr.net/npm/reveal.js@4.6.0/dist/reveal.min.js"><\/script>';
            html += '<script>Reveal.initialize({hash:true,transition:"slide"});<\/script></body></html>';
            w.document.write(html);
            w.document.close();
        }

        // Allow /slides command in chat
        var _origSendForSlides = send;
        send = async function() {
            var input = document.getElementById('userInput');
            var val = (input.value || '').trim();
            if (val.toLowerCase().startsWith('/slides ')) {
                var topic = val.substring(8).trim();
                input.value = '';
                await generateSlides(topic);
                return;
            }
            await _origSendForSlides();
        };
        // ── Workspace ──
        var wsCurrentFolder = null;
        function openWorkspace() {
            document.getElementById('wsOverlay').classList.add('open');
            loadFolders();
        }
        function closeWorkspace() { document.getElementById('wsOverlay').classList.remove('open'); }

        async function loadFolders() {
            try {
                var r = await fetch('/api/folders').then(function(r){return r.json();});
                var el = document.getElementById('wsFolderList');
                if (!r.workspace) {
                    el.innerHTML = '<div style="color:var(--text2);font-size:12px;">Supabase not configured</div>';
                    return;
                }
                
                let folders = (r.folders || []).map(f => {
                    let descObj = {text: f.description || ''};
                    try {
                        let parsed = JSON.parse(f.description);
                        if (parsed && typeof parsed === 'object') descObj = parsed;
                    } catch(e) {}
                    f.parent_id = descObj.parent_id || null;
                    f.descText = descObj.text || '';
                    return f;
                });
                
                let rootFolders = folders.filter(f => !f.parent_id);
                let html = '';
                
                function renderFolder(f, depth) {
                    var cls = wsCurrentFolder === f.id ? 'ws-folder-item active' : 'ws-folder-item';
                    let pad = depth * 15;
                    let h = `<div class="${cls}" style="padding-left:${12 + pad}px;" onclick="selectFolder('${f.id}')">
                        <span style="display:flex;align-items:center;gap:6px;">
                            ${depth > 0 ? `<span style="color:var(--text2);font-size:10px;">↳</span>` : ''}
                            ${f.icon||'📁'} <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${f.name}</span>
                        </span>
                        <div class="folder-actions">
                            ${depth < 2 ? `<button class="ws-close" onclick="event.stopPropagation();createSubFolder('${f.id}')" title="Add Subfolder" style="font-size:16px;margin-right:4px;">+</button>` : ''}
                            <button class="ws-close" onclick="event.stopPropagation();deleteFolder('${f.id}')" title="Delete">×</button>
                        </div>
                    </div>`;
                    let children = folders.filter(child => child.parent_id === f.id);
                    children.forEach(c => { h += renderFolder(c, depth + 1); });
                    return h;
                }
                
                rootFolders.forEach(f => { html += renderFolder(f, 0); });
                el.innerHTML = html;
            } catch(e) { console.log('loadFolders err:', e); }
        }

        async function createFolder() {
            var name = prompt('Folder name:');
            if (!name) return;
            var icon = prompt('Folder icon (emoji):', '📁') || '📁';
            var desc = prompt('Folder description (optional):', '') || '';
            let extDesc = JSON.stringify({text: desc, parent_id: null});
            await fetch('/api/folders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name,icon:icon,description:extDesc})});
            loadFolders();
        }

        async function createSubFolder(parentId) {
            var name = prompt('Subfolder name:');
            if (!name) return;
            var icon = prompt('Folder icon (emoji):', '📁') || '📁';
            var desc = prompt('Folder description (optional):', '') || '';
            let extDesc = JSON.stringify({text: desc, parent_id: parentId});
            await fetch('/api/folders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name,icon:icon,description:extDesc})});
            loadFolders();
        }

        async function deleteFolder(id) {
            if (!confirm('Delete this folder and all files?')) return;
            await fetch('/api/folders/'+id, {method:'DELETE'});
            if (wsCurrentFolder === id) wsCurrentFolder = null;
            loadFolders();
            document.getElementById('wsFileList').innerHTML = '';
        }

        async function selectFolder(id) {
            wsCurrentFolder = id;
            loadFolders();
            loadFiles(id);
        }

        async function loadFiles(folderId) {
            var r = await fetch('/api/folders/'+folderId+'/files').then(function(r){return r.json();});
            var el = document.getElementById('wsFileList');
            var html = '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">';
            html += '<button class="ws-btn ws-btn-green" onclick="saveNote()">+ Note</button>';
            html += '<button class="ws-btn" style="background:#2a2a3e;" onclick="triggerWorkspaceUpload()">+ Upload File</button>';
            html += '<button class="ws-btn" onclick="saveCurrentChat()">Save Chat</button>';
            html += '<button class="ws-btn" onclick="saveCurrentSlides()">Save Slides</button>';
            html += '<button class="ws-btn" style="border-color:var(--blue);color:var(--blue);" onclick="saveUploadedFile()">' + '\uD83D\uDCBE Save File</button>';
            html += '</div>';
            var files = r.files || [];
            // Sort: pinned first, then by date
            files.sort(function(a,b) {
                var pa = (a.metadata && a.metadata.pinned) ? 1 : 0;
                var pb = (b.metadata && b.metadata.pinned) ? 1 : 0;
                if (pa !== pb) return pb - pa;
                return 0;
            });
            files.forEach(function(f) {
                var icon = {note:'\uD83D\uDCDD',conversation:'\uD83D\uDCAC',slides:'\uD83D\uDCCA',file:'\uD83D\uDCC4'}[f.type] || '\uD83D\uDCC4';
                var date = f.updated_at ? new Date(f.updated_at).toLocaleDateString() : '';
                var pinned = f.metadata && f.metadata.pinned;
                var pinIcon = pinned ? '\uD83D\uDCCC' : '\uD83D\uDCCC';
                var pinStyle = pinned ? 'color:var(--green);opacity:1;' : 'opacity:0.3;';
                var aiBtn = {note:'Ask AI',conversation:'Continue',slides:'Develop'}[f.type] || 'Ask AI';
                var border = pinned ? 'border-color:var(--green);' : '';
                html += '<div class="ws-file-item" style="'+border+'">';
                html += '<div style="display:flex;justify-content:space-between;align-items:center;">';
                html += '<div onclick="openFile(\'' + f.id + '\',\'' + f.type + '\')" style="cursor:pointer;flex:1;">';
                if (pinned) html += '<span style="font-size:10px;color:var(--green);font-weight:600;">PINNED </span>';
                html += '<div class="ws-file-type">' + icon + ' ' + f.type + '</div>';
                html += '<div class="ws-file-name">' + f.name + '</div>';
                html += '<div class="ws-file-date">' + date + '</div></div>';
                html += '<div style="display:flex;gap:4px;align-items:center;flex-shrink:0;">';
                html += '<button class="ws-btn" style="padding:4px 10px;font-size:11px;border-color:var(--accent);color:var(--accent2);" onclick="event.stopPropagation();askAiAboutFile(\'' + f.id + '\',\'' + f.type + '\')">\uD83E\uDD16 ' + aiBtn + '</button>';
                html += '<button style="border:none;background:none;cursor:pointer;font-size:14px;'+pinStyle+'" onclick="event.stopPropagation();togglePin(\'' + f.id + '\',' + (pinned?'false':'true') + ')" title="Pin">' + pinIcon + '</button>';
                html += '<button class="ws-close" onclick="event.stopPropagation();deleteFile(\'' + f.id + '\')" title="Delete">\u00D7</button>';
                html += '</div></div></div>';
            });
            if (!files.length) html += '<div style="color:var(--text2);font-size:13px;text-align:center;padding:20px;">No files yet. Create a note or save a chat!</div>';
            el.innerHTML = html;
        }

        async function togglePin(fileId, pin) {
            var r = await fetch('/api/files/'+fileId).then(function(r){return r.json();});
            var f = r.file;
            if (!f) return;
            var meta = f.metadata || {};
            meta.pinned = pin;
            await fetch('/api/files/'+fileId, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({metadata:meta})});
            if (wsCurrentFolder) loadFiles(wsCurrentFolder);
        }

        async function saveNote() {
            if (!wsCurrentFolder) return;
            var name = prompt('Note title:');
            if (!name) return;
            try {
                var r = await fetch('/api/folders/'+wsCurrentFolder+'/files', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({name:name, type:'note', content:''})
                }).then(function(r){return r.json();});
                if (r.error) {
                    alert('Error saving note:\n' + r.error);
                    return;
                }
                loadFiles(wsCurrentFolder);
                if (r.file && r.file.id) { closeWorkspace(); openFile(r.file.id, 'note'); }
            } catch(e) {
                alert('Connection error:\n' + e.message);
            }
        }

        async function uploadToWorkspace(file) {
            if (!wsCurrentFolder) return;
            var loadId = addLoading('Uploading and parsing file...');
            const fd = new FormData(); fd.append('file', file);
            try {
                const resp = await fetch('/api/upload', {method:'POST', body:fd});
                const ct = resp.headers.get('content-type') || '';
                if (!ct.includes('application/json')) {
                    alert(`Server Error (${resp.status})`);
                    removeLoading(loadId);
                    return;
                }
                const r = await resp.json();
                if(r.success) {
                    var saveResp = await fetch('/api/folders/'+wsCurrentFolder+'/files', {
                        method:'POST', headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({name: r.filename, type:'file', content: r.content})
                    }).then(res => res.json());
                    if (saveResp.error) alert('Error saving to workspace:\n' + saveResp.error);
                } else {
                    alert('Error parsing file:\n' + r.error);
                }
            } catch(e) {
                alert('Upload failed:\n' + e.message);
            }
            removeLoading(loadId);
            loadFiles(wsCurrentFolder);
        }

        function triggerWorkspaceUpload() {
            var input = document.createElement('input');
            input.type = 'file';
            input.multiple = true;
            input.accept = ".txt,.pdf,.csv,.md,.json,.py,.js,.html,.css,.xml,.log,.docx,.xlsx,.mp3,.wav,.m4a,.ogg,.webm";
            input.onchange = async e => {
                for (const f of e.target.files) {
                    await uploadToWorkspace(f);
                }
            };
            input.click();
        }

        async function saveCurrentChat() {
            if (!wsCurrentFolder) return;
            var msgs = document.querySelectorAll('.msg-body');
            var text = '';
            msgs.forEach(function(m){ text += m.textContent + '\n---\n'; });
            var name = prompt('Save chat as:', 'Chat ' + new Date().toLocaleDateString());
            if (!name) return;
            await fetch('/api/folders/'+wsCurrentFolder+'/files', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({name:name, type:'conversation', content:text})
            });
            loadFiles(wsCurrentFolder);
            addMessage('System', 'Chat saved to workspace!', 'system-msg');
        }

        async function saveCurrentSlides() {
            if (!wsCurrentFolder || !currentSlides) { addMessage('System', 'No slides to save. Use /slides first.', 'system-msg'); return; }
            var name = prompt('Save slides as:', currentSlideTopic);
            if (!name) return;
            await fetch('/api/folders/'+wsCurrentFolder+'/files', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({name:name, type:'slides', content:JSON.stringify(currentSlides), metadata:{topic:currentSlideTopic}})
            });
            loadFiles(wsCurrentFolder);
            addMessage('System', 'Slides saved to workspace!', 'system-msg');
        }

        async function saveUploadedFile() {
            if (!wsCurrentFolder) { addMessage('System', '먼저 폴더를 선택하세요.', 'system-msg'); return; }
            if (!uploadedFileContent || uploadedFiles.length === 0) { addMessage('System', '저장할 파일이 없습니다. 먼저 파일을 업로드하세요.', 'system-msg'); return; }
            var defaultName = uploadedFiles.length === 1 ? uploadedFiles[0].name : uploadedFiles.length + '개 파일';
            var name = prompt('파일 이름:', defaultName);
            if (!name) return;
            var meta = {original_files: uploadedFiles.map(function(f){return {name:f.name, size:f.size, chars:f.chars};})}
            await fetch('/api/folders/'+wsCurrentFolder+'/files', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({name:name, type:'file', content:uploadedFileContent, metadata:meta})
            });
            loadFiles(wsCurrentFolder);
            closeWorkspace();
            addMessage('System', '\uD83D\uDCBE 파일이 워크스페이스에 저장되었습니다: ' + name, 'system-msg');
        }

        async function openFile(fileId, type) {
            var r = await fetch('/api/files/'+fileId).then(function(r){return r.json();});
            var f = r.file;
            if (!f) return;
            closeWorkspace();
            var outputArea = document.querySelector('.output-area') || document.getElementById('outputArea');
            if (type === 'note') {
                if (outputArea) {
                    var html = '<div style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">';
                    html += '<span style="font-size:16px;font-weight:700;color:var(--accent2);">\uD83D\uDCDD ' + f.name + '</span>';
                    html += '<button class="ws-btn ws-btn-green" style="font-size:11px;" onclick="saveNoteContent(\'' + fileId + '\')">Save</button>';
                    html += '<button class="ws-btn" style="font-size:11px;" onclick="askAiAboutFile(\'' + fileId + '\',\'note\')">\uD83E\uDD16 Ask AI</button>';
                    html += '</div>';
                    html += '<textarea id="noteEditor" class="ws-editor" style="min-height:300px;" placeholder="Write your note here...">' + (f.content||'').replace(/</g,'&lt;') + '</textarea>';
                    html += '<div style="margin-top:8px;display:flex;gap:8px;">';
                    html += '<button class="ws-btn ws-btn-green" onclick="saveNoteContent(\'' + fileId + '\')">Save Note</button>';
                    html += '<span id="noteSaveStatus" style="font-size:12px;color:var(--text2);line-height:32px;"></span>';
                    html += '</div>';
                    outputArea.innerHTML = html;
                }
                if (window.innerWidth <= 768) showMobilePanel('output');
            } else if (type === 'conversation') {
                if (outputArea) {
                    var html = '<div style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">';
                    html += '<span style="font-size:16px;font-weight:700;color:var(--accent2);">\uD83D\uDCAC ' + f.name + '</span>';
                    html += '<button class="ws-btn" style="font-size:11px;" onclick="askAiAboutFile(\'' + fileId + '\',\'conversation\')">\uD83E\uDD16 Continue</button>';
                    html += '</div>';
                    html += '<div style="white-space:pre-wrap;color:var(--text);font-size:14px;line-height:1.8;">' + (f.content||'').replace(/</g,'&lt;') + '</div>';
                    outputArea.innerHTML = html;
                }
                if (window.innerWidth <= 768) showMobilePanel('output');
            } else if (type === 'slides') {
                try {
                    var slides = JSON.parse(f.content);
                    currentSlides = slides;
                    currentSlideTopic = (f.metadata && f.metadata.topic) || f.name;
                    showSlidesPreview(slides, currentSlideTopic);
                    if (window.innerWidth <= 768) showMobilePanel('output');
                } catch(e) {}
            } else if (type === 'file') {
                // Check if tabular data → render as spreadsheet
                if (isTabularContent(f.content, f.name)) {
                    var rows = parseTabularData(f.content);
                    if (rows) { renderSpreadsheet(rows, f.name, f.name); return; }
                }
                if (outputArea) {
                    var html = '<div style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">';
                    html += '<span style="font-size:16px;font-weight:700;color:var(--accent2);">\uD83D\uDCC4 ' + f.name + '</span>';
                    html += '<button class="ws-btn" style="font-size:11px;" onclick="askAiAboutFile(\'' + fileId + '\',\'file\')">🤖 Ask AI</button>';
                    html += '</div>';
                    if (f.metadata && f.metadata.original_files) {
                        html += '<div style="margin-bottom:12px;padding:8px 12px;background:#1a1a2e;border:1px solid var(--border);border-radius:8px;font-size:11px;color:var(--text2);">';
                        html += '📎 원본 파일: ';
                        f.metadata.original_files.forEach(function(of, idx) {
                            if (idx > 0) html += ', ';
                            html += of.name + ' (' + (of.size/1024).toFixed(1) + 'KB, ' + (of.chars||0).toLocaleString() + '자)';
                        });
                        html += '</div>';
                    }
                    html += '<div style="white-space:pre-wrap;color:var(--text);font-size:13px;line-height:1.8;max-height:70vh;overflow-y:auto;">' + (f.content||'').replace(/</g,'&lt;') + '</div>';
                    outputArea.innerHTML = html;
                }
                if (window.innerWidth <= 768) showMobilePanel('output');
            }
        }

        async function saveNoteContent(fileId) {
            var editor = document.getElementById('noteEditor');
            if (!editor) return;
            var status = document.getElementById('noteSaveStatus');
            if (status) status.textContent = 'Saving...';
            await fetch('/api/files/'+fileId, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content:editor.value})});
            if (status) { status.textContent = 'Saved!'; setTimeout(function(){status.textContent='';}, 2000); }
        }

        async function editNote(fileId) { openFile(fileId, 'note'); }

        async function askAiAboutFile(fileId, type) {
            var r = await fetch('/api/files/'+fileId).then(function(r){return r.json();});
            var f = r.file;
            if (!f) return;
            closeWorkspace();
            var content = f.content || '';
            var input = document.getElementById('userInput');
            if (type === 'note') {
                input.value = 'Based on this note, please analyze, expand, and suggest improvements:\n\n' + content;
            } else if (type === 'conversation') {
                input.value = 'Based on this previous conversation, continue the discussion and provide deeper insights:\n\n' + content.substring(0, 3000);
            } else if (type === 'slides') {
                try {
                    var slides = JSON.parse(content);
                    var summary = slides.map(function(s,i){return 'Slide '+(i+1)+': '+s.title;}).join(', ');
                    input.value = 'I have a presentation about "' + ((f.metadata && f.metadata.topic) || f.name) + '" with slides: ' + summary + '. Please suggest improvements.';
                } catch(e) { input.value = 'Analyze and improve this: ' + content.substring(0, 2000); }
            } else if (type === 'file') {
                input.value = '다음 파일("' + f.name + '")의 내용을 분석하고 요약해 주세요:\n\n' + content.substring(0, 5000);
            }
            addMessage('System', 'Loaded from workspace: ' + f.name, 'system-msg');
            send();
        }

        async function deleteFile(id) {
            if (!confirm('Delete this file?')) return;
            await fetch('/api/files/'+id, {method:'DELETE'});
            if (wsCurrentFolder) loadFiles(wsCurrentFolder);
        }
    </script>
</body>
</html>
"""


# ──────────────────────────── Routes ────────────────────────────

@app.route("/")
@login_required
def index():
    import json
    status = hub.status()
    personas = hub.list_personas()
    persona_groups = hub.list_persona_groups()
    
    username = session.get("username", "")
    if username != "shinwookyi":
        filtered_groups = []
        filtered_personas = {}
        for g in persona_groups:
            limited_ps = g["personas"][:3]
            new_g = dict(g)
            new_g["personas"] = limited_ps
            filtered_groups.append(new_g)
            for p in limited_ps:
                filtered_personas[p["key"]] = personas[p["key"]]
        personas = filtered_personas
        persona_groups = filtered_groups

    html = MAIN_HTML.replace("AI_STATUS", json.dumps(status)).replace(
        "PERSONA_DATA", json.dumps(personas, ensure_ascii=False)).replace(
        "PERSONA_GROUPS_DATA", json.dumps(persona_groups, ensure_ascii=False)).replace(
        "USER_TIER_DATA", session.get("user_tier", "free")).replace(
        "USERNAME_DATA", username)
    return html


@app.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    try:
        data = request.json
        prompt = data.get("prompt", "")
        provider = data.get("provider", "chatgpt")
        persona = data.get("persona", "")
        response = None
        if persona:
            memory_context = ""
            conversation_context = ""
            user_id = session.get("username", "admin")
            if supabase_client:
                try:
                    mem_result = supabase_client.table("persona_memory").select("content").eq(
                        "user_id", user_id
                    ).eq("persona_key", persona).order("created_at", desc=True).limit(20).execute()
                    if mem_result.data:
                        memories = [m["content"] for m in mem_result.data]
                        memory_context = "\n".join(f"- {m}" for m in memories)
                except Exception:
                    pass
                try:
                    conv_result = supabase_client.table("persona_conversations").select(
                        "question,answer"
                    ).eq("user_id", user_id).eq(
                        "persona_key", persona
                    ).order("created_at", desc=True).limit(10).execute()
                    if conv_result.data:
                        convs = []
                        for c in reversed(conv_result.data):
                            convs.append(f"Q: {c['question'][:200]}\nA: {c['answer'][:300]}")
                        conversation_context = "\n\n".join(convs)
                except Exception:
                    pass
            full_memory = ""
            if memory_context:
                full_memory += f"KEY INSIGHTS:\n{memory_context}"
            if conversation_context:
                if full_memory:
                    full_memory += "\n\n"
                full_memory += f"RECENT CONVERSATION HISTORY:\n{conversation_context}"
            response = hub.ask_as(prompt, persona=persona, provider=provider,
                                  memory_context=full_memory)
            if response.success and supabase_client:
                try:
                    supabase_client.table("persona_conversations").insert({
                        "user_id": user_id,
                        "persona_key": persona,
                        "question": prompt[:2000],
                        "answer": response.content[:3000],
                        "provider": provider
                    }).execute()
                except Exception:
                    pass
                if len(response.content) > 50:
                    try:
                        extract = hub.ask(
                            f"From this conversation, extract ONE concise key insight or fact worth remembering "
                            f"for future reference (1 sentence max, in the language of the content). "
                            f"If nothing worth remembering, respond with exactly 'NONE'.\n\n"
                            f"User asked: {prompt[:500]}\nResponse: {response.content[:1000]}",
                            provider=provider,
                            system_prompt="You are a memory extraction assistant. Extract only genuinely useful facts or insights. Respond with a single sentence or 'NONE'."
                        )
                        if extract.success and extract.content.strip().upper() != "NONE" and len(extract.content.strip()) > 5:
                            supabase_client.table("persona_memory").insert({
                                "user_id": user_id,
                                "persona_key": persona,
                                "content": extract.content.strip()[:500]
                            }).execute()
                    except Exception:
                        pass
        else:
            response = hub.ask(prompt, provider=provider)
        return jsonify({"provider": response.provider, "model": response.model,
                         "content": response.content, "success": response.success,
                         "error": response.error, "elapsed_seconds": response.elapsed_seconds})
    except Exception as e:
        return jsonify({"success": False, "error": f"서버 오류: {str(e)}", "content": "", "provider": "error", "model": "", "elapsed_seconds": 0}), 500


@app.route("/api/compare", methods=["POST"])
@login_required
def api_compare():
    try:
        data = request.json
        results = hub.ask_all(data.get("prompt", ""))
        return jsonify({"results": [{"provider": r.provider, "model": r.model,
            "content": r.content, "success": r.success, "error": r.error,
            "elapsed_seconds": r.elapsed_seconds} for r in results]})
    except Exception as e:
        return jsonify({"error": str(e), "results": []}), 500


@app.route("/api/debate", methods=["POST"])
@login_required
def api_debate():
    try:
        topic = request.json.get("topic", "")
        av = hub.available_providers()
        result = hub.debate(topic=topic, rounds=2, ai_for=av[0],
            ai_against=av[1] if len(av) > 1 else av[0],
            judge=av[2] if len(av) >= 3 else av[0])
        return jsonify({"topic": result["topic"], "for_name": result["for"],
            "against_name": result["against"], "judge": result["judge"],
            "debate_log": result["debate_log"], "judgment": result["judgment"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/discuss", methods=["POST"])
@login_required
def api_discuss():
    try:
        topic = request.json.get("topic", "")
        result = hub.discuss(topic=topic, rounds=2)
        return jsonify({"topic": result["topic"], "participants": result["participants"],
            "discussion_log": result["discussion_log"], "summary": result["summary"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/best", methods=["POST"])
@login_required
def api_best():
    try:
        question = request.json.get("question", "")
        result = hub.find_best(question=question)
        return jsonify({"question": result["question"],
            "answers": [{"provider": r.provider, "model": r.model, "content": r.content,
                "success": r.success, "error": r.error, "elapsed_seconds": r.elapsed_seconds}
                for r in result["answers"]],
            "evaluations": result["evaluations"], "votes": result["votes"], "winner": result["winner"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona_debate", methods=["POST"])
@login_required
def api_persona_debate():
    try:
        data = request.json
        av = hub.available_providers()
        result = hub.persona_debate(topic=data.get("topic", ""),
            persona_for=data.get("persona_for", "elon_musk"),
            persona_against=data.get("persona_against", "trump"),
            ai_for=av[0], ai_against=av[1] if len(av) > 1 else av[0],
            judge=av[2] if len(av) >= 3 else av[0], rounds=2)
        return jsonify({"topic": result["topic"], "for_name": result["for"],
            "against_name": result["against"], "judge": result["judge"],
            "debate_log": result["debate_log"], "judgment": result["judgment"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona_discuss", methods=["POST"])
@login_required
def api_persona_discuss():
    try:
        data = request.json
        result = hub.persona_discuss(topic=data.get("topic", ""),
            persona_keys=data.get("personas", []), rounds=2)
        if "error" in result:
            return jsonify({"error": result["error"]}), 400
        return jsonify({"topic": result["topic"], "participants": result["participants"],
            "discussion_log": result["discussion_log"], "synthesis": result["synthesis"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona_report", methods=["POST"])
@login_required
def api_persona_report():
    try:
        data = request.json
        personas = data.get("personas", [])
        if len(personas) < 1:
            return jsonify({"error": "Select at least 1 persona"}), 400
        result = hub.multi_persona_report(topic=data.get("topic", ""),
            persona_keys=personas, provider=data.get("provider", "chatgpt"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona_chain", methods=["POST"])
@login_required
def api_persona_chain():
    try:
        data = request.json
        personas = data.get("personas", [])
        if len(personas) < 2:
            return jsonify({"error": "Select at least 2 personas for chain"}), 400
        result = hub.persona_chain(topic=data.get("topic", ""),
            persona_keys=personas, provider=data.get("provider", "chatgpt"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona_vote", methods=["POST"])
@login_required
def api_persona_vote():
    try:
        data = request.json
        personas = data.get("personas", [])
        if len(personas) < 2:
            return jsonify({"error": "Select at least 2 personas for voting"}), 400
        result = hub.persona_vote(proposal=data.get("proposal", ""),
            persona_keys=personas, provider=data.get("provider", "chatgpt"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/decision_matrix", methods=["POST"])
@login_required
def api_decision_matrix():
    """Evaluate options against criteria using selected personas."""
    data = request.json
    options = data.get("options", [])
    criteria = data.get("criteria", [])
    personas = data.get("personas", [])
    if len(options) < 2 or len(criteria) < 1 or len(personas) < 1:
        return jsonify({"error": "Need ≥2 options, ≥1 criteria, ≥1 persona"}), 400

    available = [p for p in ["chatgpt", "gemini", "azure", "claude", "grok"]
                 if p in hub.providers]
    if not available:
        return jsonify({"error": "No AI providers available"}), 400

    scores = []
    for i, pkey in enumerate(personas):
        name = hub.get_persona_name(pkey)
        prompt_text = hub.get_persona_prompt(pkey)
        if not prompt_text:
            continue
        ai = available[i % len(available)]
        options_str = ", ".join(options)
        criteria_str = ", ".join(criteria)
        sys_prompt = (
            f"{prompt_text}\n\n"
            f"You are evaluating options in a decision matrix. "
            f"Score each option on each criterion from 1-10.\n"
            f"Respond in EXACTLY this format for each option:\n"
            f"OPTION_NAME: criterion1=N, criterion2=N, ...\n"
            f"Then one line: BEST: [your recommended option]"
        )
        resp = hub.ask(
            f"Evaluate these options: {options_str}\n"
            f"Against these criteria: {criteria_str}\n"
            f"Score each 1-10.",
            provider=ai, system_prompt=sys_prompt
        )
        scores.append({
            "persona_key": pkey, "persona_name": name,
            "evaluation": resp.content if resp.success else "Error",
            "provider": ai
        })

    # Synthesize
    all_evals = "\n\n".join(f"[{s['persona_name']}]:\n{s['evaluation']}" for s in scores)
    synth = hub.ask(
        f"Synthesize these decision matrix evaluations:\n\n{all_evals}\n\n"
        f"Options: {', '.join(options)}\nCriteria: {', '.join(criteria)}\n\n"
        f"Create a final scorecard table and recommend the best option.",
        provider=available[0],
        system_prompt="You are a decision matrix synthesizer. Present a clear scorecard."
    )
    return jsonify({
        "options": options, "criteria": criteria,
        "evaluations": scores, "synthesis": synth.content if synth.success else synth.error
    })


# ── Prompt Library ──

@app.route("/api/prompts", methods=["GET"])
@login_required
def api_prompts_list():
    if not supabase_client:
        return jsonify({"prompts": []})
    try:
        result = supabase_client.table("saved_prompts").select("*").eq(
            "user_id", session.get("username", "admin")
        ).order("created_at", desc=True).execute()
        return jsonify({"prompts": result.data or []})
    except Exception:
        return jsonify({"prompts": []})


@app.route("/api/prompts", methods=["POST"])
@login_required
def api_prompts_save():
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    data = request.json
    result = supabase_client.table("saved_prompts").insert({
        "user_id": session.get("username", "admin"),
        "name": data.get("name", "Untitled"),
        "prompt": data.get("prompt", ""),
        "mode": data.get("mode", "chat"),
        "personas": data.get("personas", [])
    }).execute()
    return jsonify({"prompt": result.data[0] if result.data else {}, "success": True})


@app.route("/api/prompts/<prompt_id>", methods=["DELETE"])
@login_required
def api_prompts_delete(prompt_id):
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    supabase_client.table("saved_prompts").delete().eq("id", prompt_id).execute()
    return jsonify({"deleted": True})


@app.route("/api/add_custom_persona", methods=["POST"])
@login_required
def api_add_custom_persona():
    data = request.json
    key = data.get("key", "custom")
    name = data.get("name", "Custom")
    prompt_text = data.get("prompt", "You are a helpful assistant.")
    hub.add_persona(key, name, prompt_text)
    return jsonify({"success": True, "key": key, "name": name})


@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file"})
    file = request.files['file']
    if not file.filename:
        return jsonify({"success": False, "error": "No filename"})
    ext = os.path.splitext(file.filename)[1].lower()
    filepath = os.path.join(UPLOAD_DIR, file.filename)
    file.save(filepath)
    try:
        content = ""
        if ext in (".txt",".md",".csv",".json",".py",".js",".html",".css",".xml",".log",
                    ".yaml",".yml",".toml",".ini",".cfg",".bat",".sh",".sql"):
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        elif ext == ".pdf":
            # Step 1: Try normal text extraction
            try:
                import pypdf
                with open(filepath, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages: content += page.extract_text() or ""
            except Exception: content = ""

            # Step 2: If text is empty → AI Vision OCR using GPT-4o
            if len(content.strip()) < 50 and hub.openai_api_key:
                try:
                    import fitz, base64  # PyMuPDF
                    from openai import OpenAI
                    client = OpenAI(api_key=hub.openai_api_key)
                    doc = fitz.open(filepath)
                    ocr_pages = []
                    total_pages = len(doc)
                    for i in range(total_pages):
                        pix = doc[i].get_pixmap(dpi=150)
                        b64 = base64.b64encode(pix.tobytes("png")).decode()
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role":"user","content":[
                                {"type":"text","text":f"이 PDF 페이지({i+1}/{total_pages})의 모든 텍스트를 정확하게 추출해주세요. 표, 숫자, 특수문자도 포함해서 원본 그대로 출력해주세요."},
                                {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}","detail":"high"}}
                            ]}],
                            max_tokens=4096
                        )
                        ocr_pages.append(f"=== 페이지 {i+1} ===\n{resp.choices[0].message.content}")
                    content = "\n\n".join(ocr_pages)
                    doc.close()
                except Exception as e:
                    if not content.strip(): content = f"[OCR 실패: {str(e)}]"
            elif len(content.strip()) < 50:
                content = "[PDF: 이미지 기반 PDF - OpenAI API 키 필요]"
        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(filepath)
                content = "\n".join(p.text for p in doc.paragraphs)
            except ImportError: content = "[DOCX: pip install python-docx]"
        elif ext == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True)
                for s in wb.sheetnames:
                    ws = wb[s]; content += f"\n--- {s} ---\n"
                    for row in ws.iter_rows(values_only=True):
                        content += "\t".join(str(c) if c else "" for c in row) + "\n"
            except ImportError: content = "[XLSX: pip install openpyxl]"
        else:
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f: content = f.read()
            except: content = "[Unsupported format]"
        if len(content) > 50000: content = content[:50000] + "\n\n[... truncated ...]"
        return jsonify({"success": True, "filename": file.filename,
            "size": os.path.getsize(filepath), "char_count": len(content), "content": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})



@app.route("/api/visualize", methods=["POST"])
@login_required
def api_visualize():
    """Ask AI to analyze context and return Chart.js data or Mermaid diagram"""
    try:
        context = request.json.get("context", "").strip()
        if not context:
            return jsonify({"success": False, "error": "No context provided"})

        prompt = f"""다음 데이터/내용을 분석하고, 가장 적합한 시각화를 선택하세요.

데이터:
{context[:6000]}

다음 중 하나의 JSON 형식으로만 응답하세요 (다른 텍스트 없이):

1. 숫자 데이터 → Chart.js 차트:
{{"type": "chart", "title": "제목", "chart_data": {{"type": "bar"|"line"|"pie"|"doughnut", "labels": [...], "datasets": [{{"label": "...", "data": [...]}}]}}}}

2. 프로세스/관계 → Mermaid 다이어그램:
{{"type": "diagram", "title": "제목", "diagram": "flowchart TD\\n  A --> B"}}

JSON만 반환하세요."""

        from openai import OpenAI
        client = OpenAI(api_key=hub.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        import json as _json
        result = _json.loads(resp.choices[0].message.content)

        if result.get("type") == "chart":
            return jsonify({"success": True, "title": result.get("title", "Chart"),
                            "chart_data": result["chart_data"]})
        elif result.get("type") == "diagram":
            return jsonify({"success": True, "title": result.get("title", "Diagram"),
                            "diagram": result["diagram"]})
        else:
            return jsonify({"success": False, "error": "예상치 못한 응답 형식"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/fetch_url", methods=["POST"])
@login_required
def api_fetch_url():
    """Fetch and extract text content from a URL for AI analysis"""
    try:
        url = request.json.get("url", "").strip()
        if not url:
            return jsonify({"success": False, "error": "No URL provided"})
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        import requests as req
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = req.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove scripts, styles, nav elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Clean up excessive blank lines
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)

        if len(text) > 40000:
            text = text[:40000] + "\n\n[... 내용이 길어 일부 생략됨 ...]"

        title = soup.title.string.strip() if soup.title else url

        return jsonify({
            "success": True,
            "url": url,
            "title": title,
            "content": text,
            "char_count": len(text)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ──────────────────────────── Conversation History (Supabase) ────────────────────────────

@app.route("/api/conversations", methods=["GET"])
@login_required
def api_conversations_list():
    """List all conversations for current user"""
    if not supabase_client:
        return jsonify({"conversations": [], "supabase": False})
    try:
        username = session.get("username", APP_USERNAME)
        result = supabase_client.table("conversations").select("*").eq(
            "username", username).order("updated_at", desc=True).limit(50).execute()
        return jsonify({"conversations": result.data, "supabase": True})
    except Exception as e:
        return jsonify({"conversations": [], "error": str(e), "supabase": True})


@app.route("/api/conversations", methods=["POST"])
@login_required
def api_conversations_create():
    """Create a new conversation"""
    if not supabase_client:
        return jsonify({"error": "Supabase not configured"}), 400
    try:
        data = request.json
        username = session.get("username", APP_USERNAME)
        result = supabase_client.table("conversations").insert({
            "title": data.get("title", "New Chat"),
            "mode": data.get("mode", "chat"),
            "username": username,
        }).execute()
        return jsonify({"conversation": result.data[0]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversations/<conv_id>/messages", methods=["GET"])
@login_required
def api_conversation_messages(conv_id):
    """Get all messages for a conversation"""
    if not supabase_client:
        return jsonify({"messages": []})
    try:
        result = supabase_client.table("messages").select("*").eq(
            "conversation_id", conv_id).order("created_at").execute()
        return jsonify({"messages": result.data})
    except Exception as e:
        return jsonify({"messages": [], "error": str(e)})


@app.route("/api/conversations/<conv_id>/messages", methods=["POST"])
@login_required
def api_conversation_save_message(conv_id):
    """Save a message to a conversation"""
    if not supabase_client:
        return jsonify({"saved": False})
    try:
        data = request.json
        msg = {
            "conversation_id": conv_id,
            "role": data.get("role", "user"),
            "speaker": data.get("speaker", ""),
            "content": data.get("content", ""),
            "provider": data.get("provider", ""),
            "model": data.get("model", ""),
            "badge": data.get("badge", ""),
            "elapsed_seconds": data.get("elapsed_seconds"),
        }
        supabase_client.table("messages").insert(msg).execute()
        # Update conversation title & timestamp
        title_update = {"updated_at": datetime.utcnow().isoformat()}
        if data.get("role") == "user" and data.get("update_title"):
            title_text = data.get("content", "")[:50]
            title_update["title"] = title_text
        supabase_client.table("conversations").update(title_update).eq("id", conv_id).execute()
        return jsonify({"saved": True})
    except Exception as e:
        return jsonify({"saved": False, "error": str(e)})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
@login_required
def api_conversation_delete(conv_id):
    """Delete a conversation and all its messages"""
    if not supabase_client:
        return jsonify({"deleted": False})
    try:
        supabase_client.table("conversations").delete().eq("id", conv_id).execute()
        return jsonify({"deleted": True})
    except Exception as e:
        return jsonify({"deleted": False, "error": str(e)})


# ──────────────────────────── Workspace: Folders & Files ────────────────────────────

@app.route("/api/folders", methods=["GET"])
@login_required
def api_folders_list():
    """List all folders"""
    if not supabase_client:
        return jsonify({"folders": [], "workspace": False})
    try:
        result = supabase_client.table("folders").select("*").eq(
            "user_id", session.get("username", "admin")
        ).order("created_at", desc=False).execute()
        return jsonify({"folders": result.data, "workspace": True})
    except:
        return jsonify({"folders": [], "workspace": True})


@app.route("/api/folders", methods=["POST"])
@login_required
def api_folders_create():
    """Create a new folder"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        data = request.json
        result = supabase_client.table("folders").insert({
            "user_id": session.get("username", "admin"),
            "name": data.get("name", "New Folder"),
            "icon": data.get("icon", "📁"),
            "description": data.get("description", "")
        }).execute()
        return jsonify({"folder": result.data[0] if result.data else {}, "success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/folders/<folder_id>", methods=["PUT"])
@login_required
def api_folders_update(folder_id):
    """Rename/update folder"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        data = request.json
        update = {}
        if "name" in data: update["name"] = data["name"]
        if "icon" in data: update["icon"] = data["icon"]
        if "description" in data: update["description"] = data["description"]
        supabase_client.table("folders").update(update).eq("id", folder_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/folders/<folder_id>", methods=["DELETE"])
@login_required
def api_folders_delete(folder_id):
    """Delete folder and its files"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        supabase_client.table("workspace_files").delete().eq("folder_id", folder_id).execute()
        supabase_client.table("folders").delete().eq("id", folder_id).execute()
        return jsonify({"deleted": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/folders/<folder_id>/files", methods=["GET"])
@login_required
def api_files_list(folder_id):
    """List files in a folder"""
    if not supabase_client:
        return jsonify({"files": []})
    try:
        result = supabase_client.table("workspace_files").select("*").eq(
            "folder_id", folder_id
        ).order("updated_at", desc=True).execute()
        return jsonify({"files": result.data})
    except:
        return jsonify({"files": []})


@app.route("/api/folders/<folder_id>/files", methods=["POST"])
@login_required
def api_files_create(folder_id):
    """Create/save a file in a folder"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        data = request.json
        result = supabase_client.table("workspace_files").insert({
            "folder_id": folder_id,
            "user_id": session.get("username", "admin"),
            "name": data.get("name", "Untitled"),
            "type": data.get("type", "note"),  # note, conversation, slides, file
            "content": data.get("content", ""),
            "metadata": data.get("metadata", {})
        }).execute()
        return jsonify({"file": result.data[0] if result.data else {}, "success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/<file_id>", methods=["GET"])
@login_required
def api_files_get(file_id):
    """Get file content"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        result = supabase_client.table("workspace_files").select("*").eq("id", file_id).execute()
        if result.data:
            return jsonify({"file": result.data[0]})
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/<file_id>", methods=["PUT"])
@login_required
def api_files_update(file_id):
    """Update file content"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        data = request.json
        update = {"updated_at": "now()"}
        if "name" in data: update["name"] = data["name"]
        if "content" in data: update["content"] = data["content"]
        if "metadata" in data: update["metadata"] = data["metadata"]
        supabase_client.table("workspace_files").update(update).eq("id", file_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files/<file_id>", methods=["DELETE"])
@login_required
def api_files_delete(file_id):
    """Delete a file"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        supabase_client.table("workspace_files").delete().eq("id", file_id).execute()
        return jsonify({"deleted": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────── Persona Memory API ────────────────────────────


@app.route("/api/persona/<persona_key>/memory", methods=["GET"])
@login_required
def api_persona_memory_list(persona_key):
    """List memories for a persona"""
    if not supabase_client:
        return jsonify({"memories": [], "error": "No database"}), 200
    try:
        result = supabase_client.table("persona_memory").select("*").eq(
            "user_id", session.get("username", "admin")
        ).eq("persona_key", persona_key).order("created_at", desc=True).execute()
        return jsonify({"memories": result.data or [], "count": len(result.data or [])})
    except Exception as e:
        return jsonify({"memories": [], "error": str(e)}), 200


@app.route("/api/persona/<persona_key>/memory", methods=["POST"])
@login_required
def api_persona_memory_add(persona_key):
    """Manually add a memory for a persona"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        data = request.json
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "Empty memory"}), 400
        result = supabase_client.table("persona_memory").insert({
            "user_id": session.get("username", "admin"),
            "persona_key": persona_key,
            "content": content[:500]
        }).execute()
        return jsonify({"memory": result.data[0] if result.data else {}, "success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona/memory/<memory_id>", methods=["DELETE"])
@login_required
def api_persona_memory_delete(memory_id):
    """Delete a specific memory"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        supabase_client.table("persona_memory").delete().eq("id", memory_id).execute()
        return jsonify({"deleted": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona/<persona_key>/memory/clear", methods=["DELETE"])
@login_required
def api_persona_memory_clear(persona_key):
    """Clear all memories AND conversations for a persona"""
    if not supabase_client:
        return jsonify({"error": "No database"}), 400
    try:
        supabase_client.table("persona_memory").delete().eq(
            "user_id", session.get("username", "admin")
        ).eq("persona_key", persona_key).execute()
        supabase_client.table("persona_conversations").delete().eq(
            "user_id", session.get("username", "admin")
        ).eq("persona_key", persona_key).execute()
        return jsonify({"cleared": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/persona/<persona_key>/conversations", methods=["GET"])
@login_required
def api_persona_conversations(persona_key):
    """List recent conversations for a persona"""
    if not supabase_client:
        return jsonify({"conversations": []})
    try:
        result = supabase_client.table("persona_conversations").select("*").eq(
            "user_id", session.get("username", "admin")
        ).eq("persona_key", persona_key).order("created_at", desc=True).limit(20).execute()
        return jsonify({"conversations": result.data or [], "count": len(result.data or [])})
    except Exception:
        return jsonify({"conversations": []})


# ──────────────────────────── Audio: OpenAI TTS ────────────────────────────

@app.route("/api/tts", methods=["POST"])
@login_required
def api_tts():
    """Convert text to natural speech using OpenAI TTS"""
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return jsonify({"error": "OpenAI API key not configured"}), 400
        client = OpenAI(api_key=api_key)
        data = request.json
        text = data.get("text", "")[:4096]  # TTS limit
        voice = data.get("voice", "alloy")  # alloy, echo, fable, onyx, nova, shimmer
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        # Return audio as binary
        from flask import Response
        return Response(response.content, mimetype="audio/mpeg",
                       headers={"Content-Disposition": "inline"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────── Audio: Whisper Transcription ────────────────────────────

@app.route("/api/transcribe", methods=["POST"])
@login_required
def api_transcribe():
    """Transcribe audio file to text using OpenAI Whisper"""
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return jsonify({"error": "OpenAI API key not configured"}), 400
        client = OpenAI(api_key=api_key)

        if "file" not in request.files:
            return jsonify({"error": "No audio file uploaded"}), 400

        audio_file = request.files["file"]
        # Save to temp file
        suffix = os.path.splitext(audio_file.filename)[1] or ".mp3"
        tmp_path = os.path.join(UPLOAD_DIR, f"whisper_{secrets.token_hex(4)}{suffix}")
        audio_file.save(tmp_path)

        try:
            with open(tmp_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f
                )
            return jsonify({"text": transcript.text, "success": True})
        finally:
            os.remove(tmp_path)
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


# ──────────────────────────── Slides: PPTX Generation ────────────────────────────

@app.route("/api/slides", methods=["POST"])
@login_required
def api_slides():
    """Generate PPTX from slide data and return for download"""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from io import BytesIO

        data = request.json
        slides_data = data.get("slides", [])
        title = data.get("title", "AI Hub Presentation")

        if not slides_data:
            return jsonify({"error": "No slides data"}), 400

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        for i, slide_data in enumerate(slides_data):
            slide_layout = prs.slide_layouts[6]  # Blank layout
            slide = prs.slides.add_slide(slide_layout)

            # Dark background
            bg = slide.background
            fill = bg.fill
            fill.solid()
            fill.fore_color.rgb = RGBColor(0x0d, 0x0d, 0x1a)

            s_title = slide_data.get("title", "")
            s_content = slide_data.get("content", "")
            s_bullets = slide_data.get("bullets", [])

            # Title
            left = Inches(0.8)
            top = Inches(0.6) if i == 0 else Inches(0.5)
            width = Inches(11.7)
            height = Inches(1.5) if i == 0 else Inches(1.0)
            txBox = slide.shapes.add_textbox(left, top, width, height)
            tf = txBox.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = s_title
            p.font.size = Pt(40) if i == 0 else Pt(32)
            p.font.bold = True
            p.font.color.rgb = RGBColor(0xe0, 0xe0, 0xff)
            p.alignment = PP_ALIGN.LEFT if i > 0 else PP_ALIGN.CENTER

            # Subtitle for title slide
            if i == 0 and s_content:
                p2 = tf.add_paragraph()
                p2.text = s_content
                p2.font.size = Pt(20)
                p2.font.color.rgb = RGBColor(0x88, 0x88, 0xaa)
                p2.alignment = PP_ALIGN.CENTER

            # Bullets
            if s_bullets and i > 0:
                b_top = Inches(1.8)
                b_height = Inches(5.0)
                txBox2 = slide.shapes.add_textbox(left, b_top, width, b_height)
                tf2 = txBox2.text_frame
                tf2.word_wrap = True
                for j, bullet in enumerate(s_bullets):
                    p = tf2.paragraphs[0] if j == 0 else tf2.add_paragraph()
                    p.text = bullet
                    p.font.size = Pt(22)
                    p.font.color.rgb = RGBColor(0xcc, 0xcc, 0xdd)
                    p.space_after = Pt(12)

            # Content paragraph for non-title slides
            if s_content and i > 0 and not s_bullets:
                c_top = Inches(1.8)
                txBox3 = slide.shapes.add_textbox(left, c_top, width, Inches(5.0))
                tf3 = txBox3.text_frame
                tf3.word_wrap = True
                p = tf3.paragraphs[0]
                p.text = s_content
                p.font.size = Pt(20)
                p.font.color.rgb = RGBColor(0xcc, 0xcc, 0xdd)

        # Save to buffer
        buffer = BytesIO()
        prs.save(buffer)
        buffer.seek(0)

        from flask import send_file
        safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:50] or "presentation"
        return send_file(buffer, mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        as_attachment=True, download_name=f"{safe_title}.pptx")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Global error handlers → always return JSON for /api/* ──
# ──────────────────────────── Admin: User Management ────────────────────────

@app.route("/api/admin/users", methods=["GET"])
@login_required
@admin_required
def admin_list_users():
    if not supabase_admin:
        return jsonify({"success": False, "error": "Supabase not configured"}), 400
    try:
        res = supabase_admin.table("users").select("id,username,tier,display_name,email,phone,is_active,created_at,last_login,temp_password").order("created_at", desc=False).execute()
        return jsonify({"success": True, "users": res.data or []})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/users", methods=["POST"])
@login_required
@admin_required
def admin_create_user():
    if not supabase_client:
        return jsonify({"success": False, "error": "Supabase not configured"}), 400
    data = request.json
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    tier = data.get("tier", "free")
    display_name = data.get("display_name", username)
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
    if len(password) < 4:
        return jsonify({"success": False, "error": "Password must be at least 4 characters"}), 400
    if tier not in ("owner", "admin", "premium", "free"):
        return jsonify({"success": False, "error": "Invalid tier"}), 400
    try:
        # Check if username exists
        existing = supabase_admin.table("users").select("id").eq("username", username).execute()
        if existing.data:
            return jsonify({"success": False, "error": "Username already exists"}), 409
        res = supabase_admin.table("users").insert({
            "username": username,
            "password_hash": _hash_password(password),
            "tier": tier,
            "display_name": display_name,
            "is_active": True,
        }).execute()
        return jsonify({"success": True, "user": res.data[0] if res.data else {}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/users/<user_id>", methods=["PUT"])
@login_required
@admin_required
def admin_update_user(user_id):
    if not supabase_admin:
        return jsonify({"success": False, "error": "Supabase not configured"}), 400
    data = request.json
    updates = {}
    if "tier" in data and data["tier"] in ("owner", "admin", "premium", "free"):
        updates["tier"] = data["tier"]
    if "display_name" in data:
        updates["display_name"] = data["display_name"]
    if "email" in data:
        updates["email"] = data["email"]
    if "phone" in data:
        updates["phone"] = data["phone"]
    if "is_active" in data:
        updates["is_active"] = bool(data["is_active"])
    if "password" in data and data["password"].strip():
        updates["password_hash"] = _hash_password(data["password"].strip())
    if "temp_password" in data:
        tp = data["temp_password"]
        if tp:
            # Setting temp password: also update actual login password and flag for forced change
            updates["temp_password"] = tp
            updates["password_hash"] = _hash_password(tp)
            updates["must_change_password"] = True
        else:
            # Clearing temp password: remove flag too
            updates["temp_password"] = None
            updates["must_change_password"] = False
    if not updates:
        return jsonify({"success": False, "error": "No valid fields to update"}), 400
    try:
        supabase_admin.table("users").update(updates).eq("id", user_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/users/<user_id>", methods=["DELETE"])
@login_required
@admin_required
def admin_delete_user(user_id):
    if not supabase_admin:
        return jsonify({"success": False, "error": "Supabase not configured"}), 400
    # Prevent deleting yourself
    if session.get("user_id") == user_id:
        return jsonify({"success": False, "error": "Cannot delete your own account"}), 400
    try:
        supabase_admin.table("users").delete().eq("id", user_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/user/password", methods=["POST"])
@login_required
def change_own_password():
    if not supabase_client:
        return jsonify({"success": False, "error": "Supabase not configured"}), 400
    data = request.json
    current_pw = (data.get("current_password") or "").strip()
    new_pw = (data.get("new_password") or "").strip()
    if not current_pw or not new_pw:
        return jsonify({"success": False, "error": "Both current and new passwords are required"}), 400
    if len(new_pw) < 4:
        return jsonify({"success": False, "error": "New password must be at least 4 characters"}), 400
    user_id = session.get("user_id")
    if not user_id or user_id == "env_admin":
        return jsonify({"success": False, "error": "Password change only available for Supabase users"}), 400
    try:
        res = supabase_client.table("users").select("password_hash").eq("id", user_id).execute()
        if not res.data or res.data[0]["password_hash"] != _hash_password(current_pw):
            return jsonify({"success": False, "error": "Current password is incorrect"}), 401
        supabase_client.table("users").update({
            "password_hash": _hash_password(new_pw),
            "temp_password": None,        # clear temp password
            "must_change_password": False  # clear forced-change flag
        }).eq("id", user_id).execute()
        session["must_change_password"] = False  # update session immediately
        return jsonify({"success": True, "message": "Password changed successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/user/session-info")
@login_required
def session_info():
    """Return user session stats for header display."""
    import requests as http_req
    user_id = session.get("user_id")
    login_time = session.get("login_time", datetime.utcnow().isoformat())
    now = datetime.utcnow()
    # Calculate current session duration
    try:
        lt = datetime.fromisoformat(login_time)
        session_secs = int((now - lt).total_seconds())
    except Exception:
        session_secs = 0
    info = {
        "first_login": None,
        "last_login": None,
        "total_time_minutes": 0,
        "current_session_seconds": session_secs,
        "ip": request.remote_addr or "unknown",
        "location": "—",
    }
    # Get data from Supabase
    if supabase_client and user_id and user_id != "env_admin":
        try:
            res = supabase_client.table("users").select("created_at,last_login,total_time_minutes").eq("id", user_id).execute()
            if res.data:
                u = res.data[0]
                info["first_login"] = u.get("created_at")
                info["last_login"] = u.get("last_login")
                info["total_time_minutes"] = u.get("total_time_minutes") or 0
        except Exception:
            pass
    elif user_id == "env_admin":
        info["first_login"] = "N/A (env admin)"
        info["last_login"] = login_time
    # Get IP geolocation
    try:
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
            info["ip"] = client_ip
        geo = http_req.get(f"http://ip-api.com/json/{client_ip}?fields=city,regionName,country", timeout=3).json()
        if geo.get("city"):
            info["location"] = f"{geo['city']}, {geo.get('regionName', '')} {geo.get('country', '')}"
    except Exception:
        pass
    info["must_change_password"] = session.get("must_change_password", False)
    return jsonify(info)


# ──────────────────────────── Error Handlers ────────────────────────────

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": str(e),
                        "detail": traceback.format_exc()[-500:]}), 500
    raise e


@app.errorhandler(500)
def handle_500(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Internal server error", "detail": str(e)}), 500
    return str(e), 500


if __name__ == "__main__":
    _seed_admin_user()
    port = int(os.getenv("PORT", 5000))
    print(f"\n  AI Hub Web App")
    print(f"  http://localhost:{port}")
    print(f"  Login: {APP_USERNAME}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
