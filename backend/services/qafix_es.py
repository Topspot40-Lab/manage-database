# backend/services/qafix_es.py
from __future__ import annotations
import re
from typing import Tuple, List
# backend/services/qafix_es.py
from backend.services.locales_common import (
    strip_llm_brackets, contains_name,
    force_exact_casing, rebalance_parens_quotes,
    rank_ok,  # ← add this
)

# --- Glue + punctuation cleanup ---------------------------------------------
_CAMEL_GLUE = re.compile(r"(?<=[a-záéíóúüñ])(?=[A-ZÁÉÍÓÚÜÑ])")

def _unglue_camelcase(s: str) -> str:
    # Fix "SorryWindsong" → "Sorry Windsong" (safe in our narrow context)
    if not s: return s
    return _CAMEL_GLUE.sub(" ", s)

# Kill a stray, orphan closing quote fragment that appears right after the artist
# e.g., "'... 'Title' de John Denver SorryWindsong' ..." -> keep only the first clause
_ORPHAN_AFTER_ARTIST = re.compile(
    r"(\bde\s+[A-Za-zÁÉÍÓÚÜÑ&.\- ]{2,60})"      # "de <Artist>"
    r"(?:\s+[A-ZÁÉÍÓÚÜÑ][^\"'“”‘’,.){]{1,60})?"  # an extra CapWord run (optional)
    r"\s*['’](?=\s*(?:,|y\b|del\b|de\b|\.|$))",  # orphan closing quote
    flags=re.IGNORECASE
)

def _strip_orphan_quoted_fragment_after_artist(s: str) -> str:
    if not s: return s
    return _ORPHAN_AFTER_ARTIST.sub(r"\1", s)
def _tidy_spanish_punct_markdown(s: str) -> str:
    if not s:
        return s
    # strip common markdown artifacts
    s = s.replace("**", "").replace("__", "").replace("~~", "").replace("`", "")
    # collapse double inverted marks
    s = s.replace("¿¿", "¿").replace("¡¡", "¡")
    # remove space before punctuation, ensure single space after (except end of line)
    s = re.sub(r"\s+([,.;:!?…])", r"\1", s)
    s = re.sub(r"([,.;:!?…])(?!\s|$)", r"\1 ", s)
    # no space after inverted marks
    s = re.sub(r"([¿¡])\s+", r"\1", s)
    return s



def qa_intro_errors_es(text: str, rank: int, track: str, artist: str) -> List[str]:
    s = (text or "").strip()
    errs: List[str] = []
    if "#" in s:
        errs.append("Contains '#'.")
    if re.search(r"\bnumber\s*[:#-]?\s*\d+\b", s, re.IGNORECASE):
        errs.append("English 'number' token present for localized language.")
    if rank and not rank_ok(s, rank, "es"):   # ← use tolerant check
        errs.append(f"Missing localized rank phrase for es (e.g., 'número {rank}').")
    if track and not contains_name(s, track):
        errs.append("Track name altered/missing.")
    if artist and not contains_name(s, artist):
        errs.append("Artist name altered/missing.")
    return errs




# ── Rank phrase handling ─────────────────────────────────────────────────────
_EN_RANK_TOKENS_RE   = re.compile(r"(?i)\b(?:no\.?|number)\s*\d+\b|#\s*\d+\b|#\d+\b")
_NUMERO_NO_ACCENT_RE = re.compile(r"(?i)\bnumero\b")
_ES_RANK_PHRASE_RE   = re.compile(r"(?i)\bnú?mero\s+(\d+)\b")

def _ensure_rank_phrase_es(text: str, rank: int) -> str:
    t = text or ""

    def _sub_rank(m: re.Match) -> str:
        digits = re.findall(r"\d+", m.group(0))
        n = digits[0] if digits else str(rank)
        return f"número {n}"

    t = _EN_RANK_TOKENS_RE.sub(_sub_rank, t)
    t = _NUMERO_NO_ACCENT_RE.sub("número", t)

    if not _ES_RANK_PHRASE_RE.search(t):
        insert = f" número {rank}"
        comma_idx = t.find(",")
        if 0 <= comma_idx < 120:
            t = t[:comma_idx] + "," + insert + t[comma_idx + 1:]
        else:
            period_idx = t.find(".")
            if 0 < period_idx < 160:
                t = t[:period_idx] + insert + t[period_idx:]
            else:
                t = f"{t.strip()} (número {rank})"

    parts, last_end = [], 0
    for m in _ES_RANK_PHRASE_RE.finditer(t):
        parts.append(t[last_end:m.start()])
        parts.append(f"número {rank}")
        last_end = m.end()
    parts.append(t[last_end:])
    return "".join(parts)

# ── Title handling ───────────────────────────────────────────────────────────
_QUOTED_TITLE_RE = re.compile(r"[\"'“”‘’]([^\"'“”‘’]+)[\"'“”‘’]")

def _insert_or_replace_exact(subj_text: str, needle: str, label_intro: str) -> str:
    """Ensure exact track title appears, quoted once."""
    t = subj_text or ""
    if not needle or needle in t:
        return t

    clean = needle.replace('"', "").strip()
    quoted = f' "{clean}"'

    m = _QUOTED_TITLE_RE.search(t)
    if m:
        start, end = m.span(1)
        return t[:start] + clean + t[end:]

    comma_idx = t.find(",")
    if 0 <= comma_idx < 120:
        return t[:comma_idx] + "," + quoted + t[comma_idx + 1:]
    return t.rstrip() + f" — {label_intro} {quoted.strip()}"

# ── Artist placement/dedup ───────────────────────────────────────────────────
# ── Artist placement/dedup ───────────────────────────────────────────────────
def _ensure_artist_after_title(text: str, title: str, artist: str) -> str:
    """Prefer: '<title>' de {artist} …"""
    if not (text and title and artist):
        return text
    variants = [f"'{title}'", f"\"{title}\"", f"“{title}”", f"‘{title}’"]
    pos = -1
    picked = None
    for v in variants:
        pos = text.find(v)
        if pos != -1:
            picked = v
            break
    if pos == -1:
        return text

    after = text[pos + len(picked):]
    if after.lstrip().startswith(f" de {artist}"):
        return text

    t = text[:pos + len(picked)] + f" de {artist}" + text[pos + len(picked):]
    # Remove one nearby duplicate ", de {artist}"
    t = re.sub(
        rf"(,\s*)de\s+{re.escape(artist)}\b",
        r"\g<1>",   # keep the comma, drop the duplicate
        t,
        count=1,
        flags=re.IGNORECASE
    )
    return t

# Public, lint-friendly wrapper
def ensure_artist_after_title(text: str, title: str, artist: str) -> str:
    return _ensure_artist_after_title(text, title, artist)

__all__ = ["ensure_artist_after_title", "qa_fix_spanish_intro", "qa_intro_errors_es"]

_CONTRACTION_BITS = r"(?:re|ll|ve|m|d|s)"  # you're, I'll, I've, I'm, I'd, John's

def _fix_orphan_contractions_after_token(token: str, s: str) -> str:
    """
    Remove orphan English contraction bits immediately after a token, with or without apostrophe, with or without space:
      'Alabama're -> 'Alabama'
      'Alabamare  -> 'Alabama'
      'Restless Heartll -> 'Restless Heart'
    """
    if not token or not s:
        return s
    pat = re.compile(rf"({re.escape(token)})\s*(?:’|')?{_CONTRACTION_BITS}\b", re.IGNORECASE)
    return pat.sub(r"\g<1>", s)



def _insert_or_replace_exact_anycase(subj_text: str, needle: str, label_intro: str) -> str:
    """
    Case-insensitive version of _insert_or_replace_exact:
    - If a quoted chunk exists, replace its INNER text with the exact-cased title.
    - Else, if the (unquoted) title appears in any casing, replace that span with the exact title and quote it.
    - Else, insert a ' — {label_intro} "Title"' clause at a natural spot.
    """
    t = subj_text or ""
    if not needle:
        return t

    exact = needle.replace('"', "").strip()
    quoted_exact = f' "{exact}"'

    # 1) If *any* quoted chunk exists, replace its inner text (keeps the surrounding quotes)
    m = _QUOTED_TITLE_RE.search(t)
    if m:
        start, end = m.span(1)
        return t[:start] + exact + t[end:]

    # 2) If the (unquoted) title appears in any casing, replace that span and add quotes
    pat = re.compile(re.escape(exact), flags=re.IGNORECASE)
    if pat.search(t):
        return pat.sub(exact, t, count=1).replace(exact, f"'{exact}'", 1)

    # 3) Fallback: insert near the first comma; else append an em-dash clause
    comma_idx = t.find(",")
    if 0 <= comma_idx < 120:
        return t[:comma_idx] + "," + quoted_exact + t[comma_idx + 1:]
    return t.rstrip() + f" — {label_intro} {quoted_exact.strip()}"



def _dedupe_artist_mentions_es(text: str, artist: str) -> str:
    """Collapse repeated 'de ARTIST' runs into a single one."""
    if not (text and artist):
        return text
    pattern = re.compile(
        rf"(de\s+{re.escape(artist)}\b)(?:\s*,?\s*de\s+{re.escape(artist)}\b)+",
        re.IGNORECASE
    )
    return pattern.sub(r"\1", text)

# ── Orphan 're cleanup & spacing ─────────────────────────────────────────────
_ORPHAN_RE_GLOBAL = re.compile(r"(['’\"])re\b", re.IGNORECASE)

def _fix_orphan_re_globally(s: str) -> str:
    """Turn \"'Title're\" into \"'Title'\" etc."""
    if not s:
        return s
    return _ORPHAN_RE_GLOBAL.sub(r"\1", s)

def _fix_re_after_token(token: str, s: str) -> str:
    """
    Remove orphan 're/’re immediately after a specific token (artist/title without quotes):
      '... John Schneiderre the ...' -> '... John Schneider the ...'
    """
    if not token or not s:
        return s
    return re.sub(rf"({re.escape(token)})\s*(?:’|')re\b", r"\1", s, flags=re.IGNORECASE)


def _normalize_spaces_commas(s: str) -> str:
    """Tighten spaces & commas: ',  ' -> ', ', collapse multi-spaces."""
    if not s:
        return s
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s{2,}", ", ", s)
    s = re.sub(r"\s{2,}\.", ". ", s)
    return s

# Remove any additional quoted-title clauses after the first one,
# including an immediate " de <Artist...>" tail if present.
_QUOTED_TITLE_ANY = re.compile(r"[\"'“”‘’][^\"'“”‘’]{1,120}[\"'“”‘’]")

def _dedupe_extra_quoted_title_clauses(text: str) -> str:
    if not text:
        return text
    matches = list(_QUOTED_TITLE_ANY.finditer(text))
    if len(matches) <= 1:
        return text

    keep_end = matches[0].end()
    out = text[:keep_end]
    idx = keep_end
    tail = re.compile(r"\s*de\s+[A-Za-zÁÉÍÓÚÑ&.\- ]{1,60}", re.IGNORECASE)

    for m in matches[1:]:
        out += text[idx:m.start()]
        end = m.end()
        mt = tail.match(text, end)
        if mt:
            end = mt.end()  # also drop a trailing " de <Artist...>"
        idx = end

    out += text[idx:]
    return out
# If a name is glued to an opening quote, add a space:  elton john'cold → elton john 'cold
def _space_before_open_quote(s: str) -> str:
    if not s: return s
    return re.sub(r"(?<=[A-Za-zÁÉÍÓÚÜÑ])(['“‘])", r" \1", s)



def _force_title_exact_case(text: str, title: str) -> str:
    if not text or not title:
        return text
    pat = re.compile(re.escape(title), flags=re.IGNORECASE)
    tmp = pat.sub(title, text, count=1)  # fix casing first
    # if already quoted (either ' or “ ”), don't add quotes again
    already = re.compile(rf"[\"'“”‘’]\s*{re.escape(title)}\s*[\"'“”‘’]")
    if already.search(tmp):
        return tmp
    return tmp.replace(title, f"'{title}'", 1)

def _force_title_exact_case_fuzzy(text: str, title: str) -> str:
    """
    Fuzzy-match any case/spacing/apostrophe variant of the title
    and replace the FIRST occurrence with the **canonical quoted** title.

    Works even if the LLM output has "youre" for "You're", all lowercase,
    or has odd punctuation between tokens.
    """
    if not text or not title:
        return text

    # Build a tolerant pattern: split title into alnum tokens and allow
    # 0+ non-word chars between them in the text ("youre" vs "you're" handled by \W*)
    tokens = re.findall(r"\w+", title, flags=re.UNICODE)
    if not tokens:
        return text

    fuzzy = r"(?:\W*)".join(map(re.escape, tokens))  # allow dropped apostrophes etc.
    pat = re.compile(rf"\b{fuzzy}\b", flags=re.IGNORECASE)

    # If there's a quoted chunk already, keep its quotes but replace the inside
    m_quote = _QUOTED_TITLE_RE.search(text)
    if m_quote:
        start, end = m_quote.span(1)
        # Only replace if the inner text looks like it's trying to be the title
        inner = text[start:end]
        if pat.fullmatch(inner) or pat.search(inner):
            return text[:start] + title + text[end:]

    # Otherwise, replace the first fuzzy match in the whole string
    if pat.search(text):
        replaced = pat.sub(title, text, count=1)
        # Ensure it's quoted exactly once: if already quoted, keep; else add single quotes
        already = re.compile(rf"[\"'“”‘’]\s*{re.escape(title)}\s*[\"'“”‘’]")
        if already.search(replaced):
            return replaced
        return replaced.replace(title, f"'{title}'", 1)

    return text



# ── Fuzzy→exact casing ───────────────────────────────────────────────────────
def _fuzzy_pattern(name: str) -> str:
    if not name:
        return ""
    tokens = re.findall(r"\w+", name, flags=re.UNICODE)
    if not tokens:
        return ""
    between = r"(?:\W+)?"
    core = between.join(map(re.escape, tokens))
    return rf"\b{core}\b"

def _force_exact_casing_fuzzy(text: str, name: str) -> str:
    if not text or not name:
        return text
    pat = _fuzzy_pattern(name)
    if not pat:
        return text
    return re.sub(pat, name, text, flags=re.IGNORECASE)
import re

def _dedupe_quotes_around_title(text: str, title: str) -> str:
    if not title:
        return text

    # Build a case-insensitive pattern that matches any of these quotes,
    # optional spaces, the exact title, optional spaces, then the same quote again.
    pattern = re.compile(
        rf"([\"'“”‘’])\s*{re.escape(title)}\s*\1",
        flags=re.IGNORECASE
    )

    # Use a function replacement to avoid backreference pitfalls
    return pattern.sub(lambda m: f"{m.group(1)}{title}{m.group(1)}", text)


# ── Main fixer ───────────────────────────────────────────────────────────────
def qa_fix_spanish_intro(
    text: str,
    *,
    rank: int,
    track_name: str,
    artist_name: str
) -> Tuple[str, bool, List[str]]:
    issues: List[str] = []
    original = (text or "").strip()
    t = strip_llm_brackets(original).strip()

    # Rank phrase
    t2 = _ensure_rank_phrase_es(t, rank)
    if t2 != t:
        t = t2
        issues.append("rank_phrase_normalized")

    # '#' normalization (before spacing/dedupe)
    t = re.sub(r"#\s*(\d+)\s*(?:['’]s|s)\b", r"número \g<1>", t)  # '#1s' / "#1’s"
    t = re.sub(r"#\s*(\d+)\b", r"número \g<1>", t)  # '#1' / '# 1'
    t = re.sub(r"(?<=\w)(?=número\s+\d+\b)", " ", t)  # Boogienúmero → Boogie número
    t = re.sub(r"(?<!\w)#(?!\d)", "", t)  # strip stray '#', keep 'C#'

    # ── Title present/quoted (case-insensitive enforcement) ──
    if track_name:
        before = t
        # Always try to insert/replace (case-insensitive)
        t = _insert_or_replace_exact_anycase(t, track_name, "con")
        # Then force the exact canonical casing + quoting (fuzzy first, exact second)
        t = _force_title_exact_case_fuzzy(t, track_name)
        t = _force_title_exact_case(t, track_name)
        t = _dedupe_quotes_around_title(t, track_name)

        if t != before:
            issues.append("track_title_enforced")

    # Artist mention
    if artist_name and not ((artist_name in t) or (f"de {artist_name}" in t)):
        if "," in t:
            i = t.find(",")
            t = t[:i+1] + f" de {artist_name}" + t[i+1:]
        else:
            t = t.rstrip() + f" de {artist_name}"
        issues.append("artist_name_enforced")

    # Prefer "'Title' de ARTIST", then dedupe & spacing
    t = _ensure_artist_after_title(t, track_name, artist_name)
    t = _dedupe_extra_quoted_title_clauses(t)

    # NEW: glue fixes
    t = _unglue_camelcase(t)
    t = _strip_orphan_quoted_fragment_after_artist(t)
    t = _tidy_spanish_punct_markdown(t)

    # Normalize spacing first, then dedupe repeated "de ARTIST"
    t = _normalize_spaces_commas(t)
    t = _apply_spanish_contractions(t)
    t = _dedupe_artist_mentions_es(t, artist_name)

    # Remove orphan "'re"/"’re" and other bits glued to artist/title
    t = _fix_orphan_re_globally(t)
    t = _fix_re_after_token(artist_name, t)
    t = _fix_re_after_token(track_name, t)
    t = _fix_orphan_contractions_after_token(artist_name, t)  # NEW
    t = _fix_orphan_contractions_after_token(track_name, t)  # NEW

    # Casing: fuzzy then exact
    t = _force_exact_casing_fuzzy(t, track_name)
    t = _force_exact_casing_fuzzy(t, artist_name)
    t = force_exact_casing(t, track_name, artist_name)

    # Final tidy
    t = rebalance_parens_quotes(t)
    if t and t[-1] not in ".!?…":
        t += "."

    changed = (t != original)
    return t, changed, issues

_CONTRACTIONS = ( (re.compile(r"\bde el\b", re.IGNORECASE), "del"),
                  (re.compile(r"\ba el\b",  re.IGNORECASE), "al") )

def _apply_spanish_contractions(s: str) -> str:
    for pat, rep in _CONTRACTIONS:
        s = pat.sub(rep, s)
    return s
