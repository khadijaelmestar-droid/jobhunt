from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class GreenhouseProvider:
    platform = ATSPlatform.GREENHOUSE

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://boards-api.greenhouse.io/v1/boards/{company.slug}/jobs",
            params={"content": "true"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for item in data.get("jobs", []):
            location = item.get("location", {}).get("name", "")
            content = item.get("content", "")
            snippet = strip_html(content)[:200] if content else None

            updated = None
            if item.get("updated_at"):
                try:
                    updated = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            departments = item.get("departments", [])
            department = departments[0]["name"] if departments else None

            jobs.append(Job(
                id=str(item["id"]),
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department,
                url=item.get("absolute_url", ""),
                updated_at=updated,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
