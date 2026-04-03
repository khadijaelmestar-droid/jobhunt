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

app = typer.Typer(help="Search for jobs across ATS platforms (Greenhouse, Lever, Ashby, Rippling, Recruitee)")
companies_app = typer.Typer(help="Manage the company database")
cache_app = typer.Typer(help="Manage the cache")
app.add_typer(companies_app, name="companies")
app.add_typer(cache_app, name="cache")

console = Console()


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
        to_fetch: list[Company] = []

        if cache:
            for c in companies:
                cached = cache.get(c.platform, c.slug)
                if cached is not None:
                    cached_jobs.extend(cached)
                else:
                    to_fetch.append(c)
        else:
            to_fetch = companies

        fetched: list[Job] = []
        if to_fetch:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Fetching jobs from {len(to_fetch)} companies...", total=None)

                def on_progress(company: Company, had_jobs: bool) -> None:
                    progress.update(task, description=f"Fetched {company.name} ({company.platform})")

                fetched = await client.fetch_all(to_fetch, PROVIDERS, on_progress=on_progress)

            if cache:
                # Group fetched jobs by company and cache
                by_company: dict[tuple[str, str], list[Job]] = {}
                for j in fetched:
                    key = (j.platform, j.company_slug)
                    by_company.setdefault(key, []).append(j)
                for (plat, slug), jobs in by_company.items():
                    cache.set(ATSPlatform(plat), slug, jobs)
                # Also cache empty results for companies that returned nothing
                fetched_slugs = {(j.platform, j.company_slug) for j in fetched}
                for c in to_fetch:
                    if (c.platform, c.slug) not in fetched_slugs:
                        cache.set(c.platform, c.slug, [])

        return cached_jobs + fetched

    all_jobs = asyncio.run(run())
    results = filter_jobs(all_jobs, query)

    display_jobs_table(results, console=console, limit=limit)

    if output:
        export_json(results, output)
        console.print(f"\n[green]Exported {len(results)} jobs to {output}[/green]")


@app.command()
def discover(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="Filter by region: eu, us, uk, remote"),
    platform: Optional[list[ATSPlatform]] = typer.Option(None, "--platform", "-p", help="Only discover for specific ATS platforms"),
    source: Optional[str] = typer.Option(None, "--source", help="Custom source URL (CSV)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be added without saving"),
    skip_validation: bool = typer.Option(False, "--skip-validation", help="Skip slug validation (faster, may include dead slugs)"),
    concurrency: int = typer.Option(50, "--concurrency", help="Max concurrent requests"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Max companies to discover"),
) -> None:
    """Auto-discover companies from community sources."""
    from jobhunt.discovery import DEFAULT_SOURCES, DiscoverySource, discover as run_discover

    sources = DEFAULT_SOURCES
    if source:
        sources = [DiscoverySource(name="Custom", url=source)]

    db = CompanyDB()
    existing_keys = db.get_all_keys()

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

    if not discovered:
        console.print("[yellow]No new companies discovered.[/yellow]")
        if region:
            console.print(f"[dim]Try without --region to see all available companies.[/dim]")
        return

    # Show summary
    from rich.table import Table
    from collections import Counter
    platform_counts = Counter(c.platform.value for c in discovered)
    console.print(f"\n[green]Discovered {len(discovered)} new companies:[/green]")
    for plat, count in sorted(platform_counts.items()):
        console.print(f"  [cyan]{plat}[/cyan]: {count}")

    # Show sample
    table = Table(title=f"Sample (first {min(20, len(discovered))})")
    table.add_column("Platform", style="cyan")
    table.add_column("Slug", style="green")
    table.add_column("Name")
    if region:
        table.add_column("Region", style="yellow")

    for c in discovered[:20]:
        row = [c.platform.value, c.slug, c.name]
        if region:
            row.append(", ".join(c.region_tags) if c.region_tags else "-")
        table.add_row(*row)
    console.print(table)

    if dry_run:
        console.print("\n[dim]--dry-run: no companies saved.[/dim]")
        return

    # Convert to Company models and save
    if not typer.confirm(f"\nAdd {len(discovered)} companies to your database?"):
        return

    companies_to_add = [
        Company(
            slug=c.slug,
            name=c.name,
            platform=c.platform,
            tags=c.region_tags if c.region_tags else ["discovered"],
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
