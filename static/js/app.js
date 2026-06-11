// ── STATE VARIABLES ───────────────────────────────────────────────────────────
let apiBase = "https://api.athena.nexushestia.com"; // Defaults to Railway backend
// Auto-detect local development
if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    apiBase = window.location.origin;
}
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('local') === 'true') {
    apiBase = window.location.origin;
}
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

function getSessionId() {
    let sid = localStorage.getItem("athena_session_id");
    if (!sid) {
        sid = "session_" + Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
        localStorage.setItem("athena_session_id", sid);
    }
    return sid;
}

// ── DOM LOAD INITIALIZATION ───────────────────────────────────────────────────
let dashboardStarted = false;
function startDashboard() {
    if (dashboardStarted) return;
    dashboardStarted = true;
    
    // Core loads
    loadBrief();
    loadDrafts();
    loadPriorities();
    loadStates();
    loadGoals(); // Load long-term goals
    loadHorizon(); // Load horizon events
    fetchTelemetryData();
    fetchLogs();
    
    // Polling schedules
    setInterval(fetchTelemetryData, 4000);
    setInterval(loadDrafts, 5000);
    setInterval(fetchLogs, 5000);
    setInterval(loadStates, 10000); // Poll states every 10s
    setInterval(loadGoals, 30000); // Poll goals every 30s
    setInterval(loadHorizon, 30000); // Poll horizon events every 30s
    setInterval(loadPriorities, 5 * 60 * 1000); // 5 min
}

document.addEventListener("DOMContentLoaded", () => {
    initTimeClocks();
    initWaveformCanvas();
    initAthenaVoice();
    
    // Polling schedules (Non-authenticated)
    setInterval(initTimeClocks, 1000);
    
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
    
    // Wire lock screen Enter key press
    const lockInput = document.getElementById("lock-passcode-input");
    if (lockInput) {
        lockInput.addEventListener("keypress", (e) => {
            if (e.key === 'Enter') submitPasscode();
        });
    }
    
    // Check URL parameters for OAuth status
    const authStatus = urlParams.get('auth');
    const passcodeParam = urlParams.get('passcode');
    const authError = urlParams.get('error');
    
    if (authStatus === 'success' && passcodeParam) {
        unlockConsole(passcodeParam);
        addSimulatedSystemLog("Google Auth", "Access granted via Google Sign-In with preapproved email.");
        // Clean URL parameters
        window.history.replaceState({}, document.title, window.location.pathname);
    } else if (authStatus === 'failed' || authError) {
        showLockScreen();
        const errorEl = document.getElementById("lock-error-msg");
        if (errorEl) {
            if (authError === 'unauthorized_email') {
                errorEl.textContent = "Your Google account is not authorized to access Athena.";
            } else {
                errorEl.textContent = "Google authentication failed: " + (authError || "unknown error");
            }
            errorEl.classList.add("visible");
        }
        addSimulatedSystemLog("Google Auth", `Authentication failed: ${authError || 'unknown'}`);
        // Clean URL parameters
        window.history.replaceState({}, document.title, window.location.pathname);
    } else {
        // Authenticate / Check passcode
        const passcode = localStorage.getItem("athena_passcode");
        if (passcode) {
            verifyPasscodeSilent(passcode);
        } else {
            showLockScreen();
        }
    }
});

// ── AUTHENTICATION & LOCK SCREEN ─────────────────────────────────────────────
async function athenaFetch(url, options = {}) {
    const passcode = localStorage.getItem("athena_passcode");
    options.headers = options.headers || {};
    if (passcode) {
        options.headers["Authorization"] = `Bearer ${passcode}`;
        options.headers["X-Athena-Token"] = passcode;
    }
    
    try {
        const res = await fetch(url, options);
        if (res.status === 401) {
            showLockScreen();
            throw new Error("Unauthorized");
        }
        return res;
    } catch (err) {
        if (err.message === "Unauthorized") {
            throw err;
        }
        throw err;
    }
}

function showLockScreen() {
    const overlay = document.getElementById("athena-lock-screen");
    if (overlay) {
        overlay.classList.add("visible");
    }
    const input = document.getElementById("lock-passcode-input");
    if (input) {
        input.focus();
        input.value = "";
    }
}

function hideLockScreen() {
    const overlay = document.getElementById("athena-lock-screen");
    if (overlay) {
        overlay.classList.remove("visible");
    }
}

async function verifyPasscodeSilent(passcode) {
    try {
        const res = await fetch(`${apiBase}/api/auth/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode })
        });
        if (res.ok) {
            unlockConsole(passcode);
        } else {
            showLockScreen();
        }
    } catch (e) {
        console.error("Verification error", e);
        showLockScreen();
    }
}

function unlockConsole(passcode) {
    localStorage.setItem("athena_passcode", passcode);
    hideLockScreen();
    
    // Sync passcode to Android Client if interface exists
    if (window.AndroidInterface && typeof window.AndroidInterface.savePasscode === "function") {
        try {
            window.AndroidInterface.savePasscode(passcode);
        } catch (e) {
            console.error("Failed to sync passcode to Android", e);
        }
    }
    
    startDashboard();
}

async function submitPasscode() {
    const input = document.getElementById("lock-passcode-input");
    const errorEl = document.getElementById("lock-error-msg");
    const passcode = input.value.trim();
    
    if (!passcode) return;
    
    try {
        const res = await fetch(`${apiBase}/api/auth/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode })
        });
        
        if (res.ok) {
            errorEl.textContent = "";
            errorEl.classList.remove("visible");
            unlockConsole(passcode);
        } else {
            const data = await res.json();
            errorEl.textContent = data.error || "Incorrect passcode";
            errorEl.classList.add("visible");
            // Trigger shake animation
            errorEl.style.animation = 'none';
            errorEl.offsetHeight; /* trigger reflow */
            errorEl.style.animation = null;
        }
    } catch (e) {
        errorEl.textContent = "Connection failed";
        errorEl.classList.add("visible");
    }
}

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
        const res = await athenaFetch(`${apiBase}/api/voice/dictate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: text, session_id: getSessionId() })
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
        const res = await athenaFetch(`${apiBase}/api/comms/drafts`);
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

        <textarea class="draft-textarea" id="textarea-${d.id}" readonly style="cursor: pointer;" onclick="editDraft('${d.id}')">${escapeHtml(d.payload)}</textarea>

        <div class="draft-action-bar" id="actions-${d.id}">
            <span class="broadcast-badge"><i class="fa-solid fa-tower-broadcast"></i> ${d.broadcast_type}</span>
            <div class="btn-group">
                <button class="btn-edit" id="edit-btn-${d.id}" onclick="editDraft('${d.id}')">
                    <i class="fa-solid fa-pen"></i> Edit
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
    const draft = draftsData[id];
    if (!draft) return;
    
    const modal = document.getElementById("edit-draft-modal");
    if (!modal) return;
    
    document.getElementById("edit-draft-id").value = id;
    document.getElementById("modal-draft-channel").textContent = draft.channel;
    document.getElementById("modal-draft-recipient").textContent = draft.recipient;
    document.getElementById("edit-draft-payload").value = draft.payload;
    document.getElementById("edit-draft-rework-instruction").value = "";
    
    modal.style.display = "flex";
    modal.offsetHeight; // Force reflow
    modal.classList.add("visible");
    addSimulatedSystemLog('Comms-Draft-Engine', `Draft for ${draft.recipient} opened in edit modal.`);
}

function closeEditDraftDraftModal() {
    const modal = document.getElementById("edit-draft-modal");
    if (modal) {
        modal.classList.remove("visible");
        setTimeout(() => {
            if (!modal.classList.contains("visible")) {
                modal.style.display = "none";
            }
        }, 500);
    }
}

function closeEditDraftModal() {
    closeEditDraftDraftModal();
}

async function submitDraftSave() {
    const id = document.getElementById("edit-draft-id").value;
    const payload = document.getElementById("edit-draft-payload").value;
    
    if (!id || !payload) return;
    
    const saveBtn = document.getElementById("btn-save-draft-modal");
    const originalText = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...';
    
    try {
        const res = await athenaFetch(`${apiBase}/api/comms/draft/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, payload })
        });
        const data = await res.json();
        if (data.success) {
            if (draftsData[id]) draftsData[id].payload = payload;
            closeEditDraftModal();
            loadDrafts();
            addSimulatedSystemLog('Comms-Draft-Engine', `Draft edits saved and persisted.`);
        } else {
            alert("Failed to save draft: " + (data.error || "unknown error"));
        }
    } catch (e) {
        console.error(e);
        alert("Failed to save draft due to connection error.");
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    }
}

async function submitReworkWithAI() {
    const id = document.getElementById("edit-draft-id").value;
    const instruction = document.getElementById("edit-draft-rework-instruction").value.trim();
    const payload = document.getElementById("edit-draft-payload").value;
    
    if (!id || !instruction) {
        alert("Rework instruction is required.");
        return;
    }
    
    const reworkBtn = document.getElementById("btn-rework-ai");
    const originalText = reworkBtn.innerHTML;
    reworkBtn.disabled = true;
    reworkBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Reworking...';
    
    addSimulatedSystemLog('Athena-Core', `Requesting Claude to rework draft '${id}' with instructions: "${instruction}"`);
    
    try {
        const res = await athenaFetch(`${apiBase}/api/comms/rework`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, instruction, payload })
        });
        const data = await res.json();
        if (data.success && data.draft) {
            document.getElementById("edit-draft-payload").value = data.draft.payload;
            document.getElementById("edit-draft-rework-instruction").value = "";
            addSimulatedSystemLog('Athena-Core', `Draft reworked successfully by Claude.`);
        } else {
            alert("Rework failed: " + (data.error || "unknown error"));
        }
    } catch (e) {
        console.error(e);
        alert("Rework failed due to connection error.");
    } finally {
        reworkBtn.disabled = false;
        reworkBtn.innerHTML = originalText;
    }
}

async function approveDraft(id) {
    const payload = draftsData[id]?.payload;
    try {
        const res = await athenaFetch(`${apiBase}/api/comms/approve`, {
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
        const res = await athenaFetch(`${apiBase}/api/comms/reject`, {
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
        const res = await athenaFetch(`${apiBase}/api/brief`);
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
        const res = await athenaFetch(`${apiBase}/api/priorities`);
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
        const res = await athenaFetch(`${apiBase}/api/brief/feedback`, {
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
        const res = await athenaFetch(`${apiBase}/api/devops/telemetry`);
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
        const res = await athenaFetch(`${apiBase}/api/logs`);
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

async function loadStates() {
    try {
        const res = await athenaFetch(`${apiBase}/api/states`);
        const states = await res.json();
        updateTimelineItem("state-routine", states.routine_block);
        updateTimelineItem("state-target", states.target_block);
        updateTimelineItem("state-anchor", states.anchor_block);
    } catch(e) {
        console.error("Failed to load timeline states", e);
    }
}

// ── TIMELINE STATE MODAL HANDLERS ─────────────────────────────────────────────
async function openStateModal(blockKey) {
    const modal = document.getElementById("state-edit-modal");
    if (!modal) return;
    
    document.getElementById("edit-state-block-key").value = blockKey;
    
    const titleEl = document.getElementById(`${blockKey.replace("_block", "")}-title`);
    const timeEl = document.getElementById(`${blockKey.replace("_block", "")}-time`);
    const statusEl = document.getElementById(`${blockKey.replace("_block", "")}-status`);
    
    document.getElementById("edit-state-title").value = titleEl ? titleEl.textContent : "";
    document.getElementById("edit-state-time").value = timeEl ? timeEl.textContent : "";
    document.getElementById("edit-state-status").value = statusEl ? statusEl.textContent : "";
    
    modal.style.display = "flex";
    modal.offsetHeight; // Force reflow
    modal.classList.add("visible");
}

function closeStateModal() {
    const modal = document.getElementById("state-edit-modal");
    if (modal) {
        modal.classList.remove("visible");
        setTimeout(() => {
            if (!modal.classList.contains("visible")) {
                modal.style.display = "none";
            }
        }, 500);
    }
}

async function submitStateEdit() {
    const block = document.getElementById("edit-state-block-key").value;
    const title = document.getElementById("edit-state-title").value.trim();
    const timeVal = document.getElementById("edit-state-time").value.trim();
    const status = document.getElementById("edit-state-status").value.trim();
    
    if (!block) return;
    
    try {
        const res = await athenaFetch(`${apiBase}/api/states`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ block, title, time: timeVal, status })
        });
        const data = await res.json();
        if (data.success) {
            closeStateModal();
            loadStates();
            addSimulatedSystemLog("State-Engine", `Successfully updated state block '${block}'`);
            fetchLogs();
        } else {
            alert("Error updating block: " + (data.error || "unknown error"));
        }
    } catch(e) {
        console.error(e);
        alert("Failed to connect to backend to update state.");
    }
}

// ── NEW DRAFT MODAL HANDLERS ───────────────────────────────────────────────────
function openNewDraftModal() {
    const modal = document.getElementById("new-draft-modal");
    if (modal) {
        modal.style.display = "flex";
        modal.offsetHeight; // Force reflow
        modal.classList.add("visible");
        document.getElementById("draft-recipient-input").value = "";
        document.getElementById("draft-prompt-input").value = "";
    }
}

function closeNewDraftModal() {
    const modal = document.getElementById("new-draft-modal");
    if (modal) {
        modal.classList.remove("visible");
        setTimeout(() => {
            if (!modal.classList.contains("visible")) {
                modal.style.display = "none";
            }
        }, 500);
    }
}

async function submitNewDraft() {
    const recipient = document.getElementById("draft-recipient-input").value.trim();
    const channel = document.getElementById("draft-channel-input").value;
    const prompt = document.getElementById("draft-prompt-input").value.trim();
    
    if (!recipient || !prompt) {
        alert("Recipient name and prompt instructions are required.");
        return;
    }
    
    const generateBtn = document.querySelector("#new-draft-modal button[onclick='submitNewDraft()']");
    const originalText = generateBtn ? generateBtn.textContent : "Generate Draft";
    if (generateBtn) {
        generateBtn.disabled = true;
        generateBtn.textContent = "Generating...";
    }
    
    try {
        const res = await athenaFetch(`${apiBase}/api/comms/draft/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ recipient, channel, prompt })
        });
        const data = await res.json();
        if (data.success) {
            closeNewDraftModal();
            loadDrafts();
            addSimulatedSystemLog("Comms-Draft-Engine", `Generated new draft for ${recipient}`);
            fetchLogs();
        } else {
            alert("Draft generation failed: " + (data.error || "unknown error"));
        }
    } catch(e) {
        console.error(e);
        alert("Draft generation failed due to connection error.");
    } finally {
        if (generateBtn) {
            generateBtn.disabled = false;
            generateBtn.textContent = originalText;
        }
    }
}

// ── SUBMIT DRAFT APPROVAL DIRECTLY FROM MODAL ─────────────────────────
async function submitDraftApproveFromModal() {
    const id = document.getElementById("edit-draft-id").value;
    const payload = document.getElementById("edit-draft-payload").value;
    
    if (!id || !payload) return;
    
    const approveBtn = document.getElementById("btn-approve-draft-modal");
    const originalText = approveBtn.innerHTML;
    approveBtn.disabled = true;
    approveBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Sending...';
    
    try {
        // Save first
        const saveRes = await athenaFetch(`${apiBase}/api/comms/draft/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, payload })
        });
        const saveData = await saveRes.json();
        if (!saveData.success) {
            alert("Failed to save draft edits: " + (saveData.error || "unknown error"));
            approveBtn.disabled = false;
            approveBtn.innerHTML = originalText;
            return;
        }
        
        // Update local cache
        if (draftsData[id]) draftsData[id].payload = payload;
        
        // Approve and send
        const approveRes = await athenaFetch(`${apiBase}/api/comms/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, payload })
        });
        const approveData = await approveRes.json();
        if (approveData.success) {
            closeEditDraftModal();
            loadDrafts();
            addSimulatedSystemLog('Athena-Core', `HUMAN-IN-THE-LOOP VALIDATED: Sent draft to ${draftsData[id]?.recipient} from edit modal.`);
        } else {
            alert("Approval failed: " + (approveData.error || "unknown error"));
        }
    } catch (e) {
        console.error(e);
        alert("Action failed due to connection error.");
    } finally {
        approveBtn.disabled = false;
        approveBtn.innerHTML = originalText;
    }
}

// ── LONG-TERM GOALS MODULE ──────────────────────────────────────────────────
async function loadGoals() {
    try {
        const res = await athenaFetch(`${apiBase}/api/goals`);
        const goals = await res.json();
        renderGoals(goals);
    } catch(e) {
        console.error("Failed to load goals", e);
        const list = document.getElementById("long-term-goals-list");
        if (list) list.innerHTML = '<div class="loading-placeholder">Goals offline.</div>';
    }
}

function renderGoals(goals) {
    const list = document.getElementById("long-term-goals-list");
    if (!list) return;
    
    if (!goals || goals.length === 0) {
        list.innerHTML = `<div class="loading-placeholder" style="color:var(--text-muted); padding: 10px 0;">No active long-term goals.</div>`;
        return;
    }
    
    list.innerHTML = goals.map(g => {
        let dateStr = g.due_date;
        try {
            const dateObj = new Date(g.due_date + "T00:00:00");
            dateStr = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        } catch(e) {}
        
        return `
            <div class="approval-item" style="border-color: rgba(71, 200, 255, 0.15); margin-bottom: 8px; background: rgba(255,255,255,0.01);">
                <div class="approval-info" style="flex: 1; padding-right: 10px;">
                    <span class="approval-target" style="color: var(--text-primary); font-size: 0.82rem; font-weight: 600;">${escapeHtml(g.title)}</span>
                    <span class="approval-desc" style="color: var(--color-warning); font-size: 0.72rem; font-family: var(--font-mono); margin-top: 2px; display: inline-flex; align-items: center; gap: 4px;"><i class="fa-solid fa-calendar-days"></i> Due: ${dateStr}</span>
                    ${g.description ? `<p style="font-size:0.75rem; color:var(--text-secondary); margin-top:6px; line-height:1.4; border-top: 1px solid rgba(255,255,255,0.03); padding-top:4px;">${escapeHtml(g.description)}</p>` : ''}
                </div>
                <button class="approve-mini-btn" onclick="completeGoal('${g.id}')" style="background:rgba(60,220,120,0.08); border-color:rgba(60,220,120,0.3); color:#3cdc78; padding: 4px 8px; height: fit-content;" title="Mark Goal Completed">
                    <i class="fa-solid fa-check"></i> Done
                </button>
            </div>
        `;
    }).join("");
}

function openNewGoalModal() {
    const modal = document.getElementById("new-goal-modal");
    if (modal) {
        modal.style.display = "flex";
        modal.offsetHeight; // Force reflow
        modal.classList.add("visible");
        document.getElementById("goal-title-input").value = "";
        document.getElementById("goal-date-input").value = "";
        document.getElementById("goal-desc-input").value = "";
    }
}

function closeNewGoalModal() {
    const modal = document.getElementById("new-goal-modal");
    if (modal) {
        modal.classList.remove("visible");
        setTimeout(() => {
            if (!modal.classList.contains("visible")) {
                modal.style.display = "none";
            }
        }, 500);
    }
}

async function submitNewGoal() {
    const title = document.getElementById("goal-title-input").value.trim();
    const dueDate = document.getElementById("goal-date-input").value;
    const description = document.getElementById("goal-desc-input").value.trim();
    
    if (!title || !dueDate) {
        alert("Goal title and due date are required.");
        return;
    }
    
    try {
        const res = await athenaFetch(`${apiBase}/api/goals`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, due_date: dueDate, description })
        });
        const data = await res.json();
        if (data.success) {
            closeNewGoalModal();
            loadGoals();
            addSimulatedSystemLog("Memory-Vault", `Offloaded new long-term goal: "${title}"`);
            fetchLogs();
        } else {
            alert("Failed to save goal: " + (data.error || "unknown error"));
        }
    } catch(e) {
        console.error(e);
        alert("Failed to save goal due to connection error.");
    }
}

async function completeGoal(id) {
    try {
        const res = await athenaFetch(`${apiBase}/api/goals/complete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.success) {
            loadGoals();
            addSimulatedSystemLog("Memory-Vault", `Completed and cleared goal from active registry.`);
            fetchLogs();
        }
    } catch(e) {
        console.error(e);
    }
}

// ── BRIEF ORCHESTRATOR TABS ──────────────────────────────────────────────────
function switchBriefTab(tabName) {
    const timelineTab = document.getElementById("tab-timeline");
    const horizonTab = document.getElementById("tab-horizon");
    const timelineContent = document.getElementById("content-timeline");
    const horizonContent = document.getElementById("content-horizon");
    
    if (!timelineTab || !horizonTab) return;
    
    if (tabName === "timeline") {
        timelineTab.classList.add("active");
        timelineTab.style.color = "#7aaaff";
        horizonTab.classList.remove("active");
        horizonTab.style.color = "var(--text-secondary)";
        
        timelineContent.style.display = "block";
        horizonContent.style.display = "none";
    } else {
        horizonTab.classList.add("active");
        horizonTab.style.color = "var(--color-warning)";
        timelineTab.classList.remove("active");
        timelineTab.style.color = "var(--text-secondary)";
        
        timelineContent.style.display = "none";
        horizonContent.style.display = "block";
        loadHorizon();
    }
}

// ── ON THE HORIZON MODULE ────────────────────────────────────────────────────
async function loadHorizon() {
    try {
        const res = await athenaFetch(`${apiBase}/api/horizon`);
        const events = await res.json();
        renderHorizon(events);
    } catch(e) {
        console.error("Failed to load horizon events", e);
        const list = document.getElementById("horizon-events-list");
        if (list) list.innerHTML = '<div class="loading-placeholder">Horizon events offline.</div>';
    }
}

function renderHorizon(events) {
    const list = document.getElementById("horizon-events-list");
    if (!list) return;
    
    if (!events || events.length === 0) {
        list.innerHTML = `<div class="loading-placeholder" style="color:var(--text-muted); padding: 10px 0;">No upcoming events on the horizon.</div>`;
        return;
    }
    
    list.innerHTML = events.map(e => {
        let dateStr = e.event_date;
        try {
            const dateObj = new Date(e.event_date + "T00:00:00");
            dateStr = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        } catch(ex) {}
        
        return `
            <div class="approval-item" style="border-color: rgba(255, 107, 53, 0.2); margin-bottom: 8px; background: rgba(255,255,255,0.01);">
                <div class="approval-info" style="flex: 1; padding-right: 10px;">
                    <span class="approval-target" style="color: var(--text-primary); font-size: 0.82rem; font-weight: 600;">${escapeHtml(e.title)}</span>
                    <span class="approval-desc" style="color: var(--color-warning); font-size: 0.72rem; font-family: var(--font-mono); margin-top: 2px; display: inline-flex; align-items: center; gap: 4px;"><i class="fa-solid fa-calendar-day"></i> Event Date: ${dateStr}</span>
                    ${e.action_required ? `<p style="font-size:0.75rem; color:var(--text-secondary); margin-top:6px; line-height:1.4; border-top: 1px solid rgba(255,255,255,0.03); padding-top:4px;"><strong>Athena Action:</strong> ${escapeHtml(e.action_required)}</p>` : ''}
                </div>
                <button class="approve-mini-btn" onclick="completeHorizonEvent('${e.id}')" style="background:rgba(60,220,120,0.08); border-color:rgba(60,220,120,0.3); color:#3cdc78; padding: 4px 8px; height: fit-content;" title="Archive Event">
                    <i class="fa-solid fa-check"></i> Clear
                </button>
            </div>
        `;
    }).join("");
}

function openNewHorizonModal() {
    const modal = document.getElementById("new-horizon-modal");
    if (modal) {
        modal.style.display = "flex";
        modal.offsetHeight; // Force reflow
        modal.classList.add("visible");
        document.getElementById("horizon-title-input").value = "";
        document.getElementById("horizon-date-input").value = "";
        document.getElementById("horizon-action-input").value = "";
    }
}

function closeNewHorizonModal() {
    const modal = document.getElementById("new-horizon-modal");
    if (modal) {
        modal.classList.remove("visible");
        setTimeout(() => {
            if (!modal.classList.contains("visible")) {
                modal.style.display = "none";
            }
        }, 500);
    }
}

async function submitNewHorizon() {
    const title = document.getElementById("horizon-title-input").value.trim();
    const eventDate = document.getElementById("horizon-date-input").value;
    const actionRequired = document.getElementById("horizon-action-input").value.trim();
    
    if (!title || !eventDate) {
        alert("Event title and event date are required.");
        return;
    }
    
    try {
        const res = await athenaFetch(`${apiBase}/api/horizon`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, event_date: eventDate, action_required: actionRequired })
        });
        const data = await res.json();
        if (data.success) {
            closeNewHorizonModal();
            loadHorizon();
            addSimulatedSystemLog("Memory-Vault", `Added event on the horizon: "${title}"`);
            fetchLogs();
        } else {
            alert("Failed to save event: " + (data.error || "unknown error"));
        }
    } catch(e) {
        console.error(e);
        alert("Failed to save event due to connection error.");
    }
}

async function completeHorizonEvent(id) {
    try {
        const res = await athenaFetch(`${apiBase}/api/horizon/complete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.success) {
            loadHorizon();
            addSimulatedSystemLog("Memory-Vault", `Cleared horizon event from active monitoring list.`);
            fetchLogs();
        }
    } catch(e) {
        console.error(e);
    }
}
