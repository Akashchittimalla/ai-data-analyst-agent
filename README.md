# AI Data Analyst Agent

Ask questions in plain English, get SQL-powered analytics with visualizations and AI-generated business insights — all backed by Claude.

## Overview

Type a natural language question (e.g. *"Show me monthly revenue by region for 2023"*) and the agent:

1. Generates a DuckDB SQL query via Claude
2. Executes it against a local analytics database
3. Detects statistical anomalies in the results
4. Produces 4 structured business insights via Claude
5. Renders an appropriate Chart.js visualization

## Architecture

```
Browser (React + Vite)
    │
    ▼
FastAPI (Python)
    ├── Claude API  ──► SQL generation + repair
    ├── DuckDB      ──► Query execution (sales / customers / products)
    ├── Anomaly detector (Z-score, IQR)
    ├── Claude API  ──► Business insights
    └── Chart recommender ──► Chart.js config
```

**Stack**

| Layer | Technology |
|-------|------------|
| Frontend | React 18, Vite 5, Chart.js |
| Backend | Python 3.11, FastAPI, Uvicorn |
| Database | DuckDB (embedded, no server needed) |
| AI | Anthropic Claude (`claude-haiku-4-5-20251001` by default) |
| Deployment | Docker + docker-compose |

## Quick Start

### Local (without Docker)

**Backend**

```bash
cd Backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Add your API key to Backend/.env
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

uvicorn main:app --reload --port 8000
```

**Frontend**

```bash
cd Frontend
npm install
npm run dev        # http://localhost:5173
```

### Docker

```bash
# Set your API key, then launch both services
ANTHROPIC_API_KEY=sk-ant-... docker compose -f Root/docker-compose.yml up --build
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-haiku-4-5-20251001` | Override the Claude model |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Comma-separated browser origins allowed to call the API |
| `API_ACCESS_KEY` | No | — | Shared API key required through `X-API-Key`; suitable for internal deployments |
| `MAX_UPLOAD_BYTES` | No | `10485760` | Maximum CSV upload size (10 MB) |
| `MAX_QUERY_ROWS` | No | `500` | Maximum rows returned by an analysis/query |

Set these in `Backend/.env` for local development.

Never commit a real API key. The included `.gitignore` excludes `.env` files; use
`Backend/.env.example` as the safe template. If `API_ACCESS_KEY` is enabled, set
the same value as `VITE_API_KEY` for the bundled frontend. This is appropriate
for a private/internal tool, but a public deployment should use real user
authentication (for example OAuth/OIDC with server-side sessions) rather than a
browser-visible shared key.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/metrics` | Request/error/latency counters (requires API key when configured) |
| `GET` | `/schema` | Returns table schemas |
| `POST` | `/analyze` | Main analysis pipeline |
| `POST` | `/query` | Run one validated, read-only SELECT/CTE query |
| `POST` | `/upload` | Load a size-limited CSV as a DuckDB table |

### POST /analyze

**Request**
```json
{
  "question": "Show monthly revenue by category in 2023",
  "max_rows": 500
}
```

**Response**
```json
{
  "sql": "SELECT DATE_TRUNC('month', date) AS month, ...",
  "data": [...],
  "columns": ["month", "category", "revenue"],
  "chart_config": { "type": "bar", "data": {...}, "options": {...} },
  "anomalies": [{ "column": "revenue", "message": "Spike detected in October" }],
  "insights": [
    { "icon": "📉", "type": "negative", "title": "Q3 Revenue Dropped 22%", "text": "..." },
    ...
  ],
  "summary": "..."
}
```

## Sample Questions

- *"What were the top 5 products by revenue last year?"*
- *"Compare regional sales performance across all quarters"*
- *"Which customer segment has the highest lifetime value?"*
- *"Show the revenue trend for Electronics in 2023"*

## Database Schema

The app seeds a DuckDB database with synthetic 2023–2024 retail data on first run.

| Table | Key Columns |
|-------|-------------|
| `sales` | date, customer_id, product_id, product, category, region, revenue, units, cost |
| `customers` | customer_id, name, segment, region, acq_date, lifetime_val |
| `products` | product_id, name, category, price, cost, launch_date |

Regions: North, South, East, West  
Categories: Electronics, Apparel, Home, Sports

`sales.customer_id` joins `customers.customer_id`, and `sales.product_id` joins
`products.product_id`, enabling cross-table customer and product analysis. CSV
tables uploaded through the UI are included automatically in the live schema
given to the SQL-generation model.

## Reliability and security notes

- Generated and raw queries are limited to one read-only `SELECT` or CTE statement; mutation, file, extension, and admin keywords are rejected.
- Results and uploads have configurable limits to protect local resources.
- CORS defaults to the local Vite origin instead of accepting every website.
- The `/metrics` endpoint exposes dependency-free request count, error count, and average-latency counters for basic monitoring.
- Run the regression suite with `cd Backend` then `python -m unittest discover -s tests`.
