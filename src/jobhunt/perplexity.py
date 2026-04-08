"""Perplexity API client for AI-powered company discovery."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from jobhunt.models import ATSPlatform

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
    return json.loads(content)


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
