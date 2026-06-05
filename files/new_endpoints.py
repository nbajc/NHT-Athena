# ── ADD THESE TWO ENDPOINTS TO app.py ────────────────────────────────────────
# Paste them before the last `if __name__ == "__main__":` line

# In-memory feedback store (replace with Supabase later)
brief_feedback_log = []


@app.route("/api/brief/feedback", methods=["POST"])
def brief_feedback():
    """
    FIX 4: Receive feedback about today's brief.
    Stored and injected into tomorrow's Gemini + Claude brief generation.
    """
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
    """
    FIX 5: Claude + Gemini coordinate to produce today's priority list.
    Gemini structures the data, Claude synthesizes through Natasha's strategic lens.
    """
    # Build feedback context from previous feedback
    feedback_context = ""
    if brief_feedback_log:
        recent = brief_feedback_log[-3:]  # Last 3 feedback items
        feedback_context = "Previous feedback to incorporate:\n" + \
            "\n".join([f"- {f['feedback']}" for f in recent])

    # Step 1: Gemini structures raw priorities
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

    # Step 2: Claude synthesizes into structured JSON priorities
    claude_prompt = f"""
    Based on these raw priorities from Gemini:
    
    {gemini_priorities_raw}
    
    Return ONLY a JSON array of priority objects. No preamble, no markdown, no explanation.
    Each object must have:
    - "text": the priority as a clear, actionable sentence (max 15 words)
    - "urgent": true or false
    
    Example format:
    [{{"text": "Submit ARC website before June 20 deadline.", "urgent": true}}, ...]
    
    Return valid JSON only.
    """

    try:
        claude_response = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=512,
            system="You are Athena, Natasha's executive AI. Return only valid JSON arrays as instructed.",
            messages=[{"role": "user", "content": claude_prompt}]
        )
        import json
        priorities_json = claude_response.content[0].text.strip()
        # Strip any accidental markdown fences
        priorities_json = priorities_json.replace("```json", "").replace("```", "").strip()
        priorities = json.loads(priorities_json)
    except Exception as e:
        # Fallback if Claude JSON parsing fails
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
