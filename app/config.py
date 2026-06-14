"""Runtime configuration, loaded from environment / .env."""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load .env from the project root if present.
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Default to the most capable Claude model. Override with ANALYST_MODEL.
MODEL = os.environ.get("ANALYST_MODEL", "claude-opus-4-8")

# How many times the agent may rewrite broken code before giving up.
MAX_FIX_ATTEMPTS = int(os.environ.get("ANALYST_MAX_FIX_ATTEMPTS", "3"))

# Hard wall-clock limit (seconds) for a single code execution.
EXEC_TIMEOUT = int(os.environ.get("ANALYST_EXEC_TIMEOUT", "30"))

HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
