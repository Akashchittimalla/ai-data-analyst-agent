"""
chart_recommender.py
Rules-based engine that picks the best chart type from query results.
No LLM needed — fast and deterministic.
"""


def recommend_chart(question: str, rows: list[dict], columns: list[str]) -> dict:
    """
    Returns chart config:
    { type, x_col, y_cols, group_col, title, stacked, horizontal }
    """
    if not rows or not columns:
        return {"type": "bar", "x_col": None, "y_cols": [], "title": question, "stacked": False}

    q = question.lower()

    # Classify columns
    numeric_cols = [c for c in columns if isinstance(rows[0].get(c), (int, float))]
    text_cols    = [c for c in columns if c not in numeric_cols]

    # Detect time column
    time_col = None
    for col in columns:
        if any(k in col.lower() for k in ["date", "month", "quarter", "year", "week", "period"]):
            time_col = col
            break

    # Detect group/series column
    group_col = None
    for col in text_cols:
        if any(k in col.lower() for k in ["region", "category", "segment", "product", "channel", "type"]):
            group_col = col
            break

    # ── Chart selection logic ──────────────────────────────────────────────────

    # Time + groups → multi-line
    if time_col and group_col and numeric_cols:
        return {
            "type": "line",
            "x_col": time_col,
            "y_cols": numeric_cols[:2],
            "group_col": group_col,
            "title": _title(question),
            "stacked": False,
            "horizontal": False,
        }

    # Time only → line or area
    if time_col and numeric_cols:
        is_growth = any(k in q for k in ["growth", "trend", "over time", "cumulative"])
        return {
            "type": "area" if is_growth else "line",
            "x_col": time_col,
            "y_cols": numeric_cols[:2],
            "group_col": None,
            "title": _title(question),
            "stacked": False,
            "horizontal": False,
        }

    # Share/breakdown → doughnut
    if any(k in q for k in ["share", "breakdown", "percentage", "proportion", "mix", "distribution", "which"]):
        if len(rows) <= 8 and text_cols and numeric_cols:
            return {
                "type": "doughnut",
                "x_col": text_cols[0],
                "y_cols": [numeric_cols[0]],
                "group_col": None,
                "title": _title(question),
                "stacked": False,
                "horizontal": False,
            }

    # Many categories → horizontal bar
    if text_cols and numeric_cols and len(rows) > 6:
        return {
            "type": "bar",
            "x_col": text_cols[0],
            "y_cols": numeric_cols[:2],
            "group_col": None,
            "title": _title(question),
            "stacked": len(numeric_cols) > 1,
            "horizontal": True,
        }

    # Category comparison → bar
    if text_cols and numeric_cols:
        return {
            "type": "bar",
            "x_col": text_cols[0],
            "y_cols": numeric_cols[:2],
            "group_col": None,
            "title": _title(question),
            "stacked": len(numeric_cols) > 1,
            "horizontal": False,
        }

    # Two numerics → scatter
    if len(numeric_cols) >= 2:
        return {
            "type": "scatter",
            "x_col": numeric_cols[0],
            "y_cols": [numeric_cols[1]],
            "group_col": None,
            "title": _title(question),
            "stacked": False,
            "horizontal": False,
        }

    # Fallback
    return {
        "type": "bar",
        "x_col": columns[0],
        "y_cols": numeric_cols[:1],
        "group_col": None,
        "title": _title(question),
        "stacked": False,
        "horizontal": False,
    }


def _title(q: str) -> str:
    clean = q.strip().rstrip("?").strip()
    return clean[:50] + "..." if len(clean) > 50 else clean