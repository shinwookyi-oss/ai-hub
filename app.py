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
from functools import wraps
from datetime import datetime

from flask import Flask, request, jsonify, session, redirect, url_for

from ai_hub import AIHub

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

hub = AIHub()

APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "aihub2026")

UPLOAD_DIR = tempfile.mkdtemp(prefix="aihub_uploads_")

# ──────────────────────────── Supabase ────────────────────────────

supabase_client = None
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("  ✅ Supabase connected")
    except Exception as e:
        print(f"  ⚠️ Supabase init failed: {e}")
else:
    print("  ⚠️ Supabase not configured (no SUPABASE_URL/KEY)")


# ──────────────────────────── Authentication ────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            # Return JSON for API routes (includes file upload which uses multipart)
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"success": False, "error": "Session expired. Please refresh and login again."}), 401
            return redirect(url_for("login_page"))
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
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == APP_USERNAME and password == APP_PASSWORD:
            session["logged_in"] = True
            return redirect("/")
        return LOGIN_HTML.replace("ERROR_MSG", '<p class="error">Invalid credentials</p>')
    return LOGIN_HTML.replace("ERROR_MSG", "")


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
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
        /* 3-column layout */
        .container { display: flex; flex: 1; overflow: hidden; }
        .sidebar {
            width: 220px; min-width: 220px; flex-shrink: 0;
            background: var(--surface); border-right: 1px solid var(--border);
            padding: 12px; overflow-y: auto;
        }
        .sidebar h3 {
            font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px;
            color: var(--text2); margin-bottom: 10px; margin-top: 16px;
        }
        .sidebar h3:first-child { margin-top: 0; }
        .mode-btn {
            width: 100%; padding: 9px 12px; border: 1px solid var(--border);
            border-radius: 8px; background: var(--surface2); color: var(--text);
            font-size: 13px; font-family: 'Inter', sans-serif; cursor: pointer;
            margin-bottom: 5px; text-align: left; transition: all 0.2s;
        }
        .mode-btn:hover { border-color: var(--accent); background: #1e1e3a; }
        .mode-btn.active { border-color: var(--accent); background: #2a2058; }
        .persona-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
        .persona-chip {
            padding: 5px 6px; border: 1px solid var(--border); border-radius: 6px;
            background: var(--surface2); font-size: 10px; cursor: pointer;
            transition: all 0.2s; text-align: center; overflow: hidden;
            text-overflow: ellipsis; white-space: nowrap;
        }
        .persona-chip:hover { border-color: var(--accent); }
        .persona-chip.selected { border-color: var(--green); background: #1a3a2a; color: var(--green); }
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
        .input-row { display: flex; gap: 10px; }
        .input-row input {
            flex: 1; padding: 11px 16px; border: 1px solid var(--border); border-radius: 10px;
            background: var(--surface2); color: var(--text); font-size: 14px;
            font-family: 'Inter', sans-serif; outline: none; transition: border-color 0.2s;
        }
        .input-row input:focus { border-color: var(--accent); }
        .input-row input::placeholder { color: var(--text2); }
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
            .persona-grid { grid-template-columns: 1fr 1fr 1fr; }
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
            <h1>⚡ AI Hub</h1>
        </div>
        <div class="header-right">
            <div class="status-dots" id="statusDots"></div>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    <div class="mobile-panel-tabs" id="mobileTabs">
        <button class="active" onclick="showMobilePanel('chat')">💬 Chat</button>
        <button onclick="showMobilePanel('output')">📄 Output</button>
    </div>
    <div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
    <div class="container">
    <!-- Workspace Modal -->
    <div class="ws-overlay" id="wsOverlay" onclick="if(event.target===this)closeWorkspace()">
        <div class="ws-modal">
            <div class="ws-header">
                <h2>📂 My Workspace</h2>
                <button class="ws-close" onclick="closeWorkspace()">×</button>
            </div>
            <div class="ws-body">
                <div class="ws-folders">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <span style="font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;">Folders</span>
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
        <div class="sidebar">
            <button class="mode-btn" style="background:#1a1a3a;border-color:var(--accent);margin-bottom:12px;" onclick="openWorkspace()">📂 My Workspace</button>
            <h3>Mode</h3>
            <button class="mode-btn active" data-mode="chat" onclick="setMode('chat')">💬 Chat</button>
            <button class="mode-btn" data-mode="compare" onclick="setMode('compare')">🔄 Compare All</button>
            <button class="mode-btn" data-mode="debate" onclick="setMode('debate')">⚔️ Debate</button>
            <button class="mode-btn" data-mode="discuss" onclick="setMode('discuss')">🗣️ Discussion</button>
            <button class="mode-btn" data-mode="best" onclick="setMode('best')">🏆 Best Answer</button>
            <button class="mode-btn" data-mode="persona_debate" onclick="setMode('persona_debate')">🎭 Persona Debate</button>
            <button class="mode-btn" data-mode="persona_discuss" onclick="setMode('persona_discuss')">🧠 Persona Discussion</button>
            <h3>Provider</h3>
            <button class="mode-btn active" data-provider="chatgpt" onclick="setProvider('chatgpt')">ChatGPT</button>
            <button class="mode-btn" data-provider="gemini" onclick="setProvider('gemini')">Gemini</button>
            <button class="mode-btn" data-provider="azure" onclick="setProvider('azure')">Azure OpenAI</button>
            <button class="mode-btn" data-provider="claude" onclick="setProvider('claude')">Claude</button>
            <button class="mode-btn" data-provider="grok" onclick="setProvider('grok')">Grok</button>
            <h3>Persona</h3>
            <div class="persona-grid" id="personaGrid"></div>
            <div class="history-section">
                <h3>Chat History</h3>
                <button class="new-chat-btn" onclick="newConversation()">+ New Chat</button>
                <div class="history-list" id="historyList">
                    <div class="history-empty">Loading...</div>
                </div>
            </div>
        </div>
        <div class="main-panel">
            <div class="chat-area" id="chatArea"></div>
            <div class="input-area">
                <div class="persona-selectors hidden" id="personaSelectors">
                    <div><label>FOR</label><select id="personaFor"></select></div>
                    <div><label>AGAINST</label><select id="personaAgainst"></select></div>
                </div>
                <div id="personaMultiSelect" style="display:none; flex-wrap:wrap; gap:6px; margin-bottom:10px; padding:8px; background:#1a1a2e; border:1px solid #2a2a3e; border-radius:10px;">
                    <div style="width:100%; font-size:11px; color:#8888aa; margin-bottom:4px;">Select personas for group discussion (2+):</div>
                    <div id="personaCheckboxes" style="display:flex; flex-wrap:wrap; gap:6px;"></div>
                </div>
                <div class="file-bar" id="fileBar">
                    <span>📎</span>
                    <span id="fileLabel">Drop file(s) or Browse (TXT, PDF, CSV, DOCX...)</span>
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
                <div class="input-row">
                    <input type="text" id="userInput" placeholder="Type your message..." autofocus>
                    <button class="mic-btn" id="micBtn" onclick="toggleMic()" title="Voice Input">🎙️</button>
                    <button class="send-btn" id="sendBtn" onclick="send()">Send</button>
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
                    <button class="output-action-btn" id="vizBtn" onclick="visualize()">📊 Visualize</button>
                    <button class="output-action-btn" onclick="copyOutput()">Copy</button>
                    <button class="output-action-btn" onclick="clearOutput()">Clear</button>
                </div>
            </div>
            <div class="output-area" id="outputArea">
                <div class="doc-empty"><div class="ei">📝</div><p style="font-size:13px;">AI 분석 결과가<br>여기에 문서화됩니다</p></div>
            </div>
        </div>
    </div>
    <script>
        let currentMode='chat', currentProvider='chatgpt', currentPersona='',
            uploadedFileContent='', uploadedFileName='',
            uploadedFiles=[];  // array of {name, content, size, chars}
        const personas = PERSONA_DATA;
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
        function initPersonas() {
            const g=document.getElementById('personaGrid'),
                  f=document.getElementById('personaFor'),
                  a=document.getElementById('personaAgainst');
            g.innerHTML=''; f.innerHTML=''; a.innerHTML='';
            const cb=document.getElementById('personaCheckboxes'); cb.innerHTML='';
            for (const [k,n] of Object.entries(personas)) {
                g.innerHTML += `<div class="persona-chip" data-key="${k}" onclick="togglePersona('${k}')">${n}</div>`;
                f.innerHTML += `<option value="${k}">${n}</option>`;
                a.innerHTML += `<option value="${k}">${n}</option>`;
                cb.innerHTML += `<label style="display:flex;align-items:center;gap:4px;padding:4px 8px;background:#12121a;border:1px solid #2a2a3e;border-radius:6px;font-size:11px;cursor:pointer;"><input type="checkbox" value="${k}" class="persona-cb"> ${n}</label>`;
            }
            const keys=Object.keys(personas);
            if (keys.length>=2) a.value=keys[1];
        }
        function setMode(m) {
            currentMode=m;
            document.querySelectorAll('.mode-btn[data-mode]').forEach(b=>b.classList.remove('active'));
            document.querySelector(`.mode-btn[data-mode="${m}"]`)?.classList.add('active');
            document.getElementById('personaSelectors').classList.toggle('hidden', m!=='persona_debate');
            document.getElementById('personaMultiSelect').style.display = (m==='persona_discuss') ? 'flex' : 'none';
            const ph={chat:'Type your message...',compare:'Ask all AIs...',debate:'Debate topic...',
                       discuss:'Discussion topic...',best:'Question for best answer...',persona_debate:'Persona debate topic...',persona_discuss:'Topic for persona group discussion...'};
            document.getElementById('userInput').placeholder = ph[m] || 'Type...';
        }
        function setProvider(p) {
            currentProvider=p;
            document.querySelectorAll('.mode-btn[data-provider]').forEach(b=>b.classList.remove('active'));
            document.querySelector(`.mode-btn[data-provider="${p}"]`)?.classList.add('active');
        }
        function togglePersona(k) {
            const chips=document.querySelectorAll('.persona-chip');
            if(currentPersona===k){currentPersona='';chips.forEach(c=>c.classList.remove('selected'));}
            else{currentPersona=k;chips.forEach(c=>c.classList.toggle('selected',c.dataset.key===k));}
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
        function copyOutput() {
            navigator.clipboard.writeText(outputArea.innerText).then(() => {
                const b = document.querySelector('.output-action-btn');
                b.textContent = 'Copied!'; setTimeout(() => b.textContent = 'Copy', 1500);
            });
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
                }
            }catch(e){removeLoading(loadId);addMessage('Error',e.message,'error-msg');}
            document.getElementById('sendBtn').disabled=false;input.focus();
        }
        document.getElementById('userInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});

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

        initStatus(); initPersonas(); initHistory();

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
                var html = '';
                (r.folders || []).forEach(function(f) {
                    var cls = wsCurrentFolder === f.id ? 'ws-folder-item active' : 'ws-folder-item';
                    html += '<div class="'+cls+'" onclick="selectFolder(\'' + f.id + '\')"><span>' + (f.icon||'\uD83D\uDCC1') + ' ' + f.name + '</span><button class="ws-close" onclick="event.stopPropagation();deleteFolder(\'' + f.id + '\')" title="Delete">\u00D7</button></div>';
                });
                el.innerHTML = html;
                if (!r.workspace) el.innerHTML = '<div style="color:var(--text2);font-size:12px;">Supabase not configured</div>';
            } catch(e) { console.log('loadFolders err:', e); }
        }

        async function createFolder() {
            var name = prompt('Folder name:');
            if (!name) return;
            var icon = prompt('Folder icon (emoji):', '\uD83D\uDCC1') || '\uD83D\uDCC1';
            await fetch('/api/folders', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:name,icon:icon})});
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
            html += '<button class="ws-btn" onclick="saveCurrentChat()">Save Chat</button>';
            html += '<button class="ws-btn" onclick="saveCurrentSlides()">Save Slides</button>';
            html += '</div>';
            (r.files || []).forEach(function(f) {
                var icon = {note:'\uD83D\uDCDD',conversation:'\uD83D\uDCAC',slides:'\uD83D\uDCCA',file:'\uD83D\uDCC4'}[f.type] || '\uD83D\uDCC4';
                var date = f.updated_at ? new Date(f.updated_at).toLocaleDateString() : '';
                html += '<div class="ws-file-item" onclick="openFile(\'' + f.id + '\',\'' + f.type + '\')">';
                html += '<div class="ws-file-type">' + icon + ' ' + f.type + '  <button class="ws-close" onclick="event.stopPropagation();deleteFile(\'' + f.id + '\')" title="Delete">\u00D7</button></div>';
                html += '<div class="ws-file-name">' + f.name + '</div>';
                html += '<div class="ws-file-date">' + date + '</div></div>';
            });
            el.innerHTML = html;
        }

        async function saveNote() {
            if (!wsCurrentFolder) return;
            var name = prompt('Note title:');
            if (!name) return;
            await fetch('/api/folders/'+wsCurrentFolder+'/files', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({name:name, type:'note', content:''})
            });
            loadFiles(wsCurrentFolder);
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
                    html += '<button class="ws-btn" style="font-size:11px;" onclick="askAiAboutFile(\'' + fileId + '\',\'note\')">\uD83E\uDD16 Ask AI</button>';
                    html += '<button class="ws-btn" style="font-size:11px;" onclick="editNote(\'' + fileId + '\')">Edit</button>';
                    html += '</div>';
                    html += '<div style="white-space:pre-wrap;color:var(--text);font-size:14px;line-height:1.8;background:#12121f;padding:16px;border-radius:12px;">' + (f.content||'(empty)').replace(/</g,'&lt;') + '</div>';
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
            }
        }

        async function editNote(fileId) {
            var r = await fetch('/api/files/'+fileId).then(function(r){return r.json();});
            var f = r.file;
            if (!f) return;
            var newContent = prompt('Edit note: ' + f.name, f.content || '');
            if (newContent !== null) {
                await fetch('/api/files/'+fileId, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({content:newContent})});
                openFile(fileId, 'note');
            }
        }

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
                    input.value = 'I have a presentation about "' + ((f.metadata && f.metadata.topic) || f.name) + '" with slides: ' + summary + '. Please suggest improvements, additional content, and ways to make it more impactful.';
                } catch(e) { input.value = 'Analyze and improve this presentation: ' + content.substring(0, 2000); }
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
    html = MAIN_HTML.replace("AI_STATUS", json.dumps(status)).replace(
        "PERSONA_DATA", json.dumps(personas, ensure_ascii=False))
    return html


@app.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    data = request.json
    prompt = data.get("prompt", "")
    provider = data.get("provider", "chatgpt")
    persona = data.get("persona", "")
    if persona:
        response = hub.ask_as(prompt, persona=persona, provider=provider)
    else:
        response = hub.ask(prompt, provider=provider)
    return jsonify({"provider": response.provider, "model": response.model,
                     "content": response.content, "success": response.success,
                     "error": response.error, "elapsed_seconds": response.elapsed_seconds})


@app.route("/api/compare", methods=["POST"])
@login_required
def api_compare():
    data = request.json
    results = hub.ask_all(data.get("prompt", ""))
    return jsonify({"results": [{"provider": r.provider, "model": r.model,
        "content": r.content, "success": r.success, "error": r.error,
        "elapsed_seconds": r.elapsed_seconds} for r in results]})


@app.route("/api/debate", methods=["POST"])
@login_required
def api_debate():
    topic = request.json.get("topic", "")
    av = hub.available_providers()
    result = hub.debate(topic=topic, rounds=2, ai_for=av[0],
        ai_against=av[1] if len(av) > 1 else av[0],
        judge=av[2] if len(av) >= 3 else av[0])
    return jsonify({"topic": result["topic"], "for_name": result["for"],
        "against_name": result["against"], "judge": result["judge"],
        "debate_log": result["debate_log"], "judgment": result["judgment"]})


@app.route("/api/discuss", methods=["POST"])
@login_required
def api_discuss():
    topic = request.json.get("topic", "")
    result = hub.discuss(topic=topic, rounds=2)
    return jsonify({"topic": result["topic"], "participants": result["participants"],
        "discussion_log": result["discussion_log"], "summary": result["summary"]})


@app.route("/api/best", methods=["POST"])
@login_required
def api_best():
    question = request.json.get("question", "")
    result = hub.find_best(question=question)
    return jsonify({"question": result["question"],
        "answers": [{"provider": r.provider, "model": r.model, "content": r.content,
            "success": r.success, "error": r.error, "elapsed_seconds": r.elapsed_seconds}
            for r in result["answers"]],
        "evaluations": result["evaluations"], "votes": result["votes"], "winner": result["winner"]})


@app.route("/api/persona_debate", methods=["POST"])
@login_required
def api_persona_debate():
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


@app.route("/api/persona_discuss", methods=["POST"])
@login_required
def api_persona_discuss():
    data = request.json
    result = hub.persona_discuss(topic=data.get("topic", ""),
        persona_keys=data.get("personas", []), rounds=2)
    if "error" in result:
        return jsonify({"error": result["error"]}), 400
    return jsonify({"topic": result["topic"], "participants": result["participants"],
        "discussion_log": result["discussion_log"], "synthesis": result["synthesis"]})


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
            "user_id", session.get("user", "admin")
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
            "user_id": session.get("user", "admin"),
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
            "user_id": session.get("user", "admin"),
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
    port = int(os.getenv("PORT", 5000))
    print(f"\n  AI Hub Web App")
    print(f"  http://localhost:{port}")
    print(f"  Login: {APP_USERNAME} / {APP_PASSWORD}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
