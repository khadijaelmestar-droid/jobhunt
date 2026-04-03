from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class RecruiteeProvider:
    platform = ATSPlatform.RECRUITEE

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://api.recruitee.com/c/{company.slug}/offers",
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for item in data.get("offers", []):
            location = item.get("location", "")
            is_remote = item.get("remote", False)
            if not is_remote and isinstance(location, str):
                is_remote = "remote" in location.lower()

            created = None
            if item.get("created_at"):
                try:
                    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            jobs.append(Job(
                id=str(item.get("id", "")),
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=item.get("department"),
                employment_type=item.get("employment_type_code"),
                url=item.get("careers_url", ""),
                created_at=created,
                is_remote=is_remote,
                description_snippet=snippet,
            ))
        return jobs
