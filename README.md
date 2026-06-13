# 📊 Insight Engine — Autonomous Data Analysis Agent

> Drop in a dataset. Ask a business question in plain English. Watch the agent
> **write code, run it, fix its own errors, chart the answer, and explain what
> it means** — with the limitations stated honestly.

Assignment 9 (Data AI). A conversational data-analysis agent that lets any
business user get a rigorous, defensible answer without writing SQL or Python.

![flow](https://img.shields.io/badge/profile→plan→code→execute→visualize→explain-7c5cff)

---

## ✨ What it does

| Core feature | How it's implemented |
|---|---|
| **Data ingestion** | CSV, TSV, Excel (multi-sheet), JSON, and **SQLite** (`.db`/`.sqlite`, multi-table → exposed as `tables['name']`). |
| **Automatic profiling** | Schema, dtypes, semantic types, null rates, value distributions, IQR outliers, duplicates, and a quality flag list — computed on upload. |
| **Natural-language query** | Plain-English questions → Claude plans the analytical operation (aggregation, filtering, grouping, trend, correlation, segmentation). |
| **Code generation & execution** | Claude writes pandas/Plotly code; it runs in a **restricted sandbox**; on failure the error is fed back and the code is **rewritten automatically** (up to 3 attempts). |
| **Visualization** | Interactive Plotly charts — the agent picks the right type (bar/line/scatter/histogram/heatmap), with title, labelled axes, and a plain-English caption. |
| **Findings narrative** | Key insight, what it means, **honest limitations & uncertainty**, and suggested follow-up questions. |
| **Analysis history** | Every question, code, and result is kept in the session; follow-up questions **build on earlier analyses** (click a suggested follow-up to continue the thread). |

The whole run is **streamed live** to the UI over Server-Sent Events, so you
literally watch the agent think → write code → execute → self-repair → chart →
explain.

---

## 🧰 Tech stack (deliberately simple)

- **Backend:** Python + FastAPI (one language, no build step)
- **Brain:** Claude **`claude-opus-4-8`** via the official `anthropic` SDK, with adaptive thinking
- **Data:** pandas + numpy
- **Charts:** Plotly (interactive, rendered in the browser)
- **Frontend:** a single static HTML/CSS/JS page (Plotly, highlight.js, marked via CDN) — no framework, no bundler

---

## 🚀 Quickstart

```bash
# 1. add your key
cp .env.example .env        # then edit .env and paste your ANTHROPIC_API_KEY

# 2. run (creates a venv, installs deps, generates sample data, starts server)
./run.sh
```

Open **http://127.0.0.1:8000**, click **“✦ Try sample data”** (or drop your own
file), and ask away.

<details>
<summary>Manual setup (instead of <code>run.sh</code>)</summary>

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python generate_sample.py
export ANTHROPIC_API_KEY=sk-ant-...
./.venv/bin/uvicorn app.main:app --reload --port 8000
```
</details>

> Uploading and profiling work **without** a key — you only need the key to ask
> questions (the LLM step).

---

## 💬 Five business questions to try (on the sample data)

The bundled `sample_data/superstore_sales.csv` (2,400 orders, 2 years) is built
to support diverse analyses:

1. *How has total sales trended over time?* → time-series / line chart
2. *Which region is the most profitable?* → grouping + comparison / bar chart
3. *Is there a relationship between discount and profit?* → correlation / scatter
4. *Compare sales across customer segments.* → segmentation
5. *What are the biggest anomalies or data-quality issues?* → distribution + caveats

Then ask a **follow-up** like *“break that down by category”* — it reuses the
prior analysis as context.

---

## 🏗️ How it works

```
Upload → ingestion.py ─┐
                       ├─ profiler.py ─→ schema, types, nulls, anomalies (shown in UI)
                       └─ session.py  ─→ keeps df + history

Ask ──→ agent.run_analysis()  (a generator streamed as SSE)
        1. build prompt: profile + sample rows + prior analyses + question
        2. llm.call → PLAN + Python   (adaptive thinking; reasoning surfaced)
        3. executor.execute → restricted sandbox, capture stdout + Plotly fig
        4. on error → feed traceback back to the model → rewrite → retry (×3)
        5. llm.call → findings JSON (insight, meaning, limitations, follow-ups)
        6. record in history
```

Key files:

| File | Responsibility |
|---|---|
| `app/main.py` | FastAPI routes (`/api/upload`, `/api/sample`, `/api/ask` SSE) |
| `app/agent.py` | The autonomous loop (plan → code → execute → repair → narrate) |
| `app/llm.py` | Anthropic SDK wrapper (adaptive thinking + graceful fallback) |
| `app/prompts.py` | System prompts, profile rendering, narrative parsing |
| `app/profiler.py` | Automatic data profiling (JSON-safe) |
| `app/executor.py` | Sandboxed code execution with timeout |
| `app/ingestion.py` | CSV / Excel / JSON / SQLite loaders |
| `static/*` | The single-page UI |

---

## 🔒 Sandbox & security

Generated code runs with a **restricted `__builtins__`** and an **import
allow-list** (pandas, numpy, plotly, math, datetime, … only — no `os`, `sys`,
`open`, network, or subprocess), on a worker thread with a hard **timeout**.

This is defence-in-depth for a **local, single-user** tool — not a hardened
multi-tenant sandbox. Run it on data and in an environment you trust. For
production-grade isolation you'd move execution into a container/VM or
Anthropic's server-side code-execution tool.

---

## ⚙️ Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Your Claude API key (required to ask questions) |
| `ANALYST_MODEL` | `claude-opus-4-8` | Model id (e.g. `claude-sonnet-4-6` for lower cost) |
| `ANALYST_MAX_FIX_ATTEMPTS` | `3` | Max automatic code-repair retries |
| `ANALYST_EXEC_TIMEOUT` | `30` | Per-execution timeout (seconds) |

---

## ✅ Success metrics — how this project meets them

- **Answers diverse business questions** — aggregation, trend, correlation, segmentation all supported via generated pandas.
- **Errors caught & corrected without user intervention** — the execute→repair loop (verified to recover from a `KeyError` automatically).
- **Appropriate chart types** — the agent is prompted to match chart to question; charts carry titles, axis labels, and captions.
- **Findings identify the key insight + limitations** — every answer separates the headline insight from honest caveats and uncertainty.
- **Iterative questions build on context** — prior questions, insights, and code are fed into each follow-up.
