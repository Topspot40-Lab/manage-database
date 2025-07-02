import logging
logger = logging.getLogger("STEP_1.A" or "STEP_1")


def build_track_prompt(decade, genre, num_tracks, language, buffer_size):
    prompted_num = num_tracks + buffer_size
    prompt = (
        f"Generate a JSON array with exactly {prompted_num} top tracks strictly from the {genre} genre "
        f"during the {decade} decade, as officially recognized at the time. "
        f"Only include artists who were actively releasing original music during the actual {decade}. "
        f"EXCLUDE all songs and artists from later decades, even if they sound retro or nostalgic.\n\n"

        f"This list is intended for a {language}-speaking audience. "
        f"The genre must reflect what {genre} meant during the {decade}, not modern reinterpretations.\n\n"

        "🎵 Genre Clarifications:\n"
        "- 'Rock': Use the most popular style of the era — e.g., classic rock in the 1970s, grunge in the 1990s.\n"
        "- 'Country': Match the sound of the decade — traditional in the 1960s, pop-country in the 2000s, etc.\n"
        "- 'Pop': Billboard-style mainstream pop of the decade, not retro indie pop.\n"
        "- 'R&B': Motown/soul in the 60s, modern R&B in the 2000s.\n"
        "- 'Folk': Include artists like Peter, Paul and Mary or Joan Baez for the 1960s; avoid modern indie-folk.\n\n"

        "🧾 Each JSON entry must include:\n"
        "- rank (integer)\n"
        "- trackName (string)\n"
        "- artistName (string)\n"
        "- yearReleased (integer)\n\n"

        "🎤 **Artist Name Formatting Rules** (this is critical):\n"
        "- Use **'with'** to indicate a duet where two solo artists collaborated equally. Example: 'Waylon Jennings with Willie Nelson'.\n"
        "- Use **'feat.'** for featured artists who play a supporting role. Example: 'Aretha Franklin feat. The Sweet Inspirations'.\n"
        "- Use **'&' or 'and'** only for official, branded duos or groups. Example: 'Simon & Garfunkel', 'Peter, Paul and Mary'.\n"
        "- DO NOT use '&' when 'with' is more appropriate.\n"
        "- DO NOT make up group names or blend formats.\n"
        "- DO NOT use slashes (/) or commas in artist names.\n\n"

        "✅ Include at least 2–3 duets using 'with'. Include at least 1 featured track using 'feat.'.\n"
        "❌ Avoid common mistakes:\n"
        "- Don't write 'Waylon Jennings & Willie Nelson' — instead write 'Waylon Jennings with Willie Nelson'.\n"
        "- Don't use 'feat.' when it should be a duet.\n\n"

        "Return ONLY a valid JSON array. No extra commentary, no headings, no explanations."
    )

    # 🧠 Only log in STEP 1 context (DEBUG mode)
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("📝 [STEP_1.A] PROMPT]\n\n%s\n", prompt)

    return prompt
