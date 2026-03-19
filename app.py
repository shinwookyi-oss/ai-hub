"""
AI Hub Web App (Cloud Deployment Version)
==========================================
Includes login authentication for security.

Environment Variables (set in Render Dashboard):
  OPENAI_API_KEY       - ChatGPT API key
  GEMINI_API_KEY       - Gemini API key
  AZURE_OPENAI_API_KEY - Azure OpenAI API key
  AZURE_OPENAI_ENDPOINT - Azure endpoint URL
  APP_USERNAME         - Login username (default: admin)
  APP_PASSWORD         - Login password (default: aihub2026)
  SECRET_KEY           - Flask session secret (auto-generated if not set)
"""

import os
import tempfile
import secrets
from functools import wraps

from flask import Flask, request, jsonify, session, redirect, url_for

from ai_hub import AIHub

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

hub = AIHub()

APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "aihub2026")

UPLOAD_DIR = tempfile.mkdtemp(prefix="aihub_uploads_")


# ──────────────────────────── Authentication ────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.is_json:
                return jsonify({"error": "Login required"}), 401
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
        <p class="subtitle">ChatGPT | Gemini | Azure OpenAI</p>
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
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0a0a0f; --surface: #12121a; --surface2: #1a1a2e;
            --border: #2a2a3e; --text: #e0e0f0; --text2: #8888aa;
            --accent: #6c5ce7; --accent2: #a29bfe; --green: #00d2a0;
            --orange: #fdcb6e; --red: #ff6b6b; --blue: #74b9ff;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
        .header {
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border-bottom: 1px solid var(--border);
            padding: 14px 24px;
            display: flex; align-items: center; justify-content: space-between;
        }
        .header h1 {
            font-size: 20px; font-weight: 700;
            background: linear-gradient(135deg, var(--accent2), var(--blue));
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .header-right { display: flex; gap: 16px; align-items: center; }
        .status-dots { display: flex; gap: 12px; }
        .status-dot { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text2); }
        .status-dot .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px var(--green); }
        .status-dot .dot.off { background: var(--red); box-shadow: 0 0 8px var(--red); }
        .logout-btn {
            padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px;
            background: var(--surface2); color: var(--text2); font-size: 12px;
            text-decoration: none; transition: all 0.2s;
        }
        .logout-btn:hover { border-color: var(--red); color: var(--red); }
        .container { display: grid; grid-template-columns: 250px 1fr; height: calc(100vh - 53px); }
        .sidebar {
            background: var(--surface); border-right: 1px solid var(--border);
            padding: 14px; overflow-y: auto;
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
        .main { display: flex; flex-direction: column; height: 100%; }
        .chat-area { flex: 1; overflow-y: auto; padding: 20px; }
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
    </style>
</head>
<body>
    <div class="header">
        <h1>AI Hub</h1>
        <div class="header-right">
            <div class="status-dots" id="statusDots"></div>
            <a href="/logout" class="logout-btn">Logout</a>
        </div>
    </div>
    <div class="container">
        <div class="sidebar">
            <h3>Mode</h3>
            <button class="mode-btn active" data-mode="chat" onclick="setMode('chat')">💬 Chat</button>
            <button class="mode-btn" data-mode="compare" onclick="setMode('compare')">🔄 Compare All</button>
            <button class="mode-btn" data-mode="debate" onclick="setMode('debate')">⚔️ Debate</button>
            <button class="mode-btn" data-mode="discuss" onclick="setMode('discuss')">🗣️ Discussion</button>
            <button class="mode-btn" data-mode="best" onclick="setMode('best')">🏆 Best Answer</button>
            <button class="mode-btn" data-mode="persona_debate" onclick="setMode('persona_debate')">🎭 Persona Debate</button>
            <h3>Provider</h3>
            <button class="mode-btn active" data-provider="chatgpt" onclick="setProvider('chatgpt')">ChatGPT</button>
            <button class="mode-btn" data-provider="gemini" onclick="setProvider('gemini')">Gemini</button>
            <button class="mode-btn" data-provider="azure" onclick="setProvider('azure')">Azure OpenAI</button>
            <h3>Persona</h3>
            <div class="persona-grid" id="personaGrid"></div>
        </div>
        <div class="main">
            <div class="chat-area" id="chatArea"></div>
            <div class="input-area">
                <div class="persona-selectors hidden" id="personaSelectors">
                    <div><label>FOR</label><select id="personaFor"></select></div>
                    <div><label>AGAINST</label><select id="personaAgainst"></select></div>
                </div>
                <div class="file-bar" id="fileBar">
                    <span>📎</span>
                    <span id="fileLabel">Drop file or Browse (TXT, PDF, CSV, DOCX...)</span>
                    <span class="file-name hidden" id="fileName"></span>
                    <span class="file-size hidden" id="fileSize"></span>
                    <button class="remove-file-btn hidden" id="removeFileBtn" onclick="removeFile()">✕</button>
                    <button class="upload-btn" onclick="document.getElementById('fileInput').click()">Browse</button>
                    <input type="file" id="fileInput" accept=".txt,.pdf,.csv,.md,.json,.py,.js,.html,.css,.xml,.log,.docx,.xlsx" style="display:none">
                </div>
                <div class="input-row">
                    <input type="text" id="userInput" placeholder="Type your message..." autofocus>
                    <button class="send-btn" id="sendBtn" onclick="send()">Send</button>
                </div>
            </div>
        </div>
    </div>
    <script>
        let currentMode='chat', currentProvider='chatgpt', currentPersona='',
            uploadedFileContent='', uploadedFileName='';
        const personas = PERSONA_DATA;
        const chatArea = document.getElementById('chatArea');

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
            for (const [k,n] of Object.entries(personas)) {
                g.innerHTML += `<div class="persona-chip" data-key="${k}" onclick="togglePersona('${k}')">${n}</div>`;
                f.innerHTML += `<option value="${k}">${n}</option>`;
                a.innerHTML += `<option value="${k}">${n}</option>`;
            }
            const keys=Object.keys(personas);
            if (keys.length>=2) a.value=keys[1];
        }
        function setMode(m) {
            currentMode=m;
            document.querySelectorAll('.mode-btn[data-mode]').forEach(b=>b.classList.remove('active'));
            document.querySelector(`.mode-btn[data-mode="${m}"]`)?.classList.add('active');
            document.getElementById('personaSelectors').classList.toggle('hidden', m!=='persona_debate');
            const ph={chat:'Type your message...',compare:'Ask all AIs...',debate:'Debate topic...',
                       discuss:'Discussion topic...',best:'Question for best answer...',persona_debate:'Persona debate topic...'};
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

        // File upload
        const fileInput=document.getElementById('fileInput'), fileBar=document.getElementById('fileBar');
        fileInput.addEventListener('change',async e=>{const f=e.target.files[0];if(f)await uploadFile(f);});
        fileBar.addEventListener('dragover',e=>{e.preventDefault();fileBar.classList.add('dragover');});
        fileBar.addEventListener('dragleave',()=>{fileBar.classList.remove('dragover');});
        fileBar.addEventListener('drop',async e=>{e.preventDefault();fileBar.classList.remove('dragover');if(e.dataTransfer.files[0])await uploadFile(e.dataTransfer.files[0]);});

        async function uploadFile(file) {
            const fd=new FormData(); fd.append('file',file);
            try{
                const r=await fetch('/api/upload',{method:'POST',body:fd}).then(r=>r.json());
                if(r.success){
                    uploadedFileContent=r.content; uploadedFileName=r.filename;
                    const kb=(r.size/1024).toFixed(1);
                    document.getElementById('fileLabel').classList.add('hidden');
                    document.getElementById('fileName').textContent=r.filename;
                    document.getElementById('fileName').classList.remove('hidden');
                    document.getElementById('fileSize').textContent=kb+' KB';
                    document.getElementById('fileSize').classList.remove('hidden');
                    document.getElementById('removeFileBtn').classList.remove('hidden');
                    fileBar.classList.add('has-file');
                    addMessage('System',`File: ${r.filename} (${kb} KB, ${r.char_count.toLocaleString()} chars)`,'system-msg');
                }else{addMessage('Error',r.error,'error-msg');}
            }catch(e){addMessage('Error','Upload failed: '+e.message,'error-msg');}
        }
        function removeFile(){
            uploadedFileContent='';uploadedFileName='';
            document.getElementById('fileLabel').classList.remove('hidden');
            document.getElementById('fileName').classList.add('hidden');
            document.getElementById('fileSize').classList.add('hidden');
            document.getElementById('removeFileBtn').classList.add('hidden');
            fileBar.classList.remove('has-file');fileInput.value='';
        }

        async function send() {
            const input=document.getElementById('userInput'), text=input.value.trim();
            if(!text) return;
            let prompt=text;
            if(uploadedFileContent) prompt=`[File: ${uploadedFileName}]\n\n${uploadedFileContent}\n\n---\nUser question: ${text}`;
            input.value=''; document.getElementById('sendBtn').disabled=true;
            addMessage('You',text,'user-msg');
            const loadId='load-'+Date.now(); addLoading(loadId);
            try {
                let result;
                if(currentMode==='chat'){
                    result=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({prompt,provider:currentProvider,persona:currentPersona})}).then(r=>r.json());
                    removeLoading(loadId);
                    if(result.success) addMessage(result.provider,result.content,'',result.model,result.elapsed_seconds+'s');
                    else addMessage('Error',result.error,'error-msg');
                } else if(currentMode==='compare'){
                    result=await fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({prompt})}).then(r=>r.json());
                    removeLoading(loadId); addCompareCards(result.results);
                } else if(currentMode==='debate'){
                    result=await fetch('/api/debate',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({topic:text})}).then(r=>r.json());
                    removeLoading(loadId);
                    addMessage('System',`DEBATE: ${text}\n${result.for_name} vs ${result.against_name}`,'system-msg');
                    for(const e of result.debate_log) addMessage(`${e.speaker} (${e.side})`,e.content,'',`Round ${e.round}`);
                    addMessage(`Judge (${result.judge})`,result.judgment,'judge-msg','VERDICT');
                } else if(currentMode==='discuss'){
                    result=await fetch('/api/discuss',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({topic:text})}).then(r=>r.json());
                    removeLoading(loadId);
                    addMessage('System',`DISCUSSION: ${text}`,'system-msg');
                    for(const e of result.discussion_log) addMessage(e.speaker,e.content,'',`Round ${e.round}`);
                    addMessage('Summary',result.summary,'judge-msg','CONCLUSION');
                } else if(currentMode==='best'){
                    result=await fetch('/api/best',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({question:text})}).then(r=>r.json());
                    removeLoading(loadId);
                    addMessage('System',`Finding Best: ${text}`,'system-msg');
                    addCompareCards(result.answers);
                    for(const e of result.evaluations) addMessage(`${e.evaluator}`,e.evaluation,'','EVAL');
                    addMessage('Winner',`${result.winner}\nVotes: ${JSON.stringify(result.votes)}`,'judge-msg','WINNER');
                } else if(currentMode==='persona_debate'){
                    const p1=document.getElementById('personaFor').value, p2=document.getElementById('personaAgainst').value;
                    result=await fetch('/api/persona_debate',{method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({topic:text,persona_for:p1,persona_against:p2})}).then(r=>r.json());
                    removeLoading(loadId);
                    addMessage('System',`${result.for_name} vs ${result.against_name}: ${text}`,'system-msg');
                    for(const e of result.debate_log) addMessage(`${e.speaker} (${e.side})`,e.content,'',`Round ${e.round}`);
                    addMessage(`Judge (${result.judge})`,result.judgment,'judge-msg','VERDICT');
                }
            }catch(e){removeLoading(loadId);addMessage('Error',e.message,'error-msg');}
            document.getElementById('sendBtn').disabled=false;input.focus();
        }
        document.getElementById('userInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
        initStatus(); initPersonas();
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
            try:
                import PyPDF2
                with open(filepath, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages: content += page.extract_text() or ""
            except ImportError: content = "[PDF: pip install PyPDF2]"
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n  AI Hub Web App")
    print(f"  http://localhost:{port}")
    print(f"  Login: {APP_USERNAME} / {APP_PASSWORD}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
