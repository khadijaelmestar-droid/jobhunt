"""Parse GitHub awesome-lists to find companies and their career pages."""

from __future__ import annotations

import logging
import re

import httpx

from jobhunt.discovery import DiscoveredCompany
from jobhunt.discovery_sources import CareerPageEntry
from jobhunt.discovery_sources.ats_detector import check_url_for_ats, detect_ats_batch

logger = logging.getLogger(__name__)

# GitHub repos with company lists (raw markdown URLs)
_GITHUB_SOURCES = [
    {
        "name": "remoteintech/remote-jobs",
        "url": "https://raw.githubusercontent.com/remoteintech/remote-jobs/main/README.md",
        "parser": "markdown_table",
    },
    {
        "name": "poteto/hiring-without-whiteboards",
        "url": "https://raw.githubusercontent.com/poteto/hiring-without-whiteboards/master/README.md",
        "parser": "markdown_links",
    },
]


def _parse_markdown_table(text: str) -> list[CareerPageEntry]:
    """Extract company names and URLs from markdown table rows."""
    entries: list[CareerPageEntry] = []
    for match in re.finditer(r"\|\s*\[([^\]]+)\]\(([^)]+)\)", text):
        name, url = match.group(1).strip(), match.group(2).strip()
        if url.startswith("http") and "github.com" not in url:
            entries.append(CareerPageEntry(company_name=name, career_url=url))
    return entries


def _parse_markdown_links(text: str) -> list[CareerPageEntry]:
    """Extract company names and URLs from markdown links in lists."""
    entries: list[CareerPageEntry] = []
    for match in re.finditer(r"[-*]\s+\[([^\]]+)\]\(([^)]+)\)", text):
        name, url = match.group(1).strip(), match.group(2).strip()
        if url.startswith("http") and "github.com" not in url:
            entries.append(CareerPageEntry(company_name=name, career_url=url))
    return entries


_PARSERS = {
    "markdown_table": _parse_markdown_table,
    "markdown_links": _parse_markdown_links,
}


async def discover_from_github_lists(
    max_concurrent: int = 30,
) -> list[DiscoveredCompany]:
    """Fetch GitHub awesome-lists, extract career pages, detect ATS platforms."""
    all_entries: list[CareerPageEntry] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        for source in _GITHUB_SOURCES:
            try:
                resp = await client.get(source["url"])
                resp.raise_for_status()
                parser = _PARSERS.get(source["parser"], _parse_markdown_links)
                entries = parser(resp.text)
                logger.info("Parsed %d entries from %s", len(entries), source["name"])
                all_entries.extend(entries)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", source["name"], e)

    if not all_entries:
        return []

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique: list[CareerPageEntry] = []
    for entry in all_entries:
        if entry.career_url not in seen_urls:
            seen_urls.add(entry.career_url)
            unique.append(entry)

    # Phase 1: Check URLs directly for ATS patterns (no HTTP needed)
    direct_matches: list[DiscoveredCompany] = []
    need_detection: list[CareerPageEntry] = []

    for entry in unique:
        match = check_url_for_ats(entry.career_url, entry.company_name)
        if match:
            direct_matches.append(match)
        else:
            need_detection.append(entry)

    logger.info(
        "GitHub lists: %d direct ATS URL matches, %d need HTML detection",
        len(direct_matches), len(need_detection),
    )

    # Phase 2: Detect ATS from HTML for remaining entries
    html_matches = await detect_ats_batch(need_detection, max_concurrent=max_concurrent)

    return direct_matches + html_matches
