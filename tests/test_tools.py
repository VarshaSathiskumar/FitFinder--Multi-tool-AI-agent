"""
Tests for all three FitFindr tools.

One test per failure mode, plus the provided baseline tests for search_listings.
suggest_outfit and create_fit_card hit the real Groq API — they require GROQ_API_KEY
to be set in .env. Tests are grouped by tool.
"""

import pytest
from unittest.mock import patch, MagicMock

from tools import search_listings, suggest_outfit, create_fit_card


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_item(**overrides):
    base = {
        "id": "lst_test",
        "title": "Vintage Graphic Tee",
        "description": "A cool graphic tee with a band print.",
        "category": "tops",
        "style_tags": ["vintage", "graphic", "streetwear"],
        "size": "M",
        "condition": "good",
        "price": 25.0,
        "colors": ["black", "white"],
        "brand": None,
        "platform": "depop",
    }
    base.update(overrides)
    return base


def _mock_groq(content="Mocked LLM response"):
    """Return a patch target and mock that makes Groq return `content`."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return mock_client


# ── Tool 1: search_listings ────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Impossibly specific constraints — should return [] not raise
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    # Dataset has sizes like "S/M" and "M" — "m" should match both
    results = search_listings("top", size="m", max_price=None)
    assert len(results) > 0
    assert all("m" in item["size"].lower() for item in results)


def test_search_no_zero_score_items():
    # A highly specific keyword that won't match anything should yield []
    results = search_listings("zzznomatch", size=None, max_price=None)
    assert results == []


def test_search_results_sorted_by_relevance():
    # Items with more keyword hits should rank above items with fewer
    results = search_listings("vintage denim streetwear", size=None, max_price=None)
    assert len(results) >= 2
    # The top result should contain at least one of the keywords
    top = results[0]
    text = (top["title"] + top["description"] + " ".join(top["style_tags"])).lower()
    assert any(kw in text for kw in ["vintage", "denim", "streetwear"])


def test_search_both_filters_applied():
    # Price AND size filters must both apply simultaneously
    results = search_listings("top", size="M", max_price=30)
    assert all(item["price"] <= 30 for item in results)
    assert all("m" in item["size"].lower() for item in results)


def test_search_max_price_inclusive():
    # An item priced exactly at max_price should be included
    results = search_listings("vintage", size=None, max_price=38.0)
    prices = [item["price"] for item in results]
    assert 38.0 in prices  # Levi's 501 is $38 and is vintage-tagged


def test_search_returns_full_listing_dicts():
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 0
    required_keys = {"id", "title", "description", "category", "style_tags",
                     "size", "condition", "price", "colors", "brand", "platform"}
    assert required_keys.issubset(results[0].keys())


# ── Tool 2: suggest_outfit ─────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe(monkeypatch):
    wardrobe = {
        "items": [
            {"name": "Black jeans", "category": "bottoms", "colors": ["black"],
             "style_tags": ["classic"], "notes": ""},
            {"name": "White sneakers", "category": "shoes", "colors": ["white"],
             "style_tags": ["casual"], "notes": ""},
        ]
    }
    mock_client = _mock_groq("Outfit 1: pair the tee with black jeans and white sneakers.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    result = suggest_outfit(_fake_item(), wardrobe)

    assert isinstance(result, str)
    assert len(result) > 0
    mock_client.chat.completions.create.assert_called_once()


def test_suggest_outfit_empty_wardrobe_does_not_crash(monkeypatch):
    # Empty wardrobe must not raise — should return general styling advice
    mock_client = _mock_groq("General styling tips for this item.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    result = suggest_outfit(_fake_item(), {"items": []})

    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_missing_items_key_does_not_crash(monkeypatch):
    # Wardrobe dict missing 'items' key entirely — .get() should handle it
    mock_client = _mock_groq("General tips.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    result = suggest_outfit(_fake_item(), {})

    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_includes_wardrobe_items_in_prompt(monkeypatch):
    # When wardrobe is non-empty, the prompt sent to the LLM should reference it
    wardrobe = {"items": [
        {"name": "Cargo pants", "category": "bottoms", "colors": ["olive"],
         "style_tags": ["utilitarian"], "notes": ""}
    ]}
    mock_client = _mock_groq("Wear with cargo pants.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    suggest_outfit(_fake_item(), wardrobe)

    call_args = mock_client.chat.completions.create.call_args
    prompt_text = call_args[1]["messages"][0]["content"]
    assert "Cargo pants" in prompt_text


def test_suggest_outfit_empty_wardrobe_skips_wardrobe_in_prompt(monkeypatch):
    # Empty wardrobe path should NOT reference wardrobe items in the prompt
    mock_client = _mock_groq("General tips.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    suggest_outfit(_fake_item(), {"items": []})

    call_args = mock_client.chat.completions.create.call_args
    prompt_text = call_args[1]["messages"][0]["content"]
    assert "wardrobe contains" not in prompt_text.lower()


# ── Tool 3: create_fit_card ────────────────────────────────────────────────────

def test_create_fit_card_returns_string(monkeypatch):
    mock_client = _mock_groq("Found this gem on Depop for $25!")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    result = create_fit_card("Tee + black jeans + white sneakers", _fake_item())

    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_empty_outfit_returns_error_string():
    # Empty outfit must return an error string, not raise an exception
    result = create_fit_card("", _fake_item())
    assert isinstance(result, str)
    assert len(result) > 0
    assert "error" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    # Whitespace-only outfit should also be caught
    result = create_fit_card("   ", _fake_item())
    assert isinstance(result, str)
    assert "error" in result.lower()


def test_create_fit_card_no_exception_on_empty_outfit():
    # Explicitly verify no exception is raised
    try:
        create_fit_card("", _fake_item())
    except Exception as exc:
        pytest.fail(f"create_fit_card raised an exception on empty outfit: {exc}")


def test_create_fit_card_uses_high_temperature(monkeypatch):
    # Caption creativity requires temperature > 1.0
    mock_client = _mock_groq("A fun caption.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    create_fit_card("Tee + jeans", _fake_item())

    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert "temperature" in call_kwargs
    assert call_kwargs["temperature"] >= 1.0


def test_create_fit_card_prompt_includes_item_details(monkeypatch):
    # The LLM prompt must include item name, price, and platform
    mock_client = _mock_groq("Caption here.")
    monkeypatch.setattr("tools._get_groq_client", lambda: mock_client)

    item = _fake_item(title="Rare Vintage Tee", price=42.0, platform="poshmark")
    create_fit_card("Tee + cargos", item)

    prompt_text = mock_client.chat.completions.create.call_args[1]["messages"][0]["content"]
    assert "Rare Vintage Tee" in prompt_text
    assert "42" in prompt_text
    assert "poshmark" in prompt_text.lower()
