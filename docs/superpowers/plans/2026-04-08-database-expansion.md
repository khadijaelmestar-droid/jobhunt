# Database Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand jobhunt from 5 ATS platforms / 1,017 companies to 17 ATS platforms / 5,000+ companies by adding 12 new providers and a multi-source discovery engine.

**Architecture:** Each ATS provider is a class with `platform` attribute and async `fetch_jobs(client, company) -> list[Job]`, registered in `PROVIDERS` dict. Discovery sources produce `DiscoveredCompany` objects that flow through deduplication → validation → region probing → `bulk_add()`. The CLI's `--source` option selects which discovery source to use.

**Tech Stack:** Python 3.12+, httpx (async HTTP), Pydantic (models), Typer (CLI), Rich (display), Perplexity API (AI discovery)

**Scope:** Waves 1-3 (Tier 1 + Tier 2 platforms + Discovery Engine). Wave 4 (Tier 3 enterprise: Workday, iCIMS, Taleo, SuccessFactors) is deferred — requires real-world API research for each platform's unique URL patterns.

---

## Task 1: Update Models — ATSPlatform Enum + Company.base_url

**Files:**
- Modify: `src/jobhunt/models.py:10-15` (ATSPlatform enum)
- Modify: `src/jobhunt/models.py:35-40` (Company model)

- [ ] **Step 1: Add 12 new enum values to ATSPlatform**

```python
class ATSPlatform(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    RIPPLING = "rippling"
    RECRUITEE = "recruitee"
    WORKABLE = "workable"
    SMARTRECRUITERS = "smartrecruiters"
    JAZZHR = "jazzhr"
    BREEZY = "breezy"
    TEAMTAILOR = "teamtailor"
    HOMERUN = "homerun"
    BAMBOOHR = "bamboohr"
    PERSONIO = "personio"
    WORKDAY = "workday"
    ICIMS = "icims"
    TALEO = "taleo"
    SUCCESSFACTORS = "successfactors"
```

- [ ] **Step 2: Add base_url to Company model**

```python
class Company(BaseModel):
    slug: str
    name: str
    platform: ATSPlatform
    tags: list[str] = []
    enabled: bool = True
    base_url: str | None = None
```

- [ ] **Step 3: Update VALIDATION_URLS in discovery.py**

Add validation URLs for all new platforms in `src/jobhunt/discovery.py:18-23`:

```python
VALIDATION_URLS: dict[ATSPlatform, str] = {
    ATSPlatform.GREENHOUSE: "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    ATSPlatform.LEVER: "https://api.lever.co/v0/postings/{slug}",
    ATSPlatform.ASHBY: "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    ATSPlatform.RECRUITEE: "https://api.recruitee.com/c/{slug}/offers",
    ATSPlatform.WORKABLE: "https://apply.workable.com/api/v1/widget/{slug}",
    ATSPlatform.SMARTRECRUITERS: "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
    ATSPlatform.JAZZHR: "https://app.jazz.co/api/{slug}/jobs",
    ATSPlatform.BREEZY: "https://{slug}.breezy.hr/json",
    ATSPlatform.TEAMTAILOR: "https://{slug}.teamtailor.com/jobs",
    ATSPlatform.HOMERUN: "https://{slug}.homerun.co",
    ATSPlatform.BAMBOOHR: "https://{slug}.bamboohr.com/careers/list",
    ATSPlatform.PERSONIO: "https://{slug}.jobs.personio.de/search",
}
```

- [ ] **Step 4: Update _URL_PATTERNS in discovery.py**

Add URL extraction patterns for new platforms in `src/jobhunt/discovery.py:26-31`:

```python
_URL_PATTERNS: list[tuple[str, ATSPlatform]] = [
    (r"greenhouse\.io/([a-zA-Z0-9_-]+)", ATSPlatform.GREENHOUSE),
    (r"lever\.co/([a-zA-Z0-9_-]+)", ATSPlatform.LEVER),
    (r"ashbyhq\.com/([a-zA-Z0-9_.-]+)", ATSPlatform.ASHBY),
    (r"recruitee\.com/c/([a-zA-Z0-9_-]+)", ATSPlatform.RECRUITEE),
    (r"apply\.workable\.com/([a-zA-Z0-9_-]+)", ATSPlatform.WORKABLE),
    (r"smartrecruiters\.com/([a-zA-Z0-9_-]+)", ATSPlatform.SMARTRECRUITERS),
    (r"jazz\.co/([a-zA-Z0-9_-]+)", ATSPlatform.JAZZHR),
    (r"([a-zA-Z0-9_-]+)\.breezy\.hr", ATSPlatform.BREEZY),
    (r"([a-zA-Z0-9_-]+)\.teamtailor\.com", ATSPlatform.TEAMTAILOR),
    (r"([a-zA-Z0-9_-]+)\.homerun\.co", ATSPlatform.HOMERUN),
    (r"([a-zA-Z0-9_-]+)\.bamboohr\.com", ATSPlatform.BAMBOOHR),
    (r"([a-zA-Z0-9_-]+)\.jobs\.personio\.de", ATSPlatform.PERSONIO),
]
```

- [ ] **Step 5: Update Perplexity _PLATFORM_HINTS**

Add platform hints for new ATS platforms in `src/jobhunt/perplexity.py:17-38`:

```python
_PLATFORM_HINTS: dict[ATSPlatform, str] = {
    # ... existing 5 ...
    ATSPlatform.WORKABLE: (
        "companies that use Workable ATS for hiring (their job boards are at apply.workable.com/<slug>). "
        "Return the company name and the slug (the part after apply.workable.com/)."
    ),
    ATSPlatform.SMARTRECRUITERS: (
        "companies that use SmartRecruiters ATS (their job boards are at jobs.smartrecruiters.com/<slug>). "
        "Return the company name and the slug (the part after jobs.smartrecruiters.com/)."
    ),
    ATSPlatform.JAZZHR: (
        "companies that use JazzHR ATS for hiring (at app.jazz.co/<slug> or similar). "
        "Return the company name and the JazzHR slug."
    ),
    ATSPlatform.BREEZY: (
        "companies that use Breezy HR ATS (their job boards are at <slug>.breezy.hr). "
        "Return the company name and the subdomain slug."
    ),
    ATSPlatform.TEAMTAILOR: (
        "companies that use Teamtailor ATS (their career sites are at <slug>.teamtailor.com or custom domains powered by Teamtailor). "
        "Return the company name and the Teamtailor subdomain slug."
    ),
    ATSPlatform.HOMERUN: (
        "companies that use Homerun ATS (their job boards are at <slug>.homerun.co). "
        "Return the company name and the Homerun subdomain slug."
    ),
    ATSPlatform.BAMBOOHR: (
        "companies that use BambooHR ATS (their career pages are at <slug>.bamboohr.com/careers). "
        "Return the company name and the BambooHR subdomain slug."
    ),
    ATSPlatform.PERSONIO: (
        "companies that use Personio ATS (their job boards are at <slug>.jobs.personio.de). "
        "Return the company name and the Personio subdomain slug."
    ),
}
```

- [ ] **Step 6: Verify existing CLI still works**

Run: `cd /run/media/kakaroot/4d94f399-4e96-48b2-89e4-52a93c15be761/Projects/projects/job && python -m jobhunt.cli platforms`
Expected: Lists all 17 platforms

- [ ] **Step 7: Commit**

```bash
git add src/jobhunt/models.py src/jobhunt/discovery.py src/jobhunt/perplexity.py
git commit -m "feat: add 12 new ATS platform enums, validation URLs, and Perplexity hints"
```

---

## Task 2: Workable Provider

**Files:**
- Create: `src/jobhunt/providers/workable.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create Workable provider**

Create `src/jobhunt/providers/workable.py`:

```python
from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class WorkableProvider:
    platform = ATSPlatform.WORKABLE

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://apply.workable.com/api/v1/widget/{company.slug}",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        jobs: list[Job] = []
        for item in data.get("jobs", []):
            location = item.get("location", "")
            department = item.get("department", "")
            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("published_on"):
                try:
                    created = datetime.fromisoformat(item["published_on"])
                except (ValueError, TypeError):
                    pass

            shortcode = item.get("shortcode", "")
            url = f"https://apply.workable.com/{company.slug}/j/{shortcode}/" if shortcode else ""

            jobs.append(Job(
                id=shortcode or str(item.get("id", "")),
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=item.get("employment_type"),
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py` — add import and registry entry:

```python
from jobhunt.providers.workable import WorkableProvider

# Add to PROVIDERS dict:
ATSPlatform.WORKABLE: WorkableProvider(),
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from jobhunt.providers import PROVIDERS; print(list(PROVIDERS.keys()))"`
Expected: Shows all platforms including `ATSPlatform.WORKABLE`

- [ ] **Step 4: Commit**

```bash
git add src/jobhunt/providers/workable.py src/jobhunt/providers/__init__.py
git commit -m "feat: add Workable ATS provider"
```

---

## Task 3: SmartRecruiters Provider

**Files:**
- Create: `src/jobhunt/providers/smartrecruiters.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create SmartRecruiters provider**

Create `src/jobhunt/providers/smartrecruiters.py`:

```python
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
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.smartrecruiters import SmartRecruitersProvider

# Add to PROVIDERS dict:
ATSPlatform.SMARTRECRUITERS: SmartRecruitersProvider(),
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from jobhunt.providers import PROVIDERS; print(list(PROVIDERS.keys()))"`

- [ ] **Step 4: Commit**

```bash
git add src/jobhunt/providers/smartrecruiters.py src/jobhunt/providers/__init__.py
git commit -m "feat: add SmartRecruiters ATS provider"
```

---

## Task 4: JazzHR Provider

**Files:**
- Create: `src/jobhunt/providers/jazzhr.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create JazzHR provider**

Create `src/jobhunt/providers/jazzhr.py`:

```python
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
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.jazzhr import JazzHRProvider

# Add to PROVIDERS dict:
ATSPlatform.JAZZHR: JazzHRProvider(),
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/providers/jazzhr.py src/jobhunt/providers/__init__.py
git commit -m "feat: add JazzHR ATS provider"
```

---

## Task 5: Breezy HR Provider

**Files:**
- Create: `src/jobhunt/providers/breezy.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create Breezy provider**

Create `src/jobhunt/providers/breezy.py`:

```python
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
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.breezy import BreezyProvider

# Add to PROVIDERS dict:
ATSPlatform.BREEZY: BreezyProvider(),
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/providers/breezy.py src/jobhunt/providers/__init__.py
git commit -m "feat: add Breezy HR ATS provider"
```

---

## Task 6: Teamtailor Provider

**Files:**
- Create: `src/jobhunt/providers/teamtailor.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create Teamtailor provider**

Create `src/jobhunt/providers/teamtailor.py`:

```python
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
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.teamtailor import TeamtailorProvider

# Add to PROVIDERS dict:
ATSPlatform.TEAMTAILOR: TeamtailorProvider(),
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/providers/teamtailor.py src/jobhunt/providers/__init__.py
git commit -m "feat: add Teamtailor ATS provider"
```

---

## Task 7: Homerun Provider

**Files:**
- Create: `src/jobhunt/providers/homerun.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create Homerun provider**

Create `src/jobhunt/providers/homerun.py`:

```python
from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class HomerunProvider:
    platform = ATSPlatform.HOMERUN

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.homerun.co/api/v1/jobs",
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("jobs", [])

        jobs: list[Job] = []
        for item in items:
            location = item.get("location", "")
            department = item.get("department", "")

            description = item.get("description", "")
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("published_at"):
                try:
                    created = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = str(item.get("id", item.get("slug", "")))
            url = item.get("url", item.get("application_url", f"https://{company.slug}.homerun.co/{job_id}"))

            jobs.append(Job(
                id=job_id,
                title=item.get("title", ""),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=item.get("employment_type"),
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.homerun import HomerunProvider

# Add to PROVIDERS dict:
ATSPlatform.HOMERUN: HomerunProvider(),
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/providers/homerun.py src/jobhunt/providers/__init__.py
git commit -m "feat: add Homerun ATS provider"
```

---

## Task 8: BambooHR Provider (Tier 2)

**Files:**
- Create: `src/jobhunt/providers/bamboohr.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create BambooHR provider**

Create `src/jobhunt/providers/bamboohr.py`:

```python
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
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.bamboohr import BambooHRProvider

# Add to PROVIDERS dict:
ATSPlatform.BAMBOOHR: BambooHRProvider(),
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/providers/bamboohr.py src/jobhunt/providers/__init__.py
git commit -m "feat: add BambooHR ATS provider"
```

---

## Task 9: Personio Provider (Tier 2)

**Files:**
- Create: `src/jobhunt/providers/personio.py`
- Modify: `src/jobhunt/providers/__init__.py`

- [ ] **Step 1: Create Personio provider**

Create `src/jobhunt/providers/personio.py`:

```python
from __future__ import annotations

from datetime import datetime

import httpx

from jobhunt.models import ATSPlatform, Company, Job, strip_html


class PersonioProvider:
    platform = ATSPlatform.PERSONIO

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        resp = await client.get(
            f"https://{company.slug}.jobs.personio.de/search.json",
        )
        resp.raise_for_status()
        data = resp.json()

        items = data if isinstance(data, list) else data.get("positions", data.get("jobs", []))
        if not isinstance(items, list):
            return []

        jobs: list[Job] = []
        for item in items:
            location = item.get("office", item.get("location", ""))
            department = item.get("department", "")
            schedule = item.get("schedule", item.get("employment_type", ""))

            description = item.get("description", item.get("jobDescription", ""))
            snippet = strip_html(description)[:200] if description else None

            created = None
            if item.get("createdAt"):
                try:
                    created = datetime.fromisoformat(str(item["createdAt"]).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            job_id = str(item.get("id", item.get("positionId", "")))
            slug_part = item.get("slug", job_id)
            url = item.get("url", f"https://{company.slug}.jobs.personio.de/job/{slug_part}")

            jobs.append(Job(
                id=job_id,
                title=item.get("name", item.get("title", "")),
                company=company.name,
                company_slug=company.slug,
                platform=self.platform,
                location=location or None,
                department=department or None,
                employment_type=schedule or None,
                url=url,
                created_at=created,
                is_remote="remote" in location.lower() if location else False,
                description_snippet=snippet,
            ))
        return jobs
```

- [ ] **Step 2: Register in provider registry**

Add to `src/jobhunt/providers/__init__.py`:

```python
from jobhunt.providers.personio import PersonioProvider

# Add to PROVIDERS dict:
ATSPlatform.PERSONIO: PersonioProvider(),
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/providers/personio.py src/jobhunt/providers/__init__.py
git commit -m "feat: add Personio ATS provider"
```

---

## Task 10: Discovery Sources Package — ATS Detector

**Files:**
- Create: `src/jobhunt/discovery_sources/__init__.py`
- Create: `src/jobhunt/discovery_sources/ats_detector.py`

- [ ] **Step 1: Create package init with source registry**

Create `src/jobhunt/discovery_sources/__init__.py`:

```python
"""Discovery source modules for finding companies across ATS platforms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from jobhunt.discovery import DiscoveredCompany


class DiscoverySourceProtocol(Protocol):
    name: str

    async def discover(self) -> list[DiscoveredCompany]:
        ...


@dataclass
class CareerPageEntry:
    """A company with a career page URL, before ATS detection."""

    company_name: str
    career_url: str
```

- [ ] **Step 2: Create ATS detector module**

Create `src/jobhunt/discovery_sources/ats_detector.py`:

```python
"""Detect which ATS a company uses by inspecting their career page HTML."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from jobhunt.discovery import DiscoveredCompany
from jobhunt.discovery_sources import CareerPageEntry
from jobhunt.models import ATSPlatform

logger = logging.getLogger(__name__)

# ATS detection patterns: (regex_pattern, platform, slug_extraction_regex)
_ATS_SIGNATURES: list[tuple[str, ATSPlatform, str]] = [
    (r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)", ATSPlatform.GREENHOUSE, r"boards\.greenhouse\.io/([a-zA-Z0-9_-]+)"),
    (r"jobs\.lever\.co/([a-zA-Z0-9_-]+)", ATSPlatform.LEVER, r"jobs\.lever\.co/([a-zA-Z0-9_-]+)"),
    (r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)", ATSPlatform.ASHBY, r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)"),
    (r"apply\.workable\.com/([a-zA-Z0-9_-]+)", ATSPlatform.WORKABLE, r"apply\.workable\.com/([a-zA-Z0-9_-]+)"),
    (r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)", ATSPlatform.SMARTRECRUITERS, r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_-]+)"),
    (r"([a-zA-Z0-9_-]+)\.teamtailor\.com", ATSPlatform.TEAMTAILOR, r"([a-zA-Z0-9_-]+)\.teamtailor\.com"),
    (r"([a-zA-Z0-9_-]+)\.bamboohr\.com/careers", ATSPlatform.BAMBOOHR, r"([a-zA-Z0-9_-]+)\.bamboohr\.com"),
    (r"([a-zA-Z0-9_-]+)\.jobs\.personio\.de", ATSPlatform.PERSONIO, r"([a-zA-Z0-9_-]+)\.jobs\.personio\.de"),
    (r"([a-zA-Z0-9_-]+)\.breezy\.hr", ATSPlatform.BREEZY, r"([a-zA-Z0-9_-]+)\.breezy\.hr"),
    (r"([a-zA-Z0-9_-]+)\.homerun\.co", ATSPlatform.HOMERUN, r"([a-zA-Z0-9_-]+)\.homerun\.co"),
    (r"([a-zA-Z0-9_-]+)\.recruitee\.com", ATSPlatform.RECRUITEE, r"([a-zA-Z0-9_-]+)\.recruitee\.com"),
    (r"myworkdaysite\.com|myworkday\.com", ATSPlatform.WORKDAY, r"([a-zA-Z0-9_-]+)\.(?:wd\d+\.)?myworkday"),
    (r"icims\.com", ATSPlatform.ICIMS, r"careers[.-]([a-zA-Z0-9_-]+)\.icims\.com"),
]


async def detect_ats(
    client: httpx.AsyncClient,
    entry: CareerPageEntry,
) -> DiscoveredCompany | None:
    """Fetch a career page and detect which ATS it uses."""
    try:
        resp = await client.get(entry.career_url, timeout=15.0, follow_redirects=True)
        html = resp.text
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", entry.career_url, e)
        return None

    for pattern, platform, slug_pattern in _ATS_SIGNATURES:
        if re.search(pattern, html):
            slug_match = re.search(slug_pattern, html)
            if slug_match:
                slug = slug_match.group(1).lower()
                return DiscoveredCompany(
                    slug=slug,
                    name=entry.company_name,
                    platform=platform,
                )
    return None


async def detect_ats_batch(
    entries: list[CareerPageEntry],
    max_concurrent: int = 30,
) -> list[DiscoveredCompany]:
    """Detect ATS for a batch of career page entries."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[DiscoveredCompany] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        async def detect_one(entry: CareerPageEntry) -> None:
            async with semaphore:
                result = await detect_ats(client, entry)
                if result:
                    results.append(result)

        await asyncio.gather(*[detect_one(e) for e in entries])

    return results
```

- [ ] **Step 3: Commit**

```bash
git add src/jobhunt/discovery_sources/__init__.py src/jobhunt/discovery_sources/ats_detector.py
git commit -m "feat: add ATS detector — detect company ATS from career page HTML"
```

---

## Task 11: Discovery Sources — GitHub Awesome Lists

**Files:**
- Create: `src/jobhunt/discovery_sources/github_lists.py`

- [ ] **Step 1: Create GitHub lists parser**

Create `src/jobhunt/discovery_sources/github_lists.py`:

```python
"""Parse GitHub awesome-lists to find companies and their career pages."""

from __future__ import annotations

import logging
import re

import httpx

from jobhunt.discovery import DiscoveredCompany
from jobhunt.discovery_sources import CareerPageEntry
from jobhunt.discovery_sources.ats_detector import detect_ats_batch

logger = logging.getLogger(__name__)

# GitHub repos with company lists (raw markdown URLs)
_GITHUB_SOURCES = [
    {
        "name": "remoteintech/remote-jobs",
        "url": "https://raw.githubusercontent.com/remoteintech/remote-jobs/main/README.md",
        "parser": "markdown_table",
    },
    {
        "name": "poteto/hiring-without-whiteboards",
        "url": "https://raw.githubusercontent.com/poteto/hiring-without-whiteboards/master/README.md",
        "parser": "markdown_links",
    },
]


def _parse_markdown_table(text: str) -> list[CareerPageEntry]:
    """Extract company names and URLs from markdown table rows."""
    entries: list[CareerPageEntry] = []
    # Match table rows: | [Name](url) | ... | or | Name | url | ...
    for match in re.finditer(r"\|\s*\[([^\]]+)\]\(([^)]+)\)", text):
        name, url = match.group(1).strip(), match.group(2).strip()
        if url.startswith("http") and "github.com" not in url:
            entries.append(CareerPageEntry(company_name=name, career_url=url))
    return entries


def _parse_markdown_links(text: str) -> list[CareerPageEntry]:
    """Extract company names and URLs from markdown links in lists."""
    entries: list[CareerPageEntry] = []
    # Match list items: - [Name](url) or * [Name](url)
    for match in re.finditer(r"[-*]\s+\[([^\]]+)\]\(([^)]+)\)", text):
        name, url = match.group(1).strip(), match.group(2).strip()
        if url.startswith("http") and "github.com" not in url:
            entries.append(CareerPageEntry(company_name=name, career_url=url))
    return entries


_PARSERS = {
    "markdown_table": _parse_markdown_table,
    "markdown_links": _parse_markdown_links,
}


async def discover_from_github_lists(
    max_concurrent: int = 30,
) -> list[DiscoveredCompany]:
    """Fetch GitHub awesome-lists, extract career pages, detect ATS platforms."""
    all_entries: list[CareerPageEntry] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        for source in _GITHUB_SOURCES:
            try:
                resp = await client.get(source["url"])
                resp.raise_for_status()
                parser = _PARSERS.get(source["parser"], _parse_markdown_links)
                entries = parser(resp.text)
                logger.info("Parsed %d entries from %s", len(entries), source["name"])
                all_entries.extend(entries)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", source["name"], e)

    if not all_entries:
        return []

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique: list[CareerPageEntry] = []
    for entry in all_entries:
        if entry.career_url not in seen_urls:
            seen_urls.add(entry.career_url)
            unique.append(entry)

    logger.info("Detecting ATS for %d unique career pages", len(unique))
    return await detect_ats_batch(unique, max_concurrent=max_concurrent)
```

- [ ] **Step 2: Commit**

```bash
git add src/jobhunt/discovery_sources/github_lists.py
git commit -m "feat: add GitHub awesome-lists discovery source"
```

---

## Task 12: Discovery Sources — Community Aggregators

**Files:**
- Create: `src/jobhunt/discovery_sources/aggregators.py`

- [ ] **Step 1: Create aggregators module**

Create `src/jobhunt/discovery_sources/aggregators.py`:

```python
"""Parse community aggregators (HN Who's Hiring, YC directory) for companies."""

from __future__ import annotations

import logging
import re

import httpx

from jobhunt.discovery import DiscoveredCompany
from jobhunt.discovery_sources import CareerPageEntry
from jobhunt.discovery_sources.ats_detector import detect_ats_batch

logger = logging.getLogger(__name__)


async def _fetch_hn_whos_hiring(client: httpx.AsyncClient) -> list[CareerPageEntry]:
    """Fetch the latest HN 'Who is Hiring?' thread and extract company career URLs."""
    # Search HN Algolia API for latest "Who is hiring" thread
    resp = await client.get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "query": "Ask HN: Who is hiring?",
            "tags": "story",
            "hitsPerPage": 1,
        },
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", [])
    if not hits:
        return []

    story_id = hits[0].get("objectID", "")
    if not story_id:
        return []

    # Fetch comments for this story
    resp = await client.get(
        f"https://hn.algolia.com/api/v1/items/{story_id}",
    )
    resp.raise_for_status()
    story = resp.json()

    entries: list[CareerPageEntry] = []
    for child in story.get("children", []):
        text = child.get("text", "")
        if not text:
            continue

        # Extract company name from first line (usually "Company Name | Location | ...")
        first_line = text.split("<p>")[0] if "<p>" in text else text.split("\n")[0]
        # Strip HTML
        company_name = re.sub(r"<[^>]+>", "", first_line).split("|")[0].strip()

        # Extract URLs from comment
        urls = re.findall(r'href="(https?://[^"]+)"', text)
        career_url = ""
        for url in urls:
            if any(kw in url.lower() for kw in ["career", "jobs", "hiring", "work", "apply", "openings"]):
                career_url = url
                break
        if not career_url and urls:
            career_url = urls[0]

        if company_name and career_url:
            entries.append(CareerPageEntry(company_name=company_name[:100], career_url=career_url))

    return entries


async def _fetch_yc_companies(client: httpx.AsyncClient) -> list[CareerPageEntry]:
    """Fetch Y Combinator company directory."""
    resp = await client.get(
        "https://api.ycombinator.com/v0.1/companies",
        params={"page": 1, "batch": ""},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()

    companies = data.get("companies", [])
    entries: list[CareerPageEntry] = []

    for co in companies:
        name = co.get("name", "")
        url = co.get("url", "")
        # Prefer jobs URL if available
        jobs_url = co.get("jobs_url", "")
        career_url = jobs_url or url
        if name and career_url and career_url.startswith("http"):
            entries.append(CareerPageEntry(company_name=name, career_url=career_url))

    return entries


async def discover_from_aggregators(
    max_concurrent: int = 30,
) -> list[DiscoveredCompany]:
    """Run all aggregator sources and detect ATS platforms."""
    all_entries: list[CareerPageEntry] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        # Fetch HN Who's Hiring
        try:
            hn_entries = await _fetch_hn_whos_hiring(client)
            logger.info("Found %d entries from HN Who's Hiring", len(hn_entries))
            all_entries.extend(hn_entries)
        except Exception as e:
            logger.warning("Failed to fetch HN Who's Hiring: %s", e)

        # Fetch YC companies
        try:
            yc_entries = await _fetch_yc_companies(client)
            logger.info("Found %d entries from YC directory", len(yc_entries))
            all_entries.extend(yc_entries)
        except Exception as e:
            logger.warning("Failed to fetch YC directory: %s", e)

    if not all_entries:
        return []

    # Deduplicate by URL
    seen: set[str] = set()
    unique: list[CareerPageEntry] = []
    for entry in all_entries:
        if entry.career_url not in seen:
            seen.add(entry.career_url)
            unique.append(entry)

    logger.info("Detecting ATS for %d unique career pages from aggregators", len(unique))
    return await detect_ats_batch(unique, max_concurrent=max_concurrent)
```

- [ ] **Step 2: Commit**

```bash
git add src/jobhunt/discovery_sources/aggregators.py
git commit -m "feat: add HN Who's Hiring and YC directory aggregator sources"
```

---

## Task 13: Enhanced Perplexity Discovery

**Files:**
- Modify: `src/jobhunt/perplexity.py`

- [ ] **Step 1: Add industry-specific discovery**

Add to `src/jobhunt/perplexity.py` after the existing `_REGION_HINTS` dict:

```python
_INDUSTRIES = [
    "tech", "fintech", "healthtech", "e-commerce", "SaaS",
    "cybersecurity", "AI/ML", "biotech", "logistics", "edtech",
]


async def discover_via_perplexity_deep(
    platforms: list[ATSPlatform] | None = None,
    region: str | None = None,
    industries: list[str] | None = None,
    count_per_query: int = 50,
    model: str = "sonar",
    api_key: str | None = None,
    exclude_slugs: set[str] | None = None,
) -> list[PerplexityCandidate]:
    """Enhanced discovery with industry-specific queries and iterative deepening.

    Queries Perplexity for each platform × industry combination,
    then does a follow-up "more like these" query excluding already-found slugs.
    """
    key = api_key or _get_api_key()
    target_platforms = platforms or list(ATSPlatform)
    target_industries = industries or _INDUSTRIES
    all_candidates: list[PerplexityCandidate] = []
    seen: set[tuple[str, str]] = set()
    excluded = exclude_slugs or set()

    for plat in target_platforms:
        platform_hint = _PLATFORM_HINTS.get(plat, f"companies using {plat.value} ATS")
        region_hint = _REGION_HINTS.get(region, "") if region else ""

        for industry in target_industries:
            prompt = (
                f"List {count_per_query} {industry} {platform_hint} "
                f"{region_hint} "
                f"Only include companies you are confident about. "
                f"The slug should be lowercase, using hyphens not spaces."
            ).strip()

            if excluded:
                sample = list(excluded)[:20]
                prompt += f" Exclude these already-known slugs: {', '.join(sample)}."

            try:
                result = await query_perplexity(prompt, model=model, api_key=key)
            except Exception as e:
                logger.warning("Perplexity query failed for %s/%s: %s", plat.value, industry, e)
                continue

            for c in result.get("companies", []):
                name = c.get("name", "").strip()
                slug = c.get("slug", "").strip().lower().replace(" ", "-")
                if not name or not slug:
                    continue
                if slug in excluded:
                    continue

                dedup_key = (plat.value, slug)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                all_candidates.append(
                    PerplexityCandidate(
                        name=name,
                        slug=slug,
                        platform=plat,
                        source_query=f"{industry}/{plat.value}",
                    )
                )

    return all_candidates
```

- [ ] **Step 2: Commit**

```bash
git add src/jobhunt/perplexity.py
git commit -m "feat: add industry-aware Perplexity discovery with iterative deepening"
```

---

## Task 14: Update CLI — New Discovery Sources

**Files:**
- Modify: `src/jobhunt/cli.py:120-184` (discover command + _discover_perplexity)

- [ ] **Step 1: Update discover command to handle new sources**

Replace the `discover` command in `src/jobhunt/cli.py` with expanded source handling. The `--source` option now accepts: `perplexity`, `perplexity-deep`, `github-lists`, `aggregators`, `detect`, `all`, or a custom CSV URL.

Update the `source` parameter help text and add routing:

```python
@app.command()
def discover(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Filter by region: eu, us, uk, remote"),
    platform: Optional[list[ATSPlatform]] = typer.Option(None, "--platform", "-p", help="Only discover for specific ATS platforms"),
    source: Optional[str] = typer.Option(None, "--source", help="Source: perplexity, perplexity-deep, github-lists, aggregators, detect, all, or a CSV URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be added without saving"),
    skip_validation: bool = typer.Option(False, "--skip-validation", help="Skip slug validation (faster, may include dead slugs)"),
    concurrency: int = typer.Option(50, "--concurrency", help="Max concurrent requests"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max companies to discover"),
    urls_file: Optional[Path] = typer.Option(None, "--urls", help="File with career page URLs (one per line) for --source detect"),
) -> None:
    """Auto-discover companies from community sources, Perplexity AI, GitHub lists, or aggregators."""
    db = CompanyDB()
    existing_keys = db.get_all_keys()

    if source == "perplexity":
        _discover_perplexity(
            region=region, platform=platform, dry_run=dry_run,
            skip_validation=skip_validation, concurrency=concurrency,
            limit=limit, db=db, existing_keys=existing_keys,
        )
        return

    if source == "perplexity-deep":
        _discover_perplexity_deep(
            region=region, platform=platform, dry_run=dry_run,
            skip_validation=skip_validation, concurrency=concurrency,
            limit=limit, db=db, existing_keys=existing_keys,
        )
        return

    if source in ("github-lists", "aggregators", "detect", "all"):
        _discover_new_sources(
            source=source, region=region, platform=platform,
            dry_run=dry_run, skip_validation=skip_validation,
            concurrency=concurrency, limit=limit, db=db,
            existing_keys=existing_keys, urls_file=urls_file,
        )
        return

    # Default: Stapply CSV or custom URL
    from jobhunt.discovery import DEFAULT_SOURCES, DiscoverySource, discover as run_discover

    sources = DEFAULT_SOURCES
    if source:
        sources = [DiscoverySource(name="Custom", url=source)]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching company lists from sources...", total=None)

        def on_progress(stage: str, current: int, total: int) -> None:
            if stage == "fetch":
                progress.update(task, description="Fetching company lists from sources...")
            elif stage == "validate":
                progress.update(task, description=f"Validating slugs ({current}/{total})...")
            elif stage == "region":
                progress.update(task, description=f"Probing regions ({current}/{total})...")

        discovered = asyncio.run(
            run_discover(
                sources=sources, platforms=platform or None,
                region=region, max_concurrent=concurrency,
                existing_keys=existing_keys, on_progress=on_progress,
                skip_validation=skip_validation,
            )
        )

    if limit:
        discovered = discovered[:limit]

    _display_and_save_discovered(discovered, region, dry_run, db, existing_keys)
```

- [ ] **Step 2: Add _discover_new_sources helper**

Add this new function after `_discover_perplexity` in `src/jobhunt/cli.py`:

```python
def _discover_perplexity_deep(
    region: Optional[str],
    platform: Optional[list[ATSPlatform]],
    dry_run: bool,
    skip_validation: bool,
    concurrency: int,
    limit: Optional[int],
    db: CompanyDB,
    existing_keys: set[tuple[str, str]],
) -> None:
    """Discover companies using enhanced Perplexity AI with industry-specific queries."""
    from jobhunt.perplexity import discover_via_perplexity_deep
    from jobhunt.discovery import DiscoveredCompany, validate_slug

    exclude_slugs = {slug for _, slug in existing_keys}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Querying Perplexity AI (deep discovery)...", total=None)

        candidates = asyncio.run(
            discover_via_perplexity_deep(
                platforms=platform or None,
                region=region,
                exclude_slugs=exclude_slugs,
            )
        )

        progress.update(task, description=f"Found {len(candidates)} candidates from Perplexity (deep)")

    if not candidates:
        console.print("[yellow]No companies found via Perplexity deep discovery.[/yellow]")
        return

    new_candidates = [
        c for c in candidates
        if (c.platform.value, c.slug) not in existing_keys
    ]

    if not new_candidates:
        console.print("[yellow]All discovered companies are already in the database.[/yellow]")
        return

    console.print(f"[green]Deep discovery found {len(new_candidates)} new candidates[/green]")

    discovered = [
        DiscoveredCompany(
            slug=c.slug, name=c.name, platform=c.platform,
            region_tags=[region] if region else ["discovered"],
        )
        for c in new_candidates
    ]

    if not skip_validation:
        import httpx as httpx_mod

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            total = len(discovered)
            task = progress.add_task(f"Validating {total} slugs...", total=None)
            validated_count = 0

            async def validate_all() -> None:
                nonlocal validated_count
                semaphore = asyncio.Semaphore(min(concurrency, 20))
                async with httpx_mod.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                    async def validate_one(c: DiscoveredCompany) -> None:
                        nonlocal validated_count
                        await validate_slug(client, semaphore, c)
                        validated_count += 1
                        progress.update(task, description=f"Validating slugs ({validated_count}/{total})...")

                    await asyncio.gather(*[validate_one(c) for c in discovered])

            asyncio.run(validate_all())

        valid_before = len(discovered)
        discovered = [c for c in discovered if c.valid]
        console.print(f"[dim]Validation: {len(discovered)}/{valid_before} slugs confirmed valid[/dim]")

    if limit:
        discovered = discovered[:limit]

    _display_and_save_discovered(discovered, region, dry_run, db, existing_keys)


def _discover_new_sources(
    source: str,
    region: Optional[str],
    platform: Optional[list[ATSPlatform]],
    dry_run: bool,
    skip_validation: bool,
    concurrency: int,
    limit: Optional[int],
    db: CompanyDB,
    existing_keys: set[tuple[str, str]],
    urls_file: Optional[Path] = None,
) -> None:
    """Discover companies from GitHub lists, aggregators, or ATS detection."""
    from jobhunt.discovery import DiscoveredCompany, validate_slug

    all_discovered: list[DiscoveredCompany] = []

    async def run_sources() -> list[DiscoveredCompany]:
        results: list[DiscoveredCompany] = []

        if source in ("github-lists", "all"):
            from jobhunt.discovery_sources.github_lists import discover_from_github_lists
            try:
                found = await discover_from_github_lists(max_concurrent=concurrency)
                console.print(f"[dim]GitHub lists: {len(found)} companies detected[/dim]")
                results.extend(found)
            except Exception as e:
                console.print(f"[yellow]GitHub lists failed: {e}[/yellow]")

        if source in ("aggregators", "all"):
            from jobhunt.discovery_sources.aggregators import discover_from_aggregators
            try:
                found = await discover_from_aggregators(max_concurrent=concurrency)
                console.print(f"[dim]Aggregators: {len(found)} companies detected[/dim]")
                results.extend(found)
            except Exception as e:
                console.print(f"[yellow]Aggregators failed: {e}[/yellow]")

        if source in ("detect", "all"):
            if urls_file and urls_file.exists():
                from jobhunt.discovery_sources import CareerPageEntry
                from jobhunt.discovery_sources.ats_detector import detect_ats_batch
                entries = []
                for line in urls_file.read_text().strip().split("\n"):
                    line = line.strip()
                    if line and line.startswith("http"):
                        # Try to extract company name from URL
                        name = line.split("//")[1].split("/")[0].split(".")[0]
                        entries.append(CareerPageEntry(company_name=name, career_url=line))
                if entries:
                    found = await detect_ats_batch(entries, max_concurrent=concurrency)
                    console.print(f"[dim]ATS detection: {len(found)} companies detected from {len(entries)} URLs[/dim]")
                    results.extend(found)
            elif source == "detect":
                console.print("[yellow]--urls file required for 'detect' source[/yellow]")

        return results

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Running discovery source: {source}...", total=None)
        all_discovered = asyncio.run(run_sources())

    if not all_discovered:
        console.print("[yellow]No companies discovered from selected sources.[/yellow]")
        return

    # Filter by platform
    if platform:
        all_discovered = [c for c in all_discovered if c.platform in platform]

    # Deduplicate against existing
    all_discovered = [
        c for c in all_discovered
        if (c.platform.value, c.slug) not in existing_keys
    ]

    # Deduplicate within results
    seen: set[tuple[str, str]] = set()
    unique: list[DiscoveredCompany] = []
    for c in all_discovered:
        key = (c.platform.value, c.slug)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    all_discovered = unique

    console.print(f"[green]Found {len(all_discovered)} new unique companies[/green]")

    # Validate if needed
    if not skip_validation and all_discovered:
        import httpx as httpx_mod

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            total = len(all_discovered)
            task = progress.add_task(f"Validating {total} slugs...", total=None)
            validated_count = 0

            async def validate_all() -> None:
                nonlocal validated_count
                semaphore = asyncio.Semaphore(min(concurrency, 20))
                async with httpx_mod.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                    async def validate_one(c: DiscoveredCompany) -> None:
                        nonlocal validated_count
                        await validate_slug(client, semaphore, c)
                        validated_count += 1
                        progress.update(task, description=f"Validating slugs ({validated_count}/{total})...")

                    await asyncio.gather(*[validate_one(c) for c in all_discovered])

            asyncio.run(validate_all())

        valid_before = len(all_discovered)
        all_discovered = [c for c in all_discovered if c.valid]
        console.print(f"[dim]Validation: {len(all_discovered)}/{valid_before} slugs confirmed valid[/dim]")

    if limit:
        all_discovered = all_discovered[:limit]

    _display_and_save_discovered(all_discovered, region, dry_run, db, existing_keys)
```

- [ ] **Step 3: Update CLI help text**

Update the `app` Typer help string in `src/jobhunt/cli.py:19`:

```python
app = typer.Typer(help="Search for jobs across ATS platforms (Greenhouse, Lever, Ashby, Rippling, Recruitee, Workable, SmartRecruiters, JazzHR, Breezy, Teamtailor, Homerun, BambooHR, Personio, and more)")
```

- [ ] **Step 4: Add Path import if missing**

Ensure `from pathlib import Path` is imported at the top of `src/jobhunt/cli.py` (already exists on line 3).

- [ ] **Step 5: Verify CLI loads without errors**

Run: `python -m jobhunt.cli --help`
Expected: Shows help with updated description

Run: `python -m jobhunt.cli discover --help`
Expected: Shows `--source` with new options listed, `--urls` option present

- [ ] **Step 6: Commit**

```bash
git add src/jobhunt/cli.py
git commit -m "feat: add github-lists, aggregators, detect, perplexity-deep discovery sources to CLI"
```

---

## Task 15: Final Provider Registry Update + Verification

**Files:**
- Modify: `src/jobhunt/providers/__init__.py` (ensure all 13 providers registered)

- [ ] **Step 1: Verify final __init__.py has all providers**

The final `src/jobhunt/providers/__init__.py` should look like:

```python
from __future__ import annotations

from jobhunt.models import ATSPlatform
from jobhunt.providers.ashby import AshbyProvider
from jobhunt.providers.bamboohr import BambooHRProvider
from jobhunt.providers.base import ATSProvider
from jobhunt.providers.breezy import BreezyProvider
from jobhunt.providers.greenhouse import GreenhouseProvider
from jobhunt.providers.homerun import HomerunProvider
from jobhunt.providers.jazzhr import JazzHRProvider
from jobhunt.providers.lever import LeverProvider
from jobhunt.providers.personio import PersonioProvider
from jobhunt.providers.recruitee import RecruiteeProvider
from jobhunt.providers.rippling import RipplingProvider
from jobhunt.providers.smartrecruiters import SmartRecruitersProvider
from jobhunt.providers.teamtailor import TeamtailorProvider
from jobhunt.providers.workable import WorkableProvider

PROVIDERS: dict[ATSPlatform, ATSProvider] = {
    ATSPlatform.GREENHOUSE: GreenhouseProvider(),
    ATSPlatform.LEVER: LeverProvider(),
    ATSPlatform.ASHBY: AshbyProvider(),
    ATSPlatform.RIPPLING: RipplingProvider(),
    ATSPlatform.RECRUITEE: RecruiteeProvider(),
    ATSPlatform.WORKABLE: WorkableProvider(),
    ATSPlatform.SMARTRECRUITERS: SmartRecruitersProvider(),
    ATSPlatform.JAZZHR: JazzHRProvider(),
    ATSPlatform.BREEZY: BreezyProvider(),
    ATSPlatform.TEAMTAILOR: TeamtailorProvider(),
    ATSPlatform.HOMERUN: HomerunProvider(),
    ATSPlatform.BAMBOOHR: BambooHRProvider(),
    ATSPlatform.PERSONIO: PersonioProvider(),
}

__all__ = ["PROVIDERS", "ATSProvider"]
```

Note: Workday, iCIMS, Taleo, SuccessFactors are NOT registered — they have enum values but no providers yet (Wave 4).

- [ ] **Step 2: Run full verification**

```bash
# All imports work
python -c "from jobhunt.providers import PROVIDERS; print(f'{len(PROVIDERS)} providers registered'); [print(f'  {k}: {type(v).__name__}') for k, v in PROVIDERS.items()]"

# CLI lists all platforms
python -m jobhunt.cli platforms

# Discovery sources import
python -c "from jobhunt.discovery_sources.github_lists import discover_from_github_lists; print('github_lists OK')"
python -c "from jobhunt.discovery_sources.aggregators import discover_from_aggregators; print('aggregators OK')"
python -c "from jobhunt.discovery_sources.ats_detector import detect_ats_batch; print('ats_detector OK')"
python -c "from jobhunt.perplexity import discover_via_perplexity_deep; print('perplexity_deep OK')"
```

Expected: 13 providers registered, 17 platforms listed, all imports succeed

- [ ] **Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: complete database expansion — 13 providers, 4 discovery sources, 17 platforms"
```

---

## Verification Plan

### Quick Smoke Tests (no API keys needed)

```bash
# All providers load
python -c "from jobhunt.providers import PROVIDERS; print(len(PROVIDERS))"
# Expected: 13

# All platforms listed
python -m jobhunt.cli platforms
# Expected: 17 platforms

# CLI help shows new options
python -m jobhunt.cli discover --help
# Expected: source options include github-lists, aggregators, detect, perplexity-deep, all

# Discovery sources import cleanly
python -c "from jobhunt.discovery_sources.ats_detector import detect_ats_batch; print('OK')"
python -c "from jobhunt.discovery_sources.github_lists import discover_from_github_lists; print('OK')"
python -c "from jobhunt.discovery_sources.aggregators import discover_from_aggregators; print('OK')"
```

### Live Tests (requires network)

```bash
# Discover from GitHub lists (free, no API key)
python -m jobhunt.cli discover --source github-lists --dry-run --limit 10

# Discover from HN/YC aggregators (free, no API key)
python -m jobhunt.cli discover --source aggregators --dry-run --limit 10

# Search on new platform (needs companies in DB first)
python -m jobhunt.cli companies add workable some-company --name "Test Company"
python -m jobhunt.cli search "engineer" --platform workable
```

### Perplexity Tests (requires PERPLEXITY_API_KEY)

```bash
# Basic Perplexity for new platforms
export PERPLEXITY_API_KEY=pplx-xxx
python -m jobhunt.cli discover --source perplexity --platform workable --dry-run

# Deep discovery with industries
python -m jobhunt.cli discover --source perplexity-deep --platform teamtailor --region eu --dry-run
```

---

## Deferred: Wave 4 — Enterprise Platforms

Workday, iCIMS, Taleo, and SuccessFactors have enum values but **no providers registered**. These require dedicated research:

- **Workday:** Each company uses `{company}.wd{N}.myworkdaysite.com` — need to map company → subdomain + site ID
- **iCIMS:** URL patterns vary: `careers-{slug}.icims.com` vs `jobs-{slug}.icims.com`
- **Taleo:** Oracle legacy system with XML-heavy APIs and multiple hosting zones
- **SuccessFactors:** SAP system with complex auth and varied deployment patterns

These will be a separate implementation plan after API research confirms viable integration approaches.
