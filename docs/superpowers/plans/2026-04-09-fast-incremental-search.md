# Fast Incremental Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `jobhunt search` near-instant via stale-while-revalidate caching, and flag new jobs with `[NEW]` badges by tracking search result fingerprints.

**Architecture:** Evolve the existing gzip file cache to use deterministic keys (no time bucket) with a `fetched_at` timestamp for staleness. Return stale results immediately, refresh in background. A separate `SearchFingerprint` class tracks seen job IDs per keyword hash and uses Jaccard similarity for similar-term matching.

**Tech Stack:** Python 3.10+, asyncio, gzip, json, hashlib (all stdlib). Pydantic (existing dep). pytest (new dev dep).

**Spec:** `docs/superpowers/specs/2026-04-09-fast-incremental-search-design.md`

---

## File Structure

| File | Role |
|------|------|
| `src/jobhunt/cache.py` | **Modify** — Persistent cache with `fetched_at`, deterministic keys, `is_stale()`, legacy format handling |
| `src/jobhunt/fingerprint.py` | **Create** — `SearchFingerprint` class: keyword normalization, Jaccard similarity, seen job ID tracking |
| `src/jobhunt/display.py` | **Modify** — Accept `new_job_ids` param, render `[NEW]` badges and summary count |
| `src/jobhunt/cli.py` | **Modify** — SWR search flow, `--refresh` flag, background refresh, fingerprint integration |
| `tests/test_cache.py` | **Create** — Tests for persistent cache, staleness, legacy format |
| `tests/test_fingerprint.py` | **Create** — Tests for keyword normalization, Jaccard matching, fingerprint CRUD |
| `tests/test_display.py` | **Create** — Tests for NEW badge rendering |
| `tests/conftest.py` | **Create** — Shared fixtures (tmp dirs, sample Job objects) |

---

### Task 1: Set Up Test Infrastructure

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add pytest to dev dependencies**

In `pyproject.toml`, add after the `[build-system]` section:

```toml
[project.optional-dependencies]
dev = ["pytest>=7.0.0", "pytest-asyncio>=0.21.0"]
```

- [ ] **Step 2: Install dev dependencies**

Run: `pip install -e ".[dev]"`
Expected: Successfully installs pytest and pytest-asyncio

- [ ] **Step 3: Create tests/conftest.py with shared fixtures**

```python
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
```

- [ ] **Step 4: Verify pytest runs**

Run: `pytest tests/ -v --co`
Expected: Shows `tests/conftest.py` collected, 0 tests (no test files yet)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/conftest.py
git commit -m "chore: add pytest infrastructure and shared fixtures"
```

---

### Task 2: Persistent Cache with Staleness Tracking

**Files:**
- Modify: `src/jobhunt/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests for the new cache behavior**

Create `tests/test_cache.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cache.py -v`
Expected: Multiple failures — `is_stale` not defined, cache key uses time bucket, `get` returns `None` for stale data

- [ ] **Step 3: Implement the new cache**

Replace the entire contents of `src/jobhunt/cache.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobhunt/cache.py tests/test_cache.py
git commit -m "feat: persistent cache with staleness tracking, no time-bucket expiry"
```

---

### Task 3: Search Fingerprints

**Files:**
- Create: `src/jobhunt/fingerprint.py`
- Create: `tests/test_fingerprint.py`

- [ ] **Step 1: Write failing tests for fingerprint behavior**

Create `tests/test_fingerprint.py`:

```python
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
        # Store a fingerprint for ["backend", "engineer", "python"]
        fp.update(["backend", "engineer", "python"], {"job1", "job2"})
        # Search with ["backend", "engineer"] — Jaccard = 2/3 = 0.67 > 0.5
        new_ids = fp.get_new_job_ids(["backend", "engineer"], {"job1", "job2", "job3"})
        assert new_ids == {"job3"}

    def test_low_overlap_no_match(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend", "developer"], {"job1", "job2"})
        # Search with ["frontend", "engineer"] — Jaccard = 0/4 = 0.0 < 0.5
        new_ids = fp.get_new_job_ids(["frontend", "engineer"], {"job1", "job2", "job3"})
        # No previous fingerprint matches, so ALL jobs are "new"
        assert new_ids == {"job1", "job2", "job3"}

    def test_exact_match_preferred_over_similar(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["backend", "engineer", "python"], {"job1", "job2"})
        fp.update(["backend", "engineer"], {"job1", "job3"})
        # Exact match for ["backend", "engineer"] should use its fingerprint
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
        # Load a fresh instance to verify persistence
        fp2 = SearchFingerprint(cache_dir=tmp_cache_dir)
        new_ids = fp2.get_new_job_ids(["backend"], {"job1", "job2", "job3"})
        assert new_ids == {"job3"}

    def test_prunes_old_fingerprints(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        # Create 55 fingerprints (exceeds max of 50)
        for i in range(55):
            fp.update([f"keyword{i}"], {f"job{i}"})
        # Reload and check count
        fp2 = SearchFingerprint(cache_dir=tmp_cache_dir)
        data = fp2._load()
        assert len(data["fingerprints"]) <= 50

    def test_prunes_fingerprints_older_than_30_days(self, tmp_cache_dir):
        fp = SearchFingerprint(cache_dir=tmp_cache_dir)
        fp.update(["old"], {"job1"})
        # Manually backdate
        data = fp._load()
        old_hash = fp._keyword_hash(["old"])
        data["fingerprints"][old_hash]["last_searched_at"] = time.time() - (31 * 86400)
        fp._save(data)
        # Trigger prune via another update
        fp.update(["new"], {"job2"})
        data = fp._load()
        assert old_hash not in data["fingerprints"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fingerprint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobhunt.fingerprint'`

- [ ] **Step 3: Implement SearchFingerprint**

Create `src/jobhunt/fingerprint.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fingerprint.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobhunt/fingerprint.py tests/test_fingerprint.py
git commit -m "feat: add SearchFingerprint for tracking seen jobs per keyword set"
```

---

### Task 4: Display NEW Badges

**Files:**
- Modify: `src/jobhunt/display.py`
- Create: `tests/test_display.py`

- [ ] **Step 1: Write failing tests for NEW badge rendering**

Create `tests/test_display.py`:

```python
from __future__ import annotations

from io import StringIO

from rich.console import Console

from jobhunt.display import display_jobs_table


class TestNewBadges:
    """Jobs in new_job_ids get a [NEW] badge instead of a row number."""

    def test_new_badge_shown_for_new_jobs(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        new_ids = {sample_jobs[0].id}  # "1001" is new
        display_jobs_table(sample_jobs, console=console, new_job_ids=new_ids)
        text = output.getvalue()
        assert "NEW" in text

    def test_no_badge_when_no_new_ids(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        display_jobs_table(sample_jobs, console=console, new_job_ids=set())
        text = output.getvalue()
        assert "NEW" not in text

    def test_no_badge_when_new_job_ids_is_none(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        display_jobs_table(sample_jobs, console=console)
        text = output.getvalue()
        # Default behavior — just row numbers, no NEW
        assert "NEW" not in text

    def test_summary_count_printed(self, sample_jobs):
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        new_ids = {sample_jobs[0].id, sample_jobs[2].id}
        display_jobs_table(sample_jobs, console=console, new_job_ids=new_ids)
        text = output.getvalue()
        assert "2 new" in text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_display.py -v`
Expected: FAIL — `display_jobs_table()` doesn't accept `new_job_ids` parameter

- [ ] **Step 3: Implement NEW badge support in display.py**

Replace the entire contents of `src/jobhunt/display.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table
from jobhunt.models import Job


def display_jobs_table(
    jobs: list[Job],
    console: Console | None = None,
    limit: int | None = None,
    new_job_ids: set[str] | None = None,
) -> None:
    con = console or Console()

    if not jobs:
        con.print("[yellow]No jobs found matching your criteria.[/yellow]")
        return

    shown = jobs[:limit] if limit else jobs
    title = f"Found {len(jobs)} jobs"
    if limit and limit < len(jobs):
        title += f" (showing {len(shown)})"

    # Print NEW summary if applicable
    if new_job_ids:
        new_count = sum(1 for j in shown if j.id in new_job_ids)
        if new_count > 0:
            con.print(f"[bold green]{new_count} new job{'s' if new_count != 1 else ''} since last search[/bold green]\n")

    table = Table(title=title, show_lines=False, expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Company", style="cyan", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("Title", style="green", ratio=4, no_wrap=True, overflow="ellipsis")
    table.add_column("Location", style="yellow", ratio=2, no_wrap=True, overflow="ellipsis")
    table.add_column("ATS", style="dim", width=6)

    for i, job in enumerate(shown, 1):
        row_num = "[bold green]NEW[/bold green]" if new_job_ids and job.id in new_job_ids else str(i)
        table.add_row(
            row_num,
            job.company,
            job.title,
            job.location or "-",
            job.platform.value[:5],
        )
    con.print(table)

    # Print URLs below the table
    con.print()
    for i, job in enumerate(shown, 1):
        con.print(f"  [dim]{i:>3}.[/dim] [blue underline]{job.url}[/blue underline]")


def export_json(jobs: list[Job], path: Path) -> None:
    data = [job.model_dump(mode="json") for job in jobs]
    path.write_text(json.dumps(data, indent=2, default=str))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_display.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/jobhunt/display.py tests/test_display.py
git commit -m "feat: add NEW badge support to job results table"
```

---

### Task 5: Stale-While-Revalidate Search Flow

**Files:**
- Modify: `src/jobhunt/cli.py`

This is the core integration task. It modifies the `search()` command to use the SWR pattern.

- [ ] **Step 1: Add the --refresh flag to the search command**

In `src/jobhunt/cli.py`, add the `refresh` parameter to the `search()` function signature. Change line 38 (after the `no_cache` parameter):

```python
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache"),
    refresh: bool = typer.Option(False, "--refresh", help="Force re-fetch all companies before displaying"),
    concurrency: int = typer.Option(20, "--concurrency", help="Max concurrent requests"),
```

- [ ] **Step 2: Rewrite the async run() function inside search() for SWR**

Replace the entire `async def run()` function (lines 63–108) and the lines after it (109–117) with the following. The full `search()` function body from `query = SearchQuery(...)` onward becomes:

```python
    query = SearchQuery(
        keywords=keywords or [],
        location=location,
        remote_only=remote,
        platforms=platform,
        tags=tag or [],
        department=department,
    )

    cache = JobCache() if not no_cache else None

    async def run() -> list:
        from jobhunt.models import Job

        client = JobhuntClient(max_concurrent=concurrency)
        cached_jobs: list[Job] = []
        stale_companies: list[Company] = []
        cold_companies: list[Company] = []

        if cache and not refresh:
            for c in companies:
                cached = cache.get(c.platform, c.slug)
                if cached is not None:
                    cached_jobs.extend(cached)
                    if cache.is_stale(c.platform, c.slug):
                        stale_companies.append(c)
                else:
                    cold_companies.append(c)
        else:
            cold_companies = list(companies)

        # Cold start: blocking fetch with spinner
        fetched: list[Job] = []
        if cold_companies:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Fetching jobs from {len(cold_companies)} companies...", total=None)

                def on_progress(company: Company, had_jobs: bool) -> None:
                    progress.update(task, description=f"Fetched {company.name} ({company.platform})")

                fetched = await client.fetch_all(cold_companies, PROVIDERS, on_progress=on_progress)

            if cache:
                _cache_fetched(cache, fetched, cold_companies)

        all_jobs = cached_jobs + fetched

        # Background refresh for stale companies
        if stale_companies and cache:
            console.print(f"[dim]Refreshing {len(stale_companies)} stale companies in background...[/dim]")
            bg_client = JobhuntClient(max_concurrent=50)

            async def background_refresh() -> None:
                bg_fetched = await bg_client.fetch_all(stale_companies, PROVIDERS)
                _cache_fetched(cache, bg_fetched, stale_companies)
                console.print(f"[green]\u2713 Cache refreshed. Run again for latest results.[/green]")

            await background_refresh()

        return all_jobs

    all_jobs = asyncio.run(run())
    results = filter_jobs(all_jobs, query)

    # Fingerprint integration for NEW badges
    from jobhunt.fingerprint import SearchFingerprint
    new_ids: set[str] | None = None
    if query.keywords and cache is not None:
        fp = SearchFingerprint()
        current_ids = {j.id for j in results}
        new_ids = fp.get_new_job_ids(query.keywords, current_ids)
        display_jobs_table(results, console=console, limit=limit, new_job_ids=new_ids)
        fp.update(query.keywords, current_ids)
    else:
        display_jobs_table(results, console=console, limit=limit)

    if output:
        export_json(results, output)
        console.print(f"\n[green]Exported {len(results)} jobs to {output}[/green]")
```

- [ ] **Step 3: Add the _cache_fetched helper function**

Add this function in `src/jobhunt/cli.py` right before the `search()` function definition (before line 28):

```python
def _cache_fetched(cache: JobCache, fetched: list, companies: list[Company]) -> None:
    """Group fetched jobs by company and cache each group."""
    from jobhunt.models import Job

    by_company: dict[tuple[str, str], list[Job]] = {}
    for j in fetched:
        key = (j.platform, j.company_slug)
        by_company.setdefault(key, []).append(j)
    for (plat, slug), jobs in by_company.items():
        cache.set(ATSPlatform(plat), slug, jobs)
    # Cache empty results for companies that returned nothing
    fetched_slugs = {(j.platform, j.company_slug) for j in fetched}
    for c in companies:
        if (c.platform, c.slug) not in fetched_slugs:
            cache.set(c.platform, c.slug, [])
```

- [ ] **Step 4: Manually test the SWR flow**

Run: `jobhunt cache clear && jobhunt search backend --limit 10`
Expected: Shows spinner (cold start), fetches all companies, displays results.

Run again immediately: `jobhunt search backend --limit 10`
Expected: Instant results from cache, no spinner.

Run with refresh: `jobhunt search backend --limit 10 --refresh`
Expected: Shows spinner, re-fetches everything, displays results.

- [ ] **Step 5: Commit**

```bash
git add src/jobhunt/cli.py
git commit -m "feat: stale-while-revalidate search with --refresh flag and NEW badges"
```

---

### Task 6: End-to-End Verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass (cache, fingerprint, display)

- [ ] **Step 2: Test cold start → warm → stale cycle**

```bash
# Cold start
jobhunt cache clear
jobhunt search engineer --limit 5
# Expect: spinner, fetches all companies, results displayed, all marked NEW (first search)

# Warm cache
jobhunt search engineer --limit 5
# Expect: instant results, no spinner, no NEW badges (same results)

# Different keywords with overlap
jobhunt search "engineer python" --limit 5
# Expect: instant results (still cached), NEW badges for jobs not in previous "engineer" search
```

- [ ] **Step 3: Test --no-cache and --refresh flags**

```bash
jobhunt search engineer --no-cache --limit 5
# Expect: spinner, fetches everything, no NEW badges (fingerprints skipped with no-cache)

jobhunt search engineer --refresh --limit 5
# Expect: spinner, fetches everything, NEW badges still work
```

- [ ] **Step 4: Verify cache files on disk**

```bash
ls ~/.cache/jobhunt/*.json.gz | head -5
# Expect: files exist with deterministic names (no time bucket in name)

python3 -c "
import gzip, json
from pathlib import Path
p = next(Path.home().joinpath('.cache/jobhunt').glob('*.json.gz'))
with gzip.open(p, 'rt') as f:
    d = json.loads(f.read())
print('Has fetched_at:', 'fetched_at' in d)
print('Has jobs:', 'jobs' in d)
"
# Expect: Has fetched_at: True, Has jobs: True
```

- [ ] **Step 5: Verify fingerprint file**

```bash
python3 -c "
import json
from pathlib import Path
p = Path.home() / '.cache/jobhunt/seen_jobs.json'
if p.exists():
    d = json.loads(p.read_text())
    print(f'Fingerprints stored: {len(d[\"fingerprints\"])}')
    for k, v in d['fingerprints'].items():
        print(f'  {k}: keywords={v[\"keywords\"]}, jobs={len(v[\"job_ids\"])}')
else:
    print('No fingerprint file yet')
"
```

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
# Only if changes were made during verification
git add -A
git commit -m "fix: address issues found during end-to-end verification"
```
