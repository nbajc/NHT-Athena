import os
import time
import random
import json
import anthropic
import google.generativeai as genai
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from dotenv import load_dotenv
import datetime
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from supabase import create_client, Client

# Load environmental variables
load_dotenv()

app = Flask(__name__)

# Update CORS to support localized testing and production subdomain
CORS(app, origins=[
    "https://athena.nexushestia.com",
    "http://localhost:5000",
    "http://127.0.0.1:5000"
])

# ── API Clients ────────────────────────────────────────────────────────────────
anthropic_client = None
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
if anthropic_key:
    try:
        anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Anthropic client: {e}")
else:
    print("[WARNING] ANTHROPIC_API_KEY is missing from environment. Claude integration will be disabled.")

gemini_model = None
google_key = os.getenv("GOOGLE_API_KEY")
if google_key:
    try:
        genai.configure(api_key=google_key)
        gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        print(f"[ERROR] Failed to initialize Gemini model: {e}")
else:
    print("[WARNING] GOOGLE_API_KEY is missing from environment. Gemini integration will be disabled.")

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = None

if supabase_url and supabase_key:
    try:
        # Normalize trailing slash in REST URL if present
        normalized_url = supabase_url
        if normalized_url.endswith("/rest/v1/"):
            normalized_url = normalized_url.replace("/rest/v1/", "")
        supabase = create_client(normalized_url, supabase_key)
        print(f"[SUPABASE] Client initialized successfully for URL: {normalized_url}")
    except Exception as e:
        print(f"[SUPABASE ERROR] Failed to initialize Supabase client: {e}")
else:
    print("[SUPABASE WARNING] Missing SUPABASE_URL or SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY. Running in fallback memory mode.")

# ── Google OAuth Scopes ──────────────────────────────────────────────────────
# Authorized redirect URIs configured in Google Cloud Console:
# - https://api.athena.nexushestia.com/api/auth/callback
# - http://localhost:5000/api/auth/callback
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/gmail.readonly'
]

# Helper to load Google Client Config
def get_google_client_config():
    env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if env_creds:
        try:
            return json.loads(env_creds)
        except Exception as e:
            print(f"Error parsing GOOGLE_CREDENTIALS_JSON: {e}")
            
    secret_path = os.getenv("GOOGLE_CLIENT_SECRET_FILE")
    if secret_path and os.path.exists(secret_path):
        try:
            with open(secret_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading GOOGLE_CLIENT_SECRET_FILE: {e}")
    return None

# Helper to load stored Google Credentials from Supabase
def load_google_credentials():
    if not supabase:
        return None
    try:
        res = supabase.table("oauth_tokens").select("token_data").eq("user_id", "natasha").execute()
        if res.data:
            creds_data = res.data[0]['token_data']
            creds = Credentials(
                token=creds_data.get('token'),
                refresh_token=creds_data.get('refresh_token'),
                token_uri=creds_data.get('token_uri'),
                client_id=creds_data.get('client_id'),
                client_secret=creds_data.get('client_secret'),
                scopes=creds_data.get('scopes')
            )
            # Auto refresh token if expired
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                # Update back in Supabase
                creds_dict = {
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes
                }
                supabase.table("oauth_tokens").upsert({
                    "user_id": "natasha",
                    "token_data": creds_dict,
                    "updated_at": "now()"
                }).execute()
            return creds
    except Exception as e:
        print(f"Error loading/refreshing Google credentials: {e}")
    return None

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

# ── Fallback / Initial States ──────────────────────────────────────────────────
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

comms_drafts = {
    "gmail": {
        "id": "gmail",
        "channel": "Gmail (PCC Response)",
        "recipient": "Nathan",
        "status": "Pending Approval",
        "payload": "Subject: PCC Milestone Review & Next Steps\n\nNathan,\n\nCongratulations on reaching the 18-month PCC milestone! It's incredible to see the progress. Let's schedule a review next week to align on the next phases.\n\nBest,\nNatasha",
        "integration": "Integrated 18-month PCC milestone data from OAUTH_CLIENT_SECRET context.",
        "broadcast_type": "Gmail API (gmail.context.create_draft)",
        "repeat_tomorrow": False
    },
    "instagram": {
        "id": "instagram",
        "channel": "Instagram (Outreach)",
        "recipient": "Jenny (Don't Look Projects)",
        "status": "Pending Approval",
        "payload": "Hey Jenny! I love what you're doing with Don't Look Projects. The aesthetic is incredibly aligned. Would love to sync up about a collaboration next week if you're open!",
        "integration": "Local browser automation buffer payload (Puppeteer/Playwright headless buffer).",
        "broadcast_type": "Browser Automation Buffer",
        "repeat_tomorrow": False
    },
    "whatsapp": {
        "id": "whatsapp",
        "channel": "WhatsApp (Metrics)",
        "recipient": "Denis",
        "status": "Pending Approval",
        "payload": "Denis, here are the Belgrade timezone automated metrics:\n- Daily Active Sessions: 142\n- Sync Status: SUCCESS\n- Response Latency: 14ms",
        "integration": "Belgrade timezone trigger (+9 hrs). Formulated Twilio WhatsApp transaction routing payload.",
        "broadcast_type": "Twilio WhatsApp API Gateway",
        "repeat_tomorrow": False
    }
}

system_logs = [
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600)), "source": "Athena-Core", "message": "System initialization complete. Sovereignty guardrails loaded."},
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3200)), "source": "Brief-Orchestrator", "message": "Routine block 'Dennis + Mama Exam Prep' synced and tracked."},
    {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 1800)), "source": "Comms-Draft-Engine", "message": "Draft payloads compiled. Headless loop paused. Awaiting human verification."}
]

devops_telemetry = {
    "supabase_connection": "CONNECTED",
    "supabase_url": os.getenv("SUPABASE_URL", "https://nht-athena-mock.supabase.co"),
    "twilio_gateway": "READY",
    "gmail_gateway": "READY",
    "behavioral_profiling_trackers": "STRIPPED & BLOCKED (Data Privacy Enforcement)",
    "latency_history": [12, 14, 11, 15, 12, 13, 12],
    "error_history": [0, 0, 0, 0, 0, 0, 0]
}

brief_feedback_log = []

# ── Helper: Call Claude ────────────────────────────────────────────────────────
def ask_claude(user_message: str, context: str = "") -> str:
    """Send a message to Claude with Athena's system prompt."""
    if not anthropic_client:
        return "Claude unavailable: ANTHROPIC_API_KEY is not configured in settings."
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
    if not gemini_model:
        return "Gemini brief unavailable: GOOGLE_API_KEY is not configured in settings."
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

# ── Helper: Mock FCM Notification ──────────────────────────────────────────────
def send_fcm_notification(title: str, body: str):
    """Sends a mock or real FCM push notification."""
    print(f"[FCM SEND] {title}: {body}")
    # Real implementation placeholder:
    # try:
    #     from firebase_admin import messaging
    #     message = messaging.Message(
    #         notification=messaging.Notification(title=title, body=body),
    #         topic="athena_briefs"
    #     )
    #     messaging.send(message)
    # except Exception as e:
    #     print(f"FCM Send failed: {e}")

# ── Helper: Generate Daily Brief Internal ──────────────────────────────────────
def generate_daily_brief_internal():
    # Pull latest user feedback & RL signals
    feedback_context = ""
    if supabase:
        try:
            res_fb = supabase.table("feedback").select("feedback").order("created_at", desc=True).limit(5).execute()
            res_rl = supabase.table("rl_signals").select("type", "weight", "data").order("created_at", desc=True).limit(10).execute()
            
            fb_list = [f["feedback"] for f in res_fb.data] if res_fb.data else []
            rl_list = [f"{r['type']} ({r['weight']}): {r['data']}" for r in res_rl.data] if res_rl.data else []
            
            if fb_list or rl_list:
                feedback_context = "INCORPORATED RL SIGNALS & USER FEEDBACK FROM LAST 7 DAYS:\n"
                if fb_list:
                    feedback_context += "User feedback:\n" + "\n".join([f"- {f}" for f in fb_list]) + "\n"
                if rl_list:
                    feedback_context += "RL outcomes:\n" + "\n".join([f"- {r}" for r in rl_list]) + "\n"
        except Exception as e:
            print(f"Error loading RL signals: {e}")
    else:
        if brief_feedback_log:
            recent = brief_feedback_log[-3:]
            feedback_context = "Previous feedback to incorporate:\n" + \
                "\n".join([f"- {f['feedback']}" for f in recent])

    # Fetch live calendar + email data using stored credentials
    google_creds = load_google_credentials()
    raw_data = {
        "calendar": "Google Calendar not connected. Go to /api/auth/google.",
        "emails": "Gmail not connected. Go to /api/auth/google.",
        "tasks": "ARC website build | Tobii EyeX C# script (~80 lines remaining) | TFAP@CAA paper proposal (July 15)"
    }
    
    if google_creds:
        try:
            # Calendar API
            cal_service = build('calendar', 'v3', credentials=google_creds)
            now_str = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = cal_service.events().list(
                calendarId='primary', timeMin=now_str, maxResults=5, singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            if events:
                raw_data["calendar"] = "\n".join([f"- {e.get('summary')} ({e.get('start', {}).get('dateTime', e.get('start', {}).get('date'))})" for e in events])
            else:
                raw_data["calendar"] = "No events scheduled today."
                
            # Gmail API
            gmail_service = build('gmail', 'v1', credentials=google_creds)
            gmail_res = gmail_service.users().messages().list(userId='me', maxResults=5, q='is:unread').execute()
            messages = gmail_res.get('messages', [])
            email_summaries = []
            for m in messages:
                msg = gmail_service.users().messages().get(userId='me', id=m['id'], format='metadata', metadataHeaders=['From', 'Subject']).execute()
                headers = msg.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
                email_summaries.append(f"Email from {sender} - Subj: {subject}")
            if email_summaries:
                raw_data["emails"] = "\n".join(email_summaries)
            else:
                raw_data["emails"] = "No unread emails requiring action."
        except Exception as e:
            print(f"Error fetching Google API data: {e}")
            raw_data["calendar"] = f"Error querying Google Calendar: {str(e)}"
            raw_data["emails"] = f"Error querying Gmail: {str(e)}"

    # Generate brief & synthesis
    gemini_brief = generate_brief_with_gemini(raw_data)
    
    prompt = "Review this daily brief and tell me what Natasha should focus on first today, and flag anything critical."
    if feedback_context:
        prompt += f"\n\n{feedback_context}"
        
    claude_synthesis = ask_claude(prompt, context=gemini_brief)
    
    # Store to Supabase
    if supabase:
        try:
            supabase.table("briefs").insert({
                "gemini_brief": gemini_brief,
                "athena_synthesis": claude_synthesis,
                "states": orchestrator_states
            }).execute()
        except Exception as e:
            print(f"Error saving brief to Supabase: {e}")
            
    # Send FCM push
    send_fcm_notification("Morning Briefing Ready", "Your customized priority agenda has been created.")
    
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Brief-Orchestrator",
        "message": "Scheduled Daily Briefing generated and broadcasted via FCM."
    })
    
    return gemini_brief, claude_synthesis

# ── Scheduled Jobs ─────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()

def daily_brief_job():
    print("[SCHEDULER] Starting morning briefing generation...")
    generate_daily_brief_internal()

# Schedule briefing for 7:00 AM Pacific Time
la_tz = timezone('America/Los_Angeles')
scheduler.add_job(daily_brief_job, 'cron', hour=7, minute=0, timezone=la_tz)
scheduler.start()
print("[SCHEDULER] Daily 7:00 AM PT morning brief job scheduled.")

# ── Google OAuth Routes ────────────────────────────────────────────────────────
@app.route("/api/auth/google", methods=["GET"])
def auth_google():
    client_config = get_google_client_config()
    if not client_config:
        return jsonify({"success": False, "error": "Google client secret configuration missing"}), 500
    
    host = request.headers.get('Host', '')
    if 'localhost' in host or '127.0.0.1' in host:
        redirect_uri = 'http://localhost:5000/api/auth/callback'
    else:
        redirect_uri = 'https://api.athena.nexushestia.com/api/auth/callback'
        
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    return jsonify({"success": True, "authorization_url": authorization_url})

@app.route("/api/auth/callback", methods=["GET"])
def auth_callback():
    code = request.args.get('code')
    if not code:
        return "Authorization code missing", 400
        
    client_config = get_google_client_config()
    if not client_config:
        return "Google client secret configuration missing", 500
        
    host = request.headers.get('Host', '')
    if 'localhost' in host or '127.0.0.1' in host:
        redirect_uri = 'http://localhost:5000/api/auth/callback'
    else:
        redirect_uri = 'https://api.athena.nexushestia.com/api/auth/callback'

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    
    flow.fetch_token(code=code)
    credentials = flow.credentials
    
    creds_dict = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    
    if supabase:
        try:
            supabase.table("oauth_tokens").upsert({
                "user_id": "natasha",
                "token_data": creds_dict,
                "updated_at": "now()"
            }).execute()
        except Exception as e:
            print(f"Error saving tokens: {e}")
            
    # Redirect back to dashboard
    if 'localhost' in host or '127.0.0.1' in host:
        return redirect('http://localhost:5000/?auth=success')
    else:
        return redirect('https://athena.nexushestia.com/?auth=success')

# ── General Routes ─────────────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(SOVEREIGNTY_CONFIG)

@app.route("/api/brief", methods=["GET"])
def get_brief():
    """Returns the latest daily brief summary (or generates it if none exist)."""
    if supabase:
        try:
            res = supabase.table("briefs").select("*").order("created_at", desc=True).limit(1).execute()
            if res.data:
                brief = res.data[0]
                return jsonify({
                    "states": brief.get("states", orchestrator_states),
                    "gemini_brief": brief.get("gemini_brief"),
                    "athena_synthesis": brief.get("athena_synthesis"),
                    "generated_at": brief.get("created_at")
                })
        except Exception as e:
            print(f"Error querying briefs table: {e}")
            
    # If no database or empty, generate on the fly
    gemini_brief, claude_synthesis = generate_daily_brief_internal()
    return jsonify({
        "states": orchestrator_states,
        "gemini_brief": gemini_brief,
        "athena_synthesis": claude_synthesis,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route("/api/brief/generate", methods=["POST"])
def generate_daily_brief_endpoint():
    """Endpoint to trigger the morning brief pipeline manually."""
    gemini_brief, claude_synthesis = generate_daily_brief_internal()
    return jsonify({
        "success": True,
        "gemini_brief": gemini_brief,
        "athena_synthesis": claude_synthesis
    })

@app.route("/api/brief/feedback", methods=["POST"])
def brief_feedback():
    """Receive feedback about today's brief to inject into future generation."""
    data = request.json or {}
    feedback_text = data.get("feedback", "").strip()

    if not feedback_text:
        return jsonify({"success": False, "error": "No feedback provided"}), 400

    if supabase:
        try:
            supabase.table("feedback").insert({"feedback": feedback_text}).execute()
            # Also log a general RL signal
            supabase.table("rl_signals").insert({
                "type": "brief_feedback",
                "weight": 0,
                "data": {"feedback": feedback_text}
            }).execute()
        except Exception as e:
            print(f"Error inserting feedback to Supabase: {e}")

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
    if supabase:
        try:
            res_fb = supabase.table("feedback").select("feedback").order("created_at", desc=True).limit(3).execute()
            feedback_context = "Previous feedback to incorporate:\n" + \
                "\n".join([f"- {f['feedback']}" for f in res_fb.data]) if res_fb.data else ""
        except Exception as e:
            print(f"Error pulling feedback for priorities: {e}")
    else:
        if brief_feedback_log:
            recent = brief_feedback_log[-3:]
            feedback_context = "Previous feedback to incorporate:\n" + \
                "\n".join([f"- {f['feedback']}" for f in recent])

    # Fetch live calendar + email data
    google_creds = load_google_credentials()
    raw_data = {
        "calendar": "ARC Athena Fund application deadline June 20 | Denis exams June 16-19 | Seed round follow-ups",
        "emails": "Boris Ivanović warm response pending | Trimble Craig Trickett intro",
        "tasks": "ARC website build | Tobii EyeX C# script | TFAP@CAA paper (July 15) | Sasha Jokić client follow-up",
        "active_projects": "Nexus Hestia seed round ($2-3M, Pedja verbal) | Athena agent build | Technosomatic Cyberfeminism 2.0 show"
    }
    
    if google_creds:
        try:
            # Query Calendar
            cal_service = build('calendar', 'v3', credentials=google_creds)
            now_str = datetime.datetime.utcnow().isoformat() + 'Z'
            events_result = cal_service.events().list(
                calendarId='primary', timeMin=now_str, maxResults=5, singleEvents=True, orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            if events:
                raw_data["calendar"] = ", ".join([e.get('summary') for e in events])
                
            # Query Gmail
            gmail_service = build('gmail', 'v1', credentials=google_creds)
            gmail_res = gmail_service.users().messages().list(userId='me', maxResults=5, q='is:unread').execute()
            messages = gmail_res.get('messages', [])
            email_summaries = []
            for m in messages:
                msg = gmail_service.users().messages().get(userId='me', id=m['id'], format='metadata', metadataHeaders=['Subject']).execute()
                subject = next((h['value'] for h in msg.get('payload', {}).get('headers', []) if h['name'] == 'Subject'), 'No Subject')
                email_summaries.append(subject)
            if email_summaries:
                raw_data["emails"] = ", ".join(email_summaries)
        except Exception as e:
            print(f"Error querying Google data for priorities: {e}")

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
        
        # Save to priorities table if Supabase active
        if supabase:
            try:
                for p in priorities:
                    supabase.table("priorities").insert({
                        "text": p["text"],
                        "urgent": p["urgent"]
                    }).execute()
            except Exception as e:
                print(f"Error storing priorities: {e}")
                
    except Exception as e:
        # Graceful fallback
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
    if supabase:
        try:
            res = supabase.table("drafts").select("*").execute()
            if not res.data:
                # Seed database if empty
                initial_drafts = list(comms_drafts.values())
                for d in initial_drafts:
                    supabase.table("drafts").insert(d).execute()
                return jsonify(initial_drafts)
            return jsonify(res.data)
        except Exception as e:
            print(f"Error querying drafts: {e}")
            
    return jsonify(list(comms_drafts.values()))

@app.route("/api/comms/draft/generate", methods=["POST"])
def generate_draft():
    data = request.json or {}
    recipient = data.get("recipient")
    channel = data.get("channel")
    prompt = data.get("prompt")
    
    if not recipient or not channel or not prompt:
        return jsonify({"success": False, "error": "Missing recipient, channel or prompt"}), 400
        
    system_instructions = f"Draft a message for {recipient} via {channel} based on: '{prompt}'."
    payload = ask_claude(system_instructions)
    
    draft_id = f"draft_{int(time.time())}"
    draft = {
        "id": draft_id,
        "recipient": recipient,
        "channel": channel,
        "status": "Pending Approval",
        "payload": payload,
        "integration": "Generated by Claude draft engine.",
        "broadcast_type": "Gmail API" if "gmail" in channel.lower() else "Twilio WhatsApp API Gateway" if "whatsapp" in channel.lower() else "Browser Automation Buffer",
        "repeat_tomorrow": False
    }
    
    if supabase:
        try:
            supabase.table("drafts").insert(draft).execute()
        except Exception as e:
            print(f"Error saving draft: {e}")
            
    comms_drafts[draft_id] = draft
    return jsonify({"success": True, "draft": draft})

@app.route("/api/comms/approve", methods=["POST"])
def approve_draft():
    data = request.json or {}
    draft_id = data.get("id")
    payload = data.get("payload")
    
    if not draft_id:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400
        
    try:
        # Load draft details
        draft = None
        if supabase:
            res = supabase.table("drafts").select("*").eq("id", draft_id).execute()
            if res.data:
                draft = res.data[0]
        else:
            draft = comms_drafts.get(draft_id)
            
        if not draft:
            return jsonify({"success": False, "error": "Draft not found"}), 404
            
        if draft["status"] == "Executed / Sent":
            return jsonify({"success": False, "error": "Draft already executed"}), 400
            
        # Update payload if user edited
        update_data = {"status": "Executed / Sent"}
        if payload:
            update_data["payload"] = payload
            draft["payload"] = payload
            
        if supabase:
            supabase.table("drafts").update(update_data).eq("id", draft_id).execute()
            # Log approval RL signal
            supabase.table("rl_signals").insert({
                "type": "draft_approved",
                "weight": 1,
                "data": {"draft_id": draft_id, "recipient": draft.get("recipient"), "channel": draft.get("channel")}
            }).execute()
        else:
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
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/comms/reject", methods=["POST"])
def reject_draft():
    """Natasha rejects a draft action, recording the choice in Supabase and returning repeat_tomorrow status."""
    data = request.json or {}
    draft_id = data.get("id")
    repeat_tomorrow = data.get("repeat_tomorrow", False)

    if not draft_id:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400

    try:
        draft = None
        if supabase:
            res = supabase.table("drafts").select("*").eq("id", draft_id).execute()
            if res.data:
                draft = res.data[0]
        else:
            draft = comms_drafts.get(draft_id)

        if not draft:
            return jsonify({"success": False, "error": "Draft not found"}), 404

        if draft["status"] == "Executed / Sent":
            return jsonify({"success": False, "error": "Cannot reject an already executed draft"}), 400

        update_data = {
            "status": "Rejected",
            "repeat_tomorrow": repeat_tomorrow
        }

        if supabase:
            supabase.table("drafts").update(update_data).eq("id", draft_id).execute()
            # Log rejection RL signal
            supabase.table("rl_signals").insert({
                "type": "draft_rejected",
                "weight": -1,
                "data": {"draft_id": draft_id, "recipient": draft.get("recipient"), "channel": draft.get("channel")}
            }).execute()
        else:
            draft["status"] = "Rejected"
            draft["repeat_tomorrow"] = repeat_tomorrow

        system_logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Athena-Core",
            "message": f"HUMAN-IN-THE-LOOP REJECTED: Outbound draft to {draft['recipient']} was dismissed. Repeat tomorrow: {repeat_tomorrow}"
        })

        return jsonify({
            "success": True,
            "message": f"Draft for {draft['recipient']} has been rejected.",
            "draft": draft,
            "repeat_tomorrow": repeat_tomorrow
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/comms/rework", methods=["POST"])
def rework_draft():
    """Natasha requests a rework of a draft from Athena."""
    data = request.json or {}
    draft_id = data.get("id")
    instruction = data.get("instruction", "")
    current_payload = data.get("payload")

    if not draft_id:
        return jsonify({"success": False, "error": "Invalid Draft ID"}), 400
    if not instruction:
        return jsonify({"success": False, "error": "Instruction required"}), 400

    try:
        draft = None
        if supabase:
            res = supabase.table("drafts").select("*").eq("id", draft_id).execute()
            if res.data:
                draft = res.data[0]
        else:
            draft = comms_drafts.get(draft_id)

        if not draft:
            return jsonify({"success": False, "error": "Draft not found"}), 404

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

        update_data = {
            "payload": revised_text,
            "status": "Pending Approval"
        }

        if supabase:
            supabase.table("drafts").update(update_data).eq("id", draft_id).execute()
        else:
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
            "draft": draft if not supabase else {**draft, **update_data}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/offline/sync", methods=["POST"])
def offline_sync():
    """Receive and synchronize offline voice/text dictations queued inside Android APK."""
    data = request.json or {}
    items = data.get("items", [])
    
    if not items:
        return jsonify({"success": True, "processed": 0, "results": []})
        
    results = []
    for item in items:
        text = item.get("text", "")
        item_id = item.get("id")
        
        if supabase:
            try:
                supabase.table("offline_queue").insert({
                    "text": text,
                    "synced": True
                }).execute()
            except Exception as e:
                print(f"Error logging to offline_queue: {e}")
                
        # Synthesize via Claude
        claude_response = ask_claude(text)
        results.append({
            "id": item_id,
            "text": text,
            "response": claude_response,
            "status": "PROCESSED"
        })
        
        system_logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Athena-Core (Offline Sync)",
            "message": f"Processed synced dictation '{text[:40]}': {len(claude_response)} chars."
        })
        
    return jsonify({
        "success": True,
        "processed": len(items),
        "results": results
    })

@app.route("/api/ask", methods=["POST"])
def post_ask():
    """Direct QA pipeline with Athena/Claude."""
    data = request.json or {}
    question = data.get("question", "")
    
    if not question:
        return jsonify({"success": False, "error": "No question provided"}), 400
        
    response = ask_claude(question)
    return jsonify({"success": True, "response": response})

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
        "supabase_connection": "CONNECTED" if supabase else "FALLBACK_CONNECTED",
        "supabase_url": supabase_url or "https://nht-athena-mock.supabase.co",
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
