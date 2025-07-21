# backend/services/xai_common.py

import json
import requests
import logging
from backend.config import XAI_API_KEY, XAI_API_URL

logger = logging.getLogger("XAI")

def query_xai(prompt: str, model: str = "grok-2-latest", temperature: float = 0.3) -> list:
    """
    Sends a prompt to XAI and returns the parsed JSON response.
    """
    payload = {
        "messages": [
            {"role": "system", "content": "You are an AI that returns valid JSON arrays only."},
            {"role": "user", "content": prompt}
        ],
        "model": model,
        "stream": False,
        "temperature": temperature
    }

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(XAI_API_URL, json=payload, headers=headers)
        response.raise_for_status()

        # Separate try block in case content fails
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"[XAI ERROR] Failed to parse content:\n{e}")
            logger.debug(f"[XAI RAW CONTENT]: {response.text}")

    except requests.RequestException as e:
        logger.error(f"[XAI ERROR] Request failed: {e}")
    except Exception as e:
        logger.error(f"[XAI ERROR] Unexpected error:\n{e}")

    return []
