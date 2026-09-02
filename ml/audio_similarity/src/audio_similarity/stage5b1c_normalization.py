"""Tier-2 structural metadata normalization for candidate resolution.

This module intentionally does not replace the frozen Stage 5B.1B parser.  It
provides a richer compatibility path used only after POLICY_BALANCED_V1 returns
MATCH_UNCERTAIN.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from .stage5b1b_identity import ABSENT, CONFLICT, MATCH, VersionDescriptor, parse_versions


TIER2_NORMALIZATION_VERSION = "stage5b1c-tier2-normalization-v1"

_SPACE = re.compile(r"\s+")
_SOURCE_PHRASES = re.compile(
    r"\b(?:official\s+(?:music\s+)?video|official\s+audio|official\s+lyric\s+video|"
    r"lyric\s+video|lyrics?|letra(?:\s+video\s+oficial)?|audio|m\s*/?\s*v|visualizer)\b",
    re.I,
)
_TWIN_VERSION = re.compile(r"\btwin\s*ver(?:sion)?\.?\b", re.I)
_LIVE_VERSION = re.compile(
    r"\blive(?:\s+(?:at|in|from))?\s+([^\)\]]+)", re.I
)
_NON_LATIN = re.compile(r"[^\x00-\x7f]")
_BRACKETED = re.compile(r"([\[(])([^\])]+)([\])])")
_FEATURE_CREDIT = re.compile(r"\b(?:feat(?:uring)?|ft)\.?\s+", re.I)


@dataclass(frozen=True)
class Tier2TitleIdentity:
    raw_title: str
    recording_text: str
    core_title: str
    normalized_core_title: str
    source_descriptors: tuple[str, ...]
    versions: tuple[VersionDescriptor, ...]
    title_performer_text: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_title": self.raw_title,
            "recording_text": self.recording_text,
            "core_title": self.core_title,
            "normalized_core_title": self.normalized_core_title,
            "source_descriptors": list(self.source_descriptors),
            "version_descriptors": [item.to_dict() for item in self.versions],
            "title_performer_text": self.title_performer_text,
        }


def normalize_metadata_text(value: str | None) -> str:
    """Normalize harmless Unicode/punctuation differences without fuzzy matching."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    folded = without_marks.casefold().replace("&", " and ")
    return _SPACE.sub(" ", re.sub(r"[^\w]+", " ", folded)).strip()


def normalize_performer(value: str | None) -> str:
    """Return a strict performer alias, ignoring only presentation-level syntax."""
    normalized = normalize_metadata_text(value)
    normalized = re.sub(r"^(?:the)\s+", "", normalized)
    normalized = re.sub(r"\s+(?:official|vevo|topic)$", "", normalized)
    return _SPACE.sub(" ", normalized).strip()


def performer_equivalent(left: str | None, right: str | None) -> bool:
    a, b = normalize_performer(left), normalize_performer(right)
    return bool(a and b and a == b)


def performer_credit_aliases(value: str | None) -> tuple[str, ...]:
    """Normalize primary/featured credits without fuzzy artist matching."""
    if not value:
        return ()
    return tuple(
        alias
        for part in _FEATURE_CREDIT.split(value)
        if (alias := normalize_performer(part))
    )


def _top_level_separator(value: str) -> tuple[str, str] | None:
    depth = 0
    index = 0
    while index < len(value):
        char = value[index]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if depth == 0:
            for separator in (" - ", " – ", " — "):
                if value.startswith(separator, index):
                    return value[:index].strip(), value[index + len(separator):].strip()
        index += 1
    return None


def title_performer_prefix(value: str) -> str | None:
    """Return only a top-level ``performer - title`` prefix when present."""
    separated = _top_level_separator(value)
    return separated[0] if separated else None


def split_title_performer(value: str) -> tuple[str, str] | None:
    """Expose the conservative top-level split for conflict inspection."""
    return _top_level_separator(value)


def _artist_pattern(artist: str) -> re.Pattern[str]:
    words = re.findall(r"\w+", unicodedata.normalize("NFKC", artist), re.UNICODE)
    if words and words[0].casefold() == "the":
        words = words[1:]
    body = r"[\W_]+".join(re.escape(word) for word in words)
    return re.compile(rf"^\s*(?:the[\W_]+)?{body}(?=\W|$)", re.I) if body else re.compile(r"$^")


def _remove_matching_artist_prefix(
    title: str, expected_artists: Iterable[str]
) -> tuple[str, str | None]:
    separated = _top_level_separator(title)
    if separated and any(
        normalize_performer(artist) in performer_credit_aliases(separated[0])
        for artist in expected_artists
    ):
        return separated[1], separated[0]
    for artist in expected_artists:
        match = _artist_pattern(artist).match(title)
        if not match:
            continue
        remainder = title[match.end():].lstrip()
        while remainder.startswith("("):
            end = remainder.find(")")
            if end < 0 or not _NON_LATIN.search(remainder[1:end]):
                break
            remainder = remainder[end + 1:].lstrip()
        remainder = remainder.lstrip(" -–—:|'‘’\"")
        if remainder:
            return remainder, title[:match.end()].strip()
    return title, None


def _source_descriptors(title: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0).strip() for match in _SOURCE_PHRASES.finditer(title)))


def _version_qualifier(value: str | None) -> str:
    normalized = normalize_metadata_text(value)
    normalized = re.sub(r"^(?:the)\s+", "", normalized)
    substitutions = {
        "version": "",
        "ver": "",
        "california": "ca",
    }
    tokens = [substitutions.get(token, token) for token in normalized.split()]
    return " ".join(token for token in tokens if token)


def parse_tier2_versions(title: str) -> tuple[VersionDescriptor, ...]:
    """Extend the frozen parser with deterministic formatting equivalences."""
    found = {item.family: item for item in parse_versions(title)}
    twin = _TWIN_VERSION.search(title)
    if twin:
        found["twin_version"] = VersionDescriptor("twin_version", "twin", twin.group(0))
    live = _LIVE_VERSION.search(title)
    if live:
        raw = live.group(0).strip()
        qualifier = live.group(1).strip(" -–—:()[]") or None
        found["live"] = VersionDescriptor("live", qualifier, raw)
    return tuple(sorted(found.values(), key=lambda item: item.family))


def compare_tier2_versions(
    target: tuple[VersionDescriptor, ...],
    candidate: tuple[VersionDescriptor, ...],
    provenance: tuple[VersionDescriptor, ...] = (),
) -> list[dict[str, Any]]:
    """Compare versions while allowing raw-backed provenance to fill title omissions."""
    expected = {item.family: item for item in target}
    observed = {item.family: item for item in candidate}
    provenance_by_family = {item.family: item for item in provenance}
    rows: list[dict[str, Any]] = []
    for family in sorted(set(expected) | set(observed)):
        wanted = expected.get(family)
        seen = observed.get(family)
        source = "candidate_title"
        if wanted and not seen and family in provenance_by_family:
            seen = provenance_by_family[family]
            source = "release_provenance"
        if wanted and not seen:
            relationship = ABSENT
        elif seen and not wanted:
            relationship = CONFLICT
        else:
            assert wanted is not None and seen is not None
            left = _version_qualifier(wanted.qualifier)
            right = _version_qualifier(seen.qualifier)
            if left and not right:
                relationship = ABSENT
            else:
                relationship = MATCH if (
                    not left
                    or left == right
                    or f" {left} " in f" {right} "
                    or f" {right} " in f" {left} "
                ) else CONFLICT
        rows.append(
            {
                "family": family,
                "relationship": relationship,
                "target_qualifier": wanted.qualifier if wanted else None,
                "candidate_qualifier": seen.qualifier if seen else None,
                "target_raw": wanted.raw if wanted else None,
                "candidate_raw": seen.raw if seen else None,
                "candidate_evidence_source": source if seen else None,
            }
        )
    return rows


def _removable_bracket(content: str) -> bool:
    return bool(
        _SOURCE_PHRASES.search(content)
        or _NON_LATIN.search(content)
        or re.search(r"\b(?:color\s+coded|4k|\d+fps|hq)\b", content, re.I)
    )


def parse_tier2_title(
    title: str,
    *,
    expected_artists: Iterable[str] = (),
    candidate: bool,
) -> Tier2TitleIdentity:
    recording_text, performer = (
        _remove_matching_artist_prefix(title, expected_artists) if candidate else (title, None)
    )
    versions = parse_tier2_versions(recording_text)
    value = recording_text
    for descriptor in versions:
        value = value.replace(descriptor.raw, " ")
    value = _SOURCE_PHRASES.sub(" ", value)

    def bracket_replacement(match: re.Match[str]) -> str:
        content = match.group(2)
        return " " if _removable_bracket(content) else f" {content} "

    value = _BRACKETED.sub(bracket_replacement, value)
    value = re.sub(r"^\s*\[[^\]]*(?:4k|fps|hq)[^\]]*\]\s*", "", value, flags=re.I)
    value = _SPACE.sub(" ", value.strip(" -–—:|()[]'\"‘’"))
    return Tier2TitleIdentity(
        raw_title=title,
        recording_text=recording_text,
        core_title=value or recording_text.strip(),
        normalized_core_title=normalize_metadata_text(value or recording_text),
        source_descriptors=_source_descriptors(recording_text),
        versions=versions,
        title_performer_text=performer,
    )
