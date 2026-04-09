from __future__ import annotations

import gzip
import json
import time

import pytest

from jobhunt.cache import JobCache
from jobhunt.models import ATSPlatform


class TestPersistentCache:
    """Cache returns data regardless of age — no time-bucket expiry."""

    def test_get_returns_none_when_no_cache_file(self, tmp_cache_dir):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        result = cache.get(ATSPlatform.GREENHOUSE, "acme")
        assert result is None

    def test_set_then_get_returns_jobs(self, tmp_cache_dir, sample_jobs):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        cache.set(ATSPlatform.GREENHOUSE, "acme", sample_jobs)
        result = cache.get(ATSPlatform.GREENHOUSE, "acme")
        assert result is not None
        assert len(result) == 3
        assert result[0].id == "1001"

    def test_get_returns_data_even_when_stale(self, tmp_cache_dir, sample_jobs):
        cache = JobCache(ttl_seconds=1)
        cache.cache_dir = tmp_cache_dir
        cache.set(ATSPlatform.GREENHOUSE, "acme", sample_jobs)
        # Manually backdate fetched_at
        path = cache._path(cache._key(ATSPlatform.GREENHOUSE, "acme"))
        with gzip.open(path, "rt") as f:
            data = json.loads(f.read())
        data["fetched_at"] = time.time() - 3600  # 1 hour ago
        with gzip.open(path, "wt") as f:
            f.write(json.dumps(data))
        result = cache.get(ATSPlatform.GREENHOUSE, "acme")
        assert result is not None
        assert len(result) == 3

    def test_deterministic_key_no_time_bucket(self, tmp_cache_dir):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        key1 = cache._key(ATSPlatform.GREENHOUSE, "acme")
        key2 = cache._key(ATSPlatform.GREENHOUSE, "acme")
        assert key1 == key2

    def test_different_companies_different_keys(self, tmp_cache_dir):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        key1 = cache._key(ATSPlatform.GREENHOUSE, "acme")
        key2 = cache._key(ATSPlatform.GREENHOUSE, "beta")
        assert key1 != key2


class TestStaleness:
    """is_stale() checks fetched_at against TTL."""

    def test_is_stale_when_no_cache(self, tmp_cache_dir):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        assert cache.is_stale(ATSPlatform.GREENHOUSE, "acme") is True

    def test_is_stale_when_fresh(self, tmp_cache_dir, sample_jobs):
        cache = JobCache(ttl_seconds=3600)
        cache.cache_dir = tmp_cache_dir
        cache.set(ATSPlatform.GREENHOUSE, "acme", sample_jobs)
        assert cache.is_stale(ATSPlatform.GREENHOUSE, "acme") is False

    def test_is_stale_when_old(self, tmp_cache_dir, sample_jobs):
        cache = JobCache(ttl_seconds=1)
        cache.cache_dir = tmp_cache_dir
        cache.set(ATSPlatform.GREENHOUSE, "acme", sample_jobs)
        # Backdate fetched_at
        path = cache._path(cache._key(ATSPlatform.GREENHOUSE, "acme"))
        with gzip.open(path, "rt") as f:
            data = json.loads(f.read())
        data["fetched_at"] = time.time() - 3600
        with gzip.open(path, "wt") as f:
            f.write(json.dumps(data))
        assert cache.is_stale(ATSPlatform.GREENHOUSE, "acme") is True


class TestLegacyFormat:
    """Old cache files (bare JSON list) are handled gracefully."""

    def test_legacy_bare_list_returns_jobs(self, tmp_cache_dir, sample_jobs):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        cache.cache_dir.mkdir(parents=True, exist_ok=True)
        # Write old format: bare list without fetched_at wrapper
        path = cache._path(cache._key(ATSPlatform.GREENHOUSE, "acme"))
        data = [j.model_dump(mode="json") for j in sample_jobs]
        with gzip.open(path, "wt") as f:
            f.write(json.dumps(data))
        result = cache.get(ATSPlatform.GREENHOUSE, "acme")
        assert result is not None
        assert len(result) == 3

    def test_legacy_bare_list_is_stale(self, tmp_cache_dir, sample_jobs):
        cache = JobCache(ttl_seconds=60)
        cache.cache_dir = tmp_cache_dir
        cache.cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache._path(cache._key(ATSPlatform.GREENHOUSE, "acme"))
        data = [j.model_dump(mode="json") for j in sample_jobs]
        with gzip.open(path, "wt") as f:
            f.write(json.dumps(data))
        assert cache.is_stale(ATSPlatform.GREENHOUSE, "acme") is True
