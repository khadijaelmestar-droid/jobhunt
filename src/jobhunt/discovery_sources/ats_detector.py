"""Detect which ATS a company uses by inspecting their career page HTML."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from jobhunt.discovery import DiscoveredCompany
from jobhunt.discovery_sources import CareerPageEntry
from jobhunt.models import ATSPlatform

logger = logging.getLogger(__name__)

# ATS detection patterns: (regex_pattern, platform, slug_extraction_regex)
_ATS_SIGNATURES: list[tuple[str, ATSPlatform, str]] = [
    (r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)", ATSPlatform.GREENHOUSE, r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)"),
    (r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", ATSPlatform.LEVER, r"jobs\.lever\.co/([a-zA-Z0-9_-]+)"),
    (r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)", ATSPlatform.ASHBY, r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)"),
    (r"apply\.workable\.com/([a-zA-Z0-9_-]+)", ATSPlatform.WORKABLE, r"apply\.workable\.com/([a-zA-Z0-9_-]+)"),
    (r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)", ATSPlatform.SMARTRECRUITERS, r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)"),
    (r"([a-zA-Z0-9_-]+)\.teamtailor\.com", ATSPlatform.TEAMTAILOR, r"([a-zA-Z0-9_-]+)\.teamtailor\.com"),
    (r"([a-zA-Z0-9_-]+)\.bamboohr\.com/careers", ATSPlatform.BAMBOOHR, r"([a-zA-Z0-9_-]+)\.bamboohr\.com"),
    (r"([a-zA-Z0-9_-]+)\.jobs\.personio\.de", ATSPlatform.PERSONIO, r"([a-zA-Z0-9_-]+)\.jobs\.personio\.de"),
    (r"([a-zA-Z0-9_-]+)\.breezy\.hr", ATSPlatform.BREEZY, r"([a-zA-Z0-9_-]+)\.breezy\.hr"),
    (r"([a-zA-Z0-9_-]+)\.homerun\.co", ATSPlatform.HOMERUN, r"([a-zA-Z0-9_-]+)\.homerun\.co"),
    (r"([a-zA-Z0-9_-]+)\.recruitee\.com", ATSPlatform.RECRUITEE, r"([a-zA-Z0-9_-]+)\.recruitee\.com"),
    (r"myworkdaysite\.com|myworkday\.com", ATSPlatform.WORKDAY, r"([a-zA-Z0-9_-]+)\.(?:wd\d+\.)?myworkday"),
    (r"icims\.com", ATSPlatform.ICIMS, r"careers[.-]([a-zA-Z0-9_-]+)\.icims\.com"),
]


async def detect_ats(
    client: httpx.AsyncClient,
    entry: CareerPageEntry,
) -> DiscoveredCompany | None:
    """Fetch a career page and detect which ATS it uses."""
    try:
        resp = await client.get(entry.career_url, timeout=15.0, follow_redirects=True)
        html = resp.text
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", entry.career_url, e)
        return None

    for pattern, platform, slug_pattern in _ATS_SIGNATURES:
        if re.search(pattern, html):
            slug_match = re.search(slug_pattern, html)
            if slug_match:
                slug = slug_match.group(1).lower()
                return DiscoveredCompany(
                    slug=slug,
                    name=entry.company_name,
                    platform=platform,
                )
    return None


async def detect_ats_batch(
    entries: list[CareerPageEntry],
    max_concurrent: int = 30,
) -> list[DiscoveredCompany]:
    """Detect ATS for a batch of career page entries."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[DiscoveredCompany] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        async def detect_one(entry: CareerPageEntry) -> None:
            async with semaphore:
                result = await detect_ats(client, entry)
                if result:
                    results.append(result)

        await asyncio.gather(*[detect_one(e) for e in entries])

    return results
