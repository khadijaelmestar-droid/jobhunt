from __future__ import annotations

from datetime import datetime, timezone

import httpx

from jobhunt.models import ATSPlatform, Company, Job


class LeverProvider:
    platform = ATSPlatform.LEVER

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://api.lever.co/v0/postings/{company.slug}",
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []

        jobs: list[Job] = []
        for item in data:
            categories = item.get("categories", {})
            location = categories.get("location", "")
            description = item.get("descriptionPlain", "")
            snippet = description[:200] if description else None

            created = None
            if item.get("createdAt"):
                try:
                    created = datetime.fromtimestamp(item["createdAt"] / 1000, tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass

            jobs.append(Job(
                id=item.get("id", ""),
                title=item.get("text", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=categories.get("department"),
                team=categories.get("team"),
                employment_type=categories.get("commitment"),
                url=item.get("hostedUrl", ""),
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
