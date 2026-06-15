"""In-memory session store.

Each session holds the loaded dataset, its profile, and the running history of
analyses so follow-up questions can build on earlier context.
"""
import uuid

SESSIONS: dict = {}


def create_session(df, tables, profile, name, main_key):
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = {
        "df": df,
        "tables": tables,
        "profile": profile,
        "source_name": name,
        "main_name": main_key,
        "history": [],
    }
    return sid


def get_session(sid):
    return SESSIONS.get(sid)


def add_history(session, item):
    item["id"] = len(session["history"]) + 1
    session["history"].append(item)
    return item["id"]
