from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class PersonioProvider:
    platform = ATSPlatform.PERSONIO

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.jobs.personio.de/search.json",
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("positions", data.get("jobs", []))
        if not isinstance(items, list):
            return []

        jobs: list[Job] = []
        for item in items:
            location = item.get("office", item.get("location", ""))
            department = item.get("department", "")
            schedule = item.get("schedule", item.get("employment_type", ""))

            description = item.get("description", item.get("jobDescription", ""))
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("createdAt"):
                try:
                    created = datetime.fromisoformat(str(item["createdAt"]).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = str(item.get("id", item.get("positionId", "")))
            slug_part = item.get("slug", job_id)
            url = item.get("url", f"https://{company.slug}.jobs.personio.de/job/{slug_part}")

            jobs.append(Job(
                id=job_id,
                title=item.get("name", item.get("title", "")),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=schedule or None,
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
