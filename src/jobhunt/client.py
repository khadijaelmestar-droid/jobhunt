from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx

from jobhunt.models import ATSPlatform, Company, Job
from jobhunt.providers.base import ATSProvider

logger = logging.getLogger(__name__)


class JobhuntClient:
    def __init__(self, max_concurrent: int = 20, timeout: float = 15.0, max_retries: int = 3):
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch_all(
        self,
        companies: list[Company],
        providers: dict[ATSPlatform, ATSProvider],
        on_progress: Callable[[Company, bool], None] | None = None,
    ) -> list[Job]:
        semaphore = asyncio.Semaphore(self.max_concurrent)
        all_jobs: list[Job] = []
        lock = asyncio.Lock()

        async def fetch_one(client: httpx.AsyncClient, company: Company) -> None:
            provider = providers.get(company.platform)
            if not provider:
                return

            async with semaphore:
                jobs = await self._fetch_with_retry(client, provider, company)

            async with lock:
                all_jobs.extend(jobs)
            if on_progress:
                on_progress(company, len(jobs) > 0)

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            tasks = [fetch_one(client, c) for c in companies]
            await asyncio.gather(*tasks)

        return all_jobs

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        provider: ATSProvider,
        company: Company,
    ) -> list[Job]:
        for attempt in range(self.max_retries):
            try:
                return await provider.fetch_jobs(client, company)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                logger.debug("HTTP %s for %s/%s: %s", e.response.status_code, company.platform, company.slug, e)
                return []
            except (httpx.RequestError, Exception) as e:
                logger.debug("Error fetching %s/%s: %s", company.platform, company.slug, e)
                return []
        return []
