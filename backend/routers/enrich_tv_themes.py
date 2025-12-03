# backend/routers/enrich_tv_themes.py
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import date
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from fastapi import APIRouter, HTTPException, Query, Body, status
from backend.config import (
    BASE_DIR,
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    spotify_creds_ok,
)

logger = logging.getLogger("enrich_tv_themes")
router = APIRouter(tags=["Generators"], prefix="/generate")

# ---------- Core text utils ----------
_WORDS = re.compile(r"[^\w]+", re.UNICODE)

# Basic emoji ranges (BMP + supplemental symbols); conservative on purpose
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]+")

def de_emoji(s: str | None) -> str:
    """Remove emoji-like characters from text."""
    return _EMOJI.sub("", s or "")

def _ensure_spotify(sp_ref: dict) -> spotipy.Spotify:
    """Lazy init. sp_ref is a one-slot dict used to hold a singleton client."""
    sp = sp_ref.get("sp")
    if sp is not None:
        return sp
    if not spotify_creds_ok():
        # return a 400 that serializes as JSON instead of a vague 500
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spotify credentials are missing. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET (or SPOTIPY_*).",
        )
    sp = _get_spotify()
    sp_ref["sp"] = sp
    return sp

def _norm(s: str) -> str:
    return _WORDS.sub("", (s or "").lower())


# ---------- Narrative helpers ----------
def _clean_years(yoa: str | None) -> str:
    s = (yoa or "").strip()
    if not s:
        return ""
    # normalize hyphen/en dash and collapse spaces
    s = re.sub(r"\s*[–-]\s*", "–", s)
    return s

def _clean_genre(g: str | None) -> str:
    g = (g or "").strip()
    if not g:
        return ""
    # title case but keep slashes lowercase, e.g., "Anthology/Thriller"
    parts = [p.strip().title() for p in re.split(r"[/]", g)]
    return "/".join(parts)

def _first_nonempty(d: Dict[str, Any], keys: List[str]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v:
            return ", ".join([str(x).strip() for x in v if str(x).strip()][:6])
    return ""

def _split_names(s: str) -> List[str]:
    if not s:
        return []
    s = re.sub(r"\s*&\s*", ",", s)
    parts = [p.strip() for p in re.split(r",|\band\b", s, flags=re.I)]
    return [p for p in parts if p]

def _pick_cast(meta: Dict[str, Any]) -> List[str]:
    raw = _first_nonempty(
        meta,
        [
            "starring",
            "stars",
            "cast",
            "top_cast",
            "lead_cast",
            "lead_actors",
            "lead_names",
            "principal_cast",
        ],
    )
    names = _split_names(raw)
    return names[:4]

# ---- scoring boosts/penalties for Spotify search ----
def _has_token(s: str | None, toks: List[str]) -> bool:
    s = (s or "").lower()
    return any(t in s for t in toks)

_PENALTY_TOKENS_ARTIST = [
    "8-bit", "8bit", "lounge", "lofi", "lo-fi", "karaoke", "tribute",
    "kids", "crew", "tunesters", "players", "orchestra", "pops",
    "factory", "tv ", " sounds ", " band", " cast", "dj ", "remix",
    "re-record", "rerecorded", "sound-a-like", "soundalike"
]
_PENALTY_TOKENS_ALBUM = [
    "tv themes", "television themes", "karaoke", "8-bit", "8bit", "chip",
    "chiptune", "lofi", "lo-fi", "lounge", "tribute", "cover", "workout",
    "remix", "re-record", "rerecorded", "kids", "sing-along"
]
_BONUS_TOKENS_ALBUM = [
    "original television soundtrack", "original tv soundtrack",
    "original soundtrack", "from the television series",
    "music from the original tv series", "from the series", "original score"
]

# Show→composer/performer hints (1970s-heavy; add more as needed)
_SHOW_COMPOSER_HINTS = {
    _norm("Dallas"): {"jerrold immel"},
    _norm("The Rockford Files"): {"mike post", "pete carpenter"},
    _norm("Columbo"): {"henry mancini"},
    _norm("Kojak"): {"john cacavas"},
    _norm("Baretta"): {"sammy davis jr", "dave grusin", "rhythm heritage"},
    _norm("Taxi"): {"bob james"},
    _norm("Welcome Back, Kotter"): {"john sebastian"},
    _norm("The Dukes of Hazzard"): {"waylon jennings"},
    _norm("The Love Boat"): {"jack jones", "dionne warwick"},
    _norm("The Incredible Hulk"): {"joe harnell"},
    _norm("Wonder Woman"): {"charles fox"},
    _norm("The Muppet Show"): {"the muppets", "jim henson", "sam pottle"},
    _norm("Little House on the Prairie"): {"david rose"},
    _norm("Charlie's Angels"): {"jack elliott", "allyn ferguson"},
    _norm("Starsky & Hutch"): {"lalo schifrin", "tom scott"},
    _norm("S.W.A.T."): {"rhythm heritage", "barry de vorzon"},
    _norm("The Waltons"): {"jerry goldsmith"},
    _norm("Three's Company"): {"joe raposo", "ray charles", "julia rinker"},
    _norm("Happy Days"): {"pratt & mcclain"},
    _norm("Laverne & Shirley"): {"cyndi grecco"},
    _norm("The Mary Tyler Moore Show"): {"sonny curtis"},
    _norm("All in the Family"): {"carroll o'connor", "jean stapleton"},
    _norm("Sanford and Son"): {"quincy jones"},
    _norm("The Jeffersons"): {"ja'net dubois", "jeff barry"},
}



# ---- generic/cover-artist detection ----
_GENERIC_EXACT = {
    # common compilations / cover factories
    "various artists",
    "the great tv crew",
    "music factory",
    "the hit co.",
    "8-bit arcade",
    "soundtrack & theme orchestra",
    "tv sounds unlimited",
    "tv tunesters",
    "hollywood tv players",
    "the movie pops",
    "mount royal orchestra",
    "dj tv",
    "parry music",
    "london television orchestra",
    "sega sound team",
    "the sesame street kids",
    # offenders seen in your dump
    "boom tube",
    "toners",
    "los muppets",
    "sanford and son",  # show title mis-used as “artist”
}

_GENERIC_TOKENS = [
    " tv ", "theme", "themes", "soundtrack", "orchestra", "players",
    "tunesters", "crew", "team", "factory", "kids", "arcade",
    "karaoke", "tribute", "cover", "movie", "hollywood", "london",
    "mount royal"
]

# ---- scoring boosts/penalties for Spotify search ----
def _has_token(s: str | None, toks: List[str]) -> bool:
    s = (s or "").lower()
    return any(t in s for t in toks)

_PENALTY_TOKENS_ARTIST = [
    "8-bit", "8bit", "lounge", "lofi", "lo-fi", "karaoke", "tribute",
    "kids", "crew", "tunesters", "players", "orchestra", "pops",
    "factory", "tv ", " sounds ", " band", " cast", "dj ", "remix",
    "re-record", "sound-a-like", "soundalike"
]
_PENALTY_TOKENS_ALBUM = [
    "tv themes", "television themes", "karaoke", "8-bit", "8bit", "chip",
    "chiptune", "lofi", "lo-fi", "lounge", "tribute", "cover", "workout",
    "remix", "re-record", "kids", "sing-along"
]
_BONUS_TOKENS_ALBUM = [
    "original television soundtrack", "original tv soundtrack",
    "original soundtrack", "from the television series",
    "music from the original tv series", "from the series", "original score"
]

# Show→composer/performer hints (big bonus if artist matches)
_SHOW_COMPOSER_HINTS = {
    _norm("Dallas"): {"jerrold immel"},
    _norm("The Rockford Files"): {"mike post", "pete carpenter"},
    _norm("Columbo"): {"henry mancini"},
    _norm("Kojak"): {"john cacavas"},
    _norm("Baretta"): {"sammy davis jr", "dave grusin", "rhythm heritage"},
    _norm("Taxi"): {"bob james"},
    _norm("Welcome Back, Kotter"): {"john sebastian"},
    _norm("The Dukes of Hazzard"): {"waylon jennings"},
    _norm("The Love Boat"): {"jack jones", "dionne warwick"},
    _norm("The Incredible Hulk"): {"joe harnell"},
    _norm("Wonder Woman"): {"charles fox"},
    _norm("The Muppet Show"): {"the muppets", "jim henson", "sam pottle"},
    _norm("Little House on the Prairie"): {"david rose"},
    _norm("Charlie's Angels"): {"jack elliott", "allyn ferguson"},
    _norm("Starsky & Hutch"): {"lalo schifrin", "tom scott"},
    _norm("S.W.A.T."): {"rhythm heritage", "barry de vorzon"},
    _norm("The Waltons"): {"jerry goldsmith"},
    _norm("Three's Company"): {"joe raposo", "ray charles", "julia rinker"},
    _norm("Happy Days"): {"pratt & mcclain"},
    _norm("Laverne & Shirley"): {"cyndi grecco"},
    _norm("The Mary Tyler Moore Show"): {"sonny curtis"},
    _norm("All in the Family"): {"carroll o'connor", "jean stapleton"},
    _norm("Sanford and Son"): {"quincy jones"},
    _norm("The Jeffersons"): {"ja'net dubois", "jeff barry"},
}


def _looks_generic_artist(name: str) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return True
    if n in _GENERIC_EXACT:
        return True
    # token check (pad with spaces so " tv " hits and reduce false positives)
    nn = f" {n} "
    return any(tok in nn for tok in _GENERIC_TOKENS)

def _normkey(s: str) -> str:
    import re
    return re.sub(r"[^\w]+", "", (s or "").lower())

def _is_show_title_as_artist(artist_name: str, show_names_norm: set[str]) -> bool:
    return _normkey(artist_name) in show_names_norm


# Known, tasteful settings for iconic shows (seeded with 1950s; harmless for others)
_KNOWN_SHOW_SETTINGS = {
    _norm("Peter Gunn"): "smoky jazz clubs and Los Angeles waterfront alleys",
    _norm("Perry Mason"): "Los Angeles courtrooms and sleek law offices",
    _norm("Rawhide"): "cattle-drive trails, river crossings, and dusty camps",
    _norm("Bonanza"): "the Ponderosa ranch near Virginia City, Nevada",
    _norm("The Mickey Mouse Club"): "a bright clubhouse set with roll-call sing-alongs",
    _norm("Alfred Hitchcock Presents"): "ordinary places tilted toward suspenseful twists",
    _norm("The Lone Ranger"): "open ranges, canyons, and frontier towns",
    _norm("Adventures of Superman"): "Metropolis streets and the Daily Planet newsroom",
    _norm("Have Gun – Will Travel"): "waystations and border towns across the American West",
    _norm("The Rifleman"): "a New Mexico homestead and the town of North Fork",
    _norm("The Honeymooners"): "a Brooklyn walk-up and neighborhood corners",
}

# Genre templates. Keys are lowercase tokens we search for inside the cleaned genre string.
_GENRE_TEMPLATES = {
    "western": dict(
        setting="frontier towns, ranches, and wide-open ranges",
        episodes="trail dilemmas, frontier justice, and moral tests",
        storytelling="tight, episodic plots with clear stakes",
        production="location shooting, practical stunts, and brassy, galloping scores",
    ),
    "detective": dict(
        setting="back-alleys, nightclubs, and neon-lit offices",
        episodes="case-of-the-week investigations",
        storytelling="hard-boiled banter and cool-jazz atmosphere",
        production="economical staging, noirish lighting, and punchy edits",
    ),
    "noir": dict(
        setting="shadowed streets and smoky lounges",
        episodes="morally tangled cases",
        storytelling="laconic dialogue and fatalistic undertones",
        production="high-contrast lighting and tight close-ups",
    ),
    "legal": dict(
        setting="courtrooms, chambers, and downtown law offices",
        episodes="client-of-the-week trials",
        storytelling="procedural clarity and late-act reversals",
        production="studio sets and composed arguments framed like chess matches",
    ),
    "procedural": dict(
        setting="squad rooms and city streets",
        episodes="step-by-step investigations",
        storytelling="docudrama pacing and factual narration",
        production="minimalist scoring and utilitarian camera work",
    ),
    "sitcom": dict(
        setting="living rooms, kitchens, and neighborhood stoops",
        episodes="domestic mix-ups and brisk misunderstandings",
        storytelling="setup-payoff rhythms and tidy resolutions",
        production="multi-camera staging and bright, close-miked theme cues",
    ),
    "anthology": dict(
        setting="everyday locations slanted toward the uncanny",
        episodes="standalone twist stories",
        storytelling="tight ironies and moral fables",
        production="economical sets and mood-first scoring",
    ),
    "adventure": dict(
        setting="exotic locales and peril-prone outposts",
        episodes="peril-of-the-week scrapes",
        storytelling="swift pacing and clean heroism",
        production="stock-footage assists and bold brass fanfares",
    ),
    "superhero": dict(
        setting="metropolitan skylines and newsrooms",
        episodes="rescue-driven conflicts and secret-identity dilemmas",
        storytelling="square-jawed optimism and serial momentum",
        production="miniatures, wire gags, and declarative title cards",
    ),
    "family": dict(
        setting="small-town streets and schoolhouse corridors",
        episodes="everyday scrapes and heartfelt fixes",
        storytelling="gentle humor and wholesome lessons",
        production="studio interiors with warm strings and woodwinds",
    ),
    "kids": dict(
        setting="cheerful clubhouses and soundstage playgrounds",
        episodes="sing-along bits and serialized skits",
        storytelling="go-along participation and call-and-response hooks",
        production="march tempos, bright choruses, and crisp enunciation",
    ),
    "variety": dict(
        setting="proscenium stages and bandstands",
        episodes="sketches, novelty numbers, and guest turns",
        storytelling="buttoned gags and musical interludes",
        production="lush studio orchestras and show-curtain fanfares",
    ),
    "sci": dict(  # covers sci-fi tokenization
        setting="laboratories, launch pads, and uncanny thresholds",
        episodes="speculative dilemmas and eerie reveals",
        storytelling="what-if premises and twist endings",
        production="theremin-tinged cues and stylized effects",
    ),
}

def _match_genre_template(genre_t: str) -> Dict[str, str]:
    """Non-recursive matcher that safely merges common multi-genre phrasings."""
    g = (genre_t or "").lower()

    # Simple alias
    if "legal drama" in g:
        return _GENRE_TEMPLATES["legal"]

    def merge(keys: List[str]) -> Dict[str, str]:
        out = dict(setting="", episodes="", storytelling="", production="")
        for k in keys:
            base = _GENRE_TEMPLATES.get(k)
            if not base:
                continue
            for f in out:
                out[f] = (out[f] + "; " if out[f] else "") + base[f]
        return out

    if "crime" in g and "procedural" in g:
        return merge(["procedural"])
    if "detective" in g and "noir" in g:
        return merge(["detective", "noir"])
    if "anthology" in g and ("sci" in g or "sci-fi" in g or "science fiction" in g):
        return merge(["anthology", "sci"])

    # single-token fallback
    for key in _GENRE_TEMPLATES:
        if key in g:
            return _GENRE_TEMPLATES[key]

    return dict(
        setting="its signature locales",
        episodes="week-to-week conflicts",
        storytelling="clear arcs and strong motifs",
        production="practical staging and economical camera work",
    )

def _synth_detail(
    show: str, years: str, genre: str, meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build a richer, reusable paragraph for a TV show theme.
    Uses cast/setting if available; otherwise falls back to genre-aware templates.
    """
    meta = meta or {}
    show = (show or "").strip()
    years = _clean_years(years)
    genre_t = _clean_genre(genre)

    bits: List[str] = []
    if show:
        head = (
            f"{show} was a {genre_t.lower() if genre_t else 'tv'} mainstay of the {years} run"
            if years
            else f"{show} was a {genre_t.lower() if genre_t else 'tv'} staple"
        )
        cast = _pick_cast(meta)
        if cast:
            head += f", headlined by {', '.join(cast)}"
        head += "."
        bits.append(head)

    # setting
    s_key = _norm(meta.get("show_name") or show)
    setting = _KNOWN_SHOW_SETTINGS.get(s_key) or _first_nonempty(
        meta, ["setting", "locations", "show_setting", "series_setting"]
    )
    tmpl = _match_genre_template(genre_t)
    setting = setting or tmpl["setting"]
    bits.append(
        f"Set around {setting}, episodes balanced character moments with {tmpl['episodes']}."
    )

    # storytelling & production
    bits.append(
        f"Storytelling favored {tmpl['storytelling']}, while production leaned on {tmpl['production']}."
    )

    # theme line (composer/arranger credit if non-generic)
    theme_line = "The theme cues that mood in seconds—announcing who these characters are and the kind of world you’re stepping into."
    artist = (meta.get("artist_display_name") or meta.get("artist_name") or "").strip()
    if artist and not _looks_generic_artist(artist) and artist.lower() != show.lower():
        theme_line = f"Composed/arranged by {artist}, the theme cues that mood in seconds—announcing who these characters are and the kind of world you’re stepping into."
    bits.append(theme_line)

    return " ".join(bits).strip()

def _synth_intro(rank: int | None, show: str, years: str, genre: str) -> str:
    show = (show or "").strip()
    years = _clean_years(years)
    genre_t = _clean_genre(genre)
    lead = []
    if rank:
        lead.append(f"#{rank} ")
    if show:
        lead.append(show)
    if years:
        lead.append(f" ({years})")
    head = "".join(lead).strip()
    tail = (
        f" — a {genre_t.lower()} staple whose theme instantly sets the tone."
        if genre_t
        else " — a TV staple whose theme instantly sets the tone."
    )
    return (head + tail).strip()

def _best_artist_image(sp, artist_id: str) -> str | None:
    if not artist_id:
        return None
    try:
        a = sp.artist(artist_id)
    except Exception:
        return None
    imgs = a.get("images") or []
    if not imgs:
        return None
    return sorted(imgs, key=lambda im: (im.get("width") or 0), reverse=True)[0].get("url")


# ---------- Spotify client ----------
def _get_spotify() -> spotipy.Spotify:
    if not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET):
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing Spotify credentials. Set SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET "
                "(or SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET) in your .env"
            ),
        )
    auth = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET
    )
    return spotipy.Spotify(auth_manager=auth, requests_timeout=15, retries=3)


# ---------- Spotify helpers ----------
def _best_image(images: List[Dict[str, Any]]) -> Optional[str]:
    if not images:
        return None
    return sorted(images, key=lambda im: (im.get("width") or 0), reverse=True)[0].get("url")
def _score_candidate(track: Dict[str, Any], theme: str, show: str) -> float:
    score = 0.0
    tname = track.get("name") or ""
    album = (track.get("album") or {}).get("name") or ""
    artists = track.get("artists") or []
    aname = (artists[0].get("name") if artists else "") or ""
    pop = track.get("popularity") or 0
    dur_ms = track.get("duration_ms") or 0

    tn, sn, an, alb = _norm(tname), _norm(show), _norm(aname), _norm(album)
    theme_n = _norm(theme)

    # Strong exact-ish matches
    if theme_n and theme_n in tn:
        score += 7.0
    if sn and (sn in tn):
        score += 5.0
    if sn and (sn in alb):
        score += 4.0

    # Useful keywords in title/album
    keywords = ["theme", "maintitle", "main title", "tv", "television", "ost", "originalsoundtrack"]
    if any(k in tname.lower() for k in keywords):
        score += 2.0
    if any(k in album.lower() for k in keywords):
        score += 2.0

    # Popularity helps a bit
    score += pop / 20.0

    # Duration: themes are often ~0:30–2:00 (allow up to 2:30)
    if 25_000 <= dur_ms <= 150_000:
        score += 2.0
    elif dur_ms < 12_000 or dur_ms > 240_000:
        score -= 2.0

    # Bonus if album smells like the *original* thing
    if _has_token(album, _BONUS_TOKENS_ALBUM):
        score += 3.0

    # Big bonus if the artist matches a known composer/performer for this show
    hints = _SHOW_COMPOSER_HINTS.get(sn, set())
    if hints and an.lower() in hints:
        score += 6.0

    # Penalties for cover/compilation factories & novelty acts
    if _looks_generic_artist(aname):
        score -= 6.0
    if _has_token(aname, _PENALTY_TOKENS_ARTIST):
        score -= 4.0
    if _has_token(album, _PENALTY_TOKENS_ALBUM):
        score -= 4.0

    return score

def _search_spotify_theme(
    sp: spotipy.Spotify, theme: str, show: str, start_year: int, end_year: int
) -> Optional[Dict[str, Any]]:
    """Try several queries & pick best-scoring candidate."""
    queries = [
        f'track:"{theme}" {show}',
        f'"{theme}" {show} theme',
        f'track:"{theme}"',
        f"{theme} theme",
        f"{show} theme",
    ]
    best: Tuple[float, Optional[Dict[str, Any]]] = (0.0, None)

    seen_ids = set()
    for q in queries:
        try:
            res = sp.search(q=q, type="track", limit=20, market="US")
            items = (res.get("tracks") or {}).get("items") or []
        except Exception as ex:
            logger.warning("Spotify search error for %r: %s", q, ex)
            items = []

        for tr in items:
            tid = tr.get("id")
            if not tid or tid in seen_ids:
                continue
            seen_ids.add(tid)

            year_str = ((tr.get("album") or {}).get("release_date") or "")[:4]
            try:
                yr = int(year_str)
            except Exception:
                yr = None
            if yr and (yr < start_year - 10 or yr > end_year + 40):
                continue

            sc = _score_candidate(tr, theme, show)
            if sc > best[0]:
                best = (sc, tr)

    return best[1]

def _update_track_fields(track_obj: Dict[str, Any], sp_track: Dict[str, Any]) -> None:
    artists = sp_track.get("artists") or []
    primary_artist = artists[0] if artists else {}
    album = sp_track.get("album") or {}

    track_obj["spotify_track_id"] = sp_track.get("id") or ""
    track_obj["spotify_artist_id"] = primary_artist.get("id") or ""
    track_obj["album_name"] = album.get("name")
    track_obj["album_artwork"] = _best_image(album.get("images") or [])
    track_obj["duration_ms"] = sp_track.get("duration_ms")
    track_obj["popularity"] = sp_track.get("popularity")
    track_obj["is_explicit"] = bool(sp_track.get("explicit"))

    # ensure we actually keep a human artist name on the track
    primary_name = (primary_artist.get("name") or "").strip()
    if primary_name:
        if not (track_obj.get("artist_display_name") or "").strip():
            track_obj["artist_display_name"] = primary_name
        if not (track_obj.get("artist_name") or "").strip():
            track_obj["artist_name"] = primary_name

# ---------- Endpoint ----------
@router.post("/{decade}")
def enrich_tv_theme_file(
    decade: str,
    filename: str = Query(..., description="e.g., 1950s_tv_themes_en.json"),
    overwrite: bool = Query(True, description="Overwrite existing spotify_* fields if present"),
    dry_run: bool = Query(False),
    max_items: int = Query(0, ge=0, le=60, description="0 = all; otherwise limit how many tracks to process"),
    overwrite_details: bool = Query(False, description="Regenerate 'detail' even if already present"),
    overwrite_intros: bool = Query(True, description="Regenerate ranking 'intro' even if already present"),
    scrub_emojis: bool = Query(True, description="Strip emojis from ALL 'detail' and 'intro' fields"),
    overrides: Optional[List[Dict[str, str]]] = Body(default=None, description="Optional list of overrides"),
) -> Dict[str, Any]:

    """
    Enrich a TopSpot TV-themes JSON file with Spotify metadata.
    - Reads data/json_files/genredecade/{decade}/{filename}
    - For each track, searches Spotify and fills spotify_track_id, spotify_artist_id, duration_ms, album_artwork, etc.
    - Updates track_ranking[*].track_id to the same spotify_track_id
    - Respects overrides if provided.
    """
    path = BASE_DIR / "data" / "json_files" / "genredecade" / decade / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        data = path.read_text(encoding="utf-8")
    except Exception as ex:
        logger.exception("Failed reading JSON file %s", path)
        raise HTTPException(status_code=400, detail=f"Could not read file: {ex}")

    import json
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as ex:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in file: {ex}")

    tracks: List[Dict[str, Any]] = payload.get("track") or []
    rankings: List[Dict[str, Any]] = payload.get("track_ranking") or []

    if max_items and max_items < len(tracks):
        work_indexes = list(range(max_items))
    else:
        work_indexes = list(range(len(tracks)))

    # lazy Spotify holder (init only if/when needed)
    sp_ref = {"sp": None}

    ok, skipped, misses, forced = 0, 0, [], 0

    # Quick override dict for O(1) checks
    olist = overrides or []

    def _find_override(show: str, theme: str) -> Optional[str]:
        sn, tn = _norm(show), _norm(theme)
        for ov in olist:
            ms, mt, sid = (
                ov.get("match_show"),
                ov.get("match_theme"),
                ov.get("spotify_track_id"),
            )
            if not sid:
                continue
            if (not ms or _norm(ms) == sn) and (not mt or _norm(mt) == tn):
                return sid
        return None

    for idx in work_indexes:
        t = tracks[idx]
        theme = t.get("track_name") or ""
        show = (
            t.get("show_name")
            or t.get("artist_display_name")
            or t.get("artist_name")
            or ""
        ).strip() or "Unknown Show"

        already = bool(t.get("spotify_track_id"))
        if already and not overwrite:
            skipped += 1
            continue

        # defaults if parsing fails
        ystart, yend = 1950, 1969
        years_on_air_raw = (t.get("years_on_air") or "").strip()

        # match: 1957–1966, 1957-66, 1957–present, etc.
        m = re.search(r"(\d{4})\s*[–-]\s*(\d{1,4}|present)?", years_on_air_raw, flags=re.I)
        if m:
            ystart = int(m.group(1))
            end_s = (m.group(2) or "").strip().lower()
            if end_s and end_s != "present":
                if len(end_s) <= 2:
                    base = (ystart // 100) * 100
                    yend = base + int(end_s)
                    if yend < ystart:
                        yend += 100
                else:
                    yend = int(end_s)
            else:
                yend = ystart
        else:
            m2 = re.search(r"(\d{4})", years_on_air_raw)
            if m2:
                ystart = yend = int(m2.group(1))

        # infer decade bounds (e.g., "1950s" → 1950–1959)
        m_dec = re.fullmatch(r"(\d{4})s", decade)
        if m_dec:
            dstart = int(m_dec.group(1))
            dend = dstart + 9
            ystart = max(ystart, dstart)
            yend = min(yend, dend)

        # 1) If override provided, use it
        forced_id = _find_override(show, theme)
        sp_track = None
        sp_client = None

        if forced_id:
            try:
                sp_client = _ensure_spotify(sp_ref)
                sp_track = sp_client.track(forced_id, market="US")
                forced += 1
            except Exception as ex:
                logger.warning(
                    "Override id %s failed for %s – %s: %s", forced_id, show, theme, ex
                )
                sp_track = None

        # 2) Otherwise search
        if sp_track is None:
            if sp_client is None:
                sp_client = _ensure_spotify(sp_ref)
            sp_track = _search_spotify_theme(sp_client, theme, show, ystart, yend)

        if sp_track:
            _update_track_fields(t, sp_track)
            ok += 1
        else:
            misses.append({"index": idx, "show": show, "theme": theme})

    # Sync track_ranking[*].track_id to the freshly set spotify_track_id
    id_by_name = {
        (tr.get("track_display_name") or tr.get("track_name") or "").strip(): tr.get(
            "spotify_track_id"
        )
        for tr in tracks
    }
    for r in rankings:
        nm = (r.get("track_name") or "").strip()
        if id_by_name.get(nm):
            r["track_id"] = id_by_name[nm]

    # ---------- Fill artist_artwork (prefer artist image; fallback to album art) ----------
    artist_image_cache: Dict[str, Optional[str]] = {}
    album_art_by_artist: Dict[str, Optional[str]] = {}

    for t in tracks:
        aid = t.get("spotify_artist_id") or ""
        if not aid:
            continue

        if aid not in artist_image_cache:
            sp_client = _ensure_spotify(sp_ref)
            artist_image_cache[aid] = _best_artist_image(sp_client, aid)

        if aid not in album_art_by_artist and t.get("album_artwork"):
            album_art_by_artist[aid] = t["album_artwork"]

    filled_track_artist_artwork = 0
    for t in tracks:
        aid = t.get("spotify_artist_id") or ""
        url = None
        if aid:
            url = artist_image_cache.get(aid) or album_art_by_artist.get(aid)
        else:
            if t.get("album_artwork"):
                url = t["album_artwork"]

        if url and not t.get("artist_artwork"):
            t["artist_artwork"] = url
            filled_track_artist_artwork += 1

    # ---------- Add any missing top-level artists from tracks, then fill their artwork ----------
    show_names_norm = {_normkey(t.get("show_name") or "") for t in tracks if (t.get("show_name") or "").strip()}

    artist_list = payload.get("artist") or []
    artist_by_id: Dict[str, Dict[str, Any]] = {}
    artist_by_name: Dict[str, Dict[str, Any]] = {}
    for a in artist_list:
        aid0 = (a.get("spotify_artist_id") or "").strip()
        nm0 = (a.get("artist_name") or "").strip().lower()
        if aid0:
            artist_by_id[aid0] = a
        if nm0:
            artist_by_name[nm0] = a
    added_top_artists = 0

    for t in tracks:
        aid = (t.get("spotify_artist_id") or "").strip()
        anm = (t.get("artist_display_name") or t.get("artist_name") or "").strip()
        anm_l = anm.lower()

        # NEW: skip bad actors
        if not anm or _looks_generic_artist(anm) or _is_show_title_as_artist(anm, show_names_norm):
            continue

        if aid:
            already = artist_by_id.get(aid) or artist_by_name.get(anm_l)
        else:
            already = artist_by_name.get(anm_l)

        if not already:
            new_artist = {
                "artist_name": anm,
                "spotify_artist_id": aid,
                "artist_artwork": None,
                "artist_description": "",
                "not_on_spotify": False if aid else True,
            }
            artist_list.append(new_artist)
            if aid:
                artist_by_id[aid] = new_artist
            artist_by_name[anm_l] = new_artist
            added_top_artists += 1

    filled_top_artist_artwork = 0
    for a in artist_list:
        aid = (a.get("spotify_artist_id") or "").strip()
        url = None
        if aid:
            url = artist_image_cache.get(aid) or album_art_by_artist.get(aid)
        if not url and a.get("artist_name"):
            nm_l = a["artist_name"].strip().lower()
            for t in tracks:
                t_nm_l = (
                    (t.get("artist_display_name") or t.get("artist_name") or "")
                    .strip()
                    .lower()
                )
                if t_nm_l == nm_l and t.get("album_artwork"):
                    url = t["album_artwork"]
                    break
        if url and not a.get("artist_artwork"):
            a["artist_artwork"] = url
            filled_top_artist_artwork += 1

    # ---- Filter & de-duplicate top-level artists (remove generics and show-titles) ----
    filtered = []
    seen_ids = set()
    seen_names = set()

    for a in artist_list:
        nm = (a.get("artist_name") or "").strip()
        if not nm:
            continue
        if _looks_generic_artist(nm) or _is_show_title_as_artist(nm, show_names_norm):
            continue

        aid = (a.get("spotify_artist_id") or "").strip()
        key = aid or nm.lower()
        if key in seen_ids or nm.lower() in seen_names:
            continue

        filtered.append(a)
        if aid:
            seen_ids.add(aid)
        seen_names.add(nm.lower())

    # Optional: drop the "Various Artists" stub entirely
    filtered = [a for a in filtered if a["artist_name"].strip().lower() != "various artists"]

    artist_list = filtered
    # payload["artist"] = artist_list

    # ---------- Global emoji scrub on existing text ----------
    scrubbed_details_count = 0
    scrubbed_intros_count = 0
    if scrub_emojis:
        for t in tracks:
            if t.get("detail"):
                cleaned = de_emoji(t["detail"])
                if cleaned != t["detail"]:
                    t["detail"] = cleaned
                    scrubbed_details_count += 1
        for r in rankings:
            if r.get("intro"):
                cleaned = de_emoji(r["intro"])
                if cleaned != r["intro"]:
                    r["intro"] = cleaned
                    scrubbed_intros_count += 1




    # Persist possibly-extended artist list
    payload["artist"] = artist_list

    # ---------- Indexes for lookups ----------
    track_by_spotify: Dict[str, Dict[str, Any]] = {}
    tracks_by_name: Dict[str, List[Dict[str, Any]]] = {}
    for t in tracks:
        tid = (t.get("spotify_track_id") or "").strip()
        nm = (t.get("track_display_name") or t.get("track_name") or "").strip()
        if tid:
            track_by_spotify[tid] = t
        if nm:
            tracks_by_name.setdefault(nm, []).append(t)

    # ---------- Fill/overwrite narrative fields ----------
    filled_track_details = 0
    for idx in work_indexes:
        t = tracks[idx]
        if overwrite_details or not (t.get("detail") or "").strip():
            show = t.get("show_name") or t.get("track_display_name") or t.get("track_name") or ""
            years = t.get("years_on_air") or ""
            sgenre = t.get("show_genre") or t.get("genre_label") or t.get("genre") or ""
            t["detail"] = de_emoji(_synth_detail(show, years, sgenre, meta=t))
            filled_track_details += 1

    filled_ranking_intros = 0
    filled_ranking_artist_names = 0
    for r in rankings:
        # overwrite or fill missing intro
        if overwrite_intros or not (r.get("intro") or "").strip():
            tr = None
            rid = (r.get("track_id") or "").strip()
            if rid and rid in track_by_spotify:
                tr = track_by_spotify[rid]
            else:
                nm = (r.get("track_name") or "").strip()
                cands = tracks_by_name.get(nm) or []
                tr = cands[0] if len(cands) == 1 else None

            show = (tr.get("show_name") if tr else r.get("track_name")) or ""
            years = (tr.get("years_on_air") if tr else "") or ""
            sgenre = (tr.get("show_genre") if tr else r.get("genre")) or ""
            r["intro"] = de_emoji(_synth_intro(r.get("rank"), show, years, sgenre))
            filled_ranking_intros += 1

        if not (r.get("artist_name") or "").strip():
            tr = None
            rid = (r.get("track_id") or "").strip()
            if rid and rid in track_by_spotify:
                tr = track_by_spotify[rid]
            else:
                nm = (r.get("track_name") or "").strip()
                cands = tracks_by_name.get(nm) or []
                tr = cands[0] if len(cands) == 1 else None
            if tr:
                r["artist_name"] = (
                    tr.get("artist_name") or tr.get("artist_display_name") or r.get("artist_name") or ""
                )
                if r["artist_name"]:
                    filled_ranking_artist_names += 1

        if not r.get("created_at"):
            r["created_at"] = date.today().isoformat()

    # Persist
    if not dry_run:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "file": str(path),
        "processed": len(work_indexes),
        "updated": ok,
        "skipped": skipped,
        "forced_overrides": forced,
        "misses": misses,
        "filled_track_artist_artwork": filled_track_artist_artwork,
        "filled_top_artist_artwork": filled_top_artist_artwork,
        "added_top_artists": added_top_artists,
        "dry_run": dry_run,
        "overwrite": overwrite,
        "overwrite_details": overwrite_details,
        "overwrite_intros": overwrite_intros,
        "scrub_emojis": scrub_emojis,
        "scrubbed_details_count": scrubbed_details_count,
        "scrubbed_intros_count": scrubbed_intros_count,
        "filled_track_details": filled_track_details,
        "filled_ranking_intros": filled_ranking_intros,
        "filled_ranking_artist_names": filled_ranking_artist_names,

    }
