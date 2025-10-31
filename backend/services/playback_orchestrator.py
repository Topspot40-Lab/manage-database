from backend.services.radio_runtime import (
    log_header_and_texts, narration_keys_for,
    play_intro_then_bed, play_narrations, play_track_with_skip
)
from backend.config.volume import PLAY_FULL_TRACK

async def play_one_server_side(*, lang: str, track, artist,
                               play_intro: bool, play_detail: bool,
                               play_artist_description: bool, play_track: bool):
    # header log (no DG/collection rows context)
    log_header_and_texts(lang=lang, track=track, artist=artist, tr_rows=[])

    # narrations
    intro_jobs = []  # keep empty unless you add a collection/other intro generator
    detail_bucket, detail_key, artist_bucket, artist_key = narration_keys_for(lang=lang, track=track, artist=artist)

    if (play_intro and intro_jobs) or (play_detail and detail_bucket and detail_key) or (play_artist_description and artist_bucket and artist_key):
        await play_intro_then_bed()

    await play_narrations(
        play_intro=play_intro, play_detail=play_detail, play_artist=play_artist_description,
        intro_jobs=intro_jobs,
        detail_bucket=detail_bucket, detail_key=detail_key,
        artist_bucket=artist_bucket, artist_key=artist_key
    )

    skipped_mid = False
    if play_track and track.spotify_track_id:
        skipped_mid = await play_track_with_skip(track=track, full_flag=PLAY_FULL_TRACK)

    return {"skipped": skipped_mid}
