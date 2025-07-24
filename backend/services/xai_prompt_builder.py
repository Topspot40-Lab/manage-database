import logging
from backend.config import SPOTIFY_BLACKLIST

logger = logging.getLogger("STEP_1.A" or "STEP_1")
def build_track_prompt(decade, genre, num_tracks, language, buffer_size):
    prompted_num = num_tracks + buffer_size
    prompt = (
        f"Using chart history and critical acclaim as your guide, generate a JSON array with exactly {prompted_num} of the most iconic and influential tracks in the {genre} genre during the {decade} decade. "
        f"Your selections should reflect actual popularity or historical recognition — prioritize songs that ranked high in Billboard charts, won awards, or defined the era. "

        f"For each track, also include the original album where it was first officially released — not a later compilation, remaster, or live album. "
        f"Use a mix of sources such as Billboard, Cashbox, Grammy archives, and music historians to guide your selections.\n\n"

        f"Only include artists who were actively releasing **original music** during the {decade}. "
        f"EXCLUDE all songs and artists from later decades, even if they sound retro or nostalgic.\n\n"

        f"This list is intended for a {language}-speaking audience. Interpret genre definitions as they were understood in the {decade}, not based on modern reinterpretations.\n\n"

        "🎵 Genre Clarifications:\n"
        "- 'Rock': Use the most popular subgenre of the era — e.g., surf rock (1960s), hard rock (1970s), grunge (1990s).\n"
        "- 'Country': Match the decade's dominant sound — e.g., honky-tonk (1950s), outlaw (1970s), pop-country (2000s).\n"
        "- 'Pop': Reflect mainstream chart success, like Billboard Hot 100 hits of the era.\n"
        "- 'R&B': Motown and soul in the 60s, New Jack Swing in the 90s, etc.\n"
        "- 'Folk': Include 1960s protest songs and acoustic revival, not modern indie-folk.\n\n"

        "🧾 Each JSON object must include:\n"
        "- rank (integer)\n"
        "- trackName (string)\n"
        "- artistName (string)\n"
        "- albumName (string) ← original official album (not a compilation)\n"
        "- yearReleased (integer)\n\n"

        "🎤 **Artist Name Formatting Rules** (important for data accuracy):\n"
        "- Use **'with'** for equal-credited duets. Example: 'George Jones with Tammy Wynette'.\n"
        "- Use **'feat.'** for featured artists. Example: 'Ray Charles feat. The Raelettes'.\n"
        "- Use **'&' or 'and'** only for branded groups/duos: 'Simon & Garfunkel', 'Peter, Paul and Mary'.\n"
        "- Do not use slashes (/) or commas. Stick to clear formatting.\n\n"
    )

    if num_tracks >= 5:
        prompt += (
            "✅ Include at least 2–3 duets using 'with'. Include at least 1 track using 'feat.'.\n"
            "❌ Avoid:\n"
            "- 'Waylon Jennings & Willie Nelson' → Use 'Waylon Jennings with Willie Nelson'\n"
            "- Inventing artist combinations or ambiguous formatting.\n\n"
        )

    blacklist_line = ", ".join(name.title() for name in sorted(SPOTIFY_BLACKLIST))
    prompt += (
        "\n\n🚫 **Exclusions (Spotify availability warning):**\n"
        "- Do NOT include any artist whose catalog is missing or restricted on Spotify.\n"
        f"- Exclude these known unavailable artists: {blacklist_line}.\n"
        "- These artists are strictly banned from this list, even if historically relevant.\n"
        "- When in doubt, omit artists that do not reliably appear in Spotify search or are unavailable for playback.\n"
    )

    prompt += (
        "🎯 Your goal is to recreate a realistic and accurate list that could appear in a retrospective music documentary.\n"
        "Return ONLY a valid JSON array — no headings, explanations, or markdown."
    )

    return prompt
