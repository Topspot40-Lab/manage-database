# backend/logging/track_logging.py

import logging

logger = logging.getLogger(__name__)  # ✅ Module-specific logger

def log_raw_tracks(tracks):
    for t in tracks:
        rank = t.get("rank", "?")
        logger.debug(f"[TRACK RAW #{rank}] {t}")

def log_filtered_out(filtered_count):
    if filtered_count > 0:
        logger.debug(f"[CLEANUP] Filtered {filtered_count} hallucinated or invalid track(s).")

def log_duet_feature_info(tracks):
    for t in tracks:
        rank = t.get("rank", "?")
        name = t.get("artistName", "")
        name_lower = name.lower()

        if " with " in name_lower:
            logger.debug(
                f"[DUET DETECTED] Rank #{rank}: {name}\n"
                f"    ↪ Detected 'with' pattern — possible duet."
            )
        elif " feat." in name_lower or " ft. " in name_lower:
            logger.debug(
                f"[FEATURED DETECTED] Rank #{rank}: {name}\n"
                f"    ↪ Detected 'feat.' or 'ft.' pattern — possible featured artist."
            )
        else:
            logger.debug(
                f"[SOLO DETECTED] Rank #{rank}: {name}\n"
                f"    ↪ No 'with', 'feat.', or 'ft.' found — likely a solo performer."
            )
