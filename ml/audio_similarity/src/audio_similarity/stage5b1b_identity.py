"""Deterministic recording-identity parsing for Stage 5B.1B."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .stage5b1a_models import SpotifyTrack


MATCH = "MATCH"
ABSENT = "ABSENT"
CONFLICT = "CONFLICT"

_FEATURED = re.compile(r"\b(?:feat(?:uring)?|ft)\.?\s+[^()\[\]-]+", re.IGNORECASE)
_BRACKETED = re.compile(r"[\[(]([^\]\)]+)[\])]")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class VersionDescriptor:
    family: str
    qualifier: str | None
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {"family": self.family, "qualifier": self.qualifier, "raw": self.raw}


@dataclass(frozen=True)
class ParsedIdentity:
    raw_title: str
    core_title: str
    normalized_title: str
    primary_artist: str | None
    credited_artists: tuple[str, ...]
    normalized_artists: tuple[str, ...]
    duration_seconds: float | None
    versions: tuple[VersionDescriptor, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_title": self.raw_title,
            "core_title": self.core_title,
            "normalized_title": self.normalized_title,
            "primary_artist": self.primary_artist,
            "credited_artists": list(self.credited_artists),
            "normalized_artists": list(self.normalized_artists),
            "duration_seconds": self.duration_seconds,
            "version_descriptors": [item.to_dict() for item in self.versions],
            "version_families": sorted({item.family for item in self.versions}),
        }


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SPACE.sub(" ", re.sub(r"[^\w]+", " ", ascii_like.casefold())).strip()


def text_similarity(left: str | None, right: str | None) -> float:
    a, b = normalize_text(left), normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def _qualifier(segment: str, marker: str) -> str | None:
    value = re.sub(marker, " ", segment, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:version|edit|audio|official|the|from the vault)\b", " ", value, flags=re.I)
    value = _SPACE.sub(" ", value.strip(" -:()[]"))
    return value or None


def parse_versions(title: str) -> tuple[VersionDescriptor, ...]:
    """Extract version families without erasing their target-relative qualifiers."""
    segments = list(_BRACKETED.findall(title))
    segments.extend(part.strip() for part in re.split(r"\s[-–—]\s", title)[1:])
    segments.append(title)
    found: dict[str, VersionDescriptor] = {}

    def add(family: str, qualifier: str | None, raw: str) -> None:
        qualifier = _SPACE.sub(" ", qualifier).strip() if qualifier else None
        found.setdefault(family, VersionDescriptor(family, qualifier, raw.strip()))

    for segment in segments:
        lowered = segment.casefold()
        if "taylor's version" in lowered or "taylors version" in lowered:
            add("rerecording", "Taylor's Version", segment)
        duration_match = re.search(r"\b(\d+(?:\.\d+)?)\s*[- ]?minute\s+version\b", segment, re.I)
        if duration_match:
            add("duration_version", f"{duration_match.group(1)} minute", segment)
        remaster = re.search(
            r"\b(?:(\d{4})\s+)?remaster(?:ed)?(?:\s+(\d{4}))?\b", segment, re.I
        )
        if remaster:
            add("remaster", remaster.group(1) or remaster.group(2), segment)
        remix = re.search(r"\bremix(?:ed)?\b", segment, re.I)
        if remix:
            add("remix", _qualifier(segment, r"\bremix(?:ed)?\b"), segment)
        elif re.search(r"\bmix\b", segment, re.I):
            add("mix", _qualifier(segment, r"\bmix\b"), segment)
        live = re.search(r"\blive\b", segment, re.I)
        if live:
            qualifier = re.sub(r".*?\blive\b(?:\s+(?:at|in|from))?\s*", "", segment, flags=re.I)
            qualifier = _SPACE.sub(" ", qualifier.strip(" -:()[]")) or None
            add("live", qualifier, segment)
        for family, pattern, qualifier in (
            ("acoustic", r"\bacoustic\b", None),
            ("radio_edit", r"\bradio\s+edit\b", "radio edit"),
            ("extended", r"\bextended(?:\s+(?:mix|version))?\b", "extended"),
            ("instrumental", r"\binstrumental\b", None),
            ("karaoke", r"\bkaraoke\b", None),
            ("slowed", r"\bslowed\b", None),
            ("sped_up", r"\bsped\s*up\b", None),
            ("nightcore", r"\bnightcore\b", None),
            ("reverb", r"\breverb(?:ed)?\b", None),
        ):
            if re.search(pattern, segment, re.I):
                add(family, qualifier, segment)
        if re.search(r"\bclean(?:\s+version)?\b", segment, re.I):
            add("content_rating", "clean", segment)
        elif re.search(r"\bexplicit(?:\s+version)?\b", segment, re.I):
            add("content_rating", "explicit", segment)
        if re.fullmatch(r"\s*edit\s*", segment, re.I):
            add("edit", "edit", segment)
        named = re.fullmatch(
            r"\s*(angrier|chill|demo|b[- ]?side|from the vault|duet(?: version)?)\s*",
            segment,
            re.I,
        )
        if named:
            add("named_version", named.group(1), segment)
    return tuple(sorted(found.values(), key=lambda item: item.family))


def core_title(title: str, versions: tuple[VersionDescriptor, ...] | None = None) -> str:
    value = _FEATURED.sub("", title)
    descriptors = versions if versions is not None else parse_versions(title)
    for descriptor in descriptors:
        value = value.replace(descriptor.raw, " ")
    value = _BRACKETED.sub(" ", value)
    value = re.sub(r"\s[-–—]\s*$", "", value)
    return _SPACE.sub(" ", value.strip(" -–—:()[]")) or title.strip()


def parse_target(track: SpotifyTrack) -> ParsedIdentity:
    versions = parse_versions(track.title)
    return ParsedIdentity(
        raw_title=track.title,
        core_title=core_title(track.title, versions),
        normalized_title=normalize_text(core_title(track.title, versions)),
        primary_artist=track.artists[0],
        credited_artists=track.artists,
        normalized_artists=tuple(normalize_text(value) for value in track.artists),
        duration_seconds=track.duration_ms / 1000.0 if track.duration_ms is not None else None,
        versions=versions,
    )


def parse_candidate_identity(candidate: dict[str, Any]) -> ParsedIdentity:
    title = str(candidate.get("title") or "")
    performer = None
    recording_title = title
    if " - " in title:
        performer, recording_title = (part.strip() for part in title.split(" - ", 1))
        performer = performer or None
    versions = parse_versions(recording_title)
    return ParsedIdentity(
        raw_title=title,
        core_title=core_title(recording_title, versions),
        normalized_title=normalize_text(core_title(recording_title, versions)),
        primary_artist=performer,
        credited_artists=(performer,) if performer else (),
        normalized_artists=(normalize_text(performer),) if performer else (),
        duration_seconds=(
            float(candidate["duration_seconds"])
            if candidate.get("duration_seconds") is not None
            else None
        ),
        versions=versions,
    )


def compare_versions(
    target: tuple[VersionDescriptor, ...], candidate: tuple[VersionDescriptor, ...]
) -> list[dict[str, Any]]:
    target_by_family = {item.family: item for item in target}
    candidate_by_family = {item.family: item for item in candidate}
    rows = []
    for family in sorted(set(target_by_family) | set(candidate_by_family)):
        expected = target_by_family.get(family)
        observed = candidate_by_family.get(family)
        if expected and not observed:
            relationship = ABSENT
        elif observed and not expected:
            relationship = CONFLICT
        else:
            assert expected is not None and observed is not None
            left, right = normalize_text(expected.qualifier), normalize_text(observed.qualifier)
            if left and not right:
                relationship = ABSENT
            else:
                qualifiers_compatible = (
                    not left
                    or left == right
                    or f" {left} " in f" {right} "
                    or f" {right} " in f" {left} "
                )
                relationship = MATCH if qualifiers_compatible else CONFLICT
        rows.append(
            {
                "family": family,
                "relationship": relationship,
                "target_qualifier": expected.qualifier if expected else None,
                "candidate_qualifier": observed.qualifier if observed else None,
                "target_raw": expected.raw if expected else None,
                "candidate_raw": observed.raw if observed else None,
            }
        )
    return rows
