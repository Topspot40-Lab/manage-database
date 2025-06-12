import os
from datetime import datetime
from backend import config
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def _write_track_group(f, label, tracks, formatter):
    f.write(f"{label}:\n")
    if tracks:
        for t in tracks:
            f.write(formatter(t) + "\n")
    else:
        f.write("None\n")
    f.write("\n")
def log_generate_json_summary(
    tracks: list,
    artists: list,
    now: datetime,
    category: str,
    genre: str,
    errors: list
) -> Dict[str, str | int]:
    if not config.GENERATE_JSON_LOGGING_ENABLED:
        return {}

    os.makedirs(os.path.dirname(config.GENERATE_JSON_LOG_PATH), exist_ok=True)

    total_tracks = len(tracks)
    good_tracks = [
        t for t in tracks
        if t.get("spotify_track_id") and t.get("spotify_artist_id")
    ]
    duet_tracks = [t for t in tracks if t.get("mode_flag") == 2]
    featured_tracks = [t for t in tracks if t.get("mode_flag") == 1]
    missing_artist_id = [a for a in artists if not a.get("spotify_artist_id")]
    missing_track_id = [t for t in tracks if not t.get("spotify_track_id")]

    with open(config.GENERATE_JSON_LOG_PATH, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 100 + "\n")
        f.write(f"🕒 {now.isoformat()} — Generate JSON Summary\n")
        f.write(f"📆 Decade: {category}   🎵 Genre: {genre}   🔢 Total Tracks: {total_tracks}\n")
        f.write("=" * 100 + "\n\n")

        f.write("✅ Tracks with Good Results:\n")
        f.write(f"# of Tracks with NO missing data: {len(good_tracks)}\n\n")

        _write_track_group(
            f,
            "🎤 Duet Tracks (mode_flag == 2)",
            duet_tracks,
            lambda t: f"Rank {t.get('rank')}: {t.get('track_name')}, mode_flag=2, "
                      f"{t.get('artist_name')} + {t.get('featured_artist')}"
        )

        _write_track_group(
            f,
            "🌟 Featured Artist Tracks (mode_flag == 1)",
            featured_tracks,
            lambda t: f"Rank {t.get('rank')}: {t.get('track_name')}, mode_flag=1, "
                      f"{t.get('artist_name')} feat. {t.get('featured_artist')}"
        )

        f.write("❌ Artists with missing spotify_artist_id:\n")
        if missing_artist_id:
            for a in missing_artist_id:
                f.write(f"{a.get('artist_name')}, spotify_artist_id: {a.get('spotify_artist_id')}\n")
        else:
            f.write("None\n")
        f.write("\n")

        f.write("❌ Tracks with missing spotify_track_id:\n")
        if missing_track_id:
            for t in missing_track_id:
                f.write(f"{t.get('track_name')} by {t.get('artist_name')}, spotify_track_id: {t.get('spotify_track_id')}\n")
        else:
            f.write("None\n")
        f.write("\n")

        f.write("🚨 Other Errors:\n")
        if errors:
            for err in errors:
                f.write(f"{err}\n")
        else:
            f.write("No other errors reported.\n")

        f.write("-" * 100 + "\n")

    # 📊 Return summary stats for table
    return {
        "decade": category,
        "total": total_tracks,
        "good": len(good_tracks),
        "missed": len(missing_track_id),
        "duets": len(duet_tracks) if duet_tracks else "None"
    }

def log_summary_table(decade_stats: List[Dict[str, str | int]]) -> None:
    """
    Logs a summary table of results per decade.
    Each item in decade_stats must include:
        - 'decade', 'total', 'good', 'missed', 'duets'
    """
    header = "✅ Quick Summary:\n"
    columns = f"{'Decade':<9} | {'Total Tracks':<13} | {'Good Tracks':<12} | {'Missed IDs':<13} | {'Notable Duets'}"
    separator = "-" * len(columns)
    rows = []

    for stat in decade_stats:
        row = f"{stat['decade']:<9} | {stat['total']:<13} | {stat['good']:<12} | {stat['missed']:<13} | {stat['duets']}"
        rows.append(row)

    summary = "\n".join([header, columns, separator] + rows)
    logger.info(summary)
