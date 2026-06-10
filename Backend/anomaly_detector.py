"""
anomaly_detector.py
Detects statistical anomalies using Z-score and IQR fencing methods.
No ML dependencies — pure Python statistics.
"""

import statistics


def detect_anomalies(rows: list[dict], columns: list[str]) -> list[dict]:
    """
    Scan numeric columns for anomalies.
    Returns list of anomaly dicts with severity, label, value, and message.
    """
    anomalies = []

    # Find numeric columns with enough data points
    numeric_cols = []
    for col in columns:
        vals = [
            r[col] for r in rows
            if r.get(col) is not None and isinstance(r[col], (int, float))
        ]
        if len(vals) >= 3:
            numeric_cols.append((col, vals))

    label_col = _find_label_col(columns)

    for col, vals in numeric_cols:
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 0

        # ── Z-Score detection ──────────────────────────────────────────────────
        if stdev > 0:
            for i, row in enumerate(rows):
                v = row.get(col)
                if v is None or not isinstance(v, (int, float)):
                    continue
                z = abs((v - mean) / stdev)
                if z > 2.5:
                    pct = round((v - mean) / mean * 100, 1) if mean != 0 else 0
                    label = str(row.get(label_col, f"Row {i+1}")) if label_col else f"Row {i+1}"
                    severity = "critical" if z > 3.5 else "warning"
                    anomalies.append({
                        "type": severity,
                        "column": col,
                        "label": label,
                        "value": round(v, 2),
                        "mean": round(mean, 2),
                        "z_score": round(z, 2),
                        "pct_diff": pct,
                        "direction": "above" if v > mean else "below",
                        "message": f"{label}: {col} is {abs(pct):.0f}% {'above' if v > mean else 'below'} average (z={z:.1f})"
                    })

        # ── IQR Fencing ────────────────────────────────────────────────────────
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[(3 * n) // 4]
        iqr = q3 - q1
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr

        for i, row in enumerate(rows):
            v = row.get(col)
            if v is None or not isinstance(v, (int, float)):
                continue
            if v < lo or v > hi:
                label = str(row.get(label_col, f"Row {i+1}")) if label_col else f"Row {i+1}"
                already = any(
                    a["label"] == label and a["column"] == col
                    for a in anomalies
                )
                if not already:
                    anomalies.append({
                        "type": "outlier",
                        "column": col,
                        "label": label,
                        "value": round(v, 2),
                        "fence_low": round(lo, 2),
                        "fence_high": round(hi, 2),
                        "pct_diff": round((v - mean) / mean * 100, 1) if mean != 0 else 0,
                        "message": f"{label}: {col} = {v:.0f} is outside normal range [{lo:.0f}–{hi:.0f}]"
                    })

    # Deduplicate and cap
    seen = set()
    unique = []
    for a in anomalies:
        key = (a["column"], a["label"])
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique[:6]


def _find_label_col(columns: list[str]) -> str | None:
    """Find the best text column to use as a row identifier."""
    preferred = ["quarter", "month", "date", "period", "region",
                 "category", "product", "name", "segment"]
    col_lower = {c.lower(): c for c in columns}
    for p in preferred:
        if p in col_lower:
            return col_lower[p]
    for c in columns:
        if any(k in c.lower() for k in ["name", "label", "type", "cat", "reg"]):
            return c
    return columns[0] if columns else None