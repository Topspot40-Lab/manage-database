import json

def build_html_player(title: str, mode: str, lang: str, base_url: str, sequence: list[dict],
                      play_track: bool, play_endpoint_path: str, query_extra: dict[str,str]) -> str:
    # `play_endpoint_path` e.g. "/supabase/play-track-by-rank" or "/supabase/collections/play-track-by-rank"
    # `query_extra` gets merged into the fetch URL (e.g. decade/genre or collection_slug)
    return f"""<!doctype html>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{title} ({mode})</title>
<style>
 body{{font:16px/1.5 system-ui,Segoe UI,Roboto,Arial;background:#0b0b0c;color:#e6e6e6;max-width:760px;margin:24px auto;padding:0 14px}}
 button{{font:inherit;padding:10px 14px;border-radius:12px;border:0;background:#2b6;cursor:pointer}}
 button[disabled]{{opacity:.5;cursor:not-allowed}}
 .muted{{color:#9aa}} .row{{margin:.5rem 0}}
 .badge{{display:inline-block;background:#222;border:1px solid #333;border-radius:10px;padding:2px 8px;margin-right:6px}}
 .log{{white-space:pre-wrap;background:#111;border:1px solid #222;border-radius:12px;padding:10px;margin-top:12px;max-height:40vh;overflow:auto}}
</style>
<h2>{title}</h2>
<p class="muted">Mode: <b>{mode}</b> • Language: <b>{lang}</b></p>
<div class="row"><button id="go">▶ Start</button> <span id="status" class="badge">idle</span></div>
<ol id="list"></ol>
<div class="log" id="log"></div>
<script>
const seq = {json.dumps(sequence)};
const base = {json.dumps(base_url)};
const lang = {json.dumps(lang)};
const playTrack = {json.dumps(play_track)};
const extra = {json.dumps(query_extra)};

const elList = document.getElementById('list');
const elStatus = document.getElementById('status');
const elLog = document.getElementById('log');
function log(msg){{ elLog.textContent += msg + "\\n"; elLog.scrollTop = elLog.scrollHeight; }}
function setStatus(s){{ elStatus.textContent = s; }}

seq.forEach(step => {{
  const li = document.createElement('li');
  li.textContent = `#${{step.rank}} — ${{step.track_name}} — ${{step.artist_name||""}}`;
  elList.appendChild(li);
}});

function playOne(url) {{
  return new Promise((resolve, reject) => {{
    const a = new Audio(url);
    a.preload = "auto";
    a.onended = () => resolve();
    a.onerror = () => reject(new Error("Audio error: " + url));
    a.play().catch(reject);
  }});
}}

async function playNarrations(step) {{
  const urls = [];
  if (Array.isArray(step.intros)) urls.push(...step.intros);
  if (step.detail) urls.push(step.detail);
  if (step.artist) urls.push(step.artist);
  for (const u of urls) {{
    setStatus("narration"); log("▶ " + u);
    try {{ await playOne(u); }} catch(e) {{ log("skip: " + e.message); }}
  }}
}}

async function startSpotify(rank, spotifyId) {{
  setStatus("spotify");
  const qs = new URLSearchParams({{ ...extra, rank, play_intro: "false", play_detail: "false", play_artist_description: "false", play_track: "true", tts_language: lang }});
  const url = `${{base}}{play_endpoint_path}?${{qs.toString()}}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error("Spotify play failed: " + r.status);
}}

document.getElementById('go').onclick = async () => {{
  const btn = document.getElementById('go'); btn.disabled = true;
  try {{
    for (const step of seq) {{
      await playNarrations(step);
      if (playTrack && step.spotify_track_id) {{
        await startSpotify(step.rank, step.spotify_track_id);
        setStatus("waiting");
      }}
    }}
    setStatus("done");
  }} catch (e) {{
    console.error(e); log("ERROR: " + e.message); setStatus("error");
  }} finally {{
    btn.disabled = false;
  }}
}};
</script>
"""
