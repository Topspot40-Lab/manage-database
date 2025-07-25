from enum import Enum
from typing import List, Optional, Tuple
from backend.models.enums import ModeFlag

import logging
logger = logging.getLogger(__name__)


# NOTE: Only used during Spotify enrichment when determining featured artist ID
# DO NOT use in general track processing — use get_mode_flag() instead

def determine_mode_flag(artist_name: str, artist_list: List[dict]) -> Tuple[ModeFlag, Optional[str]]:
    print("Entering determine_mode_flag")
    name_lower = artist_name.lower()

    # is_duet = " with " in name_lower or " and " in name_lower
    is_duet = " with " in name_lower
    is_feature = " feat." in name_lower or " featuring " in name_lower

    featured_artist_id = None

    if is_feature and len(artist_list) > 1:
        mode_flag = ModeFlag.FEATURED
        featured_artist_id = artist_list[1]["id"]
    elif is_duet and len(artist_list) > 1:
        mode_flag = ModeFlag.DUET
        featured_artist_id = artist_list[1]["id"]
    else:
        mode_flag = ModeFlag.SOLO

    return mode_flag, featured_artist_id

def determine_mode_flag_basic(artist_name: str) -> ModeFlag:
    name_lower = artist_name.lower()
    if "feat." in name_lower or "featuring" in name_lower:
        return ModeFlag.FEATURED
    elif " with " in name_lower or " and " in name_lower:
        return ModeFlag.DUET
    return ModeFlag.SOLO



def parse_mode_flag(raw_flag: Optional[str]) -> ModeFlag:
    """Safely parse a raw string (e.g., from JSON) into a ModeFlag enum."""
    if not raw_flag:
        return ModeFlag.SOLO

    try:
        return ModeFlag(raw_flag.upper())  # <-- FIXED CASE
    except ValueError:
        logger.warning(f"⚠️ Invalid mode_flag '{raw_flag}', defaulting to ModeFlag.SOLO")
        return ModeFlag.SOLO
