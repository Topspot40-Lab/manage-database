# "Supabase"/expand_tv_themes.py
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from backend.config import BASE_DIR

logger = logging.getLogger("expand_tv_themes")
router = APIRouter(tags=["Generators"], prefix="/generate")

# ─────────────────────────────────────────────────────────────────────────────
# Seed helpers
# Format per line: "Show|Years|Genre|[ThemeOverride]"
# If ThemeOverride is omitted, theme defaults to "Show Theme".
# Years may be "1951-1957" (hyphen). We'll also accept "–".
# ─────────────────────────────────────────────────────────────────────────────

def _S(lines: List[str]) -> List[Dict[str, str]]:
    out = []
    for ln in lines:
        if not ln.strip():
            continue
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) < 3:
            continue
        show, years, genre = parts[:3]
        theme = parts[3] if len(parts) >= 4 and parts[3] else f"{show} Theme"
        # normalize years separator to hyphen
        years = re.sub(r"[–\u2013\u2014]", "-", years)
        out.append({"show": show, "years": years, "genre": genre, "theme": theme})
    return out

SEEDS_BY_DECADE: Dict[str, List[Dict[str, str]]] = {
    # 1950s — includes a few famous non-generic theme titles
    "1950s": _S([
        "I Love Lucy|1951-1957|sitcom|I Love Lucy Theme",
        "The Honeymooners|1955-1956|sitcom",
        "The Adventures of Superman|1952-1958|adventure|Superman Main Title",
        "Dragnet|1951-1959|crime|Dragnet Theme",
        "Perry Mason|1957-1966|legal drama|Park Avenue Beat",
        "Gunsmoke|1955-1975|western",
        "Bonanza|1959-1973|western|Bonanza Theme",
        "The Twilight Zone|1959-1964|anthology/sci-fi|The Twilight Zone Theme",
        "Leave It to Beaver|1957-1963|sitcom|The Toy Parade",
        "The Phil Silvers Show (Sgt. Bilko)|1955-1959|sitcom",
        "The Jack Benny Program|1950-1965|comedy/variety",
        "The George Burns and Gracie Allen Show|1950-1958|sitcom|Love Nest",
        "The Red Skelton Show|1951-1971|comedy/variety|Holiday for Strings",
        "The Adventures of Ozzie and Harriet|1952-1966|sitcom",
        "Father Knows Best|1954-1960|sitcom",
        "The Donna Reed Show|1958-1966|sitcom",
        "The Real McCoys|1957-1963|sitcom",
        "The Mickey Mouse Club|1955-1959|kids/variety|Mickey Mouse March",
        "Zorro|1957-1959|adventure",
        "The Cisco Kid|1950-1956|western",
        "The Life and Legend of Wyatt Earp|1955-1961|western",
        "Cheyenne|1955-1963|western",
        "Maverick|1957-1962|western",
        "Have Gun – Will Travel|1957-1963|western|The Ballad of Paladin",
        "Rawhide|1959-1965|western|Rawhide",
        "The Rifleman|1958-1963|western",
        "Wagon Train|1957-1965|western",
        "Bat Masterson|1958-1961|western",
        "Tales of Wells Fargo|1957-1962|western",
        "The Restless Gun|1957-1959|western",
        "The Adventures of Rin Tin Tin|1954-1959|adventure/western",
        "Lassie|1954-1971|family/adventure",
        "Sea Hunt|1958-1961|adventure",
        "77 Sunset Strip|1958-1964|detective",
        "Peter Gunn|1958-1961|detective/jazz|Peter Gunn",
        "M Squad|1957-1960|crime",
        "The Untouchables|1959-1963|crime",
        "The Many Loves of Dobie Gillis|1959-1963|sitcom|Dobie",
        "The Adventures of Robin Hood|1955-1959|adventure",
        "The Invisible Man|1958-1960|sci-fi",
        "Captain Kangaroo|1955-1984|children|Puffin' Billy",
        "Howdy Doody|1947-1960|children",
        "The Lone Ranger|1949-1957|western|William Tell Overture",
        "The Danny Thomas Show (Make Room for Daddy)|1953-1964|sitcom",
        "Fury|1955-1960|family/western",
        "The Addams Family|1964-1966|sitcom|The Addams Family Theme",  # bonus carryover fits late-50s vibe too
    ]),
    "1960s": _S([
        "Mission: Impossible|1966-1973|spy",
        "Hawaii Five-O|1968-1980|crime",
        "Star Trek|1966-1969|sci-fi",
        "Batman|1966-1968|superhero",
        "The Andy Griffith Show|1960-1968|sitcom",
        "The Dick Van Dyke Show|1961-1966|sitcom",
        "Bewitched|1964-1972|sitcom",
        "The Addams Family|1964-1966|sitcom",
        "Gilligan's Island|1964-1967|sitcom",
        "The Monkees|1966-1968|sitcom/music",
        "Get Smart|1965-1970|spy/sitcom",
        "I Dream of Jeannie|1965-1970|sitcom",
        "The Brady Bunch|1969-1974|sitcom",
        "The Beverly Hillbillies|1962-1971|sitcom",
        "Green Acres|1965-1971|sitcom",
        "Petticoat Junction|1963-1970|sitcom",
        "The Fugitive|1963-1967|drama",
        "The Avengers|1961-1969|spy",
        "Doctor Who|1963-1989|sci-fi",
        "The Saint|1962-1969|spy",
        "Thunderbirds|1965-1966|adventure",
        "The Prisoner|1967-1968|spy/drama",
        "Hogan's Heroes|1965-1971|sitcom",
        "The Man from U.N.C.L.E.|1964-1968|spy",
        "Lost in Space|1965-1968|sci-fi",
        "Dark Shadows|1966-1971|gothic soap",
        "Rowan & Martin's Laugh-In|1968-1973|sketch/comedy",
        "Dragnet 1967|1967-1970|crime",
        "The Mod Squad|1968-1973|crime",
        "The Wild Wild West|1965-1969|western/spy",
        "The Lucy Show|1962-1968|sitcom",
        "My Three Sons|1960-1972|sitcom",
        "The Flintstones|1960-1966|animation",
        "The Jetsons|1962-1963|animation",
        "Scooby-Doo, Where Are You!|1969-1970|animation",
        "Top of the Pops|1964-2006|music",
        "The Munsters|1964-1966|sitcom",
        "The Outer Limits|1963-1965|sci-fi",
        "The Patty Duke Show|1963-1966|sitcom",
        "The Smothers Brothers Comedy Hour|1967-1969|variety",
        "The Courtship of Eddie's Father|1969-1972|sitcom",
        "Adam-12|1968-1975|police",
        "Mannix|1967-1975|detective",
        "Ironside|1967-1975|crime",
        "Love, American Style|1969-1974|comedy",
    ]),
    "1970s": _S([
        "M*A*S*H|1972-1983|dramedy",
        "Happy Days|1974-1984|sitcom",
        "Laverne & Shirley|1976-1983|sitcom",
        "The Mary Tyler Moore Show|1970-1977|sitcom",
        "The Bob Newhart Show|1972-1978|sitcom",
        "The Odd Couple|1970-1975|sitcom",
        "All in the Family|1971-1979|sitcom",
        "Sanford and Son|1972-1977|sitcom",
        "The Jeffersons|1975-1985|sitcom",
        "Good Times|1974-1979|sitcom",
        "Little House on the Prairie|1974-1983|drama",
        "Charlie's Angels|1976-1981|crime",
        "Starsky & Hutch|1975-1979|crime",
        "The Rockford Files|1974-1980|detective",
        "Columbo|1971-1978|detective",
        "Kojak|1973-1978|crime",
        "CHiPs|1977-1983|police",
        "Baretta|1975-1978|crime",
        "Taxi|1978-1983|sitcom",
        "Welcome Back, Kotter|1975-1979|sitcom",
        "Three's Company|1977-1984|sitcom",
        "The Muppet Show|1976-1981|variety",
        "The Six Million Dollar Man|1973-1978|sci-fi",
        "The Bionic Woman|1976-1978|sci-fi",
        "The Dukes of Hazzard|1979-1985|action/comedy",
        "WKRP in Cincinnati|1978-1982|sitcom",
        "Dallas|1978-1991|soap",
        "The Love Boat|1977-1987|comedy",
        "Fantasy Island|1977-1984|fantasy",
        "Sesame Street|1969- |children",
        "Soap|1977-1981|sitcom/soap",
        "Barney Miller|1975-1982|sitcom",
        "Quincy, M.E.|1976-1983|crime",
        "One Day at a Time|1975-1984|sitcom",
        "The Waltons|1972-1981|drama",
        "Maude|1972-1978|sitcom",
        "Rhoda|1974-1978|sitcom",
        "The Rookies|1972-1976|police",
        "S.W.A.T.|1975-1976|police",
        "The White Shadow|1978-1981|drama",
        "What's Happening!!|1976-1979|sitcom",
        "Eight Is Enough|1977-1981|drama",
        "The Incredible Hulk|1977-1982|sci-fi",
        "Wonder Woman|1975-1979|superhero",
    ]),
    "1980s": _S([
        "Knight Rider|1982-1986|action",
        "Miami Vice|1984-1989|crime",
        "The A-Team|1983-1987|action",
        "Magnum, P.I.|1980-1988|detective",
        "Cheers|1982-1993|sitcom",
        "The Cosby Show|1984-1992|sitcom",
        "Family Ties|1982-1989|sitcom",
        "Growing Pains|1985-1992|sitcom",
        "The Golden Girls|1985-1992|sitcom",
        "Who's the Boss?|1984-1992|sitcom",
        "ALF|1986-1990|sitcom",
        "MacGyver|1985-1992|action",
        "The Facts of Life|1979-1988|sitcom",
        "Diff'rent Strokes|1978-1986|sitcom",
        "Hill Street Blues|1981-1987|police",
        "St. Elsewhere|1982-1988|drama",
        "L.A. Law|1986-1994|legal",
        "Dynasty|1981-1989|soap",
        "Dallas|1978-1991|soap",
        "Falcon Crest|1981-1990|soap",
        "Airwolf|1984-1986|action",
        "Fraggle Rock|1983-1987|children",
        "The Transformers|1984-1987|animation",
        "G.I. Joe|1983-1986|animation",
        "He-Man and the Masters of the Universe|1983-1985|animation",
        "ThunderCats|1985-1989|animation",
        "DuckTales|1987-1990|animation",
        "Teenage Mutant Ninja Turtles|1987-1996|animation",
        "The Wonder Years|1988-1993|drama",
        "Doogie Howser, M.D.|1989-1993|dramedy",
        "Moonlighting|1985-1989|dramedy",
        "Murder, She Wrote|1984-1996|mystery",
        "21 Jump Street|1987-1991|police",
        "Family Matters|1989-1998|sitcom",
        "Full House|1987-1995|sitcom",
        "Newhart|1982-1990|sitcom",
        "The Equalizer|1985-1989|crime",
        "Remington Steele|1982-1987|detective",
        "Perfect Strangers|1986-1993|sitcom",
        "Night Court|1984-1992|sitcom",
        "Highway to Heaven|1984-1989|drama",
        "The Fall Guy|1981-1986|action",
        "Amazing Stories|1985-1987|anthology",
        "Quantum Leap|1989-1993|sci-fi",
    ]),
    "1990s": _S([
        "Friends|1994-2004|sitcom",
        "Seinfeld|1989-1998|sitcom",
        "The X-Files|1993-2002|sci-fi",
        "ER|1994-2009|medical",
        "NYPD Blue|1993-2005|police",
        "Law & Order|1990-2010|legal/police",
        "Frasier|1993-2004|sitcom",
        "Home Improvement|1991-1999|sitcom",
        "Roseanne|1988-1997|sitcom",
        "The Fresh Prince of Bel-Air|1990-1996|sitcom",
        "The Nanny|1993-1999|sitcom",
        "Boy Meets World|1993-2000|sitcom",
        "Dawson's Creek|1998-2003|teen drama",
        "Beverly Hills, 90210|1990-2000|teen drama",
        "Twin Peaks|1990-1991|mystery",
        "The West Wing|1999-2006|political",
        "Ally McBeal|1997-2002|legal",
        "Third Rock from the Sun|1996-2001|sitcom",
        "King of the Hill|1997-2010|animation",
        "Family Guy|1999- |animation",
        "South Park|1997- |animation",
        "Pokémon|1997- |animation",
        "Mighty Morphin Power Rangers|1993-1996|action",
        "Walker, Texas Ranger|1993-2001|action",
        "Baywatch|1989-2001|drama",
        "Buffy the Vampire Slayer|1997-2003|fantasy",
        "Charmed|1998-2006|fantasy",
        "Stargate SG-1|1997-2007|sci-fi",
        "Spin City|1996-2002|sitcom",
        "Northern Exposure|1990-1995|dramedy",
        "Everybody Loves Raymond|1996-2005|sitcom",
        "Will & Grace|1998-2006|sitcom",
        "That '70s Show|1998-2006|sitcom",
        "Mad About You|1992-1999|sitcom",
        "Homicide: Life on the Street|1993-1999|police",
        "Party of Five|1994-2000|drama",
        "NewsRadio|1995-1999|sitcom",
        "7th Heaven|1996-2007|drama",
        "Xena: Warrior Princess|1995-2001|adventure",
        "Hercules: The Legendary Journeys|1995-1999|adventure",
        "Batman: The Animated Series|1992-1995|animation",
        "Animaniacs|1993-1998|animation",
        "The Ren & Stimpy Show|1991-1996|animation",
    ]),
    "2000s": _S([
        "CSI: Crime Scene Investigation|2000-2015|crime",
        "CSI: Miami|2002-2012|crime",
        "NCIS|2003- |crime",
        "House|2004-2012|medical",
        "Lost|2004-2010|drama",
        "24|2001-2010|action",
        "The Office (US)|2005-2013|sitcom",
        "Scrubs|2001-2010|sitcom",
        "How I Met Your Mother|2005-2014|sitcom",
        "Grey's Anatomy|2005- |medical",
        "Desperate Housewives|2004-2012|dramedy",
        "The Sopranos|1999-2007|drama",
        "The Wire|2002-2008|drama",
        "Mad Men|2007-2015|drama",
        "Breaking Bad|2008-2013|drama",
        "Arrested Development|2003-2006|sitcom",
        "Veronica Mars|2004-2007|mystery",
        "Supernatural|2005-2020|fantasy",
        "Prison Break|2005-2009|drama",
        "Battlestar Galactica|2004-2009|sci-fi",
        "Doctor Who|2005- |sci-fi",
        "Heroes|2006-2010|sci-fi",
        "True Blood|2008-2014|fantasy",
        "Dexter|2006-2013|crime",
        "Chuck|2007-2012|spy",
        "Friday Night Lights|2006-2011|drama",
        "One Tree Hill|2003-2012|drama",
        "Smallville|2001-2011|superhero",
        "Avatar: The Last Airbender|2005-2008|animation",
        "Malcolm in the Middle|2000-2006|sitcom",
        "Monk|2002-2009|detective",
        "Psych|2006-2014|detective",
        "The Shield|2002-2008|crime",
        "The Big Bang Theory|2007-2019|sitcom",
        "Pushing Daisies|2007-2009|fantasy",
        "Skins (UK)|2007-2013|teen drama",
        "Ugly Betty|2006-2010|dramedy",
        "Glee|2009-2015|musical",
        "The Hills|2006-2010|reality",
        "Top Gear|2002-2015|motoring",
        "SpongeBob SquarePants|1999- |animation",
    ]),
    "2010s": _S([
        "Game of Thrones|2011-2019|fantasy",
        "Stranger Things|2016- |sci-fi",
        "The Walking Dead|2010-2022|drama",
        "Westworld|2016-2022|sci-fi",
        "True Detective|2014- |anthology",
        "Sherlock|2010-2017|detective",
        "Downton Abbey|2010-2015|drama",
        "The Crown|2016- |drama",
        "Narcos|2015-2017|crime",
        "Better Call Saul|2015-2022|drama",
        "Mr. Robot|2015-2019|thriller",
        "The Mandalorian|2019- |sci-fi",
        "Rick and Morty|2013- |animation",
        "BoJack Horseman|2014-2020|animation",
        "Peaky Blinders|2013-2022|drama",
        "Black Mirror|2011- |anthology",
        "The Witcher|2019- |fantasy",
        "The Americans|2013-2018|drama",
        "Homeland|2011-2020|thriller",
        "Vikings|2013-2020|drama",
        "Suits|2011-2019|legal",
        "Fargo|2014- |anthology",
        "The Handmaid's Tale|2017- |drama",
        "Mindhunter|2017-2019|crime",
        "Legion|2017-2019|superhero",
        "The Expanse|2015-2022|sci-fi",
        "The Good Place|2016-2020|sitcom",
        "Brooklyn Nine-Nine|2013-2021|sitcom",
        "House of Cards|2013-2018|drama",
        "Orange Is the New Black|2013-2019|drama",
        "Archer|2009- |animation",
        "Gravity Falls|2012-2016|animation",
        "Steven Universe|2013-2019|animation",
        "Adventure Time|2010-2018|animation",
        "Fleabag|2016-2019|comedy",
        "Killing Eve|2018-2022|thriller",
        "Lucifer|2016-2021|fantasy",
        "The Umbrella Academy|2019- |superhero",
        "Chernobyl|2019|miniseries",
        "The Boys|2019- |superhero",
        "Cobra Kai|2018- |dramedy",
    ]),
    "2020s": _S([
        "The Last of Us|2023- |drama",
        "House of the Dragon|2022- |fantasy",
        "The Bear|2022- |drama",
        "Severance|2022- |thriller",
        "Andor|2022- |sci-fi",
        "Wednesday|2022- |mystery",
        "Squid Game|2021- |thriller",
        "Loki|2021- |superhero",
        "WandaVision|2021|superhero",
        "The White Lotus|2021- |drama",
        "The Sandman|2022- |fantasy",
        "Bridgerton|2020- |drama",
        "The Queen's Gambit|2020|miniseries",
        "Ted Lasso|2020-2023|comedy",
        "Only Murders in the Building|2021- |mystery/comedy",
        "Yellowjackets|2021- |drama",
        "Arcane|2021- |animation",
        "Reacher|2022- |action",
        "The Lincoln Lawyer|2022- |legal",
        "Peacemaker|2022- |superhero",
        "Ms. Marvel|2022|superhero",
        "The Book of Boba Fett|2021- |sci-fi",
        "Obi-Wan Kenobi|2022|miniseries",
        "Ahsoka|2023- |sci-fi",
        "Silo|2023- |sci-fi",
        "Fallout|2024- |sci-fi",
        "3 Body Problem|2024- |sci-fi",
        "Shogun|2024|miniseries",
        "One Piece (Live Action)|2023- |adventure",
        "Monarch: Legacy of Monsters|2023- |sci-fi",
        "The Diplomat|2023- |drama",
        "The Peripheral|2022|sci-fi",
        "Foundation|2021- |sci-fi",
        "The Boys (S2+)|2020s|superhero",
        "The Mandalorian (S2+)|2020s|sci-fi",
        "Halo|2022- |sci-fi",
        "The Wheel of Time|2021- |fantasy",
        "Rings of Power|2022- |fantasy",
        "She-Hulk: Attorney at Law|2022|superhero",
        "And Just Like That...|2021- |comedy/drama",
        "The Morning Show|2019- |drama",
        "Pachinko|2022- |drama",
        "The Night Agent|2023- |thriller",
        "Gen V|2023- |superhero",
        "A Murder at the End of the World|2023|miniseries",
    ]),
}

# ─────────────────────────────────────────────────────────────────────────────
# JSON helpers
# ─────────────────────────────────────────────────────────────────────────────

def _new_payload(decade: str) -> Dict[str, Any]:
    from datetime import datetime
    return {
        "language": "english",
        "category": decade,
        "genre": "tv themes",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "genre_table": [{"genre_name": "TV Themes"}],
        "decade": [{"decade_name": decade}],
        "artist": [],
        "track": [],
        "tracklist": [{
            "name": "TopSpot Autogen",
            "curator": "TopSpot",
            "is_official": True,
            "language": "en",
            "notes": f"Generated for TV Themes - {decade}",
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        }],
        "track_ranking": [],
    }

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _make_track(rank: int, show: str, theme: str, years: str, genre: str, decade: str) -> Dict[str, Any]:
    return {
        "ranking": rank,
        "track_name": theme,
        "show_name": show,
        "years_on_air": years,
        "show_genre": genre,
        # artist/spotify will be filled by enrich
        "artist_name": "",
        "artist_display_name": "",
        "spotify_track_id": "",
        "spotify_artist_id": "",
        "album_name": None,
        "album_artwork": None,
        "duration_ms": None,
        "popularity": None,
        "is_explicit": False,
        "intro": "",
        "detail": "",
        "artist_description": "",
        "decade": decade,
        "genre_label": "TV Themes",
    }

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{decade}")
def expand_tv_themes(
    decade: str,
    filename: str = Query(..., description="e.g., 1950s_tv_themes_en.json"),
    target: int = Query(45, ge=1, le=60),
    dry_run: bool = Query(False),
) -> Dict[str, Any]:
    if decade not in SEEDS_BY_DECADE:
        raise HTTPException(status_code=400, detail=f"No seeds configured for {decade}")

    path = BASE_DIR / "data" / "json_files" / "genredecade" / decade / filename
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = _new_payload(decade)

    tracks: List[Dict[str, Any]] = payload.get("track") or []
    rankings: List[Dict[str, Any]] = payload.get("track_ranking") or []

    # Existing keys to prevent duplicates
    existing_keys = {(_norm(t.get("show_name")), _norm(t.get("track_name"))) for t in tracks}
    have = len(tracks)
    need = max(0, target - have)

    seeds = SEEDS_BY_DECADE[decade]
    added_seeds: List[Dict[str, str]] = []
    # First pass: unique by show+theme
    for s in seeds:
        if need <= 0:
            break
        key = (_norm(s["show"]), _norm(s["theme"]))
        if key in existing_keys:
            continue
        added_seeds.append(s)
        existing_keys.add(key)
        need -= 1

    # If still short, allow a second theme from the same show if available
    if need > 0:
        for s in seeds:
            if need <= 0:
                break
            # permit duplicates by show if theme differs and we still need more
            key = (_norm(s["show"]), _norm(s["theme"]))
            if key in existing_keys:
                continue
            added_seeds.append(s)
            existing_keys.add(key)
            need -= 1

    # Realize into track objects and rankings
    rank_start = len(tracks) + 1
    new_tracks: List[Dict[str, Any]] = []
    new_rankings: List[Dict[str, Any]] = []
    for i, s in enumerate(added_seeds, start=rank_start):
        tr = _make_track(i, s["show"], s["theme"], s["years"], s["genre"], decade)
        new_tracks.append(tr)
        new_rankings.append({
            "track_id": "",
            "track_name": tr["track_name"],
            "artist_name": (tr.get("artist_name") or "").lower(),
            "rank": tr["ranking"],
            "genre": "tv themes",
            "decade": decade,
            "tracklist": "TopSpot Autogen",
            "intro": "",
            "created_at": None,
        })

    payload["track"] = tracks + new_tracks
    payload["track_ranking"] = rankings + new_rankings

    if not dry_run:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "file": str(path),
        "existing_count": len(tracks),
        "added_count": len(new_tracks),
        "new_total": len(payload["track"]),
        "dry_run": dry_run,
    }
