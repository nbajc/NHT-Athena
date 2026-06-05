import os
import time
import random
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Load environmental variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Settings & Sovereignty Guardrails
SOVEREIGNTY_CONFIG = {
    "agent_name": "Athena-Core",
    "system_role": "Sovereignty Executive & Interface Layer",
    "interface_mode": "Voice-First / Mobile Dictation Optimization",
    "root_context": "Sitting directly on top of Natasha's Daily Briefing loop.",
    "guardrails": {
        "human_in_the_loop": True,
        "data_privacy": "Zero behavioral user surveillance telemetry."
    }
}

# Persistent States for Brief-Orchestrator
orchestrator_states = {
    "routine_block": {
        "title": "Dennis + Mama Exam Prep",
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

# Initial state for Comms-Draft-Engine drafts
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

# System activity logs
system_logs = [
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600)), "source": "Athena-Core", "message": "System initialization complete. Sovereignty guardrails loaded."},
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3200)), "source": "Brief-Orchestrator", "message": "Routine block 'Dennis + Mama Exam Prep' synced and tracked."},
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1800)), "source": "Comms-Draft-Engine", "message": "Draft payloads compiled. Headless loop paused. Awaiting human verification."}
]

# Track simulated DevOps metrics
devops_telemetry = {
    "supabase_connection": "CONNECTED",
    "supabase_url": os.getenv("SUPABASE_URL", "https://nht-athena-mock.supabase.co"),
    "twilio_gateway": "READY",
    "gmail_gateway": "READY",
    "behavioral_profiling_trackers": "STRIPPED & BLOCKED (Data Privacy Enforcement)",
    "latency_history": [12, 14, 11, 15, 12, 13, 12],
    "error_history": [0, 0, 0, 0, 0, 0, 0]
}

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(SOVEREIGNTY_CONFIG)

@app.route("/api/brief", methods=["GET"])
def get_brief():
    return jsonify({
        "states": orchestrator_states,
        "daily_brief_text": "Good morning Natasha. Today you have Dennis + Mama Exam Prep at 07:00 AM, ongoing research check for DE Recertification (June 15), and the upcoming Boja's 50th Birthday Walk on Saturday, June 20. Comms-Draft-Engine has prepared 3 drafts for Nathan, Jenny, and Denis. Staging repositories are green."
    })

@app.route("/api/comms/drafts", methods=["GET"])
def get_comms_drafts():
    return jsonify(list(comms_drafts.values()))

@app.route("/api/comms/approve", methods=["POST"])
def approve_draft():
    data = request.json or {}
    draft_id = data.get("id")
    
    if not draft_id or draft_id not in comms_drafts:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400
        
    draft = comms_drafts[draft_id]
    if draft["status"] == "Executed / Sent":
        return jsonify({"success": False, "error": "Draft already executed"}), 400
        
    # Guardrail Check - Simulating final broadcast execution upon user confirmation
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

@app.route("/api/devops/telemetry", methods=["GET"])
def get_telemetry():
    # Update latest latency with small fluctuation
    current_latency = int(12 + random.uniform(-3, 4))
    devops_telemetry["latency_history"].append(current_latency)
    if len(devops_telemetry["latency_history"]) > 10:
        devops_telemetry["latency_history"].pop(0)
        
    devops_telemetry["error_history"].append(0)  # Always 0 due to premium stability
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
    data = request.json or {}
    text = data.get("text", "")
    
    if not text:
        return jsonify({"success": False, "error": "No text provided"}), 400
        
    # Athena parses the mobile dictation / voice input
    log_entry = f"Dictation Received: '{text}'"
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core (Voice-First)",
        "message": log_entry
    })
    
    # Simple keyword routing simulation
    response_msg = "Dictation processed."
    if "status" in text.lower() or "check" in text.lower():
        response_msg = "Checking statuses. All sub-agents operating within guardrail parameters."
    elif "approve" in text.lower() or "send" in text.lower():
        response_msg = "Dictation request parsed. Please manually click 'Approve' to confirm the outbound broadcast, as required by Sovereignty Guardrails."
    elif "dennis" in text.lower() or "mama" in text.lower():
        response_msg = "Brief-Orchestrator confirms Dennis + Mama prep block state is up to date."
        
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core",
        "message": f"Response: {response_msg}"
    })
    
    return jsonify({
        "success": True,
        "response": response_msg,
        "logs": system_logs
    })

# Add routes for frontend serving
@app.route("/")
def index():
    # Render static frontend index
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Frontend file not found. Please ensure index.html exists in templates.", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
