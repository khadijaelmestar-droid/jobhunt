from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class TeamtailorProvider:
    platform = ATSPlatform.TEAMTAILOR

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.teamtailor.com/jobs",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("jobs", data.get("data", []))
        if not isinstance(items, list):
            return []

        jobs: list[Job] = []
        for item in items:
            attrs = item.get("attributes", item)
            location = attrs.get("location", "")
            department = attrs.get("department", "")

            body = attrs.get("body", attrs.get("description", ""))
            snippet = strip_html(body)[:200] if body else None

            created = None
            pub_date = attrs.get("published-at", attrs.get("created_at", ""))
            if pub_date:
                try:
                    created = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = str(item.get("id", ""))
            title = attrs.get("title", "")
            url = attrs.get("careersite-job-url", f"https://{company.slug}.teamtailor.com/jobs/{job_id}")

            jobs.append(Job(
                id=job_id,
                title=title,
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=attrs.get("employment-type"),
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
