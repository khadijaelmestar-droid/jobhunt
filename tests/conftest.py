from __future__ import annotations

from datetime import datetime

import pytest

from jobhunt.models import ATSPlatform, Job


@pytest.fixture
def tmp_cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def sample_jobs() -> list[Job]:
    return [
        Job(
            id="1001",
            title="Backend Engineer",
            company="Acme Corp",
            company_slug="acme",
            platform=ATSPlatform.GREENHOUSE,
            location="Remote",
            url="https://boards.greenhouse.io/acme/jobs/1001",
            is_remote=True,
            created_at=datetime(2026, 4, 1),
        ),
        Job(
            id="2002",
            title="Frontend Developer",
            company="Beta Inc",
            company_slug="beta",
            platform=ATSPlatform.LEVER,
            location="New York, NY",
            url="https://jobs.lever.co/beta/2002",
            is_remote=False,
            created_at=datetime(2026, 4, 2),
        ),
        Job(
            id="3003",
            title="DevOps Engineer",
            company="Gamma LLC",
            company_slug="gamma",
            platform=ATSPlatform.ASHBY,
            location="Berlin, Germany",
            url="https://jobs.ashbyhq.com/gamma/3003",
            is_remote=False,
            created_at=datetime(2026, 4, 3),
        ),
    ]
