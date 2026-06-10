"""
insight_generator.py
Sends query results + anomalies to Claude and gets back 4 structured business insights.
"""

import json

from xai_client import chat_completion


async def generate_insights(
    question: str,
    rows: list[dict],
    columns: list[str],
    anomalies: list[dict],
) -> list[dict]:
    """
    Call Grok with the data and return exactly 4 insight objects.
    Each: { icon, type, title, text }
    """
    sample = rows[:20]
    anomaly_msgs = [a["message"] for a in anomalies] or ["No anomalies detected"]

    prompt = f"""You are a senior business data analyst. Analyze this query result and return EXACTLY 4 insights.

Original question: {question}

Columns: {columns}
Data ({len(sample)} of {len(rows)} rows):
{json.dumps(sample, indent=2, default=str)}

Detected anomalies:
{chr(10).join(f"- {m}" for m in anomaly_msgs)}

Return a JSON array of exactly 4 objects. Each must have:
- "icon": one emoji from ["📉","📈","⚠️","💡","🔍","⚡","✅","📊","🗺️","💰","📍","🧭"]
- "type": one of ["negative","positive","warning","recommendation"]
- "title": bold phrase 4-7 words
- "text": exactly 2 sentences. Be specific with real numbers from the data.

Order:
1. Main finding — what happened
2. Root cause or breakdown
3. Context or comparison
4. Actionable recommendation (start with "Recommendation:")

Respond with ONLY the JSON array. No markdown, no explanation."""

    raw = chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=0.3,
    )
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        insights = json.loads(raw)
        for ins in insights:
            ins.setdefault("icon", "📊")
            ins.setdefault("type", "positive")
            ins.setdefault("title", "Analysis Result")
            ins.setdefault("text", "See data for details.")
        return insights[:4]
    except json.JSONDecodeError:
        return [{
            "icon": "📊",
            "type": "positive",
            "title": "Analysis Complete",
            "text": raw[:300]
        }]
