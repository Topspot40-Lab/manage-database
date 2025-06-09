# backend/services/xai_api_client.py

import requests
import logging
import json
from backend.config import (
    XAI_API_KEY,
    XAI_API_URL,
    DEFAULT_XAI_MODEL,
    TEMPERATURE_DEFAULT,
    TEST_JSON_DIR
)

def fetch_xai_tracks(prompt, test_file_number=0):
    if test_file_number > 0:
        test_path = TEST_JSON_DIR / f"json_test_file_{test_file_number}.json"
        logging.warning(f"🧪 TEST MODE ENABLED: Using {test_path}")
        with open(test_path, "r", encoding="utf-8") as f:
            return json.load(f)

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "system", "content": "You are an AI that strictly returns valid JSON arrays with no extra text."},
            {"role": "user", "content": prompt}
        ],
        "model": DEFAULT_XAI_MODEL,
        "temperature": TEMPERATURE_DEFAULT,
        "stream": False
    }

    response = requests.post(XAI_API_URL, json=payload, headers=headers)

    if response.status_code != 200:
        logging.error(f"❌ XAI request failed: {response.status_code}")
        logging.error(response.text)
        raise Exception("XAI response failed")

    content = response.json()["choices"][0]["message"]["content"]
    return content

