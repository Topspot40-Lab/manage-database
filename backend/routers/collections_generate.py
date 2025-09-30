# backend/routers/collections_generate.py
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone  # ← moved here

from backend.services.curate import (
    curate_tracks_via_xai,
    list_available_themes,   # helper we added
    describe_theme,          # helper we added
)


from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from requests import HTTPError as RequestsHTTPError
from requests.exceptions import Timeout, RequestException
from backend.services.spotify.enrich_artist_artwork import enrich_artist_table_with_spotify

# XAI error helpers (same pattern as decade-genre pipeline)
from backend.services.xai_errors import XAIQuotaError, XAIRateLimitError

# Spotify enrich step (same function used in decade-genre flow)
from backend.services.track_generator import enrich_tracks_with_spotify

from backend.services.xai_descriptions import get_collection_descriptions_from_xai
from backend.services.collections_utils import build_ranking_from_tracks, validate_compact_ranks

# Helpers consistent with your pipeline
from backend.utils.naming import slug_underscore, normalize_language_code
from backend.services.spotify.missing_log import handle_missing_track, reassign_ranks

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collections")

from contextlib import contextmanager
import backend.config as _cfg

@contextmanager
def temp_flags(**kw):
    old = {k: getattr(_cfg, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(_cfg, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(_cfg, k, v)

# --- helpers: normalize explicit flag + album art + safe detail ----------------
from typing import Any, Dict, List

ALBUM_IMAGE_KEYS = (
    "album_art_url", "albumArtUrl", "album_artwork", "album_image_url", "albumImageUrl"
)

def _pick_album_art_url(t: Dict[str, Any]) -> str | None:
    # Prefer any pre-normalized keys first
    for k in ALBUM_IMAGE_KEYS:
        url = t.get(k)
        if isinstance(url, str) and url.strip():
            return url.strip()

    # Fall back to common Spotify shapes
    # 1) flat list of images (your enrich step may stash this)
    images = t.get("album_images") or t.get("images")
    if isinstance(images, list) and images:
        # prefer largest first (Spotify returns largest first usually)
        for img in images:
            if isinstance(img, dict) and isinstance(img.get("url"), str) and img["url"].strip():
                return img["url"].strip()

    # 2) nested album.images (typical Spotify object)
    album = t.get("album")
    if isinstance(album, dict):
        images = album.get("images")
        if isinstance(images, list) and images:
            for img in images:
                if isinstance(img, dict) and isinstance(img.get("url"), str) and img["url"].strip():
                    return img["url"].strip()
    return None

def _coerce_is_explicit(t: Dict[str, Any]) -> bool:
    # Accept a variety of upstream shapes
    val = (
        t.get("is_explicit", None) if "is_explicit" in t else
        t.get("explicit", None) if "explicit" in t else
        t.get("isExplicit", None)
    )
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in {"true", "t", "yes", "y", "1"}:
            return True
        if s in {"false", "f", "no", "n", "0"}:
            return False
    # default if unknown
    return False

def _finalize_track_triplet_fields(tracks: List[Dict[str, Any]]) -> None:
    """
    Ensures each track has:
      - detail (string or None, but try hard to fill)
      - is_explicit (bool)
      - album_artwork (string or None)
    """
    for t in tracks:
        # is_explicit
        t["is_explicit"] = _coerce_is_explicit(t)

        # album_artwork
        album_url = _pick_album_art_url(t)
        t["album_artwork"] = album_url if album_url else None

        # detail (leave string/None; don't invent text here)
        # If some other key already has the long description, mirror it.
        if not t.get("detail"):
            # inside _finalize_track_triplet_fields(...)
            t["detail"] = (
                    t.get("detail_en")
                    or t.get("description")
                    or t.get("trackDetail")
                    or t.get("track_detail")
                    or None
            )


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
    enable_rank_intro: Optional[bool] = Query(None),
    enable_track_detail: Optional[bool] = Query(None),
    enable_artist_detail: Optional[bool] = Query(None),
) -> Dict[str, Any]:

    try:
        logger.debug("🟡 STEP 0: Starting collections.generate-json")

        # Normalize input → canonical slug + display name using curate’s registry
        resolved = describe_theme(slug_underscore(request.slug))
        slug = resolved["slug"]  # stable slug (e.g., "power_ballads")
        theme = resolved["display_name"]  # display name (e.g., "Power Ballads")
        lang_code = normalize_language_code(request.language)

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

        if not raw_candidates:
            raise HTTPException(status_code=502, detail=f"No tracks curated for theme '{theme}'")

        # ───────────────── STEP 2 ─────────────────
        logger.debug("✍️ STEP 2: Skipped (legacy descriptions moved to STEP 9)")
        if max_step == 2:
            return {"message": "Stopped after STEP 2", "count": len(tracks)}

        # ───────────────── STEP 3 ─────────────────
        logger.debug("🎧 STEP 3: Enriching with Spotify")
        tracks = [_to_snake_track(t) for t in tracks]
        tracks = [_normalize_artist_collab(t) for t in tracks]

        tracks = enrich_tracks_with_spotify(tracks, is_test_mode=False)



        if tracks:
            logger.debug("STEP 3 sample keys: %s", sorted(tracks[0].keys()))

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

        # Build a ranking array from tracks (rank + spotify_track_id)
        ranking = build_ranking_from_tracks(tracks)
        ok, msg = validate_compact_ranks(ranking)
        if not ok:
            logger.warning(f"Ranking validation: {msg}")

        if max_step == 8:
            return {"message": "Stopped after STEP 8"}

        # ───────────────── STEP 8.5 ─────────────────
        logger.debug("🧭 STEP 8.5: Build artist table from tracks & enrich with Spotify artwork/IDs")

        # Build a unique artist list from tracks (best-effort IDs from track enrichment)
        artist_tbl = []
        seen_artists = set()
        for t in tracks:
            name = (t.get("artist_name") or "").strip()
            if not name:
                continue
            k = name.lower()
            if k in seen_artists:
                continue
            seen_artists.add(k)
            artist_tbl.append({
                "artist_name": name,
                # Try to carry over any IDs that the track enrichment already found
                "spotify_artist_id": t.get("spotify_artist_id") or t.get("artist_id") or None,
                "artist_artwork": None,
                "artist_description": None,  # will merge after XAI
            })

        # Fill artist_artwork (and missing spotify_artist_id) from Spotify
        artist_tbl = enrich_artist_table_with_spotify(
            artist_table=artist_tbl,
            tracks_after_step3=tracks,      # we have enriched tracks here
            fill_missing_ids_via_search=True
        )


        # ───────────────── STEP 9 ─────────────────
        logger.debug("🖊 STEP 9: Add XAI descriptions (intro/detail/artist per flags)")

        flag_kwargs = {}
        if enable_rank_intro is not None: flag_kwargs["ENABLE_RANK_INTRO"] = enable_rank_intro
        if enable_track_detail is not None: flag_kwargs["ENABLE_TRACK_DETAIL"] = enable_track_detail
        if enable_artist_detail is not None: flag_kwargs["ENABLE_ARTIST_DETAIL"] = enable_artist_detail

        def _run_xai():
            return get_collection_descriptions_from_xai(
                tracks,
                language=lang_code,  # normalized "en"/"es"
                slug=slug,
                decade=None,
                genre=theme,
                ranking=ranking,  # maps intros to both tracks & ranking
            )

        if flag_kwargs:
            with temp_flags(**flag_kwargs):
                described = _run_xai()
        else:
            described = _run_xai()

        if not described or "tracks" not in described:
            raise HTTPException(status_code=500, detail="Failed to generate collection descriptions")

        tracks = described["tracks"]
        ranking = described.get("track_ranking", ranking)

        # ✅ Normalize detail / is_explicit / album_artwork now that XAI + Spotify data are present
        _finalize_track_triplet_fields(tracks)


        # Merge artist descriptions (if any) into the artist table
        # Priority: explicit artist table from XAI → per-track artist_description fields
        desc_by_name = {}
        # If your get_collection_descriptions_from_xai returns artist_table, prefer it:
        if described.get("artist_table"):
            for a in described["artist_table"]:
                nm = (a.get("artist_name") or "").strip().lower()
                if nm and a.get("artist_description"):
                    desc_by_name[nm] = a["artist_description"]

        # Fallback: scrape from the track items themselves
        for t in tracks:
            nm = (t.get("artist_name") or "").strip().lower()
            ad = t.get("artist_description")
            if nm and ad and nm not in desc_by_name:
                desc_by_name[nm] = ad

        # Apply to artist_tbl
        for a in artist_tbl:
            nm = (a.get("artist_name") or "").strip().lower()
            if nm in desc_by_name and not a.get("artist_description"):
                a["artist_description"] = desc_by_name[nm]

        # ───────────── helpers (put just above STEP 10) ─────────────
        from typing import Optional, Any

        def _resolve_album_art(t: dict) -> Optional[str]:
            return (
                    t.get("album_art_url")
                    or t.get("album_artwork")
                    or t.get("albumImageUrl")
                    or t.get("album_image_url")
                    or t.get("albumArtUrl")
                    or None
            )

        def _to_bool_or_none(v: Any) -> Optional[bool]:
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            if s in {"true", "1", "yes"}:
                return True
            if s in {"false", "0", "no"}:
                return False
            return None

        def _to_int_or_none(v: Any) -> Optional[int]:
            try:
                return int(v)
            except Exception:
                return None

        def _harmonize_mode_and_feature(t: dict) -> None:
            feat = t.get("featured_artist")
            if not isinstance(feat, str):
                feat = "" if feat is None else str(feat)
            feat = feat.strip()

            flag = (t.get("mode_flag") or "").strip().upper()

            # If there is a featured artist → ensure DUET
            if feat and flag in ("", "SOLO"):
                t["mode_flag"] = "DUET"
            # If no featured artist and flag empty → mark SOLO
            if not feat and flag == "":
                t["mode_flag"] = "SOLO"
            # If no featured artist but flag is DUET/FEATURED → reset to SOLO
            if not feat and flag in ("DUET", "FEATURED"):
                t["mode_flag"] = "SOLO"

            base = t.get("track_name") or ""
            t["track_display_name"] = f"{base} (feat. {feat})" if feat else base
            # Also keep a normalized featured name string or None for DB
            t["featured_artist"] = feat or None

        # ───────────────── STEP 10 ─────────────────
        logger.debug("💾 STEP 10: Save JSON to data/json_files/collections/{slug}.json")

        # Harmonize per-track once
        for t in tracks:
            _harmonize_mode_and_feature(t)

        # Build legacy artist table (preserves IDs + artwork + descriptions)
        artists_legacy = [
            {
                "artist_name": a.get("artist_name"),
                "spotify_artist_id": a.get("spotify_artist_id"),
                "artist_artwork": a.get("artist_artwork"),
                "artist_description": a.get("artist_description"),
            }
            for a in artist_tbl
        ]

        created_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

        tracks_legacy = []
        for t in tracks:
            mf = (t.get("mode_flag") or "").upper() or None

            explicit = t.get("is_explicit")
            if explicit is None:
                explicit = t.get("explicit")  # Spotify may use 'explicit'
            explicit = _to_bool_or_none(explicit)

            tracks_legacy.append({
                "track_name": t.get("track_name"),
                "artist_name": t.get("artist_name"),
                "spotify_track_id": t.get("spotify_track_id"),
                "duration_ms": _to_int_or_none(t.get("duration_ms")),
                "popularity": _to_int_or_none(t.get("popularity")),
                "album_artwork": t.get("album_artwork") or _resolve_album_art(t),  # prefer normalized
                "year_released": _to_int_or_none(t.get("year_released")),
                "is_explicit": t.get("is_explicit", False),  # always boolean
                "created_at": created_iso,
                "detail": (t.get("detail") or None),
                "album_name": t.get("album_name"),
                "mode_flag": mf,
                "featured_artist_name": t.get("featured_artist") or None,
                "featured_artist_sid": t.get("featured_artist_sid") or None,  # stays None unless you add it upstream
                "artist_display_name": t.get("artist_name"),
            })

        # Legacy ranking array (snake_case) expected by the upsert
        rankings_legacy = []
        for r in ranking:
            rankings_legacy.append({
                "rank": r.get("rank"),
                "spotify_track_id": r.get("spotify_track_id"),
                "track_id": r.get("track_id"),  # keep if present
                "intro": r.get("intro"),  # XAI intro per rank if you set it
                "created_at": created_iso,
            })

        out = {
            "collection": {
                "name": theme,
                "slug": slug,
                "type": "COLLECTION",
                "language": normalize_language_code(request.language),
                "created_at": created_iso,
            },

            # ✅ Legacy sections for the upsert endpoint
            "artist": artists_legacy,  # list of artists
            "track": tracks_legacy,  # list of tracks (snake_case)
            "track_ranking": rankings_legacy,

            # ✅ Keep your current camelCase consumers happy too
            "trackRanking": [
                {
                    "rank": r.get("rank"),
                    "spotifyTrackId": r.get("spotify_track_id"),
                    "trackId": r.get("track_id"),
                    "intro": r.get("intro"),
                }
                for r in ranking
            ],
            "tracks": [
                {
                    "ranking": t.get("rank"),
                    "title": t.get("track_name"),
                    "artistName": t.get("artist_name"),
                    "year": t.get("year_released"),
                    "spotifyTrackId": t.get("spotify_track_id"),
                    "albumName": t.get("album_name"),
                    "albumArtUrl": t.get("album_artwork") or _resolve_album_art(t),

                    "intro": t.get("intro"),
                    "detail": t.get("detail"),  # already normalized by the finalizer

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


@router.get("/themes", summary="List available collection themes (slugs)")
def list_collection_themes():
    slugs = list_available_themes()
    return {
        "themes": [
            {"slug": s, "name": describe_theme(s)["display_name"]}
            for s in slugs
        ]
    }
