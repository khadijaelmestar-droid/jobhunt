from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


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
    LINKEDIN = "linkedin"


class Job(BaseModel):
    id: str
    title: str
    company: str
    company_slug: str
    platform: ATSPlatform
    location: str | None = None
    department: str | None = None
    team: str | None = None
    employment_type: str | None = None
    url: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_remote: bool = False
    description_snippet: str | None = None


class Company(BaseModel):
    slug: str
    name: str
    platform: ATSPlatform
    tags: list[str] = []
    enabled: bool = True
    base_url: str | None = None


class CompanyDatabase(BaseModel):
    version: int = 1
    companies: list[Company] = []


class SearchQuery(BaseModel):
    keywords: list[str] = []
    location: str | None = None
    remote_only: bool = False
    platforms: list[ATSPlatform] | None = None
    tags: list[str] = []
    department: str | None = None


def strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
