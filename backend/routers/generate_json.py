# backend/routers/generate_json.py
from json import JSONDecodeError
from pydantic import ValidationError
from requests import HTTPError as RequestsHTTPError
from requests.exceptions import Timeout, RequestException
from backend.utils.naming import slug_underscore, normalize_language_code
# If you have custom XAI errors (recommended):
from backend.services.xai_errors import XAIQuotaError, XAIRateLimitError
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
import json
from backend.services.spotify.missing_log import (
    handle_missing_track,
    reassign_ranks,
)
import re
from pathlib import Path
from backend.builders.track_builder import build_track_entry
from backend.builders.json_builder import build_final_json
from backend.services.track_generator import enrich_tracks_with_spotify
from backend.routers.steps.step_01_get_tracks import run as step01_get_tracks
from backend.services.xai_descriptions import get_track_descriptions_from_xai
from backend.services.xai_artist_detail import get_artist_descriptions_from_xai
from backend.utils.json_helpers import save_full_json_file
from shared.filepaths import get_json_path
from pydantic import BaseModel

from backend.utils.log_helpers import log_generate_json_summary

logger = logging.getLogger(__name__)
logger.debug("📦 Final step message...")

router = APIRouter()



class TrackRequest(BaseModel):
    decade: str = "1950s"
    genre: str = "country"
    language: str  = "english"
    num_tracks: int = 1

def _rank2(rank):
    try:
        return f"{int(rank):02d}"
    except Exception:
        return "--"



# connectors → how to treat the collab
# FEATURED: leave first as main, put the rest into featured_artist
# DUET: treat as a collab (still keep the first as main for search)
_CONNECTORS = [
    (r"\s+feat\.\s+", "FEATURED"),
    (r"\s+ft\.\s+", "FEATURED"),
    (r"\s+featuring\s+", "FEATURED"),
    (r"\s+with\s+", "DUET"),
    (r"\s+con\s+", "DUET"),       # es
    (r"\s+y\s+", "DUET"),         # es
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
            # Only set mode if caller didn’t supply one
            if not (t.get("mode_flag") or "").strip():
                t["mode_flag"] = mode
            # capture featured/collab partner(s) for later
            # (your insert code already guards and only uses these if mode is DUET/FEATURED)
            t["featured_artist"] = rest
            return t
    return t



def _to_snake_track(d: dict) -> dict:
    out = {}
    out["track_name"] = d.get("track_name") or d.get("trackName") or d.get("traackName") or d.get("title")
    out["artist_name"] = d.get("artist_name") or d.get("artistName") or d.get("artist")
    out["year_released"] = d.get("year_released") or d.get("yearReleased") or d.get("release_year")
    out["album_name"] = d.get("album_name") or d.get("albumName")
    out["rank"] = d.get("rank")

    # 👇 ensure these keys always exist
    out["mode_flag"] = d.get("mode_flag") or d.get("modeFlag") or ""
    out["mode_flag_detail"] = d.get("mode_flag_detail") or d.get("modeFlagDetail") or ""

    # pass through anything else
    for k, v in d.items():
        if k not in out:
            out[k] = v
    return out


# noinspection PyTypeChecker
@router.post("/generate-json", summary="Generate JSON from XAI + Spotify")
async def generate_track_json(
    request: TrackRequest,
    test_file_number: int = 0,
    max_step: int = 11
):
    try:  # ────────────────────────────────────────────────────────
        if not 1 <= max_step <= 11:
            raise HTTPException(status_code=400,
                                detail="max_step must be between 1 and 11")

        logger.debug("🟡 STEP 0: Starting generate_track_json")
        now_dt = datetime.now()
        now = now_dt.isoformat()

        # ───────────────── STEP 1 ─────────────────
        wrapped = step01_get_tracks(request, test_file_number=test_file_number)
        track_list = wrapped["tracks"]

        track_list = [_to_snake_track(t) for t in track_list]
        track_list = [_normalize_artist_collab(t) for t in track_list]  # 👈 add this line

        def _scan_for_missing(field: str, items: list, step_label: str):
            bad = []
            for i, it in enumerate(items, start=1):
                if field not in it or it.get(field) in (None, ""):
                    bad.append((i, list(it.keys())))
            if bad:
                logger.error(
                    f"❌ {step_label}: {len(bad)} item(s) missing '{field}'. "
                    f"Examples: {bad[:5]}"
                )
            else:
                logger.debug(f"✅ {step_label}: all items have '{field}'")

        _scan_for_missing("artist_name", track_list, "STEP 1 (model output)")


        if max_step == 1:
            logger.info("🛑 Stopping after STEP 1 as requested")
            return {
                "message": "Stopped after STEP 1",
                "track_count": len(track_list),
                "tracks": track_list
            }

        logger.info("🛑 Step 1 ----- Complete")

        # ───────────────── STEP 2 ─────────────────
        logger.debug("✍️ STEP 2: Skipped XAI description enrichment — moved to STEP 9")

        # Just wrap raw track list for compatibility with STEP 3
        enriched = {"tracks": track_list}

        if max_step == 2:
            logger.info("🛑 Stopping after STEP 2 as requested")
            return {
                "message": "Stopped after STEP 2",
                "track_count": len(enriched['tracks']),
                "tracks": enriched["tracks"]
            }

        logger.info("🛑 Step 2 ----- Complete")

        # ───────────────── STEP 3 ─────────────────
        logger.debug("✍️ STEP 3: Enriching tracks with Spotify API")
        enriched["tracks"] = enrich_tracks_with_spotify(
            enriched["tracks"], is_test_mode=(test_file_number > 0)
        )

        logger.debug(f"🔎 Enriched tracks after STEP 3: {len(enriched['tracks'])}")
        for t in enriched["tracks"]:
            logger.debug(
                f"   🎵 {t.get('track_name')} by {t.get('artist_name')} - track_id: {t.get('spotify_track_id')}")

        # ✅ Filter out tracks with no Spotify match
        before = len(enriched["tracks"])
        enriched["tracks"] = [t for t in enriched["tracks"] if t.get("spotify_track_id")]
        after = len(enriched["tracks"])
        # re-normalize in case enrich step added/renamed fields
        enriched["tracks"] = [_to_snake_track(t) for t in enriched["tracks"]]

        missing_modes = [i for i, t in enumerate(enriched["tracks"], 1) if "mode_flag" not in t]
        blanks = sum(1 for t in enriched["tracks"] if (t.get("mode_flag") or "") == "")
        logger.info(f"🧪 mode_flag present in all: {not missing_modes} | blanks: {blanks}/{len(enriched['tracks'])}")

        logger.info(f"🧹 STEP 3: Filtered out {before - after} tracks with no Spotify match")

        logger.info("🛑 Step 3 ----- Complete")

        if max_step == 3:
            logger.info("        🛑 Stopping after STEP 3 as requested")
            return {"message": "Stopped after STEP 3"}

        # ───────────────── STEP 4 ─────────────────
        logger.debug("🧱 STEP 4: Building full JSON structure from enriched data")
        is_test_mode = test_file_number > 0

        final_json, track_entries, artist_entries = build_final_json(
            enriched_tracks=enriched["tracks"],
            request=request,
            now=now,
            is_test_mode=is_test_mode
        )
        # ✅ STEP 4 Summary Output
        logger.debug("📋 STEP 4 SUMMARY: Track Listing")
        tracks = final_json["track"]
        for t in tracks:
            rank = t.get("rank")
            name = t.get("track_name", "")
            artist = t.get("artist_name", "")
            track_id = t.get("spotify_track_id")

            if track_id:
                logger.debug(f"   #{_rank2(rank)} — {name} by {artist} 🎧 {track_id}")
            else:
                logger.warning(f"   #{_rank2(rank)} — {name} by {artist} ❌ MISSING Spotify ID")

        logger.debug("🧾 STEP 4.E: Final JSON preview (pretty-printed)")
        logger.debug(json.dumps(final_json, indent=2, ensure_ascii=False))

        logger.info("🛑 Step 4 ----- Complete")

        if max_step == 4:
            logger.info("🛑 Stopping after STEP 4 as requested")
            return {"message": "Stopped after STEP 4", "preview": final_json}

        # 🧹 STEP 5: Handling tracks with missing Spotify IDs
        logger.debug("🧹 STEP 5: Handling tracks with missing Spotify IDs")
        tracks = final_json["track"]
        spare_tracks = final_json.get("spares", [])

        for track in tracks[:]:
            if not track.get("spotify_track_id"):
                handle_missing_track(track, tracks)

        logger.info("🛑 Step 5 ----- Complete")

        # 🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement
        logger.debug("🗑 STEP 6: Removing tracks still missing Spotify IDs after replacement")
        tracks = [t for t in tracks if t.get("spotify_track_id")]

        logger.info("🛑 Step 6 ----- Complete")

        # ➕ STEP 7: Filling in with spare tracks to ensure 40 total
        logger.debug("➕ STEP 7: Filling in with spare tracks to ensure 40 total")

        while len(tracks) < 40 and spare_tracks:
            spare = spare_tracks.pop(0)

            # normalize spare just like STEP 1/3
            spare = _to_snake_track(spare)

            missing_keys = [key for key in ("track_name", "artist_name") if key not in spare or not spare.get(key)]
            if missing_keys:
                logger.warning(f"⚠️ Skipping spare track due to missing keys: {missing_keys} — {spare}")
                continue

            try:
                rebuilt = build_track_entry(
                    spare,
                    request,
                    spotify_data=None,
                    now=now,
                    is_test_mode=is_test_mode
                )
                rebuilt["rank"] = len(tracks) + 1
                tracks.append(rebuilt)
                logger.info(
                    f"✅ Spare track added: {rebuilt.get('artist_name', '<unknown>')} — {rebuilt.get('track_name', '')}")
            except Exception as e:
                logger.warning(f"❌ Failed to rebuild spare track: {e}")
                continue

        logger.info("🛑 Step 7 ----- Complete")

        # 🔢 STEP 8: Reassigning ranks and finalizing track table
        logger.debug("🔢 STEP 8: Reassigning ranks and finalizing track table")
        reassign_ranks(tracks)
        final_json["track"] = tracks

        logger.info("🛑 Step 8 ----- Complete")

        # ✅ STEP 9: Add XAI descriptions after final rank assignment
        logger.debug("✍️ STEP 9: Adding XAI descriptions after rank reassignment")

        # 👇 Prepare enriched_for_xai with ranking + artist table for proper merging
        enriched_for_xai = {
            "tracks": tracks,
            "track_ranking": final_json.get("track_ranking", []),
            "artist_table": final_json.get("artist_table", [])
        }

        # 🎯 Generate descriptions and apply them to appropriate tables
        described = get_track_descriptions_from_xai(
            track_data=enriched_for_xai,
            language=request.language,
            decade=request.decade,
            genre=request.genre
        )

        # 🧪 Validate response
        if not described or "tracks" not in described or len(described["tracks"]) != len(tracks):
            raise HTTPException(status_code=500, detail="Failed to generate final track descriptions")

        # ✅ Update final_json with enriched outputs
        final_json["track"] = described["tracks"]
        final_json.update({
            "track_ranking": described.get("track_ranking", [])
        })

        final_json["artist_table"] = described.get("artist_table", [])

        # 🎙️ STEP 9.B: Add artist_description using XAI

        core_artists = final_json.get("artist", [])

        if core_artists:
            artist_described = get_artist_descriptions_from_xai(core_artists, request.language)
            desc_map = {
                a["artist_name"].strip().lower(): a["artist_description"]
                for a in artist_described
                if a.get("artist_description")
            }

            for artist in core_artists:
                name = artist.get("artist_name", "").strip().lower()
                if name in desc_map:
                    artist["artist_description"] = desc_map[name]
                    logger.debug(f"✅ Step 9.B Merged artist_description for '{artist.get('artist_name')}'")
                else:
                    logger.warning(f"⚠️ Step 9.BNo artist_description found for '{artist.get('artist_name')}'")

        logger.info("🛑 Step 9 ----- Complete")

        # 💾 STEP 10: Saving final JSON to file

        # 10.0 Uppercase any existing mode flags (defensive)
        for t in (final_json.get("track") or []):
            mf = t.get("mode_flag")
            if mf is not None:
                t["mode_flag"] = str(mf).upper().strip()

        lang_code = normalize_language_code(request.language)  # "es", not "sp"
        filepath = get_json_path(request.decade, request.genre, lang_code)
        logger.debug(f"💾 STEP 10: Saving final JSON to dir: {filepath}")

        decade_slug = slug_underscore(request.decade)
        genre_slug = slug_underscore(request.genre)
        # keep directory name as it exists on disk (e.g., "before 1990s")
        decade_dir = request.decade

        filename = (
            f"{decade_slug}_{genre_slug}_{lang_code}_test_{now_dt.strftime('%Y%m%d_%H%M%S')}.json"
            if is_test_mode else
            f"{decade_slug}_{genre_slug}_{lang_code}.json"
        )

        base_dir = Path(filepath)
        if base_dir.suffix:  # if get_json_path returned a file
            base_dir = base_dir.parent

        final_path = base_dir / filename
        final_path.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(f"💾 STEP 10: Target directory: {final_path.parent}")
        logger.info(f"🧮 STEP 10: Saving {len(tracks)} track(s) to {final_path.name}")

        # ---- STEP 10.A: normalize language + harmonize mode/featured before save ----
        final_json["language"] = lang_code  # e.g., "es"

        # Be defensive: only set on dict items
        for tl in (final_json.get("tracklist") or []):
            if isinstance(tl, dict):
                tl["language"] = lang_code

        def _harmonize_mode_and_feature(t: dict) -> None:
            feat = (t.get("featured_artist") or "")
            if not isinstance(feat, str):
                feat = str(feat)
            feat = feat.strip()

            flag = (t.get("mode_flag") or "").strip().upper()

            # If there is a featured artist but flag says SOLO/blank, mark as DUET
            if feat and flag in ("", "SOLO"):
                t["mode_flag"] = "DUET"
            # If no featured artist but flag says DUET/FEATURED, reset to SOLO
            if not feat and flag in ("DUET", "FEATURED"):
                t["mode_flag"] = "SOLO"

            # Keep display name in sync
            base = t.get("track_name") or ""
            t["track_display_name"] = f"{base} (feat. {feat})" if feat else base

        for t in (final_json.get("track") or []):
            _harmonize_mode_and_feature(t)

        save_full_json_file(payload=final_json, decade=decade_dir, filename=filename)
        logger.info("🛑 Step 10 ----- Complete")

        # 📊 STEP 11: Logging summary report
        logger.debug("📊 STEP 11: Logging summary report")
        log_generate_json_summary(
            tracks=track_entries,
            artists=artist_entries,

            now=datetime.now(),
            category=request.decade,
            genre=request.genre,
            errors=[]
        )


        logger.info("🛑 Step 11 ----- JSON Creation Complete")
        return {
            "message": "JSON created successfully",
            "file": str(final_path),  # <— use final_path, not filepath
            "version": "v3-official",
            "track_count": len(tracks),
        }

    # ──────────────────────────────────────────────────────────────────────────────
    # Specific, actionable exception handling
    # ──────────────────────────────────────────────────────────────────────────────
    except HTTPException:
        # Re-raise FastAPI HTTP errors unchanged so status codes propagate.
        raise
    except XAIQuotaError as e:
        logger.warning("💳 XAI quota exhausted: %s", e)
        raise HTTPException(
            status_code=409,
            detail={"reason": "xai_quota_exhausted", "message": str(e)},
        )
    except XAIRateLimitError as e:
        logger.warning("⏳ XAI rate limited: %s", e)
        raise HTTPException(
            status_code=429,
            detail={"reason": "xai_rate_limited", "message": str(e)},
        )
    except Timeout as e:
        logger.warning("🌐 Upstream timeout: %s", e)
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except (RequestsHTTPError, RequestException) as e:
        logger.warning("🌐 Upstream HTTP error: %s", e)
        raise HTTPException(status_code=502, detail="Upstream service error")
    except (ValidationError, JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.exception("🧩 Data/parse/validation error in generate_json")
        raise HTTPException(status_code=400, detail=f"Bad input/state: {e}")
    except Exception as e:  # noqa: TRY002  (keep a final safety net)
        logger.exception("❌ Unhandled error in generate_json")
        raise HTTPException(status_code=500, detail="Internal server error")
