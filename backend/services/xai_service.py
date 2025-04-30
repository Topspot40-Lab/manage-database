import os
import requests

XAI_API_KEY = os.getenv("XAI_API_KEY")
XAI_API_URL = "https://api.openai.com/v1/chat/completions"

def get_top_tracks_from_xai(category: str, genre: str, num_tracks: int, language: str):
    prompt = (
        f"Generate a list of the top {num_tracks} {genre} songs from the {category}. "
        f"List each song with its rank, title, artist, and year released. "
        f"Output JSON with keys: rank, trackName, artistName, yearReleased."
    )
    messages = [{"role": "user", "content": prompt}]
    response = requests.post(
        XAI_API_URL,
        headers={
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4",
            "messages": messages,
            "temperature": 0.8
        }
    )

    result = response.json()

    print("XAI result returned:", result)

    if "choices" not in result:
        raise ValueError(f"❌ XAI call failed or unexpected response: {result}")

    return result["choices"][0]["message"]["content"]

    text = result["choices"][0]["message"]["content"]

    try:
        data = eval(text) if isinstance(text, str) else text
        return data
    except Exception as e:
        print("Error parsing response:", e)
        return []

def get_track_descriptions_from_xai(track_data, language: str, category: str, genre: str):
    prompt = (
        f"For each of the following {genre} songs from the {category}, write an 'intro' and 'detail' in {language}. "
        f"The 'intro' should include the rank, genre, decade, song title, and artist in a fun countdown style. "
        f"The 'detail' should include about 4 sentences with interesting or funny info about the song or artist. "
        f"Return JSON list with keys: intro, detail."
    )
    formatted_list = "\n".join(
        [f"{item['rank']}. {item['trackName']} by {item['artistName']}" for item in track_data]
    )

    messages = [
        {"role": "user", "content": prompt},
        {"role": "user", "content": formatted_list}
    ]

    response = requests.post(
        XAI_API_URL,
        headers={
            "Authorization": f"Bearer {XAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "gpt-4",
            "messages": messages,
            "temperature": 0.8
        }
    )

    result = response.json()
    text = result["choices"][0]["message"]["content"]

    try:
        data = eval(text) if isinstance(text, str) else text
        return data
    except Exception as e:
        print("Error parsing descriptions:", e)
        return []
