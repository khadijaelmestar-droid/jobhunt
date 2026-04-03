from __future__ import annotations

import importlib.resources
import json
import os
from pathlib import Path

from jobhunt.models import ATSPlatform, Company, CompanyDatabase


def _user_db_path() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(config) / "jobhunt" / "companies.json"


def _builtin_db_path() -> Path:
    return Path(importlib.resources.files("jobhunt")) / "data" / "companies.json"  # type: ignore[arg-type]


class CompanyDB:
    def __init__(self) -> None:
        self.builtin_path = _builtin_db_path()
        self.user_path = _user_db_path()

    def _load(self, path: Path) -> CompanyDatabase:
        if not path.exists():
            return CompanyDatabase()
        try:
            data = json.loads(path.read_text())
            return CompanyDatabase.model_validate(data)
        except Exception:
            return CompanyDatabase()

    def _save_user(self, db: CompanyDatabase) -> None:
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_path.write_text(db.model_dump_json(indent=2))

    def get_all(
        self,
        platform: ATSPlatform | None = None,
        tags: list[str] | None = None,
    ) -> list[Company]:
        builtin = self._load(self.builtin_path)
        user = self._load(self.user_path)

        # User entries override built-in by (platform, slug)
        by_key: dict[tuple[str, str], Company] = {}
        for c in builtin.companies:
            by_key[(c.platform, c.slug)] = c
        for c in user.companies:
            by_key[(c.platform, c.slug)] = c

        companies = [c for c in by_key.values() if c.enabled]

        if platform:
            companies = [c for c in companies if c.platform == platform]
        if tags:
            tag_set = set(t.lower() for t in tags)
            companies = [c for c in companies if tag_set & set(t.lower() for t in c.tags)]

        return sorted(companies, key=lambda c: (c.platform, c.name.lower()))

    def add(self, company: Company) -> None:
        db = self._load(self.user_path)
        # Remove existing with same key
        db.companies = [c for c in db.companies if not (c.platform == company.platform and c.slug == company.slug)]
        db.companies.append(company)
        self._save_user(db)

    def remove(self, platform: ATSPlatform, slug: str) -> bool:
        db = self._load(self.user_path)
        before = len(db.companies)
        db.companies = [c for c in db.companies if not (c.platform == platform and c.slug == slug)]
        if len(db.companies) < before:
            self._save_user(db)
            return True
        return False

    def get_all_keys(self) -> set[tuple[str, str]]:
        """Return set of (platform_value, slug) for all known companies."""
        builtin = self._load(self.builtin_path)
        user = self._load(self.user_path)
        return {(c.platform.value, c.slug) for c in builtin.companies} | {
            (c.platform.value, c.slug) for c in user.companies
        }

    def bulk_add(self, companies: list[Company]) -> int:
        """Add multiple companies to user DB, skipping duplicates. Returns count added."""
        db = self._load(self.user_path)
        existing = {(c.platform, c.slug) for c in db.companies}
        # Also check built-in
        builtin = self._load(self.builtin_path)
        existing |= {(c.platform, c.slug) for c in builtin.companies}

        count = 0
        for c in companies:
            key = (c.platform, c.slug)
            if key not in existing:
                db.companies.append(c)
                existing.add(key)
                count += 1
        if count:
            self._save_user(db)
        return count

    def import_from_file(self, path: Path) -> int:
        data = json.loads(path.read_text())
        imported = CompanyDatabase.model_validate(data)
        db = self._load(self.user_path)
        existing = {(c.platform, c.slug) for c in db.companies}
        count = 0
        for c in imported.companies:
            if (c.platform, c.slug) not in existing:
                db.companies.append(c)
                count += 1
        self._save_user(db)
        return count
