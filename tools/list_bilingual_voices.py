#!/usr/bin/env python3
"""
List ElevenLabs voices that support a given set of languages.

Priority for configuration:
1) Environment variables
   - ELEVENLABS_API_KEY
   - TTS_LANGS (comma/space-separated; e.g. "en, es" or "es-MX en")
2) backend.config fallbacks
   - ELEVENLABS_API_KEY
   - DEFAULT_TTS_LANGUAGE (used with 'en' as a sensible default pair)
3) Hard default: ['en', 'es']

Usage:
  # Default (tries env/config for langs; else en+es)
  python backend/tools/list_bilingual_voices.py

  # Explicit languages
  python backend/tools/list_bilingual_voices.py --langs en es

  # Match ANY instead of ALL
  python backend/tools/list_bilingual_voices.py --langs es en --match any

  # IDs only
  python backend/tools/list_bilingual_voices.py --ids-only

  # Export CSV
  python backend/tools/list_bilingual_voices.py --csv voices_en_es.csv

  # Raw JSON
  python backend/tools/list_bilingual_voices.py --json
"""

from __future__ import annotations
import os
import sys
import json
import argparse
import csv
import re
from typing import Dict, List, Any, Iterable

import requests

# ── Project config (fallbacks) ────────────────────────────────────────────────
try:
    # Adjust import if your config path differs
    from backend.config import ELEVENLABS_API_KEY as CFG_API_KEY  # type: ignore
except Exception:
    CFG_API_KEY = None

try:
    from backend.config import DEFAULT_TTS_LANGUAGE as CFG_DEFAULT_LANG  # type: ignore
except Exception:
    CFG_DEFAULT_LANG = None

ELEVEN_VOICES_URL = "https://api.elevenlabs.io/v1/voices"

# Accept a handful of common variants and normalize them to short tags
_LANG_NORMALIZER = {
    # English
    "en": "en", "en-us": "en", "en-uk": "en", "en-gb": "en",
    # Spanish
    "es": "es", "es-mx": "es", "es-419": "es", "es-es": "es",
    # Portuguese (handy if you extend to pt-BR)
    "pt": "pt", "pt-br": "pt",
    # Names
    "english": "en", "spanish": "es", "portuguese": "pt",
}

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

def resolve_api_key() -> str:
    # 1) ENV first
    k = _from_env("ELEVENLABS_API_KEY")
    if k:
        return k
    # 2) backend.config fallback
    if CFG_API_KEY:
        return CFG_API_KEY
    print("❌ ELEVENLABS_API_KEY not set (env or backend.config).", file=sys.stderr)
    sys.exit(1)

def resolve_default_langs(cli_langs: List[str] | None) -> List[str]:
    # CLI overrides everything if provided
    if cli_langs:
        return normalize_lang_list(cli_langs)

    # 1) ENV TTS_LANGS
    env_langs = normalize_lang_list(_split_langs(_from_env("TTS_LANGS")))
    if env_langs:
        return env_langs

    # 2) backend.config DEFAULT_TTS_LANGUAGE (+ 'en' as a sensible pair)
    if CFG_DEFAULT_LANG:
        cfg = normalize_lang_list([CFG_DEFAULT_LANG, "en"])
        return cfg if cfg else ["en", "es"]

    # 3) Hard default
    return ["en", "es"]

def languages_from_voice(voice: Dict[str, Any]) -> List[str]:
    """
    Extract language codes from a voice object.
    ElevenLabs voice JSON isn't 100% uniform; check multiple fields:
      - voice.get("labels", {}).get("languages", [...])
      - voice.get("labels", {}).get("language"/"lang"/"primary_language")
      - voice.get("languages") / voice.get("language")
      - Heuristic: parse language names in stringy labels
    """
    langs: List[str] = []

    labels = voice.get("labels") or {}
    if isinstance(labels.get("languages"), list):
        langs.extend([str(x) for x in labels["languages"]])

    for key in ("language", "lang", "primary_language"):
        if key in labels and isinstance(labels[key], str):
            langs.append(labels[key])

    if isinstance(voice.get("languages"), list):
        langs.extend([str(x) for x in voice["languages"]])
    if isinstance(voice.get("language"), str):
        langs.append(voice["language"])

    # Heuristic scan of string labels
    for _, v in labels.items():
        if isinstance(v, str) and any(tok in v.lower() for tok in ("english", "spanish", "en", "es")):
            cand = [t for t in re.split(r"[^A-Za-z\-]+", v) if t]
            langs.extend(cand)

    return normalize_lang_list(langs)

def fetch_voices(api_key: str) -> List[Dict[str, Any]]:
    headers = {"xi-api-key": api_key}
    resp = requests.get(ELEVEN_VOICES_URL, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise SystemExit(f"⚠️  ElevenLabs API error {resp.status_code}: {resp.text}")
    data = resp.json() or {}
    return data.get("voices", [])

def matches_languages(voice_langs: List[str], target_langs: List[str], mode: str) -> bool:
    if not target_langs:
        return True
    vset = set(voice_langs)
    tset = set(target_langs)
    return tset.issubset(vset) if mode == "all" else bool(vset & tset)

def as_table(rows: List[Dict[str, str]]) -> str:
    if not rows:
        return "No matching voices found."
    name_w = max(len("Name"), *(len(r["name"]) for r in rows))
    id_w   = max(len("Voice ID"), *(len(r["voice_id"]) for r in rows))
    langs_w= max(len("Languages"), *(len(r["languages"]) for r in rows))
    line = f"{'Name'.ljust(name_w)}  {'Voice ID'.ljust(id_w)}  {'Languages'.ljust(langs_w)}"
    bar  = f"{'-'*name_w}  {'-'*id_w}  {'-'*langs_w}"
    out = [line, bar]
    for r in rows:
        out.append(f"{r['name'].ljust(name_w)}  {r['voice_id'].ljust(id_w)}  {r['languages'].ljust(langs_w)}")
    return "\n".join(out)

def write_csv(path: str, rows: List[Dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "voice_id", "languages", "category"])
        writer.writeheader()
        writer.writerows(rows)

def main():
    parser = argparse.ArgumentParser(description="Filter ElevenLabs voices by supported languages.")
    parser.add_argument("--langs", nargs="+", help="Language codes (e.g., en es or es-MX en-GB).")
    parser.add_argument("--match", choices=["all", "any"], default="all", help="Require ALL or ANY of the languages.")
    parser.add_argument("--ids-only", action="store_true", help="Only print matching voice IDs (one per line).")
    parser.add_argument("--csv", metavar="PATH", help="Write matches to CSV.")
    parser.add_argument("--json", action="store_true", help="Output full JSON for matches (raw voice objects).")
    args = parser.parse_args()

    api_key = resolve_api_key()
    target_langs = resolve_default_langs(args.langs)

    try:
        voices = fetch_voices(api_key)
    except Exception as e:
        print(f"❌ Failed to fetch voices: {e}", file=sys.stderr)
        sys.exit(2)

    matches = []
    raw_matches = []
    for v in voices:
        vlangs = languages_from_voice(v)
        if matches_languages(vlangs, target_langs, args.match):
            raw_matches.append(v)
            matches.append({
                "name": v.get("name", ""),
                "voice_id": v.get("voice_id", ""),
                "languages": ", ".join(vlangs) if vlangs else "",
                "category": v.get("category", ""),  # 'cloned' | 'professional' | 'generated' (varies)
            })

    if args.ids_only:
        for r in matches:
            print(r["voice_id"])
        sys.exit(0)

    if args.json:
        print(json.dumps(raw_matches, indent=2, ensure_ascii=False))

    if args.csv:
        write_csv(args.csv, matches)
        print(f"💾 Wrote CSV: {args.csv}")

    print(as_table(matches))

if __name__ == "__main__":
    main()
