# Deploy guide

## 1. Push to GitHub

```bash
cd /Users/dhruv/Desktop/GenAi-Project
git init
git config user.name "Dhruv Davda"          # if not set globally
git config user.email "dhruvdavda500@gmail.com"
git add .
git commit -m "Insight Engine: autonomous data analysis agent"
git branch -M main
git remote add origin https://github.com/Dhruv-Davda/GenAI-End-Term-Project.git
git push -u origin main
```

If the GitHub repo already has commits (e.g. an auto-created README) and the push
is rejected, run `git pull --rebase origin main` first, then push again.

> Secrets are safe: `.env` is git-ignored and only `.env.example` (a placeholder) is committed.

---

## 2. Deploy — pick one

### A. Instant public link from your laptop (fastest, for a live demo)
The local server is already running. Expose it with a no-signup tunnel:

```bash
brew install cloudflared
cloudflared tunnel --url http://127.0.0.1:8010
```

It prints a public `https://*.trycloudflare.com` URL. (Alternatives: `ngrok http 8010`, `npx localtunnel --port 8010`.)

### B. Free hosted deploy on Render (persistent URL)
1. Push to GitHub (above).
2. Go to <https://render.com> → **New → Blueprint** → connect this repo (it reads `render.yaml`).
3. When prompted, paste your **`ANTHROPIC_API_KEY`**.
4. Deploy (~3–5 min) → you get a public `https://<name>.onrender.com` URL.

Free tier notes: single instance (in-memory sessions are fine), 512 MB RAM (fine for small/medium CSVs), sleeps after ~15 min idle (first request cold-starts in ~30s).

### C. Container platforms (Fly.io / Hugging Face Spaces / Cloud Run)
A `Dockerfile` is included. e.g. Fly: `fly launch` then `fly secrets set ANTHROPIC_API_KEY=sk-ant-...`.

---

## ⚠️ Security before going public

This app runs **LLM-generated Python** in an in-process sandbox (allow-listed
imports, no `os`/network/`open`, timeout). That is fine for a **trusted, short-lived
demo**, but it is **not safe for an open public service**: allowed libraries like
pandas can still read server files (`pd.read_csv`, `pd.read_pickle`). Before any
public, long-lived deploy, put it behind **authentication** (HTTP basic auth / a
login) and/or run code execution in a locked-down container with no secrets and
no outbound network. Prefer the tunnel (option A) or a private/short-lived deploy
for grading.
