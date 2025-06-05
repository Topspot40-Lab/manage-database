# backend/services/xai_prompt_builder.py

def build_track_prompt(category, genre, num_tracks, language, buffer_size):
    prompted_num = num_tracks + buffer_size
    return (
        f"Generate a JSON array with exactly {prompted_num} top tracks strictly from the {genre} genre "
        f"during the {category} decade, as officially recognized during that time. "
        f"Only include artists who were actively releasing original music during the actual {category} decade. "
        f"EXCLUDE all songs and artists from later decades, even if they sound retro. "
        f"Genre must be strictly {genre} as defined in the {category}. This is for a {language} audience. "
        "Each entry must include: rank (integer), trackName (string), artistName (string), and yearReleased (integer). "
        "Format artistName based on the artist type:\n"
        "- Use '&' only for established, well-known groups from that decade (e.g., 'Simon & Garfunkel', 'Sonny & Cher').\n"
        "- Use ' and ' to indicate two artists singing a duet (e.g., 'George Jones and Tammy Wynette').\n"
        "- Use ' ft. ' to indicate a featured artist (e.g., 'James Brown ft. Bobby Byrd').\n"
        "Include a few edge cases with each format to help test parsing logic.\n"
        "Return a valid JSON array only — no extra text."
    )
