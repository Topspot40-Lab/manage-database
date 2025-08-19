from backend.config import SPOTIFY_BLACKLIST



def build_track_prompt(decade, genre, num_tracks, language, buffer_size):
    prompted_num = num_tracks + buffer_size

    # Base prompt (applies to all genres)
    prompt = (
        f"Using chart history and critical acclaim as your guide, generate a JSON array with exactly {prompted_num} of the most iconic and influential tracks in the {genre} genre during the {decade} decade. "
        f"Your selections should reflect actual popularity or historical recognition — prioritize songs that ranked high on contemporaneous charts, won awards, or defined the era. "

        f"For each track, also include the original album where it was first officially released — not a later compilation, remaster, or live album. "
        f"If the track first appeared only as a stand-alone single or 78/45 (no album at the time), set albumName to \"Single\". "
        f"Use a mix of sources such as Billboard, Cashbox, RIAA certifications, Grammy archives, AllMusic, and respected critics/historians.\n\n"

        f"Only include artists who were actively releasing **original music** during the {decade}. "
        f"EXCLUDE all songs and artists from later decades, even if they sound retro or nostalgic.\n\n"

        f"This list is intended for a {language}-speaking audience. Interpret genre definitions as they were understood in the {decade}, not based on modern reinterpretations. Preserve diacritics in names and titles (e.g., João, Caetano, Café).\n\n"

        "🎵 Genre Clarifications (use era-appropriate substyles):\n"
        "- 'Rock': Use the decade’s dominant substyles (e.g., surf rock 1960s, hard rock 1970s, grunge 1990s).\n"
        "- 'Country': Match the decade’s sound (e.g., honky-tonk 1950s, outlaw 1970s, pop-country 2000s).\n"
        "- 'Pop': Reflect mainstream cross-format success, e.g., Hot 100 caliber hits of the era.\n"
        "- 'Rnb Soul': Motown/Stax in the 1960s, Philadelphia soul/quiet storm in the 1970s, New Jack Swing in the 1990s, contemporary R&B thereafter.\n"
        "- 'Blues Jazz': See special rules below.\n"
        "- 'Latin Global': See special rules below.\n\n"

        # TTS-friendly formatting
        "🔊 TTS Formatting (strict):\n"
        "- Never use the '#' character for ranks.\n"
        "- Whenever a rank is referenced in text, write it as 'number {rank}' (e.g., 'number 12'), not '#12' and not '12th'.\n\n"

        "🧾 Each JSON object must include:\n"
        "- rank (integer)\n"
        "- trackName (string)\n"
        "- artistName (string)\n"
        "- albumName (string) ← original official album, or 'Single' if first issued as a single only\n"
        "- yearReleased (integer)\n\n"

        "🎤 **Artist Name Formatting Rules** (important for data accuracy):\n"
        "- Use **'with'** for equal-credited duets. Example: 'George Jones with Tammy Wynette'.\n"
        "- Use **'feat.'** for featured artists (official credit only). Example: 'Ray Charles feat. The Raelettes'.\n"
        "- Use **'&' or 'and'** only for branded groups/duos: 'Simon & Garfunkel', 'Peter, Paul and Mary'.\n"
        "- Do not use slashes (/) or commas. Stick to clear formatting.\n\n"
    )

    # Duet/feat guidance for larger lists
    if num_tracks >= 5:
        prompt += (
            "✅ Include at least 2–3 duets using 'with' and at least 1 track using 'feat.' **when historically accurate for the selected genre/decade**.\n"
            "❌ Avoid:\n"
            "- 'Waylon Jennings & Willie Nelson' → Use 'Waylon Jennings with Willie Nelson'\n"
            "- Inventing artist combinations or ambiguous formatting.\n\n"
        )

    # --- Genre-specific enhancements -----------------------------------------
    if str(genre).strip().lower() in {"blues jazz", "blues/jazz", "blues & jazz", "bluesandjazz"}:
        prompt += (
            "🎷 **Blues Jazz — Special Guidance**\n"
            "- Valid substyles by decade: classic/Delta/Chicago blues, jump blues, electric blues, swing, bebop, cool, hard bop, modal, soul jazz, post-bop, fusion, contemporary jazz.\n"
            "- Instrumentals are allowed and often canonical; do not penalize tracks for lacking vocals.\n"
            "- Chart data for Jazz/Blues can be sparse; balance recognized charts with critic polls and canonical lists (DownBeat critics/readers polls, JazzTimes, The Penguin Guide to Jazz, Blues Foundation Hall of Fame, AllMusic, NPR/Jazz at Lincoln Center lists).\n"
            "- Use first-issued **single** if that is the original release; otherwise the first studio LP that included the track.\n"
            "- Credit conventions: use 'feat.' only if it appears in the official credit. Many classic sessions credit a bandleader ('Miles Davis') with a working group; don’t invent 'feat.' credits.\n\n"
        )

    if str(genre).strip().lower() in {"latin global", "latin", "latín global"}:
        prompt += (
            "🌎 **Latin Global — Special Guidance**\n"
            "- Scope includes Spanish-language and Portuguese-language music across Latin America and the Iberian world (e.g., Mexico, Caribbean, Andean region, Southern Cone, Brazil, Spain). Preserve diacritics (e.g., México, España, João, Caetano, Shakira).\n"
            "- Aim for **regional coverage** appropriate to the decade (examples: bolero/mambo/boogaloo in the 1950s–60s; salsa, cumbia, MPB, bossa nova; rock en español; bachata/merengue; reggaetón/Latin trap; sertanejo/pagode/funk carioca; flamenco-pop). Avoid over-concentrating on a single country.\n"
            "- Prioritize recognized sources: Billboard Hot Latin Songs/Latin Airplay/Tropical/Regional Mexican (where applicable by decade), Monitor Latino/country radio charts, national certifiers (AMPROFON—Mexico, PROMUSICAE—Spain, CAPIF—Argentina, Pro-Música Brasil—Brazil), and major streaming impact.\n"
            "- Bilingual crossovers are allowed if the **primary artistic origin** is Latin; don’t include unrelated English-language tracks.\n"
            "- If a song was first released as a single (common historically), set albumName='Single'.\n\n"
        )

    # --- Blacklist / availability guardrail ----------------------------------
    blacklist_line = ", ".join(name.title() for name in sorted(SPOTIFY_BLACKLIST))
    prompt += (
        "\n\n🚫 **Exclusions (Spotify availability warning):**\n"
        "- Do NOT include any artist whose catalog is missing or restricted on Spotify.\n"
        f"- Exclude these known unavailable artists: {blacklist_line}.\n"
        "- These artists are strictly banned from this list, even if historically relevant.\n"
        "- When in doubt, omit artists that do not reliably appear in Spotify search or are unavailable for playback.\n"
    )

    # --- Quality bar / output contract ---------------------------------------
    prompt += (
        "🧪 Validation Rules:\n"
        "- yearReleased must fall within the specified decade.\n"
        "- albumName is the first official studio LP containing the track, or 'Single' if initially non-album.\n"
        "- Preserve diacritics and official capitalization in artist and track names.\n"
        "- Avoid duplicates, re-recordings, live-only versions, and posthumous remixes unless they are the canonical hit.\n\n"

        "🎯 Your goal is to recreate a realistic and accurate list that could appear in a retrospective music documentary.\n"
        "Return ONLY a valid JSON array — no headings, explanations, or markdown."
    )

    return prompt
