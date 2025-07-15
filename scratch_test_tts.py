from pathlib import Path
from backend.services.tts.elevenlabs_tts import generate_tts_mp3
from backend.config import VOICE_ID_INTRO, VOICE_ID_ARTIST, VOICE_ID_TRACK
from playsound import playsound

# 🔍 Confirm voice IDs loaded
print(f"VOICE_ID_INTRO: {VOICE_ID_INTRO}")
print(f"VOICE_ID_ARTIST: {VOICE_ID_ARTIST}")
print(f"VOICE_ID_TRACK: {VOICE_ID_TRACK}")


# Voice test cases
tests = [
    {
        "voice_label": "intro",
        "voice_id": VOICE_ID_INTRO,
        "text": "This is your TopSpot ranking intro voice. At rank 37, this 1950s country ballad by a legendary figure will make you feel all the feels!",
        "filename": "intro_test.mp3"
    },
    {
        "voice_label": "artist",
        "voice_id": VOICE_ID_ARTIST,
        "text": "This is the voice used for artist biographies. Patti Page, an American singer born in 1927, was known for her versatile voice that spanned genres like traditional pop, country, and jazz. She rose to fame in the late 1940s with hits like \"Tennessee Waltz,\" which became one of the best-selling singles of the 20th century. Page was the top-charting female vocalist of the 1950s and was nicknamed \"The Singin' Rage, Miss Patti Page,\" and interestingly, she was one of the first artists to use multi-track recording techniques.",
        "filename": "artist_test.mp3"
    },
    {
        "voice_label": "track",
        "voice_id": VOICE_ID_TRACK,
        "text": "This voice presents the detailed track narratives in TopSpot.The song was written in a single afternoon, a burst of creativity that captured the hearts of many. Recorded in a studio known for its warm acoustics, the track benefited from the expertise of a seasoned engineer. It soared on the charts, becoming a symbol of the era's optimism. And that’s the hit that still ignites the airwaves!",
        "filename": "track_test.mp3"
    }
]

for test in tests:
    out_path = Path("data/mp3_files/voice_preview") / test["filename"]

    # ❌ Remove the file if it exists so it regenerates with the right voice
    if out_path.exists():
        print(f"🗑️ Deleting old file to force regeneration: {out_path}")
        out_path.unlink()

    generate_tts_mp3(test["text"], out_path, test["voice_id"])
    print(f"🔊 Playing {test['voice_label']} voice — Voice ID: {test['voice_id']}")
    clean_path = str(out_path.resolve()).replace("\\", "/")
    playsound(clean_path)


