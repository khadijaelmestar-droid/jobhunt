from __future__ import annotations

from jobhunt.models import Job, SearchQuery


def filter_jobs(jobs: list[Job], query: SearchQuery) -> list[Job]:
    results = jobs

    if query.keywords:
        results = [j for j in results if _matches_keywords(j, query.keywords)]
    if query.remote_only:
        results = [j for j in results if j.is_remote]
    if query.location:
        results = [j for j in results if _matches_location(j, query.location)]
    if query.department:
        results = [j for j in results if _matches_field(j.department, query.department)]
    if query.platforms:
        results = [j for j in results if j.platform in query.platforms]

    return sorted(results, key=lambda j: (j.company.lower(), j.title.lower()))


def _matches_keywords(job: Job, keywords: list[str]) -> bool:
    searchable = " ".join(
        s.lower() for s in [
            job.title,
            job.department or "",
            job.team or "",
            job.description_snippet or "",
            job.location or "",
        ]
    )
    return any(kw.lower() in searchable for kw in keywords)


def _matches_location(job: Job, location: str) -> bool:
    if not job.location:
        return False
    return location.lower() in job.location.lower()


def _matches_field(field: str | None, value: str) -> bool:
    if not field:
        return False
    return value.lower() in field.lower()
