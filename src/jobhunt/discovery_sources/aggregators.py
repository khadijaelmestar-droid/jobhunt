"""Parse community aggregators (HN Who's Hiring, YC directory) for companies."""

from __future__ import annotations

import logging
import re

import httpx

from jobhunt.discovery import DiscoveredCompany
from jobhunt.discovery_sources import CareerPageEntry
from jobhunt.discovery_sources.ats_detector import check_url_for_ats, detect_ats_batch

logger = logging.getLogger(__name__)


async def _fetch_hn_whos_hiring(client: httpx.AsyncClient) -> list[CareerPageEntry]:
    """Fetch the latest HN 'Who is Hiring?' thread and extract company career URLs."""
    resp = await client.get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "query": "Ask HN: Who is hiring?",
            "tags": "story",
            "hitsPerPage": 1,
        },
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return []

    story_id = hits[0].get("objectID", "")
    if not story_id:
        return []

    resp = await client.get(
        f"https://hn.algolia.com/api/v1/items/{story_id}",
    )
    resp.raise_for_status()
    story = resp.json()

    entries: list[CareerPageEntry] = []
    for child in story.get("children", []):
        text = child.get("text", "")
        if not text:
            continue

        first_line = text.split("<p>")[0] if "<p>" in text else text.split("\n")[0]
        company_name = re.sub(r"<[^>]+>", "", first_line).split("|")[0].strip()

        urls = re.findall(r'href="(https?://[^"]+)"', text)
        career_url = ""
        for url in urls:
            if any(kw in url.lower() for kw in ["career", "jobs", "hiring", "work", "apply", "openings",
                                                  "lever.co", "greenhouse.io", "ashbyhq.com", "workable.com",
                                                  "smartrecruiters.com", "teamtailor.com", "breezy.hr",
                                                  "bamboohr.com", "personio.de", "homerun.co"]):
                career_url = url
                break
        if not career_url and urls:
            career_url = urls[0]

        if company_name and career_url:
            entries.append(CareerPageEntry(company_name=company_name[:100], career_url=career_url))

    return entries


async def _fetch_yc_companies(client: httpx.AsyncClient) -> list[CareerPageEntry]:
    """Fetch Y Combinator company directory."""
    resp = await client.get(
        "https://api.ycombinator.com/v0.1/companies",
        params={"page": 1, "batch": ""},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    companies = data.get("companies", [])
    entries: list[CareerPageEntry] = []

    for co in companies:
        name = co.get("name", "")
        url = co.get("url", "")
        jobs_url = co.get("jobs_url", "")
        career_url = jobs_url or url
        if name and career_url and career_url.startswith("http"):
            entries.append(CareerPageEntry(company_name=name, career_url=career_url))

    return entries


async def discover_from_aggregators(
    max_concurrent: int = 30,
) -> list[DiscoveredCompany]:
    """Run all aggregator sources and detect ATS platforms."""
    all_entries: list[CareerPageEntry] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            hn_entries = await _fetch_hn_whos_hiring(client)
            logger.info("Found %d entries from HN Who's Hiring", len(hn_entries))
            all_entries.extend(hn_entries)
        except Exception as e:
            logger.warning("Failed to fetch HN Who's Hiring: %s", e)

        try:
            yc_entries = await _fetch_yc_companies(client)
            logger.info("Found %d entries from YC directory", len(yc_entries))
            all_entries.extend(yc_entries)
        except Exception as e:
            logger.warning("Failed to fetch YC directory: %s", e)

    if not all_entries:
        return []

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[CareerPageEntry] = []
    for entry in all_entries:
        if entry.career_url not in seen:
            seen.add(entry.career_url)
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
        "Aggregators: %d direct ATS URL matches, %d need HTML detection",
        len(direct_matches), len(need_detection),
    )

    # Phase 2: Detect ATS from HTML for remaining entries
    html_matches = await detect_ats_batch(need_detection, max_concurrent=max_concurrent)

    return direct_matches + html_matches
