import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OMNIPARSER_DIR = ROOT / "omniparser"
WEIGHTS_DIR = ROOT / "models" / "omniparser"
LOG_DIR = ROOT / "logs"  # one JSONL file per run

# OmniParser's helpers read these on import (Florence-2 processor, easyocr).
os.environ.setdefault("HF_HOME", str(ROOT / "models" / "hf"))
os.environ.setdefault("EASYOCR_MODULE_PATH", str(ROOT / "models" / "easyocr"))

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8081")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "120"))
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "30"))
BOX_THRESHOLD = float(os.environ.get("OMNI_BOX_THRESHOLD", "0.05"))

# decide() probability of "sim" needed before the mouse moves at all.
CERTAINTY = float(os.environ.get("OMNI_CERTAINTY", "0.85"))

SERVER_HOST = "127.0.0.1"
SERVER_PORT = int(os.environ.get("AGENT_SERVER_PORT", "8766"))

# Title of the shell's floating input window (control.find_window).
SHELL_TITLE = "omni-all"

# Safety net for testing: when set, every click/scroll must land inside the
# window whose title contains this text, and typing only happens while that
# window is in front. Anything else is refused instead of executed.
CONFINE_TITLE = os.environ.get("OMNI_CONFINE_TITLE", "")
