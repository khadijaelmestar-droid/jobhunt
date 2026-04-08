from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class HomerunProvider:
    platform = ATSPlatform.HOMERUN

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.homerun.co/api/v1/jobs",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("jobs", [])

        jobs: list[Job] = []
        for item in items:
            location = item.get("location", "")
            department = item.get("department", "")

            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("published_at"):
                try:
                    created = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = str(item.get("id", item.get("slug", "")))
            url = item.get("url", item.get("application_url", f"https://{company.slug}.homerun.co/{job_id}"))

            jobs.append(Job(
                id=job_id,
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
