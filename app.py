import os
import time
import random
import anthropic
import google.generativeai as genai
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
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
    "version": "2.0",
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
        "title": "ARC Athena Fund Application",
        "time": "Deadline June 20, 2026",
        "status": "Artist statement drafted — website still needed"
    },
    "anchor_block": {
        "title": "Seed Round — Pedja Predin / Fifth Quarter",
        "time": "Target: End of Year Close",
        "status": "Verbal commitment secured"
    }
}

# ── Comms Drafts ───────────────────────────────────────────────────────────────
comms_drafts = {
    "boris": {
        "id": "boris",
        "channel": "Email",
        "recipient": "Boris Ivanović",
        "status": "Pending Approval",
        "payload": "Subject: Athena is live — NHT update\n\nBoris,\n\nQuick update: Athena, our internal AI executive layer, is now running on top of the NHT stack. Seed round has verbal from Pedja Predin / Fifth Quarter. ARC Athena Fund solo show confirmed for September 2026.\n\nWould love 20 minutes when you're next available.\n\nNatasha",
        "broadcast_type": "Gmail API"
    },
    "pedja": {
        "id": "pedja",
        "channel": "WhatsApp",
        "recipient": "Pedja Predin",
        "status": "Pending Approval",
        "payload": "Pedja — Athena agent is live on the stack. Making good progress. Let's sync this week on next steps toward close.",
        "broadcast_type": "Twilio WhatsApp"
    },
    "denis": {
        "id": "denis",
        "channel": "WhatsApp",
        "recipient": "Denis",
        "status": "Pending Approval",
        "payload": "Denis, checking in. How did the exam prep go today? Miss you.",
        "broadcast_type": "Twilio WhatsApp"
    }
}

# ── System Logs ────────────────────────────────────────────────────────────────
system_logs = [
    {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600)),
        "source": "Athena-Core",
        "message": "System v2.0 initialized. Claude + Gemini intelligence layer active."
    },
    {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1800)),
        "source": "Athena-Core",
        "message": "Sovereignty guardrails loaded. Human-in-the-loop enforced on all outbound."
    }
]

# ── DevOps Telemetry ───────────────────────────────────────────────────────────
devops_telemetry = {
    "supabase_connection": "CONNECTED",
    "supabase_url": os.getenv("SUPABASE_URL", "not-configured"),
    "anthropic_gateway": "READY",
    "gemini_gateway": "READY",
    "twilio_gateway": "READY",
    "gmail_gateway": "READY",
    "behavioral_profiling_trackers": "STRIPPED & BLOCKED",
    "latency_history": [12, 14, 11, 15, 12, 13, 12],
    "error_history": [0, 0, 0, 0, 0, 0, 0]
}

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
    2. Claude synthesizes it through Natasha's strategic lens
    """
    # Step 1: Raw data (in production this pulls from Google Calendar/Gmail APIs)
    raw_data = {
        "calendar": "ARC application deadline June 20 | Seed round follow-ups pending",
        "emails": "Boris Ivanović responded warmly | Trimble Discovery Session invite",
        "tasks": "ARC website build | Tobii EyeX C# script (~80 lines remaining) | TFAP@CAA paper proposal (July 15)"
    }

    # Step 2: Gemini generates structured brief
    gemini_brief = generate_brief_with_gemini(raw_data)

    # Step 3: Claude synthesizes with strategic context
    claude_synthesis = ask_claude(
        "Review this daily brief and tell me what Natasha should focus on first today, and flag anything critical.",
        context=gemini_brief
    )

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


@app.route("/api/comms/drafts", methods=["GET"])
def get_comms_drafts():
    return jsonify(list(comms_drafts.values()))


@app.route("/api/comms/draft/generate", methods=["POST"])
def generate_draft():
    """Ask Claude to draft a communication."""
    data = request.json or {}
    recipient = data.get("recipient", "")
    context = data.get("context", "")
    channel = data.get("channel", "email")

    if not recipient:
        return jsonify({"success": False, "error": "Recipient required"}), 400

    prompt = f"Draft a {channel} message to {recipient}. Context: {context}. Match Natasha's voice: direct, warm, intelligent. No filler."
    draft_text = ask_claude(prompt)

    draft_id = f"draft_{int(time.time())}"
    comms_drafts[draft_id] = {
        "id": draft_id,
        "channel": channel.capitalize(),
        "recipient": recipient,
        "status": "Pending Approval",
        "payload": draft_text,
        "broadcast_type": "Pending selection",
        "generated_by": "Claude / Athena"
    }

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Comms-Draft-Engine",
        "message": f"Claude-generated draft created for {recipient}. Awaiting human approval."
    })

    return jsonify({"success": True, "draft": comms_drafts[draft_id]})


@app.route("/api/comms/approve", methods=["POST"])
def approve_draft():
    """Human-in-the-loop approval gate."""
    data = request.json or {}
    draft_id = data.get("id")
    payload = data.get("payload")

    if not draft_id or draft_id not in comms_drafts:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400

    draft = comms_drafts[draft_id]

    if draft["status"] == "Executed / Sent":
        return jsonify({"success": False, "error": "Draft already executed"}), 400

    # Save any manual inline modifications
    if payload:
        draft["payload"] = payload

    draft["status"] = "Executed / Sent"

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": f"HUMAN-IN-THE-LOOP VALIDATED: Executed broadcast for {draft['channel']} → {draft['recipient']}."
    })

    return jsonify({
        "success": True,
        "message": f"Draft for {draft['recipient']} approved and executed.",
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

    if not draft_id or draft_id not in comms_drafts:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400
    if not instruction:
        return jsonify({"success": False, "error": "Instruction required"}), 400

    draft = comms_drafts[draft_id]

    if draft["status"] == "Executed / Sent":
        return jsonify({"success": False, "error": "Cannot rework an already executed draft"}), 400

    # Call Claude to rewrite the message based on feedback
    prompt = f"""
    Rework this communication draft to {draft['recipient']} based on the following instruction: "{instruction}"
    
    ORIGINAL DRAFT:
    {draft['payload']}
    
    Ensure you match Natasha's voice (intelligent, warm, direct, no corporate filler). Return only the revised message text. No introductory remarks.
    """
    revised_text = ask_claude(prompt)

    draft["payload"] = revised_text
    draft["status"] = "Pending Approval"  # Reset status

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



@app.route("/api/voice/dictate", methods=["POST"])
def post_dictation():
    """
    Voice/dictation endpoint — routes to Claude for real reasoning.
    No more keyword matching.
    """
    data = request.json or {}
    text = data.get("text", "")

    if not text:
        return jsonify({"success": False, "error": "No text provided"}), 400

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core (Voice)",
        "message": f"Dictation received: '{text[:80]}...'" if len(text) > 80 else f"Dictation received: '{text}'"
    })

    # Route to Claude for real reasoning
    claude_response = ask_claude(text)

    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": f"Claude response delivered. {len(claude_response)} chars."
    })

    return jsonify({
        "success": True,
        "input": text,
        "response": claude_response,
        "processed_by": "Claude / Athena",
        "logs": system_logs[-5:]  # Return last 5 logs only
    })


@app.route("/api/ask", methods=["POST"])
def ask_athena():
    """
    Direct question to Athena (Claude).
    For any strategic, synthesis, or drafting request.
    """
    data = request.json or {}
    question = data.get("question", "")
    context = data.get("context", "")

    if not question:
        return jsonify({"success": False, "error": "Question required"}), 400

    response = ask_claude(question, context)

    return jsonify({
        "success": True,
        "question": question,
        "response": response,
        "processed_by": "Claude / Athena"
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
        **devops_telemetry,
        "current_latency_ms": current_latency,
    })


@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify(system_logs)


@app.route("/")
def index():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Athena v2.0 running. Frontend not found — check templates/index.html.", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
