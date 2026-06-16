"""FastAPI application: upload + profile, then stream analyses over SSE."""
import json
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import agent, ingestion, profiler
from .config import BASE_DIR, HAS_API_KEY, MAX_FIX_ATTEMPTS, MODEL
from .session import create_session, get_session

app = FastAPI(title="Autonomous Data Analysis Agent")

STATIC_DIR = os.path.join(BASE_DIR, "static")
SAMPLE_PATH = os.path.join(BASE_DIR, "sample_data", "superstore_sales.csv")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model": MODEL,
        "has_api_key": HAS_API_KEY,
        "max_fix_attempts": MAX_FIX_ATTEMPTS,
        "sample_available": os.path.exists(SAMPLE_PATH),
    }


def _make_session(df, tables, name, kind, note, main_key):
    prof = profiler.profile(df, tables, main_key)
    sid = create_session(df, tables, prof, name, main_key)
    return {
        "session_id": sid,
        "source": name,
        "kind": kind,
        "note": note,
        "profile": prof,
        "model": MODEL,
        "has_api_key": HAS_API_KEY,
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    try:
        df, tables, kind, note, main_key = ingestion.load_any(file.filename, data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not read '{file.filename}': {e}")
    if df is None or df.shape[1] == 0:
        raise HTTPException(400, "No tabular data could be parsed from the file.")
    return _make_session(df, tables, file.filename, kind, note, main_key)


@app.post("/api/sample")
def sample():
    if not os.path.exists(SAMPLE_PATH):
        raise HTTPException(
            404, "Sample dataset not found — run `python generate_sample.py`."
        )
    with open(SAMPLE_PATH, "rb") as f:
        data = f.read()
    df, tables, kind, note, main_key = ingestion.load_any("superstore_sales.csv", data)
    return _make_session(
        df, tables, "superstore_sales.csv (sample)", kind, note, main_key
    )


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/ask")
async def ask(req: Request):
    body = await req.json()
    sid = body.get("session_id")
    question = (body.get("question") or "").strip()

    session = get_session(sid)
    if not session:
        raise HTTPException(404, "Session not found — upload a dataset first.")
    if not question:
        raise HTTPException(400, "The question is empty.")

    if not HAS_API_KEY:
        def no_key():
            yield _sse(
                "error",
                {
                    "message": (
                        "ANTHROPIC_API_KEY is not set. Add it to a .env file "
                        "(see .env.example) and restart the server."
                    )
                },
            )

        return StreamingResponse(no_key(), media_type="text/event-stream")

    def stream():
        try:
            for e in agent.run_analysis(session, question):
                yield _sse(e["event"], e["data"])
        except Exception as ex:  # noqa: BLE001
            yield _sse("error", {"message": f"Unexpected error: {ex}"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
