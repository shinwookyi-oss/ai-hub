Reveal.initialize({hash:true,transition:"slide"});<\/script></body></html>';
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