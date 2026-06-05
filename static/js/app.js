// State variables
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

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
    initTimeClocks();
    initWaveformCanvas();
    initAthenaVoice();
    fetchBriefData();
    fetchCommsDrafts();
    fetchTelemetryData();
    fetchLogs();
    
    // Set up polling loops
    setInterval(fetchTelemetryData, 4000);
    setInterval(fetchCommsDrafts, 5000);
    setInterval(fetchLogs, 5000);
    setInterval(initTimeClocks, 1000);
    
    // Add Event Listeners
    document.getElementById("mic-btn").addEventListener("click", toggleVoiceRecording);
    document.getElementById("send-dictation-btn").addEventListener("click", submitTextDictation);
    document.getElementById("dictation-input").addEventListener("keypress", (e) => {
        if (e.key === 'Enter') submitTextDictation();
    });
});

// Text-to-Speech (TTS) Female Voice Integration
function initAthenaVoice() {
    if (!('speechSynthesis' in window)) return;
    
    const setVoice = () => {
        const voices = window.speechSynthesis.getVoices();
        // Look for a female voice in English
        // Common female voice names: Microsoft Zira, Google US English (has female quality), Samantha, Karen, Victoria, Hazel, etc.
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
            // fallback to any English voice
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
    // Cancel any ongoing speech
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    if (athenaVoice) {
        utterance.voice = athenaVoice;
    }
    // Adjust pitch and rate to sound more natural and pleasant
    utterance.pitch = 1.05; // slightly higher pitch to emphasize female tone
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
}

// 1. Time Clocks (Local & Belgrade)
function initTimeClocks() {
    const localTimeEl = document.getElementById("local-time");
    const belgradeTimeEl = document.getElementById("belgrade-time");
    
    const now = new Date();
    
    // Local Time
    localTimeEl.textContent = now.toTimeString().split(' ')[0];
    
    // Belgrade Time (+9 hours relative to typical US Pacific time, or calculated via UTC offset)
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

// 2. Waveform Canvas Animation
function initWaveformCanvas() {
    canvas = document.getElementById("waveform-canvas");
    ctx = canvas.getContext("2d");
    
    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
    
    drawWave();
}

function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
}

let phase = 0;
function drawWave() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const waveCount = isRecording ? 4 : 2;
    const colors = isRecording 
        ? ["rgba(255, 0, 85, 0.4)", "rgba(157, 78, 221, 0.3)", "rgba(0, 210, 255, 0.2)", "rgba(255, 158, 0, 0.15)"]
        : ["rgba(0, 210, 255, 0.15)", "rgba(157, 78, 221, 0.1)"];
    
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
            
        const speed = isRecording ? 0.15 : 0.05;
        
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

// 3. Voice Recording Simulation
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
                
                addSimulatedSystemLog("Athena-Core (Voice)", `Mobile audio transcribed: "${phrase}"`);
                speakAthena(`Transcribed input: ${phrase}`);
            }
        }, 2500);
    } else {
        micBtn.classList.remove("active");
        inputField.placeholder = "Type a verbal instruction or command...";
    }
}

function applySuggestion(phrase) {
    document.getElementById("dictation-input").value = phrase;
    addSimulatedSystemLog("Athena-Core (Interface)", `Applied quick input template: "${phrase}"`);
    speakAthena(`Selected query: ${phrase}`);
}

// 4. Submit Dictation / Text Action
async function submitTextDictation() {
    const input = document.getElementById("dictation-input");
    const text = input.value.trim();
    
    if (!text) return;
    
    input.value = "";
    
    addSimulatedSystemLog("User (Voice/Dictation)", text);
    
    try {
        const res = await fetch(`${apiBase}/api/voice/dictate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: text })
        });
        const data = await res.json();
        
        if (data.success) {
            addSimulatedSystemLog("Athena-Core", data.response);
            speakAthena(data.response);
            fetchLogs();
        }
    } catch (e) {
        console.error("Error submitting dictation:", e);
        addSimulatedSystemLog("System", "Failed to communicate with Athena core agent endpoint.");
        speakAthena("Communication failure with Athena core.");
    }
}

// 5. Fetch Daily Brief
async function fetchBriefData() {
    try {
        const res = await fetch(`${apiBase}/api/brief`);
        const data = await res.json();
        
        document.getElementById("brief-text").textContent = data.daily_brief_text;
        
        updateTimelineItem("state-routine", data.states.routine_block);
        updateTimelineItem("state-target", data.states.target_block);
        updateTimelineItem("state-anchor", data.states.anchor_block);
        
    } catch (e) {
        console.error("Error fetching brief:", e);
        document.getElementById("brief-text").textContent = "Error loading Gemini daily brief state.";
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
    if (block.status.includes("Completed") || block.status.includes("Active")) {
        indicator.classList.add("success");
    } else if (block.status.includes("Progress")) {
        indicator.classList.add("warning");
    } else {
        indicator.classList.add("info");
    }
}

// 6. Fetch Communication Drafts
async function fetchCommsDrafts() {
    try {
        const res = await fetch(`${apiBase}/api/comms/drafts`);
        const drafts = await res.json();
        
        renderDrafts(drafts);
        renderApprovalsQueue(drafts);
    } catch (e) {
        console.error("Error fetching drafts:", e);
    }
}

function renderDrafts(drafts) {
    const container = document.getElementById("drafts-container");
    container.innerHTML = "";
    
    drafts.forEach(draft => {
        const card = document.createElement("div");
        card.className = "draft-card";
        
        const isPending = draft.status === "Pending Approval";
        const statusClass = isPending ? "pending" : "sent";
        
        card.innerHTML = `
            <div class="draft-card-header">
                <div>
                    <span class="draft-channel">${draft.channel}</span>
                    <span class="draft-recipient">to ${draft.recipient}</span>
                </div>
                <span class="draft-status ${statusClass}">${draft.status}</span>
            </div>
            
            <div class="draft-payload">${escapeHtml(draft.payload)}</div>
            
            <div class="draft-integration">
                <i class="fa-solid fa-code-merge"></i> Context: ${draft.integration}
            </div>
            
            <div class="draft-action-bar">
                <span class="broadcast-badge"><i class="fa-solid fa-tower-broadcast"></i> ${draft.broadcast_type}</span>
                <button class="approve-full-btn" 
                        onclick="approveDraft('${draft.id}')" 
                        ${isPending ? "" : "disabled"}>
                    ${isPending ? '<i class="fa-solid fa-circle-check"></i> Approve Broadcast' : '<i class="fa-solid fa-check-double"></i> Executed'}
                </button>
            </div>
        `;
        
        container.appendChild(card);
    });
}

function renderApprovalsQueue(drafts) {
    const list = document.getElementById("approvals-list");
    list.innerHTML = "";
    
    const pendingDrafts = drafts.filter(d => d.status === "Pending Approval");
    
    if (pendingDrafts.length === 0) {
        list.innerHTML = `
            <div class="approval-item" style="justify-content: center; border-color: rgba(0, 245, 212, 0.1); background: rgba(0, 245, 212, 0.02)">
                <span class="approval-desc" style="color: var(--color-success)">
                    <i class="fa-solid fa-circle-check"></i> Sovereignty Clear: No pending broadcasts
                </span>
            </div>
        `;
        return;
    }
    
    pendingDrafts.forEach(draft => {
        const item = document.createElement("div");
        item.className = "approval-item";
        
        item.innerHTML = `
            <div class="approval-info">
                <span class="approval-target">${draft.channel} (${draft.recipient})</span>
                <span class="approval-desc">Awaiting Human-in-the-Loop broadcast approval</span>
            </div>
            <button class="approve-mini-btn" onclick="approveDraft('${draft.id}')">
                <i class="fa-solid fa-paper-plane"></i> Send
            </button>
        `;
        
        list.appendChild(item);
    });
}

async function approveDraft(id) {
    try {
        const res = await fetch(`${apiBase}/api/comms/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: id })
        });
        const data = await res.json();
        
        if (data.success) {
            addSimulatedSystemLog("Athena-Core (Sovereignty)", `BROADCAST SUCCESS: Approved draft dispatch for ${id.toUpperCase()}`);
            speakAthena(`Outbound ${id} dispatch broadcast successfully executed.`);
            fetchCommsDrafts();
            fetchLogs();
        }
    } catch (e) {
        console.error("Error executing draft approval:", e);
    }
}

// 7. Telemetry & DevOps Dashboard
async function fetchTelemetryData() {
    try {
        const res = await fetch(`${apiBase}/api/devops/telemetry`);
        const data = await res.json();
        
        document.getElementById("tel-supabase").textContent = data.supabase_connection;
        document.getElementById("tel-latency").textContent = `${data.current_latency_ms}ms`;
        document.getElementById("tel-behavioral").textContent = "STRIPPED";
        
        renderTelemetryChart(data.latency_history);
        
    } catch (e) {
        console.error("Error fetching telemetry:", e);
    }
}

function renderTelemetryChart(latencies) {
    const chart = document.getElementById("latency-chart");
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

// 8. System Logs Console
async function fetchLogs() {
    try {
        const res = await fetch(`${apiBase}/api/logs`);
        const logs = await res.json();
        
        const consoleEl = document.getElementById("console-logs");
        consoleEl.innerHTML = "";
        
        logs.forEach(log => {
            const line = document.createElement("div");
            line.className = "log-line";
            
            let msgClass = "";
            if (log.message.includes("HUMAN-IN-THE-LOOP") || log.message.includes("BROADCAST")) {
                msgClass = "highlight-validated";
            }
            
            line.innerHTML = `
                <span class="log-time">[${log.timestamp.split(' ')[1]}]</span>
                <span class="log-source">[${log.source}]</span>
                <span class="log-msg ${msgClass}">${escapeHtml(log.message)}</span>
            `;
            
            consoleEl.appendChild(line);
        });
        
        consoleEl.scrollTop = consoleEl.scrollHeight;
    } catch (e) {
        console.error("Error fetching logs:", e);
    }
}

function addSimulatedSystemLog(source, msg) {
    const consoleEl = document.getElementById("console-logs");
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    
    const line = document.createElement("div");
    line.className = "log-line";
    
    let msgClass = "";
    if (msg.includes("HUMAN-IN-THE-LOOP") || msg.includes("Transcribed") || msg.includes("DISPATCH")) {
        msgClass = "highlight-validated";
    }
    
    line.innerHTML = `
        <span class="log-time">[${timeStr}]</span>
        <span class="log-source">[${source}]</span>
        <span class="log-msg ${msgClass}">${escapeHtml(msg)}</span>
    `;
    
    consoleEl.appendChild(line);
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
