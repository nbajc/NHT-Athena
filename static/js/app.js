// ── STATE VARIABLES ───────────────────────────────────────────────────────────
let apiBase = window.location.origin;
let isRecording = false;
let canvas, ctx, animationFrameId;
let mockDictationPhrases = [
    "Check status of routine blocks",
    "Approve Nathan Gmail draft response",
    "Validate WhatsApp Belgrade timezone metrics for Denis",
    "Request DE Recertification Workshop status",
    "Confirm Boja's Birthday Walk anchor state"
];
let dictationIndex = 0;
let athenaVoice = null;
let draftsData = {};

// ── DOM LOAD INITIALIZATION ───────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    initTimeClocks();
    initWaveformCanvas();
    initAthenaVoice();
    
    // Core loads
    loadBrief();
    loadDrafts();
    loadPriorities();
    fetchTelemetryData();
    fetchLogs();
    
    // Polling schedules
    setInterval(initTimeClocks, 1000);
    setInterval(fetchTelemetryData, 4000);
    setInterval(loadDrafts, 5000);
    setInterval(fetchLogs, 5000);
    setInterval(loadPriorities, 5 * 60 * 1000); // 5 min
    
    // Event listeners
    document.getElementById("mic-btn").addEventListener("click", toggleVoiceRecording);
    document.getElementById("send-dictation-btn").addEventListener("click", submitTextDictation);
    document.getElementById("dictation-input").addEventListener("keypress", (e) => {
        if (e.key === 'Enter') submitTextDictation();
    });
    
    // Wire Google Auth clickable trigger
    const googleAuthBtn = document.getElementById("google-auth-btn");
    if (googleAuthBtn) {
        googleAuthBtn.addEventListener("click", startGoogleAuth);
        googleAuthBtn.style.cursor = "pointer";
        googleAuthBtn.title = "Click to authenticate Google Account (Calendar & Gmail)";
    }
});

// ── TEXT-TO-SPEECH (TTS) ATHENA VOICE ──────────────────────────────────────────
function initAthenaVoice() {
    if (!('speechSynthesis' in window)) return;
    
    const setVoice = () => {
        const voices = window.speechSynthesis.getVoices();
        athenaVoice = voices.find(v => 
            v.lang.startsWith('en') && 
            (v.name.toLowerCase().includes('female') || 
             v.name.toLowerCase().includes('zira') || 
             v.name.toLowerCase().includes('samantha') || 
             v.name.toLowerCase().includes('karen') || 
             v.name.toLowerCase().includes('victoria') || 
             v.name.toLowerCase().includes('hazel') ||
             v.name.toLowerCase().includes('google us english') ||
             v.name.toLowerCase().includes('natural'))
        );
        if (!athenaVoice) {
            athenaVoice = voices.find(v => v.lang.startsWith('en'));
        }
    };
    
    setVoice();
    if (window.speechSynthesis.onvoiceschanged !== undefined) {
        window.speechSynthesis.onvoiceschanged = setVoice;
    }
}

function speakAthena(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    if (athenaVoice) {
        utterance.voice = athenaVoice;
    }
    utterance.pitch = 1.05;
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
}

// ── TIME CLOCKS (LOCAL & BELGRADE) ────────────────────────────────────────────
function initTimeClocks() {
    const localTimeEl = document.getElementById("local-time");
    const belgradeTimeEl = document.getElementById("belgrade-time");
    if (!localTimeEl || !belgradeTimeEl) return;
    
    const now = new Date();
    
    // Local clock
    localTimeEl.textContent = now.toTimeString().split(' ')[0];
    
    // Belgrade clock (+9 hours or calculated via IANA timeZone)
    try {
        const options = {
            timeZone: 'Europe/Belgrade',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        };
        const formatter = new Intl.DateTimeFormat([], options);
        belgradeTimeEl.textContent = formatter.format(now);
    } catch (e) {
        const belgradeTime = new Date(now.getTime() + (9 * 60 * 60 * 1000));
        belgradeTimeEl.textContent = belgradeTime.toTimeString().split(' ')[0];
    }
}

// ── WAVEFORM CANVAS ANIMATION ──────────────────────────────────────────────────
function initWaveformCanvas() {
    canvas = document.getElementById("waveform-canvas");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    drawWave();
}

function resizeCanvas() {
    if (!canvas) return;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
}

let phase = 0;
function drawWave() {
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const waveCount = isRecording ? 4 : 2;
    const colors = isRecording 
        ? ["rgba(212, 0, 122, 0.4)", "rgba(255, 45, 138, 0.3)", "rgba(71, 200, 255, 0.2)", "rgba(232, 160, 32, 0.15)"]
        : ["rgba(212, 0, 122, 0.15)", "rgba(71, 200, 255, 0.1)"];
    
    for (let i = 0; i < waveCount; i++) {
        ctx.beginPath();
        ctx.lineWidth = i === 0 ? 2 : 1;
        ctx.strokeStyle = colors[i];
        
        const amplitude = isRecording 
            ? (canvas.height * 0.35) * (1 - i * 0.2) 
            : (canvas.height * 0.15) * (1 - i * 0.3);
            
        const frequency = isRecording 
            ? 0.02 + i * 0.005 
            : 0.01 + i * 0.003;
            
        for (let x = 0; x < canvas.width; x++) {
            const y = canvas.height / 2 + Math.sin(x * frequency + phase + i) * amplitude;
            if (x === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
    }
    
    phase += isRecording ? 0.12 : 0.03;
    animationFrameId = requestAnimationFrame(drawWave);
}

// ── VOICE RECORDING SIMULATOR ──────────────────────────────────────────────────
function toggleVoiceRecording() {
    const micBtn = document.getElementById("mic-btn");
    const inputField = document.getElementById("dictation-input");
    
    isRecording = !isRecording;
    
    if (isRecording) {
        micBtn.classList.add("active");
        inputField.placeholder = "Listening...";
        
        setTimeout(() => {
            if (isRecording) {
                const phrase = mockDictationPhrases[dictationIndex];
                dictationIndex = (dictationIndex + 1) % mockDictationPhrases.length;
                inputField.value = phrase;
                toggleVoiceRecording();
                
                addSimulatedSystemLog("Athena-Core (Voice)", `Audio transcribed: "${phrase}"`);
                speakAthena(`Transcribed input: ${phrase}`);
                submitTextDictation();
            }
        }, 2500);
    } else {
        micBtn.classList.remove("active");
        inputField.placeholder = "Ask Athena anything...";
    }
}

function applySuggestion(phrase) {
    document.getElementById("dictation-input").value = phrase;
    addSimulatedSystemLog("Athena-Core (Interface)", `Quick template: "${phrase}"`);
    speakAthena(`Selected query: ${phrase}`);
    submitTextDictation();
}

// ── GOOGLE OAUTH FLOW ──────────────────────────────────────────────────────────
async function startGoogleAuth() {
    addSimulatedSystemLog("Google Auth", "Initiating client handshake...");
    try {
        const res = await fetch(`${apiBase}/api/auth/google`);
        const data = await res.json();
        if (data.success && data.authorization_url) {
            window.location.href = data.authorization_url;
        } else {
            addSimulatedSystemLog("Google Auth", `Authentication failed: ${data.error}`);
        }
    } catch(e) {
        console.error("handshake failed", e);
        addSimulatedSystemLog("Google Auth", "Handshake connection error.");
    }
}

// ── DICTATION → CLAUDE ─────────────────────────────────────────────────────────
async function submitTextDictation() {
    const input = document.getElementById("dictation-input");
    const text = input.value.trim();
    if (!text) return;
    
    input.value = "";
    const box = document.getElementById('athena-response-box');
    const responseText = document.getElementById('athena-response-text');
    
    box.classList.add('visible');
    responseText.textContent = 'Thinking...';
    
    addSimulatedSystemLog("User (Voice/Dictation)", text);
    
    try {
        const res = await fetch(`${apiBase}/api/voice/dictate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: text })
        });
        const data = await res.json();
        if (data.success) {
            responseText.textContent = data.response || 'Processed.';
            speakAthena(data.response);
            fetchLogs();
        } else {
            responseText.textContent = data.error || 'Execution failed.';
        }
    } catch (e) {
        console.error(e);
        responseText.textContent = 'Athena core offline.';
    }
}

// ── DRAFT ENGINE LOGIC (CONSOLIDATED) ──────────────────────────────────────────
async function loadDrafts() {
    try {
        const res = await fetch(`${apiBase}/api/comms/drafts`);
        const drafts = await res.json();
        draftsData = {};
        drafts.forEach(d => { draftsData[d.id] = d; });
        renderDrafts();
        renderApprovalsQueue();
    } catch(e) { console.error('Drafts load failed', e); }
}

function renderDrafts() {
    const container = document.getElementById('drafts-container');
    if (!container) return;
    
    const pending = Object.values(draftsData).filter(d => d.status === 'Pending Approval');
    if (!pending.length) {
        container.innerHTML = '<div class="loading-placeholder">No pending drafts.</div>';
        return;
    }
    container.innerHTML = pending.map(d => buildDraftCard(d)).join('');
}

function buildDraftCard(d) {
    return `
    <div class="draft-card" id="draft-card-${d.id}">
        <div class="draft-card-header">
            <div>
                <span class="draft-channel">${d.channel}</span>
                <span class="draft-recipient">to ${d.recipient}</span>
            </div>
            <span class="draft-status pending" id="draft-status-${d.id}">PENDING APPROVAL</span>
        </div>

        <textarea class="draft-textarea" id="textarea-${d.id}" readonly>${escapeHtml(d.payload)}</textarea>

        <div class="draft-action-bar" id="actions-${d.id}">
            <span class="broadcast-badge"><i class="fa-solid fa-tower-broadcast"></i> ${d.broadcast_type}</span>
            <div class="btn-group">
                <button class="btn-edit" id="edit-btn-${d.id}" onclick="editDraft('${d.id}')">
                    <i class="fa-solid fa-pen"></i> Edit
                </button>
                <button class="btn-save" id="save-btn-${d.id}" style="display:none;" onclick="saveDraft('${d.id}')">
                    <i class="fa-solid fa-floppy-disk"></i> Save
                </button>
                <button class="reject-btn" onclick="rejectDraft('${d.id}')">
                    <i class="fa-solid fa-ban"></i> Reject
                </button>
                <button class="approve-full-btn" onclick="approveDraft('${d.id}')">
                    <i class="fa-solid fa-circle-check"></i> Approve & Send
                </button>
            </div>
        </div>

        <div class="repeat-prompt" id="repeat-prompt-${d.id}" style="display:none; margin-top:10px; padding:10px; border:1px solid rgba(255,100,100,0.3); border-radius:6px; background:rgba(255,100,100,0.05); justify-content:space-between; align-items:center;">
            <span style="font-size:0.75rem; color:#ff6b6b;"><i class="fa-solid fa-clock"></i> Draft rejected. Queue this to repeat tomorrow?</span>
            <div>
                <button style="background:rgba(255,100,100,0.2); border:1px solid #ff5050; color:#ff5050; padding:4px 8px; border-radius:4px; font-size:0.7rem; cursor:pointer;" onclick="repeatTomorrow('${d.id}', true)">YES, TOMORROW</button>
                <button style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.2); color:#fff; padding:4px 8px; border-radius:4px; font-size:0.7rem; cursor:pointer; margin-left:6px;" onclick="repeatTomorrow('${d.id}', false)">NO, DISMISS</button>
            </div>
        </div>
    </div>`;
}

function editDraft(id) {
    const ta = document.getElementById(`textarea-${id}`);
    const editBtn = document.getElementById(`edit-btn-${id}`);
    const saveBtn = document.getElementById(`save-btn-${id}`);
    if (!ta) return;
    
    ta.removeAttribute('readonly');
    ta.focus();
    editBtn.style.display = 'none';
    saveBtn.style.display = 'inline-block';
    addSimulatedSystemLog('Comms-Draft-Engine', `Draft for ${draftsData[id]?.recipient} opened for editing.`);
}

function saveDraft(id) {
    const ta = document.getElementById(`textarea-${id}`);
    const editBtn = document.getElementById(`edit-btn-${id}`);
    const saveBtn = document.getElementById(`save-btn-${id}`);
    if (!ta) return;
    
    ta.setAttribute('readonly', true);
    editBtn.style.display = 'inline-block';
    saveBtn.style.display = 'none';
    if (draftsData[id]) draftsData[id].payload = ta.value;
    addSimulatedSystemLog('Comms-Draft-Engine', `Draft edits locally staged.`);
}

async function approveDraft(id) {
    saveDraft(id);
    const payload = draftsData[id]?.payload;
    try {
        const res = await fetch(`${apiBase}/api/comms/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, payload })
        });
        const data = await res.json();
        if (data.success) {
            const card = document.getElementById(`draft-card-${id}`);
            document.getElementById(`draft-status-${id}`).className = 'draft-status sent';
            document.getElementById(`draft-status-${id}`).textContent = 'EXECUTED / SENT';
            document.getElementById(`actions-${id}`).innerHTML = 
                '<span style="font-size:0.75rem;color:#47C8FF"><i class="fa-solid fa-circle-check"></i> Transmitted successfully via gateway.</span>';
            addSimulatedSystemLog('Athena-Core', `HUMAN-IN-THE-LOOP VALIDATED: Sent draft to ${draftsData[id]?.recipient}.`);
            setTimeout(() => { card.remove(); loadDrafts(); }, 2000);
        }
    } catch(e) { console.error('Approve failed', e); }
}

function rejectDraft(id) {
    const card = document.getElementById(`draft-card-${id}`);
    document.getElementById(`draft-status-${id}`).className = 'draft-status rejected';
    document.getElementById(`draft-status-${id}`).textContent = 'REJECTED';
    document.getElementById(`actions-${id}`).style.display = 'none';
    document.getElementById(`repeat-prompt-${id}`).style.display = 'flex';
    addSimulatedSystemLog('Comms-Draft-Engine', `Draft for ${draftsData[id]?.recipient} rejected. Awaiting repeat decision.`);
}

async function repeatTomorrow(id, repeat) {
    try {
        const res = await fetch(`${apiBase}/api/comms/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, repeat_tomorrow: repeat })
        });
        const data = await res.json();
        if (data.success) {
            const promptBox = document.getElementById(`repeat-prompt-${id}`);
            if (repeat) {
                promptBox.innerHTML = '<span style="font-size:0.75rem; color:#FF6B35;"><i class="fa-solid fa-check"></i> Scheduled for tomorrow morning.</span>';
                addSimulatedSystemLog('Comms-Draft-Engine', `Draft for ${draftsData[id]?.recipient} scheduled for tomorrow.`);
            } else {
                promptBox.innerHTML = '<span style="font-size:0.75rem; color:#aaa;"><i class="fa-solid fa-trash"></i> Draft permanently dismissed.</span>';
                addSimulatedSystemLog('Comms-Draft-Engine', `Draft dismissed.`);
            }
            setTimeout(() => {
                document.getElementById(`draft-card-${id}`).remove();
                loadDrafts();
            }, 2000);
        }
    } catch(e) { console.error(e); }
}

function renderApprovalsQueue() {
    const list = document.getElementById("approvals-list");
    if (!list) return;
    
    const pending = Object.values(draftsData).filter(d => d.status === 'Pending Approval');
    if (pending.length === 0) {
        list.innerHTML = `
            <div class="approval-item" style="justify-content: center; border-color: rgba(71, 200, 255, 0.1); background: rgba(71, 200, 255, 0.02)">
                <span class="approval-desc" style="color: var(--color-success)">
                    <i class="fa-solid fa-circle-check"></i> Sovereignty Clear: No pending broadcasts
                </span>
            </div>
        `;
        return;
    }
    
    list.innerHTML = pending.map(draft => `
        <div class="approval-item">
            <div class="approval-info">
                <span class="approval-target">${draft.channel} (${draft.recipient})</span>
                <span class="approval-desc">Awaiting validation</span>
            </div>
            <button class="approve-mini-btn" onclick="approveDraft('${draft.id}')">
                <i class="fa-solid fa-paper-plane"></i> Send
            </button>
        </div>
    `).join('');
}

// ── BRIEF SYNOPSIS LOAD ────────────────────────────────────────────────────────
async function loadBrief() {
    try {
        const res = await fetch(`${apiBase}/api/brief`);
        const data = await res.json();
        
        // Render syntheses
        const briefText = document.getElementById("brief-text");
        if (briefText) {
            briefText.innerHTML = data.athena_synthesis 
                ? escapeHtml(data.athena_synthesis).replace(/\n/g, '<br>')
                : escapeHtml(data.gemini_brief).replace(/\n/g, '<br>');
        }
        
        updateTimelineItem("state-routine", data.states.routine_block);
        updateTimelineItem("state-target", data.states.target_block);
        updateTimelineItem("state-anchor", data.states.anchor_block);
        
    } catch(e) {
        console.error(e);
        document.getElementById("brief-text").textContent = "Error loading brief.";
    }
}

function updateTimelineItem(id, block) {
    const el = document.getElementById(id);
    if (!el || !block) return;
    
    el.querySelector(".title").textContent = block.title;
    el.querySelector(".time-pill").textContent = block.time;
    
    const indicator = el.querySelector(".status-indicator");
    indicator.textContent = block.status;
    
    indicator.className = "status-indicator";
    if (block.status.includes("Completed") || block.status.includes("Active") || block.status.includes("commitment")) {
        indicator.classList.add("success");
    } else if (block.status.includes("Progress") || block.status.includes("drafted")) {
        indicator.classList.add("warning");
    } else {
        indicator.classList.add("info");
    }
}

// ── PRIORITIES ENGINE LOAD ──────────────────────────────────────────────────────
async function loadPriorities() {
    try {
        const res = await fetch(`${apiBase}/api/priorities`);
        const data = await res.json();
        const list = document.getElementById('priorities-list');
        if (!list) return;
        
        if (data.priorities && data.priorities.length) {
            list.innerHTML = data.priorities.map((p, i) => `
                <div class="priority-item ${p.urgent ? 'priority-urgent' : ''}">
                    <span class="priority-num">${i+1}.</span>
                    <span>${escapeHtml(p.text)}</span>
                    ${p.urgent ? '<i class="fa-solid fa-triangle-exclamation" style="color:#ff9060;margin-left:auto;flex-shrink:0"></i>' : ''}
                </div>`).join('');
        } else {
            list.innerHTML = '<div class="loading-placeholder">No priorities coordinated.</div>';
        }
    } catch(e) {
        console.error(e);
        document.getElementById('priorities-list').innerHTML = '<div class="loading-placeholder">Priorities offline.</div>';
    }
}

// ── FEEDBACK LOOP ─────────────────────────────────────────────────────────────
async function submitFeedback() {
    const input = document.getElementById('feedback-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    
    try {
        const res = await fetch(`${apiBase}/api/brief/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feedback: text })
        });
        const data = await res.json();
        if (data.success) {
            input.value = '';
            const feedbackSent = document.getElementById('feedback-sent');
            feedbackSent.style.display = 'block';
            addSimulatedSystemLog('Brief-Orchestrator', `Feedback submitted: "${text.slice(0,50)}..."`);
            setTimeout(() => { feedbackSent.style.display = 'none'; }, 4000);
        }
    } catch(e) { console.error('Feedback failed', e); }
}

// ── TELEMETRY & SYSTEM LOGS ────────────────────────────────────────────────────
async function fetchTelemetryData() {
    try {
        const res = await fetch(`${apiBase}/api/devops/telemetry`);
        const data = await res.json();
        
        const dbStatus = document.getElementById("tel-supabase");
        const latencyVal = document.getElementById("tel-latency");
        if (dbStatus) dbStatus.textContent = data.supabase_connection;
        if (latencyVal) latencyVal.textContent = `${data.current_latency_ms}ms`;
        
        renderTelemetryChart(data.latency_history);
        
        // Update connection icon active/inactive in env-config-panel
        const gCheck = document.querySelector("#google-auth-btn .key-val i");
        if (gCheck) {
            if (data.gmail_gateway === "READY") {
                gCheck.className = "fa-solid fa-check icon-green";
            } else {
                gCheck.className = "fa-solid fa-triangle-exclamation icon-yellow";
            }
        }
    } catch (e) {
        console.error("Telemetry query failed:", e);
    }
}

function renderTelemetryChart(latencies) {
    const chart = document.getElementById("latency-chart");
    if (!chart) return;
    chart.innerHTML = "";
    
    const maxVal = Math.max(...latencies, 20);
    
    latencies.forEach((latency, index) => {
        const pctHeight = (latency / maxVal) * 80;
        const isLast = index === latencies.length - 1;
        
        const bar = document.createElement("div");
        bar.className = `chart-bar ${isLast ? "active" : ""}`;
        bar.style.height = `${pctHeight}%`;
        bar.innerHTML = `<span>${latency}ms</span>`;
        
        chart.appendChild(bar);
    });
}

async function fetchLogs() {
    try {
        const res = await fetch(`${apiBase}/api/logs`);
        const logs = await res.json();
        const consoleEl = document.getElementById("console-logs");
        if (!consoleEl) return;
        
        consoleEl.innerHTML = "";
        
        logs.forEach(log => {
            const line = document.createElement("div");
            line.className = "log-line";
            
            let msgClass = "";
            if (log.message.includes("HUMAN-IN-THE-LOOP") || log.message.includes("BROADCAST")) {
                msgClass = "highlight-validated";
            } else if (log.message.includes("REJECTED") || log.message.includes("DISMISSED")) {
                msgClass = "highlight-rejected";
            }
            
            line.innerHTML = `
                <span class="log-time">[${log.timestamp.split(' ')[1] || log.timestamp}]</span>
                <span class="log-source">[${log.source}]</span>
                <span class="log-msg ${msgClass}">${escapeHtml(log.message)}</span>
            `;
            
            consoleEl.appendChild(line);
        });
        
        consoleEl.scrollTop = consoleEl.scrollHeight;
    } catch (e) {
        console.error("Logs error:", e);
    }
}

function addSimulatedSystemLog(source, msg) {
    const consoleEl = document.getElementById("console-logs");
    if (!consoleEl) return;
    
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    
    const line = document.createElement("div");
    line.className = "log-line";
    
    let msgClass = "";
    if (msg.includes("HUMAN-IN-THE-LOOP") || msg.includes("Transcribed") || msg.includes("SUCCESS")) {
        msgClass = "highlight-validated";
    } else if (msg.includes("REJECTED") || msg.includes("DISMISSED")) {
        msgClass = "highlight-rejected";
    }
    
    line.innerHTML = `
        <span class="log-time">[${timeStr}]</span>
        <span class="log-source">[${source}]</span>
        <span class="log-msg ${msgClass}">${escapeHtml(msg)}</span>
    `;
    
    consoleEl.appendChild(line);
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

// ── UTILS ──────────────────────────────────────────────────────────────────────
function escapeHtml(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
