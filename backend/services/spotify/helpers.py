import re
from backend.utils.json_helpers import normalize_name
from backend.models.enums import ModeFlag

NON_WORD = re.compile(r"\W+")


def safe_slug(text: str) -> str:
    return NON_WORD.sub("_", normalize_name(text))

def clean_track_title(title: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", title).strip()

def format_artist_display_name(main: str, feat: str | None, mode_flag: int) -> str:
    if mode_flag == ModeFlag.DUET and feat:
        return f"{main} WITH {feat} (Duet)"
    if mode_flag == ModeFlag.FEATURED and feat:
        return f"{main} feat. {feat}"
    return main
