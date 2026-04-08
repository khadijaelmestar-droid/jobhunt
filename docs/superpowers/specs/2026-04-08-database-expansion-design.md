# Database Expansion: More ATS Platforms + Discovery Engine

## Context

Jobhunt currently has 1,017 companies across 5 ATS platforms (Ashby 417, Lever 390, Greenhouse 199, Recruitee 10, Rippling 1). Discovery relies on Stapply CSV and Perplexity AI. The goal is to dramatically expand coverage by adding 12 new ATS platforms and building an automated multi-source discovery engine. Everything stays open-source (public GitHub CLI).

**Target:** 5,000+ companies across 17 ATS platforms.

---

## 1. New ATS Platforms (12)

### Tier 1 — Easy (public JSON APIs)

| Platform | Slug Pattern | API Endpoint | Region |
|----------|-------------|-------------|--------|
| Workable | `{slug}` | `apply.workable.com/{slug}/positions.json` | Global |
| SmartRecruiters | `{id}` | `api.smartrecruiters.com/v1/companies/{id}/postings` | Global |
| JazzHR | `{slug}` | `app.jazz.co/api/{slug}/jobs` | US |
| Breezy HR | `{slug}` | `{slug}.breezy.hr/json` | Global |
| Teamtailor | `{slug}` | `{slug}.teamtailor.com/jobs.json` | EU |
| Homerun | `{slug}` | `{slug}.homerun.co/api/jobs` | EU (NL) |

### Tier 2 — Medium (HTML parsing or non-standard JSON)

| Platform | Slug Pattern | API Endpoint | Region |
|----------|-------------|-------------|--------|
| BambooHR | `{slug}` | `{slug}.bamboohr.com/careers/list` | US/Global |
| Personio | `{slug}` | `{slug}.jobs.personio.de/search.json` | EU (DE) |

### Tier 3 — Hard (complex URL patterns, enterprise)

| Platform | Challenge | Region |
|----------|-----------|--------|
| Workday | Unique subdomains + site IDs per company (`{co}.wd{N}.myworkdaysite.com`) | Enterprise |
| iCIMS | Varied URL patterns (`careers-{slug}.icims.com`) | US/Enterprise |
| Taleo (Oracle) | Legacy XML-heavy system, multiple hosting zones | Enterprise |
| SuccessFactors (SAP) | Complex auth, varied deployment patterns | Enterprise |

### Provider Implementation

Each provider follows the existing pattern:
- File: `src/jobhunt/providers/{platform}.py`
- Async function: `fetch_jobs(client, slug, base_url?) -> list[Job]`
- Registered in `src/jobhunt/providers/__init__.py`
- Added to `ATSPlatform` enum in `src/jobhunt/models.py`

### Model Changes

**`ATSPlatform` enum** — add 12 new values:
```python
WORKABLE = "workable"
SMARTRECRUITERS = "smartrecruiters"
JAZZHR = "jazzhr"
BREEZY = "breezy"
TEAMTAILOR = "teamtailor"
HOMERUN = "homerun"
BAMBOOHR = "bamboohr"
PERSONIO = "personio"
WORKDAY = "workday"
ICIMS = "icims"
TALEO = "taleo"
SUCCESSFACTORS = "successfactors"
```

**`Company` model** — add optional field:
```python
base_url: str | None = None  # For Workday/iCIMS/Taleo where URL isn't derivable from slug
```

---

## 2. Discovery Engine

Four new discovery sources, integrated into the existing `jobhunt discover` CLI.

### Source 1: GitHub Awesome Lists

**File:** `src/jobhunt/discovery_sources/github_lists.py`

Parse markdown from curated GitHub repos:
- `remoteintech/remote-jobs` — remote-friendly companies
- `poteto/hiring-without-whiteboards` — companies with sane interview processes
- `tramcar/awesome-job-boards` — job board links

**Flow:** Fetch raw markdown -> extract company names + career URLs -> pass to ATS detector.

### Source 2: ATS Detector (Career Page Crawling)

**File:** `src/jobhunt/discovery_sources/ats_detector.py`

Given a career page URL, detect which ATS the company uses by checking HTML signatures:

| ATS | Detection Pattern |
|-----|------------------|
| Greenhouse | `boards.greenhouse.io` in iframe/script src |
| Lever | `jobs.lever.co` in iframe/script src |
| Ashby | `jobs.ashbyhq.com` in embed/script |
| Workable | `apply.workable.com` in widget/script |
| SmartRecruiters | `jobs.smartrecruiters.com` in iframe |
| Teamtailor | `career.teamtailor.com` or custom domain with TT scripts |
| BambooHR | `bamboohr.com/careers` in iframe |
| Personio | `jobs.personio.de` in iframe/script |
| Workday | `myworkdaysite.com` or `myworkday.com` in iframe |
| iCIMS | `icims.com` in iframe/script |

**Flow:** Fetch career page HTML -> scan for ATS signatures -> extract slug from URL -> return (platform, slug, company_name).

### Source 3: Enhanced Perplexity Discovery

**File:** Update existing `src/jobhunt/perplexity.py`

Improvements:
- **Industry-specific queries:** tech, fintech, healthtech, e-commerce, SaaS, cybersecurity, AI/ML, biotech, logistics, edtech
- **Iterative deepening:** After each batch, query "more companies like these, excluding [already found]"
- **All 17 platforms:** Generate prompts for each new ATS platform
- **Batch size:** 50 companies per query (up from 30)

### Source 4: Community Aggregators

**File:** `src/jobhunt/discovery_sources/aggregators.py`

Parse structured data from:
- **HN "Who's Hiring" threads** — monthly threads with company names + career links
- **Y Combinator company directory** — `ycombinator.com/companies` API
- **AngelList/Wellfound** — startup listings with career page links

**Flow:** Fetch listings -> extract company names + URLs -> pass to ATS detector.

### Discovery Source Registry

**File:** `src/jobhunt/discovery_sources/__init__.py`

```python
SOURCES = {
    "stapply": StapplySource,       # Existing
    "perplexity": PerplexitySource, # Enhanced
    "github-lists": GitHubListsSource,
    "detect": ATSDetectorSource,
    "aggregators": AggregatorsSource,
}
```

### Updated CLI

```
jobhunt discover                            # Default (Stapply)
jobhunt discover --source github-lists      # GitHub awesome lists
jobhunt discover --source detect --urls companies.txt  # ATS detection from URL list
jobhunt discover --source perplexity        # Enhanced AI discovery
jobhunt discover --source aggregators       # HN, YC, AngelList
jobhunt discover --source all               # Run all sources sequentially
jobhunt discover --source all --region eu   # All sources, EU companies only
```

---

## 3. Architecture

### File Structure

```
src/jobhunt/
├── providers/
│   ├── __init__.py              # Registry: 17 platforms
│   ├── greenhouse.py            # Existing
│   ├── lever.py                 # Existing
│   ├── ashby.py                 # Existing
│   ├── rippling.py              # Existing
│   ├── recruitee.py             # Existing
│   ├── workable.py              # NEW - Tier 1
│   ├── smartrecruiters.py       # NEW - Tier 1
│   ├── jazzhr.py                # NEW - Tier 1
│   ├── breezy.py                # NEW - Tier 1
│   ├── teamtailor.py            # NEW - Tier 1
│   ├── homerun.py               # NEW - Tier 1
│   ├── bamboohr.py              # NEW - Tier 2
│   ├── personio.py              # NEW - Tier 2
│   ├── workday.py               # NEW - Tier 3
│   ├── icims.py                 # NEW - Tier 3
│   ├── taleo.py                 # NEW - Tier 3
│   └── successfactors.py        # NEW - Tier 3
├── discovery_sources/
│   ├── __init__.py              # Source registry
│   ├── github_lists.py          # GitHub awesome-list parser
│   ├── ats_detector.py          # Career page ATS detection
│   └── aggregators.py           # HN, YC, AngelList parsers
├── models.py                    # Updated ATSPlatform (17 values) + Company.base_url
├── discovery.py                 # Updated to delegate to discovery_sources/
├── perplexity.py                # Enhanced with industries + iterative deepening
├── client.py                    # Unchanged
├── db.py                        # Unchanged (bulk_add handles new platforms)
├── search.py                    # Unchanged
├── cli.py                       # Updated discover command with new --source options
└── data/companies.json          # Will grow: 1,017 → 5,000+
```

### Data Flow

```
Discovery Sources
  ├── GitHub Lists ──→ company names + career URLs
  ├── ATS Detector ──→ (platform, slug) from career page HTML
  ├── Perplexity ────→ (platform, slug) from AI search
  ├── Aggregators ───→ company names + career URLs
  └── Stapply CSV ───→ (platform, slug) from CSV
          ↓
    Candidate list: [(name, slug, platform, base_url?)]
          ↓
    Deduplication (against CompanyDB.get_all_keys())
          ↓
    Async slug validation (hit ATS API, semaphore=50)
          ↓
    Optional region probing (fetch jobs, check locations)
          ↓
    CompanyDB.bulk_add() → saved to companies.json
```

---

## 4. Implementation Waves

### Wave 1: Tier 1 ATS Platforms
- Workable, SmartRecruiters, JazzHR, Breezy, Teamtailor, Homerun
- Update ATSPlatform enum (all 12 new values at once) + provider registry
- Add `base_url: str | None = None` to Company model (needed later for Tier 3)
- 6 new provider files, each ~80-120 lines
- Seed initial companies via existing Perplexity discovery

### Wave 2: Tier 2 ATS Platforms
- BambooHR, Personio
- May need HTML parsing fallbacks
- 2 provider files

### Wave 3: Discovery Engine
- `discovery_sources/` package with 3 new source modules
- Enhanced Perplexity with industry matrix
- Updated CLI with new `--source` options
- Run full discovery to populate database

### Wave 4: Tier 3 Enterprise Platforms
- Workday, iCIMS, Taleo, SuccessFactors
- Research-heavy: each needs URL pattern investigation
- `base_url` field already on Company model from Wave 1
- 4 provider files, likely more complex (~150-250 lines each)

---

## 5. Verification Plan

### Per-Provider Tests
- Mock API response → parse → verify Job objects have correct fields
- Real API smoke test: pick 1 known company per platform, fetch jobs

### Discovery Tests
- GitHub lists: parse sample markdown → extract companies
- ATS detector: feed known career pages → verify correct platform detected
- Perplexity: mock response → verify candidate extraction

### End-to-End Tests
```bash
# New platform works
jobhunt search "engineer" --platform workable

# Discovery finds companies
jobhunt discover --source github-lists --platform teamtailor

# Full pipeline
jobhunt discover --source all --region eu
jobhunt companies --platform workable  # Should show discovered companies
jobhunt platforms                      # Should list all 17 platforms

# Database growth
wc -l src/jobhunt/data/companies.json  # Should be significantly larger
```

### Acceptance Criteria
- All 17 platforms return valid Job objects from real company slugs
- Discovery sources collectively find 500+ new companies per run
- `jobhunt platforms` shows all 17 platforms with company counts
- No regressions on existing 5 platforms
