from __future__ import annotations

import pytest

from audio_similarity.stage5b1b_identity import ABSENT, CONFLICT, MATCH
from audio_similarity.stage5b1c_normalization import (
    compare_tier2_versions,
    normalize_metadata_text,
    normalize_performer,
    parse_tier2_title,
    parse_tier2_versions,
    performer_credit_aliases,
    performer_equivalent,
)


def relationships(target: str, candidate: str) -> dict[str, str]:
    return {
        row["family"]: row["relationship"]
        for row in compare_tier2_versions(
            parse_tier2_versions(target), parse_tier2_versions(candidate)
        )
    }


@pytest.mark.parametrize(
    "value",
    ["Cupid (Twin Ver.)", "Cupid (TwinVer.)", "Cupid (Twin Version)"],
)
def test_twin_version_tokens_are_structurally_equivalent(value):
    parsed = parse_tier2_title(value, candidate=False)
    assert parsed.normalized_core_title == "cupid"
    assert relationships("Cupid - Twin Version", value)["twin_version"] == MATCH


def test_title_normalization_removes_only_source_and_presentation_noise():
    target = parse_tier2_title("ANTIFRAGILE", candidate=False)
    candidate = parse_tier2_title(
        "LE SSERAFIM 'ANTIFRAGILE' Lyrics "
        "(레세라핌 ANTIFRAGILE 가사) (Color Coded Lyrics)",
        expected_artists=("LE SSERAFIM",),
        candidate=True,
    )
    assert candidate.normalized_core_title == target.normalized_core_title
    assert candidate.title_performer_text == "LE SSERAFIM"
    assert "Lyrics" in candidate.source_descriptors


def test_title_normalization_preserves_material_recording_descriptors():
    plain = parse_tier2_title("Another Love", candidate=False)
    slowed = parse_tier2_title("Another Love (Slowed + Reverb) (Lyrics)", candidate=False)
    assert plain.normalized_core_title == slowed.normalized_core_title == "another love"
    assert {item.family for item in slowed.versions} == {"reverb", "slowed"}
    assert relationships("Another Love", "Another Love (Slowed + Reverb)") == {
        "reverb": CONFLICT,
        "slowed": CONFLICT,
    }


def test_unicode_quotes_punctuation_and_spacing_are_harmless():
    assert normalize_metadata_text("  ‘Beyoncé’—Song  ") == "beyonce song"


def test_performer_normalization_handles_leading_article_and_safe_formatting():
    assert normalize_performer("The Goo Goo Dolls") == "goo goo dolls"
    assert performer_equivalent("The Goo Goo Dolls", "Goo Goo Dolls")
    assert performer_equivalent("Earth, Wind & Fire", "Earth Wind and Fire")
    assert not performer_equivalent("Adele", "Adele Tribute Band")


@pytest.mark.parametrize("marker", ["feat.", "ft.", "featuring"])
def test_featured_performer_markers_preserve_explicit_credits(marker):
    aliases = performer_credit_aliases(f"DJ Snake {marker} Selena Gomez")
    assert aliases == ("dj snake", "selena gomez")
    parsed = parse_tier2_title(
        f"DJ Snake {marker} Selena Gomez - Taki Taki (Official Audio)",
        expected_artists=("DJ Snake", "Selena Gomez"),
        candidate=True,
    )
    assert parsed.normalized_core_title == "taki taki"


def test_live_venue_year_formatting_is_preserved_and_equivalent():
    target = "Free Fallin' - Live at the Nokia Theatre, Los Angeles, CA - December 2007"
    candidate = "Free Fallin' (Live at the Nokia Theatre, Los Angeles, CA - December 2007)"
    assert relationships(target, candidate)["live"] == MATCH
    parsed = parse_tier2_title(candidate, candidate=False)
    assert parsed.normalized_core_title == "free fallin"


def test_missing_remaster_stays_absent_and_wrong_remix_stays_conflict():
    assert relationships("Landslide - 2015 Remaster", "Landslide")["remaster"] == ABSENT
    assert relationships(
        "Bad Habits - FISHER Remix", "Bad Habits (Marc Benjamin Remix)"
    )["remix"] == CONFLICT
