from __future__ import annotations

import httpx

from jobhunt.models import ATSPlatform, Company, Job


class RipplingProvider:
    platform = ATSPlatform.RIPPLING

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://api.rippling.com/platform/api/ats/v1/board/{company.slug}/jobs",
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("jobs", data.get("results", []))

        jobs: list[Job] = []
        for item in items:
            location_obj = item.get("location", {})
            if isinstance(location_obj, dict):
                parts = [location_obj.get("city", ""), location_obj.get("state", ""), location_obj.get("country", "")]
                location = ", ".join(p for p in parts if p) or None
            elif isinstance(location_obj, str):
                location = location_obj or None
            else:
                location = None

            is_remote = item.get("remote", False)
            if not is_remote and location:
                is_remote = "remote" in location.lower()

            jobs.append(Job(
                id=str(item.get("id", "")),
                title=item.get("name", item.get("title", "")),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location,
                department=item.get("department", {}).get("name") if isinstance(item.get("department"), dict) else item.get("department"),
                url=item.get("url", item.get("applicationUrl", f"https://ats.rippling.com/{company.slug}/jobs/{item.get('id', '')}")),
                is_remote=is_remote,
            ))
        return jobs
