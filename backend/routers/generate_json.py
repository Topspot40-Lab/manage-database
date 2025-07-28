# backend/routers/generate_json.py

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
import json
from backend.services.spotify.missing_log import (
    handle_missing_track,
    reassign_ranks,
)

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
            name = t.get("trackName") or t.get("track_name")
            artist = t.get("artistName") or t.get("artist_name")
            track_id = t.get("spotify_track_id")
            if track_id:
                pass
                # logger.debug(f"   #{rank:02d} — {name} by {artist} 🎧 {track_id}")
            else:
                logger.warning(f"   #{rank:02d} — {name} by {artist} ❌ MISSING Spotify ID")


        logger.debug("🧾 STEP 4.E: Final JSON preview (pretty-printed)")
        logger.debug(json.dumps(final_json, indent=2, ensure_ascii=False))

        logger.info("🛑 Step 4 ----- Complete")

        if max_step == 4:
            logger.info("🛑 Stopping after STEP 4 as requested")
            return {"message": "Stopped after STEP 4", "preview": final_json}

        # ───────────── STEP 5 - STEP 11 (unchanged) ─────────────
        # Make sure all the following code stays at **this** indent.
        # … STEP 5 replacement logic …
        # … STEP 6 remove invalid …
        # … STEP 7 add spares …
        # … STEP 8 reassign ranks …
        # … STEP 9 rebuild artist table …
        # … STEP 10 save JSON …
        # … STEP 11 summary …

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
            missing_keys = [key for key in ("trackName", "artistName") if key not in spare]
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
                logger.info(f"✅ Spare track added: {rebuilt['artist_display_name']}")

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

        # 👨‍🎤 STEP 9: Rebuilding artist table from track data
        # logger.debug("👨‍🎤 STEP 9: Rebuilding artist table from track data")
        # artist_lookup = {}
        # for t in tracks:
        #     aid = t.get("spotify_artist_id")
        #     if not aid:
        #         continue
        #     if aid not in artist_lookup:
        #         artist_lookup[aid] = {
        #             "artist_name": t.get("artist_name"),
        #             "spotify_artist_id": aid,
        #             "artist_artwork": t.get("artist_artwork"),
        #             "artist_description": None,
        #             "artist_mp3_url": None,
        #             "not_on_spotify": t.get("not_on_spotify", False)
        #         }
        # final_json[["artist"] = list(artist_lookup.values())
        #
        # logger.info("🛑 Step 9 ----- Complete")

        # 💾 STEP 10: Saving final JSON to file
        filepath = get_json_path(request.decade, request.genre, request.language[:2])
        logger.debug(f"💾 STEP 10: Saving final JSON to file: {filepath}")

        decade = request.decade.lower()
        genre = request.genre.lower()

        # Use timestamped filename if running in test mode
        if is_test_mode:
            filename = f"{decade}_{genre}_en_test_{now_dt.strftime('%Y%m%d_%H%M%S')}.json"
        else:
            filename = f"{decade}_{genre}_en.json"

        logger.info(f"🧮 STEP 10: Saving {len(track_list)} track(s) to {filename}")
        # assert len(track_list) <= 5, "🚨 Something's off — too many tracks being saved!"


        # 🕵️ Log final JSON tables before saving
        track_list = final_json.get("track", [])
        ranking_list = final_json.get("track_ranking", [])
        artist_list = final_json.get("artist", [])

        logger.debug(
            f"📂 STEP 10: FINAL JSON CONTENT PREVIEW:\n"
            f"🧾 track ({len(track_list)} entries):\n" +
            "\n".join([f"   - #{t.get('rank')}: {t.get('track_name')} by {t.get('artist_name')}" for t in
                       track_list]) + "\n" +
            f"🧾 track_ranking ({len(ranking_list)} entries):\n" +
            "\n".join([f"   - #{r.get('rank')}: {r.get('track_name')} by {r.get('artist_name')}" for r in
                       ranking_list]) + "\n" +
            f"🧾 artist ({len(artist_list)} entries):\n" +
            "\n".join([f"   - {a.get('artist_name')} ({a.get('spotify_artist_id')})" for a in artist_list])
        )

        logger.info(f"🧾 FINAL JSON: {len(track_list)} track(s)")

        save_full_json_file(
            payload=final_json,
            decade=decade,
            filename=filename
        )

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

        # Save the full final_json to the file
        # with open(filepath, "w", encoding="utf-8") as f:
        #     json.dump(final_json, f, indent=2, ensure_ascii=False)
        # logger.debug(f"✅ JSON saved to {filepath}")

        logger.info("🛑 Step 11 ----- JSON Creation Complete")

        return {
            "message": "JSON created successfully",
            "file": str(filepath),
            "version": "v3-official",
            "track_count": len(tracks)
        }


    except Exception as e:
        logger.exception("❌ Unexpected error in generate_track_json")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
