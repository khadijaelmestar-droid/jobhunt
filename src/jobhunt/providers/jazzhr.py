from __future__ import annotations

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class JazzHRProvider:
    platform = ATSPlatform.JAZZHR

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://app.jazz.co/api/{company.slug}/jobs",
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            data = data.get("jobs", [])

        jobs: list[Job] = []
        for item in data:
            location_parts = []
            if item.get("city"):
                location_parts.append(item["city"])
            if item.get("state"):
                location_parts.append(item["state"])
            if item.get("country"):
                location_parts.append(item["country"])
            location = ", ".join(location_parts)

            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            job_id = item.get("id", item.get("board_code", ""))
            url = item.get("url", f"https://app.jazz.co/{company.slug}/jobs/{job_id}")

            jobs.append(Job(
                id=str(job_id),
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=item.get("department"),
                employment_type=item.get("type"),
                url=url,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
