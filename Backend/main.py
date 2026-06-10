"""
main.py - FastAPI backend
Pipeline: Question -> SQL generation -> DuckDB -> anomaly detection -> insights -> chart config
"""

import os
import re
import tempfile
from typing import Optional

import anthropic
import duckdb
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from anomaly_detector import detect_anomalies
from chart_recommender import recommend_chart
from insight_generator import generate_insights
from xai_client import AnthropicConfigError, chat_completion

load_dotenv()

app = FastAPI(title="AI Data Analyst Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "data/analytics.duckdb"


class AnalysisRequest(BaseModel):
    question: str
    max_rows: Optional[int] = 500


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


def init_database():
    os.makedirs("data", exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            date        DATE,
            product     VARCHAR,
            category    VARCHAR,
            region      VARCHAR,
            revenue     DECIMAL(12,2),
            units       INTEGER,
            cost        DECIMAL(12,2)
        )
        """
    )
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

    schema = """
    Tables:
    - sales(date DATE, product VARCHAR, category VARCHAR, region VARCHAR, revenue DECIMAL, units INTEGER, cost DECIMAL)
    - customers(customer_id VARCHAR, name VARCHAR, segment VARCHAR, region VARCHAR, acq_date DATE, lifetime_val DECIMAL)
    - products(product_id VARCHAR, name VARCHAR, category VARCHAR, price DECIMAL, cost DECIMAL, launch_date DATE)

    Data context: 2023-2024 sales data. Regions: North, South, East, West.
    Categories: Electronics, Apparel, Home, Sports.
    Q3 2023 had a supply chain disruption in Electronics causing ~22% revenue drop.
    """

    sql = chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert DuckDB SQL analyst.\n"
                    "Return ONLY a valid DuckDB SELECT query - no explanation, no markdown, no backticks.\n"
                    "Use DuckDB syntax: DATE_TRUNC(), strftime(), QUALIFY, window functions like LAG() OVER().\n"
                    "Always include meaningful aggregations. Make queries useful for charting."
                ),
            },
            {
                "role": "user",
                "content": f"Schema:\n{schema}\n\nQuestion: {question}",
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
        clean_sql = sql.strip().rstrip(";")
        result = con.execute(clean_sql + f" LIMIT {max_rows}")
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


@app.get("/schema")
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


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(req: AnalysisRequest):
    try:
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


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    raw = re.sub(r"[^a-zA-Z0-9_]", "_", os.path.splitext(file.filename)[0]).strip("_") or "uploaded"
    if raw[0].isdigit():
        raw = "t_" + raw
    table_name = raw

    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
        f.write(content)
        tmp_path = f.name

    try:
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


@app.post("/query")
async def raw_query(body: dict):
    sql = body.get("sql", "").strip()
    if not sql.upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries allowed.")
    rows, columns = run_sql(sql)
    return {"data": rows, "columns": columns, "row_count": len(rows)}
