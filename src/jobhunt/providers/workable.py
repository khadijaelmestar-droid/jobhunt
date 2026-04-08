from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class WorkableProvider:
    platform = ATSPlatform.WORKABLE

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://apply.workable.com/api/v1/widget/{company.slug}",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for item in data.get("jobs", []):
            location = item.get("location", "")
            department = item.get("department", "")
            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("published_on"):
                try:
                    created = datetime.fromisoformat(item["published_on"])
                except (ValueError, TypeError):
                    pass

            shortcode = item.get("shortcode", "")
            url = f"https://apply.workable.com/{company.slug}/j/{shortcode}/" if shortcode else ""

            jobs.append(Job(
                id=shortcode or str(item.get("id", "")),
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=item.get("employment_type"),
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
