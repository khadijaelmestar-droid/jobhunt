from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class SmartRecruitersProvider:
    platform = ATSPlatform.SMARTRECRUITERS

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        all_jobs: list[Job] = []
        offset = 0
        limit = 100

        while True:
            resp = await client.get(
                f"https://api.smartrecruiters.com/v1/companies/{company.slug}/postings",
                params={"offset": offset, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            content = data.get("content", [])
            if not content:
                break

            for item in content:
                location_obj = item.get("location", {})
                city = location_obj.get("city", "")
                country = location_obj.get("country", "")
                location = ", ".join(filter(None, [city, country]))

                department_obj = item.get("department", {})
                department = department_obj.get("label") if department_obj else None

                created = None
                if item.get("releasedDate"):
                    try:
                        created = datetime.fromisoformat(item["releasedDate"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                name = item.get("name", "")
                job_id = item.get("id", "")
                url = f"https://jobs.smartrecruiters.com/{company.slug}/{job_id}"

                description = item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "")
                snippet = strip_html(description)[:200] if description else None

                all_jobs.append(Job(
                    id=str(job_id),
                    title=name,
                    company=company.name,
                    company_slug=company.slug,
                    platform=self.platform,
                    location=location or None,
                    department=department,
                    employment_type=item.get("typeOfEmployment", {}).get("label"),
                    url=url,
                    created_at=created,
                    is_remote="remote" in location.lower() if location else False,
                    description_snippet=snippet,
                ))

            if len(content) < limit:
                break
            offset += limit

        return all_jobs
