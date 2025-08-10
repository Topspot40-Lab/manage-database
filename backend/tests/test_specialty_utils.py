# tests/test_specialty_utils.py
from backend.utils.specialty_utils import (
    resolve_labels,
    should_update,
    parse_featured_keys,
)

def test_resolve_labels_category_from_json():
    data = {"genre": "latin favorites", "category": "before 1990s"}
    g, c = resolve_labels(data, "fallback-cat", "fallback-spec")
    assert g == "latin favorites"
    assert c == "before 1990s"

def test_resolve_labels_uses_decade_array_when_no_category():
    data = {"genre": "latin favorites", "decade": [{"decade_name": "before 1990s"}]}
    g, c = resolve_labels(data, "fallback-cat", "fallback-spec")
    assert g == "latin favorites"
    assert c == "before 1990s"

def test_resolve_labels_all_fallbacks():
    g, c = resolve_labels({}, "catX", "specY")
    assert g == "specY"
    assert c == "catX"

def test_should_update_logic():
    assert should_update(None, True) is True
    assert should_update("", True) is True
    assert should_update("   ", True) is True
    assert should_update("text", True) is False
    assert should_update("text", False) is True

def test_parse_featured_keys_variants():
    t1 = {"featured_artist": "Il Volo"}
    t2 = {"featured_artist_name": "Il Volo"}
    t3 = {"featured_artist_id": "SPOTIFY123"}
    assert parse_featured_keys(t1) == (None, "Il Volo")
    assert parse_featured_keys(t2) == (None, "Il Volo")
    assert parse_featured_keys(t3) == ("SPOTIFY123", None)
