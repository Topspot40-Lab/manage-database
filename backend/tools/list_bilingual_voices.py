#!/usr/bin/env python3
"""
List ElevenLabs voices that support a given set of languages.

Config priority:
1) ENV:
   - ELEVENLABS_API_KEY
   - TTS_LANGS (comma/space-separated; e.g. "en, es" or "es-MX en")
2) backend.config fallbacks:
   - ELEVENLABS_API_KEY
   - DEFAULT_TTS_LANGUAGE (used with 'en' as a sensible default pair)
3) Hard default: ['en', 'es']

Examples:
  # Default (tries env/config for langs; else en+es)
  python backend/tools/list_bilingual_voices.py

  # Explicit languages (positional or --langs):
  python backend/tools/list_bilingual_voices.py en es
  python backend/tools/list_bilingual_voices.py --langs en es

  # Match ANY instead of ALL
  python backend/tools/list_bilingual_voices.py --langs es en --match any

  # Add model column and probe voice/model compatibility
  python backend/tools/list_bilingual_voices.py --model eleven_multilingual_v2 --probe

  # IDs only / CSV / JSON
  python backend/tools/list_bilingual_voices.py --ids-only
  python backend/tools/list_bilingual_voices.py --csv voices.csv
  python backend/tools/list_bilingual_voices.py --json
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import csv
import re
import io
from typing import Dict, List, Any, Iterable
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────────────────
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[2]  # .../topspot_json_creator
load_dotenv(PROJECT_ROOT / ".env")

# ── Project config (fallbacks) ───────────────────────────────────────────────
try:
    from backend.config import ELEVENLABS_API_KEY as CFG_API_KEY  # type: ignore
except Exception:
    CFG_API_KEY = None

try:
    from backend.config import DEFAULT_TTS_LANGUAGE as CFG_DEFAULT_LANG  # type: ignore
except Exception:
    CFG_DEFAULT_LANG = None

ELEVEN_VOICES_URL = "https://api.elevenlabs.io/v1/voices"
ELEVEN_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# ── Normalization helpers ────────────────────────────────────────────────────
_LANG_NORMALIZER = {
    # English
    "en": "en", "en-us": "en", "en-uk": "en", "en-gb": "en",
    # Spanish
    "es": "es", "es-mx": "es", "es-419": "es", "es-es": "es",
    # Portuguese (handy if you extend to pt-BR)
    "pt": "pt", "pt-br": "pt",
    # Names
    "english": "en", "spanish": "es", "español": "es", "portuguese": "pt",
}

# map human names → codes
_NAME_TO_CODE = {
    "english": "en",
    "spanish": "es",
    "español": "es",
    "mexican": "es",              # "Mexican Spanish" → es
    "mexican spanish": "es",
    "portuguese": "pt",
    "brazilian portuguese": "pt",
    "português": "pt",
    "português (br)": "pt",
}

# Accept only these as "real" language tokens after normalization
_ALLOWED_LANG_CODES = {"en", "es", "pt"}
_ALLOWED_LANG_NAMES = set(_NAME_TO_CODE.keys())

def _from_env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    return v if (v is not None and str(v).strip() != "") else default

def _split_langs(s: str | None) -> List[str]:
    if not s:
        return []
    # support both comma and whitespace separation
    parts = re.split(r"[\s,]+", s.strip())
    return [p for p in parts if p]

def normalize_lang(code: str) -> str:
    if not code:
        return ""
    c = code.strip().lower()
    return _LANG_NORMALIZER.get(c, c)

def normalize_lang_list(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    for v in values or []:
        nv = normalize_lang(str(v))
        if nv:
            out.append(nv)
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq

def _maybe_lang_tokens(s: str) -> list[str]:
    """
    Split a free-form string and return only plausible language tokens.
    Filters out marketing tags like 'professional', 'advertisement', 'intense'.
    """
    toks = [t.strip().lower() for t in re.split(r"[^A-Za-zÀ-ÿ\-]+", s) if t.strip()]
    out = []
    for t in toks:
        mapped = _NAME_TO_CODE.get(t, t)
        mapped = normalize_lang(mapped)  # en-us→en, es-mx→es, pt-br→pt
        if mapped in _ALLOWED_LANG_CODES:
            out.append(mapped)
        elif t in _ALLOWED_LANG_NAMES:
            out.append(_NAME_TO_CODE[t])
        # else: ignore non-language tags
    return out

def languages_from_voice(voice: Dict[str, Any]) -> List[str]:
    """
    Extract language codes from a voice object, using a strict whitelist so we
    don't accidentally treat tags like 'professional' as languages.
    """
    langs: list[str] = []
    labels = voice.get("labels") or {}

    # 1) Common structured locations
    lbl_langs = labels.get("languages")
    if isinstance(lbl_langs, list):
        for val in lbl_langs:
            if isinstance(val, str):
                langs.extend(_maybe_lang_tokens(val))

    for key in ("language", "lang", "primary_language"):
        val = labels.get(key)
        if isinstance(val, str):
            langs.extend(_maybe_lang_tokens(val))

    # 2) Top-level variants found in some responses
    for k in ("languages", "available_languages", "supported_languages", "voice_languages"):
        val = voice.get(k)
        if isinstance(val, list):
            for v in val:
                if isinstance(v, str):
                    langs.extend(_maybe_lang_tokens(v))
        elif isinstance(val, str):
            langs.extend(_maybe_lang_tokens(val))

    if isinstance(voice.get("language"), str):
        langs.extend(_maybe_lang_tokens(voice["language"]))

    # 3) Heuristic scan of other string labels (names/tags)
    for _, v in labels.items():
        if isinstance(v, str):
            langs.extend(_maybe_lang_tokens(v))

    # 4) Accent sometimes reveals language (e.g., "es", "pt-BR")
    accent = labels.get("accent")
    if isinstance(accent, str):
        langs.extend(_maybe_lang_tokens(accent))

    return normalize_lang_list(langs)

# ── API helpers ──────────────────────────────────────────────────────────────
def resolve_api_key() -> str:
    k = _from_env("ELEVENLABS_API_KEY")
    if k:
        return k
    if CFG_API_KEY:
        return CFG_API_KEY
    print("❌ ELEVENLABS_API_KEY not set (env or backend.config).", file=sys.stderr)
    sys.exit(1)

def resolve_default_langs(cli_langs: List[str] | None) -> List[str]:
    # CLI overrides everything if provided
    if cli_langs:
        return normalize_lang_list(cli_langs)

    # ENV TTS_LANGS
    env_langs = normalize_lang_list(_split_langs(_from_env("TTS_LANGS")))
    if env_langs:
        return env_langs

    # backend.config DEFAULT_TTS_LANGUAGE (+ 'en' as a sensible pair)
    if CFG_DEFAULT_LANG:
        cfg = normalize_lang_list([CFG_DEFAULT_LANG, "en"])
        return cfg if cfg else ["en", "es"]

    # Hard default
    return ["en", "es"]

def fetch_voices(api_key: str) -> List[Dict[str, Any]]:
    headers = {"xi-api-key": api_key}
    resp = requests.get(ELEVEN_VOICES_URL, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise SystemExit(f"⚠️  ElevenLabs API error {resp.status_code}: {resp.text}")
    data = resp.json() or {}
    return data.get("voices", [])

def probe_voice_model(voice_id: str, model_id: str, api_key: str) -> bool:
    """
    Opt-in, minimal-cost probe to see if a voice accepts a given model.
    Sends a 1-word request; if 200, we consider it supported.
    Treat any 4xx as 'not supported'; others as 'unknown/false'.
    """
    try:
        headers = {
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        payload = {"model_id": model_id, "text": "Hola"}
        r = requests.post(ELEVEN_TTS_URL.format(voice_id=voice_id),
                          headers=headers, data=json.dumps(payload), timeout=15)
        if r.status_code == 200 and r.content:
            return True
        if 400 <= r.status_code < 500:
            return False
        return False
    except requests.Timeout:
        return False
    except Exception:
        return False

# ── Output helpers ───────────────────────────────────────────────────────────
def as_table(rows: List[Dict[str, str]]) -> str:
    if not rows:
        return "No matching voices found."

    show_model = any("model" in r for r in rows)
    show_probe = any("probe" in r for r in rows)

    headers = ["Name", "Voice ID", "Languages"]
    if show_model: headers.append("Model")
    if show_probe: headers.append("Probe")

    widths = {h: len(h) for h in headers}
    for r in rows:
        widths["Name"] = max(widths["Name"], len(r.get("name","")))
        widths["Voice ID"] = max(widths["Voice ID"], len(r.get("voice_id","")))
        widths["Languages"] = max(widths["Languages"], len(r.get("languages","")))
        if show_model:
            widths["Model"] = max(widths["Model"], len(r.get("model","")))
        if show_probe:
            widths["Probe"] = max(widths["Probe"], len(r.get("probe","")))

    line = "  ".join(h.ljust(widths[h]) for h in headers)
    bar  = "  ".join("-"*widths[h] for h in headers)
    out = [line, bar]

    for r in rows:
        cols = [
            r.get("name","").ljust(widths["Name"]),
            r.get("voice_id","").ljust(widths["Voice ID"]),
            r.get("languages","").ljust(widths["Languages"]),
        ]
        if show_model:
            cols.append(r.get("model","").ljust(widths["Model"]))
        if show_probe:
            cols.append(r.get("probe","").ljust(widths["Probe"]))
        out.append("  ".join(cols))
    return "\n".join(out)

def write_csv(path: str, rows: List[Dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "voice_id", "languages", "category", "model", "probe"])
        writer.writeheader()
        writer.writerows(rows)

# ── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Filter ElevenLabs voices by supported languages.")
    # accept either positional or --langs
    parser.add_argument("positional_langs", nargs="*", help="Optional positional languages (e.g., en es).")
    parser.add_argument("--langs", nargs="+", help="Language codes (e.g., en es or es-MX en-GB).")
    parser.add_argument("--match", choices=["all", "any"], default="all", help="Require ALL or ANY of the languages.")
    parser.add_argument("--ids-only", action="store_true", help="Only print matching voice IDs (one per line).")
    parser.add_argument("--csv", metavar="PATH", help="Write matches to CSV.")
    parser.add_argument("--json", action="store_true", help="Output full JSON for matches (raw voice objects).")
    parser.add_argument("--model", default="eleven_multilingual_v2",
                        help="Model to display/probe (e.g., eleven_multilingual_v2).")
    parser.add_argument("--probe", action="store_true",
                        help="Try a minimal synthesis to verify the voice accepts --model (uses tiny TTS quota).")
    parser.add_argument("--show-labels", action="store_true", help="Also print labels for each match (debug).")
    args = parser.parse_args()

    api_key = resolve_api_key()

    # prefer explicit --langs, else positional, else env/config/defaults
    cli_langs = args.langs if args.langs else args.positional_langs
    target_langs = resolve_default_langs(cli_langs)

    try:
        voices = fetch_voices(api_key)
    except Exception as e:
        print(f"❌ Failed to fetch voices: {e}", file=sys.stderr)
        sys.exit(2)

    matches: List[Dict[str, str]] = []
    raw_matches: List[Dict[str, Any]] = []

    for v in voices:
        vlangs = languages_from_voice(v)
        if not target_langs or (args.match == "all" and set(target_langs).issubset(set(vlangs))) or \
           (args.match == "any" and bool(set(target_langs) & set(vlangs))):
            raw_matches.append(v)
            matches.append({
                "name": v.get("name", ""),
                "voice_id": v.get("voice_id", ""),
                "languages": ", ".join(vlangs) if vlangs else "",
                "category": v.get("category", ""),
                "model": args.model,
                "probe": "",
            })

    if args.ids_only:
        for r in matches:
            print(r["voice_id"])
        sys.exit(0)

    # Optional probe (lightweight)
    if args.probe:
        for r in matches:
            ok = probe_voice_model(r["voice_id"], args.model, api_key)
            r["probe"] = "✅" if ok else "❌"

    print(as_table(matches))

    if args.csv:
        write_csv(args.csv, matches)
        print(f"\n💾 Wrote CSV: {args.csv}")

    if args.json:
        print(json.dumps(raw_matches, indent=2, ensure_ascii=False))

    if args.show_labels:
        for v in raw_matches:
            print(f"\n--- {v.get('name','?')} ({v.get('voice_id','?')}) labels ---")
            print(json.dumps(v.get("labels", {}), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
