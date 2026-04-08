"""Discovery source modules for finding companies across ATS platforms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CareerPageEntry:
    """A company with a career page URL, before ATS detection."""

    company_name: str
    career_url: str
