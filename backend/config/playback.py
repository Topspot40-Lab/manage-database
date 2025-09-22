import os, logging
from .helpers import env_bool, env_int, clamp, extract_spotify_track_id as _extract
log = logging.getLogger("config.playback")

BED_ENABLED         = env_bool("BED_ENABLED", True)
MAIN_VOLUME_PERCENT = env_int("MAIN_VOLUME_PERCENT", 60)
BED_FADE_MS         = env_int("BED_FADE_MS", 1200)
BED_DEVICE_ID       = os.getenv("BED_DEVICE_ID") or None

_bed_id_raw = os.getenv("BED_SPOTIFY_TRACK_ID") or os.getenv("SPOTIFY_BED_TRACK_ID") or "2ggZjjqszgPpFUMyCwPrrj"
BED_SPOTIFY_TRACK_ID = _extract(_bed_id_raw)
SPOTIFY_BED_TRACK_ID = BED_SPOTIFY_TRACK_ID

BED_FACTOR = None
_bed_factor_env = (os.getenv("BED_FACTOR") or "").strip()
if _bed_factor_env:
    try:
        BED_FACTOR = float(_bed_factor_env)
    except ValueError:
        log.warning("Invalid BED_FACTOR '%s'; ignoring.", _bed_factor_env)

if BED_FACTOR is not None:
    BED_VOLUME_PERCENT = clamp(int(round(MAIN_VOLUME_PERCENT * BED_FACTOR)))
    log.info("🎚 BED via factor: MAIN=%s%% * %s => BED=%s%%", MAIN_VOLUME_PERCENT, BED_FACTOR, BED_VOLUME_PERCENT)
else:
    BED_VOLUME_PERCENT = clamp(env_int("BED_VOLUME_PERCENT", 20))
    log.info("🎚 BED fixed volume: %s%%", BED_VOLUME_PERCENT)
