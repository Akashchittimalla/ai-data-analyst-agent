import { useState, useEffect, useRef } from "react";

// ── Config ─────────────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const COLORS = ["#7c6aff", "#34d399", "#60a5fa", "#fbbf24", "#f87171", "#a78bfa", "#fb923c"];

const EXAMPLES = [
  "Why did sales drop in Q3 2023?",
  "Which product categories drive the most revenue?",
  "Compare regional performance across all quarters",
  "Show month-over-month revenue growth trend",
  "What are the top 5 products by total revenue?",
  "Identify anomalies in our sales data",
  "Which region has the highest average order value?",
  "How does Electronics compare to Apparel revenue?",
];

const PROCESSING_STEPS = [
  "Parsing your question...",
  "Generating SQL with Claude...",
  "Executing on DuckDB...",
  "Running anomaly detection...",
  "Generating insights with Claude...",
  "Building chart configuration...",
];

// ── API ────────────────────────────────────────────────────────────────────────
async function apiAnalyze(question) {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, max_rows: 500 }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || "Analysis failed");
  }
  return res.json();
}

async function apiSchema() {
  const res = await fetch(`${API_BASE}/schema`);
  return res.json();
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function fmtVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (Math.abs(v) >= 1_000_000) return "$" + (v / 1_000_000).toFixed(1) + "M";
    if (Math.abs(v) >= 1_000)     return "$" + (v / 1_000).toFixed(1) + "K";
    if (Number.isInteger(v))      return v.toLocaleString();
    return v.toFixed(2);
  }
  return String(v);
}

function highlightSQL(sql) {
  return sql
    .replace(/\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|JOIN|LEFT|RIGHT|INNER|ON|AS|AND|OR|IN|NOT|NULL|OVER|BY|PARTITION|DATE_TRUNC|DATE_PART|strftime|LAG|LEAD|SUM|COUNT|ROUND|AVG|MAX|MIN|DISTINCT|WITH|UNION|LIMIT|CASE|WHEN|THEN|ELSE|END|QUALIFY|ROW_NUMBER)\b/g,
      '<span style="color:#ff7b72;font-weight:500">$1</span>')
    .replace(/\b(\d[\d.,]*)\b/g, '<span style="color:#79c0ff">$1</span>')
    .replace(/'([^']*)'/g, '<span style="color:#a5d6ff">\'$1\'</span>')
    .replace(/--.*/g, '<span style="color:#6e7681;font-style:italic">$&</span>');
}

// ── Chart Component ────────────────────────────────────────────────────────────
function DataChart({ config, data }) {
  const ref   = useRef(null);
  const chart = useRef(null);

  useEffect(() => {
    if (!ref.current || !data?.length || !window.Chart) return;
    chart.current?.destroy();

    const ctx = ref.current.getContext("2d");
    const { type, x_col, y_cols = [], group_col, stacked, horizontal } = config;
    const isNumeric = (v) => typeof v === "number";

    const tickFmt = (v) =>
      Math.abs(v) >= 1000 ? "$" + (v / 1000).toFixed(0) + "K" : v;

    const axisStyle = {
      grid: { color: "rgba(255,255,255,0.05)" },
      ticks: { color: "#6b7280", font: { family: "JetBrains Mono", size: 11 } },
    };

    let cfg;

    // Doughnut
    if (type === "doughnut") {
      cfg = {
        type: "doughnut",
        data: {
          labels: data.map((r) => r[x_col]),
          datasets: [{
            data: data.map((r) => r[y_cols[0]]),
            backgroundColor: COLORS,
            borderWidth: 2,
            borderColor: "#16181c",
            hoverOffset: 8,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: "65%",
          plugins: {
            legend: {
              position: "right",
              labels: { color: "#9ca3af", font: { family: "DM Sans", size: 12 }, boxWidth: 10, padding: 14 },
            },
          },
        },
      };
    }

    // Multi-line (grouped)
    else if ((type === "line" || type === "area") && group_col) {
      const groups  = [...new Set(data.map((r) => r[group_col]))];
      const xLabels = [...new Set(data.map((r) => String(r[x_col])))];
      cfg = {
        type: "line",
        data: {
          labels: xLabels,
          datasets: groups.map((g, i) => ({
            label: String(g),
            data: xLabels.map((xl) => {
              const row = data.find((r) => String(r[x_col]) === xl && r[group_col] === g);
              return row ? row[y_cols[0]] : null;
            }),
            borderColor: COLORS[i % COLORS.length],
            backgroundColor: COLORS[i % COLORS.length] + "20",
            borderWidth: 2, pointRadius: 4, tension: 0.35,
            fill: type === "area",
          })),
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#9ca3af", font: { family: "DM Sans", size: 11 }, boxWidth: 10, padding: 10 } } },
          scales: { x: axisStyle, y: { ...axisStyle, stacked, ticks: { ...axisStyle.ticks, callback: tickFmt } } },
        },
      };
    }

    // Line / Area (single series)
    else if (type === "line" || type === "area") {
      cfg = {
        type: "line",
        data: {
          labels: data.map((r) => String(r[x_col])),
          datasets: y_cols.map((col, i) => ({
            label: col,
            data: data.map((r) => r[col]),
            borderColor: COLORS[i],
            backgroundColor: COLORS[i] + "25",
            borderWidth: 2, pointRadius: 4, tension: 0.35,
            fill: type === "area",
          })),
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: "#9ca3af", font: { family: "DM Sans", size: 11 }, boxWidth: 10 } } },
          scales: { x: axisStyle, y: { ...axisStyle, ticks: { ...axisStyle.ticks, callback: tickFmt } } },
        },
      };
    }

    // Bar (vertical or horizontal)
    else {
      cfg = {
        type: "bar",
        data: {
          labels: data.map((r) => String(r[x_col])),
          datasets: y_cols.map((col, i) => ({
            label: col,
            data: data.map((r) => r[col]),
            backgroundColor: COLORS[i % COLORS.length],
            borderRadius: horizontal ? 3 : 5,
            borderSkipped: false,
          })),
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          indexAxis: horizontal ? "y" : "x",
          plugins: { legend: { display: y_cols.length > 1, labels: { color: "#9ca3af", font: { family: "DM Sans", size: 11 }, boxWidth: 10 } } },
          scales: {
            x: { ...axisStyle, stacked, ticks: { ...axisStyle.ticks, callback: horizontal ? undefined : tickFmt } },
            y: { ...axisStyle, stacked, ticks: { ...axisStyle.ticks, callback: horizontal ? undefined : tickFmt } },
          },
        },
      };
    }

    chart.current = new window.Chart(ctx, cfg);
    return () => chart.current?.destroy();
  }, [config, data]);

  return (
    <div style={{ position: "relative", width: "100%", height: 300 }}>
      <canvas ref={ref} />
    </div>
  );
}

// ── SQL Block ──────────────────────────────────────────────────────────────────
function SQLBlock({ sql }) {
  const [copied, setCopied] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => { navigator.clipboard.writeText(sql); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
        style={{ position: "absolute", top: 10, right: 12, background: "rgba(255,255,255,0.07)", border: "0.5px solid rgba(255,255,255,0.12)", borderRadius: 6, color: "#9ca3af", fontSize: 11, padding: "3px 8px", cursor: "pointer" }}
      >
        {copied ? "✓ copied" : "copy"}
      </button>
      <pre
        dangerouslySetInnerHTML={{ __html: highlightSQL(sql) }}
        style={{ padding: "14px 16px", fontFamily: "JetBrains Mono, monospace", fontSize: 12, lineHeight: 1.8, color: "#c9d1d9", background: "#0d1117", overflowX: "auto", margin: 0, whiteSpace: "pre-wrap" }}
      />
    </div>
  );
}

// ── Data Table ─────────────────────────────────────────────────────────────────
function DataTable({ rows, columns }) {
  if (!rows?.length) return <p style={{ padding: 20, color: "#6b7280", fontSize: 13 }}>No data</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: "JetBrains Mono, monospace" }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} style={{ textAlign: "left", padding: "8px 14px", color: "#6b7280", fontSize: 11, fontWeight: 400, borderBottom: "0.5px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c} style={{ padding: "7px 14px", color: typeof row[c] === "number" ? "#60a5fa" : "#e8e9eb", borderBottom: "0.5px solid rgba(255,255,255,0.03)" }}>
                  {fmtVal(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 50 && (
        <p style={{ padding: "8px 14px", fontSize: 11, color: "#6b7280" }}>Showing 50 of {rows.length} rows</p>
      )}
    </div>
  );
}

// ── Insights Panel ─────────────────────────────────────────────────────────────
function InsightsPanel({ insights, anomalies }) {
  const colors = {
    negative:       { bg: "rgba(248,113,113,0.08)", border: "rgba(248,113,113,0.2)",  icon: "rgba(248,113,113,0.15)" },
    positive:       { bg: "rgba(52,211,153,0.08)",  border: "rgba(52,211,153,0.2)",   icon: "rgba(52,211,153,0.15)" },
    warning:        { bg: "rgba(251,191,36,0.08)",  border: "rgba(251,191,36,0.2)",   icon: "rgba(251,191,36,0.15)" },
    recommendation: { bg: "rgba(124,106,255,0.08)", border: "rgba(124,106,255,0.2)",  icon: "rgba(124,106,255,0.15)" },
  };

  return (
    <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      {insights?.map((ins, i) => {
        const c = colors[ins.type] || colors.positive;
        return (
          <div key={i} style={{ display: "flex", gap: 12, padding: "12px 14px", background: c.bg, border: `0.5px solid ${c.border}`, borderRadius: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: c.icon, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, flexShrink: 0 }}>
              {ins.icon}
            </div>
            <div>
              <div style={{ fontWeight: 500, fontSize: 13, color: "#e8e9eb", marginBottom: 3 }}>{ins.title}</div>
              <div style={{ fontSize: 13, color: "#9ca3af", lineHeight: 1.65 }}>{ins.text}</div>
            </div>
          </div>
        );
      })}

      {anomalies?.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <p style={{ fontSize: 11, color: "#6b7280", letterSpacing: "0.4px", marginBottom: 8, textTransform: "uppercase" }}>Detected Anomalies</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {anomalies.map((a, i) => (
              <span key={i} style={{
                padding: "4px 10px", borderRadius: 20, fontSize: 11,
                fontFamily: "JetBrains Mono, monospace",
                color: a.type === "critical" ? "#f87171" : a.type === "warning" ? "#fbbf24" : "#60a5fa",
                background: a.type === "critical" ? "rgba(248,113,113,0.08)" : a.type === "warning" ? "rgba(251,191,36,0.08)" : "rgba(96,165,250,0.08)",
                border: `0.5px solid ${a.type === "critical" ? "rgba(248,113,113,0.3)" : a.type === "warning" ? "rgba(251,191,36,0.3)" : "rgba(96,165,250,0.3)"}`,
              }}>
                {a.label}: {a.pct_diff > 0 ? "+" : ""}{a.pct_diff}% vs avg
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Schema Panel ───────────────────────────────────────────────────────────────
function SchemaPanel({ schema }) {
  if (!schema) return <p style={{ padding: 14, color: "#6b7280", fontSize: 12 }}>Loading...</p>;
  return (
    <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 14 }}>
      {Object.entries(schema).map(([table, cols]) => (
        <div key={table}>
          <p style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#a78bfa", marginBottom: 5 }}>
            ▸ {table}
          </p>
          <div style={{ paddingLeft: 12, display: "flex", flexDirection: "column", gap: 3 }}>
            {cols.map((c) => (
              <div key={c.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
                <span style={{ color: "#6b7280" }}>{c.name}</span>
                <span style={{ color: "#3b82f6", opacity: 0.8 }}>{c.type}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Panel Wrapper ──────────────────────────────────────────────────────────────
function Panel({ children, style }) {
  return (
    <div style={{ background: "#16181c", border: "0.5px solid rgba(255,255,255,0.07)", borderRadius: 12, overflow: "hidden", ...style }}>
      {children}
    </div>
  );
}

function PanelHeader({ icon, label, iconBg, iconColor }) {
  return (
    <div style={{ padding: "10px 14px", borderBottom: "0.5px solid rgba(255,255,255,0.07)", display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 20, height: 20, borderRadius: 5, background: iconBg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, color: iconColor }}>
        {icon}
      </div>
      <span style={{ fontSize: 12, fontWeight: 500 }}>{label}</span>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────────
export default function App() {
  const [question,  setQuestion]  = useState("");
  const [loading,   setLoading]   = useState(false);
  const [result,    setResult]    = useState(null);
  const [error,     setError]     = useState(null);
  const [tab,       setTab]       = useState("insights");
  const [schema,    setSchema]    = useState(null);
  const [step,      setStep]      = useState(0);

  useEffect(() => { apiSchema().then(setSchema).catch(() => {}); }, []);

  async function runAnalysis() {
    if (!question.trim() || loading) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setStep(0);

    // Animate steps
    for (let i = 0; i < PROCESSING_STEPS.length; i++) {
      setStep(i);
      await new Promise((r) => setTimeout(r, 320));
    }

    try {
      const data = await apiAnalyze(question);
      setResult(data);
      setTab("insights");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  const TABS = [
    { id: "insights", label: "Insights" },
    { id: "chart",    label: "Chart"    },
    { id: "data",     label: "Data"     },
    { id: "sql",      label: "SQL"      },
  ];

  return (
    <div style={{ background: "#0e0f11", color: "#e8e9eb", fontFamily: "DM Sans, sans-serif", minHeight: "100vh", padding: 20 }}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, paddingBottom: 16, borderBottom: "0.5px solid rgba(255,255,255,0.07)", marginBottom: 20 }}>
          <div style={{ width: 32, height: 32, background: "linear-gradient(135deg,#7c6aff,#a78bfa)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>◈</div>
          <div>
            <p style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>AI Data Analyst Agent</p>
            <p style={{ fontSize: 12, color: "#6b7280", margin: 0 }}>Claude · LangChain · DuckDB · FastAPI · React</p>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 20, color: "#34d399", border: "0.5px solid rgba(52,211,153,0.3)", background: "rgba(52,211,153,0.08)" }}>● Live</span>
            <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 20, color: "#a78bfa", border: "0.5px solid rgba(167,139,250,0.3)", background: "rgba(167,139,250,0.08)" }}>Claude-powered</span>
          </div>
        </div>

        {/* ── Layout ── */}
        <div style={{ display: "grid", gridTemplateColumns: "290px 1fr", gap: 16, alignItems: "start" }}>

          {/* ── Sidebar ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Panel>
              <PanelHeader icon="⊞" label="Database Schema" iconBg="rgba(96,165,250,0.12)" iconColor="#60a5fa" />
              <SchemaPanel schema={schema} />
            </Panel>

            <Panel>
              <PanelHeader icon="✦" label="Example Questions" iconBg="rgba(251,191,36,0.12)" iconColor="#fbbf24" />
              <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 5 }}>
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    onClick={() => setQuestion(q)}
                    style={{ padding: "7px 10px", background: "#1e2128", border: "0.5px solid rgba(255,255,255,0.07)", borderRadius: 8, fontSize: 12, color: "#e8e9eb", cursor: "pointer", textAlign: "left", lineHeight: 1.4, fontFamily: "DM Sans, sans-serif", transition: "all 0.15s" }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#7c6aff"; e.currentTarget.style.color = "#a78bfa"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)"; e.currentTarget.style.color = "#e8e9eb"; }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </Panel>
          </div>

          {/* ── Main ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

            {/* Input */}
            <Panel>
              <div style={{ padding: 14, display: "flex", gap: 8, alignItems: "flex-end" }}>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runAnalysis(); } }}
                  placeholder="Ask a business question... e.g. Why did sales drop in Q3?"
                  style={{ flex: 1, background: "#1e2128", border: "0.5px solid rgba(255,255,255,0.12)", borderRadius: 8, color: "#e8e9eb", fontFamily: "DM Sans, sans-serif", fontSize: 13, padding: "10px 12px", resize: "none", outline: "none", minHeight: 44, maxHeight: 120, lineHeight: 1.5 }}
                />
                <button
                  onClick={runAnalysis}
                  disabled={loading || !question.trim()}
                  style={{ height: 44, padding: "0 20px", background: loading ? "#4a3db5" : "#7c6aff", border: "none", borderRadius: 8, color: "#fff", fontFamily: "DM Sans, sans-serif", fontSize: 13, fontWeight: 500, cursor: loading ? "not-allowed" : "pointer", opacity: !question.trim() ? 0.5 : 1, flexShrink: 0, transition: "background 0.2s" }}
                >
                  {loading ? "Analyzing..." : "Analyze →"}
                </button>
              </div>
            </Panel>

            {/* Processing */}
            {loading && (
              <Panel>
                <div style={{ padding: "14px 16px" }}>
                  {PROCESSING_STEPS.map((s, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, marginBottom: 8, color: i < step ? "#34d399" : i === step ? "#e8e9eb" : "#374151", opacity: i > step ? 0.4 : 1, transition: "all 0.3s" }}>
                      <span>{i < step ? "✓" : i === step ? "⟳" : "·"}</span>
                      {s}
                    </div>
                  ))}
                  <div style={{ height: 2, background: "#1e2128", borderRadius: 1, marginTop: 12 }}>
                    <div style={{ height: "100%", background: "#7c6aff", borderRadius: 1, width: `${(step / PROCESSING_STEPS.length) * 100}%`, transition: "width 0.35s ease" }} />
                  </div>
                </div>
              </Panel>
            )}

            {/* Error */}
            {error && (
              <div style={{ padding: "12px 16px", background: "rgba(248,113,113,0.08)", border: "0.5px solid rgba(248,113,113,0.25)", borderRadius: 12, fontSize: 13, color: "#f87171" }}>
                ⚠ {error}
              </div>
            )}

            {/* Results */}
            {result && (
              <Panel>
                {/* Tabs */}
                <div style={{ display: "flex", borderBottom: "0.5px solid rgba(255,255,255,0.07)" }}>
                  {TABS.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setTab(t.id)}
                      style={{ padding: "10px 16px", fontSize: 12, fontWeight: 500, color: tab === t.id ? "#a78bfa" : "#6b7280", background: "none", border: "none", cursor: "pointer", borderBottom: `2px solid ${tab === t.id ? "#7c6aff" : "transparent"}`, fontFamily: "DM Sans, sans-serif", transition: "all 0.15s", marginBottom: -0.5 }}
                    >
                      {t.label}
                    </button>
                  ))}
                  <div style={{ marginLeft: "auto", padding: "8px 14px", fontSize: 11, color: "#6b7280", display: "flex", alignItems: "center" }}>
                    {result.data.length} rows
                  </div>
                </div>

                {tab === "insights" && <InsightsPanel insights={result.insights} anomalies={result.anomalies} />}
                {tab === "chart"    && <div style={{ padding: 16 }}><DataChart config={result.chart_config} data={result.data} /></div>}
                {tab === "data"     && <DataTable rows={result.data} columns={result.columns} />}
                {tab === "sql"      && <SQLBlock sql={result.sql} />}
              </Panel>
            )}

            {/* Empty state */}
            {!loading && !result && !error && (
              <Panel>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "48px 24px", gap: 12, color: "#6b7280", textAlign: "center" }}>
                  <div style={{ fontSize: 36, opacity: 0.25 }}>◈</div>
                  <p style={{ fontSize: 13, lineHeight: 1.7, maxWidth: 320, margin: 0 }}>
                    Ask a business question above. The agent generates SQL, executes it on DuckDB, detects anomalies, and explains findings using Grok.
                  </p>
                </div>
              </Panel>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
