from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]  # project root (above /backend)
TEST_JSON_DIR = BASE_DIR / "backend" / "tests" / "json_tests" / "xai"
SCHEMA_PATH   = BASE_DIR / "backend" / "schemas" / "track_schema.json"
