"""Tests for cache management functionality."""

import json
import os
import tempfile
import pytest
from common import load_cache, save_cache
import common


@pytest.fixture
def temp_cache_file():
    """Create a temporary cache file for testing."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False
    ) as f:
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


class TestCacheManagement:
    """Test cache loading and saving."""

    def test_load_cache_empty(self, temp_cache_file, monkeypatch):
        """Test loading cache when file doesn't exist."""
        # Point to non-existent file
        monkeypatch.setattr(
            common, "CACHE_FILE", temp_cache_file + "_nonexistent"
        )

        result = load_cache()
        assert result == {}

    def test_save_and_load_cache(self, temp_cache_file, monkeypatch):
        """Test saving and loading cache."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        # Create test data
        test_data = {
            "premier_division": {
                "post_id": "abc123",
                "match_dates": ["2024-10-19", "2024-10-20"],
                "round": "Regular Season - 32",
            },
            "first_division": {
                "post_id": "def456",
                "match_dates": ["2024-10-21"],
                "round": "Regular Season - 28",
            },
        }

        # Save cache
        save_cache(test_data)
        assert os.path.exists(temp_cache_file)

        # Load cache
        loaded_data = load_cache()
        assert loaded_data == test_data
        assert loaded_data["premier_division"]["post_id"] == "abc123"
        assert loaded_data["first_division"]["post_id"] == "def456"

    def test_cache_structure(self, temp_cache_file, monkeypatch):
        """Test cache file has correct structure."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        test_data = {
            "premier_division": {
                "post_id": "xyz789",
                "match_dates": ["2024-10-19"],
                "round": "Regular Season - 30",
                "posted_at": "2024-10-17T06:00:00"
            }
        }

        save_cache(test_data)
        loaded = load_cache()

        assert "premier_division" in loaded
        assert "post_id" in loaded["premier_division"]
        assert "match_dates" in loaded["premier_division"]
        assert "round" in loaded["premier_division"]

    def test_cache_with_multiple_match_dates(
        self, temp_cache_file, monkeypatch
    ):
        """Test cache with multiple match dates."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        test_data = {
            "premier_division": {
                "post_id": "multi_abc",
                "match_dates": [
                    "2024-10-19",
                    "2024-10-20",
                    "2024-10-21",
                    "2024-10-22",
                    "2024-10-23"
                ],
                "round": "Regular Season - 32",
            }
        }

        save_cache(test_data)
        loaded = load_cache()

        loaded_matches = loaded["premier_division"]["match_dates"]
        assert len(loaded_matches) == 5
        assert "2024-10-21" in loaded_matches

    def test_overwrite_existing_cache_entry(
        self, temp_cache_file, monkeypatch
    ):
        """Test overwriting an existing cache entry."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        # Save first entry
        first_data = {
            "premier_division": {
                "post_id": "old_id",
                "match_dates": ["2024-10-19"],
                "round": "Regular Season - 1",
            }
        }
        save_cache(first_data)

        # Overwrite with new data
        second_data = {
            "premier_division": {
                "post_id": "new_id",
                "match_dates": ["2024-10-26"],
                "round": "Regular Season - 2",
            }
        }
        save_cache(second_data)

        loaded = load_cache()
        assert loaded["premier_division"]["post_id"] == "new_id"
        assert loaded["premier_division"]["round"] == "Regular Season - 2"

    def test_update_cache_adds_new_entry(self, temp_cache_file, monkeypatch):
        """Test adding a new entry to existing cache."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        # Save initial data
        initial_data = {
            "premier_division": {
                "post_id": "prem_id",
                "match_dates": ["2024-10-19"],
                "round": "Regular Season - 10",
            }
        }
        save_cache(initial_data)

        # Load and add new entry
        cache = load_cache()
        cache["first_division"] = {
            "post_id": "first_id",
            "match_dates": ["2024-10-20"],
            "round": "Regular Season - 8",
        }
        save_cache(cache)

        # Verify both entries exist
        final = load_cache()
        assert "premier_division" in final
        assert "first_division" in final
        assert final["premier_division"]["post_id"] == "prem_id"
        assert final["first_division"]["post_id"] == "first_id"

    def test_cache_json_formatting(self, temp_cache_file, monkeypatch):
        """Test cache file is valid JSON."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        test_data = {
            "premier_division": {
                "post_id": "json_test",
                "match_dates": ["2024-10-19"],
                "round": "Regular Season - 32"
            }
        }

        save_cache(test_data)

        # Read raw file and verify it's valid JSON
        with open(temp_cache_file, 'r', encoding='utf-8') as f:
            loaded_json = json.load(f)

        assert loaded_json == test_data


class TestCacheEdgeCases:
    """Test edge cases in cache handling."""

    def test_cache_with_empty_match_dates(self, temp_cache_file, monkeypatch):
        """Test cache with empty match dates list."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        test_data = {
            "premier_division": {
                "post_id": "empty_dates",
                "match_dates": [],
                "round": "Regular Season - 32",
            }
        }

        save_cache(test_data)
        loaded = load_cache()

        assert loaded["premier_division"]["match_dates"] == []

    def test_cache_with_iso_format_dates(self, temp_cache_file, monkeypatch):
        """Test cache preserves ISO date format."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        test_data = {
            "premier_division": {
                "post_id": "iso_dates",
                "match_dates": [
                    "2024-10-19",
                    "2024-10-20",
                ],
                "round": "Regular Season - 32",
            }
        }

        save_cache(test_data)
        loaded = load_cache()

        # Verify ISO format is preserved
        for date_str in loaded["premier_division"]["match_dates"]:
            assert len(date_str) == 10
            assert date_str.count('-') == 2

    def test_cache_with_special_characters_in_post_id(
        self,
        temp_cache_file,
        monkeypatch
    ):
        """Test cache handles special characters in post IDs."""
        monkeypatch.setattr(common, "CACHE_FILE", temp_cache_file)

        test_data = {
            "premier_division": {
                "post_id": "abc-123_xyz.post",
                "match_dates": ["2024-10-19"],
                "round": "Regular Season - 32",
            }
        }

        save_cache(test_data)
        loaded = load_cache()

        assert loaded["premier_division"]["post_id"] == "abc-123_xyz.post"
