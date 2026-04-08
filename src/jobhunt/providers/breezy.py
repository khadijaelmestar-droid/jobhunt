from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class BreezyProvider:
    platform = ATSPlatform.BREEZY

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.breezy.hr/json",
        )
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list):
            return []

        jobs: list[Job] = []
        for item in data:
            location_obj = item.get("location", {})
            if isinstance(location_obj, dict):
                city = location_obj.get("name", "")
                country = location_obj.get("country", {}).get("name", "")
                location = ", ".join(filter(None, [city, country]))
            elif isinstance(location_obj, str):
                location = location_obj
            else:
                location = ""

            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("published_date"):
                try:
                    created = datetime.fromisoformat(item["published_date"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = item.get("id", item.get("friendly_id", ""))
            url = item.get("url", f"https://{company.slug}.breezy.hr/p/{job_id}")

            jobs.append(Job(
                id=str(job_id),
                title=item.get("name", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=item.get("department"),
                team=item.get("team"),
                employment_type=item.get("type", {}).get("name") if isinstance(item.get("type"), dict) else item.get("type"),
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
