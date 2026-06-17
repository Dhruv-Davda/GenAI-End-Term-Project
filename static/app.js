"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  sessionId: null,
  profile: null,
  busy: false,
  qCount: 0,
  hasKey: false,
};

/* ------------------------------------------------------------------ init */
document.addEventListener("DOMContentLoaded", () => {
  wireUpload();
  wireComposer();
  health();
});

async function health() {
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    state.hasKey = h.has_api_key;
    $("model-name").textContent = h.model;
    if (!h.has_api_key) {
      $("key-warning").hidden = false;
      document.querySelector(".pulse-dot").classList.add("off");
    }
  } catch {
    $("model-name").textContent = "offline";
    document.querySelector(".pulse-dot").classList.add("off");
  }
}

/* ---------------------------------------------------------------- upload */
function wireUpload() {
  const dz = $("dropzone");
  const input = $("file-input");

  dz.addEventListener("click", () => input.click());
  $("browse-btn").addEventListener("click", () => input.click());
  $("sample-btn").addEventListener("click", loadSample);

  input.addEventListener("change", () => {
    if (input.files.length) uploadFile(input.files[0]);
  });

  ["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => {
      e.preventDefault();
      dz.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => {
      e.preventDefault();
      dz.classList.remove("drag");
    })
  );
  dz.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
  });
}

async function uploadFile(file) {
  setUploading(true, `Reading ${file.name}…`);
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Upload failed");
    onDataset(data);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    setUploading(false);
  }
}

async function loadSample() {
  setUploading(true, "Loading sample…");
  try {
    const r = await fetch("/api/sample", { method: "POST" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Could not load sample");
    onDataset(data);
  } catch (e) {
    toast(e.message, "error");
  } finally {
    setUploading(false);
  }
}

function setUploading(on, msg) {
  $("sample-btn").disabled = on;
  $("dropzone").classList.toggle("drag", on);
  $("dropzone").querySelector(".dz-title").textContent = on
    ? msg || "Working…"
    : "Drop your data here";
}

/* --------------------------------------------------------- render profile */
function onDataset(data) {
  state.sessionId = data.session_id;
  state.profile = data.profile;
  renderProfile(data);
  buildExamples(data.profile);
  enableComposer();
  toast(`Loaded ${data.source}`, "success");
}

function renderProfile(data) {
  const p = data.profile;
  $("ds-name").textContent = data.source;
  $("ds-kind").textContent = data.kind || "Data";
  $("ds-note").textContent = data.note || "";

  const stats = [
    { v: fmtNum(p.shape.rows), l: "Rows" },
    { v: fmtNum(p.shape.cols), l: "Columns" },
    { v: p.missing_pct + "%", l: "Missing cells", warn: p.missing_pct > 5 },
    { v: fmtNum(p.duplicates), l: "Duplicate rows", warn: p.duplicates > 0 },
  ];
  $("stat-grid").innerHTML = stats
    .map(
      (s) => `<div class="stat ${s.warn ? "warn" : ""}">
        <div class="v">${s.v}</div>
        <div class="l">${s.l}</div></div>`
    )
    .join("");

  const tc = p.type_counts || {};
  $("type-chips").innerHTML = Object.entries(tc)
    .map(
      ([k, v]) =>
        `<span class="tchip"><span class="sem ${k}">${k}</span><b>${v}</b></span>`
    )
    .join("");

  $("col-table").innerHTML = p.columns
    .map((c) => {
      const note = colNote(c);
      return `<tr>
        <td><div class="col-name">${esc(c.name)}</div>
            <div class="col-meta">${note}</div>
            <div class="nullbar"><i style="width:${Math.min(c.null_pct, 100)}%"></i></div></td>
        <td style="text-align:right"><span class="sem ${c.semantic}">${c.semantic}</span></td>
      </tr>`;
    })
    .join("");

  const box = $("anomaly-box");
  if (p.anomalies && p.anomalies.length) {
    box.hidden = false;
    $("anomaly-list").innerHTML = p.anomalies.map((a) => `<li>${esc(a)}</li>`).join("");
  } else {
    box.hidden = true;
  }

  $("dataset-panel").hidden = false;
  animateCounts();
}

function colNote(c) {
  const s = c.stats || {};
  if (c.semantic === "numeric")
    return `μ ${fmtMaybe(s.mean)} · ${fmtMaybe(s.min)}–${fmtMaybe(s.max)}${
      s.outliers ? ` · ${s.outliers} outliers` : ""
    }`;
  if (c.semantic === "datetime") return `${shortDate(s.min)} → ${shortDate(s.max)}`;
  if (s.top && s.top.length) return "top: " + s.top.slice(0, 2).map((t) => esc(String(t[0]))).join(", ");
  return `${fmtNum(c.unique)} unique`;
}

/* --------------------------------------------------------- example chips */
function buildExamples(p) {
  const cols = p.columns;
  const measureRe = /(sales|revenue|profit|amount|price|cost|value|total|count|score|spend)/i;
  const nums = cols
    .filter((c) => c.semantic === "numeric")
    .sort((a, b) => (measureRe.test(b.name) ? 1 : 0) - (measureRe.test(a.name) ? 1 : 0))
    .map((c) => c.name);
  const cats = cols.filter((c) => c.semantic === "categorical").map((c) => c.name);
  const dates = cols.filter((c) => c.semantic === "datetime").map((c) => c.name);

  const ex = [];
  if (dates.length && nums.length) ex.push(`How has total ${nums[0]} trended over time?`);
  if (cats.length && nums.length) ex.push(`Which ${cats[0]} has the highest total ${nums[0]}?`);
  if (nums.length >= 2) ex.push(`Is there a relationship between ${nums[0]} and ${nums[1]}?`);
  if (cats.length && nums.length) ex.push(`Compare ${nums[0]} across ${cats[0]} segments.`);
  ex.push("Summarize the most important patterns and any anomalies in this data.");

  const seen = new Set();
  const chips = ex.filter((q) => !seen.has(q) && seen.add(q)).slice(0, 5);
  $("example-chips").innerHTML = chips
    .map((q) => `<button class="ex">${esc(q)}</button>`)
    .join("");
  $("example-chips").querySelectorAll(".ex").forEach((b) =>
    b.addEventListener("click", () => {
      $("question").value = b.textContent;
      autogrow($("question"));
      $("question").focus();
    })
  );
}

/* ------------------------------------------------------------- composer */
function wireComposer() {
  const q = $("question");
  q.addEventListener("input", () => autogrow(q));
  q.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitQuestion();
    }
  });
  $("send-btn").addEventListener("click", submitQuestion);
}

function enableComposer() {
  const q = $("question");
  q.disabled = false;
  q.placeholder = "Ask a business question…  (e.g. which region is most profitable?)";
  $("send-btn").disabled = false;
}

function autogrow(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

function submitQuestion() {
  if (state.busy) return;
  const q = $("question").value.trim();
  if (!q) return;
  if (!state.sessionId) {
    toast("Upload a dataset first.", "error");
    return;
  }
  ask(q);
  $("question").value = "";
  autogrow($("question"));
}

/* ------------------------------------------------------------- ask / SSE */
async function ask(question) {
  setBusy(true);
  $("empty-state")?.remove();
  state.qCount += 1;
  const card = buildCard(question, state.qCount);
  $("feed").appendChild(card.el);
  scrollFeed();

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, question }),
    });
    if (!res.ok) {
      const t = await res.json().catch(() => ({ detail: res.statusText }));
      card.fail(t.detail || "Request failed");
      toast(t.detail || "Request failed", "error");
      return;
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        handleSSE(buf.slice(0, idx), card);
        buf = buf.slice(idx + 2);
      }
    }
  } catch (e) {
    card.fail("Connection error: " + e.message);
  } finally {
    setBusy(false);
  }
}

function handleSSE(raw, card) {
  let event = "message";
  let data = "";
  raw.split("\n").forEach((line) => {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  });
  if (!data) return;
  let payload;
  try {
    payload = JSON.parse(data);
  } catch {
    return;
  }
  dispatch(event, payload, card);
}

function dispatch(event, d, card) {
  switch (event) {
    case "status": card.pushStep(d.message); break;
    case "thinking": card.setThinking(d.text); break;
    case "plan": card.setPlan(d.text); break;
    case "code": card.setCode(d.code, d.attempt); break;
    case "stdout": card.setOutput(d.text); break;
    case "retry": card.addRetry(d.attempt, d.error); break;
    case "chart": card.setChart(d.figure); break;
    case "narrative": card.setFindings(d); break;
    case "error": card.fail(d.message, d.detail); break;
    case "done": card.complete(); break;
  }
}

/* --------------------------------------------------------- analysis card */
function buildCard(question, n) {
  const el = document.createElement("div");
  el.className = "analysis";
  el.innerHTML = `
    <div class="q-head">
      <div class="q-badge">Q${n}</div>
      <div class="q-text">${esc(question)}</div>
    </div>
    <div class="q-plan" hidden></div>
    <ul class="timeline"></ul>
    <div class="reason" hidden></div>
    <div class="code-slot"></div>
    <div class="output-slot"></div>
    <div class="chart-slot"></div>
    <div class="findings-slot"></div>
    <div class="error-slot"></div>`;

  const timeline = el.querySelector(".timeline");
  const planEl = el.querySelector(".q-plan");
  const reasonEl = el.querySelector(".reason");
  const codeSlot = el.querySelector(".code-slot");
  const outputSlot = el.querySelector(".output-slot");
  const chartSlot = el.querySelector(".chart-slot");
  const findingsSlot = el.querySelector(".findings-slot");
  const errorSlot = el.querySelector(".error-slot");

  function markActiveDone() {
    const active = timeline.querySelector("li.active");
    if (active) {
      active.classList.remove("active");
      active.classList.add("done");
    }
  }

  return {
    el,
    pushStep(msg) {
      markActiveDone();
      const li = document.createElement("li");
      li.className = "active";
      li.innerHTML = `<span class="node"></span>${esc(msg)}`;
      timeline.appendChild(li);
      scrollFeed();
    },
    addRetry(attempt, err) {
      markActiveDone();
      const li = document.createElement("li");
      li.className = "err done";
      li.innerHTML = `<span class="node"></span>Error on attempt ${attempt}: <code>${esc(
        err || ""
      )}</code>`;
      timeline.appendChild(li);
    },
    setPlan(text) {
      planEl.hidden = false;
      planEl.textContent = "“" + text + "”";
    },
    setThinking(text) {
      reasonEl.hidden = false;
      reasonEl.innerHTML = `<details><summary>Agent reasoning</summary>
        <div class="reason-body"></div></details>`;
      reasonEl.querySelector(".reason-body").textContent = text;
    },
    setCode(code, attempt) {
      codeSlot.innerHTML = `
        <div class="codeblock">
          <div class="code-bar">
            <span class="dots"><i></i><i></i><i></i></span>
            <span class="code-file">analysis.py</span>
            ${attempt > 1 ? `<span class="rev-badge">revision ${attempt}</span>` : ""}
            <button class="copy-btn">copy</button>
          </div>
          <pre><code class="language-python type-caret"></code></pre>
        </div>`;
      const codeEl = codeSlot.querySelector("code");
      codeSlot.querySelector(".copy-btn").addEventListener("click", (e) => {
        navigator.clipboard.writeText(code);
        e.target.textContent = "copied!";
        setTimeout(() => (e.target.textContent = "copy"), 1200);
      });
      typewriter(codeEl, code, () => {
        codeEl.classList.remove("type-caret");
        if (window.hljs) hljs.highlightElement(codeEl);
      });
    },
    setOutput(text) {
      outputSlot.innerHTML = `<div class="output"><details>
        <summary>Computed output</summary><pre></pre></details></div>`;
      outputSlot.querySelector("pre").textContent = text;
    },
    setChart(figure) {
      chartSlot.innerHTML = `<div class="chart-card">
        <div class="chart-plot"></div>
        <div class="chart-caption" hidden></div></div>`;
      const plot = chartSlot.querySelector(".chart-plot");
      try {
        Plotly.newPlot(plot, figure.data, figure.layout, {
          responsive: true,
          displaylogo: false,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
        });
      } catch (e) {
        plot.textContent = "Chart could not be rendered.";
      }
      scrollFeed();
    },
    setFindings(f) {
      const cap = chartSlot.querySelector(".chart-caption");
      if (cap && f.chart_caption) {
        cap.hidden = false;
        cap.textContent = f.chart_caption;
      }
      let html = `<div class="findings">
        <div class="insight"><span class="star">✦</span><p>${esc(f.key_insight)}</p></div>`;
      if (f.explanation)
        html += `<div class="f-block"><h4>What it means</h4>
          <div class="f-explain">${mdToHtml(f.explanation)}</div></div>`;
      if (f.limitations && f.limitations.length)
        html += `<div class="f-block"><h4>Limitations &amp; uncertainty</h4>
          <ul class="limits">${f.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>`;
      if (f.followups && f.followups.length)
        html += `<div class="f-block"><h4>Ask next</h4><div class="followups">${f.followups
          .map((q) => `<button class="fchip">${esc(q)}</button>`)
          .join("")}</div></div>`;
      html += `</div>`;
      findingsSlot.innerHTML = html;
      findingsSlot.querySelectorAll(".fchip").forEach((b) =>
        b.addEventListener("click", () => {
          if (state.busy) {
            toast("Let the current analysis finish first.", "error");
            return;
          }
          ask(b.textContent);
        })
      );
      scrollFeed();
    },
    fail(msg, detail) {
      markActiveDone();
      const active = timeline.querySelector("li.done:last-child");
      if (active) active.classList.add("err");
      errorSlot.innerHTML = `<div class="card-error">${esc(msg)}${
        detail ? `<pre>${esc(detail)}</pre>` : ""
      }</div>`;
      scrollFeed();
    },
    complete() {
      markActiveDone();
      scrollFeed();
    },
  };
}

/* ------------------------------------------------------------- utilities */
function setBusy(on) {
  state.busy = on;
  const btn = $("send-btn");
  btn.disabled = on || !state.sessionId;
  btn.classList.toggle("busy", on);
}

function typewriter(el, text, done) {
  const len = text.length;
  const perTick = Math.max(2, Math.ceil(len / 60));
  let i = 0;
  (function tick() {
    i = Math.min(len, i + perTick);
    el.textContent = text.slice(0, i);
    if (i < len) setTimeout(tick, 10);
    else if (done) done();
  })();
}

function animateCounts() {
  document.querySelectorAll(".stat .v").forEach((el) => {
    const raw = el.textContent;
    const m = raw.match(/^([\d,]+)/);
    if (!m) return;
    const target = parseInt(m[1].replace(/,/g, ""), 10);
    if (isNaN(target) || target > 1e7) return;
    const suffix = raw.slice(m[1].length);
    let cur = 0;
    const steps = 28;
    const inc = target / steps;
    (function run() {
      cur += inc;
      if (cur >= target) {
        el.textContent = fmtNum(target) + suffix;
      } else {
        el.textContent = fmtNum(Math.floor(cur)) + suffix;
        requestAnimationFrame(run);
      }
    })();
  });
}

function scrollFeed() {
  const feed = $("feed");
  feed.scrollTop = feed.scrollHeight;
}

function toast(msg, type = "") {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.textContent = msg;
  $("toast-wrap").appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transition = "0.4s";
    setTimeout(() => t.remove(), 400);
  }, 4200);
}

function mdToHtml(text) {
  try {
    return window.marked ? marked.parse(text) : esc(text).replace(/\n/g, "<br>");
  } catch {
    return esc(text);
  }
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
function fmtNum(n) {
  return typeof n === "number" ? n.toLocaleString("en-US") : n;
}
function fmtMaybe(v) {
  if (v === null || v === undefined) return "—";
  return typeof v === "number" ? (Math.abs(v) >= 1000 ? fmtNum(Math.round(v)) : v) : v;
}
function shortDate(s) {
  if (!s) return "—";
  return String(s).slice(0, 10);
}
