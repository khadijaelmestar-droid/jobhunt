from __future__ import annotations

from jobhunt.models import ATSPlatform
from jobhunt.providers.ashby import AshbyProvider
from jobhunt.providers.base import ATSProvider
from jobhunt.providers.breezy import BreezyProvider
from jobhunt.providers.greenhouse import GreenhouseProvider
from jobhunt.providers.homerun import HomerunProvider
from jobhunt.providers.jazzhr import JazzHRProvider
from jobhunt.providers.lever import LeverProvider
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
}

__all__ = ["PROVIDERS", "ATSProvider"]
