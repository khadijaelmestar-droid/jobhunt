# Fast Incremental Search with Stale-While-Revalidate

**Date:** 2026-04-09
**Status:** Draft

## Context

The `jobhunt search` command queries 1,000+ companies across 13 ATS platforms. The current cache uses a 1-hour TTL with time-bucketed keys — when the bucket rolls over, every company becomes a cache miss, forcing a full re-fetch that takes minutes. Users who search multiple times per hour experience a painful cold-start penalty once per hour.

**Goals:**
1. Make search near-instant by returning cached results immediately, regardless of age
2. Refresh stale data in the background so the next search gets fresh results
3. Flag jobs as `[NEW]` that weren't present in the previous search with similar keywords

## Architecture

### 1. Persistent Cache with Staleness Tracking

**File:** `src/jobhunt/cache.py`

Remove the time bucket from the cache key. The key becomes deterministic per company:

```
key = SHA256(f"{platform}:{slug}")[:16]
```

Store `fetched_at` alongside job data in each cache file:

```json
{
  "fetched_at": 1712678400,
  "jobs": [{ ... }, { ... }]
}
```

**API changes to `JobCache`:**

- `get(platform, slug) -> list[Job] | None` — returns cached jobs regardless of age. Returns `None` only if no cache file exists.
- `is_stale(platform, slug) -> bool` — returns `True` if `fetched_at` is older than `self.ttl` seconds, or if no cache exists.
- `set(platform, slug, jobs)` — writes with `fetched_at = time.time()`.
- `clear()` — unchanged.

**Legacy format handling:** If a cache file contains a bare JSON list (old format without `fetched_at`), treat it as stale and return the jobs. It will be overwritten on next refresh with the new format.

### 2. Stale-While-Revalidate Search Flow

**File:** `src/jobhunt/cli.py` — `search()` command

New flow:

```
1. Load companies from DB, apply platform/tag filters
2. For each company:
   a. cached = cache.get(platform, slug)
   b. If cached is not None: add to cached_jobs
   c. If cache.is_stale(platform, slug): add to stale_list
   d. If cached is None (no cache file at all): add to cold_list
3. If cold_list is non-empty (true cold start):
   → Blocking fetch with progress spinner (current behavior)
   → Cache results, add to cached_jobs
4. Filter cached_jobs by SearchQuery → display results IMMEDIATELY
5. If stale_list is non-empty:
   → Print "[dim]Refreshing {N} companies in background...[/dim]"
   → asyncio.create_task(background_refresh(stale_list))
   → When complete: print "[green]✓ Cache refreshed. Run again for latest.[/green]"
```

**Key behaviors:**
- First-ever search (no cache at all): blocking fetch with spinner — same as today
- Subsequent searches within TTL: instant from cache, no background work
- Searches after TTL: instant from stale cache, background refresh for next time
- `--no-cache`: bypasses everything, blocking fetch (unchanged)
- `--refresh` (new flag): forces blocking re-fetch, updates cache, then displays

**Background refresh concurrency:** 50 (vs default 20 for foreground) since the user isn't waiting.

**asyncio integration:** The background refresh runs as a task within the same `asyncio.run()` event loop. The main path awaits display, then the event loop continues until the refresh task completes.

### 3. Search Fingerprints (NEW Badge)

**New file:** `src/jobhunt/fingerprint.py`

Tracks which job IDs were shown for a given keyword set, enabling `[NEW]` badges.

**Storage:** `~/.cache/jobhunt/seen_jobs.json`

```json
{
  "fingerprints": {
    "a1b2c3d4e5f6": {
      "keywords": ["backend", "engineer"],
      "job_ids": ["gh-stripe-12345", "lever-acme-67890"],
      "last_searched_at": 1712678400
    }
  }
}
```

**Keyword normalization:**
- Lowercase all keywords
- Sort alphabetically
- Join with `|`
- Hash: `SHA256(normalized)[:12]`
- Example: `"Backend Engineer"` and `"engineer backend"` → `SHA256("backend|engineer")[:12]`

**Similar-term matching:**
- First: exact hash match (same keywords, different order)
- Fallback: find fingerprint with highest Jaccard similarity on keyword sets, threshold > 0.5
- Example: `"backend engineer"` (keywords: {backend, engineer}) matches `"backend developer"` (keywords: {backend, developer}) with Jaccard = 1/3 = 0.33 → no match. But `"backend engineer python"` vs `"backend engineer"` → Jaccard = 2/3 = 0.67 → match.

**`SearchFingerprint` class API:**

```python
class SearchFingerprint:
    def __init__(self, cache_dir: Path | None = None): ...
    def get_new_job_ids(self, keywords: list[str], current_job_ids: set[str]) -> set[str]:
        """Returns job IDs in current_job_ids that weren't in the previous fingerprint."""
    def update(self, keywords: list[str], job_ids: set[str]) -> None:
        """Save the current result set as the fingerprint for these keywords."""
```

**Lifecycle:**
- Fingerprints older than 30 days are pruned on each `update()` call
- Maximum 50 fingerprints stored (LRU eviction by `last_searched_at`)

### 4. Display Integration

**File:** `src/jobhunt/display.py`

`display_jobs_table()` gets an optional `new_job_ids: set[str] | None` parameter.

When provided:
- Jobs whose `id` is in `new_job_ids` show `NEW` (bold green) in the `#` column instead of their number
- A summary line prints above the table: `"X new jobs since last search"`

When `None` (default): unchanged behavior.

### 5. CLI Integration

**File:** `src/jobhunt/cli.py`

After filtering results:

```python
fingerprint = SearchFingerprint()
current_ids = {j.id for j in results}
new_ids = fingerprint.get_new_job_ids(query.keywords, current_ids)
display_jobs_table(results, console=console, limit=limit, new_job_ids=new_ids)
fingerprint.update(query.keywords, current_ids)
```

## Files Changed

| File | Change |
|------|--------|
| `src/jobhunt/cache.py` | Remove time-bucket from key, add `fetched_at` wrapper, add `is_stale()`, handle legacy format |
| `src/jobhunt/cli.py` | SWR flow in `search()`, add `--refresh` flag, background refresh, fingerprint integration |
| `src/jobhunt/display.py` | Accept `new_job_ids` param, render `[NEW]` badge, summary count |
| `src/jobhunt/fingerprint.py` | **New file** — `SearchFingerprint` class with load/save/match/update |

**No new dependencies.** Uses stdlib (`json`, `hashlib`, `gzip`, `asyncio`, `time`) and existing deps.

## Verification

1. **Cache persistence:** Run `jobhunt search backend`. Check `~/.cache/jobhunt/` has `.json.gz` files. Wait >1h (or temporarily set TTL to 5s). Run again — should return instantly from stale cache.
2. **Background refresh:** After stale search, verify "[dim]Refreshing..." message appears. Wait for completion message. Run again — cache files should have updated `fetched_at`.
3. **NEW badges:** Run `jobhunt search backend`. Note results. Add a new company via `jobhunt companies add`. Run `jobhunt search backend` again. Jobs from the new company should show `[NEW]`.
4. **Cold start:** Clear cache (`jobhunt cache clear`). Run search — should show blocking spinner (current behavior).
5. **--refresh flag:** Run `jobhunt search backend --refresh` — should block and re-fetch everything, then display.
6. **--no-cache:** Run `jobhunt search backend --no-cache` — unchanged behavior, no fingerprint update.
7. **Similar keywords:** Search `"backend engineer"`, then `"backend developer"` — second search should show NEW badges for jobs not in the first result set (if Jaccard > 0.5, otherwise all jobs appear without NEW).
