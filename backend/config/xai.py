import os
from .helpers import env_int

LLM_PROVIDER      = "xai"
XAI_API_KEY       = os.getenv("XAI_API_KEY")
XAI_API_BASE      = "https://api.x.ai/v1"
XAI_API_URL       = f"{XAI_API_BASE}/chat/completions"
DEFAULT_XAI_MODEL = os.getenv("XAI_MODEL", "grok-3-latest")
XAI_MODEL         = DEFAULT_XAI_MODEL
TEMPERATURE_DEFAULT = 0.3

XAI_CONNECT_TIMEOUT = env_int("XAI_CONNECT_TIMEOUT", 10)
XAI_READ_TIMEOUT    = env_int("XAI_READ_TIMEOUT", 120)
XAI_MAX_RETRIES     = env_int("XAI_MAX_RETRIES", 3)
XAI_BACKOFF_FACTOR  = float(os.getenv("XAI_BACKOFF_FACTOR", "1.5"))
XAI_TIMEOUT_SECONDS = env_int("XAI_TIMEOUT_SECONDS", XAI_READ_TIMEOUT)

FALLBACK_TO_TEST_ON_XAI_ERROR = True
FALLBACK_TEST_FILE_NUMBER     = 1

def get_active_llm_info() -> dict:
    return {
        "provider": LLM_PROVIDER,
        "xai_model": DEFAULT_XAI_MODEL,
        "timeouts": {
            "connect": XAI_CONNECT_TIMEOUT,
            "read": XAI_READ_TIMEOUT,
            "max_retries": XAI_MAX_RETRIES,
            "backoff_factor": XAI_BACKOFF_FACTOR,
        },
    }
