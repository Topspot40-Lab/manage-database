# backend/services/xai_track_descriptions.py

from __future__ import annotations
import json
import logging
import time
from typing import List, Dict, Any
import requests

from backend.config import XAI_API_KEY, XAI_API_URL, BATCH_SIZE

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
_MAX_RETRIES = 2
_BACKOFF_SECS = 1.5

def _detail_instruction_for_lang(lang: str) -> str:
    if lang == "es":
        return (
            "detail: un mini-relato de EXACTAMENTE 4 a 6 oraciones completas (no menos de 4), con tono auténtico y natural de locutor de radio. "
            "Escribe cada oración separada claramente con punto. Debe haber al menos 4 oraciones completas. "
            "Si la respuesta tiene menos de 4 oraciones, es incorrecta. "

            "Estructura: "
            "Primera oración: introduce la canción o el artista. "
            "Segunda y tercera: explican el significado, emoción o mensaje. "
            "Última oración: incluye un dato concreto, contexto o impacto. "

            "Incluye obligatoriamente el nombre del artista y el significado de la canción. "

            "Describe con precisión el tono real de la canción (romántico, nostálgico, enérgico, etc.). "
            "Para canciones en inglés, ayuda al oyente hispanohablante a entender su significado. "

            "No traduzcas nombres de canciones ni de artistas. "
            "No inventes escenas ficticias. "
            "Evita descripciones genéricas que podrían aplicar a muchas canciones. "

            "Haz que suene natural, fluido y creíble en español, como un locutor real."
        )

    if lang == "pt-BR":
        return (
            "detail: uma mini-história de 4 a 5 frases, com tom caloroso, animado e natural de locutor de rádio. "
            "Pode repetir ocasionalmente e de forma natural o título da música e o nome do artista "
            "se isso ajudar a dar mais clareza ao ouvinte, mas sem soar repetitivo. "
            "Descreva o sentido, a emoção, a mensagem ou o contexto da música de forma clara e envolvente para falantes de português do Brasil, "
            "especialmente quando se tratar de uma música em inglês. "
            "Inclua pelo menos um fato concreto sobre a música, o artista, sua história ou seu impacto quando possível. "
            "Não traduza nomes de músicas nem de artistas. "
            "Não invente cenas de filmes, séries ou situações fictícias, a menos que estejam claramente relacionadas à música ou ao artista. "
            "Certifique-se de que a descrição esteja claramente baseada no conteúdo, na mensagem ou no contexto real da música específica, e não em uma interpretação genérica. "
            "Faça soar natural em português do Brasil, não como tradução literal do inglês."
        )

    return (
        "detail: a 4–5 sentence radio-style mini-story with a warm, lively tone. "
        "You may repeat the song title and artist name sparingly if it helps anchor the listener, but do not sound repetitive. "
        "Explain the song’s meaning, emotion, message, or background in a clear and engaging way. "
        "Include at least one concrete fact about the song, artist, history, or impact when possible. "
        "Do not invent movie scenes, TV scenes, or fictional situations unless they are clearly related to the song or artist. "
        "Make sure the description is clearly based on the actual content, message, or context of the specific song, not a generic interpretation."
    )


def _build_prompt(lang: str, formatted_input: list[dict]) -> str:
    detail_instruction = _detail_instruction_for_lang(lang)

    return (
        f"Language: {lang}.\n"
        "For each item, generate three fields:\n"
        "  - id: copy the input id exactly.\n"
        "  - intro: a short, varied one-sentence radio intro that mentions rank/category/genre context.\n"
        f"  - {detail_instruction}\n\n"
        "Return ONLY valid JSON, no commentary, as an array matching the input items. "
        "Each array element must be an object with exactly these keys: id, intro, detail.\n\n"
        f"Tracks:\n{json.dumps(formatted_input, ensure_ascii=False, indent=2)}"
    )


def _canon_lang(lang: str) -> str:
    if not lang:
        return "en"
    s = lang.strip().lower()
    if s in {"ptbr", "pt-br", "pt_br", "pt"}:
        return "pt-BR"
    if s in {"es-mx", "es_mx", "es"}:
        return "es"
    return "en" if s.startswith("en") else s

def _strip_code_fences(s: str) -> str:
    # removes ```json ... ``` or ``` ... ```
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        # after strip, model may have 'json\n{...}'
        parts = s.split("\n", 1)
        if len(parts) == 2 and parts[0].lower() in {"json", "javascript"}:
            return parts[1].strip()
        return parts[-1].strip()
    return s

def _safe_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None

def _merge_intro_detail(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    intro = (src.get("intro") or "").strip()
    detail = (src.get("detail") or "").strip()
    if intro and not (dst.get("intro") or "").strip():
        dst["intro"] = intro
    if detail and not (dst.get("detail") or "").strip():
        dst["detail"] = detail

def get_track_descriptions_from_xai(track_data, language, category, genre):
    """
    Batches requests to XAI to fill 'intro' and 'detail' for each track.
    Keeps camelCase input fields intact (trackName, artistName).
    Only fills fields that are missing/empty.
    """
    lang = _canon_lang(language)

    run_id = int(time.time())
    print(f"\n🚀 [{run_id}] START get_track_descriptions_from_xai")
    print(f"[{run_id}] Language={lang}, Category={category}, Genre={genre}")

    tracks: List[Dict[str, Any]] = track_data if isinstance(track_data, list) else (track_data.get("tracks", []) or [])
    n = len(tracks)
    if n == 0:
        return {"language": lang, "category": category, "genre": genre, "tracks": tracks}

    for batch_index in range(0, n, BATCH_SIZE):
        batch = tracks[batch_index:batch_index + BATCH_SIZE]
        formatted_input = [
            {
                "id": t.get("id"),
                "rank": t.get("rank"),
                "category": category,
                "genre": genre,
                "trackName": t.get("trackName") or t.get("title") or t.get("track_name"),
                "artistName": t.get("artistName") or t.get("artist") or t.get("artist_name"),
            }
            for t in batch
        ]

        # Prompt tightened to enforce strict JSON array of objects with intro/detail only
        prompt = _build_prompt(lang, formatted_input)

        payload = {
            "messages": [
                {"role": "system", "content": "You are a precise JSON generator. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.3,
        }

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    XAI_API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {XAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=_DEFAULT_TIMEOUT,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                raw = _strip_code_fences(content)
                parsed = _safe_json_loads(raw)

                if not isinstance(parsed, list):
                    raise ValueError("Model did not return a JSON array.")

                batch_by_id = {}
                for t in batch:
                    track_id = t.get("id")
                    if track_id is not None:
                        batch_by_id[str(track_id)] = t

                matched = 0
                for desc in parsed:
                    if not isinstance(desc, dict):
                        continue

                    desc_id = desc.get("id")
                    if desc_id is None:
                        logger.warning("⚠️ Skipping XAI item with no id: %s", desc)
                        continue

                    target = batch_by_id.get(str(desc_id))
                    if not target:
                        logger.warning("⚠️ XAI returned unknown id %s; skipping.", desc_id)
                        continue

                    _merge_intro_detail(target, desc)
                    matched += 1

                if matched != len(batch):
                    logger.warning(
                        "⚠️ Matched %s of %s returned descriptions in batch %s",
                        matched,
                        len(batch),
                        batch_index // BATCH_SIZE + 1,
                    )

                logger.debug(
                    f"✅ XAI batch {batch_index // BATCH_SIZE + 1}: size={len(batch)} (attempt {attempt+1})"
                )
                break  # success

            except (requests.HTTPError, requests.Timeout) as e:
                logger.warning(
                    f"XAI HTTP error on batch {batch_index // BATCH_SIZE + 1} attempt {attempt+1}: {e}"
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECS * (attempt + 1))
                    continue
                logger.error(f"❌ Giving up batch {batch_index // BATCH_SIZE + 1} after retries.")
            except Exception as e:
                logger.error(
                    f"❌ Error processing batch {batch_index // BATCH_SIZE + 1} attempt {attempt+1}: {e}"
                )
                # No retry for non-HTTP parsing errors unless you want to.
                break

    return {
        "language": lang,
        "category": category,
        "genre": genre,
        "tracks": tracks,
    }
