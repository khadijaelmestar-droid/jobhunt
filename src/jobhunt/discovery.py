from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from jobhunt.models import ATSPlatform, Company
from jobhunt.providers import PROVIDERS

logger = logging.getLogger(__name__)

VALIDATION_URLS: dict[ATSPlatform, str] = {
    ATSPlatform.GREENHOUSE: "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    ATSPlatform.LEVER: "https://api.lever.co/v0/postings/{slug}",
    ATSPlatform.ASHBY: "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    ATSPlatform.RECRUITEE: "https://api.recruitee.com/c/{slug}/offers",
    ATSPlatform.WORKABLE: "https://apply.workable.com/api/v1/widget/{slug}",
    ATSPlatform.SMARTRECRUITERS: "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
    ATSPlatform.JAZZHR: "https://app.jazz.co/api/{slug}/jobs",
    ATSPlatform.BREEZY: "https://{slug}.breezy.hr/json",
    ATSPlatform.TEAMTAILOR: "https://{slug}.teamtailor.com/jobs",
    ATSPlatform.HOMERUN: "https://{slug}.homerun.co",
    ATSPlatform.BAMBOOHR: "https://{slug}.bamboohr.com/careers/list",
    ATSPlatform.PERSONIO: "https://{slug}.jobs.personio.de/search",
}

# URL patterns to extract (platform, slug) from job URLs
_URL_PATTERNS: list[tuple[str, ATSPlatform]] = [
    (r"greenhouse\.io/([a-zA-Z0-9_-]+)", ATSPlatform.GREENHOUSE),
    (r"lever\.co/([a-zA-Z0-9_-]+)", ATSPlatform.LEVER),
    (r"ashbyhq\.com/([a-zA-Z0-9_.-]+)", ATSPlatform.ASHBY),
    (r"recruitee\.com/c/([a-zA-Z0-9_-]+)", ATSPlatform.RECRUITEE),
    (r"apply\.workable\.com/([a-zA-Z0-9_-]+)", ATSPlatform.WORKABLE),
    (r"smartrecruiters\.com/([a-zA-Z0-9_-]+)", ATSPlatform.SMARTRECRUITERS),
    (r"jazz\.co/([a-zA-Z0-9_-]+)", ATSPlatform.JAZZHR),
    (r"([a-zA-Z0-9_-]+)\.breezy\.hr", ATSPlatform.BREEZY),
    (r"([a-zA-Z0-9_-]+)\.teamtailor\.com", ATSPlatform.TEAMTAILOR),
    (r"([a-zA-Z0-9_-]+)\.homerun\.co", ATSPlatform.HOMERUN),
    (r"([a-zA-Z0-9_-]+)\.bamboohr\.com", ATSPlatform.BAMBOOHR),
    (r"([a-zA-Z0-9_-]+)\.jobs\.personio\.de", ATSPlatform.PERSONIO),
]

_GREENHOUSE_SKIP_SLUGS = {"embed", "api", "v1", "boards", "job-boards"}

REGION_KEYWORDS: dict[str, list[str]] = {
    "eu": [
        "Europe", "EMEA", "EU",
        "Germany", "Berlin", "Munich", "Hamburg", "Frankfurt",
        "France", "Paris", "Lyon", "Marseille",
        "Netherlands", "Amsterdam", "Rotterdam", "The Hague",
        "Spain", "Madrid", "Barcelona", "Valencia",
        "Italy", "Milan", "Rome", "Turin",
        "Ireland", "Dublin",
        "Sweden", "Stockholm", "Gothenburg",
        "Denmark", "Copenhagen",
        "Finland", "Helsinki",
        "Poland", "Warsaw", "Krakow", "Wroclaw",
        "Portugal", "Lisbon", "Porto",
        "Austria", "Vienna",
        "Belgium", "Brussels", "Antwerp",
        "Czech", "Prague", "Brno",
        "Romania", "Bucharest",
        "Norway", "Oslo",
        "Switzerland", "Zurich", "Geneva", "Basel",
        "Greece", "Athens",
        "Hungary", "Budapest",
        "Croatia", "Zagreb",
        "Estonia", "Tallinn",
        "Latvia", "Riga",
        "Lithuania", "Vilnius",
    ],
    "us": [
        "United States", "USA", "US ", " US,", "US-",
        "North America",
        "New York", "NYC", "Manhattan", "Brooklyn",
        "San Francisco", "SF Bay", "Bay Area",
        "Los Angeles", "LA,",
        "Chicago", "Seattle", "Austin", "Boston", "Denver",
        "Atlanta", "Miami", "Portland", "Houston", "Dallas",
        "San Diego", "San Jose", "Phoenix", "Philadelphia",
        "Washington DC", "D.C.",
        "California", "Texas", "Colorado", "Massachusetts",
        "Virginia", "Georgia", "Oregon", "Minnesota",
        "Remote, US", "Remote - US", "Remote US", "US Remote",
        "Remote, United States",
    ],
    "uk": [
        "United Kingdom", " UK", "UK,", "UK -",
        "London", "Manchester", "Edinburgh", "Glasgow",
        "Bristol", "Cambridge", "Oxford", "Birmingham",
        "Leeds", "Liverpool", "Belfast", "Cardiff",
    ],
    "remote": [
        "Remote", "Anywhere", "Distributed", "Work from home",
        "Worldwide", "Global",
    ],
    "mena": [
        "Morocco", "Casablanca", "Rabat", "Marrakech", "Tangier", "Agadir", "Fez", "Meknes",
        "Tunisia", "Tunis", "Sfax",
        "Egypt", "Cairo", "Alexandria", "Giza",
        "UAE", "Dubai", "Abu Dhabi", "Sharjah", "United Arab Emirates",
        "Saudi", "Saudi Arabia", "Riyadh", "Jeddah", "Dammam",
        "Jordan", "Amman",
        "Lebanon", "Beirut",
        "Bahrain", "Manama",
        "Qatar", "Doha",
        "Oman", "Muscat",
        "Kuwait", "Kuwait City",
        "MENA", "Middle East", "North Africa",
    ],
    "morocco": [
        "Morocco", "Casablanca", "Rabat", "Marrakech", "Tangier", "Agadir", "Fez", "Meknes",
    ],
    "uae": [
        "UAE", "Dubai", "Abu Dhabi", "Sharjah", "United Arab Emirates",
    ],
    "egypt": [
        "Egypt", "Cairo", "Alexandria", "Giza",
    ],
    "saudi": [
        "Saudi", "Saudi Arabia", "Riyadh", "Jeddah", "Dammam",
    ],
    "tunisia": [
        "Tunisia", "Tunis", "Sfax",
    ],
    "jordan": ["Jordan", "Amman"],
    "lebanon": ["Lebanon", "Beirut"],
    "bahrain": ["Bahrain", "Manama"],
    "qatar": ["Qatar", "Doha"],
    "oman": ["Oman", "Muscat"],
    "kuwait": ["Kuwait", "Kuwait City"],
}


@dataclass
class DiscoverySource:
    name: str
    url: str
    format: str = "stapply_csv"


DEFAULT_SOURCES: list[DiscoverySource] = [
    DiscoverySource(
        name="Stapply ATS Jobs",
        url="https://storage.stapply.ai/jobs.csv",
        format="stapply_csv",
    ),
]


@dataclass
class DiscoveredCompany:
    slug: str
    name: str
    platform: ATSPlatform
    valid: bool | None = None  # None = not yet validated
    region_tags: list[str] = field(default_factory=list)


async def fetch_source(client: httpx.AsyncClient, source: DiscoverySource) -> list[DiscoveredCompany]:
    """Fetch and parse a discovery source into company candidates."""
    resp = await client.get(source.url, timeout=30.0)
    resp.raise_for_status()

    if source.format == "stapply_csv":
        return _parse_stapply_csv(resp.text)
    elif source.format == "newline_slugs":
        return _parse_newline_slugs(resp.text, source)
    return []


def _parse_stapply_csv(text: str) -> list[DiscoveredCompany]:
    """Parse the stapply jobs.csv — extract unique (platform, slug) from job URLs."""
    reader = csv.DictReader(io.StringIO(text))
    seen: dict[tuple[str, str], str] = {}  # (platform, slug) -> company_name

    for row in reader:
        url = row.get("url", "")
        company_name = row.get("company", "")

        for pattern, platform in _URL_PATTERNS:
            m = re.search(pattern, url)
            if m:
                slug = m.group(1).lower()
                if platform == ATSPlatform.GREENHOUSE and slug in _GREENHOUSE_SKIP_SLUGS:
                    continue
                key = (platform.value, slug)
                if key not in seen:
                    seen[key] = company_name or slug
                break

    return [
        DiscoveredCompany(slug=slug, name=name, platform=ATSPlatform(plat))
        for (plat, slug), name in seen.items()
    ]


def _parse_newline_slugs(text: str, source: DiscoverySource) -> list[DiscoveredCompany]:
    """Parse a simple newline-separated list of slugs."""
    slugs = [line.strip() for line in text.strip().split("\n") if line.strip()]
    # Try to infer platform from URL
    platform = None
    url_lower = source.url.lower()
    for plat in ATSPlatform:
        if plat.value in url_lower:
            platform = plat
            break
    if not platform:
        platform = ATSPlatform.GREENHOUSE  # fallback

    return [DiscoveredCompany(slug=s, name=s, platform=platform) for s in slugs]


async def validate_slug(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    company: DiscoveredCompany,
) -> bool:
    """Check if a company slug is valid by making a HEAD/GET request.

    Network errors and timeouts are treated as 'assume valid' since
    slugs come from curated community sources. Only explicit 404/410
    responses mark a slug as invalid.
    """
    url_template = VALIDATION_URLS.get(company.platform)
    if not url_template:
        company.valid = False
        return False

    url = url_template.format(slug=company.slug)

    async with semaphore:
        try:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                company.valid = True
            elif resp.status_code in (404, 410):
                company.valid = False
            else:
                # Other errors (429, 5xx) — assume valid, slug probably exists
                company.valid = True
        except (httpx.TimeoutException, httpx.ConnectError):
            # Network issues — assume valid since slug came from community source
            company.valid = True
        except Exception:
            company.valid = False

    return company.valid


async def probe_region(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    company: DiscoveredCompany,
    region: str,
) -> bool:
    """Fetch jobs from a company and check if any match the target region."""
    keywords = REGION_KEYWORDS.get(region, [])
    if not keywords:
        return False

    provider = PROVIDERS.get(company.platform)
    if not provider:
        return False

    c = Company(slug=company.slug, name=company.name, platform=company.platform)

    async with semaphore:
        try:
            jobs = await provider.fetch_jobs(client, c)
        except Exception:
            return False

    # Check if any job location matches region keywords
    for job in jobs:
        if not job.location:
            continue
        loc_lower = job.location.lower()
        if any(kw.lower() in loc_lower for kw in keywords):
            return True

    return False


async def discover(
    sources: list[DiscoverySource] | None = None,
    platforms: list[ATSPlatform] | None = None,
    region: str | None = None,
    max_concurrent: int = 50,
    existing_keys: set[tuple[str, str]] | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
    skip_validation: bool = False,
) -> list[DiscoveredCompany]:
    if sources is None:
        sources = DEFAULT_SOURCES
    if existing_keys is None:
        existing_keys = set()

    # Step 1: Fetch sources
    candidates: list[DiscoveredCompany] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for source in sources:
            try:
                if on_progress:
                    on_progress("fetch", 0, 0)
                fetched = await fetch_source(client, source)
                candidates.extend(fetched)
            except Exception as e:
                logger.warning("Failed to fetch source %s: %s", source.name, e)
                if on_progress:
                    on_progress("error", 0, 0)

    # Step 2: Filter by platform
    if platforms:
        candidates = [c for c in candidates if c.platform in platforms]

    # Step 3: Deduplicate against existing database
    candidates = [
        c for c in candidates
        if (c.platform.value, c.slug) not in existing_keys
    ]

    # Deduplicate within candidates
    seen: set[tuple[str, str]] = set()
    unique: list[DiscoveredCompany] = []
    for c in candidates:
        key = (c.platform.value, c.slug)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    candidates = unique

    if not candidates:
        return []

    total = len(candidates)

    # Step 4: Validate slugs (unless skipped)
    if skip_validation:
        for c in candidates:
            c.valid = True
        valid = candidates
    else:
        semaphore = asyncio.Semaphore(max_concurrent)
        validated_count = 0

        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            async def validate_one(c: DiscoveredCompany) -> None:
                nonlocal validated_count
                await validate_slug(client, semaphore, c)
                validated_count += 1
                if on_progress:
                    on_progress("validate", validated_count, total)

            await asyncio.gather(*[validate_one(c) for c in candidates])

        valid = [c for c in candidates if c.valid]

    if not valid:
        return []

    # Step 5: Region probing (optional)
    if region and region in REGION_KEYWORDS:
        region_sem = asyncio.Semaphore(min(max_concurrent, 15))
        probed_count = 0
        region_total = len(valid)

        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            async def probe_one(c: DiscoveredCompany) -> None:
                nonlocal probed_count
                matched = await probe_region(client, region_sem, c, region)
                if matched:
                    c.region_tags.append(region)
                probed_count += 1
                if on_progress:
                    on_progress("region", probed_count, region_total)

            await asyncio.gather(*[probe_one(c) for c in valid])

        # Filter to only region-matched companies
        valid = [c for c in valid if region in c.region_tags]

    return valid
