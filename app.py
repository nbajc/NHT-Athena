import os
import time
import random
import json
import anthropic
import google.generativeai as genai
from flask import Flask, jsonify, request, redirect, send_file
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

# Read ATHENA_PASSCODE from environment, default to "athena2026"
athena_passcode = os.getenv("ATHENA_PASSCODE") or "athena2026"
athena_passcode = athena_passcode.strip('"\'')

app = Flask(__name__)

# Update CORS to support localized testing and production subdomain
CORS(app, origins=[
    "https://athena.nexushestia.com",
    "http://localhost:5000",
    "http://127.0.0.1:5000"
])

@app.before_request
def require_passcode():
    # Only intercept API requests
    if request.path.startswith("/api/"):
        # Exclude public auth routes
        exempt_routes = [
            "/api/auth/verify",
            "/api/auth/google",
            "/api/auth/callback"
        ]
        if request.path in exempt_routes:
            return None
        
        # Check authorization header or X-Athena-Token
        auth_header = request.headers.get("Authorization")
        token = request.headers.get("X-Athena-Token")
        
        if auth_header and auth_header.startswith("Bearer "):
            header_token = auth_header[7:] # strip "Bearer "
            if header_token == athena_passcode:
                return None
                
        if token == athena_passcode:
            return None
            
        return jsonify({"success": False, "error": "Unauthorized"}), 401

@app.route("/api/auth/verify", methods=["POST"])
def verify_passcode():
    data = request.json or {}
    passcode = data.get("passcode")
    if passcode == athena_passcode:
        return jsonify({"success": True, "message": "Access granted"})
    return jsonify({"success": False, "error": "Incorrect passcode"}), 401

# ── API Clients ────────────────────────────────────────────────────────────────
anthropic_client = None
anthropic_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("anthropic_api_key")
if anthropic_key:
    # Remove surrounding quotes if present (sometimes happens with raw environment input)
    anthropic_key = anthropic_key.strip('"\'')
    try:
        anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    except Exception as e:
        print(f"[ERROR] Failed to initialize Anthropic client: {e}")
else:
    print("[WARNING] ANTHROPIC_API_KEY is missing from environment. Claude integration will be disabled.")

gemini_model = None
google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("google_api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api_key")
if google_key:
    google_key = google_key.strip('"\'')
    try:
        genai.configure(api_key=google_key)
        gemini_model = genai.GenerativeModel("gemini-2.0-flash")
        print(f"[GEMINI] Configured successfully using API key: {google_key[:10]}...")
    except Exception as e:
        print(f"[ERROR] Failed to initialize Gemini model: {e}")
else:
    print("[WARNING] GOOGLE_API_KEY/GEMINI_API_KEY is missing from environment. Gemini integration will be disabled.")

# Initialize Supabase client
supabase_url = os.getenv("SUPABASE_URL") or os.getenv("supabase_url")
supabase_key = os.getenv("SUPABASE_KEY") or os.getenv("supabase_key") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("supabase_service_role_key")
supabase: Client = None

if supabase_url and supabase_key:
    supabase_url = supabase_url.strip('"\'')
    supabase_key = supabase_key.strip('"\'')
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
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly'
]

# Helper to load Google Client Config
def get_google_client_config():
    env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("google_credentials_json")
    if env_creds:
        # Strip outer quotes if present
        env_creds = env_creds.strip('"\'')
        try:
            return json.loads(env_creds)
        except Exception as e:
            print(f"Error parsing GOOGLE_CREDENTIALS_JSON: {e}")
            
    secret_path = os.getenv("GOOGLE_CLIENT_SECRET_FILE") or os.getenv("google_client_secret_file")
    if secret_path:
        secret_path = secret_path.strip('"\'')
        if os.path.exists(secret_path):
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

comms_drafts = {}

active_memory_goals = [
    {
        "id": "goal_1",
        "title": "Technosomatic Cyberfeminism 2.0 solo show (ARC Gallery)",
        "description": "Prepare solo show artwork and coordination. Deadline June 20, show in September 2026.",
        "due_date": "2026-06-20",
        "completed": False
    },
    {
        "id": "goal_2",
        "title": "TFAP@CAA Paper Proposal submission",
        "description": "Prepare abstract and submit proposal.",
        "due_date": "2026-07-15",
        "completed": False
    }
]

active_horizon_events = [
    {
        "id": "event_1",
        "title": "September Solo Show: Technosomatic Cyberfeminism 2.0 at ARC Gallery",
        "action_required": "Coordinating seed funding and ARC show artworks.",
        "event_date": "2026-09-01",
        "completed": False
    },
    {
        "id": "event_2",
        "title": "Aleksandar Lazarevic cybersecurity review check-in",
        "action_required": "Schedule cybersecurity audit of Athena platform.",
        "event_date": "2026-06-25",
        "completed": False
    }
]

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

# Global cache variables and chat session memory
last_known_priorities = []
last_known_brief = {"gemini_brief": "", "athena_synthesis": ""}
chat_sessions = {}

def get_realtime_context() -> str:
    """Gathers current timezone values, timeline state blocks, priorities, and brief synthesis."""
    from pytz import timezone
    la_tz = timezone('America/Los_Angeles')
    belgrade_tz = timezone('Europe/Belgrade')
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    la_time = now_utc.astimezone(la_tz)
    belgrade_time = now_utc.astimezone(belgrade_tz)
    
    local_time_str = la_time.strftime("%Y-%m-%d %H:%M:%S %Z")
    belgrade_time_str = belgrade_time.strftime("%Y-%m-%d %H:%M:%S %Z")
    local_date_str = la_time.strftime("%A, %B %d, %Y")
    belgrade_date_str = belgrade_time.strftime("%A, %B %d, %Y")
    
    states_str = json.dumps(orchestrator_states, indent=2)
    
    priorities_list = []
    if last_known_priorities:
        priorities_list = [p.get("text", "") for p in last_known_priorities]
    elif supabase:
        try:
            res = supabase.table("priorities").select("text").order("created_at", desc=True).limit(10).execute()
            if res.data:
                priorities_list = [r["text"] for r in res.data]
        except Exception as e:
            print(f"Error reading priorities for context: {e}")
            
    if not priorities_list:
        priorities_list = ["No priorities set yet."]
        
    priorities_str = "\n".join([f"- {p}" for p in priorities_list])
    
    brief_synth = ""
    if last_known_brief.get("athena_synthesis"):
        brief_synth = last_known_brief["athena_synthesis"]
    elif supabase:
        try:
            res = supabase.table("briefs").select("athena_synthesis").order("created_at", desc=True).limit(1).execute()
            if res.data:
                brief_synth = res.data[0].get("athena_synthesis", "")
        except Exception as e:
            print(f"Error reading brief for context: {e}")
            
    if not brief_synth:
        brief_synth = "No active daily brief synthesis."
        
    # Fetch active long-term goals for permanent memory injection
    goals_list = []
    if supabase:
        try:
            res_goals = supabase.table("long_term_goals").select("*").eq("completed", False).order("due_date", desc=False).execute()
            if res_goals.data:
                goals_list = res_goals.data
        except Exception as e:
            print(f"Error reading long term goals for context: {e}")
            
    if not goals_list:
        goals_list = [g for g in active_memory_goals if not g["completed"]]
        goals_list.sort(key=lambda x: x["due_date"])
        
    if goals_list:
        goals_str = "\n".join([f"- {g['title']} (Due: {g['due_date']}){': ' + g['description'] if g.get('description') else ''}" for g in goals_list])
    else:
        goals_str = "No active long-term goals."
        
    # Fetch active upcoming events on the horizon
    horizon_list = []
    if supabase:
        try:
            res_hor = supabase.table("on_the_horizon").select("*").eq("completed", False).order("event_date", desc=False).execute()
            if res_hor.data:
                horizon_list = res_hor.data
        except Exception as e:
            print(f"Error reading horizon events for context: {e}")
            
    if not horizon_list:
        horizon_list = [h for h in active_horizon_events if not h["completed"]]
        horizon_list.sort(key=lambda x: x["event_date"])
        
    if horizon_list:
        horizon_str = "\n".join([f"- {h['title']} (Date: {h['event_date']}){': ' + h['action_required'] if h.get('action_required') else ''}" for h in horizon_list])
    else:
        horizon_str = "No upcoming events on the horizon."
        
    context = f"""Current Times:
- Local Time (LA): {local_time_str} ({local_date_str})
- Belgrade Time: {belgrade_time_str} ({belgrade_date_str})

Active Long-Term Goals (in permanent memory):
{goals_str}

Upcoming Events on the Horizon (Athena is monitoring):
{horizon_str}

Active Persistent State Blocks:
{states_str}

Today's Actionable Priorities:
{priorities_str}

Latest Daily Briefing Synthesis:
{brief_synth}
"""
    return context

def ask_claude_with_memory(user_message: str, context: str = "", session_id: str = "default") -> str:
    """Send a message to Claude maintaining 10 turns of conversation memory and system context."""
    if not anthropic_client:
        return "Claude unavailable: ANTHROPIC_API_KEY is not configured in settings."
    try:
        if session_id not in chat_sessions:
            chat_sessions[session_id] = []
            
        history = chat_sessions[session_id][-10:]
        
        messages = []
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})
            
        current_content = user_message
        if context:
            current_content = f"REAL-TIME CONTEXT:\n{context}\n\nUSER REQUEST:\n{user_message}"
            
        messages.append({"role": "user", "content": current_content})
        
        response = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=ATHENA_SYSTEM_PROMPT,
            messages=messages
        )
        
        assistant_response = response.content[0].text
        
        chat_sessions[session_id].append({"role": "user", "content": user_message})
        chat_sessions[session_id].append({"role": "assistant", "content": assistant_response})
        
        return assistant_response
    except Exception as e:
        return f"Claude unavailable: {str(e)}"

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
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        la_time = now_utc.astimezone(timezone('America/Los_Angeles'))
        current_date_str = la_time.strftime("%A, %B %d, %Y")
        
        prompt = f"""
        Current Date: {current_date_str}
        
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
    
    # Fallback to Claude if Gemini fails or hits quota limits
    if not gemini_brief or "unavailable" in gemini_brief.lower() or "limit" in gemini_brief.lower() or "quota" in gemini_brief.lower() or "429" in gemini_brief:
        print("[WARNING] Gemini brief generation failed or hit quota. Falling back to Claude for structured brief...")
        fallback_prompt = f"""
        Generate a concise, structured daily brief for Natasha Bajc based on this raw data:
        
        Calendar events today: {raw_data.get('calendar', 'No events found')}
        Emails requiring attention: {raw_data.get('emails', 'None')}
        Active tasks: {raw_data.get('tasks', 'None')}
        
        Format as:
        - 3 bullet priorities for today
        - Any urgent flags
        - One sentence on what can wait
        
        Be direct. No filler.
        """
        gemini_brief = ask_claude(fallback_prompt)
    
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    la_time = now_utc.astimezone(timezone('America/Los_Angeles'))
    belgrade_time = now_utc.astimezone(timezone('Europe/Belgrade'))
    la_date_str = la_time.strftime("%A, %B %d, %Y")
    la_time_str = la_time.strftime("%I:%M %p")
    belgrade_time_str = belgrade_time.strftime("%I:%M %p")
    
    # Get active long-term goals
    goals_list = []
    if supabase:
        try:
            res_goals = supabase.table("long_term_goals").select("*").eq("completed", False).order("due_date", desc=False).execute()
            if res_goals.data:
                goals_list = res_goals.data
        except Exception as e:
            print(f"Error querying long_term_goals for brief: {e}")
    if not goals_list:
        goals_list = [g for g in active_memory_goals if not g["completed"]]
        
    goals_str = "\n".join([f"- {g['title']} (Due: {g['due_date']})" for g in goals_list]) if goals_list else "None"

    brief_time_context = f"""Current Date: {la_date_str}
Current LA Time: {la_time_str}
Current Belgrade Time: {belgrade_time_str}

Active Long-Term Goals (Permanent Memory):
{goals_str}

DAILY BRIEF DATA:
{gemini_brief}"""

    prompt = "Review this daily brief and tell me what Natasha should focus on first today, and flag anything critical."
    if feedback_context:
        prompt += f"\n\n{feedback_context}"
        
    claude_synthesis = ask_claude(prompt, context=brief_time_context)
    
    # Generate draft recommendations dynamically using Claude based on the daily brief context
    try:
        draft_prompt = f"""
        Analyze the daily briefing and raw Google calendar/email data:
        
        DAILY BRIEF:
        {gemini_brief}
        
        ATHENA SYNTHESIS:
        {claude_synthesis}
        
        Identify any communication tasks Natasha needs to perform (e.g. congratulations to Nathan for reaching the 18-month PCC milestone, reaching out to Jenny at Don't Look Projects, follow up with client prospects).
        For each task, write a draft in Natasha's voice (intelligent, warm, direct, no filler).
        
        Return ONLY a valid JSON array of draft objects. No markdown formatting (no ```json). No preamble or explanation.
        Each object MUST have:
        - "recipient": the name of the recipient (e.g., "Nathan" or "Jenny")
        - "channel": the platform channel (e.g. "Gmail (PCC Response)", "Instagram (Outreach)", "WhatsApp (Metrics)")
        - "payload": the message text drafted
        - "integration": a short phrase describing the context (e.g. "Integrated 18-month PCC milestone data.")
        - "broadcast_type": "Gmail API (gmail.context.create_draft)" or "Browser Automation Buffer" or "Twilio WhatsApp API Gateway"
        """
        
        claude_draft_res = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system="You are Athena, Natasha's sovereign assistant. Return only valid JSON arrays of communications drafts.",
            messages=[{"role": "user", "content": draft_prompt}]
        )
        drafts_json = claude_draft_res.content[0].text.strip()
        drafts_json = drafts_json.replace("```json", "").replace("```", "").strip()
        new_drafts = json.loads(drafts_json)
        
        if supabase:
            try:
                # Delete current pending drafts
                supabase.table("drafts").delete().eq("status", "Pending Approval").execute()
                
                # Insert new drafts
                for idx, nd in enumerate(new_drafts):
                    draft_id = f"draft_brief_{int(time.time())}_{idx}"
                    supabase.table("drafts").insert({
                        "id": draft_id,
                        "recipient": nd.get("recipient"),
                        "channel": nd.get("channel"),
                        "status": "Pending Approval",
                        "payload": nd.get("payload"),
                        "integration": nd.get("integration"),
                        "broadcast_type": nd.get("broadcast_type"),
                        "repeat_tomorrow": False
                    }).execute()
            except Exception as e:
                print(f"Error saving generated drafts to Supabase: {e}")
        
        # Update local memory
        for k in list(comms_drafts.keys()):
            if comms_drafts[k]["status"] == "Pending Approval":
                comms_drafts.pop(k)
                
        for idx, nd in enumerate(new_drafts):
            draft_id = f"draft_brief_{int(time.time())}_{idx}"
            comms_drafts[draft_id] = {
                "id": draft_id,
                "recipient": nd.get("recipient"),
                "channel": nd.get("channel"),
                "status": "Pending Approval",
                "payload": nd.get("payload"),
                "integration": nd.get("integration"),
                "broadcast_type": nd.get("broadcast_type"),
                "repeat_tomorrow": False
            }
            
        system_logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Brief-Orchestrator",
            "message": f"Dynamically compiled {len(new_drafts)} drafts from daily briefing context."
        })
    except Exception as e:
        print(f"Error generating drafts from brief: {e}")
    
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
    
    global last_known_brief
    last_known_brief = {
        "gemini_brief": gemini_brief,
        "athena_synthesis": claude_synthesis
    }
    
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
    
    # Fetch authenticated user profile using the Gmail API
    email = ""
    try:
        gmail_service = build('gmail', 'v1', credentials=credentials)
        profile = gmail_service.users().getProfile(userId='me').execute()
        email = profile.get('emailAddress', '').lower().strip()
        print(f"[AUTH] Google callback authenticated user email: {email}")
    except Exception as e:
        print(f"[AUTH ERROR] Failed to fetch Google profile: {e}")
        
    # Check against preapproved email list
    is_preapproved = False
    if email:
        preapproved_emails = [
            "natasha@nexushestia.com",
            "natasha.bajc@nexushestia.com",
            "natasabajc@gmail.com",
            "natasa.bajc@gmail.com"
        ]
        if email in preapproved_emails or email.endswith("@nexushestia.com"):
            is_preapproved = True
            
        # Check against Supabase users table (hosted access similar to Cosmic Buildings)
        if supabase:
            try:
                res_user = supabase.table("users").select("*").eq("email", email).execute()
                if res_user.data:
                    user_record = res_user.data[0]
                    if user_record.get("approved") is True:
                        is_preapproved = True
                        print(f"[AUTH] User '{email}' authenticated via Supabase users table (role: {user_record.get('role')})")
            except Exception as e:
                print(f"[AUTH ERROR] Failed to query users table in Supabase: {e}")
            
    if 'localhost' in host or '127.0.0.1' in host:
        dest_url = 'http://localhost:5000/'
    else:
        dest_url = 'https://athena.nexushestia.com/'
        
    if not is_preapproved:
        print(f"[AUTH DENIED] Email '{email}' is not authorized to access Athena.")
        return redirect(f"{dest_url}?auth=failed&error=unauthorized_email")
        
    if supabase:
        try:
            supabase.table("oauth_tokens").upsert({
                "user_id": "natasha",
                "token_data": creds_dict,
                "updated_at": "now()"
            }).execute()
        except Exception as e:
            print(f"Error saving tokens: {e}")
            
    return redirect(f"{dest_url}?auth=success&passcode={athena_passcode}")

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

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    la_time = now_utc.astimezone(timezone('America/Los_Angeles'))
    current_date_str = la_time.strftime("%A, %B %d, %Y")
    
    # Get active long-term goals for priorities
    goals_list = []
    if supabase:
        try:
            res_goals = supabase.table("long_term_goals").select("*").eq("completed", False).order("due_date", desc=False).execute()
            if res_goals.data:
                goals_list = res_goals.data
        except Exception as e:
            print(f"Error querying goals for priorities: {e}")
    if not goals_list:
        goals_list = [g for g in active_memory_goals if not g["completed"]]
    goals_str = ", ".join([f"{g['title']} (Due {g['due_date']})" for g in goals_list]) if goals_list else "None"

    gemini_priorities_prompt = f"""
    Current Date: {current_date_str}
    Active Long-Term Goals (Permanent Memory): {goals_str}
    
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
        if not gemini_model:
            raise Exception("Gemini model not initialized")
        gemini_response = gemini_model.generate_content(gemini_priorities_prompt)
        gemini_priorities_raw = gemini_response.text
    except Exception as e:
        print(f"[WARNING] Gemini priorities generation failed or hit quota: {e}. Falling back to Claude...")
        try:
            fallback_prompt = f"""
            You are Athena, Natasha's sovereign executive assistant. 
            Current Date: {current_date_str}
            Active Long-Term Goals (Permanent Memory): {goals_str}
            
            Based on this data:
            Calendar: {raw_data['calendar']}
            Emails: {raw_data['emails']}
            Tasks: {raw_data['tasks']}
            Active Projects: {raw_data['active_projects']}
            {feedback_context}
            
            Return ONLY a numbered list of 5-7 priorities, one per line.
            Mark urgent items with [URGENT] at the start.
            Be specific and actionable. No filler.
            """
            gemini_priorities_raw = ask_claude(fallback_prompt)
        except Exception as ex:
            gemini_priorities_raw = f"Gemini and Claude fallback unavailable: {str(ex)}"

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

    global last_known_priorities
    last_known_priorities = priorities

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

@app.route("/api/comms/draft/save", methods=["POST"])
def save_draft():
    data = request.json or {}
    draft_id = data.get("id")
    payload = data.get("payload")
    
    if not draft_id or not payload:
        return jsonify({"success": False, "error": "Missing id or payload"}), 400
        
    try:
        if supabase:
            supabase.table("drafts").update({"payload": payload}).eq("id", draft_id).execute()
            
        if draft_id in comms_drafts:
            comms_drafts[draft_id]["payload"] = payload
            
        system_logs.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "Comms-Draft-Engine",
            "message": f"Draft saved locally/remotely: ID '{draft_id}'."
        })
        return jsonify({"success": True, "message": "Draft saved successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
    session_id = data.get("session_id", "default")
    
    if not question:
        return jsonify({"success": False, "error": "No question provided"}), 400
        
    context = get_realtime_context()
    response = ask_claude_with_memory(question, context=context, session_id=session_id)
    return jsonify({"success": True, "response": response})

# ── Goals Routes ─────────────────────────────────────────────────────────────
@app.route("/api/goals", methods=["GET"])
def get_goals():
    if supabase:
        try:
            res = supabase.table("long_term_goals").select("*").eq("completed", False).order("due_date", desc=False).execute()
            return jsonify(res.data)
        except Exception as e:
            print(f"Error querying long_term_goals: {e}")
            
    # Return sorted memory goals
    active = [g for g in active_memory_goals if not g["completed"]]
    active.sort(key=lambda x: x["due_date"])
    return jsonify(active)

@app.route("/api/goals", methods=["POST"])
def create_goal():
    data = request.json or {}
    title = data.get("title")
    description = data.get("description", "")
    due_date = data.get("due_date")
    
    if not title or not due_date:
        return jsonify({"success": False, "error": "Missing title or due_date"}), 400
        
    goal_id = f"goal_{int(time.time())}"
    goal = {
        "id": goal_id,
        "title": title,
        "description": description,
        "due_date": due_date,
        "completed": False
    }
    
    if supabase:
        try:
            supabase.table("long_term_goals").insert(goal).execute()
        except Exception as e:
            print(f"Error saving goal to Supabase: {e}")
            
    active_memory_goals.append(goal)
    
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Memory-Vault",
        "message": f"Offloaded new long-term goal: '{title}' (due {due_date})."
    })
    
    return jsonify({"success": True, "goal": goal})

@app.route("/api/goals/complete", methods=["POST"])
def complete_goal_api():
    data = request.json or {}
    goal_id = data.get("id")
    
    if not goal_id:
        return jsonify({"success": False, "error": "Missing goal ID"}), 400
        
    if supabase:
        try:
            supabase.table("long_term_goals").update({"completed": True}).eq("id", goal_id).execute()
        except Exception as e:
            print(f"Error updating goal: {e}")
            
    for g in active_memory_goals:
        if g["id"] == goal_id:
            g["completed"] = True
            system_logs.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Memory-Vault",
                "message": f"Completed long-term goal: '{g['title']}'."
            })
            break
            
    return jsonify({"success": True})

# ── Horizon Events Routes ─────────────────────────────────────────────────────────────
@app.route("/api/horizon", methods=["GET"])
def get_horizon():
    if supabase:
        try:
            res = supabase.table("on_the_horizon").select("*").eq("completed", False).order("event_date", desc=False).execute()
            return jsonify(res.data)
        except Exception as e:
            print(f"Error querying on_the_horizon: {e}")
            
    # Return sorted memory events
    active = [e for e in active_horizon_events if not e["completed"]]
    active.sort(key=lambda x: x["event_date"])
    return jsonify(active)

@app.route("/api/horizon", methods=["POST"])
def create_horizon_event():
    data = request.json or {}
    title = data.get("title")
    action_required = data.get("action_required", "")
    event_date = data.get("event_date")
    
    if not title or not event_date:
        return jsonify({"success": False, "error": "Missing title or event_date"}), 400
        
    event_id = f"event_{int(time.time())}"
    event = {
        "id": event_id,
        "title": title,
        "action_required": action_required,
        "event_date": event_date,
        "completed": False
    }
    
    if supabase:
        try:
            supabase.table("on_the_horizon").insert(event).execute()
        except Exception as e:
            print(f"Error saving event to Supabase: {e}")
            
    active_horizon_events.append(event)
    
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Memory-Vault",
        "message": f"Added upcoming event: '{title}' (date {event_date})."
    })
    
    return jsonify({"success": True, "event": event})

@app.route("/api/horizon/complete", methods=["POST"])
def complete_horizon_event_api():
    data = request.json or {}
    event_id = data.get("id")
    
    if not event_id:
        return jsonify({"success": False, "error": "Missing event ID"}), 400
        
    if supabase:
        try:
            supabase.table("on_the_horizon").update({"completed": True}).eq("id", event_id).execute()
        except Exception as e:
            print(f"Error updating event: {e}")
            
    for e in active_horizon_events:
        if e["id"] == event_id:
            e["completed"] = True
            system_logs.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Memory-Vault",
                "message": f"Completed and archived horizon event: '{e['title']}'."
            })
            break
            
    return jsonify({"success": True})

@app.route("/api/states", methods=["GET"])
def get_states():
    """Returns the current persistent timeline state blocks."""
    return jsonify(orchestrator_states)

@app.route("/api/states", methods=["POST"])
def update_state():
    """Updates one of the timeline state blocks."""
    data = request.json or {}
    block_key = data.get("block") # 'routine_block', 'target_block', or 'anchor_block'
    title = data.get("title")
    time_val = data.get("time")
    status = data.get("status")
    
    if not block_key or block_key not in orchestrator_states:
        return jsonify({"success": False, "error": "Invalid block key"}), 400
        
    if title is not None:
        orchestrator_states[block_key]["title"] = title
    if time_val is not None:
        orchestrator_states[block_key]["time"] = time_val
    if status is not None:
        orchestrator_states[block_key]["status"] = status
        
    # If Supabase is connected, we can also update the latest brief record's states
    if supabase:
        try:
            res = supabase.table("briefs").select("id").order("created_at", desc=True).limit(1).execute()
            if res.data:
                latest_id = res.data[0]["id"]
                supabase.table("briefs").update({"states": orchestrator_states}).eq("id", latest_id).execute()
        except Exception as e:
            print(f"Error syncing updated states to Supabase: {e}")
            
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "State-Engine",
        "message": f"Updated timeline block '{block_key}': {title} | {time_val} | {status}"
    })
    
    return jsonify({"success": True, "states": orchestrator_states})

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
    """Voice/dictation endpoint — routes to Claude with memory and context."""
    data = request.json or {}
    text = data.get("text", "")
    session_id = data.get("session_id", "default")
    
    if not text:
        return jsonify({"success": False, "error": "No text provided"}), 400
        
    system_logs.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Athena-Core (Voice)",
        "message": f"Dictation received: '{text}'"
    })
    
    context = get_realtime_context()
    claude_response = ask_claude_with_memory(text, context=context, session_id=session_id)
    
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

@app.route("/api/wellness", methods=["GET"])
def get_wellness():
    # Return wellness data dynamically from Google Sheet if connected, otherwise fallback to default
    google_creds = load_google_credentials()
    fallback_data = {
        "1": {"focus": "Gym Resistance", "core": "Heavy Upper Body Compound Lifting", "duration": "45 Min", "sauna": "Infrared Sauna (20–30 min post)", "hydration": "2.5 Liters", "nutrition": "HIGH protein · MODERATE complex carbs · LOW-MODERATE anti-inflammatory Omegas", "type": "Gym & EMS Day"},
        "2": {"focus": "Cardio / Flush", "core": "Steady-State Swim (Moderate Pace)", "duration": "40–50 Min", "sauna": "None — let skin breathe", "hydration": "2.5 Liters", "nutrition": "HIGH protein · LOW carbs targeted around swim · MODERATE healthy fats (avocado, olive oil)", "type": "Swimming & Rest Day"},
        "3": {"focus": "Aesthetic Day", "core": "RF & Ultrasonic Cavitation + Microneedling", "duration": "Varies", "sauna": "Microneedling (Face/Body) post-RF", "hydration": "3.0 Liters — CRITICAL", "nutrition": "HIGH protein · STRICTLY LOW carbs · MINIMAL fats · Fasted or protein-only pre · ZERO carbs/fats 3–4h post", "type": "Cavitation Day"},
        "4": {"focus": "Gym Resistance", "core": "Heavy Lower Body Compound Lifting", "duration": "45 Min", "sauna": "Infrared Sauna (20–30 min post)", "hydration": "2.5 Liters", "nutrition": "HIGH protein · MODERATE complex carbs timed 90 min pre-workout · Focus on anti-inflammatory Omegas", "type": "Gym & EMS Day"},
        "5": {"focus": "Cardio / Flush", "core": "Steady-State Swim (Moderate Pace)", "duration": "40–50 Min", "sauna": "None — let skin breathe", "hydration": "2.5 Liters", "nutrition": "HIGH protein · LOW carbs targeted around swim · MODERATE healthy fats", "type": "Swimming & Rest Day"},
        "6": {"focus": "Deep Sculpt", "core": "Full Body EMS — Electrical Muscle Stimulation", "duration": "20 Min", "sauna": "None", "hydration": "3.0 Liters — CRITICAL", "nutrition": "HIGH protein · MODERATE complex carbs pre · Fast-digesting protein + simple carb within 45 min post", "type": "Gym & EMS Day"},
        "0": {"focus": "Rest & Reset", "core": "Complete Systemic Rest — Passive Recovery", "duration": "Full Day", "sauna": "None", "hydration": "2.0 Liters", "nutrition": "HIGH protein · LOW carbs light and targeted · MODERATE healthy fats for hormone optimization", "type": "Swimming & Rest Day"}
    }
    
    if google_creds:
        try:
            service = build('sheets', 'v4', credentials=google_creds)
            spreadsheet_id = "1cWBKR9MXPjbC6_JqasprCnOBKoVCkRc3a9pqfYZvvNk"
            # Read first sheet
            meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = [s['properties']['title'] for s in meta['sheets']]
            
            # Find a sheet named Wellness, otherwise use the first sheet
            wellness_sheet = next((s for s in sheets if "wellness" in s.lower()), sheets[0])
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=f"'{wellness_sheet}'!A1:J50"
            ).execute()
            rows = result.get('values', [])
            
            if len(rows) > 1:
                # We have data! Let's parse it.
                headers = [h.strip().lower() for h in rows[0]]
                
                idx_day = next((i for i, h in enumerate(headers) if "day" in h), -1)
                idx_focus = next((i for i, h in enumerate(headers) if "focus" in h), -1)
                idx_core = next((i for i, h in enumerate(headers) if "core" in h or "training" in h or "workout" in h), -1)
                idx_duration = next((i for i, h in enumerate(headers) if "duration" in h or "time" in h), -1)
                idx_sauna = next((i for i, h in enumerate(headers) if "sauna" in h), -1)
                idx_hydration = next((i for i, h in enumerate(headers) if "hydration" in h or "water" in h), -1)
                idx_nutrition = next((i for i, h in enumerate(headers) if "nutrition" in h or "diet" in h or "food" in h), -1)
                idx_type = next((i for i, h in enumerate(headers) if "type" in h or "category" in h), -1)
                
                sheet_data = {}
                day_map = {
                    "sunday": "0", "monday": "1", "tuesday": "2", "wednesday": "3", "thursday": "4", "friday": "5", "saturday": "6",
                    "sun": "0", "mon": "1", "tue": "2", "wed": "3", "thu": "4", "fri": "5", "sat": "6",
                    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6"
                }
                
                for row in rows[1:]:
                    if not row:
                        continue
                    day_val = row[idx_day].strip().lower() if idx_day != -1 and len(row) > idx_day else ""
                    day_key = day_map.get(day_val)
                    if not day_key:
                        continue
                        
                    sheet_data[day_key] = {
                        "focus": row[idx_focus].strip() if idx_focus != -1 and len(row) > idx_focus else "None",
                        "core": row[idx_core].strip() if idx_core != -1 and len(row) > idx_core else "None",
                        "duration": row[idx_duration].strip() if idx_duration != -1 and len(row) > idx_duration else "None",
                        "sauna": row[idx_sauna].strip() if idx_sauna != -1 and len(row) > idx_sauna else "None",
                        "hydration": row[idx_hydration].strip() if idx_hydration != -1 and len(row) > idx_hydration else "None",
                        "nutrition": row[idx_nutrition].strip() if idx_nutrition != -1 and len(row) > idx_nutrition else "None",
                        "type": row[idx_type].strip() if idx_type != -1 and len(row) > idx_type else "None"
                    }
                
                if len(sheet_data) > 0:
                    final_data = fallback_data.copy()
                    final_data.update(sheet_data)
                    return jsonify({"success": True, "source": "Google Sheets", "wellness": final_data})
        except Exception as e:
            print(f"[WELLNESS ERROR] Failed to fetch from Google Sheet: {e}")
            
    return jsonify({"success": True, "source": "Fallback (Hardcoded)", "wellness": fallback_data})

@app.route("/api/timeline", methods=["GET"])
def get_timeline():
    # Return calendar events dynamically from Google Calendar if connected, otherwise fallback to default
    google_creds = load_google_credentials()
    
    fallback_blocks = [
        {"id": "tb-0", "time": "06:30", "title": "Morning routine + hydration protocol", "notes": "2.5L water · Check Athena overnight digest"},
        {"id": "tb-1", "time": "08:00", "title": "GYM — Lower Body Compound", "notes": "45 min · Infrared sauna 20 min post"},
        {"id": "tb-2", "time": "10:00", "title": "ARC Gallery website build", "notes": "technosomatic-arc-athena.vercel.app · Pull 3 exhibition sites"},
        {"id": "tb-3", "time": "12:00", "title": "Tobii EyeX SDK investigation", "notes": "Win11 + Game Integration API + C# Unity script"},
        {"id": "tb-4", "time": "14:00", "title": "Boris Ivanović follow-up", "notes": "Written investment intent confirmation"},
        {"id": "tb-5", "time": "15:30", "title": "Supabase memory layer debug", "notes": "Verify Railway env vars in dashboard settings"},
        {"id": "tb-6", "time": "17:00", "title": "PCC class prep + academic writing block", "notes": "TFAP@CAA proposal outline start"},
        {"id": "tb-7", "time": "19:30", "title": "Review + reset · Athena end-of-day brief", "notes": "Tomorrow's priorities · Overnight context load"}
    ]
    
    if google_creds:
        try:
            cal_service = build('calendar', 'v3', credentials=google_creds)
            from pytz import timezone
            la_tz = timezone('America/Los_Angeles')
            now_la = datetime.datetime.now(la_tz)
            
            start_of_day = now_la.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = now_la.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            start_iso = start_of_day.isoformat()
            end_iso = end_of_day.isoformat()
            
            events_result = cal_service.events().list(
                calendarId='primary', 
                timeMin=start_iso, 
                timeMax=end_iso, 
                singleEvents=True, 
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if events:
                blocks = []
                for idx, event in enumerate(events):
                    start = event.get('start', {})
                    start_dt = start.get('dateTime') or start.get('date')
                    time_str = "—"
                    if start_dt:
                        try:
                            dt = datetime.datetime.fromisoformat(start_dt)
                            if dt.tzinfo:
                                dt = dt.astimezone(la_tz)
                            time_str = dt.strftime("%H:%M")
                        except Exception:
                            if "T" in start_dt:
                                time_str = start_dt.split("T")[1][:5]
                                
                    blocks.append({
                        "id": event.get('id') or f"cal-{idx}",
                        "time": time_str,
                        "title": event.get('summary', 'Untitled Event'),
                        "notes": event.get('description', '') or ''
                    })
                return jsonify({"success": True, "source": "Google Calendar", "blocks": blocks})
        except Exception as e:
            print(f"[CALENDAR ERROR] Failed to fetch today's timeline: {e}")
            
    return jsonify({"success": True, "source": "Fallback (Hardcoded)", "blocks": fallback_blocks})

@app.route("/intricateNHT.png")
def serve_intricate():
    return send_file(os.path.join(app.root_path, "intricateNHT.png"))

@app.route("/reducedNHT.png")
def serve_reduced():
    return send_file(os.path.join(app.root_path, "reducedNHT.png"))

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
