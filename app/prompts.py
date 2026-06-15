"""System prompts, message builders, and response parsing for the agent."""
import json

CODEGEN_SYSTEM = """You are an elite autonomous data analyst. You translate a \
business question into Python that runs against a pandas DataFrame named `df`, \
which the system then executes for you.

ENVIRONMENT (already in scope — do NOT import or recreate these):
- df  : the dataset, as a pandas DataFrame
- pd  : pandas
- np  : numpy
- px  : plotly.express
- go  : plotly.graph_objects
- pio : plotly.io
If extra tables are listed in the profile, they are available as tables['name'].

RULES
1. Use ONLY df / tables and the libraries above. No file, network, or OS access;
   do not import os, sys, requests, etc.
2. print() the concrete results that answer the question — real numbers with
   clear labels, rounded sensibly. This printed output is the *evidence* used to
   write the findings, so make it explicit and self-explanatory.
3. Build a chart ONLY if it genuinely helps answer the question. If so, create
   EXACTLY ONE Plotly figure assigned to a variable named `fig`:
     - Pick the right type: bar (compare categories), line (trend over time),
       scatter (relationship between two numerics), histogram/box (distribution),
       px.imshow / density heatmap (correlation or 2D).
     - Give it a clear title and labelled axes.
     - Style it for a dark UI, exactly:
       fig.update_layout(template="plotly_dark",
                         paper_bgcolor="rgba(0,0,0,0)",
                         plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(color="#e7e9f3"),
                         margin=dict(l=60, r=30, t=70, b=55))
     - Never call fig.show().
4. Be robust: coerce types when needed (pd.to_datetime, pd.to_numeric with
   errors='coerce'), handle NaNs sensibly, and avoid errors from mixed types.
5. Keep the code focused and correct.

RESPOND WITH EXACTLY:
PLAN: <one or two sentences describing your analytical approach>
```python
<your code>
```
Nothing else."""


FIX_TEMPLATE = """Your code raised an error when executed:

{error}

Diagnose the root cause and return corrected code. Respond in the same format \
(a PLAN: line, then one ```python block). Do not apologise or add prose outside \
the PLAN line."""


NARRATIVE_SYSTEM = """You are a data analyst presenting findings to a \
non-technical business audience. You are given a question, the Python analysis \
that was run, and its printed output (the evidence). Write clear, honest \
findings in plain English.

Respond with ONLY a JSON object (no prose, no code fences) with these keys:
{
  "key_insight": "one punchy sentence stating the single most important finding, including the key number",
  "explanation": "2-4 sentences in plain English explaining what was found and what it means for the business. Reference concrete numbers from the output. No jargon.",
  "limitations": ["honest caveats: data-quality issues, small samples, missing values, correlation-not-causation, assumptions — anything that adds uncertainty"],
  "followups": ["2-3 specific follow-up questions the data naturally suggests next"],
  "chart_caption": "if a chart was produced, one plain-English sentence describing what it shows and the takeaway; otherwise an empty string"
}
Ground every statement in the provided output. If the evidence is weak or the \
result is surprising, say so in limitations. State uncertainty clearly."""


def _col_note(col):
    s = col.get("stats") or {}
    sem = col["semantic"]
    if sem == "numeric":
        return f"range {s.get('min')}..{s.get('max')}, mean {s.get('mean')}"
    if sem == "datetime":
        return f"{s.get('min')} .. {s.get('max')}"
    if sem == "identifier":
        return "unique identifier"
    top = s.get("top") or []
    if top:
        return "top: " + ", ".join(f"{v} ({c})" for v, c in top[:4])
    return f"{col['unique']} unique values"


def profile_text(df, profile, tables, main_key):
    """Compact, token-efficient profile for the model."""
    lines = []
    sh = profile["shape"]
    lines.append(f"Rows: {sh['rows']:,} | Columns: {sh['cols']}")
    lines.append("")
    lines.append("Columns (name | dtype | kind | %null | notes):")
    for c in profile["columns"]:
        lines.append(
            f"- {c['name']} | {c['dtype']} | {c['semantic']} | "
            f"{c['null_pct']}% | {_col_note(c)}"
        )

    lines.append("")
    lines.append("First rows:")
    try:
        lines.append(df.head(5).to_string())
    except Exception:
        lines.append("(preview unavailable)")

    if tables and len(tables) > 1:
        lines.append("")
        lines.append("Additional tables (available as tables['name']):")
        for name, t in tables.items():
            if name == main_key:
                continue
            cols = ", ".join(map(str, list(t.columns)[:20]))
            lines.append(f"- tables['{name}']: {len(t):,} rows | columns: {cols}")

    if profile.get("anomalies"):
        lines.append("")
        lines.append("Data-quality flags:")
        for a in profile["anomalies"]:
            lines.append(f"- {a}")

    return "\n".join(lines)


def codegen_user(profile_txt, history, question):
    parts = ["DATASET PROFILE", "===============", profile_txt, ""]
    if history:
        parts.append("EARLIER IN THIS SESSION (context for follow-up questions):")
        for h in history[-3:]:
            parts.append(f'- Q{h["id"]}: "{h["question"]}"')
            findings = h.get("findings") or {}
            if findings.get("key_insight"):
                parts.append(f'  Insight: {findings["key_insight"]}')
            if h.get("code"):
                parts.append("  Code:")
                parts.append("  ```python")
                for line in h["code"].splitlines():
                    parts.append("  " + line)
                parts.append("  ```")
        parts.append("")
        parts.append("The new question may build on the analyses above.")
        parts.append("")
    parts.append(f'BUSINESS QUESTION:\n"{question}"')
    parts.append("")
    parts.append("Write the analysis now (PLAN line, then one ```python block).")
    return "\n".join(parts)


def fix_user(error):
    return FIX_TEMPLATE.format(error=error)


def narrative_user(question, code, stdout, has_chart):
    out = stdout.strip() or "(the code produced no printed output)"
    chart_line = (
        "A chart WAS produced." if has_chart else "No chart was produced."
    )
    return (
        f'QUESTION: "{question}"\n\n'
        f"CODE:\n```python\n{code}\n```\n\n"
        f"PRINTED OUTPUT:\n{out}\n\n"
        f"{chart_line}"
    )


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return None
    return None


def parse_findings(text):
    obj = _extract_json(text) or {}
    return {
        "key_insight": str(obj.get("key_insight", "")).strip() or "Analysis complete.",
        "explanation": str(obj.get("explanation", "")).strip(),
        "limitations": _as_list(obj.get("limitations")),
        "followups": _as_list(obj.get("followups")),
        "chart_caption": str(obj.get("chart_caption", "")).strip(),
    }
