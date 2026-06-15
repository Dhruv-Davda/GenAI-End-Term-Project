"""The autonomous analysis loop.

run_analysis() is a generator that yields {"event", "data"} dicts so the web
layer can stream the agent's progress live: plan -> code -> execute -> (repair
on error) -> chart -> findings.
"""
import re

from . import executor, llm, prompts
from .config import MAX_FIX_ATTEMPTS
from .session import add_history

_CODE_RE = re.compile(r"```(?:python)?\s*\n?(.*?)```", re.S)
_PLAN_RE = re.compile(r"PLAN:\s*(.+)")


def _ev(event, data):
    return {"event": event, "data": data}


def _extract(text):
    m = _CODE_RE.search(text)
    code = m.group(1).strip() if m else text.strip()
    pm = _PLAN_RE.search(text)
    plan = pm.group(1).strip() if pm else ""
    return plan, code


def _short(err, limit=320):
    if not err:
        return ""
    line = err.strip().splitlines()[-1] if err.strip().splitlines() else err
    return line[:limit]


def run_analysis(session, question):
    df = session["df"]
    tables = session["tables"]

    yield _ev("status", {"message": "Reviewing the dataset profile"})
    profile_txt = prompts.profile_text(
        df, session["profile"], tables, session["main_name"]
    )
    user = prompts.codegen_user(profile_txt, session["history"], question)
    messages = [{"role": "user", "content": user}]

    yield _ev("status", {"message": "Planning the analysis with Claude"})
    text, reasoning = llm.call(prompts.CODEGEN_SYSTEM, messages, max_tokens=12000)
    plan, code = _extract(text)
    messages.append({"role": "assistant", "content": text})

    if reasoning:
        yield _ev("thinking", {"text": reasoning})
    if plan:
        yield _ev("plan", {"text": plan})
    yield _ev("code", {"code": code, "attempt": 1})

    attempt = 1
    result = None
    while True:
        yield _ev(
            "status", {"message": f"Executing code in the sandbox (attempt {attempt})"}
        )
        result = executor.execute(code, df, tables)
        if result["ok"]:
            break

        yield _ev("retry", {"attempt": attempt, "error": _short(result["error"])})
        if attempt >= MAX_FIX_ATTEMPTS:
            add_history(
                session,
                {
                    "question": question,
                    "plan": plan,
                    "code": code,
                    "stdout": result.get("stdout", ""),
                    "figure": None,
                    "findings": None,
                    "error": result["error"],
                },
            )
            yield _ev(
                "error",
                {
                    "message": (
                        f"Could not produce working code after {MAX_FIX_ATTEMPTS} "
                        "attempts."
                    ),
                    "detail": result["error"],
                },
            )
            return

        attempt += 1
        yield _ev(
            "status",
            {"message": f"Error caught — repairing the code (attempt {attempt})"},
        )
        messages.append({"role": "user", "content": prompts.fix_user(result["error"])})
        text, reasoning = llm.call(prompts.CODEGEN_SYSTEM, messages, max_tokens=12000)
        _, code = _extract(text)
        messages.append({"role": "assistant", "content": text})
        if reasoning:
            yield _ev("thinking", {"text": reasoning})
        yield _ev("code", {"code": code, "attempt": attempt})

    if result["stdout"].strip():
        yield _ev("stdout", {"text": result["stdout"]})

    has_chart = bool(result["figure"])
    if has_chart:
        yield _ev("status", {"message": "Rendering the visualization"})
        yield _ev("chart", {"figure": result["figure"]})

    yield _ev("status", {"message": "Writing plain-English findings"})
    n_user = prompts.narrative_user(question, code, result["stdout"], has_chart)
    n_text, _ = llm.call(
        prompts.NARRATIVE_SYSTEM,
        [{"role": "user", "content": n_user}],
        max_tokens=3000,
        thinking=False,
    )
    findings = prompts.parse_findings(n_text)
    yield _ev("narrative", findings)

    aid = add_history(
        session,
        {
            "question": question,
            "plan": plan,
            "code": code,
            "stdout": result["stdout"],
            "figure": result["figure"],
            "findings": findings,
        },
    )
    yield _ev("done", {"analysis_id": aid})
