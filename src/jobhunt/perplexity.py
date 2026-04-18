"""Perplexity API client for AI-powered company discovery."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.parse
from dataclasses import dataclass

from jobhunt.models import ATSPlatform, Job

logger = logging.getLogger(__name__)

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

# Prompt templates per platform
_PLATFORM_HINTS: dict[ATSPlatform, str] = {
    ATSPlatform.GREENHOUSE: (
        "companies that use Greenhouse ATS for hiring (their job boards are at boards.greenhouse.io/<slug>). "
        "Return the company name and the slug (the part after boards.greenhouse.io/ in their job board URL)."
    ),
    ATSPlatform.LEVER: (
        "companies that use Lever for their job board (at jobs.lever.co/<slug>). "
        "Return the company name and the slug (the part after jobs.lever.co/)."
    ),
    ATSPlatform.ASHBY: (
        "companies that use Ashby ATS for their job board (at jobs.ashbyhq.com/<slug>). "
        "Return the company name and the slug (the part after jobs.ashbyhq.com/)."
    ),
    ATSPlatform.RECRUITEE: (
        "companies that use Recruitee ATS (at <slug>.recruitee.com or careers pages powered by Recruitee). "
        "Return the company name and the Recruitee slug."
    ),
    ATSPlatform.RIPPLING: (
        "companies that use Rippling ATS for their job board. "
        "Return the company name and their Rippling board slug."
    ),
    ATSPlatform.WORKABLE: (
        "companies that use Workable ATS for hiring (their job boards are at apply.workable.com/<slug>). "
        "Return the company name and the slug (the part after apply.workable.com/)."
    ),
    ATSPlatform.SMARTRECRUITERS: (
        "companies that use SmartRecruiters ATS (their job boards are at jobs.smartrecruiters.com/<slug>). "
        "Return the company name and the slug (the part after jobs.smartrecruiters.com/)."
    ),
    ATSPlatform.JAZZHR: (
        "companies that use JazzHR ATS for hiring (at app.jazz.co/<slug> or similar). "
        "Return the company name and the JazzHR slug."
    ),
    ATSPlatform.BREEZY: (
        "companies that use Breezy HR ATS (their job boards are at <slug>.breezy.hr). "
        "Return the company name and the subdomain slug."
    ),
    ATSPlatform.TEAMTAILOR: (
        "companies that use Teamtailor ATS (their career sites are at <slug>.teamtailor.com or custom domains powered by Teamtailor). "
        "Return the company name and the Teamtailor subdomain slug."
    ),
    ATSPlatform.HOMERUN: (
        "companies that use Homerun ATS (their job boards are at <slug>.homerun.co). "
        "Return the company name and the Homerun subdomain slug."
    ),
    ATSPlatform.BAMBOOHR: (
        "companies that use BambooHR ATS (their career pages are at <slug>.bamboohr.com/careers). "
        "Return the company name and the BambooHR subdomain slug."
    ),
    ATSPlatform.PERSONIO: (
        "companies that use Personio ATS (their job boards are at <slug>.jobs.personio.de). "
        "Return the company name and the Personio subdomain slug."
    ),
}

_REGION_HINTS: dict[str, str] = {
    "eu": "Focus on companies based in Europe (EU countries, UK, Switzerland, Nordics).",
    "us": "Focus on companies based in the United States.",
    "uk": "Focus on companies based in the United Kingdom.",
    "remote": "Focus on companies that offer remote positions or are remote-first.",
    "mena": "Focus on companies based in the Middle East and North Africa (Morocco, Tunisia, Egypt, UAE, Saudi Arabia, Jordan, Lebanon, Bahrain, Qatar, Oman, Kuwait). Include all industries: tech, banking, telecom, BPO, manufacturing, retail, logistics.",
    "morocco": "Focus on companies based in Morocco (Casablanca, Rabat, Marrakech, Tangier, Agadir). Include all industries.",
    "uae": "Focus on companies based in the United Arab Emirates (Dubai, Abu Dhabi, Sharjah). Include all industries.",
    "egypt": "Focus on companies based in Egypt (Cairo, Alexandria). Include all industries.",
    "saudi": "Focus on companies based in Saudi Arabia (Riyadh, Jeddah, Dammam). Include all industries.",
    "tunisia": "Focus on companies based in Tunisia (Tunis, Sfax). Include all industries.",
    "jordan": "Focus on companies based in Jordan (Amman). Include all industries.",
    "lebanon": "Focus on companies based in Lebanon (Beirut). Include all industries.",
    "bahrain": "Focus on companies based in Bahrain. Include all industries.",
    "qatar": "Focus on companies based in Qatar (Doha). Include all industries.",
    "oman": "Focus on companies based in Oman (Muscat). Include all industries.",
    "kuwait": "Focus on companies based in Kuwait. Include all industries.",
}

DISCOVERY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "company_discovery",
        "schema": {
            "type": "object",
            "properties": {
                "companies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Company display name"},
                            "slug": {"type": "string", "description": "The URL slug for their job board"},
                        },
                        "required": ["name", "slug"],
                    },
                },
            },
            "required": ["companies"],
        },
    },
}


@dataclass
class PerplexityCandidate:
    """A company candidate discovered via Perplexity."""

    name: str
    slug: str
    platform: ATSPlatform
    source_query: str = ""


def _get_api_key() -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        raise RuntimeError(
            "PERPLEXITY_API_KEY not set. "
            "Get one at https://www.perplexity.ai/settings/api and set it: "
            "export PERPLEXITY_API_KEY=pplx-xxx"
        )
    return key


def _build_prompt(platform: ATSPlatform, region: str | None, count: int = 30) -> str:
    platform_hint = _PLATFORM_HINTS.get(platform, f"companies using {platform.value} ATS")
    region_hint = _REGION_HINTS.get(region, "") if region else ""
    return (
        f"List {count} tech {platform_hint} "
        f"{region_hint} "
        f"Only include companies you are confident about. "
        f"The slug should be lowercase, using hyphens not spaces."
    ).strip()


async def query_perplexity(
    prompt: str,
    model: str = "sonar",
    api_key: str | None = None,
) -> dict:
    """Send a structured query to Perplexity API. Returns parsed JSON response."""
    import httpx

    key = api_key or _get_api_key()

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{PERPLEXITY_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a research assistant that finds companies using specific ATS platforms. Return accurate, verified information only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": DISCOVERY_SCHEMA,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Perplexity sometimes returns truncated JSON — try to salvage partial results
        return _repair_json(content)


def _repair_json(raw: str) -> dict:
    """Attempt to extract valid company entries from truncated JSON."""
    # Try to find all complete {"name": "...", "slug": "..."} objects
    companies = []
    for m in re.finditer(
        r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"slug"\s*:\s*"([^"]+)"\s*\}',
        raw,
    ):
        companies.append({"name": m.group(1), "slug": m.group(2)})
    return {"companies": companies}


async def discover_via_perplexity(
    platforms: list[ATSPlatform] | None = None,
    region: str | None = None,
    count_per_query: int = 30,
    model: str = "sonar",
    api_key: str | None = None,
) -> list[PerplexityCandidate]:
    """Discover companies using Perplexity AI web search.

    Generates targeted queries per platform (optionally filtered by region),
    parses structured JSON responses, and returns candidate companies.
    """
    key = api_key or _get_api_key()
    target_platforms = platforms or list(ATSPlatform)
    all_candidates: list[PerplexityCandidate] = []
    seen: set[tuple[str, str]] = set()

    for plat in target_platforms:
        prompt = _build_prompt(plat, region, count_per_query)
        logger.info("Querying Perplexity for %s companies (region=%s)", plat.value, region or "any")

        try:
            result = await query_perplexity(prompt, model=model, api_key=key)
        except Exception as e:
            logger.warning("Perplexity query failed for %s: %s", plat.value, e)
            continue

        companies = result.get("companies", [])
        for c in companies:
            name = c.get("name", "").strip()
            slug = c.get("slug", "").strip().lower().replace(" ", "-")
            if not name or not slug:
                continue

            dedup_key = (plat.value, slug)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            all_candidates.append(
                PerplexityCandidate(
                    name=name,
                    slug=slug,
                    platform=plat,
                    source_query=prompt[:100],
                )
            )

    return all_candidates


_INDUSTRIES = [
    "tech", "fintech", "healthtech", "e-commerce", "SaaS",
    "cybersecurity", "AI/ML", "biotech", "logistics", "edtech",
]


async def discover_via_perplexity_deep(
    platforms: list[ATSPlatform] | None = None,
    region: str | None = None,
    industries: list[str] | None = None,
    count_per_query: int = 50,
    model: str = "sonar",
    api_key: str | None = None,
    exclude_slugs: set[str] | None = None,
) -> list[PerplexityCandidate]:
    """Enhanced discovery with industry-specific queries and iterative deepening.

    Queries Perplexity for each platform x industry combination,
    then does a follow-up "more like these" query excluding already-found slugs.
    """
    key = api_key or _get_api_key()
    target_platforms = platforms or list(ATSPlatform)
    target_industries = industries or _INDUSTRIES
    all_candidates: list[PerplexityCandidate] = []
    seen: set[tuple[str, str]] = set()
    excluded = exclude_slugs or set()

    for plat in target_platforms:
        platform_hint = _PLATFORM_HINTS.get(plat, f"companies using {plat.value} ATS")
        region_hint = _REGION_HINTS.get(region, "") if region else ""

        for industry in target_industries:
            prompt = (
                f"List {count_per_query} {industry} {platform_hint} "
                f"{region_hint} "
                f"Only include companies you are confident about. "
                f"The slug should be lowercase, using hyphens not spaces."
            ).strip()

            if excluded:
                sample = list(excluded)[:20]
                prompt += f" Exclude these already-known slugs: {', '.join(sample)}."

            try:
                result = await query_perplexity(prompt, model=model, api_key=key)
            except Exception as e:
                logger.warning("Perplexity query failed for %s/%s: %s", plat.value, industry, e)
                continue

            for c in result.get("companies", []):
                name = c.get("name", "").strip()
                slug = c.get("slug", "").strip().lower().replace(" ", "-")
                if not name or not slug:
                    continue
                if slug in excluded:
                    continue

                dedup_key = (plat.value, slug)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                all_candidates.append(
                    PerplexityCandidate(
                        name=name,
                        slug=slug,
                        platform=plat,
                        source_query=f"{industry}/{plat.value}",
                    )
                )

    return all_candidates


_LINKEDIN_JOB_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "linkedin_jobs",
        "schema": {
            "type": "object",
            "properties": {
                "jobs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "company": {"type": "string"},
                            "url": {"type": "string"},
                            "location": {"type": "string"},
                            "remote": {"type": "boolean"},
                            "description": {"type": "string"},
                        },
                        "required": ["title", "company", "url"],
                    },
                },
            },
            "required": ["jobs"],
        },
    },
}


async def search_linkedin_jobs(
    keywords: list[str],
    location: str | None = None,
    remote_only: bool = False,
    region: str | None = None,
    count: int = 20,
    model: str = "sonar",
    api_key: str | None = None,
) -> list[Job]:
    """Search LinkedIn job postings via Perplexity and return as Job objects."""
    import httpx

    key = api_key or _get_api_key()
    if not key:
        return []

    keywords_str = " ".join(keywords) if keywords else "software engineer"

    region_hint = _REGION_HINTS.get(region, f"in {region}") if region else ""
    location_hint = f"in {location}" if location else ""
    remote_hint = "remote positions only" if remote_only else ""

    context_parts = [p for p in [region_hint, location_hint, remote_hint] if p]
    context = ". ".join(context_parts) + "." if context_parts else ""

    prompt = (
        f"Find {count} current active job postings on LinkedIn matching: {keywords_str}. "
        f"{context} "
        f"Return only real LinkedIn job URLs (linkedin.com/jobs/view/...). "
        f"For each job include: title, company name, direct LinkedIn job URL, location, "
        f"whether it is remote, and a one-sentence description."
    ).strip()

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{PERPLEXITY_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a job search assistant. Return accurate, current LinkedIn job listings."},
                    {"role": "user", "content": prompt},
                ],
                "response_format": _LINKEDIN_JOB_SCHEMA,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)

    jobs: list[Job] = []
    for item in parsed.get("jobs", []):
        company = item.get("company", "").strip()
        title = item.get("title", "").strip()
        if not company or not title:
            continue
        # Build a real LinkedIn search URL instead of using Perplexity-generated
        # job IDs, which are fabricated and always return 404.
        search_q = urllib.parse.quote_plus(f"{title} {company}")
        search_url = f"https://www.linkedin.com/jobs/search/?keywords={search_q}"
        slug = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")
        job_id = hashlib.md5(f"{title}:{slug}".encode()).hexdigest()[:12]
        jobs.append(
            Job(
                id=job_id,
                title=title,
                company=company,
                company_slug=slug,
                platform=ATSPlatform.LINKEDIN,
                location=item.get("location") or None,
                is_remote=bool(item.get("remote", False)),
                url=search_url,
                description_snippet=item.get("description") or None,
            )
        )

    return jobs
