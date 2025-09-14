# backend/routers/collections_generate.py
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from requests import HTTPError as RequestsHTTPError
from requests.exceptions import Timeout, RequestException

# XAI error helpers (same pattern as decade-genre pipeline)
from backend.services.xai_errors import XAIQuotaError, XAIRateLimitError

# Reuse your XAI curator used by the prior collections stub
from backend.services.curate import curate_tracks_via_xai

# Spotify enrich step (same function used in decade-genre flow)
from backend.services.track_generator import enrich_tracks_with_spotify

# XAI copy generators (same ones used in decade-genre flow)
from backend.services.xai_descriptions import get_track_descriptions_from_xai
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai

# Helpers consistent with your pipeline
from backend.utils.naming import slug_underscore, normalize_language_code
from backend.services.spotify.missing_log import handle_missing_track, reassign_ranks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collections", tags=["Collections (Generate JSON)"])

# ─────────────────────────────────────────────────────────────────────────────
# Slug → Display name mapping (kept from your earlier stub)
# ─────────────────────────────────────────────────────────────────────────────
SLUG_TO_NAME = {
    "power_ballads": "Power Ballads",
    "disney_classics_pre_1988": "Disney: Classics (pre-1988)",
    "disney_revival_after_1988": "Disney: Revival (after-1988)",
    "motown_magic": "Motown Magic",
    "disco_favorites": "Disco Favorites",
    "one_hit_wonders": "One-Hit Wonders",
    "dance_floor_anthems": "Dance Floor Anthems",
    "latin_crossovers": "Latin Crossovers",
    "novelty_songs": "Novelty Songs",
    "holiday_favorites": "Holiday Favorites",
    "protest_social_justice": "Protest & Social Justice",
    "stage_screen_broadway_classics": "Stage & Screen: Broadway Classics",
    "stage_screen_movie_themes": "Stage & Screen: Movie Themes",
    "classical_music_baroque_period_1600_1750": "Classical Music: Baroque Period (1600-1750)",
    "classical_music_classical_period_1750_1820": "Classical Music: Classical Period (1750-1820)",
    "classical_music_romantic_period_1820_1910": "Classical Music: Romantic Period (1820-1910)",
}


def _theme_from_slug(slug: str) -> str:
    return SLUG_TO_NAME.get(slug, slug.replace("_", " ").title())


# ─────────────────────────────────────────────────────────────────────────────
# Normalizers (mirrors your decade-genre pipeline behavior)
# ─────────────────────────────────────────────────────────────────────────────
_CONNECTORS = [
    (r"\s+feat\.\s+", "FEATURED"),
    (r"\s+ft\.\s+", "FEATURED"),
    (r"\s+featuring\s+", "FEATURED"),
    (r"\s+with\s+", "DUET"),
    (r"\s+con\s+", "DUET"),
    (r"\s+y\s+", "DUET"),
    (r"\s+&\s+", "DUET"),
]

def _normalize_artist_collab(t: dict) -> dict:
    name = (t.get("artist_name") or "").strip()
    if not name:
        return t
    for pattern, mode in _CONNECTORS:
        parts = re.split(pattern, name, flags=re.IGNORECASE)
        if len(parts) >= 2:
            main = parts[0].strip()
            rest = " & ".join(p.strip() for p in parts[1:] if p.strip())
            t["artist_name"] = main
            if not (t.get("mode_flag") or "").strip():
                t["mode_flag"] = mode
            t["featured_artist"] = rest
            return t
    return t

def _to_snake_track(d: dict) -> dict:
    out = {}
    out["track_name"] = d.get("track_name") or d.get("trackName") or d.get("title")
    out["artist_name"] = d.get("artist_name") or d.get("artistName") or d.get("artist")
    out["year_released"] = d.get("year_released") or d.get("yearReleased") or d.get("year")
    out["album_name"] = d.get("album_name") or d.get("albumName")
    out["rank"] = d.get("rank") or d.get("ranking")

    # Ensure mode keys exist
    out["mode_flag"] = d.get("mode_flag") or d.get("modeFlag") or ""
    out["mode_flag_detail"] = d.get("mode_flag_detail") or d.get("modeFlagDetail") or ""

    # pass-through
    for k, v in d.items():
        if k not in out:
            out[k] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Request model
# ─────────────────────────────────────────────────────────────────────────────
class CollectionRequest(BaseModel):
    slug: str
    language: str = "english"
    target_count: int = 45


# ─────────────────────────────────────────────────────────────────────────────
# Main endpoint — mirrors your 11-step flow, adapted for collections
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/generate-json", summary="Generate a COLLECTION JSON via XAI→Spotify→XAI and save to disk")
def generate_collection_json(
    request: CollectionRequest,
    max_step: int = Query(11, ge=1, le=11),
) -> Dict[str, Any]:
    try:
        logger.debug("🟡 STEP 0: Starting collections.generate-json")

        slug = slug_underscore(request.slug)
        theme = _theme_from_slug(slug)
        lang_code = normalize_language_code(request.language)  # e.g., "en", "es"

        now_dt = datetime.now()
        is_test_mode = False  # keep simple; collections filenames are stable

        # ───────────────── STEP 1 ─────────────────
        logger.debug("✍️ STEP 1: Curating candidates from XAI")
        # Ask for extra candidates as spares to backfill missing Spotify matches
        raw_candidates = curate_tracks_via_xai(theme, max_items=request.target_count * 2) or []

        tracks: List[Dict[str, Any]] = []
        spares: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def _first(d: Dict[str, Any], *keys: str, default: str = "") -> str:
            for k in keys:
                v = d.get(k)
                if v not in (None, ""):
                    return v if not isinstance(v, str) else v.strip()
            return default

        def _parse_year(v: Any) -> Optional[int]:
            try:
                y = int(str(v)[:4])
                return y if 1600 <= y <= 2100 else None
            except Exception:
                return None

        for c in raw_candidates:
            if not isinstance(c, dict):
                continue
            title = _first(c, "title", "trackName", "track", "name")
            artist = _first(c, "artist", "artistName")
            year = _parse_year(_first(c, "year", "yearReleased"))

            if not title or not artist:
                continue

            key = (title.lower(), artist.lower())
            if key in seen:
                continue
            seen.add(key)

            item = {
                "rank": len(tracks) + 1,
                "track_name": title,
                "artist_name": artist,
                "year_released": year,
                "spotify_track_id": None,
                "album_name": None,
                "album_art_url": None,
                "mode_flag": "",
                "mode_flag_detail": "",
            }

            if len(tracks) < request.target_count:
                tracks.append(item)
            else:
                spares.append(item)

        if max_step == 1:
            return {"message": "Stopped after STEP 1", "preview": {"collection": theme, "tracks": tracks}}

        # ───────────────── STEP 2 ─────────────────
        logger.debug("✍️ STEP 2: Skipped (legacy descriptions moved to STEP 9)")
        if max_step == 2:
            return {"message": "Stopped after STEP 2", "count": len(tracks)}

        # ───────────────── STEP 3 ─────────────────
        logger.debug("🎧 STEP 3: Enriching with Spotify")
        tracks = [_to_snake_track(t) for t in tracks]
        tracks = [_normalize_artist_collab(t) for t in tracks]

        tracks = enrich_tracks_with_spotify(tracks, is_test_mode=False)

        # Filter out tracks with no Spotify match
        before = len(tracks)
        tracks = [t for t in tracks if t.get("spotify_track_id")]
        after = len(tracks)
        logger.info(f"🧹 STEP 3: Filtered out {before - after} tracks without Spotify ID")

        if max_step == 3:
            return {"message": "Stopped after STEP 3", "count": len(tracks)}

        # ───────────────── STEP 4 ─────────────────
        logger.debug("📋 STEP 4: Post-enrich summary (log only)")
        # (Optional: log titles/ids here)

        if max_step == 4:
            return {"message": "Stopped after STEP 4"}

        # ───────────────── STEP 5 ─────────────────
        logger.debug("🧹 STEP 5: Handle remaining missing Spotify IDs by replacement")
        for tr in list(tracks):
            if not tr.get("spotify_track_id"):
                handle_missing_track(tr, tracks)

        if max_step == 5:
            return {"message": "Stopped after STEP 5"}

        # ───────────────── STEP 6 ─────────────────
        logger.debug("🗑 STEP 6: Remove any tracks still missing Spotify IDs")
        tracks = [t for t in tracks if t.get("spotify_track_id")]

        if max_step == 6:
            return {"message": "Stopped after STEP 6"}

        # ───────────────── STEP 7 ─────────────────
        logger.debug("➕ STEP 7: Fill from spares until target_count reached")
        # Try spares one-by-one; enrich each until we meet target_count
        for spare in list(spares):
            if len(tracks) >= request.target_count:
                break
            spare_norm = _normalize_artist_collab(_to_snake_track(spare))
            enriched_list = enrich_tracks_with_spotify([spare_norm], is_test_mode=False)
            enriched = enriched_list[0] if enriched_list else None
            if enriched and enriched.get("spotify_track_id"):
                enriched["rank"] = len(tracks) + 1
                tracks.append(enriched)

        if max_step == 7:
            return {"message": "Stopped after STEP 7", "count": len(tracks)}

        # ───────────────── STEP 8 ─────────────────
        logger.debug("🔢 STEP 8: Reassign ranks")
        reassign_ranks(tracks)

        if max_step == 8:
            return {"message": "Stopped after STEP 8"}

        # ───────────────── STEP 9 ─────────────────
        logger.debug("🖊 STEP 9: Add XAI descriptions (intro/detail) + optional artist bios")
        # Prepare a minimal payload compatible with your XAI helper
        payload_for_xai = {"tracks": tracks}

        described = get_track_descriptions_from_xai(
            track_data=payload_for_xai,
            language=request.language,
            decade="Collection",     # label for context
            genre=theme,             # display theme as "genre" context
        )

        if not described or "tracks" not in described or len(described["tracks"]) != len(tracks):
            raise HTTPException(status_code=500, detail="Failed to generate track descriptions (intro/detail)")

        tracks = described["tracks"]

        # Optional: artist bios table then map onto tracks where helpful
        try:
            unique_artists = sorted({(t.get("artist_name") or "").strip() for t in tracks if t.get("artist_name")})
            artist_rows = [{"artist_name": a} for a in unique_artists if a]
            artist_described = get_artist_descriptions_from_xai(artist_rows, request.language) or []
            bios = {
                (a.get("artist_name") or "").strip().lower(): a.get("artist_description")
                for a in artist_described if a.get("artist_name")
            }
            for t in tracks:
                nm = (t.get("artist_name") or "").strip().lower()
                if nm in bios and bios[nm]:
                    t["artist_description"] = bios[nm]
        except Exception as e:
            logger.warning("Artist bios step skipped: %s", e)

        if max_step == 9:
            return {"message": "Stopped after STEP 9"}

        # ───────────────── STEP 10 ─────────────────
        logger.debug("💾 STEP 10: Save JSON to data/json_files/collections/{slug}.json")
        # Harmonize mode flag vs featured artist (parity with decade-genre save step)
        def _harmonize_mode_and_feature(t: dict) -> None:
            feat = (t.get("featured_artist") or "")
            if not isinstance(feat, str):
                feat = str(feat)
            feat = feat.strip()
            flag = (t.get("mode_flag") or "").strip().upper()
            if feat and flag in ("", "SOLO"):
                t["mode_flag"] = "DUET"
            if not feat and flag in ("DUET", "FEATURED"):
                t["mode_flag"] = "SOLO"
            base = t.get("track_name") or ""
            t["track_display_name"] = f"{base} (feat. {feat})" if feat else base

        for t in tracks:
            _harmonize_mode_and_feature(t)

        out = {
            "collection": {
                "name": theme,
                "slug": slug,
                "type": "COLLECTION",
                "language": normalize_language_code(request.language),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            },
            "tracks": [
                {
                    "ranking": t.get("rank"),
                    "title": t.get("track_name"),
                    "artistName": t.get("artist_name"),
                    "year": t.get("year_released"),
                    "spotifyTrackId": t.get("spotify_track_id"),
                    "albumName": t.get("album_name"),
                    "albumArtUrl": t.get("album_art_url"),
                    # new copy fields
                    "intro": t.get("intro"),
                    "detail": t.get("detail"),
                    # optional helpers
                    "modeFlag": (t.get("mode_flag") or "").upper(),
                    "featuredArtist": t.get("featured_artist") or None,
                    "trackDisplayName": t.get("track_display_name"),
                    "artistDescription": t.get("artist_description"),
                }
                for t in tracks
            ],
        }

        base = Path("data/json_files/collections")
        base.mkdir(parents=True, exist_ok=True)
        final_path = base / f"{slug}.json"
        with final_path.open("w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)

        if max_step == 10:
            return {"message": "Stopped after STEP 10", "file": str(final_path)}

        # ───────────────── STEP 11 ─────────────────
        logger.debug("📊 STEP 11: Done (summary in response)")
        return {
            "message": "JSON created successfully",
            "file": str(final_path),
            "collection": theme,
            "track_count": len(out["tracks"]),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Actionable exception handling (same as decade-genre)
    # ─────────────────────────────────────────────────────────────────────────
    except HTTPException:
        raise
    except XAIQuotaError as e:
        logger.warning("💳 XAI quota exhausted: %s", e)
        raise HTTPException(status_code=409, detail={"reason": "xai_quota_exhausted", "message": str(e)})
    except XAIRateLimitError as e:
        logger.warning("⏳ XAI rate limited: %s", e)
        raise HTTPException(status_code=429, detail={"reason": "xai_rate_limited", "message": str(e)})
    except Timeout as e:
        logger.warning("🌐 Upstream timeout: %s", e)
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except (RequestsHTTPError, RequestException) as e:
        logger.warning("🌐 Upstream service error: %s", e)
        raise HTTPException(status_code=502, detail="Upstream service error")
    except Exception as e:
        logger.exception("❌ Unhandled error in collections.generate-json")
        raise HTTPException(status_code=500, detail="Internal server error")
