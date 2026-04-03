from __future__ import annotations

from jobhunt.models import ATSPlatform
from jobhunt.providers.ashby import AshbyProvider
from jobhunt.providers.base import ATSProvider
from jobhunt.providers.greenhouse import GreenhouseProvider
from jobhunt.providers.lever import LeverProvider
from jobhunt.providers.recruitee import RecruiteeProvider
from jobhunt.providers.rippling import RipplingProvider

PROVIDERS: dict[ATSPlatform, ATSProvider] = {
    ATSPlatform.GREENHOUSE: GreenhouseProvider(),
    ATSPlatform.LEVER: LeverProvider(),
    ATSPlatform.ASHBY: AshbyProvider(),
    ATSPlatform.RIPPLING: RipplingProvider(),
    ATSPlatform.RECRUITEE: RecruiteeProvider(),
}

__all__ = ["PROVIDERS", "ATSProvider"]
