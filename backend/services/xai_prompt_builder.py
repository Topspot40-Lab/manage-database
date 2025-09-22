from backend.config import SPOTIFY_BLACKLIST

def build_track_prompt(
    decade: str,
    genre: str,
    num_tracks: int,
    language: str,
    buffer_size: int,
    anchors=None,
    avoid_tracks=None,
    avoid_artists=None,
    coverage_hints=None,
    max_tracks_per_artist: int = 1,
    canon_fallback_to_pop: bool = True,
    overlap_allowance: int = 5,  # ← allow up to N cross-listed tracks
):

    """
    Build an LLM prompt to generate a canonical track list with:
    - POP/ROCK separation rubrics
    - meta fields (importanceScore, popScore, rockScore)
    - anchors to prevent losing must-have tracks
    - overlap avoidance to reduce Pop/Rock leakage within the same decade
    - optional substyle coverage nudges and per-artist cap
    """
    prompted_num = num_tracks + buffer_size
    g = str(genre).strip().lower()

    # ---------- Render helpers ----------
    anchors = anchors or []
    avoid_tracks = avoid_tracks or []
    avoid_artists = avoid_artists or []
    coverage_hints = [h for h in (coverage_hints or []) if h]

    anchors_lines = "\n".join(
        f'- "{a.get("trackName")}" by {a.get("artistName")}'
        for a in anchors if a.get("trackName") and a.get("artistName")
    )
    avoid_tracks_lines = "\n".join(
        f'- "{t.get("trackName")}" by {t.get("artistName")}'
        for t in avoid_tracks if t.get("trackName") and t.get("artistName")
    )
    avoid_artists_lines = "\n".join(f"- {name}" for name in avoid_artists if name)

    coverage_lines = "\n".join(f"- {h}" for h in coverage_hints)

    has_anchors = bool(anchors_lines)
    has_avoid_tracks = bool(avoid_tracks_lines)
    has_avoid_artists = bool(avoid_artists_lines)
    has_coverage = bool(coverage_lines)

    # ---------- Base prompt ----------
    prompt = (
        f"Using chart history and critical acclaim as your guide, generate a JSON array with exactly {prompted_num} "
        f"of the most iconic and influential tracks in the {genre} genre during the {decade} decade. "
        f"Your selections should reflect actual popularity or historical recognition — prioritize songs that ranked high "
        f"on contemporaneous charts, won awards, or defined the era. "

        f"For each track, also include the original album where it was first officially released — not a later compilation, "
        f"remaster, or live album. If the track first appeared only as a stand-alone single or 78/45 (no album at the time), "
        f"set albumName to \"Single\". Use a mix of sources such as Billboard, Cashbox, RIAA certifications, Grammy archives, "
        f"AllMusic, and respected critics/historians.\n\n"

        f"Only include artists who were actively releasing original music during the {decade}. "
        f"EXCLUDE all songs and artists from later decades, even if they sound retro or nostalgic.\n\n"

        f"This list is intended for a {language}-speaking audience. Interpret genre definitions as they were understood in the "
        f"{decade}, not based on modern reinterpretations. Preserve diacritics in names and titles (e.g., João, Caetano, Café).\n\n"

        "🎵 Genre Clarifications (use era-appropriate substyles):\n"
        "- 'Rock': Use the decade’s dominant substyles (e.g., surf rock 1960s, hard rock 1970s, grunge 1990s).\n"
        "- 'Country': Match the decade’s sound (e.g., honky-tonk 1950s, outlaw 1970s, pop-country 2000s).\n"
        "- 'Pop': Reflect mainstream cross-format success, e.g., Hot 100 caliber hits of the era.\n"
        "- 'RnB Soul': Motown/Stax in the 1960s, Philadelphia soul/quiet storm in the 1970s, New Jack Swing in the 1990s, contemporary R&B thereafter.\n"
        "- 'Blues Jazz': See special rules below.\n"
        "- 'Latin Global': See special rules below.\n\n"

        "🔊 TTS Formatting (strict):\n"
        "- Never use the '#' character for ranks.\n"
        "- Whenever a rank is referenced in text, write it as 'number {rank}', not '#12' and not '12th'.\n\n"

        "🧾 Each JSON object must include (required fields):\n"
        "- rank (integer)\n"
        "- trackName (string)\n"
        "- artistName (string)\n"
        "- albumName (string) ← original official album, or 'Single' if first issued as a single only\n"
        "- yearReleased (integer)\n\n"

        "📊 Add these meta fields for internal triage (they will be removed downstream):\n"
        "- importanceScore (integer 1–100) ← overall historical/canonical weight\n"
        "- popScore (integer 0–3) ← apply the POP rubric\n"
        "- rockScore (integer 0–3) ← apply the ROCK rubric\n\n"
    )

    # Duets/feat rule (kept from your original)
    if num_tracks >= 5:
        prompt += (
            "✅ Include at least 2–3 duets using 'with' and at least 1 track using 'feat.' when historically accurate.\n"
            "❌ Avoid:\n"
            "- 'Waylon Jennings & Willie Nelson' → Use 'Waylon Jennings with Willie Nelson'\n"
            "- Inventing artist combinations or ambiguous formatting.\n\n"
        )

    # Blues/Jazz special
    if g in {"blues jazz", "blues/jazz", "blues & jazz", "bluesandjazz"}:
        prompt += (
            "🎷 Blues Jazz — Special Guidance\n"
            "- Valid substyles by decade: classic/Delta/Chicago blues, jump blues, electric blues, swing, bebop, cool, hard bop, modal, soul jazz, post-bop, fusion, contemporary jazz.\n"
            "- Instrumentals are allowed and often canonical; do not penalize tracks for lacking vocals.\n"
            "- Use first-issued single if that is the original release; otherwise the first studio LP that included the track.\n"
            "- Credit conventions: use 'feat.' only if it appears in the official credit; do not invent credits.\n\n"
        )

    # Latin/Global special
    if g in {"latin global", "latin", "latín global"}:
        prompt += (
            "🌎 Latin Global — Special Guidance\n"
            "- Scope includes Spanish- and Portuguese-language music across Latin America and the Iberian world; preserve diacritics.\n"
            "- Aim for regional coverage by decade; prioritize recognized charts/certifications where applicable.\n"
            "- Bilingual crossovers are allowed if the primary artistic origin is Latin; do not include unrelated English tracks.\n"
            "- If first released as a single, set albumName='Single'.\n\n"
        )

    # Pop/Rock separation rules
    # add to function signature: canon_fallback_to_pop: bool = True

    if g == "pop":
        prompt += (
            "🎤 POP — Separation Rules (vs Rock)\n"
            "- Definition: mainstream, cross-format hits with pop-oriented production (hook-first, prominent vocals, polished mixes, dance/synth/AC radio appeal).\n"
            "- Prioritize Hot 100/Radio Songs/Adult Contemporary leaders; treat Mainstream/Album Rock identity as a negative signal.\n"
            "- EXCLUDE hard rock, heavy guitar-distortion leads, extended rock solos, power-trio aesthetics.\n"
            "- Gray areas: keep synthpop/new wave with strong Hot 100 performance; dance-pop; pop-R&B hybrids.\n"
            "- Ambiguous artists: pick their most pop-identified singles; avoid their rock-radio staples here.\n"
            "🧭 Disambiguation rubric (internal): POP score 0–3 vs ROCK score 0–3; keep only if POP > ROCK.\n"
        )
        if canon_fallback_to_pop:
            prompt += (
                "🛟 Canonical fallback: If a widely recognized, decade-defining single risks being excluded by the "
                "POP/ROCK separation, prefer including it here in POP to avoid omission—provided it obeys decade rules "
                "and Spotify availability.\n\n"
            )
        else:
            prompt += "\n"

    elif g == "rock":
        prompt += (
            "🎸 ROCK — Separation Rules (vs Pop)\n"
            "- Definition: guitar/band-centric records rooted in rock scenes (AOR, hard/alt/indie, punk/post-punk, metal, etc.).\n"
            "- Prioritize Mainstream/Album Rock and rock-press canons (Hot 100 supportive but not determinative).\n"
            "- EXCLUDE pure dance-pop, polished AC ballads, producer-led pop projects.\n"
            "- Gray areas: guitar-led new wave/post-punk; hard rock/metal; alternative/college rock; grunge; punk.\n"
            "- Ambiguous artists: choose their rock-radio staples; avoid pop-dance crossovers here.\n"
            "🧭 Disambiguation rubric (internal): ROCK score 0–3 vs POP score 0–3; keep only if ROCK > POP.\n\n"
        )

    # Artist exclusivity & per-artist cap
    if g in {"pop", "rock"}:
        prompt += (
            "👥 Artist exclusivity within the same decade: prefer artists whose core identity aligns with THIS genre. "
            "If an artist is canonical in both Pop and Rock, choose tracks that clearly match THIS genre and avoid their other-genre staples here.\n"
            f"👤 Diversity: include a wide range of artists; do not include more than {max_tracks_per_artist} track(s) by the same primary artist unless absolutely essential.\n\n"
        )

    prompt += (
        "⚖️ Balance rule: Avoid over-concentrating on a single substyle; "
        "aim for balance across the decade's representative substyles for this genre.\n\n"
    )

    # Substyle coverage nudges
    if has_coverage:
        prompt += (
            f"🧭 Coverage balance (guidance, not hard quotas): ensure the final {num_tracks} covers these substyle areas for this decade where applicable:\n"
            f"{coverage_lines}\n\n"
        )

    # Anchors: must-keep
    if has_anchors:
        prompt += (
            "⭐ Must-keep anchors (include when valid for this decade/genre; do NOT fabricate):\n"
            f"{anchors_lines}\n"
            "- If an anchor clearly violates the genre/decade rules, omit it. Otherwise, include it and reflect its canonical status with a high importanceScore.\n\n"
        )

    # Overlap avoidance (tracks/artists already used in the other genre list for the same decade)
    if has_avoid_tracks or has_avoid_artists:
        prompt += "🚧 Overlap avoidance (reduce cross-genre leakage in the same decade):\n"
        if has_avoid_tracks:
            prompt += (
                "- Avoid these specific tracks unless excluding them would significantly damage accuracy for THIS genre; if needed, prefer a different canonical track by the same artist:\n"
                f"{avoid_tracks_lines}\n"
            )
        if has_avoid_artists:
            prompt += (
                "- Prefer not to use these primary artists (already covered in the other genre). If they must appear for accuracy, pick tracks clearly aligned to THIS genre and avoid tracks identical to the other list:\n"
                f"{avoid_artists_lines}\n"
            )
        prompt += "\n"

    # Soft overlap policy: allow a small number of canonical duplicates
    if overlap_allowance and overlap_allowance > 0:
        prompt += (
            "🔁 Overlap policy (same decade, Pop vs Rock):\n"
            f"- It is OK if up to {overlap_allowance} tracks also appear in the other genre’s list "
            "**when those tracks are broadly canonical**.\n"
            "- Prefer diversity first; only duplicate when excluding the track would materially harm accuracy.\n"
            "- If you duplicate, keep the most canonical single for THIS genre (use your POP/ROCK rubric).\n"
            "- Only duplicate when importanceScore ≥ 85 **and** this list’s rubric score exceeds the other "
            "(POP > ROCK for Pop; ROCK > POP for Rock).\n\n"
        )

    # Blacklist / availability
    blacklist_line = ", ".join(name.title() for name in sorted(SPOTIFY_BLACKLIST))
    prompt += (
        "🚫 Exclusions (Spotify availability warning):\n"
        "- Do NOT include any artist whose catalog is missing or restricted on Spotify.\n"
        f"- Exclude these known unavailable artists: {blacklist_line}.\n"
        "- When in doubt, omit artists that do not reliably appear in Spotify search or are unavailable for playback.\n\n"
    )

    # Output contract
    prompt += (
        "🧪 Validation Rules:\n"
        "- yearReleased must fall within the specified decade.\n"
        "- albumName is the first official studio LP containing the track, or 'Single' if initially non-album.\n"
        "- Preserve diacritics/capitalization; avoid duplicates, re-recordings, live-only versions, and posthumous remixes unless canonical.\n\n"
        "🎯 Your goal is to recreate a realistic, source-defensible list. "
        "Return ONLY a valid JSON array of objects with the required fields plus the meta fields; no headings, comments, or extra keys.\n"
    )

    return prompt
