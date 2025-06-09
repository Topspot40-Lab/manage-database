def build_track_prompt(decade, genre, num_tracks, language, buffer_size):
    prompted_num = num_tracks + buffer_size
    return (
        f"Generate a JSON array with exactly {prompted_num} top tracks strictly from the {genre} genre "
        f"during the {decade} decade, as officially recognized during that time. "
        f"Only include artists who were actively releasing original music during the actual {decade} decade. "
        f"EXCLUDE all songs and artists from later decades, even if they sound retro. "
        f"Genre must be strictly {genre} as defined in the {decade}. This is for a {language} audience. "
        "Clarify the definition of the genre according to the selected decade:\n"
        "- 'Rock' should reflect the dominant form of rock in that decade (e.g., classic rock in the 1970s, alternative or grunge in the 1990s).\n"
        "- 'Pop' must reflect popular chart-topping artists from that time, not retro-styled or future reinterpretations.\n"
        "- 'Country' should match the era’s country style — traditional in the 1960s, pop-country in the 2000s, etc.\n"
        "- 'R&B' should reflect what was considered R&B during that decade — soul and Motown in the 60s, contemporary R&B in the 2000s, etc.\n"
        "- 'Folk' should align with how the genre was understood in that time, avoiding modern indie-folk or retro imitations in early decades.\n"
        "Each entry must include: rank (integer), trackName (string), artistName (string), and yearReleased (integer). "
        "Format artistName based on the artist type:\n"
        "- Use '&' or 'and' only for **officially established duos or groups** from that decade (e.g., 'Simon & Garfunkel', 'Sonny & Cher').\n"
        "- Use ' with ' to indicate a **duet**, where both artists are equally credited on the track (e.g., 'George Jones with Tammy Wynette').\n"
        "- Use ' feat. ' to indicate a **featured artist**, who is not the main performer (e.g., 'James Brown feat. Bobby Byrd').\n"
        "Be consistent in formatting. Do not invent group names or use multiple styles in one name.\n"
        "Include a few edge cases with each format to help test parsing logic.\n"
        "Return a valid JSON array only — no extra text."
    )
