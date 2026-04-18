from __future__ import annotations

from jobhunt.models import Job, SearchQuery

# Expand location tokens to also match major cities / country variants
_LOCATION_ALIASES: dict[str, list[str]] = {
    "morocco": ["casablanca", "rabat", "marrakech", "tangier", "agadir", "fes", "fez", "meknes", "oujda", "tetouan", "ma"],
    "uae": ["dubai", "abu dhabi", "sharjah", "ajman", "ae"],
    "egypt": ["cairo", "alexandria", "giza", "eg"],
    "saudi": ["riyadh", "jeddah", "dammam", "mecca", "medina", "sa"],
    "tunisia": ["tunis", "sfax", "tn"],
    "jordan": ["amman", "jo"],
    "lebanon": ["beirut", "lb"],
    "bahrain": ["manama", "bh"],
    "qatar": ["doha", "qa"],
    "oman": ["muscat", "om"],
    "kuwait": ["kuwait city", "kw"],
    "mena": ["casablanca", "dubai", "cairo", "riyadh", "tunis", "amman", "beirut", "doha", "muscat", "manama", "morocco", "uae", "egypt", "saudi", "tunisia", "jordan", "lebanon", "bahrain", "qatar", "oman", "kuwait"],
    "eu": ["amsterdam", "berlin", "paris", "madrid", "barcelona", "rome", "milan", "warsaw", "prague", "vienna", "stockholm", "oslo", "copenhagen", "helsinki", "brussels", "lisbon", "athens"],
    "uk": ["london", "manchester", "birmingham", "edinburgh", "glasgow", "bristol", "gb"],
    "us": ["new york", "san francisco", "seattle", "austin", "boston", "chicago", "los angeles", "denver", "us", "usa"],
}


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
    job_loc = job.location.lower()
    loc = location.lower()
    if loc in job_loc:
        return True
    return any(alias in job_loc for alias in _LOCATION_ALIASES.get(loc, []))


def _matches_field(field: str | None, value: str) -> bool:
    if not field:
        return False
    return value.lower() in field.lower()
