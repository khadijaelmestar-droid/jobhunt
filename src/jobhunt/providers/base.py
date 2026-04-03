from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from jobhunt.models import ATSPlatform, Company, Job


@runtime_checkable
class ATSProvider(Protocol):
    platform: ATSPlatform

    async def fetch_jobs(self, client: httpx.AsyncClient, company: Company) -> list[Job]:
        """Fetch all jobs for a company from this ATS platform."""
        ...
