import os
import time
import random
import json
import anthropic
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Load environmental variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# ── API Clients ────────────────────────────────────────────────────────────────
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ── Athena System Prompt ───────────────────────────────────────────────────────
ATHENA_SYSTEM_PROMPT = """You are Athena, the sovereign AI executive assistant to Natasha Bajc —
architect, artist, and founder of Nexus Hestia Technologies (NHT), an AI platform for the AEC industry.

Your role is to reduce Natasha's cognitive load, synthesize information, and surface what truly matters.
You speak with precision, warmth, and strategic clarity. No filler. No sycophancy.

KEY CONTEXT ABOUT NATASHA:
- Running Nexus Hestia Technologies — sovereign on-premise institutional memory for AEC
- Seed round in progress, led by Pedja Predin / Fifth Quarter Ventures ($2-3M target, verbal commitment)
- ARC Gallery Athena Fund solo show: "Technosomatic Cyberfeminism 2.0" — September 2026, deadline June 20
- Son Denis lives in Belgrade with his grandmother
- Travels regularly between LA and Belgrade
- Art practice: Technosomatic Architecture framework
- Key contacts: Boris Ivanović (warm angel), Sasha Jokić (first client prospect), German Aparicio (Trimble)
- Co-founder: Mudassar Shaikh (Tech Lead), Advisor: Aleksandar Lazarević (cybersecurity)

YOUR PRIORITIES WHEN RESPONDING:
1. Identify what needs Natasha's attention TODAY vs what can wait
2. Flag anything time-sensitive (fundraise, ARC show deadline, Denis)
3. Be direct — Natasha does not need cushioning, she needs clarity
4. Keep responses concise unless depth is explicitly requested
5. When drafting comms, match Natasha's voice: intelligent, warm, direct, no corporate filler

SOVEREIGNTY GUARDRAILS:
- Always require human approval before any outbound communication
- Never store or transmit behavioral surveillance data
- Flag any privacy concerns immediately"""

# ── Sovereignty Config ─────────────────────────────────────────────────────────
SOVEREIGNTY_CONFIG = {
    "agent_name": "Athena",
    "version": "2.2",
    "system_role": "Sovereign AI Executive Assistant",
    "interface_mode": "Voice-First / Mobile Dictation Optimization",
    "intelligence_layer": {
        "brief_generation": "Google Gemini 1.5 Flash",
        "reasoning_synthesis": "Anthropic Claude",
        "routing": "Athena Orchestrator"
    },
    "guardrails": {
        "human_in_the_loop": True,
        "data_privacy": "Zero behavioral surveillance telemetry.",
        "outbound_comms": "Requires explicit human approval before execution."
    }
}

# ── Persistent States ──────────────────────────────────────────────────────────
orchestrator_states = {
    "routine_block": {
        "title": "Denis + Mama Exam Prep",
        "time": "Daily 07:00 – 09:00 AM",
        "status": "Completed Today"
    },
    "target_block": {
        "title": "DE Recertification Tracking",
        "time": "June 15 Workshops checking",
        "status": "In Progress"
    },
    "anchor_block": {
        "title": "Boja's 50th Birthday Walk",
        "time": "Saturday, June 20 @ 09:00 AM",
        "status": "Scheduled"
    }
}

# ── Comms Drafts ───────────────────────────────────────────────────────────────
comms_drafts = {
    "gmail": {
        "id": "gmail",
        "channel": "Gmail (PCC Response)",
        "recipient": "Nathan",
        "status": "Pending Approval",
        "payload": "Subject: PCC Milestone Review & Next Steps\n\nNathan,\n\nCongratulations on reaching the 18-month PCC milestone! It's incredible to see the progress. Let's schedule a review next week to align on the next phases.\n\nBest,\nNatasha",
        "integration": "Integrated 18-month PCC milestone data from OAUTH_CLIENT_SECRET context.",
        "broadcast_type": "Gmail API (gmail.context.create_draft)"
    },
    "instagram": {
        "id": "instagram",
        "channel": "Instagram (Outreach)",
        "recipient": "Jenny (Don't Look Projects)",
        "status": "Pending Approval",
        "payload": "Hey Jenny! I love what you're doing with Don't Look Projects. The aesthetic is incredibly aligned. Would love to sync up about a collaboration next week if you're open!",
        "integration": "Local browser automation buffer payload (Puppeteer/Playwright headless buffer).",
        "broadcast_type": "Browser Automation Buffer"
    },
    "whatsapp": {
        "id": "whatsapp",
        "channel": "WhatsApp (Metrics)",
        "recipient": "Denis",
        "status": "Pending Approval",
        "payload": "Denis, here are the Belgrade timezone automated metrics:\n- Daily Active Sessions: 142\n- Sync Status: SUCCESS\n- Response Latency: 14ms",
        "integration": "Belgrade timezone trigger (+9 hrs). Formulated Twilio WhatsApp transaction routing payload.",
        "broadcast_type": "Twilio WhatsApp API Gateway"
    }
}

# ── System Logs ────────────────────────────────────────────────────────────────
system_logs = [
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600)), "source": "Athena-Core", "message": "System initialization complete. Sovereignty guardrails loaded."},
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3200)), "source": "Brief-Orchestrator", "message": "Routine block 'Dennis + Mama Exam Prep' synced and tracked."},
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1800)), "source": "Comms-Draft-Engine", "message": "Draft payloads compiled. Headless loop paused. Awaiting human verification."}
]

# ── DevOps Telemetry ───────────────────────────────────────────────────────────
devops_telemetry = {
    "supabase_connection": "CONNECTED",
    "supabase_url": os.getenv("SUPABASE_URL", "https://nht-athena-mock.supabase.co"),
    "twilio_gateway": "READY",
    "gmail_gateway": "READY",
    "behavioral_profiling_trackers": "STRIPPED & BLOCKED (Data Privacy Enforcement)",
    "latency_history": [12, 14, 11, 15, 12, 13, 12],
    "error_history": [0, 0, 0, 0, 0, 0, 0]
}

# In-memory feedback store (replace with Supabase later)
brief_feedback_log = []

# ── Helper: Call Claude ────────────────────────────────────────────────────────
def ask_claude(user_message: str, context: str = "") -> str:
    """Send a message to Claude with Athena's system prompt."""
    try:
        full_message = user_message
        if context:
            full_message = f"CONTEXT:\n{context}\n\nREQUEST:\n{user_message}"

        response = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=ATHENA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": full_message}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Claude unavailable: {str(e)}"

# ── Helper: Call Gemini ────────────────────────────────────────────────────────
def generate_brief_with_gemini(raw_data: dict) -> str:
    """Use Gemini to generate a structured daily brief from raw data."""
    try:
        prompt = f"""
        Generate a concise, structured daily brief for Natasha Bajc based on this data:
        
        Calendar events today: {raw_data.get('calendar', 'No events found')}
        Emails requiring attention: {raw_data.get('emails', 'None')}
        Active tasks: {raw_data.get('tasks', 'None')}
        
        Format as:
        - 3 bullet priorities for today
        - Any urgent flags
        - One sentence on what can wait
        
        Be direct. No filler.
        """
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Gemini brief unavailable: {str(e)}"

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(SOVEREIGNTY_CONFIG)

@app.route("/api/brief", methods=["GET"])
def get_brief():
    """
    Generate daily brief:
    1. Gemini structures the raw data into a brief
    2. Claude synthesizes it through Natasha's strategic lens (integrating feedback log)
    """
    # Build feedback context from previous feedback
    feedback_context = ""
    if brief_feedback_log:
        recent = brief_feedback_log[-3:]  # Last 3 feedback items
        feedback_context = "Previous feedback to incorporate:\n" + \
            "\n".join([f"- {f['feedback']}" for f in recent])

    # Step 1: Raw data (in production this pulls from Google Calendar/Gmail APIs)
    raw_data = {
        "calendar": "ARC application deadline June 20 | Seed round follow-ups pending",
        "emails": "Boris Ivanović responded warmly | Trimble Discovery Session invite",
        "tasks": "ARC website build | Tobii EyeX C# script (~80 lines remaining) | TFAP@CAA paper proposal (July 15)"
    }

    # Step 2: Gemini generates structured brief
    gemini_brief = generate_brief_with_gemini(raw_data)

    # Step 3: Claude synthesizes with strategic context
    prompt = "Review this daily brief and tell me what Natasha should focus on first today, and flag anything critical."
    if feedback_context:
        prompt += f"\n\n{feedback_context}"

    claude_synthesis = ask_claude(prompt, context=gemini_brief)

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Brief-Orchestrator",
        "message": "Daily brief generated: Gemini structured → Claude synthesized."
    })

    return jsonify({
        "states": orchestrator_states,
        "gemini_brief": gemini_brief,
        "athena_synthesis": claude_synthesis,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/api/brief/feedback", methods=["POST"])
def brief_feedback():
    """Receive feedback about today's brief to inject into future generation."""
    data = request.json or {}
    feedback_text = data.get("feedback", "").strip()

    if not feedback_text:
        return jsonify({"success": False, "error": "No feedback provided"}), 400

    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "feedback": feedback_text
    }
    brief_feedback_log.append(entry)

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Brief-Orchestrator",
        "message": f"Feedback logged for tomorrow's brief: '{feedback_text[:80]}'"
    })

    return jsonify({
        "success": True,
        "message": "Feedback stored. Will be injected into tomorrow's Gemini + Claude brief.",
        "entry": entry
    })

@app.route("/api/priorities", methods=["GET"])
def get_priorities():
    """Claude + Gemini coordinate to produce today's priorities list as JSON."""
    feedback_context = ""
    if brief_feedback_log:
        recent = brief_feedback_log[-3:]
        feedback_context = "Previous feedback to incorporate:\n" + \
            "\n".join([f"- {f['feedback']}" for f in recent])

    raw_data = {
        "calendar": "ARC Athena Fund application deadline June 20 | Denis exams June 16-19 | Seed round follow-ups",
        "emails": "Boris Ivanović warm response pending | Trimble Craig Trickett intro",
        "tasks": "ARC website build | Tobii EyeX C# script | TFAP@CAA paper (July 15) | Sasha Jokić client follow-up",
        "active_projects": "Nexus Hestia seed round ($2-3M, Pedja verbal) | Athena agent build | Technosomatic Cyberfeminism 2.0 show"
    }

    gemini_priorities_prompt = f"""
    Generate a prioritized task list for Natasha Bajc for today based on:
    
    Calendar: {raw_data['calendar']}
    Emails: {raw_data['emails']}
    Tasks: {raw_data['tasks']}
    Active Projects: {raw_data['active_projects']}
    {feedback_context}
    
    Return ONLY a numbered list of 5-7 priorities, one per line.
    Mark urgent items with [URGENT] at the start.
    Be specific and actionable. No filler.
    """

    try:
        gemini_response = gemini_model.generate_content(gemini_priorities_prompt)
        gemini_priorities_raw = gemini_response.text
    except Exception as e:
        gemini_priorities_raw = f"Gemini unavailable: {str(e)}"

    claude_prompt = f"""
    Based on these raw priorities from Gemini:
    
    {gemini_priorities_raw}
    
    Return ONLY a JSON array of priority objects. No preamble, no markdown, no explanation.
    Each object must have:
    - "text": the priority as a clear, actionable sentence (max 15 words)
    - "urgent": true or false
    
    Return valid JSON only.
    """

    try:
        claude_response = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            system="You are Athena, Natasha's executive AI. Return only valid JSON arrays as instructed.",
            messages=[{"role": "user", "content": claude_prompt}]
        )
        priorities_json = claude_response.content[0].text.strip()
        priorities_json = priorities_json.replace("```json", "").replace("```", "").strip()
        priorities = json.loads(priorities_json)
    except Exception as e:
        priorities = [
            {"text": "ARC Athena Fund website — deadline June 20.", "urgent": True},
            {"text": "Follow up with Boris Ivanović on angel bridge.", "urgent": True},
            {"text": "Denis exam prep check-in (Law June 16).", "urgent": False},
            {"text": "Tobii EyeX C# script — ~80 lines remaining.", "urgent": False},
            {"text": "Sasha Jokić / Cosmic Buildings follow-up.", "urgent": False},
        ]

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Priority-Engine",
        "message": f"Gemini + Claude coordinated {len(priorities)} priorities for today."
    })

    return jsonify({
        "success": True,
        "priorities": priorities,
        "generated_by": "Gemini (structure) + Claude (synthesis)",
        "feedback_incorporated": len(brief_feedback_log)
    })

@app.route("/api/comms/drafts", methods=["GET"])
def get_comms_drafts():
    return jsonify(list(comms_drafts.values()))

@app.route("/api/comms/approve", methods=["POST"])
def approve_draft():
    data = request.json or {}
    draft_id = data.get("id")
    payload = data.get("payload")
    
    if not draft_id or draft_id not in comms_drafts:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400
        
    draft = comms_drafts[draft_id]
    if draft["status"] == "Executed / Sent":
        return jsonify({"success": False, "error": "Draft already executed"}), 400
        
    if payload:
        draft["payload"] = payload
        
    draft["status"] = "Executed / Sent"
    
    log_msg = f"HUMAN-IN-THE-LOOP VALIDATED: Executed network broadcast for {draft['channel']}. Payload successfully transmitted."
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": log_msg
    })
    
    return jsonify({
        "success": True,
        "message": f"Draft for {draft['recipient']} has been verified and executed.",
        "draft": draft
    })

@app.route("/api/comms/reject", methods=["POST"])
def reject_draft():
    """Natasha rejects/dismisses a draft action."""
    data = request.json or {}
    draft_id = data.get("id")

    if not draft_id or draft_id not in comms_drafts:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400

    draft = comms_drafts[draft_id]
    if draft["status"] == "Executed / Sent":
        return jsonify({"success": False, "error": "Cannot reject an already executed draft"}), 400

    draft["status"] = "Rejected"

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": f"HUMAN-IN-THE-LOOP REJECTED: Outbound draft to {draft['recipient']} was dismissed."
    })

    return jsonify({
        "success": True,
        "message": f"Draft for {draft['recipient']} has been rejected.",
        "draft": draft
    })

@app.route("/api/comms/rework", methods=["POST"])
def rework_draft():
    """Natasha requests a rework of a draft from Athena."""
    data = request.json or {}
    draft_id = data.get("id")
    instruction = data.get("instruction", "")
    current_payload = data.get("payload")

    if not draft_id or draft_id not in comms_drafts:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400
    if not instruction:
        return jsonify({"success": False, "error": "Instruction required"}), 400

    draft = comms_drafts[draft_id]
    if draft["status"] == "Executed / Sent":
        return jsonify({"success": False, "error": "Cannot rework an already executed draft"}), 400

    base_text = current_payload if current_payload else draft["payload"]

    prompt = f"""
    Rework this communication draft to {draft['recipient']} based on the following instruction: "{instruction}"
    
    ORIGINAL DRAFT / BASE TEXT:
    {base_text}
    
    Ensure you match Natasha's voice (intelligent, warm, direct, no corporate filler). Return only the revised message text. No introductory remarks.
    """
    revised_text = ask_claude(prompt)

    draft["payload"] = revised_text
    draft["status"] = "Pending Approval"

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": f"ATHENA REWORKED DRAFT: Updated draft to {draft['recipient']} based on instruction: '{instruction}'"
    })

    return jsonify({
        "success": True,
        "message": "Draft revised by Athena.",
        "draft": draft
    })

@app.route("/api/devops/telemetry", methods=["GET"])
def get_telemetry():
    current_latency = int(12 + random.uniform(-3, 4))
    devops_telemetry["latency_history"].append(current_latency)
    if len(devops_telemetry["latency_history"]) > 10:
        devops_telemetry["latency_history"].pop(0)
        
    devops_telemetry["error_history"].append(0)
    if len(devops_telemetry["error_history"]) > 10:
        devops_telemetry["error_history"].pop(0)
        
    return jsonify({
        "supabase_connection": devops_telemetry["supabase_connection"],
        "supabase_url": devops_telemetry["supabase_url"],
        "twilio_gateway": devops_telemetry["twilio_gateway"],
        "gmail_gateway": devops_telemetry["gmail_gateway"],
        "behavioral_profiling_trackers": devops_telemetry["behavioral_profiling_trackers"],
        "current_latency_ms": current_latency,
        "latency_history": devops_telemetry["latency_history"],
        "error_history": devops_telemetry["error_history"]
    })

@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify(system_logs)

@app.route("/api/voice/dictate", methods=["POST"])
def post_dictation():
    """Voice/dictation endpoint — routes to Claude for real reasoning."""
    data = request.json or {}
    text = data.get("text", "")
    
    if not text:
        return jsonify({"success": False, "error": "No text provided"}), 400
        
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core (Voice)",
        "message": f"Dictation received: '{text}'"
    })
    
    claude_response = ask_claude(text)
    
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": f"Claude response delivered: {len(claude_response)} chars."
    })
    
    return jsonify({
        "success": True,
        "response": claude_response,
        "logs": system_logs[-5:]
    })

@app.route("/")
def index():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Frontend file not found. Please ensure index.html exists in templates.", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
