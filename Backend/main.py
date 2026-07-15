"""
main.py - FastAPI backend
Pipeline: Question -> SQL generation -> DuckDB -> anomaly detection -> insights -> chart config
"""

import os
import re
import tempfile
import time
from typing import Optional

import anthropic
import duckdb
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from anomaly_detector import detect_anomalies
from chart_recommender import recommend_chart
from insight_generator import generate_insights
from sql_safety import validate_read_sql as validate_safe_read_sql
from xai_client import AnthropicConfigError, chat_completion

load_dotenv()

app = FastAPI(title="AI Data Analyst Agent", version="1.0.0")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_QUERY_ROWS = int(os.getenv("MAX_QUERY_ROWS", "500"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    REQUEST_METRICS["requests"] += 1
    REQUEST_METRICS["total_latency_ms"] += (time.perf_counter() - started) * 1000
    if response.status_code >= 400:
        REQUEST_METRICS["query_errors"] += 1
    return response

DB_PATH = os.getenv("DB_PATH", "data/analytics.duckdb")

REQUEST_METRICS = {"requests": 0, "analyses": 0, "uploads": 0, "query_errors": 0, "total_latency_ms": 0.0}

class AnalysisRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    max_rows: int = Field(default=MAX_QUERY_ROWS, ge=1, le=MAX_QUERY_ROWS)


class AnalysisResponse(BaseModel):
    sql: str
    data: list
    columns: list
    chart_config: dict
    anomalies: list
    insights: list
    summary: str


def get_db():
    return duckdb.connect(DB_PATH)


def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Enable shared-key protection by setting API_ACCESS_KEY in deployment."""
    expected = os.getenv("API_ACCESS_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def validate_read_sql(sql: str) -> str:
    """Translate pure SQL validation failures into a safe API response."""
    try:
        return validate_safe_read_sql(sql)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def database_schema_context() -> str:
    """Build a live schema summary so uploaded CSV tables are queryable by the agent."""
    con = get_db()
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        parts = []
        for (table,) in tables[:25]:
            columns = con.execute(f'DESCRIBE "{table}"').fetchall()
            rendered = ", ".join(f"{name} {data_type}" for name, data_type, *_ in columns[:50])
            parts.append(f"- {table}({rendered})")
        return "\n".join(parts)
    finally:
        con.close()


def init_database():
    os.makedirs("data", exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            date        DATE,
            customer_id VARCHAR,
            product_id  VARCHAR,
            product     VARCHAR,
            category    VARCHAR,
            region      VARCHAR,
            revenue     DECIMAL(12,2),
            units       INTEGER,
            cost        DECIMAL(12,2)
        )
        """
    )
    # Lightweight forward migration for databases created by earlier versions.
    existing = {row[0] for row in con.execute("DESCRIBE sales").fetchall()}
    if "customer_id" not in existing:
        con.execute("ALTER TABLE sales ADD COLUMN customer_id VARCHAR")
        con.execute("UPDATE sales SET customer_id = 'C' || lpad(CAST((rowid % 3000) + 1 AS VARCHAR), 5, '0')")
    if "product_id" not in existing:
        con.execute("ALTER TABLE sales ADD COLUMN product_id VARCHAR")
        con.execute("UPDATE sales SET product_id = lower(replace(product, ' ', '_'))")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id  VARCHAR,
            name         VARCHAR,
            segment      VARCHAR,
            region       VARCHAR,
            acq_date     DATE,
            lifetime_val DECIMAL(12,2)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id  VARCHAR,
            name        VARCHAR,
            category    VARCHAR,
            price       DECIMAL(10,2),
            cost        DECIMAL(10,2),
            launch_date DATE
        )
        """
    )
    count = con.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    if count == 0:
        from seed_data import seed_all

        seed_all(con)
        print("Database seeded")
    con.close()
    print("Database ready")


def generate_sql(question: str) -> str:
    """Use Claude/Anthropic to generate SQL for the question."""

    schema = database_schema_context()
    context = """Data context: seeded retail data covers 2023-2024. Regions: North, South, East, West.
    Categories: Electronics, Apparel, Home, Sports. sales.customer_id joins customers.customer_id;
    sales.product_id joins products.product_id. Q3 2023 contains a simulated Electronics supply-chain disruption.
    Uploaded CSV tables may also appear in the schema."""

    sql = chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert DuckDB SQL analyst.\n"
                    "Return ONLY a valid DuckDB SELECT query - no explanation, no markdown, no backticks.\n"
                    "Use DuckDB syntax: DATE_TRUNC(), strftime(), QUALIFY, window functions like LAG() OVER().\n"
                    "Always include meaningful aggregations. Make queries useful for charting. "
                    "Never mutate data or use external file/database commands."
                ),
            },
            {
                "role": "user",
                "content": f"Schema:\n{schema}\n\n{context}\n\nQuestion: {question}",
            },
        ],
        max_tokens=600,
        temperature=0.1,
    )
    sql = re.sub(r"```sql|```", "", sql).strip()
    return sql


def repair_sql(question: str, sql: str, error_message: str) -> str:
    """Ask Claude to fix a broken DuckDB query using the DB error message."""
    fixed_sql = chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You fix invalid DuckDB SQL queries.\n"
                    "Return ONLY a corrected DuckDB SELECT query.\n"
                    "Do not include markdown, comments, or explanations.\n"
                    "Preserve the user's intent while fixing invalid references, aliases, CTE outputs, and syntax."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original question:\n{question}\n\n"
                    f"Broken SQL:\n{sql}\n\n"
                    f"DuckDB error:\n{error_message}\n\n"
                    "Return a corrected DuckDB SELECT query only."
                ),
            },
        ],
        max_tokens=700,
        temperature=0.0,
    )
    return re.sub(r"```sql|```", "", fixed_sql).strip()


def run_sql(sql: str, max_rows: int = 500):
    con = get_db()
    try:
        clean_sql = validate_read_sql(sql)
        bounded_rows = min(max(1, max_rows), MAX_QUERY_ROWS)
        result = con.execute(f"SELECT * FROM ({clean_sql}) AS analysis_result LIMIT {bounded_rows}")
        columns = [desc[0] for desc in result.description]
        tuples = result.fetchall()
        rows = []
        for values in tuples:
            row = {}
            for key, value in zip(columns, values):
                if hasattr(value, "item"):
                    value = value.item()
                elif hasattr(value, "isoformat"):
                    value = value.isoformat()
                elif value != value:
                    value = None
                row[key] = value
            rows.append(row)
        return rows, columns
    finally:
        con.close()


@app.on_event("startup")
async def startup():
    init_database()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics", dependencies=[Depends(require_api_key)])
async def metrics():
    """Small dependency-free operational counters for local monitoring."""
    average_latency = REQUEST_METRICS["total_latency_ms"] / max(REQUEST_METRICS["requests"], 1)
    return {**REQUEST_METRICS, "avg_latency_ms": round(average_latency, 2), "max_query_rows": MAX_QUERY_ROWS, "max_upload_bytes": MAX_UPLOAD_BYTES}


@app.get("/schema", dependencies=[Depends(require_api_key)])
async def get_schema():
    con = get_db()
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        schema = {}
        for (table,) in tables:
            cols = con.execute(f"DESCRIBE {table}").fetchall()
            schema[table] = [{"name": col[0], "type": col[1]} for col in cols]
        return schema
    finally:
        con.close()


@app.post("/analyze", response_model=AnalysisResponse, dependencies=[Depends(require_api_key)])
async def analyze(req: AnalysisRequest):
    try:
        REQUEST_METRICS["analyses"] += 1
        sql = generate_sql(req.question)
        try:
            rows, columns = run_sql(sql, req.max_rows)
        except duckdb.Error as exc:
            sql = repair_sql(req.question, sql, str(exc))
            rows, columns = run_sql(sql, req.max_rows)
        if not rows:
            raise HTTPException(status_code=404, detail="Query returned no results.")

        anomalies = detect_anomalies(rows, columns)
        insights = await generate_insights(req.question, rows, columns, anomalies)
        chart_config = recommend_chart(req.question, rows, columns)
        summary = insights[0]["text"] if insights else "Analysis complete."

        return AnalysisResponse(
            sql=sql,
            data=rows,
            columns=columns,
            chart_config=chart_config,
            anomalies=anomalies,
            insights=insights,
            summary=summary,
        )
    except HTTPException:
        raise
    except AnthropicConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Anthropic API error: {exc.message}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/upload", dependencies=[Depends(require_api_key)])
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    raw = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(file.filename)[0]).strip("_") or "uploaded"
    if raw[0].isdigit():
        raw = "t_" + raw
    table_name = raw

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"CSV exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
        f.write(content)
        tmp_path = f.name

    try:
        REQUEST_METRICS["uploads"] += 1
        safe_path = tmp_path.replace("\\", "/")
        con = get_db()
        try:
            con.execute(
                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto('{safe_path}')"
            )
            cols = con.execute(f"DESCRIBE {table_name}").fetchall()
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not parse CSV: {exc}")
        finally:
            con.close()
        return {"table": table_name, "columns": [{"name": c[0], "type": c[1]} for c in cols]}
    finally:
        os.unlink(tmp_path)


@app.post("/query", dependencies=[Depends(require_api_key)])
async def raw_query(body: dict):
    sql = body.get("sql", "").strip()
    validate_read_sql(sql)
    rows, columns = run_sql(sql)
    return {"data": rows, "columns": columns, "row_count": len(rows)}
