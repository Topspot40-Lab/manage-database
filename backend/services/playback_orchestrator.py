from backend.services.radio_runtime import (
    log_header_and_texts,
    narration_keys_for,
    play_narrations,
    play_track_with_skip,
    _respect_user_controls,
)

from backend.config.volume import PLAY_FULL_TRACK


async def play_one_server_side(
    *,
    lang: str,
    track,
    artist,
    play_intro: bool,
    play_detail: bool,
    play_artist_description: bool,
    play_track: bool,
):
    """
    Enhanced single-track playback orchestrator.

    - Logs header
    - Respects pause / stop / cancel
    - Plays intro / detail / artist narrations
    - Plays Spotify track with skip + fade
    """

    # ─────────────────────────────────────────────
    # 0️⃣ Prelude: respect any pending controls
    # ─────────────────────────────────────────────
    await _respect_user_controls()

    # ─────────────────────────────────────────────
    # 1️⃣ Header log (no DG / collection context)
    # ─────────────────────────────────────────────
    log_header_and_texts(
        lang=lang,
        track=track,
        artist=artist,
        tr_rows=[],  # single play has no ranking rows
    )

    await _respect_user_controls()

    # ─────────────────────────────────────────────
    # 2️⃣ Narration setup
    # ─────────────────────────────────────────────
    intro_jobs: list = []  # single-track play never uses intro jobs

    detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(
        lang=lang,
        track=track,
        artist=artist,
    )

    # ─────────────────────────────────────────────
    # 3️⃣ Narration (unified pipeline)
    # ─────────────────────────────────────────────
    await play_narrations(
        play_intro=play_intro,
        play_detail=play_detail,
        play_artist=play_artist_description,
        intro_jobs=intro_jobs,
        detail_bucket=detail_bucket,
        detail_key=detail_key,
        artist_bucket=artist_bucket,
        artist_key=artist_key,
        lang=lang,
        mode="single",
        rank=None,
        track_name=track.track_name,
        artist_name=artist.artist_name,
    )

    await _respect_user_controls()

    # ─────────────────────────────────────────────
    # 4️⃣ Spotify track playback
    # ─────────────────────────────────────────────
    skipped_mid = False

    if play_track and track.spotify_track_id:
        skipped_mid = await play_track_with_skip(
            track=track,
            lang=lang,
            mode="single",
            rank=None,
            track_name=track.track_name,
            artist_name=artist.artist_name,
            full_flag=PLAY_FULL_TRACK,
        )

    # ─────────────────────────────────────────────
    # 5️⃣ Final checkpoint
    # ─────────────────────────────────────────────
    await _respect_user_controls()

    return {"skipped": skipped_mid}
