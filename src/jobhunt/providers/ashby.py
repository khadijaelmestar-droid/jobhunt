from __future__ import annotations

import httpx

from jobhunt.models import ATSPlatform, Company, Job


class AshbyProvider:
    platform = ATSPlatform.ASHBY

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{company.slug}",
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for item in data.get("jobs", []):
            location = item.get("location", "")
            is_remote = item.get("isRemote", False)
            if not is_remote and isinstance(location, str):
                is_remote = "remote" in location.lower()

            jobs.append(Job(
                id=item.get("id", ""),
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location if isinstance(location, str) else None,
                department=item.get("departmentName"),
                team=item.get("teamName"),
                employment_type=item.get("employmentType"),
                url=item.get("jobUrl", ""),
                is_remote=is_remote,
            ))
        return jobs
