"""Metadata-only chart-source feasibility pilot; never invokes media providers."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from .stage5b1b_artifacts import atomic_json

PILOT_ID = "CHART_ANCHORED_V2_FEASIBILITY"


class ChartFields(HTMLParser):
    """Read only named rank/title/artist fields, including nested inline text."""

    def __init__(self, provider):
        super().__init__(convert_charrefs=True)
        self.fields = {
            "aria": {"c-chart-item__rank": "rank", "c-chart-item__title": "title",
                     "c-chart-item__artist": "artist"},
            "billboard_japan": {"rank": "rank", "musuc_title": "title",
                                "artist_name": "artist"},
        }[provider]
        self.active = None
        self.depth = 0
        self.buffer = []
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag in {"img", "br", "input", "meta", "link", "hr", "source", "wbr"}:
            return
        if self.active:
            self.depth += 1
            return
        classes = dict(attrs).get("class", "").split()
        for name in classes:
            if name in self.fields:
                self.active = self.fields[name]
                self.depth = 1
                self.buffer = []
                break

    def handle_endtag(self, tag):
        if self.active:
            self.depth -= 1
            if self.depth == 0:
                self.values.append((self.active, " ".join("".join(self.buffer).split())))
                self.active = None

    def handle_data(self, data):
        if self.active:
            self.buffer.append(data)


def parse_chart(html, provider, expected_count=100):
    parser = ChartFields(provider)
    parser.feed(html)
    rows = []
    current = {}
    for field, value in parser.values:
        if field == "rank":
            if current:
                rows.append(current)
            current = {"rank": int(value)}
        elif current:
            if field in current:
                raise ValueError("duplicate field within chart row")
            current[field] = value
    if current:
        rows.append(current)
    if [r["rank"] for r in rows] != list(range(1, expected_count + 1)):
        raise ValueError(f"expected contiguous 1–{expected_count} ranks; got {len(rows)} rows")
    if any(not r.get("title") or not r.get("artist") for r in rows):
        raise ValueError("missing title/artist")
    return rows


def pilot_sources():
    sources = []
    for year in (2006, 2015, 2025):
        sources.append({"provider": "aria", "territory": "AU", "chart_year": year,
                        "url": f"https://www.aria.com.au/charts/{year}/singles-chart"})
    for territory, chart in (("JP", "hot100_year"), ("US", "uhot100_year")):
        for year in (2015, 2025):
            sources.append({"provider": "billboard_japan", "territory": territory,
                            "chart_year": year,
                            "url": f"https://www.billboard-japan.com/charts/detail?a={chart}&year={year}"})
    return sources


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_period(html, provider, year):
    pattern = (r'class="c-chart-years[^\"]*">\s*(\d{4})\s*</button>'
               if provider == 'aria' else r'<option value="(\d{4})" selected="selected">')
    displayed = re.findall(pattern, html)
    if displayed != [str(year)]:
        raise ValueError(f"displayed chart year {displayed} differs from requested {year}")


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"refusing to replace frozen artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        atomic_json(path, value)


def run(root, sources=None, output=None):
    report = root / "reports/stage5d_chart_catalog_pilot"
    runtime = root / ".research_audio/chart_catalog_pilot"
    runtime.mkdir(parents=True, exist_ok=True)
    stop = runtime / "provider_stop.json"
    results, entries = [], []
    for source in sources if sources is not None else pilot_sources():
        key = f"{source['territory']}_{source['chart_year']}"
        path = runtime / f"{key}.json"
        if path.exists():
            snapshot = json.loads(path.read_text())
            if snapshot["url"] != source["url"]:
                raise ValueError("snapshot source mismatch")
        else:
            if stop.exists():
                raise RuntimeError("chart provider stop is active; inspect provider_stop.json before resuming network work")
            time.sleep(2)
            try:
                req = Request(source["url"], headers={"User-Agent": "SpotifySorter-ChartMetadataPilot/1.0"})
                with urlopen(req, timeout=30) as response:
                    html = response.read().decode("utf-8")
                    final_url = response.url
                snapshot = {"url": source["url"], "final_url": final_url, "html": html,
                            "retrieved_at": datetime.now(timezone.utc).isoformat()}
                write_json(path, snapshot)
            except HTTPError as exc:
                if exc.code in {403, 429}:
                    write_json(stop, {"url": source["url"], "status": exc.code,
                                      "retry_after": exc.headers.get("Retry-After"),
                                      "automatic_resume": False})
                    raise RuntimeError(f"chart collection paused: HTTP {exc.code}") from None
                results.append(source | {"status": "FETCH_FAILED", "error": str(exc)})
                continue
            except Exception as exc:
                results.append(source | {"status": "FETCH_FAILED", "error": str(exc)})
                continue
        try:
            # Reject silently redirected or year-fallback pages before parsing.
            if snapshot["final_url"] != source["url"]:
                raise ValueError("unexpected redirect; manual source validation required")
            html = snapshot["html"]
            validate_period(html, source['provider'], source['chart_year'])
            rows = parse_chart(html, source["provider"])
            sha = digest(html.encode())
            for row in rows:
                identity = f"{key}:{row['rank']}"
                entries.append(row | source | {"entry_id": identity, "period_type": "YEAR_END",
                    "source_sha256": sha, "recording_release_year": None,
                    "spotify_status": "UNRESOLVED", "acquisition_eligible": False})
            results.append(source | {"status": "PARSED", "count": len(rows),
                "source_sha256": sha, "retrieved_at": snapshot["retrieved_at"]})
        except Exception as exc:
            results.append(source | {"status": "VALIDATION_FAILED", "error": str(exc)})
    payload = {"pilot_id": PILOT_ID, "sources": results, "entries": entries,
               "scope": "source feasibility only; chart entries are not recording identities",
               "youtube_calls": 0, "media_downloads": 0, "2026_status": "YEAR_INCOMPLETE"}
    write_json(output or report / "chart_pilot_verified.json", payload)
    print(json.dumps({"entries": len(entries), "sources": results}, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    run(parser.parse_args().root)
