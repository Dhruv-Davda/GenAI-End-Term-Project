"""Thin wrapper around the Anthropic SDK.

Uses adaptive thinking (recommended for non-trivial reasoning) and falls back
gracefully if a given SDK/model combination rejects the thinking parameter.
"""
import anthropic

from .config import MODEL

_client = None


def _get_client():
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY from the environment.
        _client = anthropic.Anthropic()
    return _client


def _text_of(resp):
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )


def _reasoning_of(resp):
    return "\n".join(
        b.thinking
        for b in resp.content
        if getattr(b, "type", None) == "thinking" and getattr(b, "thinking", None)
    ).strip()


def call(system, messages, max_tokens=8000, thinking=True, model=None):
    """Run a single Messages request and return (text, reasoning_summary)."""
    kwargs = dict(
        model=model or MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    if thinking:
        # Summarized display surfaces the agent's reasoning to the UI.
        kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}

    try:
        resp = _get_client().messages.create(**kwargs)
    except Exception:
        if thinking:
            # Some models / SDK versions may reject adaptive thinking — retry plain.
            kwargs.pop("thinking", None)
            resp = _get_client().messages.create(**kwargs)
        else:
            raise

    return _text_of(resp), _reasoning_of(resp)
