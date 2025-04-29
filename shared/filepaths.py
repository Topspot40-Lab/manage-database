import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "json_files", "genredecade"))

def get_json_path(decade: str, genre: str, language: str = "en") -> str:
    decade_dir = os.path.join(BASE_DIR, decade)
    os.makedirs(decade_dir, exist_ok=True)
    filename = f"{decade}_{genre}_{language}.json".replace(" ", "_").lower()
    return os.path.join(decade_dir, filename)
