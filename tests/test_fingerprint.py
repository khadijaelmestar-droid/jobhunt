from __future__ import annotations

import json
import time

import pytest

from jobhunt.fingerprint import SearchFingerprint


class TestKeywordNormalization:
    """Keywords are lowercased, sorted, and joined for deterministic hashing."""

    def test_same_keywords_different_order_same_hash(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        h1 = fp._keyword_hash(["Backend", "Engineer"])
        h2 = fp._keyword_hash(["engineer", "backend"])
        assert h1 == h2

    def test_different_keywords_different_hash(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        h1 = fp._keyword_hash(["backend", "engineer"])
        h2 = fp._keyword_hash(["frontend", "developer"])
        assert h1 != h2

    def test_empty_keywords(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        h = fp._keyword_hash([])
        assert isinstance(h, str)
        assert len(h) == 12


class TestJaccardSimilarity:
    """Find the best matching fingerprint for similar keyword sets."""

    def test_high_overlap_matches(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend", "engineer", "python"], {"job1", "job2"})
        new_ids = fp.get_new_job_ids(["backend", "engineer"], {"job1", "job2", "job3"})
        assert new_ids == {"job3"}

    def test_low_overlap_no_match(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend", "developer"], {"job1", "job2"})
        new_ids = fp.get_new_job_ids(["frontend", "engineer"], {"job1", "job2", "job3"})
        assert new_ids == {"job1", "job2", "job3"}

    def test_exact_match_preferred_over_similar(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend", "engineer", "python"], {"job1", "job2"})
        fp.update(["backend", "engineer"], {"job1", "job3"})
        new_ids = fp.get_new_job_ids(["backend", "engineer"], {"job1", "job3", "job4"})
        assert new_ids == {"job4"}


class TestGetNewJobIds:
    """get_new_job_ids returns IDs not present in the previous fingerprint."""

    def test_first_search_all_new(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        new_ids = fp.get_new_job_ids(["backend"], {"job1", "job2"})
        assert new_ids == {"job1", "job2"}

    def test_second_search_only_new(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend"], {"job1", "job2"})
        new_ids = fp.get_new_job_ids(["backend"], {"job1", "job2", "job3"})
        assert new_ids == {"job3"}

    def test_no_new_jobs(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend"], {"job1", "job2", "job3"})
        new_ids = fp.get_new_job_ids(["backend"], {"job1", "job2"})
        assert new_ids == set()


class TestUpdate:
    """update() persists the fingerprint and handles lifecycle."""

    def test_update_persists_to_disk(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend"], {"job1", "job2"})
        fp2 = SearchFingerprint(cache_dir=tmp_cache_dir)
        new_ids = fp2.get_new_job_ids(["backend"], {"job1", "job2", "job3"})
        assert new_ids == {"job3"}

    def test_prunes_old_fingerprints(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        for i in range(55):
            fp.update([f"keyword{i}"], {f"job{i}"})
        fp2 = SearchFingerprint(cache_dir=tmp_cache_dir)
        data = fp2._load()
        assert len(data["fingerprints"]) <= 50

    def test_prunes_fingerprints_older_than_30_days(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["old"], {"job1"})
        data = fp._load()
        old_hash = fp._keyword_hash(["old"])
        data["fingerprints"][old_hash]["last_searched_at"] = time.time() - (31 * 86400)
        fp._save(data)
        fp.update(["new"], {"job2"})
        data = fp._load()
        assert old_hash not in data["fingerprints"]
