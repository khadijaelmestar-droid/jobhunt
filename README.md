# jobhunt

A command-line tool that searches for jobs directly on company ATS (Applicant Tracking System) platforms — the kind of roles that never make it to LinkedIn.

Most companies post their open positions on platforms like Greenhouse, Lever, and Ashby before (or instead of) syndicating them to job boards. **jobhunt** queries these platforms directly, giving you access to thousands of hidden opportunities across the US and Europe.

### Search across 1,000+ companies in seconds

<p align="center">
  <img src="https://github.com/aouznini/jobhunt/blob/main/public/imgs/Screenshot_20260403_005951.png?raw=true" alt="jobhunt search python --remote" width="100%">
</p>

### Auto-discover companies by region

<p align="center">
  <img src="https://github.com/aouznini/jobhunt/blob/main/public/imgs/Screenshot_20260403_005906.png?raw=true" alt="jobhunt discover --region eu" width="100%">
</p>

## Why jobhunt?

- **Jobs you won't find on LinkedIn** — Many companies only post on their ATS. Small startups, AI labs, and remote-first companies often skip job boards entirely.
- **Search 1000+ companies at once** — Async requests query hundreds of companies in seconds.
- **Auto-discovery** — Don't know which companies to search? `jobhunt discover` finds them for you, filtered by region.
- **No account needed** — All ATS APIs are public. No login, no API key, no tracking.

## Supported Platforms

| Platform     | Companies | Coverage |
|--------------|-----------|----------|
| Greenhouse   | 25,000+   | US & EU tech, enterprise |
| Lever        | 11,000+   | US startups, mid-market |
| Ashby        | 8,000+    | AI/ML companies, fast-growing startups |
| Recruitee    | EU-focused | European tech companies |
| Rippling     | Growing   | HR-tech companies |

## Installation

Requires Python 3.10+.

```bash
# Clone the repo
git clone <repo-url>
cd job

# Install in editable mode
pip install -e .

# Verify it works
jobhunt --help
```

## Quick Start

### Step 1: Search with built-in companies

jobhunt ships with **1,000+ validated companies** (GitLab, Cloudflare, OpenAI, Notion, Vercel, 1Password, Deel, Back Market, and many more). You can search immediately:

```bash
# Find remote engineering jobs
jobhunt search "engineer" --remote

# Find support roles
jobhunt search "support" --remote

# Search only AI companies
jobhunt search "engineer" --tag ai

# Search European companies
jobhunt search --tag eu
```

### Step 2: Discover more companies

Expand your database with auto-discovery. This fetches company lists from community sources and validates them against ATS APIs:

```bash
# Preview what's available (no changes saved)
jobhunt discover --dry-run

# Discover companies with EU jobs
jobhunt discover --region eu

# Discover companies with US jobs on Greenhouse
jobhunt discover --region us --platform greenhouse

# Discover all companies (no region filter)
jobhunt discover
```

Discovery can find even more companies beyond the 1,000+ built-in ones.

### Step 3: Search across everything

```bash
# Search all discovered + built-in companies
jobhunt search "python developer" --remote

# Export results to JSON for further processing
jobhunt search "engineer" --remote --output jobs.json

# Limit results
jobhunt search "backend" --remote --limit 30
```

## Usage Guide

### Searching for jobs

```bash
jobhunt search [KEYWORDS] [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--remote` | `-r` | Only show remote positions |
| `--location TEXT` | `-l` | Filter by location (e.g. "Berlin", "US") |
| `--platform NAME` | `-p` | Filter by ATS (greenhouse, lever, ashby, rippling, recruitee) |
| `--tag TEXT` | `-t` | Filter companies by tag (e.g. "ai", "fintech", "eu") |
| `--department TEXT` | `-d` | Filter by department |
| `--output PATH` | `-o` | Export results to a JSON file |
| `--limit N` | | Max number of results to display |
| `--no-cache` | | Bypass the 1-hour cache for fresh results |
| `--concurrency N` | | Max concurrent API requests (default: 20) |

**Examples:**

```bash
# Remote Python jobs at fintech companies
jobhunt search "python" --remote --tag fintech

# All jobs in Berlin
jobhunt search --location "Berlin"

# Backend roles on Lever and Ashby only
jobhunt search "backend" --platform lever --platform ashby

# DevOps jobs, exported to JSON
jobhunt search "devops" --remote --output devops_jobs.json
```

### Auto-discovering companies

```bash
jobhunt discover [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--region TEXT` | `-r` | Filter by region: `eu`, `us`, `uk`, `remote` |
| `--platform NAME` | `-p` | Only discover for a specific ATS platform |
| `--dry-run` | | Preview results without saving |
| `--skip-validation` | | Skip API validation (faster, may include inactive companies) |
| `--source URL` | | Use a custom community source URL |
| `--concurrency N` | | Max concurrent requests (default: 50) |
| `--limit N` | | Max companies to discover |

**How discovery works:**

1. Fetches company slug lists from community-maintained sources
2. Deduplicates against your existing database
3. Validates each company by pinging the ATS API
4. If `--region` is set, probes each company's jobs for location matches
5. Shows a summary and asks for confirmation before saving

**Examples:**

```bash
# Find all EU companies across all platforms
jobhunt discover --region eu

# Preview remote-friendly companies on Ashby
jobhunt discover --region remote --platform ashby --dry-run

# Fast discovery without validation
jobhunt discover --skip-validation

# Discover US companies, max 100
jobhunt discover --region us --limit 100
```

### Managing companies

```bash
# List all companies in your database
jobhunt companies list

# Filter by platform or tag
jobhunt companies list --platform ashby
jobhunt companies list --tag ai

# Manually add a company
jobhunt companies add greenhouse stripe --name "Stripe" --tags "fintech,payments"

# Remove a company
jobhunt companies remove greenhouse stripe

# Import from a JSON file
jobhunt companies import ./my-companies.json
```

**Import file format:**

```json
{
  "version": 1,
  "companies": [
    {"slug": "mycompany", "name": "My Company", "platform": "greenhouse", "tags": ["startup"]}
  ]
}
```

### Other commands

```bash
# List supported ATS platforms
jobhunt platforms

# Clear cached job results
jobhunt cache clear
```

## How It Works

```
                    jobhunt search "engineer" --remote
                                  |
                    +-------------+-------------+
                    |             |             |
              Greenhouse      Lever         Ashby        ...
              (boards-api)  (api.lever)  (ashbyhq)
                    |             |             |
                    +-------------+-------------+
                                  |
                         Normalize to Job model
                                  |
                    Filter: keywords, remote, location
                                  |
                         Display results table
```

1. **Load companies** from built-in database + user additions (`~/.config/jobhunt/`)
2. **Fetch jobs** from each company's ATS API concurrently (async, 20 connections)
3. **Normalize** different API response formats into a unified Job model
4. **Filter** by keywords, remote status, location, department, tags
5. **Display** as a terminal table with numbered apply URLs
6. **Cache** results for 1 hour to avoid re-fetching (`~/.cache/jobhunt/`)

## Available Tags

Use tags to filter companies by category:

| Category | Tags |
|----------|------|
| Industry | `ai`, `fintech`, `health`, `gaming`, `ecommerce`, `education`, `biotech`, `blockchain` |
| Function | `devtools`, `infra`, `database`, `security`, `monitoring`, `search`, `automation` |
| Region | `eu`, `remote-first` |
| Type | `startup`, `open-source`, `saas`, `marketplace` |
| Other | `api`, `cms`, `hr`, `productivity`, `design`, `collaboration` |

## File Locations

| What | Where |
|------|-------|
| Built-in company database | Packaged with `jobhunt` (1,000+ companies) |
| Your added companies | `~/.config/jobhunt/companies.json` |
| Job cache | `~/.cache/jobhunt/*.json.gz` |

## Tips

- **You're ready out of the box.** The built-in database has 1,000+ companies. Run `jobhunt discover --region eu` to find even more.
- **Use tags for targeted searches.** `--tag ai --remote` is faster than searching everything and gives more relevant results.
- **Export + filter externally.** Use `--output jobs.json` to get structured data you can filter with `jq`, import into spreadsheets, or feed into other tools.
- **Cache is your friend.** Results are cached for 1 hour. Use `--no-cache` only when you need fresh data.
- **Add companies you know about.** If a company you're interested in uses Greenhouse/Lever/Ashby, add it: `jobhunt companies add greenhouse companyslug --name "Company Name"`.
- **Finding the slug.** Visit a company's careers page. If the URL looks like `boards.greenhouse.io/acme` or `jobs.lever.co/acme`, the slug is `acme`.

## License

MIT
