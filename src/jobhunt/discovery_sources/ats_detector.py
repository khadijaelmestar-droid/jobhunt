"""Detect which ATS a company uses by inspecting URLs and career page HTML."""

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

# Career page subpaths to try if homepage doesn't have ATS embed
_CAREER_PATHS = ["/careers", "/jobs", "/open-positions", "/careers/jobs"]


def check_url_for_ats(url: str, company_name: str = "") -> DiscoveredCompany | None:
    """Check if a URL itself is a known ATS URL (no HTTP request needed)."""
    for pattern, platform, slug_pattern in _ATS_SIGNATURES:
        if re.search(pattern, url):
            slug_match = re.search(slug_pattern, url)
            if slug_match:
                slug = slug_match.group(1).lower()
                return DiscoveredCompany(
                    slug=slug,
                    name=company_name or slug,
                    platform=platform,
                )
    return None


def _scan_html_for_ats(html: str, company_name: str) -> DiscoveredCompany | None:
    """Scan HTML content for ATS signatures."""
    for pattern, platform, slug_pattern in _ATS_SIGNATURES:
        if re.search(pattern, html):
            slug_match = re.search(slug_pattern, html)
            if slug_match:
                slug = slug_match.group(1).lower()
                return DiscoveredCompany(
                    slug=slug,
                    name=company_name,
                    platform=platform,
                )
    return None


async def detect_ats(
    client: httpx.AsyncClient,
    entry: CareerPageEntry,
) -> DiscoveredCompany | None:
    """Detect ATS from a career page entry. Tries: URL match → HTML scan → career subpages."""
    # Step 1: Check URL itself for ATS patterns (free, no HTTP)
    url_match = check_url_for_ats(entry.career_url, entry.company_name)
    if url_match:
        return url_match

    # Step 2: Fetch the URL and scan HTML
    try:
        resp = await client.get(entry.career_url, timeout=15.0, follow_redirects=True)
        html = resp.text

        # Check if we were redirected to an ATS URL
        redirect_match = check_url_for_ats(str(resp.url), entry.company_name)
        if redirect_match:
            return redirect_match

        result = _scan_html_for_ats(html, entry.company_name)
        if result:
            return result
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", entry.career_url, e)
        return None

    # Step 3: Try common career subpages
    base_url = entry.career_url.rstrip("/")
    for path in _CAREER_PATHS:
        try:
            resp = await client.get(f"{base_url}{path}", timeout=10.0, follow_redirects=True)
            if resp.status_code >= 400:
                continue

            # Check redirect URL
            redirect_match = check_url_for_ats(str(resp.url), entry.company_name)
            if redirect_match:
                return redirect_match

            result = _scan_html_for_ats(resp.text, entry.company_name)
            if result:
                return result
        except Exception:
            continue

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
