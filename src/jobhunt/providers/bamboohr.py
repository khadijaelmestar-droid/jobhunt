from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class BambooHRProvider:
    platform = ATSPlatform.BAMBOOHR

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.bamboohr.com/careers/list",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("result", [])
        if not isinstance(items, list):
            return []

        jobs: list[Job] = []
        for item in items:
            location_obj = item.get("location", {})
            if isinstance(location_obj, dict):
                city = location_obj.get("city", "")
                state = location_obj.get("state", "")
                country = location_obj.get("country", "")
                location = ", ".join(filter(None, [city, state, country]))
            else:
                location = str(location_obj) if location_obj else ""

            department = item.get("departmentLabel", item.get("department", ""))

            created = None
            if item.get("dateCreated"):
                try:
                    created = datetime.fromisoformat(item["dateCreated"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = str(item.get("id", ""))
            url = f"https://{company.slug}.bamboohr.com/careers/{job_id}"

            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            jobs.append(Job(
                id=job_id,
                title=item.get("jobOpeningName", item.get("title", "")),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=item.get("employmentStatusLabel"),
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
