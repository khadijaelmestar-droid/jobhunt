from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from pathlib import Path

from jobhunt.models import ATSPlatform, Job


def _cache_dir() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return Path(cache) / "jobhunt"


class JobCache:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl = ttl_seconds
        self.cache_dir = _cache_dir()

    def _key(self, platform: ATSPlatform, slug: str) -> str:
        raw = f"{platform}:{slug}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json.gz"

    def _read_raw(self, platform: ATSPlatform, slug: str) -> dict | None:
        """Read cache file and return parsed dict with 'fetched_at' and 'jobs' keys.

        Handles legacy format (bare list) by wrapping it.
        Returns None if file doesn't exist or is corrupt.
        """
        path = self._path(self._key(platform, slug))
        if not path.exists():
            return None
        try:
            with gzip.open(path, "rt") as f:
                data = json.loads(f.read())
        except Exception:
            return None
        # Legacy format: bare list without fetched_at wrapper
        if isinstance(data, list):
            return {"fetched_at": 0, "jobs": data}
        return data

    def get(self, platform: ATSPlatform, slug: str) -> list[Job] | None:
        raw = self._read_raw(platform, slug)
        if raw is None:
            return None
        try:
            return [Job.model_validate(j) for j in raw["jobs"]]
        except Exception:
            return None

    def is_stale(self, platform: ATSPlatform, slug: str) -> bool:
        raw = self._read_raw(platform, slug)
        if raw is None:
            return True
        fetched_at = raw.get("fetched_at", 0)
        return (time.time() - fetched_at) > self.ttl

    def set(self, platform: ATSPlatform, slug: str, jobs: list[Job]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(self._key(platform, slug))
        data = {
            "fetched_at": time.time(),
            "jobs": [j.model_dump(mode="json") for j in jobs],
        }
        with gzip.open(path, "wt") as f:
            f.write(json.dumps(data))

    def clear(self) -> int:
        if not self.cache_dir.exists():
            return 0
        count = 0
        for f in self.cache_dir.glob("*.json.gz"):
            f.unlink()
            count += 1
        return count
