DASHBOARD_CSS = """
<style>
:root {
  --bg: #0f1419;
  --panel: #171d25;
  --panel-2: #1d2530;
  --text: #e8edf2;
  --muted: #9aa7b5;
  --accent: #4f8cff;
  --accent-2: #7c5cff;
  --ok: #2ecc71;
  --warn: #f4b942;
  --bad: #ff6b6b;
  --border: rgba(255,255,255,0.08);
}
.stApp {
  background: linear-gradient(180deg, #0b1015 0%, #111821 100%);
  color: var(--text);
}
.block-container {
  padding-top: 1.25rem;
  max-width: 1280px;
}
.hero {
  background: linear-gradient(135deg, rgba(79,140,255,0.18), rgba(124,92,255,0.14));
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}
.hero h1 {
  font-size: 1.9rem;
  margin: 0 0 0.35rem 0;
}
.hero p {
  color: var(--muted);
  margin: 0;
}
.metric-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 0.9rem 1rem;
}
.metric-label {
  color: var(--muted);
  font-size: 0.82rem;
  margin-bottom: 0.25rem;
}
.metric-value {
  font-size: 1.55rem;
  font-weight: 700;
}
.section-title {
  font-size: 1.05rem;
  font-weight: 700;
  margin: 1.2rem 0 0.6rem 0;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1rem 1.1rem;
}
.badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  border: 1px solid var(--border);
  background: var(--panel-2);
  margin-right: 0.35rem;
}
.badge.ok { color: var(--ok); }
.badge.warn { color: var(--warn); }
.badge.bad { color: var(--bad); }
.guide-step {
  background: var(--panel-2);
  border-left: 3px solid var(--accent);
  border-radius: 10px;
  padding: 0.8rem 0.95rem;
  margin-bottom: 0.65rem;
}
.stButton > button {
  border-radius: 12px;
  border: 1px solid var(--border);
  background: linear-gradient(135deg, #2f5fd0, #5a49d4);
  color: white;
  font-weight: 600;
}
.stTabs [data-baseweb="tab-list"] {
  gap: 0.35rem;
}
.stTabs [data-baseweb="tab"] {
  background: var(--panel);
  border-radius: 12px 12px 0 0;
  border: 1px solid var(--border);
  padding: 0.55rem 0.9rem;
}
</style>
"""
