from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from jobhunt.cache import JobCache
from jobhunt.client import JobhuntClient
from jobhunt.db import CompanyDB
from jobhunt.display import display_jobs_table, export_json
from jobhunt.models import ATSPlatform, Company, SearchQuery
from jobhunt.providers import PROVIDERS
from jobhunt.search import filter_jobs

app = typer.Typer(help="Search for jobs across ATS platforms (Greenhouse, Lever, Ashby, Rippling, Recruitee, Workable, SmartRecruiters, JazzHR, Breezy, Teamtailor, Homerun, BambooHR, Personio, and more)")
companies_app = typer.Typer(help="Manage the company database")
cache_app = typer.Typer(help="Manage the cache")
app.add_typer(companies_app, name="companies")
app.add_typer(cache_app, name="cache")

console = Console()


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


@app.command()
def search(
    keywords: Optional[list[str]] = typer.Argument(None, help="Search keywords (e.g. 'engineer' 'remote')"),
    remote: bool = typer.Option(False, "--remote", "-r", help="Only show remote jobs"),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Filter by location"),
    platform: Optional[list[ATSPlatform]] = typer.Option(None, "--platform", "-p", help="Filter by ATS platform"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Filter companies by tag"),
    department: Optional[str] = typer.Option(None, "--department", "-d", help="Filter by department"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Export results to JSON file"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max results to display"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache"),
    refresh: bool = typer.Option(False, "--refresh", help="Force re-fetch all companies before displaying"),
    concurrency: int = typer.Option(20, "--concurrency", help="Max concurrent requests"),
) -> None:
    """Search for jobs across ATS platforms."""
    db = CompanyDB()
    companies = db.get_all(tags=tag or None)

    if platform:
        companies = [c for c in companies if c.platform in platform]

    if not companies:
        console.print("[red]No companies in database. Add some with: jobhunt companies add[/red]")
        raise typer.Exit(1)

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


@app.command()
def discover(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Filter by region: eu, us, uk, remote"),
    platform: Optional[list[ATSPlatform]] = typer.Option(None, "--platform", "-p", help="Only discover for specific ATS platforms"),
    source: Optional[str] = typer.Option(None, "--source", help="Source: perplexity, perplexity-deep, github-lists, aggregators, detect, all, or a CSV URL"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be added without saving"),
    skip_validation: bool = typer.Option(False, "--skip-validation", help="Skip slug validation (faster, may include dead slugs)"),
    concurrency: int = typer.Option(50, "--concurrency", help="Max concurrent requests"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max companies to discover"),
    urls_file: Optional[Path] = typer.Option(None, "--urls", help="File with career page URLs (one per line) for --source detect"),
) -> None:
    """Auto-discover companies from community sources or Perplexity AI."""
    db = CompanyDB()
    existing_keys = db.get_all_keys()

    if source == "perplexity":
        _discover_perplexity(
            region=region,
            platform=platform,
            dry_run=dry_run,
            skip_validation=skip_validation,
            concurrency=concurrency,
            limit=limit,
            db=db,
            existing_keys=existing_keys,
        )
        return

    if source == "perplexity-deep":
        _discover_perplexity_deep(
            region=region, platform=platform, dry_run=dry_run,
            skip_validation=skip_validation, concurrency=concurrency,
            limit=limit, db=db, existing_keys=existing_keys,
        )
        return

    if source in ("github-lists", "aggregators", "detect", "all"):
        _discover_new_sources(
            source=source, region=region, platform=platform,
            dry_run=dry_run, skip_validation=skip_validation,
            concurrency=concurrency, limit=limit, db=db,
            existing_keys=existing_keys, urls_file=urls_file,
        )
        return

    from jobhunt.discovery import DEFAULT_SOURCES, DiscoverySource, discover as run_discover

    sources = DEFAULT_SOURCES
    if source:
        sources = [DiscoverySource(name="Custom", url=source)]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching company lists from sources...", total=None)

        def on_progress(stage: str, current: int, total: int) -> None:
            if stage == "fetch":
                progress.update(task, description="Fetching company lists from sources...")
            elif stage == "validate":
                progress.update(task, description=f"Validating slugs ({current}/{total})...")
            elif stage == "region":
                progress.update(task, description=f"Probing regions ({current}/{total})...")

        discovered = asyncio.run(
            run_discover(
                sources=sources,
                platforms=platform or None,
                region=region,
                max_concurrent=concurrency,
                existing_keys=existing_keys,
                on_progress=on_progress,
                skip_validation=skip_validation,
            )
        )

    if limit:
        discovered = discovered[:limit]

    _display_and_save_discovered(discovered, region, dry_run, db, existing_keys)


def _discover_perplexity(
    region: Optional[str],
    platform: Optional[list[ATSPlatform]],
    dry_run: bool,
    skip_validation: bool,
    concurrency: int,
    limit: Optional[int],
    db: CompanyDB,
    existing_keys: set[tuple[str, str]],
) -> None:
    """Discover companies using Perplexity AI web search."""
    from jobhunt.perplexity import discover_via_perplexity
    from jobhunt.discovery import DiscoveredCompany, validate_slug

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Querying Perplexity AI for companies...", total=None)

        candidates = asyncio.run(
            discover_via_perplexity(
                platforms=platform or None,
                region=region,
            )
        )

        progress.update(task, description=f"Found {len(candidates)} candidates from Perplexity")

    if not candidates:
        console.print("[yellow]No companies found via Perplexity.[/yellow]")
        return

    # Deduplicate against existing database
    new_candidates = [
        c for c in candidates
        if (c.platform.value, c.slug) not in existing_keys
    ]

    if not new_candidates:
        console.print("[yellow]All discovered companies are already in the database.[/yellow]")
        return

    console.print(f"[green]Perplexity found {len(new_candidates)} new candidates (filtered {len(candidates) - len(new_candidates)} existing)[/green]")

    # Convert to DiscoveredCompany for validation
    discovered = [
        DiscoveredCompany(
            slug=c.slug,
            name=c.name,
            platform=c.platform,
            region_tags=[region] if region else ["discovered"],
        )
        for c in new_candidates
    ]

    # Validate slugs against ATS APIs
    if not skip_validation:
        import httpx

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            total = len(discovered)
            task = progress.add_task(f"Validating {total} slugs...", total=None)
            validated_count = 0

            async def validate_all() -> None:
                nonlocal validated_count
                semaphore = asyncio.Semaphore(min(concurrency, 20))
                async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                    async def validate_one(c: DiscoveredCompany) -> None:
                        nonlocal validated_count
                        await validate_slug(client, semaphore, c)
                        validated_count += 1
                        progress.update(task, description=f"Validating slugs ({validated_count}/{total})...")

                    await asyncio.gather(*[validate_one(c) for c in discovered])

            asyncio.run(validate_all())

        valid_before = len(discovered)
        discovered = [c for c in discovered if c.valid]
        console.print(f"[dim]Validation: {len(discovered)}/{valid_before} slugs confirmed valid[/dim]")

    if limit:
        discovered = discovered[:limit]

    _display_and_save_discovered(discovered, region, dry_run, db, existing_keys)


def _discover_perplexity_deep(
    region: Optional[str],
    platform: Optional[list[ATSPlatform]],
    dry_run: bool,
    skip_validation: bool,
    concurrency: int,
    limit: Optional[int],
    db: CompanyDB,
    existing_keys: set[tuple[str, str]],
) -> None:
    """Discover companies using enhanced Perplexity AI with industry-specific queries."""
    from jobhunt.perplexity import discover_via_perplexity_deep
    from jobhunt.discovery import DiscoveredCompany, validate_slug

    exclude_slugs = {slug for _, slug in existing_keys}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Querying Perplexity AI (deep discovery)...", total=None)

        candidates = asyncio.run(
            discover_via_perplexity_deep(
                platforms=platform or None,
                region=region,
                exclude_slugs=exclude_slugs,
            )
        )

        progress.update(task, description=f"Found {len(candidates)} candidates from Perplexity (deep)")

    if not candidates:
        console.print("[yellow]No companies found via Perplexity deep discovery.[/yellow]")
        return

    new_candidates = [
        c for c in candidates
        if (c.platform.value, c.slug) not in existing_keys
    ]

    if not new_candidates:
        console.print("[yellow]All discovered companies are already in the database.[/yellow]")
        return

    console.print(f"[green]Deep discovery found {len(new_candidates)} new candidates[/green]")

    discovered = [
        DiscoveredCompany(
            slug=c.slug, name=c.name, platform=c.platform,
            region_tags=[region] if region else ["discovered"],
        )
        for c in new_candidates
    ]

    if not skip_validation:
        import httpx as httpx_mod

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            total = len(discovered)
            task = progress.add_task(f"Validating {total} slugs...", total=None)
            validated_count = 0

            async def validate_all() -> None:
                nonlocal validated_count
                semaphore = asyncio.Semaphore(min(concurrency, 20))
                async with httpx_mod.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                    async def validate_one(c: DiscoveredCompany) -> None:
                        nonlocal validated_count
                        await validate_slug(client, semaphore, c)
                        validated_count += 1
                        progress.update(task, description=f"Validating slugs ({validated_count}/{total})...")

                    await asyncio.gather(*[validate_one(c) for c in discovered])

            asyncio.run(validate_all())

        valid_before = len(discovered)
        discovered = [c for c in discovered if c.valid]
        console.print(f"[dim]Validation: {len(discovered)}/{valid_before} slugs confirmed valid[/dim]")

    if limit:
        discovered = discovered[:limit]

    _display_and_save_discovered(discovered, region, dry_run, db, existing_keys)


def _discover_new_sources(
    source: str,
    region: Optional[str],
    platform: Optional[list[ATSPlatform]],
    dry_run: bool,
    skip_validation: bool,
    concurrency: int,
    limit: Optional[int],
    db: CompanyDB,
    existing_keys: set[tuple[str, str]],
    urls_file: Optional[Path] = None,
) -> None:
    """Discover companies from GitHub lists, aggregators, or ATS detection."""
    from jobhunt.discovery import DiscoveredCompany, validate_slug

    async def run_sources() -> list[DiscoveredCompany]:
        import logging
        logging.basicConfig(level=logging.INFO, format="%(message)s")

        results: list[DiscoveredCompany] = []

        if source in ("github-lists", "all"):
            from jobhunt.discovery_sources.github_lists import discover_from_github_lists
            try:
                console.print("[dim]Fetching GitHub awesome-lists...[/dim]")
                found = await discover_from_github_lists(max_concurrent=concurrency)
                console.print(f"[green]GitHub lists: {len(found)} companies detected[/green]")
                results.extend(found)
            except Exception as e:
                console.print(f"[red]GitHub lists failed: {e}[/red]")

        if source in ("aggregators", "all"):
            from jobhunt.discovery_sources.aggregators import discover_from_aggregators
            try:
                console.print("[dim]Fetching HN Who's Hiring + YC directory...[/dim]")
                found = await discover_from_aggregators(max_concurrent=concurrency)
                console.print(f"[green]Aggregators: {len(found)} companies detected[/green]")
                results.extend(found)
            except Exception as e:
                console.print(f"[red]Aggregators failed: {e}[/red]")

        if source in ("detect", "all"):
            if urls_file and urls_file.exists():
                from jobhunt.discovery_sources import CareerPageEntry
                from jobhunt.discovery_sources.ats_detector import detect_ats_batch
                entries = []
                for line in urls_file.read_text().strip().split("\n"):
                    line = line.strip()
                    if line and line.startswith("http"):
                        name = line.split("//")[1].split("/")[0].split(".")[0]
                        entries.append(CareerPageEntry(company_name=name, career_url=line))
                if entries:
                    found = await detect_ats_batch(entries, max_concurrent=concurrency)
                    console.print(f"[dim]ATS detection: {len(found)} companies detected from {len(entries)} URLs[/dim]")
                    results.extend(found)
            elif source == "detect":
                console.print("[yellow]--urls file required for 'detect' source[/yellow]")

        return results

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Running discovery source: {source}...", total=None)
        all_discovered = asyncio.run(run_sources())

    if not all_discovered:
        console.print("[yellow]No companies discovered from selected sources.[/yellow]")
        return

    if platform:
        all_discovered = [c for c in all_discovered if c.platform in platform]

    all_discovered = [
        c for c in all_discovered
        if (c.platform.value, c.slug) not in existing_keys
    ]

    seen: set[tuple[str, str]] = set()
    unique: list[DiscoveredCompany] = []
    for c in all_discovered:
        key = (c.platform.value, c.slug)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    all_discovered = unique

    console.print(f"[green]Found {len(all_discovered)} new unique companies[/green]")

    if not skip_validation and all_discovered:
        import httpx as httpx_mod

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            total = len(all_discovered)
            task = progress.add_task(f"Validating {total} slugs...", total=None)
            validated_count = 0

            async def validate_all() -> None:
                nonlocal validated_count
                semaphore = asyncio.Semaphore(min(concurrency, 20))
                async with httpx_mod.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                    async def validate_one(c: DiscoveredCompany) -> None:
                        nonlocal validated_count
                        await validate_slug(client, semaphore, c)
                        validated_count += 1
                        progress.update(task, description=f"Validating slugs ({validated_count}/{total})...")

                    await asyncio.gather(*[validate_one(c) for c in all_discovered])

            asyncio.run(validate_all())

        valid_before = len(all_discovered)
        all_discovered = [c for c in all_discovered if c.valid]
        console.print(f"[dim]Validation: {len(all_discovered)}/{valid_before} slugs confirmed valid[/dim]")

    if limit:
        all_discovered = all_discovered[:limit]

    _display_and_save_discovered(all_discovered, region, dry_run, db, existing_keys)


def _display_and_save_discovered(
    discovered: list,
    region: Optional[str],
    dry_run: bool,
    db: CompanyDB,
    existing_keys: set[tuple[str, str]],
) -> None:
    """Display discovered companies and optionally save them."""
    if not discovered:
        console.print("[yellow]No new companies discovered.[/yellow]")
        if region:
            console.print("[dim]Try without --region to see all available companies.[/dim]")
        return

    from rich.table import Table
    from collections import Counter
    platform_counts = Counter(c.platform.value for c in discovered)
    console.print(f"\n[green]Discovered {len(discovered)} new companies:[/green]")
    for plat, count in sorted(platform_counts.items()):
        console.print(f"  [cyan]{plat}[/cyan]: {count}")

    table = Table(title=f"Sample (first {min(20, len(discovered))})")
    table.add_column("Platform", style="cyan")
    table.add_column("Slug", style="green")
    table.add_column("Name")
    if region:
        table.add_column("Region", style="yellow")

    for c in discovered[:20]:
        row = [c.platform.value, c.slug, c.name]
        if region:
            tags = c.region_tags if hasattr(c, "region_tags") else []
            row.append(", ".join(tags) if tags else "-")
        table.add_row(*row)
    console.print(table)

    if dry_run:
        console.print("\n[dim]--dry-run: no companies saved.[/dim]")
        return

    if not typer.confirm(f"\nAdd {len(discovered)} companies to your database?"):
        return

    companies_to_add = [
        Company(
            slug=c.slug,
            name=c.name,
            platform=c.platform,
            tags=c.region_tags if hasattr(c, "region_tags") and c.region_tags else ["discovered"],
        )
        for c in discovered
    ]
    count = db.bulk_add(companies_to_add)
    console.print(f"[green]Added {count} new companies to your database.[/green]")
    console.print(f"[dim]Run 'jobhunt search' to search across all {len(existing_keys) + count} companies.[/dim]")


@app.command()
def platforms() -> None:
    """List supported ATS platforms."""
    for p in ATSPlatform:
        console.print(f"  [cyan]{p.value}[/cyan]")


@companies_app.command("list")
def companies_list(
    platform: Optional[ATSPlatform] = typer.Option(None, "--platform", "-p"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t"),
) -> None:
    """List companies in the database."""
    db = CompanyDB()
    companies = db.get_all(platform=platform, tags=tag or None)

    if not companies:
        console.print("[yellow]No companies found.[/yellow]")
        return

    from rich.table import Table
    table = Table(title=f"{len(companies)} companies")
    table.add_column("Platform", style="cyan")
    table.add_column("Slug", style="green")
    table.add_column("Name")
    table.add_column("Tags", style="dim")

    for c in companies:
        table.add_row(c.platform.value, c.slug, c.name, ", ".join(c.tags) if c.tags else "-")
    console.print(table)


@companies_app.command("add")
def companies_add(
    platform: ATSPlatform = typer.Argument(..., help="ATS platform"),
    slug: str = typer.Argument(..., help="Company slug/token on the ATS"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Display name (defaults to slug)"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
) -> None:
    """Add a company to your local database."""
    company = Company(
        slug=slug,
        name=name or slug,
        platform=platform,
        tags=[t.strip() for t in tags.split(",")] if tags else [],
    )
    db = CompanyDB()
    db.add(company)
    console.print(f"[green]Added {company.name} ({company.platform}/{company.slug})[/green]")


@companies_app.command("remove")
def companies_remove(
    platform: ATSPlatform = typer.Argument(..., help="ATS platform"),
    slug: str = typer.Argument(..., help="Company slug"),
) -> None:
    """Remove a company from your local database."""
    db = CompanyDB()
    if db.remove(platform, slug):
        console.print(f"[green]Removed {platform}/{slug}[/green]")
    else:
        console.print(f"[yellow]{platform}/{slug} not found in user database[/yellow]")


@companies_app.command("import")
def companies_import(
    source: Path = typer.Argument(..., help="Path to a companies JSON file"),
) -> None:
    """Import companies from a JSON file."""
    if not source.exists():
        console.print(f"[red]File not found: {source}[/red]")
        raise typer.Exit(1)
    db = CompanyDB()
    count = db.import_from_file(source)
    console.print(f"[green]Imported {count} new companies[/green]")


@cache_app.command("clear")
def cache_clear() -> None:
    """Clear the job cache."""
    c = JobCache()
    count = c.clear()
    console.print(f"[green]Cleared {count} cached entries[/green]")
