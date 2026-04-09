from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

_MAX_FINGERPRINTS = 50
_MAX_AGE_SECONDS = 30 * 86400  # 30 days
_JACCARD_THRESHOLD = 0.5


def _default_cache_dir() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return Path(cache) / "jobhunt"


class SearchFingerprint:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or _default_cache_dir()
        self._file = self.cache_dir / "seen_jobs.json"

    def _keyword_hash(self, keywords: list[str]) -> str:
        normalized = "|".join(sorted(kw.lower() for kw in keywords))
        return hashlib.sha256(normalized.encode()).hexdigest()[:12]

    def _load(self) -> dict:
        if not self._file.exists():
            return {"fingerprints": {}}
        try:
            return json.loads(self._file.read_text())
        except Exception:
            return {"fingerprints": {}}

    def _save(self, data: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(data))

    def _find_best_match(
        self, keywords: list[str], data: dict
    ) -> set[str] | None:
        """Find the best matching fingerprint: exact hash first, then Jaccard similarity."""
        fingerprints = data.get("fingerprints", {})
        kw_hash = self._keyword_hash(keywords)

        # Exact match
        if kw_hash in fingerprints:
            return set(fingerprints[kw_hash]["job_ids"])

        # Jaccard similarity fallback
        query_set = {kw.lower() for kw in keywords}
        if not query_set:
            return None

        best_score = 0.0
        best_ids: set[str] | None = None
        for entry in fingerprints.values():
            stored_set = {kw.lower() for kw in entry["keywords"]}
            if not stored_set:
                continue
            intersection = len(query_set & stored_set)
            union = len(query_set | stored_set)
            jaccard = intersection / union
            if jaccard > best_score and jaccard > _JACCARD_THRESHOLD:
                best_score = jaccard
                best_ids = set(entry["job_ids"])

        return best_ids

    def get_new_job_ids(
        self, keywords: list[str], current_job_ids: set[str]
    ) -> set[str]:
        """Returns job IDs in current_job_ids that weren't in the previous fingerprint."""
        data = self._load()
        previous_ids = self._find_best_match(keywords, data)
        if previous_ids is None:
            return set(current_job_ids)
        return current_job_ids - previous_ids

    def update(self, keywords: list[str], job_ids: set[str]) -> None:
        """Save the current result set as the fingerprint for these keywords."""
        data = self._load()
        kw_hash = self._keyword_hash(keywords)
        data["fingerprints"][kw_hash] = {
            "keywords": [kw.lower() for kw in keywords],
            "job_ids": list(job_ids),
            "last_searched_at": time.time(),
        }
        self._prune(data)
        self._save(data)

    def _prune(self, data: dict) -> None:
        """Remove old fingerprints and enforce max count."""
        fingerprints = data.get("fingerprints", {})
        now = time.time()

        # Remove entries older than 30 days
        expired = [
            k for k, v in fingerprints.items()
            if (now - v.get("last_searched_at", 0)) > _MAX_AGE_SECONDS
        ]
        for k in expired:
            del fingerprints[k]

        # LRU eviction if over max count
        if len(fingerprints) > _MAX_FINGERPRINTS:
            sorted_keys = sorted(
                fingerprints.keys(),
                key=lambda k: fingerprints[k].get("last_searched_at", 0),
            )
            for k in sorted_keys[: len(fingerprints) - _MAX_FINGERPRINTS]:
                del fingerprints[k]
